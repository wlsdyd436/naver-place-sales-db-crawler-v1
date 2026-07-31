from pathlib import Path
import sys


# Apollo 목록 페이지 DOM 탐색·polling/settle 대기(src/collection/
# apollo_page_navigator.py)의 private 심볼(_probe_captcha_state/
# _find_search_frame/_find_page_button/_wait_for_next_page_settle/
# _wait_for_apollo_list_ready/_APOLLO_FULL_STATE_JS/_QUIET_PERIOD_MS/
# _POLL_INTERVAL_MS) 계약 고정용 standalone 스크립트. 이 파일은 다음 단계
# 리팩토링(예: _find_search_frame 중복 제거) 전에 현재 동작(fallback 순서,
# 예외 격리, polling·대기 계산, 반환 dict 계약)을 characterization test로
# 고정하는 것이 유일한 목적이며, 실제 Playwright page/frame 객체는 전혀
# 다루지 않고 최소 Fake만 사용한다(실제 Playwright 접속 없음). 기존
# tests/test_collection_apollo_list_collector.py, tests/test_browser_session.py의
# Fake 객체와 의도적으로 독립적으로 재구현한다(파일 간 import 없음 - 기존
# 관례 그대로).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.browser.session import _CAPTCHA_PROBE_SELECTORS
from src.collection.apollo_page_navigator import (
    _APOLLO_FULL_STATE_JS,
    _POLL_INTERVAL_MS,
    _find_page_button,
    _find_search_frame,
    _probe_captcha_state,
    _wait_for_apollo_list_ready,
    _wait_for_next_page_settle,
)


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


class FakeFrameLocator:
    """page.frame_locator("#searchIframe")가 반환하는 객체 흉내 - .locator("body")
    ->.first->.wait_for(timeout=...) 체인만 제공한다(자기 자신을 body locator로도
    사용해 클래스 수를 늘리지 않는다)."""

    def __init__(self):
        self.locator_calls: list = []
        self.wait_for_calls: list = []

    def locator(self, selector):
        self.locator_calls.append(selector)
        return self

    @property
    def first(self):
        return self

    def wait_for(self, timeout=None):
        self.wait_for_calls.append(timeout)


class FakeFrame:
    """검색 frame 흉내. name/url(frames 목록 fallback 매칭용),
    evaluate(Apollo state 폴링용), get_by_role(페이지 버튼 조회용) 표면을
    모두 제공하되, 각 check는 그중 필요한 것만 사용한다."""

    def __init__(self, *, name="", url="", evaluate_sequence=None, get_by_role_error=None):
        self.name = name
        self.url = url
        self._evaluate_sequence = list(evaluate_sequence) if evaluate_sequence is not None else []
        self.evaluate_calls: list = []
        self._get_by_role_error = get_by_role_error
        self.get_by_role_calls: list = []
        self.button_locator = object()

    def evaluate(self, script):
        self.evaluate_calls.append(script)
        if len(self._evaluate_sequence) > 1:
            return self._evaluate_sequence.pop(0)
        return self._evaluate_sequence[0]

    def get_by_role(self, role, name=None, exact=None):
        self.get_by_role_calls.append((role, name, exact))
        if self._get_by_role_error is not None:
            raise self._get_by_role_error
        return self.button_locator


class FakeLocator:
    """CAPTCHA probe용 locator 흉내 - count()/is_visible()/bounding_box() 각각
    독립적으로 정상값 또는 예외를 설정할 수 있다."""

    def __init__(self, *, count_value=0, count_error=None, visible=False, visible_error=None, box=None, box_error=None):
        self._count = count_value
        self._count_error = count_error
        self._visible = visible
        self._visible_error = visible_error
        self._box = box
        self._box_error = box_error

    @property
    def first(self):
        return self

    def count(self):
        if self._count_error is not None:
            raise self._count_error
        return self._count

    def is_visible(self, timeout=300):
        if self._visible_error is not None:
            raise self._visible_error
        return self._visible

    def bounding_box(self):
        if self._box_error is not None:
            raise self._box_error
        return self._box


