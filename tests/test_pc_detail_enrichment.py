from pathlib import Path
import sys


# PAGE300-DETAIL-1: src/pc/network_browser_collector.py의 _fetch_place_detail/
# DomMembershipCollector.enrich_detail을 검증하는 standalone 스크립트(실제
# Playwright/브라우저 없음). entryIframe 콘텐츠 추출 자체(_extract_entry_phone
# 등)는 tests/test_pc_detail_scraper.py가 이미 검증하므로, 여기서는 새로 작성한
# 순회/진입/안전중단 로직(_fetch_place_detail/enrich_detail)만 검증한다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.network_browser_collector import DomMembershipCollector, _fetch_place_detail


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


class FakeLD:
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
    def __init__(self, text="", hrefs=None):
        self._text = text
        self._hrefs = hrefs or []

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def inner_text(self, timeout=None):
        return self._text

    def locator(self, selector):
        if selector == "span.pz7wy":
            return FakeLD(count_value=0)
        return FakeHrefs(self._hrefs)


class FakeLabel:
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
    """detail_scraper._extract_entry_*/_entry_title이 기대하는 최소 계약만
    흉내낸다(test_pc_detail_scraper.py의 FakeEntryFrame과 동일한 패턴)."""

    def __init__(self, title="", phone="", address="", hrefs=None):
        self.name = "entryIframe"
        self.url = "https://pcmap.place.naver.com/place/1/home"
        self._map = {}
        if title:
            self._map["span.IY7ZX"] = FakeLD(count_value=1, text=title)
        if phone:
            self._map["span.place_blind:has-text('전화번호')"] = FakeLabel(FakeValue(text=phone))
        if address:
            self._map["span.place_blind:has-text('주소')"] = FakeLabel(FakeValue(text=address))
        if hrefs:
            self._map["span.place_blind:has-text('홈페이지')"] = FakeLabel(FakeValue(hrefs=hrefs))

    def locator(self, selector):
        return self._map.get(selector, FakeMissing())


class FakeCaptchaLocator:
    def __init__(self, count=0, visible=False, box=None):
        self._count = count
        self._visible = visible
        self._box = box or {"width": 0, "height": 0}

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def is_visible(self, timeout=300):
        return self._visible

    def bounding_box(self):
        return self._box


class FakeResponse:
    def __init__(self, url, status):
        self.url = url
        self.status = status


class FakePage:
    """URL별로 entry frame/HTTP status를 미리 계획해둔 fake page. goto() 시점에
    등록된 response 핸들러에 계획된 status를 동기적으로 전달한다."""

    def __init__(self, *, entry_frame_by_url=None, status_by_url=None, captcha_selectors=None):
        self._entry_frame_by_url = entry_frame_by_url or {}
        self._status_by_url = status_by_url or {}
        self._captcha_selectors = captcha_selectors or {}
        self._handlers: dict = {}
        self._current_url = None
        self.goto_calls: list = []
        self.closed = False

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event, handler):
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        self._current_url = url
        for status in self._status_by_url.get(url, [200]):
            response = FakeResponse(url, status)
            for handler in list(self._handlers.get("response", [])):
                handler(response)

    def locator(self, selector):
        return self._captcha_selectors.get(selector, FakeCaptchaLocator(count=0))

    def frame(self, name=None):
        if name == "entryIframe":
            return self._entry_frame_by_url.get(self._current_url)
        return None

    @property
    def frames(self):
        return []

    def close(self):
        self.closed = True


def _row(name, place_id):
    return {
        "업체명": name,
        "place_id": place_id,
        "플레이스 URL": "",
        "대표전화": "",
        "주소": "",
        "홈페이지": "",
        "인스타": "",
        "블로그": "",
    }


PLACE_URL_1 = "https://pcmap.place.naver.com/place/1000001/home"
PLACE_URL_2 = "https://pcmap.place.naver.com/place/1000002/home"


# ---------------------------------------------------------------------------
# 1. _fetch_place_detail 단건
# ---------------------------------------------------------------------------


def check_fetch_place_detail_success(reporter: ValidationReporter) -> None:
    row = _row("카페 성공", "1000001")
    page = FakePage(entry_frame_by_url={
        PLACE_URL_1: FakeEntryFrame(title="카페 성공", phone="02-1234-5678", address="서울 강동구 상세주소",
                                     hrefs=["https://instagram.com/cafe", "https://example.com"]),
    })
    result = _fetch_place_detail(page, row)
    ok = (
        result["detail_attempted"] and result["detail_success"]
        and result["대표전화"] == "02-1234-5678"
        and result["주소"] == "서울 강동구 상세주소"
        and result["인스타"] == "https://instagram.com/cafe"
        and result["홈페이지"] == "https://example.com"
        and result["플레이스 URL"] == PLACE_URL_1
    )
    if ok:
        reporter.pass_("_fetch_place_detail: 성공 시 대표전화/주소/URL/SNS를 모두 확보")
    else:
        reporter.fail(f"성공 케이스 결과 이상: {result}")


