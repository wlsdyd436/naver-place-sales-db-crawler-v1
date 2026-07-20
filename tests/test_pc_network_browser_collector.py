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
