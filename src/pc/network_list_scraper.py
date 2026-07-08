# ARCH-300 PoC-1: 브라우저 네트워크 응답 관찰 기반 업체 리스트 수집(기술 검증 단계).
#
# 이 모듈은 "직접 API를 호출"하지 않는다. Playwright 브라우저가 검색 결과 화면을
# 정상적으로 렌더링하는 과정에서 자연히 발생시키는 Network response(xhr/fetch)를
# 관찰(observe)하여, 그 응답에 이미 담겨 있는 업체 리스트 데이터를 파싱만 한다.
# CAPTCHA 우회/자동 해결/stealth/proxy/무단 반복 호출은 이 모듈의 목적이 아니며
# 시도하지 않는다.
#
# 아직 PoC-1 단계이므로 이 모듈은 UI(src/ui.py)나 pipeline(src/pc/pipeline.py)에
# 연결되지 않는다. 순수 함수(파서/매퍼/필터/dedup)만 제공하며, 실제 Playwright
# page/response 객체를 다루는 코드(리스너 등록 등)는 scratchpad의 PoC 스크립트가
# 담당한다 - 이렇게 분리해야 이 모듈을 live 브라우저 없이 fixture만으로 테스트할
# 수 있다.
#
# 네이버 내부 응답의 JSON 구조는 비공식/미문서화이며 사전 예고 없이 바뀔 수 있다.
# 따라서 모든 파싱은 방어적으로 작성한다: 알려진 경로를 우선 시도하고, 실패하면
# 휴리스틱으로 재귀 탐색하며, 그래도 실패하면 예외를 던지지 않고 빈 값을 반환한다.

_CANDIDATE_RESOURCE_TYPES = ("xhr", "fetch")

# URL에 포함되면 "업체 리스트를 담고 있을 가능성이 있는 응답"으로 간주하는 토큰 후보.
# 확장 포인트: PoC live 관찰 결과 새로운 엔드포인트 패턴이 발견되면 이 튜플에 추가한다.
# (이 토큰은 "관찰 대상을 넓히는" 용도일 뿐, 이 토큰으로 직접 URL을 만들어 요청하지 않는다.)
_CANDIDATE_URL_TOKENS = (
    "allsearch",
    "graphql",
    "search/instant",
    "place/list",
    "pcmap",
)


def is_candidate_response(url: str, resource_type: str) -> bool:
    """Playwright page.on("response") 핸들러에서 사용할 후보 응답 판별 함수.

    입력: 응답 URL과 Playwright의 request.resource_type("xhr"/"fetch"/"document" 등).
    출력: 이 응답이 업체 리스트를 담고 있을 가능성이 있는 "후보"인지 여부(bool).

    resource_type이 xhr/fetch이고 URL에 후보 토큰이 하나라도 포함되어야 후보로
    본다. URL만으로는 오탐이 있을 수 있으므로, 실제 리스트 존재 여부는 이 함수가
    아니라 _extract_list_items가 JSON 내용을 보고 별도로 판단한다(이중 방어).
    """
    if resource_type not in _CANDIDATE_RESOURCE_TYPES:
        return False
    if not url:
        return False
    lowered = url.lower()
    return any(token in lowered for token in _CANDIDATE_URL_TOKENS)


# 업체 항목(item)으로 추정하기 위한 식별자/이름 키 후보.
# 확장 포인트: 실제 응답에서 다른 키 이름이 확인되면 여기에 추가한다.
_ITEM_ID_KEYS = ("id", "place_id", "placeId")
_ITEM_NAME_KEYS = ("name", "businessName", "title")

# 알려진 응답 구조에서 리스트가 위치할 것으로 예상되는 경로(우선 시도 대상).
# 확장 포인트: PoC live 관찰로 새로운 경로가 확인되면 이 튜플에 튜플을 추가한다.
_KNOWN_LIST_PATHS = (
    ("result", "place", "list"),
    ("result", "business", "list"),
)


