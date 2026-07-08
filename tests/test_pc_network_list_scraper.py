from pathlib import Path
import sys


# ARCH-300 PoC-1: src/pc/network_list_scraper.py 검증용 standalone 스크립트(live 없음,
# 샘플 fixture dict 기반). 이 모듈은 UI/pipeline에 연결되지 않으므로, 순수 함수 단위로만
# 검증한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.network_list_scraper import (
    _extract_list_items,
    _map_item_to_row,
    dedup_rows,
    is_candidate_response,
)


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


# allSearch류 응답을 흉내낸 fixture: result.place.list 형태(알려진 경로).
ALLSEARCH_FIXTURE = {
    "result": {
        "place": {
            "totalCount": 2,
            "list": [
                {
                    "id": "111111",
                    "name": "카페 A",
                    "category": "카페",
                    "roadAddress": "서울 강동구 성내로 1",
                    "tel": "02-1111-2222",
                    "visitorReviewCount": 10,
                },
                {
                    "id": "222222",
                    "name": "카페 B",
                    "categoryName": "커피전문점",
                    "address": "서울 강동구 성내로 2(지번)",
                    "virtualTel": "0507-1234-5678",
                    "reviewCount": 5,
                    "homePage": "https://cafeb.example.com",
                },
            ],
        }
    }
}

# graphql/Apollo 유사 중첩 구조 fixture: 알려진 경로에 해당하지 않아 휴리스틱 탐색이 필요.
GRAPHQL_FIXTURE = {
    "data": {
        "searchPlace": {
            "businesses": {
                "items": [
                    {
                        "placeId": "333333",
                        "businessName": "카페 C",
                        "categoryName": "카페",
                        "fullAddress": "서울 강동구 성내로 3",
                    },
                    {
                        "placeId": "444444",
                        "businessName": "카페 D",
                        "categoryName": "카페",
                        "fullAddress": "서울 강동구 성내로 4",
                    },
                ]
            }
        }
    }
}


def check_extract_known_path_allsearch(reporter: ValidationReporter) -> None:
    items = _extract_list_items(ALLSEARCH_FIXTURE)
    ok = (
        len(items) == 2
        and items[0]["id"] == "111111"
        and items[1]["name"] == "카페 B"
    )
    if ok:
        reporter.pass_("result.place.list(알려진 경로) 형태에서 업체 리스트 2건 추출")
    else:
        reporter.fail(f"알려진 경로 추출 결과가 예상과 다름: {items}")


def check_extract_heuristic_graphql(reporter: ValidationReporter) -> None:
    items = _extract_list_items(GRAPHQL_FIXTURE)
    ok = (
        len(items) == 2
        and items[0]["placeId"] == "333333"
        and items[1]["businessName"] == "카페 D"
    )
    if ok:
        reporter.pass_("graphql 유사 중첩 구조(알려진 경로 아님)에서 휴리스틱으로 업체 리스트 2건 추출")
    else:
        reporter.fail(f"휴리스틱 추출 결과가 예상과 다름: {items}")


def check_map_item_to_row_11_columns(reporter: ValidationReporter) -> None:
    item = ALLSEARCH_FIXTURE["result"]["place"]["list"][0]
    row = _map_item_to_row(item, "2026-07-08")

    expected_columns = {
        "업체명", "업종", "새로오픈여부", "리뷰수", "주소", "대표전화",
        "플레이스 URL", "수집일", "홈페이지", "인스타", "블로그",
    }
    ok = (
        expected_columns.issubset(row.keys())
        and row["업체명"] == "카페 A"
        and row["업종"] == "카페"
        and row["대표전화"] == "02-1111-2222"
        and row["주소"] == "서울 강동구 성내로 1"
        and row["리뷰수"] == "10"
        and row["수집일"] == "2026-07-08"
        and row["플레이스 URL"] == "https://pcmap.place.naver.com/place/111111/home"
        and row["새로오픈여부"] == ""
        and row["인스타"] == ""
        and row["블로그"] == ""
        and row.get("place_id") == "111111"
    )
    if ok:
        reporter.pass_("item -> 11컬럼 row 매핑 성공(place_id는 내부 필드로 별도 포함)")
    else:
        reporter.fail(f"11컬럼 매핑 결과가 예상과 다름: {row}")


