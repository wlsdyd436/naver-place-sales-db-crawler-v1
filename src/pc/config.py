# 정식 출시 전 PC 단일 엔진 전환 - Stage 1 (safety 분리) 청크1.
# 진단 모드 설정 객체입니다. 기존 pc_crawler.py는 참조하지 않으며 프로덕션 경로에 연결되지 않습니다.
import os
import sys
from dataclasses import dataclass


DEFAULT_KEEP_OPEN_TIMEOUT_SEC = 30


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class DiagnosticConfig:
    """PC 단일 엔진 진단(Diagnostic) 모드 설정. 기본값은 고객용 안전 모드(전부 비활성)입니다."""

    visible: bool = False
    keep_open_on_error: bool = False
    capture_artifacts: bool = False
    verbose: bool = False
    keep_open_timeout_sec: int = 0

    @classmethod
    def safe_default(cls) -> "DiagnosticConfig":
        """고객용 실행 기본값. 모든 진단 기능이 비활성화된 설정을 반환합니다."""
        return cls()

    @classmethod
    def from_env(cls) -> "DiagnosticConfig":
        """환경 변수 기반으로 진단 설정을 생성합니다.

        패키징된 실행 파일(sys.frozen) 환경에서는 환경 변수 값과 무관하게
        항상 안전 모드(safe_default)를 반환합니다.
        """
        if getattr(sys, "frozen", False):
            return cls.safe_default()

        debug_on = _env_bool("PCCRAWLER_DEBUG", False)

        return cls(
            visible=_env_bool("PCCRAWLER_VISIBLE", debug_on),
            keep_open_on_error=_env_bool("PCCRAWLER_KEEP_OPEN_ON_ERROR", debug_on),
            capture_artifacts=_env_bool("PCCRAWLER_CAPTURE_ARTIFACTS", debug_on),
            verbose=_env_bool("PCCRAWLER_VERBOSE", debug_on),
            keep_open_timeout_sec=_env_int(
                "PCCRAWLER_KEEP_OPEN_TIMEOUT_SEC",
                DEFAULT_KEEP_OPEN_TIMEOUT_SEC if debug_on else 0,
            ),
        )


DEFAULT_CDP_STARTUP_TIMEOUT_SEC = 15.0
DEFAULT_CDP_PORT_BIND_MAX_ATTEMPTS = 3

DEFAULT_BROWSER_PROFILE_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "NaverPlaceSalesDbCrawler",
    "browser_profiles",
)


@dataclass(frozen=True)
class BrowserBackendConfig:
    """PC 단일 엔진 브라우저 backend 설정. 기존 DiagnosticConfig(진단 플래그)와는
    독립된 설정 축이다 - 브라우저를 어떻게 띄우고 연결할지만 다룬다.

    2026-07-21 Native Edge/Chrome + CDP Attach 통합: production 기본값은
    backend="native_cdp"이며, 기존 Playwright launch 방식은 backend="launch"로
    명시적으로 선택할 때만 사용하는 개발·테스트 fallback으로 보존한다.
    """

    backend: str = "native_cdp"
    browser_preference: str = "auto"
    browser_path: str | None = None
    profile_root: str = DEFAULT_BROWSER_PROFILE_ROOT
    cdp_startup_timeout_sec: float = DEFAULT_CDP_STARTUP_TIMEOUT_SEC
    cdp_port_bind_max_attempts: int = DEFAULT_CDP_PORT_BIND_MAX_ATTEMPTS

    @classmethod
    def default(cls) -> "BrowserBackendConfig":
        """production 기본값. native_cdp/auto(Edge 우선)/기본 profile root."""
        return cls()

    @classmethod
    def from_env(cls) -> "BrowserBackendConfig":
        """환경 변수 기반으로 브라우저 backend 설정을 생성합니다.

        패키징된 실행 파일(sys.frozen) 환경에서는 환경 변수 값과 무관하게
        항상 production 기본값(default())을 반환합니다(DiagnosticConfig.from_env와
        동일한 frozen 정책).
        """
        if getattr(sys, "frozen", False):
            return cls.default()

        backend = os.environ.get("PCCRAWLER_BROWSER_BACKEND", "native_cdp").strip().lower()
        if backend not in ("native_cdp", "launch"):
            backend = "native_cdp"

        preference = os.environ.get("PCCRAWLER_BROWSER_PREFERENCE", "auto").strip().lower()
        if preference not in ("auto", "edge", "chrome"):
            preference = "auto"

        browser_path = os.environ.get("PCCRAWLER_BROWSER_PATH")
        browser_path = browser_path.strip() if browser_path else None

        profile_root = os.environ.get("PCCRAWLER_BROWSER_PROFILE_ROOT", DEFAULT_BROWSER_PROFILE_ROOT)

        return cls(
            backend=backend,
            browser_preference=preference,
            browser_path=browser_path or None,
            profile_root=profile_root,
            cdp_startup_timeout_sec=_env_int(
                "PCCRAWLER_CDP_STARTUP_TIMEOUT_SEC", int(DEFAULT_CDP_STARTUP_TIMEOUT_SEC)
            ),
            cdp_port_bind_max_attempts=_env_int(
                "PCCRAWLER_CDP_PORT_BIND_MAX_ATTEMPTS", DEFAULT_CDP_PORT_BIND_MAX_ATTEMPTS
            ),
        )
