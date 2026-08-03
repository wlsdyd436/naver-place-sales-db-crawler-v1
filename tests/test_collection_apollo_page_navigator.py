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


class FakeChildFrame:
    """child frame 흉내 - frame-aware probe가 page.frames로 접근하는 child frame.
    locator_map으로 selector별 FakeLocator를 반환하고, 나머지는 기본 empty locator."""

    def __init__(self, *, locator_map=None, locator_error=None):
        self._locator_map = locator_map or {}
        self._locator_error = locator_error

    def locator(self, selector):
        if self._locator_error is not None:
            raise self._locator_error
        return self._locator_map.get(selector, FakeLocator(count_value=0))


class FakePage:
    """Navigator 함수들이 실제로 접근하는 page 표면만 최소로 제공한다. 각
    check는 필요한 부분만 채워서 사용하고 나머지는 기본값(빈 결과)으로 둔다.
    frames_list는 frame-aware probe가 child frame을 순회할 때 사용된다."""

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
    # Production 수정 후 broad text selector 3개 제거 → #wtm-captcha-root 1개만 남음
    if len(selectors) < 1:
        reporter.fail(f"7. 사전 조건 실패: _CAPTCHA_PROBE_SELECTORS가 비어있음({selectors})")
        return

    # A. 첫 번째 selector(#wtm-captcha-root)에서 locator() 자체가 예외를 던지면
    # 예외를 흡수하고 나머지 selector로 진행해야 한다.
    # Production 수정 후 selectors가 1개뿐이므로 그 1개를 에러로 만들면 전체 실패 케이스.
    first_sel = selectors[0]
    locator_error_selectors = {first_sel: RuntimeError("locator boom")}
    page_err = FakePage(locator_error_selectors=locator_error_selectors)

    try:
        result_err = _probe_captcha_state(page_err)
    except Exception as exc:
        reporter.fail(f"7. CAPTCHA probe 예외 격리 실패: 예외가 밖으로 전파됨({exc!r})")
        return

    subcase_a_ok = result_err == {
        "marker_present": False,
        "visible": False,
        "bounding_box_area": 0.0,
        "click_intercepted_message": "",
    }

    # B. 정상 selector(#wtm-captcha-root)가 count=1, visible=True, box 존재 → active
    page_ok = FakePage(locator_map={
        first_sel: FakeLocator(count_value=1, visible=True, box={"width": 300, "height": 150}),
    })
    try:
        result_ok = _probe_captcha_state(page_ok)
    except Exception as exc:
        reporter.fail(f"7. CAPTCHA probe 정상 케이스에서 예외 전파됨: {exc!r}")
        return

    subcase_b_ok = (
        set(result_ok.keys()) == {"marker_present", "visible", "bounding_box_area", "click_intercepted_message"}
        and result_ok["marker_present"] is True
        and result_ok["visible"] is True
        and result_ok["bounding_box_area"] == 45000.0
        and result_ok["click_intercepted_message"] == ""
    )

    # C. 모든 selector가 실패(count=0) → 기본 반환 dict 유지
    all_fail_page = FakePage(locator_map={})
    try:
        all_fail_result = _probe_captcha_state(all_fail_page)
    except Exception as exc:
        reporter.fail(f"7. CAPTCHA probe 전체 실패 케이스에서 예외가 밖으로 전파됨: {exc!r}")
        return

    subcase_c_ok = all_fail_result == {
        "marker_present": False,
        "visible": False,
        "bounding_box_area": 0.0,
        "click_intercepted_message": "",
    }

    ok = subcase_a_ok and subcase_b_ok and subcase_c_ok
    if ok:
        reporter.pass_("7. CAPTCHA probe: locator() 예외를 흡수하고 기본 dict 반환(A), 정상 selector는 결과 반영(B), 전부 실패하면 기본 dict 유지(C)")
    else:
        reporter.fail(
            f"7. CAPTCHA probe 예외 격리 계약 실패: "
            f"subcase_a(예외흡수)={subcase_a_ok}({result_err}), "
            f"subcase_b(정상)={subcase_b_ok}({result_ok}), "
            f"subcase_c(전체실패)={subcase_c_ok}({all_fail_result})"
        )


