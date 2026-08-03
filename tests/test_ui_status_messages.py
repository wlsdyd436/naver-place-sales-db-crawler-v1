import ast
from pathlib import Path
import sys


# UI-2(상태 문구 생성 순수 함수 분리) 검증용 standalone 스크립트(실제 CTk
# 창/Tk mainloop 없음). src/ui.py의 SalesDbCrawlerApp method였던 3개 함수
# (_format_eta_seconds/_home_stage_suffix/_network_stop_message)가
# src/ui_status_messages.py로 옮겨지고, src/ui.py는 module-level 함수로
# import해서만 쓰는지 확인한다. 문자열 값은 이동 전 실제 Production 함수를
# 직접 호출해 얻은 스냅샷을 그대로 고정한 것이며(추정 없음), 이동 후에도
# 문자 단위로 동일해야 한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

_MOVED_NAMES = ("_format_eta_seconds", "_home_stage_suffix", "_network_stop_message")


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


# --------------------------------------------------------------------------
# UI-STATUS-MODULE-1~6: 모듈 경계 계약
# --------------------------------------------------------------------------

def check_new_module_api_exists(reporter: ValidationReporter) -> None:
    try:
        from src import ui_status_messages
    except ImportError as exc:
        reporter.fail(f"UI-STATUS-MODULE-1. src.ui_status_messages import 실패: {exc!r}")
        return
    missing = [name for name in _MOVED_NAMES if not hasattr(ui_status_messages, name)]
    if not missing:
        reporter.pass_("UI-STATUS-MODULE-1. src.ui_status_messages에 이동 대상 3개 함수가 전부 존재함")
    else:
        reporter.fail(f"UI-STATUS-MODULE-1. 없는 함수: {missing}")


def check_functions_defined_in_new_module(reporter: ValidationReporter) -> None:
    try:
        from src import ui_status_messages
    except ImportError as exc:
        reporter.fail(f"UI-STATUS-MODULE-2. import 실패: {exc!r}")
        return
    wrong = {
        name: getattr(ui_status_messages, name).__module__
        for name in _MOVED_NAMES
        if hasattr(ui_status_messages, name) and getattr(ui_status_messages, name).__module__ != "src.ui_status_messages"
    }
    if not wrong:
        reporter.pass_("UI-STATUS-MODULE-2. 3개 함수 전부 __module__ == 'src.ui_status_messages'")
    else:
        reporter.fail(f"UI-STATUS-MODULE-2. __module__ 불일치: {wrong}")


def check_new_module_has_no_gui_dependency(reporter: ValidationReporter) -> None:
    """UI-STATUS-MODULE-3: AST import 노드 검사(문자열 grep 아님 - module
    docstring의 일반 단어로 인한 false positive 방지)."""
    path = ROOT_DIR / "src" / "ui_status_messages.py"
    if not path.exists():
        reporter.fail("UI-STATUS-MODULE-3. src/ui_status_messages.py가 존재하지 않음")
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
        reporter.pass_("UI-STATUS-MODULE-3. src/ui_status_messages.py는 tkinter/customtkinter/src.ui를 import하지 않음(AST 검사)")
    else:
        reporter.fail(f"UI-STATUS-MODULE-3. 금지된 import 발견: {found}")


def check_class_no_longer_defines_moved_functions(reporter: ValidationReporter) -> None:
    """UI-STATUS-MODULE-4: SalesDbCrawlerApp에 이동 대상 3개가 더 이상
    method로 정의돼 있지 않아야 한다."""
    ui_path = ROOT_DIR / "src" / "ui.py"
    tree = _parse_module_ast(ui_path)
    found = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "SalesDbCrawlerApp":
            found = [
                child.name for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name in _MOVED_NAMES
            ]
    if not found:
        reporter.pass_("UI-STATUS-MODULE-4. SalesDbCrawlerApp에 이동 대상 3개의 method 정의가 더 이상 없음")
    else:
        reporter.fail(f"UI-STATUS-MODULE-4. 여전히 class method로 정의돼 있음: {found}")


def check_ui_imports_new_module_without_wrapper(reporter: ValidationReporter) -> None:
    """UI-STATUS-MODULE-5: src/ui.py가 실제로 직접 호출하는 함수(_format_eta_seconds/
    _network_stop_message)는 src.ui_status_messages에서 import해야 한다.
    _home_stage_suffix는 ui.py가 직접 호출하지 않고(_network_stop_message
    내부에서만 쓰임) import하면 미사용 import가 되므로 대상에서 제외한다
    (§9 "사용하지 않는 import 제거" 요구사항 - UI-STATUS-MODULE-1/2와
    UI-STATUS-2~5가 _home_stage_suffix 자체의 존재·동작은 이미 검증함).
    self._format_eta_seconds/_home_stage_suffix/_network_stop_message 같은
    잔존 self.* 호출도 없어야 한다(class wrapper 미생성)."""
    ui_path = ROOT_DIR / "src" / "ui.py"
    tree = _parse_module_ast(ui_path)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.ui_status_messages":
            imported.update(alias.name for alias in node.names)
    directly_used_names = ("_format_eta_seconds", "_network_stop_message")
    missing_import = [name for name in directly_used_names if name not in imported]

    source = ui_path.read_text(encoding="utf-8")
    stale_self_calls = [
        name for name in _MOVED_NAMES if f"self.{name}(" in source
    ]

    if not missing_import and not stale_self_calls:
        reporter.pass_("UI-STATUS-MODULE-5. src/ui.py가 실제 호출하는 함수를 신규 모듈에서 import하고, self.* 잔존 호출 없음")
    else:
        reporter.fail(f"UI-STATUS-MODULE-5. missing_import={missing_import}, stale_self_calls={stale_self_calls}")


