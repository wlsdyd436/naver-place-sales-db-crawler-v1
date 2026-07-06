from pathlib import Path
import sys
import tempfile

from openpyxl import load_workbook


# Stage 3C: exporter 단일 스키마 확장(통합_결과 온라인 채널 컬럼 append) 검증 스크립트.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import exporter
from src.exporter import (
    MERGED_COLUMNS,
    MOBILE_COLUMNS,
    PC_COLUMNS,
    export_places_to_excel,
)


# 기존 8개 컬럼(순서/이름 불변) + 신규 3개 append.
FROZEN_MERGED_HEAD = [
    "업체명",
    "업종",
    "새로오픈여부",
    "리뷰수",
    "주소",
    "대표전화",
    "플레이스 URL",
    "수집일",
]
NEW_MERGED_TAIL = ["홈페이지", "인스타", "블로그"]
EXPECTED_MERGED = FROZEN_MERGED_HEAD + NEW_MERGED_TAIL
EXPECTED_MOBILE = ["업체명", "업종", "주소", "대표전화", "플레이스 URL", "수집일"]
EXPECTED_PC = ["업체명", "업종", "새로오픈여부", "리뷰수", "주소", "수집일"]


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


def _new_engine_row():
    # collect_pc_full 결과 형태(가산 필드 + place_id 포함).
    return {
        "업체명": "오베르캄프 본점",
        "업종": "베이커리",
        "새로오픈여부": "",
        "리뷰수": "2469",
        "주소": "서울 강동구 성내로14길 48 1층",
        "대표전화": "0507-1387-4967",
        "플레이스 URL": "https://pcmap.place.naver.com/restaurant/1171815551/home",
        "place_id": "1171815551",
        "수집일": "2026-07-06",
        "홈페이지": "",
        "인스타": "https://www.instagram.com/oberkampf.kr",
        "블로그": "",
    }


def _legacy_row():
    # SNS 필드가 없는 기존 흐름 행(모바일/merge 결과 형태).
    return {
        "업체명": "레거시 카페",
        "업종": "카페",
        "새로오픈여부": "O",
        "리뷰수": "10",
        "주소": "서울 강동구 어딘가",
        "대표전화": "02-000-0000",
        "플레이스 URL": "https://m.place.naver.com/place/1/home",
        "수집일": "2026-07-06",
    }


def _read_headers(path, sheet_name):
    workbook = load_workbook(path, data_only=True)
    worksheet = workbook[sheet_name]
    return [cell.value for cell in worksheet[1]]


def _read_rows(path, sheet_name):
    workbook = load_workbook(path, data_only=True)
    worksheet = workbook[sheet_name]
    headers = [cell.value for cell in worksheet[1]]
    rows = []
    for values in worksheet.iter_rows(min_row=2, values_only=True):
        rows.append(dict(zip(headers, values)))
    return rows


# ---------------------------------------------------------------------------
# 1. 모듈 상수 스키마
# ---------------------------------------------------------------------------


def check_merged_columns_constant(reporter: ValidationReporter) -> None:
    if MERGED_COLUMNS[:8] == FROZEN_MERGED_HEAD:
        reporter.pass_("MERGED_COLUMNS 앞 8개 컬럼 이름/순서 불변")
    else:
        reporter.fail(f"기존 8개 컬럼이 변경됨: {MERGED_COLUMNS[:8]}")

    if MERGED_COLUMNS == EXPECTED_MERGED:
        reporter.pass_("MERGED_COLUMNS = 기존 8개 + [홈페이지, 인스타, 블로그] append")
    else:
        reporter.fail(f"MERGED_COLUMNS 확장 결과가 예상과 다름: {MERGED_COLUMNS}")


