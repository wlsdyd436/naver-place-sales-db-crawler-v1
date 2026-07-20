from pathlib import Path
import json
import sys


# ARCH-300C WIRE-2A: src/pc/network_browser_collector.py 검증용 standalone
# 스크립트(live/Playwright 없음, FakePage/FakeResponse 기반). collect_network_query는
# page를 전달받기만 하므로, 실제 브라우저 없이 FakePage 주입만으로 검증할 수 있다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import src.pc.browser_session as browser_session_module
import src.pc.network_browser_collector as network_browser_collector
from src.pc.network_browser_collector import NetworkBrowserCollector, collect_network_query


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
    """PAGE-300-2B-2B: requestfinished/requestfailed 핸들러가 받는 request 객체를
    흉내낸다. response와 양방향으로 참조해(response.request/request.response())
    id(request) 기반 candidate 역참조를 재현할 수 있게 한다."""

    def __init__(self, resource_type, method="GET"):
        self.resource_type = resource_type
        self.method = method
        self.failure = None
        self._response = None

    def response(self):
        return self._response


class FakeResponse:
    """PAGE-300-2B-2B: `.json()` 대신 `.body()`(bytes)/`.text()`(str)로 candidate
    body를 노출한다 - production이 requestfinished 시점에만 이 메서드를
    호출하고 harvest에서는 저장된 snapshot bytes만 쓰는지 검증하기 위해
    `body_call_count`로 호출 횟수를 계측한다."""

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


class FakePage:
    def __init__(self, *, responses=None, goto_error=None, captcha_selectors=None):
        self._handlers: dict = {}
        self._responses = responses or []
        self._goto_error = goto_error
        self._captcha_selectors = captcha_selectors or {}
        self.on_call_count = 0
        self.off_call_count = 0
        self.goto_calls: list = []
        self.wait_calls: list = []

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)
        self.on_call_count += 1

    def off(self, event, handler):
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)
        self.off_call_count += 1

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        if self._goto_error is not None:
            raise self._goto_error
        for response in self._responses:
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

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)

    def locator(self, selector):
        return self._captcha_selectors.get(selector, FakeLocator(count=0))


JOB = {
    "region": "서울특별시 강동구 천호동",
    "keyword": "카페",
    "query": "서울특별시 강동구 천호동 카페",
    "source_city": "서울특별시",
    "source_district": "강동구",
    "source_subregion": "천호동",
    "source_layer": "legal_dong",
}

CANDIDATE_URL = "https://map.naver.com/p/api/search/allSearch?query=x"


def _place_response(item_ids_and_names, url=CANDIDATE_URL):
    items = [{"id": item_id, "name": name} for item_id, name in item_ids_and_names]
    body = json.dumps({"result": {"place": {"list": items}}}).encode("utf-8")
    return FakeResponse(url, 200, "xhr", body=body)


def check_listener_registered_once_and_removed(reporter: ValidationReporter) -> None:
    """PAGE-300-2B-2B: response/requestfinished/requestfailed 3개 리스너를
    각각 정확히 1회 등록·해제해야 한다(합계 on=3/off=3)."""
    page = FakePage(responses=[_place_response([("p1", "업체1")])])
    collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    remaining = sum(len(page._handlers.get(evt, [])) for evt in ("response", "requestfinished", "requestfailed"))
    if page.on_call_count == 3 and page.off_call_count == 3 and remaining == 0:
        reporter.pass_("listener 등록·해제: response/requestfinished/requestfailed 각각 on 1회·off 1회, 잔여 handler 없음")
    else:
        reporter.fail(
            f"listener 등록·해제 결과가 예상과 다름: on={page.on_call_count}, off={page.off_call_count}, "
            f"remaining={remaining}"
        )


