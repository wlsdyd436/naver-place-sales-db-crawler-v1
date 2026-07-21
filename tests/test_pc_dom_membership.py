from pathlib import Path
import sys


# PAGE300-DOM-1: src/pc/network_list_scraper.py에 추가된 DOM-first membership
# 순수 함수(정규화/매칭/병합/시그니처/dedup)를 검증하는 standalone 스크립트
# (실제 Playwright/브라우저 없음, dict/list fixture만 사용).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.exporter import MERGED_COLUMNS
from src.pc.network_list_scraper import (
    apollo_key_exists_for_id,
    build_entity_index,
    compute_page_signature,
    dedup_key_for_membership_row,
    dedup_membership_rows,
    extract_place_id_from_url,
    is_skeleton_dom_row,
    merge_dom_row_fields,
    normalize_dom_row,
    normalize_place_url,
    overall_row_confidence,
    page_transition_confirmed,
    resolve_dom_identifier,
    resolve_match,
    summarize_membership_diagnostics,
    to_common_entity,
    trim_membership_rows_to_target,
)


class ValidationReporter:
    def __init__(self):
        self.pass_count = 0
        self.fail_count = 0
        self.warn_count = 0

    def pass_(self, message: str) -> None:
        self.pass_count += 1
        print(f"[PASS] {message}")

    def fail(self, message: str) -> None:
        self.fail_count += 1
        print(f"[FAIL] {message}")

    def summary(self) -> None:
        final = "FAIL" if self.fail_count else "PASS"
        print("====================")
        print("검증 요약")
        print(f"PASS: {self.pass_count}")
        print(f"FAIL: {self.fail_count}")
        print(f"WARN: {self.warn_count}")
        print(f"FINAL: {final}")
        print("====================")


def _network_index(rows):
    common = [
        to_common_entity(
            row,
            id_key="place_id",
            name_key="업체명",
            category_key="업종",
            address_key="주소",
            url_key="플레이스 URL",
        )
        for row in rows
    ]
    return build_entity_index(common)


def _apollo_index(entities):
    common = [
        to_common_entity(
            entity, id_key="place_id", name_key="name", category_key="category", address_key="address"
        )
        for entity in entities
    ]
    return build_entity_index(common)


# ---------------------------------------------------------------------------
# 1. extract_place_id_from_url / normalize_place_url
# ---------------------------------------------------------------------------


def check_extract_place_id_named_and_generic_segments(reporter: ValidationReporter) -> None:
    a = extract_place_id_from_url("https://pcmap.place.naver.com/restaurant/1571880529/home")
    b = extract_place_id_from_url("https://pcmap.place.naver.com/place/2014880028/home?query=x")
    c = extract_place_id_from_url("")
    if a == "1571880529" and b == "2014880028" and c == "":
        reporter.pass_("extract_place_id_from_url: restaurant/place 세그먼트, 빈 URL 모두 정상")
    else:
        reporter.fail(f"extract_place_id_from_url 결과 이상: a={a} b={b} c={c}")


def check_normalize_place_url_strips_query_and_slash(reporter: ValidationReporter) -> None:
    result = normalize_place_url("https://pcmap.place.naver.com/restaurant/123/home/?query=1#frag")
    if result == "https://pcmap.place.naver.com/restaurant/123/home":
        reporter.pass_("normalize_place_url: query/fragment/trailing slash 제거")
    else:
        reporter.fail(f"normalize_place_url 결과 이상: {result}")


# ---------------------------------------------------------------------------
# 2. normalize_dom_row / is_skeleton_dom_row
# ---------------------------------------------------------------------------


