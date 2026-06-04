# V1 parser placeholder. Implementation is intentionally excluded in STEP 1.

import re


BASIC_COLUMNS = [
    "업체명",
    "업종",
    "주소",
    "대표전화",
    "플레이스 URL",
    "수집일",
]

PREMIUM_COLUMNS = [
    "업체명",
    "업종",
    "새로오픈여부",
    "리뷰수",
    "주소",
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


# 2026-06-05: crawler 공통 문자열 파싱/정제 함수입니다.
def normalize_place_url_mobile(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return f"https://m.map.naver.com{url}"
    return ""


def normalize_phone(phone_text: str, phone_href: str) -> str:
    if phone_href.startswith("tel:"):
        return phone_href.replace("tel:", "").strip()
    return phone_text.strip()


def detect_new_open_mobile(text: str) -> str:
    return "O" if "새로오픈" in text else ""


def detect_new_open_pc(text: str) -> str:
    return "O" if "새로오픈" in text or "신규오픈" in text else ""


def extract_review_count_mobile(text: str) -> str:
    patterns = [
        r"방문자리뷰\s*([\d,]+)",
        r"블로그리뷰\s*([\d,]+)",
        r"리뷰\s*([\d,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def extract_review_count_pc(text: str) -> str:
    normalized = " ".join(text.split())
    patterns = [
        r"리뷰\s*([0-9,]+)",
        r"방문자리뷰\s*([0-9,]+)",
        r"블로그리뷰\s*([0-9,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return re.sub(r"\D", "", match.group(1))
    return ""


def extract_address_from_pc_text(text: str) -> str:
    address_pattern = re.compile(
        r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
        r"\s+[가-힣]+(?:시|군|구)\s+[가-힣0-9]+(?:동|읍|면)"
    )

    for line in text.splitlines():
        candidate = " ".join(line.split())
        if not candidate:
            continue
        match = address_pattern.search(candidate)
        if match:
            return match.group(0)
    return ""


PC_EXCLUDED_NAME_KEYWORDS = [
    "주간 인기 많은 메뉴",
    "connect+ 혜택",
    "더보기",
    "저장",
    "광고",
    "리뷰",
    "혜택",
    "새로오픈",
    "신규오픈",
    "방문자리뷰",
    "블로그리뷰",
]


def is_valid_pc_place_name(name: str) -> bool:
    if not name:
        return False
    if name == "#":
        return False
    if any(keyword in name for keyword in PC_EXCLUDED_NAME_KEYWORDS):
        return False
    if "*" in name:
        return False
    if len(name) > 40:
        return False
    return True


def split_pc_name_category(name: str, category: str) -> tuple[str, str]:
    category_suffixes = [
        "카페,디저트",
    ]
    if category:
        return name, category
    for suffix in category_suffixes:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)].strip(), suffix
    return name, category


def is_primary_pc_name_anchor(name: str, card_text: str) -> bool:
    lines = [" ".join(line.split()) for line in card_text.splitlines() if line.strip()]
    for line in lines[:3]:
        if name in line:
            return True
    return False


def guess_pc_category_from_text(text: str, name: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    for line in lines[:5]:
        if name and line.startswith(name):
            candidate = line.replace(name, "", 1).strip()
            if 0 < len(candidate) <= 20 and not re.search(
                r"\d|리뷰|저장|공유|광고", candidate
            ):
                return candidate
    for index, line in enumerate(lines[:6]):
        if line == name and index + 1 < len(lines):
            candidate = lines[index + 1]
            if 0 < len(candidate) <= 20 and not re.search(
                r"\d|리뷰|저장|공유|광고", candidate
            ):
                return candidate
    return ""


def _get_columns(mode: str) -> list[str]:
    # 2026-06-04: Basic/Premium 모드별 Excel 컬럼 순서입니다.
    return PREMIUM_COLUMNS if mode == "premium" else BASIC_COLUMNS


def parse_places(raw_places: list[dict], mode: str = "basic") -> list[dict]:
    """2026-06-04: 모드별 컬럼 순서로 crawler 결과를 정리하고 중복 제거합니다."""
    parsed_places = []
    seen = set()
    columns = _get_columns(mode)

    for raw_place in raw_places:
        place = {
            "업체명": normalize_text(raw_place.get("업체명")),
            "업종": normalize_text(raw_place.get("업종")),
            "주소": clean_address(raw_place.get("주소")),
            "대표전화": normalize_text(raw_place.get("대표전화")),
            "플레이스 URL": normalize_text(raw_place.get("플레이스 URL")),
            "새로오픈여부": normalize_text(raw_place.get("새로오픈여부")),
            "리뷰수": normalize_text(raw_place.get("리뷰수")),
            "수집일": normalize_text(raw_place.get("수집일")),
        }

        if not place["업체명"]:
            continue

        dedupe_key = (place["업체명"], place["주소"], place["대표전화"])
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        parsed_places.append({column: place[column] for column in columns})

    return parsed_places


if __name__ == "__main__":
    # 2026-06-04: 주소보기 제거 및 중복 제거 확인용 최소 테스트입니다.
    sample_data = [
        {
            "업체명": "테스트 카페",
            "새로오픈여부": "O",
            "업종": "카페,디저트",
            "리뷰수": "123",
            "주소": "주소보기 대전 서구 둔산로 1",
            "대표전화": "042-123-4567",
            "플레이스 URL": "https://m.map.naver.com/place/1",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "테스트 카페",
            "새로오픈여부": "O",
            "업종": "카페,디저트",
            "리뷰수": "123",
            "주소": " 대전   서구   둔산로 1 ",
            "대표전화": "042-123-4567",
            "플레이스 URL": "https://m.map.naver.com/place/1",
            "수집일": "2026-06-04",
        },
        {
            "업체명": "",
            "새로오픈여부": "",
            "업종": "식료품제조",
            "리뷰수": "",
            "주소": "주소보기 대전 유성구 대학로 1",
            "대표전화": "042-000-0000",
            "플레이스 URL": "https://m.map.naver.com/place/2",
            "수집일": "2026-06-04",
        },
    ]
    print(parse_places(sample_data, mode="basic"))
    print(parse_places(sample_data, mode="premium"))
