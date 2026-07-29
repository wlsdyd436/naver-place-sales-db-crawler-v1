# ARCH-300C WIRE-2A: 쿼리 1개 단위 Network 응답 관찰 함수.
#
# 이 모듈은 이미 생성된 Playwright page(또는 FakePage)를 전달받아 검색 쿼리
# 1개만 처리하는 collect_network_query()와, 브라우저/context를 큐 전체에서
# 공유하며 쿼리마다 새 page를 생성/종료하는 생명주기 관리자
# NetworkBrowserCollector(WIRE-2B-1)를 함께 담는다. collect_network_query
# 자체는 여전히 브라우저를 직접 launch하지 않으므로 live 실행 없이 FakePage
# 주입만으로 검증할 수 있고, NetworkBrowserCollector도 session_factory에
# FakeSession을 주입하면 실제 Playwright 없이 생명주기(page 생성/종료 횟수,
# teardown 순서)만 검증할 수 있다.
#
# ARCH-300 PoC-1~9A(브라우저 네트워크 응답 관찰 기반 리스트 수집 기술 검증)의
# 연장선이며, PoC-7에서 검증된 검색 URL 형식·CAPTCHA probe 흐름을 그대로
# 재사용한다. is_candidate_response/_extract_list_items/_map_item_to_row/
# dedup_rows/classify_captcha_signal은 src/pc/network_list_scraper.py에서
# 읽기 전용으로 재사용하며 재구현하지 않는다.
#
# page=1만 수집한다: 페이지네이션 클릭, 카드 클릭, entryIframe 진입 코드는
# 이 모듈에 존재하지 않는다(존재하지 않는 것 자체가 page=1 보장이다).
# CAPTCHA DOM 제거/클릭/자동 해결/우회는 시도하지 않는다 - 감지된 신호는
# 반환 dict의 플래그로만 전달하며, 중단 여부 판단은 이 함수를 호출하는
# 상위 orchestrator(run_collection_plan, WIRE-1)의 책임이다.
#
# WIRE-2A-B: page.goto()에서 발생 가능한 예외는 성격이 다르다. 실제 Playwright
# TimeoutError(느린 로드)만 timeout=True로 분류하고, "page/context/browser가
# 이미 닫힘(Target closed)"·"브라우저 실행 장애"·"일반 navigation 오류" 등
# 그 외 예외는 timeout으로 위장하지 않고 navigation_error로 별도 분류한다
# (browser_session.goto와 동일하게 PlaywrightTimeoutError만 관용적으로 흡수).
import json
import time
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pc.apollo_list_adapter import (
    build_rows_from_apollo_list_result,
    extract_main_place_list_from_apollo,
    extract_new_opening_place_list_from_apollo,
)
from src.pc.browser_session import _CAPTCHA_PROBE_SELECTORS
from src.pc.detail_scraper import (
    _CONSECUTIVE_FAILURE_LIMIT,
    _DETAIL_RETRY,
    _entry_title,
    _extract_entry_address,
    _extract_entry_phone,
    _extract_entry_sns,
    _title_matches,
)
from src.pc.naver_region_policy import (
    OFFICIAL_EXACT,
    OUT_OF_SCOPE,
    PROVIDER_ALIAS_EXACT,
    REGION_UNVERIFIED,
    classify_region_match,
)
from src.pc.network_list_scraper import (
    GlobalPlaceAccumulator,
    _extract_list_items,
    _is_personal_mobile_phone,
    _map_item_to_row,
    build_entity_index,
    build_place_url_from_id,
    classify_captcha_signal,
    compute_page_signature,
    dedup_membership_rows,
    dedup_rows,
    extract_normalized_apollo_detail,
    is_candidate_response,
    is_skeleton_dom_row,
    merge_detail_into_row,
    merge_dom_row_fields,
    normalize_dom_row,
    overall_row_confidence,
    page_transition_confirmed,
    resolve_match,
    summarize_membership_diagnostics,
    to_common_entity,
    trim_membership_rows_to_target,
)

_SEARCH_URL_TEMPLATE = "https://map.naver.com/v5/search/{query}"

# ARCH-300C PERF-1A: 적응형 settle 종료 상수(모듈 상수로만 고정 - 이번 단계에서
# collect_network_query 시그니처나 UI에는 노출하지 않는다). settle_ms(기존
# 파라미터, 기본 5000)는 "무조건 기다리는 시간"에서 "최대 대기 hard cap"으로
# 의미가 바뀌었고, 파싱 가능한(비어있지 않은) 업체 목록 응답을 확인한 뒤
# _QUIET_PERIOD_MS 동안 추가 후보가 도착하지 않으면 hard cap 전에 조기
# 종료한다. 750/100이라는 구체적인 값은 WIRE-4C(실제 네이버, 300건 규모)
# 관찰에서 얻은 잠정치이며, candidate 응답들 사이의 실제 도착 간격(inter-arrival
# gap)을 직접 계측한 적은 아직 없다 - 다음 live 검증 단계(WIRE-5 등)에서
# 이 값의 적정성을 실측으로 재확인해야 한다(반대 검토 AI 지적 사항).
_QUIET_PERIOD_MS = 750
_POLL_INTERVAL_MS = 100

# ARCH-300C PAGE-300-2B-1: 검색 조합당 상한이 첫 페이지(약 20건)를 넘어설 때
# 목록 하단 페이지 번호를 순차 클릭해 추가 candidate response를 누적하는
# 제한 구현의 내부 안전 상한. 초기 page 1을 포함해 최대 5페이지(추가 클릭
# 최대 4회, 약 100건 범위)까지만 진행하며, 그 이상(다음 페이지 번호 묶음
# 전환)은 이번 단계 범위가 아니다 - 300건 지원 완료를 의미하지 않는다
# (PAGE-300-PoC-B2 실측 근거: page300_poc_b2_report.md). UI/공개 API에는
# 노출하지 않는다.
_MAX_PAGINATION_PAGES = 5

# PAGE-300-2B-1-FIX §4: 다음 페이지 버튼을 클릭하기 직전, 아직 처리되지 않은
# candidate response가 남아있는지 짧게 확인하는 bounded quiet 구간(전체 첫
# settle의 _QUIET_PERIOD_MS(750ms)보다 훨씬 짧다 - 이미 도착해 있는(또는
# 막 도착하는) 응답의 존재만 재확인하는 목적이지 새 페이지 로드를 기다리는
# 것이 아니기 때문이다). 목표 페이지 버튼을 실제로 찾아 클릭이 임박한 경우
# (_drain_pending_responses가 호출되는 경우)에만 소모되며, 클릭을 시도하지
# 않는 단일 페이지 호출부나 pagination_exhausted로 종료되는 경로에는 영향이
# 없다.
_PENDING_DRAIN_QUIET_MS = 200

# PAGE-300-2B-2B: candidate response body의 안전 상한(바이트). PAGE-300-2B-2A
# 실측(page 2 candidate 응답 약 414KB)보다 넉넉한 여유를 두되, 메모리 폭주를
# 막기 위한 상한이다 - 초과하면 body 자체는 저장하지 않고 에러로만 기록한다.
_MAX_CANDIDATE_BODY_BYTES = 2 * 1024 * 1024

# PAGE-300-2B-2D §4: candidate별 안전 진단(candidate_snapshot_diagnostics)에서
# 원본 body를 노출하지 않고도 인코딩/구조 단서를 남기기 위한 순수 분류
# 헬퍼들이다. 셋 다 raw byte prefix 자체를 반환하지 않고 enum 성격의 짧은
# 문자열만 반환한다 - 압축 해제나 charset 추측 재시도는 절대 하지 않는다
# (§6, 실제 magic/header 근거가 확인되기 전까지 decompression 구현 금지).
_BOM_PREFIXES = (
    (b"\xff\xfe\x00\x00", "utf32_le"),
    (b"\x00\x00\xfe\xff", "utf32_be"),
    (b"\xef\xbb\xbf", "utf8"),
    (b"\xff\xfe", "utf16_le"),
    (b"\xfe\xff", "utf16_be"),
)
_WHITESPACE_BYTES = (0x20, 0x09, 0x0A, 0x0D, 0x00)

# PAGE-300-2B-4A §5: candidate 처리 단계에서 확인된 candidate_error_type을
# pagination_stop_reason으로 변환하는 우선순위 매핑(dict 순서 = 우선순위 -
# HTTP 오류가 non-JSON 판정보다 먼저 확인된다). 이 두 값은 JSON decode를
# "시도조차 하지 않은" 경우에만 설정되므로(§3/§4), 기존 candidate_json_decode_
# error(실제 decode를 시도했다가 실패한 경우)와 명확히 구분된다.
_CANDIDATE_ERROR_STOP_REASONS = {
    "CandidateHttpError": "candidate_http_error",
    "NonJsonCandidateBody": "candidate_non_json_response",
}


def _classify_candidate_http_status(status) -> str:
    """PAGE-300-2B-4A(gpt-5.6-sol 독립 검토 지적, Medium 반영): status는
    response 이벤트 시점에 이미 알 수 있으므로, body snapshot 성공/실패와
    무관하게 candidate 등록 즉시 분류한다 - 이전에는 이 판정이
    body_snapshot_ready 분기 안에만 있어 EmptyBody/BodyTooLarge/RequestFailed
    등으로 snapshot 자체가 실패한 non-2xx candidate(예: HTTP 429 + 빈 body)가
    candidate_http_error_count/candidate_http_status_counts에 전혀 반영되지
    않았다(안전성에는 영향 없음 - candidate_snapshot_error로 이미 pagination이
    중단되지만, 진단 완전성이 떨어졌다). status가 None이면(예: response를
    전혀 받지 못한 requestfailed 전용 synthetic entry) 빈 문자열을 반환한다."""
    if status is not None and not (200 <= status <= 299):
        return "CandidateHttpError"
    return ""


def _url_kind(url: str) -> str:
    """candidate URL을 안전한 enum 라벨로만 요약한다(전체 query string은
    진단에 남기지 않는다 - §4)."""
    lowered = (url or "").lower()
    if "allsearch" in lowered:
        return "all_search"
    if "graphql" in lowered:
        return "graphql_candidate"
    return "other_candidate"


def _classify_bom(body: bytes) -> str:
    for prefix, label in _BOM_PREFIXES:
        if body.startswith(prefix):
            return label
    return "none"


def _classify_compression_magic(body: bytes) -> str:
    if body.startswith(b"\x1f\x8b"):
        return "gzip"
    if len(body) >= 2 and body[0] == 0x78 and body[1] in (0x01, 0x5E, 0x9C, 0xDA):
        return "zlib"
    if body and body[0] >= 0x80:
        return "unknown_binary"
    return "none"


def _classify_first_non_whitespace_character(body: bytes) -> str:
    """§4: BOM 접두부와 ASCII 공백을 건너뛴 뒤 첫 바이트만 4가지 enum으로
    분류한다. body 자체(원문)는 반환하지 않는다."""
    if not body:
        return "empty"
    index = 0
    for prefix, _label in _BOM_PREFIXES:
        if body.startswith(prefix):
            index = len(prefix)
            break
    while index < len(body) and body[index] in _WHITESPACE_BYTES:
        index += 1
    if index >= len(body):
        return "empty"
    char = body[index]
    if char == 0x7B:
        return "{"
    if char == 0x5B:
        return "["
    if char == 0x3C:
        return "<"
    return "other"


def _summarize_candidate_snapshots(candidates: list, parsed_cache: dict | None = None) -> dict:
    """PAGE-300-2B-2D(gpt-5.6-sol 독립 검토 지적, Medium 반영): candidate 목록에서
    body snapshot 3분류(success/error/pending)와 안전 진단(candidate_snapshot_
    diagnostics)을 계산하는 단일 지점이다. navigation_error 조기 반환과 정상
    반환 경로가 이 함수를 공유해야, "response/requestfinished가 goto() 예외
    발생 전에 이미 도착했을 수 있는" edge case에서도 success+error+pending==
    candidate_response_count 불변식이 모든 반환 경로에서 항상 성립한다(수정
    전에는 navigation_error 조기 반환이 이미 관측된 candidate가 있어도 전부
    0/빈 리스트로 고정해 불변식이 깨질 수 있었다). parsed_cache가 없으면(예:
    navigation_error 조기 반환처럼 JSON 파싱 자체가 아직 시도되지 않은 시점)
    json_decode_error_count는 0으로 둔다."""
    parsed_cache = parsed_cache or {}
    diagnostics = []
    for e in candidates:
        body = e.get("body_snapshot")
        if e["body_snapshot_ready"]:
            state = "success"
        elif e["body_snapshot_error_type"] == "EmptyBody":
            state = "empty"
        elif e["body_snapshot_error_type"]:
            state = "error"
        else:
            state = "pending"
        diagnostics.append({
            "sequence_id": e["sequence_id"],
            "url_kind": _url_kind(e["url"]),
            "method": e["method"],
            "resource_type": e["resource_type"],
            "status": e["status"],
            "content_type": e.get("content_type", ""),
            "content_encoding": e.get("content_encoding", ""),
            "body_snapshot_state": state,
            "body_snapshot_size": e["body_snapshot_size"],
            "body_snapshot_error_type": e["body_snapshot_error_type"],
            "json_top_level_type": e.get("json_top_level_type", ""),
            "json_decode_error_type": e.get("json_decode_error_type", ""),
            "candidate_error_type": e.get("candidate_error_type", ""),
            "first_non_whitespace_character": (
                _classify_first_non_whitespace_character(body) if body is not None else "empty"
            ),
            "bom_type": _classify_bom(body) if body is not None else "none",
            "compression_magic": _classify_compression_magic(body) if body is not None else "none",
            "processed": e["processed"],
            "generation": e["generation"],
        })
    success = sum(1 for e in candidates if e["body_snapshot_ready"])
    error = sum(1 for e in candidates if (not e["body_snapshot_ready"]) and e["body_snapshot_error_type"])
    pending = sum(1 for e in candidates if (not e["body_snapshot_ready"]) and not e["body_snapshot_error_type"])
    empty = sum(1 for e in candidates if e["body_snapshot_error_type"] == "EmptyBody")
    total_bytes = sum(e["body_snapshot_size"] for e in candidates if e["body_snapshot_ready"])
    # PAGE-300-2B-4A: json_decode_error_count는 "실제로 json.loads를 시도했다가
    # 실패한" candidate만 세야 한다(§3 "JSON decode 자체를 시도하지 않았기
    # 때문이다") - candidate_http_error/non_json 판정은 json.loads 호출 이전에
    # 이미 반환되므로 entry["json_decode_error_type"]이 채워지지 않는다. 기존
    # parsed_cache 기반 계산은 "harvest 단계에서 error로 확정된 모든 candidate"를
    # 뭉뚱그렸으므로(§candidate_error_type 도입 전에는 둘이 같았음), 이제는
    # json_decode_error_type 필드 자체로 정밀하게 판별한다.
    json_decode_error_count = sum(
        1 for e in candidates
        if e["body_snapshot_ready"] and e.get("json_decode_error_type")
    )
    candidate_http_error_count = sum(1 for e in candidates if e.get("candidate_error_type") == "CandidateHttpError")
    candidate_non_json_count = sum(1 for e in candidates if e.get("candidate_error_type") == "NonJsonCandidateBody")
    candidate_http_status_counts: dict = {}
    for e in candidates:
        if e.get("candidate_error_type") == "CandidateHttpError":
            key = str(e.get("status"))
            candidate_http_status_counts[key] = candidate_http_status_counts.get(key, 0) + 1
    # PAGE-300-2B-4A §7: "정상적으로 성공(snapshot 성공 + candidate/decode 오류
    # 전혀 없음)"이 아닌 candidate를 전부 합산한 총계 - snapshot 자체가 실패/
    # 미확정인 경우(error/empty/pending)와 snapshot은 성공했지만 candidate
    # HTTP 오류/non-JSON/decode 실패인 경우를 모두 포함한다.
    candidate_processing_error_count = sum(
        1 for e in candidates
        if (not e["body_snapshot_ready"]) or e.get("candidate_error_type") or e.get("json_decode_error_type")
    )
    return {
        "body_snapshot_success_count": success,
        "body_snapshot_error_count": error,
        "snapshot_pending_count": pending,
        "body_snapshot_empty_count": empty,
        "body_snapshot_total_bytes": total_bytes,
        "json_decode_error_count": json_decode_error_count,
        "candidate_http_error_count": candidate_http_error_count,
        "candidate_non_json_count": candidate_non_json_count,
        "candidate_http_status_counts": candidate_http_status_counts,
        "candidate_processing_error_count": candidate_processing_error_count,
        "candidate_snapshot_diagnostics": diagnostics,
    }


class _QueryObservationContext:
    """쿼리 1회 호출에 국한된 로컬 상태(전역/클래스 공용 상태를 두지 않기 위함).

    handler는 이 인스턴스에만 기록하며, collect_network_query 호출이 끝나면
    함께 버려진다 - 다음 쿼리는 항상 새 인스턴스로 시작하므로 이전 쿼리의
    응답과 섞이지 않는다(페이지 자체도 WIRE-2B부터는 쿼리마다 새로 생성/종료될
    예정이라 이중으로 격리된다).
    """

    def __init__(self):
        # PAGE-300-2B-2B: candidate 하나당 raw response 객체 대신 candidate
        # entry(dict)를 담는다(§candidate entry 계약) - 인덱스 순서(도착 순서)
        # 의미는 기존과 동일하게 유지하면서, 내용물만 "나중에 body에 다시
        # 접근 가능한 response 객체"에서 "이미 확보한 snapshot(bytes) 여부를
        # 담은 entry"로 바뀐다.
        self.candidates: list = []
        self.candidate_response_count = 0
        self.status_429_seen = False
        # PAGE-300-2B-1-FIX §3: 같은 response 객체가 브라우저에서 'response'
        # 이벤트를 중복 발생시키는 극단적인 경우에도 object identity(id())로
        # 한 번만 기록한다 - 인덱스가 아니라 객체 자체를 키로 써야, 동일 객체가
        # 두 번 append돼 서로 다른 인덱스로 두 번 harvest(JSON parse 2회)되는
        # 것을 막을 수 있다. response 객체는 candidates에 계속 참조로 남아있으므로
        # (쿼리 종료 전까지) id() 재사용(GC) 위험이 없다.
        self.seen_response_ids: set = set()
        # PAGE-300-2B-2B: requestfinished/requestfailed는 request 객체를 받으므로
        # (response가 아니라), id(request) -> candidate entry로 역참조할 수 있어야
        # 한다. response 이벤트가 먼저 도착해 candidate로 판별될 때만 이 맵에
        # 등록되므로, candidate가 아닌 request는 이 맵에 없고 두 핸들러는 즉시
        # no-op으로 반환한다.
        self.request_id_to_candidate: dict = {}
        # PAGE-300-2B-2B: 순수 진단용 로컬 라벨(§candidate entry의 generation) -
        # "지금까지 확정된 페이지 수 + 1"을 기록할 뿐, response 내용으로 실제
        # 네이버 page를 추측하는 것과 무관하다(우리가 클릭을 시도한 시점 기준
        # 로컬 카운터일 뿐이라 "페이지 번호 추측 금지" 원칙과 충돌하지 않는다).
        self.current_generation = 1
        # PAGE-300-2B-2D §5: request-response 연결 무결성 진단. 정상 경로에서는
        # 항상 0이어야 하며, 0보다 크면 candidate identity 매칭이 깨졌다는 뜻이다.
        self.unmatched_requestfinished_count = 0
        self.ambiguous_request_mapping_count = 0


