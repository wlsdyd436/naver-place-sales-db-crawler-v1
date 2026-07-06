# 프로젝트 상태 관리 (PROJECT_STATE.md)

## 1. 프로젝트 개요

- **프로젝트명**: 네이버 플레이스 영업 DB 수집기 V1.2
- **목표**: 광고대행사, POS/키오스크 영업자, 식자재 유통업체가 바로 영업에 활용할 수 있는 공개 사업장 DB를 수집하고 Excel로 정리한다.
- **현재 방향**: GUI 기반 Basic/Premium 모드 분리 운영
- **핵심 원칙**: 상세 페이지 진입 없이 리스트 화면에서 확보 가능한 정보만 수집한다.

---

## 2. 설계 변경 기록

### 2026-06-04

- Gemini 분석 결과에 따라 수집 타겟을 PC 네이버 지도에서 모바일 웹으로 변경했다.
- 기존 방향이었던 PC 네이버 지도 `map.naver.com/v5/search` 기반 접근을 V1 범위에서 제외했다.
- `searchIframe`, `entryIframe` 접근 방식은 V1에서 사용하지 않기로 했다.
- 상세 페이지 클릭/진입은 V1에서 제외했다.
- 리뷰 수, 영업시간, 평점은 V1 수집 필드에서 제외했다.
- V1은 모바일 웹 리스트 화면 중심의 최소 수집 방식으로 설계한다.
- V1.2에서 GUI 진입점은 `app.py`로 확정하고 CLI 전용 `main.py`는 제거했다.
- 기획/시장 분석 문서는 `docs/` 폴더로 이동했다.

---

## 3. V1.2 수집 범위

Basic Mode 수집 필드:

- 업체명
- 업종
- 주소
- 대표전화
- 플레이스 URL
- 수집일

Premium Mode 통합 결과 필드:

- 업체명
- 업종
- 새로오픈여부
- 리뷰수
- 주소
- 대표전화
- 플레이스 URL
- 수집일

제외 필드:

- 리뷰 수
- 영업시간
- 평점
- 상세 페이지 내부 정보
- 대표자명
- 개인 휴대폰 번호
- 개인 이메일

---

## 4. 개발 및 진행 단계

- [x] STEP 0: 고객 문제 및 사업성 분석
- [x] STEP 0.1: 법적 리스크 검토 및 `LEGAL_NOTICE.md` 작성
- [x] STEP 0.2: 모바일 웹 타겟팅으로 설계 변경
- [x] STEP 1: 환경 구성 및 실행 준비
- [x] STEP 2: 모바일 웹 리스트 수집기 구현
- [x] STEP 3: 리스트 DOM 파서 구현 (parser.py)
- [x] STEP 4: Excel 저장 및 중복/무전화 업체 정리 (exporter.py)
- [x] STEP 5: GUI 실행 진입점 통합 및 MVP 검증 (`app.py`)
- [x] STEP 6: GUI 기반 지역/업종/모드 선택 구조 적용
- [x] STEP 7: 대전 카페 / 대전 미용실 / 대전 치킨 기준 안정성 테스트 완료
- [x] STEP 8: Premium Mode PC 리스트 수집 및 Safe Merge 실험
- [x] STEP 9: 폴더 구조 정리 (`docs/` 추가, `main.py` 삭제)
- [ ] STEP 10: 크몽 납품형 상품화 준비

---

## 5. 운영 리스크 관리

- V1은 무리한 차단 우회보다 모바일 웹 리스트 화면 중심의 최소 수집을 우선한다.
- 내부 API 우회, 캡차 우회, 대량 요청 자동화는 V1 범위에 포함하지 않는다.
- 대표자명, 개인 휴대폰 번호, 개인 이메일은 수집하지 않는다.
- 광고성 문자/이메일 발송 기능은 포함하지 않는다.
- 수집 결과는 공개 사업장 대표 정보 기반 영업 조사 및 영업 준비용으로만 사용한다.

---

## 6. 2026-06-04 안정화 기록

### 구현 완료

- STEP 1~7 전체 완료. V1 MVP 실행 가능 상태 확인.
- `src/crawler.py`: m.map.naver.com 모바일 웹 리스트 수집기. `li` selector 효라우테이 및 fallback 구조 유지.
- `src/parser.py`: 주소 "주소보기" 제거, 진짜 업체명 검증, 빈 레코드 필터링.
- `src/exporter.py`: openpyxl 기반 Excel 저장, 열 너비 자동 조정.
- `app.py`: CustomTkinter GUI 실행 진입점.
- `src/ui.py`: Basic/Premium 모드 선택, 수집 실행, Excel 저장, output 폴더 열기.
- `src/merger.py`: 모바일 Basic 결과를 기준으로 PC Premium 리뷰수/신규오픈 여부를 안전 병합.

### 안정성 테스트 결과

| 키워드 | 수집 결과 |
|---|---|
| 대전 카페 | 10건 성공 |
| 대전 미용실 | 10건 성공 |
| 대전 치킨 | 10건 성공 |

