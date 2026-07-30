from pathlib import Path
import json
import sys
import threading
import time


# 신규 Apollo/GraphQL-first 목록 수집(collect_apollo_first_list_query/
# ApolloFirstListCollector, src/collection/apollo_list_collector.py) 검증용
# standalone 스크립트(실제 Playwright/네이버 접속 없음). 기존
# tests/test_pc_network_pagination.py의 FakePaginationPage/FakeSearchFrame/
# FakePaginationButtonLocator 패턴을 이 파일 안에서 독립적으로 재구현하고,
# 1페이지 window.__APOLLO_STATE__ 폴링을 위한 evaluate()만 추가한다(기존
# 파일 무수정, 파일 간 import 없음 - 기존 관례 그대로).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collection.apollo_list_collector import (
    _APOLLO_FULL_STATE_JS,
    ApolloFirstListCollector,
    collect_apollo_first_list_query,
)
import src.collection.apollo_list_collector as apollo_list_collector


class ValidationReporter:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0

    def pass_(self, message: str) -> None:
        self.pass_count += 1
        print(f"[PASS] {message}")

    def fail(self, message: str) -> None:
        self.fail_count += 1
        print(f"[FAIL] {message}")

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"FINAL: {final}")
        print("====================")


JOB = {
    "region": "서울특별시 강남구",
    "keyword": "카페",
    "query": "서울특별시 강남구 카페",
    "source_city": "서울특별시",
    "source_district": "강남구",
    "source_subregion": "강남구",
    "source_layer": "district",
}


def _op_key(input_obj: dict) -> str:
    return f"placeList({json.dumps({'input': input_obj})})"


def _item_entity(place_id: str, name: str) -> dict:
    return {
        "id": place_id,
        "name": name,
        "category": "카페",
        "visitorReviewsTotal": 10,
        "cafeBlogReviewsTotal": 5,
        "roadAddress": "서울 강남구 테헤란로 1",
        "phone": "02-000-0000",
    }


def _apollo_state(query: str, item_ids_and_names, start: int = 0) -> dict:
    ref_key_of = lambda pid: f"PlaceListBusinessesItem:{pid}:{pid}"
    state = {ref_key_of(pid): _item_entity(pid, name) for pid, name in item_ids_and_names}
    state["ROOT_QUERY"] = {
        _op_key({"query": query, "start": start, "display": 70}): {
            "businesses": {"items": [{"__ref": ref_key_of(pid)} for pid, _ in item_ids_and_names]}
        },
    }
    return state


def _apollo_state_result(state) -> dict:
    return {"available": True, "apollo_state": state, "oversized": False}


class FakeCaptchaLocator:
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
    def __init__(self, resource_type, method="GET"):
        self.resource_type = resource_type
        self.method = method
        self.failure = None
        self._response = None

    def response(self):
        return self._response


class FakeResponse:
    def __init__(self, url, status, resource_type, *, body=None, headers=None):
        self.url = url
        self.status = status
        self.request = FakeRequest(resource_type)
        self.request._response = self
        self._body = body
        self.headers = headers if headers is not None else {}

    def body(self):
        return self._body

    def text(self):
        return (self._body or b"").decode("utf-8")


CANDIDATE_URL = "https://map.naver.com/p/api/search/allSearch?query=x"


def _place_response(item_ids_and_names, url=CANDIDATE_URL):
    items = [{"id": item_id, "name": name} for item_id, name in item_ids_and_names]
    body = json.dumps({"result": {"place": {"list": items}}}).encode("utf-8")
    return FakeResponse(url, 200, "xhr", body=body)


class FakePaginationButtonLocator:
    def __init__(self, spec: dict):
        self._spec = spec

    @property
    def first(self):
        return self

    def count(self):
        return self._spec.get("count", 0)

    def is_visible(self, timeout=None):
        return self._spec.get("visible", True)

    def is_enabled(self):
        return self._spec.get("enabled", True)

    def click(self):
        self._spec["click_calls"] = self._spec.get("click_calls", 0) + 1
        error = self._spec.get("click_error")
        if error is not None:
            raise error


class FakeApolloSearchFrame:
    """searchIframe 흉내 - 1페이지 window.__APOLLO_STATE__ 폴링(evaluate)과
    페이지 번호 버튼 조회(get_by_role) 둘 다 제공한다. apollo_state_sequence는
    evaluate() 호출마다 순서대로 반환되며, 마지막 값은 그 뒤로도 계속 반복된다
    (hard cap까지 폴링해도 끝내 확인되지 않는 상황을 표현하기 위함)."""

    def __init__(self, apollo_state_sequence, click_plan=None, *, name="searchIframe", url="https://map.naver.com/p/search"):
        self._sequence = list(apollo_state_sequence)
        self._click_plan = click_plan or {}
        self.name = name
        self.url = url
        self.evaluated_scripts: list = []
        self.get_by_role_calls: list = []

    def evaluate(self, script):
        self.evaluated_scripts.append(script)
        if len(self._sequence) > 1:
            return self._sequence.pop(0)
        if self._sequence:
            return self._sequence[0]
        return {"available": False, "apollo_state": None, "oversized": False}

    def get_by_role(self, role, name=None, exact=None):
        self.get_by_role_calls.append((role, name, exact))
        spec = self._click_plan.get(name)
        if spec is None:
            return FakePaginationButtonLocator({"count": 0})
        return FakePaginationButtonLocator(spec)


class FakeApolloPage:
    """collect_apollo_first_list_query 전용 fake clock page. wait_for_timeout(ms)
    호출마다 누적 경과시간을 추적하고, 그 경과시간을 기준으로 예약된 response를
    전달한다(FakePaginationPage와 동일한 원리). 페이지 버튼 click() 직후 새
    response를 즉시(지연 0) 전달하도록 click_plan의 responses_after_click을
    바로 harvest에 반영한다."""

    def __init__(self, apollo_state_sequence, click_plan=None, *, captcha_selectors=None, goto_error=None, frame_missing=False):
        self._handlers: dict = {}
        self._captcha_selectors = captcha_selectors or {}
        self._goto_error = goto_error
        self._frame = None if frame_missing else FakeApolloSearchFrame(apollo_state_sequence, click_plan or {})
        self.goto_calls: list = []
        self.wait_calls: list = []
        self._pending_responses: list = []

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

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)
        pending, self._pending_responses = self._pending_responses, []
        for response in pending:
            self._deliver(response)

    def _deliver(self, response):
        if getattr(response, "simulate_request_failed", False):
            for handler in list(self._handlers.get("requestfailed", [])):
                handler(response.request)
        else:
            for handler in list(self._handlers.get("response", [])):
                handler(response)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(response.request)

    def schedule_after_click(self, response):
        self._pending_responses.append(response)

    def locator(self, selector):
        return self._captcha_selectors.get(selector, FakeCaptchaLocator(count=0))

    def frame(self, name=None):
        return self._frame


