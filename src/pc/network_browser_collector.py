# 목록 수집 엔진(ApolloFirstListCollector/collect_apollo_first_list_query,
# 파일 하단)이 쓰는 Network 응답 관찰 인프라(_QueryObservationContext와
# response/requestfinished/requestfailed 핸들러, candidate 안전 진단,
# CAPTCHA probe, 페이지네이션 대기)를 담는다. is_candidate_response/
# _extract_list_items/_map_item_to_row/dedup_rows/classify_captcha_signal은
# src/pc/network_list_scraper.py에서 읽기 전용으로 재사용하며 재구현하지
# 않는다.
#
# page.goto()에서 발생 가능한 예외는 성격이 다르다. 실제 Playwright
# TimeoutError(느린 로드)만 timeout=True로 분류하고, "page/context/browser가
# 이미 닫힘(Target closed)"·"브라우저 실행 장애"·"일반 navigation 오류" 등
# 그 외 예외는 timeout으로 위장하지 않고 navigation_error로 별도 분류한다
# (browser_session.goto와 동일하게 PlaywrightTimeoutError만 관용적으로 흡수).
import json
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pc.apollo_list_adapter import (
    build_rows_from_apollo_list_result,
    extract_main_place_list_from_apollo,
    extract_new_opening_place_list_from_apollo,
)
from src.pc.browser_session import _CAPTCHA_PROBE_SELECTORS
from src.region.naver_region_policy import (
    OFFICIAL_EXACT,
    OUT_OF_SCOPE,
    PROVIDER_ALIAS_EXACT,
    REGION_UNVERIFIED,
    classify_region_match,
)
from src.pc.network_list_scraper import (
    _extract_list_items,
    _map_item_to_row,
    classify_captcha_signal,
    dedup_rows,
    is_candidate_response,
)
from src.pc.run_control import wait_while_paused

_SEARCH_URL_TEMPLATE = "https://map.naver.com/v5/search/{query}"

# ARCH-300C PERF-1A: 적응형 settle 종료 상수(모듈 상수로만 고정 - 함수
# 시그니처나 UI에는 노출하지 않는다). settle_ms(기존
# 파라미터, 기본 5000)는 "무조건 기다리는 시간"에서 "최대 대기 hard cap"으로
# 의미가 바뀌었고, 파싱 가능한(비어있지 않은) 업체 목록 응답을 확인한 뒤
# _QUIET_PERIOD_MS 동안 추가 후보가 도착하지 않으면 hard cap 전에 조기
# 종료한다. 750/100이라는 구체적인 값은 WIRE-4C(실제 네이버, 300건 규모)
# 관찰에서 얻은 잠정치이며, candidate 응답들 사이의 실제 도착 간격(inter-arrival
# gap)을 직접 계측한 적은 아직 없다 - 다음 live 검증 단계(WIRE-5 등)에서
# 이 값의 적정성을 실측으로 재확인해야 한다(반대 검토 AI 지적 사항).
_QUIET_PERIOD_MS = 750
_POLL_INTERVAL_MS = 100

# PAGE-300-2B-2B: candidate response body의 안전 상한(바이트). PAGE-300-2B-2A
# 실측(page 2 candidate 응답 약 414KB)보다 넉넉한 여유를 두되, 메모리 폭주를
# 막기 위한 상한이다 - 초과하면 body 자체는 저장하지 않고 에러로만 기록한다.
_MAX_CANDIDATE_BODY_BYTES = 2 * 1024 * 1024


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