def _make_response_handler(ctx: _QueryObservationContext):
    """response handler는 최소 작업만 한다(상태 확인 + candidate entry 등록) -
    PAGE-300-2B-2B: body snapshot도 JSON 파싱도 이 handler에서 하지 않는다
    (response 본문을 읽는 메서드는 전혀 호출하지 않음 - 정적 검사로 회귀
    고정). body snapshot은 requestfinished handler가, JSON 파싱은 harvest
    단계가 각각 책임진다."""

    def handle_response(response) -> None:
        try:
            if response.status == 429:
                ctx.status_429_seen = True
        except Exception:
            pass

        try:
            request = response.request
        except Exception:
            request = None

        try:
            resource_type = request.resource_type if request is not None else ""
        except Exception:
            resource_type = ""
        url = response.url or ""

        try:
            if is_candidate_response(url, resource_type):
                response_id = id(response)
                if response_id in ctx.seen_response_ids:
                    return
                ctx.seen_response_ids.add(response_id)
                # 방어적 dedupe: 같은 request가 이미 candidate로 등록돼 있으면
                # (이론상 발생하지 않아야 하지만) entry를 중복 생성하지 않는다.
                # PAGE-300-2B-2D §5: 이 경우가 바로 "하나의 request가 둘 이상의
                # response/candidate에 연결되려는" ambiguous 상황이다 - 두 번째
                # entry를 만들지 않음으로써 "snapshot을 성공 처리하지 않음"
                # 요구사항을 이미 만족하며, 여기서는 그 사실을 진단 카운터로
                # 남긴다.
                if request is not None and id(request) in ctx.request_id_to_candidate:
                    ctx.ambiguous_request_mapping_count += 1
                    return
                try:
                    status = response.status
                except Exception:
                    status = None
                try:
                    method = request.method if request is not None else ""
                except Exception:
                    method = ""
                entry = {
                    "sequence_id": ctx.candidate_response_count,
                    "response": response,
                    "request": request,
                    "url": url,
                    "method": method,
                    "resource_type": resource_type,
                    "status": status,
                    "content_type": "",
                    "content_encoding": "",
                    "body_snapshot": None,
                    "body_snapshot_ready": False,
                    "body_snapshot_error_type": "",
                    "body_snapshot_error_message": "",
                    "body_snapshot_size": 0,
                    "json_top_level_type": "",
                    "json_decode_error_type": "",
                    "candidate_error_type": _classify_candidate_http_status(status),
                    "processed": False,
                    "generation": ctx.current_generation,
                }
                ctx.candidates.append(entry)
                ctx.candidate_response_count += 1
                if request is not None:
                    ctx.request_id_to_candidate[id(request)] = entry
        except Exception:
            pass

    return handle_response


def _make_request_finished_handler(ctx: _QueryObservationContext):
    """PAGE-300-2B-2B: requestfinished 시점에 candidate body를 즉시 bytes로
    snapshot한다(PAGE-300-2B-2A 실측 원인 - 지연된 시점의 response.json()/
    body()는 "Response body is unavailable"로 실패할 수 있으므로, 완료
    직후 안전한 시점에만 접근한다). candidate가 아닌 request는 즉시 무시하고,
    이미 resolve된 entry(중복 이벤트)도 idempotent하게 무시한다. 어떤 예외도
    밖으로 던지지 않는다."""

    def handle_request_finished(request) -> None:
        try:
            entry = ctx.request_id_to_candidate.get(id(request))
            if entry is None:
                # PAGE-300-2B-2D §5: candidate로 등록된 적 없는 request의
                # requestfinished는 대부분 정상이다(이미지/스크립트 등 애초에
                # candidate가 아닌 리소스도 requestfinished를 발생시킨다).
                # candidate URL/resource_type 패턴과 일치하는데도 매핑이 없는
                # 경우에만 진짜 이상 신호(연결 실패)로 집계한다.
                try:
                    unmatched_url = request.url or ""
                except Exception:
                    unmatched_url = ""
                try:
                    unmatched_resource_type = request.resource_type
                except Exception:
                    unmatched_resource_type = ""
                if is_candidate_response(unmatched_url, unmatched_resource_type):
                    ctx.unmatched_requestfinished_count += 1
                return
            if entry["body_snapshot_ready"] or entry["body_snapshot_error_type"]:
                return
            # PAGE-300-2B-2D(gpt-5.6-sol 독립 검토 지적, High): request.response()를
            # 다시 호출하면, 이 request 객체가 (이론상 발생하지 않아야 하지만)
            # candidate 등록 이후 다른 response를 참조하도록 바뀌었을 경우 이
            # entry의 메타데이터(url/status 등은 candidate A)와 실제로 snapshot되는
            # body(response B)가 서로 다른 candidate의 것으로 뒤섞일 수 있다.
            # entry["response"]는 candidate 등록 시점(response handler)에 이미
            # 확정된 참조이므로 이를 우선 사용해 정체성을 고정한다 - request.
            # response()로의 재조회는 entry["response"]가 없는 경우(예: 향후
            # 다른 등록 경로)에 한해서만 fallback으로 사용한다.
            response = entry.get("response")
            if response is None:
                try:
                    response = request.response()
                except Exception as exc:
                    entry["body_snapshot_error_type"] = type(exc).__name__
                    entry["body_snapshot_error_message"] = str(exc)[:200]
                    return
            if response is None:
                entry["body_snapshot_error_type"] = "NoResponse"
                entry["body_snapshot_error_message"] = "request.response()가 None을 반환함"
                return
            # PAGE-300-2B-2B(gpt-5.6-sol 독립 검토 지적): response.body()는
            # 전체 body를 메모리에 만든 뒤에야 길이를 알 수 있어 크기 검사
            # 만으로는 할당 자체를 막지 못한다 - content-length 헤더를 먼저
            # 확인할 수 있으면 body()를 아예 호출하지 않고 조기에 거른다
            # (헤더가 없거나 파싱 불가하면 기존처럼 body() 이후 길이로만 판단).
            try:
                entry["content_type"] = response.headers.get("content-type") or ""
            except Exception:
                entry["content_type"] = ""
            try:
                entry["content_encoding"] = response.headers.get("content-encoding") or ""
            except Exception:
                entry["content_encoding"] = ""
            try:
                content_length_header = response.headers.get("content-length")
            except Exception:
                content_length_header = None
            if content_length_header is not None:
                try:
                    content_length = int(content_length_header)
                except (TypeError, ValueError):
                    content_length = None
                if content_length is not None and content_length > _MAX_CANDIDATE_BODY_BYTES:
                    entry["body_snapshot_error_type"] = "BodyTooLarge"
                    entry["body_snapshot_error_message"] = (
                        f"content-length {content_length} bytes exceeds {_MAX_CANDIDATE_BODY_BYTES} bytes cap"
                    )
                    entry["body_snapshot_size"] = content_length
                    return
            try:
                body = response.body()
            except Exception:
                try:
                    body = response.text().encode("utf-8")
                except Exception as exc2:
                    entry["body_snapshot_error_type"] = type(exc2).__name__
                    entry["body_snapshot_error_message"] = str(exc2)[:200]
                    return
            # PAGE-300-2B-2D §3: 빈 body(0바이트)는 성공이 아니다 - json.loads(b"")는
            # 항상 실패하므로 JSON decode 실패로 미루지 않고 이 시점에 별도
            # 오류 타입으로 확정한다(PAGE-300-2B-2C의 "success_count=2인데
            # total_bytes가 page1 크기만"이던 모순의 유력 원인 - 빈 snapshot이
            # 성공으로 잘못 집계됐을 가능성).
            if len(body) == 0:
                entry["body_snapshot_error_type"] = "EmptyBody"
                entry["body_snapshot_error_message"] = "response body가 0바이트입니다"
                entry["body_snapshot_size"] = 0
                return
            if len(body) > _MAX_CANDIDATE_BODY_BYTES:
                entry["body_snapshot_error_type"] = "BodyTooLarge"
                entry["body_snapshot_error_message"] = (
                    f"{len(body)} bytes exceeds {_MAX_CANDIDATE_BODY_BYTES} bytes cap"
                )
                entry["body_snapshot_size"] = len(body)
                return
            entry["body_snapshot"] = body
            entry["body_snapshot_ready"] = True
            entry["body_snapshot_size"] = len(body)
        except Exception:
            pass

    return handle_request_finished


def _make_request_failed_handler(ctx: _QueryObservationContext):
    """PAGE-300-2B-2B: requestfailed 시점에 candidate를 실패로 표시한다(retry는
    하지 않는다 - 사실만 기록). idempotent하게, 이미 resolve된 entry는
    건드리지 않는다.

    gpt-5.6-sol 독립 검토 지적(2차) 반영: response를 전혀 받지 못하고 실패한
    request는 'response' 이벤트가 한 번도 발생하지 않으므로
    ctx.request_id_to_candidate에 등록될 기회가 없었다 - 다른 candidate가
    정상 성공해 per_query_limit에 도달하면 이 실패가 진단에서 완전히
    사라져(parse_error_count/body_snapshot_error_count 어디에도 반영되지
    않음) 거짓 성공처럼 보일 위험이 있었다. 이제 등록된 적 없는 request도
    request.url/resource_type만으로 candidate 여부를 판별해(§response
    handler와 동일한 is_candidate_response 판정 - response 객체 접근은
    필요 없다), candidate였다면 실패 entry를 새로 만들어 harvest 시점에
    parse_error_count/body_snapshot_error_count에 반영되게 한다."""

    def handle_request_failed(request) -> None:
        try:
            entry = ctx.request_id_to_candidate.get(id(request))
            if entry is not None:
                if entry["body_snapshot_ready"] or entry["body_snapshot_error_type"]:
                    return
            else:
                try:
                    url = request.url or ""
                except Exception:
                    url = ""
                try:
                    resource_type = request.resource_type
                except Exception:
                    resource_type = ""
                if not is_candidate_response(url, resource_type):
                    return
                try:
                    method = request.method
                except Exception:
                    method = ""
                entry = {
                    "sequence_id": ctx.candidate_response_count,
                    "response": None,
                    "request": request,
                    "url": url,
                    "method": method,
                    "resource_type": resource_type,
                    "status": None,
                    "content_type": "",
                    "content_encoding": "",
                    "body_snapshot": None,
                    "body_snapshot_ready": False,
                    "body_snapshot_error_type": "",
                    "body_snapshot_error_message": "",
                    "body_snapshot_size": 0,
                    "json_top_level_type": "",
                    "json_decode_error_type": "",
                    "candidate_error_type": "",
                    "processed": False,
                    "generation": ctx.current_generation,
                }
                ctx.candidates.append(entry)
                ctx.candidate_response_count += 1
                ctx.request_id_to_candidate[id(request)] = entry

            entry["body_snapshot_error_type"] = "RequestFailed"
            try:
                failure = request.failure
                message = str(failure) if failure else ""
            except Exception:
                message = ""
            entry["body_snapshot_error_message"] = message[:200]
        except Exception:
            pass

    return handle_request_failed


def _probe_captcha_state(page) -> dict:
    """PoC-7 _probe_captcha_presence와 동일한 방식으로 CAPTCHA DOM 상태를 관찰한다.

    marker가 DOM에 존재한다는 사실만으로 active로 단정하지 않는다(오탐 방지 -
    classify_captcha_signal이 visible+면적까지 함께 봐야 active로 판정한다).
    클릭을 전혀 하지 않으므로 click_intercepted_message는 항상 빈 문자열이다.
    """
    marker_present = False
    visible = False
    area = 0.0
    for selector in _CAPTCHA_PROBE_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            marker_present = True
            if locator.is_visible(timeout=300):
                visible = True
                box = locator.bounding_box()
                if box:
                    area = max(area, float(box.get("width", 0)) * float(box.get("height", 0)))
        except Exception:
            continue
    return {
        "marker_present": marker_present,
        "visible": visible,
        "bounding_box_area": area,
        "click_intercepted_message": "",
    }


def _find_search_frame(page):
    """PAGE-300-2B-1: src/pc/browser_session.py의 BrowserSession.find_search_frame
    과 동일한 폴백 순서(name -> frame_locator+body wait -> frames 스캔)를
    collect_network_query 전용으로 재구현한다 - 이 함수는 BrowserSession
    인스턴스가 아니라 bare page만 받으므로 그 메서드를 직접 호출할 수 없다
    (browser_session.py는 이번 단계 수정 금지 범위).

    이 함수는 어떤 예외도 밖으로 내보내지 않는다 - frame API를 전혀 구현하지
    않은 기존 FakePage(단일 페이지 no-live 테스트 전용)에서도 안전하게 None을
    반환해야, per_query_limit이 첫 페이지 결과보다 큰 기존 테스트들이 실수로
    pagination을 "시도"하더라도(§collect_network_query 진입 조건) 예외 없이
    즉시 pagination_exhausted로 안전 종료되어 기존 단일 페이지 반환값이
    전혀 달라지지 않는다.
    """
    try:
        frame = page.frame(name="searchIframe")
        if frame:
            return frame
    except Exception:
        pass
    try:
        frame_locator = page.frame_locator("#searchIframe")
        frame_locator.locator("body").first.wait_for(timeout=5000)
        frame = page.frame(name="searchIframe")
        if frame:
            return frame
    except Exception:
        pass
    try:
        for frame in page.frames:
            frame_id = f"{frame.name} {frame.url}".lower()
            if "search" in frame_id:
                return frame
    except Exception:
        pass
    return None


def _find_page_button(frame, target_page_number: int):
    """PAGE-300-2B-1 §9: role="button"이며 텍스트가 목표 페이지 번호와 정확히
    일치하는 요소만 찾는다. has_text(부분 문자열 포함) 방식은 "2"를 찾을 때
    "12"·"20" 같은 다른 페이지 번호나 업체 본문의 숫자와 오매칭될 수 있어
    사용하지 않는다 - exact=True로 정확한 문자열 일치만 허용한다. 여러 개가
    일치하면(ambiguous) 호출자가 count()로 판단해 클릭하지 않는다(이 함수는
    locator만 반환하고 클릭 여부는 판단하지 않음).
    """
    try:
        return frame.get_by_role("button", name=str(target_page_number), exact=True)
    except Exception:
        return None


def _wait_for_next_page_settle(page, ctx: "_QueryObservationContext", ensure_parsed, count_before_click: int, hard_cap_ms: int) -> dict:
    """PAGE-300-2B-1 §12: 페이지 번호 클릭 직후 신규 candidate response가
    도착할 때까지 기다리고, 첫 신규 응답이 확인되면 기존 adaptive
    quiet-period 원칙(_QUIET_PERIOD_MS)으로 이 페이지의 candidate response
    수집이 안정화될 때까지 추가로 기다린다(collect_network_query 본문의
    최초 settle 폴링 루프와 동일한 로직을 count_before_click부터 시작하도록
    일반화한 것 - 로직 자체는 복제가 아니라 재사용 목적으로 별도 함수화했다).

    hard_cap_ms 안에 신규 candidate response가 전혀 도착하지 않으면
    got_new_response=False를 반환한다(next_page_response_timeout 판정은
    호출자의 책임 - 이 함수는 판정하지 않고 사실만 보고한다).
    """
    elapsed_ms = 0
    got_new_response = False
    valid_confirmed = False
    quiet_elapsed_ms = 0
    last_seen_count = count_before_click

    while elapsed_ms < hard_cap_ms:
        page.wait_for_timeout(_POLL_INTERVAL_MS)
        elapsed_ms += _POLL_INTERVAL_MS

        current_count = ctx.candidate_response_count
        if current_count > last_seen_count:
            got_new_response = True
            found_valid_this_tick = False
            for index in range(last_seen_count, current_count):
                parsed = ensure_parsed(index)
                if not parsed["error"] and parsed["items"]:
                    found_valid_this_tick = True
            last_seen_count = current_count
            quiet_elapsed_ms = 0
            if found_valid_this_tick:
                valid_confirmed = True
        elif valid_confirmed:
            quiet_elapsed_ms += _POLL_INTERVAL_MS
            if quiet_elapsed_ms >= _QUIET_PERIOD_MS:
                break

    return {
        "got_new_response": got_new_response,
        "final_count": last_seen_count,
        "elapsed_ms": elapsed_ms,
    }


def _classify_page_candidate_error(ctx: "_QueryObservationContext", start_index: int, end_index: int):
    """PAGE-300-2B-4A §5(gpt-5.6-sol 독립 검토 지적, High 반영): 지정된 candidate
    인덱스 범위(하나의 새로 확정된 페이지의 harvest 범위이거나, 다음 페이지
    클릭 직전 drain으로 합류된 지연 도착분)에 candidate HTTP 오류·non-JSON
    body·snapshot 오류·JSON decode 오류 중 하나라도 있으면 우선순위(HTTP 오류 >
    non-JSON > snapshot 오류 > decode 오류)에 따라 대응하는 pagination_stop_
    reason을 반환한다. 없으면 None. 원래는 새로 확정된 페이지의 harvest
    직후에만 이 검사를 했는데, drain 경로(§4)로 늦게 합류되는 candidate는
    검사되지 않아 PAGE-300-2B-4류의 오류 candidate 이후에도 다음 페이지
    클릭이 계속될 수 있었다 - 이제 drain 호출부에서도 동일하게 이 함수를
    호출해 즉시 안전 중단한다.

    PAGE-300-2B-4A-FIX(gpt-5.6-sol 최종 검토 지적, Medium 반영): 이 범위에서
    candidate 오류가 발견됐고 동시에 `ctx.status_429_seen`도 True라면(예:
    drain/scroll 중 도착한 candidate 자체가 HTTP 429), 기존에 이 함수 밖
    (루프 최상단/클릭 직후)에서 이미 적용되던 "429가 다른 모든 판정보다
    우선"이라는 전역 우선순위와 라벨을 일치시키기 위해 "status_429_seen"을
    반환한다 - 중단 여부(반환값이 None이 아님) 자체는 바뀌지 않고, 어떤
    문자열로 보고할지만 기존 전역 우선순위에 맞춘다."""
    if end_index <= start_index:
        return None
    indices = range(start_index, end_index)
    for candidate_error_type, mapped_reason in _CANDIDATE_ERROR_STOP_REASONS.items():
        if any(ctx.candidates[i].get("candidate_error_type") == candidate_error_type for i in indices):
            return "status_429_seen" if ctx.status_429_seen else mapped_reason
    if any(ctx.candidates[i]["body_snapshot_error_type"] for i in indices):
        return "status_429_seen" if ctx.status_429_seen else "candidate_snapshot_error"
    if any(ctx.candidates[i].get("json_decode_error_type") for i in indices):
        return "status_429_seen" if ctx.status_429_seen else "candidate_json_decode_error"
    return None


def _safe_get_attribute(locator, name: str):
    """PAGE-300-2B-1-FIX §6: DOM 속성 조회는 절대 예외를 밖으로 던지지 않는다 -
    locator가 stale하거나(클릭 사이 DOM이 통째로 재렌더링) frame이 이미
    사라진 경우에도 None을 반환해, 호출자가 "식별 불가"로 안전하게 처리할 수
    있게 한다.
    """
    try:
        return locator.get_attribute(name)
    except Exception:
        return None


def _drain_pending_responses(page, ctx: "_QueryObservationContext", ensure_parsed, from_index: int) -> dict:
    """PAGE-300-2B-1-FIX §4: 다음 페이지 버튼을 클릭하기 직전, from_index부터
    아직 harvest되지 않은 candidate response가 있다면 "이전(현재까지 확정된)
    페이지의 지연 도착분"으로 간주해 먼저 처리한다 - 클릭 이후에 도착하는
    response와 섞이지 않도록 클릭 기준점(candidate_count_before_click)을
    확정하기 전에 반드시 비워야 한다. 이미 도착한 candidate가 하나도 없더라도
    "더 도착하지 않는다"는 사실 자체를 실제로 짧게 대기해 확인한다(호출은
    이 함수가 실제로 호출될 때만 발생한다 - 목표 페이지 버튼을 정상적으로
    찾아 클릭이 임박한 경우에만 도달하므로, 애초에 클릭을 시도하지 않는
    단일 페이지 호출부/pagination_exhausted 경로에는 영향이 없다).

    짧은 bounded quiet(_PENDING_DRAIN_QUIET_MS) 동안 추가 도착이 없을 때까지
    폴링한 뒤 그때까지 확보한 모든 candidate를 harvest한다.
    """
    last_seen = from_index
    quiet_elapsed_ms = 0
    while quiet_elapsed_ms < _PENDING_DRAIN_QUIET_MS:
        page.wait_for_timeout(_POLL_INTERVAL_MS)
        current_count = ctx.candidate_response_count
        if current_count > last_seen:
            last_seen = current_count
            quiet_elapsed_ms = 0
        else:
            quiet_elapsed_ms += _POLL_INTERVAL_MS

    raw_items: list = []
    parse_error_count = 0
    for index in range(from_index, last_seen):
        parsed = ensure_parsed(index)
        if parsed["error"]:
            parse_error_count += 1
        else:
            raw_items.extend(parsed["items"])

    return {"final_count": last_seen, "raw_items": raw_items, "parse_error_count": parse_error_count}