class FakePage:
    """Navigator 함수들이 실제로 접근하는 page 표면만 최소로 제공한다. 각
    check는 필요한 부분만 채워서 사용하고 나머지는 기본값(빈 결과)으로 둔다."""

    def __init__(
        self, *,
        frame_sequence=None,
        frame_locator=None,
        frames_list=None,
        frames_error=None,
        locator_map=None,
        locator_error_selectors=None,
    ):
        self.frame_calls = 0
        self._frame_sequence = list(frame_sequence) if frame_sequence is not None else []
        self.frame_locator_calls: list = []
        self._frame_locator = frame_locator
        self._frames_list = frames_list if frames_list is not None else []
        self._frames_error = frames_error
        self.frames_accessed = False
        self._locator_map = locator_map or {}
        self._locator_error_selectors = locator_error_selectors or {}
        self.wait_for_timeout_calls: list = []

    def frame(self, name=None):
        self.frame_calls += 1
        if self._frame_sequence:
            return self._frame_sequence.pop(0)
        return None

    def frame_locator(self, selector):
        self.frame_locator_calls.append(selector)
        return self._frame_locator

    @property
    def frames(self):
        self.frames_accessed = True
        if self._frames_error is not None:
            raise self._frames_error
        return self._frames_list

    def locator(self, selector):
        if selector in self._locator_error_selectors:
            raise self._locator_error_selectors[selector]
        return self._locator_map.get(selector, FakeLocator(count_value=0))

    def wait_for_timeout(self, ms):
        self.wait_for_timeout_calls.append(ms)


class ObserverCountContext:
    """_QueryObservationContext의 candidate_response_count 속성만 흉내내는
    최소 duck-typed 객체 - _wait_for_next_page_settle은 이 속성만 읽는다."""

    def __init__(self, candidate_response_count=0):
        self.candidate_response_count = candidate_response_count


def _extractor(apollo_state, expected_query, expected_start):
    """_wait_for_apollo_list_ready가 extractor를 어떻게 호출하는지(인자·호출
    시점)만 검증하면 되므로, extract_main_place_list_from_apollo의 실제 필드
    파싱 로직과 무관한 최소 계약만 흉내낸다: apollo_state가 None이면
    미준비(error 존재), dict면 준비됨(error 없음)."""
    _extractor.calls.append((apollo_state, expected_query, expected_start))
    if apollo_state is None:
        return {"error": "not_ready", "items": []}
    return {"error": "", "items": ["row"], "apollo_state_seen": apollo_state}


_extractor.calls = []


def check_find_search_frame_frame_locator_fallback(reporter: ValidationReporter) -> None:
    target_frame = FakeFrame(name="searchIframe", url="https://map.naver.com/p/search")
    frame_locator = FakeFrameLocator()
    page = FakePage(frame_sequence=[None, target_frame], frame_locator=frame_locator)

    result = _find_search_frame(page)

    ok = (
        result is target_frame
        and page.frame_calls == 2
        and page.frame_locator_calls == ["#searchIframe"]
        and frame_locator.locator_calls == ["body"]
        and frame_locator.wait_for_calls == [5000]
        and page.frames_accessed is False
    )
    if ok:
        reporter.pass_("1. frame_locator fallback: #searchIframe + body.first.wait_for(5000) 후 두 번째 frame() 호출로 성공, frames 목록은 불필요하게 접근하지 않음")
    else:
        reporter.fail(
            f"1. frame_locator fallback 계약 실패: result={result!r}, frame_calls={page.frame_calls}, "
            f"frame_locator_calls={page.frame_locator_calls}, locator_calls={frame_locator.locator_calls}, "
            f"wait_for_calls={frame_locator.wait_for_calls}, frames_accessed={page.frames_accessed}"
        )


def check_find_search_frame_frames_list_fallback(reporter: ValidationReporter) -> None:
    frame_locator = FakeFrameLocator()
    non_matching = FakeFrame(name="", url="https://map.naver.com/p/other")
    matching = FakeFrame(name="searchIframe", url="https://map.naver.com/p/search")
    page = FakePage(
        frame_sequence=[None, None],
        frame_locator=frame_locator,
        frames_list=[non_matching, matching],
    )

    result = _find_search_frame(page)

    ok = result is matching and page.frames_accessed is True
    if ok:
        reporter.pass_("2. 1·2단계 실패 후 frames 목록에서 name+url 결합·소문자화로 'search' 포함 frame만 선택하고 불일치 frame은 건너뜀")
    else:
        reporter.fail(f"2. frames 목록 fallback 계약 실패: result={result!r}, frames_accessed={page.frames_accessed}")


