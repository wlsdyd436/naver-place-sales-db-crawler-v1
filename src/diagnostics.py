# 정식 출시 전 PC 단일 엔진 전환 - Stage 1 (safety 분리) 청크3.
# CAPTCHA/Timeout/Pagination/entryIframe 문제 진단용 산출물(screenshot/html/url/iframe/
# exception/metadata) 저장 유틸리티입니다. 이 모듈은 수집 로직을 실행하지 않고,
# 브라우저를 닫거나 재시작하지 않으며, safety.py의 SafetyDecision을 받아 기록만 할 뿐
# 안전 종료를 직접 수행하지 않습니다. 저장 실패는 원 예외를 덮어쓰지 않고
# DiagnosticArtifact(success=False)로만 기록합니다.
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# 고객 산출물(output/)과 분리된 진단 전용 저장 루트입니다.
DEFAULT_DIAGNOSTICS_ROOT = Path("logs") / "diagnostics"

_UNSAFE_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_label(label: str) -> str:
    """Windows 파일/폴더명에 안전하지 않은 문자를 치환합니다."""
    if not label:
        return "unlabeled"
    sanitized = _UNSAFE_CHARS_PATTERN.sub("_", label)
    sanitized = sanitized.strip(" .")
    sanitized = re.sub(r"\s+", "_", sanitized)
    return sanitized or "unlabeled"


def create_diagnostic_run_dir(base_dir: Path, label: str) -> Path:
    """<timestamp>_<sanitized label> 형태의 하위 폴더를 생성하고 경로를 반환합니다."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_label = sanitize_label(label)
    run_dir = Path(base_dir) / f"{timestamp}_{safe_label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@dataclass(frozen=True)
class DiagnosticArtifact:
    name: str
    path: Optional[Path]
    success: bool
    error_message: str = ""


@dataclass
class DiagnosticCaptureResult:
    run_dir: Path
    artifacts: list = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for artifact in self.artifacts if artifact.success)

    @property
    def fail_count(self) -> int:
        return sum(1 for artifact in self.artifacts if not artifact.success)


def save_text_artifact(run_dir: Path, name: str, content: str) -> DiagnosticArtifact:
    path = Path(run_dir) / name
    try:
        path.write_text("" if content is None else content, encoding="utf-8")
        return DiagnosticArtifact(name=name, path=path, success=True)
    except Exception as exc:
        return DiagnosticArtifact(
            name=name, path=None, success=False, error_message=f"{type(exc).__name__}: {exc}"
        )


def save_json_artifact(run_dir: Path, name: str, data: dict) -> DiagnosticArtifact:
    path = Path(run_dir) / name
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        return DiagnosticArtifact(name=name, path=path, success=True)
    except Exception as exc:
        return DiagnosticArtifact(
            name=name, path=None, success=False, error_message=f"{type(exc).__name__}: {exc}"
        )


def _safe_call(func):
    """func()를 실행하고 (결과, None) 또는 (None, 에러메시지)를 반환합니다. raise하지 않습니다."""
    try:
        return func(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _frame_summary(page) -> list:
    frames = getattr(page, "frames", [])
    return [
        {"name": getattr(frame, "name", ""), "url": getattr(frame, "url", "")}
        for frame in frames
    ]


def capture_page_diagnostics(
    page,
    run_dir: Path,
    label: str,
    exception=None,
    safety_decision=None,
) -> DiagnosticCaptureResult:
    """page의 url/html/screenshot/iframe 요약과 exception/safety_decision을 run_dir에 저장합니다.

    각 산출물은 개별적으로 best-effort 저장되며, 하나가 실패해도 나머지 저장과
    이 함수 자체는 예외를 던지지 않습니다. 브라우저 종료/재시작, 수집 로직 실행,
    안전 종료 실행은 이 함수의 책임이 아닙니다(호출자가 SafetyDecision을 보고 수행).
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []

    url_value, url_error = _safe_call(lambda: getattr(page, "url", ""))
    if url_error is None:
        artifacts.append(save_text_artifact(run_dir, "url.txt", str(url_value)))
    else:
        artifacts.append(
            DiagnosticArtifact(name="url.txt", path=None, success=False, error_message=url_error)
        )

    html_value, html_error = _safe_call(lambda: page.content())
    if html_error is None:
        artifacts.append(save_text_artifact(run_dir, "page.html", html_value))
    else:
        artifacts.append(
            DiagnosticArtifact(name="page.html", path=None, success=False, error_message=html_error)
        )

    screenshot_path = run_dir / "screenshot.png"
    _, screenshot_error = _safe_call(
        lambda: page.screenshot(path=str(screenshot_path), full_page=True)
    )
    if screenshot_error is None:
        artifacts.append(DiagnosticArtifact(name="screenshot.png", path=screenshot_path, success=True))
    else:
        artifacts.append(
            DiagnosticArtifact(
                name="screenshot.png", path=None, success=False, error_message=screenshot_error
            )
        )

    frames_value, frames_error = _safe_call(lambda: _frame_summary(page))
    if frames_error is None:
        artifacts.append(save_json_artifact(run_dir, "iframe_summary.json", {"frames": frames_value}))
    else:
        artifacts.append(
            DiagnosticArtifact(
                name="iframe_summary.json", path=None, success=False, error_message=frames_error
            )
        )

    if exception is not None:
        exc_text = (
            f"{type(exception).__name__}: {exception}"
            if isinstance(exception, BaseException)
            else str(exception)
        )
        artifacts.append(save_text_artifact(run_dir, "exception.txt", exc_text))

    metadata = {
        "label": label,
        "timestamp": datetime.now().isoformat(),
        "url": url_value if url_error is None else None,
    }
    if safety_decision is not None:
        reason = getattr(safety_decision, "reason", None)
        metadata["safety_decision"] = {
            "reason": getattr(reason, "value", str(reason)) if reason is not None else None,
            "should_stop_safely": getattr(safety_decision, "should_stop_safely", None),
            "should_save_partial": getattr(safety_decision, "should_save_partial", None),
            "message": getattr(safety_decision, "message", ""),
        }
    artifacts.append(save_json_artifact(run_dir, "metadata.json", metadata))

    return DiagnosticCaptureResult(run_dir=run_dir, artifacts=artifacts)
