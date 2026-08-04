"""수집 결과를 .xlsx 파일로 저장한다.

병합 결과(MERGED_COLUMNS)·원본 모바일(MOBILE_COLUMNS)·원본 PC
(PC_COLUMNS) 세 시트를 구성하고, 출력 폴더 생성과 열 너비·줄바꿈 등 기본
서식을 적용한 뒤 저장된 파일 경로를 반환한다. rows가 비어 있을 때 이
모듈을 호출할지 여부는 호출자(`src.ui_export_flow`)의 책임이며, 이 모듈은
전달받은 데이터로 항상 세 시트를 그대로 생성한다. UI 로그나 최종 상태
문구는 담당하지 않는다.
"""

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font


# 2026-07-23 5M-R1: 단일 "리뷰수" 컬럼을 방문자/블로그/총리뷰수 3개로 분리하고
# 13개 컬럼 순서를 확정했다(사용자 확정 스키마). 원본_모바일/원본_PC 시트
# (MOBILE_COLUMNS/PC_COLUMNS)는 legacy 엔진 전용이라 이번 변경 대상이 아니다.
# PAGE300-6E-V3(2026-07-27): 대표 3링크(홈페이지/인스타/블로그) 외 모든 공개
# 채널(카카오채널/유튜브/페이스북/스마트스토어/기타 및 2번째 이후 홈페이지·
# 인스타·블로그)을 보존하기 위해 "추가 링크" 14번째 컬럼을 블로그 다음(마지막)에
# 추가한다. 기존 13컬럼 입력 row는 이 키가 없어도 _rows_with_columns의
# row.get(column, "")로 공란 처리되어 하위 호환된다.
MERGED_COLUMNS = [
    "업체명",
    "업종",
    "새로오픈여부",
    "방문자리뷰수",
    "블로그리뷰수",
    "총리뷰수",
    "주소",
    "대표전화",
    "플레이스 URL",
    "수집일",
    "홈페이지",
    "인스타",
    "블로그",
    "추가 링크",
]

MOBILE_COLUMNS = [
    "업체명",
    "업종",
    "주소",
    "대표전화",
    "플레이스 URL",
    "수집일",
]

PC_COLUMNS = [
    "업체명",
    "업종",
    "새로오픈여부",
    "리뷰수",
    "주소",
    "수집일",
]


def _rows_with_columns(data: list[dict], columns: list[str] | None = None) -> list[dict]:
    # 2026-06-04: 엑셀에는 수식 없이 dict 값을 그대로 텍스트/값으로 저장합니다.
    if columns is None:
        return [dict(row) for row in data]
    return [{column: row.get(column, "") for column in columns} for row in data]


def _apply_basic_format(worksheet) -> None:
    # 2026-06-04: Excel 2016 호환을 위해 기본 서식만 적용합니다.
    worksheet.freeze_panes = "A2"

    for cell in worksheet[1]:
        cell.font = Font(bold=True)

    for column_cells in worksheet.columns:
        header = str(column_cells[0].value or "")
        # PAGE300-6E-V3: "추가 링크"는 줄바꿈으로 구분된 여러 URL을 담으므로
        # wrap_text + 상단 정렬을 적용하고, 열 너비는 전체 글자수가 아니라
        # 가장 긴 한 줄 기준으로 계산한다(그렇지 않으면 링크가 많은 셀 때문에
        # 열이 비정상적으로 넓어짐 - 기존 열 너비 정책 범위 안에서만 조정).
        is_extra_links_column = header == "추가 링크"
        max_length = len(header)
        for cell in column_cells[1:]:
            value = "" if cell.value is None else str(cell.value)
            if is_extra_links_column:
                if value:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                max_length = max(max_length, max((len(line) for line in value.split("\n")), default=0))
            else:
                max_length = max(max_length, len(value))
        adjusted_width = min(max(max_length + 2, 10), 60)
        worksheet.column_dimensions[column_cells[0].column_letter].width = (
            adjusted_width
        )


def export_places_to_excel(
    merged_data: list,
    mobile_data: list,
    pc_data: list,
    output_path: str,
) -> str:
    """2026-06-04: 통합 결과와 원본 데이터를 3개 시트로 저장합니다."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    merged_rows = _rows_with_columns(merged_data, MERGED_COLUMNS)
    mobile_rows = _rows_with_columns(mobile_data, MOBILE_COLUMNS)
    pc_rows = _rows_with_columns(pc_data, PC_COLUMNS)

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        pd.DataFrame(merged_rows, columns=MERGED_COLUMNS).to_excel(
            writer,
            index=False,
            sheet_name="통합_결과",
        )
        pd.DataFrame(mobile_rows, columns=MOBILE_COLUMNS).to_excel(
            writer,
            index=False,
            sheet_name="원본_모바일",
        )
        pd.DataFrame(pc_rows, columns=PC_COLUMNS).to_excel(
            writer,
            index=False,
            sheet_name="원본_PC",
        )

        workbook = writer.book
        workbook.active = workbook.sheetnames.index("통합_결과")

        for sheet_name in ["통합_결과", "원본_모바일", "원본_PC"]:
            _apply_basic_format(writer.sheets[sheet_name])

    return str(output_file)


if __name__ == "__main__":
    # 2026-06-04: 3시트 Excel 저장 동작 확인용 최소 테스트입니다.
    mobile_sample = [
        {
            "업체명": "테스트 카페",
            "업종": "카페,디저트",
            "주소": "대전 서구 둔산로 1",
            "대표전화": "042-123-4567",
            "플레이스 URL": "https://m.place.naver.com/place/1/home",
            "수집일": "2026-06-04",
        }
    ]
    pc_sample = [
        {
            "업체명": "테스트 카페",
            "업종": "카페,디저트",
            "새로오픈여부": "O",
            "리뷰수": "123",
            "주소": "대전 서구 둔산동",
            "수집일": "2026-06-04",
        }
    ]
    merged_sample = [
        {
            "업체명": "테스트 카페",
            "업종": "카페,디저트",
            "새로오픈여부": "O",
            "방문자리뷰수": 100,
            "블로그리뷰수": 23,
            "총리뷰수": 123,
            "주소": "대전 서구 둔산로 1",
            "대표전화": "042-123-4567",
            "플레이스 URL": "https://m.place.naver.com/place/1/home",
            "수집일": "2026-06-04",
        }
    ]
    saved_path = export_places_to_excel(
        merged_sample,
        mobile_sample,
        pc_sample,
        "output/naver_place_merged_db.xlsx",
    )
    print(saved_path)
