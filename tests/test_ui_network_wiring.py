from pathlib import Path
import sys
import threading


# ARCH-300C WIRE-2B-2: src.ui._run_network_pipeline 검증용 standalone 스크립트
# (실제 CTk 창/Tk mainloop/Playwright/네이버 없음). collector_factory/orchestrator를
# fake로 주입해 UI 작업 큐가 run_collection_plan에 어떻게 연결되는지만 검증한다.
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
    app._security_block_decision = None
    return app, logs, statuses


class FakeNetworkCollector:
    """NetworkBrowserCollector와 동일한 계약(컨텍스트 매니저 + collect_query)만
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

    def __call__(self, *, collected_at):
        self.calls.append(collected_at)
        instance = FakeNetworkCollector(collected_at)
        self.instances.append(instance)
        return instance


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
    result = _base_result(stop_reason="queue_exhausted", final_count=3, executed_query_count=2)
    fake_orchestrator, calls = _make_fake_orchestrator(result)
    query_queue = [{"query": "q1"}, {"query": "q2"}]

    returned = app._run_network_pipeline(
        query_queue, 30, 300, "output/naver_place_network_db.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
    )

    if not calls:
        reporter.fail("orchestrator가 호출되지 않음")
        return
    call = calls[0]
    collector = factory.instances[0]
    ok = (
        call["jobs"] == query_queue
        and call["per_query_limit"] == 30
        and call["target_count"] == 300
        and call["collected_at"] == factory.calls[0]
        and call["collect_query"] == collector.collect_query
        and callable(call["should_continue"])
        and call["on_security_block"] == app._note_security_block
        and returned == result
    )
    if ok:
        reporter.pass_("인자 전달: query_queue/per_query_limit/target_count/collected_at/collect_query/should_continue/on_security_block이 정확히 전달됨")
    else:
        reporter.fail(f"인자 전달 결과가 예상과 다름: call={call}")


def check_collector_lifecycle(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result()
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
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


def check_target_reached_reflected_in_status(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result(stop_reason="target_reached", final_count=300, executed_query_count=17, skipped_query_count=7)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
    )

    ok = (
        statuses
        and statuses[-1] == "전체 목표 개수에 도달했습니다."
        and any("final_count=300" in message for message in logs)
    )
    if ok:
        reporter.pass_("target_reached: 상태 문구와 final_count가 로그에 반영됨")
    else:
        reporter.fail(f"target_reached 결과가 예상과 다름: statuses={statuses}, logs={logs}")


def check_queue_exhausted_under_target_shows_shortfall(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result(stop_reason="queue_exhausted", final_count=50, executed_query_count=4)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
    )

    ok = statuses and statuses[-1] == "선택한 지역 수집이 완료되었습니다. (목표 미달: 50/300)"
    if ok:
        reporter.pass_("queue_exhausted(목표 미달): 50/300 미달 문구가 상태에 반영됨")
    else:
        reporter.fail(f"queue_exhausted 목표 미달 결과가 예상과 다름: statuses={statuses}")


def check_navigation_error_shows_browser_error_not_captcha(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    long_message = "TargetClosedError: " + ("x" * 300)
    result = _base_result(
        stop_reason="navigation_error", final_count=1,
        navigation_error=True, navigation_error_message=long_message,
    )
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
    )

    ok = (
        statuses
        and statuses[-1] == "브라우저 페이지 오류로 수집을 중단했습니다."
        and "보안" not in statuses[-1]
        and "CAPTCHA" not in statuses[-1]
        and not any(long_message in message for message in logs)
        and any("navigation_error 상세" in message for message in logs)
    )
    if ok:
        reporter.pass_("navigation_error: 브라우저 오류 문구(보안 확인 아님) + 전체 메시지는 사용자 상태에 노출되지 않음")
    else:
        reporter.fail(f"navigation_error 결과가 예상과 다름: statuses={statuses}, logs={logs}")


def check_user_stopped_shows_user_stop_message(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result(stop_reason="user_stopped", final_count=1, executed_query_count=1, skipped_query_count=1)
    fake_orchestrator, _ = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}, {"query": "q2"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
    )

    ok = statuses and statuses[-1] == "사용자가 수집을 중단했습니다."
    if ok:
        reporter.pass_("user_stopped: 사용자 중단 문구가 상태에 반영됨")
    else:
        reporter.fail(f"user_stopped 결과가 예상과 다름: statuses={statuses}")


def check_security_blocked_callback_and_no_save_wording(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result(
        stop_reason="security_blocked", final_count=2, security_blocked=True,
    )
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
    )

    call = calls[0] if calls else {}
    ok = (
        call.get("on_security_block") == app._note_security_block
        and statuses
        and statuses[-1] == "보안 확인이 감지되어 수집을 중단했습니다."
        and not any(("저장했습니다" in m) or ("저장 완료" in m) for m in logs + statuses)
    )
    if ok:
        reporter.pass_("security_blocked: on_security_block 콜백 전달 확인, 아직 저장 관련 문구는 없음")
    else:
        reporter.fail(f"security_blocked 결과가 예상과 다름: call={call}, statuses={statuses}, logs={logs}")


def check_should_continue_reflects_stop_event(reporter: ValidationReporter) -> None:
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result()
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
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


def check_legacy_path_untouched(reporter: ValidationReporter) -> None:
    import inspect

    has_methods = (
        hasattr(ui.SalesDbCrawlerApp, "_run_queue_pipeline")
        and hasattr(ui.SalesDbCrawlerApp, "_collect_premium_query")
        and hasattr(ui.SalesDbCrawlerApp, "_collect_basic_query")
        and hasattr(ui.SalesDbCrawlerApp, "_collect_premium_query_legacy")
        and hasattr(ui.SalesDbCrawlerApp, "_run_network_pipeline")
    )
    start_crawl_source = inspect.getsource(ui.SalesDbCrawlerApp.start_crawl)
    still_legacy_default = (
        "self._run_queue_pipeline" in start_crawl_source
        and "self._run_network_pipeline" not in start_crawl_source
    )

    if has_methods and still_legacy_default:
        reporter.pass_("기존 legacy 경로 무영향: _run_queue_pipeline/_collect_premium_query 등 보존, start_crawl 기본 실행 경로는 여전히 legacy")
    else:
        reporter.fail(f"legacy 경로 무영향 결과가 예상과 다름: has_methods={has_methods}, still_legacy_default={still_legacy_default}")


def check_legacy_default_per_query_limit_preserved(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2B-2A: start_crawl이 여전히 legacy를 실행하는 동안
    limit_var의 화면 기본값은 300으로 유지되어야 한다(WIRE-2B-2에서 30으로
    바뀌었던 것을 되돌린 회귀 수정 확인)."""
    ok = ui._DEFAULT_PER_QUERY_LIMIT == "300" and ui._DEFAULT_TARGET_COUNT == "300"
    if ok:
        reporter.pass_("legacy 기본값 보존: _DEFAULT_PER_QUERY_LIMIT=300, _DEFAULT_TARGET_COUNT=300 유지")
    else:
        reporter.fail(
            f"기본값 결과가 예상과 다름: PER_QUERY_LIMIT={ui._DEFAULT_PER_QUERY_LIMIT}, TARGET_COUNT={ui._DEFAULT_TARGET_COUNT}"
        )