def check_map_item_to_row_second_field_variant(reporter: ValidationReporter) -> None:
    item = ALLSEARCH_FIXTURE["result"]["place"]["list"][1]
    row = _map_item_to_row(item, "2026-07-08")

    ok = (
        row["업체명"] == "카페 B"
        and row["업종"] == "커피전문점"
        and row["주소"] == "서울 강동구 성내로 2(지번)"
        and row["대표전화"] == "0507-1234-5678"
        and row["홈페이지"] == "https://cafeb.example.com"
        and row["리뷰수"] == "5"
    )
    if ok:
        reporter.pass_("2순위 키 후보(categoryName/address/virtualTel/reviewCount)도 정상 매핑")
    else:
        reporter.fail(f"2순위 키 후보 매핑 결과가 예상과 다름: {row}")


def check_map_item_to_row_missing_keys(reporter: ValidationReporter) -> None:
    sparse_item = {"id": "999999", "name": "정보 부족 카페"}
    row = _map_item_to_row(sparse_item, "2026-07-08")

    ok = (
        row["업체명"] == "정보 부족 카페"
        and row["업종"] == ""
        and row["주소"] == ""
        and row["대표전화"] == ""
        and row["리뷰수"] == ""
        and row["홈페이지"] == ""
        and row["플레이스 URL"] == "https://pcmap.place.naver.com/place/999999/home"
        and row.get("place_id") == "999999"
    )
    if ok:
        reporter.pass_("키가 대부분 누락된 item도 크래시 없이 빈칸으로 채워짐")
    else:
        reporter.fail(f"키 누락 처리 결과가 예상과 다름: {row}")

    empty_row = _map_item_to_row({}, "2026-07-08")
    if empty_row["업체명"] == "" and empty_row["플레이스 URL"] == "" and empty_row.get("place_id") == "":
        reporter.pass_("완전히 빈 item({})도 예외 없이 전부 빈칸 row 반환")
    else:
        reporter.fail(f"빈 item 처리 결과가 예상과 다름: {empty_row}")


def check_dedup_rows(reporter: ValidationReporter) -> None:
    rows = [
        {"place_id": "111111", "업체명": "카페 A"},
        {"place_id": "111111", "업체명": "카페 A(중복, 같은 id)"},  # 같은 place_id -> 제외
        {"place_id": "222222", "업체명": "카페 B"},
        {"place_id": "", "업체명": "카페 C"},
        {"place_id": "", "업체명": "카페 C"},  # place_id 없고 업체명도 중복 -> 제외
        {"place_id": "", "업체명": "카페 E"},  # place_id 없지만 새 업체명 -> 포함
    ]
    seen: set = set()
    unique_rows = dedup_rows(rows, seen)

    ok = (
        len(unique_rows) == 4
        and unique_rows[0]["place_id"] == "111111"
        and unique_rows[1]["place_id"] == "222222"
        and unique_rows[2]["업체명"] == "카페 C"
        and unique_rows[3]["업체명"] == "카페 E"
    )
    if ok:
        reporter.pass_("place_id 기준 중복 및 (place_id 없을 때) 업체명 기준 중복이 각각 제거됨")
    else:
        reporter.fail(f"dedup 결과가 예상과 다름: {unique_rows}")

    # seen을 재사용하는 두 번째 호출에서도 동일 place_id는 계속 제외되어야 함(누적 페이지 대응).
    more_rows = [{"place_id": "111111", "업체명": "카페 A"}, {"place_id": "333333", "업체명": "카페 F"}]
    more_unique = dedup_rows(more_rows, seen)
    if len(more_unique) == 1 and more_unique[0]["place_id"] == "333333":
        reporter.pass_("seen을 재사용한 후속 호출에서도 기존 place_id 중복이 계속 제외됨")
    else:
        reporter.fail(f"seen 재사용 dedup 결과가 예상과 다름: {more_unique}")


# ---------------------------------------------------------------------------
# PoC-1.1: 업종 list join / 외부 링크 도메인 분류 검증
# ---------------------------------------------------------------------------


def check_category_list_is_joined(reporter: ValidationReporter) -> None:
    item = {"id": "555555", "name": "카페 F", "category": ["카페,디저트", "베이커리"]}
    row = _map_item_to_row(item, "2026-07-08")
    if row["업종"] == "카페,디저트, 베이커리":
        reporter.pass_("category가 list이면 ', '로 join되어 사람이 읽기 좋은 문자열이 됨(repr 문자열 아님)")
    else:
        reporter.fail(f"category list join 결과가 예상과 다름: {row['업종']!r}")


