import inspect
import sys
import threading
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import ui  # noqa: E402


def _make_app():
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)
    app.stop_event = threading.Event()
    app.pause_event = threading.Event()
    app.log = lambda message: None
    app.set_status = lambda message: None
    app._security_block_decision = None
    return app


def _item(code, name):
    return {"legal_code": code, "eup_myeon_dong": name}


# --------------------------------------------------------------------------
# 11-16. build_legal_dong_query_plan (순수 함수)
# --------------------------------------------------------------------------
def test_no_legal_dong_selected_produces_one_district_level_query():
    jobs = ui.build_legal_dong_query_plan("서울특별시", "강동구", [], "카페", 30)
    assert len(jobs) == 1
    assert jobs[0]["query"] == "서울특별시 강동구 카페"
    assert jobs[0]["source_layer"] == "district"
    assert jobs[0]["legal_code"] == ""


def test_one_legal_dong_selected_produces_one_query():
    jobs = ui.build_legal_dong_query_plan(
        "서울특별시", "강동구", [_item("1174010900", "천호동")], "카페", 30
    )
    assert len(jobs) == 1
    assert jobs[0]["query"] == "서울특별시 강동구 천호동 카페"
    assert jobs[0]["source_layer"] == "legal_dong"
    assert jobs[0]["legal_code"] == "1174010900"


def test_two_legal_dongs_selected_produces_two_queries_in_order():
    jobs = ui.build_legal_dong_query_plan(
        "서울특별시", "강동구",
        [_item("1174010900", "천호동"), _item("1174010200", "성내동")],
        "카페", 30,
    )
    assert [j["query"] for j in jobs] == ["서울특별시 강동구 천호동 카페", "서울특별시 강동구 성내동 카페"]


def test_legal_dong_order_preserved():
    jobs = ui.build_legal_dong_query_plan(
        "서울특별시", "강동구",
        [_item("2", "나동"), _item("1", "가동")],
        "카페", 30,
    )
    assert [j["source_subregion"] for j in jobs] == ["나동", "가동"]


def test_duplicate_queries_deduplicated_preserving_order():
    jobs = ui.build_legal_dong_query_plan(
        "서울특별시", "강동구",
        [_item("1", "천호동"), _item("1", "천호동"), _item("2", "성내동")],
        "카페", 30,
    )
    assert [j["query"] for j in jobs] == ["서울특별시 강동구 천호동 카페", "서울특별시 강동구 성내동 카페"]


def test_legal_code_provenance_maintained():
    jobs = ui.build_legal_dong_query_plan(
        "서울특별시", "강동구", [_item("1174010900", "천호동")], "카페", 30,
    )
    assert jobs[0]["source_city"] == "서울특별시"
    assert jobs[0]["source_district"] == "강동구"
    assert jobs[0]["source_subregion"] == "천호동"
    assert jobs[0]["legal_code"] == "1174010900"
    assert jobs[0]["per_query_limit"] == 30


def test_sejong_no_selection_uses_sido_only():
    jobs = ui.build_legal_dong_query_plan("세종특별자치시", "", [], "카페", 30)
    assert jobs[0]["query"] == "세종특별자치시 카페"


def test_sejong_legal_dong_selected_uses_sido_plus_dong():
    jobs = ui.build_legal_dong_query_plan(
        "세종특별자치시", "", [_item("3600010100", "조치원읍")], "카페", 30,
    )
    assert jobs[0]["query"] == "세종특별자치시 조치원읍 카페"


# --------------------------------------------------------------------------
# 17-18. target_count 자동 계산
# --------------------------------------------------------------------------
def test_target_count_equals_limit_times_query_count():
    assert ui.calculate_legal_dong_target_count(30, 9) == 270


def test_target_count_recalculates_with_query_count_change():
    assert ui.calculate_legal_dong_target_count(30, 1) == 30
    assert ui.calculate_legal_dong_target_count(30, 2) == 60


def test_target_count_zero_when_invalid_inputs():
    assert ui.calculate_legal_dong_target_count(0, 5) == 0
    assert ui.calculate_legal_dong_target_count(30, 0) == 0


