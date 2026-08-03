# 홈페이지·SNS 포함 모드 전용 - 목록 수집(ApolloFirstListCollector, sync
# Playwright + Native Edge CDP persistent profile)이 이미 끝나고 그
# browser/context/page가 완전히 정리된(owned process 종료 + profile lock
# 해제) 뒤에만 호출되는 독립 단계다. place_id당 최대 1회 home HTML GET을
# 동시성 2로 수행해 홈페이지/인스타/블로그(+ 목록에서 공란인 대표전화만)를
# 보강한다.
#
# 2026-07-24 PAGE300-6A-FIX1(request provenance 보정): 이전 구현은
# playwright.request.new_context(storage_state=cookies)로 만든, 실제
# 브라우저와 무관한 별도 APIRequestContext에 쿠키 "값"만 복사해 쓰는
# 방식이었다 - 이는 scratchpad/page300_5z_ssr_scheduling_final_benchmark가
# 검증한 방식과 다르다(5Z는 Native Edge CDP persistent profile에
# connect_over_cdp로 연결한 실제 BrowserContext의 `context.request`를
# 사용했다 - test_async_native_cdp.py 참고). 이번 수정은 이 모듈도 동일하게
# "같은 persistent profile을 가리키는 Native Edge/Chrome을 다시 연결해 실제
# BrowserContext.request를 사용"하도록 바꾼다. 쿠키 "값"은 이 모듈 어디에도
# 저장/복사하지 않는다 - 세션 연속성은 브라우저가 그 persistent profile
# 디렉터리에 이미 기록해 둔 실제 쿠키 저장소에서 자연스럽게 나온다(이것이
# NativeCdpBrowserSession이 애초에 "persistent profile"을 쓰는 이유와 동일한
# 메커니즘 - 앱을 재시작해도 세션이 유지되는 것과 같은 원리다).
#
# 목록 수집 세션과 이 단계는 동시에 실행되지 않는다(순차 - ui.py의 `with`
# 블록이 완전히 닫힌 뒤에만 호출됨) - profile lock이 이를 물리적으로
# 보장하므로, 이 모듈이 같은 profile_dir로 새 프로세스를 시작해도 두 프로세스가
# 동시에 같은 profile을 쓰는 충돌은 발생하지 않는다.
import asyncio
import math
import re
import subprocess
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightAsyncTimeoutError
from playwright.async_api import async_playwright

from src.browser.session import (
    _acquire_profile_lock,
    _build_native_browser_args,
    _pick_free_port,
    _release_profile_lock,
    _resolve_browser,
    _terminate_owned_process,
    _wait_for_cdp_ready,
)
from src.browser.config import BrowserBackendConfig
from src.collection.apollo_html_parser import (
    _classify_ssr_block_signal,
    _parse_apollo_state_from_html,
)
from src.collection.apollo_detail_adapter import extract_normalized_apollo_detail
from src.collection.place_mapper import (
    _is_personal_mobile_phone,
    _map_item_to_row,
    build_place_url_from_id,
)
from src.run_control import wait_while_paused_async

_SSR_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://m.place.naver.com/",
}
_SSR_REQUEST_TIMEOUT_MS = 15000

_HOME_ENRICHMENT_CONCURRENCY = 2
_HOME_RETRY_CONCURRENCY = 1
_HOME_RETRY_STABILIZATION_SECONDS = 3
_HOME_MAX_FAILURE_RATIO_FOR_RETRY = 0.1

# PAGE300-6G-R1(홈페이지 보강 진단/재시도): 일시적(transient) 실패로 간주해
# 재시도하는 상태 집합 - HTTP 403/405/429/CAPTCHA/place_id_mismatch/
# no_place_url/user_stopped는 여기 없으므로 재시도되지 않는다(요청서 §7).
_HOME_RETRYABLE_STATUSES = frozenset(
    {
        "timeout",
        "request_error",
        "http_5xx",
        "empty_html",
        "apollo_missing",
        "base_missing",
        "parent_missing",
        "adapter_empty",
    }
)


