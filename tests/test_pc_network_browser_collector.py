from pathlib import Path
from types import SimpleNamespace
import sys


# ARCH-300C WIRE-2A: src/pc/network_browser_collector.py 검증용 standalone
# 스크립트(live/Playwright 없음, FakePage/FakeResponse 기반). collect_network_query는
# page를 전달받기만 하므로, 실제 브라우저 없이 FakePage 주입만으로 검증할 수 있다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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


class FakeResponse:
    def __init__(self, url, status, resource_type, json_data=None, json_error=None):
        self.url = url
        self.status = status
        self.request = SimpleNamespace(resource_type=resource_type)
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


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
    return FakeResponse(url, 200, "xhr", json_data={"result": {"place": {"list": items}}})


def check_listener_registered_once_and_removed(reporter: ValidationReporter) -> None:
    page = FakePage(responses=[_place_response([("p1", "업체1")])])
    collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if page.on_call_count == 1 and page.off_call_count == 1 and len(page._handlers.get("response", [])) == 0:
        reporter.pass_("listener 등록·해제: on 1회, off 1회, 잔여 handler 없음")
    else:
        reporter.fail(
            f"listener 등록·해제 결과가 예상과 다름: on={page.on_call_count}, off={page.off_call_count}, "
            f"remaining={len(page._handlers.get('response', []))}"
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
    broken = FakeResponse(CANDIDATE_URL, 200, "xhr", json_error=ValueError("bad json"))
    ok = _place_response([("p1", "업체1")])
    page = FakePage(responses=[broken, ok])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-14")
    if result["parse_error_count"] == 1 and len(result["rows"]) == 1 and result["rows"][0]["place_id"] == "p1":
        reporter.pass_("parse error: json() 예외는 parse_error_count만 증가시키고 나머지 후보는 계속 처리됨")
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

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
