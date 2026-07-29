# 법정동 스냅샷 갱신 개발자용 스크립트(법정동 production 통합 1단계).
#
# 행정안전부 공공데이터포털(data.go.kr) StanReginCd Open API에서 전체 법정동
# 코드를 조회해 data/legal_dong_snapshot.json과 비교한 변경 보고서를 만든다.
# 기본 실행은 보고서만 만들고 기존 snapshot 파일을 수정하지 않으며, --apply를
# 줘야만 기존 파일을 백업한 뒤 새 snapshot으로 교체한다. --probe는 실제
# 네트워크 호출을 정확히 1회(3건)만 보내 응답 구조를 확인하는 안전 모드이며
# snapshot 파일을 읽거나 쓰지 않는다. API 키가 없으면 어떤 네트워크 호출도
# 시도하지 않고 안내만 출력한 뒤 종료한다(파일 수정 0건).
#
# 주의(검증 필요): _parse_api_response()/_normalize_record()의 필드 매핑은
# data.go.kr StanReginCd API 문서(공개 페이지 요약) 기준으로 작성했으며, 실제
# 서비스키로 처음 호출했을 때 응답 구조(특히 head/row 중첩 형태)가 문서와
# 다르면 즉시 실패로 드러나도록 방어적으로 파싱한다 - 조용히 잘못된 값으로
# 넘어가지 않는다. locat_rm은 전국 20,560건 실측(비공란 298건 전수 확인)
# 결과 폐지 여부가 아니라 명칭/관할구역 변경 조례를 인용하는 비고임이
# 확인됐다(§H 해소) - is_active 판정에 쓰지 않는다. 정규화는 법정동 코드
# 구간으로 상위(sido/sigungu) 행을 조회하지 않고 locatadd_nm/locallow_nm
# 원문을 그대로 구조적으로 분리한다(세종특별자치시는 실제로 상위 sido 행이
# API 응답에 없어 코드 기반 조회가 항상 실패함이 Full Dry Run 감사로 확인됨).
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.diagnostics import DEFAULT_DIAGNOSTICS_ROOT  # noqa: E402

SNAPSHOT_PATH = ROOT_DIR / "data" / "legal_dong_snapshot.json"
ENV_PATH = ROOT_DIR / ".env"
API_BASE_URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
NUM_OF_ROWS = 1000
PROBE_NUM_OF_ROWS = 3
PROBE_LOCATADD_NM = "서울특별시"  # 공공데이터포털 미리보기 성공 사례와 동일 조건 - --probe 전용, 전체 조회에는 쓰지 않음
REQUEST_TIMEOUT_SEC = 30
SOURCE_NAME = "행정안전부 행정표준코드관리시스템(공공데이터포털 StanReginCd API)"
SOURCE_URL = "https://www.data.go.kr/data/15077871/openapi.do"

LEGAL_CODE_RE = re.compile(r"^[0-9]{10}$")
SNAPSHOT_SCHEMA_VERSION = 1
_OK_RESULT_CODES = ("INFO-0", "00")
_SERVICE_KEY_PATTERN = re.compile(r"serviceKey=[^&\s]*", re.IGNORECASE)


class SnapshotUpdateError(Exception):
    """API 조회·검증 실패 - 이 예외가 발생하면 snapshot 파일을 절대 건드리지 않는다."""


_HTTP_ERROR_BODY_LIMIT_BYTES = 4096


class HttpProbeFailure(Exception):
    """HTTP 오류(예: 500) 진단 정보를 구조화해서 담는다. status/content_type/
    body_format/body_snippet 전부 인증키가 제거된 상태로만 보관한다."""

    def __init__(self, *, status: int, reason: str, content_type: str, body_snippet: str, body_format: str):
        self.status = status
        self.reason = reason
        self.content_type = content_type
        self.body_snippet = body_snippet
        self.body_format = body_format
        super().__init__(f"HTTP {status} {reason}")


def _redact(text: str) -> str:
    """예외/로그 문자열에 serviceKey=... 가 섞여 있으면 값을 가린다(대소문자 무관)."""
    return _SERVICE_KEY_PATTERN.sub("serviceKey=***", str(text))


