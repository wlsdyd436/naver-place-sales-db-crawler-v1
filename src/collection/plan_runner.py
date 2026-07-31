# 이미 생성된 Collection Query Plan(jobs)을 실행하는 순수 orchestrator다.
#
# 이 모듈은 실제 Playwright/브라우저를 다루지 않는다. Query별 Collector가
# 제공하는 collect_query(job, per_query_limit) callback을 호출만 하고, 그
# 결과(rows/보안 신호)를 바탕으로 place_id 전역 중복 제거·target_count
# 도달·per-query 상한·필터 제외 통계 합산·CAPTCHA/429 안전 중단을 판단하는
# 계약만 담당한다(브라우저 구현 세부사항은 전달받은 Collector에 위임).
#
# CAPTCHA 우회/자동 해결/stealth/proxy는 이 모듈의 목적이 아니며 시도하지
# 않는다 - active_captcha_detected/status_429_seen 신호를 받으면 즉시
# 중단하고 그때까지의 부분 결과만 반환한다.
from types import SimpleNamespace

from src.collection.place_mapper import dedup_rows, should_stop_for_target
from src.collection.safety import SafetyReason

_SECURITY_BLOCK_MESSAGE = "보안 확인 또는 요청 제한이 감지되었습니다."


def run_collection_plan(
    jobs,
    *,
    per_query_limit,
    target_count,
    collected_at,
    collect_query,
    on_partial_save=None,
    on_security_block=None,
    seen=None,
    should_continue=None,
) -> dict:
    """jobs(검색 조합 목록)를 순서대로 collect_query에 위임 실행하는 순수 orchestrator.

    jobs: build_collection_queries()가 만든 job dict의 list(각 dict는 최소
    "query" 키를 가진다는 전제이며, 이 함수는 job 내용 자체를 해석하지 않고
    그대로 collect_query에 전달만 한다).

    collect_query(job, per_query_limit)는 다음 형태의 dict를 반환해야 한다:
      {"rows": [...], "active_captcha_detected": bool, "status_429_seen": bool,
       "navigation_error": bool, "navigation_error_message": str}
    navigation_error/navigation_error_message는 없어도 된다(WIRE-2A-B 이전
    collect_query와의 하위 호환 - 없으면 False/빈 문자열로 취급). rows의 각
    항목은 place_mapper.dedup_rows가 기대하는 형태(place_id 또는
    업체명 키를 가진 dict)여야 한다.

    seen은 여러 jobs에 걸쳐 공유되는 dedup 집합이다(호출자가 재사용하고
    싶으면 직접 만들어 전달, 아니면 이 함수가 새로 만든다).

    should_continue(선택, WIRE-2B-1): 인자 없이 bool을 반환하는 callable.
    각 job을 실행하기 직전에 호출해 False면 그 job의 collect_query를 호출하지
    않고 즉시 stop_reason="user_stopped"로 중단한다(target trim/보안 콜백과는
    무관 - on_security_block을 호출하지 않는다). None(기본값)이면 기존 동작
    그대로다.

    중단 판단 우선순위(매 job마다): 1) should_continue()가 False면 즉시
    user_stopped. 2) collect_query 실행 후 navigation_error면 즉시
    navigation_error(이 쿼리의 rows는 신규 누적하지 않고, CAPTCHA/429로
    오분류하지 않으며 on_security_block을 호출하지 않는다 - navigation_error가
    발생한 page는 신뢰하지 않으므로 다음 쿼리를 실행하지 않는다). 3) active
    CAPTCHA. 4) HTTP 429(3·4는 security_blocked/status_429 처리로 기존과
    동일). 5) 정상 rows를 global dedup에 반영. 6) target_count 도달 검사.
    7) 다음 job으로.

    collected_at은 이 함수에서 직접 사용하지 않는다(row 매핑은 collect_query/
    _map_item_to_row가 이미 끝낸 상태로 넘겨준다는 전제) - 호출부(향후 live
    collect_query 구현)가 collected_at을 필요로 할 수 있어 시그니처에만
    남겨둔다.

    반환 dict에 추가된 진단 필드: "duplicate_removed_count"(전체 job에 걸쳐
    dedup_rows가 실제로 걸러낸 행 수 누적), "review_filter_stats"(리뷰
    필터가 적용된 job이 하나라도 있으면 candidate/accepted/rejected_by_min/
    rejected_by_max/unknown을 job 간 합산한 dict, 없으면 None) - 둘 다
    collect_query가 반환하는 값을 그대로 신뢰하고 집계만 한다(plan_runner
    자체는 dedup/리뷰 판정 로직을 갖지 않는다).
    """
    if seen is None:
        seen = set()

    if not jobs:
        return {
            "rows": [],
            "executed_query_count": 0,
            "skipped_query_count": 0,
            "stop_reason": "empty_jobs",
            "before_trim_count": 0,
            "final_count": 0,
            "security_blocked": False,
            "status_429_seen": False,
            "navigation_error": False,
            "navigation_error_message": "",
            "rejected_rows": [],
            "duplicate_removed_count": 0,
            "review_filter_stats": None,
        }

    total_jobs = len(jobs)
    effective_target = target_count if target_count else 0

    rows: list = []
    rejected_rows: list = []
    executed_query_count = 0
    before_trim_count = 0
    security_blocked = False
    status_429_seen = False
    navigation_error = False
    navigation_error_message = ""
    stop_reason = None
    duplicate_removed_count = 0
    review_filter_stats = None

    for job in jobs:
        if should_continue is not None and not should_continue():
            stop_reason = "user_stopped"
            break

        result = collect_query(job, per_query_limit) or {}
        executed_query_count += 1
        rejected_rows.extend(result.get("rejected_rows") or [])

        if result.get("navigation_error"):
            navigation_error = True
            navigation_error_message = result.get("navigation_error_message") or ""
            stop_reason = "navigation_error"
            break

        raw_rows = result.get("rows") or []
        capped_rows = raw_rows[:per_query_limit] if per_query_limit else raw_rows
        deduped_rows = dedup_rows(capped_rows, seen)
        duplicate_removed_count += len(capped_rows) - len(deduped_rows)
        rows.extend(deduped_rows)
        before_trim_count = len(rows)

        job_review_stats = result.get("review_filter_stats")
        if job_review_stats is not None:
            if review_filter_stats is None:
                review_filter_stats = {"candidate": 0, "accepted": 0, "rejected_by_min": 0, "rejected_by_max": 0, "unknown": 0}
            for key in review_filter_stats:
                review_filter_stats[key] += job_review_stats.get(key, 0)

        captcha_detected = bool(result.get("active_captcha_detected"))
        this_status_429 = bool(result.get("status_429_seen"))
        if captcha_detected or this_status_429:
            status_429_seen = this_status_429
            security_blocked = True
            stop_reason = "status_429" if this_status_429 and not captcha_detected else "security_blocked"
            _try_notify_security_block(on_security_block)
            break

        if should_stop_for_target(len(rows), effective_target):
            stop_reason = "target_reached"
            break
    else:
        stop_reason = "queue_exhausted"

    final_rows = rows
    if stop_reason == "target_reached" and effective_target > 0:
        final_rows = rows[:effective_target]

    if stop_reason in ("security_blocked", "status_429"):
        _try_partial_save(on_partial_save, final_rows)

    return {
        "rows": final_rows,
        "executed_query_count": executed_query_count,
        "skipped_query_count": total_jobs - executed_query_count,
        "stop_reason": stop_reason,
        "before_trim_count": before_trim_count,
        "final_count": len(final_rows),
        "security_blocked": security_blocked,
        "status_429_seen": status_429_seen,
        "navigation_error": navigation_error,
        "navigation_error_message": navigation_error_message,
        "rejected_rows": rejected_rows,
        "duplicate_removed_count": duplicate_removed_count,
        "review_filter_stats": review_filter_stats,
    }


def _try_notify_security_block(on_security_block) -> None:
    """CAPTCHA/429 감지를 best-effort로 호출자에게 알린다."""
    if on_security_block is None:
        return
    decision = SimpleNamespace(
        reason=SafetyReason.CAPTCHA_OR_SECURITY_BLOCK,
        message=_SECURITY_BLOCK_MESSAGE,
    )
    try:
        on_security_block(decision)
    except Exception:
        # 콜백 실패가 부분 보존 반환 흐름을 깨서는 안 된다.
        pass


def _try_partial_save(on_partial_save, rows) -> None:
    """부분 저장 콜백을 best-effort로 시도한다. 실패해도 반환 흐름을 깨지 않는다."""
    if on_partial_save is None:
        return
    try:
        on_partial_save(list(rows))
    except Exception:
        pass