def collect_network_query(
    page,
    job,
    per_query_limit,
    *,
    collected_at,
    settle_ms: int = 5000,
) -> dict:
    """쿼리 1개를 처리하는 Network 응답 관찰 함수(page는 호출자가 이미 생성해 전달).

    반환: {"rows", "active_captcha_detected", "status_429_seen",
    "candidate_response_count", "raw_item_count", "local_unique_count",
    "parse_error_count", "timeout", "navigation_error",
    "navigation_error_message", "adaptive_settle_wait_ms",
    "adaptive_settle_early_exit"}. rows는 network_pipeline.run_collection_plan이
    기대하는 형태(place_id/업체명 키를 가진 dict)이며, job의 source_city/
    source_district/source_subregion/source_layer를 각 row에 그대로
    전달한다(전역 dedup은 이 함수의 책임이 아니라 run_collection_plan의
    책임 - 여기서는 쿼리 내부 로컬 dedup만 수행한다).

    navigation 정책(WIRE-2A-B): page.goto()가 실제 PlaywrightTimeoutError를
    던지면 "느린 로드"로 간주해 관용적으로 흡수하고(timeout=True), 이후
    settle 대기·후보 파싱·CAPTCHA probe를 그대로 계속 진행한다(BrowserSession.
    goto와 동일하게 현재 DOM으로 계속 진행). 그 외 예외(Target closed 등
    page/context/browser가 이미 닫혔거나 브라우저 실행 자체가 실패한 경우)는
    페이지 상태를 더 이상 신뢰할 수 없다고 보고 settle 대기·후보 파싱·CAPTCHA
    probe를 전부 건너뛰며 즉시 navigation_error=True, timeout=False, rows=[]로
    반환한다(CAPTCHA/429로 오분류하지 않는다). 이 함수는 이 경우 재시도하지
    않으며, 재시도/복구 정책은 이 함수를 호출하는 상위 계층(WIRE-2B 이후)의
    책임으로 남겨둔다. 상위 orchestrator(run_collection_plan)와 UI는 이번
    단계에서 이 신규 필드를 아직 읽지 않는다.

    적응형 settle(PERF-1A, WIRE-2A-B 이후 추가): settle_ms는 "무조건 대기
    시간"이 아니라 "최대 대기 hard cap"이다. page.wait_for_timeout(settle_ms)
    한 번 대신, _POLL_INTERVAL_MS(100ms) 간격으로 폴링하며 매 tick마다 새로
    도착한 candidate 응답이 있는지 확인한다. 새 candidate를 "예외 없이
    파싱 성공하고 추출된 목록이 비어있지 않음"(valid) 기준으로 확인하면
    조기 종료 대상으로 표시하고, 이후 _QUIET_PERIOD_MS(750ms) 동안 추가
    candidate가 전혀 도착하지 않으면 hard cap 전에 즉시 대기를 끝낸다.
    추가 candidate가 도착하면 valid 여부와 무관하게 quiet 타이머를 다시
    시작한다(늦게 오는 두 번째 응답에게 다시 기회를 준다). candidate가
    전혀 없거나 끝까지 valid로 확인되지 않으면 기존과 동일하게 hard cap
    전체를 대기한다(회귀 없음 - candidate_response_count==0인 케이스는
    timeout 계산도 기존과 동일).

    알려진 트레이드오프(반대 검토 AI 확인, 의도된 설계): quiet period가
    지나 조기 종료한 "직후"에 두 번째 candidate가 도착하면 그 응답은
    수집되지 않는다(harvest 루프가 이미 끝난 뒤이므로). 기존 고정 5초
    대기는 이 경우를 항상 잡았을 수 있다 - 이는 속도 최적화가 감수하는
    알려진 트레이드오프이며, candidate 간 실제 도착 간격(750ms 적정성)은
    아직 live로 계측되지 않았다(§_QUIET_PERIOD_MS 주석). "valid" 판정은
    빈 목록을 확인한 것만으로는 성립하지 않는다 - 응답 URL 후보 판별
    (is_candidate_response)이 실제 업체 목록이 아닌 응답(예: pcmap host의
    다른 xhr/fetch)도 후보로 잡을 수 있어, "빈 목록도 valid"로 두면 진짜
    데이터가 담긴 응답이 나중에 와도 그 전에 조기 종료해 데이터를 통째로
    놓칠 위험이 있기 때문이다(반대 검토에서 발견된 결함, 수정 반영).
    elapsed_ms는 폴링 대기(wait_for_timeout 호출)의 누적 합이며 실제
    벽시계 시간이 아니다 - tick 사이의 파싱/probe 작업 시간은 포함되지
    않으므로 실제 경과 시간은 이보다 소폭 더 걸릴 수 있다(기존 방식도
    고정 대기 후 파싱 작업을 했으므로 총량 자체는 회귀가 아니다).

    제한된 페이지네이션(PAGE-300-2B-1, PAGE-300-PoC-B2 근거): 첫 페이지
    settle·harvest 이후 local unique 개수가 여전히 per_query_limit보다
    적으면(그리고 CAPTCHA/429가 이미 감지되지 않았으면), searchIframe 내부의
    다음 페이지 번호 버튼(정확한 텍스트 일치, force click 미사용)을 최대
    _MAX_PAGINATION_PAGES(5)페이지까지 순차 클릭해 추가 candidate response를
    같은 dedup 집합에 누적한다. 다음 페이지 번호 "묶음" 전환(예: 5페이지
    이후 6~10페이지 이동)은 이번 단계에 구현하지 않으며, per_query_limit=300을
    줘도 최대 5페이지(약 100건) 내에서 pagination_stop_reason=
    "max_page_count_reached"로 종료될 수 있다 - 이를 300건 지원 완료로
    오판하지 않는다(신규 진단 필드 pagination_*/per_page_diagnostics 참고).
    searchIframe을 찾지 못하거나(예: frame API를 구현하지 않은 fake page,
    또는 실제로 iframe이 없는 예외 상황) 목표 페이지 버튼을 찾지 못하면
    pagination_stop_reason="pagination_exhausted"로 안전하게 종료하고 그때까지
    수집한 rows를 그대로 반환한다 - 예외를 던지지 않으므로 기존(페이지네이션
    이전) 단일 페이지 호출부와 테스트는 결과가 전혀 달라지지 않는다.

    응답 귀속 안전성(PAGE-300-2B-1-FIX, 독립 검토에서 지적된 결함 수정):
    실제 allSearch 응답 JSON과 request URL에는 page/cursor 식별자가 전혀
    없다는 것이 PAGE-300-PoC-B2 실측 결론이므로(page300_poc_b2_report.md),
    "candidate_response_count가 클릭 전보다 늘었다"는 사실 하나만으로는 그
    응답이 실제로 목표 페이지의 응답인지 확정할 수 없다 - 클릭 직전에 도착한
    이전 페이지의 늦은 응답을 다음 페이지 응답으로 오인할 위험이 있었다(구
    PAGE-300-2B-1의 알려진 한계). 이를 두 가지 보완으로 완화한다:
    1) 클릭 기준점(candidate_count_before_click)을 확정하기 직전에
       _drain_pending_responses로 미처리 candidate를 전부 "현재까지 확정된
       페이지의 지연 도착분"으로 먼저 harvest한다(§4) - 최초 harvest와 클릭
       기준점 사이에 도착한 응답이 누락되는 결함도 함께 해결한다.
    2) 클릭 이후 새 candidate response가 도착해도, PAGE-300-PoC-B2에서 실측
       확인된 DOM 근거(목표 페이지 번호 버튼이 "현재 페이지"가 되면 class
       속성이 바뀐다 - page300_network_summary.json의 page_1 DOM 캡처에서
       버튼 "1"만 다른 버튼과 다른 class를 가짐)를 보조 신호로 함께 확인한다.
       리터럴 클래스명(예: qxokY)에 의존하지 않고, 같은 버튼 locator의 클릭
       전/후 class 속성 문자열이 실제로 달라졌는지만 비교한다(§6). class를
       읽을 수 없으면(locator stale 등) pagination_stop_reason=
       "next_page_identity_unverified"로, class를 읽었지만 클릭 전후로
       변화가 없으면(target response와 DOM 상태 불일치) "page_transition_unverified"로
       안전하게 중단하고 그 응답의 데이터는 rows에 포함하지 않는다(추측
       금지) - 두 경우 모두 pagination_page_count를 증가시키지 않고, 그때까지
       확정된 rows만 보존한다. 진단 필드 pagination_unverified_candidate_count에
       그렇게 버려진 candidate 수를 기록한다. 실제 응답 body 자체에 페이지
       식별자가 없다는 실측 결론은 여전히 유효하므로, request/response 값으로
       page 번호를 추측하는 코드는 추가하지 않았다(요청서 §5 금지 사항).

    남아있는 구조적 한계(gpt-5.6-sol 독립 재검토로 확인, 현재 증거로는 코드만으로
    해결 불가): DOM class diff와 "새 response 도착"은 서로 인과관계로 묶여있지
    않고 각각 독립적으로 확인된다 - 클릭이 실제로 DOM을 목표 페이지로 전환시켰고,
    그 직후 우연히 지연 도착한 "이전 페이지"의 응답이 클릭 후 첫 신규 candidate가
    되는 경우, class diff(진짜 전환 근거)와 response 도착(가짜 데이터)이 둘 다
    "성공"처럼 보여 오귀속될 이론적 가능성이 남아있다. 이를 완전히 닫으려면
    실제 네이버에서 "DOM 전환"과 "response 도착"의 순서 보장 여부를 실측해야
    하며(이번 단계는 실제 live 금지), 실측 없이 추가 휴리스틱을 넣는 것은
    페이지 번호 추측 금지 원칙에 위배되므로 넣지 않았다. 다만 이 오귀속이
    무한히 이어지지는 않는다 - _MAX_PAGINATION_PAGES(5)와 per_query_limit이
    그대로 상한으로 작동하므로 폭주(runaway)는 없고, "정확히 한 페이지만
    오염된다"는 보장도 아니다(지연 응답이 연쇄되면 이론상 상한 페이지까지
    오귀속이 이어질 수 있음) - 다음 단계(PAGE-300-2B-2 등)에서 실측 근거가
    보강되면 재검토가 필요하다.

    알려진 한계(그대로 유지, 이번 단계 수정 범위 아님):
    - _find_search_frame은 browser_session.py의 find_search_frame과 동일한
      폴백 순서(name -> frame_locator+body wait -> frames 스캔)를 그대로
      재구현했다 - 두 번째 폴백에서 frame_locator로 실제 iframe을 찾고도 그
      객체 대신 다시 page.frame(name=...)을 호출하므로, 실제 iframe에 id만
      있고 name 속성이 없는 극단적인 경우 탐색에 실패할 수 있다. 이는
      browser_session.py(이번 단계 수정 금지)의 기존 패턴을 그대로 복제한
      것이며 임의로 다르게 구현하지 않았다.

    click count와 page count의 의미(PAGE-300-2B-1-FIX §7, 수정됨):
    - pagination_click_count는 "실제 click()이 예외 없이 반환된 횟수"다(§7) -
      click()이 성공한 직후 즉시 증가하며, 그 뒤 응답이 timeout되거나(성공한
      클릭 자체는 사실이므로) DOM identity를 확인하지 못해도 되돌리지 않는다.
      click() 호출 자체가 예외를 던지면 증가하지 않는다(force click은 쓰지
      않으므로 클릭 성공은 실제 클릭 가능 상태였다는 근거가 된다).
    - pagination_page_count(current_page_number)는 "§5/§6 기준으로 target
      response identity가 확인되고 DOM 전환도 확인된, 확정 성공한 페이지 수"만
      의미한다 - click count와 달리 클릭 성공만으로는 증가하지 않는다(구
      PAGE-300-2B-1에서는 두 개념이 사실상 같이 움직였으나, 이번 수정으로
      "클릭은 성공했지만 페이지 확정은 실패"한 경우를 구분할 수 있게 됐다).
    """
    ctx = _QueryObservationContext()
    response_handler = _make_response_handler(ctx)
    request_finished_handler = _make_request_finished_handler(ctx)
    request_failed_handler = _make_request_failed_handler(ctx)
    # PAGE-300-2B-2B(gpt-5.6-sol 독립 검토 지적, 수정 반영): 세 리스너 중
    # 두 번째/세 번째 등록(page.on)이 예외를 던지면, 이미 등록된 앞선
    # 리스너가 해제되지 않고 page에 남을 수 있었다 - 등록 도중 실패하면
    # 그때까지 등록된 리스너를 즉시 해제하고 원래 예외를 그대로 전파한다.
    _registered_listeners: list = []
    try:
        for _event, _handler in (
            ("response", response_handler),
            ("requestfinished", request_finished_handler),
            ("requestfailed", request_failed_handler),
        ):
            page.on(_event, _handler)
            _registered_listeners.append((_event, _handler))
    except Exception:
        for _event, _handler in _registered_listeners:
            try:
                page.off(_event, _handler)
            except Exception:
                pass
        raise

    goto_timed_out = False
    navigation_error = False
    navigation_error_message = ""
    try:
        search_url = _SEARCH_URL_TEMPLATE.format(query=quote(job["query"]))
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
        except PlaywrightTimeoutError:
            # BrowserSession.goto와 동일한 태도: 타임아웃이어도 현재 DOM으로 계속
            # 진행한다(우회가 아니라 "느린 로드"에 대한 관용 - CAPTCHA와는 무관).
            goto_timed_out = True
        except Exception as exc:
            # Target closed/브라우저 실행 장애 등 "느린 로드"가 아닌 그 외
            # navigation 오류는 timeout으로 위장하지 않는다. 페이지 상태를
            # 더 이상 신뢰할 수 없으므로 이후 단계(settle/파싱/CAPTCHA probe)를
            # 시도하지 않고 즉시 반환한다.
            navigation_error = True
            navigation_error_message = f"{type(exc).__name__}: {exc}"

        if navigation_error:
            # PAGE-300-2B-2D(gpt-5.6-sol 독립 검토 지적, Medium 반영): goto()가
            # 던진 예외가 timeout이 아닌 navigation_error로 분류되기 전에도,
            # 리스너는 이미 등록돼 있었으므로 response/requestfinished가 먼저
            # 도착해 candidate가 생겼을 가능성이 있다(예: 병행 요청이 goto
            # 완료 전에 이미 끝난 경우) - 이 경우에도 하드코딩된 0/빈 리스트
            # 대신 실제 ctx 상태를 그대로 요약해 불변식을 유지한다.
            navigation_error_snapshot_summary = _summarize_candidate_snapshots(ctx.candidates)
            return {
                "rows": [],
                "active_captcha_detected": False,
                "status_429_seen": ctx.status_429_seen,
                "candidate_response_count": ctx.candidate_response_count,
                "raw_item_count": 0,
                "local_unique_count": 0,
                "parse_error_count": 0,
                "timeout": False,
                "navigation_error": True,
                "navigation_error_message": navigation_error_message,
                "adaptive_settle_wait_ms": 0,
                "adaptive_settle_early_exit": False,
                "pagination_page_count": 1,
                "pagination_click_count": 0,
                "pagination_stop_reason": None,
                "pagination_error_message": "",
                "pagination_candidate_response_count": ctx.candidate_response_count,
                "pagination_raw_item_count": 0,
                "pagination_unique_item_count": 0,
                "pagination_duplicate_count": 0,
                "pagination_max_pages": _MAX_PAGINATION_PAGES,
                "pagination_unverified_candidate_count": 0,
                "pagination_drain_item_count": 0,
                "per_page_diagnostics": [],
                "body_snapshot_success_count": navigation_error_snapshot_summary["body_snapshot_success_count"],
                "body_snapshot_error_count": navigation_error_snapshot_summary["body_snapshot_error_count"],
                "body_snapshot_total_bytes": navigation_error_snapshot_summary["body_snapshot_total_bytes"],
                "json_decode_error_count": navigation_error_snapshot_summary["json_decode_error_count"],
                "body_snapshot_empty_count": navigation_error_snapshot_summary["body_snapshot_empty_count"],
                "snapshot_pending_count": navigation_error_snapshot_summary["snapshot_pending_count"],
                "unmatched_requestfinished_count": ctx.unmatched_requestfinished_count,
                "ambiguous_request_mapping_count": ctx.ambiguous_request_mapping_count,
                "candidate_snapshot_diagnostics": navigation_error_snapshot_summary["candidate_snapshot_diagnostics"],
                "candidate_http_error_count": navigation_error_snapshot_summary["candidate_http_error_count"],
                "candidate_non_json_count": navigation_error_snapshot_summary["candidate_non_json_count"],
                "candidate_http_status_counts": navigation_error_snapshot_summary["candidate_http_status_counts"],
                "candidate_processing_error_count": navigation_error_snapshot_summary["candidate_processing_error_count"],
            }

        # PAGE-300-2B-2B: parsed_cache는 candidate 하나당 JSON 파싱을 정확히
        # 1회만 수행하도록 메모이즈한다(폴링 루프의 "peek" 확인과 아래 harvest
        # 단계가 결과를 공유 - 중복 파싱/중복 parse_error 집계 방지). harvest는
        # Playwright Response 객체에 다시 접근하지 않고 requestfinished가 이미
        # 확보해 둔 candidate entry의 body_snapshot(bytes)만 사용한다.
        parsed_cache: dict = {}

        def _ensure_parsed(index: int) -> dict:
            """peek 전용 - candidate가 아직 pending(response는 왔지만
            requestfinished/requestfailed가 아직 도착하지 않음)이면 memoize하지
            않고 그대로 반환한다(다음 tick에 다시 확인하기 위함). 정말로
            resolve된 경우(성공 snapshot 또는 영구 실패)만 parsed_cache에
            영구 기록한다."""
            if index in parsed_cache:
                return parsed_cache[index]
            entry = ctx.candidates[index]
            if entry["body_snapshot_ready"]:
                # PAGE-300-2B-4A §3(gpt-5.6-sol 독립 검토 지적, Medium 반영):
                # HTTP status 분류는 candidate 등록 시점(response handler,
                # _classify_candidate_http_status)에 body snapshot 성공/실패와
                # 무관하게 이미 확정돼 있다 - 여기서는 그 결과만 확인해 json
                # decode를 아예 시도하지 않는다(json_decode_error_type은 채우지
                # 않음 - §3 "JSON decode 자체를 시도하지 않았기 때문이다").
                if entry.get("candidate_error_type") == "CandidateHttpError":
                    parsed_cache[index] = {"items": [], "error": True}
                    entry["processed"] = True
                    return parsed_cache[index]
                # PAGE-300-2B-4A §4: HTTP 2xx이지만 body의 첫 유효 문자가 JSON
                # object/array 시작 기호가 아니면(예: HTML 오류 페이지 "<") 목록
                # candidate로 인정하지 않는다 - Content-Type 헤더만으로 차단하지
                # 않고(§4 "Content-Type만으로 무조건 차단하지 않는다") body 내용
                # 기준(first_non_whitespace_character)으로만 판단하므로, 정상
                # object/array를 잘못된 Content-Type(text/plain 등)으로 보내는
                # endpoint도 여전히 정상 decode된다.
                first_char = _classify_first_non_whitespace_character(entry["body_snapshot"])
                if first_char not in ("{", "["):
                    entry["candidate_error_type"] = "NonJsonCandidateBody"
                    parsed_cache[index] = {"items": [], "error": True}
                    entry["processed"] = True
                    return parsed_cache[index]
                try:
                    # PAGE-300-2B-2D §6: decode("utf-8-sig") 고정 대신 bytes를
                    # json.loads에 직접 전달한다 - CPython 3.6+의 json 모듈은
                    # bytes/bytearray 입력에 한해 RFC 8259 BOM/UTF-8/UTF-16/
                    # UTF-32를 자체 감지하므로(json.detect_encoding), UTF-8
                    # 고정 가정보다 더 넓은 인코딩을 안전하게 처리한다. 압축
                    # 해제나 charset 추측 재시도는 하지 않는다(§6, 임의 gzip
                    # 해제 금지).
                    data = json.loads(entry["body_snapshot"])
                    items = _extract_list_items(data)
                    parsed_cache[index] = {"items": items, "error": False}
                    if isinstance(data, dict):
                        entry["json_top_level_type"] = "object"
                    elif isinstance(data, list):
                        entry["json_top_level_type"] = "array"
                    else:
                        entry["json_top_level_type"] = "other"
                except Exception as exc:
                    parsed_cache[index] = {"items": [], "error": True}
                    entry["json_decode_error_type"] = type(exc).__name__
                entry["processed"] = True
                return parsed_cache[index]
            if entry["body_snapshot_error_type"]:
                parsed_cache[index] = {"items": [], "error": True}
                entry["processed"] = True
                return parsed_cache[index]
            # 아직 진짜 pending 상태 - memoize하지 않는다.
            return {"items": [], "error": False, "pending": True}

        def _ensure_parsed_final(index: int) -> dict:
            """실제 harvest(추출) 지점 전용 - peek에서 pending으로 남아있던
            candidate를 이 시점에 최종적으로 error로 확정한다(더 이상 기다리지
            않는다는 뜻이므로, 이후에는 같은 index를 다시 pending으로 보지
            않는다 - "candidate당 JSON parse 정확히 1회" 계약 유지)."""
            parsed = _ensure_parsed(index)
            if parsed.get("pending"):
                parsed_cache[index] = {"items": [], "error": True}
                entry = ctx.candidates[index]
                if not entry["body_snapshot_error_type"]:
                    entry["body_snapshot_error_type"] = "SnapshotPendingAtHarvest"
                entry["processed"] = True
                return parsed_cache[index]
            return parsed

        elapsed_ms = 0
        last_seen_count = 0
        valid_list_confirmed = False
        quiet_elapsed_ms = 0

        while elapsed_ms < settle_ms:
            page.wait_for_timeout(_POLL_INTERVAL_MS)
            elapsed_ms += _POLL_INTERVAL_MS

            current_count = ctx.candidate_response_count
            if current_count > last_seen_count:
                found_valid_this_tick = False
                for index in range(last_seen_count, current_count):
                    parsed = _ensure_parsed(index)
                    if not parsed["error"] and parsed["items"]:
                        found_valid_this_tick = True
                last_seen_count = current_count
                # 새 candidate가 도착하면(valid 여부와 무관하게) quiet 타이머를
                # 다시 시작한다 - 늦게 오는 두 번째 응답에게 다시 기회를 준다.
                quiet_elapsed_ms = 0
                if found_valid_this_tick:
                    valid_list_confirmed = True
            elif valid_list_confirmed:
                quiet_elapsed_ms += _POLL_INTERVAL_MS
                if quiet_elapsed_ms >= _QUIET_PERIOD_MS:
                    break

        adaptive_settle_wait_ms = elapsed_ms
        adaptive_settle_early_exit = elapsed_ms < settle_ms

        raw_items: list = []
        parse_error_count = 0
        for index in range(len(ctx.candidates)):
            parsed = _ensure_parsed_final(index)
            if parsed["error"]:
                parse_error_count += 1
            else:
                raw_items.extend(parsed["items"])

        mapped_rows = []
        for item in raw_items:
            row = _map_item_to_row(item, collected_at, source_query=job.get("query"))
            row["source_city"] = job.get("source_city")
            row["source_district"] = job.get("source_district")
            row["source_subregion"] = job.get("source_subregion")
            row["source_layer"] = job.get("source_layer")
            mapped_rows.append(row)

        local_seen: set = set()
        unique_rows = dedup_rows(mapped_rows, local_seen)
        total_mapped_count = len(mapped_rows)
        total_adaptive_wait_ms = adaptive_settle_wait_ms

        # timeout은 페이지네이션 이전(page 1)의 candidate 존재 여부만으로
        # 확정한다 - 이후 pagination 단계의 next_page_response_timeout은
        # 이 필드에 영향을 주지 않는다(§12: "timeout = False"로 별도 유지).
        timeout = goto_timed_out or ctx.candidate_response_count == 0

        # ---- PAGE-300-2B-1-FIX: 제한된 페이지네이션(최대 _MAX_PAGINATION_PAGES) ----
        pagination_stop_reason = None
        pagination_error_message = ""
        pagination_click_count = 0
        pagination_unverified_candidate_count = 0
        pagination_drain_item_count = 0
        current_page_number = 1
        # §3/§4: 지금까지 harvest(merge)된 candidate 인덱스의 상한 - 이 포인터
        # 이후 도착한 candidate만 "아직 처리되지 않은 pending"으로 간주한다.
        harvested_up_to_index = ctx.candidate_response_count
        per_page_diagnostics = [{
            "page_number": 1,
            "candidate_response_count": ctx.candidate_response_count,
            "raw_item_count": len(raw_items),
            "new_unique_count": len(unique_rows),
            "duplicate_count": len(mapped_rows) - len(unique_rows),
            "adaptive_wait_ms": adaptive_settle_wait_ms,
        }]
        consecutive_zero_new_unique = 0
        frame = None
        final_captcha_signal = None

        def _apply_pending_drain(from_index: int) -> int:
            """§4 드레인 결과를 현재까지 확정된 페이지의 rows/진단에 병합하고
            새 harvested 상한을 반환한다(page.wait_for_timeout 실패 시 예외를
            그대로 전파 - 호출자가 pagination_click_error로 안전하게 흡수한다).
            """
            nonlocal total_mapped_count, parse_error_count, pagination_drain_item_count
            drain_result = _drain_pending_responses(page, ctx, _ensure_parsed_final, from_index)
            # PAGE-300-2B-2B(gpt-5.6-sol 독립 검토 지적, 수정 반영): drain된
            # candidate가 전부 실패(raw_items=[])해도 parse_error_count는
            # 반드시 반영해야 한다 - 이전에는 이 라인이 raw_items가 있을 때만
            # 실행되는 조건문 안에 있어, drain 중 body snapshot이 끝내
            # 확정(_ensure_parsed_final)돼도 error로만 끝나면 parse_error_count가
            # 증가하지 않고 조용히 사라질 수 있었다(§9/§10 위험 - 거짓 성공 가능성).
            parse_error_count += drain_result["parse_error_count"]
            if drain_result["raw_items"]:
                drain_mapped_rows = []
                for item in drain_result["raw_items"]:
                    row = _map_item_to_row(item, collected_at, source_query=job.get("query"))
                    row["source_city"] = job.get("source_city")
                    row["source_district"] = job.get("source_district")
                    row["source_subregion"] = job.get("source_subregion")
                    row["source_layer"] = job.get("source_layer")
                    drain_mapped_rows.append(row)
                drain_newly_unique = dedup_rows(drain_mapped_rows, local_seen)
                unique_rows.extend(drain_newly_unique)
                total_mapped_count += len(drain_mapped_rows)
                raw_items.extend(drain_result["raw_items"])
                pagination_drain_item_count += len(drain_result["raw_items"])
            return drain_result["final_count"]

        if per_query_limit and len(unique_rows) >= per_query_limit:
            pagination_stop_reason = "per_query_limit_reached"
        elif per_query_limit:
            while current_page_number < _MAX_PAGINATION_PAGES:
                probe = _probe_captcha_state(page)
                loop_signal = classify_captcha_signal(
                    marker_present_in_dom=probe["marker_present"],
                    element_visible=probe["visible"],
                    bounding_box_area=probe["bounding_box_area"],
                    click_exception_message=probe["click_intercepted_message"],
                )
                final_captcha_signal = loop_signal
                if loop_signal["active_captcha_detected"]:
                    pagination_stop_reason = "captcha_detected"
                    break
                if ctx.status_429_seen:
                    pagination_stop_reason = "status_429_seen"
                    break

                if frame is None:
                    frame = _find_search_frame(page)
                if frame is None:
                    pagination_stop_reason = "pagination_exhausted"
                    break

                target_page_number = current_page_number + 1
                # PAGE-300-2B-2B: 순수 진단 라벨 - 지금부터 도착하는 candidate는
                # "target_page_number를 시도 중인 시점"에 관측된 것으로 기록한다.
                ctx.current_generation = target_page_number
                button_locator = _find_page_button(frame, target_page_number)
                try:
                    button_count = button_locator.count() if button_locator is not None else 0
                except Exception:
                    button_count = 0
                if button_count == 0:
                    pagination_stop_reason = "pagination_exhausted"
                    break
                if button_count > 1:
                    pagination_stop_reason = "ambiguous_page_button"
                    break

                target_locator = button_locator.first
                try:
                    is_ready = bool(target_locator.is_visible()) and bool(target_locator.is_enabled())
                except Exception as exc:
                    pagination_stop_reason = "pagination_click_error"
                    pagination_error_message = f"{type(exc).__name__}: {exc}"
                    break
                if not is_ready:
                    pagination_stop_reason = "pagination_click_error"
                    pagination_error_message = "다음 페이지 버튼이 보이지 않거나 비활성 상태입니다"
                    break

                # §4: 클릭 기준점을 확정하기 전에 미처리 candidate를 전부
                # "현재까지 확정된 페이지의 지연 도착분"으로 먼저 harvest한다.
                _drain_start_index = harvested_up_to_index
                try:
                    harvested_up_to_index = _apply_pending_drain(harvested_up_to_index)
                except Exception as exc:
                    pagination_stop_reason = "pagination_click_error"
                    pagination_error_message = f"{type(exc).__name__}: {exc}"
                    break

                # PAGE-300-2B-4A §5(gpt-5.6-sol 독립 검토 High 반영): drain으로
                # 합류된 candidate 중 HTTP 오류·non-JSON 등이 있으면 다음 페이지
                # 버튼을 클릭하지 않고 즉시 안전 중단한다 - 이 검사가 없으면
                # 오류 candidate가 "이전 페이지 지연 도착분"으로 조용히
                # 흡수되어 다음 페이지 클릭이 그대로 진행될 수 있었다.
                drain_error_reason = _classify_page_candidate_error(ctx, _drain_start_index, harvested_up_to_index)
                if drain_error_reason is not None:
                    pagination_stop_reason = drain_error_reason
                    break

                # 드레인만으로 이미 목표에 도달했다면(늦게 도착한 이전 페이지
                # 데이터로 충분하다면) 다음 페이지로 오인하지 않고 여기서
                # 종료한다 - pending 도착 자체는 page count를 늘리지 않는다.
                if per_query_limit and len(unique_rows) >= per_query_limit:
                    pagination_stop_reason = "per_query_limit_reached"
                    break

                candidate_count_before_click = harvested_up_to_index
                # §6 DOM 보조 판별 준비: 클릭 전 목표 버튼의 class 속성을
                # 남겨 둔다(리터럴 클래스명이 아니라 클릭 전/후 diff로만 쓴다).
                class_before = _safe_get_attribute(target_locator, "class")

                # 반대 검토(gpt-5.6-sol) 지적 사항, 수정 반영: class_before를
                # 읽는 get_attribute() 호출도(실제 Playwright에서는 이벤트
                # 루프에 제어권을 넘길 수 있다) baseline 확정 이후 벌어지는
                # 일이므로, 그 사이 새 candidate가 도착했다면 baseline에 조용히
                # 섞여 들어가 드레인 구간과 다음 페이지 harvest 구간 양쪽에서
                # 누락될 수 있었다 - 클릭 직전에 한 번 더 흡수해 확실히
                # "이전 페이지 데이터"로 처리한다.
                if ctx.candidate_response_count > candidate_count_before_click:
                    _second_drain_start_index = candidate_count_before_click
                    try:
                        harvested_up_to_index = _apply_pending_drain(candidate_count_before_click)
                    except Exception as exc:
                        pagination_stop_reason = "pagination_click_error"
                        pagination_error_message = f"{type(exc).__name__}: {exc}"
                        break
                    # PAGE-300-2B-4A §5(gpt-5.6-sol 독립 검토 High 반영): 클릭
                    # 직전 두 번째 drain에서도 동일하게 오류 candidate를 확인한다.
                    second_drain_error_reason = _classify_page_candidate_error(
                        ctx, _second_drain_start_index, harvested_up_to_index
                    )
                    if second_drain_error_reason is not None:
                        pagination_stop_reason = second_drain_error_reason
                        break
                    candidate_count_before_click = harvested_up_to_index
                    if per_query_limit and len(unique_rows) >= per_query_limit:
                        pagination_stop_reason = "per_query_limit_reached"
                        break
                    class_before = _safe_get_attribute(target_locator, "class")

                try:
                    target_locator.scroll_into_view_if_needed()
                except Exception as exc:
                    pagination_stop_reason = "pagination_click_error"
                    pagination_error_message = f"{type(exc).__name__}: {exc}"
                    break

                # PAGE-300-2B-4A-FIX §3(gpt-5.6-sol 최종 검토 지적, 잔여 타이밍
                # 공백 반영): scroll_into_view_if_needed() 실행 중에도 새
                # candidate가 도착할 수 있다 - 이전 두 drain 검사와 click() 사이의
                # 마지막 공백이었다. click() 호출 직전에 한 번 더(새 candidate가
                # 실제로 도착했을 때만) drain하고 공유 helper로 오류를 검사해,
                # 이 구간에서 도착한 오류 candidate도 다음 페이지 클릭을 막는다.
                # 새 candidate가 전혀 없으면 추가 대기 없이 곧바로 click으로
                # 진행한다(§8 - 무조건적인 대기 추가 금지).
                pre_click_drain_start_index = candidate_count_before_click
                if ctx.candidate_response_count > candidate_count_before_click:
                    try:
                        harvested_up_to_index = _apply_pending_drain(candidate_count_before_click)
                    except Exception as exc:
                        pagination_stop_reason = "pagination_click_error"
                        pagination_error_message = f"{type(exc).__name__}: {exc}"
                        break
                    candidate_count_before_click = harvested_up_to_index

                    pre_click_error_reason = _classify_page_candidate_error(
                        ctx, pre_click_drain_start_index, candidate_count_before_click
                    )
                    if pre_click_error_reason is not None:
                        pagination_stop_reason = pre_click_error_reason
                        break

                    # scroll 중 도착한 정상 candidate만으로 이미 목표에 도달했다면
                    # (§6 "목표 도달 시 click 생략") 다음 페이지로 오인하지 않고
                    # 여기서 종료한다 - 다른 drain 지점과 동일한 계약이다.
                    if per_query_limit and len(unique_rows) >= per_query_limit:
                        pagination_stop_reason = "per_query_limit_reached"
                        break

                    class_before = _safe_get_attribute(target_locator, "class")

                try:
                    target_locator.click()
                    # §7: 실제 click()이 예외 없이 반환된 직후 증가한다 - 이후
                    # 응답 timeout/identity 미확인으로 페이지 확정에 실패해도
                    # 클릭 자체가 성공했다는 사실은 되돌리지 않는다.
                    pagination_click_count += 1
                    # _wait_for_next_page_settle의 내부 page.wait_for_timeout() 호출도
                    # 이 try 블록으로 함께 감싼다 - 클릭 이후 page/context가 닫히는 등의
                    # 예외가 밖으로 새어나가 collect_network_query 전체가 죽고 이미
                    # 수집한 부분 rows까지 잃는 것을 방지한다(반대 검토 AI 지적 사항,
                    # 수정 반영 - 예외는 전부 pagination_click_error로 안전하게 귀결한다).
                    wait_result = _wait_for_next_page_settle(
                        page, ctx, _ensure_parsed, candidate_count_before_click, settle_ms
                    )
                except Exception as exc:
                    pagination_stop_reason = "pagination_click_error"
                    pagination_error_message = f"{type(exc).__name__}: {exc}"
                    break

                # §15 "각 페이지 클릭 전후 확인": 클릭 "전" 확인(루프 상단)만으로는
                # 클릭·대기 도중 나타난 CAPTCHA/429를 놓칠 수 있으므로, 응답 성공
                # 여부와 무관하게 클릭 직후 다시 확인한다(반대 검토 AI 지적 사항,
                # 수정 반영). 우선순위(§16: captcha > 429 > ... > timeout)를 지키기
                # 위해 next_page_response_timeout 판정보다 먼저 검사한다.
                probe = _probe_captcha_state(page)
                post_click_signal = classify_captcha_signal(
                    marker_present_in_dom=probe["marker_present"],
                    element_visible=probe["visible"],
                    bounding_box_area=probe["bounding_box_area"],
                    click_exception_message=probe["click_intercepted_message"],
                )
                final_captcha_signal = post_click_signal
                if post_click_signal["active_captcha_detected"]:
                    pagination_stop_reason = "captcha_detected"
                    break
                if ctx.status_429_seen:
                    pagination_stop_reason = "status_429_seen"
                    break

                if not wait_result["got_new_response"]:
                    pagination_stop_reason = "next_page_response_timeout"
                    break

                # §5/§6: candidate_response_count 증가만으로 목표 페이지 성공을
                # 판정하지 않는다. 클릭한 버튼의 class 속성이 클릭 전/후로
                # 실제로 달라졌는지(리터럴 클래스명이 아니라 같은 locator의
                # diff로) 확인해야 한다. class를 아예 읽을 수 없으면(locator
                # stale 등) identity를 판단할 근거가 없는 것이고, 읽었지만 값이
                # 그대로라면 DOM 상태와 신규 response 도착이 서로 불일치하는
                # 것이다 - 두 경우 모두 이 response를 목표 페이지 데이터로
                # 인정하지 않고(추측 금지) 그때까지 확정된 rows만 보존한다.
                class_after = _safe_get_attribute(target_locator, "class")
                newly_arrived_count = wait_result["final_count"] - candidate_count_before_click
                if class_before is None or class_after is None:
                    pagination_stop_reason = "next_page_identity_unverified"
                    pagination_unverified_candidate_count += newly_arrived_count
                    harvested_up_to_index = wait_result["final_count"]
                    break
                if class_before == class_after:
                    pagination_stop_reason = "page_transition_unverified"
                    pagination_unverified_candidate_count += newly_arrived_count
                    harvested_up_to_index = wait_result["final_count"]
                    break

                page_raw_items: list = []
                page_parse_errors = 0
                for index in range(candidate_count_before_click, wait_result["final_count"]):
                    parsed = _ensure_parsed_final(index)
                    if parsed["error"]:
                        page_parse_errors += 1
                    else:
                        page_raw_items.extend(parsed["items"])
                parse_error_count += page_parse_errors
                raw_items.extend(page_raw_items)
                harvested_up_to_index = wait_result["final_count"]

                page_mapped_rows = []
                for item in page_raw_items:
                    row = _map_item_to_row(item, collected_at, source_query=job.get("query"))
                    row["source_city"] = job.get("source_city")
                    row["source_district"] = job.get("source_district")
                    row["source_subregion"] = job.get("source_subregion")
                    row["source_layer"] = job.get("source_layer")
                    page_mapped_rows.append(row)

                newly_unique = dedup_rows(page_mapped_rows, local_seen)
                unique_rows.extend(newly_unique)
                total_mapped_count += len(page_mapped_rows)
                total_adaptive_wait_ms += wait_result["elapsed_ms"]

                current_page_number = target_page_number
                per_page_diagnostics.append({
                    "page_number": current_page_number,
                    "candidate_response_count": wait_result["final_count"] - candidate_count_before_click,
                    "raw_item_count": len(page_raw_items),
                    "new_unique_count": len(newly_unique),
                    "duplicate_count": len(page_mapped_rows) - len(newly_unique),
                    "adaptive_wait_ms": wait_result["elapsed_ms"],
                })

                # PAGE-300-2B-4A §5: 이번 페이지의 candidate가 HTTP 오류·non-JSON
                # body·snapshot 오류·JSON decode 오류 중 하나라도 겪었다면 다음
                # 페이지 버튼을 클릭하지 않고 즉시 안전 중단한다(PAGE-300-2B-4
                # 재현 - HTTP 405 응답을 받고도 계속 다음 페이지를 클릭하려다
                # 30초 클릭 타임아웃으로만 우연히 멈췄던 문제를 명시적으로
                # 고친다). 페이지 확정(DOM 전환) 자체는 되돌리지 않는다 - 데이터
                # 품질과 DOM 전환 여부는 서로 다른 판단이다.
                page_error_reason = _classify_page_candidate_error(ctx, candidate_count_before_click, wait_result["final_count"])
                if page_error_reason is not None:
                    pagination_stop_reason = page_error_reason
                    break

                # §16 종료 우선순위(1.per_query_limit > 4.max_page > 9.no_new_unique)를
                # 그대로 반영한다 - 예를 들어 마지막(5번째) 페이지에서 신규 unique가
                # 2연속 0건이 되는 경우에도 max_page_count_reached가 no_new_unique_rows
                # 보다 먼저 보고돼야 한다(반대 검토 AI 지적 사항, 순서 수정 반영).
                if per_query_limit and len(unique_rows) >= per_query_limit:
                    pagination_stop_reason = "per_query_limit_reached"
                    break
                if current_page_number >= _MAX_PAGINATION_PAGES:
                    pagination_stop_reason = "max_page_count_reached"
                    break
                if len(newly_unique) == 0:
                    consecutive_zero_new_unique += 1
                    if consecutive_zero_new_unique >= 2:
                        pagination_stop_reason = "no_new_unique_rows"
                        break
                else:
                    consecutive_zero_new_unique = 0

            if pagination_stop_reason is None:
                pagination_stop_reason = "max_page_count_reached"

        if final_captcha_signal is None:
            probe = _probe_captcha_state(page)
            final_captcha_signal = classify_captcha_signal(
                marker_present_in_dom=probe["marker_present"],
                element_visible=probe["visible"],
                bounding_box_area=probe["bounding_box_area"],
                click_exception_message=probe["click_intercepted_message"],
            )

        capped_rows = unique_rows[:per_query_limit] if per_query_limit else unique_rows

        # PAGE-300-2B-2D §3/§4: navigation_error 조기 반환과 동일한 공유 헬퍼로
        # success/error/pending 3분류 불변식과 candidate_snapshot_diagnostics를
        # 계산한다(gpt-5.6-sol 독립 검토 Medium 지적 반영 - 두 반환 경로가
        # 서로 다른 계산 로직을 갖지 않도록 통일).
        snapshot_summary = _summarize_candidate_snapshots(ctx.candidates, parsed_cache)

        return {
            "rows": capped_rows,
            "active_captcha_detected": bool(final_captcha_signal["active_captcha_detected"]),
            "status_429_seen": ctx.status_429_seen,
            "candidate_response_count": ctx.candidate_response_count,
            "raw_item_count": len(raw_items),
            "local_unique_count": len(unique_rows),
            "parse_error_count": parse_error_count,
            "timeout": timeout,
            "navigation_error": False,
            "navigation_error_message": "",
            "adaptive_settle_wait_ms": total_adaptive_wait_ms,
            "adaptive_settle_early_exit": adaptive_settle_early_exit,
            "pagination_page_count": current_page_number,
            "pagination_click_count": pagination_click_count,
            "pagination_stop_reason": pagination_stop_reason,
            "pagination_error_message": pagination_error_message,
            "pagination_candidate_response_count": ctx.candidate_response_count,
            "pagination_raw_item_count": len(raw_items),
            "pagination_unique_item_count": len(unique_rows),
            "pagination_duplicate_count": total_mapped_count - len(unique_rows),
            "pagination_max_pages": _MAX_PAGINATION_PAGES,
            "pagination_unverified_candidate_count": pagination_unverified_candidate_count,
            "pagination_drain_item_count": pagination_drain_item_count,
            "per_page_diagnostics": per_page_diagnostics,
            "body_snapshot_success_count": snapshot_summary["body_snapshot_success_count"],
            "body_snapshot_error_count": snapshot_summary["body_snapshot_error_count"],
            "body_snapshot_total_bytes": snapshot_summary["body_snapshot_total_bytes"],
            "json_decode_error_count": snapshot_summary["json_decode_error_count"],
            "body_snapshot_empty_count": snapshot_summary["body_snapshot_empty_count"],
            "snapshot_pending_count": snapshot_summary["snapshot_pending_count"],
            "unmatched_requestfinished_count": ctx.unmatched_requestfinished_count,
            "ambiguous_request_mapping_count": ctx.ambiguous_request_mapping_count,
            "candidate_snapshot_diagnostics": snapshot_summary["candidate_snapshot_diagnostics"],
            "candidate_http_error_count": snapshot_summary["candidate_http_error_count"],
            "candidate_non_json_count": snapshot_summary["candidate_non_json_count"],
            "candidate_http_status_counts": snapshot_summary["candidate_http_status_counts"],
            "candidate_processing_error_count": snapshot_summary["candidate_processing_error_count"],
        }
    finally:
        for event, event_handler in (
            ("response", response_handler),
            ("requestfinished", request_finished_handler),
            ("requestfailed", request_failed_handler),
        ):
            try:
                page.off(event, event_handler)
            except Exception:
                pass


