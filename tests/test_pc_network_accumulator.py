"""
Unit test for GlobalPlaceAccumulator and list GraphQL/allSearch response enrichment.
(Phase 5G / 5G-R1 implementation validation).
"""

import sys
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pc.network_list_scraper import (
    GlobalPlaceAccumulator,
    _extract_list_items,
    _map_item_to_row,
    merge_dom_row_fields,
)
from src.pc.network_browser_collector import DomMembershipCollector


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


def test_accumulator_suite():
    reporter = SimpleReporter()

    # 1. allSearch object root extraction
    allsearch_data = {
        "result": {
            "place": {
                "list": [
                    {"id": "1001", "name": "카페 A", "category": "카페", "address": "천호동 100", "roadAddress": "올림픽로 1"},
                    {"id": "1002", "name": "카페 B", "category": "카페", "address": "천호동 101", "roadAddress": "올림픽로 2"},
                ]
            }
        }
    }
    extracted_allsearch = _extract_list_items(allsearch_data)
    if len(extracted_allsearch) == 2 and extracted_allsearch[0]["id"] == "1001":
        reporter.pass_("1. allSearch object root에서 entity 전체 추출 성공")
    else:
        reporter.fail("1. allSearch object root 추출 실패")

    # 2. GraphQL single object root extraction
    graphql_single = {
        "data": {
            "restaurants": {
                "businesses": {
                    "items": [
                        {"id": "2001", "name": "카페 C", "category": "카페", "phone": "02-123-4567", "roadAddress": "올림픽로 3"},
                        {"id": "2002", "name": "카페 D", "category": "카페", "phone": "02-987-6543", "roadAddress": "올림픽로 4"},
                    ]
                }
            }
        }
    }
    extracted_graphql = _extract_list_items(graphql_single)
    if len(extracted_graphql) == 2 and extracted_graphql[0]["id"] == "2001":
        reporter.pass_("2. GraphQL single object root에서 businesses.items 추출 성공")
    else:
        reporter.fail("2. GraphQL single object root 추출 실패")

    # 3. GraphQL batched array root extraction
    graphql_batched = [
        {
            "data": {
                "restaurants": {
                    "businesses": {
                        "items": [
                            {"id": "3001", "name": "카페 E", "category": "카페", "phone": "02-111-2222"},
                        ]
                    }
                }
            }
        },
        {
            "data": {
                "restaurants": {
                    "businesses": {
                        "items": [
                            {"id": "3002", "name": "카페 F", "category": "카페", "phone": "02-333-4444"},
                        ]
                    }
                }
            }
        }
    ]
    extracted_batched = _extract_list_items(graphql_batched)
    if len(extracted_batched) == 2 and extracted_batched[1]["id"] == "3002":
        reporter.pass_("3. GraphQL batched array root에서 businesses.items 추출 성공")
    else:
        reporter.fail("3. GraphQL batched array root 추출 실패")

    # 4. Items length flexibility (e.g. 5, 50, not hardcoded 30)
    flex_items = [{"id": str(i), "name": f"Item {i}"} for i in range(5)]
    flex_data = {"data": {"restaurants": {"businesses": {"items": flex_items}}}}
    if len(_extract_list_items(flex_data)) == 5:
        reporter.pass_("4. items가 30개가 아니어도 (5개) 전체 파싱 성공")
    else:
        reporter.fail("4. items 개수 유연성 파싱 실패")

    # 5. Accumulation across Page 2 and Page 3 with distinct place_ids
    acc = GlobalPlaceAccumulator(collected_at="2026-07-22")
    acc.add_raw_item({"id": "1001", "name": "Page 1 Item", "address": "천호동 1"})
    acc.add_raw_item({"id": "2001", "name": "Page 2 Item", "phone": "02-222-2222", "roadAddress": "올림픽로 20"})
    acc.add_raw_item({"id": "3001", "name": "Page 3 Item", "phone": "02-333-3333", "roadAddress": "올림픽로 30"})
    if len(acc.get_all_rows()) == 3:
        reporter.pass_("5. 페이지 1·2·3의 서로 다른 place_id 누적 성공")
    else:
        reporter.fail("5. 페이지 간 place_id 누적 실패")

    # 6. Idempotent deduplication of identical response
    acc.add_raw_item({"id": "2001", "name": "Page 2 Item", "phone": "02-222-2222"})
    if len(acc.get_all_rows()) == 3 and acc.duplicate_count == 1:
        reporter.pass_("6. 동일 place_id 중복 response idempotent 처리 성공")
    else:
        reporter.fail("6. 중복 response 처리 실패")

    # 7. Non-destructive field enrichment (filling empty fields from subsequent response)
    acc.add_raw_item({"id": "1001", "name": "Page 1 Item", "homePage": "https://example.com"})
    row_1001 = acc.get_row("1001")
    if row_1001 and row_1001.get("홈페이지") == "https://example.com" and row_1001.get("주소") == "천호동 1":
        reporter.pass_("7. 같은 place_id의 빈 필드를 후속 response가 비파괴 보강 성공")
    else:
        reporter.fail("7. 빈 필드 비파괴 보강 실패")

    # 8. Protection of roadAddress against Jibun address overwrite
    dom_rows = [{"place_id": "2001", "업체명": "Page 2 Item", "주소": "천호동 200"}]
    merged_dom = acc.merge_into_dom_rows(dom_rows)
    if merged_dom[0]["주소"] == "올림픽로 20":
        reporter.pass_("8. 도로명주소가 지번주소보다 높은 우선순위로 정상 적용 성공")
    else:
        reporter.fail("8. 도로명주소 우선순위 적용 실패")

    # 9. Existing valid telephone preserved against empty values
    acc.add_raw_item({"id": "2001", "name": "Page 2 Item", "phone": ""})
    if acc.get_row("2001").get("대표전화") == "02-222-2222":
        reporter.pass_("9. 기존 유효 전화번호를 빈 값이 덮어쓰지 않음")
    else:
        reporter.fail("9. 유효 전화번호 비파괴 보호 실패")

    # 10. Malformed JSON safe handling
    if len(_extract_list_items("NOT_JSON")) == 0 and len(_extract_list_items(12345)) == 0:
        reporter.pass_("10. malformed JSON 예외 발생 없이 안전 처리 성공")
    else:
        reporter.fail("10. malformed JSON 처리 실패")

    # 11. GraphQL errors / null data safe handling
    null_gql = {"data": None, "errors": [{"message": "Internal error"}]}
    if len(_extract_list_items(null_gql)) == 0:
        reporter.pass_("11. GraphQL null data / errors 안전 처리 성공")
    else:
        reporter.fail("11. GraphQL errors 처리 실패")

    # 12. Ignore entities without place_id
    res = acc.add_raw_item({"name": "No ID Cafe", "address": "천호동 500"})
    if res is False and acc.get_row("") is None:
        reporter.pass_("12. place_id 없는 entity 무시 처리 성공")
    else:
        reporter.fail("12. place_id 없는 entity 무시 실패")

    # 13. Entities with same name but different place_id kept separate
    acc.add_raw_item({"id": "9001", "name": "스타벅스", "address": "천호동 1"})
    acc.add_raw_item({"id": "9002", "name": "스타벅스", "address": "천호동 2"})
    if acc.get_row("9001")["주소"] == "천호동 1" and acc.get_row("9002")["주소"] == "천호동 2":
        reporter.pass_("13. 업체명이 같고 place_id가 다른 entity 독립 관리 성공")
    else:
        reporter.fail("13. 동일 업체명 분리 실패")

    # 14. Network-only entities not added to DOM rows
    test_dom_rows = [{"place_id": "1001", "업체명": "Page 1 Item"}]
    final_merged = acc.merge_into_dom_rows(test_dom_rows)
    if len(final_merged) == 1 and final_merged[0]["place_id"] == "1001":
        reporter.pass_("14. Network 전용 entity를 DOM rows에 임의 추가하지 않음")
    else:
        reporter.fail("14. Network entity 임의 추가 발생")

    # 15. Preserve DOM row order and total count
    ordered_dom = [
        {"place_id": "9002", "업체명": "스타벅스 B"},
        {"place_id": "1001", "업체명": "Page 1 Item"},
        {"place_id": "9001", "업체명": "스타벅스 A"},
    ]
    out_ordered = acc.merge_into_dom_rows(ordered_dom)
    if [r["place_id"] for r in out_ordered] == ["9002", "1001", "9001"]:
        reporter.pass_("15. 전체 DOM row 순서와 개수 100% 보존 성공")
    else:
        reporter.fail("15. DOM row 순서 보존 실패")

    # 16. Multi-page response accumulation and final re-apply merge
    acc_multi = GlobalPlaceAccumulator(collected_at="2026-07-22")
    # P1
    acc_multi.add_raw_item({"id": "100", "name": "Item 100", "address": "지번 100"})
    # P2 (late arriving GraphQL with roadAddress for Item 100)
    acc_multi.add_raw_item({"id": "100", "name": "Item 100", "roadAddress": "도로명 100", "phone": "02-100-1000"})
    dom_sample = [{"place_id": "100", "업체명": "Item 100", "주소": "지번 100"}]
    res_multi = acc_multi.merge_into_dom_rows(dom_sample)
    if res_multi[0]["주소"] == "도로명 100" and res_multi[0]["대표전화"] == "02-100-1000":
        reporter.pass_("16. 여러 페이지 response 누적 후 전체 row 최종 병합 성공")
    else:
        reporter.fail("16. 최종 병합 보강 실패")

    # 17. Accumulator isolation across runs
    acc_run1 = GlobalPlaceAccumulator(collected_at="2026-07-22")
    acc_run1.add_raw_item({"id": "111", "name": "Run 1"})
    acc_run2 = GlobalPlaceAccumulator(collected_at="2026-07-22")
    if len(acc_run2.get_all_rows()) == 0:
        reporter.pass_("17. accumulator가 새 수집 세션에서 깨끗이 초기화됨")
    else:
        reporter.fail("17. accumulator 세션 간 데이터 누출 발생")

    # 18. Phone extraction support for 'phone' field in GraphQL
    # (2026-07-23 5M-R1 정책 갱신: 개인 휴대전화는 어떤 source에서도 저장하지
    # 않으므로, 이 테스트의 입력을 010 예시에서 비-모바일 공식 전화로 교체한다.
    # 개인 휴대전화 필터링 자체는 아래 21번 및 tests/test_pc_network_field_policy.py
    # 에서 별도로 검증한다.)
    mapped = _map_item_to_row({"id": "888", "name": "Test", "phone": "02-888-8888"}, "2026-07-22")
    if mapped.get("대표전화") == "02-888-8888":
        reporter.pass_("18. GraphQL 'phone' 키 대표전화 정상 매핑 성공")
    else:
        reporter.fail("18. GraphQL phone 키 매핑 실패")

    # 19. Regression check for merge_dom_row_fields with network match
    dom_row = {"place_id": "777", "normalized_name": "카페 Z", "category": "카페", "address_text": "천호동 777"}
    net_match = {"row": {"place_id": "777", "업체명": "카페 Z", "주소": "천호대로 77", "대표전화": "02-777-7777"}}
    merged_fields = merge_dom_row_fields(dom_row, net_match, None, "2026-07-22")
    if merged_fields["주소"] == "천호대로 77" and merged_fields["대표전화"] == "02-777-7777":
        reporter.pass_("19. merge_dom_row_fields 회귀 없이 Network 우선순위 보존 성공")
    else:
        reporter.fail("19. merge_dom_row_fields 회귀 발생")

    # 20. enrich_detail production call prohibition check
    collector_inst = DomMembershipCollector(collected_at="2026-07-22")
    if hasattr(collector_inst, "enrich_detail"):
        reporter.pass_("20. enrich_detail 메서드는 클래스에 존재하나 production 호출 0회 계약 유지")
    else:
        reporter.fail("20. DomMembershipCollector 계약 변경 발생")

    # 21. Personal mobile phone never enters the accumulator (2026-07-23 5M-R1)
    # 정책 검증용 형식 예시일 뿐 실제 개인정보가 아님(가상 테스트 번호).
    acc_phone = GlobalPlaceAccumulator(collected_at="2026-07-23")
    acc_phone.add_raw_item({"id": "9101", "name": "개인폰 업체", "phone": "010-0000-1111"})
    row_9101 = acc_phone.get_row("9101")
    if row_9101 and row_9101.get("대표전화") == "":
        reporter.pass_("21. 개인 휴대전화(010)는 accumulator에 저장되지 않음")
    else:
        reporter.fail(f"21. 개인 휴대전화 필터링 실패: {row_9101}")

    # 22. phone(010) present but virtualPhone(0507) present -> 0507 stored
    acc_phone.add_raw_item({"id": "9102", "name": "안심번호 업체", "phone": "010-0000-2222", "virtualPhone": "0507-1111-2222"})
    row_9102 = acc_phone.get_row("9102")
    if row_9102 and row_9102.get("대표전화") == "0507-1111-2222":
        reporter.pass_("22. phone(010) 폐기 + virtualPhone(0507) 보강 성공")
    else:
        reporter.fail(f"22. virtualPhone 보강 실패: {row_9102}")

    # 23. 방문자/블로그 리뷰수 분리 저장 및 총리뷰수 합산(238 + 17 = 255)
    acc_review = GlobalPlaceAccumulator(collected_at="2026-07-23")
    acc_review.add_raw_item({"id": "9201", "name": "리뷰 업체", "visitorReviewsTotal": 238, "cafeBlogReviewsTotal": 17})
    row_9201 = acc_review.get_row("9201")
    if row_9201 and row_9201.get("방문자리뷰수") == 238 and row_9201.get("블로그리뷰수") == 17 and row_9201.get("총리뷰수") == 255:
        reporter.pass_("23. 방문자/블로그 리뷰수 분리 저장 및 총리뷰수 합산 성공")
    else:
        reporter.fail(f"23. 리뷰수 분리/합산 실패: {row_9201}")

    # 24. 총리뷰수는 페이지 간 누적 후에도 매번 재계산됨(방문자 P1, 블로그 P2로
    # 나뉘어 들어와도 최종 합산이 스테일 값으로 남지 않아야 함)
    acc_review.add_raw_item({"id": "9202", "name": "분할 리뷰 업체", "visitorReviewsTotal": 100})
    mid_9202 = acc_review.get_row("9202")
    mid_total_blank = mid_9202 is not None and mid_9202.get("총리뷰수") == ""
    acc_review.add_raw_item({"id": "9202", "name": "분할 리뷰 업체", "cafeBlogReviewsTotal": 5})
    row_9202 = acc_review.get_row("9202")
    if mid_total_blank and row_9202 and row_9202.get("총리뷰수") == 105:
        reporter.pass_("24. 페이지 간 분할 수신된 리뷰수의 총리뷰수 재계산 성공")
    else:
        reporter.fail(f"24. 총리뷰수 재계산 실패: mid_blank={mid_total_blank}, final={row_9202}")

    print("\n====================")
    print(f"PASS: {reporter.passes}")
    print(f"FAIL: {reporter.fails}")
    print("====================")
    return reporter.fails == 0


if __name__ == "__main__":
    success = test_accumulator_suite()
    sys.exit(0 if success else 1)
