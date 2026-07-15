# ARCH-300C WIRE-2A: 쿼리 1개 단위 Network 응답 관찰 함수.
#
# 이 모듈은 이미 생성된 Playwright page(또는 FakePage)를 전달받아 검색 쿼리
# 1개만 처리하는 collect_network_query()와, 브라우저/context를 큐 전체에서
# 공유하며 쿼리마다 새 page를 생성/종료하는 생명주기 관리자
# NetworkBrowserCollector(WIRE-2B-1)를 함께 담는다. collect_network_query
# 자체는 여전히 브라우저를 직접 launch하지 않으므로 live 실행 없이 FakePage
# 주입만으로 검증할 수 있고, NetworkBrowserCollector도 session_factory에
# FakeSession을 주입하면 실제 Playwright 없이 생명주기(page 생성/종료 횟수,
# teardown 순서)만 검증할 수 있다.
#
# ARCH-300 PoC-1~9A(브라우저 네트워크 응답 관찰 기반 리스트 수집 기술 검증)의
# 연장선이며, PoC-7에서 검증된 검색 URL 형식·CAPTCHA probe 흐름을 그대로
# 재사용한다. is_candidate_response/_extract_list_items/_map_item_to_row/
# dedup_rows/classify_captcha_signal은 src/pc/network_list_scraper.py에서
# 읽기 전용으로 재사용하며 재구현하지 않는다.
#
# page=1만 수집한다: 페이지네이션 클릭, 카드 클릭, entryIframe 진입 코드는
# 이 모듈에 존재하지 않는다(존재하지 않는 것 자체가 page=1 보장이다).
# CAPTCHA DOM 제거/클릭/자동 해결/우회는 시도하지 않는다 - 감지된 신호는
# 반환 dict의 플래그로만 전달하며, 중단 여부 판단은 이 함수를 호출하는
# 상위 orchestrator(run_collection_plan, WIRE-1)의 책임이다.
#
# WIRE-2A-B: page.goto()에서 발생 가능한 예외는 성격이 다르다. 실제 Playwright
# TimeoutError(느린 로드)만 timeout=True로 분류하고, "page/context/browser가
# 이미 닫힘(Target closed)"·"브라우저 실행 장애"·"일반 navigation 오류" 등
# 그 외 예외는 timeout으로 위장하지 않고 navigation_error로 별도 분류한다
# (browser_session.goto와 동일하게 PlaywrightTimeoutError만 관용적으로 흡수).
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pc.browser_session import _CAPTCHA_PROBE_SELECTORS
from src.pc.network_list_scraper import (
    _extract_list_items,
    _map_item_to_row,
    classify_captcha_signal,
    dedup_rows,
    is_candidate_response,
)

_SEARCH_URL_TEMPLATE = "https://map.naver.com/v5/search/{query}"

# ARCH-300C PERF-1A: 적응형 settle 종료 상수(모듈 상수로만 고정 - 이번 단계에서
# collect_network_query 시그니처나 UI에는 노출하지 않는다). settle_ms(기존
# 파라미터, 기본 5000)는 "무조건 기다리는 시간"에서 "최대 대기 hard cap"으로
# 의미가 바뀌었고, 파싱 가능한(비어있지 않은) 업체 목록 응답을 확인한 뒤
# _QUIET_PERIOD_MS 동안 추가 후보가 도착하지 않으면 hard cap 전에 조기
# 종료한다. 750/100이라는 구체적인 값은 WIRE-4C(실제 네이버, 300건 규모)
# 관찰에서 얻은 잠정치이며, candidate 응답들 사이의 실제 도착 간격(inter-arrival
# gap)을 직접 계측한 적은 아직 없다 - 다음 live 검증 단계(WIRE-5 등)에서
# 이 값의 적정성을 실측으로 재확인해야 한다(반대 검토 AI 지적 사항).
_QUIET_PERIOD_MS = 750
_POLL_INTERVAL_MS = 100


