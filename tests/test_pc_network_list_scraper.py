from pathlib import Path
import sys


# ARCH-300 PoC-1: src/pc/network_list_scraper.py 검증용 standalone 스크립트(live 없음,
# 샘플 fixture dict 기반). 이 모듈은 UI/pipeline에 연결되지 않으므로, 순수 함수 단위로만
# 검증한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.exporter import MERGED_COLUMNS
from src.pc.network_list_scraper import (
    _extract_list_items,
    _map_item_to_row,
    build_candidate_record,
    classify_captcha_signal,
    classify_query_efficiency,
    count_rows_by_field,
    count_rows_by_source_page,
    dedup_rows,
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


def check_build_candidate_record_shape(reporter: ValidationReporter) -> None:
    record = build_candidate_record(
        "https://map.naver.com/p/api/search/allSearch?query=x",
        200,
        "xhr",
        top_level_keys=["result"],
    )
    ok = (
        record["url"] == "https://map.naver.com/p/api/search/allSearch?query=x"
        and record["status"] == 200
        and record["resource_type"] == "xhr"
        and record["top_level_keys"] == ["result"]
        and record["parse_error"] is None
    )
    if ok:
        reporter.pass_("build_candidate_record가 후보 응답 메타를 예상 형태로 조립")
    else:
        reporter.fail(f"build_candidate_record 결과가 예상과 다름: {record}")

    error_record = build_candidate_record("https://x", 500, "fetch", parse_error="ValueError: bad json")
    if error_record["top_level_keys"] == [] and error_record["parse_error"] == "ValueError: bad json":
        reporter.pass_("build_candidate_record가 파싱 실패(parse_error)도 예외 없이 기록")
    else:
        reporter.fail(f"build_candidate_record 실패 케이스 결과가 예상과 다름: {error_record}")


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


def check_count_rows_by_source_page_three_pages(reporter: ValidationReporter) -> None:
    """page=1/2/3에서 온 row를 병합했을 때 source_page별 건수가 정확히 집계되는지 확인한다."""
    seen: set = set()
    page1_rows = dedup_rows(
        [_map_item_to_row({"id": str(i), "name": f"카페{i}"}, "2026-07-09", source_page=1) for i in range(1, 21)],
        seen,
    )
    page2_rows = dedup_rows(
        [_map_item_to_row({"id": str(i), "name": f"카페{i}"}, "2026-07-09", source_page=2) for i in range(21, 91)],
        seen,
    )
    page3_rows = dedup_rows(
        [_map_item_to_row({"id": str(i), "name": f"카페{i}"}, "2026-07-09", source_page=3) for i in range(91, 141)],
        seen,
    )
    merged = page1_rows + page2_rows + page3_rows
    counts = count_rows_by_source_page(merged)

    ok = counts == {1: 20, 2: 70, 3: 50}
    if ok:
        reporter.pass_("page=1/2/3 병합 후 source_page별 건수가 각각 20/70/50건으로 정확히 집계됨")
    else:
        reporter.fail(f"source_page별 집계 결과가 예상과 다름: {counts}")

    # source_page를 채우지 않은 행(예: PoC-1 스타일 호출)은 "unknown"으로 묶여야 한다.
    legacy_row = _map_item_to_row({"id": "9999", "name": "레거시카페"}, "2026-07-09")
    counts_with_unknown = count_rows_by_source_page(merged + [legacy_row])
    if counts_with_unknown.get("unknown") == 1 and counts_with_unknown.get(1) == 20:
        reporter.pass_("source_page 미지정(레거시) 행은 'unknown'으로 별도 집계됨")
    else:
        reporter.fail(f"unknown 집계 결과가 예상과 다름: {counts_with_unknown}")


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


def check_count_rows_by_field_generic_aggregation(reporter: ValidationReporter) -> None:
    """count_rows_by_field가 source_page뿐 아니라 임의 필드(source_dong)로도
    동일하게 집계할 수 있는지 확인한다(count_rows_by_source_page의 일반화 검증)."""
    rows = [
        _map_item_to_row({"id": "1", "name": "A"}, "2026-07-09", source_dong="천호동"),
        _map_item_to_row({"id": "2", "name": "B"}, "2026-07-09", source_dong="천호동"),
        _map_item_to_row({"id": "3", "name": "C"}, "2026-07-09", source_dong="성내동"),
        _map_item_to_row({"id": "4", "name": "D"}, "2026-07-09"),  # source_dong 없음 -> unknown
    ]
    counts = count_rows_by_field(rows, "source_dong")
    if counts == {"천호동": 2, "성내동": 1, "unknown": 1}:
        reporter.pass_("count_rows_by_field가 source_dong 기준으로 정확히 집계(미지정 행은 unknown)")
    else:
        reporter.fail(f"count_rows_by_field(source_dong) 결과가 예상과 다름: {counts}")

    # count_rows_by_source_page와 동일한 결과를 내는지(일반화가 기존 동작을 보존하는지) 교차 확인.
    page_rows = [
        _map_item_to_row({"id": "1", "name": "A"}, "2026-07-09", source_page=1),
        _map_item_to_row({"id": "2", "name": "B"}, "2026-07-09", source_page=2),
    ]
    if count_rows_by_field(page_rows, "source_page") == count_rows_by_source_page(page_rows):
        reporter.pass_("count_rows_by_field(source_page)가 기존 count_rows_by_source_page와 동일한 결과를 냄")
    else:
        reporter.fail(
            f"count_rows_by_field/source_page 교차 검증 실패: "
            f"{count_rows_by_field(page_rows, 'source_page')} vs {count_rows_by_source_page(page_rows)}"
        )

    custom_label = count_rows_by_field(
        [_map_item_to_row({"id": "9", "name": "E"}, "2026-07-09")], "source_dong", unknown_label="미지정"
    )
    if custom_label == {"미지정": 1}:
        reporter.pass_("unknown_label을 커스텀 문자열로 지정할 수 있음")
    else:
        reporter.fail(f"custom unknown_label 결과가 예상과 다름: {custom_label}")


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
# PoC-6: classify_query_efficiency / should_stop_for_target 검증
# ---------------------------------------------------------------------------


def check_classify_query_efficiency_high_ratio_not_low(reporter: ValidationReporter) -> None:
    """PoC-4/PoC-5의 '깨끗한 동'(raw=20, unique_added=20)처럼 비율이 높으면
    low_efficiency=False가 되어야 한다."""
    result = classify_query_efficiency(20, 20)
    if result["efficiency_ratio"] == 1.0 and result["low_efficiency"] is False:
        reporter.pass_("raw=20/unique_added=20이면 efficiency_ratio=1.0, low_efficiency=False")
    else:
        reporter.fail(f"높은 비율 처리 결과가 예상과 다름: {result}")


def check_classify_query_efficiency_zero_unique_is_low(reporter: ValidationReporter) -> None:
    """PoC-5의 성내제1~3동(raw=20, unique_added=0)처럼 신규 기여가 0이면
    low_efficiency=True가 되어야 한다."""
    result = classify_query_efficiency(20, 0)
    if result["efficiency_ratio"] == 0.0 and result["low_efficiency"] is True:
        reporter.pass_("raw=20/unique_added=0이면 efficiency_ratio=0.0, low_efficiency=True(PoC-5 성내제N동 재현)")
    else:
        reporter.fail(f"zero unique_added 처리 결과가 예상과 다름: {result}")


def check_classify_query_efficiency_zero_raw_items_no_crash(reporter: ValidationReporter) -> None:
    """raw_items가 0이면(응답 자체가 없음) 0으로 나누지 않고 ratio=0.0을 반환한다."""
    result = classify_query_efficiency(0, 0)
    if result["efficiency_ratio"] == 0.0 and result["low_efficiency"] is True:
        reporter.pass_("raw_items=0이어도 예외 없이 efficiency_ratio=0.0으로 처리됨")
    else:
        reporter.fail(f"raw_items=0 처리 결과가 예상과 다름: {result}")


def check_classify_query_efficiency_boundary_values(reporter: ValidationReporter) -> None:
    """비율이 임계값(0.15) 이상이어도 unique_added가 절대 하한(3) 미만이면 low_efficiency다."""
    result = classify_query_efficiency(10, 2)  # ratio=0.2 (>=0.15) 이지만 unique_added=2 (<3)
    if abs(result["efficiency_ratio"] - 0.2) < 1e-9 and result["low_efficiency"] is True:
        reporter.pass_("비율은 임계값 이상이어도 unique_added 절대 하한 미만이면 low_efficiency=True")
    else:
        reporter.fail(f"경계값 처리 결과가 예상과 다름: {result}")


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
    check_dedup_rows(reporter)
    check_category_list_is_joined(reporter)
    check_homepage_instagram_url_classified_as_insta(reporter)
    check_homepage_blog_url_classified_as_blog(reporter)
    check_homepage_generic_url_classified_as_homepage(reporter)
    check_homepage_url_list_classified_individually(reporter)
    check_multi_page_merge_dedup_by_place_id(reporter)
    check_multi_page_merge_grows_when_no_duplicates(reporter)
    check_source_page_internal_meta_not_in_excel_columns(reporter)
    check_build_candidate_record_shape(reporter)
    check_captcha_signal_passive_marker_does_not_halt(reporter)
    check_captcha_signal_visible_indicator_is_active(reporter)
    check_captcha_signal_click_exception_is_strong_signal(reporter)
    check_count_rows_by_source_page_three_pages(reporter)
    check_total_dedup_after_three_page_merge(reporter)
    check_source_dong_and_query_internal_meta_not_in_excel_columns(reporter)
    check_count_rows_by_field_generic_aggregation(reporter)
    check_is_candidate_response_filters_correctly(reporter)
    check_classify_query_efficiency_high_ratio_not_low(reporter)
    check_classify_query_efficiency_zero_unique_is_low(reporter)
    check_classify_query_efficiency_zero_raw_items_no_crash(reporter)
    check_classify_query_efficiency_boundary_values(reporter)
    check_should_stop_for_target_reaches_and_below(reporter)
    check_should_stop_for_target_non_positive_target_is_false(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
