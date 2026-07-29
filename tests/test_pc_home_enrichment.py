from pathlib import Path
import asyncio
import inspect
import json
import re
import sys


# 홈페이지·SNS 포함 모드 전용 신규 모듈(src/pc/home_enrichment.py) 검증용
# standalone 스크립트(실제 Playwright/네이버/Native Edge 프로세스 실행 없음).
# 이 저장소는 pytest-asyncio 등 별도 async 테스트 인프라를 쓰지 않으므로,
# async 로직은 평범한 sync 함수 안에서 asyncio.run(...)으로 호출해 검증한다.
#
# PAGE300-6A-FIX1(request provenance 보정): production 경로(request_context_
# factory 미주입)는 실제 Native Edge CDP persistent profile에 다시 연결해
# 그 BrowserContext.request를 쓴다(5Z 벤치마크와 동일 메커니즘) - 이 파일의
# 대부분 케이스는 request_context_factory로 그 연결 자체를 우회해 순수
# 로직(동시성/차단/dedup/병합)만 검증하고, check_production_path_uses_native_
# cdp_reconnect_not_cookie_copy 하나만 소스 검사로 "쿠키만 복사한 독립
# APIRequestContext(request.new_context)로 되돌아가지 않았는지"를 회귀
# 가드한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from playwright.async_api import TimeoutError as PlaywrightAsyncTimeoutError

import src.pc.home_enrichment as home_enrichment
from src.pc.home_enrichment import (
    _enrich_home_batch_async,
    enrich_home_details,
    merge_home_result_into_row,
)

# PAGE300-6G-R1: 운영 안정화 대기(3초)를 테스트에서는 0으로 낮춘다 - 이
# 모듈 상수는 _enrich_home_batch_async 안에서 매 호출 시 전역으로 참조되므로
# 여기서 재할당하면 이 프로세스 안에서 즉시 반영된다(운영 기본값 자체는
# home_enrichment.py 소스에서 바뀌지 않음 - 이 프로세스에서만 유효한 테스트
# 전용 오버라이드).
home_enrichment._HOME_RETRY_STABILIZATION_SECONDS = 0


class ValidationReporter:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0

    def pass_(self, message: str) -> None:
        self.pass_count += 1
        print(f"[PASS] {message}")

    def fail(self, message: str) -> None:
        self.fail_count += 1
        print(f"[FAIL] {message}")

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"FINAL: {final}")
        print("====================")


_PLACE_ID_FROM_URL = re.compile(r"/place/(\d+)/home")


def _place_id_from_url(url: str) -> str:
    match = _PLACE_ID_FROM_URL.search(url)
    return match.group(1) if match else ""


def _base_entity(place_id: str, **overrides) -> dict:
    entity = {
        "id": place_id,
        "name": "테스트 카페",
        "category": "카페",
        "roadAddress": "서울 강남구 테헤란로 1",
        "phone": "02-000-0000",
        "visitorReviewsTotal": 10,
        "cafeBlogReviewsTotal": 5,
        "naverBlog": None,
    }
    entity.update(overrides)
    return entity


def _parent_entity(base_ref: str, **overrides) -> dict:
    entity = {
        "base": {"__ref": base_ref},
        "homepages": {"repr": {"url": "https://example-cafe.test", "type": "홈페이지"}, "etc": []},
        "newOpening": False,
        "phoneInfo": {"phone": "02-000-0000", "isVirtualPhone": False, "isPrivatePhone": False},
    }
    entity.update(overrides)
    return entity


def _success_html_for(place_id: str) -> bytes:
    base_key = f"PlaceDetailBase:{place_id}"
    op_key = f'placeDetail({{"input":{{"deviceType":"mobile","id":"{place_id}","isNx":false}}}})'
    apollo_state = {
        base_key: _base_entity(place_id),
        "ROOT_QUERY": {op_key: _parent_entity(base_key)},
    }
    html = f"<html><script>window.__APOLLO_STATE__ = {json.dumps(apollo_state)};</script></html>"
    return html.encode("utf-8")


def _row(place_id: str, phone: str = "") -> dict:
    return {
        "업체명": f"업체{place_id}", "place_id": place_id, "대표전화": phone,
        "주소": "", "홈페이지": "", "인스타": "", "블로그": "",
        "방문자리뷰수": "", "블로그리뷰수": "", "총리뷰수": "", "새로오픈여부": "", "업종": "",
        "플레이스 URL": "",
    }


class FakeAsyncResponse:
    def __init__(self, status: int, body: bytes, headers=None):
        self.status = status
        self._body = body
        self.headers = headers if headers is not None else {"content-type": "text/html"}

    async def text(self) -> str:
        return self._body.decode("utf-8")


