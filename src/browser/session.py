# Playwright 브라우저 생명주기(launch/context/page)와 진단 캡처 트리거를 소유합니다.
# 이 모듈은 목록 탐색/페이지네이션/파싱 로직을 갖지 않으며(apollo_list_collector.py/
# place_mapper.py 책임), CAPTCHA 우회/자동 해결을 시도하지 않습니다. 진단 캡처는
# page가 살아있는 이 계층에서 호출자가 명시적으로 수행해야 합니다(teardown 이후에는
# 캡처가 불가능하기 때문).
#
# 2026-07-21 Native Edge/Chrome + CDP Attach 통합: 이 파일 하단의 NativeCdpBrowserSession은
# 별도 클래스로 추가됐으며, 위 BrowserSession(launch 방식)은 수정하지 않고 그대로
# 개발·테스트용 fallback으로 보존한다.
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.browser.config import BrowserBackendConfig
from src.diagnostics import (
    DEFAULT_DIAGNOSTICS_ROOT,
    capture_page_diagnostics,
    create_diagnostic_run_dir,
)

_VIEWPORT = {"width": 1400, "height": 900}
_OFFSCREEN_ARGS = ["--window-position=-32000,-32000", "--window-size=1400,900"]
_ONSCREEN_ARGS = ["--window-size=1400,900"]

# 진단 신호 전용 probe selector입니다. 2026-07-01 진단 기록에 따라 is_visible()
# 단독 판정은 신뢰할 수 없으므로, 안전 종료 여부(주 판정)는 절대 이 값에 의존하지
# 않고 safety.classify_exception(실제 발생한 예외 메시지)에 맡깁니다.
_CAPTCHA_PROBE_SELECTORS = [
    "#wtm-captcha-root",
    "text=보안",
    "text=사람",
    "text=자동",
]


def _select_launch_args(visible: bool) -> list:
    """visible 여부에 따라 온스크린/오프스크린 launch args를 선택합니다."""
    return list(_ONSCREEN_ARGS) if visible else list(_OFFSCREEN_ARGS)


