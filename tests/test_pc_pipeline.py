import json
from pathlib import Path
import shutil
import sys


# Stage 1 청크4: src/pc/pipeline.py collect_pc_full() 계약 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.config import DiagnosticConfig
from src.pc.diagnostics import DEFAULT_DIAGNOSTICS_ROOT
from src.pc.pipeline import collect_pc_full


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

    def warn(self, message: str) -> None:
        self.warn_count += 1
        print(f"[WARN] {message}")

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print("검증 요약")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"WARN: {self.warn_count}")
        print(f"FINAL: {final}")
        print("====================")


class FakePage:
    def __init__(self, url="https://map.naver.com/v5/search/test", html="<html>fake</html>"):
        self.url = url
        self._html = html

    def content(self):
        return self._html

    def screenshot(self, path=None, full_page=False):
        Path(path).write_bytes(b"fake-png-bytes")

    @property
    def frames(self):
        return []


def mock_collector_success(keyword, limit, new_open_only, stop_event, pause_event, results):
    results.append({"업체명": "A카페"})
    results.append({"업체명": "B카페"})


def mock_collector_partial_timeout(keyword, limit, new_open_only, stop_event, pause_event, results):
    results.append({"업체명": "A카페"})
    results.append({"업체명": "B카페"})
    raise TimeoutError("Timeout 3000ms exceeded.")


def make_captcha_collector(page):
    def _collector(keyword, limit, new_open_only, stop_event, pause_event, results):
        results.append({"업체명": "C카페"})
        exc = TimeoutError(
            'Timeout 3000ms exceeded. <div id="wtm-captcha-root">...</div> '
            "subtree intercepts pointer events"
        )
        exc.page = page
        raise exc

    return _collector


def check_success_path(reporter: ValidationReporter) -> None:
    partial_calls = []
    result = collect_pc_full(
        "강동구 카페",
        limit=10,
        collector=mock_collector_success,
        on_partial_save=lambda partial: partial_calls.append(partial),
    )
    if result == [{"업체명": "A카페"}, {"업체명": "B카페"}] and not partial_calls:
        reporter.pass_("정상 mock collector -> 전체 결과 반환, on_partial_save 미호출")
    else:
        reporter.fail(f"정상 경로 결과가 예상과 다름: result={result}, partial_calls={partial_calls}")


def check_partial_preserved_on_timeout(reporter: ValidationReporter) -> None:
    result = collect_pc_full("강동구 카페", limit=10, collector=mock_collector_partial_timeout)
    if result == [{"업체명": "A카페"}, {"업체명": "B카페"}]:
        reporter.pass_("TimeoutError 발생해도 2건 보존 반환, 예외 전파 없음")
    else:
        reporter.fail(f"부분 보존 결과가 예상과 다름: {result}")


def check_on_partial_save_called_with_partial_list(reporter: ValidationReporter) -> None:
    captured = []
    result = collect_pc_full(
        "강동구 카페",
        limit=10,
        collector=mock_collector_partial_timeout,
        on_partial_save=lambda partial: captured.append(partial),
    )
    if len(captured) == 1 and captured[0] == result == [{"업체명": "A카페"}, {"업체명": "B카페"}]:
        reporter.pass_("on_partial_save가 정확히 2건 리스트로 1회 호출됨")
    else:
        reporter.fail(f"on_partial_save 호출 결과가 예상과 다름: captured={captured}")