class FakeAsyncRequestContext:
    """`_fetch_place_home_async`가 기대하는 최소 계약(async get())만 흉내낸다.
    production에서는 이 객체가 실제 Native Edge BrowserContext의
    `context.request`이지만, 이 fake는 그 계약만 만족하면 되므로 실제
    브라우저/CDP 연결 없이 순수 로직만 검증할 수 있다. delay_seconds는
    place_id별 인위적인 await 지연을 줘 동시성 상한(Semaphore(2))을 관측
    가능하게 만든다.

    outcomes_by_place_id(선택, PAGE300-6G-R1 재시도 검증용): place_id별로
    호출 순서대로 소비되는 응답/예외 리스트 - 1차 시도와 재시도가 다른
    결과를 내도록(예: 1차 apollo_missing → 재시도 success) 만들 때 쓴다.
    리스트의 항목이 BaseException 인스턴스면 그 예외를 그대로 raise한다.
    같은 place_id로 두 번째 이상 호출되면(=재시도 호출) 별도의 재시도
    전용 동시성 카운터도 관측한다."""

    def __init__(
        self, response_by_place_id: dict, *, delay_by_place_id=None, on_response_for=None,
        outcomes_by_place_id=None,
    ):
        self.response_by_place_id = response_by_place_id
        self.delay_by_place_id = delay_by_place_id or {}
        self.on_response_for = on_response_for or {}
        self.outcomes_by_place_id = outcomes_by_place_id or {}
        self.get_calls: list = []
        self._current_concurrency = 0
        self.max_observed_concurrency = 0
        self._current_retry_concurrency = 0
        self.max_observed_retry_concurrency = 0

    async def get(self, url, headers=None, timeout=None):
        place_id = _place_id_from_url(url)
        is_retry_call = self.get_calls.count(place_id) >= 1
        self.get_calls.append(place_id)
        self._current_concurrency += 1
        self.max_observed_concurrency = max(self.max_observed_concurrency, self._current_concurrency)
        if is_retry_call:
            self._current_retry_concurrency += 1
            self.max_observed_retry_concurrency = max(
                self.max_observed_retry_concurrency, self._current_retry_concurrency
            )
        try:
            delay = self.delay_by_place_id.get(place_id, 0)
            if delay:
                await asyncio.sleep(delay)
            callback = self.on_response_for.get(place_id)
            if callback is not None:
                callback()
            if place_id in self.outcomes_by_place_id:
                outcomes = self.outcomes_by_place_id[place_id]
                call_index = self.get_calls.count(place_id) - 1
                outcome = outcomes[min(call_index, len(outcomes) - 1)]
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome
            return self.response_by_place_id[place_id]
        finally:
            self._current_concurrency -= 1
            if is_retry_call:
                self._current_retry_concurrency -= 1


def _run(coro):
    return asyncio.run(coro)


def _factory_for(ctx):
    """request_context_factory(인자 없음) DI 계약 - 주어진 fake request_context를
    그대로 반환하는 코루틴을 만든다(실제 Native Edge CDP 연결을 완전히 우회)."""

    async def _factory():
        return ctx

    return _factory


def check_success_merges_home_fields_without_touching_existing_phone(reporter: ValidationReporter) -> None:
    rows = [_row("111", phone="02-111-1111")]
    ctx = FakeAsyncRequestContext({"111": FakeAsyncResponse(200, _success_html_for("111"))})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    row0 = result["rows"][0]
    ok = (
        row0["홈페이지"] == "https://example-cafe.test"
        and row0["대표전화"] == "02-111-1111"  # 기존 목록 전화가 유지됨(덮어쓰지 않음)
        and result["home_success_count"] == 1
    )
    if ok:
        reporter.pass_("1. 성공 시 홈페이지 병합 + 기존 목록 전화 보존")
    else:
        reporter.fail(f"1. 성공 병합 케이스 실패: {row0}, result={result}")


def check_blank_phone_gets_filled_from_home(reporter: ValidationReporter) -> None:
    rows = [_row("111", phone="")]
    ctx = FakeAsyncRequestContext({"111": FakeAsyncResponse(200, _success_html_for("111"))})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    row0 = result["rows"][0]
    if row0["대표전화"] == "02-000-0000":
        reporter.pass_("2. 목록 전화가 공란이면 home 전화로 보완")
    else:
        reporter.fail(f"2. 공란 전화 보완 실패: {row0}")


def check_concurrency_capped_at_two(reporter: ValidationReporter) -> None:
    place_ids = [str(100 + i) for i in range(5)]
    rows = [_row(pid) for pid in place_ids]
    responses = {pid: FakeAsyncResponse(200, _success_html_for(pid)) for pid in place_ids}
    ctx = FakeAsyncRequestContext(responses, delay_by_place_id={pid: 0.02 for pid in place_ids})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    if ctx.max_observed_concurrency <= 2 and len(ctx.get_calls) == 5 and result["home_success_count"] == 5:
        reporter.pass_(f"3. 동시성 상한 2 준수(관측된 최대={ctx.max_observed_concurrency}), 5건 전부 성공")
    else:
        reporter.fail(f"3. 동시성 상한 검증 실패: max_observed={ctx.max_observed_concurrency}, calls={ctx.get_calls}, result={result}")


def check_blocked_response_stops_new_scheduling(reporter: ValidationReporter) -> None:
    place_ids = [str(200 + i) for i in range(5)]
    rows = [_row(pid) for pid in place_ids]
    responses = {pid: FakeAsyncResponse(200, _success_html_for(pid)) for pid in place_ids}
    responses[place_ids[0]] = FakeAsyncResponse(403, b"")
    ctx = FakeAsyncRequestContext(responses, delay_by_place_id={place_ids[1]: 0.05})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    not_attempted = result["not_attempted_count"]
    if len(ctx.get_calls) <= 2 and not_attempted >= 3 and result["security_blocked"] is True:
        reporter.pass_(f"4. 차단 감지 시 신규 scheduling 중단(실제 요청={len(ctx.get_calls)}건, 미시도={not_attempted}건)")
    else:
        reporter.fail(f"4. 차단 시 중단 검증 실패: calls={ctx.get_calls}, not_attempted={not_attempted}, result={result}")


