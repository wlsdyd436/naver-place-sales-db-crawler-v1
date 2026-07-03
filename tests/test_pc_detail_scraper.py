from pathlib import Path
import re
import subprocess
import sys


# Stage 3A: src/pc/detail_scraper.py 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.config import DiagnosticConfig
from src.pc.diagnostics import DEFAULT_DIAGNOSTICS_ROOT
from src.pc.pipeline import collect_pc_full
from src.pc.detail_scraper import (
    ENTRY_ADDRESS_SELECTORS,
    DetailCollectionAborted,
    _extract_full_address,
    _extract_phone,
    build_full_collector,
    enrich_with_details,
)


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


# ---------------------------------------------------------------------------
# Fake Playwright 계층 (실 브라우저 없이 상세 진입 시퀀스 시뮬레이션)
# ---------------------------------------------------------------------------


class FakeLD:
    """entryIframe 내부 요소 locator."""

    def __init__(self, count_value=0, text="", attr_map=None):
        self._count = count_value
        self._text = text
        self._attr_map = attr_map or {}

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def inner_text(self, timeout=None):
        return self._text

    def get_attribute(self, name, timeout=None):
        return self._attr_map.get(name)


class FakeEntryFrame:
    def __init__(self, place_id, phone_href=None, address=""):
        self.url = f"https://map.naver.com/entry/place/{place_id}/home"
        self._lm = {}
        if phone_href:
            self._lm["a[href^='tel:']"] = FakeLD(count_value=1, attr_map={"href": phone_href})
        if address:
            self._lm[ENTRY_ADDRESS_SELECTORS[0]] = FakeLD(count_value=1, text=address)

    def locator(self, selector):
        return self._lm.get(selector, FakeLD(count_value=0))


class FakeAnchor:
    def __init__(self, present, on_click=None, click_error=None):
        self._present = present
        self._on_click = on_click
        self._click_error = click_error

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._present else 0

    def click(self, timeout=None):
        if self._click_error is not None:
            raise self._click_error
        if self._on_click is not None:
            self._on_click()


class DetailScenario:
    """place_id -> cfg({present, loads, click_error, phone_href, address})를 보관하고
    클릭에 따라 현재 로드된 entryIframe 상태를 전이한다."""

    def __init__(self, places):
        self.places = places
        self.current_entry_id = None

    def click(self, place_id):
        cfg = self.places.get(place_id, {})
        if cfg.get("click_error") is not None:
            raise cfg["click_error"]
        if cfg.get("loads", True):
            self.current_entry_id = place_id

    def entry_frame(self):
        if self.current_entry_id is None:
            return None
        cfg = self.places.get(self.current_entry_id, {})
        return FakeEntryFrame(
            self.current_entry_id,
            phone_href=cfg.get("phone_href"),
            address=cfg.get("address", ""),
        )


class FakeSearchFrame:
    def __init__(self, scenario):
        self.scenario = scenario

    def locator(self, selector):
        match = re.search(r"(\d+)", selector)
        place_id = match.group(1) if match else ""
        cfg = self.scenario.places.get(place_id, {})
        present = cfg.get("present", True)
        return FakeAnchor(
            present,
            on_click=lambda: self.scenario.click(place_id),
            click_error=cfg.get("click_error"),
        )


class FakePage:
    def __init__(self):
        self.wait_for_timeout_calls = 0

    def wait_for_timeout(self, ms):
        self.wait_for_timeout_calls += 1


class FakeSession:
    def __init__(self, scenario, diagnostic_config):
        self.scenario = scenario
        self.diagnostic_config = diagnostic_config
        self.page = FakePage()
        self.capture_calls = []
        self.keep_open_calls = 0
        self.goto_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def goto(self, url):
        self.goto_calls.append(url)

    def find_search_frame(self):
        return FakeSearchFrame(self.scenario)

    def find_entry_frame(self):
        return self.scenario.entry_frame()

    def capture_diagnostics(self, label, exception=None, safety_decision=None):
        self.capture_calls.append(
            {"label": label, "exception": exception, "safety_decision": safety_decision}
        )
        return "captured"

    def keep_open_if_configured(self):
        self.keep_open_calls += 1


class FakeEvent:
    def __init__(self, initial=False):
        self._set = initial

    def is_set(self):
        return self._set

    def set(self):
        self._set = True


def _row(place_id, name):
    return {
        "업체명": name,
        "업종": "카페",
        "새로오픈여부": "",
        "리뷰수": "10",
        "주소": "서울 강동구 (리스트주소)",
        "대표전화": "",
        "플레이스 URL": f"https://map.naver.com/place/{place_id}/home",
        "place_id": place_id,
        "수집일": "2026-07-03",
    }


