from pathlib import Path
import inspect
import sys
import threading
from types import SimpleNamespace


# ARCH-300C WIRE-2C-2: src.ui.start_crawl이 Network/List를 기본 실행 경로로
# 선택하고 per_query_limit/target_count를 실제로 검증해 Network worker
# thread를 시작하는지 검증하는 standalone 스크립트(실제 CTk 창/Tk mainloop/
# Playwright/네이버/실제 스레드 실행 없음). threading.Thread는 ui 모듈
# 네임스페이스에서만 fake로 교체하고(stdlib threading 자체는 건드리지
# 않음), start_crawl이 실제로 만드는 target/args만 검증한다 - 실제 worker
# 본문(_run_network_pipeline)은 여기서 실행하지 않는다.
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


class _Saved:
    """ui 모듈 전역을 임시 교체/복원한다(test_ui_pc_full_wiring.py와 동일 패턴)."""

    def __init__(self, names):
        self.names = names
        self.originals = {}

    def __enter__(self):
        for name in self.names:
            self.originals[name] = getattr(ui, name)
        return self

    def set(self, name, value):
        setattr(ui, name, value)

    def __exit__(self, exc_type, exc, tb):
        for name, value in self.originals.items():
            setattr(ui, name, value)
        return False


class FakeVar:
    """ctk.StringVar/BooleanVar와 동일한 get()/set() 계약만 흉내내는 fake -
    실제 Tk root가 없어도 만들 수 있다."""

    def __init__(self, value=""):
        self._value = value

    def get(self):
        return self._value

    def set(self, value) -> None:
        self._value = value


class FakeWidget:
    """CTkButton 등 configure(**kwargs)만 필요한 위젯의 최소 fake."""

    def __init__(self):
        self.configure_calls: list = []

    def configure(self, **kwargs) -> None:
        self.configure_calls.append(kwargs)


class FakeProgressBar:
    def __init__(self):
        self.values: list = []

    def set(self, value) -> None:
        self.values.append(value)


def _make_fake_threading():
    """ui.threading을 통째로 교체할 fake 네임스페이스 + 생성된 FakeThread
    인스턴스 기록 리스트를 반환한다. 실제 threading 모듈은 건드리지 않는다."""
    instances: list = []

    class FakeThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}
            self.daemon = daemon
            self.start_called = False
            instances.append(self)

        def start(self) -> None:
            self.start_called = True

    return SimpleNamespace(Thread=FakeThread), instances


def _make_app(*, districts=("강동구",), query_queue=None):
    """Tk __init__/mainloop 없이 start_crawl 계열 메서드만 호출하기 위한
    헤드리스 fake 인스턴스. 실제 Tk 위젯/StringVar 대신 FakeVar/FakeWidget을
    쓰고, get_selected_districts/_build_collection_queries는 지역/세부구역
    체크박스 트리 없이 고정값을 반환하도록 인스턴스 속성으로 덮어쓴다
    (test_ui_network_wiring.py의 log/set_status 오버라이드와 동일한 원리 -
    인스턴스 속성이 클래스 메서드보다 먼저 조회된다)."""
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)

    app.stop_event = threading.Event()
    app.pause_event = threading.Event()
    app.eta_after_id = None

    app.keyword_input_var = FakeVar("카페")
    app.output_path_var = FakeVar("output/naver_place_test.xlsx")
    app.limit_var = FakeVar(ui._DEFAULT_PER_QUERY_LIMIT)
    app.target_count_var = FakeVar(ui._DEFAULT_TARGET_COUNT)
    app.new_open_only_var = FakeVar(False)
    app.review_min_var = FakeVar("")
    app.review_max_var = FakeVar("")
    app.mode_var = FakeVar("premium")
    app.collection_mode_var = FakeVar("basic")

    # LEGALDONG-UI-2: _start_network_crawl이 참조하는
    # 공식 법정동 상태 - 이 fake app은 지역 자체는 검증하지 않고 per_query_limit
    # /target_count/thread 배선만 확인하므로, 시군구가 없는 시도를 고른 것으로
    # 고정해 시군구 필수 검사를 자연스럽게 통과시킨다.
    class _StubLoader:
        def list_sigungus(self, sido):
            return []

    app._legal_dong_loader = _StubLoader()
    app.legal_dong_sido_var = FakeVar("서울특별시")
    app.legal_dong_sigungu_var = FakeVar(ui._LEGAL_DONG_NO_SIGUNGU)
    app.get_selected_legal_dongs = lambda: []

    app.total_found_var = FakeVar("")
    app.duplicate_removed_var = FakeVar("")
    app.final_expected_var = FakeVar("")
    app.progress_percent_var = FakeVar("")
    app.eta_var = FakeVar("")

    app.btn_pause = FakeWidget()
    app.progress_bar = FakeProgressBar()
    app.last_output_path = ""

    # after/after_cancel: 실제 Tk 이벤트 루프가 없으므로 아무 것도 하지 않는
    # fake로 둔다(_start_eta_loop/legacy finally 분기가 호출해도 안전).
    app.after = lambda *a, **k: None
    app.after_cancel = lambda *a, **k: None

    logs: list = []
    statuses: list = []
    running_calls: list = []
    app.log = lambda message: logs.append(message)
    app.set_status = lambda message: statuses.append(message)
    app.set_running = lambda flag: running_calls.append(flag)

    fixed_query_queue = list(query_queue) if query_queue is not None else [
        {"region": "서울특별시 강동구", "keyword": "카페", "query": "서울특별시 강동구 카페"},
    ]
    app.get_selected_districts = lambda: list(districts)
    app._build_collection_queries = lambda: list(fixed_query_queue)

    return app, logs, statuses, running_calls