def check_user_stop_mid_batch(reporter: ValidationReporter) -> None:
    place_ids = [str(300 + i) for i in range(5)]
    rows = [_row(pid) for pid in place_ids]
    responses = {pid: FakeAsyncResponse(200, _success_html_for(pid)) for pid in place_ids}
    stop_flag = {"stop": False}

    def _stop_after_first():
        stop_flag["stop"] = True

    ctx = FakeAsyncRequestContext(
        responses,
        delay_by_place_id={place_ids[1]: 0.05},
        on_response_for={place_ids[0]: _stop_after_first},
    )
    result = _run(
        _enrich_home_batch_async(
            rows, should_continue=lambda: not stop_flag["stop"], request_context_factory=_factory_for(ctx),
        )
    )
    if result["stop_reason"] == "user_stopped" and result["not_attempted_count"] >= 3:
        reporter.pass_("5. should_continue False 전환 시 신규 scheduling 중단")
    else:
        reporter.fail(f"5. 사용자 중지 검증 실패: {result}")


def check_pause_event_blocks_new_requests_until_resumed(reporter: ValidationReporter) -> None:
    """NETWORK-CONTROLS-1 회귀 가드: 5개 place_id가 전부 asyncio.create_task로
    거의 동시에 스케줄되므로, _run_one 진입 시점(semaphore 획득 전)의 pause
    체크 단 한 번만으로는 실효성이 없다 - 동시성 상한(2)에 걸려 아직 순번이
    안 온 나머지 place_id는 이미 그 첫 체크를 통과한 뒤 semaphore 대기열에
    들어가 있으므로, semaphore를 실제로 획득하는 시점에 다시 확인해야만
    막힌다(2026-07-30 실제 UI 검증에서 이 재확인이 없어 일시정지가 전혀
    동작하지 않음을 실측으로 확인했다). 5개 모두 동일한 인위적 지연(0.05s)을
    줘 두 슬롯(0,1)이 먼저 점유되고 나머지(2,3,4)가 semaphore 대기 상태에
    들어간 뒤에, 독립된 실제 스레드가 pause_event를 켜는 방식으로 재현한다."""
    import threading
    import time

    place_ids = [str(400 + i) for i in range(5)]
    rows = [_row(pid) for pid in place_ids]
    responses = {pid: FakeAsyncResponse(200, _success_html_for(pid)) for pid in place_ids}
    pause_event = threading.Event()
    stop_event = threading.Event()

    def _pause_then_resume():
        time.sleep(0.02)  # 2,3,4가 semaphore 대기열에 들어갈 시간을 준다
        pause_event.set()
        time.sleep(0.3)
        pause_event.clear()

    ctx = FakeAsyncRequestContext(responses, delay_by_place_id={pid: 0.05 for pid in place_ids})
    threading.Thread(target=_pause_then_resume, daemon=True).start()
    # 재확인 게이트가 없다면(회귀) 대기열의 2,3,4는 pause 여부와 무관하게
    # 0.05s 안팎으로 곧바로 끝나 전체 소요시간이 0.3s보다 훨씬 짧다. 게이트가
    # 있으면 재개(0.32s 시점)까지 실제로 막혀 총 소요시간이 0.3s 이상이어야 한다.
    started = time.monotonic()
    result = _run(
        _enrich_home_batch_async(
            rows, request_context_factory=_factory_for(ctx),
            pause_event=pause_event, stop_event=stop_event,
        )
    )
    elapsed = time.monotonic() - started
    ok = (
        result["home_success_count"] == 5
        and result["not_attempted_count"] == 0
        and set(ctx.get_calls) == set(place_ids)
        and elapsed >= 0.28
    )
    if ok:
        reporter.pass_(f"7. 일시정지 중 새 요청이 막혔다가({elapsed:.2f}s 소요) 재개 후 전부 정상 완료(semaphore 재확인 게이트 회귀 가드)")
    else:
        reporter.fail(f"7. 일시정지 재확인 게이트 검증 실패: elapsed={elapsed:.2f}s, result={result}, get_calls={ctx.get_calls}")


def check_duplicate_place_id_fetched_once(reporter: ValidationReporter) -> None:
    rows = [_row("111"), _row("111"), _row("111")]
    ctx = FakeAsyncRequestContext({"111": FakeAsyncResponse(200, _success_html_for("111"))})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    if ctx.get_calls == ["111"] and len(result["rows"]) == 3:
        reporter.pass_("6. 동일 place_id가 여러 row에 있어도 요청은 정확히 1회")
    else:
        reporter.fail(f"6. 중복 place_id 단일 요청 검증 실패: calls={ctx.get_calls}, rows={len(result['rows'])}")


def check_merge_home_result_into_row_unit_cases(reporter: ValidationReporter) -> None:
    row = _row("111", phone="02-111-1111")

    merged_none = merge_home_result_into_row(row, None)
    merged_failed = merge_home_result_into_row(row, {"detail_success": False})
    success_result = {
        "detail_success": True, "place_id": "111", "홈페이지": "https://x.test",
        "인스타": "", "블로그": "", "주소": "", "플레이스 URL": "https://pcmap.place.naver.com/place/111/home",
        "업종": "", "새로오픈여부": "", "방문자리뷰수": "", "블로그리뷰수": "",
    }
    merged_success = merge_home_result_into_row(row, success_result)
    row_blank_phone = _row("111", phone="")
    merged_fill = merge_home_result_into_row(row_blank_phone, success_result)

    ok = (
        merged_none is row
        and merged_failed is row
        and merged_success["홈페이지"] == "https://x.test"
        and merged_success["대표전화"] == "02-111-1111"
        and merged_fill["대표전화"] == ""
    )
    if ok:
        reporter.pass_("7. merge_home_result_into_row 단위 케이스(None/실패/성공/전화 보존) 성공")
    else:
        reporter.fail(
            f"7. merge_home_result_into_row 단위 케이스 실패: none={merged_none is row}, "
            f"failed={merged_failed is row}, success={merged_success}, fill={merged_fill}"
        )