### 기록된 이슈

- 업종 오탐 문제 확인: `span` 셀렉터 포함 시 예약, 공유가격 등 UI 텍스트가 업종으로 오탐되는 문제 확인.
- V1 정책: 업종 추출 실패 시 빈 값("") 허용 (Graceful Degradation). 오염 데이터 차단 우선.
- CLI 전용 `main.py`는 V1.2 GUI 구조에서 제거됨.

### 다음 작업 후보

- 업종 셀렉터 정확도 개선 실험 (Selector 갱신 또는 제외 확정)
- 키워드 다중 배치 실행 기능 추가 검토
- 크몽 납품형 상품화 준비 (STEP 8)

# 2026-06-25 정식 출시 전 제어 시스템(Queue/Stop/Pause) 1차 완성 기록

## 완료

- 제어 UI 적용
- 다중 지역 Queue
- 다중 키워드 Queue
- Progress 표시
- Stop 기능
- Pause / Resume 기능
- Excel 저장 안정화

## 검증

- Queue 정상
- Basic 정상
- Premium 정상
- Stop 정상
- Pause 정상
- Resume 정상

## 다음 작업

- ETA 계산
- 리뷰수 필터
- 새로오픈 필터
- 온라인채널 필터
- 최종 QA

# 2026-06-30 성능/필터 안정화 기록 (정식 출시 전 PC 단일 엔진 전환 설계 단계 진입 전)

## 완료
- ETA 표시 및 보정
- 리뷰수 필터 연결
- 새로오픈 필터 연결
- PC 크롤러 Card 기반 성능 리팩토링
- PC Pagination / CAPTCHA 발생 조건 검증
- Basic candidate/saved 차이 원인 확인
- skip 통계 로그 추가
- 운영 로그 UX 일부 개선

## 확인
- Basic 86개 후보 중 11개는 네이버 UI 요소, 실제 업체 75개 확인
- PC Premium 속도 병목은 anchor → ancestor 역탐색 구조였음
- Card 기반 리팩토링 후 PC 파싱 속도 개선
- Pagination은 가능하지만 CAPTCHA 리스크 존재
- 표준 wheel scroll 방식이 안정성에 중요함

## 다음 작업
- PC Premium Pagination 안정화
- CAPTCHA 발생 시 안전 저장/중단 정책 보강
- 운영 로그 최종 정리
- 온라인채널/B안은 출시 후 개선 후보 또는 고급 상품 후보로 보류

# 2026-07-01 CAPTCHA 감지 타이밍 진단 기록

## 배경

정식 출시 전 PC 단일 엔진 전환 설계 단계에서, 기존 미커밋 `src/pc_crawler.py` 변경을 rollback한 뒤 `강동구 카페 limit=100`으로 page=3 페이지네이션 실패를 재현/진단했다. 최소 패치(텍스트 기반 캡차 셀렉터 제거) 적용 후에도 동일 증상이 재현되어, 원인을 더 정확히 파악하기 위한 별도 타이밍 진단(probe)을 진행했다. 이번 기록은 그 결과를 정리한 것이며, 이 시점에는 `src/pc_crawler.py`에 대한 추가 패치를 적용하지 않기로 했다.

## 테스트 목적

`#wtm-captcha-root`가 page 2 → page 3 전환 시점에 정확히 언제(클릭 전 / 클릭 도중 / 클릭 후) 나타나는지 시간대별로 확인하여, 기존 캡차 감지 로직(`count() > 0 and is_visible()`)이 놓치는 원인을 특정한다.

## 확인된 사실

1. `#wtm-captcha-root`는 `searchIframe` 내부에 페이지 최초 로드 시점부터 `count=1`로 존재할 수 있음이 확인됨 — page1 스크롤 이전부터, page2 진입 전/후 등 전 구간에서 동일하게 존재.
2. 그러나 `is_visible()`은 전 구간에서 한 번도 `True`를 반환하지 않음.
3. 그럼에도 page 2 → page 3 클릭 시 Playwright `TimeoutError`가 발생했고, 예외 trace에서 `wtm-captcha-root` 하위 요소가 실제로 pointer event를 가로챈 것으로 확인됨.
4. 따라서 `count() > 0`만으로 캡차를 판정하면 오탐 위험이 있고(상시 존재 요소일 수 있음), `is_visible()`만으로는 감지가 불충분함이 확인됨.
5. 클릭/페이지네이션 실패 예외 메시지에 `wtm-captcha-root`가 포함될 때 이를 CAPTCHA/보안 차단으로 분류하는 방식이, 확인된 사실 기준으로는 가장 신뢰도 높은 향후 `pc_safety` 설계 후보로 판단됨.
6. 오늘 반복된 live test로 세션/IP 차단 강도가 누적됐을 가능성이 있어, 추가 live test는 중단함.
7. visible browser 진단 모드는 향후 PC 단일 엔진 구조 설계 단계에서 검토 예정.

