# 2026-06-25: V2.0 CustomTkinter UI. 기존 크롤링/파싱/엑셀 저장 파이프라인은 유지합니다.
# 2026-07-09 UI-CLEANUP-1: 다중 키워드/수집모드 선택/온라인 채널 필터를 제거하고
# 단일 키워드 + 자동 세분화 미리보기 중심으로 정리했다(구조 변경, 상세 설계는
# PROJECT_STATE.md 2026-07-09 UI-CLEANUP-1 기록 참고). [DB 수집] 탭과, 아직
# 실제 기능이 없는 [순위추적] V2 예정 탭으로 분리했다.
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from src.exporter import export_places_to_excel
from src.pc.diagnostics import DEFAULT_DIAGNOSTICS_ROOT, save_json_artifact
from src.pc.home_enrichment import enrich_home_details
from src.pc.network_browser_collector import ApolloFirstListCollector
from src.region.legal_dong_loader import LegalDongSnapshotError, LegalDongSnapshotLoader
from src.pc.network_pipeline import run_collection_plan
from src.pc.run_control import wait_while_paused


# LEGALDONG-UI-2: 공식 법정동 Snapshot(§_build_region_section)이 시도/시군구/
# 법정동의 유일한 production 출처다 - 하드코딩된 REGION_DATA는 제거했다.
# NEW-OPENING-1: 역/상권·세부업종 보조 검색 기능(regions_kr_sample.json 기반)은
# 완전히 제거했다 - 최종 Query Queue는 공식 법정동 선택 + 키워드만으로 구성된다.

# 다중 키워드로 보이는 입력을 차단하기 위한 패턴(쉼표/세미콜론/슬래시/파이프/
# 가운뎃점/줄바꿈). 다중 키워드 UI(추가/삭제/목록) 자체를 없앤 이유는 ①큐가
# 길어질수록 CAPTCHA 누적 리스크가 커지고(PoC-4~9 실측) ②제품 문구/기대치가
# 단일 검색어 기준으로 단순해지기 때문이다 - REGION-DATA-1/UI-CLEANUP-1 설계
# 참고. "카페 미용실"처럼 공백만 있는 입력은 하나의 실제 검색어일 수 있으므로
# 의도적으로 차단 대상에서 제외한다(UI-CLEANUP-1B).
_MULTI_KEYWORD_PATTERN = re.compile(r"[,;\n/|·]")

# 왼쪽 설정 패널 섹션 간 여백을 통일하기 위한 상수(위/아래 여백을 맞춰
# 달라는 요청 대응). 섹션 제목은 위 16/아래 4, 섹션 본문 프레임은 아래 16으로
# 맞춰 첫 섹션의 위쪽 여백과 마지막 섹션의 아래쪽 여백이 대칭이 되게 한다.
_SECTION_TITLE_PADY = (16, 4)
_SECTION_BODY_PADY = (0, 16)

# UI-CLEANUP-1D-A: [DB 수집]/[순위추적] 탭 자체를 감싸는 앱 전체 외곽 여백.
# 왼쪽 패널 "섹션 간" 여백(위 상수)과는 다른 층위 - 이건 "제목 아래 ~ 탭
# 바로 위"와 "앱 맨 아래" 여백을 상하 대칭으로 맞추기 위한 것이다. tabview는
# 창 전체를 채우는 단일 grid 셀이므로, 이 pady 하나만 상하 동일하게 주면
# 창 위/아래 외곽 여백이 자동으로 대칭이 된다.
_OUTER_PAD_X = 12
_OUTER_PAD_Y = (14, 14)

# 왼쪽 설정 패널의 최소 폭. 구를 여러 개 선택할 수 있게 되면서 체크박스
# 텍스트(예: "영등포구")가 좁은 폭에서 잘리는 문제가 있었다 - weight 대신
# minsize를 줘서 창을 줄여도 왼쪽 패널이 이 폭 아래로는 줄어들지 않게
# 고정하고, 남는 폭은 오른쪽 수집 현황/로그 패널이 전부 가져가게 한다.
_LEFT_PANEL_MIN_WIDTH = 420

# per_query_limit(검색 조합당 수집 상한, limit_var)의 권장 기본값.
_DEFAULT_PER_QUERY_LIMIT = "30"
_DEFAULT_TARGET_COUNT = "300"

# LEGALDONG-UI-2: 세종특별자치시처럼 시군구 계층이 없는 지역을 시군구 콤보박스에 표시할 때
# 쓰는 placeholder(지역명을 코드에 하드코딩하지 않고, list_sigungus()가 빈
# 리스트를 반환하는 데이터 구조로만 판단한다).
_LEGAL_DONG_NO_SIGUNGU = "(시군구 없음)"

def _parse_positive_int(raw: str, max_value: int | None = None) -> int | None:
    """문자열을 양의 정수로 파싱한다(WIRE-2B-2: per_query_limit/target_count
    공용 입력 검증 helper, Tk 불필요).

    비어있음/공백/비정수/0/음수는 전부 None을 반환한다(예외를 던지지 않음 -
    호출자가 None 여부로 차단 여부를 판단하고, 필드별 로그 메시지는 호출자가
    작성한다).

    max_value(LIMIT-300-A, 선택적): 주어지면 이 값을 초과하는 정수도 None을
    반환한다. 기본값 None이면 기존과 동일하게 상한 없이 양의 정수를 전부
    허용한다 - target_count 호출부는 max_value를 넘기지 않아 300 초과값도
    그대로 유효하다(검색 조합당 상한에만 max_value=300을 지정해, 전체 목표
    저장 개수에 실수로 300 상한이 전파되지 않도록 분리한다).
    """
    try:
        value = int((raw or "").strip())
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if max_value is not None and value > max_value:
        return None
    return value


def _parse_review_bound(raw: str) -> int | None:
    """review_min_var/review_max_var 하나를 파싱한다(NETWORK-CONTROLS-1).
    0을 유효한 값으로 허용해야 하므로(총리뷰수 0 이상 전부라는 의미) 0을
    None으로 취급하는 _parse_positive_int를 재사용하지 않는다. 공백/빈
    문자열은 None(제한 없음)이고, 그 외 값은 int()로 변환하며 실패 시
    ValueError를 그대로 전파한다."""
    raw = (raw or "").strip()
    return int(raw) if raw else None


def _sort_korean_names(values: list) -> list:
    """OS locale(strcoll 등)에 의존하지 않는 안정 정렬 - NFC 정규화 후
    코드포인트 비교만 사용한다(§3 시군구 목록 가나다순)."""
    return sorted(values, key=lambda value: unicodedata.normalize("NFC", value))


def _sort_legal_dong_items(items: list[dict]) -> list[dict]:
    """법정동 레코드를 eup_myeon_dong 가나다순으로 안정 정렬한다. 이름이
    같으면 legal_code를 보조 키로 사용해 결과 순서를 결정적으로 만든다
    (§3) - legal_code/선택 상태(BooleanVar 매핑은 legal_code 기준이므로)는
    이 정렬로 전혀 변하지 않는다."""
    return sorted(
        items,
        key=lambda item: (unicodedata.normalize("NFC", item["eup_myeon_dong"]), item["legal_code"]),
    )


def build_legal_dong_query_plan(
    sido: str, sigungu: str, legal_dongs: list[dict], keyword: str, per_query_limit: int,
    *, new_opening_only: bool = False, review_min: int | None = None, review_max: int | None = None,
) -> list[dict]:
    """공식 법정동 Snapshot 기반 선택(시도/시군구/법정동 다중선택)으로 검색
    조합을 만드는 순수 함수(Tk 불필요). job 형태({"region","keyword","query",
    "source_city","source_district","source_subregion","source_layer",
    "legal_code","per_query_limit","new_opening_only"})를 반환해
    _run_network_pipeline/orchestrator에 그대로 흘러가게 한다 - 기본모드/
    홈페이지·SNS 모드가 동일한 이 job 목록을 받는다(§_build_collection_queries).

    법정동을 하나도 선택하지 않으면 시군구(세종처럼 시군구가 없는 지역은
    시도) 단위 검색 조합 1개를 만든다("district" 계층). 법정동을 N개
    선택하면 legal_code로 식별되는 법정동별로 N개의 검색 조합을 만든다
    ("legal_dong" 계층) - 동일 명칭이 여러 시군구에 있어도(예: "신교동") 항상
    올바른 legal_code를 provenance로 유지한다. 공백 정규화를 적용하고, 중복
    쿼리는 제거하되 처음 등장한 순서(=legal_dongs 인자 순서, 화면 표시/선택
    순서 - 호출자가 이미 가나다순으로 정렬해 넘긴다는 전제, §3)를 유지한다.

    new_opening_only(NEW-OPENING-1): UI의 새로오픈 체크박스 값을 그대로
    job에 실어 collect_apollo_first_list_query까지 전달한다 - Query
    문자열 생성에는 영향을 주지 않는다(공식 지역명+키워드만 사용).

    review_min/review_max(NETWORK-CONTROLS-1): UI의 리뷰 최소·최대 입력값을
    동일한 방식으로 job에 실어 전달한다(둘 다 기본 None=필터 비활성).
    """

    def _norm(text: str) -> str:
        return " ".join(text.split())

    jobs: list[dict] = []
    seen_queries: set = set()

    if not legal_dongs:
        region_label = _norm(f"{sido} {sigungu}") if sigungu else _norm(sido)
        query = _norm(f"{region_label} {keyword}")
        if query and query not in seen_queries:
            seen_queries.add(query)
            jobs.append({
                "region": region_label,
                "keyword": keyword,
                "query": query,
                "source_city": sido,
                "source_district": sigungu,
                "source_subregion": "",
                "source_layer": "district",
                "legal_code": "",
                "per_query_limit": per_query_limit,
                "new_opening_only": new_opening_only,
                "review_min": review_min,
                "review_max": review_max,
            })
        return jobs

    for item in legal_dongs:
        eup_myeon_dong = item["eup_myeon_dong"]
        legal_code = item["legal_code"]
        region_label = (
            _norm(f"{sido} {sigungu} {eup_myeon_dong}") if sigungu else _norm(f"{sido} {eup_myeon_dong}")
        )
        query = _norm(f"{region_label} {keyword}")
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)
        jobs.append({
            "region": region_label,
            "keyword": keyword,
            "query": query,
            "source_city": sido,
            "source_district": sigungu,
            "source_subregion": eup_myeon_dong,
            "source_layer": "legal_dong",
            "legal_code": legal_code,
            "per_query_limit": per_query_limit,
            "new_opening_only": new_opening_only,
            "review_min": review_min,
            "review_max": review_max,
        })
    return jobs


