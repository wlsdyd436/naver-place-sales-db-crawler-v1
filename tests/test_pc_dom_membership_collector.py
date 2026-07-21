from pathlib import Path
import json
import sys


# PAGE300-DOM-1: src/pc/network_browser_collector.py::collect_dom_membership_query를
# 검증하는 standalone 스크립트(실제 Playwright/브라우저 없음). FakePage/FakeDomFrame이
# frame.evaluate(script)를 스크립트 내 고유 마커 문자열로 분기해 DOM row/Apollo
# entity/스크롤 결과/현재 페이지 top-10을 그대로 반환한다(test_pc_network_pagination.py의
# FakePage 패턴을 참고했지만 파일 간 import 없이 독립적으로 재정의한다).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.network_browser_collector import (
    _APOLLO_ENTITY_EXTRACTION_JS,
    _DOM_ROW_EXTRACTION_JS,
    _DOM_SCROLL_JS,
    collect_dom_membership_query,
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

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print("검증 요약")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"WARN: {self.warn_count}")
        print(f"FINAL: {final}")
        print("====================")


JOB = {"query": "서울특별시 강동구 천호동 카페"}


class FakeLocator:
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


class FakeRequest:
    def __init__(self, resource_type, method="GET"):
        self.resource_type = resource_type
        self.method = method
        self.failure = None
        self._response = None

    def response(self):
        return self._response


class FakeResponse:
    def __init__(self, url, status, resource_type, *, body=None, headers=None):
        self.url = url
        self.status = status
        self.request = FakeRequest(resource_type)
        self.request._response = self
        self._body = body
        self.headers = headers or {}
        self.simulate_request_failed = False

    def body(self):
        return self._body

    def text(self):
        return (self._body or b"").decode("utf-8")


CANDIDATE_URL = "https://map.naver.com/p/api/search/allSearch?query=x"


def _place_response(id_name_pairs, *, url=CANDIDATE_URL, status=200):
    items = [{"id": i, "name": n} for i, n in id_name_pairs]
    body = json.dumps({"result": {"place": {"list": items}}}).encode("utf-8")
    return FakeResponse(url, status, "xhr", body=body)


class FakeButtonLocator:
    def __init__(self, spec: dict, frame_ref):
        self._spec = spec
        self._frame_ref = frame_ref

    @property
    def first(self):
        return self

    def count(self):
        return self._spec.get("count", 0)

    def is_visible(self, timeout=None):
        return self._spec.get("visible", True)

    def is_enabled(self):
        return self._spec.get("enabled", True)

    def scroll_into_view_if_needed(self):
        pass

    def click(self):
        self._spec["click_calls"] = self._spec.get("click_calls", 0) + 1
        error = self._spec.get("click_error")
        if error is not None:
            raise error
        target_page = self._spec.get("target_page")
        if target_page is not None:
            self._frame_ref.current_page = target_page


class FakeDomFrame:
    """pages_plan: {page_number: {"dom_rows": [...]}}. apollo_plan(선택):
    {page_number: {"available": bool, "entities": [...]}}(기본은 available=True,
    entities=[]). click_plan: {"목표 페이지 번호 문자열": spec dict}."""

    def __init__(self, pages_plan: dict, click_plan: dict = None, apollo_plan: dict = None,
                 *, container_lost_on_page=None, name="searchIframe"):
        self.name = name
        self._pages_plan = pages_plan
        self._click_plan = click_plan or {}
        self._apollo_plan = apollo_plan or {}
        self._container_lost_on_page = container_lost_on_page
        self.current_page = 1
        self.evaluate_calls: list = []

    def _current_dom_rows(self):
        return self._pages_plan.get(self.current_page, {}).get("dom_rows", [])

    def evaluate(self, script):
        self.evaluate_calls.append(script)
        if script == _DOM_SCROLL_JS:
            if self._container_lost_on_page == self.current_page:
                return {"status": "no_container", "iters": 0}
            rows = self._current_dom_rows()
            return {"status": "done", "iters": 5, "scrollHeight": 1000, "rowCount": len(rows), "nameCount": len(rows)}
        if script == _DOM_ROW_EXTRACTION_JS:
            return self._current_dom_rows()
        if script == _APOLLO_ENTITY_EXTRACTION_JS:
            return self._apollo_plan.get(self.current_page, {"available": True, "entities": []})
        # _CURRENT_PAGE_AND_TOP10_JS(모듈에 노출되지 않으므로 문자열 상수 대신
        # 위 3개와 겹치지 않는 마커로 분기한다)
        rows = self._current_dom_rows()
        names = [r.get("name", "") for r in rows[:10]]
        return {"page": self.current_page, "top10": names}

    def get_by_role(self, role, name=None, exact=None):
        spec = self._click_plan.get(name)
        if spec is None:
            return FakeButtonLocator({"count": 0}, self)
        return FakeButtonLocator(spec, self)