def _looks_like_place_item(value) -> bool:
    """dict가 '업체 항목'처럼 보이는지 휴리스틱으로 판단한다(id류 키 + name류 키 존재)."""
    if not isinstance(value, dict):
        return False
    has_id = any(key in value for key in _ITEM_ID_KEYS)
    has_name = any(key in value for key in _ITEM_NAME_KEYS)
    return has_id and has_name


def _get_by_path(data, path):
    """data에서 path(키 튜플)를 따라가며 값을 찾는다. 중간에 없으면 None."""
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _find_item_lists(node, found: list) -> None:
    """data 트리를 재귀 순회하며 '업체 항목처럼 보이는 dict들의 리스트'를 found에 누적한다.

    그래프ql/Apollo 유사 응답처럼 실제 리스트가 어느 깊이에 있을지 미리 알 수
    없는 중첩 구조를 대응하기 위한 휴리스틱 탐색이다. 알려진 경로(_KNOWN_LIST_PATHS)
    탐색이 실패했을 때만 _extract_list_items가 이 함수를 호출한다.
    """
    if isinstance(node, list):
        if node and all(_looks_like_place_item(item) for item in node):
            found.append(node)
        else:
            for item in node:
                _find_item_lists(item, found)
    elif isinstance(node, dict):
        for value in node.values():
            _find_item_lists(value, found)


def _extract_list_items(data) -> list:
    """파싱된 JSON(dict/list)에서 업체 리스트로 보이는 dict의 배열을 찾아 반환한다.

    입력: response.json()으로 이미 파싱된 dict 또는 list.
    출력: 업체 항목(dict)들의 list. 찾지 못하면 빈 list(예외를 던지지 않음).

    1) 먼저 _KNOWN_LIST_PATHS(예: result.place.list)를 우선 시도한다.
    2) 실패하면 트리 전체를 재귀 스캔해(_find_item_lists) 휴리스틱으로 후보를
       찾고, 후보가 여러 개면 가장 긴 리스트를 채택한다(업체 리스트일 확률이
       가장 높다고 가정).
    이 함수는 JSON 구조가 사전 예고 없이 바뀔 수 있다는 전제 하에 작성되었으므로,
    알 수 없는 구조가 들어와도 예외 없이 빈 리스트를 반환한다.
    """
    if not isinstance(data, (dict, list)):
        return []

    for path in _KNOWN_LIST_PATHS:
        candidate = _get_by_path(data, path)
        if (
            isinstance(candidate, list)
            and candidate
            and all(_looks_like_place_item(item) for item in candidate)
        ):
            return candidate

    found: list = []
    try:
        _find_item_lists(data, found)
    except Exception:
        return []

    if not found:
        return []
    return max(found, key=len)


# 컬럼별 값 후보 키(우선순위 순). 실제 응답 키 이름은 응답 종류(allSearch/graphql 등)에
# 따라 다를 수 있으므로 여러 후보를 순서대로 시도한다.
# 확장 포인트: PoC live 관찰로 새로운 키 이름이 확인되면 아래 튜플에 추가한다.
_FIELD_KEY_CANDIDATES = {
    "업체명": ("name", "businessName", "title"),
    "업종": ("category", "categoryName"),
    "주소": ("roadAddress", "address"),
    "대표전화": ("tel", "virtualTel"),
    "홈페이지": ("homePage",),
}

# PoC-1.1 확장 포인트: 지금은 "확인 가능한 첫 값"만 사용하는 단일 컬럼(리뷰수)이지만,
# 방문자 리뷰/블로그 리뷰를 Excel에서 분리해야 할 필요가 생기면(제품 요구 확정 시)
# 이 튜플을 나눠 별도 컬럼 매핑을 추가한다. 지금은 과도한 합산/가공 없이 방어적으로
# 첫 번째 확인 가능한 값만 사용한다.
_REVIEW_COUNT_KEY_CANDIDATES = ("visitorReviewCount", "reviewCount", "blogReviewCount")
_ID_KEY_CANDIDATES = _ITEM_ID_KEYS
_PLACE_URL_KEY_CANDIDATES = ("placeUrl", "url", "detailUrl", "businessUrl")


