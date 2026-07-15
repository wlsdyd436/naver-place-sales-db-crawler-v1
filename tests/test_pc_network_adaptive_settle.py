from pathlib import Path
from types import SimpleNamespace
import inspect
import sys


# ARCH-300C PERF-1A: src/pc/network_browser_collector.py의 적응형 settle
# (고정 5초 대기 -> 유효 목록 확인 후 quiet period 조기 종료, hard cap=settle_ms
# 유지)을 검증하는 standalone 스크립트(live/Playwright 없음). 기존
# tests/test_pc_network_browser_collector.py의 FakePage는 goto() 시점에
# 등록된 모든 response를 한꺼번에 동기 전달하므로 "폴링 도중 나중에 도착"하는
# 시나리오를 표현하지 못한다 - 이 파일은 그 시나리오를 결정적으로(fake clock,
# 실제 대기 없음) 표현하기 위한 FakeAdaptivePage를 별도로 둔다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc import network_browser_collector
from src.pc.network_browser_collector import (
    _POLL_INTERVAL_MS,
    _QUIET_PERIOD_MS,
    collect_network_query,
)


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
        self.json_call_count = 0

    def json(self):
        self.json_call_count += 1
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


CANDIDATE_URL = "https://map.naver.com/p/api/search/allSearch?query=x"


def _place_response(item_ids_and_names, url=CANDIDATE_URL):
    items = [{"id": item_id, "name": name} for item_id, name in item_ids_and_names]
    return FakeResponse(url, 200, "xhr", json_data={"result": {"place": {"list": items}}})


def _broken_response(url=CANDIDATE_URL):
    return FakeResponse(url, 200, "xhr", json_error=ValueError("bad json"))


class FakeAdaptivePage:
    """wait_for_timeout(ms) 호출마다 누적 경과시간(_elapsed_ms)을 추적하고,
    그 경과시간을 기준으로 예약된 response를 그 시점에 "도착"시키는 fake clock
    기반 page. delivery_schedule은 [(deliver_after_ms, response), ...] 형태 -
    누적 elapsed_ms가 deliver_after_ms 이상이 되는 첫 wait_for_timeout(또는
    goto) 호출 시점에 해당 response의 핸들러를 호출한다. 실제 시간 대기는
    전혀 하지 않는다(테스트가 즉시 끝남)."""

    def __init__(self, delivery_schedule, *, captcha_selectors=None, goto_error=None):
        self._handlers: dict = {}
        self._schedule = sorted(delivery_schedule, key=lambda pair: pair[0])
        self._delivered_count = 0
        self._elapsed_ms = 0
        self._captcha_selectors = captcha_selectors or {}
        self._goto_error = goto_error
        self.goto_calls: list = []
        self.wait_calls: list = []

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
        self.wait_calls.append(ms)
        self._elapsed_ms += ms
        self._deliver_due()

    def _deliver_due(self):
        while self._delivered_count < len(self._schedule) and self._schedule[self._delivered_count][0] <= self._elapsed_ms:
            _, response = self._schedule[self._delivered_count]
            self._delivered_count += 1
            for handler in list(self._handlers.get("response", [])):
                handler(response)

    def locator(self, selector):
        return self._captcha_selectors.get(selector, FakeLocator(count=0))


JOB = {
    "query": "서울특별시 강동구 천호동 카페",
    "source_city": "서울특별시", "source_district": "강동구",
    "source_subregion": "천호동", "source_layer": "legal_dong",
}

