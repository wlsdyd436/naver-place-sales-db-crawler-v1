# 네이버 플레이스 영업 DB 수집기 V1.2

지역 기반 소상공인 영업을 하는 광고대행사, POS/키오스크 영업자, 식자재 유통업체를 위한 **영업 DB 엑셀 수집 도구**입니다.

GUI 실행 진입점인 `app.py`를 기준으로 동작합니다. `빠른 수집(모바일)` 경로는 모바일 웹 리스트 화면 기반의 빠른 수집이고, `상세 수집(PC·전화·SNS)` 경로는 PC 네이버 지도 단일 엔진으로 검색 리스트 카드를 클릭해 상세(entryIframe)로 진입하여 대표전화·주소·플레이스 URL·리뷰수·새로오픈여부·홈페이지/SNS 링크를 수집합니다.

> UI의 `수집 모드` 라디오는 내부적으로 `basic`(빠른 수집) / `premium`(상세 수집) 값으로 동작합니다. 라벨 문구는 실제 동작을 설명하도록 정리되었으며, 내부 값과 저장 파일명 규칙은 그대로 유지됩니다.

---

## 1. 핵심 방향

- GUI 기반 실행 (`app.py`)
- **빠른 수집(모바일, `basic`)**: 모바일 웹 `m.map.naver.com` 리스트 화면 기반 빠른 영업 DB 수집 (상세 페이지 진입 없음)
- **상세 수집(PC·전화·SNS, `premium`)**: PC 네이버 지도 단일 엔진 기반 상세 수집
  - 검색 리스트(`searchIframe`)에서 카드 클릭 → 상세(`entryIframe`) 진입
  - entryIframe URL에서 place_id를 사후 확보하고, 상세 화면에서 대표전화/주소/플레이스 URL/리뷰수/새로오픈여부/홈페이지·SNS 링크 수집
- 무리한 우회보다 최소 수집과 안정성 우선 (CAPTCHA 우회/회피를 시도하지 않음)
- Excel 저장을 통한 즉시 영업 활용

검색 흐름:

```text
# 빠른 수집(모바일)
https://m.map.naver.com/search.naver?query={지역+업종}

# 상세 수집(PC)
https://map.naver.com/v5/search/{지역+업종}
  -> searchIframe 리스트 카드 클릭
  -> entryIframe 상세(예: https://pcmap.place.naver.com/{segment}/{place_id}/home)
```

상세 수집 경로는 상세 화면의 **home 탭**만 사용하며, 정보 탭 클릭은 사용하지 않습니다.

---

## 2. 수집 필드

빠른 수집(모바일) 대상:

- 업체명
- 업종
- 주소
- 대표전화
- 플레이스 URL
- 수집일

상세 수집(PC) 통합 결과 (`통합_결과` 시트, 11컬럼):

- 업체명
- 업종
- 새로오픈여부
- 리뷰수
- 주소
- 대표전화
- 플레이스 URL
- 수집일
- 홈페이지
- 인스타
- 블로그

> `place_id`는 상세 진입 시 entryIframe URL에서 확보하는 **내부 식별 필드**로, 중복 방지·상세 진입 판정에 사용되며 **Excel에는 노출하지 않습니다**. 사용자에게는 `플레이스 URL`이 제공됩니다.

제외 항목:

- 영업시간
- 평점
- 대표자명
- 개인 휴대폰 번호
- 개인 이메일

> 홈페이지/인스타/블로그는 사업장이 플레이스에 **스스로 공개한 대표 링크**를 상세 화면에서 읽어 도메인으로 분류한 값입니다(개인정보 아님).

---

## 3. 결과물

수집 결과는 Excel 파일로 저장합니다.

실제 저장 경로 예시:

```text
output/naver_place_basic_db_YYYYMMDD_HHMMSS.xlsx      # 빠른 수집(모바일)
output/naver_place_premium_db_YYYYMMDD_HHMMSS.xlsx    # 상세 수집(PC)
```