def check_multiple_candidate_responses_concat(reporter: ValidationReporter) -> None:
    page = FakePage(
        responses=[
            _place_response([("p1", "업체1")]),
            _place_response([("p2", "업체2")]),
        ]
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    ids = sorted(row["place_id"] for row in result["rows"])
    if ids == ["p1", "p2"] and result["candidate_response_count"] == 2:
        reporter.pass_("복수 candidate concat: 응답 2개의 목록이 합쳐짐")
    else:
        reporter.fail(f"복수 candidate concat 결과가 예상과 다름: {result}")


def check_local_dedup_before_limit(reporter: ValidationReporter) -> None:
    page = FakePage(
        responses=[
            _place_response([("dup1", "업체dup")]),
            _place_response([("dup1", "업체dup")]),
        ]
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["local_unique_count"] == 1 and len(result["rows"]) == 1:
        reporter.pass_("local dedup: 후보 응답 간 같은 place_id는 중복 제거 후 1건만 남음")
    else:
        reporter.fail(f"local dedup 결과가 예상과 다름: {result}")


def check_per_query_limit_caps_after_dedup(reporter: ValidationReporter) -> None:
    items = [(f"p{i}", f"업체{i}") for i in range(5)]
    page = FakePage(responses=[_place_response(items)])
    result = collect_network_query(page, JOB, 3, collected_at="2026-07-14")
    if result["local_unique_count"] == 5 and len(result["rows"]) == 3:
        reporter.pass_("per_query_limit: local dedup 후 5건 중 3건으로 정확히 cap됨")
    else:
        reporter.fail(f"per_query_limit 결과가 예상과 다름: {result}")


def check_active_captcha_detected(reporter: ValidationReporter) -> None:
    page = FakePage(
        responses=[],
        captcha_selectors={"#wtm-captcha-root": FakeLocator(count=1, visible=True, box={"width": 100, "height": 100})},
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["active_captcha_detected"] is True:
        reporter.pass_("active CAPTCHA: marker visible + 면적>0이면 active_captcha_detected=True")
    else:
        reporter.fail(f"active CAPTCHA 결과가 예상과 다름: {result}")


def check_passive_marker_not_active(reporter: ValidationReporter) -> None:
    page = FakePage(
        responses=[],
        captcha_selectors={"#wtm-captcha-root": FakeLocator(count=1, visible=False, box={"width": 0, "height": 0})},
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["active_captcha_detected"] is False:
        reporter.pass_("passive marker: DOM에 존재하지만 hidden이면 active_captcha_detected=False")
    else:
        reporter.fail(f"passive marker 결과가 예상과 다름: {result}")


def check_status_429_seen_on_non_candidate_response(reporter: ValidationReporter) -> None:
    page = FakePage(
        responses=[FakeResponse("https://map.naver.com/", 429, "document")],
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["status_429_seen"] is True and result["candidate_response_count"] == 0:
        reporter.pass_("HTTP 429: 후보 URL이 아닌 응답에서도 status_429_seen=True로 감지됨")
    else:
        reporter.fail(f"HTTP 429 결과가 예상과 다름: {result}")


def check_goto_timeout(reporter: ValidationReporter) -> None:
    """실제 Playwright TimeoutError만 timeout=True로 분류되어야 한다(WIRE-2A-B)."""
    page = FakePage(
        responses=[_place_response([("p1", "업체1")])],
        goto_error=PlaywrightTimeoutError("Timeout 40000ms exceeded"),
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        result["timeout"] is True
        and result["navigation_error"] is False
        and result["rows"] == []
        and result["active_captcha_detected"] is False
    ):
        reporter.pass_("goto timeout(PlaywrightTimeoutError): timeout=True, navigation_error=False, rows=[], CAPTCHA 아님")
    else:
        reporter.fail(f"goto timeout 결과가 예상과 다름: {result}")


def check_goto_navigation_error_is_not_timeout(reporter: ValidationReporter) -> None:
    """TimeoutError가 아닌 navigation 예외(Target closed 등)는 timeout으로 위장하면 안 된다(WIRE-2A-B)."""
    page = FakePage(
        responses=[_place_response([("p1", "업체1")])],
        goto_error=Exception("Target page, context or browser has been closed"),
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        result["timeout"] is False
        and result["navigation_error"] is True
        and result["navigation_error_message"] != ""
        and result["rows"] == []
        and result["active_captcha_detected"] is False
        and result["status_429_seen"] is False
    ):
        reporter.pass_("navigation error(Target closed 등): timeout=False, navigation_error=True, navigation_error_message 비어있지 않음, CAPTCHA/429로 오분류 안 됨")
    else:
        reporter.fail(f"navigation error 결과가 예상과 다름: {result}")


def check_no_candidate_responses_is_timeout(reporter: ValidationReporter) -> None:
    page = FakePage(responses=[])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["timeout"] is True and result["rows"] == [] and result["candidate_response_count"] == 0:
        reporter.pass_("candidate 응답 0개: settle 종료까지 후보가 없으면 timeout=True")
    else:
        reporter.fail(f"candidate 응답 0개 결과가 예상과 다름: {result}")


def check_zero_search_results_is_not_timeout(reporter: ValidationReporter) -> None:
    page = FakePage(responses=[_place_response([])])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["timeout"] is False and result["rows"] == [] and result["candidate_response_count"] == 1:
        reporter.pass_("검색 결과 0건: candidate 응답은 있으나 items=0이면 timeout=False, rows=[]")
    else:
        reporter.fail(f"검색 결과 0건 결과가 예상과 다름: {result}")


def check_parse_error_does_not_crash(reporter: ValidationReporter) -> None:
    """PAGE-300-2B-2B: body snapshot 자체는 성공하지만(정상 candidate) 내용이
    깨진 JSON이면 harvest 단계의 json.loads가 실패해 parse_error_count만
    증가하고 나머지 후보는 계속 처리돼야 한다."""
    broken = FakeResponse(CANDIDATE_URL, 200, "xhr", body=b"not valid json {{{")
    ok = _place_response([("p1", "업체1")])
    page = FakePage(responses=[broken, ok])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["parse_error_count"] == 1 and len(result["rows"]) == 1 and result["rows"][0]["place_id"] == "p1":
        reporter.pass_("parse error: 깨진 JSON body는 parse_error_count만 증가시키고 나머지 후보는 계속 처리됨")
    else:
        reporter.fail(f"parse error 결과가 예상과 다름: {result}")


def check_source_meta_preserved_on_rows(reporter: ValidationReporter) -> None:
    page = FakePage(responses=[_place_response([("p1", "업체1")])])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    row = result["rows"][0]
    if (
        row["source_city"] == "서울특별시"
        and row["source_district"] == "강동구"
        and row["source_subregion"] == "천호동"
        and row["source_layer"] == "legal_dong"
        and row["source_query"] == JOB["query"]
    ):
        reporter.pass_("source_* 메타: job의 source_city/district/subregion/layer/query가 row에 유지됨")
    else:
        reporter.fail(f"source_* 메타 결과가 예상과 다름: {row}")


# ---------------------------------------------------------------------------
# PAGE-300-2B-2B: candidate response body snapshot(requestfinished 시점 즉시
# bytes 확보) 관련 신규 케이스. PAGE-300-2B-2A 실측 원인(지연된 시점의
# response.json()/body() 재호출이 "Response body is unavailable"로 실패)을
# 직접 재현/회귀 고정한다.
# ---------------------------------------------------------------------------


def check_late_body_access_would_fail_but_snapshot_cached(reporter: ValidationReporter) -> None:
    """PAGE-300-2B-2A 핵심 회귀: body()가 최초 호출(requestfinished 시점)에는
    성공하지만 이후 재호출되면 예외를 던지도록 구성해도, harvest는 저장된
    snapshot bytes만 재사용하므로 정상 파싱돼야 한다(body() 재호출 자체가
    없어야 함 - call_state["count"]==1로 확인)."""
    response = _place_response([("p1", "업체1")])
    original_body = response.body
    call_state = {"count": 0}

    def flaky_body():
        call_state["count"] += 1
        if call_state["count"] > 1:
            raise Exception("response.json: Response body is unavailable")
        return original_body()

    response.body = flaky_body
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "p1"
        and call_state["count"] == 1
        and result["parse_error_count"] == 0
    ):
        reporter.pass_("body 지연 재접근 시뮬레이션(PAGE-300-2B-2A 재현): snapshot이 requestfinished 시점 1회만 호출되고 harvest는 캐시된 bytes로 정상 파싱됨")
    else:
        reporter.fail(f"body 지연 재접근 결과가 예상과 다름: call_count={call_state['count']}, result={result}")


def check_requestfinished_snapshot_failure_records_parse_error(reporter: ValidationReporter) -> None:
    """requestfinished 시점에 body()/text() 둘 다 실패하면 해당 candidate는
    parse_error로 안전하게 처리되고(예외 유출 없음) 나머지 후보는 정상 처리돼야
    한다."""
    broken = FakeResponse(CANDIDATE_URL, 200, "xhr", body_error=Exception("Response body is unavailable"))
    ok = _place_response([("p1", "업체1")])
    page = FakePage(responses=[broken, ok])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        result["parse_error_count"] == 1
        and result["body_snapshot_error_count"] == 1
        and result["body_snapshot_success_count"] == 1
        and len(result["rows"]) == 1
    ):
        reporter.pass_("requestfinished snapshot 실패: parse_error_count/body_snapshot_error_count=1, 나머지 candidate 정상 처리")
    else:
        reporter.fail(f"snapshot 실패 결과가 예상과 다름: {result}")


def check_requestfailed_marks_candidate_failed_partial_rows_preserved(reporter: ValidationReporter) -> None:
    """requestfailed 이벤트가 오면 해당 candidate는 body()를 아예 호출하지
    않고 실패로 기록하며, 이미 확보한 다른 candidate의 rows는 보존돼야 한다."""
    failed = FakeResponse(CANDIDATE_URL, 200, "xhr", body=b"unused", simulate_request_failed=True)
    failed.request.failure = "net::ERR_ABORTED"
    ok = _place_response([("p1", "업체1")])
    page = FakePage(responses=[ok, failed])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "p1"
        and result["parse_error_count"] == 1
        and result["body_snapshot_error_count"] == 1
        and failed.body_call_count == 0
    ):
        reporter.pass_("requestfailed 안전 처리: body() 미호출, 실패로 기록, 정상 candidate의 rows 보존됨(재시도 없음)")
    else:
        reporter.fail(f"requestfailed 결과가 예상과 다름: body_call_count={failed.body_call_count}, result={result}")


def check_requestfailed_without_prior_response_is_still_counted(reporter: ValidationReporter) -> None:
    """gpt-5.6-sol 2차 독립 검토 지적 회귀: 실제 네트워크 레벨 실패(response
    이벤트가 한 번도 발생하지 않고 requestfailed만 발생)의 표준 경로에서도,
    URL/resource_type 기준으로 candidate였던 request라면 실패로 집계돼야
    한다 - 다른 candidate가 정상 성공해 per_query_limit에 도달해도 이 실패가
    parse_error_count/body_snapshot_error_count 어디에도 반영되지 않고
    조용히 사라지면 거짓 성공처럼 보일 위험이 있었다."""
    never_responded_request = FakeRequest("xhr")
    never_responded_request.url = CANDIDATE_URL
    never_responded_request.failure = "net::ERR_CONNECTION_RESET"

    class RequestFailedOnlyPage(FakePage):
        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            ok_response = _place_response([("p1", "업체1")])
            for handler in list(self._handlers.get("response", [])):
                handler(ok_response)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(ok_response.request)
            # response 이벤트 없이 requestfailed만 발생(실제 네트워크 실패의
            # 표준 경로 - 이 request는 ctx.request_id_to_candidate에 등록될
            # 기회가 전혀 없었다).
            for handler in list(self._handlers.get("requestfailed", [])):
                handler(never_responded_request)

    page = RequestFailedOnlyPage()
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        result["candidate_response_count"] == 2
        and result["parse_error_count"] == 1
        and result["body_snapshot_error_count"] == 1
        and len(result["rows"]) == 1
    ):
        reporter.pass_("response 이벤트 없이 requestfailed만 발생한 candidate도 실패로 집계됨(정상 candidate와 공존해도 누락되지 않음)")
    else:
        reporter.fail(f"response 없는 requestfailed 결과가 예상과 다름: {result}")


def check_candidate_body_too_large_is_rejected_safely(reporter: ValidationReporter) -> None:
    """_MAX_CANDIDATE_BODY_BYTES를 초과하는 candidate body는 저장하지 않고
    BodyTooLarge로 안전하게 실패 처리해야 한다(나머지 candidate는 영향 없음)."""
    huge_body = b"[" + b"1" * (network_browser_collector._MAX_CANDIDATE_BODY_BYTES + 1) + b"]"
    huge = FakeResponse(CANDIDATE_URL, 200, "xhr", body=huge_body)
    ok = _place_response([("p1", "업체1")])
    page = FakePage(responses=[huge, ok])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        result["parse_error_count"] == 1
        and result["body_snapshot_error_count"] == 1
        and len(result["rows"]) == 1
    ):
        reporter.pass_("candidate body 크기 상한 초과: BodyTooLarge로 안전 실패, 나머지 candidate 정상 처리")
    else:
        reporter.fail(f"body 크기 상한 결과가 예상과 다름: {result}")