def _default_session_factory():
    """실제 제품 배선용 기본 factory - 이 함수가 호출되어 반환된 객체의
    __enter__가 실제로 호출될 때만 Playwright/브라우저가 시작된다(이 함수를
    정의/참조하는 것만으로는 아무것도 시작하지 않는다). 테스트는 항상
    session_factory를 fake로 주입하므로 이 함수는 테스트에서 호출되지 않는다.

    2026-07-21: BrowserBackendConfig.from_env().backend에 따라
    NativeCdpBrowserSession(기본값, production)과 BrowserSession(launch,
    명시적 backend="launch" 선택 시만 사용하는 개발·테스트 fallback) 중
    하나를 반환한다. DiagnosticConfig는 기존과 동일하게 safe_default()를
    사용한다(브라우저 backend 선택과 진단 플래그는 독립된 설정 축).
    """
    from src.pc.browser_session import BrowserSession, NativeCdpBrowserSession
    from src.pc.config import BrowserBackendConfig, DiagnosticConfig

    diagnostic_config = DiagnosticConfig.safe_default()
    backend_config = BrowserBackendConfig.from_env()

    if backend_config.backend == "launch":
        return BrowserSession(diagnostic_config)
    return NativeCdpBrowserSession(diagnostic_config, backend_config)


