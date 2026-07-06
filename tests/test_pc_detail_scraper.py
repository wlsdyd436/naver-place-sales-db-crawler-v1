from pathlib import Path
import subprocess
import sys


# Stage 3B: src/pc/detail_scraper.py(카드 index 클릭 기반 상세 수집) 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.config import DiagnosticConfig
from src.pc.diagnostics import DEFAULT_DIAGNOSTICS_ROOT
from src.pc.pipeline import collect_pc_full
from src.pc.detail_scraper import (
    DetailCollectionAborted,
    _click_card_by_name,
    _enrich_card,
    _extract_entry_address,
    _extract_entry_phone,
    _extract_entry_sns,
    _parse_place_id_from_url,
    _title_matches,
    _wait_entry_updated,
    build_full_collector,
    collect_full,
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
# Fake Playwright 계층 (실 브라우저 없이 카드 클릭/entryIframe 시퀀스 시뮬레이션)
# ---------------------------------------------------------------------------


class FakeLD:
    """단일 텍스트 locator(title 등)."""

    def __init__(self, count_value=0, text=""):
        self._count = count_value
        self._text = text

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def inner_text(self, timeout=None):
        return self._text


class FakeHrefs:
    def __init__(self, hrefs):
        self._hrefs = hrefs

    def evaluate_all(self, expression):
        return list(self._hrefs)


class FakeValue:
    """place_blind 라벨의 값 div (텍스트 + 외부 링크 + 주소 전용 span.pz7wy)."""

    def __init__(self, text="", hrefs=None, address_span=None):
        self._text = text
        self._hrefs = hrefs or []
        self._address_span = address_span

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def inner_text(self, timeout=None):
        return self._text

    def locator(self, selector):
        if selector == "span.pz7wy":
            if self._address_span is not None:
                return FakeLD(count_value=1, text=self._address_span)
            return FakeLD(count_value=0)
        return FakeHrefs(self._hrefs)


class FakeLabel:
    """place_blind 라벨 locator. xpath로 값 div를 반환한다."""

    def __init__(self, value):
        self._value = value

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def locator(self, selector):
        return self._value


class FakeMissing:
    @property
    def first(self):
        return self

    def count(self):
        return 0

    def inner_text(self, timeout=None):
        return ""

    def locator(self, selector):
        return FakeMissing()


class FakeEntryFrame:
    def __init__(self, place_id, title="", phone="", address="", address_span=None, hrefs=None):
        self.url = (
            f"https://pcmap.place.naver.com/restaurant/{place_id}/home"
            f"?entry=bmp&timestamp=1&searchText=x"
        )
        self._map = {}
        if title:
            self._map["span.IY7ZX"] = FakeLD(count_value=1, text=title)
        if phone:
            self._map["span.place_blind:has-text('전화번호')"] = FakeLabel(FakeValue(text=phone))
        if address or address_span:
            self._map["span.place_blind:has-text('주소')"] = FakeLabel(
                FakeValue(text=address, address_span=address_span)
            )
        if hrefs:
            self._map["span.place_blind:has-text('홈페이지')"] = FakeLabel(FakeValue(hrefs=hrefs))

    def locator(self, selector):
        return self._map.get(selector, FakeMissing())


class FakeAnchor:
    def __init__(self, text, on_click=None, click_error=None, present=True):
        self._text = text
        self._on_click = on_click
        self._click_error = click_error
        self._present = present

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._present else 0

    def inner_text(self, timeout=None):
        return self._text

    def click(self, timeout=None):
        if self._click_error is not None:
            raise self._click_error
        if self._on_click is not None:
            self._on_click()


class FakeAnchorList:
    def __init__(self, anchors):
        self._anchors = anchors

    def filter(self, has_text=None):
        if has_text is None:
            return FakeAnchorList(list(self._anchors))
        return FakeAnchorList([a for a in self._anchors if has_text in a._text])

    @property
    def first(self):
        return self._anchors[0] if self._anchors else FakeAnchor("", present=False)

    def count(self):
        return len(self._anchors)


class FakeCard:
    """searchIframe 카드. 첫 anchor가 업체명 버튼, 나머지는 저장/썸네일 등."""

    def __init__(self, name, place_id, scenario):
        self.name = name
        self.place_id = place_id
        name_anchor = FakeAnchor(name, on_click=lambda: scenario.click(place_id))
        self._anchors = [name_anchor, FakeAnchor("저장")]

    def locator(self, selector):
        if selector == "a":
            return FakeAnchorList(self._anchors)
        return FakeAnchorList([])


class DetailScenario:
    """place_id -> cfg({loads, click_error, title, phone, address, hrefs})를 보관하고
    카드 클릭에 따라 현재 로드된 entryIframe 상태를 전이한다."""

    def __init__(self, places, current=None):
        self.places = places
        self.current_entry_id = current

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
            title=cfg.get("title", ""),
            phone=cfg.get("phone", ""),
            address=cfg.get("address", ""),
            hrefs=cfg.get("hrefs"),
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
        return "search-frame"

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
        "플레이스 URL": "",
        "place_id": "",
        "수집일": "2026-07-06",
    }