def _classify_body_format(content_type: str, body_text: str) -> str:
    """Content-Type 헤더를 우선 신뢰하고, 없거나 애매하면 본문 앞부분을
    보고 XML/JSON/HTML/PLAIN_TEXT 중 하나로 분류한다(추측 표시 없이 확정
    불가하면 UNKNOWN)."""
    ct = (content_type or "").lower()
    if "json" in ct:
        return "JSON"
    if "html" in ct:
        return "HTML"
    if "xml" in ct:
        return "XML"

    stripped = body_text.lstrip()
    if not stripped:
        return "UNKNOWN"
    if stripped.startswith("{") or stripped.startswith("["):
        return "JSON"
    lowered_head = stripped[:200].lower()
    if stripped.startswith("<"):
        if "<html" in lowered_head or "<!doctype html" in lowered_head:
            return "HTML"
        return "XML"
    return "PLAIN_TEXT"


# --------------------------------------------------------------------------
# 서비스키 로딩 - 어떤 예외 상황에서도 키 값 자체를 print/log에 남기지 않는다.
# --------------------------------------------------------------------------
def load_service_key() -> str:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ENV_PATH)
    return (os.environ.get("DATA_GO_KR_SERVICE_KEY") or "").strip()


# --------------------------------------------------------------------------
# HTTP - requests 정식 클라이언트(urllib은 게이트웨이와 호환되지 않아 폐기됨,
# 격리 probe에서 requests만 HTTP 200으로 성공한 것을 근거로 교체)
# --------------------------------------------------------------------------
def _http_get(params: dict) -> dict:
    """requests.get으로 실제 요청을 보낸다. params는 그대로 requests에 넘겨
    인코딩을 전담시킨다(수동 quote/urlencode 없음). Timeout/ConnectionError/
    TooManyRedirects 등 requests 예외는 여기서 삼키지 않고 그대로 올려
    보내 호출자가 SnapshotUpdateError로 감싸며 redact하게 한다. HTTP status가
    200이 아니면(서버가 Content-Type을 text/html로 잘못 표기하는 경우가
    있어 Content-Type을 신뢰 기준으로 쓰지 않고 상태 코드만으로 판단) 본문을
    최대 4096 bytes까지만 읽어 HttpProbeFailure로 구조화한다. 리다이렉트는
    requests 기본 동작대로 따라가고 횟수만 반환값에 담는다(최종 URL은 어디에도
    남기지 않는다)."""
    response = requests.get(API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SEC)
    redirect_count = len(response.history)

    if response.status_code != 200:
        body_bytes = response.content[:_HTTP_ERROR_BODY_LIMIT_BYTES]
        body_text = _redact(body_bytes.decode("utf-8", errors="replace"))
        content_type = response.headers.get("Content-Type", "") or ""
        body_format = _classify_body_format(content_type, body_text)
        raise HttpProbeFailure(
            status=response.status_code,
            reason=response.reason or "",
            content_type=content_type,
            body_snippet=body_text,
            body_format=body_format,
        )

    return {"text": response.text, "redirect_count": redirect_count}


def _build_params(service_key: str, page_no: int, num_of_rows: int) -> dict:
    """공식 파라미터명은 'serviceKey'(소문자). 값은 원본 그대로 dict에 담아
    requests.get(..., params=이_dict)에 넘긴다 - 인코딩은 requests가 전담하며
    여기서 수동 quote/urlencode를 하지 않는다."""
    return {"serviceKey": service_key, "pageNo": page_no, "numOfRows": num_of_rows, "type": "json"}


def _build_probe_params(service_key: str) -> dict:
    """--probe 전용 파라미터. 공공데이터포털 콘솔에서 실제로 성공한 요청과
    동일한 순서(serviceKey -> pageNo -> numOfRows -> type -> locatadd_nm)와
    값(type=json 소문자, locatadd_nm=서울특별시)으로 구성한다(dict 삽입 순서 =
    requests가 보내는 쿼리 순서). 전체 조회(_build_params)에는 영향을 주지
    않는다."""
    return {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": PROBE_NUM_OF_ROWS,
        "type": "json",
        "locatadd_nm": PROBE_LOCATADD_NM,
    }