def check_page1_success_builds_tagged_rows(reporter: ValidationReporter) -> None:
    state = _apollo_state(JOB["query"], [("111", "카페 A"), ("222", "카페 B")])
    page = FakeApolloPage([_apollo_state_result(state)])
    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    row0 = result["rows"][0] if result["rows"] else {}
    ok = (
        result["navigation_error"] is False
        and len(result["rows"]) == 2
        and row0.get("업체명") == "카페 A"
        and row0.get("source_page") == 1
        and row0.get("source_city") == "서울특별시"
        and row0.get("source_district") == "강남구"
    )
    if ok:
        reporter.pass_("1. 1페이지 성공: rows 태깅(source_page/city/district) 정상")
    else:
        reporter.fail(f"1. 1페이지 성공 케이스 실패: {result}")


def check_page1_apollo_never_ready_is_navigation_error(reporter: ValidationReporter) -> None:
    page = FakeApolloPage([{"available": False, "apollo_state": None, "oversized": False}])
    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    ok = (
        result["navigation_error"] is True
        and "ApolloListParseError:" in result["navigation_error_message"]
        and result["rows"] == []
    )
    if ok:
        reporter.pass_("2. Apollo state 끝내 미확인: navigation_error=True + ApolloListParseError 메시지")
    else:
        reporter.fail(f"2. Apollo 미확인 케이스 실패: {result}")


def check_page1_ambiguous_is_navigation_error(reporter: ValidationReporter) -> None:
    # 두 후보가 동점(같은 query/start)이면서 서로 다른(비어있지 않은) 유효
    # place_id 집합을 가져야 진짜 ambiguous 상황이 된다 - 두 후보 모두 items가
    # 비어 있으면(id_set이 둘 다 빈 집합으로 동일) 새 알고리즘은 "동점이지만
    # ID 집합이 같음"으로 보고 임의로 하나를 채택한다(중복 표현으로 간주 -
    # 진짜 모호한 상황이 아님).
    state = {
        "PlaceListBusinessesItem:701:701": _item_entity("701", "카페701"),
        "PlaceListBusinessesItem:702:702": _item_entity("702", "카페702"),
        "ROOT_QUERY": {
            _op_key({"query": JOB["query"], "start": 0, "tag": "a"}): {
                "businesses": {"items": [{"__ref": "PlaceListBusinessesItem:701:701"}]}
            },
            _op_key({"query": JOB["query"], "start": 0, "tag": "b"}): {
                "businesses": {"items": [{"__ref": "PlaceListBusinessesItem:702:702"}]}
            },
        },
    }
    page = FakeApolloPage([_apollo_state_result(state)])
    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    ok = (
        result["navigation_error"] is True
        and "ambiguous_placelist_operation" in result["navigation_error_message"]
    )
    if ok:
        reporter.pass_("3. ambiguous placeList: navigation_error=True + ambiguous_placelist_operation 메시지")
    else:
        reporter.fail(f"3. ambiguous 케이스 실패: {result}")


def check_only_apollo_state_js_evaluated(reporter: ValidationReporter) -> None:
    state = _apollo_state(JOB["query"], [("111", "카페 A")])
    page = FakeApolloPage([_apollo_state_result(state)])
    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    evaluated = page._frame.evaluated_scripts
    ok = (
        result["navigation_error"] is False
        and all(script == _APOLLO_FULL_STATE_JS for script in evaluated)
    )
    if ok:
        reporter.pass_("4. Apollo state 폴링(_APOLLO_FULL_STATE_JS) 외 다른 스크립트는 평가되지 않음")
    else:
        reporter.fail(f"4. 평가된 스크립트 확인 실패: evaluated={evaluated}")


def check_page2_graphql_harvest_and_dedup(reporter: ValidationReporter) -> None:
    state = _apollo_state(JOB["query"], [("111", "카페 A"), ("222", "카페 B")])
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},
    )

    # click() 자체는 FakePaginationButtonLocator에서 즉시 반환되므로, 클릭
    # "직후" 새 candidate response가 도착하는 상황을 흉내내려면 클릭 스펙에
    # 반응을 등록하는 대신, 첫 wait_for_timeout 호출 이전에 pending queue에
    # 넣어 둔다(FakeApolloPage.schedule_after_click).
    original_click = page._frame.get_by_role

    def _patched_get_by_role(role, name=None, exact=None):
        locator = original_click(role, name=name, exact=exact)
        if name == "2":
            original_locator_click = locator.click

            def _click_and_schedule():
                original_locator_click()
                page.schedule_after_click(_place_response([("111", "업체111(중복)"), ("333", "카페 C")]))

            locator.click = _click_and_schedule
        return locator

    page._frame.get_by_role = _patched_get_by_role

    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    place_ids = sorted(row["place_id"] for row in result["rows"])
    ok = (
        result["navigation_error"] is False
        and place_ids == ["111", "222", "333"]
        and result["page_count"] == 2
    )
    if ok:
        reporter.pass_("5. 2페이지 자연 발생 GraphQL harvest + place_id dedup 성공")
    else:
        reporter.fail(f"5. 2페이지 harvest 케이스 실패: {result}, place_ids={place_ids}")


def check_captcha_mid_pagination_stops_with_partial_rows(reporter: ValidationReporter) -> None:
    state = _apollo_state(JOB["query"], [("111", "카페 A")])
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},
        captcha_selectors={"#wtm-captcha-root": FakeCaptchaLocator(count=1, visible=True, box={"width": 100, "height": 100})},
    )
    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    ok = (
        result["navigation_error"] is False
        and result["active_captcha_detected"] is True
        and result["pagination_stop_reason"] == "captcha_detected"
        and len(result["rows"]) == 1
    )
    if ok:
        reporter.pass_("6. CAPTCHA 감지 시 새 페이지 시도 없이 즉시 중단 + 부분 rows 보존")
    else:
        reporter.fail(f"6. CAPTCHA 중단 케이스 실패: {result}")