## 기각된 가설

- **텍스트 셀렉터(`text=보안`/`text=사람`/`text=자동`) 제거가 page=3 실패의 원인**이라는 가설 — 해당 셀렉터 유무와 무관하게 동일 실패가 재현되어 기각.
- **캡차가 page 2→3 전환 "도중"에 새로 나타나는 타이밍 레이스**라는 가설 — 캡차 관련 요소가 전환 이전, 최초 로드 시점부터 이미 존재한 것으로 확인되어 기각.

## 현재 판단

`is_visible()` 단독 또는 `count() > 0` 단독 판정 모두 캡차 감지 기준으로 적합하지 않다. 현재 시점에는 `src/pc_crawler.py`에 대한 추가 패치를 적용하지 않고, 이번 진단 결과를 향후 PC 단일 엔진 설계(안전 종료/캡차 판정 모듈)에 반영할 참고 자료로만 기록한다.

## 향후 PC 단일 엔진 safety 설계 반영 항목

- 사전 가시성 체크(`is_visible()`) 대신, 클릭/페이지네이션 실패 시 예외 메시지에 `wtm-captcha-root` 포함 여부를 사후에 파싱해 CAPTCHA/보안 차단으로 분류하는 방식 검토.
- `count() > 0`만으로 판정하지 않도록 함 — 상시 존재 요소로 인한 오탐 방지.
- 캡차 판정을 단발성 이벤트가 아니라, 반복 실패/차단 누적을 감지해 세션 단위로 조기 안전 종료하는 정책과 함께 설계.
- 부분 저장/안전 종료 정책과 캡차 판정 개선을 같은 축(안전 종료 트리거 신뢰도)으로 묶어 설계.
- visible browser 진단 모드 도입 여부는 PC 단일 엔진 구조 설계 단계에서 별도 검토.

## 추가 테스트 중단 이유

오늘 짧은 시간 내 라이브 테스트를 여러 차례 반복 실행했고, 증상이 회차마다 악화되는 패턴(전면 차단 → 부분 실패 → 상시 캡차 요소 존재)이 관찰되었다. 이는 코드 결함과 별개로 해당 세션/IP에 대한 네이버 측 차단·감시 강도가 누적됐을 가능성을 시사한다. 이 상태에서 추가 반복 테스트는 진단 신호를 오염시킬 수 있어 중단하고, 시간을 두고 재진단하기로 한다.

## 다음 작업

- 시간 경과 후 동일 조건(`강동구 카페 limit=100`)으로 재진단하여, 오늘 관찰이 상시 재현되는 문제인지 오늘의 반복 테스트로 인한 일시적 악화인지 구분.
- `pc_safety`/`safety_manager` 설계 시 "예외 메시지 기반 캡차 분류" 방식을 1순위 후보로 검토.
- 이 기록은 첫 정식 출시 후보를 위한 PC 단일 엔진 전환 설계의 안전 종료 정책 설계에 입력값으로 사용.


# 2026-07-03 PC 단일 엔진 Stage 2 신규 모듈 구현 기록

## 완료
- src/pc/browser_session.py 신규 생성
- src/pc/list_scraper.py 신규 생성
- tests/test_pc_browser_session.py 신규 생성
- tests/test_pc_list_scraper.py 신규 생성

## 구현 방향
- 기존 pc_crawler.py는 수정하지 않고 spec 참조로만 사용
- Stage 1 pipeline 계약에 맞는 collector 구조 구현
- 진단 캡처 1차 책임은 browser_session/list_scraper 계층에 둠
- pipeline은 부분 보존 및 fallback 역할 유지
- 공식 collector는 exc.page를 붙이지 않고 diagnostics_captured=True 마커만 사용

## 검증
- test_pc_browser_session.py PASS 12 / FAIL 0
- test_pc_list_scraper.py PASS 19 / FAIL 0
- pc_crawler.py, ui.py, exporter.py, parser.py, crawler.py 및 Stage 1 파일 무변경 확인

## 다음 작업
- 통제된 count parity 검증
- page=3 이상 진입 검증
- CAPTCHA 발생 시 반복 live test 금지
- entryIframe 상세 진입은 후속 단계로 보류


# 2026-07-03 PC 단일 엔진 Stage 2 신규 리스트 경로 통제 검증 기록

## 배경
- Stage 2에서 browser_session.py와 list_scraper.py 신규 독립 모듈 구현 완료.
- 기존 실행 경로(pc_crawler.py/ui.py/exporter.py/parser.py/crawler.py)는 수정하지 않음.
- 신규 경로가 실제 네이버 지도 PC 리스트에서 page=3까지 진입 가능한지 1회 통제 검증.

## 실행 조건
- 엔진: 신규 엔진만
- keyword: 서울특별시 강동구 카페
- limit: 30
- visible: True
- capture_artifacts: True
- live test: 1회만 실행
- 기존 엔진 재실행 없음
- 반복 테스트 없음

