from pathlib import Path
import inspect
import json
import sys


# ARCH-300C PAGE-300-2B-1: src/pc/network_browser_collector.py의 제한된
# 페이지네이션(최대 _MAX_PAGINATION_PAGES=5페이지, 다음 페이지 번호 버튼
# 클릭 -> 신규 candidate response 대기 -> 기존 adaptive quiet-period로 안정화
# -> harvest -> local dedup 누적)을 검증하는 standalone 스크립트(실제
# Playwright/네이버 접속 없음). 기존 tests/test_pc_network_adaptive_settle.py의
# FakeAdaptivePage(fake clock)를 확장해, 페이지 버튼 클릭이 "클릭 시점을
# 기준으로 한 상대 지연" 뒤에 신규 response를 전달할 수 있도록
# FakePaginationPage/FakeSearchFrame/FakePaginationButtonLocator를 새로 둔다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc import network_browser_collector
from src.pc.network_browser_collector import collect_network_query


class ValidationReporter:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0
        self.warn_count = 0

    def pass_(self, message: str) -> None:
        self.pass_count += 1
        print(f"[PASS] {message}")

    def fail(self, message: str) -> None:
        self.fail_count += 1
        print(f"[FAIL] {message}")

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print("검증 요약")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"WARN: {self.warn_count}")
        print(f"FINAL: {final}")
        print("====================")


class FakeLocator:
    """CAPTCHA probe(_probe_captcha_state)가 기대하는 최소 계약만 흉내낸다
    (기존 test_pc_network_browser_collector.py/test_pc_network_adaptive_settle.py
    와 동일한 패턴 - 파일 간 import 없이 각자 독립적으로 정의)."""

    def __init__(self, count=0, visible=False, box=None):
        self._count = count
        self._visible = visible
        self._box = box or {"width": 0, "height": 0}

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def is_visible(self, timeout=300):
        return self._visible

    def bounding_box(self):
        return self._box


class FakeRequest:
    """PAGE-300-2B-2B: requestfinished/requestfailed 핸들러가 받는 request
    객체를 흉내낸다(response와 양방향 참조)."""

    def __init__(self, resource_type, method="GET"):
        self.resource_type = resource_type
        self.method = method
        self.failure = None
        self._response = None

    def response(self):
        return self._response


class FakeResponse:
    """PAGE-300-2B-2B: `.json()` 대신 `.body()`(bytes)로 candidate body를
    노출한다 - body_call_count로 requestfinished 시점 이후 재호출이 없는지
    계측한다."""

    def __init__(self, url, status, resource_type, *, body=None, body_error=None,
                 method="GET", simulate_request_failed=False, headers=None):
        self.url = url
        self.status = status
        self.request = FakeRequest(resource_type, method=method)
        self.request._response = self
        self._body = body
        self._body_error = body_error
        self.body_call_count = 0
        self.simulate_request_failed = simulate_request_failed
        self.headers = headers if headers is not None else {}

    def body(self):
        self.body_call_count += 1
        if self._body_error is not None:
            raise self._body_error
        return self._body

    def text(self):
        if self._body_error is not None:
            raise self._body_error
        return (self._body or b"").decode("utf-8")


CANDIDATE_URL = "https://map.naver.com/p/api/search/allSearch?query=x"


def _place_response(item_ids_and_names, url=CANDIDATE_URL):
    items = [{"id": item_id, "name": name} for item_id, name in item_ids_and_names]
    body = json.dumps({"result": {"place": {"list": items}}}).encode("utf-8")
    return FakeResponse(url, 200, "xhr", body=body)


def _page_items(prefix: str, count: int):
    return [(f"{prefix}{i}", f"업체{prefix}{i}") for i in range(count)]


class FakePaginationButtonLocator:
    """페이지 번호 버튼 1개(또는 count>=2인 "모호한" 상태)를 흉내낸다.
    spec은 dict이며 click_plan에 저장된 바로 그 객체를 그대로 참조하므로,
    click_calls/scroll_calls를 spec에 직접 기록해 테스트가 click_plan을 통해
    사후 확인할 수 있다(locator 인스턴스를 별도로 캡처할 필요 없음)."""

    def __init__(self, spec: dict, page_ref):
        self._spec = spec
        self._page_ref = page_ref

    @property
    def first(self):
        return self

    def count(self):
        return self._spec.get("count", 0)

    def is_visible(self, timeout=None):
        return self._spec.get("visible", True)

    def is_enabled(self):
        return self._spec.get("enabled", True)

    def get_attribute(self, name):
        """PAGE-300-2B-1-FIX §6: DOM class diff 기반 identity 확인을 흉내낸다.
        spec에 명시하지 않으면 기본값은 클릭 전("mBN2s")과 클릭 후("mBN2s
        active-fake")가 서로 달라 "확인됨(confirmed)" 상태를 시뮬레이션한다 -
        기존(§6 도입 전) 23개 검증이 전부 DOM 확인 성공을 전제로 작성됐으므로,
        명시적으로 class_before/class_after를 지정하지 않는 한 항상 전환이
        확인된 것으로 취급해 기존 검증을 그대로 통과시킨다. get_attribute_error를
        지정하면 매 호출마다 그 예외를 던져 "식별 불가"(identity 판단 근거
        자체가 없는 경우)를 시뮬레이션한다."""
        if name != "class":
            return None
        error = self._spec.get("get_attribute_error")
        if error is not None:
            raise error
        if self._spec.get("click_calls", 0) > 0:
            return self._spec.get("class_after", "mBN2s active-fake")
        return self._spec.get("class_before", "mBN2s")

    def scroll_into_view_if_needed(self):
        self._spec["scroll_calls"] = self._spec.get("scroll_calls", 0) + 1

    def click(self):
        # 이 메서드는 의도적으로 force 등 어떤 인자도 받지 않는다 - production이
        # locator.click(force=True) 등으로 호출하면 TypeError가 발생해
        # pagination_click_error로 귀결되므로, 성공 자체가 force 미사용 증거다.
        self._spec["click_calls"] = self._spec.get("click_calls", 0) + 1
        error = self._spec.get("click_error")
        if error is not None:
            raise error
        # 반대 검토(Codex/gpt-5.6-sol) 지적 재현용 훅: 클릭 "직후"에 CAPTCHA가
        # 나타나거나(클릭 전에는 없었다가) 다음 wait_for_timeout 호출이 예외를
        # 던지는 상황을 각각 시뮬레이션한다.
        activates_captcha = self._spec.get("activates_captcha_after_click")
        if activates_captcha is not None:
            selector, locator = activates_captcha
            self._page_ref._captcha_selectors[selector] = locator
        raise_on_wait = self._spec.get("raise_on_wait_after_click")
        if raise_on_wait is not None:
            self._page_ref._pending_wait_error = raise_on_wait
        for delay_ms, response in (self._spec.get("responses_after_click") or []):
            self._page_ref._schedule_relative(delay_ms, response)


