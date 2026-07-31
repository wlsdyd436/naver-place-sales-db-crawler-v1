import json
from pathlib import Path
import shutil
import sys
import tempfile


# Stage 1 청크3: src/pc/diagnostics.py 저장 유틸리티 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.diagnostics import (
    capture_page_diagnostics,
    create_diagnostic_run_dir,
    sanitize_label,
    save_json_artifact,
    save_text_artifact,
)
from src.collection.safety import SafetyReason, classify_exception


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


class FakeFrame:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url


class FakePage:
    def __init__(self, url="https://example.com", html="<html>ok</html>", frames=None, fail_screenshot=False):
        self.url = url
        self._html = html
        self._frames = frames or []
        self._fail_screenshot = fail_screenshot
        self.screenshot_calls = []

    def content(self):
        return self._html

    def screenshot(self, path=None, full_page=False):
        if self._fail_screenshot:
            raise RuntimeError("simulated screenshot failure")
        Path(path).write_bytes(b"fake-png-bytes")
        self.screenshot_calls.append(path)

    @property
    def frames(self):
        return self._frames


def check_sanitize_label_removes_unsafe_chars(reporter: ValidationReporter) -> None:
    dirty = 'a<b>c:d"e/f\\g|h?i*j\nk'
    cleaned = sanitize_label(dirty)
    unsafe = set('<>:"/\\|?*')
    if not any(ch in cleaned for ch in unsafe) and "\n" not in cleaned:
        reporter.pass_(f"sanitize_label이 Windows 위험 문자를 제거함: {cleaned!r}")
    else:
        reporter.fail(f"sanitize_label 결과에 위험 문자가 남음: {cleaned!r}")


