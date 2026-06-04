import re
from collections import Counter


MERGED_COLUMNS = [
    "업체명",
    "업종",
    "주소",
    "대표전화",
    "플레이스 URL",
    "새로오픈여부",
    "리뷰수",
    "수집일",
]


def normalize_place_name(name: str) -> str:
    """2026-06-04: 안전한 병합 비교를 위해 업체명을 보수적으로 정규화합니다."""
    if name is None:
        return ""

    normalized = str(name).strip().lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("(", "").replace(")", "")
    normalized = normalized.replace("[", "").replace("]", "")
    normalized = normalized.replace("{", "").replace("}", "")
    normalized = re.sub(r"[^0-9a-z가-힣]", "", normalized)
    return normalized


def _blank_enrichment(item: dict) -> dict:
    merged = dict(item)
    merged["새로오픈여부"] = ""
    merged["리뷰수"] = ""
    return {column: merged.get(column, "") for column in MERGED_COLUMNS}


def safe_merge_places(mobile_data: list[dict], pc_data: list[dict]) -> list[dict]:
    """2026-06-04: 모바일 Basic 결과를 기준으로 PC Premium 새로오픈/리뷰수만 안전하게 보강합니다."""
    pc_by_name = {}
    pc_name_counts = Counter()

    for pc_item in pc_data:
        normalized_name = normalize_place_name(pc_item.get("업체명"))
        if not normalized_name:
            continue
        pc_name_counts[normalized_name] += 1
        pc_by_name.setdefault(normalized_name, pc_item)

    merged_results = []
    matched_count = 0
    ambiguous_count = 0
    unmatched_count = 0

    for mobile_item in mobile_data:
        normalized_name = normalize_place_name(mobile_item.get("업체명"))
        if not normalized_name or len(normalized_name) <= 2:
            unmatched_count += 1
            merged_results.append(_blank_enrichment(mobile_item))
            continue

        if pc_name_counts.get(normalized_name, 0) > 1:
            ambiguous_count += 1
            merged_results.append(_blank_enrichment(mobile_item))
            continue

        pc_item = pc_by_name.get(normalized_name)
        if not pc_item:
            unmatched_count += 1
            merged_results.append(_blank_enrichment(mobile_item))
            continue

        merged = dict(mobile_item)
        merged["새로오픈여부"] = pc_item.get("새로오픈여부", "")
        merged["리뷰수"] = pc_item.get("리뷰수", "")
        merged_results.append({column: merged.get(column, "") for column in MERGED_COLUMNS})
        matched_count += 1

    print(f"[merger] mobile count={len(mobile_data)}")
    print(f"[merger] pc count={len(pc_data)}")
    print(f"[merger] matched count={matched_count}")
    print(f"[merger] ambiguous count={ambiguous_count}")
    print(f"[merger] unmatched count={unmatched_count}")

    return merged_results


if __name__ == "__main__":
    # 2026-06-04: 정확 매칭, 공백 차이, 미매칭, 중복명, 짧은 이름 검증용 샘플입니다.
    mobile_sample = [
        {
            "업체명": "카페인터뷰체크메이트",
            "업종": "카페,디저트",
            "주소": "대전 서구 둔산동",
            "대표전화": "042-111-1111",
            "플레이스 URL": "https://m.place.naver.com/place/1/home",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "스타벅스 (강남점)",
            "업종": "카페",
            "주소": "서울 강남구 역삼동",
            "대표전화": "02-111-1111",
            "플레이스 URL": "https://m.place.naver.com/place/2/home",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "매칭없는카페",
            "업종": "카페",
            "주소": "",
            "대표전화": "",
            "플레이스 URL": "",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "중복카페",
            "업종": "카페",
            "주소": "",
            "대표전화": "",
            "플레이스 URL": "",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "옘",
            "업종": "카페,디저트",
            "주소": "",
            "대표전화": "",
            "플레이스 URL": "",
            "수집일": "2026-06-04",
        },
    ]

    pc_sample = [
        {
            "업체명": "카페인터뷰 체크메이트",
            "새로오픈여부": "O",
            "리뷰수": "80",
        },
        {
            "업체명": "스타벅스강남점",
            "새로오픈여부": "",
            "리뷰수": "1234",
        },
        {
            "업체명": "중복카페",
            "새로오픈여부": "O",
            "리뷰수": "10",
        },
        {
            "업체명": "중복카페",
            "새로오픈여부": "O",
            "리뷰수": "20",
        },
    ]

    print(safe_merge_places(mobile_sample, pc_sample))