def calculate_legal_dong_target_count(per_query_limit: int, query_count: int) -> int:
    """전체 목표 저장 개수 자동 계산: per_query_limit x query_count.
    둘 중 하나라도 0 이하면 0(미계산 상태)을 반환한다 - 호출자가 0을
    "계산 불가"로 취급해 기존 _parse_positive_int 검증에서 자연스럽게
    차단되게 한다(§_start_network_crawl, 새 오류 문구를 따로 만들지 않음)."""
    if per_query_limit <= 0 or query_count <= 0:
        return 0
    return per_query_limit * query_count


class SalesDbCrawlerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("네이버 플레이스 영업 DB 수집기 V2.0")
        # UI-CLEANUP-1D-A: 여러 구 체크박스 + 세부구역 설정 팝업까지 들어오면서
        # 기존 1000x800/고정 크기로는 좁았다. 기본 창을 키우고 최소 크기를
        # 지정한 뒤 크기 조절을 허용한다(왼쪽 패널은 minsize로, 오른쪽은
        # weight로 배분 - §_build_ui). resizable(False, False)로 고정하면
        # 사용자 모니터/DPI 환경에 따라 오히려 내용이 잘릴 위험이 커서
        # 가변 크기로 바꿨다.
        self.geometry("1240x820")
        self.minsize(1100, 780)
        self.resizable(True, True)

        self.keyword_input_var = ctk.StringVar(value="카페")
        # per_query_limit 의미(검색 조합 하나당 상한, run_collection_plan에
        # 그대로 전달) - 쿼리 간 dedup은 없다.
        self.limit_var = ctk.StringVar(value=_DEFAULT_PER_QUERY_LIMIT)
        # ARCH-300C WIRE-2B-2: 전역 place_id dedup 이후 최종 저장할 목표
        # 개수(target_count). run_collection_plan(WIRE-1)이 이 값에 도달하면
        # 남은 검색 조합을 실행하지 않고 조기 종료한다(실제 orchestrator 동작과
        # 일치 - "300개 보장"이 아니라 "도달 시 남은 조합 중단").
        # start_crawl(_start_network_crawl)이 이 값을 읽고 검증한다
        # (§_parse_positive_int) - 입력 위젯 활성화(§_build_global_target_count_section).
        self.target_count_var = ctk.StringVar(value=_DEFAULT_TARGET_COUNT)
        # 수집모드 선택 UI는 제거하지만, 내부적으로는 기존 PC 상세 수집 경로
        # (premium)를 그대로 기본값으로 사용한다(엔진 코드는 삭제하지 않음).
        self.mode_var = ctk.StringVar(value="premium")
        # 신규 두 모드(기본/홈페이지·SNS 포함) - mode_var(legacy 경로 전용)와는
        # 별개의 값이다. "basic"이 기본 선택값이다(§_build_collection_mode_section).
        self.collection_mode_var = ctk.StringVar(value="basic")
        self.output_path_var = ctk.StringVar(value="output/naver_place_premium_db.xlsx")
        self.new_open_only_var = ctk.BooleanVar(value=False)
        self.review_min_var = ctk.StringVar()
        self.review_max_var = ctk.StringVar()
        self.progress_percent_var = ctk.StringVar(value="0%")
        self.eta_var = ctk.StringVar(value="예상 남은 시간: 계산 중...")
        self.current_task_var = ctk.StringVar(value="대기 중...")
        self.total_found_var = ctk.StringVar(value="총 발견: 0개")
        self.duplicate_removed_var = ctk.StringVar(value="중복 제거: 0개")
        self.final_expected_var = ctk.StringVar(value="최종 저장 예정: 0개")

        self.last_output_path = ""
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.completed_queries = 0
        self.total_pure_time = 0.0
        self.current_query_start_time = None
        self.current_query_pause_time_at_start = 0.0
        self.total_pause_time = 0.0
        self.current_pause_start = None
        self.eta_after_id = None
        self.total_queries = 0
        self.total_found_count = 0

        # LEGALDONG-UI-2: 공식 법정동 Snapshot(data/legal_dong_snapshot.json)이
        # 시도/시군구/법정동의 유일한 production 출처다. 로더는 앱 시작 시
        # 1회만 로드한다(행안부 API 호출 없음, 순수 파일 읽기). 실패해도
        # 조용히 다른 데이터로 대체하지 않고 오류를 그대로
        # 보관해 §_build_region_section이 화면에 표시하고 수집 시작 버튼을
        # 비활성화하게 한다.
        self.legal_dong_sido_var = ctk.StringVar(value="")
        self.legal_dong_sigungu_var = ctk.StringVar(value=_LEGAL_DONG_NO_SIGUNGU)
        self.legal_dong_selected_count_var = ctk.StringVar(value="선택한 법정동: 0개")
        self.legal_dong_query_count_var = ctk.StringVar(value="검색 조합 수: 0개")
        self.legal_dong_load_error_var = ctk.StringVar(value="")
        # {legal_code: BooleanVar} - 현재 렌더링된 법정동 체크박스 상태.
        self.legal_dong_selection_vars: dict = {}
        # 현재 시도/시군구에 속한 법정동 레코드 목록(화면 표시 순서 그대로,
        # legal_code로 식별) - _render_legal_dong_checkboxes가 그리는 원본.
        self._legal_dong_current_items: list = []
        self._legal_dong_popup = None
        self._legal_dong_popup_container = None
        self._legal_dong_loader = None
        self._legal_dong_load_error = None
        try:
            self._legal_dong_loader = LegalDongSnapshotLoader()
            sidos = self._legal_dong_loader.list_sidos()
            self.legal_dong_sido_var.set("서울특별시" if "서울특별시" in sidos else (sidos[0] if sidos else ""))
        except LegalDongSnapshotError as exc:
            self._legal_dong_load_error = str(exc)
            self.legal_dong_load_error_var.set(str(exc))

        self._build_ui()
        self._reload_region_selection()

        # per_query_limit/keyword가 바뀌면 자동 target_count도 다시 계산한다
        # (§_recalculate_target_count) - 위젯이 전부 만들어진 뒤(_build_ui
        # 이후)에만 안전하게 붙일 수 있다.
        self.limit_var.trace_add("write", lambda *_args: self._recalculate_target_count())
        self.keyword_input_var.trace_add("write", lambda *_args: self._recalculate_target_count())

        if self._legal_dong_load_error is not None:
            self.log(f"[ui] 법정동 Snapshot 로드 실패: {self._legal_dong_load_error}")
            self.btn_start.configure(state="disabled")

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # UI-CLEANUP-1: 제목 아래에 [DB 수집] / [순위추적] 탭을 추가한다. 순위추적은
        # 업체 DB 수집과는 다른 알고리즘(검색 노출 순위 확인)이 필요해 별도 탭으로
        # 분리하고, 이번 단계에서는 V2 예정 화면만 제공한다(§_build_rank_tracking_tab).
        # UI-CLEANUP-1D-A: tabview는 창 전체를 채우는 유일한 최상위 grid 셀이므로,
        # 여기 pady를 상하 동일(_OUTER_PAD_Y)하게 주는 것만으로 "제목~탭 위" 여백과
        # "앱 맨 아래" 여백이 자동으로 대칭이 된다(왼쪽 패널 섹션 간격과는 다른 층위).
        # UI-CLEANUP-1D-B: [안내·정책] 탭 자리를 추가한다. 실제 판매/유지보수/
        # 라이선스 정책 문구는 정식 배포 전에 확정해 다시 작성할 예정이므로,
        # 이번에는 "정식 배포 전 작성 예정" placeholder만 채운 자리를 만든다
        # (§_build_policy_tab). 1PC 라이선스 인증 등 실제 기능은 구현하지 않는다.
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=_OUTER_PAD_X, pady=_OUTER_PAD_Y)
        self.db_tab = self.tabview.add("DB 수집")
        self.rank_tab = self.tabview.add("순위추적")
        self.policy_tab = self.tabview.add("안내·정책")
        self.tabview.set("DB 수집")

        self.db_tab.grid_rowconfigure(0, weight=1)
        # 왼쪽 패널은 minsize로 폭을 고정(구 이름 잘림 방지), 오른쪽은 weight=1로
        # 남는 공간을 전부 흡수한다 - 창을 늘리거나 줄여도 왼쪽 폭은 안정적으로
        # 유지되고 오른쪽만 늘었다 줄었다 한다.
        self.db_tab.grid_columnconfigure(0, weight=0, minsize=_LEFT_PANEL_MIN_WIDTH)
        self.db_tab.grid_columnconfigure(1, weight=1)

        # UI-CLEANUP-1B: 세부구역 체크박스가 펼쳐지면 왼쪽 설정 영역이 창보다
        # 길어질 수 있어 "목표 수집 개수"가 잘리는 문제가 있었다. CTkFrame 대신
        # CTkScrollableFrame을 써서 왼쪽 영역 전체를 세로 스크롤 가능하게 만들어
        # 해결한다(오른쪽 수집 현황/로그 영역은 기존 CTkFrame 그대로 유지).
        self.left_panel = ctk.CTkScrollableFrame(self.db_tab)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
        self.left_panel.grid_columnconfigure(0, weight=1)

        self.right_panel = ctk.CTkFrame(self.db_tab)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(3, weight=1)

        self._build_region_section()
        self._build_keyword_section()
        self._build_filter_section()
        self._build_target_count_section()
        self._build_global_target_count_section()
        self._build_collection_mode_section()
        self._build_dashboard_section()
        self._build_control_section()
        self._build_log_section()

        self._build_rank_tracking_tab()
        self._build_policy_tab()

    def _build_region_section(self):
        """LEGALDONG-UI-2: 공식 법정동 Snapshot(data/legal_dong_snapshot.json)이
        시도/시군구/법정동의 유일한 production 출처다(REGION_DATA 하드코딩은
        제거됨). 시도/시군구는 콤보박스 단일 선택, 법정동은 별도 팝업에서
        다중 선택한다(§_open_legal_dong_popup). Snapshot 로드가 실패했으면
        오류 문구만 보여주고 수집 시작 버튼을 비활성화한다(§__init__) -
        다른 데이터로 조용히 대체하지 않는다."""
        ctk.CTkLabel(self.left_panel, text="1. 지역 선택", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        region_frame = ctk.CTkFrame(self.left_panel)
        region_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        region_frame.grid_columnconfigure(0, weight=1)

        if self._legal_dong_load_error is not None:
            ctk.CTkLabel(
                region_frame, text="지역 데이터 파일 오류로 지역을 선택할 수 없습니다.",
                anchor="w", text_color="#c0392b", font=ctk.CTkFont(weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(
                region_frame, textvariable=self.legal_dong_load_error_var,
                justify="left", anchor="w", text_color="#c0392b", font=ctk.CTkFont(size=11), wraplength=360,
            ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
            return

        ctk.CTkLabel(region_frame, text="시도", anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self.legal_dong_sido_dropdown = ctk.CTkOptionMenu(
            region_frame, variable=self.legal_dong_sido_var,
            values=self._legal_dong_loader.list_sidos(),
            command=self._on_legal_dong_sido_changed,
        )
        self.legal_dong_sido_dropdown.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))

        ctk.CTkLabel(region_frame, text="시군구", anchor="w").grid(row=2, column=0, sticky="w", padx=12, pady=(0, 0))
        self.legal_dong_sigungu_dropdown = ctk.CTkOptionMenu(
            region_frame, variable=self.legal_dong_sigungu_var,
            values=[_LEGAL_DONG_NO_SIGUNGU], state="disabled",
            command=self._on_legal_dong_sigungu_changed,
        )
        self.legal_dong_sigungu_dropdown.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 8))

        self.legal_dong_popup_button = ctk.CTkButton(
            region_frame, text="법정동 선택(선택 사항)", command=self._open_legal_dong_popup,
        )
        self.legal_dong_popup_button.grid(row=4, column=0, sticky="ew", padx=12, pady=(2, 4))

        ctk.CTkLabel(region_frame, textvariable=self.legal_dong_selected_count_var, anchor="w", text_color="gray").grid(
            row=5, column=0, sticky="w", padx=12, pady=(4, 0)
        )
        ctk.CTkLabel(region_frame, textvariable=self.legal_dong_query_count_var, anchor="w", text_color="gray").grid(
            row=6, column=0, sticky="w", padx=12, pady=(0, 4)
        )
        ctk.CTkLabel(
            region_frame,
            text=(
                "행정안전부 공식 법정동 데이터를 사용합니다(앱 실행 중 API 호출 없음).\n"
                "법정동을 선택하지 않으면 시군구(시군구 없는 지역은 시도) 단위로 검색합니다.\n"
                "전남광주통합특별시/세종특별자치시 등은 공식 명칭을 그대로 표시하며,\n"
                "네이버 검색어 호환성과 지역 exact 필터는 아직 다음 단계입니다."
            ),
            justify="left", anchor="w", text_color="gray", font=ctk.CTkFont(size=11), wraplength=360,
        ).grid(row=7, column=0, sticky="w", padx=12, pady=(0, 10))

        self._legal_dong_popup = None
        self._legal_dong_popup_container = None

    def _build_keyword_section(self):
        ctk.CTkLabel(self.left_panel, text="2. 키워드 입력", font=ctk.CTkFont(size=14, weight="bold")).grid(row=2, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        keyword_frame = ctk.CTkFrame(self.left_panel)
        keyword_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        keyword_frame.grid_columnconfigure(0, weight=1)

        # 다중 키워드 추가/목록/삭제 UI를 제거하고 단일 입력창만 남긴다.
        # 이유: 큐가 길어질수록(지역x키워드 곱집합) 연속 요청이 늘어 CAPTCHA
        # 누적 리스크가 커진다는 것이 PoC-4~9 실측으로 확인됐고, 여러 키워드를
        # 한 번에 도는 기능은 현재 안정성 근거가 없다 - 다중 키워드 시도는
        # start_crawl에서 쉼표/세미콜론/줄바꿈 패턴으로 사전 차단한다.
        ctk.CTkLabel(keyword_frame, text="수집할 업종/검색어", anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.keyword_entry = ctk.CTkEntry(keyword_frame, textvariable=self.keyword_input_var, placeholder_text="예: 카페")
        self.keyword_entry.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            keyword_frame, text="현재 버전은 키워드 1개만 지원합니다.",
            anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))

    def _build_filter_section(self):
        ctk.CTkLabel(self.left_panel, text="3. 필터", font=ctk.CTkFont(size=14, weight="bold")).grid(row=4, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        filter_frame = ctk.CTkFrame(self.left_panel)
        filter_frame.grid(row=5, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        filter_frame.grid_columnconfigure((1, 3), weight=1)

        # 온라인 채널(블로그/인스타 등 존재) 필터는 제거한다: 홈페이지/인스타/
        # 블로그는 이제 기본 수집 컬럼으로 항상 가져오므로 "있는 업체만" 필터가
        # 더 이상 필요하지 않다. 단, 엑셀 결과의 홈페이지/인스타/블로그 컬럼
        # 자체는 그대로 유지한다(exporter.MERGED_COLUMNS 변경 없음).
        # NEW-OPENING-1: filterOpening="true" 전용 placeList operation을
        # 실측으로 확인해(scratchpad/new_opening_filter_implementation) 새로오픈
        # 전용 목록 수집을 실제로 구현했으므로, 항상 잠그던 코드를 제거하고
        # 기본 사용 가능한 체크박스로 되돌린다. 체크 시 apollo_list_adapter의
        # 전용 selector가 filterOpening=true operation만 선택하고, newOpening이
        # 명시적으로 true인 업체만 저장한다(§_build_collection_queries).
        self.new_open_checkbox = ctk.CTkCheckBox(filter_frame, text="새로오픈 업체만 수집", variable=self.new_open_only_var)
        self.new_open_checkbox.grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            filter_frame,
            text=(
                "체크 시 새로오픈 전용 목록만 수집합니다(일반 목록으로 대체하지 않음).\n"
                "새로오픈 업체가 목표보다 적으면 실제 확보된 개수로 정상 종료됩니다."
            ),
            justify="left", anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 8))

        ctk.CTkLabel(filter_frame, text="리뷰 수:").grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(0, 10))
        self.review_min_entry = ctk.CTkEntry(filter_frame, textvariable=self.review_min_var, placeholder_text="Min", width=70)
        self.review_min_entry.grid(row=2, column=1, sticky="ew", padx=(0, 6), pady=(0, 10))
        ctk.CTkLabel(filter_frame, text="~").grid(row=2, column=2, padx=2, pady=(0, 10))
        self.review_max_entry = ctk.CTkEntry(filter_frame, textvariable=self.review_max_var, placeholder_text="Max", width=70)
        self.review_max_entry.grid(row=2, column=3, sticky="ew", padx=(6, 12), pady=(0, 10))

    def _build_target_count_section(self):
        # UI-CLEANUP-1D-B에서 "조기 종료" 문구는 제거했지만, 라벨 자체가 여전히
        # "목표 수집 개수"라 전체 목표처럼 오해될 수 있었다. limit_var는 실제로
        # 전체 목표가 아니라 검색 조합(쿼리) 1개당 상한이므로(§self.limit_var
        # 정의부 주석), 라벨/문구를 그 동작 그대로 표현하도록 다시 정정했다.
        ctk.CTkLabel(self.left_panel, text="4. 검색 조합당 수집 상한", font=ctk.CTkFont(size=14, weight="bold")).grid(row=6, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        target_frame = ctk.CTkFrame(self.left_panel)
        target_frame.grid(row=7, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        target_frame.grid_columnconfigure(0, weight=1)

        self.limit_entry = ctk.CTkEntry(target_frame, textvariable=self.limit_var, width=100)
        self.limit_entry.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        # UI-CLEANUP-1E: "네이버 플레이스 검색 구조상 최대 300개" 관련 긴 설명은
        # 안내·정책 탭에서 정식 문구로 다룰 예정이라 여기서는 핵심만 남긴다.
        # 조기 종료 문구는 다시 추가하지 않는다(1D-B 결정 유지).
        ctk.CTkLabel(
            target_frame,
            text=(
                "검색 조합(지역+업종으로 만든 검색어 1개)마다 적용되는 최대 수집 상한입니다.\n"
                "실제 수집 수는 검색 결과에 따라 이 값보다 적을 수 있습니다.\n"
                "전체 저장 개수는 지역 수와 중복 제거 결과에 따라 달라집니다.\n"
                "최대 300개"
            ),
            justify="left", anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

    def _build_global_target_count_section(self):
        # LEGALDONG-UI-2: 전체 목표 저장 개수(target_count)는 항상 자동
        # 계산이다(검색 조합당 수집 상한 x 최종 검색 조합 수,
        # §_recalculate_target_count) - 사용자가 직접 입력하지 못하도록
        # 위젯을 항상 disabled(읽기 전용)로 만든다. run_collection_plan이
        # 실제로 "목표 도달 시 남은 검색 조합 중단"을 구현하고 있으므로 그
        # 문구만 사용하고 "300개 보장"처럼 과장된 표현은 쓰지 않는다.
        ctk.CTkLabel(self.left_panel, text="5. 전체 목표 저장 개수(자동 계산)", font=ctk.CTkFont(size=14, weight="bold")).grid(row=8, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        global_target_frame = ctk.CTkFrame(self.left_panel)
        global_target_frame.grid(row=9, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        global_target_frame.grid_columnconfigure(0, weight=1)

        self.target_count_entry = ctk.CTkEntry(global_target_frame, textvariable=self.target_count_var, width=100, state="disabled")
        self.target_count_entry.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            global_target_frame,
            text=(
                "검색 조합당 수집 상한 x 검색 조합 수로 자동 계산됩니다(직접 수정 불가).\n"
                "여러 검색 조합의 결과를 합치고 중복을 제거한 뒤 Excel에 최종 저장할 최대 업체 수입니다.\n"
                "목표 개수는 보장값이 아니며, 업종·지역 및 검색 결과에 따라 미달할 수 있습니다."
            ),
            justify="left", anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))
        # UX-1: "검색 조합당 수집 상한"(§5)과 "전체 목표 저장 개수"(§6)의 관계를
        # 숫자를 넣지 않고는 이해하기 어렵다는 사용자 혼동 지점이 있어, 두 값을
        # 모두 입력한 뒤 확인하게 되는 이 섹션 마지막에 기본값 30/300 예시를
        # 짧게 덧붙인다(옵션 A: 두 숫자 입력 영역 아래 공통 안내 문구).
        ctk.CTkLabel(
            global_target_frame,
            text=(
                "예) 조합당 30 / 전체 목표 300\n"
                "→ 검색어마다 최대 30개씩 수집하고, 여러 결과를 합쳐\n"
                "   중복 제거 후 전체 최대 300개를 저장합니다."
            ),
            justify="left", anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))

    def _build_collection_mode_section(self):
        # 두 모드(기본/홈페이지·SNS 포함) 선택 - "프리미엄"/"유료"/"제한 모드"
        # 같은 분류 문구는 쓰지 않는다(요청서 §0 금지 사항). 기본 선택값은
        # collection_mode_var(§__init__)와 동일하게 "basic"이다.
        ctk.CTkLabel(self.left_panel, text="6. 수집 모드", font=ctk.CTkFont(size=14, weight="bold")).grid(row=10, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        mode_frame = ctk.CTkFrame(self.left_panel)
        mode_frame.grid(row=11, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        mode_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkRadioButton(
            mode_frame, text="빠른 기본 수집", variable=self.collection_mode_var, value="basic",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            mode_frame, text="업체·리뷰·주소·전화 등 목록 핵심정보를 빠르게 수집합니다.",
            justify="left", anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, sticky="w", padx=28, pady=(0, 8))

        ctk.CTkRadioButton(
            mode_frame, text="홈페이지·SNS 포함 수집", variable=self.collection_mode_var, value="home_sns",
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 2))
        ctk.CTkLabel(
            mode_frame,
            text=(
                "기본정보에 홈페이지·인스타그램·블로그를 추가합니다.\n"
                "업체 수에 따라 시간이 더 걸립니다."
            ),
            justify="left", anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=3, column=0, sticky="w", padx=28, pady=(0, 10))

    def _on_legal_dong_sido_changed(self, _sido=None):
        self._reload_legal_dong_sigungu_options()
        self._reload_legal_dong_checkboxes()
        self._recalculate_target_count()

    def _reload_legal_dong_sigungu_options(self):
        """시도가 바뀌면 시군구 목록을 새로 채운다. 시군구가 없는 지역
        (세종특별자치시 등)은 콤보박스를 비활성화하고 "(시군구 없음)"만
        보여준다 - 지역명을 코드에 직접 넣지 않고 list_sigungus()가 빈
        리스트인지로만 판단한다. 화면 표시는 가나다순(§3)이며, 로더/원본
        Snapshot의 legal_code 오름차순 계약 자체는 건드리지 않는다."""
        sido = self.legal_dong_sido_var.get()
        sigungus = _sort_korean_names(self._legal_dong_loader.list_sigungus(sido)) if self._legal_dong_loader else []
        if sigungus:
            self.legal_dong_sigungu_dropdown.configure(values=sigungus, state="normal")
            self.legal_dong_sigungu_var.set(sigungus[0])
        else:
            self.legal_dong_sigungu_dropdown.configure(values=[_LEGAL_DONG_NO_SIGUNGU], state="disabled")
            self.legal_dong_sigungu_var.set(_LEGAL_DONG_NO_SIGUNGU)

    def _on_legal_dong_sigungu_changed(self, _sigungu=None):
        self._reload_legal_dong_checkboxes()
        self._recalculate_target_count()

    def _current_legal_dong_sigungu(self) -> str:
        """시군구 콤보박스 값을 조회 가능한 실제 값으로 바꾼다("(시군구 없음)"
        placeholder는 빈 문자열로 취급 - 세종특별자치시 등)."""
        value = self.legal_dong_sigungu_var.get()
        return "" if value == _LEGAL_DONG_NO_SIGUNGU else value

    def _current_region_description(self) -> str:
        """로그 표시용 - 현재 선택된 시도/시군구/법정동을 한 줄로 요약한다."""
        sido = self.legal_dong_sido_var.get()
        sigungu = self._current_legal_dong_sigungu()
        region_desc = f"{sido} {sigungu}".strip() if sigungu else sido
        selected_names = [item["eup_myeon_dong"] for item in self.get_selected_legal_dongs()]
        if selected_names:
            return f"{region_desc}(법정동 {', '.join(selected_names)})"
        return f"{region_desc}(법정동 미선택 - 시군구 단위)"

    def _reload_legal_dong_checkboxes(self):
        """시도/시군구 변경 시 그 아래 법정동 목록을 새로 불러오고 선택
        상태를 전부 초기화한다(시도 변경 시 시군구·법정동 초기화, 시군구
        변경 시 법정동 초기화 요구사항). 화면 표시/선택 순서 및 이 순서를
        그대로 물려받는 Query Queue는 가나다순이다(§3) - legal_code는
        정렬 키가 아니라 동명이인 법정동의 보조 정렬/식별 키로만 쓰인다."""
        sido = self.legal_dong_sido_var.get()
        items = self._legal_dong_loader.list_legal_dongs(sido, self._current_legal_dong_sigungu()) if self._legal_dong_loader else []
        items = _sort_legal_dong_items(items)
        self._legal_dong_current_items = items
        self.legal_dong_selection_vars = {item["legal_code"]: ctk.BooleanVar(value=False) for item in items}
        self._render_legal_dong_checkboxes()
        self._update_legal_dong_summary()

    def _is_legal_dong_popup_open(self) -> bool:
        popup = self._legal_dong_popup
        return popup is not None and popup.winfo_exists()

    def _open_legal_dong_popup(self):
        """"법정동 선택" 버튼 클릭 시 팝업(Toplevel)을 연다. 법정동 체크박스는
        legal_dong_selection_vars의 BooleanVar를 그대로 공유하므로 체크/해제가
        즉시 실제 상태에 반영된다."""
        if self._is_legal_dong_popup_open():
            self._legal_dong_popup.lift()
            self._legal_dong_popup.focus_force()
            return

        popup = ctk.CTkToplevel(self)
        popup.title("법정동 선택")
        popup.geometry("420x560")
        popup.minsize(360, 400)
        popup.transient(self)
        popup.grab_set()
        popup.grid_rowconfigure(0, weight=1)
        popup.grid_columnconfigure(0, weight=1)
        popup.protocol("WM_DELETE_WINDOW", self._close_legal_dong_popup)

        container = ctk.CTkScrollableFrame(popup)
        container.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        container.grid_columnconfigure(0, weight=1)

        button_row = ctk.CTkFrame(popup, fg_color="transparent")
        button_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkButton(button_row, text="전체 선택", width=100, command=self._select_all_legal_dongs).pack(side="left", padx=(0, 6))
        ctk.CTkButton(button_row, text="전체 해제", width=100, fg_color="gray", command=self._deselect_all_legal_dongs).pack(side="left")
        ctk.CTkButton(button_row, text="닫기", width=100, fg_color="gray", command=self._close_legal_dong_popup).pack(side="right")
        ctk.CTkButton(button_row, text="적용", width=100, command=self._close_legal_dong_popup).pack(side="right", padx=(0, 6))

        self._legal_dong_popup = popup
        self._legal_dong_popup_container = container
        self._render_legal_dong_checkboxes()

    def _close_legal_dong_popup(self):
        self._update_legal_dong_summary()
        popup = self._legal_dong_popup
        self._legal_dong_popup = None
        self._legal_dong_popup_container = None
        if popup is not None:
            try:
                popup.grab_release()
                popup.destroy()
            except Exception:
                pass

    def _render_legal_dong_checkboxes(self):
        """팝업이 열려 있을 때만 그린다(닫혀 있으면 그릴 대상이 없음) -
        공식 데이터 순서(legal_code 오름차순) 그대로 보존한다."""
        if not self._is_legal_dong_popup_open():
            return
        container = self._legal_dong_popup_container
        for child in container.winfo_children():
            child.destroy()
        if not self._legal_dong_current_items:
            ctk.CTkLabel(container, text="이 시군구는 법정동 목록이 없습니다.", text_color="gray").grid(row=0, column=0, sticky="w")
            return
        for row, item in enumerate(self._legal_dong_current_items):
            legal_code = item["legal_code"]
            ctk.CTkCheckBox(
                container, text=item["eup_myeon_dong"],
                variable=self.legal_dong_selection_vars[legal_code],
                command=self._on_legal_dong_toggle,
            ).grid(row=row, column=0, sticky="w", padx=8, pady=2)

    def _on_legal_dong_toggle(self):
        self._update_legal_dong_summary()

    def _select_all_legal_dongs(self):
        for var in self.legal_dong_selection_vars.values():
            var.set(True)
        self._update_legal_dong_summary()

    def _deselect_all_legal_dongs(self):
        for var in self.legal_dong_selection_vars.values():
            var.set(False)
        self._update_legal_dong_summary()

    def get_selected_legal_dongs(self) -> list:
        """현재 체크된 법정동 레코드를 화면 표시 순서 그대로 반환한다
        (legal_code로 식별 - 동일 명칭이라도 서로 다른 레코드로 구분됨)."""
        return [
            item for item in self._legal_dong_current_items
            if self.legal_dong_selection_vars[item["legal_code"]].get()
        ]

    def _update_legal_dong_summary(self):
        self.legal_dong_selected_count_var.set(f"선택한 법정동: {len(self.get_selected_legal_dongs())}개")
        self._recalculate_target_count()

    def _recalculate_target_count(self):
        """전체 목표 저장 개수는 항상 자동 계산이다(LEGALDONG-UI-2) -
        검색 조합당 수집 상한 x 최종 검색 조합 수(공식 법정동 선택의 중복
        제거된 최종 결과, §_build_collection_queries). keyword가 비어
        있거나 per_query_limit이 유효하지 않으면 0(계산 불가)으로 표시한다.
        target_count_entry는 항상 disabled이며 사용자가 직접 수정할 수
        없다(§_build_global_target_count_section)."""
        if not hasattr(self, "target_count_entry"):
            return  # _build_ui 진행 중(target_count_entry가 아직 없음) - 최초 렌더 시 1회 무시
        per_query_limit = _parse_positive_int(self.limit_var.get(), max_value=300)
        query_count = len(self._build_collection_queries())
        target = calculate_legal_dong_target_count(per_query_limit or 0, query_count)
        self.target_count_var.set(str(target))
        self.legal_dong_query_count_var.set(f"검색 조합 수: {query_count}개")

    def _build_dashboard_section(self):
        ctk.CTkLabel(self.right_panel, text="수집 현황", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
        status_card = ctk.CTkFrame(self.right_panel)
        status_card.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        status_card.grid_columnconfigure(0, weight=1)
        self.progress_bar = ctk.CTkProgressBar(status_card)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        self.progress_bar.set(0)
        ctk.CTkLabel(status_card, textvariable=self.progress_percent_var, font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, padx=(0, 16), pady=(16, 8))
        ctk.CTkLabel(status_card, textvariable=self.eta_var, anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
        ctk.CTkLabel(status_card, textvariable=self.current_task_var, anchor="w").grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 10))
        # 총 발견/최종 저장 예정은 실제 집계값을 반영한다. 중복 제거는 현재
        # 파이프라인이 쿼리 간 dedup을 추적하지 않아(ARCH-300C 계층형 큐 미연결)
        # 항상 0으로 표시된다 - 실제로 연결되기 전까지 근거 없는 숫자를 보여주지
        # 않기 위한 정직한 placeholder다(§_reset_collection_stats).
        ctk.CTkLabel(status_card, textvariable=self.total_found_var, anchor="w").grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 2))
        ctk.CTkLabel(status_card, textvariable=self.duplicate_removed_var, anchor="w").grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 2))
        ctk.CTkLabel(status_card, textvariable=self.final_expected_var, anchor="w").grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 16))

    def _build_control_section(self):
        button_frame = ctk.CTkFrame(self.right_panel)
        button_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 14))
        button_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.btn_start = ctk.CTkButton(button_frame, text="수집 시작", height=40, font=ctk.CTkFont(weight="bold"), command=self.start_crawl)
        self.btn_start.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=10)
        self.btn_pause = ctk.CTkButton(button_frame, text="일시정지", height=40, fg_color="gray", command=self.pause_crawl)
        self.btn_pause.grid(row=0, column=1, sticky="ew", padx=5, pady=10)
        self.btn_stop = ctk.CTkButton(button_frame, text="중지", height=40, fg_color="#c0392b", hover_color="#922b21", command=self.stop_crawl)
        self.btn_stop.grid(row=0, column=2, sticky="ew", padx=5, pady=10)
        self.btn_open_folder = ctk.CTkButton(button_frame, text="저장 폴더 열기", height=40, command=self.open_output_folder)
        self.btn_open_folder.grid(row=0, column=3, sticky="ew", padx=(5, 10), pady=10)

    def _build_log_section(self):
        self.log_box = ctk.CTkTextbox(self.right_panel, state="disabled")
        self.log_box.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.log("[ui] 실행 준비 완료")

    def _build_rank_tracking_tab(self):
        # 순위추적은 업체 DB 수집(리스트/상세 수집)과는 전혀 다른 알고리즘
        # (특정 키워드로 검색했을 때 노출 순서를 확인)이 필요하다. 이번
        # UI-CLEANUP-1은 화면 정리 작업이므로 실제 검색/크롤러/DB 스키마/
        # 자동 스케줄링은 구현하지 않고, 어떤 기능이 올 예정인지 보여주는
        # 정적 미리보기만 제공한다. 실제 구현은 DB 수집 MVP 안정화 이후
        # 별도 단계(PROJECT_STATE.md 참고)에서 진행한다.
        self.rank_tab.grid_rowconfigure(0, weight=1)
        self.rank_tab.grid_columnconfigure(0, weight=1)

        container = ctk.CTkScrollableFrame(self.rank_tab)
        container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(container, text="순위추적 V2 예정", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w", pady=(4, 4))
        ctk.CTkLabel(
            container,
            text=(
                "순위추적은 업체 DB 수집과 별도 알고리즘으로 동작합니다.\n"
                "특정 업체 또는 특정 키워드를 기준으로 노출 순위를 확인하고,\n"
                "날짜별 변화를 기록하는 기능입니다."
            ),
            justify="left", anchor="w", text_color="gray",
        ).grid(row=1, column=0, sticky="w", pady=(0, 16))

        self._build_rank_tracking_card(
            container, row=2, title="업체별 순위",
            description="특정 업체가 여러 키워드에서 몇 위인지 확인합니다.",
            example=(
                "예: 굽네치킨 천호점\n"
                "- 천호동 치킨: 7위\n"
                "- 강동구 치킨: 15위\n"
                "- 천호역 치킨: 4위"
            ),
        )
        self._build_rank_tracking_card(
            container, row=3, title="키워드별 순위",
            description="특정 키워드에서 어떤 업체들이 상위에 노출되는지 확인합니다.",
            example=(
                "예: 천호동 치킨\n"
                "1위 교촌치킨 천호점\n"
                "2위 굽네치킨 천호점\n"
                "3위 BBQ 천호점"
            ),
        )
        self._build_rank_tracking_card(
            container, row=4, title="날짜별 변화 기록",
            description="매일 또는 주간 단위로 순위 변화를 저장하고 리포트화합니다.",
            example=None,
        )

        self.rank_placeholder_button = ctk.CTkButton(container, text="순위추적 기능 준비중", state="disabled")
        self.rank_placeholder_button.grid(row=5, column=0, sticky="ew", pady=(10, 0))

    def _build_rank_tracking_card(self, parent, row: int, title: str, description: str, example: str | None):
        card = ctk.CTkFrame(parent)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(card, text=description, anchor="w", justify="left").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4 if example else 10))
        if example:
            ctk.CTkLabel(card, text=example, justify="left", anchor="w", text_color="gray").grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))

    def _build_policy_tab(self):
        # ARCH-300C WIRE-2D: [안내·정책] 탭에 실제 동작과 일치하는 핵심 정책을
        # 요약해 채운다(POLICY-ALIGN-1 감사 결과 반영). 장문의 README/
        # LEGAL_NOTICE 전체를 옮기지 않고 핵심 문장만 담는다 - 자세한 내용은
        # README.md/LEGAL_NOTICE.md를 참고하도록 안내한다. 유지보수/A/S,
        # 라이선스 안내(1PC 인증, 결제/고객센터/계정 기능 등)는 여전히 개발
        # 마지막 단계의 별도 태스크이므로 placeholder를 유지한다. 기존
        # 카드·스크롤 레이아웃 구조는 그대로 재사용한다.
        self.policy_tab.grid_rowconfigure(0, weight=1)
        self.policy_tab.grid_columnconfigure(0, weight=1)

        container = ctk.CTkScrollableFrame(self.policy_tab)
        container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(container, text="안내·정책", font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, sticky="w", pady=(4, 4))
        ctk.CTkLabel(
            container, text="핵심 수집 정책을 요약합니다. 자세한 내용은 README.md/LEGAL_NOTICE.md를 확인하세요.",
            anchor="w", text_color="gray",
        ).grid(row=1, column=0, sticky="w", pady=(0, 16))

        policy_sections = [
            (
                "1. 수집 방식",
                "검색 결과 목록 화면에서 브라우저가 검색 과정 중 정상적으로 수신한 응답을 처리합니다.\n"
                "별도의 HTTP 클라이언트로 네이버 엔드포인트를 직접 호출하는 구조는 사용하지 않습니다.",
            ),
            (
                "2. 수집 개수",
                "검색 조합당 수집 상한(기본 30)과 전체 목표 저장 개수(기본 300)는 서로 다른 값입니다.\n"
                "전체 목표 저장 개수는 최대 목표값이며 보장값이 아니고, 검색 결과에 따라 미달할 수 있습니다.",
            ),
            (
                "3. 안전 중단",
                "CAPTCHA(보안 확인)·요청 제한(429)이 감지되면 우회하지 않고 즉시 중단합니다.\n"
                "중단 시점까지 수집된 결과가 있으면 저장하고, 결과가 없으면 저장하지 않습니다.",
            ),
            (
                "4. 데이터 제공 범위",
                "업체별로 홈페이지·인스타·블로그·전화 등 일부 필드가 검색 응답에 없으면 빈칸일 수 있습니다.\n"
                "새로오픈 업체만 수집 필터는 현재 지원하지 않습니다(항상 비활성화).",
            ),
            (
                "5. 이용 책임",
                "수집 결과의 사용 목적과 개인정보·영업 활용에 대한 책임은 사용자에게 있습니다.\n"
                "본 프로그램은 네이버 공식 제품이거나 네이버와 제휴한 제품이 아닙니다.",
            ),
        ]
        row = 2
        for title, body in policy_sections:
            card = ctk.CTkFrame(container)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(card, text=body, justify="left", anchor="w", text_color="gray").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
            row += 1

        placeholder_sections = [
            "유지보수 / A/S 안내",
            "라이선스 안내",
        ]
        for title in placeholder_sections:
            card = ctk.CTkFrame(container)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(card, text="정식 배포 전 작성 예정", anchor="w", text_color="gray").grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
            row += 1

    def _reload_region_selection(self):
        """앱 시작 시(§__init__, _build_ui 이후) 초기 지역 상태를 한 번에
        맞춘다: 시군구 옵션 → 법정동 목록 → 자동 target_count 순서로 채운다."""
        self._reload_legal_dong_sigungu_options()
        self._reload_legal_dong_checkboxes()
        self._recalculate_target_count()

    def _build_collection_queries(self) -> list[dict]:
        """공식 법정동 선택(§1)만으로 최종 검색 조합을 만든다(NEW-OPENING-1:
        역/상권·세부업종 보조 검색 기능 완전 제거). 계산 자체는 Tk와 무관한
        순수 함수(build_legal_dong_query_plan)에 위임한다. 기본모드/
        홈페이지·SNS 모드(§_start_network_crawl) 둘 다 이 메서드 하나만
        거치므로 자동으로 동일한 검색계획을 사용하게 된다."""
        keyword = self.keyword_input_var.get().strip()
        if not keyword:
            return []

        per_query_limit = _parse_positive_int(self.limit_var.get(), max_value=300) or 0
        sido = self.legal_dong_sido_var.get()
        sigungu = self._current_legal_dong_sigungu()

        jobs = build_legal_dong_query_plan(
            sido, sigungu, self.get_selected_legal_dongs(), keyword, per_query_limit,
            new_opening_only=self.new_open_only_var.get(),
            review_min=_parse_review_bound(self.review_min_var.get()),
            review_max=_parse_review_bound(self.review_max_var.get()),
        )

        seen_queries: set = set()
        deduped: list[dict] = []
        for job in jobs:
            if job["query"] in seen_queries:
                continue
            seen_queries.add(job["query"])
            deduped.append(job)
        return deduped

    def _estimate_query_count(self) -> int:
        return len(self._build_collection_queries())

    def log(self, message: str):
        self.after(0, self._append_log, message)

    def _append_log(self, message: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_status(self, message: str):
        self.after(0, self.current_task_var.set, message)

    def set_running(self, is_running: bool):
        state = "disabled" if is_running else "normal"
        self.after(0, lambda: self.btn_start.configure(state=state))
        self.after(0, lambda: self._set_left_panel_state(state))

    def _set_left_panel_state(self, state: str):
        # NEW-OPENING-1: 새로오픈 체크박스는 이제 정상 사용 가능한 필터이므로
        # (§_build_filter_section) 수집 중에는 다른 입력과 함께 잠기고, 수집이
        # 끝나면 아래 블랑킷 루프(CTkCheckBox 포함)를 통해 그대로 normal로
        # 복구된다 - 더 이상 강제로 disabled를 유지하는 특례가 없다.
        for widget in self._iter_children(self.left_panel):
            if isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkEntry, ctk.CTkRadioButton, ctk.CTkOptionMenu)):
                widget.configure(state=state)
        # LEGALDONG-UI-2: 전체 목표 저장 개수는 항상 자동 계산·읽기 전용이므로
        # (§_build_global_target_count_section) 좌측 패널이 normal로 복구되어도
        # 다시 입력 가능해지지 않도록 항상 disabled를 유지한다.
        if hasattr(self, "target_count_entry"):
            self.target_count_entry.configure(state="disabled")

    def _iter_children(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self._iter_children(child)

    def make_timestamped_output_path(self, output_path: str, mode: str) -> str:
        # 2026-06-05: 열린 Excel 파일과의 덮어쓰기 충돌을 막기 위해 분 단위 타임스탬프 파일명으로 저장합니다.
        path = Path(output_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        default_stem = "naver_place_premium_db" if mode == "premium" else "naver_place_basic_db"
        stem = path.stem or default_stem
        output_dir = path.parent if str(path.parent) != "." else Path("output")
        return str(output_dir / f"{stem}_{timestamp}.xlsx")

    def show_info(self, title: str, message: str):
        self.after(0, lambda: messagebox.showinfo(title, message))

    def show_error(self, title: str, message: str):
        self.after(0, lambda: messagebox.showerror(title, message))

    def _reset_eta_state(self, total_queries: int):
        self._cancel_eta_timer()
        self.completed_queries = 0
        self.total_pure_time = 0.0
        self.current_query_start_time = None
        self.current_query_pause_time_at_start = 0.0
        self.total_pause_time = 0.0
        self.current_pause_start = None
        self.total_queries = total_queries

    def _reset_collection_stats(self):
        # 총 발견/최종 저장 예정은 이번 실행에서 실제로 집계된 값을 반영한다.
        # 중복 제거는 현재 파이프라인이 쿼리 간 dedup을 추적하지 않으므로
        # (ARCH-300C 계층형 큐 미연결) 항상 0으로 둔다 - 실제로 연결되기 전까지
        # 근거 없는 숫자를 보여주지 않기 위함이다.
        self.total_found_count = 0
        self.total_found_var.set("총 발견: 0개")
        self.duplicate_removed_var.set("중복 제거: 0개")
        self.final_expected_var.set("최종 저장 예정: 0개")

    def _cancel_eta_timer(self):
        if not self.eta_after_id:
            return
        try:
            self.after_cancel(self.eta_after_id)
        except Exception:
            pass
        self.eta_after_id = None

    def _get_total_pause_time_now(self) -> float:
        if self.pause_event.is_set() and self.current_pause_start is not None:
            return self.total_pause_time + (time.time() - self.current_pause_start)
        return self.total_pause_time

    def _record_query_complete(self, query_start_time: float, pause_time_at_start: float):
        pure_time = time.time() - query_start_time - (self._get_total_pause_time_now() - pause_time_at_start)
        self.completed_queries += 1
        self.total_pure_time += max(0.0, pure_time)
        self.current_query_start_time = None
        self.current_query_pause_time_at_start = 0.0

    def _format_eta_seconds(self, seconds: float) -> str:
        remaining_seconds = max(0, int(round(seconds)))
        minutes, seconds = divmod(remaining_seconds, 60)
        if minutes > 0:
            return f"{minutes}분 {seconds}초"
        return f"{seconds}초"

    def _update_eta_loop(self):
        if self.stop_event.is_set():
            self.eta_var.set("예상 남은 시간: 중단됨")
            self.eta_after_id = None
            return

        if self.total_queries and self.completed_queries >= self.total_queries:
            self.eta_var.set("예상 남은 시간: 완료")
            self.eta_after_id = None
            return

        current_query_elapsed = 0.0
        if self.current_query_start_time is not None:
            current_query_elapsed = time.time() - self.current_query_start_time
            current_query_elapsed -= self._get_total_pause_time_now() - self.current_query_pause_time_at_start
            current_query_elapsed = max(0.0, current_query_elapsed)

        remaining_queries = max(0, self.total_queries - self.completed_queries)
        limit = int(self.limit_var.get().strip())
        # 2026-07-06 Stage 3D: premium이 PC full engine(카드별 entryIframe 클릭/wait)으로
        # 전환되어 항목당 소요가 늘어, 첫 쿼리 추정 계수를 3.5 -> 5.0으로 상향(이후 실측 자기보정).
        prior_time = limit * 5.0 if self.mode_var.get() == "premium" else limit * 1.5
        avg_time = (prior_time + self.total_pure_time) / (1 + self.completed_queries)

        remaining_time = (avg_time * remaining_queries) - current_query_elapsed
        if remaining_time <= 0:
            self.eta_var.set("예상 남은 시간: 마무리 중...")
        else:
            self.eta_var.set(f"예상 남은 시간: {self._format_eta_seconds(remaining_time)}")

        self.eta_after_id = self.after(1000, self._update_eta_loop)

    def _start_eta_loop(self):
        self._cancel_eta_timer()
        self.eta_after_id = self.after(1000, self._update_eta_loop)

    def pause_crawl(self):
        if self.pause_event.is_set():
            if self.current_pause_start is not None:
                self.total_pause_time += time.time() - self.current_pause_start
                self.current_pause_start = None
            self.pause_event.clear()
            self.btn_pause.configure(text="일시정지")
            self.log("[ui] 수집을 재개합니다.")
        else:
            self.current_pause_start = time.time()
            self.pause_event.set()
            self.btn_pause.configure(text="계속(Resume)")
            self.log("[ui] 일시정지됨. 계속 버튼을 눌러 재개하세요.")

    def stop_crawl(self):
        if self.pause_event.is_set() and self.current_pause_start is not None:
            self.total_pause_time += time.time() - self.current_pause_start
            self.current_pause_start = None
        self.pause_event.clear()
        self.btn_pause.configure(text="일시정지")
        self.stop_event.set()
        self.eta_var.set("예상 남은 시간: 중단됨")
        self._cancel_eta_timer()
        self.log("[ui] 중지 요청: 현재 진행 중인 수집이 끝난 후 중단됩니다.")
        self.set_status("중지 요청됨")

    def _filter_by_review_count(self, places, min_val, max_val):
        filtered_places = []
        for row in places or []:
            review_text = str((row or {}).get("리뷰수", "")).strip()
            review_digits = re.sub(r"[^\d]", "", review_text)
            review_count = int(review_digits) if review_digits else 0
            if min_val is not None and review_count < min_val:
                continue
            if max_val is not None and review_count > max_val:
                continue
            filtered_places.append(row)
        return filtered_places

    def _validate_single_keyword(self, raw_keyword: str) -> str | None:
        """다중 키워드로 보이는 입력이면 에러 메시지를, 문제 없으면 None을 반환한다.

        _MULTI_KEYWORD_PATTERN(쉼표/세미콜론/슬래시/파이프/가운뎃점/줄바꿈)에
        걸리는 입력만 차단한다. "카페 미용실"처럼 공백만 있는 입력은 하나의
        검색어로 볼 수 있으므로 막지 않는다.
        """
        if _MULTI_KEYWORD_PATTERN.search(raw_keyword):
            return "현재 버전은 키워드 1개만 지원합니다.\n여러 키워드 수집은 안정성 문제로 제공하지 않습니다."
        return None

    def start_crawl(self):
        """Network/List 기본 실행 경로 진입점(button command)."""
        self._start_network_crawl()

    def _start_network_crawl(self):
        """ARCH-300C WIRE-2C-2: Network/List 기본 실행 경로.

        흐름(요청서 §5 그대로): 입력 검증(키워드/per_query_limit/target_count/
        저장 경로/지역) → query_queue 생성 → stop_event.clear() → 실행 중 UI
        상태 적용 → Network worker thread 시작(`_run_network_pipeline_worker`
        경유 → `_run_network_pipeline`). 저장 정책(stop_reason별 저장, 0건
        미저장, exporter 실패 처리)은 WIRE-2C-1의 `_run_network_pipeline`/
        `_export_network_result`/`_network_stop_message`를 그대로 재사용하고
        이번 단계에서 다시 손대지 않는다.
        """
        raw_keyword = self.keyword_input_var.get()
        output_path = self.output_path_var.get().strip()

        if not self.legal_dong_sido_var.get():
            message = "지역 데이터를 불러오지 못해 지역을 선택할 수 없습니다."
            self.log(f"[ui] 실패: {message}")
            self.show_error("지역 선택 오류", message)
            return

        sido = self.legal_dong_sido_var.get()
        if self._legal_dong_loader.list_sigungus(sido) and self.legal_dong_sigungu_var.get() == _LEGAL_DONG_NO_SIGUNGU:
            message = "법정동을 선택하려면 먼저 시군구를 선택하세요."
            self.log(f"[ui] 실패: {message}")
            self.show_error("시군구 선택 오류", message)
            return

        keyword_error = self._validate_single_keyword(raw_keyword)
        if keyword_error:
            self.log(f"[ui] 실패: {keyword_error}")
            self.show_error("키워드 입력 오류", keyword_error)
            return

        keyword = raw_keyword.strip()
        if not keyword:
            self.log("[ui] 실패: 키워드를 입력하세요")
            return

        per_query_limit = _parse_positive_int(self.limit_var.get(), max_value=300)
        if per_query_limit is None:
            message = "검색 조합당 수집 상한은 1~300 사이의 정수로 입력해 주세요."
            self.log(f"[ui] 실패: {message}")
            self.show_error("검색 조합당 수집 상한 오류", message)
            return

        try:
            review_min = _parse_review_bound(self.review_min_var.get())
            review_max = _parse_review_bound(self.review_max_var.get())
        except ValueError:
            message = "리뷰수는 숫자만 입력해야 합니다."
            self.log(f"[ui] 실패: {message}")
            self.show_error("리뷰 필터 오류", message)
            return

        if not output_path:
            self.log("[ui] 실패: 저장 경로가 비어 있습니다")
            return

        query_queue = self._build_collection_queries()
        if not query_queue:
            message = "수집할 지역 또는 보조 검색 항목이 선택되지 않았습니다.\n법정동 선택 또는 보조 검색 항목을 확인해주세요."
            self.log(f"[ui] 실패: {message}")
            self.show_error("지역 선택 오류", message)
            return

        # LEGALDONG-UI-2: 전체 목표 저장 개수는 항상 자동 계산이다(§5) - 화면
        # 표시값(target_count_var)이 아니라 방금 만든 query_queue 길이로 다시
        # 계산해 검증한다(§_recalculate_target_count가 갱신한 표시값과 이 값이
        # 다를 이유는 없지만, 시작 시점 계산을 신뢰의 근거로 삼는다).
        target_count = calculate_legal_dong_target_count(per_query_limit, len(query_queue))
        if target_count <= 0:
            message = "전체 목표 저장 개수를 계산할 수 없습니다. 검색 조합당 수집 상한을 확인하세요."
            self.log(f"[ui] 실패: {message}")
            self.show_error("전체 목표 저장 개수 오류", message)
            return
        self.target_count_var.set(str(target_count))

        # 저장 폴더 생성은 export_places_to_excel이 이미 담당한다(§src/exporter.py
        # output_file.parent.mkdir) - rows가 0건이면 저장 자체를 하지 않으므로
        # (§_export_network_result) 여기서 미리 폴더를 만들지 않는다.
        saved_output_path = self.make_timestamped_output_path(output_path, "network")

        self._reset_eta_state(len(query_queue))
        self._reset_collection_stats()
        self.pause_event.clear()
        self.btn_pause.configure(text="일시정지")
        self.stop_event.clear()
        self.set_running(True)
        self.set_status(f"검색 조합 {len(query_queue)}건 수집 대기 중")
        self.progress_bar.set(0)
        self.progress_percent_var.set(f"0/{len(query_queue)}")
        self.eta_var.set("예상 남은 시간: 계산 중...")
        self.last_output_path = saved_output_path

        collection_mode = self.collection_mode_var.get()

        self.log(f"[ui] Queue 생성 완료: {len(query_queue)}건")
        self.log(f"[ui] 선택 지역={self._current_region_description()}")
        self.log(f"[ui] 키워드={keyword}")
        self.log(f"[ui] 검색 조합당 수집 상한={per_query_limit}, 전체 목표 저장 개수(자동 계산)={target_count}")
        self.log(f"[ui] 저장 경로={saved_output_path}")
        self.log(f"[ui] 수집 모드={collection_mode}")
        if self.new_open_only_var.get():
            self.log("[ui] 새로오픈 전용 목록을 수집합니다.")
        if review_min is not None or review_max is not None:
            self.log(f"[ui] 리뷰 필터(총리뷰수 기준)={review_min if review_min is not None else '제한없음'}~{review_max if review_max is not None else '제한없음'}")

        threading.Thread(
            target=self._run_network_pipeline_worker,
            args=(query_queue, per_query_limit, target_count, saved_output_path, collection_mode),
            daemon=True,
        ).start()

    def _run_network_pipeline_worker(
        self,
        query_queue: list[dict],
        per_query_limit: int,
        target_count: int,
        output_path: str,
        collection_mode: str = "basic",
    ):
        """ARCH-300C WIRE-2C-2: `_run_network_pipeline` 호출을 감싸는 최종
        방어선 + UI 상태 복구 지점.

        여기서 잡는 예외는 collector/orchestrator가 결과 dict조차 반환하지
        못한 예상 밖 오류뿐이다(예: Playwright 시작 자체가 실패) - exporter
        실패는 `_run_network_pipeline`/`_export_network_result`가 이미
        result 메타(export_error)로 처리하므로 여기서 다시 다루지 않는다
        (이중 처리 금지). 정상/예외 종료 어느 쪽이든 finally에서
        `set_running(False)`(내부적으로 self.after(0, ...) 사용)로 좌측
        패널/시작 버튼을 복구한다.
        """
        try:
            self._run_network_pipeline(query_queue, per_query_limit, target_count, output_path, collection_mode=collection_mode)
        except Exception as exc:
            self.log(f"[ui][network] 예상하지 못한 오류: {exc}")
            self.set_status("수집 중 오류가 발생했습니다.")
        finally:
            if self.stop_event.is_set():
                self.after(0, self.eta_var.set, "예상 남은 시간: 중단됨")
                self.after(0, self._cancel_eta_timer)
            self.set_running(False)

    def _set_queue_progress(self, completed: int, total: int):
        progress = completed / total if total else 0
        self.after(0, lambda: self.progress_bar.set(progress))
        self.after(0, self.progress_percent_var.set, f"{completed}/{total}")

    def _note_security_block(self, decision) -> None:
        # SAFE-1: Network 파이프라인의 on_security_block 콜백. CAPTCHA/보안 차단 감지를
        # 인스턴스 상태에 기록만 하고, 실제 중단/저장/안내는 _run_network_pipeline이 담당한다.
        self._security_block_decision = decision
        self.log("[ui] 보안 확인(CAPTCHA) 감지: 안전 중단합니다.")

    def _note_home_progress(self, completed: int, total: int, success_count: int, failure_count: int) -> None:
        """홈페이지·SNS 포함 모드의 home_enrichment_fn on_progress 콜백. 목록
        수집 단계 진행률과는 별개의 상태 텍스트만 갱신한다."""
        self.set_status(f"홈페이지/SNS 정보 수집 중: {completed} / {total} (성공 {success_count}, 실패 {failure_count})")

    def _home_stage_suffix(self, result: dict) -> str:
        """홈페이지·SNS 포함 모드의 home 보강 단계 결과를 완료 문구에 덧붙인다.
        실행되지 않았으면(기본 모드이거나 목록 자체가 차단/0건) 빈 문자열을
        반환한다."""
        attempted_anything = (
            result.get("home_success_count", 0) or result.get("home_failure_count", 0)
            or result.get("home_not_attempted_count", 0)
        )
        if not attempted_anything:
            return ""
        home_stop_reason = result.get("home_stop_reason")
        completion = " 홈페이지/SNS 보강 완료." if home_stop_reason in (None, "") else " 홈페이지/SNS 보강 부분 완료(중단)."
        return (
            f"{completion} 성공 {result.get('home_success_count', 0)}건, "
            f"실패 {result.get('home_failure_count', 0)}건, "
            f"미시도 {result.get('home_not_attempted_count', 0)}건."
        )

    def _network_stop_message(self, result: dict, target_count: int) -> str:
        """저장 결과까지 반영한 최종 상태 문구를 만든다(ARCH-300C WIRE-2C-1).

        우선순위: 저장 실패(export_error) > 저장할 rows 없음(exported=False,
        export_error=False) > stop_reason별 완료/부분 저장 문구. "저장했습니다"는
        실제 저장이 성공(exported=True)했을 때만 쓴다 - export 실패 시 기존
        완료 문구만 보여 성공으로 오인시키지 않기 위해 가장 먼저 검사한다.
        navigation_error_message 전체는 여기서도 노출하지 않는다(로그 전용).
        완료/부분 완료 문구에는 홈페이지·SNS 보강 결과 요약(성공/실패/미시도
        건수)을 덧붙인다(_home_stage_suffix, home_sns 모드가 아니면 빈
        문자열).
        """
        if result.get("export_error"):
            return "수집 결과를 Excel로 저장하지 못했습니다."
        if not result.get("exported"):
            return "저장할 결과가 없습니다."

        final_count = result.get("final_count", 0)
        stop_reason = result.get("stop_reason")
        stage_suffix = self._home_stage_suffix(result)
        if stop_reason == "target_reached":
            return f"전체 목표 개수에 도달했습니다. {final_count}개를 저장했습니다.{stage_suffix}"
        if stop_reason == "queue_exhausted":
            if target_count and final_count < target_count:
                return f"선택한 지역 수집이 완료되었습니다. 목표에는 미달했으며 {final_count}개를 저장했습니다.{stage_suffix}"
            return f"선택한 지역 수집이 완료되었습니다. {final_count}개를 저장했습니다.{stage_suffix}"
        if stop_reason == "security_blocked":
            return f"보안 확인이 감지되어 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
        if stop_reason == "status_429":
            return f"요청 제한이 감지되어 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
        if stop_reason == "navigation_error":
            return f"브라우저 페이지 오류로 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
        if stop_reason == "user_stopped":
            return f"사용자가 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다.{stage_suffix}"
        return f"수집이 종료되었습니다. {final_count}개를 저장했습니다. (stop_reason={stop_reason}){stage_suffix}"

    def _export_network_result(self, result: dict, output_path: str, excel_exporter) -> dict:
        """orchestrator 결과의 rows를 Excel로 저장하는 단일 지점(ARCH-300C WIRE-2C-1).

        저장은 이 메서드 한 곳에서만, 최대 1회 발생한다 - run_collection_plan에는
        on_partial_save를 넘기지 않으므로 중간 저장과 종료 후 저장이 겹치는
        이중 저장은 구조적으로 발생하지 않는다. rows가 비어 있으면(0건) 근거
        없는 빈 Excel 파일을 남기지 않기 위해 excel_exporter를 아예 호출하지
        않는다. result는 orchestrator가 반환한 원본 dict를 그대로 변형하지
        않도록 복사해서 사용한다.
        """
        result = dict(result)
        rows = result.get("rows") or []

        if not rows:
            result.update(exported=False, export_path="", export_error=False, export_error_message="")
            self.log("[ui][network] 저장할 결과가 없어 Excel 저장을 건너뜁니다.")
            return result

        try:
            # mobile/pc 원본 인자는 Network/List 경로에 해당 소스가 없으므로 빈
            # 리스트로 전달한다 - exporter는 3시트 구조를 그대로 유지하되
            # 원본_모바일/원본_PC는 헤더만 있는 빈 시트가 된다(exporter 무수정).
            saved_path = excel_exporter(rows, [], [], output_path)
            result.update(
                exported=True, export_path=str(saved_path or output_path),
                export_error=False, export_error_message="",
            )
            self.log(f"[ui][network] Excel 저장 완료: {result['export_path']} ({len(rows)}건)")
        except Exception as exc:
            # traceback/전체 경로를 사용자 상태 라벨에 노출하지 않는다 - 로그에만
            # 짧게 남기고, 실패를 성공으로 오인하지 않도록 exported=False로 둔다.
            message = f"{type(exc).__name__}: {exc}"[:200]
            result.update(exported=False, export_path="", export_error=True, export_error_message=message)
            self.log(f"[ui][network] Excel 저장 실패: {message}")

        return result

    def _run_network_pipeline(
        self,
        query_queue: list[dict],
        per_query_limit: int,
        target_count: int,
        output_path: str,
        *,
        collection_mode: str = "basic",
        collector_factory=ApolloFirstListCollector,
        orchestrator=run_collection_plan,
        excel_exporter=export_places_to_excel,
        home_enrichment_fn=enrich_home_details,
    ) -> dict:
        """ARCH-300C WIRE-2C-1: Network/List 제품 흐름 worker + Excel 저장 연결.

        기본 `collector_factory`는 `ApolloFirstListCollector`(1페이지 메인
        placeList(...) Apollo 파싱 + 2페이지 이후 자연 발생 GraphQL, DOM
        스크롤 없음)다. 새 두 모드(`collection_mode`)는 이
        `ApolloFirstListCollector` 기반 목록 수집을 공통으로 사용하고,
        `collection_mode="home_sns"`일 때만 목록 수집 이후 별도 단계
        (`home_enrichment_fn`)로 place_id당 home HTML 보강을 추가한다.

        collector_factory/orchestrator/excel_exporter/home_enrichment_fn은
        의존성 주입 지점이다 - 기본값 참조만으로는 Playwright 시작도 파일
        저장도 발생하지 않는다(실제로 호출될 때만 부작용이 생긴다). 이번
        단계 테스트는 항상 fake를 주입해 실제 브라우저/파일 저장을 실행하지
        않는다.

        저장은 collector(브라우저/session/context)가 완전히 종료된 뒤
        `_export_network_result`에서만 수행한다. 이 worker의 책임은
        collected_at 생성 → collector 생성 → run_collection_plan 호출 →
        collector 종료(Native Edge CDP owned process 종료 + profile lock
        해제) → `collection_mode="home_sns"`면 home_enrichment_fn으로
        홈페이지/SNS 보강 → rows 확인 후 Excel 저장(0건이면 건너뜀) → 결과를
        로그/상태에 반영 → result 반환까지다.

        홈페이지/SNS 보강은 목록 수집 browser context가 완전히 닫힌(sync
        Playwright + owned process가 전부 정리된) *이후에* 별도 asyncio
        event loop(`home_enrichment_fn` 내부에서 `asyncio.run()`)로 실행한다
        - 쿠키를 복사해 넘기지 않는다. `home_enrichment_fn`이 같은 persistent
        profile을 가리키는 새 Native Edge/Chrome 프로세스에 순차적으로(동시
        실행 아님 - profile lock으로 보장됨) 다시 연결해 그 실제
        BrowserContext.request를 사용한다(5Z 벤치마크와 동일한 메커니즘,
        PAGE300-6A-FIX1).
        """
        collected_at = datetime.now().strftime("%Y-%m-%d")
        total = len(query_queue)
        self.log(f"[ui][network] Queue 생성 완료: {total}건")
        self.log(f"[ui][network] 검색 조합당 수집 상한={per_query_limit}, 전체 목표 저장 개수={target_count}")

        def _network_should_continue() -> bool:
            # NETWORK-CONTROLS-1: 다음 job(검색 조합) 시작 전(§5 요청서) -
            # 일시정지 중이면 여기서 대기한다. 동기 컨텍스트(worker thread,
            # Tk UI 스레드 아님)라 블로킹 대기가 안전하다. stop_event가
            # pause_event보다 우선하므로 대기 중 중지되면 즉시 빠져나온다.
            wait_while_paused(self.pause_event, self.stop_event)
            return not self.stop_event.is_set()

        with collector_factory(collected_at=collected_at, pause_event=self.pause_event, stop_event=self.stop_event) as collector:
            result = orchestrator(
                query_queue,
                per_query_limit=per_query_limit,
                target_count=target_count,
                collected_at=collected_at,
                collect_query=collector.collect_query,
                should_continue=_network_should_continue,
                on_security_block=self._note_security_block,
            )

        # with 블록 종료: collector의 browser/context/Playwright(sync, Native
        # Edge CDP owned process 포함)가 완전히 정리된 상태다(process 종료 +
        # profile lock 해제). 홈페이지·SNS 보강은 여기서부터 별도 asyncio
        # event loop(home_enrichment_fn 내부)로 실행한다 - 쿠키를 복사해
        # 넘기지 않는다. home_enrichment_fn이 같은 persistent profile을
        # 가리키는 새 Native Edge/Chrome에 다시 연결해 실제 BrowserContext의
        # 세션을 그대로 사용한다(PAGE300-6A-FIX1).
        result["home_stop_reason"] = None
        result["home_security_blocked"] = False
        result["home_success_count"] = 0
        result["home_failure_count"] = 0
        result["home_not_attempted_count"] = 0
        rows = result.get("rows") or []
        if collection_mode == "home_sns" and rows and not result.get("security_blocked"):
            self.set_status(f"홈페이지/SNS 보강 준비 중... (총 {len(rows)}건)")
            self.log(f"[ui][network][home] 홈페이지/SNS 보강 시작: 대상 {len(rows)}건")
            home_result = home_enrichment_fn(
                rows,
                should_continue=lambda: not self.stop_event.is_set(),
                on_progress=self._note_home_progress,
                pause_event=self.pause_event,
                stop_event=self.stop_event,
            )
            result["rows"] = home_result["rows"]
            result["home_stop_reason"] = home_result["stop_reason"]
            result["home_security_blocked"] = home_result["security_blocked"]
            result["home_success_count"] = home_result["home_success_count"]
            result["home_failure_count"] = home_result["failure_count"]
            result["home_not_attempted_count"] = home_result["not_attempted_count"]

            # PAGE300-6G-R1: first_pass/retry_pass가 없는 fake(구 버전 테스트
            # fixture 등)와도 호환되도록 .get(..., 기본값)만 사용한다.
            first_pass = home_result.get("first_pass") or {}
            retry_pass = home_result.get("retry_pass") or {}
            self.log(
                "[ui][network][home] 보강 종료: "
                f"1차 성공={first_pass.get('success', home_result['home_success_count'])}, "
                f"1차 실패={first_pass.get('failed', home_result['failure_count'])}, "
                f"재시도 성공={retry_pass.get('success', 0)}, "
                f"최종 실패={home_result['failure_count']}, "
                f"미시도={home_result['not_attempted_count']}"
            )

            final_failures = home_result.get("final_failures") or []
            total_final_failures = len(final_failures)
            for index, failure in enumerate(final_failures, start=1):
                self.log(
                    f"[ui][network][home][실패 {index}/{total_final_failures}] "
                    f"업체명={failure.get('name', '')} place_id={failure.get('place_id', '')} "
                    f"원인={failure.get('status', '')} HTTP={failure.get('http_status')} "
                    f"시도={failure.get('attempt', '')} 응답시간={failure.get('elapsed_ms', '')}ms"
                )

            diagnostics_report = home_result.get("diagnostics_report")
            if diagnostics_report is not None:
                diagnostics_filename = f"home_enrichment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                try:
                    DEFAULT_DIAGNOSTICS_ROOT.mkdir(parents=True, exist_ok=True)
                    artifact = save_json_artifact(
                        DEFAULT_DIAGNOSTICS_ROOT, diagnostics_filename, diagnostics_report
                    )
                    if artifact.success:
                        self.log(f"[ui][network][home] 실패 진단 저장: {artifact.path}")
                    else:
                        self.log(f"[ui][network][home] 진단 저장 실패: {artifact.error_message}")
                except Exception as exc:
                    self.log(f"[ui][network][home] 진단 저장 실패: {type(exc).__name__}: {exc}")

        self.log(
            f"[ui][network] stop_reason={result.get('stop_reason')}, "
            f"executed={result.get('executed_query_count')}, skipped={result.get('skipped_query_count')}, "
            f"final_count={result.get('final_count')}"
        )
        if result.get("navigation_error"):
            nav_message = (result.get("navigation_error_message") or "")[:120]
            self.log(f"[ui][network] navigation_error 상세(로그 전용): {nav_message}")

        duplicate_removed_count = result.get("duplicate_removed_count", 0)
        self.after(0, self.duplicate_removed_var.set, f"중복 제거: {duplicate_removed_count}개")

        review_filter_stats = result.get("review_filter_stats")
        if review_filter_stats is not None:
            self.log(
                "[ui][network] 리뷰 필터: 후보 "
                f"{review_filter_stats['candidate']}건 중 채택 {review_filter_stats['accepted']}건 / "
                f"제외 {review_filter_stats['candidate'] - review_filter_stats['accepted']}건"
                f"(최소미만 {review_filter_stats['rejected_by_min']}, "
                f"최대초과 {review_filter_stats['rejected_by_max']}, "
                f"확인불가 {review_filter_stats['unknown']})"
            )

        result = self._export_network_result(result, output_path, excel_exporter)

        self.set_status(self._network_stop_message(result, target_count))
        return result

    def open_output_folder(self):
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(output_dir.resolve())


def run_app():
    app = SalesDbCrawlerApp()
    app.mainloop()