class NetworkBrowserCollector:
    """실제 제품 경로에서 사용할 브라우저 생명주기 관리자(WIRE-2B-1).

    브라우저 1개·context 1개를 큐 전체(여러 쿼리)에서 공유하고, 쿼리마다
    새 page를 생성해 collect_network_query에 전달한 뒤 그 쿼리가 끝나면
    즉시 닫는다(page를 여러 쿼리에서 재사용하지 않는다):

        browser 1개 → context 1개 → [쿼리마다: new_page → collect_network_query
        → page.close()] → 큐 종료 후 context/browser/playwright 종료

    이렇게 페이지를 쿼리마다 격리하면 (1) 이전 쿼리의 늦은 응답이 다음
    쿼리로 섞이지 않고(response listener가 page와 함께 폐기됨) (2) 쿠키/
    세션은 동일 context에서 그대로 유지된다. CAPTCHA 발생 후 context를
    재시작하거나 재시도로 우회하지 않는다 - 이 클래스는 생명주기만
    관리하며, 안전 중단 판단은 여전히 run_collection_plan의 책임이다.

    session_factory는 인자 없이 호출하면 BrowserSession과 동일한 계약
    (컨텍스트 매니저로 진입(`__enter__`)하면 최소 `.context` 속성을 가진
    객체를 반환)을 만족하는 callable이어야 한다. 기본값은 실제
    BrowserSession을 참고하지만, 이 클래스의 `__enter__`가 실제로 호출될
    때만 Playwright가 시작된다 - 테스트는 항상 FakeSession factory를
    주입해 실제 BrowserSession/Playwright를 절대 실행하지 않는다.

    BrowserSession(WIRE-2B-1B 확인 - 실제 속성 기준): __enter__()가 browser/
    context와 함께 초기 page 1개(`session.page`)도 미리 만들어 둔다(다른
    호출부인 detail_scraper 등이 session.page를 바로 goto에 쓰는 용도).
    이 클래스는 쿼리마다 context에서 새 page를 만들어 쓰므로 그 초기 page를
    수집용으로 재사용하지 않는다 - `__enter__`에서 best-effort로 즉시 닫아
    큐 실행 내내 불필요한 page가 열려있지 않게 한다(닫기에 실패해도 결국
    BrowserSession._teardown()의 context.close()가 정리하므로 안전하다).
    session 객체에 `.page` 속성 자체가 없으면(FakeSession 등) 아무 것도
    하지 않는다.
    """

    def __init__(self, *, collected_at, session_factory=None, settle_ms: int = 5000):
        self.collected_at = collected_at
        self.settle_ms = settle_ms
        self._session_factory = session_factory or _default_session_factory
        self._session_cm = None
        self._session = None

    def __enter__(self):
        self._session_cm = self._session_factory()
        self._session = self._session_cm.__enter__()
        self._close_initial_page_if_present()
        return self

    def _close_initial_page_if_present(self) -> None:
        """BrowserSession.__enter__가 미리 만든 초기 page(session.page)는 쿼리별
        page 생성 방식과 무관하므로 수집용으로 쓰지 않고 즉시 닫는다(best-effort).
        """
        initial_page = getattr(self._session, "page", None)
        if initial_page is None:
            return
        try:
            initial_page.close()
        except Exception:
            pass

    def collect_query(self, job, per_query_limit) -> dict:
        """run_collection_plan이 기대하는 collect_query(job, per_query_limit)
        시그니처를 만족하는 bound method. 공유 context에서 새 page를 만들어
        collect_network_query에 위임하고, 결과를 반환한 뒤(반환값 확정 후)
        page를 best-effort로 닫는다 - page.close()가 예외를 던져도(이미
        닫힌 page, Target closed 등) 그 예외를 삼키므로 collect_network_query
        가 만든 원래 결과(navigation_error 포함)를 덮어쓰지 않는다.
        """
        page = self._session.context.new_page()
        try:
            return collect_network_query(
                page,
                job,
                per_query_limit,
                collected_at=self.collected_at,
                settle_ms=self.settle_ms,
            )
        finally:
            try:
                page.close()
            except Exception:
                pass

    def __exit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            self._session_cm.__exit__(exc_type, exc, tb)
        self._session_cm = None
        self._session = None
        return False


# ============================================================================
# PAGE300-DOM-1: DOM-first membership 수집(collect_dom_membership_query)
# ============================================================================
#
# 단일 검색어에서 최대 5페이지, DOM에 실제 렌더링된 업체 목록을 최종 membership
# 기준으로 삼고 Network/Apollo는 필드 보강에만 쓰는 신규 경로다. 기존
# collect_network_query는 수정하지 않는다 - 이 함수는 그 위에 있는
# _QueryObservationContext/_make_response_handler/_make_request_finished_handler/
# _make_request_failed_handler/_find_search_frame/_find_page_button/
# _safe_get_attribute/_probe_captcha_state를 그대로 재사용하는 별도 함수다.
# UI/network_pipeline.run_collection_plan에는 연결하지 않는다(독립 함수로만
# 추가 - Live 검증은 scratchpad 러너가 직접 호출한다).
#
# 스크롤 방법론(요청서 승인 근거): cdp_validation_tests/comprehensive_cdp_tester.py의
# scroll_to_bottom()이 Edge/Chrome 4회 실측(70/70/70/70/20=300건, CAPTCHA/HTTP
# 오류 없음)으로 검증됐다 - scrollBy(상대 증분) + scrollHeight 안정화 + 단일
# frame.evaluate() 내 완결 + 40회 상한 + 600ms tick을 그대로 유지하고, row
# count/업체명 count 안정성도 함께 확인하도록 확장했다(scrollHeight만으로는
# 놓칠 수 있는 사례에 대한 추가 안전판). scrollTo(절대 좌표) + item_count만
# 보는 방식(scratchpad/page300_4b2_apollo_consistency/probe_consistency.py)은
# 같은 검색에서 53건에 그쳤고, 구조 비교 결과 조기 종료 아티팩트로 판정되어
# 이번 구현에는 사용하지 않는다.

_DOM_SCROLL_JS = """async () => {
    const container = document.querySelector("#_pcmap_list_scroll_container");
    if (!container) return {status: 'no_container', iters: 0};
    let lastHeight = container.scrollHeight;
    let lastRowCount = container.querySelectorAll('li.UEzoS.rTjJo').length;
    let lastNameCount = container.querySelectorAll('li.UEzoS.rTjJo .TYaxT').length;
    let stable = 0;
    let iters = 0;
    while (iters < 40) {
        container.scrollBy(0, 1000);
        await new Promise(r => setTimeout(r, 600));
        const h = container.scrollHeight;
        const rc = container.querySelectorAll('li.UEzoS.rTjJo').length;
        const nc = container.querySelectorAll('li.UEzoS.rTjJo .TYaxT').length;
        if (h === lastHeight && rc === lastRowCount && nc === lastNameCount) {
            stable++;
            if (stable >= 3) break;
        } else {
            stable = 0;
            lastHeight = h;
            lastRowCount = rc;
            lastNameCount = nc;
        }
        iters++;
    }
    return {status: 'done', iters: iters, scrollHeight: lastHeight, rowCount: lastRowCount, nameCount: lastNameCount};
}"""

_DOM_ROW_EXTRACTION_JS = """() => {
    // PAGE300-DOM-2: DOM anchor href가 전부 "#"(placeholder)임이 실측 확인됨에 따라,
    // React가 DOM node에 심어두는 __reactFiber$*/__reactProps$* 속성에서 place_id
    // 후보를 함께 수집한다(scratchpad/page300_4d_dom_place_id_audit/audit.py에서
    // 42/42 row 재현 검증된 방식). 여기서는 원시 후보만 모으고, 검증/우선순위 판정
    // (형식 검증/충돌 감지)은 Python의 resolve_dom_identifier가 담당한다.
    const SKIP_KEYS = new Set(['ref', 'return', 'sibling', 'parent', 'child',
        'memoizedProps', 'memoizedState', 'stateNode', 'updateQueue']);
    const ID_KEY_PATTERN = /id|place|business|url|href|link|restaurant|entry|cid/i;
    const MAX_DEPTH = 6;
    const MAX_VISITED = 500;

    function boundedSearch(obj, depth, visited) {
        const results = [];
        if (depth <= 0 || !obj || typeof obj !== 'object') return results;
        if (visited.count >= MAX_VISITED || visited.seen.has(obj)) return results;
        visited.seen.add(obj);
        visited.count++;

        let keys;
        try { keys = Object.keys(obj); } catch (e) { return results; }

        for (const k of keys) {
            if (SKIP_KEYS.has(k)) continue;
            let v;
            try { v = obj[k]; } catch (e) { continue; }
            if (v === null || v === undefined) continue;
            if (typeof v !== 'object' && typeof v !== 'function') {
                if (ID_KEY_PATTERN.test(k)) results.push({path: k, value: String(v)});
            } else if (typeof v === 'object') {
                if (visited.count >= MAX_VISITED) break;
                const nested = boundedSearch(v, depth - 1, visited);
                for (const r of nested) results.push(r);
            }
        }
        return results;
    }

    function extractIdentifierCandidates(el) {
        let fiberKey = null;
        for (const key of Object.keys(el)) {
            if (key.startsWith('__reactFiber$') || key.startsWith('__reactProps$')) {
                fiberKey = key;
                break;
            }
        }
        if (!fiberKey) return {fast_item_id: '', fast_apollo_cache_id: '', bounded_candidates: []};

        const fiber = el[fiberKey];
        const children = fiber && fiber.pendingProps ? fiber.pendingProps.children : undefined;
        const item = Array.isArray(children) && children[1] && children[1].props ? children[1].props.item : undefined;

        const fastItemId = (item && item.id !== undefined && item.id !== null) ? String(item.id) : '';
        const fastApolloId = (item && item.apolloCacheId !== undefined && item.apolloCacheId !== null) ? String(item.apolloCacheId) : '';

        let bounded = [];
        if (!fastItemId && !fastApolloId && fiber) {
            bounded = boundedSearch(fiber, MAX_DEPTH, {seen: new Set(), count: 0});
        }
        return {fast_item_id: fastItemId, fast_apollo_cache_id: fastApolloId, bounded_candidates: bounded};
    }

    const rows = Array.from(document.querySelectorAll('li.UEzoS.rTjJo'));
    return rows.map((row, i) => {
        const nameEl = row.querySelector('.TYaxT');
        const catEl = row.querySelector('.KCMnt');
        const anchors = Array.from(row.querySelectorAll('a[href]')).map(a => a.getAttribute('href'));
        const data_attributes = {};
        for (const attr of row.attributes) {
            if (attr.name.startsWith('data-')) data_attributes[attr.name] = attr.value;
        }
        return {
            dom_index: i,
            name: nameEl ? nameEl.innerText.trim() : "",
            category: catEl ? catEl.innerText.trim() : "",
            raw_text: row.innerText ? row.innerText.trim() : "",
            anchor_hrefs: anchors,
            data_attributes: data_attributes,
            identifier_candidates: extractIdentifierCandidates(row),
        };
    });
}"""

_APOLLO_ENTITY_EXTRACTION_JS = """() => {
    const state = window.__APOLLO_STATE__;
    if (!state || typeof state !== 'object') return {available: false, entities: []};
    const out = [];
    for (const key of Object.keys(state)) {
        const obj = state[key];
        if (!obj || typeof obj !== 'object') continue;
        if (typeof obj.name !== 'string' || !obj.name || obj.category === undefined) continue;
        const idFromKey = key.indexOf(':') >= 0 ? key.split(':')[1] : '';
        out.push({
            apollo_key: key,
            place_id: String(obj.id || idFromKey || ''),
            name: obj.name || '',
            category: obj.category || '',
            address: obj.address || obj.roadAddress || '',
            review_count: (obj.reviewCount !== undefined && obj.reviewCount !== null) ? String(obj.reviewCount) : '',
        });
    }
    return {available: true, entities: out};
}"""

# 5O(2026-07-23): 상세 페이지 방문 시 window.__APOLLO_STATE__에서 현재 place_id의
# PlaceDetailBase(base)와, ROOT_QUERY 안의 placeDetail(...) parent 후보만 축소
# 발췌한다(요청서 §8 - state 전체를 직렬화하지 않음). Base/Parent 선택·검증
# (exact base.__ref 일치, stale 차단)은 여기서 하지 않고 순수 Python adapter
# extract_normalized_apollo_detail()에 위임한다 - 이 JS는 후보를 좁히기만 한다.
_APOLLO_DETAIL_EXTRACTION_JS = """(placeId) => {
    const state = window.__APOLLO_STATE__;
    if (!state || typeof state !== 'object') return {available: false, apollo_state: {}};
    const bounded = {};
    const baseKey = 'PlaceDetailBase:' + placeId;
    if (state[baseKey] && typeof state[baseKey] === 'object') {
        bounded[baseKey] = state[baseKey];
    }
    const rootQuery = state['ROOT_QUERY'];
    if (rootQuery && typeof rootQuery === 'object') {
        const quotedId = '"' + placeId + '"';
        const boundedRoot = {};
        for (const key of Object.keys(rootQuery)) {
            if (key.indexOf('placeDetail(') >= 0 && key.indexOf(quotedId) >= 0) {
                const value = rootQuery[key];
                boundedRoot[key] = value;
                // parent가 {"__ref": "..."} 형태면 참조 대상 entity도 1단계만 함께 담는다
                // (adapter가 apollo_state에서 그 entity를 찾을 수 있도록).
                if (value && typeof value === 'object' && typeof value.__ref === 'string') {
                    const refEntity = state[value.__ref];
                    if (refEntity && typeof refEntity === 'object') {
                        bounded[value.__ref] = refEntity;
                    }
                }
            }
        }
        if (Object.keys(boundedRoot).length > 0) {
            bounded['ROOT_QUERY'] = boundedRoot;
        }
    }
    return {available: true, apollo_state: bounded};
}"""

_CURRENT_PAGE_AND_TOP10_JS = """() => {
    const rows = Array.from(document.querySelectorAll('li.UEzoS.rTjJo'));
    const top10 = rows.slice(0, 10).map(r => {
        const el = r.querySelector('.TYaxT');
        return el ? el.innerText.trim() : '';
    });
    let page = null;
    const pageMatches = document.querySelectorAll('.mBN2s.qxokY, a[aria-current="true"], a[aria-current="page"]');
    for (const p of pageMatches) {
        const num = parseInt((p.innerText || '').trim().replace(/[^0-9]/g, ''), 10);
        if (num) { page = num; break; }
    }
    return {page: page, top10: top10};
}"""


def _parse_candidate_entry_items(entry: dict) -> dict:
    """collect_network_query 내부의 _ensure_parsed(closure라 직접 재사용 불가)와
    동일한 안전 판정(HTTP 오류/non-JSON body 제외)만 최소로 재구현한다.
    BOM/compression 분류 등 진단 전용 필드는 이 경로에서 필요하지 않으므로
    만들지 않는다 - candidate_error_type/body_snapshot_ready 등 상태 자체는
    이미 재사용 중인 response/requestfinished/requestfailed 핸들러가
    채워두므로 중복 구현하지 않는다."""
    if entry.get("candidate_error_type") == "CandidateHttpError":
        return {"items": [], "error": True}
    if not entry.get("body_snapshot_ready"):
        return {"items": [], "error": bool(entry.get("body_snapshot_error_type"))}
    body = entry.get("body_snapshot")
    first_char = _classify_first_non_whitespace_character(body) if body is not None else "empty"
    if first_char not in ("{", "["):
        return {"items": [], "error": True}
    try:
        data = json.loads(body)
    except Exception:
        return {"items": [], "error": True}
    return {"items": _extract_list_items(data), "error": False}