class _QueryObservationContext:
    """쿼리 1회 호출에 국한된 로컬 상태(전역/클래스 공용 상태를 두지 않기 위함).

    handler는 이 인스턴스에만 기록하며, collect_network_query 호출이 끝나면
    함께 버려진다 - 다음 쿼리는 항상 새 인스턴스로 시작하므로 이전 쿼리의
    응답과 섞이지 않는다(페이지 자체도 WIRE-2B부터는 쿼리마다 새로 생성/종료될
    예정이라 이중으로 격리된다).
    """

    def __init__(self):
        self.candidate_responses: list = []
        self.candidate_response_count = 0
        self.status_429_seen = False


def _make_response_handler(ctx: _QueryObservationContext):
    """response handler는 최소 작업만 한다(상태 확인 + 후보 저장) - json 파싱은
    settle 종료 후 별도로 수행해 callback 블로킹을 피하고 parse_error_count를
    명확히 집계한다."""

    def handle_response(response) -> None:
        try:
            if response.status == 429:
                ctx.status_429_seen = True
        except Exception:
            pass

        try:
            resource_type = response.request.resource_type
        except Exception:
            resource_type = ""
        url = response.url or ""

        try:
            if is_candidate_response(url, resource_type):
                ctx.candidate_response_count += 1
                ctx.candidate_responses.append(response)
        except Exception:
            pass

    return handle_response


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


