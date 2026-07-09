# PoC-9A(REGION-DATA-1): data/verticals_kr.json을 읽는 얇은 로더.
#
# 이 모듈은 직접 API를 호출하지 않으며, 네트워크/브라우저와 무관한 순수 파일
# 읽기 전용 로더다(src/pc/region_data.py와 동일한 패턴). 아직 PoC-9A 단계이므로
# UI(src/ui.py)나 pipeline(src/pc/pipeline.py)에 연결되지 않는다.
#
# 이 파일이 담는 것: 업종 키워드가 "정의형(defined)"인지 "umbrella(포괄)"인지
# "전문/소형(niche)"인지 구분하고, 각 유형에 맞는 세부업종/하위업종 후보를
# 조회하는 것까지만 담당한다. umbrella 키워드를 실제로 분해해 큐를 만드는
# 로직(예: build_tiered_query_queue 호출)은 이 모듈의 책임이 아니다 - 이
# 모듈은 "이 키워드를 어떻게 다뤄야 하는지"에 대한 정적 메타데이터 조회만
# 제공한다(region_data.load_region_layers가 지역 데이터만 조회하고 쿼리 생성은
# region_expander에 맡기는 것과 동일한 책임 분리).
import json
from pathlib import Path


def load_vertical_presets(path) -> dict:
    """data/verticals_kr.json 전체를 읽어 업종별 preset dict를 반환한다.

    입력: path(str 또는 Path) - verticals_kr.json 경로.
    출력: {"카페": {...}, "음식점": {...}, ...} 형태의 dict(파일 내용 그대로).

    파일이 존재하지 않으면 FileNotFoundError를 그대로 전파한다(설정 오류를
    감추지 않는다 - region_data.load_region_layers와 동일한 방침).
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_vertical_preset(presets: dict, keyword: str):
    """업종 키워드 하나의 preset을 조회한다.

    입력: presets(load_vertical_presets가 반환한 dict), keyword(예: "한식").
    출력: 해당 키워드의 preset dict(예: {"type": "defined", "subcategories": [...]})
    또는, presets에 없는 키워드면 None(예외를 던지지 않음 - 호출자가 "이
    키워드는 아직 preset이 없다"는 사실만 확인하면 되는 상황이 많으므로).
    """
    if not isinstance(presets, dict):
        return None
    return presets.get(keyword)
