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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.parser import detect_new_open_pc, extract_address_from_pc_text, extract_review_count_pc
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
    ("data", "restaurants", "businesses", "items"),
    ("data", "businesses", "items"),
    ("data", "place", "list"),
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

    1) 먼저 _KNOWN_LIST_PATHS(예: result.place.list, data.restaurants.businesses.items)를 우선 시도한다.
    2) data가 list(GraphQL batched response 등)인 경우 배열 원소를 순회 파싱한다.
    3) 실패하면 트리 전체를 재귀 스캔해(_find_item_lists) 휴리스틱으로 후보를
       찾고, 후보가 여러 개면 가장 긴 리스트를 채택한다.
    """
    if not isinstance(data, (dict, list)):
        return []

    if isinstance(data, list):
        if data and all(_looks_like_place_item(item) for item in data):
            return data
        batched_items = []
        for entry in data:
            if isinstance(entry, (dict, list)):
                sub_items = _extract_list_items(entry)
                if sub_items:
                    batched_items.extend(sub_items)
        if batched_items:
            return batched_items
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
    "주소": ("roadAddress", "address", "commonAddress"),
    "홈페이지": ("homePage", "website", "homepage"),
}

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


# 2026-07-25 field parity 보정: 전국 시·도 축약명 -> 정식 명칭 정규화 표
# (요청서 §5 예시 그대로). 이미 정식 명칭인 키도 등록해 idempotent하게
# 유지되도록 한다(그대로 유지 - 축약 재변환/이중 변환 없음).
_SIDO_CANONICAL_MAP = {
    "서울": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시", "부산광역시": "부산광역시",
    "대구": "대구광역시", "대구광역시": "대구광역시",
    "인천": "인천광역시", "인천광역시": "인천광역시",
    "광주": "광주광역시", "광주광역시": "광주광역시",
    "대전": "대전광역시", "대전광역시": "대전광역시",
    "울산": "울산광역시", "울산광역시": "울산광역시",
    "세종": "세종특별자치시", "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    "경기": "경기도", "경기도": "경기도",
    "강원": "강원특별자치도", "강원도": "강원특별자치도", "강원특별자치도": "강원특별자치도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "전북": "전북특별자치도", "전라북도": "전북특별자치도", "전북특별자치도": "전북특별자치도",
    "전남": "전라남도", "전라남도": "전라남도",
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "제주": "제주특별자치도", "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
}


def _normalize_sido_token(token: str) -> str:
    """시·도 축약명을 정식 명칭으로 변환한다. 표에 없는 토큰(시·군·구/읍·면·동
    등)은 원문 그대로 반환한다(임의 변형 없음)."""
    return _SIDO_CANONICAL_MAP.get(token, token)


def _token_matches_common_address(detail_token: str, common_token: str, index: int) -> bool:
    """detail(도로명/지번주소)의 앞부분이 commonAddress와 같은 행정구역을
    가리키는지 토큰 단위로 비교한다. index==0(시·도)만 축약/정식 표기 차이를
    허용하고(_normalize_sido_token으로 양쪽 정규화 후 비교), 그 외(시·군·구/
    읍·면·동)는 원문 그대로 비교한다 - 시·군·구·동 이름은 축약형이 따로
    없어 정규화 없이 정확히 같을 때만 중복으로 간주한다(다른 행정구역을
    잘못 잘라내지 않기 위함)."""
    if index == 0:
        return _normalize_sido_token(detail_token) == _normalize_sido_token(common_token)
    return detail_token == common_token


def format_common_address(common_address, road_address, address: str = "") -> str:
    """업체 entity 자신의 주소 필드만으로 두 모드 공통 주소 문자열을
    조립한다(요청서 §5) - 검색어(job/query)는 어떤 인자로도 받지 않으므로
    구조적으로 "검색어 동을 모든 업체에 강제 주입"할 수 없다.

    우선순위: commonAddress(시·도/시·군·구/읍·면·동) + roadAddress(도로명+
    상세, 없으면 address의 지번주소) 결합. commonAddress의 시·도 토큰만
    정식 명칭으로 정규화하고(_normalize_sido_token), detail의 시작 토큰이
    commonAddress와 같은 행정구역을 가리키면(정식/축약 표기 무관) 그 구간만
    잘라 중복을 제거한다(건물명/층/호수/쉼표 등 나머지 토큰은 그대로 보존).
    commonAddress가 없으면 detail만(시·도로 보이는 첫 토큰만 정규화 시도)
    반환하고, 전부 없으면 빈 문자열을 반환한다(예외 없음)."""
    common_address = str(common_address or "").strip()
    detail = str(road_address or "").strip() or str(address or "").strip()

    if not common_address:
        if not detail:
            return ""
        tokens = detail.split()
        if tokens:
            tokens[0] = _normalize_sido_token(tokens[0])
        return re.sub(r"\s+", " ", " ".join(tokens)).strip()

    common_tokens = common_address.split()
    normalized_common_tokens = list(common_tokens)
    if normalized_common_tokens:
        normalized_common_tokens[0] = _normalize_sido_token(normalized_common_tokens[0])
    normalized_common = " ".join(normalized_common_tokens)

    if not detail:
        return re.sub(r"\s+", " ", normalized_common).strip()

    detail_tokens = detail.split()
    overlap = 0
    for i in range(min(len(common_tokens), len(detail_tokens))):
        if _token_matches_common_address(detail_tokens[i], common_tokens[i], i):
            overlap = i + 1
        else:
            break
    remaining_detail = " ".join(detail_tokens[overlap:])

    combined = f"{normalized_common} {remaining_detail}".strip() if remaining_detail else normalized_common
    return re.sub(r"\s+", " ", combined).strip()


# ============================================================================
# 5M-R1 field policy (2026-07-23): 방문자/블로그 리뷰 분리, 개인 휴대전화 차단,
# 외부 URL 유형별 분리, 새로오픈 tri-state. 실제 GraphQL/Apollo 5M 증거
# (scratchpad/page300_5m_r1_graphql_field_provenance_audit)에서 확인된 키
# (visitorReviewsTotal/cafeBlogReviewsTotal/phone/virtualPhone/homepages/
# newOpening)를 우선 사용하며, 미확인 값은 절대 0/false로 임의 확정하지 않는다.
# ============================================================================


def _normalize_review_count(value):
    """리뷰수 원시 값을 정수로 정규화한다. bool/음수/비숫자/None/빈 문자열은
    모두 "미확인"(빈 문자열)으로 취급한다 - 실패를 0으로 바꾸지 않는다."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return value if value >= 0 else ""
    if isinstance(value, float):
        if value.is_integer() and value >= 0:
            return int(value)
        return ""
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text or not text.isdigit():
            return ""
        return int(text)
    return ""


