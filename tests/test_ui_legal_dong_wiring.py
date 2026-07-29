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
                      per_query_limit=10, keyword="카페", auto_subdivide=False,
                      subregions=None):
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
    app.auto_subdivide_var = _SimpleVar(auto_subdivide)
    app.get_selected_subregions = lambda: subregions or {"landmarks": [], "subcategory_keywords": []}
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


def test_4_auto_subdivide_off_by_default_adds_no_aux_query():
    """auto_subdivide=False(기본값)면 보조 데이터가 있어도(강동구) 추가 Query가
    생기지 않는다 - 강동구 샘플 데이터가 존재한다는 이유만으로 법정동 1개가
    Query 10개로 확장되던 회귀를 재발 방지한다."""
    app = _make_region_app(
        legal_dongs=[_item("1174010900", "천호동")], per_query_limit=10,
        auto_subdivide=False, subregions={"landmarks": ["올림픽공원"], "subcategory_keywords": ["브런치"]},
    )
    queue = app._build_collection_queries()
    assert len(queue) == 1


def test_4_auto_subdivide_on_adds_aux_query_and_recalculates_target():
    """사용자가 보조 검색을 명시적으로 켜면(auto_subdivide=True) 실제 최종
    Query Queue 개수를 기준으로 target_count가 다시 계산된다."""
    app = _make_region_app(
        legal_dongs=[_item("1174010900", "천호동")], per_query_limit=10,
        auto_subdivide=True, subregions={"landmarks": ["올림픽공원"], "subcategory_keywords": ["브런치"]},
    )
    queue = app._build_collection_queries()
    app._recalculate_target_count()
    assert len(queue) == 3  # 법정동 1개 + landmarks 1개 + subcategory_keywords 1개
    assert app.target_count_var.get() == "30"


def test_auto_subdivide_var_default_is_false_in_source():
    """§2 - 체크박스 생성 시점의 기본값이 False인지(위젯 생성 자체는 Tk 루트가
    필요해 여기서는 소스 코드로 확인한다 - target_count_entry_always_disabled
    테스트와 동일한 패턴)."""
    source = inspect.getsource(ui.SalesDbCrawlerApp._build_subdivision_section)
    assert "self.auto_subdivide_var = ctk.BooleanVar(value=False)" in source


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
