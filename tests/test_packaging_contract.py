# build.bat/NaverPlaceSalesDBCollector.spec의 배포 계약을 정적으로 검증한다.
# 실제 PyInstaller 빌드나 네트워크 요청은 하지 않는다 - 텍스트/AST 기반 계약
# 검사만 수행한다.
#
# data/regions_kr_sample.json은 4910d14("기능: 새로오픈 전용 수집 및 지역
# 선택 구조 정리")에서 역/상권 보조 검색 기능과 함께 이미 삭제됐다(공식
# 법정동 체계로 완전 대체). 저장소에 존재하지 않는 파일을 spec이 번들해야
#한다는 계약은 만들 수 없으므로, 대신 "존재하지 않는 이 파일을 spec이
# 실수로 요구하지 않는지"를 검증한다(요구하면 파일이 없어 빌드가 즉시
# 실패한다).
import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BUILD_BAT_PATH = ROOT_DIR / "build.bat"
SPEC_PATH = ROOT_DIR / "NaverPlaceSalesDBCollector.spec"


def _normalize(text: str) -> str:
    """경로 구분자·대소문자·공백 차이를 흡수한다(취약한 문자열 grep 방지)."""
    return " ".join(text.replace("\\", "/").lower().split())


def _build_bat_lines() -> list[str]:
    return BUILD_BAT_PATH.read_text(encoding="utf-8").splitlines()


def _build_bat_pyinstaller_lines() -> list[str]:
    """build.bat에서 실제로 pyinstaller를 호출하는 줄만 골라낸다(echo/REM 제외)."""
    lines = []
    for raw_line in _build_bat_lines():
        stripped = raw_line.strip()
        if not stripped or stripped.upper().startswith("REM"):
            continue
        normalized = _normalize(stripped)
        if "pyinstaller" in normalized and not normalized.startswith("echo"):
            lines.append(normalized)
    return lines


def _spec_datas_literal_tuples() -> list[tuple]:
    """spec의 `datas += [(...)]` augmented assignment에서 리터럴 튜플만 추출한다.
    collect_all() 등 함수 호출로 채워지는 항목은 정적으로 알 수 없으므로 대상이
    아니다 - 여기서 검증하려는 것은 "명시적으로 지정한 데이터 파일"이다."""
    tree = ast.parse(SPEC_PATH.read_text(encoding="utf-8"))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "datas":
            if isinstance(node.value, ast.List):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Tuple) and len(elt.elts) == 2:
                        src, dst = elt.elts
                        src_val = src.value if isinstance(src, ast.Constant) else None
                        dst_val = dst.value if isinstance(dst, ast.Constant) else None
                        result.append((src_val, dst_val))
    return result


