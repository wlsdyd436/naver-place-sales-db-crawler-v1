# 2026-06-25: V2.0 CustomTkinter UI. 기존 크롤링/파싱/엑셀 저장 파이프라인은 유지합니다.
# 2026-07-09 UI-CLEANUP-1: 다중 키워드/수집모드 선택/온라인 채널 필터를 제거하고
# 단일 키워드 + 자동 세분화 미리보기 중심으로 정리했다(구조 변경, 상세 설계는
# PROJECT_STATE.md 2026-07-09 UI-CLEANUP-1 기록 참고). [DB 수집] 탭과, 아직
# 실제 기능이 없는 [순위추적] V2 예정 탭으로 분리했다.
import contextlib
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from src.crawler import crawl_places
from src.exporter import export_places_to_excel
from src.merger import safe_merge_places
from src.parser import parse_places
from src.pc_crawler import crawl_places_pc
from src.pc.config import DiagnosticConfig
from src.pc.detail_scraper import build_full_collector
from src.pc.network_browser_collector import NetworkBrowserCollector
from src.pc.network_pipeline import run_collection_plan
from src.pc.pipeline import collect_pc_full
from src.pc.region_data import load_region_layers


REGION_DATA = {
    "서울특별시": ["강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구", "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구", "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"],
    "부산광역시": ["강서구", "금정구", "기장군", "남구", "동구", "동래구", "부산진구", "북구", "사상구", "사하구", "서구", "수영구", "연제구", "영도구", "중구", "해운대구"],
    "대구광역시": ["군위군", "남구", "달서구", "달성군", "동구", "북구", "서구", "수성구", "중구"],
    "인천광역시": ["강화군", "계양구", "남동구", "동구", "미추홀구", "부평구", "서구", "연수구", "옹진군", "중구"],
    "광주광역시": ["광산구", "남구", "동구", "북구", "서구"],
    "대전광역시": ["대덕구", "동구", "서구", "유성구", "중구"],
    "울산광역시": ["남구", "동구", "북구", "울주군", "중구"],
    "세종특별자치시": ["세종시"],
    "경기도": ["가평군", "고양시", "과천시", "광명시", "광주시", "구리시", "군포시", "김포시", "남양주시", "동두천시", "부천시", "성남시", "수원시", "시흥시", "안산시", "안성시", "안양시", "양주시", "양평군", "여주시", "연천군", "오산시", "용인시", "의왕시", "의정부시", "이천시", "파주시", "평택시", "포천시", "하남시", "화성시"],
}

# ARCH-300C PoC-6~9에서 만든 강동구 샘플 지역 데이터(법정동/역상권)를 세부구역
# 미리보기에 읽기 전용으로 재사용한다. 아직 강동구 외 지역은 데이터가 없으며,
# 그 경우 "준비 중" 문구로 처리한다(§region_data.load_region_layers가 미존재
# city/gu에 대해 빈 리스트를 반환하므로 예외 처리 불필요).
REGIONS_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "regions_kr_sample.json"

# 다중 키워드로 보이는 입력을 차단하기 위한 패턴(쉼표/세미콜론/슬래시/파이프/
# 가운뎃점/줄바꿈). 다중 키워드 UI(추가/삭제/목록) 자체를 없앤 이유는 ①큐가
# 길어질수록 CAPTCHA 누적 리스크가 커지고(PoC-4~9 실측) ②제품 문구/기대치가
# 단일 검색어 기준으로 단순해지기 때문이다 - REGION-DATA-1/UI-CLEANUP-1 설계
# 참고. "카페 미용실"처럼 공백만 있는 입력은 하나의 실제 검색어일 수 있으므로
# 의도적으로 차단 대상에서 제외한다(UI-CLEANUP-1B).
_MULTI_KEYWORD_PATTERN = re.compile(r"[,;\n/|·]")

# UI-CLEANUP-1C: 시/군/구를 여러 개 선택할 수 있는 구조로 바꾸면서, 나중에
# 또 갈아엎지 않도록 처음부터 "여러 구 기준" 쿼리 생성으로 설계한다(사용자
# 피드백: 구 선택은 결국 다중이 될 거라 지금 정리). 기본 선택 구는 세부구역
# 샘플 데이터가 있는 강동구 - 다른 시/도로 바꿔 강동구가 없으면 그 시/도의
# 첫 번째 구를 기본 선택한다.
_DEFAULT_DISTRICT = "강동구"

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

# ARCH-300C WIRE-2C-2: Network/List가 기본 실행 경로가 되면서(§start_crawl,
# _DEFAULT_COLLECTION_ENGINE) per_query_limit(검색 조합당 수집 상한, limit_var)의
# "진짜" 권장 기본값 30을 다시 적용한다 - WIRE-2B-2A에서 300으로 되돌린 이유
# (legacy _run_queue_pipeline이 limit_var를 유일한 "수집 개수" 입력으로 그대로
# 쓰던 문제)는 legacy가 더 이상 기본 실행 경로가 아니게 되면서 해소됐다.
# legacy 경로(_start_legacy_crawl, _DEFAULT_COLLECTION_ENGINE="legacy"로 내부
# 전환 시에만 진입)는 이 기본값 변경과 무관하게 여전히 존재한다.
_DEFAULT_PER_QUERY_LIMIT = "30"
_DEFAULT_TARGET_COUNT = "300"

# ARCH-300C WIRE-2C-2: 기본 수집 엔진을 고르는 내부 전환 지점이다. 사용자
# 화면에는 엔진 선택 UI를 노출하지 않는다 - "network"가 기본 실행 경로이고,
# "legacy"는 문제 발생 시 코드 수정으로만 되돌릴 수 있는 내부 롤백 경로다
# (§start_crawl/_start_legacy_crawl/_start_network_crawl).
_DEFAULT_COLLECTION_ENGINE = "network"

