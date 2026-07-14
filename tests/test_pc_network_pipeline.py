from pathlib import Path
import sys


# ARCH-300C WIRE-1: src/pc/network_pipeline.py 검증용 standalone 스크립트
# (live/Playwright 없음, fake collect_query 기반). run_collection_plan은 순수
# orchestrator이므로 이 테스트도 순수 함수 단위로만 검증한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.network_pipeline import run_collection_plan


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
    if result["rows"] == [] and result["stop_reason"] == "empty_jobs":
        reporter.pass_("empty_jobs: jobs=[]이면 rows=[], stop_reason=empty_jobs")
    else:
        reporter.fail(f"empty_jobs 결과가 예상과 다름: {result}")


def main() -> int:
    reporter = ValidationReporter()

    check_queue_exhausted(reporter)
    check_global_dedup(reporter)
    check_target_reached(reporter)
    check_per_query_limit(reporter)
    check_active_captcha_detected(reporter)
    check_status_429_seen(reporter)
    check_empty_jobs(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
