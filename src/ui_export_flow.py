"""수집이 끝난 Network row 목록의 Excel 저장 흐름을 담당한다.

입력은 순수 데이터(orchestrator 결과 dict)·경로 문자열·callable이다.
실제 Excel 파일 생성은 주입받은 excel_exporter가 담당하며, 이 모듈은
그 호출 여부·인자·성공/실패 기록만 책임진다. GUI 위젯을 읽거나 쓰지
않는다. src/ui.py는 반환된 결과 dict를 최종 Network 결과에 그대로
반영한다.
"""


def export_network_result(result: dict, output_path: str, excel_exporter, *, on_log) -> dict:
    """orchestrator 결과의 rows를 Excel로 저장하는 단일 지점(ARCH-300C WIRE-2C-1).

    저장은 이 함수 한 곳에서만, 최대 1회 발생한다 - run_collection_plan에는
    on_partial_save를 넘기지 않으므로 중간 저장과 종료 후 저장이 겹치는
    이중 저장은 구조적으로 발생하지 않는다. rows가 비어 있으면(0건) 근거
    없는 빈 Excel 파일을 남기지 않기 위해 excel_exporter를 아예 호출하지
    않는다. result는 orchestrator가 반환한 원본 dict를 그대로 변형하지
    않도록 복사해서 사용한다.
    """
    result = dict(result)
    rows = result.get("rows") or []

    if not rows:
        result.update(exported=False, export_path="", export_error=False, export_error_message="")
        on_log("[ui][network] 저장할 결과가 없어 Excel 저장을 건너뜁니다.")
        return result

    try:
        # mobile/pc 원본 인자는 Network/List 경로에 해당 소스가 없으므로 빈
        # 리스트로 전달한다 - exporter는 3시트 구조를 그대로 유지하되
        # 원본_모바일/원본_PC는 헤더만 있는 빈 시트가 된다(exporter 무수정).
        saved_path = excel_exporter(rows, [], [], output_path)
        result.update(
            exported=True, export_path=str(saved_path or output_path),
            export_error=False, export_error_message="",
        )
        on_log(f"[ui][network] Excel 저장 완료: {result['export_path']} ({len(rows)}건)")
    except Exception as exc:
        # traceback/전체 경로를 사용자 상태 라벨에 노출하지 않는다 - 로그에만
        # 짧게 남기고, 실패를 성공으로 오인하지 않도록 exported=False로 둔다.
        message = f"{type(exc).__name__}: {exc}"[:200]
        result.update(exported=False, export_path="", export_error=True, export_error_message=message)
        on_log(f"[ui][network] Excel 저장 실패: {message}")

    return result
