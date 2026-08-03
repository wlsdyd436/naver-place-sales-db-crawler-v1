# Apollo 목록 페이지의 DOM 탐색과 polling/settle 대기를 담당하는 모듈. 입력은
# Playwright형 page/frame 객체, Observer의 _QueryObservationContext(문자열
# annotation으로만 참조 - runtime import 없음), extractor callback이며,
# 출력은 검색 frame, 페이지 버튼 locator, CAPTCHA 원시 probe 결과, Apollo
# 준비 결과, 다음 페이지 settle 결과다. CAPTCHA selector는 browser.session을,
# 기본 extractor는 apollo_list_adapter를 그대로 재사용한다(재구현 없음). 이
# 모듈은 검색 URL 생성, page.goto, locator.click, listener 등록·해제, stop
# reason 판정, row 변환·필터, BrowserSession 수명 관리를 전혀 수행하지
# 않는다 - 그 책임은 전부 apollo_list_collector.py에 남는다.
from __future__ import annotations

from typing import TYPE_CHECKING

from src.browser.session import _CAPTCHA_PROBE_SELECTORS
from src.collection.apollo_list_adapter import extract_main_place_list_from_apollo

if TYPE_CHECKING:
    from src.collection.apollo_response_observer import _QueryObservationContext

# ARCH-300C PERF-1A: 적응형 settle 종료 상수(모듈 상수로만 고정 - 함수
# 시그니처나 UI에는 노출하지 않는다). settle_ms(기존
# 파라미터, 기본 5000)는 "무조건 기다리는 시간"에서 "최대 대기 hard cap"으로
# 의미가 바뀌었고, 파싱 가능한(비어있지 않은) 업체 목록 응답을 확인한 뒤
# _QUIET_PERIOD_MS 동안 추가 후보가 도착하지 않으면 hard cap 전에 조기
# 종료한다. 750/100이라는 구체적인 값은 WIRE-4C(실제 네이버, 300건 규모)
# 관찰에서 얻은 잠정치이며, candidate 응답들 사이의 실제 도착 간격(inter-arrival
# gap)을 직접 계측한 적은 아직 없다 - 다음 live 검증 단계(WIRE-5 등)에서
# 이 값의 적정성을 실측으로 재확인해야 한다(반대 검토 AI 지적 사항).
_QUIET_PERIOD_MS = 750
_POLL_INTERVAL_MS = 100

# 2026-08 실측: 실제 CAPTCHA 발생 시 #wtm-captcha-root 자체는 height=0/
# visible=False(정적 placeholder)였지만, 그 내부의 실제 challenge dialog
# ([role="dialog"][aria-modal="true"])는 visible=True였다 - root 자체의
# visible/bbox만 보던 기존 계산으로는 이 케이스를 active로 못 잡았다. root
# subtree 안쪽만 한정해서 함께 확인한다(페이지 전역 dialog는 대상이 아님 -
# selector 문자열 자체가 root 접두어를 포함해야만 조회된다).
_CAPTCHA_CHILD_DIALOG_SUFFIXES = ('[role="dialog"][aria-modal="true"]',)
_CAPTCHA_PROBE_SELECTORS_WITH_CHILDREN = list(_CAPTCHA_PROBE_SELECTORS) + [
    f"{root} {suffix}" for root in _CAPTCHA_PROBE_SELECTORS for suffix in _CAPTCHA_CHILD_DIALOG_SUFFIXES
]