def _compute_total_review_count(visitor, blog):
    """방문자/블로그 리뷰수가 둘 다 확인된 정수일 때만 합산한다(0도 유효한
    확인값). 어느 한쪽이라도 미확인("")이면 총리뷰수는 공란이다 - 부분 합계를
    총리뷰수로 표시하지 않는다."""
    if isinstance(visitor, bool) or isinstance(blog, bool):
        return ""
    if isinstance(visitor, int) and isinstance(blog, int):
        return visitor + blog
    return ""


# 2026-07-25 field parity 보정: 목록(PlaceListBusinessesItem) entity와
# 상세(PlaceDetailBase) entity가 리뷰수를 서로 다른 키 이름으로 담고 있음이
# 실측 확인됐다(scratchpad/page300_5m_r1_graphql_field_provenance_audit/
# final_report.md 10번 "React Fiber list item visitorReviewCount",
# review_semantics_audit.md 5개 표본 전부 visitorReviewCount 실측 - 기존
# visitorReviewsTotal/cafeBlogReviewsTotal는 상세 entity 전용 키였다). 목록
# 전용 키를 1순위로, 기존 상세 전용 키를 2순위 fallback으로 둬 두 출처
# 모두 이 하나의 함수로 처리한다.
_VISITOR_REVIEW_KEYS = ("visitorReviewCount", "visitorReviewsTotal")
_BLOG_REVIEW_KEYS = ("blogCafeReviewCount", "cafeBlogReviewsTotal")


def _first_review_count_value(item: dict, keys):
    """keys 순서대로 item에 '키가 실제로 존재하는' 첫 값을 원본 그대로
    반환한다(값이 0이어도 유효한 확인값이므로 dict.get 기본값 대신 in으로
    존재 자체를 확인한다). 어느 키도 없으면 None(미확인)을 반환한다."""
    for key in keys:
        if key in item:
            return item[key]
    return None


# 개인 휴대전화 prefix(공백/괄호/하이픈 제거 후 판정). 국제표기(+82-10...)는
# 국가코드가 선행 0을 대체하므로 "82" + 10/11/16/17/18/19로 별도 판정한다.
_PERSONAL_MOBILE_PREFIXES = ("010", "011", "016", "017", "018", "019")
_PERSONAL_MOBILE_INTL_PREFIXES = ("10", "11", "16", "17", "18", "19")