def check_captcha_fp1_normal_business_name_jado(reporter: ValidationReporter) -> None:
    """CAPTCHA-FP-1: 정상 업체명 '왕광자동차공업사'가 visible DOM에 있어도
    #wtm-captcha-root가 없으면 active CAPTCHA가 아님.
    Production 수정 전: text=자동 selector가 오탐해 marker_present=True, visible=True가 됨.
    Production 수정 후: text=자동이 제거되므로 이 계약이 PASS 해야 함.
    """
    # '왕광자동차공업사'를 포함하는 marker_title DOM이 있어도,
    # #wtm-captcha-root는 없는 정상 검색 결과 화면을 시뮬레이션.
    # text=자동 selector가 이 DOM에 매칭된다면 오탐.
    page = FakePage(
        locator_map={
            # #wtm-captcha-root는 없음(count=0) — 정상
            "#wtm-captcha-root": FakeLocator(count_value=0),
            # text=자동 selector가 업체명을 매칭한다면 오탐이 발생하는 상황
            "text=자동": FakeLocator(count_value=1, visible=True, box={"width": 87.53, "height": 15}),
        }
    )

    result = _probe_captcha_state(page)

    # Production 수정 후: text=자동이 제거되므로 marker_present=False, visible=False
    # Production 수정 전(현재): text=자동이 오탐해 marker_present=True, visible=True — 이 체크가 FAIL
    ok = (
        result["marker_present"] is False
        and result["visible"] is False
        and result["bounding_box_area"] == 0.0
    )
    if ok:
        reporter.pass_("8. CAPTCHA-FP-1: 정상 업체명 '자동' 포함 DOM이 있어도 #wtm-captcha-root 없으면 active CAPTCHA 아님")
    else:
        reporter.fail(
            f"8. CAPTCHA-FP-1 실패: text=자동 selector가 정상 업체명을 오탐함 "
            f"→ marker_present={result['marker_present']}, visible={result['visible']}, "
            f"area={result['bounding_box_area']} (text=자동 제거 필요)"
        )


def check_captcha_fp2_normal_security_menu(reporter: ValidationReporter) -> None:
    """CAPTCHA-FP-2: 정상 네이버 메뉴의 '보안설정' 텍스트가 visible DOM에 있어도
    #wtm-captcha-root가 없으면 active CAPTCHA가 아님.
    Production 수정 전: text=보안 selector가 오탐.
    """
    page = FakePage(
        locator_map={
            "#wtm-captcha-root": FakeLocator(count_value=0),
            "text=보안": FakeLocator(count_value=1, visible=True, box={"width": 60, "height": 20}),
        }
    )

    result = _probe_captcha_state(page)

    ok = (
        result["marker_present"] is False
        and result["visible"] is False
    )
    if ok:
        reporter.pass_("9. CAPTCHA-FP-2: 정상 '보안설정' 메뉴가 visible이어도 #wtm-captcha-root 없으면 active CAPTCHA 아님")
    else:
        reporter.fail(
            f"9. CAPTCHA-FP-2 실패: text=보안 selector가 정상 메뉴를 오탐함 "
            f"→ marker_present={result['marker_present']}, visible={result['visible']} (text=보안 제거 필요)"
        )


def check_captcha_fp3_normal_content_with_saram(reporter: ValidationReporter) -> None:
    """CAPTCHA-FP-3: 정상 콘텐츠에 '사람' 문자열이 포함돼도 active CAPTCHA가 아님."""
    page = FakePage(
        locator_map={
            "#wtm-captcha-root": FakeLocator(count_value=0),
            "text=사람": FakeLocator(count_value=1, visible=True, box={"width": 50, "height": 10}),
        }
    )

    result = _probe_captcha_state(page)

    ok = (
        result["marker_present"] is False
        and result["visible"] is False
    )
    if ok:
        reporter.pass_("10. CAPTCHA-FP-3: 정상 콘텐츠의 '사람' 텍스트가 visible이어도 active CAPTCHA 아님")
    else:
        reporter.fail(
            f"10. CAPTCHA-FP-3 실패: text=사람 selector가 정상 콘텐츠를 오탐함 "
            f"→ marker_present={result['marker_present']}, visible={result['visible']} (text=사람 제거 필요)"
        )