# ---------------------------------------------------------------------------
# 1. 순수 helper
# ---------------------------------------------------------------------------


def check_parse_place_id_from_url(reporter: ValidationReporter) -> None:
    cases = {
        "https://pcmap.place.naver.com/restaurant/1171815551/home?x=1": "1171815551",
        "https://pcmap.place.naver.com/cafe/123456/home": "123456",
        "https://pcmap.place.naver.com/hairshop/987654321/information": "987654321",
        "https://map.naver.com/p/entry/place/555555/home": "555555",
        "https://pcmap.place.naver.com/restaurant/home": "",
        "": "",
    }
    bad = {url: (_parse_place_id_from_url(url), expected)
           for url, expected in cases.items()
           if _parse_place_id_from_url(url) != expected}
    if not bad:
        reporter.pass_("entryIframe URL segment/쿼리/비정상에서 place_id 정규식 확보")
    else:
        reporter.fail(f"place_id 파싱 불일치: {bad}")


def check_title_matches(reporter: ValidationReporter) -> None:
    ok = (
        _title_matches("오베르캄프 본점", "오베르캄프 본점") is True
        and _title_matches("오베르캄프 본점", "오베르캄프 본점 베이커리") is True  # 카드명 업종 접미사
        and _title_matches("오베르캄프 본점", "아티초크라보") is False
        and _title_matches("", "오베르캄프") is False
        and _title_matches("오베르캄프", "") is False
    )
    if ok:
        reporter.pass_("title 일치 판정: 동일/부분포함 매칭, 불일치/공란 거부")
    else:
        reporter.fail("title 일치 판정 결과가 예상과 다름")


def check_extract_entry_phone(reporter: ValidationReporter) -> None:
    frame = FakeEntryFrame("1234567", phone="0507-1387-4967 안내 복사")
    empty = FakeEntryFrame("1234567")  # 전화번호 라벨 없음
    if _extract_entry_phone(frame) == "0507-1387-4967" and _extract_entry_phone(empty) == "":
        reporter.pass_("home 탭 '전화번호' 라벨 텍스트에서 전화 정규식 추출(tel: href 아님), 부재 시 공란")
    else:
        reporter.fail(f"전화 추출 결과가 예상과 다름: {_extract_entry_phone(frame)!r}")


def check_extract_entry_address(reporter: ValidationReporter) -> None:
    frame = FakeEntryFrame("1234567", address="서울 강동구 성내로14길 48 1층")
    if _extract_entry_address(frame) == "서울 강동구 성내로14길 48 1층":
        reporter.pass_("home 탭 '주소' 라벨 값에서 전체주소 추출")
    else:
        reporter.fail(f"주소 추출 결과가 예상과 다름: {_extract_entry_address(frame)!r}")