class FakeSearchFrame:
    """searchIframe 내부에서 페이지 번호 버튼을 찾는 get_by_role만 흉내낸다.
    click_plan은 {"목표 페이지 번호 문자열": spec dict} 형태이며, 없는 키를
    조회하면 count=0(버튼 없음)을 반환한다."""

    def __init__(self, click_plan: dict, page_ref, *, name="searchIframe", url="https://map.naver.com/p/search"):
        self._click_plan = click_plan
        self._page_ref = page_ref
        self.name = name
        self.url = url
        self.get_by_role_calls: list = []

    def get_by_role(self, role, name=None, exact=None):
        self.get_by_role_calls.append((role, name, exact))
        spec = self._click_plan.get(name)
        if spec is None:
            return FakePaginationButtonLocator({"count": 0}, self._page_ref)
        return FakePaginationButtonLocator(spec, self._page_ref)


class FakePaginationPage:
    """wait_for_timeout(ms) 호출마다 누적 경과시간(_elapsed_ms)을 추적하고,
    그 경과시간을 기준으로 예약된 response를 전달하는 fake clock page
    (FakeAdaptivePage와 동일한 원리). 페이지 번호 버튼 click()이 호출되면
    "클릭 시점(현재 _elapsed_ms) + 지연"을 기준으로 새 response를 추가
    예약할 수 있다(_schedule_relative) - 페이지 클릭마다 다른 지연/무응답을
    표현하기 위함. 실제 시간 대기는 전혀 하지 않는다."""

    def __init__(self, initial_schedule, click_plan=None, *, captcha_selectors=None, goto_error=None, frame_missing=False):
        self._handlers: dict = {}
        self._schedule = sorted(initial_schedule, key=lambda pair: pair[0])
        self._delivered_count = 0
        self._elapsed_ms = 0
        self._captcha_selectors = captcha_selectors or {}
        self._goto_error = goto_error
        self._frame = None if frame_missing else FakeSearchFrame(click_plan or {}, self)
        self.goto_calls: list = []
        self.wait_calls: list = []
        self._pending_wait_error = None

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event, handler):
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        if self._goto_error is not None:
            raise self._goto_error
        self._deliver_due()

    def wait_for_timeout(self, ms):
        if self._pending_wait_error is not None:
            error = self._pending_wait_error
            self._pending_wait_error = None
            raise error
        self.wait_calls.append(ms)
        self._elapsed_ms += ms
        self._deliver_due()

    def _deliver_due(self):
        while self._delivered_count < len(self._schedule) and self._schedule[self._delivered_count][0] <= self._elapsed_ms:
            _, response = self._schedule[self._delivered_count]
            self._delivered_count += 1
            for handler in list(self._handlers.get("response", [])):
                handler(response)
            # 실제 Playwright의 response -> requestfinished(또는 requestfailed)
            # 순서를 그대로 재현한다(같은 tick에서 바로 이어서 전달).
            if getattr(response, "simulate_request_failed", False):
                for handler in list(self._handlers.get("requestfailed", [])):
                    handler(response.request)
            else:
                for handler in list(self._handlers.get("requestfinished", [])):
                    handler(response.request)

    def _schedule_relative(self, delay_ms, response):
        absolute = self._elapsed_ms + delay_ms
        self._schedule.append((absolute, response))
        self._schedule.sort(key=lambda pair: pair[0])
        self._deliver_due()

    def locator(self, selector):
        return self._captcha_selectors.get(selector, FakeLocator(count=0))

    def frame(self, name=None):
        return self._frame


JOB = {
    "region": "서울특별시 강동구",
    "keyword": "카페",
    "query": "서울특별시 강동구 카페",
    "source_city": "서울특별시",
    "source_district": "강동구",
    "source_subregion": "강동구",
    "source_layer": "district",
}


# ---------------------------------------------------------------------------
# 1. limit=20, page1=20 -> page2 클릭 0, rows=20, per_query_limit_reached
# ---------------------------------------------------------------------------


def check_limit20_stops_at_page1(reporter: ValidationReporter) -> None:
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={},
    )
    result = collect_network_query(page, JOB, 20, collected_at="2026-07-16")
    ok = (
        len(result["rows"]) == 20
        and result["pagination_click_count"] == 0
        and result["pagination_page_count"] == 1
        and result["pagination_stop_reason"] == "per_query_limit_reached"
    )
    if ok:
        reporter.pass_("limit=20/page1=20: page2 클릭 0회, rows=20, per_query_limit_reached")
    else:
        reporter.fail(f"limit=20 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 2. limit=30, page1=20/page2=20 -> page2 click=1, rows=30, page3 click=0
# ---------------------------------------------------------------------------


def check_limit30_clicks_page2_only(reporter: ValidationReporter) -> None:
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 30, collected_at="2026-07-16")
    ok = (
        result["pagination_click_count"] == 1
        and result["pagination_page_count"] == 2
        and len(result["rows"]) == 30
        and result["pagination_stop_reason"] == "per_query_limit_reached"
        and page2_spec.get("click_calls", 0) == 1
    )
    if ok:
        reporter.pass_("limit=30/page1=20+page2=20: page2 click=1, rows=30(cap), page3 미시도")
    else:
        reporter.fail(f"limit=30 결과가 예상과 다름: {result}, page2_spec={page2_spec}")


