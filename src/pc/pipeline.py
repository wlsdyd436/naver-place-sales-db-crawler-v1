# 정식 출시 전 PC 단일 엔진 전환 - Stage 1 (safety 분리) 청크4 (계약 골격).
# collect_pc_full()은 실제 수집 로직을 아직 소유하지 않습니다. browser_session.py /
# list_scraper.py(향후 단계)에서 만들어질 실제 수집 함수를 collector로 주입받아 실행하고,
# 실패 시 safety 분류 + diagnostics 캡처(best-effort) + 부분 보존 반환을 담당하는
# 오케스트레이션 계약입니다. 이 모듈은 브라우저를 열거나 닫지 않고, CAPTCHA를
# 우회/자동 해결하지 않으며, Excel 저장을 직접 호출하지 않습니다.
from src.pc.config import DiagnosticConfig
from src.pc.diagnostics import (
    DEFAULT_DIAGNOSTICS_ROOT,
    capture_page_diagnostics,
    create_diagnostic_run_dir,
)
from src.pc.safety import SafetyReason, classify_exception


def collect_pc_full(
    keyword,
    limit=10,
    new_open_only=False,
    stop_event=None,
    pause_event=None,
    *,
    diagnostic_config=None,
    on_partial_save=None,
    on_security_block=None,
    collector=None,
) -> list:
    """PC 단일 엔진 수집 facade(계약 골격).

    앞 5개 위치 인자는 기존 crawl_places_pc(keyword, limit, new_open_only,
    stop_event, pause_event)와 순서·이름이 동일하여, 향후 ui.py 재배선 시
    호출 대상만 교체하면 됩니다.

    실제 수집 로직(collector)은 browser_session.py/list_scraper.py 완료 후
    주입됩니다. collector가 없으면 NotImplementedError를 발생시켜, 아직 실제
    수집 경로가 연결되지 않았음을 명시적으로 드러냅니다.

    stop_event/pause_event는 이 함수가 직접 polling하지 않고 collector에
    그대로 전달만 합니다.

    on_security_block(decision)은 CAPTCHA/보안 차단(classify_exception의
    SafetyReason.CAPTCHA_OR_SECURITY_BLOCK)으로 분류된 경우에만 best-effort로
    1회 호출된다(SAFE-1). 우회/자동 해결을 시도하지 않으며, 호출자(ui.py)가
    사용자 안내에 사용한다. 부분 보존 반환(results) 계약은 변경되지 않는다.
    """
    if diagnostic_config is None:
        diagnostic_config = DiagnosticConfig.safe_default()

    results: list = []

    if collector is None:
        raise NotImplementedError(
            "PC 단일 엔진 수집 로직 미구현 - S2/S3 완료 후 연결 예정"
        )

    try:
        collector(keyword, limit, new_open_only, stop_event, pause_event, results)
    except Exception as exc:
        decision = classify_exception(exc)
        _try_capture_diagnostics(exc, decision, diagnostic_config, keyword)
        _try_partial_save(on_partial_save, results)
        _try_notify_security_block(on_security_block, decision)
        return results

    return results


def _try_capture_diagnostics(exc, decision, diagnostic_config, keyword) -> None:
    """진단 산출물 저장을 best-effort로 시도합니다. 실패해도 원래 흐름을 깨지 않습니다."""
    if not diagnostic_config.capture_artifacts:
        return
    page = getattr(exc, "page", None)
    if page is None:
        return
    try:
        run_dir = create_diagnostic_run_dir(
            DEFAULT_DIAGNOSTICS_ROOT, f"{keyword}_{decision.reason.value}"
        )
        capture_page_diagnostics(
            page, run_dir, label=keyword, exception=exc, safety_decision=decision
        )
    except Exception:
        # 진단 저장 실패가 부분 보존 반환 흐름을 깨서는 안 된다.
        pass


def _try_partial_save(on_partial_save, results) -> None:
    """부분 저장 콜백을 best-effort로 시도합니다. 실패해도 원래 흐름을 깨지 않습니다."""
    if on_partial_save is None:
        return
    try:
        on_partial_save(list(results))
    except Exception:
        # 콜백 실패가 부분 보존 반환 흐름을 깨서는 안 된다.
        pass


def _try_notify_security_block(on_security_block, decision) -> None:
    """CAPTCHA/보안 차단 감지를 best-effort로 호출자에게 알립니다.

    콜백은 CAPTCHA/보안 차단으로 분류된 경우에만 호출하며, 실패해도 부분 보존
    반환 흐름을 깨서는 안 된다.
    """
    if on_security_block is None:
        return
    if decision.reason != SafetyReason.CAPTCHA_OR_SECURITY_BLOCK:
        return
    try:
        on_security_block(decision)
    except Exception:
        pass