def _parse_api_response(raw_text: str, page_no: int) -> dict:
    """head(resultCode/totalCount)와 row(레코드 목록)를 뽑아 dict로 반환한다.
    {"result_code": str, "result_msg": str, "total_count": int, "rows": list[dict]}.
    resultCode가 없거나 성공 값이 아니면 여기서 즉시 SnapshotUpdateError."""
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SnapshotUpdateError(f"page {page_no} 응답 JSON 파싱 실패: {exc}") from exc

    try:
        sections = payload["StanReginCd"]
        head_items = sections[0]["head"]
        result_code = None
        result_msg = None
        total_count = None
        for item in head_items:
            if "RESULT" in item:
                result_code = item["RESULT"].get("resultCode")
                result_msg = item["RESULT"].get("resultMsg")
            if "totalCount" in item:
                total_count = int(item["totalCount"])
        rows = sections[1].get("row", []) if len(sections) > 1 else []
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SnapshotUpdateError(
            f"page {page_no} 응답 구조가 예상(StanReginCd/head/row)과 다름: {exc}"
        ) from exc

    if result_code is None or result_code not in _OK_RESULT_CODES:
        raise SnapshotUpdateError(
            f"page {page_no} API 오류/누락 resultCode: resultCode={result_code!r} resultMsg={result_msg!r}"
        )
    if total_count is None:
        raise SnapshotUpdateError(f"page {page_no} 응답에 totalCount가 없음")

    return {"result_code": result_code, "result_msg": result_msg, "total_count": total_count, "rows": rows}


def _validate_region_cd(raw_value) -> str:
    """region_cd는 원본부터 정확히 10자리 숫자 문자열이어야 한다.
    zfill이나 자동 패딩을 하지 않는다 - 9/11자리·공란·문자 포함은 즉시 오류."""
    code = str(raw_value if raw_value is not None else "")
    if not LEGAL_CODE_RE.match(code):
        raise SnapshotUpdateError(f"region_cd가 정확히 10자리 숫자 문자열이 아님: {raw_value!r}")
    return code


# --------------------------------------------------------------------------
# 전체 페이지네이션(기본/--apply 경로 전용 - --probe는 이 함수를 쓰지 않음)
# --------------------------------------------------------------------------
def fetch_all_records(service_key: str, *, fetch_fn=None) -> list:
    """totalCount에 도달할 때까지 전체 페이지를 조회한다. totalCount<=0, 전체
    row 0건, 중간 빈 페이지, 페이지 간 totalCount 불일치, 중복 코드, HTTP/JSON
    오류 중 하나라도 발생하면 SnapshotUpdateError를 던지고 지금까지 모은
    결과를 버린다(호출자가 snapshot을 수정하지 않도록)."""
    fetch = fetch_fn or _http_get
    all_rows: list = []
    seen_codes: set = set()
    page_no = 1
    expected_total = None

    while True:
        params = _build_params(service_key, page_no, NUM_OF_ROWS)
        try:
            result = fetch(params)
        except HttpProbeFailure:
            raise
        except Exception as exc:
            raise SnapshotUpdateError(f"page {page_no} 요청 실패: {_redact(f'{type(exc).__name__}: {exc}')}") from exc

        parsed = _parse_api_response(result["text"], page_no)
        if expected_total is None:
            expected_total = parsed["total_count"]
            if expected_total <= 0:
                raise SnapshotUpdateError(f"totalCount가 0 이하임: {expected_total}")
        elif parsed["total_count"] != expected_total:
            raise SnapshotUpdateError(
                f"page {page_no}에서 totalCount가 바뀜(최초 {expected_total} -> {parsed['total_count']})"
            )

        rows = parsed["rows"]
        if not rows:
            if len(all_rows) < expected_total:
                raise SnapshotUpdateError(
                    f"page {page_no}가 비어 있는데 아직 totalCount({expected_total})에 도달하지 못함(수신 {len(all_rows)}건)"
                )
            break

        for row in rows:
            code = _validate_region_cd(row.get("region_cd"))
            if code in seen_codes:
                raise SnapshotUpdateError(f"중복 region_cd 발견: {code}")
            seen_codes.add(code)
            all_rows.append(row)

        if len(all_rows) >= expected_total:
            break
        page_no += 1

    if len(all_rows) == 0:
        raise SnapshotUpdateError("전체 수신 row가 0건")
    if len(all_rows) != expected_total:
        raise SnapshotUpdateError(
            f"전체 조회 건수 불일치: totalCount={expected_total}, 실제 수신={len(all_rows)}"
        )
    return all_rows


