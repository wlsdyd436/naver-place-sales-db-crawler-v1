# ARCH-300 PoC-1: 브라우저 네트워크 응답 관찰 기반 업체 리스트 수집(기술 검증 단계).
#
# 이 모듈은 "직접 API를 호출"하지 않는다. Playwright 브라우저가 검색 결과 화면을
# 정상적으로 렌더링하는 과정에서 자연히 발생시키는 Network response(xhr/fetch)를
# 관찰(observe)하여, 그 응답에 이미 담겨 있는 업체 리스트 데이터를 파싱만 한다.
# CAPTCHA 우회/자동 해결/stealth/proxy/무단 반복 호출은 이 모듈의 목적이 아니며
# 시도하지 않는다.
#
# 아직 PoC-1 단계이므로 이 모듈은 UI(src/ui.py)나 pipeline(src/collection/plan_runner.py)에
# 연결되지 않는다. 순수 함수(파서/매퍼/필터/dedup)만 제공하며, 실제 Playwright
# page/response 객체를 다루는 코드(리스너 등록 등)는 scratchpad의 PoC 스크립트가
# 담당한다 - 이렇게 분리해야 이 모듈을 live 브라우저 없이 fixture만으로 테스트할
# 수 있다.
#
# 네이버 내부 응답의 JSON 구조는 비공식/미문서화이며 사전 예고 없이 바뀔 수 있다.
# 따라서 모든 파싱은 방어적으로 작성한다: 알려진 경로를 우선 시도하고, 실패하면
# 휴리스틱으로 재귀 탐색하며, 그래도 실패하면 예외를 던지지 않고 빈 값을 반환한다.
#
# safety.is_captcha_or_security_message는 읽기 전용으로 재사용한다(src/collection/safety.py는
# 수정하지 않는다) - 클릭 예외 메시지의 CAPTCHA/보안 차단 키워드 판정 로직을
# 중복 구현하지 않기 위함이다.
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.collection.safety import is_captcha_or_security_message

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


_PAREN_GROUP_PATTERN = re.compile(r"\(([^()]*)\)")


def _strip_duplicate_dong_parens(text: str, dong: str) -> str:
    """detail 문자열 안의 "(행정동)"/"(행정동, 건물명)" 괄호 그룹 중, 괄호 첫
    항목이 commonAddress의 마지막 토큰(행정동)과 정확히 같은 것만 제거한다
    (요청서 §14) - "(102동)"/"(판매시설동)"/"(상가동)"처럼 괄호 첫 항목이
    행정동과 다르면 그대로 보존하고, "(행정동, 건물명)"이면 건물명만 남긴다
    (쉼표 뒤 공백 유무 무관 - 정규식이 아닌 문자열 전체 기준으로 괄호 그룹을
    찾으므로 "(천호동, 강동 헤르셔)"처럼 내부에 공백이 있어도 안전하다).
    dong이 비어 있으면 아무 것도 바꾸지 않는다."""
    if not dong or "(" not in text:
        return text

    def _replace(match: re.Match) -> str:
        parts = [p.strip() for p in match.group(1).split(",")]
        if parts and parts[0] == dong:
            remaining = [p for p in parts[1:] if p]
            return "(" + ", ".join(remaining) + ")" if remaining else ""
        return match.group(0)

    return _PAREN_GROUP_PATTERN.sub(_replace, text)


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
    remaining_detail_raw = " ".join(detail_tokens[overlap:])
    remaining_detail = _strip_duplicate_dong_parens(remaining_detail_raw, common_tokens[-1] if common_tokens else "")

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