_HARD_CAP_TICKS = 5000 // _POLL_INTERVAL_MS  # 기본 settle_ms=5000 기준 최대 tick 수(50)
# quiet_elapsed_ms는 100ms 단위로만 누적되므로 750ms를 "이상"으로 채우려면
# 올림(ceil) 계산이 필요하다(750//100=7이지만 실제로는 800ms, 즉 8틱이 걸림).
_QUIET_TICKS = -(-_QUIET_PERIOD_MS // _POLL_INTERVAL_MS)


def check_constants_match_expected_defaults(reporter: ValidationReporter) -> None:
    if _QUIET_PERIOD_MS == 750 and _POLL_INTERVAL_MS == 100:
        reporter.pass_("모듈 상수: _QUIET_PERIOD_MS=750, _POLL_INTERVAL_MS=100(요청서 권장 기본값과 일치)")
    else:
        reporter.fail(f"모듈 상수가 예상과 다름: _QUIET_PERIOD_MS={_QUIET_PERIOD_MS}, _POLL_INTERVAL_MS={_POLL_INTERVAL_MS}")


def check_single_valid_candidate_exits_early(reporter: ValidationReporter) -> None:
    """규칙 2: 유효한(비어있지 않은) 목록 응답을 확인한 뒤 quiet period가
    지나면 hard cap(50틱) 전에 조기 종료해야 한다."""
    page = FakeAdaptivePage([(0, _place_response([("p1", "업체1")]))])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    expected_ticks = 1 + _QUIET_TICKS  # 감지 1틱 + quiet 누적 틱
    ok = (
        len(page.wait_calls) == expected_ticks
        and len(page.wait_calls) < _HARD_CAP_TICKS
        and result["adaptive_settle_early_exit"] is True
        and result["adaptive_settle_wait_ms"] == expected_ticks * _POLL_INTERVAL_MS
        and len(result["rows"]) == 1
    )
    if ok:
        reporter.pass_(f"단일 valid candidate: hard cap(50틱)보다 훨씬 적은 {expected_ticks}틱 만에 조기 종료, rows 1건 확보")
    else:
        reporter.fail(f"단일 valid candidate 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_parse_error_only_falls_back_to_hard_cap(reporter: ValidationReporter) -> None:
    """규칙 4: 첫(유일한) 후보가 parse error이면 조기 종료하지 않고 기존처럼
    hard cap까지 대기해야 한다."""
    page = FakeAdaptivePage([(0, _broken_response())])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = (
        len(page.wait_calls) == _HARD_CAP_TICKS
        and result["adaptive_settle_early_exit"] is False
        and result["adaptive_settle_wait_ms"] == 5000
        and result["parse_error_count"] == 1
        and result["rows"] == []
    )
    if ok:
        reporter.pass_(f"parse error만 있는 후보: 조기 종료하지 않고 hard cap({_HARD_CAP_TICKS}틱) 전체 대기, parse_error_count=1")
    else:
        reporter.fail(f"parse error 단독 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_no_candidate_falls_back_to_hard_cap(reporter: ValidationReporter) -> None:
    page = FakeAdaptivePage([])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = (
        len(page.wait_calls) == _HARD_CAP_TICKS
        and result["adaptive_settle_early_exit"] is False
        and result["timeout"] is True
        and result["candidate_response_count"] == 0
    )
    if ok:
        reporter.pass_("candidate 0건: hard cap 전체 대기, timeout=True(기존과 동일한 의미 보존)")
    else:
        reporter.fail(f"candidate 0건 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_late_valid_candidate_resets_quiet_period(reporter: ValidationReporter) -> None:
    """규칙 5: 첫 후보가 parse error여도(규칙 4) 이후 새 후보가 도착하면
    quiet 타이머가 다시 시작되어, 그 새 후보를 기준으로 조기 종료해야 한다."""
    page = FakeAdaptivePage([
        (0, _broken_response()),
        (300, _place_response([("p1", "업체1")])),
    ])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    # tick1~3(100~300ms)에 broken 처리+대기, tick3(300ms)에 valid 도착으로 quiet 리셋,
    # 이후 quiet_period_ms(750)를 채우는 데 8틱 추가 필요 -> 총 3+8=11틱.
    expected_ticks = 3 + _QUIET_TICKS
    ok = (
        len(page.wait_calls) == expected_ticks
        and result["adaptive_settle_early_exit"] is True
        and result["parse_error_count"] == 1
        and len(result["rows"]) == 1
    )
    if ok:
        reporter.pass_(f"늦게 도착한 valid 후보: quiet 타이머가 재시작되어 {expected_ticks}틱에 조기 종료, parse error 1건 + rows 1건 모두 확보")
    else:
        reporter.fail(f"quiet 재시작 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_two_valid_candidates_within_quiet_period_both_harvested(reporter: ValidationReporter) -> None:
    """valid 후보 2개가 quiet period 이내 간격으로 도착하면 quiet이 재시작되어
    둘 다 수집돼야 한다."""
    page = FakeAdaptivePage([
        (0, _place_response([("p1", "업체1")])),
        (400, _place_response([("p2", "업체2")])),
    ])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    expected_ticks = 4 + _QUIET_TICKS
    ok = (
        len(page.wait_calls) == expected_ticks
        and len(result["rows"]) == 2
        and result["candidate_response_count"] == 2
    )
    if ok:
        reporter.pass_(f"quiet 이내(400ms) 간격의 valid 후보 2개: 둘 다 수집(rows=2), {expected_ticks}틱에 조기 종료")
    else:
        reporter.fail(f"quiet 이내 2개 후보 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_second_valid_candidate_beyond_quiet_period_is_lost(reporter: ValidationReporter) -> None:
    """알려진 트레이드오프(반대 검토 AI 지적, 의도된 설계): quiet period가 지나
    조기 종료된 이후에 도착하는 후보는 수집되지 않는다 - 이 동작을 회귀
    없이 고정(pin)해 둔다."""
    page = FakeAdaptivePage([
        (0, _place_response([("p1", "업체1")])),
        (1000, _place_response([("p2", "업체2")])),  # quiet 종료(900ms) 이후 도착
    ])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    expected_ticks = 1 + _QUIET_TICKS  # p2는 배달 기회조차 없음
    ok = (
        len(page.wait_calls) == expected_ticks
        and result["candidate_response_count"] == 1
        and len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "p1"
    )
    if ok:
        reporter.pass_(f"알려진 트레이드오프 고정: quiet period(900ms) 이후 도착한 두 번째 valid 후보(1000ms)는 수집되지 않음(p1만 확보)")
    else:
        reporter.fail(f"늦은 두 번째 후보 유실 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_candidate_just_before_hard_cap_is_still_harvested(reporter: ValidationReporter) -> None:
    """hard cap 경계(마지막 틱) 바로 직전에 도착한 후보도 quiet period를 다
    채울 시간은 없어 조기 종료 혜택은 못 받지만, harvest 자체에서는 누락되지
    않아야 한다."""
    page = FakeAdaptivePage([(4900, _place_response([("p1", "업체1")]))])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = (
        len(page.wait_calls) == _HARD_CAP_TICKS
        and result["adaptive_settle_early_exit"] is False
        and result["candidate_response_count"] == 1
        and len(result["rows"]) == 1
    )
    if ok:
        reporter.pass_("hard cap 직전(4900ms) 도착 후보: 조기 종료는 안 되지만(hard cap까지 대기) harvest에서는 정상 수집됨")
    else:
        reporter.fail(f"hard cap 경계 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_response_json_called_exactly_once_per_candidate(reporter: ValidationReporter) -> None:
    """반대 검토 확인 사항: 폴링 루프의 peek 확인과 이후 harvest 단계가
    parsed_cache를 공유해, candidate 응답당 response.json()이 정확히 1회만
    호출되고 parse_error_count가 중복 집계되지 않아야 한다."""
    valid = _place_response([("p1", "업체1")])
    broken = _broken_response()
    page = FakeAdaptivePage([(0, broken), (0, valid)])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = (
        valid.json_call_count == 1
        and broken.json_call_count == 1
        and result["parse_error_count"] == 1
        and result["raw_item_count"] == 1
    )
    if ok:
        reporter.pass_("response.json() 호출 횟수: candidate당 정확히 1회(peek/harvest 공유), parse_error_count 중복 집계 없음")
    else:
        reporter.fail(f"json() 호출 횟수 결과가 예상과 다름: valid.json_call_count={valid.json_call_count}, broken.json_call_count={broken.json_call_count}, result={result}")


def check_empty_list_candidate_is_not_treated_as_valid(reporter: ValidationReporter) -> None:
    """반대 검토에서 발견된 결함 수정 확인: 파싱은 성공했지만 목록이 비어있는
    candidate(예: 검색 결과 0건)는 "valid"로 취급되어 조기 종료를 유발하면
    안 된다 - 그런 candidate만 있으면 hard cap까지 대기해야 한다(진짜 데이터가
    나중에 올 가능성을 배제하지 않기 위함)."""
    page = FakeAdaptivePage([(0, _place_response([]))])  # 빈 목록(파싱은 성공)
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = (
        len(page.wait_calls) == _HARD_CAP_TICKS
        and result["adaptive_settle_early_exit"] is False
        and result["candidate_response_count"] == 1
        and result["rows"] == []
    )
    if ok:
        reporter.pass_("빈 목록 candidate(파싱 성공, 항목 0개): valid로 취급되지 않아 hard cap까지 대기(조기 종료 결함 수정 확인)")
    else:
        reporter.fail(f"빈 목록 candidate 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_empty_then_late_valid_candidate_is_not_lost(reporter: ValidationReporter) -> None:
    """위 결함 수정이 실제로 데이터 유실을 막는지 확인: 빈 목록 candidate가
    먼저 오고, 진짜 데이터가 담긴 candidate가 quiet period(750ms)보다 늦게
    (예: 1000ms) 도착해도 hard cap 안에만 있으면 정상 수집돼야 한다."""
    page = FakeAdaptivePage([
        (0, _place_response([])),  # decoy: 파싱 성공하지만 빈 목록
        (1000, _place_response([("p1", "업체1")])),  # 진짜 데이터, quiet period보다 늦게 도착
    ])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = len(result["rows"]) == 1 and result["rows"][0]["place_id"] == "p1"
    if ok:
        reporter.pass_("빈 목록 decoy 이후 늦게 도착한 진짜 데이터(1000ms)가 유실 없이 정상 수집됨(valid 정의 수정의 핵심 효과)")
    else:
        reporter.fail(f"decoy+지연 데이터 결과가 예상과 다름: {result}")


def check_navigation_error_path_includes_adaptive_fields_with_defaults(reporter: ValidationReporter) -> None:
    """모든 반환 경로의 키 집합이 동일해야 한다(반대 검토 권장 사항) -
    navigation_error 조기 반환에도 adaptive 필드가 기본값으로 포함돼야 한다."""
    page = FakeAdaptivePage([], goto_error=Exception("Target page, context or browser has been closed"))
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = (
        result["navigation_error"] is True
        and result["adaptive_settle_wait_ms"] == 0
        and result["adaptive_settle_early_exit"] is False
    )
    if ok:
        reporter.pass_("navigation_error 경로: adaptive_settle_wait_ms=0/adaptive_settle_early_exit=False 기본값 포함(모든 반환 경로 키 집합 동일)")
    else:
        reporter.fail(f"navigation_error 경로 결과가 예상과 다름: {result}")


def check_captcha_detection_unaffected_by_adaptive_loop(reporter: ValidationReporter) -> None:
    """CAPTCHA probe는 여전히 대기 루프가 끝난 뒤(hard cap이든 조기 종료든)
    호출되며, 판정 로직 자체는 변경되지 않았어야 한다."""
    page = FakeAdaptivePage(
        [],
        captcha_selectors={"#wtm-captcha-root": FakeLocator(count=1, visible=True, box={"width": 100, "height": 100})},
    )
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    ok = result["active_captcha_detected"] is True and len(page.wait_calls) == _HARD_CAP_TICKS
    if ok:
        reporter.pass_("CAPTCHA 판정 무영향: candidate 없이도(hard cap 대기 후) active_captcha_detected=True 정상 판정")
    else:
        reporter.fail(f"CAPTCHA 판정 결과가 예상과 다름: {result}")


def check_non_candidate_429_during_quiet_period_is_detected(reporter: ValidationReporter) -> None:
    """quiet period 진행 중 candidate가 아닌 URL/resource_type의 HTTP 429
    응답이 도착해도 status_429_seen 감지가 누락되면 안 된다. 429 판정은
    _make_response_handler에서 is_candidate_response 여부와 무관하게(그보다
    먼저) 상태 코드만으로 수행되므로, candidate_response_count를 늘리지도
    않고 quiet 타이머를 "새 candidate 도착"처럼 재시작시키지도 않아야 한다
    - 즉 429가 전혀 없었을 때와 동일한 tick 수(1+_QUIET_TICKS)에 조기
    종료돼야 한다."""
    non_candidate_429 = FakeResponse("https://map.naver.com/", 429, "document")
    page = FakeAdaptivePage([
        (0, _place_response([("p1", "업체1")])),  # 정상 valid candidate
        (400, non_candidate_429),  # quiet period 진행 중 도착하는 non-candidate 429
    ])
    result = collect_network_query(page, JOB, 10, collected_at="2026-07-16")

    expected_ticks = 1 + _QUIET_TICKS  # 429는 candidate가 아니므로 quiet 타이머를 재시작시키지 않아야 함
    ok = (
        result["status_429_seen"] is True
        and result["candidate_response_count"] == 1
        and result["parse_error_count"] == 0
        and len(result["rows"]) >= 1
        and result["timeout"] is False
        and result["navigation_error"] is False
        and result["adaptive_settle_early_exit"] is True
        and result["adaptive_settle_wait_ms"] < 5000
        and len(page.wait_calls) == expected_ticks
        and non_candidate_429.json_call_count == 0
    )
    if ok:
        reporter.pass_(
            f"quiet period 중 non-candidate 429: status_429_seen=True로 감지되지만 "
            f"candidate_response_count는 그대로(1)이고 quiet 타이머도 재시작되지 않아 "
            f"{expected_ticks}틱에 정상 조기 종료(429 응답 json() 미호출 확인)"
        )
    else:
        reporter.fail(f"quiet period 중 non-candidate 429 결과가 예상과 다름: wait_calls={len(page.wait_calls)}, result={result}")


def check_response_handler_does_not_call_json(reporter: ValidationReporter) -> None:
    """규칙 7: response callback(handle_response) 안에서는 무거운 JSON
    파싱을 하지 않아야 한다 - 소스에 .json( 호출이 없는지 정적으로 확인."""
    source = inspect.getsource(network_browser_collector._make_response_handler)
    if ".json(" not in source:
        reporter.pass_("response callback 소스에 .json( 호출이 없음(status/url/resource_type만 확인, 무거운 파싱은 폴링 루프 메인 흐름에서만 발생)")
    else:
        reporter.fail(f"response callback 소스에 .json( 호출이 발견됨:\n{source}")


def main() -> int:
    reporter = ValidationReporter()

    check_constants_match_expected_defaults(reporter)
    check_single_valid_candidate_exits_early(reporter)
    check_parse_error_only_falls_back_to_hard_cap(reporter)
    check_no_candidate_falls_back_to_hard_cap(reporter)
    check_late_valid_candidate_resets_quiet_period(reporter)
    check_two_valid_candidates_within_quiet_period_both_harvested(reporter)
    check_second_valid_candidate_beyond_quiet_period_is_lost(reporter)
    check_candidate_just_before_hard_cap_is_still_harvested(reporter)
    check_response_json_called_exactly_once_per_candidate(reporter)
    check_empty_list_candidate_is_not_treated_as_valid(reporter)
    check_empty_then_late_valid_candidate_is_not_lost(reporter)
    check_navigation_error_path_includes_adaptive_fields_with_defaults(reporter)
    check_captcha_detection_unaffected_by_adaptive_loop(reporter)
    check_non_candidate_429_during_quiet_period_is_detected(reporter)
    check_response_handler_does_not_call_json(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