def check_fetch_place_detail_no_place_id(reporter: ValidationReporter) -> None:
    row = _row("카페 무ID", "")
    page = FakePage()
    result = _fetch_place_detail(page, row)
    if not result["detail_attempted"] and result["detail_stop_reason"] == "no_place_url":
        reporter.pass_("_fetch_place_detail: place_id가 없으면 URL을 만들 수 없어 시도조차 하지 않음")
    else:
        reporter.fail(f"place_id 없음 처리 이상: {result}")


def check_fetch_place_detail_title_mismatch_retries_then_fails(reporter: ValidationReporter) -> None:
    row = _row("카페 진짜이름", "1000001")
    page = FakePage(entry_frame_by_url={
        PLACE_URL_1: FakeEntryFrame(title="완전히다른업체", phone="02-0000-0000"),
    })
    result = _fetch_place_detail(page, row, retry=1)
    if not result["detail_success"] and result["detail_stop_reason"] == "entry_title_mismatch" and len(page.goto_calls) == 2:
        reporter.pass_("_fetch_place_detail: entry 업체명이 불일치하면 재시도 후에도 실패 처리(오염 방지), retry=1이면 2회 시도")
    else:
        reporter.fail(f"title mismatch 처리 이상: result={result} goto_calls={page.goto_calls}")


def check_fetch_place_detail_http_blocking_status_stops_immediately(reporter: ValidationReporter) -> None:
    row = _row("카페 차단", "1000002")
    page = FakePage(status_by_url={PLACE_URL_2: [405]})
    result = _fetch_place_detail(page, row, retry=2)
    if (
        not result["detail_success"]
        and result["detail_stop_reason"] == "detail_http_error"
        and result["detail_http_status"] == 405
        and len(page.goto_calls) == 1
    ):
        reporter.pass_("_fetch_place_detail: HTTP 405 감지 시 재시도 없이 즉시 중단")
    else:
        reporter.fail(f"HTTP 차단 처리 이상: result={result} goto_calls={page.goto_calls}")


def check_fetch_place_detail_captcha_stops_immediately(reporter: ValidationReporter) -> None:
    row = _row("카페 캡차", "1000001")
    captcha_locator = FakeCaptchaLocator(count=1, visible=True, box={"width": 300, "height": 200})
    page = FakePage(
        entry_frame_by_url={PLACE_URL_1: FakeEntryFrame(title="카페 캡차")},
        captcha_selectors={"#wtm-captcha-root": captcha_locator},
    )
    result = _fetch_place_detail(page, row, retry=2)
    if not result["detail_success"] and result["detail_stop_reason"] == "captcha_detected" and len(page.goto_calls) == 1:
        reporter.pass_("_fetch_place_detail: CAPTCHA 감지 시 재시도 없이 즉시 중단")
    else:
        reporter.fail(f"CAPTCHA 처리 이상: result={result} goto_calls={page.goto_calls}")


def check_fetch_place_detail_retry_recovers(reporter: ValidationReporter) -> None:
    """entry frame이 첫 시도에 None(아직 갱신 안 됨)이었다가 재시도 시 정상 로드되는 상황."""
    row = _row("카페 재시도", "1000001")
    calls = {"n": 0}
    real_frame = FakeEntryFrame(title="카페 재시도", phone="02-1111-2222")

    class FlakyPage(FakePage):
        def frame(self, name=None):
            calls["n"] += 1
            if name == "entryIframe" and calls["n"] >= 2:
                return real_frame
            return None

    page = FlakyPage(entry_frame_by_url={})
    result = _fetch_place_detail(page, row, retry=1)
    if result["detail_success"] and result["대표전화"] == "02-1111-2222":
        reporter.pass_("_fetch_place_detail: 첫 시도 실패 후 retry로 회복 가능")
    else:
        reporter.fail(f"retry 회복 처리 이상: {result}")


# ---------------------------------------------------------------------------
# 2. DomMembershipCollector.enrich_detail
# ---------------------------------------------------------------------------


class FakeContext:
    def __init__(self, pages):
        self._pages = list(pages)
        self._index = 0

    def new_page(self):
        page = self._pages[self._index]
        self._index += 1
        return page


class FakeInnerSession:
    def __init__(self, pages):
        self.context = FakeContext(pages)


