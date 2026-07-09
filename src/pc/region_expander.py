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
