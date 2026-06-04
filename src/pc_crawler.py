import re
from datetime import datetime
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


# 2026-06-04: PC Premium Mode 디버그용 카드 텍스트 출력 여부입니다.
DEBUG_CARD_TEXT = False


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

EXCLUDED_NAME_KEYWORDS = [
    "주간 인기 많은 메뉴",
    "connect+ 혜택",
    "더보기",
    "저장",
    "광고",
    "리뷰",
    "혜택",
    "새로오픈",
    "신규오픈",
    "방문자리뷰",
    "블로그리뷰",
]


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
            print(f"[pc_crawler] anchor selector failed: {selector} ({exc})")
            continue
    return frame.locator("a")


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


def _light_scroll_cards(anchors, scroll_count: int = 2) -> None:
    """2026-06-04: 마지막 li 요소 기준으로 가볍게 추가 로딩만 시도합니다."""
    for index in range(scroll_count):
        try:
            last_li = anchors.locator("xpath=ancestor::li[1]").last
            if last_li.count() > 0:
                last_li.scroll_into_view_if_needed(timeout=2000)
            else:
                anchors.last.scroll_into_view_if_needed(timeout=2000)
            print(f"[pc_crawler] light scroll {index + 1}/{scroll_count}")
        except Exception as exc:
            print(f"[pc_crawler] scroll skipped {index + 1}")
            break


def _normalize_phone(phone_text: str, phone_href: str) -> str:
    if phone_href.startswith("tel:"):
        return phone_href.replace("tel:", "").strip()
    return phone_text.strip()


def _detect_new_open(text: str) -> str:
    return "O" if "새로오픈" in text or "신규오픈" in text else ""


def _extract_review_count(text: str) -> str:
    """2026-06-04: 방문자리뷰/블로그리뷰/리뷰 숫자를 쉼표 포함 정규식으로 추출합니다."""
    normalized = " ".join(text.split())
    patterns = [
        r"리뷰\s*([0-9,]+)",
        r"방문자리뷰\s*([0-9,]+)",
        r"블로그리뷰\s*([0-9,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return re.sub(r"\D", "", match.group(1))
    return ""


def _extract_address_from_text(text: str) -> str:
    """2026-06-04: 카드 텍스트에서 명확한 행정구역 형태만 주소 후보로 사용합니다."""
    address_pattern = re.compile(
        r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
        r"\s+[가-힣]+(?:시|군|구)\s+[가-힣0-9]+(?:동|읍|면)"
    )

    for line in text.splitlines():
        candidate = " ".join(line.split())
        if not candidate:
            continue
        match = address_pattern.search(candidate)
        if match:
            return match.group(0)
    return ""


def _is_valid_place_name(name: str) -> bool:
    """2026-06-04: 메뉴/혜택/리뷰 등 업체명이 아닌 텍스트를 제외합니다."""
    if not name:
        return False
    if name == "#":
        return False
    if any(keyword in name for keyword in EXCLUDED_NAME_KEYWORDS):
        return False
    if "*" in name:
        return False
    if len(name) > 40:
        return False
    return True


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


def _split_name_category(name: str, category: str) -> tuple[str, str]:
    """2026-06-04: 업체명 뒤에 붙은 짧은 업종 텍스트를 분리합니다."""
    category_suffixes = [
        "카페,디저트",
    ]
    if category:
        return name, category
    for suffix in category_suffixes:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)].strip(), suffix
    return name, category


def _is_primary_name_anchor(name: str, card_text: str) -> bool:
    """2026-06-04: 카드 상단 3줄 안에 업체명이 포함되면 정상 카드로 봅니다."""
    lines = [" ".join(line.split()) for line in card_text.splitlines() if line.strip()]
    for line in lines[:3]:
        if name in line:
            return True
    return False


def _guess_category_from_text(text: str, name: str) -> str:
    """2026-06-04: 업체명 주변 짧은 텍스트에서만 업종 후보를 보수적으로 추정합니다."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    for line in lines[:5]:
        if name and line.startswith(name):
            candidate = line.replace(name, "", 1).strip()
            if 0 < len(candidate) <= 20 and not re.search(
                r"\d|리뷰|저장|공유|광고", candidate
            ):
                return candidate
    for index, line in enumerate(lines[:6]):
        if line == name and index + 1 < len(lines):
            candidate = lines[index + 1]
            if 0 < len(candidate) <= 20 and not re.search(
                r"\d|리뷰|저장|공유|광고", candidate
            ):
                return candidate
    return ""


def crawl_places_pc(
    keyword: str, limit: int = 10, new_open_only: bool = False
) -> list[dict]:
    """2026-06-04: PC searchIframe 리스트에서 새로오픈 업체 발굴용 정보를 수집합니다."""
    results = []
    collected_at = datetime.now().strftime("%Y-%m-%d")
    search_url = f"https://map.naver.com/v5/search/{quote(keyword)}"

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

            anchors = _find_place_anchors(search_frame)
            _light_scroll_cards(anchors, scroll_count=10)
            anchor_count = anchors.count()
            print(f"[pc_crawler] candidate anchors={anchor_count}")

            seen = set()
            debug_count = 0
            for index in range(anchor_count):
                if len(results) >= limit:
                    break

                try:
                    anchor = anchors.nth(index)
                    card = _get_card_from_anchor(anchor)
                    card_text = _safe_inner_text(card)
                    name = _extract_name_from_anchor(anchor)

                    if not _is_valid_place_name(name):
                        continue
                    if "리뷰" not in card_text:
                        continue
                    if not _is_primary_name_anchor(name, card_text):
                        continue

                    new_open = _detect_new_open(card_text)
                    if new_open_only and new_open != "O":
                        continue

                    if DEBUG_CARD_TEXT and debug_count < 3:
                        print(f"[pc_crawler] card {debug_count} text:")
                        print(card_text[:500])
                        debug_count += 1

                    category = _safe_text(card, FIELD_SELECTORS["category"])
                    name, category = _split_name_category(name, category)
                    if not _is_valid_place_name(name):
                        continue

                    if not category:
                        category = _guess_category_from_text(card_text, name)

                    address = _extract_address_from_text(card_text)
                    phone_text = _safe_text(card, FIELD_SELECTORS["phone"])
                    phone_href = _safe_attr(card, FIELD_SELECTORS["phone"], "href")
                    phone = _normalize_phone(phone_text, phone_href)
                    review_count = _extract_review_count(card_text)

                    if name in seen:
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
                    print(f"[pc_crawler] collected {len(results)}: {name}")
                except Exception as exc:
                    print(f"[pc_crawler] card parse failed index={index}: {exc}")
                    continue

            context.close()
            browser.close()
    except Exception as exc:
        print(f"[pc_crawler] failed safely: {exc}")
        return []

    print(f"[pc_crawler] done count={len(results)}")
    return results


if __name__ == "__main__":
    results = crawl_places_pc("대전 신상 카페", 10)
    print(results)
