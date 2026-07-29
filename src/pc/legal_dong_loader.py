# 공식 법정동 Snapshot(data/legal_dong_snapshot.json) 읽기 전용 로더.
#
# 이 모듈은 scripts/update_legal_dong_snapshot.py(개발자용 갱신 도구)가 만든
# Snapshot 파일만 읽는다 - 행안부 API를 직접 호출하지 않으며, 앱 실행 중
# 네트워크 호출이 0회임을 보장한다. Snapshot이 없거나 손상되면 조용히
# data/regions_kr_sample.json(다른 용도의 별도 샘플 데이터)으로 폴백하지
# 않고 LegalDongSnapshotError를 던진다 - 호출자(UI)가 명확한 오류로 처리해야
# 한다.
import json
import re
import sys
from pathlib import Path

SNAPSHOT_SCHEMA_VERSION = 1
_LEGAL_CODE_RE = re.compile(r"^[0-9]{10}$")
_REQUIRED_RECORD_FIELDS = ("sido", "sigungu", "eup_myeon_dong", "full_name", "is_active")


class LegalDongSnapshotError(Exception):
    """Snapshot 파일 로드/검증 실패. 이 예외가 발생하면 호출자는 조용히
    대체 데이터로 넘어가지 않고 사용자에게 오류를 표시해야 한다."""


def default_snapshot_path() -> Path:
    """개발 실행/프로젝트 루트 실행/PyInstaller 배포 실행 모두에서
    legal_dong_snapshot.json 위치를 찾는다. cwd에 의존하지 않고 이 모듈
    파일 위치(또는 PyInstaller 번들 경로) 기준으로 계산한다."""
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_dir = Path(__file__).resolve().parents[2]
    return base_dir / "data" / "legal_dong_snapshot.json"


class LegalDongSnapshotLoader:
    """data/legal_dong_snapshot.json을 1회 로드해 시도/시군구/법정동 계층
    조회 기능을 제공한다.

    - is_active=false 레코드는 어떤 조회 결과에도 노출하지 않는다.
    - 정렬 계약: 원본 Snapshot은 legal_code 오름차순으로 정렬돼 있고, 이
      로더는 그 순서를 그대로 보존한다(임의 재정렬 없음) - list_sidos()/
      list_sigungus()는 그 순서에서 처음 등장한 순서를 따른다.
    - 같은 eup_myeon_dong 명칭이라도 legal_code로 서로 다른 레코드임을
      구분한다(find_by_legal_code가 유일한 식별 경로).
    - 세종특별자치시처럼 시군구 계층이 없는 지역은 list_sigungus()가 빈
      리스트를 반환한다(세종이라는 이름을 코드에 하드코딩하지 않고, sigungu
      필드가 빈 문자열인 데이터 구조로만 판단한다).
    """

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_snapshot_path()
        self._records = self._load_and_validate(self.path)
        self._by_code: dict = {r["legal_code"]: r for r in self._records}
        self._sido_order: list = []
        self._sigungu_by_sido: dict = {}
        self._dongs_by_sido_sigungu: dict = {}
        for record in self._records:
            sido = record["sido"]
            sigungu = record["sigungu"]
            if sido not in self._sigungu_by_sido:
                self._sido_order.append(sido)
                self._sigungu_by_sido[sido] = []
            if sigungu and sigungu not in self._sigungu_by_sido[sido]:
                self._sigungu_by_sido[sido].append(sigungu)
            self._dongs_by_sido_sigungu.setdefault((sido, sigungu), []).append(record)

    @staticmethod
    def _load_and_validate(path: Path) -> list:
        if not path.exists():
            raise LegalDongSnapshotError(f"법정동 Snapshot 파일이 없습니다: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise LegalDongSnapshotError(f"법정동 Snapshot 파일이 UTF-8이 아닙니다: {path}") from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LegalDongSnapshotError(f"법정동 Snapshot JSON 파싱 실패: {path} ({exc})") from exc

        if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise LegalDongSnapshotError(
                f"법정동 Snapshot schema_version이 예상({SNAPSHOT_SCHEMA_VERSION})과 "
                f"다릅니다: {payload.get('schema_version')!r}"
            )
        raw_records = payload.get("records")
        if not isinstance(raw_records, list):
            raise LegalDongSnapshotError("법정동 Snapshot의 records가 배열이 아닙니다.")

        seen_codes: set = set()
        active_records = []
        for index, record in enumerate(raw_records):
            if not isinstance(record, dict):
                raise LegalDongSnapshotError(f"레코드 {index}가 객체(dict)가 아닙니다.")
            for field in _REQUIRED_RECORD_FIELDS:
                if field not in record:
                    raise LegalDongSnapshotError(f"레코드 {index}에 필수 필드 '{field}'가 없습니다.")
            legal_code = record.get("legal_code")
            if not isinstance(legal_code, str) or not _LEGAL_CODE_RE.match(legal_code):
                raise LegalDongSnapshotError(
                    f"레코드 {index}의 legal_code가 10자리 문자열이 아닙니다: {legal_code!r}"
                )
            if legal_code in seen_codes:
                raise LegalDongSnapshotError(f"중복 legal_code 발견: {legal_code}")
            seen_codes.add(legal_code)
            if record.get("is_active") is True:
                active_records.append(record)
        return active_records

    def list_sidos(self) -> list:
        return list(self._sido_order)

    def list_sigungus(self, sido: str) -> list:
        return list(self._sigungu_by_sido.get(sido, []))

    def list_legal_dongs(self, sido: str, sigungu: str) -> list:
        return list(self._dongs_by_sido_sigungu.get((sido, sigungu), []))

    def find_by_legal_code(self, legal_code: str):
        return self._by_code.get(legal_code)
