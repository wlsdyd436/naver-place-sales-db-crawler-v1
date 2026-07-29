# GraphQL-first 두 모드(기본/홈페이지·SNS 포함) production 목록 수집 경로의 1페이지
# 파서. window.__APOLLO_STATE__의 ROOT_QUERY에서 "현재 검색어와 일치하는 메인
# placeList(...) operation" 하나만 선택하고 businesses.items의 __ref만 따라간다.
#
# 이 모듈은 기존 DomMembershipCollector/collect_dom_membership_query(DOM 풀스크롤 +
# Apollo + Network 3중 병합, network_browser_collector.py)를 대체하지 않는다 -
# 그 경로는 무수정으로 보존되며, 이 모듈은 사용자가 명시적으로 승인한 신규
# Apollo/GraphQL-first 경로(ApolloFirstListCollector)만을 위해 존재한다.
#
# 알려진 미검증 가정(Live 검증 전까지 문서로만 남김 - 이번 구현 단계는 Live 요청을
# 실행하지 않는다): placeList(...) 키의 정확한 input 필드명(query/filterOpening/
# start/display)은 이 저장소에 이미 증명된 유일한 유사 패턴인
# placeDetail({"input":{"deviceType":"mobile","id":"...","isNx":false}})
# (extract_normalized_apollo_detail, network_list_scraper.py)의 "fieldName(JSON)"
# 키 형태와 사용자 요청서 문구에서 추론한 것이다. 실제 리스트 페이지의
# window.__APOLLO_STATE__ 원본 fixture로 아직 검증되지 않았다.
import json
import re

from src.pc.network_list_scraper import _map_item_to_row

_ROOT_QUERY_KEY = "ROOT_QUERY"
_PLACE_LIST_PREFIX = "placeList("


