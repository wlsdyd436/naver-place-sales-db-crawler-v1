from pathlib import Path
import shutil
import sys


# Stage 2 청크1: src/pc/browser_session.py 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.config import DiagnosticConfig
from src.pc.diagnostics import DEFAULT_DIAGNOSTICS_ROOT
from src.pc.browser_session import BrowserSession, _select_launch_args


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

    def warn(self, message: str) -> None:
        self.warn_count += 1
        print(f"[WARN] {message}")

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
    def __init__(self, count_value=0, visible=True):
        self._count = count_value
        self._visible = visible

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        if isinstance(self._visible, Exception):
            raise self._visible
        return self._visible

    def wait_for(self, timeout=None):
        pass


class FakeFrame:
    def __init__(self, name="searchIframe", url="https://map.naver.com/search"):
        self.name = name
        self.url = url


class FakeFrameLocator:
    def __init__(self, should_fail=False):
        self._should_fail = should_fail

    def locator(self, selector):
        if self._should_fail:
            raise TimeoutError("frame locator wait_for timeout")
        return FakeLocator(count_value=1)


class FakeMouse:
    def __init__(self):
        self.wheel_calls = 0

    def wheel(self, dx, dy):
        self.wheel_calls += 1


class FakePage:
    def __init__(
        self,
        named_frame=None,
        frame_locator_fails=False,
        frames=None,
        goto_error=None,
        url="https://map.naver.com/v5/search/test",
        html="<html>fake</html>",
        locator_map=None,
    ):
        self._named_frame = named_frame
        self._frame_locator_fails = frame_locator_fails
        self.frames = frames or []
        self._goto_error = goto_error
        self.url = url
        self._html = html
        self.mouse = FakeMouse()
        self.wait_for_timeout_calls = []
        self._locator_map = locator_map or {}

    def frame(self, name=None):
        return self._named_frame

    def frame_locator(self, selector):
        return FakeFrameLocator(should_fail=self._frame_locator_fails)

    def goto(self, url, wait_until=None, timeout=None):
        if self._goto_error is not None:
            raise self._goto_error

    def wait_for_timeout(self, ms):
        self.wait_for_timeout_calls.append(ms)

    def content(self):
        return self._html

    def screenshot(self, path=None, full_page=False):
        Path(path).write_bytes(b"fake-png-bytes")

    def locator(self, selector):
        return self._locator_map.get(selector, FakeLocator(count_value=0))


def _make_session(diagnostic_config, page):
    session = BrowserSession(diagnostic_config)
    session.page = page
    return session


def check_launch_args_offscreen_by_default(reporter: ValidationReporter) -> None:
    args = _select_launch_args(False)
    if "--window-position=-32000,-32000" in args:
        reporter.pass_("visible=False -> offscreen(--window-position=-32000,-32000) args 선택")
    else:
        reporter.fail(f"offscreen args가 선택되지 않음: {args}")


def check_launch_args_onscreen_when_visible(reporter: ValidationReporter) -> None:
    args = _select_launch_args(True)
    if "--window-position=-32000,-32000" not in args and "--window-size=1400,900" in args:
        reporter.pass_("visible=True -> onscreen args 선택(오프스크린 좌표 미포함)")
    else:
        reporter.fail(f"onscreen args가 예상과 다름: {args}")


def check_goto_swallows_timeout(reporter: ValidationReporter) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    page = FakePage(goto_error=PlaywrightTimeoutError("Timeout 40000ms exceeded."))
    session = _make_session(DiagnosticConfig.safe_default(), page)
    try:
        session.goto("https://map.naver.com/v5/search/test")
        reporter.pass_("goto 타임아웃 발생해도 예외 전파 없이 계속 진행")
    except Exception as exc:
        reporter.fail(f"goto 타임아웃이 전파됨: {type(exc).__name__}: {exc}")


