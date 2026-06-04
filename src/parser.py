# V1 parser placeholder. Implementation is intentionally excluded in STEP 1.


# 2026-06-04: V1 Excel 저장 전 정리 단계에서 사용할 컬럼 순서입니다.
COLUMNS = [
    "업체명",
    "업종",
    "주소",
    "대표전화",
    "플레이스 URL",
    "수집일",
]


def normalize_text(value) -> str:
    """2026-06-04: None과 불필요한 공백을 안전하게 정리합니다."""
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def clean_address(address: str) -> str:
    """2026-06-04: 주소 앞의 UI 텍스트를 제거하고 공백을 정리합니다."""
    cleaned = normalize_text(address)
    if cleaned.startswith("주소보기"):
        cleaned = cleaned[len("주소보기") :]
    return normalize_text(cleaned)


def parse_places(raw_places: list[dict]) -> list[dict]:
    """2026-06-04: crawler 결과를 컬럼 순서 고정, 주소 정리, 중복 제거합니다."""
    parsed_places = []
    seen = set()

    for raw_place in raw_places:
        place = {
            "업체명": normalize_text(raw_place.get("업체명")),
            "업종": normalize_text(raw_place.get("업종")),
            "주소": clean_address(raw_place.get("주소")),
            "대표전화": normalize_text(raw_place.get("대표전화")),
            "플레이스 URL": normalize_text(raw_place.get("플레이스 URL")),
            "수집일": normalize_text(raw_place.get("수집일")),
        }

        if not place["업체명"]:
            continue

        dedupe_key = (place["업체명"], place["주소"], place["대표전화"])
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        parsed_places.append({column: place[column] for column in COLUMNS})

    return parsed_places


if __name__ == "__main__":
    # 2026-06-04: 주소보기 제거 및 중복 제거 확인용 최소 테스트입니다.
    sample_data = [
        {
            "업체명": "테스트 카페",
            "업종": "카페,디저트",
            "주소": "주소보기 대전 서구 둔산로 1",
            "대표전화": "042-123-4567",
            "플레이스 URL": "https://m.map.naver.com/place/1",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "테스트 카페",
            "업종": "카페,디저트",
            "주소": " 대전   서구   둔산로 1 ",
            "대표전화": "042-123-4567",
            "플레이스 URL": "https://m.map.naver.com/place/1",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "",
            "업종": "식료품제조",
            "주소": "주소보기 대전 유성구 대학로 1",
            "대표전화": "042-000-0000",
            "플레이스 URL": "https://m.map.naver.com/place/2",
            "수집일": "2026-06-04",
        },
    ]
    print(parse_places(sample_data))