# ---------------------------------------------------------------------------
# 3. limit=100, page1~5 각 20 -> page count=5, click count=4, rows=100, per_query_limit_reached
# ---------------------------------------------------------------------------


def _five_page_click_plan():
    click_plan = {}
    for n in range(2, 6):
        click_plan[str(n)] = {
            "count": 1, "visible": True, "enabled": True,
            "responses_after_click": [(0, _place_response(_page_items(f"p{n}_", 20)))],
        }
    return click_plan


def check_limit100_reaches_five_pages(reporter: ValidationReporter) -> None:
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan=_five_page_click_plan(),
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_page_count"] == 5
        and result["pagination_click_count"] == 4
        and len(result["rows"]) == 100
        and result["pagination_stop_reason"] == "per_query_limit_reached"
    )
    if ok:
        reporter.pass_("limit=100/page1~5 각 20: page_count=5, click_count=4, rows=100, per_query_limit_reached")
    else:
        reporter.fail(f"limit=100 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 4. limit=300, page1~5 각 20 -> rows=100, click count=4, max_page_count_reached
# ---------------------------------------------------------------------------


def check_limit300_stops_at_max_pages_not_300(reporter: ValidationReporter) -> None:
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan=_five_page_click_plan(),
    )
    result = collect_network_query(page, JOB, 300, collected_at="2026-07-16")
    ok = (
        len(result["rows"]) == 100
        and result["pagination_click_count"] == 4
        and result["pagination_page_count"] == 5
        and result["pagination_stop_reason"] == "max_page_count_reached"
    )
    if ok:
        reporter.pass_("limit=300/page1~5 각 20: rows=100(300 미달), click_count=4, max_page_count_reached(300 지원으로 오판하지 않음)")
    else:
        reporter.fail(f"limit=300 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 5. page2 중복 2건 -> 누적 unique=38
# ---------------------------------------------------------------------------


def check_page2_partial_duplicates_accumulate_unique(reporter: ValidationReporter) -> None:
    page1_items = _page_items("p1_", 20)
    page2_items = [("p1_0", "업체p1_0"), ("p1_1", "업체p1_1")] + _page_items("p2_", 18)
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(page2_items))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(page1_items))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["local_unique_count"] == 38
        and result["pagination_click_count"] == 1
        and result["per_page_diagnostics"][1]["duplicate_count"] == 2
        and result["per_page_diagnostics"][1]["new_unique_count"] == 18
    )
    if ok:
        reporter.pass_("page2 중복 2건: 누적 unique=38, per_page_diagnostics duplicate_count=2 확인")
    else:
        reporter.fail(f"page2 중복 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 6. 목표 페이지 번호 버튼 없음 -> 첫 페이지 rows 유지, pagination_exhausted
# ---------------------------------------------------------------------------


def check_missing_next_page_button_preserves_page1(reporter: ValidationReporter) -> None:
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        len(result["rows"]) == 20
        and result["pagination_click_count"] == 0
        and result["pagination_stop_reason"] == "pagination_exhausted"
    )
    if ok:
        reporter.pass_("목표 페이지 버튼 없음: 첫 페이지 rows(20) 유지, pagination_exhausted")
    else:
        reporter.fail(f"버튼 없음 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 7. 목표 페이지 번호 locator가 2개 이상 -> 클릭하지 않음, ambiguous_page_button
# ---------------------------------------------------------------------------


def check_ambiguous_page_button_not_clicked(reporter: ValidationReporter) -> None:
    page2_spec = {"count": 2, "visible": True, "enabled": True}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        len(result["rows"]) == 20
        and page2_spec.get("click_calls", 0) == 0
        and result["pagination_stop_reason"] == "ambiguous_page_button"
    )
    if ok:
        reporter.pass_("페이지 버튼 locator 2개 이상: 클릭하지 않음(click_calls=0), ambiguous_page_button")
    else:
        reporter.fail(f"ambiguous 결과가 예상과 다름: {result}, spec={page2_spec}")


# ---------------------------------------------------------------------------
# 8. 일반 click 오류 -> navigation_error=False, pagination_click_error, 부분 rows 보존
# ---------------------------------------------------------------------------


