from pathlib import Path
import sys


# PoC-9A: src/pc/vertical_presets.py 검증용 standalone 스크립트(live 없음).
# data/verticals_kr.json은 저장소에 실제로 포함된 파일을 그대로 읽어 검증한다
# (test_pc_region_data.py와 동일한 방침 - 실제 파일 구조가 바뀌면 이 테스트도
# 즉시 깨져야 하므로 fixture로 별도 복제하지 않음).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.vertical_presets import get_vertical_preset, load_vertical_presets

VERTICALS_PATH = ROOT_DIR / "data" / "verticals_kr.json"


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


def check_load_verticals_kr_all_entries(reporter: ValidationReporter) -> None:
    presets = load_vertical_presets(VERTICALS_PATH)
    ok = (
        set(presets.keys()) == {"카페", "음식점", "한식", "미용실"}
        and presets["카페"]["type"] == "defined"
        and presets["음식점"]["type"] == "umbrella"
        and presets["한식"]["type"] == "defined"
        and presets["미용실"]["type"] == "niche"
    )
    if ok:
        reporter.pass_("verticals_kr.json에서 카페/음식점/한식/미용실 4개 항목과 각 type을 정확히 읽음")
    else:
        reporter.fail(f"verticals_kr.json 로드 결과가 예상과 다름: {presets}")


def check_get_vertical_preset_defined_type(reporter: ValidationReporter) -> None:
    presets = load_vertical_presets(VERTICALS_PATH)
    preset = get_vertical_preset(presets, "한식")
    ok = (
        preset is not None
        and preset["type"] == "defined"
        and preset["subcategories"] == ["백반", "국밥", "찌개"]
        and preset.get("parent_keyword") == "음식점"
    )
    if ok:
        reporter.pass_("get_vertical_preset('한식')이 defined type과 세부업종/parent_keyword를 정확히 반환")
    else:
        reporter.fail(f"'한식' preset 조회 결과가 예상과 다름: {preset}")


def check_get_vertical_preset_umbrella_type(reporter: ValidationReporter) -> None:
    presets = load_vertical_presets(VERTICALS_PATH)
    preset = get_vertical_preset(presets, "음식점")
    ok = (
        preset is not None
        and preset["type"] == "umbrella"
        and preset["strategy"] == "split_to_subverticals"
        and "한식" in preset["subverticals"]
    )
    if ok:
        reporter.pass_("get_vertical_preset('음식점')이 umbrella type과 subverticals를 정확히 반환")
    else:
        reporter.fail(f"'음식점' preset 조회 결과가 예상과 다름: {preset}")


def check_get_vertical_preset_unknown_keyword_returns_none(reporter: ValidationReporter) -> None:
    presets = load_vertical_presets(VERTICALS_PATH)
    preset = get_vertical_preset(presets, "존재하지않는업종")
    if preset is None:
        reporter.pass_("존재하지 않는 업종 키워드는 예외 없이 None을 반환함")
    else:
        reporter.fail(f"미존재 키워드 처리 결과가 예상과 다름: {preset}")


def check_get_vertical_preset_non_dict_input_returns_none(reporter: ValidationReporter) -> None:
    if get_vertical_preset(None, "한식") is None and get_vertical_preset([], "한식") is None:
        reporter.pass_("presets가 dict가 아니면(None/list) 예외 없이 None을 반환함")
    else:
        reporter.fail("presets가 dict가 아닐 때 방어 처리가 예상과 다름")


def check_load_missing_file_raises(reporter: ValidationReporter) -> None:
    missing_path = ROOT_DIR / "data" / "does_not_exist_verticals.json"
    try:
        load_vertical_presets(missing_path)
        reporter.fail("존재하지 않는 파일 경로인데 예외가 발생하지 않음")
    except FileNotFoundError:
        reporter.pass_("존재하지 않는 파일 경로는 FileNotFoundError를 그대로 전파함")


def main() -> int:
    reporter = ValidationReporter()

    check_load_verticals_kr_all_entries(reporter)
    check_get_vertical_preset_defined_type(reporter)
    check_get_vertical_preset_umbrella_type(reporter)
    check_get_vertical_preset_unknown_keyword_returns_none(reporter)
    check_get_vertical_preset_non_dict_input_returns_none(reporter)
    check_load_missing_file_raises(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
