import ast
from pathlib import Path
import sys


# UI-1(query-plan 순수 함수 분리) 검증용 standalone 스크립트(실제 CTk 창/Tk
# mainloop 없음). src/ui.py에 있던 법정동 query-plan 순수 함수 4개
# (_sort_korean_names/_sort_legal_dong_items/build_legal_dong_query_plan/
# calculate_legal_dong_target_count)가 src/ui_query_plan.py로 옮겨지고,
# src/ui.py는 그 이름을 단순 재노출(re-export)만 하는지 확인한다. 기존
# 대표 계약(job dict schema/정렬 규칙/세종 처리/target count 계산)은
# 새 대량 복제 없이 최소 대표 사례만 이 파일에서 재확인한다(로직 자체의
# 전체 계약은 tests/test_ui_legal_dong_wiring.py가 이미 보호함).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

_MOVED_NAMES = (
    "_sort_korean_names",
    "_sort_legal_dong_items",
    "build_legal_dong_query_plan",
    "calculate_legal_dong_target_count",
)
_KEPT_IN_UI_NAMES = ("_parse_positive_int", "_parse_review_bound")


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


def check_new_module_api_exists(reporter: ValidationReporter) -> None:
    """UI-QP-1: src.ui_query_plan에 이동 대상 4개 함수가 전부 존재해야 한다."""
    try:
        from src import ui_query_plan
    except ImportError as exc:
        reporter.fail(f"UI-QP-1. src.ui_query_plan import 실패: {exc!r}")
        return
    missing = [name for name in _MOVED_NAMES if not hasattr(ui_query_plan, name)]
    if not missing:
        reporter.pass_("UI-QP-1. src.ui_query_plan에 이동 대상 4개 함수가 전부 존재함")
    else:
        reporter.fail(f"UI-QP-1. src.ui_query_plan에 없는 함수: {missing}")


def check_ui_reexport_is_same_object(reporter: ValidationReporter) -> None:
    """UI-QP-2: src.ui의 각 이름이 wrapper가 아니라 src.ui_query_plan의
    동일 객체(identity)여야 한다."""
    try:
        from src import ui
        from src import ui_query_plan
    except ImportError as exc:
        reporter.fail(f"UI-QP-2. import 실패: {exc!r}")
        return
    mismatched = [
        name for name in _MOVED_NAMES
        if getattr(ui, name, None) is not getattr(ui_query_plan, name, None)
    ]
    if not mismatched:
        reporter.pass_("UI-QP-2. src.ui의 4개 이름이 src.ui_query_plan과 동일 객체(단순 재노출, wrapper 아님)")
    else:
        reporter.fail(f"UI-QP-2. identity 불일치(wrapper로 감쌌을 가능성): {mismatched}")


def check_functions_defined_in_new_module(reporter: ValidationReporter) -> None:
    """UI-QP-3: 각 함수의 __module__이 src.ui_query_plan이어야 한다(실제
    정의 위치 확인 - src.ui가 단순 import만 하는 게 아니라 재정의하지
    않았는지도 함께 검증)."""
    try:
        from src import ui_query_plan
    except ImportError as exc:
        reporter.fail(f"UI-QP-3. import 실패: {exc!r}")
        return
    wrong = {
        name: getattr(ui_query_plan, name).__module__
        for name in _MOVED_NAMES
        if hasattr(ui_query_plan, name) and getattr(ui_query_plan, name).__module__ != "src.ui_query_plan"
    }
    if not wrong:
        reporter.pass_("UI-QP-3. 4개 함수 전부 __module__ == 'src.ui_query_plan'")
    else:
        reporter.fail(f"UI-QP-3. __module__ 불일치: {wrong}")