def check_query_plan_split_untouched(reporter: ValidationReporter) -> None:
    """UI-STATUS-MODULE-6: 이전 UI-1(query-plan 분리) 결과가 이번 작업으로
    되돌아가지 않았는지 재확인한다."""
    try:
        from src import ui, ui_query_plan
    except ImportError as exc:
        reporter.fail(f"UI-STATUS-MODULE-6. import 실패: {exc!r}")
        return
    names = ("_sort_korean_names", "_sort_legal_dong_items", "build_legal_dong_query_plan", "calculate_legal_dong_target_count")
    ok = all(getattr(ui, name, None) is getattr(ui_query_plan, name, None) for name in names)
    modules_ok = all(getattr(ui_query_plan, name).__module__ == "src.ui_query_plan" for name in names)
    if ok and modules_ok:
        reporter.pass_("UI-STATUS-MODULE-6. query-plan 분리(identity/__module__)가 이번 작업 이후에도 그대로 유지됨")
    else:
        reporter.fail(f"UI-STATUS-MODULE-6. query-plan 분리가 훼손됨: identity_ok={ok}, modules_ok={modules_ok}")


# --------------------------------------------------------------------------
# UI-STATUS-1: ETA 경계값(이동 전 실제 Production 함수 호출로 고정한 스냅샷)
# --------------------------------------------------------------------------

_ETA_CASES = (
    (-5, "0초"), (0, "0초"), (1, "1초"), (59, "59초"),
    (60, "1분 0초"), (61, "1분 1초"),
    (3599, "59분 59초"), (3600, "60분 0초"), (3661, "61분 1초"),
    (90.4, "1분 30초"), (90.5, "1분 30초"), (90.6, "1분 31초"),
)


def check_format_eta_seconds_boundary_values(reporter: ValidationReporter) -> None:
    try:
        from src.ui_status_messages import _format_eta_seconds
    except ImportError as exc:
        reporter.fail(f"UI-STATUS-1. import 실패: {exc!r}")
        return
    mismatches = [
        (seconds, expected, _format_eta_seconds(seconds))
        for seconds, expected in _ETA_CASES
        if _format_eta_seconds(seconds) != expected
    ]
    if not mismatches:
        reporter.pass_(f"UI-STATUS-1. ETA 경계값 {len(_ETA_CASES)}개 전부 이동 전 스냅샷과 문자 단위 일치")
    else:
        reporter.fail(f"UI-STATUS-1. 불일치: {mismatches}")


# --------------------------------------------------------------------------
# UI-STATUS-2~5: _home_stage_suffix(이동 전 스냅샷)
# --------------------------------------------------------------------------

_HOME_STAGE_CASES = (
    (
        "UI-STATUS-2(전체 통계 존재, 정상 완료)",
        {
            "home_processed_success_count": 515, "home_link_found_count": 182, "home_no_link_count": 333,
            "home_success_count": 515, "home_failure_count": 0, "home_retry_count": 3,
            "home_not_attempted_count": 0, "home_stop_reason": None,
        },
        " 홈페이지/SNS 보강 완료. 상세 처리 성공 515건(링크 발견 182건/없음 333건), 실패 0건, 미시도 0건.",
    ),
    (
        "UI-STATUS-3(부분 실패+미시도, 중단)",
        {
            "home_success_count": 10, "home_failure_count": 2, "home_not_attempted_count": 3,
            "home_link_found_count": 4, "home_no_link_count": 6, "home_stop_reason": "security_blocked",
        },
        " 홈페이지/SNS 보강 부분 완료(중단). 상세 처리 성공 10건(링크 발견 4건/없음 6건), 실패 2건, 미시도 3건.",
    ),
    (
        "UI-STATUS-4(구 schema만 존재, 하위 호환)",
        {"home_success_count": 7, "home_failure_count": 1, "home_not_attempted_count": 0, "home_stop_reason": None},
        " 홈페이지/SNS 보강 완료. 상세 처리 성공 7건(링크 발견 7건/없음 0건), 실패 1건, 미시도 0건.",
    ),
    (
        "UI-STATUS-5(홈 보강 미실행, 전부 0)",
        {"home_success_count": 0, "home_failure_count": 0, "home_not_attempted_count": 0},
        "",
    ),
    (
        "UI-STATUS-5(홈 관련 키 자체가 없음)",
        {},
        "",
    ),
)


