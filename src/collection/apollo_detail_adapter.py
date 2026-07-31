"""Apollo State의 Place Base/Parent entity를 해석한다. place_id와 정확히
일치하는 entity만 선택하며, 공통 row 필드 변환은 place_mapper의 기존
helper를 재사용한다. 네트워크·브라우저 요청을 수행하지 않는 순수 Adapter다."""
from src.collection.place_mapper import _DIGIT_ONLY_PATTERN, _normalize_text

# ============================================================================
# 5O(2026-07-23): Apollo State 정규화 엔티티 adapter. 상세 페이지 방문 시
# window.__APOLLO_STATE__에 채워지는 `PlaceDetailBase:{id}`(base)와 ROOT_QUERY의
# `placeDetail({"input":{...}})`(parent)를 exact place_id/`__ref` 기준으로만
# 결합해 기존 `_map_item_to_row()`가 소비할 수 있는 flat dict로 변환한다.
# 5O 감사(scratchpad/page300_5o_real_apollo_parser_integration_audit)의
# joined_entity_replay_results.json이 이 결합 방식으로 5/5 raw 표본 정확히
# 일치함을 확인했다. 리뷰 합산/URL 분류/전화 필터는 여기서 만들지 않고 그대로
# place_mapper._map_item_to_row에 위임한다(중복 구현 금지).
# ============================================================================

_APOLLO_BASE_KEY_PREFIX = "PlaceDetailBase:"
_APOLLO_ROOT_QUERY_KEY = "ROOT_QUERY"
_APOLLO_PARENT_KEY_TOKEN = "placeDetail("
_APOLLO_BASE_FIELDS = (
    "id", "name", "category", "roadAddress", "address", "commonAddress", "phone", "virtualPhone",
    "visitorReviewsTotal", "cafeBlogReviewsTotal", "naverBlog",
)
# homepages는 bare key가 아닐 수 있어 _resolve_homepages로 따로 찾는다.
_APOLLO_PARENT_FIELDS = ("newOpening", "phoneInfo")
_APOLLO_HOMEPAGES_FIELD = "homepages"
# 2026-07-31 Live 실측: parent entity는 homepages를 bare key가 아니라 GraphQL
# 인자가 포함된 key로 담는다(같은 값의 사본이 parent["shopWindow"]["homepages"]
# 에도 있다). bare key만 읽던 기존 구현은 URL이 실제로 존재하는 업체에서도
# homepages를 통째로 놓쳐 홈페이지/인스타/블로그/추가 링크가 항상 공란이 됐다.
_APOLLO_HOMEPAGES_CANONICAL_KEY = 'homepages({"source":["shopWindow","jto"]})'
_APOLLO_HOMEPAGES_KEY_PREFIX = "homepages("


def _resolve_homepages(parent: dict):
    """parent에서 Apollo Homepage dict를 찾는다(없으면 None).

    bare key -> 현재 canonical 인자 key -> 그 외 "homepages(" 인자 key ->
    shopWindow 중첩 순으로 "먼저 찾은 하나"만 채택한다. 여러 source의 결과를
    병합하지 않고 Apollo tree 전체를 재귀 탐색하지도 않는다(값 해석·URL 분류는
    place_mapper._extract_external_urls의 책임 그대로). etc=[]/repr=None인
    Homepage dict도 "링크가 없다"는 유효한 구조이므로 그대로 채택한다."""
    for key in (_APOLLO_HOMEPAGES_FIELD, _APOLLO_HOMEPAGES_CANONICAL_KEY):
        value = parent.get(key)
        if isinstance(value, dict):
            return value

    for key, value in parent.items():
        if isinstance(key, str) and key.startswith(_APOLLO_HOMEPAGES_KEY_PREFIX) and isinstance(value, dict):
            return value

    shop_window = parent.get("shopWindow")
    if isinstance(shop_window, dict):
        value = shop_window.get(_APOLLO_HOMEPAGES_FIELD)
        if isinstance(value, dict):
            return value
    return None