def _parse_module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def check_new_module_has_no_tkinter_dependency(reporter: ValidationReporter) -> None:
    """UI-QP-4: src/ui_query_plan.py는 tkinter/customtkinter/src.ui를 import하지
    않아야 한다(AST import 노드 검사 - 문자열 단순 검색으로 인한 false
    positive 방지)."""
    path = ROOT_DIR / "src" / "ui_query_plan.py"
    if not path.exists():
        reporter.fail("UI-QP-4. src/ui_query_plan.py가 존재하지 않음")
        return
    tree = _parse_module_ast(path)
    forbidden_roots = ("tkinter", "customtkinter", "src.ui", "src", "ui")
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("tkinter", "customtkinter") or alias.name in ("src.ui", "ui"):
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in ("tkinter", "customtkinter", "src.ui", "ui") or module.startswith("tkinter.") or module.startswith("customtkinter."):
                found.append(module)
    if not found:
        reporter.pass_("UI-QP-4. src/ui_query_plan.py는 tkinter/customtkinter/src.ui를 import하지 않음(AST 검사)")
    else:
        reporter.fail(f"UI-QP-4. 금지된 import 발견: {found}")


def check_new_module_does_not_import_ui_back(reporter: ValidationReporter) -> None:
    """신규 모듈이 src.ui를 역참조하지 않는지(순환 import 방지) 별도 확인한다."""
    path = ROOT_DIR / "src" / "ui_query_plan.py"
    if not path.exists():
        reporter.fail("신규 모듈 파일 없음")
        return
    source = path.read_text(encoding="utf-8")
    tree = _parse_module_ast(path)
    reversed_import = any(
        (isinstance(node, ast.ImportFrom) and node.module == "src.ui")
        or (isinstance(node, ast.Import) and any(alias.name == "src.ui" for alias in node.names))
        for node in ast.walk(tree)
    )
    if not reversed_import:
        reporter.pass_("신규 모듈이 src.ui를 역참조하지 않음(순환 import 없음)")
    else:
        reporter.fail("신규 모듈이 src.ui를 import함(순환 import 위험)")


def check_representative_contracts_via_new_module(reporter: ValidationReporter) -> None:
    """UI-QP-5: 신규 모듈을 직접 import해 기존 대표 계약을 최소 사례로만
    재확인한다(전체 계약은 test_ui_legal_dong_wiring.py가 이미 보호)."""
    try:
        from src.ui_query_plan import (
            _sort_korean_names,
            _sort_legal_dong_items,
            build_legal_dong_query_plan,
            calculate_legal_dong_target_count,
        )
    except ImportError as exc:
        reporter.fail(f"UI-QP-5. import 실패: {exc!r}")
        return

    checks_ok = []

    # 서울특별시·강동구·법정동 복수 선택 job 생성 + new_opening/review 전달
    legal_dongs = [
        {"eup_myeon_dong": "천호동", "legal_code": "1174010100"},
        {"eup_myeon_dong": "성내동", "legal_code": "1174010200"},
    ]
    jobs = build_legal_dong_query_plan(
        "서울특별시", "강동구", legal_dongs, "카페", 30,
        new_opening_only=True, review_min=5, review_max=100,
    )
    checks_ok.append(
        len(jobs) == 2
        and jobs[0]["source_layer"] == "legal_dong"
        and jobs[0]["source_subregion"] == "천호동"
        and jobs[0]["legal_code"] == "1174010100"
        and jobs[0]["new_opening_only"] is True
        and jobs[0]["review_min"] == 5 and jobs[0]["review_max"] == 100
        and jobs[0]["query"] == "서울특별시 강동구 천호동 카페"
    )

    # 법정동 미선택 시 구 단위(district) job 1개
    district_jobs = build_legal_dong_query_plan("서울특별시", "강동구", [], "카페", 30)
    checks_ok.append(
        len(district_jobs) == 1
        and district_jobs[0]["source_layer"] == "district"
        and district_jobs[0]["source_subregion"] == ""
        and district_jobs[0]["query"] == "서울특별시 강동구 카페"
    )

    # 세종특별자치시(시군구 없음) 처리
    sejong_jobs = build_legal_dong_query_plan("세종특별자치시", "", [], "카페", 30)
    checks_ok.append(
        len(sejong_jobs) == 1
        and sejong_jobs[0]["query"] == "세종특별자치시 카페"
        and sejong_jobs[0]["source_district"] == ""
    )

    # 한글 이름 정렬(가나다순)
    checks_ok.append(_sort_korean_names(["강동구", "강남구", "강북구"]) == ["강남구", "강동구", "강북구"])

    # 법정동 항목 정렬(이름 가나다순, 동명이인은 legal_code 보조키)
    items = [
        {"eup_myeon_dong": "천호동", "legal_code": "222"},
        {"eup_myeon_dong": "성내동", "legal_code": "111"},
        {"eup_myeon_dong": "천호동", "legal_code": "111"},
    ]
    sorted_items = _sort_legal_dong_items(items)
    checks_ok.append(
        [item["eup_myeon_dong"] for item in sorted_items] == ["성내동", "천호동", "천호동"]
        and sorted_items[1]["legal_code"] == "111" and sorted_items[2]["legal_code"] == "222"
    )

    # target count = 30 x 9 = 270
    checks_ok.append(calculate_legal_dong_target_count(30, 9) == 270)

    # 0 또는 빈 query count는 0 반환
    checks_ok.append(calculate_legal_dong_target_count(0, 5) == 0)
    checks_ok.append(calculate_legal_dong_target_count(30, 0) == 0)

    if all(checks_ok):
        reporter.pass_("UI-QP-5. 신규 모듈 직접 호출로 대표 계약(job schema/세종/정렬/target count) 전부 확인됨")
    else:
        reporter.fail(f"UI-QP-5. 대표 계약 검증 실패: {checks_ok}")


