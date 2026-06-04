# V1 crawler placeholder. Implementation is intentionally excluded in STEP 1.

import re
from datetime import datetime
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


# 2026-06-04: 모바일 웹 리스트 화면 기준 selector 후보입니다.
SELECTORS = {
    "cards": [
        "li",
        "div[role='listitem']",
        "div:has(a[href*='/place/'])",
        "div:has(a[href*='place.naver.com'])",
        "a[href*='/place/']",
    ],
    "name": [
        "[class*='place_bluelink']",
        "[class*='TYaxT']",
        "[class*='Fc1rA']",
        "strong",
        "span[role='text']",
    ],
    "category": [
        # 2026-06-04: 업종은 업체명 옆 em 태그에서만 보수적으로 추출합니다.
        "em[class*='_item_category']",
        "em[class*='item_category']",
        "strong + em",
    ],
    "address": [
        "[class*='LDgIH']",
        "[class*='place_addr']",
        "[class*='addr']",
        "span:has-text('동')",
        "span:has-text('로')",
        "span:has-text('길')",
    ],
    "phone": [
        "a[href^='tel:']",
        "[class*='phone']",
        "span:has-text('02-')",
        "span:has-text('031-')",
        "span:has-text('032-')",
        "span:has-text('042-')",
        "span:has-text('051-')",
        "span:has-text('053-')",
        "span:has-text('070-')",
        "span:has-text('010-')",
    ],
    "url": [
        "a[href*='/place/']",
        "a[href*='place.naver.com']",
        "a[href]",
    ],
}


def safe_text(card, selector_candidates) -> str:
    """2026-06-04: selector 실패 시 빈 문자열을 반환합니다."""
    for selector in selector_candidates:
        try:
            element = card.locator(selector).first
            if element.count() == 0:
                continue
            text = element.inner_text(timeout=1000).strip()
            if text:
                return " ".join(text.split())
        except Exception:
            continue
    return ""


def safe_attr(card, selector_candidates, attr: str) -> str:
    """2026-06-04: attribute 추출 실패 시 빈 문자열을 반환합니다."""
    for selector in selector_candidates:
        try:
            element = card.locator(selector).first
            if element.count() == 0:
                continue
            value = element.get_attribute(attr, timeout=1000)
            if value:
                return value.strip()
        except Exception:
            continue
    return ""


def _find_cards(page):
    # 2026-06-04: 모바일 DOM 변경에 대비한 카드 후보 fallback입니다.
    for selector in SELECTORS["cards"]:
        try:
            cards = page.locator(selector)
            count = cards.count()
            if count > 0:
                print(f"[crawler] card selector matched: {selector} ({count})")
                return cards
        except Exception as exc:
            print(f"[crawler] card selector failed: {selector} ({exc})")
            continue
    return page.locator("body > *")


def _normalize_place_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return f"https://m.map.naver.com{url}"
    return url


def _normalize_phone(phone_text: str, phone_href: str) -> str:
    if phone_href.startswith("tel:"):
        return phone_href.replace("tel:", "").strip()
    return phone_text.strip()


def _detect_new_open_badge(card) -> str:
    """2026-06-04: 리스트 카드에 표시된 '새로오픈' 텍스트만 기준으로 판단합니다."""
    try:
        text = card.inner_text(timeout=1000)
    except Exception:
        return ""
    return "O" if "새로오픈" in text else ""


def _extract_review_count(card) -> str:
    """2026-06-04: 리스트 카드에 노출된 리뷰 관련 텍스트만 보수적으로 추출합니다."""
    try:
        text = " ".join(card.inner_text(timeout=1000).split())
    except Exception:
        return ""

    patterns = [
        r"방문자리뷰\s*([\d,]+)",
        r"블로그리뷰\s*([\d,]+)",
        r"리뷰\s*([\d,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def crawl_places(
    keyword: str, limit: int = 10, new_open_only: bool = False
) -> list[dict]:
    """2026-06-04: m.map.naver.com 리스트 화면에서 장소 후보를 최소 수집합니다."""
    results = []
    collected_at = datetime.now().strftime("%Y-%m-%d")
    search_url = f"https://m.map.naver.com/search.naver?query={quote_plus(keyword)}"

    print(f"[crawler] start keyword={keyword}, limit={limit}")
    print(f"[crawler] new_open_only={new_open_only}")
    print(f"[crawler] url={search_url}")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
            )
            page = context.new_page()

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
            except PlaywrightTimeoutError:
                print("[crawler] page load timeout, continue with current DOM")

            cards = _find_cards(page)
            # 2026-06-04: 새로오픈 필터 ON이면 limit 도달을 위해 더 많은 카드 후보를 확인합니다.
            scan_limit = max(limit * 10, 50) if new_open_only else max(limit * 3, limit)
            card_count = min(cards.count(), scan_limit)
            print(f"[crawler] candidate cards={card_count}")
            if new_open_only:
                print(f"[crawler] scan cards={scan_limit}")

            seen = set()
            for index in range(card_count):
                if len(results) >= limit:
                    break

                try:
                    card = cards.nth(index)
                    name = safe_text(card, SELECTORS["name"])
                    category = safe_text(card, SELECTORS["category"])
                    address = safe_text(card, SELECTORS["address"])
                    phone_text = safe_text(card, SELECTORS["phone"])
                    phone_href = safe_attr(card, SELECTORS["phone"], "href")
                    place_url = _normalize_place_url(
                        safe_attr(card, SELECTORS["url"], "href")
                    )
                    phone = _normalize_phone(phone_text, phone_href)
                    new_open = _detect_new_open_badge(card)
                    review_count = _extract_review_count(card)
                    # 2026-06-04: 업종은 명확한 selector 결과만 사용하고 추론하지 않습니다.

                    if not name:
                        continue

                    if new_open_only and new_open != "O":
                        continue

                    dedupe_key = (name, address, phone)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)

                    results.append(
                        {
                            "업체명": name,
                            "새로오픈여부": new_open,
                            "업종": category,
                            "리뷰수": review_count,
                            "주소": address,
                            "대표전화": phone,
                            "플레이스 URL": place_url,
                            "수집일": collected_at,
                        }
                    )
                    print(f"[crawler] collected {len(results)}: {name}")
                    if new_open_only:
                        print(
                            f"[crawler] new open collected {len(results)}/{limit}"
                        )
                except Exception as exc:
                    print(f"[crawler] card parse failed index={index}: {exc}")
                    continue

            context.close()
            browser.close()
    except Exception as exc:
        print(f"[crawler] failed safely: {exc}")
        return []

    print(f"[crawler] done count={len(results)}")
    return results