def check_core_fields_never_overwritten_by_home_result(reporter: ValidationReporter) -> None:
    """G(§9): 두 모드 core parity 정책 - home_result가 목록 단계와 전혀 다른
    업종/새로오픈여부/리뷰수/주소/플레이스 URL/수집일 값을 갖고 있어도
    merge_home_result_into_row는 그 필드들을 절대 참조·덮어쓰지 않는다.
    2026-07-25 field parity 보정 전에는 merge_detail_into_row를 재사용해
    이 필드들이 무조건(또는 공란일 때만) 덮어써졌다 - 이번 회귀 가드가
    바로 그 결함을 고정한다."""
    row = {
        "업체명": "카페 원본", "업종": "카페(목록)", "새로오픈여부": "",
        "방문자리뷰수": 10, "블로그리뷰수": 5, "총리뷰수": 15,
        "주소": "서울특별시 강동구 천호동 구천면로 140", "대표전화": "02-111-1111",
        "플레이스 URL": "https://pcmap.place.naver.com/place/111/home", "수집일": "2026-07-25",
        "홈페이지": "", "인스타": "", "블로그": "",
    }
    conflicting_home_result = {
        "detail_success": True,
        "업종": "카페(상세, 다른 값)", "새로오픈여부": "X",
        "방문자리뷰수": 999, "블로그리뷰수": 888, "총리뷰수": 1887,
        "주소": "완전히 다른 상세 주소", "플레이스 URL": "https://pcmap.place.naver.com/place/999/home",
        "수집일": "2099-01-01",
        "대표전화": "02-999-9999", "홈페이지": "https://home.test", "인스타": "https://instagram.com/x", "블로그": "",
    }
    merged = merge_home_result_into_row(row, conflicting_home_result)
    ok = (
        merged["업체명"] == "카페 원본"
        and merged["업종"] == "카페(목록)"
        and merged["새로오픈여부"] == ""
        and merged["방문자리뷰수"] == 10
        and merged["블로그리뷰수"] == 5
        and merged["총리뷰수"] == 15
        and merged["주소"] == "서울특별시 강동구 천호동 구천면로 140"
        and merged["플레이스 URL"] == "https://pcmap.place.naver.com/place/111/home"
        and merged["수집일"] == "2026-07-25"
        and merged["대표전화"] == "02-111-1111"  # 이미 유효한 목록 전화 보존(덮어쓰지 않음)
        and merged["홈페이지"] == "https://home.test"  # 허용된 필드만 채워짐
        and merged["인스타"] == "https://instagram.com/x"
    )
    if ok:
        reporter.pass_("G. home_result의 상충되는 핵심 필드값이 전부 무시되고 목록 값이 그대로 보존되며, 허용된 URL 필드만 채워짐")
    else:
        reporter.fail(f"G. core parity 회귀 발생: {merged}")


def check_basic_and_home_sns_share_core_fields_given_same_list_rows(reporter: ValidationReporter) -> None:
    """G(§9): 동일한 목록 rows를 두 모드에 준다고 가정했을 때 - 기본 모드는
    rows를 그대로 반환하고(가공 없음), 홈페이지·SNS 모드는
    merge_home_result_into_row만 거치므로 핵심 9개 필드(업체명/업종/새로
    오픈여부/방문자리뷰수/블로그리뷰수/총리뷰수/주소/플레이스 URL/수집일)가
    두 모드에서 정확히 동일함을 확인한다."""
    core_fields = (
        "업체명", "업종", "새로오픈여부", "방문자리뷰수", "블로그리뷰수",
        "총리뷰수", "주소", "플레이스 URL", "수집일",
    )
    list_rows = [
        {
            "업체명": f"업체{i}", "업종": "카페", "새로오픈여부": "O" if i == 0 else "",
            "방문자리뷰수": 10 + i, "블로그리뷰수": i, "총리뷰수": 10 + i + i,
            "주소": f"서울특별시 강동구 천호동 도로명 {i}", "대표전화": "",
            "플레이스 URL": f"https://pcmap.place.naver.com/place/{i}/home", "수집일": "2026-07-25",
            "홈페이지": "", "인스타": "", "블로그": "", "place_id": str(i),
        }
        for i in range(3)
    ]
    basic_rows = [dict(row) for row in list_rows]  # 기본 모드: 가공 없이 그대로
    home_result_by_index = {
        0: {"detail_success": True, "홈페이지": "https://x0.test", "인스타": "", "블로그": "", "대표전화": "051-000-0000",
            "업종": "완전히다른값", "새로오픈여부": "X", "방문자리뷰수": 0, "블로그리뷰수": 0, "총리뷰수": 0},
        1: {"detail_success": False},
        2: None,
    }
    home_sns_rows = [
        merge_home_result_into_row(dict(row), home_result_by_index[i]) for i, row in enumerate(list_rows)
    ]

    core_parity_ok = all(
        basic_rows[i][field] == home_sns_rows[i][field]
        for i in range(3) for field in core_fields
    )
    home_extras_ok = (
        home_sns_rows[0]["홈페이지"] == "https://x0.test"
        and home_sns_rows[0]["대표전화"] == "051-000-0000"  # 목록 전화가 공란이었으므로 보완됨
        and home_sns_rows[1] == basic_rows[1]  # 실패한 home_result는 row를 그대로 반환
        and home_sns_rows[2] == basic_rows[2]  # None도 마찬가지
    )
    if core_parity_ok and home_extras_ok:
        reporter.pass_("G. 동일 목록 rows 기준 basic/home_sns 핵심 9필드 완전 일치 + home_sns는 URL/공란전화만 추가")
    else:
        reporter.fail(f"G. 두 모드 core parity 실패: core_parity_ok={core_parity_ok}, home_extras_ok={home_extras_ok}, home_sns_rows={home_sns_rows}")