def _is_personal_mobile_phone(value) -> bool:
    """010/011/016~019(국내) 또는 +82-10 등(국제, 82 다음이 10/11/16~19)
    개인 휴대전화 형식인지 판정한다. 050/0507 안심번호, 02/031 지역번호,
    070 인터넷전화, 1588 등 대표번호는 이 판정에 해당하지 않는다."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return False
    if digits[:3] in _PERSONAL_MOBILE_PREFIXES:
        return True
    if digits[:2] == "82" and digits[2:4] in _PERSONAL_MOBILE_INTL_PREFIXES:
        return True
    return False


# 5M 증거로 확인된 전화 후보 키 우선순위: 공식 phone -> tel -> virtualPhone(0507)
# -> virtualTel(미확인 후보, 하위호환용) -> 공란. 각 후보는 개인 휴대전화
# 필터를 통과해야 채택된다(요청서 §7/§8).
_OFFICIAL_PHONE_KEY_PRIORITY = ("phone", "tel", "virtualPhone", "virtualTel")


def _resolve_official_phone(item: dict) -> tuple:
    """item에서 대표전화를 우선순위대로 선택하고, 개인 휴대전화는 걸러낸다.

    반환: (phone, filtered_count). phone은 채택된 값(없으면 ""), filtered_count는
    이번 호출에서 개인 휴대전화로 판정되어 폐기된 후보 개수(원문은 어디에도
    보존하지 않고 건수만 반환한다 - 로그/진단에는 PERSONAL_MOBILE_FILTERED와
    건수만 노출해야 한다는 정책과 일치).
    """
    filtered_count = 0
    for key in _OFFICIAL_PHONE_KEY_PRIORITY:
        raw = item.get(key)
        if raw in (None, ""):
            continue
        text = str(raw).strip()
        if not text:
            continue
        if _is_personal_mobile_phone(text):
            filtered_count += 1
            continue
        return text, filtered_count
    return "", filtered_count


def _resolve_new_open_tristate(item: dict) -> str:
    """newOpening(boolean, 5M 증거 확인 키) 기반 tri-state 판정.
    True -> "O", False -> "X", None 또는 키 없음 -> "" (미확인/공란).
    """
    if "newOpening" not in item:
        return ""
    value = item.get("newOpening")
    if value is True:
        return "O"
    if value is False:
        return "X"
    return ""


# 홈페이지로 분류하지 않을 네이버 내부/광고 URL(예약/주문/스마트스토어/지도/
# 플레이스/광고 리다이렉트). exact hostname 또는 그 서브도메인만 제외한다.
_EXCLUDED_HOMEPAGE_HOSTS = (
    "map.naver.com",
    "pcmap.place.naver.com",
    "m.place.naver.com",
    "place.naver.com",
    "booking.naver.com",
    "order.naver.com",
    "smartstore.naver.com",
    "adcr.naver.com",
    # 2026-07-23 5O 감사(S5 표본)에서 카카오톡채널 URL이 홈페이지로 오분류된
    # 사례가 실측 확인되어 제외 목록에 추가.
    "pf.kakao.com",
)
_INSTAGRAM_HOSTS = ("instagram.com", "www.instagram.com", "m.instagram.com")
_BLOG_HOSTS = ("blog.naver.com",)
_URL_TYPE_LABEL_MAP = {"인스타그램": "insta", "블로그": "blog", "홈페이지": "homepage"}
_TRACKING_QUERY_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def _normalize_external_url(raw) -> str:
    """URL을 정규화한다: tel:/mailto:/javascript: 거부, scheme 없는 명백한
    도메인만 https:// 보정, hostname 소문자화, 추적 파라미터 제거, fragment
    제거, 알려진 네이버 내부/예약/주문/광고 hostname 거부. 유효하지 않으면
    빈 문자열을 반환한다(예외 없음)."""
    text = str(raw or "").strip()
    if not text:
        return ""
    low = text.lower()
    if low.startswith(("tel:", "mailto:", "javascript:")):
        return ""
    if not low.startswith(("http://", "https://")):
        if " " in text or "." not in text:
            return ""
        text = "https://" + text

    parsed = urlsplit(text)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    hostname = parsed.hostname.lower()
    if any(hostname == host or hostname.endswith("." + host) for host in _EXCLUDED_HOMEPAGE_HOSTS):
        return ""

    kept_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in _TRACKING_QUERY_PARAMS]
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit((parsed.scheme, hostname, path, urlencode(kept_query), ""))


def _classify_single_url(url, type_label=None) -> tuple:
    """URL 하나를 (category, normalized_url)로 분류한다. category는
    "insta"/"blog"/"homepage" 중 하나이며, 무효 URL이면 (None, None)을
    반환한다. type_label(응답이 이미 제공하는 한글 라벨)을 1차 기준으로,
    hostname을 보조 기준으로 사용한다."""
    normalized = _normalize_external_url(url)
    if not normalized:
        return None, None
    if type_label:
        mapped = _URL_TYPE_LABEL_MAP.get(str(type_label).strip())
        if mapped:
            return mapped, normalized
    hostname = (urlsplit(normalized).hostname or "").lower()
    if hostname in _INSTAGRAM_HOSTS:
        return "insta", normalized
    if hostname in _BLOG_HOSTS:
        return "blog", normalized
    return "homepage", normalized


def _iter_url_candidates(value, depth: int = 0):
    """homepages{repr, etc[]} 객체, 문자열, 문자열 리스트, {url}/{link}/
    {type,url} 객체, 중첩 리스트에서 (url, type_label) 후보를 depth<=2까지만
    순회한다(무제한 재귀 금지)."""
    if depth > 2 or value is None:
        return
    if isinstance(value, str):
        if value:
            yield value, None
    elif isinstance(value, dict):
        if "repr" in value or "etc" in value:
            if value.get("repr") is not None:
                yield from _iter_url_candidates(value["repr"], depth + 1)
            for entry in value.get("etc") or []:
                yield from _iter_url_candidates(entry, depth + 1)
            return
        url = value.get("url") or value.get("link") or value.get("landingUrl")
        type_label = value.get("type") or value.get("typeI18n")
        if url:
            yield url, type_label
    elif isinstance(value, (list, tuple)):
        for entry in value:
            yield from _iter_url_candidates(entry, depth + 1)


def _extract_external_urls(item: dict) -> tuple:
    """item에서 홈페이지/인스타/블로그를 추출·분류한다. homepages(5M 증거
    확인 구조), naverBlog, 기존 homePage류 후보 필드를 모두 수집해 type_label
    우선 -> hostname 보조 순으로 분류하고, 동일 정규화 URL은 중복 제거한다.
    같은 분류에 이미 값이 있으면 먼저 찾은 값을 유지한다(덮어쓰지 않음).
    """
    homepage = ""
    insta = ""
    blog = ""
    seen_urls: set = set()

    sources = []
    if "homepages" in item and item["homepages"] is not None:
        sources.append(item["homepages"])
    if "naverBlog" in item and item["naverBlog"] is not None:
        sources.append(item["naverBlog"])
    # snsList: 5M 증거에는 실존하지 않음(homepages.etc[]로 통합 확인됨)이나,
    # 응답 구조 변경 대비 방어적으로 키가 있으면 동일하게 처리한다.
    if "snsList" in item and item["snsList"] is not None:
        sources.append(item["snsList"])
    legacy_raw = _first_raw_value(item, _FIELD_KEY_CANDIDATES["홈페이지"])
    if legacy_raw is not None:
        sources.append(legacy_raw)

    for source in sources:
        for url, type_label in _iter_url_candidates(source):
            category, normalized = _classify_single_url(url, type_label)
            if not category or not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            if category == "insta" and not insta:
                insta = normalized
            elif category == "blog" and not blog:
                blog = normalized
            elif category == "homepage" and not homepage:
                homepage = normalized

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
    """네트워크 응답의 업체 item 하나를 exporter.MERGED_COLUMNS(13컬럼)
    row(dict)로 매핑한다(5M-R1: 리뷰 방문자/블로그 분리, 개인 휴대전화 차단,
    URL 유형별 분리, 새로오픈 tri-state - scratchpad/page300_5m_r1_graphql_
    field_provenance_audit에서 확인된 실제 키 사용).

    입력: item(dict, 응답에서 추출된 업체 하나), collected_at(수집일 문자열),
    source_page(선택, PoC-2: 어느 page 응답에서 나왔는지), source_dong(선택,
    PoC-4: 어느 동 검색어에서 나왔는지), source_query(선택, PoC-4: 실제 사용된
    전체 검색어 문자열) - 전부 디버그/집계용으로만 남기고 싶을 때 전달한다.
    출력: exporter.MERGED_COLUMNS와 동일한 키를 가진 dict + 내부 필드
    place_id(+전달된 source_* 필드들 + _personal_mobile_filtered_count).
    이 내부 필드들은 dedup/진단용일 뿐이며, exporter가 MERGED_COLUMNS로만
    투영하므로 Excel에는 노출되지 않는다. 셋 다 미전달 시 기존 PoC-1/PoC-2
    호출과 완전히 하위 호환된다(row에 해당 키 자체가 생기지 않음).

    리스트 응답에는 방문자/블로그 리뷰·전화·홈페이지·새로오픈 필드가 없는
    경우가 대부분임이 5M 증거로 확인됐다 - 이 경우 아래 헬퍼들은 모두
    안전하게 공란/미확인을 반환한다(추측으로 채우지 않는다).
    """
    if not isinstance(item, dict):
        item = {}

    homepage, insta, blog = _extract_external_urls(item)
    visitor_reviews = _normalize_review_count(_first_review_count_value(item, _VISITOR_REVIEW_KEYS))
    blog_reviews = _normalize_review_count(_first_review_count_value(item, _BLOG_REVIEW_KEYS))
    total_reviews = _compute_total_review_count(visitor_reviews, blog_reviews)
    phone, personal_mobile_filtered_count = _resolve_official_phone(item)

    row = {
        "업체명": _first_present(item, _FIELD_KEY_CANDIDATES["업체명"]),
        "업종": _extract_category(item),
        "새로오픈여부": _resolve_new_open_tristate(item),
        "방문자리뷰수": visitor_reviews,
        "블로그리뷰수": blog_reviews,
        "총리뷰수": total_reviews,
        "주소": format_common_address(item.get("commonAddress"), item.get("roadAddress"), item.get("address")),
        "대표전화": phone,
        "플레이스 URL": _build_place_url(item),
        "수집일": collected_at,
        "홈페이지": homepage,
        "인스타": insta,
        "블로그": blog,
        "place_id": _first_present(item, _ID_KEY_CANDIDATES),
        "roadAddress": _first_present(item, ("roadAddress",)),
        "_personal_mobile_filtered_count": personal_mobile_filtered_count,
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
    """DOM row의 raw_text(카드 전체 innerText)에서 리뷰수/주소/새로오픈여부를
    추출한다(억지 매칭 금지 - 못 찾으면 빈 문자열). PAGE300-DETAIL-1: 자체
    regex 대신 기존 PC 카드 파서(src/parser.py, list_scraper.py의 _build_row가
    이미 쓰고 있던 검증된 규칙)를 그대로 재사용한다 - "1.2만" 같은 한국어 축약
    표기 처리는 기존 정책에 없으므로 이번에도 추가하지 않는다. Network/Apollo
    enrichment가 실패했을 때만 쓰는 최후 fallback이다."""
    text = str(raw_text or "")
    review_guess = extract_review_count_pc(text)
    address_guess = extract_address_from_pc_text(text)
    new_open_guess = detect_new_open_pc(text)
    return {"review_count_guess": review_guess, "address_guess": address_guess, "new_open_guess": new_open_guess}


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


def build_place_url_from_id(place_id) -> str:
    """place_id로 범용(vertical 비의존) 플레이스 URL을 구성한다. DOM anchor
    href가 전부 "#"라 실측 세그먼트(예: restaurant/hospital/hairshop)를 알 수
    없으므로, 특정 vertical을 추측해 하드코딩하지 않고 네이버가 실제로 자동
    리다이렉트하는 범용 세그먼트("place")를 사용한다(PAGE300-DETAIL-1 §7 -
    Live 검증으로 실측 확인 필요, 잘못된 vertical을 임의로 붙이지 않는다).
    place_id가 숫자 형식이 아니면 빈 문자열을 반환한다(malformed ID로 잘못된
    URL을 만들지 않는다)."""
    text = _normalize_text(place_id)
    if not _DIGIT_ONLY_PATTERN.match(text):
        return ""
    return f"https://pcmap.place.naver.com/place/{text}/home"


# ============================================================================
# 5O(2026-07-23): Apollo State 정규화 엔티티 adapter. 상세 페이지 방문 시
# window.__APOLLO_STATE__에 채워지는 `PlaceDetailBase:{id}`(base)와 ROOT_QUERY의
# `placeDetail({"input":{...}})`(parent)를 exact place_id/`__ref` 기준으로만
# 결합해 기존 `_map_item_to_row()`가 소비할 수 있는 flat dict로 변환한다.
# 5O 감사(scratchpad/page300_5o_real_apollo_parser_integration_audit)의
# joined_entity_replay_results.json이 이 결합 방식으로 5/5 raw 표본 정확히
# 일치함을 확인했다. 리뷰 합산/URL 분류/전화 필터는 여기서 만들지 않고 그대로
# _map_item_to_row에 위임한다(중복 구현 금지).
# ============================================================================

_APOLLO_BASE_KEY_PREFIX = "PlaceDetailBase:"
_APOLLO_ROOT_QUERY_KEY = "ROOT_QUERY"
_APOLLO_PARENT_KEY_TOKEN = "placeDetail("
_APOLLO_BASE_FIELDS = (
    "id", "name", "category", "roadAddress", "address", "commonAddress", "phone", "virtualPhone",
    "visitorReviewsTotal", "cafeBlogReviewsTotal", "naverBlog",
)
_APOLLO_PARENT_FIELDS = ("homepages", "newOpening", "phoneInfo")


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
    필드만 복사). Apollo State 전체나 무관한 entity를 반환하지 않는다."""
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

    return result