def _parse_positive_int(raw: str) -> int | None:
    """문자열을 양의 정수로 파싱한다(WIRE-2B-2: per_query_limit/target_count
    공용 입력 검증 helper, Tk 불필요).

    비어있음/공백/비정수/0/음수는 전부 None을 반환한다(예외를 던지지 않음 -
    호출자가 None 여부로 차단 여부를 판단하고, 필드별 로그 메시지는 호출자가
    작성한다).
    """
    try:
        value = int((raw or "").strip())
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def build_collection_queries(city: str, district_selections: list[dict], keyword: str) -> list[dict]:
    """구별 선택 상태 + 키워드로 최종 수집 쿼리 목록을 만드는 순수 함수(Tk 불필요).

    district_selections: 화면에 표시된 순서 그대로, 각 구에 대해
      {"district": str, "has_subregion_data": bool, "selected_subregions": [str, ...]}
    형태의 dict 목록. has_subregion_data가 False면 "{city} {district} {keyword}"
    구 기준 fallback 쿼리 1개를 만든다. True인데 selected_subregions가 비어
    있으면(법정동/역상권을 전부 체크 해제) 그 구는 쿼리를 만들지 않고 건너뛴다
    (세부구역 데이터가 있는 구에서 전부 해제하면 수집 대상에서 제외되어야
    하기 때문). True이고 목록이 있으면 세부구역마다 "{city} {district}
    {subregion} {keyword}" 쿼리를 만든다.

    entry는 선택적으로 "legal_dongs": [str, ...] / "landmarks": [str, ...]
    (region_data.load_region_layers/get_selected_subregions과 동일한 이름의
    원본 목록)를 함께 넘길 수 있다. selected_subregions의 각 항목이 이 중
    어느 목록에 속하는지에 따라 아래 source_layer를 분류한다. 넘기지 않으면
    (기존 테스트 등 하위 호환 호출) "unknown"으로 분류한다 - 실제 UI 인스턴스
    메서드(_build_collection_queries, ARCH-300C WIRE-1B)는 이 두 목록을 분리
    전달하므로 실제 화면에서 생성되는 job은 legal_dong/landmark/fallback으로만
    분류되고 unknown은 발생하지 않는다.

    반환은 `_run_queue_pipeline`이 그대로 받을 수 있는 job 형태
    [{"region": ..., "keyword": keyword, "query": ...}, ...]에 내부 메타
    source_city/source_district/source_subregion/source_layer를 추가한
    것이다 - 기존 region/keyword/query 키와 값은 그대로 유지되며, 이
    source_* 필드들은 dedup/orchestrator 진단용일 뿐 Excel에는 노출되지
    않는다(exporter가 MERGED_COLUMNS로만 투영). source_layer 후보:
    "legal_dong" / "landmark" / "fallback"(세부구역 데이터 없는 구) /
    "unknown"(legal_dongs/landmarks 미전달 시). 중복 쿼리는 제거하되 처음
    등장한 순서는 유지한다.
    """
    jobs: list[dict] = []
    seen_queries: set = set()
    for entry in district_selections:
        district = entry["district"]
        if entry.get("has_subregion_data"):
            legal_dongs = set(entry.get("legal_dongs") or [])
            landmarks = set(entry.get("landmarks") or [])
            for subregion in entry.get("selected_subregions") or []:
                region_label = f"{city} {district} {subregion}"
                query = f"{region_label} {keyword}"
                if query in seen_queries:
                    continue
                seen_queries.add(query)
                if subregion in legal_dongs:
                    source_layer = "legal_dong"
                elif subregion in landmarks:
                    source_layer = "landmark"
                else:
                    source_layer = "unknown"
                jobs.append({
                    "region": region_label,
                    "keyword": keyword,
                    "query": query,
                    "source_city": city,
                    "source_district": district,
                    "source_subregion": subregion,
                    "source_layer": source_layer,
                })
        else:
            region_label = f"{city} {district}"
            query = f"{region_label} {keyword}"
            if query in seen_queries:
                continue
            seen_queries.add(query)
            jobs.append({
                "region": region_label,
                "keyword": keyword,
                "query": query,
                "source_city": city,
                "source_district": district,
                "source_subregion": "",
                "source_layer": "fallback",
            })
    return jobs