# ---------------------------------------------------------------------------
# 1. 추출 유닛
# ---------------------------------------------------------------------------


def check_extract_phone_from_tel_href(reporter: ValidationReporter) -> None:
    frame = FakeEntryFrame("1234567", phone_href="tel:02-123-4567")
    phone = _extract_phone(frame)
    if phone == "02-123-4567":
        reporter.pass_("entryIframe tel: href에서 대표전화 추출 + normalize_phone 적용")
    else:
        reporter.fail(f"대표전화 추출 결과가 예상과 다름: {phone!r}")


def check_extract_full_address(reporter: ValidationReporter) -> None:
    frame = FakeEntryFrame("1234567", address="서울 강동구 천호대로 1001")
    address = _extract_full_address(frame)
    if address == "서울 강동구 천호대로 1001":
        reporter.pass_("entryIframe에서 전체주소 추출")
    else:
        reporter.fail(f"전체주소 추출 결과가 예상과 다름: {address!r}")


# ---------------------------------------------------------------------------
# 2. enrich_with_details 성공/보존
# ---------------------------------------------------------------------------


def check_enrich_success_updates_rows(reporter: ValidationReporter) -> None:
    scenario = DetailScenario(
        {
            "1111111": {"loads": True, "phone_href": "tel:02-111-1111", "address": "서울 강동구 A로 1"},
            "2222222": {"loads": True, "phone_href": "tel:02-222-2222"},
        }
    )
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    rows = [_row("1111111", "A카페"), _row("2222222", "B카페")]

    enrich_with_details(session, session.find_search_frame(), rows)

    ok = (
        rows[0]["대표전화"] == "02-111-1111"
        and rows[0]["주소"] == "서울 강동구 A로 1"
        and rows[1]["대표전화"] == "02-222-2222"
        and rows[1]["주소"] == "서울 강동구 (리스트주소)"  # 상세 주소 없음 -> 리스트 주소 유지
    )
    if ok:
        reporter.pass_("상세 성공 -> 대표전화 채움, 상세주소 있으면 갱신/없으면 리스트주소 유지")
    else:
        reporter.fail(f"enrich 성공 결과가 예상과 다름: {rows}")


