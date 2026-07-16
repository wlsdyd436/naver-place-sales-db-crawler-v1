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
    app._security_block_decision = None

    app.keyword_input_var = FakeVar("카페")
    app.output_path_var = FakeVar("output/naver_place_test.xlsx")
    app.limit_var = FakeVar(ui._DEFAULT_PER_QUERY_LIMIT)
    app.target_count_var = FakeVar(ui._DEFAULT_TARGET_COUNT)
    app.new_open_only_var = FakeVar(False)
    app.review_min_var = FakeVar("")
    app.review_max_var = FakeVar("")
    app.mode_var = FakeVar("premium")

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
        and ui._DEFAULT_COLLECTION_ENGINE == "network"
    )
    if ok:
        reporter.pass_("기본 상수: per_query_limit=30, target_count=300, 기본 엔진=network")
    else:
        reporter.fail(
            f"기본 상수 결과가 예상과 다름: PER_QUERY_LIMIT={ui._DEFAULT_PER_QUERY_LIMIT}, "
            f"TARGET_COUNT={ui._DEFAULT_TARGET_COUNT}, ENGINE={ui._DEFAULT_COLLECTION_ENGINE}"
        )


# ---------------------------------------------------------------------------
# 2. target_count 활성화
# ---------------------------------------------------------------------------


def check_target_count_entry_enabled_and_restored_normal(reporter: ValidationReporter) -> None:
    build_source = inspect.getsource(ui.SalesDbCrawlerApp._build_global_target_count_section)
    panel_state_source = inspect.getsource(ui.SalesDbCrawlerApp._set_left_panel_state)
    ok = (
        'state="disabled"' not in build_source
        and "target_count_entry" in build_source
        and "새 수집 엔진 연결 후 적용됩니다." not in build_source
        and "target_count_entry" not in panel_state_source
    )
    if ok:
        reporter.pass_("target_count 활성화: disabled/낡은 안내 문구 없음, 좌측 패널 상태 전환 시 강제 disabled 예외 없음(다른 입력과 동일하게 normal로 복구됨)")
    else:
        reporter.fail(f"target_count 활성화 결과가 예상과 다름: build_source에 disabled/안내 문구 잔존 또는 panel_state_source에 target_count_entry 특례 존재\n{build_source}\n{panel_state_source}")


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

    if not instances:
        reporter.fail("Thread가 생성되지 않음")
        return
    thread = instances[0]
    ok = (
        thread.target == app._run_network_pipeline_worker
        and thread.args[0] == expected_queue
        and thread.args[1] == 30
        and thread.args[2] == 300
        and thread.args[3] == expected_output_path
        and thread.daemon is True
        and thread.start_called is True
        and app._run_queue_pipeline != thread.target
    )
    if ok:
        reporter.pass_("정상 start_crawl: Network worker thread가 선택되고 query_queue/per_query_limit=30/target_count=300/output_path가 정확히 전달되며 legacy worker는 호출되지 않음")
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
# 5. target_count 오류
# ---------------------------------------------------------------------------


def check_invalid_target_count_blocks_execution(reporter: ValidationReporter) -> None:
    invalid_values = ("0", "-5", "abc", "3.5", "")
    for invalid_value in invalid_values:
        app, logs, statuses, running_calls = _make_app()
        app.target_count_var = FakeVar(invalid_value)
        fake_threading, instances = _make_fake_threading()

        with _Saved(["threading"]) as saved:
            saved.set("threading", fake_threading)
            app.start_crawl()

        if instances or running_calls:
            reporter.fail(f"target_count={invalid_value!r}: 실행이 차단되지 않음(instances={len(instances)}, running_calls={running_calls})")
            return
        if not any("전체 목표 저장 개수" in message for message in logs):
            reporter.fail(f"target_count={invalid_value!r}: 전체 목표 저장 개수 관련 오류 로그가 없음(logs={logs})")
            return

    reporter.pass_(f"target_count 오류({len(invalid_values)}종: 0/-5/abc/3.5/빈 문자열) 각각 실행 차단, thread 생성 0회, 필드별 오류 로그 확인")


