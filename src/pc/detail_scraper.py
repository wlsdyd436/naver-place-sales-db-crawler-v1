# 정식 출시 전 PC 단일 엔진 전환 - Stage 3A (entryIframe 상세 수집) 신규 모듈.
# 리스트 수집(list_scraper.py) 결과 행을 받아, 각 업체의 entryIframe 상세 패널로
# 진입해 대표전화/전체주소를 보강(enrich)합니다. 진입 모델은 "클릭 in-place"만
# 사용하며(URL 재진입은 fallback 후보로만 문서화, 미구현), 플레이스 URL은 리스트
# 단계에서 이미 확보되므로 여기서는 대표전화/전체주소만 대상으로 합니다.
#
# 실패 정책:
#   - 단건 상세 실패(anchor 미발견/entry 미갱신/클릭 예외)는 1회 retry 후 skip(공란
#     유지)하고 세션을 계속합니다. 단건 실패는 진단 캡처를 하지 않습니다.
#   - 연속 실패가 임계(_CONSECUTIVE_FAILURE_LIMIT)를 넘으면 단건 문제가 아니라
#     차단/구조 신호로 보고 DetailCollectionAborted를 발생시킵니다. 이 예외는
#     build_full_collector의 except에서 classify_exception -> session.capture_diagnostics
#     -> diagnostics_captured=True 마커 -> exc.page 미부착 -> raise 로 처리됩니다
#     (Stage 2 build_collector와 동일 계약, pipeline은 exc.page가 없어 자동 no-op).
#
# 잔상 방지: 클릭 후 entryIframe의 place id가 "직전 상세와 다른 대상 id"로 바뀔
# 때까지 bounded 폴링합니다. 갱신되지 않으면 이전 상세 잔상을 수집하지 않고 skip.
import re
from urllib.parse import quote

from src.parser import normalize_phone
from src.pc.browser_session import BrowserSession
from src.pc.list_scraper import (
    _check_stop,
    _safe_attr,
    _safe_text,
    _wait_while_paused,
    scrape_list,
)
from src.pc.safety import classify_exception


_ENTRY_WAIT_TIMEOUT_MS = 8000
_ENTRY_POLL_STEP_MS = 300
_CONSECUTIVE_FAILURE_LIMIT = 5
_DETAIL_RETRY = 1

# entryIframe 상세의 대표전화/전체주소 후보 selector입니다. 실 selector는 Stage 3A
# 통제 live probe 1회에서 보정합니다(현재는 후보 + fallback 방식으로만 착수).
ENTRY_PHONE_SELECTORS = [
    "a[href^='tel:']",
    "span[class*='phone']",
    "span:has-text('02-')",
    "span:has-text('031-')",
    "span:has-text('0507-')",
    "span:has-text('070-')",
]

ENTRY_ADDRESS_SELECTORS = [
    "span[class*='LDgIH']",
    "span[class*='address']",
    "span[class*='addr']",
    "div[class*='address'] span",
    "span:has-text('로')",
    "span:has-text('길')",
]


class DetailCollectionAborted(Exception):
    """연속 상세 실패가 임계를 넘어 세션 단위 안전 종료가 필요할 때 발생합니다."""


