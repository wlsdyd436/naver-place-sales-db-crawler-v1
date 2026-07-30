"""단위 테스트: src/collection/apollo_list_adapter.extract_new_opening_place_list_from_apollo
(NEW-OPENING-1 §9-C operation 선택 규칙). 2026-07-30 Live 실측
(scratchpad/new_opening_filter_implementation)에서 확인된 실제 필드 형태
(filterOpening="true" 문자열, display=9)를 그대로 반영한 합성 fixture만
사용한다."""
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collection.apollo_list_adapter import (  # noqa: E402
    extract_main_place_list_from_apollo,
    extract_new_opening_place_list_from_apollo,
)

QUERY = "서울특별시 강동구 천호동 카페"


def _op_key(prefix: str, input_obj: dict) -> str:
    return f"{prefix}({json.dumps({'input': input_obj})})"


def _ref(key: str) -> dict:
    return {"__ref": key}


def _entity(place_id: str, *, new_opening=None) -> dict:
    entity = {"id": place_id, "name": f"업체{place_id}", "category": "카페"}
    if new_opening is not None:
        entity["newOpening"] = new_opening
    return entity


def _state_with(main_ids, new_opening_ids, *, filter_opening_value="true", extra_root_query=None):
    state = {}
    for pid in set(main_ids) | set(new_opening_ids):
        state[f"PlaceListBusinessesItem:{pid}:{pid}"] = _entity(pid, new_opening=(pid in new_opening_ids))
    root_query = {
        _op_key("placeList", {"query": QUERY, "start": 1, "display": 70}): {
            "businesses": {"items": [_ref(f"PlaceListBusinessesItem:{pid}:{pid}") for pid in main_ids]}
        },
        _op_key("placeList", {"query": QUERY, "start": 1, "display": 9, "filterOpening": filter_opening_value}): {
            "businesses": {"items": [_ref(f"PlaceListBusinessesItem:{pid}:{pid}") for pid in new_opening_ids]}
        },
    }
    if extra_root_query:
        root_query.update(extra_root_query)
    state["ROOT_QUERY"] = root_query
    return state


def test_new_opening_selector_picks_filter_opening_string_true():
    state = _state_with(main_ids=["1", "2", "3"], new_opening_ids=["10", "11"], filter_opening_value="true")
    result = extract_new_opening_place_list_from_apollo(state, QUERY, 1)
    assert result["error"] == ""
    ids = sorted(i["id"] for i in result["items"])
    assert ids == ["10", "11"]


def test_new_opening_selector_picks_filter_opening_bool_true():
    state = _state_with(main_ids=["1", "2"], new_opening_ids=["10"], filter_opening_value=True)
    result = extract_new_opening_place_list_from_apollo(state, QUERY, 1)
    assert result["error"] == ""
    assert [i["id"] for i in result["items"]] == ["10"]


def test_new_opening_selector_excludes_false_string_filter_opening():
    """filterOpening="false"(다른 필터 조합의 후보)는 선택 대상이 아니다."""
    state = _state_with(main_ids=["1"], new_opening_ids=["10"], filter_opening_value="false")
    result = extract_new_opening_place_list_from_apollo(state, QUERY, 1)
    assert result["error"] == "no_new_opening_operation_found"
    assert result["items"] == []


def test_main_selector_still_excludes_filter_opening_candidate():
    """OFF 경로(extract_main_place_list_from_apollo)는 기존 그대로 filterOpening
    후보를 배제하고 메인 목록만 선택해야 한다(회귀 없음)."""
    state = _state_with(main_ids=["1", "2", "3"], new_opening_ids=["10", "11"], filter_opening_value="true")
    result = extract_main_place_list_from_apollo(state, QUERY, 1)
    assert result["error"] == ""
    ids = sorted(i["id"] for i in result["items"])
    assert ids == ["1", "2", "3"]


def test_new_opening_selector_ignores_ad_businesses_operation():
    """adBusinesses(...) 같은 placeList가 아닌 operation은 애초에 후보로
    잡히지 않는다(prefix 자체가 다름)."""
    state = _state_with(main_ids=["1"], new_opening_ids=["10"], filter_opening_value="true")
    state["ROOT_QUERY"][_op_key("adBusinesses", {"query": QUERY})] = {
        "businesses": {"items": [_ref("PlaceListBusinessesItem:99:99")]}
    }
    state["PlaceListBusinessesItem:99:99"] = _entity("99", new_opening=True)
    result = extract_new_opening_place_list_from_apollo(state, QUERY, 1)
    assert result["error"] == ""
    assert [i["id"] for i in result["items"]] == ["10"]
    assert all("adBusinesses" not in c["key"] for c in result["selection_diagnostics"]["candidates_scored"])


def test_new_opening_selector_no_candidate_found_returns_explicit_error_not_fallback():
    """새로오픈 전용 placeList가 아예 없으면(예: 페이지에 메인 목록만 있는
    경우) 일반 목록으로 조용히 대체하지 않고 명시적 오류를 반환해야 한다."""
    state = {
        "PlaceListBusinessesItem:1:1": _entity("1"),
        "ROOT_QUERY": {
            _op_key("placeList", {"query": QUERY, "start": 1, "display": 70}): {
                "businesses": {"items": [_ref("PlaceListBusinessesItem:1:1")]}
            },
        },
    }
    result = extract_new_opening_place_list_from_apollo(state, QUERY, 1)
    assert result["error"] == "no_new_opening_operation_found"
    assert result["items"] == []


def test_new_opening_selector_multiple_filter_opening_candidates_picks_largest_valid():
    """filterOpening 조건에 맞는 candidate가 여럿이면(비정상 상황이지만
    방어적으로) 구조적으로 유효한 것 중 크기가 큰 후보를 선택한다 - 기존
    메인 선택 로직과 동일한 스코어링 원칙."""
    state = _state_with(main_ids=["1"], new_opening_ids=["10", "11"], filter_opening_value="true")
    # 두 번째 filterOpening candidate(더 작은 size)를 추가한다.
    state["PlaceListBusinessesItem:20:20"] = _entity("20", new_opening=True)
    state["ROOT_QUERY"][_op_key("placeList", {"query": QUERY, "start": 1, "display": 9, "filterOpening": "true", "tag": "dup"})] = {
        "businesses": {"items": [_ref("PlaceListBusinessesItem:20:20")]}
    }
    result = extract_new_opening_place_list_from_apollo(state, QUERY, 1)
    assert result["error"] == ""
    ids = sorted(i["id"] for i in result["items"])
    assert ids == ["10", "11"]


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