def check_find_search_frame_not_found_and_exception_absorbed(reporter: ValidationReporter) -> None:
    # A. 모든 탐색 단계가 정상적으로 실패 -> None
    non_matching = FakeFrame(name="", url="https://map.naver.com/p/other")
    page_a = FakePage(
        frame_sequence=[None, None],
        frame_locator=FakeFrameLocator(),
        frames_list=[non_matching],
    )
    result_a = _find_search_frame(page_a)
    subcase_a_ok = result_a is None

    # B. 마지막 page.frames 접근 자체가 예외를 던짐 -> 예외를 밖으로 전파하지 않고 None
    page_b = FakePage(
        frame_sequence=[None, None],
        frame_locator=FakeFrameLocator(),
        frames_error=RuntimeError("frames access boom"),
    )
    try:
        result_b = _find_search_frame(page_b)
        subcase_b_raised = False
    except Exception:
        result_b = None
        subcase_b_raised = True
    subcase_b_ok = (not subcase_b_raised) and result_b is None

    ok = subcase_a_ok and subcase_b_ok
    if ok:
        reporter.pass_("3. 모든 단계 실패 시 None 반환(A), page.frames 접근 예외도 밖으로 전파하지 않고 None 반환(B)")
    else:
        reporter.fail(
            f"3. 미발견/예외 흡수 계약 실패: subcase_a_ok={subcase_a_ok}(result={result_a!r}), "
            f"subcase_b_ok={subcase_b_ok}(raised={subcase_b_raised}, result={result_b!r})"
        )


def check_find_page_button_locator_contract(reporter: ValidationReporter) -> None:
    frame = FakeFrame()
    result = _find_page_button(frame, 3)
    normal_ok = result is frame.button_locator and frame.get_by_role_calls == [("button", "3", True)]

    error_frame = FakeFrame(get_by_role_error=RuntimeError("get_by_role boom"))
    error_result = _find_page_button(error_frame, 4)
    error_ok = error_result is None and error_frame.get_by_role_calls == [("button", "4", True)]

    ok = normal_ok and error_ok
    if ok:
        reporter.pass_("4. _find_page_button: role='button', name=str(target_page_number), exact=True로 조회한 locator를 그대로 반환, frame API 예외 시 None 반환")
    else:
        reporter.fail(
            f"4. _find_page_button 계약 실패: normal_ok={normal_ok}(calls={frame.get_by_role_calls}), "
            f"error_ok={error_ok}(calls={error_frame.get_by_role_calls})"
        )


def check_wait_for_apollo_list_ready_polls_until_success(reporter: ValidationReporter) -> None:
    ready_state = {"a": 1}
    sequence = [
        {"available": False, "apollo_state": None, "oversized": False},
        {"available": False, "apollo_state": None, "oversized": False},
        {"available": True, "apollo_state": ready_state, "oversized": False},
    ]
    frame = FakeFrame(evaluate_sequence=sequence)
    page = FakePage()
    _extractor.calls = []

    result = _wait_for_apollo_list_ready(page, frame, "테스트쿼리", 0, hard_cap_ms=5000, extractor=_extractor)

    ok = (
        result == {"error": "", "items": ["row"], "apollo_state_seen": ready_state}
        and frame.evaluate_calls == [_APOLLO_FULL_STATE_JS] * 3
        and page.wait_for_timeout_calls == [_POLL_INTERVAL_MS, _POLL_INTERVAL_MS]
        and len(_extractor.calls) == 3
        and _extractor.calls[0] == (None, "테스트쿼리", 0)
        and _extractor.calls[-1] == (ready_state, "테스트쿼리", 0)
    )
    if ok:
        reporter.pass_("5. _wait_for_apollo_list_ready: _APOLLO_FULL_STATE_JS만 evaluate에 전달하며 _POLL_INTERVAL_MS 단위로 대기하다 준비되면 extractor 반환 dict를 그대로 반환(hard cap 전 종료, 불필요한 추가 evaluate 없음)")
    else:
        reporter.fail(
            f"5. Apollo 폴링 계약 실패: result={result}, evaluate_calls={frame.evaluate_calls}, "
            f"wait_calls={page.wait_for_timeout_calls}, extractor_calls={_extractor.calls}"
        )