def check_ui_no_longer_defines_moved_functions(reporter: ValidationReporter) -> None:
    """UI-QP-6: src/ui.py의 AST top-level 함수 정의 목록에 이동 대상 4개
    함수가 더 이상 정의돼 있지 않아야 한다(import를 통한 이름 존재는 허용)."""
    ui_path = ROOT_DIR / "src" / "ui.py"
    tree = _parse_module_ast(ui_path)
    defined_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    still_defined = [name for name in _MOVED_NAMES if name in defined_names]
    if not still_defined:
        reporter.pass_("UI-QP-6. src/ui.py에 이동 대상 4개 함수의 def가 더 이상 없음(import만 존재)")
    else:
        reporter.fail(f"UI-QP-6. src/ui.py에 여전히 정의돼 있음: {still_defined}")


def check_input_validation_functions_remain_in_ui(reporter: ValidationReporter) -> None:
    """UI-QP-7: _parse_positive_int/_parse_review_bound는 이번 범위가 아니므로
    여전히 src/ui.py에 def로 남아 있어야 한다."""
    ui_path = ROOT_DIR / "src" / "ui.py"
    tree = _parse_module_ast(ui_path)
    defined_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = [name for name in _KEPT_IN_UI_NAMES if name not in defined_names]
    if not missing:
        reporter.pass_("UI-QP-7. _parse_positive_int/_parse_review_bound가 src/ui.py에 그대로 정의돼 있음(범위 확대 없음)")
    else:
        reporter.fail(f"UI-QP-7. src/ui.py에서 사라짐(범위 초과 이동 의심): {missing}")


def main() -> int:
    reporter = ValidationReporter()

    check_new_module_api_exists(reporter)
    check_ui_reexport_is_same_object(reporter)
    check_functions_defined_in_new_module(reporter)
    check_new_module_has_no_tkinter_dependency(reporter)
    check_new_module_does_not_import_ui_back(reporter)
    check_representative_contracts_via_new_module(reporter)
    check_ui_no_longer_defines_moved_functions(reporter)
    check_input_validation_functions_remain_in_ui(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
