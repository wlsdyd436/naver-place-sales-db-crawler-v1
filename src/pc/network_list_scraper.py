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
#
# safety.is_captcha_or_security_message는 읽기 전용으로 재사용한다(src/pc/safety.py는
# 수정하지 않는다) - 클릭 예외 메시지의 CAPTCHA/보안 차단 키워드 판정 로직을
# 중복 구현하지 않기 위함이다.
import hashlib
import re

from src.pc.safety import is_captcha_or_security_message

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


def _map_item_to_row(
    item: dict,
    collected_at: str,
    *,
    source_page: int | None = None,
    source_dong: str | None = None,
    source_query: str | None = None,
) -> dict:
    """네트워크 응답의 업체 item 하나를 기존 Excel 11컬럼 row(dict)로 매핑한다.

    입력: item(dict, 응답에서 추출된 업체 하나), collected_at(수집일 문자열),
    source_page(선택, PoC-2: 어느 page 응답에서 나왔는지), source_dong(선택,
    PoC-4: 어느 동 검색어에서 나왔는지), source_query(선택, PoC-4: 실제 사용된
    전체 검색어 문자열) - 전부 디버그/집계용으로만 남기고 싶을 때 전달한다.
    출력: exporter.MERGED_COLUMNS(11컬럼)와 동일한 키를 가진 dict + 내부 필드
    place_id(+전달된 source_* 필드들). 이 내부 필드들은 dedup/디버그용일 뿐이며,
    exporter가 MERGED_COLUMNS로만 투영하므로 Excel에는 노출되지 않는다
    (detail_scraper 경로와 동일한 관례). 셋 다 미전달 시 기존 PoC-1/PoC-2
    호출과 완전히 하위 호환된다(row에 해당 키 자체가 생기지 않음).

    새로오픈여부는 리스트 응답만으로는 신뢰할 수 있는 값을 확인하지 못해 PoC
    단계에서는 항상 빈칸이다(추후 응답 구조 추가 확인 후 채울 후보). 홈페이지/
    인스타/블로그는 homePage류 필드 값을 도메인 기준으로 분류해 채운다
    (_classify_external_links, PoC-1.1) - 응답에 값이 없으면 그대로 전부 빈칸.
    """
    if not isinstance(item, dict):
        item = {}

    homepage_raw = _first_raw_value(item, _FIELD_KEY_CANDIDATES["홈페이지"])
    homepage, insta, blog = _classify_external_links(homepage_raw)

    row = {
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
    if source_page is not None:
        row["source_page"] = source_page
    if source_dong is not None:
        row["source_dong"] = source_dong
    if source_query is not None:
        row["source_query"] = source_query
    return row


def build_candidate_record(url: str, status, resource_type: str, *, top_level_keys=None, parse_error=None) -> dict:
    """live probe 스크립트가 관찰한 후보 response 하나를 요약 dict로 조립한다.

    PoC-1/PoC-2 등 여러 probe 스크립트가 동일한 형태로 관찰 로그(JSON)를 남기도록
    돕는 유틸이다. 이 함수는 Playwright response 객체를 직접 다루지 않는다(그
    처리 - url/status/resource_type 추출, response.json() 시도 - 는 호출자인
    probe 스크립트가 이미 완료했다는 전제이며, 이 함수는 결과를 dict로 정리만
    한다). 이 모듈이 "브라우저를 직접 다루지 않고 관찰 결과만 가공한다"는
    원칙을 유지하기 위함이다.

    top_level_keys/parse_error는 probe 스크립트가 response.json() 파싱을
    시도한 결과(성공 시 최상위 키 목록, 실패 시 에러 메시지)를 그대로 넘기면
    된다.
    """
    return {
        "url": url,
        "status": status,
        "resource_type": resource_type,
        "top_level_keys": list(top_level_keys) if top_level_keys else [],
        "parse_error": parse_error,
    }


def classify_captcha_signal(
    *,
    marker_present_in_dom: bool = False,
    element_visible: bool = False,
    bounding_box_area: float = 0.0,
    click_exception_message: str = "",
) -> dict:
    """관찰된 원시 신호를 CAPTCHA/보안 확인 판정 3단계로 조합한다(PoC-2R 오탐 보정).

    이 함수는 Playwright page/locator 객체를 직접 다루지 않는다. locator.count(),
    locator.is_visible(), bounding_box() 같은 실제 브라우저 호출은 probe
    스크립트가 미리 수행해 bool/문자열로 넘겨야 한다 - 그래야 live 브라우저
    없이 fixture만으로 테스트할 수 있다.

    2026-07-01/2026-07-08 관찰(PROJECT_STATE.md 기록): "#wtm-captcha-root" 같은
    마커 요소/문자열은 페이지 최초 로드 시점부터 DOM에 상시 존재할 수 있지만
    is_visible()이 한 번도 True를 반환하지 않는 경우가 있다(활성 챌린지가
    아니라 항상 존재하는 static placeholder). 따라서 "DOM에 존재한다"는 사실
    만으로는 활성 CAPTCHA로 판정하지 않는다(오탐 방지).

    반환 3개 키(중단 판단은 호출자가 active_captcha_detected 또는
    click_intercepted_by_captcha만 근거로 사용해야 한다 - passive만 있으면
    기록만 하고 계속 진행):
      - passive_captcha_marker_found: 마커가 DOM/HTML에 존재(가시성 무관).
        단독으로는 중단 근거가 아니다.
      - active_captcha_detected: 마커가 실제로 보이고(element_visible) 의미
        있는 크기(bounding_box_area > 0)를 가짐. 중단 근거로 사용한다.
      - click_intercepted_by_captcha: 클릭 시도 중 발생한 예외 메시지에
        CAPTCHA/보안 차단 키워드가 포함됨(safety.is_captcha_or_security_message
        재사용). pointer event가 실제로 가로채였다는 가장 신뢰도 높은 신호이며,
        중단 근거로 사용한다.

    확장 포인트: 새로운 CAPTCHA 판정 신호(예: 특정 응답 status 코드)를 추가하려면
    이 함수에 키워드 인자를 추가하고 반환 dict에 반영한다.
    """
    marker_present_in_dom = bool(marker_present_in_dom)
    element_visible = bool(element_visible)
    active = marker_present_in_dom and element_visible and bounding_box_area > 0
    click_intercepted = bool(click_exception_message) and is_captcha_or_security_message(
        click_exception_message
    )

    return {
        "passive_captcha_marker_found": marker_present_in_dom,
        "active_captcha_detected": active,
        "click_intercepted_by_captcha": click_intercepted,
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


def count_rows_by_source_page(rows) -> dict:
    """rows(list[dict])를 source_page 값 기준으로 몇 건인지 집계한다(PoC-3).

    여러 page(1/2/3...)에서 모인 row를 병합한 뒤, page별로 몇 건씩 확보됐는지
    확인하기 위한 순수 집계 함수다. Playwright나 파일 IO를 다루지 않으므로
    live 브라우저 없이 fixture만으로 테스트할 수 있다.

    `_map_item_to_row`가 `source_page`를 채우지 않은 행(예: 기존 PoC-1 스타일
    호출)은 "unknown" 키로 묶는다. place_id/source_page는 Excel에는 노출되지
    않는 내부 필드이므로, 이 집계 결과도 진단/로그 용도로만 쓰고 Excel 저장에는
    사용하지 않는다.

    확장 포인트: page 외에 다른 기준(예: 응답 URL)으로도 집계하고 싶다면
    `row.get("source_page", ...)` 부분만 원하는 키로 바꾼 유사 함수를 추가한다.
    """
    counts: dict = {}
    for row in rows:
        key = row.get("source_page")
        if key is None:
            key = "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def count_rows_by_field(rows, field: str, *, unknown_label: str = "unknown") -> dict:
    """rows(list[dict])를 임의의 내부 메타 필드(field) 값 기준으로 집계한다(PoC-4).

    `count_rows_by_source_page`의 일반화 버전이다. 동(dong)/검색어(query) 등
    page 외의 다른 내부 메타 기준으로도 같은 방식의 집계가 필요해져 추가했다
    (예: `count_rows_by_field(rows, "source_dong")`). 순수 집계 함수이며
    Playwright/파일 IO를 다루지 않아 fixture만으로 테스트할 수 있다.

    field 값이 없는(None) 행은 unknown_label(기본 "unknown") 키로 묶는다.
    place_id/source_page/source_dong/source_query 등은 모두 Excel에는
    노출되지 않는 내부 필드이므로, 이 집계 결과도 진단/로그 용도로만 쓴다.
    """
    counts: dict = {}
    for row in rows:
        key = row.get(field)
        if key is None:
            key = unknown_label
        counts[key] = counts.get(key, 0) + 1
    return counts


# PoC-6(REGION-DATA-1): 쿼리별 신규 기여도가 낮은지 판단하기 위한 임계값.
# 확장 포인트: 실측 데이터가 쌓이면 이 상수만 조정한다(호출자 코드 변경 불필요).
_LOW_EFFICIENCY_RATIO_THRESHOLD = 0.15
_LOW_EFFICIENCY_MIN_UNIQUE_ADDED = 3


def classify_query_efficiency(raw_items: int, unique_added: int) -> dict:
    """쿼리 하나가 확보한 raw_items 대비 unique_added가 효율적인지 판단한다(PoC-6).

    입력: raw_items(해당 쿼리 응답에서 나온 원시 항목 수), unique_added(전역
    dedup 후 실제로 새로 추가된 행 수, unique_added는 raw_items 이하여야
    정상이지만 이 함수는 그 관계를 검증하지 않는다 - 호출자가 이미 dedup_rows로
    계산한 값을 그대로 전달한다는 전제).
    출력: {"efficiency_ratio": float, "low_efficiency": bool}.

    efficiency_ratio = unique_added / raw_items(raw_items가 0이면 0.0 - PoC-5의
    "성내제1~3동처럼 raw는 있지만 unique_added=0"인 경우와, 응답 자체가 없어
    raw_items=0인 경우를 구분하지 않고 둘 다 낮은 효율로 취급한다).

    low_efficiency는 efficiency_ratio가 _LOW_EFFICIENCY_RATIO_THRESHOLD(0.15)
    미만이거나 unique_added가 _LOW_EFFICIENCY_MIN_UNIQUE_ADDED(3) 미만이면
    True다. PoC-6에서는 이 값을 기록만 하고 자동 중단/스킵에는 사용하지
    않는다(호출자가 아직 그 정책을 적용하지 않기로 결정함) - 자동 스킵 정책은
    별도 PoC에서 검증한다.
    """
    ratio = (unique_added / raw_items) if raw_items > 0 else 0.0
    low_efficiency = ratio < _LOW_EFFICIENCY_RATIO_THRESHOLD or unique_added < _LOW_EFFICIENCY_MIN_UNIQUE_ADDED
    return {"efficiency_ratio": ratio, "low_efficiency": low_efficiency}


def should_stop_for_target(current_count: int, target: int) -> bool:
    """누적 unique row 수(current_count)가 목표(target)에 도달했는지 판단한다(PoC-6).

    target이 0 이하이면(목표가 없거나 잘못된 값) 항상 False를 반환한다(방어적
    처리 - 의미 없는 target으로 조기 종료하지 않는다). PoC-6에서는 이 값을
    관찰용으로만 기록하며, 실제 큐 순회를 이 값으로 중단하는 정책은 PoC-7에서
    검증한다.
    """
    if target <= 0:
        return False
    return current_count >= target


# ============================================================================
# DOM-first membership (PAGE300-DOM-1): 단일 검색어 300건 수집에서 DOM에 실제
# 렌더링된 업체 목록을 최종 membership 기준으로 삼고, Network/Apollo는 필드
# 보강(enrichment)에만 쓰기 위한 순수 함수들. Playwright/브라우저 객체를 전혀
# 다루지 않으며(dict/list 입출력만), 실제 DOM row 추출·스크롤·Apollo state
# 접근은 network_browser_collector.py의 collect_dom_membership_query가 담당한다.
#
# 매핑 우선순위(요청서 §10): place_id -> normalized place_url -> (업체명,업종,
# 주소) -> (업체명,업종) 순. "업체명+업종+raw_text" 단계는 Network/Apollo
# entity 자체가 raw_text 필드를 갖지 않으므로(그 필드는 DOM 카드 고유의
# 값이다) source 매칭에는 적용하지 않는다 - 대신 dedup_key_for_membership_row
# (최종 확정된 row끼리의 중복 판정)에서만 raw_text 기반 fallback으로 쓰인다.
# "업체명+업종"만 일치하는 마지막 단계는 후보가 있어도 AMBIGUOUS로 강등한다
# (느슨한 키이므로 임의 채택 금지 - 요청서 §10).
# ============================================================================

_REVIEW_COUNT_TEXT_PATTERN = re.compile(r"리뷰\s*([\d,]+)")
_ADDRESS_HINT_PATTERN = re.compile(r"[가-힣]+(?:시|도)\s?[가-힣]+구\s?[가-힣0-9]+동")
_PLACE_ID_NAMED_SEGMENT_PATTERN = re.compile(r"/(?:restaurant|place|hairshop|beauty)/(\d+)")
_PLACE_ID_GENERIC_SEGMENT_PATTERN = re.compile(r"/(\d{5,})(?:[/?]|$)")

_MATCH_CONFIDENCE_RANK = {
    "EXACT_ID": 4,
    "EXACT_URL": 3,
    "STRONG_COMPOSITE": 2,
    "AMBIGUOUS": 1,
    "UNMATCHED": 0,
}


def _normalize_text(value) -> str:
    """공백을 정리한 문자열로 정규화한다(None/숫자 등도 안전하게 문자열화)."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_place_url(url) -> str:
    """플레이스 URL을 query string/fragment/trailing slash 없이 정규화한다."""
    if not url:
        return ""
    text = str(url).strip()
    text = text.split("?", 1)[0]
    text = text.split("#", 1)[0]
    return text.rstrip("/")


def extract_place_id_from_url(url) -> str:
    """URL에서 숫자 place_id를 best-effort로 추출한다(세그먼트 이름을 가정하지
    않는다 - 실측에서 /restaurant/{id}/home, /place/{id}/... 두 세그먼트가 모두
    확인됨). 알려진 세그먼트를 우선 시도하고, 실패하면 5자리 이상 숫자 세그먼트를
    범용으로 찾는다. 못 찾으면 빈 문자열."""
    if not url:
        return ""
    text = str(url)
    match = _PLACE_ID_NAMED_SEGMENT_PATTERN.search(text)
    if match:
        return match.group(1)
    match = _PLACE_ID_GENERIC_SEGMENT_PATTERN.search(text)
    if match:
        return match.group(1)
    return ""


def parse_raw_text_fallback(raw_text: str) -> dict:
    """DOM row의 raw_text(카드 전체 innerText)에서 리뷰수/주소를 최소 정규식으로
    추출한다(억지 매칭 금지 - 못 찾으면 빈 문자열). Network/Apollo enrichment가
    실패했을 때만 쓰는 최후 fallback이다."""
    text = str(raw_text or "")
    review_match = _REVIEW_COUNT_TEXT_PATTERN.search(text)
    review_guess = review_match.group(1).replace(",", "") if review_match else ""
    address_match = _ADDRESS_HINT_PATTERN.search(text)
    address_guess = address_match.group(0) if address_match else ""
    return {"review_count_guess": review_guess, "address_guess": address_guess}


# PAGE300-DOM-2: React Fiber 기반 place_id guard. DOM anchor href가 전부 "#"
# placeholder임이 실측으로 재확인되어(scratchpad/page300_4d_dom_place_id_audit),
# React가 DOM node에 심어두는 __reactFiber$*/__reactProps$* 속성에서 얻은 후보를
# 우선 신뢰한다. 실제 Fiber 트리 탐색(fast path 우선 시도 + bounded recursive
# search fallback)은 브라우저 전용이라 network_browser_collector.py의 JS가
# 수행하고, 여기서는 그 JS가 반환한 원시 후보(raw_row["identifier_candidates"])에
# 대한 검증/우선순위 판정만 담당한다(순수 로직 - fake 테스트로 브라우저 없이 검증
# 가능하도록 분리).
_DIGIT_ONLY_PATTERN = re.compile(r"^\d+$")
_MIN_PLACE_ID_LENGTH = 5
_MAX_PLACE_ID_LENGTH = 15
_APOLLO_KEY_PREFIXES = ("PlaceListBusinessesItem:{id}:{id}", "RestaurantBase:{id}")


def _is_valid_place_id_format(value) -> bool:
    """숫자로만 구성되고 비정상적으로 짧거나 긴 값을 거부한다."""
    text = str(value or "").strip()
    if not _DIGIT_ONLY_PATTERN.match(text):
        return False
    return _MIN_PLACE_ID_LENGTH <= len(text) <= _MAX_PLACE_ID_LENGTH


def apollo_key_exists_for_id(apollo_raw_keys, place_id: str) -> bool:
    """Apollo State의 원본 key 목록(예: "PlaceListBusinessesItem:123:123")에서
    place_id에 대응하는 key가 존재하는지 확인한다(정보성 - 존재하지 않아도 다른
    경로로 이미 확정된 place_id를 무효화하지 않는다. Apollo State는 페이지당
    약 78개로 제한적임이 이전 감사에서 이미 확인됨)."""
    if not place_id or not apollo_raw_keys:
        return False
    candidates = {template.format(id=place_id) for template in _APOLLO_KEY_PREFIXES}
    return bool(candidates & set(apollo_raw_keys))


def resolve_dom_identifier(raw_row: dict, apollo_raw_keys=None) -> dict:
    """DOM row의 identifier_candidates(JS가 수집한 원시 후보)로부터 place_id를
    확정한다. 우선순위: fast path(item.id/apolloCacheId 상호 검증) > bounded
    search(distinct 유효값이 정확히 1개일 때만) > href 파싱. 각 단계에서 서로
    다른 유효 후보가 2개 이상이면 그 단계에서 즉시 CONFLICT로 확정하고 더 느슨한
    단계로 내려가 임의로 채택하지 않는다.

    반환: {"place_id", "identifier_method"(FIBER_FAST_PATH/FIBER_BOUNDED_SEARCH/
    HREF_ID/CONFLICT/UNRESOLVED), "identifier_validated", "identifier_conflict",
    "identifier_apollo_confirmed"}.
    """
    candidates = (raw_row or {}).get("identifier_candidates") or {}

    fast_item_id = _normalize_text(candidates.get("fast_item_id"))
    fast_apollo_id = _normalize_text(candidates.get("fast_apollo_cache_id"))
    fast_item_valid = _is_valid_place_id_format(fast_item_id)
    fast_apollo_valid = _is_valid_place_id_format(fast_apollo_id)

    def _finalize(place_id: str, method: str, validated: bool, conflict: bool) -> dict:
        return {
            "place_id": place_id,
            "identifier_method": method,
            "identifier_validated": validated,
            "identifier_conflict": conflict,
            "identifier_apollo_confirmed": apollo_key_exists_for_id(apollo_raw_keys, place_id),
        }

    if fast_item_valid and fast_apollo_valid:
        if fast_item_id != fast_apollo_id:
            return _finalize("", "CONFLICT", False, True)
        return _finalize(fast_item_id, "FIBER_FAST_PATH", True, False)
    if fast_item_valid:
        return _finalize(fast_item_id, "FIBER_FAST_PATH", True, False)
    if fast_apollo_valid:
        return _finalize(fast_apollo_id, "FIBER_FAST_PATH", True, False)

    bounded = candidates.get("bounded_candidates") or []
    distinct_values = set()
    for item in bounded:
        raw_value = item.get("value") if isinstance(item, dict) else item
        value = _normalize_text(raw_value)
        if _is_valid_place_id_format(value):
            distinct_values.add(value)
    if len(distinct_values) == 1:
        return _finalize(next(iter(distinct_values)), "FIBER_BOUNDED_SEARCH", True, False)
    if len(distinct_values) > 1:
        return _finalize("", "CONFLICT", False, True)

    for href in (raw_row or {}).get("anchor_hrefs") or []:
        href_id = extract_place_id_from_url(href)
        if _is_valid_place_id_format(href_id):
            return _finalize(href_id, "HREF_ID", True, False)

    return _finalize("", "UNRESOLVED", False, False)


def normalize_dom_row(raw_row: dict, page_number: int, apollo_raw_keys=None) -> dict:
    """DOM에서 추출한 row 하나(dom_index/name/category/raw_text/
    identifier_candidates/place_url/anchor_hrefs/data_attributes)를 정규화한다.
    place_id는 resolve_dom_identifier(React Fiber 기반 guard)가 확정하며, 실패
    (UNRESOLVED/CONFLICT)해도 row 자체를 삭제하지 않는다(그 판단은
    is_skeleton_dom_row가 업체명 기준으로 별도 담당). place_url(anchor href 기반,
    "플레이스 URL" 필드용)은 식별자 판단과 별개로 기존 로직을 유지한다."""
    if not isinstance(raw_row, dict):
        raw_row = {}

    name = _normalize_text(raw_row.get("name"))
    category = _normalize_text(raw_row.get("category"))
    raw_text = str(raw_row.get("raw_text") or "")
    place_url = str(raw_row.get("place_url") or "").strip()
    anchor_hrefs = list(raw_row.get("anchor_hrefs") or [])
    data_attributes = dict(raw_row.get("data_attributes") or {})

    if not place_url:
        for href in anchor_hrefs:
            if href and extract_place_id_from_url(href):
                place_url = href
                break

    identifier = resolve_dom_identifier(raw_row, apollo_raw_keys)

    address_text = _normalize_text(raw_row.get("address_text"))
    if not address_text:
        address_text = parse_raw_text_fallback(raw_text)["address_guess"]

    return {
        "page_number": page_number,
        "dom_index": raw_row.get("dom_index"),
        "name": name,
        "category": category,
        "raw_text": raw_text,
        "address_text": address_text,
        "place_id": identifier["place_id"],
        "place_url": place_url,
        "anchor_hrefs": anchor_hrefs,
        "data_attributes": data_attributes,
        "identifier_method": identifier["identifier_method"],
        "identifier_validated": identifier["identifier_validated"],
        "identifier_conflict": identifier["identifier_conflict"],
        "identifier_apollo_confirmed": identifier["identifier_apollo_confirmed"],
        "normalized_name": name,
        "normalized_place_url": normalize_place_url(place_url),
        "normalized_raw_text": _normalize_text(raw_text),
    }


def is_skeleton_dom_row(dom_row: dict) -> bool:
    """업체명이 없는 row(광고 placeholder/skeleton/구분자 등으로 간주)인지 확인한다."""
    return not (dom_row or {}).get("normalized_name")


def to_common_entity(row: dict, *, id_key, name_key, category_key, address_key, url_key=None) -> dict:
    """Network 매핑 row(한글 키)와 Apollo entity(영문 키)를 동일한 공용 형태로
    변환한다(build_entity_index가 소스 종류와 무관하게 동작하도록). source_row는
    원본 dict를 그대로 보존한다(merge_dom_row_fields가 나머지 필드를 그 원본에서
    직접 읽는다)."""
    return {
        "id": _normalize_text(row.get(id_key)),
        "url": normalize_place_url(row.get(url_key)) if url_key else "",
        "name": _normalize_text(row.get(name_key)),
        "category": _normalize_text(row.get(category_key)),
        "address": _normalize_text(row.get(address_key)),
        "source_row": row,
    }


def build_entity_index(common_rows: list) -> dict:
    """to_common_entity로 변환된 row 목록을 place_id/URL/(이름,업종,주소)/
    (이름,업종) 4단 인덱스로 만든다. 값은 항상 list다 - 후보가 2건 이상이면
    resolve_match가 그 사실 자체를 AMBIGUOUS 판정 근거로 쓴다."""
    by_id: dict = {}
    by_url: dict = {}
    by_addr: dict = {}
    by_name_category: dict = {}
    for row in common_rows:
        if row["id"]:
            by_id.setdefault(row["id"], []).append(row)
        if row["url"]:
            by_url.setdefault(row["url"], []).append(row)
        if row["name"] and row["category"]:
            by_name_category.setdefault((row["name"], row["category"]), []).append(row)
            if row["address"]:
                by_addr.setdefault((row["name"], row["category"], row["address"]), []).append(row)
    return {"by_id": by_id, "by_url": by_url, "by_addr": by_addr, "by_name_category": by_name_category}


def resolve_match(dom_row: dict, index: dict) -> dict:
    """DOM row 하나를 하나의 entity index(Network 또는 Apollo, 독립적으로 호출)에
    대해 매칭한다. 반환: {"row": dict|None, "confidence": "EXACT_ID"|"EXACT_URL"|
    "STRONG_COMPOSITE"|"AMBIGUOUS"|"UNMATCHED"}. 각 단계에서 후보가 2건 이상이면
    그 단계에서 즉시 AMBIGUOUS로 확정한다(더 느슨한 하위 단계로 내려가 임의로
    골라잡지 않는다)."""
    place_id = dom_row.get("place_id") or ""
    if place_id:
        candidates = index["by_id"].get(place_id)
        if candidates is not None:
            if len(candidates) != 1:
                return {"row": None, "confidence": "AMBIGUOUS"}
            return {"row": candidates[0]["source_row"], "confidence": "EXACT_ID"}

    place_url = dom_row.get("normalized_place_url") or ""
    if place_url:
        candidates = index["by_url"].get(place_url)
        if candidates is not None:
            if len(candidates) != 1:
                return {"row": None, "confidence": "AMBIGUOUS"}
            return {"row": candidates[0]["source_row"], "confidence": "EXACT_URL"}

    name = dom_row.get("normalized_name") or ""
    category = dom_row.get("category") or ""
    address = dom_row.get("address_text") or ""
    if name and category and address:
        candidates = index["by_addr"].get((name, category, address))
        if candidates is not None:
            if len(candidates) != 1:
                return {"row": None, "confidence": "AMBIGUOUS"}
            return {"row": candidates[0]["source_row"], "confidence": "STRONG_COMPOSITE"}

    if name and category and (name, category) in index["by_name_category"]:
        return {"row": None, "confidence": "AMBIGUOUS"}

    return {"row": None, "confidence": "UNMATCHED"}


def overall_row_confidence(network_result: dict, apollo_result: dict) -> str:
    """두 소스(Network/Apollo) 중 더 강한 신뢰도를 채택한다."""
    nc = (network_result or {}).get("confidence", "UNMATCHED")
    ac = (apollo_result or {}).get("confidence", "UNMATCHED")
    return nc if _MATCH_CONFIDENCE_RANK.get(nc, 0) >= _MATCH_CONFIDENCE_RANK.get(ac, 0) else ac


def merge_dom_row_fields(dom_row: dict, network_result: dict, apollo_result: dict, collected_at: str) -> dict:
    """필드 우선순위(요청서 §10): 1)Network 검증값 2)Apollo 구조화값 3)DOM 직접값
    4)DOM raw_text 정규식 파싱값 5)빈값. 업체명은 항상 DOM 값(정규화만). 플레이스
    URL은 DOM anchor href를 최우선으로 쓴다 - _build_place_url의 구성 fallback
    ("/place/{id}/home")은 실측 URL 세그먼트(/restaurant/{id}/home)와 달라 이
    경로에서는 신뢰하지 않는다(그 fallback으로 만들어진 값인지는 "/place/"
    포함 여부로 방어적으로 걸러낸다)."""
    network_row = (network_result or {}).get("row") or {}
    apollo_row = (apollo_result or {}).get("row") or {}
    raw_fallback = parse_raw_text_fallback(dom_row.get("raw_text") or "")

    def _pick(network_key, apollo_key, dom_value):
        if network_key:
            value = _normalize_text(network_row.get(network_key))
            if value:
                return value
        if apollo_key:
            value = _normalize_text(apollo_row.get(apollo_key))
            if value:
                return value
        return _normalize_text(dom_value)

    place_url = dom_row.get("place_url") or ""
    if not place_url:
        network_url = str(network_row.get("플레이스 URL") or "")
        if network_url and "/place/" not in network_url:
            place_url = network_url

    row = {
        "업체명": dom_row.get("normalized_name") or "",
        "업종": _pick("업종", "category", dom_row.get("category")),
        "새로오픈여부": "",
        "리뷰수": _pick("리뷰수", "review_count", raw_fallback["review_count_guess"]),
        "주소": _pick("주소", "address", dom_row.get("address_text") or raw_fallback["address_guess"]),
        "대표전화": _pick("대표전화", None, ""),
        "플레이스 URL": place_url,
        "수집일": collected_at,
        "홈페이지": _normalize_text(network_row.get("홈페이지")),
        "인스타": _normalize_text(network_row.get("인스타")),
        "블로그": _normalize_text(network_row.get("블로그")),
        "place_id": dom_row.get("place_id") or network_row.get("place_id") or apollo_row.get("place_id") or "",
        "source_page": dom_row.get("page_number"),
        "dom_index": dom_row.get("dom_index"),
        "match_confidence": overall_row_confidence(network_result, apollo_result),
        "_dedup_raw_text": dom_row.get("normalized_raw_text") or "",
    }
    return row


def compute_page_signature(dom_rows: list) -> dict:
    """DOM row 배열의 표시 순서를 그대로 써서 first/top5/top10 시그니처를
    계산한다(comprehensive_cdp_tester.calculate_signature와 동일한 top-N
    join+md5 관례). Apollo/Network 순서는 전혀 참조하지 않는다."""
    names = [row.get("normalized_name") or row.get("name") or "" for row in dom_rows]
    top5 = names[:5]
    top10 = names[:10]
    return {
        "first_name": names[0] if names else "",
        "top5": top5,
        "top10": top10,
        "top5_hash": hashlib.md5("|".join(top5).encode("utf-8")).hexdigest(),
        "top10_hash": hashlib.md5("|".join(top10).encode("utf-8")).hexdigest(),
    }


def page_transition_confirmed(
    expected_page_number, actual_page_number, current_flag_ok, previous_signature, new_signature
) -> bool:
    """expected_page_number==actual_page_number AND 현재 페이지 활성 표시 확인
    AND top10 signature가 이전 페이지와 다름을 모두 만족해야 전환 완료로
    인정한다(요청서 §5/§7 - page 번호/active 속성만으로는 완료 처리 금지)."""
    if expected_page_number != actual_page_number:
        return False
    if not current_flag_ok:
        return False
    new_hash = (new_signature or {}).get("top10_hash")
    if not new_hash:
        return False
    prev_hash = (previous_signature or {}).get("top10_hash")
    return prev_hash != new_hash


def dedup_key_for_membership_row(row: dict) -> str:
    """우선순위: place_id > normalized place_url > (업체명,업종,주소) >
    (업체명,업종,raw_text) > (업체명, source_page, dom_index)로 유일성을 보장한다.
    업체명 단독으로는 절대 dedup하지 않는다(마지막 fallback도 page/dom_index로
    row별 유일성을 유지해, 서로 다른 지점을 잘못 합치지 않는다)."""
    place_id = _normalize_text(row.get("place_id"))
    if place_id:
        return f"id:{place_id}"
    url = normalize_place_url(row.get("플레이스 URL"))
    if url:
        return f"url:{url}"
    name = _normalize_text(row.get("업체명"))
    category = _normalize_text(row.get("업종"))
    address = _normalize_text(row.get("주소"))
    if name and category and address:
        return f"addr:{name}|{category}|{address}"
    raw_text = _normalize_text(row.get("_dedup_raw_text"))
    if name and raw_text:
        return f"raw:{name}|{category}|{raw_text}"
    if name:
        return f"nameonly:{name}|{row.get('source_page')}|{row.get('dom_index')}"
    return ""


def dedup_membership_rows(rows: list, seen: set) -> list:
    """dedup_rows와 동일한 in-place seen 패턴(여러 page에 걸쳐 seen을 재사용)."""
    unique_rows = []
    for row in rows:
        key = dedup_key_for_membership_row(row)
        if not key or key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def summarize_membership_diagnostics(match_results: list) -> dict:
    """요청서 §13 진단 카운터(중복/최종 유일 개수는 dedup 이후 호출자가 채운다)."""
    total_dom_raw = len(match_results)
    exact_id = sum(1 for m in match_results if m.get("overall") == "EXACT_ID")
    exact_url = sum(1 for m in match_results if m.get("overall") == "EXACT_URL")
    composite = sum(1 for m in match_results if m.get("overall") == "STRONG_COMPOSITE")
    ambiguous = sum(1 for m in match_results if m.get("overall") == "AMBIGUOUS")
    unmatched = sum(1 for m in match_results if m.get("overall") == "UNMATCHED")
    return {
        "total_dom_raw": total_dom_raw,
        "total_enriched": exact_id + exact_url + composite,
        "exact_id_match_count": exact_id,
        "exact_url_match_count": exact_url,
        "composite_match_count": composite,
        "ambiguous_count": ambiguous,
        "unmatched_count": unmatched,
    }


def trim_membership_rows_to_target(rows: list, target: int) -> list:
    """DOM 표시 순서를 보존한 채 target 개수로 trim한다(target<=0이면 그대로)."""
    if not target or target <= 0:
        return list(rows)
    return list(rows[:target])