def _probe_captcha_state(page) -> dict:
    """PoC-7 _probe_captcha_presence와 동일한 방식으로 CAPTCHA DOM 상태를 관찰한다.

    marker가 DOM에 존재한다는 사실만으로 active로 단정하지 않는다(오탐 방지 -
    classify_captcha_signal이 visible+면적까지 함께 봐야 active로 판정한다).
    클릭을 전혀 하지 않으므로 click_intercepted_message는 항상 빈 문자열이다.

    2026-07-31 frame-aware 보강: main frame 외에 page.frames의 child frame을
    순회해 #wtm-captcha-root가 iframe 안에 있어도 탐지한다. 첫 hidden match에서
    종료하지 않고 전체를 집계해 visible 신호를 우선 채택한다.
    """
    marker_present = False
    visible = False
    area = 0.0

    # 탐색 대상: main frame(page 자체) + 접근 가능한 모든 child frame.
    # page.frames가 예외를 던지거나 비어있어도 main frame 결과는 유지한다.
    frames_to_scan = [page]
    try:
        child_frames = list(page.frames)
        frames_to_scan.extend(child_frames)
    except Exception:
        pass  # child frame 접근 실패 시 main frame만 탐색

    for target in frames_to_scan:
        for selector in _CAPTCHA_PROBE_SELECTORS_WITH_CHILDREN:
            try:
                locator = target.locator(selector).first
                if locator.count() == 0:
                    continue
                marker_present = True
                try:
                    if locator.is_visible(timeout=300):
                        try:
                            box = locator.bounding_box()
                            if box:
                                candidate_area = float(box.get("width", 0)) * float(box.get("height", 0))
                                if candidate_area > 0:
                                    visible = True
                                    area = max(area, candidate_area)
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception:
                continue

    return {
        "marker_present": marker_present,
        "visible": visible,
        "bounding_box_area": area,
        "click_intercepted_message": "",
    }


def _find_visible_captcha_dialog_locator(page):
    """진단 element screenshot 전용 helper(요청서 §6 옵션 A) - _probe_captcha_state와
    동일한 selector 목록(_CAPTCHA_PROBE_SELECTORS_WITH_CHILDREN)과 frame 순회
    순서를 그대로 재사용해(재구현 없음, detection과 screenshot이 서로 다른
    selector를 쓰지 않도록 보장) 실제로 visible+양수 bbox인 첫 Locator를
    반환한다. _probe_captcha_state의 bool 전용 반환 계약은 이 함수와 무관하게
    그대로 유지된다. 찾지 못하거나 조회 중 예외가 나면 None을 반환한다(예외
    전파 없음) - 호출자(diagnostics 저장)가 None이면 PNG 없이 JSON만 저장한다."""
    frames_to_scan = [page]
    try:
        frames_to_scan.extend(list(page.frames))
    except Exception:
        pass

    for target in frames_to_scan:
        for selector in _CAPTCHA_PROBE_SELECTORS_WITH_CHILDREN:
            try:
                locator = target.locator(selector).first
                if locator.count() == 0:
                    continue
                if not locator.is_visible(timeout=300):
                    continue
                box = locator.bounding_box()
                if box and float(box.get("width", 0)) * float(box.get("height", 0)) > 0:
                    return locator
            except Exception:
                continue
    return None


def _find_search_frame(page):
    """PAGE-300-2B-1: src/browser/session.py의 BrowserSession.find_search_frame
    과 동일한 폴백 순서(name -> frame_locator+body wait -> frames 스캔)를
    이 모듈 전용으로 재구현한다 - 이 함수는 BrowserSession
    인스턴스가 아니라 bare page만 받으므로 그 메서드를 직접 호출할 수 없다
    (src/browser/session.py는 이번 단계 수정 금지 범위).

    이 함수는 어떤 예외도 밖으로 내보내지 않는다 - frame API를 전혀 구현하지
    않은 기존 FakePage(단일 페이지 no-live 테스트 전용)에서도 안전하게 None을
    반환해야, per_query_limit이 첫 페이지 결과보다 큰 기존 테스트들이 실수로
    pagination을 "시도"하더라도 예외 없이 즉시 pagination_exhausted로 안전
    종료되어 기존 단일 페이지 반환값이 전혀 달라지지 않는다.
    """
    try:
        frame = page.frame(name="searchIframe")
        if frame:
            return frame
    except Exception:
        pass
    try:
        frame_locator = page.frame_locator("#searchIframe")
        frame_locator.locator("body").first.wait_for(timeout=5000)
        frame = page.frame(name="searchIframe")
        if frame:
            return frame
    except Exception:
        pass
    try:
        for frame in page.frames:
            frame_id = f"{frame.name} {frame.url}".lower()
            if "search" in frame_id:
                return frame
    except Exception:
        pass
    return None


def _find_page_button(frame, target_page_number: int):
    """PAGE-300-2B-1 §9: role="button"이며 텍스트가 목표 페이지 번호와 정확히
    일치하는 요소만 찾는다. has_text(부분 문자열 포함) 방식은 "2"를 찾을 때
    "12"·"20" 같은 다른 페이지 번호나 업체 본문의 숫자와 오매칭될 수 있어
    사용하지 않는다 - exact=True로 정확한 문자열 일치만 허용한다. 여러 개가
    일치하면(ambiguous) 호출자가 count()로 판단해 클릭하지 않는다(이 함수는
    locator만 반환하고 클릭 여부는 판단하지 않음).
    """
    try:
        return frame.get_by_role("button", name=str(target_page_number), exact=True)
    except Exception:
        return None


