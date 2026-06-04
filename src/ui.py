import contextlib
import os
import threading
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from src.crawler import crawl_places
from src.exporter import export_places_to_excel
from src.merger import safe_merge_places
from src.parser import parse_places
from src.pc_crawler import crawl_places_pc


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
    # 2026-06-04: 판매형 MVP를 위한 최소 CustomTkinter UI입니다.
    def __init__(self):
        super().__init__()
        self.title("네이버 플레이스 영업 DB 수집기 V1.1")
        self.geometry("780x700")
        self.minsize(700, 640)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.region_var = ctk.StringVar(value="강남구 역삼동")
        self.industry_var = ctk.StringVar(value="카페")
        self.limit_var = ctk.StringVar(value="10")
        self.mode_var = ctk.StringVar(value="basic")
        self.output_path_var = ctk.StringVar(value="output/naver_place_basic_db.xlsx")
        self.status_var = ctk.StringVar(value="대기 중")
        self.last_output_path = ""

        self._build_ui()

    def _build_ui(self):
        container = ctk.CTkFrame(self)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        title = ctk.CTkLabel(
            container,
            text="네이버 플레이스 영업 DB 수집기 V1.1",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.pack(anchor="w", padx=20, pady=(20, 12))

        section_label = ctk.CTkLabel(
            container,
            text="검색 설정",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        section_label.pack(anchor="w", padx=20, pady=(0, 8))

        form = ctk.CTkFrame(container)
        form.pack(fill="x", padx=20, pady=(0, 14))

        mode_row = ctk.CTkFrame(form)
        mode_row.grid(row=0, column=1, padx=(0, 16), pady=(10, 4), sticky="w")
        mode_label = ctk.CTkLabel(form, text="수집 모드", width=90, anchor="w")
        mode_label.grid(row=0, column=0, padx=(16, 8), pady=(10, 4), sticky="w")
        basic_radio = ctk.CTkRadioButton(
            mode_row,
            text="Basic Mode (빠른 수집)",
            variable=self.mode_var,
            value="basic",
            command=self.on_mode_change,
        )
        basic_radio.pack(side="left", padx=(0, 14))
        premium_radio = ctk.CTkRadioButton(
            mode_row,
            text="Premium Mode (리뷰수·신규오픈 추가)",
            variable=self.mode_var,
            value="premium",
            command=self.on_mode_change,
        )
        premium_radio.pack(side="left")

        self._add_input_row(
            form,
            "지역 입력",
            self.region_var,
            1,
            "예시: 강남역, 강남구, 역삼동, 대전 서구",
        )
        self._add_input_row(
            form,
            "업종 입력",
            self.industry_var,
            2,
            "예시: 카페, 미용실, 음식점, 병원",
        )
        self._add_input_row(form, "수집 개수", self.limit_var, 3)
        self._add_input_row(form, "저장 경로", self.output_path_var, 4)

        action_row = ctk.CTkFrame(container)
        action_row.pack(fill="x", padx=20, pady=(0, 14))

        self.run_button = ctk.CTkButton(
            action_row,
            text="수집 시작",
            height=40,
            command=self.start_crawl,
        )
        self.run_button.pack(side="left")

        self.open_folder_button = ctk.CTkButton(
            action_row,
            text="저장 폴더 열기",
            height=40,
            command=self.open_output_folder,
        )
        self.open_folder_button.pack(side="left", padx=(10, 0))

        status_text = ctk.CTkLabel(action_row, text="상태:")
        status_text.pack(side="left", padx=(14, 4))

        status_label = ctk.CTkLabel(
            action_row,
            textvariable=self.status_var,
            font=ctk.CTkFont(weight="bold"),
        )
        status_label.pack(side="left")

        guide_label = ctk.CTkLabel(
            container,
            text="※ Premium Mode는 속도가 조금 느리지만 기존 데이터에 리뷰수와 신규오픈 여부를 마킹해 줍니다.",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        )
        guide_label.pack(anchor="w", padx=20, pady=(0, 10))

        log_label = ctk.CTkLabel(
            container,
            text="로그 화면",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        log_label.pack(anchor="w", padx=20, pady=(0, 8))

        self.log_box = ctk.CTkTextbox(container, height=300)
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        self.log_box.insert("end", "[ui] 실행 준비 완료\n")
        self.log_box.configure(state="disabled")

    def _add_input_row(self, parent, label_text, variable, row, help_text=""):
        label = ctk.CTkLabel(parent, text=label_text, width=90, anchor="w")
        label.grid(row=row * 2, column=0, padx=(16, 8), pady=(10, 4), sticky="w")

        entry = ctk.CTkEntry(parent, textvariable=variable)
        entry.grid(row=row * 2, column=1, padx=(0, 16), pady=(10, 4), sticky="ew")
        parent.grid_columnconfigure(1, weight=1)

        if help_text:
            help_label = ctk.CTkLabel(parent, text=help_text, text_color="gray")
            help_label.grid(
                row=row * 2 + 1,
                column=1,
                padx=(0, 16),
                pady=(0, 8),
                sticky="w",
            )

    def log(self, message: str):
        self.after(0, self._append_log, message)

    def _append_log(self, message: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_status(self, message: str):
        self.after(0, self.status_var.set, message)

    def set_running(self, is_running: bool):
        state = "disabled" if is_running else "normal"
        self.after(0, lambda: self.run_button.configure(state=state))

    def make_timestamped_output_path(self, output_path: str, mode: str) -> str:
        # 2026-06-04: 열린 Excel 파일과의 덮어쓰기 충돌을 막기 위해 매번 새 파일명으로 저장합니다.
        path = Path(output_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_stem = (
            "naver_place_premium_db" if mode == "premium" else "naver_place_basic_db"
        )
        stem = path.stem or default_stem
        output_dir = path.parent if str(path.parent) != "." else Path("output")
        return str(output_dir / f"{stem}_{timestamp}.xlsx")

    def show_info(self, title: str, message: str):
        self.after(0, lambda: messagebox.showinfo(title, message))

    def show_error(self, title: str, message: str):
        self.after(0, lambda: messagebox.showerror(title, message))

    def on_mode_change(self):
        # 2026-06-04: 모드별 기본 저장 파일명을 분리합니다.
        if self.mode_var.get() == "premium":
            self.output_path_var.set("output/naver_place_premium_db.xlsx")
        else:
            self.output_path_var.set("output/naver_place_basic_db.xlsx")

    def start_crawl(self):
        region = self.region_var.get().strip()
        industry = self.industry_var.get().strip()
        output_path = self.output_path_var.get().strip()
        mode = self.mode_var.get()

        if not region:
            self.status_var.set("실패")
            self.log("[ui] 실패: 지역을 입력하세요")
            return

        if not industry:
            self.status_var.set("실패")
            self.log("[ui] 실패: 업종을 입력하세요")
            return

        try:
            limit = int(self.limit_var.get().strip())
            if limit <= 0:
                raise ValueError
        except ValueError:
            self.status_var.set("실패")
            self.log("[ui] 실패: 수집 개수는 양수여야 합니다")
            return

        if not output_path:
            self.status_var.set("실패")
            self.log("[ui] 실패: 저장 경로를 입력하세요")
            return

        # 2026-06-04: 지역과 업종을 조합해 기존 crawler 검색어로 전달합니다.
        keyword = f"{region} {industry}"
        self.set_running(True)
        self.set_status("수집 중")
        self.last_output_path = output_path
        self.log(f"[ui] 지역={region}")
        self.log(f"[ui] 업종={industry}")
        self.log(f"[ui] 검색어={keyword}")
        self.log(f"[ui] 선택 모드={mode}")
        if mode == "premium":
            self.log("[ui] Premium Mode: PC 기반 신규/리뷰 타겟 수집 시작")
        else:
            self.log("[ui] Basic Mode: 모바일 기반 빠른 수집 시작")
        self.log(f"[ui] 수집 개수={limit}")
        self.log(f"[ui] 저장 경로={output_path}")

        worker = threading.Thread(
            target=self._run_pipeline,
            args=(keyword, limit, output_path, mode),
            daemon=True,
        )
        worker.start()

    def _run_pipeline(self, keyword: str, limit: int, output_path: str, mode: str):
        try:
            output_path = self.make_timestamped_output_path(output_path, mode)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            self.log(f"[ui] 실제 저장 파일={output_path}")

            if mode == "premium":
                self.set_status("1/3: 기본 데이터(전화번호) 수집 중...")
                self.log("[ui] 1/3: 기본 데이터(전화번호) 수집 중...")
                with contextlib.redirect_stdout(LogWriter(self.log)):
                    mobile_raw = crawl_places(keyword, limit)
                mobile_data = parse_places(mobile_raw, mode="basic")
                self.log(f"[ui] mobile count={len(mobile_data)}")

                self.set_status("2/3: 고급 데이터(리뷰수) 수집 중...")
                self.log("[ui] 2/3: 고급 데이터(리뷰수) 수집 중...")
                with contextlib.redirect_stdout(LogWriter(self.log)):
                    pc_raw = crawl_places_pc(keyword, limit, new_open_only=False)
                pc_data = parse_places(pc_raw, mode="premium")
                self.log(f"[ui] pc count={len(pc_data)}")

                self.set_status("3/3: 데이터 병합 및 저장 중...")
                self.log("[ui] 3/3: 데이터 병합 및 저장 중...")
                merged_data = safe_merge_places(mobile_data, pc_data)
                self.log(f"[ui] merged count={len(merged_data)}")

                saved_path = export_places_to_excel(
                    merged_data,
                    mobile_data,
                    pc_data,
                    output_path,
                )
            else:
                with contextlib.redirect_stdout(LogWriter(self.log)):
                    raw_places = crawl_places(keyword, limit)
                self.log(f"[ui] raw count={len(raw_places)}")

                parsed_places = parse_places(raw_places, mode=mode)
                self.log(f"[ui] parsed count={len(parsed_places)}")

                saved_path = export_places_to_excel(
                    parsed_places,
                    parsed_places,
                    [],
                    output_path,
                )
            self.last_output_path = saved_path
            self.log(f"[ui] 저장 완료: {saved_path}")
            self.set_status("수집 완료")
            self.show_info("완료", "수집 및 저장이 완료되었습니다.")
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
            self.set_running(False)

    def open_output_folder(self):
        # 2026-06-04: output 폴더를 Windows 탐색기로 엽니다.
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(output_dir.resolve())


def run_app():
    # 2026-06-04: app.py에서 호출하는 UI 실행 진입점입니다.
    app = SalesDbCrawlerApp()
    app.mainloop()
