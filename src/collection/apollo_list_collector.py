# Apollo/GraphQL 목록 Network 응답을 관찰해 Place row를 수집하는 Collector
# 모듈(ApolloFirstListCollector/collect_apollo_first_list_query, 파일
# 하단)과 그 인프라(candidate 안전 진단, CAPTCHA probe, 페이지네이션 대기)를
# 담는다. BrowserSession(Native Edge CDP 세션)은 src/browser가 제공하고,
# candidate response/request 생명주기 관찰(_QueryObservationContext,
# response/requestfinished/requestfailed 핸들러)은 src/collection.
# apollo_response_observer를, Apollo 목록 선택(extract_main_place_list_from_apollo
# 등)·Place row 매핑·중복 제거는 src/collection의 apollo_list_adapter/
# place_mapper를, 지역 Exact·새로오픈·리뷰 범위 row 채택 판정은
# src/collection.row_filters를, 일시정지·중지 게이트는 src/run_control을
# 그대로 재사용한다(재구현 없음).
#
# page.goto()에서 발생 가능한 예외는 성격이 다르다. 실제 Playwright
# TimeoutError(느린 로드)만 timeout=True로 분류하고, "page/context/browser가
# 이미 닫힘(Target closed)"·"브라우저 실행 장애"·"일반 navigation 오류" 등
# 그 외 예외는 timeout으로 위장하지 않고 navigation_error로 별도 분류한다
# (browser_session.goto와 동일하게 PlaywrightTimeoutError만 관용적으로 흡수).
import json
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.collection.apollo_list_adapter import (
    build_rows_from_apollo_list_result,
    extract_main_place_list_from_apollo,
    extract_new_opening_place_list_from_apollo,
)
from src.browser.session import _CAPTCHA_PROBE_SELECTORS
from src.collection.apollo_response_observer import (
    _QueryObservationContext,
    _make_request_failed_handler,
    _make_request_finished_handler,
    _make_response_handler,
)
from src.collection.place_mapper import (
    _extract_list_items,
    _map_item_to_row,
    classify_captcha_signal,
    dedup_rows,
)
from src.collection.row_filters import (
    _merge_review_filter_stats,
    _review_filter_stats,
    _split_new_opening_valid_rows,
    _split_region_valid_rows,
    _split_review_valid_rows,
)
from src.run_control import wait_while_paused

_SEARCH_URL_TEMPLATE = "https://map.naver.com/v5/search/{query}"

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


def _probe_captcha_state(page) -> dict:
    """PoC-7 _probe_captcha_presence와 동일한 방식으로 CAPTCHA DOM 상태를 관찰한다.

    marker가 DOM에 존재한다는 사실만으로 active로 단정하지 않는다(오탐 방지 -
    classify_captcha_signal이 visible+면적까지 함께 봐야 active로 판정한다).
    클릭을 전혀 하지 않으므로 click_intercepted_message는 항상 빈 문자열이다.
    """
    marker_present = False
    visible = False
    area = 0.0
    for selector in _CAPTCHA_PROBE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            marker_present = True
            if locator.is_visible(timeout=300):
                visible = True
                box = locator.bounding_box()
                if box:
                    area = max(area, float(box.get("width", 0)) * float(box.get("height", 0)))
        except Exception:
            continue
    return {
        "marker_present": marker_present,
        "visible": visible,
        "bounding_box_area": area,
        "click_intercepted_message": "",
    }


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


def _wait_for_next_page_settle(page, ctx: "_QueryObservationContext", ensure_parsed, count_before_click: int, hard_cap_ms: int) -> dict:
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