def check_click_error_preserves_partial_rows(reporter: ValidationReporter) -> None:
    page2_spec = {"count": 1, "visible": True, "enabled": True, "click_error": RuntimeError("click intercepted")}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        len(result["rows"]) == 20
        and result["navigation_error"] is False
        and result["pagination_stop_reason"] == "pagination_click_error"
        and result["pagination_error_message"] != ""
    )
    if ok:
        reporter.pass_("일반 click 오류: navigation_error=False, pagination_click_error, page1 rows(20) 보존")
    else:
        reporter.fail(f"click 오류 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 9. page2 신규 response timeout -> timeout=False, next_page_response_timeout, page1 rows 유지
# ---------------------------------------------------------------------------


def check_next_page_response_timeout_preserves_page1(reporter: ValidationReporter) -> None:
    page2_spec = {"count": 1, "visible": True, "enabled": True, "responses_after_click": []}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["timeout"] is False
        and len(result["rows"]) == 20
        and result["pagination_stop_reason"] == "next_page_response_timeout"
        and page2_spec.get("click_calls", 0) == 1
    )
    if ok:
        reporter.pass_("page2 신규 response timeout: timeout(전역)=False, next_page_response_timeout, page1 rows 유지")
    else:
        reporter.fail(f"response timeout 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 10. page2 CAPTCHA -> 즉시 중단, 재시도 없음, 부분 rows 유지
# ---------------------------------------------------------------------------


def check_captcha_before_next_click_stops_pagination(reporter: ValidationReporter) -> None:
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
        captcha_selectors={"#wtm-captcha-root": FakeLocator(count=1, visible=True, box={"width": 100, "height": 100})},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["active_captcha_detected"] is True
        and len(result["rows"]) == 20
        and page2_spec.get("click_calls", 0) == 0
        and result["pagination_stop_reason"] == "captcha_detected"
    )
    if ok:
        reporter.pass_("page2 진입 전 CAPTCHA: 즉시 중단(클릭 0회), 재시도 없음, page1 rows(20) 유지")
    else:
        reporter.fail(f"CAPTCHA 중단 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 11. page2 HTTP 429 -> 즉시 중단, 재시도 없음, 부분 rows 유지
# ---------------------------------------------------------------------------


def check_429_before_next_click_stops_pagination(reporter: ValidationReporter) -> None:
    non_candidate_429 = FakeResponse("https://map.naver.com/", 429, "document")
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20))), (0, non_candidate_429)],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["status_429_seen"] is True
        and len(result["rows"]) == 20
        and page2_spec.get("click_calls", 0) == 0
        and result["pagination_stop_reason"] == "status_429_seen"
    )
    if ok:
        reporter.pass_("page2 진입 전 HTTP 429: 즉시 중단(클릭 0회), 재시도 없음, page1 rows(20) 유지")
    else:
        reporter.fail(f"429 중단 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 12. 신규 unique 0개 연속 2페이지 -> no_new_unique_rows, 무한 루프 없음
# ---------------------------------------------------------------------------


def check_two_consecutive_zero_unique_pages_stop(reporter: ValidationReporter) -> None:
    page1_items = _page_items("p1_", 20)
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(page1_items))]}
    page3_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(page1_items))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(page1_items))],
        click_plan={"2": page2_spec, "3": page3_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_click_count"] == 2
        and result["pagination_stop_reason"] == "no_new_unique_rows"
        and len(result["rows"]) == 20
        and page2_spec.get("click_calls", 0) == 1
        and page3_spec.get("click_calls", 0) == 1
    )
    if ok:
        reporter.pass_("신규 unique 0개 연속 2페이지(page2/page3 전부 중복): no_new_unique_rows로 안전 종료, 무한 루프 없음")
    else:
        reporter.fail(f"연속 중복 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 13. callback에서 response.json() 호출 없음(2페이지 시나리오)
# ---------------------------------------------------------------------------


def check_response_handler_never_calls_json(reporter: ValidationReporter) -> None:
    p1 = _place_response(_page_items("p1_", 20))
    p2 = _place_response(_page_items("p2_", 20))
    page = FakePaginationPage(
        initial_schedule=[(0, p1)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True, "responses_after_click": [(0, p2)]}},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    # handler가 직접 .json()을 호출했다면 harvest 단계와 합쳐 2회 이상이 됐을 것이다.
    ok = p1.body_call_count == 1 and p2.body_call_count == 1 and result["pagination_click_count"] == 1
    if ok:
        reporter.pass_("response callback 소스는 .json() 호출을 하지 않음(각 응답 body_call_count=1로 확인, 2페이지 시나리오)")
    else:
        reporter.fail(f"json 호출 횟수가 예상과 다름: p1={p1.body_call_count}, p2={p2.body_call_count}, result={result}")


# ---------------------------------------------------------------------------
# 14. candidate response당 JSON parse 정확히 1회(3페이지 시나리오)
# ---------------------------------------------------------------------------


def check_json_parsed_exactly_once_per_candidate_across_pages(reporter: ValidationReporter) -> None:
    p1 = _place_response(_page_items("p1_", 20))
    p2 = _place_response(_page_items("p2_", 20))
    p3 = _place_response(_page_items("p3_", 20))
    page = FakePaginationPage(
        initial_schedule=[(0, p1)],
        click_plan={
            "2": {"count": 1, "visible": True, "enabled": True, "responses_after_click": [(0, p2)]},
            "3": {"count": 1, "visible": True, "enabled": True, "responses_after_click": [(0, p3)]},
        },
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        p1.body_call_count == 1
        and p2.body_call_count == 1
        and p3.body_call_count == 1
        and result["pagination_click_count"] == 2
    )
    if ok:
        reporter.pass_("candidate response 3개(page1~3) 각각 JSON parse 정확히 1회")
    else:
        reporter.fail(f"parse 횟수가 예상과 다름: p1={p1.body_call_count}, p2={p2.body_call_count}, p3={p3.body_call_count}")


# ---------------------------------------------------------------------------
# 15. 정확한 page text 매칭: get_by_role("button", name="2", exact=True) 호출 확인
# ---------------------------------------------------------------------------


def check_page_button_lookup_uses_exact_match(reporter: ValidationReporter) -> None:
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 30, collected_at="2026-07-16")
    calls = page._frame.get_by_role_calls
    ok = (
        len(calls) >= 1
        and calls[0] == ("button", "2", True)
        and result["pagination_click_count"] == 1
    )
    if ok:
        reporter.pass_("페이지 버튼 조회: get_by_role('button', name='2', exact=True) 정확히 호출됨(12·20과 오매칭 방지)")
    else:
        reporter.fail(f"get_by_role 호출 계약이 예상과 다름: calls={calls}, result={result}")


# ---------------------------------------------------------------------------
# 16. force=True 사용 없음
# ---------------------------------------------------------------------------


def check_click_does_not_use_force(reporter: ValidationReporter) -> None:
    """FakePaginationButtonLocator.click()은 force 등 어떤 인자도 받지 않는다 -
    production이 click(force=True)를 호출했다면 TypeError -> pagination_click_error로
    귀결되므로, 정상 성공(per_query_limit_reached) 자체가 force 미사용의 증거다."""
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 30, collected_at="2026-07-16")
    ok = (
        result["pagination_click_count"] == 1
        and result["pagination_stop_reason"] == "per_query_limit_reached"
    )
    if ok:
        reporter.pass_("click()이 인자 없이 정상 성공함(force=True 등 인자를 넘겼다면 TypeError로 실패했을 것)")
    else:
        reporter.fail(f"force 미사용 검증 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 17. URL query parameter 직접 조작 없음
# ---------------------------------------------------------------------------


def check_no_additional_goto_for_pagination(reporter: ValidationReporter) -> None:
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True,
                          "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}},
    )
    result = collect_network_query(page, JOB, 30, collected_at="2026-07-16")
    ok = len(page.goto_calls) == 1 and result["pagination_click_count"] == 1
    if ok:
        reporter.pass_("페이지네이션 중 page.goto() 추가 호출 없음(총 1회 유지, URL query parameter 직접 조작 없음)")
    else:
        reporter.fail(f"goto 호출 횟수가 예상과 다름: goto_calls={page.goto_calls}, result={result}")


