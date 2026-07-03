# 정식 출시 전 PC 단일 엔진 전환 - Stage 2 (browser_session/list_scraper 경계) 청크1.
# Playwright 브라우저 생명주기(launch/context/page)와 진단 캡처 트리거를 소유합니다.
# 이 모듈은 카드 탐색/스크롤/페이지네이션/파싱 로직을 갖지 않으며(list_scraper.py 책임),
# CAPTCHA 우회/자동 해결을 시도하지 않습니다. 진단 캡처는 page가 살아있는 이 계층에서
# 호출자가 명시적으로 수행해야 합니다(teardown 이후에는 캡처가 불가능하기 때문).
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.pc.diagnostics import (
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

        호출자(list_scraper의 collector)가 진단 캡처 이후, teardown 직전에
        명시적으로 호출해야 합니다. capture_artifacts 여부와 무관하게 동작합니다.
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