# --------------------------------------------------------------------------
# Bounded Live Probe(§5) - pageNo=1/numOfRows=3 요청 정확히 1회, snapshot 무관
# --------------------------------------------------------------------------
def run_probe(service_key: str, *, fetch_fn=None) -> dict:
    """실제 요청 정확히 1회(numOfRows=3)만 보내 응답 구조를 안전하게 요약한다.
    snapshot 파일을 읽거나 쓰지 않고, 인증키/전체 URL/원본 응답 전체는 어디에도
    남기지 않는다. 반환값이 그대로 probe 보고서(JSON)로 저장 가능해야 한다."""
    fetch = fetch_fn or _http_get
    params = _build_probe_params(service_key)
    try:
        result = fetch(params)
    except HttpProbeFailure:
        raise
    except Exception as exc:
        raise SnapshotUpdateError(f"probe 요청 실패: {_redact(f'{type(exc).__name__}: {exc}')}") from exc

    raw_text = result["text"]
    parsed = _parse_api_response(raw_text, page_no=1)
    rows = parsed["rows"]

    row_key_inventory: list = []
    seen_keys: set = set()
    for row in rows:
        for key in row.keys():
            if key not in seen_keys:
                seen_keys.add(key)
                row_key_inventory.append(key)

    watched_fields = ("region_cd", "locatadd_nm", "locallow_nm", "locat_rm", "adpt_de")
    sample_rows = []
    for row in rows[:3]:
        sample = {}
        for field in watched_fields:
            present = field in row
            value = row.get(field)
            sample[field] = {"present": present, "value": value if present else None}
        raw_code = row.get("region_cd")
        sample["region_cd_is_10_digit"] = bool(raw_code is not None and LEGAL_CODE_RE.match(str(raw_code)))
        sample_rows.append(sample)

    return {
        "endpoint_name": API_BASE_URL,  # 쿼리스트링(서비스키 포함) 없이 base URL만
        "result_code": parsed["result_code"],
        "result_msg": parsed["result_msg"],
        "total_count": parsed["total_count"],
        "row_count": len(rows),
        "top_level_keys": list(json.loads(raw_text).keys()),
        "row_key_inventory": row_key_inventory,
        "sample_rows": sample_rows,
        "redirect_count": result["redirect_count"],
    }


# --------------------------------------------------------------------------
# 정규화 - 원문 API row -> LegalDongItemContract record
# --------------------------------------------------------------------------
def _code_segments(code: str) -> tuple:
    return code[0:2], code[2:5], code[5:8], code[8:10]


def _record_level(code: str) -> str:
    """법정동 코드 구간으로 계층 레벨(sido/sigungu/dong/ri)만 분류한다 -
    전국 20,560건 실측에서 예외 없이 일관되게 성립함이 확인됐다(Full Dry
    Run 감사). 상위 행의 이름/존재 자체를 이 코드 구간으로 추정하지는
    않는다 - 그건 normalize_records가 locatadd_nm 원문으로 처리한다."""
    sido_seg, sgg_seg, umd_seg, ri_seg = _code_segments(code)
    if ri_seg != "00":
        return "ri"
    if umd_seg != "000":
        return "dong"
    if sgg_seg != "000":
        return "sigungu"
    return "sido"


