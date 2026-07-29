import json
import os
import sys
from pathlib import Path

import pytest
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import update_legal_dong_snapshot as target


def _api_page(rows, total_count, *, result_code="INFO-0", omit_result=False):
    head = [{"totalCount": total_count}]
    if not omit_result:
        head.append({"RESULT": {"resultCode": result_code, "resultMsg": "OK"}})
    return json.dumps({"StanReginCd": [{"head": head}, {"row": rows}]})


def _row(code, locallow_nm, *, locatadd_nm="", locat_rm="", adpt_de=""):
    return {
        "region_cd": code,
        "locallow_nm": locallow_nm,
        "locatadd_nm": locatadd_nm,
        "locat_rm": locat_rm,
        "adpt_de": adpt_de,
    }


# 부모 행(sido/sigungu 요약 row)은 더 이상 정규화에 쓰이지 않는다(코드 구간
# 기반 부모 조회를 폐기했으므로) - 실제 fetch_all_records/페이지네이션
# 집계 테스트용으로만 남겨둔다.
SIDO_SEOUL = _row("1100000000", "서울특별시", locatadd_nm="서울특별시")
SIGUNGU_GANGDONG = _row("1174000000", "강동구", locatadd_nm="서울특별시 강동구")
DONG_CHEONHO = _row("1174010100", "천호동", locatadd_nm="서울특별시 강동구 천호동", adpt_de="19880401")
RI_SAMPLE = _row("4180025321", "샘플리", locatadd_nm="전라남도 담양군 담양읍 샘플리")  # ri_seg != "00" -> 제외 대상

SIDO_SEJONG = _row("3600000000", "세종특별자치시", locatadd_nm="세종특별자치시")
# 실제 API 응답에는 세종시 상위 sido 행 자체가 없음(전국 Full Dry Run 감사로 확인) -
# 정규화는 이 상위 행 없이 DONG_SEJONG_JOCHIWON 하나만으로 성립해야 한다.
DONG_SEJONG_JOCHIWON = _row("3600010100", "조치원읍", locatadd_nm="세종특별자치시 조치원읍")

SIDO_GYEONGGI = _row("4100000000", "경기도", locatadd_nm="경기도")
SIGUNGU_SUWON_JANGAN = _row("4111100000", "수원시 장안구", locatadd_nm="경기도 수원시 장안구")
DONG_JEONGJA = _row("4111110100", "정자동", locatadd_nm="경기도 수원시 장안구 정자동")

# 제주특별자치도: 자치구 없는 "행정시"가 중간 토큰으로 오는 경우
DONG_JEJU = _row("5011010100", "일도일동", locatadd_nm="제주특별자치도 제주시 일도일동")

# 광역시 + 자치구 구조(서울 특별시와 별개로 광역시 사례를 별도로 확인)
DONG_HAEUNDAE = _row("2635010100", "우동", locatadd_nm="부산광역시 해운대구 우동")

# 일반 도 + 군(자치구 아님) + 읍 구조
DONG_DAMYANG = _row("4682025000", "담양읍", locatadd_nm="전라남도 담양군 담양읍")

DONG_ABOLISHED = _row(
    "1174099900", "폐지동", locatadd_nm="서울특별시 강동구 폐지동", locat_rm="폐지(1998-01-01)"
)

ALL_ROWS = [
    SIDO_SEOUL,
    SIGUNGU_GANGDONG,
    DONG_CHEONHO,
    RI_SAMPLE,
    SIDO_SEJONG,
    DONG_SEJONG_JOCHIWON,
    SIDO_GYEONGGI,
    SIGUNGU_SUWON_JANGAN,
    DONG_JEONGJA,
    DONG_JEJU,
    DONG_HAEUNDAE,
    DONG_DAMYANG,
    DONG_ABOLISHED,
]


