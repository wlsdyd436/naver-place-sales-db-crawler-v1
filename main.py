from src.crawler import crawl_places
from src.exporter import export_places_to_excel
from src.parser import parse_places


def main() -> None:
    # 2026-06-04: V1 MVP 기본 실행값입니다.
    keyword = "대전 카페"
    limit = 10

    print(f"[main] keyword={keyword}")
    print(f"[main] limit={limit}")

    raw_places = crawl_places(keyword, limit)
    print(f"[main] raw count={len(raw_places)}")

    parsed_places = parse_places(raw_places)
    print(f"[main] parsed count={len(parsed_places)}")

    output_path = export_places_to_excel(parsed_places)
    print(f"[main] saved={output_path}")


if __name__ == "__main__":
    main()
