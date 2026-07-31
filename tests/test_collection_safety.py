from pathlib import Path
import sys


# Stage 1 청크2: src/collection/safety.py 분류 로직 검증용 standalone 스크립트입니다.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.collection.safety import (
    SafetyReason,
    classify_exception,
    is_captcha_or_security_message,
    is_timeout_message,
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


def check_wtm_captcha_root_keyword(reporter: ValidationReporter) -> None:
    message = (
        '<div id="wtm-captcha-root">보안문자 확인이 필요합니다</div> subtree intercepts pointer events'
    )
    decision = classify_exception(message)
    if decision.reason == SafetyReason.CAPTCHA_OR_SECURITY_BLOCK:
        reporter.pass_("wtm-captcha-root 포함 메시지 -> CAPTCHA/보안 차단 분류")
    else:
        reporter.fail(f"wtm-captcha-root 메시지가 잘못 분류됨: {decision.reason}")


def check_captcha_keyword(reporter: ValidationReporter) -> None:
    decision = classify_exception("element intercepted by captcha overlay")
    if decision.reason == SafetyReason.CAPTCHA_OR_SECURITY_BLOCK:
        reporter.pass_("captcha 포함 메시지 -> CAPTCHA/보안 차단 분류")
    else:
        reporter.fail(f"captcha 메시지가 잘못 분류됨: {decision.reason}")


def check_timeout_error_only(reporter: ValidationReporter) -> None:
    exc = TimeoutError("Timeout 3000ms exceeded.")
    decision = classify_exception(exc)
    if decision.reason == SafetyReason.TIMEOUT:
        reporter.pass_("TimeoutError만 포함 -> timeout 분류")
    else:
        reporter.fail(f"TimeoutError만 있는데 잘못 분류됨: {decision.reason}")


def check_captcha_and_timeout_together(reporter: ValidationReporter) -> None:
    exc = TimeoutError(
        'Locator.click: Timeout 3000ms exceeded.\n'
        '<div id="wtm-captcha-root">...</div> subtree intercepts pointer events'
    )
    decision = classify_exception(exc)
    if decision.reason == SafetyReason.CAPTCHA_OR_SECURITY_BLOCK:
        reporter.pass_("CAPTCHA 키워드 + TimeoutError 동시 포함 -> CAPTCHA 우선 분류")
    else:
        reporter.fail(f"CAPTCHA+Timeout 동시 포함인데 우선순위가 잘못됨: {decision.reason}")


def check_general_value_error(reporter: ValidationReporter) -> None:
    decision = classify_exception(ValueError("잘못된 입력값입니다"))
    if decision.reason == SafetyReason.GENERAL_ERROR:
        reporter.pass_("일반 ValueError -> 일반 오류(GENERAL_ERROR) 분류")
    else:
        reporter.fail(f"일반 ValueError가 잘못 분류됨: {decision.reason}")


def check_empty_and_none_input(reporter: ValidationReporter) -> None:
    empty_decision = classify_exception("")
    none_decision = classify_exception(None)
    if (
        empty_decision.reason == SafetyReason.UNKNOWN
        and none_decision.reason == SafetyReason.UNKNOWN
    ):
        reporter.pass_("빈 문자열/None 입력 -> UNKNOWN으로 안전하게 분류")
    else:
        reporter.fail(
            f"빈 입력 분류가 예상과 다름: empty={empty_decision.reason}, none={none_decision.reason}"
        )


def check_captcha_decision_flags(reporter: ValidationReporter) -> None:
    decision = classify_exception("captcha detected on page")
    if decision.should_stop_safely is True and decision.should_save_partial is True:
        reporter.pass_("CAPTCHA 분류 -> should_stop_safely=True, should_save_partial=True")
    else:
        reporter.fail(
            f"CAPTCHA 분류의 플래그가 예상과 다름: "
            f"stop={decision.should_stop_safely}, save={decision.should_save_partial}"
        )


def check_timeout_decision_flags(reporter: ValidationReporter) -> None:
    # 설계 결정: 이 모듈은 list/detail 단계 컨텍스트를 모르는 순수 메시지 분류기이므로
    # timeout도 기본적으로 안전 종료 + 부분 저장을 True로 둔다. 상세페이지 개별 실패를
    # skip 처리해야 하는 경우(§8 E표의 detail_timeout)는 단계 정보를 아는 상위
    # pipeline/safety_manager가 이 분류 결과를 받아 별도로 override한다.
    decision = classify_exception(TimeoutError("Timeout 5000ms exceeded."))
    if decision.should_stop_safely is True and decision.should_save_partial is True:
        reporter.pass_(
            "timeout 분류 -> should_stop_safely=True, should_save_partial=True "
            "(단계별 override는 상위 호출자 책임으로 설계)"
        )
    else:
        reporter.fail(
            f"timeout 분류의 플래그가 예상과 다름: "
            f"stop={decision.should_stop_safely}, save={decision.should_save_partial}"
        )


def check_helper_functions_directly(reporter: ValidationReporter) -> None:
    ok = (
        is_captcha_or_security_message("message_text 확인 필요") is True
        and is_captcha_or_security_message("rcpt_desc 안내") is True
        and is_captcha_or_security_message("평범한 문구") is False
        and is_timeout_message("Timeout 3000ms exceeded") is True
        and is_timeout_message("평범한 문구") is False
    )
    if ok:
        reporter.pass_("is_captcha_or_security_message / is_timeout_message 헬퍼 단독 동작 확인")
    else:
        reporter.fail("헬퍼 함수 단독 호출 결과가 예상과 다름")


def main() -> int:
    reporter = ValidationReporter()

    check_wtm_captcha_root_keyword(reporter)
    check_captcha_keyword(reporter)
    check_timeout_error_only(reporter)
    check_captcha_and_timeout_together(reporter)
    check_general_value_error(reporter)
    check_empty_and_none_input(reporter)
    check_captcha_decision_flags(reporter)
    check_timeout_decision_flags(reporter)
    check_helper_functions_directly(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


def test_standalone_suite():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