def _parse_operation_args(key, prefix: str):
    """key가 prefix로 시작하고 ")"로 끝나면 그 사이의 JSON을 파싱해 반환한다.
    형식이 맞지 않거나 JSON이 아니면 예외를 던지지 않고 None을 반환한다."""
    if not isinstance(key, str) or not key.startswith(prefix) or not key.endswith(")"):
        return None
    args_text = key[len(prefix):-1]
    try:
        parsed = json.loads(args_text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _resolve_ref(apollo_state: dict, value):
    """value가 {"__ref": key} 형태면 apollo_state[key]를 1단계만 해석해 반환한다.
    이미 dict(inline)이면 그대로 반환한다. 그 외(None/list/스칼라 등)는 None.
    무제한 재귀를 하지 않는다(network_list_scraper._select_apollo_parent와 동일한
    '1단계만 해석' 원칙)."""
    if not isinstance(value, dict):
        return None
    ref = value.get("__ref")
    if isinstance(ref, str) and "__ref" in value:
        resolved = apollo_state.get(ref)
        return resolved if isinstance(resolved, dict) else None
    return value


def _empty_result(error: str) -> dict:
    return {
        "available": False,
        "error": error,
        "selected_operation_key": None,
        "candidate_operation_keys": [],
        "excluded_operation_keys": [],
        "items": [],
        "item_refs": [],
        "missing_ref_count": 0,
        "missing_refs": [],
        "selection_diagnostics": {"candidates_scored": [], "chosen_key": None},
    }


def _normalize_query_for_compare(text) -> str:
    """비교용 - 공백만 제거한다(exact match를 요구하지 않고 유사도 신호로만
    쓰기 위함 - 요청서 §7 "문자열 완전일치에만 의존하지 않음")."""
    return re.sub(r"\s+", "", str(text or "").strip())


def _query_similarity_score(candidate_query, expected_query) -> float:
    """공백 제거 후 완전 일치=1.0, 한쪽이 다른 쪽의 부분 문자열이면(공백·행정
    구역 축약 차이 허용)=0.7, 그 외(빈 값 포함)=0.0. 이 점수만으로 후보를
    배제하지 않는다 - size(유효 item 개수)가 1순위 신호이고 이건 동점 상황의
    보조 신호일 뿐이다."""
    a = _normalize_query_for_compare(candidate_query)
    b = _normalize_query_for_compare(expected_query)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.7
    return 0.0


def extract_main_place_list_from_apollo(apollo_state, expected_query: str, expected_start: int = 0) -> dict:
    """ROOT_QUERY에서 현재 검색어의 메인 placeList(...) operation 하나만
    안전하게 선택한다(2026-07-25 field parity 보정 - "query/start가 정확히
    일치하지 않으면 후보[0]를 강제 채택"하던 핫픽스를 제거하고, 구조적 신호
    (유효 item 개수)를 1순위로, query/start 일치는 동점을 가릴 때만 참고하는
    스코어링 방식으로 교체했다 - 요청서 §7).

    선택 절차:
      1) ROOT_QUERY의 key 중 "placeList(" 접두사 + JSON 파싱 성공만 후보로
         삼는다.
      2) input.filterOpening is True 또는 input.display == 9인 후보는
         제외한다(필터용/새로오픈 전용 보조 query 오염 차단 - 기존 로직 유지).
      3) 남은 각 후보의 businesses.items를 실제로 해석해본다 - 구조적으로
         무효(list가 아님)면 스코어링 대상에서 제외한다(reason=
         "businesses_items_missing").
      4) 구조적으로 유효한 후보가 정확히 1개면 그대로 채택한다 - query/start
         문자열이 기대와 달라도, filterOpening/display=9 aux를 이미
         제외했다면 남은 유일한 후보가 메인이라는 뜻이므로 문자열 완전일치
         실패만으로 전체를 실패 처리하지 않는다.
      5) 2개 이상이면 (size=유효 item 개수, query_score, start_score)를
         내림차순으로 정렬해 최고점을 채택한다. size를 1순위로 쓰는 이유:
         실측상 메인 목록은 항상 보조 목록보다 훨씬 크다(§0/§3 근거) - 절대
         개수(예: 70)를 하드코딩하지 않고 후보 간 상대 크기만 신호로 쓴다.
      6) 최고점이 동점인 후보가 여럿이고 그 후보들의 유효 place_id 집합이
         서로 다르면 임의로 하나를 고르지 않고 "ambiguous_placelist_operation"
         오류를 반환한다(요청서 §7 금지 사항 - 모호한 후보 조용히 선택 금지).
         동점이지만 ID 집합이 같으면(같은 목록의 중복 표현) 안전하게 하나를
         채택한다.
      7) 선택된 값과 businesses 필드를 각각 1단계만 __ref 해석하고, items의
         각 원소도 1단계 __ref 해석해 존재하는 것만 원래 순서대로 반환한다
         (존재하지 않는 __ref는 missing_refs에 기록하고 스킵 - 예외 없음,
         조용한 무시도 아님).

    반환에 신규 "selection_diagnostics" 키를 추가한다(각 후보의 key/size/
    query_score/start_score/unique_id_count + 최종 선택 key, 요청서 §7
    "선택 근거를 diagnostics에 기록") - 기존 키는 전부 그대로 유지되므로
    호출부(network_browser_collector._wait_for_apollo_list_ready)는 무수정
    호환된다."""
    if not isinstance(apollo_state, dict):
        return _empty_result("apollo_state_missing")

    root_query = apollo_state.get(_ROOT_QUERY_KEY)
    if not isinstance(root_query, dict):
        result = _empty_result("root_query_missing")
        result["available"] = True
        return result

    candidate_operation_keys = [
        key for key in root_query if isinstance(key, str) and key.startswith(_PLACE_LIST_PREFIX)
    ]
    if not candidate_operation_keys:
        result = _empty_result("no_placelist_operation_found")
        result["available"] = True
        return result

    excluded_operation_keys = []
    scored_candidates = []
    for key in candidate_operation_keys:
        parsed = _parse_operation_args(key, _PLACE_LIST_PREFIX)
        if parsed is None:
            excluded_operation_keys.append({"key": key, "reason": "parse_error"})
            continue
        input_obj = parsed.get("input") if isinstance(parsed.get("input"), dict) else parsed

        if input_obj.get("filterOpening") is True:
            excluded_operation_keys.append({"key": key, "reason": "filterOpening_true"})
            continue
        if input_obj.get("display") == 9:
            excluded_operation_keys.append({"key": key, "reason": "display_9"})
            continue

        resolved = _resolve_ref(apollo_state, root_query.get(key))
        businesses = _resolve_ref(apollo_state, resolved.get("businesses")) if isinstance(resolved, dict) else None
        items_refs = businesses.get("items") if isinstance(businesses, dict) else None
        if not isinstance(items_refs, list):
            excluded_operation_keys.append({"key": key, "reason": "businesses_items_missing"})
            continue

        resolved_items: list = []
        item_refs: list = []
        missing_refs: list = []
        unique_ids: set = set()
        for entry in items_refs:
            entity = _resolve_ref(apollo_state, entry)
            ref = entry.get("__ref") if isinstance(entry, dict) else None
            if entity is None:
                if isinstance(ref, str):
                    missing_refs.append(ref)
                continue
            resolved_items.append(entity)
            if isinstance(ref, str):
                item_refs.append(ref)
            entity_id = entity.get("id")
            if entity_id is not None:
                unique_ids.add(str(entity_id))

        query_score = _query_similarity_score(input_obj.get("query"), expected_query)
        start_value = input_obj.get("start")
        if start_value == expected_start:
            start_score = 1.0
        elif "start" not in input_obj:
            start_score = 0.5
        else:
            start_score = 0.0

        scored_candidates.append({
            "key": key,
            "items": resolved_items,
            "item_refs": item_refs,
            "missing_refs": missing_refs,
            "unique_id_count": len(unique_ids),
            "id_set": frozenset(unique_ids),
            "size": len(resolved_items),
            "query_score": query_score,
            "start_score": start_score,
        })

    if not scored_candidates:
        only_structural_failures = bool(excluded_operation_keys) and all(
            entry["reason"] in ("businesses_items_missing", "parse_error") for entry in excluded_operation_keys
        )
        error = "businesses_items_missing" if only_structural_failures else "no_matching_placelist_operation"
        result = _empty_result(error)
        result["available"] = True
        result["candidate_operation_keys"] = candidate_operation_keys
        result["excluded_operation_keys"] = excluded_operation_keys
        return result

    diagnostics_candidates = [
        {
            "key": c["key"], "size": c["size"], "query_score": c["query_score"],
            "start_score": c["start_score"], "unique_id_count": c["unique_id_count"],
        }
        for c in scored_candidates
    ]

    if len(scored_candidates) == 1:
        chosen = scored_candidates[0]
    else:
        ranked = sorted(
            scored_candidates,
            key=lambda c: (c["size"], c["query_score"], c["start_score"]),
            reverse=True,
        )
        best = ranked[0]
        tied = [
            c for c in ranked
            if c["size"] == best["size"] and c["query_score"] == best["query_score"] and c["start_score"] == best["start_score"]
        ]
        if len(tied) > 1 and len({c["id_set"] for c in tied}) > 1:
            result = _empty_result("ambiguous_placelist_operation")
            result["available"] = True
            result["candidate_operation_keys"] = candidate_operation_keys
            result["excluded_operation_keys"] = excluded_operation_keys
            result["selection_diagnostics"] = {"candidates_scored": diagnostics_candidates, "chosen_key": None}
            return result
        chosen = ranked[0]

    return {
        "available": True,
        "error": "",
        "selected_operation_key": chosen["key"],
        "candidate_operation_keys": candidate_operation_keys,
        "excluded_operation_keys": excluded_operation_keys,
        "items": chosen["items"],
        "item_refs": chosen["item_refs"],
        "missing_ref_count": len(chosen["missing_refs"]),
        "missing_refs": chosen["missing_refs"],
        "selection_diagnostics": {"candidates_scored": diagnostics_candidates, "chosen_key": chosen["key"]},
    }


def extract_new_opening_place_list_from_apollo(apollo_state, expected_query: str, expected_start: int = 0) -> dict:
    """새로오픈 전용 placeList(...) operation만 선택한다(NEW-OPENING-1).

    2026-07-30 Live 실측(scratchpad/new_opening_filter_implementation)으로
    확인한 사실: 새로오픈 전용 operation은 input.filterOpening이 Python
    bool True가 아니라 문자열 "true"로 온다(둘 다 인정). 이 operation은
    page 1 Apollo state에 메인 목록과 함께 이미 존재하며, 별도의 "필터
    토글 클릭" 없이도 나타난다(실측 확인) - 이 함수는 페이지 로드만으로
    이미 채워진 이 candidate를 찾아 선택하는 역할만 한다. 실측상 이
    candidate는 항상 display=9였지만, display 값 자체를 선택 조건으로
    쓰지 않는다(filterOpening 조건만으로 판별 - 요청서 §6).

    선택 절차는 extract_main_place_list_from_apollo와 같은 원칙(구조적
    유효성 우선, query/start는 동점 처리용 보조 신호, 모호하면
    "ambiguous_placelist_operation" 오류)을 따르되 후보 조건이 정반대라
    별도 함수로 둔다(그 함수를 필터 조건만 반전시켜 재사용하도록 리팩터링
    하면 이미 여러 테스트로 굳어진 기존 로직을 건드리는 위험이 커서
    피했다 - ponytail: 이 두 함수의 스코어링 루프는 의도적으로 중복
    허용, 통합은 더 넓은 회귀 범위에서 재검토).

    전용 목록을 하나도 찾지 못하면 "no_new_opening_operation_found" 오류를
    반환한다 - 일반 목록으로 조용히 대체하지 않는다(호출자가 명확한 오류로
    처리해야 함, §6 금지 사항)."""
    if not isinstance(apollo_state, dict):
        return _empty_result("apollo_state_missing")

    root_query = apollo_state.get(_ROOT_QUERY_KEY)
    if not isinstance(root_query, dict):
        result = _empty_result("root_query_missing")
        result["available"] = True
        return result

    candidate_operation_keys = [
        key for key in root_query if isinstance(key, str) and key.startswith(_PLACE_LIST_PREFIX)
    ]
    if not candidate_operation_keys:
        result = _empty_result("no_placelist_operation_found")
        result["available"] = True
        return result

    excluded_operation_keys = []
    scored_candidates = []
    for key in candidate_operation_keys:
        parsed = _parse_operation_args(key, _PLACE_LIST_PREFIX)
        if parsed is None:
            excluded_operation_keys.append({"key": key, "reason": "parse_error"})
            continue
        input_obj = parsed.get("input") if isinstance(parsed.get("input"), dict) else parsed

        if input_obj.get("filterOpening") not in (True, "true"):
            excluded_operation_keys.append({"key": key, "reason": "not_filter_opening"})
            continue

        resolved = _resolve_ref(apollo_state, root_query.get(key))
        businesses = _resolve_ref(apollo_state, resolved.get("businesses")) if isinstance(resolved, dict) else None
        items_refs = businesses.get("items") if isinstance(businesses, dict) else None
        if not isinstance(items_refs, list):
            excluded_operation_keys.append({"key": key, "reason": "businesses_items_missing"})
            continue

        resolved_items: list = []
        item_refs: list = []
        missing_refs: list = []
        unique_ids: set = set()
        for entry in items_refs:
            entity = _resolve_ref(apollo_state, entry)
            ref = entry.get("__ref") if isinstance(entry, dict) else None
            if entity is None:
                if isinstance(ref, str):
                    missing_refs.append(ref)
                continue
            resolved_items.append(entity)
            if isinstance(ref, str):
                item_refs.append(ref)
            entity_id = entity.get("id")
            if entity_id is not None:
                unique_ids.add(str(entity_id))

        query_score = _query_similarity_score(input_obj.get("query"), expected_query)
        start_value = input_obj.get("start")
        if start_value == expected_start:
            start_score = 1.0
        elif "start" not in input_obj:
            start_score = 0.5
        else:
            start_score = 0.0

        scored_candidates.append({
            "key": key,
            "items": resolved_items,
            "item_refs": item_refs,
            "missing_refs": missing_refs,
            "unique_id_count": len(unique_ids),
            "id_set": frozenset(unique_ids),
            "size": len(resolved_items),
            "query_score": query_score,
            "start_score": start_score,
        })

    if not scored_candidates:
        only_structural_failures = bool(excluded_operation_keys) and all(
            entry["reason"] in ("businesses_items_missing", "parse_error") for entry in excluded_operation_keys
        )
        error = "businesses_items_missing" if only_structural_failures else "no_new_opening_operation_found"
        result = _empty_result(error)
        result["available"] = True
        result["candidate_operation_keys"] = candidate_operation_keys
        result["excluded_operation_keys"] = excluded_operation_keys
        return result

    diagnostics_candidates = [
        {
            "key": c["key"], "size": c["size"], "query_score": c["query_score"],
            "start_score": c["start_score"], "unique_id_count": c["unique_id_count"],
        }
        for c in scored_candidates
    ]

    if len(scored_candidates) == 1:
        chosen = scored_candidates[0]
    else:
        ranked = sorted(
            scored_candidates,
            key=lambda c: (c["size"], c["query_score"], c["start_score"]),
            reverse=True,
        )
        best = ranked[0]
        tied = [
            c for c in ranked
            if c["size"] == best["size"] and c["query_score"] == best["query_score"] and c["start_score"] == best["start_score"]
        ]
        if len(tied) > 1 and len({c["id_set"] for c in tied}) > 1:
            result = _empty_result("ambiguous_placelist_operation")
            result["available"] = True
            result["candidate_operation_keys"] = candidate_operation_keys
            result["excluded_operation_keys"] = excluded_operation_keys
            result["selection_diagnostics"] = {"candidates_scored": diagnostics_candidates, "chosen_key": None}
            return result
        chosen = ranked[0]

    return {
        "available": True,
        "error": "",
        "selected_operation_key": chosen["key"],
        "candidate_operation_keys": candidate_operation_keys,
        "excluded_operation_keys": excluded_operation_keys,
        "items": chosen["items"],
        "item_refs": chosen["item_refs"],
        "missing_ref_count": len(chosen["missing_refs"]),
        "missing_refs": chosen["missing_refs"],
        "selection_diagnostics": {"candidates_scored": diagnostics_candidates, "chosen_key": chosen["key"]},
    }


def build_rows_from_apollo_list_result(list_result: dict, collected_at: str, *, source_query: str = None) -> list:
    """extract_main_place_list_from_apollo의 items를 network_list_scraper._map_item_to_row로
    순서 보존 매핑한다(순수 함수 - source_page/source_city 등은 호출자가 이후 붙인다,
    collect_network_query가 이미 쓰는 패턴과 동일)."""
    rows = []
    for item in list_result.get("items") or []:
        if not isinstance(item, dict):
            continue
        rows.append(_map_item_to_row(item, collected_at, source_query=source_query))
    return rows