def _harvest_all_candidates(ctx: "_QueryObservationContext") -> list:
    """지금까지 관측된 candidate 전부를 파싱해 raw item 목록으로 합친다(page당
    호출 빈도가 낮고 candidate 수가 많지 않아, 인덱스 기반 증분 harvest 대신
    매번 전체를 다시 파싱하는 단순한 방식을 택했다)."""
    raw_items: list = []
    for entry in ctx.candidates:
        parsed = _parse_candidate_entry_items(entry)
        if not parsed["error"]:
            raw_items.extend(parsed["items"])
    return raw_items


def _has_blocking_http_status(ctx: "_QueryObservationContext", statuses=(403, 405)) -> bool:
    return any(e.get("status") in statuses for e in ctx.candidates)


def _wait_for_dom_page_transition(page, frame, expected_page_number: int, previous_signature: dict, *,
                                   hard_cap_ms: int = 15000, poll_ms: int = 300) -> dict:
    """클릭 이후 다음 페이지 전환 완료를 DOM 기준으로 확인한다(요청서 §5/§7 -
    page 번호/active 속성만으로 완료 처리 금지). expected_page_number와
    실제 활성 페이지 번호가 같고, top-10 signature가 이전 페이지와 달라야
    confirmed=True. hard_cap_ms 안에 확인되지 않으면 reason으로 "active 페이지
    번호 자체가 한 번도 기대값과 일치하지 않음"(transition_timeout)과 "번호는
    일치했지만 signature가 그대로임"(signature_unchanged)을 구분해 반환한다."""
    elapsed_ms = 0
    saw_expected_page = False
    while elapsed_ms < hard_cap_ms:
        page.wait_for_timeout(poll_ms)
        elapsed_ms += poll_ms
        try:
            result = frame.evaluate(_CURRENT_PAGE_AND_TOP10_JS)
        except Exception:
            continue
        actual_page = result.get("page")
        if actual_page == expected_page_number:
            saw_expected_page = True
        top10 = result.get("top10") or []
        new_signature = compute_page_signature([{"normalized_name": n} for n in top10])
        current_flag_ok = actual_page is not None
        if page_transition_confirmed(expected_page_number, actual_page, current_flag_ok, previous_signature, new_signature):
            return {"confirmed": True, "elapsed_ms": elapsed_ms, "reason": "confirmed"}
    reason = "signature_unchanged" if saw_expected_page else "transition_timeout"
    return {"confirmed": False, "elapsed_ms": elapsed_ms, "reason": reason}


# ============================================================================
# PAGE300-DETAIL-1: place_id 기반 상세정보 enrichment(대표전화/주소/홈페이지/
# 인스타/블로그/플레이스 URL 확정). src/pc/detail_scraper.py의 collect_full은
# 카드를 처음부터 다시 찾아 클릭하는 순회형 collector라 place_id를 입력받는
# 함수가 아니다(감사 결과, PROJECT_STATE.md 기록) - 그래서 새 순회/진입 로직
# (_fetch_place_detail)만 새로 작성하고, entryIframe 콘텐츠 추출 로직
# (_extract_entry_phone/_extract_entry_address/_extract_entry_sns/
# _entry_title/_title_matches)은 detail_scraper.py에서 그대로 import해
# 재사용한다(재구현 금지 원칙). session.find_entry_frame()은
# NativeCdpBrowserSession에는 없으므로(BrowserSession 전용 메서드) 이 모듈의
# 기존 _find_search_frame(page) 패턴을 그대로 따르는 자유 함수로 새로 만든다.
# ============================================================================

_DETAIL_HTTP_BLOCKING_STATUSES = (403, 405, 429)


def _find_entry_frame_like(page):
    """_find_search_frame(page)와 동일한 폴백 패턴으로 "entry"가 이름/URL에
    포함된 frame을 찾는다. 못 찾으면(직접 URL 진입 시 iframe 없이 본문에 바로
    렌더링되는 경우 대응 - Live로 실측 확인 필요) page 자신을 반환한다 -
    이 모듈이 재사용하는 추출 함수들(_extract_entry_phone 등)은 `.locator()`만
    쓰므로 Page/Frame 어느 쪽을 받아도 동일하게 동작한다."""
    try:
        frame = page.frame(name="entryIframe")
        if frame:
            return frame
    except Exception:
        pass
    try:
        for frame in page.frames:
            frame_id = f"{getattr(frame, 'name', '')} {getattr(frame, 'url', '')}".lower()
            if "entry" in frame_id:
                return frame
    except Exception:
        pass
    return page


_SSR_MAX_HTML_CHARS = 5_000_000
_SSR_BLOCK_TEXT_MARKERS = ("보안 확인", "자동입력방지문자", "captcha_challenge", "captcha-wrapper")
_SSR_APOLLO_STATE_PREFIX = "window.__APOLLO_STATE__"
_SSR_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://m.place.naver.com/",
}
_SSR_REQUEST_TIMEOUT_MS = 15000


def _parse_apollo_state_from_html(html_text: str) -> dict | None:
    """SSR HTML 응답 본문에서 window.__APOLLO_STATE__ 값을 안전하게 추출한다.

    5W 감사(page300_5w_r1_multirun_evidence_integrity_audit)가 `\\{.*?\\}` 형태의
    non-greedy 정규식은 값 내부에 이스케이프된 `}` 문자열이 있으면 JSON 경계를
    조기 절단할 위험이 있다고 지적했다 - 이 함수는 대신 `json.JSONDecoder().
    raw_decode()`로 실제 JSON 문법 경계를 정확히 찾는다(중첩 객체/이스케이프
    문자열/트레일링 `</script>`에 안전). 병적으로 큰 응답(_SSR_MAX_HTML_CHARS
    초과)은 파싱을 시도하지 않고 None을 반환한다. 예외를 던지지 않고 항상
    dict 또는 None만 반환한다."""
    if not html_text or len(html_text) > _SSR_MAX_HTML_CHARS:
        return None
    marker_pos = html_text.find(_SSR_APOLLO_STATE_PREFIX)
    if marker_pos < 0:
        return None
    eq_pos = html_text.find("=", marker_pos + len(_SSR_APOLLO_STATE_PREFIX))
    if eq_pos < 0:
        return None
    start = eq_pos + 1
    while start < len(html_text) and html_text[start] in " \t\r\n":
        start += 1
    try:
        value, _end = json.JSONDecoder().raw_decode(html_text, start)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def _classify_ssr_block_signal(status_code, html_text: str) -> dict:
    """SSR 응답이 차단(CAPTCHA/HTTP 403·405·429)인지 텍스트/상태 기준으로
    판정한다. DOM 방문 기반 classify_captcha_signal은 렌더링된 page의
    locator(bounding_box 등)를 요구하므로 이 경로(page.request, 렌더링 없음)에는
    적용할 수 없다 - 5S/5T/5W가 실측으로 검증한 텍스트 마커를 그대로 재사용한
    별도의 텍스트 기반 판정으로 대체한다."""
    if status_code in _DETAIL_HTTP_BLOCKING_STATUSES:
        return {"blocked": True, "block_type": f"HTTP_{status_code}"}
    lowered = (html_text or "").lower()
    for marker in _SSR_BLOCK_TEXT_MARKERS:
        if marker in (html_text or "") or marker.lower() in lowered:
            return {"blocked": True, "block_type": "CAPTCHA_CHALLENGE"}
    return {"blocked": False, "block_type": ""}