def check_status_429_stops_with_partial_rows(reporter: ValidationReporter) -> None:
    state = _apollo_state(JOB["query"], [("111", "카페 A")])
    page = FakeApolloPage([_apollo_state_result(state)])
    page.on("response", lambda response: None)  # no-op 등록 순서 확인용(실사용 영향 없음)
    # goto 이후 429 응답을 즉시 흘려보낸다(1페이지 harvest와 무관, 429만 관찰됨).
    original_goto = page.goto

    def _goto_with_429(url, wait_until=None, timeout=None):
        original_goto(url, wait_until=wait_until, timeout=timeout)
        page._deliver(FakeResponse("https://map.naver.com/", 429, "document"))

    page.goto = _goto_with_429
    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    ok = result["navigation_error"] is False and result["status_429_seen"] is True
    if ok:
        reporter.pass_("7. HTTP 429 감지 시 status_429_seen=True로 안전 중단")
    else:
        reporter.fail(f"7. HTTP 429 케이스 실패: {result}")


def check_pagination_exhausted_is_normal_stop(reporter: ValidationReporter) -> None:
    state = _apollo_state(JOB["query"], [("111", "카페 A")])
    page = FakeApolloPage([_apollo_state_result(state)], click_plan={})
    result = collect_apollo_first_list_query(page, JOB, 30, collected_at="2026-07-24")
    ok = (
        result["navigation_error"] is False
        and result["pagination_stop_reason"] == "pagination_exhausted"
        and len(result["rows"]) == 1
    )
    if ok:
        reporter.pass_("8. 다음 페이지 버튼 없음: navigation_error=False(정상 종료)")
    else:
        reporter.fail(f"8. pagination_exhausted 케이스 실패: {result}")


def check_max_pages_reached_is_normal_stop(reporter: ValidationReporter) -> None:
    click_plan = {str(n): {"count": 1, "visible": True, "enabled": True} for n in range(2, 6)}
    state = _apollo_state(JOB["query"], [("p1", "카페1")])
    page = FakeApolloPage([_apollo_state_result(state)], click_plan=click_plan)

    # 각 페이지 버튼 클릭 시 새 candidate 하나씩 흘려보내도록 patch한다.
    original_get_by_role = page._frame.get_by_role

    def _patched(role, name=None, exact=None):
        locator = original_get_by_role(role, name=name, exact=exact)
        if name in click_plan:
            original_locator_click = locator.click

            def _click_and_schedule(n=name):
                original_locator_click()
                page.schedule_after_click(_place_response([(f"p{n}", f"카페{n}")]))

            locator.click = _click_and_schedule
        return locator

    page._frame.get_by_role = _patched
    result = collect_apollo_first_list_query(page, JOB, 300, collected_at="2026-07-24", max_pages=5)
    ok = (
        result["navigation_error"] is False
        and result["pagination_stop_reason"] == "max_page_count_reached"
        and result["page_count"] == 5
    )
    if ok:
        reporter.pass_("9. max_pages 도달: navigation_error=False, page_count=5로 정상 종료")
    else:
        reporter.fail(f"9. max_pages 케이스 실패: {result}")


class FakeLifecyclePage:
    def __init__(self):
        self.close_call_count = 0
        self.close_error = None

    def close(self):
        self.close_call_count += 1
        if self.close_error is not None:
            raise self.close_error


class FakeLifecycleContext:
    def __init__(self, cookies_result=None, cookies_error=None):
        self.new_page_call_count = 0
        self.pages_created: list = []
        self._cookies_result = cookies_result if cookies_result is not None else []
        self._cookies_error = cookies_error

    def new_page(self):
        self.new_page_call_count += 1
        page = FakeLifecyclePage()
        self.pages_created.append(page)
        return page

    def cookies(self):
        if self._cookies_error is not None:
            raise self._cookies_error
        return self._cookies_result


class FakeLifecycleSession:
    def __init__(self, context: FakeLifecycleContext):
        self.context = context
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exit_count += 1
        return False