# ---------------------------------------------------------------------------
# 18. GraphQL variables 의존 없음(정적 소스 검사)
# ---------------------------------------------------------------------------


def check_no_graphql_variables_in_source(reporter: ValidationReporter) -> None:
    source = inspect.getsource(network_browser_collector)
    forbidden = ["graphql", "operationname", "variables.input.page", "variables[\"input\"]"]
    found = [token for token in forbidden if token in source.lower()]
    if not found:
        reporter.pass_("network_browser_collector.py 소스에 GraphQL operationName/variables 의존 코드 없음")
    else:
        reporter.fail(f"금지된 GraphQL 관련 토큰이 소스에 존재함: {found}")


# ---------------------------------------------------------------------------
# 19. hasNext/nextCursor 의존 없음(정적 소스 검사)
# ---------------------------------------------------------------------------


def check_no_has_next_or_cursor_dependency_in_source(reporter: ValidationReporter) -> None:
    source = inspect.getsource(network_browser_collector)
    forbidden = ["hasnext", "nextcursor"]
    found = [token for token in forbidden if token in source.lower()]
    if not found:
        reporter.pass_("network_browser_collector.py 소스에 hasNext/nextCursor 의존 코드 없음")
    else:
        reporter.fail(f"금지된 hasNext/nextCursor 관련 토큰이 소스에 존재함: {found}")


# ---------------------------------------------------------------------------
# 20. 기존 첫 페이지 단일 response 계약 유지(pagination 시도했지만 버튼 없어 실패해도 동일)
# ---------------------------------------------------------------------------


def check_existing_single_page_contract_preserved(reporter: ValidationReporter) -> None:
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 5)))],
        click_plan={},
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")
    ok = (
        result["candidate_response_count"] == 1
        and result["raw_item_count"] == 5
        and result["local_unique_count"] == 5
        and len(result["rows"]) == 5
        and result["parse_error_count"] == 0
        and result["timeout"] is False
        and result["active_captcha_detected"] is False
        and result["status_429_seen"] is False
        and result["navigation_error"] is False
        and result["pagination_click_count"] == 0
        and result["pagination_page_count"] == 1
    )
    if ok:
        reporter.pass_("기존 첫 페이지 단일 response 계약 유지(candidate=1/raw=5/unique=5/rows=5, pagination 시도했으나 버튼 없어 0회 클릭)")
    else:
        reporter.fail(f"기존 계약 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 21~23(반대 검토 AI 지적 재현/수정 확인). Codex(gpt-5.6-sol) 독립 검토 결과 반영
# ---------------------------------------------------------------------------


def check_captcha_appearing_right_after_click_is_detected(reporter: ValidationReporter) -> None:
    """반대 검토 지적: 클릭 "전" 확인만으로는 클릭 도중/직후 나타난 CAPTCHA를
    놓칠 수 있었다(수정 전에는 loop 상단에서만 확인하고 결과를 캐시해 재확인하지
    않았음). 클릭이 성공하고 응답도 도착했지만 그 직후 CAPTCHA가 나타나는
    경우를 재현한다 - 안전을 위해 그 페이지의 데이터는 버리고(신뢰할 수 없는
    시점의 응답이므로) 이전까지 확보한 rows만 보존해야 한다."""
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))],
        "activates_captcha_after_click": ("#wtm-captcha-root", FakeLocator(count=1, visible=True, box={"width": 100, "height": 100})),
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["active_captcha_detected"] is True
        and result["pagination_stop_reason"] == "captcha_detected"
        and len(result["rows"]) == 20
        and page2_spec.get("click_calls", 0) == 1
    )
    if ok:
        reporter.pass_("클릭 직후(응답 도착 이후) 나타난 CAPTCHA도 감지되어 즉시 중단됨(page2 데이터는 버리고 page1 rows=20만 보존)")
    else:
        reporter.fail(f"클릭 직후 CAPTCHA 감지 결과가 예상과 다름: {result}")


def check_exception_during_next_page_wait_does_not_crash(reporter: ValidationReporter) -> None:
    """반대 검토 지적: 클릭 이후 page.wait_for_timeout()에서 예외(예: "Target
    closed")가 발생하면 수정 전에는 collect_network_query 밖으로 그대로
    전파되어 이미 수집한 page1 rows까지 잃을 위험이 있었다. 이제는 그 예외를
    pagination_click_error로 안전하게 흡수하고 부분 rows를 보존해야 한다."""
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "raise_on_wait_after_click": RuntimeError("Target closed during pagination settle"),
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        len(result["rows"]) == 20
        and result["pagination_stop_reason"] == "pagination_click_error"
        and result["pagination_error_message"] != ""
        and page2_spec.get("click_calls", 0) == 1
    )
    if ok:
        reporter.pass_("클릭 이후 wait_for_timeout() 예외가 collect_network_query 밖으로 전파되지 않고 pagination_click_error로 흡수됨(page1 rows=20 보존)")
    else:
        reporter.fail(f"예외 안전망 결과가 예상과 다름: {result}")


