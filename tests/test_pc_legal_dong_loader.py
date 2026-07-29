import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.legal_dong_loader import (  # noqa: E402
    LegalDongSnapshotError,
    LegalDongSnapshotLoader,
    default_snapshot_path,
)

REAL_SNAPSHOT_PATH = ROOT_DIR / "data" / "legal_dong_snapshot.json"


@pytest.fixture(scope="module")
def loader():
    return LegalDongSnapshotLoader(REAL_SNAPSHOT_PATH)


def _write_snapshot(tmp_path, payload) -> Path:
    path = tmp_path / "legal_dong_snapshot.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _record(code, sido, sigungu, eup_myeon_dong, *, is_active=True):
    return {
        "legal_code": code,
        "sido": sido,
        "sigungu": sigungu,
        "eup_myeon_dong": eup_myeon_dong,
        "full_name": " ".join(part for part in (sido, sigungu, eup_myeon_dong) if part),
        "is_active": is_active,
        "effective_date": "",
        "source_name": "test",
        "source_version": "",
    }


# --------------------------------------------------------------------------
# 1-7. 실제 Snapshot 기반 검증
# --------------------------------------------------------------------------
def test_snapshot_loads_5067_active_records(loader):
    assert len(loader._records) == 5067


def test_unique_sido_count_is_16(loader):
    assert len(loader.list_sidos()) == 16


def test_snapshot_file_hash_unchanged():
    """§20 - 이번 라운드(Provider Alias/Exact 필터 구현)는 공식 Snapshot을
    전혀 수정하지 않는다. 2026-07-29 실측 시점에 확인한 해시와 비교해 파일
    내용이 그대로임을 증명한다."""
    digest = hashlib.sha256(REAL_SNAPSHOT_PATH.read_bytes()).hexdigest()
    assert digest == "eacf8307d7ffd363f03b84ceac7470dba7c555768c1362c04f6e5cd6194af65c"


def test_no_duplicate_legal_code(loader):
    codes = [r["legal_code"] for r in loader._records]
    assert len(codes) == len(set(codes))


def test_only_active_records_exposed(loader):
    assert all(r["is_active"] is True for r in loader._records)


def test_seoul_gangdong_cheonho_exists(loader):
    assert "강동구" in loader.list_sigungus("서울특별시")
    dongs = loader.list_legal_dongs("서울특별시", "강동구")
    assert any(d["eup_myeon_dong"] == "천호동" for d in dongs)


def test_complex_sigungu_supported(loader):
    """경기도 수원시 장안구처럼 2단어로 결합된 시군구도 그대로 조회 가능해야 한다."""
    assert "수원시 장안구" in loader.list_sigungus("경기도")
    dongs = loader.list_legal_dongs("경기도", "수원시 장안구")
    assert len(dongs) > 0


def test_sejong_sigungu_is_empty_list(loader):
    """세종특별자치시는 list_sigungus가 빈 리스트를 반환해야 한다(코드에
    "세종"이라는 이름을 하드코딩하지 않고 데이터 구조로만 판단)."""
    assert loader.list_sigungus("세종특별자치시") == []
    dongs = loader.list_legal_dongs("세종특별자치시", "")
    assert len(dongs) > 0


def test_find_by_legal_code(loader):
    dongs = loader.list_legal_dongs("서울특별시", "강동구")
    cheonho = next(d for d in dongs if d["eup_myeon_dong"] == "천호동")
    found = loader.find_by_legal_code(cheonho["legal_code"])
    assert found is not None
    assert found["eup_myeon_dong"] == "천호동"
    assert loader.find_by_legal_code("0000000000") is None


# --------------------------------------------------------------------------
# 8-10. 오류 처리(임시 파일)
# --------------------------------------------------------------------------
def test_missing_snapshot_file_raises(tmp_path):
    with pytest.raises(LegalDongSnapshotError):
        LegalDongSnapshotLoader(tmp_path / "does_not_exist.json")


