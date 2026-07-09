# ARCH-300C PoC-4: 구 단위 검색어를 동 단위 검색어로 분할하는 순수 로직(기술 검증 단계).
#
# 배경: PoC-3에서 단일 검색어의 깊은 page 전환(page=2→3)이 실제 CAPTCHA를
# 유발함이 확인됐다(PROJECT_STATE.md 2026-07-09 PoC-3 기록). 이에 따라 "한
# 검색어를 깊게 파는" 대신 "여러 동 검색어를 얕게(page=1) 조회해 합산"하는
# 방향으로 전환했다. 이 모듈은 그 첫 단계인 "동 단위 검색어 생성"만 담당한다.
#
# 이 모듈은 직접 API를 호출하지 않는다. 검색어 문자열(dict)만 만들 뿐이며,
# 그 검색어로 브라우저를 실제로 이동시키는 것은 호출자(probe 스크립트 등)의
# 책임이다. 이렇게 분리해야 이 모듈을 live 브라우저 없이 순수 함수로 테스트할
# 수 있다.
#
# 아직 PoC-4 단계이므로 이 모듈은 UI(src/ui.py)나 pipeline(src/pc/pipeline.py)에
# 연결되지 않는다.
#
# PoC-6(REGION-DATA-1 설계 후속): PoC-5에서 법정동/행정동 혼합이 중복 폭증의
# 원인임이 실측으로 확인됨에 따라(PROJECT_STATE.md 2026-07-09 PoC-5 기록),
# 기본 큐는 법정동만 사용하고, 300개 목표에 부족할 때 채울 확장 레이어를
# Tier로 분리한다: Tier1=법정동×업종(build_dong_queries, 기존 유지),
# Tier2=역/상권×업종(build_landmark_queries), Tier3=법정동×세부업종
# (build_subcategory_queries). 세 빌더 모두 build_dong_queries와 동일한
# 순수 함수 원칙(직접 API 호출 없음, 공백/중복/빈 입력 방어)을 따르며,
# build_tiered_query_queue가 이들을 순서대로 이어붙여 tier/source_layer
# 메타를 태깅한다. page=2 이상 pagination은 이 모듈의 책임이 아니다(별도
# 승인 없이는 호출자도 page=1만 사용해야 한다).


def build_dong_queries(city: str, gu: str, dongs, keywords) -> list:
    """구 단위 검색어를 동 단위 검색어 목록으로 분할한다.

    입력:
      city: 시/도 이름(예: "서울특별시").
      gu: 구/군 이름(예: "강동구").
      dongs: 동 이름 문자열의 목록(예: ["천호동", "성내동", "길동"]).
      keywords: 검색 키워드 문자열의 목록(예: ["카페"]).

    출력: 아래 형태의 dict를 담은 list(동 × 키워드 곱, 순서는 dongs → keywords
    순으로 순회).
      {"city": "서울특별시", "gu": "강동구", "dong": "천호동",
       "keyword": "카페", "query": "서울특별시 강동구 천호동 카페"}

    방어적 처리(예외를 던지지 않음):
    - dongs/keywords 각 항목에서 공백만 있거나 빈 문자열인 값은 제외한다.
    - 완전히 동일한 동 이름/키워드 문자열이 여러 번 들어와도 순서를 보존한 채
      1회만 사용한다(dict.fromkeys 기반 중복 제거).
    - city/gu/dongs/keywords 중 하나라도 정규화 후 비어 있으면(city나 gu가
      공백뿐이거나, dongs/keywords가 비어있거나 전부 공백뿐이면) 빈 리스트
      ([])를 반환한다.

    확장 포인트: 여러 시/구를 한 번에 곱집합으로 처리하고 싶다면, 이 함수를
    감싸는 상위 함수(예: build_multi_gu_dong_queries)를 추가한다 - 이 함수
    자체의 city/gu는 단일 값 책임만 진다(단일 책임 유지, 곱집합 확장은 상위
    레이어에서).
    """
    normalized_city = (city or "").strip()
    normalized_gu = (gu or "").strip()
    normalized_dongs = list(dict.fromkeys(d.strip() for d in (dongs or []) if d and d.strip()))
    normalized_keywords = list(dict.fromkeys(k.strip() for k in (keywords or []) if k and k.strip()))

    if not normalized_city or not normalized_gu or not normalized_dongs or not normalized_keywords:
        return []

    queries = []
    for dong in normalized_dongs:
        for keyword in normalized_keywords:
            query = " ".join([normalized_city, normalized_gu, dong, keyword])
            queries.append(
                {
                    "city": normalized_city,
                    "gu": normalized_gu,
                    "dong": dong,
                    "keyword": keyword,
                    "query": query,
                }
            )
    return queries