class BrowserSession:
    """PC 단일 엔진 Playwright 브라우저 생명주기 컨텍스트 매니저.

    with BrowserSession(diagnostic_config) as session:
        session.goto(url)
        frame = session.find_search_frame()
        ...

    정상/예외 모든 경로에서 __exit__가 확정적으로 teardown합니다. 실패 시
    진단 캡처는 teardown 이전, 즉 이 with 블록 내부(page가 살아있는 상태)에서
    호출자가 session.capture_diagnostics(...)를 호출해 수행해야 합니다.
    """

    def __init__(self, diagnostic_config):
        self.diagnostic_config = diagnostic_config
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        args = _select_launch_args(self.diagnostic_config.visible)
        # 2026-06-04 pc_crawler.py 기록: PC 지도는 headless에서 DOM이 달라지므로
        # 항상 headless=False로 실행하고, visible=False면 화면 밖 창으로 띄운다.
        self.browser = self._playwright.chromium.launch(headless=False, args=args)
        self.context = self.browser.new_context(viewport=_VIEWPORT)
        self.page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._teardown()
        return False

    def _teardown(self) -> None:
        for closer in (self.context, self.browser):
            if closer is None:
                continue
            try:
                closer.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self.context = None
        self.browser = None
        self.page = None
        self._playwright = None

    def goto(self, url: str, timeout: int = 40000, settle_timeout: int = 5000) -> None:
        """pc_crawler.py 동작 보존: 로드 타임아웃이어도 현재 DOM으로 계속 진행합니다."""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            self.page.wait_for_timeout(settle_timeout)
        except PlaywrightTimeoutError:
            print("[browser_session] page load timeout, continue with current DOM")

    def find_search_frame(self):
        """pc_crawler.py _find_search_frame 이식(동작 보존)."""
        page = self.page
        try:
            frame = page.frame(name="searchIframe")
            if frame:
                print("[browser_session] searchIframe found")
                return frame
        except Exception:
            pass

        try:
            frame_locator = page.frame_locator("#searchIframe")
            frame_locator.locator("body").first.wait_for(timeout=5000)
            frame = page.frame(name="searchIframe")
            if frame:
                print("[browser_session] searchIframe found")
                return frame
        except Exception:
            pass

        for frame in page.frames:
            frame_id = f"{frame.name} {frame.url}".lower()
            if "search" in frame_id:
                print("[browser_session] searchIframe found")
                return frame

        print("[browser_session] searchIframe not found")
        return None

    def find_entry_frame(self):
        """entryIframe(상세 패널)을 우선 찾고, 실패 시 frames fallback을 사용합니다.

        find_search_frame과 동일한 패턴이며, 업체 상세(대표전화/전체주소) 추출을
        위해 사용합니다. 이 메서드는 프레임을 찾기만 하고 클릭/네비게이션/대기는
        호출자가 담당합니다.
        """
        page = self.page
        try:
            frame = page.frame(name="entryIframe")
            if frame:
                print("[browser_session] entryIframe found")
                return frame
        except Exception:
            pass

        try:
            frame_locator = page.frame_locator("#entryIframe")
            frame_locator.locator("body").first.wait_for(timeout=5000)
            frame = page.frame(name="entryIframe")
            if frame:
                print("[browser_session] entryIframe found")
                return frame
        except Exception:
            pass

        for frame in page.frames:
            frame_id = f"{frame.name} {frame.url}".lower()
            if "entry" in frame_id:
                print("[browser_session] entryIframe found")
                return frame

        return None

    def probe_captcha_dom_present(self, frame=None) -> bool:
        """CAPTCHA DOM 존재 여부 probe. 진단 신호(로그/참고용)로만 사용하고, 이 결과로
        안전 종료/재시도 등 제어 흐름을 바꾸지 않습니다. 주 판정은 항상
        safety.classify_exception(실제 발생한 예외)이 담당합니다.
        """
        targets = [self.page]
        if frame is not None:
            targets.append(frame)
        for target in targets:
            for selector in _CAPTCHA_PROBE_SELECTORS:
                try:
                    element = target.locator(selector).first
                    if element.count() > 0 and element.is_visible(timeout=300):
                        return True
                except Exception:
                    continue
        return False

    def keep_open_if_configured(self) -> None:
        """keep_open_on_error=True이면 keep_open_timeout_sec만큼 브라우저를 유지합니다(bounded).

        호출자가 진단 캡처 이후, teardown 직전에 명시적으로 호출해야 합니다.
        capture_artifacts 여부와 무관하게 동작합니다.
        """
        if not self.diagnostic_config.keep_open_on_error:
            return
        timeout_sec = self.diagnostic_config.keep_open_timeout_sec
        if timeout_sec <= 0 or self.page is None:
            return
        print(f"[browser_session] keep_open_on_error: {timeout_sec}s 대기")
        try:
            self.page.wait_for_timeout(timeout_sec * 1000)
        except Exception:
            pass

    def capture_diagnostics(self, label: str, exception=None, safety_decision=None):
        """page가 살아있는 상태에서 진단 산출물을 저장합니다(진단 캡처의 1차 책임 계층).

        capture_artifacts=False이거나 page가 없으면 아무 것도 하지 않고 None을
        반환합니다(고객용 안전 모드에서는 저장이 발생하지 않음).
        """
        if not self.diagnostic_config.capture_artifacts or self.page is None:
            return None
        reason = getattr(safety_decision, "reason", None)
        reason_value = getattr(reason, "value", "unknown") if reason is not None else "unknown"
        run_dir = create_diagnostic_run_dir(DEFAULT_DIAGNOSTICS_ROOT, f"{label}_{reason_value}")
        return capture_page_diagnostics(
            self.page, run_dir, label=label, exception=exception, safety_decision=safety_decision
        )


# ============================================================================
# NativeCdpBrowserSession: Windows 네이티브 Edge/Chrome + CDP Attach
# ============================================================================
#
# 2026-07-21 근거: cdp_validation_tests/comprehensive_cdp_tester.py로 수행한
# Edge 2회·Chrome 2회 실측(서울특별시 강동구 천호동 카페, 최대 300건)에서
# subprocess.Popen(전용 --user-data-dir + --remote-debugging-port) 후
# connect_over_cdp()로 연결하는 방식이 4회 모두 CAPTCHA/HTTP 403·405·429
# 없이 300건(70/70/70/70/20) 수집에 성공했다. 반면 기존 Playwright launch
# 방식은 동일 검색어의 page 2 요청에서 HTTP 405가 반복 재현되어(PROJECT_
# STATE.md 2026-07-20 기록) 20건에서 안전 중단됐다. 이 결과는 "현재 Windows
# 환경과 검증 검색에서 Playwright launch 환경과 다른 결과를 보였다"는
# 의미이며, 특정 fingerprint 항목이 차단 원인이라거나 CDP가 CAPTCHA를
# 영구적으로 우회한다는 의미가 아니다. CAPTCHA/HTTP 403·405·429 감지와
# 안전 중단(apollo_list_collector.py/plan_runner.py)은 이
# backend 교체와 무관하게 그대로 유지된다.
#
# 이 클래스는 BrowserSession과 동일한 context manager 계약(.context/.page,
# __enter__/__exit__)만 제공한다 - 실제 production 소비자인
# ApolloFirstListCollector(apollo_list_collector.py)는 session의
# .context/.page만 사용하므로 그 외 메서드는 추가하지 않는다(요청 범위 외
# 기능 추가 금지).