def check_enrich_skips_row_without_place_id(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({"1111111": {"loads": True, "phone_href": "tel:02-111-1111"}})
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    no_id_row = _row("", "무ID카페")
    rows = [no_id_row, _row("1111111", "A카페")]

    enrich_with_details(session, session.find_search_frame(), rows)

    if no_id_row["대표전화"] == "" and rows[1]["대표전화"] == "02-111-1111":
        reporter.pass_("place_id 없는 행은 상세 skip(공란 유지), 나머지는 정상 보강")
    else:
        reporter.fail(f"place_id 없는 행 처리 결과가 예상과 다름: {rows}")


def check_enrich_single_failure_skips_without_raise(reporter: ValidationReporter) -> None:
    # 2222222는 클릭해도 entry가 로드되지 않음(loads=False) -> 단건 실패 -> skip
    scenario = DetailScenario(
        {
            "1111111": {"loads": True, "phone_href": "tel:02-111-1111"},
            "2222222": {"loads": False},
            "3333333": {"loads": True, "phone_href": "tel:02-333-3333"},
        }
    )
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    rows = [_row("1111111", "A"), _row("2222222", "B"), _row("3333333", "C")]

    try:
        enrich_with_details(session, session.find_search_frame(), rows)
    except Exception as exc:
        reporter.fail(f"단건 실패가 예외로 전파됨(임계 미만인데): {type(exc).__name__}: {exc}")
        return

    ok = (
        rows[0]["대표전화"] == "02-111-1111"
        and rows[1]["대표전화"] == ""  # 단건 실패 -> 공란 유지
        and rows[2]["대표전화"] == "02-333-3333"  # 실패 후에도 계속 진행
        and len(rows) == 3  # 행 손실 없음
    )
    if ok:
        reporter.pass_("단건 상세 실패 -> 공란 skip + 예외 없이 계속(행 손실 없음)")
    else:
        reporter.fail(f"단건 실패 처리 결과가 예상과 다름: {rows}")


# ---------------------------------------------------------------------------
# 3. 연속 실패 임계 escalation
# ---------------------------------------------------------------------------


def check_enrich_consecutive_failures_raise(reporter: ValidationReporter) -> None:
    places = {str(i) * 7: {"loads": False} for i in range(1, 7)}  # 1111111..6666666 모두 실패
    scenario = DetailScenario(places)
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    rows = [_row(str(i) * 7, f"F{i}") for i in range(1, 7)]

    try:
        enrich_with_details(session, session.find_search_frame(), rows, consecutive_limit=5)
        reporter.fail("연속 실패가 임계를 넘었는데 DetailCollectionAborted가 발생하지 않음")
        return
    except DetailCollectionAborted as exc:
        # exc.page 미부착 확인(마커는 collector 계층에서 부착되므로 여기선 없음)
        if not hasattr(exc, "page"):
            reporter.pass_("연속 실패 임계 초과 -> DetailCollectionAborted raise, exc.page 미부착")
        else:
            reporter.fail("DetailCollectionAborted에 exc.page가 부착됨(계약 위반)")
    except Exception as exc:
        reporter.fail(f"예상과 다른 예외: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# 4. stop / pause
# ---------------------------------------------------------------------------


def check_enrich_stops_on_stop_event(reporter: ValidationReporter) -> None:
    scenario = DetailScenario(
        {
            "1111111": {"loads": True, "phone_href": "tel:02-111-1111"},
            "2222222": {"loads": True, "phone_href": "tel:02-222-2222"},
        }
    )
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    rows = [_row("1111111", "A"), _row("2222222", "B")]
    stop_event = FakeEvent(initial=True)

    enrich_with_details(session, session.find_search_frame(), rows, stop_event=stop_event)

    if rows[0]["대표전화"] == "" and rows[1]["대표전화"] == "":
        reporter.pass_("stop_event가 set이면 상세 보강을 시작하지 않고 즉시 중단")
    else:
        reporter.fail(f"stop_event 무시하고 상세 보강이 진행됨: {rows}")


# ---------------------------------------------------------------------------
# 5. build_full_collector + pipeline 조립
# ---------------------------------------------------------------------------


def _make_session_factory(scenario):
    created = []

    def factory(diagnostic_config):
        session = FakeSession(scenario, diagnostic_config)
        created.append(session)
        return session

    return factory, created


def _fake_list_scrape(rows_to_add):
    def _fn(session, search_frame, keyword, limit, new_open_only, stop_event, pause_event, results):
        for row in rows_to_add:
            results.append(row)

    return _fn


def check_full_collector_success_with_pipeline(reporter: ValidationReporter) -> None:
    scenario = DetailScenario(
        {
            "1111111": {"loads": True, "phone_href": "tel:02-111-1111", "address": "서울 강동구 A로 1"},
            "2222222": {"loads": True, "phone_href": "tel:02-222-2222"},
        }
    )
    factory, created = _make_session_factory(scenario)
    list_fn = _fake_list_scrape([_row("1111111", "A카페"), _row("2222222", "B카페")])
    collector = build_full_collector(
        DiagnosticConfig.safe_default(),
        session_factory=factory,
        list_scrape_fn=list_fn,
        detail_enrich_fn=enrich_with_details,
    )

    partial_calls = []
    result = collect_pc_full(
        "강동구카페",
        limit=30,
        collector=collector,
        on_partial_save=lambda partial: partial_calls.append(partial),
    )

    ok = (
        len(result) == 2
        and result[0]["대표전화"] == "02-111-1111"
        and result[0]["주소"] == "서울 강동구 A로 1"
        and result[1]["대표전화"] == "02-222-2222"
        and result[1]["플레이스 URL"] == "https://map.naver.com/place/2222222/home"
        and not partial_calls
        and len(created) == 1
    )
    if ok:
        reporter.pass_("build_full_collector + pipeline -> list 수집 후 상세 보강된 전체 결과 반환")
    else:
        reporter.fail(f"full collector 정상 조립 결과가 예상과 다름: result={result}, partial={partial_calls}")


def check_full_collector_escalation_contract(reporter: ValidationReporter) -> None:
    # list 단계에서 5행을 쌓고, detail_enrich_fn이 연속 실패로 escalation 예외를 던지도록
    # 실제 enrich_with_details를 쓰되 모든 place가 로드되지 않게 시나리오 구성.
    places = {str(i) * 7: {"loads": False} for i in range(1, 7)}
    scenario = DetailScenario(places)
    factory, created = _make_session_factory(scenario)
    rows_to_add = [_row(str(i) * 7, f"F{i}") for i in range(1, 7)]
    list_fn = _fake_list_scrape(rows_to_add)

    def enrich_limit5(session, search_frame, rows, stop_event=None, pause_event=None):
        return enrich_with_details(
            session, search_frame, rows, stop_event, pause_event, consecutive_limit=5
        )

    collector = build_full_collector(
        DiagnosticConfig(capture_artifacts=True),
        session_factory=factory,
        list_scrape_fn=list_fn,
        detail_enrich_fn=enrich_limit5,
    )

    before_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()

    partial_calls = []
    result = collect_pc_full(
        "강동구상세실패키워드",
        limit=30,
        collector=collector,
        diagnostic_config=DiagnosticConfig(capture_artifacts=True),
        on_partial_save=lambda partial: partial_calls.append(partial),
    )

    after_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    pipeline_level_dirs = [d for d in (after_dirs - before_dirs) if "강동구상세실패키워드" in d.name]

    session = created[0] if created else None
    checks = {
        "list 행 부분 보존 반환(6행)": len(result) == 6,
        "on_partial_save 1회": len(partial_calls) == 1 and partial_calls[0] == result,
        "session.capture_diagnostics 1회(중복 없음)": session is not None
        and len(session.capture_calls) == 1,
        "keep_open_if_configured 1회": session is not None and session.keep_open_calls == 1,
        "pipeline 자체 캡처 no-op(파일 미생성)": pipeline_level_dirs == [],
    }
    if all(checks.values()):
        reporter.pass_(
            "연속 실패 escalation -> 세션 계층 1차 캡처 1회 + 부분 보존 반환 + pipeline no-op"
        )
    else:
        failed = [name for name, ok in checks.items() if not ok]
        reporter.fail(f"escalation 계약 검증 실패 항목: {failed}")


def check_full_collector_marks_exc_without_page(reporter: ValidationReporter) -> None:
    # detail_enrich_fn이 우리가 들고 있는 예외를 던지게 해서, collector가 exc.page를
    # 붙이지 않고 diagnostics_captured 마커만 부착하는지 직접 확인.
    scenario = DetailScenario({})
    factory, created = _make_session_factory(scenario)
    held = {"exc": None}

    def raising_enrich(session, search_frame, rows, stop_event=None, pause_event=None):
        exc = DetailCollectionAborted("강제 escalation")
        held["exc"] = exc
        raise exc

    collector = build_full_collector(
        DiagnosticConfig(capture_artifacts=True),
        session_factory=factory,
        list_scrape_fn=_fake_list_scrape([_row("1111111", "A")]),
        detail_enrich_fn=raising_enrich,
    )

    result = collect_pc_full(
        "마커테스트키워드",
        limit=10,
        collector=collector,
        diagnostic_config=DiagnosticConfig(capture_artifacts=True),
    )

    exc = held["exc"]
    ok = (
        result == [_row("1111111", "A")]
        and exc is not None
        and getattr(exc, "diagnostics_captured", False) is True
        and not hasattr(exc, "page")
    )
    if ok:
        reporter.pass_("collector -> exc에 diagnostics_captured 마커 부착, exc.page 미부착, 부분 보존")
    else:
        reporter.fail(
            f"마커/page 계약 검증 실패: result={result}, "
            f"marker={getattr(exc, 'diagnostics_captured', None)}, has_page={hasattr(exc, 'page')}"
        )


# ---------------------------------------------------------------------------
# 6. 금지 파일 무변경 확인
# ---------------------------------------------------------------------------


def check_protected_files_unchanged(reporter: ValidationReporter) -> None:
    protected_files = [
        "src/pc_crawler.py",
        "src/ui.py",
        "src/exporter.py",
        "src/parser.py",
        "src/crawler.py",
        "src/pc/config.py",
        "src/pc/safety.py",
        "src/pc/diagnostics.py",
        "src/pc/pipeline.py",
    ]
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--"] + protected_files,
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        if result.returncode == 0 and output == "":
            reporter.pass_("금지 파일 9개 모두 git 변경 없음")
        else:
            reporter.fail(f"금지 파일 변경 감지 또는 git 실패: rc={result.returncode}, out={output!r}")
    except Exception as exc:
        reporter.warn(f"git 상태 확인 건너뜀: {exc}")


def main() -> int:
    reporter = ValidationReporter()

    check_extract_phone_from_tel_href(reporter)
    check_extract_full_address(reporter)

    check_enrich_success_updates_rows(reporter)
    check_enrich_skips_row_without_place_id(reporter)
    check_enrich_single_failure_skips_without_raise(reporter)

    check_enrich_consecutive_failures_raise(reporter)

    check_enrich_stops_on_stop_event(reporter)

    check_full_collector_success_with_pipeline(reporter)
    check_full_collector_escalation_contract(reporter)
    check_full_collector_marks_exc_without_page(reporter)

    check_protected_files_unchanged(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
