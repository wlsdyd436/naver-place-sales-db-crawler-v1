import os
from pathlib import Path
import sys


# Stage 1 청크1: src/pc/config.py DiagnosticConfig 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.config import DiagnosticConfig


ENV_KEYS = [
    "PCCRAWLER_DEBUG",
    "PCCRAWLER_VISIBLE",
    "PCCRAWLER_KEEP_OPEN_ON_ERROR",
    "PCCRAWLER_CAPTURE_ARTIFACTS",
    "PCCRAWLER_VERBOSE",
    "PCCRAWLER_KEEP_OPEN_TIMEOUT_SEC",
]


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


def _clear_env():
    for key in ENV_KEYS:
        os.environ.pop(key, None)


def _clear_frozen():
    if hasattr(sys, "frozen"):
        delattr(sys, "frozen")


def check_default_is_safe(reporter: ValidationReporter) -> None:
    config = DiagnosticConfig()
    if (
        config.visible is False
        and config.keep_open_on_error is False
        and config.capture_artifacts is False
        and config.verbose is False
        and config.keep_open_timeout_sec == 0
    ):
        reporter.pass_("DiagnosticConfig() 기본값이 전부 안전(False/0)")
    else:
        reporter.fail(f"DiagnosticConfig() 기본값이 안전하지 않음: {config}")


def check_safe_default(reporter: ValidationReporter) -> None:
    config = DiagnosticConfig.safe_default()
    if config == DiagnosticConfig():
        reporter.pass_("safe_default()가 기본 생성자와 동일")
    else:
        reporter.fail(f"safe_default()가 기본값과 다름: {config}")


def check_from_env_no_vars(reporter: ValidationReporter) -> None:
    _clear_env()
    _clear_frozen()
    config = DiagnosticConfig.from_env()
    if config == DiagnosticConfig.safe_default():
        reporter.pass_("환경 변수 미설정 시 from_env()가 안전 모드")
    else:
        reporter.fail(f"환경 변수 미설정인데 안전 모드가 아님: {config}")


def check_from_env_debug_on(reporter: ValidationReporter) -> None:
    _clear_env()
    _clear_frozen()
    os.environ["PCCRAWLER_DEBUG"] = "1"
    config = DiagnosticConfig.from_env()
    _clear_env()
    if (
        config.visible is True
        and config.keep_open_on_error is True
        and config.capture_artifacts is True
        and config.verbose is True
        and config.keep_open_timeout_sec > 0
    ):
        reporter.pass_(
            f"PCCRAWLER_DEBUG=1 시 전체 진단 기능 활성화 (timeout={config.keep_open_timeout_sec}s)"
        )
    else:
        reporter.fail(f"PCCRAWLER_DEBUG=1인데 예상과 다름: {config}")


def check_from_env_individual_override(reporter: ValidationReporter) -> None:
    _clear_env()
    _clear_frozen()
    os.environ["PCCRAWLER_VISIBLE"] = "true"
    os.environ["PCCRAWLER_KEEP_OPEN_TIMEOUT_SEC"] = "45"
    config = DiagnosticConfig.from_env()
    _clear_env()
    if (
        config.visible is True
        and config.keep_open_timeout_sec == 45
        and config.keep_open_on_error is False
        and config.capture_artifacts is False
    ):
        reporter.pass_("개별 환경 변수 override가 PCCRAWLER_DEBUG 없이도 동작")
    else:
        reporter.fail(f"개별 override 결과가 예상과 다름: {config}")


def check_frozen_forces_safe_mode(reporter: ValidationReporter) -> None:
    _clear_env()
    os.environ["PCCRAWLER_DEBUG"] = "1"
    os.environ["PCCRAWLER_VISIBLE"] = "1"
    os.environ["PCCRAWLER_KEEP_OPEN_ON_ERROR"] = "1"
    os.environ["PCCRAWLER_KEEP_OPEN_TIMEOUT_SEC"] = "999"
    sys.frozen = True
    try:
        config = DiagnosticConfig.from_env()
    finally:
        _clear_frozen()
        _clear_env()

    if config == DiagnosticConfig.safe_default():
        reporter.pass_("sys.frozen=True면 환경 변수와 무관하게 강제 안전 모드")
    else:
        reporter.fail(f"sys.frozen=True인데 진단 모드가 강제 OFF되지 않음: {config}")


def main() -> int:
    reporter = ValidationReporter()

    check_default_is_safe(reporter)
    check_safe_default(reporter)
    check_from_env_no_vars(reporter)
    check_from_env_debug_on(reporter)
    check_from_env_individual_override(reporter)
    check_frozen_forces_safe_mode(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