def _normalize_list(values) -> list:
    """공백/빈 문자열을 제외하고, 순서를 보존한 채 중복을 제거한 문자열 목록을 만든다.

    build_dong_queries에 이미 있던 정규화 로직(공백 strip + dict.fromkeys 중복
    제거)을 Tier2/Tier3 빌더에서도 그대로 재사용하기 위해 뽑아낸 private
    헬퍼다. 외부에 노출하지 않는다(build_dong_queries의 기존 인라인 처리와
    동작이 완전히 동일해야 하므로 build_dong_queries 자체는 건드리지 않는다).
    """
    return list(dict.fromkeys(v.strip() for v in (values or []) if v and v.strip()))


def build_landmark_queries(city: str, gu: str, landmarks, keywords) -> list:
    """Tier2: 역/상권명 단위 검색어를 생성한다(build_dong_queries의 역/상권 버전).

    입력:
      city, gu: build_dong_queries와 동일.
      landmarks: 역/상권명 문자열의 목록(예: ["천호역", "강동역"]).
      keywords: 검색 키워드 문자열의 목록(예: ["카페"]).

    출력: landmark × keyword 곱집합(landmarks → keywords 순회) dict의 list.
      {"city", "gu", "landmark", "keyword", "query",
       "tier": "tier2", "source_layer": "역상권"}

    방어적 처리는 build_dong_queries와 동일하다(공백/빈 문자열 제외, 중복
    제거, city/gu/landmarks/keywords 중 하나라도 비면 빈 리스트 반환).

    법정동과 역/상권 상권명은 지리적으로 겹칠 수 있으므로(예: "천호역" 주변이
    "천호동"과 실제로 겹치는 지역), 이 함수가 만든 쿼리로 수집한 결과는 반드시
    Tier1과 같은 전역 seen(place_id dedup)을 공유해 중복을 흡수해야 한다 -
    이 함수 자체는 dedup을 하지 않는다(검색어 생성만 담당, PoC-4/PoC-5와
    동일한 책임 분리).
    """
    normalized_city = (city or "").strip()
    normalized_gu = (gu or "").strip()
    normalized_landmarks = _normalize_list(landmarks)
    normalized_keywords = _normalize_list(keywords)

    if not normalized_city or not normalized_gu or not normalized_landmarks or not normalized_keywords:
        return []

    queries = []
    for landmark in normalized_landmarks:
        for keyword in normalized_keywords:
            query = " ".join([normalized_city, normalized_gu, landmark, keyword])
            queries.append(
                {
                    "city": normalized_city,
                    "gu": normalized_gu,
                    "landmark": landmark,
                    "keyword": keyword,
                    "query": query,
                    "tier": "tier2",
                    "source_layer": "역상권",
                }
            )
    return queries