def _format_date(raw_date) -> str:
    text = str(raw_date or "").strip()
    if re.fullmatch(r"[0-9]{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return ""


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(text) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()


def _split_full_name(full_name: str) -> tuple:
    """locatadd_nm(공백 정규화된 행안부 공식 전체 명칭) 토큰만으로 sido/
    sigungu/eup_myeon_dong을 구조적으로 분리한다. 법정동 코드 구간으로 상위
    행을 조회/추정하지 않는다 - 세종특별자치시는 실제로 상위 sido 행 자체가
    API 응답에 없다는 것이 전국 Full Dry Run 감사로 확인됐다(코드 기반
    조회는 이 경우 항상 실패한다). 규칙: 첫 토큰=sido, 마지막 토큰=
    eup_myeon_dong(권위 필드 - locallow_nm과 비교하지 않는다, §normalization
    _policy.md 권위 순서), 그 사이 토큰은 순서를 보존해 합쳐 sigungu로 쓴다
    (중간이 없으면 빈 문자열 - 세종/제주시 등, "수원시 장안구"처럼 2개면
    그대로 결합). 특정 지역명을 조건문에 직접 넣지 않는다 - 토큰 개수/위치
    만으로 일반화된다."""
    tokens = full_name.split(" ") if full_name else []
    if len(tokens) < 2:
        raise SnapshotUpdateError(
            f"locatadd_nm 토큰이 2개 미만이라 sido/읍면동을 분리할 수 없음: {full_name!r}"
        )
    sido_name = tokens[0]
    eup_myeon_dong = tokens[-1]
    sigungu_name = " ".join(tokens[1:-1])
    return sido_name, sigungu_name, eup_myeon_dong


def _classify_locallow_variant(locallow_nm: str, eup_myeon_dong: str, sigungu_name: str) -> str:
    """locallow_nm은 권위 필드가 아니라 보조 일관성 감사 필드다(eup_myeon_dong은
    항상 locatadd_nm 마지막 토큰을 쓴다 - 여기서 locallow_nm으로 잘라 만들지
    않는다). 전국 실측(청주시 상당구 사례: locatadd_nm 마지막 토큰='영동',
    locallow_nm='상당구영동')에서 locallow_nm이 sigungu 마지막 토큰을 구분자
    없이 붙인 값을 담는 경우가 확인돼 이를 정상 변형으로 분류한다. 어떤
    알려진 유형에도 해당하지 않으면 "unexplained"를 반환하고, 호출자가
    이를 실패로 처리한다(완화 규칙을 여기서 임의로 넓히지 않는다)."""
    locallow = _normalize_whitespace(locallow_nm)
    if locallow == eup_myeon_dong:
        return "exact_match"
    if locallow.replace(" ", "") == eup_myeon_dong.replace(" ", ""):
        return "whitespace_diff"
    if eup_myeon_dong and locallow.endswith(eup_myeon_dong):
        prefix = locallow[: -len(eup_myeon_dong)]
        sigungu_last_token = sigungu_name.split(" ")[-1] if sigungu_name else ""
        if prefix and prefix == sigungu_last_token:
            return "sigungu_prefix_concatenation"
        return "ends_with_eup_myeon_dong_other_prefix"
    return "unexplained"


def normalize_records(raw_rows: list, *, source_version: str = "") -> list:
    """법정리(ri)는 제외하고, 읍/면/동(dong) 레코드만 행안부 원문 locatadd_nm
    을 권위 필드로 구조적으로 분리해 LegalDongItemContract 스키마로 변환한다.
    법정동 코드 구간으로 상위(sido/sigungu) 행을 조회/추정하지 않는다 -
    locatadd_nm은 이미 행안부가 만든 완성된 전체 명칭 문자열이므로 이를
    분리하는 편이 코드 구간 산술보다 안정적이다(세종특별자치시 dong 33건이
    상위 sido 행 부재로 코드 기반 조회에서만 실패했음을 전국 Full Dry Run으로
    확인). eup_myeon_dong은 항상 locatadd_nm 마지막 토큰이며, locallow_nm은
    보조 일관성 감사 필드일 뿐이다 - 알려진 변형(공백차이/sigungu 접두 결합/
    읍면동명으로 끝남)이 아니면 즉시 오류로 중단한다(전국 20,560건 실측
    기반, §normalization_policy.md). region_cd는 zfill 등 자동 보정 없이
    원본이 정확히 10자리가 아니면 즉시 오류로 중단한다. is_active는 이번
    API 응답에 포함된 모든 행에 대해 무조건 true다 - locat_rm은 실제로는
    명칭/관할구역 변경 조례를 인용하는 비고일 뿐 폐지 상태 플래그가 아님이
    전국 298건 비공란 표본 전수 확인으로 밝혀졌다(§H 해소). 폐지 감지는
    build_diff_report의 REMOVED_CANDIDATE(기존 snapshot에는 있었으나 신규
    조회에 없는 코드)에 맡긴다."""
    records = []
    for row in raw_rows:
        code = _validate_region_cd(row.get("region_cd"))
        if _record_level(code) != "dong":
            continue

        full_name = _normalize_whitespace(row.get("locatadd_nm"))
        sido_name, sigungu_name, eup_myeon_dong = _split_full_name(full_name)

        variant = _classify_locallow_variant(row.get("locallow_nm"), eup_myeon_dong, sigungu_name)
        if variant == "unexplained":
            raise SnapshotUpdateError(
                f"legal_code={code} locallow_nm과 eup_myeon_dong의 관계를 알려진 유형으로 "
                f"설명할 수 없음: locatadd_nm={full_name!r} locallow_nm={row.get('locallow_nm')!r}"
            )

        records.append(
            {
                "legal_code": code,
                "sido": sido_name,
                "sigungu": sigungu_name,
                "eup_myeon_dong": eup_myeon_dong,
                "full_name": full_name,
                "is_active": True,
                "effective_date": _format_date(row.get("adpt_de")),
                "source_name": SOURCE_NAME,
                "source_version": source_version,
            }
        )

    records.sort(key=lambda r: r["legal_code"])
    return records


# --------------------------------------------------------------------------
# 기존 snapshot 로드 + diff 보고서
# --------------------------------------------------------------------------
def load_existing_snapshot(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SNAPSHOT_SCHEMA_VERSION, "records": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SnapshotUpdateError(f"기존 snapshot JSON 파싱 실패({path}): {exc}") from exc


def build_diff_report(existing_records: list, new_records: list) -> dict:
    existing_by_code = {r["legal_code"]: r for r in existing_records}
    new_by_code = {r["legal_code"]: r for r in new_records}

    new_entries = [r for code, r in new_by_code.items() if code not in existing_by_code]
    renamed_entries = [
        {"legal_code": code, "old_full_name": existing_by_code[code]["full_name"], "new_full_name": r["full_name"]}
        for code, r in new_by_code.items()
        if code in existing_by_code and existing_by_code[code]["full_name"] != r["full_name"]
    ]
    removed_candidates = [
        r for code, r in existing_by_code.items() if code not in new_by_code and r.get("is_active", True)
    ]

    return {
        "new_count": len(new_entries),
        "renamed_count": len(renamed_entries),
        "removed_candidate_count": len(removed_candidates),
        "new_entries": new_entries,
        "renamed_entries": renamed_entries,
        "removed_candidates": removed_candidates,
    }


# --------------------------------------------------------------------------
# 원자적 snapshot 저장(§G) - 임시파일 write+fsync+재검증 후 os.replace
# --------------------------------------------------------------------------
def _apply_snapshot(records: list, retrieved_at: str) -> Path:
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_retrieved_at": retrieved_at,
        "active_record_count": sum(1 for r in records if r["is_active"]),
        "records": records,
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(snapshot, ensure_ascii=False, indent=2)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(SNAPSHOT_PATH.parent), prefix=SNAPSHOT_PATH.stem + ".", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())

        reparsed = json.loads(tmp_path.read_text(encoding="utf-8"))
        if reparsed.get("schema_version") != SNAPSHOT_SCHEMA_VERSION or len(reparsed.get("records", [])) != len(records):
            raise SnapshotUpdateError("임시 snapshot 재검증 실패(schema_version 또는 record 수 불일치)")

        if SNAPSHOT_PATH.exists():
            backup_path = SNAPSHOT_PATH.with_name(
                SNAPSHOT_PATH.stem + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}" + SNAPSHOT_PATH.suffix
            )
            shutil.copy2(SNAPSHOT_PATH, backup_path)

        os.replace(tmp_path, SNAPSHOT_PATH)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return SNAPSHOT_PATH