def check_target_count_allows_values_above_300(reporter: ValidationReporter) -> None:
    """LIMIT-300-A: 전체 목표 저장 개수는 검색 조합당 상한과 별개로 300
    초과값(301/500/1000)도 그대로 허용해야 한다(target_count에는 max_value를
    전달하지 않으므로 상한 검증 자체가 없음)."""
    for allowed_value in ("1", "300", "301", "500", "1000"):
        app, logs, statuses, running_calls = _make_app()
        app.target_count_var = FakeVar(allowed_value)
        fake_threading, instances = _make_fake_threading()

        with _Saved(["threading"]) as saved:
            saved.set("threading", fake_threading)
            app.start_crawl()

        if not instances or instances[0].args[2] != int(allowed_value):
            reporter.fail(f"target_count={allowed_value!r}: 허용돼야 하지만 thread 미생성 또는 값 불일치(instances={instances})")
            return

    reporter.pass_("target_count(1/300/301/500/1000) 전부 허용되어 thread 정상 생성됨(300 초과도 차단되지 않음)")


# ---------------------------------------------------------------------------
# 5A. 검색 조합당 상한 / 전체 목표 저장 개수 분리 검증 계약
# ---------------------------------------------------------------------------


def check_per_query_limit_and_target_count_validated_independently(reporter: ValidationReporter) -> None:
    """LIMIT-300-A §4 분리 계약: (1) limit=300/target=1000은 둘 다 유효,
    (2) limit=301/target=1000은 검색 조합당 상한 오류만 발생(전체 목표는
    검증 전에 이미 차단), (3) limit=30/target=0은 전체 목표 저장 개수
    오류만 발생(검색 조합당 상한은 통과)."""

    # (1) 유효 조합: limit=300, target=1000 → 둘 다 통과, thread 생성.
    app, logs, statuses, running_calls = _make_app()
    app.limit_var = FakeVar("300")
    app.target_count_var = FakeVar("1000")
    fake_threading, instances = _make_fake_threading()
    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()
    if not instances or instances[0].args[1] != 300 or instances[0].args[2] != 1000:
        reporter.fail(f"limit=300/target=1000: 유효해야 하지만 실패(instances={instances})")
        return

    # (2) limit=301(무효) / target=1000(유효라도 도달 전 차단) → 검색 조합당 상한 오류.
    app, logs, statuses, running_calls = _make_app()
    app.limit_var = FakeVar("301")
    app.target_count_var = FakeVar("1000")
    fake_threading, instances = _make_fake_threading()
    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()
    if instances or not any("검색 조합당 수집 상한" in message for message in logs):
        reporter.fail(f"limit=301/target=1000: 검색 조합당 상한 오류가 나와야 하는데 결과가 다름(instances={len(instances)}, logs={logs})")
        return
    if any("전체 목표 저장 개수" in message for message in logs):
        reporter.fail(f"limit=301/target=1000: 전체 목표 저장 개수 오류가 섞여 나오면 안 됨(logs={logs})")
        return

    # (3) limit=30(유효) / target=0(무효) → 전체 목표 저장 개수 오류.
    app, logs, statuses, running_calls = _make_app()
    app.limit_var = FakeVar("30")
    app.target_count_var = FakeVar("0")
    fake_threading, instances = _make_fake_threading()
    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()
    if instances or not any("전체 목표 저장 개수" in message for message in logs):
        reporter.fail(f"limit=30/target=0: 전체 목표 저장 개수 오류가 나와야 하는데 결과가 다름(instances={len(instances)}, logs={logs})")
        return
    if any("검색 조합당 수집 상한" in message for message in logs):
        reporter.fail(f"limit=30/target=0: 검색 조합당 상한 오류가 섞여 나오면 안 됨(logs={logs})")
        return

    reporter.pass_("분리 계약 확인: limit=300/target=1000 유효, limit=301은 조합당 상한 오류만, target=0은 전체 목표 오류만 발생")


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


