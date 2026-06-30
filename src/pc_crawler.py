# 2026-06-05: 배포 전 안정화를 위해 PC Premium 스크롤 수집 범위를 최적화합니다.
from datetime import datetime
import time
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.parser import (
    detect_new_open_pc,
    extract_address_from_pc_text,
    extract_review_count_pc,
    guess_pc_category_from_text,
    is_primary_pc_name_anchor,
    is_valid_pc_place_name,
    normalize_phone,
    split_pc_name_category,
)


# 2026-06-04: PC Premium Mode 디버그용 카드 텍스트 출력 여부입니다.
DEBUG_CARD_TEXT = False


def _safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("cp949", errors="replace").decode("cp949"))


# 2026-06-04: PC 네이버 지도 searchIframe 내부 업체명 anchor 후보 selector입니다.
CARD_SELECTORS = [
    "a[href*='/place/']",
    "a[href*='place.naver.com']",
    "a",
]

FIELD_SELECTORS = {
    "category": [
        "span[class*='KCMnt']",
        "span[class*='DJJvD']",
        "em[class*='category']",
        "span[class*='category']",
    ],
    "phone": [
        "a[href^='tel:']",
        "span:has-text('02-')",
        "span:has-text('031-')",
        "span:has-text('032-')",
        "span:has-text('042-')",
        "span:has-text('051-')",
        "span:has-text('053-')",
        "span:has-text('070-')",
        "span:has-text('0507-')",
    ],
}

def _safe_text(locator, selector_candidates) -> str:
    """2026-06-04: selector 실패 시 빈 문자열을 반환합니다."""
    for selector in selector_candidates:
        try:
            element = locator.locator(selector).first
            if element.count() == 0:
                continue
            text = element.inner_text(timeout=1000).strip()
            if text:
                return " ".join(text.split())
        except Exception:
            continue
    return ""


def _safe_attr(locator, selector_candidates, attr: str) -> str:
    """2026-06-04: attribute 추출 실패 시 빈 문자열을 반환합니다."""
    for selector in selector_candidates:
        try:
            element = locator.locator(selector).first
            if element.count() == 0:
                continue
            value = element.get_attribute(attr, timeout=1000)
            if value:
                return value.strip()
        except Exception:
            continue
    return ""


def _safe_inner_text(locator) -> str:
    """2026-06-04: 카드 전체 텍스트 추출 실패 시 빈 문자열을 반환합니다."""
    try:
        return locator.inner_text(timeout=1000)
    except Exception:
        return ""


def _find_search_frame(page):
    """2026-06-04: searchIframe을 우선 찾고, 실패 시 frames fallback을 사용합니다."""
    try:
        frame = page.frame(name="searchIframe")
        if frame:
            print("[pc_crawler] searchIframe found")
            return frame
    except Exception:
        pass

    try:
        frame_locator = page.frame_locator("#searchIframe")
        frame_locator.locator("body").first.wait_for(timeout=5000)
        frame = page.frame(name="searchIframe")
        if frame:
            print("[pc_crawler] searchIframe found")
            return frame
    except Exception:
        pass

    for frame in page.frames:
        frame_id = f"{frame.name} {frame.url}".lower()
        if "search" in frame_id:
            print("[pc_crawler] searchIframe found")
            return frame

    print("[pc_crawler] searchIframe not found")
    return None


def _find_place_anchors(frame):
    """2026-06-04: 실제 업체명 anchor 후보를 찾습니다."""
    for selector in CARD_SELECTORS:
        try:
            links = frame.locator(selector)
            count = links.count()
            if count > 0:
                print(f"[pc_crawler] anchor selector matched: {selector} ({count})")
                return links
        except Exception as exc:
            _safe_print(f"[pc_crawler] anchor selector failed: {selector} ({exc})")
            continue
    return frame.locator("a")


def _find_pc_cards(frame):
    try:
        cards = frame.locator("li:has(a[href*='/place/'])")
        count = cards.count()
        if count > 0:
            print(f"[pc_crawler] card selector matched: li:has(a[href*='/place/']) ({count})")
            return cards
    except Exception as exc:
        _safe_print(f"[pc_crawler] card selector failed: li:has(a[href*='/place/']) ({exc})")

    anchors = _find_place_anchors(frame)
    for selector in [
        "xpath=ancestor::li[1]",
        "xpath=ancestor::div[@role='listitem'][1]",
        "xpath=ancestor::div[1]",
    ]:
        try:
            fallback_cards = anchors.locator(selector)
            count = fallback_cards.count()
            if count > 0:
                print(f"[pc_crawler] fallback card selector matched: {selector} ({count})")
                return fallback_cards
        except Exception as exc:
            _safe_print(f"[pc_crawler] fallback card selector failed: {selector} ({exc})")

    return anchors


def _is_pc_captcha_detected(page, frame=None) -> bool:
    selectors = [
        "#wtm-captcha-root",
        "text=보안",
        "text=사람",
        "text=자동",
    ]
    targets = [page]
    if frame is not None:
        targets.append(frame)

    for target in targets:
        for selector in selectors:
            try:
                element = target.locator(selector).first
                if element.count() > 0 and element.is_visible(timeout=300):
                    return True
            except Exception:
                continue
    return False


def _get_card_from_anchor(anchor):
    """2026-06-04: 업체명 anchor의 가장 가까운 카드 상위 요소를 반환합니다."""
    for selector in [
        "xpath=ancestor::li[1]",
        "xpath=ancestor::div[@role='listitem'][1]",
        "xpath=ancestor::div[1]",
    ]:
        try:
            card = anchor.locator(selector).first
            if card.count() > 0:
                return card
        except Exception:
            continue
    return anchor


def _light_scroll_cards(
    page,
    anchors,
    max_scrolls: int = 8,
    stop_event=None,
    pause_event=None,
) -> None:
    """2026-06-05: 후보 카드 수 증가가 멈추면 중단하는 제한 스크롤입니다."""
    no_new_cards_count = 0
    previous_count = 0

    try:
        previous_count = anchors.count()
    except Exception:
        previous_count = 0

    for index in range(max_scrolls):
        if stop_event is not None and stop_event.is_set():
            print("[pc_crawler] stop event detected, aborting pc crawl")
            break
        if pause_event is not None and pause_event.is_set():
            print("[pc_crawler] pause event detected, blocking...")
            while pause_event.is_set():
                if stop_event is not None and stop_event.is_set():
                    break
                page.wait_for_timeout(500)
            if stop_event is not None and stop_event.is_set():
                print("[pc_crawler] stop event detected, aborting pc crawl")
                break
        try:
            for _ in range(4):
                page.mouse.wheel(0, 350)
                page.wait_for_timeout(120)
            print(f"[pc_crawler] scroll {index + 1}/{max_scrolls}")
            page.wait_for_timeout(500)

            current_count = anchors.count()
            print(f"[pc_crawler] cards before={previous_count}, after={current_count}")
            if current_count <= previous_count:
                no_new_cards_count += 1
            else:
                no_new_cards_count = 0

            print(f"[pc_crawler] no new cards count={no_new_cards_count}")
            if no_new_cards_count >= 2:
                break

            previous_count = current_count
        except Exception as exc:
            _safe_print(f"[pc_crawler] scroll skipped {index + 1}: {exc}")
            break


def _extract_name_from_anchor(anchor) -> str:
    """2026-06-04: 카드 전체 텍스트가 아니라 실제 업체명 anchor 텍스트를 우선 사용합니다."""
    selectors = [
        "span.place_bluelink",
        "span",
        "strong",
    ]
    name = _safe_text(anchor, selectors)
    if not name:
        name = _safe_inner_text(anchor)
    name = " ".join(name.split())
    for separator in ["리뷰", "저장", "공유"]:
        if separator in name:
            name = name.split(separator)[0].strip()
    return name


def _extract_name_from_card(card) -> str:
    for selector in [
        "a[href*='/place/']",
        "a[href*='place.naver.com']",
        "a",
    ]:
        try:
            anchor = card.locator(selector).first
            if anchor.count() > 0:
                name = _extract_name_from_anchor(anchor)
                if name:
                    return name
        except Exception:
            continue
    return _extract_name_from_anchor(card)


def crawl_places_pc(
    keyword: str,
    limit: int = 10,
    new_open_only: bool = False,
    stop_event=None,
    pause_event=None,
) -> list[dict]:
    """2026-06-04: PC searchIframe 리스트에서 새로오픈 업체 발굴용 정보를 수집합니다."""
    results = []
    collected_at = datetime.now().strftime("%Y-%m-%d")
    search_url = f"https://map.naver.com/v5/search/{quote(keyword)}"
    scan_limit = max(limit * 10, 50) if new_open_only else limit
    calculated_scrolls = max(2, (scan_limit // 10) + 1)
    t_scroll = 0.0
    t_get_card = 0.0
    t_inner_text = 0.0
    t_extract = 0.0
    anchor_count = 0
    card_count = 0

    print(f"[pc_crawler] start keyword={keyword}, limit={limit}")
    print(f"[pc_crawler] new_open_only={new_open_only}")
    print(f"[pc_crawler] url={search_url}")

    try:
        with sync_playwright() as playwright:
            # 2026-06-04: PC 지도는 headless에서 DOM이 달라져 화면 밖 창으로 실행합니다.
            browser = playwright.chromium.launch(
                headless=False,
                args=[
                    "--window-position=-32000,-32000",
                    "--window-size=1400,900",
                ],
            )
            context = browser.new_context(viewport={"width": 1400, "height": 900})
            page = context.new_page()

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(5000)
            except PlaywrightTimeoutError:
                print("[pc_crawler] page load timeout, continue with current DOM")

            search_frame = _find_search_frame(page)
            if not search_frame:
                context.close()
                browser.close()
                return []

            seen = set()
            debug_count = 0
            last_progress_printed = 0
            current_page = 1
            max_pages = 15

            while len(results) < limit and current_page <= max_pages:
                if stop_event is not None and stop_event.is_set():
                    print("[pc_crawler] stop event detected, aborting pc crawl")
                    break
                if pause_event is not None and pause_event.is_set():
                    print("[pc_crawler] pause event detected, blocking...")
                    while pause_event.is_set():
                        if stop_event is not None and stop_event.is_set():
                            break
                        page.wait_for_timeout(500)
                    if stop_event is not None and stop_event.is_set():
                        print("[pc_crawler] stop event detected, aborting pc crawl")
                        break

                if _is_pc_captcha_detected(page, search_frame):
                    print("[pc_crawler] captcha detected, returning collected data safely")
                    break

                print(f"[pc_crawler] collect page={current_page}")
                cards = _find_pc_cards(search_frame)
                scroll_start = time.time()
                _light_scroll_cards(
                    page,
                    cards,
                    max_scrolls=calculated_scrolls,
                    stop_event=stop_event,
                    pause_event=pause_event,
                )
                t_scroll += time.time() - scroll_start
                if _is_pc_captcha_detected(page, search_frame):
                    print("[pc_crawler] captcha detected, returning collected data safely")
                    break
                card_count = cards.count()
                anchor_count += card_count
                print(f"[pc_crawler] candidate cards={card_count}")

                for index in range(card_count):
                    if stop_event is not None and stop_event.is_set():
                        print("[pc_crawler] stop event detected, aborting pc crawl")
                        break
                    if len(results) >= limit:
                        break
                    if pause_event is not None and pause_event.is_set():
                        print("[pc_crawler] pause event detected, blocking...")
                        while pause_event.is_set():
                            if stop_event is not None and stop_event.is_set():
                                break
                            page.wait_for_timeout(500)
                        if stop_event is not None and stop_event.is_set():
                            print("[pc_crawler] stop event detected, aborting pc crawl")
                            break
                    try:
                        t_get_card_start = time.time()
                        card = cards.nth(index)
                        t_get_card += time.time() - t_get_card_start

                        t_inner_text_start = time.time()
                        card_text = _safe_inner_text(card)
                        t_inner_text += time.time() - t_inner_text_start

                        t_extract_start = time.time()
                        name = _extract_name_from_card(card)

                        if not is_valid_pc_place_name(name):
                            t_extract += time.time() - t_extract_start
                            continue
                        if "리뷰" not in card_text:
                            t_extract += time.time() - t_extract_start
                            continue
                        if not is_primary_pc_name_anchor(name, card_text):
                            t_extract += time.time() - t_extract_start
                            continue

                        new_open = detect_new_open_pc(card_text)
                        if new_open_only and new_open != "O":
                            t_extract += time.time() - t_extract_start
                            continue

                        if DEBUG_CARD_TEXT and debug_count < 3:
                            print(f"[pc_crawler] card {debug_count} text:")
                            print(card_text[:500])
                            debug_count += 1

                        category = _safe_text(card, FIELD_SELECTORS["category"])
                        name, category = split_pc_name_category(name, category)
                        if not is_valid_pc_place_name(name):
                            t_extract += time.time() - t_extract_start
                            continue

                        if not category:
                            category = guess_pc_category_from_text(card_text, name)

                        address = extract_address_from_pc_text(card_text)
                        phone_text = _safe_text(card, FIELD_SELECTORS["phone"])
                        phone_href = _safe_attr(card, FIELD_SELECTORS["phone"], "href")
                        phone = normalize_phone(phone_text, phone_href)
                        review_count = extract_review_count_pc(card_text)

                        if name in seen:
                            t_extract += time.time() - t_extract_start
                            continue
                        seen.add(name)

                        results.append(
                            {
                                "업체명": name,
                                "업종": category,
                                "새로오픈여부": new_open,
                                "리뷰수": review_count,
                                "주소": address,
                                "대표전화": phone,
                                "수집일": collected_at,
                            }
                        )
                        if len(results) % 10 == 0 or len(results) == limit:
                            print(f"[pc_crawler] collecting... {len(results)}/{limit}")
                            last_progress_printed = len(results)
                        t_extract += time.time() - t_extract_start
                    except Exception as exc:
                        _safe_print(f"[pc_crawler] card parse failed index={index}: {exc}")
                        continue

                if len(results) >= limit:
                    break
                if stop_event is not None and stop_event.is_set():
                    print("[pc_crawler] stop event detected, aborting pc crawl")
                    break
                if current_page >= max_pages:
                    break

                if pause_event is not None and pause_event.is_set():
                    print("[pc_crawler] pause event detected, blocking...")
                    while pause_event.is_set():
                        if stop_event is not None and stop_event.is_set():
                            break
                        page.wait_for_timeout(500)
                    if stop_event is not None and stop_event.is_set():
                        print("[pc_crawler] stop event detected, aborting pc crawl")
                        break

                if _is_pc_captcha_detected(page, search_frame):
                    print("[pc_crawler] captcha detected, returning collected data safely")
                    break

                next_page = current_page + 1
                next_clicked = False
                for selector in [
                    f'a:text-is("{next_page}")',
                    f'button:text-is("{next_page}")',
                    f'a:has-text("{next_page}")',
                    f'button:has-text("{next_page}")',
                ]:
                    try:
                        next_button = search_frame.locator(selector).first
                        if next_button.count() > 0 and next_button.is_visible(timeout=1000):
                            next_button.click(timeout=3000)
                            next_clicked = True
                            break
                    except Exception as exc:
                        _safe_print(f"[pc_crawler] next page selector failed: {selector} ({exc})")
                        continue

                if not next_clicked:
                    print(f"[pc_crawler] next page not found: {next_page}")
                    break

                page.wait_for_timeout(2000)
                if _is_pc_captcha_detected(page, search_frame):
                    print("[pc_crawler] captcha detected, returning collected data safely")
                    break
                current_page += 1

                if stop_event is not None and stop_event.is_set():
                    print("[pc_crawler] stop event detected, aborting pc crawl")
                    break
                if pause_event is not None and pause_event.is_set():
                    print("[pc_crawler] pause event detected, blocking...")
                    while pause_event.is_set():
                        if stop_event is not None and stop_event.is_set():
                            break
                        page.wait_for_timeout(500)
                    if stop_event is not None and stop_event.is_set():
                        print("[pc_crawler] stop event detected, aborting pc crawl")
                        break

            context.close()
            browser.close()
    except Exception as exc:
        _safe_print(f"[pc_crawler] failed safely: {exc}")
        return []
    finally:
        print(
            f"[Profiler] Target: {keyword} | Anchors: {anchor_count} | Saved: {len(results)}"
        )
        print(
            f"[Profiler] Scroll: {t_scroll:.2f}s | GetCard: {t_get_card:.2f}s | "
            f"InnerText: {t_inner_text:.2f}s | Extract: {t_extract:.2f}s"
        )

    if last_progress_printed != len(results) and len(results) > 0:
        print(f"[pc_crawler] collecting... {len(results)}/{limit}")
    print(f"[pc_crawler] completed {len(results)}/{limit}")
    return results


if __name__ == "__main__":
    results = crawl_places_pc("대전 신상 카페", 10)
    print(results)