def collect_network_query(
    page,
    job,
    per_query_limit,
    *,
    collected_at,
    settle_ms: int = 5000,
) -> dict:
    """쿼리 1개를 처리하는 Network 응답 관찰 함수(page는 호출자가 이미 생성해 전달).

    반환: {"rows", "active_captcha_detected", "status_429_seen",
    "candidate_response_count", "raw_item_count", "local_unique_count",
    "parse_error_count", "timeout", "navigation_error",
    "navigation_error_message", "adaptive_settle_wait_ms",
    "adaptive_settle_early_exit"}. rows는 network_pipeline.run_collection_plan이
    기대하는 형태(place_id/업체명 키를 가진 dict)이며, job의 source_city/
    source_district/source_subregion/source_layer를 각 row에 그대로
    전달한다(전역 dedup은 이 함수의 책임이 아니라 run_collection_plan의
    책임 - 여기서는 쿼리 내부 로컬 dedup만 수행한다).

    navigation 정책(WIRE-2A-B): page.goto()가 실제 PlaywrightTimeoutError를
    던지면 "느린 로드"로 간주해 관용적으로 흡수하고(timeout=True), 이후
    settle 대기·후보 파싱·CAPTCHA probe를 그대로 계속 진행한다(BrowserSession.
    goto와 동일하게 현재 DOM으로 계속 진행). 그 외 예외(Target closed 등
    page/context/browser가 이미 닫혔거나 브라우저 실행 자체가 실패한 경우)는
    페이지 상태를 더 이상 신뢰할 수 없다고 보고 settle 대기·후보 파싱·CAPTCHA
    probe를 전부 건너뛰며 즉시 navigation_error=True, timeout=False, rows=[]로
    반환한다(CAPTCHA/429로 오분류하지 않는다). 이 함수는 이 경우 재시도하지
    않으며, 재시도/복구 정책은 이 함수를 호출하는 상위 계층(WIRE-2B 이후)의
    책임으로 남겨둔다. 상위 orchestrator(run_collection_plan)와 UI는 이번
    단계에서 이 신규 필드를 아직 읽지 않는다.

    적응형 settle(PERF-1A, WIRE-2A-B 이후 추가): settle_ms는 "무조건 대기
    시간"이 아니라 "최대 대기 hard cap"이다. page.wait_for_timeout(settle_ms)
    한 번 대신, _POLL_INTERVAL_MS(100ms) 간격으로 폴링하며 매 tick마다 새로
    도착한 candidate 응답이 있는지 확인한다. 새 candidate를 "예외 없이
    파싱 성공하고 추출된 목록이 비어있지 않음"(valid) 기준으로 확인하면
    조기 종료 대상으로 표시하고, 이후 _QUIET_PERIOD_MS(750ms) 동안 추가
    candidate가 전혀 도착하지 않으면 hard cap 전에 즉시 대기를 끝낸다.
    추가 candidate가 도착하면 valid 여부와 무관하게 quiet 타이머를 다시
    시작한다(늦게 오는 두 번째 응답에게 다시 기회를 준다). candidate가
    전혀 없거나 끝까지 valid로 확인되지 않으면 기존과 동일하게 hard cap
    전체를 대기한다(회귀 없음 - candidate_response_count==0인 케이스는
    timeout 계산도 기존과 동일).

    알려진 트레이드오프(반대 검토 AI 확인, 의도된 설계): quiet period가
    지나 조기 종료한 "직후"에 두 번째 candidate가 도착하면 그 응답은
    수집되지 않는다(harvest 루프가 이미 끝난 뒤이므로). 기존 고정 5초
    대기는 이 경우를 항상 잡았을 수 있다 - 이는 속도 최적화가 감수하는
    알려진 트레이드오프이며, candidate 간 실제 도착 간격(750ms 적정성)은
    아직 live로 계측되지 않았다(§_QUIET_PERIOD_MS 주석). "valid" 판정은
    빈 목록을 확인한 것만으로는 성립하지 않는다 - 응답 URL 후보 판별
    (is_candidate_response)이 실제 업체 목록이 아닌 응답(예: pcmap host의
    다른 xhr/fetch)도 후보로 잡을 수 있어, "빈 목록도 valid"로 두면 진짜
    데이터가 담긴 응답이 나중에 와도 그 전에 조기 종료해 데이터를 통째로
    놓칠 위험이 있기 때문이다(반대 검토에서 발견된 결함, 수정 반영).
    elapsed_ms는 폴링 대기(wait_for_timeout 호출)의 누적 합이며 실제
    벽시계 시간이 아니다 - tick 사이의 파싱/probe 작업 시간은 포함되지
    않으므로 실제 경과 시간은 이보다 소폭 더 걸릴 수 있다(기존 방식도
    고정 대기 후 파싱 작업을 했으므로 총량 자체는 회귀가 아니다).
    """
    ctx = _QueryObservationContext()
    handler = _make_response_handler(ctx)
    page.on("response", handler)

    goto_timed_out = False
    navigation_error = False
    navigation_error_message = ""
    try:
        search_url = _SEARCH_URL_TEMPLATE.format(query=quote(job["query"]))
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
        except PlaywrightTimeoutError:
            # BrowserSession.goto와 동일한 태도: 타임아웃이어도 현재 DOM으로 계속
            # 진행한다(우회가 아니라 "느린 로드"에 대한 관용 - CAPTCHA와는 무관).
            goto_timed_out = True
        except Exception as exc:
            # Target closed/브라우저 실행 장애 등 "느린 로드"가 아닌 그 외
            # navigation 오류는 timeout으로 위장하지 않는다. 페이지 상태를
            # 더 이상 신뢰할 수 없으므로 이후 단계(settle/파싱/CAPTCHA probe)를
            # 시도하지 않고 즉시 반환한다.
            navigation_error = True
            navigation_error_message = f"{type(exc).__name__}: {exc}"

        if navigation_error:
            return {
                "rows": [],
                "active_captcha_detected": False,
                "status_429_seen": ctx.status_429_seen,
                "candidate_response_count": ctx.candidate_response_count,
                "raw_item_count": 0,
                "local_unique_count": 0,
                "parse_error_count": 0,
                "timeout": False,
                "navigation_error": True,
                "navigation_error_message": navigation_error_message,
                "adaptive_settle_wait_ms": 0,
                "adaptive_settle_early_exit": False,
            }

        # PERF-1A 적응형 settle: parsed_cache는 candidate 응답 하나당
        # response.json()/_extract_list_items()를 정확히 1회만 호출하도록
        # 메모이즈한다(폴링 루프의 "peek" 확인과 아래 harvest 단계가 결과를
        # 공유 - 중복 파싱/중복 parse_error 집계를 방지).
        parsed_cache: dict = {}

        def _ensure_parsed(index: int) -> dict:
            if index not in parsed_cache:
                response = ctx.candidate_responses[index]
                try:
                    data = response.json()
                    items = _extract_list_items(data)
                    parsed_cache[index] = {"items": items, "error": False}
                except Exception:
                    parsed_cache[index] = {"items": [], "error": True}
            return parsed_cache[index]

        elapsed_ms = 0
        last_seen_count = 0
        valid_list_confirmed = False
        quiet_elapsed_ms = 0

        while elapsed_ms < settle_ms:
            page.wait_for_timeout(_POLL_INTERVAL_MS)
            elapsed_ms += _POLL_INTERVAL_MS

            current_count = ctx.candidate_response_count
            if current_count > last_seen_count:
                found_valid_this_tick = False
                for index in range(last_seen_count, current_count):
                    parsed = _ensure_parsed(index)
                    if not parsed["error"] and parsed["items"]:
                        found_valid_this_tick = True
                last_seen_count = current_count
                # 새 candidate가 도착하면(valid 여부와 무관하게) quiet 타이머를
                # 다시 시작한다 - 늦게 오는 두 번째 응답에게 다시 기회를 준다.
                quiet_elapsed_ms = 0
                if found_valid_this_tick:
                    valid_list_confirmed = True
            elif valid_list_confirmed:
                quiet_elapsed_ms += _POLL_INTERVAL_MS
                if quiet_elapsed_ms >= _QUIET_PERIOD_MS:
                    break

        adaptive_settle_wait_ms = elapsed_ms
        adaptive_settle_early_exit = elapsed_ms < settle_ms

        raw_items: list = []
        parse_error_count = 0
        for index in range(len(ctx.candidate_responses)):
            parsed = _ensure_parsed(index)
            if parsed["error"]:
                parse_error_count += 1
            else:
                raw_items.extend(parsed["items"])

        probe = _probe_captcha_state(page)
        signal = classify_captcha_signal(
            marker_present_in_dom=probe["marker_present"],
            element_visible=probe["visible"],
            bounding_box_area=probe["bounding_box_area"],
            click_exception_message=probe["click_intercepted_message"],
        )

        mapped_rows = []
        for item in raw_items:
            row = _map_item_to_row(item, collected_at, source_query=job.get("query"))
            row["source_city"] = job.get("source_city")
            row["source_district"] = job.get("source_district")
            row["source_subregion"] = job.get("source_subregion")
            row["source_layer"] = job.get("source_layer")
            mapped_rows.append(row)

        local_seen: set = set()
        unique_rows = dedup_rows(mapped_rows, local_seen)
        capped_rows = unique_rows[:per_query_limit] if per_query_limit else unique_rows

        timeout = goto_timed_out or ctx.candidate_response_count == 0

        return {
            "rows": capped_rows,
            "active_captcha_detected": bool(signal["active_captcha_detected"]),
            "status_429_seen": ctx.status_429_seen,
            "candidate_response_count": ctx.candidate_response_count,
            "raw_item_count": len(raw_items),
            "local_unique_count": len(unique_rows),
            "parse_error_count": parse_error_count,
            "timeout": timeout,
            "navigation_error": False,
            "navigation_error_message": "",
            "adaptive_settle_wait_ms": adaptive_settle_wait_ms,
            "adaptive_settle_early_exit": adaptive_settle_early_exit,
        }
    finally:
        try:
            page.off("response", handler)
        except Exception:
            pass


