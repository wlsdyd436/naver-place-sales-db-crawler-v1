# 정식 출시 전 PC 단일 엔진 전환 - Stage 1 (safety 분리) 청크2.
# 예외/메시지를 분류만 하는 독립 유틸리티입니다. 이 모듈은 예외를 직접 처리하거나
# 브라우저를 닫지 않으며, CAPTCHA 우회/자동 해결을 시도하지 않습니다.
#
# 2026-07-01 CAPTCHA 감지 타이밍 진단(PROJECT_STATE.md) 결과, count()>0 또는
# is_visible() 단독 판정은 신뢰할 수 없음이 확인되어, 클릭/페이지네이션 실패
# 예외 메시지에 캡차 관련 키워드가 포함되는지로 판정하는 방식을 사용합니다.
from dataclasses import dataclass
from enum import Enum


class SafetyReason(Enum):
    CAPTCHA_OR_SECURITY_BLOCK = "captcha_or_security_block"
    TIMEOUT = "timeout"
    GENERAL_ERROR = "general_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SafetyDecision:
    """분류 결과. 실행(브라우저 종료/저장 등)은 호출자(pipeline/safety_manager)가 수행합니다."""

    reason: SafetyReason
    should_stop_safely: bool
    should_save_partial: bool
    message: str


_CAPTCHA_KEYWORDS = (
    "wtm-captcha-root",
    "captcha",
    "rcpt_desc",
    "message_text",
)

_CAPTCHA_KOREAN_PHRASES = (
    "자동화된 접근",
)


def is_captcha_or_security_message(message: str) -> bool:
    """count()>0/is_visible() 단독 판정 대신, 예외 메시지 키워드로 CAPTCHA/보안 차단 여부를 판단합니다."""
    if not message:
        return False
    lowered = message.lower()
    if any(keyword in lowered for keyword in _CAPTCHA_KEYWORDS):
        return True
    return any(phrase in message for phrase in _CAPTCHA_KOREAN_PHRASES)


def is_timeout_message(message: str) -> bool:
    if not message:
        return False
    return "timeout" in message.lower()


def classify_exception(exc) -> SafetyDecision:
    """예외(Exception) 또는 메시지(str)를 받아 SafetyDecision으로 분류합니다.

    우선순위: CAPTCHA/보안 차단 > Timeout > 일반 오류 > (메시지 없음) Unknown.
    이 함수는 판정만 하며, 실제 안전 종료/부분 저장/브라우저 종료는 수행하지 않습니다.
    """
    if exc is None:
        return SafetyDecision(
            reason=SafetyReason.UNKNOWN,
            should_stop_safely=True,
            should_save_partial=True,
            message="",
        )

    if isinstance(exc, str):
        message = exc
        type_name = ""
    else:
        message = str(exc)
        type_name = type(exc).__name__

    combined = f"{type_name} {message}".strip()

    if not combined:
        return SafetyDecision(
            reason=SafetyReason.UNKNOWN,
            should_stop_safely=True,
            should_save_partial=True,
            message=message,
        )

    if is_captcha_or_security_message(combined):
        return SafetyDecision(
            reason=SafetyReason.CAPTCHA_OR_SECURITY_BLOCK,
            should_stop_safely=True,
            should_save_partial=True,
            message=message,
        )

    if is_timeout_message(combined):
        return SafetyDecision(
            reason=SafetyReason.TIMEOUT,
            should_stop_safely=True,
            should_save_partial=True,
            message=message,
        )

    return SafetyDecision(
        reason=SafetyReason.GENERAL_ERROR,
        should_stop_safely=True,
        should_save_partial=True,
        message=message,
    )