빠른 수집(모바일) 출력 컬럼:

| 컬럼명 | 설명 |
|---|---|
| 업체명 | 네이버 플레이스 등록 업체명 |
| 업종 | 카테고리 (추출 불안정, 빈 값 허용) |
| 주소 | 사업장 주소 ("주소보기" 접두사 제거 처리됨) |
| 대표전화 | tel: href 기준 추출, 없으면 빈 값 |
| 플레이스 URL | `m.place.naver.com/place/{id}/home` 형식 |
| 수집일 | 수집 실행일 (YYYY-MM-DD) |

상세 수집(PC) `통합_결과` 출력 컬럼 (11컬럼):

| 컬럼명 | 설명 |
|---|---|
| 업체명 | 네이버 플레이스 등록 업체명 |
| 업종 | 카테고리 (추출 불안정, 빈 값 허용) |
| 새로오픈여부 | 신규/새로오픈 표기 시 `O` |
| 리뷰수 | 리스트 카드 기준 리뷰 수 |
| 주소 | 상세 화면 주소 (역/출구/거리 안내 문구 정제 처리됨) |
| 대표전화 | 상세 화면 텍스트 기준 추출 |
| 플레이스 URL | entryIframe 실제 URL 기준 (`pcmap.place.naver.com/{segment}/{place_id}/home`) |
| 수집일 | 수집 실행일 (YYYY-MM-DD) |
| 홈페이지 | 대표 외부 링크 중 인스타/블로그가 아닌 홈페이지 |
| 인스타 | `instagram.com` 링크 |
| 블로그 | `blog.naver.com` 등 블로그 링크 |

Excel은 항상 `통합_결과`, `원본_모바일`, `원본_PC` 3개 시트로 저장됩니다.

- `통합_결과`: 주 산출물 시트입니다.
- `원본_모바일`, `원본_PC`: V1.2까지의 레거시 3시트 구조를 유지하기 위한 시트입니다. **상세 수집(PC) 경로에서는 별도 모바일 수집을 하지 않으므로**, 이 두 시트는 `통합_결과`의 데이터를 각 시트의 축소 컬럼으로 투영한 **미러 성격**을 가집니다. 특히 `원본_모바일`은 명칭과 달리 상세 수집(PC) 소스 데이터가 투영될 수 있습니다. 시트명/구조 정리는 후속 단계에서 다룹니다.

---

## 4. 프로젝트 구조

```text
naver-place-sales-db-crawler-v1/
├── README.md
├── LEGAL_NOTICE.md
├── RELEASE_CHECKLIST.md
├── PROJECT_STATE.md
├── implementation_plan.md
├── requirements.txt
├── .env.example
├── app.py
├── build.bat
├── docs/
├── src/
│   ├── crawler.py            # 모바일 리스트 수집(빠른 수집)
│   ├── parser.py             # 모바일/레거시 결과 파싱
│   ├── exporter.py           # 3시트 Excel 저장(통합_결과 11컬럼)
│   ├── merger.py             # 레거시 모바일+PC 병합
│   ├── pc_crawler.py         # 레거시 PC 리스트 수집(fallback로 보존)
│   ├── ui.py                 # GUI / 수집 모드 분기
│   └── pc/                   # PC 단일 엔진(상세 수집)
│       ├── config.py         # DiagnosticConfig
│       ├── safety.py         # 예외 분류
│       ├── diagnostics.py    # 진단 산출물 저장
│       ├── browser_session.py# Playwright 세션 / iframe 탐색
│       ├── list_scraper.py   # searchIframe 리스트 수집
│       ├── detail_scraper.py # 카드 클릭 → entryIframe 상세 수집
│       ├── pipeline.py       # collect_pc_full 오케스트레이션
│       └── export_adapter.py # PC full 결과 → 통합_결과 직결
├── tests/
│   ├── test_excel_validation.py
│   ├── test_exporter_schema.py
│   ├── test_export_adapter.py
│   ├── test_ui_pc_full_wiring.py
│   ├── test_pc_config.py
│   ├── test_pc_safety.py
│   ├── test_pc_diagnostics.py
│   ├── test_pc_pipeline.py
│   ├── test_pc_list_scraper.py
│   ├── test_pc_browser_session.py
│   └── test_pc_detail_scraper.py
├── input/
├── logs/
└── output/
```