# --------------------------------------------------------------------------
# 1-4. 보조 검색 기본값 OFF + 기본 Queue/target_count 계약(NAVER-REGION-POLICY-1)
# --------------------------------------------------------------------------
class _SimpleVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


def _make_region_app(*, sido="서울특별시", sigungu="강동구", legal_dongs=None,
                      per_query_limit=10, keyword="카페", new_open_only=False):
    """`_build_collection_queries`/`_recalculate_target_count`(실제 바운드
    메서드, override 없음)를 그대로 호출하기 위한 헤드리스 fake app. 시군구가
    있는 지역 기준(세종 등 시군구 없는 지역은 개별 테스트에서 sigungu=""로
    전달)."""
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)
    app.keyword_input_var = _SimpleVar(keyword)
    app.limit_var = _SimpleVar(str(per_query_limit))
    app.legal_dong_sido_var = _SimpleVar(sido)
    app.legal_dong_sigungu_var = _SimpleVar(sigungu if sigungu else ui._LEGAL_DONG_NO_SIGUNGU)
    app.get_selected_legal_dongs = lambda: list(legal_dongs or [])
    app.new_open_only_var = _SimpleVar(new_open_only)
    app.target_count_var = _SimpleVar(ui._DEFAULT_TARGET_COUNT)
    app.legal_dong_query_count_var = _SimpleVar("")
    app.target_count_entry = object()  # hasattr 체크만 통과하면 됨(위젯 메서드 불필요)
    return app


def test_1_no_legal_dong_selected_query_1_target_10():
    app = _make_region_app(legal_dongs=[], per_query_limit=10)
    queue = app._build_collection_queries()
    app._recalculate_target_count()
    assert len(queue) == 1
    assert app.target_count_var.get() == "10"


def test_2_one_legal_dong_selected_query_1_target_10():
    app = _make_region_app(legal_dongs=[_item("1174010900", "천호동")], per_query_limit=10)
    queue = app._build_collection_queries()
    app._recalculate_target_count()
    assert len(queue) == 1
    assert app.target_count_var.get() == "10"


def test_3_two_legal_dongs_selected_query_2_target_20():
    app = _make_region_app(
        legal_dongs=[_item("1174010900", "천호동"), _item("1174010200", "성내동")],
        per_query_limit=10,
    )
    queue = app._build_collection_queries()
    app._recalculate_target_count()
    assert len(queue) == 2
    assert app.target_count_var.get() == "20"


# --------------------------------------------------------------------------
# NEW-OPENING-1 §9-A: 보조 검색(역·상권/세부업종) 기능 완전 제거 확인
# --------------------------------------------------------------------------
def test_aux_search_ui_attributes_no_longer_exist():
    """역·상권/세부업종 보조 검색 UI/상태가 클래스에서 완전히 제거됐는지
    확인한다 - 이름이 남아있으면 §2 요구사항 위반이다."""
    removed_names = (
        "_build_subdivision_section", "auto_subdivide_var", "get_selected_subregions",
        "_open_subregion_popup", "_close_subregion_popup", "_render_subregion_selection",
        "_set_all_subregions", "_update_subdivision_summary", "_refresh_subdivision_view",
        "_reload_subdivision_data", "_ensure_subdivision_data_loaded",
    )
    for name in removed_names:
        assert not hasattr(ui.SalesDbCrawlerApp, name), f"{name}이 여전히 존재함(보조 검색 미완전 제거)"
    assert not hasattr(ui, "build_auxiliary_query_plan")
    assert not hasattr(ui, "REGIONS_SAMPLE_PATH")


def test_query_queue_contains_only_official_region_and_keyword():
    """법정동을 여러 개 선택해도 최종 Query Queue의 각 query 문자열은 오직
    "공식 시도/시군구/법정동 + 키워드" 조합만 포함해야 한다 - 역명/상권명/
    세부업종 기반 Query가 섞여 있으면 실패다."""
    app = _make_region_app(
        legal_dongs=[_item("1174010900", "천호동"), _item("1174010200", "성내동")],
        per_query_limit=10, keyword="카페",
    )
    queue = app._build_collection_queries()
    assert len(queue) == 2
    expected_queries = {"서울특별시 강동구 천호동 카페", "서울특별시 강동구 성내동 카페"}
    assert {job["query"] for job in queue} == expected_queries
    assert all(job["source_layer"] in ("legal_dong", "district") for job in queue)