def check_max_page_priority_over_no_new_unique_rows(reporter: ValidationReporter) -> None:
    """반대 검토 지적: 마지막(5번째) 페이지에서 신규 unique가 2연속 0건이 되면
    수정 전에는 no_new_unique_rows가 max_page_count_reached보다 먼저 보고됐다
    (§16 우선순위 위반). page4/page5를 모두 page1과 중복된 응답으로 구성해
    2연속 0건과 "5페이지 도달"이 동시에 발생하는 상황을 재현하고,
    max_page_count_reached가 보고되는지 확인한다."""
    page1_items = _page_items("p1_", 20)
    click_plan = {
        "2": {"count": 1, "visible": True, "enabled": True,
              "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]},
        "3": {"count": 1, "visible": True, "enabled": True,
              "responses_after_click": [(0, _place_response(_page_items("p3_", 20)))]},
        "4": {"count": 1, "visible": True, "enabled": True,
              "responses_after_click": [(0, _place_response(page1_items))]},
        "5": {"count": 1, "visible": True, "enabled": True,
              "responses_after_click": [(0, _place_response(page1_items))]},
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(page1_items))],
        click_plan=click_plan,
    )
    result = collect_network_query(page, JOB, 1000, collected_at="2026-07-16")
    ok = (
        result["pagination_click_count"] == 4
        and result["pagination_page_count"] == 5
        and result["pagination_stop_reason"] == "max_page_count_reached"
    )
    if ok:
        reporter.pass_("5페이지 도달과 2연속 무수확(page4/5)이 동시 발생해도 max_page_count_reached가 우선 보고됨(no_new_unique_rows 아님)")
    else:
        reporter.fail(f"우선순위 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 24~33 (PAGE-300-2B-1-FIX): response 귀속 안전성 보완 - 지연 response 오인,
# harvest gap 누락, DOM identity 확인, click count 정확성을 검증한다.
# ---------------------------------------------------------------------------


def check_late_page1_response_after_click_not_accepted_as_page2(reporter: ValidationReporter) -> None:
    """§1 요구 시나리오: page2 클릭 뒤 "진짜 page2 응답"이 아니라 이전(page1)
    데이터가 지연 도착한 응답만 온 상황을 재현한다. 이 늦은 응답은 실제로
    페이지가 전환되지 않았으므로 DOM class가 클릭 전/후로 그대로다
    (class_before==class_after로 명시). candidate 개수만 늘었다는 이유로
    page2 성공을 인정하면 안 된다."""
    page1_items = _page_items("p1_", 20)
    late_page1_response = _place_response(page1_items)
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "responses_after_click": [(0, late_page1_response)],
        "class_before": "mBN2s", "class_after": "mBN2s",
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(page1_items))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_page_count"] == 1
        and result["pagination_click_count"] == 1
        and result["pagination_stop_reason"] == "page_transition_unverified"
        and len(result["rows"]) == 20
        and result["local_unique_count"] == 20
    )
    if ok:
        reporter.pass_("클릭 뒤 도착한 지연 page1 응답을 page2로 오인하지 않음(DOM 미확인, page_count=1 유지, rows=20 그대로)")
    else:
        reporter.fail(f"지연 응답 오인 방지 결과가 예상과 다름: {result}")


def check_gap_between_harvest_and_click_baseline_not_lost(reporter: ValidationReporter) -> None:
    """§2 요구 시나리오: 최초 settle이 끝난(약 900ms) 뒤, 다음 페이지 버튼을
    클릭하기 전(§4 drain 단계) 사이에 도착한 candidate("orphan")가 유실되지
    않고 이전 페이지 데이터로 정확히 1회만 harvest되는지 확인한다. orphan은
    950ms 시점에 도착하도록 예약해(초기 settle은 900ms에 이미 종료) 최초
    harvest 루프에는 포함되지 않고, 클릭 직전 drain 단계에서만 잡히게 한다."""
    page1_items = _page_items("p1_", 20)
    orphan_response = _place_response(_page_items("orphan_", 5))
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(page1_items)), (950, orphan_response)],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        orphan_response.body_call_count == 1
        and result["local_unique_count"] == 45
        and result["pagination_drain_item_count"] == 5
        and result["pagination_click_count"] == 1
        and result["pagination_page_count"] == 2
    )
    if ok:
        reporter.pass_("최초 harvest~클릭 기준점 사이 도착한 candidate(orphan) 누락 없이 이전 페이지 데이터로 1회 harvest(unique=45)")
    else:
        reporter.fail(f"harvest gap 결과가 예상과 다름: {result}, orphan.body_call_count={orphan_response.body_call_count}")


def check_drain_parse_error_counted_even_when_all_drained_items_fail(reporter: ValidationReporter) -> None:
    """gpt-5.6-sol 독립 검토 지적(PAGE-300-2B-2B) 회귀: 클릭 전 drain
    단계(§4)에서 harvest된 candidate가 전부 파싱 실패(raw_items=[])해도
    parse_error_count에 반영돼야 한다 - 수정 전에는 `_apply_pending_drain`이
    `drain_result["raw_items"]`가 있을 때만 parse_error_count를 누적해,
    drain된 candidate가 전부 실패하면 그 사실이 조용히 사라질 수 있었다."""
    page1_items = _page_items("p1_", 20)
    broken_orphan = FakeResponse(CANDIDATE_URL, 200, "xhr", body=b"not valid json {{{")
    page2_spec = {"count": 1, "visible": True, "enabled": True,
                  "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(page1_items)), (950, broken_orphan)],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["parse_error_count"] == 1
        and result["local_unique_count"] == 40
        and result["pagination_click_count"] == 1
        and result["pagination_page_count"] == 2
    )
    if ok:
        reporter.pass_("drain 중 전부 파싱 실패한 candidate도 parse_error_count에 정상 반영됨(raw_items=[]이어도 누락되지 않음)")
    else:
        reporter.fail(f"drain parse_error_count 결과가 예상과 다름: {result}")


def check_click_success_then_timeout_click_count_is_one(reporter: ValidationReporter) -> None:
    """§3 요구 시나리오: 클릭은 예외 없이 성공했지만 다음 페이지 response가
    끝내 도착하지 않으면(timeout) pagination_click_count=1(클릭 자체는 성공),
    pagination_page_count=1(페이지 확정은 실패)이어야 한다(§7)."""
    page2_spec = {"count": 1, "visible": True, "enabled": True, "responses_after_click": []}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_click_count"] == 1
        and result["pagination_page_count"] == 1
        and result["pagination_stop_reason"] == "next_page_response_timeout"
        and len(result["rows"]) == 20
    )
    if ok:
        reporter.pass_("클릭 성공 + response timeout: pagination_click_count=1, pagination_page_count=1, page1 rows(20) 보존")
    else:
        reporter.fail(f"click_count 결과가 예상과 다름: {result}")