def _wait_for_next_page_settle(page, ctx: _QueryObservationContext, ensure_parsed, count_before_click: int, hard_cap_ms: int) -> dict:
    """PAGE-300-2B-1 §12: 페이지 번호 클릭 직후 신규 candidate response가
    도착할 때까지 기다리고, 첫 신규 응답이 확인되면 기존 adaptive
    quiet-period 원칙(_QUIET_PERIOD_MS)으로 이 페이지의 candidate response
    수집이 안정화될 때까지 추가로 기다린다(최초 settle 폴링 루프와 동일한
    로직을 count_before_click부터 시작하도록 일반화한 것).

    hard_cap_ms 안에 신규 candidate response가 전혀 도착하지 않으면
    got_new_response=False를 반환한다(next_page_response_timeout 판정은
    호출자의 책임 - 이 함수는 판정하지 않고 사실만 보고한다).
    """
    elapsed_ms = 0
    got_new_response = False
    valid_confirmed = False
    quiet_elapsed_ms = 0
    last_seen_count = count_before_click

    while elapsed_ms < hard_cap_ms:
        page.wait_for_timeout(_POLL_INTERVAL_MS)
        elapsed_ms += _POLL_INTERVAL_MS

        current_count = ctx.candidate_response_count
        if current_count > last_seen_count:
            got_new_response = True
            found_valid_this_tick = False
            for index in range(last_seen_count, current_count):
                parsed = ensure_parsed(index)
                if not parsed["error"] and parsed["items"]:
                    found_valid_this_tick = True
            last_seen_count = current_count
            quiet_elapsed_ms = 0
            if found_valid_this_tick:
                valid_confirmed = True
        elif valid_confirmed:
            quiet_elapsed_ms += _POLL_INTERVAL_MS
            if quiet_elapsed_ms >= _QUIET_PERIOD_MS:
                break

    return {
        "got_new_response": got_new_response,
        "final_count": last_seen_count,
        "elapsed_ms": elapsed_ms,
    }


_APOLLO_FULL_STATE_JS = """() => {
    const state = window.__APOLLO_STATE__;
    if (!state || typeof state !== 'object') return {available: false, apollo_state: null, oversized: false};
    try {
        if (JSON.stringify(state).length > 5000000) {
            return {available: true, apollo_state: null, oversized: true};
        }
    } catch (e) {
        return {available: false, apollo_state: null, oversized: false};
    }
    return {available: true, apollo_state: state, oversized: false};
}"""


def _wait_for_apollo_list_ready(
    page, frame, expected_query: str, expected_start: int, hard_cap_ms: int = 5000,
    *, extractor=extract_main_place_list_from_apollo,
) -> dict:
    """1페이지 window.__APOLLO_STATE__에 메인 placeList(...) operation이 확인될
    때까지 폴링한다. 매 tick마다 전체 apollo state를 다시 읽어
    extractor(기본값 extract_main_place_list_from_apollo)로 판정하고,
    error가 없어지면 즉시 반환한다(추가 대기 없음). hard_cap_ms 안에 끝내
    확인되지 않으면 마지막 관찰된 list_result를 그대로 반환한다(호출자가
    error 필드로 판단 - 이 함수 자체는 성공/실패를 판정하지 않는다).

    NEW-OPENING-1: extractor=extract_new_opening_place_list_from_apollo를
    넘기면 새로오픈 전용 placeList(filterOpening=true) operation을 기다린다
    - 폴링 로직 자체는 어떤 operation을 찾는지와 무관하게 동일하다."""
    elapsed_ms = 0
    while True:
        try:
            state_result = frame.evaluate(_APOLLO_FULL_STATE_JS)
        except Exception:
            state_result = None
        apollo_state = state_result.get("apollo_state") if isinstance(state_result, dict) else None
        list_result = extractor(apollo_state, expected_query, expected_start)
        if not list_result["error"]:
            return list_result
        if elapsed_ms >= hard_cap_ms:
            return list_result
        page.wait_for_timeout(_POLL_INTERVAL_MS)
        elapsed_ms += _POLL_INTERVAL_MS