class FakePage:
    def __init__(self, frame: FakeDomFrame, *, initial_responses=None, captcha_selectors=None, goto_error=None):
        self._frame = frame
        self._handlers: dict = {}
        self._responses = list(initial_responses or [])
        self._captcha_selectors = captcha_selectors or {}
        self._goto_error = goto_error
        self.goto_calls: list = []
        self.wait_calls: list = []

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event, handler):
        handlers = self._handlers.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        if self._goto_error is not None:
            raise self._goto_error
        self._deliver_pending()

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)
        self._deliver_pending()

    def _deliver_pending(self):
        while self._responses:
            response = self._responses.pop(0)
            for handler in list(self._handlers.get("response", [])):
                handler(response)
            for handler in list(self._handlers.get("requestfinished", [])):
                handler(response.request)

    def locator(self, selector):
        return self._captcha_selectors.get(selector, FakeLocator(count=0))

    def frame(self, name=None):
        return self._frame


def _dom_row(dom_index, name, category="카페", place_id="", href=""):
    """place_id는 PAGE300-DOM-2부터 React Fiber fast-path 후보(identifier_
    candidates.fast_item_id)로 주입된다(DOM anchor href는 실측상 전부 "#"
    placeholder라 더 이상 주 식별 경로가 아니다). 숫자 5~15자리가 아니면
    resolve_dom_identifier가 UNRESOLVED로 안전하게 거부하므로, place_id로
    단순 dedup 유일성만 표현하고 싶은 기존 테스트(비숫자 문자열 등)는 영향받지
    않는다(dedup은 raw_text/이름 기반 fallback으로 계속 동작)."""
    anchor_hrefs = [href] if href else []
    identifier_candidates = {"fast_item_id": place_id} if place_id else {}
    return {
        "dom_index": dom_index,
        "name": name,
        "category": category,
        "raw_text": f"{name}{category}",
        "identifier_candidates": identifier_candidates,
        "place_url": "",
        "anchor_hrefs": anchor_hrefs,
        "data_attributes": {},
    }


# ---------------------------------------------------------------------------
# 1. 검증된 selector/스크롤 방식이 실제로 쓰였는지(스크립트 리터럴 검사)
# ---------------------------------------------------------------------------


def check_scroll_js_uses_scrollby_not_scrollto(reporter: ValidationReporter) -> None:
    ok = (
        "scrollBy" in _DOM_SCROLL_JS
        and "scrollTo" not in _DOM_SCROLL_JS
        and "#_pcmap_list_scroll_container" in _DOM_SCROLL_JS
        and "stable = 0" in _DOM_SCROLL_JS
    )
    if ok:
        reporter.pass_("_DOM_SCROLL_JS: scrollBy 상대 증분 + list container 한정 + 변화 시 stable 리셋")
    else:
        reporter.fail("_DOM_SCROLL_JS가 검증된 scrollBy 방식을 사용하지 않음")


def check_row_selector_is_specific_not_generic_li(reporter: ValidationReporter) -> None:
    ok = "li.UEzoS.rTjJo" in _DOM_ROW_EXTRACTION_JS and ".TYaxT" in _DOM_ROW_EXTRACTION_JS and ".KCMnt" in _DOM_ROW_EXTRACTION_JS
    if ok:
        reporter.pass_("_DOM_ROW_EXTRACTION_JS: li.UEzoS.rTjJo/.TYaxT/.KCMnt 검증된 selector 사용")
    else:
        reporter.fail("_DOM_ROW_EXTRACTION_JS가 검증된 row selector를 사용하지 않음")


