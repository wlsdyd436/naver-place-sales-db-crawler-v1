# 정식 출시 전 PC 단일 엔진 전환 - Stage 2 (browser_session/list_scraper 경계) 청크2.
# PC searchIframe 리스트 화면에서 카드 탐색/스크롤/페이지네이션/행 데이터 수집을
# 담당합니다. entryIframe 상세 진입, 대표전화 상세 수집, Excel/ui 연결은 이 모듈의
# 책임이 아닙니다(각각 향후 Stage에서 다룸).
#
# 진단 캡처 계약(확정): 실패 시 이 계층(page가 살아있는 시점)에서
# safety.classify_exception -> (capture_artifacts=True면) session.capture_diagnostics
# -> 예외에 diagnostics_captured=True 마커만 부착 -> exc.page는 붙이지 않고 그대로
# re-raise 합니다. pipeline.py는 exc.page가 없으면 자체 캡처를 하지 않으므로
# (getattr(exc, "page", None) 확인), 이 계약을 지키는 한 중복 캡처는 발생하지 않습니다.
import re
from datetime import datetime
from urllib.parse import quote

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
from src.pc.browser_session import BrowserSession
from src.pc.safety import classify_exception


_MAX_PAGES = 15

# pc_crawler.py 동작 보존: 업체명 anchor/카드 후보 selector입니다.
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


def _safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("cp949", errors="replace").decode("cp949"))


def _safe_text(locator, selector_candidates) -> str:
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
    try:
        return locator.inner_text(timeout=1000)
    except Exception:
        return ""


def _find_place_anchors(frame):
    for selector in CARD_SELECTORS:
        try:
            links = frame.locator(selector)
            count = links.count()
            if count > 0:
                print(f"[list_scraper] anchor selector matched: {selector} ({count})")
                return links
        except Exception as exc:
            _safe_print(f"[list_scraper] anchor selector failed: {selector} ({exc})")
            continue
    return frame.locator("a")


def _find_pc_cards(frame):
    try:
        cards = frame.locator("li:has(a[href*='/place/'])")
        count = cards.count()
        if count > 0:
            print(f"[list_scraper] card selector matched: li:has(a[href*='/place/']) ({count})")
            return cards
    except Exception as exc:
        _safe_print(f"[list_scraper] card selector failed: li:has(a[href*='/place/']) ({exc})")

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
                print(f"[list_scraper] fallback card selector matched: {selector} ({count})")
                return fallback_cards
        except Exception as exc:
            _safe_print(f"[list_scraper] fallback card selector failed: {selector} ({exc})")

    return anchors


def _get_card_from_anchor(anchor):
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
    """pc_crawler.py 동작 보존: 후보 카드 수 증가가 2회 연속 멈추면 중단하는 제한 스크롤."""
    no_new_cards_count = 0
    previous_count = 0

    try:
        previous_count = anchors.count()
    except Exception:
        previous_count = 0

    for index in range(max_scrolls):
        if _check_stop(stop_event):
            break
        if _wait_while_paused(page, stop_event, pause_event):
            break
        try:
            for _ in range(4):
                page.mouse.wheel(0, 350)
                page.wait_for_timeout(120)
            print(f"[list_scraper] scroll {index + 1}/{max_scrolls}")
            page.wait_for_timeout(500)

            current_count = anchors.count()
            print(f"[list_scraper] cards before={previous_count}, after={current_count}")
            if current_count <= previous_count:
                no_new_cards_count += 1
            else:
                no_new_cards_count = 0

            print(f"[list_scraper] no new cards count={no_new_cards_count}")
            if no_new_cards_count >= 2:
                break

            previous_count = current_count
        except Exception as exc:
            _safe_print(f"[list_scraper] scroll skipped {index + 1}: {exc}")
            break


def _extract_name_from_anchor(anchor) -> str:
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


def _extract_place_href(card) -> str:
    """카드 내 업체 anchor의 href를 추출합니다. 실패 시 빈 문자열을 반환합니다."""
    for selector in CARD_SELECTORS:
        try:
            anchor = card.locator(selector).first
            if anchor.count() == 0:
                continue
            href = anchor.get_attribute("href", timeout=1000)
            if href:
                return href.strip()
        except Exception:
            continue
    return ""