def check_wait_for_next_page_settle_hard_cap(reporter: ValidationReporter) -> None:
    ctx = ObserverCountContext(candidate_response_count=5)
    page = FakePage()
    ensure_parsed_calls: list = []

    def fake_ensure_parsed(index):
        ensure_parsed_calls.append(index)
        return {"items": [], "error": False}

    hard_cap_ms = 300
    result = _wait_for_next_page_settle(page, ctx, fake_ensure_parsed, 5, hard_cap_ms=hard_cap_ms)

    expected_ticks = hard_cap_ms // _POLL_INTERVAL_MS
    ok = (
        result == {"got_new_response": False, "final_count": 5, "elapsed_ms": hard_cap_ms}
        and page.wait_for_timeout_calls == [_POLL_INTERVAL_MS] * expected_ticks
        and ctx.candidate_response_count == 5
        and ensure_parsed_calls == []
    )
    if ok:
        reporter.pass_("6. _wait_for_next_page_settle: candidate_response_count가 끝까지 증가하지 않으면 _POLL_INTERVAL_MS 단위로 hard cap까지 대기 후 got_new_response=False로 종료(ensure_parsed 미호출, ctx 변경 없음)")
    else:
        reporter.fail(
            f"6. settle hard cap 계약 실패: result={result}, wait_calls={page.wait_for_timeout_calls}, "
            f"candidate_response_count={ctx.candidate_response_count}, ensure_parsed_calls={ensure_parsed_calls}"
        )


def check_probe_captcha_state_exception_isolation(reporter: ValidationReporter) -> None:
    selectors = list(_CAPTCHA_PROBE_SELECTORS)
    if len(selectors) != 4:
        reporter.fail(f"7. 사전 조건 실패: _CAPTCHA_PROBE_SELECTORS 개수가 4가 아님({selectors})")
        return

    # A. selector별로 locator()/count()/is_visible()/bounding_box() 각 단계에서
    # 예외를 던지되, 정상 selector(뒤쪽)의 결과는 그대로 반영돼야 한다.
    locator_map = {
        selectors[1]: FakeLocator(count_error=ValueError("count boom")),
        selectors[2]: FakeLocator(count_value=1, visible_error=TypeError("visible boom")),
        selectors[3]: FakeLocator(count_value=1, visible=True, box_error=KeyError("box boom")),
    }
    locator_error_selectors = {selectors[0]: RuntimeError("locator boom")}
    page = FakePage(locator_map=locator_map, locator_error_selectors=locator_error_selectors)

    try:
        result = _probe_captcha_state(page)
    except Exception as exc:
        reporter.fail(f"7. CAPTCHA probe 예외 격리 실패: 예외가 밖으로 전파됨({exc!r})")
        return

    subcase_a_ok = (
        set(result.keys()) == {"marker_present", "visible", "bounding_box_area", "click_intercepted_message"}
        and result["marker_present"] is True
        and result["visible"] is True
        and result["bounding_box_area"] == 0.0
        and result["click_intercepted_message"] == ""
    )

    # B. 모든 selector가 실패(locator()/count() 예외 또는 count=0) -> 기본 반환 dict 유지
    all_fail_map = {
        selectors[1]: FakeLocator(count_value=0),
        selectors[2]: FakeLocator(count_error=RuntimeError("count boom 2")),
    }
    all_fail_error_selectors = {
        selectors[0]: RuntimeError("locator boom 2"),
        selectors[3]: RuntimeError("locator boom 3"),
    }
    all_fail_page = FakePage(locator_map=all_fail_map, locator_error_selectors=all_fail_error_selectors)
    try:
        all_fail_result = _probe_captcha_state(all_fail_page)
    except Exception as exc:
        reporter.fail(f"7. CAPTCHA probe 전체 실패 케이스에서 예외가 밖으로 전파됨: {exc!r}")
        return

    subcase_b_ok = all_fail_result == {
        "marker_present": False,
        "visible": False,
        "bounding_box_area": 0.0,
        "click_intercepted_message": "",
    }

    ok = subcase_a_ok and subcase_b_ok
    if ok:
        reporter.pass_("7. CAPTCHA probe: selector별 locator()/count()/is_visible()/bounding_box() 예외를 각각 흡수하고 다음 selector로 진행(뒤쪽 정상 selector 결과 반영), 전부 실패하면 기본 dict 유지")
    else:
        reporter.fail(f"7. CAPTCHA probe 예외 격리 계약 실패: subcase_a={result}, subcase_b={all_fail_result}")


def main() -> bool:
    reporter = ValidationReporter()
    checks = [
        check_find_search_frame_frame_locator_fallback,
        check_find_search_frame_frames_list_fallback,
        check_find_search_frame_not_found_and_exception_absorbed,
        check_find_page_button_locator_contract,
        check_wait_for_apollo_list_ready_polls_until_success,
        check_wait_for_next_page_settle_hard_cap,
        check_probe_captcha_state_exception_isolation,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return reporter.fail_count == 0


def test_apollo_page_navigator_contract():
    assert main() is True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