def test_corrupted_json_raises(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("not a json {", encoding="utf-8")
    with pytest.raises(LegalDongSnapshotError):
        LegalDongSnapshotLoader(path)


def test_duplicate_legal_code_in_snapshot_raises(tmp_path):
    payload = {
        "schema_version": 1,
        "records": [
            _record("1100000001", "서울특별시", "강동구", "천호동"),
            _record("1100000001", "서울특별시", "강동구", "성내동"),
        ],
    }
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(LegalDongSnapshotError):
        LegalDongSnapshotLoader(path)


def test_wrong_schema_version_raises(tmp_path):
    payload = {"schema_version": 999, "records": []}
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(LegalDongSnapshotError):
        LegalDongSnapshotLoader(path)


def test_missing_required_field_raises(tmp_path):
    bad_record = _record("1100000001", "서울특별시", "강동구", "천호동")
    del bad_record["is_active"]
    payload = {"schema_version": 1, "records": [bad_record]}
    path = _write_snapshot(tmp_path, payload)
    with pytest.raises(LegalDongSnapshotError):
        LegalDongSnapshotLoader(path)


def test_inactive_records_excluded(tmp_path):
    payload = {
        "schema_version": 1,
        "records": [
            _record("1100000001", "서울특별시", "강동구", "천호동", is_active=True),
            _record("1100000002", "서울특별시", "강동구", "성내동", is_active=False),
        ],
    }
    path = _write_snapshot(tmp_path, payload)
    loader = LegalDongSnapshotLoader(path)
    names = [d["eup_myeon_dong"] for d in loader.list_legal_dongs("서울특별시", "강동구")]
    assert names == ["천호동"]


def test_default_snapshot_path_points_to_data_dir():
    assert default_snapshot_path().name == "legal_dong_snapshot.json"
    assert default_snapshot_path().parent.name == "data"


def test_default_snapshot_path_dev_mode_is_project_root_data(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    path = default_snapshot_path()
    assert path == ROOT_DIR / "data" / "legal_dong_snapshot.json"


def test_default_snapshot_path_frozen_mode_uses_meipass(monkeypatch, tmp_path):
    """PyInstaller 배포 실행(§8. PyInstaller 설정) 환경을 흉내낸다 -
    sys.frozen=True + sys._MEIPASS가 있으면 그 경로 기준 data/를 찾아야
    한다(NaverPlaceSalesDBCollector.spec의 datas=[('data/legal_dong_snapshot.json','data')]
    가 이 경로로 번들을 풀어준다는 전제)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    path = default_snapshot_path()
    assert path == tmp_path / "data" / "legal_dong_snapshot.json"


# --------------------------------------------------------------------------
# PyInstaller .spec - Git 추적 + Snapshot datas 포함(§8)
# --------------------------------------------------------------------------
SPEC_PATH = ROOT_DIR / "NaverPlaceSalesDBCollector.spec"


def test_spec_file_is_not_gitignored():
    """*.spec은 기본적으로 .gitignore 대상이지만(다른 임시 spec은 계속
    제외), NaverPlaceSalesDBCollector.spec만 예외로 추적 가능해야 한다
    (실제 git add/commit은 사용자 승인 없이 수행하지 않으므로, 여기서는
    "추적 가능한 상태"만 확인한다 - `git check-ignore`가 이 파일을 더 이상
    무시 대상으로 보지 않으면 exit code 1을 반환한다)."""
    import subprocess

    result = subprocess.run(
        ["git", "check-ignore", "-q", "NaverPlaceSalesDBCollector.spec"],
        cwd=ROOT_DIR, capture_output=True, text=True,
    )
    assert result.returncode == 1, "NaverPlaceSalesDBCollector.spec이 여전히 gitignore 대상임"

    other_spec_result = subprocess.run(
        ["git", "check-ignore", "-q", "some_other_temp.spec"],
        cwd=ROOT_DIR, capture_output=True, text=True,
    )
    assert other_spec_result.returncode == 0, "다른 임시 .spec 파일까지 예외 처리되면 안 됨(*.spec 기본 규칙 유지 확인)"


def test_spec_includes_legal_dong_snapshot_in_datas():
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert "legal_dong_snapshot.json" in text
    assert "'data'" in text or '"data"' in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