def check_captcha_frame1_hidden_placeholder_in_child_frame(reporter: ValidationReporter) -> None:
    """CAPTCHA-FRAME-1: child frame 안에 #wtm-captcha-root가 존재하지만
    height=0(bounding box area=0)이면 active CAPTCHA가 아님.
    marker_present=True는 허용, visible은 locator.is_visible() 결과로 판단.
    """
    hidden_root = FakeLocator(count_value=1, visible=False, box={"width": 0, "height": 0})
    child_frame = FakeChildFrame(locator_map={"#wtm-captcha-root": hidden_root})
    # main page에는 #wtm-captcha-root 없음
    page = FakePage(
        locator_map={"#wtm-captcha-root": FakeLocator(count_value=0)},
        frames_list=[child_frame],
    )

    result = _probe_captcha_state(page)

    ok = (
        result["marker_present"] is True  # child frame에서 count>0이므로 marker 존재
        and result["visible"] is False     # is_visible=False이므로 visible 아님
        and result["bounding_box_area"] == 0.0  # area=0
    )
    if ok:
        reporter.pass_("11. CAPTCHA-FRAME-1: child frame의 hidden #wtm-captcha-root → marker_present=True지만 visible=False, area=0 → active CAPTCHA 아님")
    else:
        reporter.fail(
            f"11. CAPTCHA-FRAME-1 실패: marker_present={result['marker_present']}, "
            f"visible={result['visible']}, area={result['bounding_box_area']} "
            "(frame-aware probe 미구현 또는 hidden 판정 오류)"
        )


def check_captcha_frame2_and_frame3_visible_child_frame(reporter: ValidationReporter) -> None:
    """CAPTCHA-FRAME-2: child frame 안의 #wtm-captcha-root가 visible이고 area>0이면
    active CAPTCHA 신호 (marker_present=True, visible=True, area>0).

    CAPTCHA-FRAME-3: main frame hidden + 다른 child frame에 visible root가 있을 때
    첫 hidden에서 종료하지 않고 전체 frame을 순회해 visible 신호를 최종 채택.
    """
    # FRAME-2: main frame #wtm-captcha-root 없음, child frame 1에 visible root
    visible_root = FakeLocator(count_value=1, visible=True, box={"width": 400, "height": 300})
    child_frame2 = FakeChildFrame(locator_map={"#wtm-captcha-root": visible_root})
    page2 = FakePage(
        locator_map={"#wtm-captcha-root": FakeLocator(count_value=0)},
        frames_list=[child_frame2],
    )

    result2 = _probe_captcha_state(page2)

    frame2_ok = (
        result2["marker_present"] is True
        and result2["visible"] is True
        and result2["bounding_box_area"] == 120000.0  # 400 * 300
    )

    # FRAME-3: main frame에 hidden root, child1에 hidden root, child2에 visible root
    # frame-aware probe는 첫 hidden match에서 멈추지 않고 계속 탐색해야 함
    hidden_root = FakeLocator(count_value=1, visible=False, box={"width": 0, "height": 0})
    visible_root3 = FakeLocator(count_value=1, visible=True, box={"width": 350, "height": 200})
    child_frame3a = FakeChildFrame(locator_map={"#wtm-captcha-root": hidden_root})
    child_frame3b = FakeChildFrame(locator_map={"#wtm-captcha-root": visible_root3})
    page3 = FakePage(
        locator_map={"#wtm-captcha-root": FakeLocator(count_value=1, visible=False, box={"width": 0, "height": 0})},
        frames_list=[child_frame3a, child_frame3b],
    )

    result3 = _probe_captcha_state(page3)

    frame3_ok = (
        result3["marker_present"] is True
        and result3["visible"] is True
        and result3["bounding_box_area"] == 70000.0  # 350 * 200, child2의 visible 채택
    )

    ok = frame2_ok and frame3_ok
    if ok:
        reporter.pass_(
            "12. CAPTCHA-FRAME-2/3: child frame visible #wtm-captcha-root → active 신호(FRAME-2), "
            "main/child1 hidden + child2 visible → visible 신호 최종 채택(첫 hidden에서 미종료)(FRAME-3)"
        )
    else:
        reporter.fail(
            f"12. CAPTCHA-FRAME-2/3 실패: "
            f"FRAME-2: marker={result2['marker_present']}, visible={result2['visible']}, area={result2['bounding_box_area']}; "
            f"FRAME-3: marker={result3['marker_present']}, visible={result3['visible']}, area={result3['bounding_box_area']} "
            "(frame-aware probe 미구현)"
        )