def check_content_length_header_rejects_before_body_call(reporter: ValidationReporter) -> None:
    """gpt-5.6-sol 독립 검토 지적 반영: content-length 헤더가 상한을 넘으면
    body()/text()를 아예 호출하지 않고(전체 body를 메모리에 만들지 않고)
    BodyTooLarge로 조기에 거절해야 한다."""
    huge = FakeResponse(
        CANDIDATE_URL, 200, "xhr",
        headers={"content-length": str(network_browser_collector._MAX_CANDIDATE_BODY_BYTES + 1)},
    )
    ok = _place_response([("p1", "업체1")])
    page = FakePage(responses=[huge, ok])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        result["body_snapshot_error_count"] == 1
        and result["parse_error_count"] == 1
        and huge.body_call_count == 0
        and len(result["rows"]) == 1
    ):
        reporter.pass_("content-length 헤더 상한 초과: body() 호출 없이 조기에 BodyTooLarge로 거절됨")
    else:
        reporter.fail(f"content-length 조기 거절 결과가 예상과 다름: body_call_count={huge.body_call_count}, result={result}")


def check_duplicate_requestfinished_event_snapshots_once(reporter: ValidationReporter) -> None:
    """같은 request에 대해 requestfinished가 중복으로 발생해도(이론상 발생하지
    않아야 하지만) body snapshot은 1회만 수행돼야 한다(idempotent)."""
    response = _place_response([("p1", "업체1")])

    class DuplicateFinishPage(FakePage):
        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            for handler in list(self._handlers.get("response", [])):
                handler(response)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(response.request)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(response.request)  # 중복 이벤트

    page = DuplicateFinishPage()
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if response.body_call_count == 1 and len(result["rows"]) == 1:
        reporter.pass_("동일 requestfinished 이벤트 2회: body snapshot 1회만 수행됨(idempotent)")
    else:
        reporter.fail(f"중복 requestfinished 결과가 예상과 다름: body_call_count={response.body_call_count}, result={result}")


def check_no_raw_body_leak_in_result(reporter: ValidationReporter) -> None:
    """반환 dict의 rows/per_page_diagnostics를 제외한 나머지 값 어디에도 raw
    body 원문(파싱된 업체명 등)이 그대로 노출되면 안 된다 - size/타입/예외
    유형만 진단으로 허용한다."""
    marker = "고유업체마커XYZ"
    response = _place_response([(marker, marker)])
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    leaked = any(
        marker in str(value)
        for key, value in result.items()
        if key not in ("rows", "per_page_diagnostics")
    )
    if not leaked:
        reporter.pass_("raw body 미노출: rows/per_page_diagnostics를 제외한 반환값 어디에도 원문 데이터가 없음")
    else:
        reporter.fail("raw body 미노출 검증 실패: rows 외 필드에서 원문 데이터가 발견됨")


def check_unicode_json_bytes_decoded_correctly(reporter: ValidationReporter) -> None:
    """UTF-8 한글 JSON bytes가 snapshot -> decode -> json.loads 경로에서
    깨지지 않고 정상 처리돼야 한다."""
    response = _place_response([("p1", "카페상호명")])
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["rows"] and result["rows"][0]["업체명"] == "카페상호명":
        reporter.pass_("UTF-8 JSON bytes: 한글 업체명이 깨지지 않고 정상 decode됨")
    else:
        reporter.fail(f"UTF-8 decode 결과가 예상과 다름: {result.get('rows')}")


