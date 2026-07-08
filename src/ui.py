# 2026-06-25: V2.0 CustomTkinter UI. 기존 크롤링/파싱/엑셀 저장 파이프라인은 유지합니다.
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
from src.pc.pipeline import collect_pc_full


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
        self.geometry("1000x700")
        self.resizable(False, False)

        self.selected_city_var = ctk.StringVar(value="서울특별시")
        self.keyword_input_var = ctk.StringVar()
        self.limit_var = ctk.StringVar(value="10")
        self.mode_var = ctk.StringVar(value="basic")
        self.output_path_var = ctk.StringVar(value="output/naver_place_basic_db.xlsx")
        self.new_open_only_var = ctk.BooleanVar(value=False)
        self.online_channel_var = ctk.BooleanVar(value=False)
        self.review_min_var = ctk.StringVar()
        self.review_max_var = ctk.StringVar()
        self.progress_percent_var = ctk.StringVar(value="0%")
        self.eta_var = ctk.StringVar(value="예상 남은 시간: 계산 중...")
        self.current_task_var = ctk.StringVar(value="대기 중...")

        self.keywords = ["카페"]
        self.district_vars = {}
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

        self._build_ui()
        self._render_district_checkboxes()
        self._render_keyword_list()

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=6)

        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=6)
        self.left_panel.grid_columnconfigure(0, weight=1)

        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=6)
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(3, weight=1)

        self._build_region_section()
        self._build_keyword_section()
        self._build_filter_section()
        self._build_dashboard_section()
        self._build_control_section()
        self._build_log_section()

    def _build_region_section(self):
        ctk.CTkLabel(self.left_panel, text="1. 지역 선택", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=14, pady=(8, 4))
        region_frame = ctk.CTkFrame(self.left_panel, height=150)
        region_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        region_frame.grid_propagate(False)
        region_frame.grid_columnconfigure((0, 1), weight=1)
        region_frame.grid_rowconfigure(0, weight=1)

        self.city_scroll = ctk.CTkScrollableFrame(region_frame)
        self.city_scroll.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=6)
        self.district_scroll = ctk.CTkScrollableFrame(region_frame)
        self.district_scroll.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=6)

        for city in REGION_DATA:
            ctk.CTkRadioButton(self.city_scroll, text=city, variable=self.selected_city_var, value=city, command=self._render_district_checkboxes).pack(anchor="w", padx=6, pady=4)

        self.toggle_all_button = ctk.CTkButton(region_frame, text="전체 선택 / 해제", command=self.toggle_all_districts)
        self.toggle_all_button.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 6))

    def _build_keyword_section(self):
        ctk.CTkLabel(self.left_panel, text="2. 키워드 입력", font=ctk.CTkFont(size=14, weight="bold")).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        keyword_input_frame = ctk.CTkFrame(self.left_panel)
        keyword_input_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 4))
        keyword_input_frame.grid_columnconfigure(0, weight=1)

        self.keyword_entry = ctk.CTkEntry(keyword_input_frame, textvariable=self.keyword_input_var, placeholder_text="예: 카페, 미용실, 병원")
        self.keyword_entry.grid(row=0, column=0, sticky="ew", padx=(10, 8), pady=6)
        self.keyword_entry.bind("<Return>", self._handle_keyword_return)
        self.keyword_entry._entry.bind("<Return>", self._handle_keyword_return)
        self.bind_all("<Return>", self._handle_keyword_return)
        self.add_keyword_button = ctk.CTkButton(keyword_input_frame, text="추가", width=70, command=self.add_keyword)
        self.add_keyword_button.grid(row=0, column=1, padx=(0, 10), pady=10)

        keyword_list_container = ctk.CTkFrame(self.left_panel, height=78)
        keyword_list_container.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 4))
        keyword_list_container.grid_propagate(False)
        keyword_list_container.grid_columnconfigure(0, weight=1)
        keyword_list_container.grid_rowconfigure(0, weight=1)
        self.keyword_list_frame = ctk.CTkScrollableFrame(keyword_list_container)
        self.keyword_list_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.keyword_list_frame.grid_columnconfigure(0, weight=1)
        self.clear_keyword_button = ctk.CTkButton(self.left_panel, text="전체 삭제", fg_color="gray", command=self.clear_keywords)
        self.clear_keyword_button.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 6))

    def _build_filter_section(self):
        ctk.CTkLabel(self.left_panel, text="3. 상세 필터", font=ctk.CTkFont(size=14, weight="bold")).grid(row=6, column=0, sticky="w", padx=14, pady=(0, 4))
        filter_frame = ctk.CTkFrame(self.left_panel)
        filter_frame.grid(row=7, column=0, sticky="ew", padx=14, pady=(0, 14))
        filter_frame.grid_columnconfigure((1, 3), weight=1)

        self.new_open_checkbox = ctk.CTkCheckBox(filter_frame, text="새로오픈 업체만 수집", variable=self.new_open_only_var)
        self.new_open_checkbox.grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 4))
        self.online_channel_checkbox = ctk.CTkCheckBox(filter_frame, text="온라인 채널(블로그/인스타 등) 존재 (준비 중)", variable=self.online_channel_var)
        self.online_channel_checkbox.grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 4))

        ctk.CTkLabel(filter_frame, text="리뷰 수:").grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(0, 6))
        self.review_min_entry = ctk.CTkEntry(filter_frame, textvariable=self.review_min_var, placeholder_text="Min", width=70)
        self.review_min_entry.grid(row=2, column=1, sticky="ew", padx=(0, 6), pady=(0, 6))
        ctk.CTkLabel(filter_frame, text="~").grid(row=2, column=2, padx=2, pady=(0, 6))
        self.review_max_entry = ctk.CTkEntry(filter_frame, textvariable=self.review_max_var, placeholder_text="Max", width=70)
        self.review_max_entry.grid(row=2, column=3, sticky="ew", padx=(6, 12), pady=(0, 6))

        ctk.CTkLabel(filter_frame, text="수집 모드:").grid(row=3, column=0, sticky="w", padx=(12, 6), pady=(0, 6))
        mode_frame = ctk.CTkFrame(filter_frame, fg_color="transparent")
        mode_frame.grid(row=3, column=1, columnspan=3, sticky="w", padx=(0, 12), pady=(0, 6))
        self.basic_radio = ctk.CTkRadioButton(mode_frame, text="빠른 수집(모바일)", variable=self.mode_var, value="basic", command=self.on_mode_change)
        self.basic_radio.pack(side="left", padx=(0, 12))
        self.premium_radio = ctk.CTkRadioButton(mode_frame, text="상세 수집(PC·전화·SNS)", variable=self.mode_var, value="premium", command=self.on_mode_change)
        self.premium_radio.pack(side="left")

        ctk.CTkLabel(filter_frame, text="수집 개수:").grid(row=4, column=0, sticky="w", padx=(12, 6), pady=(0, 6))
        self.limit_entry = ctk.CTkEntry(filter_frame, textvariable=self.limit_var, width=80)
        self.limit_entry.grid(row=4, column=1, sticky="w", padx=(0, 6), pady=(0, 6))

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
        ctk.CTkLabel(status_card, textvariable=self.current_task_var, anchor="w").grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 16))

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

    def _render_district_checkboxes(self):
        for child in self.district_scroll.winfo_children():
            child.destroy()
        self.district_vars = {}
        for index, district in enumerate(REGION_DATA.get(self.selected_city_var.get(), [])):
            var = ctk.BooleanVar(value=index == 0)
            ctk.CTkCheckBox(self.district_scroll, text=district, variable=var).pack(anchor="w", padx=6, pady=4)
            self.district_vars[district] = var

    def toggle_all_districts(self):
        if not self.district_vars:
            return
        should_select = not all(var.get() for var in self.district_vars.values())
        for var in self.district_vars.values():
            var.set(should_select)

    def _handle_keyword_return(self, event):
        if event.widget in (self.keyword_entry, self.keyword_entry._entry):
            self.add_keyword()
            return "break"
        return None

    def add_keyword(self):
        keyword = self.keyword_input_var.get().strip()
        if not keyword:
            return
        if keyword not in self.keywords:
            self.keywords.append(keyword)
            self._render_keyword_list()
        self.keyword_input_var.set("")

    def remove_keyword(self, keyword: str):
        self.keywords = [item for item in self.keywords if item != keyword]
        self._render_keyword_list()

    def clear_keywords(self):
        self.keywords = []
        self._render_keyword_list()

    def _render_keyword_list(self):
        for child in self.keyword_list_frame.winfo_children():
            child.destroy()
        if not self.keywords:
            ctk.CTkLabel(self.keyword_list_frame, text="추가된 키워드가 없습니다.", text_color="gray").grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return
        for row, keyword in enumerate(self.keywords):
            ctk.CTkLabel(self.keyword_list_frame, text=keyword, anchor="w").grid(row=row, column=0, sticky="ew", padx=(8, 6), pady=4)
            ctk.CTkButton(self.keyword_list_frame, text="X", width=34, height=26, fg_color="gray", command=lambda item=keyword: self.remove_keyword(item)).grid(row=row, column=1, padx=(0, 8), pady=4)

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
            if isinstance(widget, (ctk.CTkButton, ctk.CTkCheckBox, ctk.CTkEntry, ctk.CTkRadioButton)):
                widget.configure(state=state)

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

    def on_mode_change(self):
        if self.mode_var.get() == "premium":
            self.output_path_var.set("output/naver_place_premium_db.xlsx")
        else:
            self.output_path_var.set("output/naver_place_basic_db.xlsx")

    def _reset_eta_state(self, total_queries: int):
        self._cancel_eta_timer()
        self.completed_queries = 0
        self.total_pure_time = 0.0
        self.current_query_start_time = None
        self.current_query_pause_time_at_start = 0.0
        self.total_pause_time = 0.0
        self.current_pause_start = None
        self.total_queries = total_queries

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

    def _get_selected_regions(self):
        city = self.selected_city_var.get().strip()
        selected_districts = [district for district, var in self.district_vars.items() if var.get()]
        if selected_districts:
            return [f"{city} {district}" for district in selected_districts]
        return [city] if city else []

    def _build_query_queue(self, regions: list[str], keywords: list[str]) -> list[dict]:
        return [
            {"region": region, "keyword": keyword, "query": f"{region} {keyword}"}
            for region in regions
            for keyword in keywords
        ]

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

    def start_crawl(self):
        regions = self._get_selected_regions()
        keywords = [keyword.strip() for keyword in self.keywords if keyword.strip()]
        output_path = self.output_path_var.get().strip()
        mode = self.mode_var.get()
        new_open_only = self.new_open_only_var.get()
        review_min_raw = self.review_min_var.get().strip()
        review_max_raw = self.review_max_var.get().strip()

        if not regions:
            self.log("[ui] 실패: 지역을 선택하세요")
            return
        if not keywords:
            self.log("[ui] 실패: 키워드를 입력하세요")
            return
        try:
            limit = int(self.limit_var.get().strip())
            if limit <= 0:
                raise ValueError
        except ValueError:
            self.log("[ui] 실패: 수집 개수는 양수여야 합니다")
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

        query_queue = self._build_query_queue(regions, keywords)
        first_job = query_queue[0]
        self._reset_eta_state(len(query_queue))
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
        self.log(f"[ui] 선택 지역 수={len(regions)}")
        self.log(f"[ui] 선택 키워드 수={len(keywords)}")
        self.log(f"[ui] 선택 모드={mode}")
        self.log(f"[ui] 수집 개수={limit}")
        self.log(f"[ui] 저장 경로={output_path}")
        self.log(f"[ui] 신규오픈 필터={self.new_open_only_var.get()} (TODO)")
        self.log(f"[ui] 온라인 채널 필터={self.online_channel_var.get()} (TODO)")
        self.log(f"[ui] 리뷰 수 필터={self.review_min_var.get()}~{self.review_max_var.get()} (TODO)")

        threading.Thread(
            target=self._run_queue_pipeline,
            args=(query_queue, limit, output_path, mode, new_open_only, review_min, review_max),
            daemon=True,
        ).start()

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
                    "네이버 보안 확인으로 인해 수집을 안전하게 중단했습니다.\n"
                    "현재까지 수집된 결과는 정상 저장되었습니다.\n"
                    "짧은 시간에 반복 실행하면 차단이 강화될 수 있습니다.\n"
                    "잠시 후 다시 시도해 주세요.\n"
                    "※ 보안 확인은 우회하지 않습니다.",
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

    def open_output_folder(self):
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(output_dir.resolve())


def run_app():
    app = SalesDbCrawlerApp()
    app.mainloop()



