"""공식 법정동 선택(시도/시군구/법정동)과 키워드로부터 네이버 플레이스
수집용 query job 목록과 전체 목표 저장 개수를 계산한다.

이 모듈은 GUI 프레임워크를 전혀 참조하지 않는다 - 입력은 순수 값
(문자열/리스트/dict/정수)이며, 출력도 순수 값(query job 목록 또는 목표
개수 정수)이다. src/ui.py의 SalesDbCrawlerApp이 화면 위젯에서 값을 읽어
이 모듈의 함수를 호출하고, 반환된 job 목록/개수를 그대로 orchestrator
(run_collection_plan)와 화면 표시에 사용한다.
"""
import unicodedata


def _sort_korean_names(values: list) -> list:
    """OS locale(strcoll 등)에 의존하지 않는 안정 정렬 - NFC 정규화 후
    코드포인트 비교만 사용한다(§3 시군구 목록 가나다순)."""
    return sorted(values, key=lambda value: unicodedata.normalize("NFC", value))


def _sort_legal_dong_items(items: list[dict]) -> list[dict]:
    """법정동 레코드를 eup_myeon_dong 가나다순으로 안정 정렬한다. 이름이
    같으면 legal_code를 보조 키로 사용해 결과 순서를 결정적으로 만든다
    (§3) - legal_code/선택 상태(BooleanVar 매핑은 legal_code 기준이므로)는
    이 정렬로 전혀 변하지 않는다."""
    return sorted(
        items,
        key=lambda item: (unicodedata.normalize("NFC", item["eup_myeon_dong"]), item["legal_code"]),
    )


def build_legal_dong_query_plan(
    sido: str, sigungu: str, legal_dongs: list[dict], keyword: str, per_query_limit: int,
    *, new_opening_only: bool = False, review_min: int | None = None, review_max: int | None = None,
) -> list[dict]:
    """공식 법정동 Snapshot 기반 선택(시도/시군구/법정동 다중선택)으로 검색
    조합을 만드는 순수 함수(Tk 불필요). job 형태({"region","keyword","query",
    "source_city","source_district","source_subregion","source_layer",
    "legal_code","per_query_limit","new_opening_only"})를 반환해
    _run_network_pipeline/orchestrator에 그대로 흘러가게 한다 - 기본모드/
    홈페이지·SNS 모드가 동일한 이 job 목록을 받는다(§_build_collection_queries).

    법정동을 하나도 선택하지 않으면 시군구(세종처럼 시군구가 없는 지역은
    시도) 단위 검색 조합 1개를 만든다("district" 계층). 법정동을 N개
    선택하면 legal_code로 식별되는 법정동별로 N개의 검색 조합을 만든다
    ("legal_dong" 계층) - 동일 명칭이 여러 시군구에 있어도(예: "신교동") 항상
    올바른 legal_code를 provenance로 유지한다. 공백 정규화를 적용하고, 중복
    쿼리는 제거하되 처음 등장한 순서(=legal_dongs 인자 순서, 화면 표시/선택
    순서 - 호출자가 이미 가나다순으로 정렬해 넘긴다는 전제, §3)를 유지한다.

    new_opening_only(NEW-OPENING-1): UI의 새로오픈 체크박스 값을 그대로
    job에 실어 collect_apollo_first_list_query까지 전달한다 - Query
    문자열 생성에는 영향을 주지 않는다(공식 지역명+키워드만 사용).

    review_min/review_max(NETWORK-CONTROLS-1): UI의 리뷰 최소·최대 입력값을
    동일한 방식으로 job에 실어 전달한다(둘 다 기본 None=필터 비활성).
    """

    def _norm(text: str) -> str:
        return " ".join(text.split())

    jobs: list[dict] = []
    seen_queries: set = set()

    if not legal_dongs:
        region_label = _norm(f"{sido} {sigungu}") if sigungu else _norm(sido)
        query = _norm(f"{region_label} {keyword}")
        if query and query not in seen_queries:
            seen_queries.add(query)
            jobs.append({
                "region": region_label,
                "keyword": keyword,
                "query": query,
                "source_city": sido,
                "source_district": sigungu,
                "source_subregion": "",
                "source_layer": "district",
                "legal_code": "",
                "per_query_limit": per_query_limit,
                "new_opening_only": new_opening_only,
                "review_min": review_min,
                "review_max": review_max,
            })
        return jobs

    for item in legal_dongs:
        eup_myeon_dong = item["eup_myeon_dong"]
        legal_code = item["legal_code"]
        region_label = (
            _norm(f"{sido} {sigungu} {eup_myeon_dong}") if sigungu else _norm(f"{sido} {eup_myeon_dong}")
        )
        query = _norm(f"{region_label} {keyword}")
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)
        jobs.append({
            "region": region_label,
            "keyword": keyword,
            "query": query,
            "source_city": sido,
            "source_district": sigungu,
            "source_subregion": eup_myeon_dong,
            "source_layer": "legal_dong",
            "legal_code": legal_code,
            "per_query_limit": per_query_limit,
            "new_opening_only": new_opening_only,
            "review_min": review_min,
            "review_max": review_max,
        })
    return jobs


def calculate_legal_dong_target_count(per_query_limit: int, query_count: int) -> int:
    """전체 목표 저장 개수 자동 계산: per_query_limit x query_count.
    둘 중 하나라도 0 이하면 0(미계산 상태)을 반환한다 - 호출자가 0을
    "계산 불가"로 취급해 기존 _parse_positive_int 검증에서 자연스럽게
    차단되게 한다(§_start_network_crawl, 새 오류 문구를 따로 만들지 않음)."""
    if per_query_limit <= 0 or query_count <= 0:
        return 0
    return per_query_limit * query_count