# PAGE300-6G-R2(진단 스키마 보강): place_id=1398764421 실패 감사 - unexpected_error가
# 발생하면 _run_one이 _fetch_place_home_async의 부분 진행 상태를 전부 버리고
# 새 dict로 교체하므로(§ 아래 _error_result), 기존 필드만으로는 어느 단계에서
# 무엇이 실패했는지 알 수 없었다. status(기존 값)별 안정적인 stage/retry_reason
# 라벨 - deterministic 실패는 "no_retry"/"deterministic_" 접두어로 retryable=False와
# 모순되지 않게, transient 실패는 _HOME_RETRYABLE_STATUSES와 일치하게 둔다.
_ERROR_STAGE_BY_STATUS = {
    "no_place_url": "input_validation",
    "timeout": "detail_request",
    "request_error": "detail_request",
    "http_5xx": "detail_request",
    "http_4xx": "detail_request",
    "captcha_detected": "detail_request",
    "security_blocked": "detail_request",
    "empty_html": "response_parse",
    "apollo_missing": "response_parse",
    "base_missing": "response_parse",
    "place_id_mismatch": "response_parse",
    "adapter_empty": "apollo_adapter",
    "parent_missing": "apollo_adapter",
}
_RETRY_REASON_BY_STATUS = {
    "timeout": "request_timeout",
    "request_error": "transient_request_error",
    "http_5xx": "transient_http_5xx",
    "empty_html": "transient_empty_html",
    "apollo_missing": "transient_apollo_missing",
    "base_missing": "transient_base_missing",
    "parent_missing": "transient_parent_missing",
    "adapter_empty": "transient_adapter_empty",
    "captcha_detected": "security_block",
    "security_blocked": "security_block",
    "place_id_mismatch": "deterministic_place_id_mismatch",
    "http_4xx": "deterministic_http_4xx",
    "no_place_url": "deterministic_no_place_url",
    "unexpected_error": "no_retry_unexpected_error",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ERROR_MESSAGE_MAX_LEN = 300
_SENSITIVE_MESSAGE_PATTERN = re.compile(r"(?i)\b(cookie|authorization|bearer)\S*")


def _sanitize_error_message(message: str) -> str:
    """예외 메시지를 진단 JSON에 남기기 전 정리한다 - 줄바꿈 제거, 쿠키/
    Authorization/Bearer류 토큰 마스킹, 메시지에 URL이 섞여 있을 경우를 대비해
    쿼리스트링·fragment 제거, 최대 300자로 절단(요청서 §12)."""
    text = re.sub(r"[\r\n]+", " ", message or "").strip()
    text = _SENSITIVE_MESSAGE_PATTERN.sub("[REDACTED]", text)
    text = re.sub(r"[?#]\S*", "", text)
    return text[:_ERROR_MESSAGE_MAX_LEN]


def _project_error_frame(exc: BaseException) -> tuple:
    """예외 traceback에서 프로젝트 내부 마지막 frame만 사용해 (location, stage)를
    만든다(요청서 §12) - location은 "path:func:line"(절대경로/사용자명/TEMP
    경로 없음), stage는 함수명만. 프로젝트 밖(stdlib/venv) frame만 있으면
    라이브러리 파일명:함수명만 남긴다."""
    frames = traceback.extract_tb(exc.__traceback__)
    project_frame = None
    for frame in frames:
        try:
            rel = Path(frame.filename).resolve().relative_to(_PROJECT_ROOT)
        except ValueError:
            continue
        project_frame = (rel.as_posix(), frame.name, frame.lineno)
    if project_frame:
        path, func, line = project_frame
        return f"{path}:{func}:{line}", func
    if frames:
        last = frames[-1]
        return f"{Path(last.filename).name}:{last.name}", last.name
    return "", ""


def _not_attempted_result(place_id: str) -> dict:
    return {"place_id": place_id, "detail_success": False, "home_status": "not_attempted"}


def _error_result(place_id: str, exc: Exception | None = None) -> dict:
    result = {"place_id": place_id, "detail_success": False, "home_status": "unexpected_error"}
    if exc is not None:
        location, stage = _project_error_frame(exc)
        result["home_error_type"] = type(exc).__name__
        result["home_error_message"] = _sanitize_error_message(str(exc))
        result["home_error_location"] = location
        result["home_error_stage"] = stage
    return result


def _blank_home_fetch_result(place_id: str) -> dict:
    """`_fetch_place_home_async` 반환 dict의 공통 뼈대 - 병합용 필드와
    진단용 필드(home_* 접두사, `_fetch_place_detail_ssr`의 detail_ssr_*
    명명 규약과 동일한 의미)를 항상 포함한다. 쿠키/헤더 전체/HTML
    원문/토큰은 어디에도 담지 않는다(공개 정보와 구조 진단만)."""
    return {
        "place_id": place_id,
        "detail_success": False,
        "home_status": "",
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
        "home_http_status": None,
        "home_response_size": 0,
        "home_apollo_found": False,
        "home_base_found": False,
        "home_parent_found": False,
        "home_response_place_id": "",
        "home_place_id_exact": False,
        "home_adapter_success": False,
        "home_elapsed_seconds": 0.0,
        "home_error_type": "",
    }


async def _fetch_place_home_async(request_context, row: dict) -> dict:
    """`_fetch_place_detail_ssr`(기존 동기식 상세 보강 경로, 현재는 삭제됨)의
    async 대응. I/O만 async로 바뀌고 판정 로직(_classify_ssr_block_signal,
    _parse_apollo_state_from_html, extract_normalized_apollo_detail,
    _map_item_to_row, build_place_url_from_id)은 전부 순수 함수라 그대로
    재사용한다(재구현 없음). request_context는 실제 Native Edge
    BrowserContext의 `context.request`(production) 또는 테스트 fake다 -
    이 함수는 어느 쪽이든 `.get(url, headers=..., timeout=...)` 계약만
    있으면 동작한다. 예외를 던지지 않고 항상 dict를 반환한다.

    home_status는 항상 링크 존재 여부와 무관하게 apollo/base/place_id_exact/
    adapter 성공 시에만 "success"다 - 업체가 실제로 홈페이지·SNS를 등록하지
    않아 홈페이지/인스타/블로그/추가 링크가 전부 공란이어도 그 자체는
    실패가 아니다(요청서 §4)."""
    place_id = str(row.get("place_id") or "").strip()
    result = _blank_home_fetch_result(place_id)
    place_url = build_place_url_from_id(place_id)
    if not place_url:
        result["home_status"] = "no_place_url"
        result["home_error_type"] = "MissingPlaceId"
        return result

    t0 = time.monotonic()
    try:
        resp = await request_context.get(place_url, headers=_SSR_REQUEST_HEADERS, timeout=_SSR_REQUEST_TIMEOUT_MS)
    except PlaywrightAsyncTimeoutError:
        result["home_status"] = "timeout"
        result["home_error_type"] = "Timeout"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result
    except Exception as exc:
        result["home_status"] = "request_error"
        result["home_error_type"] = type(exc).__name__
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    status_code = resp.status
    result["home_http_status"] = status_code
    try:
        content_type = resp.headers.get("content-type", "") if resp.headers else ""
    except Exception:
        content_type = ""
    try:
        html_text = await resp.text()
    except Exception:
        html_text = ""
    result["home_response_size"] = len(html_text)

    block_signal = _classify_ssr_block_signal(status_code, html_text[:4000])
    if block_signal["blocked"]:
        block_type = block_signal["block_type"]
        result["home_status"] = "captcha_detected" if block_type == "CAPTCHA_CHALLENGE" else "security_blocked"
        result["home_error_type"] = block_type
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    if status_code != 200 or "text/html" not in content_type:
        if 500 <= status_code < 600:
            result["home_status"] = "http_5xx"
        else:
            result["home_status"] = "http_4xx"
        result["home_error_type"] = f"UnexpectedHttpStatus{status_code}"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    if not html_text.strip():
        result["home_status"] = "empty_html"
        result["home_error_type"] = "EmptyResponseBody"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    apollo_state = _parse_apollo_state_from_html(html_text)
    result["home_apollo_found"] = apollo_state is not None
    if apollo_state is None:
        result["home_status"] = "apollo_missing"
        result["home_error_type"] = "ApolloStateNotFound"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    base_key = f"PlaceDetailBase:{place_id}"
    base_entity = apollo_state.get(base_key)
    base_found = isinstance(base_entity, dict)
    result["home_base_found"] = base_found
    if not base_found:
        result["home_status"] = "base_missing"
        result["home_error_type"] = "BaseNotFound"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result
    base_id = str(base_entity.get("id") or "").strip()
    result["home_response_place_id"] = base_id
    if base_id and base_id != place_id:
        result["home_status"] = "place_id_mismatch"
        result["home_error_type"] = "PlaceIdMismatch"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result
    result["home_place_id_exact"] = True

    apollo_detail = extract_normalized_apollo_detail(apollo_state, place_id)
    if not apollo_detail:
        result["home_status"] = "adapter_empty"
        result["home_error_type"] = "AdapterEmpty"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result
    result["home_adapter_success"] = True

    parent_found = any(
        apollo_detail.get(field) is not None for field in ("homepages", "newOpening", "phoneInfo")
    )
    result["home_parent_found"] = parent_found
    if not parent_found:
        result["home_status"] = "parent_missing"
        result["home_error_type"] = "ParentNotFound"
        result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
        return result

    apollo_row = _map_item_to_row(apollo_detail, "")
    result["detail_success"] = True
    result["home_status"] = "success"
    result["업종"] = apollo_row.get("업종", "")
    result["새로오픈여부"] = apollo_row.get("새로오픈여부", "")
    result["방문자리뷰수"] = apollo_row.get("방문자리뷰수", "")
    result["블로그리뷰수"] = apollo_row.get("블로그리뷰수", "")
    result["총리뷰수"] = apollo_row.get("총리뷰수", "")
    result["대표전화"] = apollo_row.get("대표전화", "")
    result["주소"] = apollo_row.get("주소", "")
    result["플레이스 URL"] = place_url
    result["홈페이지"] = apollo_row.get("홈페이지", "")
    result["인스타"] = apollo_row.get("인스타", "")
    result["블로그"] = apollo_row.get("블로그", "")
    result["추가 링크"] = apollo_row.get("추가 링크", "")
    result["home_elapsed_seconds"] = round(time.monotonic() - t0, 3)
    return result


def merge_home_result_into_row(row: dict, home_result) -> dict:
    """홈페이지·SNS 모드 전용 병합 - 허용 목록(홈페이지/인스타/블로그/추가
    링크/공란 대표전화)만 채운다(요청서 §6 core parity 정책). 업체명/업종/
    새로오픈여부/방문자·블로그·총리뷰수/주소/플레이스 URL/수집일은 절대
    덮어쓰지 않는다 - 목록(ApolloFirstListCollector) 단계에서 이미 확정된
    값이 두 모드 공통 진실의 원천이며, home 상세 응답이 그 핵심 필드에 대해
    다른 값을 갖고 있어도 여기서는 참조조차 하지 않는다.
    home_result가 없거나 실패면 row를 그대로 반환한다(row 삭제 금지)."""
    if home_result is None or not home_result.get("detail_success"):
        return row
    merged = dict(row)
    for field in ("홈페이지", "인스타", "블로그", "추가 링크"):
        value = home_result.get(field)
        if value:
            merged[field] = value
    if not str(row.get("대표전화") or "").strip():
        detail_phone = home_result.get("대표전화")
        if detail_phone and not _is_personal_mobile_phone(detail_phone):
            merged["대표전화"] = detail_phone
    return merged


async def _connect_native_edge_context(backend_config: BrowserBackendConfig):
    """5Z가 검증한 방식 그대로: 같은 persistent profile을 가리키는 새 Native
    Edge/Chrome 프로세스를 시작하고, `connect_over_cdp`로 연결해 실제
    BrowserContext를 반환한다(NativeCdpBrowserSession._connect_over_cdp와
    동일한 절차를 async로 재구현 - src/browser/session.py 자체는 무수정 재사용,
    private helper만 import한다).

    반환: (playwright_cm, browser, context, process, lock_path). 실패 시
    이미 시작된 자원은 best-effort로 정리한 뒤 예외를 그대로 전파한다 -
    호출자가 '이번 실행에서는 재연결 불가'로 판단해 안전하게 중단할 수
    있도록, 조용히 계속 진행하지 않는다."""
    browser_type, browser_path = _resolve_browser(
        backend_config.browser_preference, backend_config.browser_path
    )
    profile_dir = Path(backend_config.profile_root) / browser_type
    lock_path = _acquire_profile_lock(profile_dir)
    process = None
    playwright_cm = None
    try:
        port = _pick_free_port()
        args = _build_native_browser_args(browser_path, port, profile_dir, visible=False)
        process = subprocess.Popen(args)
        # _wait_for_cdp_ready는 짧고 bounded된 동기 polling이다(NativeCdpBrowserSession과
        # 동일한 함수) - 이 시점에는 아직 동시 실행 중인 asyncio task가 없으므로
        # 이벤트 루프를 잠깐 막아도 다른 작업에 영향이 없다.
        _wait_for_cdp_ready(port, process, backend_config.cdp_startup_timeout_sec)

        playwright_cm = async_playwright()
        pw = await playwright_cm.__aenter__()
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        return playwright_cm, browser, context, process, lock_path
    except Exception:
        if playwright_cm is not None:
            try:
                await playwright_cm.__aexit__(None, None, None)
            except Exception:
                pass
        _terminate_owned_process(process)
        _release_profile_lock(lock_path)
        raise


# PAGE300-6H(홈페이지 보강 결과 의미 세분화): home_status="success"(detail_success
# =True)는 "업체 상세 보강 처리가 예외 없이 완료됨"만 뜻하며 홈페이지·SNS
# 링크 존재 여부와 무관하다(§4 요청서) - 링크가 하나도 없는 업체도 정상
# 성공이다. 사용자가 "성공 N건"을 "링크 N건 발견"으로 오인하지 않도록,
# 상세 처리 성공 row를 merge_home_result_into_row가 만드는 최종 export
# 필드(홈페이지/인스타/블로그/추가 링크) 기준으로 다시 "외부 링크 발견"과
# "외부 링크 없음"으로 나눈다. raw Apollo 값이 있어도 URL 정규화에서
# 폐기됐다면(예: malformed URL) 최종 필드가 비어 있으므로 "없음"으로
# 집계된다 - 이 판정은 항상 병합 이후 최종 row를 기준으로 한다.
_EXTERNAL_LINK_ROW_FIELDS = ("홈페이지", "인스타", "블로그", "추가 링크")


def _row_has_external_link(row: dict) -> bool:
    return any(str(row.get(field) or "").strip() for field in _EXTERNAL_LINK_ROW_FIELDS)


def _external_url_count(result: dict) -> int:
    if not result.get("detail_success"):
        return 0
    count = sum(1 for field in ("홈페이지", "인스타", "블로그") if result.get(field))
    extra = result.get("추가 링크") or ""
    if extra:
        count += len([line for line in extra.split("\n") if line.strip()])
    return count


async def _enrich_home_batch_async(
    rows, *, should_continue=None, on_progress=None, backend_config=None, request_context_factory=None,
    pause_event=None, stop_event=None,
) -> dict:
    """asyncio.Semaphore(2)로 1차 순회를 수행하고(동시성/차단/사용자중지/
    dedup 정책은 기존과 동일), 1차 실패 중 일시적(transient) 상태만
    (_HOME_RETRYABLE_STATUSES) 골라 안정화 대기(3초) 후 동시성 1로 최대 1회
    재시도한다(요청서 §7/§8, PAGE300-6G-R1). 차단/사용자중지/1차 실패율이
    대상 수의 10%를 초과하면 재시도 큐 자체를 만들지 않는다(§8 대량 실패
    안전장치 - 비율은 항상 실제 대상 수 기준으로 동적 계산, 하드코딩 금지).

    place_id마다 모든 시도(1차 + 재시도)의 진단 기록(§5 스키마)을
    `attempts`에 남기고, 최종까지 실패한 업체는 `final_failures`에
    업체명/place_id/원인/HTTP/시도횟수/응답시간을 남긴다. 쿠키/헤더
    전체/HTML 원문/토큰은 어디에도 저장하지 않는다.

    request_context_factory(선택, 테스트 전용 DI)는 인자 없이 호출되어
    request_context(.get() 계약만 있으면 됨)를 awaitable로 반환해야 한다 -
    주어지면 실제 Native Edge CDP 프로세스를 전혀 시작하지 않는다(테스트가
    순수 fake만으로 검증할 수 있게 하기 위함). 주어지지 않으면(production
    기본 경로) `_connect_native_edge_context`로 같은 persistent profile의
    실제 BrowserContext에 연결해 그 `.request`를 사용한다."""
    started_at = datetime.now(timezone.utc)
    unique_place_ids: list = []
    seen_ids: set = set()
    row_by_place_id: dict = {}
    for row in rows:
        place_id = str(row.get("place_id") or "").strip()
        if not place_id or place_id in seen_ids:
            continue
        seen_ids.add(place_id)
        unique_place_ids.append(place_id)
        row_by_place_id[place_id] = row

    total = len(unique_place_ids)
    cache: dict = {}
    attempts: list = []
    last_attempt_number: dict = {}
    stop_new_requests = asyncio.Event()
    sequence = {"n": 0}

    def _should_stop() -> bool:
        return stop_new_requests.is_set() or (should_continue is not None and not should_continue())

    def _report_progress() -> None:
        if on_progress is None:
            return
        completed = sum(1 for result in cache.values() if result.get("home_status") != "not_attempted")
        success = sum(1 for result in cache.values() if result.get("detail_success"))
        failure = completed - success
        try:
            on_progress(completed, total, success, failure)
        except Exception:
            pass

    def _record_attempt(place_id: str, attempt: int, result: dict) -> None:
        sequence["n"] += 1
        last_attempt_number[place_id] = attempt
        row = row_by_place_id.get(place_id, {})
        status = result.get("home_status", "")
        retryable = (not result.get("detail_success")) and status in _HOME_RETRYABLE_STATUSES
        error_stage = (
            result.get("home_error_stage", "") if status == "unexpected_error"
            else _ERROR_STAGE_BY_STATUS.get(status, "")
        )
        attempts.append(
            {
                "sequence": sequence["n"],
                "place_id": place_id,
                "name": row.get("업체명", ""),
                "attempt": attempt,
                "elapsed_ms": round(result.get("home_elapsed_seconds", 0.0) * 1000),
                "http_status": result.get("home_http_status"),
                "response_size": result.get("home_response_size", 0),
                "apollo_found": result.get("home_apollo_found", False),
                "base_found": result.get("home_base_found", False),
                "parent_found": result.get("home_parent_found", False),
                "reference_exact": result.get("home_adapter_success", False),
                "response_place_id": result.get("home_response_place_id", ""),
                "place_id_exact": result.get("home_place_id_exact", False),
                "adapter_success": result.get("home_adapter_success", False),
                "external_url_count": _external_url_count(result),
                "status": status,
                "error_type": result.get("home_error_type", ""),
                "error_stage": error_stage,
                "error_message": result.get("home_error_message", ""),
                "error_location": result.get("home_error_location", ""),
                "retryable": retryable,
                "retry_reason": _RETRY_REASON_BY_STATUS.get(status, ""),
                "blocked": status in ("security_blocked", "captcha_detected"),
                "final": False,  # 마지막에 place_id별 최종 시도만 True로 보정한다
            }
        )

    async def _run_pass(place_ids: list, concurrency: int, attempt: int, request_context, *, is_retry: bool) -> dict:
        semaphore = asyncio.Semaphore(concurrency)
        pass_counters = {"attempted": 0, "success": 0, "failed": 0}

        async def _run_one(place_id: str) -> None:
            # 다음 업체 home GET 전(§5 요청서). 60개 place_id 전부가
            # asyncio.create_task로 한꺼번에 스케줄되므로, 여기 첫 번째
            # 대기만으로는 실효성이 없다(일시정지가 켜지기도 전에 전부
            # 이 지점을 통과해버림) - 진짜 동시성 제한 지점인 semaphore
            # 획득 "직후"에도 다시 확인해야, 아직 순번이 안 온 나머지
            # place_id가 실제로 새 요청을 시작하기 직전에 걸린다. 이미
            # semaphore를 획득해 진행 중인 요청은 이 지점을 다시 지나지
            # 않으므로 취소되지 않고 안전하게 끝까지 완료된다.
            await wait_while_paused_async(pause_event, stop_event)
            if _should_stop():
                if not is_retry:
                    cache[place_id] = _not_attempted_result(place_id)
                    _report_progress()
                return  # retry pass: 1차 결과를 그대로 보존(덮어쓰지 않음)
            async with semaphore:
                await wait_while_paused_async(pause_event, stop_event)
                if _should_stop():
                    if not is_retry:
                        cache[place_id] = _not_attempted_result(place_id)
                        _report_progress()
                    return
                try:
                    result = await _fetch_place_home_async(request_context, row_by_place_id[place_id])
                except Exception as exc:
                    result = _error_result(place_id, exc)
                status = result.get("home_status")
                pass_counters["attempted"] += 1
                if result.get("detail_success"):
                    pass_counters["success"] += 1
                else:
                    pass_counters["failed"] += 1
                if status in ("security_blocked", "captcha_detected"):
                    stop_new_requests.set()
                cache[place_id] = result
                _record_attempt(place_id, attempt, result)
                _report_progress()

        tasks = [asyncio.create_task(_run_one(place_id)) for place_id in place_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return pass_counters

    # request_context_factory가 주어지면(테스트 전용 DI) 실제 Native Edge
    # CDP 프로세스를 전혀 시작하지 않는다 - collector_factory 등 이 저장소의
    # 다른 DI 지점들과 동일하게, 기본값이 아닌 값을 주입하면 실제 브라우저
    # 부작용이 생기지 않아야 한다는 원칙을 그대로 따른다.
    playwright_cm = browser = process = lock_path = None
    if request_context_factory is not None:
        request_context = await request_context_factory()
    else:
        playwright_cm, browser, context, process, lock_path = await _connect_native_edge_context(
            backend_config or BrowserBackendConfig.default()
        )
        request_context = context.request

    retry_pass_counters = {"attempted": 0, "success": 0, "failed": 0, "skipped": 0}
    try:
        first_pass_counters = await _run_pass(
            unique_place_ids, _HOME_ENRICHMENT_CONCURRENCY, 1, request_context, is_retry=False
        )

        retry_candidates = [
            place_id
            for place_id in unique_place_ids
            if not cache.get(place_id, {}).get("detail_success")
            and cache.get(place_id, {}).get("home_status") in _HOME_RETRYABLE_STATUSES
        ]
        failure_ratio_exceeded = total > 0 and first_pass_counters["failed"] > math.ceil(
            total * _HOME_MAX_FAILURE_RATIO_FOR_RETRY
        )
        safety_gate_triggered = _should_stop() or failure_ratio_exceeded

        if retry_candidates and not safety_gate_triggered:
            await asyncio.sleep(_HOME_RETRY_STABILIZATION_SECONDS)
            if _should_stop():
                retry_pass_counters["skipped"] = len(retry_candidates)
            else:
                ran = await _run_pass(
                    retry_candidates, _HOME_RETRY_CONCURRENCY, 2, request_context, is_retry=True
                )
                retry_pass_counters["attempted"] = ran["attempted"]
                retry_pass_counters["success"] = ran["success"]
                retry_pass_counters["failed"] = ran["failed"]
                retry_pass_counters["skipped"] = len(retry_candidates) - ran["attempted"]
        else:
            retry_pass_counters["skipped"] = len(retry_candidates)
    finally:
        if playwright_cm is not None:
            # context.request는 BrowserContext 소유 객체이므로 별도 dispose()를
            # 호출하지 않는다(그 context/browser를 닫으면 함께 정리된다) -
            # request.new_context()가 반환한 독립 APIRequestContext와 달리
            # 이 객체를 직접 dispose하는 것은 Playwright 계약이 아니다.
            try:
                await browser.close()
            except Exception:
                pass
            try:
                await playwright_cm.__aexit__(None, None, None)
            except Exception:
                pass
            _terminate_owned_process(process)
            _release_profile_lock(lock_path)

    # place_id별 마지막 시도만 final=True로 보정한다(재시도 큐가 나중에
    # 안전장치로 skip되어도 1차 시도 기록이 final로 정확히 남는다).
    for record in attempts:
        record["final"] = record["attempt"] == last_attempt_number.get(record["place_id"])

    if stop_new_requests.is_set():
        stop_reason = "security_blocked"
    elif should_continue is not None and not should_continue():
        stop_reason = "user_stopped"
    else:
        stop_reason = None

    final_success_count = sum(1 for result in cache.values() if result.get("detail_success"))
    not_attempted_count = sum(1 for result in cache.values() if result.get("home_status") == "not_attempted")
    final_failure_count = len(cache) - final_success_count - not_attempted_count

    # 상세 처리 성공(final_success_count) row만 최종 병합 row 기준으로 외부
    # 링크 발견/없음으로 나눈다 - 이 loop는 정확히 성공 row 집합만 순회하므로
    # link_found_count + no_link_count == final_success_count는 구조적으로
    # 항상 성립한다(런타임 방어 불필요, 어긋날 수 있는 외부 입력이 없음).
    link_found_count = 0
    no_link_count = 0
    for place_id in unique_place_ids:
        result = cache.get(place_id)
        if result is None or not result.get("detail_success"):
            continue
        merged_for_stats = merge_home_result_into_row(row_by_place_id[place_id], result)
        if _row_has_external_link(merged_for_stats):
            link_found_count += 1
        else:
            no_link_count += 1

    # 실제로 추가 요청이 실행된 횟수(retryable로 "표시"만 되고 안전장치/
    # 중지로 실행되지 않은 건 포함하지 않음) - retry_pass_counters["attempted"]가
    # 이미 정확히 이 의미다(재시도 대상은 최대 1회만 재시도하는 구조라 row
    # 수와 시도 횟수가 항상 같다 - 별도 retried_row_count는 추가하지 않는다).
    home_retry_count = retry_pass_counters["attempted"]

    final_failures = []
    failure_reason_counts: dict = {}
    for place_id in unique_place_ids:
        result = cache.get(place_id)
        if result is None or result.get("detail_success") or result.get("home_status") == "not_attempted":
            continue
        status = result.get("home_status", "")
        failure_reason_counts[status] = failure_reason_counts.get(status, 0) + 1
        row = row_by_place_id.get(place_id, {})
        final_failures.append(
            {
                "place_id": place_id,
                "name": row.get("업체명", ""),
                "status": status,
                "http_status": result.get("home_http_status"),
                "attempt": last_attempt_number.get(place_id, 1),
                "elapsed_ms": round(result.get("home_elapsed_seconds", 0.0) * 1000),
            }
        )

    finished_at = datetime.now(timezone.utc)
    diagnostics_report = {
        "run_id": uuid.uuid4().hex,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "mode": "home_sns",
        "target_count": total,
        "first_pass": {
            "attempted": first_pass_counters["attempted"],
            "success": first_pass_counters["success"],
            "failed": first_pass_counters["failed"],
        },
        "retry_pass": retry_pass_counters,
        "final": {
            "success": final_success_count,
            "failed": final_failure_count,
            "not_attempted": not_attempted_count,
            "stop_reason": stop_reason,
            "link_found": link_found_count,
            "no_link": no_link_count,
            "retry_count": home_retry_count,
        },
        "failure_reason_counts": failure_reason_counts,
        "attempts": attempts,
        "final_failures": final_failures,
    }

    merged_rows = [
        merge_home_result_into_row(row, cache.get(str(row.get("place_id") or "").strip())) for row in rows
    ]

    return {
        "rows": merged_rows,
        "stop_reason": stop_reason,
        "security_blocked": stop_new_requests.is_set(),
        "home_success_count": final_success_count,  # 하위 호환 별칭(HOME-STAT-11) - home_processed_success_count와 항상 동일
        "home_processed_success_count": final_success_count,
        "home_link_found_count": link_found_count,
        "home_no_link_count": no_link_count,
        "home_retry_count": home_retry_count,
        "failure_count": final_failure_count,
        "not_attempted_count": not_attempted_count,
        "first_pass": diagnostics_report["first_pass"],
        "retry_pass": retry_pass_counters,
        "final_failures": final_failures,
        "diagnostics_report": diagnostics_report,
    }


def enrich_home_details(rows, *, should_continue=None, on_progress=None, pause_event=None, stop_event=None) -> dict:
    """`asyncio.run()`으로 새 event loop를 만들고 그 안에서만 async Playwright를
    생성/사용/종료한다(sync 목록 수집 단계의 browser/context/page는 전혀
    참조하지 않음 - 그 세션은 이 함수가 호출되는 시점에 이미 완전히
    종료되어 있다). `asyncio.run()`이 함수 종료 시 loop를 자동으로 닫으므로
    '단일 event loop 소유 + 정상 종료'가 보장된다.

    pause_event/stop_event(선택, threading.Event)는 ui.py의 일시정지·중지
    버튼과 그대로 연결된다 - 매 place_id의 신규 home GET 시작 직전에
    wait_while_paused_async로 대기한다(이미 진행 중인 요청은 취소하지
    않음)."""
    return asyncio.run(
        _enrich_home_batch_async(
            rows, should_continue=should_continue, on_progress=on_progress,
            pause_event=pause_event, stop_event=stop_event,
        )
    )