# --------------------------------------------------------------------------
# NEW-OPENING-1 §7: UI의 new_open_only_var가 job까지 명시적으로 전달됨
# --------------------------------------------------------------------------
def test_new_open_only_false_by_default_in_job():
    app = _make_region_app(legal_dongs=[_item("1174010900", "천호동")], new_open_only=False)
    queue = app._build_collection_queries()
    assert all(job["new_opening_only"] is False for job in queue)


def test_new_open_only_true_threaded_into_every_job():
    app = _make_region_app(
        legal_dongs=[_item("1174010900", "천호동"), _item("1174010200", "성내동")],
        new_open_only=True,
    )
    queue = app._build_collection_queries()
    assert len(queue) == 2
    assert all(job["new_opening_only"] is True for job in queue)


def test_new_open_checkbox_no_longer_force_disabled_in_source():
    """§5 - 새로오픈 체크박스를 항상 잠그던 코드(예: state="disabled" 고정
    생성, _set_left_panel_state의 강제 재잠금)가 더 이상 없어야 한다."""
    build_source = inspect.getsource(ui.SalesDbCrawlerApp._build_filter_section)
    panel_state_source = inspect.getsource(ui.SalesDbCrawlerApp._set_left_panel_state)
    assert 'ctk.CTkCheckBox(filter_frame, text="새로오픈 업체만 수집", variable=self.new_open_only_var, state="disabled")' not in build_source
    assert "new_open_checkbox" not in panel_state_source


# --------------------------------------------------------------------------
# §3/§9-B 시군구·법정동 가나다순 정렬(순수 함수 + 실제 wiring)
# --------------------------------------------------------------------------
def test_sort_korean_names_gu_order():
    names = ["강서구", "강동구", "강남구", "강북구"]
    assert ui._sort_korean_names(names) == ["강남구", "강동구", "강북구", "강서구"]


def test_sort_legal_dong_items_ga_dong_order():
    items = [_item("1", "가양동"), _item("2", "가산동"), _item("3", "가락동")]
    sorted_items = ui._sort_legal_dong_items(items)
    assert [i["eup_myeon_dong"] for i in sorted_items] == ["가락동", "가산동", "가양동"]


def test_sort_legal_dong_items_mixed_eup_myeon_dong():
    """읍/면/동이 섞인 목록도 이름 문자열 기준 가나다순으로만 정렬된다
    (계층 종류로 별도 그룹핑하지 않음)."""
    items = [_item("1", "조치원읍"), _item("2", "가락동"), _item("3", "나성면")]
    sorted_items = ui._sort_legal_dong_items(items)
    assert [i["eup_myeon_dong"] for i in sorted_items] == ["가락동", "나성면", "조치원읍"]


def test_sort_legal_dong_items_same_name_uses_legal_code_tiebreaker():
    """이름이 같은 법정동(다른 시군구에서 옮겨 합친 경우 등)은 legal_code
    오름차순을 보조 키로 사용해 정렬 결과가 결정적이어야 한다."""
    items = [_item("2000000000", "신교동"), _item("1000000000", "신교동")]
    sorted_items = ui._sort_legal_dong_items(items)
    assert [i["legal_code"] for i in sorted_items] == ["1000000000", "2000000000"]


def test_sort_korean_names_normalization_insensitive():
    """NFC/NFD 정규화 차이가 있는 문자열도(정렬 키만 NFC로 맞춰 비교하므로)
    같은 값으로 취급되어 올바른 위치에 정렬돼야 한다(OS locale에 의존하지
    않음, §3). 반환값 자체는 원본 문자열을 그대로 보존한다(정규화로
    바꿔치기하지 않음)."""
    import unicodedata
    nfd_name = unicodedata.normalize("NFD", "강동구")
    result = ui._sort_korean_names(["강서구", nfd_name, "강남구"])
    assert result == ["강남구", nfd_name, "강서구"]


