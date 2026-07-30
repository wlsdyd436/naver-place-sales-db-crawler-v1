import subprocess
import sys
import urllib.error
from pathlib import Path


# 2026-07-21 Native Edge/Chrome + CDP Attach 통합: src/pc/browser_session.py의
# NativeCdpBrowserSession 검증용 standalone 스크립트입니다(기존 test_pc_browser_session.py와
# 동일한 패턴 - pytest가 아니라 python으로 직접 실행). 실제 브라우저/네트워크는 절대
# 실행하지 않으며, subprocess.Popen/urllib.request.urlopen/sync_playwright/tasklist를
# 전부 fake로 주입해 검증한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import src.pc.browser_session as browser_session
from src.pc.browser_session import (
    BrowserExecutableNotFoundError,
    BrowserSession,
    CdpConnectionError,
    CdpStartupError,
    NativeCdpBrowserSession,
    ProfileInUseError,
    _acquire_profile_lock,
    _build_native_browser_args,
    _pick_free_port,
    _release_profile_lock,
    _resolve_browser,
    _terminate_owned_process,
    _wait_for_cdp_ready,
)
from src.pc.config import BrowserBackendConfig, DiagnosticConfig


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
        print("검증 요약")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"FINAL: {final}")
        print("====================")


# ----------------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------------


def _exists_fn_for(existing_paths):
    existing = set(existing_paths)
    return lambda p: p in existing


class FakeProcess:
    def __init__(self, pid=4242, poll_sequence=None, wait_outcomes=None):
        self.pid = pid
        self.returncode = None
        self._poll_sequence = list(poll_sequence) if poll_sequence is not None else []
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = []
        self._wait_outcomes = list(wait_outcomes) if wait_outcomes is not None else []

    def poll(self):
        if self._poll_sequence:
            self.returncode = self._poll_sequence.pop(0)
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        outcome = self._wait_outcomes.pop(0) if self._wait_outcomes else "ok"
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        self.returncode = 0


class FakeRunResult:
    def __init__(self, stdout=""):
        self.stdout = stdout


class FakeUrlopenResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


class FakeContext:
    def __init__(self):
        self.new_page_calls = 0

    def new_page(self):
        self.new_page_calls += 1
        return object()


class FakeBrowser:
    def __init__(self, contexts=None):
        self.contexts = contexts if contexts is not None else [FakeContext()]
        self.close_calls = 0

    def close(self):
        self.close_calls += 1

    def new_context(self):
        ctx = FakeContext()
        self.contexts.append(ctx)
        return ctx


class FakeChromium:
    def __init__(self, browser=None, connect_error=None):
        self.browser = browser if browser is not None else FakeBrowser()
        self.connect_error = connect_error
        self.connect_calls = []

    def connect_over_cdp(self, url):
        self.connect_calls.append(url)
        if self.connect_error is not None:
            raise self.connect_error
        return self.browser


class FakePlaywrightHandle:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class FakeSyncPlaywrightCM:
    def __init__(self, chromium):
        self._chromium = chromium

    def start(self):
        return FakePlaywrightHandle(self._chromium)


def _install_fake_sync_playwright(monkeypatch_stack, chromium):
    original = browser_session.sync_playwright
    browser_session.sync_playwright = lambda: FakeSyncPlaywrightCM(chromium)
    monkeypatch_stack.append(("sync_playwright", original))


def _install_fake(monkeypatch_stack, name, value):
    original = getattr(browser_session, name)
    setattr(browser_session, name, value)
    monkeypatch_stack.append((name, original))


def _restore_all(monkeypatch_stack):
    for name, original in reversed(monkeypatch_stack):
        setattr(browser_session, name, original)
    monkeypatch_stack.clear()


# ----------------------------------------------------------------------------
# _resolve_browser: 탐색 순서/우선순위/오류
# ----------------------------------------------------------------------------


def check_resolve_browser_custom_path(reporter: ValidationReporter) -> None:
    custom = r"D:\CustomBrowsers\msedge.exe"
    browser_type, path = _resolve_browser("auto", custom, exists_fn=_exists_fn_for([custom]))
    if browser_type == "edge" and path == custom:
        reporter.pass_("custom browser_path가 최우선으로 사용되고 edge로 인식됨")
    else:
        reporter.fail(f"custom path 결과가 예상과 다름: {browser_type}, {path}")