def _parse_place_id(href: str) -> str:
    """anchor href(/place/{id}, /restaurant/{id} 등)에서 place id(숫자)를 추출합니다."""
    if not href:
        return ""
    match = re.search(r"/(\d{5,})", href)
    return match.group(1) if match else ""


def _normalize_pc_place_url(href: str) -> str:
    """anchor href를 절대 URL 형태의 플레이스 URL로 정규화합니다."""
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://map.naver.com{href}"
    return ""


def _build_row(card, collected_at: str, new_open_only: bool, seen: set):
    """카드 하나에서 행 데이터를 만듭니다. 유효하지 않으면 None을 반환합니다.

    pc_crawler.py 동작 보존: 카드 단위 파싱 실패/스킵은 이 카드만 건너뛰고 예외를
    전파하지 않습니다(카드 파싱 실패는 CAPTCHA/보안 차단 신호가 아니므로, 진단 캡처
    계약과는 무관합니다).
    """
    try:
        card_text = _safe_inner_text(card)
        name = _extract_name_from_card(card)

        if not is_valid_pc_place_name(name):
            return None
        if "리뷰" not in card_text:
            return None
        if not is_primary_pc_name_anchor(name, card_text):
            return None

        new_open = detect_new_open_pc(card_text)
        if new_open_only and new_open != "O":
            return None

        category = _safe_text(card, FIELD_SELECTORS["category"])
        name, category = split_pc_name_category(name, category)
        if not is_valid_pc_place_name(name):
            return None

        if not category:
            category = guess_pc_category_from_text(card_text, name)

        address = extract_address_from_pc_text(card_text)
        phone_text = _safe_text(card, FIELD_SELECTORS["phone"])
        phone_href = _safe_attr(card, FIELD_SELECTORS["phone"], "href")
        phone = normalize_phone(phone_text, phone_href)
        review_count = extract_review_count_pc(card_text)

        if name in seen:
            return None
        seen.add(name)

        # Stage 3A 가산 필드: 상세 진입 없이 리스트 anchor href에서 확보.
        href = _extract_place_href(card)
        place_id = _parse_place_id(href)
        place_url = _normalize_pc_place_url(href)

        return {
            "업체명": name,
            "업종": category,
            "새로오픈여부": new_open,
            "리뷰수": review_count,
            "주소": address,
            "대표전화": phone,
            "플레이스 URL": place_url,
            "place_id": place_id,
            "수집일": collected_at,
        }
    except Exception as exc:
        _safe_print(f"[list_scraper] card parse failed: {exc}")
        return None


def _click_next_page(frame, next_page: int) -> bool:
    """다음 페이지 버튼을 4개 후보 셀렉터로 시도합니다.

    셀렉터 후보를 찾지 못하는 경우(count==0)나 존재 확인(is_visible) 실패는
    삼키고 다음 후보로 넘어갑니다. 그러나 실제 클릭(click()) 실패는 삼키지 않고
    그대로 전파합니다 - CAPTCHA/보안 차단으로 클릭이 가로채인 경우가 이 경로의
    예외로 감지되어야 하기 때문입니다(PROJECT_STATE.md 2026-07-01 진단 기록:
    is_visible() 단독 판정은 신뢰할 수 없고, 예외 메시지 기반 판정이 필요함).
    """
    for selector in [
        f'a:text-is("{next_page}")',
        f'button:text-is("{next_page}")',
        f'a:has-text("{next_page}")',
        f'button:has-text("{next_page}")',
    ]:
        try:
            next_button = frame.locator(selector).first
            if next_button.count() == 0 or not next_button.is_visible(timeout=1000):
                continue
        except Exception as exc:
            _safe_print(f"[list_scraper] next page selector check failed: {selector} ({exc})")
            continue
        next_button.click(timeout=3000)
        return True
    return False


def _check_stop(stop_event) -> bool:
    if stop_event is not None and stop_event.is_set():
        print("[list_scraper] stop event detected, aborting pc list scrape")
        return True
    return False


def _wait_while_paused(page, stop_event, pause_event) -> bool:
    """일시정지 상태면 대기하고, 그 사이 stop이 감지되면 True를 반환합니다."""
    if pause_event is None or not pause_event.is_set():
        return False
    print("[list_scraper] pause event detected, blocking...")
    while pause_event.is_set():
        if _check_stop(stop_event):
            return True
        page.wait_for_timeout(500)
    return _check_stop(stop_event)


