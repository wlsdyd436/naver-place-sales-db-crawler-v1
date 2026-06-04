from datetime import datetime
from pathlib import Path
import sys


# 2026-06-05: V1.2 배포 전 Basic/Premium/Merge/Excel 전체 흐름 QA 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.crawler import crawl_places
from src.exporter import export_places_to_excel
from src.merger import safe_merge_places
from src.parser import parse_places
from src.pc_crawler import crawl_places_pc


LIMIT = 3
BASIC_KEYWORD = "대전 서구 카페"
PREMIUM_KEYWORD = "대전 신상 카페"

BASIC_COLUMNS = ["업체명", "업종", "주소", "대표전화", "플레이스 URL", "수집일"]
PREMIUM_COLUMNS = ["업체명", "업종", "새로오픈여부", "리뷰수", "주소", "수집일"]
MERGED_COLUMNS = [
    "업체명",
    "업종",
    "새로오픈여부",
    "리뷰수",
    "주소",
    "대표전화",
    "플레이스 URL",
    "수집일",
]


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


def assert_columns(
    reporter: ValidationReporter, rows: list[dict], columns: list[str], label: str
) -> None:
    if not rows:
        reporter.warn(f"{label} 데이터 0건 - 컬럼 검증은 샘플 dict로 대체 불가")
        return

    actual_columns = list(rows[0].keys())
    if actual_columns == columns:
        reporter.pass_(f"{label} 컬럼 순서 확인")
    else:
        reporter.fail(f"{label} 컬럼 불일치 - 기대: {columns}, 실제: {actual_columns}")


def validate_required_names(
    reporter: ValidationReporter, rows: list[dict], label: str
) -> None:
    failed = False
    for index, row in enumerate(rows, start=1):
        if not str(row.get("업체명", "")).strip():
            reporter.fail(f"{label} 업체명 누락 - {index}번째 데이터")
            failed = True
    if rows and not failed:
        reporter.pass_(f"{label} 업체명 확인")


def validate_merged_integrity(
    reporter: ValidationReporter, mobile_data: list[dict], merged_data: list[dict]
) -> None:
    if len(merged_data) == len(mobile_data):
        reporter.pass_("Safe Left Join 행 개수 확인")
    else:
        reporter.fail(
            f"Safe Left Join 행 개수 불일치 - mobile={len(mobile_data)}, merged={len(merged_data)}"
        )


def run_basic(reporter: ValidationReporter) -> list[dict]:
    try:
        raw = crawl_places(BASIC_KEYWORD, LIMIT)
        reporter.pass_("Basic 크롤러 실행")
    except Exception as exc:
        reporter.fail(f"Basic 크롤러 실행 실패: {exc}")
        return []

    parsed = parse_places(raw, mode="basic")
    reporter.pass_("Basic parser 실행")
    if not parsed:
        reporter.warn("Basic 수집 결과 0건")
    assert_columns(reporter, parsed, BASIC_COLUMNS, "Basic")
    validate_required_names(reporter, parsed, "Basic")
    return parsed


def run_premium(reporter: ValidationReporter) -> list[dict]:
    try:
        raw = crawl_places_pc(PREMIUM_KEYWORD, LIMIT, new_open_only=False)
        reporter.pass_("Premium 크롤러 실행")
    except Exception as exc:
        reporter.fail(f"Premium 크롤러 실행 실패: {exc}")
        return []

    parsed = parse_places(raw, mode="premium")
    reporter.pass_("Premium parser 실행")
    if not parsed:
        reporter.warn("Premium 수집 결과 0건")
    assert_columns(reporter, parsed, PREMIUM_COLUMNS, "Premium")
    validate_required_names(reporter, parsed, "Premium")
    return parsed


def run_merge(
    reporter: ValidationReporter, mobile_data: list[dict], pc_data: list[dict]
) -> list[dict]:
    try:
        merged = safe_merge_places(mobile_data, pc_data)
        reporter.pass_("Merge 실행")
    except Exception as exc:
        reporter.fail(f"Merge 실행 실패: {exc}")
        return []

    assert_columns(reporter, merged, MERGED_COLUMNS, "병합 결과")
    validate_required_names(reporter, merged, "병합 결과")
    validate_merged_integrity(reporter, mobile_data, merged)
    return merged


def run_excel_export(
    reporter: ValidationReporter,
    merged_data: list[dict],
    mobile_data: list[dict],
    pc_data: list[dict],
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = Path("output") / f"naver_place_qa_validation_{timestamp}.xlsx"

    try:
        saved_path = export_places_to_excel(
            merged_data,
            mobile_data,
            pc_data,
            str(output_path),
        )
        reporter.pass_(f"Excel 저장 실행: {saved_path}")
    except PermissionError:
        reporter.fail("Excel 저장 실패: 파일이 열려 있거나 권한이 없습니다")
        return output_path
    except Exception as exc:
        reporter.fail(f"Excel 저장 실패: {exc}")
        return output_path

    if output_path.exists():
        reporter.pass_("Excel 파일 생성 확인")
    else:
        reporter.fail(f"Excel 파일 생성 실패: {output_path}")
    return output_path


def main() -> int:
    reporter = ValidationReporter()

    mobile_data = run_basic(reporter)
    pc_data = run_premium(reporter)
    merged_data = run_merge(reporter, mobile_data, pc_data)
    excel_path = run_excel_export(reporter, merged_data, mobile_data, pc_data)

    if excel_path.exists():
        print(f"[INFO] Excel 검증 대상: {excel_path}")

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