# ---------------------------------------------------------------------------
# 1. 기본 상수
# ---------------------------------------------------------------------------


def check_default_constants(reporter: ValidationReporter) -> None:
    ok = (
        ui._DEFAULT_PER_QUERY_LIMIT == "30"
        and ui._DEFAULT_TARGET_COUNT == "300"
    )
    if ok:
        reporter.pass_("기본 상수: per_query_limit=30, target_count=300")
    else:
        reporter.fail(
            f"기본 상수 결과가 예상과 다름: PER_QUERY_LIMIT={ui._DEFAULT_PER_QUERY_LIMIT}, "
            f"TARGET_COUNT={ui._DEFAULT_TARGET_COUNT}"
        )


# ---------------------------------------------------------------------------
# 2. target_count 항상 자동 계산·읽기 전용(LEGALDONG-UI-2)
# ---------------------------------------------------------------------------


def check_target_count_entry_always_disabled(reporter: ValidationReporter) -> None:
    """LEGALDONG-UI-2: 전체 목표 저장 개수는 항상 자동 계산이며 사용자가
    직접 수정할 수 없다 - 생성 시점과 좌측 패널 상태 복구(_set_left_panel_state)
    양쪽 모두에서 target_count_entry가 항상 disabled로 유지돼야 한다."""
    build_source = inspect.getsource(ui.SalesDbCrawlerApp._build_global_target_count_section)
    panel_state_source = inspect.getsource(ui.SalesDbCrawlerApp._set_left_panel_state)
    ok = (
        'state="disabled"' in build_source
        and "target_count_entry" in build_source
        and "target_count_entry" in panel_state_source
    )
    if ok:
        reporter.pass_("target_count 항상 자동 계산: 생성 시 disabled + 좌측 패널 상태 복구 시에도 강제 disabled 유지")
    else:
        reporter.fail(f"target_count가 항상 disabled로 유지되지 않음\n{build_source}\n{panel_state_source}")


# ---------------------------------------------------------------------------
# 3. 정상 start_crawl(Network 기본 경로)
# ---------------------------------------------------------------------------


def check_normal_start_crawl_selects_network_worker(reporter: ValidationReporter) -> None:
    app, logs, statuses, running_calls = _make_app()
    expected_queue = app._build_collection_queries()
    fake_threading, instances = _make_fake_threading()

    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()

    expected_output_path = app.make_timestamped_output_path(app.output_path_var.get(), "network")
    # LEGALDONG-UI-2: target_count는 항상 per_query_limit x len(query_queue)로
    # 자동 계산된다(더 이상 target_count_var의 기본값 300을 그대로 쓰지 않음).
    expected_target_count = 30 * len(expected_queue)

    if not instances:
        reporter.fail("Thread가 생성되지 않음")
        return
    thread = instances[0]
    ok = (
        thread.target == app._run_network_pipeline_worker
        and thread.args[0] == expected_queue
        and thread.args[1] == 30
        and thread.args[2] == expected_target_count
        and thread.args[3] == expected_output_path
        and thread.daemon is True
        and thread.start_called is True
    )
    if ok:
        reporter.pass_(f"정상 start_crawl: Network worker thread가 선택되고 query_queue/per_query_limit=30/target_count(자동계산)={expected_target_count}/output_path가 정확히 전달됨")
    else:
        reporter.fail(f"정상 start_crawl 결과가 예상과 다름: target={thread.target}, args={thread.args}, expected_queue={expected_queue}, expected_output_path={expected_output_path}")