def check_capture_session_cookies_returns_context_cookies(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext(cookies_result=[{"name": "NID_AUT", "value": "abc"}])
    session = FakeLifecycleSession(context)
    collector = ApolloFirstListCollector(collected_at="2026-07-24", session_factory=lambda: session)
    with collector:
        cookies = collector.capture_session_cookies()
    if cookies == [{"name": "NID_AUT", "value": "abc"}]:
        reporter.pass_("10. capture_session_cookies가 context.cookies()를 그대로 반환")
    else:
        reporter.fail(f"10. capture_session_cookies 결과가 예상과 다름: {cookies}")


def check_capture_session_cookies_returns_empty_on_exception(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext(cookies_error=RuntimeError("context closed"))
    session = FakeLifecycleSession(context)
    collector = ApolloFirstListCollector(collected_at="2026-07-24", session_factory=lambda: session)
    with collector:
        cookies = collector.capture_session_cookies()
    if cookies == []:
        reporter.pass_("11. context.cookies() 예외 시 빈 list 반환(예외를 밖으로 던지지 않음)")
    else:
        reporter.fail(f"11. capture_session_cookies 예외 처리 실패: {cookies}")


def check_collector_opens_and_closes_one_page_per_query(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext()
    session = FakeLifecycleSession(context)
    collector = ApolloFirstListCollector(collected_at="2026-07-24", session_factory=lambda: session)

    calls: list = []
    original = apollo_list_collector.collect_apollo_first_list_query

    def fake_collect(page, job, per_query_limit, *, collected_at, max_pages, pause_event=None, stop_event=None):
        calls.append(page)
        return {"rows": [], "active_captcha_detected": False, "status_429_seen": False,
                "navigation_error": False, "navigation_error_message": "", "page_count": 1,
                "pagination_stop_reason": "pagination_exhausted"}

    apollo_list_collector.collect_apollo_first_list_query = fake_collect
    try:
        with collector:
            collector.collect_query(JOB, 30)
            collector.collect_query(JOB, 30)
    finally:
        apollo_list_collector.collect_apollo_first_list_query = original

    ok = (
        context.new_page_call_count == 2
        and len(calls) == 2
        and all(p.close_call_count == 1 for p in context.pages_created)
    )
    if ok:
        reporter.pass_("12. collect_query 호출마다 새 page 생성 + 정확히 1회 close")
    else:
        reporter.fail(f"12. 생명주기 검증 실패: new_page={context.new_page_call_count}, pages={context.pages_created}")


def check_collector_closes_page_even_when_collect_raises(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext()
    session = FakeLifecycleSession(context)
    collector = ApolloFirstListCollector(collected_at="2026-07-24", session_factory=lambda: session)

    original = apollo_list_collector.collect_apollo_first_list_query

    def fake_collect_raises(page, job, per_query_limit, *, collected_at, max_pages, pause_event=None, stop_event=None):
        raise RuntimeError("boom")

    apollo_list_collector.collect_apollo_first_list_query = fake_collect_raises
    raised = False
    try:
        with collector:
            try:
                collector.collect_query(JOB, 30)
            except RuntimeError:
                raised = True
    finally:
        apollo_list_collector.collect_apollo_first_list_query = original

    ok = raised and len(context.pages_created) == 1 and context.pages_created[0].close_call_count == 1
    if ok:
        reporter.pass_("13. collect_apollo_first_list_query가 예외를 던져도 page.close()는 실행됨")
    else:
        reporter.fail(f"13. 예외 시 page close 보장 실패: raised={raised}, pages={context.pages_created}")


# --------------------------------------------------------------------------
# 지역 Exact 필터(§4/§5, naver_region_policy 배선) - 2026-07-29 Live 감사에서
# 실측된 전남광주통합특별시 서구 치평동 시나리오(치평동 6건 + 쌍촌동/마륵동
# 4건)를 그대로 재현한다. JOB(위)은 source_layer="district"라 이 필터가
# 적용되지 않으므로, 법정동이 선택된 별도 JOB을 이 섹션 전용으로 둔다.
# --------------------------------------------------------------------------
CHIPYEONGDONG_JOB = {
    "region": "전남광주통합특별시 서구 치평동",
    "keyword": "카페",
    "query": "전남광주통합특별시 서구 치평동 카페",
    "source_city": "전남광주통합특별시",
    "source_district": "서구",
    "source_subregion": "치평동",
    "source_layer": "legal_dong",
    "legal_code": "1224012000",
}


def _item_entity_with_address(place_id: str, name: str, road_address: str) -> dict:
    return {
        "id": place_id,
        "name": name,
        "category": "카페",
        "visitorReviewsTotal": 10,
        "cafeBlogReviewsTotal": 5,
        "roadAddress": road_address,
        "phone": "02-000-0000",
    }


def _apollo_state_with_addresses(query: str, items_with_address, start: int = 0) -> dict:
    ref_key_of = lambda pid: f"PlaceListBusinessesItem:{pid}:{pid}"
    state = {
        ref_key_of(pid): _item_entity_with_address(pid, name, addr)
        for pid, name, addr in items_with_address
    }
    state["ROOT_QUERY"] = {
        _op_key({"query": query, "start": start, "display": 70}): {
            "businesses": {"items": [{"__ref": ref_key_of(pid)} for pid, _, _ in items_with_address]}
        },
    }
    return state


_PAGE1_MIXED_ITEMS = [
    ("1", "교집합", "전남광주 서구 쌍촌동 운천로172번길 10 2층"),
    ("2", "우트롱", "전남광주 서구 치평동 운천로 261 어반피크 상무 2층 220호"),
    ("3", "존제의존재", "전남광주 서구 마륵동 상무누리로 5 1층"),
    ("4", "쏘쏘사라다", "전남광주 서구 치평동 치평로 76 1층"),
    ("5", "머든 상무점", "전남광주 서구 치평동 상무중앙로34번길 6 1층"),
    ("6", "부부더상록", "전남광주 서구 치평동 상무중앙로78번길 5-6 102호"),
    ("7", "녹음", "전남광주 서구 쌍촌동 월드컵4강로181번길 34 1층"),
    ("8", "화이트리에", "전남광주 서구 치평동 치평로 106 1층"),
    ("9", "퍼니스", "전남광주 서구 치평동 천변좌하로 192"),
    ("10", "무난", "전남광주 서구 쌍촌동 상무대로902번길 3 1층"),
]  # 치평동(유효) 6건: 2/4/5/6/8/9, 쌍촌동/마륵동(제외) 4건: 1/3/7/10


def check_region_filter_excludes_rows_and_does_not_consume_limit(reporter: ValidationReporter) -> None:
    """15. 제외 row(쌍촌동/마륵동)가 per_query_limit을 소비하지 않는다 - 다음
    페이지가 없어 소진되는 상황에서, 유효 6건만 rows에 남고 4건은
    rejected_rows로 분리 보존되며(주소 원문 포함, Cookie/Authorization/
    서비스키/응답 원문은 없음) per_query_limit=10에 못 미쳐도(6<10) 조기에
    "충분하다"고 잘못 판단하지 않는다(제외 row가 상한을 채우지 못함)."""
    state = _apollo_state_with_addresses(CHIPYEONGDONG_JOB["query"], _PAGE1_MIXED_ITEMS)
    page = FakeApolloPage([_apollo_state_result(state)])  # click_plan 없음 -> 다음 페이지 없음
    result = collect_apollo_first_list_query(page, CHIPYEONGDONG_JOB, 10, collected_at="2026-07-29")

    valid_addresses = [row["주소"] for row in result["rows"]]
    rejected = result["rejected_rows"]
    ok = (
        result["navigation_error"] is False
        and len(result["rows"]) == 6
        and all("치평동" in addr for addr in valid_addresses)
        and len(rejected) == 4
        and all(r["판정_상태"] == "OUT_OF_SCOPE" for r in rejected)
        and all("쌍촌동" in r["주소"] or "마륵동" in r["주소"] for r in rejected)
        and all(r["기대_법정동"] == "치평동" for r in rejected)
        and result["pagination_stop_reason"] == "pagination_exhausted"
    )
    if ok:
        reporter.pass_("15. 지역 필터 제외 row는 per_query_limit을 소비하지 않고 rejected_rows로 분리 보존됨")
    else:
        reporter.fail(f"15. 지역 필터 제외 케이스 실패: rows={result['rows']}, rejected={rejected}, stop={result.get('pagination_stop_reason')}")


def check_region_filter_backfills_valid_rows_from_next_page(reporter: ValidationReporter) -> None:
    """16. 1페이지에서 유효 6건만 확보되면(목표 10건 미달) 다음 페이지로
    이동해 유효 법정동 row로 보충하고, 목표(10건)에 도달하면 그때 멈춘다."""
    state = _apollo_state_with_addresses(CHIPYEONGDONG_JOB["query"], _PAGE1_MIXED_ITEMS)
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},
    )
    page2_items = [
        ("11", "치평동카페11", "전남광주 서구 치평동 치평로 200"),
        ("12", "치평동카페12", "전남광주 서구 치평동 치평로 210"),
        ("13", "치평동카페13", "전남광주 서구 치평동 치평로 220"),
        ("14", "치평동카페14", "전남광주 서구 치평동 치평로 230"),
    ]

    original_get_by_role = page._frame.get_by_role

    def _patched_get_by_role(role, name=None, exact=None):
        locator = original_get_by_role(role, name=name, exact=exact)
        if name == "2":
            original_locator_click = locator.click

            def _click_and_schedule():
                original_locator_click()
                body = json.dumps({
                    "result": {"place": {"list": [
                        {"id": pid, "name": name_, "roadAddress": addr}
                        for pid, name_, addr in page2_items
                    ]}}
                }).encode("utf-8")
                page.schedule_after_click(FakeResponse(CANDIDATE_URL, 200, "xhr", body=body))

            locator.click = _click_and_schedule
        return locator

    page._frame.get_by_role = _patched_get_by_role
    result = collect_apollo_first_list_query(page, CHIPYEONGDONG_JOB, 10, collected_at="2026-07-29")

    ok = (
        result["navigation_error"] is False
        and len(result["rows"]) == 10
        and all("치평동" in row["주소"] for row in result["rows"])
        and len(result["rejected_rows"]) == 4
        and result["pagination_stop_reason"] == "per_query_limit_reached"
        and result["page_count"] == 2
    )
    if ok:
        reporter.pass_("16. 1페이지 유효 6건 부족분을 2페이지 유효 법정동 row로 보충해 목표(10건) 도달")
    else:
        reporter.fail(f"16. 다음 페이지 보충 케이스 실패: rows={len(result['rows'])}, stop={result.get('pagination_stop_reason')}, page_count={result.get('page_count')}")


# --------------------------------------------------------------------------
# NEW-OPENING-1: 새로오픈 전용 목록 수집(collect_apollo_first_list_query
# job["new_opening_only"] 배선) - 2026-07-30 Live 실측(filterOpening="true",
# display=9, 다음 페이지 없음)을 그대로 반영한다.
# --------------------------------------------------------------------------
NEW_OPENING_JOB = {
    "region": "서울특별시 강동구 천호동",
    "keyword": "카페",
    "query": "서울특별시 강동구 천호동 카페",
    "source_city": "서울특별시",
    "source_district": "강동구",
    "source_subregion": "천호동",
    "source_layer": "legal_dong",
    "legal_code": "1174010900",
    "new_opening_only": True,
}


def _item_entity_new_opening(place_id: str, name: str, *, new_opening=None, road_address="서울특별시 강동구 천호동 올림픽로 1") -> dict:
    entity = {
        "id": place_id, "name": name, "category": "카페",
        "visitorReviewsTotal": 10, "cafeBlogReviewsTotal": 5,
        "roadAddress": road_address, "phone": "02-000-0000",
    }
    if new_opening is not None:
        entity["newOpening"] = new_opening
    return entity


def _apollo_state_main_and_new_opening(query: str, main_items, new_opening_items, start: int = 0) -> dict:
    """main_items/new_opening_items: (place_id, name, new_opening) 튜플 목록.
    실측대로 두 operation이 항상 함께 존재하는 page 1 상태를 만든다."""
    ref_key_of = lambda pid: f"PlaceListBusinessesItem:{pid}:{pid}"
    state = {}
    for pid, name, new_opening in {*main_items, *new_opening_items}:
        state[ref_key_of(pid)] = _item_entity_new_opening(pid, name, new_opening=new_opening)
    state["ROOT_QUERY"] = {
        _op_key({"query": query, "start": start, "display": 70}): {
            "businesses": {"items": [{"__ref": ref_key_of(pid)} for pid, _, _ in main_items]}
        },
        _op_key({"query": query, "start": start, "display": 9, "filterOpening": "true"}): {
            "businesses": {"items": [{"__ref": ref_key_of(pid)} for pid, _, _ in new_opening_items]}
        },
    }
    return state


def check_new_opening_only_selects_filter_opening_and_filters_rows(reporter: ValidationReporter) -> None:
    main_items = [("1", "카페1", None), ("2", "카페2", None)]
    new_opening_items = [("10", "새카페1", True), ("11", "새카페2", True), ("12", "가짜새카페", False)]
    state = _apollo_state_main_and_new_opening(NEW_OPENING_JOB["query"], main_items, new_opening_items)
    page = FakeApolloPage([_apollo_state_result(state)])
    result = collect_apollo_first_list_query(page, NEW_OPENING_JOB, 10, collected_at="2026-07-29")

    ok = (
        result["navigation_error"] is False
        and sorted(row["place_id"] for row in result["rows"]) == ["10", "11"]
        and len(result["rejected_rows"]) == 1
        and result["rejected_rows"][0]["place_id"] == "12"
        and result["rejected_rows"][0]["판정_상태"] == "NOT_NEW_OPENING"
    )
    if ok:
        reporter.pass_("새로오픈 ON: filterOpening 전용 operation 선택 + newOpening=false 제외")
    else:
        reporter.fail(f"새로오픈 ON 선택/필터 케이스 실패: {result}")


def check_new_opening_only_never_attempts_pagination(reporter: ValidationReporter) -> None:
    """새로오픈 전용 목록은 목표(10건)에 못 미쳐도(2건만 확보) 다음 페이지
    버튼을 시도하지 않고 정상 종료해야 한다(§6/§7 - 오류도 무한 이동도
    아님)."""
    main_items = [("1", "카페1", None)]
    new_opening_items = [("10", "새카페1", True), ("11", "새카페2", True)]
    state = _apollo_state_main_and_new_opening(NEW_OPENING_JOB["query"], main_items, new_opening_items)
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},  # 페이지 2 버튼이 있어도 시도하면 안 됨
    )
    result = collect_apollo_first_list_query(page, NEW_OPENING_JOB, 10, collected_at="2026-07-29")

    ok = (
        result["navigation_error"] is False
        and len(result["rows"]) == 2
        and result["page_count"] == 1
        and result["pagination_stop_reason"] == "new_opening_single_page_exhausted"
        and page._frame.get_by_role_calls == []  # 페이지 버튼 조회 자체를 시도하지 않음
    )
    if ok:
        reporter.pass_("새로오픈 ON: 목표 미달이어도 다음 페이지를 시도하지 않고 정상 종료(page_count=1)")
    else:
        reporter.fail(f"새로오픈 ON 페이지네이션 미시도 검증 실패: {result}, get_by_role_calls={page._frame.get_by_role_calls}")