def check_homepage_instagram_url_classified_as_insta(reporter: ValidationReporter) -> None:
    item = {"id": "666666", "name": "카페 G", "homePage": "https://www.instagram.com/cafe_g"}
    row = _map_item_to_row(item, "2026-07-08")
    if row["인스타"] == "https://www.instagram.com/cafe_g" and row["홈페이지"] == "" and row["블로그"] == "":
        reporter.pass_("homePage가 instagram URL이면 인스타 컬럼으로 분류됨")
    else:
        reporter.fail(f"인스타 분류 결과가 예상과 다름: 홈페이지={row['홈페이지']!r}, 인스타={row['인스타']!r}, 블로그={row['블로그']!r}")


def check_homepage_blog_url_classified_as_blog(reporter: ValidationReporter) -> None:
    item = {"id": "777777", "name": "카페 H", "homePage": "https://blog.naver.com/cafe_h"}
    row = _map_item_to_row(item, "2026-07-08")
    if row["블로그"] == "https://blog.naver.com/cafe_h" and row["홈페이지"] == "" and row["인스타"] == "":
        reporter.pass_("homePage가 blog.naver.com URL이면 블로그 컬럼으로 분류됨")
    else:
        reporter.fail(f"블로그 분류 결과가 예상과 다름: 홈페이지={row['홈페이지']!r}, 인스타={row['인스타']!r}, 블로그={row['블로그']!r}")


def check_homepage_generic_url_classified_as_homepage(reporter: ValidationReporter) -> None:
    item = {"id": "888888", "name": "카페 I", "homePage": "https://cafe-i.example.com"}
    row = _map_item_to_row(item, "2026-07-08")
    if row["홈페이지"] == "https://cafe-i.example.com" and row["인스타"] == "" and row["블로그"] == "":
        reporter.pass_("homePage가 일반 도메인이면 홈페이지 컬럼으로 분류됨")
    else:
        reporter.fail(f"일반 도메인 분류 결과가 예상과 다름: 홈페이지={row['홈페이지']!r}, 인스타={row['인스타']!r}, 블로그={row['블로그']!r}")


def check_homepage_url_list_classified_individually(reporter: ValidationReporter) -> None:
    item = {
        "id": "999000",
        "name": "카페 J",
        "homePage": [
            "https://cafe-j.example.com",
            "https://www.instagram.com/cafe_j",
            "https://blog.naver.com/cafe_j",
        ],
    }
    row = _map_item_to_row(item, "2026-07-08")
    ok = (
        row["홈페이지"] == "https://cafe-j.example.com"
        and row["인스타"] == "https://www.instagram.com/cafe_j"
        and row["블로그"] == "https://blog.naver.com/cafe_j"
    )
    if ok:
        reporter.pass_("homePage가 URL list면 각각 홈페이지/인스타/블로그로 분류됨")
    else:
        reporter.fail(f"URL list 분류 결과가 예상과 다름: {row}")


def check_is_candidate_response_filters_correctly(reporter: ValidationReporter) -> None:
    cases = {
        "allsearch xhr": (True, "https://map.naver.com/p/api/search/allSearch?query=x", "xhr"),
        "graphql fetch": (True, "https://map.naver.com/graphql", "fetch"),
        "pcmap xhr": (True, "https://pcmap.place.naver.com/restaurant/list", "xhr"),
        "document 타입 제외": (False, "https://map.naver.com/p/api/search/allSearch", "document"),
        "무관 URL 제외": (False, "https://map.naver.com/static/app.js", "xhr"),
        "빈 URL 제외": (False, "", "xhr"),
    }
    failed = []
    for label, (expected, url, resource_type) in cases.items():
        actual = is_candidate_response(url, resource_type)
        if actual != expected:
            failed.append((label, expected, actual))

    if not failed:
        reporter.pass_("is_candidate_response가 URL/resource_type 조합을 기대대로 판별")
    else:
        reporter.fail(f"is_candidate_response 판별 실패 케이스: {failed}")


def main() -> int:
    reporter = ValidationReporter()

    check_extract_known_path_allsearch(reporter)
    check_extract_heuristic_graphql(reporter)
    check_map_item_to_row_11_columns(reporter)
    check_map_item_to_row_second_field_variant(reporter)
    check_map_item_to_row_missing_keys(reporter)
    check_dedup_rows(reporter)
    check_category_list_is_joined(reporter)
    check_homepage_instagram_url_classified_as_insta(reporter)
    check_homepage_blog_url_classified_as_blog(reporter)
    check_homepage_generic_url_classified_as_homepage(reporter)
    check_homepage_url_list_classified_individually(reporter)
    check_is_candidate_response_filters_correctly(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
