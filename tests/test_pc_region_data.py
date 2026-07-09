from pathlib import Path
import sys


# PoC-6: src/pc/region_data.py 검증용 standalone 스크립트(live 없음).
# data/regions_kr_sample.json은 저장소에 실제로 포함된 파일을 그대로 읽어
# 검증한다(fixture로 별도 복제하지 않음 - 실제 파일 구조가 바뀌면 이 테스트도
# 즉시 깨져야 하므로).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pc.region_data import load_region_layers

SAMPLE_PATH = ROOT_DIR / "data" / "regions_kr_sample.json"


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


def check_load_gangdong_sample_layers(reporter: ValidationReporter) -> None:
    layers = load_region_layers(SAMPLE_PATH, "서울특별시", "강동구")
    ok = (
        len(layers["legal_dongs"]) == 9
        and "천호동" in layers["legal_dongs"]
        and len(layers["landmarks"]) == 6
        and "천호역" in layers["landmarks"]
        and layers["subcategory_keywords"] == ["디저트카페", "브런치카페", "베이커리카페"]
    )
    if ok:
        reporter.pass_("regions_kr_sample.json에서 강동구 법정동 9개/역상권 6개/세부업종 3개를 정확히 읽음")
    else:
        reporter.fail(f"강동구 샘플 레이어 로드 결과가 예상과 다름: {layers}")


def check_load_unknown_city_gu_returns_empty_layers(reporter: ValidationReporter) -> None:
    """존재하지 않는 city/gu는 예외 없이 세 키 모두 빈 리스트로 반환된다."""
    layers = load_region_layers(SAMPLE_PATH, "부산광역시", "해운대구")
    ok = layers == {"legal_dongs": [], "landmarks": [], "subcategory_keywords": []}
    if ok:
        reporter.pass_("존재하지 않는 city/gu는 예외 없이 빈 레이어 dict를 반환함")
    else:
        reporter.fail(f"미존재 city/gu 처리 결과가 예상과 다름: {layers}")


def check_load_missing_file_raises(reporter: ValidationReporter) -> None:
    """존재하지 않는 파일 경로는 FileNotFoundError를 그대로 전파해야 한다(설정 오류를 감추지 않음)."""
    missing_path = ROOT_DIR / "data" / "does_not_exist_regions.json"
    try:
        load_region_layers(missing_path, "서울특별시", "강동구")
        reporter.fail("존재하지 않는 파일 경로인데 예외가 발생하지 않음")
    except FileNotFoundError:
        reporter.pass_("존재하지 않는 파일 경로는 FileNotFoundError를 그대로 전파함")


def main() -> int:
    reporter = ValidationReporter()

    check_load_gangdong_sample_layers(reporter)
    check_load_unknown_city_gu_returns_empty_layers(reporter)
    check_load_missing_file_raises(reporter)

    reporter.summary()
    return 1 if reporter.fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
