import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.naver_region_policy import (  # noqa: E402
    NAVER_SIDO_ALIASES,
    OFFICIAL_EXACT,
    OUT_OF_SCOPE,
    PROVIDER_ALIAS_EXACT,
    REGION_UNVERIFIED,
    classify_region_match,
)

# 2026-07-29 Live 감사(scratchpad/legaldong_naver_region_compatibility_audit)
# 실측 그대로 재현 - 5~14번은 사용자 지시서 §7의 시나리오 번호와 동일하다.


def test_5_seoul_gangdong_cheonho_official_exact():
    result = classify_region_match(
        "서울특별시 강동구 천호동 올림픽로78길 60", "서울특별시", "강동구", "천호동"
    )
    assert result == OFFICIAL_EXACT


def test_6_sejong_jochiwon_official_exact_no_sigungu():
    result = classify_region_match(
        "세종특별자치시 조치원읍 신안리 신안새동네2길 15", "세종특별자치시", "", "조치원읍"
    )
    assert result == OFFICIAL_EXACT


def test_7_gyeonggi_suwon_jangan_official_exact_compound_sigungu():
    result = classify_region_match(
        "경기도 수원시 장안구 정자동 수성로 175", "경기도", "수원시 장안구", "정자동"
    )
    assert result == OFFICIAL_EXACT


def test_8_jeju_yeondong_official_exact():
    result = classify_region_match(
        "제주특별자치도 제주시 연동 국기로3길 2", "제주특별자치도", "제주시", "연동"
    )
    assert result == OFFICIAL_EXACT


def test_9_jeonnam_gwangju_seogu_chipyeongdong_provider_alias_exact():
    result = classify_region_match(
        "전남광주 서구 치평동 치평로 76 1층", "전남광주통합특별시", "서구", "치평동"
    )
    assert result == PROVIDER_ALIAS_EXACT


def test_10_jeonnam_gwangju_seogu_ssangchondong_out_of_scope():
    result = classify_region_match(
        "전남광주 서구 쌍촌동 운천로172번길 10", "전남광주통합특별시", "서구", "치평동"
    )
    assert result == OUT_OF_SCOPE


def test_11_jeonnam_gwangju_seogu_mareukdong_out_of_scope():
    result = classify_region_match(
        "전남광주 서구 마륵동 상무누리로 5", "전남광주통합특별시", "서구", "치평동"
    )
    assert result == OUT_OF_SCOPE


def test_12_jeonnam_gwangju_yeosu_hakdong_provider_alias_exact():
    result = classify_region_match(
        "전남광주 여수시 학동 거북선공원2길 8-4", "전남광주통합특별시", "여수시", "학동"
    )
    assert result == PROVIDER_ALIAS_EXACT


def test_13_empty_address_is_region_unverified():
    result = classify_region_match("", "서울특별시", "강동구", "천호동")
    assert result == REGION_UNVERIFIED


def test_14_business_name_leakage_ignored_only_address_field_used():
    """상호명에 "천호동"이 들어있어도 이 함수는 주소 문자열만 받으므로
    이름과는 무관하게, 주소가 실제로 성내동이면 OUT_OF_SCOPE여야 한다."""
    address_only = "서울특별시 강동구 성내동 성내로 10"
    result = classify_region_match(address_only, "서울특별시", "강동구", "천호동")
    assert result == OUT_OF_SCOPE


def test_only_realtime_audited_alias_is_registered_no_speculative_aliases():
    """§3 - 실측되지 않은 광주광역시/전라남도 등 추측 별칭은 등록하지
    않는다(증거 없이 광범위한 fuzzy match 추가 금지)."""
    assert NAVER_SIDO_ALIASES == {"전남광주통합특별시": ("전남광주",)}


def test_unregistered_sido_variant_is_region_unverified_not_out_of_scope():
    """등록되지 않은 별칭으로 sido만 다르고 sigungu/법정동이 일치하면(전혀
    다른 지역이라는 적극적 증거는 없으므로) OUT_OF_SCOPE가 아니라
    REGION_UNVERIFIED로 보수적으로 분류해야 한다(§6 정확성 우선 정책)."""
    result = classify_region_match(
        "미등록별칭 강동구 천호동 올림픽로78길 60", "서울특별시", "강동구", "천호동"
    )
    assert result == REGION_UNVERIFIED


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