def merge_detail_into_row(row: dict, detail_result: dict) -> dict:
    """이미 확정된 최종 row에 상세 페이지 결과(detail_result)를 사후 병합한다.
    place_id 또는 normalized place URL이 정확히 일치할 때만 병합하고, 업체명만
    으로는 병합하지 않는다(요청서 §4 - 업체명만 같은 다른 지점 오염 방지).
    detail_result가 없거나 성공하지 못했으면 row를 그대로 반환한다(row 삭제
    금지 - 실패해도 기존 값 보존).

    5O(2026-07-23): 방문자/블로그 리뷰수와 새로오픈여부 병합을 추가한다(기존에는
    두 필드를 전혀 다루지 않던 gap). 리뷰수는 detail_result가 확인한 값만
    개별 반영하고(한쪽만 확인돼도 그것만 갱신), 총리뷰수는 항상
    _compute_total_review_count로 재계산한다(중복 합산 로직 없음). 새로오픈은
    row가 이미 값을 가지고 있으면(목록에서 확정된 "O" 등) 덮어쓰지 않는다."""
    if not detail_result or not detail_result.get("detail_success"):
        return row
    detail_place_id = _normalize_text(detail_result.get("place_id"))
    detail_url = normalize_place_url(detail_result.get("플레이스 URL"))
    row_place_id = _normalize_text(row.get("place_id"))
    row_url = normalize_place_url(row.get("플레이스 URL"))
    id_match = bool(detail_place_id) and detail_place_id == row_place_id
    url_match = bool(detail_url) and detail_url == row_url
    if not (id_match or url_match):
        return row

    merged = dict(row)
    detail_phone = detail_result.get("대표전화")
    if detail_phone and not _is_personal_mobile_phone(detail_phone):
        merged["대표전화"] = detail_phone
    if detail_result.get("주소"):
        merged["주소"] = detail_result["주소"]
    if detail_result.get("플레이스 URL"):
        merged["플레이스 URL"] = detail_result["플레이스 URL"]
    if detail_result.get("홈페이지"):
        merged["홈페이지"] = detail_result["홈페이지"]
    if detail_result.get("인스타"):
        merged["인스타"] = detail_result["인스타"]
    if detail_result.get("블로그"):
        merged["블로그"] = detail_result["블로그"]

    detail_visitor = detail_result.get("방문자리뷰수")
    detail_blog = detail_result.get("블로그리뷰수")
    visitor_confirmed = isinstance(detail_visitor, int) and not isinstance(detail_visitor, bool)
    blog_confirmed = isinstance(detail_blog, int) and not isinstance(detail_blog, bool)
    if visitor_confirmed or blog_confirmed:
        if visitor_confirmed:
            merged["방문자리뷰수"] = detail_visitor
        if blog_confirmed:
            merged["블로그리뷰수"] = detail_blog
        merged["총리뷰수"] = _compute_total_review_count(merged.get("방문자리뷰수"), merged.get("블로그리뷰수"))

    if detail_result.get("새로오픈여부") and not merged.get("새로오픈여부"):
        merged["새로오픈여부"] = detail_result["새로오픈여부"]

    return merged