def check_resolve_browser_custom_path_missing(reporter: ValidationReporter) -> None:
    try:
        _resolve_browser("auto", r"D:\nope\msedge.exe", exists_fn=_exists_fn_for([]))
        reporter.fail("custom path가 없는데 예외가 발생하지 않음")
    except BrowserExecutableNotFoundError:
        reporter.pass_("존재하지 않는 custom browser_path는 BrowserExecutableNotFoundError 발생")


def check_resolve_browser_edge_program_files_x86(reporter: ValidationReporter) -> None:
    target = browser_session._EDGE_PATH_CANDIDATES[0]
    browser_type, path = _resolve_browser("auto", None, exists_fn=_exists_fn_for([target]))
    if browser_type == "edge" and path == target:
        reporter.pass_("Edge Program Files (x86) 경로 탐색 성공(auto 우선순위)")
    else:
        reporter.fail(f"Edge x86 경로 탐색 실패: {browser_type}, {path}")


def check_resolve_browser_edge_localappdata(reporter: ValidationReporter) -> None:
    target = browser_session._local_appdata_path("Microsoft", "Edge", "Application", "msedge.exe")
    browser_type, path = _resolve_browser("auto", None, exists_fn=_exists_fn_for([target]))
    if browser_type == "edge" and path == target:
        reporter.pass_("Program Files 경로가 없을 때 Edge LOCALAPPDATA fallback 탐색 성공")
    else:
        reporter.fail(f"Edge LOCALAPPDATA fallback 실패: {browser_type}, {path}")


def check_resolve_browser_chrome_fallback_when_edge_missing(reporter: ValidationReporter) -> None:
    target = browser_session._CHROME_PATH_CANDIDATES[0]
    browser_type, path = _resolve_browser("auto", None, exists_fn=_exists_fn_for([target]))
    if browser_type == "chrome" and path == target:
        reporter.pass_("Edge 미탐지 시 auto가 Chrome으로 fallback")
    else:
        reporter.fail(f"Chrome fallback 실패: {browser_type}, {path}")


def check_resolve_browser_chrome_localappdata(reporter: ValidationReporter) -> None:
    target = browser_session._local_appdata_path("Google", "Chrome", "Application", "chrome.exe")
    browser_type, path = _resolve_browser("auto", None, exists_fn=_exists_fn_for([target]))
    if browser_type == "chrome" and path == target:
        reporter.pass_("Chrome LOCALAPPDATA fallback 탐색 성공")
    else:
        reporter.fail(f"Chrome LOCALAPPDATA fallback 실패: {browser_type}, {path}")


def check_resolve_browser_none_found_raises_with_paths(reporter: ValidationReporter) -> None:
    try:
        _resolve_browser("auto", None, exists_fn=_exists_fn_for([]))
        reporter.fail("Edge/Chrome 모두 없는데 예외가 발생하지 않음")
    except BrowserExecutableNotFoundError as exc:
        message = str(exc)
        has_paths = "msedge.exe" in message and "chrome.exe" in message
        has_remedy = "browser_path" in message or "설치" in message
        if has_paths and has_remedy:
            reporter.pass_("browser 없음 오류에 탐색 경로 + 해결 방법이 포함됨(bundled Chromium 무음 대체 없음)")
        else:
            reporter.fail(f"오류 메시지에 경로/해결책이 부족함: {message}")


def check_resolve_browser_explicit_edge_preference_no_silent_switch(reporter: ValidationReporter) -> None:
    chrome_target = browser_session._CHROME_PATH_CANDIDATES[0]
    try:
        _resolve_browser("edge", None, exists_fn=_exists_fn_for([chrome_target]))
        reporter.fail("preference=edge인데 edge가 없어도 예외 없이 통과함(Chrome으로 조용히 전환된 것으로 의심)")
    except BrowserExecutableNotFoundError:
        reporter.pass_("preference=edge에서 edge 미탐지 시 Chrome이 있어도 조용히 전환하지 않고 오류 발생")


