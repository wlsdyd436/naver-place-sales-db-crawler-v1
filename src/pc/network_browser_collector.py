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
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.pc.browser_session import _CAPTCHA_PROBE_SELECTORS
from src.pc.network_list_scraper import (
    _extract_list_items,
    _map_item_to_row,
    classify_captcha_signal,
    dedup_rows,
    is_candidate_response,
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


class _QueryObservationContext:
    """쿼리 1회 호출에 국한된 로컬 상태(전역/클래스 공용 상태를 두지 않기 위함).

    handler는 이 인스턴스에만 기록하며, collect_network_query 호출이 끝나면
    함께 버려진다 - 다음 쿼리는 항상 새 인스턴스로 시작하므로 이전 쿼리의
    응답과 섞이지 않는다(페이지 자체도 WIRE-2B부터는 쿼리마다 새로 생성/종료될
    예정이라 이중으로 격리된다).
    """

    def __init__(self):
        self.candidate_responses: list = []
        self.candidate_response_count = 0
        self.status_429_seen = False
        # PAGE-300-2B-1-FIX §3: 같은 response 객체가 브라우저에서 'response'
        # 이벤트를 중복 발생시키는 극단적인 경우에도 object identity(id())로
        # 한 번만 기록한다 - 인덱스가 아니라 객체 자체를 키로 써야, 동일 객체가
        # 두 번 append돼 서로 다른 인덱스로 두 번 harvest(JSON parse 2회)되는
        # 것을 막을 수 있다. response 객체는 candidate_responses에 계속
        # 참조로 남아있으므로(쿼리 종료 전까지) id() 재사용(GC) 위험이 없다.
        self.seen_response_ids: set = set()


def _make_response_handler(ctx: _QueryObservationContext):
    """response handler는 최소 작업만 한다(상태 확인 + 후보 저장) - json 파싱은
    settle 종료 후 별도로 수행해 callback 블로킹을 피하고 parse_error_count를
    명확히 집계한다."""

    def handle_response(response) -> None:
        try:
            if response.status == 429:
                ctx.status_429_seen = True
        except Exception:
            pass

        try:
            resource_type = response.request.resource_type
        except Exception:
            resource_type = ""
        url = response.url or ""

        try:
            if is_candidate_response(url, resource_type):
                response_id = id(response)
                if response_id not in ctx.seen_response_ids:
                    ctx.seen_response_ids.add(response_id)
                    ctx.candidate_response_count += 1
                    ctx.candidate_responses.append(response)
        except Exception:
            pass

    return handle_response


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
    handler = _make_response_handler(ctx)
    page.on("response", handler)

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
            }

        # PERF-1A 적응형 settle: parsed_cache는 candidate 응답 하나당
        # response.json()/_extract_list_items()를 정확히 1회만 호출하도록
        # 메모이즈한다(폴링 루프의 "peek" 확인과 아래 harvest 단계가 결과를
        # 공유 - 중복 파싱/중복 parse_error 집계를 방지).
        parsed_cache: dict = {}

        def _ensure_parsed(index: int) -> dict:
            if index not in parsed_cache:
                response = ctx.candidate_responses[index]
                try:
                    data = response.json()
                    items = _extract_list_items(data)
                    parsed_cache[index] = {"items": items, "error": False}
                except Exception:
                    parsed_cache[index] = {"items": [], "error": True}
            return parsed_cache[index]

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
        for index in range(len(ctx.candidate_responses)):
            parsed = _ensure_parsed(index)
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
            drain_result = _drain_pending_responses(page, ctx, _ensure_parsed, from_index)
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
                parse_error_count += drain_result["parse_error_count"]
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
                try:
                    harvested_up_to_index = _apply_pending_drain(harvested_up_to_index)
                except Exception as exc:
                    pagination_stop_reason = "pagination_click_error"
                    pagination_error_message = f"{type(exc).__name__}: {exc}"
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
                    try:
                        harvested_up_to_index = _apply_pending_drain(candidate_count_before_click)
                    except Exception as exc:
                        pagination_stop_reason = "pagination_click_error"
                        pagination_error_message = f"{type(exc).__name__}: {exc}"
                        break
                    candidate_count_before_click = harvested_up_to_index
                    if per_query_limit and len(unique_rows) >= per_query_limit:
                        pagination_stop_reason = "per_query_limit_reached"
                        break
                    class_before = _safe_get_attribute(target_locator, "class")

                try:
                    target_locator.scroll_into_view_if_needed()
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
                    parsed = _ensure_parsed(index)
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
        }
    finally:
        try:
            page.off("response", handler)
        except Exception:
            pass


def _default_session_factory():
    """실제 제품 배선용 기본 factory - BrowserSession을 참고하되, 이 함수가
    호출되어 반환된 객체의 __enter__가 실제로 호출될 때만 Playwright가
    시작된다(이 함수를 정의/참조하는 것만으로는 아무것도 시작하지 않는다).
    테스트는 항상 session_factory를 fake로 주입하므로 이 함수는 테스트에서
    호출되지 않는다.
    """
    from src.pc.browser_session import BrowserSession
    from src.pc.config import DiagnosticConfig

    return BrowserSession(DiagnosticConfig.safe_default())


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
