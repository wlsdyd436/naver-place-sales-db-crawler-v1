from pathlib import Path
import sys


# src/collection/plan_runner.py 검증용 standalone 스크립트
# (live/Playwright 없음, fake collect_query 기반). run_collection_plan은 순수
# orchestrator이므로 이 테스트도 순수 함수 단위로만 검증한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collection.plan_runner import run_collection_plan


class ValidationReporter:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0
        self.warn_count = 0

    def pass_(self, message: str) -> None:
        self.pass_count += 1
        print(f"[PASS] {message}")

    def fail(self, message: str) -> None:
        self.fail_count += 1
        print(f"[FAIL] {message}")

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print("검증 요약")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"WARN: {self.warn_count}")
        print(f"FINAL: {final}")
        print("====================")


def _row(place_id: str, name: str = "") -> dict:
    return {"place_id": place_id, "업체명": name or f"업체_{place_id}"}


def check_queue_exhausted(reporter: ValidationReporter) -> None:
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1"), _row("2")]}
        return {"rows": [_row("3")]}

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
    )
    if (
        result["stop_reason"] == "queue_exhausted"
        and result["executed_query_count"] == 2
        and result["skipped_query_count"] == 0
        and result["final_count"] == 3
    ):
        reporter.pass_("queue_exhausted: jobs 2개를 전부 소진하면 stop_reason=queue_exhausted, executed=2")
    else:
        reporter.fail(f"queue_exhausted 결과가 예상과 다름: {result}")


def check_global_dedup(reporter: ValidationReporter) -> None:
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        return {"rows": [_row("dup-1")]}

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
    )
    if result["final_count"] == 1 and len(result["rows"]) == 1:
        reporter.pass_("global dedup: job1/job2가 같은 place_id를 반환해도 최종 rows는 1개")
    else:
        reporter.fail(f"global dedup 결과가 예상과 다름: {result}")


def check_target_reached(reporter: ValidationReporter) -> None:
    jobs = [{"query": "q1"}, {"query": "q2"}, {"query": "q3"}]

    def fake_collect(job, per_query_limit):
        mapping = {
            "q1": [_row("1"), _row("2")],
            "q2": [_row("3"), _row("4"), _row("5")],
            "q3": [_row("6")],
        }
        return {"rows": mapping[job["query"]]}

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=3,
        collected_at="2026-07-14",
        collect_query=fake_collect,
    )
    if (
        result["final_count"] == 3
        and result["before_trim_count"] >= 3
        and result["stop_reason"] == "target_reached"
        and result["executed_query_count"] == 2
        and result["skipped_query_count"] == 1
    ):
        reporter.pass_("target_reached: target_count=3 도달 시 trim되고 남은 쿼리는 skipped로 집계됨")
    else:
        reporter.fail(f"target_reached 결과가 예상과 다름: {result}")


def check_per_query_limit(reporter: ValidationReporter) -> None:
    jobs = [{"query": "q1"}]
    seen_limits = []

    def fake_collect(job, per_query_limit):
        seen_limits.append(per_query_limit)
        rows = [_row(str(i)) for i in range(10)]
        return {"rows": rows}

    result = run_collection_plan(
        jobs,
        per_query_limit=3,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
    )
    if result["final_count"] == 3 and seen_limits == [3]:
        reporter.pass_("per_query_limit: collect_query가 상한보다 많이 반환해도 3건으로 cap됨")
    else:
        reporter.fail(f"per_query_limit 결과가 예상과 다름: {result}, seen_limits={seen_limits}")


def check_active_captcha_detected(reporter: ValidationReporter) -> None:
    jobs = [{"query": "q1"}, {"query": "q2"}]
    captured = []

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1")], "active_captcha_detected": True}
        return {"rows": [_row("2")]}

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
        on_security_block=lambda decision: captured.append(decision),
    )
    if (
        result["stop_reason"] == "security_blocked"
        and result["security_blocked"] is True
        and result["executed_query_count"] == 1
        and len(result["rows"]) == 1
        and len(captured) == 1
    ):
        reporter.pass_("active_captcha_detected: 즉시 중단 + on_security_block 호출 + 부분 rows 반환")
    else:
        reporter.fail(f"active_captcha_detected 결과가 예상과 다름: {result}, captured={captured}")


def check_status_429_seen(reporter: ValidationReporter) -> None:
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1")], "status_429_seen": True}
        return {"rows": [_row("2")]}

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
    )
    if (
        result["stop_reason"] in ("status_429", "security_blocked")
        and result["status_429_seen"] is True
        and result["executed_query_count"] == 1
        and len(result["rows"]) == 1
    ):
        reporter.pass_("status_429_seen: 즉시 중단 + 부분 rows 반환")
    else:
        reporter.fail(f"status_429_seen 결과가 예상과 다름: {result}")