def check_normalize_dom_row_fills_place_id_from_href_fallback(reporter: ValidationReporter) -> None:
    """identifier_candidates(Fiber 기반 후보)가 전혀 없을 때만 href 파싱이
    최후 fallback으로 place_id를 채운다(PAGE300-DOM-2 - HREF_ID)."""
    raw = {
        "dom_index": 0,
        "name": "  카페 A  ",
        "category": "카페",
        "raw_text": "카페 A카페\n리뷰 10",
        "place_url": "",
        "anchor_hrefs": ["/restaurant/551111/home", "#"],
        "data_attributes": {"data-id": "551111"},
    }
    row = normalize_dom_row(raw, page_number=1)
    ok = (
        row["normalized_name"] == "카페 A"
        and row["place_id"] == "551111"
        and row["identifier_method"] == "HREF_ID"
        and row["identifier_validated"] is True
        and row["place_url"] == "/restaurant/551111/home"
        and row["page_number"] == 1
    )
    if ok:
        reporter.pass_("normalize_dom_row: identifier_candidates 없으면 anchor href로 HREF_ID fallback")
    else:
        reporter.fail(f"normalize_dom_row 결과 이상: {row}")


def check_skeleton_row_excluded(reporter: ValidationReporter) -> None:
    empty_row = normalize_dom_row({"dom_index": 1, "name": "", "raw_text": ""}, page_number=1)
    named_row = normalize_dom_row({"dom_index": 2, "name": "카페 B", "raw_text": "카페 B"}, page_number=1)
    if is_skeleton_dom_row(empty_row) and not is_skeleton_dom_row(named_row):
        reporter.pass_("is_skeleton_dom_row: 업체명 없는 row만 skeleton으로 판정")
    else:
        reporter.fail("is_skeleton_dom_row 판정 이상")


# ---------------------------------------------------------------------------
# 3. resolve_match 6단계 우선순위
# ---------------------------------------------------------------------------


