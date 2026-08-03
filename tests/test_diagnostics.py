import json
from pathlib import Path
import shutil
import sys
import tempfile


# Stage 1 청크3: src/diagnostics.py 저장 유틸리티 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.diagnostics import (
    build_security_diagnostics_log_messages,
    capture_page_diagnostics,
    create_diagnostic_run_dir,
    sanitize_label,
    save_json_artifact,
    save_security_block_diagnostics,
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


class FakeCaptchaDialogLocator:
    def __init__(self, *, fail_screenshot=False):
        self._fail_screenshot = fail_screenshot
        self.screenshot_calls = []

    def screenshot(self, path=None):
        if self._fail_screenshot:
            raise RuntimeError("simulated element screenshot failure")
        Path(path).write_bytes(b"fake-captcha-png")
        self.screenshot_calls.append(path)


def check_save_security_block_diagnostics_with_visible_dialog(reporter: ValidationReporter) -> None:
    """DIAG-CAPTCHA-1: visible dialog locator가 있으면 JSON+PNG 모두 저장되고
    basename이 동일하며 schema 필드가 정확히 채워진다."""
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        locator = FakeCaptchaDialogLocator()
        result = save_security_block_diagnostics(
            captcha_dialog_locator=locator,
            diagnostics_root=temp_root,
            run_id="run-abc",
            detection_source="visible_dialog",
            active_captcha_detected=True,
            marker_present=True,
            element_visible=True,
            bounding_box_area=60000.0,
            pagination_stop_reason="captcha_detected",
            collected_count=5,
            current_url="https://map.naver.com/v5/search/x?query=secret&token=abc#frag",
        )
        json_ok = result["json_saved"] and result["json_path"] and Path(result["json_path"]).exists()
        png_ok = result["screenshot_saved"] and result["screenshot_path"] and Path(result["screenshot_path"]).exists()
        basename_ok = (
            json_ok and png_ok
            and Path(result["json_path"]).stem == Path(result["screenshot_path"]).stem
        )
        payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8")) if json_ok else {}
        schema_ok = (
            payload.get("event_type") == "security_blocked"
            and payload.get("security_reason") == "captcha_detected"
            and payload.get("run_id") == "run-abc"
            and payload.get("active_captcha_detected") is True
            and payload.get("current_url") == "https://map.naver.com/v5/search/x"
            and "?" not in payload.get("current_url", "")
            and "#" not in payload.get("current_url", "")
        )
        if json_ok and png_ok and basename_ok and schema_ok:
            reporter.pass_("DIAG-CAPTCHA-1. visible dialog: JSON+PNG 저장, basename 동일, schema/URL sanitize 정확")
        else:
            reporter.fail(
                f"DIAG-CAPTCHA-1 실패: result={result}, basename_ok={basename_ok}, payload={payload}"
            )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_save_security_block_diagnostics_screenshot_failure_isolated(reporter: ValidationReporter) -> None:
    """DIAG-CAPTCHA-5: locator.screenshot()이 예외를 던져도 JSON은 저장되고
    screenshot_saved=False, screenshot_error가 기록되며 예외가 전파되지 않는다."""
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        locator = FakeCaptchaDialogLocator(fail_screenshot=True)
        try:
            result = save_security_block_diagnostics(
                captcha_dialog_locator=locator, diagnostics_root=temp_root,
            )
        except Exception as exc:
            reporter.fail(f"DIAG-CAPTCHA-5 예외 전파됨: {exc!r}")
            return
        ok = (
            result["json_saved"] is True
            and result["screenshot_saved"] is False
            and result["screenshot_path"] is None
            and result["screenshot_error"]
            and "\n" not in result["screenshot_error"]
        )
        if ok:
            reporter.pass_("DIAG-CAPTCHA-5. screenshot 실패가 격리됨(JSON은 저장, screenshot_saved=False, 예외 미전파)")
        else:
            reporter.fail(f"DIAG-CAPTCHA-5 실패: {result}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_save_security_block_diagnostics_no_locator_json_only(reporter: ValidationReporter) -> None:
    """captcha_dialog_locator=None(visible dialog를 못 찾은 경우): 전체 페이지
    screenshot으로 대체하지 않고 PNG 없이 JSON만 저장한다."""
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        result = save_security_block_diagnostics(captcha_dialog_locator=None, diagnostics_root=temp_root)
        ok = (
            result["json_saved"] is True
            and result["screenshot_saved"] is False
            and result["screenshot_path"] is None
            and result["screenshot_error"] == "visible_dialog_locator_not_available"
        )
        if ok:
            reporter.pass_("DIAG-CAPTCHA. locator=None이면 전체 페이지 screenshot 대체 없이 JSON만 저장")
        else:
            reporter.fail(f"locator=None 케이스 실패: {result}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_save_security_block_diagnostics_no_sensitive_keys(reporter: ValidationReporter) -> None:
    """DIAG-CAPTCHA-10: 저장 JSON에 민감정보 key/값이 없다."""
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        result = save_security_block_diagnostics(
            captcha_dialog_locator=FakeCaptchaDialogLocator(),
            diagnostics_root=temp_root,
            current_url="https://map.naver.com/x?token=secret123",
        )
        serialized = Path(result["json_path"]).read_text(encoding="utf-8")
        forbidden = ["cookie", "Cookie", "authorization", "Authorization", "header",
                     "localStorage", "sessionStorage", "response_body", "<html", "secret123"]
        found = [term for term in forbidden if term in serialized]
        if not found:
            reporter.pass_("DIAG-CAPTCHA-10. 저장 JSON에 민감정보 key/값 없음(query token 제거 포함)")
        else:
            reporter.fail(f"DIAG-CAPTCHA-10 실패: 민감정보 발견={found}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_build_log_messages_json_and_png_success(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-1: JSON+PNG 모두 성공하면 두 줄이 정확한 문구로 나온다."""
    result = {
        "json_saved": True, "json_path": r"C:\logs\diagnostics\x.json", "json_error": None,
        "screenshot_saved": True, "screenshot_path": r"C:\logs\diagnostics\x.png", "screenshot_error": None,
    }
    messages = build_security_diagnostics_log_messages(result)
    ok = messages == [
        r"[진단] 보안 차단 정보 저장: C:\logs\diagnostics\x.json",
        r"[진단] CAPTCHA 화면 저장: C:\logs\diagnostics\x.png",
    ]
    if ok:
        reporter.pass_("GUI-DIAG-LOG-1. JSON+PNG 성공 시 정확히 2줄(경로 포함) 생성")
    else:
        reporter.fail(f"GUI-DIAG-LOG-1 실패: {messages}")


def check_build_log_messages_png_failure(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-2: JSON 성공 + PNG 실패 - 2줄, 실패 이유 포함.
    screenshot_error는 save_security_block_diagnostics가 이미 개행 제거·길이
    제한을 거친 뒤 채우는 값이므로(이 formatter는 재정규화하지 않음), 여기서도
    이미 정규화된 형태(개행 없음)를 입력으로 준다."""
    result = {
        "json_saved": True, "json_path": r"C:\logs\diagnostics\x.json", "json_error": None,
        "screenshot_saved": False, "screenshot_path": None,
        "screenshot_error": "RuntimeError: element screenshot failed",
    }
    messages = build_security_diagnostics_log_messages(result)
    ok = (
        len(messages) == 2
        and messages[0] == r"[진단] 보안 차단 정보 저장: C:\logs\diagnostics\x.json"
        and messages[1] == "[진단] CAPTCHA 화면 저장 실패: RuntimeError: element screenshot failed"
    )
    if ok:
        reporter.pass_("GUI-DIAG-LOG-2. JSON 성공+PNG 실패 - 2줄, 실패 이유 정확히 포함")
    else:
        reporter.fail(f"GUI-DIAG-LOG-2 실패: {messages}")


def check_build_log_messages_json_failure_only(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-3: JSON 자체가 실패(screenshot_error도 없는 총체적 실패)면
    1줄만 나온다(정보 없는 PNG 줄을 억지로 만들지 않음)."""
    result = {
        "json_saved": False, "json_path": None, "json_error": "OSError: disk full",
        "screenshot_saved": False, "screenshot_path": None, "screenshot_error": None,
    }
    messages = build_security_diagnostics_log_messages(result)
    ok = messages == ["[진단] 보안 차단 정보 저장 실패: OSError: disk full"]
    if ok:
        reporter.pass_("GUI-DIAG-LOG-3. JSON 실패(+PNG 정보 없음)면 1줄만 생성")
    else:
        reporter.fail(f"GUI-DIAG-LOG-3 실패: {messages}")


def check_build_log_messages_json_failure_but_png_saved(reporter: ValidationReporter) -> None:
    """JSON은 실패했지만 PNG는 저장됐다면(요청서 §5 "현재 결과에 따라 정확히
    출력") PNG 성공 줄도 함께 나와야 한다 - 추정으로 억누르지 않는다."""
    result = {
        "json_saved": False, "json_path": None, "json_error": "PermissionError: denied",
        "screenshot_saved": True, "screenshot_path": r"C:\logs\diagnostics\x.png", "screenshot_error": None,
    }
    messages = build_security_diagnostics_log_messages(result)
    ok = messages == [
        "[진단] 보안 차단 정보 저장 실패: PermissionError: denied",
        r"[진단] CAPTCHA 화면 저장: C:\logs\diagnostics\x.png",
    ]
    if ok:
        reporter.pass_("JSON 실패 + PNG 성공: 실제 결과대로 2줄(추정으로 PNG 줄을 숨기지 않음)")
    else:
        reporter.fail(f"JSON 실패+PNG 성공 케이스 실패: {messages}")


def check_build_log_messages_none_result_is_empty(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-4: CAPTCHA가 없어 result가 None이면 로그 0줄."""
    ok = build_security_diagnostics_log_messages(None) == [] and build_security_diagnostics_log_messages({}) == []
    if ok:
        reporter.pass_("GUI-DIAG-LOG-4. result가 None/빈 dict면 로그 0줄")
    else:
        reporter.fail("GUI-DIAG-LOG-4 실패: None/빈 dict에서 메시지가 생성됨")


def check_build_log_messages_malformed_input_absorbed(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-7 관련: dict가 아닌 잘못된 입력이 들어와도 예외를 던지지
    않고 빈 리스트를 반환한다(호출부가 예외 처리를 따로 하지 않아도 안전)."""
    try:
        messages = build_security_diagnostics_log_messages("not-a-dict")
    except Exception as exc:
        reporter.fail(f"잘못된 입력에서 예외 전파됨: {exc!r}")
        return
    if messages == []:
        reporter.pass_("잘못된 입력(dict 아님)은 예외 없이 빈 리스트 반환")
    else:
        reporter.fail(f"잘못된 입력 처리 결과가 예상과 다름: {messages}")


def check_build_log_messages_no_sensitive_content(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-8: 실제 저장 파이프라인(save_security_block_diagnostics -
    이미 cookie/authorization/header/query token을 만들지 않는 필드만 담음)을
    거친 결과를 포맷팅해도 로그 메시지에 민감정보가 없다 - 포맷 함수 자신이
    json_path/screenshot_path/error 문자열 외에 current_url/capture_id 등
    dict의 다른 필드를 추가로 노출하지 않는지도 함께 확인한다."""
    temp_root = Path(tempfile.mkdtemp(prefix="pc_diag_test_"))
    try:
        save_result = save_security_block_diagnostics(
            captcha_dialog_locator=FakeCaptchaDialogLocator(),
            diagnostics_root=temp_root,
            run_id="run-secret-check",
            current_url="https://map.naver.com/x?token=secret123",
        )
        messages = build_security_diagnostics_log_messages(save_result)
        combined = "\n".join(messages)
        forbidden = [
            "cookie", "Cookie", "Authorization", "authorization", "secret123",
            "run-secret-check", "capture_id", "current_url",
        ]
        found = [term for term in forbidden if term in combined]
        if not found and messages:
            reporter.pass_("GUI-DIAG-LOG-8. 실제 저장 결과를 포맷팅해도 민감정보/부가 필드가 로그에 노출되지 않음")
        else:
            reporter.fail(f"GUI-DIAG-LOG-8 실패: found={found}, messages={messages}")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def check_not_wired_to_production_paths(reporter: ValidationReporter) -> None:
    source = (ROOT_DIR / "src" / "diagnostics.py").read_text(encoding="utf-8")
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
    check_save_security_block_diagnostics_with_visible_dialog(reporter)
    check_save_security_block_diagnostics_screenshot_failure_isolated(reporter)
    check_save_security_block_diagnostics_no_locator_json_only(reporter)
    check_save_security_block_diagnostics_no_sensitive_keys(reporter)
    check_build_log_messages_json_and_png_success(reporter)
    check_build_log_messages_png_failure(reporter)
    check_build_log_messages_json_failure_only(reporter)
    check_build_log_messages_json_failure_but_png_saved(reporter)
    check_build_log_messages_none_result_is_empty(reporter)
    check_build_log_messages_malformed_input_absorbed(reporter)
    check_build_log_messages_no_sensitive_content(reporter)
    check_not_wired_to_production_paths(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