## 결과
- new_count: 30 / 30
- max_page_seen: 3
- CAPTCHA 언급: 0
- wtm-captcha-root 언급: 0
- Timeout 언급: 0
- diagnostics_captured: False
- elapsed: 약 20.48초
- 예외 없음
- 부분 보존 로직 발동 없음

## 판단
- 신규 list_scraper + browser_session + pipeline 조합은 정상 성공 경로에서 page=3까지 진입 가능함.
- 이전 2026-07-01 CAPTCHA/page=3 실패는 상시 재현 문제가 아니라 특정 세션/요청 누적 조건에서 발생했을 가능성이 있음.
- CAPTCHA 실패 경로는 이번 live test에서 발생하지 않았으므로 실제 live 환경에서는 미검증이며, 현재는 test_pc_list_scraper.py의 mock 기반 계약 검증 상태로 유지.
- 반복 live test는 차단 누적 리스크가 있으므로 중단.

## 다음 작업
- 추가 live test는 즉시 반복하지 않음.
- 다음 설계 단계에서 entryIframe 상세 진입/대표전화 수집 구조를 검토.
- 기존 ui.py/Excel/Queue 연결은 후속 단계까지 보류.
- CAPTCHA 발생 시에는 session/list_scraper 계층에서 diagnostics를 1차 캡처하는 계약 유지.

# 2026-07-03 PC 단일 엔진 Stage 3A 상세 수집 모듈 구현 기록

- src/pc/detail_scraper.py 신규 생성
- browser_session.py에 find_entry_frame 추가
- list_scraper.py에 place_id / 플레이스 URL 가산 필드 추가
- build_full_collector() 신규 추가
- list_scraper.build_collector()는 Stage 2 list-only 의미 유지
- pipeline.py 수정 없음
- 단건 상세 실패는 skip
- 연속 상세 실패는 diagnostics 캡처 후 안전 종료
- tests/test_pc_detail_scraper.py PASS 11
- test_pc_list_scraper.py PASS 20
- test_pc_browser_session.py PASS 15
- test_pc_pipeline.py PASS 8


# 2026-07-06 PC 단일 엔진 Stage 3B 카드 클릭 기반 상세 수집 재설계 기록

## 배경
- Stage 3A live probe에서 리스트 href 기반 place_id 사전 확보가 실패함.
- DOM 진단 결과 리스트 카드 anchor href는 "#"이고, 클릭 전 place_id/플레이스 URL이 노출되지 않는 구조로 확인됨.
- Gemini/Antigravity Browser 실측 결과, 카드 클릭 후 entryIframe URL에서 place_id를 사후 확보하는 방식이 필요함.

## 구현
- src/pc/detail_scraper.py를 카드 index 클릭 기반 융합 순회 구조로 재설계.
- build_full_collector()는 list row 생성 후 같은 카드 index를 클릭하여 entryIframe을 대기하고 상세 값을 병합.
- place_id와 플레이스 URL은 entryIframe 실제 URL에서 확보.
- 정보 탭은 보안 확인 발생 가능성이 있어 Stage 3B에서는 폐기하고 home 탭만 사용.
- 전화/주소/홈페이지/SNS는 home 탭의 place_blind 라벨 기반 구조에서 추출.
- 홈페이지/인스타/블로그는 row dict에는 수집하지만 exporter/ui 배선은 Stage 3C로 보류.

## 테스트
- tests/test_pc_detail_scraper.py: PASS 19 / FAIL 0
- tests/test_pc_list_scraper.py: PASS 21 / FAIL 0
- tests/test_pc_browser_session.py: PASS 15 / FAIL 0
- tests/test_pc_pipeline.py: PASS 8 / FAIL 0

## 리스크
- 정보 탭 클릭 시 보안 확인이 발생했으므로 정보 탭 기반 확장은 보류.
- 실제 카드 간 이동은 최종 smoke로 별도 확인 필요.
- home 탭에 외부 링크가 1개만 노출되는 업체가 있을 수 있어 홈페이지/인스타/블로그 전체 분리는 후속 검증 필요.

## 다음 작업
- 사용자 감독 하에 limit=1~2 최종 live smoke 1회.
- 성공 시 Stage 3B 검증 기록 추가.
- 이후 Stage 3C에서 exporter/ui 컬럼 배선 여부 판단.


# 2026-07-06 PC 단일 엔진 Stage 3B 최종 live smoke 기록

## 실행 조건
- keyword: 서울특별시 강동구 카페
- limit: 1
- visible: True
- capture_artifacts: True
- 실행 횟수: 1회
- 정보 탭 클릭 없음
- home 탭만 사용
- 반복 실행 없음

## 결과
- full_count: 1
- 업체명: 오베르캄프 본점
- place_id: 1171815551
- 플레이스 URL: https://pcmap.place.naver.com/restaurant/1171815551/home
- 주소: 서울 강동구 성내로14길 48 1층 8강동구청역 2번 출구에서 866m 미터
- 대표전화: 0507-1387-4967
- 홈페이지: 공란
- 인스타: https://www.instagram.com/oberkampf.kr
- 블로그: 공란
- entryIframe 진입 성공: True
- title wait 성공: True
- CAPTCHA/Timeout 신호: False
- diagnostics_captured: null
- 예외 발생: 없음
- 부분 결과 보존: on_partial_save 0회