# 외부 홍보 채널로 절대 취급하지 않을 네이버 내부/기능성/광고 URL(플레이스
# 자체/지도·route/예약/주문/광고 리다이렉트/talktalk). exact hostname 또는 그
# 서브도메인만 제외한다. 카카오채널/스마트스토어는 여기서 제외하지 않는다 -
# 공개 판매·홍보 채널이므로 "추가 링크"에는 남겨야 한다(요청서 §8/§9).
_EXCLUDED_HOMEPAGE_HOSTS = (
    "map.naver.com",
    "m.map.naver.com",
    "pcmap.place.naver.com",
    "m.place.naver.com",
    "place.naver.com",
    "booking.naver.com",
    "order.naver.com",
    "adcr.naver.com",
    "talk.naver.com",
)
# 확장 채널 hostname -> category. hostname이 명확하면 type_label과 충돌해도
# hostname이 우선한다(요청서 §7 "명확한 hostname과 type이 충돌하면 hostname
# 우선" - 버터온 사례: type="홈페이지" + instagram.com hostname -> insta).
_HOST_CATEGORY_MAP = {
    "instagram.com": "insta", "www.instagram.com": "insta", "m.instagram.com": "insta",
    "blog.naver.com": "blog",
    "pf.kakao.com": "kakao",
    "youtube.com": "youtube", "www.youtube.com": "youtube", "m.youtube.com": "youtube", "youtu.be": "youtube",
    "facebook.com": "facebook", "www.facebook.com": "facebook", "m.facebook.com": "facebook", "fb.com": "facebook",
    "smartstore.naver.com": "smartstore", "brand.naver.com": "smartstore",
}
_URL_TYPE_LABEL_MAP = {
    "인스타그램": "insta", "인스타": "insta",
    "블로그": "blog",
    "홈페이지": "homepage",
    "카카오톡채널": "kakao", "카카오채널": "kakao",
    "유튜브": "youtube",
    "페이스북": "facebook",
    "스마트스토어": "smartstore", "브랜드스토어": "smartstore",
}
_CHANNEL_LABELS = {
    "homepage": "홈페이지", "insta": "인스타", "blog": "블로그", "kakao": "카카오채널",
    "youtube": "유튜브", "facebook": "페이스북", "smartstore": "스마트스토어", "etc": "기타",
}
_TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "igshid", "igsh",
}
_EXCLUDED_URL_PATH_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")


def _normalize_external_url(raw) -> str:
    """URL을 정규화한다: tel:/mailto:/javascript: 거부, scheme 없는 명백한
    도메인만 https:// 보정, hostname 소문자화, 추적 파라미터 제거, fragment
    제거, 알려진 네이버 내부/예약/주문/광고/지도/talktalk hostname과 이미지
    URL 거부. 유효하지 않으면 빈 문자열을 반환한다(예외 없음)."""
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
    if hostname == "pstatic.net" or hostname.endswith(".pstatic.net"):
        return ""
    path_lower = parsed.path.lower()
    if any(path_lower.endswith(suffix) for suffix in _EXCLUDED_URL_PATH_SUFFIXES):
        return ""

    kept_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in _TRACKING_QUERY_PARAMS]
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit((parsed.scheme, hostname, path, urlencode(kept_query), ""))


def _dedup_key_for_external_url(normalized_url: str) -> str:
    """dedup 판정 전용 key - www 유무 차이를 같은 URL로 취급하기 위해 hostname의
    선행 'www.'만 제거한다(표시용 normalized_url 자체는 원본 형태를 그대로
    보존 - 기존 테스트가 기대하는 'www.instagram.com/...' 표기를 바꾸지 않는다)."""
    parsed = urlsplit(normalized_url)
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return urlunsplit((parsed.scheme, hostname, parsed.path, parsed.query, ""))


def _classify_single_url(url, type_label=None) -> tuple:
    """URL 하나를 (category, normalized_url)로 분류한다. category는
    "insta"/"blog"/"homepage"/"kakao"/"youtube"/"facebook"/"smartstore"/
    "etc" 중 하나이며, 무효 URL이면 (None, None)을 반환한다. hostname이
    알려진 채널과 명확히 일치하면 type_label과 무관하게 hostname이 우선한다
    (요청서 §7). hostname으로 판단할 수 없으면 type_label(응답이 제공하는
    한글 라벨)을 사용하고, 라벨이 있으나 알려지지 않은 값이면 "etc", 라벨도
    없으면 공개 홈페이지로 간주해 "homepage"를 반환한다."""
    normalized = _normalize_external_url(url)
    if not normalized:
        return None, None
    hostname = (urlsplit(normalized).hostname or "").lower()
    host_category = _HOST_CATEGORY_MAP.get(hostname)
    if host_category:
        return host_category, normalized
    if type_label:
        mapped = _URL_TYPE_LABEL_MAP.get(str(type_label).strip())
        if mapped:
            return mapped, normalized
        return "etc", normalized
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


