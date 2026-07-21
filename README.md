# 네이버 플레이스 영업 DB 수집기 V1.2

지역 기반 소상공인 영업을 하는 광고대행사, POS/키오스크 영업자, 식자재 유통업체를 위한 **영업 DB 엑셀 수집 도구**입니다.

GUI 실행 진입점인 `app.py`를 기준으로 동작합니다. 시/도·구(다중 선택)·법정동/역상권 세부구역과 키워드를 선택하면 검색 조합을 자동으로 생성하고, 브라우저가 검색 과정에서 정상적으로 수신한 목록 응답을 처리해 업체 데이터를 Excel로 저장합니다.

---

## 1. 핵심 방향

- GUI 기반 실행 (`app.py`)
- 지역(시/도 + 구 다중 선택 + 법정동/역상권 세부구역) + 키워드 선택 → 검색 조합 자동 생성
- 브라우저가 검색 과정에서 정상적으로 수신한 응답을 처리해 업체 목록 데이터로 변환합니다. 별도의 HTTP 클라이언트로 네이버 엔드포인트를 직접 호출하는 구조는 사용하지 않습니다.
- 검색 결과 목록 화면만 사용하며, 카드를 클릭해 상세 화면으로 진입하지 않습니다(상세 페이지 미진입).
- 검색 조합 내부 중복 제거(검색 조합당 수집 상한) → 전체 검색 조합 전역 중복 제거(전체 목표 저장 개수) 2단계로 중복을 제거합니다.
- 전체 목표 저장 개수에 도달하거나 선택한 검색 조합을 모두 실행하면 종료합니다.
- CAPTCHA·요청 제한(429) 감지 시 우회하지 않고 즉시 중단하며, 그때까지 수집된 결과가 있으면 저장합니다.
- Excel 저장을 통한 즉시 영업 활용
- 본 프로그램은 네이버 공식 제품이거나 네이버와 제휴한 제품이 아닙니다.
- 참고: 이전 버전의 `빠른 수집(모바일)`/`상세 수집(PC·전화·SNS)` 엔진 코드는 삭제하지 않고 내부 롤백 경로로 보존되어 있으나, 현재 UI 기본 실행 경로는 아닙니다.

검색 흐름:

```text
https://map.naver.com/v5/search/{지역+업종}
  -> 검색 결과 목록 화면에서 브라우저가 정상적으로 수신한 응답을 관찰
  -> 응답에 포함된 업체 목록 데이터를 그대로 사용(카드 클릭·상세 페이지 진입 없음)
```

---

## 2. 수집 필드

`통합_결과` 시트 기준 11컬럼:

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

> `place_id`와 `source_city`/`source_district`/`source_subregion`/`source_layer`/`source_query`는 중복 제거·내부 진단용 필드이며 **Excel에는 노출하지 않습니다**. 사용자에게는 위 11컬럼만 제공됩니다.

필드별 참고:

- 업체명/업종/리뷰수/주소/대표전화/플레이스 URL/수집일은 검색 목록 응답에 포함된 값을 그대로 사용하며, 응답에 값이 없으면 빈칸일 수 있습니다.
- 홈페이지/인스타/블로그는 사업장이 플레이스에 **스스로 공개한 대표 링크**를 도메인 기준으로 분류한 값입니다(개인정보 아님). 업체별로 링크가 없으면 빈칸일 수 있습니다.
- **새로오픈여부는 현재 항상 빈칸입니다.** 검색 목록 응답만으로는 신뢰할 수 있는 새로오픈 여부를 확인할 수 없어, 열은 남겨두되 값을 채우지 않습니다. 같은 이유로 UI의 "새로오픈 업체만 수집" 필터는 현재 비활성화(disabled)되어 있습니다.

제외 항목:

- 영업시간
- 평점
- 대표자명
- 개인 휴대폰 번호
- 개인 이메일

---

## 3. 결과물

수집 결과가 1건 이상이면 Excel 파일로 저장합니다. **수집 결과가 0건이면 Excel 파일을 만들지 않습니다**(빈 파일을 남기지 않음).

실제 저장 경로 예시(파일명은 화면에서 지정한 저장 경로의 파일명을 기준으로, 실행 시각 타임스탬프가 자동으로 붙습니다 - 열려 있는 파일과의 덮어쓰기 충돌 방지):

```text
output/<파일명>_YYYYMMDD_HHMM.xlsx
```

