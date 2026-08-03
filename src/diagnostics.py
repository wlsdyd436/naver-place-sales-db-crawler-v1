# 정식 출시 전 PC 단일 엔진 전환 - Stage 1 (safety 분리) 청크3.
# CAPTCHA/Timeout/Pagination/entryIframe 문제 진단용 산출물(screenshot/html/url/iframe/
# exception/metadata) 저장 유틸리티입니다. 이 모듈은 수집 로직을 실행하지 않고,
# 브라우저를 닫거나 재시작하지 않으며, safety.py의 SafetyDecision을 받아 기록만 할 뿐
# 안전 종료를 직접 수행하지 않습니다. 저장 실패는 원 예외를 덮어쓰지 않고
# DiagnosticArtifact(success=False)로만 기록합니다.
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


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


_ERROR_MESSAGE_MAX_LEN = 300


def _sanitize_message(message) -> str:
    """줄바꿈을 제거하고 길이를 제한한다(요청서 §4 - 긴 원문/스택트레이스 저장 금지)."""
    text = re.sub(r"[\r\n]+", " ", str(message or "")).strip()
    return text[:_ERROR_MESSAGE_MAX_LEN]


def _sanitize_current_url(url) -> str:
    """query string과 fragment를 제거한 origin/path만 남긴다(요청서 §4)."""
    try:
        parsed = urlsplit(str(url or ""))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except Exception:
        return ""


def save_security_block_diagnostics(
    *,
    captcha_dialog_locator,
    diagnostics_root: Path = DEFAULT_DIAGNOSTICS_ROOT,
    run_id: str = "",
    security_reason: str = "captcha_detected",
    detection_source: str = "unknown",
    active_captcha_detected: bool = False,
    click_intercepted_by_captcha: bool = False,
    passive_captcha_marker_found: bool = False,
    marker_present: bool = False,
    element_visible: bool = False,
    bounding_box_area: float = 0.0,
    pagination_stop_reason: str = "",
    security_blocked: bool = True,
    collected_count: int = 0,
    page_sequence=None,
    target_page=None,
    current_url: str = "",
) -> dict:
    """CAPTCHA/보안 차단이 확정된 순간 JSON(항상 시도)과 CAPTCHA dialog
    element PNG(captcha_dialog_locator가 있을 때만)를 저장한다.

    이 함수는 Playwright page/frame을 직접 다루지 않는다(check_not_wired_to_
    production_paths와 동일한 원칙 - captcha_dialog_locator는 `.screenshot(path=...)`
    계약만 있으면 되는 duck-typed 객체이며, current_url은 호출자가 이미
    문자열로 추출해 넘긴다). 예외를 밖으로 전파하지 않는다 - 어떤 저장
    실패도 Production 수집 결과를 바꾸지 않는다(best-effort). 전체 페이지
    screenshot은 절대 찍지 않는다(locator 없음/실패 시 PNG 없이 JSON만
    저장하고 screenshot_saved=False로 기록).

    반환: {"json_saved", "json_path", "json_error", "screenshot_saved",
    "screenshot_path", "screenshot_error"}.
    """
    try:
        diagnostics_root = Path(diagnostics_root)
        diagnostics_root.mkdir(parents=True, exist_ok=True)

        capture_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        basename = f"security_blocked_{timestamp}_{capture_id}"
        json_filename = f"{basename}.json"
        png_filename = f"{basename}.png"

        screenshot_saved = False
        screenshot_error = None
        if captcha_dialog_locator is not None:
            png_path = diagnostics_root / png_filename
            try:
                captcha_dialog_locator.screenshot(path=str(png_path))
                screenshot_saved = True
            except Exception as exc:
                screenshot_error = _sanitize_message(f"{type(exc).__name__}: {exc}")
        else:
            screenshot_error = "visible_dialog_locator_not_available"

        payload = {
            "schema_version": 1,
            "event_type": "security_blocked",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id or None,
            "capture_id": capture_id,
            "security_reason": security_reason,
            "detection_source": detection_source,
            "active_captcha_detected": bool(active_captcha_detected),
            "click_intercepted_by_captcha": bool(click_intercepted_by_captcha),
            "passive_captcha_marker_found": bool(passive_captcha_marker_found),
            "marker_present": bool(marker_present),
            "element_visible": bool(element_visible),
            "bounding_box_area": float(bounding_box_area),
            "pagination_stop_reason": pagination_stop_reason or None,
            "security_blocked": bool(security_blocked),
            "collected_count": int(collected_count),
            "page_sequence": page_sequence,
            "target_page": target_page,
            "current_url": _sanitize_current_url(current_url) or None,
            "screenshot_saved": screenshot_saved,
            "screenshot_filename": png_filename if screenshot_saved else None,
            "screenshot_error": screenshot_error,
        }

        json_artifact = save_json_artifact(diagnostics_root, json_filename, payload)
        return {
            "json_saved": json_artifact.success,
            "json_path": str(json_artifact.path) if json_artifact.success else None,
            "json_error": json_artifact.error_message or None,
            "screenshot_saved": screenshot_saved,
            "screenshot_path": str(diagnostics_root / png_filename) if screenshot_saved else None,
            "screenshot_error": screenshot_error,
        }
    except Exception as exc:
        return {
            "json_saved": False,
            "json_path": None,
            "json_error": _sanitize_message(f"{type(exc).__name__}: {exc}"),
            "screenshot_saved": False,
            "screenshot_path": None,
            "screenshot_error": None,
        }


def build_security_diagnostics_log_messages(result) -> list:
    """save_security_block_diagnostics()의 반환 dict를 사용자에게 보여줄
    한 줄짜리 로그 문자열 목록으로 변환하는 순수 함수(UI 프레임워크 의존
    없음 - Tkinter 등 어떤 UI 계층도 import하지 않는다).

    result가 None/빈 dict/dict가 아니면(CAPTCHA가 없었던 정상 실행, 또는
    잘못된 입력) 빈 list를 반환한다(예외 없음). json/screenshot 각각 실제
    성공·실패 여부에 따라 정확히 표시하며, 실패인데 표시할 이유(*_error)가
    전혀 없는 경우(예: mkdir 자체가 실패해 screenshot을 시도조차 못한 경우)는
    그 줄 자체를 만들지 않는다 - 정보 없는 "실패: None" 줄을 지어내지
    않는다. json_path/screenshot_path/*_error 외의 다른 필드(current_url/
    capture_id/run_id 등)는 로그에 노출하지 않는다."""
    if not isinstance(result, dict) or not result:
        return []

    messages = []
    if result.get("json_saved"):
        messages.append(f"[진단] 보안 차단 정보 저장: {result.get('json_path')}")
    elif result.get("json_error"):
        messages.append(f"[진단] 보안 차단 정보 저장 실패: {result.get('json_error')}")

    if result.get("screenshot_saved"):
        messages.append(f"[진단] CAPTCHA 화면 저장: {result.get('screenshot_path')}")
    elif result.get("screenshot_error"):
        messages.append(f"[진단] CAPTCHA 화면 저장 실패: {result.get('screenshot_error')}")

    return messages
