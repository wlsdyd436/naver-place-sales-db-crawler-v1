from pathlib import Path
import subprocess
import sys
import types


# Stage 2 청크2: src/pc/list_scraper.py 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.config import DiagnosticConfig
from src.pc.diagnostics import DEFAULT_DIAGNOSTICS_ROOT
from src.pc.pipeline import collect_pc_full
from src.pc.list_scraper import (
    _build_row,
    _check_stop,
    _click_next_page,
    _find_pc_cards,
    _light_scroll_cards,
    _normalize_pc_place_url,
    _parse_place_id,
    _wait_while_paused,
    build_collector,
    scrape_list,
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


class FakeLocator:
    def __init__(
        self,
        count_value=0,
        text="",
        attr_map=None,
        visible=True,
        click_error=None,
        sub_locators=None,
        nth_items=None,
    ):
        self._count = count_value
        self._text = text
        self._attr_map = attr_map or {}
        self._visible = visible
        self._click_error = click_error
        self._sub_locators = sub_locators or {}
        self._nth_items = nth_items or []

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def nth(self, index):
        return self._nth_items[index]

    def locator(self, selector):
        return self._sub_locators.get(selector, FakeLocator(count_value=0))

    def is_visible(self, timeout=None):
        if isinstance(self._visible, Exception):
            raise self._visible
        return self._visible

    def click(self, timeout=None):
        if self._click_error is not None:
            raise self._click_error

    def inner_text(self, timeout=None):
        return self._text

    def get_attribute(self, name, timeout=None):
        return self._attr_map.get(name)


class FakeFrame:
    def __init__(self, locator_map=None):
        self._locator_map = locator_map or {}

    def locator(self, selector):
        return self._locator_map.get(selector, FakeLocator(count_value=0))


class SequenceCountLocator:
    """count() 호출마다 미리 정해둔 시퀀스 값을 순서대로 반환하는 fake anchors."""

    def __init__(self, counts):
        self._counts = list(counts)
        self._index = 0

    def count(self):
        value = self._counts[min(self._index, len(self._counts) - 1)]
        self._index += 1
        return value


class FakeMouse:
    def __init__(self):
        self.wheel_calls = 0

    def wheel(self, dx, dy):
        self.wheel_calls += 1


class FakePage:
    def __init__(self):
        self.mouse = FakeMouse()
        self.wait_for_timeout_calls = []

    def wait_for_timeout(self, ms):
        self.wait_for_timeout_calls.append(ms)


class FakeEvent:
    def __init__(self, initial=False):
        self._set = initial

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def clear(self):
        self._set = False


class FakeBrowserSession:
    def __init__(self, diagnostic_config):
        self.diagnostic_config = diagnostic_config
        self.page = object()
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
        return object()

    def capture_diagnostics(self, label, exception=None, safety_decision=None):
        self.capture_calls.append(
            {"label": label, "exception": exception, "safety_decision": safety_decision}
        )
        return "captured"

    def keep_open_if_configured(self):
        self.keep_open_calls += 1


def _make_session_factory():
    created = []

    def factory(diagnostic_config):
        session = FakeBrowserSession(diagnostic_config)
        created.append(session)
        return session

    return factory, created


def fake_scrape_success(session, frame, keyword, limit, new_open_only, stop_event, pause_event, results):
    results.append({"업체명": "A카페"})
    results.append({"업체명": "B카페"})


def make_fake_scrape_timeout(captured_exceptions):
    def _fn(session, frame, keyword, limit, new_open_only, stop_event, pause_event, results):
        results.append({"업체명": "A카페"})
        results.append({"업체명": "B카페"})
        exc = TimeoutError(
            'Timeout 3000ms exceeded. <div id="wtm-captcha-root">...</div> '
            "subtree intercepts pointer events"
        )
        captured_exceptions.append(exc)
        raise exc

    return _fn


# ---------------------------------------------------------------------------
# 1. 카드 탐색
# ---------------------------------------------------------------------------


def check_find_pc_cards_primary_selector(reporter: ValidationReporter) -> None:
    frame = FakeFrame(
        locator_map={"li:has(a[href*='/place/'])": FakeLocator(count_value=3)}
    )
    cards = _find_pc_cards(frame)
    if cards.count() == 3:
        reporter.pass_("주 카드 selector(li:has(...))가 매칭되면 그 결과를 바로 사용")
    else:
        reporter.fail(f"주 카드 selector 결과가 예상과 다름: count={cards.count()}")


def check_find_pc_cards_fallback_to_anchor_ancestor(reporter: ValidationReporter) -> None:
    frame = FakeFrame(
        locator_map={
            "li:has(a[href*='/place/'])": FakeLocator(count_value=0),
            "a[href*='/place/']": FakeLocator(
                count_value=2,
                sub_locators={"xpath=ancestor::li[1]": FakeLocator(count_value=2)},
            ),
        }
    )
    cards = _find_pc_cards(frame)
    if cards.count() == 2:
        reporter.pass_("주 selector 실패 시 anchor->ancestor xpath fallback으로 카드 탐색")
    else:
        reporter.fail(f"fallback 카드 탐색 결과가 예상과 다름: count={cards.count()}")


# ---------------------------------------------------------------------------
# 2. 스크롤 동작
# ---------------------------------------------------------------------------


def check_light_scroll_cards_stops_after_two_no_growth(reporter: ValidationReporter) -> None:
    page = FakePage()
    anchors = SequenceCountLocator(counts=[5, 8, 8, 8])
    _light_scroll_cards(page, anchors, max_scrolls=8, stop_event=None, pause_event=None)
    if page.mouse.wheel_calls == 12:
        reporter.pass_("카드 수 증가가 2회 연속 멈추면 max_scrolls(8) 전에 스크롤 중단(wheel 12회=3회x4)")
    else:
        reporter.fail(f"스크롤 조기 중단 로직이 예상과 다름: wheel_calls={page.mouse.wheel_calls}")


def check_light_scroll_cards_stops_on_stop_event(reporter: ValidationReporter) -> None:
    page = FakePage()
    anchors = SequenceCountLocator(counts=[0, 5, 10, 15, 20, 25, 30, 35])
    stop_event = FakeEvent(initial=True)
    _light_scroll_cards(page, anchors, max_scrolls=8, stop_event=stop_event, pause_event=None)
    if page.mouse.wheel_calls == 0:
        reporter.pass_("stop_event가 이미 set이면 스크롤을 아예 시작하지 않음")
    else:
        reporter.fail(f"stop_event 무시하고 스크롤이 진행됨: wheel_calls={page.mouse.wheel_calls}")


def check_light_scroll_cards_skips_when_target_already_met(reporter: ValidationReporter) -> None:
    """OPT-A: 이미 target_count 이상이면 스크롤을 아예 생략한다."""
    page = FakePage()
    anchors = SequenceCountLocator(counts=[10])
    _light_scroll_cards(
        page, anchors, max_scrolls=8, stop_event=None, pause_event=None, target_count=5
    )
    if page.mouse.wheel_calls == 0:
        reporter.pass_("target_count 이미 충족(10>=5) -> 스크롤 0회로 생략")
    else:
        reporter.fail(f"target_count 충족했는데 스크롤이 수행됨: wheel_calls={page.mouse.wheel_calls}")


def check_light_scroll_cards_stops_early_when_target_reached_mid_loop(reporter: ValidationReporter) -> None:
    """OPT-A: 스크롤 도중 target_count에 도달하면 max_scrolls를 다 쓰기 전에 조기 종료한다.

    counts는 계속 증가하는 시퀀스라 target_count 게이트가 없으면 no_new_cards 조건이
    트리거되지 않아 max_scrolls(8)까지 진행(wheel 32회)한다. target_count=6이면
    2번째 스크롤에서 count=6에 도달해 wheel 8회(2회x4)만에 멈춰야 한다.
    """
    page = FakePage()
    anchors = SequenceCountLocator(counts=[2, 4, 6, 8, 10, 12, 14, 16])
    _light_scroll_cards(
        page, anchors, max_scrolls=8, stop_event=None, pause_event=None, target_count=6
    )
    if page.mouse.wheel_calls == 8:
        reporter.pass_("target_count(6) 도달 시 max_scrolls(8) 전에 조기 종료(wheel 8회=2회x4)")
    else:
        reporter.fail(f"target_count 조기 종료가 예상과 다름: wheel_calls={page.mouse.wheel_calls}")


def check_light_scroll_cards_target_count_none_unchanged(reporter: ValidationReporter) -> None:
    """OPT-A: target_count=None(기본값)이면 기존 2회 무성장 중단 동작이 그대로 유지된다."""
    page = FakePage()
    anchors = SequenceCountLocator(counts=[5, 8, 8, 8])
    _light_scroll_cards(page, anchors, max_scrolls=8, stop_event=None, pause_event=None, target_count=None)
    if page.mouse.wheel_calls == 12:
        reporter.pass_("target_count=None -> 기존 2회 무성장 중단 동작 불변(wheel 12회)")
    else:
        reporter.fail(f"target_count=None인데 기존 동작이 바뀜: wheel_calls={page.mouse.wheel_calls}")


# ---------------------------------------------------------------------------
# 3. 페이지네이션 4셀렉터
# ---------------------------------------------------------------------------


def check_click_next_page_uses_last_matching_selector(reporter: ValidationReporter) -> None:
    frame = FakeFrame(
        locator_map={
            'a:text-is("2")': FakeLocator(count_value=0),
            'button:text-is("2")': FakeLocator(count_value=0),
            'a:has-text("2")': FakeLocator(count_value=0),
            'button:has-text("2")': FakeLocator(count_value=1, visible=True),
        }
    )
    result = _click_next_page(frame, 2)
    if result is True:
        reporter.pass_("4개 후보 selector를 순서대로 시도해 마지막 selector로 클릭 성공")
    else:
        reporter.fail(f"페이지네이션 클릭 결과가 예상과 다름: {result}")


def check_click_next_page_propagates_click_failure(reporter: ValidationReporter) -> None:
    click_error = TimeoutError(
        'Timeout 3000ms exceeded. <div id="wtm-captcha-root">...</div> '
        "subtree intercepts pointer events"
    )
    frame = FakeFrame(
        locator_map={
            'a:text-is("3")': FakeLocator(count_value=1, visible=True, click_error=click_error),
        }
    )
    try:
        _click_next_page(frame, 3)
        reporter.fail("클릭이 가로채였는데(intercept) 예외가 전파되지 않음")
    except TimeoutError as exc:
        if "wtm-captcha-root" in str(exc):
            reporter.pass_("클릭 실패(intercept)는 삼키지 않고 그대로 전파(CAPTCHA 신호 보존)")
        else:
            reporter.fail(f"예외는 전파됐지만 메시지가 예상과 다름: {exc}")


def check_click_next_page_swallows_visibility_check_and_tries_next(reporter: ValidationReporter) -> None:
    frame = FakeFrame(
        locator_map={
            'a:text-is("4")': FakeLocator(count_value=1, visible=RuntimeError("visibility check failed")),
            'button:text-is("4")': FakeLocator(count_value=1, visible=True),
        }
    )
    result = _click_next_page(frame, 4)
    if result is True:
        reporter.pass_("존재/visible 확인 단계의 예외는 삼키고 다음 selector로 진행")
    else:
        reporter.fail(f"visibility 확인 예외 처리 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 4. row dict 생성
# ---------------------------------------------------------------------------


def _make_card_with_name(card_text: str, name: str) -> FakeLocator:
    name_locator = FakeLocator(count_value=1, text=name)
    anchor_locator = FakeLocator(count_value=1, sub_locators={"span.place_bluelink": name_locator})
    return FakeLocator(
        count_value=1,
        text=card_text,
        sub_locators={"a[href*='/place/']": anchor_locator},
    )


def _make_card_with_href(card_text: str, name: str, href: str) -> FakeLocator:
    name_locator = FakeLocator(count_value=1, text=name)
    anchor_locator = FakeLocator(
        count_value=1,
        attr_map={"href": href},
        sub_locators={"span.place_bluelink": name_locator},
    )
    return FakeLocator(
        count_value=1,
        text=card_text,
        sub_locators={"a[href*='/place/']": anchor_locator},
    )


def check_build_row_success(reporter: ValidationReporter) -> None:
    card_text = "테스트카페 카페,디저트\n리뷰 128\n서울 강남구 역삼동 123-4"
    card = _make_card_with_name(card_text, "테스트카페")
    row = _build_row(card, "2026-07-03", new_open_only=False, seen=set())

    expected = {
        "업체명": "테스트카페",
        "업종": "카페,디저트",
        "새로오픈여부": "",
        "리뷰수": "128",
        "주소": "서울 강남구 역삼동",
        "대표전화": "",
        "플레이스 URL": "",
        "place_id": "",
        "수집일": "2026-07-03",
    }
    if row == expected:
        reporter.pass_("정상 카드 -> 업체명/업종/리뷰수/주소/대표전화/플레이스 URL/place_id/수집일 dict 생성")
    else:
        reporter.fail(f"row dict 결과가 예상과 다름: {row}")


def check_build_row_captures_place_id_and_url(reporter: ValidationReporter) -> None:
    card_text = "테스트카페 카페,디저트\n리뷰 128\n서울 강남구 역삼동 123-4"
    card = _make_card_with_href(card_text, "테스트카페", "/place/1234567/home")
    row = _build_row(card, "2026-07-03", new_open_only=False, seen=set())

    if (
        row is not None
        and row.get("place_id") == "1234567"
        and row.get("플레이스 URL") == "https://map.naver.com/place/1234567/home"
    ):
        reporter.pass_("anchor href에서 place_id/플레이스 URL 가산 필드 확보(상세 진입 없이)")
    else:
        reporter.fail(f"place_id/플레이스 URL 가산 필드 결과가 예상과 다름: {row}")


def check_parse_place_id_and_url_helpers(reporter: ValidationReporter) -> None:
    checks = {
        "place_id from /restaurant/": _parse_place_id("/restaurant/987654/home") == "987654",
        "place_id 없음 -> 빈 문자열": _parse_place_id("/foo/bar") == "",
        "절대 URL 유지": _normalize_pc_place_url("https://pcmap.place.naver.com/restaurant/1")
        == "https://pcmap.place.naver.com/restaurant/1",
        "루트상대 -> 도메인 prefix": _normalize_pc_place_url("/place/1")
        == "https://map.naver.com/place/1",
        "빈 href -> 빈 문자열": _normalize_pc_place_url("") == "",
    }
    if all(checks.values()):
        reporter.pass_("_parse_place_id / _normalize_pc_place_url 헬퍼 동작 검증")
    else:
        failed = [name for name, ok in checks.items() if not ok]
        reporter.fail(f"place_id/URL 헬퍼 검증 실패 항목: {failed}")


def check_build_row_skips_when_no_review_keyword(reporter: ValidationReporter) -> None:
    card_text = "테스트카페 카페,디저트\n서울 강남구 역삼동 123-4"
    card = _make_card_with_name(card_text, "테스트카페")
    row = _build_row(card, "2026-07-03", new_open_only=False, seen=set())
    if row is None:
        reporter.pass_("카드 텍스트에 '리뷰'가 없으면 None 반환(스킵)")
    else:
        reporter.fail(f"'리뷰' 키워드 없는 카드가 스킵되지 않음: {row}")


def check_build_row_skips_duplicate_name(reporter: ValidationReporter) -> None:
    card_text = "테스트카페 카페,디저트\n리뷰 128\n서울 강남구 역삼동 123-4"
    card = _make_card_with_name(card_text, "테스트카페")
    seen = {"테스트카페"}
    row = _build_row(card, "2026-07-03", new_open_only=False, seen=seen)
    if row is None:
        reporter.pass_("이미 seen에 있는 업체명은 None 반환(중복 스킵)")
    else:
        reporter.fail(f"중복 업체명이 스킵되지 않음: {row}")


# ---------------------------------------------------------------------------
# 5. 실패 주입: classify -> capture(session) -> mark -> exc.page 미부착
# ---------------------------------------------------------------------------


def check_failure_contract_classify_capture_mark_no_page(reporter: ValidationReporter) -> None:
    factory, created = _make_session_factory()
    captured_exceptions = []
    scrape_fn = make_fake_scrape_timeout(captured_exceptions)
    config = DiagnosticConfig(capture_artifacts=True)
    collector = build_collector(config, session_factory=factory, scrape_fn=scrape_fn)

    before_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()

    partial_calls = []
    result = collect_pc_full(
        "실패계약테스트키워드",
        limit=10,
        collector=collector,
        diagnostic_config=config,
        on_partial_save=lambda partial: partial_calls.append(partial),
    )

    after_dirs = set(DEFAULT_DIAGNOSTICS_ROOT.glob("*")) if DEFAULT_DIAGNOSTICS_ROOT.exists() else set()
    pipeline_level_dirs = [d for d in (after_dirs - before_dirs) if "실패계약테스트키워드" in d.name]

    session = created[0] if created else None
    exc = captured_exceptions[0] if captured_exceptions else None

    checks = {
        "부분 보존 반환": result == [{"업체명": "A카페"}, {"업체명": "B카페"}],
        "on_partial_save 1회 호출": len(partial_calls) == 1 and partial_calls[0] == result,
        "session 생성 1회": session is not None,
        "session.capture_diagnostics 정확히 1회 호출(중복 캡처 없음)": session is not None
        and len(session.capture_calls) == 1,
        "capture 시 CAPTCHA 판정 전달": session is not None
        and session.capture_calls
        and session.capture_calls[0]["safety_decision"].reason.value == "captcha_or_security_block",
        "keep_open_if_configured 1회 호출": session is not None and session.keep_open_calls == 1,
        "exc.diagnostics_captured 마커 부착": exc is not None
        and getattr(exc, "diagnostics_captured", False) is True,
        "exc.page 미부착": exc is not None and not hasattr(exc, "page"),
        "pipeline 자체 캡처는 no-op(실 파일 미생성)": pipeline_level_dirs == [],
    }

    if all(checks.values()):
        reporter.pass_("실패 주입 -> classify/session capture 1회/마커 부착/exc.page 미부착/pipeline no-op 모두 확인")
    else:
        failed = [name for name, ok in checks.items() if not ok]
        reporter.fail(f"진단 캡처 계약 검증 실패 항목: {failed}")


# ---------------------------------------------------------------------------
# 6/7. build_collector + pipeline.collect_pc_full 조립
# ---------------------------------------------------------------------------


def check_build_collector_success_with_pipeline(reporter: ValidationReporter) -> None:
    factory, created = _make_session_factory()
    collector = build_collector(
        DiagnosticConfig.safe_default(), session_factory=factory, scrape_fn=fake_scrape_success
    )
    partial_calls = []
    result = collect_pc_full(
        "강동구카페",
        limit=10,
        collector=collector,
        on_partial_save=lambda partial: partial_calls.append(partial),
    )
    if result == [{"업체명": "A카페"}, {"업체명": "B카페"}] and not partial_calls and len(created) == 1:
        reporter.pass_("build_collector 정상 조립 -> pipeline이 전체 결과 반환, on_partial_save 미호출")
    else:
        reporter.fail(f"정상 조립 결과가 예상과 다름: result={result}, partial_calls={partial_calls}")


def check_build_collector_partial_preserve_with_pipeline(reporter: ValidationReporter) -> None:
    factory, created = _make_session_factory()
    captured_exceptions = []
    scrape_fn = make_fake_scrape_timeout(captured_exceptions)
    collector = build_collector(DiagnosticConfig.safe_default(), session_factory=factory, scrape_fn=scrape_fn)

    result = collect_pc_full("강동구카페부분보존", limit=10, collector=collector)
    if result == [{"업체명": "A카페"}, {"업체명": "B카페"}]:
        reporter.pass_("build_collector 조립 -> 예외 발생해도 pipeline이 부분 보존 반환")
    else:
        reporter.fail(f"부분 보존 조립 결과가 예상과 다름: {result}")


# ---------------------------------------------------------------------------
# 8. stop_event / pause_event 전달 및 polling 동작
# ---------------------------------------------------------------------------


def check_build_collector_stop_pause_passthrough(reporter: ValidationReporter) -> None:
    factory, created = _make_session_factory()
    captured = {}

    def scrape_fn(session, frame, keyword, limit, new_open_only, stop_event, pause_event, results):
        captured["stop_event"] = stop_event
        captured["pause_event"] = pause_event
        results.append({"업체명": "D카페"})

    collector = build_collector(DiagnosticConfig.safe_default(), session_factory=factory, scrape_fn=scrape_fn)

    marker_stop = object()
    marker_pause = object()
    collect_pc_full(
        "강동구카페",
        stop_event=marker_stop,
        pause_event=marker_pause,
        collector=collector,
    )

    if captured.get("stop_event") is marker_stop and captured.get("pause_event") is marker_pause:
        reporter.pass_("stop_event/pause_event가 scrape_fn까지 동일 객체로 전달됨(is 비교)")
    else:
        reporter.fail(f"stop_event/pause_event 전달이 예상과 다름: {captured}")


def check_scrape_list_stops_immediately_when_stop_event_set(reporter: ValidationReporter) -> None:
    page = FakePage()
    frame = FakeFrame(locator_map={})
    session = types.SimpleNamespace(page=page)
    stop_event = FakeEvent(initial=True)
    results: list = []

    scrape_list(session, frame, "키워드", 10, False, stop_event, None, results)

    if results == []:
        reporter.pass_("scrape_list 시작 전 stop_event가 set이면 즉시 중단(결과 없음)")
    else:
        reporter.fail(f"stop_event 무시하고 수집이 진행됨: {results}")


def check_wait_while_paused_blocks_until_cleared(reporter: ValidationReporter) -> None:
    page = FakePage()
    pause_event = FakeEvent(initial=True)
    stop_event = FakeEvent(initial=False)

    call_count = {"n": 0}

    def wait_and_maybe_clear(ms):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            pause_event.clear()

    page.wait_for_timeout = wait_and_maybe_clear

    stopped = _wait_while_paused(page, stop_event, pause_event)
    if stopped is False and call_count["n"] >= 2:
        reporter.pass_("pause_event가 clear될 때까지 polling 대기 후 정상 진행(False 반환)")
    else:
        reporter.fail(f"pause polling 동작이 예상과 다름: stopped={stopped}, calls={call_count['n']}")


def check_wait_while_paused_detects_stop_during_pause(reporter: ValidationReporter) -> None:
    page = FakePage()
    pause_event = FakeEvent(initial=True)
    stop_event = FakeEvent(initial=False)

    def wait_and_set_stop(ms):
        stop_event.set()

    page.wait_for_timeout = wait_and_set_stop

    stopped = _wait_while_paused(page, stop_event, pause_event)
    if stopped is True:
        reporter.pass_("일시정지 대기 중 stop_event가 set되면 True 반환(중단)")
    else:
        reporter.fail(f"pause 중 stop 감지 실패: stopped={stopped}")


def check_check_stop_true_when_set(reporter: ValidationReporter) -> None:
    if _check_stop(FakeEvent(initial=True)) is True and _check_stop(FakeEvent(initial=False)) is False:
        reporter.pass_("_check_stop이 stop_event.is_set() 값을 그대로 반영")
    else:
        reporter.fail("_check_stop 결과가 예상과 다름")


# ---------------------------------------------------------------------------
# 9. 금지 파일 무변경 확인
# ---------------------------------------------------------------------------


def check_protected_files_unchanged(reporter: ValidationReporter) -> None:
    # 2026-07-06 Stage 3C: exporter.py는 통합_결과 스키마 확장으로 정당하게 수정되어 제외.
    # 2026-07-06 Stage 3D: ui.py는 premium 분기의 PC full engine 연결로 정당하게 수정되어 제외
    # (ui 연결은 test_ui_pc_full_wiring.py가 별도 검증).
    protected_files = [
        "src/pc_crawler.py",
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
            reporter.pass_("금지 파일 7개 모두 git 변경 없음(git status --porcelain 결과 없음)")
        else:
            reporter.fail(
                f"금지 파일 변경 감지 또는 git 명령 실패: returncode={result.returncode}, output={output!r}"
            )
    except Exception as exc:
        reporter.warn(f"git 상태 확인을 건너뜀(환경 문제로 추정): {exc}")


def main() -> int:
    reporter = ValidationReporter()

    check_find_pc_cards_primary_selector(reporter)
    check_find_pc_cards_fallback_to_anchor_ancestor(reporter)

    check_light_scroll_cards_stops_after_two_no_growth(reporter)
    check_light_scroll_cards_stops_on_stop_event(reporter)
    check_light_scroll_cards_skips_when_target_already_met(reporter)
    check_light_scroll_cards_stops_early_when_target_reached_mid_loop(reporter)
    check_light_scroll_cards_target_count_none_unchanged(reporter)

    check_click_next_page_uses_last_matching_selector(reporter)
    check_click_next_page_propagates_click_failure(reporter)
    check_click_next_page_swallows_visibility_check_and_tries_next(reporter)

    check_build_row_success(reporter)
    check_build_row_captures_place_id_and_url(reporter)
    check_parse_place_id_and_url_helpers(reporter)
    check_build_row_skips_when_no_review_keyword(reporter)
    check_build_row_skips_duplicate_name(reporter)

    check_failure_contract_classify_capture_mark_no_page(reporter)

    check_build_collector_success_with_pipeline(reporter)
    check_build_collector_partial_preserve_with_pipeline(reporter)

    check_build_collector_stop_pause_passthrough(reporter)
    check_scrape_list_stops_immediately_when_stop_event_set(reporter)
    check_wait_while_paused_blocks_until_cleared(reporter)
    check_wait_while_paused_detects_stop_during_pause(reporter)
    check_check_stop_true_when_set(reporter)

    check_protected_files_unchanged(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
