"""
Unit tests for 5M-R1 field policy: review split/total, personal mobile phone
filter, external URL classification, new-open tri-state.
(2026-07-23, scratchpad/page300_5m_r1_graphql_field_provenance_audit 기반)

테스트 fixture의 전화번호는 전부 정책 검증용 가상값(0000/1111 등)이며 실제
개인정보가 아니다. 실패 출력에도 실제 개인 번호가 노출되지 않도록
가상값만 사용한다.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pc.network_list_scraper import (
    _compute_total_review_count,
    _extract_external_urls,
    _is_personal_mobile_phone,
    _map_item_to_row,
    _normalize_review_count,
    _resolve_new_open_tristate,
    _resolve_official_phone,
    merge_dom_row_fields,
)


class SimpleReporter:
    def __init__(self):
        self.passes = 0
        self.fails = 0

    def pass_(self, msg: str):
        self.passes += 1
        print(f"[PASS] {msg}")

    def fail(self, msg: str):
        self.fails += 1
        print(f"[FAIL] {msg}")


def test_field_policy_suite():
    reporter = SimpleReporter()

    # ------------------------------------------------------------------
    # A. 리뷰
    # ------------------------------------------------------------------

    # 1. 방문자·블로그 각각 정상 추출
    row1 = _map_item_to_row({"id": "1", "name": "A", "visitorReviewsTotal": 238, "cafeBlogReviewsTotal": 17}, "2026-07-23")
    if row1.get("방문자리뷰수") == 238 and row1.get("블로그리뷰수") == 17:
        reporter.pass_("1. 방문자/블로그 리뷰수 각각 정상 추출")
    else:
        reporter.fail(f"1. 방문자/블로그 리뷰수 추출 실패: {row1}")

    # 2. 두 값 합산
    if _compute_total_review_count(238, 17) == 255:
        reporter.pass_("2. 두 값 합산 성공")
    else:
        reporter.fail("2. 두 값 합산 실패")

    # 3. 방문자 238 + 블로그 17 = 총 255 (row 단위 재확인)
    if row1.get("총리뷰수") == 255:
        reporter.pass_("3. 방문자 238 + 블로그 17 = 총 255")
    else:
        reporter.fail(f"3. 총리뷰수 계산 실패: {row1.get('총리뷰수')}")

    # 4. 블로그 명시적 0이면 총합 정상(238 + 0 = 238)
    row4 = _map_item_to_row({"id": "4", "name": "B", "visitorReviewsTotal": 238, "cafeBlogReviewsTotal": 0}, "2026-07-23")
    if row4.get("블로그리뷰수") == 0 and row4.get("총리뷰수") == 238:
        reporter.pass_("4. 블로그 명시적 0이어도 총합 정상(238)")
    else:
        reporter.fail(f"4. 명시적 0 처리 실패: {row4}")

    # 5. 한쪽 null이면 총합 공란
    row5 = _map_item_to_row({"id": "5", "name": "C", "visitorReviewsTotal": 238, "cafeBlogReviewsTotal": None}, "2026-07-23")
    if row5.get("총리뷰수") == "":
        reporter.pass_("5. 한쪽 null이면 총리뷰수 공란")
    else:
        reporter.fail(f"5. null 처리 실패: {row5.get('총리뷰수')!r}")

    # 6. 한쪽 key 미존재면 총합 공란
    row6 = _map_item_to_row({"id": "6", "name": "D", "visitorReviewsTotal": 238}, "2026-07-23")
    if row6.get("블로그리뷰수") == "" and row6.get("총리뷰수") == "":
        reporter.pass_("6. 한쪽 key 미존재면 총리뷰수 공란")
    else:
        reporter.fail(f"6. key 미존재 처리 실패: {row6}")

    # 7. 문자열 쉼표 숫자 normalization
    if _normalize_review_count("1,234") == 1234:
        reporter.pass_("7. 문자열 쉼표 숫자 normalization 성공")
    else:
        reporter.fail("7. 콤마 숫자 normalization 실패")

    # 8. Boolean 값 거부
    if _normalize_review_count(True) == "" and _normalize_review_count(False) == "":
        reporter.pass_("8. Boolean 값 거부 성공")
    else:
        reporter.fail("8. Boolean 값이 숫자로 취급됨")

    # 9. 음수 거부
    if _normalize_review_count(-5) == "" and _normalize_review_count("-5") == "":
        reporter.pass_("9. 음수 거부 성공")
    else:
        reporter.fail("9. 음수가 그대로 통과됨")

    # 10. 기존 단일 리뷰수 의미가 총리뷰로 잘못 유지되지 않음
    #     (리뷰수 키 자체가 더 이상 생성되지 않고, 미확인 상태에서 억지로
    #     합산되지 않는지 확인)
    row10 = _map_item_to_row({"id": "10", "name": "E", "reviewCount": "999"}, "2026-07-23")
    if "리뷰수" not in row10 and row10.get("총리뷰수") == "":
        reporter.pass_("10. 기존 단일 리뷰수 의미가 총리뷰로 잘못 유지되지 않음")
    else:
        reporter.fail(f"10. 리뷰수 의미 오염 발생: {row10}")

    # ------------------------------------------------------------------
    # B. 전화
    # ------------------------------------------------------------------

    # 11. 일반 지역번호 저장
    phone11, _ = _resolve_official_phone({"phone": "02-488-5582"})
    if phone11 == "02-488-5582":
        reporter.pass_("11. 일반 지역번호 저장 성공")
    else:
        reporter.fail(f"11. 지역번호 저장 실패: {phone11!r}")

    # 12. 대표번호 저장
    phone12, _ = _resolve_official_phone({"phone": "1588-1234"})
    if phone12 == "1588-1234":
        reporter.pass_("12. 대표번호 저장 성공")
    else:
        reporter.fail(f"12. 대표번호 저장 실패: {phone12!r}")

    # 13. virtualPhone 0507 저장
    phone13, _ = _resolve_official_phone({"virtualPhone": "0507-1111-2222"})
    if phone13 == "0507-1111-2222":
        reporter.pass_("13. virtualPhone(0507) 저장 성공")
    else:
        reporter.fail(f"13. virtualPhone 저장 실패: {phone13!r}")

    # 14. phone null + virtualPhone 존재 시 보강
    phone14, _ = _resolve_official_phone({"phone": None, "virtualPhone": "0507-3333-4444"})
    if phone14 == "0507-3333-4444":
        reporter.pass_("14. phone null + virtualPhone 보강 성공")
    else:
        reporter.fail(f"14. virtualPhone 보강 실패: {phone14!r}")

    # 15. 010 번호 폐기
    phone15, filtered15 = _resolve_official_phone({"phone": "010-0000-1111"})
    if phone15 == "" and filtered15 == 1:
        reporter.pass_("15. 010 번호 폐기 성공")
    else:
        reporter.fail(f"15. 010 번호 폐기 실패: {phone15!r}")

    # 16. 하이픈 없는 010 폐기
    if _is_personal_mobile_phone("01000001111"):
        reporter.pass_("16. 하이픈 없는 010 폐기 성공")
    else:
        reporter.fail("16. 하이픈 없는 010 판정 실패")

    # 17. +82-10 폐기
    if _is_personal_mobile_phone("+82 10-0000-1111") and _is_personal_mobile_phone("82-10-0000-1111"):
        reporter.pass_("17. +82-10 / 82-10 폐기 성공")
    else:
        reporter.fail("17. 국제표기 010 폐기 실패")

    # 18. 구형 모바일 prefix 폐기 (011/016/017/018/019)
    old_prefixes_ok = all(
        _is_personal_mobile_phone(f"{prefix}-000-1111") for prefix in ("011", "016", "017", "018", "019")
    )
    if old_prefixes_ok:
        reporter.pass_("18. 구형 모바일 prefix(011/016~019) 폐기 성공")
    else:
        reporter.fail("18. 구형 모바일 prefix 폐기 실패")

    # 19. phone 010 + virtualPhone 0507이면 0507 저장
    phone19, filtered19 = _resolve_official_phone({"phone": "010-0000-5555", "virtualPhone": "0507-5555-6666"})
    if phone19 == "0507-5555-6666" and filtered19 == 1:
        reporter.pass_("19. phone(010) 폐기 + virtualPhone(0507) 채택 성공")
    else:
        reporter.fail(f"19. 우선순위 폐기/채택 실패: {phone19!r}, filtered={filtered19}")

    # 20. 개인 모바일 원문 로그 미출력 (반환값 어디에도 원문 010이 남지 않음)
    row20 = _map_item_to_row({"id": "20", "name": "F", "phone": "010-0000-7777"}, "2026-07-23")
    row20_repr = repr(row20)
    if "010-0000-7777" not in row20_repr and row20.get("대표전화") == "":
        reporter.pass_("20. 개인 모바일 원문이 row/로그 표현에 남지 않음")
    else:
        reporter.fail("20. 개인 모바일 원문이 결과에 노출됨")

    # 21. 빈 전화가 기존 유효 번호를 덮어쓰지 않음 (merge_dom_row_fields 레벨,
    # detail_row가 개인 모바일을 반환해도 network_row의 유효 값을 지키지 않고
    # 안전하게 공란 처리되는지 확인 - 상세 경로 안전망 검증)
    dom_row21 = {"place_id": "21", "normalized_name": "G", "category": "카페", "address_text": "천호동 21"}
    network_match21 = {"row": {"place_id": "21", "대표전화": "02-999-9999"}}
    detail_result21 = {"detail_success": True, "place_id": "21", "대표전화": "010-0000-8888"}
    merged21 = merge_dom_row_fields(dom_row21, network_match21, None, "2026-07-23", detail_result21)
    if merged21["대표전화"] == "":
        reporter.pass_("21. 상세 경로의 개인 모바일도 최종 병합에서 필터링됨")
    else:
        reporter.fail(f"21. 상세 경로 개인 모바일 안전망 실패: {merged21['대표전화']!r}")

    # ------------------------------------------------------------------
    # C. 외부 URL
    # ------------------------------------------------------------------

    # 22. homepages 문자열 배열(legacy homePage 스타일)
    home22, insta22, blog22, _ = _extract_external_urls({"homePage": ["https://example.com", "https://www.instagram.com/example"]})
    if home22 == "https://example.com" and insta22 == "https://www.instagram.com/example":
        reporter.pass_("22. 문자열 리스트 형태 URL 분류 성공")
    else:
        reporter.fail(f"22. 문자열 리스트 URL 분류 실패: {(home22, insta22, blog22)}")

    # 23. homepages 객체(repr/etc) 형태
    home23, insta23, blog23, _ = _extract_external_urls({
        "homepages": {
            "repr": {"url": "https://blog.naver.com/cafein5959", "type": "블로그"},
            "etc": [{"landingUrl": "https://example-cafe.com", "type": "홈페이지"}],
        }
    })
    if blog23 == "https://blog.naver.com/cafein5959" and home23 == "https://example-cafe.com":
        reporter.pass_("23. homepages{repr,etc} 객체 구조 분류 성공")
    else:
        reporter.fail(f"23. homepages 객체 분류 실패: {(home23, insta23, blog23)}")

    # 24. snsList 인스타 분류(방어적 지원, 5M 증거에는 미확인 키)
    _, insta24, _, _ = _extract_external_urls({"snsList": [{"url": "https://www.instagram.com/w.b.o.cake", "type": "인스타그램"}]})
    if insta24 == "https://www.instagram.com/w.b.o.cake":
        reporter.pass_("24. snsList 인스타 분류 성공")
    else:
        reporter.fail(f"24. snsList 분류 실패: {insta24!r}")

    # 25. blog.naver.com 블로그 분류
    _, _, blog25, _ = _extract_external_urls({"homePage": "https://blog.naver.com/somecafe"})
    if blog25 == "https://blog.naver.com/somecafe":
        reporter.pass_("25. blog.naver.com 블로그 분류 성공")
    else:
        reporter.fail(f"25. 블로그 분류 실패: {blog25!r}")

    # 26. 공식 홈페이지 분류
    home26, _, _, _ = _extract_external_urls({"homePage": "https://my-official-cafe.example"})
    if home26 == "https://my-official-cafe.example":
        reporter.pass_("26. 공식 홈페이지 분류 성공")
    else:
        reporter.fail(f"26. 홈페이지 분류 실패: {home26!r}")

    # 27. 네이버 예약 링크 홈페이지 제외
    home27, _, _, _ = _extract_external_urls({"homePage": "https://booking.naver.com/booking/some-shop"})
    if home27 == "":
        reporter.pass_("27. 네이버 예약 링크 홈페이지 제외 성공")
    else:
        reporter.fail(f"27. 예약 링크가 홈페이지로 채택됨: {home27!r}")

    # 28. 네이버 주문 링크 홈페이지 제외
    home28, _, _, _ = _extract_external_urls({"homePage": "https://order.naver.com/orders/some-shop"})
    if home28 == "":
        reporter.pass_("28. 네이버 주문 링크 홈페이지 제외 성공")
    else:
        reporter.fail(f"28. 주문 링크가 홈페이지로 채택됨: {home28!r}")

    # 29. 동일 URL 중복 제거
    home29, _, _, _ = _extract_external_urls({"homePage": ["https://dup-cafe.example", "https://dup-cafe.example/"]})
    if home29 == "https://dup-cafe.example":
        reporter.pass_("29. 동일 URL(trailing slash 차이) 중복 제거 성공")
    else:
        reporter.fail(f"29. 중복 제거 실패: {home29!r}")

    # 30. 잘못된 scheme 거부
    home30, insta30, blog30, _ = _extract_external_urls({"homePage": "javascript:alert(1)"})
    if home30 == "" and insta30 == "" and blog30 == "":
        reporter.pass_("30. 잘못된 scheme(javascript:) 거부 성공")
    else:
        reporter.fail(f"30. 잘못된 scheme이 통과됨: {(home30, insta30, blog30)}")

    # 31. URL 배열 값이 최종 row(Excel 투영 대상)까지 유지
    row31 = _map_item_to_row({
        "id": "31", "name": "H",
        "homepages": {"repr": {"url": "https://my-cafe-31.example", "type": "홈페이지"}, "etc": []},
    }, "2026-07-23")
    if row31.get("홈페이지") == "https://my-cafe-31.example":
        reporter.pass_("31. URL 값이 최종 row까지 유지됨")
    else:
        reporter.fail(f"31. URL 값이 최종 row에 유지되지 않음: {row31.get('홈페이지')!r}")

    # ------------------------------------------------------------------
    # D. 새로오픈 tri-state
    # ------------------------------------------------------------------

    # 32. 목록 true -> O
    if _resolve_new_open_tristate({"newOpening": True}) == "O":
        reporter.pass_("32. newOpening true -> O 성공")
    else:
        reporter.fail("32. true -> O 변환 실패")

    # 33. 명시적 false -> X
    if _resolve_new_open_tristate({"newOpening": False}) == "X":
        reporter.pass_("33. newOpening false -> X 성공")
    else:
        reporter.fail("33. false -> X 변환 실패")

    # 34. key 미존재 -> 공란
    if _resolve_new_open_tristate({}) == "":
        reporter.pass_("34. key 미존재 -> 공란 성공")
    else:
        reporter.fail("34. key 미존재가 공란으로 처리되지 않음")

    # 35. null -> 공란
    if _resolve_new_open_tristate({"newOpening": None}) == "":
        reporter.pass_("35. newOpening null -> 공란 성공")
    else:
        reporter.fail("35. null이 공란으로 처리되지 않음")

    # 36. 상세 미확인이 목록 O를 덮어쓰지 않음 (merge_dom_row_fields 레벨:
    # DOM raw_text 뱃지가 "O"를 확정했으면 network/detail이 미확인이어도 유지)
    dom_row36 = {"place_id": "36", "normalized_name": "새로오픈카페", "category": "카페", "raw_text": "새로오픈카페 새로오픈 카페", "address_text": ""}
    network_match36 = {"row": {"place_id": "36", "새로오픈여부": ""}}
    merged36 = merge_dom_row_fields(dom_row36, network_match36, None, "2026-07-23", {"새로오픈여부": ""})
    if merged36["새로오픈여부"] == "O":
        reporter.pass_("36. 상세/네트워크 미확인이 목록 O를 덮어쓰지 않음")
    else:
        reporter.fail(f"36. 목록 O가 덮어써짐: {merged36['새로오픈여부']!r}")

    print("\n====================")
    print(f"PASS: {reporter.passes}")
    print(f"FAIL: {reporter.fails}")
    print("====================")
    return reporter.fails == 0


if __name__ == "__main__":
    success = test_field_policy_suite()
    sys.exit(0 if success else 1)