def check_captcha_diagnostics_metadata(reporter: ValidationReporter) -> None:
    page = FakePage()
    config = DiagnosticConfig(capture_artifacts=True)
    before_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()

    result = collect_pc_full(
        "테스트캡차키워드",
        limit=5,
        collector=make_captcha_collector(page),
        diagnostic_config=config,
    )

    after_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    new_dirs = [d for d in (after_dirs - before_dirs) if "테스트캡차키워드" in d.name]

    ok = False
    if result == [{"업체명": "C카페"}] and new_dirs:
        metadata_path = new_dirs[0] / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            safety_meta = metadata.get("safety_decision", {})
            ok = safety_meta.get("reason") == "captcha_or_security_block"

    if ok:
        reporter.pass_("CAPTCHA 예외 + capture_artifacts=True -> metadata.json에 CAPTCHA 분류 기록")
    else:
        reporter.fail(f"CAPTCHA 진단 캡처 결과가 예상과 다름: result={result}, new_dirs={new_dirs}")

    for d in new_dirs:
        shutil.rmtree(d, ignore_errors=True)


def check_stop_pause_event_passthrough(reporter: ValidationReporter) -> None:
    marker_stop = object()
    marker_pause = object()
    captured = {}

    def collector(keyword, limit, new_open_only, stop_event, pause_event, results):
        captured["stop_event"] = stop_event
        captured["pause_event"] = pause_event
        results.append({"업체명": "D카페"})

    collect_pc_full(
        "강동구 카페",
        stop_event=marker_stop,
        pause_event=marker_pause,
        collector=collector,
    )

    if captured.get("stop_event") is marker_stop and captured.get("pause_event") is marker_pause:
        reporter.pass_("stop_event/pause_event가 collector에 동일 객체로 전달됨(is 비교)")
    else:
        reporter.fail(f"stop_event/pause_event 전달이 예상과 다름: {captured}")


def check_collector_none_raises_not_implemented(reporter: ValidationReporter) -> None:
    try:
        collect_pc_full("강동구 카페", collector=None)
        reporter.fail("collector=None인데 NotImplementedError가 발생하지 않음")
    except NotImplementedError:
        reporter.pass_("collector=None -> NotImplementedError 발생")
    except Exception as exc:
        reporter.fail(f"collector=None인데 예상과 다른 예외 발생: {type(exc).__name__}: {exc}")


def check_default_config_no_artifacts(reporter: ValidationReporter) -> None:
    page = FakePage()
    before_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()

    collect_pc_full(
        "기본설정테스트키워드",
        collector=make_captcha_collector(page),
        # diagnostic_config 미지정 -> DiagnosticConfig.safe_default() (capture_artifacts=False)
    )

    after_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    new_dirs = [d for d in (after_dirs - before_dirs) if "기본설정테스트키워드" in d.name]

    if not new_dirs:
        reporter.pass_("diagnostic_config 미지정(기본 안전 모드) -> fake page 있어도 진단 산출물 미생성")
    else:
        reporter.fail(f"기본 설정인데 진단 산출물이 생성됨: {new_dirs}")
        for d in new_dirs:
            shutil.rmtree(d, ignore_errors=True)


def check_capture_artifacts_false_no_artifacts(reporter: ValidationReporter) -> None:
    page = FakePage()
    config = DiagnosticConfig(capture_artifacts=False)
    before_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()

    collect_pc_full(
        "캡처끔테스트키워드",
        collector=make_captcha_collector(page),
        diagnostic_config=config,
    )

    after_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    new_dirs = [d for d in (after_dirs - before_dirs) if "캡처끔테스트키워드" in d.name]

    if not new_dirs:
        reporter.pass_("capture_artifacts=False -> fake page 있어도 진단 산출물 미생성")
    else:
        reporter.fail(f"capture_artifacts=False인데 진단 산출물이 생성됨: {new_dirs}")
        for d in new_dirs:
            shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    reporter = ValidationReporter()

    check_success_path(reporter)
    check_partial_preserved_on_timeout(reporter)
    check_on_partial_save_called_with_partial_list(reporter)
    check_captcha_diagnostics_metadata(reporter)
    check_stop_pause_event_passthrough(reporter)
    check_collector_none_raises_not_implemented(reporter)
    check_default_config_no_artifacts(reporter)
    check_capture_artifacts_false_no_artifacts(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