# ---------------------------------------------------------------------------
# 2. skeleton 제외 / DOM 순서 보존 / page별 가변 수량
# ---------------------------------------------------------------------------


def check_skeleton_excluded_and_order_preserved(reporter: ValidationReporter) -> None:
    rows_page1 = [
        _dom_row(0, "카페 A", place_id="1"),
        _dom_row(1, "", place_id=""),  # skeleton
        _dom_row(2, "카페 B", place_id="2"),
        _dom_row(3, "카페 C", place_id="3"),
    ]
    frame = FakeDomFrame({1: {"dom_rows": rows_page1}})
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    names = [r["업체명"] for r in result["rows"]]
    if names == ["카페 A", "카페 B", "카페 C"] and result["stop_reason"] == "max_page_count_reached":
        reporter.pass_("skeleton row 제외 + 나머지 DOM 순서 그대로 보존")
    else:
        reporter.fail(f"skeleton 제외/순서 보존 실패: names={names} stop_reason={result['stop_reason']}")


def check_variable_page_counts(reporter: ValidationReporter) -> None:
    rows_page1 = [_dom_row(i, f"1페이지업체{i}", place_id=f"p1-{i}") for i in range(3)]
    rows_page2 = [_dom_row(i, f"2페이지업체{i}", place_id=f"p2-{i}") for i in range(5)]
    frame = FakeDomFrame(
        {1: {"dom_rows": rows_page1}, 2: {"dom_rows": rows_page2}},
        click_plan={"2": {"count": 1, "visible": True, "enabled": True, "target_page": 2}},
    )
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if (
        len(result["rows"]) == 8
        and result["page_count"] == 2
        and result["stop_reason"] == "next_page_button_not_found"
        and result["per_page_diagnostics"][0]["dom_row_count"] == 3
        and result["per_page_diagnostics"][1]["dom_row_count"] == 5
    ):
        reporter.pass_("page별 가변 DOM 수량(3건/5건) 정상 처리, 다음 page 버튼 없으면 정상 종료")
    else:
        reporter.fail(f"가변 page 처리 이상: rows={len(result['rows'])} result={result['page_count']} stop={result['stop_reason']}")


# ---------------------------------------------------------------------------
# 3. target 300 trim
# ---------------------------------------------------------------------------


def check_target_300_trim_preserves_order(reporter: ValidationReporter) -> None:
    rows_page1 = [_dom_row(i, f"업체{i:03d}", place_id=f"id-{i}") for i in range(305)]
    frame = FakeDomFrame({1: {"dom_rows": rows_page1}})
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if (
        len(result["rows"]) == 300
        and result["stop_reason"] == "target_reached"
        and result["rows"][0]["업체명"] == "업체000"
        and result["rows"][-1]["업체명"] == "업체299"
    ):
        reporter.pass_("target=300: 305건 중 순서 보존한 채 300개로 trim, target_reached")
    else:
        reporter.fail(f"target trim 이상: len={len(result['rows'])} stop={result['stop_reason']}")


# ---------------------------------------------------------------------------
# 4. 안전 중단: CAPTCHA / HTTP 403·405 / 429
# ---------------------------------------------------------------------------


def check_captcha_safe_stop(reporter: ValidationReporter) -> None:
    frame = FakeDomFrame({1: {"dom_rows": [_dom_row(0, "카페 A", place_id="1")]}})
    captcha_locator = FakeLocator(count=1, visible=True, box={"width": 300, "height": 200})
    page = FakePage(frame, captcha_selectors={"#wtm-captcha-root": captcha_locator})
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if result["active_captcha_detected"] and result["stop_reason"] == "captcha_detected" and result["rows"] == []:
        reporter.pass_("CAPTCHA 활성 감지 시 즉시 안전 중단(rows=[])")
    else:
        reporter.fail(f"CAPTCHA 안전 중단 실패: {result}")