def check_navigation_error_stops_immediately(reporter: ValidationReporter) -> None:
    """WIRE-2B-1: 두 번째 job에서 navigation_error가 발생하면 즉시 중단하고
    첫 번째 job의 부분 rows만 유지한다(CAPTCHA/429로 오분류하지 않음)."""
    jobs = [{"query": "q1"}, {"query": "q2"}, {"query": "q3"}]
    captured = []

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1")]}
        if job["query"] == "q2":
            return {
                "rows": [],
                "navigation_error": True,
                "navigation_error_message": "TargetClosedError: Target closed",
            }
        raise AssertionError("navigation_error 이후 q3는 실행되면 안 됨")

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
        on_security_block=lambda decision: captured.append(decision),
    )
    if (
        result["stop_reason"] == "navigation_error"
        and result["navigation_error"] is True
        and result["navigation_error_message"] == "TargetClosedError: Target closed"
        and result["executed_query_count"] == 2
        and result["skipped_query_count"] == 1
        and len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "1"
        and result["security_blocked"] is False
        and result["status_429_seen"] is False
        and len(captured) == 0
    ):
        reporter.pass_("navigation_error: 즉시 중단, 첫 job 부분 rows 유지, on_security_block 미호출")
    else:
        reporter.fail(f"navigation_error 결과가 예상과 다름: {result}, captured={captured}")


def check_navigation_error_field_missing_is_backward_compatible(reporter: ValidationReporter) -> None:
    """WIRE-2B-1 이전 collect_query(navigation_error 필드 없음)는 기존 동작 그대로여야 한다."""
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1")]}
        return {"rows": [_row("2")]}

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
    )
    if (
        result["stop_reason"] == "queue_exhausted"
        and result["navigation_error"] is False
        and result["navigation_error_message"] == ""
        and result["final_count"] == 2
    ):
        reporter.pass_("navigation_error 필드 없는 기존 collector: 기존 queue_exhausted 동작 그대로 유지됨")
    else:
        reporter.fail(f"하위 호환 결과가 예상과 다름: {result}")


def check_should_continue_false_from_start(reporter: ValidationReporter) -> None:
    """WIRE-2B-1: should_continue가 처음부터 False면 collect_query를 한 번도 호출하지 않는다."""
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        raise AssertionError("should_continue=False인데 collect_query가 호출됨")

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
        should_continue=lambda: False,
    )
    if (
        result["stop_reason"] == "user_stopped"
        and result["executed_query_count"] == 0
        and result["skipped_query_count"] == 2
        and result["rows"] == []
    ):
        reporter.pass_("should_continue=False(처음부터): collect_query 0회 호출, stop_reason=user_stopped")
    else:
        reporter.fail(f"should_continue=False(처음부터) 결과가 예상과 다름: {result}")


def check_should_continue_false_after_first_job(reporter: ValidationReporter) -> None:
    """WIRE-2B-1: 첫 job 실행 후 should_continue가 False가 되면 두 번째 job은 호출되지 않는다."""
    jobs = [{"query": "q1"}, {"query": "q2"}]
    call_state = {"count": 0}

    def fake_should_continue():
        call_state["count"] += 1
        return call_state["count"] <= 1

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1")]}
        raise AssertionError("should_continue=False 이후 q2는 실행되면 안 됨")

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
        should_continue=fake_should_continue,
    )
    if (
        result["stop_reason"] == "user_stopped"
        and result["executed_query_count"] == 1
        and result["skipped_query_count"] == 1
        and len(result["rows"]) == 1
        and result["rows"][0]["place_id"] == "1"
    ):
        reporter.pass_("should_continue=False(첫 job 이후): 첫 job 결과 유지, 두 번째 job 미실행, skipped_query_count 정상")
    else:
        reporter.fail(f"should_continue=False(첫 job 이후) 결과가 예상과 다름: {result}")


def check_should_continue_none_keeps_existing_behavior(reporter: ValidationReporter) -> None:
    """WIRE-2B-1: should_continue=None을 명시적으로 전달해도 기존 queue_exhausted 동작이 유지된다."""
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1"), _row("2")]}
        return {"rows": [_row("3")]}

    result = run_collection_plan(
        jobs,
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
        should_continue=None,
    )
    if (
        result["stop_reason"] == "queue_exhausted"
        and result["executed_query_count"] == 2
        and result["skipped_query_count"] == 0
        and result["final_count"] == 3
    ):
        reporter.pass_("should_continue=None: 기존 queue_exhausted 동작 그대로 유지됨")
    else:
        reporter.fail(f"should_continue=None 결과가 예상과 다름: {result}")


