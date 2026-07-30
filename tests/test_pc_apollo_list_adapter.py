"""
Unit tests for src/pc/apollo_list_adapter.py - 신규 Apollo/GraphQL-first 목록
수집 경로의 1페이지 파서(ROOT_QUERY의 메인 placeList(...) operation 선택).

합성/익명화된 최소 fixture만 사용한다(실제 네이버 raw JSON을 그대로 복사하지
않음) - placeList(...) 키의 정확한 input 필드명은 이 저장소에 이미 증명된
placeDetail({"input":{...}}) 패턴과 동일한 "fieldName(JSON)" 형태를 그대로
따른다고 가정한 것이며, Live 검증 전까지는 이 fixture의 필드명이 실제와
다를 수 있다(apollo_list_adapter.py 모듈 docstring 참고).
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pc.apollo_list_adapter import (
    build_rows_from_apollo_list_result,
    extract_main_place_list_from_apollo,
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


def _op_key(prefix: str, input_obj: dict) -> str:
    return f"{prefix}({json.dumps({'input': input_obj})})"


def _item_entity(place_id: str, name: str = "테스트 카페", **overrides) -> dict:
    entity = {
        "id": place_id,
        "name": name,
        "category": "카페",
        "visitorReviewsTotal": 10,
        "cafeBlogReviewsTotal": 5,
        "roadAddress": "서울 강남구 테헤란로 1",
        "phone": "02-000-0000",
    }
    entity.update(overrides)
    return entity


def _ref(key: str) -> dict:
    return {"__ref": key}


def _run_apollo_list_adapter_suite() -> bool:
    reporter = SimpleReporter()
    query = "강남구 카페"
    start = 0

    # 1. 정상 매칭: businesses.items가 인라인(placeList 값 자체가 인라인 dict)
    state1 = {
        "PlaceListBusinessesItem:111:111": _item_entity("111", name="카페 A"),
        "PlaceListBusinessesItem:222:222": _item_entity("222", name="카페 B"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": start, "display": 70}): {
                "businesses": {"items": [_ref("PlaceListBusinessesItem:111:111"), _ref("PlaceListBusinessesItem:222:222")]}
            },
        },
    }
    result1 = extract_main_place_list_from_apollo(state1, query, start)
    names1 = [item.get("name") for item in result1["items"]]
    if result1["error"] == "" and names1 == ["카페 A", "카페 B"]:
        reporter.pass_("1. 정상 매칭 - businesses.items 순서 보존 추출 성공")
    else:
        reporter.fail(f"1. 정상 매칭 실패: {result1}")

    # 2. filterOpening=true 후보 제외
    state2 = {
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": start, "filterOpening": True}): {
                "businesses": {"items": []}
            },
        },
    }
    result2 = extract_main_place_list_from_apollo(state2, query, start)
    if result2["error"] == "no_matching_placelist_operation" and result2["items"] == []:
        reporter.pass_("2. filterOpening=true 후보 제외 성공")
    else:
        reporter.fail(f"2. filterOpening 제외 실패: {result2}")

    # 3. display=9 보조 query 제외
    state3 = {
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": start, "display": 9}): {
                "businesses": {"items": []}
            },
        },
    }
    result3 = extract_main_place_list_from_apollo(state3, query, start)
    if result3["error"] == "no_matching_placelist_operation":
        reporter.pass_("3. display=9 보조 query 제외 성공")
    else:
        reporter.fail(f"3. display=9 제외 실패: {result3}")

    # 4. query 문자열이 달라도(공백/축약 차이 등) 구조적으로 유효한 후보가
    # 유일하면 그대로 채택한다(2026-07-25 정책 변경 - query 완전일치를 hard
    # filter로 쓰지 않음. §7 "정확한 query 문자열 완전일치에만 의존하지
    # 않으면서" - 유일한 후보를 문자열 불일치만으로 실패 처리하지 않는다).
    state4 = {
        "PlaceListBusinessesItem:401:401": _item_entity("401", name="카페 다른검색어"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": "완전히 다른 검색어", "start": start}): {
                "businesses": {"items": [_ref("PlaceListBusinessesItem:401:401")]}
            },
        },
    }
    result4 = extract_main_place_list_from_apollo(state4, query, start)
    if result4["error"] == "" and [i.get("name") for i in result4["items"]] == ["카페 다른검색어"]:
        reporter.pass_("4. query mismatch여도 유일한 구조적 유효 후보는 그대로 채택 성공")
    else:
        reporter.fail(f"4. query mismatch 단일 후보 채택 실패: {result4}")

    # 5. start 값이 달라도 구조적으로 유효한 후보가 유일하면 그대로 채택한다
    # (§7 "start 매칭 완화" - 네이버가 1페이지를 start=1 등 다른 값으로 보낼
    # 수 있으므로 hard filter로 쓰지 않는다).
    state5 = {
        "PlaceListBusinessesItem:501:501": _item_entity("501", name="카페 다른start"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": 99}): {
                "businesses": {"items": [_ref("PlaceListBusinessesItem:501:501")]}
            },
        },
    }
    result5 = extract_main_place_list_from_apollo(state5, query, start)
    if result5["error"] == "" and [i.get("name") for i in result5["items"]] == ["카페 다른start"]:
        reporter.pass_("5. start mismatch여도 유일한 구조적 유효 후보는 그대로 채택 성공")
    else:
        reporter.fail(f"5. start mismatch 단일 후보 채택 실패: {result5}")

    # 6. 동점 후보(같은 size/query_score/start_score)의 유효 place_id 집합이
    # 서로 다르면 임의로 채택하지 않고 ambiguous_placelist_operation을
    # 반환한다(§7 금지 사항 - 모호한 후보 조용히 선택 금지).
    key_a = _op_key("placeList", {"query": query, "start": start, "tag": "a"})
    key_b = _op_key("placeList", {"query": query, "start": start, "tag": "b"})
    state6 = {
        "PlaceListBusinessesItem:601:601": _item_entity("601", name="카페F"),
        "PlaceListBusinessesItem:602:602": _item_entity("602", name="카페G"),
        "ROOT_QUERY": {
            key_a: {"businesses": {"items": [_ref("PlaceListBusinessesItem:601:601")]}},
            key_b: {"businesses": {"items": [_ref("PlaceListBusinessesItem:602:602")]}},
        },
    }
    result6 = extract_main_place_list_from_apollo(state6, query, start)
    if result6["error"] == "ambiguous_placelist_operation" and result6["items"] == []:
        reporter.pass_("6. 동점 + ID 집합이 다른 후보는 ambiguous_placelist_operation으로 임의 채택하지 않음 성공")
    else:
        reporter.fail(f"6. ambiguous 실패: {result6}")

    # 7. placeList( 키 자체가 없음
    state7 = {"ROOT_QUERY": {"someOtherQuery(...)": {}}}
    result7 = extract_main_place_list_from_apollo(state7, query, start)
    if result7["error"] == "no_placelist_operation_found":
        reporter.pass_("7. placeList 후보 없음 성공")
    else:
        reporter.fail(f"7. placeList 후보 없음 처리 실패: {result7}")

    # 8. ROOT_QUERY 없음/dict 아님
    result8a = extract_main_place_list_from_apollo({}, query, start)
    result8b = extract_main_place_list_from_apollo({"ROOT_QUERY": "not_a_dict"}, query, start)
    if result8a["error"] == "root_query_missing" and result8b["error"] == "root_query_missing":
        reporter.pass_("8. ROOT_QUERY 없음/타입 불일치 성공")
    else:
        reporter.fail(f"8. ROOT_QUERY 누락 처리 실패: {result8a} / {result8b}")

    # 9. apollo_state 자체가 dict가 아님/None
    result9a = extract_main_place_list_from_apollo(None, query, start)
    result9b = extract_main_place_list_from_apollo("not_a_dict", query, start)
    if result9a["error"] == "apollo_state_missing" and result9a["available"] is False and result9b["error"] == "apollo_state_missing":
        reporter.pass_("9. apollo_state 타입 불일치 성공")
    else:
        reporter.fail(f"9. apollo_state 타입 불일치 처리 실패: {result9a} / {result9b}")

    # 10. 선택된 placeList 값이 __ref(1단계 해석) -> businesses 인라인
    state10 = {
        "PlaceListPage:1": {"businesses": {"items": [_ref("PlaceListBusinessesItem:333:333")]}},
        "PlaceListBusinessesItem:333:333": _item_entity("333", name="카페 C"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": start}): _ref("PlaceListPage:1"),
        },
    }
    result10 = extract_main_place_list_from_apollo(state10, query, start)
    if result10["error"] == "" and [i.get("name") for i in result10["items"]] == ["카페 C"]:
        reporter.pass_("10. placeList 값 __ref 1단계 해석 성공")
    else:
        reporter.fail(f"10. placeList __ref 해석 실패: {result10}")

    # 11. businesses 필드 자체도 __ref(2단계 총 해석)
    state11 = {
        "PlaceListBusinesses:1": {"items": [_ref("PlaceListBusinessesItem:444:444")]},
        "PlaceListBusinessesItem:444:444": _item_entity("444", name="카페 D"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": start}): {"businesses": _ref("PlaceListBusinesses:1")},
        },
    }
    result11 = extract_main_place_list_from_apollo(state11, query, start)
    if result11["error"] == "" and [i.get("name") for i in result11["items"]] == ["카페 D"]:
        reporter.pass_("11. businesses __ref 2단계 해석 성공")
    else:
        reporter.fail(f"11. businesses __ref 해석 실패: {result11}")

    # 12. businesses.items가 없거나 list가 아님
    state12a = {"ROOT_QUERY": {_op_key("placeList", {"query": query, "start": start}): {"businesses": {}}}}
    state12b = {"ROOT_QUERY": {_op_key("placeList", {"query": query, "start": start}): {"businesses": {"items": "not_a_list"}}}}
    result12a = extract_main_place_list_from_apollo(state12a, query, start)
    result12b = extract_main_place_list_from_apollo(state12b, query, start)
    if result12a["error"] == "businesses_items_missing" and result12b["error"] == "businesses_items_missing":
        reporter.pass_("12. businesses.items 누락/타입 불일치 성공")
    else:
        reporter.fail(f"12. businesses.items 누락 처리 실패: {result12a} / {result12b}")

    # 13. items 안의 __ref가 apollo_state에 존재하지 않음 -> missing_refs 기록, 나머지는 정상 반환
    state13 = {
        "PlaceListBusinessesItem:555:555": _item_entity("555", name="카페 E"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": start}): {
                "businesses": {
                    "items": [
                        _ref("PlaceListBusinessesItem:555:555"),
                        _ref("PlaceListBusinessesItem:999:999"),
                    ]
                }
            },
        },
    }
    result13 = extract_main_place_list_from_apollo(state13, query, start)
    if (
        result13["error"] == ""
        and [i.get("name") for i in result13["items"]] == ["카페 E"]
        and result13["missing_ref_count"] == 1
        and result13["missing_refs"] == ["PlaceListBusinessesItem:999:999"]
    ):
        reporter.pass_("13. missing __ref 진단(예외 없이 스킵 + 기록) 성공")
    else:
        reporter.fail(f"13. missing __ref 처리 실패: {result13}")

    # 14. 빈 items(합법적인 0건 검색 결과) - 정상 성공으로 취급
    state14 = {"ROOT_QUERY": {_op_key("placeList", {"query": query, "start": start}): {"businesses": {"items": []}}}}
    result14 = extract_main_place_list_from_apollo(state14, query, start)
    if result14["error"] == "" and result14["items"] == []:
        reporter.pass_("14. 빈 items를 정상 성공으로 처리 성공")
    else:
        reporter.fail(f"14. 빈 items 처리 실패: {result14}")

    # 15. 순서 보존(중간에 missing ref가 섞여도 나머지 순서 유지)
    state15 = {
        "PlaceListBusinessesItem:1:1": _item_entity("1", name="1번"),
        "PlaceListBusinessesItem:3:3": _item_entity("3", name="3번"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": query, "start": start}): {
                "businesses": {
                    "items": [
                        _ref("PlaceListBusinessesItem:1:1"),
                        _ref("PlaceListBusinessesItem:2:2"),
                        _ref("PlaceListBusinessesItem:3:3"),
                    ]
                }
            },
        },
    }
    result15 = extract_main_place_list_from_apollo(state15, query, start)
    if [i.get("name") for i in result15["items"]] == ["1번", "3번"] and result15["missing_ref_count"] == 1:
        reporter.pass_("15. 중간 missing ref가 있어도 나머지 순서 보존 성공")
    else:
        reporter.fail(f"15. 순서 보존 실패: {result15}")

    # 16. build_rows_from_apollo_list_result가 _map_item_to_row로 정확히 매핑
    rows16 = build_rows_from_apollo_list_result(result1, "2026-07-24", source_query=query)
    if (
        len(rows16) == 2
        and rows16[0]["업체명"] == "카페 A"
        and rows16[0]["place_id"] == "111"
        and rows16[1]["업체명"] == "카페 B"
        and rows16[0]["수집일"] == "2026-07-24"
    ):
        reporter.pass_("16. build_rows_from_apollo_list_result 매핑 순서 보존 성공")
    else:
        reporter.fail(f"16. build_rows_from_apollo_list_result 매핑 실패: {rows16}")

    # 17. main(50개) + auxiliary(9개, filterOpening=true)가 함께 존재해도
    # 절대 개수(70 등)를 하드코딩하지 않고 상대 크기로 main을 선택한다.
    main_ids = [(f"m{i}", f"메인카페{i}") for i in range(50)]
    aux_ids = [(f"a{i}", f"보조카페{i}") for i in range(9)]
    state17 = {}
    for pid, name in main_ids + aux_ids:
        state17[f"PlaceListBusinessesItem:{pid}:{pid}"] = _item_entity(pid, name=name)
    state17["ROOT_QUERY"] = {
        _op_key("placeList", {"query": query, "start": start, "display": 70}): {
            "businesses": {"items": [_ref(f"PlaceListBusinessesItem:{pid}:{pid}") for pid, _ in main_ids]}
        },
        _op_key("placeList", {"query": query, "start": start, "filterOpening": True, "display": 9}): {
            "businesses": {"items": [_ref(f"PlaceListBusinessesItem:{pid}:{pid}") for pid, _ in aux_ids]}
        },
    }
    result17 = extract_main_place_list_from_apollo(state17, query, start)
    if result17["error"] == "" and len(result17["items"]) == 50:
        reporter.pass_("17. main 50개 + auxiliary 9개 동시 존재 시 main만 선택(하드코딩 없이 상대 크기로 판단) 성공")
    else:
        reporter.fail(f"17. main+aux 동시 존재 처리 실패: len={len(result17['items'])}, error={result17['error']}")

    # 18. auxiliary가 ROOT_QUERY 순서상 먼저 나와도(main이 나중) 결과는 동일해야 한다.
    state18_aux_first = {}
    for pid, name in aux_ids + main_ids:
        state18_aux_first[f"PlaceListBusinessesItem:{pid}:{pid}"] = _item_entity(pid, name=name)
    state18_aux_first["ROOT_QUERY"] = {
        _op_key("placeList", {"query": query, "start": start, "filterOpening": True, "display": 9}): {
            "businesses": {"items": [_ref(f"PlaceListBusinessesItem:{pid}:{pid}") for pid, _ in aux_ids]}
        },
        _op_key("placeList", {"query": query, "start": start, "display": 70}): {
            "businesses": {"items": [_ref(f"PlaceListBusinessesItem:{pid}:{pid}") for pid, _ in main_ids]}
        },
    }
    result18 = extract_main_place_list_from_apollo(state18_aux_first, query, start)
    if result18["error"] == "" and len(result18["items"]) == 50:
        reporter.pass_("18. auxiliary가 먼저, main이 나중이어도 순서와 무관하게 main 선택 성공")
    else:
        reporter.fail(f"18. aux-먼저 순서 처리 실패: len={len(result18['items'])}, error={result18['error']}")

    # 19. 동일 apollo_state(response)를 반복 처리해도 결과가 불변(idempotent)해야 한다.
    result19_first = extract_main_place_list_from_apollo(state17, query, start)
    result19_second = extract_main_place_list_from_apollo(state17, query, start)
    ids19_first = [i.get("id") for i in result19_first["items"]]
    ids19_second = [i.get("id") for i in result19_second["items"]]
    if ids19_first == ids19_second and result19_first["selected_operation_key"] == result19_second["selected_operation_key"]:
        reporter.pass_("19. 동일 response 반복 처리 시 결과 불변(idempotent) 성공")
    else:
        reporter.fail(f"19. idempotent 검증 실패: first={ids19_first}, second={ids19_second}")

    # 20. 첫 번째 후보를 강제로 선택하는 구현으로 되돌아가면 실패해야 하는
    # 회귀 가드: auxiliary가 ROOT_QUERY의 첫 번째 key이고 main이 두 번째일 때
    # "첫 번째 채택" 정책이면 9개(aux)가 선택되지만, 올바른 구현은 50개
    # (main)를 선택해야 한다.
    if len(result18["items"]) != 9:
        reporter.pass_("20. 첫 번째 placeList 강제 채택 회귀 가드 통과(9개 aux를 채택하지 않음)")
    else:
        reporter.fail(f"20. 첫 번째 placeList 강제 채택으로 회귀함: {result18}")

    print("\n====================")
    print(f"PASS: {reporter.passes}")
    print(f"FAIL: {reporter.fails}")
    print("====================")
    return reporter.fails == 0


def test_apollo_list_adapter_suite():
    assert _run_apollo_list_adapter_suite() is True


if __name__ == "__main__":
    success = _run_apollo_list_adapter_suite()
    sys.exit(0 if success else 1)