def check_http_403_405_safe_stop(reporter: ValidationReporter) -> None:
    frame = FakeDomFrame({1: {"dom_rows": [_dom_row(0, "카페 A", place_id="1")]}})
    page = FakePage(frame, initial_responses=[_place_response([("9", "네트워크업체")], status=405)])
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if result["stop_reason"] == "candidate_http_error":
        reporter.pass_("HTTP 405 candidate 감지 시 안전 중단(candidate_http_error)")
    else:
        reporter.fail(f"HTTP 오류 안전 중단 실패: {result}")


def check_http_429_safe_stop(reporter: ValidationReporter) -> None:
    frame = FakeDomFrame({1: {"dom_rows": [_dom_row(0, "카페 A", place_id="1")]}})
    page = FakePage(frame, initial_responses=[_place_response([("9", "네트워크업체")], status=429)])
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if result["status_429_seen"] and result["stop_reason"] == "status_429_seen":
        reporter.pass_("HTTP 429 감지 시 안전 중단(status_429_seen)")
    else:
        reporter.fail(f"429 안전 중단 실패: {result}")


def check_dom_container_lost_safe_stop(reporter: ValidationReporter) -> None:
    frame = FakeDomFrame({1: {"dom_rows": []}}, container_lost_on_page=1)
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if result["stop_reason"] == "dom_container_lost":
        reporter.pass_("list container 소실 시 안전 중단(dom_container_lost)")
    else:
        reporter.fail(f"container lost 안전 중단 실패: {result}")


# ---------------------------------------------------------------------------
# 5. page signature 미변경 시 전환 실패
# ---------------------------------------------------------------------------


def check_signature_unchanged_stops_pagination(reporter: ValidationReporter) -> None:
    same_rows = [_dom_row(i, f"업체{i}", place_id=str(i)) for i in range(10)]
    frame = FakeDomFrame(
        {1: {"dom_rows": same_rows}, 2: {"dom_rows": list(same_rows)}},
        click_plan={"2": {"count": 1, "visible": True, "enabled": True, "target_page": 2}},
    )
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if result["stop_reason"] == "next_page_dom_signature_unchanged" and result["page_count"] == 1:
        reporter.pass_("클릭 후 page 번호는 바뀌었지만 top-10 signature가 그대로면 전환 실패로 안전 중단")
    else:
        reporter.fail(f"signature 미변경 감지 실패: {result}")


def check_next_page_transition_timeout(reporter: ValidationReporter) -> None:
    rows_page1 = [_dom_row(i, f"업체{i}", place_id=str(i)) for i in range(5)]
    # click_plan에 target_page를 지정하지 않아 클릭해도 frame.current_page가 그대로 1로 남는다
    # -> _CURRENT_PAGE_AND_TOP10_JS가 계속 page=1(기대값 2와 불일치)만 반환 -> transition_timeout.
    frame = FakeDomFrame(
        {1: {"dom_rows": rows_page1}},
        click_plan={"2": {"count": 1, "visible": True, "enabled": True}},
    )
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=5)
    if result["stop_reason"] == "next_page_dom_transition_timeout" and result["page_count"] == 1:
        reporter.pass_("클릭해도 실제 페이지 번호가 기대값과 계속 불일치하면 전환 타임아웃으로 안전 중단")
    else:
        reporter.fail(f"transition timeout 처리 이상: {result}")


# ---------------------------------------------------------------------------
# 6. DOM+Network / DOM+Apollo 매핑(collector 배선 검증), Apollo unavailable 저하
# ---------------------------------------------------------------------------


def check_dom_network_id_mapping_end_to_end(reporter: ValidationReporter) -> None:
    dom_rows = [_dom_row(0, "카페 A", place_id="7777777")]
    frame = FakeDomFrame({1: {"dom_rows": dom_rows}})
    page = FakePage(frame, initial_responses=[_place_response([("7777777", "카페 A(네트워크)")])])
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    row = result["rows"][0] if result["rows"] else {}
    if row.get("match_confidence") == "EXACT_ID" and result["per_page_diagnostics"][0]["exact_id_match_count"] == 1:
        reporter.pass_("DOM place_id와 Network place_id가 일치하면 collector 배선에서도 EXACT_ID로 매칭됨")
    else:
        reporter.fail(f"DOM+Network ID 매핑 배선 실패: row={row} diag={result['per_page_diagnostics']}")