def check_target_count_input_disabled_with_guidance(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2B-2A: target_count_var는 아직 start_crawl에 연결되지
    않았으므로, 입력 위젯은 disabled 상태로 생성되고 "새 수집 엔진 연결 후
    적용됩니다." 안내 문구가 함께 표시되어야 한다. 실제 Tk 위젯을 만들지
    않고(헤드리스 테스트) 위젯 생성 소스 코드로 확인한다(check_legacy_path_untouched
    와 동일한 검증 방식).
    """
    import inspect

    source = inspect.getsource(ui.SalesDbCrawlerApp._build_global_target_count_section)
    ok = (
        'state="disabled"' in source
        and "target_count_entry" in source
        and "새 수집 엔진 연결 후 적용됩니다." in source
    )
    if ok:
        reporter.pass_("target_count 준비 상태: 입력 위젯 disabled 생성 + 안내 문구 존재")
    else:
        reporter.fail(f"target_count 준비 상태 결과가 예상과 다름: source에 disabled/안내 문구 포함 여부 확인 실패\n{source}")


def check_run_network_pipeline_ignores_target_count_disabled_state(reporter: ValidationReporter) -> None:
    """ARCH-300C WIRE-2B-2A: target_count 입력이 화면에서 비활성화되어도
    _run_network_pipeline 자체는 전달받은 target_count를 그대로
    orchestrator에 넘겨야 한다(fake wiring 구조 무영향 확인)."""
    app, logs, statuses = _make_app()
    factory = FakeCollectorFactory()
    result = _base_result(stop_reason="target_reached", final_count=300)
    fake_orchestrator, calls = _make_fake_orchestrator(result)

    app._run_network_pipeline(
        [{"query": "q1"}], 30, 300, "out.xlsx",
        collector_factory=factory, orchestrator=fake_orchestrator,
    )

    ok = calls and calls[0]["target_count"] == 300
    if ok:
        reporter.pass_("Network worker 무영향: target_count=300이 UI 비활성화와 무관하게 orchestrator에 그대로 전달됨")
    else:
        reporter.fail(f"Network worker 결과가 예상과 다름: calls={calls}")


def main() -> int:
    reporter = ValidationReporter()

    check_run_network_pipeline_passes_expected_arguments(reporter)
    check_collector_lifecycle(reporter)
    check_target_reached_reflected_in_status(reporter)
    check_queue_exhausted_under_target_shows_shortfall(reporter)
    check_navigation_error_shows_browser_error_not_captcha(reporter)
    check_user_stopped_shows_user_stop_message(reporter)
    check_security_blocked_callback_and_no_save_wording(reporter)
    check_should_continue_reflects_stop_event(reporter)
    check_parse_positive_int_validation(reporter)
    check_legacy_path_untouched(reporter)
    check_legacy_default_per_query_limit_preserved(reporter)
    check_target_count_input_disabled_with_guidance(reporter)
    check_run_network_pipeline_ignores_target_count_disabled_state(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