def check_empty_jobs(reporter: ValidationReporter) -> None:
    def fake_collect(job, per_query_limit):
        raise AssertionError("empty_jobs 케이스에서는 collect_query가 호출되면 안 됨")

    result = run_collection_plan(
        [],
        per_query_limit=10,
        target_count=1000,
        collected_at="2026-07-14",
        collect_query=fake_collect,
    )
    if result["rows"] == [] and result["stop_reason"] == "empty_jobs" and result["duplicate_removed_count"] == 0 and result["review_filter_stats"] is None:
        reporter.pass_("empty_jobs: jobs=[]이면 rows=[], stop_reason=empty_jobs, duplicate_removed_count=0, review_filter_stats=None")
    else:
        reporter.fail(f"empty_jobs 결과가 예상과 다름: {result}")


def check_duplicate_removed_count_zero_when_no_duplicates(reporter: ValidationReporter) -> None:
    """NETWORK-CONTROLS-1: 중복이 실제로 없으면 duplicate_removed_count=0을
    그대로 표시해야 한다(항상 0으로 고정하던 기존 UI 버그와 달리, 실측값이
    우연히 0인 경우도 정확히 구분돼야 함)."""
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {"rows": [_row("1"), _row("2")]}
        return {"rows": [_row("3")]}

    result = run_collection_plan(
        jobs, per_query_limit=10, target_count=1000, collected_at="2026-07-14", collect_query=fake_collect,
    )
    if result["duplicate_removed_count"] == 0:
        reporter.pass_("duplicate_removed_count: 중복이 없으면 0")
    else:
        reporter.fail(f"duplicate_removed_count 결과가 예상과 다름: {result}")


def check_duplicate_removed_count_within_query(reporter: ValidationReporter) -> None:
    """한 job의 rows 안에서 같은 place_id가 반복되면(Query 내부 중복) 그
    건수만큼 duplicate_removed_count에 반영돼야 한다."""
    jobs = [{"query": "q1"}]

    def fake_collect(job, per_query_limit):
        return {"rows": [_row("1"), _row("1"), _row("1"), _row("2")]}

    result = run_collection_plan(
        jobs, per_query_limit=10, target_count=1000, collected_at="2026-07-14", collect_query=fake_collect,
    )
    if result["final_count"] == 2 and result["duplicate_removed_count"] == 2:
        reporter.pass_("duplicate_removed_count: Query 내부 중복(place_id '1' 2회 초과분)이 정확히 집계됨")
    else:
        reporter.fail(f"duplicate_removed_count(Query 내부) 결과가 예상과 다름: {result}")


def check_duplicate_removed_count_across_queries(reporter: ValidationReporter) -> None:
    """서로 다른 job이 같은 place_id를 반환하면(Query 간 전역 중복) 그
    건수만큼 duplicate_removed_count에 반영돼야 한다."""
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        return {"rows": [_row("dup-1")]}

    result = run_collection_plan(
        jobs, per_query_limit=10, target_count=1000, collected_at="2026-07-14", collect_query=fake_collect,
    )
    if result["final_count"] == 1 and result["duplicate_removed_count"] == 1:
        reporter.pass_("duplicate_removed_count: Query 간 전역 중복(job1/job2 동일 place_id)이 정확히 집계됨")
    else:
        reporter.fail(f"duplicate_removed_count(Query 간) 결과가 예상과 다름: {result}")


def check_review_filter_stats_aggregated_across_jobs(reporter: ValidationReporter) -> None:
    """collect_query가 반환하는 review_filter_stats를 job 여러 개에 걸쳐
    정확히 합산해야 한다(plan_runner는 판정 로직 없이 집계만 함)."""
    jobs = [{"query": "q1"}, {"query": "q2"}]

    def fake_collect(job, per_query_limit):
        if job["query"] == "q1":
            return {
                "rows": [_row("1")],
                "review_filter_stats": {"candidate": 5, "accepted": 1, "rejected_by_min": 2, "rejected_by_max": 1, "unknown": 1},
            }
        return {
            "rows": [_row("2")],
            "review_filter_stats": {"candidate": 3, "accepted": 1, "rejected_by_min": 1, "rejected_by_max": 0, "unknown": 1},
        }

    result = run_collection_plan(
        jobs, per_query_limit=10, target_count=1000, collected_at="2026-07-14", collect_query=fake_collect,
    )
    expected = {"candidate": 8, "accepted": 2, "rejected_by_min": 3, "rejected_by_max": 1, "unknown": 2}
    if result["review_filter_stats"] == expected:
        reporter.pass_("review_filter_stats: job 2개의 통계가 정확히 합산됨")
    else:
        reporter.fail(f"review_filter_stats 합산 결과가 예상과 다름: {result['review_filter_stats']} (expected {expected})")