def check_new_open_filter_disabled_and_normalized(reporter: ValidationReporter) -> None:
    filter_source = inspect.getsource(ui.SalesDbCrawlerApp._build_filter_section)
    panel_state_source = inspect.getsource(ui.SalesDbCrawlerApp._set_left_panel_state)
    static_ok = (
        'state="disabled"' in filter_source
        and "new_open_checkbox" in filter_source
        and "정확하게 판별할 수 없어 사용할 수 없습니다" in filter_source
        and "new_open_checkbox" in panel_state_source
        and '"disabled"' in panel_state_source
    )
    if not static_ok:
        reporter.fail(f"새로오픈 필터 정적 검증 결과가 예상과 다름\nfilter_source={filter_source}\npanel_state_source={panel_state_source}")
        return

    app, logs, statuses, running_calls = _make_app()
    app.new_open_only_var = FakeVar(True)
    fake_threading, instances = _make_fake_threading()

    with _Saved(["threading"]) as saved:
        saved.set("threading", fake_threading)
        app.start_crawl()

    if instances and app.new_open_only_var.get() is False:
        reporter.pass_("새로오픈 필터: 체크박스 disabled 생성 + 안내 문구 + 좌측 패널 복구 후에도 강제 disabled 유지 + Network 실행 전 False로 정규화됨")
    else:
        reporter.fail(f"새로오픈 필터 정규화 결과가 예상과 다름: instances={len(instances)}, new_open_only_var={app.new_open_only_var.get()}")


# ---------------------------------------------------------------------------
# 12. legacy 보존(내부 롤백)
# ---------------------------------------------------------------------------


def check_legacy_rollback_path_reachable_via_internal_constant(reporter: ValidationReporter) -> None:
    has_methods = (
        hasattr(ui.SalesDbCrawlerApp, "_run_queue_pipeline")
        and hasattr(ui.SalesDbCrawlerApp, "_collect_premium_query")
    )
    if not has_methods:
        reporter.fail("legacy 메서드(_run_queue_pipeline/_collect_premium_query)가 보존되지 않음")
        return

    app, logs, statuses, running_calls = _make_app()
    fake_threading, instances = _make_fake_threading()

    with _Saved(["_DEFAULT_COLLECTION_ENGINE", "threading"]) as saved:
        saved.set("_DEFAULT_COLLECTION_ENGINE", "legacy")
        saved.set("threading", fake_threading)
        app.start_crawl()

    if not instances:
        reporter.fail("_DEFAULT_COLLECTION_ENGINE='legacy'로 전환해도 thread가 생성되지 않음")
        return
    thread = instances[0]
    ok = thread.target == app._run_queue_pipeline and thread.start_called is True
    if ok:
        reporter.pass_("legacy 롤백 경로: 내부 상수를 legacy로 바꾸면 _run_queue_pipeline이 선택됨(실제 legacy crawler는 fake thread라 실행되지 않음)")
    else:
        reporter.fail(f"legacy 롤백 경로 결과가 예상과 다름: target={thread.target}")


def main() -> int:
    reporter = ValidationReporter()

    check_default_constants(reporter)
    check_target_count_entry_enabled_and_restored_normal(reporter)
    check_normal_start_crawl_selects_network_worker(reporter)
    check_invalid_per_query_limit_blocks_execution(reporter)
    check_per_query_limit_boundary_values_allowed(reporter)
    check_invalid_target_count_blocks_execution(reporter)
    check_target_count_allows_values_above_300(reporter)
    check_per_query_limit_and_target_count_validated_independently(reporter)
    check_empty_query_queue_blocks_execution(reporter)
    check_stop_event_cleared_before_run(reporter)
    check_running_state_applied_before_thread_start(reporter)
    check_worker_normal_completion_restores_ui(reporter)
    check_worker_unexpected_exception_restores_ui_without_success_wording(reporter)
    check_new_open_filter_disabled_and_normalized(reporter)
    check_legacy_rollback_path_reachable_via_internal_constant(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