def check_other_columns_unchanged(reporter: ValidationReporter) -> None:
    if MOBILE_COLUMNS == EXPECTED_MOBILE and PC_COLUMNS == EXPECTED_PC:
        reporter.pass_("MOBILE_COLUMNS / PC_COLUMNS 무변경")
    else:
        reporter.fail(f"원본 시트 컬럼이 변경됨: mobile={MOBILE_COLUMNS}, pc={PC_COLUMNS}")


# ---------------------------------------------------------------------------
# 2. 실제 저장 파일 스키마
# ---------------------------------------------------------------------------


def check_exported_merged_headers(reporter: ValidationReporter) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "schema_test.xlsx"
        export_places_to_excel([_new_engine_row(), _legacy_row()], [], [], str(path))

        merged_headers = _read_headers(path, "통합_결과")
        checks = {
            "통합_결과 헤더 11개(기존8+신규3)": merged_headers == EXPECTED_MERGED,
            "place_id는 통합_결과 컬럼에 미노출": "place_id" not in merged_headers,
            "원본_모바일 헤더 무변경": _read_headers(path, "원본_모바일") == EXPECTED_MOBILE,
            "원본_PC 헤더 무변경": _read_headers(path, "원본_PC") == EXPECTED_PC,
        }
        if all(checks.values()):
            reporter.pass_("저장 파일 3시트 헤더: 통합_결과만 append 확장, place_id 미노출, 원본 시트 불변")
        else:
            failed = [name for name, ok in checks.items() if not ok]
            reporter.fail(f"저장 헤더 검증 실패 항목: {failed} (통합_결과={merged_headers})")


def check_new_engine_row_values(reporter: ValidationReporter) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "values_test.xlsx"
        export_places_to_excel([_new_engine_row()], [], [], str(path))
        rows = _read_rows(path, "통합_결과")
        row = rows[0] if rows else {}
        ok = (
            row.get("업체명") == "오베르캄프 본점"
            and row.get("대표전화") == "0507-1387-4967"
            and row.get("플레이스 URL") == "https://pcmap.place.naver.com/restaurant/1171815551/home"
            and row.get("인스타") == "https://www.instagram.com/oberkampf.kr"
        )
        if ok:
            reporter.pass_("PC full 엔진 row가 통합_결과 11개 컬럼에 정확히 매핑(대표전화/URL/인스타 포함)")
        else:
            reporter.fail(f"새 엔진 row 매핑 결과가 예상과 다름: {row}")


def check_legacy_row_blank_sns(reporter: ValidationReporter) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "legacy_test.xlsx"
        export_places_to_excel([_legacy_row()], [], [], str(path))
        rows = _read_rows(path, "통합_결과")
        row = rows[0] if rows else {}

        def _blank(value):
            return value is None or str(value).strip() == ""

        ok = (
            row.get("업체명") == "레거시 카페"
            and _blank(row.get("홈페이지"))
            and _blank(row.get("인스타"))
            and _blank(row.get("블로그"))
        )
        if ok:
            reporter.pass_("SNS 필드 없는 기존 흐름 행은 홈페이지/인스타/블로그가 빈칸(get 기본값)")
        else:
            reporter.fail(f"레거시 행 빈칸 처리 결과가 예상과 다름: {row}")


def check_signature_unchanged(reporter: ValidationReporter) -> None:
    # export_places_to_excel 시그니처(위치 인자 4개)와 반환 경로 계약 유지 확인.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sig_test.xlsx"
        returned = export_places_to_excel([_legacy_row()], [_legacy_row()], [_legacy_row()], str(path))
        if returned == str(path) and Path(returned).exists():
            reporter.pass_("export_places_to_excel 시그니처/반환 경로 계약 유지")
        else:
            reporter.fail(f"export 반환/저장 계약이 예상과 다름: {returned!r}")


def main() -> int:
    reporter = ValidationReporter()

    check_merged_columns_constant(reporter)
    check_other_columns_unchanged(reporter)
    check_exported_merged_headers(reporter)
    check_new_engine_row_values(reporter)
    check_legacy_row_blank_sns(reporter)
    check_signature_unchanged(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
