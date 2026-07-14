# ARCH-300C WIRE-1: Network/List 관찰 기반 수집을 위한 순수 orchestrator.
#
# 이 모듈은 실제 Playwright/브라우저를 다루지 않는다. collect_query(job,
# per_query_limit)를 주입받아 호출만 하고, 그 결과(rows/보안 신호)를 바탕으로
# dedup·target 도달·per-query 상한·CAPTCHA·429 안전 중단을 판단하는 계약만
# 담당한다(src/pc/pipeline.py의 collect_pc_full과 동일한 "오케스트레이션
# 계약" 원칙). WIRE-1 단계에서는 fake collector로만 검증하며, 실제 제품
# 경로(collect_pc_full/app.py/ui.py 수집 버튼)에는 아직 연결되지 않는다.
#
# CAPTCHA 우회/자동 해결/stealth/proxy는 이 모듈의 목적이 아니며 시도하지
# 않는다 - active_captcha_detected/status_429_seen 신호를 받으면 즉시
# 중단하고 그때까지의 부분 결과만 반환한다.
from types import SimpleNamespace

from src.pc.network_list_scraper import dedup_rows, should_stop_for_target
from src.pc.safety import SafetyReason

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
) -> dict:
    """jobs(검색 조합 목록)를 순서대로 collect_query에 위임 실행하는 순수 orchestrator.

    jobs: build_collection_queries()가 만든 job dict의 list(각 dict는 최소
    "query" 키를 가진다는 전제이며, 이 함수는 job 내용 자체를 해석하지 않고
    그대로 collect_query에 전달만 한다).

    collect_query(job, per_query_limit)는 다음 형태의 dict를 반환해야 한다:
      {"rows": [...], "active_captcha_detected": bool, "status_429_seen": bool}
    rows의 각 항목은 network_list_scraper.dedup_rows가 기대하는 형태(place_id
    또는 업체명 키를 가진 dict)여야 한다.

    seen은 여러 jobs에 걸쳐 공유되는 dedup 집합이다(호출자가 재사용하고
    싶으면 직접 만들어 전달, 아니면 이 함수가 새로 만든다).

    collected_at은 이 함수에서 직접 사용하지 않는다(row 매핑은 collect_query/
    _map_item_to_row가 이미 끝낸 상태로 넘겨준다는 전제) - 호출부(향후 live
    collect_query 구현)가 collected_at을 필요로 할 수 있어 시그니처에만
    남겨둔다.
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
        }

    total_jobs = len(jobs)
    effective_target = target_count if target_count else 0

    rows: list = []
    executed_query_count = 0
    before_trim_count = 0
    security_blocked = False
    status_429_seen = False
    stop_reason = None

    for job in jobs:
        result = collect_query(job, per_query_limit) or {}
        executed_query_count += 1

        raw_rows = result.get("rows") or []
        capped_rows = raw_rows[:per_query_limit] if per_query_limit else raw_rows
        rows.extend(dedup_rows(capped_rows, seen))
        before_trim_count = len(rows)

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
    }


def _try_notify_security_block(on_security_block) -> None:
    """CAPTCHA/429 감지를 best-effort로 호출자에게 알린다(pipeline.collect_pc_full과 동일 패턴)."""
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
