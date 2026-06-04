# V1 exporter placeholder. Implementation is intentionally excluded in STEP 1.

from pathlib import Path

import pandas as pd
from openpyxl.styles import Font


# 2026-06-04: V1 Excel 저장 컬럼 순서입니다.
COLUMNS = [
    "업체명",
    "업종",
    "주소",
    "대표전화",
    "플레이스 URL",
    "수집일",
]


def export_places_to_excel(
    places: list[dict], output_path: str = "output/naver_place_sales_db.xlsx"
) -> str:
    """2026-06-04: 정리된 영업 DB 데이터를 Excel 파일로 저장합니다."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for place in places:
        rows.append({column: place.get(column, "") for column in COLUMNS})

    df = pd.DataFrame(rows, columns=COLUMNS)

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="영업DB")
        worksheet = writer.sheets["영업DB"]

        # 2026-06-04: 기본 가독성을 위한 헤더/고정/컬럼 너비 설정입니다.
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

    return str(output_file)


if __name__ == "__main__":
    # 2026-06-04: Excel 저장 동작 확인용 최소 테스트입니다.
    sample_data = [
        {
            "업체명": "테스트 카페",
            "업종": "카페,디저트",
            "주소": "대전 서구 둔산로 1",
            "대표전화": "042-123-4567",
            "플레이스 URL": "https://m.map.naver.com/place/1",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "테스트 제조",
            "업종": "식료품제조",
            "주소": "대전 유성구 대학로 1",
            "대표전화": "042-000-0000",
            "플레이스 URL": "https://m.map.naver.com/place/2",
            "수집일": "2026-06-04",
        },
    ]
    saved_path = export_places_to_excel(sample_data)
    print(saved_path)
