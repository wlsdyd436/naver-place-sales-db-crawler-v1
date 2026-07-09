from pathlib import Path
import sys


# ARCH-300C PoC-4: src/pc/region_expander.py 검증용 standalone 스크립트(live 없음,
# 순수 문자열 조합 로직만 검증). API 호출이 전혀 없는 순수 함수이므로 fixture 없이도
# 직접 인자로 테스트한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.region_expander import (
    build_dong_queries,
    build_landmark_queries,
    build_subcategory_queries,
    build_tiered_query_queue,
)


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


def check_dong_keyword_cartesian_product(reporter: ValidationReporter) -> None:
    """동 3개 × 키워드 2개 = 6건, 순서는 dong -> keyword 순."""
    result = build_dong_queries(
        "서울특별시", "강동구", ["천호동", "성내동", "길동"], ["카페", "미용실"]
    )
    ok = (
        len(result) == 6
        and result[0] == {
            "city": "서울특별시", "gu": "강동구", "dong": "천호동",
            "keyword": "카페", "query": "서울특별시 강동구 천호동 카페",
        }
        and result[1]["keyword"] == "미용실"
        and result[2]["dong"] == "성내동"
        and result[-1] == {
            "city": "서울특별시", "gu": "강동구", "dong": "길동",
            "keyword": "미용실", "query": "서울특별시 강동구 길동 미용실",
        }
    )
    if ok:
        reporter.pass_("동 3개 × 키워드 2개 = 6건, dong->keyword 순서와 필드 구성이 정확함")
    else:
        reporter.fail(f"곱집합 생성 결과가 예상과 다름: {result}")


def check_duplicate_dong_removed(reporter: ValidationReporter) -> None:
    """완전히 동일한 동 이름이 여러 번 들어와도 1회만 사용된다(순서 보존)."""
    result = build_dong_queries(
        "서울특별시", "강동구", ["천호동", "성내동", "천호동", "성내동"], ["카페"]
    )
    dongs_in_order = [r["dong"] for r in result]
    if dongs_in_order == ["천호동", "성내동"]:
        reporter.pass_("중복 동 이름은 순서를 보존한 채 1회만 사용됨")
    else:
        reporter.fail(f"중복 제거 결과가 예상과 다름: {dongs_in_order}")


def check_duplicate_keyword_removed(reporter: ValidationReporter) -> None:
    """완전히 동일한 키워드가 여러 번 들어와도 1회만 사용된다."""
    result = build_dong_queries("서울특별시", "강동구", ["천호동"], ["카페", "카페", "베이커리"])
    keywords_in_order = [r["keyword"] for r in result]
    if keywords_in_order == ["카페", "베이커리"]:
        reporter.pass_("중복 키워드는 순서를 보존한 채 1회만 사용됨")
    else:
        reporter.fail(f"중복 키워드 제거 결과가 예상과 다름: {keywords_in_order}")


def check_whitespace_only_entries_filtered(reporter: ValidationReporter) -> None:
    """공백만 있는 동/키워드 항목은 제외된다."""
    result = build_dong_queries("서울특별시", "강동구", ["천호동", "   ", "", "성내동"], ["카페", "  "])
    dongs_in_order = [r["dong"] for r in result]
    if dongs_in_order == ["천호동", "성내동"] and all(r["keyword"] == "카페" for r in result):
        reporter.pass_("공백/빈 문자열 동·키워드 항목은 제외되고 유효한 항목만 사용됨")
    else:
        reporter.fail(f"공백 방어 결과가 예상과 다름: {result}")


def check_empty_dongs_or_keywords_returns_empty_list(reporter: ValidationReporter) -> None:
    """dongs 또는 keywords가 비어 있으면(또는 전부 공백) 예외 없이 빈 리스트를 반환한다."""
    cases = [
        ("빈 dongs 리스트", build_dong_queries("서울특별시", "강동구", [], ["카페"])),
        ("빈 keywords 리스트", build_dong_queries("서울특별시", "강동구", ["천호동"], [])),
        ("dongs 전부 공백", build_dong_queries("서울특별시", "강동구", ["   ", ""], ["카페"])),
        ("keywords 전부 공백", build_dong_queries("서울특별시", "강동구", ["천호동"], ["   "])),
        ("city 공백", build_dong_queries("   ", "강동구", ["천호동"], ["카페"])),
        ("gu 공백", build_dong_queries("서울특별시", "", ["천호동"], ["카페"])),
        ("dongs=None", build_dong_queries("서울특별시", "강동구", None, ["카페"])),
        ("keywords=None", build_dong_queries("서울특별시", "강동구", ["천호동"], None)),
    ]
    failed = [label for label, result in cases if result != []]
    if not failed:
        reporter.pass_("dongs/keywords/city/gu 중 하나라도 비면 예외 없이 빈 리스트 반환(8개 케이스 전부)")
    else:
        reporter.fail(f"빈 입력 방어 실패 케이스: {failed}")