def _first_present(item: dict, keys) -> str:
    """item에서 keys 순서대로 첫 번째로 존재하는(비어있지 않은) 값을 문자열로 반환한다.

    값이 숫자(int/float)여도 str()로 안전하게 문자열화하며, 없으면 빈 문자열을
    반환한다(예외를 던지지 않음 - 방어적 파싱 원칙). list/dict처럼 join 등 별도
    가공이 필요한 필드(예: 업종)는 이 함수 대신 전용 헬퍼(_extract_category 등)를
    사용한다 - 그대로 str()하면 "['a', 'b']" 같은 repr 문자열이 되어버리기 때문.
    """
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _first_raw_value(item: dict, keys):
    """item에서 keys 순서대로 첫 번째로 존재하는 '원본' 값을 반환한다(문자열화하지 않음).

    _first_present와 달리 list 등 원본 타입을 그대로 넘겨야 하는 호출자
    (_classify_external_links처럼 값이 list인지 먼저 판별해야 하는 경우)를 위한
    헬퍼다. 값이 없거나 빈 값(""/[]) 이면 None을 반환한다.
    """
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return None


def _extract_category(item: dict) -> str:
    """category/categoryName 값을 사람이 읽기 좋은 문자열로 정리한다.

    값이 list("['카페,디저트', '베이커리']"가 될 수 있는 경우)이면 ", "로
    join하고, 문자열이면 그대로 사용하며, 없거나 빈 값이면 빈 문자열을 반환한다.
    _first_present를 그대로 쓰면 list가 Python repr 문자열로 그대로 박혀버리므로
    이 필드만 전용 처리한다.
    """
    for key in _FIELD_KEY_CANDIDATES["업종"]:
        value = item.get(key)
        if isinstance(value, list):
            joined = ", ".join(str(v) for v in value if v not in (None, ""))
            if joined:
                return joined
            continue
        if value not in (None, ""):
            return str(value)
    return ""


def _classify_external_links(raw_value) -> tuple:
    """homePage류 필드 값(문자열 또는 문자열 리스트)을 도메인 기준으로 분류한다.

    네이버 응답은 대표 외부 링크를 종류와 무관하게 "홈페이지" 필드 하나에 담는
    경우가 있다(detail_scraper._extract_entry_sns가 entryIframe에서 확인한 것과
    동일한 관례). 이 함수는 URL의 도메인을 보고 인스타/블로그/그 외(홈페이지)로
    분류한다:
      - "instagram.com" 포함 -> 인스타
      - "blog.naver.com" 포함 또는 "blog."로 시작/포함(그 외 블로그 계열) -> 블로그
      - 그 외 유효한 URL -> 홈페이지
    값이 list로 여러 개 들어오면 각각 분류하고, 같은 분류에 이미 값이 있으면
    먼저 발견한 값을 유지한다(덮어쓰지 않음). 값이 없거나 예상과 다른 타입이면
    예외 없이 (빈 문자열, 빈 문자열, 빈 문자열)을 반환한다.

    반환: (homepage, insta, blog) 튜플.
    """
    homepage = ""
    insta = ""
    blog = ""

    if isinstance(raw_value, str):
        candidates = [raw_value] if raw_value else []
    elif isinstance(raw_value, (list, tuple)):
        candidates = [v for v in raw_value if isinstance(v, str) and v]
    else:
        candidates = []

    for url in candidates:
        low = url.lower()
        if "instagram.com" in low:
            insta = insta or url
        elif "blog.naver.com" in low or low.startswith("https://blog.") or ".blog." in low:
            blog = blog or url
        elif not homepage:
            homepage = url

    return homepage, insta, blog