def scrape_list(
    session,
    frame,
    keyword,
    limit,
    new_open_only,
    stop_event,
    pause_event,
    results,
) -> None:
    """searchIframe 리스트에서 스크롤/페이지네이션을 진행하며 results에 append합니다.

    pc_crawler.py의 is_visible() 기반 CAPTCHA 사전 감지(_is_pc_captcha_detected 반복
    호출)는 이식하지 않습니다. 대신 실제 클릭/조작에서 발생하는 예외를 그대로
    전파시켜 호출자(build_collector)가 safety.classify_exception으로 판정합니다.
    """
    page = session.page
    collected_at = datetime.now().strftime("%Y-%m-%d")
    scan_limit = max(limit * 10, 50) if new_open_only else limit
    calculated_scrolls = max(2, (scan_limit // 10) + 1)
    seen: set = set()
    current_page = 1

    while len(results) < limit and current_page <= _MAX_PAGES:
        if _check_stop(stop_event):
            break
        if _wait_while_paused(page, stop_event, pause_event):
            break

        print(f"[list_scraper] collect page={current_page}")
        cards = _find_pc_cards(frame)
        _light_scroll_cards(
            page, cards, max_scrolls=calculated_scrolls, stop_event=stop_event, pause_event=pause_event
        )
        card_count = cards.count()
        print(f"[list_scraper] candidate cards={card_count}")

        for index in range(card_count):
            if _check_stop(stop_event):
                break
            if len(results) >= limit:
                break
            if _wait_while_paused(page, stop_event, pause_event):
                break

            card = cards.nth(index)
            row = _build_row(card, collected_at, new_open_only, seen)
            if row is not None:
                results.append(row)
                if len(results) % 10 == 0 or len(results) == limit:
                    print(f"[list_scraper] collecting... {len(results)}/{limit}")

        if len(results) >= limit:
            break
        if _check_stop(stop_event):
            break
        if current_page >= _MAX_PAGES:
            break
        if _wait_while_paused(page, stop_event, pause_event):
            break

        next_page = current_page + 1
        if not _click_next_page(frame, next_page):
            print(f"[list_scraper] next page not found: {next_page}")
            break

        page.wait_for_timeout(2000)
        current_page += 1

        if _check_stop(stop_event):
            break
        if _wait_while_paused(page, stop_event, pause_event):
            break

    print(f"[list_scraper] completed {len(results)}/{limit}")


def build_collector(diagnostic_config, *, session_factory=BrowserSession, scrape_fn=scrape_list):
    """pipeline.collect_pc_full이 기대하는 collector 시그니처를 반환하는 팩토리입니다.

    session_factory/scrape_fn은 기본값이 실제 프로덕션 구현(BrowserSession/scrape_list)이며,
    테스트에서 실제 브라우저 launch 없이 이 함수의 예외 처리 계약(classify -> capture ->
    mark -> raise, exc.page 미부착)만 검증할 수 있도록 주입 지점을 열어둔 것입니다.

    실패 시 확정된 진단 캡처 계약을 따릅니다:
    1) safety.classify_exception(exc) 호출
    2) capture_artifacts=True이면 session.capture_diagnostics로 진단 산출물 저장
    3) 예외에 diagnostics_captured=True 마커만 부착
    4) exc.page는 붙이지 않고 그대로 re-raise
    이로써 pipeline.py의 자체 캡처(exc.page가 있을 때만 동작)는 자동으로 no-op이 되어
    중복 캡처가 발생하지 않습니다.
    """

    def _collector(keyword, limit, new_open_only, stop_event, pause_event, results) -> None:
        search_url = f"https://map.naver.com/v5/search/{quote(keyword)}"
        with session_factory(diagnostic_config) as session:
            try:
                session.goto(search_url)
                frame = session.find_search_frame()
                if frame is None:
                    return
                scrape_fn(session, frame, keyword, limit, new_open_only, stop_event, pause_event, results)
            except Exception as exc:
                decision = classify_exception(exc)
                session.capture_diagnostics(label=keyword, exception=exc, safety_decision=decision)
                session.keep_open_if_configured()
                exc.diagnostics_captured = True
                raise

    return _collector
