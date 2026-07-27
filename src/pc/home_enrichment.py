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
import subprocess
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightAsyncTimeoutError
from playwright.async_api import async_playwright

from src.pc.browser_session import (
    _acquire_profile_lock,
    _build_native_browser_args,
    _pick_free_port,
    _release_profile_lock,
    _resolve_browser,
    _terminate_owned_process,
    _wait_for_cdp_ready,
)
from src.pc.config import BrowserBackendConfig
from src.pc.network_browser_collector import (
    _SSR_REQUEST_HEADERS,
    _SSR_REQUEST_TIMEOUT_MS,
    _classify_ssr_block_signal,
    _parse_apollo_state_from_html,
)
from src.pc.network_list_scraper import (
    _is_personal_mobile_phone,
    _map_item_to_row,
    build_place_url_from_id,
    extract_normalized_apollo_detail,
)

_HOME_ENRICHMENT_CONCURRENCY = 2


def _not_attempted_result(place_id: str) -> dict:
    return {"place_id": place_id, "detail_success": False, "home_status": "not_attempted"}


def _error_result(place_id: str) -> dict:
    return {"place_id": place_id, "detail_success": False, "home_status": "error"}


async def _fetch_place_home_async(request_context, row: dict) -> dict:
    """`_fetch_place_detail_ssr`(sync, network_browser_collector.py)의 async
    대응. I/O만 async로 바뀌고 판정 로직(_classify_ssr_block_signal,
    _parse_apollo_state_from_html, extract_normalized_apollo_detail,
    _map_item_to_row, build_place_url_from_id)은 전부 순수 함수라 그대로
    재사용한다(재구현 없음). request_context는 실제 Native Edge
    BrowserContext의 `context.request`(production) 또는 테스트 fake다 -
    이 함수는 어느 쪽이든 `.get(url, headers=..., timeout=...)` 계약만
    있으면 동작한다. 예외를 던지지 않고 항상 dict를 반환한다."""
    place_id = str(row.get("place_id") or "").strip()
    result = {
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
    }
    place_url = build_place_url_from_id(place_id)
    if not place_url:
        result["home_status"] = "no_place_url"
        return result

    try:
        resp = await request_context.get(place_url, headers=_SSR_REQUEST_HEADERS, timeout=_SSR_REQUEST_TIMEOUT_MS)
    except PlaywrightAsyncTimeoutError:
        result["home_status"] = "timeout"
        return result
    except Exception:
        result["home_status"] = "request_error"
        return result

    status_code = resp.status
    try:
        content_type = resp.headers.get("content-type", "") if resp.headers else ""
    except Exception:
        content_type = ""
    try:
        html_text = await resp.text()
    except Exception:
        html_text = ""

    block_signal = _classify_ssr_block_signal(status_code, html_text[:4000])
    if block_signal["blocked"]:
        result["home_status"] = "blocked"
        result["block_type"] = block_signal["block_type"]
        return result

    if status_code != 200 or "text/html" not in content_type:
        result["home_status"] = "unexpected_response"
        return result

    apollo_state = _parse_apollo_state_from_html(html_text)
    if apollo_state is None:
        result["home_status"] = "apollo_missing"
        return result

    base_key = f"PlaceDetailBase:{place_id}"
    base_entity = apollo_state.get(base_key)
    if not isinstance(base_entity, dict):
        result["home_status"] = "base_missing"
        return result
    base_id = str(base_entity.get("id") or "").strip()
    if base_id and base_id != place_id:
        result["home_status"] = "place_id_mismatch"
        return result

    apollo_detail = extract_normalized_apollo_detail(apollo_state, place_id)
    if not apollo_detail:
        result["home_status"] = "adapter_empty"
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
    return result


def merge_home_result_into_row(row: dict, home_result) -> dict:
    """홈페이지·SNS 모드 전용 병합 - 허용 목록(홈페이지/인스타/블로그/공란
    대표전화)만 채운다(요청서 §6 core parity 정책). 업체명/업종/새로오픈여부/
    방문자·블로그·총리뷰수/주소/플레이스 URL/수집일은 절대 덮어쓰지 않는다 -
    목록(ApolloFirstListCollector) 단계에서 이미 확정된 값이 두 모드 공통
    진실의 원천이며, SSR 상세 응답이 그 핵심 필드에 대해 다른 값을 갖고
    있어도 여기서는 참조조차 하지 않는다. `merge_detail_into_row`(legacy
    DomMembershipCollector.enrich_detail_ssr 전용, network_list_scraper.py)를
    재사용하지 않는다 - 그 함수는 핵심 필드를 무조건 덮어쓰는 다른 정책을
    쓰므로 여기 재사용하면 안 된다(2026-07-25 field parity 보정으로 분리).
    home_result가 없거나 실패면 row를 그대로 반환한다(row 삭제 금지)."""
    if home_result is None or not home_result.get("detail_success"):
        return row
    merged = dict(row)
    for field in ("홈페이지", "인스타", "블로그"):
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
    동일한 절차를 async로 재구현 - browser_session.py 자체는 무수정 재사용,
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


