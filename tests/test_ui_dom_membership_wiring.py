import inspect
from pathlib import Path
import sys


# PAGE300-DOM-2: src.ui._run_network_pipeline의 기본 collector_factory가
# DomMembershipCollector로 배선되어 있는지(= UI 기본 경로가 DOM-first를
# 사용하는지)만 검증하는 standalone 스크립트. 실제 Playwright/브라우저는
# 절대 실행하지 않는다 - 기본값을 "실제로 호출"하지 않고 함수 시그니처
# introspection(inspect.signature)만으로 확인한다(collector_factory()를
# 실행하면 실제 브라우저를 띄우려 시도하므로 절대 호출하지 않는다).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import ui
from src.pc.network_browser_collector import DomMembershipCollector, NetworkBrowserCollector


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

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print("검증 요약")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"WARN: {self.warn_count}")
        print(f"FINAL: {final}")
        print("====================")


def check_default_collector_factory_is_no_longer_dom_membership_collector(reporter: ValidationReporter) -> None:
    """2026-07-24(신규 두 모드, 사용자 승인): 기본 collector_factory가
    DomMembershipCollector에서 ApolloFirstListCollector로 다시 교체됐다 -
    이 파일 자신이 과거(PAGE300-DOM-2) 같은 방식으로 NetworkBrowserCollector ->
    DomMembershipCollector 전환을 반영했던 선례를 그대로 따른다. 새 기본값에
    대한 상세 검증은 tests/test_ui_apollo_list_wiring.py가 담당하고, 이
    파일은 DomMembershipCollector가 더 이상 기본값이 아니라는 사실과, 여전히
    비활성 fallback capability로 보존되어 있는지만 확인한다."""
    signature = inspect.signature(ui.SalesDbCrawlerApp._run_network_pipeline)
    default = signature.parameters["collector_factory"].default
    if default is not DomMembershipCollector:
        reporter.pass_("_run_network_pipeline 기본 collector_factory가 더 이상 DomMembershipCollector가 아님(신규 ApolloFirstListCollector로 교체됨)")
    else:
        reporter.fail(f"_run_network_pipeline 기본 collector_factory가 여전히 DomMembershipCollector임: {default!r}")


def check_dom_membership_collector_still_importable_for_rollback(reporter: ValidationReporter) -> None:
    """DomMembershipCollector(DOM 풀스크롤 + Apollo + Network 3중 병합)는
    이번 신규 두 모드 도입으로 삭제/수정되지 않고 비활성 fallback capability로
    그대로 보존되어야 한다 - 필요 시 collector_factory=DomMembershipCollector를
    명시적으로 주입해 이전 경로로 되돌릴 수 있다."""
    if DomMembershipCollector is not None and hasattr(DomMembershipCollector, "collect_query"):
        reporter.pass_("DomMembershipCollector가 그대로 보존되어 있어 명시적 opt-out(비상 복구)이 가능함")
    else:
        reporter.fail("DomMembershipCollector가 손상되었거나 collect_query 계약이 없음")


def check_default_collector_factory_is_not_legacy_network_collector(reporter: ValidationReporter) -> None:
    signature = inspect.signature(ui.SalesDbCrawlerApp._run_network_pipeline)
    default = signature.parameters["collector_factory"].default
    if default is not NetworkBrowserCollector:
        reporter.pass_("기본 collector_factory가 더 이상 legacy NetworkBrowserCollector가 아님(명시 주입 시에만 사용 가능)")
    else:
        reporter.fail("기본 collector_factory가 여전히 NetworkBrowserCollector임 - 배선 변경이 반영되지 않음")


def check_network_browser_collector_still_importable_for_rollback(reporter: ValidationReporter) -> None:
    """legacy/비상 복구 경로가 삭제되지 않고 그대로 남아있는지 확인한다 -
    NetworkBrowserCollector는 이번 변경으로 전혀 수정되지 않았고, 필요 시
    collector_factory=NetworkBrowserCollector를 명시적으로 주입해 이전 경로로
    되돌릴 수 있어야 한다."""
    if NetworkBrowserCollector is not None and hasattr(NetworkBrowserCollector, "collect_query"):
        reporter.pass_("NetworkBrowserCollector가 그대로 보존되어 있어 명시적 opt-out(비상 복구)이 가능함")
    else:
        reporter.fail("NetworkBrowserCollector가 손상되었거나 collect_query 계약이 없음")


def main() -> int:
    reporter = ValidationReporter()
    checks = [
        check_default_collector_factory_is_no_longer_dom_membership_collector,
        check_dom_membership_collector_still_importable_for_rollback,
        check_default_collector_factory_is_not_legacy_network_collector,
        check_network_browser_collector_still_importable_for_rollback,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