## 판단
- Stage 3B의 핵심 구조인 카드 index 클릭 → entryIframe wait → place_id 사후 확보 → 상세 데이터 병합이 실제 환경에서 성공함.
- place_id, 플레이스 URL, 대표전화, 주소, 인스타 링크 수집이 확인됨.
- CAPTCHA/Timeout은 발생하지 않음.
- 정보 탭은 보안 확인 유발 가능성이 있으므로 계속 보류하고 home 탭 중심 전략을 유지함.
- 반복 live test는 하지 않음.

## 발견된 개선점
- 주소 값에 길찾기/거리 정보가 이어 붙는 현상 확인.
- 예: "서울 강동구 성내로14길 48 1층 8강동구청역 2번 출구에서 866m 미터"
- 이는 주소 라벨 값 div 전체 텍스트를 읽으면서 주소 외 안내 문구가 함께 포함된 것으로 판단됨.
- 다음 단계에서 주소 정제 또는 주소 selector 세분화가 필요함.

## 다음 작업
- Stage 3B.1 주소 정제 보정
- 저장된 home HTML 또는 mock 기반 테스트로 주소에서 역/출구/거리 안내 제거
- live test 반복 없이 단위 테스트 우선
- 이후 Stage 3C에서 exporter/ui 컬럼 배선 여부 판단


# 2026-07-06 PC 단일 엔진 Stage 3B.1 주소 정제 보정 기록

## 배경
- Stage 3B 최종 live smoke에서 place_id, 플레이스 URL, 대표전화, 주소, 인스타 수집은 성공함.
- 다만 주소 값에 역/출구/거리 안내 문구가 함께 붙는 현상이 확인됨.
- 예: 서울 강동구 성내로14길 48 1층 8강동구청역 2번 출구에서 866m 미터

## 완료
- src/pc/detail_scraper.py의 주소 추출 로직 보정
- tests/test_pc_detail_scraper.py 테스트 보강
- live test 없이 저장된 DOM 증거와 mock 테스트 기반으로 처리

## 구현 방향
- 주소 row 내부의 span.pz7wy 값을 우선 사용
- span.pz7wy가 없을 때만 기존 전체 텍스트 fallback 사용
- fallback 텍스트에서는 역/출구/거리 안내 문구 제거
- 번지, 층, 호수 정보는 제거하지 않도록 테스트로 확인

## 정제 예시
- 기존: 서울 강동구 성내로14길 48 1층 8강동구청역 2번 출구에서 866m 미터
- 목표: 서울 강동구 성내로14길 48 1층

## 테스트
- tests/test_pc_detail_scraper.py: PASS 23 / FAIL 0
- tests/test_pc_list_scraper.py: PASS 21 / FAIL 0
- tests/test_pc_browser_session.py: PASS 15 / FAIL 0
- tests/test_pc_pipeline.py: PASS 8 / FAIL 0

## 다음 작업
- Stage 3C Export Schema / Excel 출력 연결 여부 검토
- 홈페이지/인스타/블로그를 Excel 컬럼에 포함할지 별도 판단
- ui.py 연결 전에는 기존 Excel 컬럼 보존과 상품 구성 기준을 먼저 확정


# 2026-07-06 PC 단일 엔진 Stage 3C Export Schema 구현 기록

## 배경
- Stage 3B에서 PC full collector가 place_id, 플레이스 URL, 주소, 대표전화, 인스타 링크 수집에 성공함.
- Stage 3B.1에서 주소 정제 보정까지 완료함.
- 다음 단계로 새 PC full row를 기존 Excel 출력 스키마에 연결하기 위한 export schema 확장을 진행함.

## 완료
- src/exporter.py의 MERGED_COLUMNS에 홈페이지, 인스타, 블로그 3개 컬럼 append
- 기존 통합_결과 8개 컬럼 이름/순서/위치 보존
- MOBILE_COLUMNS / PC_COLUMNS 불변
- src/pc/export_adapter.py 신규 생성
- 새 PC full row를 parse_places를 거치지 않고 통합_결과로 직접 투영하는 얇은 어댑터 추가
- place_id는 row 내부 유지, Excel 비노출로 확정
- ui.py 연결은 하지 않음
- pc_crawler.py / parser.py / merger.py 무변경

## 최종 통합_결과 컬럼
1. 업체명
2. 업종
3. 새로오픈여부
4. 리뷰수
5. 주소
6. 대표전화
7. 플레이스 URL
8. 수집일
9. 홈페이지
10. 인스타
11. 블로그