def check_match_exact_id(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row(
        {"name": "카페 A", "category": "카페", "identifier_candidates": {"fast_item_id": "100000001"}},
        page_number=1,
    )
    index = _network_index([{"place_id": "100000001", "업체명": "카페 A", "업종": "카페", "주소": "서울시 강동구 x동"}])
    result = resolve_match(dom_row, index)
    if result["confidence"] == "EXACT_ID" and result["row"]["place_id"] == "100000001":
        reporter.pass_("resolve_match: place_id 일치 -> EXACT_ID")
    else:
        reporter.fail(f"EXACT_ID 매칭 실패: {result}")


def check_match_exact_url(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row({"name": "카페 A", "category": "카페", "place_url": "/restaurant/222/home"}, page_number=1)
    index = _network_index([{"place_id": "", "업체명": "카페 A", "업종": "카페", "플레이스 URL": "/restaurant/222/home"}])
    result = resolve_match(dom_row, index)
    if result["confidence"] == "EXACT_URL":
        reporter.pass_("resolve_match: place_id 없어도 place_url 일치 -> EXACT_URL")
    else:
        reporter.fail(f"EXACT_URL 매칭 실패: {result}")


def check_match_strong_composite_address(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row(
        {"name": "카페 A", "category": "카페", "address_text": "서울특별시 강동구 천호동"}, page_number=1
    )
    index = _apollo_index([{"place_id": "", "name": "카페 A", "category": "카페", "address": "서울특별시 강동구 천호동"}])
    result = resolve_match(dom_row, index)
    if result["confidence"] == "STRONG_COMPOSITE":
        reporter.pass_("resolve_match: (이름,업종,주소) 일치 -> STRONG_COMPOSITE")
    else:
        reporter.fail(f"STRONG_COMPOSITE 매칭 실패: {result}")


def check_match_name_category_only_is_ambiguous(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row({"name": "카페 A", "category": "카페"}, page_number=1)
    index = _network_index([{"place_id": "", "업체명": "카페 A", "업종": "카페"}])
    result = resolve_match(dom_row, index)
    if result["confidence"] == "AMBIGUOUS" and result["row"] is None:
        reporter.pass_("resolve_match: 이름+업종만 일치하면 후보 1건이어도 AMBIGUOUS로 강등(임의 채택 금지)")
    else:
        reporter.fail(f"이름+업종 단독 매칭이 잘못 확정됨: {result}")


def check_match_multiple_candidates_ambiguous(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row(
        {"name": "카페 A", "category": "카페", "identifier_candidates": {"fast_item_id": "999999"}},
        page_number=1,
    )
    index = _network_index(
        [
            {"place_id": "999999", "업체명": "카페 A1"},
            {"place_id": "999999", "업체명": "카페 A2"},
        ]
    )
    result = resolve_match(dom_row, index)
    if result["confidence"] == "AMBIGUOUS":
        reporter.pass_("resolve_match: 같은 place_id 후보 2건 이상 -> AMBIGUOUS(더 느슨한 단계로 안 내려감)")
    else:
        reporter.fail(f"복수 후보 처리 이상: {result}")


def check_match_unmatched(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row({"name": "카페 Z", "category": "카페"}, page_number=1)
    index = _network_index([{"place_id": "1", "업체명": "카페 A", "업종": "카페"}])
    result = resolve_match(dom_row, index)
    if result["confidence"] == "UNMATCHED":
        reporter.pass_("resolve_match: 후보 자체가 없으면 UNMATCHED")
    else:
        reporter.fail(f"UNMATCHED 판정 이상: {result}")


# ---------------------------------------------------------------------------
# 4. merge_dom_row_fields 3가지 병합 조합 + enrichment 실패 시 DOM 유지
# ---------------------------------------------------------------------------


def check_merge_dom_network_only(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row({"name": "카페 A", "category": "카페(DOM)"}, page_number=1)
    network_result = {
        "row": {"업종": "카페(Network)", "리뷰수": "10", "주소": "서울 강동구", "플레이스 URL": "/restaurant/1/home"},
        "confidence": "EXACT_ID",
    }
    apollo_result = {"row": None, "confidence": "UNMATCHED"}
    row = merge_dom_row_fields(dom_row, network_result, apollo_result, "2026-07-21")
    ok = row["업체명"] == "카페 A" and row["업종"] == "카페(Network)" and row["리뷰수"] == "10"
    if ok:
        reporter.pass_("merge_dom_row_fields: DOM+Network only 조합, Network 값이 업종/리뷰수 우선 채택")
    else:
        reporter.fail(f"DOM+Network only 병합 이상: {row}")


def check_merge_dom_apollo_only(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row({"name": "카페 B", "category": "카페(DOM)"}, page_number=1)
    network_result = {"row": None, "confidence": "UNMATCHED"}
    apollo_result = {"row": {"category": "카페(Apollo)", "address": "서울 강동구 천호동"}, "confidence": "STRONG_COMPOSITE"}
    row = merge_dom_row_fields(dom_row, network_result, apollo_result, "2026-07-21")
    ok = row["업종"] == "카페(Apollo)" and row["주소"] == "서울 강동구 천호동"
    if ok:
        reporter.pass_("merge_dom_row_fields: DOM+Apollo only 조합, Apollo 값으로 업종/주소 보강")
    else:
        reporter.fail(f"DOM+Apollo only 병합 이상: {row}")


def check_merge_dom_network_apollo_network_wins(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row({"name": "카페 C", "category": "카페(DOM)"}, page_number=1)
    network_result = {"row": {"업종": "카페(Network)"}, "confidence": "EXACT_ID"}
    apollo_result = {"row": {"category": "카페(Apollo)"}, "confidence": "STRONG_COMPOSITE"}
    row = merge_dom_row_fields(dom_row, network_result, apollo_result, "2026-07-21")
    if row["업종"] == "카페(Network)":
        reporter.pass_("merge_dom_row_fields: DOM+Network+Apollo 동시 존재 시 Network가 우선")
    else:
        reporter.fail(f"Network 우선순위가 지켜지지 않음: {row}")


def check_merge_enrichment_failed_keeps_dom_row(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row(
        {"name": "카페 D", "category": "카페", "raw_text": "카페 D카페\n리뷰 42"}, page_number=1
    )
    network_result = {"row": None, "confidence": "UNMATCHED"}
    apollo_result = {"row": None, "confidence": "UNMATCHED"}
    row = merge_dom_row_fields(dom_row, network_result, apollo_result, "2026-07-21")
    ok = row["업체명"] == "카페 D" and row["업종"] == "카페" and row["리뷰수"] == "42" and row["대표전화"] == ""
    if ok:
        reporter.pass_("merge_dom_row_fields: enrichment 실패해도 DOM/raw_text 기반 값 유지, row 삭제 없음")
    else:
        reporter.fail(f"enrichment 실패 row 처리 이상: {row}")


def check_merge_place_url_prefers_dom_anchor(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row(
        {"name": "카페 E", "category": "카페", "anchor_hrefs": ["/restaurant/555/home"]}, page_number=1
    )
    network_result = {"row": {"place_id": "555", "플레이스 URL": "https://pcmap.place.naver.com/place/555/home"}, "confidence": "EXACT_ID"}
    apollo_result = {"row": None, "confidence": "UNMATCHED"}
    row = merge_dom_row_fields(dom_row, network_result, apollo_result, "2026-07-21")
    if row["플레이스 URL"] == "/restaurant/555/home":
        reporter.pass_("merge_dom_row_fields: DOM anchor href를 network 구성 fallback(/place/{id}/home)보다 우선 채택")
    else:
        reporter.fail(f"플레이스 URL 우선순위 이상: {row}")


# ---------------------------------------------------------------------------
# 5. dedup: place_id 우선, 업체명 단독 금지, 동일 이름 다른 지점 유지
# ---------------------------------------------------------------------------


def check_dedup_prefers_place_id_over_name(reporter: ValidationReporter) -> None:
    row_a = {"업체명": "카페 A", "업종": "카페", "주소": "", "place_id": "1", "플레이스 URL": ""}
    row_a_dup = {"업체명": "카페 A", "업종": "카페", "주소": "", "place_id": "1", "플레이스 URL": ""}
    seen: set = set()
    unique = dedup_membership_rows([row_a, row_a_dup], seen)
    if len(unique) == 1:
        reporter.pass_("dedup_membership_rows: 동일 place_id는 중복 제거")
    else:
        reporter.fail(f"place_id 중복 제거 실패: {len(unique)}건")


def check_dedup_same_name_different_branch_kept(reporter: ValidationReporter) -> None:
    row_1 = {"업체명": "스타벅스", "업종": "카페", "주소": "서울 강동구 천호동 1", "place_id": "101", "플레이스 URL": ""}
    row_2 = {"업체명": "스타벅스", "업종": "카페", "주소": "서울 강동구 천호동 2", "place_id": "102", "플레이스 URL": ""}
    seen: set = set()
    unique = dedup_membership_rows([row_1, row_2], seen)
    if len(unique) == 2:
        reporter.pass_("dedup_membership_rows: 업체명만 같은 서로 다른 지점(place_id 다름)은 둘 다 유지")
    else:
        reporter.fail(f"동일 이름 다른 지점이 잘못 병합됨: {len(unique)}건")


def check_dedup_key_never_name_only(reporter: ValidationReporter) -> None:
    row = {"업체명": "카페 X", "업종": "", "주소": "", "place_id": "", "플레이스 URL": "", "_dedup_raw_text": ""}
    key = dedup_key_for_membership_row(row)
    if key.startswith("nameonly:") and "source_page" not in key:
        reporter.pass_("dedup_key_for_membership_row: 모든 근거가 없을 때도 업체명 단독 키가 아니라 row별 고유 키를 만듦")
    else:
        reporter.fail(f"dedup key가 업체명 단독처럼 보임: {key}")


# ---------------------------------------------------------------------------
# 6. page signature / 전환 판정
# ---------------------------------------------------------------------------


def check_signature_changes_with_content(reporter: ValidationReporter) -> None:
    rows_a = [{"normalized_name": f"업체{i}"} for i in range(10)]
    rows_b = [{"normalized_name": f"업체{i}"} for i in range(10)]
    rows_c = [{"normalized_name": f"다른업체{i}"} for i in range(10)]
    sig_a = compute_page_signature(rows_a)
    sig_b = compute_page_signature(rows_b)
    sig_c = compute_page_signature(rows_c)
    if sig_a["top10_hash"] == sig_b["top10_hash"] and sig_a["top10_hash"] != sig_c["top10_hash"]:
        reporter.pass_("compute_page_signature: 동일 내용은 같은 해시, 다른 내용은 다른 해시")
    else:
        reporter.fail(f"signature 계산 이상: a={sig_a['top10_hash']} b={sig_b['top10_hash']} c={sig_c['top10_hash']}")


def check_transition_requires_all_three_conditions(reporter: ValidationReporter) -> None:
    prev_sig = compute_page_signature([{"normalized_name": "업체A"}])
    same_sig = compute_page_signature([{"normalized_name": "업체A"}])
    new_sig = compute_page_signature([{"normalized_name": "업체B"}])

    wrong_page = page_transition_confirmed(2, 1, True, prev_sig, new_sig)
    not_active = page_transition_confirmed(2, 2, False, prev_sig, new_sig)
    signature_unchanged = page_transition_confirmed(2, 2, True, prev_sig, same_sig)
    fully_confirmed = page_transition_confirmed(2, 2, True, prev_sig, new_sig)

    if not wrong_page and not not_active and not signature_unchanged and fully_confirmed:
        reporter.pass_("page_transition_confirmed: expected_page/active/signature 변화 3조건 모두 필요")
    else:
        reporter.fail(
            f"전환 판정 이상: wrong_page={wrong_page} not_active={not_active} "
            f"signature_unchanged={signature_unchanged} fully_confirmed={fully_confirmed}"
        )


# ---------------------------------------------------------------------------
# 7. 진단 카운터 / trim / Excel 컬럼
# ---------------------------------------------------------------------------


def check_diagnostics_counts_match(reporter: ValidationReporter) -> None:
    match_results = [
        {"overall": "EXACT_ID"},
        {"overall": "EXACT_ID"},
        {"overall": "EXACT_URL"},
        {"overall": "STRONG_COMPOSITE"},
        {"overall": "AMBIGUOUS"},
        {"overall": "UNMATCHED"},
    ]
    summary = summarize_membership_diagnostics(match_results)
    ok = (
        summary["total_dom_raw"] == 6
        and summary["exact_id_match_count"] == 2
        and summary["exact_url_match_count"] == 1
        and summary["composite_match_count"] == 1
        and summary["ambiguous_count"] == 1
        and summary["unmatched_count"] == 1
        and summary["total_enriched"] == 4
    )
    if ok:
        reporter.pass_("summarize_membership_diagnostics: 카운터 합산 정확")
    else:
        reporter.fail(f"진단 카운터 이상: {summary}")


def check_trim_preserves_order(reporter: ValidationReporter) -> None:
    rows = [{"업체명": f"업체{i}"} for i in range(305)]
    trimmed = trim_membership_rows_to_target(rows, 300)
    under_target = trim_membership_rows_to_target(rows[:250], 300)
    if len(trimmed) == 300 and trimmed[0]["업체명"] == "업체0" and len(under_target) == 250:
        reporter.pass_("trim_membership_rows_to_target: 300 초과 시 순서 보존 trim, 미만이면 그대로")
    else:
        reporter.fail(f"trim 결과 이상: len(trimmed)={len(trimmed)} len(under_target)={len(under_target)}")


def check_final_row_column_keys_match_excel_contract(reporter: ValidationReporter) -> None:
    dom_row = normalize_dom_row({"name": "카페 F", "category": "카페"}, page_number=1)
    row = merge_dom_row_fields(dom_row, {"row": None, "confidence": "UNMATCHED"}, {"row": None, "confidence": "UNMATCHED"}, "2026-07-21")
    missing = [col for col in MERGED_COLUMNS if col not in row]
    if not missing:
        reporter.pass_("merge_dom_row_fields 결과가 exporter.MERGED_COLUMNS(11개) 키를 모두 포함")
    else:
        reporter.fail(f"Excel 11컬럼 중 누락된 키: {missing}")


def check_apollo_schema_change_safely_degrades(reporter: ValidationReporter) -> None:
    """Apollo entity가 category 키 자체를 갖지 않는(스키마 변경) 상황을 흉내낸다.
    to_common_entity/build_entity_index/resolve_match가 예외 없이 UNMATCHED로
    안전하게 처리해야 한다(크래시 금지, DOM 결과는 그대로 유지)."""
    dom_row = normalize_dom_row({"name": "카페 G", "category": "카페"}, page_number=1)
    broken_entities = [{"id": "9"}]  # name/category 키 자체가 없음
    index = _apollo_index(broken_entities)
    result = resolve_match(dom_row, index)
    if result["confidence"] == "UNMATCHED":
        reporter.pass_("Apollo 스키마 변경(필드 누락) 시 예외 없이 UNMATCHED로 안전 저하")
    else:
        reporter.fail(f"Apollo 스키마 변경 처리 이상: {result}")


# ---------------------------------------------------------------------------
# 8. resolve_dom_identifier guard (React Fiber 기반 place_id, PAGE300-DOM-2)
# ---------------------------------------------------------------------------


def check_identifier_fast_path_item_id(reporter: ValidationReporter) -> None:
    raw = {"identifier_candidates": {"fast_item_id": "2014880028"}}
    result = resolve_dom_identifier(raw)
    if result == {
        "place_id": "2014880028",
        "identifier_method": "FIBER_FAST_PATH",
        "identifier_validated": True,
        "identifier_conflict": False,
        "identifier_apollo_confirmed": False,
    }:
        reporter.pass_("resolve_dom_identifier: fast path item.id 단독 채택 -> FIBER_FAST_PATH")
    else:
        reporter.fail(f"fast path item.id 처리 이상: {result}")


def check_identifier_fast_path_apollo_cache_id(reporter: ValidationReporter) -> None:
    raw = {"identifier_candidates": {"fast_apollo_cache_id": "2024584509"}}
    result = resolve_dom_identifier(raw)
    if result["place_id"] == "2024584509" and result["identifier_method"] == "FIBER_FAST_PATH":
        reporter.pass_("resolve_dom_identifier: fast path apolloCacheId 단독 채택 -> FIBER_FAST_PATH")
    else:
        reporter.fail(f"fast path apolloCacheId 처리 이상: {result}")


def check_identifier_fast_path_matching_pair(reporter: ValidationReporter) -> None:
    raw = {"identifier_candidates": {"fast_item_id": "2014880028", "fast_apollo_cache_id": "2014880028"}}
    result = resolve_dom_identifier(raw)
    if result["place_id"] == "2014880028" and result["identifier_method"] == "FIBER_FAST_PATH" and not result["identifier_conflict"]:
        reporter.pass_("resolve_dom_identifier: item.id와 apolloCacheId 일치 시 정상 채택")
    else:
        reporter.fail(f"id/apolloCacheId 일치 케이스 처리 이상: {result}")


def check_identifier_fast_path_conflict(reporter: ValidationReporter) -> None:
    raw = {"identifier_candidates": {"fast_item_id": "2014880028", "fast_apollo_cache_id": "9999999999"}}
    result = resolve_dom_identifier(raw)
    if result["place_id"] == "" and result["identifier_method"] == "CONFLICT" and result["identifier_conflict"] is True:
        reporter.pass_("resolve_dom_identifier: item.id와 apolloCacheId 불일치 -> CONFLICT, 임의 채택 금지")
    else:
        reporter.fail(f"id/apolloCacheId 충돌 처리 이상: {result}")


def check_identifier_bounded_search_single_value(reporter: ValidationReporter) -> None:
    raw = {
        "identifier_candidates": {
            "bounded_candidates": [
                {"path": "x.placeId", "value": "1234567"},
                {"path": "y.placeId", "value": "1234567"},
            ]
        }
    }
    result = resolve_dom_identifier(raw)
    if result["place_id"] == "1234567" and result["identifier_method"] == "FIBER_BOUNDED_SEARCH":
        reporter.pass_("resolve_dom_identifier: bounded search에서 distinct 값이 1개면 채택")
    else:
        reporter.fail(f"bounded search 단일값 처리 이상: {result}")


def check_identifier_bounded_search_conflicting_values(reporter: ValidationReporter) -> None:
    raw = {
        "identifier_candidates": {
            "bounded_candidates": [
                {"path": "x.placeId", "value": "1234567"},
                {"path": "y.businessId", "value": "7654321"},
            ]
        }
    }
    result = resolve_dom_identifier(raw)
    if result["place_id"] == "" and result["identifier_method"] == "CONFLICT":
        reporter.pass_("resolve_dom_identifier: bounded search 후보가 서로 다르면 CONFLICT(임의 선택 금지)")
    else:
        reporter.fail(f"bounded search 충돌 처리 이상: {result}")


def check_identifier_rejects_invalid_format(reporter: ValidationReporter) -> None:
    too_short = resolve_dom_identifier({"identifier_candidates": {"fast_item_id": "42"}})
    non_numeric = resolve_dom_identifier({"identifier_candidates": {"fast_item_id": "abc12345"}})
    too_long = resolve_dom_identifier({"identifier_candidates": {"fast_item_id": "1" * 20}})
    if (
        too_short["identifier_method"] == "UNRESOLVED"
        and non_numeric["identifier_method"] == "UNRESOLVED"
        and too_long["identifier_method"] == "UNRESOLVED"
    ):
        reporter.pass_("resolve_dom_identifier: 숫자가 아니거나 비정상 길이인 값은 거부(무관한 id 채택 금지)")
    else:
        reporter.fail(f"형식 검증 이상: too_short={too_short} non_numeric={non_numeric} too_long={too_long}")


def check_identifier_href_fallback_only_when_no_fiber_candidates(reporter: ValidationReporter) -> None:
    raw = {"anchor_hrefs": ["/restaurant/887766/home", "#"]}
    result = resolve_dom_identifier(raw)
    if result["place_id"] == "887766" and result["identifier_method"] == "HREF_ID":
        reporter.pass_("resolve_dom_identifier: Fiber 후보가 전혀 없을 때만 href 파싱으로 fallback")
    else:
        reporter.fail(f"href fallback 처리 이상: {result}")


def check_identifier_unresolved_row_kept_by_normalize(reporter: ValidationReporter) -> None:
    row = normalize_dom_row({"name": "카페 무식별", "category": "카페"}, page_number=1)
    if (
        row["place_id"] == ""
        and row["identifier_method"] == "UNRESOLVED"
        and row["identifier_validated"] is False
        and row["normalized_name"] == "카페 무식별"
    ):
        reporter.pass_("normalize_dom_row: place_id를 확정하지 못해도(UNRESOLVED) row 자체는 삭제되지 않고 유지됨")
    else:
        reporter.fail(f"UNRESOLVED row 처리 이상: {row}")


def check_apollo_key_confirmation(reporter: ValidationReporter) -> None:
    apollo_raw_keys = {"PlaceListBusinessesItem:2014880028:2014880028", "PlaceListBusinessesItem:1:1"}
    confirmed = apollo_key_exists_for_id(apollo_raw_keys, "2014880028")
    not_confirmed = apollo_key_exists_for_id(apollo_raw_keys, "9999999999")
    empty_keys_not_confirmed = apollo_key_exists_for_id(set(), "2014880028")
    if confirmed and not not_confirmed and not empty_keys_not_confirmed:
        reporter.pass_("apollo_key_exists_for_id: PlaceListBusinessesItem key 존재 여부를 정확히 판별")
    else:
        reporter.fail(f"apollo_key_exists_for_id 판정 이상: confirmed={confirmed} not_confirmed={not_confirmed}")


def check_identifier_apollo_confirmed_flag_propagates(reporter: ValidationReporter) -> None:
    apollo_raw_keys = {"PlaceListBusinessesItem:2014880028:2014880028"}
    row = normalize_dom_row(
        {"name": "카페 A", "category": "카페", "identifier_candidates": {"fast_item_id": "2014880028"}},
        page_number=1,
        apollo_raw_keys=apollo_raw_keys,
    )
    row_unconfirmed = normalize_dom_row(
        {"name": "카페 B", "category": "카페", "identifier_candidates": {"fast_item_id": "5555555555"}},
        page_number=1,
        apollo_raw_keys=apollo_raw_keys,
    )
    if row["identifier_apollo_confirmed"] is True and row_unconfirmed["identifier_apollo_confirmed"] is False:
        reporter.pass_("normalize_dom_row: Apollo key 존재 여부가 identifier_apollo_confirmed로 정확히 전달됨(무효화 근거로는 사용 안 함)")
    else:
        reporter.fail(f"apollo_confirmed 전달 이상: row={row} row_unconfirmed={row_unconfirmed}")


def check_identifier_places_300_unique_via_fast_path(reporter: ValidationReporter) -> None:
    """300개 row가 각각 다른 fast-path id를 가지면 place_id 300개가 모두 서로 달라야 한다."""
    place_ids = set()
    for i in range(300):
        raw = {"name": f"업체{i}", "category": "카페", "identifier_candidates": {"fast_item_id": f"{100000000 + i}"}}
        row = normalize_dom_row(raw, page_number=(i // 70) + 1)
        place_ids.add(row["place_id"])
    if len(place_ids) == 300:
        reporter.pass_("normalize_dom_row: 300개 row 각각 고유 fast-path id -> place_id 300개 uniqueness 확인")
    else:
        reporter.fail(f"place_id uniqueness 이상: {len(place_ids)}/300")


def main() -> int:
    reporter = ValidationReporter()
    checks = [
        check_extract_place_id_named_and_generic_segments,
        check_normalize_place_url_strips_query_and_slash,
        check_normalize_dom_row_fills_place_id_from_href_fallback,
        check_skeleton_row_excluded,
        check_match_exact_id,
        check_match_exact_url,
        check_match_strong_composite_address,
        check_match_name_category_only_is_ambiguous,
        check_match_multiple_candidates_ambiguous,
        check_match_unmatched,
        check_merge_dom_network_only,
        check_merge_dom_apollo_only,
        check_merge_dom_network_apollo_network_wins,
        check_merge_enrichment_failed_keeps_dom_row,
        check_merge_place_url_prefers_dom_anchor,
        check_dedup_prefers_place_id_over_name,
        check_dedup_same_name_different_branch_kept,
        check_dedup_key_never_name_only,
        check_signature_changes_with_content,
        check_transition_requires_all_three_conditions,
        check_diagnostics_counts_match,
        check_trim_preserves_order,
        check_final_row_column_keys_match_excel_contract,
        check_apollo_schema_change_safely_degrades,
        check_identifier_fast_path_item_id,
        check_identifier_fast_path_apollo_cache_id,
        check_identifier_fast_path_matching_pair,
        check_identifier_fast_path_conflict,
        check_identifier_bounded_search_single_value,
        check_identifier_bounded_search_conflicting_values,
        check_identifier_rejects_invalid_format,
        check_identifier_href_fallback_only_when_no_fiber_candidates,
        check_identifier_unresolved_row_kept_by_normalize,
        check_apollo_key_confirmation,
        check_identifier_apollo_confirmed_flag_propagates,
        check_identifier_places_300_unique_via_fast_path,
    ]
    for check in checks:
        check(reporter)
    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