def build_subcategory_queries(city: str, gu: str, dongs, subcategories) -> list:
    """Tier3: 같은 법정동을 세부 업종으로 재조회하는 검색어를 생성한다.

    입력:
      city, gu: build_dong_queries와 동일.
      dongs: 법정동 이름 문자열의 목록(예: ["천호동", "성내동", "길동"]) -
        보통 Tier1에서 이미 조회한 동 중 핵심 동만 좁혀서 전달한다(전체 동을
        다시 다 돌리면 쿼리 수만 늘고 신규 기여는 낮을 가능성이 높다는 것이
        PoC-6가 검증하려는 가설 중 하나).
      subcategories: 세부 업종 키워드 목록(예: ["디저트카페", "브런치카페"]).

    출력: dong × subcategory 곱집합(dongs → subcategories 순회) dict의 list.
      {"city", "gu", "dong", "subcategory", "query",
       "tier": "tier3", "source_layer": "세부업종"}

    방어적 처리는 build_dong_queries와 동일하다. keywords 대신 subcategories를
    쓰는 이유는 "카페"(상위 업종)와 "디저트카페"(세부 업종)를 같은 필드에
    섞으면 어떤 게 Tier1이고 어떤 게 Tier3인지 쿼리 dict만 보고 구분할 수
    없어지기 때문이다(tier/source_layer 필드로도 구분되지만, 필드명 자체도
    의미를 분리해 이중으로 방어한다).
    """
    normalized_city = (city or "").strip()
    normalized_gu = (gu or "").strip()
    normalized_dongs = _normalize_list(dongs)
    normalized_subcategories = _normalize_list(subcategories)

    if not normalized_city or not normalized_gu or not normalized_dongs or not normalized_subcategories:
        return []

    queries = []
    for dong in normalized_dongs:
        for subcategory in normalized_subcategories:
            query = " ".join([normalized_city, normalized_gu, dong, subcategory])
            queries.append(
                {
                    "city": normalized_city,
                    "gu": normalized_gu,
                    "dong": dong,
                    "subcategory": subcategory,
                    "query": query,
                    "tier": "tier3",
                    "source_layer": "세부업종",
                }
            )
    return queries


def build_tiered_query_queue(
    city: str,
    gu: str,
    *,
    keywords=None,
    legal_dongs=None,
    subcategory_dongs=None,
    subcategories=None,
    landmarks=None,
    enabled_tiers=("tier1", "tier3", "tier2"),
) -> list:
    """Tier1/Tier2/Tier3 검색어를 지정된 순서로 이어붙여 하나의 큐로 조합한다.

    입력:
      city, gu: 세 Tier 공통.
      keywords: Tier1(법정동)과 Tier2(역/상권)가 공유하는 업종 키워드 목록
        (예: ["카페"]) - 같은 업종을 법정동과 역/상권 양쪽에서 조회하는 것이
        PoC-6의 목적이므로 별도 키워드를 받지 않는다.
      legal_dongs: Tier1 대상 법정동 목록.
      subcategory_dongs: Tier3 대상 법정동 목록(보통 legal_dongs의 부분집합 -
        세부업종 확장을 검증할 핵심 동만 좁혀서 전달).
      subcategories: Tier3 세부 업종 목록.
      landmarks: Tier2 대상 역/상권 목록.
      enabled_tiers: 포함할 Tier와 실행 순서를 함께 지정하는 문자열 목록/튜플
        (기본값은 PoC-6 실행 순서인 "법정동 baseline → 세부업종 확장 →
        역/상권 확장"). 각 tier 이름에 대응하는 입력이 비어 있으면(예:
        landmarks=[]) 해당 tier는 자연히 빈 리스트를 반환하므로 결과에
        아무것도 추가되지 않는다.

    출력: enabled_tiers 순서대로 이어붙인 쿼리 dict의 list(각 항목에 이미
    tier/source_layer가 태깅되어 있음 - build_dong_queries만 예외적으로
    tier/source_layer가 없으므로 여기서 채워 넣는다).

    이 함수는 각 Tier 빌더를 호출만 할 뿐 자체적으로 dedup을 하지 않는다 -
    Tier 간 dedup(전역 seen 공유)은 호출자(probe 스크립트)의 책임이다
    (network_list_scraper.dedup_rows를 여러 Tier에 걸쳐 재사용하는 기존
    PoC-4/PoC-5 패턴과 동일).
    """
    tier_builders = {
        "tier1": lambda: [
            {**q, "tier": "tier1", "source_layer": "법정동"}
            for q in build_dong_queries(city, gu, legal_dongs, keywords)
        ],
        "tier2": lambda: build_landmark_queries(city, gu, landmarks, keywords),
        "tier3": lambda: build_subcategory_queries(city, gu, subcategory_dongs, subcategories),
    }

    queue = []
    for tier_name in enabled_tiers or []:
        builder = tier_builders.get(tier_name)
        if builder is None:
            continue
        queue.extend(builder())
    return queue