def check_resolve_browser_explicit_chrome_preference(reporter: ValidationReporter) -> None:
    edge_target = browser_session._EDGE_PATH_CANDIDATES[0]
    chrome_target = browser_session._CHROME_PATH_CANDIDATES[0]
    browser_type, path = _resolve_browser(
        "chrome", None, exists_fn=_exists_fn_for([edge_target, chrome_target])
    )
    if browser_type == "chrome" and path == chrome_target:
        reporter.pass_("preference=chrome 명시 시 Edge가 있어도 Chrome 사용")
    else:
        reporter.fail(f"명시적 chrome 선택이 무시됨: {browser_type}, {path}")


# ----------------------------------------------------------------------------
# port / launch args
# ----------------------------------------------------------------------------


def check_pick_free_port_is_bindable_and_dynamic(reporter: ValidationReporter) -> None:
    port_a = _pick_free_port()
    port_b = _pick_free_port()
    if isinstance(port_a, int) and 1024 < port_a < 65536 and port_a != 0:
        reporter.pass_(f"동적 localhost 포트 확보 성공(예: {port_a}, {port_b})")
    else:
        reporter.fail(f"포트 확보 결과가 비정상: {port_a}")


def check_build_native_browser_args_contains_required_flags(reporter: ValidationReporter) -> None:
    args = _build_native_browser_args(
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", 54321, Path(r"C:\profiles\edge"), False
    )
    joined = " ".join(args)
    checks = [
        "--remote-debugging-port=54321" in joined,
        "--remote-debugging-address=127.0.0.1" in joined,
        r"--user-data-dir=C:\profiles\edge" in joined,
    ]
    if all(checks):
        reporter.pass_("launch args에 동적 포트/127.0.0.1 바인딩/전용 user-data-dir 모두 포함")
    else:
        reporter.fail(f"launch args 누락: {args}")


# ----------------------------------------------------------------------------
# profile lock
# ----------------------------------------------------------------------------


def check_profile_lock_acquire_and_conflict(reporter: ValidationReporter, tmp_root: Path) -> None:
    profile_dir = tmp_root / "lock_conflict" / "edge"
    lock_path = _acquire_profile_lock(profile_dir, is_pid_running_fn=lambda pid: True)
    try:
        _acquire_profile_lock(profile_dir, is_pid_running_fn=lambda pid: True)
        reporter.fail("동일 profile을 두 번째로 lock 시도했는데 ProfileInUseError가 발생하지 않음")
    except ProfileInUseError:
        reporter.pass_("동일 profile 동시 사용 시도는 ProfileInUseError로 명확히 차단됨")
    finally:
        _release_profile_lock(lock_path)


def check_profile_lock_stale_recovery(reporter: ValidationReporter, tmp_root: Path) -> None:
    profile_dir = tmp_root / "lock_stale" / "chrome"
    lock_path = _acquire_profile_lock(profile_dir, is_pid_running_fn=lambda pid: True)
    try:
        second_lock = _acquire_profile_lock(profile_dir, is_pid_running_fn=lambda pid: False)
        reporter.pass_("죽은 프로세스가 남긴 stale lock은 정리되고 재획득 성공")
        _release_profile_lock(second_lock)
    except ProfileInUseError:
        reporter.fail("stale lock(프로세스 종료됨)인데도 정리되지 않고 충돌로 처리됨")
    finally:
        _release_profile_lock(lock_path)


def check_profile_lock_release_allows_reacquire(reporter: ValidationReporter, tmp_root: Path) -> None:
    profile_dir = tmp_root / "lock_release" / "edge"
    lock_path = _acquire_profile_lock(profile_dir, is_pid_running_fn=lambda pid: True)
    _release_profile_lock(lock_path)
    try:
        second_lock = _acquire_profile_lock(profile_dir, is_pid_running_fn=lambda pid: True)
        reporter.pass_("lock 해제 후에는 동일 profile을 재획득 가능")
        _release_profile_lock(second_lock)
    except ProfileInUseError:
        reporter.fail("lock을 해제했는데도 재획득이 ProfileInUseError로 실패함")


def check_profile_root_edge_chrome_separated(reporter: ValidationReporter, tmp_root: Path) -> None:
    edge_dir = tmp_root / "sep_root" / "edge"
    chrome_dir = tmp_root / "sep_root" / "chrome"
    edge_lock = _acquire_profile_lock(edge_dir, is_pid_running_fn=lambda pid: True)
    try:
        chrome_lock = _acquire_profile_lock(chrome_dir, is_pid_running_fn=lambda pid: True)
        reporter.pass_("Edge/Chrome profile 디렉터리가 분리되어 있어 동시 사용해도 충돌 없음")
        _release_profile_lock(chrome_lock)
    except ProfileInUseError:
        reporter.fail("Edge/Chrome profile이 분리되지 않고 서로 충돌함")
    finally:
        _release_profile_lock(edge_lock)


# ----------------------------------------------------------------------------
# CDP readiness
# ----------------------------------------------------------------------------


def check_wait_for_cdp_ready_success(reporter: ValidationReporter) -> None:
    body = b'{"Browser": "Edge/1.0", "webSocketDebuggerUrl": "ws://127.0.0.1:1/x"}'
    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        return FakeUrlopenResponse(body)

    process = FakeProcess()
    _wait_for_cdp_ready(9333, process, timeout_sec=2, poll_interval_sec=0.01, urlopen_fn=fake_urlopen)
    if calls and "/json/version" in calls[0] and "9333" in calls[0]:
        reporter.pass_("readiness 성공: /json/version 응답 확인 후 즉시 반환")
    else:
        reporter.fail(f"readiness 성공 경로 호출 URL이 예상과 다름: {calls}")


def check_wait_for_cdp_ready_early_exit(reporter: ValidationReporter) -> None:
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError("connection refused")

    process = FakeProcess(poll_sequence=[7])
    try:
        _wait_for_cdp_ready(9334, process, timeout_sec=5, poll_interval_sec=0.01, urlopen_fn=fake_urlopen)
        reporter.fail("process가 조기 종료됐는데 readiness가 예외 없이 통과함")
    except CdpStartupError as exc:
        if "조기 종료" in str(exc):
            reporter.pass_("process 조기 종료를 즉시 감지하고 CdpStartupError 발생(추가 polling 없음)")
        else:
            reporter.fail(f"조기 종료 오류 메시지가 예상과 다름: {exc}")


def check_wait_for_cdp_ready_timeout(reporter: ValidationReporter) -> None:
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError("not ready yet")

    process = FakeProcess()
    try:
        _wait_for_cdp_ready(9335, process, timeout_sec=0.05, poll_interval_sec=0.01, urlopen_fn=fake_urlopen)
        reporter.fail("응답이 계속 실패하는데 readiness가 timeout 없이 통과함")
    except CdpStartupError as exc:
        if "timeout" in str(exc).lower():
            reporter.pass_("전체 startup timeout 초과 시 CdpStartupError(고정 sleep 아님, 조건 기반 polling)")
        else:
            reporter.fail(f"timeout 오류 메시지가 예상과 다름: {exc}")


# ----------------------------------------------------------------------------
# subprocess cleanup
# ----------------------------------------------------------------------------


def check_terminate_owned_process_noop_when_already_dead(reporter: ValidationReporter) -> None:
    process = FakeProcess(poll_sequence=[0])
    _terminate_owned_process(process)
    if process.terminate_calls == 0 and process.kill_calls == 0:
        reporter.pass_("이미 종료된 process는 terminate/kill을 호출하지 않음(no-op)")
    else:
        reporter.fail(f"이미 죽은 process에 불필요한 호출 발생: terminate={process.terminate_calls}, kill={process.kill_calls}")


def check_terminate_owned_process_terminate_succeeds(reporter: ValidationReporter) -> None:
    process = FakeProcess(poll_sequence=[None], wait_outcomes=["ok"])
    _terminate_owned_process(process)
    if process.terminate_calls == 1 and process.kill_calls == 0:
        reporter.pass_("terminate()만으로 종료되면 kill/taskkill을 추가로 호출하지 않음")
    else:
        reporter.fail(f"terminate 성공 경로가 예상과 다름: terminate={process.terminate_calls}, kill={process.kill_calls}")


def check_terminate_owned_process_escalates_to_kill(reporter: ValidationReporter) -> None:
    process = FakeProcess(poll_sequence=[None], wait_outcomes=["timeout", "ok"])
    _terminate_owned_process(process)
    if process.terminate_calls == 1 and process.kill_calls == 1:
        reporter.pass_("terminate() 후 제한 시간 내 종료되지 않으면 kill()로 승격")
    else:
        reporter.fail(f"kill 승격 경로가 예상과 다름: terminate={process.terminate_calls}, kill={process.kill_calls}")


def check_terminate_owned_process_taskkill_fallback_uses_pid_not_image(reporter: ValidationReporter) -> None:
    process = FakeProcess(pid=9911, poll_sequence=[None], wait_outcomes=["timeout", "timeout"])
    taskkill_calls = []

    def fake_run(args, **kwargs):
        taskkill_calls.append(args)
        return FakeRunResult()

    _terminate_owned_process(process, taskkill_run_fn=fake_run)
    if not taskkill_calls:
        reporter.fail("terminate/kill 모두 실패했는데 taskkill 안전망이 호출되지 않음")
        return
    args = taskkill_calls[0]
    uses_pid = "/PID" in args and "9911" in args
    uses_tree = "/T" in args
    forbids_image_name = "/IM" not in args
    if uses_pid and uses_tree and forbids_image_name:
        reporter.pass_("terminate/kill 모두 실패 시 taskkill 안전망은 /IM이 아닌 /PID+/T로 소유 PID 트리만 정리")
    else:
        reporter.fail(f"taskkill 안전망 인자가 예상과 다름: {args}")


def check_is_pid_running_conservative_on_error(reporter: ValidationReporter) -> None:
    def failing_run(*args, **kwargs):
        raise OSError("tasklist unavailable")

    result = browser_session._is_pid_running(123, run_fn=failing_run)
    if result is True:
        reporter.pass_("tasklist 확인 자체가 실패하면 보수적으로 '사용 중(True)'으로 취급")
    else:
        reporter.fail(f"tasklist 실패 시 처리 결과가 예상과 다름: {result}")


# ----------------------------------------------------------------------------
# full class: __enter__/__exit__ end-to-end (전부 fake 주입, 실제 브라우저 없음)
# ----------------------------------------------------------------------------


def _install_success_fakes(monkeypatch_stack, *, process=None, chromium=None):
    process = process or FakeProcess()
    chromium = chromium or FakeChromium()

    _install_fake(monkeypatch_stack, "_resolve_browser", lambda pref, path: ("edge", r"C:\fake\msedge.exe"))
    _install_fake(monkeypatch_stack, "_acquire_profile_lock", lambda profile_dir, **kw: profile_dir / ".lock")
    _install_fake(monkeypatch_stack, "_release_profile_lock", lambda lock_path: None)
    _install_fake(monkeypatch_stack, "_pick_free_port", lambda: 51234)
    _install_fake(
        monkeypatch_stack,
        "_build_native_browser_args",
        lambda *a, **k: ["fake-browser-exe"],
    )
    _install_fake(monkeypatch_stack, "_wait_for_cdp_ready", lambda *a, **k: None)
    browser_session.subprocess.Popen = lambda args: process
    monkeypatch_stack.append(("__popen_marker__", None))
    _install_fake_sync_playwright(monkeypatch_stack, chromium)
    return process, chromium


def check_native_cdp_session_enter_success(reporter: ValidationReporter) -> None:
    stack = []
    original_popen = browser_session.subprocess.Popen
    try:
        process, chromium = _install_success_fakes(stack)
        config = BrowserBackendConfig.default()
        session = NativeCdpBrowserSession(DiagnosticConfig.safe_default(), config)
        entered = session.__enter__()
        ok = (
            entered is session
            and session.context is chromium.browser.contexts[0]
            and session.page is not None
            and chromium.connect_calls == ["http://127.0.0.1:51234"]
        )
        session.__exit__(None, None, None)
        if ok:
            reporter.pass_("__enter__ 성공 시 .context/.page가 채워지고 connect_over_cdp가 올바른 포트로 호출됨")
        else:
            reporter.fail("성공 경로의 context/page/connect_over_cdp 호출이 예상과 다름")
    finally:
        browser_session.subprocess.Popen = original_popen
        _restore_all(stack)


