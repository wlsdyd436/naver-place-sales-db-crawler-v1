# Codebase Map

## 1. 문서 목적

이 문서는 **현재 Production 코드 구조**를 개발자가 빠르게 찾아갈 수 있도록 정리한 지도다. 설치·사용법은 `README.md`, 진행 상태·이력·리스크는 `PROJECT_STATE.md`가 담당하며(§15), 이 문서는 "무엇이 어디에 있고 무엇을 호출하는가"만 다룬다.

이 문서는 날짜 기반 작업 로그가 아니다. 코드가 바뀌면 이 문서도 그 변경을 반영해 갱신해야 하며, 이 문서와 실제 코드가 다르면 **코드가 항상 기준**이다.

---

## 2. 전체 구조

```text
naver-place-sales-db-crawler-v1/
├── app.py                          # GUI 실행 진입점
├── NaverPlaceSalesDBCollector.spec # PyInstaller 빌드 계약
├── build.bat                       # EXE 빌드 스크립트
├── requirements.txt
├── data/
│   └── legal_dong_snapshot.json    # 공식 법정동 Snapshot(읽기 전용)
├── scripts/
│   ├── update_legal_dong_snapshot.py  # 법정동 Snapshot 개발자용 갱신 도구
│   └── validate_excel_output.py
├── src/
│   ├── ui.py                       # App, 화면, Network 실행 orchestration
│   ├── ui_query_plan.py            # 법정동 선택 → query job 계산(순수 함수)
│   ├── ui_status_messages.py       # ETA·종료 상태 문구 생성(순수 함수)
│   ├── ui_export_flow.py           # Excel 저장 호출 단일 지점
│   ├── ui_home_stage.py            # 홈페이지·SNS 보강 stage 위임
│   ├── run_control.py              # pause/stop 동기·비동기 공용 게이트
│   ├── diagnostics.py              # 진단 산출물(JSON/PNG/텍스트) 저장
│   ├── exporter.py                 # Excel 3시트 저장
│   ├── browser/
│   │   ├── session.py              # Playwright/Native CDP 세션 생명주기
│   │   └── config.py               # Diagnostic/BrowserBackend 설정
│   ├── region/
│   │   ├── legal_dong_loader.py    # Snapshot 로더(시도/시군구/법정동)
│   │   └── naver_region_policy.py  # 주소 ↔ 공식 지역 exact 판정
│   └── collection/
│       ├── apollo_list_collector.py     # 목록 수집 orchestration + Collector
│       ├── apollo_response_observer.py  # response/request 이벤트 관찰
│       ├── apollo_page_navigator.py     # 페이지 이동/CAPTCHA probe/settle 대기
│       ├── apollo_list_adapter.py       # Apollo State 목록 파서
│       ├── apollo_detail_adapter.py     # Apollo State 상세 파서
│       ├── apollo_html_parser.py        # SSR HTML 파서 + 차단 신호 분류
│       ├── place_mapper.py              # item → 판매 DB row 정규화
│       ├── row_filters.py               # 지역/새오픈/리뷰 필터 정책
│       ├── home_enrichment.py           # place_id 기반 홈페이지·SNS 보강
│       ├── plan_runner.py               # 여러 query job 실행 orchestrator
│       └── safety.py                    # 예외 → SafetyDecision 분류
└── tests/                           # 31개 파일, 계약 그룹 단위(§13)
```

문서에서 제외한 것: `.venv/`, `__pycache__/`, `.pytest_cache/`, `build/`, `dist/`, `logs/diagnostics/` 실행 산출물, `scratchpad/`(임시 조사 노트), `cdp_validation_tests/`(보조 실측 스크립트, Production 실행 경로 아님), 그리고 이미 삭제된 legacy `src/pc/`·`src/crawler.py`·`src/parser.py`·`src/merger.py`·`src/pc_crawler.py`(현재 파일시스템에 존재하지 않음 — README §5의 구조 설명은 이 legacy 트리를 그대로 남기고 있어 실제와 다르다. §16 참고).

| 범주 | 파일 | 역할 | 연결 |
|---|---|---|---|
| Entry | `app.py` | 브라우저 경로 환경변수 준비 후 `src.ui.run_app` 호출 | → `src/ui.py` |
| UI | `src/ui.py` | App/위젯 상태, 입력 검증, worker thread 시작, Network orchestration | query plan, status messages, home stage, export flow, collection, region |
| UI | `src/ui_query_plan.py` | 법정동 선택 → query job 목록 + target count 계산 | 없음(순수) |
| UI | `src/ui_status_messages.py` | ETA·종료 상태 문구 생성 | 없음(순수) |
| UI | `src/ui_export_flow.py` | Excel 저장 호출 단일 지점, 빈 rows 시 생략 | `src/exporter.py` |
| UI | `src/ui_home_stage.py` | home_sns 모드 분기 + home enrichment 결과 병합/로그/진단 저장 | `src/collection/home_enrichment.py`, `src/diagnostics.py` |
| Collection | `src/collection/apollo_list_collector.py` | 목록 수집 페이지 반복 orchestration, Collector 컨텍스트 | observer, navigator, adapter, mapper, filters, browser |
| Collection | `src/collection/apollo_response_observer.py` | Playwright response/request 이벤트 관찰, candidate 축적 | place_mapper |
| Collection | `src/collection/apollo_page_navigator.py` | 검색 frame 탐색, CAPTCHA probe, settle 대기 | browser/session, list_adapter, response_observer |
| Collection | `src/collection/apollo_list_adapter.py` | 1페이지 Apollo State에서 메인/새오픈 목록 선택 | place_mapper |
| Collection | `src/collection/apollo_detail_adapter.py` | 상세 Apollo State Base+Parent 결합 | place_mapper |
| Collection | `src/collection/apollo_html_parser.py` | SSR HTML에서 Apollo State 추출 + 차단 신호 분류 | 없음(순수) |
| Collection | `src/collection/place_mapper.py` | item → 14컬럼 row 정규화, URL/전화/리뷰 변환, CAPTCHA 신호 분류 | safety |
| Collection | `src/collection/row_filters.py` | 지역 exact·새오픈·리뷰 범위 필터 | region/naver_region_policy |
| Collection | `src/collection/plan_runner.py` | 여러 query job 순차 실행, 전역 dedup, target/중단 판정 | place_mapper, safety |
| Collection | `src/collection/home_enrichment.py` | place_id 기반 홈페이지·SNS async 보강(재시도 포함) | browser/session, apollo_detail_adapter, apollo_html_parser, place_mapper |
| Collection | `src/collection/safety.py` | 예외/메시지 → SafetyDecision 분류 | 없음 |
| Browser | `src/browser/session.py` | Playwright launch 세션 + Native Edge/Chrome CDP 세션 생명주기 | browser/config, diagnostics |
| Browser | `src/browser/config.py` | Diagnostic/BrowserBackend 설정 dataclass | 없음 |
| Region | `src/region/legal_dong_loader.py` | Snapshot 1회 로드, 시도/시군구/법정동 조회 | 없음(파일 읽기만) |
| Region | `src/region/naver_region_policy.py` | 반환 주소 ↔ 선택 공식 지역 exact 판정 | 없음(순수) |
| Support | `src/run_control.py` | pause/stop 동기(`wait_while_paused`)·비동기(`wait_while_paused_async`) 게이트 | 없음 |
| Support | `src/diagnostics.py` | JSON/PNG/텍스트 진단 저장, 보안 차단 진단 | 없음(파일 I/O만) |
| Support | `src/exporter.py` | Excel 3시트(`통합_결과`/`원본_모바일`/`원본_PC`) 생성 | 없음(pandas/openpyxl) |

---

## 3. 런타임 진입 흐름

```text
app.py
  → PLAYWRIGHT_BROWSERS_PATH 환경변수 준비
  → src.ui.run_app()
  → SalesDbCrawlerApp() 생성 + mainloop()
  → (사용자가 "수집 시작" 클릭) start_crawl() → _start_network_crawl()
  → 입력 검증(키워드/시군구/per_query_limit/리뷰 필터/저장 경로)
  → _build_collection_queries() (ui_query_plan.build_legal_dong_query_plan 위임)
  → threading.Thread(target=_run_network_pipeline_worker)
  → _run_network_pipeline_worker() → _run_network_pipeline()
```

`_run_network_pipeline`이 이 앱의 실질적 오케스트레이션 중심이다 - Collector 생성 → `run_collection_plan` 호출 → Collector 종료 → 보안 진단 로그 → `run_home_enrichment_stage` → 리뷰 필터 통계 로그 → `export_network_result` → 상태 문구 반영까지 이 함수 하나가 순서를 보장한다.

---

## 4. UI 계층

- **`src/ui.py`** — `SalesDbCrawlerApp`이 CustomTkinter 위젯과 사용자 입력 상태(`pause_event`/`stop_event` 포함)를 소유한다. UI thread에서 입력을 검증해 순수 값(query queue, per_query_limit, target_count)으로 확정한 뒤 worker thread를 시작한다. worker thread는 위젯을 직접 건드리지 않고 `self.after`로 예약된 콜백(`log`/`set_status`/`set_running` 등)을 통해서만 화면을 갱신한다. Apollo 파싱이나 Excel Workbook 생성 자체는 이 파일이 구현하지 않는다.
- **`src/ui_query_plan.py`** — `build_legal_dong_query_plan`이 법정동 선택(또는 시군구 단위)을 query job 목록으로 변환하고, `calculate_legal_dong_target_count`가 전체 목표 저장 개수를 계산한다. Tkinter를 참조하지 않는 순수 함수.
- **`src/ui_status_messages.py`** — `_format_eta_seconds`가 남은 시간을, `_network_stop_message`가 저장 결과+stop_reason+home 보강 요약을 사용자 문구로 변환한다.
- **`src/ui_export_flow.py`** — `export_network_result`가 Excel 저장이 실제로 일어나는 유일한 지점이다. rows가 비어 있으면 exporter를 호출하지 않는다.
- **`src/ui_home_stage.py`** — `run_home_enrichment_stage`가 `collection_mode == "home_sns"`이고 목록이 차단되지 않았을 때만 `home_enrichment.enrich_home_details`를 호출하고, 반환값을 result dict에 병합 + 로그 + 진단 JSON 저장까지 담당한다.

---

## 5. Collection 계층

- **`src/collection/apollo_list_collector.py`** — `collect_apollo_first_list_query`(1개 query 처리)와 `ApolloFirstListCollector`(컨텍스트 매니저, `run_collection_plan`이 기대하는 `collect_query` 계약 제공)가 핵심이다. 1페이지는 메인 `placeList(...)` Apollo state만 파싱하고, 2페이지 이후는 페이지 버튼 클릭 후 자연 발생하는 GraphQL 응답을 관찰해 수집한다. **페이지 반복 루프는 이 파일의 orchestration으로 유지되며, 더 잘게 분리할 계획은 없다** — 관찰(observer)·탐색(navigator)·파싱(adapter)·매핑(mapper)·필터(row_filters)는 이미 별도 모듈로 분리되어 있고, 이 파일은 그 모듈들을 순서대로 호출하는 조율자다.
- **`src/collection/apollo_response_observer.py`** — `_QueryObservationContext`가 query 1회 호출에 국한된 로컬 상태를 갖고, response/requestfinished/requestfailed 핸들러가 candidate body를 지연 파싱 가능한 형태로 축적한다.
- **`src/collection/apollo_page_navigator.py`** — 검색 frame 탐색, CAPTCHA DOM probe(`_probe_captcha_state`), 다음 페이지 버튼 탐색, settle 대기(`_wait_for_next_page_settle`)를 담당한다.
- **`src/collection/apollo_list_adapter.py`** — `extract_main_place_list_from_apollo`(메인 목록)와 `extract_new_opening_place_list_from_apollo`(새오픈 전용 목록)가 후보 operation을 구조적 신호(유효 item 개수) 우선으로 스코어링해 선택한다.
- **`src/collection/apollo_detail_adapter.py`** / **`src/collection/apollo_html_parser.py`** — 상세 페이지(SSR HTML)의 Apollo State에서 Base+Parent entity를 결합해 정규화한다(홈페이지·SNS 보강 전용 경로).
- **`src/collection/place_mapper.py`** — `_map_item_to_row`가 raw item을 exporter의 14컬럼 계약에 맞는 row로 변환한다(리뷰 방문자/블로그 분리, 개인 휴대전화 차단, URL 유형 분류, 새오픈 tri-state). `classify_captcha_signal`/`dedup_rows`/`should_stop_for_target`도 이 파일이 제공한다.
- **`src/collection/row_filters.py`** — 지역 exact(법정동 계층 query만), 새오픈 tri-state, 리뷰 범위 필터를 적용하고 거부 사유를 기록한다.
- **`src/collection/plan_runner.py`** — `run_collection_plan`이 여러 query job을 순차 실행하며 전역 dedup, target_count 도달, CAPTCHA/429 안전 중단, 부분 결과 보존을 판단한다.
- **`src/collection/home_enrichment.py`** — `enrich_home_details`가 목록 Collector 세션이 완전히 종료된 뒤 별도 async event loop에서 place_id별 home HTML을 동시성 2로 요청하고, 재시도 가능한 실패만 안정화 대기 후 동시성 1로 최대 1회 재시도한다.
- **`src/collection/safety.py`** — `classify_exception`이 예외/메시지를 CAPTCHA/Timeout/일반 오류로 분류한다(실행 자체는 하지 않음).

---

## 6. Browser 계층

- **`src/browser/session.py`** — 두 세션 클래스를 제공한다.
  - `BrowserSession`: Playwright가 직접 launch하는 개발·테스트 fallback(`backend="launch"`일 때만 선택).
  - `NativeCdpBrowserSession`: production 기본값. Windows에 설치된 Edge/Chrome을 전용 profile+동적 포트로 `subprocess.Popen` 실행한 뒤 `connect_over_cdp`로 연결한다. 자신이 시작한 프로세스(PID)만 종료하며, profile lock으로 동시 실행을 막는다.
  - `src/collection/home_enrichment.py`는 이 두 클래스를 그대로 재사용하지 않고, 이 파일이 노출하는 저수준 private helper(`_acquire_profile_lock`/`_build_native_browser_args`/`_pick_free_port`/`_resolve_browser`/`_terminate_owned_process`/`_wait_for_cdp_ready`)를 가져와 **자체 async CDP 연결**(`_connect_native_edge_context`)을 구성한다 — 목록 수집은 sync Playwright, home 보강은 async Playwright라 세션 클래스를 공유할 수 없기 때문이다.
- **`src/browser/config.py`** — `DiagnosticConfig`(진단 캡처 플래그, 고객용 기본값은 전부 비활성)와 `BrowserBackendConfig`(backend/브라우저 우선순위/profile 경로)를 환경 변수 또는 기본값으로 생성한다. PyInstaller frozen 환경에서는 환경 변수와 무관하게 항상 안전 기본값을 사용한다.

---

## 7. Region 계층

- **`src/region/legal_dong_loader.py`** — `LegalDongSnapshotLoader`가 `data/legal_dong_snapshot.json`을 앱 시작 시 1회 로드한다. 행안부 API를 호출하지 않으며, 로드 실패 시 조용히 대체하지 않고 `LegalDongSnapshotError`를 던진다. `is_active=false` 레코드는 노출하지 않고, `legal_code` 오름차순 원본 순서를 보존한다(가나다순 정렬은 UI 계층 `_sort_korean_names`/`_sort_legal_dong_items`가 별도로 수행).
- **`src/region/naver_region_policy.py`** — `classify_region_match`가 Naver가 반환한 주소 문자열을 선택된 공식 지역과 비교해 `OFFICIAL_EXACT`/`PROVIDER_ALIAS_EXACT`/`OUT_OF_SCOPE`/`REGION_UNVERIFIED`로 판정한다. 실측되지 않은 별칭은 등록하지 않는다.

---

## 8. Diagnostics와 Excel 저장

- **`src/diagnostics.py`** — `save_security_block_diagnostics`가 CAPTCHA/보안 차단이 확정된 순간 JSON(항상 시도)과 CAPTCHA dialog element PNG(locator가 있을 때만)를 저장한다. `build_security_diagnostics_log_messages`는 그 결과를 UI 로그 문자열로만 변환하는 순수 함수다. 저장 실패는 예외를 전파하지 않고 실행 자체를 바꾸지 않는다.
- **`src/exporter.py`** — `export_places_to_excel`이 `통합_결과`/`원본_모바일`/`원본_PC` 3개 시트를 만들고 열 너비·줄바꿈 서식을 적용한 뒤 저장 경로를 반환한다. rows가 비어 있을 때 호출할지 여부는 이 파일의 책임이 아니라 호출자(`src/ui_export_flow.py`)의 책임이다.

---

## 9. 주요 실행 흐름

### 9.1 Basic 모드

```text
사용자 입력 → 법정동 query plan(ui_query_plan)
  → worker thread → Collector 컨텍스트(ApolloFirstListCollector)
  → run_collection_plan(plan_runner)
      → 지역 exact·새오픈·리뷰 필터(row_filters)
      → 전역 dedup·target_count 판정
  → Collector 컨텍스트 종료(browser/session)
  → 보안 진단 로그(diagnostics)
  → run_home_enrichment_stage: collection_mode != "home_sns"이므로 home_* 필드를 기본값(0/None/False)으로만 채우고 종료 — 홈페이지 GET 요청 0회
  → export_network_result(exporter 호출)
  → UI 완료 상태 문구(ui_status_messages)
```

### 9.2 home_sns 모드

```text
(목록 수집 완료, 위와 동일)
  → Collector 컨텍스트 종료 확정(browser/context/page 정리 + owned process 종료)
  → run_home_enrichment_stage → home_enrichment.enrich_home_details
      → 같은 persistent profile을 가리키는 새 async Native CDP 연결
      → place_id별 home HTML GET, 동시성 2, 1차 실패 중 재시도 가능 상태만 최대 1회 재시도(동시성 1)
      → 상세 처리 성공(detail_success) / 그중 외부 링크 발견 / 외부 링크 없음 / 실패 / 미시도 / 재시도 횟수를 구분해 통계
      → 진단 JSON 저장(diagnostics)
  → export_network_result → UI 완료 상태 문구
```

목록 단계에서 확정된 핵심 필드(업체명/업종/새오픈여부/리뷰수/주소/플레이스 URL/수집일)는 home 보강이 절대 덮어쓰지 않는다. 최종까지 실패한 업체도 행이 삭제되지 않는다.

### 9.3 신규 오픈 전용

`new_opening_only=True`이면 `apollo_list_adapter.extract_new_opening_place_list_from_apollo`가 `filterOpening in (True, "true")` operation만 선택한다. 찾지 못하면 `no_new_opening_operation_found` 오류를 반환하며 **일반 목록으로 조용히 대체하지 않는다**. 이 operation은 다음 페이지 개념이 없는 1페이지 고정 미리보기로 취급되어 페이지네이션을 시도하지 않는다 — 목표보다 적게 확보돼도 오류가 아니라 정상 종료(`new_opening_single_page_exhausted`)다.

### 9.4 CAPTCHA/security block

목록 수집 중에는 `apollo_page_navigator._probe_captcha_state`(DOM 존재+가시성+면적) 또는 클릭 중 예외 메시지(`place_mapper.classify_captcha_signal`)로 CAPTCHA를 판정한다. HTTP 403/429만으로 CAPTCHA를 판정하지 않는다 — 홈 보강 단계(SSR 경로)는 별도로 `apollo_html_parser._classify_ssr_block_signal`이 HTTP 403/405/429 상태 코드와 텍스트 마커(자동입력방지문자 등)를 함께 본다. 감지되면 추가 클릭·재시도를 중단하고, `plan_runner`/`apollo_list_collector`가 실행당 최초 1회만 진단 JSON/PNG를 저장하며, 이미 수집된 rows가 있으면 그대로 부분 저장한다.

### 9.5 Pause/stop

`run_control.wait_while_paused`(동기)/`wait_while_paused_async`(비동기)가 각각 목록 수집(다음 페이지/다음 job 진입 직전)과 home 보강(신규 request 시작 직전, semaphore 획득 직후 재확인)에서 게이트 역할을 한다. stop은 pause보다 우선하며, worker 완료 시 `finally` 블록이 `set_running(False)`로 좌측 패널/시작 버튼을 복구한다.

---

## 10. 핵심 데이터 계약

### Query job (`ui_query_plan.build_legal_dong_query_plan` 반환 dict)

```text
region, keyword, query, source_city, source_district, source_subregion,
source_layer("district" | "legal_dong"), legal_code,
per_query_limit, new_opening_only, review_min, review_max
```

### Collection result (`plan_runner.run_collection_plan` 반환 dict)

```text
rows, executed_query_count, skipped_query_count, stop_reason,
before_trim_count, final_count, security_blocked, status_429_seen,
navigation_error, navigation_error_message, rejected_rows,
duplicate_removed_count, review_filter_stats, security_diagnostics
```

`stop_reason` 값: `target_reached` / `queue_exhausted` / `security_blocked` / `status_429` / `navigation_error` / `user_stopped` / `empty_jobs`.

### Home result

`home_enrichment.enrich_home_details`가 반환하는 원본 키(`home_success_count`, `home_processed_success_count`, `home_link_found_count`, `home_no_link_count`, `failure_count`, `not_attempted_count`, `home_retry_count`, `stop_reason`, `security_blocked`, `final_failures`, `diagnostics_report`)를 `ui_home_stage.run_home_enrichment_stage`가 최종 result dict의 `home_*` 접두사 키로 재배치한다:

```text
home_stop_reason, home_security_blocked, home_success_count,
home_processed_success_count, home_link_found_count, home_no_link_count,
home_retry_count, home_failure_count, home_not_attempted_count
```

`home_success_count`는 "상세 처리가 예외 없이 끝남"만 의미하며 링크 존재 여부와 무관하다 — `home_link_found_count`/`home_no_link_count`가 실제 외부 링크 발견 여부를 나눈 값이다(§9.2).

### Export result (`ui_export_flow.export_network_result` 반환 dict에 병합)

```text
exported, export_path, export_error, export_error_message
```

### Excel 14개 열(`exporter.MERGED_COLUMNS`, 순서 고정)

```text
업체명, 업종, 새로오픈여부, 방문자리뷰수, 블로그리뷰수, 총리뷰수, 주소,
대표전화, 플레이스 URL, 수집일, 홈페이지, 인스타, 블로그, 추가 링크
```

`place_id`, `source_city`/`source_district`/`source_subregion`/`source_layer`/`source_query`, `home_*` 진단 필드는 dedup·진단 전용 내부 필드이며 이 14개 열에 포함되지 않는다(`exporter._rows_with_columns`가 `MERGED_COLUMNS`로만 투영).

---

## 11. Thread·리소스 경계

- **UI thread**: 위젯 읽기/갱신, worker thread 시작, `self.after` 콜백 실행(로그/상태바/ETA/progress). 위젯은 UI thread 밖에서 직접 수정하지 않는다.
- **Worker thread**(`_run_network_pipeline_worker`가 시작): 목록 수집(Playwright I/O), `run_home_enrichment_stage` 호출(내부적으로 `asyncio.run()`으로 새 event loop 생성), Excel 저장까지 전부 이 thread에서 순차 실행된다.
- **리소스 순서**: 목록 Collector/Native CDP context 진입 → 목록 수집 → Collector context 종료(browser/process/profile lock 전부 정리) → (home_sns 모드면) 별도 async Native CDP 연결로 home enrichment → Excel 저장. **home enrichment는 목록 Collector context를 재사용하지 않는다** — 완전히 종료된 뒤 새 프로세스로 다시 연결한다.
- **예외 경계**:
  - Collection에서 collector/orchestrator가 결과 dict조차 반환하지 못하는 예상 밖 예외는 `_run_network_pipeline_worker`의 최종 방어선(`try/except`)까지 전파된다.
  - `diagnostics` 저장 실패는 예외를 전파하지 않고 본 실행을 중단하지 않는다.
  - exporter 예외는 `ui_export_flow.export_network_result`가 잡아 `export_error`/`export_error_message`로 변환한다.
  - **home enrichment의 예상 밖 예외는 현재 `run_home_enrichment_stage`가 흡수하지 않고 그대로 worker까지 전파된다** — 이 경우 목록 수집 결과(Excel 저장 포함)가 반영되지 않을 수 있는 알려진 위험이며, 개선이 완료된 상태가 아니다.

---

## 12. 기능별 수정 위치

| 변경 목적 | 먼저 볼 파일 |
|---|---|
| UI 입력·레이아웃 | `src/ui.py` |
| 법정동 query 생성 | `src/ui_query_plan.py` |
| 종료 상태 문구 | `src/ui_status_messages.py` |
| 목록 수집 반복 | `src/collection/apollo_list_collector.py` |
| GraphQL response 관찰 | `src/collection/apollo_response_observer.py` |
| 페이지 이동/CAPTCHA probe | `src/collection/apollo_page_navigator.py` |
| Apollo 목록 선택 | `src/collection/apollo_list_adapter.py` |
| row 매핑 | `src/collection/place_mapper.py` |
| 지역·리뷰 필터 | `src/collection/row_filters.py` |
| 여러 법정동 실행 | `src/collection/plan_runner.py` |
| 홈페이지·SNS 보강(핵심 로직) | `src/collection/home_enrichment.py` |
| 홈페이지·SNS 보강(UI orchestration) | `src/ui_home_stage.py` |
| Edge/CDP lifecycle | `src/browser/session.py` |
| 법정동 snapshot | `src/region/legal_dong_loader.py` |
| 지역 exact 판정 정책 | `src/region/naver_region_policy.py` |
| Excel 열·시트 | `src/exporter.py` |
| 저장 호출 정책(언제 호출할지) | `src/ui_export_flow.py` |
| 진단 저장 | `src/diagnostics.py` |
| pause/stop | `src/run_control.py` |

---

## 13. 테스트 구조

전체 목록 대신 계약 그룹으로 묶는다(31개 파일, 전부 `tests/` 아래):

- **Apollo adapter/parser**: 목록 선택(`test_collection_apollo_list_adapter.py`), 상세 결합(`test_collection_apollo_detail_adapter.py`), 새오픈 selector, 필드 정책(`test_collection_field_policy.py`)
- **response observer**: `test_collection_apollo_response_observer.py`
- **page navigator**: `test_collection_apollo_page_navigator.py`
- **collector**: `test_collection_apollo_list_collector.py`
- **place mapper**: `test_collection_place_mapper.py`
- **plan runner**: `test_collection_plan_runner.py`
- **safety**: `test_collection_safety.py`
- **home enrichment**: `test_collection_home_enrichment.py`, `test_ui_home_stage.py`
- **region policy/snapshot**: `test_region_naver_region_policy.py`, `test_region_legal_dong_loader.py`, `test_update_legal_dong_snapshot.py`
- **browser**: `test_browser_session.py`, `test_browser_session_cdp.py`, `test_browser_config.py`
- **run_control**: `test_run_control.py`
- **diagnostics**: `test_diagnostics.py`
- **export**: `test_ui_export_flow.py`, `test_exporter_schema.py`
- **UI wiring**: `test_ui_apollo_list_wiring.py`, `test_ui_legal_dong_wiring.py`, `test_ui_legal_dong_default_select.py`, `test_ui_network_wiring.py`, `test_ui_network_start.py`, `test_ui_network_export.py`, `test_ui_policy_text.py`, `test_ui_query_plan.py`, `test_ui_status_messages.py`
- **build/spec**: `test_packaging_contract.py`

일부 파일은 하나의 pytest 파일 안에서 여러 개별 계약을 검증하므로, `pytest --collect-only`의 collect 수와 "논리적 계약 수"는 항상 일치하지 않는다. 최신 collect/pass 수치는 이 문서에 고정하지 않고 `PROJECT_STATE.md`가 관리한다.

---