class _QueryObservationContext:
    """쿼리 1회 호출에 국한된 로컬 상태(전역/클래스 공용 상태를 두지 않기 위함).

    handler는 이 인스턴스에만 기록하며, 쿼리 1건 처리가 끝나면
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
    이 모듈 전용으로 재구현한다 - 이 함수는 BrowserSession
    인스턴스가 아니라 bare page만 받으므로 그 메서드를 직접 호출할 수 없다
    (browser_session.py는 이번 단계 수정 금지 범위).

    이 함수는 어떤 예외도 밖으로 내보내지 않는다 - frame API를 전혀 구현하지
    않은 기존 FakePage(단일 페이지 no-live 테스트 전용)에서도 안전하게 None을
    반환해야, per_query_limit이 첫 페이지 결과보다 큰 기존 테스트들이 실수로
    pagination을 "시도"하더라도 예외 없이 즉시 pagination_exhausted로 안전
    종료되어 기존 단일 페이지 반환값이 전혀 달라지지 않는다.
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
    수집이 안정화될 때까지 추가로 기다린다(최초 settle 폴링 루프와 동일한
    로직을 count_before_click부터 시작하도록 일반화한 것).

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


_DETAIL_HTTP_BLOCKING_STATUSES = (403, 405, 429)


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


_REVIEW_BELOW_MIN_REASON = "총리뷰수가 최소값 미만"
_REVIEW_ABOVE_MAX_REASON = "총리뷰수가 최대값 초과"
_REVIEW_UNKNOWN_REASON = "총리뷰수를 확인할 수 없음(빈 값/파싱 불가)"


def _parse_review_count(value) -> int | None:
    """row["총리뷰수"](정수 또는 숫자 문자열)를 int로 변환한다. 비어있거나
    숫자로 해석할 수 없으면 None(REVIEW_UNKNOWN 처리 대상)을 반환한다."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_review_valid_rows(rows: list, review_min: int | None, review_max: int | None) -> tuple:
    """review_min/review_max(둘 중 하나라도 설정된 경우에만 호출) 기준으로
    row["총리뷰수"]가 범위 안인 row만 유효로 남긴다(§4 - 총리뷰수를 기준
    필드로 사용하기로 확정, scratchpad/network_controls_fix/review_filter_contract_audit.md).
    _split_region_valid_rows/_split_new_opening_valid_rows와 동일하게
    per_query_limit 판정보다 먼저 호출돼야 한다 - 제외된 row가 상한을
    소비하지 않게 하기 위함이다. 총리뷰수가 비어있거나 파싱 불가하면
    범위를 판정할 수 없으므로 REVIEW_UNKNOWN으로 분류해 제외한다(레거시의
    "빈 값=0으로 취급" 대신, 실제로 확인 불가능하다는 사실을 진단에 남긴다)."""
    valid_rows = []
    rejected = []
    for row in rows:
        review_count = _parse_review_count(row.get("총리뷰수"))
        if review_count is None:
            status, reason = "REVIEW_UNKNOWN", _REVIEW_UNKNOWN_REASON
        elif review_min is not None and review_count < review_min:
            status, reason = "REVIEW_BELOW_MIN", _REVIEW_BELOW_MIN_REASON
        elif review_max is not None and review_count > review_max:
            status, reason = "REVIEW_ABOVE_MAX", _REVIEW_ABOVE_MAX_REASON
        else:
            status, reason = None, None
        if status is None:
            valid_rows.append(row)
        else:
            rejected.append({
                "source_query": row.get("source_query"),
                "업체명": row.get("업체명"),
                "place_id": row.get("place_id"),
                "판정_상태": status,
                "거부_이유": reason,
                "주소": row.get("주소"),
            })
    return valid_rows, rejected


def _review_filter_stats(candidate_count: int, rejected: list) -> dict:
    """_split_review_valid_rows의 rejected 목록에서 §8 진단 카운터를 만든다."""
    return {
        "candidate": candidate_count,
        "accepted": candidate_count - len(rejected),
        "rejected_by_min": sum(1 for r in rejected if r["판정_상태"] == "REVIEW_BELOW_MIN"),
        "rejected_by_max": sum(1 for r in rejected if r["판정_상태"] == "REVIEW_ABOVE_MAX"),
        "unknown": sum(1 for r in rejected if r["판정_상태"] == "REVIEW_UNKNOWN"),
    }


def _merge_review_filter_stats(a: dict, b: dict) -> dict:
    return {key: a.get(key, 0) + b.get(key, 0) for key in ("candidate", "accepted", "rejected_by_min", "rejected_by_max", "unknown")}