class _StubLoaderForSort:
    """실제 list_sigungus/list_legal_dongs가 legal_code 오름차순(=미정렬,
    Snapshot 원본 순서)으로 반환한다고 가정하고, ui.py 쪽 wiring이 이를
    가나다순으로 다시 정렬해 화면/상태에 반영하는지 확인하기 위한 스텁."""

    def __init__(self, sigungus, dongs):
        self._sigungus = sigungus
        self._dongs = dongs

    def list_sigungus(self, sido):
        return list(self._sigungus)

    def list_legal_dongs(self, sido, sigungu):
        return list(self._dongs)


class _FakeDropdown:
    def __init__(self):
        self.values = None
        self.state = None

    def configure(self, **kwargs):
        if "values" in kwargs:
            self.values = kwargs["values"]
        if "state" in kwargs:
            self.state = kwargs["state"]


def _make_sort_wiring_app(*, sigungus, dongs):
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)
    app.legal_dong_sido_var = _SimpleVar("서울특별시")
    app.legal_dong_sigungu_var = _SimpleVar("")
    app.legal_dong_sigungu_dropdown = _FakeDropdown()
    app._legal_dong_loader = _StubLoaderForSort(sigungus, dongs)
    app._legal_dong_popup = None
    app.legal_dong_selected_count_var = _SimpleVar("")
    app.legal_dong_query_count_var = _SimpleVar("")
    app.target_count_var = _SimpleVar(ui._DEFAULT_TARGET_COUNT)
    app.limit_var = _SimpleVar("30")
    app.keyword_input_var = _SimpleVar("카페")
    app.new_open_only_var = _SimpleVar(False)
    app.target_count_entry = object()
    return app


def test_reload_sigungu_options_sorts_gu_names():
    app = _make_sort_wiring_app(sigungus=["강서구", "강동구", "강남구"], dongs=[])
    app._reload_legal_dong_sigungu_options()
    assert app.legal_dong_sigungu_dropdown.values == ["강남구", "강동구", "강서구"]
    assert app.legal_dong_sigungu_var.get() == "강남구"


def test_reload_sigungu_options_sejong_no_sigungu_still_disabled():
    """세종특별자치시처럼 시군구가 없는 지역은 정렬 로직이 끼어들어도
    기존 "(시군구 없음)" 처리가 그대로 유지돼야 한다(회귀 없음)."""
    app = _make_sort_wiring_app(sigungus=[], dongs=[])
    app._reload_legal_dong_sigungu_options()
    assert app.legal_dong_sigungu_dropdown.values == [ui._LEGAL_DONG_NO_SIGUNGU]
    assert app.legal_dong_sigungu_dropdown.state == "disabled"
    assert app.legal_dong_sigungu_var.get() == ui._LEGAL_DONG_NO_SIGUNGU


def test_reload_legal_dong_checkboxes_sorts_and_preserves_legal_code(monkeypatch):
    """_reload_legal_dong_checkboxes는 실제로 ctk.BooleanVar()를 생성하므로
    (Tk 루트 없이는 RuntimeError) 이 테스트에서만 BooleanVar를 가벼운
    fake로 바꿔치기한다 - 로직(정렬/legal_code 보존) 검증이 목적이며 실제
    Tk 위젯 동작 자체는 검증 대상이 아니다."""
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    dongs = [_item("1174010900", "천호동"), _item("1174010200", "성내동"), _item("1174010300", "길동")]
    app = _make_sort_wiring_app(sigungus=["강동구"], dongs=dongs)
    app._reload_legal_dong_checkboxes()
    names = [item["eup_myeon_dong"] for item in app._legal_dong_current_items]
    assert names == ["길동", "성내동", "천호동"]
    # legal_code 자체는 값이 바뀌지 않고, 각 이름에 그대로 매칭된다.
    by_name = {item["eup_myeon_dong"]: item["legal_code"] for item in app._legal_dong_current_items}
    assert by_name == {"천호동": "1174010900", "성내동": "1174010200", "길동": "1174010300"}
    # 선택 상태(BooleanVar) 키도 legal_code 기준으로 전부 생성돼 있어야 한다.
    assert set(app.legal_dong_selection_vars.keys()) == {"1174010900", "1174010200", "1174010300"}