---

## 5. 실행 방법

### 환경 설정

```powershell
# 1. 가상환경 생성 및 활성화
python -m venv .venv
.venv\Scripts\activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. Playwright 브라우저 설치
playwright install chromium
```

### 실행

GUI 진입점은 `app.py`입니다.

```powershell
python app.py
```

실행 후 UI에서 지역, 업종, 수집 개수, 수집 모드를 선택합니다.

- **빠른 수집(모바일)**: 빠른 전화영업 DB 수집 (모바일 리스트 기반)
- **상세 수집(PC·전화·SNS)**: PC 단일 엔진으로 카드 클릭 → 상세 진입하여 대표전화·주소·플레이스 URL·리뷰수·새로오픈여부·홈페이지/SNS 링크 수집

### 배포 EXE 실행 (최종 사용자)

개발 환경 없이 실행 파일(EXE)로 배포/사용하는 경우입니다.

**빌드(배포자):**

```powershell
# 사전: .venv 활성화 + playwright install chromium 완료 상태에서
build.bat
```

- 빌드 후 `dist/` 폴더에 다음이 생성됩니다.
  - `dist/NaverPlaceSalesDBCollector.exe`
  - `dist/ms-playwright/` (브라우저 번들)
- **배포 시 EXE와 `ms-playwright` 폴더를 반드시 같은 폴더에 함께** 두어야 합니다. EXE는 자기 옆의 `ms-playwright`를 브라우저 실행 경로로 사용합니다.

**실행(사용자):**

- `NaverPlaceSalesDBCollector.exe`를 더블클릭하면 GUI가 실행됩니다.
- 수집 결과 Excel은 **EXE가 실행된 위치 기준 `output/` 폴더**에 저장됩니다.
- EXE 실행 시에는 진단 모드가 자동으로 비활성화되어(안전 모드), 브라우저는 화면 밖에서 동작하고 진단 산출물은 저장되지 않습니다.

**안내:**

- 최초 실행 시 내부 압축 해제로 수 초~수십 초가 걸릴 수 있습니다.
- 일부 백신은 PyInstaller onefile EXE를 오탐할 수 있습니다. 필요 시 예외 처리 후 사용하세요.
- `ms-playwright` 폴더가 EXE 옆에 없으면 브라우저를 찾지 못해 실행되지 않습니다.

### 주의사항

- 업종 추출은 불안정할 수 있으며, 빈 값으로 출력될 수 있습니다 (오탐 방지 정책).
- 수집 건수는 검색 결과 DOM 구조에 따라 `limit` 미만이 될 수 있습니다.
- 상세 수집(PC)은 카드별 상세 진입이 있어 빠른 수집(모바일)보다 시간이 더 걸립니다.
- 대량/반복 수집은 네이버 이용약관 위반 가능성이 있으니 자제합니다.
- CAPTCHA/보안 확인이 나타나면 우회하지 않고 중단·기록합니다.
- 수집된 데이터의 활용 방법은 반드시 `LEGAL_NOTICE.md`를 확인하세요.

---

## 6. 법적 주의

본 프로젝트는 공개 사업장 대표 정보를 영업 조사 및 방문/전화 영업 준비용으로 정리하는 도구입니다.

광고성 문자, 이메일, 카카오톡 등 전자적 광고 발송은 관련 법령에 따른 수신 동의와 수신거부 절차를 준수해야 합니다. 자세한 내용은 `LEGAL_NOTICE.md`를 확인해야 합니다.