`통합_결과` 출력 컬럼(11컬럼):

| 컬럼명 | 설명 |
|---|---|
| 업체명 | 검색 목록 응답 기준 업체명 |
| 업종 | 카테고리 (추출 불안정, 빈 값 허용) |
| 새로오픈여부 | 현재는 항상 빈 값(§2. 수집 필드) |
| 리뷰수 | 검색 목록 응답 기준 리뷰 수(값 없으면 빈 값) |
| 주소 | 검색 목록 응답 기준 주소(값 없으면 빈 값) |
| 대표전화 | 검색 목록 응답 기준 대표전화(값 없으면 빈 값) |
| 플레이스 URL | 업체 상세 페이지 URL |
| 수집일 | 수집 실행일 (YYYY-MM-DD) |
| 홈페이지 | 대표 외부 링크 중 인스타/블로그가 아닌 홈페이지(없으면 빈 값) |
| 인스타 | `instagram.com` 링크(없으면 빈 값) |
| 블로그 | `blog.naver.com` 등 블로그 링크(없으면 빈 값) |

Excel은 `통합_결과`, `원본_모바일`, `원본_PC` 3개 시트로 저장됩니다(`src/exporter.py` 기준, 시트 구조 무변경).

- `통합_결과`: 주 산출물 시트이며 위 11컬럼 데이터가 들어갑니다.
- `원본_모바일`, `원본_PC`: 과거 모바일/PC 분리 수집 구조를 유지하기 위한 시트입니다. 현재 기본 수집 경로는 목록 응답 하나만 사용하므로 이 두 시트는 **항상 헤더만 있는 빈 시트**로 저장됩니다.

---

## 4. 수집 개수와 중단·저장 정책

두 입력값은 서로 다른 의미이며 독립적인 양의 정수입니다.

| 입력값 | 의미 | 기본값 |
|---|---|---|
| 검색 조합당 수집 상한 | 검색 조합(지역+업종) 하나에서 중복 제거 후 사용할 최대 개수 | 30 |
| 전체 목표 저장 개수 | 여러 검색 조합 결과를 전역 중복 제거한 뒤 최종 저장할 목표 개수 | 300 |

- **전체 목표 저장 개수는 최대 목표값이며, 지역·업종·검색 결과 및 서비스 상태에 따라 목표에 미달할 수 있습니다.** "300개 보장"을 의미하지 않습니다.
- 목표 개수에 도달하면 남은 검색 조합은 실행하지 않고 그 시점까지의 결과를 저장합니다.
- 검색 가능한 고유 업체 수가 목표보다 적으면 선택한 검색 조합을 모두 실행한 뒤, 그때까지의 결과를 저장합니다(목표 미달 가능).

수집이 끝나는 경우와 저장 여부:

| 상황 | 저장 여부 |
|---|---|
| 전체 목표 개수 도달 | 저장 |
| 선택한 검색 조합을 모두 실행(목표 미달 가능) | 저장 |
| CAPTCHA(보안 확인) 감지 | 우회하지 않고 즉시 중단, 그때까지 결과가 있으면 저장 |
| 요청 제한(429) 감지 | 우회하지 않고 즉시 중단, 그때까지 결과가 있으면 저장 |
| 브라우저 페이지 오류 | 즉시 중단, 그 이전까지의 결과가 있으면 저장 |
| 사용자 중지 버튼 | 즉시 중단, 그때까지 결과가 있으면 저장 |

- **위 어떤 경우든 수집된 결과가 1건 이상 있을 때만 저장됩니다.** 결과가 0건이면 어떤 경우에도 Excel 파일을 만들지 않습니다("항상 부분 저장된다"는 의미가 아닙니다).
- Excel 저장 자체(디스크 쓰기 등)에서 오류가 발생하면 저장되지 않을 수 있습니다. 이 경우 프로그램은 저장 성공 문구를 표시하지 않고 저장 실패를 화면에 알립니다.
- CAPTCHA/429 감지 시 프로그램은 이를 해결하거나 회피하려고 시도하지 않습니다. 짧은 시간에 반복 실행하지 말고 잠시 후 다시 시도하세요.

---