## 14. Build·배포 경계

- 실행 진입점은 `app.py` 하나다(`NaverPlaceSalesDBCollector.spec`의 `Analysis(['app.py'], ...)`).
- 빌드 계약은 tracked `NaverPlaceSalesDBCollector.spec` 하나뿐이다 — `data/legal_dong_snapshot.json`을 EXE 내부(`_MEIPASS/data/`)에 번들하며, `region/legal_dong_loader.default_snapshot_path()`가 `sys.frozen`일 때 이 경로를 찾는다.
- `build.bat`이 PyInstaller 실행 후 `%LOCALAPPDATA%\ms-playwright`를 `dist/ms-playwright`로 복사한다 — 배포 시 EXE와 이 폴더가 반드시 같은 위치에 있어야 한다(`app.py`가 `sys.frozen`이면 EXE 옆의 `ms-playwright`를 `PLAYWRIGHT_BROWSERS_PATH`로 사용).
- 산출물 위치: `dist/NaverPlaceSalesDBCollector.exe`, `dist/ms-playwright/`.
- 이 문서는 spec/build 스크립트의 **선언 내용**만 확인한 것이며, 최근 실제 EXE 재빌드·실행 검증 여부는 확인하지 않았다(별도 검증 단계 필요, §16 참고).

---

## 15. 문서 책임 구분

- **README.md** — 제품 소개, 설치, 사용법, 수집 필드/정책 설명(사용자 대상). 내부 함수 목록이나 import 관계는 다루지 않는다.
- **PROJECT_STATE.md** — 날짜 기반 설계 변경 이력, 검증 결과, 남은 위험·작업(운영 상태 대상). 영구적인 구조 설명은 다루지 않으며, 과거 섹션은 기록 시점의 스냅샷이므로 이후 구조 변경으로 낡아도 수정하지 않는 것이 이 저장소의 관례다.
- **CODEBASE_MAP.md**(이 문서) — 폴더/파일 역할, 의존 방향, 실행 흐름, 데이터 계약, 수정 위치(개발자 대상). 설치 안내나 일자별 로그는 다루지 않는다.

---

## 16. README/PROJECT_STATE 오래된 항목(이번 문서에서 수정하지 않음)

이번 작업 범위가 아니므로 아래는 목록으로만 남긴다.

- **README_NEXT**: §5 "프로젝트 구조"가 삭제된 legacy 트리(`src/crawler.py`, `src/parser.py`, `src/merger.py`, `src/pc_crawler.py`, `src/pc/` 하위 다수 파일, 해당 legacy 테스트 파일들)를 그대로 나열하고 있다 — 현재 파일시스템에 전부 존재하지 않는다(§2 확인). 현재 구조(`src/ui_query_plan.py` 등 분리 모듈, `src/browser/`, `src/region/`, `src/collection/`)로 교체 필요.
- **README_NEXT**: §8 "목록 수집 엔진", §9 "홈페이지·SNS 보강"이 `src/pc/network_browser_collector.py`, `DomMembershipCollector`, `NetworkBrowserCollector`, `src/pc/home_enrichment.py`, `src/pc/detail_scraper.py`, `src/pc/apollo_list_adapter.py` 등 이미 삭제/이동된 legacy 경로를 현재형으로 서술한다 — 실제 현재 경로는 `src/collection/apollo_list_collector.py`, `src/collection/home_enrichment.py`, `src/collection/apollo_list_adapter.py`다.
- **PROJECT_STATE_NEXT**: §1 "프로젝트 개요"의 "현재 방향: GUI 기반 Basic/Premium 모드 분리 운영"이 최신 수집 모드 명칭(`collection_mode`: "빠른 기본 수집"/"홈페이지·SNS 포함 수집")과 다르다 — Basic/Premium은 더 이전 세대 명칭이다.
- **NO_CHANGE_NEEDED**: `LEGAL_NOTICE.md`, `RELEASE_CHECKLIST.md`, `.env.example`은 이번 감사 범위에서 구조 관련 stale 항목이 발견되지 않았다(내용 전체를 정독하지는 않았으므로 별도 요청 시 재확인 필요).
