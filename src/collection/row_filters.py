# Apollo 목록에서 변환된 Place row의 채택 여부를 판정하는 순수 정책 모듈.
#
# 입력: place_mapper._map_item_to_row가 만든 row(dict) 목록과, 판정에 필요한
# job(dict, 지역/새로오픈 조건) 또는 리뷰 최소·최대 범위. 출력: (채택된
# valid_rows, 제외된 rejected_rows) tuple과, 리뷰 필터의 경우 review_filter_stats
# 집계 dict. 지역 Exact 판정은 src/region.naver_region_policy를 그대로
# 재사용한다(재구현 없음). 이 모듈은 Browser·Apollo response 관찰·Session
# 생명주기·UI·파일 I/O를 전혀 수행하지 않는다 - row(dict)만 받아 row(dict)만
# 반환하는 순수 함수만 담는다.
from src.region.naver_region_policy import (
    OFFICIAL_EXACT,
    OUT_OF_SCOPE,
    PROVIDER_ALIAS_EXACT,
    REGION_UNVERIFIED,
    classify_region_match,
)

_REGION_REJECTION_REASON = {
    OUT_OF_SCOPE: "선택 법정동/시군구 범위를 벗어난 주소",
    REGION_UNVERIFIED: "주소로 공식 지역과의 일치를 확인할 수 없음(주소 공란 또는 인식되지 않은 시도 표기)",
}


def _split_region_valid_rows(rows: list, job: dict) -> tuple:
    """법정동이 선택된 Query(source_layer="legal_dong")에만 지역 Exact
    필터(naver_region_policy.classify_region_match)를 적용해 (유효 rows,
    거부 진단 목록)을 반환한다. 시군구 단위 검색(법정동 미선택)/보조
    역·상권·세부업종 Query는 비교할 특정 법정동이 없으므로 필터를 적용하지
    않고 그대로 통과시킨다(기존 동작 유지) - §4 요구사항이 "법정동 Query"로
    범위를 한정하고 있기 때문이다.

    이 필터는 per_query_limit 도달 판정보다 앞에서 호출돼야 한다(호출자가
    이 함수의 반환값 중 valid_rows만 unique_rows에 누적하고 카운트한다) -
    OUT_OF_SCOPE/REGION_UNVERIFIED row가 상한을 소비하면 안 된다는 요구사항을
    만족한다."""
    if job.get("source_layer") != "legal_dong" or not job.get("source_subregion"):
        return rows, []

    expected_sido = job.get("source_city") or ""
    expected_sigungu = job.get("source_district") or ""
    expected_dong = job.get("source_subregion") or ""

    valid_rows = []
    rejected = []
    for row in rows:
        address = row.get("주소") or row.get("roadAddress") or ""
        classification = classify_region_match(address, expected_sido, expected_sigungu, expected_dong)
        if classification in (OFFICIAL_EXACT, PROVIDER_ALIAS_EXACT):
            valid_rows.append(row)
        else:
            rejected.append({
                "source_query": row.get("source_query"),
                "업체명": row.get("업체명"),
                "place_id": row.get("place_id"),
                "판정_상태": classification,
                "거부_이유": _REGION_REJECTION_REASON.get(classification, classification),
                "주소": address,
                "기대_시도": expected_sido,
                "기대_시군구": expected_sigungu,
                "기대_법정동": expected_dong,
            })
    return valid_rows, rejected


_NEW_OPENING_REJECTION_REASON = "새로오픈 확인되지 않음(false/null/누락)"