def check_captcha_tp1_hidden_root_only_no_child_dialog(reporter: ValidationReporter) -> None:
    """CAPTCHA-TP-1: 실제 관측값(width=390, height=0, visible=False)과 동일한
    hidden root만 있고 그 내부에 challenge dialog가 전혀 없으면, child selector가
    추가돼도 기존 오탐 방지 계약(active 아님)이 그대로 유지돼야 한다."""
    hidden_root = FakeLocator(count_value=1, visible=False, box={"width": 390, "height": 0})
    page = FakePage(locator_map={"#wtm-captcha-root": hidden_root})
    result = _probe_captcha_state(page)
    ok = (
        result["marker_present"] is True
        and result["visible"] is False
        and result["bounding_box_area"] == 0.0
    )
    if ok:
        reporter.pass_("13. CAPTCHA-TP-1. hidden root만 있고 child dialog 없음 -> active 아님(기존 계약 유지)")
    else:
        reporter.fail(f"13. CAPTCHA-TP-1 실패: {result}")


def check_captcha_tp2_visible_child_dialog_despite_hidden_root(reporter: ValidationReporter) -> None:
    """CAPTCHA-TP-2: 실제 CAPTCHA 증거(root height=0/visible=False, 그러나 그
    내부 [role="dialog"][aria-modal="true"]는 visible+양수 bbox) 재현 - root
    자체의 visible/area만 보던 기존 계산으로는 이 경우를 놓쳤다. root subtree
    안의 challenge dialog를 발견하면 그 값을 채택해야 한다."""
    hidden_root = FakeLocator(count_value=1, visible=False, box={"width": 390, "height": 0})
    visible_child_dialog = FakeLocator(count_value=1, visible=True, box={"width": 300, "height": 200})
    page = FakePage(
        locator_map={
            "#wtm-captcha-root": hidden_root,
            '#wtm-captcha-root [role="dialog"][aria-modal="true"]': visible_child_dialog,
        }
    )
    result = _probe_captcha_state(page)
    ok = (
        result["marker_present"] is True
        and result["visible"] is True
        and result["bounding_box_area"] == 60000.0
    )
    if ok:
        reporter.pass_("14. CAPTCHA-TP-2. root는 hidden/height=0이어도 그 내부 visible challenge dialog를 발견해 visible=True/area 반영")
    else:
        reporter.fail(f"14. CAPTCHA-TP-2 실패: {result}")


def check_captcha_tp3_dialog_outside_root_ignored(reporter: ValidationReporter) -> None:
    """CAPTCHA-TP-3: #wtm-captcha-root 밖(페이지 전역)의 일반 dialog는 절대
    조회되지 않는다 - root selector 접두어 없는 전역 [role="dialog"] selector를
    다시 도입하지 않았음을 회귀 가드한다(오탐 방지)."""
    unrelated_dialog = FakeLocator(count_value=1, visible=True, box={"width": 500, "height": 400})
    page = FakePage(
        locator_map={
            "#wtm-captcha-root": FakeLocator(count_value=0),
            '[role="dialog"][aria-modal="true"]': unrelated_dialog,  # root 접두어 없음 - 절대 조회 안 됨
        }
    )
    result = _probe_captcha_state(page)
    ok = (
        result["marker_present"] is False
        and result["visible"] is False
        and result["bounding_box_area"] == 0.0
    )
    if ok:
        reporter.pass_("15. CAPTCHA-TP-3. root 밖의 일반 dialog는 조회되지 않고 무시됨(전역 selector 미도입 회귀 가드)")
    else:
        reporter.fail(f"15. CAPTCHA-TP-3 실패: {result}")


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
        check_captcha_fp1_normal_business_name_jado,
        check_captcha_fp2_normal_security_menu,
        check_captcha_fp3_normal_content_with_saram,
        check_captcha_frame1_hidden_placeholder_in_child_frame,
        check_captcha_frame2_and_frame3_visible_child_frame,
        check_captcha_tp1_hidden_root_only_no_child_dialog,
        check_captcha_tp2_visible_child_dialog_despite_hidden_root,
        check_captcha_tp3_dialog_outside_root_ignored,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return reporter.fail_count == 0


def test_apollo_page_navigator_contract():
    assert main() is True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