def check_find_search_frame_by_name(reporter: ValidationReporter) -> None:
    named_frame = FakeFrame()
    page = FakePage(named_frame=named_frame)
    session = _make_session(DiagnosticConfig.safe_default(), page)
    frame = session.find_search_frame()
    if frame is named_frame:
        reporter.pass_("page.frame(name='searchIframe')로 즉시 탐색 성공")
    else:
        reporter.fail(f"named frame 탐색 실패: {frame}")


def check_find_search_frame_fallback_to_frames_list(reporter: ValidationReporter) -> None:
    fallback_frame = FakeFrame(name="", url="https://map.naver.com/v5/search/searchIframe")
    page = FakePage(named_frame=None, frame_locator_fails=True, frames=[fallback_frame])
    session = _make_session(DiagnosticConfig.safe_default(), page)
    frame = session.find_search_frame()
    if frame is fallback_frame:
        reporter.pass_("named/frame_locator 실패 시 page.frames fallback으로 탐색 성공")
    else:
        reporter.fail(f"frames fallback 탐색 실패: {frame}")


def check_find_search_frame_not_found(reporter: ValidationReporter) -> None:
    page = FakePage(named_frame=None, frame_locator_fails=True, frames=[])
    session = _make_session(DiagnosticConfig.safe_default(), page)
    frame = session.find_search_frame()
    if frame is None:
        reporter.pass_("searchIframe을 찾을 수 없으면 None 반환(예외 없음)")
    else:
        reporter.fail(f"None이 아닌 값을 반환함: {frame}")


def check_find_entry_frame_by_name(reporter: ValidationReporter) -> None:
    named_frame = FakeFrame(name="entryIframe", url="https://map.naver.com/entry/place/1234567")
    page = FakePage(named_frame=named_frame)
    session = _make_session(DiagnosticConfig.safe_default(), page)
    frame = session.find_entry_frame()
    if frame is named_frame:
        reporter.pass_("page.frame(name='entryIframe')로 상세 프레임 즉시 탐색 성공")
    else:
        reporter.fail(f"entryIframe named frame 탐색 실패: {frame}")


def check_find_entry_frame_fallback_to_frames_list(reporter: ValidationReporter) -> None:
    fallback_frame = FakeFrame(name="", url="https://map.naver.com/entry/place/1234567")
    page = FakePage(named_frame=None, frame_locator_fails=True, frames=[fallback_frame])
    session = _make_session(DiagnosticConfig.safe_default(), page)
    frame = session.find_entry_frame()
    if frame is fallback_frame:
        reporter.pass_("named/frame_locator 실패 시 page.frames의 'entry' 프레임 fallback 탐색")
    else:
        reporter.fail(f"entryIframe frames fallback 탐색 실패: {frame}")


def check_find_entry_frame_not_found(reporter: ValidationReporter) -> None:
    page = FakePage(named_frame=None, frame_locator_fails=True, frames=[])
    session = _make_session(DiagnosticConfig.safe_default(), page)
    frame = session.find_entry_frame()
    if frame is None:
        reporter.pass_("entryIframe을 찾을 수 없으면 None 반환(예외 없음)")
    else:
        reporter.fail(f"None이 아닌 값을 반환함: {frame}")


def check_probe_captcha_dom_present_true(reporter: ValidationReporter) -> None:
    page = FakePage(locator_map={"#wtm-captcha-root": FakeLocator(count_value=1, visible=True)})
    session = _make_session(DiagnosticConfig.safe_default(), page)
    if session.probe_captcha_dom_present() is True:
        reporter.pass_("CAPTCHA 후보 DOM이 count>0 & visible이면 probe True 반환")
    else:
        reporter.fail("CAPTCHA DOM이 있는데 probe가 False를 반환함")