def _spec_exe_kwarg(name: str):
    tree = ast.parse(SPEC_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "EXE":
            for kw in node.keywords:
                if kw.arg == name and isinstance(kw.value, ast.Constant):
                    return kw.value.value
    return None


def test_build_bat_uses_tracked_spec_file():
    """build.bat이 추적 중인 spec 파일명을 PyInstaller 호출 인자로 사용해야 한다."""
    spec_name = _normalize("NaverPlaceSalesDBCollector.spec")
    lines = _build_bat_pyinstaller_lines()
    assert any(spec_name in line for line in lines), (
        "build.bat의 pyinstaller 호출 라인 어디에도 "
        "NaverPlaceSalesDBCollector.spec이 없다"
    )


def test_build_bat_does_not_delete_spec_file():
    """build.bat이 spec 파일을 삭제하는 명령을 포함하면 안 된다.

    `del`/`erase`는 `if exist ... del ...`처럼 조건문 뒤에 올 수 있으므로
    줄 시작이 아니라 공백으로 나뉜 토큰 단위로 검사한다(startswith만
    쓰면 이 형태를 놓친다)."""
    spec_name = _normalize("NaverPlaceSalesDBCollector.spec")
    for raw_line in _build_bat_lines():
        normalized = _normalize(raw_line)
        tokens = normalized.split(" ")
        if "del" in tokens or "erase" in tokens:
            assert spec_name not in normalized, f"spec 파일을 삭제하는 라인 발견: {raw_line!r}"


def test_build_bat_does_not_build_app_py_directly():
    """PyInstaller 호출이 app.py를 직접 입력으로 받지 않아야 한다(spec을 거쳐야 함)."""
    app_py = _normalize("app.py")
    lines = _build_bat_pyinstaller_lines()
    for line in lines:
        assert app_py not in line, f"pyinstaller가 app.py를 직접 받는 라인 발견: {line!r}"


def test_build_bat_uses_project_venv_python():
    """PyInstaller 호출이 프로젝트 .venv의 python.exe -m PyInstaller 형태여야 한다."""
    venv_python = _normalize(".venv\\Scripts\\python.exe")
    lines = _build_bat_pyinstaller_lines()
    assert lines, "build.bat에서 pyinstaller 호출 라인을 찾지 못했다"
    assert any(venv_python in line and "-m pyinstaller" in line for line in lines), (
        f"pyinstaller 호출 라인이 '{venv_python} -m PyInstaller' 형태가 아니다: {lines}"
    )


def test_spec_includes_legal_dong_snapshot():
    """spec이 data/legal_dong_snapshot.json을 명시적으로 번들해야 한다."""
    normalized_pairs = [
        (_normalize(src) if src else src, _normalize(dst) if dst else dst)
        for src, dst in _spec_datas_literal_tuples()
    ]
    target = (_normalize("data/legal_dong_snapshot.json"), _normalize("data"))
    assert target in normalized_pairs, (
        f"spec의 datas에 data/legal_dong_snapshot.json 번들 항목이 없다: {normalized_pairs}"
    )


def test_data_regions_kr_sample_resource_absent_and_not_referenced_by_spec():
    """data/regions_kr_sample.json은 4910d14에서 이미 삭제된 리소스다(역/상권
    보조 검색 기능 제거와 함께 제거됨, 공식 법정동 체계로 완전 대체).
    존재하지 않는 이 파일을 spec이 실수로 요구하면 안 된다(요구하는 순간
    빌드가 파일 없음으로 즉시 실패한다) - 이 회귀를 잡는 것이 실제 안전장치다."""
    resource_path = ROOT_DIR / "data" / "regions_kr_sample.json"
    assert not resource_path.exists(), (
        "data/regions_kr_sample.json이 다시 존재한다 - 이 테스트를 "
        "spec 번들 포함 검증으로 되돌려야 한다"
    )
    spec_text_normalized = _normalize(SPEC_PATH.read_text(encoding="utf-8"))
    assert "regions_kr_sample" not in spec_text_normalized, (
        "spec이 존재하지 않는 data/regions_kr_sample.json을 참조한다"
    )


def test_spec_does_not_include_dotenv():
    """spec이 .env를 데이터 파일로 번들하면 안 된다(API 키 등 비밀 유출 방지)."""
    normalized_pairs = [
        _normalize(src) for src, _dst in _spec_datas_literal_tuples() if src
    ]
    assert not any(".env" in pair for pair in normalized_pairs), (
        f"spec의 datas에 .env 관련 항목이 있다: {normalized_pairs}"
    )
    spec_text_normalized = _normalize(SPEC_PATH.read_text(encoding="utf-8"))
    assert ".env" not in spec_text_normalized, "spec 텍스트 어딘가에 .env가 언급되어 있다"


def test_spec_exe_name_is_naver_place_sales_db_collector():
    """spec의 EXE 이름이 NaverPlaceSalesDBCollector여야 한다."""
    name_value = _spec_exe_kwarg("name")
    assert name_value is not None, "spec의 EXE(...) 호출에서 name= 인자를 찾지 못했다"
    assert _normalize(name_value) == _normalize("NaverPlaceSalesDBCollector"), (
        f"spec의 EXE 이름이 예상과 다르다: {name_value!r}"
    )
