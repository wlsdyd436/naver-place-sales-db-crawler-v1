# 첫 출시 후보 체크리스트 (RELEASE CHECKLIST)

본 문서는 네이버 플레이스 영업 DB 수집기의 첫 출시 후보 판단을 위한 체크리스트입니다. `[x]`는 완료, `[ ]`는 미완/확인 필요, `[-]`는 이번 출시 범위에서 보류를 의미합니다. 상태는 실제 코드/문서 변경과 동기화될 때만 갱신합니다.

최종 갱신: 2026-07-06 (Stage 3F)

---

## 1. 기능 체크

- [x] 빠른 수집(모바일, `basic`) 경로 동작 유지 (기존 `crawl_places`)
- [x] 상세 수집(PC, `premium`) 경로가 UI에 연결됨 (`_collect_premium_query` → `collect_pc_full` → `build_full_collector`)
- [x] 카드 index 클릭 → entryIframe wait → place_id 사후 확보 → 상세 병합
- [x] 대표전화 / 주소 / 플레이스 URL / 리뷰수 / 새로오픈여부 / 홈페이지·인스타·블로그 수집
- [x] 주소 정제(역/출구/거리 안내 제거) 적용 (Stage 3B.1)
- [x] Stop / Pause 이벤트가 상세 수집 경로에 전달됨
- [x] 부분 실패 시 부분 결과 보존 반환 (collect_pc_full 계약)
- [ ] 다건(limit>1) / 다지역 대량 흐름 실사용 검증 (출시 후 별도 확인 권장)

## 2. Excel 스키마 체크

- [x] `통합_결과` 11컬럼: 업체명·업종·새로오픈여부·리뷰수·주소·대표전화·플레이스 URL·수집일·홈페이지·인스타·블로그
- [x] 기존 8컬럼 이름/순서/위치 보존 + 신규 3컬럼 맨 뒤 append
- [x] `place_id`는 내부 필드로 유지되고 Excel에는 비노출
- [x] 3시트(`통합_결과`/`원본_모바일`/`원본_PC`) 구조 유지
- [-] 원본_모바일/원본_PC 시트 의미 정리(명칭-내용 불일치) — README 설명으로 갈음, 시트 재설계는 후속

## 3. UI 문구 체크

- [x] 수집 모드 라디오 라벨 정리: `빠른 수집(모바일)` / `상세 수집(PC·전화·SNS)`
- [x] 라디오 내부 value(`basic`/`premium`) 및 분기 로직 불변
- [x] 온라인 채널 체크박스에 `(준비 중)` 표기 (오해 방지)
- [ ] 온라인 채널 필터 실배선 (Stage 3F)

## 4. 법적 / 공개정보 안내 체크

- [x] LEGAL_NOTICE에 상세 수집(PC) 경로 반영 섹션 추가(2026-07-06)
- [x] entryIframe 상세 진입 및 홈페이지/SNS 링크 수집 명시(공개 정보 범위)
- [x] CAPTCHA/보안 확인 비우회 원칙 명시
- [x] 과도한 요청/반복 수집 지양 안내
- [x] 사용자의 약관/법령 준수 의무 안내
- [x] README의 "상세 진입 안 함" 등 구 서술 정정

## 5. 테스트 체크

- [x] 단위/회귀 테스트 스위트 최신 실행 결과 (Stage 3E, 문서/UI 텍스트 정렬 후 재실행)
  - test_ui_pc_full_wiring: PASS 3 / FAIL 0
  - test_exporter_schema: PASS 7 / FAIL 0
  - test_export_adapter: PASS 2 / FAIL 0
  - test_pc_detail_scraper: PASS 23 / FAIL 0
  - test_pc_list_scraper: PASS 21 / FAIL 0
  - test_pc_browser_session: PASS 15 / FAIL 0
  - test_pc_pipeline: PASS 8 / FAIL 0
  - Stage 3E는 문서/텍스트 정렬 작업이며 런타임 로직 변경이 없어, 위 결과는 회귀 없음을 확인하는 용도임. 이번 Stage 3E 자체에서는 live test를 실행하지 않음(직전 Stage 3D UI end-to-end smoke는 이미 성공 기록 완료).
- [x] `test_excel_validation.py`의 통합_결과 기대 컬럼 11컬럼 동기화

## 6. Smoke 체크

