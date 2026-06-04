# V1 exporter placeholder. Implementation is intentionally excluded in STEP 1.

from pathlib import Path

import pandas as pd
from openpyxl.styles import Font


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
        max_length = len(header)
        for cell in column_cells[1:]:
            value = "" if cell.value is None else str(cell.value)
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
            "리뷰수": "123",
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
