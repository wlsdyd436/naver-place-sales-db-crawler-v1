# Naver가 실제로 반환하는 주소 문자열을 공식 법정동 Snapshot(시도/시군구/
# 법정동)과 비교해 판정하는 전용 정책 모듈. 공식 Snapshot이나 Query 생성
# (build_legal_dong_query_plan)에는 전혀 관여하지 않는다 - Query는 항상
# 공식 명칭으로 만들고, 이 모듈은 그 결과로 Naver가 돌려준 주소 문자열만
# 사후 비교한다.
#
# 2026-07-29 scratchpad/legaldong_naver_region_compatibility_audit Live
# 감사에서 실측 확인된 별칭만 등록한다 - 광주광역시/전라남도 등 실측되지
# 않은 추측 별칭은 등록하지 않는다(§3 "증거 없이 광범위한 지역명 fuzzy
# match 추가 금지").
NAVER_SIDO_ALIASES: dict[str, tuple[str, ...]] = {
    "전남광주통합특별시": ("전남광주",),
}

OFFICIAL_EXACT = "OFFICIAL_EXACT"
PROVIDER_ALIAS_EXACT = "PROVIDER_ALIAS_EXACT"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
REGION_UNVERIFIED = "REGION_UNVERIFIED"


def classify_region_match(address: str, expected_sido: str, expected_sigungu: str, expected_dong: str) -> str:
    """Naver가 반환한 주소(address) 하나가 공식 법정동
    (expected_sido/expected_sigungu/expected_dong)과 얼마나 일치하는지
    판정한다. 상호명·업종·검색어 문자열은 입력받지 않는다 - 오직 주소
    필드만으로 판단한다(§4).

    세종처럼 시군구가 없는 지역은 expected_sigungu=""를 전달하면 시도+
    읍면동 두 조건만으로 판정한다. expected_dong=""(법정동 미선택 - 시군구
    단위 검색)이면 법정동 일치 조건 자체를 적용하지 않는다 - 이 함수는
    법정동이 선택된 Query(legal_dong 계층)에만 사용하도록 설계됐다.
    """
    address = (address or "").strip()
    if not address:
        return REGION_UNVERIFIED

    if expected_dong and expected_dong not in address:
        return OUT_OF_SCOPE

    if expected_sigungu and expected_sigungu not in address:
        return OUT_OF_SCOPE

    if address.startswith(expected_sido):
        return OFFICIAL_EXACT

    for alias in NAVER_SIDO_ALIASES.get(expected_sido, ()):
        if address.startswith(alias):
            return PROVIDER_ALIAS_EXACT

    return REGION_UNVERIFIED