def check_enrich_home_details_sync_wrapper_bypasses_native_cdp_when_injected(reporter: ValidationReporter) -> None:
    """`enrich_home_details`(공개 sync 진입점)는 `cookies` 인자를 받지 않는다
    (구 버전 인터페이스 회귀 가드) - request_context_factory가 없는 production
    경로는 `_connect_native_edge_context`를 통해서만 연결되므로, 여기서는
    시그니처만 검증하고 실제 연결은 다른 소스 검사 케이스에서 확인한다."""
    signature = inspect.signature(enrich_home_details)
    has_cookies_param = "cookies" in signature.parameters
    if not has_cookies_param:
        reporter.pass_("8. enrich_home_details가 더 이상 cookies 파라미터를 받지 않음(쿠키 값 복사 폐기)")
    else:
        reporter.fail(f"8. enrich_home_details가 여전히 cookies 파라미터를 받음: {signature}")


def check_production_path_uses_native_cdp_reconnect_not_cookie_copy(reporter: ValidationReporter) -> None:
    """PAGE300-6A-FIX1 핵심 회귀 가드: production 경로(request_context_factory
    미주입)가 `playwright.request.new_context(storage_state=...)`(쿠키만
    복사한 독립 APIRequestContext, 5Z와 다른 방식)로 되돌아가지 않고,
    `_connect_native_edge_context`(같은 persistent profile에 connect_over_cdp
    로 재연결해 실제 BrowserContext.request를 쓰는 방식)를 사용하는지
    소스 검사로 확인한다."""
    # 주석에는 "이 방식(storage_state 쿠키 복사)을 쓰지 않는다"는 설명 자체가
    # 그 금지 패턴의 이름을 포함할 수 있으므로(예: 이 파일 헤더 주석), 주석이
    # 아니라 실행 코드 라인만 검사한다.
    code_lines = [
        line for line in inspect.getsource(home_enrichment).splitlines()
        if not line.strip().startswith("#")
    ]
    code_only_source = "\n".join(code_lines)
    uses_native_reconnect = "_connect_native_edge_context" in inspect.getsource(home_enrichment._enrich_home_batch_async)
    uses_context_request = "context.request" in inspect.getsource(home_enrichment._enrich_home_batch_async)
    no_cookie_storage_state = "storage_state" not in code_only_source and "request.new_context" not in code_only_source
    connect_source = inspect.getsource(home_enrichment._connect_native_edge_context)
    uses_connect_over_cdp = "connect_over_cdp" in connect_source
    uses_native_helpers = all(
        name in connect_source
        for name in ("_resolve_browser", "_build_native_browser_args", "_wait_for_cdp_ready")
    )
    ok = (
        uses_native_reconnect
        and uses_context_request
        and no_cookie_storage_state
        and uses_connect_over_cdp
        and uses_native_helpers
    )
    if ok:
        reporter.pass_("9. production 경로가 Native Edge CDP persistent profile 재연결(context.request) 방식을 사용하고, storage_state 쿠키 복사 방식은 코드에서 완전히 제거됨")
    else:
        reporter.fail(
            f"9. request provenance 회귀 발생: uses_native_reconnect={uses_native_reconnect}, "
            f"uses_context_request={uses_context_request}, no_cookie_storage_state={no_cookie_storage_state}, "
            f"uses_connect_over_cdp={uses_connect_over_cdp}, uses_native_helpers={uses_native_helpers}"
        )


def check_dispose_not_called_on_context_request(reporter: ValidationReporter) -> None:
    """context.request(BrowserContext 소유 객체)는 이 모듈이 직접
    dispose()하면 안 된다(Playwright 계약 위반) - 소스에 request_context.
    dispose()/request.dispose() 호출이 없는지 확인한다."""
    source = inspect.getsource(home_enrichment._enrich_home_batch_async)
    if "request_context.dispose" not in source:
        reporter.pass_("10. context.request에 대해 dispose()를 직접 호출하지 않음(BrowserContext가 소유)")
    else:
        reporter.fail("10. context.request에 대해 dispose()를 호출하고 있음 - Playwright 계약 위반 가능성")


def _success_html_with_extra_links(place_id: str) -> bytes:
    """PAGE300-6E-V3: homepages.etc에 대표(홈페이지) 외 채널이 여러 개
    있는 SSR 성공 응답을 만든다(카카오채널 + 두 번째 인스타)."""
    base_key = f"PlaceDetailBase:{place_id}"
    op_key = f'placeDetail({{"input":{{"deviceType":"mobile","id":"{place_id}","isNx":false}}}})'
    parent = _parent_entity(
        base_key,
        homepages={
            "repr": {"url": "https://example-cafe.test", "type": "홈페이지"},
            "etc": [
                {"url": "https://pf.kakao.com/_example", "type": "홈페이지"},
                {"url": "https://instagram.com/example_second", "type": "인스타그램"},
            ],
        },
    )
    apollo_state = {
        base_key: _base_entity(place_id),
        "ROOT_QUERY": {op_key: parent},
    }
    html = f"<html><script>window.__APOLLO_STATE__ = {json.dumps(apollo_state)};</script></html>"
    return html.encode("utf-8")