def _parse_place_id_from_url(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/(\d{5,})", url)
    return match.group(1) if match else ""


def _click_place_anchor(search_frame, place_id: str) -> bool:
    """searchIframe에서 place_id에 해당하는 업체 anchor를 클릭합니다.

    anchor를 찾지 못하면 False를 반환합니다. 클릭 자체가 실패(예: CAPTCHA/보안 차단이
    포인터 이벤트를 가로챔)하면 예외를 삼키지 않고 그대로 전파해, 호출자(_attempt_detail)가
    단건 실패로 집계하도록 합니다.
    """
    for selector in (f'a[href*="/{place_id}"]', f'a[href*="{place_id}"]'):
        anchor = search_frame.locator(selector).first
        try:
            present = anchor.count() > 0
        except Exception:
            present = False
        if not present:
            continue
        anchor.click(timeout=3000)
        return True
    return False


def _wait_entry_loaded(session, target_place_id: str, previous_place_id, timeout_ms: int):
    """entryIframe이 target_place_id로 갱신될 때까지 bounded 폴링합니다.

    직전 상세(previous_place_id)와 동일한 place id면 아직 잔상으로 보고 계속 대기하며,
    timeout까지 갱신되지 않으면 None을 반환합니다(호출자가 skip 처리).
    """
    waited = 0
    while waited < timeout_ms:
        frame = session.find_entry_frame()
        if frame is not None:
            current_id = _parse_place_id_from_url(getattr(frame, "url", "") or "")
            if current_id and current_id == target_place_id:
                if previous_place_id is None or current_id != previous_place_id:
                    return frame
        session.page.wait_for_timeout(_ENTRY_POLL_STEP_MS)
        waited += _ENTRY_POLL_STEP_MS
    return None


def _extract_phone(entry_frame) -> str:
    phone_text = _safe_text(entry_frame, ENTRY_PHONE_SELECTORS)
    phone_href = _safe_attr(entry_frame, ENTRY_PHONE_SELECTORS, "href")
    return normalize_phone(phone_text, phone_href)


def _extract_full_address(entry_frame) -> str:
    return _safe_text(entry_frame, ENTRY_ADDRESS_SELECTORS)


def _attempt_detail(session, search_frame, row, previous_place_id):
    """단건 상세 진입/추출을 1회 시도합니다. ("ok"|"fail", error_message)를 반환합니다.

    성공 시 row의 대표전화/주소를 in-place로 갱신합니다(값이 있을 때만 덮어씀 -
    상세 주소가 비면 리스트 주소를 유지하고 다운그레이드하지 않음).
    """
    place_id = str(row.get("place_id") or "")
    try:
        if not _click_place_anchor(search_frame, place_id):
            return "fail", "anchor not found"
        entry_frame = _wait_entry_loaded(
            session, place_id, previous_place_id, _ENTRY_WAIT_TIMEOUT_MS
        )
        if entry_frame is None:
            return "fail", "entry frame not loaded (stale or slow)"
        phone = _extract_phone(entry_frame)
        address = _extract_full_address(entry_frame)
        if phone:
            row["대표전화"] = phone
        if address:
            row["주소"] = address
        return "ok", ""
    except Exception as exc:
        return "fail", f"{type(exc).__name__}: {exc}"


def enrich_with_details(
    session,
    search_frame,
    rows,
    stop_event=None,
    pause_event=None,
    *,
    consecutive_limit: int = _CONSECUTIVE_FAILURE_LIMIT,
    retry: int = _DETAIL_RETRY,
) -> None:
    """rows(list_scraper 결과)를 place_id 기준으로 상세 진입해 대표전화/전체주소를 보강합니다.

    행은 in-place로 갱신되므로 행 손실이 없고, 상세 실패 행은 공란을 유지합니다.
    place_id가 없는 행은 상세 진입 불가 대상으로 skip(실패로 집계하지 않음)합니다.
    연속 실패가 consecutive_limit을 넘으면 DetailCollectionAborted를 raise 합니다.
    """
    previous_place_id = None
    consecutive_failures = 0
    last_error = ""

    for row in rows:
        if _check_stop(stop_event):
            break
        if _wait_while_paused(session.page, stop_event, pause_event):
            break

        place_id = str(row.get("place_id") or "")
        if not place_id:
            continue

        outcome, error = _attempt_detail(session, search_frame, row, previous_place_id)
        attempts_left = retry
        while outcome == "fail" and attempts_left > 0:
            attempts_left -= 1
            outcome, error = _attempt_detail(session, search_frame, row, previous_place_id)

        if outcome == "ok":
            consecutive_failures = 0
            previous_place_id = place_id
            continue

        consecutive_failures += 1
        last_error = error
        if consecutive_failures >= consecutive_limit:
            raise DetailCollectionAborted(
                f"연속 {consecutive_failures}건 상세 진입 실패로 세션 안전 종료: {last_error}"
            )

    print(f"[detail_scraper] detail enrich done, rows={len(rows)}")


def build_full_collector(
    diagnostic_config,
    *,
    session_factory=BrowserSession,
    list_scrape_fn=scrape_list,
    detail_enrich_fn=enrich_with_details,
):
    """pipeline.collect_pc_full이 기대하는 collector를 반환하는 full(list + detail) 팩토리입니다.

    list_scraper.build_collector()(list-only)와 별개 함수이며, 그 의미를 변경하지
    않습니다. 이 collector는 list 단계로 행+place_id를 수집한 뒤 detail 단계로
    대표전화/전체주소를 보강해 results에 최종 행을 남깁니다.

    실패 시 Stage 2 build_collector와 동일한 진단 캡처 계약을 따릅니다:
    classify_exception -> session.capture_diagnostics -> diagnostics_captured=True 마커
    -> exc.page는 붙이지 않고 raise. list 단계에서 이미 results에 쌓인 행은 부분
    보존되어 pipeline이 반환합니다.
    """

    def _collector(keyword, limit, new_open_only, stop_event, pause_event, results) -> None:
        search_url = f"https://map.naver.com/v5/search/{quote(keyword)}"
        with session_factory(diagnostic_config) as session:
            try:
                session.goto(search_url)
                search_frame = session.find_search_frame()
                if search_frame is None:
                    return
                list_scrape_fn(
                    session, search_frame, keyword, limit, new_open_only, stop_event, pause_event, results
                )
                detail_enrich_fn(session, search_frame, results, stop_event, pause_event)
            except Exception as exc:
                decision = classify_exception(exc)
                session.capture_diagnostics(label=keyword, exception=exc, safety_decision=decision)
                session.keep_open_if_configured()
                exc.diagnostics_captured = True
                raise

    return _collector