## 테스트
- tests/test_exporter_schema.py: PASS 7 / FAIL 0
- tests/test_export_adapter.py: PASS 2 / FAIL 0
- tests/test_pc_detail_scraper.py: PASS 23 / FAIL 0
- tests/test_pc_list_scraper.py: PASS 21 / FAIL 0
- tests/test_pc_browser_session.py: PASS 15 / FAIL 0
- tests/test_pc_pipeline.py: PASS 8 / FAIL 0

## 참고
- tests/test_excel_validation.py는 통합_결과 기대 컬럼을 11개로 동기화함.
- 기존 output 파일은 과거 8컬럼 산출물이므로, 과거 파일 대상으로 validation을 실행하면 컬럼 불일치가 날 수 있음.
- 신규 산출물부터 11컬럼 스키마가 기준임.

## 다음 작업
- Stage 3D UI 연결 설계
- 새 PC full engine을 기존 Queue / Stop / Pause / Excel 저장 흐름에 어떻게 연결할지 검토
- 기존 pc_crawler.py는 삭제하지 않고 legacy/fallback으로 유지
- ui.py 연결 전 ETA, 부분 저장, 실패 처리, 기존 모드 흐름 영향 검토 필요


# 2026-07-06 PC 단일 엔진 Stage 3D UI premium 경로 연결 기록

## 배경
- Stage 3B에서 카드 index 클릭 기반 PC full collector가 실제 smoke에 성공함.
- Stage 3C에서 통합_결과 Excel 스키마를 11컬럼으로 확장하고 export adapter를 추가함.
- 다음 단계로 새 PC full engine을 기존 UI premium 실행 경로에 연결함.

## 완료
- src/ui.py의 _collect_premium_query 본문을 새 PC full engine 호출로 교체
- DiagnosticConfig.from_env()
- build_full_collector()
- collect_pc_full()
- 기존 premium 모바일+PC 병합 로직은 _collect_premium_query_legacy로 보존
- _run_queue_pipeline / 누적 / 저장 / export_places_to_excel 호출부는 수정하지 않음
- basic 분기는 수정하지 않음
- basic/premium 라디오 및 UI 텍스트는 수정하지 않음
- premium ETA 계수는 3.5에서 5.0으로 상향
- 반환 구조는 옵션 A 유지: (rows, [], rows)

## 현재 premium 동작
- premium 선택 시 새 PC full engine이 실행됨
- 카드 index 클릭 → entryIframe wait → place_id/주소/대표전화/플레이스 URL/SNS 수집
- parse_places / merger를 우회함
- 통합_결과에는 새 PC full row가 들어감
- 원본_PC에는 rows가 투영됨
- 원본_모바일은 기존 누적 로직 영향으로 rows 기반 투영 가능성이 있음
- 시트 역할 정리는 후속 UI cleanup 단계로 보류

## 테스트
- tests/test_ui_pc_full_wiring.py: PASS 3 / FAIL 0
- tests/test_exporter_schema.py: PASS 7 / FAIL 0
- tests/test_export_adapter.py: PASS 2 / FAIL 0
- tests/test_pc_detail_scraper.py: PASS 23 / FAIL 0
- tests/test_pc_list_scraper.py: PASS 21 / FAIL 0
- tests/test_pc_browser_session.py: PASS 15 / FAIL 0
- tests/test_pc_pipeline.py: PASS 8 / FAIL 0

## 리스크 / 참고
- 이제 premium 라디오는 내부적으로 새 PC full engine을 실행함.
- 기존 legacy premium은 _collect_premium_query_legacy로 남아 있어 롤백 가능함.
- 실제 UI에서 premium 수집 → Excel 저장까지의 end-to-end는 아직 live smoke 미검증.
- basic 분기는 기존 모바일 수집 그대로 유지됨.
- 행 수는 구버전 모바일+PC 병합 방식과 달라질 수 있음. 병합 탈락이 줄어드는 것은 의도된 개선임.

## 다음 작업
- Stage 3D UI end-to-end smoke 준비
- 조건: premium, limit=1, keyword=서울특별시 강동구 카페, visible=True, capture_artifacts=True
- 실제 UI 실행 또는 UI 경로를 최대한 모사한 smoke로 Excel 파일 생성 확인
- 반복 live test 금지
- 성공 후 Stage 3D 검증 기록 추가


# 2026-07-06 PC 단일 엔진 Stage 3D UI end-to-end smoke 기록

## 실행 조건
- premium 경로 모사
- keyword: 서울특별시 강동구 카페
- limit: 1
- visible: True
- capture_artifacts: True
- 실행 횟수: 1회
- 정보 탭 클릭 없음
- home 탭만 사용
- 반복 실행 없음

## 결과
- _collect_premium_query 호출 성공: True
- rows count: 1
- mobile_rows count: 0
- pc_rows count: 1
- 업체명: 오베르캄프 본점
- place_id: 1171815551
- 플레이스 URL: https://pcmap.place.naver.com/restaurant/1171815551/home
- 주소: 서울 강동구 성내로14길 48 1층
- 대표전화: 0507-1387-4967
- 홈페이지: 공란
- 인스타: https://www.instagram.com/oberkampf.kr
- 블로그: 공란
- Excel 파일 생성: True
- 통합_결과 시트 존재: True
- 통합_결과 11컬럼 일치: True
- place_id Excel 비노출: True
- 원본_PC 시트 존재: True
- CAPTCHA/Timeout 신호: False
- 예외 발생: 없음

