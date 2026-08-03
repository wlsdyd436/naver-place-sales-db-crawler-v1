import ast
from pathlib import Path
import sys


# UI-3(Excel export orchestration 분리) 검증용 standalone 스크립트(실제 CTk
# 창/Tk mainloop 없음). src/ui.py의 SalesDbCrawlerApp method였던
# _export_network_result가 src/ui_export_flow.py의 module-level 함수
# export_network_result로 옮겨지고, 유일한 self.* 의존(self.log)이 명시적
# on_log 콜백으로 바뀌었는지 확인한다. 반환 dict/로그 문구는 이동 전 실제
# Production 함수를 직접 호출해 얻은 스냅샷을 그대로 고정한 것이며(추정
# 없음), 이동 후에도 문자 단위로 동일해야 한다. 전체 Network pipeline
# 시나리오(security_blocked/user_stopped/status_429/navigation_error 부분
# 저장, 이중 저장 방지, Basic/home_sns, Excel 컬럼)는 이미
# test_ui_network_wiring.py/test_ui_network_export.py가 보호하므로 여기서
# 중복 작성하지 않는다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"FINAL: {final}")
        print("====================")


def _parse_module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


class LogCollector:
    def __init__(self):
        self.messages: list = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


# --------------------------------------------------------------------------
# UI-EXPORT-1~5: 모듈 경계 계약
# --------------------------------------------------------------------------

def check_new_module_api_exists(reporter: ValidationReporter) -> None:
    try:
        from src import ui_export_flow
    except ImportError as exc:
        reporter.fail(f"UI-EXPORT-1. src.ui_export_flow import 실패: {exc!r}")
        return
    if hasattr(ui_export_flow, "export_network_result"):
        reporter.pass_("UI-EXPORT-1. src.ui_export_flow.export_network_result가 존재함")
    else:
        reporter.fail("UI-EXPORT-1. export_network_result가 없음")


def check_function_defined_in_new_module(reporter: ValidationReporter) -> None:
    try:
        from src.ui_export_flow import export_network_result
    except ImportError as exc:
        reporter.fail(f"UI-EXPORT-2. import 실패: {exc!r}")
        return
    if export_network_result.__module__ == "src.ui_export_flow":
        reporter.pass_("UI-EXPORT-2. export_network_result.__module__ == 'src.ui_export_flow'")
    else:
        reporter.fail(f"UI-EXPORT-2. __module__ 불일치: {export_network_result.__module__}")


