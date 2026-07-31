"""LEGAL-DONG-DEFAULT-1~3, LEGAL-DONG-COUNT-1~3 계약 테스트.

수정 전 실행: 전체 실패 예상 (FAIL == 요구사항 부재 확인).
수정 후 실행: 전체 PASS 확인.
"""
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import ui


class _SimpleVar:
    def __init__(self, value=""):
        self._value = value
    def get(self): return self._value
    def set(self, value): self._value = value


class _StubLoader:
    _DONGS = {
        "금천구": [
            {"legal_code": "1154510100", "eup_myeon_dong": "가산동"},
            {"legal_code": "1154510200", "eup_myeon_dong": "독산동"},
            {"legal_code": "1154510300", "eup_myeon_dong": "시흥동"},
        ],
        "영등포구": [
            {"legal_code": "1156010100", "eup_myeon_dong": "영등포동"},
            {"legal_code": "1156010200", "eup_myeon_dong": "여의도동"},
        ],
    }
    def list_sigungus(self, sido): return list(self._DONGS.keys())
    def list_legal_dongs(self, sido, sigungu): return list(self._DONGS.get(sigungu, []))


class _FakeDropdown:
    def __init__(self): self.values = []; self.state = "normal"
    def configure(self, **kwargs):
        if "values" in kwargs: self.values = kwargs["values"]
        if "state" in kwargs: self.state = kwargs["state"]


def _make_app(*, sigungu="금천구"):
    app = ui.SalesDbCrawlerApp.__new__(ui.SalesDbCrawlerApp)
    app.legal_dong_sido_var = _SimpleVar("서울특별시")
    app.legal_dong_sigungu_var = _SimpleVar(sigungu)
    app.legal_dong_sigungu_dropdown = _FakeDropdown()
    app._legal_dong_loader = _StubLoader()
    app._legal_dong_popup = None
    app._legal_dong_popup_container = None
    app.legal_dong_selected_count_var = _SimpleVar("")
    app.legal_dong_query_count_var = _SimpleVar("")
    app.target_count_var = _SimpleVar(ui._DEFAULT_TARGET_COUNT)
    app.limit_var = _SimpleVar("30")
    app.keyword_input_var = _SimpleVar("카페")
    app.new_open_only_var = _SimpleVar(False)
    app.review_min_var = _SimpleVar("")
    app.review_max_var = _SimpleVar("")
    app.target_count_entry = object()
    return app


# LEGAL-DONG-DEFAULT-1
def test_sigungu_select_selects_all_active_legal_dongs(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    loaded_codes = {item["legal_code"] for item in app._legal_dong_current_items}
    selected_codes = {c for c, v in app.legal_dong_selection_vars.items() if v.get()}
    assert loaded_codes == selected_codes
    assert len(selected_codes) == 3


def test_sigungu_select_count_equals_total_active(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    total = len(app._legal_dong_current_items)
    selected = sum(1 for v in app.legal_dong_selection_vars.values() if v.get())
    assert selected == total == 3


# LEGAL-DONG-DEFAULT-2
def test_switching_sigungu_selects_all_new_sigungu_dongs(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    for code, var in app.legal_dong_selection_vars.items():
        item = next(i for i in app._legal_dong_current_items if i["legal_code"] == code)
        if item["eup_myeon_dong"] != "독산동":
            var.set(False)
    app.legal_dong_sigungu_var.set("영등포구")
    app._reload_legal_dong_checkboxes()
    loaded = {i["legal_code"] for i in app._legal_dong_current_items}
    selected = {c for c, v in app.legal_dong_selection_vars.items() if v.get()}
    assert loaded == selected
    assert len(selected) == 2


def test_previous_partial_selection_does_not_leak(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    old_codes = set(app.legal_dong_selection_vars.keys())
    app.legal_dong_sigungu_var.set("영등포구")
    app._reload_legal_dong_checkboxes()
    new_codes = set(app.legal_dong_selection_vars.keys())
    assert not (old_codes & new_codes)


# LEGAL-DONG-DEFAULT-3
def test_reselecting_previous_sigungu_selects_all_not_partial(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    for code, var in app.legal_dong_selection_vars.items():
        item = next(i for i in app._legal_dong_current_items if i["legal_code"] == code)
        if item["eup_myeon_dong"] != "독산동":
            var.set(False)
    app.legal_dong_sigungu_var.set("영등포구")
    app._reload_legal_dong_checkboxes()
    app.legal_dong_sigungu_var.set("금천구")
    app._reload_legal_dong_checkboxes()
    selected = sum(1 for v in app.legal_dong_selection_vars.values() if v.get())
    assert selected == 3


def test_no_history_cache_attribute_exists(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    for attr in dir(app):
        if "history" in attr.lower() or "cache" in attr.lower():
            val = getattr(app, attr, None)
            if isinstance(val, dict) and any(
                isinstance(k, str) and k.isdigit() and len(k) >= 10 for k in val.keys()
            ):
                pytest.fail(f"구별 선택 history/cache 의심: {attr}")


# LEGAL-DONG-COUNT-1
def test_count_label_shows_all_after_sigungu_change(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    label = app.legal_dong_selected_count_var.get()
    assert "3" in label, f"레이블에 '3' 없음: '{label}'"


def test_count_label_zero_when_no_legal_dongs(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="없는구")
    app._reload_legal_dong_checkboxes()
    label = app.legal_dong_selected_count_var.get()
    assert "0" in label, f"레이블에 '0' 없음: '{label}'"


# LEGAL-DONG-COUNT-2
def test_count_decreases_on_deselect(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    first_code = app._legal_dong_current_items[0]["legal_code"]
    app.legal_dong_selection_vars[first_code].set(False)
    app._on_legal_dong_toggle()
    label = app.legal_dong_selected_count_var.get()
    assert "2" in label, f"해제 후 '2' 없음: '{label}'"


def test_count_increases_on_reselect(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    first_code = app._legal_dong_current_items[0]["legal_code"]
    app.legal_dong_selection_vars[first_code].set(False)
    app._on_legal_dong_toggle()
    app.legal_dong_selection_vars[first_code].set(True)
    app._on_legal_dong_toggle()
    label = app.legal_dong_selected_count_var.get()
    assert "3" in label, f"재선택 후 '3' 없음: '{label}'"


# LEGAL-DONG-COUNT-3
def test_deselect_all_shows_zero(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    app._deselect_all_legal_dongs()
    label = app.legal_dong_selected_count_var.get()
    assert "0" in label, f"전체 해제 후 '0' 없음: '{label}'"


def test_select_all_shows_total(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    app._deselect_all_legal_dongs()
    app._select_all_legal_dongs()
    label = app.legal_dong_selected_count_var.get()
    assert "3" in label, f"전체 선택 후 '3' 없음: '{label}'"


def test_apply_query_plan_matches_selected_count(monkeypatch):
    monkeypatch.setattr(ui.ctk, "BooleanVar", lambda value=False: _SimpleVar(value))
    app = _make_app(sigungu="금천구")
    app._reload_legal_dong_checkboxes()
    for code, var in app.legal_dong_selection_vars.items():
        item = next(i for i in app._legal_dong_current_items if i["legal_code"] == code)
        if item["eup_myeon_dong"] != "독산동":
            var.set(False)
    app._update_legal_dong_summary()
    selected_dongs = app.get_selected_legal_dongs()
    label = app.legal_dong_selected_count_var.get()
    assert len(selected_dongs) == 1
    assert "1" in label


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