class BrowserExecutableNotFoundError(RuntimeError):
    """Edge/Chrome 실행 파일을 찾지 못했을 때 발생. bundled Chromium으로 조용히
    대체하지 않고 탐색한 경로와 해결 방법을 메시지에 포함한다."""


class ProfileInUseError(RuntimeError):
    """전용 profile 디렉터리가 이미 다른 실행 중인 프로세스에 의해 사용 중일 때 발생."""


class CdpStartupError(RuntimeError):
    """브라우저 프로세스 시작 또는 CDP readiness(/json/version) 확보에 실패했을 때 발생."""


class CdpConnectionError(RuntimeError):
    """CDP readiness는 확인됐으나 connect_over_cdp()/context/page 준비에 실패했을 때 발생."""


_EDGE_PATH_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
_CHROME_PATH_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

_PROFILE_LOCK_FILENAME = ".naver_crawler_profile.lock"


def _local_appdata_path(*parts: str) -> str | None:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None
    return os.path.join(local_appdata, *parts)


def _edge_candidates() -> list:
    candidates = list(_EDGE_PATH_CANDIDATES)
    la = _local_appdata_path("Microsoft", "Edge", "Application", "msedge.exe")
    if la:
        candidates.append(la)
    return candidates


def _chrome_candidates() -> list:
    candidates = list(_CHROME_PATH_CANDIDATES)
    la = _local_appdata_path("Google", "Chrome", "Application", "chrome.exe")
    if la:
        candidates.append(la)
    return candidates


def _first_existing(paths, exists_fn) -> str | None:
    for p in paths:
        if p and exists_fn(p):
            return p
    return None


def _not_found_message(searched_types: list) -> str:
    lines = ["Edge/Chrome 실행 파일을 찾지 못했습니다. 탐색한 경로:"]
    if "edge" in searched_types:
        lines.extend(f"  - {p}" for p in _edge_candidates())
    if "chrome" in searched_types:
        lines.extend(f"  - {p}" for p in _chrome_candidates())
    lines.append(
        "해결 방법: Microsoft Edge 또는 Google Chrome을 설치하거나, "
        "BrowserBackendConfig.browser_path(또는 PCCRAWLER_BROWSER_PATH 환경 변수)로 "
        "실행 파일 경로를 직접 지정하세요."
    )
    return "\n".join(lines)


def _resolve_browser(browser_preference: str, browser_path, *, exists_fn=os.path.isfile):
    """browser_preference(auto/edge/chrome)와 custom browser_path로 실제 실행 파일을 찾는다.

    우선순위: 1) custom browser_path 2) Edge 3) Chrome(browser_preference="auto" 기준).
    찾지 못하면 BrowserExecutableNotFoundError(탐색 경로 + 해결 방법 포함)를 발생시킨다.
    """
    if browser_path:
        if exists_fn(browser_path):
            browser_type = "edge" if "msedge" in os.path.basename(browser_path).lower() else "chrome"
            return browser_type, browser_path
        raise BrowserExecutableNotFoundError(
            f"지정한 custom browser path를 찾을 수 없습니다: {browser_path}"
        )

    edge_path = _first_existing(_edge_candidates(), exists_fn)
    chrome_path = _first_existing(_chrome_candidates(), exists_fn)

    if browser_preference == "edge":
        if edge_path:
            return "edge", edge_path
        raise BrowserExecutableNotFoundError(_not_found_message(["edge"]))
    if browser_preference == "chrome":
        if chrome_path:
            return "chrome", chrome_path
        raise BrowserExecutableNotFoundError(_not_found_message(["chrome"]))

    # auto: Edge 우선, Chrome fallback (지시서 §6 우선순위)
    if edge_path:
        return "edge", edge_path
    if chrome_path:
        return "chrome", chrome_path
    raise BrowserExecutableNotFoundError(_not_found_message(["edge", "chrome"]))