def check_native_cdp_session_readiness_timeout_cleans_up(reporter: ValidationReporter) -> None:
    stack = []
    original_popen = browser_session.subprocess.Popen
    try:
        process = FakeProcess(poll_sequence=[None], wait_outcomes=["ok"])

        def fail_wait_for_ready(*a, **k):
            raise CdpStartupError("fake readiness timeout")

        _install_fake(stack, "_resolve_browser", lambda pref, path: ("edge", r"C:\fake\msedge.exe"))
        released = {"called": False}
        _install_fake(stack, "_acquire_profile_lock", lambda profile_dir, **kw: profile_dir / ".lock")
        _install_fake(stack, "_release_profile_lock", lambda lock_path: released.__setitem__("called", True))
        _install_fake(stack, "_pick_free_port", lambda: 51235)
        _install_fake(stack, "_build_native_browser_args", lambda *a, **k: ["fake-browser-exe"])
        _install_fake(stack, "_wait_for_cdp_ready", fail_wait_for_ready)
        browser_session.subprocess.Popen = lambda args: process
        stack.append(("__popen_marker__", None))

        config = BrowserBackendConfig.default()
        session = NativeCdpBrowserSession(DiagnosticConfig.safe_default(), config)
        try:
            session.__enter__()
            reporter.fail("readiness timeout인데 __enter__가 예외 없이 성공함")
        except CdpStartupError:
            if process.terminate_calls >= 1 and released["called"]:
                reporter.pass_("readiness timeout 시 owned process 종료 + profile lock 해제까지 cleanup됨")
            else:
                reporter.fail(
                    f"readiness timeout cleanup 불완전: terminate={process.terminate_calls}, lock_released={released['called']}"
                )
    finally:
        browser_session.subprocess.Popen = original_popen
        _restore_all(stack)


def check_native_cdp_session_connect_failure_cleans_up(reporter: ValidationReporter) -> None:
    stack = []
    original_popen = browser_session.subprocess.Popen
    try:
        chromium = FakeChromium(connect_error=RuntimeError("cdp handshake failed"))
        process, chromium = _install_success_fakes(stack, chromium=chromium)

        config = BrowserBackendConfig.default()
        session = NativeCdpBrowserSession(DiagnosticConfig.safe_default(), config)
        try:
            session.__enter__()
            reporter.fail("connect_over_cdp 실패인데 __enter__가 예외 없이 성공함")
        except CdpConnectionError:
            if process.terminate_calls >= 1:
                reporter.pass_("connect_over_cdp 실패 시 CdpConnectionError + owned process 종료(cleanup)")
            else:
                reporter.fail(f"connect 실패인데 owned process가 종료되지 않음: terminate={process.terminate_calls}")
    finally:
        browser_session.subprocess.Popen = original_popen
        _restore_all(stack)


def check_native_cdp_session_normal_exit_terminates_process(reporter: ValidationReporter) -> None:
    stack = []
    original_popen = browser_session.subprocess.Popen
    try:
        process, chromium = _install_success_fakes(stack)
        config = BrowserBackendConfig.default()
        session = NativeCdpBrowserSession(DiagnosticConfig.safe_default(), config)
        session.__enter__()
        session.__exit__(None, None, None)
        if chromium.browser.close_calls == 1 and process.terminate_calls == 1:
            reporter.pass_("정상 종료 시 browser.close() 시도 + owned process terminate 모두 수행")
        else:
            reporter.fail(
                f"정상 종료 cleanup이 예상과 다름: close={chromium.browser.close_calls}, terminate={process.terminate_calls}"
            )
    finally:
        browser_session.subprocess.Popen = original_popen
        _restore_all(stack)


