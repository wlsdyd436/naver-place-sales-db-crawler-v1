from src.crawler import crawl_places
from src.exporter import export_places_to_excel
from src.parser import parse_places


# 2026-06-04: V1 MVP 실행 설정값입니다.
KEYWORD = "대전 치킨"
LIMIT = 10
OUTPUT_PATH = "output/naver_place_sales_db.xlsx"


def main() -> None:
    print(f"[main] keyword={KEYWORD}")
    print(f"[main] limit={LIMIT}")
    print(f"[main] output path={OUTPUT_PATH}")

    raw_places = crawl_places(KEYWORD, LIMIT)
    print(f"[main] raw count={len(raw_places)}")

    parsed_places = parse_places(raw_places)
    print(f"[main] parsed count={len(parsed_places)}")

    output_path = export_places_to_excel(parsed_places, OUTPUT_PATH)
    print(f"[main] saved={output_path}")


if __name__ == "__main__":
    main()