# ---------------------------------------------------------------------------
# 4. per_query_limit 오류
# ---------------------------------------------------------------------------


def check_invalid_per_query_limit_blocks_execution(reporter: ValidationReporter) -> None:
    # LIMIT-300-A: 기존 0/-5/abc에 더해 301 이상(경계 위반)·999·공백/빈
    # 문자열·소수·숫자+문자 혼합·부호만 있는 값까지 전부 검색 조합당 상한
    # 오류로 차단돼야 한다(전체 목표 저장 개수와는 별개 계약).
    invalid_values = ("0", "-5", "abc", "301", "999", "-300", "", "   ", "1.0", "30.5", "30개", "+", "-")
    for invalid_value in invalid_values:
        app, logs, statuses, running_calls = _make_app()
        app.limit_var = FakeVar(invalid_value)
        fake_threading, instances = _make_fake_threading()

        with _Saved(["threading"]) as saved:
            saved.set("threading", fake_threading)
            app.start_crawl()

        if instances or running_calls:
            reporter.fail(f"per_query_limit={invalid_value!r}: 실행이 차단되지 않음(instances={len(instances)}, running_calls={running_calls})")
            return
        if not any("검색 조합당 수집 상한" in message for message in logs):
            reporter.fail(f"per_query_limit={invalid_value!r}: 검색 조합당 상한 관련 오류 로그가 없음(logs={logs})")
            return

    reporter.pass_(f"per_query_limit 오류({len(invalid_values)}종: 0/-5/abc/301/999/-300/빈 문자열/공백/소수/숫자+문자/부호만) 각각 실행 차단, thread 생성 0회, 필드별 오류 로그 확인")


def check_per_query_limit_boundary_values_allowed(reporter: ValidationReporter) -> None:
    """LIMIT-300-A: 검색 조합당 상한의 경계값 1/30/299/300은 모두 허용되어
    Network worker thread가 정상 생성돼야 한다(300을 넘지 않으므로 차단
    이유가 없음)."""
    for boundary_value in ("1", "30", "299", "300"):
        app, logs, statuses, running_calls = _make_app()
        app.limit_var = FakeVar(boundary_value)
        fake_threading, instances = _make_fake_threading()

        with _Saved(["threading"]) as saved:
            saved.set("threading", fake_threading)
            app.start_crawl()

        if not instances or instances[0].args[1] != int(boundary_value):
            reporter.fail(f"per_query_limit={boundary_value!r}: 허용돼야 하지만 thread 미생성 또는 값 불일치(instances={instances})")
            return

    reporter.pass_("per_query_limit 경계값(1/30/299/300) 전부 허용되어 thread 정상 생성됨")


# ---------------------------------------------------------------------------
# 5. target_count 항상 자동 계산(LEGALDONG-UI-2 - 사용자 입력 검증 제거)
# ---------------------------------------------------------------------------


def check_target_count_always_computed_from_query_count(reporter: ValidationReporter) -> None:
    """LEGALDONG-UI-2: 전체 목표 저장 개수는 항상
    per_query_limit x len(query_queue)로 자동 계산된다 - target_count_var에
    사용자가 어떤 값(무효값 포함)을 넣어도 무시되고 계산된 값으로
    덮어써진다. 300을 넘는 계산값도 자동 계산에는 상한이 없으므로 그대로
    허용된다."""
    nine_jobs = [
        {"region": f"서울특별시 강동구 동{i}", "keyword": "카페", "query": f"서울특별시 강동구 동{i} 카페"}
        for i in range(9)
    ]
    app, logs, statuses, running_calls = _make_app(query_queue=nine_jobs)
    app.limit_var = FakeVar("300")
    app.target_count_var = FakeVar("abc")  # 사용자가 뭘 넣어도 무시되고 계산값으로 덮어써져야 함
    fake_threading, instances = _make_fake_threading()
    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()

    expected_target = 300 * 9
    if not instances or instances[0].args[2] != expected_target:
        reporter.fail(f"target_count 자동 계산 실패: 기대값={expected_target}, instances={instances}")
        return
    if app.target_count_var.get() != str(expected_target):
        reporter.fail(f"target_count_var가 계산값으로 갱신되지 않음: {app.target_count_var.get()!r}")
        return
    reporter.pass_(f"target_count 자동 계산 확인: limit=300 x query_queue=9건 = {expected_target}(300 초과도 정상 허용, 사용자 입력은 무시됨)")