def _default_session_factory():
    """실제 제품 배선용 기본 factory - 이 함수가 호출되어 반환된 객체의
    __enter__가 실제로 호출될 때만 Playwright/브라우저가 시작된다(이 함수를
    정의/참조하는 것만으로는 아무것도 시작하지 않는다). 테스트는 항상
    session_factory를 fake로 주입하므로 이 함수는 테스트에서 호출되지 않는다.

    BrowserBackendConfig.from_env().backend에 따라 NativeCdpBrowserSession
    (기본값, production)과 BrowserSession(launch, 명시적 backend="launch"
    선택 시만 사용하는 개발·테스트 fallback) 중 하나를 반환한다.
    DiagnosticConfig는 safe_default()를 사용한다(브라우저 backend 선택과
    진단 플래그는 독립된 설정 축).
    """
    from src.pc.browser_session import BrowserSession, NativeCdpBrowserSession
    from src.pc.config import BrowserBackendConfig, DiagnosticConfig

    diagnostic_config = DiagnosticConfig.safe_default()
    backend_config = BrowserBackendConfig.from_env()

    if backend_config.backend == "launch":
        return BrowserSession(diagnostic_config)
    return NativeCdpBrowserSession(diagnostic_config, backend_config)


def collect_apollo_first_list_query(
    page, job, target_count, *, collected_at, max_pages: int = 5, pause_event=None, stop_event=None
) -> dict:
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
            "review_filter_stats": None,
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

        review_min = job.get("review_min")
        review_max = job.get("review_max")
        review_filter_enabled = review_min is not None or review_max is not None
        review_filter_stats = {"candidate": 0, "accepted": 0, "rejected_by_min": 0, "rejected_by_max": 0, "unknown": 0}

        local_seen: set = set()
        unique_rows = dedup_rows(mapped_rows, local_seen)
        unique_rows, rejected_rows = _split_region_valid_rows(unique_rows, job)
        if new_opening_only:
            unique_rows, new_opening_rejected = _split_new_opening_valid_rows(unique_rows)
            rejected_rows = rejected_rows + new_opening_rejected
        if review_filter_enabled:
            candidate_count = len(unique_rows)
            unique_rows, review_rejected = _split_review_valid_rows(unique_rows, review_min, review_max)
            rejected_rows = rejected_rows + review_rejected
            review_filter_stats = _merge_review_filter_stats(
                review_filter_stats, _review_filter_stats(candidate_count, review_rejected)
            )

        def _ensure_parsed_simple(index: int) -> dict:
            """candidate당 재확인 memoize를 하지 않는 단순화된 버전 - 이
            경로는 DOM class-diff 등 추가 하드닝이 없어 candidate 수 자체가
            훨씬 적으므로 매 호출마다
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
                # 다음 페이지 이동 전(§5 요청서) - 일시정지 중이면 여기서
                # 대기하고, 대기 중 또는 대기 후 중지가 감지되면 새 페이지로
                # 넘어가지 않고 지금까지 확보한 rows를 보존한 채 정상 종료한다.
                wait_while_paused(pause_event, stop_event)
                if stop_event is not None and stop_event.is_set():
                    pagination_stop_reason = "user_stopped"
                    break

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
                if review_filter_enabled:
                    candidate_count = len(newly_valid)
                    newly_valid, newly_review_rejected = _split_review_valid_rows(newly_valid, review_min, review_max)
                    newly_rejected = newly_rejected + newly_review_rejected
                    review_filter_stats = _merge_review_filter_stats(
                        review_filter_stats, _review_filter_stats(candidate_count, newly_review_rejected)
                    )
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
            "review_filter_stats": review_filter_stats if review_filter_enabled else None,
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
    """Apollo/GraphQL-first 목록 수집의 production 기본 collector.

    컨텍스트 매니저 + `collect_query(job, per_query_limit)` 생명주기 계약을
    만족해 `run_collection_plan`이 그대로 재사용한다. `enrich_detail`/
    `enrich_detail_ssr`은 의도적으로 정의하지 않는다 - 홈페이지·SNS 포함
    모드의 home 보강은 이 클래스가 아니라 `src/pc/home_enrichment.py`가,
    이 컨텍스트가 닫힌(브라우저 세션이 종료된) 뒤 별도로 담당한다.
    """

    def __init__(self, *, collected_at, session_factory=None, max_pages: int = 5, pause_event=None, stop_event=None):
        self.collected_at = collected_at
        self.max_pages = max_pages
        self.pause_event = pause_event
        self.stop_event = stop_event
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
                pause_event=self.pause_event,
                stop_event=self.stop_event,
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
