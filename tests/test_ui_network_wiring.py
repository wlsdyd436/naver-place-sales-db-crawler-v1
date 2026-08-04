from pathlib import Path
import sys
import threading
from types import SimpleNamespace


# ARCH-300C WIRE-2B-2/2C-1: src.ui._run_network_pipeline 검증용 standalone
# 스크립트(실제 CTk 창/Tk mainloop/Playwright/네이버/실제 파일 저장 없음).
# collector_factory/orchestrator/excel_exporter를 fake로 주입해 UI 작업 큐가
# run_collection_plan + Excel 저장에 어떻게 연결되는지만 검증한다. 실제
# .xlsx 파일을 만드는 통합 검증은 tests/test_ui_network_export.py가 담당한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import ui


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


def _make_app():
    # Tk __init__/mainloop 없이 메서드만 호출하기 위해 __new__로 인스턴스만 만든다
    # (test_ui_pc_full_wiring.py와 동일 패턴). log/set_status는 self.after 없이
    # 바로 리스트에 기록하도록 교체한다.
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)
    app.stop_event = threading.Event()
    app.pause_event = threading.Event()
    logs: list = []
    statuses: list = []
    app.log = lambda message: logs.append(message)
    app.set_status = lambda message: statuses.append(message)
    app.after = lambda delay, func, *args: func(*args)
    app.duplicate_removed_var = SimpleNamespace(set=lambda value: None)
    return app, logs, statuses


class FakeNetworkCollector:
    """ApolloFirstListCollector와 동일한 계약(컨텍스트 매니저 + collect_query)만
    흉내내는 fake. 실제 Playwright/브라우저는 전혀 다루지 않는다."""

    def __init__(self, collected_at):
        self.collected_at = collected_at
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exit_count += 1
        return False

    def collect_query(self, job, per_query_limit):
        raise AssertionError("collect_query는 fake orchestrator를 통해서만 참조되어야 하며 직접 호출되면 안 됨")


class FakeCollectorFactory:
    """collector_factory(collected_at=...) 호출을 기록하고 FakeNetworkCollector를 반환."""

    def __init__(self):
        self.calls: list = []
        self.instances: list = []

    def __call__(self, *, collected_at, pause_event=None, stop_event=None):
        self.calls.append(collected_at)
        instance = FakeNetworkCollector(collected_at)
        self.instances.append(instance)
        return instance


class FakeExporter:
    """export_places_to_excel과 동일한 시그니처(merged, mobile, pc, output_path)만
    흉내내는 fake. 실제 파일을 전혀 만들지 않는다."""

    def __init__(self, *, raise_error: Exception | None = None, return_path: str | None = None):
        self.calls: list = []
        self._raise_error = raise_error
        self._return_path = return_path

    def __call__(self, merged_data, mobile_data, pc_data, output_path):
        self.calls.append({
            "merged_data": merged_data,
            "mobile_data": mobile_data,
            "pc_data": pc_data,
            "output_path": output_path,
        })
        if self._raise_error is not None:
            raise self._raise_error
        return self._return_path or output_path


def _fake_rows(n: int) -> list:
    return [{"place_id": str(i), "업체명": f"업체{i}"} for i in range(n)]


def _make_fake_orchestrator(result: dict):
    calls: list = []

    def fake_orchestrator(jobs, **kwargs):
        calls.append({"jobs": jobs, **kwargs})
        return result

    return fake_orchestrator, calls


def _base_result(**overrides) -> dict:
    result = {
        "rows": [],
        "executed_query_count": 1,
        "skipped_query_count": 0,
        "stop_reason": "queue_exhausted",
        "before_trim_count": 0,
        "final_count": 0,
        "security_blocked": False,
        "status_429_seen": False,
        "navigation_error": False,
        "navigation_error_message": "",
    }
    result.update(overrides)
    return result