## 판단
- Stage 3D의 핵심 목표인 UI premium 경로 → 새 PC full engine → Excel 생성 흐름이 실제로 성공함.
- Stage 3B.1 주소 정제 보정도 실제 UI smoke 결과에 반영됨.
- 통합_결과 11컬럼 스키마가 정상 적용됨.
- place_id는 내부 필드로 유지되고 Excel에는 노출되지 않음.
- CAPTCHA/Timeout 없이 완료됨.
- 반복 live test는 하지 않음.

## 현재 의미
- 새 PC 단일 엔진이 독립 모듈 상태를 넘어 실제 UI premium 실행 경로에 연결됨.
- 기존 모바일+PC 병합 방식은 _collect_premium_query_legacy로 보존됨.
- basic 경로는 기존 모바일 수집 흐름으로 유지됨.
- 출시 후보에 가까운 end-to-end 흐름이 처음으로 확인됨.

## 다음 작업
- Stage 3E UI Cleanup / 시트 의미 정리 설계
- basic/premium 라벨 정리 여부 판단
- 원본_모바일 / 원본_PC 시트 의미 정리
- legacy premium fallback 유지 방식 정리
- 온라인 채널 존재 필터 배선 여부 검토
- 첫 출시 후보 체크리스트 준비


# 2026-07-06 PC 단일 엔진 Stage 3E UI Cleanup / 출시 문서 정렬 기록

## 배경
- Stage 3D에서 UI premium 경로 → 새 PC full engine → Excel 생성 end-to-end smoke가 성공함.
- 이후 실제 동작과 README/UI 문구/법적 안내/출시 체크리스트의 불일치를 정리하기 위해 Stage 3E를 진행함.

## 완료
- README.md를 현재 동작 기준으로 전면 갱신
- Premium 구 설명을 새 상세 수집 흐름으로 정정
- 상세 수집은 PC 단일 엔진 기반이며 카드 클릭 → entryIframe 상세 진입 → 주소/전화/플레이스 URL/SNS 수집 구조임을 반영
- 통합_결과 11컬럼 스키마 반영
- 홈페이지/인스타/블로그 컬럼 설명 추가
- place_id는 내부 필드이며 Excel 비노출임을 명시
- 원본_모바일 / 원본_PC 시트는 레거시 3시트 구조 유지용이며, 새 상세 수집 경로에서는 축소 미러 성격이 있을 수 있음을 문서화
- src/ui.py 라디오/체크박스 텍스트만 수정
  - Basic → 빠른 수집(모바일)
  - Premium → 상세 수집(PC·전화·SNS)
  - 온라인 채널 체크박스 → 온라인 채널(블로그/인스타 등) 존재 (준비 중)
- 라디오 value, mode_var, on_mode_change, 수집 분기, 저장 로직은 변경하지 않음
- LEGAL_NOTICE.md에 2026-07-06 기준 상세 진입/SNS 공개정보 수집 관련 보완 섹션 추가
- RELEASE_CHECKLIST.md 신규 생성
- 온라인 채널 필터 배선은 하지 않음. Stage 3F 후보로 분리함.

## 테스트
- test_ui_pc_full_wiring: PASS 3 / FAIL 0
- test_exporter_schema: PASS 7 / FAIL 0
- test_export_adapter: PASS 2 / FAIL 0
- test_pc_detail_scraper: PASS 23 / FAIL 0
- test_pc_list_scraper: PASS 21 / FAIL 0
- test_pc_browser_session: PASS 15 / FAIL 0
- test_pc_pipeline: PASS 8 / FAIL 0

## 판단
- Stage 3E는 런타임 동작 변경 없이 문서/문구 정렬만 완료함.
- README의 기존 구 설명과 실제 동작 불일치를 해소함.
- UI 문구가 현재 실제 동작과 더 일치하게 됨.
- 출시 후보 문서 기반이 마련됨.

## 다음 작업 후보
- Stage 3F 온라인 채널 필터 배선 여부 판단
- 또는 첫 출시 후보 점검 / 패키징 / 사용자 실행 테스트 준비
- 시트명/시트 구조 변경은 아직 보류
- basic 경로 제거/통합도 보류
- legacy premium fallback 제거도 보류


# 2026-07-06 PC 단일 엔진 Stage 3F 패키징 문서·설정 위생 기록

## 배경
- Stage 3D에서 UI premium 경로 end-to-end smoke가 성공함.
- Stage 3E에서 README / LEGAL_NOTICE / RELEASE_CHECKLIST / UI 문구 정렬을 완료함.
- Stage 3F에서는 첫 출시 후보 준비를 위해 패키징 실행 문서와 환경 예시를 현재 코드 기준으로 정리함.