def check_new_opening_only_combines_with_region_filter(reporter: ValidationReporter) -> None:
    """새로오픈 ON이어도 지역 Exact 필터(§4)는 그대로 함께 적용돼 지역
    밖 주소는 제외돼야 한다."""
    main_items = [("1", "카페1", None)]
    new_opening_items = [("10", "새카페1", True), ("11", "새카페2", True)]
    state = _apollo_state_main_and_new_opening(NEW_OPENING_JOB["query"], main_items, new_opening_items)
    # place_id=11만 다른 동(성내동) 주소로 바꿔 지역 밖 처리 대상으로 만든다.
    state["PlaceListBusinessesItem:11:11"]["roadAddress"] = "서울특별시 강동구 성내동 다른동로 1"
    page = FakeApolloPage([_apollo_state_result(state)])
    result = collect_apollo_first_list_query(page, NEW_OPENING_JOB, 10, collected_at="2026-07-29")

    ok = (
        result["navigation_error"] is False
        and [row["place_id"] for row in result["rows"]] == ["10"]
        and any(r["place_id"] == "11" and r["판정_상태"] == "OUT_OF_SCOPE" for r in result["rejected_rows"])
    )
    if ok:
        reporter.pass_("새로오픈 ON + 지역 Exact 필터 동시 적용(지역 밖 주소 제외)")
    else:
        reporter.fail(f"새로오픈 ON + 지역 필터 결합 검증 실패: {result}")


def check_new_opening_only_no_candidate_is_navigation_error_not_fallback(reporter: ValidationReporter) -> None:
    """새로오픈 전용 operation이 아예 없으면(예: 이 검색어에 새로오픈 업체가
    전혀 없는 지역) 일반 목록으로 조용히 대체하지 않고 명시적
    navigation_error로 보고해야 한다(§6 금지 사항)."""
    state = _apollo_state(NEW_OPENING_JOB["query"], [("1", "카페1")])  # 메인 목록만 존재, filterOpening 후보 없음
    page = FakeApolloPage([_apollo_state_result(state)])
    result = collect_apollo_first_list_query(page, NEW_OPENING_JOB, 10, collected_at="2026-07-29")

    ok = (
        result["navigation_error"] is True
        and "NewOpeningListParseError:" in result["navigation_error_message"]
        and result["rows"] == []
    )
    if ok:
        reporter.pass_("새로오픈 ON: 전용 operation 미발견 시 일반 목록 fallback 없이 명시적 navigation_error")
    else:
        reporter.fail(f"새로오픈 ON 미발견 케이스 실패: {result}")


def check_new_opening_only_still_detects_captcha(reporter: ValidationReporter) -> None:
    """새로오픈 ON이어도 CAPTCHA 감지는 기존과 동일하게 동작해야 한다
    (페이지네이션 루프를 건너뛰어도 최종 captcha probe는 항상 실행됨)."""
    new_opening_items = [("10", "새카페1", True)]
    state = _apollo_state_main_and_new_opening(NEW_OPENING_JOB["query"], [("1", "카페1", None)], new_opening_items)
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        captcha_selectors={"#wtm-captcha-root": FakeCaptchaLocator(count=1, visible=True, box={"width": 100, "height": 100})},
    )
    result = collect_apollo_first_list_query(page, NEW_OPENING_JOB, 10, collected_at="2026-07-29")

    ok = result["navigation_error"] is False and result["active_captcha_detected"] is True
    if ok:
        reporter.pass_("새로오픈 ON에서도 CAPTCHA 감지가 정상 동작함")
    else:
        reporter.fail(f"새로오픈 ON CAPTCHA 감지 실패: {result}")


# --------------------------------------------------------------------------
# NETWORK-CONTROLS-1: 리뷰 최소·최대 필터(job["review_min"/"review_max"])와
# 일시정지·중지(pause_event/stop_event)를 collect_apollo_first_list_query에
# 연결한 결과를 검증한다. 기준 필드는 총리뷰수(방문자+블로그 합산, 사용자
# 확정 - scratchpad/network_controls_fix/review_filter_contract_audit.md).
# --------------------------------------------------------------------------
REVIEW_JOB = dict(CHIPYEONGDONG_JOB, review_min=50, review_max=200)


def _item_entity_with_reviews(place_id: str, name: str, visitor, blog, road_address="전남광주 서구 치평동 치평로 1") -> dict:
    entity = {
        "id": place_id, "name": name, "category": "카페",
        "roadAddress": road_address, "phone": "02-000-0000",
    }
    if visitor is not None:
        entity["visitorReviewsTotal"] = visitor
    if blog is not None:
        entity["cafeBlogReviewsTotal"] = blog
    return entity


def _apollo_state_with_reviews(query: str, items, start: int = 0) -> dict:
    """items: (place_id, name, visitor, blog) 튜플 목록. visitor/blog가 None이면
    해당 키를 아예 만들지 않아 총리뷰수가 ""(REVIEW_UNKNOWN 대상)이 되게 한다."""
    ref_key_of = lambda pid: f"PlaceListBusinessesItem:{pid}:{pid}"
    state = {ref_key_of(pid): _item_entity_with_reviews(pid, name, visitor, blog) for pid, name, visitor, blog in items}
    state["ROOT_QUERY"] = {
        _op_key({"query": query, "start": start, "display": 70}): {
            "businesses": {"items": [{"__ref": ref_key_of(pid)} for pid, *_ in items]}
        },
    }
    return state


_REVIEW_PAGE1_ITEMS = [
    ("1", "미만1", 10, 5),       # 총 15 - 최소(50) 미만
    ("2", "적합1", 30, 40),      # 총 70 - 범위(50~200) 안
    ("3", "초과1", 150, 100),    # 총 250 - 최대(200) 초과
    ("4", "적합2", 50, 50),      # 총 100 - 범위 안
    ("5", "미확인", None, None),  # 총리뷰수 확인 불가
    ("6", "경계최소", 25, 25),   # 총 50 - 최소 경계값(포함)
]  # 유효 3건(2/4/6), 제외 3건(1 미만, 3 초과, 5 미확인)


def check_review_filter_excludes_rows_and_does_not_consume_limit(reporter: ValidationReporter) -> None:
    state = _apollo_state_with_reviews(REVIEW_JOB["query"], _REVIEW_PAGE1_ITEMS)
    page = FakeApolloPage([_apollo_state_result(state)])  # click_plan 없음 -> 다음 페이지 없음
    result = collect_apollo_first_list_query(page, REVIEW_JOB, 10, collected_at="2026-07-29")

    rejected = result["rejected_rows"]
    rejected_by_status = {r["판정_상태"] for r in rejected}
    stats = result["review_filter_stats"]
    ok = (
        result["navigation_error"] is False
        and len(result["rows"]) == 3
        and {row["업체명"] for row in result["rows"]} == {"적합1", "적합2", "경계최소"}
        and len(rejected) == 3
        and rejected_by_status == {"REVIEW_BELOW_MIN", "REVIEW_ABOVE_MAX", "REVIEW_UNKNOWN"}
        and stats == {"candidate": 6, "accepted": 3, "rejected_by_min": 1, "rejected_by_max": 1, "unknown": 1}
        and result["pagination_stop_reason"] == "pagination_exhausted"
    )
    if ok:
        reporter.pass_("NC-1. 리뷰 필터 제외 row는 per_query_limit을 소비하지 않고 rejected_rows/review_filter_stats로 정확히 분리됨")
    else:
        reporter.fail(f"NC-1. 리뷰 필터 제외 케이스 실패: rows={result['rows']}, rejected={rejected}, stats={stats}")


def check_review_filter_backfills_valid_rows_from_next_page(reporter: ValidationReporter) -> None:
    """1페이지 유효 3건(목표 5건 미달)이면 2페이지로 이동해 유효 row로
    보충한다(§4 요청서 - 제외 후 다음 페이지에서 보충)."""
    state = _apollo_state_with_reviews(REVIEW_JOB["query"], _REVIEW_PAGE1_ITEMS)
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},
    )
    page2_items = [
        ("11", "적합3", 60, 60, "전남광주 서구 치평동 치평로 300"),
        ("12", "미만2", 5, 5, "전남광주 서구 치평동 치평로 310"),
    ]

    original_get_by_role = page._frame.get_by_role

    def _patched_get_by_role(role, name=None, exact=None):
        locator = original_get_by_role(role, name=name, exact=exact)
        if name == "2":
            original_locator_click = locator.click

            def _click_and_schedule():
                original_locator_click()
                body = json.dumps({
                    "result": {"place": {"list": [
                        {"id": pid, "name": name_, "roadAddress": addr, "visitorReviewCount": v, "blogCafeReviewCount": b}
                        for pid, name_, v, b, addr in page2_items
                    ]}}
                }).encode("utf-8")
                page.schedule_after_click(FakeResponse(CANDIDATE_URL, 200, "xhr", body=body))

            locator.click = _click_and_schedule
        return locator

    page._frame.get_by_role = _patched_get_by_role
    result = collect_apollo_first_list_query(page, REVIEW_JOB, 5, collected_at="2026-07-29")

    ok = (
        result["navigation_error"] is False
        and len(result["rows"]) == 4
        and {row["업체명"] for row in result["rows"]} == {"적합1", "적합2", "경계최소", "적합3"}
        and result["page_count"] == 2
    )
    if ok:
        reporter.pass_("NC-2. 리뷰 필터 제외로 부족해진 1페이지 결과를 2페이지 유효 row로 보충함")
    else:
        reporter.fail(f"NC-2. 리뷰 필터 다음 페이지 보충 실패: rows={[r.get('업체명') for r in result['rows']]}, page_count={result.get('page_count')}")


def check_review_filter_combines_with_region_filter(reporter: ValidationReporter) -> None:
    """지역 밖(쌍촌동/마륵동) row는 지역 필터가 먼저 걸러내고, 남은 row에만
    리뷰 필터가 적용돼야 한다(§4 처리 순서)."""
    query = CHIPYEONGDONG_JOB["query"]
    ref_key_of = lambda pid: f"PlaceListBusinessesItem:{pid}:{pid}"
    items = [
        ("1", "지역밖", "전남광주 서구 쌍촌동 운천로 1", 999, 999),   # 지역 밖(리뷰는 충분) - REGION에서 제외
        ("2", "적합", "전남광주 서구 치평동 치평로 1", 60, 60),        # 지역 안 + 리뷰 범위 안 - 유효
        ("3", "지역안리뷰미달", "전남광주 서구 치평동 치평로 2", 1, 1),  # 지역 안이지만 리뷰 미달 - REVIEW에서 제외
    ]
    state = {ref_key_of(pid): _item_entity_with_reviews(pid, name, v, b, road_address=addr) for pid, name, addr, v, b in items}
    state["ROOT_QUERY"] = {
        _op_key({"query": query, "start": 0, "display": 70}): {
            "businesses": {"items": [{"__ref": ref_key_of(pid)} for pid, *_ in items]}
        },
    }
    page = FakeApolloPage([_apollo_state_result(state)])
    review_job = dict(CHIPYEONGDONG_JOB, review_min=50, review_max=200)
    result = collect_apollo_first_list_query(page, review_job, 10, collected_at="2026-07-29")

    rejected_status_by_name = {r["업체명"]: r["판정_상태"] for r in result["rejected_rows"]}
    ok = (
        len(result["rows"]) == 1
        and result["rows"][0]["업체명"] == "적합"
        and rejected_status_by_name.get("지역밖") == "OUT_OF_SCOPE"
        and rejected_status_by_name.get("지역안리뷰미달") == "REVIEW_BELOW_MIN"
    )
    if ok:
        reporter.pass_("NC-3. 지역 필터와 리뷰 필터가 함께 정확히 적용됨(지역 밖은 OUT_OF_SCOPE, 지역 안 리뷰 미달은 REVIEW_BELOW_MIN)")
    else:
        reporter.fail(f"NC-3. 지역+리뷰 필터 조합 실패: rows={result['rows']}, rejected={rejected_status_by_name}")


def check_review_filter_disabled_when_both_bounds_none(reporter: ValidationReporter) -> None:
    """review_min/review_max가 둘 다 None이면(필터 비활성) 기존 동작과
    동일하게 review_filter_stats는 None이고 모든 row가 그대로 통과해야 한다."""
    state = _apollo_state_with_reviews(CHIPYEONGDONG_JOB["query"], _REVIEW_PAGE1_ITEMS)
    page = FakeApolloPage([_apollo_state_result(state)])
    result = collect_apollo_first_list_query(page, CHIPYEONGDONG_JOB, 10, collected_at="2026-07-29")

    ok = len(result["rows"]) == 6 and result["review_filter_stats"] is None
    if ok:
        reporter.pass_("NC-4. review_min/max 미설정 시 리뷰 필터 비활성(전 row 통과, stats=None)")
    else:
        reporter.fail(f"NC-4. 필터 비활성 케이스 실패: rows={len(result['rows'])}, stats={result['review_filter_stats']}")


def check_pause_event_blocks_next_page_until_resumed(reporter: ValidationReporter) -> None:
    """일시정지 중에는 다음 페이지로 넘어가지 않고 대기하다가, 재개되면
    이어서 정상적으로 다음 페이지 결과를 반영해야 한다(§5 요청서)."""
    state = _apollo_state_with_addresses(CHIPYEONGDONG_JOB["query"], _PAGE1_MIXED_ITEMS)
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},
    )
    page2_items = [
        ("11", "치평동카페11", "전남광주 서구 치평동 치평로 200"),
        ("12", "치평동카페12", "전남광주 서구 치평동 치평로 210"),
        ("13", "치평동카페13", "전남광주 서구 치평동 치평로 220"),
        ("14", "치평동카페14", "전남광주 서구 치평동 치평로 230"),
    ]
    original_get_by_role = page._frame.get_by_role

    def _patched_get_by_role(role, name=None, exact=None):
        locator = original_get_by_role(role, name=name, exact=exact)
        if name == "2":
            original_locator_click = locator.click

            def _click_and_schedule():
                original_locator_click()
                body = json.dumps({
                    "result": {"place": {"list": [
                        {"id": pid, "name": name_, "roadAddress": addr}
                        for pid, name_, addr in page2_items
                    ]}}
                }).encode("utf-8")
                page.schedule_after_click(FakeResponse(CANDIDATE_URL, 200, "xhr", body=body))

            locator.click = _click_and_schedule
        return locator

    page._frame.get_by_role = _patched_get_by_role

    pause_event = threading.Event()
    stop_event = threading.Event()
    pause_event.set()

    def _resume_after_delay():
        time.sleep(0.3)
        pause_event.clear()

    threading.Thread(target=_resume_after_delay, daemon=True).start()
    started = time.monotonic()
    result = collect_apollo_first_list_query(
        page, CHIPYEONGDONG_JOB, 10, collected_at="2026-07-29",
        pause_event=pause_event, stop_event=stop_event,
    )
    elapsed = time.monotonic() - started

    ok = elapsed >= 0.2 and len(result["rows"]) == 10 and result["page_count"] == 2
    if ok:
        reporter.pass_("NC-5. 일시정지 중 다음 페이지로 넘어가지 않고 대기하다가 재개 후 정상 이어짐")
    else:
        reporter.fail(f"NC-5. 일시정지 대기 실패: elapsed={elapsed:.2f}s, rows={len(result['rows'])}, page_count={result.get('page_count')}")


def check_stop_event_aborts_pagination_before_next_page(reporter: ValidationReporter) -> None:
    """중지 중이면(일시정지 아님) 다음 페이지로 아예 넘어가지 않고 1페이지
    결과만 보존한 채 정상 종료해야 한다(§5 요청서 - stop이 pause보다 우선)."""
    state = _apollo_state_with_addresses(CHIPYEONGDONG_JOB["query"], _PAGE1_MIXED_ITEMS)
    page = FakeApolloPage(
        [_apollo_state_result(state)],
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},
    )
    pause_event = threading.Event()
    stop_event = threading.Event()
    stop_event.set()

    result = collect_apollo_first_list_query(
        page, CHIPYEONGDONG_JOB, 10, collected_at="2026-07-29",
        pause_event=pause_event, stop_event=stop_event,
    )

    ok = (
        len(result["rows"]) == 6
        and result["pagination_stop_reason"] == "user_stopped"
        and page._frame.get_by_role_calls == []
    )
    if ok:
        reporter.pass_("NC-6. 중지 시 다음 페이지 이동을 시도하지 않고 확보된 1페이지 결과로 정상 종료")
    else:
        reporter.fail(f"NC-6. 중지 케이스 실패: rows={len(result['rows'])}, stop={result.get('pagination_stop_reason')}, calls={page._frame.get_by_role_calls}")


def check_default_session_factory_used_when_not_injected(reporter: ValidationReporter) -> None:
    """session_factory를 주입하지 않으면 ApolloFirstListCollector가
    apollo_list_collector._default_session_factory를 그대로 쓴다(production
    배선) - 이전 대청소에서 이 함수를 실수로 삭제했다가 복구한 이력이 있어
    이 기본 배선 자체를 회귀 가드로 남긴다."""
    collector = ApolloFirstListCollector(collected_at="2026-07-30")
    if collector._session_factory is apollo_list_collector._default_session_factory:
        reporter.pass_("session_factory 미주입 시 _default_session_factory가 기본값으로 쓰임")
    else:
        reporter.fail(f"기본 session_factory 배선 이상: {collector._session_factory!r}")


def check_default_session_factory_builds_session_without_launching_browser(reporter: ValidationReporter) -> None:
    """_default_session_factory()는 세션 객체를 생성만 할 뿐(__enter__ 호출
    전까지) 실제 브라우저를 띄우지 않는다(함수 자체의 계약) - 반환 객체가
    NativeCdpBrowserSession 계약(context manager + collect_query 상위에서
    쓰는 __enter__/__exit__)을 만족하는지만 라이브 브라우저 없이 확인한다."""
    session = apollo_list_collector._default_session_factory()
    ok = hasattr(session, "__enter__") and hasattr(session, "__exit__") and type(session).__name__ in (
        "NativeCdpBrowserSession", "BrowserSession",
    )
    if ok:
        reporter.pass_(f"_default_session_factory(): 브라우저를 실행하지 않고 세션 객체({type(session).__name__})만 생성")
    else:
        reporter.fail(f"_default_session_factory() 반환값 이상: {session!r}")


def main() -> bool:
    reporter = ValidationReporter()
    checks = [
        check_page1_success_builds_tagged_rows,
        check_page1_apollo_never_ready_is_navigation_error,
        check_page1_ambiguous_is_navigation_error,
        check_only_apollo_state_js_evaluated,
        check_page2_graphql_harvest_and_dedup,
        check_captcha_mid_pagination_stops_with_partial_rows,
        check_status_429_stops_with_partial_rows,
        check_pagination_exhausted_is_normal_stop,
        check_max_pages_reached_is_normal_stop,
        check_capture_session_cookies_returns_context_cookies,
        check_capture_session_cookies_returns_empty_on_exception,
        check_collector_opens_and_closes_one_page_per_query,
        check_collector_closes_page_even_when_collect_raises,
        check_region_filter_excludes_rows_and_does_not_consume_limit,
        check_region_filter_backfills_valid_rows_from_next_page,
        check_new_opening_only_selects_filter_opening_and_filters_rows,
        check_new_opening_only_never_attempts_pagination,
        check_new_opening_only_combines_with_region_filter,
        check_new_opening_only_no_candidate_is_navigation_error_not_fallback,
        check_new_opening_only_still_detects_captcha,
        check_review_filter_excludes_rows_and_does_not_consume_limit,
        check_review_filter_backfills_valid_rows_from_next_page,
        check_review_filter_combines_with_region_filter,
        check_review_filter_disabled_when_both_bounds_none,
        check_pause_event_blocks_next_page_until_resumed,
        check_stop_event_aborts_pagination_before_next_page,
        check_default_session_factory_used_when_not_injected,
        check_default_session_factory_builds_session_without_launching_browser,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return reporter.fail_count == 0


def test_standalone_suite():
    assert main() is True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