def check_confirmed_page2_identity_via_dom_class_diff(reporter: ValidationReporter) -> None:
    """§4 요구 시나리오: PAGE-300-PoC-B2 실측(page_1 DOM 캡처)과 동일한 형태로
    목표 버튼의 class가 클릭 전("mBN2s")과 클릭 후("mBN2s qxokY")에 실제로
    달라지는 정상 케이스 - 리터럴 "qxokY" 문자열 자체가 아니라 클릭 전/후
    diff로 확인되며, 이 경우에만 page2 성공으로 확정돼야 한다."""
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))],
        "class_before": "mBN2s ", "class_after": "mBN2s qxokY",
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_page_count"] == 2
        and result["pagination_click_count"] == 1
        and len(result["rows"]) == 40
        and result["pagination_unverified_candidate_count"] == 0
    )
    if ok:
        reporter.pass_("실측 DOM class diff(mBN2s -> mBN2s qxokY)로 page2 identity 확정, rows=40 누적")
    else:
        reporter.fail(f"DOM 확정 결과가 예상과 다름: {result}")


def check_unrelated_candidate_response_after_click_not_accepted(reporter: ValidationReporter) -> None:
    """§5 요구 시나리오: 클릭 이후 candidate response가 도착하긴 했지만(JSON은
    파싱 가능) 실제로는 목표 페이지와 무관한 응답인 상황을 DOM 불일치로
    표현한다(response 본문 자체에는 페이지 식별자가 없다는 것이 실측 결론이므로
    - PAGE-300-PoC-B2 - DOM 불일치가 유일하게 실측 가능한 "무관함" 신호다).
    page2 성공으로 인정하면 안 된다."""
    unrelated_response = _place_response(_page_items("other_", 10))
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "responses_after_click": [(0, unrelated_response)],
        "class_before": "mBN2s", "class_after": "mBN2s",
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_page_count"] == 1
        and result["pagination_stop_reason"] == "page_transition_unverified"
        and len(result["rows"]) == 20
        and result["pagination_unverified_candidate_count"] == 1
    )
    if ok:
        reporter.pass_("클릭 이후 무관한 candidate response 도착: page2 성공으로 인정하지 않음(page_count=1 유지)")
    else:
        reporter.fail(f"무관 response 결과가 예상과 다름: {result}")


def check_duplicate_response_object_registered_twice_parsed_once(reporter: ValidationReporter) -> None:
    """§6 요구 시나리오: 브라우저가 동일 response 객체에 대해 'response'
    이벤트를 중복 발생시키는 극단적인 경우(같은 객체가 콜백 목록에 두 번
    등록)에도 object identity로 중복을 걸러 JSON parse가 1회만 일어나고
    rows도 중복되지 않아야 한다."""
    p1 = _place_response(_page_items("p1_", 20))
    page = FakePaginationPage(
        initial_schedule=[(0, p1), (0, p1)],
        click_plan={},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["candidate_response_count"] == 1
        and p1.body_call_count == 1
        and result["raw_item_count"] == 20
        and len(result["rows"]) == 20
    )
    if ok:
        reporter.pass_("동일 response 객체 중복 등록: object identity로 중복 제거(candidate=1, body_call_count=1, rows=20)")
    else:
        reporter.fail(f"중복 등록 결과가 예상과 다름: {result}, body_call_count={p1.body_call_count}")


def check_processed_page1_candidate_not_reused_on_page2(reporter: ValidationReporter) -> None:
    """§7 요구 시나리오: page1 candidate가 page1 harvest 단계에서 이미
    처리됐다면, page2 harvest 단계(range(candidate_count_before_click, ...))에서
    다시 사용되지 않아야 한다 - raw_item_count가 20+20=40이어야 하며 60(page1이
    중복 집계됨)이 되면 안 된다."""
    p1 = _place_response(_page_items("p1_", 20))
    p2 = _place_response(_page_items("p2_", 20))
    page2_spec = {"count": 1, "visible": True, "enabled": True, "responses_after_click": [(0, p2)]}
    page = FakePaginationPage(
        initial_schedule=[(0, p1)],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["raw_item_count"] == 40
        and p1.body_call_count == 1
        and p2.body_call_count == 1
        and result["per_page_diagnostics"][0]["raw_item_count"] == 20
        and result["per_page_diagnostics"][1]["raw_item_count"] == 20
    )
    if ok:
        reporter.pass_("처리 완료된 page1 candidate가 page2 harvest에서 재사용되지 않음(raw_item_count=40, 60 아님)")
    else:
        reporter.fail(f"재사용 방지 결과가 예상과 다름: {result}")


def check_response_identity_completely_unverifiable(reporter: ValidationReporter) -> None:
    """§8 요구 시나리오: DOM class 속성 자체를 읽을 수 없는(locator stale 등)
    상황 - request/response에도 식별자가 없고(PAGE-300-PoC-B2 실측 결론)
    DOM도 읽을 수 없으므로 identity를 판단할 근거가 전혀 없다. 페이지 번호를
    추측해서 진행하면 안 되고 next_page_identity_unverified로 안전 종료해야
    한다."""
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))],
        "get_attribute_error": RuntimeError("element is not attached to the DOM"),
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_stop_reason"] == "next_page_identity_unverified"
        and result["pagination_page_count"] == 1
        and len(result["rows"]) == 20
        and result["pagination_unverified_candidate_count"] == 1
    )
    if ok:
        reporter.pass_("DOM class를 읽을 수 없어 identity 확인 불가: 추측 진행 금지, next_page_identity_unverified, page1 rows(20) 보존")
    else:
        reporter.fail(f"identity 확인 불가 결과가 예상과 다름: {result}")