async def _enrich_home_batch_async(
    rows, *, should_continue=None, on_progress=None, backend_config=None, request_context_factory=None
) -> dict:
    """asyncio.Semaphore(2)로 동시성을 제한하고, 차단(blocked) 또는 사용자
    중지 시 신규 scheduling을 즉시 중단한다 - 이미 세마포어를 통과해
    실행 중이던 요청(최대 2개)만 완료까지 진행하고, 아직 세마포어를 기다리던
    나머지는 시도하지 않고 not_attempted로 남는다. place_id당 정확히 1회만
    요청한다(dict 캐시).

    request_context_factory(선택, 테스트 전용 DI)는 인자 없이 호출되어
    request_context(.get() 계약만 있으면 됨)를 awaitable로 반환해야 한다 -
    주어지면 실제 Native Edge CDP 프로세스를 전혀 시작하지 않는다(테스트가
    순수 fake만으로 검증할 수 있게 하기 위함). 주어지지 않으면(production
    기본 경로) `_connect_native_edge_context`로 같은 persistent profile의
    실제 BrowserContext에 연결해 그 `.request`를 사용한다."""
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
    stop_new_requests = asyncio.Event()
    semaphore = asyncio.Semaphore(_HOME_ENRICHMENT_CONCURRENCY)
    counters = {"success": 0, "failure": 0, "completed": 0}

    def _should_stop() -> bool:
        return stop_new_requests.is_set() or (should_continue is not None and not should_continue())

    async def _run_one(request_context, place_id: str) -> None:
        if _should_stop():
            result = _not_attempted_result(place_id)
        else:
            async with semaphore:
                if _should_stop():
                    result = _not_attempted_result(place_id)
                else:
                    try:
                        result = await _fetch_place_home_async(request_context, row_by_place_id[place_id])
                    except Exception:
                        result = _error_result(place_id)
                    if result.get("home_status") == "blocked":
                        stop_new_requests.set()
        cache[place_id] = result
        counters["completed"] += 1
        if result.get("detail_success"):
            counters["success"] += 1
        elif result.get("home_status") != "not_attempted":
            counters["failure"] += 1
        if on_progress is not None:
            try:
                on_progress(counters["completed"], total, counters["success"], counters["failure"])
            except Exception:
                pass

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

    try:
        tasks = [asyncio.create_task(_run_one(request_context, place_id)) for place_id in unique_place_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
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

    if stop_new_requests.is_set():
        stop_reason = "security_blocked"
    elif should_continue is not None and not should_continue():
        stop_reason = "user_stopped"
    else:
        stop_reason = None

    not_attempted_count = sum(1 for result in cache.values() if result.get("home_status") == "not_attempted")

    merged_rows = [
        merge_home_result_into_row(row, cache.get(str(row.get("place_id") or "").strip())) for row in rows
    ]

    return {
        "rows": merged_rows,
        "stop_reason": stop_reason,
        "security_blocked": stop_new_requests.is_set(),
        "home_success_count": counters["success"],
        "failure_count": counters["failure"],
        "not_attempted_count": not_attempted_count,
    }


def enrich_home_details(rows, *, should_continue=None, on_progress=None) -> dict:
    """`asyncio.run()`으로 새 event loop를 만들고 그 안에서만 async Playwright를
    생성/사용/종료한다(sync 목록 수집 단계의 browser/context/page는 전혀
    참조하지 않음 - 그 세션은 이 함수가 호출되는 시점에 이미 완전히
    종료되어 있다). `asyncio.run()`이 함수 종료 시 loop를 자동으로 닫으므로
    '단일 event loop 소유 + 정상 종료'가 보장된다."""
    return asyncio.run(_enrich_home_batch_async(rows, should_continue=should_continue, on_progress=on_progress))
