from pathlib import Path
import inspect
import sys


# ARCH-300C WIRE-2D: README.md/LEGAL_NOTICE.md/UI 안내·정책 탭의 문구가
# 실제 Network/List 기본 엔진 동작과 일치하는지 검증하는 standalone
# 스크립트(실제 UI 창/Tk mainloop 없음, 텍스트/소스 기반 검사만 수행).
# 전체 문장 일치가 아니라 핵심 구절·의미 존재 여부만 검사한다 - 문장부호나
# 줄바꿈이 바뀌어도 깨지지 않도록 하기 위함.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import ui

README_TEXT = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
LEGAL_NOTICE_TEXT = (ROOT_DIR / "LEGAL_NOTICE.md").read_text(encoding="utf-8")
POLICY_TAB_SOURCE = inspect.getsource(ui.SalesDbCrawlerApp._build_policy_tab)


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


def _legal_notice_current_section_text() -> str:
    """LEGAL_NOTICE.md는 날짜 기반 append-only 섹션 구조(4→5→6)를 쓰며,
    과거 섹션(예: 4번의 "10건 이내")은 역사적 기록으로 그대로 보존한다.
    "현재 적용되는" 최신 섹션만 검사하고 싶을 때는 마지막 '## ' 섹션부터
    파일 끝까지만 잘라서 본다(사용자 확인: 과거 섹션 보존 + 최신 섹션만 검증)."""
    sections = LEGAL_NOTICE_TEXT.split("\n## ")
    return "## " + sections[-1] if len(sections) > 1 else LEGAL_NOTICE_TEXT


LEGAL_NOTICE_CURRENT_SECTION = _legal_notice_current_section_text()


# ---------------------------------------------------------------------------
# 1~9. README.md
# ---------------------------------------------------------------------------


def check_readme_network_flow_described(reporter: ValidationReporter) -> None:
    ok = "검색 조합" in README_TEXT and "브라우저" in README_TEXT and "정상적으로 수신" in README_TEXT
    if ok:
        reporter.pass_("README: 검색 조합 생성 → 브라우저가 정상적으로 수신한 응답 처리라는 현재 흐름 설명 존재")
    else:
        reporter.fail("README에 Network/List 현재 흐름 설명(검색 조합/브라우저/정상적으로 수신)이 없음")


def check_readme_per_query_and_target_distinguished(reporter: ValidationReporter) -> None:
    ok = (
        "검색 조합당 수집 상한" in README_TEXT
        and "전체 목표 저장 개수" in README_TEXT
        and "30" in README_TEXT
        and "300" in README_TEXT
    )
    if ok:
        reporter.pass_("README: 검색 조합당 수집 상한(30)과 전체 목표 저장 개수(300)가 구분되어 설명됨")
    else:
        reporter.fail("README에 검색 조합당 상한/전체 목표 저장 개수 구분 또는 기본값(30/300) 표기가 없음")


def check_readme_target_shortfall_possible(reporter: ValidationReporter) -> None:
    if "미달" in README_TEXT:
        reporter.pass_("README: 목표 미달 가능 문구 존재")
    else:
        reporter.fail("README에 목표 미달 가능성을 알리는 문구('미달')가 없음")


def check_readme_captcha_429_no_bypass(reporter: ValidationReporter) -> None:
    ok = "우회하지 않" in README_TEXT and "429" in README_TEXT
    if ok:
        reporter.pass_("README: CAPTCHA·429 우회 없음 정책 명시")
    else:
        reporter.fail("README에 CAPTCHA/429 우회 없음 문구가 없음")


def check_readme_zero_rows_no_file(reporter: ValidationReporter) -> None:
    ok = "0건" in README_TEXT and "만들지 않습니다" in README_TEXT
    if ok:
        reporter.pass_("README: 0건이면 Excel 파일을 만들지 않는다는 문구 존재")
    else:
        reporter.fail("README에 0건 시 파일 미생성 문구가 없음")


def check_readme_new_open_filter_unsupported(reporter: ValidationReporter) -> None:
    ok = "새로오픈" in README_TEXT and ("지원하지 않" in README_TEXT or "지원하지 않습니다" in README_TEXT)
    if ok:
        reporter.pass_("README: 새로오픈 필터 현재 미지원 명시")
    else:
        reporter.fail("README에 새로오픈 필터 미지원 문구가 없음")


def check_readme_fields_may_be_blank(reporter: ValidationReporter) -> None:
    ok = "빈칸" in README_TEXT or "빈 값" in README_TEXT
    if ok:
        reporter.pass_("README: 일부 필드가 빈칸/빈 값일 수 있다는 문구 존재")
    else:
        reporter.fail("README에 필드 공백 가능 문구가 없음")


def check_readme_no_direct_http_client(reporter: ValidationReporter) -> None:
    ok = "HTTP 클라이언트" in README_TEXT and "직접 호출" in README_TEXT
    if ok:
        reporter.pass_("README: 별도 HTTP 클라이언트 직접 호출 없음 구조 설명 존재")
    else:
        reporter.fail("README에 HTTP 클라이언트 직접 호출 없음 설명이 없음")


def check_official_product_disclaimer(reporter: ValidationReporter) -> None:
    def _has_disclaimer(text: str) -> bool:
        return "공식" in text and "제휴" in text and "아닙" in text

    ok = _has_disclaimer(README_TEXT) or _has_disclaimer(LEGAL_NOTICE_TEXT)
    if ok:
        reporter.pass_("공식 네이버 제품·제휴 제품이 아니라는 고지가 README 또는 LEGAL_NOTICE에 존재")
    else:
        reporter.fail("README/LEGAL_NOTICE 어디에도 공식·제휴 제품 아님 고지가 없음")


