import ast
import inspect
from pathlib import Path
import sys
import threading


# UI-4(홈페이지·SNS 보강 stage 분리) 검증용 standalone 스크립트(실제 CTk
# 창/Tk mainloop 없음). src/ui.py의 _run_network_pipeline 안에 인라인으로
# 있던 Home stage 코드 블록(1291-1367줄)이 src/ui_home_stage.py의
# module-level 함수 run_home_enrichment_stage로 옮겨지고, 유일한 self.*
# 의존(self.log/self.set_status/self.pause_event/self.stop_event/
# self._note_home_progress)이 명시적 콜백/인자(on_log/on_status/
# pause_event/stop_event/on_progress)로 바뀌었는지 확인한다. 문자열/로그
# 값은 이동 전 실제 Production 코드를 그대로 옮긴 것이며(추정 없음), 이동
# 후에도 문자 단위로 동일해야 한다. 전체 Network pipeline 시나리오
# (security_blocked/user_stopped/navigation_error 부분 저장, 이중 저장
# 방지, Excel export, CAPTCHA diagnostics)는 이미 test_ui_network_wiring.py/
# test_ui_network_export.py/test_collection_home_enrichment.py가 보호하므로
# 여기서 중복 작성하지 않는다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


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


def _parse_module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


class LogCollector:
    def __init__(self):
        self.messages: list = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)


def _base_collection_result(**overrides) -> dict:
    """목록 수집 단계(run_collection_plan) 직후, Home stage 진입 시점의
    result dict를 흉내낸다 - Home stage와 무관한 key도 함께 넣어 §12(입력
    result 보존) 검증에 사용한다."""
    result = {
        "rows": [{"place_id": "1", "업체명": "업체1"}],
        "executed_query_count": 1,
        "skipped_query_count": 0,
        "stop_reason": "queue_exhausted",
        "final_count": 1,
        "security_blocked": False,
        "status_429_seen": False,
        "navigation_error": False,
        "navigation_error_message": "",
        "duplicate_removed_count": 0,
        "review_filter_stats": None,
        "security_diagnostics": None,
    }
    result.update(overrides)
    return result


def _home_enrichment_fn_must_not_be_called(rows, **kwargs):
    raise AssertionError("home_enrichment_fn이 호출되면 안 되는 경로에서 호출됨")


class SpyHomeEnrichmentFn:
    def __init__(self, home_result_overrides: dict):
        self.calls: list = []
        self._overrides = home_result_overrides

    def __call__(self, rows, **kwargs):
        self.calls.append({"rows": rows, **kwargs})
        base = {
            "rows": rows, "stop_reason": None, "security_blocked": False,
            "home_success_count": 0, "home_processed_success_count": 0,
            "home_link_found_count": 0, "home_no_link_count": 0, "home_retry_count": 0,
            "failure_count": 0, "not_attempted_count": 0,
        }
        base.update(self._overrides)
        return base


# --------------------------------------------------------------------------
# UI-HOME-STAGE-1~3: 모듈 경계 계약
# --------------------------------------------------------------------------

def check_new_module_api_exists(reporter: ValidationReporter) -> None:
    try:
        from src import ui_home_stage
    except ImportError as exc:
        reporter.fail(f"UI-HOME-STAGE-1. src.ui_home_stage import 실패: {exc!r}")
        return
    if hasattr(ui_home_stage, "run_home_enrichment_stage"):
        reporter.pass_("UI-HOME-STAGE-1. src.ui_home_stage.run_home_enrichment_stage가 존재함")
    else:
        reporter.fail("UI-HOME-STAGE-1. run_home_enrichment_stage가 없음")