def check_run_network_pipeline_passes_expected_arguments(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    result = _base_result(stop_reason="queue_exhausted", final_count=3, executed_query_count=2)
    fake_orchestrator, calls = _make_fake_orchestrator(result)
    query_queue = [{"query": "q1"}, {"query": "q2"}]

    returned = app._run_network_pipeline(
        query_queue, 30, 300, "output/naver_place_network_db.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    if not calls:
        reporter.fail("orchestrator가 호출되지 않음")
        return
    call = calls[0]
    collector = factory.instances[0]
    expected = dict(result, exported=False, export_path="", export_error=False, export_error_message="")
    ok = (
        call["jobs"] == query_queue
        and call["per_query_limit"] == 30
        and call["target_count"] == 300
        and call["collected_at"] == factory.calls[0]
        and call["collect_query"] == collector.collect_query
        and callable(call["should_continue"])
        and call["on_security_block"] == app._note_security_block
        and returned == expected
        and exporter.calls == []
    )
    if ok:
        reporter.pass_("인자 전달: query_queue/per_query_limit/target_count/collected_at/collect_query/should_continue/on_security_block이 정확히 전달됨(rows=0이라 exporter 미호출)")
    else:
        reporter.fail(f"인자 전달 결과가 예상과 다름: call={call}, returned={returned}")


def check_collector_lifecycle(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result()
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=FakeExporter(),
    )

    collector = factory.instances[0] if factory.instances else None
    ok = (
        len(factory.calls) == 1
        and collector is not None
        and collector.enter_count == 1
        and collector.exit_count == 1
    )
    if ok:
        reporter.pass_("collector 생명주기: collector_factory/__enter__/__exit__가 각각 정확히 1회 호출됨")
    else:
        reporter.fail(f"collector 생명주기 결과가 예상과 다름: factory.calls={factory.calls}, collector={collector}")


def check_export_called_with_correct_arguments(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2C-1: rows가 있으면 exporter에
    (merged=result rows, mobile=[], pc=[], output_path)로 정확히 1회 호출된다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _fake_rows(3)
    result = _base_result(stop_reason="queue_exhausted", final_count=3, rows=rows)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "output/naver_place_network_db.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        len(exporter.calls) == 1
        and exporter.calls[0]["merged_data"] == rows
        and exporter.calls[0]["mobile_data"] == []
        and exporter.calls[0]["pc_data"] == []
        and exporter.calls[0]["output_path"] == "output/naver_place_network_db.xlsx"
    )
    if ok:
        reporter.pass_("정상 저장 인자: merged=rows/mobile=[]/pc=[]/output_path가 정확히 전달되고 exporter 1회 호출됨")
    else:
        reporter.fail(f"정상 저장 인자 결과가 예상과 다름: calls={exporter.calls}")


def check_target_reached_reflected_in_status(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _fake_rows(3)
    result = _base_result(stop_reason="target_reached", final_count=3, rows=rows, executed_query_count=17, skipped_query_count=7)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    returned = app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        statuses
        and statuses[-1] == "전체 목표 개수에 도달했습니다. 3개를 저장했습니다."
        and any("final_count=3" in message for message in logs)
        and returned["exported"] is True
        and returned["export_path"] == "out.xlsx"
        and len(exporter.calls) == 1
    )
    if ok:
        reporter.pass_("target_reached: 저장 성공 문구(N개를 저장했습니다.) + exported=True + exporter 1회 호출")
    else:
        reporter.fail(f"target_reached 결과가 예상과 다름: statuses={statuses}, logs={logs}, returned={returned}")


def check_queue_exhausted_under_target_shows_shortfall(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _fake_rows(50)
    result = _base_result(stop_reason="queue_exhausted", final_count=50, rows=rows, executed_query_count=4)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = statuses and statuses[-1] == "선택한 지역 수집이 완료되었습니다. 목표에는 미달했으며 50개를 저장했습니다."
    if ok:
        reporter.pass_("queue_exhausted(목표 미달): 미달 + 저장 개수 문구가 상태에 반영됨")
    else:
        reporter.fail(f"queue_exhausted 목표 미달 결과가 예상과 다름: statuses={statuses}")


def check_navigation_error_partial_save_not_captcha(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    long_message = "TargetClosedError: " + ("x" * 300)
    rows = _fake_rows(1)
    result = _base_result(
        stop_reason="navigation_error", final_count=1, rows=rows,
        navigation_error=True, navigation_error_message=long_message,
    )
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        statuses
        and statuses[-1] == "브라우저 페이지 오류로 수집을 중단했습니다. 현재까지 1개를 저장했습니다."
        and "보안" not in statuses[-1]
        and "CAPTCHA" not in statuses[-1]
        and not any(long_message in message for message in logs)
        and any("navigation_error 상세" in message for message in logs)
        and len(exporter.calls) == 1
    )
    if ok:
        reporter.pass_("navigation_error 부분 저장: 브라우저 오류 문구(보안 확인 아님) + 이전 쿼리 rows 저장 + 전체 메시지 미노출")
    else:
        reporter.fail(f"navigation_error 결과가 예상과 다름: statuses={statuses}, logs={logs}")


def check_user_stopped_partial_save(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _fake_rows(1)
    result = _base_result(stop_reason="user_stopped", final_count=1, rows=rows, executed_query_count=1, skipped_query_count=1)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}, {"query": "q2"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        statuses
        and statuses[-1] == "사용자가 수집을 중단했습니다. 현재까지 1개를 저장했습니다."
        and len(exporter.calls) == 1
    )
    if ok:
        reporter.pass_("user_stopped 부분 저장: 이전 rows가 저장되고 사용자 중단 문구가 반영됨")
    else:
        reporter.fail(f"user_stopped 결과가 예상과 다름: statuses={statuses}")


def check_security_blocked_partial_save(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _fake_rows(2)
    result = _base_result(stop_reason="security_blocked", final_count=2, rows=rows, security_blocked=True)
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    call = calls[0] if calls else {}
    ok = (
        call.get("on_security_block") == app._note_security_block
        and statuses
        and statuses[-1] == "보안 확인이 감지되어 수집을 중단했습니다. 현재까지 2개를 저장했습니다."
        and len(exporter.calls) == 1
    )
    if ok:
        reporter.pass_("security_blocked 부분 저장: on_security_block 콜백 전달 + 이전 rows 1회 저장 + 부분 저장 문구")
    else:
        reporter.fail(f"security_blocked 결과가 예상과 다름: call={call}, statuses={statuses}, exporter.calls={exporter.calls}")


def check_status_429_partial_save(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _fake_rows(4)
    result = _base_result(stop_reason="status_429", final_count=4, rows=rows, status_429_seen=True, security_blocked=True)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        statuses
        and statuses[-1] == "요청 제한이 감지되어 수집을 중단했습니다. 현재까지 4개를 저장했습니다."
        and len(exporter.calls) == 1
    )
    if ok:
        reporter.pass_("status_429 부분 저장: 이전 rows가 1회 저장되고 요청 제한 문구가 반영됨")
    else:
        reporter.fail(f"status_429 결과가 예상과 다름: statuses={statuses}, exporter.calls={exporter.calls}")


def check_security_diagnostics_json_and_png_logged(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-1: orchestrator 결과의 security_diagnostics가 있으면
    기존 self.log(callback)로 JSON/PNG 경로가 정확히 1회씩 표시된다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    diag = {
        "json_saved": True, "json_path": r"C:\logs\diagnostics\x.json", "json_error": None,
        "screenshot_saved": True, "screenshot_path": r"C:\logs\diagnostics\x.png", "screenshot_error": None,
    }
    result = _base_result(
        stop_reason="security_blocked", final_count=1, rows=_fake_rows(1),
        security_blocked=True, security_diagnostics=diag,
    )
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    json_line = r"[진단] 보안 차단 정보 저장: C:\logs\diagnostics\x.json"
    png_line = r"[진단] CAPTCHA 화면 저장: C:\logs\diagnostics\x.png"
    ok = logs.count(json_line) == 1 and logs.count(png_line) == 1
    if ok:
        reporter.pass_("GUI-DIAG-LOG-1. security_diagnostics의 JSON/PNG 경로가 기존 log callback으로 정확히 1회씩 표시됨")
    else:
        reporter.fail(f"GUI-DIAG-LOG-1 실패: logs={logs}")


def check_security_diagnostics_png_failure_logged(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-2: PNG 저장 실패 시 JSON 성공 로그 + PNG 실패 로그가 표시된다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    diag = {
        "json_saved": True, "json_path": r"C:\logs\diagnostics\x.json", "json_error": None,
        "screenshot_saved": False, "screenshot_path": None, "screenshot_error": "RuntimeError: boom",
    }
    result = _base_result(
        stop_reason="security_blocked", final_count=1, rows=_fake_rows(1),
        security_blocked=True, security_diagnostics=diag,
    )
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        r"[진단] 보안 차단 정보 저장: C:\logs\diagnostics\x.json" in logs
        and "[진단] CAPTCHA 화면 저장 실패: RuntimeError: boom" in logs
    )
    if ok:
        reporter.pass_("GUI-DIAG-LOG-2. PNG 실패 시 JSON 성공 로그 + PNG 실패 로그가 함께 표시됨")
    else:
        reporter.fail(f"GUI-DIAG-LOG-2 실패: logs={logs}")


def check_security_diagnostics_json_failure_logged(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-3: JSON 저장 자체가 실패하면 실패 로그가 표시되고,
    수집 결과의 security_blocked=True는 그대로 유지된다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    diag = {
        "json_saved": False, "json_path": None, "json_error": "OSError: disk full",
        "screenshot_saved": False, "screenshot_path": None, "screenshot_error": None,
    }
    result = _base_result(
        stop_reason="security_blocked", final_count=1, rows=_fake_rows(1),
        security_blocked=True, security_diagnostics=diag,
    )
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    returned = app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        "[진단] 보안 차단 정보 저장 실패: OSError: disk full" in logs
        and returned.get("security_blocked") is True
    )
    if ok:
        reporter.pass_("GUI-DIAG-LOG-3. JSON 저장 실패 로그 표시 + security_blocked=True 결과 불변")
    else:
        reporter.fail(f"GUI-DIAG-LOG-3 실패: logs={logs}, returned={returned}")


def check_normal_run_no_security_diagnostics_logs(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-4: CAPTCHA가 없는 정상 실행(security_diagnostics=None)이면
    진단 관련 로그가 0회다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    result = _base_result(stop_reason="queue_exhausted", final_count=1, rows=_fake_rows(1))
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    diag_logs = [message for message in logs if message.startswith("[진단]")]
    if diag_logs == []:
        reporter.pass_("GUI-DIAG-LOG-4. 정상 실행(CAPTCHA 없음)은 진단 로그 0회")
    else:
        reporter.fail(f"GUI-DIAG-LOG-4 실패: 예상치 못한 진단 로그={diag_logs}")


def check_security_diagnostics_malformed_does_not_crash_pipeline(reporter: ValidationReporter) -> None:
    """GUI-DIAG-LOG-7 관련: security_diagnostics가 dict가 아닌 잘못된 값이어도
    _run_network_pipeline은 예외를 던지지 않고 정상적으로 결과를 반환한다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    result = _base_result(
        stop_reason="security_blocked", final_count=1, rows=_fake_rows(1),
        security_blocked=True, security_diagnostics="malformed-not-a-dict",
    )
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    try:
        returned = app._run_network_pipeline(
            [{"query": "q1"}], 30, 300, "out.xlsx",
            collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
        )
    except Exception as exc:
        reporter.fail(f"GUI-DIAG-LOG-7 실패: malformed security_diagnostics로 예외 전파됨: {exc!r}")
        return
    if returned.get("security_blocked") is True:
        reporter.pass_("GUI-DIAG-LOG-7. malformed security_diagnostics가 있어도 예외 없이 정상 반환(security_blocked 불변)")
    else:
        reporter.fail(f"GUI-DIAG-LOG-7 실패: returned={returned}")


def check_no_double_save_for_security_and_429(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2C-1: on_partial_save 콜백과 종료 후 저장을 동시에 쓰지
    않으므로, security_blocked/status_429에서도 exporter는 정확히 1회만
    호출되어야 한다(이중 저장 방지)."""
    for stop_reason, extra in (
        ("security_blocked", {"security_blocked": True}),
        ("status_429", {"status_429_seen": True, "security_blocked": True}),
    ):
        app, logs, statuses = _make_app()
        factory = FakeCollectorFactory()
        exporter = FakeExporter()
        rows = _fake_rows(2)
        result = _base_result(stop_reason=stop_reason, final_count=2, rows=rows, **extra)
        fake_orchestrator, calls = _make_fake_orchestrator(result)

        app._run_network_pipeline(
            [{"query": "q1"}], 30, 300, "out.xlsx",
            collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
        )

        if calls[0].get("on_partial_save") is not None:
            reporter.fail(f"{stop_reason}: run_collection_plan에 on_partial_save가 전달됨(이중 저장 위험)")
            return
        if len(exporter.calls) != 1:
            reporter.fail(f"{stop_reason}: exporter 호출 횟수가 1이 아님({len(exporter.calls)})")
            return

    reporter.pass_("이중 저장 방지: security_blocked/status_429 모두 on_partial_save 미사용 + exporter 정확히 1회 호출")


def check_zero_rows_no_export_no_file_creation(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2C-1: 정상 실행했지만 최종 결과가 0건이면 exporter를
    호출하지 않고, "저장할 결과가 없습니다." 문구를 사용한다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    result = _base_result(stop_reason="queue_exhausted", final_count=0, rows=[])
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    returned = app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        exporter.calls == []
        and returned["exported"] is False
        and returned["export_error"] is False
        and returned["export_path"] == ""
        and statuses
        and statuses[-1] == "저장할 결과가 없습니다."
    )
    if ok:
        reporter.pass_("rows 0건: exporter 0회 호출, 파일 생성 시도 없음, '저장할 결과가 없습니다.' 문구")
    else:
        reporter.fail(f"rows 0건 결과가 예상과 다름: exporter.calls={exporter.calls}, returned={returned}, statuses={statuses}")


def check_empty_jobs_no_export(reporter: ValidationReporter) -> None:
    """empty_jobs도 rows가 없으므로 동일하게 저장하지 않는다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    result = _base_result(stop_reason="empty_jobs", final_count=0, rows=[])
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = exporter.calls == [] and statuses and statuses[-1] == "저장할 결과가 없습니다."
    if ok:
        reporter.pass_("empty_jobs: exporter 미호출, '저장할 결과가 없습니다.' 문구")
    else:
        reporter.fail(f"empty_jobs 결과가 예상과 다름: exporter.calls={exporter.calls}, statuses={statuses}")


def check_exporter_exception_marks_export_error(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2C-1: exporter가 예외를 던지면 exported=False,
    export_error=True로 기록하고, 성공 문구를 절대 보여주지 않는다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter(raise_error=RuntimeError("disk full"))
    rows = _fake_rows(2)
    result = _base_result(stop_reason="queue_exhausted", final_count=2, rows=rows)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    returned = app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
    )

    ok = (
        len(exporter.calls) == 1
        and returned["exported"] is False
        and returned["export_error"] is True
        and "disk full" in returned["export_error_message"]
        and statuses
        and statuses[-1] == "수집 결과를 Excel로 저장하지 못했습니다."
        and not any("저장했습니다" in m for m in statuses)
    )
    if ok:
        reporter.pass_("exporter 예외: exported=False/export_error=True 기록, 성공 문구 없음, worker가 저장 성공으로 오인하지 않음")
    else:
        reporter.fail(f"exporter 예외 결과가 예상과 다름: returned={returned}, statuses={statuses}")


def check_should_continue_reflects_stop_event(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result()
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=FakeExporter(),
    )

    should_continue = calls[0]["should_continue"]
    before_stop = should_continue()
    app.stop_event.set()
    after_stop = should_continue()

    if before_stop is True and after_stop is False:
        reporter.pass_("should_continue: stop_event가 set되기 전 True, set된 후 False를 반환함")
    else:
        reporter.fail(f"should_continue 결과가 예상과 다름: before_stop={before_stop}, after_stop={after_stop}")


def check_parse_positive_int_validation(reporter: ValidationReporter) -> None:
    valid_cases = [("30", 30), ("300", 300), (" 15 ", 15), ("1", 1)]
    invalid_cases = ["0", "-5", "abc", "", "3.5", "  ", None]

    valid_ok = all(ui._parse_positive_int(raw) == expected for raw, expected in valid_cases)
    invalid_ok = all(ui._parse_positive_int(raw) is None for raw in invalid_cases)

    if valid_ok and invalid_ok:
        reporter.pass_("입력 검증 helper(_parse_positive_int): 정상값 반환, 비정수/0/음수/빈 문자열은 None")
    else:
        reporter.fail(f"입력 검증 helper 결과가 예상과 다름: valid_ok={valid_ok}, invalid_ok={invalid_ok}")


def check_default_values_for_network_engine(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2C-2: Network/List가 기본 실행 경로가 되면서
    per_query_limit 기본값이 30으로 다시 바뀌어야 한다(target_count는
    300 그대로)."""
    ok = ui._DEFAULT_PER_QUERY_LIMIT == "30" and ui._DEFAULT_TARGET_COUNT == "300"
    if ok:
        reporter.pass_("Network 기본값 전환: _DEFAULT_PER_QUERY_LIMIT=30, _DEFAULT_TARGET_COUNT=300")
    else:
        reporter.fail(
            f"기본값 결과가 예상과 다름: PER_QUERY_LIMIT={ui._DEFAULT_PER_QUERY_LIMIT}, TARGET_COUNT={ui._DEFAULT_TARGET_COUNT}"
        )


def check_target_count_input_enabled_no_stale_guidance(reporter: ValidationReporter) -> None:
    """LEGALDONG-UI-2: 전체 목표 저장 개수는 항상 자동 계산이며 사용자가
    직접 수정할 수 없다 - 입력 위젯은 항상 disabled로 생성되고, "새 수집
    엔진 연결 후 적용됩니다." 같은 낡은 안내 문구는 남아있지 않아야 한다.
    실제 Tk 위젯을 만들지 않고(헤드리스 테스트) 위젯 생성 소스 코드로
    확인한다(check_legacy_path_untouched와 동일한 검증 방식).
    """
    import inspect

    source = inspect.getsource(ui.SalesDbCrawlerApp._build_global_target_count_section)
    ok = (
        'state="disabled"' in source
        and "target_count_entry" in source
        and "새 수집 엔진 연결 후 적용됩니다." not in source
    )
    if ok:
        reporter.pass_("target_count 항상 자동 계산: 입력 위젯이 disabled로 생성되고 낡은 안내 문구는 없음")
    else:
        reporter.fail(f"target_count 자동 계산 결과가 예상과 다름: source에서 disabled 생성/낡은 안내 문구 제거 확인 실패\n{source}")


def check_run_network_pipeline_passes_target_count_through(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2C-2: _run_network_pipeline 자체는 여전히 전달받은
    target_count를 그대로 orchestrator에 넘긴다(worker 계약 자체는 이번
    단계에서 변경하지 않았음을 재확인)."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result(stop_reason="target_reached", final_count=3, rows=_fake_rows(3))
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=FakeExporter(),
    )

    ok = calls and calls[0]["target_count"] == 300
    if ok:
        reporter.pass_("Network worker 계약 무변경: target_count=300이 orchestrator에 그대로 전달됨")
    else:
        reporter.fail(f"Network worker 결과가 예상과 다름: calls={calls}")


# ============================================================================
# collection_mode에 따른 home_enrichment_fn 호출 여부(§_run_network_pipeline
# 1542행의 `if collection_mode == "home_sns" and rows and not security_blocked`
# 게이트를 실제 production 메서드 호출로 직접 검증 - 수동 dict 비교가 아님)
# ============================================================================


def _core_field_rows(n: int) -> list:
    return [
        {
            "업체명": f"업체{i}", "업종": "카페", "새로오픈여부": "", "방문자리뷰수": 10,
            "블로그리뷰수": 0, "총리뷰수": 10, "주소": f"서울특별시 강동구 천호동 {i}",
            "대표전화": "", "플레이스 URL": f"https://pcmap.place.naver.com/place/{i}/home",
            "수집일": "2026-07-30", "홈페이지": "", "인스타": "", "블로그": "", "추가 링크": "",
            "place_id": str(i),
        }
        for i in range(n)
    ]


_CORE_FIELDS = ("업체명", "업종", "새로오픈여부", "방문자리뷰수", "블로그리뷰수", "총리뷰수", "주소", "대표전화", "플레이스 URL", "수집일")
_LINK_FIELDS = ("홈페이지", "인스타", "블로그", "추가 링크")


def _home_enrichment_fn_must_not_be_called(rows, **kwargs):
    raise AssertionError("home_enrichment_fn이 호출되면 안 되는 경로(collection_mode!='home_sns')에서 호출됨")


class SpyHomeEnrichmentFn:
    """실제 enrich_home_details와 동일한 반환 계약(요청서 §_run_network_pipeline
    1552-1557행이 참조하는 키)만 흉내낸다. 허용된 링크 필드(홈페이지/인스타/
    블로그/추가 링크)만 채우고 core 필드는 절대 건드리지 않는다(실제
    merge_home_result_into_row의 core-field 불변 정책과 동일한 계약)."""

    def __init__(self):
        self.calls: list = []

    def __call__(self, rows, **kwargs):
        self.calls.append({"rows": rows, **kwargs})
        enriched = []
        for row in rows:
            new_row = dict(row)
            new_row["홈페이지"] = f"https://example-{row['place_id']}.test"
            new_row["인스타"] = f"https://instagram.com/example{row['place_id']}"
            enriched.append(new_row)
        return {
            "rows": enriched,
            "stop_reason": None,
            "security_blocked": False,
            "home_success_count": len(rows),
            "failure_count": 0,
            "not_attempted_count": 0,
        }


def check_basic_mode_never_calls_home_enrichment_fn(reporter: ValidationReporter) -> None:
    """collection_mode="basic"(기본값)이면 rows가 있어도 home_enrichment_fn을
    전혀 호출하지 않는다 - 실제 _run_network_pipeline을 호출하고, 호출되면
    바로 실패하는 home_enrichment_fn을 주입해 증명한다(수동 dict 비교가 아님,
    실제 네트워크 호출 없음)."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _core_field_rows(3)
    result = _base_result(stop_reason="queue_exhausted", final_count=3, rows=rows)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    returned = app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "output/naver_place_network_db.xlsx",
        collection_mode="basic",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
        home_enrichment_fn=_home_enrichment_fn_must_not_be_called,
    )

    ok = (
        returned["rows"] == rows
        and all(row["홈페이지"] == "" and row["인스타"] == "" and row["블로그"] == "" and row["추가 링크"] == "" for row in returned["rows"])
        and len(exporter.calls) == 1
        and exporter.calls[0]["merged_data"] == rows
    )
    if ok:
        reporter.pass_("기본모드(basic): home_enrichment_fn 호출 0회, rows 보존, 홈페이지/인스타/블로그/추가 링크 공란 유지, exporter에 원본 rows 전달")
    else:
        reporter.fail(f"기본모드 결과가 예상과 다름: returned={returned}, exporter.calls={exporter.calls}")


def check_home_sns_mode_calls_home_enrichment_fn_once_and_preserves_core_fields(reporter: ValidationReporter) -> None:
    """collection_mode="home_sns"면 home_enrichment_fn이 정확히 1회 호출되고,
    그 결과가 result["rows"]에 반영된다 - 같은 입력 row로 기본모드와 비교해
    core 필드(업체명/업종/새로오픈여부/리뷰수/주소/대표전화/플레이스 URL/
    수집일)는 동일하게 유지되고 허용된 링크 필드만 달라지는지 확인한다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _core_field_rows(3)
    result = _base_result(stop_reason="queue_exhausted", final_count=3, rows=rows)
    fake_orchestrator, _ = _make_fake_orchestrator(result)
    home_fn = SpyHomeEnrichmentFn()

    returned = app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "output/naver_place_network_db.xlsx",
        collection_mode="home_sns",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
        home_enrichment_fn=home_fn,
    )

    basic_rows = _core_field_rows(3)  # 기본모드 대조군(home 보강 없이 그대로)
    core_fields_match = all(
        all(returned["rows"][i][field] == basic_rows[i][field] for field in _CORE_FIELDS)
        for i in range(3)
    )
    only_allowed_links_changed = all(
        returned["rows"][i]["홈페이지"] != "" and returned["rows"][i]["인스타"] != ""
        and returned["rows"][i]["블로그"] == basic_rows[i]["블로그"]
        and returned["rows"][i]["추가 링크"] == basic_rows[i]["추가 링크"]
        for i in range(3)
    )
    ok = (
        len(home_fn.calls) == 1
        and home_fn.calls[0]["rows"] == rows
        and core_fields_match
        and only_allowed_links_changed
    )
    if ok:
        reporter.pass_("home_sns모드: home_enrichment_fn 정확히 1회 호출, core 필드는 기본모드와 동일 유지, 허용된 링크 필드(홈페이지/인스타)만 변경")
    else:
        reporter.fail(f"home_sns모드 결과가 예상과 다름: calls={len(home_fn.calls)}, returned={returned}")


class FakeHomeEnrichmentFnWithStats:
    """새 통계 필드(home_processed_success_count 등)를 실제로 반환하는
    home_enrichment_fn fake - 최종 로그 문구 검증용."""

    def __init__(self, home_result_overrides: dict):
        self._overrides = home_result_overrides

    def __call__(self, rows, **kwargs):
        base = {
            "rows": rows, "stop_reason": None, "security_blocked": False,
            "home_success_count": 0, "home_processed_success_count": 0,
            "home_link_found_count": 0, "home_no_link_count": 0, "home_retry_count": 0,
            "failure_count": 0, "not_attempted_count": 0,
        }
        base.update(self._overrides)
        return base


def check_home_stat12_basic_mode_new_fields_default_and_excel_unchanged(reporter: ValidationReporter) -> None:
    """HOME-STAT-12: basic 모드는 home_enrichment_fn을 호출하지 않고, 신규
    통계 필드도 기존 계약대로 기본값(0)을 유지하며 Excel 저장 rows는 그대로다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _core_field_rows(2)
    result = _base_result(stop_reason="queue_exhausted", final_count=2, rows=rows)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    returned = app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx", collection_mode="basic",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
        home_enrichment_fn=_home_enrichment_fn_must_not_be_called,
    )

    ok = (
        returned.get("home_processed_success_count") == 0
        and returned.get("home_link_found_count") == 0
        and returned.get("home_no_link_count") == 0
        and returned.get("home_retry_count") == 0
        and returned["rows"] == rows
        and exporter.calls and exporter.calls[0]["merged_data"] == rows
    )
    if ok:
        reporter.pass_("HOME-STAT-12. basic 모드: home_enrichment_fn 미호출, 신규 통계 기본값 0, Excel rows 불변")
    else:
        reporter.fail(f"HOME-STAT-12 실패: returned={returned}, exporter.calls={exporter.calls}")


def check_home_sns_summary_log_shows_link_found_and_no_link_breakdown(reporter: ValidationReporter) -> None:
    """새 요약 로그는 '성공 N건' 단독 표현 대신 상세 처리 성공/외부 링크
    발견·없음/실패/재시도/미시도를 명확히 구분해 표시한다."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _core_field_rows(1)
    result = _base_result(stop_reason="queue_exhausted", final_count=1, rows=rows)
    fake_orchestrator, _ = _make_fake_orchestrator(result)
    home_fn = FakeHomeEnrichmentFnWithStats({
        "home_success_count": 5, "home_processed_success_count": 5,
        "home_link_found_count": 2, "home_no_link_count": 3,
        "home_retry_count": 1, "failure_count": 0, "not_attempted_count": 0,
        "first_pass": {"attempted": 5, "success": 4, "failed": 1},
        "retry_pass": {"attempted": 1, "success": 1, "failed": 0, "skipped": 0},
    })

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx", collection_mode="home_sns",
        collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
        home_enrichment_fn=home_fn,
    )

    summary_logs = [message for message in logs if "[ui][network][home] 보강 종료" in message]
    ok = (
        len(summary_logs) == 1
        and "상세 처리 성공 5건" in summary_logs[0]
        and "외부 링크 발견 2건" in summary_logs[0]
        and "없음 3건" in summary_logs[0]
        and "실패 0건" in summary_logs[0]
        and "재시도 1회" in summary_logs[0]
        and "미시도 0건" in summary_logs[0]
        and "성공 5건" not in summary_logs[0].replace("상세 처리 성공 5건", "")
    )
    if ok:
        reporter.pass_("새 요약 로그: 상세 처리 성공/외부 링크 발견·없음/실패/재시도(회)/미시도를 명확히 구분해 표시")
    else:
        reporter.fail(f"요약 로그 문구 검증 실패: summary_logs={summary_logs}")


def check_home_sns_summary_log_backward_compatible_without_new_fields(reporter: ValidationReporter) -> None:
    """home_enrichment_fn이 신규 통계 필드를 반환하지 않는 기존 fake(예:
    SpyHomeEnrichmentFn)여도 예외 없이 로그가 생성된다(하위 호환)."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    exporter = FakeExporter()
    rows = _core_field_rows(2)
    result = _base_result(stop_reason="queue_exhausted", final_count=2, rows=rows)
    fake_orchestrator, _ = _make_fake_orchestrator(result)
    home_fn = SpyHomeEnrichmentFn()

    try:
        app._run_network_pipeline(
            [{"query": "q1"}], 30, 300, "out.xlsx", collection_mode="home_sns",
            collector_factory=factory, orchestrator=fake_orchestrator, excel_exporter=exporter,
            home_enrichment_fn=home_fn,
        )
    except Exception as exc:
        reporter.fail(f"신규 필드 없는 home_enrichment_fn 결과 처리 중 예외 발생: {exc!r}")
        return

    summary_logs = [message for message in logs if "[ui][network][home] 보강 종료" in message]
    if len(summary_logs) == 1:
        reporter.pass_("신규 통계 필드가 없는 기존 home_enrichment_fn 결과도 예외 없이 요약 로그 생성(하위 호환)")
    else:
        reporter.fail(f"하위 호환 결과가 예상과 다름: summary_logs={summary_logs}")


def main() -> int:
    reporter = ValidationReporter()

    check_run_network_pipeline_passes_expected_arguments(reporter)
    check_collector_lifecycle(reporter)
    check_export_called_with_correct_arguments(reporter)
    check_target_reached_reflected_in_status(reporter)
    check_queue_exhausted_under_target_shows_shortfall(reporter)
    check_navigation_error_partial_save_not_captcha(reporter)
    check_user_stopped_partial_save(reporter)
    check_security_blocked_partial_save(reporter)
    check_status_429_partial_save(reporter)
    check_security_diagnostics_json_and_png_logged(reporter)
    check_security_diagnostics_png_failure_logged(reporter)
    check_security_diagnostics_json_failure_logged(reporter)
    check_normal_run_no_security_diagnostics_logs(reporter)
    check_security_diagnostics_malformed_does_not_crash_pipeline(reporter)
    check_no_double_save_for_security_and_429(reporter)
    check_zero_rows_no_export_no_file_creation(reporter)
    check_empty_jobs_no_export(reporter)
    check_exporter_exception_marks_export_error(reporter)
    check_should_continue_reflects_stop_event(reporter)
    check_parse_positive_int_validation(reporter)
    check_default_values_for_network_engine(reporter)
    check_target_count_input_enabled_no_stale_guidance(reporter)
    check_run_network_pipeline_passes_target_count_through(reporter)
    check_basic_mode_never_calls_home_enrichment_fn(reporter)
    check_home_sns_mode_calls_home_enrichment_fn_once_and_preserves_core_fields(reporter)
    check_home_stat12_basic_mode_new_fields_default_and_excel_unchanged(reporter)
    check_home_sns_summary_log_shows_link_found_and_no_link_breakdown(reporter)
    check_home_sns_summary_log_backward_compatible_without_new_fields(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