def check_dom_apollo_id_mapping_end_to_end(reporter: ValidationReporter) -> None:
    dom_rows = [_dom_row(0, "카페 B", place_id="8888888")]
    apollo_entities = [{"apollo_key": "PlaceListBusinessesItem:8888888:8888888", "place_id": "8888888", "name": "카페 B", "category": "카페", "address": "서울 강동구"}]
    frame = FakeDomFrame({1: {"dom_rows": dom_rows}}, apollo_plan={1: {"available": True, "entities": apollo_entities}})
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    row = result["rows"][0] if result["rows"] else {}
    if row.get("match_confidence") == "EXACT_ID" and row.get("주소") == "서울 강동구":
        reporter.pass_("DOM place_id와 Apollo place_id가 일치하면 collector 배선에서도 EXACT_ID로 매칭되고 주소 보강됨")
    else:
        reporter.fail(f"DOM+Apollo ID 매핑 배선 실패: row={row}")


def check_apollo_unavailable_keeps_dom_rows(reporter: ValidationReporter) -> None:
    dom_rows = [_dom_row(0, "카페 C", category="카페")]
    frame = FakeDomFrame({1: {"dom_rows": dom_rows}}, apollo_plan={1: {"available": False, "entities": []}})
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    diag = result["per_page_diagnostics"][0]
    if len(result["rows"]) == 1 and result["rows"][0]["업체명"] == "카페 C" and diag["apollo_available"] is False:
        reporter.pass_("Apollo state 자체를 못 읽어도(unavailable) DOM 기반 결과는 그대로 유지됨")
    else:
        reporter.fail(f"Apollo unavailable 저하 처리 실패: rows={result['rows']} diag={diag}")


def check_network_only_entity_excluded_from_rows(reporter: ValidationReporter) -> None:
    """DOM에 없는 Network entity(place_id 999)는 최종 rows에 나타나면 안 된다."""
    dom_rows = [_dom_row(0, "카페 D", place_id="1")]
    frame = FakeDomFrame({1: {"dom_rows": dom_rows}})
    page = FakePage(frame, initial_responses=[_place_response([("1", "카페 D"), ("999", "네트워크전용업체")])])
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    names = [r["업체명"] for r in result["rows"]]
    if names == ["카페 D"]:
        reporter.pass_("Network 응답에만 있는 entity(999)는 DOM에 없으므로 최종 rows에서 제외됨")
    else:
        reporter.fail(f"Network-only entity가 결과에 섞여 들어옴: {names}")


def check_excel_11_columns_present_in_collector_rows(reporter: ValidationReporter) -> None:
    from src.exporter import MERGED_COLUMNS

    dom_rows = [_dom_row(0, "카페 E")]
    frame = FakeDomFrame({1: {"dom_rows": dom_rows}})
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    row = result["rows"][0]
    missing = [col for col in MERGED_COLUMNS if col not in row]
    if not missing:
        reporter.pass_("collect_dom_membership_query 결과 row가 Excel 11컬럼 키를 모두 포함")
    else:
        reporter.fail(f"Excel 컬럼 누락: {missing}")


# ---------------------------------------------------------------------------
# 7. React Fiber place_id 추출(PAGE300-DOM-2) - JS 리터럴 구조 확인 + collector 배선
# ---------------------------------------------------------------------------


def check_dom_row_js_includes_fiber_extraction(reporter: ValidationReporter) -> None:
    ok = (
        "__reactFiber$" in _DOM_ROW_EXTRACTION_JS
        and "__reactProps$" in _DOM_ROW_EXTRACTION_JS
        and "pendingProps" in _DOM_ROW_EXTRACTION_JS
        and "apolloCacheId" in _DOM_ROW_EXTRACTION_JS
        and "identifier_candidates" in _DOM_ROW_EXTRACTION_JS
    )
    if ok:
        reporter.pass_("_DOM_ROW_EXTRACTION_JS: __reactFiber$ 동적 suffix key 탐색 + fast path(item.id/apolloCacheId) 포함")
    else:
        reporter.fail("_DOM_ROW_EXTRACTION_JS에 React Fiber 추출 로직이 없음")


