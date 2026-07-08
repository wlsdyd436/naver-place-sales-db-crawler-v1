from pathlib import Path
import sys
import threading


# Stage 3D: ui._collect_premium_query가 새 PC full engine(collect_pc_full)에 연결됐는지,
# legacy 메서드가 보존됐는지 검증하는 standalone 스크립트(모킹, live/Tk mainloop 없음).
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
    # Tk __init__/mainloop 없이 메서드만 호출하기 위해 __new__로 인스턴스만 만든다.
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)
    app.stop_event = threading.Event()
    app.pause_event = threading.Event()
    app.log = lambda message: None
    return app


class _Saved:
    """ui 모듈 전역을 임시 교체/복원한다."""

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


# ---------------------------------------------------------------------------
# 1. 새 premium 경로 = PC full engine 연결
# ---------------------------------------------------------------------------


def check_premium_uses_pc_full_engine(reporter: ValidationReporter) -> None:
    calls = {}

    class FakeCfg:
        @classmethod
        def from_env(cls):
            calls["from_env"] = True
            return "CFG_SENTINEL"

    def fake_build_full_collector(cfg):
        calls["build_cfg"] = cfg
        return "COLLECTOR_SENTINEL"

    sentinel_rows = [{"업체명": "A", "place_id": "111", "인스타": "https://insta/a"}]

    def fake_collect_pc_full(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return sentinel_rows

    def _boom(*a, **k):
        raise AssertionError("legacy 함수가 새 premium 경로에서 호출됨")

    with _Saved(
        ["DiagnosticConfig", "build_full_collector", "collect_pc_full",
         "parse_places", "safe_merge_places", "crawl_places", "crawl_places_pc"]
    ) as saved:
        saved.set("DiagnosticConfig", FakeCfg)
        saved.set("build_full_collector", fake_build_full_collector)
        saved.set("collect_pc_full", fake_collect_pc_full)
        saved.set("parse_places", _boom)
        saved.set("safe_merge_places", _boom)
        saved.set("crawl_places", _boom)
        saved.set("crawl_places_pc", _boom)

        app = _make_app()
        try:
            result = app._collect_premium_query("서울 강동구 카페", 7, new_open_only=True)
        except AssertionError as exc:
            reporter.fail(f"새 premium 경로가 legacy 함수를 호출함: {exc}")
            return

    checks = {
        "반환 형태 (rows, [], rows)": result == (sentinel_rows, [], sentinel_rows),
        "DiagnosticConfig.from_env 사용": calls.get("from_env") is True,
        "build_full_collector에 cfg 전달": calls.get("build_cfg") == "CFG_SENTINEL",
        "collect_pc_full 위치인자(query, limit)": calls.get("args") == ("서울 강동구 카페", 7),
        "new_open_only 전달": calls.get("kwargs", {}).get("new_open_only") is True,
        "stop/pause 이벤트 전달": (
            calls.get("kwargs", {}).get("stop_event") is app.stop_event
            and calls.get("kwargs", {}).get("pause_event") is app.pause_event
        ),
        "collector/diagnostic_config 전달": (
            calls.get("kwargs", {}).get("collector") == "COLLECTOR_SENTINEL"
            and calls.get("kwargs", {}).get("diagnostic_config") == "CFG_SENTINEL"
        ),
        "on_security_block 콜백 전달": calls.get("kwargs", {}).get("on_security_block") == app._note_security_block,
    }
    if all(checks.values()):
        reporter.pass_("premium 분기가 collect_pc_full로 연결되고 (rows,[],rows) 반환, parse/merge 우회")
    else:
        failed = [name for name, ok in checks.items() if not ok]
        reporter.fail(f"premium 연결 검증 실패 항목: {failed} (calls={calls}, result={result})")


# ---------------------------------------------------------------------------
# SAFE-1: 보안 차단 콜백(_note_security_block) 검증
# ---------------------------------------------------------------------------


def check_note_security_block_sets_instance_state(reporter: ValidationReporter) -> None:
    app = _make_app()
    logged = []
    app.log = lambda message: logged.append(message)

    class FakeDecision:
        reason = type("R", (), {"value": "captcha_or_security_block"})()

    decision = FakeDecision()
    app._note_security_block(decision)

    ok = (
        getattr(app, "_security_block_decision", None) is decision
        and any("보안 확인" in message and "CAPTCHA" in message for message in logged)
    )
    if ok:
        reporter.pass_("_note_security_block 호출 시 인스턴스 상태 세팅 + 감지 로그 출력")
    else:
        reporter.fail(
            f"_note_security_block 결과가 예상과 다름: decision={getattr(app, '_security_block_decision', None)}, logged={logged}"
        )


# ---------------------------------------------------------------------------
# 2. legacy premium 메서드 보존/동작
# ---------------------------------------------------------------------------


def check_legacy_premium_preserved(reporter: ValidationReporter) -> None:
    if not hasattr(ui.SalesDbCrawlerApp, "_collect_premium_query_legacy"):
        reporter.fail("_collect_premium_query_legacy 메서드가 보존되지 않음")
        return

    def fake_crawl_places(*a, **k):
        return [{"업체명": "모바일카페"}]

    def fake_crawl_places_pc(*a, **k):
        return [{"업체명": "PC카페"}]

    def fake_parse_places(raw, mode="basic"):
        return list(raw)

    def fake_safe_merge_places(mobile, pc):
        return [{"업체명": "병합카페"}]

    with _Saved(["crawl_places", "crawl_places_pc", "parse_places", "safe_merge_places"]) as saved:
        saved.set("crawl_places", fake_crawl_places)
        saved.set("crawl_places_pc", fake_crawl_places_pc)
        saved.set("parse_places", fake_parse_places)
        saved.set("safe_merge_places", fake_safe_merge_places)

        app = _make_app()
        merged, mobile, pc = app._collect_premium_query_legacy("서울 강동구 카페", 5)

    ok = (
        merged == [{"업체명": "병합카페"}]
        and mobile == [{"업체명": "모바일카페"}]
        and pc == [{"업체명": "PC카페"}]
    )
    if ok:
        reporter.pass_("legacy premium(_collect_premium_query_legacy) 모바일+PC 병합 경로 보존/동작")
    else:
        reporter.fail(f"legacy premium 결과가 예상과 다름: merged={merged}, mobile={mobile}, pc={pc}")


# ---------------------------------------------------------------------------
# 3. basic 경로 무변경(스모크)
# ---------------------------------------------------------------------------


def check_basic_path_unchanged(reporter: ValidationReporter) -> None:
    def fake_crawl_places(*a, **k):
        return [{"업체명": "베이직카페"}]

    def fake_parse_places(raw, mode="basic"):
        return [{"업체명": "파싱카페", "mode": mode}]

    with _Saved(["crawl_places", "parse_places"]) as saved:
        saved.set("crawl_places", fake_crawl_places)
        saved.set("parse_places", fake_parse_places)

        app = _make_app()
        merged, mobile, pc = app._collect_basic_query("서울 강동구 카페", 5)

    if merged == mobile == [{"업체명": "파싱카페", "mode": "basic"}] and pc == []:
        reporter.pass_("basic 경로 무변경: crawl_places + parse_places(basic), pc 빈 리스트")
    else:
        reporter.fail(f"basic 경로 결과가 예상과 다름: merged={merged}, mobile={mobile}, pc={pc}")


def main() -> int:
    reporter = ValidationReporter()
    check_premium_uses_pc_full_engine(reporter)
    check_legacy_premium_preserved(reporter)
    check_basic_path_unchanged(reporter)
    check_note_security_block_sets_instance_state(reporter)
    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