def _default_session_factory():
    """실제 제품 배선용 기본 factory - 이 함수가 호출되어 반환된 객체의
    __enter__가 실제로 호출될 때만 Playwright/브라우저가 시작된다(이 함수를
    정의/참조하는 것만으로는 아무것도 시작하지 않는다). 테스트는 항상
    session_factory를 fake로 주입하므로 이 함수는 테스트에서 호출되지 않는다.

    BrowserBackendConfig.from_env().backend에 따라 NativeCdpBrowserSession
    (기본값, production)과 BrowserSession(launch, 명시적 backend="launch"
    선택 시만 사용하는 개발·테스트 fallback) 중 하나를 반환한다.
    DiagnosticConfig는 safe_default()를 사용한다(브라우저 backend 선택과
    진단 플래그는 독립된 설정 축).
    """
    from src.browser.session import BrowserSession, NativeCdpBrowserSession
    from src.browser.config import BrowserBackendConfig, DiagnosticConfig

    diagnostic_config = DiagnosticConfig.safe_default()
    backend_config = BrowserBackendConfig.from_env()

    if backend_config.backend == "launch":
        return BrowserSession(diagnostic_config)
    return NativeCdpBrowserSession(diagnostic_config, backend_config)


def collect_apollo_first_list_query(
    page, job, target_count, *, collected_at, max_pages: int = 5, pause_event=None, stop_event=None
) -> dict:
    """신규 Apollo/GraphQL-first 목록 수집. 1페이지는 메인 placeList(...)
    operation만 파싱하고(DOM 스크롤 없음), 2페이지 이후는 자연 발생 GraphQL
    response를 harvest한다. run_collection_plan이 기대하는 최소 계약
    {"rows", "active_captcha_detected", "status_429_seen", "navigation_error",
    "navigation_error_message"}을 그대로 만족해 plan_runner.py는 무수정
    으로 재사용된다.

    실패 시맨틱: 1페이지 Apollo 구조 파싱 실패(search frame 없음/apollo_state
    없음/메인 placeList 없음·모호함/businesses.items 없음)만
    navigation_error=True로 취급한다(run_collection_plan이 이미 "즉시 큐
    전체 중단, 이전 결과 보존"으로 처리하는 필드 - 조용한 DOM fallback
    없음). 페이지네이션 소진/다음 페이지 버튼 없음/max_pages 도달은 정상
    종료(navigation_error=False)로 처리한다.

    반환에 추가된 진단 필드(navigation_error 계약 외): "page_count"(확정된
    페이지 수), "pagination_stop_reason"(정상 종료 사유).

    NEW-OPENING-1: job["new_opening_only"]=True면 메인 placeList 대신
    filterOpening=true 전용 placeList(extract_new_opening_place_list_from_apollo)
    를 찾는다. 2026-07-30 Live 실측상 이 operation은 page 1에 이미 존재하며
    "다음 페이지" 개념이 없는 고정 소규모 미리보기이므로(§4 실측 근거,
    scratchpad/new_opening_filter_implementation), 페이지네이션 루프를
    시도하지 않고 1페이지 결과만으로 즉시 종료한다 - 새로오픈 업체가
    목표보다 적어도 오류가 아니라 정상 종료다(§7)."""
    new_opening_only = bool(job.get("new_opening_only"))
    list_extractor = extract_new_opening_place_list_from_apollo if new_opening_only else extract_main_place_list_from_apollo
    error_prefix = "NewOpeningListParseError" if new_opening_only else "ApolloListParseError"

    ctx = _QueryObservationContext()
    response_handler = _make_response_handler(ctx)
    request_finished_handler = _make_request_finished_handler(ctx)
    request_failed_handler = _make_request_failed_handler(ctx)
    _registered_listeners: list = []
    try:
        for _event, _handler in (
            ("response", response_handler),
            ("requestfinished", request_finished_handler),
            ("requestfailed", request_failed_handler),
        ):
            page.on(_event, _handler)
            _registered_listeners.append((_event, _handler))
    except Exception:
        for _event, _handler in _registered_listeners:
            try:
                page.off(_event, _handler)
            except Exception:
                pass
        raise

    def _navigation_error_result(message: str) -> dict:
        return {
            "rows": [],
            "active_captcha_detected": False,
            "status_429_seen": ctx.status_429_seen,
            "navigation_error": True,
            "navigation_error_message": message,
            "page_count": 0,
            "pagination_stop_reason": None,
            "rejected_rows": [],
            "review_filter_stats": None,
        }

    try:
        query_text = job.get("query") or ""
        search_url = _SEARCH_URL_TEMPLATE.format(query=quote(query_text))
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
        except PlaywrightTimeoutError:
            pass  # BrowserSession.goto와 동일: 느린 로드는 관용적으로 흡수하고 계속 진행.
        except Exception as exc:
            return _navigation_error_result(f"{type(exc).__name__}: {exc}")

        frame = _find_search_frame(page)
        if frame is None:
            return _navigation_error_result("ApolloListParseError:search_frame_not_found")

        list_result = _wait_for_apollo_list_ready(page, frame, query_text, 0, hard_cap_ms=5000, extractor=list_extractor)
        if list_result["error"]:
            return _navigation_error_result(f"{error_prefix}:{list_result['error']}")

        mapped_rows = build_rows_from_apollo_list_result(list_result, collected_at, source_query=query_text)
        for row in mapped_rows:
            row["source_page"] = 1
            row["source_city"] = job.get("source_city")
            row["source_district"] = job.get("source_district")
            row["source_subregion"] = job.get("source_subregion")
            row["source_layer"] = job.get("source_layer")

        review_min = job.get("review_min")
        review_max = job.get("review_max")
        review_filter_enabled = review_min is not None or review_max is not None
        review_filter_stats = {"candidate": 0, "accepted": 0, "rejected_by_min": 0, "rejected_by_max": 0, "unknown": 0}

        local_seen: set = set()
        unique_rows = dedup_rows(mapped_rows, local_seen)
        unique_rows, rejected_rows = _split_region_valid_rows(unique_rows, job)
        if new_opening_only:
            unique_rows, new_opening_rejected = _split_new_opening_valid_rows(unique_rows)
            rejected_rows = rejected_rows + new_opening_rejected
        if review_filter_enabled:
            candidate_count = len(unique_rows)
            unique_rows, review_rejected = _split_review_valid_rows(unique_rows, review_min, review_max)
            rejected_rows = rejected_rows + review_rejected
            review_filter_stats = _merge_review_filter_stats(
                review_filter_stats, _review_filter_stats(candidate_count, review_rejected)
            )

        def _ensure_parsed_simple(index: int) -> dict:
            """candidate당 재확인 memoize를 하지 않는 단순화된 버전 - 이
            경로는 DOM class-diff 등 추가 하드닝이 없어 candidate 수 자체가
            훨씬 적으므로 매 호출마다
            다시 파싱해도 비용이 낮다(§3 - 새 pagination 루프는 의도적으로
            더 단순하게 작성)."""
            entry = ctx.candidates[index]
            if entry["body_snapshot_ready"]:
                if entry.get("candidate_error_type") == "CandidateHttpError":
                    return {"items": [], "error": True}
                try:
                    data = json.loads(entry["body_snapshot"])
                    return {"items": _extract_list_items(data), "error": False}
                except Exception:
                    return {"items": [], "error": True}
            if entry["body_snapshot_error_type"]:
                return {"items": [], "error": True}
            return {"items": [], "error": False, "pending": True}

        pagination_stop_reason = None
        current_page_number = 1
        final_captcha_signal = None

        if new_opening_only:
            # §4 Live 실측: 새로오픈 전용 operation은 page 1의 고정 소규모
            # 미리보기이며 "다음 페이지"가 없다 - 목표 미달이어도 페이지네이션을
            # 시도하지 않고 확보된 만큼으로 정상 종료한다(§7 - 오류/무한 이동
            # 아님).
            pagination_stop_reason = "new_opening_single_page_exhausted"
        elif target_count and len(unique_rows) >= target_count:
            pagination_stop_reason = "per_query_limit_reached"
        else:
            while current_page_number < max_pages:
                # 다음 페이지 이동 전(§5 요청서) - 일시정지 중이면 여기서
                # 대기하고, 대기 중 또는 대기 후 중지가 감지되면 새 페이지로
                # 넘어가지 않고 지금까지 확보한 rows를 보존한 채 정상 종료한다.
                wait_while_paused(pause_event, stop_event)
                if stop_event is not None and stop_event.is_set():
                    pagination_stop_reason = "user_stopped"
                    break

                probe = _probe_captcha_state(page)
                final_captcha_signal = classify_captcha_signal(
                    marker_present_in_dom=probe["marker_present"],
                    element_visible=probe["visible"],
                    bounding_box_area=probe["bounding_box_area"],
                    click_exception_message=probe["click_intercepted_message"],
                )
                if final_captcha_signal["active_captcha_detected"]:
                    pagination_stop_reason = "captcha_detected"
                    break
                if ctx.status_429_seen:
                    pagination_stop_reason = "status_429_seen"
                    break

                frame = _find_search_frame(page)
                if frame is None:
                    pagination_stop_reason = "pagination_exhausted"
                    break

                target_page_number = current_page_number + 1
                button_locator = _find_page_button(frame, target_page_number)
                try:
                    button_count = button_locator.count() if button_locator is not None else 0
                except Exception:
                    button_count = 0
                if button_count == 0:
                    pagination_stop_reason = "pagination_exhausted"
                    break
                if button_count > 1:
                    pagination_stop_reason = "ambiguous_page_button"
                    break

                target_locator = button_locator.first
                try:
                    is_ready = bool(target_locator.is_visible()) and bool(target_locator.is_enabled())
                except Exception:
                    pagination_stop_reason = "pagination_click_error"
                    break
                if not is_ready:
                    pagination_stop_reason = "pagination_click_error"
                    break

                count_before_click = ctx.candidate_response_count
                try:
                    target_locator.click()
                except Exception:
                    pagination_stop_reason = "pagination_click_error"
                    break

                wait_result = _wait_for_next_page_settle(
                    page, ctx, _ensure_parsed_simple, count_before_click, hard_cap_ms=5000
                )

                probe = _probe_captcha_state(page)
                final_captcha_signal = classify_captcha_signal(
                    marker_present_in_dom=probe["marker_present"],
                    element_visible=probe["visible"],
                    bounding_box_area=probe["bounding_box_area"],
                    click_exception_message=probe["click_intercepted_message"],
                )
                if final_captcha_signal["active_captcha_detected"]:
                    pagination_stop_reason = "captcha_detected"
                    break
                if ctx.status_429_seen:
                    pagination_stop_reason = "status_429_seen"
                    break
                if not wait_result["got_new_response"]:
                    pagination_stop_reason = "next_page_response_timeout"
                    break

                page_raw_items: list = []
                for index in range(count_before_click, wait_result["final_count"]):
                    parsed = _ensure_parsed_simple(index)
                    if not parsed["error"]:
                        page_raw_items.extend(parsed["items"])

                page_mapped_rows = []
                for item in page_raw_items:
                    row = _map_item_to_row(
                        item, collected_at, source_page=target_page_number, source_query=query_text
                    )
                    row["source_city"] = job.get("source_city")
                    row["source_district"] = job.get("source_district")
                    row["source_subregion"] = job.get("source_subregion")
                    row["source_layer"] = job.get("source_layer")
                    page_mapped_rows.append(row)

                newly_unique = dedup_rows(page_mapped_rows, local_seen)
                newly_valid, newly_rejected = _split_region_valid_rows(newly_unique, job)
                if review_filter_enabled:
                    candidate_count = len(newly_valid)
                    newly_valid, newly_review_rejected = _split_review_valid_rows(newly_valid, review_min, review_max)
                    newly_rejected = newly_rejected + newly_review_rejected
                    review_filter_stats = _merge_review_filter_stats(
                        review_filter_stats, _review_filter_stats(candidate_count, newly_review_rejected)
                    )
                unique_rows.extend(newly_valid)
                rejected_rows.extend(newly_rejected)
                current_page_number = target_page_number

                if target_count and len(unique_rows) >= target_count:
                    pagination_stop_reason = "per_query_limit_reached"
                    break
                if current_page_number >= max_pages:
                    pagination_stop_reason = "max_page_count_reached"
                    break

            if pagination_stop_reason is None:
                pagination_stop_reason = "max_page_count_reached"

        if final_captcha_signal is None:
            probe = _probe_captcha_state(page)
            final_captcha_signal = classify_captcha_signal(
                marker_present_in_dom=probe["marker_present"],
                element_visible=probe["visible"],
                bounding_box_area=probe["bounding_box_area"],
                click_exception_message=probe["click_intercepted_message"],
            )

        capped_rows = unique_rows[:target_count] if target_count else unique_rows
        return {
            "rows": capped_rows,
            "active_captcha_detected": bool(final_captcha_signal["active_captcha_detected"]),
            "status_429_seen": ctx.status_429_seen,
            "navigation_error": False,
            "navigation_error_message": "",
            "page_count": current_page_number,
            "pagination_stop_reason": pagination_stop_reason,
            "rejected_rows": rejected_rows,
            "review_filter_stats": review_filter_stats if review_filter_enabled else None,
        }
    finally:
        for event, event_handler in (
            ("response", response_handler),
            ("requestfinished", request_finished_handler),
            ("requestfailed", request_failed_handler),
        ):
            try:
                page.off(event, event_handler)
            except Exception:
                pass