def check_dom_row_js_bounded_search_has_guards(reporter: ValidationReporter) -> None:
    ok = (
        "MAX_DEPTH" in _DOM_ROW_EXTRACTION_JS
        and "MAX_VISITED" in _DOM_ROW_EXTRACTION_JS
        and "visited.seen.has(obj)" in _DOM_ROW_EXTRACTION_JS
        and "'stateNode'" in _DOM_ROW_EXTRACTION_JS
    )
    if ok:
        reporter.pass_("_DOM_ROW_EXTRACTION_JS bounded search: 최대 깊이/최대 방문 수/순환 참조 차단/stateNode 등 스킵 키 모두 포함")
    else:
        reporter.fail("_DOM_ROW_EXTRACTION_JS bounded search guard가 누락됨")


def check_fiber_absent_row_kept_unresolved(reporter: ValidationReporter) -> None:
    """identifier_candidates가 전혀 없는(Fiber를 못 찾은) row도 삭제되지 않고
    UNRESOLVED로 유지되어야 한다."""
    dom_rows = [_dom_row(0, "카페 노식별")]  # place_id 미지정 -> identifier_candidates={}
    frame = FakeDomFrame({1: {"dom_rows": dom_rows}})
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    if len(result["rows"]) == 1 and result["rows"][0]["업체명"] == "카페 노식별":
        reporter.pass_("Fiber 후보가 전혀 없어 place_id가 UNRESOLVED여도 row는 삭제되지 않고 유지됨")
    else:
        reporter.fail(f"Fiber 없음 row 처리 이상: {result['rows']}")


def check_place_id_300_uniqueness_through_collector(reporter: ValidationReporter) -> None:
    """300개 row 각각 다른 fast-path id를 가지면 collector를 통과한 최종 rows의
    place_id 300개가 모두 서로 달라야 한다(dedup이 place_id 기준으로 정확히 동작)."""
    dom_rows = [
        _dom_row(i, f"업체{i:03d}", place_id=str(200000000 + i))
        for i in range(300)
    ]
    frame = FakeDomFrame({1: {"dom_rows": dom_rows}})
    page = FakePage(frame)
    result = collect_dom_membership_query(page, JOB, 300, collected_at="2026-07-21", max_pages=1)
    place_ids = {r["place_id"] for r in result["rows"]}
    if len(result["rows"]) == 300 and len(place_ids) == 300:
        reporter.pass_("collect_dom_membership_query: 300개 fast-path id가 최종 rows에서 300개 고유 place_id로 유지됨")
    else:
        reporter.fail(f"place_id 300 uniqueness 이상: rows={len(result['rows'])} unique_place_id={len(place_ids)}")


def main() -> int:
    reporter = ValidationReporter()
    checks = [
        check_scroll_js_uses_scrollby_not_scrollto,
        check_row_selector_is_specific_not_generic_li,
        check_skeleton_excluded_and_order_preserved,
        check_variable_page_counts,
        check_target_300_trim_preserves_order,
        check_captcha_safe_stop,
        check_http_403_405_safe_stop,
        check_http_429_safe_stop,
        check_dom_container_lost_safe_stop,
        check_signature_unchanged_stops_pagination,
        check_next_page_transition_timeout,
        check_dom_network_id_mapping_end_to_end,
        check_dom_apollo_id_mapping_end_to_end,
        check_apollo_unavailable_keeps_dom_rows,
        check_network_only_entity_excluded_from_rows,
        check_excel_11_columns_present_in_collector_rows,
        check_dom_row_js_includes_fiber_extraction,
        check_dom_row_js_bounded_search_has_guards,
        check_fiber_absent_row_kept_unresolved,
        check_place_id_300_uniqueness_through_collector,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