def check_new_module_has_no_gui_dependency(reporter: ValidationReporter) -> None:
    """UI-EXPORT-3: AST import 노드 검사(문자열 grep 아님)."""
    path = ROOT_DIR / "src" / "ui_export_flow.py"
    if not path.exists():
        reporter.fail("UI-EXPORT-3. src/ui_export_flow.py가 존재하지 않음")
        return
    tree = _parse_module_ast(path)
    forbidden = {"tkinter", "customtkinter", "src.ui"}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(
                alias.name for alias in node.names
                if any(alias.name == item or alias.name.startswith(item + ".") for item in forbidden)
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if any(node.module == item or node.module.startswith(item + ".") for item in forbidden):
                found.append(node.module)
    if not found:
        reporter.pass_("UI-EXPORT-3. src/ui_export_flow.py는 tkinter/customtkinter/src.ui를 import하지 않음(AST 검사)")
    else:
        reporter.fail(f"UI-EXPORT-3. 금지된 import 발견: {found}")


def check_class_no_longer_defines_export_method(reporter: ValidationReporter) -> None:
    """UI-EXPORT-4: SalesDbCrawlerApp에 _export_network_result가 더 이상
    method로 정의돼 있지 않아야 한다."""
    ui_path = ROOT_DIR / "src" / "ui.py"
    tree = _parse_module_ast(ui_path)
    found = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SalesDbCrawlerApp":
            found = [
                child.name for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "_export_network_result"
            ]
    if not found:
        reporter.pass_("UI-EXPORT-4. SalesDbCrawlerApp에 _export_network_result method 정의가 더 이상 없음")
    else:
        reporter.fail("UI-EXPORT-4. 여전히 class method로 정의돼 있음")


def check_ui_imports_new_module_without_wrapper(reporter: ValidationReporter) -> None:
    """UI-EXPORT-5: src/ui.py가 export_network_result를 import하고,
    self._export_network_result(...) 잔존 호출이 없어야 한다(class wrapper
    미생성)."""
    ui_path = ROOT_DIR / "src" / "ui.py"
    tree = _parse_module_ast(ui_path)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.ui_export_flow":
            imported.update(alias.name for alias in node.names)

    source = ui_path.read_text(encoding="utf-8")
    stale_self_call = "self._export_network_result(" in source

    if "export_network_result" in imported and not stale_self_call:
        reporter.pass_("UI-EXPORT-5. src/ui.py가 export_network_result를 import하고, self.* 잔존 호출 없음")
    else:
        reporter.fail(f"UI-EXPORT-5. imported={imported}, stale_self_call={stale_self_call}")


# --------------------------------------------------------------------------
# UI-EXPORT-6~11: 이동 전 실제 Production 함수 호출로 고정한 스냅샷
# --------------------------------------------------------------------------

def check_normal_save_locked_contract(reporter: ValidationReporter) -> None:
    """UI-EXPORT-6/9/10: 정상 저장 - exporter 1회, 인자(rows, [], [],
    output_path) 그대로 전달, 반환값 str() 변환, 반환 dict와 로그가 이동 전
    스냅샷과 문자 단위 일치."""
    try:
        from src.ui_export_flow import export_network_result
    except ImportError as exc:
        reporter.fail(f"UI-EXPORT-6. import 실패: {exc!r}")
        return

    calls = []

    def exporter_ok(rows, mobile, pc, output_path):
        calls.append((rows, mobile, pc, output_path))
        return "output/actual_saved.xlsx"

    on_log = LogCollector()
    rows = [{"a": 1}, {"a": 2}]
    result = export_network_result(
        {"rows": rows, "stop_reason": "queue_exhausted"}, "out.xlsx", exporter_ok, on_log=on_log,
    )

    expected_return = {
        "rows": rows, "stop_reason": "queue_exhausted",
        "exported": True, "export_path": "output/actual_saved.xlsx",
        "export_error": False, "export_error_message": "",
    }
    expected_logs = ["[ui][network] Excel 저장 완료: output/actual_saved.xlsx (2건)"]

    ok = (
        len(calls) == 1
        and calls[0] == (rows, [], [], "out.xlsx")
        and result == expected_return
        and on_log.messages == expected_logs
    )
    if ok:
        reporter.pass_("UI-EXPORT-6/9/10. 정상 저장: exporter 1회(인자 그대로), 반환 dict/로그가 이동 전 스냅샷과 일치")
    else:
        reporter.fail(f"UI-EXPORT-6/9/10 실패: calls={calls}, result={result}, logs={on_log.messages}")


def check_empty_rows_locked_contract(reporter: ValidationReporter) -> None:
    """UI-EXPORT-7: rows가 비어 있으면 exporter를 전혀 호출하지 않는다."""
    try:
        from src.ui_export_flow import export_network_result
    except ImportError as exc:
        reporter.fail(f"UI-EXPORT-7. import 실패: {exc!r}")
        return

    def exporter_must_not_be_called(*args, **kwargs):
        raise AssertionError("rows가 비어 있는데 exporter가 호출됨")

    on_log = LogCollector()
    result = export_network_result(
        {"rows": [], "stop_reason": "queue_exhausted"}, "out.xlsx", exporter_must_not_be_called, on_log=on_log,
    )

    expected_return = {
        "rows": [], "stop_reason": "queue_exhausted",
        "exported": False, "export_path": "", "export_error": False, "export_error_message": "",
    }
    expected_logs = ["[ui][network] 저장할 결과가 없어 Excel 저장을 건너뜁니다."]

    if result == expected_return and on_log.messages == expected_logs:
        reporter.pass_("UI-EXPORT-7. 빈 rows: exporter 0회 호출, 반환 dict/로그가 이동 전 스냅샷과 일치")
    else:
        reporter.fail(f"UI-EXPORT-7 실패: result={result}, logs={on_log.messages}")


def check_exporter_exception_locked_contract(reporter: ValidationReporter) -> None:
    """UI-EXPORT-8: exporter 예외 시 exported=False/export_error=True로
    기록하고 예외를 외부로 전파하지 않으며, 두 번째 호출도 없다."""
    try:
        from src.ui_export_flow import export_network_result
    except ImportError as exc:
        reporter.fail(f"UI-EXPORT-8. import 실패: {exc!r}")
        return

    call_count = {"n": 0}

    def exporter_raises(rows, mobile, pc, output_path):
        call_count["n"] += 1
        raise RuntimeError("disk full")

    on_log = LogCollector()
    try:
        result = export_network_result(
            {"rows": [{"a": 1}], "stop_reason": "queue_exhausted"}, "out.xlsx", exporter_raises, on_log=on_log,
        )
    except Exception as exc:
        reporter.fail(f"UI-EXPORT-8. 예외가 외부로 전파됨(이동 전에는 삼켜졌어야 함): {exc!r}")
        return

    expected_return = {
        "rows": [{"a": 1}], "stop_reason": "queue_exhausted",
        "exported": False, "export_path": "", "export_error": True, "export_error_message": "RuntimeError: disk full",
    }
    expected_logs = ["[ui][network] Excel 저장 실패: RuntimeError: disk full"]

    if result == expected_return and on_log.messages == expected_logs and call_count["n"] == 1:
        reporter.pass_("UI-EXPORT-8. exporter 예외: 반환 dict/로그가 이동 전 스냅샷과 일치, 재호출 없음, 예외 미전파")
    else:
        reporter.fail(f"UI-EXPORT-8 실패: result={result}, logs={on_log.messages}, call_count={call_count['n']}")


def check_falsy_saved_path_falls_back_to_output_path(reporter: ValidationReporter) -> None:
    """UI-EXPORT-9: exporter가 falsy 값(None 등)을 반환하면 export_path는
    output_path로 대체된다(str(saved_path or output_path))."""
    try:
        from src.ui_export_flow import export_network_result
    except ImportError as exc:
        reporter.fail(f"UI-EXPORT-9. import 실패: {exc!r}")
        return

    on_log = LogCollector()
    result = export_network_result(
        {"rows": [{"a": 1}], "stop_reason": "x"}, "out.xlsx", lambda *a: None, on_log=on_log,
    )
    expected_logs = ["[ui][network] Excel 저장 완료: out.xlsx (1건)"]
    if result["export_path"] == "out.xlsx" and result["exported"] is True and on_log.messages == expected_logs:
        reporter.pass_("UI-EXPORT-9. exporter가 falsy 값을 반환하면 export_path가 output_path로 대체됨(이동 전 스냅샷과 일치)")
    else:
        reporter.fail(f"UI-EXPORT-9 실패: result={result}, logs={on_log.messages}")


def check_result_dict_not_mutated_in_place(reporter: ValidationReporter) -> None:
    """이동 전 계약: 원본 result dict를 변형하지 않고 복사해서 사용한다
    (호출자가 넘긴 dict가 그대로 남아 있어야 함)."""
    try:
        from src.ui_export_flow import export_network_result
    except ImportError as exc:
        reporter.fail(f"실패: import 오류: {exc!r}")
        return
    original = {"rows": [], "stop_reason": "queue_exhausted"}
    original_copy = dict(original)
    export_network_result(original, "out.xlsx", lambda *a: None, on_log=lambda m: None)
    if original == original_copy:
        reporter.pass_("원본 result dict가 변형되지 않음(복사본만 갱신됨)")
    else:
        reporter.fail(f"원본 result dict가 변형됨: {original}")


def main() -> int:
    reporter = ValidationReporter()

    check_new_module_api_exists(reporter)
    check_function_defined_in_new_module(reporter)
    check_new_module_has_no_gui_dependency(reporter)
    check_class_no_longer_defines_export_method(reporter)
    check_ui_imports_new_module_without_wrapper(reporter)
    check_normal_save_locked_contract(reporter)
    check_empty_rows_locked_contract(reporter)
    check_exporter_exception_locked_contract(reporter)
    check_falsy_saved_path_falls_back_to_output_path(reporter)
    check_result_dict_not_mutated_in_place(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