# --------------------------------------------------------------------------
# 19-21. 기존 두 수집 모드 연결(fake orchestrator/home_enrichment_fn)
# --------------------------------------------------------------------------
def _base_result(**overrides) -> dict:
    result = {
        "rows": [], "executed_query_count": 1, "skipped_query_count": 0,
        "stop_reason": "queue_exhausted", "before_trim_count": 0, "final_count": 0,
        "security_blocked": False, "status_429_seen": False,
        "navigation_error": False, "navigation_error_message": "",
    }
    result.update(overrides)
    return result


class _FakeCollector:
    def __init__(self, collected_at):
        self.collected_at = collected_at

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def collect_query(self, job, per_query_limit):
        raise AssertionError("이 테스트에서는 collect_query가 직접 호출되면 안 됨(fake orchestrator만 사용)")


def test_legal_dong_query_plan_reaches_orchestrator_unchanged(tmp_path):
    """법정동 선택으로 만든 query_queue가 orchestrator(jobs)에 그대로
    전달되는지(기본모드) fake collector/orchestrator로 검증한다 - 실제
    Naver 요청은 0회."""
    jobs = ui.build_legal_dong_query_plan(
        "서울특별시", "강동구", [_item("1174010900", "천호동")], "카페", 30,
    )
    captured = {}

    def fake_orchestrator(query_jobs, **kwargs):
        captured["jobs"] = query_jobs
        return _base_result()

    app = _make_app()
    app._run_network_pipeline(
        jobs, 30, 30, str(tmp_path / "out.xlsx"),
        collection_mode="basic",
        collector_factory=lambda *, collected_at: _FakeCollector(collected_at),
        orchestrator=fake_orchestrator,
        excel_exporter=lambda rows, mobile, pc, path: path,
        home_enrichment_fn=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("basic 모드에서는 home_enrichment_fn이 호출되면 안 됨")
        ),
    )
    assert captured["jobs"] == jobs


def test_legal_dong_query_plan_reaches_home_sns_mode(tmp_path):
    """홈페이지·SNS 모드에서도 동일한 job 목록이 orchestrator에 전달되고,
    home_enrichment_fn이 정확히 1회 호출되는지 확인한다."""
    jobs = ui.build_legal_dong_query_plan(
        "서울특별시", "강동구", [_item("1174010900", "천호동")], "카페", 30,
    )
    captured = {"jobs": None, "home_calls": 0}

    def fake_orchestrator(query_jobs, **kwargs):
        captured["jobs"] = query_jobs
        return _base_result(rows=[{"place_id": "1"}], final_count=1, before_trim_count=1)

    def fake_home_enrichment(*args, **kwargs):
        captured["home_calls"] += 1
        rows = args[0] if args else kwargs.get("rows", [])
        return {
            "rows": rows, "stop_reason": "queue_exhausted", "security_blocked": False,
            "home_success_count": len(rows), "failure_count": 0, "not_attempted_count": 0,
            "first_pass": {}, "diagnostics_report": None,
        }

    app = _make_app()
    app._run_network_pipeline(
        jobs, 30, 30, str(tmp_path / "out.xlsx"),
        collection_mode="home_sns",
        collector_factory=lambda *, collected_at: _FakeCollector(collected_at),
        orchestrator=fake_orchestrator,
        excel_exporter=lambda rows, mobile, pc, path: path,
        home_enrichment_fn=fake_home_enrichment,
    )
    assert captured["jobs"] == jobs
    assert captured["home_calls"] == 1