def check_extract_entry_address_prefers_pz7wy_span(reporter: ValidationReporter) -> None:
    # 값 div 전체 텍스트에는 역/출구/거리 안내가 섞여 있지만, span.pz7wy가 있으면
    # 그 값만 사용해야 한다(2026-07-06 live smoke 발견 문제 보정).
    frame = FakeEntryFrame(
        "1234567",
        address="서울 강동구 성내로14길 48 1층 8강동구청역 2번 출구에서 866m 미터",
        address_span="서울 강동구 성내로14길 48 1층",
    )
    result = _extract_entry_address(frame)
    if result == "서울 강동구 성내로14길 48 1층":
        reporter.pass_("span.pz7wy 존재 시 그 값만 추출(전체 텍스트의 역/출구/거리 안내 무시)")
    else:
        reporter.fail(f"pz7wy 우선 추출 결과가 예상과 다름: {result!r}")


def check_extract_entry_address_fallback_strips_noise(reporter: ValidationReporter) -> None:
    # span.pz7wy가 없을 때만 fallback: 전체 텍스트에서 역/출구/거리 안내를 정제한다.
    frame = FakeEntryFrame(
        "1234567",
        address="서울 강동구 성내로14길 48 1층 8강동구청역 2번 출구에서 866m 미터",
    )
    result = _extract_entry_address(frame)
    if result == "서울 강동구 성내로14길 48 1층":
        reporter.pass_("pz7wy 부재 시 fallback 전체 텍스트에서 역/출구/거리 안내 정제")
    else:
        reporter.fail(f"fallback 정제 결과가 예상과 다름: {result!r}")


def check_extract_entry_address_preserves_number_components(reporter: ValidationReporter) -> None:
    # 정제 규칙이 번지/층/호수 등 실제 주소 구성 요소(48, 1층, 101호)를 지우면 안 된다.
    frame = FakeEntryFrame(
        "1234567",
        address="서울 강동구 성내로14길 48 1층 101호 8강동구청역 2번 출구에서 866m 미터",
    )
    result = _extract_entry_address(frame)
    if result == "서울 강동구 성내로14길 48 1층 101호":
        reporter.pass_("정제 후에도 번지/층/호수(48, 1층, 101호)는 보존됨")
    else:
        reporter.fail(f"주소 구성 요소 보존 결과가 예상과 다름: {result!r}")


def check_extract_entry_address_missing_label_returns_empty(reporter: ValidationReporter) -> None:
    # '주소' 라벨 자체가 없으면(값 div를 찾지 못하면) 기존과 동일하게 공란을 반환한다.
    frame = FakeEntryFrame("1234567")  # address/address_span 모두 미지정
    result = _extract_entry_address(frame)
    if result == "":
        reporter.pass_("주소 라벨 부재 시 기존 fallback 동작 유지(공란 반환, 예외 없음)")
    else:
        reporter.fail(f"주소 라벨 부재 시 결과가 예상과 다름: {result!r}")


def check_extract_entry_sns(reporter: ValidationReporter) -> None:
    insta_only = FakeEntryFrame("1", hrefs=["https://www.instagram.com/oberkampf.kr"])
    blog_only = FakeEntryFrame("2", hrefs=["https://blog.naver.com/some_cafe"])
    home_only = FakeEntryFrame("3", hrefs=["https://oberkampf.co.kr"])
    none_row = FakeEntryFrame("4")  # 홈페이지 라벨 없음
    with_noise = FakeEntryFrame(
        "5", hrefs=["https://phinf.pstatic.net/x.jpg", "https://www.instagram.com/abc"]
    )

    r_insta = _extract_entry_sns(insta_only)
    r_blog = _extract_entry_sns(blog_only)
    r_home = _extract_entry_sns(home_only)
    r_none = _extract_entry_sns(none_row)
    r_noise = _extract_entry_sns(with_noise)

    ok = (
        r_insta == ("", "https://www.instagram.com/oberkampf.kr", "")
        and r_blog == ("", "", "https://blog.naver.com/some_cafe")
        and r_home == ("https://oberkampf.co.kr", "", "")
        and r_none == ("", "", "")
        and r_noise == ("", "https://www.instagram.com/abc", "")  # pstatic 제외
    )
    if ok:
        reporter.pass_("홈페이지 라벨 행 도메인 분류: 인스타/블로그/홈페이지, pstatic 제외, 부재 시 공란")
    else:
        reporter.fail(
            f"SNS 분류 결과가 예상과 다름: insta={r_insta}, blog={r_blog}, "
            f"home={r_home}, none={r_none}, noise={r_noise}"
        )