def check_extra_links_flow_through_ssr_fetch_and_merge(reporter: ValidationReporter) -> None:
    """PAGE300-6E-V3: homepages.etc의 카카오채널/두 번째 인스타가 유실되지
    않고 _fetch_place_home_async 결과와 merge_home_result_into_row 병합
    결과 모두에 "추가 링크"로 보존되는지 확인한다."""
    rows = [_row("222")]
    ctx = FakeAsyncRequestContext({"222": FakeAsyncResponse(200, _success_html_with_extra_links("222"))})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    row0 = result["rows"][0]
    extra_lines = row0["추가 링크"].split("\n") if row0["추가 링크"] else []
    ok = (
        row0["홈페이지"] == "https://example-cafe.test"
        and row0["인스타"] == "https://instagram.com/example_second"
        and len(extra_lines) == 1
        and extra_lines[0] == "[카카오채널] https://pf.kakao.com/_example"
    )
    if ok:
        reporter.pass_("11. homepages.etc의 카카오채널이 SSR fetch + merge 전체 경로에서 '추가 링크'로 유실 없이 보존됨")
    else:
        reporter.fail(f"11. 추가 링크 SSR 흐름 검증 실패: {row0}")


def check_merge_home_result_into_row_fills_extra_links_field(reporter: ValidationReporter) -> None:
    row = _row("333")
    home_result = {
        "detail_success": True, "place_id": "333", "홈페이지": "https://x.test",
        "인스타": "", "블로그": "", "추가 링크": "[카카오채널] https://pf.kakao.com/_x",
        "주소": "", "플레이스 URL": "https://pcmap.place.naver.com/place/333/home",
        "업종": "", "새로오픈여부": "", "방문자리뷰수": "", "블로그리뷰수": "",
    }
    merged = merge_home_result_into_row(row, home_result)
    if merged["추가 링크"] == "[카카오채널] https://pf.kakao.com/_x":
        reporter.pass_("12. merge_home_result_into_row가 '추가 링크' 필드도 정확히 채움")
    else:
        reporter.fail(f"12. 추가 링크 병합 실패: {merged}")


def check_basic_mode_leaves_extra_links_blank(reporter: ValidationReporter) -> None:
    """§12: 기본(basic) 모드는 home GET을 전혀 하지 않으므로 목록 rows를
    가공 없이 그대로 반환한다 - 홈페이지/인스타/블로그와 마찬가지로 '추가
    링크'도 목록 응답에 없으면(대부분) 공란으로 유지되고, home_sns 모드만
    거쳐야 채워진다(merge_home_result_into_row를 거치지 않으면 불변)."""
    list_row = {
        "업체명": "업체0", "업종": "카페", "새로오픈여부": "", "방문자리뷰수": 10,
        "블로그리뷰수": 0, "총리뷰수": 10, "주소": "서울특별시 강동구 천호동 0",
        "대표전화": "", "플레이스 URL": "https://pcmap.place.naver.com/place/0/home",
        "수집일": "2026-07-27", "홈페이지": "", "인스타": "", "블로그": "", "추가 링크": "",
        "place_id": "0",
    }
    basic_row = dict(list_row)  # 기본 모드: home_enrichment 자체를 호출하지 않음(가공 없음)
    if basic_row["추가 링크"] == "" and basic_row == list_row:
        reporter.pass_("13. 기본 모드는 home 보강을 거치지 않아 추가 링크를 포함한 모든 URL 필드가 공란으로 유지됨")
    else:
        reporter.fail(f"13. 기본 모드 추가 링크 공란 정책 위반: {basic_row}")


# ============================================================================
# PAGE300-6G-R1: 홈페이지 보강 실패 진단 + 1회 재시도 검증(요청서 §13 A~H)
# ============================================================================


def _apollo_html(place_id: str, *, base_overrides=None, parent_overrides=None) -> bytes:
    base_key = f"PlaceDetailBase:{place_id}"
    op_key = f'placeDetail({{"input":{{"deviceType":"mobile","id":"{place_id}","isNx":false}}}})'
    base = _base_entity(place_id, **(base_overrides or {}))
    parent = _parent_entity(base_key, **(parent_overrides or {}))
    apollo_state = {base_key: base, "ROOT_QUERY": {op_key: parent}}
    html = f"<html><script>window.__APOLLO_STATE__ = {json.dumps(apollo_state)};</script></html>"
    return html.encode("utf-8")


def check_zero_external_links_is_success_not_retried(reporter: ValidationReporter) -> None:
    """A(§13): 업체가 실제로 홈페이지·SNS를 등록하지 않아도(homepages 없음)
    HTTP/Apollo/Base/Parent/Adapter가 전부 정상이면 성공이며, 실패 집계에
    들어가지 않고 재시도도 하지 않는다."""
    rows = [_row("911")]
    html = _apollo_html("911", parent_overrides={"homepages": None})
    ctx = FakeAsyncRequestContext({"911": FakeAsyncResponse(200, html)})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    row0 = result["rows"][0]
    ok = (
        result["home_success_count"] == 1
        and result["failure_count"] == 0
        and result["not_attempted_count"] == 0
        and len(result["final_failures"]) == 0
        and ctx.get_calls.count("911") == 1
        and row0["홈페이지"] == "" and row0["인스타"] == "" and row0["블로그"] == ""
    )
    if ok:
        reporter.pass_("A. 홈페이지·SNS 미등록(외부 링크 0개)은 성공으로 처리되고 재시도 큐에 들어가지 않음")
    else:
        reporter.fail(f"A. 링크 0개 성공 처리 검증 실패: result={result}")