def check_probe_captcha_dom_present_false(reporter: ValidationReporter) -> None:
    page = FakePage(locator_map={})
    session = _make_session(DiagnosticConfig.safe_default(), page)
    if session.probe_captcha_dom_present() is False:
        reporter.pass_("CAPTCHA 후보 DOM이 없으면 probe False 반환")
    else:
        reporter.fail("CAPTCHA DOM이 없는데 probe가 True를 반환함")


def check_keep_open_if_configured_waits_when_enabled(reporter: ValidationReporter) -> None:
    page = FakePage()
    config = DiagnosticConfig(keep_open_on_error=True, keep_open_timeout_sec=3)
    session = _make_session(config, page)
    session.keep_open_if_configured()
    if page.wait_for_timeout_calls == [3000]:
        reporter.pass_("keep_open_on_error=True -> keep_open_timeout_sec(초)만큼 wait_for_timeout 호출")
    else:
        reporter.fail(f"keep_open 대기 호출이 예상과 다름: {page.wait_for_timeout_calls}")


def check_keep_open_if_configured_noop_when_disabled(reporter: ValidationReporter) -> None:
    page = FakePage()
    config = DiagnosticConfig.safe_default()
    session = _make_session(config, page)
    session.keep_open_if_configured()
    if page.wait_for_timeout_calls == []:
        reporter.pass_("keep_open_on_error=False(기본 안전 모드) -> wait_for_timeout 미호출")
    else:
        reporter.fail(f"기본 설정인데 대기가 호출됨: {page.wait_for_timeout_calls}")


def check_capture_diagnostics_writes_when_enabled(reporter: ValidationReporter) -> None:
    page = FakePage()
    config = DiagnosticConfig(capture_artifacts=True)
    session = _make_session(config, page)

    before_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    result = session.capture_diagnostics(label="세션캡처테스트키워드", exception=RuntimeError("boom"))
    after_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    new_dirs = [d for d in (after_dirs - before_dirs) if "세션캡처테스트키워드" in d.name]

    if result is not None and new_dirs and (new_dirs[0] / "metadata.json").exists():
        reporter.pass_("capture_artifacts=True -> session.capture_diagnostics가 진단 산출물 저장")
    else:
        reporter.fail(f"세션 진단 캡처 결과가 예상과 다름: result={result}, new_dirs={new_dirs}")

    for d in new_dirs:
        shutil.rmtree(d, ignore_errors=True)


def check_capture_diagnostics_noop_when_disabled(reporter: ValidationReporter) -> None:
    page = FakePage()
    config = DiagnosticConfig.safe_default()
    session = _make_session(config, page)

    before_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    result = session.capture_diagnostics(label="세션캡처끔테스트키워드", exception=RuntimeError("boom"))
    after_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    new_dirs = [d for d in (after_dirs - before_dirs) if "세션캡처끔테스트키워드" in d.name]

    if result is None and not new_dirs:
        reporter.pass_("capture_artifacts=False(기본 안전 모드) -> session.capture_diagnostics가 no-op")
    else:
        reporter.fail(f"기본 설정인데 진단 산출물이 생성됨: result={result}, new_dirs={new_dirs}")
        for d in new_dirs:
            shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    reporter = ValidationReporter()

    check_launch_args_offscreen_by_default(reporter)
    check_launch_args_onscreen_when_visible(reporter)
    check_goto_swallows_timeout(reporter)
    check_find_search_frame_by_name(reporter)
    check_find_search_frame_fallback_to_frames_list(reporter)
    check_find_search_frame_not_found(reporter)
    check_find_entry_frame_by_name(reporter)
    check_find_entry_frame_fallback_to_frames_list(reporter)
    check_find_entry_frame_not_found(reporter)
    check_probe_captcha_dom_present_true(reporter)
    check_probe_captcha_dom_present_false(reporter)
    check_keep_open_if_configured_waits_when_enabled(reporter)
    check_keep_open_if_configured_noop_when_disabled(reporter)
    check_capture_diagnostics_writes_when_enabled(reporter)
    check_capture_diagnostics_noop_when_disabled(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