# ---------------------------------------------------------------------------
# 2. 클릭 / wait
# ---------------------------------------------------------------------------


def check_click_card_by_name(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({"1111111": {"loads": True}})
    card = FakeCard("A카페베이커리", "1111111", scenario)
    clicked = _click_card_by_name(card, "A카페")

    # 오클릭 가드: 이름과 무관한 카드(anchor 텍스트가 업체명과 포함관계 아님)
    empty_card = FakeCard("전혀다른상호", "2222222", scenario)
    no_name = _click_card_by_name(empty_card, "매칭안됨키워드")

    if clicked is True and scenario.current_entry_id == "1111111" and no_name is False:
        reporter.pass_("업체명 anchor 클릭 성공(부분포함), 무관 카드는 가드로 클릭 안 함")
    else:
        reporter.fail(
            f"클릭 대상 선정 결과가 예상과 다름: clicked={clicked}, "
            f"current={scenario.current_entry_id}, no_name={no_name}"
        )


def check_wait_entry_stale_then_update(reporter: ValidationReporter) -> None:
    # 직전 상세가 남아있는 잔상: previous_place_id와 동일 -> None,
    # click_error 없이 loads=False면 갱신 안 됨.
    scenario = DetailScenario({"9999999": {"loads": True, "title": "이전상세"}}, current="9999999")
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    frame, pid, url = _wait_entry_updated(session, "새업체", previous_place_id="9999999", timeout_ms=900)
    if frame is None and pid == "" and url == "":
        reporter.pass_("잔상(place_id==previous)일 때 갱신으로 인정하지 않고 skip")
    else:
        reporter.fail(f"잔상 처리 결과가 예상과 다름: frame={frame}, pid={pid}, url={url}")


def check_wait_entry_title_mismatch(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({"1111111": {"loads": True, "title": "다른상호"}}, current="1111111")
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    frame, pid, url = _wait_entry_updated(session, "원하는업체", previous_place_id=None, timeout_ms=900)
    if frame is None:
        reporter.pass_("title 불일치 시 갱신으로 인정하지 않고 skip(오매칭 방지)")
    else:
        reporter.fail(f"title 불일치인데 갱신 인정됨: pid={pid}, url={url}")


def check_wait_entry_success(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({"1111111": {"loads": True, "title": "오베르캄프 본점"}}, current="1111111")
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    frame, pid, url = _wait_entry_updated(session, "오베르캄프 본점", previous_place_id="8888888", timeout_ms=900)
    if frame is not None and pid == "1111111" and url == "https://pcmap.place.naver.com/restaurant/1111111/home":
        reporter.pass_("place_id 변경 + title 일치 시 갱신 인정, URL은 volatile query 제거")
    else:
        reporter.fail(f"정상 갱신 결과가 예상과 다름: frame={frame}, pid={pid}, url={url}")


# ---------------------------------------------------------------------------
# 3. _enrich_card 병합 / retry / 보존
# ---------------------------------------------------------------------------


def check_enrich_card_success_merges(reporter: ValidationReporter) -> None:
    scenario = DetailScenario(
        {
            "1111111": {
                "loads": True,
                "title": "A카페",
                "phone": "0507-111-1111 복사",
                "address": "서울 강동구 A로 1",
                "hrefs": ["https://www.instagram.com/a_cafe"],
            }
        }
    )
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    card = FakeCard("A카페", "1111111", scenario)
    row = _row("", "A카페")
    row.setdefault("홈페이지", "")
    row.setdefault("인스타", "")
    row.setdefault("블로그", "")

    outcome, error, new_prev = _enrich_card(session, card, row, None, retry=1)

    ok = (
        outcome == "ok"
        and new_prev == "1111111"
        and row["place_id"] == "1111111"
        and row["플레이스 URL"] == "https://pcmap.place.naver.com/restaurant/1111111/home"
        and row["대표전화"] == "0507-111-1111"
        and row["주소"] == "서울 강동구 A로 1"
        and row["인스타"] == "https://www.instagram.com/a_cafe"
        and row["홈페이지"] == ""
        and row["블로그"] == ""
    )
    if ok:
        reporter.pass_("_enrich_card 성공: place_id/URL 사후 확보, 전화/주소/인스타 병합, 새 previous 반환")
    else:
        reporter.fail(f"_enrich_card 성공 병합 결과가 예상과 다름: {row}, new_prev={new_prev}")


def check_enrich_card_keeps_list_fields_on_blank(reporter: ValidationReporter) -> None:
    # 상세 주소 없음 -> 리스트 주소 유지(다운그레이드 방지)
    scenario = DetailScenario(
        {"1111111": {"loads": True, "title": "A카페", "phone": "0507-111-1111"}}
    )
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    card = FakeCard("A카페", "1111111", scenario)
    row = _row("", "A카페")

    _enrich_card(session, card, row, None, retry=1)

    if row["대표전화"] == "0507-111-1111" and row["주소"] == "서울 강동구 (리스트주소)":
        reporter.pass_("상세 주소 공란이면 리스트 주소 유지(다운그레이드 안 함)")
    else:
        reporter.fail(f"공란 보존 결과가 예상과 다름: {row}")


def check_enrich_card_failure_preserves_row(reporter: ValidationReporter) -> None:
    # 클릭해도 loads=False -> entry 미갱신 -> retry 후 fail. 리스트 필드는 보존.
    scenario = DetailScenario({"1111111": {"loads": False}})
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    card = FakeCard("A카페", "1111111", scenario)
    row = _row("", "A카페")

    outcome, error, new_prev = _enrich_card(session, card, row, "7777777", retry=1)

    ok = (
        outcome == "fail"
        and new_prev == "7777777"  # previous 유지
        and row["업체명"] == "A카페"
        and row["place_id"] == ""  # 상세 확보 실패 -> 공란
        and row["주소"] == "서울 강동구 (리스트주소)"
    )
    if ok:
        reporter.pass_("_enrich_card 실패: 리스트 필드 보존, place_id 공란, previous 유지")
    else:
        reporter.fail(f"_enrich_card 실패 보존 결과가 예상과 다름: {row}, outcome={outcome}, new_prev={new_prev}")


# ---------------------------------------------------------------------------
# 4. collect_full 순회 / escalation
# ---------------------------------------------------------------------------


class FakeCards:
    def __init__(self, cards):
        self._cards = cards

    def count(self):
        return len(self._cards)

    def nth(self, index):
        return self._cards[index]


def _static_build_row(name):
    def _fn(card, collected_at, new_open_only, seen):
        return {
            "업체명": name,
            "업종": "카페",
            "주소": "리스트주소",
            "대표전화": "",
            "플레이스 URL": "",
            "place_id": "",
            "수집일": collected_at,
        }
    return _fn


def check_collect_full_success(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({})
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    cards = FakeCards([FakeCard("A", "1", scenario), FakeCard("B", "2", scenario)])

    def enrich_ok(session_, card, row, previous, retry):
        row["place_id"] = card.place_id
        row["대표전화"] = "0507-000-0000"
        return "ok", "", card.place_id

    results = []
    collect_full(
        session, "search", "kw", 2, False, None, None, results,
        build_row_fn=lambda card, at, no, seen: {"업체명": card.name, "주소": "리스트주소",
                                                  "대표전화": "", "플레이스 URL": "", "place_id": ""},
        enrich_fn=enrich_ok,
        find_cards_fn=lambda frame: cards,
        scroll_fn=lambda page, c, **kw: None,
        next_page_fn=lambda frame, n: False,
    )

    ok = (
        len(results) == 2
        and results[0]["place_id"] == "1"
        and results[1]["place_id"] == "2"
        and all("홈페이지" in r for r in results)  # 새 필드 초기화 보장
    )
    if ok:
        reporter.pass_("collect_full 정상: 카드 index 순회로 list+detail 융합, 새 필드 초기화")
    else:
        reporter.fail(f"collect_full 정상 순회 결과가 예상과 다름: {results}")


def check_collect_full_escalation(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({})
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    cards = FakeCards([FakeCard(f"C{i}", str(i), scenario) for i in range(6)])

    def enrich_fail(session_, card, row, previous, retry):
        return "fail", "boom", previous

    results = []
    try:
        collect_full(
            session, "search", "kw", 30, False, None, None, results,
            build_row_fn=lambda card, at, no, seen: {"업체명": card.name, "주소": "리스트주소",
                                                     "대표전화": "", "플레이스 URL": "", "place_id": ""},
            enrich_fn=enrich_fail,
            find_cards_fn=lambda frame: cards,
            scroll_fn=lambda page, c, **kw: None,
            next_page_fn=lambda frame, n: False,
            consecutive_limit=5,
        )
        reporter.fail("연속 실패가 임계를 넘었는데 DetailCollectionAborted 미발생")
    except DetailCollectionAborted:
        # 임계(5)에서 raise, 그때까지 5행은 부분 보존
        if len(results) == 5 and not hasattr(DetailCollectionAborted, "page"):
            reporter.pass_("collect_full 연속 실패 임계 초과 -> DetailCollectionAborted, 5행 부분 보존")
        else:
            reporter.fail(f"escalation 시 부분 보존 행 수가 예상과 다름: {len(results)}")
    except Exception as exc:
        reporter.fail(f"예상과 다른 예외: {type(exc).__name__}: {exc}")


def check_collect_full_stops_on_stop_event(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({})
    session = FakeSession(scenario, DiagnosticConfig.safe_default())
    cards = FakeCards([FakeCard("A", "1", scenario)])
    stop_event = FakeEvent(initial=True)
    results = []
    collect_full(
        session, "search", "kw", 5, False, stop_event, None, results,
        find_cards_fn=lambda frame: cards,
        scroll_fn=lambda page, c, **kw: None,
        next_page_fn=lambda frame, n: False,
    )
    if results == []:
        reporter.pass_("stop_event가 set이면 순회를 시작하지 않고 즉시 중단")
    else:
        reporter.fail(f"stop_event 무시하고 순회됨: {results}")


# ---------------------------------------------------------------------------
# 5. build_full_collector + pipeline 조립 / 진단 계약
# ---------------------------------------------------------------------------


def _make_session_factory(scenario):
    created = []

    def factory(diagnostic_config):
        session = FakeSession(scenario, diagnostic_config)
        created.append(session)
        return session

    return factory, created


def check_full_collector_success_with_pipeline(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({})
    factory, created = _make_session_factory(scenario)

    def fake_collect(session, search_frame, keyword, limit, new_open_only, stop_event, pause_event, results):
        r1 = _row("1111111", "A카페")
        r1["place_id"] = "1111111"
        r1["대표전화"] = "0507-111-1111"
        r1["플레이스 URL"] = "https://pcmap.place.naver.com/restaurant/1111111/home"
        r2 = _row("2222222", "B카페")
        r2["place_id"] = "2222222"
        r2["대표전화"] = "0507-222-2222"
        results.append(r1)
        results.append(r2)

    collector = build_full_collector(
        DiagnosticConfig.safe_default(),
        session_factory=factory,
        collect_fn=fake_collect,
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
        and result[0]["대표전화"] == "0507-111-1111"
        and result[1]["place_id"] == "2222222"
        and not partial_calls
        and len(created) == 1
        and created[0].goto_calls  # goto 호출됨
    )
    if ok:
        reporter.pass_("build_full_collector + pipeline -> 융합 수집 결과 정상 반환")
    else:
        reporter.fail(f"full collector 조립 결과가 예상과 다름: result={result}, partial={partial_calls}")


def check_full_collector_escalation_contract(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({})
    factory, created = _make_session_factory(scenario)

    def collect_then_abort(session, search_frame, keyword, limit, new_open_only, stop_event, pause_event, results):
        for i in range(6):
            results.append(_row(str(i) * 7, f"F{i}"))
        raise DetailCollectionAborted("연속 실패 escalation")

    collector = build_full_collector(
        DiagnosticConfig(capture_artifacts=True),
        session_factory=factory,
        collect_fn=collect_then_abort,
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
        "session.capture_diagnostics 1회(중복 없음)": session is not None and len(session.capture_calls) == 1,
        "keep_open_if_configured 1회": session is not None and session.keep_open_calls == 1,
        "pipeline 자체 캡처 no-op(파일 미생성)": pipeline_level_dirs == [],
    }
    if all(checks.values()):
        reporter.pass_("연속 실패 escalation -> 세션 계층 1차 캡처 1회 + 부분 보존 + pipeline no-op")
    else:
        failed = [name for name, ok in checks.items() if not ok]
        reporter.fail(f"escalation 계약 검증 실패 항목: {failed}")


def check_full_collector_marks_exc_without_page(reporter: ValidationReporter) -> None:
    scenario = DetailScenario({})
    factory, created = _make_session_factory(scenario)
    held = {"exc": None}

    def raising_collect(session, search_frame, keyword, limit, new_open_only, stop_event, pause_event, results):
        results.append(_row("1111111", "A"))
        exc = DetailCollectionAborted("강제 escalation")
        held["exc"] = exc
        raise exc

    collector = build_full_collector(
        DiagnosticConfig(capture_artifacts=True),
        session_factory=factory,
        collect_fn=raising_collect,
    )

    result = collect_pc_full(
        "마커테스트키워드",
        limit=10,
        collector=collector,
        diagnostic_config=DiagnosticConfig(capture_artifacts=True),
    )

    exc = held["exc"]
    ok = (
        len(result) == 1
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
    # 2026-07-06 Stage 3C: exporter.py는 통합_결과 스키마 확장으로 정당하게 수정되어 제외.
    # 2026-07-06 Stage 3D: ui.py는 premium 분기의 PC full engine 연결로 정당하게 수정되어 제외
    # (ui 연결은 test_ui_pc_full_wiring.py가 별도 검증). 나머지 파일은 계속 수정 금지 대상.
    protected_files = [
        "src/pc_crawler.py",
        "src/parser.py",
        "src/crawler.py",
        "src/pc/config.py",
        "src/pc/safety.py",
        "src/pc/diagnostics.py",
        "src/pc/pipeline.py",
        "src/pc/browser_session.py",
        "src/pc/list_scraper.py",
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
            reporter.pass_("금지 파일 9개 모두 git 변경 없음(list_scraper/browser_session 포함)")
        else:
            reporter.fail(f"금지 파일 변경 감지 또는 git 실패: rc={result.returncode}, out={output!r}")
    except Exception as exc:
        reporter.warn(f"git 상태 확인 건너뜀: {exc}")


def main() -> int:
    reporter = ValidationReporter()

    check_parse_place_id_from_url(reporter)
    check_title_matches(reporter)
    check_extract_entry_phone(reporter)
    check_extract_entry_address(reporter)
    check_extract_entry_address_prefers_pz7wy_span(reporter)
    check_extract_entry_address_fallback_strips_noise(reporter)
    check_extract_entry_address_preserves_number_components(reporter)
    check_extract_entry_address_missing_label_returns_empty(reporter)
    check_extract_entry_sns(reporter)

    check_click_card_by_name(reporter)
    check_wait_entry_stale_then_update(reporter)
    check_wait_entry_title_mismatch(reporter)
    check_wait_entry_success(reporter)

    check_enrich_card_success_merges(reporter)
    check_enrich_card_keeps_list_fields_on_blank(reporter)
    check_enrich_card_failure_preserves_row(reporter)

    check_collect_full_success(reporter)
    check_collect_full_escalation(reporter)
    check_collect_full_stops_on_stop_event(reporter)

    check_full_collector_success_with_pipeline(reporter)
    check_full_collector_escalation_contract(reporter)
    check_full_collector_marks_exc_without_page(reporter)

    check_protected_files_unchanged(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