def merge_dom_row_fields(
    dom_row: dict, network_result: dict, apollo_result: dict, collected_at: str, detail_result: dict = None
) -> dict:
    """필드 우선순위(요청서 §3, PAGE300-DETAIL-1/5M-R1로 갱신): 업체명은 항상
    DOM 값. 업종은 DOM -> Network/Apollo -> 상세정보. 새로오픈여부는 DOM
    raw_text 판정(목록 뱃지, 기존 parser.detect_new_open_pc 재사용) ->
    Network 구조화값(newOpening tri-state) -> 상세정보. 방문자/블로그
    리뷰수는 Network/Apollo 구조화값만 사용한다(DOM raw_text 정규식은 방문자/
    블로그를 구분할 수 없는 값이라 사용하지 않음 - 오귀속 방지). 총리뷰수는
    최종 방문자/블로그 값으로 매번 재계산한다. 주소는 Network/Apollo(기존
    유지) -> 상세정보 -> DOM raw_text(parser.extract_address_from_pc_text).
    대표전화는 상세정보 -> Network(이미 개인 휴대전화 필터를 거친 값) 순이며,
    이 함수에서 개인 휴대전화 안전망을 한 번 더 적용한다(상세정보 경로는
    DOM entryIframe 스크레이핑이라 아직 필터를 거치지 않았으므로). 홈페이지/
    인스타/블로그는 상세정보 우선(Network/Apollo에는 이 필드가 없음이 실측
    확인됨). 플레이스 URL은 상세정보로 확인된 실제 URL -> DOM anchor href ->
    place_id로 구성한 범용 URL(build_place_url_from_id) -> 빈값.
    detail_result는 이번 호출 시점에 없을 수 있다(None, 기본값) - 이 함수
    자체는 상세 페이지를 방문하지 않으며, 상세 병합은 detail_result가 이미
    확보된 경우에만 이 우선순위에 반영된다(추가 상세 병합은
    merge_detail_into_row로 사후에도 가능)."""
    network_row = (network_result or {}).get("row") or {}
    apollo_row = (apollo_result or {}).get("row") or {}
    detail_row = detail_result or {}
    raw_fallback = parse_raw_text_fallback(dom_row.get("raw_text") or "")

    def _pick(*value_sources):
        for value in value_sources:
            normalized = _normalize_text(value)
            if normalized:
                return normalized
        return ""

    def _pick_numeric(*value_sources):
        for value in value_sources:
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return ""

    def _finalize_phone(value):
        text = _normalize_text(value)
        if not text or _is_personal_mobile_phone(text):
            return ""
        return text

    place_url = _pick(
        detail_row.get("플레이스 URL") if detail_row.get("detail_success") else "",
        dom_row.get("place_url"),
        build_place_url_from_id(dom_row.get("place_id")),
    )

    visitor_reviews = _pick_numeric(network_row.get("방문자리뷰수"), apollo_row.get("visitorReviewsTotal"))
    blog_reviews = _pick_numeric(network_row.get("블로그리뷰수"), apollo_row.get("cafeBlogReviewsTotal"))

    row = {
        "업체명": dom_row.get("normalized_name") or "",
        "업종": _pick(dom_row.get("category"), network_row.get("업종"), apollo_row.get("category"), detail_row.get("업종")),
        "새로오픈여부": _pick(raw_fallback["new_open_guess"], network_row.get("새로오픈여부"), detail_row.get("새로오픈여부")),
        "방문자리뷰수": visitor_reviews,
        "블로그리뷰수": blog_reviews,
        "총리뷰수": _compute_total_review_count(visitor_reviews, blog_reviews),
        "주소": _pick(network_row.get("주소"), apollo_row.get("address"), detail_row.get("주소"), dom_row.get("address_text"), raw_fallback["address_guess"]),
        "대표전화": _finalize_phone(_pick(detail_row.get("대표전화"), network_row.get("대표전화"))),
        "플레이스 URL": place_url,
        "수집일": collected_at,
        "홈페이지": _pick(detail_row.get("홈페이지"), network_row.get("홈페이지")),
        "인스타": _pick(detail_row.get("인스타"), network_row.get("인스타")),
        "블로그": _pick(detail_row.get("블로그"), network_row.get("블로그")),
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


class GlobalPlaceAccumulator:
    """수집 세션(쿼리 1회) 동안 발생한 Network response entity들을
    place_id 키 기준으로 전역 누적/보강하는 클래스.
    """

    def __init__(self, collected_at: str = ""):
        self.collected_at = collected_at
        self.accumulated: dict[str, dict] = {}
        self.observation_count: int = 0
        self.duplicate_count: int = 0
        # PERSONAL_MOBILE_FILTERED: 원문 번호는 저장하지 않고 건수만 누적한다.
        self.personal_mobile_filtered_count: int = 0

    def add_raw_item(self, item: dict, source_page: int | None = None, source_query: str | None = None) -> bool:
        """네트워크 response에서 추출된 raw dict item 하나를 누적한다.
        place_id가 없으면 accumulator에 추가하지 않는다. 업체명 단독 병합 금지.
        """
        if not isinstance(item, dict):
            return False
        self.observation_count += 1
        row = _map_item_to_row(item, self.collected_at, source_page=source_page, source_query=source_query)
        return self.add_mapped_row(row)

    def add_mapped_row(self, row: dict) -> bool:
        """이미 매핑된 row(dict)를 place_id 키로 누적한다."""
        if not isinstance(row, dict):
            return False
        self.personal_mobile_filtered_count += int(row.get("_personal_mobile_filtered_count") or 0)
        place_id = _normalize_text(row.get("place_id"))
        if not place_id or not _DIGIT_ONLY_PATTERN.match(place_id):
            return False

        if place_id not in self.accumulated:
            self.accumulated[place_id] = dict(row)
            return True

        self.duplicate_count += 1
        existing = self.accumulated[place_id]

        # 도로명주소 보강 우선권 처리
        new_road = _normalize_text(row.get("roadAddress"))
        if new_road:
            existing["roadAddress"] = new_road
            existing["주소"] = new_road

        # 비파괴적(non-destructive) 필드 보강: 기존 유효 값은 유지하고 비어있는 필드만 채움
        # (int 0도 "값 있음"으로 정확히 처리됨 - 0 not in (None, "", [])).
        for key, val in row.items():
            if val not in (None, "", []):
                if existing.get(key) in (None, "", []):
                    existing[key] = val

        # 총리뷰수는 병합된 최종 방문자/블로그 리뷰수 기준으로 매번 재계산한다
        # (요청서 §11 - 스테일 값으로 남기지 않는다).
        existing["총리뷰수"] = _compute_total_review_count(existing.get("방문자리뷰수"), existing.get("블로그리뷰수"))
        return False

    def get_row(self, place_id: str) -> dict | None:
        norm_id = _normalize_text(place_id)
        return self.accumulated.get(norm_id)

    def get_all_rows(self) -> list[dict]:
        return list(self.accumulated.values())

    def merge_into_dom_rows(self, dom_rows: list[dict]) -> list[dict]:
        """고유 DOM rows 리스트에 누적된 place_id entities를 exact matching으로 최종 병합한다.
        DOM row 수와 순서를 100% 보존하며, place_id가 매칭될 경우 비어있는 필드 및 도로명주소를 보강한다.
        """
        if not dom_rows:
            return []

        merged_result = []
        for dom_row in dom_rows:
            place_id = _normalize_text(dom_row.get("place_id"))
            net_row = self.accumulated.get(place_id) if place_id else None
            if not net_row:
                merged_result.append(dom_row)
                continue

            updated = dict(dom_row)

            # 1. 주소 보강 (Network에서 수신된 도로명/지번주소가 있으면 비파괴 보강)
            net_addr = _normalize_text(net_row.get("주소"))
            dom_addr = _normalize_text(updated.get("주소"))
            if net_addr:
                if not dom_addr or net_addr != dom_addr:
                    updated["주소"] = net_addr

            # 2. 기타 주요 필드 보강
            for field in ("대표전화", "업종", "홈페이지", "인스타", "블로그", "플레이스 URL", "새로오픈여부"):
                net_val = _normalize_text(net_row.get(field))
                if net_val and not _normalize_text(updated.get(field)):
                    updated[field] = net_val

            # 2b. 방문자/블로그 리뷰수는 정수 타입을 보존해야 하므로 별도 처리한다
            # (int 0을 문자열화해 덮어쓰지 않기 위해 위 루프와 분리).
            for field in ("방문자리뷰수", "블로그리뷰수"):
                net_val = net_row.get(field)
                has_net_val = isinstance(net_val, int) and not isinstance(net_val, bool)
                existing_val = updated.get(field)
                has_existing_val = isinstance(existing_val, int) and not isinstance(existing_val, bool)
                if has_net_val and not has_existing_val:
                    updated[field] = net_val
            updated["총리뷰수"] = _compute_total_review_count(updated.get("방문자리뷰수"), updated.get("블로그리뷰수"))

            merged_result.append(updated)
        return merged_result
