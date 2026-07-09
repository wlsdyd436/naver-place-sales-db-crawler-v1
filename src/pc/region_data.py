# PoC-6(REGION-DATA-1): data/regions_kr_sample.json을 읽는 얇은 로더.
#
# 이 모듈은 직접 API를 호출하지 않으며, 네트워크/브라우저와 무관한 순수 파일
# 읽기 전용 로더다. 아직 PoC-6 단계이므로 UI(src/ui.py)나 pipeline
# (src/pc/pipeline.py)에 연결되지 않는다.
#
# 전국 법정동/역상권 데이터 자산화(공개 출처 기반 정식 데이터셋)는 이번 PoC-6
# 범위가 아니다 - 강동구 샘플만 담은 data/regions_kr_sample.json을 읽어
# region_expander의 Tier 빌더에 넘길 입력을 만드는 것까지만 담당한다.
import json
from pathlib import Path


def load_region_layers(path, city: str, gu: str) -> dict:
    """지정한 city/gu의 법정동/역상권/세부업종 후보 목록을 JSON 파일에서 읽어온다.

    입력:
      path: regions_kr_sample.json 등 지역 데이터 JSON 파일 경로(str 또는 Path).
      city, gu: 조회할 시/도, 구/군 이름(예: "서울특별시", "강동구").

    출력: {"legal_dongs": [...], "landmarks": [...], "subcategory_keywords": [...]}
    형태의 dict. 각 값은 파일에 없으면 빈 리스트로 채워진다(예외를 던지지
    않음 - region_expander의 Tier 빌더는 빈 리스트를 넘겨받으면 스스로 빈
    쿼리 목록을 반환하도록 이미 방어되어 있으므로, 이 함수는 그 이상의 방어를
    중복 구현하지 않는다).

    파일이 존재하지 않으면 FileNotFoundError를 그대로 전파한다(호출자가 잘못된
    경로를 넘긴 것은 방어적으로 감출 상황이 아니라 즉시 드러나야 할 설정
    오류이므로). city/gu가 파일에 없으면(오타 등) 예외 없이 세 키 모두 빈
    리스트인 dict를 반환한다.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    gu_data = data.get(city, {}).get(gu, {})
    return {
        "legal_dongs": list(gu_data.get("legal_dongs", [])),
        "landmarks": list(gu_data.get("landmarks", [])),
        "subcategory_keywords": list(gu_data.get("subcategory_keywords", [])),
    }
