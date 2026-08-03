"""ETA·홈페이지 보강·Network 종료 상태를 사용자에게 보여줄 문자열로
만든다.

입력은 UI가 이미 계산·확정한 순수 값(초 단위 숫자, orchestrator/home
enrichment 결과 dict)이다. GUI 위젯을 읽거나 쓰지 않는다. src/ui.py의
SalesDbCrawlerApp이 이 모듈의 함수가 반환한 문자열을 로그창 또는
상태바에 표시한다.
"""


def _format_eta_seconds(seconds: float) -> str:
    remaining_seconds = max(0, int(round(seconds)))
    minutes, seconds = divmod(remaining_seconds, 60)
    if minutes > 0:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"


def _home_stage_suffix(result: dict) -> str:
    """홈페이지·SNS 포함 모드의 home 보강 단계 결과를 완료 문구에 덧붙인다.
    실행되지 않았으면(기본 모드이거나 목록 자체가 차단/0건) 빈 문자열을
    반환한다."""
    attempted_anything = (
        result.get("home_success_count", 0) or result.get("home_failure_count", 0)
        or result.get("home_not_attempted_count", 0)
    )
    if not attempted_anything:
        return ""
    home_stop_reason = result.get("home_stop_reason")
    completion = " 홈페이지/SNS 보강 완료." if home_stop_reason in (None, "") else " 홈페이지/SNS 보강 부분 완료(중단)."
    success_count = result.get("home_success_count", 0)
    link_found = result.get("home_link_found_count", success_count)
    no_link = result.get("home_no_link_count", 0)
    return (
        f"{completion} 상세 처리 성공 {success_count}건(링크 발견 {link_found}건/없음 {no_link}건), "
        f"실패 {result.get('home_failure_count', 0)}건, "
        f"미시도 {result.get('home_not_attempted_count', 0)}건."
    )


def _network_stop_message(result: dict, target_count: int) -> str:
    """저장 결과까지 반영한 최종 상태 문구를 만든다(ARCH-300C WIRE-2C-1).

    우선순위: 저장 실패(export_error) > 저장할 rows 없음(exported=False,
    export_error=False) > stop_reason별 완료/부분 저장 문구. "저장했습니다"는
    실제 저장이 성공(exported=True)했을 때만 쓴다 - export 실패 시 기존
    완료 문구만 보여 성공으로 오인시키지 않기 위해 가장 먼저 검사한다.
    navigation_error_message 전체는 여기서도 노출하지 않는다(로그 전용).
    완료/부분 완료 문구에는 홈페이지·SNS 보강 결과 요약(성공/실패/미시도
    건수)을 덧붙인다(_home_stage_suffix, home_sns 모드가 아니면 빈
    문자열).
    """
    if result.get("export_error"):
        return "수집 결과를 Excel로 저장하지 못했습니다."
    if not result.get("exported"):
        return "저장할 결과가 없습니다."

    final_count = result.get("final_count", 0)
    stop_reason = result.get("stop_reason")
    stage_suffix = _home_stage_suffix(result)
    if stop_reason == "target_reached":
        return f"전체 목표 개수에 도달했습니다. {final_count}개를 저장했습니다.{stage_suffix}"
    if stop_reason == "queue_exhausted":
        if target_count and final_count < target_count:
            return f"선택한 지역 수집이 완료되었습니다. 목표에는 미달했으며 {final_count}개를 저장했습니다.{stage_suffix}"
        return f"선택한 지역 수집이 완료되었습니다. {final_count}개를 저장했습니다.{stage_suffix}"
    if stop_reason == "security_blocked":
        return f"보안 확인이 감지되어 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
    if stop_reason == "status_429":
        return f"요청 제한이 감지되어 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
    if stop_reason == "navigation_error":
        return f"브라우저 페이지 오류로 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
    if stop_reason == "user_stopped":
        return f"사용자가 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
    return f"수집이 종료되었습니다. {final_count}개를 저장했습니다. (stop_reason={stop_reason}){stage_suffix}"