# --------------------------------------------------------------------------
# 메인 흐름
# --------------------------------------------------------------------------
def _write_report(report: dict, *, prefix: str) -> Path:
    DEFAULT_DIAGNOSTICS_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = DEFAULT_DIAGNOSTICS_ROOT / f"{prefix}_{timestamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def _print_no_key_notice() -> None:
    print(
        "[안내] DATA_GO_KR_SERVICE_KEY가 .env에 설정되어 있지 않습니다.\n"
        "  - 공개 미러 데이터로 대체하지 않습니다.\n"
        "  - 가짜 snapshot을 만들지 않습니다.\n"
        f"  - .env 파일({ENV_PATH})에 DATA_GO_KR_SERVICE_KEY=<발급받은 키>를 추가한 뒤 다시 실행하세요.\n"
        "  - 기존 파일은 수정하지 않았습니다."
    )


def run_probe_cli(*, fetch_fn=None) -> int:
    service_key = load_service_key()
    if not service_key:
        _print_no_key_notice()
        return 0
    try:
        probe_result = run_probe(service_key, fetch_fn=fetch_fn)
    except HttpProbeFailure as exc:
        print(
            "[중단] Probe HTTP 오류\n"
            f"  HTTP status={exc.status} reason={exc.reason}\n"
            f"  Content-Type={exc.content_type or '(없음)'}\n"
            f"  body_format={exc.body_format}\n"
            f"  body_snippet(redacted, 최대 {_HTTP_ERROR_BODY_LIMIT_BYTES} bytes)=\n{exc.body_snippet}"
        )
        return 1
    except SnapshotUpdateError as exc:
        print(f"[중단] Probe 요청/검증 실패: {exc}")
        return 1
    report_path = _write_report(probe_result, prefix="legal_dong_probe")
    print(
        f"[Probe 완료] {report_path}\n"
        f"  resultCode={probe_result['result_code']} totalCount={probe_result['total_count']} "
        f"row_count={probe_result['row_count']}"
    )
    return 0