# ---------------------------------------------------------------------------
# 10~11. LEGAL_NOTICE.md
# ---------------------------------------------------------------------------


def check_legal_notice_current_section_no_stale_limit(reporter: ValidationReporter) -> None:
    """LEGAL_NOTICE.md는 append-only 구조라 과거 섹션(4번, 2026-06-04)의
    "10건 이내"는 역사적 기록으로 보존된다. 이 테스트는 "현재 적용 범위"를
    나타내는 최신 섹션(마지막 '## ' 섹션)에만 그 낡은 수치가 없는지 검사한다."""
    if "10건 이내" not in LEGAL_NOTICE_CURRENT_SECTION:
        reporter.pass_("LEGAL_NOTICE: 현재 적용 섹션(최신 '## ' 섹션)에 낡은 '10건 이내' 표현이 없음(과거 섹션은 역사적 기록으로 보존)")
    else:
        reporter.fail(f"LEGAL_NOTICE 최신 섹션에 '10건 이내'가 남아있음:\n{LEGAL_NOTICE_CURRENT_SECTION[:500]}")


def check_legal_notice_no_legal_guarantee_wording(reporter: ValidationReporter) -> None:
    forbidden_phrases = ["합법을 보장", "위반이 아닙니다", "법적 문제가 없습니다", "네이버가 허용했습니다"]
    found = [phrase for phrase in forbidden_phrases if phrase in LEGAL_NOTICE_TEXT]
    if not found:
        reporter.pass_("LEGAL_NOTICE: 법적 확정 보장 표현(합법을 보장/위반이 아님/법적 문제 없음/네이버 허용) 없음")
    else:
        reporter.fail(f"LEGAL_NOTICE에 금지된 법적 보장 표현이 있음: {found}")


# ---------------------------------------------------------------------------
# 12. UI 안내·정책 탭
# ---------------------------------------------------------------------------


def check_policy_tab_core_guidance_present(reporter: ValidationReporter) -> None:
    required_terms = ["수집 방식", "수집 개수", "안전 중단", "데이터 제공 범위", "이용 책임", "우회하지", "HTTP 클라이언트"]
    missing = [term for term in required_terms if term not in POLICY_TAB_SOURCE]
    if not missing:
        reporter.pass_("UI 안내·정책 탭: 수집 방식/수집 개수/안전 중단/데이터 제공 범위/이용 책임 핵심 안내 + 우회 없음/직접 호출 없음 문구 존재")
    else:
        reporter.fail(f"UI 안내·정책 탭 소스에 다음 핵심 문구가 없음: {missing}")


# ---------------------------------------------------------------------------
# 13(추가). README/LEGAL_NOTICE 금지 표현 부재
# ---------------------------------------------------------------------------


_NEGATION_MARKERS = ("하지 않", "지 않습니다", "아닙니다", "의미하지 않", "보장하지 않")


def _asserted_positively(text: str, phrase: str) -> bool:
    """phrase가 text에 등장하되, 그 직후(약 20자 이내)에 부정 표현이 없어
    "긍정 주장"으로 읽히는 경우만 True를 반환한다. "'300개 보장'을 의미하지
    않습니다"처럼 금지 표현을 인용해 명시적으로 부인하는 문장은 위반이
    아니므로 이 헬퍼로 걸러낸다(단순 substring 검사의 오탐 방지)."""
    start = 0
    while True:
        idx = text.find(phrase, start)
        if idx == -1:
            return False
        window = text[idx: idx + len(phrase) + 20]
        if not any(marker in window for marker in _NEGATION_MARKERS):
            return True
        start = idx + len(phrase)


def check_forbidden_hype_phrases_absent(reporter: ValidationReporter) -> None:
    """요청서 §3의 '피해야 할 표현' 목록이 README/LEGAL_NOTICE에 "긍정 주장"
    형태로는 없는지 확인한다(300개 보장, 탐지/차단되지 않음, CAPTCHA 해결/
    회피 등). 금지 표현을 인용하며 명시적으로 부인하는 문장(예: "'300개
    보장'을 의미하지 않습니다", "무제한 수집을... 보장하지 않습니다")은
    오탐으로 걸러진다(§_asserted_positively)."""
    forbidden_phrases = [
        "탐지되지 않습니다", "차단되지 않습니다", "무제한 수집", "300개 보장",
        "300개를 보장", "CAPTCHA를 해결", "CAPTCHA를 회피", "캡차를 해결", "캡차를 회피",
    ]
    combined = README_TEXT + "\n" + LEGAL_NOTICE_TEXT
    found = [phrase for phrase in forbidden_phrases if _asserted_positively(combined, phrase)]
    if not found:
        reporter.pass_("README/LEGAL_NOTICE: 과장·보장성 금지 표현(300개 보장/탐지·차단 안 됨/CAPTCHA 해결·회피 등)이 긍정 주장 형태로는 없음")
    else:
        reporter.fail(f"README/LEGAL_NOTICE에 금지 표현이 긍정 주장 형태로 남아있음: {found}")


def main() -> int:
    reporter = ValidationReporter()

    check_readme_network_flow_described(reporter)
    check_readme_per_query_and_target_distinguished(reporter)
    check_readme_target_shortfall_possible(reporter)
    check_readme_captcha_429_no_bypass(reporter)
    check_readme_zero_rows_no_file(reporter)
    check_readme_new_open_filter_unsupported(reporter)
    check_readme_fields_may_be_blank(reporter)
    check_readme_no_direct_http_client(reporter)
    check_official_product_disclaimer(reporter)
    check_legal_notice_current_section_no_stale_limit(reporter)
    check_legal_notice_no_legal_guarantee_wording(reporter)
    check_policy_tab_core_guidance_present(reporter)
    check_forbidden_hype_phrases_absent(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