def _fetch_place_detail_ssr(page, row: dict, *, should_continue=None) -> dict:
    """PAGE300-SSR-1: place_id 기반 상세정보를 BrowserContext-shared
    APIRequestContext(page.request)로 HTML GET 1회만 수행해 확보한다(요청서
    §3/§4). page.goto()로 렌더링하지 않으므로 상세 UI navigation은 0회다.

    반환 dict는 항상 detail_ssr_* 진단 키 11개(요청서 §4)와, 성공 시
    merge_detail_into_row가 바로 소비하는 병합용 필드(업종/새로오픈여부/
    방문자리뷰수/블로그리뷰수/총리뷰수/대표전화/주소/플레이스 URL/홈페이지/
    인스타/블로그/place_id/detail_success)를 포함한다. detail_success=True는
    detail_ssr_status="success"일 때만 설정한다 - merge_detail_into_row는
    detail_success 키만 확인하므로 이 함수는 그 계약을 그대로 재사용하고
    수정하지 않는다.

    예외를 던지지 않고 항상 dict를 반환한다(row 삭제 방지 원칙). retry는
    수행하지 않는다(업체당 SSR 요청 최대 1회 - 실패 시 호출자가 기존 상세 UI
    fallback을 별도로 판단한다)."""
    place_id = str(row.get("place_id") or "").strip()
    result = {
        "detail_ssr_attempted": False,
        "detail_ssr_status": "",
        "detail_ssr_http_status": None,
        "detail_ssr_apollo_found": False,
        "detail_ssr_base_found": False,
        "detail_ssr_parent_found": False,
        "detail_ssr_place_id_exact": False,
        "detail_ssr_adapter_success": False,
        "detail_ssr_stop_reason": "",
        "detail_ssr_error_type": "",
        "detail_ssr_duration_seconds": 0.0,
        "detail_success": False,
        "place_id": place_id,
        "업종": "",
        "새로오픈여부": "",
        "방문자리뷰수": "",
        "블로그리뷰수": "",
        "총리뷰수": "",
        "대표전화": "",
        "주소": "",
        "플레이스 URL": "",
        "홈페이지": "",
        "인스타": "",
        "블로그": "",
        "추가 링크": "",
    }
    place_url = build_place_url_from_id(place_id)
    if not place_url:
        result["detail_ssr_status"] = "no_place_url"
        result["detail_ssr_stop_reason"] = "no_place_url"
        result["detail_ssr_error_type"] = "MissingPlaceId"
        return result

    if should_continue is not None and not should_continue():
        result["detail_ssr_status"] = "user_stopped"
        result["detail_ssr_stop_reason"] = "user_stopped"
        result["detail_ssr_error_type"] = "UserStopped"
        return result

    result["detail_ssr_attempted"] = True
    t0 = time.time()
    try:
        resp = page.request.get(place_url, headers=_SSR_REQUEST_HEADERS, timeout=_SSR_REQUEST_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_timeout"
        result["detail_ssr_error_type"] = "Timeout"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result
    except Exception as exc:
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_request_error"
        result["detail_ssr_error_type"] = type(exc).__name__
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    status_code = resp.status
    result["detail_ssr_http_status"] = status_code
    try:
        content_type = resp.headers.get("content-type", "") if resp.headers else ""
    except Exception:
        content_type = ""
    try:
        html_text = resp.text()
    except Exception:
        html_text = ""

    block_signal = _classify_ssr_block_signal(status_code, html_text[:4000])
    if block_signal["blocked"]:
        result["detail_ssr_status"] = "blocked"
        result["detail_ssr_stop_reason"] = block_signal["block_type"]
        result["detail_ssr_error_type"] = "Blocked"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    if should_continue is not None and not should_continue():
        result["detail_ssr_status"] = "user_stopped"
        result["detail_ssr_stop_reason"] = "user_stopped"
        result["detail_ssr_error_type"] = "UserStopped"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    if status_code != 200 or "text/html" not in content_type:
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_unexpected_response"
        result["detail_ssr_error_type"] = "UnexpectedContentType" if status_code == 200 else "UnexpectedHttpStatus"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    apollo_state = _parse_apollo_state_from_html(html_text)
    result["detail_ssr_apollo_found"] = apollo_state is not None
    if apollo_state is None:
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_apollo_missing"
        result["detail_ssr_error_type"] = "ApolloStateNotFound"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    base_key = f"PlaceDetailBase:{place_id}"
    base_entity = apollo_state.get(base_key)
    base_found = isinstance(base_entity, dict)
    result["detail_ssr_base_found"] = base_found
    if base_found:
        base_id = str(base_entity.get("id") or "").strip()
        if base_id and base_id != place_id:
            result["detail_ssr_status"] = "mismatch"
            result["detail_ssr_stop_reason"] = "place_id_mismatch"
            result["detail_ssr_error_type"] = "PlaceIdMismatch"
            result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
            return result
        result["detail_ssr_place_id_exact"] = True
    else:
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_base_missing"
        result["detail_ssr_error_type"] = "BaseNotFound"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    apollo_detail = extract_normalized_apollo_detail(apollo_state, place_id)
    if not apollo_detail:
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_adapter_empty"
        result["detail_ssr_error_type"] = "AdapterEmpty"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result
    result["detail_ssr_adapter_success"] = True

    parent_found = any(
        apollo_detail.get(field) is not None for field in ("homepages", "newOpening", "phoneInfo")
    )
    result["detail_ssr_parent_found"] = parent_found
    if not parent_found:
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_parent_missing"
        result["detail_ssr_error_type"] = "ParentNotFound"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    apollo_row = _map_item_to_row(apollo_detail, "")
    visitor_reviews = apollo_row.get("방문자리뷰수")
    blog_reviews = apollo_row.get("블로그리뷰수")
    if visitor_reviews in (None, "") and blog_reviews in (None, ""):
        result["detail_ssr_status"] = "needs_fallback"
        result["detail_ssr_stop_reason"] = "detail_ssr_reviews_missing"
        result["detail_ssr_error_type"] = "ReviewFieldsMissing"
        result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
        return result

    result["detail_ssr_status"] = "success"
    result["detail_success"] = True
    result["업종"] = apollo_row.get("업종", "")
    result["새로오픈여부"] = apollo_row.get("새로오픈여부", "")
    result["방문자리뷰수"] = visitor_reviews if visitor_reviews not in (None,) else ""
    result["블로그리뷰수"] = blog_reviews if blog_reviews not in (None,) else ""
    result["총리뷰수"] = apollo_row.get("총리뷰수", "")
    result["대표전화"] = apollo_row.get("대표전화", "")
    result["주소"] = apollo_row.get("주소", "")
    result["플레이스 URL"] = place_url
    result["홈페이지"] = apollo_row.get("홈페이지", "")
    result["인스타"] = apollo_row.get("인스타", "")
    result["블로그"] = apollo_row.get("블로그", "")
    result["추가 링크"] = apollo_row.get("추가 링크", "")
    result["detail_ssr_duration_seconds"] = round(time.time() - t0, 3)
    return result


def _fetch_place_detail(page, row: dict, *, retry: int = _DETAIL_RETRY, should_continue=None) -> dict:
    """row(place_id 포함)의 상세 페이지를 직접 URL로 방문해 대표전화/주소/
    홈페이지/인스타/블로그/실제 플레이스 URL을 확보한다. 예외를 던지지 않고
    항상 dict를 반환한다(row 삭제 방지 원칙 - 호출자는 실패해도 기존 값을
    유지하면 된다). place_id가 없어 URL을 만들 수 없으면 즉시
    detail_attempted=False로 반환한다.

    PAGE300-DETAIL-2: should_continue(선택, 인자 없이 bool 반환)가 주어지고
    False를 반환하면 첫 시도를 포함해 매 재시도 직전에 확인하여 즉시
    detail_stop_reason="user_stopped"로 중단한다(요청서 §6 "각 상세 업체
    방문 전, retry 전"). None(기본값)이면 기존 동작과 완전히 동일하다."""
    name = str(row.get("업체명") or "")
    place_id = row.get("place_id") or ""
    place_url = build_place_url_from_id(place_id)
    result = {
        "detail_attempted": False,
        "detail_success": False,
        "detail_stop_reason": "",
        "detail_http_status": None,
        "detail_source": "direct_place_url",
        "detail_error_type": "",
        "place_id": place_id,
        "업종": "",
        "새로오픈여부": "",
        "방문자리뷰수": "",
        "블로그리뷰수": "",
        "총리뷰수": "",
        "대표전화": "",
        "주소": "",
        "플레이스 URL": "",
        "홈페이지": "",
        "인스타": "",
        "블로그": "",
        "추가 링크": "",
    }
    if not place_url:
        result["detail_stop_reason"] = "no_place_url"
        result["detail_error_type"] = "MissingPlaceId"
        return result

    result["detail_attempted"] = True
    attempts_left = 1 + max(0, retry)
    last_error_type = ""
    last_stop_reason = "unknown_failure"

    while attempts_left > 0:
        if should_continue is not None and not should_continue():
            result["detail_stop_reason"] = "user_stopped"
            result["detail_error_type"] = "UserStopped"
            return result
        attempts_left -= 1
        http_statuses: list = []

        def _handle_response(response, _statuses=http_statuses):
            try:
                if response.url == place_url or place_url in (response.url or ""):
                    _statuses.append(response.status)
            except Exception:
                pass

        try:
            page.on("response", _handle_response)
        except Exception:
            pass
        try:
            try:
                page.goto(place_url, wait_until="domcontentloaded", timeout=15000)
            except PlaywrightTimeoutError:
                pass
            except Exception as exc:
                last_error_type = type(exc).__name__
                last_stop_reason = "navigation_error"
                continue
            finally:
                try:
                    page.off("response", _handle_response)
                except Exception:
                    pass

            blocking = [s for s in http_statuses if s in _DETAIL_HTTP_BLOCKING_STATUSES]
            if blocking:
                result["detail_http_status"] = blocking[0]
                result["detail_stop_reason"] = "detail_http_error"
                result["detail_error_type"] = "DetailHttpError"
                return result

            probe = _probe_captcha_state(page)
            signal = classify_captcha_signal(
                marker_present_in_dom=probe["marker_present"],
                element_visible=probe["visible"],
                bounding_box_area=probe["bounding_box_area"],
                click_exception_message=probe["click_intercepted_message"],
            )
            if signal["active_captcha_detected"]:
                result["detail_stop_reason"] = "captcha_detected"
                result["detail_error_type"] = "CaptchaDetected"
                return result

            entry_frame = _find_entry_frame_like(page)
            title = _entry_title(entry_frame)
            if not _title_matches(title, name):
                last_error_type = "TitleMismatch"
                last_stop_reason = "entry_title_mismatch"
                continue

            phone = _extract_entry_phone(entry_frame)
            if phone and _is_personal_mobile_phone(phone):
                # 5O §9: DOM 상세 추출 결과 자체에서도 개인 휴대전화를 제거한다
                # (merge_detail_into_row 단계에서만 걸러지던 기존 gap 보강).
                phone = ""
            address = _extract_entry_address(entry_frame)
            homepage, insta, blog = _extract_entry_sns(entry_frame)

            result["detail_success"] = True
            result["detail_stop_reason"] = ""
            result["대표전화"] = phone
            result["주소"] = address
            result["플레이스 URL"] = place_url
            result["홈페이지"] = homepage
            result["인스타"] = insta
            result["블로그"] = blog

            # 5O: Apollo State(PlaceDetailBase + parent PlaceDetail)로 방문자/
            # 블로그 리뷰수·새로오픈여부·(비어있는 경우) 대표전화/주소/홈페이지/
            # 인스타/블로그를 best-effort 보강한다. 실패해도 위에서 이미 확정된
            # DOM 결과와 detail_success는 그대로 유지한다(§7 - fallback 보존).
            try:
                apollo_raw = entry_frame.evaluate(_APOLLO_DETAIL_EXTRACTION_JS, place_id)
            except Exception:
                apollo_raw = None
            if isinstance(apollo_raw, dict) and apollo_raw.get("available"):
                try:
                    apollo_detail = extract_normalized_apollo_detail(apollo_raw.get("apollo_state") or {}, place_id)
                except Exception:
                    apollo_detail = {}
                if apollo_detail:
                    apollo_row = _map_item_to_row(apollo_detail, "")
                    if not result["대표전화"] and apollo_row.get("대표전화"):
                        result["대표전화"] = apollo_row["대표전화"]
                    if not result["주소"] and apollo_row.get("주소"):
                        result["주소"] = apollo_row["주소"]
                    if not result["업종"] and apollo_row.get("업종"):
                        result["업종"] = apollo_row["업종"]
                    for field in ("홈페이지", "인스타", "블로그", "추가 링크"):
                        if not result[field] and apollo_row.get(field):
                            result[field] = apollo_row[field]
                    if not result["새로오픈여부"] and apollo_row.get("새로오픈여부"):
                        result["새로오픈여부"] = apollo_row["새로오픈여부"]
                    result["방문자리뷰수"] = apollo_row.get("방문자리뷰수", "")
                    result["블로그리뷰수"] = apollo_row.get("블로그리뷰수", "")
                    result["총리뷰수"] = apollo_row.get("총리뷰수", "")

            return result
        except Exception as exc:
            last_error_type = type(exc).__name__
            last_stop_reason = "unexpected_exception"
            continue

    result["detail_stop_reason"] = last_stop_reason
    result["detail_error_type"] = last_error_type
    return result


def collect_dom_membership_query(page, job, target_count, *, collected_at, max_pages: int = 5) -> dict:
    """단일 검색어에서 DOM membership 기준으로 최대 max_pages 페이지를 수집한다.

    반환: {"rows", "final_unique_count", "page_count", "stop_reason",
    "active_captcha_detected", "status_429_seen", "navigation_error",
    "navigation_error_message", "per_page_diagnostics", "page_signatures"}.
    rows는 exporter.MERGED_COLUMNS(11컬럼) 키 + 내부 place_id/source_page/
    dom_index/match_confidence/_dedup_raw_text를 가진 dict 목록이며, DOM
    표시 순서를 그대로 보존한다.

    이 함수는 UI/network_pipeline.run_collection_plan에 연결되지 않은
    독립 함수다(요청서 §7 - 최소 변경, 기존 collect_network_query는
    수정하지 않고 그 helper들만 재사용한다).
    """
    ctx = _QueryObservationContext()
    response_handler = _make_response_handler(ctx)
    request_finished_handler = _make_request_finished_handler(ctx)
    request_failed_handler = _make_request_failed_handler(ctx)
    registered_listeners: list = []
    try:
        for event, handler in (
            ("response", response_handler),
            ("requestfinished", request_finished_handler),
            ("requestfailed", request_failed_handler),
        ):
            page.on(event, handler)
            registered_listeners.append((event, handler))
    except Exception:
        for event, handler in registered_listeners:
            try:
                page.off(event, handler)
            except Exception:
                pass
        raise

    result = {
        "rows": [],
        "final_unique_count": 0,
        "page_count": 0,
        "stop_reason": None,
        "active_captcha_detected": False,
        "status_429_seen": False,
        "navigation_error": False,
        "navigation_error_message": "",
        "per_page_diagnostics": [],
        "page_signatures": [],
    }

    try:
        search_url = _SEARCH_URL_TEMPLATE.format(query=quote(job["query"]))
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
        except PlaywrightTimeoutError:
            pass
        except Exception as exc:
            result["navigation_error"] = True
            result["navigation_error_message"] = f"{type(exc).__name__}: {exc}"
            result["stop_reason"] = "navigation_error"
            return result

        frame = _find_search_frame(page)
        if frame is None:
            result["stop_reason"] = "dom_frame_not_found"
            return result

        all_rows: list = []
        seen: set = set()
        page_number = 1
        accumulator = GlobalPlaceAccumulator(collected_at=collected_at)

        while True:
            probe = _probe_captcha_state(page)
            signal = classify_captcha_signal(
                marker_present_in_dom=probe["marker_present"],
                element_visible=probe["visible"],
                bounding_box_area=probe["bounding_box_area"],
                click_exception_message=probe["click_intercepted_message"],
            )
            if signal["active_captcha_detected"]:
                result["active_captcha_detected"] = True
                result["stop_reason"] = "captcha_detected"
                break
            if ctx.status_429_seen:
                result["status_429_seen"] = True
                result["stop_reason"] = "status_429_seen"
                break

            scroll_result = frame.evaluate(_DOM_SCROLL_JS)
            if scroll_result.get("status") == "no_container":
                result["stop_reason"] = "dom_container_lost"
                break

            # PAGE300-DOM-2: Apollo를 DOM row 정규화보다 먼저 추출한다 -
            # resolve_dom_identifier의 guard(§apollo_key_exists_for_id)가
            # Apollo 원본 key 목록을 필요로 하기 때문이다. _APOLLO_ENTITY_
            # EXTRACTION_JS가 이미 각 entity의 apollo_key를 반환하므로 추가
            # evaluate 없이 그 키들을 집합으로 재사용한다.
            try:
                apollo_raw = frame.evaluate(_APOLLO_ENTITY_EXTRACTION_JS)
            except Exception:
                apollo_raw = {"available": False, "entities": []}
            apollo_available = bool(apollo_raw.get("available"))
            apollo_entities = apollo_raw.get("entities") or [] if apollo_available else []
            apollo_raw_keys = {e.get("apollo_key") for e in apollo_entities if e.get("apollo_key")}
            apollo_index = build_entity_index([
                to_common_entity(entity, id_key="place_id", name_key="name", category_key="category", address_key="address")
                for entity in apollo_entities
            ])

            raw_dom_rows = frame.evaluate(_DOM_ROW_EXTRACTION_JS) or []
            normalized_rows = [normalize_dom_row(r, page_number, apollo_raw_keys) for r in raw_dom_rows]
            kept_rows = [r for r in normalized_rows if not is_skeleton_dom_row(r)]

            page.wait_for_timeout(500)
            if _has_blocking_http_status(ctx):
                result["stop_reason"] = "candidate_http_error"
                break
            if ctx.status_429_seen:
                result["status_429_seen"] = True
                result["stop_reason"] = "status_429_seen"
                break

            network_raw_items = _harvest_all_candidates(ctx)
            for item in network_raw_items:
                accumulator.add_raw_item(item, source_page=page_number, source_query=job.get("query"))
            network_rows = accumulator.get_all_rows()
            network_index = build_entity_index([
                to_common_entity(
                    row, id_key="place_id", name_key="업체명", category_key="업종",
                    address_key="주소", url_key="플레이스 URL",
                )
                for row in network_rows
            ])

            page_built_rows = []
            match_results = []
            network_exact_id_count = 0
            apollo_exact_id_count = 0
            for dom_row in kept_rows:
                network_match = resolve_match(dom_row, network_index)
                apollo_match = resolve_match(dom_row, apollo_index)
                built_row = merge_dom_row_fields(dom_row, network_match, apollo_match, collected_at)
                page_built_rows.append(built_row)
                match_results.append({"overall": overall_row_confidence(network_match, apollo_match)})
                if network_match.get("confidence") == "EXACT_ID":
                    network_exact_id_count += 1
                if apollo_match.get("confidence") == "EXACT_ID":
                    apollo_exact_id_count += 1

            page_signature = compute_page_signature(kept_rows)
            result["page_signatures"].append(page_signature)

            newly_unique = dedup_membership_rows(page_built_rows, seen)
            all_rows.extend(newly_unique)
            result["page_count"] = page_number

            diagnostics = summarize_membership_diagnostics(match_results)
            diagnostics["duplicate_count"] = len(page_built_rows) - len(newly_unique)
            diagnostics["final_unique_count"] = len(all_rows)
            # PAGE300-DOM-2: identifier_method별 집계(§11 Live 측정 요구사항).
            identifier_method_counts: dict = {}
            for dom_row in kept_rows:
                method = dom_row.get("identifier_method") or "UNRESOLVED"
                identifier_method_counts[method] = identifier_method_counts.get(method, 0) + 1
            resolved_place_ids = {dom_row.get("place_id") for dom_row in kept_rows if dom_row.get("place_id")}
            result["per_page_diagnostics"].append({
                "page_number": page_number,
                "dom_row_count": len(kept_rows),
                "scroll_iters": scroll_result.get("iters"),
                "network_raw_item_count": len(network_raw_items),
                "apollo_available": apollo_available,
                "apollo_entity_count": len(apollo_entities),
                "identifier_method_counts": identifier_method_counts,
                "identifier_resolved_count": len(resolved_place_ids),
                "network_exact_id_count": network_exact_id_count,
                "apollo_exact_id_count": apollo_exact_id_count,
                **diagnostics,
            })

            if target_count and len(all_rows) >= target_count:
                result["stop_reason"] = "target_reached"
                break
            if page_number >= max_pages:
                result["stop_reason"] = "max_page_count_reached"
                break

            frame = _find_search_frame(page)
            if frame is None:
                result["stop_reason"] = "dom_frame_not_found"
                break

            button_locator = _find_page_button(frame, page_number + 1)
            try:
                button_count = button_locator.count() if button_locator is not None else 0
            except Exception:
                button_count = 0
            if button_count == 0:
                result["stop_reason"] = "next_page_button_not_found"
                break
            if button_count > 1:
                result["stop_reason"] = "ambiguous_page_button"
                break

            target_locator = button_locator.first
            try:
                is_ready = bool(target_locator.is_visible()) and bool(target_locator.is_enabled())
            except Exception:
                result["stop_reason"] = "pagination_click_error"
                break
            if not is_ready:
                result["stop_reason"] = "pagination_click_error"
                break

            try:
                target_locator.scroll_into_view_if_needed()
                target_locator.click()
            except Exception:
                result["stop_reason"] = "pagination_click_error"
                break

            transition = _wait_for_dom_page_transition(page, frame, page_number + 1, page_signature)
            if not transition["confirmed"]:
                result["stop_reason"] = (
                    "next_page_dom_signature_unchanged" if transition["reason"] == "signature_unchanged"
                    else "next_page_dom_transition_timeout"
                )
                break

            page_number += 1

        all_rows = accumulator.merge_into_dom_rows(all_rows)
        trimmed_rows = trim_membership_rows_to_target(all_rows, target_count)
        result["rows"] = trimmed_rows
        result["final_unique_count"] = len(trimmed_rows)
        return result
    finally:
        for event, handler in registered_listeners:
            try:
                page.off(event, handler)
            except Exception:
                pass


class DomMembershipCollector:
    """DOM-first membership production collector(PAGE300-DOM-2).

    `NetworkBrowserCollector`와 동일한 계약(컨텍스트 매니저 + `collect_query(job,
    per_query_limit)`)을 제공하되, 내부적으로 `collect_network_query` 대신
    `collect_dom_membership_query`를 호출한다. `src/ui.py`의
    `_run_network_pipeline` 기본 `collector_factory`로 배선되어 있다(2026-07-21,
    사용자 확인 - AskUserQuestion 응답: "실제 production 기본 경로는 새
    DomMembershipCollector를 사용하도록 배선"). `run_collection_plan`이 넘기는
    `per_query_limit`을 `collect_dom_membership_query`의 `target_count`로 그대로
    전달한다 - 검색 조합 큐가 여러 job이면 job마다 그 상한까지, 단일 job 큐면
    사실상 그 값이 최종 목표가 된다(기존 `NetworkBrowserCollector.collect_query`가
    `per_query_limit`을 `collect_network_query`에 그대로 전달하는 것과 동일한
    per-job 상한 의미론).

    `NetworkBrowserCollector`(collect_network_query 기반)는 이 클래스 추가로
    전혀 수정되지 않았고 legacy/회귀 테스트/비상 복구 경로로 그대로 보존된다.
    생명주기 코드가 `NetworkBrowserCollector`와 거의 동일해 보일 수 있으나,
    그 클래스를 건드리지 않기 위해 의도적으로 별도 작성했다(작은 중복을 감수).
    """

    def __init__(self, *, collected_at, session_factory=None, max_pages: int = 5):
        self.collected_at = collected_at
        self.max_pages = max_pages
        self._session_factory = session_factory or _default_session_factory
        self._session_cm = None
        self._session = None

    def __enter__(self):
        self._session_cm = self._session_factory()
        self._session = self._session_cm.__enter__()
        self._close_initial_page_if_present()
        return self

    def _close_initial_page_if_present(self) -> None:
        """BrowserSession.__enter__가 미리 만든 초기 page(session.page)는 쿼리별
        page 생성 방식과 무관하므로 수집용으로 쓰지 않고 즉시 닫는다(best-effort)."""
        initial_page = getattr(self._session, "page", None)
        if initial_page is None:
            return
        try:
            initial_page.close()
        except Exception:
            pass

    def collect_query(self, job, per_query_limit) -> dict:
        """run_collection_plan이 기대하는 collect_query(job, per_query_limit)
        시그니처를 만족하는 bound method. 공유 context에서 새 page를 만들어
        collect_dom_membership_query에 위임하고, 결과를 반환한 뒤 page를
        best-effort로 닫는다."""
        page = self._session.context.new_page()
        try:
            return collect_dom_membership_query(
                page,
                job,
                per_query_limit,
                collected_at=self.collected_at,
                max_pages=self.max_pages,
            )
        finally:
            try:
                page.close()
            except Exception:
                pass

    def enrich_detail(
        self, rows: list, *, max_targets: int = None, should_continue=None, on_progress=None
    ) -> list:
        """PAGE300-DETAIL-1/2: 이미 확보된 rows(place_id 포함, DOM 순서)의 앞쪽
        max_targets개(None이면 전체)만 상세 페이지를 순차 방문해 대표전화/주소/
        홈페이지/인스타/블로그/플레이스 URL을 병합한 새 리스트를 반환한다.
        동시성 없이 순차 실행하며, CAPTCHA/HTTP 403·405·429 감지 시 그 즉시
        중단하고 그때까지의 결과(이미 병합된 rows + 아직 시도하지 않은 원본
        rows)를 그대로 보존한다. 연속 실패가 _CONSECUTIVE_FAILURE_LIMIT를
        넘어도 동일하게 중단한다.

        should_continue(선택, 인자 없이 bool 반환)는 매 row 처리 전에
        확인한다(요청서 §6 "다음 업체로 이동하기 전") - False가 되면(사용자
        중지) 그 즉시 새 방문 없이 남은 row를 원본 그대로 보존하고 반환한다.
        `_fetch_place_detail`에도 그대로 전달해 retry 도중의 중지도 즉시
        반영한다.

        on_progress(선택, (completed, total, success_count, failure_count)
        호출)는 각 row 처리(성공/실패 불문) 직후 호출된다 - 콜백 자체가
        예외를 던져도 수집 자체는 계속 진행한다(진행률 표시 실패가 수집을
        막지 않도록)."""
        targets = list(rows[:max_targets]) if max_targets is not None else list(rows)
        remainder = list(rows[max_targets:]) if max_targets is not None else []
        total = len(targets)

        page = self._session.context.new_page()
        merged_rows: list = []
        consecutive_failures = 0
        success_count = 0
        failure_count = 0
        stop_reason = None
        try:
            for row in targets:
                if stop_reason is None and should_continue is not None and not should_continue():
                    stop_reason = "user_stopped"
                if stop_reason is not None:
                    merged_rows.append(row)
                    continue
                detail_result = _fetch_place_detail(page, row, should_continue=should_continue)
                merged_rows.append(merge_detail_into_row(row, detail_result))

                if detail_result["detail_success"]:
                    consecutive_failures = 0
                    success_count += 1
                else:
                    failure_count += 1
                    if detail_result["detail_stop_reason"] in ("captcha_detected", "detail_http_error", "user_stopped"):
                        stop_reason = detail_result["detail_stop_reason"]
                    else:
                        consecutive_failures += 1
                        if consecutive_failures >= _CONSECUTIVE_FAILURE_LIMIT:
                            stop_reason = "consecutive_failure_limit"

                if on_progress is not None:
                    try:
                        on_progress(len(merged_rows), total, success_count, failure_count)
                    except Exception:
                        pass
        finally:
            try:
                page.close()
            except Exception:
                pass

        return merged_rows + remainder

    def enrich_detail_ssr(
        self, rows: list, *, max_targets: int = None, should_continue=None, on_progress=None
    ) -> dict:
        """PAGE300-SSR-1: 이미 확보된 rows(전역 dedup 이후 최종 고유 목록,
        DOM 순서)의 앞쪽 max_targets개(None이면 전체)를 BrowserContext-shared
        SSR HTML GET(_fetch_place_detail_ssr)으로 순차 보강한다(요청서 §6/§7).

        업체당 SSR 요청은 최대 1회다. 다음 조건에서만 기존 상세 UI 방문
        방식(_fetch_place_detail)으로 업체당 최대 1회의 제한적 fallback을
        시도한다: HTTP 500/timeout/Apollo·Base·Parent 누락/리뷰 필드 완전
        누락(요청서 §8 "needs_fallback"). SSR 또는 fallback이 차단
        (CAPTCHA/HTTP 403·405·429)을 감지하면 그 즉시 전체 상세 보강을
        중단한다(우회/retry 없음). SSR이 place_id mismatch/stale response를
        감지하면 그 row는 병합하지 않고 마찬가지로 전체를 안전 중단한다
        (요청서 §8 - block과 별개의 독립된 중단 사유).

        같은 place_id가 rows에 두 번 이상 나타나도(전역 dedup 이후에는
        발생하지 않아야 하지만 방어적으로) SSR 요청은 place_id당 최초 1회만
        보내고 이후에는 캐시된 결과를 재사용한다.

        반환 dict: {"rows": 병합된 rows + 미시도 remainder, "stop_reason":
        str|None, "security_blocked": bool, "attempted_count": int,
        "ssr_success_count": int, "ui_fallback_used_count": int,
        "ui_fallback_success_count": int, "failure_count": int,
        "not_attempted_count": int}. 기존 enrich_detail(단순 list 반환)과
        달리 dict를 반환한다 - 요청서 §11이 요구하는 SSR 성공/UI fallback/
        실패/미시도 카운트를 호출자(UI)에 전달하기 위한 의도적인 차이다.
        """
        targets = list(rows[:max_targets]) if max_targets is not None else list(rows)
        remainder = list(rows[max_targets:]) if max_targets is not None else []
        total = len(targets)

        empty_counts = dict(
            attempted_count=0, ssr_success_count=0, ui_fallback_used_count=0,
            ui_fallback_success_count=0, failure_count=0,
        )

        if should_continue is not None and not should_continue():
            return {
                "rows": targets + remainder, "stop_reason": "user_stopped",
                "security_blocked": False, "not_attempted_count": total,
                **empty_counts,
            }

        page = self._session.context.new_page()
        merged_rows: list = []
        ssr_cache: dict = {}
        consecutive_failures = 0
        attempted_count = 0
        ssr_success_count = 0
        ui_fallback_used_count = 0
        ui_fallback_success_count = 0
        failure_count = 0
        stop_reason = None
        security_blocked = False
        not_attempted_in_targets = 0

        try:
            for row in targets:
                if stop_reason is None and should_continue is not None and not should_continue():
                    stop_reason = "user_stopped"
                if stop_reason is not None:
                    merged_rows.append(row)
                    not_attempted_in_targets += 1
                    continue

                place_id = str(row.get("place_id") or "").strip()
                if place_id and place_id in ssr_cache:
                    detail_result = ssr_cache[place_id]
                else:
                    detail_result = _fetch_place_detail_ssr(page, row, should_continue=should_continue)
                    if place_id:
                        ssr_cache[place_id] = detail_result
                if detail_result["detail_ssr_attempted"]:
                    attempted_count += 1

                status = detail_result["detail_ssr_status"]

                if status == "success":
                    merged_rows.append(merge_detail_into_row(row, detail_result))
                    ssr_success_count += 1
                    consecutive_failures = 0

                elif status == "blocked":
                    merged_rows.append(row)
                    stop_reason = detail_result["detail_ssr_stop_reason"]
                    security_blocked = True

                elif status == "mismatch":
                    merged_rows.append(row)
                    stop_reason = "place_id_mismatch"

                elif status == "user_stopped":
                    merged_rows.append(row)
                    if not detail_result["detail_ssr_attempted"]:
                        not_attempted_in_targets += 1
                    stop_reason = "user_stopped"

                elif status == "no_place_url":
                    merged_rows.append(row)
                    failure_count += 1

                else:  # needs_fallback
                    if should_continue is not None and not should_continue():
                        merged_rows.append(row)
                        not_attempted_in_targets += 1
                        stop_reason = "user_stopped"
                        continue

                    ui_fallback_used_count += 1
                    fallback_result = _fetch_place_detail(page, row, should_continue=should_continue)

                    if fallback_result["detail_success"]:
                        merged_rows.append(merge_detail_into_row(row, fallback_result))
                        ui_fallback_success_count += 1
                        consecutive_failures = 0
                    elif fallback_result["detail_stop_reason"] in ("captcha_detected", "detail_http_error"):
                        merged_rows.append(row)
                        stop_reason = fallback_result["detail_stop_reason"]
                        security_blocked = True
                    else:
                        merged_rows.append(row)
                        failure_count += 1
                        consecutive_failures += 1
                        if consecutive_failures >= _CONSECUTIVE_FAILURE_LIMIT:
                            stop_reason = "consecutive_failure_limit"

                if on_progress is not None:
                    try:
                        on_progress(len(merged_rows), total, ssr_success_count + ui_fallback_success_count, failure_count)
                    except Exception:
                        pass
        finally:
            try:
                page.close()
            except Exception:
                pass

        not_attempted_count = not_attempted_in_targets + len(remainder)
        return {
            "rows": merged_rows + remainder,
            "stop_reason": stop_reason,
            "security_blocked": security_blocked,
            "attempted_count": attempted_count,
            "ssr_success_count": ssr_success_count,
            "ui_fallback_used_count": ui_fallback_used_count,
            "ui_fallback_success_count": ui_fallback_success_count,
            "failure_count": failure_count,
            "not_attempted_count": not_attempted_count,
        }

    def __exit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            self._session_cm.__exit__(exc_type, exc, tb)
        self._session_cm = None
        self._session = None
        return False


# ============================================================================
# 신규 Apollo/GraphQL-first 두 모드 production 목록 수집 경로(사용자 승인 -
# "신규 Apollo/GraphQL-first 경로를 두 모드의 production 기본 목록 수집
# 방식으로 구현하세요"). DomMembershipCollector/collect_dom_membership_query
# (DOM 풀스크롤 기반, 위)는 이 추가로 전혀 수정되지 않았고, 기존
# DomMembershipCollector 및 DOM+Apollo+Network 병합 코드는 비활성 fallback
# capability로 그대로 보존된다 - 이 신규 경로는 그것을 호출하지 않으며, 실패
# 시에도 그쪽으로 조용히 전환하지 않고 navigation_error로 명확히 반환한다.
#
# 1페이지는 window.__APOLLO_STATE__의 ROOT_QUERY에서 현재 검색어와 정확히
# 일치하는 메인 placeList(...) operation 하나만 선택해 businesses.items의
# __ref만 추적한다(apollo_list_adapter.extract_main_place_list_from_apollo).
# 목록 전체 DOM 스크롤은 호출하지 않는다. 2페이지 이후는 정상 페이지 이동으로
# 자연 발생하는 GraphQL response만 사용하며, 기존 response listener 인프라
# (_make_response_handler 등)와 _find_page_button/_wait_for_next_page_settle을
# 재사용한다. collect_network_query의 기존 pagination 블록(DOM class-diff
# 페이지 정체성 검증 포함)은 이미 여러 실측으로 하드닝된 코드라 수정하지
# 않고, 이 함수는 그 블록을 복제하지 않은 더 단순한 새 루프로 작성했다 -
# DOM row를 전혀 읽지 않으므로 DOM class-diff 검증의 전제(DOM row 오귀속
# 방지)가 적용되지 않기 때문이다(Live 검증 후 추가 하드닝 필요 - 알려진 한계).
# ============================================================================

_APOLLO_FULL_STATE_JS = """() => {
    const state = window.__APOLLO_STATE__;
    if (!state || typeof state !== 'object') return {available: false, apollo_state: null, oversized: false};
    try {
        if (JSON.stringify(state).length > 5000000) {
            return {available: true, apollo_state: null, oversized: true};
        }
    } catch (e) {
        return {available: false, apollo_state: null, oversized: false};
    }
    return {available: true, apollo_state: state, oversized: false};
}"""


def _wait_for_apollo_list_ready(
    page, frame, expected_query: str, expected_start: int, hard_cap_ms: int = 5000,
    *, extractor=extract_main_place_list_from_apollo,
) -> dict:
    """1페이지 window.__APOLLO_STATE__에 메인 placeList(...) operation이 확인될
    때까지 폴링한다. 매 tick마다 전체 apollo state를 다시 읽어
    extractor(기본값 extract_main_place_list_from_apollo)로 판정하고,
    error가 없어지면 즉시 반환한다(추가 대기 없음). hard_cap_ms 안에 끝내
    확인되지 않으면 마지막 관찰된 list_result를 그대로 반환한다(호출자가
    error 필드로 판단 - 이 함수 자체는 성공/실패를 판정하지 않는다).

    NEW-OPENING-1: extractor=extract_new_opening_place_list_from_apollo를
    넘기면 새로오픈 전용 placeList(filterOpening=true) operation을 기다린다
    - 폴링 로직 자체는 어떤 operation을 찾는지와 무관하게 동일하다."""
    elapsed_ms = 0
    while True:
        try:
            state_result = frame.evaluate(_APOLLO_FULL_STATE_JS)
        except Exception:
            state_result = None
        apollo_state = state_result.get("apollo_state") if isinstance(state_result, dict) else None
        list_result = extractor(apollo_state, expected_query, expected_start)
        if not list_result["error"]:
            return list_result
        if elapsed_ms >= hard_cap_ms:
            return list_result
        page.wait_for_timeout(_POLL_INTERVAL_MS)
        elapsed_ms += _POLL_INTERVAL_MS


_REGION_REJECTION_REASON = {
    OUT_OF_SCOPE: "선택 법정동/시군구 범위를 벗어난 주소",
    REGION_UNVERIFIED: "주소로 공식 지역과의 일치를 확인할 수 없음(주소 공란 또는 인식되지 않은 시도 표기)",
}


def _split_region_valid_rows(rows: list, job: dict) -> tuple:
    """법정동이 선택된 Query(source_layer="legal_dong")에만 지역 Exact
    필터(naver_region_policy.classify_region_match)를 적용해 (유효 rows,
    거부 진단 목록)을 반환한다. 시군구 단위 검색(법정동 미선택)/보조
    역·상권·세부업종 Query는 비교할 특정 법정동이 없으므로 필터를 적용하지
    않고 그대로 통과시킨다(기존 동작 유지) - §4 요구사항이 "법정동 Query"로
    범위를 한정하고 있기 때문이다.

    이 필터는 per_query_limit 도달 판정보다 앞에서 호출돼야 한다(호출자가
    이 함수의 반환값 중 valid_rows만 unique_rows에 누적하고 카운트한다) -
    OUT_OF_SCOPE/REGION_UNVERIFIED row가 상한을 소비하면 안 된다는 요구사항을
    만족한다."""
    if job.get("source_layer") != "legal_dong" or not job.get("source_subregion"):
        return rows, []

    expected_sido = job.get("source_city") or ""
    expected_sigungu = job.get("source_district") or ""
    expected_dong = job.get("source_subregion") or ""

    valid_rows = []
    rejected = []
    for row in rows:
        address = row.get("주소") or row.get("roadAddress") or ""
        classification = classify_region_match(address, expected_sido, expected_sigungu, expected_dong)
        if classification in (OFFICIAL_EXACT, PROVIDER_ALIAS_EXACT):
            valid_rows.append(row)
        else:
            rejected.append({
                "source_query": row.get("source_query"),
                "업체명": row.get("업체명"),
                "place_id": row.get("place_id"),
                "판정_상태": classification,
                "거부_이유": _REGION_REJECTION_REASON.get(classification, classification),
                "주소": address,
                "기대_시도": expected_sido,
                "기대_시군구": expected_sigungu,
                "기대_법정동": expected_dong,
            })
    return valid_rows, rejected


_NEW_OPENING_REJECTION_REASON = "새로오픈 확인되지 않음(false/null/누락)"


def _split_new_opening_valid_rows(rows: list) -> tuple:
    """job["new_opening_only"]=True인 Query에서 newOpening이 명시적으로
    true인 row만 유효로 남긴다(§6) - false/null/필드 누락은 rejected_rows로
    분리해 per_query_limit을 소비하지 않게 한다. row의 "새로오픈여부"는
    이미 network_list_scraper._resolve_new_open_tristate가
    True->"O"/False->"X"/미확인->""로 매핑해둔 값이므로 "O"만 통과시킨다
    (추측으로 false/null을 새로오픈으로 저장하지 않는다)."""
    valid_rows = []
    rejected = []
    for row in rows:
        if row.get("새로오픈여부") == "O":
            valid_rows.append(row)
        else:
            rejected.append({
                "source_query": row.get("source_query"),
                "업체명": row.get("업체명"),
                "place_id": row.get("place_id"),
                "판정_상태": "NOT_NEW_OPENING",
                "거부_이유": _NEW_OPENING_REJECTION_REASON,
                "주소": row.get("주소"),
            })
    return valid_rows, rejected


def collect_apollo_first_list_query(page, job, target_count, *, collected_at, max_pages: int = 5) -> dict:
    """신규 Apollo/GraphQL-first 목록 수집. 1페이지는 메인 placeList(...)
    operation만 파싱하고(DOM 스크롤 없음), 2페이지 이후는 자연 발생 GraphQL
    response를 harvest한다. run_collection_plan이 기대하는 최소 계약
    {"rows", "active_captcha_detected", "status_429_seen", "navigation_error",
    "navigation_error_message"}을 그대로 만족해 network_pipeline.py는 무수정
    으로 재사용된다.

    실패 시맨틱: 1페이지 Apollo 구조 파싱 실패(search frame 없음/apollo_state
    없음/메인 placeList 없음·모호함/businesses.items 없음)만
    navigation_error=True로 취급한다(run_collection_plan이 이미 "즉시 큐
    전체 중단, 이전 결과 보존"으로 처리하는 필드 - 조용한 DOM fallback
    없음). 페이지네이션 소진/다음 페이지 버튼 없음/max_pages 도달은 정상
    종료(navigation_error=False)로 처리한다.

    반환에 추가된 진단 필드(navigation_error 계약 외): "page_count"(확정된
    페이지 수), "pagination_stop_reason"(정상 종료 사유).

    NEW-OPENING-1: job["new_opening_only"]=True면 메인 placeList 대신
    filterOpening=true 전용 placeList(extract_new_opening_place_list_from_apollo)
    를 찾는다. 2026-07-30 Live 실측상 이 operation은 page 1에 이미 존재하며
    "다음 페이지" 개념이 없는 고정 소규모 미리보기이므로(§4 실측 근거,
    scratchpad/new_opening_filter_implementation), 페이지네이션 루프를
    시도하지 않고 1페이지 결과만으로 즉시 종료한다 - 새로오픈 업체가
    목표보다 적어도 오류가 아니라 정상 종료다(§7)."""
    new_opening_only = bool(job.get("new_opening_only"))
    list_extractor = extract_new_opening_place_list_from_apollo if new_opening_only else extract_main_place_list_from_apollo
    error_prefix = "NewOpeningListParseError" if new_opening_only else "ApolloListParseError"

    ctx = _QueryObservationContext()
    response_handler = _make_response_handler(ctx)
    request_finished_handler = _make_request_finished_handler(ctx)
    request_failed_handler = _make_request_failed_handler(ctx)
    _registered_listeners: list = []
    try:
        for _event, _handler in (
            ("response", response_handler),
            ("requestfinished", request_finished_handler),
            ("requestfailed", request_failed_handler),
        ):
            page.on(_event, _handler)
            _registered_listeners.append((_event, _handler))
    except Exception:
        for _event, _handler in _registered_listeners:
            try:
                page.off(_event, _handler)
            except Exception:
                pass
        raise

    def _navigation_error_result(message: str) -> dict:
        return {
            "rows": [],
            "active_captcha_detected": False,
            "status_429_seen": ctx.status_429_seen,
            "navigation_error": True,
            "navigation_error_message": message,
            "page_count": 0,
            "pagination_stop_reason": None,
            "rejected_rows": [],
        }

    try:
        query_text = job.get("query") or ""
        search_url = _SEARCH_URL_TEMPLATE.format(query=quote(query_text))
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
        except PlaywrightTimeoutError:
            pass  # BrowserSession.goto와 동일: 느린 로드는 관용적으로 흡수하고 계속 진행.
        except Exception as exc:
            return _navigation_error_result(f"{type(exc).__name__}: {exc}")

        frame = _find_search_frame(page)
        if frame is None:
            return _navigation_error_result("ApolloListParseError:search_frame_not_found")

        list_result = _wait_for_apollo_list_ready(page, frame, query_text, 0, hard_cap_ms=5000, extractor=list_extractor)
        if list_result["error"]:
            return _navigation_error_result(f"{error_prefix}:{list_result['error']}")

        mapped_rows = build_rows_from_apollo_list_result(list_result, collected_at, source_query=query_text)
        for row in mapped_rows:
            row["source_page"] = 1
            row["source_city"] = job.get("source_city")
            row["source_district"] = job.get("source_district")
            row["source_subregion"] = job.get("source_subregion")
            row["source_layer"] = job.get("source_layer")

        local_seen: set = set()
        unique_rows = dedup_rows(mapped_rows, local_seen)
        unique_rows, rejected_rows = _split_region_valid_rows(unique_rows, job)
        if new_opening_only:
            unique_rows, new_opening_rejected = _split_new_opening_valid_rows(unique_rows)
            rejected_rows = rejected_rows + new_opening_rejected

        def _ensure_parsed_simple(index: int) -> dict:
            """collect_network_query의 _ensure_parsed와 달리 candidate당 재확인
            memoize를 하지 않는 단순화된 버전 - 신규 경로는 DOM class-diff 등
            추가 하드닝이 없어 candidate 수 자체가 훨씬 적으므로 매 호출마다
            다시 파싱해도 비용이 낮다(§3 - 새 pagination 루프는 의도적으로
            더 단순하게 작성)."""
            entry = ctx.candidates[index]
            if entry["body_snapshot_ready"]:
                if entry.get("candidate_error_type") == "CandidateHttpError":
                    return {"items": [], "error": True}
                try:
                    data = json.loads(entry["body_snapshot"])
                    return {"items": _extract_list_items(data), "error": False}
                except Exception:
                    return {"items": [], "error": True}
            if entry["body_snapshot_error_type"]:
                return {"items": [], "error": True}
            return {"items": [], "error": False, "pending": True}

        pagination_stop_reason = None
        current_page_number = 1
        final_captcha_signal = None

        if new_opening_only:
            # §4 Live 실측: 새로오픈 전용 operation은 page 1의 고정 소규모
            # 미리보기이며 "다음 페이지"가 없다 - 목표 미달이어도 페이지네이션을
            # 시도하지 않고 확보된 만큼으로 정상 종료한다(§7 - 오류/무한 이동
            # 아님).
            pagination_stop_reason = "new_opening_single_page_exhausted"
        elif target_count and len(unique_rows) >= target_count:
            pagination_stop_reason = "per_query_limit_reached"
        else:
            while current_page_number < max_pages:
                probe = _probe_captcha_state(page)
                final_captcha_signal = classify_captcha_signal(
                    marker_present_in_dom=probe["marker_present"],
                    element_visible=probe["visible"],
                    bounding_box_area=probe["bounding_box_area"],
                    click_exception_message=probe["click_intercepted_message"],
                )
                if final_captcha_signal["active_captcha_detected"]:
                    pagination_stop_reason = "captcha_detected"
                    break
                if ctx.status_429_seen:
                    pagination_stop_reason = "status_429_seen"
                    break

                frame = _find_search_frame(page)
                if frame is None:
                    pagination_stop_reason = "pagination_exhausted"
                    break

                target_page_number = current_page_number + 1
                button_locator = _find_page_button(frame, target_page_number)
                try:
                    button_count = button_locator.count() if button_locator is not None else 0
                except Exception:
                    button_count = 0
                if button_count == 0:
                    pagination_stop_reason = "pagination_exhausted"
                    break
                if button_count > 1:
                    pagination_stop_reason = "ambiguous_page_button"
                    break

                target_locator = button_locator.first
                try:
                    is_ready = bool(target_locator.is_visible()) and bool(target_locator.is_enabled())
                except Exception:
                    pagination_stop_reason = "pagination_click_error"
                    break
                if not is_ready:
                    pagination_stop_reason = "pagination_click_error"
                    break

                count_before_click = ctx.candidate_response_count
                try:
                    target_locator.click()
                except Exception:
                    pagination_stop_reason = "pagination_click_error"
                    break

                wait_result = _wait_for_next_page_settle(
                    page, ctx, _ensure_parsed_simple, count_before_click, hard_cap_ms=5000
                )

                probe = _probe_captcha_state(page)
                final_captcha_signal = classify_captcha_signal(
                    marker_present_in_dom=probe["marker_present"],
                    element_visible=probe["visible"],
                    bounding_box_area=probe["bounding_box_area"],
                    click_exception_message=probe["click_intercepted_message"],
                )
                if final_captcha_signal["active_captcha_detected"]:
                    pagination_stop_reason = "captcha_detected"
                    break
                if ctx.status_429_seen:
                    pagination_stop_reason = "status_429_seen"
                    break
                if not wait_result["got_new_response"]:
                    pagination_stop_reason = "next_page_response_timeout"
                    break

                page_raw_items: list = []
                for index in range(count_before_click, wait_result["final_count"]):
                    parsed = _ensure_parsed_simple(index)
                    if not parsed["error"]:
                        page_raw_items.extend(parsed["items"])

                page_mapped_rows = []
                for item in page_raw_items:
                    row = _map_item_to_row(
                        item, collected_at, source_page=target_page_number, source_query=query_text
                    )
                    row["source_city"] = job.get("source_city")
                    row["source_district"] = job.get("source_district")
                    row["source_subregion"] = job.get("source_subregion")
                    row["source_layer"] = job.get("source_layer")
                    page_mapped_rows.append(row)

                newly_unique = dedup_rows(page_mapped_rows, local_seen)
                newly_valid, newly_rejected = _split_region_valid_rows(newly_unique, job)
                unique_rows.extend(newly_valid)
                rejected_rows.extend(newly_rejected)
                current_page_number = target_page_number

                if target_count and len(unique_rows) >= target_count:
                    pagination_stop_reason = "per_query_limit_reached"
                    break
                if current_page_number >= max_pages:
                    pagination_stop_reason = "max_page_count_reached"
                    break

            if pagination_stop_reason is None:
                pagination_stop_reason = "max_page_count_reached"

        if final_captcha_signal is None:
            probe = _probe_captcha_state(page)
            final_captcha_signal = classify_captcha_signal(
                marker_present_in_dom=probe["marker_present"],
                element_visible=probe["visible"],
                bounding_box_area=probe["bounding_box_area"],
                click_exception_message=probe["click_intercepted_message"],
            )

        capped_rows = unique_rows[:target_count] if target_count else unique_rows
        return {
            "rows": capped_rows,
            "active_captcha_detected": bool(final_captcha_signal["active_captcha_detected"]),
            "status_429_seen": ctx.status_429_seen,
            "navigation_error": False,
            "navigation_error_message": "",
            "page_count": current_page_number,
            "pagination_stop_reason": pagination_stop_reason,
            "rejected_rows": rejected_rows,
        }
    finally:
        for event, event_handler in (
            ("response", response_handler),
            ("requestfinished", request_finished_handler),
            ("requestfailed", request_failed_handler),
        ):
            try:
                page.off(event, event_handler)
            except Exception:
                pass


class ApolloFirstListCollector:
    """신규 Apollo/GraphQL-first 목록 수집의 production 기본 collector.

    `NetworkBrowserCollector`/`DomMembershipCollector`와 동일한 생명주기
    계약(컨텍스트 매니저 + `collect_query(job, per_query_limit)`)을 만족해
    `run_collection_plan`은 무수정으로 재사용된다. `enrich_detail`/
    `enrich_detail_ssr`은 의도적으로 정의하지 않는다 - 홈페이지·SNS 포함
    모드의 home 보강은 이 클래스가 아니라 `src/pc/home_enrichment.py`가,
    이 컨텍스트가 닫힌(브라우저 세션이 종료된) 뒤 별도로 담당한다.
    """

    def __init__(self, *, collected_at, session_factory=None, max_pages: int = 5):
        self.collected_at = collected_at
        self.max_pages = max_pages
        self._session_factory = session_factory or _default_session_factory
        self._session_cm = None
        self._session = None

    def __enter__(self):
        self._session_cm = self._session_factory()
        self._session = self._session_cm.__enter__()
        self._close_initial_page_if_present()
        return self

    def _close_initial_page_if_present(self) -> None:
        initial_page = getattr(self._session, "page", None)
        if initial_page is None:
            return
        try:
            initial_page.close()
        except Exception:
            pass

    def collect_query(self, job, per_query_limit) -> dict:
        page = self._session.context.new_page()
        try:
            return collect_apollo_first_list_query(
                page,
                job,
                per_query_limit,
                collected_at=self.collected_at,
                max_pages=self.max_pages,
            )
        finally:
            try:
                page.close()
            except Exception:
                pass

    def capture_session_cookies(self) -> list:
        """`with` 블록이 열려있는 동안(context가 닫히기 전) 호출해야 한다 -
        홈페이지·SNS 포함 모드에서 sync Playwright 세션 종료 후 별도 async
        home enrichment 단계로 쿠키를 이어주기 위한 것이다(Playwright 객체
        자체는 넘기지 않고 순수 JSON 직렬화 가능한 list[dict]만 넘긴다 - 두
        단계 사이에 Playwright 객체의 thread/event loop 공유가 없다).
        best-effort이며 어떤 예외도 밖으로 던지지 않고 빈 list를 반환한다."""
        try:
            return self._session.context.cookies()
        except Exception:
            return []

    def __exit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            self._session_cm.__exit__(exc_type, exc, tb)
        self._session_cm = None
        self._session = None
        return False