class FakeSessionCM:
    def __init__(self, pages):
        self._session = FakeInnerSession(pages)

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_collector(pages):
    collector = DomMembershipCollector(collected_at="2026-07-21", session_factory=lambda: FakeSessionCM(pages))
    collector.__enter__()
    return collector


def check_enrich_detail_max_targets_limits_visits(reporter: ValidationReporter) -> None:
    rows = [_row(f"업체{i}", f"100000{i}") for i in range(5)]
    urls = [f"https://pcmap.place.naver.com/place/100000{i}/home" for i in range(5)]
    page = FakePage(entry_frame_by_url={u: FakeEntryFrame(title=f"업체{i}") for i, u in enumerate(urls)})
    collector = _make_collector([page])
    merged = collector.enrich_detail(rows, max_targets=2)
    if len(merged) == 5 and len(page.goto_calls) == 2:
        reporter.pass_("enrich_detail: max_targets만큼만 상세 방문하고 나머지 row는 원본 그대로 보존")
    else:
        reporter.fail(f"max_targets 처리 이상: merged={len(merged)} goto_calls={page.goto_calls}")


def check_enrich_detail_captcha_stops_and_preserves_remainder(reporter: ValidationReporter) -> None:
    rows = [_row(f"업체{i}", f"200000{i}") for i in range(4)]
    urls = [f"https://pcmap.place.naver.com/place/200000{i}/home" for i in range(4)]
    captcha_locator = FakeCaptchaLocator(count=1, visible=True, box={"width": 100, "height": 100})
    page = FakePage(
        entry_frame_by_url={u: FakeEntryFrame(title=f"업체{i}") for i, u in enumerate(urls)},
        captcha_selectors={"#wtm-captcha-root": captcha_locator},
    )
    collector = _make_collector([page])
    merged = collector.enrich_detail(rows)
    if len(merged) == 4 and len(page.goto_calls) == 1 and merged[0]["대표전화"] == "":
        reporter.pass_("enrich_detail: CAPTCHA 감지 시 즉시 중단, 이후 row들은 원본 그대로 보존(부분 결과)")
    else:
        reporter.fail(f"CAPTCHA 중단 처리 이상: merged_len={len(merged)} goto_calls={page.goto_calls}")


def check_enrich_detail_consecutive_failure_limit_stops(reporter: ValidationReporter) -> None:
    rows = [_row(f"업체{i}", f"300000{i}") for i in range(10)]
    # entry_frame_by_url을 비워 전부 entry_title_mismatch(title="")로 실패하게 만든다.
    page = FakePage(entry_frame_by_url={})
    collector = _make_collector([page])
    merged = collector.enrich_detail(rows)
    attempted_urls = len(page.goto_calls)
    # retry=_DETAIL_RETRY(1)이므로 실패 1건당 최대 2회 goto, consecutive_limit=5건 실패 시 중단
    if len(merged) == 10 and attempted_urls <= 12:
        reporter.pass_("enrich_detail: 연속 실패가 임계를 넘으면 중단하고 나머지 row는 원본 보존")
    else:
        reporter.fail(f"연속 실패 중단 처리 이상: merged_len={len(merged)} goto_calls={attempted_urls}")


def check_enrich_detail_success_merges_into_row(reporter: ValidationReporter) -> None:
    rows = [_row("카페 병합", "1000001")]
    page = FakePage(entry_frame_by_url={PLACE_URL_1: FakeEntryFrame(title="카페 병합", phone="02-9999-8888", address="상세주소")})
    collector = _make_collector([page])
    merged = collector.enrich_detail(rows)
    if merged[0]["대표전화"] == "02-9999-8888" and merged[0]["주소"] == "상세주소":
        reporter.pass_("enrich_detail: 성공한 상세 결과가 place_id exact 일치로 원본 row에 정확히 병합됨")
    else:
        reporter.fail(f"성공 병합 이상: {merged}")


# ---------------------------------------------------------------------------
# 3. should_continue(사용자 중지) / on_progress(진행률) - PAGE300-DETAIL-2
# ---------------------------------------------------------------------------


def check_fetch_place_detail_stops_immediately_when_should_continue_false(reporter: ValidationReporter) -> None:
    row = _row("카페 중지", "1000001")
    page = FakePage(entry_frame_by_url={PLACE_URL_1: FakeEntryFrame(title="카페 중지", phone="02-1111-1111")})
    result = _fetch_place_detail(row=row, page=page, should_continue=lambda: False)
    if not result["detail_success"] and result["detail_stop_reason"] == "user_stopped" and len(page.goto_calls) == 0:
        reporter.pass_("_fetch_place_detail: should_continue=False면 첫 시도조차 하지 않고 즉시 user_stopped")
    else:
        reporter.fail(f"should_continue 즉시중단 처리 이상: {result} goto_calls={page.goto_calls}")