def run(*, apply: bool, fetch_fn=None) -> int:
    service_key = load_service_key()
    if not service_key:
        _print_no_key_notice()
        return 0
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        raw_rows = fetch_all_records(service_key, fetch_fn=fetch_fn)
        new_records = normalize_records(raw_rows, source_version=retrieved_at)
    except SnapshotUpdateError as exc:
        print(f"[중단] 공식 API 조회/검증 실패로 snapshot을 수정하지 않았습니다: {exc}")
        return 1

    if len(new_records) == 0:
        print("[중단] 정규화된 읍면동 레코드가 0건이라 snapshot을 수정하지 않았습니다.")
        return 1

    existing = load_existing_snapshot(SNAPSHOT_PATH)
    report = build_diff_report(existing.get("records", []), new_records)
    report["retrieved_at"] = retrieved_at
    report["existing_snapshot_found"] = SNAPSHOT_PATH.exists()
    report["fetched_dong_record_count"] = len(new_records)
    report_path = _write_report(report, prefix="legal_dong_snapshot_update")

    print(
        f"[보고서] {report_path}\n"
        f"  신규 {report['new_count']}건, 명칭변경 {report['renamed_count']}건, "
        f"삭제후보(REMOVED_CANDIDATE) {report['removed_candidate_count']}건"
    )

    if not apply:
        print("[안내] --apply가 없어 보고서만 생성했습니다. 기존 snapshot 파일은 수정하지 않았습니다.")
        return 0

    snapshot_path = _apply_snapshot(new_records, retrieved_at)
    print(f"[적용 완료] {snapshot_path} 갱신됨(기존 파일은 있었다면 백업 후 교체).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="법정동 snapshot 갱신 도구")
    parser.add_argument(
        "--apply", action="store_true", help="검증된 최신 snapshot으로 기존 파일을 백업 후 교체"
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="실제 요청 1회(3건)만 보내 응답 구조를 안전하게 확인(snapshot 미변경)",
    )
    args = parser.parse_args()

    if args.probe and args.apply:
        print("[중단] --probe와 --apply는 동시에 사용할 수 없습니다.")
        return 1
    if args.probe:
        return run_probe_cli()
    return run(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
