"""
Unit tests for the Apollo State Base+Parent normalization adapter (5O,
2026-07-23, scratchpad/page300_5o_real_apollo_parser_integration_audit 기반).

extract_normalized_apollo_detail() 순수 함수 레벨 - 축소·익명화된 합성
apollo_state dict만 사용한다(5M/5O raw JSON 원본을 fixture로 복사하지 않음).
"""

import copy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.collection.place_mapper import (
    _compute_total_review_count,
    _map_item_to_row,
    extract_normalized_apollo_detail,
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


def _base_entity(place_id="2014880028", **overrides):
    entity = {
        "id": place_id,
        "name": "테스트 카페",
        "category": "카페,디저트",
        "roadAddress": "서울 강동구 성내로 1",
        "address": "서울 강동구 천호동 1",
        "phone": "02-488-5582",
        "virtualPhone": "0507-1111-2222",
        "visitorReviewsTotal": 239,
        "cafeBlogReviewsTotal": 134,
        "naverBlog": None,
    }
    entity.update(overrides)
    return entity


def _parent_entity(base_ref="PlaceDetailBase:2014880028", **overrides):
    entity = {
        "base": {"__ref": base_ref},
        "homepages": {"repr": {"url": "https://example-cafe.test", "type": "홈페이지"}, "etc": []},
        "newOpening": False,
        "phoneInfo": {"phone": "02-488-5582", "isVirtualPhone": False, "isPrivatePhone": False},
    }
    entity.update(overrides)
    return entity


def _run_apollo_detail_adapter_suite() -> bool:
    reporter = SimpleReporter()

    # ------------------------------------------------------------------
    # Pure adapter (1~24)
    # ------------------------------------------------------------------

    # 1. 실제 구조의 Base 단독 추출
    state1 = {"PlaceDetailBase:2014880028": _base_entity()}
    result1 = extract_normalized_apollo_detail(state1, "2014880028")
    if result1.get("id") == "2014880028" and result1.get("visitorReviewsTotal") == 239:
        reporter.pass_("1. Base 단독 추출 성공")
    else:
        reporter.fail(f"1. Base 단독 추출 실패: {result1}")

    # 2. ROOT_QUERY inline parent + base.__ref 결합
    state2 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': _parent_entity(),
        },
    }
    result2 = extract_normalized_apollo_detail(state2, "2014880028")
    if result2.get("homepages", {}).get("repr", {}).get("url") == "https://example-cafe.test":
        reporter.pass_("2. ROOT_QUERY inline parent + base.__ref 결합 성공")
    else:
        reporter.fail(f"2. inline parent 결합 실패: {result2}")

    # 3. ROOT_QUERY parent __ref 1단계 해석
    state3 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "PlaceDetail:2014880028": _parent_entity(),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': {
                "__ref": "PlaceDetail:2014880028"
            },
        },
    }
    result3 = extract_normalized_apollo_detail(state3, "2014880028")
    if result3.get("newOpening") is False and "homepages" in result3:
        reporter.pass_("3. ROOT_QUERY parent __ref 1단계 해석 성공")
    else:
        reporter.fail(f"3. __ref 1단계 해석 실패: {result3}")

    # 4. Base + Parent 전체 결합
    result4 = extract_normalized_apollo_detail(state2, "2014880028")
    ok4 = (
        result4.get("phone") == "02-488-5582"
        and result4.get("visitorReviewsTotal") == 239
        and result4.get("cafeBlogReviewsTotal") == 134
        and "phoneInfo" in result4
    )
    if ok4:
        reporter.pass_("4. Base + Parent 전체 결합 성공")
    else:
        reporter.fail(f"4. 전체 결합 실패: {result4}")

    # 5. 잘못된 place_id Base 거부(base entity 자신의 id가 요청과 다름)
    state5 = {"PlaceDetailBase:2014880028": _base_entity(place_id="9999999999")}
    result5 = extract_normalized_apollo_detail(state5, "2014880028")
    if result5 == {}:
        reporter.pass_("5. 잘못된 place_id Base 거부 성공")
    else:
        reporter.fail(f"5. 잘못된 place_id Base가 거부되지 않음: {result5}")

    # 6. 다른 base.__ref parent 거부
    state6 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': _parent_entity(
                base_ref="PlaceDetailBase:9999999999"
            ),
        },
    }
    result6 = extract_normalized_apollo_detail(state6, "2014880028")
    if "homepages" not in result6 and result6.get("id") == "2014880028":
        reporter.pass_("6. 다른 base.__ref parent 거부 성공(base 필드만 반환)")
    else:
        reporter.fail(f"6. 다른 base.__ref parent가 잘못 채택됨: {result6}")

    # 7. stale parent가 먼저 있어도 exact parent 선택
    state7 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false},"stale":1})': _parent_entity(
                base_ref="PlaceDetailBase:0000000000"
            ),
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': _parent_entity(),
        },
    }
    result7 = extract_normalized_apollo_detail(state7, "2014880028")
    if result7.get("homepages", {}).get("repr", {}).get("url") == "https://example-cafe.test":
        reporter.pass_("7. stale parent가 먼저 있어도 exact parent 선택 성공")
    else:
        reporter.fail(f"7. exact parent 선택 실패: {result7}")

    # 8. 여러 업체 Apollo State에서 현재 place_id만 선택
    state8 = {
        "PlaceDetailBase:2014880028": _base_entity(place_id="2014880028", name="카페 A"),
        "PlaceDetailBase:1518485665": _base_entity(place_id="1518485665", name="카페 B"),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': _parent_entity(
                base_ref="PlaceDetailBase:2014880028"
            ),
            'placeDetail({"input":{"deviceType":"mobile","id":"1518485665","isNx":false}})': _parent_entity(
                base_ref="PlaceDetailBase:1518485665"
            ),
        },
    }
    result8 = extract_normalized_apollo_detail(state8, "2014880028")
    if result8.get("name") == "카페 A":
        reporter.pass_("8. 여러 업체 Apollo State에서 현재 place_id만 선택 성공")
    else:
        reporter.fail(f"8. 다른 업체 데이터가 섞임: {result8}")

    # 9. Base 없음 -> {}
    result9 = extract_normalized_apollo_detail({"ROOT_QUERY": {}}, "2014880028")
    if result9 == {}:
        reporter.pass_("9. Base 없음 -> {} 성공")
    else:
        reporter.fail(f"9. Base 없음 처리 실패: {result9}")

    # 10. Parent 없음 -> Base 필드만 반환
    state10 = {"PlaceDetailBase:2014880028": _base_entity()}
    result10 = extract_normalized_apollo_detail(state10, "2014880028")
    if result10.get("visitorReviewsTotal") == 239 and "homepages" not in result10 and "newOpening" not in result10:
        reporter.pass_("10. Parent 없음 -> Base 필드만 반환 성공")
    else:
        reporter.fail(f"10. Parent 없음 처리 실패: {result10}")

    # 11. malformed ROOT_QUERY 안전 처리
    state11 = {"PlaceDetailBase:2014880028": _base_entity(), "ROOT_QUERY": "not-a-dict"}
    result11 = extract_normalized_apollo_detail(state11, "2014880028")
    if result11.get("id") == "2014880028" and "homepages" not in result11:
        reporter.pass_("11. malformed ROOT_QUERY 안전 처리 성공")
    else:
        reporter.fail(f"11. malformed ROOT_QUERY 처리 실패: {result11}")

    # 12. 순환 ref 안전 처리(자기 자신을 가리키는 __ref, 무한루프/크래시 없음)
    state12 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "PlaceDetail:2014880028": {"__ref": "PlaceDetail:2014880028"},
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': {
                "__ref": "PlaceDetail:2014880028"
            },
        },
    }
    try:
        result12 = extract_normalized_apollo_detail(state12, "2014880028")
        ok12 = result12.get("id") == "2014880028" and "homepages" not in result12
    except Exception as exc:
        ok12 = False
        result12 = f"exception: {exc}"
    if ok12:
        reporter.pass_("12. 순환 ref 안전 처리 성공(크래시 없이 parent 미사용)")
    else:
        reporter.fail(f"12. 순환 ref 처리 실패: {result12}")

    # 13. visitorReviewsTotal 전달
    if extract_normalized_apollo_detail(state1, "2014880028").get("visitorReviewsTotal") == 239:
        reporter.pass_("13. visitorReviewsTotal 전달 성공")
    else:
        reporter.fail("13. visitorReviewsTotal 전달 실패")

    # 14. cafeBlogReviewsTotal 전달
    if extract_normalized_apollo_detail(state1, "2014880028").get("cafeBlogReviewsTotal") == 134:
        reporter.pass_("14. cafeBlogReviewsTotal 전달 성공")
    else:
        reporter.fail("14. cafeBlogReviewsTotal 전달 실패")

    # 15. 총리뷰수 parser 계산(adapter는 합산하지 않고 _map_item_to_row가 계산)
    apollo_detail15 = extract_normalized_apollo_detail(state1, "2014880028")
    row15 = _map_item_to_row(apollo_detail15, "2026-07-23")
    if row15.get("총리뷰수") == _compute_total_review_count(239, 134) == 373:
        reporter.pass_("15. 총리뷰수가 기존 parser 계산으로 373 산출 성공")
    else:
        reporter.fail(f"15. 총리뷰수 계산 실패: {row15.get('총리뷰수')}")

    # 16. phone 전달
    if row15.get("대표전화") == "02-488-5582":
        reporter.pass_("16. phone 전달 성공")
    else:
        reporter.fail(f"16. phone 전달 실패: {row15.get('대표전화')}")

    # 17. virtualPhone 전달(phone이 없을 때만 채택되는지 확인)
    state17 = {"PlaceDetailBase:2014880028": _base_entity(phone=None)}
    row17 = _map_item_to_row(extract_normalized_apollo_detail(state17, "2014880028"), "2026-07-23")
    if row17.get("대표전화") == "0507-1111-2222":
        reporter.pass_("17. phone 없을 때 virtualPhone 전달 성공")
    else:
        reporter.fail(f"17. virtualPhone 전달 실패: {row17.get('대표전화')}")

    # 18. 010 개인 모바일 폐기(가상 테스트 번호)
    state18 = {"PlaceDetailBase:2014880028": _base_entity(phone="010-0000-9999", virtualPhone=None)}
    row18 = _map_item_to_row(extract_normalized_apollo_detail(state18, "2014880028"), "2026-07-23")
    if row18.get("대표전화") == "":
        reporter.pass_("18. 010 개인 모바일 폐기 성공")
    else:
        reporter.fail(f"18. 개인 모바일 폐기 실패: {row18.get('대표전화')}")

    # 19. homepages 객체 전달 및 URL 분류
    row19 = _map_item_to_row(extract_normalized_apollo_detail(state2, "2014880028"), "2026-07-23")
    if row19.get("홈페이지") == "https://example-cafe.test":
        reporter.pass_("19. homepages 객체 전달 및 URL 분류 성공")
    else:
        reporter.fail(f"19. homepages URL 분류 실패: {row19.get('홈페이지')}")

    # 20. newOpening true -> O
    state20 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': _parent_entity(
                newOpening=True
            ),
        },
    }
    row20 = _map_item_to_row(extract_normalized_apollo_detail(state20, "2014880028"), "2026-07-23")
    if row20.get("새로오픈여부") == "O":
        reporter.pass_("20. newOpening true -> O 성공")
    else:
        reporter.fail(f"20. newOpening true 처리 실패: {row20.get('새로오픈여부')}")

    # 21. newOpening false -> X
    row21 = _map_item_to_row(extract_normalized_apollo_detail(state2, "2014880028"), "2026-07-23")
    if row21.get("새로오픈여부") == "X":
        reporter.pass_("21. newOpening false -> X 성공")
    else:
        reporter.fail(f"21. newOpening false 처리 실패: {row21.get('새로오픈여부')}")

    # 22. newOpening 미존재 -> 공란
    state22 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': {
                k: v for k, v in _parent_entity().items() if k != "newOpening"
            },
        },
    }
    row22 = _map_item_to_row(extract_normalized_apollo_detail(state22, "2014880028"), "2026-07-23")
    if row22.get("새로오픈여부") == "":
        reporter.pass_("22. newOpening 미존재 -> 공란 성공")
    else:
        reporter.fail(f"22. newOpening 미존재 처리 실패: {row22.get('새로오픈여부')}")

    # 23. 원본 Apollo State mutate 없음
    state23 = {
        "PlaceDetailBase:2014880028": _base_entity(),
        "ROOT_QUERY": {
            'placeDetail({"input":{"deviceType":"mobile","id":"2014880028","isNx":false}})': _parent_entity(),
        },
    }
    snapshot23 = copy.deepcopy(state23)
    extract_normalized_apollo_detail(state23, "2014880028")
    if state23 == snapshot23:
        reporter.pass_("23. 원본 Apollo State mutate 없음 성공")
    else:
        reporter.fail("23. 원본 Apollo State가 변형됨")

    # 24. 반환 dict에 불필요한 Apollo entity 없음
    result24 = extract_normalized_apollo_detail(state8, "2014880028")
    has_foreign_key = any(isinstance(k, str) and k.startswith("PlaceDetailBase:") for k in result24.keys())
    if not has_foreign_key and result24.get("name") == "카페 A":
        reporter.pass_("24. 반환 dict에 불필요한 Apollo entity 없음 성공")
    else:
        reporter.fail(f"24. 반환 dict에 불필요한 entity 포함됨: {result24}")

    print("\n====================")
    print(f"PASS: {reporter.passes}")
    print(f"FAIL: {reporter.fails}")
    print("====================")
    return reporter.fails == 0


def test_apollo_detail_adapter_suite():
    assert _run_apollo_detail_adapter_suite() is True


if __name__ == "__main__":
    success = _run_apollo_detail_adapter_suite()
    sys.exit(0 if success else 1)
