from pathlib import Path
import sys


# ARCH-300C PoC-4: src/pc/region_expander.py 검증용 standalone 스크립트(live 없음,
# 순수 문자열 조합 로직만 검증). API 호출이 전혀 없는 순수 함수이므로 fixture 없이도
# 직접 인자로 테스트한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.region_expander import build_dong_queries


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


def main() -> int:
    reporter = ValidationReporter()

    check_dong_keyword_cartesian_product(reporter)
    check_duplicate_dong_removed(reporter)
    check_duplicate_keyword_removed(reporter)
    check_whitespace_only_entries_filtered(reporter)
    check_empty_dongs_or_keywords_returns_empty_list(reporter)
    check_query_string_format(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