## 완료
- .env.example 최신화
  - 구식 변수 DEFAULT_REGION / MIN_DELAY / MAX_DELAY / HEADLESS / MAX_PAGES 제거
  - 현재 코드가 실제로 읽는 PCCRAWLER_* 변수 기준으로 정리
  - PCCRAWLER_DEBUG
  - PCCRAWLER_VISIBLE
  - PCCRAWLER_CAPTURE_ARTIFACTS
  - PCCRAWLER_KEEP_OPEN_ON_ERROR
  - PCCRAWLER_VERBOSE
  - PCCRAWLER_KEEP_OPEN_TIMEOUT_SEC
  - 기본은 안전 모드이며 frozen(EXE) 환경에서는 env와 무관하게 안전 모드가 적용됨을 명시

- README.md 보완
  - 배포 EXE 실행 절 추가
  - build.bat 빌드 안내
  - EXE와 ms-playwright 폴더를 같은 dist 폴더에 배치해야 함을 명시
  - output 폴더 저장 위치 안내
  - EXE 실행 시 DiagnosticConfig 안전 모드 적용 안내
  - 최초 실행 지연 및 백신 오탐 가능성 안내

- RELEASE_CHECKLIST.md 보완
  - 패키징/빌드 체크 섹션 추가
  - Tier 1 번들 chromium smoke 계획 추가
  - Tier 2 EXE end-to-end smoke 계획 추가
  - 온라인 채널 필터는 Stage 3F가 아니라 후속 단계로 정정

## 수정하지 않은 것
- src/ 전체 무변경
- app.py 무변경
- build.bat 무변경
- NaverPlaceSalesDBCollector.spec 무변경
- 수집 로직 무변경
- UI 구조 무변경
- 시트 구조 무변경
- 온라인 채널 필터 미배선 유지
- live smoke 미실행

## 테스트
- test_pc_config: PASS 6 / FAIL 0
- test_pc_safety: PASS 9 / FAIL 0
- test_pc_diagnostics: PASS 8 / FAIL 0
- test_pc_pipeline: PASS 8 / FAIL 0
- test_pc_browser_session: PASS 15 / FAIL 0
- test_pc_list_scraper: PASS 21 / FAIL 0
- test_pc_detail_scraper: PASS 23 / FAIL 0
- test_exporter_schema: PASS 7 / FAIL 0
- test_export_adapter: PASS 2 / FAIL 0
- test_ui_pc_full_wiring: PASS 3 / FAIL 0

## 판단
- Stage 3F는 런타임 변경 없이 문서·설정 위생만 완료함.
- 첫 출시 후보 전 패키징 안내와 환경 예시의 불일치를 해소함.
- build.bat / 브라우저 번들 최적화는 보류함.
- 현재 번들 구조로 먼저 EXE 실행 가능성을 검증하는 것이 우선임.

## 다음 작업
- Tier 1 번들 chromium smoke
  - PLAYWRIGHT_BROWSERS_PATH=dist/ms-playwright 기준으로 번들 chromium이 실제 구동되는지 확인
  - build 없이 1회만 실행
- Tier 2 EXE end-to-end smoke
  - build.bat 실행 후 dist/NaverPlaceSalesDBCollector.exe로 실제 GUI 실행
  - 상세 수집 limit=1
  - Excel 11컬럼 생성 확인
  - 별도 승인 후 1회만 실행


# 2026-07-07 Tier 1 번들 chromium smoke 성공 기록

## 실행 조건
- PLAYWRIGHT_BROWSERS_PATH=dist/ms-playwright
- keyword: 서울특별시 강동구 카페
- limit: 1
- visible: True
- capture_artifacts: True
- collect_pc_full 직접 호출
- 실행 횟수: 1회
- 정보 탭 클릭 없음
- CAPTCHA 우회/회피 없음

## 결과
- dist/ms-playwright 존재: True
- chromium 폴더: chromium-1223, chromium_headless_shell-1223
- PLAYWRIGHT_BROWSERS_PATH 일치: True
- collect_pc_full 호출 성공: True
- rows count: 1
- 업체명: 오베르캄프 본점
- place_id: 1171815551
- 플레이스 URL: https://pcmap.place.naver.com/restaurant/1171815551/home
- 주소: 서울 강동구 성내로14길 48 1층
- 대표전화: 0507-1387-4967
- 인스타: https://www.instagram.com/oberkampf.kr
- CAPTCHA/Timeout 신호: False
- 예외 발생: 없음

## 판단
- 번들된 chromium(dist/ms-playwright/chromium-1223)이 실제 Playwright 실행에서 정상 구동됨.
- requirements.txt의 playwright==1.60.0과 번들 리비전 1223 정합성은 실제 구동으로 간접 확인됨.
- EXE 빌드 전 브라우저 번들 리스크가 1차 해소됨.
- Tier 2 EXE end-to-end smoke가 다음 출시 게이트로 남음.