class LogWriter:
    # 2026-06-04: crawler의 print 로그를 UI 로그창으로 전달합니다.
    def __init__(self, callback):
        self.callback = callback

    def write(self, text):
        if text.strip():
            self.callback(text.rstrip())

    def flush(self):
        pass


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

        self.selected_city_var = ctk.StringVar(value="서울특별시")
        self.keyword_input_var = ctk.StringVar(value="카페")
        # ARCH-300C WIRE-2C-2: 기본 실행 경로가 Network/List(_start_network_crawl)
        # 로 바뀌면서 이 값은 진짜 per_query_limit 의미(검색 조합 하나당 상한,
        # run_collection_plan에 그대로 전달)로 쓰인다. legacy 경로
        # (_start_legacy_crawl, 내부 롤백 시에만 진입)에서는 기존과 동일하게
        # 각 검색 조합(쿼리) 하나당 상한으로만 쓰이고 쿼리 간 dedup은 없다.
        self.limit_var = ctk.StringVar(value=_DEFAULT_PER_QUERY_LIMIT)
        # ARCH-300C WIRE-2B-2: 전역 place_id dedup 이후 최종 저장할 목표
        # 개수(target_count). run_collection_plan(WIRE-1)이 이 값에 도달하면
        # 남은 검색 조합을 실행하지 않고 조기 종료한다(실제 orchestrator 동작과
        # 일치 - "300개 보장"이 아니라 "도달 시 남은 조합 중단"). legacy 경로
        # (_run_queue_pipeline)는 이 값을 사용하지 않는다.
        # WIRE-2C-2: Network/List가 기본 실행 경로가 되면서 이 값을 실제로
        # start_crawl(_start_network_crawl)이 읽고 검증한다(§_parse_positive_int)
        # - 입력 위젯 활성화(§_build_global_target_count_section).
        self.target_count_var = ctk.StringVar(value=_DEFAULT_TARGET_COUNT)
        # 수집모드 선택 UI는 제거하지만, 내부적으로는 기존 PC 상세 수집 경로
        # (premium)를 그대로 기본값으로 사용한다(엔진 코드는 삭제하지 않음).
        self.mode_var = ctk.StringVar(value="premium")
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

        # UI-CLEANUP-1C: 구를 여러 개 선택할 수 있으므로 선택 상태를 전부
        # "구 이름"을 키로 하는 딕셔너리로 관리한다.
        #   selected_district_vars: {구이름: BooleanVar}  - 구 체크박스 상태
        #   _subdivision_layers:    {구이름: {"legal_dongs": [...], "landmarks": [...]}}
        #                           - 구별로 한 번 로드한 세부구역 데이터 캐시
        #   region_selection_vars:  {구이름: {"legal_dongs": {이름: BooleanVar},
        #                                      "landmarks": {이름: BooleanVar}}}
        # 체크박스가 화면에 그려져 있지 않아도(접힌 상태) 항상 최신 선택 상태를
        # 담고 있어야 한다 - 요약 문구/예상 쿼리 수/시작 시 검증이 접힌
        # 상태에서도 정확해야 하기 때문이다.
        self.selected_district_vars: dict = {}
        self._subdivision_layers: dict = {}
        self.region_selection_vars: dict = {}

        self._build_ui()
        self._reload_district_data()

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
        self._build_subdivision_section()
        self._build_keyword_section()
        self._build_filter_section()
        self._build_target_count_section()
        self._build_global_target_count_section()
        self._build_dashboard_section()
        self._build_control_section()
        self._build_log_section()

        self._build_rank_tracking_tab()
        self._build_policy_tab()

    def _build_region_section(self):
        ctk.CTkLabel(self.left_panel, text="1. 지역 선택", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        region_frame = ctk.CTkFrame(self.left_panel)
        region_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        region_frame.grid_columnconfigure(0, weight=1)

        # 시/도는 드롭다운 1개 선택을 유지한다(여러 시/도 동시 선택은 이번
        # 범위 밖). 시/군/구는 체크박스 다중 선택으로 바꾼다 - 나중에 다시
        # 구조를 바꾸지 않도록, 쿼리 생성(get_selected_districts +
        # build_collection_queries)을 처음부터 "여러 구"를 전제로 짰다.
        ctk.CTkLabel(region_frame, text="시/도", anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self.city_dropdown = ctk.CTkOptionMenu(
            region_frame, variable=self.selected_city_var,
            values=list(REGION_DATA.keys()), command=self._on_city_changed,
        )
        self.city_dropdown.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))

        ctk.CTkLabel(region_frame, text="시/군/구 (여러 개 선택 가능)", anchor="w").grid(row=2, column=0, sticky="w", padx=12, pady=(0, 2))
        self.district_checkbox_frame = ctk.CTkFrame(region_frame, fg_color="transparent")
        self.district_checkbox_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 2))
        # 3열은 "영등포구"처럼 4글자 구 이름이 잘리는 문제가 있어 2열로 줄이고
        # 각 열에 weight를 줘 왼쪽 패널 폭(_LEFT_PANEL_MIN_WIDTH)을 넉넉히
        # 나눠 갖게 한다(고정 폭을 텍스트에 억지로 맞추지 않기 위함).
        self.district_checkbox_frame.grid_columnconfigure((0, 1), weight=1)

        self.district_summary_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            region_frame, textvariable=self.district_summary_var, anchor="w", text_color="gray",
        ).grid(row=4, column=0, sticky="w", padx=12, pady=(2, 10))

    def _render_district_checkboxes(self):
        """selected_district_vars(현재 시/도의 구 목록)를 2열 체크박스로 그린다."""
        for child in self.district_checkbox_frame.winfo_children():
            child.destroy()
        row = 0
        col = 0
        for district, var in self.selected_district_vars.items():
            ctk.CTkCheckBox(
                self.district_checkbox_frame, text=district, variable=var,
                command=lambda d=district: self._on_district_toggle(d),
            ).grid(row=row, column=col, sticky="w", padx=8, pady=4)
            col += 1
            if col >= 2:
                col = 0
                row += 1
        self._update_district_summary()

    def _update_district_summary(self):
        self.district_summary_var.set(f"선택한 구: {len(self.get_selected_districts())}개")

    def get_selected_districts(self) -> list[str]:
        """현재 체크된 구 이름을 REGION_DATA 순서 그대로 반환한다."""
        return [district for district, var in self.selected_district_vars.items() if var.get()]

    def _build_subdivision_section(self):
        ctk.CTkLabel(self.left_panel, text="2. 세부구역 설정", font=ctk.CTkFont(size=14, weight="bold")).grid(row=2, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        subdivision_frame = ctk.CTkFrame(self.left_panel)
        subdivision_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        subdivision_frame.grid_columnconfigure(0, weight=1)

        # 자동 세분화 자체는 여전히 화면 표시/선택 상태 보관용이며, 실제 검색
        # 쿼리 생성에는 아직 연결되지 않는다(ARCH-300C 계층형 큐는 PoC-6~9
        # 실험 단계이며 파이프라인 미연결 - get_selected_subregions()가 그
        # 연결 지점이 될 확장 포인트다).
        self.auto_subdivide_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            subdivision_frame, text="선택한 구를 동/상권 단위로 자동 세분화",
            variable=self.auto_subdivide_var, command=self._refresh_subdivision_view,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        # 선택된 구 수 + 예상 수집 쿼리 수(실제 build_collection_queries 결과
        # 기준)를 함께 보여준다 - 선택이 바뀔 때마다 _update_subdivision_summary
        # 에서 갱신한다.
        self.subdivision_summary_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            subdivision_frame, textvariable=self.subdivision_summary_var,
            justify="left", anchor="w", text_color="gray",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))

        # UI-CLEANUP-1E: 안전 안내 취지는 유지하되(SAFE-1과 동일 - 우회 표현
        # 없이 사실만 전달) 한 줄로 축약한다. 자세한 배경(쿼리 수 증가 이유 등)은
        # 안내·정책 탭에서 다룰 예정이다.
        ctk.CTkLabel(
            subdivision_frame,
            text="보안 확인 감지 시 수집을 중단하고 현재 결과를 저장합니다.",
            anchor="w", text_color="gray", font=ctk.CTkFont(size=11),
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(0, 6))

        # UI-CLEANUP-1D-A: 법정동/역상권 체크박스 목록을 왼쪽 패널에 직접 펼치면
        # (구가 여러 개일수록) 패널이 매우 길어지고, CTkScrollableFrame 안에서
        # 큰 위젯 트리를 자주 destroy/recreate하면서 스크롤 잔상처럼 보이는
        # 렌더링 문제가 있었다. 그래서 메인 화면에는 요약 + 버튼만 두고,
        # 실제 법정동/역상권 체크박스는 별도 팝업(Toplevel)에서만 그린다
        # (§_open_subregion_popup). 행정동은 팝업에서도 표시하지 않는다(법정동
        # 기준으로 300개 목표를 채운다는 REGION-DATA-1 설계 결론 - 행정동을
        # 섞으면 PoC-5에서 확인된 것처럼 같은 지역이 이중 집계될 위험이 있다).
        # 체크박스 상태는 get_selected_subregions()를 거쳐 build_collection_queries가
        # 실제 검색 쿼리에 반영한다.
        self.subregion_popup_button = ctk.CTkButton(
            subdivision_frame, text="수집할 동/상권 설정", command=self._open_subregion_popup,
        )
        self.subregion_popup_button.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 10))

        self._subregion_popup = None
        self._subregion_popup_container = None

    def _build_keyword_section(self):
        ctk.CTkLabel(self.left_panel, text="3. 키워드 입력", font=ctk.CTkFont(size=14, weight="bold")).grid(row=4, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        keyword_frame = ctk.CTkFrame(self.left_panel)
        keyword_frame.grid(row=5, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
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
        ctk.CTkLabel(self.left_panel, text="4. 필터", font=ctk.CTkFont(size=14, weight="bold")).grid(row=6, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        filter_frame = ctk.CTkFrame(self.left_panel)
        filter_frame.grid(row=7, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        filter_frame.grid_columnconfigure((1, 3), weight=1)

        # 온라인 채널(블로그/인스타 등 존재) 필터는 제거한다: 홈페이지/인스타/
        # 블로그는 이제 기본 수집 컬럼으로 항상 가져오므로 "있는 업체만" 필터가
        # 더 이상 필요하지 않다. 단, 엑셀 결과의 홈페이지/인스타/블로그 컬럼
        # 자체는 그대로 유지한다(exporter.MERGED_COLUMNS 변경 없음).
        # ARCH-300C WIRE-2C-2: Network/List 매핑에서는 새로오픈여부를 신뢰성
        # 있게 제공하지 않으므로(§_start_network_crawl에서 항상 False로
        # 정규화), 기본 실행 경로에서 동작하는 필터처럼 보이지 않도록 체크박스를
        # disabled로 두고 안내 문구를 보여준다 - 체크된 상태로 disabled되면
        # "적용된 것"으로 오해할 수 있어 초기값도 항상 False다(§new_open_only_var).
        self.new_open_checkbox = ctk.CTkCheckBox(filter_frame, text="새로오픈 업체만 수집", variable=self.new_open_only_var, state="disabled")
        self.new_open_checkbox.grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            filter_frame,
            text=(
                "현재 버전에서는 새로오픈 여부를 정확하게 판별할 수 없어 사용할 수 없습니다.\n"
                "Excel의 '새로오픈여부' 열은 유지되며 현재 결과에서는 빈칸으로 저장됩니다."
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
        ctk.CTkLabel(self.left_panel, text="5. 검색 조합당 수집 상한", font=ctk.CTkFont(size=14, weight="bold")).grid(row=8, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        target_frame = ctk.CTkFrame(self.left_panel)
        target_frame.grid(row=9, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
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
        # ARCH-300C WIRE-2B-2: 검색 조합당 상한(§_build_target_count_section,
        # per_query_limit)과는 별개로, 전역 dedup 이후 최종 저장할 목표
        # 개수(target_count)를 입력받는다. run_collection_plan이 실제로 "목표
        # 도달 시 남은 검색 조합 중단"을 구현하고 있으므로 그 문구만 사용하고,
        # "300개 보장"처럼 과장된 표현은 쓰지 않는다.
        # WIRE-2C-2: Network/List가 기본 실행 경로가 되어 start_crawl
        # (_start_network_crawl)이 이 값을 실제로 읽고 검증하므로 입력 위젯을
        # 활성화한다(WIRE-2B-2A 당시의 임시 disabled 안내 문구는 더 이상
        # 사실이 아니므로 제거했다).
        ctk.CTkLabel(self.left_panel, text="6. 전체 목표 저장 개수", font=ctk.CTkFont(size=14, weight="bold")).grid(row=10, column=0, sticky="w", padx=14, pady=_SECTION_TITLE_PADY)
        global_target_frame = ctk.CTkFrame(self.left_panel)
        global_target_frame.grid(row=11, column=0, sticky="ew", padx=14, pady=_SECTION_BODY_PADY)
        global_target_frame.grid_columnconfigure(0, weight=1)

        self.target_count_entry = ctk.CTkEntry(global_target_frame, textvariable=self.target_count_var, width=100)
        self.target_count_entry.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            global_target_frame,
            text=(
                "여러 검색 조합의 결과를 합치고 중복을 제거한 뒤\n"
                "Excel에 최종 저장할 최대 업체 수입니다.\n"
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

    def _on_city_changed(self, _city: str):
        self._reload_district_data()

    def _reload_district_data(self):
        """시/도가 바뀔 때 그 시/도의 구 목록으로 선택 상태를 완전히 새로
        만든다(다른 시/도의 세부구역 데이터는 이어받지 않는다). 기본으로
        _DEFAULT_DISTRICT(강동구)가 있으면 그것을, 없으면 첫 번째 구를
        선택한다.
        """
        city = self.selected_city_var.get()
        districts = REGION_DATA.get(city, [])
        default_district = _DEFAULT_DISTRICT if _DEFAULT_DISTRICT in districts else (districts[0] if districts else None)

        self.selected_district_vars = {name: ctk.BooleanVar(value=(name == default_district)) for name in districts}
        self._subdivision_layers = {}
        self.region_selection_vars = {}

        self._render_district_checkboxes()
        if default_district:
            self._ensure_subregion_data_loaded(default_district)
        self._render_subregion_selection_if_popup_open()
        self._refresh_subdivision_view()

    def _on_district_toggle(self, district: str):
        """구 체크박스를 눌렀을 때: 새로 체크된 구면 세부구역 데이터를 로드하고
        (전체 선택으로 초기화), 세부구역 화면/요약/예상 쿼리 수를 갱신한다.
        체크 해제된 구는 region_selection_vars에서 지우지 않는다 - 다시
        체크하면 이전 선택 상태가 그대로 남아 있어야 하기 때문이다.
        """
        var = self.selected_district_vars.get(district)
        if var is not None and var.get():
            self._ensure_subregion_data_loaded(district)
        self._render_subregion_selection_if_popup_open()
        self._update_district_summary()
        self._refresh_subdivision_view()

    def _ensure_subregion_data_loaded(self, district: str):
        """이 구의 법정동/역상권 데이터가 아직 로드되지 않았으면 지금 로드하고
        전체 선택 상태로 초기화한다(요구사항: 새로 선택된 구는 전체 선택)."""
        if district in self._subdivision_layers:
            return
        city = self.selected_city_var.get()
        layers = load_region_layers(REGIONS_SAMPLE_PATH, city, district)
        self._subdivision_layers[district] = layers
        self.region_selection_vars[district] = {
            "legal_dongs": {name: ctk.BooleanVar(value=True) for name in layers.get("legal_dongs", [])},
            "landmarks": {name: ctk.BooleanVar(value=True) for name in layers.get("landmarks", [])},
        }

    def _is_subregion_popup_open(self) -> bool:
        popup = self._subregion_popup
        return popup is not None and popup.winfo_exists()

    def _open_subregion_popup(self):
        """"수집할 동/상권 설정" 버튼 클릭 시 팝업(Toplevel)을 연다.

        이미 열려 있으면 새로 만들지 않고 기존 창을 앞으로 가져온다(중복
        생성/상태 꼬임 방지). 팝업 안의 체크박스는 region_selection_vars의
        BooleanVar를 그대로 공유하므로, 체크/해제는 즉시 실제 상태에 반영된다
        - "적용"/"닫기"는 팝업을 닫고 메인 화면 요약을 갱신하는 역할만 한다.
        """
        if self._is_subregion_popup_open():
            self._subregion_popup.lift()
            self._subregion_popup.focus_force()
            return

        popup = ctk.CTkToplevel(self)
        popup.title("수집할 동/상권 설정")
        popup.geometry("560x620")
        popup.minsize(480, 420)
        popup.transient(self)
        popup.grab_set()
        popup.grid_rowconfigure(0, weight=1)
        popup.grid_columnconfigure(0, weight=1)
        # 사용자가 팝업의 닫기(X) 버튼을 눌러도 메인 요약이 갱신되도록 연결.
        popup.protocol("WM_DELETE_WINDOW", self._close_subregion_popup)

        container = ctk.CTkScrollableFrame(popup)
        container.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        container.grid_columnconfigure((0, 1, 2), weight=1)

        button_row = ctk.CTkFrame(popup, fg_color="transparent")
        button_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkButton(button_row, text="전체 선택", width=100, command=lambda: self._set_all_subregions(True)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(button_row, text="전체 해제", width=100, fg_color="gray", command=lambda: self._set_all_subregions(False)).pack(side="left")
        ctk.CTkButton(button_row, text="닫기", width=100, fg_color="gray", command=self._close_subregion_popup).pack(side="right")
        ctk.CTkButton(button_row, text="적용", width=100, command=self._close_subregion_popup).pack(side="right", padx=(0, 6))

        self._subregion_popup = popup
        self._subregion_popup_container = container
        self._render_subregion_selection()

    def _close_subregion_popup(self):
        """팝업의 적용/닫기/창 닫기(X) 공통 처리 - 상태는 이미 실시간 반영되어
        있으므로, 메인 화면 요약(선택 구 수/예상 쿼리 수)만 다시 계산하고
        팝업을 정리한다."""
        self._update_subdivision_summary()
        popup = self._subregion_popup
        self._subregion_popup = None
        self._subregion_popup_container = None
        if popup is not None:
            try:
                popup.grab_release()
                popup.destroy()
            except Exception:
                pass

    def _render_subregion_selection_if_popup_open(self):
        """팝업이 열려 있을 때만 내용을 다시 그린다(닫혀 있으면 그릴 대상이
        없으므로 스킵) - 지역/구 선택이 바뀔 때마다 호출된다."""
        if self._is_subregion_popup_open():
            self._render_subregion_selection()

    def _build_subregion_checkbox_grid(self, parent, vars_dict: dict, start_row: int, columns: int = 3) -> int:
        """vars_dict(이름 -> BooleanVar)의 각 항목을 체크박스로 그려 3열로 배치한다.

        새 BooleanVar를 만들지 않고 이미 존재하는 var를 그대로 재사용한다 -
        접혔다 펼쳐져도(또는 전체 선택/해제 버튼으로 바뀐 값이) 그대로
        유지되어야 하기 때문이다. 반환값은 다음에 이어 그릴 row 번호다.
        """
        row = start_row
        col = 0
        for name, var in vars_dict.items():
            ctk.CTkCheckBox(
                parent, text=name, variable=var, command=self._update_subdivision_summary,
            ).grid(row=row, column=col, sticky="w", padx=8, pady=3)
            col += 1
            if col >= columns:
                col = 0
                row += 1
        if col != 0:
            row += 1
        return row

    def _render_subregion_selection(self):
        """팝업 컨테이너에 선택된 구마다 법정동/역상권 체크박스(데이터 있음)
        또는 "준비 중" 안내(데이터 없음)를 순서대로 그린다. 전체 선택/해제
        버튼은 팝업 하단에 한 번만 있으므로 여기서는 그리지 않는다."""
        if not self._is_subregion_popup_open():
            return
        container = self._subregion_popup_container
        for child in container.winfo_children():
            child.destroy()

        row = 0
        for district in self.get_selected_districts():
            legal_vars = self.region_selection_vars.get(district, {}).get("legal_dongs", {})
            landmark_vars = self.region_selection_vars.get(district, {}).get("landmarks", {})

            ctk.CTkLabel(
                container, text=district, anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 2))
            row += 1

            if not legal_vars and not landmark_vars:
                ctk.CTkLabel(
                    container,
                    text=f"이 지역의 세부구역 데이터는 아직 준비 중입니다.\n현재는 {district} 기준으로 수집합니다.",
                    justify="left", anchor="w", text_color="gray",
                ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
                row += 1
                continue

            if legal_vars:
                ctk.CTkLabel(
                    container, text="법정동", anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold"),
                ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 2))
                row += 1
                row = self._build_subregion_checkbox_grid(container, legal_vars, row)

            if landmark_vars:
                ctk.CTkLabel(
                    container, text="역/상권", anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold"),
                ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 2))
                row += 1
                row = self._build_subregion_checkbox_grid(container, landmark_vars, row)

        if not self.get_selected_districts():
            ctk.CTkLabel(container, text="선택된 구가 없습니다.", text_color="gray").grid(row=0, column=0, sticky="w")

    def _set_all_subregions(self, select: bool):
        # 요구사항: 전체 선택/해제는 "현재 선택된 모든 구"의 법정동/역상권에
        # 적용한다. 선택 해제된 구의 캐시된 상태까지 건드려도 무해하다(그
        # 구가 다시 체크되기 전까지는 쿼리 생성에 영향이 없으므로).
        for district_vars in self.region_selection_vars.values():
            for group in district_vars.values():
                for var in group.values():
                    var.set(select)
        self._update_subdivision_summary()

    def get_selected_subregions(self) -> dict:
        """선택된 구별로 현재 체크된 법정동/역상권 이름 목록을 반환한다.

        반환: {구이름: {"legal_dongs": [...], "landmarks": [...]}, ...}
        (선택된 구 중 세부구역 데이터가 로드된 구만 키가 생긴다). 실제 수집
        쿼리 반영은 _build_collection_queries()가 이 값을 읽어 처리한다.
        """
        result = {}
        for district in self.get_selected_districts():
            district_vars = self.region_selection_vars.get(district, {})
            result[district] = {
                "legal_dongs": [name for name, var in district_vars.get("legal_dongs", {}).items() if var.get()],
                "landmarks": [name for name, var in district_vars.get("landmarks", {}).items() if var.get()],
            }
        return result

    def _build_collection_queries(self) -> list[dict]:
        """현재 UI 선택 상태(시/도 + 선택된 구들 + 세부구역 + 키워드)로 실제
        수집 쿼리 목록을 만든다. 계산 자체는 Tk와 무관한 순수 함수
        build_collection_queries에 위임한다(그래야 Tk 없이 단위 테스트할 수
        있다). 자동 세분화가 꺼져 있으면 데이터가 있는 구도 구 기준
        fallback으로만 처리한다.
        """
        city = self.selected_city_var.get()
        keyword = self.keyword_input_var.get().strip()
        if not keyword:
            return []

        selected_subregions = self.get_selected_subregions()
        auto_subdivide = self.auto_subdivide_var.get()

        district_selections = []
        for district in self.get_selected_districts():
            layers = self._subdivision_layers.get(district, {})
            has_data = auto_subdivide and bool(layers.get("legal_dongs") or layers.get("landmarks"))
            subregions: list[str] = []
            legal_dongs: list[str] = []
            landmarks: list[str] = []
            if has_data:
                entry = selected_subregions.get(district, {"legal_dongs": [], "landmarks": []})
                legal_dongs = entry["legal_dongs"]
                landmarks = entry["landmarks"]
                subregions = legal_dongs + landmarks
            district_selections.append({
                "district": district,
                "has_subregion_data": has_data,
                "selected_subregions": subregions,
                "legal_dongs": legal_dongs,
                "landmarks": landmarks,
            })
        return build_collection_queries(city, district_selections, keyword)

    def _estimate_query_count(self) -> int:
        return len(self._build_collection_queries())

    def _update_subdivision_summary(self):
        selected_districts = self.get_selected_districts()
        if not selected_districts:
            self.subdivision_summary_var.set("선택된 구가 없습니다.")
            return
        query_count = self._estimate_query_count()
        self.subdivision_summary_var.set(f"선택된 구: {len(selected_districts)}개\n예상 수집 쿼리: {query_count}개")

    def _refresh_subdivision_view(self):
        """자동 세분화 on/off에 따라 "수집할 동/상권 설정" 버튼 표시 여부만
        갱신한다(선택 상태 자체는 건드리지 않음 - 그건
        _ensure_subregion_data_loaded/_set_all_subregions 몫). 요약 문구(선택
        구 수 + 예상 쿼리 수)는 자동 세분화 여부와 무관하게 항상 갱신한다.
        데이터 없는 구만 선택된 경우에도 팝업에서 "준비 중" 안내를 보여줘야
        하므로, 버튼은 선택된 구가 있으면 항상 표시한다(데이터 유무로
        숨기지 않음 - UI-CLEANUP-1C까지는 데이터 없으면 버튼 자체를 숨겼지만,
        여러 구 중 일부만 데이터가 없는 경우를 다루기 어려워 팝업 분리와
        함께 정리했다)."""
        if not self.auto_subdivide_var.get() or not self.get_selected_districts():
            self.subregion_popup_button.grid_remove()
        else:
            self.subregion_popup_button.grid()
        self._update_subdivision_summary()

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
        for widget in self._iter_children(self.left_panel):
            if isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkEntry, ctk.CTkRadioButton, ctk.CTkOptionMenu)):
                widget.configure(state=state)
        # ARCH-300C WIRE-2C-2: 새로오픈 체크박스는 Network 기본 경로에서
        # 신뢰성 있게 지원되지 않으므로(§_build_filter_section), 좌측 패널이
        # normal로 복구되어도 다시 활성화되지 않도록 항상 disabled를 유지한다.
        if hasattr(self, "new_open_checkbox"):
            self.new_open_checkbox.configure(state="disabled")

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
        """ARCH-300C WIRE-2C-2: 기본 실행 경로를 고르는 진입점.

        `_DEFAULT_COLLECTION_ENGINE`(내부 상수, UI 노출 없음)이 "network"면
        `_start_network_crawl`(기본값), "legacy"면 `_start_legacy_crawl`(내부
        롤백 경로)로 위임한다. 두 경로 모두 이 메서드가 button command로
        연결된 시그니처(self, 인자 없음)를 그대로 유지한다.
        """
        if _DEFAULT_COLLECTION_ENGINE == "legacy":
            self._start_legacy_crawl()
        else:
            self._start_network_crawl()

    def _start_legacy_crawl(self):
        # ARCH-300C WIRE-2C-2: WIRE-2C-1까지의 start_crawl 본문을 그대로
        # 옮긴 것이다(검증 순서/동작 무변경) - _run_queue_pipeline(basic/premium)
        # 을 실행하는 내부 롤백 경로이며, _DEFAULT_COLLECTION_ENGINE="legacy"로
        # 바꿔야만 진입한다.
        raw_keyword = self.keyword_input_var.get()
        output_path = self.output_path_var.get().strip()
        mode = self.mode_var.get()
        new_open_only = self.new_open_only_var.get()
        review_min_raw = self.review_min_var.get().strip()
        review_max_raw = self.review_max_var.get().strip()

        if not self.get_selected_districts():
            self.log("[ui] 실패: 구를 1개 이상 선택하세요")
            return

        # 다중 키워드 UI를 제거한 대신, 다중 키워드로 보이는 입력은 수집 시작
        # 전에 막는다(§_validate_single_keyword).
        keyword_error = self._validate_single_keyword(raw_keyword)
        if keyword_error:
            self.log(f"[ui] 실패: {keyword_error}")
            self.show_error("키워드 입력 오류", keyword_error)
            return

        keyword = raw_keyword.strip()
        if not keyword:
            self.log("[ui] 실패: 키워드를 입력하세요")
            return

        try:
            limit = int(self.limit_var.get().strip())
            if limit <= 0:
                raise ValueError
        except ValueError:
            self.log("[ui] 실패: 목표 수집 개수는 양수여야 합니다")
            return
        try:
            review_min = int(review_min_raw) if review_min_raw else None
            review_max = int(review_max_raw) if review_max_raw else None
        except ValueError:
            self.log("[ui] 실패: 리뷰수는 숫자만 입력해야 합니다.")
            return
        if not output_path:
            self.log("[ui] 실패: 저장 경로가 비어 있습니다")
            return

        # 선택된 구/세부구역 상태를 실제 쿼리로 변환한다(§_build_collection_queries).
        # 세부구역 데이터가 있는 구에서 법정동/역상권을 전부 해제했거나, 선택된
        # 구/세부구역이 전혀 없으면 쿼리가 0개가 되므로 여기서 차단한다.
        query_queue = self._build_collection_queries()
        if not query_queue:
            message = "수집할 지역 또는 동/상권이 선택되지 않았습니다.\n최소 1개 이상의 구 또는 세부구역을 선택해주세요."
            self.log(f"[ui] 실패: {message}")
            self.show_error("지역/세부구역 선택 오류", message)
            return

        first_job = query_queue[0]
        self._reset_eta_state(len(query_queue))
        self._reset_collection_stats()
        self.pause_event.clear()
        self.btn_pause.configure(text="일시정지")
        self.stop_event.clear()
        self.set_running(True)
        self.set_status(f"{first_job['region']}\n{first_job['keyword']}\n수집 대기 중\n(0/{len(query_queue)})")
        self.progress_bar.set(0)
        self.progress_percent_var.set(f"0/{len(query_queue)}")
        self.eta_var.set("예상 남은 시간: 계산 중...")
        self._start_eta_loop()
        self.last_output_path = output_path

        self.log(f"[ui] Queue 생성 완료: {len(query_queue)}건")
        self.log(f"[ui] 선택 구={', '.join(self.get_selected_districts())}")
        self.log(f"[ui] 키워드={keyword}")
        self.log(f"[ui] 목표 수집 개수={limit}(검색 조합 1개당 상한, 쿼리 {len(query_queue)}개)")
        self.log(f"[ui] 저장 경로={output_path}")
        self.log(f"[ui] 신규오픈 필터={new_open_only}")
        self.log(f"[ui] 리뷰 수 필터={self.review_min_var.get()}~{self.review_max_var.get()}")

        threading.Thread(
            target=self._run_queue_pipeline,
            args=(query_queue, limit, output_path, mode, new_open_only, review_min, review_max),
            daemon=True,
        ).start()

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

        if not self.get_selected_districts():
            self.log("[ui] 실패: 구를 1개 이상 선택하세요")
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

        per_query_limit = _parse_positive_int(self.limit_var.get())
        if per_query_limit is None:
            message = "검색 조합당 수집 상한은 양의 정수여야 합니다."
            self.log(f"[ui] 실패: {message}")
            self.show_error("입력 오류", message)
            return

        target_count = _parse_positive_int(self.target_count_var.get())
        if target_count is None:
            message = "전체 목표 저장 개수는 양의 정수여야 합니다."
            self.log(f"[ui] 실패: {message}")
            self.show_error("입력 오류", message)
            return

        if not output_path:
            self.log("[ui] 실패: 저장 경로가 비어 있습니다")
            return

        query_queue = self._build_collection_queries()
        if not query_queue:
            message = "수집할 지역 또는 동/상권이 선택되지 않았습니다.\n최소 1개 이상의 구 또는 세부구역을 선택해주세요."
            self.log(f"[ui] 실패: {message}")
            self.show_error("지역/세부구역 선택 오류", message)
            return

        # 새로오픈 필터는 Network 기본 경로에서 신뢰성 있게 지원되지 않으므로
        # (§_build_filter_section) 체크박스 상태와 무관하게 항상 False로
        # 정규화한다 - 체크된 상태로 disabled되어 적용된 것처럼 오해하지
        # 않도록 하는 방어다.
        self.new_open_only_var.set(False)

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

        self.log(f"[ui] Queue 생성 완료: {len(query_queue)}건")
        self.log(f"[ui] 선택 구={', '.join(self.get_selected_districts())}")
        self.log(f"[ui] 키워드={keyword}")
        self.log(f"[ui] 검색 조합당 수집 상한={per_query_limit}, 전체 목표 저장 개수={target_count}")
        self.log(f"[ui] 저장 경로={saved_output_path}")

        threading.Thread(
            target=self._run_network_pipeline_worker,
            args=(query_queue, per_query_limit, target_count, saved_output_path),
            daemon=True,
        ).start()

    def _run_network_pipeline_worker(self, query_queue: list[dict], per_query_limit: int, target_count: int, output_path: str):
        """ARCH-300C WIRE-2C-2: `_run_network_pipeline` 호출을 감싸는 최종
        방어선 + UI 상태 복구 지점.

        여기서 잡는 예외는 collector/orchestrator가 결과 dict조차 반환하지
        못한 예상 밖 오류뿐이다(예: Playwright 시작 자체가 실패) - exporter
        실패는 `_run_network_pipeline`/`_export_network_result`가 이미
        result 메타(export_error)로 처리하므로 여기서 다시 다루지 않는다
        (이중 처리 금지). 정상/예외 종료 어느 쪽이든 finally에서 기존
        `set_running(False)`(내부적으로 self.after(0, ...) 사용)로 좌측
        패널/시작 버튼을 복구한다 - `_run_queue_pipeline`의 finally와 동일한
        원칙이다.
        """
        try:
            self._run_network_pipeline(query_queue, per_query_limit, target_count, output_path)
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

    def _collect_basic_query(self, query: str, limit: int, new_open_only=False) -> tuple[list[dict], list[dict], list[dict]]:
        with contextlib.redirect_stdout(LogWriter(self.log)):
            raw_places = crawl_places(query, limit, new_open_only=new_open_only, stop_event=self.stop_event, pause_event=self.pause_event)
        self.log(f"[ui] raw count={len(raw_places)}")
        parsed_places = parse_places(raw_places, mode="basic")
        self.log(f"[ui] parsed count={len(parsed_places)}")
        return parsed_places, parsed_places, []

    def _note_security_block(self, decision) -> None:
        # SAFE-1: collect_pc_full의 on_security_block 콜백. CAPTCHA/보안 차단 감지를
        # 인스턴스 상태에 기록만 하고, 실제 Queue 중단/저장/안내는 _run_queue_pipeline이 담당한다.
        self._security_block_decision = decision
        self.log("[ui] 보안 확인(CAPTCHA) 감지: 안전 중단합니다.")

    def _collect_premium_query(self, query: str, limit: int, new_open_only=False) -> tuple[list[dict], list[dict], list[dict]]:
        # 2026-07-06 Stage 3D: premium 분기를 새 PC full engine(collect_pc_full)에 연결.
        # 카드 index 클릭 -> entryIframe에서 전화/주소/플레이스 URL/SNS를 한 번에 수집하며,
        # row는 이미 최종 컬럼 형태이므로 parse_places/merger를 우회한다(우회 이유: 신규
        # 필드 홈페이지/인스타/블로그 보존, place_id는 row에 남기고 Excel 비노출).
        # 반환은 (rows, [], rows)로, 기존 _run_queue_pipeline 누적/저장 로직을 수정하지 않는다.
        # 기존 모바일+PC 병합 로직은 _collect_premium_query_legacy로 보존(fallback/롤백용).
        self.log("[ui] Premium Mode(PC full engine): 상세 데이터 수집 중...")
        cfg = DiagnosticConfig.from_env()
        collector = build_full_collector(cfg)
        with contextlib.redirect_stdout(LogWriter(self.log)):
            rows = collect_pc_full(
                query,
                limit,
                new_open_only=new_open_only,
                stop_event=self.stop_event,
                pause_event=self.pause_event,
                diagnostic_config=cfg,
                on_security_block=self._note_security_block,
                collector=collector,
            )
        self.log(f"[ui] pc full count={len(rows)}")
        return rows, [], rows

    def _collect_premium_query_legacy(self, query: str, limit: int, new_open_only=False) -> tuple[list[dict], list[dict], list[dict]]:
        # Stage 3C까지의 모바일+PC 병합 premium 로직(fallback/롤백용, 현재 호출부 없음).
        # UI에서 "빠른 수집(모바일)" 선택 자체는 사라졌지만, 엔진 코드는 삭제하지
        # 않는다(요청 범위: UI 노출 제거만, 크롤러 엔진 대규모 변경 금지).
        self.log("[ui] Premium Mode: 기본 데이터(전화번호) 수집 중...")
        with contextlib.redirect_stdout(LogWriter(self.log)):
            mobile_raw = crawl_places(query, limit, new_open_only=new_open_only, stop_event=self.stop_event, pause_event=self.pause_event)
        mobile_data = parse_places(mobile_raw, mode="basic")
        self.log(f"[ui] mobile count={len(mobile_data)}")
        if self.stop_event.is_set():
            self.log("[ui] 중지 요청됨: PC 수집 단계를 건너뜁니다.")
            return mobile_data, mobile_data, []

        self.log("[ui] Premium Mode: 고급 데이터(리뷰수) 수집 중...")
        with contextlib.redirect_stdout(LogWriter(self.log)):
            pc_raw = crawl_places_pc(query, limit, new_open_only=new_open_only, stop_event=self.stop_event, pause_event=self.pause_event)
        pc_data = parse_places(pc_raw, mode="premium")
        self.log(f"[ui] pc count={len(pc_data)}")

        merged_data = safe_merge_places(mobile_data, pc_data)
        self.log(f"[ui] merged count={len(merged_data)}")
        return merged_data, mobile_data, pc_data

    def _run_queue_pipeline(self, query_queue: list[dict], limit: int, output_path: str, mode: str, new_open_only=False, review_min=None, review_max=None):
        # 정합성 참고(UI-CLEANUP-1D-B): limit은 아래 for 루프에서 매 쿼리마다
        # 그대로 재사용된다(전체 누적 목표가 아니라 쿼리 1개당 상한) - 쿼리가
        # 여러 개면 전체 raw 수집량은 limit x len(query_queue)까지 늘어날 수
        # 있고, 쿼리 간 place_id dedup은 아직 이 파이프라인에 연결되지 않았다.
        # 이 사실을 감추지 않기 위해 목표 개수 UI 문구에서 "조기 종료" 표현을
        # 제거했다(§_build_target_count_section, §self.limit_var).
        all_merged_data = []
        all_mobile_data = []
        all_pc_data = []
        total = len(query_queue)
        self._security_block_decision = None

        try:
            saved_output_path = self.make_timestamped_output_path(output_path, mode)
            Path(saved_output_path).parent.mkdir(parents=True, exist_ok=True)
            self.log(f"[ui] 최종 저장 경로={saved_output_path}")

            was_stopped = False
            security_blocked = False
            for index, job in enumerate(query_queue, start=1):
                if self.stop_event.is_set():
                    was_stopped = True
                    self.log("[ui] 사용자에 의해 Queue 수집이 중단되었습니다.")
                    self.set_status("사용자 중단")
                    break

                region = job["region"]
                keyword = job["keyword"]
                query = job["query"]
                self.set_status(f"{region}\n{keyword}\n수집 중\n({index}/{total})")
                self.log(f"[{index}/{total}] {region} / {keyword} 수집 시작")
                self.log(f"[ui] 검색어={query}")
                self.current_query_start_time = time.time()
                query_pause_time_at_start = self._get_total_pause_time_now()
                self.current_query_pause_time_at_start = query_pause_time_at_start

                if mode == "premium":
                    merged_data, mobile_data, pc_data = self._collect_premium_query(query, limit, new_open_only=new_open_only)
                else:
                    merged_data, mobile_data, pc_data = self._collect_basic_query(query, limit, new_open_only=new_open_only)

                merged_rows = list(merged_data or [])
                mobile_rows = list(mobile_data or [])
                pc_rows = list(pc_data or [])

                # "총 발견"은 이번 쿼리에서 필터 적용 전 확보한 raw 건수를 누적한다.
                self.total_found_count += len(merged_rows)
                self.after(0, self.total_found_var.set, f"총 발견: {self.total_found_count}개")

                if mode == "premium" and (review_min is not None or review_max is not None):
                    before_count = len(merged_rows)
                    merged_rows = self._filter_by_review_count(merged_rows, review_min, review_max)
                    self.log(f"[ui] 리뷰수 필터 적용: {before_count}건 -> {len(merged_rows)}건 남음")

                if mode == "premium":
                    all_merged_data.extend(merged_rows or mobile_rows or pc_rows)
                    all_mobile_data.extend(mobile_rows or merged_rows)
                    all_pc_data.extend(pc_rows)
                else:
                    basic_rows = merged_rows or mobile_rows
                    all_merged_data.extend(basic_rows)
                    all_mobile_data.extend(mobile_rows or basic_rows)
                self.after(0, self.final_expected_var.set, f"최종 저장 예정: {len(all_merged_data)}개")
                self._record_query_complete(self.current_query_start_time, query_pause_time_at_start)
                self._set_queue_progress(index, total)
                self.log(f"[{index}/{total}] {region} / {keyword} 수집 완료")
                if self.stop_event.is_set():
                    was_stopped = True
                    self.log("[ui] 사용자에 의해 Queue 수집이 중단되었습니다.")
                    self.set_status("사용자 중단")
                    break
                if self._security_block_decision is not None:
                    security_blocked = True
                    self.log("[ui] 현재까지 수집된 결과는 저장됩니다.")
                    self.log("[ui] 남은 Queue는 반복 요청 방지를 위해 중단합니다.")
                    self.set_status("보안 확인 감지 — 부분 저장됨")
                    break

            if not all_merged_data and not all_mobile_data and not all_pc_data:
                self.log("[ui] 누적 데이터가 없어 Excel 저장을 건너뜁니다.")
                self.after(0, self.progress_percent_var.set, f"0/{total}")
                if security_blocked:
                    self.set_status("보안 확인 감지 — 부분 저장됨")
                elif was_stopped:
                    self.set_status("사용자 중단")
                else:
                    self.set_status("수집 결과 없음")
                return

            self.set_status("데이터 저장 중...")
            self.log(f"[ui] 누적 통합 결과={len(all_merged_data)}")
            self.log(f"[ui] 누적 모바일 원본={len(all_mobile_data)}")
            self.log(f"[ui] 누적 PC 원본={len(all_pc_data)}")
            export_pc_data = all_pc_data if mode == "premium" else []
            saved_path = export_places_to_excel(
                all_merged_data,
                all_mobile_data,
                export_pc_data,
                saved_output_path,
            )

            self.last_output_path = saved_path
            self.log(f"[ui] 저장 완료: {saved_path}")
            if security_blocked:
                self.set_status("보안 확인 감지 — 부분 저장됨")
                self.show_info(
                    "보안 확인 감지",
                    "보안 확인이 감지되어 수집을 중단했습니다.\n"
                    "우회하지 않고 현재까지 수집된 결과를 저장합니다.\n"
                    "짧은 시간에 반복 실행하면 차단이 강화될 수 있습니다.\n"
                    "잠시 후 다시 시도해 주세요.",
                )
            elif was_stopped:
                self.set_status("사용자 중단")
                self.show_info("중단", "Queue 수집이 중단되었고 누적 데이터는 저장되었습니다.")
            else:
                self.after(0, lambda: self.progress_bar.set(1))
                self.after(0, self.progress_percent_var.set, f"{total}/{total}")
                self.after(0, self.eta_var.set, "예상 남은 시간: 완료")
                self.after(0, self._cancel_eta_timer)
                self.set_status("수집 완료")
                self.show_info("완료", "전체 Queue 수집 및 저장이 완료되었습니다.")
            self.after(0, self.open_output_folder)
        except PermissionError:
            message = "엑셀 파일이 열려있거나 권한이 없습니다. 엑셀을 닫고 다시 시도해 주세요."
            self.log(f"[ui] 실패: {message}")
            self.set_status("실패")
            self.show_error("저장 실패", message)
        except Exception as exc:
            self.log(f"[ui] 실패: {exc}")
            self.set_status("실패")
        finally:
            if self.stop_event.is_set():
                self.after(0, self.eta_var.set, "예상 남은 시간: 중단됨")
                self.after(0, self._cancel_eta_timer)
            self.set_running(False)

    def _run_pipeline(self, keyword: str, limit: int, output_path: str, mode: str):
        # 기존 단일 Query 실행 호환용 래퍼입니다. 실제 V2 UI는 Queue 파이프라인을 사용합니다.
        query_queue = [{"region": keyword, "keyword": "", "query": keyword}]
        self._run_queue_pipeline(query_queue, limit, output_path, mode)

    def _network_stop_message(self, result: dict, target_count: int) -> str:
        """저장 결과까지 반영한 최종 상태 문구를 만든다(ARCH-300C WIRE-2C-1).

        우선순위: 저장 실패(export_error) > 저장할 rows 없음(exported=False,
        export_error=False) > stop_reason별 완료/부분 저장 문구. "저장했습니다"는
        실제 저장이 성공(exported=True)했을 때만 쓴다 - export 실패 시 기존
        완료 문구만 보여 성공으로 오인시키지 않기 위해 가장 먼저 검사한다.
        navigation_error_message 전체는 여기서도 노출하지 않는다(로그 전용).
        """
        if result.get("export_error"):
            return "수집 결과를 Excel로 저장하지 못했습니다."
        if not result.get("exported"):
            return "저장할 결과가 없습니다."

        final_count = result.get("final_count", 0)
        stop_reason = result.get("stop_reason")
        if stop_reason == "target_reached":
            return f"전체 목표 개수에 도달했습니다. {final_count}개를 저장했습니다."
        if stop_reason == "queue_exhausted":
            if target_count and final_count < target_count:
                return f"선택한 지역 수집이 완료되었습니다. 목표에는 미달했으며 {final_count}개를 저장했습니다."
            return f"선택한 지역 수집이 완료되었습니다. {final_count}개를 저장했습니다."
        if stop_reason == "security_blocked":
            return f"보안 확인이 감지되어 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다."
        if stop_reason == "status_429":
            return f"요청 제한이 감지되어 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다."
        if stop_reason == "navigation_error":
            return f"브라우저 페이지 오류로 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다."
        if stop_reason == "user_stopped":
            return f"사용자가 수집을 중단했습니다. 현재까지 {final_count}개를 저장했습니다."
        return f"수집이 종료되었습니다. {final_count}개를 저장했습니다. (stop_reason={stop_reason})"

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
        collector_factory=NetworkBrowserCollector,
        orchestrator=run_collection_plan,
        excel_exporter=export_places_to_excel,
    ) -> dict:
        """ARCH-300C WIRE-2C-1: Network/List 제품 흐름 worker + Excel 저장 연결.

        collector_factory/orchestrator/excel_exporter는 의존성 주입 지점이다 -
        기본값은 실제 NetworkBrowserCollector/run_collection_plan/
        export_places_to_excel을 가리키지만, 기본값 참조만으로는 Playwright
        시작도 파일 저장도 발생하지 않는다(실제로 호출될 때만 부작용이
        생긴다). 이번 단계 테스트는 항상 fake를 주입해 실제 브라우저/파일
        저장을 실행하지 않는다.

        저장은 collector(브라우저/session/context)가 완전히 종료된 뒤
        `_export_network_result`에서만 수행한다 - 브라우저 자원 정리와 파일
        저장은 실패 원인이 서로 다르므로 같은 try 블록에 섞지 않는다. 이
        worker의 책임은 collected_at 생성 → collector 생성 → run_collection_plan
        호출 → collector 종료 → rows 확인 후 Excel 저장(0건이면 건너뜀) →
        결과를 로그/상태에 반영 → result 반환까지다. legacy 경로
        (_run_queue_pipeline, basic/premium)는 이 메서드와 무관하게 그대로
        동작한다. target_count UI 활성화·start_crawl 실제 연결은 WIRE-2C-2에서
        진행한다(이번 단계는 이 worker 자체만 다룬다).
        """
        collected_at = datetime.now().strftime("%Y-%m-%d")
        total = len(query_queue)
        self.log(f"[ui][network] Queue 생성 완료: {total}건")
        self.log(f"[ui][network] 검색 조합당 수집 상한={per_query_limit}, 전체 목표 저장 개수={target_count}")

        with collector_factory(collected_at=collected_at) as collector:
            result = orchestrator(
                query_queue,
                per_query_limit=per_query_limit,
                target_count=target_count,
                collected_at=collected_at,
                collect_query=collector.collect_query,
                should_continue=lambda: not self.stop_event.is_set(),
                on_security_block=self._note_security_block,
            )

        self.log(
            f"[ui][network] stop_reason={result.get('stop_reason')}, "
            f"executed={result.get('executed_query_count')}, skipped={result.get('skipped_query_count')}, "
            f"final_count={result.get('final_count')}"
        )
        if result.get("navigation_error"):
            nav_message = (result.get("navigation_error_message") or "")[:120]
            self.log(f"[ui][network] navigation_error 상세(로그 전용): {nav_message}")

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