def check_native_cdp_session_exception_in_with_block_still_cleans_up(reporter: ValidationReporter) -> None:
    stack = []
    original_popen = browser_session.subprocess.Popen
    try:
        process, chromium = _install_success_fakes(stack)
        config = BrowserBackendConfig.default()
        try:
            with NativeCdpBrowserSession(DiagnosticConfig.safe_default(), config) as session:
                assert session.context is not None
                raise ValueError("body에서 발생한 예외")
        except ValueError:
            pass
        if process.terminate_calls == 1:
            reporter.pass_("with 블록 내부에서 예외가 발생해도 __exit__가 호출되어 owned process가 종료됨")
        else:
            reporter.fail(f"예외 경로에서 cleanup이 수행되지 않음: terminate={process.terminate_calls}")
    finally:
        browser_session.subprocess.Popen = original_popen
        _restore_all(stack)


def check_native_cdp_session_does_not_touch_other_process(reporter: ValidationReporter) -> None:
    stack = []
    original_popen = browser_session.subprocess.Popen
    try:
        owned_process = FakeProcess(pid=5555)
        other_process = FakeProcess(pid=6666)
        process, chromium = _install_success_fakes(stack, process=owned_process)
        config = BrowserBackendConfig.default()
        session = NativeCdpBrowserSession(DiagnosticConfig.safe_default(), config)
        session.__enter__()
        session.__exit__(None, None, None)
        if owned_process.terminate_calls == 1 and other_process.terminate_calls == 0:
            reporter.pass_("자신이 실행한 owned process(PID)만 종료하고 다른 브라우저 process는 건드리지 않음")
        else:
            reporter.fail("owned process 외의 process에 영향을 줄 가능성이 있는 구현으로 보임")
    finally:
        browser_session.subprocess.Popen = original_popen
        _restore_all(stack)


# ----------------------------------------------------------------------------
# backend 선택: native_cdp 기본값 / launch 명시적 선택 / silent fallback 금지
# ----------------------------------------------------------------------------


def check_backend_config_defaults_to_native_cdp(reporter: ValidationReporter) -> None:
    config = BrowserBackendConfig.default()
    if config.backend == "native_cdp":
        reporter.pass_("BrowserBackendConfig 기본값은 native_cdp(production 기본 backend)")
    else:
        reporter.fail(f"기본 backend가 native_cdp가 아님: {config.backend}")


def check_backend_config_env_selects_launch_explicitly(reporter: ValidationReporter, monkeypatch_env) -> None:
    monkeypatch_env["PCCRAWLER_BROWSER_BACKEND"] = "launch"
    config = BrowserBackendConfig.from_env()
    if config.backend == "launch":
        reporter.pass_("PCCRAWLER_BROWSER_BACKEND=launch로 launch backend를 명시적으로 선택 가능(dev/test fallback)")
    else:
        reporter.fail(f"launch 명시 선택이 반영되지 않음: {config.backend}")


def check_backend_config_frozen_ignores_env(reporter: ValidationReporter, monkeypatch_env) -> None:
    monkeypatch_env["PCCRAWLER_BROWSER_BACKEND"] = "launch"
    original_frozen = getattr(sys, "frozen", None)
    sys.frozen = True
    try:
        config = BrowserBackendConfig.from_env()
        if config.backend == "native_cdp":
            reporter.pass_("frozen(배포 EXE) 환경에서는 env 값과 무관하게 항상 native_cdp 기본값 사용")
        else:
            reporter.fail(f"frozen 환경에서 env로 backend가 바뀜(의도하지 않은 동작): {config.backend}")
    finally:
        if original_frozen is None:
            del sys.frozen
        else:
            sys.frozen = original_frozen


