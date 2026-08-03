from pathlib import Path
import sys


# ARCH-300 PoC-1: src/collection/place_mapper.py 검증용 standalone 스크립트(live 없음,
# 샘플 fixture dict 기반). 이 모듈은 UI/pipeline에 연결되지 않으므로, 순수 함수 단위로만
# 검증한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.exporter import MERGED_COLUMNS
from src.collection.place_mapper import (
    _classify_single_url,
    _extract_external_urls,
    _extract_list_items,
    _map_item_to_row,
    build_place_url_from_id,
    classify_captcha_signal,
    dedup_rows,
    format_common_address,
    is_candidate_response,
    should_stop_for_target,
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
                    "visitorReviewsTotal": 10,
                },
                {
                    "id": "222222",
                    "name": "카페 B",
                    "categoryName": "커피전문점",
                    "address": "서울 강동구 성내로 2(지번)",
                    "virtualTel": "0507-1234-5678",
                    "cafeBlogReviewsTotal": 5,
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


# PAGE-300-2B-2A 실측: page 2 후보 응답의 JSON top-level이 object가 아니라
# list(array)였다("[" 로 시작). 정확한 중첩 키 경로는 진단 보고서에 없으므로
# (요청서 §10: 미확인 key를 임의로 만들지 않는다) 완전히 placeholder인 키
# 이름만 사용해 "top-level list 재귀 순회" 일반 계약만 검증한다 - 실제 확인된
# GraphQL 스키마를 추정/재현하는 fixture가 아니다.
TOP_LEVEL_ARRAY_FIXTURE = [
    {
        "wrapper_unconfirmed": {
            "nested_unconfirmed": [
                {"id": "555555", "name": "카페 E", "category": "카페"},
                {"id": "666666", "name": "카페 F", "category": "카페"},
            ]
        }
    }
]

EMPTY_TOP_LEVEL_ARRAY_FIXTURE: list = []

UNRELATED_TOP_LEVEL_ARRAY_FIXTURE = [1, 2, 3, {"foo": "bar"}, "text"]


def check_extract_top_level_array_recurses_into_nested_list(reporter: ValidationReporter) -> None:
    """PAGE-300-2B-2B §10-1/2: JSON top-level이 list여도 내부에 중첩된
    업체 배열을 예외 없이 찾아내야 한다(placeholder 키 - 실제 스키마 아님)."""
    items = _extract_list_items(TOP_LEVEL_ARRAY_FIXTURE)
    ok = (
        len(items) == 2
        and items[0]["id"] == "555555"
        and items[1]["name"] == "카페 F"
    )
    if ok:
        reporter.pass_("top-level list(placeholder 중첩 구조)에서도 휴리스틱 재귀로 업체 리스트 2건 추출")
    else:
        reporter.fail(f"top-level list 추출 결과가 예상과 다름: {items}")


def check_extract_empty_top_level_array_is_safe(reporter: ValidationReporter) -> None:
    """PAGE-300-2B-2B §10-3: 빈 top-level list는 예외 없이 빈 목록을 반환해야
    한다."""
    items = _extract_list_items(EMPTY_TOP_LEVEL_ARRAY_FIXTURE)
    if items == []:
        reporter.pass_("빈 top-level list: 예외 없이 빈 목록 반환")
    else:
        reporter.fail(f"빈 top-level list 결과가 예상과 다름: {items}")


def check_extract_unrelated_top_level_array_not_mistaken(reporter: ValidationReporter) -> None:
    """PAGE-300-2B-2B §10-4: 업체 항목처럼 보이지 않는 list(정수/문자열/무관한
    dict 혼합)는 업체 목록으로 오인하지 않고 빈 목록을 반환해야 한다."""
    items = _extract_list_items(UNRELATED_TOP_LEVEL_ARRAY_FIXTURE)
    if items == []:
        reporter.pass_("업체 항목처럼 보이지 않는 top-level list는 오인하지 않고 빈 목록 반환")
    else:
        reporter.fail(f"무관한 top-level list 결과가 예상과 다름: {items}")


def check_map_item_to_row_11_columns(reporter: ValidationReporter) -> None:
    item = ALLSEARCH_FIXTURE["result"]["place"]["list"][0]
    row = _map_item_to_row(item, "2026-07-08")

    expected_columns = {
        "업체명", "업종", "새로오픈여부", "방문자리뷰수", "블로그리뷰수", "총리뷰수",
        "주소", "대표전화", "플레이스 URL", "수집일", "홈페이지", "인스타", "블로그",
    }
    ok = (
        expected_columns.issubset(row.keys())
        and row["업체명"] == "카페 A"
        and row["업종"] == "카페"
        and row["대표전화"] == "02-1111-2222"
        and row["주소"] == "서울특별시 강동구 성내로 1"
        and row["방문자리뷰수"] == 10
        and row["블로그리뷰수"] == ""
        and row["총리뷰수"] == ""
        and row["수집일"] == "2026-07-08"
        and row["플레이스 URL"] == "https://pcmap.place.naver.com/place/111111/home"
        and row["새로오픈여부"] == ""
        and row["인스타"] == ""
        and row["블로그"] == ""
        and row.get("place_id") == "111111"
    )
    if ok:
        reporter.pass_("item -> 13컬럼 row 매핑 성공(place_id는 내부 필드로 별도 포함)")
    else:
        reporter.fail(f"13컬럼 매핑 결과가 예상과 다름: {row}")


def check_map_item_to_row_second_field_variant(reporter: ValidationReporter) -> None:
    item = ALLSEARCH_FIXTURE["result"]["place"]["list"][1]
    row = _map_item_to_row(item, "2026-07-08")

    ok = (
        row["업체명"] == "카페 B"
        and row["업종"] == "커피전문점"
        and row["주소"] == "서울특별시 강동구 성내로 2(지번)"
        and row["대표전화"] == "0507-1234-5678"
        and row["홈페이지"] == "https://cafeb.example.com"
        and row["블로그리뷰수"] == 5
        and row["방문자리뷰수"] == ""
        and row["총리뷰수"] == ""
    )
    if ok:
        reporter.pass_("2순위 키 후보(categoryName/address/virtualTel/cafeBlogReviewsTotal)도 정상 매핑")
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
        and row["방문자리뷰수"] == ""
        and row["블로그리뷰수"] == ""
        and row["총리뷰수"] == ""
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


def check_visitor_blog_review_mapping_from_list_entity_keys(reporter: ValidationReporter) -> None:
    """2026-07-25 field parity 보정(A): 목록(PlaceListBusinessesItem) entity의
    실제 필드명 visitorReviewCount/blogCafeReviewCount(실측:
    scratchpad/page300_5m_r1_graphql_field_provenance_audit)가 정확히
    매핑되고 총리뷰수가 둘의 합으로 계산되는지 확인한다."""
    item = {"id": "1", "name": "테스트 카페", "visitorReviewCount": 241, "blogCafeReviewCount": 136}
    row = _map_item_to_row(item, "2026-07-25")
    if row["방문자리뷰수"] == 241 and row["블로그리뷰수"] == 136 and row["총리뷰수"] == 377:
        reporter.pass_("A. visitorReviewCount=241/blogCafeReviewCount=136 -> 방문자241/블로그136/총377 매핑 성공")
    else:
        reporter.fail(f"A. 목록 entity 리뷰 매핑 실패: {row}")


def check_review_both_missing_stays_blank(reporter: ValidationReporter) -> None:
    """B: 방문자/블로그 리뷰 원본이 모두 없으면 세 컬럼 전부 공란(0 강제 변환 금지)."""
    item = {"id": "2", "name": "리뷰 정보 없는 카페"}
    row = _map_item_to_row(item, "2026-07-25")
    if row["방문자리뷰수"] == "" and row["블로그리뷰수"] == "" and row["총리뷰수"] == "":
        reporter.pass_("B. 리뷰 원본 모두 누락 시 방문자/블로그/총리뷰수 전부 공란 유지 성공")
    else:
        reporter.fail(f"B. 리뷰 전체 누락 처리 실패: {row}")


def check_review_one_side_only_preserves_value_and_blank_total(reporter: ValidationReporter) -> None:
    """C: 한쪽 리뷰만 존재하면 그 값은 보존하고, 총리뷰수는 둘 다 확인돼야만
    합산한다는 정책에 따라 공란으로 유지된다(부분 합계를 총리뷰로 표시하지 않음)."""
    visitor_only = _map_item_to_row({"id": "3", "name": "방문자만", "visitorReviewCount": 88}, "2026-07-25")
    blog_only = _map_item_to_row({"id": "4", "name": "블로그만", "blogCafeReviewCount": 12}, "2026-07-25")
    ok = (
        visitor_only["방문자리뷰수"] == 88 and visitor_only["블로그리뷰수"] == "" and visitor_only["총리뷰수"] == ""
        and blog_only["블로그리뷰수"] == 12 and blog_only["방문자리뷰수"] == "" and blog_only["총리뷰수"] == ""
    )
    if ok:
        reporter.pass_("C. 한쪽 리뷰만 존재 시 그 값 보존 + 총리뷰수는 합산 정책에 따라 공란 유지 성공")
    else:
        reporter.fail(f"C. 한쪽 리뷰만 존재 처리 실패: visitor_only={visitor_only}, blog_only={blog_only}")


def check_total_review_count_field_not_reused_as_total(reporter: ValidationReporter) -> None:
    """D: totalReviewCount가 blogCafeReviewCount와 우연히 같은 값이어도
    무시하고, 총리뷰수는 항상 visitor+blog 산술 계산 결과여야 한다(totalReviewCount
    는 blogCafeReviewCount와 동일한 값으로 관찰된 오염된 필드 - 요청서 §3)."""
    item = {
        "id": "5", "name": "totalReviewCount 오염 카페",
        "visitorReviewCount": 200, "blogCafeReviewCount": 50,
        "totalReviewCount": 50,  # blogCafeReviewCount와 같은 값(실측 오염 패턴) - 무시돼야 함
    }
    row = _map_item_to_row(item, "2026-07-25")
    if row["총리뷰수"] == 250 and row["방문자리뷰수"] == 200 and row["블로그리뷰수"] == 50:
        reporter.pass_("D. totalReviewCount 값과 무관하게 총리뷰수 = 방문자+블로그(250)로 계산됨")
    else:
        reporter.fail(f"D. totalReviewCount 오용 방지 실패: {row}")


def check_format_common_address_basic_combination(reporter: ValidationReporter) -> None:
    """F: commonAddress(시·도/시·군·구/읍·면·동) + roadAddress(도로명+상세)
    기본 결합 - 요청서 §9 F 예시 그대로."""
    result = format_common_address("서울 강동구 천호동", "구천면로 140 2층 201호")
    if result == "서울특별시 강동구 천호동 구천면로 140 2층 201호":
        reporter.pass_("F. commonAddress+roadAddress 기본 결합 성공")
    else:
        reporter.fail(f"F. 기본 결합 실패: {result!r}")


def check_format_common_address_dedup_when_road_address_repeats_region(reporter: ValidationReporter) -> None:
    """F: roadAddress에 이미 "서울 강동구"(또는 정식 명칭 "서울특별시 강동구")가
    포함돼 있으면 중복 없이 한 번만 나와야 한다."""
    result_abbrev = format_common_address("서울 강동구 천호동", "서울 강동구 구천면로 140")
    result_canonical = format_common_address("서울 강동구 천호동", "서울특별시 강동구 구천면로 140")
    ok = (
        result_abbrev == "서울특별시 강동구 천호동 구천면로 140"
        and result_canonical == "서울특별시 강동구 천호동 구천면로 140"
    )
    if ok:
        reporter.pass_("F. roadAddress에 이미 포함된 시·도/시·군·구(축약·정식 표기 모두)는 중복 없이 제거됨")
    else:
        reporter.fail(f"F. 중복 제거 실패: abbrev={result_abbrev!r}, canonical={result_canonical!r}")


def check_format_common_address_preserves_already_canonical_name(reporter: ValidationReporter) -> None:
    """F: commonAddress가 이미 정식 명칭이면 그대로 유지된다(재변환/이중 변환 없음)."""
    result = format_common_address("서울특별시 강동구 천호동", "구천면로 140")
    if result == "서울특별시 강동구 천호동 구천면로 140":
        reporter.pass_("F. 이미 정식 명칭인 시·도는 그대로 유지됨")
    else:
        reporter.fail(f"F. 정식 명칭 보존 실패: {result!r}")


def check_format_common_address_nationwide_sido_table(reporter: ValidationReporter) -> None:
    """F: 요청서 §5가 예시로 든 전국 17개 시·도 축약명 전수 변환 확인."""
    expected_pairs = [
        ("서울", "서울특별시"), ("부산", "부산광역시"), ("대구", "대구광역시"),
        ("인천", "인천광역시"), ("광주", "광주광역시"), ("대전", "대전광역시"),
        ("울산", "울산광역시"), ("세종", "세종특별자치시"), ("경기", "경기도"),
        ("강원", "강원특별자치도"), ("충북", "충청북도"), ("충남", "충청남도"),
        ("전북", "전북특별자치도"), ("전남", "전라남도"), ("경북", "경상북도"),
        ("경남", "경상남도"), ("제주", "제주특별자치도"),
    ]
    failures = []
    for abbrev, canonical in expected_pairs:
        result = format_common_address(f"{abbrev} 임의구 임의동", "상세주소 1")
        if not result.startswith(canonical):
            failures.append((abbrev, canonical, result))
    if not failures:
        reporter.pass_("F. 전국 17개 시·도 축약명 전수 정식 명칭 변환 성공")
    else:
        reporter.fail(f"F. 시·도 변환 실패 항목: {failures}")


def check_format_common_address_preserves_building_floor_unit(reporter: ValidationReporter) -> None:
    """F: 건물명/층/호수/쉼표가 결합 과정에서 유실되지 않아야 한다."""
    result = format_common_address("서울 강동구 천호동", "구천면로 140 ABC빌딩, 2층 201호")
    if result == "서울특별시 강동구 천호동 구천면로 140 ABC빌딩, 2층 201호":
        reporter.pass_("F. 건물명/층/호수/쉼표 유실 없이 보존됨")
    else:
        reporter.fail(f"F. 건물명/층/호수 보존 실패: {result!r}")


def check_format_common_address_does_not_contaminate_across_different_dong(reporter: ValidationReporter) -> None:
    """F: 이 함수는 검색어(job/query)를 인자로 아예 받지 않으므로, 서로 다른
    업체의 실제 commonAddress를 넣으면 서로 다른 동 주소가 그대로 나와야
    한다(검색어 동을 모든 업체에 강제 주입하는 오염이 구조적으로 불가능함을
    증명)."""
    cheonho = format_common_address("서울 강동구 천호동", "구천면로 140")
    other_dong = format_common_address("서울 강동구 성내동", "성내로 5")
    if "천호동" in cheonho and "천호동" not in other_dong and "성내동" in other_dong:
        reporter.pass_("F. 서로 다른 업체의 실제 commonAddress가 각각 그대로 반영되고 다른 동으로 오염되지 않음")
    else:
        reporter.fail(f"F. 동 오염 방지 실패: cheonho={cheonho!r}, other_dong={other_dong!r}")


def check_format_common_address_fallback_without_common_address(reporter: ValidationReporter) -> None:
    """F: commonAddress가 없을 때 roadAddress/address만으로 안전하게 폴백한다
    (첫 토큰이 시·도로 보이면 정규화 시도, 나머지는 그대로)."""
    result = format_common_address("", "부산 해운대구 우동 마린시티로 1")
    if result == "부산광역시 해운대구 우동 마린시티로 1":
        reporter.pass_("F. commonAddress 없을 때 roadAddress 단독 폴백 성공(시·도 정규화 포함)")
    else:
        reporter.fail(f"F. commonAddress 없음 폴백 실패: {result!r}")


def check_format_common_address_all_blank_returns_empty(reporter: ValidationReporter) -> None:
    """F: commonAddress/roadAddress/address 전부 없으면 예외 없이 빈 문자열."""
    result = format_common_address("", "", "")
    result_none = format_common_address(None, None, None)
    if result == "" and result_none == "":
        reporter.pass_("F. 주소 정보 전체 없음 시 예외 없이 공란 반환")
    else:
        reporter.fail(f"F. 전체 없음 처리 실패: result={result!r}, result_none={result_none!r}")


def check_map_item_to_row_uses_common_address_formatter(reporter: ValidationReporter) -> None:
    """_map_item_to_row가 실제로 format_common_address를 거쳐 주소를 만드는지
    통합 확인(list entity 실측 형태: roadAddress는 지역 없이 도로명+상세만,
    commonAddress가 시·도/시·군·구/동을 담당 - 요청서 §0/§5 실측)."""
    item = {
        "id": "6", "name": "구천면로 카페",
        "commonAddress": "서울 강동구 천호동",
        "roadAddress": "구천면로 140 2층 201호",
    }
    row = _map_item_to_row(item, "2026-07-25")
    if row["주소"] == "서울특별시 강동구 천호동 구천면로 140 2층 201호":
        reporter.pass_("_map_item_to_row가 commonAddress+roadAddress를 format_common_address로 결합함")
    else:
        reporter.fail(f"_map_item_to_row 주소 결합 실패: {row['주소']!r}")


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


# ---------------------------------------------------------------------------
# PoC-2: page 간 병합 dedup / source_page 내부 메타 검증
# ---------------------------------------------------------------------------


def check_multi_page_merge_dedup_by_place_id(reporter: ValidationReporter) -> None:
    """page=1 rows + page=2 rows를 같은 seen으로 이어 붙일 때 place_id 기준으로
    중복이 제거되는지 확인한다(PoC-2: 페이지 전환 후 응답을 이어붙이는 시나리오
    모사, seen을 페이지 간 재사용하는 것이 실제 probe 스크립트의 방식과 동일)."""
    page1_items = [
        {"id": "111111", "name": "카페 A"},
        {"id": "222222", "name": "카페 B"},
    ]
    page2_items = [
        {"id": "111111", "name": "카페 A"},  # page=1과 동일 업체(중복) -> 제외되어야 함
        {"id": "333333", "name": "카페 C"},
    ]

    seen: set = set()
    page1_rows = dedup_rows(
        [_map_item_to_row(item, "2026-07-08", source_page=1) for item in page1_items], seen
    )
    page2_rows = dedup_rows(
        [_map_item_to_row(item, "2026-07-08", source_page=2) for item in page2_items], seen
    )
    merged = page1_rows + page2_rows

    place_ids = [row["place_id"] for row in merged]
    ok = len(merged) == 3 and len(place_ids) == len(set(place_ids)) and "111111" in place_ids and "333333" in place_ids
    if ok:
        reporter.pass_("page=1/page=2 응답을 같은 seen으로 이어붙이면 place_id 기준 중복(111111)이 제거됨")
    else:
        reporter.fail(f"page 간 병합 dedup 결과가 예상과 다름: place_ids={place_ids}")


def check_multi_page_merge_grows_when_no_duplicates(reporter: ValidationReporter) -> None:
    """page=2에 겹치는 place_id가 전혀 없으면, 병합 후 총 row 수가 page=1 + page=2
    개수만큼 그대로 증가하는지 확인한다(PoC-2의 핵심 가설: 새 place_id가 있으면
    총 확보량이 늘어나야 함)."""
    page1_items = [{"id": "111111", "name": "카페 A"}, {"id": "222222", "name": "카페 B"}]
    page2_items = [{"id": "444444", "name": "카페 D"}, {"id": "555555", "name": "카페 E"}, {"id": "666666", "name": "카페 F"}]

    seen: set = set()
    page1_rows = dedup_rows([_map_item_to_row(item, "2026-07-08") for item in page1_items], seen)
    page2_rows = dedup_rows([_map_item_to_row(item, "2026-07-08") for item in page2_items], seen)

    if len(page1_rows) == 2 and len(page2_rows) == 3 and len(page1_rows + page2_rows) == 5:
        reporter.pass_("중복 place_id가 없으면 병합 후 총 row 수가 page=1+page=2 개수만큼 증가함")
    else:
        reporter.fail(f"증가분 검증 결과가 예상과 다름: page1={len(page1_rows)}, page2={len(page2_rows)}")


def check_source_page_internal_meta_not_in_excel_columns(reporter: ValidationReporter) -> None:
    """source_page는 디버그용 내부 메타일 뿐, exporter의 실제 Excel 11컬럼
    (MERGED_COLUMNS)에는 절대 포함되지 않아야 한다(place_id와 동일한 관례)."""
    row = _map_item_to_row({"id": "777777", "name": "카페 G"}, "2026-07-08", source_page=2)

    ok = (
        row.get("source_page") == 2
        and "source_page" not in MERGED_COLUMNS
        and "place_id" not in MERGED_COLUMNS
    )
    if ok:
        reporter.pass_("source_page는 row에는 포함되지만 exporter.MERGED_COLUMNS(11컬럼)에는 없어 Excel 비노출")
    else:
        reporter.fail(f"source_page 내부 메타 처리 결과가 예상과 다름: row={row}, MERGED_COLUMNS={MERGED_COLUMNS}")

    # source_page를 전달하지 않으면(PoC-1 기존 호출 방식) row에 아예 키가 생기지 않아야 함(하위 호환).
    row_without_source_page = _map_item_to_row({"id": "888888", "name": "카페 H"}, "2026-07-08")
    if "source_page" not in row_without_source_page:
        reporter.pass_("source_page 미전달 시 row에 해당 키 자체가 생기지 않음(기존 PoC-1 호출 하위 호환)")
    else:
        reporter.fail(f"source_page 미전달인데 키가 생김: {row_without_source_page}")


# ---------------------------------------------------------------------------
# PoC-2R: CAPTCHA 감지 오탐 보정(classify_captcha_signal) 검증
# ---------------------------------------------------------------------------


def check_captcha_signal_passive_marker_does_not_halt(reporter: ValidationReporter) -> None:
    """DOM에 마커는 있지만 실제로 보이지 않는 경우(2026-07-01/07-08 관찰과 동일한
    상시 존재 placeholder 패턴) - 중단 근거(active/click_intercepted)가 되면 안 된다."""
    signal = classify_captcha_signal(marker_present_in_dom=True, element_visible=False)
    should_halt = signal["active_captcha_detected"] or signal["click_intercepted_by_captcha"]
    ok = signal["passive_captcha_marker_found"] is True and should_halt is False
    if ok:
        reporter.pass_("passive marker만 있으면 active/click_intercepted가 전부 False라 중단 근거가 되지 않음")
    else:
        reporter.fail(f"passive-only 신호 처리 결과가 예상과 다름: {signal}")


def check_captcha_signal_visible_indicator_is_active(reporter: ValidationReporter) -> None:
    """마커가 실제로 화면에 보이고 유의미한 크기를 가지면 active로 분류되어 중단 근거가 된다."""
    signal = classify_captcha_signal(marker_present_in_dom=True, element_visible=True, bounding_box_area=1234.0)
    should_halt = signal["active_captcha_detected"] or signal["click_intercepted_by_captcha"]
    if signal["active_captcha_detected"] is True and should_halt is True:
        reporter.pass_("가시성+유의미한 크기가 확인되면 active_captcha_detected=True로 중단 신호가 됨")
    else:
        reporter.fail(f"visible indicator 처리 결과가 예상과 다름: {signal}")

    zero_area_signal = classify_captcha_signal(marker_present_in_dom=True, element_visible=True, bounding_box_area=0.0)
    if zero_area_signal["active_captcha_detected"] is False:
        reporter.pass_("가시성은 True여도 bounding_box_area=0이면 active로 판정하지 않음(방어적)")
    else:
        reporter.fail(f"bounding_box_area=0 처리 결과가 예상과 다름: {zero_area_signal}")


def check_captcha_signal_click_exception_is_strong_signal(reporter: ValidationReporter) -> None:
    """클릭 예외 메시지에 wtm-captcha-root 등 CAPTCHA 키워드가 있으면
    click_intercepted_by_captcha=True로 강한 신호로 분류되어 중단 근거가 된다."""
    message = (
        'Timeout 3000ms exceeded. <div id="wtm-captcha-root">...</div> '
        "subtree intercepts pointer events"
    )
    signal = classify_captcha_signal(click_exception_message=message)
    should_halt = signal["active_captcha_detected"] or signal["click_intercepted_by_captcha"]
    if signal["click_intercepted_by_captcha"] is True and should_halt is True:
        reporter.pass_("클릭 예외 메시지의 wtm-captcha-root가 click_intercepted_by_captcha로 분류되어 중단 신호가 됨")
    else:
        reporter.fail(f"클릭 예외 분류 결과가 예상과 다름: {signal}")

    unrelated_signal = classify_captcha_signal(click_exception_message="TimeoutError: element not found")
    if unrelated_signal["click_intercepted_by_captcha"] is False:
        reporter.pass_("CAPTCHA와 무관한 클릭 예외는 click_intercepted_by_captcha=False로 유지됨")
    else:
        reporter.fail(f"무관 예외 처리 결과가 예상과 다름: {unrelated_signal}")


# ---------------------------------------------------------------------------
# PoC-3: page=1/2/3 3페이지 병합 집계 검증
# ---------------------------------------------------------------------------


def check_total_dedup_after_three_page_merge(reporter: ValidationReporter) -> None:
    """page=1/2/3 응답 중 일부가 겹치더라도(같은 place_id 재등장) 3페이지 병합 후
    총 dedup row 수가 정확한지 확인한다(PoC-3: 중복 있는 실전 시나리오 모사)."""
    seen: set = set()
    page1_items = [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]
    page2_items = [{"id": "2", "name": "B"}, {"id": "3", "name": "C"}, {"id": "4", "name": "D"}]  # id=2 중복
    page3_items = [{"id": "4", "name": "D"}, {"id": "5", "name": "E"}]  # id=4 중복

    page1_rows = dedup_rows([_map_item_to_row(i, "2026-07-09", source_page=1) for i in page1_items], seen)
    page2_rows = dedup_rows([_map_item_to_row(i, "2026-07-09", source_page=2) for i in page2_items], seen)
    page3_rows = dedup_rows([_map_item_to_row(i, "2026-07-09", source_page=3) for i in page3_items], seen)
    merged = page1_rows + page2_rows + page3_rows

    place_ids = [row["place_id"] for row in merged]
    ok = len(merged) == 5 and len(place_ids) == len(set(place_ids)) and set(place_ids) == {"1", "2", "3", "4", "5"}
    if ok:
        reporter.pass_("page=1/2/3에 중복 place_id가 섞여도 3페이지 병합 후 총 5건(중복 2건 제거)으로 정확히 집계됨")
    else:
        reporter.fail(f"3페이지 병합 dedup 결과가 예상과 다름: place_ids={place_ids}")


# ---------------------------------------------------------------------------
# PoC-4: source_dong/source_query 내부 메타 + count_rows_by_field 검증
# ---------------------------------------------------------------------------


def check_source_dong_and_query_internal_meta_not_in_excel_columns(reporter: ValidationReporter) -> None:
    """source_dong/source_query는 place_id/source_page와 마찬가지로 디버그용
    내부 메타일 뿐, exporter.MERGED_COLUMNS(11컬럼)에는 절대 노출되지 않아야 한다."""
    row = _map_item_to_row(
        {"id": "123", "name": "동단위카페"},
        "2026-07-09",
        source_dong="천호동",
        source_query="서울특별시 강동구 천호동 카페",
    )
    ok = (
        row.get("source_dong") == "천호동"
        and row.get("source_query") == "서울특별시 강동구 천호동 카페"
        and "source_dong" not in MERGED_COLUMNS
        and "source_query" not in MERGED_COLUMNS
    )
    if ok:
        reporter.pass_("source_dong/source_query는 row에 포함되지만 MERGED_COLUMNS(11컬럼)에는 없어 Excel 비노출")
    else:
        reporter.fail(f"source_dong/source_query 내부 메타 처리 결과가 예상과 다름: row={row}")

    row_without_meta = _map_item_to_row({"id": "456", "name": "레거시카페"}, "2026-07-09")
    if "source_dong" not in row_without_meta and "source_query" not in row_without_meta:
        reporter.pass_("source_dong/source_query 미전달 시 row에 해당 키가 생기지 않음(기존 호출 하위 호환)")
    else:
        reporter.fail(f"source_dong/source_query 미전달인데 키가 생김: {row_without_meta}")


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


# ---------------------------------------------------------------------------
# should_stop_for_target 검증
# ---------------------------------------------------------------------------


def check_should_stop_for_target_reaches_and_below(reporter: ValidationReporter) -> None:
    """current_count가 target에 도달/초과하면 True, 미달이면 False."""
    ok = (
        should_stop_for_target(300, 300) is True
        and should_stop_for_target(301, 300) is True
        and should_stop_for_target(299, 300) is False
    )
    if ok:
        reporter.pass_("should_stop_for_target이 target 도달/초과/미달을 정확히 판단함")
    else:
        reporter.fail("should_stop_for_target 도달 판정 결과가 예상과 다름")


def check_should_stop_for_target_non_positive_target_is_false(reporter: ValidationReporter) -> None:
    """target이 0 이하이면 current_count와 무관하게 항상 False(방어적 처리)."""
    if should_stop_for_target(100, 0) is False and should_stop_for_target(100, -1) is False:
        reporter.pass_("target<=0이면 should_stop_for_target이 항상 False를 반환함")
    else:
        reporter.fail("target<=0 처리 결과가 예상과 다름")


# ---------------------------------------------------------------------------
# PAGE300-6E-V3: 대표 3링크 + 추가 링크 보존, hostname 교정, dedup, 제외 URL,
# 주소 행정동 중복 제거 검증
# ---------------------------------------------------------------------------


def check_butteron_instagram_type_mismatch_fixture(reporter: ValidationReporter) -> None:
    """실제 결함(A): type="홈페이지"인데 hostname이 instagram.com이면 hostname이
    우선해 인스타로 분류되어야 하고, igshid 추적 파라미터는 제거되어야 한다."""
    item = {
        "id": "5001",
        "name": "버터온",
        "homepages": {
            "repr": {"url": "https://instagram.com/butteron_?igshid=abc123", "type": "홈페이지"},
            "etc": [],
        },
    }
    row = _map_item_to_row(item, "2026-07-27")
    ok = (
        row["홈페이지"] == ""
        and row["인스타"] == "https://instagram.com/butteron_"
        and row["블로그"] == ""
        and row["추가 링크"] == ""
    )
    if ok:
        reporter.pass_("버터온 fixture: type=홈페이지+instagram.com hostname이 인스타로 정확히 교정되고 igshid 제거됨")
    else:
        reporter.fail(f"버터온 fixture 결과가 예상과 다름: 홈페이지={row['홈페이지']!r}, 인스타={row['인스타']!r}, 추가 링크={row['추가 링크']!r}")


def check_kakao_channel_hostname_corrected_and_sent_to_extra_links(reporter: ValidationReporter) -> None:
    """type="홈페이지"인데 hostname이 pf.kakao.com이면 카카오채널로 분류되고,
    카카오채널은 대표 홈페이지로 승격되지 않고 추가 링크에만 저장된다."""
    item = {"id": "5002", "name": "카카오채널 업체", "homepages": {"repr": {"url": "https://pf.kakao.com/_example", "type": "홈페이지"}, "etc": []}}
    row = _map_item_to_row(item, "2026-07-27")
    ok = (
        row["홈페이지"] == ""
        and row["추가 링크"] == "[카카오채널] https://pf.kakao.com/_example"
    )
    if ok:
        reporter.pass_("type=홈페이지+pf.kakao.com hostname이 카카오채널로 교정되고 홈페이지 열로 승격되지 않음")
    else:
        reporter.fail(f"카카오채널 교정 결과가 예상과 다름: 홈페이지={row['홈페이지']!r}, 추가 링크={row['추가 링크']!r}")


def check_smartstore_classified_and_preserved_in_extra_links(reporter: ValidationReporter) -> None:
    """스마트스토어는 완전히 제외하지 않고 공개 판매 채널로 분류해 추가 링크에 보존한다."""
    _, _, _, extra = _extract_external_urls({"homepages": {"repr": {"url": "https://smartstore.naver.com/example"}, "etc": []}})
    if extra == "[스마트스토어] https://smartstore.naver.com/example":
        reporter.pass_("스마트스토어 URL이 제외되지 않고 [스마트스토어] 라벨로 추가 링크에 보존됨")
    else:
        reporter.fail(f"스마트스토어 분류 결과가 예상과 다름: {extra!r}")


def check_multi_url_five_candidates_no_loss(reporter: ValidationReporter) -> None:
    """B(구조): repr 1개 + etc 4개(총 5개 외부 URL)를 끝까지 순회해 누락 0건,
    대표 홈페이지/인스타/블로그 각 1개, 나머지 2개가 추가 링크에 줄바꿈으로 저장됨."""
    item = {
        "id": "5003",
        "name": "다중 링크 업체",
        "homepages": {
            "repr": {"url": "https://cafe-k.example.com", "type": "홈페이지"},
            "etc": [
                {"url": "https://www.instagram.com/cafe_k", "type": "인스타그램"},
                {"url": "https://blog.naver.com/cafe_k", "type": "블로그"},
                {"url": "https://pf.kakao.com/_cafek", "type": "홈페이지"},
                {"url": "https://youtube.com/@cafe_k", "type": "홈페이지"},
            ],
        },
    }
    row = _map_item_to_row(item, "2026-07-27")
    extra_lines = row["추가 링크"].split("\n") if row["추가 링크"] else []
    ok = (
        row["홈페이지"] == "https://cafe-k.example.com"
        and row["인스타"] == "https://www.instagram.com/cafe_k"
        and row["블로그"] == "https://blog.naver.com/cafe_k"
        and len(extra_lines) == 2
        and "[카카오채널] https://pf.kakao.com/_cafek" in extra_lines
        and "[유튜브] https://youtube.com/@cafe_k" in extra_lines
    )
    if ok:
        reporter.pass_("repr 1개 + etc 4개(외부 URL 5개) 전체 순회 성공 - 누락 0건, 대표 3개 + 추가 링크 2개")
    else:
        reporter.fail(f"다중 URL 5개 fixture 결과가 예상과 다름: {row}")


def check_representative_vs_extra_split_with_duplicated_categories(reporter: ValidationReporter) -> None:
    """C: 홈페이지 2개 + 인스타 2개 + 블로그 2개 + 카카오채널 1개(총 7개) 입력 시
    대표는 각 카테고리 첫 번째만, 나머지 4개는 추가 링크로 분리된다."""
    item = {
        "id": "5004",
        "name": "대표추가분리 업체",
        "homepages": {
            "repr": None,
            "etc": [
                {"url": "https://home1.example.com", "type": "홈페이지"},
                {"url": "https://home2.example.com", "type": "홈페이지"},
                {"url": "https://instagram.com/insta1", "type": "인스타그램"},
                {"url": "https://instagram.com/insta2", "type": "인스타그램"},
                {"url": "https://blog.naver.com/blog1", "type": "블로그"},
                {"url": "https://blog.naver.com/blog2", "type": "블로그"},
                {"url": "https://pf.kakao.com/_channel", "type": "홈페이지"},
            ],
        },
    }
    row = _map_item_to_row(item, "2026-07-27")
    extra_lines = row["추가 링크"].split("\n") if row["추가 링크"] else []
    ok = (
        row["홈페이지"] == "https://home1.example.com"
        and row["인스타"] == "https://instagram.com/insta1"
        and row["블로그"] == "https://blog.naver.com/blog1"
        and len(extra_lines) == 4
        and "[홈페이지] https://home2.example.com" in extra_lines
        and "[인스타] https://instagram.com/insta2" in extra_lines
        and "[블로그] https://blog.naver.com/blog2" in extra_lines
        and "[카카오채널] https://pf.kakao.com/_channel" in extra_lines
    )
    if ok:
        reporter.pass_("홈페이지/인스타/블로그 각 2개+카카오채널 1개 -> 대표 3개 + 추가 링크 4개로 정확히 분리")
    else:
        reporter.fail(f"대표/추가 분리 결과가 예상과 다름: {row}")


def check_dedup_www_and_tracking_params_and_fragment(reporter: ValidationReporter) -> None:
    """D: repr/etc 동일 URL, www 유무, 추적 파라미터(utm/fbclid) 차이, fragment
    차이는 모두 같은 URL로 취급해 중복 제거되고, 서로 다른 path는 보존된다."""
    item = {
        "id": "5005",
        "name": "중복 제거 업체",
        "homepages": {
            "repr": {"url": "https://example.com/shop?utm_source=naver#section1", "type": "홈페이지"},
            "etc": [
                {"url": "https://www.example.com/shop?fbclid=xyz", "type": "홈페이지"},  # www + tracking = 동일 URL(중복)
                {"url": "https://example.com/shop", "type": "홈페이지"},  # fragment만 다름 = 동일 URL(중복)
                {"url": "https://example.com", "type": "홈페이지"},  # 다른 path = 보존
            ],
        },
    }
    row = _map_item_to_row(item, "2026-07-27")
    ok = (
        row["홈페이지"] == "https://example.com/shop"
        and row["추가 링크"] == "[홈페이지] https://example.com"
    )
    if ok:
        reporter.pass_("www/추적 파라미터/fragment 차이는 중복 제거되고, 서로 다른 path(example.com vs /shop)는 보존됨")
    else:
        reporter.fail(f"dedup 결과가 예상과 다름: 홈페이지={row['홈페이지']!r}, 추가 링크={row['추가 링크']!r}")


def check_multiple_responses_repeated_merge_no_extra_growth(reporter: ValidationReporter) -> None:
    """동일 item을 여러 번(반복 response) _map_item_to_row로 다시 매핑해도
    개별 매핑 결과 자체는 항상 동일하다(idempotent 매핑 - accumulator 수준의
    누적 idempotent 검증은 이 파일에서 다루지 않는다)."""
    item = {
        "id": "5006",
        "name": "반복 매핑 업체",
        "homepages": {"repr": {"url": "https://example2.com", "type": "홈페이지"}, "etc": [{"url": "https://youtube.com/@x", "type": "홈페이지"}]},
    }
    row_a = _map_item_to_row(item, "2026-07-27")
    row_b = _map_item_to_row(item, "2026-07-27")
    if row_a["홈페이지"] == row_b["홈페이지"] and row_a["추가 링크"] == row_b["추가 링크"] == "[유튜브] https://youtube.com/@x":
        reporter.pass_("동일 item 반복 매핑 결과가 idempotent함(추가 링크 중복 누적 없음)")
    else:
        reporter.fail(f"반복 매핑 idempotent 검증 실패: a={row_a}, b={row_b}")


def check_excluded_urls_never_become_channels(reporter: ValidationReporter) -> None:
    """E: 네이버 내부/지도/route/예약/주문/talktalk/이미지/잘못된 scheme URL은
    대표 링크는 물론 추가 링크에도 전혀 나타나지 않는다."""
    excluded_urls = [
        "https://pcmap.place.naver.com/place/12345/home",
        "https://m.place.naver.com/place/12345/home",
        "https://place.naver.com/place/12345",
        "https://map.naver.com/p/directions/1/2",
        "https://booking.naver.com/booking/13/bizes/999",
        "https://order.naver.com/orders/1",
        "https://talk.naver.com/ct/w4example",
        "https://adcr.naver.com/adcr?x=1",
        "https://cafe.example.com/photo.jpg",
        "javascript:void(0)",
    ]
    item = {
        "id": "5007",
        "name": "제외 URL 업체",
        "homepages": {"repr": None, "etc": [{"url": u, "type": None} for u in excluded_urls]},
    }
    row = _map_item_to_row(item, "2026-07-27")
    ok = row["홈페이지"] == "" and row["인스타"] == "" and row["블로그"] == "" and row["추가 링크"] == ""
    if ok:
        reporter.pass_("플레이스/지도/route/예약/주문/talktalk/광고/이미지/잘못된 scheme URL은 대표·추가 링크 어디에도 나타나지 않음")
    else:
        reporter.fail(f"제외 URL 처리 결과가 예상과 다름: {row}")


def check_classify_single_url_hostname_overrides_unknown_type_label(reporter: ValidationReporter) -> None:
    """hostname이 알려진 채널과 일치하지 않고 type_label도 매핑되지 않는
    미확인 값이면 "etc"(기타)로 분류된다."""
    category, normalized = _classify_single_url("https://unknown-channel.example.com/x", "트위터")
    if category == "etc" and normalized == "https://unknown-channel.example.com/x":
        reporter.pass_("hostname 미확인 + 알 수 없는 type_label -> 기타(etc)로 분류됨")
    else:
        reporter.fail(f"기타 분류 결과가 예상과 다름: category={category!r}, normalized={normalized!r}")


def check_malformed_bracket_prefixed_url_does_not_raise(reporter: ValidationReporter) -> None:
    """HOME-VE-1: place_id=1398764421(톨브 링크플레이스 신세계백화점
    타임스퀘어점) 홈페이지 보강에서 실제로 발생한 ValueError("Invalid IPv6
    URL") 재현 - `[라벨]도메인` 형태(공백 없이 대괄호로 시작하는 라벨이
    붙은 URL, 백화점 입점 업체 표기에서 흔함)로 scheme 보정("https://" 접두)이
    이뤄지면 urlsplit()이 netloc을 IPv6 리터럴로 오인해 예외를 던진다.
    `_normalize_external_url`의 기존 계약("유효하지 않으면 빈 문자열 반환,
    예외 없음")대로 처리되어야 하며, 다른 정상 URL은 그대로 보존돼야 한다."""
    item = {
        "id": "1398764421",
        "name": "톨브 링크플레이스 신세계백화점 타임스퀘어점",
        "homepages": {
            "repr": {"url": "[신세계타임스퀘어]blog.naver.com/example", "type": "홈페이지"},
            "etc": [{"url": "https://instagram.com/example_valid", "type": "인스타그램"}],
        },
    }
    try:
        row = _map_item_to_row(item, "2026-08-03")
    except ValueError as exc:
        reporter.fail(f"HOME-VE-1. 대괄호 라벨 URL이 여전히 ValueError를 던짐(미수정): {exc}")
        return
    ok = row["홈페이지"] == "" and row["인스타"] == "https://instagram.com/example_valid"
    if ok:
        reporter.pass_("HOME-VE-1. 대괄호 라벨 URL은 예외 없이 제외되고, 다른 정상 URL(인스타)은 보존됨")
    else:
        reporter.fail(f"HOME-VE-1. 대괄호 라벨 URL 처리 결과가 예상과 다름: {row}")


def check_format_common_address_removes_duplicate_dong_paren_suffix(reporter: ValidationReporter) -> None:
    """§14 실제 3건: commonAddress와 동일한 행정동이 detail 끝에 괄호로
    중복되면 제거하고, 건물명이 함께 있으면 건물명만 보존한다."""
    r1 = format_common_address("서울 강동구 천호동", "올림픽로 651 (천호동)")
    r2 = format_common_address("서울 강동구 천호동", "천호대로 1015-14 (천호동) 이마트별관")
    r3 = format_common_address("서울 강동구 천호동", "천호대로 1089 (천호동, 강동 헤르셔)")
    ok = (
        r1 == "서울특별시 강동구 천호동 올림픽로 651"
        and r2 == "서울특별시 강동구 천호동 천호대로 1015-14 이마트별관"
        and r3 == "서울특별시 강동구 천호동 천호대로 1089 (강동 헤르셔)"
    )
    if ok:
        reporter.pass_("실제 3건 주소 모두 중복 행정동 괄호 제거/건물명 보존이 정확히 동작함")
    else:
        reporter.fail(f"주소 행정동 중복 제거 결과가 예상과 다름: r1={r1!r}, r2={r2!r}, r3={r3!r}")


def check_format_common_address_preserves_building_style_dong_tokens(reporter: ValidationReporter) -> None:
    """"102동"/"판매시설동"/"상가동"처럼 건물 의미의 동은 행정동과 달라
    괄호 dedup 대상이 아니므로 그대로 보존된다."""
    r1 = format_common_address("서울 강동구 천호동", "천호대로 1000 102동 301호")
    r2 = format_common_address("서울 강동구 천호동", "천호대로 1000 (판매시설동)")
    r3 = format_common_address("서울 강동구 천호동", "천호대로 1000 (상가동, 헤르셔)")
    ok = (
        "102동" in r1
        and "(판매시설동)" in r2
        and "(상가동, 헤르셔)" in r3
    )
    if ok:
        reporter.pass_("102동/판매시설동/상가동처럼 건물 의미 동 토큰은 중복 제거 대상에서 제외되고 보존됨")
    else:
        reporter.fail(f"건물 의미 동 보존 결과가 예상과 다름: r1={r1!r}, r2={r2!r}, r3={r3!r}")


def check_build_place_url_from_id_valid(reporter: ValidationReporter) -> None:
    url = build_place_url_from_id("2014880028")
    if url == "https://pcmap.place.naver.com/place/2014880028/home":
        reporter.pass_("build_place_url_from_id: 유효한 숫자 ID로 범용 place URL 생성")
    else:
        reporter.fail(f"build_place_url_from_id 결과 이상: {url}")


def check_build_place_url_from_id_rejects_malformed(reporter: ValidationReporter) -> None:
    empty = build_place_url_from_id("")
    non_numeric = build_place_url_from_id("abc123")
    none_value = build_place_url_from_id(None)
    if empty == "" and non_numeric == "" and none_value == "":
        reporter.pass_("build_place_url_from_id: 빈 값/비숫자 ID는 URL을 만들지 않고 거부")
    else:
        reporter.fail(f"malformed ID 처리 이상: empty={empty!r} non_numeric={non_numeric!r} none={none_value!r}")


def main() -> int:
    reporter = ValidationReporter()

    check_extract_known_path_allsearch(reporter)
    check_extract_heuristic_graphql(reporter)
    check_extract_top_level_array_recurses_into_nested_list(reporter)
    check_extract_empty_top_level_array_is_safe(reporter)
    check_extract_unrelated_top_level_array_not_mistaken(reporter)
    check_map_item_to_row_11_columns(reporter)
    check_map_item_to_row_second_field_variant(reporter)
    check_map_item_to_row_missing_keys(reporter)
    check_visitor_blog_review_mapping_from_list_entity_keys(reporter)
    check_review_both_missing_stays_blank(reporter)
    check_review_one_side_only_preserves_value_and_blank_total(reporter)
    check_total_review_count_field_not_reused_as_total(reporter)
    check_format_common_address_basic_combination(reporter)
    check_format_common_address_dedup_when_road_address_repeats_region(reporter)
    check_format_common_address_preserves_already_canonical_name(reporter)
    check_format_common_address_nationwide_sido_table(reporter)
    check_format_common_address_preserves_building_floor_unit(reporter)
    check_format_common_address_does_not_contaminate_across_different_dong(reporter)
    check_format_common_address_fallback_without_common_address(reporter)
    check_format_common_address_all_blank_returns_empty(reporter)
    check_map_item_to_row_uses_common_address_formatter(reporter)
    check_dedup_rows(reporter)
    check_category_list_is_joined(reporter)
    check_homepage_instagram_url_classified_as_insta(reporter)
    check_homepage_blog_url_classified_as_blog(reporter)
    check_homepage_generic_url_classified_as_homepage(reporter)
    check_homepage_url_list_classified_individually(reporter)
    check_multi_page_merge_dedup_by_place_id(reporter)
    check_multi_page_merge_grows_when_no_duplicates(reporter)
    check_source_page_internal_meta_not_in_excel_columns(reporter)
    check_captcha_signal_passive_marker_does_not_halt(reporter)
    check_captcha_signal_visible_indicator_is_active(reporter)
    check_captcha_signal_click_exception_is_strong_signal(reporter)
    check_total_dedup_after_three_page_merge(reporter)
    check_source_dong_and_query_internal_meta_not_in_excel_columns(reporter)
    check_is_candidate_response_filters_correctly(reporter)
    check_should_stop_for_target_reaches_and_below(reporter)
    check_should_stop_for_target_non_positive_target_is_false(reporter)
    check_butteron_instagram_type_mismatch_fixture(reporter)
    check_kakao_channel_hostname_corrected_and_sent_to_extra_links(reporter)
    check_smartstore_classified_and_preserved_in_extra_links(reporter)
    check_multi_url_five_candidates_no_loss(reporter)
    check_representative_vs_extra_split_with_duplicated_categories(reporter)
    check_dedup_www_and_tracking_params_and_fragment(reporter)
    check_multiple_responses_repeated_merge_no_extra_growth(reporter)
    check_excluded_urls_never_become_channels(reporter)
    check_classify_single_url_hostname_overrides_unknown_type_label(reporter)
    check_malformed_bracket_prefixed_url_does_not_raise(reporter)
    check_format_common_address_removes_duplicate_dong_paren_suffix(reporter)
    check_format_common_address_preserves_building_style_dong_tokens(reporter)
    check_build_place_url_from_id_valid(reporter)
    check_build_place_url_from_id_rejects_malformed(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
