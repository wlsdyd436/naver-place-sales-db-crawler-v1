from pathlib import Path
import sys


# UI-CLEANUP-1C: src.ui.build_collection_queries 검증용 standalone 스크립트
# (Tk/실제 앱 인스턴스 없이 순수 함수만 테스트). 여러 구 선택 + 세부구역
# 체크 상태가 실제 수집 쿼리 생성에 어떻게 반영되는지가 이번 검증의 핵심이다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ui import build_collection_queries


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


CITY = "서울특별시"


def check_case_a_single_district_with_subregions(reporter: ValidationReporter) -> None:
    """케이스 A: 강동구 + 세부구역 3개 선택 -> 쿼리 3개."""
    district_selections = [
        {
            "district": "강동구",
            "has_subregion_data": True,
            "selected_subregions": ["천호동", "길동", "천호역"],
        },
    ]
    jobs = build_collection_queries(CITY, district_selections, "카페")
    queries = [job["query"] for job in jobs]
    expected = ["서울특별시 강동구 천호동 카페", "서울특별시 강동구 길동 카페", "서울특별시 강동구 천호역 카페"]
    if queries == expected and all(job["keyword"] == "카페" for job in jobs):
        reporter.pass_("케이스 A: 강동구 세부구역 3개 선택 시 쿼리 3개가 순서대로 생성됨")
    else:
        reporter.fail(f"케이스 A 결과가 예상과 다름: {queries}")


def check_case_b_multiple_districts_mixed_data(reporter: ValidationReporter) -> None:
    """케이스 B: 강동구(세부구역 3개) + 송파구(데이터 없음) -> 쿼리 4개."""
    district_selections = [
        {
            "district": "강동구",
            "has_subregion_data": True,
            "selected_subregions": ["천호동", "길동", "천호역"],
        },
        {
            "district": "송파구",
            "has_subregion_data": False,
            "selected_subregions": [],
        },
    ]
    jobs = build_collection_queries(CITY, district_selections, "카페")
    queries = [job["query"] for job in jobs]
    expected = [
        "서울특별시 강동구 천호동 카페",
        "서울특별시 강동구 길동 카페",
        "서울특별시 강동구 천호역 카페",
        "서울특별시 송파구 카페",
    ]
    if queries == expected:
        reporter.pass_("케이스 B: 강동구 세부구역 3개 + 송파구 fallback 1개 = 총 4개 쿼리가 순서대로 생성됨")
    else:
        reporter.fail(f"케이스 B 결과가 예상과 다름: {queries}")


def check_case_c_all_subregions_deselected_excludes_district(reporter: ValidationReporter) -> None:
    """케이스 C: 강동구 세부구역 전부 해제(데이터는 있음) -> 쿼리 0개(fallback 아님)."""
    district_selections = [
        {
            "district": "강동구",
            "has_subregion_data": True,
            "selected_subregions": [],
        },
    ]
    jobs = build_collection_queries(CITY, district_selections, "카페")
    if jobs == []:
        reporter.pass_("케이스 C: 세부구역 데이터가 있는 구에서 전부 해제하면 fallback 없이 쿼리 0개")
    else:
        reporter.fail(f"케이스 C 결과가 예상과 다름: {jobs}")


def check_case_d_district_without_data_uses_fallback(reporter: ValidationReporter) -> None:
    """케이스 D: 강남구(데이터 없음) -> 구 기준 fallback 쿼리 1개."""
    district_selections = [
        {"district": "강남구", "has_subregion_data": False, "selected_subregions": []},
    ]
    jobs = build_collection_queries(CITY, district_selections, "카페")
    if len(jobs) == 1 and jobs[0] == {"region": "서울특별시 강남구", "keyword": "카페", "query": "서울특별시 강남구 카페"}:
        reporter.pass_("케이스 D: 데이터 없는 강남구는 구 기준 fallback 쿼리 1개만 생성됨")
    else:
        reporter.fail(f"케이스 D 결과가 예상과 다름: {jobs}")


def check_duplicate_queries_are_removed_preserving_order(reporter: ValidationReporter) -> None:
    """동일한 쿼리 문자열이 중복 생성되면 처음 등장한 순서를 유지한 채 1개만 남는다."""
    district_selections = [
        {"district": "강동구", "has_subregion_data": True, "selected_subregions": ["천호동", "천호동", "길동"]},
    ]
    jobs = build_collection_queries(CITY, district_selections, "카페")
    queries = [job["query"] for job in jobs]
    if queries == ["서울특별시 강동구 천호동 카페", "서울특별시 강동구 길동 카페"]:
        reporter.pass_("중복 세부구역으로 인한 중복 쿼리가 순서를 유지한 채 제거됨")
    else:
        reporter.fail(f"중복 제거 결과가 예상과 다름: {queries}")


def check_empty_district_selections_returns_empty_list(reporter: ValidationReporter) -> None:
    if build_collection_queries(CITY, [], "카페") == []:
        reporter.pass_("선택된 구가 없으면 예외 없이 빈 쿼리 목록을 반환함")
    else:
        reporter.fail("빈 district_selections 처리 결과가 예상과 다름")


def main() -> int:
    reporter = ValidationReporter()

    check_case_a_single_district_with_subregions(reporter)
    check_case_b_multiple_districts_mixed_data(reporter)
    check_case_c_all_subregions_deselected_excludes_district(reporter)
    check_case_d_district_without_data_uses_fallback(reporter)
    check_duplicate_queries_are_removed_preserving_order(reporter)
    check_empty_district_selections_returns_empty_list(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