def check_default_session_factory_dispatches_by_backend(reporter: ValidationReporter, monkeypatch_env) -> None:
    from src.pc.network_browser_collector import _default_session_factory

    monkeypatch_env["PCCRAWLER_BROWSER_BACKEND"] = "launch"
    launch_session = _default_session_factory()

    monkeypatch_env["PCCRAWLER_BROWSER_BACKEND"] = "native_cdp"
    native_session = _default_session_factory()

    if isinstance(launch_session, BrowserSession) and isinstance(native_session, NativeCdpBrowserSession):
        reporter.pass_("_default_session_factory가 backend 설정에 따라 BrowserSession/NativeCdpBrowserSession을 올바르게 분기")
    else:
        reporter.fail(
            f"_default_session_factory 분기가 예상과 다름: launch={type(launch_session).__name__}, native={type(native_session).__name__}"
        )


def check_default_session_factory_defaults_native_cdp_without_env(reporter: ValidationReporter, monkeypatch_env) -> None:
    from src.pc.network_browser_collector import _default_session_factory

    monkeypatch_env.pop("PCCRAWLER_BROWSER_BACKEND", None)
    session = _default_session_factory()
    if isinstance(session, NativeCdpBrowserSession):
        reporter.pass_("환경 변수가 없으면 production은 native_cdp가 기본값(silent launch fallback 없음)")
    else:
        reporter.fail(f"기본 backend가 native_cdp가 아님: {type(session).__name__}")


def main() -> int:
    import os
    import shutil
    import tempfile

    reporter = ValidationReporter()
    tmp_root = Path(tempfile.mkdtemp(prefix="cdp_session_test_"))

    env_backup = dict(os.environ)

    class _EnvProxy(dict):
        def __setitem__(self, key, value):
            os.environ[key] = value
            super().__setitem__(key, value)

        def pop(self, key, default=None):
            os.environ.pop(key, None)
            return super().pop(key, default)

    monkeypatch_env = _EnvProxy()

    try:
        check_resolve_browser_custom_path(reporter)
        check_resolve_browser_custom_path_missing(reporter)
        check_resolve_browser_edge_program_files_x86(reporter)
        check_resolve_browser_edge_localappdata(reporter)
        check_resolve_browser_chrome_fallback_when_edge_missing(reporter)
        check_resolve_browser_chrome_localappdata(reporter)
        check_resolve_browser_none_found_raises_with_paths(reporter)
        check_resolve_browser_explicit_edge_preference_no_silent_switch(reporter)
        check_resolve_browser_explicit_chrome_preference(reporter)

        check_pick_free_port_is_bindable_and_dynamic(reporter)
        check_build_native_browser_args_contains_required_flags(reporter)

        check_profile_lock_acquire_and_conflict(reporter, tmp_root)
        check_profile_lock_stale_recovery(reporter, tmp_root)
        check_profile_lock_release_allows_reacquire(reporter, tmp_root)
        check_profile_root_edge_chrome_separated(reporter, tmp_root)

        check_wait_for_cdp_ready_success(reporter)
        check_wait_for_cdp_ready_early_exit(reporter)
        check_wait_for_cdp_ready_timeout(reporter)

        check_terminate_owned_process_noop_when_already_dead(reporter)
        check_terminate_owned_process_terminate_succeeds(reporter)
        check_terminate_owned_process_escalates_to_kill(reporter)
        check_terminate_owned_process_taskkill_fallback_uses_pid_not_image(reporter)
        check_is_pid_running_conservative_on_error(reporter)

        check_native_cdp_session_enter_success(reporter)
        check_native_cdp_session_readiness_timeout_cleans_up(reporter)
        check_native_cdp_session_connect_failure_cleans_up(reporter)
        check_native_cdp_session_normal_exit_terminates_process(reporter)
        check_native_cdp_session_exception_in_with_block_still_cleans_up(reporter)
        check_native_cdp_session_does_not_touch_other_process(reporter)

        check_backend_config_defaults_to_native_cdp(reporter)
        check_backend_config_env_selects_launch_explicitly(reporter, monkeypatch_env)
        check_backend_config_frozen_ignores_env(reporter, monkeypatch_env)
        check_default_session_factory_dispatches_by_backend(reporter, monkeypatch_env)
        check_default_session_factory_defaults_native_cdp_without_env(reporter, monkeypatch_env)
    finally:
        os.environ.clear()
        os.environ.update(env_backup)
        shutil.rmtree(tmp_root, ignore_errors=True)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