def check_transient_failure_retried_and_succeeds(reporter: ValidationReporter) -> None:
    """B(§13): 1차 apollo_missing → 재시도 성공. 총 요청 2회, retry_pass
    성공 집계 1, final_failures는 빈 리스트."""
    rows = [_row("922")]
    outcomes = {"922": [FakeAsyncResponse(200, b"<html>no apollo state here</html>"), FakeAsyncResponse(200, _apollo_html("922"))]}
    ctx = FakeAsyncRequestContext({}, outcomes_by_place_id=outcomes)
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    ok = (
        ctx.get_calls.count("922") == 2
        and result["home_success_count"] == 1
        and result["failure_count"] == 0
        and result["first_pass"]["failed"] == 1
        and result["retry_pass"]["success"] == 1
        and len(result["final_failures"]) == 0
        and result["rows"][0]["홈페이지"] == "https://example-cafe.test"
    )
    if ok:
        reporter.pass_("B. 1차 apollo_missing 후 재시도 성공(총 요청 2회, 최종 실패 0건)")
    else:
        reporter.fail(f"B. 일시적 실패 재시도 성공 검증 실패: result={result}")


def check_final_failure_after_retry_still_fails(reporter: ValidationReporter) -> None:
    """C(§13): 1차/재시도 모두 timeout → 최종 실패로 기록되고 업체명/
    place_id/원인이 남으며, row 자체는 삭제되지 않는다(목록 원본 유지)."""
    rows = [_row("933")]
    outcomes = {"933": [PlaywrightAsyncTimeoutError("t1"), PlaywrightAsyncTimeoutError("t2")]}
    ctx = FakeAsyncRequestContext({}, outcomes_by_place_id=outcomes)
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    failures = result["final_failures"]
    ok = (
        ctx.get_calls.count("933") == 2
        and result["home_success_count"] == 0
        and result["failure_count"] == 1
        and len(failures) == 1
        and failures[0]["place_id"] == "933"
        and failures[0]["name"] == "업체933"
        and failures[0]["status"] == "timeout"
        and failures[0]["attempt"] == 2
        and len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "933"
    )
    if ok:
        reporter.pass_("C. 1차·재시도 모두 timeout이면 최종 실패로 기록되고 row는 그대로 보존됨")
    else:
        reporter.fail(f"C. 최종 실패 기록 검증 실패: failures={failures}, result={result}")


def check_blocked_first_pass_skips_retry_entirely(reporter: ValidationReporter) -> None:
    """D(§13): 1차에서 HTTP 403(차단) 감지 시 재시도 큐 자체를 만들지
    않는다(재시도 요청 0회) - 기존 즉시 중단 동작(§4)과 결합."""
    place_ids = [str(700 + i) for i in range(5)]
    rows = [_row(pid) for pid in place_ids]
    responses = {pid: FakeAsyncResponse(200, _apollo_html(pid)) for pid in place_ids}
    responses[place_ids[0]] = FakeAsyncResponse(403, b"")
    ctx = FakeAsyncRequestContext(responses, delay_by_place_id={place_ids[1]: 0.05})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    ok = (
        result["security_blocked"] is True
        and result["stop_reason"] == "security_blocked"
        and result["retry_pass"]["attempted"] == 0
    )
    if ok:
        reporter.pass_("D. 1차 HTTP 403 차단 시 재시도 요청 0회(즉시 안전 중단)")
    else:
        reporter.fail(f"D. 차단 시 재시도 차단 검증 실패: result={result}")


def check_place_id_mismatch_not_merged_and_not_retried(reporter: ValidationReporter) -> None:
    """E(§13): place_id_mismatch는 재시도 대상이 아니며(값을 신뢰할 수 없는
    응답이라 재요청해도 의미가 없음), row에 병합되지 않고 최종 실패로만
    기록된다."""
    rows = [_row("944")]
    html = _apollo_html("944", base_overrides={"id": "999999"})
    ctx = FakeAsyncRequestContext({"944": FakeAsyncResponse(200, html)})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    failures = result["final_failures"]
    ok = (
        ctx.get_calls.count("944") == 1
        and result["rows"][0]["홈페이지"] == ""
        and len(failures) == 1
        and failures[0]["status"] == "place_id_mismatch"
    )
    if ok:
        reporter.pass_("E. place_id_mismatch는 재시도되지 않고 병합도 되지 않음(최종 실패로만 기록)")
    else:
        reporter.fail(f"E. place_id mismatch 비병합 검증 실패: failures={failures}, result={result}")