class ApolloFirstListCollector:
    """Apollo/GraphQL-first 목록 수집의 production 기본 collector.

    컨텍스트 매니저 + `collect_query(job, per_query_limit)` 생명주기 계약을
    만족해 `run_collection_plan`이 그대로 재사용한다. `enrich_detail`/
    `enrich_detail_ssr`은 의도적으로 정의하지 않는다 - 홈페이지·SNS 포함
    모드의 home 보강은 이 클래스가 아니라 `src/collection/home_enrichment.py`가,
    이 컨텍스트가 닫힌(브라우저 세션이 종료된) 뒤 별도로 담당한다.
    """

    def __init__(self, *, collected_at, session_factory=None, max_pages: int = 5, pause_event=None, stop_event=None):
        self.collected_at = collected_at
        self.max_pages = max_pages
        self.pause_event = pause_event
        self.stop_event = stop_event
        self._session_factory = session_factory or _default_session_factory
        self._session_cm = None
        self._session = None

    def __enter__(self):
        self._session_cm = self._session_factory()
        self._session = self._session_cm.__enter__()
        self._close_initial_page_if_present()
        return self

    def _close_initial_page_if_present(self) -> None:
        initial_page = getattr(self._session, "page", None)
        if initial_page is None:
            return
        try:
            initial_page.close()
        except Exception:
            pass

    def collect_query(self, job, per_query_limit) -> dict:
        page = self._session.context.new_page()
        try:
            return collect_apollo_first_list_query(
                page,
                job,
                per_query_limit,
                collected_at=self.collected_at,
                max_pages=self.max_pages,
                pause_event=self.pause_event,
                stop_event=self.stop_event,
            )
        finally:
            try:
                page.close()
            except Exception:
                pass

    def capture_session_cookies(self) -> list:
        """`with` 블록이 열려있는 동안(context가 닫히기 전) 호출해야 한다 -
        홈페이지·SNS 포함 모드에서 sync Playwright 세션 종료 후 별도 async
        home enrichment 단계로 쿠키를 이어주기 위한 것이다(Playwright 객체
        자체는 넘기지 않고 순수 JSON 직렬화 가능한 list[dict]만 넘긴다 - 두
        단계 사이에 Playwright 객체의 thread/event loop 공유가 없다).
        best-effort이며 어떤 예외도 밖으로 던지지 않고 빈 list를 반환한다."""
        try:
            return self._session.context.cookies()
        except Exception:
            return []

    def __exit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            self._session_cm.__exit__(exc_type, exc, tb)
        self._session_cm = None
        self._session = None
        return False