def check_json_decode_error_diagnostic_field(reporter: ValidationReporter) -> None:
    """body snapshot은 성공했지만 JSON decode 자체가 실패하는 경우
    json_decode_error_count(신규 진단 필드)가 증가해야 한다(body_snapshot_error_count와
    구분됨 - snapshot 실패와 JSON decode 실패는 서로 다른 원인이다)."""
    broken = FakeResponse(CANDIDATE_URL, 200, "xhr", body=b"not valid json {{{")
    page = FakePage(responses=[broken])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if (
        result["json_decode_error_count"] == 1
        and result["body_snapshot_success_count"] == 1
        and result["body_snapshot_error_count"] == 0
        and result["parse_error_count"] == 1
    ):
        reporter.pass_("json_decode_error_count 진단 필드: snapshot 성공 + JSON decode 실패를 body_snapshot_error_count와 구분해 집계함")
    else:
        reporter.fail(f"json_decode_error_count 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# PAGE-300-2B-2D: PAGE-300-2B-2C의 모순(body_snapshot_success_count=2인데
# body_snapshot_total_bytes가 실측 page1 크기(약 78KB)뿐이던 현상) 원인을
# 좁히기 위한 snapshot 무결성/EmptyBody/request-response 연결/JSON bytes
# decode 신규 검증.
# ---------------------------------------------------------------------------


def check_snapshot_total_bytes_equals_exact_sum_of_two_candidates(reporter: ValidationReporter) -> None:
    """테스트 1/13: page1(약 78KB급)과 page2(약 414KB급) 두 candidate 모두
    body snapshot이 성공하면 body_snapshot_total_bytes는 두 body 길이의
    "정확한 합"이어야 한다(PAGE-300-2B-2C처럼 page1 크기만 남는 결함 회귀 고정)."""
    body1 = json.dumps({"result": {"place": {"list": [{"id": f"p1_{i}", "name": f"업체{i}"} for i in range(400)]}}}).encode("utf-8")
    body2 = json.dumps([{"id": f"p2_{i}", "name": f"업체{i}"} for i in range(2200)]).encode("utf-8")
    response1 = FakeResponse(CANDIDATE_URL, 200, "xhr", body=body1)
    response2 = FakeResponse("https://pcmap-api.place.naver.com/graphql", 200, "fetch", body=body2)
    page = FakePage(responses=[response1, response2])
    result = collect_network_query(page, JOB, 10000, collected_at="2026-07-20")
    expected_total = len(body1) + len(body2)
    if (
        result["body_snapshot_success_count"] == 2
        and result["body_snapshot_error_count"] == 0
        and result["body_snapshot_empty_count"] == 0
        and result["json_decode_error_count"] == 0
        and result["body_snapshot_total_bytes"] == expected_total
        and expected_total > 50000
    ):
        reporter.pass_(f"snapshot total bytes: 두 candidate({len(body1)}B+{len(body2)}B) 합계 {expected_total}B와 정확히 일치")
    else:
        reporter.fail(f"snapshot total bytes 결과가 예상과 다름: expected={expected_total}, result={result}")


def check_empty_body_not_counted_as_success(reporter: ValidationReporter) -> None:
    """테스트 2: page1은 정상, page2는 빈 bytes(0바이트) - EmptyBody로 안전
    분류되어 성공으로 집계되지 않아야 한다(PAGE-300-2B-2C 모순의 유력 원인)."""
    ok_response = _place_response([("p1", "업체1")])
    empty_response = FakeResponse("https://pcmap-api.place.naver.com/graphql", 200, "fetch", body=b"")
    page = FakePage(responses=[ok_response, empty_response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = {d["sequence_id"]: d for d in result["candidate_snapshot_diagnostics"]}
    if (
        result["body_snapshot_success_count"] == 1
        and result["body_snapshot_empty_count"] == 1
        and result["body_snapshot_error_count"] == 1
        and result["body_snapshot_total_bytes"] == len(json.dumps({"result": {"place": {"list": [{"id": "p1", "name": "업체1"}]}}}).encode("utf-8"))
        and diag[1]["body_snapshot_state"] == "empty"
        and diag[1]["body_snapshot_error_type"] == "EmptyBody"
    ):
        reporter.pass_("빈 body(0바이트) candidate: EmptyBody로 안전 분류, success_count=1/empty_count=1, total_bytes=page1 크기만")
    else:
        reporter.fail(f"빈 body 결과가 예상과 다름: {result}")


def check_duplicate_requestfinished_total_bytes_counted_once(reporter: ValidationReporter) -> None:
    """테스트 3: 동일 requestfinished가 두 번 발생해도 body_snapshot_total_bytes는
    한 번만 합산돼야 한다(idempotent snapshot의 byte 집계 버전)."""
    response = _place_response([("p1", "업체1")])

    class DuplicateFinishPage(FakePage):
        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            for handler in list(self._handlers.get("response", [])):
                handler(response)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(response.request)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(response.request)

    page = DuplicateFinishPage()
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    expected_bytes = len(json.dumps({"result": {"place": {"list": [{"id": "p1", "name": "업체1"}]}}}).encode("utf-8"))
    if (
        response.body_call_count == 1
        and result["body_snapshot_success_count"] == 1
        and result["body_snapshot_total_bytes"] == expected_bytes
    ):
        reporter.pass_("동일 requestfinished 2회: body_snapshot_total_bytes도 1회만 합산됨(idempotent)")
    else:
        reporter.fail(f"중복 requestfinished byte 집계 결과가 예상과 다름: {result}")


def check_unmatched_requestfinished_for_never_registered_candidate(reporter: ValidationReporter) -> None:
    """테스트 4: candidate 패턴과 일치하는 request가 response 이벤트 없이
    (즉 request_id_to_candidate에 등록된 적 없이) requestfinished만 발생하면
    unmatched_requestfinished_count가 증가해야 하고, 다른 candidate에 잘못
    연결되어 snapshot이 저장되면 안 된다."""
    ok_response = _place_response([("p1", "업체1")])
    stray_request = FakeRequest("xhr")
    stray_request.url = CANDIDATE_URL

    class UnmatchedFinishPage(FakePage):
        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            for handler in list(self._handlers.get("response", [])):
                handler(ok_response)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(ok_response.request)
            # response 이벤트 없이(candidate로 등록된 적 없이) requestfinished만 발생.
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(stray_request)

    page = UnmatchedFinishPage()
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    if (
        result["unmatched_requestfinished_count"] == 1
        and result["candidate_response_count"] == 1
        and result["body_snapshot_success_count"] == 1
        and len(result["rows"]) == 1
    ):
        reporter.pass_("잘못된 request identity: unmatched_requestfinished_count 증가, 다른 candidate에 snapshot 저장 안 됨")
    else:
        reporter.fail(f"unmatched requestfinished 결과가 예상과 다름: {result}")


def check_ambiguous_request_mapping_not_snapshotted_as_new_success(reporter: ValidationReporter) -> None:
    """테스트 5: 서로 다른 두 response 이벤트가 같은 request 객체를 공유하면
    (하나의 request가 둘 이상의 candidate에 연결되려는 상황) 두 번째는
    ambiguous_request_mapping_count로만 집계되고 별도 성공 candidate로
    만들어지면 안 된다."""
    shared_request = FakeRequest("xhr")
    response_a = FakeResponse.__new__(FakeResponse)
    response_a.url = CANDIDATE_URL
    response_a.status = 200
    response_a.request = shared_request
    response_a._body = json.dumps({"result": {"place": {"list": [{"id": "p1", "name": "업체1"}]}}}).encode("utf-8")
    response_a._body_error = None
    response_a.body_call_count = 0
    response_a.simulate_request_failed = False
    response_a.headers = {}
    shared_request._response = response_a

    response_b = FakeResponse.__new__(FakeResponse)
    response_b.url = CANDIDATE_URL
    response_b.status = 200
    response_b.request = shared_request
    response_b._body = json.dumps({"result": {"place": {"list": [{"id": "p2", "name": "업체2"}]}}}).encode("utf-8")
    response_b._body_error = None
    response_b.body_call_count = 0
    response_b.simulate_request_failed = False
    response_b.headers = {}

    def body_a():
        response_a.body_call_count += 1
        return response_a._body

    def body_b():
        response_b.body_call_count += 1
        return response_b._body

    response_a.body = body_a
    response_b.body = body_b

    # gpt-5.6-sol 독립 검토(High) 재현, 2차 검토 지적 반영(순서 강화): A의
    # requestfinished를 B가 도착하기 "전에" 미리 확정시키면 idempotent guard가
    # 회귀를 가려버려 수정 전 코드도 우연히 통과할 수 있다(2차 검토 지적) -
    # 실제 결함을 확실히 재현하려면 response(A) -> response(B, ambiguous 판정) ->
    # shared_request가 B를 가리키도록 재할당 -> "최초" requestfinished 순서여야
    # 한다. 이 순서에서 entry(candidate A)는 여전히 A의 body만 snapshot해야
    # 하며(entry["response"]를 신뢰), request.response()를 다시 조회해 B의
    # body가 A의 entry에 뒤섞이면 안 된다.
    class AmbiguousRequestResponseSwapPage(FakePage):
        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            for handler in list(self._handlers.get("response", [])):
                handler(response_a)
            for handler in list(self._handlers.get("response", [])):
                handler(response_b)
            # ambiguous 판정(entry 미생성) 이후에야 shared_request가 B를
            # 가리키도록 재할당하고, 이 시점에 처음이자 유일하게 requestfinished를
            # 발생시킨다 - entry["response"](=A)를 신뢰하지 않으면 이 시점에
            # request.response()가 B를 반환해 A entry에 B body가 저장된다.
            shared_request._response = response_b
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(shared_request)

    page = AmbiguousRequestResponseSwapPage()
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    if (
        result["ambiguous_request_mapping_count"] == 1
        and result["candidate_response_count"] == 1
        and len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "p1"
        and response_b.body_call_count == 0
    ):
        reporter.pass_("동일 request가 둘 이상의 response에 연결(request.response()가 이후 B로 바뀌어도): entry는 candidate 등록 시점의 response(A)만 snapshot하고 B body는 호출조차 되지 않음")
    else:
        reporter.fail(f"ambiguous request mapping 결과가 예상과 다름: {result}, response_b.body_call_count={response_b.body_call_count}")


def check_navigation_error_preserves_already_observed_snapshot_invariant(reporter: ValidationReporter) -> None:
    """gpt-5.6-sol 독립 검토(Medium) 재현: goto() 도중 candidate response와
    requestfinished가 먼저 관측된 뒤(예: 병행 요청이 이미 끝남) navigation_error
    예외가 발생하면, 조기 반환도 하드코딩된 0/빈 리스트 대신 실제 ctx 상태를
    반영해 success+error+pending == candidate_response_count 불변식을 유지해야
    한다."""
    response = _place_response([("p1", "업체1")])

    class NavigationErrorAfterResponsePage(FakePage):
        def goto(self, url, wait_until=None, timeout=None):
            self.goto_calls.append(url)
            for handler in list(self._handlers.get("response", [])):
                handler(response)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(response.request)
            raise Exception("Target page, context or browser has been closed")

    page = NavigationErrorAfterResponsePage()
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    total = result["body_snapshot_success_count"] + result["body_snapshot_error_count"] + result["snapshot_pending_count"]
    if (
        result["navigation_error"] is True
        and result["candidate_response_count"] == 1
        and result["body_snapshot_success_count"] == 1
        and total == result["candidate_response_count"] == 1
        and len(result["candidate_snapshot_diagnostics"]) == 1
        and result["body_snapshot_total_bytes"] > 0
        and result["rows"] == []
    ):
        reporter.pass_("navigation_error 조기 반환도 이미 관측된 candidate의 snapshot 상태를 정확히 반영(success+error+pending==candidate_response_count 유지, rows는 여전히 빈 리스트)")
    else:
        reporter.fail(f"navigation_error 조기 반환 불변식 결과가 예상과 다름: total={total}, result={result}")


def check_utf8_json_object_bytes_decoded(reporter: ValidationReporter) -> None:
    """테스트 6: UTF-8 JSON object(dict top-level) bytes가 정상 decode된다."""
    response = _place_response([("p1", "업체1")])
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = result["candidate_snapshot_diagnostics"][0]
    if len(result["rows"]) == 1 and diag["json_top_level_type"] == "object" and diag["json_decode_error_type"] == "":
        reporter.pass_("UTF-8 JSON object bytes: 정상 decode, json_top_level_type=object")
    else:
        reporter.fail(f"UTF-8 object decode 결과가 예상과 다름: {diag}")


def check_utf8_json_array_bytes_decoded(reporter: ValidationReporter) -> None:
    """테스트 7: UTF-8 JSON array(top-level list) bytes가 정상 decode된다."""
    body = json.dumps([{"id": "p1", "name": "업체1"}]).encode("utf-8")
    response = FakeResponse(CANDIDATE_URL, 200, "xhr", body=body)
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = result["candidate_snapshot_diagnostics"][0]
    if (
        len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "p1"
        and diag["json_top_level_type"] == "array"
        and diag["json_decode_error_type"] == ""
    ):
        reporter.pass_("UTF-8 JSON array bytes: 정상 decode, json_top_level_type=array")
    else:
        reporter.fail(f"UTF-8 array decode 결과가 예상과 다름: {diag}, rows={result.get('rows')}")


def check_utf8_bom_prefixed_json_decoded(reporter: ValidationReporter) -> None:
    """테스트 8: UTF-8 BOM이 포함된 JSON bytes도 json.loads(bytes)로 정상 decode된다."""
    body = b"\xef\xbb\xbf" + json.dumps({"result": {"place": {"list": [{"id": "p1", "name": "업체1"}]}}}).encode("utf-8")
    response = FakeResponse(CANDIDATE_URL, 200, "xhr", body=body)
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = result["candidate_snapshot_diagnostics"][0]
    if len(result["rows"]) == 1 and diag["bom_type"] == "utf8" and diag["json_decode_error_type"] == "":
        reporter.pass_("UTF-8 BOM 포함 JSON: 정상 decode, bom_type=utf8로 진단됨")
    else:
        reporter.fail(f"UTF-8 BOM decode 결과가 예상과 다름: {diag}, rows={result.get('rows')}")


def check_utf16_json_bytes_decoded_by_json_loads(reporter: ValidationReporter) -> None:
    """테스트 9: UTF-16(BOM 포함) 인코딩된 JSON bytes를 json.loads(bytes)가
    실제로 처리할 수 있는지 검증한다(Python 표준 동작 확인 - fake 없이 실제
    encode/decode 경로를 그대로 통과시킨다)."""
    body = json.dumps({"result": {"place": {"list": [{"id": "p1", "name": "업체1"}]}}}).encode("utf-16")
    response = FakeResponse(CANDIDATE_URL, 200, "xhr", body=body)
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = result["candidate_snapshot_diagnostics"][0]
    if (
        len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "p1"
        and diag["json_decode_error_type"] == ""
        and diag["bom_type"] in ("utf16_le", "utf16_be")
    ):
        reporter.pass_("UTF-16 JSON bytes: json.loads(bytes)가 BOM을 감지해 정상 decode함(실제 Python 표준 동작 확인)")
    else:
        reporter.fail(f"UTF-16 decode 결과가 예상과 다름: {diag}, rows={result.get('rows')}")


def check_html_error_body_reports_first_char_and_no_leak(reporter: ValidationReporter) -> None:
    """테스트 10: HTML 오류 body는 first_non_whitespace_character='<'로
    진단되고 JSON decode 실패로 안전 처리되며 원문이 노출되지 않아야 한다."""
    html_marker = "고유HTML마커QWE"
    body = f"<html><body>{html_marker}</body></html>".encode("utf-8")
    response = FakeResponse(CANDIDATE_URL, 200, "xhr", body=body)
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = result["candidate_snapshot_diagnostics"][0]
    leaked = html_marker in json.dumps(result["candidate_snapshot_diagnostics"])
    if (
        diag["first_non_whitespace_character"] == "<"
        and diag["json_decode_error_type"] != ""
        and result["json_decode_error_count"] == 1
        and not leaked
    ):
        reporter.pass_("HTML 오류 body: first_non_whitespace_character='<', json decode 실패, 원문 미노출")
    else:
        reporter.fail(f"HTML 오류 body 결과가 예상과 다름: {diag}, leaked={leaked}")


def check_gzip_magic_body_no_decompression_attempted(reporter: ValidationReporter) -> None:
    """테스트 11: gzip magic bytes(\\x1f\\x8b)로 시작하는 body는
    compression_magic='gzip'으로만 진단되고, 임의 압축 해제를 시도하지
    않으므로 json decode는 실패해야 한다."""
    body = b"\x1f\x8b" + b"\x00" * 20
    response = FakeResponse(CANDIDATE_URL, 200, "xhr", body=body)
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = result["candidate_snapshot_diagnostics"][0]
    if (
        diag["compression_magic"] == "gzip"
        and diag["json_decode_error_type"] != ""
        and result["json_decode_error_count"] == 1
        and result["rows"] == []
    ):
        reporter.pass_("gzip magic body: compression_magic=gzip으로만 진단, 임의 압축 해제 없이 json decode 실패로 안전 처리")
    else:
        reporter.fail(f"gzip magic body 결과가 예상과 다름: {diag}")


def check_zero_length_body_skips_json_loads(reporter: ValidationReporter) -> None:
    """테스트 12: 0바이트 body는 EmptyBody로 즉시 확정되며, json.loads가
    호출되지 않으므로 json_decode_error_type이 채워지지 않아야 한다(decode
    시도 자체가 없었다는 증거 - 이미 EmptyBody 원인으로 확정됐기 때문)."""
    response = FakeResponse(CANDIDATE_URL, 200, "xhr", body=b"")
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    diag = result["candidate_snapshot_diagnostics"][0]
    if (
        diag["body_snapshot_state"] == "empty"
        and diag["body_snapshot_error_type"] == "EmptyBody"
        and diag["json_decode_error_type"] == ""
        and result["json_decode_error_count"] == 0
        and result["body_snapshot_empty_count"] == 1
    ):
        reporter.pass_("zero-length body: EmptyBody로 즉시 확정, json.loads 호출 없음(json_decode_error_type 미기록)")
    else:
        reporter.fail(f"zero-length body 결과가 예상과 다름: {diag}, result={result}")


def check_snapshot_invariant_success_error_pending_equals_candidate_count(reporter: ValidationReporter) -> None:
    """테스트 13(불변식): body_snapshot_success_count + body_snapshot_error_count
    + snapshot_pending_count는 candidate_response_count와 정확히 일치해야 한다."""
    ok_response = _place_response([("p1", "업체1")])
    broken = FakeResponse(CANDIDATE_URL, 200, "xhr", body=b"not valid json {{{")
    empty_response = FakeResponse(CANDIDATE_URL, 200, "xhr", body=b"")
    page = FakePage(responses=[ok_response, broken, empty_response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    total = result["body_snapshot_success_count"] + result["body_snapshot_error_count"] + result["snapshot_pending_count"]
    if total == result["candidate_response_count"] == 3:
        reporter.pass_("snapshot 불변식: success+error+pending == candidate_response_count(3) 정확히 성립")
    else:
        reporter.fail(f"snapshot 불변식 결과가 예상과 다름: total={total}, result={result}")


def check_candidate_diagnostics_no_business_data_leak(reporter: ValidationReporter) -> None:
    """테스트 14: candidate_snapshot_diagnostics는 raw body, 업체명, 주소,
    전화번호를 전혀 포함하지 않아야 한다(size/타입/enum 라벨만 허용)."""
    marker_name = "고유업체진단마커"
    marker_address = "고유주소진단마커"
    marker_tel = "010-9999-8888"
    response = FakeResponse(
        CANDIDATE_URL, 200, "xhr",
        body=json.dumps({
            "result": {"place": {"list": [
                {"id": "p1", "name": marker_name, "roadAddress": marker_address, "tel": marker_tel}
            ]}}
        }).encode("utf-8"),
    )
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    serialized = json.dumps(result["candidate_snapshot_diagnostics"])
    leaked = any(marker in serialized for marker in (marker_name, marker_address, marker_tel))
    if not leaked:
        reporter.pass_("candidate diagnostics: raw body/업체명/주소/전화번호 미노출(size/enum 라벨만 포함)")
    else:
        reporter.fail("candidate diagnostics 검증 실패: 업체 원문 데이터가 진단 필드에 노출됨")


def check_graphql_top_level_list_synthetic_body_end_to_end(reporter: ValidationReporter) -> None:
    """테스트 15: GraphQL top-level list(placeholder 중첩 구조) synthetic
    body가 snapshot -> json.loads(bytes) -> 기존 parser(_extract_list_items/
    _find_item_lists) 전체 경로를 통과해 rows로 정상 매핑돼야 한다."""
    # placeholder 키(실제 미확인 GraphQL 스키마를 추정하지 않음) - top-level list
    # 안에 중첩된 업체 배열을 휴리스틱 재귀로 찾아내는 계약만 검증한다
    # (tests/test_pc_network_list_scraper.py의 TOP_LEVEL_ARRAY_FIXTURE와 동일한 패턴).
    synthetic_graphql_array = [
        {"wrapper_unconfirmed": {"nested_unconfirmed": [
            {"id": f"g{i}", "name": f"업체g{i}"} for i in range(3)
        ]}}
    ]
    body = json.dumps(synthetic_graphql_array).encode("utf-8")
    response = FakeResponse("https://pcmap-api.place.naver.com/graphql", 200, "fetch", body=body)
    page = FakePage(responses=[response])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-20")
    ids = sorted(row.get("place_id") for row in result["rows"])
    diag = result["candidate_snapshot_diagnostics"][0]
    if ids == ["g0", "g1", "g2"] and diag["json_top_level_type"] == "array" and result["parse_error_count"] == 0:
        reporter.pass_("GraphQL top-level list synthetic body: snapshot->json.loads(bytes)->기존 parser 경로로 rows 정상 추출")
    else:
        reporter.fail(f"GraphQL top-level list 결과가 예상과 다름: ids={ids}, diag={diag}")


class FakeLifecyclePage:
    """NetworkBrowserCollector 생명주기 테스트용 fake page. 실제 응답 관찰은
    하지 않고, close() 호출 여부/횟수와 best-effort 예외 처리만 검증한다."""

    def __init__(self, page_id: int):
        self.page_id = page_id
        self.close_call_count = 0
        self.close_error = None

    def close(self):
        self.close_call_count += 1
        if self.close_error is not None:
            raise self.close_error


class FakeLifecycleContext:
    """공유 context 역할의 fake. new_page() 호출마다 새 FakeLifecyclePage를 만든다."""

    def __init__(self):
        self.new_page_call_count = 0
        self.pages_created: list = []
        self.next_page_close_error = None

    def new_page(self):
        self.new_page_call_count += 1
        page = FakeLifecyclePage(self.new_page_call_count)
        if self.next_page_close_error is not None:
            page.close_error = self.next_page_close_error
            self.next_page_close_error = None
        self.pages_created.append(page)
        return page


class FakeLifecycleSession:
    """BrowserSession과 동일한 계약(컨텍스트 매니저 + .context 속성)만 흉내내는 fake."""

    def __init__(self, context: FakeLifecycleContext):
        self.context = context
        self.enter_count = 0
        self.exit_count = 0
        self.last_exit_args = None

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exit_count += 1
        self.last_exit_args = (exc_type, exc, tb)
        return False


def _fake_collect_network_query_recording(calls: list, *, raise_error: Exception | None = None):
    """network_browser_collector.collect_network_query를 monkeypatch할 fake.
    실제 응답 관찰 대신 호출 인자만 기록하고 고정된 결과 dict를 반환한다."""

    def fake(page, job, per_query_limit, *, collected_at, settle_ms):
        calls.append({
            "page": page,
            "job": job,
            "per_query_limit": per_query_limit,
            "collected_at": collected_at,
            "settle_ms": settle_ms,
        })
        if raise_error is not None:
            raise raise_error
        return {
            "rows": [],
            "active_captcha_detected": False,
            "status_429_seen": False,
            "candidate_response_count": 0,
            "raw_item_count": 0,
            "local_unique_count": 0,
            "parse_error_count": 0,
            "timeout": False,
            "navigation_error": False,
            "navigation_error_message": "",
        }

    return fake


def check_session_and_context_shared_across_jobs(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext()
    session = FakeLifecycleSession(context)
    factory_calls = {"count": 0}

    def factory():
        factory_calls["count"] += 1
        return session

    calls: list = []
    original = network_browser_collector.collect_network_query
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording(calls)
    try:
        with NetworkBrowserCollector(collected_at="2026-07-14", session_factory=factory) as collector:
            collector.collect_query({"query": "q1"}, 10)
            collector.collect_query({"query": "q2"}, 10)
            collector.collect_query({"query": "q3"}, 10)
    finally:
        network_browser_collector.collect_network_query = original

    if factory_calls["count"] == 1 and session.enter_count == 1:
        reporter.pass_("browser/context 공유: 여러 job을 처리해도 session_factory/session.__enter__는 1회만 호출됨")
    else:
        reporter.fail(f"browser/context 공유 결과가 예상과 다름: factory_calls={factory_calls}, enter_count={session.enter_count}")


def check_new_page_created_per_query(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext()
    session = FakeLifecycleSession(context)

    calls: list = []
    original = network_browser_collector.collect_network_query
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording(calls)
    try:
        with NetworkBrowserCollector(collected_at="2026-07-14", session_factory=lambda: session) as collector:
            collector.collect_query({"query": "q1"}, 10)
            collector.collect_query({"query": "q2"}, 10)
            collector.collect_query({"query": "q3"}, 10)
    finally:
        network_browser_collector.collect_network_query = original

    if context.new_page_call_count == 3 and len(context.pages_created) == 3:
        reporter.pass_("쿼리별 page 생성: collect_query 3회 호출 시 new_page도 정확히 3회 호출됨")
    else:
        reporter.fail(f"쿼리별 page 생성 결과가 예상과 다름: new_page_call_count={context.new_page_call_count}")


def check_each_page_closed_exactly_once(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext()
    session = FakeLifecycleSession(context)

    calls: list = []
    original = network_browser_collector.collect_network_query
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording(calls)
    try:
        with NetworkBrowserCollector(collected_at="2026-07-14", session_factory=lambda: session) as collector:
            collector.collect_query({"query": "q1"}, 10)
            collector.collect_query({"query": "q2"}, 10)
            collector.collect_query({"query": "q3"}, 10)
    finally:
        network_browser_collector.collect_network_query = original

    close_counts = [page.close_call_count for page in context.pages_created]
    if len(context.pages_created) == 3 and close_counts == [1, 1, 1]:
        reporter.pass_("쿼리별 page 종료: 생성된 각 page가 정확히 1회씩 close됨")
    else:
        reporter.fail(f"쿼리별 page 종료 결과가 예상과 다름: close_counts={close_counts}")


def check_collect_network_query_receives_expected_arguments(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext()
    session = FakeLifecycleSession(context)
    job = {"query": "서울특별시 강동구 천호동 카페"}

    calls: list = []
    original = network_browser_collector.collect_network_query
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording(calls)
    try:
        with NetworkBrowserCollector(
            collected_at="2026-07-14", session_factory=lambda: session, settle_ms=1234
        ) as collector:
            collector.collect_query(job, 7)
    finally:
        network_browser_collector.collect_network_query = original

    if (
        len(calls) == 1
        and calls[0]["job"] is job
        and calls[0]["per_query_limit"] == 7
        and calls[0]["collected_at"] == "2026-07-14"
        and calls[0]["settle_ms"] == 1234
        and calls[0]["page"] is context.pages_created[0]
    ):
        reporter.pass_("collect_network_query 전달: job/per_query_limit/collected_at/settle_ms/page가 정확히 전달됨")
    else:
        reporter.fail(f"collect_network_query 인자 전달 결과가 예상과 다름: {calls}")


def check_page_close_error_does_not_override_result(reporter: ValidationReporter) -> None:
    context = FakeLifecycleContext()
    context.next_page_close_error = Exception("page already closed")
    session = FakeLifecycleSession(context)

    calls: list = []
    original = network_browser_collector.collect_network_query
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording(calls)
    try:
        with NetworkBrowserCollector(collected_at="2026-07-14", session_factory=lambda: session) as collector:
            result = collector.collect_query({"query": "q1"}, 10)
    finally:
        network_browser_collector.collect_network_query = original

    if (
        result is not None
        and result["navigation_error"] is False
        and result["rows"] == []
        and context.pages_created[0].close_call_count == 1
    ):
        reporter.pass_("page close best-effort: close()가 예외를 던져도 collect_network_query의 원래 결과를 그대로 반환함")
    else:
        reporter.fail(f"page close best-effort 결과가 예상과 다름: result={result}")


def check_context_manager_teardown_normal_and_on_error(reporter: ValidationReporter) -> None:
    # 정상 종료: with 블록이 끝나면 session.__exit__가 1회 호출된다.
    context_ok = FakeLifecycleContext()
    session_ok = FakeLifecycleSession(context_ok)
    calls: list = []
    original = network_browser_collector.collect_network_query
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording(calls)
    try:
        with NetworkBrowserCollector(collected_at="2026-07-14", session_factory=lambda: session_ok) as collector:
            collector.collect_query({"query": "q1"}, 10)
    finally:
        network_browser_collector.collect_network_query = original

    normal_ok = session_ok.exit_count == 1

    # 예외 종료: collect_query 도중 예외가 발생해도 __exit__는 여전히 호출되어야 한다.
    context_err = FakeLifecycleContext()
    session_err = FakeLifecycleSession(context_err)
    boom = RuntimeError("boom")
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording([], raise_error=boom)
    error_ok = False
    try:
        try:
            with NetworkBrowserCollector(collected_at="2026-07-14", session_factory=lambda: session_err) as collector:
                collector.collect_query({"query": "q1"}, 10)
        except RuntimeError:
            pass
        error_ok = (
            session_err.exit_count == 1
            and len(context_err.pages_created) == 1
            and context_err.pages_created[0].close_call_count == 1
        )
    finally:
        network_browser_collector.collect_network_query = original

    if normal_ok and error_ok:
        reporter.pass_("context manager teardown: 정상/예외 종료 모두 session __exit__ 호출 + page close 보장")
    else:
        reporter.fail(f"context manager teardown 결과가 예상과 다름: normal_ok={normal_ok}, error_ok={error_ok}")


class FakeBrowserSessionLike:
    """BrowserSession의 실제 계약(속성명·생명주기)만 흉내내는 fake(WIRE-2B-1B).

    __enter__에서 browser/context와 함께 초기 page(.page)도 미리 만들어 두는
    실제 BrowserSession의 동작을 그대로 재현한다. 생성자 시그니처도
    BrowserSession(diagnostic_config)와 동일하게 맞춘다(값은 사용하지 않음).
    생성된 인스턴스는 `instances`에 누적되어 테스트가 monkeypatch된
    _default_session_factory 경로에서 실제로 무엇이 만들어졌는지 확인할 수
    있게 한다.
    """

    instances: list = []

    def __init__(self, diagnostic_config=None):
        FakeBrowserSessionLike.instances.append(self)
        self.diagnostic_config = diagnostic_config
        self.context = FakeLifecycleContext()
        self.page = FakeLifecyclePage(0)
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exit_count += 1
        return False


def _run_with_fake_browser_session(body, *, raise_error: Exception | None = None):
    """src.pc.browser_session.BrowserSession을 FakeBrowserSessionLike로 monkeypatch한
    상태에서 body(collector)를 실행한다(session_factory 미지정 - 기본 factory 경로
    검증용). collect_network_query도 함께 monkeypatch해 실제 응답 관찰을 하지 않는다.
    """
    FakeBrowserSessionLike.instances.clear()
    original_browser_session = browser_session_module.BrowserSession
    original_collect = network_browser_collector.collect_network_query
    calls: list = []
    browser_session_module.BrowserSession = FakeBrowserSessionLike
    network_browser_collector.collect_network_query = _fake_collect_network_query_recording(
        calls, raise_error=raise_error
    )
    try:
        with NetworkBrowserCollector(collected_at="2026-07-14") as collector:
            body(collector)
    finally:
        browser_session_module.BrowserSession = original_browser_session
        network_browser_collector.collect_network_query = original_collect
    return calls


def check_default_factory_uses_browser_session(reporter: ValidationReporter) -> None:
    """1) 기본 factory 경로: session_factory를 넘기지 않아도 src.pc.browser_session.
    BrowserSession(monkeypatch됨)을 통해 세션이 만들어지고, 실제 Playwright는
    시작되지 않는다(FakeBrowserSessionLike는 Playwright를 전혀 다루지 않음)."""
    _run_with_fake_browser_session(lambda collector: collector.collect_query({"query": "q1"}, 10))

    if len(FakeBrowserSessionLike.instances) == 1 and FakeBrowserSessionLike.instances[0].enter_count == 1:
        reporter.pass_("기본 factory 경로: session_factory 미지정 시 BrowserSession(monkeypatch)이 정확히 1회 생성·진입됨")
    else:
        reporter.fail(f"기본 factory 경로 결과가 예상과 다름: instances={len(FakeBrowserSessionLike.instances)}")


def check_shared_context_attribute_used(reporter: ValidationReporter) -> None:
    """2) 공유 context 접근: collector가 session.context.new_page()를 사용하며,
    존재하지 않는 속성(예: session.browser 등)을 가정하지 않는다."""
    calls = _run_with_fake_browser_session(lambda collector: collector.collect_query({"query": "q1"}, 10))
    session = FakeBrowserSessionLike.instances[0]

    if (
        session.context.new_page_call_count == 1
        and len(calls) == 1
        and calls[0]["page"] is session.context.pages_created[0]
    ):
        reporter.pass_("공유 context 접근: collector가 session.context.new_page()로 만든 page를 collect_network_query에 전달함")
    else:
        reporter.fail(f"공유 context 접근 결과가 예상과 다름: new_page_call_count={session.context.new_page_call_count}, calls={calls}")


def check_initial_page_is_closed_and_not_reused(reporter: ValidationReporter) -> None:
    """3) 초기 page 처리: BrowserSession.__enter__가 미리 만든 session.page는
    쿼리용으로 재사용되지 않고, best-effort로 즉시 닫힌다."""
    calls = _run_with_fake_browser_session(lambda collector: collector.collect_query({"query": "q1"}, 10))
    session = FakeBrowserSessionLike.instances[0]

    if (
        session.page.close_call_count == 1
        and calls[0]["page"] is not session.page
    ):
        reporter.pass_("초기 page 처리: session.page는 수집용으로 재사용되지 않고 __enter__에서 즉시 닫힘")
    else:
        reporter.fail(f"초기 page 처리 결과가 예상과 다름: initial_close_count={session.page.close_call_count}")


def check_per_query_page_separate_from_initial_page(reporter: ValidationReporter) -> None:
    """4) 쿼리별 page: collect_query 2회 시 new_page()도 2회 호출되고, 초기 page와는
    별개로 관리되며 각 쿼리 page는 정확히 1회씩 close된다."""

    def body(collector):
        collector.collect_query({"query": "q1"}, 10)
        collector.collect_query({"query": "q2"}, 10)

    _run_with_fake_browser_session(body)
    session = FakeBrowserSessionLike.instances[0]
    query_pages = session.context.pages_created
    close_counts = [page.close_call_count for page in query_pages]

    if (
        session.context.new_page_call_count == 2
        and len(query_pages) == 2
        and close_counts == [1, 1]
        and session.page not in query_pages
        and session.page.close_call_count == 1
    ):
        reporter.pass_("쿼리별 page: collect_query 2회 → new_page 2회, 각 쿼리 page는 1회씩 close, 초기 page와 분리됨")
    else:
        reporter.fail(f"쿼리별 page 결과가 예상과 다름: new_page_call_count={session.context.new_page_call_count}, close_counts={close_counts}")


def check_default_factory_teardown_normal_and_on_error(reporter: ValidationReporter) -> None:
    """5) teardown: 기본 factory 경로에서도 정상/예외 종료 모두 session.__exit__가
    정확히 1회 호출된다(초기 page/context/browser 자원 정리 계약 확인)."""
    _run_with_fake_browser_session(lambda collector: collector.collect_query({"query": "q1"}, 10))
    normal_session = FakeBrowserSessionLike.instances[0]
    normal_ok = normal_session.exit_count == 1

    error_ok = False
    try:
        _run_with_fake_browser_session(
            lambda collector: collector.collect_query({"query": "q1"}, 10),
            raise_error=RuntimeError("boom"),
        )
    except RuntimeError:
        error_ok = True
    if error_ok:
        error_session = FakeBrowserSessionLike.instances[0]
        error_ok = error_session.exit_count == 1

    if normal_ok and error_ok:
        reporter.pass_("teardown(기본 factory): 정상/예외 종료 모두 session.__exit__가 1회 호출됨")
    else:
        reporter.fail(f"teardown(기본 factory) 결과가 예상과 다름: normal_ok={normal_ok}, error_ok={error_ok}")


def main() -> int:
    reporter = ValidationReporter()

    check_listener_registered_once_and_removed(reporter)
    check_multiple_candidate_responses_concat(reporter)
    check_local_dedup_before_limit(reporter)
    check_per_query_limit_caps_after_dedup(reporter)
    check_active_captcha_detected(reporter)
    check_passive_marker_not_active(reporter)
    check_status_429_seen_on_non_candidate_response(reporter)
    check_goto_timeout(reporter)
    check_goto_navigation_error_is_not_timeout(reporter)
    check_no_candidate_responses_is_timeout(reporter)
    check_zero_search_results_is_not_timeout(reporter)
    check_parse_error_does_not_crash(reporter)
    check_source_meta_preserved_on_rows(reporter)
    check_late_body_access_would_fail_but_snapshot_cached(reporter)
    check_requestfinished_snapshot_failure_records_parse_error(reporter)
    check_requestfailed_marks_candidate_failed_partial_rows_preserved(reporter)
    check_requestfailed_without_prior_response_is_still_counted(reporter)
    check_candidate_body_too_large_is_rejected_safely(reporter)
    check_content_length_header_rejects_before_body_call(reporter)
    check_duplicate_requestfinished_event_snapshots_once(reporter)
    check_no_raw_body_leak_in_result(reporter)
    check_unicode_json_bytes_decoded_correctly(reporter)
    check_json_decode_error_diagnostic_field(reporter)

    check_snapshot_total_bytes_equals_exact_sum_of_two_candidates(reporter)
    check_empty_body_not_counted_as_success(reporter)
    check_duplicate_requestfinished_total_bytes_counted_once(reporter)
    check_unmatched_requestfinished_for_never_registered_candidate(reporter)
    check_ambiguous_request_mapping_not_snapshotted_as_new_success(reporter)
    check_navigation_error_preserves_already_observed_snapshot_invariant(reporter)
    check_utf8_json_object_bytes_decoded(reporter)
    check_utf8_json_array_bytes_decoded(reporter)
    check_utf8_bom_prefixed_json_decoded(reporter)
    check_utf16_json_bytes_decoded_by_json_loads(reporter)
    check_html_error_body_reports_first_char_and_no_leak(reporter)
    check_gzip_magic_body_no_decompression_attempted(reporter)
    check_zero_length_body_skips_json_loads(reporter)
    check_snapshot_invariant_success_error_pending_equals_candidate_count(reporter)
    check_candidate_diagnostics_no_business_data_leak(reporter)
    check_graphql_top_level_list_synthetic_body_end_to_end(reporter)

    check_session_and_context_shared_across_jobs(reporter)
    check_new_page_created_per_query(reporter)
    check_each_page_closed_exactly_once(reporter)
    check_collect_network_query_receives_expected_arguments(reporter)
    check_page_close_error_does_not_override_result(reporter)
    check_context_manager_teardown_normal_and_on_error(reporter)
    check_default_factory_uses_browser_session(reporter)
    check_shared_context_attribute_used(reporter)
    check_initial_page_is_closed_and_not_reused(reporter)
    check_per_query_page_separate_from_initial_page(reporter)
    check_default_factory_teardown_normal_and_on_error(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