## 5. 프로젝트 구조

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
│   ├── crawler.py            # 레거시 모바일 리스트 수집(내부 롤백 경로로 보존)
│   ├── parser.py             # 레거시 결과 파싱
│   ├── exporter.py           # 3시트 Excel 저장(통합_결과 11컬럼)
│   ├── merger.py             # 레거시 모바일+PC 병합
│   ├── pc_crawler.py         # 레거시 PC 리스트 수집(내부 롤백 경로로 보존)
│   ├── ui.py                 # GUI / 수집 엔진 배선(기본: Network/List)
│   └── pc/
│       ├── config.py                    # DiagnosticConfig, BrowserBackendConfig
│       ├── safety.py                    # 예외 분류
│       ├── diagnostics.py               # 진단 산출물 저장
│       ├── browser_session.py           # BrowserSession(launch)/NativeCdpBrowserSession(native_cdp, 기본값)
│       ├── network_list_scraper.py      # 목록 응답 파싱/매핑/dedup + DOM membership/식별자 guard(현재 기본 엔진)
│       ├── network_browser_collector.py # DomMembershipCollector(현재 기본, DOM-first+Fiber place_id) / NetworkBrowserCollector(레거시 보존, 명시 지정 시만 사용)
│       ├── network_pipeline.py          # 검색 조합 큐 오케스트레이션(현재 기본 엔진)
│       ├── list_scraper.py              # 레거시 searchIframe 리스트 수집(내부 롤백 경로)
│       ├── detail_scraper.py            # 레거시 카드 클릭 → entryIframe 상세 수집(내부 롤백 경로)
│       ├── pipeline.py                  # 레거시 collect_pc_full 오케스트레이션(내부 롤백 경로)
│       └── export_adapter.py            # 레거시 PC full 결과 → 통합_결과 직결
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
│   ├── test_pc_browser_session_cdp.py    # NativeCdpBrowserSession(native_cdp) 검증
│   └── test_pc_detail_scraper.py
├── input/
├── logs/
└── output/
```

---

## 6. 실행 방법

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

### Windows Native Browser + CDP

2026-07-21부터 기본 브라우저 backend는 Playwright 번들 Chromium을 직접 띄우는 방식(`launch`)이 아니라, **Windows에 설치된 네이티브 Microsoft Edge 또는 Google Chrome을 백그라운드로 실행한 뒤 CDP(Chrome DevTools Protocol)로 연결하는 방식(`native_cdp`)**입니다.

- **요구사항**: Windows에 Microsoft Edge 또는 Google Chrome 중 하나 이상이 설치되어 있어야 합니다(대부분의 Windows 10/11에는 Edge가 기본 설치되어 있음).
- **탐색 순서**: 1) 사용자가 지정한 custom browser 경로 → 2) Microsoft Edge → 3) Google Chrome. 아래 경로를 순서대로 탐색합니다.
  - Edge: `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` → `C:\Program Files\Microsoft\Edge\Application\msedge.exe` → `%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe`
  - Chrome: `C:\Program Files\Google\Chrome\Application\chrome.exe` → `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe` → `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`
  - 둘 다 찾지 못하면 Playwright 번들 Chromium으로 조용히 대체하지 않고, 탐색한 경로와 해결 방법이 포함된 명확한 오류를 표시합니다.
- **전용 profile**: 사용자의 평소 Edge/Chrome 프로필이 아니라 `%LOCALAPPDATA%\NaverPlaceSalesDbCrawler\browser_profiles\{edge|chrome}` 전용 프로필을 사용합니다. 동일 프로필을 두 프로세스가 동시에 사용하려 하면 `profile_in_use` 오류로 명확히 차단됩니다(다른 backend로 조용히 전환하지 않음).
- **디버깅 포트**: 고정 포트가 아니라 매 실행마다 `127.0.0.1`에서만 열리는 임시(동적) 포트를 사용합니다. 외부 네트워크 인터페이스에는 노출되지 않습니다.
- **정상 종료**: 프로그램이 실행한 브라우저 프로세스(PID)만 종료합니다. `taskkill /IM`처럼 이미지 이름으로 모든 Edge/Chrome 창을 닫는 방식은 사용하지 않으므로, 사용자가 평소 쓰던 Edge/Chrome 창에는 영향이 없습니다.
- **launch backend(개발·테스트용)**: 기존 Playwright 번들 Chromium 실행 방식은 삭제되지 않고 개발·테스트 전용 fallback으로 보존되어 있습니다. 필요 시 환경 변수 `PCCRAWLER_BROWSER_BACKEND=launch`로 명시적으로 전환할 수 있으며(배포 EXE에서는 이 환경 변수가 무시되고 항상 `native_cdp`가 사용됩니다), 프로덕션 배포 시에는 사용하지 않습니다.
- **문제 해결**:
  - `BrowserExecutableNotFoundError`: Edge 또는 Chrome을 설치하거나, 환경 변수 `PCCRAWLER_BROWSER_PATH`로 실행 파일 경로를 직접 지정하세요.
  - `profile_in_use`: 이미 실행 중인 다른 수집 프로세스가 끝날 때까지 기다린 뒤 다시 시도하세요.
  - `CdpStartupError`(CDP 준비 실패/timeout): 브라우저가 비정상 종료되었거나 포트가 막혀있을 수 있습니다. 잠시 후 다시 시도하세요.
- Native Browser + CDP 방식은 현재 Windows 환경과 검증 검색(서울특별시 강동구 천호동 카페)에서 Edge 2회·Chrome 2회 실측과 단일 Live 검증 모두 CAPTCHA·HTTP 403/405/429 없이 수집에 성공했으며, 기존 Playwright launch 환경(동일 검색에서 page 2 HTTP 405로 반복 중단)과 다른 결과를 보였습니다. 이는 모든 환경·검색어에서 항상 차단을 우회한다는 의미가 아니며, CAPTCHA·403·405·429 감지와 안전 중단 정책은 이 backend 교체와 무관하게 그대로 유지됩니다(§4. 수집 개수와 중단·저장 정책).

### 실행

GUI 진입점은 `app.py`입니다.

```powershell
python app.py
```

실행 후 UI에서 다음을 선택/입력합니다.

- 시/도 + 구(다중 선택) + 법정동/역상권 세부구역
- 키워드(업종, 1개만 지원)
- 검색 조합당 수집 상한(기본값 30)
- 전체 목표 저장 개수(기본값 300, 보장값 아님 - §4. 수집 개수와 중단·저장 정책)
- 새로오픈 업체만 수집 필터는 현재 비활성화(disabled)되어 있습니다(§2. 수집 필드).

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
- 전체 목표 저장 개수는 최대 목표값이며, 지역·업종·검색 결과에 따라 미달할 수 있습니다(§4. 수집 개수와 중단·저장 정책).
- 새로오픈 업체만 수집 필터는 현재 지원하지 않습니다(항상 비활성화).
- 대량/반복 수집은 네이버 이용약관 위반 가능성이 있으니 자제합니다.
- CAPTCHA·요청 제한(429)이 감지되면 우회하지 않고 즉시 중단하며, 그때까지 수집된 결과가 있으면 저장합니다(0건이면 파일 미생성). 짧은 시간에 반복 실행하지 말고 잠시 후 다시 시도하세요.
- 수집된 데이터의 활용 방법은 반드시 `LEGAL_NOTICE.md`를 확인하세요.

---

## 7. 법적 주의

본 프로젝트는 공개 사업장 대표 정보를 영업 조사 및 방문/전화 영업 준비용으로 정리하는 도구입니다.

광고성 문자, 이메일, 카카오톡 등 전자적 광고 발송은 관련 법령에 따른 수신 동의와 수신거부 절차를 준수해야 합니다. 자세한 내용은 `LEGAL_NOTICE.md`를 확인해야 합니다.

---

## 8. DOM-first 단일 검색어 300건 수집(2026-07-21부터 기본 엔진)

`src/pc/network_browser_collector.py`의 `collect_dom_membership_query`(및 그 production wrapper인 `DomMembershipCollector`)가 제공합니다. **2026-07-21부터 `app.py`의 "수집 시작" 기본 동작이 이 엔진을 사용합니다**(`src/ui.py`의 `_run_network_pipeline` 기본 `collector_factory`가 `DomMembershipCollector`로 배선됨 - UI에 별도 토글은 없습니다). 이전 엔진(`NetworkBrowserCollector`/`collect_network_query`, Network 응답 관찰 기반)은 코드에 그대로 보존되어 있으며, 필요 시 코드에서 `collector_factory=NetworkBrowserCollector`를 명시적으로 지정하면 이전 경로로 되돌릴 수 있습니다(현재 UI에는 이 전환을 위한 화면 옵션이 없습니다).

- **DOM-first membership**: 검색 목록 화면(`iframe#searchIframe`)에서 검증된 scrollBy 증분 스크롤(`cdp_validation_tests/comprehensive_cdp_tester.py` 기준 - scrollHeight/row수/업체명수 3개 지표가 함께 안정될 때까지 단일 `frame.evaluate()` 안에서 반복)로 리스트를 끝까지 렌더링한 뒤, `li.UEzoS.rTjJo` row를 그대로 최종 업체 목록(membership)과 표시 순서로 사용합니다. Network 응답과 `window.__APOLLO_STATE__`는 그 DOM 업체의 구조화 필드(업종/리뷰수/주소 등)를 보강하는 용도로만 쓰이고, DOM에 없는 Network/Apollo 항목은 결과에 추가되지 않습니다.
- **React Fiber 기반 place_id 식별자(2026-07-21 추가)**: DOM 카드의 링크(`<a href>`)는 실측 결과 전부 `href="#"`(placeholder)라 URL에서 업체 ID를 안정적으로 얻을 수 없습니다. 대신 React가 각 DOM 노드에 심어두는 내부 속성(`__reactFiber$*`/`__reactProps$*` - 접두사 뒤 임의 문자열은 페이지 로드마다 바뀌므로 `Object.keys()`로 동적 탐색)에서 실제 업체 ID(`item.id`/`item.apolloCacheId`)를 읽습니다. 이 속성은 **React의 비공개 내부 구현이며 공식 API가 아닙니다** - Naver Map 프론트엔드 구조가 바뀌면 이 경로가 깨질 수 있습니다. 이를 대비해 다음 guard를 둡니다.
  - 1차: 알려진 경로(fast path)에서 `item.id`와 `item.apolloCacheId`를 각각 확인하고, 둘 다 있는데 값이 다르면 **CONFLICT로 판정하고 임의로 하나를 선택하지 않습니다**.
  - 2차(fast path 실패 시만): 깊이·방문 객체 수·순환 참조를 제한한 범위 탐색(bounded search)으로 `id`류 이름의 값을 찾되, 서로 다른 값이 2개 이상이면 역시 CONFLICT로 판정합니다.
  - 3차(그래도 없을 때): DOM anchor href 파싱을 최후 수단으로 시도합니다.
  - 숫자가 아니거나 비정상적으로 짧거나/긴 값은 애초에 후보로 인정하지 않습니다.
  - 어떤 방법으로도 확정하지 못해도(UNRESOLVED) **업체 row 자체는 삭제하지 않습니다** - 업체명/업종 등 DOM에서 바로 얻은 값은 그대로 보존됩니다.