def _split_new_opening_valid_rows(rows: list) -> tuple:
    """job["new_opening_only"]=True인 Query에서 newOpening이 명시적으로
    true인 row만 유효로 남긴다(§6) - false/null/필드 누락은 rejected_rows로
    분리해 per_query_limit을 소비하지 않게 한다. row의 "새로오픈여부"는
    이미 place_mapper._resolve_new_open_tristate가
    True->"O"/False->"X"/미확인->""로 매핑해둔 값이므로 "O"만 통과시킨다
    (추측으로 false/null을 새로오픈으로 저장하지 않는다)."""
    valid_rows = []
    rejected = []
    for row in rows:
        if row.get("새로오픈여부") == "O":
            valid_rows.append(row)
        else:
            rejected.append({
                "source_query": row.get("source_query"),
                "업체명": row.get("업체명"),
                "place_id": row.get("place_id"),
                "판정_상태": "NOT_NEW_OPENING",
                "거부_이유": _NEW_OPENING_REJECTION_REASON,
                "주소": row.get("주소"),
            })
    return valid_rows, rejected


_REVIEW_BELOW_MIN_REASON = "총리뷰수가 최소값 미만"
_REVIEW_ABOVE_MAX_REASON = "총리뷰수가 최대값 초과"
_REVIEW_UNKNOWN_REASON = "총리뷰수를 확인할 수 없음(빈 값/파싱 불가)"


def _parse_review_count(value) -> int | None:
    """row["총리뷰수"](정수 또는 숫자 문자열)를 int로 변환한다. 비어있거나
    숫자로 해석할 수 없으면 None(REVIEW_UNKNOWN 처리 대상)을 반환한다."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_review_valid_rows(rows: list, review_min: int | None, review_max: int | None) -> tuple:
    """review_min/review_max(둘 중 하나라도 설정된 경우에만 호출) 기준으로
    row["총리뷰수"]가 범위 안인 row만 유효로 남긴다(§4 - 총리뷰수를 기준
    필드로 사용하기로 확정, scratchpad/network_controls_fix/review_filter_contract_audit.md).
    _split_region_valid_rows/_split_new_opening_valid_rows와 동일하게
    per_query_limit 판정보다 먼저 호출돼야 한다 - 제외된 row가 상한을
    소비하지 않게 하기 위함이다. 총리뷰수가 비어있거나 파싱 불가하면
    범위를 판정할 수 없으므로 REVIEW_UNKNOWN으로 분류해 제외한다(레거시의
    "빈 값=0으로 취급" 대신, 실제로 확인 불가능하다는 사실을 진단에 남긴다)."""
    valid_rows = []
    rejected = []
    for row in rows:
        review_count = _parse_review_count(row.get("총리뷰수"))
        if review_count is None:
            status, reason = "REVIEW_UNKNOWN", _REVIEW_UNKNOWN_REASON
        elif review_min is not None and review_count < review_min:
            status, reason = "REVIEW_BELOW_MIN", _REVIEW_BELOW_MIN_REASON
        elif review_max is not None and review_count > review_max:
            status, reason = "REVIEW_ABOVE_MAX", _REVIEW_ABOVE_MAX_REASON
        else:
            status, reason = None, None
        if status is None:
            valid_rows.append(row)
        else:
            rejected.append({
                "source_query": row.get("source_query"),
                "업체명": row.get("업체명"),
                "place_id": row.get("place_id"),
                "판정_상태": status,
                "거부_이유": reason,
                "주소": row.get("주소"),
            })
    return valid_rows, rejected


def _review_filter_stats(candidate_count: int, rejected: list) -> dict:
    """_split_review_valid_rows의 rejected 목록에서 §8 진단 카운터를 만든다."""
    return {
        "candidate": candidate_count,
        "accepted": candidate_count - len(rejected),
        "rejected_by_min": sum(1 for r in rejected if r["판정_상태"] == "REVIEW_BELOW_MIN"),
        "rejected_by_max": sum(1 for r in rejected if r["판정_상태"] == "REVIEW_ABOVE_MAX"),
        "unknown": sum(1 for r in rejected if r["판정_상태"] == "REVIEW_UNKNOWN"),
    }


def _merge_review_filter_stats(a: dict, b: dict) -> dict:
    return {key: a.get(key, 0) + b.get(key, 0) for key in ("candidate", "accepted", "rejected_by_min", "rejected_by_max", "unknown")}
