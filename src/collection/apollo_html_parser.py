"""Naver Place HTML에서 Apollo State를 읽는 순수 파서와, HTML/응답 문자열의
차단 신호를 분류하는 순수 함수를 담는다. 브라우저 실행·네트워크 요청을
전혀 수행하지 않으며, 목록 수집(network_browser_collector)과 홈페이지
보강(home_enrichment) 양쪽이 공동 사용한다."""
import json

_DETAIL_HTTP_BLOCKING_STATUSES = (403, 405, 429)


_SSR_MAX_HTML_CHARS = 5_000_000
_SSR_BLOCK_TEXT_MARKERS = ("보안 확인", "자동입력방지문자", "captcha_challenge", "captcha-wrapper")
_SSR_APOLLO_STATE_PREFIX = "window.__APOLLO_STATE__"


def _parse_apollo_state_from_html(html_text: str) -> dict | None:
    """SSR HTML 응답 본문에서 window.__APOLLO_STATE__ 값을 안전하게 추출한다.

    5W 감사(page300_5w_r1_multirun_evidence_integrity_audit)가 `\\{.*?\\}` 형태의
    non-greedy 정규식은 값 내부에 이스케이프된 `}` 문자열이 있으면 JSON 경계를
    조기 절단할 위험이 있다고 지적했다 - 이 함수는 대신 `json.JSONDecoder().
    raw_decode()`로 실제 JSON 문법 경계를 정확히 찾는다(중첩 객체/이스케이프
    문자열/트레일링 `</script>`에 안전). 병적으로 큰 응답(_SSR_MAX_HTML_CHARS
    초과)은 파싱을 시도하지 않고 None을 반환한다. 예외를 던지지 않고 항상
    dict 또는 None만 반환한다."""
    if not html_text or len(html_text) > _SSR_MAX_HTML_CHARS:
        return None
    marker_pos = html_text.find(_SSR_APOLLO_STATE_PREFIX)
    if marker_pos < 0:
        return None
    eq_pos = html_text.find("=", marker_pos + len(_SSR_APOLLO_STATE_PREFIX))
    if eq_pos < 0:
        return None
    start = eq_pos + 1
    while start < len(html_text) and html_text[start] in " \t\r\n":
        start += 1
    try:
        value, _end = json.JSONDecoder().raw_decode(html_text, start)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def _classify_ssr_block_signal(status_code, html_text: str) -> dict:
    """SSR 응답이 차단(CAPTCHA/HTTP 403·405·429)인지 텍스트/상태 기준으로
    판정한다. DOM 방문 기반 classify_captcha_signal은 렌더링된 page의
    locator(bounding_box 등)를 요구하므로 이 경로(page.request, 렌더링 없음)에는
    적용할 수 없다 - 5S/5T/5W가 실측으로 검증한 텍스트 마커를 그대로 재사용한
    별도의 텍스트 기반 판정으로 대체한다."""
    if status_code in _DETAIL_HTTP_BLOCKING_STATUSES:
        return {"blocked": True, "block_type": f"HTTP_{status_code}"}
    lowered = (html_text or "").lower()
    for marker in _SSR_BLOCK_TEXT_MARKERS:
        if marker in (html_text or "") or marker.lower() in lowered:
            return {"blocked": True, "block_type": "CAPTCHA_CHALLENGE"}
    return {"blocked": False, "block_type": ""}