def check_invalid_per_query_limit_blocks_before_target_count(reporter: ValidationReporter) -> None:
    """per_query_limit이 무효하면 target_count 계산 이전에 이미 차단된다 -
    전체 목표 저장 개수 관련 오류 로그는 섞여 나오지 않아야 한다."""
    app, logs, statuses, running_calls = _make_app()
    app.limit_var = FakeVar("301")
    fake_threading, instances = _make_fake_threading()
    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()
    if instances or not any("검색 조합당 수집 상한" in message for message in logs):
        reporter.fail(f"limit=301: 검색 조합당 상한 오류가 나와야 하는데 결과가 다름(instances={len(instances)}, logs={logs})")
        return
    if any("전체 목표 저장 개수" in message for message in logs):
        reporter.fail(f"limit=301: 전체 목표 저장 개수 오류가 섞여 나오면 안 됨(logs={logs})")
        return
    reporter.pass_("per_query_limit 무효 시 target_count 계산 전에 차단되고, 전체 목표 오류는 섞이지 않음")


# ---------------------------------------------------------------------------
# 6. query_queue 0건
# ---------------------------------------------------------------------------


def check_empty_query_queue_blocks_execution(reporter: ValidationReporter) -> None:
    app, logs, statuses, running_calls = _make_app(query_queue=[])
    fake_threading, instances = _make_fake_threading()

    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()

    ok = not instances and not running_calls and any("선택되지 않았습니다" in message for message in logs)
    if ok:
        reporter.pass_("query_queue 0건: 실행 차단, thread 생성 0회, 지역/세부구역 선택 오류 로그 확인")
    else:
        reporter.fail(f"query_queue 0건 결과가 예상과 다름: instances={len(instances)}, running_calls={running_calls}, logs={logs}")


# ---------------------------------------------------------------------------
# 7. stop_event
# ---------------------------------------------------------------------------


def check_stop_event_cleared_before_run(reporter: ValidationReporter) -> None:
    app, logs, statuses, running_calls = _make_app()
    app.stop_event.set()
    fake_threading, instances = _make_fake_threading()

    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()

    if instances and not app.stop_event.is_set():
        reporter.pass_("stop_event: 정상 실행 전에 clear()가 호출되어 이전 중단 상태가 남지 않음")
    else:
        reporter.fail(f"stop_event 결과가 예상과 다름: instances={len(instances)}, stop_event.is_set()={app.stop_event.is_set()}")


# ---------------------------------------------------------------------------
# 8. UI 실행 상태(thread 시작 전에 적용)
# ---------------------------------------------------------------------------


def check_running_state_applied_before_thread_start(reporter: ValidationReporter) -> None:
    app, logs, statuses, running_calls = _make_app()
    timeline: list = []
    app.set_running = lambda flag: timeline.append(("set_running", flag))

    class TimelineFakeThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self.target = target
            self.args = args

        def start(self) -> None:
            timeline.append(("thread_start",))

    with _Saved(["threading"]) as saved:
        saved.set("threading", SimpleNamespace(Thread=TimelineFakeThread))
        app.start_crawl()

    ok = ("set_running", True) in timeline and ("thread_start",) in timeline and timeline.index(("set_running", True)) < timeline.index(("thread_start",))
    if ok:
        reporter.pass_("UI 실행 상태: set_running(True)가 thread.start()보다 먼저 호출됨")
    else:
        reporter.fail(f"UI 실행 상태 결과가 예상과 다름: timeline={timeline}")


# ---------------------------------------------------------------------------
# 9. worker 정상 종료 UI 복구
# ---------------------------------------------------------------------------