def check_review_filter_stats_none_when_not_reported(reporter: ValidationReporter) -> None:
    """collect_query가 review_filter_stats를 아예 반환하지 않으면(리뷰 필터
    비활성 job) 최종 결과도 None이어야 한다(하위 호환 - 기존 fake collector도
    그대로 동작해야 함)."""
    jobs = [{"query": "q1"}]

    def fake_collect(job, per_query_limit):
        return {"rows": [_row("1")]}

    result = run_collection_plan(
        jobs, per_query_limit=10, target_count=1000, collected_at="2026-07-14", collect_query=fake_collect,
    )
    if result["review_filter_stats"] is None:
        reporter.pass_("review_filter_stats: 어떤 job도 반환하지 않으면 None 유지")
    else:
        reporter.fail(f"review_filter_stats가 None이어야 하는데: {result['review_filter_stats']}")


def check_security_diagnostics_propagated_from_job_result(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG 사전 조건: collect_query 결과의 security_diagnostics가
    run_collection_plan 최종 반환에 그대로 전달돼야 ui.py가 볼 수 있다."""
    jobs = [{"query": "q1"}]
    diag = {
        "json_saved": True, "json_path": "C:\\logs\\diagnostics\\x.json", "json_error": None,
        "screenshot_saved": True, "screenshot_path": "C:\\logs\\diagnostics\\x.png", "screenshot_error": None,
    }

    def fake_collect(job, per_query_limit):
        return {"rows": [_row("1")], "security_diagnostics": diag}

    result = run_collection_plan(
        jobs, per_query_limit=10, target_count=1000, collected_at="2026-08-03", collect_query=fake_collect,
    )
    if result.get("security_diagnostics") == diag:
        reporter.pass_("security_diagnostics: job 결과가 최종 반환 dict에 그대로 전달됨")
    else:
        reporter.fail(f"security_diagnostics 전달 실패: {result.get('security_diagnostics')}")


def check_security_diagnostics_none_when_no_captcha(reporter: ValidationReporter) -> None:
    """CAPTCHA가 없어 job 결과에 security_diagnostics 키 자체가 없으면(기존
    fake collector와도 하위 호환) 최종 결과도 None이어야 한다."""
    jobs = [{"query": "q1"}]

    def fake_collect(job, per_query_limit):
        return {"rows": [_row("1")]}

    result = run_collection_plan(
        jobs, per_query_limit=10, target_count=1000, collected_at="2026-08-03", collect_query=fake_collect,
    )
    if result.get("security_diagnostics") is None:
        reporter.pass_("security_diagnostics: CAPTCHA 없으면 None 유지(하위 호환)")
    else:
        reporter.fail(f"security_diagnostics가 None이어야 하는데: {result.get('security_diagnostics')}")


def check_security_diagnostics_empty_jobs_is_none(reporter: ValidationReporter) -> None:
    result = run_collection_plan(
        [], per_query_limit=10, target_count=1000, collected_at="2026-08-03", collect_query=lambda j, p: {"rows": []},
    )
    if result.get("security_diagnostics") is None:
        reporter.pass_("security_diagnostics: empty_jobs 경로도 None")
    else:
        reporter.fail(f"empty_jobs 경로 security_diagnostics 이상: {result.get('security_diagnostics')}")


def main() -> int:
    reporter = ValidationReporter()

    check_queue_exhausted(reporter)
    check_global_dedup(reporter)
    check_target_reached(reporter)
    check_per_query_limit(reporter)
    check_active_captcha_detected(reporter)
    check_status_429_seen(reporter)
    check_navigation_error_stops_immediately(reporter)
    check_navigation_error_field_missing_is_backward_compatible(reporter)
    check_should_continue_false_from_start(reporter)
    check_should_continue_false_after_first_job(reporter)
    check_should_continue_none_keeps_existing_behavior(reporter)
    check_empty_jobs(reporter)
    check_duplicate_removed_count_zero_when_no_duplicates(reporter)
    check_duplicate_removed_count_within_query(reporter)
    check_duplicate_removed_count_across_queries(reporter)
    check_review_filter_stats_aggregated_across_jobs(reporter)
    check_review_filter_stats_none_when_not_reported(reporter)
    check_security_diagnostics_propagated_from_job_result(reporter)
    check_security_diagnostics_none_when_no_captcha(reporter)
    check_security_diagnostics_empty_jobs_is_none(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
