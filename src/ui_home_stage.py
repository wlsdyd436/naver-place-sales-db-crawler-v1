"""목록 수집(Basic/홈페이지·SNS 포함) 완료 이후 홈페이지·SNS 보강 stage를
담당한다.

입력은 목록 수집 직후의 result dict(rows/security_blocked 포함)와 순수
설정값·callable(collection_mode/home_enrichment_fn/pause_event/stop_event/
on_log/on_status/on_progress)이다. 실제 홈페이지 HTML 보강은 주입받은
home_enrichment_fn(src/collection/home_enrichment.py)이 담당하며, 이
모듈은 그 호출 여부·통계 병합·로그·진단 저장만 책임진다. GUI 위젯을
읽거나 쓰지 않는다. src/ui.py는 이 함수가 반환한 result dict를 그대로
받아 Excel export/최종 상태 처리로 넘긴다(그 두 단계는 이 모듈의 책임이
아니다).
"""
from datetime import datetime

from src.diagnostics import DEFAULT_DIAGNOSTICS_ROOT, save_json_artifact


def run_home_enrichment_stage(
    result: dict,
    *,
    collection_mode: str,
    home_enrichment_fn,
    pause_event,
    stop_event,
    on_log,
    on_status,
    on_progress,
) -> dict:
    """목록 수집 결과(result)에 홈페이지·SNS 보강 stage를 적용한다
    (ARCH-300C WIRE-2C-1이 확정한 계약을 그대로 이동 - 로직 변경 없음).

    collection_mode != "home_sns"이거나 rows가 비어 있거나 이미
    security_blocked(목록 수집 단계에서 CAPTCHA/429로 중단)면
    home_enrichment_fn을 호출하지 않고 home_* 필드를 기본값(0/None/False)
    으로만 채운 result를 반환한다.

    home_enrichment_fn이 예상 밖 예외를 던지면 이 함수는 그 예외를
    흡수하지 않고 그대로 호출자에게 전파한다(현재 동작 - 이번 이동에서
    바꾸지 않음). 이 경우 통계 병합·로그·진단 저장은 실행되지 않는다.

    result는 호출자가 넘긴 dict를 그대로 변형(in-place mutate)하고
    동일 객체를 반환한다(export_network_result처럼 복사하지 않음 -
    이동 전 _run_network_pipeline과 동일한 동작).
    """
    result["home_stop_reason"] = None
    result["home_security_blocked"] = False
    result["home_success_count"] = 0
    result["home_processed_success_count"] = 0
    result["home_link_found_count"] = 0
    result["home_no_link_count"] = 0
    result["home_retry_count"] = 0
    result["home_failure_count"] = 0
    result["home_not_attempted_count"] = 0
    rows = result.get("rows") or []
    if collection_mode == "home_sns" and rows and not result.get("security_blocked"):
        on_status(f"홈페이지/SNS 보강 준비 중... (총 {len(rows)}건)")
        on_log(f"[ui][network][home] 홈페이지/SNS 보강 시작: 대상 {len(rows)}건")
        home_result = home_enrichment_fn(
            rows,
            should_continue=lambda: not stop_event.is_set(),
            on_progress=on_progress,
            pause_event=pause_event,
            stop_event=stop_event,
        )
        result["rows"] = home_result["rows"]
        result["home_stop_reason"] = home_result["stop_reason"]
        result["home_security_blocked"] = home_result["security_blocked"]
        result["home_success_count"] = home_result["home_success_count"]
        result["home_failure_count"] = home_result["failure_count"]
        result["home_not_attempted_count"] = home_result["not_attempted_count"]
        # PAGE300-6H: home_success_count는 "상세 처리가 예외 없이 끝남"만
        # 뜻하고 링크 존재 여부와 무관하다 - 신규 통계가 없는 기존
        # home_enrichment_fn fake와도 호환되도록, 없으면 home_success_count로
        # 안전하게 대체한다(그 fake들은 "링크 발견" 개념 자체가 없으므로
        # 발견/없음을 나눌 근거가 없어 전부 "발견"으로 보는 것이 기존
        # 동작과 가장 가깝다 - 실패로 잘못 보이지 않게 함).
        result["home_processed_success_count"] = home_result.get(
            "home_processed_success_count", home_result["home_success_count"]
        )
        result["home_link_found_count"] = home_result.get(
            "home_link_found_count", home_result["home_success_count"]
        )
        result["home_no_link_count"] = home_result.get("home_no_link_count", 0)
        result["home_retry_count"] = home_result.get("home_retry_count", 0)

        # PAGE300-6G-R1: first_pass/retry_pass가 없는 fake(구 버전 테스트
        # fixture 등)와도 호환되도록 .get(..., 기본값)만 사용한다.
        on_log(
            "[ui][network][home] 보강 종료: "
            f"상세 처리 성공 {result['home_processed_success_count']}건 "
            f"(외부 링크 발견 {result['home_link_found_count']}건 / "
            f"없음 {result['home_no_link_count']}건), "
            f"실패 {result['home_failure_count']}건, "
            f"재시도 {result['home_retry_count']}회, "
            f"미시도 {result['home_not_attempted_count']}건"
        )

        final_failures = home_result.get("final_failures") or []
        total_final_failures = len(final_failures)
        for index, failure in enumerate(final_failures, start=1):
            on_log(
                f"[ui][network][home][실패 {index}/{total_final_failures}] "
                f"업체명={failure.get('name', '')} place_id={failure.get('place_id', '')} "
                f"원인={failure.get('status', '')} HTTP={failure.get('http_status')} "
                f"시도={failure.get('attempt', '')} 응답시간={failure.get('elapsed_ms', '')}ms"
            )

        diagnostics_report = home_result.get("diagnostics_report")
        if diagnostics_report is not None:
            diagnostics_filename = f"home_enrichment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            try:
                DEFAULT_DIAGNOSTICS_ROOT.mkdir(parents=True, exist_ok=True)
                artifact = save_json_artifact(
                    DEFAULT_DIAGNOSTICS_ROOT, diagnostics_filename, diagnostics_report
                )
                if artifact.success:
                    on_log(f"[ui][network][home] 실패 진단 저장: {artifact.path}")
                else:
                    on_log(f"[ui][network][home] 진단 저장 실패: {artifact.error_message}")
            except Exception as exc:
                on_log(f"[ui][network][home] 진단 저장 실패: {type(exc).__name__}: {exc}")

    return result