def check_query_string_format(reporter: ValidationReporter) -> None:
    """query 문자열이 '시 구 동 키워드' 형태로 정확히 조합되는지 확인한다."""
    result = build_dong_queries("서울특별시", "강동구", ["암사동"], ["부동산"])
    if len(result) == 1 and result[0]["query"] == "서울특별시 강동구 암사동 부동산":
        reporter.pass_("query 문자열이 '시 구 동 키워드' 형태로 정확히 조합됨")
    else:
        reporter.fail(f"query 포맷 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# PoC-6: Tier2(역/상권) build_landmark_queries 검증
# ---------------------------------------------------------------------------


def check_landmark_keyword_cartesian_product(reporter: ValidationReporter) -> None:
    """역/상권 2개 × 키워드 1개 = 2건, tier/source_layer가 태깅된다."""
    result = build_landmark_queries("서울특별시", "강동구", ["천호역", "강동역"], ["카페"])
    ok = (
        len(result) == 2
        and result[0] == {
            "city": "서울특별시", "gu": "강동구", "landmark": "천호역",
            "keyword": "카페", "query": "서울특별시 강동구 천호역 카페",
            "tier": "tier2", "source_layer": "역상권",
        }
        and result[1]["landmark"] == "강동역"
    )
    if ok:
        reporter.pass_("build_landmark_queries가 역/상권 곱집합을 tier2/역상권 태깅과 함께 생성")
    else:
        reporter.fail(f"build_landmark_queries 결과가 예상과 다름: {result}")


def check_landmark_queries_empty_input_returns_empty_list(reporter: ValidationReporter) -> None:
    """랜드마크/키워드가 비면(공백 포함) 예외 없이 빈 리스트를 반환한다."""
    cases = [
        build_landmark_queries("서울특별시", "강동구", [], ["카페"]),
        build_landmark_queries("서울특별시", "강동구", ["천호역"], []),
        build_landmark_queries("서울특별시", "강동구", ["   ", ""], ["카페"]),
        build_landmark_queries("", "강동구", ["천호역"], ["카페"]),
    ]
    if all(result == [] for result in cases):
        reporter.pass_("build_landmark_queries도 빈 입력 방어가 build_dong_queries와 동일하게 동작")
    else:
        reporter.fail(f"build_landmark_queries 빈 입력 방어 실패: {cases}")


# ---------------------------------------------------------------------------
# PoC-6: Tier3(세부업종) build_subcategory_queries 검증
# ---------------------------------------------------------------------------


def check_subcategory_dong_cartesian_product(reporter: ValidationReporter) -> None:
    """동 2개 × 세부업종 2개 = 4건, tier/source_layer가 태깅된다."""
    result = build_subcategory_queries(
        "서울특별시", "강동구", ["천호동", "성내동"], ["디저트카페", "브런치카페"]
    )
    ok = (
        len(result) == 4
        and result[0] == {
            "city": "서울특별시", "gu": "강동구", "dong": "천호동",
            "subcategory": "디저트카페", "query": "서울특별시 강동구 천호동 디저트카페",
            "tier": "tier3", "source_layer": "세부업종",
        }
        and result[-1]["dong"] == "성내동"
        and result[-1]["subcategory"] == "브런치카페"
    )
    if ok:
        reporter.pass_("build_subcategory_queries가 동×세부업종 곱집합을 tier3/세부업종 태깅과 함께 생성")
    else:
        reporter.fail(f"build_subcategory_queries 결과가 예상과 다름: {result}")


def check_subcategory_queries_empty_input_returns_empty_list(reporter: ValidationReporter) -> None:
    """동/세부업종이 비면 예외 없이 빈 리스트를 반환한다."""
    cases = [
        build_subcategory_queries("서울특별시", "강동구", [], ["디저트카페"]),
        build_subcategory_queries("서울특별시", "강동구", ["천호동"], []),
    ]
    if all(result == [] for result in cases):
        reporter.pass_("build_subcategory_queries도 빈 입력 방어가 build_dong_queries와 동일하게 동작")
    else:
        reporter.fail(f"build_subcategory_queries 빈 입력 방어 실패: {cases}")


# ---------------------------------------------------------------------------
# PoC-6: build_tiered_query_queue 조합 순서/태깅 검증
# ---------------------------------------------------------------------------


def check_tiered_queue_default_order_and_tagging(reporter: ValidationReporter) -> None:
    """기본 enabled_tiers 순서(tier1 -> tier3 -> tier2)로 이어붙여지고, tier1도
    tier/source_layer가 채워지는지 확인한다(build_dong_queries 자체는 그
    필드를 만들지 않으므로 build_tiered_query_queue가 채워야 함)."""
    queue = build_tiered_query_queue(
        "서울특별시", "강동구",
        keywords=["카페"],
        legal_dongs=["천호동"],
        subcategory_dongs=["천호동"],
        subcategories=["디저트카페"],
        landmarks=["천호역"],
    )
    tiers_in_order = [q["tier"] for q in queue]
    ok = (
        len(queue) == 3
        and tiers_in_order == ["tier1", "tier3", "tier2"]
        and queue[0]["source_layer"] == "법정동"
        and queue[0]["dong"] == "천호동" and queue[0]["keyword"] == "카페"
        and queue[1]["source_layer"] == "세부업종"
        and queue[2]["source_layer"] == "역상권"
    )
    if ok:
        reporter.pass_("build_tiered_query_queue가 기본 순서(tier1->tier3->tier2)로 조합하고 tier1도 태깅함")
    else:
        reporter.fail(f"build_tiered_query_queue 기본 순서 결과가 예상과 다름: {queue}")


def check_tiered_queue_enabled_tiers_filters_and_reorders(reporter: ValidationReporter) -> None:
    """enabled_tiers로 특정 tier만 선택하거나 순서를 바꿀 수 있다."""
    only_tier1 = build_tiered_query_queue(
        "서울특별시", "강동구", keywords=["카페"], legal_dongs=["천호동"], enabled_tiers=("tier1",)
    )
    reordered = build_tiered_query_queue(
        "서울특별시", "강동구",
        keywords=["카페"], legal_dongs=["천호동"], landmarks=["천호역"],
        enabled_tiers=("tier2", "tier1"),
    )
    ok = (
        len(only_tier1) == 1 and only_tier1[0]["tier"] == "tier1"
        and [q["tier"] for q in reordered] == ["tier2", "tier1"]
    )
    if ok:
        reporter.pass_("enabled_tiers로 tier 선택/순서를 자유롭게 제어할 수 있음")
    else:
        reporter.fail(f"enabled_tiers 제어 결과가 예상과 다름: only_tier1={only_tier1}, reordered={reordered}")


def check_tiered_queue_missing_tier_input_yields_empty_segment(reporter: ValidationReporter) -> None:
    """특정 tier의 입력(예: landmarks)이 비어 있으면 그 tier만 결과에서 빠진다(예외 없음)."""
    queue = build_tiered_query_queue(
        "서울특별시", "강동구",
        keywords=["카페"], legal_dongs=["천호동"], landmarks=[],
        enabled_tiers=("tier1", "tier2"),
    )
    if len(queue) == 1 and queue[0]["tier"] == "tier1":
        reporter.pass_("landmarks가 비어도 예외 없이 tier2 구간만 빈 채로 tier1만 반환됨")
    else:
        reporter.fail(f"입력 누락 tier 처리 결과가 예상과 다름: {queue}")


def main() -> int:
    reporter = ValidationReporter()

    check_dong_keyword_cartesian_product(reporter)
    check_duplicate_dong_removed(reporter)
    check_duplicate_keyword_removed(reporter)
    check_whitespace_only_entries_filtered(reporter)
    check_empty_dongs_or_keywords_returns_empty_list(reporter)
    check_query_string_format(reporter)
    check_landmark_keyword_cartesian_product(reporter)
    check_landmark_queries_empty_input_returns_empty_list(reporter)
    check_subcategory_dong_cartesian_product(reporter)
    check_subcategory_queries_empty_input_returns_empty_list(reporter)
    check_tiered_queue_default_order_and_tagging(reporter)
    check_tiered_queue_enabled_tiers_filters_and_reorders(reporter)
    check_tiered_queue_missing_tier_input_yields_empty_segment(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