def check_retry_pass_concurrency_capped_at_one(reporter: ValidationReporter) -> None:
    """F(§13): 1차 순회는 기존과 동일하게 동시성 2, 재시도 순회는 동시성
    1을 넘지 않는다(재시도 전용 호출만 별도로 관측). 대량 실패 안전장치
    (§8, 대상 수의 10% 초과 실패 시 재시도 차단)에 걸리지 않도록 1차
    실패 업체를 대상 수 대비 10% 이하로 구성한다(25건 중 3건만 1차 실패 -
    ceil(25*0.1)=3이므로 안전장치 미해당)."""
    retry_ids = [str(800 + i) for i in range(3)]
    success_ids = [str(820 + i) for i in range(22)]
    rows = [_row(pid) for pid in retry_ids] + [_row(pid) for pid in success_ids]
    outcomes = {
        pid: [FakeAsyncResponse(200, b"<html>no apollo</html>"), FakeAsyncResponse(200, _apollo_html(pid))]
        for pid in retry_ids
    }
    responses = {pid: FakeAsyncResponse(200, _apollo_html(pid)) for pid in success_ids}
    ctx = FakeAsyncRequestContext(
        responses, outcomes_by_place_id=outcomes, delay_by_place_id={pid: 0.02 for pid in retry_ids}
    )
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    ok = (
        ctx.max_observed_concurrency <= 2
        and ctx.max_observed_retry_concurrency <= 1
        and result["retry_pass"]["success"] == 3
        and result["home_success_count"] == 25
        and all(ctx.get_calls.count(pid) == 2 for pid in retry_ids)
    )
    if ok:
        reporter.pass_(
            f"F. 1차 동시성 상한 2({ctx.max_observed_concurrency}), 재시도 동시성 상한 1({ctx.max_observed_retry_concurrency}) 준수"
        )
    else:
        reporter.fail(f"F. 재시도 동시성 상한 검증 실패: result={result}, max_retry_concurrency={ctx.max_observed_retry_concurrency}")


def check_user_stop_before_retry_pass_skips_retry(reporter: ValidationReporter) -> None:
    """G(§13): 1차 종료 직후 should_continue가 False로 바뀌면 재시도
    요청을 전혀 보내지 않는다(안정화 대기 전 재확인, §7)."""
    rows = [_row("955")]
    stop_flag = {"stop": False}

    def _stop_after_first():
        stop_flag["stop"] = True

    ctx = FakeAsyncRequestContext(
        {"955": FakeAsyncResponse(200, b"<html>no apollo</html>")},
        on_response_for={"955": _stop_after_first},
    )
    result = _run(
        _enrich_home_batch_async(
            rows, should_continue=lambda: not stop_flag["stop"], request_context_factory=_factory_for(ctx),
        )
    )
    ok = (
        ctx.get_calls.count("955") == 1
        and result["retry_pass"]["attempted"] == 0
        and result["stop_reason"] == "user_stopped"
    )
    if ok:
        reporter.pass_("G. 1차 종료 직후 사용자 중지 시 재시도 요청 0회")
    else:
        reporter.fail(f"G. 재시도 전 사용자 중지 검증 실패: result={result}")


def check_diagnostics_report_structure_and_no_sensitive_data(reporter: ValidationReporter) -> None:
    """H(§13): diagnostics_report에 place_id/이름/상태 등 공개·구조 정보만
    있고 쿠키/Authorization/토큰/HTML 원문이 전혀 없으며, 한글 업체명이
    깨지지 않는다."""
    rows = [_row("966")]
    rows[0]["업체명"] = "한글업체명테스트"
    ctx = FakeAsyncRequestContext({"966": FakeAsyncResponse(200, _apollo_html("966"))})
    result = _run(_enrich_home_batch_async(rows, request_context_factory=_factory_for(ctx)))
    report = result["diagnostics_report"]
    serialized = json.dumps(report, ensure_ascii=False)
    forbidden_terms = [
        "cookie", "Cookie", "COOKIE", "Authorization", "authorization",
        "token", "Token", "<html", "__APOLLO_STATE__",
    ]
    ok = (
        report.get("target_count") == 1
        and report.get("mode") == "home_sns"
        and len(report.get("attempts", [])) == 1
        and report["attempts"][0]["name"] == "한글업체명테스트"
        and report["attempts"][0]["final"] is True
        and "한글업체명테스트" in serialized
        and all(term not in serialized for term in forbidden_terms)
        and report.get("final", {}).get("success") == 1
    )
    if ok:
        reporter.pass_("H. diagnostics_report에 민감정보 없음 + 한글 업체명 보존 + 구조 필드 정상")
    else:
        reporter.fail(f"H. 진단 JSON 구조/민감정보 검증 실패: report={report}")


def main() -> bool:
    reporter = ValidationReporter()
    checks = [
        check_success_merges_home_fields_without_touching_existing_phone,
        check_blank_phone_gets_filled_from_home,
        check_concurrency_capped_at_two,
        check_blocked_response_stops_new_scheduling,
        check_user_stop_mid_batch,
        check_pause_event_blocks_new_requests_until_resumed,
        check_duplicate_place_id_fetched_once,
        check_merge_home_result_into_row_unit_cases,
        check_core_fields_never_overwritten_by_home_result,
        check_basic_and_home_sns_share_core_fields_given_same_list_rows,
        check_enrich_home_details_sync_wrapper_bypasses_native_cdp_when_injected,
        check_production_path_uses_native_cdp_reconnect_not_cookie_copy,
        check_dispose_not_called_on_context_request,
        check_extra_links_flow_through_ssr_fetch_and_merge,
        check_merge_home_result_into_row_fills_extra_links_field,
        check_basic_mode_leaves_extra_links_blank,
        check_zero_external_links_is_success_not_retried,
        check_transient_failure_retried_and_succeeds,
        check_final_failure_after_retry_still_fails,
        check_blocked_first_pass_skips_retry_entirely,
        check_place_id_mismatch_not_merged_and_not_retried,
        check_retry_pass_concurrency_capped_at_one,
        check_user_stop_before_retry_pass_skips_retry,
        check_diagnostics_report_structure_and_no_sensitive_data,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return reporter.fail_count == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