def _build_place_url(item: dict) -> str:
    """item에서 플레이스 URL을 구성한다.

    응답에 명시적 URL 필드(placeUrl 등)가 있으면 그 값을 그대로 사용한다.
    없으면 id/place_id로 pcmap 플레이스 URL을 best-effort 구성한다.

    주의(PoC 단계의 임시 구성 - 실사용 전 검증 필요): 실제 pcmap URL은 업종별
    세그먼트(예: restaurant/cafe)를 쓰는 경우가 있으나, 리스트 응답만으로는
    이를 확정할 수 없다. 이 PoC 단계에서는 범용 "place" 세그먼트로 구성하며,
    이 세그먼트가 실제로 유효한 리다이렉트인지는 PoC-2 또는 별도 브라우저
    검증에서 확인한다. 정확한 세그먼트 확정은 detail_scraper의 entryIframe
    실제 URL 확보 역할로 남겨둔다(ARCH-300 후속 검증 필요, 이번 단계에서는
    live 재검증하지 않음).
    """
    explicit_url = _first_present(item, _PLACE_URL_KEY_CANDIDATES)
    if explicit_url:
        return explicit_url
    place_id = _first_present(item, _ID_KEY_CANDIDATES)
    if not place_id:
        return ""
    return f"https://pcmap.place.naver.com/place/{place_id}/home"


def _map_item_to_row(item: dict, collected_at: str) -> dict:
    """네트워크 응답의 업체 item 하나를 기존 Excel 11컬럼 row(dict)로 매핑한다.

    입력: item(dict, 응답에서 추출된 업체 하나), collected_at(수집일 문자열).
    출력: exporter.MERGED_COLUMNS(11컬럼)와 동일한 키를 가진 dict + 내부 필드 place_id.
    place_id는 dedup/디버그용 내부 필드일 뿐이며, exporter가 MERGED_COLUMNS로만
    투영하므로 Excel에는 노출되지 않는다(detail_scraper 경로와 동일한 관례).

    새로오픈여부는 리스트 응답만으로는 신뢰할 수 있는 값을 확인하지 못해 PoC
    단계에서는 항상 빈칸이다(추후 응답 구조 추가 확인 후 채울 후보). 홈페이지/
    인스타/블로그는 homePage류 필드 값을 도메인 기준으로 분류해 채운다
    (_classify_external_links, PoC-1.1) - 응답에 값이 없으면 그대로 전부 빈칸.
    """
    if not isinstance(item, dict):
        item = {}

    homepage_raw = _first_raw_value(item, _FIELD_KEY_CANDIDATES["홈페이지"])
    homepage, insta, blog = _classify_external_links(homepage_raw)

    return {
        "업체명": _first_present(item, _FIELD_KEY_CANDIDATES["업체명"]),
        "업종": _extract_category(item),
        "새로오픈여부": "",  # PoC 단계: 신뢰할 수 있는 필드 미확인
        "리뷰수": _first_present(item, _REVIEW_COUNT_KEY_CANDIDATES),
        "주소": _first_present(item, _FIELD_KEY_CANDIDATES["주소"]),
        "대표전화": _first_present(item, _FIELD_KEY_CANDIDATES["대표전화"]),
        "플레이스 URL": _build_place_url(item),
        "수집일": collected_at,
        "홈페이지": homepage,
        "인스타": insta,
        "블로그": blog,
        "place_id": _first_present(item, _ID_KEY_CANDIDATES),
    }


def _dedup_key(row: dict) -> str:
    """place_id가 있으면 그것으로, 없으면 업체명으로 dedup 키를 만든다."""
    place_id = str(row.get("place_id") or "").strip()
    if place_id:
        return f"id:{place_id}"
    name = str(row.get("업체명") or "").strip()
    return f"name:{name}" if name else ""


def dedup_rows(rows, seen: set) -> list:
    """seen(set)을 기준으로 중복 row를 제거한 새 리스트를 반환한다.

    seen은 호출자가 여러 응답/페이지에 걸쳐 재사용할 수 있도록 in-place로
    갱신된다(list_scraper._build_row가 seen 인자를 쓰는 것과 동일한 패턴).
    dedup 키가 비어있는 행(업체명/place_id 모두 없음)은 제외한다.
    """
    unique_rows = []
    for row in rows:
        key = _dedup_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows
