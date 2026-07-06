# 정식 출시 전 PC 단일 엔진 전환 - Stage 3B (카드 index 클릭 기반 상세 수집) 재설계.
#
# 설계 배경(2026-07-06 통제 live probe):
#   리스트 카드의 업체명 anchor href는 전부 "#"이라 리스트 단계에서 place_id/플레이스
#   URL을 사전 확보할 수 없다(Stage 3A의 place_id 사전 의존 구조는 전량 skip 되어
#   entryIframe 진입 0회였음). 따라서 진입 모델을 뒤집어, 카드 index를 클릭한 뒤
#   entryIframe URL에서 place_id를 "사후" 확보한다.
#
# 융합(fused) 순회(Option A):
#   list 단계와 detail 단계를 분리하지 않고, 카드 index마다 ①리스트 행 생성
#   (_build_row 재사용) → ②업체명 버튼 클릭 → ③entryIframe 갱신 wait(place_id 변경
#   AND 업체명 title 일치) → ④home 탭에서 전화/주소/홈페이지/SNS 추출 → ⑤place_id/
#   플레이스 URL/상세값을 행에 병합 → results.append. 이로써 행↔카드↔place_id 상관관계가
#   보장되고, 상세 실패 시에도 리스트 필드는 보존된다(부분 보존 강화).
#
# entryIframe home 탭만 사용:
#   probe 결과 home 탭에 전화/주소/홈페이지(SNS)가 모두 있고, "정보" 탭 클릭은
#   보안 확인(CAPTCHA)을 유발했다. 따라서 정보 탭으로 이동하지 않고 home 탭만 읽는다.
#   (CAPTCHA 우회/자동 해결은 시도하지 않는다.)
#
# selector 전략(probe 확정):
#   home 탭 상세는 <strong><span class="place_blind">{라벨}</span></strong>
#   <div class="vV_z_">{값}</div> 반복 구조다. place_blind는 안정적 a11y 클래스이므로
#   라벨 텍스트로 행을 특정한 뒤 값 div를 읽는다(hash class는 보조 후보로만 사용).
#   전화는 tel: href가 아니라 텍스트이므로 정규식으로 추출한다. 홈페이지/SNS는
#   "홈페이지" 라벨 행으로 범위를 한정해(footer 오탐 방지) href 도메인으로 분류한다.
#
# 실패 정책(Stage 3A 계약 유지):
#   단건 실패(클릭 대상 미발견/entry 미갱신/예외)는 1회 retry 후 skip(리스트 필드
#   보존, 상세 공란). 연속 실패가 임계를 넘으면 DetailCollectionAborted를 발생시키고,
#   build_full_collector의 except에서 classify_exception -> capture_diagnostics ->
#   diagnostics_captured=True 마커 -> exc.page 미부착 -> raise 로 처리된다(Stage 2
#   build_collector와 동일 계약, pipeline은 exc.page가 없어 자동 no-op).
import re
from datetime import datetime
from urllib.parse import quote

from src.pc.browser_session import BrowserSession
from src.pc.list_scraper import (
    _MAX_PAGES,
    _build_row,
    _check_stop,
    _click_next_page,
    _find_pc_cards,
    _light_scroll_cards,
    _safe_inner_text,
    _safe_text,
    _wait_while_paused,
)
from src.pc.safety import classify_exception


_ENTRY_WAIT_TIMEOUT_MS = 8000
_ENTRY_POLL_STEP_MS = 300
_CONSECUTIVE_FAILURE_LIMIT = 5
_DETAIL_RETRY = 1

# entryIframe 헤더의 업체명(title) 후보. span.IY7ZX는 probe 확정 hash class이며,
# 안정적 의미 훅이 없어 우선 후보로 두되 heading/h2 fallback을 함께 둔다.
ENTRY_TITLE_SELECTORS = [
    "span.IY7ZX",
    "[role='heading']",
    "h2",
]

_PHONE_RE = re.compile(r"0\d{1,3}-\d{3,4}-\d{4}")


class DetailCollectionAborted(Exception):
    """연속 상세 실패가 임계를 넘어 세션 단위 안전 종료가 필요할 때 발생합니다."""


def _parse_place_id_from_url(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/(\d{5,})", url)
    return match.group(1) if match else ""


def _title_matches(title: str, name: str) -> bool:
    """entryIframe title과 클릭한 업체명의 일치 여부(잔상/오매칭 방지).

    카드명은 업종 접미사를 포함할 수 있고 entry title은 순수 상호이므로,
    한쪽이 다른 쪽을 포함하면 일치로 본다(공백 정규화 후 비교).
    """
    if not title or not name:
        return False
    normalized_title = " ".join(title.split())
    normalized_name = " ".join(name.split())
    return normalized_name in normalized_title or normalized_title in normalized_name


def _entry_title(entry_frame) -> str:
    return _safe_text(entry_frame, ENTRY_TITLE_SELECTORS)


def _value_locator(entry_frame, label: str):
    """home 탭 상세에서 라벨(place_blind 텍스트)에 해당하는 값 div locator를 반환합니다.

    구조: <strong>...<span class="place_blind">{label}</span></strong>
          <div class="vV_z_">{값}</div>
    라벨 span의 조상 strong의 다음 형제 div가 값 영역이다. 없으면 None.
    """
    label_loc = entry_frame.locator(f"span.place_blind:has-text('{label}')").first
    try:
        if label_loc.count() == 0:
            return None
    except Exception:
        return None
    value_loc = label_loc.locator(
        "xpath=ancestor::strong[1]/following-sibling::div[1]"
    ).first
    try:
        return value_loc if value_loc.count() > 0 else None
    except Exception:
        return None


def _value_text(entry_frame, label: str) -> str:
    value_loc = _value_locator(entry_frame, label)
    if value_loc is None:
        return ""
    try:
        text = value_loc.inner_text(timeout=1000) or ""
    except Exception:
        return ""
    return " ".join(text.split())


def _extract_entry_phone(entry_frame) -> str:
    text = _value_text(entry_frame, "전화번호")
    if not text:
        return ""
    match = _PHONE_RE.search(text)
    return match.group(0) if match else ""


# 주소 값 영역(div.vV_z_)에는 실제 주소(span.pz7wy) 뒤에 인접 지하철역/출구/거리
# 안내가 같은 영역에 이어 붙는다(2026-07-06 live smoke 확인: "...1층 8강동구청역
# 2번 출구에서 866m 미터"). span.pz7wy는 안정적 실제 주소 전용 값이므로 우선
# 사용하고, 부재 시에만 전체 텍스트에서 역/출구/거리 안내를 정제해 사용한다.
_ADDRESS_NOISE_PATTERNS = [
    re.compile(r"\d*[가-힣A-Za-z]+역\s*\d+번\s*출구에서\s*\d+[mM](?:\s*미터)?"),
    re.compile(r"\d+번\s*출구에서\s*\d+[mM](?:\s*미터)?"),
    re.compile(r"\d+[mM]\s*미터"),
]


def _clean_address_fallback(text: str) -> str:
    cleaned = text
    for pattern in _ADDRESS_NOISE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return " ".join(cleaned.split())


def _extract_entry_address(entry_frame) -> str:
    value_loc = _value_locator(entry_frame, "주소")
    if value_loc is None:
        return ""

    try:
        address_span = value_loc.locator("span.pz7wy").first
        if address_span.count() > 0:
            text = address_span.inner_text(timeout=1000) or ""
            text = " ".join(text.split())
            if text:
                return text
    except Exception:
        pass

    try:
        text = value_loc.inner_text(timeout=1000) or ""
    except Exception:
        return ""
    return _clean_address_fallback(" ".join(text.split()))


def _extract_entry_sns(entry_frame):
    """home 탭 "홈페이지" 라벨 행의 외부 링크를 도메인으로 분류합니다.

    네이버는 대표 외부 링크를 링크 종류와 무관하게 "홈페이지"로 라벨링하므로,
    이 행의 href를 인스타/블로그/홈페이지로 분류한다. footer 오탐을 막기 위해
    반드시 이 행으로 범위를 한정한다. (homepage, insta, blog) 문자열을 반환한다.
    """
    homepage = ""
    insta = ""
    blog = ""
    value_loc = _value_locator(entry_frame, "홈페이지")
    if value_loc is None:
        return homepage, insta, blog
    try:
        hrefs = value_loc.locator("a[href^='http']").evaluate_all(
            "els => els.map(e => e.href)"
        )
    except Exception:
        hrefs = []
    for href in hrefs or []:
        low = (href or "").lower()
        if not low.startswith("http") or "pstatic.net" in low:
            continue
        if "instagram.com" in low:
            insta = insta or href
        elif "blog.naver.com" in low or low.startswith("https://blog.") or ".blog." in low:
            blog = blog or href
        elif not homepage:
            homepage = href
    return homepage, insta, blog


def _click_card_by_name(card, name: str) -> bool:
    """카드의 업체명 버튼을 클릭합니다(role/text 우선, hash class 비의존).

    href="#" SPA 구조이므로 anchor 텍스트로 대상을 특정한다. "저장"/썸네일 등
    오클릭을 막기 위해, 클릭 대상 텍스트가 업체명과 상호 포함 관계일 때만 클릭한다.
    """
    candidates = []
    if name:
        candidates.append(lambda: card.locator("a").filter(has_text=name).first)
    candidates.append(lambda: card.locator("a").first)

    for make_locator in candidates:
        try:
            locator = make_locator()
            if locator.count() == 0:
                continue
        except Exception:
            continue
        text = _safe_inner_text(locator)
        normalized = " ".join(text.split())
        if name and normalized and not (name in normalized or normalized in name):
            continue
        locator.click(timeout=3000)
        return True
    return False


def _wait_entry_updated(session, clicked_name: str, previous_place_id, timeout_ms: int):
    """카드 클릭 후 entryIframe이 새 대상으로 갱신될 때까지 bounded 폴링합니다.

    잔상/오매칭 방지 3중 조건: place_id 파싱 성공 AND place_id != previous_place_id
    AND entryIframe title이 클릭 업체명과 일치. 충족 시 (frame, place_id, url) 반환,
    timeout까지 미충족이면 (None, "", "") 반환(호출자가 skip 처리).
    플레이스 URL은 실제 entryIframe URL에서 volatile query를 제거해 사용한다
    (segment 하드코딩 없이 실제 URL을 신뢰).
    """
    waited = 0
    while waited < timeout_ms:
        frame = session.find_entry_frame()
        if frame is not None:
            url = getattr(frame, "url", "") or ""
            place_id = _parse_place_id_from_url(url)
            if place_id and (previous_place_id is None or place_id != previous_place_id):
                if _title_matches(_entry_title(frame), clicked_name):
                    return frame, place_id, url.split("?")[0]
        session.page.wait_for_timeout(_ENTRY_POLL_STEP_MS)
        waited += _ENTRY_POLL_STEP_MS
    return None, "", ""


def _attempt_card_detail(session, card, row, name, previous_place_id):
    """단건 카드 상세 진입/추출을 1회 시도합니다. ("ok"|"fail", error_message)를 반환합니다.

    성공 시 place_id/플레이스 URL은 항상 갱신하고, 전화/주소는 값이 있을 때만
    덮어써 리스트 값을 다운그레이드하지 않는다. 홈페이지/인스타/블로그는 수집 결과를
    그대로 반영한다(exporter 연결은 후속 단계).
    """
    try:
        if not _click_card_by_name(card, name):
            return "fail", "click target not found"
        entry_frame, place_id, place_url = _wait_entry_updated(
            session, name, previous_place_id, _ENTRY_WAIT_TIMEOUT_MS
        )
        if entry_frame is None:
            return "fail", "entry frame not updated (stale or slow)"

        phone = _extract_entry_phone(entry_frame)
        address = _extract_entry_address(entry_frame)
        homepage, insta, blog = _extract_entry_sns(entry_frame)

        row["place_id"] = place_id
        row["플레이스 URL"] = place_url
        if phone:
            row["대표전화"] = phone
        if address:
            row["주소"] = address
        row["홈페이지"] = homepage
        row["인스타"] = insta
        row["블로그"] = blog
        return "ok", ""
    except Exception as exc:
        return "fail", f"{type(exc).__name__}: {exc}"


def _enrich_card(session, card, row, previous_place_id, retry):
    """카드 상세를 retry 포함해 시도합니다. ("ok"|"fail", error, new_previous_place_id)."""
    name = str(row.get("업체명") or "")
    outcome, error = _attempt_card_detail(session, card, row, name, previous_place_id)
    attempts_left = retry
    while outcome == "fail" and attempts_left > 0:
        attempts_left -= 1
        outcome, error = _attempt_card_detail(session, card, row, name, previous_place_id)

    if outcome == "ok":
        return "ok", "", (row.get("place_id") or previous_place_id)
    return "fail", error, previous_place_id


def collect_full(
    session,
    search_frame,
    keyword,
    limit,
    new_open_only,
    stop_event,
    pause_event,
    results,
    *,
    build_row_fn=_build_row,
    enrich_fn=_enrich_card,
    find_cards_fn=_find_pc_cards,
    scroll_fn=_light_scroll_cards,
    next_page_fn=_click_next_page,
    consecutive_limit: int = _CONSECUTIVE_FAILURE_LIMIT,
    retry: int = _DETAIL_RETRY,
) -> None:
    """searchIframe 리스트를 카드 index로 순회하며 list+detail을 융합 수집합니다.

    카드마다 리스트 행을 만들고(유효하지 않으면 skip), 그 카드를 클릭해 entryIframe에서
    place_id/플레이스 URL/전화/주소/홈페이지/SNS를 확보해 행에 병합한 뒤 results에
    append 한다. 상세 실패 행도 리스트 필드는 보존한 채 append 된다(부분 보존).
    연속 실패가 consecutive_limit을 넘으면 DetailCollectionAborted를 raise 한다.
    """
    page = session.page
    collected_at = datetime.now().strftime("%Y-%m-%d")
    scan_limit = max(limit * 10, 50) if new_open_only else limit
    calculated_scrolls = max(2, (scan_limit // 10) + 1)
    seen: set = set()
    current_page = 1
    previous_place_id = None
    consecutive_failures = 0
    last_error = ""

    while len(results) < limit and current_page <= _MAX_PAGES:
        if _check_stop(stop_event):
            break
        if _wait_while_paused(page, stop_event, pause_event):
            break

        print(f"[detail_scraper] collect page={current_page}")
        cards = find_cards_fn(search_frame)
        scroll_fn(
            page, cards, max_scrolls=calculated_scrolls, stop_event=stop_event, pause_event=pause_event
        )
        card_count = cards.count()
        print(f"[detail_scraper] candidate cards={card_count}")

        for index in range(card_count):
            if _check_stop(stop_event):
                break
            if len(results) >= limit:
                break
            if _wait_while_paused(page, stop_event, pause_event):
                break

            card = cards.nth(index)
            row = build_row_fn(card, collected_at, new_open_only, seen)
            if row is None:
                continue
            row.setdefault("홈페이지", "")
            row.setdefault("인스타", "")
            row.setdefault("블로그", "")

            outcome, error, previous_place_id = enrich_fn(
                session, card, row, previous_place_id, retry
            )
            results.append(row)
            if len(results) % 10 == 0 or len(results) == limit:
                print(f"[detail_scraper] collecting... {len(results)}/{limit}")

            if outcome == "ok":
                consecutive_failures = 0
                continue

            consecutive_failures += 1
            last_error = error
            if consecutive_failures >= consecutive_limit:
                raise DetailCollectionAborted(
                    f"연속 {consecutive_failures}건 상세 진입 실패로 세션 안전 종료: {last_error}"
                )

        if len(results) >= limit:
            break
        if _check_stop(stop_event):
            break
        if current_page >= _MAX_PAGES:
            break
        if _wait_while_paused(page, stop_event, pause_event):
            break

        next_page = current_page + 1
        if not next_page_fn(search_frame, next_page):
            print(f"[detail_scraper] next page not found: {next_page}")
            break

        page.wait_for_timeout(2000)
        current_page += 1

        if _check_stop(stop_event):
            break
        if _wait_while_paused(page, stop_event, pause_event):
            break

    print(f"[detail_scraper] full collect done, rows={len(results)}")


def build_full_collector(
    diagnostic_config,
    *,
    session_factory=BrowserSession,
    collect_fn=collect_full,
):
    """pipeline.collect_pc_full이 기대하는 collector를 반환하는 full(list+detail) 팩토리입니다.

    list_scraper.build_collector()(list-only)와 별개 함수이며 그 의미를 변경하지 않는다.
    이 collector는 카드 index 순회로 list+detail을 융합 수집한다.

    실패 시 Stage 2 build_collector와 동일한 진단 캡처 계약을 따른다:
    classify_exception -> session.capture_diagnostics -> diagnostics_captured=True 마커
    -> exc.page는 붙이지 않고 raise. 그때까지 results에 쌓인 행은 부분 보존되어
    pipeline이 반환한다.
    """

    def _collector(keyword, limit, new_open_only, stop_event, pause_event, results) -> None:
        search_url = f"https://map.naver.com/v5/search/{quote(keyword)}"
        with session_factory(diagnostic_config) as session:
            try:
                session.goto(search_url)
                search_frame = session.find_search_frame()
                if search_frame is None:
                    return
                collect_fn(
                    session, search_frame, keyword, limit, new_open_only, stop_event, pause_event, results
                )
            except Exception as exc:
                decision = classify_exception(exc)
                session.capture_diagnostics(label=keyword, exception=exc, safety_decision=decision)
                session.keep_open_if_configured()
                exc.diagnostics_captured = True
                raise

    return _collector