def _format_extra_links(entries: list) -> str:
    """(category, normalized_url) 목록을 "[라벨] URL" 줄바꿈 문자열로
    직렬화한다(요청서 §10) - 원본 순서 유지, 빈 줄 없음, 앞뒤 줄바꿈 없음."""
    lines = [f"[{_CHANNEL_LABELS.get(category, '기타')}] {url}" for category, url in entries]
    return "\n".join(lines)


def _extract_external_urls(item: dict) -> tuple:
    """item에서 대표 홈페이지/인스타/블로그와 나머지 전체 공개 채널(추가
    링크)을 추출·분류한다. homepages{repr, etc[]}(5M 증거 확인 구조) 전체를
    끝까지 순회하고(repr 처리 후 종료하지 않음, etc의 첫 URL만 보고 멈추지
    않음), naverBlog/snsList/기존 homePage류 후보 필드도 모두 수집한다.
    hostname 우선 -> type_label 보조 순으로 분류하고(요청서 §7), 동일
    정규화 URL은 www 유무와 무관하게 중복 제거한다(요청서 §6). 대표
    홈페이지/인스타/블로그로 이미 채워진 카테고리는 그 이후 같은 카테고리
    URL부터 "추가 링크"로 보낸다 - 카카오채널/유튜브/페이스북/스마트스토어/
    기타는 대표 컬럼으로 승격하지 않고 항상 추가 링크로만 보낸다(요청서 §9
    "카카오채널을 홈페이지 열로 승격하지 마세요").
    """
    homepage = ""
    insta = ""
    blog = ""
    seen_keys: set = set()
    extra_entries: list = []

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
            if not category or not normalized:
                continue
            dedup_key = _dedup_key_for_external_url(normalized)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            if category == "insta" and not insta:
                insta = normalized
            elif category == "blog" and not blog:
                blog = normalized
            elif category == "homepage" and not homepage:
                homepage = normalized
            else:
                extra_entries.append((category, normalized))

    return homepage, insta, blog, _format_extra_links(extra_entries)


def _build_place_url(item: dict) -> str:
    """item에서 플레이스 URL을 구성한다.

    응답에 명시적 URL 필드(placeUrl 등)가 있으면 그 값을 그대로 사용한다.
    없으면 id/place_id로 pcmap 플레이스 URL을 best-effort 구성한다.

    주의: 실제 pcmap URL은 업종별 세그먼트(예: restaurant/cafe)를 쓰는 경우가
    있으나, 리스트 응답만으로는 이를 확정할 수 없어 범용 "place" 세그먼트로
    구성한다.
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
    """네트워크 응답의 업체 item 하나를 exporter.MERGED_COLUMNS(14컬럼)
    row(dict)로 매핑한다(5M-R1: 리뷰 방문자/블로그 분리, 개인 휴대전화 차단,
    URL 유형별 분리, 새로오픈 tri-state - scratchpad/page300_5m_r1_graphql_
    field_provenance_audit에서 확인된 실제 키 사용. PAGE300-6E-V3: 대표
    3링크(홈페이지/인스타/블로그) 외 모든 공개 채널은 "추가 링크"로 보존).

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

    homepage, insta, blog, extra_links = _extract_external_urls(item)
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
        "추가 링크": extra_links,
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
    갱신된다. dedup 키가 비어있는 행(업체명/place_id 모두 없음)은 제외한다.
    """
    unique_rows = []
    for row in rows:
        key = _dedup_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def should_stop_for_target(current_count: int, target: int) -> bool:
    """누적 unique row 수(current_count)가 목표(target)에 도달했는지 판단한다.

    target이 0 이하이면(목표가 없거나 잘못된 값) 항상 False를 반환한다(방어적
    처리 - 의미 없는 target으로 조기 종료하지 않는다).
    """
    if target <= 0:
        return False
    return current_count >= target


def _normalize_text(value) -> str:
    """공백을 정리한 문자열로 정규화한다(None/숫자 등도 안전하게 문자열화)."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


_DIGIT_ONLY_PATTERN = re.compile(r"^\d+$")


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