def check_enrich_detail_should_continue_stops_new_visits_and_preserves_remainder(reporter: ValidationReporter) -> None:
    """on_progress로 "2개 row가 끝났다"는 사실을 확인한 뒤에만 should_continue를
    False로 바꾼다 - _fetch_place_detail 내부에서도 should_continue를 한 번 더
    확인하므로(요청서 §6 "retry 전"), row 하나당 호출 횟수가 1회로 고정된다고
    가정하지 않고 실제 완료 개수 기준으로 중지 시점을 판정한다."""
    rows = [_row(f"업체{i}", f"400000{i}") for i in range(5)]
    urls = [f"https://pcmap.place.naver.com/place/400000{i}/home" for i in range(5)]
    page = FakePage(entry_frame_by_url={u: FakeEntryFrame(title=f"업체{i}", phone="02-0000-0000") for i, u in enumerate(urls)})
    collector = _make_collector([page])

    state = {"stop": False}

    def should_continue():
        return not state["stop"]

    def on_progress(completed, total, success_count, failure_count):
        if completed >= 2:
            state["stop"] = True

    merged = collector.enrich_detail(rows, should_continue=should_continue, on_progress=on_progress)
    visited = sum(1 for r in merged if r.get("대표전화"))
    if len(merged) == 5 and visited == 2 and merged[2]["대표전화"] == "" and merged[3]["대표전화"] == "" and merged[4]["대표전화"] == "":
        reporter.pass_("enrich_detail: should_continue이 False가 되면 새 방문을 즉시 멈추고 나머지 row는 원본 그대로 보존")
    else:
        reporter.fail(f"사용자 중지 처리 이상: merged={merged}")


def check_enrich_detail_on_progress_reports_completed_total_success_failure(reporter: ValidationReporter) -> None:
    rows = [_row("성공업체", "5000001"), _row("실패업체", "5000002")]
    urls = ["https://pcmap.place.naver.com/place/5000001/home", "https://pcmap.place.naver.com/place/5000002/home"]
    page = FakePage(entry_frame_by_url={
        urls[0]: FakeEntryFrame(title="성공업체", phone="02-2222-2222"),
        urls[1]: FakeEntryFrame(title="완전히다른이름"),
    })
    collector = _make_collector([page])
    progress_calls = []
    collector.enrich_detail(rows, on_progress=lambda *args: progress_calls.append(args))
    if progress_calls == [(1, 2, 1, 0), (2, 2, 1, 1)]:
        reporter.pass_("enrich_detail: on_progress가 (completed,total,success,failure)를 매 row마다 정확히 보고")
    else:
        reporter.fail(f"on_progress 호출 이상: {progress_calls}")


def check_enrich_detail_on_progress_exception_does_not_break_collection(reporter: ValidationReporter) -> None:
    rows = [_row("업체A", "6000001")]
    page = FakePage(entry_frame_by_url={"https://pcmap.place.naver.com/place/6000001/home": FakeEntryFrame(title="업체A", phone="02-3333-3333")})
    collector = _make_collector([page])

    def bad_progress(*args):
        raise RuntimeError("progress UI 갱신 실패 시뮬레이션")

    merged = collector.enrich_detail(rows, on_progress=bad_progress)
    if merged[0]["대표전화"] == "02-3333-3333":
        reporter.pass_("enrich_detail: on_progress 콜백이 예외를 던져도 상세 수집 자체는 계속 진행됨")
    else:
        reporter.fail(f"on_progress 예외 처리 이상: {merged}")


def main() -> int:
    reporter = ValidationReporter()
    checks = [
        check_fetch_place_detail_success,
        check_fetch_place_detail_no_place_id,
        check_fetch_place_detail_title_mismatch_retries_then_fails,
        check_fetch_place_detail_http_blocking_status_stops_immediately,
        check_fetch_place_detail_captcha_stops_immediately,
        check_fetch_place_detail_retry_recovers,
        check_enrich_detail_max_targets_limits_visits,
        check_enrich_detail_captcha_stops_and_preserves_remainder,
        check_enrich_detail_consecutive_failure_limit_stops,
        check_enrich_detail_success_merges_into_row,
        check_fetch_place_detail_stops_immediately_when_should_continue_false,
        check_enrich_detail_should_continue_stops_new_visits_and_preserves_remainder,
        check_enrich_detail_on_progress_reports_completed_total_success_failure,
        check_enrich_detail_on_progress_exception_does_not_break_collection,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