def check_home_stage_suffix_locked_strings(reporter: ValidationReporter) -> None:
    try:
        from src.ui_status_messages import _home_stage_suffix
    except ImportError as exc:
        reporter.fail(f"UI-STATUS-2~5. import 실패: {exc!r}")
        return
    mismatches = [
        (label, expected, _home_stage_suffix(result))
        for label, result, expected in _HOME_STAGE_CASES
        if _home_stage_suffix(result) != expected
    ]
    if not mismatches:
        reporter.pass_(f"UI-STATUS-2~5. _home_stage_suffix {len(_HOME_STAGE_CASES)}개 케이스 전부 이동 전 스냅샷과 문자 단위 일치")
    else:
        reporter.fail(f"UI-STATUS-2~5 불일치: {mismatches}")


# --------------------------------------------------------------------------
# UI-STATUS-6~12: _network_stop_message(이동 전 스냅샷)
# --------------------------------------------------------------------------

_BASE_RESULT = {"exported": True, "export_error": False, "final_count": 3}

_NETWORK_STOP_CASES = (
    ("UI-STATUS-6(target_reached)", dict(_BASE_RESULT, stop_reason="target_reached"), 300,
     "전체 목표 개수에 도달했습니다. 3개를 저장했습니다."),
    ("UI-STATUS-6(queue_exhausted, 목표 미달)", dict(_BASE_RESULT, stop_reason="queue_exhausted", final_count=50), 300,
     "선택한 지역 수집이 완료되었습니다. 목표에는 미달했으며 50개를 저장했습니다."),
    ("UI-STATUS-6(queue_exhausted, 목표 도달)", dict(_BASE_RESULT, stop_reason="queue_exhausted", final_count=300), 300,
     "선택한 지역 수집이 완료되었습니다. 300개를 저장했습니다."),
    ("UI-STATUS-8(security_blocked)", dict(_BASE_RESULT, stop_reason="security_blocked", final_count=2), 300,
     "보안 확인이 감지되어 수집을 중단했습니다. 현재까지 2개를 저장했습니다."),
    ("UI-STATUS-9(status_429)", dict(_BASE_RESULT, stop_reason="status_429", final_count=4), 300,
     "요청 제한이 감지되어 수집을 중단했습니다. 현재까지 4개를 저장했습니다."),
    ("UI-STATUS-10(navigation_error)", dict(_BASE_RESULT, stop_reason="navigation_error", final_count=1), 300,
     "브라우저 페이지 오류로 수집을 중단했습니다. 현재까지 1개를 저장했습니다."),
    ("UI-STATUS-7(user_stopped)", dict(_BASE_RESULT, stop_reason="user_stopped", final_count=1), 300,
     "사용자가 수집을 중단했습니다. 현재까지 1개를 저장했습니다."),
    ("UI-STATUS-12(unknown stop_reason)", dict(_BASE_RESULT, stop_reason="some_weird_value", final_count=1), 300,
     "수집이 종료되었습니다. 1개를 저장했습니다. (stop_reason=some_weird_value)"),
    ("UI-STATUS-11(export_error)", {"export_error": True}, 300,
     "수집 결과를 Excel로 저장하지 못했습니다."),
    ("UI-STATUS-11(저장할 rows 없음)", {"export_error": False, "exported": False}, 300,
     "저장할 결과가 없습니다."),
    (
        "UI-STATUS-6+home suffix 결합",
        dict(
            _BASE_RESULT, stop_reason="target_reached",
            home_success_count=5, home_failure_count=0, home_not_attempted_count=0,
            home_link_found_count=2, home_no_link_count=3, home_stop_reason=None,
        ),
        300,
        "전체 목표 개수에 도달했습니다. 3개를 저장했습니다. 홈페이지/SNS 보강 완료. 상세 처리 성공 5건(링크 발견 2건/없음 3건), 실패 0건, 미시도 0건.",
    ),
)


def check_network_stop_message_locked_strings(reporter: ValidationReporter) -> None:
    try:
        from src.ui_status_messages import _network_stop_message
    except ImportError as exc:
        reporter.fail(f"UI-STATUS-6~12. import 실패: {exc!r}")
        return
    mismatches = [
        (label, expected, _network_stop_message(result, target_count))
        for label, result, target_count, expected in _NETWORK_STOP_CASES
        if _network_stop_message(result, target_count) != expected
    ]
    if not mismatches:
        reporter.pass_(f"UI-STATUS-6~12. _network_stop_message {len(_NETWORK_STOP_CASES)}개 케이스 전부 이동 전 스냅샷과 문자 단위 일치")
    else:
        reporter.fail(f"UI-STATUS-6~12 불일치: {mismatches}")


def main() -> int:
    reporter = ValidationReporter()

    check_new_module_api_exists(reporter)
    check_functions_defined_in_new_module(reporter)
    check_new_module_has_no_gui_dependency(reporter)
    check_class_no_longer_defines_moved_functions(reporter)
    check_ui_imports_new_module_without_wrapper(reporter)
    check_query_plan_split_untouched(reporter)
    check_format_eta_seconds_boundary_values(reporter)
    check_home_stage_suffix_locked_strings(reporter)
    check_network_stop_message_locked_strings(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