def check_dom_shows_transition_but_no_response_not_treated_as_success(reporter: ValidationReporter) -> None:
    """§9 요구 시나리오: DOM 근거(class_before/after)는 확정 성공을 가리키도록
    구성했지만 실제로는 target response가 끝내 도착하지 않는 경우 - response가
    없으면 DOM만으로는 page2 수집 성공으로 판정하면 안 된다(next_page_response_timeout이
    최우선으로 보고돼야 하며 identity 확인 로직에는 도달조차 하지 않는다)."""
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "responses_after_click": [],
        "class_before": "mBN2s", "class_after": "mBN2s qxokY",
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_stop_reason"] == "next_page_response_timeout"
        and result["pagination_page_count"] == 1
        and len(result["rows"]) == 20
    )
    if ok:
        reporter.pass_("DOM은 전환된 것처럼 보여도 target response가 없으면 성공으로 판정하지 않음(next_page_response_timeout)")
    else:
        reporter.fail(f"DOM-only 결과가 예상과 다름: {result}")


def check_dom_transition_explicit_mismatch_preserves_partial_rows(reporter: ValidationReporter) -> None:
    """§10 요구 시나리오: target response는 정상 도착했으나 DOM 전환 확인이
    명시적으로 실패(class_before==class_after)하는 경우 - response와 DOM이
    불일치하므로 page_transition_unverified로 안전 종료하고 이미 확보한
    page1 rows만 보존해야 한다(§6: "DOM과 response가 서로 불일치하면
    page_transition_unverified")."""
    page2_spec = {
        "count": 1, "visible": True, "enabled": True,
        "responses_after_click": [(0, _place_response(_page_items("p2_", 20)))],
        "class_before": "mBN2s active-fake", "class_after": "mBN2s active-fake",
    }
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_stop_reason"] == "page_transition_unverified"
        and result["pagination_page_count"] == 1
        and len(result["rows"]) == 20
        and result["pagination_unverified_candidate_count"] == 1
    )
    if ok:
        reporter.pass_("target response는 도착했지만 DOM 전환 확인 명시적 실패: page_transition_unverified, page1 rows(20) 보존")
    else:
        reporter.fail(f"DOM 불일치 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# PAGE-300-2B-2B: PAGE-300-2B-2A 실제 live에서 확인된 page 2 body lifecycle
# 실패(지연된 시점의 response.json()/body() 재호출이 "Response body is
# unavailable"로 실패)를 페이지네이션 경로에서 직접 재현/회귀 고정한다.
# ---------------------------------------------------------------------------


def check_page2_late_body_access_would_fail_but_snapshot_cached(reporter: ValidationReporter) -> None:
    """PAGE-300-2B-2A 핵심 회귀(페이지네이션 경로): page2 response의 body()가
    requestfinished 시점에는 성공하지만 이후(예: adaptive settle 도중) 재호출되면
    "Response body is unavailable" 유사 예외를 던지도록 구성해도, harvest는
    저장된 snapshot bytes만 재사용하므로 page2 데이터가 정상 수집돼야 한다."""
    page2_response = _place_response(_page_items("p2_", 20))
    original_body = page2_response.body
    call_state = {"count": 0}

    def flaky_body():
        call_state["count"] += 1
        if call_state["count"] > 1:
            raise Exception("response.json: Response body is unavailable")
        return original_body()

    page2_response.body = flaky_body
    page2_spec = {"count": 1, "visible": True, "enabled": True, "responses_after_click": [(0, page2_response)]}
    page = FakePaginationPage(
        initial_schedule=[(0, _place_response(_page_items("p1_", 20)))],
        click_plan={"2": page2_spec},
    )
    result = collect_network_query(page, JOB, 100, collected_at="2026-07-16")
    ok = (
        result["pagination_page_count"] == 2
        and len(result["rows"]) == 40
        and call_state["count"] == 1
        and result["parse_error_count"] == 0
    )
    if ok:
        reporter.pass_("PAGE-300-2B-2A 페이지네이션 경로 회귀: page2 body가 requestfinished 시점 1회만 호출되고 harvest는 캐시된 snapshot으로 정상 처리(rows=40)")
    else:
        reporter.fail(f"page2 body 지연 재접근 결과가 예상과 다름: call_count={call_state['count']}, result={result}")


def main() -> int:
    reporter = ValidationReporter()

    check_limit20_stops_at_page1(reporter)
    check_limit30_clicks_page2_only(reporter)
    check_limit100_reaches_five_pages(reporter)
    check_limit300_stops_at_max_pages_not_300(reporter)
    check_page2_partial_duplicates_accumulate_unique(reporter)
    check_missing_next_page_button_preserves_page1(reporter)
    check_ambiguous_page_button_not_clicked(reporter)
    check_click_error_preserves_partial_rows(reporter)
    check_next_page_response_timeout_preserves_page1(reporter)
    check_captcha_before_next_click_stops_pagination(reporter)
    check_429_before_next_click_stops_pagination(reporter)
    check_two_consecutive_zero_unique_pages_stop(reporter)
    check_response_handler_never_calls_json(reporter)
    check_json_parsed_exactly_once_per_candidate_across_pages(reporter)
    check_page_button_lookup_uses_exact_match(reporter)
    check_click_does_not_use_force(reporter)
    check_no_additional_goto_for_pagination(reporter)
    check_no_graphql_variables_in_source(reporter)
    check_no_has_next_or_cursor_dependency_in_source(reporter)
    check_existing_single_page_contract_preserved(reporter)
    check_captcha_appearing_right_after_click_is_detected(reporter)
    check_exception_during_next_page_wait_does_not_crash(reporter)
    check_max_page_priority_over_no_new_unique_rows(reporter)

    check_late_page1_response_after_click_not_accepted_as_page2(reporter)
    check_gap_between_harvest_and_click_baseline_not_lost(reporter)
    check_drain_parse_error_counted_even_when_all_drained_items_fail(reporter)
    check_click_success_then_timeout_click_count_is_one(reporter)
    check_confirmed_page2_identity_via_dom_class_diff(reporter)
    check_unrelated_candidate_response_after_click_not_accepted(reporter)
    check_duplicate_response_object_registered_twice_parsed_once(reporter)
    check_processed_page1_candidate_not_reused_on_page2(reporter)
    check_response_identity_completely_unverifiable(reporter)
    check_dom_shows_transition_but_no_response_not_treated_as_success(reporter)
    check_dom_transition_explicit_mismatch_preserves_partial_rows(reporter)
    check_page2_late_body_access_would_fail_but_snapshot_cached(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
