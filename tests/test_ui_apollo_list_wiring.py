import inspect
from pathlib import Path
import sys


# 신규 두 모드(기본/홈페이지·SNS 포함) UI 배선 검증용 standalone 스크립트.
# src/ui.py의 SalesDbCrawlerApp을 실제로 인스턴스화하지 않는다(Tk 루트 생성
# 회피 - 기존 tests/test_ui_dom_membership_wiring.py/test_ui_network_start.py와
# 동일하게 inspect.signature/inspect.getsource introspection만 사용).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import ui
from src.collection.home_enrichment import enrich_home_details
from src.pc.network_browser_collector import ApolloFirstListCollector


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


def check_default_collector_factory_is_apollo_first_list_collector(reporter: ValidationReporter) -> None:
    signature = inspect.signature(ui.SalesDbCrawlerApp._run_network_pipeline)
    default = signature.parameters["collector_factory"].default
    if default is ApolloFirstListCollector:
        reporter.pass_("_run_network_pipeline 기본 collector_factory가 ApolloFirstListCollector(신규 GraphQL-first 경로)임을 확인")
    else:
        reporter.fail(f"_run_network_pipeline 기본 collector_factory가 예상과 다름: {default!r}")


def check_run_network_pipeline_has_collection_mode_param_default_basic(reporter: ValidationReporter) -> None:
    signature = inspect.signature(ui.SalesDbCrawlerApp._run_network_pipeline)
    param = signature.parameters.get("collection_mode")
    if param is not None and param.default == "basic":
        reporter.pass_("_run_network_pipeline에 collection_mode 파라미터(기본값 'basic') 존재 확인")
    else:
        reporter.fail(f"collection_mode 파라미터가 없거나 기본값이 다름: {param!r}")


def check_run_network_pipeline_has_home_enrichment_fn_default(reporter: ValidationReporter) -> None:
    signature = inspect.signature(ui.SalesDbCrawlerApp._run_network_pipeline)
    param = signature.parameters.get("home_enrichment_fn")
    if param is not None and param.default is enrich_home_details:
        reporter.pass_("_run_network_pipeline에 home_enrichment_fn 주입 지점(기본값 enrich_home_details) 존재 확인")
    else:
        reporter.fail(f"home_enrichment_fn 파라미터가 없거나 기본값이 다름: {param!r}")


def check_run_network_pipeline_worker_accepts_collection_mode(reporter: ValidationReporter) -> None:
    signature = inspect.signature(ui.SalesDbCrawlerApp._run_network_pipeline_worker)
    param = signature.parameters.get("collection_mode")
    if param is not None and param.default == "basic":
        reporter.pass_("_run_network_pipeline_worker가 collection_mode(기본값 'basic')를 받아 그대로 전달함")
    else:
        reporter.fail(f"_run_network_pipeline_worker의 collection_mode 파라미터가 예상과 다름: {param!r}")


def check_init_sets_collection_mode_var_default_basic(reporter: ValidationReporter) -> None:
    """SalesDbCrawlerApp을 실제로 인스턴스화하지 않고(Tk 루트 생성 회피)
    __init__ 소스에 collection_mode_var 기본값 선언이 있는지만 확인한다
    (기존 test_ui_network_start.py의 inspect.getsource 관례와 동일)."""
    source = inspect.getsource(ui.SalesDbCrawlerApp.__init__)
    if 'self.collection_mode_var = ctk.StringVar(value="basic")' in source:
        reporter.pass_("__init__에 collection_mode_var 기본값 'basic' 선언 확인")
    else:
        reporter.fail("__init__에서 collection_mode_var='basic' 선언을 찾지 못함")


def check_collection_mode_section_wired_into_build_ui(reporter: ValidationReporter) -> None:
    build_ui_source = inspect.getsource(ui.SalesDbCrawlerApp._build_ui)
    section_source = inspect.getsource(ui.SalesDbCrawlerApp._build_collection_mode_section)
    ok = (
        "self._build_collection_mode_section()" in build_ui_source
        and 'value="basic"' in section_source
        and 'value="home_sns"' in section_source
    )
    if ok:
        reporter.pass_("_build_ui가 _build_collection_mode_section을 호출하고 basic/home_sns 라디오 값이 존재함")
    else:
        reporter.fail("수집 모드 섹션이 _build_ui에 배선되지 않았거나 라디오 값이 예상과 다름")


def check_no_premium_or_paid_wording_in_collection_mode_section(reporter: ValidationReporter) -> None:
    """금지 문구(프리미엄/유료/제한 모드/상세 페이지 방문 모드)가 실제 사용자
    노출 문자열(text=/textvariable 라벨)에 없는지 확인한다. 소스 주석에는
    "이런 문구를 쓰지 않는다"는 설명 자체가 그 금지 단어를 포함할 수 있으므로
    (예: 이 섹션 헤더 주석), 주석이 아니라 실제 text= 리터럴만 검사한다."""
    import re

    section_source = inspect.getsource(ui.SalesDbCrawlerApp._build_collection_mode_section)
    code_lines = [line for line in section_source.splitlines() if not line.strip().startswith("#")]
    text_literals = re.findall(r'text=\(?\s*"([^"]*)"', "\n".join(code_lines))
    forbidden = ["프리미엄", "유료", "제한 모드", "상세 페이지 방문"]
    found = [word for word in forbidden if any(word in literal for literal in text_literals)]
    if not found:
        reporter.pass_("수집 모드 섹션의 실제 노출 문구에 금지 표현(프리미엄/유료/제한 모드/상세 페이지 방문) 없음")
    else:
        reporter.fail(f"수집 모드 섹션 노출 문구에 금지 표현 발견: {found}")


def main() -> int:
    reporter = ValidationReporter()
    checks = [
        check_default_collector_factory_is_apollo_first_list_collector,
        check_run_network_pipeline_has_collection_mode_param_default_basic,
        check_run_network_pipeline_has_home_enrichment_fn_default,
        check_run_network_pipeline_worker_accepts_collection_mode,
        check_init_sets_collection_mode_var_default_basic,
        check_collection_mode_section_wired_into_build_ui,
        check_no_premium_or_paid_wording_in_collection_mode_section,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