def _is_pid_running(pid: int, *, run_fn=subprocess.run) -> bool:
    """Windows tasklist 기반 PID 생존 확인(best-effort). 확인 자체가 실패하면
    보수적으로 '사용 중'(True)으로 취급해 잘못된 lock 해제를 방지한다."""
    try:
        result = run_fn(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return str(pid) in (result.stdout or "")
    except Exception:
        return True


def _acquire_profile_lock(profile_dir: Path, *, is_pid_running_fn=_is_pid_running) -> Path:
    """profile_dir 전용 lock 파일을 원자적으로 생성한다(os.O_CREAT|O_EXCL).

    이미 lock이 있으면 그 PID가 아직 살아있는지 확인한다 - 살아있으면
    ProfileInUseError(동일 profile을 두 프로세스가 동시에 쓸 수 없음), 죽은
    프로세스가 남긴 stale lock이면 정리하고 재시도한다. launch backend로의
    자동 fallback이나 다른 브라우저로의 조용한 변경은 하지 않는다.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    lock_path = profile_dir / _PROFILE_LOCK_FILENAME
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return lock_path
    except FileExistsError:
        pass

    stale = False
    try:
        existing_pid = int(lock_path.read_text().strip())
        stale = not is_pid_running_fn(existing_pid)
    except Exception:
        stale = False

    if not stale:
        raise ProfileInUseError(
            f"profile_in_use: '{profile_dir}'는 이미 다른 실행 중인 프로세스가 사용 중입니다. "
            "동일 profile로 두 세션을 동시에 실행할 수 없습니다. 기존 실행이 끝난 뒤 다시 시도하세요."
        )

    try:
        lock_path.unlink()
    except Exception:
        pass
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    return lock_path


def _release_profile_lock(lock_path) -> None:
    if lock_path is None:
        return
    try:
        Path(lock_path).unlink()
    except Exception:
        pass


def _pick_free_port() -> int:
    """localhost에서 사용 가능한 임시 포트를 확보한다(포트 선택과 브라우저 bind
    사이의 race는 호출자(__enter__)의 제한된 재시도로 처리한다)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_native_browser_args(browser_path: str, port: int, profile_dir: Path, visible: bool) -> list:
    args = [
        browser_path,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    args.extend(_select_launch_args(visible))
    return args


def _wait_for_cdp_ready(
    port: int,
    process: subprocess.Popen,
    timeout_sec: float,
    *,
    poll_interval_sec: float = 0.3,
    urlopen_fn=urllib.request.urlopen,
) -> None:
    """`/json/version`이 유효한 JSON으로 응답할 때까지 조건 기반으로 대기한다.

    고정된 긴 sleep 하나로 대체하지 않는다. process가 조기 종료되면 즉시
    CdpStartupError를 발생시키고(추가 polling 없음), 전체 timeout을 넘기면
    마지막 오류와 함께 CdpStartupError를 발생시킨다.
    """
    deadline = time.monotonic() + timeout_sec
    url = f"http://127.0.0.1:{port}/json/version"
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CdpStartupError(
                f"브라우저 프로세스가 CDP 준비 전에 조기 종료됨(exit code={process.returncode})"
            )
        try:
            with urlopen_fn(url, timeout=1) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("webSocketDebuggerUrl") or data.get("Browser"):
                    return
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = exc
        time.sleep(poll_interval_sec)
    raise CdpStartupError(f"CDP readiness timeout({timeout_sec}s): {url}. 마지막 오류: {last_error}")


def _terminate_owned_process(
    process,
    *,
    terminate_wait_sec: float = 5.0,
    kill_wait_sec: float = 5.0,
    taskkill_run_fn=subprocess.run,
) -> None:
    """자신이 실행한 process만 종료한다(PID 기준). taskkill /IM은 사용하지 않는다.

    순서: terminate() -> 제한 시간 wait -> (필요 시) kill() -> 제한 시간 wait ->
    (그래도 살아있으면 마지막 안전망으로) `taskkill /PID <pid> /T /F` - 이미지
    이름이 아닌 소유 PID 트리 한정이므로 사용자의 다른 Edge/Chrome 창에는
    영향을 주지 않는다(Chrome/Edge는 다중 프로세스이므로 root PID 종료만으로
    자식 프로세스가 남을 가능성에 대비한 안전망).
    """
    if process is None or process.poll() is not None:
        return

    try:
        process.terminate()
    except Exception:
        pass
    try:
        process.wait(timeout=terminate_wait_sec)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        process.kill()
    except Exception:
        pass
    try:
        process.wait(timeout=kill_wait_sec)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        taskkill_run_fn(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


class NativeCdpBrowserSession:
    """Windows 네이티브 Edge/Chrome을 전용 profile+remote-debugging-port로 실행한 뒤
    Playwright connect_over_cdp()로 연결하는 브라우저 세션.

    with NativeCdpBrowserSession(diagnostic_config, backend_config) as session:
        collector = session.context.new_page()  # 등, BrowserSession과 동일 계약

    자신이 subprocess.Popen으로 실행한 프로세스의 PID만 종료하며, 사용자의
    기존 Edge/Chrome 창에는 영향을 주지 않는다. 정상/예외 모든 경로에서
    __exit__가 확정적으로 teardown한다(playwright 연결 정리 -> owned process
    종료 -> profile lock 해제 순서).
    """

    def __init__(self, diagnostic_config, backend_config=None):
        self.diagnostic_config = diagnostic_config
        self.backend_config = backend_config or BrowserBackendConfig.default()
        self._playwright = None
        self._process = None
        self._lock_path = None
        self._port = None
        self.browser = None
        self.context = None
        self.page = None
        # 진단/Live 검증 보고용(실제 제어 흐름에는 쓰이지 않음) - 실제로 선택된
        # 브라우저 종류·경로·PID·CDP 포트·profile 경로를 확인할 수 있게 노출한다.
        self.browser_type = None
        self.browser_path = None
        self.profile_dir = None

    def __enter__(self):
        browser_type, browser_path = _resolve_browser(
            self.backend_config.browser_preference, self.backend_config.browser_path
        )
        self.browser_type = browser_type
        self.browser_path = browser_path
        profile_dir = Path(self.backend_config.profile_root) / browser_type
        self.profile_dir = profile_dir
        self._lock_path = _acquire_profile_lock(profile_dir)

        try:
            self._start_process_with_retry(browser_path, profile_dir)
            self._connect_over_cdp()
        except Exception:
            self._teardown()
            raise

        return self

    def _start_process_with_retry(self, browser_path: str, profile_dir: Path) -> None:
        max_attempts = max(1, self.backend_config.cdp_port_bind_max_attempts)
        last_error = None
        for _ in range(max_attempts):
            port = _pick_free_port()
            args = _build_native_browser_args(
                browser_path, port, profile_dir, self.diagnostic_config.visible
            )
            try:
                process = subprocess.Popen(args)
            except OSError as exc:
                last_error = exc
                continue

            try:
                _wait_for_cdp_ready(port, process, self.backend_config.cdp_startup_timeout_sec)
            except CdpStartupError as exc:
                last_error = exc
                _terminate_owned_process(process)
                continue

            self._process = process
            self._port = port
            return

        raise CdpStartupError(
            f"CDP 브라우저 시작에 {max_attempts}회 시도 후 실패했습니다. 마지막 오류: {last_error}"
        )

    def _connect_over_cdp(self) -> None:
        try:
            self._playwright = sync_playwright().start()
            self.browser = self._playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self._port}")
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            self.page = self.context.new_page()
        except Exception as exc:
            raise CdpConnectionError(f"CDP 연결에 실패했습니다: {exc}") from exc

    def __exit__(self, exc_type, exc, tb):
        self._teardown()
        return False

    def _teardown(self) -> None:
        # CDP로 connect_over_cdp()한 browser에서 browser.close()는 (Playwright 클라이언트
        # 연결) disconnect 역할만 하고 우리가 소유한 실제 프로세스를 종료하지 않는다 -
        # 그래서 아래에서 _terminate_owned_process로 owned process를 별도로 명시 종료한다.
        if self.browser is not None:
            try:
                self.browser.close()
            except Exception:
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass

        _terminate_owned_process(self._process)
        _release_profile_lock(self._lock_path)

        self.context = None
        self.browser = None
        self.page = None
        self._playwright = None
        self._process = None
        self._lock_path = None
        self._port = None
