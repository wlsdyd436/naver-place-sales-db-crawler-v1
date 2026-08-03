# Apollo/GraphQL 목록 Network 응답을 관찰해 Place row를 수집하는 Collector
# 모듈(ApolloFirstListCollector/collect_apollo_first_list_query, 파일
# 하단)과 그 인프라(listener 등록·해제, 페이지네이션 orchestration)를 담는다.
# BrowserSession(Native Edge CDP 세션)은 src/browser가 제공하고, candidate
# response/request 생명주기 관찰(_QueryObservationContext, response/
# requestfinished/requestfailed 핸들러)은 src/collection.apollo_response_observer를,
# Apollo 목록 페이지 DOM 탐색·polling/settle 대기(CAPTCHA probe, search
# frame·page button 탐색, Apollo state 준비 대기)는 src/collection.
# apollo_page_navigator를, Apollo 목록 선택(extract_main_place_list_from_apollo
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
import uuid
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.collection.apollo_list_adapter import (
    build_rows_from_apollo_list_result,
    extract_main_place_list_from_apollo,
    extract_new_opening_place_list_from_apollo,
)
from src.collection.apollo_page_navigator import (
    _find_page_button,
    _find_search_frame,
    _find_visible_captcha_dialog_locator,
    _probe_captcha_state,
    _wait_for_apollo_list_ready,
    _wait_for_next_page_settle,
)
from src.diagnostics import DEFAULT_DIAGNOSTICS_ROOT, save_security_block_diagnostics
from src.collection.apollo_response_observer import (
    _QueryObservationContext,
    _make_candidate_parser,
    _make_request_failed_handler,
    _make_request_finished_handler,
    _make_response_handler,
)
from src.collection.place_mapper import (
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


class _SecurityDiagnosticsRecorder:
    """실행(하나의 ApolloFirstListCollector `with` 블록 = 사용자가 시작한
    수집 1회) 단위로 CAPTCHA/보안 차단 진단 저장을 최초 1회만 허용한다.
    모듈 전역 mutable 상태를 쓰지 않고, 호출자가 인스턴스를 명시적으로 들고
    다니며 재사용한다(같은 실행의 여러 job/페이지가 이 인스턴스를 공유) -
    새 실행은 새 인스턴스를 만들면 다시 저장 가능하다."""

    def __init__(self):
        self._captured = False

    def try_reserve(self) -> bool:
        if self._captured:
            return False
        self._captured = True
        return True


def _maybe_save_security_diagnostics(
    *, page, security_diagnostics_recorder, diagnostics_root, run_id,
    detection_source, probe, signal, pagination_stop_reason,
    collected_count, page_sequence, target_page,
):
    """recorder가 아직 저장한 적 없을 때만(요청서 §3 실행당 1회) best-effort로
    진단을 저장한다. security_diagnostics_recorder가 None이면(기존 직접
    함수 호출 테스트 등 opt-in하지 않은 호출자) 아무 것도 하지 않는다 -
    기존 호출부에 부작용이 생기지 않도록 기본값 자체가 "off"다."""
    if security_diagnostics_recorder is None or not security_diagnostics_recorder.try_reserve():
        return None
    dialog_locator = _find_visible_captcha_dialog_locator(page)
    result = save_security_block_diagnostics(
        captcha_dialog_locator=dialog_locator,
        diagnostics_root=diagnostics_root if diagnostics_root is not None else DEFAULT_DIAGNOSTICS_ROOT,
        run_id=run_id,
        detection_source=detection_source,
        active_captcha_detected=bool(signal.get("active_captcha_detected")),
        click_intercepted_by_captcha=bool(signal.get("click_intercepted_by_captcha")),
        passive_captcha_marker_found=bool(signal.get("passive_captcha_marker_found")),
        marker_present=bool(probe.get("marker_present")),
        element_visible=bool(probe.get("visible")),
        bounding_box_area=float(probe.get("bounding_box_area") or 0.0),
        pagination_stop_reason=pagination_stop_reason,
        collected_count=collected_count,
        page_sequence=page_sequence,
        target_page=target_page,
        current_url=getattr(page, "url", ""),
    )
    if result.get("json_saved"):
        print(f"[진단] 보안 차단 정보 저장: {result.get('json_path')}")
    if result.get("screenshot_saved"):
        print(f"[진단] CAPTCHA 화면 저장: {result.get('screenshot_path')}")
    elif result.get("json_saved"):
        print(f"[진단] CAPTCHA 화면 저장 실패: {result.get('screenshot_error')}")
    return result


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
    page, job, target_count, *, collected_at, max_pages: int = 5, pause_event=None, stop_event=None,
    security_diagnostics_recorder=None, diagnostics_root=None, run_id="",
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
    _ensure_parsed_simple = _make_candidate_parser(ctx)
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

        pagination_stop_reason = None
        current_page_number = 1
        final_captcha_signal = None
        security_diagnostics_result = None

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
                    security_diagnostics_result = _maybe_save_security_diagnostics(
                        page=page, security_diagnostics_recorder=security_diagnostics_recorder,
                        diagnostics_root=diagnostics_root, run_id=run_id,
                        detection_source="visible_dialog", probe=probe, signal=final_captcha_signal,
                        pagination_stop_reason=pagination_stop_reason, collected_count=len(unique_rows),
                        page_sequence=current_page_number, target_page=None,
                    )
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
                except Exception as exc:
                    # 2026-08 실측: 클릭 전 probe는 active=False였는데 클릭
                    # 도중 CAPTCHA dialog가 pointer event를 가로채 click()
                    # 자체가 예외로 실패하는 경우가 있었다 - 이 예외를 무조건
                    # pagination_click_error로 뭉개지 않고, 같은 classify_captcha_signal
                    # (재구현 없음)로 재분류해 실제 CAPTCHA면 captcha_detected로
                    # 중단한다. final_captcha_signal을 갱신해야 함수 최종
                    # 반환의 active_captcha_detected(plan_runner의
                    # security_blocked 연결 지점)에도 반영된다.
                    post_probe = _probe_captcha_state(page)
                    post_signal = classify_captcha_signal(
                        marker_present_in_dom=post_probe["marker_present"],
                        element_visible=post_probe["visible"],
                        bounding_box_area=post_probe["bounding_box_area"],
                        click_exception_message=str(exc),
                    )
                    if post_signal["active_captcha_detected"] or post_signal["click_intercepted_by_captcha"]:
                        pagination_stop_reason = "captcha_detected"
                        final_captcha_signal = post_signal
                        security_diagnostics_result = _maybe_save_security_diagnostics(
                            page=page, security_diagnostics_recorder=security_diagnostics_recorder,
                            diagnostics_root=diagnostics_root, run_id=run_id,
                            detection_source="click_interception", probe=post_probe, signal=post_signal,
                            pagination_stop_reason=pagination_stop_reason, collected_count=len(unique_rows),
                            page_sequence=current_page_number, target_page=target_page_number,
                        )
                    else:
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
                    security_diagnostics_result = _maybe_save_security_diagnostics(
                        page=page, security_diagnostics_recorder=security_diagnostics_recorder,
                        diagnostics_root=diagnostics_root, run_id=run_id,
                        detection_source="visible_dialog", probe=probe, signal=final_captcha_signal,
                        pagination_stop_reason=pagination_stop_reason, collected_count=len(unique_rows),
                        page_sequence=target_page_number, target_page=target_page_number,
                    )
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
        # click_intercepted_by_captcha(클릭 도중 CAPTCHA dialog가 pointer
        # event를 가로챈 경우, root 자체는 active 조건을 못 채울 수 있음)도
        # active_captcha_detected와 동일하게 CAPTCHA 확정 신호로 취급한다 -
        # plan_runner는 이 단일 bool 필드만 보고 security_blocked를 판정한다.
        return {
            "rows": capped_rows,
            "active_captcha_detected": bool(
                final_captcha_signal["active_captcha_detected"]
                or final_captcha_signal.get("click_intercepted_by_captcha")
            ),
            "status_429_seen": ctx.status_429_seen,
            "navigation_error": False,
            "navigation_error_message": "",
            "page_count": current_page_number,
            "pagination_stop_reason": pagination_stop_reason,
            "rejected_rows": rejected_rows,
            "review_filter_stats": review_filter_stats if review_filter_enabled else None,
            "security_diagnostics": security_diagnostics_result,
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
        # 이 인스턴스(하나의 with 블록 = 사용자가 시작한 수집 1회) 동안
        # 여러 job/페이지가 CAPTCHA를 만나도 진단 저장은 최초 1회만 - 모듈
        # 전역이 아닌 인스턴스 상태로 관리한다(요청서 §3).
        self._security_diagnostics_recorder = _SecurityDiagnosticsRecorder()
        self._run_id = uuid.uuid4().hex

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
                security_diagnostics_recorder=self._security_diagnostics_recorder,
                run_id=self._run_id,
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