def check_create_diagnostic_run_dir(reporter: ValidationReporter) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        run_dir = create_diagnostic_run_dir(temp_root, "강동구 카페/캡차")
        safe_label = sanitize_label("강동구 카페/캡차")
        if run_dir.exists() and run_dir.is_dir() and safe_label in run_dir.name:
            reporter.pass_(f"create_diagnostic_run_dir가 timestamp+label 폴더 생성: {run_dir.name}")
        else:
            reporter.fail(f"run_dir가 예상과 다름: {run_dir}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_save_text_artifact(reporter: ValidationReporter) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        artifact = save_text_artifact(temp_root, "note.txt", "hello world")
        if artifact.success and artifact.path.read_text(encoding="utf-8") == "hello world":
            reporter.pass_("save_text_artifact가 txt 파일을 생성하고 내용을 저장함")
        else:
            reporter.fail(f"save_text_artifact 결과가 예상과 다름: {artifact}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_save_json_artifact(reporter: ValidationReporter) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        data = {"a": 1, "b": "한글"}
        artifact = save_json_artifact(temp_root, "data.json", data)
        loaded = json.loads(artifact.path.read_text(encoding="utf-8")) if artifact.success else None
        if artifact.success and loaded == data:
            reporter.pass_("save_json_artifact가 json 파일을 생성하고 읽을 수 있게 저장함")
        else:
            reporter.fail(f"save_json_artifact 결과가 예상과 다름: {artifact}, loaded={loaded}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_capture_with_fake_page(reporter: ValidationReporter) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        page = FakePage(
            url="https://map.naver.com/v5/search/test",
            html="<html><body>fake</body></html>",
            frames=[FakeFrame("searchIframe", "https://map.naver.com/search-frame")],
        )
        run_dir = create_diagnostic_run_dir(temp_root, "정상케이스")
        result = capture_page_diagnostics(page, run_dir, "정상케이스")

        url_file = run_dir / "url.txt"
        html_file = run_dir / "page.html"
        screenshot_file = run_dir / "screenshot.png"
        iframe_file = run_dir / "iframe_summary.json"

        ok = (
            url_file.exists()
            and url_file.read_text(encoding="utf-8") == page.url
            and html_file.exists()
            and screenshot_file.exists()
            and iframe_file.exists()
        )
        iframe_data = json.loads(iframe_file.read_text(encoding="utf-8")) if iframe_file.exists() else {}
        ok = ok and iframe_data.get("frames", [{}])[0].get("name") == "searchIframe"

        if ok and result.fail_count == 0:
            reporter.pass_("fake page로 url/html/screenshot/iframe summary 저장 성공")
        else:
            reporter.fail(
                f"fake page 캡처 결과가 예상과 다름: fail_count={result.fail_count}, "
                f"artifacts={[a.name for a in result.artifacts]}"
            )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_screenshot_failure_does_not_raise(reporter: ValidationReporter) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        page = FakePage(fail_screenshot=True)
        run_dir = create_diagnostic_run_dir(temp_root, "스크린샷실패")
        try:
            result = capture_page_diagnostics(page, run_dir, "스크린샷실패")
        except Exception as exc:
            reporter.fail(f"screenshot 실패가 capture_page_diagnostics 예외로 전파됨: {exc}")
            return

        screenshot_artifact = next((a for a in result.artifacts if a.name == "screenshot.png"), None)
        other_success = any(a.name == "url.txt" and a.success for a in result.artifacts)
        if screenshot_artifact is not None and not screenshot_artifact.success and other_success:
            reporter.pass_("screenshot 저장 실패가 예외로 터지지 않고 실패 artifact로만 기록됨")
        else:
            reporter.fail(f"screenshot 실패 처리 결과가 예상과 다름: {result.artifacts}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_exception_and_safety_decision_metadata(reporter: ValidationReporter) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        page = FakePage()
        run_dir = create_diagnostic_run_dir(temp_root, "캡차감지")
        exc = TimeoutError("Timeout 3000ms exceeded. wtm-captcha-root intercepts pointer events")
        decision = classify_exception(exc)

        result = capture_page_diagnostics(
            page, run_dir, "캡차감지", exception=exc, safety_decision=decision
        )

        exception_file = run_dir / "exception.txt"
        metadata_file = run_dir / "metadata.json"
        metadata = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else {}
        safety_meta = metadata.get("safety_decision", {})

        ok = (
            exception_file.exists()
            and "wtm-captcha-root" in exception_file.read_text(encoding="utf-8")
            and safety_meta.get("reason") == SafetyReason.CAPTCHA_OR_SECURITY_BLOCK.value
            and safety_meta.get("should_stop_safely") is True
            and safety_meta.get("should_save_partial") is True
            and result.fail_count == 0
        )
        if ok:
            reporter.pass_("exception.txt와 metadata.json에 safety_decision이 정확히 저장됨")
        else:
            reporter.fail(
                f"exception/metadata 저장 결과가 예상과 다름: metadata={metadata}, "
                f"fail_count={result.fail_count}"
            )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_not_wired_to_production_paths(reporter: ValidationReporter) -> None:
    source = (ROOT_DIR / "src" / "pc" / "diagnostics.py").read_text(encoding="utf-8")
    forbidden_tokens = ["pc_crawler", "src.ui", "src.exporter", "src.crawler", "src.parser"]
    found = [token for token in forbidden_tokens if token in source]
    if not found:
        reporter.pass_("diagnostics.py가 기존 실행 경로(pc_crawler/ui/exporter/crawler/parser)를 참조하지 않음")
    else:
        reporter.fail(f"diagnostics.py가 기존 실행 경로를 참조함: {found}")


def main() -> int:
    reporter = ValidationReporter()

    check_sanitize_label_removes_unsafe_chars(reporter)
    check_create_diagnostic_run_dir(reporter)
    check_save_text_artifact(reporter)
    check_save_json_artifact(reporter)
    check_capture_with_fake_page(reporter)
    check_screenshot_failure_does_not_raise(reporter)
    check_exception_and_safety_decision_metadata(reporter)
    check_not_wired_to_production_paths(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
