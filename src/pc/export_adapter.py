# 정식 출시 전 PC 단일 엔진 전환 - Stage 3C (Export 연결) 내부 어댑터.
#
# collect_pc_full()/build_full_collector()가 만든 row(dict)를 기존 exporter의
# 통합_결과 시트로 직결 저장하는 얇은 어댑터다. 이 모듈은 ui.py 등 기존 실행 경로에
# 연결되지 않으며(Stage 3D에서 별도 승인 후 배선), pc_crawler.py를 대체하지 않는다.
#
# parse_places 우회(의도):
#   list_scraper._build_row가 이미 최종 컬럼 키(업체명/업종/.../수집일)와 Stage 3B
#   가산 필드(대표전화/플레이스 URL/홈페이지/인스타/블로그)를 갖춘 row를 만들고,
#   dedup(seen)과 주소 정제까지 수행한다. 반면 parser.parse_places는 자신의 컬럼
#   집합으로만 투영해 홈페이지/인스타/블로그/place_id를 삭제하므로, 이 경로에서는
#   parse_places를 거치지 않고 exporter로 직결한다. place_id는 row에는 남지만
#   exporter.MERGED_COLUMNS에 없으므로 Excel에는 노출되지 않는다(내부 식별자).
from src.exporter import export_places_to_excel


def export_full_collection(rows, output_path, *, mobile_data=None, pc_data=None) -> str:
    """PC full 엔진 결과 rows를 통합_결과 시트로 저장하고 저장 경로를 반환한다.

    rows는 통합_결과의 merged_data로 직결된다(exporter가 MERGED_COLUMNS로 투영).
    mobile_data/pc_data는 원본 시트용으로, 이 어댑터 단계에서는 기본 빈 리스트다
    (원본 시트 구성은 Stage 3D 이후 UI 배선에서 결정).
    """
    return export_places_to_excel(
        list(rows or []),
        list(mobile_data or []),
        list(pc_data or []),
        output_path,
    )