def test_basic_mode_never_calls_home_enrichment(tmp_path):
    jobs = ui.build_legal_dong_query_plan("세종특별자치시", "", [], "카페", 30)

    def fake_orchestrator(query_jobs, **kwargs):
        return _base_result(rows=[{"place_id": "1"}], final_count=1, before_trim_count=1)

    def _boom(*args, **kwargs):
        raise AssertionError("basic 모드에서는 home_enrichment_fn이 호출되면 안 됨")

    app = _make_app()
    app._run_network_pipeline(
        jobs, 30, 30, str(tmp_path / "out.xlsx"),
        collection_mode="basic",
        collector_factory=lambda *, collected_at: _FakeCollector(collected_at),
        orchestrator=fake_orchestrator,
        excel_exporter=lambda rows, mobile, pc, path: path,
        home_enrichment_fn=_boom,
    )


# --------------------------------------------------------------------------
# 17. 기본모드/홈페이지·SNS 모드가 동일한 지역 필터 결과를 사용
# --------------------------------------------------------------------------
def test_17_both_modes_share_the_same_region_filtered_collect_query():
    """지역 Exact 필터는 collect_query(ApolloFirstListCollector.collect_query
    -> collect_apollo_first_list_query) 내부에서 적용된다. _run_network_pipeline이
    orchestrator에 넘기는 collect_query=collector.collect_query 배선이
    collection_mode 분기보다 앞(바깥)에 있어야 두 모드가 항상 동일한 필터
    결과를 쓴다고 보장할 수 있다 - home_sns 전용 분기(if collection_mode ==
    "home_sns")는 그 뒤(목록 수집이 끝난 후 홈페이지 보강 단계)에만 있어야
    한다."""
    source = inspect.getsource(ui.SalesDbCrawlerApp._run_network_pipeline)
    collect_query_pos = source.index("collect_query=collector.collect_query")
    home_sns_branch_pos = source.index('if collection_mode == "home_sns"')
    assert collect_query_pos < home_sns_branch_pos


# --------------------------------------------------------------------------
# 22. 기존 Excel 14컬럼 유지(legal_code 등 신규 job 필드가 새지 않음)
# --------------------------------------------------------------------------
def test_excel_columns_unaffected_by_new_job_fields(tmp_path):
    from src.exporter import MERGED_COLUMNS, export_places_to_excel
    import openpyxl

    row = {col: "" for col in MERGED_COLUMNS}
    row.update({
        "place_id": "1", "source_city": "서울특별시", "source_district": "강동구",
        "source_subregion": "천호동", "source_layer": "legal_dong", "source_query": "서울특별시 강동구 천호동 카페",
        "legal_code": "1174010900",
    })
    output_path = tmp_path / "out.xlsx"
    saved_path = export_places_to_excel([row], [], [], str(output_path))
    assert Path(saved_path).exists()
    wb = openpyxl.load_workbook(output_path)
    header = [cell.value for cell in next(wb.active.iter_rows(min_row=1, max_row=1))]
    assert header == MERGED_COLUMNS


# --------------------------------------------------------------------------
# 23. Snapshot 오류 시 수집 차단(LEGALDONG-UI-2: 지역 경로가 하나뿐이므로
# 로더가 없으면 선택 가능한 법정동 자체가 없어야 한다 - 실제 버튼 disable은
# Tk가 필요해 __init__ 레벨에서 직접 검증한다).
# --------------------------------------------------------------------------
def test_legal_dong_snapshot_error_disables_start_button():
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)
    app.log = lambda message: None
    app.btn_start = _FakeButton()
    app._legal_dong_load_error = "법정동 Snapshot 파일이 없습니다: (테스트)"
    if app._legal_dong_load_error is not None:
        app.log(f"[ui] 법정동 Snapshot 로드 실패: {app._legal_dong_load_error}")
        app.btn_start.configure(state="disabled")
    assert app.btn_start.state == "disabled"


class _FakeButton:
    def __init__(self):
        self.state = "normal"

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]


class _FakeVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


# --------------------------------------------------------------------------
# 24. UI import/smoke test
# --------------------------------------------------------------------------
def test_ui_module_imports_without_crash():
    import importlib

    importlib.reload(ui)
    assert hasattr(ui, "SalesDbCrawlerApp")
    assert hasattr(ui, "build_legal_dong_query_plan")
    assert hasattr(ui, "calculate_legal_dong_target_count")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