def _select_apollo_parent(apollo_state: dict, base_key: str, normalized_id: str):
    """ROOT_QUERY에서 base_key를 exact 참조하는 parent PlaceDetail entity를
    선택한다. 후보 key는 "placeDetail(" 토큰과 quoted place_id를 모두 포함해야
    하며, 값이 `{"__ref": "..."}` 형태면 apollo_state에서 딱 1단계만 해석한다
    (무제한 traversal/순환 참조 방지 - 그 이상 재귀하지 않음). exact
    `base.__ref == base_key`인 후보가 정확히 1개일 때만 채택하고, 0개나
    충돌(2개 이상)이면 None을 반환해 parent를 사용하지 않는다(임의 선택 금지,
    stale entity가 섞여 있어도 exact 조건으로 자동 배제됨)."""
    root_query = apollo_state.get(_APOLLO_ROOT_QUERY_KEY)
    if not isinstance(root_query, dict):
        return None

    quoted_id = f'"{normalized_id}"'
    exact_matches = []
    for key, value in root_query.items():
        if not isinstance(key, str) or _APOLLO_PARENT_KEY_TOKEN not in key or quoted_id not in key:
            continue

        candidate = value
        if isinstance(candidate, dict) and isinstance(candidate.get("__ref"), str) and "__ref" in candidate:
            resolved = apollo_state.get(candidate["__ref"])
            candidate = resolved if isinstance(resolved, dict) else None

        if not isinstance(candidate, dict):
            continue
        base_ref_obj = candidate.get("base")
        if not isinstance(base_ref_obj, dict) or base_ref_obj.get("__ref") != base_key:
            continue
        exact_matches.append(candidate)

    if len(exact_matches) == 1:
        return exact_matches[0]
    return None


def extract_normalized_apollo_detail(apollo_state, place_id) -> dict:
    """Apollo State 정규화 캐시에서 place_id에 해당하는 PlaceDetailBase(base)와
    exact 일치하는 parent PlaceDetail을 결합해 flat dict를 반환한다.

    입력 검증(요청서 §4): apollo_state가 dict가 아니면 {}, place_id가 숫자
    형식이 아니면 {}, base entity가 없거나 dict가 아니면 {}, base entity의
    id가 존재하는데 요청 place_id와 다르면 {}(다른 업체 데이터 차단). Parent가
    없어도 base만 있으면 base 필드만 반환한다.

    반환값은 새 dict이며 원본 apollo_state/entity를 mutate하지 않는다(필요한
    필드만 복사). Apollo State 전체나 무관한 entity를 반환하지 않는다.

    homepages만 bare key가 아닐 수 있어 _resolve_homepages로 찾고, 찾은 값은
    항상 bare "homepages" 키로 normalize해 담는다(호출부 place_mapper.
    _extract_external_urls는 무수정 재사용)."""
    if not isinstance(apollo_state, dict):
        return {}

    normalized_id = _normalize_text(place_id)
    if not _DIGIT_ONLY_PATTERN.match(normalized_id):
        return {}

    base_key = f"{_APOLLO_BASE_KEY_PREFIX}{normalized_id}"
    base_entity = apollo_state.get(base_key)
    if not isinstance(base_entity, dict):
        return {}

    base_id = base_entity.get("id")
    if base_id not in (None, "") and _normalize_text(base_id) != normalized_id:
        return {}

    result: dict = {}
    for field in _APOLLO_BASE_FIELDS:
        if field in base_entity:
            result[field] = base_entity[field]
    result["id"] = normalized_id

    parent = _select_apollo_parent(apollo_state, base_key, normalized_id)
    if isinstance(parent, dict):
        for field in _APOLLO_PARENT_FIELDS:
            if field in parent:
                result[field] = parent[field]
        homepages = _resolve_homepages(parent)
        if homepages is not None:
            result[_APOLLO_HOMEPAGES_FIELD] = homepages

    return result