class FakeFetcher:
    """호출 순서대로 미리 준비한 응답(str 또는 {"text","redirect_count"} dict)
    또는 예외를 반환하는 fetch_fn 대체. 실제 API 요청은 절대 보내지 않는다 -
    테스트 전체가 이 fake만 사용한다. 인자는 이제 URL 문자열이 아니라
    requests에 그대로 넘기는 params dict다(calls에 그 dict가 그대로 쌓인다)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, params):
        self.calls.append(params)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict) and "text" in item:
            return item
        return {"text": item, "redirect_count": 0}


class _FakeResponse:
    """requests.Response의 최소 부분집합을 흉내내는 테스트 전용 더미
    (status_code/text/content/headers/reason/history). _http_get 단위
    테스트에서 target.requests.get을 대체하는 데만 쓰인다."""

    def __init__(self, *, status_code=200, text="", headers=None, reason="", history=None):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = headers or {}
        self.reason = reason
        self.history = history or []


@pytest.fixture(autouse=True)
def _isolate_snapshot_and_env(tmp_path, monkeypatch):
    """모든 테스트에서 실제 프로젝트의 .env/data/legal_dong_snapshot.json/
    logs/diagnostics를 절대 건드리지 않도록 임시 경로로 리다이렉트한다."""
    monkeypatch.setattr(target, "SNAPSHOT_PATH", tmp_path / "legal_dong_snapshot.json")
    monkeypatch.setattr(target, "ENV_PATH", tmp_path / "does_not_exist.env")
    monkeypatch.setattr(target, "DEFAULT_DIAGNOSTICS_ROOT", tmp_path / "diag")
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    return tmp_path


# --------------------------------------------------------------------------
# 1. 키 미설정
# --------------------------------------------------------------------------
def test_no_service_key_makes_zero_network_calls(_isolate_snapshot_and_env):
    fetcher = FakeFetcher([])
    exit_code = target.run(apply=True, fetch_fn=fetcher)
    assert exit_code == 0
    assert fetcher.calls == []


def test_no_service_key_probe_also_makes_zero_network_calls(_isolate_snapshot_and_env):
    fetcher = FakeFetcher([])
    exit_code = target.run_probe_cli(fetch_fn=fetcher)
    assert exit_code == 0
    assert fetcher.calls == []


def test_real_project_env_file_is_never_read_by_tests(monkeypatch, tmp_path):
    """ENV_PATH를 리다이렉트하지 않아도(autouse fixture가 이미 리다이렉트함)
    실제 프로젝트 루트 .env가 아니라 격리된 경로만 읽힌다는 것을 명시적으로
    확인한다 - sentinel 값으로 증명."""
    sentinel_env = tmp_path / "sentinel.env"
    sentinel_env.write_text("DATA_GO_KR_SERVICE_KEY=sentinel-value-not-a-real-key\n", encoding="utf-8")
    monkeypatch.setattr(target, "ENV_PATH", sentinel_env)
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    key = target.load_service_key()
    assert key == "sentinel-value-not-a-real-key"


# --------------------------------------------------------------------------
# 2. HTTPS
# --------------------------------------------------------------------------
def test_api_base_url_uses_https():
    assert target.API_BASE_URL.startswith("https://")


# --------------------------------------------------------------------------
# requests 정식 클라이언트 채택 확인
# --------------------------------------------------------------------------
def test_requests_2_34_2_importable():
    assert requests.__version__ == "2.34.2"


def test_production_module_has_no_urllib_reference():
    """urllib 기반 HTTP 클라이언트는 게이트웨이와 호환되지 않아 완전히
    폐기됐다(격리 requests probe는 성공) - production 코드가 urllib을
    import하지 않아야 한다(과거 폐기 이력을 설명하는 주석은 무관)."""
    assert "urllib" not in dir(target)


# --------------------------------------------------------------------------
# 3-5. --probe 계약
# --------------------------------------------------------------------------
def test_probe_sends_exactly_one_request(_isolate_snapshot_and_env):
    monkeypatch_key = "fake-key-for-test"
    os.environ["DATA_GO_KR_SERVICE_KEY"] = monkeypatch_key
    try:
        page = _api_page(ALL_ROWS[:3], total_count=len(ALL_ROWS))
        fetcher = FakeFetcher([page])
        exit_code = target.run_probe_cli(fetch_fn=fetcher)
        assert exit_code == 0
        assert len(fetcher.calls) == 1
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


def test_probe_requests_num_of_rows_3(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        page = _api_page(ALL_ROWS[:3], total_count=len(ALL_ROWS))
        fetcher = FakeFetcher([page])
        target.run_probe_cli(fetch_fn=fetcher)
        called_params = fetcher.calls[0]
        assert called_params["numOfRows"] == 3
        assert called_params["pageNo"] == 1
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


def test_probe_type_param_is_lowercase_json():
    params = target._build_probe_params("plainkey")
    assert params["type"] == "json"


def test_probe_includes_locatadd_nm_seoul():
    params = target._build_probe_params("plainkey")
    assert params["locatadd_nm"] == "서울특별시"


def test_probe_locatadd_nm_not_manually_encoded():
    """locatadd_nm은 requests의 params 인코딩에 맡기기 위해 dict에 원문
    그대로(퍼센트 인코딩 없이) 저장돼야 한다 - 수동 quote/urlencode 금지."""
    params = target._build_probe_params("plainkey")
    assert params["locatadd_nm"] == "서울특별시"
    assert "%" not in params["locatadd_nm"]


def test_probe_full_params_never_leaks_service_key_by_itself(monkeypatch):
    params = target._build_probe_params("SECRET-PLAIN-KEY")
    assert params["serviceKey"] == "SECRET-PLAIN-KEY"  # 이 함수 자체는 params dict를 만들 뿐, 로그 출력이 아님(별도 확인 지점)
    # 실제로 이 dict가 로그/보고서로 나가는 경로(run_probe_cli/run_probe)는 서비스키를 절대 출력하지 않는지 별도 테스트로 확인됨.


def test_full_fetch_params_builder_unaffected_by_probe_changes():
    """전체 조회(fetch_all_records)용 _build_params는 이번 probe 전용 수정과
    무관하게 그대로 type=json(소문자), locatadd_nm 없음을 유지해야 한다."""
    params = target._build_params("plainkey", 1, 1000)
    assert params["type"] == "json"
    assert "locatadd_nm" not in params


def test_probe_never_touches_snapshot_file(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        assert not target.SNAPSHOT_PATH.exists()
        page = _api_page(ALL_ROWS[:3], total_count=len(ALL_ROWS))
        fetcher = FakeFetcher([page])
        target.run_probe_cli(fetch_fn=fetcher)
        assert not target.SNAPSHOT_PATH.exists()
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


def test_probe_report_excludes_service_key_and_full_url(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        page = _api_page([DONG_CHEONHO], total_count=1)
        fetcher = FakeFetcher([page])
        result = target.run_probe("fake-key-for-test", fetch_fn=fetcher)
        serialized = json.dumps(result, ensure_ascii=False)
        assert "fake-key-for-test" not in serialized
        assert "?" not in result["endpoint_name"]
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


# --------------------------------------------------------------------------
# 요청 파라미터 계약 - 공공데이터포털 콘솔에서 실제 성공한 요청과 동일해야 함
# (serviceKey 소문자, type=json 소문자, 파라미터 순서 고정, 수동 인코딩 없음)
# --------------------------------------------------------------------------
def test_service_key_param_name_is_lowercase_serviceKey():
    params = target._build_params("plainkey", 1, 3)
    assert "serviceKey" in params
    assert "ServiceKey" not in params  # 대문자 S로 시작하는 키가 있으면 실패해야 한다(사용자 지시 9번)


def test_probe_service_key_param_name_is_lowercase_serviceKey():
    params = target._build_probe_params("plainkey")
    assert "serviceKey" in params
    assert "ServiceKey" not in params


def test_probe_service_key_appears_exactly_once():
    params = target._build_probe_params("plainkey")
    assert list(params.keys()).count("serviceKey") == 1


def test_probe_param_order_matches_success_contract():
    """공공데이터포털 콘솔 성공 요청과 동일한 순서:
    serviceKey -> pageNo -> numOfRows -> type -> locatadd_nm. dict 삽입
    순서가 곧 requests가 보내는 쿼리 순서다(Python 3.7+ dict 순서 보장)."""
    params = target._build_probe_params("plainkey")
    assert list(params.keys()) == ["serviceKey", "pageNo", "numOfRows", "type", "locatadd_nm"]


def test_service_key_value_stored_raw_not_manually_encoded():
    # requests의 params 인코딩을 그대로 쓰기 위해 dict에는 원본 값을 그대로
    # 저장한다 - 키 종류를 임의로 판단해 수동으로 quote/urlencode하지 않는다
    # (사용자 지시 7번). 인코딩 자체는 requests.get(..., params=params) 호출
    # 시점에 일어나므로 여기서는 원문 보존만 검증한다.
    params = target._build_params("abc+def/ghi", 1, 3)
    assert params["serviceKey"] == "abc+def/ghi"


def test_redact_helper_matches_serviceKey_case_insensitive():
    mixed_case = "url=https://host/path?ServiceKey=ABCDEF123&pageNo=2"
    lower_case = "url=https://host/path?servicekey=ABCDEF123&pageNo=2"
    assert "ABCDEF123" not in target._redact(mixed_case)
    assert "ABCDEF123" not in target._redact(lower_case)


# --------------------------------------------------------------------------
# 6. --probe / --apply 동시 사용 차단
# --------------------------------------------------------------------------
def test_probe_and_apply_together_blocked(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["update_legal_dong_snapshot.py", "--probe", "--apply"])
    exit_code = target.main()
    assert exit_code == 1


# --------------------------------------------------------------------------
# 7-10. 수량 검증
# --------------------------------------------------------------------------
def test_total_count_zero_blocked():
    page = _api_page([], total_count=0)
    fetcher = FakeFetcher([page])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_total_count_positive_but_first_page_empty_blocked():
    page = _api_page([], total_count=5)
    fetcher = FakeFetcher([page])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_middle_page_empty_before_total_blocked():
    page1 = _api_page([DONG_CHEONHO], total_count=5)
    page2 = _api_page([], total_count=5)  # 아직 1건뿐인데 빈 페이지가 옴
    fetcher = FakeFetcher([page1, page2])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_total_count_value_changes_between_pages_blocked():
    page1 = _api_page([DONG_CHEONHO], total_count=10)
    page2 = _api_page([DONG_ABOLISHED], total_count=999)
    fetcher = FakeFetcher([page1, page2])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_final_aggregate_count_mismatch_blocked():
    # totalCount=2라고 선언했는데 실제로는 3건을 돌려줌(과다 수신)
    page = _api_page([DONG_CHEONHO, DONG_ABOLISHED, DONG_JEONGJA], total_count=2)
    fetcher = FakeFetcher([page])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


# --------------------------------------------------------------------------
# 11-15. region_cd strict 검증
# --------------------------------------------------------------------------
def test_duplicate_region_cd_blocked():
    page = _api_page([DONG_CHEONHO, DONG_CHEONHO], total_count=2)
    fetcher = FakeFetcher([page])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_region_cd_9_digits_blocked():
    bad_row = _row("174010100", "짧은코드동", locatadd_nm="충청북도 어딘가 짧은코드동")  # 9자리
    with pytest.raises(target.SnapshotUpdateError):
        target.normalize_records([bad_row])


def test_region_cd_11_digits_blocked():
    bad_row = _row("117401010011", "긴코드동", locatadd_nm="서울특별시 강동구 긴코드동")  # 11자리 이상
    with pytest.raises(target.SnapshotUpdateError):
        target.normalize_records([bad_row])


def test_region_cd_blank_blocked():
    bad_row = _row("", "공란동", locatadd_nm="서울특별시 강동구 공란동")
    with pytest.raises(target.SnapshotUpdateError):
        target.normalize_records([bad_row])


def test_region_cd_with_letters_blocked():
    bad_row = _row("11740101OO", "문자포함동", locatadd_nm="서울특별시 강동구 문자포함동")  # 대문자 O 포함
    with pytest.raises(target.SnapshotUpdateError):
        target.normalize_records([bad_row])


def test_region_cd_never_zero_padded_or_reconstructed():
    """9자리 코드가 zfill 등으로 조용히 10자리로 보정되지 않는다는 것을
    명시적으로 확인 - 보정이 아니라 예외가 나야 한다."""
    bad_row = _row("174010100", "짧은코드동", locatadd_nm="충청북도 어딘가 짧은코드동")
    try:
        target.normalize_records([bad_row])
        assert False, "9자리 region_cd가 예외 없이 통과됨(자동 보정이 남아있음)"
    except target.SnapshotUpdateError as exc:
        assert "10자리" in str(exc)


# --------------------------------------------------------------------------
# 16-19. 응답 파싱 검증
# --------------------------------------------------------------------------
def test_missing_result_code_blocked():
    page = _api_page([DONG_CHEONHO], total_count=1, omit_result=True)
    fetcher = FakeFetcher([page])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_error_result_code_blocked():
    page = _api_page([DONG_CHEONHO], total_count=1, result_code="ERROR-300")
    fetcher = FakeFetcher([page])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_invalid_json_blocked():
    fetcher = FakeFetcher(["not a json { at all"])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_http_error_blocked():
    fetcher = FakeFetcher([ConnectionError("network down")])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_http_get_captures_and_redacts_error_body_without_extra_request(monkeypatch):
    """_http_get이 HTTPError를 받으면(추가 요청 없이 이미 받은 응답에서)
    HttpProbeFailure로 status/content_type/body_format/body_snippet을 구조화해
    담되, 본문에 인증키가 섞여 있어도 redact된다는 것을 확인한다. 실제 네트워크
    호출은 하지 않는다(requests.get을 fake로 대체)."""
    leaky_body = '{"error":"invalid request for serviceKey=SUPERSECRET123"}'
    fake_response = _FakeResponse(
        status_code=500,
        text=leaky_body,
        headers={"Content-Type": "application/json;charset=UTF-8"},
        reason="Internal Server Error",
    )
    monkeypatch.setattr(target.requests, "get", lambda *a, **k: fake_response)

    with pytest.raises(target.HttpProbeFailure) as excinfo:
        target._http_get({"serviceKey": "REALKEY"})

    exc = excinfo.value
    assert exc.status == 500
    assert exc.content_type == "application/json;charset=UTF-8"
    assert exc.body_format == "JSON"
    assert "SUPERSECRET123" not in exc.body_snippet
    assert "invalid request" in exc.body_snippet  # 본문 내용 자체는 분석을 위해 보존됨
    assert "SUPERSECRET123" not in str(exc)


def test_http_get_error_body_capped_at_4096_bytes(monkeypatch):
    oversized_body = "x" * 5000
    fake_response = _FakeResponse(status_code=500, text=oversized_body, reason="Internal Server Error")
    monkeypatch.setattr(target.requests, "get", lambda *a, **k: fake_response)

    with pytest.raises(target.HttpProbeFailure) as excinfo:
        target._http_get({"serviceKey": "REALKEY"})

    assert len(excinfo.value.body_snippet) <= target._HTTP_ERROR_BODY_LIMIT_BYTES
    assert excinfo.value.content_type == ""  # headers 미지정이어도 예외 없이 빈 문자열로 처리됨


def test_http_get_uses_timeout_30(monkeypatch):
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["timeout"] = timeout
        return _FakeResponse(status_code=200, text=_api_page([DONG_CHEONHO], total_count=1))

    monkeypatch.setattr(target.requests, "get", _fake_get)
    target._http_get({"serviceKey": "plainkey"})
    assert captured["timeout"] == 30


def test_http_get_200_with_mislabeled_html_content_type_still_parses_json(monkeypatch):
    """실제 성공 응답이 Content-Type: text/html인데도 본문은 JSON이었던
    사례(격리 requests probe 결과와 동일) - Content-Type을 신뢰 기준으로 쓰지
    않고 상태 코드(200)만으로 판단해 본문을 그대로 반환해야 한다."""
    body = _api_page([DONG_CHEONHO], total_count=1)
    fake_response = _FakeResponse(status_code=200, text=body, headers={"Content-Type": "text/html;charset=UTF-8"})
    monkeypatch.setattr(target.requests, "get", lambda *a, **k: fake_response)

    result = target._http_get({"serviceKey": "plainkey"})
    parsed = target._parse_api_response(result["text"], page_no=1)
    assert parsed["result_code"] == "INFO-0"


def test_http_get_200_with_invalid_json_body_blocked_downstream(monkeypatch):
    """HTTP 200이어도 본문이 유효한 JSON이 아니면 _parse_api_response에서
    SnapshotUpdateError로 안전하게 중단돼야 한다(_http_get 자체는 본문을
    그대로 반환할 뿐 파싱은 하지 않는다)."""
    fake_response = _FakeResponse(status_code=200, text="not a json { at all")
    monkeypatch.setattr(target.requests, "get", lambda *a, **k: fake_response)

    result = target._http_get({"serviceKey": "plainkey"})
    with pytest.raises(target.SnapshotUpdateError):
        target._parse_api_response(result["text"], page_no=1)


def test_fetch_all_records_wraps_timeout_as_snapshot_update_error():
    fetcher = FakeFetcher([requests.exceptions.Timeout("timed out")])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_fetch_all_records_wraps_connection_error_as_snapshot_update_error():
    fetcher = FakeFetcher([requests.exceptions.ConnectionError("connection refused")])
    with pytest.raises(target.SnapshotUpdateError):
        target.fetch_all_records("fake-key", fetch_fn=fetcher)


def test_run_probe_records_redirect_count(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        page = _api_page([DONG_CHEONHO], total_count=1)
        fetcher = FakeFetcher([{"text": page, "redirect_count": 2}])
        result = target.run_probe("fake-key-for-test", fetch_fn=fetcher)
        assert result["redirect_count"] == 2
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


def test_classify_body_format_variants():
    assert target._classify_body_format("application/json", '{"a":1}') == "JSON"
    assert target._classify_body_format("", '{"a":1}') == "JSON"
    assert target._classify_body_format("text/xml", "<error>x</error>") == "XML"
    assert target._classify_body_format("", "<error>x</error>") == "XML"
    assert target._classify_body_format("text/html", "<html>x</html>") == "HTML"
    assert target._classify_body_format("", "<!DOCTYPE html><html>x</html>") == "HTML"
    assert target._classify_body_format("", "plain error text") == "PLAIN_TEXT"
    assert target._classify_body_format("", "") == "UNKNOWN"


def test_run_probe_cli_reports_structured_fields_on_http_failure(_isolate_snapshot_and_env, capsys):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        failure = target.HttpProbeFailure(
            status=500, reason="Internal Server Error", content_type="text/xml",
            body_snippet="<error>REDACTED-ALREADY</error>", body_format="XML",
        )

        def _raising_fetch(url):
            raise failure

        exit_code = target.run_probe_cli(fetch_fn=_raising_fetch)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "500" in captured.out
        assert "XML" in captured.out
        assert "text/xml" in captured.out
        assert not target.SNAPSHOT_PATH.exists()
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


# --------------------------------------------------------------------------
# 20. 서비스키 redaction
# --------------------------------------------------------------------------
def test_error_message_never_contains_service_key():
    class LeakyError(Exception):
        def __str__(self):
            return "connection failed for https://apis.data.go.kr/x?serviceKey=SECRET123&pageNo=1"

    fetcher = FakeFetcher([LeakyError()])
    with pytest.raises(target.SnapshotUpdateError) as excinfo:
        target.fetch_all_records("fake-key", fetch_fn=fetcher)
    assert "SECRET123" not in str(excinfo.value)


def test_redact_helper_masks_service_key():
    text = "url=https://host/path?serviceKey=ABCDEF123&pageNo=2"
    redacted = target._redact(text)
    assert "ABCDEF123" not in redacted
    assert "serviceKey=***" in redacted


# --------------------------------------------------------------------------
# 21-22. snapshot 무변경 보장
# --------------------------------------------------------------------------
def test_default_run_leaves_existing_snapshot_untouched(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        original_content = json.dumps({"schema_version": 1, "records": [{"legal_code": "9999999999", "full_name": "old"}]})
        target.SNAPSHOT_PATH.write_text(original_content, encoding="utf-8")

        page = _api_page([SIDO_SEOUL, SIGUNGU_GANGDONG, DONG_CHEONHO], total_count=3)
        fetcher = FakeFetcher([page])
        exit_code = target.run(apply=False, fetch_fn=fetcher)
        assert exit_code == 0
        assert target.SNAPSHOT_PATH.read_text(encoding="utf-8") == original_content
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


def test_validation_failure_leaves_snapshot_untouched_even_with_apply(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        original_content = json.dumps({"schema_version": 1, "records": []})
        target.SNAPSHOT_PATH.write_text(original_content, encoding="utf-8")

        dup_rows = [DONG_CHEONHO, DONG_CHEONHO]
        page = _api_page(dup_rows, total_count=2)
        fetcher = FakeFetcher([page])
        exit_code = target.run(apply=True, fetch_fn=fetcher)

        assert exit_code == 1
        assert target.SNAPSHOT_PATH.read_text(encoding="utf-8") == original_content
        assert list(target.SNAPSHOT_PATH.parent.glob("*.backup_*.json")) == []
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


# --------------------------------------------------------------------------
# 23-25. 원자적 교체
# --------------------------------------------------------------------------
def test_apply_atomic_replace_succeeds(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        original_content = json.dumps({"schema_version": 1, "records": []})
        target.SNAPSHOT_PATH.write_text(original_content, encoding="utf-8")

        page = _api_page([SIDO_SEOUL, SIGUNGU_GANGDONG, DONG_CHEONHO], total_count=3)
        fetcher = FakeFetcher([page])
        exit_code = target.run(apply=True, fetch_fn=fetcher)
        assert exit_code == 0

        new_content = json.loads(target.SNAPSHOT_PATH.read_text(encoding="utf-8"))
        assert any(r["legal_code"] == "1174010100" for r in new_content["records"])
        leftover_tmp = list(target.SNAPSHOT_PATH.parent.glob("*.tmp"))
        assert leftover_tmp == []
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


def test_apply_with_no_existing_file_skips_backup(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        assert not target.SNAPSHOT_PATH.exists()
        page = _api_page([SIDO_SEOUL, SIGUNGU_GANGDONG, DONG_CHEONHO], total_count=3)
        fetcher = FakeFetcher([page])
        exit_code = target.run(apply=True, fetch_fn=fetcher)
        assert exit_code == 0
        assert target.SNAPSHOT_PATH.exists()
        assert list(target.SNAPSHOT_PATH.parent.glob("*.backup_*.json")) == []
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


def test_atomic_replace_failure_preserves_existing_snapshot(_isolate_snapshot_and_env, monkeypatch):
    original_content = json.dumps({"schema_version": 1, "records": [{"legal_code": "9999999999", "full_name": "old"}]})
    target.SNAPSHOT_PATH.write_text(original_content, encoding="utf-8")

    def _boom(*args, **kwargs):
        raise OSError("simulated os.replace failure")

    monkeypatch.setattr(target.os, "replace", _boom)

    records = target.normalize_records([SIDO_SEOUL, SIGUNGU_GANGDONG, DONG_CHEONHO])
    with pytest.raises(OSError):
        target._apply_snapshot(records, "2026-01-01T00:00:00+00:00")

    assert target.SNAPSHOT_PATH.read_text(encoding="utf-8") == original_content
    assert list(target.SNAPSHOT_PATH.parent.glob("*.tmp")) == []


def test_backup_content_matches_original_before_replace(_isolate_snapshot_and_env):
    os.environ["DATA_GO_KR_SERVICE_KEY"] = "fake-key-for-test"
    try:
        original_content = json.dumps({"schema_version": 1, "records": []})
        target.SNAPSHOT_PATH.write_text(original_content, encoding="utf-8")

        page = _api_page([SIDO_SEOUL, SIGUNGU_GANGDONG, DONG_CHEONHO], total_count=3)
        fetcher = FakeFetcher([page])
        target.run(apply=True, fetch_fn=fetcher)

        backups = list(target.SNAPSHOT_PATH.parent.glob("*.backup_*.json"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == original_content
    finally:
        os.environ.pop("DATA_GO_KR_SERVICE_KEY", None)


# --------------------------------------------------------------------------
# 26-29. 정규화 - locatadd_nm/locallow_nm 원문 기반 구조적 분리
# (코드 구간으로 부모 행을 조회하지 않는다 - 상위 sido/sigungu 행이 없어도
# dong 행 하나만으로 정규화가 성립해야 한다)
# --------------------------------------------------------------------------
def test_normalization_needs_no_parent_row_present():
    """부모(sido/sigungu) 행을 아예 주지 않아도 dong 행 하나만으로 정규화가
    성립해야 한다 - 코드 구간 기반 부모 조회를 폐기했다는 구조적 증거."""
    records = target.normalize_records([DONG_CHEONHO])
    cheonho = next(r for r in records if r["legal_code"] == "1174010100")
    assert cheonho["sido"] == "서울특별시"
    assert cheonho["sigungu"] == "강동구"
    assert cheonho["eup_myeon_dong"] == "천호동"
    assert cheonho["full_name"] == "서울특별시 강동구 천호동"
    assert cheonho["effective_date"] == "1988-04-01"
    assert cheonho["source_name"] == target.SOURCE_NAME
    assert cheonho["is_active"] is True


def test_ri_level_records_excluded():
    records = target.normalize_records([DONG_CHEONHO, RI_SAMPLE])
    assert all(r["legal_code"] != "4180025321" for r in records)


def test_sejong_no_sigungu_layer_without_parent_sido_row():
    """실제 API 응답에는 세종시 상위 sido 행이 없다(전국 Full Dry Run 감사로
    확인) - SIDO_SEJONG을 빼고 DONG_SEJONG_JOCHIWON 하나만으로도 정규화가
    성공해야 한다."""
    records = target.normalize_records([DONG_SEJONG_JOCHIWON])
    jochiwon = next(r for r in records if r["legal_code"] == "3600010100")
    assert jochiwon["sido"] == "세종특별자치시"
    assert jochiwon["sigungu"] == ""
    assert jochiwon["full_name"] == "세종특별자치시 조치원읍"


def test_sigungu_name_with_space_resolved_correctly():
    records = target.normalize_records([DONG_JEONGJA])
    jeongja = next(r for r in records if r["legal_code"] == "4111110100")
    assert jeongja["sido"] == "경기도"
    assert jeongja["sigungu"] == "수원시 장안구"
    assert jeongja["full_name"] == "경기도 수원시 장안구 정자동"


def test_jeju_special_autonomous_province_structure():
    records = target.normalize_records([DONG_JEJU])
    ildo = next(r for r in records if r["legal_code"] == "5011010100")
    assert ildo["sido"] == "제주특별자치도"
    assert ildo["sigungu"] == "제주시"
    assert ildo["eup_myeon_dong"] == "일도일동"


def test_metropolitan_city_with_autonomous_gu_structure():
    records = target.normalize_records([DONG_HAEUNDAE])
    udong = next(r for r in records if r["legal_code"] == "2635010100")
    assert udong["sido"] == "부산광역시"
    assert udong["sigungu"] == "해운대구"
    assert udong["eup_myeon_dong"] == "우동"


def test_general_do_gun_eup_structure_without_gu():
    records = target.normalize_records([DONG_DAMYANG])
    damyang = next(r for r in records if r["legal_code"] == "4682025000")
    assert damyang["sido"] == "전라남도"
    assert damyang["sigungu"] == "담양군"
    assert damyang["eup_myeon_dong"] == "담양읍"


def test_split_full_name_has_no_region_name_hardcoding():
    """_split_full_name이 세종/제주 등 특정 지역명을 조건문에 하드코딩하지
    않았다는 구조적 증거 - 실제로 존재하지 않는 가상의 지역명으로도 동일한
    토큰 규칙(첫 토큰=sido, 마지막 토큰=eup_myeon_dong, 중간 없으면 sigungu
    빈 문자열)이 성립해야 한다."""
    sido_name, sigungu_name, eup_myeon_dong = target._split_full_name("가상특별시 가상동")
    assert sido_name == "가상특별시"
    assert sigungu_name == ""
    assert eup_myeon_dong == "가상동"

    sido_name2, sigungu_name2, eup_myeon_dong2 = target._split_full_name("가상도 가상시 가상구 가상동")
    assert sido_name2 == "가상도"
    assert sigungu_name2 == "가상시 가상구"
    assert eup_myeon_dong2 == "가상동"


# --------------------------------------------------------------------------
# locallow_nm은 보조 일관성 감사 필드 - eup_myeon_dong은 항상 locatadd_nm
# 마지막 토큰이며, locallow_nm과의 관계는 알려진 변형이면 통과, 설명 불가면
# 차단(§normalization_policy.md 권위 순서)
# --------------------------------------------------------------------------
# 실제 전국 데이터에서 확인된 사례(legal_code=4311110100): locatadd_nm=
# '충청북도 청주시 상당구 영동', locallow_nm='상당구영동'(구분자 없이
# sigungu 마지막 토큰이 접두로 붙음) - 전국 5,067건 중 유일한 사례
# (locallow_mismatch_inventory.json 전수조사로 확인).
DONG_CHEONGJU_SANGDANG = _row(
    "4311110100", "상당구영동", locatadd_nm="충청북도 청주시 상당구 영동"
)


def test_locallow_nm_sigungu_prefix_concatenation_variant_from_real_data():
    records = target.normalize_records([DONG_CHEONGJU_SANGDANG])
    yeongdong = records[0]
    assert yeongdong["sido"] == "충청북도"
    assert yeongdong["sigungu"] == "청주시 상당구"
    assert yeongdong["eup_myeon_dong"] == "영동"


def test_locallow_nm_exact_match_variant():
    row = _row("1174010100", "천호동", locatadd_nm="서울특별시 강동구 천호동")
    records = target.normalize_records([row])
    assert records[0]["eup_myeon_dong"] == "천호동"


def test_locallow_nm_whitespace_only_diff_variant():
    row = _row("1174010100", "천 호동", locatadd_nm="서울특별시 강동구 천호동")
    records = target.normalize_records([row])
    assert records[0]["eup_myeon_dong"] == "천호동"


def test_locallow_nm_ends_with_eup_myeon_dong_but_prefix_differs_from_sigungu():
    """locallow_nm이 읍면동명으로 끝나지만 그 앞부분이 sigungu 마지막
    토큰과 다른 경우도 허용 가능한 보조 불일치 후보다(차단하지 않음) -
    eup_myeon_dong은 어차피 locallow_nm이 아니라 locatadd_nm에서 온다."""
    row = _row("1174010100", "이상한접두천호동", locatadd_nm="서울특별시 강동구 천호동")
    records = target.normalize_records([row])
    assert records[0]["eup_myeon_dong"] == "천호동"
    assert records[0]["sigungu"] == "강동구"


def test_locallow_nm_unexplainable_mismatch_blocked():
    """locallow_nm이 eup_myeon_dong으로 끝나지도 않고 공백 차이도 아니면
    알려진 유형으로 설명할 수 없으므로 즉시 SnapshotUpdateError로 중단한다 -
    production 완화 규칙을 임의로 넓히지 않는다."""
    row = _row("1174010100", "완전히다른명칭", locatadd_nm="서울특별시 강동구 천호동")
    with pytest.raises(target.SnapshotUpdateError):
        target.normalize_records([row])


def test_gwangju_jeonnam_unified_historical_sido_structure():
    """전국 Full Dry Run 감사(missing_sido_analysis.json)에서 광주광역시/
    전라남도는 별도 sido 요약 행이 없고 "전남광주통합특별시"라는 통합 역사
    명칭 하나로 나타남이 확인됐다 - 이 이름에도 세종/제주와 동일한 일반화된
    토큰 규칙이 특별 취급 없이 성립해야 한다(대표 구조 테스트)."""
    row = _row("2911010100", "동명동", locatadd_nm="전남광주통합특별시 동구 동명동")
    records = target.normalize_records([row])
    gwangju = records[0]
    assert gwangju["sido"] == "전남광주통합특별시"
    assert gwangju["sigungu"] == "동구"
    assert gwangju["eup_myeon_dong"] == "동명동"


# --------------------------------------------------------------------------
# 추가: diff 분류 + is_active(UNRESOLVED 명시) + full pagination
# --------------------------------------------------------------------------
def test_full_pagination_collects_all_rows():
    page1 = _api_page(ALL_ROWS[:5], total_count=len(ALL_ROWS))
    page2 = _api_page(ALL_ROWS[5:], total_count=len(ALL_ROWS))
    fetcher = FakeFetcher([page1, page2])
    raw_rows = target.fetch_all_records("fake-key", fetch_fn=fetcher)
    assert len(raw_rows) == len(ALL_ROWS)
    assert len(fetcher.calls) == 2


def test_locat_rm_content_never_affects_is_active():
    """locat_rm에 어떤 문자열이 들어있어도(폐지/말소/임의 문자열 포함) API가
    실제로 반환한 행은 무조건 is_active=True다 - 전국 298건 비공란 표본
    전수 확인 결과 locat_rm은 명칭/관할구역 변경 조례를 인용하는 비고일 뿐
    폐지 상태 플래그가 아니었다(§H 해소). 폐지 감지는 diff 기반
    REMOVED_CANDIDATE에 맡긴다(이 함수의 책임이 아님)."""
    arbitrary_remark_row = _row(
        "1174010200", "임의비고동", locatadd_nm="서울특별시 강동구 임의비고동", locat_rm="아무 문자열이나 말소 폐지 테스트"
    )
    records = target.normalize_records([DONG_CHEONHO, DONG_ABOLISHED, arbitrary_remark_row])
    for r in records:
        assert r["is_active"] is True


def test_normalized_record_schema_fields():
    records = target.normalize_records([DONG_CHEONHO], source_version="2026-01-01T00:00:00+00:00")
    cheonho = records[0]
    assert set(cheonho.keys()) == {
        "legal_code",
        "sido",
        "sigungu",
        "eup_myeon_dong",
        "full_name",
        "is_active",
        "effective_date",
        "source_name",
        "source_version",
    }
    assert cheonho["source_version"] == "2026-01-01T00:00:00+00:00"


def test_diff_report_categorizes_added_renamed_removed_candidate():
    existing_records = [
        {"legal_code": "1174010100", "full_name": "서울특별시 강동구 천호동(구명칭)", "is_active": True},
        {"legal_code": "1174099900", "full_name": "폐지동", "is_active": True},
    ]
    new_records = target.normalize_records([DONG_CHEONHO])
    report = target.build_diff_report(existing_records, new_records)

    assert report["new_count"] == 0  # ADDED 없음(이미 존재하는 코드)
    assert [r["legal_code"] for r in report["renamed_entries"]] == ["1174010100"]  # RENAMED_CANDIDATE
    assert [r["legal_code"] for r in report["removed_candidates"]] == ["1174099900"]  # REMOVED_CANDIDATE


def test_diff_report_all_added_when_no_existing_snapshot():
    """첫 Snapshot에는 비교 대상이 없으므로 모든 정상 수신 읍면동은 ADDED,
    removed=0, renamed=0이어야 한다."""
    new_records = target.normalize_records([DONG_CHEONHO])
    report = target.build_diff_report([], new_records)
    assert report["new_count"] == len(new_records)  # 전부 ADDED
    assert report["renamed_count"] == 0
    assert report["removed_candidate_count"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