- 단일 검색어, 최대 5페이지, 목표 300건 계약입니다.
- **상세 필드 채움률(구조적 한계 - 2026-07-21 Live 검증 300건 실측 기준)**: place_id 식별이 안정화된 뒤(300/300 확보, 충돌·미해결 0건) 업체명·업종·수집일 300/300, **주소 300/300**, 리뷰수 285/300까지는 정상적으로 채워집니다. 그러나 **대표전화(18/300)·플레이스 URL(17/300)·홈페이지(5/300)·인스타(5/300)·블로그(0/300)는 여전히 낮습니다** - 이는 매칭 정확도 문제가 아니라, 검색 목록 API 응답 자체에 전화번호/홈페이지 필드가 없기 때문입니다(실측 확인). 이 값들을 안정적으로 채우려면 업체 상세 페이지(entryIframe) 진입이 필요한데, 이는 "카드를 클릭해 상세 화면으로 진입하지 않습니다"라는 현재 제품의 핵심 설계 원칙(§1)과 충돌하고 300건 순차 클릭이라는 새로운 차단 위험을 추가하므로 현재는 채택하지 않았습니다.
- **안전 중단**: 기존과 동일하게 CAPTCHA·HTTP 403·405·429·iframe/list container 소실 시 즉시 중단하고 그때까지 결과를 보존합니다. 페이지 전환 완료는 "기대 페이지 번호와 실제 활성 페이지 번호 일치 + DOM top-10 이름 signature 변화"를 모두 확인해야 인정합니다(페이지 번호만으로 판단하지 않음).
- **문제 해결**: 300건 미만으로 끝나면 성공으로 표시하지 않습니다. CAPTCHA/HTTP 오류/전환 실패/식별자 확보 실패는 각각 별도로 진단 기록에 남습니다(자동 보완이나 재시도를 하지 않음).