def check_function_defined_in_new_module(reporter: ValidationReporter) -> None:
    try:
        from src.ui_home_stage import run_home_enrichment_stage
    except ImportError as exc:
        reporter.fail(f"UI-HOME-STAGE-2. import 실패: {exc!r}")
        return
    if run_home_enrichment_stage.__module__ == "src.ui_home_stage":
        reporter.pass_("UI-HOME-STAGE-2. run_home_enrichment_stage.__module__ == 'src.ui_home_stage'")
    else:
        reporter.fail(f"UI-HOME-STAGE-2. __module__ 불일치: {run_home_enrichment_stage.__module__}")


def check_new_module_has_no_gui_dependency(reporter: ValidationReporter) -> None:
    """UI-HOME-STAGE-3: AST import 노드 검사(문자열 grep 아님)."""
    path = ROOT_DIR / "src" / "ui_home_stage.py"
    if not path.exists():
        reporter.fail("UI-HOME-STAGE-3. src/ui_home_stage.py가 존재하지 않음")
        return
    tree = _parse_module_ast(path)
    forbidden = {"tkinter", "customtkinter", "src.ui"}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(
                alias.name for alias in node.names
                if any(alias.name == item or alias.name.startswith(item + ".") for item in forbidden)
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if any(node.module == item or node.module.startswith(item + ".") for item in forbidden):
                found.append(node.module)
    if not found:
        reporter.pass_("UI-HOME-STAGE-3. src/ui_home_stage.py는 tkinter/customtkinter/src.ui를 import하지 않음(AST 검사)")
    else:
        reporter.fail(f"UI-HOME-STAGE-3. 금지된 import 발견: {found}")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-4: Basic 모드(home_enrichment_fn 미호출)
# --------------------------------------------------------------------------

def check_basic_mode_skips_enrichment(reporter: ValidationReporter) -> None:
    from src.ui_home_stage import run_home_enrichment_stage

    on_log = LogCollector()
    status_calls: list = []
    result_in = _base_collection_result()
    original_rows = result_in["rows"]

    returned = run_home_enrichment_stage(
        result_in,
        collection_mode="basic",
        home_enrichment_fn=_home_enrichment_fn_must_not_be_called,
        pause_event=threading.Event(),
        stop_event=threading.Event(),
        on_log=on_log,
        on_status=lambda message: status_calls.append(message),
        on_progress=lambda *a, **k: None,
    )

    ok = (
        status_calls == []
        and returned["rows"] == original_rows
        and returned["home_stop_reason"] is None
        and returned["home_security_blocked"] is False
        and returned["home_success_count"] == 0
        and returned["home_processed_success_count"] == 0
        and returned["home_link_found_count"] == 0
        and returned["home_no_link_count"] == 0
        and returned["home_retry_count"] == 0
        and returned["home_failure_count"] == 0
        and returned["home_not_attempted_count"] == 0
        and returned["stop_reason"] == "queue_exhausted"
    )
    if ok:
        reporter.pass_("UI-HOME-STAGE-4. basic 모드: home_enrichment_fn/on_status 0회 호출, home_* 필드 기본값, rows/기존 key 보존")
    else:
        reporter.fail(f"UI-HOME-STAGE-4 실패: status_calls={status_calls}, returned={returned}")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-5: home_sns 성공(1회 호출 + 통계/로그 병합)
# --------------------------------------------------------------------------

def check_home_sns_success_calls_once_and_merges(reporter: ValidationReporter) -> None:
    from src.ui_home_stage import run_home_enrichment_stage

    on_log = LogCollector()
    status_calls: list = []
    progress_calls: list = []
    pause_event = threading.Event()
    stop_event = threading.Event()
    rows = [{"place_id": "1"}, {"place_id": "2"}]
    enriched_rows = [dict(row, 홈페이지="https://example.test") for row in rows]
    home_fn = SpyHomeEnrichmentFn({
        "rows": enriched_rows,
        "home_success_count": 5, "home_processed_success_count": 5,
        "home_link_found_count": 2, "home_no_link_count": 3,
        "home_retry_count": 1, "failure_count": 0, "not_attempted_count": 0,
    })

    result_in = _base_collection_result(rows=rows)
    returned = run_home_enrichment_stage(
        result_in,
        collection_mode="home_sns",
        home_enrichment_fn=home_fn,
        pause_event=pause_event,
        stop_event=stop_event,
        on_log=on_log,
        on_status=lambda message: status_calls.append(message),
        on_progress=lambda *a, **k: progress_calls.append((a, k)),
    )

    call = home_fn.calls[0] if home_fn.calls else {}
    summary_logs = [m for m in on_log.messages if "[ui][network][home] 보강 종료" in m]
    expected_summary = (
        "[ui][network][home] 보강 종료: 상세 처리 성공 5건 "
        "(외부 링크 발견 2건 / 없음 3건), 실패 0건, 재시도 1회, 미시도 0건"
    )

    ok = (
        len(home_fn.calls) == 1
        and call.get("rows") == rows
        and call.get("pause_event") is pause_event
        and call.get("stop_event") is stop_event
        and callable(call.get("should_continue"))
        and call.get("should_continue")() is True
        and status_calls == ["홈페이지/SNS 보강 준비 중... (총 2건)"]
        and "[ui][network][home] 홈페이지/SNS 보강 시작: 대상 2건" in on_log.messages
        and summary_logs == [expected_summary]
        and returned["rows"] == enriched_rows
        and returned["home_success_count"] == 5
        and returned["home_processed_success_count"] == 5
        and returned["home_link_found_count"] == 2
        and returned["home_no_link_count"] == 3
        and returned["home_retry_count"] == 1
    )
    # on_progress가 그대로 전달됐는지(호출 자체가 아니라 동일 참조 전달 확인)
    on_progress_passed_through = call.get("on_progress") is not None
    if ok and on_progress_passed_through:
        reporter.pass_("UI-HOME-STAGE-5. home_sns 성공: home_enrichment_fn 1회(rows/pause_event/stop_event/on_progress 전달), 통계·요약 로그 문자 단위 일치")
    else:
        reporter.fail(f"UI-HOME-STAGE-5 실패: call={call}, status_calls={status_calls}, logs={on_log.messages}, returned={returned}")


def check_should_continue_reflects_stop_event(reporter: ValidationReporter) -> None:
    """UI-HOME-STAGE-5 부속: should_continue closure가 stop_event를 그대로
    반영하는지(원본 self.stop_event 대신 인자로 받은 stop_event 사용)."""
    from src.ui_home_stage import run_home_enrichment_stage

    stop_event = threading.Event()
    home_fn = SpyHomeEnrichmentFn({"rows": [{"place_id": "1"}]})
    result_in = _base_collection_result(rows=[{"place_id": "1"}])

    run_home_enrichment_stage(
        result_in, collection_mode="home_sns", home_enrichment_fn=home_fn,
        pause_event=threading.Event(), stop_event=stop_event,
        on_log=lambda m: None, on_status=lambda m: None, on_progress=lambda *a, **k: None,
    )

    should_continue = home_fn.calls[0]["should_continue"]
    before = should_continue()
    stop_event.set()
    after = should_continue()

    if before is True and after is False:
        reporter.pass_("UI-HOME-STAGE-5. should_continue이 인자로 받은 stop_event를 그대로 반영함(set 전 True/후 False)")
    else:
        reporter.fail(f"should_continue 결과가 예상과 다름: before={before}, after={after}")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-6: 신규 통계 없는 구 schema fallback
# --------------------------------------------------------------------------

def check_old_schema_fallback(reporter: ValidationReporter) -> None:
    from src.ui_home_stage import run_home_enrichment_stage

    on_log = LogCollector()
    rows = [{"place_id": "1"}]

    def old_style_home_fn(rows_arg, **kwargs):
        return {
            "rows": rows_arg, "stop_reason": None, "security_blocked": False,
            "home_success_count": 7, "failure_count": 1, "not_attempted_count": 0,
        }

    result_in = _base_collection_result(rows=rows)
    returned = run_home_enrichment_stage(
        result_in, collection_mode="home_sns", home_enrichment_fn=old_style_home_fn,
        pause_event=threading.Event(), stop_event=threading.Event(),
        on_log=on_log, on_status=lambda m: None, on_progress=lambda *a, **k: None,
    )

    ok = (
        returned["home_success_count"] == 7
        and returned["home_processed_success_count"] == 7
        and returned["home_link_found_count"] == 7
        and returned["home_no_link_count"] == 0
        and returned["home_retry_count"] == 0
        and returned["home_failure_count"] == 1
    )
    if ok:
        reporter.pass_("UI-HOME-STAGE-6. 신규 통계 필드가 없는 구 schema fake: processed/link_found가 home_success_count로 대체, no_link/retry=0 하위 호환")
    else:
        reporter.fail(f"UI-HOME-STAGE-6 실패: returned={returned}")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-7: 중단·부분 결과
# --------------------------------------------------------------------------

def check_partial_stop_stats_preserved(reporter: ValidationReporter) -> None:
    from src.ui_home_stage import run_home_enrichment_stage

    rows = [{"place_id": "1"}, {"place_id": "2"}, {"place_id": "3"}]
    home_fn = SpyHomeEnrichmentFn({
        "rows": rows, "stop_reason": "user_stopped", "security_blocked": False,
        "home_success_count": 1, "home_processed_success_count": 1,
        "home_link_found_count": 1, "home_no_link_count": 0,
        "failure_count": 0, "not_attempted_count": 2,
    })
    result_in = _base_collection_result(rows=rows)

    returned = run_home_enrichment_stage(
        result_in, collection_mode="home_sns", home_enrichment_fn=home_fn,
        pause_event=threading.Event(), stop_event=threading.Event(),
        on_log=lambda m: None, on_status=lambda m: None, on_progress=lambda *a, **k: None,
    )

    ok = (
        returned["home_stop_reason"] == "user_stopped"
        and returned["home_success_count"] == 1
        and returned["home_failure_count"] == 0
        and returned["home_not_attempted_count"] == 2
    )
    if ok:
        reporter.pass_("UI-HOME-STAGE-7. 중단(user_stopped) 부분 결과: home_stop_reason/성공/실패/미시도 통계가 정확히 반영됨")
    else:
        reporter.fail(f"UI-HOME-STAGE-7 실패: returned={returned}")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-8: 개별 실패 로그 형식·순서
# --------------------------------------------------------------------------

def check_failure_log_lines_format_and_order(reporter: ValidationReporter) -> None:
    from src.ui_home_stage import run_home_enrichment_stage

    on_log = LogCollector()
    rows = [{"place_id": "1"}, {"place_id": "2"}]
    final_failures = [
        {"place_id": "1", "name": "업체1", "status": "timeout", "http_status": None, "attempt": 2, "elapsed_ms": 15000},
        {"place_id": "2", "name": "업체2", "status": "http_5xx", "http_status": 503, "attempt": 1, "elapsed_ms": 200},
    ]
    home_fn = SpyHomeEnrichmentFn({
        "rows": rows, "home_success_count": 0, "failure_count": 2, "not_attempted_count": 0,
        "final_failures": final_failures,
    })
    result_in = _base_collection_result(rows=rows)

    run_home_enrichment_stage(
        result_in, collection_mode="home_sns", home_enrichment_fn=home_fn,
        pause_event=threading.Event(), stop_event=threading.Event(),
        on_log=on_log, on_status=lambda m: None, on_progress=lambda *a, **k: None,
    )

    expected_line_1 = (
        "[ui][network][home][실패 1/2] 업체명=업체1 place_id=1 "
        "원인=timeout HTTP=None 시도=2 응답시간=15000ms"
    )
    expected_line_2 = (
        "[ui][network][home][실패 2/2] 업체명=업체2 place_id=2 "
        "원인=http_5xx HTTP=503 시도=1 응답시간=200ms"
    )
    failure_logs = [m for m in on_log.messages if m.startswith("[ui][network][home][실패")]
    if failure_logs == [expected_line_1, expected_line_2]:
        reporter.pass_("UI-HOME-STAGE-8. 개별 실패 로그가 원본과 문자 단위로 동일한 순서·형식으로 출력됨")
    else:
        reporter.fail(f"UI-HOME-STAGE-8 실패: failure_logs={failure_logs}")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-9~10: diagnostics 저장 성공/실패
# --------------------------------------------------------------------------

def check_diagnostics_save_success(reporter: ValidationReporter) -> None:
    import re
    from src import ui_home_stage
    from src.diagnostics import DiagnosticArtifact

    on_log = LogCollector()
    rows = [{"place_id": "1"}]
    home_fn = SpyHomeEnrichmentFn({
        "rows": rows, "home_success_count": 1,
        "diagnostics_report": {"run_id": "test-run", "target_count": 1},
    })
    result_in = _base_collection_result(rows=rows)

    save_calls: list = []

    def fake_save_json_artifact(run_dir, name, data):
        save_calls.append((run_dir, name, data))
        return DiagnosticArtifact(name=name, path=run_dir / name, success=True)

    original_save = ui_home_stage.save_json_artifact
    ui_home_stage.save_json_artifact = fake_save_json_artifact
    try:
        ui_home_stage.run_home_enrichment_stage(
            result_in, collection_mode="home_sns", home_enrichment_fn=home_fn,
            pause_event=threading.Event(), stop_event=threading.Event(),
            on_log=on_log, on_status=lambda m: None, on_progress=lambda *a, **k: None,
        )
    finally:
        ui_home_stage.save_json_artifact = original_save

    ok = (
        len(save_calls) == 1
        and save_calls[0][0] == ui_home_stage.DEFAULT_DIAGNOSTICS_ROOT
        and re.fullmatch(r"home_enrichment_\d{8}_\d{6}\.json", save_calls[0][1])
        and save_calls[0][2] == {"run_id": "test-run", "target_count": 1}
        and any(m.startswith("[ui][network][home] 실패 진단 저장: ") for m in on_log.messages)
    )
    if ok:
        reporter.pass_("UI-HOME-STAGE-9. diagnostics 저장 성공: DEFAULT_DIAGNOSTICS_ROOT/파일명 패턴/report 인자 그대로 전달 + 성공 로그")
    else:
        reporter.fail(f"UI-HOME-STAGE-9 실패: save_calls={save_calls}, logs={on_log.messages}")


def check_diagnostics_save_failure_isolated(reporter: ValidationReporter) -> None:
    """UI-HOME-STAGE-10: save_json_artifact가 예외를 던져도(또는
    success=False를 반환해도) run_home_enrichment_stage는 예외를 전파하지
    않고 result를 정상 반환한다(export 흐름을 막지 않음)."""
    from src import ui_home_stage
    from src.diagnostics import DiagnosticArtifact

    # (a) success=False 반환(예외 아님)
    on_log_a = LogCollector()
    home_fn_a = SpyHomeEnrichmentFn({
        "rows": [{"place_id": "1"}], "home_success_count": 1,
        "diagnostics_report": {"run_id": "a"},
    })
    original_save = ui_home_stage.save_json_artifact
    ui_home_stage.save_json_artifact = lambda run_dir, name, data: DiagnosticArtifact(
        name=name, path=None, success=False, error_message="disk full"
    )
    try:
        returned_a = ui_home_stage.run_home_enrichment_stage(
            _base_collection_result(rows=[{"place_id": "1"}]),
            collection_mode="home_sns", home_enrichment_fn=home_fn_a,
            pause_event=threading.Event(), stop_event=threading.Event(),
            on_log=on_log_a, on_status=lambda m: None, on_progress=lambda *a, **k: None,
        )
    finally:
        ui_home_stage.save_json_artifact = original_save

    case_a_ok = (
        returned_a is not None
        and "[ui][network][home] 진단 저장 실패: disk full" in on_log_a.messages
    )

    # (b) mkdir/save 자체가 예외를 던짐
    on_log_b = LogCollector()
    home_fn_b = SpyHomeEnrichmentFn({
        "rows": [{"place_id": "1"}], "home_success_count": 1,
        "diagnostics_report": {"run_id": "b"},
    })
    ui_home_stage.save_json_artifact = lambda run_dir, name, data: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        returned_b = ui_home_stage.run_home_enrichment_stage(
            _base_collection_result(rows=[{"place_id": "1"}]),
            collection_mode="home_sns", home_enrichment_fn=home_fn_b,
            pause_event=threading.Event(), stop_event=threading.Event(),
            on_log=on_log_b, on_status=lambda m: None, on_progress=lambda *a, **k: None,
        )
    except Exception as exc:
        reporter.fail(f"UI-HOME-STAGE-10. save_json_artifact 예외가 밖으로 전파됨: {exc!r}")
        return
    finally:
        ui_home_stage.save_json_artifact = original_save

    case_b_ok = (
        returned_b is not None
        and "[ui][network][home] 진단 저장 실패: RuntimeError: boom" in on_log_b.messages
    )

    if case_a_ok and case_b_ok:
        reporter.pass_("UI-HOME-STAGE-10. diagnostics 저장 실패(success=False/예외 둘 다)가 밖으로 전파되지 않고 실패 로그만 남긴 채 result 정상 반환")
    else:
        reporter.fail(f"UI-HOME-STAGE-10 실패: case_a_ok={case_a_ok}(logs={on_log_a.messages}), case_b_ok={case_b_ok}(logs={on_log_b.messages})")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-11: 현재 예외 전파 동작(정책 아님 - 회귀 감지용)
# --------------------------------------------------------------------------

def check_current_behavior_home_enrichment_exception_propagates(reporter: ValidationReporter) -> None:
    """home_enrichment_fn이 예상 밖 예외를 던지면 run_home_enrichment_stage는
    이를 흡수하지 않고 그대로 전파한다 - 이번 이동에서 만든 정책이 아니라
    이동 전 _run_network_pipeline의 기존 동작을 그대로 보존한 것이다(§7
    요청서). 이 테스트는 "이래야 한다"는 제품 계약이 아니라, 이 예외 경계가
    향후 조용히 바뀌지 않았는지 감지하는 용도다 - 개선이 필요하면 별도
    작업으로 의도적으로 이 테스트부터 수정해야 한다."""
    from src.ui_home_stage import run_home_enrichment_stage

    def boom(rows, **kwargs):
        raise RuntimeError("home enrichment crashed")

    result_in = _base_collection_result(rows=[{"place_id": "1"}])
    try:
        run_home_enrichment_stage(
            result_in, collection_mode="home_sns", home_enrichment_fn=boom,
            pause_event=threading.Event(), stop_event=threading.Event(),
            on_log=lambda m: None, on_status=lambda m: None, on_progress=lambda *a, **k: None,
        )
    except RuntimeError as exc:
        if str(exc) == "home enrichment crashed":
            reporter.pass_("UI-HOME-STAGE-11(현재 동작). home_enrichment_fn 예외가 흡수되지 않고 그대로 전파됨(이동 전과 동일 - 제품 정책 아님)")
        else:
            reporter.fail(f"UI-HOME-STAGE-11. 예외는 전파됐으나 내용이 다름: {exc!r}")
        return
    reporter.fail("UI-HOME-STAGE-11. home_enrichment_fn 예외가 전파되지 않음(이동 전과 동작이 달라짐)")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-12: 입력 result의 Collection 전용 key 보존
# --------------------------------------------------------------------------

def check_input_result_keys_preserved(reporter: ValidationReporter) -> None:
    from src.ui_home_stage import run_home_enrichment_stage

    for mode in ("basic", "home_sns"):
        rows = [{"place_id": "1"}]
        home_fn = SpyHomeEnrichmentFn({"rows": rows, "home_success_count": 1})
        result_in = _base_collection_result(
            rows=rows, stop_reason="target_reached", final_count=1,
            security_diagnostics={"json_saved": True}, duplicate_removed_count=3,
        )
        returned = run_home_enrichment_stage(
            result_in, collection_mode=mode,
            home_enrichment_fn=_home_enrichment_fn_must_not_be_called if mode == "basic" else home_fn,
            pause_event=threading.Event(), stop_event=threading.Event(),
            on_log=lambda m: None, on_status=lambda m: None, on_progress=lambda *a, **k: None,
        )
        preserved = (
            returned["stop_reason"] == "target_reached"
            and returned["final_count"] == 1
            and returned["security_diagnostics"] == {"json_saved": True}
            and returned["duplicate_removed_count"] == 3
            and returned["executed_query_count"] == 1
        )
        if not preserved:
            reporter.fail(f"UI-HOME-STAGE-12 실패({mode} 모드): returned={returned}")
            return

    reporter.pass_("UI-HOME-STAGE-12. basic/home_sns 두 모드 모두 Collection 전용 key(stop_reason/final_count/security_diagnostics/duplicate_removed_count 등)가 손실 없이 보존됨")


# --------------------------------------------------------------------------
# UI-HOME-STAGE-13: UI 연결 구조(src/ui.py가 신규 함수를 배선)
# --------------------------------------------------------------------------

def check_ui_wires_new_module_without_duplicate_code(reporter: ValidationReporter) -> None:
    ui_path = ROOT_DIR / "src" / "ui.py"
    tree = _parse_module_ast(ui_path)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.ui_home_stage":
            imported.update(alias.name for alias in node.names)

    try:
        from src import ui
        pipeline_source = inspect.getsource(ui.SalesDbCrawlerApp._run_network_pipeline)
    except Exception as exc:
        reporter.fail(f"UI-HOME-STAGE-13. src.ui import/introspection 실패: {exc!r}")
        return

    call_count = pipeline_source.count("run_home_enrichment_stage(")
    inline_leftover = 'result["home_stop_reason"] = None' in pipeline_source

    ok = (
        "run_home_enrichment_stage" in imported
        and call_count == 1
        and not inline_leftover
    )
    if ok:
        reporter.pass_("UI-HOME-STAGE-13. src/ui.py가 run_home_enrichment_stage를 import하고 _run_network_pipeline에서 정확히 1회 호출하며, 인라인 Home stage 코드 잔존 없음")
    else:
        reporter.fail(f"UI-HOME-STAGE-13 실패: imported={imported}, call_count={call_count}, inline_leftover={inline_leftover}")


def main() -> int:
    reporter = ValidationReporter()

    check_new_module_api_exists(reporter)
    check_function_defined_in_new_module(reporter)
    check_new_module_has_no_gui_dependency(reporter)
    check_basic_mode_skips_enrichment(reporter)
    check_home_sns_success_calls_once_and_merges(reporter)
    check_should_continue_reflects_stop_event(reporter)
    check_old_schema_fallback(reporter)
    check_partial_stop_stats_preserved(reporter)
    check_failure_log_lines_format_and_order(reporter)
    check_diagnostics_save_success(reporter)
    check_diagnostics_save_failure_isolated(reporter)
    check_current_behavior_home_enrichment_exception_propagates(reporter)
    check_input_result_keys_preserved(reporter)
    check_ui_wires_new_module_without_duplicate_code(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