def check_worker_normal_completion_restores_ui(reporter: ValidationReporter) -> None:
    app, logs, statuses, running_calls = _make_app()
    app._run_network_pipeline = lambda *a, **k: {"stop_reason": "queue_exhausted", "exported": False}

    app._run_network_pipeline_worker([{"query": "q1"}], 30, 300, "out.xlsx")

    if running_calls == [False]:
        reporter.pass_("worker 정상 종료: 기존 복구 helper(set_running(False))가 정확히 1회 호출됨")
    else:
        reporter.fail(f"worker 정상 종료 결과가 예상과 다름: running_calls={running_calls}")


# ---------------------------------------------------------------------------
# 10. worker 예상 밖 예외
# ---------------------------------------------------------------------------


def check_worker_unexpected_exception_restores_ui_without_success_wording(reporter: ValidationReporter) -> None:
    app, logs, statuses, running_calls = _make_app()

    def _boom(*a, **k):
        raise RuntimeError("playwright launch failed")

    app._run_network_pipeline = _boom

    app._run_network_pipeline_worker([{"query": "q1"}], 30, 300, "out.xlsx")

    ok = (
        running_calls == [False]
        and statuses
        and "저장했습니다" not in statuses[-1]
        and "저장 완료" not in statuses[-1]
        and any("예상하지 못한 오류" in message for message in logs)
    )
    if ok:
        reporter.pass_("worker 예상 밖 예외: UI 복구(set_running(False)) + 성공/저장 문구 없음 + 짧은 오류 안내")
    else:
        reporter.fail(f"worker 예상 밖 예외 결과가 예상과 다름: running_calls={running_calls}, statuses={statuses}, logs={logs}")


# ---------------------------------------------------------------------------
# 11. 새로오픈 필터
# ---------------------------------------------------------------------------


def check_new_open_filter_enabled_and_threaded_into_jobs(reporter: ValidationReporter) -> None:
    """NEW-OPENING-1: 새로오픈 체크박스는 더 이상 항상 잠기지 않으며(§5),
    체크한 값이 query_queue의 각 job["new_opening_only"]까지 명시적으로
    전달돼야 한다(별도 thread 인자가 아니라 job dict를 통해 collector까지
    흘러간다 - §7)."""
    filter_source = inspect.getsource(ui.SalesDbCrawlerApp._build_filter_section)
    panel_state_source = inspect.getsource(ui.SalesDbCrawlerApp._set_left_panel_state)
    static_ok = (
        'ctk.CTkCheckBox(filter_frame, text="새로오픈 업체만 수집", variable=self.new_open_only_var, state="disabled")'
        not in filter_source
        and "new_open_checkbox" not in panel_state_source
    )
    if not static_ok:
        reporter.fail(f"새로오픈 필터가 여전히 강제로 잠겨 있음\nfilter_source={filter_source}\npanel_state_source={panel_state_source}")
        return

    app, logs, statuses, running_calls = _make_app(
        query_queue=[{
            "region": "서울특별시 강동구", "keyword": "카페", "query": "서울특별시 강동구 카페",
            "new_opening_only": True,
        }],
    )
    app.new_open_only_var = FakeVar(True)
    fake_threading, instances = _make_fake_threading()

    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()

    query_queue = instances[0].args[0] if instances else []
    if (
        instances
        and app.new_open_only_var.get() is True
        and query_queue
        and all(job.get("new_opening_only") is True for job in query_queue)
    ):
        reporter.pass_("새로오픈 필터: 체크박스 사용 가능(강제 disabled 없음) + query_queue의 모든 job에 new_opening_only=True 전달됨")
    else:
        reporter.fail(f"새로오픈 필터 wiring 결과가 예상과 다름: instances={len(instances)}, new_open_only_var={app.new_open_only_var.get()}, query_queue={query_queue}")



def main() -> int:
    reporter = ValidationReporter()

    check_default_constants(reporter)
    check_target_count_entry_always_disabled(reporter)
    check_normal_start_crawl_selects_network_worker(reporter)
    check_invalid_per_query_limit_blocks_execution(reporter)
    check_per_query_limit_boundary_values_allowed(reporter)
    check_target_count_always_computed_from_query_count(reporter)
    check_invalid_per_query_limit_blocks_before_target_count(reporter)
    check_empty_query_queue_blocks_execution(reporter)
    check_stop_event_cleared_before_run(reporter)
    check_running_state_applied_before_thread_start(reporter)
    check_worker_normal_completion_restores_ui(reporter)
    check_worker_unexpected_exception_restores_ui_without_success_wording(reporter)
    check_new_open_filter_enabled_and_threaded_into_jobs(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