def _default_session_factory():
    """실제 제품 배선용 기본 factory - BrowserSession을 참고하되, 이 함수가
    호출되어 반환된 객체의 __enter__가 실제로 호출될 때만 Playwright가
    시작된다(이 함수를 정의/참조하는 것만으로는 아무것도 시작하지 않는다).
    테스트는 항상 session_factory를 fake로 주입하므로 이 함수는 테스트에서
    호출되지 않는다.
    """
    from src.pc.browser_session import BrowserSession
    from src.pc.config import DiagnosticConfig

    return BrowserSession(DiagnosticConfig.safe_default())


class NetworkBrowserCollector:
    """실제 제품 경로에서 사용할 브라우저 생명주기 관리자(WIRE-2B-1).

    브라우저 1개·context 1개를 큐 전체(여러 쿼리)에서 공유하고, 쿼리마다
    새 page를 생성해 collect_network_query에 전달한 뒤 그 쿼리가 끝나면
    즉시 닫는다(page를 여러 쿼리에서 재사용하지 않는다):

        browser 1개 → context 1개 → [쿼리마다: new_page → collect_network_query
        → page.close()] → 큐 종료 후 context/browser/playwright 종료

    이렇게 페이지를 쿼리마다 격리하면 (1) 이전 쿼리의 늦은 응답이 다음
    쿼리로 섞이지 않고(response listener가 page와 함께 폐기됨) (2) 쿠키/
    세션은 동일 context에서 그대로 유지된다. CAPTCHA 발생 후 context를
    재시작하거나 재시도로 우회하지 않는다 - 이 클래스는 생명주기만
    관리하며, 안전 중단 판단은 여전히 run_collection_plan의 책임이다.

    session_factory는 인자 없이 호출하면 BrowserSession과 동일한 계약
    (컨텍스트 매니저로 진입(`__enter__`)하면 최소 `.context` 속성을 가진
    객체를 반환)을 만족하는 callable이어야 한다. 기본값은 실제
    BrowserSession을 참고하지만, 이 클래스의 `__enter__`가 실제로 호출될
    때만 Playwright가 시작된다 - 테스트는 항상 FakeSession factory를
    주입해 실제 BrowserSession/Playwright를 절대 실행하지 않는다.

    BrowserSession(WIRE-2B-1B 확인 - 실제 속성 기준): __enter__()가 browser/
    context와 함께 초기 page 1개(`session.page`)도 미리 만들어 둔다(다른
    호출부인 detail_scraper 등이 session.page를 바로 goto에 쓰는 용도).
    이 클래스는 쿼리마다 context에서 새 page를 만들어 쓰므로 그 초기 page를
    수집용으로 재사용하지 않는다 - `__enter__`에서 best-effort로 즉시 닫아
    큐 실행 내내 불필요한 page가 열려있지 않게 한다(닫기에 실패해도 결국
    BrowserSession._teardown()의 context.close()가 정리하므로 안전하다).
    session 객체에 `.page` 속성 자체가 없으면(FakeSession 등) 아무 것도
    하지 않는다.
    """

    def __init__(self, *, collected_at, session_factory=None, settle_ms: int = 5000):
        self.collected_at = collected_at
        self.settle_ms = settle_ms
        self._session_factory = session_factory or _default_session_factory
        self._session_cm = None
        self._session = None

    def __enter__(self):
        self._session_cm = self._session_factory()
        self._session = self._session_cm.__enter__()
        self._close_initial_page_if_present()
        return self

    def _close_initial_page_if_present(self) -> None:
        """BrowserSession.__enter__가 미리 만든 초기 page(session.page)는 쿼리별
        page 생성 방식과 무관하므로 수집용으로 쓰지 않고 즉시 닫는다(best-effort).
        """
        initial_page = getattr(self._session, "page", None)
        if initial_page is None:
            return
        try:
            initial_page.close()
        except Exception:
            pass

    def collect_query(self, job, per_query_limit) -> dict:
        """run_collection_plan이 기대하는 collect_query(job, per_query_limit)
        시그니처를 만족하는 bound method. 공유 context에서 새 page를 만들어
        collect_network_query에 위임하고, 결과를 반환한 뒤(반환값 확정 후)
        page를 best-effort로 닫는다 - page.close()가 예외를 던져도(이미
        닫힌 page, Target closed 등) 그 예외를 삼키므로 collect_network_query
        가 만든 원래 결과(navigation_error 포함)를 덮어쓰지 않는다.
        """
        page = self._session.context.new_page()
        try:
            return collect_network_query(
                page,
                job,
                per_query_limit,
                collected_at=self.collected_at,
                settle_ms=self.settle_ms,
            )
        finally:
            try:
                page.close()
            except Exception:
                pass

    def __exit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            self._session_cm.__exit__(exc_type, exc, tb)
        self._session_cm = None
        self._session = None
        return False