- [x] Stage 3B 최종 live smoke 성공 (place_id/URL/전화/주소/인스타)
- [x] Stage 3D UI end-to-end live smoke 성공 (premium 경로 → Excel 11컬럼 생성)
- [x] smoke 시 CAPTCHA/Timeout 미발생
- [ ] 다건/다지역 smoke (출시 후보 확정 전 선택적 확인)

## 7. Legacy Fallback 체크

- [x] 기존 모바일+PC 병합 premium 로직을 `_collect_premium_query_legacy`로 보존
- [x] `pc_crawler.py` / `crawler.py` / `parser.py` / `merger.py` 삭제 없이 유지
- [x] 롤백 경로: `_collect_premium_query`가 legacy를 호출하도록 한 줄 교체하면 구 동작 복귀
- [-] legacy 제거 시점: 상세 수집 경로 충분 검증 후 별도 스테이지

## 8. 출시 전 남은 보류 항목

- [-] 온라인 채널 존재 필터 실배선 (후속 단계)
- [-] 원본_모바일/원본_PC 시트명·구조 정리 또는 단일 시트화
- [-] basic 경로의 상세 엔진 통합 여부 판단
- [-] legacy 수집 엔진 제거
- [-] 버전 표기(README H1) 갱신 여부 결정
- [-] 다건/다지역 대량 live 검증

## 9. 패키징 / 빌드 체크

- [x] PyInstaller 빌드 스크립트 존재 (`build.bat`, `--onefile --windowed --collect-all customtkinter`)
- [x] `app.py`가 `src.ui` import 전에 `PLAYWRIGHT_BROWSERS_PATH`를 설정 (frozen 시 EXE 옆 `ms-playwright` 우선)
- [x] chromium 번들 포함 확인 (`dist/ms-playwright/chromium-*`, `chromium_headless_shell-*`)
- [x] frozen(EXE) 환경에서 `DiagnosticConfig.from_env()`가 강제 안전 모드 (test_pc_config `check_frozen_forces_safe_mode`로 검증)
- [x] README에 EXE 배포/실행 절 추가(EXE + ms-playwright 동일 폴더 배치, output 위치, AV 오탐/최초 실행 지연 안내)
- [x] `.env.example`를 현재 `PCCRAWLER_*` 진단 env 기준으로 최신화(frozen 시 무시됨을 명시)
- [ ] 빌드 머신 `playwright` 버전이 requirements(1.60.0)와 일치하고 번들 chromium 리비전과 정합
- [-] 브라우저 번들 chromium 한정 축소(용량 최적화) — 후속 패키징 최적화 단계
- [-] build.bat / `.spec` 빌드 방식 일원화 — 후속 단계

## 10. 출시 smoke 계획 (Tier 1 / Tier 2)

두 smoke 모두 **각 1회, 별도 승인 후 실행**한다(반복 live 금지). 실행 결과는 성공 시 별도 기록을 남긴다.

- [x] **Tier 1 — 번들 chromium 실행 확인 (빌드 불필요, 1회)** — 2026-07-07 완료
  - `PLAYWRIGHT_BROWSERS_PATH=dist/ms-playwright` 설정 후 상세 수집 `limit=1`(keyword: 서울특별시 강동구 카페) 실행
  - 목적: EXE 빌드 없이 번들 chromium이 실제 구동되고 place_id/플레이스 URL/전화가 수집되는지 조기 확인
  - 결과: rows=1, place_id/플레이스 URL/주소/대표전화/인스타 수집 성공, CAPTCHA/Timeout 없음, 예외 없음 (PROJECT_STATE.md 2026-07-07 기록 참조)
- [x] **Tier 2 — 패키징 EXE end-to-end (빌드 후, 1회)** — 2026-07-07 완료
  - `build.bat`로 빌드 → `dist/NaverPlaceSalesDBCollector.exe` 실행 → 상세 수집 `limit=1` → `output/*.xlsx` 통합_결과 11컬럼 생성 확인, place_id 비노출, CAPTCHA/예외 없음
  - 목적: 배포 산출물(EXE + ms-playwright)로 실제 end-to-end 동작을 출시 게이트로 확인
  - 결과: EXE 실행/GUI 표시/Excel 생성 모두 성공, 통합_결과 11컬럼·place_id 비노출 확인, 생성 파일 `naver_place_premium_db_20260707_0238.xlsx` (PROJECT_STATE.md 2026-07-07 Tier 2 기록 참조)
