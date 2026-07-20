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


# 2026-07-07 Tier 2 EXE end-to-end smoke 성공 기록

## 실행 조건
- dist/NaverPlaceSalesDBCollector.exe 실행
- 실제 GUI 실행
- 수집 모드: 상세 수집(PC·전화·SNS)
- 지역: 서울특별시 강동구
- 키워드: 카페
- 수집 개수: 1
- 실행 횟수: 1회
- 정보 탭 클릭 없음
- CAPTCHA 우회/회피 없음

## 결과
- EXE 실행 성공
- GUI 표시 성공
- Excel 파일 생성 성공
- 생성 파일: naver_place_premium_db_20260707_0238.xlsx
- 통합_결과 시트 존재
- 통합_결과 11컬럼 일치
- place_id Excel 헤더 비노출
- 원본_모바일 시트 존재
- 원본_PC 시트 존재
- Excel 오류값 없음

## 통합_결과 1행
- 업체명: 오베르캄프 본점
- 업종: 베이커리
- 새로오픈여부: 공란
- 리뷰수: 2471
- 주소: 서울 강동구 성내로14길 48 1층
- 대표전화: 0507-1387-4967
- 플레이스 URL: https://pcmap.place.naver.com/restaurant/1171815551/home
- 수집일: 2026-07-07
- 홈페이지: 공란
- 인스타: https://www.instagram.com/oberkampf.kr
- 블로그: 공란

## 판단
- 현재 커밋 기준으로 빌드된 EXE가 실제 GUI 실행부터 Excel 생성까지 성공함.
- Stage 3B~3F의 핵심 변경 사항이 패키징된 EXE에서도 정상 동작함.
- Tier 1 번들 chromium smoke와 Tier 2 EXE end-to-end smoke가 모두 성공함.
- 첫 출시 후보의 핵심 실행 게이트를 통과함.

## 남은 보류 항목
- 온라인 채널 필터 배선
- 시트명/시트 구조 정리
- basic 경로 숨김 또는 단일 수집 UX 정리
- 다건 상세 수집 안정성 테스트
- 패키징 용량 최적화
- 영업용 소개자료/가격안/사용법 정리


# 2026-07-07 Stage OPT-A 리스트 스크롤 충분성 gate 구현

## 목적
- PERF-2(limit=3) 측정에서 총 wall 13.141초 중 카드 처리 합계(약 3.5초)를 제외한
  약 9.6초가 카드 외 오버헤드로 확인됨.
- 이 중 저위험으로 줄일 수 있는 후보로, 리스트 카드가 이미 충분히 로드된 경우에도
  무조건 수행되던 리스트 스크롤을 제거함.
- searchIframe settle(5초), entryIframe wait 등 안정성과 직결된 대기는 이번 범위에서
  건드리지 않음.

## 변경 파일
- src/pc/list_scraper.py
- src/pc/detail_scraper.py
- tests/test_pc_list_scraper.py
- tests/test_pc_detail_scraper.py

## 구현 내용
- `_light_scroll_cards`에 선택 파라미터 `target_count=None` 추가.
  - `target_count=None`(기본값): 기존 동작 그대로 유지.
  - `target_count`가 정수이고 진입 시점에 이미 `anchors.count() >= target_count`이면
    스크롤을 아예 생략.
  - 스크롤 도중 `anchors.count() >= target_count`에 도달하면 `max_scrolls`를 다
    쓰기 전에 조기 종료.
- `collect_full`에서 `target_count = limit + max(5, limit // 2)` 공식으로 계산해
  `scroll_fn` 호출 시 전달.
  - `_build_row`에서 무효/중복 카드가 걸러질 수 있는 상황을 고려한 안전 마진.
- `scrape_list`(레거시 list-only 경로)는 변경하지 않음.

## 건드리지 않은 것
- searchIframe goto settle(5000ms)
- entryIframe wait / title·URL 판정 로직(`_wait_entry_updated`)
- 페이지 전환 후 wait_for_timeout(2000ms)
- Excel 스키마/시트 구조
- UI 구조/문구
- CAPTCHA 관련 로직(우회 시도 없음, 변경 없음)
- src/pc/browser_session.py, src/pc/pipeline.py, src/pc/config.py, src/exporter.py,
  src/ui.py, app.py, build.bat, spec

## 테스트 결과
- test_pc_list_scraper: PASS 24 / FAIL 0 (신규 3종 포함: target_count 충족 시 스크롤
  생략, 도중 도달 시 조기 종료, target_count=None 시 기존 동작 불변)
- test_pc_detail_scraper: PASS 24 / FAIL 0 (신규 1종 포함: collect_full이 scroll_fn에
  target_count 전달 확인 + 정상 순회/부분 보존 유지)
- test_pc_browser_session: PASS 15 / FAIL 0
- test_pc_pipeline: PASS 8 / FAIL 0
- test_exporter_schema: PASS 7 / FAIL 0
- test_export_adapter: PASS 2 / FAIL 0
- test_ui_pc_full_wiring: PASS 3 / FAIL 0
- 회귀 0건.

## 판단
- 코드 레벨에서 회귀 없이 소량 실행 시 불필요한 스크롤을 제거하는 저위험 최적화가
  완료됨.
- PERF-2 live 재측정은 이번 스테이지에서 수행하지 않음(다음 단계로 보류).

## 다음 작업
- PERF-2(limit=3) live 재측정 1회(별도 승인 후) — wall time 변화 확인, 누락률/
  상세성공률 유지 여부 확인.
- 통과 시 PERF-3(limit=10)로 진행.


# 2026-07-07 PERF-2R OPT-A 적용 후 limit=3 재측정 성공 기록

## 실행 조건
- keyword: 서울특별시 강동구 카페
- limit: 3
- dev 직접 스크립트(scratchpad/perf2_limit3_after_opta.py, 기존 스크립트 복사본)
- visible: True
- capture_artifacts: True
- 실행 횟수: 1회
- 정보 탭 클릭 없음
- CAPTCHA 우회/회피 없음
- 코드/테스트 무수정

## 결과
- rows count: 3 / 3
- 누락률: 0.0%
- 상세 성공률(place_id 채움률): 100% (3/3)
- 총 wall time: 12.689초 (기존 OPT-A 이전 13.141초 대비 -0.452초, -3.4%)
- 업체당 평균 시간(카드 처리): 1.346초 (기존 1.169초)
- 카드별 시간 avg/min/max/p90: 1.346 / 1.141 / 1.555 / 1.512초
- 필드 채움률: 대표전화 100%, 주소 100%, 플레이스 URL 100%, 인스타 100%,
  홈페이지 0%, 블로그 0% (업체 특성상 정상)
- CAPTCHA/Timeout 신호: 없음
- DetailCollectionAborted: 없음
- 예외 발생: 없음
- target_count 스크롤 생략 로그 확인됨:
  `[list_scraper] target_count(8) already satisfied, skip scroll`
  (limit=3 + max(5, 3//2)=5 → target_count=8, 공식대로 정확히 산출)
- report JSON: scratchpad/perf2_limit3_after_opta_report.json (기존
  perf2_limit3_report.json은 덮어쓰지 않고 별도 파일로 보존)

## 판단
- 안정성 게이트(rows 3/3·상세성공률 100%·CAPTCHA/Abort/예외 없음) 전부 유지되어 PASS.
- OPT-A의 스크롤 생략 로직이 로그로 명확히 검증됨(카드가 이미 충분히 로드되어 스크롤
  2회를 건너뜀).
- wall time은 소폭 개선(-3.4%)되었으나, 이번 실행에서는 카드 처리 자체 시간의 자연
  변동(네트워크/서버 응답)이 늘어 스크롤 절감분을 일부 상쇄함. 즉 개선폭은 제한적이며,
  이는 설계 단계에서 예측한 대로(고정 비용인 settle 5초 등이 그대로 남아 있어 소량
  실행에서는 효과가 부분적일 것) 부합함.
- settle(searchIframe)/entryIframe wait 등 추가 최적화는 안정성 직결 요소라 이번
  범위에서 계속 보류.

## 다음 작업
- PERF-3(limit=10) live 측정으로 진행(별도 승인 후).


# 2026-07-07 PERF-3 limit=10 상세 수집 성능·안정성 테스트 성공 기록

## 실행 조건
- keyword: 서울특별시 강동구 카페
- limit: 10
- dev 직접 스크립트(scratchpad/perf3_limit10.py, PERF-2R 계측 구조 재사용)
- visible: True
- capture_artifacts: True
- PLAYWRIGHT_BROWSERS_PATH 미설정(dev 기본 경로)
- 실행 횟수: 1회
- 정보 탭 클릭 없음
- CAPTCHA 우회/회피 없음
- 코드/테스트 무수정

## 결과
- rows count: 10 / 10
- 누락률: 0.0%
- 상세 성공률(place_id 채움률): 100% (10/10)
- 총 wall time: 21.6초
- 업체당 평균 wall time: 2.16초
- 카드 처리 평균(순수 상세 진입): 1.105초
- 카드별 시간 avg/min/max/p90: 1.105 / 0.878 / 1.824 / 1.227초
- 주소 채움률: 100%
- 대표전화 채움률: 90% (9/10, "감자집"만 공란)
- 플레이스 URL 채움률: 100%
- 홈페이지 채움률: 10% (1/10)
- 인스타 채움률: 80% (8/10)
- 블로그 채움률: 0%
- CAPTCHA/Timeout 신호: 없음
- DetailCollectionAborted: 없음
- 예외 발생: 없음
- target_count 스크롤 생략/조기종료 로그: 없음(빈 배열). limit=10의 target_count(=15)에
  이번 실행에서는 카드 로드량이 도달하지 못해 OPT-A 게이트가 발동 조건 미달로
  관여하지 않음(정상 동작, OPT-A 로직 자체 이상 아님).
- 새 진단 폴더 수: 0개
- report JSON: scratchpad/perf3_limit10_report.json

## PERF-2 / PERF-2R 대비 비교
| 지표 | PERF-2(전, n=3) | PERF-2R(후, n=3) | PERF-3(후, n=10) |
|---|---|---|---|
| wall time | 13.141s | 12.689s | 21.6s |
| 카드 처리 평균 | 1.169s | 1.346s | 1.105s |
| 업체당 wall 환산 | ~4.38s | ~4.23s | 2.16s |

- 카드 처리 평균은 세 실행 모두 약 1.1~1.35초 대역으로 안정적(엔진 자체 처리 비용은
  규모와 무관하게 일정).
- 업체당 wall 환산은 limit=10에서 2.16초로 크게 개선됨 — settle(5초) 등 쿼리당 1회
  고정비용이 더 많은 카드 수에 분산(amortize)되었기 때문으로, 설계 단계에서 예측한
  패턴(고정비용은 소량에서 비중이 크고 대량일수록 희석됨)과 일치.

## 판단
- 승인된 안정성 게이트(rows 10/10·누락률 ≤20%·상세성공률 ≥90%·CAPTCHA/Abort/예외
  없음·업체당 ≤8초) 전부 충족 → PASS.
- 대표전화 90%는 엔진 실패가 아니라 실제 업체가 대표전화를 등록하지 않았을 가능성으로
  판단(리스트/상세 모두 공란).
- 추가 속도 최적화(settle/entryIframe wait 등)는 안정성 직결 요소라 이번 범위에서
  계속 보류.

## 다음 작업
- PERF-3S: dev UI(`python app.py`)에서 Stop/Pause 및 부분 저장 확인(별도 승인 후).


# 2026-07-08 PERF-3S dev UI Pause/Resume/Stop 및 부분 저장 검증 기록

## 실행 조건
- keyword: 서울특별시 강동구 카페
- limit: 10
- 수집 모드: 상세 수집(PC·전화·SNS)
- 실행 방식: 개발환경 python app.py
- 정보 탭 클릭 없음
- CAPTCHA 우회 없음
- release_candidate/zip 생성 없음

## 결과 (Pause → Resume → Stop 중단 시나리오)
- 일시정지 동작: 정상
- 재개 동작: 정상
- 정지 동작: 정상
- 부분 저장: 정상
- Stop 시점 full collect done, rows=5
- pc full count=5
- 누적 통합_결과=5 / 누적 원본_모바일=5 / 누적 원본_PC=5
- Excel 저장 완료: output\naver_place_premium_db_20260708_1410.xlsx
- CAPTCHA/Timeout 없음, 예외 없음, 앱 강제 종료 불필요

## 추가 결과 (동일 조건, limit=10 끝까지 실행)
- full collect done, rows=10
- pc full count=10
- 누적 통합_결과=10 / 누적 원본_모바일=10 / 누적 원본_PC=10
- Excel 저장 완료: output\naver_place_premium_db_20260708_1410.xlsx
- CAPTCHA/Timeout 없음, 예외 없음

## 관찰된 사항
- `[browser_session] entryIframe found` 로그가 반복 출력됨 — 카드 클릭 후 상세 iframe을 정상 탐지했다는 debug 로그로 판단되며 오류는 아님.
- 내부 로그에 "모바일 원본" 표현이 남아 있음.

## 판단
- PERF-3S PASS: Pause / Resume / Stop / 부분저장 모두 성공 기준 충족.
- dev UI limit=10 full run PASS.

## UI 정리 후보 (별도 메모, 이번 단계에서는 배선/수정하지 않음)
- 수집 모드 제거 후보
- 온라인 채널 "(준비 중)" 표기 제거 후보
- `entryIframe found` 반복 debug 로그 숨김 또는 verbose 전용화 후보
- 로그 내 "모바일 원본" 표현 정리 후보

## 다음 작업
- PERF-4: limit=30 성능/안정성 테스트(별도 승인 후).


# 2026-07-08 PERF-4 limit=30 CAPTCHA 발생 및 안전 종료 검증 기록

## 실행 조건
- keyword: 서울특별시 강동구 카페
- limit: 30
- dev 직접 스크립트(scratchpad/perf4_limit30.py, PERF-3 계측 구조 재사용 후 삭제)
- visible: True
- capture_artifacts: True
- PLAYWRIGHT_BROWSERS_PATH 미설정(dev 기본 경로)
- 실행 횟수: 1회, 실패 후 재시도 없음
- 정보 탭 클릭 없음
- CAPTCHA 우회/회피 없음
- 코드/테스트 무수정

## 결과
- rows count: 15 / 30
- 누락률: 50.0%
- 상세 성공률(place_id 채움률): 66.7% (10/15)
- 총 wall time: 60.10초
- 업체당 평균 wall time: 4.01초
- 카드 처리 평균(순수 상세 진입): 2.82초
- 카드별 시간 avg/min/max/p90: 2.82 / 0.97 / 6.03 / 6.02초
- 주소 채움률: 66.7%
- 대표전화 채움률: 60.0%
- 플레이스 URL 채움률: 66.7%
- 홈페이지 채움률: 6.7%
- 인스타 채움률: 53.3%
- 블로그 채움률: 0.0%
- 페이지 전환: 발생, page=1 → page=2 (max_page_seen=2)
- target_count 스크롤 생략/조기종료 로그: 없음(빈 배열, limit=30의 target_count=35에 이번 실행에서 미도달)
- CAPTCHA/Timeout 신호: **CAPTCHA/보안 확인 발생** — page=2에서 카드 클릭 시 `#wtm-captcha-root`가 pointer event를 가로챔("보안 확인을 완료해 주세요")
- DetailCollectionAborted: 발생 — 연속 5건 상세 진입 실패로 세션 안전 종료
- 예외: DetailCollectionAborted 1건(예상된 안전 종료 경로, 미처리 예외 아님), 앱 크래시/강제 종료 없음
- 새 진단 폴더: `logs/diagnostics/20260708_142431_746696_서울특별시_강동구_카페_captcha_or_security_block/`
  (exception.txt, iframe_summary.json, metadata.json, page.html, screenshot.png, url.txt)
- report JSON: scratchpad/perf4_limit30_report.json (기록 반영 후 scratchpad 폴더 삭제)

## 판단
- PERF-4는 성공 기준(CAPTCHA/Timeout 없음)을 충족하지 못해 **FAIL**.
- 다만 엔진 안전 설계는 의도대로 정상 동작함: CAPTCHA 발생 → `classify_exception`이 `captcha_or_security_block`으로 정확히 분류 → 진단 캡처(1건) → `DetailCollectionAborted` 발생 → `pipeline.collect_pc_full`이 부분 결과(15건)를 그대로 반환. 크래시나 CAPTCHA 우회 시도 없이 안전 종료됨.
- 코드 결함이 아니라 30건·2페이지 규모에서 네이버 측 실제 보안 확인이 트리거된 운영 리스크로 판단됨. 2026-07-01/2026-07-03 기록의 "규모가 커질수록 CAPTCHA 리스크 증가" 가설과 일치.
- 이번 결과로 다음 단계 계획이 변경됨: 원래 예정이던 PERF-5(limit=50/100/300 등 대량 규모 확장 측정)는 보류하고, **CAPTCHA/대량 수집 리스크 설계 검토**를 다음 단계로 전환함.

## 다음 작업
- limit=50/100/300 등 대량 규모 성능 측정은 보류.
- CAPTCHA/대량 수집 리스크 설계 검토(예: 요청 간격 조정, 세션당 안전 처리 건수 상한, 실패 시 재개 전략 등)를 다음 단계 후보로 설정.


# 2026-07-08 SAFE-1V dev UI limit=30 보안 확인 대응 검증 기록

## 배경
- PERF-4(limit=30)에서 CAPTCHA/보안 확인이 발생했으나, 당시 UI는 이를 "정상 완료"로 오인시킬 수 있는 상태였음(엔진은 부분 결과를 반환하지만 UI가 CAPTCHA 발생 여부를 몰랐음).
- SAFE-1 설계(2026-07-08 Plan)에 따라 `collect_pc_full`에 `on_security_block` 콜백을 추가하고, `ui.py`에서 감지 시 정직한 안내·부분 저장·Queue 조기 중단을 배선함(커밋 `28956d1` 기능: 보안 확인 감지 시 부분 저장 안내 추가).
- 이번 SAFE-1V는 위 배선이 실제 dev UI에서 동작하는지 확인하는 live 검증이다.

## 실행 조건
- 실행 방식: 개발환경 `python app.py`
- 지역: 서울특별시 강동구
- 키워드: 카페
- 수집 개수: 30
- 수집 모드: 상세 수집(PC·전화·SNS, premium)
- 실행 횟수: 1회, 실패해도 재시도 없음
- 정보 탭 클릭 없음
- CAPTCHA 우회 없음
- 코드/테스트 무수정

## 실행 로그 요약
- page=1 수집 진행 → `collecting... 10/30` 도달
- page=2 진입 후 CAPTCHA/보안 확인 발생
- SAFE-1 로그 정상 출력:
  - `[ui] 보안 확인(CAPTCHA) 감지: 안전 중단합니다.`
  - `[ui] 현재까지 수집된 결과는 저장됩니다.`
  - `[ui] 남은 Queue는 반복 요청 방지를 위해 중단합니다.`
- pc full count=15
- 누적 통합 결과=15 / 누적 모바일 원본=15 / 누적 PC 원본=15
- Excel 저장 완료: `output\naver_place_premium_db_20260708_1453.xlsx`

## 판단
- **SAFE-1V PASS**: CAPTCHA 감지 PASS, 부분 저장 PASS, Queue 조기 중단 PASS.
- 앱 크래시 없음, CAPTCHA 우회 시도 없음.
- 30/30 정상 수집 자체는 이번에도 **FAIL**(page=2에서 CAPTCHA 재발생) — 다만 이번 검증의 목적은 "CAPTCHA 발생 시 UI가 정직하게 안내하고 안전하게 중단하는지"이며, 그 기준은 충족함.
- page=2에서 CAPTCHA가 반복적으로 발생하는 경향이 PERF-4에 이어 재확인됨. 현재 방식(딜레이/부하 완화 없음) 그대로 limit=50/100/300 테스트를 진행하는 것은 부적절하다고 판단.

## 다음 작업
- limit=50/100/300 테스트는 계속 보류.
- 다음 단계는 SAFE-2(수집 속도/배치/대량 수집 부하 완화 정책 설계)로 전환.

## UI 정리 후보 (누적, 이번 단계에서는 배선/수정하지 않음)
- 수집 모드 제거 후보
- 온라인 채널 "(준비 중)" 표기 제거 후보
- `entryIframe found` 반복 debug 로그 숨김 또는 verbose 전용화 후보
- 로그 내 "모바일 원본" 표현 정리 후보


# 2026-07-08 ARCH-300 PoC-1 착수 기록 (기술 검증, 제품 기능 아님)

## 원칙
- ARCH-300 PoC-1은 제품 기능 확정이 아니라 **기술 검증**이다.
- 직접 API 호출이 아니라 Playwright 브라우저가 정상 렌더링 중 자연히 발생시키는 응답을 관찰한다("브라우저 네트워크 응답 관찰" / Network·List collector — "네트워크 스니핑" 표현은 사용하지 않는다).
- CAPTCHA 우회/자동 해결/stealth/proxy/무단 반복 호출은 금지한다.
- UI/pipeline/product path에는 아직 연결하지 않는다(독립 모듈 + 독립 PoC 스크립트로만 검증).
- LEGAL_NOTICE.md/README.md/RELEASE_CHECKLIST.md의 정식 수정은 PoC 성공 후, 제품 기능 채택 여부를 판단하는 별도 단계에서 진행한다(이번 기록 시점에는 원칙만 남기고 해당 문서는 아직 수정하지 않음).

## PoC-1 live probe 결과 (2026-07-08, 1회 실행)
- 검색어: 서울특별시 강동구 카페, `map.naver.com/v5/search/...` 정상 렌더링(클릭/페이지 전환 없음).
- 후보 응답(candidate responses): 1건 — `map.naver.com/p/api/search/allSearch?...`(resource_type=xhr, status=200).
- `result.place.list`(알려진 경로)에서 업체 리스트 20건 추출, dedup 후에도 20건(충돌 없음).
- 앞 10개를 11컬럼 row로 매핑 성공(업체명/업종/리뷰수/주소/대표전화/플레이스 URL/수집일까지 채움). 과거 detail_scraper 실측(오베르캄프 본점 등)과 교차 검증상 값이 합리적으로 일치.
- CAPTCHA/429/보안 확인: 발생하지 않음(페이지 텍스트 보조 확인 포함).
- **300개 가능 여부는 아직 미확정.** 이번 PoC-1은 page=1 최초 렌더링만 관찰했으며, 페이지 전환(클릭 필요)을 포함한 PoC-2 이상에서 규모·CAPTCHA 재현 여부를 별도 검증해야 한다.

## 발견된 데이터 품질 이슈 및 PoC-1.1 보정
- **업종**: 응답의 category 값이 list(`["카페,디저트","베이커리"]`)인 경우 `_first_present`가 그대로 `str()`화해 `"['카페,디저트', '베이커리']"` 형태의 Python repr 문자열이 되는 문제 발견 → `_extract_category`를 신설해 list면 `", "`로 join, 문자열이면 그대로, 없으면 빈칸으로 정리.
- **홈페이지/인스타/블로그**: 응답의 `homePage` 필드가 네이버 UI 관례상 대표 외부 링크(인스타그램 링크 포함)를 종류 무관하게 담고 있어, 그대로 "홈페이지" 컬럼에 넣으면 인스타 링크가 홈페이지로 잘못 분류되는 문제 발견 → `_classify_external_links`를 신설해 `instagram.com`→인스타, `blog.naver.com`류→블로그, 그 외→홈페이지로 도메인 기준 분류(detail_scraper의 `_extract_entry_sns`와 동일한 관례 적용). 값이 list로 여러 개 와도 각각 분류.
- **리뷰수**: 기존 로직(`visitorReviewCount`/`reviewCount`/`blogReviewCount` 중 첫 확인값)이 이미 숫자/문자열 모두 크래시 없이 처리하고 있어 로직 변경 없음. 방문자/블로그 리뷰 분리가 필요해지면 확장할 수 있도록 주석만 보강.
- **플레이스 URL**: `place/{id}/home` 제네릭 세그먼트는 PoC 단계의 임시 구성이며 실제 리다이렉트 유효성은 미검증이라는 점을 주석으로 명확히 함(검증은 PoC-2 이상으로 이관, 이번 단계에서 live 재검증하지 않음).
- 테스트: `tests/test_pc_network_list_scraper.py`에 category list join, 인스타/블로그/일반 도메인/URL list 분류 테스트 5종 추가(총 14 PASS / FAIL 0). live 재실행 없이 fixture만으로 검증.


# 2026-07-08 ARCH-300 PoC-2 page=1→2 전환 실험 기록 (기술 검증, 제품 기능 아님)

## 목표
PoC-1이 관찰한 page=1 응답에 이어, 상세 카드 클릭/entryIframe 진입 없이 페이지네이션
"2"번 버튼만 클릭해 page=2 전환 후에도 추가 Network 응답이 관찰되는지, 새 place_id가
확보되는지 확인한다.

## 구현
- `scratchpad/arch300_network_probe/poc2_page2_probe.py` 신규(live probe, UI/pipeline 미연결).
- `src/pc/network_list_scraper.py`에 PoC-2용 공통 유틸 추가:
  - `_map_item_to_row`에 선택적 `source_page` 키워드 인자 추가(내부 디버그 메타, 미전달 시 기존 PoC-1 호출과 완전히 하위 호환, Excel 11컬럼에는 노출되지 않음).
  - `build_candidate_record`: 후보 response 관찰 기록을 일관된 dict로 조립하는 유틸(여러 probe 스크립트가 공용).
- probe 스크립트는 `src/pc/list_scraper._click_next_page`(페이지네이션 클릭)와 `src/pc/safety.classify_exception`(CAPTCHA 판정)을 **읽기 전용으로 재사용**했다(두 파일 모두 무수정). page=2 전환은 프로덕션 엔진과 동일한 로직으로 시도했다.
- `tests/test_pc_network_list_scraper.py`에 4종 추가(총 20 PASS / FAIL 0): page 간 seen 공유 시 place_id 기준 dedup, 중복 없을 때 row 수 증가, `source_page` 내부 메타가 `exporter.MERGED_COLUMNS`(11컬럼)에 없음(Excel 비노출) 확인, `build_candidate_record` 형태 검증.

## PoC-2 live 실행 결과 (1회, 재시도 없음)
- keyword: 서울특별시 강동구 카페
- page=1 최초 렌더링 직후, **페이지 텍스트 기반 CAPTCHA 마커 검사에서 `captcha_detected=True`가 발생하여 page=2 클릭을 시도조차 하지 않고 즉시 중단**했다(지침대로 우회 시도 없이 안전하게 종료).
- page1 candidate responses: 1건, page1 raw items: 20건, dedup 20건(=PoC-1과 동일하게 정상 파싱 성공).
- page2 candidate responses/raw items/dedup: 전부 0건(시도 자체를 안 했으므로).
- `page2_click_attempted=false`, `page2_click_succeeded=false`.

## 판단 — 이번 CAPTCHA 감지는 오탐(false positive)일 가능성이 높음
- `captcha_detected=true`이면서도 **동일 응답에서 20건이 완전히 정상 파싱**된 것은 모순적이다. 실제 CAPTCHA가 콘텐츠 로드를 막았다면 이렇게 깨끗하게 20건이 나오기 어렵다.
- 이는 2026-07-01 CAPTCHA 감지 타이밍 진단 기록과 정확히 일치하는 패턴이다: `#wtm-captcha-root`류 요소/문자열은 **페이지 최초 로드 시점부터 DOM에 상시 존재할 수 있으며, `is_visible()`은 그 구간에서 한 번도 True를 반환하지 않았다.** 이번 PoC-2의 `_looks_like_captcha_text`는 `page.content()` 전체 텍스트에서 `"captcha"`/`"wtm-captcha"` 등 **단순 substring 존재 여부만** 검사했으므로, 실제 활성 보안 확인 여부와 무관하게 상시 오탐할 수 있는 구조였다(가시성 미확인).
- 즉 이번 실행은 "page=2에서 CAPTCHA가 실제로 재현되었다"는 근거가 아니라, **PoC-2 스크립트 자체의 감지 로직 한계로 page=2 가설을 아직 검증하지 못한 상태**로 봐야 한다.

## 결과
- page=1→2 전환 여부: **미검증**(시도하지 않음).
- CAPTCHA/429/보안 확인 발생 여부: 페이지 텍스트 마커 기준 "감지됨"으로 기록되었으나, 위 판단에 따라 **실제 활성 CAPTCHA인지는 불확실(오탐 가능성 높음)**.
- 300개 가능 여부: 여전히 미확정. **이번 단계에서는 page=2 확장 가능성조차 실측하지 못했다.**

## 다음 작업
- limit=30/50/100 등 규모 확장 테스트로 넘어가지 않는다(page=2 자체가 아직 미검증).
- 다음 PoC-2 재시도(별도 승인 후 1회) 전에 CAPTCHA 감지 로직을 보강해야 한다: 단순 substring 검사 대신 `is_visible()` 기반 가시성 확인, 또는 `browser_session.probe_captcha_dom_present`처럼 이미 검증된 방식을 참고하거나, 클릭 실패 예외 기반 판정(`classify_exception`)에 더 무게를 두는 방향 검토.
- 진단 정확도를 높인 뒤 동일 조건(서울특별시 강동구 카페, page=1→2)으로 PoC-2를 1회 재시도.


# 2026-07-08 ARCH-300 PoC-2R CAPTCHA 감지 보정 및 page=1→2 재실험 기록 (기술 검증, 제품 기능 아님)

## 배경
직전 PoC-2는 page.content() 전체 텍스트의 단순 substring 검색으로 CAPTCHA를 오탐(20건이
정상 파싱됐음에도 captcha_detected=True)해 page=2 클릭 자체를 시도하지 못했다(INCONCLUSIVE).
이번 PoC-2R은 감지 로직을 가시성 기반 3단계로 보정한 뒤 동일 조건으로 1회 재실험했다.

## 감지 로직 보정
- `src/pc/network_list_scraper.py`에 `classify_captcha_signal(*, marker_present_in_dom, element_visible, bounding_box_area, click_exception_message)` 신설. Playwright 객체를 직접 다루지 않는 순수 함수(원시 신호를 호출자가 넘겨야 함 - fixture로 테스트 가능).
  - `passive_captcha_marker_found`: DOM/HTML에 마커 존재(가시성 무관) - **중단 근거 아님, 기록만**.
  - `active_captcha_detected`: 마커가 실제로 보이고(is_visible) 의미 있는 크기(bounding_box_area>0) - **중단 근거**.
  - `click_intercepted_by_captcha`: 클릭 예외 메시지에 CAPTCHA 키워드 포함(`safety.is_captcha_or_security_message` 읽기 전용 재사용) - **중단 근거**.
- `scratchpad/arch300_network_probe/poc2_page2_probe.py`를 전면 보정: `page.content()` 단순 텍스트 검사를 제거하고, `browser_session._CAPTCHA_PROBE_SELECTORS`(읽기 전용 재사용)로 각 마커 selector의 `count()`/`is_visible()`/`bounding_box()`를 직접 확인해 `classify_captcha_signal`에 넘기는 방식으로 교체. `src/pc/browser_session.py`, `src/pc/list_scraper.py`, `src/pc/safety.py`는 이번에도 무수정(읽기 전용 재사용만).
- 테스트: `tests/test_pc_network_list_scraper.py`에 3종 추가(총 25 PASS / FAIL 0) - passive만 있으면 중단 안 함, 가시성+크기 확인 시 active로 분류, 클릭 예외의 wtm-captcha-root가 강한 신호(click_intercepted_by_captcha)로 분류.

## PoC-2R live 실행 결과 (1회, 재시도 없음)
- keyword: 서울특별시 강동구 카페
- page=1: candidate responses 1건, raw items 20건, dedup 20건. **passive_captcha_marker_found=True, active_captcha_detected=False**(마커는 DOM에 있지만 `element_visible=False`, `bounding_box_area=0.0` - 상시 존재 placeholder임이 직접 확인됨) → 기록만 하고 page=2 클릭 계속 시도.
- page=2: `_click_next_page(frame, 2)` **클릭 성공**(예외 없음, `click_intercepted_by_captcha=False`). 클릭 후 3~5초 대기 후 재확인해도 여전히 passive만 있고 active 없음.
- page=2: candidate responses 1건, **raw items 70건, dedup 70건(page=1의 20건과 place_id 중복 0건, 전부 신규)**.
- **총 dedup row 수: 90건**(page=1의 20건 + page=2의 70건).
- `status_429_seen=false`.
- 상세 데이터 품질(저장된 상위 20건 = page=1분 전량) 확인 결과 업체명/업종(join 정상)/리뷰수/주소/대표전화/플레이스 URL/인스타 분류 모두 PoC-1.1 보정이 그대로 정상 반영됨. 다만 이번 저장 파일은 top 20만 기록해 page=2 표본은 개별 확인하지 못했고, 90건 중 dedup 카운트(정량 지표)로만 page=2 성공을 확인함.

## 판단
- **직전 PoC-2의 CAPTCHA 감지는 오탐이었음이 확인됨.** 가시성 기반으로 재확인한 결과 실제로는 active CAPTCHA도, 클릭 차단도 없었다.
- **page=1→2 전환은 실제로 성공**했고, CAPTCHA 없이 90건(20+70)을 확보했다 - PERF-4/SAFE-1V(카드 클릭 기반 엔진)에서 page=2 진입 시 반복적으로 CAPTCHA가 발생했던 것과 대조적으로, **카드 클릭 없이 페이지네이션만 사용하는 이번 접근에서는 같은 지점에서 CAPTCHA가 재현되지 않았다.** 이는 ARCH-300의 핵심 가설(클릭 볼륨을 줄이면 CAPTCHA 리스크가 낮아진다)과 일치하는 고무적인 신호다.
- 다만 **1회 실행 결과이며, 300개 가능 여부는 여전히 미확정.** page=3 이상, 더 큰 규모(50/100개 후보)에서도 동일하게 안전한지는 별도 검증이 필요하다.

## 다음 작업
- page=3까지 확장하거나(다음 PoC 후보), 현재 90건 규모에서 안정성을 한 번 더 재확인하는 것 중 우선순위 판단 필요.
- 300개 목표를 위해서는 여러 페이지에 걸친 반복 전환이 필요하므로, page 수가 늘어날수록 CAPTCHA 리스크가 다시 커질 가능성은 배제할 수 없음 - 규모를 단계적으로(예: page=3, 이어서 page=5) 늘려가며 매 단계 CAPTCHA 신호를 3단계 판정으로 재확인하는 점진적 접근을 권장.
- 여전히 UI/pipeline 미연결, LEGAL_NOTICE/README 정식 수정 없음.


# 2026-07-09 ARCH-300 PoC-3 page=1→2→3 점진 확장 실험 기록 (기술 검증, 제품 기능 아님)

## 목표
PoC-2R(page=1→2 성공, 90건, CAPTCHA 없음)에 이어 page=3까지만 소규모로 확장 검증한다.
300개 전면 확장이 아니며, UI/pipeline에는 연결하지 않는다.

## 구현
- `scratchpad/arch300_network_probe/poc3_page3_probe.py` 신규 - page=1→2→3을 루프로 순회하며 매 page 전환 전 3단계 CAPTCHA 신호(PoC-2R과 동일한 가시성 기반 판정)를 재확인하고, 응답 status=429 감지 시에도 즉시 중단하도록 추가.
- `src/pc/network_list_scraper.py`에 `count_rows_by_source_page(rows)` 신규 - source_page별 건수 집계(순수 함수, live 없이 테스트 가능). PoC-2와 동일하게 `browser_session._CAPTCHA_PROBE_SELECTORS`/`list_scraper._click_next_page`/`safety.is_captcha_or_security_message`를 읽기 전용으로만 재사용.
- `tests/test_pc_network_list_scraper.py`에 2종 추가(총 28 PASS / FAIL 0): 3페이지 병합 시 source_page별 건수 집계 및 "unknown" 처리, 중복 place_id가 섞인 3페이지 병합 시 총 dedup 건수 검증.
- 이번에는 `poc3_mapped_rows_full.json`으로 **전체** row를 저장(샘플 아님을 파일명에 명시, PoC-2의 "top 20만 저장" 한계를 보완).

## PoC-3 live 실행 결과 (1회, 재시도 없음)
- keyword: 서울특별시 강동구 카페
- page=1: candidate 1건, raw 20건, dedup 20건(정상).
- page=2: `_click_next_page(frame, 2)` **클릭은 성공**(예외 없음)했으나, 대기(4초) 동안 캡처된 후보 응답은 무관한 `pcmap-api.place.naver.com/graphql` 요청(status=405, JSON 파싱 실패) 1건뿐이었다. **실제 업체 리스트 응답은 이번 실행에서 캡처하지 못함**(raw=0, dedup=0) - PoC-2R에서는 동일 시나리오로 70건을 확보했던 것과 달리 이번엔 타이밍상 놓친 것으로 보인다(런마다 변동 가능성).
- page=3: `_click_next_page(frame, 3)` 클릭 시도 중 **실제 CAPTCHA에 의해 pointer event가 가로채였다**(Playwright 클릭 예외 발생, 요소가 실제로 보이는 상태(`element is visible, enabled and stable`)에서 `<div id="wtm-captcha-root">` 하위의 `aria-label="보안 인증 필요"` 다이얼로그가 클릭을 가로챔). `click_intercepted_by_captcha=True`로 정확히 분류되어 **즉시 중단**(우회 시도 없음).
- `active_captcha_detected=False`(주기적 가시성 체크 시점에는 아직 안 보였음), `passive_captcha_marker_found=True`(page=1/2 확인 시점 모두, 이전과 동일하게 상시 placeholder), `status_429_seen=False`.
- **총 dedup row 수: 20건**(page=1분만, page=2 실데이터 미포착 + page=3 도달 실패로 인해).

## 판단 — 이번 CAPTCHA는 오탐이 아니라 실제 신호로 판단됨
- PoC-2(오탐)와 달리 이번 신호는 **클릭 예외 기반**(`click_intercepted_by_captcha`)이며, Playwright 자체가 "element is visible, enabled and stable"이라고 확인한 상태에서 CAPTCHA 다이얼로그가 pointer event를 가로챈 것이 로그로 명확히 남았다. 3단계 판정 체계가 의도대로 "진짜 신호와 오탐을 구분"해낸 사례로 볼 수 있다.
- PERF-4/SAFE-1V(카드 클릭 기반 엔진)는 page=1→2 진입 시점에 CAPTCHA가 발생했던 반면, 이번 순수 페이지네이션 접근은 **page=2→3 전환 시점**(즉 한 단계 더 진행한 후)에 CAPTCHA를 만났다. 이는 "카드 클릭을 없애면 CAPTCHA 리스크가 완전히 사라진다"가 아니라 **"클릭/요청 볼륨이 늘어날수록 다시 리스크가 커진다"는 가설과 일치**한다.
- page=2의 실제 리스트 응답을 이번엔 캡처하지 못한 것은 CAPTCHA와 무관한 별개의 타이밍 이슈로 보이며(캡처 자체가 실패한 것이지 데이터가 없었다는 뜻은 아님, PoC-2R에서는 동일 지점에서 70건을 확보한 바 있음), 대기 시간(4초)이 이번 세션 조건에서는 다소 짧았을 가능성이 있다.

## 결과 요약
- page=1 raw/dedup: 20 / 20
- page=2 raw/dedup: 0 / 0(클릭 성공, 실제 리스트 응답 캡처 실패 - 무관 응답 1건만 포착)
- page=3 raw/dedup: 0 / 0(클릭이 CAPTCHA에 의해 차단되어 도달 실패)
- 총 dedup: 20건
- active_captcha_detected: False / passive_captcha_marker_found: True / **click_intercepted_by_captcha: True** / status_429_seen: False
- response URL 패턴: `map.naver.com/p/api/search/allSearch?...`(page=1, 정상), `pcmap-api.place.naver.com/graphql`(status=405, 무관 요청)

## 100~160급 확장 가능성 판단
**아직 이르다.** 이번 실행은 page=2 실데이터 재현조차 못했고 page=3에서 실제 CAPTCHA로 막혔다. PoC-2R(90건 성공)과 PoC-3(20건, page=3에서 실차단) 사이의 **실행 간 결과 변동성 자체가 중요한 신호**다 - 즉 안전 마진이 실행마다 달라질 수 있다는 뜻이므로, 100~160개처럼 더 많은 페이지 전환을 요구하는 규모로 바로 확장하는 것은 리스크가 크다. 300개는 물론 100개 수준도 이번 근거만으로는 뒷받침되지 않는다.

## 다음 작업
- 규모 확장(50/100/160/300)으로 진행하지 않는다.
- 다음 단계 후보: (a) page=2 대기시간을 4초보다 늘려 재관찰(같은 page=2 지점의 데이터 캡처 안정성 확인), (b) 동일 조건(page=1→2→3)으로 시간 간격을 두고 1회 더 재현성 확인, (c) CAPTCHA가 발생하는 지점(page 2→3)이 매번 동일한지, 아니면 세션/시간대에 따라 변하는지 별도 관찰.
- 여전히 UI/pipeline 미연결, LEGAL_NOTICE/README 정식 수정 없음, CAPTCHA 우회 시도 없음.


# 2026-07-09 ARCH-300C PoC-4 동 단위 검색어 분할 실험 기록 (기술 검증, 제품 기능 아님)

## 배경
PoC-3에서 단일 검색어의 깊은 page 전환(page=2→3)이 실제 CAPTCHA를 유발함이 확인되어,
"한 검색어를 깊게 파는" 방식은 300개 메인 엔진으로 부적합하다고 판단했다(Opus Plan Mode,
ARCH-300C 설계). 대안으로 "여러 동 검색어를 얕게(page=1만) 조회해 place_id 기준으로
합산"하는 구조의 1차 기술 검증을 PoC-4로 진행했다. 아직 제품 기능 확정이 아니며,
UI/pipeline에는 연결하지 않았다. LEGAL_NOTICE/README 정식 수정도 보류(제품 배선 결정
시점으로 미룸).

## 구현
- `src/pc/region_expander.py` 신규 — `build_dong_queries(city, gu, dongs, keywords)`: 구 단위 검색어를 동 단위 검색어 목록(동 × 키워드 곱)으로 분할하는 순수 함수. 직접 API 호출 없음, 공백/중복/빈 입력 방어. `tests/test_pc_region_expander.py` 신규(6 PASS / FAIL 0).
- `src/pc/network_list_scraper.py` 보정: `_map_item_to_row`에 `source_dong`/`source_query` 선택적 내부 메타 추가(기존 `source_page`와 동일한 하위 호환 패턴, Excel 11컬럼에는 미노출). `count_rows_by_field(rows, field)` 신규 — `count_rows_by_source_page`의 일반화 버전(동/쿼리 등 임의 필드로 집계). `tests/test_pc_network_list_scraper.py`에 4종 추가(총 33 PASS / FAIL 0).
- `scratchpad/arch300_network_probe/poc4_dong_split_probe.py` 신규 — 강동구 동 5개(천호동/성내동/길동/암사동/명일동) × "카페" × **page=1만**(pagination 클릭 없음, 상세 카드 클릭 없음, entryIframe 없음) 순회. `browser_session._CAPTCHA_PROBE_SELECTORS`/`region_expander.build_dong_queries`를 읽기 전용으로만 재사용, 나머지 보호 파일은 전부 무수정.

## PoC-4 live 실행 결과 (1회, 재시도 없음)
- 대상: 서울특별시 강동구 {천호동, 성내동, 길동, 암사동, 명일동} × "카페", 각 page=1만.
- **동별 결과(5개 전부 완주, 중단 없음)**:

| 동 | candidate | raw | unique_added | duplicate | elapsed(s) | passive | active |
|---|---|---|---|---|---|---|---|
| 천호동 | 1 | 20 | 20 | 0 | 5.839 | True | False |
| 성내동 | 1 | 20 | 20 | 0 | 5.204 | True | False |
| 길동 | 1 | 20 | 20 | 0 | 5.215 | True | False |
| 암사동 | 1 | 20 | 20 | 0 | 5.181 | True | False |
| 명일동 | 1 | 20 | 20 | 0 | 5.196 | True | False |

- **총 unique row 수: 100건**(5동 × 20건, 전 동에 걸쳐 place_id 중복 0건 — 별도 검증 스크립트로 `len(set(place_ids))==100` 확인).
- **중복률: 0.0%**(duplicate_rate=0.0). Gemini/Antigravity의 사전 실측 주장(동 5개, 총 100건, 중복률 0%)과 **정확히 일치**.
- `total_wall_seconds=33.514`, `rows_per_second≈2.98`, `seconds_per_unique_row≈0.335`, `query_count=5`, `avg_rows_per_query=20.0`.
- `active_captcha_detected=False`(5동 전부), `passive_captcha_marker_found=True`(5동 전부, 기존과 동일하게 상시 존재 placeholder), `click_intercepted_by_captcha=False`(이번 PoC-4는 pagination 클릭을 구조적으로 하지 않으므로 항상 False), `status_429_seen=False`.
- `stop_reason=None`(끝까지 정상 완주).

## 판단
- **동 단위 얕은 조회(page=1만) 5개 연속 실행에서 CAPTCHA/429가 전혀 발생하지 않았다.** PoC-3(단일 검색어 deep pagination, page=3에서 실제 차단)와 뚜렷이 대조된다.
- 동 간 중복이 이번 5개 표본에서는 0%였다 — 다만 동이 늘어날수록(특히 인접 동/좁은 상권) 중복률이 상승할 가능성은 배제할 수 없다(표본 5개, 1회 실행 결과일 뿐).
- **PoC-4 기준 300개 추정**: 이번 비율(동 1개당 약 20건, 중복 0%)이 그대로 유지된다고 "낙관적으로 가정"하면 약 15개 동이 필요하다는 계산이 나오지만, 이는 **검증된 결론이 아니라 단순 외삽**이다. 실제로는 (a) 동 수가 늘수록 중복률 상승 가능성, (b) 더 많은 동을 연속 조회할 때의 CAPTCHA 리스크 누적 가능성이 모두 미검증 상태다. **300개 가능 여부는 여전히 확정하지 않는다.**

## 다음 작업
- 더 많은 동(예: 강동구 전체 동, 10개 이상)으로 확장해 (a) 중복률 추세, (b) CAPTCHA/429 누적 리스크를 관찰하는 PoC-5 후보.
- 정적 동 목록 데이터 자산화(현재는 5개 하드코딩)는 이 방향이 채택된 이후 별도 태스크로 분리.
- 여전히 UI/pipeline 미연결, LEGAL_NOTICE/README 정식 수정 없음(제품 배선 결정 시점으로 계속 보류), CAPTCHA 우회 시도 없음.


# 2026-07-09 ARCH-300C PoC-5 동 단위 10~15개 확장 실험 기록 (기술 검증, 제품 기능 아님)

## 배경
PoC-4(동 5개, 100건, 중복 0%, CAPTCHA/429 없음)에 이어 동 개수를 15개로 확장해
300개 근접 가능성·중복률 추세·CAPTCHA/429 누적 리스크·속도를 관찰했다. 이번 동
목록은 의도적으로 법정동/행정동을 혼합했다(예: "성내동"과 "성내제1/2/3동",
"천호동"과 "천호제1/2/3동"은 실제로 같은/겹치는 지역을 가리킬 수 있음) - place_id
dedup이 이런 중복까지 실제로 흡수하는지 확인하기 위함이었다. 여전히 제품 기능
확정이 아니며 UI/pipeline 미연결, page=1만(page=2 이상 클릭 없음).

## 구현
- `scratchpad/arch300_network_probe/poc5_dong_split_scale_probe.py` 신규 — PoC-4 구조를 그대로 재사용, 동 목록만 15개로 확장. `region_expander`/`network_list_scraper`/`browser_session._CAPTCHA_PROBE_SELECTORS`는 무수정, 읽기 전용 재사용만. 이번 단계는 신규 유틸이 필요 없어 `region_expander.py`/`network_list_scraper.py`/관련 테스트는 무변경.

## PoC-5 live 실행 결과 (1회, 재시도 없음)
- 대상: 서울특별시 강동구 15개 동 × "카페", 각 page=1만. **15개 전부 완주, 중단 없음.**
- **동별 결과**:

| 동 | raw | unique_added | duplicate | elapsed(s) |
|---|---|---|---|---|
| 천호동 | 20 | 20 | 0 | 5.884 |
| 성내동 | 20 | 20 | 0 | 5.252 |
| 길동 | 20 | 20 | 0 | 5.235 |
| 암사동 | 20 | 20 | 0 | 5.223 |
| 명일동 | 20 | 20 | 0 | 5.204 |
| 고덕동 | 20 | 20 | 0 | 5.213 |
| 상일동 | 20 | 20 | 0 | 5.211 |
| 둔촌동 | 20 | 20 | 0 | 5.204 |
| 강일동 | 20 | 20 | 0 | 5.210 |
| 성내제1동 | 20 | **0** | 20 | 5.195 |
| 성내제2동 | 20 | **0** | 20 | 5.232 |
| 성내제3동 | 20 | **0** | 20 | 5.289 |
| 천호제1동 | 26 | **6** | 20 | 5.200 |
| 천호제2동 | 26 | **0** | 26 | 5.198 |
| 천호제3동 | 26 | **0** | 26 | 5.203 |

- **총 raw 318건 / 총 unique 186건 / 총 duplicate 132건 / 중복률 41.51%**(별도 검증: `place_id` 186개 전부 서로 다름 - dedup 자체는 완벽하게 정확).
- `total_wall_seconds=100.988`, `rows_per_second≈1.84`, `seconds_per_unique_row≈0.543`, `query_count=15`, `avg_rows_per_query=12.4`.
- `active_captcha_detected=False`(15개 전부), `passive_captcha_marker_found=True`(전부, 기존과 동일 상시 placeholder), `click_intercepted_by_captcha=False`(구조적으로 클릭 없음), `status_429_seen=False`. `stop_reason=None`(끝까지 정상 완주).

## 판단 — 법정동/행정동 혼합이 실측으로 확인한 핵심 리스크
- **"천호동"/"성내동"(법정동 성격) 뒤에 이어진 "천호제1~3동"/"성내제1~3동"(같은 지역의 행정동 세분류)은 거의 전량 중복이었다.** 성내제1/2/3동은 raw=20인데도 unique_added=0(이미 성내동에서 다 잡힘). 천호제1동만 6건 신규(더 넓은/다른 반경으로 잡힌 소수), 천호제2/3동은 다시 0건 신규.
- 순수 신규 기여만 놓고 보면 **앞 9개 동(천호~강일동)이 180건 + 천호제1동의 6건 = 186건**으로, 실제 `total_unique_rows=186`과 정확히 일치한다. 즉 **뒤쪽 6개 동(성내제1~3, 천호제2~3)은 사실상 낭비 쿼리**였다(신규 기여 거의 0, 쿼리/시간만 소모).
- **CAPTCHA/429는 15개 연속 조회에서도 전혀 발생하지 않았다** - 이는 PoC-4에 이어 재확인된 긍정적 신호다.
- **dedup 메커니즘 자체는 완전히 정확했다**(186개 unique place_id, 오류 0건) - 문제는 dedup이 아니라 **동 목록 큐레이션(법정동/행정동 정리)**에 있음이 이번 실측으로 명확해졌다.

## 결과 요약
- total unique row 수: **186건**(15개 동, 318 raw 중)
- 중복률: **41.51%**(법정동/행정동 혼합에 기인, dedup 자체는 정상 동작)
- 속도: `total_wall_seconds=100.988`, `rows_per_second≈1.84`
- CAPTCHA/429: 전혀 발생하지 않음(15개 연속 조회에서도 안전)

## 300개 목표에 대한 현재 추정(확정 아님)
- 이번 실행 기준으로는 **"정리되지 않은 동 목록"으로는 300개에 크게 못 미친다**(186건). 다만 이는 동 개수의 한계가 아니라 **목록 품질(법정동/행정동 중복)의 한계**로 보인다.
- **낙관적 추정**: 낭비 없는(법정동/행정동 정리된) "깨끗한" 동 9~10개가 각 20건씩 신규로 기여한 이번 패턴이 유지된다면, 약 15개의 **정리된** 동으로 300건 근접이 가능할 것으로 추정된다. 그러나 이는 여전히 **PoC-4·PoC-5의 제한된 표본(강동구 일부 동)에 대한 외삽일 뿐**이며, 확정된 결론이 아니다.
- 미검증 요소: (a) 강동구 전체·다른 구에서도 동일 패턴(동 1개당 ~20건, 저중복)이 유지되는지, (b) 정리된 동 목록으로 15개 이상 연속 조회 시 CAPTCHA/429 누적 리스크, (c) 행정동/법정동을 사전에 걸러내는 실제 데이터 소스 확보.

## 다음 작업
- 동 목록을 법정동 또는 행정동 **한쪽으로만** 통일해 재실험(다음 PoC 후보) - 이번 실험이 시사하는 가장 직접적인 개선점.
- 정적 동 목록 데이터 자산화(법정동/행정동 정리 포함)는 별도 태스크로 분리, 이번 PoC 결과가 그 필요성을 실측으로 뒷받침함.
- 여전히 UI/pipeline 미연결, LEGAL_NOTICE/README 정식 수정 없음(제품 배선 결정 시점으로 계속 보류), CAPTCHA 우회 시도 없음.
- release_candidate 생성은 위 리스크 검토 완료 전까지 보류.

# 2026-07-09 ARCH-300C PoC-6 계층형 검색어(Tier1/2/3) 신규 기여량 실험 기록 (기술 검증, 제품 기능 아님)

## 배경
PoC-5에서 법정동/행정동 혼합이 중복 폭증(41.51%)의 원인임이 확인됨에 따라
(REGION-DATA-1 설계, Opus Plan Mode), 기본 큐를 법정동만으로 정리하고
(Tier1), 300개 목표에 부족한 부분을 채울 확장 레이어 두 가지 -
Tier3(같은 법정동을 세부업종으로 재조회), Tier2(역/상권명 확장) - 가 실제로
유의미한 신규 기여를 만드는지 검증했다. 이번 PoC-6는 "300개 완성 실험"이
아니라 **Tier별 신규 기여량 측정 실험**이다. 여전히 제품 기능 확정이 아니며
UI/pipeline 미연결, page=1만(page=2 이상 클릭 없음).

## 구현
- `data/regions_kr_sample.json` 신규 — 강동구 샘플만 포함(법정동 9개/역상권 6개/세부업종 3개), 런타임 API 호출 없음. 전국 데이터 자산화는 이번 범위 아님.
- `src/pc/region_expander.py` 확장 — 기존 `build_dong_queries`(Tier1)는 하위 호환 유지. `build_landmark_queries`(Tier2: 역/상권×업종), `build_subcategory_queries`(Tier3: 법정동×세부업종), `build_tiered_query_queue`(Tier를 순서대로 조합 + tier/source_layer 태깅) 신규 추가. 전부 순수 함수, 직접 API 호출 없음, 공백/중복/빈 입력 방어.
- `src/pc/network_list_scraper.py`에 `classify_query_efficiency`(efficiency_ratio, low_efficiency 판정), `should_stop_for_target`(target 도달 판정) 순수 헬퍼 추가. 이번 PoC-6에서는 둘 다 **기록/관찰용으로만** 쓰고 자동 중단/스킵에는 사용하지 않음(실제 정책 적용은 PoC-7 이후).
- `src/pc/region_data.py` 신규(선택 구현) — `data/regions_kr_sample.json`을 읽는 얇은 로더. 파일 없으면 `FileNotFoundError` 그대로 전파, city/gu 미존재 시 빈 레이어 반환.
- `tests/test_pc_region_expander.py`(+7), `tests/test_pc_network_list_scraper.py`(+6), `tests/test_pc_region_data.py`(신규 3) — 전부 PASS, 기존 39개 회귀 0.
- `scratchpad/arch300_network_probe/poc6_tiered_probe.py` 신규 — PoC-5 구조 재사용, `build_tiered_query_queue`로 Tier1→Tier3→Tier2 순서(총 24개 쿼리) page=1만 수집. `browser_session._CAPTCHA_PROBE_SELECTORS`는 무수정 읽기 전용 재사용.

## PoC-6 live 실행 결과 (1회, 재시도 없음)
- 대상: 서울특별시 강동구, Tier1(법정동 9개×카페) → Tier3(천호동/성내동/길동×디저트카페/브런치카페/베이커리카페) → Tier2(역/상권 6개×카페). **24개 전부 완주, 중단 없음.**

**Tier1 — 법정동 baseline (9건)**

| 동 | raw | unique_added | duplicate | efficiency_ratio |
|---|---|---|---|---|
| 천호동 | 20 | 20 | 0 | 1.0 |
| 성내동 | 20 | 20 | 0 | 1.0 |
| 길동 | 20 | 20 | 0 | 1.0 |
| 암사동 | 20 | 20 | 0 | 1.0 |
| 명일동 | 20 | 20 | 0 | 1.0 |
| 고덕동 | 20 | 20 | 0 | 1.0 |
| 상일동 | 20 | 20 | 0 | 1.0 |
| 둔촌동 | 20 | 20 | 0 | 1.0 |
| 강일동 | 20 | 20 | 0 | 1.0 |

**Tier3 — 세부업종 확장 (9건, 천호동/성내동/길동 × 디저트카페/브런치카페/베이커리카페)**

| 쿼리 | raw | unique_added | duplicate | efficiency_ratio |
|---|---|---|---|---|
| 천호동 디저트카페 | 20 | 15 | 5 | 0.75 |
| 천호동 브런치카페 | 20 | 11 | 9 | 0.55 |
| 천호동 베이커리카페 | 20 | 12 | 8 | 0.60 |
| 성내동 디저트카페 | 20 | 10 | 10 | 0.50 |
| 성내동 브런치카페 | 20 | 6 | 14 | 0.30 |
| 성내동 베이커리카페 | 20 | 10 | 10 | 0.50 |
| 길동 디저트카페 | 20 | 9 | 11 | 0.45 |
| 길동 브런치카페 | 20 | 3 | 17 | 0.15 |
| 길동 베이커리카페 | 20 | 10 | 10 | 0.50 |

**Tier2 — 역/상권 확장 (6건)**

| 쿼리 | raw | unique_added | duplicate | efficiency_ratio | 누적 unique |
|---|---|---|---|---|---|
| 천호역 카페 | 20 | 16 | 4 | 0.80 | 282 |
| 강동역 카페 | 20 | 12 | 8 | 0.60 | 294 |
| 둔촌동역 카페 | 20 | 17 | 3 | 0.85 | **311(300 초과)** |
| 암사역 카페 | 26 | 21 | 5 | 0.8077 | 332 |
| 고덕역 카페 | 26 | 18 | 8 | 0.6923 | 350 |
| 명일역 카페 | 20 | 17 | 3 | 0.85 | 367 |

**Tier별 요약**: Tier1 raw=180/unique=180/dup=0/dup률=0%/avg_efficiency=1.0. Tier3 raw=180/unique=86/dup=94/dup률=52.22%/avg_efficiency=0.4778. Tier2 raw=132/unique=101/dup=31/dup률=23.48%/avg_efficiency=0.7667.

**전체 요약**: `total_raw_items=492`, `total_unique_rows=367`, `total_duplicate_count=125`, `duplicate_rate=25.41%`, `total_wall_seconds=161.046`, `rows_per_second≈2.28`, `seconds_per_unique_row≈0.439`, `query_count=24`, `avg_rows_per_query=15.29`. `active_captcha_detected=False`(24개 전부), `passive_captcha_marker_found=True`(전부, 기존과 동일 상시 placeholder), `click_intercepted_by_captcha=False`(구조적으로 클릭 없음), `status_429_seen=False`. `stop_reason=None`(끝까지 정상 완주).

## 판단 — Tier2/Tier3 확장 모두 유의미한 신규 기여, Tier2가 더 효율적
- **Tier1(법정동 baseline)만으로는 180건**(PoC-5와 동일 패턴 재확인: 동당 20건, 중복 0%).
- **Tier3(세부업종)는 180 raw에서 86건 신규 기여**(avg_efficiency≈0.48) - "저효율"은 아니지만 Tier2보다 중복률이 높다(52.22%). 같은 법정동을 다른 업종명으로 재조회하면 이미 잡힌 업체가 절반 이상 다시 걸린다는 뜻.
- **Tier2(역/상권)는 132 raw에서 101건 신규 기여**(avg_efficiency≈0.77) - 이번 실측에서 **Tier2가 Tier3보다 더 효율적**이었다(REGION-DATA-1 설계 문서의 "세부업종이 더 효율적일 것"이라는 가정과 반대 - 실측으로 뒤집힘, 정직하게 기록).
- **누적 unique가 Tier2의 3번째 쿼리(둔촌동역, 21번째 전체 쿼리)에서 311건으로 300을 넘어섰다** - 강동구 **단일 구, page=1만, 24개 쿼리**로 300 목표를 실제로 초과 달성.
- **24개 연속 page=1 조회에서도 CAPTCHA/429가 전혀 발생하지 않았다** - PoC-4/PoC-5에 이어 재확인된 긍정적 신호.
- 다만 `efficiency_ratio` 임계값(<0.15 또는 unique_added<3)에 걸린 쿼리는 없었다(가장 낮은 길동 브런치카페도 정확히 ratio=0.15, unique_added=3으로 경계값 자체에 걸침 - `low_efficiency=False`로 정상 처리됨, 헬퍼의 경계 조건이 실측 데이터로도 검증됨).

## 결과 요약
- total unique row 수: **367건**(24개 쿼리, 492 raw 중) - 300 목표 초과
- 중복률: **25.41%**(Tier1 0% / Tier3 52.22% / Tier2 23.48%)
- 속도: `total_wall_seconds=161.046`, `rows_per_second≈2.28`
- CAPTCHA/429: 전혀 발생하지 않음(24개 연속 조회에서도 안전)

## 300개 목표에 대한 현재 추정(확정 아님)
- 이번 실행 기준으로는 **강동구 단일 구 + Tier1/2/3 조합만으로 300개를 초과 달성했다(367건)**. 다만 이는 **1회 실행, 강동구 1개 구에 대한 표본**일 뿐이며, 다른 구/다른 업종 키워드에서도 동일 패턴(법정동 baseline 100% 신규, 역/상권 확장이 세부업종보다 효율적)이 재현되는지는 아직 검증되지 않았다.
- 미검증 요소: (a) 다른 구/업종에서도 Tier2가 Tier3보다 효율적인 패턴이 유지되는지, (b) target=300 도달 시 실제로 조기 중단하는 정책(`should_stop_for_target` 실사용)의 효과, (c) 24개보다 더 많은 연속 조회에서의 CAPTCHA/429 누적 리스크, (d) 세부업종/역상권 목록의 정적 데이터 자산화 범위(현재는 강동구 샘플만).

## 다음 작업
- PoC-7: `should_stop_for_target`을 실제로 큐 중단 조건에 적용해 target=300 조기 종료 동작을 검증(이번 PoC-6는 관찰만 하고 중단하지 않음).
- 다른 구(강동구 외)에서도 Tier2>Tier3 효율성 패턴이 재현되는지 추가 표본 확보.
- 정적 지역 데이터 자산화(전국 법정동/역상권, 공개 출처 기반)는 여전히 별도 태스크로 분리.
- 여전히 UI/pipeline 미연결, LEGAL_NOTICE/README 정식 수정 없음(제품 배선 결정 시점으로 계속 보류) - **300개 목표를 실제로 초과 달성한 이번 결과는 오히려 LEGAL_NOTICE 4항(대량 자동화 미포함)과의 재조정 필요성을 더 높인다.**
- CAPTCHA 우회 시도 없음, release_candidate 생성은 법적/운영 리스크 검토 완료 전까지 보류.

# 2026-07-09 ARCH-300C PoC-7 target=300 조기 종료 실험 기록 (기술 검증, 제품 기능 아님)

## 배경
PoC-6은 `should_stop_for_target`을 계산만 하고 큐를 끝까지(24개 쿼리) 실행했다.
PoC-7은 이 target_limit=300 조기 종료를 **실제 중단 조건으로 적용**해, 누적
unique row가 300 이상이 되는 즉시 남은 쿼리를 실행하지 않고 멈추는 제품형
흐름을 검증했다. 또한 PoC-6 실측(Tier2 역/상권 avg_efficiency=0.7667 > Tier3
세부업종 0.4778)을 반영해 **Tier 실행 순서를 Tier1→Tier2→Tier3로 변경**했다
(기존 PoC-6은 Tier1→Tier3→Tier2). 여전히 제품 기능 확정이 아니며 UI/pipeline
미연결, page=1만(page=2 이상 클릭 없음).

## 구현
- `scratchpad/arch300_network_probe/poc7_target_300_probe.py` 신규 — PoC-6 구조를 재사용하되, 매 쿼리 후 `should_stop_for_target(cumulative_unique_before_trim, 300)`을 실제 중단 조건으로 적용. 안전 중단(429/active CAPTCHA)이 target 도달보다 항상 우선한다. 최종 결과는 `all_unique_rows[:300]`으로 trim. `src/pc/region_expander.py`/`network_list_scraper.py`/`region_data.py`는 **무수정**(PoC-6에서 이미 만든 `build_tiered_query_queue`의 `enabled_tiers=("tier1","tier2","tier3")` 인자와 `should_stop_for_target`/`classify_query_efficiency`만으로 이번 실험 요구가 전부 충족됨).
- `tests/test_pc_region_expander.py`/`test_pc_network_list_scraper.py`/`test_pc_region_data.py` 무변경 - 사전 확인 결과 회귀 0(13/39/3 PASS 유지).

## PoC-7 live 실행 결과 (1회, 재시도 없음)
- 대상: 서울특별시 강동구, Tier1(법정동 9개×카페) → Tier2(역/상권 6개×카페) → Tier3(천호동/성내동/길동×세부업종). 총 24개 쿼리 중 **17개만 실행, target=300 도달로 정상 조기 종료**.

| 순번 | Tier | 쿼리 | raw | unique_added | 누적(trim 전) |
|---|---|---|---|---|---|
| 1~9 | tier1 | 강동구 법정동 9개×카페 | 각 20 | 각 20 | 20→180 |
| 10 | tier2 | 천호역 카페 | 20 | 17 | 197 |
| 11 | tier2 | 강동역 카페 | 20 | 18 | 215 |
| 12 | tier2 | 둔촌동역 카페 | 20 | 18 | 233 |
| 13 | tier2 | 암사역 카페 | 20 | 15 | 248 |
| 14 | tier2 | 고덕역 카페 | 20 | 18 | 266 |
| 15 | tier2 | 명일역 카페 | 20 | 17 | 283 |
| 16 | tier3 | 천호동 디저트카페 | 20 | 15 | 298 |
| 17 | tier3 | 천호동 브런치카페 | 20 | 11 | **309(300 도달, 중단)** |

- **target=300 도달 시점**: 17번째 쿼리("서울특별시 강동구 천호동 브런치카페", Tier3) 직후 누적 309에서 `should_stop_for_target=True` → 남은 7개 쿼리(길동/성내동 세부업종 잔여) 미실행.
- `executed_query_count=17`, `skipped_query_count=7`, `before_trim_unique_count=309`, `final_unique_count=300`(정확히 300으로 trim 확인).
- `total_raw_items=340`, `duplicate_count=31`, `duplicate_rate=9.12%`(PoC-6 24개 완주 시 25.41%보다 낮음 - Tier2를 먼저 실행하고 덜 실행해 고중복 Tier3 쿼리 상당수를 애초에 건너뛴 효과).
- `total_wall_seconds=115.22`, `rows_per_second≈2.60`, `seconds_per_unique_row≈0.384`(PoC-6의 161.046초/24쿼리보다 빠름 - 조기 종료로 쿼리 수 자체가 줄어든 효과).
- `active_captcha_detected=False`(17개 전부), `passive_captcha_marker_found=True`(전부, 기존과 동일 상시 placeholder), `click_intercepted_by_captcha=False`(구조적으로 클릭 없음), `status_429_seen=False`. `stop_reason="target_reached"`(안전 중단 아님, 정상적인 목표 도달 중단).

**Tier별 기여(trim 전/후)**:

| Tier | 실행 쿼리 수 | raw | unique(trim 전) | unique(trim 후) | dup률 | avg_efficiency |
|---|---|---|---|---|---|---|
| tier1(법정동) | 9 | 180 | 180 | 180 | 0% | 1.0 |
| tier2(역/상권) | 6 | 120 | 103 | 103 | 14.17% | 0.8583 |
| tier3(세부업종) | 2 | 40 | 26 | 17(마지막 쿼리 일부만 trim에 포함) | 35% | 0.65 |

## 판단 — Tier2 우선 실행이 실측으로 효과 확인됨
- **Tier 순서 변경이 실제로 효과가 있었다**: PoC-6(Tier1→Tier3→Tier2)은 300 도달에 21개 쿼리가 필요했지만, 이번(Tier1→Tier2→Tier3)은 **17개 쿼리**만으로 도달했다 - 4개 쿼리(약 17초 상당) 절약.
- **target=300 조기 종료가 의도대로 정확히 동작했다**: 남은 7개 쿼리를 실행하지 않고 즉시 멈췄고, 최종 결과도 정확히 300개로 trim됨(before_trim 309 → final 300).
- **trim 경계에 걸친 쿼리(17번째, 천호동 브런치카페)는 raw 20건 중 11건이 신규였지만, 그중 2건만 최종 300에 포함**되고 나머지 9건은 이미 306~309번째 슬롯이라 잘려나갔다 - trim이 쿼리 내부 항목까지 정교하게 자르는 것이 아니라 **"이미 확보한 row 리스트의 앞 300개"**를 취하는 방식이라, 마지막 쿼리에서 어떤 특정 업체가 실제로 최종본에 남는지는 응답 내 항목 순서에 좌우된다(우연적) - 이는 결과의 정확성 문제가 아니라, "정확히 300개"라는 요구를 만족시키는 자연스러운 trim 방식의 특성이다.
- **CAPTCHA/429는 17개 연속 조회에서도 전혀 발생하지 않았다** - PoC-4~6에 이어 재확인된 긍정적 신호.
- 중복률(9.12%)이 PoC-6 전체 실행(25.41%)보다 크게 낮아진 것은 데이터 자체가 좋아진 게 아니라 **고중복 구간(Tier3 후반)을 애초에 실행하지 않은 결과**이다 - target-stop이 "불필요한 저효율 쿼리 실행을 자동으로 줄이는" 부수 효과가 있음을 보여준다.

## 결과 요약
- target=300 도달 여부: **성공**(17번째 쿼리에서 누적 309로 도달, 조기 종료)
- 실행/스킵 쿼리 수: **17 실행 / 7 스킵**(총 24개 중)
- before_trim_unique_count / final_unique_count: **309 / 300**(정확히 trim됨)
- 속도: `total_wall_seconds=115.22`, `rows_per_second≈2.60`(PoC-6보다 빠름 - 쿼리 수 감소 효과)
- CAPTCHA/429: 전혀 발생하지 않음

## 300개 제품 흐름에 대한 현재 판단(강동구 카페 1회 실측 기준으로 제한)
- **강동구·"카페" 키워드·1회 실측 기준으로, target=300 조기 종료 흐름이 설계대로 정확히 동작함을 확인했다.** Tier2를 Tier3보다 먼저 실행하는 순서 변경도 실측으로 효과가 검증됨(21개→17개 쿼리로 단축).
- 이 결과를 다른 구/다른 업종/다른 실행 시점까지 일반화할 수 있는지는 **여전히 미검증**이다(1회, 1개 구, 1개 키워드 표본의 한계). 특히 (a) 강동구가 아닌 구에서도 법정동 9개 baseline이 유지되는지, (b) 다른 업종 키워드에서도 Tier2>Tier3 우선순위가 유지되는지, (c) target 도달 지점이 매번 비슷한 쿼리 수(17개 안팎)에서 일어나는지는 추가 표본이 필요하다.
- **300개를 실제로, 정확히, 조기 종료로 달성하는 흐름이 기술적으로 검증되었다는 사실은 제품화 결정 시 LEGAL_NOTICE 4항(대량 자동화 미포함) 재조정의 필요성을 다시 한 번 뒷받침한다** - 기술 검증과 제품 배선 승인은 여전히 별개다.

## 다음 작업
- 다른 구(강동구 외)·다른 업종 키워드로 표본을 늘려 Tier 우선순위/target 도달 쿼리 수 패턴이 재현되는지 확인.
- target-stop이 저효율 쿼리를 자동으로 건너뛰는 부수 효과를 `low_efficiency` 기반 스킵 정책(REGION-DATA-1 설계 §6 소프트 적응)과 결합할지 여부는 별도 실험으로 판단.
- 정적 지역 데이터 자산화(전국 법정동/역상권, 공개 출처 기반)는 여전히 별도 태스크로 분리.
- 여전히 UI/pipeline 미연결, LEGAL_NOTICE/README 정식 수정 없음(제품 배선 결정 시점으로 계속 보류).
- CAPTCHA 우회 시도 없음, release_candidate 생성은 법적/운영 리스크 검토 완료 전까지 보류.

# 2026-07-09 ARCH-300C PoC-8 업종 재현성 실험 기록 (기술 검증, 제품 기능 아님)

## 배경
PoC-7의 강동구 "카페" target=300 조기 종료 성공(17개 쿼리 실행, 300 도달)을
"카페"라는 단일 업종에 일반화하지 않기 위해, 같은 강동구 지역 레이어(법정동
9개/역상권 6개, Tier1→Tier2→Tier3 순서)를 그대로 두고 **업종 키워드만
"음식점"/"미용실"로 바꿔** 재현성을 확인했다. Tier3 세부업종은 카페 전용
(디저트카페 등) 대신 음식점=한식/중식/일식, 미용실=남성미용실/여성미용실/
헤어샵을 사용했다(둘 다 자연스러운 한국어 검색어로 판단되어 생략하지 않음).
`src/pc/region_expander.py`/`network_list_scraper.py`/`region_data.py`/
테스트는 이번에도 **무수정**(PoC-6/7의 기존 함수만 재사용). 각 업종 live는
1회만 실행, 재시도 없음.

## 구현
- `scratchpad/arch300_network_probe/poc8_keyword_repro_probe.py` 신규 — PoC-7 구조를 키워드별 설정(KEYWORD_CONFIGS: food=음식점/한식·중식·일식, hair=미용실/남성미용실·여성미용실·헤어샵)로 일반화. 명령줄 인자로 업종을 선택해 각각 별도 실행(`python poc8_keyword_repro_probe.py food`, `hair`).

## PoC-8 live 실행 결과 (업종별 1회, 재시도 없음)

### 음식점 — **active CAPTCHA로 4번째 쿼리에서 안전 중단**
- Tier1(법정동) 진행 중 4번째 쿼리("서울특별시 강동구 암사동 음식점")에서 `active_captcha_detected=True`(passive placeholder가 아니라 실제 가시성+유의미한 크기가 확인된 신호) 발생 → **즉시 안전 중단, 우회 시도 없음**.
- `executed_query_count=4`, `skipped_query_count=20`, `before_trim_unique_count=80`, `final_unique_count=80`(target=300 미도달), `stop_reason=active_captcha`, `stopped_after_query_index=4`.
- `total_raw_items=80`, `duplicate_count=0`, `duplicate_rate=0%`(4개 쿼리 모두 신규, CAPTCHA 발생 전까지는 카페와 동일한 100% 신규 패턴).
- `total_wall_seconds=27.328`, `rows_per_second≈2.93`.
- Tier1만: raw=80/unique=80/dup=0/avg_efficiency=1.0(중단 전까지는 정상 패턴).
- `passive_captcha_marker_found=True`, `status_429_seen=False`.

### 미용실 — **24개 쿼리 전부 완주, target=300 근접 미달(290건)**
- CAPTCHA/429 전혀 발생하지 않고 큐 소진까지 정상 진행.
- `executed_query_count=24`, `skipped_query_count=0`, `before_trim_unique_count=290`, `final_unique_count=290`(target=300 미도달), `stop_reason=queue_exhausted`.
- `total_raw_items=448`, `duplicate_count=158`, `duplicate_rate=35.27%`(카페 PoC-7의 9.12%보다 훨씬 높음).
- `total_wall_seconds=161.092`, `rows_per_second≈1.80`.
- **Tier별**: tier1(법정동) raw=180/unique=180/dup=0%/avg_efficiency=1.0(카페와 동일하게 완벽). tier2(역/상권) raw=109/unique=50/dup=54.13%/avg_efficiency=0.462(카페의 0.8583보다 크게 낮음). tier3(세부업종) raw=159/unique=60/dup=62.26%/avg_efficiency=0.3519 - 특히 "헤어샵"(천호동/성내동/길동 전부 unique_added=0)과 "여성미용실"(성내동/길동 unique_added=0)은 이미 확보한 "미용실"/"남성미용실" 결과와 거의 완전히 겹쳐 **사실상 낭비 쿼리**였다.
- `active_captcha_detected=False`, `passive_captcha_marker_found=True`, `status_429_seen=False`.

## 카페(PoC-7) 대비 비교

| 업종 | target=300 도달 | 실행/스킵 | before_trim | final | dup률 | CAPTCHA | 소요시간 |
|---|---|---|---|---|---|---|---|
| 카페(PoC-7) | **성공**(17번째 쿼리) | 17/7 | 309 | 300 | 9.12% | 없음 | 115.22s |
| 음식점 | 실패(안전 중단) | 4/20 | 80 | 80 | 0%(중단 전까지) | **active 발생(4번째 쿼리)** | 27.33s |
| 미용실 | 실패(큐 소진, 10건 부족) | 24/0 | 290 | 290 | 35.27% | 없음 | 161.09s |

## 판단 — "카페" 1회 성공이 다른 업종에 그대로 일반화되지 않음이 실측으로 확인됨
- **음식점은 카페보다 훨씬 어렵다(위험하다)**: 동일한 지역 레이어, 동일한 Tier 순서인데도 **4번째 법정동 쿼리에서 실제 active CAPTCHA가 발생**했다. Tier1의 앞 3개 쿼리(천호동/성내동/길동)는 카페와 동일하게 raw=20/unique=20/dup=0의 완벽한 패턴이었으나, 4번째(암사동)에서 신호가 바뀌었다 - 이는 PoC-2/PoC-3에서 확인된 "오탐 아닌 실제 신호" 판정 기준(가시성+유의미한 크기)을 그대로 만족했으므로 오탐이 아니라 **실제 CAPTCHA 트리거**로 판단한다. 다만 원인은 아직 불명확하다(업종 키워드 자체의 검색량/트래픽 특성 때문인지, 단순히 이번 실행 시점의 우연인지는 1회 표본으로는 구분 불가).
- **미용실은 카페보다 쉽지 않다(target 미달)**: CAPTCHA/429는 없었지만 세부업종(Tier3) 확장의 절반가량이 사실상 중복(헤어샵/여성미용실 다수가 unique_added=0)이라 300에 10건 못 미친 290건에서 큐가 소진됐다. Tier1(법정동)은 업종과 무관하게 항상 100% 신규(180건)로 안정적이었지만, Tier2/3(역상권/세부업종) 확장 효율은 업종별로 크게 다르다는 것이 이번 실측의 핵심 발견이다.
- **공통적으로 확인된 것**: Tier1(법정동 baseline)은 카페/음식점(중단 전까지)/미용실 전부에서 raw=20/unique=20/dup=0%로 동일하게 완벽했다 - 법정동 기반 baseline 자체는 업종과 무관하게 안정적인 것으로 보인다(1회 표본 기준). 반면 확장 레이어(Tier2/3)의 효율과, 심지어 CAPTCHA 발생 여부까지도 업종별로 다르다.

## 300개 제품 흐름에 대한 현재 판단(강동구 표본 기준으로 제한)
- **강동구 표본 1회 실측 기준으로, target=300 조기 종료 흐름은 "카페"에서는 성공했지만 "음식점"에서는 실제 CAPTCHA로 안전 중단됐고 "미용실"에서는 300에 못 미쳤다(290건).** "임의의 업종에서 항상 300을 안전하게 달성한다"는 주장은 이번 실측으로 명백히 성립하지 않는다.
- 특히 음식점에서의 active CAPTCHA 발생은, **업종/키워드에 따라 CAPTCHA 트리거 빈도가 달라질 수 있다는 새로운 리스크 신호**다. "카페 24개 연속 안전"이라는 이전 PoC-4~7의 결과를 다른 업종에도 안전하다고 확대 해석해서는 안 된다.
- 이는 제품화 판단에 있어 LEGAL_NOTICE 4항(대량 자동화 미포함) 재조정 필요성뿐 아니라, **업종별 안전성 편차를 감안한 추가 실측(더 많은 업종·더 많은 반복)이 필요하다**는 점을 함께 시사한다.

## 다음 작업
- 음식점 CAPTCHA 발생이 업종 특성 때문인지 우연인지 확인하기 위한 추가 반복 실측(다른 시점/다른 구)은 신중히 검토 - 반복 실측 자체가 노출을 늘리는 트레이드오프가 있음을 인지.
- 미용실의 Tier3(헤어샵/여성미용실) 낭비 쿼리 패턴처럼, 업종별로 "효율적인 세부업종 후보"가 다를 수 있음 - `low_efficiency` 신호를 활용한 사전 필터링(REGION-DATA-1 설계 §6) 필요성이 이번 실측으로 더 명확해짐.
- 정적 지역 데이터 자산화, UI/pipeline 연결, LEGAL_NOTICE/README 정식 수정은 여전히 별도 태스크로 보류(제품 배선 결정 시점까지).
- CAPTCHA 우회 시도 없음, release_candidate 생성은 법적/운영 리스크 검토(이번 업종별 편차 포함) 완료 전까지 보류.

# 2026-07-09 ARCH-300C PoC-9A 음식점 세부업종(한식) 분해 전략 검증 기록 (기술 검증, 제품 기능 아님)

## 배경
PoC-8에서 "음식점"(umbrella 키워드)을 직접 질의했을 때 4번째 쿼리(암사동)에서
active CAPTCHA가 발생했다. Opus REGION-DATA-1 재설계(§4)는 "umbrella 키워드를
직접 질의하지 않고 한식/중식/일식 등 정의형 세부업종으로 분해하면 안전성이
개선될 수 있다"는 가설(H3)을 제시했다. 이 PoC-9A는 **"음식점"을 절대
검색하지 않고** "한식"이라는 세부업종 하나만으로 이 분해 전략의 유효성을
최소 노출로 검증했다. `src/pc/region_expander.py`/`network_list_scraper.py`/
`region_data.py`는 이번에도 무수정.

## 구현
- `data/verticals_kr.json` 신규 — 카페(defined)/음식점(umbrella, strategy=split_to_subverticals)/한식(defined, parent_keyword=음식점)/미용실(niche) 4개 항목.
- `src/pc/vertical_presets.py` 신규(선택 구현) — `load_vertical_presets(path)`, `get_vertical_preset(presets, keyword)` 순수 로더. 파일 없으면 `FileNotFoundError` 전파, 미존재 키워드는 `None` 반환.
- `tests/test_pc_vertical_presets.py` 신규 — 6건 PASS(전체 항목 로드, defined/umbrella 조회, 미존재 키워드, non-dict 방어, 파일 없음 예외).
- `scratchpad/arch300_network_probe/poc9_food_subvertical_probe.py` 신규 — PoC-7/8 구조 재사용. `verticals_kr.json`에서 "한식"의 `parent_keyword=="음식점"`을 읽기 전용으로 확인만 하고, 생성된 쿼리 문자열에 "음식점"이 섞이지 않았는지 방어적으로 재확인(assert + 런타임 체크) 후 실행.
- 기존 테스트(region_expander/network_list_scraper/region_data) 무변경, 회귀 0(13/39/3 PASS 유지).

## PoC-9A live 실행 결과 (1회, 재시도 없음)

**"한식"도 4번째 쿼리(암사동)에서 active CAPTCHA로 안전 중단 — PoC-8 "음식점"과 정확히 동일한 위치·순번.**

- `executed_query_count=4`, `skipped_query_count=20`, `before_trim_unique_count=80`, `final_unique_count=80`(target=300 미도달), `stop_reason=active_captcha`, `stopped_after_query_index=4`, `stopped_after_query="서울특별시 강동구 암사동 한식"`.
- Tier1 앞 3개 쿼리(천호동/성내동/길동)는 raw=20/unique=20/dup=0의 완벽한 패턴(카페·음식점과 동일) - 4번째(암사동)에서 `active_captcha_detected=True`(가시성+유의미한 크기 확인, 오탐 아님).
- `total_raw_items=80`, `duplicate_count=0`, `duplicate_rate=0%`, `total_wall_seconds=26.987`, `rows_per_second≈2.96`.
- Tier2/Tier3는 실행되지 못함(안전 중단으로 스킵).
- `passive_captcha_marker_found=True`, `status_429_seen=False`.

## 카페(PoC-7) / 음식점 umbrella(PoC-8) 대비 비교

| 케이스 | target 도달 | 중단 지점 | before_trim | dup률(중단 전) | CAPTCHA |
|---|---|---|---|---|---|
| 카페(PoC-7) | 성공(17번째) | - | 309 | 9.12% | 없음 |
| 음식점 umbrella(PoC-8) | 실패 | **4번째, 암사동** | 80 | 0% | **active(4번째)** |
| 한식 분해(PoC-9A) | 실패 | **4번째, 암사동** | 80 | 0% | **active(4번째)** |

**"음식점"과 "한식"이 완전히 동일한 지점(4번째 쿼리, 암사동)에서 완전히 동일한 패턴(raw=80/unique=80/dup=0 후 active CAPTCHA)으로 중단됐다.**

## 판단 — "umbrella 키워드가 원인"이라는 가설(H3)이 이번 실측으로 반박됨
- **H3(umbrella 과폭 키워드가 CAPTCHA 원인) 기각**: "한식"은 명백한 정의형(defined) 세부업종인데도 umbrella였던 "음식점"과 정확히 동일한 위치에서 동일하게 실패했다. 분해 전략은 이번 1회 실측에서 **안전성을 개선하지 못했다.**
- **새로 부상하는 가설**: (a) **암사동 자체의 위치적 요인**(이 시점에 암사동 페이지 렌더링/응답이 특이했을 가능성), (b) **세션/시점 누적 요인(H4 확장판)** - 오늘 하루 동안 이미 PoC-6/7/8에서 강동구를 대상으로 다수의 연속 조회를 수행했으므로, 동일 IP/세션에 누적된 요청량이 임계치에 가까워졌고 그로 인해 이번 PoC-9A 4번째 쿼리에서 우연히 걸렸을 가능성. **카페(PoC-7)가 17개 연속 무사했던 것은 그날 초반 실행이었기 때문일 수 있고, 음식점/한식은 이미 여러 PoC가 누적된 이후 실행이었다는 시점 차이가 있다** - 이는 개별 PoC 로그만으로는 확정할 수 없는 교차 실행 누적 효과 가설이다.
- **암사동이라는 특정 동이 반복적으로 실패 지점이 된 것은 우연으로 치부하기엔 두 번 연속(PoC-8, PoC-9A) 재현됐다** - n=2로는 여전히 확정할 수 없지만, "특정 지역(암사동)이 다른 지역보다 민감하다"는 가설도 새로 세워야 한다.
- **분해 전략을 폐기하지는 않는다**: 세부업종 분해는 데이터 품질(업종 컬럼 명확성) 측면에서는 여전히 유효하지만, **"분해하면 CAPTCHA를 피할 수 있다"는 안전성 근거는 이번 실측으로 성립하지 않는다.**

## 300개 제품 흐름에 대한 현재 판단(강동구 한식 1회 실측 기준으로 제한)
- **강동구·"한식"·1회 실측 기준으로, umbrella 분해 전략은 target=300에 도달하지 못했고(80건), CAPTCHA 안전성도 개선되지 않았다.** "세부업종으로 쪼개면 안전해진다"는 이전 설계 가설은 기각됐다.
- 이 결과가 (a) 암사동이라는 특정 위치의 문제인지, (b) 오늘 하루 누적된 세션/IP 요청량 문제인지, (c) 단순 우연(n=2)인지는 **여전히 미확정**이며, 추가 실측 없이는 구분할 수 없다. 다만 추가 실측 자체가 노출을 늘리는 트레이드오프가 있으므로 신중한 판단이 필요하다.
- 제품화 판단에 있어 **"업종을 잘 나누면 안전 문제가 해결된다"는 낙관적 전제를 버려야 한다** - LEGAL_NOTICE 4항 재조정 필요성은 이번에도 그대로 유지/강화된다.

## 다음 작업
- 암사동 특이성 가설과 세션 누적 가설을 구분하려면 (a) 암사동을 제외한 순서로 재실험하거나 (b) 완전히 새로운 세션(다른 시점)에서 재실험이 필요 - 둘 다 노출을 늘리므로 사용자 승인 없이 진행하지 않는다.
- "분해하면 안전하다"는 가설이 기각됐으므로, 음식점형 전략(§4)의 안전 파라미터(세부업종 간 긴 휴지, 낮은 쿼리 상한, 즉시 전체 중단)는 여전히 유효하며 오히려 더 보수적으로 유지해야 한다.
- 정적 지역/업종 데이터 자산화, UI/pipeline 연결, LEGAL_NOTICE/README 정식 수정은 여전히 별도 태스크로 보류(제품 배선 결정 시점까지).
- CAPTCHA 우회 시도 없음, release_candidate 생성은 법적/운영 리스크 검토(이번 반박된 가설 포함) 완료 전까지 보류.

# 2026-07-09 UI-CLEANUP-1 DB 수집 UI 단순화 + 순위추적 V2 탭 추가

## 배경
V2.0 UI가 다중 키워드 큐, 빠른 수집/상세 수집 모드 선택, 온라인 채널 필터,
다중 지역 체크박스처럼 실제로는 쓰이지 않거나 안정성 근거가 약한 요소를
많이 담고 있었다(다중 키워드/다중 지역 곱집합 큐는 PoC-4~9가 실측한 CAPTCHA
누적 리스크와도 상충). 이번 작업은 **UI 정리**로, 화면을 [DB 수집] / [순위추적]
탭으로 분리하고 DB 수집 화면을 단일 지역·단일 키워드 중심으로 단순화했다.
순위추적 실제 알고리즘/크롤러/DB 스키마는 구현하지 않았고, 네이버 live 접속도
하지 않았다(요청 범위 그대로 준수).

## 변경 내용 (src/ui.py, 단일 파일)
- **탭 구조 추가**: `ctk.CTkTabview`로 [DB 수집]/[순위추적] 탭 분리, 기본 선택은 DB 수집. 기존 left_panel/right_panel은 DB 수집 탭 내부로 이동(그리드 구조 자체는 유지).
- **지역 선택 단순화**: 시/도·구 다중 체크박스(스크롤 프레임 2개 + 전체선택 버튼) 제거 → `CTkOptionMenu` 드롭다운 2개(시/도, 시/군/구)로 교체. `REGION_DATA` 딕셔너리는 그대로 재사용. 기본값은 서울특별시/강동구(세부구역 샘플 데이터가 있는 지역).
- **세부구역 설정 신규 추가**: "선택한 구를 동/상권 단위로 자동 세분화" 체크박스 + 요약 문구("법정동 9개 · 역/상권 6개 사용") + "자세히 보기" 토글(법정동/역상권 목록 텍스트만 표시, 개별 체크박스 편집 없음). `src/pc/region_data.load_region_layers`(PoC-6에서 만든 로더, 읽기 전용 재사용)로 `data/regions_kr_sample.json`을 읽는다. 데이터 없는 지역(강동구 외 전부)은 "이 지역의 세부구역 데이터는 아직 준비 중입니다" 문구로 처리. **이 섹션은 화면 표시용 미리보기이며, 실제 검색 쿼리 생성에는 아직 연결되지 않는다**(ARCH-300C 계층형 큐는 PoC 단계, 파이프라인 미연결 — 코드 주석으로 명시).
- **키워드 입력 단일화**: 추가 버튼/키워드 목록 박스/개별 삭제(X)/전체 삭제 버튼과 관련 상태(`self.keywords` 리스트, `add_keyword`/`remove_keyword`/`clear_keywords`/`_render_keyword_list`/Return 키 바인딩)를 전부 제거. 단일 `CTkEntry` + 안내 문구("현재 버전은 키워드 1개만 지원합니다.")만 남김.
- **다중 키워드 차단 validation**: `_MULTI_KEYWORD_PATTERN = re.compile(r"[,;\n]")`으로 쉼표/세미콜론/줄바꿈을 `start_crawl()` 진입 시점에 검사, 감지되면 수집을 시작하지 않고 "현재 버전은 키워드 1개만 지원합니다. 여러 키워드 수집은 안정성 문제로 제공하지 않습니다." 오류 메시지 표시.
- **필터 정리**: 온라인 채널(블로그/인스타 등) 존재 필터, 수집 모드 라디오(빠른 수집/상세 수집) 제거. 새로오픈 체크박스 아래에 동작 설명 문구 추가. 리뷰 수 범위 입력은 유지.
- **온라인 채널 필터 제거 vs 컬럼 유지**: 필터 UI만 제거했고, `exporter.MERGED_COLUMNS`(홈페이지/인스타/블로그 3컬럼)는 전혀 건드리지 않았다 — Excel 결과에는 그대로 남는다.
- **수집모드 UI 제거, 내부 기본값 premium 고정**: `basic_radio`/`premium_radio`/모드 라디오 프레임 삭제. `self.mode_var`는 항상 `"premium"`으로 고정, `output_path_var` 기본값도 premium 경로로 고정. `on_mode_change` 메서드는 더 이상 트리거될 UI가 없어 제거했지만, **`_collect_basic_query`/`_collect_premium_query_legacy`/`crawl_places`/`crawl_places_pc` 등 빠른 수집 엔진 코드는 전혀 삭제하지 않았다**(요청대로 UI 노출만 제거, 로직 보존).
- **목표 수집 개수 섹션 분리**: 기존 필터 안에 있던 "수집 개수" 입력을 별도 "5. 목표 수집 개수" 섹션으로 분리, 기본값을 10 → 300으로 변경, "중복 제거 후 최종 저장 개수 기준입니다. 업종/지역 규모에 따라 목표 개수에 못 미칠 수 있습니다." 설명 추가("무조건 300개 보장" 표현 없음).
- **수집 현황 문구 보완**: 기존 진행률/ETA/상태에 더해 "총 발견"/"중복 제거"/"최종 저장 예정" 3개 항목 추가. "총 발견"과 "최종 저장 예정"은 실제 파이프라인 집계값을 반영하도록 `_run_queue_pipeline`에 갱신 코드를 추가했다. **"중복 제거"는 현재 파이프라인이 쿼리 간 dedup을 추적하지 않아(ARCH-300C 계층형 큐 미연결) 항상 "0개"로 고정** — 근거 없는 숫자를 보여주지 않기 위한 정직한 placeholder임을 주석으로 명시.
- **보안 확인 안내 문구**: 기존 SAFE-1 안내 문구를 요청 문구("보안 확인이 감지되어 수집을 중단했습니다. 우회하지 않고 현재까지 수집된 결과를 저장합니다.")에 맞춰 정리(의미는 기존과 동일, 표현만 정리).
- **순위추적 탭 신규 추가**: "순위추적 V2 예정" 제목 + 설명 + 카드 3개(업체별 순위/키워드별 순위/날짜별 변화 기록, 각각 예시 텍스트 포함) + 비활성화된 "[순위추적 기능 준비중]" 버튼. **실제 검색/크롤러/DB 스키마/자동 스케줄링은 전혀 구현하지 않음**(정적 미리보기만).
- **주석**: 다중 키워드 제거 이유(CAPTCHA 누적 리스크), 수집모드 숨김 이유(엔진은 보존), 순위추적이 별도 탭/준비중인 이유(다른 알고리즘 필요), 세부구역 미리보기의 확장 지점(파이프라인 연결 시 교체할 지점), 온라인 채널 필터 제거와 컬럼 유지의 관계를 각 위치에 짧게 명시.

## 테스트 결과
- `python -m py_compile src/ui.py` PASS.
- `python -c "import src.ui"` PASS(모듈 임포트 성공, `REGIONS_SAMPLE_PATH.exists()`도 확인).
- 기존 UI 테스트 `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(premium/legacy/basic 경로, SAFE-1 콜백 — 이번 변경으로 로직을 건드리지 않은 부분이 실제로 무영향임을 재확인).
- 추가로 `_MULTI_KEYWORD_PATTERN` 5개 케이스(카페/미용실 허용, 쉼표·세미콜론·줄바꿈 차단) 직접 검증, `load_region_layers`로 강동구(법정동 9/역상권 6)와 강남구(0/0, 준비 중 문구 트리거) 조회 결과 확인 — 둘 다 기대대로 동작.
- live 실행/EXE/build/app.py 실행 없음(요청대로 미실행).

## 결과 요약
- DB 수집 화면: 시/도+구 드롭다운(단일 선택) → 세부구역 자동 세분화 미리보기(강동구만 실데이터, 그 외 준비 중) → 단일 키워드 입력(다중 입력 차단) → 필터(새로오픈만, 리뷰수 범위) → 목표 수집 개수(기본 300) → 수집 현황(총 발견/중복 제거/최종 저장 예정 포함) → [수집 시작/일시정지/중지/저장 폴더 열기].
- 순위추적 화면: 기능 없는 V2 예정 정적 화면(카드 3개 + 비활성 버튼).
- 빠른 수집 엔진/크롤러 로직/Excel 스키마는 전혀 변경하지 않음, UI 노출만 정리.

## 다음 작업
- 실제 UI 동작 확인(창 띄우고 지역/키워드/필터 조작)은 이번 요청 범위(live/실제 수집 금지)상 수행하지 않았음 — 사용자가 직접 실행해 육안 확인 필요.
- 세부구역 자동 세분화 미리보기를 실제 쿼리 생성(ARCH-300C `build_tiered_query_queue`)에 연결하는 것은 별도 배선 승인 이후 진행.
- "중복 제거" 수집 현황 항목을 실제 값으로 채우려면 파이프라인에 dedup 추적이 먼저 연결되어야 함.
- 순위추적 실제 알고리즘/DB 스키마/자동 스케줄링 구현은 DB 수집 MVP 안정화 이후 별도 단계.
- LEGAL_NOTICE/README 정식 수정은 여전히 제품 배선 결정 시점까지 보류.

# 2026-07-09 UI-CLEANUP-1B 세부구역 선택 UI 보완 + 화면 잘림 수정

## 배경
UI-CLEANUP-1 사용자 피드백: (1) 순위추적 탭 분리는 잘 됐음, (2) 세부구역
설정이 "자세히 보기"로 목록만 보여줄 뿐 실제 체크/해제가 안 됨 - 사용자는
수집할 동/상권을 직접 고를 수 있길 기대함, (3) 자세히 보기를 펼치면 왼쪽
패널 아래 "목표 수집 개수"가 화면 밖으로 잘림, (4) 검색순번 기록 제거 상태
유지, (5) 순위추적은 정보 부족하므로 현재 V2 예정 안내 수준 유지. 이번
작업은 (2)(3)을 보완하고 키워드 validation을 조금 더 강화했다. 순위추적
실제 기능/실제 수집/live 접속은 이번에도 하지 않았다.

## 변경 내용 (src/ui.py, 단일 파일)
- **세부구역: 미리보기 → 체크/해제 가능한 선택 UI**: "자세히 보기" 버튼을 "수집할 동/상권 선택 ▼"로 바꾸고, 펼치면 법정동/역상권 각각 체크박스 그리드(3열)로 표시한다. 기본값은 전체 체크. 하단에 [전체 선택]/[전체 해제] 버튼 추가. **행정동은 여전히 노출하지 않는다**(법정동 기준 baseline 원칙 유지 - PoC-5에서 확인된 행정동/법정동 혼합 중복 리스크 회피).
- **선택 상태 관리**: `self.region_selection_vars = {"legal_dongs": {이름: BooleanVar}, "landmarks": {이름: BooleanVar}}`로 유지. `_reload_subregion_data()`가 지역(시/도·구) 변경 시마다 `load_region_layers`로 다시 불러오고 **전체 선택으로 초기화**한다(체크박스가 화면에 그려져 있지 않아도 이 상태는 항상 최신 - 접힌 상태에서도 요약 문구/시작 검증이 정확해야 하므로). `get_selected_subregions()`가 현재 체크된 이름 목록을 반환하는 조회 함수(신규 public 메서드) - **아직 `_build_query_queue`/파이프라인에는 연결하지 않음**, 확장 지점으로 주석 명시.
- **요약 문구 동적 갱신**: `_update_subdivision_summary()`가 선택 개수 기준으로 "법정동 N개 · 역/상권 M개 선택됨" 또는 "선택된 세부구역이 없습니다."를 표시(체크박스 클릭/전체선택/전체해제 시 즉시 갱신).
- **0개 선택 시 시작 차단**: `start_crawl()`에서 자동 세분화가 켜져 있고 해당 지역에 데이터가 있는데 법정동/역상권을 전부 해제했으면 "수집할 동/상권이 선택되지 않았습니다. 최소 1개 이상의 세부구역을 선택해주세요." 오류로 차단.
- **화면 잘림 수정**: 왼쪽 `left_panel`을 `ctk.CTkFrame` → `ctk.CTkScrollableFrame`으로 교체해 왼쪽 설정 영역 전체가 세로 스크롤 가능하도록 함(오른쪽 수집 현황/로그 영역은 기존 `CTkFrame` 그대로 유지, 이중 스크롤 충돌 방지 위해 체크박스 영역 자체에는 별도 스크롤을 넣지 않음). 창 높이도 760 → 800으로 소폭 확대.
- **키워드 validation 보강**: `_MULTI_KEYWORD_PATTERN`에 `/`, `|`, `·`를 추가(`r"[,;\n/|·]"`). "카페 미용실"처럼 공백만 있는 입력은 여전히 차단하지 않음(하나의 실제 검색어일 수 있으므로). 검증 로직을 `_validate_single_keyword()` 헬퍼로 분리해 `start_crawl()`에서 재사용.
- **순위추적 탭**: 변경 없음(카드 3개 + 비활성 버튼 구조 그대로 유지, 실제 기능 미구현).
- **주석**: region_selection_vars가 "수집 큐 반영 확장 지점"이라는 점, 행정동을 노출하지 않는 이유(법정동 baseline 원칙), 다중 키워드 제거/차단 이유, 순위추적이 별도 탭/준비중인 이유, 빠른 수집 엔진 보존 이유를 각 위치에 짧게 명시.

## 테스트 결과
- `python -m py_compile src/ui.py` PASS.
- `python -c "import src.ui"` PASS, `get_selected_subregions`/`_validate_single_keyword`/`_reload_subregion_data` 메서드 존재 확인.
- 기존 `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(변경 부분과 무관함을 재확인).
- 다중 키워드 validation 8케이스 직접 검증: 카페(허용), 카페 미용실(공백만, 허용), 쉼표/세미콜론/슬래시/파이프/가운뎃점/줄바꿈(전부 차단) — 전부 기대대로 동작.
- `load_region_layers`로 강동구(법정동 9/역상권 6)·강남구(0/0, 준비 중 트리거) 재확인 — 이전과 동일하게 정상 동작(이 함수 자체는 이번에 수정하지 않음).
- **한계**: 체크박스 상태(region_selection_vars)는 `ctk.BooleanVar` 생성에 실제 Tk 루트가 필요해, live 실행 없이 인스턴스 생성까지 검증하지는 못했다(요청 범위상 실제 앱 실행/live 접속을 하지 않았기 때문). 코드 리뷰 수준으로 로직을 검증했으며, 실제 체크박스 동작/화면 잘림 해소 여부는 사용자가 직접 실행해 육안으로 확인이 필요하다.
- live 실행/EXE/build/app.py 실행 없음.

## 결과 요약
- 세부구역 설정이 읽기 전용 미리보기에서 체크/해제 가능한 선택 UI로 바뀌었고, 기본값은 전체 선택, 0개 선택 시 수집 시작이 차단된다.
- 왼쪽 설정 패널이 스크롤 가능해져 세부구역을 펼쳐도 "목표 수집 개수" 등 하단 요소에 접근 가능할 것으로 기대된다(실제 화면 확인은 사용자 몫).
- 다중 키워드 차단 패턴이 `,;/|·`+줄바꿈으로 확장됐고, 공백만 있는 입력은 계속 허용된다.
- 순위추적 탭은 이전 구조 그대로 유지, 실제 기능 없음.

## 다음 작업
- 실제 창을 띄워 세부구역 체크박스 UX와 스크롤 동작을 육안으로 확인 필요(이번 요청 범위상 미수행).
- `get_selected_subregions()`를 실제 수집 큐(`region_expander.build_tiered_query_queue`)에 연결하는 것은 여전히 별도 배선 승인 이후 진행.
- LEGAL_NOTICE/README 정식 수정, 순위추적 실제 구현은 계속 보류.

# 2026-07-10 UI-CLEANUP-1C 여러 구 선택 + 세부구역 선택 쿼리 반영 + UI 여백 정리

## 배경
UI-CLEANUP-1B 사용자 피드백: (1) 세부구역 체크/해제가 실제 수집 쿼리에
반영되어야 함(이전까지는 UI 상태만 보관하고 파이프라인 미연결), (2) 시/군/구는
1개가 아니라 여러 개 선택 가능해야 하고, 나중에 또 구조를 바꾸지 않도록
지금 여러 구 기준으로 설계, (3) 왼쪽 설정 패널의 위/아래 여백을 통일. 이번
작업이 이 세션에서 처음으로 **UI 선택 상태를 실제 수집 쿼리 생성에 연결**한
단계다(그동안은 화면 표시/검증용으로만 썼음). 순위추적 탭은 변경 없음, 실제
네이버 live 수집은 하지 않았다.

## 변경 내용 (src/ui.py, 단일 파일 + 신규 테스트 1개)
- **여러 구 선택**: 시/군/구를 드롭다운(1개) → 체크박스 다중 선택(3열 그리드)으로 변경. `self.selected_district_vars: {구이름: BooleanVar}`로 관리, `get_selected_districts()`가 체크된 구 목록을 반환. 여러 시/도 동시 선택은 이번 범위 밖(시/도는 여전히 드롭다운 1개).
- **구별 세부구역 상태**: `self.region_selection_vars`를 `{구이름: {"legal_dongs": {...}, "landmarks": {...}}}`로, `self._subdivision_layers`를 `{구이름: {"legal_dongs": [...], "landmarks": [...]}}`로 재구조화. 시/도가 바뀌면(`_reload_district_data`) 전체를 새로 만들고 기본 구(강동구, 없으면 첫 번째 구)만 선택. 구 체크박스를 새로 켜면(`_on_district_toggle` → `_ensure_subregion_data_loaded`) 그 구의 데이터를 최초 1회 로드하고 전체 선택으로 초기화하며, 체크 해제해도 캐시는 지우지 않아 다시 체크하면 이전 선택이 그대로 남는다.
- **세부구역 UI**: `_render_subregion_selection`이 현재 선택된 구를 순서대로 순회하며 각 구 이름을 소제목으로 표시하고, 데이터가 있으면 법정동/역상권 체크박스를, 없으면 "이 지역의 세부구역 데이터는 아직 준비 중입니다. 현재는 {구} 기준으로 수집합니다." 안내를 그린다. 전체 선택/해제 버튼은 하단에 1쌍만 두고 현재 로드된 모든 구에 동시 적용.
- **실제 쿼리 생성에 반영(이번 작업의 핵심)**: 신규 모듈 레벨 순수 함수 `build_collection_queries(city, district_selections, keyword)`가 구별 `has_subregion_data`/`selected_subregions` 상태로 최종 쿼리(`{"region","keyword","query"}` job dict list, `_run_queue_pipeline`이 바로 받는 형태)를 만든다. 데이터 있는 구+세부구역 선택 → 세부구역별 쿼리, 데이터 없는 구 → 구 기준 fallback 쿼리 1개, 데이터 있는 구인데 전부 해제 → 그 구는 쿼리 생성에서 제외(fallback 아님). 중복 쿼리는 순서를 유지한 채 제거. 인스턴스 메서드 `_build_collection_queries()`가 현재 UI 상태를 모아 이 순수 함수에 위임하고, `start_crawl()`이 `_build_query_queue` 대신 이 결과를 그대로 사용(구 다중 선택 이전의 단일 지역 헬퍼 `_get_selected_region`/`_build_query_queue`는 제거).
- **0개 쿼리 차단**: 구/세부구역 선택 결과 쿼리가 0개면 "수집할 지역 또는 동/상권이 선택되지 않았습니다. 최소 1개 이상의 구 또는 세부구역을 선택해주세요." 오류로 수집 시작을 막는다.
- **예상 쿼리 수 표시**: `_estimate_query_count()`(=`len(_build_collection_queries())`)를 세부구역 요약 문구에 반영 - "선택된 구: N개\n예상 수집 쿼리: M개"(자동 세분화 on/off와 무관하게 항상 최신 값으로 갱신).
- **안전 안내 문구 추가**: 세부구역 설정 섹션에 "선택한 구가 많을수록 검색 쿼리 수가 증가하여 시간이 오래 걸리거나 보안 확인으로 중단될 수 있습니다. 보안 확인 감지 시 우회하지 않고 현재까지 수집된 결과를 저장합니다." 고정 안내 추가(우회/회피 표현 없음, 기존 SAFE-1 취지와 동일).
- **목표 수집 개수 문구 보완**: "여러 구를 선택한 경우 전체 선택 지역 합산 기준입니다.", "목표 개수에 도달하면 남은 지역이 있어도 조기 종료될 수 있습니다.", "현재 네이버 플레이스 검색 노출 구조상 한 번의 검색 조합에서 수집 가능한 결과 수에는 한계가 있으며, 일반적으로 최대 300개 기준으로 처리합니다." 문장을 지시받은 문구 그대로 추가(기존 "무조건 300개 보장" 금지 원칙 유지).
- **왼쪽 패널 여백 통일**: `_SECTION_TITLE_PADY = (16, 4)`, `_SECTION_BODY_PADY = (0, 16)` 상수를 도입해 지역/세부구역/키워드/필터/목표개수 5개 섹션 전부에 동일하게 적용 - 첫 섹션 위쪽 여백과 마지막 섹션 아래쪽 여백이 대칭이 되도록 정리. `CTkScrollableFrame`(UI-CLEANUP-1B에서 도입) 구조는 그대로 유지.
- **순위추적 탭**: 변경 없음.
- **주석**: 여러 구 선택을 처음부터 도입한 이유(재설계 방지), 세부구역 체크박스가 실제 쿼리에 반영된다는 점(더 이상 미리보기 전용이 아님), 데이터 없는 구의 fallback 처리, 목표 개수가 여러 구 합산 기준이라는 점, 순위추적/빠른 수집 관련 기존 주석은 유지.

## ⚠️ 정직성 caveat(중요)
"목표 개수에 도달하면 남은 지역이 있어도 조기 종료될 수 있습니다"라는 문구를
요청대로 그대로 추가했지만, **현재 `_run_queue_pipeline`은 이 조기 종료를
실제로 구현하지 않는다** - 큐에 있는 모든 쿼리를 끝까지 순회하며, 누적
저장 개수가 목표(target)에 도달해도 중간에 멈추지 않는다(PoC-7에서 검증한
`should_stop_for_target` 조기 종료는 ARCH-300C 실험 코드에만 있고, 이
프로덕션 UI 파이프라인에는 아직 연결되지 않았다). 이번 작업은 UI 문구/쿼리
생성 범위였고 `_run_queue_pipeline`에 실제 target-stop 로직을 넣는 것은
파이프라인 동작 변경이라 이번 범위(UI 정리)를 벗어난다고 판단해 구현하지
않았다 - 문구와 실제 동작이 어긋나는 상태이므로, 다음 단계에서 반드시
`_run_queue_pipeline`에 실제 target 도달 시 조기 종료를 구현하거나, 그 전까지는
이 문구를 사실에 맞게 수정해야 한다.

## 테스트 결과
- `python -m py_compile src/ui.py` PASS.
- `python -c "import src.ui"` PASS, `build_collection_queries`/`get_selected_districts`/`_build_collection_queries`/`_estimate_query_count`/`_ensure_subregion_data_loaded`/`_reload_district_data` 존재 확인.
- 기존 `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향 재확인).
- 신규 `tests/test_ui_query_builder.py`(Tk 불필요, 순수 함수만 테스트) 6건 PASS: 케이스 A(강동구+세부구역 3개→쿼리 3개), 케이스 B(강동구 3개+송파구 fallback→쿼리 4개), 케이스 C(강동구 세부구역 전부 해제→쿼리 0개, fallback 아님), 케이스 D(강남구 데이터 없음→fallback 1개), 중복 쿼리 순서 유지 제거, 빈 입력 방어.
- 다중 키워드 8케이스 재확인(1B와 동일 결과), `load_region_layers`로 강동구(9/6)·송파구(0/0, fallback 대상) 재확인.
- live 실행/EXE/build/app.py 실행 없음.

## 결과 요약
- 시/군/구 다중 선택 + 구별 세부구역 체크/해제가 실제 수집 쿼리 생성(`build_collection_queries`)에 반영되는 구조로 바뀌었다(이 세션 최초로 UI 선택 상태 → 실제 쿼리 연결).
- 예상 쿼리 수가 선택 변경 즉시 요약 문구에 반영된다.
- 왼쪽 패널 섹션 여백이 상수 기반으로 통일됐다.
- **문구상 "목표 도달 시 조기 종료"는 아직 실제 파이프라인 동작이 아니다(위 caveat 참고)** - 다음 단계에서 반드시 해소 필요.

## 다음 작업
- `_run_queue_pipeline`에 실제 target 도달 시 조기 종료 로직을 추가하거나(파이프라인 변경 필요, 별도 승인), 그 전까지 목표 개수 문구에서 조기 종료 관련 문장을 사실에 맞게 재검토.
- 실제 창을 띄워 여러 구 선택 UX/스크롤/여백을 육안으로 확인 필요(이번 요청 범위상 미수행).
- LEGAL_NOTICE/README 정식 수정, 순위추적 실제 구현은 계속 보류.

# 2026-07-10 UI-CLEANUP-1D-A 다중 구 선택 UI 레이아웃 안정화 + 크로스플랫폼 호환성 보완

## 배경
UI-CLEANUP-1C에서 여러 구 선택 + 세부구역 실제 쿼리 반영을 완료했지만, 실제
화면 확인 결과 (1) 구 이름이 3열 체크박스에서 잘림, (2) 세부구역 안내 문구가
좁아 보기 어려움, (3) 스크롤 시 잔상, (4) 왼쪽 패널이 난잡함, (5) 사용자가
말한 "여백"은 왼쪽 섹션 간격이 아니라 **[DB 수집] 탭 바로 위 상단 여백과
앱 맨 아래 하단 여백**이었음, (6) Windows/macOS 호환성 고려 필요 - 라는
피드백을 받았다. 이번 작업은 레이아웃 안정화에 집중했고, 안내·정책 탭 추가와
목표 개수 조기 종료 문구-동작 정합성(1D-A 이전 caveat)은 다음 1D-B로 미뤘다.
실제 macOS 테스트는 **수행하지 않았다** - 아래 보고는 전부 "코드상 호환성
고려"이지 실제 검증이 아니다.

## 변경 내용 (src/ui.py, 단일 파일)
- **창 크기/최소 크기**: `geometry("1240x820")`, `minsize(1100, 780)`, `resizable(True, True)`로 변경(기존 `1000x800`/고정 크기). 고정 크기가 오히려 다양한 모니터/DPI에서 내용이 잘릴 위험이 크다고 판단해 가변 크기 + 최소 크기 하한으로 바꿨다.
- **왼쪽 패널 폭 고정**: `db_tab.grid_columnconfigure(0, weight=0, minsize=_LEFT_PANEL_MIN_WIDTH)`(420px), 오른쪽은 `weight=1`로 남는 공간을 전부 흡수하도록 변경(기존 weight 4:6 비율 방식 폐기). 창을 줄여도 왼쪽 폭은 420px 밑으로 줄지 않는다.
- **앱 전체 상단/하단 외곽 여백**: `_OUTER_PAD_X=12`, `_OUTER_PAD_Y=(14,14)` 상수를 도입해 `tabview.grid(...)`의 padx/pady에 적용 - tabview가 창 전체를 채우는 유일한 최상위 grid 셀이므로, 이 pady 하나로 "제목~탭 위" 여백과 "앱 맨 아래" 여백이 자동으로 대칭이 된다(1C에서 다룬 왼쪽 패널 섹션 간격과는 다른 층위의 여백임을 이번에 명확히 구분).
- **구 체크박스 글자 잘림 개선**: 3열 → 2열로 변경(`district_checkbox_frame.grid_columnconfigure((0,1), weight=1)`), padx/pady도 소폭 확대. 왼쪽 패널 폭 확대와 함께 적용해 "영등포구" 같은 4글자 구 이름도 잘리지 않게 함.
- **세부구역 상세를 팝업으로 분리(이번 작업의 핵심)**: 메인 화면의 인라인 "수집할 동/상권 선택 ▼" 토글 + 펼침 프레임을 제거하고, "수집할 동/상권 설정" 버튼 1개만 남겼다. 버튼을 누르면 `ctk.CTkToplevel` 팝업(`_open_subregion_popup`)이 뜨고, 그 안의 `CTkScrollableFrame`에 구별 법정동/역상권 체크박스(또는 "준비 중" 안내)를 그린다(`_render_subregion_selection`이 이제 팝업 컨테이너를 대상으로 그림). 팝업 하단에 [전체 선택]/[전체 해제]/[적용]/[닫기] 4개 버튼. 체크박스는 `region_selection_vars`의 기존 `BooleanVar`를 그대로 공유하므로 체크/해제가 즉시 실제 상태에 반영되고, 적용/닫기는 팝업을 닫고 메인 화면 요약(선택 구 수/예상 쿼리 수)만 다시 계산한다(`_close_subregion_popup`). 팝업이 이미 열려 있으면 새로 만들지 않고 기존 창을 앞으로 가져온다(`_is_subregion_popup_open` 가드로 중복 생성/상태 꼬임 방지). 지역/구 선택이 바뀌면 팝업이 열려 있을 때만 다시 그린다(`_render_subregion_selection_if_popup_open`) - 닫혀 있으면 그릴 대상이 없으므로 스킵.
- **쿼리 생성 로직은 100% 유지**: `build_collection_queries`(순수 함수)/`_build_collection_queries`/`get_selected_districts`/`get_selected_subregions`/데이터 없는 구 fallback/세부구역 전부 해제 시 제외 로직은 전혀 건드리지 않았다 - 팝업은 순전히 "체크박스를 어디에 그리느냐"만 바꾼 것이고, 상태 저장소(`region_selection_vars` 등)와 쿼리 생성 파이프라인은 UI-CLEANUP-1C 그대로다.
- **스크롤 잔상/겹침 개선 조치**: (1) 왼쪽 `CTkScrollableFrame`(left_panel) 안에 있던 대량의 동적 체크박스 트리(구별 법정동/역상권 블록)를 팝업으로 완전히 빼서, 왼쪽 패널의 destroy/recreate 대상이 구 체크박스 1개 그리드로 크게 줄었다. (2) `_render_subregion_selection`은 여전히 destroy 후 recreate 방식이지만 대상이 팝업 안의 독립된 스크롤 프레임이라 왼쪽 패널 렌더링에 영향을 주지 않는다. (3) 중첩 스크롤(스크롤 안에 스크롤)을 만들지 않음(팝업 자체가 별도 창이므로 left_panel의 스크롤과 겹치지 않음).
- **Windows/macOS 호환성 고려(코드 리뷰 수준, 실제 macOS 테스트 아님)**: 폰트는 전부 `ctk.CTkFont(size=..., weight=...)`로 CustomTkinter 기본 폰트를 쓰고 있어 Windows 전용 폰트(예: 맑은 고딕) 하드코딩이 없음(기존부터 없었음, 이번에 재확인). 체크박스/버튼에 타이트한 고정 폭을 강제하지 않도록 버튼 width를 90→100으로 소폭 확대(macOS에서 버튼 텍스트가 더 넓게 렌더링될 수 있는 점 고려). `place()` 절대좌표 사용처가 코드베이스 전체에 없음을 grep으로 확인(grid/pack만 사용). DPI/화면 크기 편차에 대응하도록 고정 크기 대신 `minsize` + `weight` 기반 grid로 전환.
- **주석**: 왼쪽 섹션 간격(`_SECTION_*`)과 앱 전체 외곽 여백(`_OUTER_PAD_*`)이 서로 다른 층위임을 명시, 팝업 분리 이유(스크롤 잔상/난잡함), 팝업 체크박스가 기존 상태(`region_selection_vars`)를 그대로 공유한다는 점, 버튼 표시 조건이 데이터 유무가 아니라 "선택된 구가 있는지"로 바뀐 이유(일부 구만 데이터 없는 경우 대응).

## 테스트 결과
- `python -m py_compile src/ui.py` PASS.
- `python -c "import src.ui"` PASS, `_open_subregion_popup`/`_close_subregion_popup`/`_is_subregion_popup_open`/`_render_subregion_selection_if_popup_open` 존재 확인.
- 기존 `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향 재확인).
- 기존 `tests/test_ui_query_builder.py` 6건 전부 PASS(케이스 A~D + 중복 제거 + 빈 입력 - 팝업 분리가 쿼리 생성 순수 함수에 전혀 영향을 주지 않음을 재확인, 코드 변경 없이 그대로 통과).
- `grep ".place("` 결과 없음(절대좌표 배치 없음, grid/pack만 사용) 확인.
- **실제 macOS 테스트는 수행하지 않았다** - 위 호환성 조치는 코드 리뷰 수준의 대비이며, 실제 macOS/Windows 10 화면에서의 렌더링 확인은 사용자가 직접 실행해야 한다.
- live 실행/EXE/build/app.py 실행 없음.

## 결과 요약
- 창 기본 1240x820 / 최소 1100x780 / 크기 조절 가능으로 변경.
- 왼쪽 패널 폭 420px 고정, 오른쪽이 남는 공간 전부 사용.
- 앱 전체 상단(제목~탭 위)/하단(맨 아래) 외곽 여백이 `_OUTER_PAD_Y=(14,14)`로 대칭.
- 구 체크박스 3열→2열, 텍스트 잘림 개선.
- 세부구역 상세가 메인 화면 인라인 펼침 → 별도 팝업(Toplevel)으로 분리, 쿼리 생성 로직/데이터 없는 구 fallback/전부 해제 시 제외 동작은 그대로 유지.
- Windows/macOS 호환성은 코드 수준으로만 고려(고정폭 최소화, place() 미사용, 기본 폰트 사용) - 실기 테스트 아님.

## 다음 작업 (1D-B로 이월)
- 안내·정책 탭 추가.
- 목표 개수 문구의 "조기 종료" 표현과 `_run_queue_pipeline`의 실제 동작 정합성 확보(1C에서 남긴 caveat).
- 실제 창을 Windows 10/11/macOS에서 띄워 이번 레이아웃 변경을 육안으로 확인 필요(이번 요청 범위상 미수행).
- LEGAL_NOTICE/README 정식 수정, 순위추적 실제 구현은 계속 보류.

# 2026-07-10 UI-CLEANUP-1D-B 목표 개수 문구-동작 정합성 + 안내·정책 탭 자리 추가

## 배경
1D-A에서 남긴 caveat(목표 수집 개수 UI 문구가 "조기 종료 가능"이라고 안내하지만
실제 `_run_queue_pipeline`은 이를 구현하지 않음)을 이번에 해소했다. 함께
[DB 수집]/[순위추적]에 [안내·정책] 탭 자리만 추가했다(실제 정책 문구/라이선스
인증/결제·고객센터 기능은 이번에 구현하지 않음).

## 1. 흐름 점검 결과 (start_crawl → _run_queue_pipeline → 저장)
- `start_crawl()`이 `self.limit_var`(목표 수집 개수, 기본 300)를 정수로 파싱해 `limit`이라는 이름으로 `_run_queue_pipeline(query_queue, limit, ...)`에 전달한다.
- `_run_queue_pipeline`은 `query_queue`의 각 job(구/세부구역별 검색 조합)을 순회하며 **매번 동일한 `limit` 값을 그 쿼리의 상한으로 그대로 재사용**한다(`_collect_premium_query(query, limit, ...)` / `_collect_basic_query(query, limit, ...)`).
- 각 쿼리의 결과는 `all_merged_data.extend(...)`로 단순 누적될 뿐, **쿼리 간 place_id 중복 제거나 누적 개수 기준 중단은 전혀 없다.** 큐의 모든 쿼리를 끝까지 돌고 나서야 `export_places_to_excel`로 저장한다.
- 결론: `limit`은 이름("목표 수집 개수")과 달리 실제로는 **검색 조합(쿼리) 1개당 상한**으로 동작한다. 구/세부구역을 여러 개 선택해 쿼리가 N개가 되면, 최종 저장 건수는 이론상 `limit × N`까지 늘어날 수 있다(중복 제거 없이).

## 2. 해결 방식: B안 채택(문구 수정, 조기 종료 로직 미구현)
- **A안(정확한 조기 종료 구현)을 채택하지 않은 이유**: 정확하게 하려면 쿼리 간 place_id dedup을 `_run_queue_pipeline`에 새로 연결해야 하는데, 그 dedup 로직(`dedup_rows`/`seen` 집합)은 현재 `src/pc/network_list_scraper.py`(ARCH-300C 실험 코드)에만 있고 프로덕션 파이프라인(`collect_pc_full`/`crawl_places` 등)에는 연결되어 있지 않다. 이걸 지금 연결하는 것은 "크롤러 엔진 대규모 변경"에 해당하고, 부정확하게 구현하면(예: 단순 카운트만 보고 중단) 데이터 누락/오해를 유발할 위험이 더 크다고 판단했다.
- **B안 채택**: 조기 종료 관련 문장을 UI에서 제거하고, 목표 개수 설명을 실제 동작에 맞게 다시 썼다.
  - 변경 전: "...목표 개수에 도달하면 남은 지역이 있어도 조기 종료될 수 있습니다. 현재 네이버 플레이스 검색 노출 구조상 한 번의 검색 조합에서 수집 가능한 결과 수에는 한계가 있으며, 일반적으로 최대 300개 기준으로 처리합니다..."
  - 변경 후: "중복 제거 후 최종 저장 개수 기준입니다. 여러 구를 선택한 경우 전체 선택 지역 합산 기준입니다. 네이버 플레이스 검색 구조상 한 번의 검색 조합은 최대 300개 기준으로 처리합니다. 업종/지역 규모에 따라 목표 개수에 못 미칠 수 있습니다."
  - "한 번의 검색 조합은 최대 300개 기준으로 처리합니다" 문장은 실제 코드 동작(쿼리 1개당 `limit` 상한)과 정확히 일치하므로 그대로 살렸다.

## 3. target_count / per_query_limit 점검 결과
- 코드에는 별도의 `target_count`/`per_query_limit`/`final_save_limit` 변수가 없고, **`self.limit_var` 하나가 UI 표시상 "목표 수집 개수"이면서 실제로는 쿼리별 상한(`per_query_limit`)으로 쓰이는 상태**다.
- 이번 단계에서는 변수/구조를 분리하지 않았다(요청 범위: 문구 정합성 우선, 크롤러 엔진 대규모 변경 금지). 대신 `self.limit_var` 정의부와 `_run_queue_pipeline` 진입부에 이 사실을 명확히 밝히는 주석을 남겨, 이후 실제로 target_count/per_query_limit을 분리하는 리팩터링을 할 때 참고할 수 있게 했다.
- **리스크**: 사용자가 "목표 수집 개수 300, 구 5개 선택"처럼 입력하면 실제로는 최대 1500건 가까이(쿼리 5개 × 300) raw로 모여 그대로 저장될 수 있다 - "300개 근처로 맞춰질 것"이라는 오해를 할 수 있으므로, 이번에 "여러 구를 선택한 경우 전체 선택 지역 합산 기준"이라는 문장은 유지하되 조기 종료/정확한 캡 실현 주장은 전부 제거해 과장하지 않도록 했다.

## 4. 안내·정책 탭 자리 추가
- 탭 구성: `[DB 수집] [순위추적] [안내·정책]`.
- `_build_policy_tab()` 신규 — 제목 + "이 영역은 정식 배포 전 최종 안내 문구를 작성할 예정입니다." 안내 + 카드 5개(수집 기준 안내 / 보안 확인 및 부분 저장 안내 / 유지보수·A/S 안내 / 라이선스 안내 / 사용자 주의사항), 각 카드 본문은 전부 "정식 배포 전 작성 예정" placeholder 한 줄뿐이다. 실제 정책 문구, 1PC 라이선스 인증, 결제/고객센터/계정 기능은 전혀 구현하지 않았다(자리만 생성).

## 테스트 결과
- `python -m py_compile src/ui.py` PASS.
- `python -c "import src.ui"` PASS, `_build_policy_tab` 존재 확인.
- 기존 `tests/test_ui_pc_full_wiring.py` 4건, `tests/test_ui_query_builder.py` 6건 전부 PASS(무영향 재확인). target_count/per_query_limit 관련 순수 헬퍼는 이번에 추가하지 않아(B안 채택, 로직 미변경) 신규 pure test는 없다.
- live 실행/EXE/build/app.py 실행 없음.

## 결과 요약
- 목표 수집 개수 UI 문구가 실제 `_run_queue_pipeline` 동작과 정합하도록 수정됨(조기 종료 주장 제거).
- `limit`이 실제로는 쿼리 1개당 상한이라는 사실이 코드 주석으로 명확히 문서화됨(향후 target_count/per_query_limit 분리 리팩터링의 출발점).
- `[안내·정책]` 탭 자리 추가(placeholder만, 실제 정책/라이선스 기능 없음).
- DB 수집/순위추적 탭의 기존 기능(여러 구 선택, 세부구역 팝업, 쿼리 생성, 단일 키워드 등)은 전혀 변경하지 않음.

## 다음 작업
- target_count(전체 목표)와 per_query_limit(쿼리별 상한)을 실제로 분리하고, 쿼리 간 place_id dedup을 프로덕션 파이프라인에 연결할지는 별도 승인 후 진행(ARCH-300C 계층형 큐 배선 결정과 함께 검토).
- 안내·정책 탭의 실제 문구는 정식 배포 전 별도 태스크로 작성.
- 1PC 라이선스 인증은 개발 마지막 단계에서 별도 구현.
- 실제 창을 Windows 10/11/macOS에서 띄워 이번 변경을 육안으로 확인 필요(이번 요청 범위상 미수행).
- LEGAL_NOTICE/README 정식 수정, 순위추적 실제 구현은 계속 보류.

# 2026-07-10 UI-CLEANUP-1D-B 후속 라벨 정정: "검색 조합당 수집 상한"

## 배경
1D-B에서 "조기 종료" 문구는 제거했지만, 섹션 라벨이 여전히 "5. 목표 수집
개수"로 남아 있어 마치 전체 목표처럼 오해될 수 있었다. `limit_var`는 실제로
전체 목표가 아니라 검색 조합(쿼리) 1개당 상한으로 동작하므로, 라벨과 설명
문구를 그 실제 동작 그대로 표현하도록 정정했다.

## 변경 내용
- `src/ui.py` `_build_target_count_section`: 라벨 "5. 목표 수집 개수" → **"5. 검색 조합당 수집 상한"**.
- 설명 문구를 다음으로 교체:
  "각 지역/동/상권 검색 조합마다 적용되는 수집 상한입니다.
  네이버 플레이스 검색 구조상 한 번의 검색 조합은 최대 300개 기준으로 처리합니다.
  전체 저장 개수는 선택한 구/세부구역 수와 중복 제거 결과에 따라 달라질 수 있습니다."
- 조기 종료 관련 문구/로직은 다시 추가하지 않았다(1D-B의 결정 유지).

## 테스트 결과
- `python -m py_compile src/ui.py` PASS.
- `tests/test_ui_pc_full_wiring.py` 4건, `tests/test_ui_query_builder.py` 6건 전부 PASS(무영향).
- live 실행/EXE/build/app.py 실행 없음.

# 2026-07-10 UI-CLEANUP-1E DB 수집 탭 문구 축약 + 스크롤 잔상 완화

## 배경
실제 화면 확인 결과 왼쪽 DB 수집 패널을 빠르게 스크롤할 때 잔상이 보이고,
설명 문구가 많아 화면이 무겁게 느껴진다는 피드백을 받았다. 긴 설명 텍스트를
줄여 텍스트 밀도를 낮추고, 상세 설명은 추후 [안내·정책] 탭에서 다루기로
했다. 기능 로직은 전혀 변경하지 않았다.

## 축약한 문구
- **세부구역 설정 안전 안내**: "선택한 구가 많을수록 검색 쿼리 수가 증가하여 시간이 오래 걸리거나 보안 확인으로 중단될 수 있습니다. 보안 확인 감지 시 우회하지 않고 현재까지 수집된 결과를 저장합니다."(3줄) → **"보안 확인 감지 시 수집을 중단하고 현재 결과를 저장합니다."**(1줄).
- **새로오픈 필터 설명**: "체크 시 새로오픈 업체만 저장합니다. 체크 해제 시 새로오픈이 아닌 업체도 포함합니다." → "체크 시 새로오픈 업체만 저장합니다. 체크 해제 시 전체 업체를 포함합니다."(간결화).
- **검색 조합당 수집 상한 설명**(라벨 "5. 검색 조합당 수집 상한"은 유지): "각 지역/동/상권 검색 조합마다 적용되는 수집 상한입니다. 네이버 플레이스 검색 구조상 한 번의 검색 조합은 최대 300개 기준으로 처리합니다. 전체 저장 개수는 선택한 구/세부구역 수와 중복 제거 결과에 따라 달라질 수 있습니다."(5줄) → **"각 검색 조합마다 적용되는 수집 상한입니다. 전체 저장 개수는 지역 수와 중복 제거 결과에 따라 달라집니다."**(2줄). "최대 300개" 관련 상세 설명은 [안내·정책] 탭에서 정식 문구 작성 시 다루기로 하고 제거했다. 조기 종료 문구는 다시 추가하지 않았다(1D-B 결정 유지).

## 스크롤 잔상 완화를 위해 적용한 조치
- 왼쪽 패널 안의 3~5줄짜리 wrap label 3개를 1~2줄로 줄여 왼쪽 `CTkScrollableFrame` 안의 텍스트 위젯 높이/개수를 낮췄다.
- 불필요한 배경/이유 설명 문장을 제거해 스크롤해야 하는 실제 콘텐츠 높이를 줄였다.
- fg_color/배경색은 기존 그대로(투명/기본값) 유지 - 부모와 어색하게 다른 색상은 없음을 재확인.
- 세부구역 체크박스 자체는 이미 1D-A에서 팝업으로 분리되어 있어 이번에는 인라인 텍스트만 축약했다.

## 기능 로직 변경 여부
**변경 없음.** 수집/쿼리 생성 로직(`build_collection_queries`, `_build_collection_queries`, `get_selected_districts`, `get_selected_subregions` 등), 필터/키워드 검증, `_run_queue_pipeline` 동작은 전혀 건드리지 않았다. 라벨 텍스트/설명 문자열만 수정.

## 테스트 결과
- `python -m py_compile src/ui.py` PASS.
- `tests/test_ui_pc_full_wiring.py` 4건, `tests/test_ui_query_builder.py` 6건 전부 PASS(무영향).
- live 실행/EXE/build/app.py 실행 없음.

## 다음 작업
- 긴 설명(쿼리 수 증가에 따른 시간/보안 확인 배경, 300개 처리 기준 상세)은 [안내·정책] 탭 정식 문구 작성 시 반영.

# 2026-07-14 ARCH-300C WIRE-1 순수 orchestrator 구현(live 없음)

## 배경
ARCH-300C-PRODUCT-WIRING-PLAN 설계 완료 후, 제품 기본 수집 엔진을 Network/List
관찰 엔진으로 전환하기 위한 첫 단계로 "실제 제품 배선 없는 순수 orchestrator"만
먼저 구현했다. 기존 PC 상세 수집(collect_pc_full 등)은 전혀 건드리지 않았고,
네이버 live 접속/Playwright/브라우저/app.py/UI 실행/build/EXE는 이번 단계에서
모두 하지 않았다.

## 변경 파일
- 신규 `src/pc/network_pipeline.py`: `run_collection_plan()` 순수 orchestrator.
- `src/ui.py`: `build_collection_queries()`에 `source_city`/`source_district`/
  `source_subregion`/`source_layer` 내부 메타만 추가(기존 region/keyword/query
  키·값, UI 레이아웃/탭/문구는 변경 없음).
- 신규 `tests/test_pc_network_pipeline.py`: fake collect_query 기반 7개 케이스.
- `tests/test_ui_query_builder.py`: source_* 메타 검증 케이스 2개 추가, 기존
  케이스 D는 반환 dict 키 수가 늘어난 것에 맞춰 정확 일치(`==`) 대신 필요한
  필드(region/keyword/query)만 값 비교하도록 조정.

## network_pipeline.py 구현 내용 / 반환 구조
`run_collection_plan(jobs, *, per_query_limit, target_count, collected_at,
collect_query, on_partial_save=None, on_security_block=None, seen=None)`이
jobs를 순서대로 순회하며 `collect_query(job, per_query_limit)`를 호출한다.
반환 dict: `rows`, `executed_query_count`, `skipped_query_count`, `stop_reason`
(`"target_reached"`/`"queue_exhausted"`/`"security_blocked"`/`"status_429"`/
`"empty_jobs"`), `before_trim_count`, `final_count`, `security_blocked`,
`status_429_seen`.

## dedup 처리 방식
`network_list_scraper.dedup_rows()`를 그대로 재사용(신규 재구현 없음). `seen`
집합을 전체 jobs에 걸쳐 공유하며(호출자가 넘기지 않으면 새로 생성), place_id
기준(없으면 업체명 기준) 중복을 제거한다.

## target_count 처리 방식
`network_list_scraper.should_stop_for_target()`을 재사용해 dedup 누적 rows가
target_count 이상이면 그 쿼리까지 처리한 뒤 `target_reached`로 중단하고,
rows를 `rows[:target_count]`로 trim한다. target_count가 None/0 이하면 target
중단을 비활성화(기존 `should_stop_for_target`의 방어 정책과 동일).

## per_query_limit 처리 방식
collect_query에 그대로 전달하는 것 외에, 반환된 rows가 per_query_limit보다
많으면 dedup 이전에 `rows[:per_query_limit]`로 한 번 더 방어적으로 cap한다.

## safety stop 처리 방식
`active_captcha_detected` 또는 `status_429_seen`이 True면 해당 쿼리까지의
rows를 포함해 즉시 중단한다. `src/pc/safety.py`는 수정하지 않고 `SafetyReason
.CAPTCHA_OR_SECURITY_BLOCK`만 재사용해 `SimpleNamespace` decision을 만들어
`on_security_block` 콜백을 best-effort(예외 무시)로 1회 호출한다(pipeline.py의
`collect_pc_full`과 동일한 try/except 패턴). CAPTCHA 우회/자동 해결은 시도하지
않음. 이 경우에만 `on_partial_save`도 best-effort로 호출한다.

## build_collection_queries source_* 메타 추가
기존 반환 필드(region/keyword/query)는 그대로 두고 `source_city`,
`source_district`, `source_subregion`, `source_layer`
(`"legal_dong"`/`"landmark"`/`"fallback"`/`"unknown"`)를 추가했다.
`district_selections` entry에 선택적으로 `legal_dongs`/`landmarks` 원본 목록을
함께 넘기면 그 목록 기준으로 `legal_dong`/`landmark`를 분류하고, 넘기지 않으면
(기존 호출부인 `_build_collection_queries` 인스턴스 메서드는 아직 이 목록을
분리 전달하지 않음) `unknown`으로 분류한다 - 실제 UI 인스턴스 메서드 배선은
이번 WIRE-1 범위 밖이며 후속 단계로 남겨둔다.

## 테스트 결과
- `python -m py_compile src/pc/network_pipeline.py src/ui.py tests/test_pc_network_pipeline.py tests/test_ui_query_builder.py` PASS.
- `tests/test_pc_network_pipeline.py` 7건 전부 PASS(queue_exhausted/global dedup/target_reached/per_query_limit/active_captcha_detected/status_429_seen/empty_jobs).
- `tests/test_ui_query_builder.py` 8건 전부 PASS(기존 6건 + source_* 메타 신규 2건).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향, collect_pc_full 경로 미수정 확인).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향, dedup_rows/should_stop_for_target 재사용 확인).

## live/Playwright/app.py/build 실행 여부
**전부 실행 안 함.** 네이버 live 접속 없음, Playwright/브라우저 실행 없음,
app.py/UI 실행 없음, build/EXE 실행 없음. fake collect_query와 pure function
테스트만 수행했다.

## 다음 단계 제안
- WIRE-2(실제 제품 배선/live 검증) 전에 LEGAL_NOTICE/README/안내·정책 문구
  재정리가 필요(이번 계획서 확정 사항).
- `_build_collection_queries` 인스턴스 메서드가 `legal_dongs`/`landmarks`를
  분리 전달하도록 배선하면 실제 UI 경로에서도 source_layer가
  legal_dong/landmark로 정확히 분류됨(현재는 unknown으로 남음) - 이 배선
  자체는 별도 승인 후 진행.
- 실제 live collect_query 구현(Network/List 관찰 기반)과 collect_pc_full 대체
  배선은 이후 WIRE 단계에서 별도 Plan으로 진행.
- 실제 창을 띄워 스크롤 체감 개선 여부를 육안으로 확인 필요(이번 요청 범위상 미수행).

# 2026-07-14 ARCH-300C WIRE-1B 실제 UI 쿼리 경로 source_layer 메타 배선

## 배경
WIRE-1에서 `build_collection_queries()` 순수 함수는 legal_dongs/landmarks가
전달되면 source_layer를 정확히 분류하지만, 실제 UI 인스턴스 메서드
`_build_collection_queries()`는 이 두 목록을 분리 전달하지 않아 실제 화면
경로에서는 source_layer가 항상 "unknown"으로 남는 문제가 있었다. 이번
WIRE-1B는 그 배선만 보완했다(수집 엔진/network_pipeline 연결은 계속 하지
않음).

## 변경 파일
- `src/ui.py`: `_build_collection_queries()` 인스턴스 메서드가
  `district_selections` entry에 `legal_dongs`/`landmarks`를 함께 전달하도록
  보완. `build_collection_queries()` 함수 docstring을 "인스턴스 메서드는 분리
  전달하지 않음" → "WIRE-1B로 분리 전달하여 실제 화면에서는 unknown이
  발생하지 않음"으로 갱신.
- `tests/test_ui_query_builder.py`: 실제 UI 인스턴스 경로(legal_dongs 2개 +
  landmarks 1개 + fallback 구 1개 혼합)를 재현하는 케이스 1개 추가.

## 실제 UI 경로에서 layer를 판별하는 방식
`get_selected_subregions()`가 이미 구별로
`{"legal_dongs": [...], "landmarks": [...]}`를 분리해 반환하고 있었다.
기존 `_build_collection_queries()`는 이 두 리스트를 `subregions = legal_dongs
+ landmarks`로 합쳐서 `selected_subregions`에만 담아 순수 함수에 넘겼는데,
이번에 `legal_dongs`/`landmarks` 원본 리스트도 함께 `district_selections`
entry에 담아 넘기도록 2줄만 추가했다(새 상태/캐시 없음, 기존
`self._subdivision_layers`/`self.region_selection_vars`/
`get_selected_subregions()` 그대로 재사용).

## legal_dong/landmark/fallback 결과 예시
강동구(법정동 천호동/길동 + 역상권 천호역 선택) + 송파구(세부구역 데이터
없음)인 경우:
- "서울특별시 강동구 천호동 카페" → source_layer="legal_dong"
- "서울특별시 강동구 길동 카페" → source_layer="legal_dong"
- "서울특별시 강동구 천호역 카페" → source_layer="landmark"
- "서울특별시 송파구 카페" → source_layer="fallback"
unknown은 발생하지 않음(테스트로 확인).

## 쿼리 순서와 개수 영향 여부
**영향 없음.** `selected_subregions` 계산 로직(legal_dongs + landmarks 순서,
fallback 조건, 빈 세부구역 시 제외)은 전혀 변경하지 않았고, 순수 함수
`build_collection_queries()`의 쿼리 생성/dedup/순서 로직도 WIRE-1B에서는
건드리지 않았다. UI 레이아웃/체크박스 동작도 변경 없음.

## 테스트 결과
- `python -m py_compile src/ui.py tests/test_ui_query_builder.py` PASS.
- `tests/test_ui_query_builder.py` 9건 전부 PASS(기존 8건 + 실제 UI 경로 재현 신규 1건, unknown 미발생 확인 포함).
- `tests/test_pc_network_pipeline.py` 7건 전부 PASS(무영향, orchestrator 미변경 확인).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향, collect_pc_full 미변경 확인).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).

## live/Playwright/app.py/build 실행 여부
**전부 실행 안 함.** 네이버 live 접속 없음, Playwright/브라우저 실행 없음, app.py/UI 실행 없음, build/EXE 실행 없음. 수집 엔진 배선(network_pipeline 실행 연결)도 하지 않음.

## 다음 단계 제안
- WIRE-2(실제 제품 배선/live 검증) 전 LEGAL_NOTICE/README/안내·정책 문구 재정리 필요(기존 계획 유지).
- 실제 live collect_query 구현과 collect_pc_full 대체 배선은 이후 WIRE 단계에서 별도 Plan으로 진행.

# 2026-07-14 ARCH-300C WIRE-2A 쿼리 단위 Network 응답 관찰 함수 구현(live 없음)

## 배경
WIRE-2-PRODUCT-WIRING-PLAN 설계에 따라, 실제 제품 배선(UI 연결/기본 엔진 전환)
전에 "쿼리 1개를 처리하는 Network 응답 관찰 계층"만 먼저 구현했다. 브라우저/
context/page의 생성·소유·teardown 책임은 이번 단계에 없으며(WIRE-2B에서
BrowserSession 기반 context manager로 구현 예정), UI 연결·target_count UI
추가·기본 엔진 전환·run_collection_plan과의 실제 연결·문서 수정도 이번
단계 범위 밖이다. 네이버 live 접속, Playwright 실행 없음.

## 변경 파일
- 신규 `src/pc/network_browser_collector.py`: `collect_network_query()` +
  내부 helper(`_QueryObservationContext`, `_make_response_handler`,
  `_probe_captcha_state`).
- 신규 `tests/test_pc_network_browser_collector.py`: FakePage/FakeResponse/
  FakeLocator 기반 12개 테스트.

## collect_network_query 인터페이스
`collect_network_query(page, job, per_query_limit, *, collected_at,
settle_ms=5000) -> dict`. 이미 생성된 page(또는 FakePage)를 전달받아 쿼리
1개만 처리한다. 반환: `rows`, `active_captcha_detected`, `status_429_seen`,
`candidate_response_count`, `raw_item_count`, `local_unique_count`,
`parse_error_count`, `timeout`.

## listener 등록·해제 방식
`page.on("response", handler)`를 함수 시작 시 1회 등록하고, `try/finally`의
`finally`에서 `page.off("response", handler)`로 반드시 해제한다(정상/예외
경로 모두). handler는 status==429 확인, `is_candidate_response`로 후보
판정, 후보 response 객체 저장, `candidate_response_count` 증가만 수행하고
`response.json()`은 호출하지 않는다(콜백 블로킹 최소화 + parse_error_count
명확한 집계를 위해 settle 종료 후 별도로 파싱).

## 쿼리별 응답 격리 방식
전역/클래스 공용 상태를 두지 않고, 매 호출마다 새 `_QueryObservationContext`
인스턴스를 만들어 handler 클로저가 그 인스턴스에만 기록한다. 함수가 끝나면
context와 handler 모두 버려지므로 다음 쿼리(다음 `collect_network_query`
호출)와 절대 섞이지 않는다. WIRE-2B부터는 페이지 자체도 쿼리마다 새로
생성/종료될 예정이라 이중으로 격리된다.

## 후보 응답 concat 및 local dedup 방식
settle 종료 후 저장된 모든 후보 response를 순회하며 `response.json()` →
`_extract_list_items()`로 items를 뽑아 `raw_items`에 concat한다(각 단계
예외는 `parse_error_count`만 증가시키고 다음 후보로 계속). 각 item을
`_map_item_to_row(item, collected_at, source_query=job["query"])`로
매핑한 뒤, `_map_item_to_row`가 지원하지 않는 `source_city`/
`source_district`/`source_subregion`/`source_layer`는 매핑된 row dict에
job에서 그대로 복사해 추가한다(network_list_scraper.py 무수정). 이후 쿼리
내부 로컬 `seen`(함수 호출마다 새로 생성, 전역 아님)으로 `dedup_rows()`를
적용한다 - 전역 dedup은 이 함수의 책임이 아니라 WIRE-1
`run_collection_plan`의 책임이다.

## per_query_limit 적용 순서
정확히 `raw_items → mapped_rows(+source_* 메타 부여) → local dedup
(dedup_rows) → rows[:per_query_limit]` 순서로 적용했다. 로컬 dedup을 먼저
수행하므로 같은 쿼리 내 중복 응답이 상한 자리를 차지하지 않는다
(`local_unique_count`는 cap 적용 전 값을 그대로 노출해 두 값을 구분할 수
있게 했다).

## CAPTCHA DOM probe 및 active/passive 분류
`_probe_captcha_state(page)`가 PoC-7의 `_probe_captcha_presence`와 동일한
방식으로 `browser_session._CAPTCHA_PROBE_SELECTORS`(읽기 전용 재사용)를
순회해 marker 존재/가시성/bounding box 면적을 관찰한다. 클릭을 전혀 하지
않으므로 `click_intercepted_message`는 항상 빈 문자열이다. 이 결과를 그대로
`classify_captcha_signal()`(읽기 전용 재사용, 재구현 없음)에 넘겨
`active_captcha_detected`를 판정한다 - marker가 DOM에 존재한다는 사실
만으로는 active로 단정하지 않고(오탐 방지), visible+면적>0일 때만 active로
판정하는 기존 정책을 그대로 따른다.

## 429/timeout/0건/parse error 처리
- **HTTP 429**: 후보 URL 여부와 무관하게 모든 response에서 `status==429`
  확인 → `status_429_seen=True`.
- **goto timeout**: `page.goto()` 예외 시 `BrowserSession.goto`와 동일한
  태도로 예외를 삼키고 현재 DOM으로 계속 진행하되, `goto_timed_out=True`로
  기록 → 최종 `timeout=True`.
- **settle 종료까지 후보 응답 0개**: `candidate_response_count==0`이면
  `timeout=True`(goto 성공 여부와 무관).
- **후보 응답은 있으나 items=0**: `candidate_response_count>0`이면
  `timeout=False`로 유지하고 `rows=[]`만 반환 - "정상적인 검색 결과 0건"과
  "관찰 실패(timeout)"을 명확히 구분했다.
- **response.json()/파싱 실패**: 해당 후보만 건너뛰고 `parse_error_count`를
  증가시키며 나머지 후보는 계속 처리한다(함수 전체 크래시 없음).
- 위 어떤 분기에서도 CAPTCHA 우회/자동 해결/재시도/DOM 조작을 시도하지
  않는다. collector는 플래그만 반환하며, 중단 여부 판단은 상위
  orchestrator(`run_collection_plan`)의 책임으로 남겨뒀다.

## FakePage 테스트 목록과 결과
`tests/test_pc_network_browser_collector.py` 12건 전부 PASS: listener 등록·
해제(1회씩, 잔여 없음) / 복수 candidate concat / local dedup 후 1건만 남음 /
per_query_limit이 local dedup 이후 정확히 cap / active CAPTCHA(visible+면적
>0) / passive marker(hidden→active=False) / HTTP 429(비후보 응답에서도 감지)
/ goto timeout(timeout=True, rows=[], CAPTCHA 아님) / candidate 0개(timeout=
True) / 검색결과 0건(timeout=False, rows=[]) / parse error(크래시 없이 나머지
후보 계속 처리) / source_* 메타(job의 source_city/district/subregion/layer/
query가 row에 유지).

## 기존 테스트 회귀 결과
- `python -m py_compile src/pc/network_browser_collector.py tests/test_pc_network_browser_collector.py` PASS.
- `tests/test_pc_network_pipeline.py` 7건 전부 PASS(무영향, orchestrator 무수정 확인).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향, is_candidate_response/_extract_list_items/_map_item_to_row/dedup_rows/classify_captcha_signal 재구현 없이 재사용 확인).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).

## live/Playwright/app.py/UI/build 실행 여부
**전부 실행 안 함.** 네이버 live 접속 없음, Playwright 실행 없음(FakePage만 사용), app.py/UI 실행 없음, build/EXE 실행 없음.

## 다음 단계(WIRE-2B)
- `BrowserSession` 기반으로 브라우저/context를 실제 소유하는 context manager(`NetworkBrowserCollector`) 구현, 쿼리마다 page를 새로 생성/종료.
- UI에 `target_count` 필드 추가 + 신규 `_run_network_pipeline` worker로 fake collector 배선(아직 live 아님).
- `run_collection_plan`에 `should_continue`(사용자 중지) 옵션 추가 여부는 별도 승인 후 결정.
- WIRE-2C(부분 저장/Excel 통합)·WIRE-2D(문서 동시 정합성 수정)는 그 이후 단계.

# 2026-07-14 ARCH-300C WIRE-2A-B navigation timeout과 일반 오류 분리(live 없음)

## 배경
WIRE-2A의 `collect_network_query()`가 `page.goto()`에서 발생한 모든 예외를
`timeout=True`로 뭉뚱그려 분류하고 있었다. 실제 Playwright 실행에서는
TimeoutError(느린 로드) 외에도 page/context/browser가 이미 닫힘(Target
closed), 브라우저 실행 장애, 그 외 일반 navigation 오류가 발생할 수 있는데,
이들을 timeout으로 숨기면 원인 진단이 불가능해진다. 이번 단계는 이 분류만
보완했다. `run_collection_plan`/UI는 여전히 무수정이며, 상위 orchestrator의
중단 정책 추가나 재시도 로직도 이번 범위에 없다.

## 변경 파일
- `src/pc/network_browser_collector.py`: `PlaywrightTimeoutError` import 추가,
  `page.goto()` 예외 처리를 `PlaywrightTimeoutError`(timeout)와 그 외
  `Exception`(navigation_error) 두 갈래로 분리. `finally`의 `page.off()` 호출도
  best-effort(`try/except`)로 방어.
- `tests/test_pc_network_browser_collector.py`: 기존 `check_goto_timeout`을
  실제 `PlaywrightTimeoutError`를 사용하도록 수정, 신규
  `check_goto_navigation_error_is_not_timeout` 테스트 추가.
- `PROJECT_STATE.md`: 이번 기록 append.

## TimeoutError를 식별하는 방식
`from playwright.sync_api import TimeoutError as PlaywrightTimeoutError`를
`browser_session.py`와 동일하게 import해서 `except PlaywrightTimeoutError:`로
명시적으로만 잡는다. 이 경우에만 "느린 로드"로 간주해 관용적으로 흡수하고
(`goto_timed_out=True`), 이후 settle 대기·후보 파싱·CAPTCHA probe를 그대로
계속 진행한다(`BrowserSession.goto`와 동일하게 현재 DOM으로 계속 진행 -
CAPTCHA와 무관).

## 일반 navigation 오류 처리 방식
`PlaywrightTimeoutError`가 아닌 그 외 모든 예외(Target closed, 브라우저 실행
장애, 일반 navigation 오류 등)는 `except Exception as exc:`에서
`navigation_error=True`, `navigation_error_message=f"{type(exc).__name__}:
{exc}"`로 기록한다. 이 경우 페이지 상태를 더 이상 신뢰할 수 없다고 보고
**settle 대기·후보 응답 파싱·CAPTCHA probe를 전부 건너뛰고 즉시 반환**한다
(닫힌 page에 `wait_for_timeout`/`locator`를 호출하면 추가 예외가 발생할
위험이 있기 때문). 반환은 `rows=[]`, `active_captcha_detected=False`,
`timeout=False`로 고정해 CAPTCHA나 429로 오분류되지 않게 했다. 재시도는
하지 않으며, 재시도/복구 정책은 상위 계층(WIRE-2B 이후)의 책임으로 문서화
했다(docstring에 명시). `finally`의 `page.off("response", handler)`도
page/context가 이미 닫힌 상태일 수 있으므로 `try/except`로 감싸 best-effort
로 처리한다.

## 반환 필드 변경
반환 dict에 `navigation_error`(bool)와 `navigation_error_message`(str) 2개
필드를 추가했다. 기존 필드(`rows`/`active_captcha_detected`/
`status_429_seen`/`candidate_response_count`/`raw_item_count`/
`local_unique_count`/`parse_error_count`/`timeout`)는 이름·의미 모두
변경하지 않았다 - PlaywrightTimeoutError 경로는 여전히 `timeout=True`,
`navigation_error=False`로 기존 WIRE-2A 동작과 동일하다.

## 신규 테스트 결과
`tests/test_pc_network_browser_collector.py` 13건 전부 PASS(기존 12건 - 단
`check_goto_timeout`은 실제 `PlaywrightTimeoutError`를 사용하도록 갱신 - +
신규 1건):
- `check_goto_timeout`: `PlaywrightTimeoutError` 발생 시 `timeout=True`,
  `navigation_error=False`, `rows=[]`, CAPTCHA 아님.
- `check_goto_navigation_error_is_not_timeout`(신규): 일반 `Exception`
  ("Target closed" 메시지) 발생 시 `timeout=False`, `navigation_error=True`,
  `navigation_error_message` 비어있지 않음, `rows=[]`, CAPTCHA/429로
  오분류되지 않음.

## 전체 회귀 결과
- `python -m py_compile src/pc/network_browser_collector.py tests/test_pc_network_browser_collector.py` PASS.
- `tests/test_pc_network_browser_collector.py` 13건 전부 PASS.
- `tests/test_pc_network_pipeline.py` 7건 전부 PASS(무영향).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).

## live/Playwright/app.py/UI/build 실행 여부
**전부 실행 안 함.** 실제 Playwright/네이버 접속 없음(FakePage와 playwright
패키지의 `TimeoutError` 클래스만 import해 예외 타입 비교에 사용), app.py/UI
실행 없음, build/EXE 실행 없음.

## 다음 단계
- WIRE-2B에서 `NetworkBrowserCollector`(실제 브라우저 소유)를 구현할 때,
  이번에 추가한 `navigation_error` 신호를 상위에서 어떻게 다룰지(재시도 없이
  즉시 다음 쿼리로 넘어갈지, 큐 자체를 안전 중단할지)를 별도로 설계해야
  한다 - 이번 단계는 "구분만" 했고 "그 이후 정책"은 결정하지 않았다.

# 2026-07-14 ARCH-300C WIRE-2B-1 오케스트레이터 오류 계약 + 브라우저 생명주기 구조(live 없음)

## 배경
WIRE-2A-B가 `collect_network_query()`의 navigation_error를 timeout/CAPTCHA/429
와 분리했지만, 그 신호를 읽는 쪽(orchestrator)이 아직 없었다. 이번 단계는
(1) `run_collection_plan()`이 navigation_error를 인식해 안전하게 중단하도록
확장하고, (2) 사용자 중지를 위한 `should_continue` 계약을 추가하고, (3)
브라우저 1개·context 1개를 큐 전체에서 공유하면서 쿼리마다 새 page를
생성/종료하는 `NetworkBrowserCollector` 생명주기 구조를 구현했다. UI 배선,
target_count UI, Excel 저장 연결, SAFE-1 UI 연결은 이번 범위에 없다. 전부
fake session/context/page/collect_query로만 검증했고, 실제 BrowserSession/
Playwright/네이버 접속은 없었다.

## 변경 파일
- `src/pc/network_pipeline.py`: `run_collection_plan()`에 `should_continue`
  선택 인자 추가, `collect_query` 결과의 `navigation_error`/
  `navigation_error_message`를 읽어 처리, 반환 dict에 두 필드 상시 포함.
- `src/pc/network_browser_collector.py`: `NetworkBrowserCollector` 클래스와
  `_default_session_factory()` 추가(기존 `collect_network_query`/
  `_QueryObservationContext`/`_probe_captcha_state`/`_make_response_handler`
  는 무변경).
- `tests/test_pc_network_pipeline.py`: navigation_error/should_continue 관련
  신규 5건 추가.
- `tests/test_pc_network_browser_collector.py`: `NetworkBrowserCollector`
  생명주기 fake 테스트 6건 추가.

## navigation_error orchestrator 처리
매 job마다 `collect_query(job, per_query_limit)` 호출 직후
`result.get("navigation_error")`를 확인한다(필드가 없으면 falsy이므로 기존
collect_query와 완전히 하위 호환). True면: 해당 job은
`executed_query_count`에 포함하되 그 job의 rows는 global dedup에 누적하지
않고(권장 정책 그대로 채택), 즉시 `stop_reason="navigation_error"`로
break한다. `security_blocked`/`status_429_seen`은 건드리지 않으며(CAPTCHA/429
와 절대 혼동하지 않음) `on_security_block`도 호출하지 않는다. 반환 dict에
`navigation_error`(bool)/`navigation_error_message`(str)를 상시 포함시켰다.

## should_continue 동작
`run_collection_plan(..., should_continue: Callable[[], bool] | None = None)`.
매 job 실행 직전(=`collect_query` 호출 전) `should_continue is not None and
not should_continue()`이면 그 job의 `collect_query`를 호출하지 않고 즉시
`stop_reason="user_stopped"`로 중단한다. `None`(기본값)이면 매 반복마다
체크 자체를 건너뛰어 기존 동작과 완전히 동일하다. 사용자 중지 시
`on_security_block`은 호출하지 않는다.

## stop_reason 목록 변화
기존 `target_reached`/`queue_exhausted`/`security_blocked`/`status_429`/
`empty_jobs`에 `navigation_error`, `user_stopped` 2개가 추가되어 총 7종이
되었다.

## 중단 우선순위(매 job마다, 요청된 순서 그대로 구현)
1) `should_continue()`가 False → `user_stopped`(collect_query 미호출).
2) `collect_query` 실행.
3) `navigation_error` → 즉시 중단(다음 쿼리 미실행 - navigation_error가
   발생한 page/세션을 신뢰하지 않기 때문).
4) active CAPTCHA / 5) HTTP 429 → 기존 `security_blocked`/`status_429` 정책
   그대로 유지(우선순위·반환 계약 변경 없음).
6) 정상 rows를 global dedup에 반영 → 7) `target_count` 도달 검사 → 8) 다음
   job.

## NetworkBrowserCollector 생명주기
`src/pc/network_browser_collector.py`에 추가한 클래스는 "브라우저 1개 →
context 1개 → [쿼리마다: new_page → collect_network_query → page.close()] →
큐 종료 후 context/browser/playwright 종료" 구조를 구현한다.
`__init__(*, collected_at, session_factory=None, settle_ms=5000)`,
`__enter__`(session_factory() 결과를 `__enter__`해 `self._session` 보관),
`collect_query(job, per_query_limit)`(run_collection_plan이 요구하는 2인자
시그니처를 만족하는 bound method), `__exit__`(session의 `__exit__`를
그대로 위임). `session_factory`가 없으면 `BrowserSession`
(`src.pc.browser_session`)과 `DiagnosticConfig.safe_default()`
(`src.pc.config`)를 참고한 기본 factory를 지연 import로 구성하지만, 이
함수는 `NetworkBrowserCollector.__enter__`가 실제로 호출될 때만 실행되므로
정의/참조만으로는 Playwright가 시작되지 않는다 - 이번 단계 테스트는 항상
fake session_factory를 주입해 이 기본 경로 자체를 실행하지 않았다.
BrowserSession의 실제 속성(`__enter__`가 반환하는 self, `.context`,
Playwright `BrowserContext.new_page()`)만 사용했고 존재하지 않는 속성은
가정하지 않았다.

## 쿼리별 page 생성·종료 방식
`collect_query`는 매 호출마다 `self._session.context.new_page()`로 새
page를 만들어 `collect_network_query(page, job, per_query_limit,
collected_at=..., settle_ms=...)`에 넘기고, `try/finally`의 `finally`에서
`page.close()`를 best-effort(`try/except`)로 호출한다. `collect_network_query`
의 반환값은 `return`으로 이미 확정된 뒤 `finally`가 실행되므로, `close()`가
예외를 던져도(이미 닫힌 page, Target closed 등) 그 예외가 원래 반환값을
덮어쓰지 않는다(Python의 `try/finally` 의미상 `finally` 내부에서 예외를
삼켜야 `try`의 `return`이 보존된다는 점을 이용). 브라우저/context는 큐
전체에서 재시작하지 않으며, CAPTCHA/429/navigation_error가 발생해도 이
클래스 자체는 재시도나 context 재시작을 시도하지 않는다(안전 중단 판단은
여전히 `run_collection_plan`의 책임).

## fake 생명주기 테스트
`tests/test_pc_network_browser_collector.py`에 `FakeLifecyclePage`/
`FakeLifecycleContext`/`FakeLifecycleSession`(BrowserSession과 동일한
컨텍스트 매니저 + `.context` 계약만 흉내)을 추가하고,
`network_browser_collector.collect_network_query`를 모듈 속성 monkeypatch로
교체해 실제 응답 관찰 없이 호출 인자만 기록하도록 했다(요청서 8절 "함수
주입 또는 monkeypatch 가능한 작은 경계" 반영). 6개 필수 테스트: (1)
browser/context 공유(session_factory·session.__enter__ 1회만 호출) / (2)
쿼리별 page 생성(collect_query 3회 → new_page 3회) / (3) 쿼리별 page
종료(생성된 각 page가 정확히 1회 close) / (4) collect_network_query 전달
인자 검증(job/per_query_limit/collected_at/settle_ms/page) / (5) page close
best-effort(close() 예외가 나도 원래 결과 유지) / (6) context manager
teardown(정상 종료·collect_query 중 예외 발생 종료 모두 session `__exit__`
호출 + page close 보장).

## 신규/회귀 테스트 결과
- `python -m py_compile src/pc/network_pipeline.py src/pc/network_browser_collector.py tests/test_pc_network_pipeline.py tests/test_pc_network_browser_collector.py` PASS.
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(기존 7건 + navigation_error/should_continue 신규 5건).
- `tests/test_pc_network_browser_collector.py` 19건 전부 PASS(기존 13건 + 생명주기 신규 6건).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향, collect_pc_full 미변경 확인).

## UI·Excel·live 배선 여부
**전부 하지 않음.** `src/ui.py`/`src/exporter.py`/`src/pc/pipeline.py`/
`src/pc/safety.py`/기존 detail·list·basic·premium 경로 무수정. target_count
UI 추가 없음, Network/List 기본 엔진 전환 없음, Excel 저장 배선 없음, SAFE-1
UI 연결 없음. 실제 BrowserSession/Playwright/네이버 접속 없음, app.py/UI/
build/EXE 실행 없음.

## 다음 WIRE-2B-2 작업
- `NetworkBrowserCollector` + `run_collection_plan`을 fake 조합으로 엔드투엔드
  연결 검증(여전히 UI 미배선) - 이번 WIRE-2B-1은 두 계약을 각각 독립적으로만
  검증했고 아직 함께 실행해보지 않았다.
- navigation_error 발생 시 상위(향후 UI)가 사용자에게 어떤 메시지/재시도
  안내를 보여줄지 설계(이번 단계는 orchestrator가 중단만 하고 안내 문구는
  다루지 않음).
- UI에 `target_count` 필드 추가 + `_run_network_pipeline` worker에서
  `NetworkBrowserCollector`를 fake로 배선(여전히 live 아님)은 그 다음
  단계(WIRE-2B-2 이후)로 유지.

# 2026-07-14 ARCH-300C WIRE-2B-1B 기본 BrowserSession 어댑터 계약 검증(live 없음)

## 배경
WIRE-2B-1의 `NetworkBrowserCollector` 생명주기 테스트는 전부
`session_factory`를 직접 주입한 `FakeLifecycleSession`(BrowserSession과
`.context`/컨텍스트 매니저 계약만 흉내내며 `.page` 속성은 아예 없음) 기준
이었다. 실제 제품 배선 시 쓰일 `_default_session_factory()`가 실제
`BrowserSession`(browser/context와 함께 초기 page도 미리 만들어 두는 구조)과
정확히 호환되는지는 검증하지 않은 상태였다. 이번 단계는 이 간극만 채웠다 -
실제 Playwright는 여전히 실행하지 않고, `src.pc.browser_session.BrowserSession`
클래스 자체를 monkeypatch한 fake로만 검증했다.

## 변경 파일
- `src/pc/network_browser_collector.py`: `NetworkBrowserCollector.__enter__`에
  `_close_initial_page_if_present()` 호출 추가(신규 메서드), docstring에
  BrowserSession의 초기 page 처리 정책 명시. `browser_session.py`는 무수정.
- `tests/test_pc_network_browser_collector.py`: `FakeBrowserSessionLike`,
  `_run_with_fake_browser_session()` 헬퍼, 기본 factory 계약 검증 신규 5건
  추가.

## BrowserSession 실제 속성/생명주기(재확인, 임의 가정 없음)
`BrowserSession.__enter__()`는 `self._playwright`/`self.browser`/
`self.context`/`self.page`를 순서대로 만들며, **`self.page = self.context.
new_page()`로 초기 page 1개를 미리 만들어 둔다**(다른 호출부인
detail_scraper 등이 바로 `session.page.goto(...)`를 쓰는 용도). `__enter__`는
`self`(BrowserSession 인스턴스 자신)를 반환한다. `__exit__`는 `_teardown()`을
호출해 `self.context.close()` → `self.browser.close()` → `self._playwright.
stop()` 순서로(각각 best-effort try/except) 정리하고 `self.page`를 포함한
모든 속성을 `None`으로 되돌린다 - `context.close()`가 그 안의 모든 page(초기
page 포함)를 함께 정리하므로, 초기 page를 별도로 닫지 않아도 teardown
시점에는 결국 정리된다.

## _default_session_factory 호환 여부
호환된다. `_default_session_factory()`는 `BrowserSession(DiagnosticConfig.
safe_default())`를 반환하며, `NetworkBrowserCollector.__enter__`가 이를
`__enter__()`하면 실제 BrowserSession과 동일하게 `.context`/`.page`를 가진
객체가 반환된다. `NetworkBrowserCollector.collect_query`는 이미
`self._session.context.new_page()`만 사용하고 있어(WIRE-2B-1에서부터)
`.page`를 오용하는 버그는 애초에 없었다 - 다만 `.page`가 큐 실행 내내
방치되는 문제만 있었다.

## 초기 page 처리 정책
"가능한 방향 A"(BrowserSession을 그대로 감싸되 초기 page는 수집용으로
재사용하지 않고, 처리 정책을 명확히 함)를 채택했다.
`NetworkBrowserCollector.__enter__`에 `_close_initial_page_if_present()`를
추가해, session 진입 직후 `getattr(self._session, "page", None)`으로 초기
page를 확인하고 있으면 best-effort(`try/except`)로 즉시 닫는다. session
객체에 `.page` 속성이 없으면(WIRE-2B-1의 FakeLifecycleSession 등) 아무 것도
하지 않으므로 기존 19건(2B-1 시점)에는 영향이 없다. 닫기에 실패해도
BrowserSession._teardown()의 `context.close()`가 결국 정리하므로 안전하다
(이중 방어). `browser_session.py`는 이 정책을 위해 전혀 수정하지 않았다
(요청대로 대규모 변경 없이 `network_browser_collector.py` 내부에서만 처리).

## 쿼리별 page와 초기 page의 관계
초기 page(`session.page`)와 쿼리별 page(`session.context.new_page()`로 매
쿼리마다 새로 생성)는 서로 다른 객체이며 절대 섞이지 않는다. 초기 page는
`__enter__` 시점에 1회만 존재하고 즉시 닫히며, 이후 각 `collect_query` 호출은
독립적으로 새 page를 만들고 그 쿼리가 끝나면 닫는다 - 초기 page가 "누적"되는
경우는 구조적으로 없다(session_factory/session.__enter__ 자체가 큐 전체에서
1회만 호출되므로 초기 page도 정확히 1개만 생긴다).

## monkeypatch 기반 기본 factory 테스트 결과
`FakeBrowserSessionLike`(BrowserSession과 동일하게 `__init__(diagnostic_
config)`, `__enter__`에서 `.context`+`.page` 보유, `__exit__` 계약을 흉내)를
`src.pc.browser_session.BrowserSession` 모듈 속성에 monkeypatch해
`NetworkBrowserCollector(collected_at=...)`를 `session_factory` 없이(=기본
factory 경로) 실행했다. `tests/test_pc_network_browser_collector.py` 5건
신규 추가, 전부 PASS:
1. 기본 factory 경로: session_factory 미지정 시 `BrowserSession`(monkeypatch)이
   정확히 1회 생성·진입됨(실제 Playwright 없음).
2. 공유 context 접근: `session.context.new_page()`로 만든 page가 그대로
   `collect_network_query`에 전달됨(존재하지 않는 속성 가정 없음).
3. 초기 page 처리: `session.page`는 수집용으로 재사용되지 않고 `__enter__`에서
   정확히 1회 닫힘.
4. 쿼리별 page: `collect_query` 2회 → `new_page` 2회, 각 쿼리 page는 1회씩
   close, 초기 page와 완전히 분리됨(`session.page not in` 쿼리 page 목록).
5. teardown(기본 factory 경로): 정상 종료·`collect_query` 중 예외 발생 종료
   모두 `session.__exit__`가 정확히 1회 호출됨.

## 기존 회귀 결과
- `python -m py_compile src/pc/network_browser_collector.py tests/test_pc_network_browser_collector.py` PASS.
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(기존 19건 + 신규 5건).
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(무영향).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향).

## 추가 코드 변경 여부
`src/pc/network_browser_collector.py`에 `_close_initial_page_if_present()`
메서드 1개 추가 + `__enter__`에서 호출 1줄 + docstring 보강만 했다.
`src/pc/browser_session.py`는 요청대로 무수정. UI/target_count/Excel 저장
배선은 이번에도 하지 않았다. 실제 Playwright/네이버 접속 없음, app.py/UI/
build/EXE 실행 없음.

# 2026-07-14 ARCH-300C WIRE-2B-2 target_count UI + fake 제품 실행 배선(live 없음)

## 배경
WIRE-2B-1/1B로 orchestrator(navigation_error/should_continue)와 브라우저
생명주기(NetworkBrowserCollector) 계약이 모두 준비된 뒤, 이번 단계는 (1)
UI에 전체 목표 저장 개수(target_count)를 검색 조합당 상한(per_query_limit)과
분리해 추가하고, (2) UI 작업 큐를 run_collection_plan에 연결하는 신규 worker
`_run_network_pipeline`을 fake collector/orchestrator로만 검증했다. 기존
legacy(basic/premium, `_run_queue_pipeline`) 경로는 전혀 수정하지 않았고,
`start_crawl`의 기본 실행 경로도 여전히 legacy다. Excel 저장/SAFE-1 최종
통합(WIRE-2C)과 Network/List 기본 전환은 이번 범위에 없다.

## 변경 파일
- `src/ui.py`: `target_count_var` 신규 상태, `_parse_positive_int()`(모듈
  레벨 순수 검증 helper), `_build_global_target_count_section()`(신규 UI
  섹션), `_run_network_pipeline()`(신규 worker), `_network_stop_message()`
  (stop_reason별 문구 helper), `_NETWORK_STOP_REASON_MESSAGES` 상수,
  `NetworkBrowserCollector`/`run_collection_plan` import 추가.
  `limit_var` 기본값을 "300" → "30"으로 변경(§아래 회귀 위험 참고).
- 신규 `tests/test_ui_network_wiring.py`: fake collector_factory/orchestrator
  기반 10건.
- `PROJECT_STATE.md`: 이번 기록 append.

## target_count UI 구성
왼쪽 패널에 기존 "5. 검색 조합당 수집 상한"(row 8-9, `limit_var`) 섹션은
그대로 두고, 그 아래 "6. 전체 목표 저장 개수"(row 10-11, `target_count_var`,
기본값 "300")를 신규 추가했다. 설명 문구: "중복 제거 후 최종 저장할 목표
개수입니다. 업종·지역 및 검색 결과에 따라 목표 개수에 미달할 수 있습니다."
- "300개 보장" 등 과장 표현은 쓰지 않았다. 기존 왼쪽 패널 스크롤(
`CTkScrollableFrame`)/여백 상수(`_SECTION_TITLE_PADY`/`_SECTION_BODY_PADY`)
를 그대로 재사용했고, 기존 row 0~9는 전혀 건드리지 않았다(레이아웃 대규모
재작성 없음).

## per_query_limit/target_count 입력 검증
`_parse_positive_int(raw: str) -> int | None`(Tk 불필요, 모듈 레벨 순수
함수)를 신규 추가했다 - 빈 문자열/공백/비정수/0/음수는 전부 `None`을
반환하고 예외를 던지지 않는다. 두 필드(`limit_var`/`target_count_var`)에
동일한 규칙을 적용할 수 있는 공용 helper이며, `tests/test_ui_network_wiring.py`
에서 Tk 없이 직접 테스트했다. 이 helper를 실제 "수집 시작" 버튼 흐름에
연결하는 것은 Network/List가 기본 실행 경로가 되는 이후 단계(WIRE-2C+)의
몫으로 남겨뒀다(이번 단계는 legacy `start_crawl`을 수정하지 않았으므로,
legacy 경로의 기존 `limit` 검증 로직도 그대로다).

## _run_network_pipeline 인터페이스
`_run_network_pipeline(self, query_queue, per_query_limit, target_count,
output_path, *, collector_factory=NetworkBrowserCollector,
orchestrator=run_collection_plan) -> dict`. 책임(요청서 §5 그대로): (1)
`collected_at` 생성, (2) `collector_factory(collected_at=...)` 생성, (3)
`with collector:` 진입, (4) `run_collection_plan` 호출(jobs=query_queue,
per_query_limit, target_count, collect_query=collector.collect_query,
should_continue=lambda: not self.stop_event.is_set(),
on_security_block=self._note_security_block), (5) 결과를 로그(`[ui][network]`
접두사)/상태(`set_status`)에 반영 후 result dict를 그대로 반환. 이번
단계에서 Excel 저장, "저장했습니다" 문구, 최종 완료 모달은 구현하지
않았다 - `output_path`는 현재 로그에 참고용으로만 남긴다.

## collector/orchestrator 의존성 주입 방식
`collector_factory`/`orchestrator` 둘 다 키워드 인자로 노출하고, 기본값을
각각 `NetworkBrowserCollector`/`run_collection_plan` 함수·클래스 참조
그 자체로 직접 지정했다(지연 import 불필요 - `NetworkBrowserCollector`
정의/참조만으로는 Playwright가 시작되지 않는다는 계약이 WIRE-2B-1B에서
이미 보장되어 있고, `run_collection_plan`은 순수 함수라 참조 자체가
안전하다). 테스트는 항상 `FakeCollectorFactory`/fake orchestrator를
명시적으로 주입해 실제 기본값 경로를 실행하지 않았다.

## stop_reason별 UI 처리
`_NETWORK_STOP_REASON_MESSAGES` 상수(target_reached/security_blocked/
status_429/navigation_error/user_stopped/empty_jobs)와 `_network_stop_message()`
(queue_exhausted 전용 - 목표 미달 시 "목표 미달: final/target" 문구, 아니면
"완료" 문구)로 분기했다. navigation_error는 CAPTCHA/보안 확인과 다른 문구
("브라우저 페이지 오류로 수집을 중단했습니다.")를 쓰고,
`navigation_error_message`는 전체를 상태에 노출하지 않고 120자로 잘라 로그
에만 별도 라인으로 남긴다. 어떤 문구에도 "저장했습니다"는 없다(아직 저장
미연결).

## 기존 legacy 기본 경로 유지 여부
**유지됨(무수정).** `_run_queue_pipeline`/`_collect_premium_query`/
`_collect_premium_query_legacy`/`_collect_basic_query`는 전혀 건드리지
않았고, `start_crawl`의 스레드 타깃도 여전히 `self._run_queue_pipeline`이다
(`tests/test_ui_network_wiring.py`의 `check_legacy_path_untouched`가
`inspect.getsource(start_crawl)`로 이를 직접 확인). `_run_network_pipeline`은
아직 어떤 버튼에도 연결되지 않았다(신규 worker 함수로만 존재).

## 회귀 위험(명시적 고지)
`self.limit_var`(검색 조합당 수집 상한)의 **기본값을 "300" → "30"으로
변경**했다(요청서 §3 권장 기본값 반영: per_query_limit=30/target_count=300).
이 값은 legacy 경로(`_collect_premium_query`/`_collect_basic_query`)에서
여전히 유일한 "수집 개수" 입력으로 쓰이므로, 사용자가 값을 직접 입력하지
않고 기본값 그대로 수집을 시작하면 **legacy 경로의 기본 수집 결과 건수가
기존 300건 상당에서 30건 상당으로 줄어든다**(로직 변경은 아니고 화면
기본값만 변경). 화면 진입 시 기본으로 채워지는 숫자만 바뀐 것이며, 사용자가
직접 300으로 바꾸면 기존과 동일하게 동작한다.

## 신규 테스트 결과
`tests/test_ui_network_wiring.py` 10건 전부 PASS: 인자 전달 / collector
생명주기(factory·enter·exit 각 1회) / target_reached 상태·로그 반영 /
queue_exhausted 목표 미달 문구(50/300) / navigation_error(브라우저 오류
문구, 전체 메시지 미노출) / user_stopped 문구 / security_blocked(콜백 전달
확인 + 저장 문구 없음) / should_continue(stop_event 반영) / 입력 검증
helper(`_parse_positive_int`) / legacy 경로 무영향(inspect 기반 확인).

## 전체 회귀 결과
- `python -m py_compile src/ui.py tests/test_ui_network_wiring.py` PASS.
- `tests/test_ui_network_wiring.py` 10건 전부 PASS.
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(무영향).
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(무영향).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향, legacy premium/basic 경로 무변경 재확인).

## live/Excel/SAFE-1 배선 여부
**전부 하지 않음.** 실제 Playwright/네이버 접속 없음(fake collector_factory/
orchestrator만 사용), app.py/UI 창/build/EXE 실행 없음, 실제 Excel 저장 없음,
SAFE-1 최종 통합(부분 저장 연결) 없음. `_note_security_block`은 기존과 동일한
인스턴스 상태 기록 역할만 하며 저장 로직에는 연결되지 않았다.

## 다음 WIRE-2C 작업
- `_run_network_pipeline` 결과(rows)를 실제 `export_places_to_excel`에 연결
  하고, MERGED_COLUMNS 11컬럼·내부 필드(place_id/source_*) 비노출을 통합
  테스트로 재확인.
- 보안 차단/부분 저장 시 실제 Excel 저장 + "부분 저장됨" 안내를 이 경로에도
  연결(SAFE-1과 동일 수준으로).
- `_parse_positive_int`를 실제 "수집 시작" 버튼 흐름(Network/List 전용
  진입점)에 연결해 입력 검증이 실제로 수집을 차단하도록 배선.
- README/LEGAL_NOTICE/안내·정책 탭 정합성 수정은 여전히 WIRE-2D로 보류.

# 2026-07-14 ARCH-300C WIRE-2B-2A legacy 동작 보존 및 미배선 UI 정직 표시(live 없음)

## 배경
WIRE-2B-2에서 `limit_var`(검색 조합당 수집 상한) 기본값을 300 → 30으로
바꿨는데, `start_crawl`이 여전히 legacy `_run_queue_pipeline`을 실행하고
`limit_var`를 legacy의 유일한 "수집 개수" 입력으로 그대로 쓰기 때문에
이는 화면 기본값만 바뀐 게 아니라 **legacy 기본 수집량이 300건 상당에서
30건 상당으로 줄어드는 실질적 회귀**였다(WIRE-2B-2 보고에서 이미 고지한
문제). 또한 신규 `target_count_var` 입력 위젯이 화면에 그대로 노출되어
있었는데, `start_crawl`이 이 값을 전혀 읽지 않으므로 사용자가 값을 바꿔도
아무 효과가 없는데도 동작하는 옵션처럼 보이는 문제가 있었다. 이번 단계는
이 두 가지를 최소 수정으로 해결했다.

## 변경 파일
- `src/ui.py`: `_DEFAULT_PER_QUERY_LIMIT`을 "30" → "300"으로 복원(주석으로
  WIRE-2C 기본 엔진 전환 시 30으로 다시 바꿀 예정임을 명시).
  `_build_global_target_count_section()`에서 `target_count_entry`를
  `state="disabled"`로 생성하고 "새 수집 엔진 연결 후 적용됩니다." 안내
  라벨 추가. `_set_left_panel_state()`에 `target_count_entry`를 항상
  `disabled`로 재적용하는 방어 코드 추가(수집 시작/종료로 좌측 패널이
  `normal`로 풀려도 이 입력만은 계속 비활성 유지).
- `tests/test_ui_network_wiring.py`: 신규 검증 3건 추가(legacy 기본값 보존,
  target_count disabled+안내 문구, Network worker 무영향).
- `PROJECT_STATE.md`: 이번 기록 append.

## 1. limit_var 기본값 복원 결과
`_DEFAULT_PER_QUERY_LIMIT`을 "300"으로 되돌렸다(모듈 상단 주석에 "Network/
List가 기본 실행 경로가 된 뒤(WIRE-2C)에만 30으로 바꾼다"는 조건을 명시).
`self.limit_var`가 이 상수를 그대로 참조하므로 legacy 경로의 기본 수집량은
WIRE-2B-2 이전과 동일하게 복원됐다. "검색 조합당 수집 상한" 라벨과 신규
Network worker 구조(`_run_network_pipeline`)는 그대로 유지했다.

## 2. target_count disabled 처리 방식
`_build_global_target_count_section()`에서 `ctk.CTkEntry(..., state=
"disabled")`로 생성해 처음부터 비활성 상태로 만들었다. 추가로
`_set_left_panel_state(state)`(수집 시작 시 `disabled`, 종료 시 `normal`로
좌측 패널 전체를 일괄 전환하는 기존 메서드)가 이 위젯만은 항상
`disabled`로 재적용하도록 방어 코드를 넣었다 - 그렇지 않으면 수집 완료 후
좌측 패널이 `normal`로 풀리면서 target_count 입력도 함께 활성화되어
버그가 재발했을 것이다. UI 레이아웃(섹션 순서/여백/스크롤)은 전혀 다시
만들지 않았다.

## 3. 안내 문구
target_count 입력 아래 기존 설명(중복 제거 후 목표 개수, 미달 가능성) 다음
줄에 "새 수집 엔진 연결 후 적용됩니다."를 1줄만 추가했다(긴 설명 추가하지
않음).

## 4. _run_network_pipeline 영향 여부
**영향 없음.** `_run_network_pipeline`은 여전히 호출자가 전달한
`target_count` 값을 그대로 `run_collection_plan`에 넘긴다 - UI에서
`target_count_entry`가 disabled인 것은 화면(legacy 진입점)에만 적용되는
정책이며, 이 worker의 시그니처·동작·fake wiring 테스트 구조는 전혀
건드리지 않았다(`check_run_network_pipeline_ignores_target_count_disabled_state`
로 target_count=300이 orchestrator에 그대로 전달됨을 재확인).

## 신규/회귀 테스트 결과
- `python -m py_compile src/ui.py tests/test_ui_network_wiring.py` PASS.
- `tests/test_ui_network_wiring.py` 13건 전부 PASS(기존 10건 + 신규 3건:
  legacy 기본값 보존 / target_count disabled+안내 문구 존재(소스 기반 확인,
  `check_legacy_path_untouched`와 동일한 `inspect.getsource` 방식) / Network
  worker가 target_count=300을 그대로 orchestrator에 전달).
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(무영향).
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(무영향).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향).

## live/Excel/Playwright/네이버/app.py/UI/build 실행 여부
**전부 실행 안 함.** 실제 Tk 위젯 생성/렌더링도 하지 않았다(신규 disabled
검증은 `inspect.getsource` 기반 소스 확인만 사용, 실제 CTkEntry 인스턴스를
만들지 않음).

## 다음 단계
WIRE-2C에서 Network/List를 기본 실행 경로로 전환할 때 함께 처리할 항목(변경
없음, WIRE-2B-2 기록과 동일): `_DEFAULT_PER_QUERY_LIMIT`을 30으로 재변경,
`target_count_entry` 활성화 및 `start_crawl` 실제 연결, `_run_network_pipeline`
결과의 Excel 저장/SAFE-1 통합, README/LEGAL_NOTICE/안내·정책 탭 정합성
수정(WIRE-2D).

# 2026-07-14 ARCH-300C WIRE-2C-1 Excel 저장·부분 저장 통합(live 없음, 기본 엔진 전환 없음)

## 배경
`_run_network_pipeline`이 orchestrator 결과를 로그/상태에만 반영하고 실제
Excel 저장은 하지 않던 상태(WIRE-2B-2/2A)에서, 이번 단계는 `export_places_to_excel`
을 단일 저장 지점으로 연결했다. 정상 완료뿐 아니라 CAPTCHA/429/사용자
중단/브라우저 오류로 중단된 경우에도 그때까지 수집된 rows를 보존해야 한다는
원칙(SAFE-1과 동일)을 Network/List 경로에도 적용했다. `start_crawl` 기본
실행 경로는 여전히 legacy이고, target_count 입력은 여전히 disabled이며,
`limit_var` 기본값도 300 그대로다 - 기본 엔진 전환은 WIRE-2C-2로 보류했다.

## 변경 파일
- `src/ui.py`: `_run_network_pipeline`에 `excel_exporter=export_places_to_excel`
  의존성 주입 인자 추가, collector 종료 후 신규 `_export_network_result()`
  단일 저장 지점 호출, `_network_stop_message()`를 저장 결과(exported/
  export_error) 반영하도록 재작성, 이제 쓰이지 않는 `_NETWORK_STOP_REASON_MESSAGES`
  상수 제거.
- `tests/test_ui_network_wiring.py`: `FakeExporter`/`_fake_rows` 추가, 기존
  테스트를 rows가 실제로 채워지도록 갱신하고 새 문구·저장 메타 검증 추가,
  신규 검증 6건(저장 인자/이중 저장 방지/0건/exporter 예외 등) 추가.
- 신규 `tests/test_ui_network_export.py`: 실제 `export_places_to_excel`을
  `tempfile.TemporaryDirectory()` 안에서 실행하는 통합 테스트 7건.
- `PROJECT_STATE.md`: 이번 기록 append.

## _run_network_pipeline → export_places_to_excel 연결
흐름(요청서 §3 그대로): collector context 진입 → `run_collection_plan` 실행 →
collector context 종료(`with` 블록 탈출, 브라우저/session/context 정리 완료) →
`result["rows"]` 확인 → rows가 있으면 `excel_exporter(rows, [], [],
output_path)` 실행 → 저장 성공/실패 메타를 `result`에 추가 → 로그/상태 갱신 →
`result` 반환. Excel 저장은 브라우저 자원이 전혀 남아있지 않은 상태에서만
수행되도록 `with collector_factory(...) as collector:` 블록 **밖**에서
호출한다(브라우저 정리 실패와 파일 저장 실패는 원인이 다르므로 같은 try에
섞지 않는다는 요청서 §3 원칙을 그대로 반영).

## 단일 저장 지점 및 이중 저장 방지
저장은 신규 `_export_network_result()` 한 곳에서만 발생하며, `run_collection_plan`
호출 시 `on_partial_save`를 전달하지 않는다(기존에도 전달하지 않았음 -
`check_no_double_save_for_security_and_429` 테스트로 `calls[0].get(
"on_partial_save") is None`을 직접 확인). 따라서 security_blocked/status_429
에서 orchestrator 내부의 부분 저장 콜백과 이 worker의 종료 후 저장이 겹쳐
두 번 저장되는 경로 자체가 존재하지 않는다 - 두 stop_reason 모두
`FakeExporter.calls`가 정확히 1임을 테스트로 재확인했다.

## stop_reason별 저장 정책
요청서 §5 그대로: `target_reached`/`queue_exhausted`/`security_blocked`/
`status_429`/`navigation_error`/`user_stopped`는 rows가 1개 이상이면 전부
저장 대상이다(이전 쿼리까지의 정상 결과 보존). `empty_jobs`와, 위 stop_reason
이어도 rows가 실제로 비어 있는 경우(navigation_error가 첫 쿼리에서 발생,
security_blocked인데 그 전까지 아무 것도 못 모음, 정상 실행했지만 최종
0건 등)는 전부 저장하지 않는다 - `rows` 리스트 자체의 비어있음만으로 이
분기를 결정하므로 stop_reason을 개별로 화이트리스트/블랙리스트하지 않는
단일 조건(`if not rows:`)으로 요청서의 두 목록을 그대로 만족시킨다.

## 0건 처리
`_export_network_result`에서 `rows`가 비어 있으면 `excel_exporter`를 아예
호출하지 않는다(→ `export_places_to_excel`이 호출되지 않으므로 파일도
생성되지 않음 - `output_file.parent.mkdir()`조차 실행되지 않는다). 반환
메타는 `exported=False`, `export_path=""`, `export_error=False`,
`export_error_message=""`이며 상태 문구는 "저장할 결과가 없습니다."이다.
`check_zero_rows_no_export_no_file_creation`(fake exporter)과
`check_zero_rows_no_file_created`(실제 exporter, 임시 디렉터리)로 이중 확인했다.

## exporter 실패 처리
`excel_exporter` 호출을 `try/except Exception`으로 감싸고, 실패 시
`exported=False`, `export_error=True`, `export_error_message`에
`f"{type(exc).__name__}: {exc}"`를 200자로 잘라 기록한다. 사용자 상태
문구는 항상 "수집 결과를 Excel로 저장하지 못했습니다."로 고정되며(어떤
stop_reason이었든 우선순위 최상위), 전체 traceback이나 경로는 상태 라벨에
노출하지 않고 로그에만 짧게 남긴다. `_network_stop_message`가 `export_error`
를 최우선으로 검사하므로, 저장이 실패해도 "완료/저장했습니다" 문구가 잘못
표시될 수 없다(`check_exporter_exception_marks_export_error`로 확인).

## result export 메타
`_export_network_result`가 `result = dict(result)`로 orchestrator 원본을
복사한 뒤 `exported`/`export_path`/`export_error`/`export_error_message`
4개 필드를 추가해 반환한다(요청서 §7 권장 구조 그대로). 원본 dict는
변형하지 않는다.

## Excel 11컬럼·내부 메타 미노출 검증
`export_places_to_excel`/`MERGED_COLUMNS`는 무수정으로 재사용했다(시그니처:
`export_places_to_excel(merged_data, mobile_data, pc_data, output_path) ->
str`, 시트명 "통합_결과"/"원본_모바일"/"원본_PC"). Network/List row(제품
11컬럼 + place_id/source_city/source_district/source_subregion/
source_layer/source_query 내부 필드 포함)를 그대로 `merged_data` 인자로
넘겨도, 기존 `_rows_with_columns()`의 `{column: row.get(column, "") for
column in columns}` 투영이 내부 필드를 자동으로 걸러낸다 - exporter를
전혀 건드리지 않고도 미노출이 보장됨을 `tests/test_ui_network_export.py`의
`check_internal_meta_fields_not_in_excel`이 실제 저장된 헤더를 읽어 확인했다.

## 기존 3시트 구조 유지 여부
**유지됨.** mobile/pc 인자에 항상 `[]`를 전달하므로 `원본_모바일`/`원본_PC`
시트는 헤더만 있고 데이터 행이 0개인 상태로 그대로 생성된다(3시트 구조
자체는 변경 없음) - `check_empty_original_sheets`로 실제 워크북을 열어
`max_row == 1`(헤더만)임을 확인했다.

## 신규 테스트 결과
- `tests/test_ui_network_wiring.py` 19건 전부 PASS(fake exporter 기반):
  인자 전달(rows=0→exporter 미호출 확인 포함) / collector 생명주기 / 저장
  인자 정확성(merged=rows/mobile=[]/pc=[]/output_path) / target_reached
  저장 성공 문구("N개를 저장했습니다.") / queue_exhausted 미달 저장 문구 /
  navigation_error 부분 저장(CAPTCHA 문구 금지 재확인) / user_stopped 부분
  저장 / security_blocked 부분 저장(on_security_block 유지 확인) /
  status_429 부분 저장 / 이중 저장 방지(on_partial_save 미사용 + exporter
  1회) / rows 0건(exporter 미호출) / empty_jobs(exporter 미호출) / exporter
  예외(exported=False/export_error=True, 성공 문구 없음) / should_continue /
  입력 검증 helper / legacy 경로 무영향 / legacy 기본값 보존 / target_count
  disabled+안내 문구 / Network worker가 target_count 그대로 전달.
- `tests/test_ui_network_export.py`(신규, 실제 exporter+tempfile) 7건 전부
  PASS: 파일 생성 / 최종 행 수=final_count 일치 / 헤더=MERGED_COLUMNS 11개
  정확히 일치 / 내부 메타(place_id/source_*) 헤더 미노출 / 원본_모바일·
  원본_PC 빈 시트(헤더만) / target trim된 rows 수만큼 정확히 저장 / 0건 시
  파일 미생성. 생성된 임시 xlsx는 `tempfile.TemporaryDirectory()` 컨텍스트
  종료 시 자동 삭제됨.

## 전체 회귀 결과
- `python -m py_compile src/ui.py tests/test_ui_network_wiring.py tests/test_ui_network_export.py` PASS.
- `tests/test_ui_network_wiring.py` 19건 전부 PASS.
- `tests/test_ui_network_export.py` 7건 전부 PASS.
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(무영향, `network_pipeline.py` 무수정).
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(무영향, `network_browser_collector.py` 무수정).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향, legacy premium/basic 경로 무변경 재확인).

## legacy 기본 경로·UI 상태 유지 여부
**전부 유지됨(무수정).** `start_crawl` 기본 실행 경로는 여전히
`self._run_queue_pipeline`(legacy). `_DEFAULT_PER_QUERY_LIMIT`/`limit_var`
기본값 "300" 그대로. `target_count_entry`는 여전히 `disabled` + "새 수집
엔진 연결 후 적용됩니다." 안내 유지. `_run_queue_pipeline`/`_collect_premium_query`
/`_collect_basic_query`/basic·premium 엔진은 무수정.

## live/Playwright/네이버/app.py/UI/build/EXE 실행 여부
**전부 실행 안 함.** `tests/test_ui_network_export.py`가 실제 `export_places_to_excel`
과 `openpyxl.load_workbook`으로 파일 IO를 수행하지만, 이는 로컬 임시 디렉터리
(`tempfile.TemporaryDirectory()`) 안에서만 발생하고 collector/orchestrator는
여전히 fake다 - 실제 Playwright/브라우저/네이버 접속은 전혀 없다. app.py/UI
창/build/EXE 실행도 없다.

## 다음 WIRE-2C-2 작업
- `target_count_entry` 활성화 + `start_crawl`에서 `_parse_positive_int`로
  실제 파싱해 Network worker에 연결.
- `_DEFAULT_PER_QUERY_LIMIT`을 30으로 재변경(Network/List가 기본 경로가
  되는 시점과 함께).
- `start_crawl`의 기본 실행 경로를 Network/List로 전환하는 결정 및 실제
  배선(legacy는 fallback으로 보존).
- README/LEGAL_NOTICE/안내·정책 탭 정합성 수정(WIRE-2D, POLICY-ALIGN-1
  감사 결과 반영) - 기본 엔진이 실제로 바뀌기 전까지는 보류 유지.

---

# 2026-07-14 ARCH-300C WIRE-2C-2 Network/List 기본 엔진 전환(live 없음)

## 배경
WIRE-2C-1까지는 `_run_network_pipeline`(Excel 저장 포함)이 완성됐지만
`start_crawl`은 여전히 legacy(`_run_queue_pipeline`, basic/premium)를
실행했고 `limit_var` 기본값은 300, `target_count_entry`는 disabled였다.
이번 단계는 Network/List를 실제 기본 실행 경로로 전환하고, per_query_limit/
target_count를 `start_crawl`에서 실제로 검증해 Network worker thread에
연결했다. legacy 경로는 삭제하지 않고 내부 상수로만 되돌릴 수 있는 롤백
경로로 보존했다.

## 변경 파일
- `src/ui.py`:
  - `_DEFAULT_PER_QUERY_LIMIT`을 "30"으로 재변경(target_count "300" 유지),
    신규 `_DEFAULT_COLLECTION_ENGINE = "network"` 내부 상수 추가(UI 노출 없음).
  - `_build_global_target_count_section`: `target_count_entry`의
    `state="disabled"`와 "새 수집 엔진 연결 후 적용됩니다." 안내 문구 제거(활성화).
  - `_build_filter_section`: `new_open_checkbox`에 `state="disabled"` 추가,
    설명 문구를 "현재 기본 수집에서는 새로오픈 필터를 지원하지 않습니다."로 교체.
  - `_set_left_panel_state`: target_count_entry 강제 disabled 방어 코드 제거,
    new_open_checkbox 강제 disabled 방어 코드로 교체(좌측 패널이 normal로
    복구돼도 새로오픈 체크박스만은 계속 disabled 유지).
  - `start_crawl`을 얇은 dispatcher로 재작성 - `_DEFAULT_COLLECTION_ENGINE`
    값에 따라 신규 `_start_network_crawl`(기본값) 또는 `_start_legacy_crawl`
    (WIRE-2C-1까지의 start_crawl 본문을 그대로 옮긴 내부 롤백 경로, 검증
    순서/동작 무변경)로 위임.
  - 신규 `_start_network_crawl`: 키워드/per_query_limit(`_parse_positive_int`)/
    target_count(`_parse_positive_int`)/저장 경로/지역 선택을 검증한 뒤
    새로오픈 필터를 False로 정규화하고, `make_timestamped_output_path`로
    저장 경로를 확정하고, `stop_event.clear()` → 실행 중 UI 상태 적용 →
    `_run_network_pipeline_worker`를 대상으로 하는 Thread를 시작한다.
  - 신규 `_run_network_pipeline_worker`: `_run_network_pipeline` 호출을
    try/except로 감싸 collector/orchestrator의 예상 밖 예외만 방어(짧은
    오류 로그 + "수집 중 오류가 발생했습니다." 상태 문구)하고, finally에서
    기존 `set_running(False)` 복구 helper를 그대로 재사용한다. exporter
    실패는 `_run_network_pipeline`/`_export_network_result`가 이미
    처리하므로 여기서 다시 다루지 않는다(이중 처리 금지).
- `tests/test_ui_network_wiring.py`: 구조 변경으로 깨진 4개 테스트 갱신
  - `check_legacy_path_untouched`: `_start_legacy_crawl` 소스가 여전히
    `_run_queue_pipeline`만 호출하는지, 기본 엔진이 "network"인지로 검증
    방식 갱신.
  - `check_legacy_default_per_query_limit_preserved` →
    `check_default_values_for_network_engine`으로 개명, 기대값을
    PER_QUERY_LIMIT=30/TARGET_COUNT=300으로 갱신.
  - `check_target_count_input_disabled_with_guidance` →
    `check_target_count_input_enabled_no_stale_guidance`로 개명, disabled/
    안내 문구가 없어야 한다는 반대 방향 검증으로 갱신.
  - `check_run_network_pipeline_ignores_target_count_disabled_state` →
    `check_run_network_pipeline_passes_target_count_through`로 개명(설명
    갱신, `_run_network_pipeline` 자체의 target_count 전달 계약은 무변경).
- 신규 `tests/test_ui_network_start.py`: `start_crawl`/`_start_network_crawl`/
  `_start_legacy_crawl`/`_run_network_pipeline_worker`를 검증하는 12개
  standalone 테스트(§신규 테스트 결과).
- `PROJECT_STATE.md`: 이번 기록 append.

## 기본 엔진 전환 방식
`_DEFAULT_COLLECTION_ENGINE`(모듈 상수, UI 노출 없음)이 "network"(기본값)면
`_start_network_crawl`, "legacy"면 `_start_legacy_crawl`을 실행한다.
`start_crawl` 자체는 이 두 갈래로 위임만 하는 얇은 dispatcher이고
button command 시그니처(`self`, 인자 없음)는 그대로다. legacy 경로는
코드를 전혀 수정하지 않고 그대로 옮겼으므로(`_start_legacy_crawl`) 기존
검증 순서·동작에 회귀가 없다 - `_DEFAULT_COLLECTION_ENGINE`을 "legacy"로
바꾸는 것만으로 되돌릴 수 있는 내부 롤백 지점이다.

## per_query_limit/target_count 기본값과 검증
`_DEFAULT_PER_QUERY_LIMIT`="30", `_DEFAULT_TARGET_COUNT`="300". Network가
기본 엔진이 되면서 WIRE-2B-2A에서 300으로 되돌렸던 이유(legacy가
limit_var를 유일한 수집 개수 입력으로 그대로 쓰던 문제)가 해소되어 30을
다시 적용했다. `_start_network_crawl`이 `_parse_positive_int`로 두 값을
각각 검증하고, 비정수/0/음수면 로그+안내 후 즉시 실행을 차단한다(Thread
생성 자체가 발생하지 않음 - `check_invalid_per_query_limit_blocks_execution`/
`check_invalid_target_count_blocks_execution`으로 확인). target_count <
per_query_limit, per_query_limit < target_count 조합 모두 허용하며(서로
독립된 양의 정수), 잘못된 값을 임의 기본값으로 보정해 실행하지 않는다.

## start_crawl → Network worker 흐름
요청서 §5 그대로: 입력 검증 → `_build_collection_queries()`로 query_queue
생성(0건이면 차단) → 새로오픈 필터 False 정규화 → 저장 경로 확정
(`make_timestamped_output_path`) → `stop_event.clear()` → `set_running(True)`
등 실행 중 UI 상태 적용 → `_run_network_pipeline_worker`를 target으로 하는
Thread 시작(`query_queue, per_query_limit, target_count, output_path` 전달).
저장 폴더 생성은 별도로 하지 않는다 - `export_places_to_excel`이 이미
`output_file.parent.mkdir()`을 수행하고, rows가 0건이면 저장 자체를
하지 않으므로(§WIRE-2C-1) 미리 폴더를 만들어 두면 오히려 "저장할 결과가
없습니다" 상황에서도 빈 폴더가 남는 부작용이 생길 수 있어 만들지 않는다.

## worker 정상·예외 종료 UI 복구
`_run_network_pipeline_worker`가 `_run_network_pipeline` 호출을
try/except/finally로 감싼다. try에서 잡는 예외는 collector/orchestrator가
결과 dict조차 반환하지 못한 예상 밖 오류뿐이다(exporter 실패는 이미
result 메타로 처리되므로 여기서 다시 다루지 않음 - 이중 처리 금지).
예외 발생 시 로그에는 "예상하지 못한 오류: ..."만 짧게 남기고 상태에는
"수집 중 오류가 발생했습니다."만 표시하며 "저장했습니다/저장 완료" 같은
성공 문구는 어떤 경우에도 나오지 않는다. finally는 정상/예외 종료 양쪽
모두에서 기존 `set_running(False)` 복구 helper(내부적으로
`self.after(0, ...)`로 `btn_start`/좌측 패널 상태를 되돌림)를 정확히 1회
호출한다 - `_run_queue_pipeline`의 finally와 동일한 원칙이다.

## 새로오픈 필터 처리
Network/List 매핑은 새로오픈여부를 신뢰성 있게 제공하지 않으므로,
`new_open_checkbox`를 생성 시점부터 `state="disabled"`로 두고 설명 문구를
"현재 기본 수집에서는 새로오픈 필터를 지원하지 않습니다."로 바꿨다.
`_set_left_panel_state`가 좌측 패널을 normal로 복구할 때도
new_open_checkbox만은 항상 disabled로 재설정하는 방어 코드를 추가해,
체크된 상태로 disabled되어 "적용된 것"으로 오해하는 상황을 막는다.
`_start_network_crawl`은 실행 직전에 `new_open_only_var.set(False)`로
한 번 더 정규화한다(체크박스 초기값도 항상 False). legacy 변수/필터 코드,
상세 클릭 fallback은 전혀 건드리지 않았고, 확인되지 않은 목록 필드로
새로오픈을 추정하는 로직도 추가하지 않았다.

## target_count UI 활성화
`target_count_entry`에서 `state="disabled"`와 낡은 안내 문구를 제거했다.
`_set_left_panel_state`에는 더 이상 target_count_entry 관련 특례가 없으므로
다른 입력(Entry)과 동일하게 수집 시작 시 disabled, 완료 후 normal로
자연스럽게 전환된다(source 검사로 확인 - `check_target_count_entry_enabled_and_restored_normal`).
새로오픈 체크박스만 유일하게 이 일반 규칙에서 예외로 남는다.

## legacy 롤백 경로
`_run_queue_pipeline`/`_collect_premium_query`/`_collect_basic_query`/
`_collect_premium_query_legacy`는 전부 무수정 보존됐다. `_start_legacy_crawl`
은 WIRE-2C-1까지의 start_crawl 본문을 그대로 옮긴 것이라 검증 순서·동작에
변화가 없다. `_DEFAULT_COLLECTION_ENGINE`을 "legacy"로 바꾸면 `start_crawl`
이 다시 `_start_legacy_crawl`(→ `_run_queue_pipeline`)로 위임한다는 것을
`check_legacy_rollback_path_reachable_via_internal_constant`가 fake
threading으로 실제 legacy crawler 실행 없이 확인했다. 사용자 화면에는
엔진 선택 UI를 노출하지 않는다.

## 신규 테스트 결과
- `tests/test_ui_network_start.py`(신규) 12건 전부 PASS: 기본 상수(30/300/
  network) / target_count 활성화(disabled·낡은 안내 문구 없음 + 좌측 패널
  특례 없음) / 정상 start_crawl(Network worker 선택, query_queue/
  per_query_limit=30/target_count=300/output_path 정확 전달, legacy worker
  미호출) / per_query_limit 오류(0/-5/abc) 실행 차단 / target_count 오류
  (0/-5/abc) 실행 차단 / query_queue 0건 실행 차단 / stop_event 사전
  clear() / set_running(True)가 thread.start()보다 먼저 호출(순서 확인) /
  worker 정상 종료 시 set_running(False) 1회 호출 / worker 예상 밖 예외 시
  UI 복구 + 성공 문구 없음 + 짧은 오류 안내 / 새로오픈 필터 disabled+안내+
  강제 유지+False 정규화 / legacy 롤백 경로(내부 상수 전환 시 실제
  legacy crawler 실행 없이 `_run_queue_pipeline` 선택 확인).
- `tests/test_ui_network_wiring.py` 갱신된 4건 포함 19건 전부 PASS(나머지
  15건은 WIRE-2C-1 그대로 무변경 재확인).

## 전체 회귀 결과
- `python -m py_compile src/ui.py tests/test_ui_network_wiring.py tests/test_ui_network_export.py tests/test_ui_network_start.py` PASS.
- `tests/test_ui_network_start.py` 12건 전부 PASS.
- `tests/test_ui_network_wiring.py` 19건 전부 PASS.
- `tests/test_ui_network_export.py` 7건 전부 PASS(무수정 파일, 무영향 재확인).
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(무영향, `network_pipeline.py` 무수정).
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(무영향, `network_browser_collector.py` 무수정).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향, legacy premium/basic 경로 무변경 재확인).

## live/Playwright/네이버/app.py/UI/build/EXE 실행 여부
**전부 실행 안 함.** 모든 신규/갱신 테스트는 `threading.Thread`를
`ui.threading` 네임스페이스 안에서만 fake로 교체(stdlib `threading` 모듈
자체는 무수정)하고, `_run_network_pipeline`/collector/orchestrator는
여전히 fake다. 실제 Playwright/브라우저/네이버 접속, app.py 실행, 실제
Tk 창, build/EXE 실행은 전혀 없다.

## 다음 WIRE-2D 작업(수정 예정 문서)
- README.md, LEGAL_NOTICE.md, 안내·정책 탭: 기본 엔진이 Network/List로
  바뀌었고 새로오픈 필터가 비활성화됐다는 사실을 반영(POLICY-ALIGN-1 감사
  결과 반영). 이번 WIRE-2C-2에서는 문서를 수정하지 않았으므로, 지금
  시점에는 문서와 실제 동작이 잠시 어긋나 있다 - WIRE-2D 완료 전까지는
  git add/commit을 하지 않고 WIRE-2C-2 + WIRE-2D를 한 커밋으로 묶을 예정.

---

# 2026-07-14 ARCH-300C WIRE-2D README·법적 고지·안내 정책 정합성(live 없음, 코드 동작 무변경)

## 배경
WIRE-2C-2까지 Network/List가 실제 기본 실행 경로가 됐지만, README/
LEGAL_NOTICE/안내·정책 탭은 여전히 옛 `빠른 수집(모바일)`/`상세 수집(PC)`
수집모드 라디오 기준으로 작성되어 있었다(POLICY-ALIGN-1 감사에서 이미
지적된 정합성 문제). 이번 단계는 코드 동작을 전혀 바꾸지 않고, 문서와
UI 안내 문구를 현재 Network/List 기본 엔진의 실제 동작(전역 dedup, 목표
미달 가능, CAPTCHA/429 비우회+부분 저장, 0건 미생성, 새로오픈 필터 미지원,
직접 HTTP 호출 없음)에 맞춰 정정했다.

## 변경 파일
- `README.md`: 섹션 1(핵심 방향)~3(결과물)을 Network/List 흐름 기준으로
  재작성(옛 수집모드 라디오/basic·premium 설명 제거), 신규 섹션 "4. 수집
  개수와 중단·저장 정책" 추가(per_query_limit=30/target_count=300 구분,
  stop_reason별 저장 표, 0건 미생성, exporter 실패 시 저장 안 될 수 있음),
  프로젝트 구조에 `network_*.py` 3개 파일 추가 및 레거시 파일 "내부 롤백
  경로" 표기, 실행 방법/주의사항 문구 갱신(수집모드 선택 문구 제거,
  target_count/새로오픈 비활성화 안내 추가), "공식 네이버 제품·제휴 제품
  아님" 고지 추가, 저장 경로 타임스탬프 형식을 실제 코드
  (`make_timestamped_output_path`, `%Y%m%d_%H%M`, 초 단위 없음)에 맞게 수정.
- `LEGAL_NOTICE.md`: 기존 날짜 기반 append-only 구조(4번 2026-06-04→5번
  2026-07-06)를 그대로 유지하며 신규 "6. Network/List 경로 반영
  (2026-07-14 추가)" 섹션을 추가하고, 5번 섹션 끝에 "제5호(수집 규모)는
  6번으로 갱신됨" 승계 포인터를 추가. 과거 섹션(4번의 "10건 이내" 등)은
  역사적 기록으로 전혀 수정하지 않았다(§아래 "낡은 표현 처리 방식" 참고).
- `src/ui.py`: `_build_policy_tab()`만 수정 - 기존 placeholder 5개 카드 중
  "수집 기준 안내"/"보안 확인 및 부분 저장 안내"/"사용자 주의사항"을 실제
  문구가 있는 "1. 수집 방식"/"2. 수집 개수"/"3. 안전 중단"/"4. 데이터 제공
  범위"/"5. 이용 책임" 5개 카드로 교체하고, "유지보수/A/S 안내"·"라이선스
  안내"는 기존과 동일하게 placeholder로 유지(개발 마지막 단계 별도 태스크,
  이번 범위 아님). 기존 카드·스크롤 레이아웃 구조는 그대로 재사용했고,
  다른 메서드는 전혀 건드리지 않았다.
- 신규 `tests/test_ui_policy_text.py`: README/LEGAL_NOTICE/안내·정책 탭
  문구를 텍스트/소스 기반으로 검증하는 13개 테스트(§아래).
- `PROJECT_STATE.md`: 이번 기록 append.

## 낡은 표현 처리 방식(사용자 확인 완료)
work order는 LEGAL_NOTICE의 "10건 이내" 표현 "제거"를 요청했지만, 이
프로젝트의 전역 문서화 규칙(`documentation.md`)은 "변경 이력을 누적하는
문서는 날짜 기반으로 새 섹션만 추가하고 과거 기록은 수정하지 않는다"고
명시하며, LEGAL_NOTICE.md는 이미 스스로 이 append-only 패턴(4→5 섹션 승계)
을 따르고 있어 규칙 충돌이 있었다. AskUserQuestion으로 확인한 결과 "과거
섹션 보존 + 최신 섹션만 검증"으로 진행하기로 확정했다 - 4번 섹션의 "10건
이내"는 역사적 기록으로 그대로 남기고, 최신 섹션(6번)에는 그 표현이 전혀
등장하지 않으며 "위 제4항에 기재된 과거의 소량 기준은 더 이상 적용되지
않습니다"로 대체 서술했다. `check_legal_notice_current_section_no_stale_limit`
테스트가 "마지막 '## ' 섹션"만 잘라 그 안에 "10건 이내"가 없는지 확인한다.

## README 주요 변경
- 섹션 1: 지역+키워드 선택 → 검색 조합 생성 → 브라우저가 검색 과정에서
  정상적으로 수신한 응답 처리 → Excel 저장 흐름으로 재작성. "별도의 HTTP
  클라이언트로 네이버 엔드포인트를 직접 호출하는 구조는 사용하지 않습니다"
  명시. 레거시 엔진은 "내부 롤백 경로로 보존되어 있으나 현재 기본 실행
  경로는 아님"으로 한 줄 언급만 유지(더 이상 선택 가능한 기능처럼 서술하지
  않음).
- 섹션 2: 11컬럼을 단일 세트로 통합(빠른/상세 이원화 서술 제거).
  업체명/업종/리뷰수/주소/대표전화/플레이스 URL/수집일은 검색 목록 응답
  값 그대로(값 없으면 빈칸), 홈페이지/인스타/블로그는 도메인 분류 값(없으면
  빈칸), **새로오픈여부는 현재 항상 빈칸**임을 명시(실제 코드
  `network_list_scraper._map_item_to_row`의 `"새로오픈여부": ""` 하드코딩
  확인 후 기술).
- 섹션 3: 0건이면 Excel 파일을 만들지 않는다는 문장을 맨 앞에 명시, 저장
  경로 타임스탬프 형식 수정, `원본_모바일`/`원본_PC`가 "항상 헤더만 있는
  빈 시트"임을 명시(exporter에 mobile/pc 인자로 항상 빈 리스트가 전달됨).
- 신규 섹션 4: per_query_limit(30)/target_count(300) 표 구분, stop_reason별
  저장 정책 표(target_reached/queue_exhausted/security_blocked/status_429/
  navigation_error/user_stopped 전부 "결과 있으면 저장"), "항상 부분
  저장된다"는 표현은 쓰지 않고 "결과가 1건 이상 있을 때만 저장" 명시,
  exporter 자체 오류 시 저장되지 않을 수 있음을 과장 없이 안내.

## LEGAL_NOTICE 주요 변경
신규 섹션 6(Network/List 경로 반영): 목록 응답 관찰 방식 + 직접 HTTP 호출
없음, per_query_limit/target_count 기준 수집 규모(과거 "10건 이내" 기준
대체), CAPTCHA/429 비우회, 데이터 정확성·완전성 미보장, "네이버 공식·제휴
제품 아님", 사용자 준수 의무. 기존 섹션 1~5(공개정보 수집 원칙, 개인정보
미수집, 면책조항, 과거 V1/PC 경로 기록)는 전혀 수정하지 않았다. 법적
확정/보장 표현("합법을 보장합니다" 등)은 기존에도 없었고 이번에도 추가하지
않았다(`check_legal_notice_no_legal_guarantee_wording`로 확인).

## 안내·정책 탭 변경
`_build_policy_tab()`의 placeholder 5개 중 3개를 실제 문구가 있는 5개
섹션(수집 방식/수집 개수/안전 중단/데이터 제공 범위/이용 책임)으로
교체했다. 상단 안내 문구를 "이 영역은 정식 배포 전 최종 안내 문구를 작성할
예정입니다"에서 "핵심 수집 정책을 요약합니다. 자세한 내용은 README.md/
LEGAL_NOTICE.md를 확인하세요"로 바꿨다. "유지보수/A/S 안내"·"라이선스
안내"는 그대로 placeholder 유지(1PC 라이선스 인증, 결제/고객센터/계정
기능은 여전히 별도 태스크). 기존 카드·스크롤 프레임 구조와 레이아웃은
재설계하지 않고 그대로 재사용했다.

## 수집 방식 설명
"검색 결과 목록 화면에서 브라우저가 검색 과정 중 정상적으로 수신한 응답을
처리합니다. 별도의 HTTP 클라이언트로 네이버 엔드포인트를 직접 호출하는
구조는 사용하지 않습니다"로 README/LEGAL_NOTICE/안내·정책 탭 3곳에 동일하게
반영했다(`network_browser_collector.py`가 `page.goto()` + response listener
방식만 쓰고 `requests`/`httpx`/`urllib.request` 등을 전혀 import하지 않음을
grep으로 재확인 후 기술).

## 수집량·목표 미달 설명
검색 조합당 수집 상한(30)과 전체 목표 저장 개수(300)를 표로 명확히
구분했다. "300개 보장"이라는 표현은 어디에도 긍정 주장 형태로 쓰지 않았고,
오히려 "'300개 보장'을 의미하지 않습니다"처럼 명시적으로 부인하는
문장으로만 등장한다(`check_forbidden_hype_phrases_absent`가 부정 문맥은
오탐으로 걸러내고 긍정 주장 형태만 위반으로 잡도록 설계됨).

## 중단·부분 저장 정책
target_reached/queue_exhausted(목표 미달 가능)/security_blocked/status_429/
navigation_error/user_stopped 6가지 stop_reason 모두 "결과가 있으면 저장"
표로 정리했다(`src/pc/network_pipeline.py`/`src/ui.py::_export_network_result`
실제 동작과 대조 확인, 두 파일 모두 무수정). "항상 부분 저장된다"는 표현은
쓰지 않았고, 결과 0건이면 어떤 stop_reason이든 저장하지 않는다는 조건을
분리해 명시했다. exporter 자체 오류(디스크 쓰기 실패 등) 시 저장되지 않을
수 있다는 점도 과장 없이 한 줄로 안내했다.

## 새로오픈 및 필드 공백 정책
새로오픈 필터가 현재 비활성화 상태이며 새로오픈여부 열은 항상 빈칸임을
README/LEGAL_NOTICE/안내·정책 탭에 일관되게 명시했다. 홈페이지/인스타/
블로그/전화 등도 검색 응답에 값이 없으면 빈칸일 수 있음을 함께 안내했다.

## 공식 제품·법적 보장 표현 검토
"본 프로그램은 네이버 공식 제품이거나 네이버와 제휴한 제품이 아닙니다"를
README 섹션 1과 LEGAL_NOTICE 섹션 6에 추가했다. LEGAL_NOTICE 전체를
재확인한 결과 "합법을 보장합니다"/"이용약관 위반이 아닙니다"/"법적 문제가
없습니다"/"네이버가 허용했습니다" 등 금지된 법적 확정 표현은 기존에도
없었고 이번에도 추가하지 않았다.

## 참고(코드 변경 아님, 개발 기록용 관찰)
`src/pc/network_list_scraper.py::_build_place_url`은 응답에 명시적 URL
필드가 없으면 `https://pcmap.place.naver.com/place/{place_id}/home`로
플레이스 URL을 best-effort 구성하며, 함수 자체 docstring이 "PoC 단계의
임시 구성 - 실사용 전 검증 필요"라고 명시한다(업종별 세그먼트가 실제로는
다를 수 있음, live 재검증 안 됨). 이번 WIRE-2D는 코드를 수정하지 않았고
README에는 "플레이스 URL"이라고만 표기해 이 PoC 단계 세부사항까지는
노출하지 않았다 - 이후 live 검증 단계에서 실제로 유효한 리다이렉트인지
확인이 필요하다는 사실만 이 기록에 남긴다.

## 신규 문서 테스트 결과
`tests/test_ui_policy_text.py`(신규) 13건 전부 PASS: README에 Network/List
흐름 설명 존재 / per_query_limit=30·target_count=300 구분 / 목표 미달 가능
문구 / CAPTCHA·429 우회 없음 / 0건 파일 미생성 / 새로오픈 필터 미지원 /
필드 공백 가능 / 별도 HTTP 클라이언트 직접 호출 없음 / 공식·제휴 제품 아님
고지 / LEGAL_NOTICE 최신 섹션에 낡은 "10건 이내" 없음(과거 섹션은 보존) /
LEGAL_NOTICE에 법적 확정 보장 표현 없음 / UI 안내·정책 탭 핵심 문구(5개
섹션 제목 + 우회 없음/직접 호출 없음) 존재 / README·LEGAL_NOTICE에 과장·
보장성 금지 표현이 긍정 주장 형태로는 없음(부정 문맥 오탐 방지).

## 전체 회귀 결과
- `python -m py_compile src/ui.py tests/test_ui_network_wiring.py tests/test_ui_network_export.py tests/test_ui_network_start.py tests/test_ui_policy_text.py` PASS.
- `tests/test_ui_policy_text.py` 13건 전부 PASS.
- `tests/test_ui_network_start.py` 12건 전부 PASS(무영향, `_build_policy_tab`
  외 다른 메서드 무수정 재확인).
- `tests/test_ui_network_wiring.py` 19건 전부 PASS(무영향).
- `tests/test_ui_network_export.py` 7건 전부 PASS(무영향).
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(무영향, 파일 무수정).
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(무영향, 파일 무수정).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향, legacy 경로 무변경 재확인).

## live/Playwright/네이버/app.py/UI/build/EXE 실행 여부
**전부 실행 안 함.** 이번 단계는 텍스트 파일(README/LEGAL_NOTICE) 읽기/
쓰기와 `src/ui.py`의 `_build_policy_tab()` 문자열 리터럴 수정, 그리고
`inspect.getsource()`/파일 텍스트 기반 검증만 수행했다. 실제 Playwright/
브라우저/네이버 접속, app.py 실행, 실제 Tk 창, build/EXE 실행은 전혀 없다.
live 10/50/300 제품 검증은 아직 미실행 상태로 남아있다.

## 커밋 관련
WIRE-2C-2(엔진 전환)와 WIRE-2D(문서 정합성)를 검토 후 한 커밋으로 묶을
예정이므로, 이번 단계에서도 git add/commit을 하지 않았다.

---

# 2026-07-15 ARCH-300C WIRE-3 실제 production 함수 기반 no-live 전체 통합 검증

## 배경
WIRE-2C-1/2C-2/2D까지 각 계층(orchestrator, browser collector, UI worker,
문서)을 개별적으로 fake/monkeypatch 기반 단위 테스트로 검증해왔다. 이번
단계는 실제 네이버·Playwright에 접속하지 않으면서도, UI 시작 지점부터
`NetworkBrowserCollector`→`collect_network_query`→`network_list_scraper`
매핑→`run_collection_plan`→`export_places_to_excel`까지 **실제 production
함수를 최대한 그대로 연결**해 전체 흐름이 실제로 맞물려 동작하는지
한 번에 검증했다. 가짜로 대체한 것은 Playwright 브라우저 계층
(FakeBrowserSessionLike/FakePage/FakeResponse/FakeLocator)뿐이다.

## 변경 파일
- 신규 `tests/test_network_product_integration_no_live.py`: 11개 통합
  테스트(§아래).
- `PROJECT_STATE.md`: 이번 기록 append.
- production 코드(`src/ui.py`, `src/pc/network_browser_collector.py`,
  `src/pc/network_pipeline.py`, `src/pc/network_list_scraper.py`)는
  **전혀 수정하지 않았다** - 통합 테스트에서 실제 결함이 발견되지 않았다
  (§아래 "테스트 fixture 문제 vs production 결함" 참고).

## 통합 테스트에서 실제 사용한 production 함수
- `src.pc.network_browser_collector.NetworkBrowserCollector`(실제 클래스,
  `session_factory`만 fake 주입)
- `src.pc.network_browser_collector.collect_network_query`(monkeypatch 없이
  그대로 호출됨 - `NetworkBrowserCollector.collect_query`를 통해서든, URL
  계약 검증에서 직접 호출하든 전부 실제 함수)
- `src.pc.network_list_scraper`의 `_extract_list_items`/`_map_item_to_row`/
  `dedup_rows`/`classify_captcha_signal`/`is_candidate_response`(전부
  `collect_network_query` 내부에서 실제로 실행됨, 별도 monkeypatch 없음)
- `src.pc.network_pipeline.run_collection_plan`(실제 함수, fake 없이 직접
  전달)
- `src.exporter.export_places_to_excel`(실제 함수, `tempfile.TemporaryDirectory()`
  안에서 실제 `.xlsx` 파일을 만듦)
- `src.ui.SalesDbCrawlerApp._run_network_pipeline`(실제 메서드, 시나리오
  4~9는 인스턴스 메서드로 직접 호출, 시나리오 10은 `ui.SalesDbCrawlerApp.
  _run_network_pipeline`을 언바운드로 가져와 fake collector_factory만 주입한
  wrapper로 교체 - 이유는 아래 "worker 예외 시나리오 설계" 참고)
- `src.ui.SalesDbCrawlerApp._run_network_pipeline_worker`(시나리오 10에서
  전혀 monkeypatch하지 않은 실제 클래스 메서드 그대로 호출)
- `src.ui.SalesDbCrawlerApp._network_stop_message`(시나리오 5에서 실제
  메서드로 안내 문구 직접 검증)
- `src.ui.SalesDbCrawlerApp.set_running`/`_set_left_panel_state`/
  `_note_security_block`(시나리오 10/6에서 실제 메서드 그대로 실행)

## fake BrowserSession/page/response 구조
`FakeBrowserSessionLike`(컨텍스트 매니저 + `.context`/`.page` 속성만
BrowserSession과 동일한 계약) → `.context`(`FakeContext`)는 `new_page()`
호출마다 미리 준비된 `FakePage` 목록을 순서대로 하나씩 내준다(job 실행
순서와 1:1 대응) → `FakePage`는 `on`/`off`/`goto`/`wait_for_timeout`/
`locator`/`close`를 지원하며, `goto(url)` 호출 시 준비된 `FakeResponse`들을
등록된 response handler에 그대로 전달한다(실제 Playwright response 이벤트
발생과 동일한 순서). `FakeResponse.json()`은 `{"result": {"place": {"list":
[...]}}}` 구조를 반환해 실제 `_extract_list_items`의 알려진 경로 탐색을
그대로 태운다. `FakeLocator`는 CAPTCHA probe selector별 count/visible/
bounding_box를 미리 지정해 실제 `_probe_captcha_state`/`classify_captcha_signal`
계산 로직을 그대로 통과시킨다. `wait_for_timeout`은 실제 대기 없이 호출
인자만 기록한다. `test_pc_network_browser_collector.py`의 기존 검증된
FakePage/FakeResponse/FakeLocator 계약을 그대로 재사용/확장(close() 추가)
했다 - 새로운 계약을 임의로 만들지 않았다.

## 목표 도달 결과
job 3개(per_query_limit=3, target_count=5). job1 응답 2개(A,B / B,C - B는
job1 내부 local dup)로 local dedup 후 A,B,C 3건. job2(B,C,D)는 전역 dedup으로
D만 신규 추가(누적 A,B,C,D). job3(E,F,G)에서 전부 신규 추가되어 누적 7건 →
target=5 도달로 trim. **stop_reason=target_reached, final_count=5,
executed_query_count=3, skipped_query_count=0**, 저장된 업체 순서가
정확히 결정적으로 `업체A,업체B,업체C,업체D,업체E` - PASS.

## 목표 미달 결과
job 3개 전부 실행(target_count=10), 전역 dedup 후 최종 고유 업체 4개
(A,B,C,D - job2의 A는 job1과 전역 중복이라 제외). **stop_reason=
queue_exhausted, final_count=4**, `_network_stop_message`가 "미달" +
"4개를 저장했습니다"를 포함한 안내 문구를 실제로 생성 - PASS.

## CAPTCHA 결과
job1 정상 3건(X,Y,Z), job2는 candidate 응답 없이 CAPTCHA locator만
visible+면적>0으로 준비(실제 `_probe_captcha_state`/`classify_captcha_signal`
이 active로 판정), job3용 FakePage는 아예 준비하지 않아 실행되면 IndexError로
즉시 드러나도록 방어했다. **stop_reason=security_blocked, final_count=3,
executed_query_count=2, skipped_query_count=1**, job1의 3건이 그대로
보존·저장되고 `app._security_block_decision`이 `_note_security_block`(실제
메서드)을 통해 정상 연결됨을 확인했다. 재시도/session 재시작은 코드
경로 자체에 존재하지 않으므로(NetworkBrowserCollector에 그런 로직 없음)
구조적으로 발생하지 않는다 - PASS.

## HTTP 429 결과
job1 정상 2건(M,N), job2는 candidate 아닌 응답에 status=429만 포함(실제
response handler가 URL 후보 여부와 무관하게 status만 먼저 검사), job3용
FakePage 미준비로 실행 시 즉시 드러나도록 방어. **stop_reason=status_429,
final_count=2, executed_query_count=2, skipped_query_count=1**, 이전
결과 2건이 exporter 정확히 1회로 저장됨 - PASS.

## 0건 처리
job 2개 모두 candidate 응답은 있으나 `result.place.list=[]`. **final_count=0,
exported=False, export_error=False, export_path=""**, 실제 임시 디렉터리에
xlsx 파일이 전혀 생성되지 않음, 상태 문구 "저장할 결과가 없습니다." - PASS.

## local/global dedup
local dedup: job1 내부에서 동일 응답 세트에 B가 두 번 등장해도 1건으로
수렴(실제 `dedup_rows` local pass). global dedup: job2/job3에서 이전
job과 겹치는 업체(B,C 또는 A)가 `run_collection_plan`의 공유 `seen` set을
통해 정확히 걸러짐(목표 도달 시나리오에서 D만 신규 추가, 목표 미달
시나리오에서 job2의 A 제외). 둘 다 실제 함수(`dedup_rows`,
`run_collection_plan`)로 검증됨 - PASS.

## Excel 결과
목표 도달 시나리오에서 실제 `export_places_to_excel`이 만든 `.xlsx`를
`openpyxl`로 직접 열어 확인: `통합_결과` 헤더가 `exporter.MERGED_COLUMNS`
11개와 정확히 일치, 데이터 행 5개, `원본_모바일`/`원본_PC`는 `max_row==1`
(헤더만). 전부 `tempfile.TemporaryDirectory()` 안에서만 생성되고 테스트
종료 시 자동 삭제됨 - PASS.

## browser/page/session teardown
목표 도달 시나리오 기준: `FakeBrowserSessionLike.exit_count==1`(context
manager 정상 종료), 초기 page(`session.page`, `_close_initial_page_if_present`
대상)의 `close_call_count==1`, `context.new_page_call_count==3`(job 수와
일치), 생성된 쿼리별 page 3개 전부 `close_call_count==1`. CAPTCHA/429
시나리오도 동일 원칙(실행된 job 수만큼만 page 생성·close, 세션은 정상
종료) - PASS.

## UI 정상·예외 복구
정상 경로(시나리오 4~9)는 `_run_network_pipeline`을 인스턴스 메서드로 직접
호출해 매 시나리오 결과 dict/Excel/상태 문구를 검증했다. 예외 경로
(시나리오 10)는 `NetworkBrowserCollector.__enter__`가 `session_factory()`를
try/except 없이 그대로 호출한다는 실제 코드 특성을 활용해, `session_factory`
가 `RuntimeError`를 던지도록 구성 - 이 예외가 `with collector_factory(...)
as collector:` 블록을 그대로 통과해 `_run_network_pipeline_worker`(실제
메서드, monkeypatch 없음)의 `except Exception`에서 잡힘을 확인했다.
`self.after`를 즉시 실행되도록 fake 처리하고 `set_running`/
`_set_left_panel_state`도 실제 메서드 그대로 둔 상태에서, 최종적으로
`app.btn_start.configure_calls[-1] == {"state": "normal"}`까지 실제로
전파됨을 확인했다 - "저장했습니다"/"저장 완료" 문구는 어디에도 없고
"수집 중 오류가 발생했습니다."만 표시됨, 불완전한 xlsx 파일도 생성되지
않음 - PASS.

## 테스트 fixture 문제 vs production 결함(발견했지만 production 코드는 수정하지 않음)
시나리오 10을 처음 구현했을 때 `set_running(False)` → `_set_left_panel_state`
→ `hasattr(self, "new_open_checkbox")` 호출에서 `RecursionError`가
발생했다. 원인은 `__new__`로 만든 헤드리스 fake app이 `tkinter.Widget`의
정상 초기화(`self.tk` 등)를 거치지 않아, 존재하지 않는 위젯 속성을
`hasattr()`로 조회할 때 `Widget.__getattr__`가 `self.tk`로 위임을
시도하다 무한 재귀에 빠지는 것이었다. **이것은 production 결함이
아니다** - 실제 앱에서는 `_build_ui()`가 항상 먼저 완료된 뒤에만
`set_running`이 호출되므로 `new_open_checkbox`는 이미 실제 위젯으로
존재하고, `hasattr()`는 재귀 없이 즉시 True를 반환한다. 재현 조건은
"헤드리스 fixture가 실제 위젯 존재를 흉내내지 못함"뿐이므로, 수정은
production 코드(`src/ui.py`)가 아니라 테스트 fixture
(`_make_app_with_real_ui_recovery`에 `app.new_open_checkbox = FakeWidget()`
추가)에서 했다. 요청서 §10 "production 로직은 결함이 발견된 경우에만
최소 수정"의 판단 기준에 따라, 이 사례는 fixture 문제로 분류하고
production 코드는 무수정으로 유지했다.

## 검색 URL 계약 검토
`src/pc/network_browser_collector._SEARCH_URL_TEMPLATE =
"https://map.naver.com/v5/search/{query}"` + `quote(job["query"])` 조합을
`scratchpad/arch300_network_probe/poc1_probe.py`~`poc9_food_subvertical_probe.py`
9개 PoC 스크립트 전부의 `search_url = f"https://map.naver.com/v5/search/
{quote(...)}"` 패턴과 grep으로 직접 대조 - **완전히 일치**(PoC-7에서
live 17개 쿼리 연속 성공, CAPTCHA/429 없음으로 실측 검증된 패턴과 동일).
no-live 문자열 계약 6개 전부 확인: (1) `job["query"]`가 URL에 정확히
포함됨, (2) 한글/공백/특수문자(&, /)가 안전하게 인코딩되고 unquote
round-trip이 원본과 일치, (3) source_city/source_district 등 내부 메타가
URL에 중복 반영되지 않음(오직 `job["query"]`만 사용), (4) 위 PoC 패턴과
정확히 일치, (5) URL 하나당 쿼리 하나만 표현되고 서로 섞이지 않음, (6)
`network_browser_collector.py` 소스에 `requests`/`httpx`/
`urllib.request`/`http.client` import가 전혀 없고 `page.goto()`로만
이동함을 `inspect.getsource()`로 확인. **현재 구현과 성공 PoC 기록 사이에
충돌이나 차이는 발견되지 않았다** - production 코드 변경 불필요. 실제
네이버가 이 URL을 정상 처리하는지 자체는 이번 단계에서 검증하지 않았고
(no-live 문자열 계약만), WIRE-4A의 실제 live 검증으로 남겨둔다.

## 신규 테스트 결과
`tests/test_network_product_integration_no_live.py`(신규) **11건 전부
PASS**: 목표 도달 전체 통합 / 목표 미달 전체 통합 / CAPTCHA 안전 중단 전체
통합 / HTTP 429 안전 중단 전체 통합 / 0건 전체 통합 / URL-job 쿼리 일치·
PoC 패턴 일치 / URL 한글·공백·특수문자 인코딩 / URL에 source_* 메타 미중복
/ URL 하나당 쿼리 하나 / 직접 HTTP 클라이언트 없음(page.goto만) / worker
예외 시 실제 UI 복구(session_factory 예외 → 실제 set_running(False) →
실제 btn_start.configure(state="normal")까지 전파).

## 전체 회귀 결과
- `python -m py_compile src/ui.py tests/test_network_product_integration_no_live.py tests/test_ui_network_start.py tests/test_ui_network_wiring.py tests/test_ui_network_export.py tests/test_ui_policy_text.py` PASS.
- `tests/test_network_product_integration_no_live.py` 11건 전부 PASS.
- `tests/test_ui_policy_text.py` 13건 전부 PASS(무영향).
- `tests/test_ui_network_start.py` 12건 전부 PASS(무영향).
- `tests/test_ui_network_wiring.py` 19건 전부 PASS(무영향).
- `tests/test_ui_network_export.py` 7건 전부 PASS(무영향).
- `tests/test_pc_network_pipeline.py` 12건 전부 PASS(무영향, 파일 무수정).
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(무영향, 파일 무수정).
- `tests/test_pc_network_list_scraper.py` 39건 전부 PASS(무영향, 파일 무수정).
- `tests/test_ui_query_builder.py` 9건 전부 PASS(무영향).
- `tests/test_ui_pc_full_wiring.py` 4건 전부 PASS(무영향).
- 총 140개 검증 항목 전부 PASS, FAIL 0.

## production 코드 수정 여부
**무수정.** `src/ui.py`/`src/pc/network_browser_collector.py`/
`src/pc/network_pipeline.py`/`src/pc/network_list_scraper.py` 전부 이번
단계에서 결함이 발견되지 않아 그대로 유지했다(§위 "테스트 fixture 문제
vs production 결함" 참고 - 유일하게 발견된 이슈는 테스트 fixture의
한계였고 production 코드와 무관했다).

## live/Playwright/네이버/app.py/UI/build/EXE 실행 여부
**전부 실행 안 함.** 모든 브라우저 계층은 FakeBrowserSessionLike/FakePage/
FakeResponse/FakeLocator로 대체됐고, `.xlsx` 파일 IO는
`tempfile.TemporaryDirectory()` 안에서만 발생했다(자동 삭제). 실제
Playwright 시작, 네이버 접속, `app.py` 실행, 실제 Tk 창, build/EXE 실행은
전혀 없었다.

## 다음 단계
WIRE-4A: 실제 Playwright + 네이버로 소규모(10개) live 검증. 이번 WIRE-3에서
확인한 URL 계약(§검색 URL 계약 검토)이 실제로 네이버 응답을 정상적으로
받아오는지, CAPTCHA/429 없이 동작하는지는 여전히 미검증 상태로 남아있다.

---

# 2026-07-15 ARCH-300C WIRE-3A 목표 도달 후 미실행 통합 검증 보강 + 합계 기록 정정(기능 변경 없음)

## 배경
WIRE-3에서 구현한 정상 목표 도달 시나리오는 job 3개(target이 job3에서 정확히
도달)만 검증했고, "목표 도달 이후 남은 job이 실제로 실행되지 않는다"는
계약을 별도 job으로 명시적으로 증명하지 않았다. 이번 단계는 job을 4개로
늘려 4번째 job(목표 도달 이후)이 new_page/goto/close 어느 것도 호출되지
않고 결과·Excel 어디에도 섞이지 않음을 직접 검증하도록 보강했다. 아울러
WIRE-3 최초 보고의 "전체 검증 합계 140"이 단순 합산 오류였음을 발견해
정정한다 - **기능 실패나 회귀가 아니라 보고 숫자 정정**이다.

## 변경 파일
- `tests/test_network_product_integration_no_live.py`: `check_target_reached_full_integration`
  을 4 job 구조로 확장(job4=X,Y,Z 추가), `_counting_exporter()` 헬퍼 추가
  (실제 `export_places_to_excel`을 그대로 위임 호출하면서 호출 횟수만
  기록), `_run_pipeline()`에 `excel_exporter` 선택 인자 추가(기본값은 기존과
  동일하게 실제 `export_places_to_excel`). 나머지 시나리오(목표 미달/
  CAPTCHA/429/0건/URL 계약/worker 예외)는 무수정.
- `PROJECT_STATE.md`: 이번 정정 기록 append.
- production 코드는 이번에도 **전혀 수정하지 않았다**(결함 미발견).

## 목표 도달 시 총 job 수
**4개**(JOB1~JOB4). JOB1=천호동, JOB2=성내동, JOB3=길동(target=5 도달
시점), JOB4=암사동(X,Y,Z - 목표 도달 이후이므로 절대 실행되면 안 됨).

## 실행된 job 수 / 건너뛴 job 수
**실행 3 / 건너뜀 1**(`executed_query_count == 3`, `skipped_query_count == 1`).
`before_trim_count`(job1~3 누적 dedup 결과, 7건)도 목표(5) 이상임을 확인했다.

## job4 미실행 검증 방법
1. `FakeContext`에 page1~4를 전부 등록해뒀지만(즉 "준비는 됐지만 안 쓰임"을
   증명하는 방식 - 없어서 어쩔 수 없이 안 쓰인 게 아님), `run_collection_plan`
   이 job3에서 멈추면 `context.new_page()`가 3번만 호출되므로 `page4`는
   `context._pages` 목록에서 아예 꺼내지지 않는다.
2. `page4.goto_calls == []`(한 번도 호출된 적 없음), `page4.close_call_count
   == 0`, `page4 not in session.context.pages_served`를 전부 직접 단언했다.
3. `session.context.new_page_call_count == 3`(정확히 3, 4가 아님)도 함께 확인.

## Excel에 job4 업체가 없는지
`result["rows"]`에서 `{"업체X","업체Y","업체Z"}`와의 교집합이 비어있음을
먼저 확인하고, 실제 저장된 `.xlsx`를 `openpyxl`로 열어 `통합_결과`의
`업체명` 컬럼 전체 집합에서도 X/Y/Z가 전혀 없음을 재확인했다(이중 확인 -
orchestrator 결과 레벨과 실제 파일 레벨 둘 다). 최종 저장 순서는 여전히
`["업체A","업체B","업체C","업체D","업체E"]` 5건으로 결정적이다.

## page/session teardown 결과
`session.exit_count == 1`, 초기 page `close_call_count == 1`,
`new_page_call_count == 3`, 실제 사용된 page 3개(`pages_served`)는 각각
정확히 1회씩 close. `exporter_calls == [1]`(`_counting_exporter`로 실제
`export_places_to_excel` 호출 횟수를 직접 계측 - 이전 보고서는 파일 존재
여부로 간접 추정했으나 이번에 명시적 카운트로 보강했다).

## 신규/보강 테스트 결과
`tests/test_network_product_integration_no_live.py` **11건 전부 PASS**
(파일 수/테스트 개수는 그대로 11개 - 기존 목표 도달 테스트 1개를 강화한
것이며 신규 테스트 함수를 추가한 것은 아니다).

## 전체 테스트 합계 정정
WIRE-3 최초 보고서(2026-07-15 WIRE-3 기록)의 "총 140개 검증 항목"은 단순
합산 오류다. 실제 합은 다음과 같다:

```
11(test_network_product_integration_no_live.py)
+ 13(test_ui_policy_text.py)
+ 12(test_ui_network_start.py)
+ 19(test_ui_network_wiring.py)
+ 7(test_ui_network_export.py)
+ 12(test_pc_network_pipeline.py)
+ 24(test_pc_network_browser_collector.py)
+ 39(test_pc_network_list_scraper.py)
+ 9(test_ui_query_builder.py)
+ 4(test_ui_pc_full_wiring.py)
= 150
```

**정정: 기존(WIRE-3 시점) 정확한 합계는 150 PASS였다(140이 아님).** 이번
WIRE-3A에서는 새 테스트 함수를 추가하지 않고 기존 목표 도달 테스트 1개를
보강했을 뿐이므로, WIRE-3A 이후 최종 합계도 **150 PASS, FAIL 0**으로
동일하다. 이는 기능 실패나 회귀가 발견된 것이 아니라 이전 보고서의 단순
산술 오기를 바로잡는 기록이다.

## production 코드 수정 여부
**무수정.** 이번 통합 테스트 보강에서도 production 코드
(`src/ui.py`/`src/pc/network_browser_collector.py`/`src/pc/network_pipeline.py`/
`src/pc/network_list_scraper.py`/`src/exporter.py`)에서 결함이 발견되지
않았다.

## live/Playwright/네이버/app.py/UI/build/EXE 실행 여부
**전부 실행 안 함.** WIRE-3와 동일하게 FakeBrowserSessionLike/FakePage/
FakeResponse만 사용했고, `.xlsx` 파일 IO는 `tempfile.TemporaryDirectory()`
안에서만 발생했다.

---

# 2026-07-15 ARCH-300C WIRE-4A 실제 Network 제품 경로 10건 단일 live 실행

## 배경
WIRE-1~WIRE-3A까지는 fake 브라우저 계층(FakeBrowserSessionLike/FakePage/
FakeResponse)만으로 검증했고, 실제 production 코드로 네이버를 실행한
적은 한 번도 없었다. 이번 단계는 실제 Playwright + 실제 네이버로 검색
조합 **정확히 1개**만 단발성 실행해, `NetworkBrowserCollector` →
`collect_network_query` → `run_collection_plan` → `export_places_to_excel`
로 이어지는 실제 제품 경로가 실제 네이버 응답과 정상적으로 맞물리는지
확인했다. 자동 재시도/재검색/CAPTCHA 우회는 전혀 구현하지 않았고, 정확히
1회만 실행했다.

## 변경 파일
- 신규 `scratchpad/arch300_network_probe/wire4a_product_live_10.py`: 단발성
  live harness(§아래).
- 신규 `scratchpad/arch300_network_probe/wire4a_live_10_result_20260715_160736.json`:
  이번 실행의 전체 결과 기록.
- 신규 `output/wire4a_live_10_20260715_160736.xlsx`: 실제 저장된 10행 Excel.
- `PROJECT_STATE.md`: 이번 기록 append.
- production 코드(`src/**`)는 **전혀 수정하지 않았다.**

## 실행 환경
`.venv\Scripts\python.exe`(3.14.3) 기준으로만 실행했다(시스템 Python
미사용). `import playwright, openpyxl, customtkinter` 확인 완료.
Playwright Chromium(`chromium-1223`)이 이미 `.venv`에 설치되어 있어 추가
설치는 하지 않았다. live 실행 전 최소 회귀 3건(`test_network_product_integration_no_live.py`
11/11, `test_pc_network_browser_collector.py` 24/24, `test_pc_network_pipeline.py`
12/12) 전부 PASS를 확인한 뒤에만 live를 실행했다.

## 검색어와 실행값
`query="서울특별시 강동구 천호동 카페"`, `source_city/district/subregion/layer`는
work order 지정값 그대로. `per_query_limit=10`, `target_count=10`. job은
정확히 1개, 검색어 추가 없음.

## live 실행 횟수
**정확히 1회.** 재시도/재검색/브라우저 재시작 없음(`retries: 0`을 결과
JSON에 명시). 두 번째 실행은 수행하지 않았다.

## 관찰 결과(요약)
- `candidate_response_count=1`, `raw_item_count=20`, `local_unique_count=20`,
  `parse_error_count=0`, `timeout=False`.
- `active_captcha_detected=False`, `status_429_seen=False`,
  `navigation_error=False`(`navigation_error_message=""`).
- `executed_query_count=1`, `skipped_query_count=0`, `before_trim_count=10`,
  `final_count=10`, `stop_reason="target_reached"`.
- `exported=True`, `export_error=False`,
  `export_path=output/wire4a_live_10_20260715_160736.xlsx`.
- 생성된 검색 URL: `https://map.naver.com/v5/search/%EC%84%9C%EC%9A%B8%ED%8A%B9%EB%B3%84%EC%8B%9C%20%EA%B0%95%EB%8F%99%EA%B5%AC%20%EC%B2%9C%ED%98%B8%EB%8F%99%20%EC%B9%B4%ED%8E%98`
  (WIRE-3의 URL 계약 검토와 동일한 `_SEARCH_URL_TEMPLATE` + `quote(job["query"])`
  조합이 실제로 네이버에 정상 도달함을 확인).

## Excel 실제 검증(openpyxl 재확인)
`통합_결과` 헤더 11개가 `MERGED_COLUMNS`와 정확히 일치, 데이터 행 10개
(`final_count`와 정확히 일치), `place_id`/`source_*` 내부 필드 미노출
(`internal_field_leak=[]`). `원본_모바일`/`원본_PC`는 둘 다 `max_row=1`
(헤더만). 필드 채움 수(10건 기준): 업체명 10/업종 10/리뷰수 10/주소 10/
대표전화 10/플레이스 URL 10/수집일 10/인스타 4/홈페이지 0/블로그 0.
**새로오픈여부는 10건 전부 빈칸(0)** - README/LEGAL_NOTICE/안내·정책
탭에 기록한 "현재 Network 경로에서는 항상 빈칸" 설명과 실제 live 결과가
정확히 일치함을 재확인했다.

## 타이밍
`session_ready_seconds=2.03`(브라우저+세션 준비), `orchestrator_seconds=6.13`
(쿼리 1개 실행 전체 - page 생성/goto/settle(5000ms)/파싱/CAPTCHA probe/
close 전부 포함, production 코드/Playwright page 객체를 건드리지 않기
위해 세부 구간으로는 쪼개지 않음), `session_teardown_seconds=0.28`,
`export_seconds=0.05`, `total_wall_seconds=8.50`.

## 재시도·우회 여부
**없음.** CAPTCHA 자동 해결/DOM 제거, context 재시작, proxy/stealth, 429
회피 로직은 harness에 전혀 구현하지 않았다(애초에 이번 실행에서는
CAPTCHA/429가 발생하지 않아 그런 분기 자체가 실행되지 않았다).

## production 코드 수정 여부
**무수정.** `src/**` 전체가 이번 단계에서 결함 없이 그대로 실제 네이버와
정상 연결됨을 확인했다 - 코드 수정이 필요한 문제를 전혀 발견하지 못했다.

## WIRE-4A 최종 판정
**완전 PASS.** work order §8의 "완전 PASS" 조건(candidate_response_count>=1,
raw_item_count>=10, local_unique_count>=10, final_count==10,
stop_reason==target_reached, CAPTCHA/429/navigation_error 전부 False,
exported==True, Excel 10행/11헤더 정확 일치, 내부 메타 미노출, session/
page 정상 종료, exporter 1회, 재시도 0회)을 전부 만족했다.

## 다음 단계 진입 가능 여부
**가능.** WIRE-4B(더 큰 규모 live 검증, 50~300건 확장)로 진입할 수 있는
최소 근거가 확보됐다. 단, 이번 결과는 강동구·천호동·카페·1회 실행이라는
단일 표본이므로(PoC-7~9에서도 이미 확인된 한계) 다른 지역/업종/시점에서도
동일하게 재현되는지는 여전히 별도 검증이 필요하다. 속도 최적화는 work
order 지시대로 이번 단계에서 진행하지 않았다.

---

# 2026-07-15 ARCH-300C WIRE-4B 실제 Network 제품 경로 50건 단일 live 실행

## 배경
WIRE-4A는 쿼리 1개·목표 10건으로 production 경로가 실제 네이버와 정상
연결됨을 확인했다. 이번 단계는 같은 브라우저 context 안에서 검색 조합
**4개를 순차 실행**해, 쿼리 내부 local dedup뿐 아니라 쿼리 사이 global
dedup과 목표(target=50) 조기 종료가 실제 환경에서도 설계대로 동작하는지
확인했다. WIRE-4A와 동일하게 정확히 1회만 실행했고 재시도/우회는
구현하지 않았다.

## 변경 파일
- 신규 `scratchpad/arch300_network_probe/wire4b_product_live_50.py`:
  WIRE-4A harness를 재사용해 4-job 순차 실행 + 쿼리별 진단 로그 +
  진단 전용 global unique_added 계산을 추가한 단발성 live harness.
- 신규 `scratchpad/arch300_network_probe/wire4b_live_50_result_20260715_162551.json`:
  이번 실행의 전체 결과·쿼리별 로그.
- 신규 `output/wire4b_live_50_20260715_162551.xlsx`: 실제 저장된 50행 Excel.
- `PROJECT_STATE.md`: 이번 기록 append.
- production 코드(`src/**`)는 **전혀 수정하지 않았다.**

## 실행 환경 및 사전 회귀
`.venv\Scripts\python.exe`(3.14.3) 기준으로만 실행. live 실행 전 최소
회귀 3건(`test_network_product_integration_no_live.py` 11/11,
`test_pc_network_browser_collector.py` 24/24, `test_pc_network_pipeline.py`
12/12) 전부 PASS 확인 후에만 live를 실행했다.

## job 구성과 실행값
공통 메타 `source_city=서울특별시, source_district=강동구,
source_layer=legal_dong` + `source_subregion`별 4개 job(순서: 천호동 →
길동 → 성내동 → 암사동), 각 `query="서울특별시 강동구 {법정동} 카페"`.
`per_query_limit=20`, `target_count=50`.

## live 실행 횟수
**정확히 1회.** `retries: 0`을 결과 JSON에 명시. 재실행 없음.

## 쿼리별 실행 결과
| 순번 | 법정동 | candidate | raw | local_unique | returned_rows | global_unique_added(진단) | 누적(진단) | wall |
|---|---|---|---|---|---|---|---|---|
| 1 | 천호동 | 1 | 20 | 20 | 20 | 20 | 20 | 6.02s |
| 2 | 길동 | 1 | 20 | 20 | 20 | 20 | 40 | 5.88s |
| 3 | 성내동 | 1 | 20 | 20 | 20 | 20 | 60 | 5.87s |
| 4 | 암사동 | - | - | - | - | - | - | 미실행(target 도달로 skip) |

3개 쿼리 전부 `parse_error_count=0`, `timeout=False`,
`active_captcha_detected=False`, `status_429_seen=False`,
`navigation_error=False`. job4(암사동)는 `run_collection_plan`이 query3
직후 `before_trim_count=60>=target=50`으로 즉시 멈춰 `collect_query`
자체가 호출되지 않았다(harness의 `recording_collect_query` wrapper 호출
로그도 3건만 기록됨 - 코드 레벨로 미실행이 직접 증명됨).

## 전체 오케스트레이션 결과
`executed_query_count=3`, `skipped_query_count=1`, `before_trim_count=60`,
`final_count=50`, `stop_reason="target_reached"`, `security_blocked=False`,
`status_429_seen=False`, `navigation_error=False`.

## 전역 중복 제거 진단
쿼리별 반환 rows 합계(local dedup+per_query_limit cap 이후) = 60건, 이번
실행에서는 **쿼리 간 겹치는 업체가 0건**이었다(`global_duplicates_removed=0`,
`global_dedup_rate=0.0`) - 천호동/길동/성내동 세 법정동의 카페 검색
결과가 이번 표본에서는 서로 겹치지 않았다는 뜻이다(과거 PoC-6/7의 "법정동
간 중복률 0%, 역/상권에서만 중복 발생" 관찰과 방향이 일치한다).
`run_collection_plan`을 전혀 건드리지 않는 별도 진단 전용 `seen` set으로
계산한 누적 고유값(60)이 실제 오케스트레이터의 `before_trim_count`(60)와
정확히 일치함을 확인했다(`diagnostic_cumulative_unique_matches_orchestrator_before_trim=true`)
- 진단 계산이 실제 dedup 로직과 완전히 같은 결과를 냄을 이중으로
검증한 셈이다.

## Excel 실제 검증(openpyxl 재확인)
`통합_결과` 헤더 11개가 `MERGED_COLUMNS`와 정확히 일치, 데이터 행 50개
(`final_count`와 정확히 일치), `place_id`/`source_*` 내부 필드 미노출.
`원본_모바일`/`원본_PC`는 둘 다 `max_row=1`(헤더만). 필드 채움 수(50건
기준): 업체명 50/업종 50/리뷰수 50/주소 50/대표전화 50/플레이스 URL 50/
수집일 50/인스타 21/홈페이지 14/블로그 3. **새로오픈여부는 50건 전부
빈칸(0)** - WIRE-4A에 이어 다시 한 번 문서 기록과 실제 live 결과가
일치함을 재확인했다.

## 시간 기록(settle_ms=5000 고정, 변경 없음)
`session_ready_seconds=0.96`, `orchestrator_seconds=17.77`(쿼리 3개 순차
실행 전체), `session_teardown_seconds=0.26`, `export_seconds=0.04`,
`total_wall_seconds=19.03`, `avg_query_wall_seconds=5.92`(쿼리 1개당
평균 - WIRE-4A의 단일 쿼리 6.13초와 유사한 수준이라 여러 쿼리 순차
실행에서도 쿼리당 소요시간이 크게 늘거나 줄지 않음을 확인했다). 속도
최적화는 work order 지시대로 이번 단계에서 진행하지 않았다.

## 재시도·우회 여부
**없음.** CAPTCHA 자동 해결/DOM 제거, context 재시작, proxy/stealth는
harness에 전혀 구현하지 않았다(이번 실행에서 CAPTCHA/429가 발생하지
않아 그런 분기 자체가 실행되지 않았다).

## production 코드 수정 여부
**무수정.** `src/**` 전체가 이번 단계에서도 결함 없이 실제 네이버와
정상 연결됨을 확인했다 - 4개 쿼리 순차 실행, 쿼리별 page 생성/종료,
global dedup, target 조기 종료, 단일 Excel 저장 전부 코드 수정 없이
설계대로 동작했다.

## WIRE-4B 최종 판정
**완전 PASS.** work order §7의 "완전 PASS" 조건(실행된 모든 query에서
candidate_response_count>=1, parse_error_count==0, CAPTCHA/429/
navigation_error 전부 False, final_count==50, stop_reason==target_reached,
Excel 50행/11헤더 정확 일치, 내부 메타 미노출, exporter 1회, session/
context 정상 종료, 쿼리별 page 생성·종료 정상, 재시도 0회)을 전부
만족했다.

## 다음 단계(WIRE-4C) 진행 가능 여부
**가능.** WIRE-4A(10건)·WIRE-4B(50건) 모두 완전 PASS로, 300건 기준선
검증(WIRE-4C)으로 진입할 최소 근거가 확보됐다. 다만 이번 표본도 여전히
강동구·카페·법정동 4개·1회 실행이라는 단일 조건이므로, 300건 규모에서는
더 많은 쿼리가 순차 실행되는 만큼 CAPTCHA/429 발생 가능성이 커질 수
있다는 점(PoC 단계에서도 반복 실행 누적 시 차단 위험이 관찰된 바 있음)을
WIRE-4C 설계 시 감안해야 한다. 속도 최적화 판단은 여전히 WIRE-4C의
300건 기준선 확보 이후로 유보한다.

---

# 2026-07-15 ARCH-300C WIRE-4C 실제 Network 제품 경로 300건 단일 기준선 live 실행

## 배경
WIRE-4A(10건)·WIRE-4B(50건, 쿼리 4개)에 이어 이번 단계는 Tier1(법정동)→
Tier2(역·상권)→Tier3(세부업종) 3단 큐 최대 24개로 target_count=300을
실제 네이버에서 검증했다. PoC-7(2026-07-09)이 동일 구조로 이미 성공한
적이 있는 실험이며, 이번 WIRE-4C는 그 결과를 production 코드 경로
(`NetworkBrowserCollector`→`collect_network_query`→`run_collection_plan`→
`export_places_to_excel`)로 재현했다. 정확히 1회만 실행했고 재시도/우회는
구현하지 않았다.

## 변경 파일
- 신규 `scratchpad/arch300_network_probe/wire4c_product_live_300.py`:
  WIRE-4B harness를 재사용해 24-job 3단 큐 + tier별 진단 집계를 추가한
  단발성 live harness.
- 신규 `scratchpad/arch300_network_probe/wire4c_live_300_result_20260715_165906.json`:
  이번 실행의 전체 결과·쿼리별 로그.
- 신규 `output/wire4c_live_300_20260715_165906.xlsx`: 실제 저장된 300행 Excel.
- `PROJECT_STATE.md`: 이번 기록 append.
- production 코드(`src/**`)는 **전혀 수정하지 않았다.**

## 실행 환경 및 사전 회귀
`.venv\Scripts\python.exe`(3.14.3) 기준으로만 실행. live 실행 전 최소
회귀 3건(`test_network_product_integration_no_live.py` 11/11,
`test_pc_network_browser_collector.py` 24/24, `test_pc_network_pipeline.py`
12/12) 전부 PASS 확인 후에만 live를 실행했다.

## 큐 구성 - work order 본문과의 차이 및 근거(투명성 기록)
work order 본문의 Tier1/Tier3 목록을 실제 `data/regions_kr_sample.json`
(현재 지역 데이터)과 `scratchpad/arch300_network_probe/poc7_target_300_probe.py`
(PoC-7 실제 성공 스크립트)에 직접 대조한 결과 두 가지 차이를 발견해
반영했다:

1. **Tier3 "베이커리카페" 누락**: work order 본문은 Tier3를 6개(천호동/
   길동/성내동 × 디저트카페/브런치카페)만 나열했지만, `regions_kr_sample.json`
   의 `subcategory_keywords`는 `["디저트카페","브런치카페","베이커리카페"]`
   3개이고, `poc7_target_300_probe.py`의 `SUBCATEGORIES`도 동일 3개다.
   PoC-7의 실제 성공 큐는 Tier1(9)+Tier2(6)+Tier3(9)=24개였다(work order도
   "PoC-7의 전체 24개 큐"라고 언급). "베이커리카페" 3개 job을 추가해 9개로
   완성했다.
2. **Tier1/Tier3 동 순서**: work order 본문은 Tier1을 가나다순(강일동→
   고덕동→길동→...)으로, Tier3 동 순서를 천호동→길동→성내동으로 나열했지만,
   `poc7_target_300_probe.py`의 실제 `LEGAL_DONGS`/`SUBCATEGORY_DONGS`는
   천호동을 첫 항목으로 하는 순서(천호동→성내동→길동→암사동→명일동→고덕동→
   상일동→둔촌동→강일동 / Tier3는 천호동→성내동→길동)이며, 이는 현재
   `regions_kr_sample.json`의 `legal_dongs` 순서와도 정확히 일치한다.
   §3의 "PoC-7 성공 순서를 기준으로" 지시를 우선해 PoC-7 실제 순서를
   채택했다(Tier2 역/상권 순서는 work order 본문과 PoC-7이 이미 동일해
   차이 없음).

두 차이 모두 **live 실행 전에 큐를 확정**한 뒤 반영했으며, 실행 중에는
전혀 수정하지 않았다. job dict의 키 이름(`source_city`/`source_district`/
`source_subregion`/`source_layer`)은 `collect_network_query`가 실제로
읽는 키와 정확히 맞췄다(PoC 전용 `region_expander.py`의 `city`/`gu`/`dong`
키 이름은 그대로 재사용하지 않고 검색어 문자열·순서만 대조 근거로 삼음).

## live 실행 횟수
**정확히 1회.** `retries: 0`을 결과 JSON에 명시. 재실행 없음.

## 전체 고정 job 수와 tier 구성
총 24개(Tier1 9 / Tier2 6 / Tier3 9).

## 실행·스킵 수
`executed_query_count=17`(PoC-7의 live 결과와 정확히 동일한 실행 쿼리
수), `skipped_query_count=7`. 17번째 쿼리(천호동 브런치카페, Tier3)
직후 `before_trim_count=308>=target=300`으로 즉시 멈췄고, 남은 7개
(천호동 베이커리카페 + 성내동/길동 세부업종 6개)는 harness의
`recording_collect_query` wrapper 자체가 호출되지 않아 로그에도 17건만
기록됐다 - 코드 레벨로 미실행이 직접 증명된다.

## tier별 효율
| tier | 실행 수 | raw 합 | local_unique 합 | returned_rows 합 | global 신규(진단) 합 |
|---|---|---|---|---|---|
| tier1(법정동) | 9 | 180 | 180 | 180 | 180 |
| tier2(역/상권) | 6 | 150 | 150(일부 raw 26 중 로컬 dedup 후) | 120(per_query_limit=20 cap) | 104 |
| tier3(세부업종) | 2 | 40 | 40 | 40 | 24 |

Tier1(법정동)은 신규 기여율 100%(중복 없음), Tier2(역/상권)는 cap 이후도
평균 약 87%가 새 업체, Tier3(세부업종, 이번엔 천호동 2개 쿼리만 실행)는
동일 법정동을 다시 훑는 특성상 신규 기여가 60%로 가장 낮았다 - PoC-6/7의
"Tier2 > Tier3 효율" 관찰과 방향이 일치한다.

## before_trim/final_count
`before_trim_count=308`, `final_count=300`(정확히 300으로 trim).

## stop_reason
`"target_reached"`.

## CAPTCHA/429/navigation/parse 상태
`security_blocked=False`, `status_429_seen=False`, `navigation_error=False`
(17개 쿼리 전부). **`parse_error_count_total=1`**(12번째 쿼리, Tier2
"둔촌동역 카페"에서 candidate 응답 2개 중 1개가 JSON 파싱에 실패 -
`collect_network_query`가 이미 방어적으로 설계된 대로 예외를 삼키고
`parse_error_count`만 증가시킨 뒤 나머지 candidate로 정상 진행했다).
이 쿼리의 `local_unique_count=20`, `efficiency_ratio=0.9`로 결과 품질에
실질적 영향은 없었고, 이후 쿼리 실행이나 최종 300건 도달에도 전혀
지장이 없었다 - 재시도/우회 없이 설계된 방어 로직만으로 흡수됐다.

## Excel 생성 및 행 수
생성됨(`output/wire4c_live_300_20260715_165906.xlsx`). `통합_결과` 데이터
행 **300개**(`final_count`와 정확히 일치), 헤더 11개가 `MERGED_COLUMNS`와
정확히 일치, `place_id`/`source_*` 내부 필드 미노출. `원본_모바일`/
`원본_PC`는 둘 다 `max_row=1`(헤더만).

## 필드 채움 수(300건 기준)
업체명 300/업종 300/리뷰수 300/주소 300/플레이스 URL 300/수집일 300,
대표전화 279(21건 빈칸), 홈페이지 94, 인스타 80, 블로그 32,
**새로오픈여부 0/300**(WIRE-4A/4B와 동일하게 항상 빈칸 재확인).

## 전체/쿼리별 시간
`session_ready_seconds=0.67`, `orchestrator_seconds=99.71`(쿼리 17개
순차 실행 전체), `session_teardown_seconds=0.25`, `export_seconds=0.06`,
`total_wall_seconds=100.72`, `avg_query_wall_seconds=5.87`,
`rows_per_second≈2.98`, `seconds_per_final_row≈0.336`,
`estimated_settle_seconds=85.0`(실행된 17개 × settle_ms=5000 고정).

## WIRE-4A/4B 대비 속도 비교
쿼리당 평균 소요시간이 WIRE-4A(6.13s, 1쿼리) → WIRE-4B(5.92s, 3쿼리
평균) → WIRE-4C(5.87s, 17쿼리 평균)로 **쿼리 수가 늘어나도 쿼리당
소요시간이 거의 동일하게 유지**됐다(성능 저하나 누적 지연 없음). 이는
production 코드가 쿼리 간 상태를 누적하거나 지연시키는 부작용 없이
동일 context에서 안정적으로 반복 실행됨을 보여준다.

## 고정 settle 추정 비중
`estimated_settle_seconds=85.0` / `orchestrator_seconds=99.71` ≈ **85.3%**
- 쿼리 실행 시간의 대부분이 고정 5초 settle 대기이며, 실제 page 생성/
goto/파싱/CAPTCHA probe에 쓰이는 시간은 쿼리당 약 0.87초 수준으로 작다.
이는 향후 PERF-1에서 settle_ms를 조정할 경우 가장 큰 개선 여지가 있는
지점임을 시사하지만, 이번 단계에서는 지시대로 어떤 코드도 최적화하지
않았다.

## 가장 낮은 효율 쿼리
13번째 쿼리(Tier2, "서울특별시 강동구 암사역 카페") - `efficiency_ratio≈0.577`,
`global_unique_added=15`(raw 26건 중 신규 15건, 나머지는 이미 다른
법정동/역상권 쿼리와 겹침). PoC 단계에서도 역/상권 쿼리는 인접 법정동과
지리적으로 겹쳐 중복이 더 많이 발생한다고 관찰된 바와 일치한다.

## session/page 종료
정상 종료(예외 없이 완료, exit code 0). `NetworkBrowserCollector`가
쿼리 17개 동안 브라우저/context 1개를 공유하고 쿼리마다 새 page를
생성·종료하는 계약이 300건 규모에서도 그대로 유지됨을 확인했다(개별
page 생성/종료 횟수를 별도로 assert하는 로직은 WIRE-3 no-live 테스트에서
이미 검증되어 있어 이번 live harness에서는 세션 정상 종료 여부만 관찰).

## 재시도·우회 여부
**없음.** CAPTCHA 자동 해결/DOM 제거, context 재시작, proxy/stealth,
쿼리 재실행은 harness에 전혀 구현하지 않았다. 12번째 쿼리의 parse error
1건도 재시도 없이 production의 기존 방어 로직만으로 처리됐다.

## production 코드 수정 여부
**무수정.** `src/**` 전체가 이번 300건 규모에서도 결함 없이 실제
네이버와 정상 연결됨을 확인했다. settle_ms(5000)와 쿼리 순서도 전혀
변경하지 않았다.

## WIRE-4C 최종 판정
**완전 PASS 기준 중 `parse_error_count 총합 == 0` 한 항목만 미충족
(실제 1건)** - 그 외 모든 완전 PASS 조건(final_count==300,
stop_reason==target_reached, before_trim_count>=300, 남은 query 미실행,
실행된 모든 query candidate_response_count>=1, active CAPTCHA==False,
HTTP 429==False, navigation_error==False, Excel 300행/11헤더/내부 메타
미노출, 원본_모바일·원본_PC 헤더만, exporter 1회, session/context/page
정상 종료, retries=0)은 전부 충족했다. parse_error 1건은 방어적으로
이미 설계된 예외 흡수 로직이 정상 동작한 결과이며(재시도/데이터 손상
없음, 최종 300건 도달에 영향 없음), production 코드 문제라기보다
실제 네이버 응답의 자연스러운 변동성(2개 candidate 중 1개의 JSON 형식
이상)으로 판단한다 - 다만 엄격한 수치 기준으로는 "완전 PASS"라고
단정하지 않고 이 사실을 그대로 보고한다.

## PERF-1 진행 가능 여부
**가능.** WIRE-4A(10)·WIRE-4B(50)·WIRE-4C(300) 전 구간에서 target_count
조기 종료, global dedup, 단일 Excel 저장, CAPTCHA/429/navigation_error
안전 중단 계약이 실제 네이버에서 일관되게 검증됐다. 고정 settle 비중이
전체 쿼리 시간의 약 85%를 차지한다는 이번 관찰이 PERF-1(속도 최적화)의
1차 근거가 될 수 있다. 1건의 parse_error가 이번 단계의 유일한 미해결
관찰 사항이며, production 코드 수정 여부(예: 발생 빈도가 잦다면 원인
조사)는 사용자 판단 이후 별도 단계에서 결정한다.

---

# 2026-07-16 ARCH-300C PERF-1A 적응형 Network settle 구현(no-live, Opus 4.8 반대 검토 포함)

## 배경
WIRE-4C 실측에서 `collect_network_query`의 고정 `settle_ms=5000` 대기가
쿼리 실행 시간의 약 85.3%를 차지함을 확인했다(쿼리당 실제 유효 작업은
평균 0.87초 수준). 이번 단계는 이 고정 대기를 "파싱 가능한(비어있지 않은)
업체 목록 응답을 확인한 뒤 quiet period가 지나면 조기 종료"하는 적응형
방식으로 바꾸되, 응답이 없거나 확인이 안 되면 기존과 동일하게 최대
settle_ms(hard cap)까지 대기하도록 구현했다. 실제 live 실행은 하지 않았다
(no-live 코드+테스트 단계).

## 변경 파일
- `src/pc/network_browser_collector.py`: `collect_network_query`의
  `page.wait_for_timeout(settle_ms)` 고정 대기 한 줄을 적응형 폴링 루프로
  교체. 모듈 상수 `_QUIET_PERIOD_MS=750`, `_POLL_INTERVAL_MS=100` 추가.
  반환 dict에 `adaptive_settle_wait_ms`/`adaptive_settle_early_exit` 2개
  필드 추가(모든 반환 경로 - navigation_error 조기 반환 포함 - 동일한
  키 집합 유지). 함수 시그니처(`collect_network_query(page, job,
  per_query_limit, *, collected_at, settle_ms=5000)`)는 완전히 그대로다.
- 신규 `tests/test_pc_network_adaptive_settle.py`: fake-clock 기반
  `FakeAdaptivePage`로 적응형 로직의 핵심 분기를 실제 대기 없이 검증하는
  14개 테스트.
- `PROJECT_STATE.md`: 이번 기록 append.
- `tests/test_pc_network_browser_collector.py`/`tests/test_network_product_integration_no_live.py`
  는 수정이 필요 없어(기존 assert가 대기 시간/tick 수를 검사하지 않음)
  **그대로 재실행만 하고 무수정**으로 뒀다.
- `src/ui.py`/`src/exporter.py`/`src/pc/browser_session.py`/
  `src/pc/network_list_scraper.py`/`src/pc/network_pipeline.py`/
  `README.md`/`LEGAL_NOTICE.md`/`app.py`/live harness 파일/UI 기본값/
  query queue 순서는 **전혀 건드리지 않았다.**

## 현재 흐름 도식화(수정 전)
`page.on("response", handler)` 등록 → `page.goto(url, wait_until=
"domcontentloaded", timeout=40000)`(PlaywrightTimeoutError는 관용적으로
흡수, 그 외 예외는 즉시 navigation_error 반환) → **`page.wait_for_timeout
(settle_ms)` 고정 5초 대기**(handler는 이 동안 계속 status_429_seen/
candidate_responses만 누적, `.json()`은 안 부름) → 대기 종료 후 모든
candidate를 순회하며 `response.json()` + `_extract_list_items()`로 raw_items
수집(parse_error_count 집계) → `_probe_captcha_state` → 매핑/로컬 dedup/cap
→ 반환 → `finally`에서 `page.off()`.

## Opus 4.8 반대 검토 결과 및 반영
구현 전 Agent 도구로 Claude Opus 4.8에 계획을 반대 검토시켰다(코드는
전혀 작성하지 않은 상태에서 계획 텍스트만 검토, 실제 소스 파일들을 직접
대조해 확인). 지정된 8개 항목 중 7개는 결함 없음으로 확인됐고, **1개
항목에서 실제 정확성 결함을 발견**했다:

- **[반드시 수정] "candidate는 있으나 result.place.list가 없는 경우"를
  valid로 취급하기로 한 원래 계획의 결정이 위험하다는 지적**: `is_candidate_response`
  의 URL 토큰 매칭이 넓어서(`pcmap` 등) 실제 업체 목록이 아닌 응답도
  candidate로 잡힐 수 있다. "파싱만 성공하면(빈 목록이어도) valid"로
  정의하면, 이런 decoy 응답 때문에 quiet period 후 조기 종료해버려서
  그 뒤에 도착하는 **진짜 데이터가 담긴 응답을 통째로 놓칠 위험**이 있다는
  지적이었다. → **valid 정의를 "파싱 성공 AND 추출된 목록이 비어있지
  않음"으로 좁혀 반영**했다(코드/docstring/신규 테스트 전부 이 정의로
  작성됨).
- [권장, 반영] navigation_error 조기 반환 경로에도 `adaptive_settle_wait_ms=0`,
  `adaptive_settle_early_exit=False` 기본값을 포함해 모든 반환 경로의
  키 집합을 동일하게 유지(향후 무조건 접근 시 KeyError 예방).
- [권장, 반영] 테스트에 "valid 후보 2개가 quiet period를 넘는 간격으로
  도착 → 두 번째는 유실"이라는 **알려진 트레이드오프를 명시적으로
  고정(pin)하는 테스트**를 추가(회귀 감지용).
- [권장, 반영] `elapsed_ms`가 실제 벽시계 시간이 아니라 폴링 대기(wait_for_timeout
  호출)의 누적 합임을 함수 docstring에 명시.
- [문제 없음으로 확인] 규칙 4(첫 후보 parse error 시 조기 종료 안 함),
  HTTP 429 감지 시점(폴링 루프 종료 시점과 무관하게 handler가 실시간으로
  잡음), callback 안 `.json()` 미호출, fake-clock 테스트 가능성(설계
  유효, 추가 시나리오 반영), `timeout` 필드 의미 보존, 기존 9개 반환
  필드/호출자(NetworkBrowserCollector, run_collection_plan) 호환성.
- **데이터 공백으로 남은 것(Opus 명시)**: candidate 응답 간 실제 도착
  간격(750ms 적정성의 실측 근거), 폴링 방식이 실제 Playwright 이벤트
  dispatch를 정상 수신하는지, `response.json()` 블로킹 시간 - 이 세
  가지는 no-live 테스트로 검증 불가능하며 다음 live 단계(PERF-1B 또는
  WIRE-5)에서 반드시 실측해야 한다고 명시했다. 이 사실을 코드 주석과
  아래 "다음 단계"에도 남겼다.

## 적응형 종료 계약(구현 요약)
`_ensure_parsed(index)`가 candidate 응답 하나당 `response.json()`/
`_extract_list_items()`를 정확히 1회만 호출하도록 메모이즈한다(폴링
루프의 "peek" 확인과 이후 harvest 단계가 캐시를 공유 - 중복 파싱/중복
`parse_error_count` 집계 방지). 폴링 루프는 `_POLL_INTERVAL_MS`(100ms)
간격으로 `page.wait_for_timeout`을 반복 호출하며, 매 tick마다: (1) 새
candidate가 도착했으면 그 후보들을 파싱해 "성공 + 비어있지 않음"이 하나라도
있으면 `valid_list_confirmed=True`로 표시하고, 새 candidate 도착 자체는
valid 여부와 무관하게 quiet 타이머를 리셋한다(규칙 5). (2) 새 candidate가
없고 이미 valid가 확인된 상태면 quiet 누적 시간을 늘리고, `_QUIET_PERIOD_MS`
(750ms)에 도달하면 즉시 break한다. candidate가 전혀 없거나 끝까지 valid로
확인되지 않으면 `elapsed_ms < settle_ms` 조건에 의해 자연스럽게 hard cap
(기존 5초)까지 전부 대기한다(회귀 없음). 루프 종료 후 harvest(raw_items/
parse_error_count 산출), `_probe_captcha_state`, dedup/cap, `timeout` 계산은
전부 기존과 동일한 순서·로직을 그대로 유지했다.

## 호환성 확인
- 함수 시그니처 무변경, `settle_ms` 기본값 5000 무변경.
- 기존 9개 반환 필드(rows/active_captcha_detected/status_429_seen/
  candidate_response_count/raw_item_count/local_unique_count/
  parse_error_count/timeout/navigation_error/navigation_error_message)
  이름·의미 전부 무변경. 신규 필드 2개는 추가만 됨(삭제·이름 변경 없음).
- `NetworkBrowserCollector.collect_query`는 `collect_network_query(page,
  job, per_query_limit, collected_at=self.collected_at,
  settle_ms=self.settle_ms)`로 무수정 그대로 호출.
- `run_collection_plan`은 `result.get("navigation_error")`/`"rows"`/
  `"active_captcha_detected"`/`"status_429_seen"`만 읽으므로 신규 필드
  추가로 인한 영향 없음(무수정).
- `response callback`(`_make_response_handler`)은 이번 단계에서 전혀
  수정하지 않았고, 여전히 status/url/resource_type만 확인 - `.json()`은
  폴링 루프의 메인 동기 흐름(peek/harvest)에서만 호출됨을 소스 기반
  테스트(`check_response_handler_does_not_call_json`)로 재확인했다.

## 알려진 트레이드오프(의도된 설계, 문서화 완료)
quiet period가 지나 조기 종료한 "직후"에 두 번째 candidate가 도착하면
그 응답은 수집되지 않는다(harvest가 이미 끝난 뒤이므로) - 기존 고정
5초 대기는 이 경우를 항상 잡았을 수 있다. 이는 속도 최적화가 감수하는
알려진 트레이드오프이며, `check_second_valid_candidate_beyond_quiet_period_is_lost`
테스트로 이 동작 자체를 회귀 없이 고정해 뒀다. candidate 간 실제 도착
간격이 750ms보다 얼마나 큰/작은 경우가 실제로 있는지는 아직 live로
계측되지 않았다.

## 신규 테스트 결과
`tests/test_pc_network_adaptive_settle.py`(신규) **14건 전부 PASS**:
모듈 상수 확인 / 단일 valid 후보 조기 종료(9틱, hard cap 50틱보다
훨씬 적음) / parse error만 있으면 hard cap 폴백 / candidate 0건이면
hard cap 폴백(timeout 의미 보존) / 늦게 도착한 valid 후보로 quiet
재시작(11틱) / quiet 이내 valid 후보 2개 모두 수집(12틱) / **quiet 초과
간격 두 번째 후보 유실 고정**(알려진 트레이드오프) / hard cap 직전(4900ms)
후보도 harvest에서는 정상 수집 / response.json() candidate당 정확히
1회(중복 집계 없음) / **빈 목록 candidate는 valid로 취급 안 됨**(반대
검토 결함 수정 확인) / 빈 목록 decoy 이후 지연 도착한 진짜 데이터가
유실 없이 정상 수집(수정 효과 확인) / navigation_error 경로 필드
기본값 포함 / CAPTCHA 판정 무영향 / response callback 소스에 `.json(`
미호출 확인.

## 전체 회귀 결과
- `python -m py_compile src/pc/network_browser_collector.py tests/test_pc_network_browser_collector.py tests/test_pc_network_adaptive_settle.py tests/test_network_product_integration_no_live.py` PASS.
- `tests/test_pc_network_browser_collector.py` 24건 전부 PASS(무수정 파일,
  적응형 구현으로도 회귀 없음 - 기존 assert가 대기 시간을 검사하지
  않아 그대로 통과).
- `tests/test_pc_network_adaptive_settle.py`(신규) 14건 전부 PASS.
- `tests/test_network_product_integration_no_live.py` 11건 전부 PASS(무수정,
  실제 NetworkBrowserCollector/run_collection_plan/export_places_to_excel을
  쓰는 통합 시나리오도 회귀 없음).
- `tests/test_pc_network_pipeline.py` 12건, `tests/test_pc_network_list_scraper.py`
  39건, `tests/test_ui_network_start.py` 12건, `tests/test_ui_network_wiring.py`
  19건, `tests/test_ui_network_export.py` 7건, `tests/test_ui_policy_text.py`
  13건, `tests/test_ui_query_builder.py` 9건, `tests/test_ui_pc_full_wiring.py`
  4건 - 전부 PASS(무영향).
- 총 164개 검증 항목 전부 PASS, FAIL 0.

## production 코드 수정 여부
`src/pc/network_browser_collector.py` **1개 파일만** 수정했다(허용 범위
내). `src/pc/network_list_scraper.py`/`src/pc/network_pipeline.py`는
가능하면 수정하지 말라는 지시대로 **무수정**(실제로 수정할 필요가 전혀
없었다 - 적응형 로직은 `collect_network_query` 내부에만 존재).

## live 실행 여부
**전부 실행 안 함.** 이번 단계는 코드 구현 + no-live fake-clock 테스트만
수행했다(요청서 §10 지시대로).

## 다음 단계(반드시 live로 확인해야 할 것)
Opus 4.8이 지적한 3가지 데이터 공백을 실측하는 live 검증 단계가 필요하다:
(1) candidate 응답 간 실제 도착 간격 분포(750ms quiet_period가 적정한지),
(2) 100ms 간격 폴링이 실제 Playwright response 이벤트를 정상적으로
수신하는지(현재 no-live 테스트는 fake clock이라 이 부분을 검증하지
못함), (3) `response.json()`의 실제 블로킹 시간. 이 실측 없이는 이번
PERF-1A의 실제 속도 개선폭(WIRE-4C 기준 85% 절감 잠재력 중 실제 달성
가능한 비율)을 확정할 수 없다.

---

# 2026-07-16 ARCH-300C PERF-1A 커밋 전 보완 검증(non-candidate 429 계약 + .venv 전체 재검증)

## 목표
- quiet period 진행 중 도착하는 non-candidate HTTP 429 감지 계약을
  fake-clock 테스트로 추가.
- 프로젝트 `.venv` 실행기(`.\.venv\Scripts\python.exe`)로 PERF-1A 관련
  전체 회귀를 처음부터 다시 검증.
- 반대 검토(Opus 4.8)는 이번 단계에서 다시 수행하지 않았다 - PERF-1A
  본 구현은 이전 단계에서 이미 반대 검토를 마쳤고, 이번은 그 위에 테스트
  1건을 보강하는 최소 작업이었다.

## 변경 파일
- `tests/test_pc_network_adaptive_settle.py`: 신규 테스트 1건 추가
  (`check_non_candidate_429_during_quiet_period_is_detected`), main()
  등록 목록에 추가. 나머지 14건은 무수정.
- `PROJECT_STATE.md`: 이번 보완 기록 append.
- `src/pc/network_browser_collector.py`: **무수정** - 신규 테스트가
  production 결함을 재현하지 않아 수정할 이유가 없었다(§아래 "테스트
  시나리오" 참고).

## 테스트 시나리오
`FakeAdaptivePage`에 두 응답을 예약: (1) ms=0에 정상 valid candidate
(파싱 성공, 비어있지 않은 목록 1건), (2) ms=400(quiet period 진행 중,
아직 조기 종료 전)에 **candidate가 아닌 URL/resource_type**의 HTTP 429
응답(`FakeResponse("https://map.naver.com/", 429, "document")` - 기존
`tests/test_pc_network_browser_collector.py`의 non-candidate 429 테스트와
동일한 값 재사용).

## 테스트가 검증한 정확한 계약
- `result["status_429_seen"] is True` - candidate가 아닌 URL이어도 429
  상태 코드만으로 감지됨(`_make_response_handler`가 상태 코드 확인을
  `is_candidate_response` 판별보다 먼저, 독립적으로 수행하기 때문).
- `result["candidate_response_count"] == 1` - 429 응답이 candidate로
  잘못 집계되지 않음(1건 그대로, 정상 candidate 1개만 유지).
- `result["parse_error_count"] == 0`, `len(result["rows"]) >= 1`,
  `result["timeout"] is False`, `result["navigation_error"] is False` -
  429 도착이 기존 결과 필드에 부작용을 남기지 않음.
- `result["adaptive_settle_early_exit"] is True`,
  `result["adaptive_settle_wait_ms"] < 5000` - 429 도착과 무관하게 정상
  조기 종료됨.
- **`len(page.wait_calls) == 1 + _QUIET_TICKS`(9틱)** - 429가 전혀 없었던
  기존 `check_single_valid_candidate_exits_early` 테스트와 정확히 동일한
  tick 수. 이는 candidate가 아닌 429 도착이 quiet 타이머를 "새 candidate
  도착"처럼 재시작시키지 않았음을 직접 증명한다(재시작됐다면 tick 수가
  더 많이 나왔을 것).
- `non_candidate_429.json_call_count == 0` - 429 응답 자체에 대해
  `response.json()`이 전혀 호출되지 않음(429 판정은 상태 코드만으로
  끝나며, candidate가 아니므로 harvest 대상에도 포함되지 않음 -
  callback 안에서든 밖에서든 무거운 파싱이 발생하지 않음을 재확인).

## production 코드 추가 수정 여부
**수정하지 않았다.** 신규 테스트가 첫 실행에서 바로 PASS했다 - 기존
구현(`_make_response_handler`가 429 상태 확인을 candidate 판별과 완전히
분리해 무조건 먼저 수행하는 구조, PERF-1A 이전부터 있던 로직이며 이번
단계에서 전혀 건드리지 않음)이 이미 이 계약을 만족하고 있었다.

## 신규 적응형 테스트 PASS / FAIL
`tests/test_pc_network_adaptive_settle.py`: **15건 전부 PASS, FAIL 0**
(기존 14건 + 신규 429 테스트 1건).

## 전체 회귀 파일별 PASS / FAIL(전부 `.\.venv\Scripts\python.exe`로 실행)
| 파일 | PASS | FAIL | 결과 |
|---|---|---|---|
| tests/test_pc_network_browser_collector.py | 24 | 0 | PASS |
| tests/test_pc_network_adaptive_settle.py | 15 | 0 | PASS |
| tests/test_network_product_integration_no_live.py | 11 | 0 | PASS |
| tests/test_pc_network_pipeline.py | 12 | 0 | PASS |
| tests/test_pc_network_list_scraper.py | 39 | 0 | PASS |
| tests/test_ui_network_start.py | 12 | 0 | PASS |
| tests/test_ui_network_wiring.py | 19 | 0 | PASS |
| tests/test_ui_network_export.py | 7 | 0 | PASS |
| tests/test_ui_policy_text.py | 13 | 0 | PASS |
| tests/test_ui_query_builder.py | 9 | 0 | PASS |
| tests/test_ui_pc_full_wiring.py | 4 | 0 | PASS |

모든 파일 exit code 0.

## 전체 PASS 합계
**165건 전부 PASS, FAIL 0**(이전 기록 164건 + 신규 429 테스트 1건).
이전 PERF-1A 기록의 "164건"은 그 시점의 정확한 결과로 그대로 유지하며
수정하지 않았다.

## 사용한 Python 실행 경로
`C:\code\naver-place-sales-db-crawler-v1\.venv\Scripts\python.exe`
(3.14.3) - `sys.executable`로 직접 확인. bare `python`/시스템 Python은
사용하지 않았다.

## live 여부
**전부 실행 안 함.** 실제 네이버 접속, 업체 데이터 JSON·Excel 생성 없음.

## Git 상태
작업 시작 시점과 종료 시점 모두 아래와 동일(신규 파일 1개 내용만 갱신,
파일 목록 변화 없음):
```
 M PROJECT_STATE.md
 M src/pc/network_browser_collector.py
?? tests/test_pc_network_adaptive_settle.py
```
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.

## 다음 단계
- 사용자 검토 후 PERF-1A(적응형 settle + 이번 429 보완 테스트) 커밋.
- 이후 PERF-1B: 실제 50건 규모 live 성능 비교(WIRE-4B 기준선 대비
  적응형 settle의 실제 절감폭 측정, Opus가 지적한 3가지 데이터 공백
  - candidate 도착 간격/폴링 이벤트 수신 정상성/`.json()` 블로킹 시간

---

# 2026-07-15 ARCH-300C PERF-1B 적응형 settle 실제 50건 live 성능 비교

## 목표
WIRE-4B(고정 5초 settle)와 동일한 4-job/50건 조건에서 PERF-1A 적응형
settle을 실제 네이버 환경에서 정확히 1회 실행해, 수집 정확성·안전
상태·Excel 정합성을 유지하면서 실제 성능 개선폭을 실측한다.

## 실행 전 Git commit
`84c0e66e9bce9e7eebe5222b9ee2eaece935a78e`(PERF-1A 커밋, 실행 시점
`git status --short` clean 확인).

## 사용한 Python executable
`C:\code\naver-place-sales-db-crawler-v1\.venv\Scripts\python.exe`
(3.14.3) - `sys.executable`로 직접 확인.

## 고정 실행 조건
```
query 4개(천호동/길동/성내동/암사동 카페), 순서 WIRE-4B와 동일
per_query_limit = 20
target_count = 50
settle_ms = 5000(NetworkBrowserCollector 기본값과 동일, harness가 명시 전달)
quiet_period_ms = 750, poll_interval_ms = 100(변경 없음, production 상수 그대로)
브라우저/context 설정, dedup 방식, Excel 열 구조 변경 없음
```

## live 실행 횟수 / 재시도
**정확히 1회.** 자동·수동 재시도 0회. 실행 마커
`scratchpad/arch300_network_probe/results/perf1b/PERF1B_LIVE_STARTED.marker`
정상 생성 확인(실행 전 부재 → 실행 직전 생성 → 삭제하지 않음).

## 준비·실행·스킵 쿼리
```
total_job_count = 4
executed_query_count = 3
skipped_query_count = 1
before_trim_count = 60
final_count = 50
stop_reason = target_reached
exporter_call_count = 1
```

## 쿼리별 결과
| # | query | query_wall_s | candidate | raw | local_unique | parse_error | adaptive_wait_ms | early_exit | CAPTCHA | 429 | nav_error | timeout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 천호동 카페 | 2.63 | 1 | 20 | 20 | 0 | 1600 | True | False | False | False | False |
| 2 | 길동 카페 | 2.55 | 1 | 20 | 20 | 0 | 1600 | True | False | False | False | False |
| 3 | 성내동 카페 | 2.57 | 1 | 20 | 20 | 0 | 1600 | True | False | False | False | False |
| 4 | 암사동 카페 | - | - | - | - | - | - | - | 실행 안 함(target_reached로 스킵) |

## 시간 측정
```
session_ready_seconds     = 0.621
orchestrator_seconds      = 7.740
session_teardown_seconds  = 0.190
export_seconds            = 0.025
total_wall_seconds        = 8.586
avg_query_wall_seconds    = 2.580
```

## WIRE-4B(고정 5초) 대비 성능 비교
```
WIRE-4B total_wall_seconds     = 19.03
PERF-1B total_wall_seconds     = 8.586
total_wall_improvement_seconds = 10.44
total_wall_improvement_percent = 54.88%

WIRE-4B avg_query_wall_seconds     = 5.92
PERF-1B avg_query_wall_seconds     = 2.580
avg_query_improvement_seconds      = 3.34
avg_query_improvement_percent      = 56.42%

adaptive_wait_sum_ms      = 4800(3개 쿼리 × 1600ms)
fixed_wait_equivalent_ms  = 15000(3개 쿼리 × 5000ms)
wait_reduction_ms         = 10200
wait_reduction_percent    = 68.0%

early_exit_query_count = 3
hard_cap_query_count   = 0
```

## export 전 rows 중복 검증(production rows 기준)
```
rows_count = 50
place_id_present_count = 50, place_id_duplicate_count = 0
place_url_present_count = 50, place_url_duplicate_count = 0
```

## Excel 검증
```
통합_결과 헤더 11개, MERGED_COLUMNS와 순서·이름 완전 일치
통합_결과 데이터 행 수 = 50 = final_count
내부 필드(place_id/source_*) 미노출
플레이스 URL 중복 0건
원본_모바일/원본_PC 시트 유지(수집 안 함 - Network 엔진은 통합_결과 중심,
  기존 WIRE-4B/4C 결과와 동일한 패턴)
```

## 판정
```
기능 PASS: True(final_count=50, stop_reason=target_reached, exported=True,
  exporter_call_count=1, Excel 정합성 전부 충족, CAPTCHA/429/navigation_error
  전부 False)
적응형 settle 작동 PASS: True(early_exit_query_count=3 >= 1,
  adaptive_wait_sum_ms(4800) < 15000, 각 쿼리 wait_ms(1600) <= 5000)
성능 개선 PASS: True(total_wall 8.586 < 19.03, avg_query 2.580 < 5.92,
  wait_reduction_percent 68.0% > 0)
완전 무경고 PASS: True(parse_error_count_total=0, timeout_count=0,
  hard_cap_query_count=0)
```

## production 코드 수정 여부
**수정하지 않았다.** 이번 단계는 harness(`scratchpad/`)만 작성했고
`src/pc/network_browser_collector.py` 등 production 파일은 전혀 건드리지
않았다. live 실행 중 production 결함도 발견되지 않았다.

## Git 상태(작업 종료 시점)
작업 시작 전 이미 PERF-1A(`84c0e66`)가 커밋되어 있었다(이번 세션 사이에
사용자가 커밋한 것으로 확인). 이번 PERF-1B 단계에서 `git status --short`:
```
 M PROJECT_STATE.md
```
`scratchpad/`는 `.gitignore`(13번째 줄)에 등록되어 있어 harness
(`perf1b_adaptive_live_50.py`)와 결과 JSON/Excel/마커 파일 전부
`git status`에 나타나지 않는다(무시 대상이므로 untracked로도 표시되지
않음).
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.

## 다음 단계
- 사용자 검토 후 이번 PROJECT_STATE.md append 커밋 여부 결정.
- harness 파일(`perf1b_adaptive_live_50.py`)은 `scratchpad/`가
  gitignore 대상이므로 기본적으로 Git에 추가되지 않는다 - 별도로
  추적하고 싶다면 사용자가 명시적으로 지시해야 한다.
  - 실측 포함).

---

# 2026-07-15 ARCH-300C PERF-1C 적응형 settle 실제 300건 최종 성능 비교

## 목표
WIRE-4C(고정 5초 settle, 24-job/300건)와 동일한 조건에서 PERF-1A 적응형
settle을 실제 네이버 환경으로 정확히 1회 실행해, 대규모 다중 쿼리에서도
정확성·안전 계약·Excel 정합성을 유지하면서 최종 성능 개선폭을 실측한다.

## 실행 전 Git commit
`f936a55d3f98be668ab69045cb9cc47293374cb3`(PERF-1B 커밋, 실행 시점
`git status --short` clean 확인).

## 사용한 Python executable
`C:\code\naver-place-sales-db-crawler-v1\.venv\Scripts\python.exe`
(3.14.3) - `sys.executable`로 직접 확인.

## 고정 실행 조건
```
query 24개(Tier1 법정동 9 → Tier2 역/상권 6 → Tier3 세부업종 9),
  순서 WIRE-4C와 완전 동일(work order 본문도 이미 9+6+9로 정확해
  WIRE-4C 때와 달리 추가 대조·수정이 필요 없었음)
per_query_limit = 20
target_count = 300
settle_ms = 5000(harness가 명시 전달, production 기본값과 동일)
quiet_period_ms = 750, poll_interval_ms = 100(변경 없음)
브라우저/context 설정, dedup 방식, Excel 열 구조 변경 없음
```

## PERF-1C harness 경로
`scratchpad/arch300_network_probe/perf1c_adaptive_live_300.py`
(WIRE-4C의 Tier 큐 구성 + PERF-1B의 실행 마커/exporter counting
wrapper/성능 비교 계산 구조를 재사용해 신규 작성, 기존 두 harness는
무수정).

## --check-config 검증
BrowserSession/Playwright를 전혀 시작하지 않고 실행: query 24개
(tier1=9/tier2=6/tier3=9) 확인, tier 순서 정확, production import
5개 모듈 전부 성공, 마커 미생성 확인. PASS(exit 0).

## live 전 `.venv` 전체 회귀
11개 파일 전부 실행, **165 PASS, FAIL 0**(예상과 정확히 일치), 전 파일
exit code 0.

## live 실행 횟수 / 재시도
**정확히 1회.** 자동·수동 재시도 0회. 실행 마커
`scratchpad/arch300_network_probe/results/perf1c/PERF1C_LIVE_STARTED.marker`
BrowserSession 시작 전 원자적(`open(..., "x")`)으로 생성 확인, 삭제하지
않음.

## 전체 실행 결과
```
total_job_count = 24
executed_query_count = 17
skipped_query_count = 7
before_trim_count = 308
final_count = 300
stop_reason = target_reached
exporter_call_count = 1
```

## Tier별 결과
| tier | executed | raw_total | local_unique_total | returned_rows_total | global_unique_added_total | adaptive_wait_ms_total | query_wall_seconds_total |
|---|---|---|---|---|---|---|---|
| tier1(법정동) | 9/9 | 180 | 180 | 180 | 180 | 14100 | 22.68 |
| tier2(역/상권) | 6/6 | 120 | 120 | 120 | 104 | 9200 | 15.65 |
| tier3(세부업종) | 2/9(target_reached로 나머지 7개 스킵) | 40 | 40 | 40 | 24 | 3000 | 4.88 |

## 쿼리별 진단(17개 실행, 전부 adaptive_settle_early_exit=True)
| # | tier | query | wall_s | candidate | raw | parse_error | adaptive_wait_ms |
|---|---|---|---|---|---|---|---|
| 1 | tier1 | 천호동 카페 | 2.72 | 1 | 20 | 0 | 1600 |
| 2 | tier1 | 성내동 카페 | 2.54 | 1 | 20 | 0 | 1600 |
| 3 | tier1 | 길동 카페 | 2.52 | 1 | 20 | 0 | 1600 |
| 4 | tier1 | 암사동 카페 | 2.56 | 1 | 20 | 0 | 1600 |
| 5 | tier1 | 명일동 카페 | 2.42 | 1 | 20 | 0 | 1500 |
| 6 | tier1 | 고덕동 카페 | 2.41 | 1 | 20 | 0 | 1500 |
| 7 | tier1 | 상일동 카페 | 2.42 | 1 | 20 | 0 | 1500 |
| 8 | tier1 | 둔촌동 카페 | 2.55 | 1 | 20 | 0 | 1600 |
| 9 | tier1 | 강일동 카페 | 2.54 | 1 | 20 | 0 | 1600 |
| 10 | tier2 | 천호역 카페 | 2.66 | 1 | 20 | 0 | 1500 |
| 11 | tier2 | 강동역 카페 | 2.63 | 1 | 20 | 0 | 1600 |
| 12 | tier2 | 둔촌동역 카페 | 2.61 | 1 | 20 | 0 | 1600 |
| 13 | tier2 | 암사역 카페 | 2.55 | 1 | 20 | 0 | 1500 |
| 14 | tier2 | 고덕역 카페 | 2.63 | 1 | 20 | 0 | 1500 |
| 15 | tier2 | 명일역 카페 | 2.56 | 1 | 20 | 0 | 1500 |
| 16 | tier3 | 천호동 디저트카페 | 2.46 | 1 | 20 | 0 | 1500 |
| 17 | tier3 | 천호동 브런치카페 | 2.42 | 1 | 20 | 0 | 1500 |

전 쿼리 CAPTCHA=False, HTTP 429=False, navigation_error=False,
timeout=False.

## adaptive wait 분포
```
sample_count = 17
minimum_ms = 1500, median_ms = 1500, average_ms = 1547.06
p95_ms = 1600(nearest-rank, ceil(0.95*17)=17번째 값 - 표본이 작아 근사치)
maximum_ms = 1600
adaptive_metadata_missing_count = 0
```

## export 전 rows 중복 검증(production rows 기준)
```
rows_count = 300
place_id_present_count = 300, place_id_missing_count = 0, place_id_duplicate_count = 0
place_url_present_count = 300, place_url_duplicate_count = 0
```

## Excel 검증
```
통합_결과 헤더 11개, MERGED_COLUMNS와 순서·이름 완전 일치
통합_결과 데이터 행 수 = 300 = final_count
내부 필드(place_id/source_*) 미노출
플레이스 URL 중복 0건
새로오픈여부 = 전부 빈칸(300, 필터 영구 비활성 정책 유지)
필드 채움 수: 업체명 300/업종 300/리뷰수 300/주소 300/대표전화 279/
  플레이스 URL 300/수집일 300/홈페이지 94/인스타 80/블로그 32
원본_모바일/원본_PC 시트 유지(수집 안 함 - WIRE-4B/4C와 동일 패턴)
```

## PERF-1C 시간 측정
```
session_ready_seconds     = 0.719
orchestrator_seconds      = 43.198
session_teardown_seconds  = 0.219
export_seconds            = 0.058
total_wall_seconds        = 44.227
avg_query_wall_seconds    = 2.541
rows_per_second           = 6.783
seconds_per_final_row     = 0.147
```

## WIRE-4C(고정 5초) 대비 성능 비교
```
WIRE-4C total_wall_seconds        = 100.72
PERF-1C total_wall_seconds        = 44.227
total_wall_improvement_percent    = 56.09%

WIRE-4C orchestrator_seconds      = 99.71
PERF-1C orchestrator_seconds      = 43.198
orchestrator_improvement_percent  = 56.68%

WIRE-4C avg_query_wall_seconds    = 5.87
PERF-1C avg_query_wall_seconds    = 2.541
avg_query_improvement_percent     = 56.71%

adaptive_wait_sum_ms      = 26300(17개 쿼리)
fixed_wait_equivalent_ms  = 85000(17개 쿼리 × 5000ms)
wait_reduction_ms         = 58700
wait_reduction_percent    = 69.06%

early_exit_query_count = 17
hard_cap_query_count   = 0

rows_per_second: WIRE-4C 2.98 → PERF-1C 6.78
seconds_per_final_row: WIRE-4C 0.336 → PERF-1C 0.147
```
WIRE-4C와 PERF-1C는 다른 시점의 네이버 환경이므로 네트워크·서비스 상태
차이가 개선폭에 포함될 수 있다 - 이번 1회 결과를 일반적인 속도 보장으로
표현하지 않는다.

## PERF-1B 관찰과의 비교(참고용, 판정 기준 아님)
PERF-1B(50건) avg_query_wall=2.580s / adaptive_wait 평균 1600ms →
PERF-1C(300건) avg_query_wall=2.541s / adaptive_wait 평균 1547.06ms로
거의 동일한 수준을 유지했다 - 쿼리 수가 늘어나도(4→24개, 실행 3→17개)
쿼리당 성능이 저하되지 않았다.

## 판정
```
제품 기능 PASS: True(final_count=300, stop_reason=target_reached,
  exported=True, exporter_call_count=1, Excel 300행/11열 정합성 전부
  충족, place_id/URL 중복 0, 내부 필드 미노출, CAPTCHA/429/
  navigation_error 전부 False)
적응형 settle 작동 PASS: True(early_exit_query_count=17 >= 1,
  adaptive_wait_sum_ms(26300) < fixed_wait_equivalent_ms(85000),
  adaptive_metadata_missing_count=0, 전 쿼리 wait_ms <= 5000)
성능 개선 PASS: True(total_wall 44.227 < 100.72, orchestrator 43.198
  < 99.71, avg_query 2.541 < 5.87, wait_reduction_percent 69.06% > 0)
완전 무경고 PASS: True(parse_error_count_total=0, timeout_count=0,
  hard_cap_query_count=0) - WIRE-4C의 유일한 경고였던 parse_error 1건이
  이번에는 재현되지 않았다(같은 표본 없이 1회성 관찰이라 재현성을
  단정하지 않는다).
```

## 알려진 한계와 실제 관찰 사항
- WIRE-4C 대비 실행 쿼리 수가 17개로 동일(before_trim_count=308도 동일)
  했다 - 네이버 데이터 자체가 이전 실행과 거의 동일하게 유지되고 있음을
  시사하나, 시점이 다른 만큼 우연의 일치일 수 있다.
- WIRE-4C의 parse_error_count_total=1은 이번 PERF-1C에서 재현되지
  않았다. 적응형 settle이 이 문제를 "고쳤다"고 단정할 근거는 없다 -
  두 실행 모두 1회성 관찰이며, parse error는 특정 응답의 우연한 파싱
  실패였을 가능성이 더 높다.
- adaptive_settle_wait_ms가 1500~1600ms 좁은 범위에 몰려 있다 - quiet
  period(750ms) 도달까지 필요한 최소 폴링 틱(8틱=800ms) 근처에서 거의
  항상 조기 종료된다는 뜻이며, 이는 PERF-1B 관찰과 일치한다.

## production·tests 수정 여부
**둘 다 수정하지 않았다.** `src/pc/network_browser_collector.py` 등
production 파일과 `tests/*` 전부 무수정. live 실행 중 production 결함도
발견되지 않았다.

## Git 상태(작업 종료 시점)
작업 시작 전 이미 PERF-1B(`f936a55`)가 커밋되어 있었다. 이번 PERF-1C
단계에서 `git status --short`:
```
 M PROJECT_STATE.md
```
`scratchpad/`는 `.gitignore`(13번째 줄)에 등록되어 있어 harness
(`perf1c_adaptive_live_300.py`)와 결과 JSON/Excel/마커 파일 전부
`git status`에 나타나지 않는다.
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.

## 생성된 결과 파일
```
scratchpad/arch300_network_probe/perf1c_adaptive_live_300.py
scratchpad/arch300_network_probe/results/perf1c/PERF1C_LIVE_STARTED.marker
scratchpad/arch300_network_probe/results/perf1c/perf1c_adaptive_live_300_result_20260715_201511.json
scratchpad/arch300_network_probe/results/perf1c/perf1c_adaptive_live_300_20260715_201511.xlsx
```

## 다음 단계
- 사용자 검토 후 PERF-1A/1B/1C 관련 파일(production 코드, 테스트,
  PROJECT_STATE.md) 커밋 여부 결정.
- harness 파일들은 `scratchpad/`가 gitignore 대상이므로 기본적으로
  Git에 추가되지 않는다 - 별도 추적이 필요하면 사용자가 명시적으로
  지시해야 한다.
- WIRE-4C 대비 300건 규모에서도 56% 이상의 총시간 개선과 완전 무경고
  PASS를 확인했으므로, 이 시점에서 적응형 settle의 실측 검증 단계
  (PERF-1A/1B/1C)는 목표를 달성한 것으로 판단된다. 추가 단계 진행
  여부는 사용자 결정 사항이다.

---

# 2026-07-15 ARCH-300C UX-1 수집 설정 사용자 설명 개선

## 목표
"검색 조합당 수집 상한"·"전체 목표 저장 개수"·새로오픈 필터라는 세 설정의
의미와 차이를 일반 사용자가 UI 문구만으로 이해할 수 있도록 개선한다.
수집 로직·입력 검증·기본값·Excel 정책은 변경하지 않는다.

## 사용자 혼동 지점(work order 그대로)
1. "검색 조합"이 무엇인지 UI만으로 알기 어려움.
2. 검색 조합당 수집 상한과 전체 목표 저장 개수의 차이가 불명확.
3. 조합당 상한을 높이면 그 개수가 반드시 수집된다고 오해 가능.
4. 새로오픈업체 체크박스가 왜 비활성화됐는지 알 수 없음.
5. 검색 조합당 300 지원 여부는 LIMIT-300-A/B에서 별도 검증 예정 -
   UX-1에서 확정적으로 표현하지 않음.

## 변경 파일
- `src/ui.py`: `_build_filter_section`(새로오픈 안내),
  `_build_target_count_section`(검색 조합당 상한 안내),
  `_build_global_target_count_section`(전체 목표 저장 개수 안내 + 30/300
  예시) 3개 메서드의 설명 Label 텍스트만 수정. 위젯 생성 순서·row/grid
  배치·`state="disabled"`·`_DEFAULT_PER_QUERY_LIMIT`/`_DEFAULT_TARGET_COUNT`
  값·검색 조합 생성 로직·입력 검증 로직은 전혀 건드리지 않았다.
- `tests/test_ui_policy_text.py`: UX-1 신규 검증 12건 추가(아래 §테스트
  참고), `PER_QUERY_LIMIT_SECTION_SOURCE`/`GLOBAL_TARGET_COUNT_SECTION_SOURCE`/
  `FILTER_SECTION_SOURCE` 소스 상수 추가.
- `tests/test_ui_network_start.py`: 기존
  `check_new_open_filter_disabled_and_normalized`가 검사하던 정확한
  문자열("새로오픈 필터를 지원하지 않습니다")이 이번 문구 개선으로
  사라져 실제로 깨졌으므로, 검사 대상 문자열만 새 문구 일부
  ("정확하게 판별할 수 없어 사용할 수 없습니다")로 최소 교체했다.
  disabled 상태·new_open_checkbox 이름 검증 등 나머지 계약은 그대로
  유지(계약 약화 없음, work order §3 조건부 수정 허용 범위 내).

## 최종 적용한 사용자 문구

### 새로오픈업체(§_build_filter_section)
```
현재 버전에서는 새로오픈 여부를 정확하게 판별할 수 없어 사용할 수 없습니다.
Excel의 '새로오픈여부' 열은 유지되며 현재 결과에서는 빈칸으로 저장됩니다.
```
(체크박스 자체는 `state="disabled"` 그대로 유지, 초기값도 항상 False)

### 검색 조합당 수집 상한(§_build_target_count_section, "5. 검색 조합당 수집 상한")
```
검색 조합(지역+업종으로 만든 검색어 1개)마다 적용되는 최대 수집 상한입니다.
실제 수집 수는 검색 결과에 따라 이 값보다 적을 수 있습니다.
전체 저장 개수는 지역 수와 중복 제거 결과에 따라 달라집니다.
```

### 전체 목표 저장 개수(§_build_global_target_count_section, "6. 전체 목표 저장 개수")
```
여러 검색 조합의 결과를 합치고 중복을 제거한 뒤
Excel에 최종 저장할 최대 업체 수입니다.
목표 개수는 보장값이 아니며, 업종·지역 및 검색 결과에 따라 미달할 수 있습니다.
```

### 조합당 30 / 전체 300 예시(같은 섹션, 위 문구 바로 아래 별도 Label)
```
예) 조합당 30 / 전체 목표 300
→ 검색어마다 최대 30개씩 수집하고, 여러 결과를 합쳐
   중복 제거 후 전체 최대 300개를 저장합니다.
```

## 선택한 UI 표시 방식
work order §4.4의 A/B/C/D 중 **A(두 숫자 입력 영역 아래 공통 안내
문구)**를 선택했다 - "6. 전체 목표 저장 개수" 섹션은 사용자가 "5. 검색
조합당 수집 상한"을 이미 입력한 뒤 도달하는 위치이므로, 두 값의 관계를
설명하기에 가장 자연스러운 지점이라고 판단했다. 새 팝업/tooltip 시스템은
만들지 않았고, 기존 CTkLabel(text_color="gray", font size 11) 스타일과
"\n" 수동 줄바꿈 패턴을 그대로 재사용했다(저장소 전체에 wraplength 사용
사례가 없어 기존 패턴을 유지).

## UI 레이아웃 변경 내용
새 CTkFrame이나 새 grid row(섹션 단위)는 추가하지 않았다. 기존 3개
섹션의 설명 Label 텍스트 줄 수만 늘었다(새로오픈 1→2줄, 조합당 상한
2→3줄, 전체 목표 2→3줄 + 예시용 Label 1개 신규, row=2 추가). 좌측
패널이 `CTkScrollableFrame`이라 세로 길이 증가는 스크롤로 흡수되며,
가로 폭이 늘어나는 표현은 쓰지 않아 가로 스크롤 위험은 없다고 판단했다
(실제 창 렌더링 시각 확인은 아래 §수동 UI 확인 참고).

## 기능·입력 검증·기본값 무변경 확인
`_DEFAULT_COLLECTION_ENGINE`/`_DEFAULT_PER_QUERY_LIMIT`("30")/
`_DEFAULT_TARGET_COUNT`("300")/검색 조합 생성 로직/`_parse_positive_int`
입력 검증/Network 수집 로직/Excel 열·시트 구조/새로오픈여부 빈칸 정책
전부 무수정(`tests/test_ui_network_start.py::check_default_constants`,
`tests/test_ui_policy_text.py::check_ux1_default_values_unchanged` 등
기존+신규 테스트로 재확인).

## 새로오픈 체크박스 disabled 유지 확인
`_build_filter_section` 소스에 `state="disabled"`와 `new_open_checkbox`
식별자가 문구 개선 후에도 그대로 존재(`check_new_open_filter_disabled_and_normalized`,
`check_ux1_new_open_checkbox_disabled_contract_preserved` 둘 다 PASS).

## 테스트
`tests/test_ui_policy_text.py`에 UX-1 신규 검증 12건 추가:
1. `check_ux1_search_combination_defined` - 검색 조합=지역+업종 검색어
   1개 정의 존재
2. `check_ux1_per_query_limit_is_per_single_combination` - 조합당
   상한이 검색어 1개 기준 최대 수집 상한이라는 의미
3. `check_ux1_actual_count_may_be_lower` - 실제 수집 수가 더 적을 수
   있다는 안내
4. `check_ux1_global_target_aggregates_combinations` - 전체 목표가
   여러 검색 조합 통합 결과 기준이라는 의미
5. `check_ux1_global_target_dedup_then_save` - 중복 제거 후 Excel
   최종 저장 안내
6. `check_ux1_global_target_not_guaranteed` - 전체 목표가 보장값이
   아니라는 안내
7. `check_ux1_new_open_currently_unavailable` - 새로오픈 현재 사용
   불가(정확 판별 불가) 안내
8. `check_ux1_new_open_column_kept_blank` - Excel 새로오픈여부 열
   유지 + 빈칸 안내
9. `check_ux1_per_query_vs_global_example` - 조합당 30/전체 300 예시
   존재
10. `check_ux1_forbidden_phrases_absent_in_new_ui_text` - 새 UI
    문구에 금지 표현 없음(순수 주석 줄은 검사 대상에서 제외 - 기존
    개발자 주석 "'300개 보장'처럼 과장된 표현은 쓰지 않는다" 등 반례
    인용에 의한 오탐 방지)
11. `check_ux1_new_open_checkbox_disabled_contract_preserved` - disabled
    계약 유지
12. `check_ux1_default_values_unchanged` - 기본값 30/300 불변

## 테스트 파일별 PASS/FAIL(전부 `.\.venv\Scripts\python.exe`로 실행)
| 파일 | PASS | FAIL | 결과 |
|---|---|---|---|
| tests/test_ui_policy_text.py | 25 | 0 | PASS |
| tests/test_ui_network_start.py | 12 | 0 | PASS |
| tests/test_ui_network_wiring.py | 19 | 0 | PASS |
| tests/test_ui_query_builder.py | 9 | 0 | PASS |
| tests/test_ui_pc_full_wiring.py | 4 | 0 | PASS |

전체 PASS 합계: **69건, FAIL 0**. 모든 파일 exit code 0.

## 수동 UI 확인
실행하지 않았다. `run_app()`/`app.mainloop()`는 `SalesDbCrawlerApp.__init__`이
아니라 별도 진입점에서만 호출되고 `_build_ui()` 계열 메서드는 위젯
생성만 수행함을 소스로 확인해, UI를 실제로 열어도 Network/브라우저
수집이 자동 시작되지는 않을 것으로 판단했다. 다만 이번 세션에는 실제
창을 시각적으로 캡처·확인할 스크린샷 도구가 없어 텍스트 잘림/위젯
겹침/창 높이 부족 여부를 눈으로 검증하지 못했다 - work order §8의
대안대로 자동 테스트 결과와 코드 구조 확인만으로 보고하며, 실제 화면
확인은 별도 UX-QA 단계 후보로 남긴다.

## live 실행 여부
**전부 실행 안 함.** 실제 네이버·Playwright 접속 없음.

## production 수집 코드 수정 여부
**수정하지 않았다.** `src/pc/*`, `src/exporter.py`, `app.py`, Network
수집 로직, 검색 조합 생성 로직, 입력 검증 로직 전부 무수정. `src/ui.py`
안에서도 3개 메서드의 설명 Label 텍스트만 바꿨을 뿐 위젯 생성/데이터
흐름/이벤트 배선은 그대로다.

## Git 상태(작업 종료 시점)
작업 시작 전 이미 PERF-1C(`cd759c1`)가 커밋되어 있었다. 이번 UX-1
단계에서:
```
git status --short
 M PROJECT_STATE.md
 M src/ui.py
 M tests/test_ui_network_start.py
 M tests/test_ui_policy_text.py
```
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.

## 다음 단계
LIMIT-300-A
- 검색 조합당 상한의 실제 입력 허용 범위 확인
- 1, 300 경계값 허용 여부
- 0, 음수, 301 이상, 문자, 소수 거부 여부
- UX-1에서는 입력 검증을 변경하지 않았음

---

# 2026-07-15 ARCH-300C LIMIT-300-A 검색 조합당 수집 상한 1~300 입력 계약 검증

## 목표
검색 조합당 수집 상한의 허용 범위를 정수 1~300으로 명확히 고정하고,
전체 목표 저장 개수(양의 정수, 300 초과 허용)와 서로 다른 검증 규칙을
갖도록 분리한다. 실제 네이버 수집은 실행하지 않는다.

## 작업 전 기준 커밋
`b592a79 개선: 수집 설정 설명과 사용자 안내 강화`(UX-1) - Git log
최상단 일치, `git status --short` clean 확인.

## 확인한 현재 입력 파싱 구조
`src/ui.py:99` `_parse_positive_int(raw)`가 `per_query_limit`/
`target_count` 공용 파서였다(WIRE-2B-2부터). 호출부는 `_start_network_crawl`
(`src/ui.py:1310`, `1317`) 단 2곳뿐이었고, legacy 실행 경로는 이 함수를
쓰지 않는다. 기존에는 두 값 다 "0 이하/비정수"만 거부하고 상한 검증
자체가 없어, 전체 목표 저장 개수는 이미 301 이상을 허용하고 있었지만
검색 조합당 상한도 마찬가지로 300 초과가 그대로 통과되는 상태였다
(예: "999"도 허용됨) - 이번 단계로 처음 상한이 생긴 것이다.

## 검색 조합당 상한과 전체 목표가 기존에 어떻게 검증됐는지
둘 다 동일한 `_parse_positive_int(raw)` 호출 → `None`이면
`"...은 양의 정수여야 합니다."` 형태의 동일한 톤의 오류만 반환. 필드
구분은 메시지 문구로만 됐고(제목도 공통 "입력 오류"), 최대값 개념
자체가 없었다.

## 변경 파일
- `src/ui.py`: `_parse_positive_int`에 선택적 `max_value` 인자 추가
  (기본값 None, 하위 호환). `_start_network_crawl`의 `per_query_limit`
  호출에만 `max_value=300` 지정, `target_count` 호출은 그대로 유지.
  오류 메시지 2건을 필드별로 구체화(§오류 메시지 참고).
- `tests/test_ui_network_start.py`: 기존
  `check_invalid_per_query_limit_blocks_execution`/
  `check_invalid_target_count_blocks_execution`에 거부값 확장 +
  필드별 오류 로그 검증 추가, 신규 3건 추가
  (`check_per_query_limit_boundary_values_allowed`,
  `check_target_count_allows_values_above_300`,
  `check_per_query_limit_and_target_count_validated_independently`).
  기존 입력 검증 테스트 파일이 이미 적합해 새 테스트 파일은 만들지
  않았다.
- `PROJECT_STATE.md`: 이번 기록 append.

## 선택한 최소 구현 방식
work order §5 방식 A(공용 파서에 선택적 `max_value` 인자 추가)를
선택했다. 호출부가 단 2곳뿐이라 방식 B(호출부에서 별도 300 초과 검사
추가)보다 오히려 A가 더 단순했고, `target_count` 호출부는 인자를
전달하지 않아 300 상한이 실수로 전파될 위험이 없다. 기존
`ui._parse_positive_int(raw)` 단일 인자 호출(테스트 포함)은
`max_value=None` 기본값으로 완전히 하위 호환된다.

## 검색 조합당 최종 허용 범위
```
1 <= per_query_limit <= 300 (정수만)
```
`target_count`는 여전히 `target_count >= 1`만 요구하며 상한 없음.

## 검색 조합당 허용값 테스트 결과
1/30/299/300 전부 허용 → Network worker thread 정상 생성, 전달된
`per_query_limit` 값도 정확히 일치(`check_per_query_limit_boundary_values_allowed`
PASS).

## 검색 조합당 거부값 테스트 결과
0/-5/abc/301/999/-300/빈 문자열/공백만/1.0/30.5/30개/+/- 총 13종 전부
차단, thread 생성 0회, "검색 조합당 수집 상한" 오류 로그 확인
(`check_invalid_per_query_limit_blocks_execution` PASS).

## 전체 목표 301·500·1000 허용 결과
1/300/301/500/1000 전부 허용되어 thread 정상 생성, 전달된 `target_count`
값도 정확히 일치 - 300 초과값이 차단되지 않음을 확인
(`check_target_count_allows_values_above_300` PASS). 무효값(0/-5/abc/3.5/
빈 문자열)은 그대로 차단(`check_invalid_target_count_blocks_execution` PASS).

## 두 입력의 분리 계약 결과
`check_per_query_limit_and_target_count_validated_independently` PASS:
- limit=300/target=1000 → 둘 다 유효, thread 생성.
- limit=301/target=1000 → 검색 조합당 상한 오류만 발생(전체 목표 오류
  로그는 섞이지 않음).
- limit=30/target=0 → 전체 목표 저장 개수 오류만 발생(검색 조합당 상한
  오류 로그는 섞이지 않음).

## 오류 메시지
```
검색 조합당 수집 상한 오류: 검색 조합당 수집 상한은 1~300 사이의 정수로 입력해 주세요.
전체 목표 저장 개수 오류: 전체 목표 저장 개수는 1 이상의 정수로 입력해 주세요.
```
`messagebox.showerror`의 제목(title)도 공통 "입력 오류"에서 필드별
제목("검색 조합당 수집 상한 오류"/"전체 목표 저장 개수 오류")으로
분리했다.

## 잘못된 입력 시 worker·수집 미실행 확인
전체 무효값 테스트(총 18개 케이스: per_query_limit 13종 + target_count
5종)에서 `instances`(fake Thread 생성 목록)와 `running_calls`
(`set_running` 호출 목록)가 전부 비어있음을 매 케이스마다 확인했다.
Network worker thread 자체가 생성되지 않으므로 그 안에서만 호출되는
`BrowserSession`/`NetworkBrowserCollector`/`run_collection_plan`/
`export_places_to_excel` 등 실제 수집·저장 함수는 애초에 호출될 여지가
없다 - 다만 이번 테스트 구조는 thread 미생성 여부까지만 직접
검증하며, BrowserSession/exporter 호출 자체를 별도로 재확인하지는
않았다(기존 `check_invalid_*` 테스트와 동일한 검증 수준, 이 한계를
그대로 보고한다).

## 기본값 30/300 유지 확인
`_DEFAULT_PER_QUERY_LIMIT == "30"`, `_DEFAULT_TARGET_COUNT == "300"`
무변경(`check_default_constants` PASS, 정상 start_crawl 테스트에서도
기본값으로 thread가 생성됨을 재확인).

## 새로오픈 disabled 유지 확인
`check_new_open_filter_disabled_and_normalized` PASS - `state="disabled"`,
`new_open_checkbox` 식별자, UX-1에서 개선한 안내 문구 전부 그대로.

## 기능·수집·Excel 계약 무변경 확인
검색 조합 생성 로직(`build_collection_queries`), 지역·업종 선택 로직,
`target_reached` 조기 종료, local/global dedup, `NetworkBrowserCollector`,
`run_collection_plan`, 적응형 settle, Excel 11개 열, 새로오픈여부 빈칸
정책, CAPTCHA·429·navigation 정책 전부 무수정 - 이번 단계는 `src/ui.py`의
`_parse_positive_int` 시그니처 확장과 `_start_network_crawl`의 호출부
2줄 + 오류 메시지 4줄만 변경했다. `per_query_limit=300`을 실제 수집
함수로 실행하지도 않았다(전부 fake thread 기반 no-live 테스트).

## 테스트 파일별 PASS/FAIL(전부 `.\.venv\Scripts\python.exe`로 실행)
| 파일 | PASS | FAIL | 결과 |
|---|---|---|---|
| tests/test_ui_network_start.py | 15 | 0 | PASS |
| tests/test_ui_network_wiring.py | 19 | 0 | PASS |
| tests/test_ui_query_builder.py | 9 | 0 | PASS |
| tests/test_ui_policy_text.py | 25 | 0 | PASS |
| tests/test_ui_pc_full_wiring.py | 4 | 0 | PASS |

## 전체 PASS 합계
**72건 전부 PASS, FAIL 0**(test_ui_network_start.py는 기존 12 + 신규 3 = 15).

## 실제 네이버·Playwright 실행 여부
**전부 실행 안 함.**

## production 수집 코드 수정 여부
**수정하지 않았다.** `src/pc/*`, `src/exporter.py`, `app.py` 전부
무수정. `src/ui.py`도 입력 파싱/검증 로직 외에는 건드리지 않았다.

## Git 상태(작업 종료 시점)
작업 시작 전 이미 UX-1(`b592a79`)이 커밋되어 있었다. 이번 LIMIT-300-A
단계에서:
```
git status --short
 M PROJECT_STATE.md
 M src/ui.py
 M tests/test_ui_network_start.py
```
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.

## 다음 단계
LIMIT-300-B
- 검색 조합 1개, per_query_limit=300, target_count=300
- 실제 live 정확히 1회, 재시도 0회
- 현재 production 경로에서 실제 몇 건까지 수집되는지 측정
- 300건 보장 테스트가 아니라 현재 목록 수집 범위 확인(LIMIT-300-A는
  입력 계약만 검증했고 실제 수집 능력은 검증하지 않았음)

---

# 2026-07-16 ARCH-300C LIMIT-300-B 검색 조합 1개 상한 300 실제 수집 범위 실측

## 목표
검색 조합당 상한 300이 UI/입력 계약상 허용되는 것(LIMIT-300-A)과 별개로,
현재 Network/List production 경로가 검색어 하나에서 스크롤·페이지네이션
추가 없이 실제 몇 건까지 확보하는지 정확히 1회 측정한다.

## 작업 전 기준 커밋
`19faee1 검증: 검색 조합당 수집 상한 1~300 계약 확정`(LIMIT-300-A) -
Git log 최상단 일치, `git status --short` clean 확인.

## Python executable
`C:\code\naver-place-sales-db-crawler-v1\.venv\Scripts\python.exe`(3.14.3).

## 고정 검색어·실행 조건
```
query = 서울특별시 강동구 카페
source_city = 서울특별시, source_district = 강동구, source_subregion = 강동구
source_layer = district(기존 harness에 legal_dong/landmark/vertical 전례는
  있었지만 구 단위 단일 쿼리 전례가 없어, work order 권장값을 그대로
  채택 - production은 source_layer를 enum 검증 없이 row 메타로만
  pass-through하므로 새 값 사용에 제약 없음을 코드로 확인)
per_query_limit = 300
target_count = 300
settle_ms = 5000(production 기본값과 동일)
quiet_period_ms = 750, poll_interval_ms = 100(변경 없음)
retry_count = 0, scroll_count = 0, pagination_count = 0
```

## 사전 회귀(전부 `.\.venv\Scripts\python.exe`로 실행)
| 파일 | PASS | FAIL | 결과 |
|---|---|---|---|
| tests/test_ui_network_start.py | 15 | 0 | PASS |
| tests/test_pc_network_browser_collector.py | 24 | 0 | PASS |
| tests/test_pc_network_adaptive_settle.py | 15 | 0 | PASS |
| tests/test_network_product_integration_no_live.py | 11 | 0 | PASS |
| tests/test_pc_network_pipeline.py | 12 | 0 | PASS |

**전체 77 PASS, FAIL 0**, 전부 exit code 0.

## harness
`scratchpad/arch300_network_probe/limit300b_single_query_live.py`
(PERF-1C harness의 실행 마커/설정 검증/exporter counting wrapper/export
전 중복 검증/Excel 검증 구조를 재사용해 신규 작성, 기존 perf1b/perf1c
harness는 무수정). `--check-config` 모드로 query_count=1, per_query_limit=300,
target_count=300, retry/scroll/pagination=0, production import 5개
모듈 전부 성공, 마커 미생성을 확인(PASS, exit 0).

## 실행 마커
`scratchpad/arch300_network_probe/results/limit300b/LIMIT300B_LIVE_STARTED.marker` -
BrowserSession 시작 전 `open(path, "x")`로 원자적 생성 확인, 삭제하지 않음.

## live 실행 횟수 / 재시도·스크롤·페이지네이션
**정확히 1회.** retry_count=0, scroll_count=0, pagination_count=0 전부
확인(추가 스크롤/페이지 열기/재검색 없음).

## 쿼리 진단(단일 쿼리)
```
recorded_per_query_limit = 300(collect_query에 실제 전달된 값 확인)
query_wall_seconds = 3.08
candidate_response_count = 1
raw_item_count = 20
local_unique_count = 20
returned_row_count = 20
parse_error_count = 0
adaptive_settle_wait_ms = 1700
adaptive_settle_early_exit = True
timeout = False, navigation_error = False
active_captcha_detected = False, status_429_seen = False
```

## 오케스트레이터 결과
```
executed_query_count = 1, skipped_query_count = 0
before_trim_count = 20
final_count = 20
stop_reason = queue_exhausted
security_blocked = False
```

## export 전 내부 중복 검증
```
rows_count = 20 (= final_count)
place_id_present_count = 20, missing = 0, duplicate_count = 0
place_url_present_count = 20, duplicate_count = 0
```

## exporter_call_count
`1`.

## Excel 검증
헤더 11개 = MERGED_COLUMNS 완전 일치, data_row_count=20=final_count,
내부 필드(place_id/source_*) 미노출, 플레이스 URL 중복 0, 새로오픈여부
전부 빈칸(20건, 정책 유지).

## 시간 측정
```
session_ready_seconds = 1.120
orchestrator_seconds = 3.085
session_teardown_seconds = 0.258
export_seconds = 0.033
total_wall_seconds = 4.505
```

## available_ratio_percent / per_query_limit_unused
```
available_ratio_percent = 6.67%(20/300)
per_query_limit_unused = 280
```

## 최종 판정
```
실행 계약 PASS: True
- live 1회, retry/scroll/pagination=0, total_job_count=1,
  executed_query_count=1, recorded_per_query_limit=300,
  navigation_error=False, CAPTCHA=False, 429=False
- final_count>=1 추가 조건: exported=True, exporter_call_count=1,
  Excel data_row_count=final_count, place_id/URL 중복 0,
  내부 필드 누출 없음 - 전부 충족

실제 단일 조합 300건 수집 지원: 미확인(final_count=20 < 300)
```

## 결과의 정확한 해석
이번 1회 실행에서 **현재 production 경로가 검색어 하나("서울특별시
강동구 카페")에서 확보한 개수는 20건**이었다(`candidate_response_count=1`,
즉 네트워크 응답이 1건만 도착했고 그 안에 20개 항목이 있었던 것으로
보임). `per_query_limit=300`은 정확히 전달됐고 UI/파서 계약(LIMIT-300-A)
자체는 정상 작동했다 - 다만 이 상한은 "수집 결과에 적용되는 최대 허용값"
일 뿐 "실제로 300개를 만들어내는" 기능이 아니므로, 20건이라는 결과는
LIMIT-300-B 실행 자체의 실패가 아니다. `stop_reason=queue_exhausted`는
큐(검색 조합 1개)가 소진되어 정상 종료됐다는 뜻이며, "네이버에 업체가
20개뿐이다" 또는 "강동구 카페는 20개뿐"이라고 단정하지 않는다 - 현재
목록 화면 응답 구조상 추가 스크롤/페이지네이션 없이는 이번 코드가 첫
응답 1건(20개)만 확보한다는 관찰일 뿐이다.

## PAGE-300-PoC 필요 여부
final_count(20) < 300이므로 work order §16 기준 **PAGE-300-PoC 후보**에
해당한다(현재 목록의 추가 결과 구조 조사, 스크롤·페이지네이션·추가
response 가능성 검증 - 구현 전 브라우저/Network 실측 우선). 단, 실제
다음 우선순위는 사용자 검토 후 결정 사항이며 이번 단계에서 임의로
시작하지 않는다.

## production·tests 수정 여부
**둘 다 수정하지 않았다.** `src/*`, `tests/*` 전부 무수정 - harness
(`scratchpad/`)만 신규 작성했다. live 실행 중 production 결함도
발견되지 않았다.

## Git 상태(작업 종료 시점)
작업 시작 전 이미 LIMIT-300-A(`19faee1`)가 커밋되어 있었다. 이번
LIMIT-300-B 단계에서:
```
git status --short
 M PROJECT_STATE.md
```
`scratchpad/`는 `.gitignore`에 등록되어 있어 harness
(`limit300b_single_query_live.py`)와 결과 JSON/Excel/마커 파일 전부
`git status`에 나타나지 않는다.
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.

## 다음 단계
사용자 검토 후 다음 중 우선순위 결정:
- PAGE-300-PoC: 현재 목록의 추가 결과 구조 조사, 스크롤·페이지네이션·
  추가 response 가능성 검증(구현 전 브라우저/Network 실측 우선)
- 또는 다른 우선순위(예: NEWOPEN-1 새로오픈 신호 탐색 PoC)
이번 단계에서는 어느 쪽도 임의로 시작하지 않는다.

# 2026-07-16 LIMIT-300-B 제품 판정 정정

기존 기록의 “실행 계약 PASS”는 harness와 안전 실행 절차가 정상이라는
하위 판정일 뿐, 제품 요구사항 달성을 의미하지 않는다.

최종 제품 판정:

LIMIT-300-B FAIL

근거:

- 요구사항: 단일 검색 조합에서 실제 최대 300개 업체 수집
- 실제 final_count: 20
- per_query_limit=300 전달만 성공
- 추가 스크롤·페이지네이션·추가 response 수집 미구현
- 따라서 현재 제품은 검색 조합당 300건 실제 수집을 지원하지 못함

---

# PAGE-300-PoC

- 목표: 단일 검색 조합 추가 결과·스크롤·페이지네이션 구조 실측
- 기준 커밋: 2ad0f30 검증: 단일 검색 조합 300건 수집 미달 확인
- 검색어: 서울특별시 강동구 카페
- 브라우저 세션 수: 1 (Subagent & Python Probe)
- 스크롤 횟수: 스크롤 20회(목록 무반응), 페이지네이션 클릭 1회(새 응답 로드)
- CAPTCHA·429 여부: 초기 페이지 이동에서는 미발생

초기 목록:
- response 수: 1
- item 수: 20
- 고유 업체 수: 20

추가 목록:
- response 수: 1 (page 2 클릭 기준)
- response별 item 수: 20
- 누적 고유 업체 수: 40
- 중복 수: 0
- page·offset·cursor 구조: DOM 페이지네이션 버튼 클릭 시 `graphql` 요청 파라미터가 페이지에 맞게 변경됨

DOM 구조:
- `searchIframe` 내부에 존재
스크롤 컨테이너:
- `#_pcmap_list_scroll_container` (그러나 무한 스크롤 미지원, 하단 페이지네이션 구조)
목록 종료 조건:
- 하단 다음 버튼(`>`)의 `aria-disabled="true"` 상태
기존 production matcher 호환성:
- 기존 matcher(`is_candidate_response`) 및 JSON 파서와 100% 호환됨
20개에서 종료된 원인:
- 현재 코드는 첫 응답 수신 후 적응형 settle이 끝나면 즉시 반환하며, 페이지네이션 클릭 순회 로직이 구현되어 있지 않기 때문

성능·안전 추정:
- 페이지 당 1~2초 소요, 300개 수집 시 약 30~45초 소요. 연속 다수 페이지 접근 시 CAPTCHA/429 차단 위험이 큼.
A/B/C/D 판정:
- PAGE-300-PoC B등급
추천 구현 경로:
- DOM의 페이지네이션 버튼 순차 클릭 및 Network 대기 타이밍 결합 로직 구현, CAPTCHA 대응 부분 저장 연동
production·tests 무수정: 확인됨
Git 상태: Clean
다음 단계: PAGE-300-2B 구현 설계 또는 기타 검토

# 2026-07-16 PAGE-300-PoC-B2 페이지네이션 구현 계약 보충 실측

- 기존 실측 범위는 page 1과 page 2이며 누적 약 40개까지 확인했다.
- 페이지네이션 추가 로딩 구조는 확인했지만 실제 300개 도달은 검증하지 않았다.
- 실측한 page 2 response가 기존 matcher/parser와 호환 가능한 구조인지 확인했으며, page 3 이후 결과는 이번 보충 실측 범위에 따라 별도로 기록한다.
- 300개에는 데이터가 충분하다는 전제 아래 초기 1페이지와 추가 최대 14페이지가 필요하다.
- 정확한 300개 수집 시간은 아직 live 검증되지 않았다.
- 다페이지 접근에는 CAPTCHA·429 위험이 있으나 안전 페이지 수와 발생 확률은 확정되지 않았다.

- 사용 브라우저: Playwright Python Probe (Antigravity Extension 보조)
- 검색어: 서울특별시 강동구 카페
- 최대 접근 페이지: 3페이지
- 페이지 클릭 수: 2회
- CAPTCHA·429 여부: 1-3페이지 내 미발생
- DOM selector 계약:
  - iframe: `iframe#searchIframe`
  - 페이지네이션 영역: `.zRM9F`
  - 페이지 번호: `<a role="button" class="mBN2s">` 내부에 번호 텍스트 포함
  - 현재 페이지 판별: `aria-current="page"`는 존재하지 않음. 활성화된 클래스 차이 등 간접 판별 필요.
  - 다음 번호 묶음: `<a role="button" class="eUTV2"><span class="place_blind">다음페이지</span></a>`
- Network request 계약:
  - `GET https://map.naver.com/p/api/search/allSearch` (GraphQL 아님)
  - page 변수: 쿼리스트링 활용 추정 (GraphQL payload 변수 아님 확인됨)
- response JSON 계약:
  - 목록 배열: `result.place.list`
  - 고유 식별자: `id` 또는 `placeId`
  - `totalCount`: `result.place.totalCount`
  - `hasNext`, `nextCursor`: 존재하지 않음 (null)
- matcher/parser 호환성: `is_candidate_response` 및 JSON 파싱 완벽 호환.
- 종료 조건: `totalCount` 역산 기반 또는 하단 `>`(다음) 버튼의 `aria-disabled="true"` 확인.
- 성능: 페이지 당 1-2초 내외
- B2 최종 판정: B2-B (제한된 범위 구현 가능)
- 추천 구현 범위: page 1~5 번호 클릭을 목표로 제한된 범위 구현 (다음 묶음 클릭은 보류)
- production·tests 무수정: 확인됨
- Git 상태: Clean
- 다음 단계: PAGE-300-2B-1 (Claude Sonnet 5를 사용한 제한된 페이지네이션 no-live 구현 및 100건 단계 검증)

---

# 2026-07-16 PAGE-300-2B-1 page 1~5 제한 페이지네이션 no-live 구현

## 목표
검색 조합당 상한 300을 UI가 받아들이는 것(LIMIT-300-A)과 별개로, 실제
production 경로가 첫 페이지(약 20건)를 넘어 추가로 수집할 수 있도록
목록 하단 페이지 번호 버튼을 최대 5페이지(초기 page1 + 추가 클릭 최대
4회, 약 100건 범위)까지 순차 클릭하는 제한된 페이지네이션을 구현하고
Fake 객체 기반 no-live 테스트로 검증한다. 실제 네이버 live는 이번
단계에서 실행하지 않는다.

## Gemini 작업 이후 저장소 변경 감사 결과
- `git status --short`: `M PROJECT_STATE.md` 1건만 존재(작업 시작 전).
  `git diff -- src`, `git diff -- tests`, `git diff -- app.py`,
  `git diff -- README.md`, `git diff -- LEGAL_NOTICE.md` 전부 출력 없음
  (무수정 확인). `git ls-files --others --exclude-standard`도 빈 결과
  (gitignore 밖의 예상 못한 untracked 파일 없음).
- `scratchpad/arch300_page300_probe/`(Gemini 조사 산출물: probe 스크립트
  4개, 리포트 2개, JSON 요약 1개)는 전부 `.gitignore` 대상이라 git
  추적 밖이다. 내용 감사 결과 `force=True`/CAPTCHA 우회/자동 재시도/
  `while True` 무한루프 등 위험 코드 없음(hasNext/nextCursor/graphql
  토큰은 "이 값이 없다"는 조사 결과를 기록한 텍스트일 뿐, 실제로
  사용하는 코드가 아님을 확인).
- 변경 내용을 `scratchpad/arch300_page300_probe/pre_claude_gemini_changes.patch`
  로 백업.

## PROJECT_STATE.md append-only 무결성 확인
- `git diff --check -- PROJECT_STATE.md`에서 trailing whitespace 2건
  발견("- Network request 계약: ", "- response JSON 계약: ") - 둘 다
  Gemini가 새로 추가한 PAGE-300-PoC-B2 섹션(파일 마지막) 내부였다.
- Python `difflib.SequenceMatcher`로 전후 파일을 비교한 결과 opcode는
  `insert` 1건뿐(과거 내용 삭제 0건) - 순수 append임을 확인했다.
- trailing whitespace가 신규 append 섹션 내부에만 있음을 확인했으므로,
  work order §2 지시에 따라 그 공백 2건만 최소 수정했다(과거 섹션은
  전혀 건드리지 않음). 수정 후 `git diff --check` 재확인 결과 오류
  없음, difflib 재확인 결과도 여전히 순수 insert 1건만 존재(공백
  제거로 인한 실질적 텍스트 손실 없음).

## PAGE-300-PoC-B2 판정 근거(B2-B, 확정된 것/미확정 유지한 것)
확정: iframe `#searchIframe`, 페이지 번호 `<a role="button">` + 정확한
숫자 텍스트, `aria-current="page"` 없음(내부 상태로 현재 페이지 추적
필요), 응답 `result.place.list`/`result.place.totalCount`, 기존
`is_candidate_response`/parser와 100% 호환, `hasNext`/`nextCursor`/
GraphQL variables 전부 미확인(사용 금지).
미확정 유지: 다음 페이지 번호 "묶음" 전환 UI, 300건 전체 실제 도달
가능 여부(다음 단계 PAGE-300-2B-2 이후 live로 확인 필요), CAPTCHA/429
위험이 실제 다중 페이지 클릭에서 얼마나 자주 발생하는지.

## 기존 production이 20개에서 끝났던 원인
`collect_network_query`가 첫 페이지 candidate 응답의 적응형 settle이
끝나면 즉시 반환했고, 페이지 번호 클릭 순회 로직 자체가 코드에 전혀
없었다(주석 "page=1만 수집한다"에 명시돼 있던 기존 설계 그대로).

## 변경 파일
- `src/pc/network_browser_collector.py`: `_MAX_PAGINATION_PAGES=5` 상수
  추가, `_find_search_frame`/`_find_page_button`/`_wait_for_next_page_settle`
  헬퍼 3개 신규 추가, `collect_network_query` 본문에 제한된 페이지네이션
  루프 추가(기존 단일 페이지 로직은 그대로 두고 이어붙임).
- `tests/test_pc_network_pagination.py`: 신규 파일, 23개 테스트
  (요청된 20개 + 반대 검토 지적 수정 확인용 3개 추가).
- `PROJECT_STATE.md`: 이번 기록 append.

## 페이지네이션 흐름 요약
첫 페이지 settle·harvest(기존 로직 무수정) → local unique가
per_query_limit보다 적고 CAPTCHA/429가 아직 없으면 → 루프 진입: (1)
클릭 전 CAPTCHA/429 확인 → (2) searchIframe 탐색(지연 캐싱) → (3)
`get_by_role("button", name=str(target), exact=True)`로 목표 페이지
버튼 탐색 → (4) count==0이면 pagination_exhausted, count>1이면
ambiguous_page_button → (5) visible/enabled 확인 → (6)
scroll_into_view_if_needed() + click()(force 없음) → (7) 클릭+대기를
하나의 try 블록으로 묶어 예외를 pagination_click_error로 흡수 → (8)
클릭 직후 CAPTCHA/429 재확인(전/후 모두 확인) → (9) 신규 candidate
대기(기존 quiet-period 재사용) 실패 시 next_page_response_timeout →
(10) harvest+dedup 누적 → (11) per_query_limit_reached →
max_page_count_reached → no_new_unique_rows(2연속 무수확) 순으로 종료
조건 확인 → 최대 5페이지까지 반복 → 최종 per_query_limit cap 적용.

## 최대 페이지 5 제한
`_MAX_PAGINATION_PAGES = 5`(모듈 상수, UI/공개 API 비노출). limit=300을
줘도 최대 5페이지(약 100건) 내에서 `max_page_count_reached`로 종료되며,
이를 300건 지원 완료로 보고하지 않는다(테스트 4로 확인).

## iframe·페이지 번호 locator
`_find_search_frame`은 `src/pc/browser_session.py`의
`find_search_frame`과 동일한 3단계 폴백(name → frame_locator+body wait
→ frames 스캔)을 bare page 전용으로 재구현(browser_session.py 자체는
무수정). `_find_page_button`은 `frame.get_by_role("button",
name=str(target_page_number), exact=True)`만 사용 - has_text(부분
일치)는 쓰지 않아 "2"가 "12"/"20"과 오매칭되지 않는다(테스트 15로
`get_by_role` 호출 인자 자체를 확인).

## 일반 click 방식 / force click 미사용 확인
`scroll_into_view_if_needed()` → `click()` 순서만 사용, `force`나 다른
인자를 전혀 넘기지 않는다. 테스트의 Fake locator `click()`은 의도적으로
인자를 받지 않게 설계해, production이 `force=True`를 넘겼다면
TypeError로 즉시 드러나도록 했다(테스트 16 PASS로 확인).

## 신규 candidate response 판별 방식 / JSON parse 횟수 보장 / parser 재사용
클릭 전 candidate 개수를 저장해두고, 이후 개수가 늘어난 인덱스만
harvest 대상으로 삼는다(기존 quiet-period 폴링 로직을
`_wait_for_next_page_settle`로 일반화해 재사용, 로직 복제 아님).
`response.json()`은 `parsed_cache`/`_ensure_parsed`를 페이지 전체에서
계속 공유하므로 candidate당 정확히 1회만 호출된다(테스트 13·14로 확인).
`is_candidate_response`/`_extract_list_items`/`_map_item_to_row`/
`dedup_rows`는 전부 무수정 재사용(page1과 동일한 함수, 새 파서 없음).

## 페이지 간 dedup / 종료 조건
모든 페이지의 row를 같은 `local_seen` set에 계속 누적하고
(`dedup_rows` 재사용), 최종적으로 `per_query_limit`으로 한 번만 자른다.
종료 조건 우선순위(1.per_query_limit_reached > 2.captcha_detected >
3.status_429_seen > 4.max_page_count_reached > 5.pagination_exhausted
> 6.ambiguous_page_button > 7.pagination_click_error >
8.next_page_response_timeout > 9.no_new_unique_rows)를 클릭 전/후
양쪽에서 일관되게 적용한다(아래 반대 검토 반영 참고).

## CAPTCHA·429·클릭 오류·response timeout 처리
기존 `_probe_captcha_state`/`classify_captcha_signal`을 그대로 재사용
(새 우회 selector 없음). 클릭 전과 클릭+대기 직후 양쪽에서 확인하며,
즉시 중단하고 재시도하지 않는다(모두 테스트로 확인 - 아래 참고).

## 추가 진단 필드
`pagination_page_count`, `pagination_click_count`,
`pagination_stop_reason`, `pagination_error_message`,
`pagination_candidate_response_count`, `pagination_raw_item_count`,
`pagination_unique_item_count`, `pagination_duplicate_count`,
`pagination_max_pages`, `per_page_diagnostics`(페이지별 배열). 기존
필드 `candidate_response_count`/`raw_item_count`/`local_unique_count`/
`adaptive_settle_wait_ms`는 페이지네이션이 없으면 기존과 완전히
동일한 값이고, 있으면 전체 쿼리 누적값으로 자연스럽게 확장된다(별도
분기 없이 같은 누산 변수를 계속 사용하기 때문).

## 기존 public interface 유지 여부
`NetworkBrowserCollector.collect_query(job, per_query_limit)`,
`collect_network_query(page, job, per_query_limit, *, collected_at,
settle_ms=...)` 시그니처 무변경. 기존 반환 필드 전부 유지(신규 필드는
선택적 추가). `navigation_error` 조기 반환 경로에도 신규 필드 기본값을
일관되게 추가했다.

## 반대 검토(Codex, gpt-5.6-sol, high reasoning, read-only sandbox) 결과와 반영
구현+no-live 테스트 완료 직후 `src/pc/network_browser_collector.py`와
`tests/test_pc_network_pagination.py`만 읽기 전용으로 검토를 요청했다
(코드 수정 없음, 허용 파일 2개로 한정). 지적 사항과 처리:
1. **[수정함]** 클릭 "전"에만 CAPTCHA를 확인하고 그 결과를 캐시해
   재사용하던 구조라, 클릭·대기 도중 나타난 CAPTCHA를 놓치고
   `active_captcha_detected=False`로 잘못 보고할 수 있었다 → 클릭+대기
   직후에도 다시 확인하도록 수정(테스트 21로 재현/확인).
2. **[수정함]** `_wait_for_next_page_settle` 내부 `page.wait_for_timeout()`
   이 예외를 던지면(예: 클릭 이후 page/context 종료) 그 예외가
   `collect_network_query` 밖으로 그대로 전파되어 이미 수집한 부분
   rows까지 잃을 위험이 있었다 → 클릭+대기 전체를 하나의 try 블록으로
   묶어 모든 예외를 `pagination_click_error`로 안전하게 흡수하도록
   수정(테스트 22로 재현/확인).
3. **[수정함]** 마지막(5번째) 페이지에서 신규 unique 2연속 0건이
   되면 `no_new_unique_rows`가 `max_page_count_reached`보다 먼저
   보고되는 우선순위 위반이 있었다 → harvest 직후 검사 순서를
   per_query_limit → max_page → no_new_unique 순으로 재정렬(테스트
   23으로 재현/확인).
4. **[알려진 한계로 문서화, 미수정]** candidate_response_count가 "어느
   페이지에서 온 응답인지" 태깅하지 않는 단순 누적 카운터라, 이론상
   이전 페이지의 늦은 응답이 다음 페이지 응답으로 오인될 가능성이
   있다는 지적 - 이는 PERF-1A부터 있던 quiet-period 조기 종료 설계
   자체의 기존 트레이드오프가 다중 페이지로 확장된 것이며, 실제 응답에
   page/cursor 식별자가 없다는 PAGE-300-PoC-B2 실측 결론상 근본 해결이
   불가능하다 - docstring에 명시했다.
5. **[의도적 유지, 미수정]** `_find_search_frame`이 browser_session.py의
   `find_search_frame`과 동일하게 frame_locator로 찾은 객체를 버리고
   다시 `page.frame(name=...)`을 호출해, iframe에 `name` 속성이 없으면
   탐색에 실패할 수 있다는 지적 - work order가 명시적으로 요구한 "동일한
   폴백 순서 재구현"이며 browser_session.py는 이번 단계 수정 금지
   범위이므로 임의로 다르게 구현하지 않았다. docstring에 한계로 명시.
6. **[문서화]** `pagination_click_count`는 "성공적으로 다음 페이지를
   확보한 횟수"를 의미하며 실제 DOM click() 호출 횟수와 다를 수 있다는
   지적 - docstring에 의미를 명확히 했다(기능 변경 없음).
검토 결과 확인된 정상 사항: 일반 경로 최대 페이지 계산 정확, 두 공개
함수 시그니처 유지, 누적 dedup·최종 cap 정상, force/JS click/URL 직접
조작/GraphQL/hasNext/nextCursor 의존 전부 소스에 없음, 기존 frame API
없는 FakePage 호환성 코드 추적상 성립, 300건 지원을 확정 주장하는
코드·테스트 없음.

## 신규 테스트 23개(요청 20개 + 반대 검토 반영 3개)
1~20은 work order §18 그대로: limit=20/30/100/300 각 시나리오, page2
중복 누적, 목표 버튼 없음, 버튼 2개 이상(ambiguous), 일반 click 오류,
response timeout, CAPTCHA/429(클릭 전), 2연속 무수확, response.json()
미호출/정확히 1회, exact 매칭 확인, force 미사용, URL/GraphQL/hasNext·
nextCursor 미의존(정적 소스 검사 2건 포함), 기존 단일 페이지 계약 유지.
21~23(반대 검토 반영): 클릭 직후 CAPTCHA 감지, wait 중 예외 안전망,
5페이지+2연속 무수확 시 우선순위(max_page_count_reached) 확인.

## 컴파일과 단독 실행
`.\.venv\Scripts\python.exe -m py_compile src\pc\network_browser_collector.py
tests\test_pc_network_pagination.py` exit 0. 단독 실행 **23/23 PASS**
(반대 검토 반영 수정 전 1차 실행은 20/20 PASS, 수정 후 3개 추가해
재실행 23/23 PASS).

## 기존 관련 회귀 파일별 PASS/FAIL(전부 `.\.venv\Scripts\python.exe`로 실행)
| 파일 | PASS | FAIL | 결과 |
|---|---|---|---|
| tests/test_pc_network_pagination.py | 23 | 0 | PASS |
| tests/test_pc_network_browser_collector.py | 24 | 0 | PASS |
| tests/test_pc_network_adaptive_settle.py | 15 | 0 | PASS |
| tests/test_network_product_integration_no_live.py | 11 | 0 | PASS |
| tests/test_pc_network_pipeline.py | 12 | 0 | PASS |
| tests/test_ui_network_start.py | 15 | 0 | PASS |
| tests/test_ui_network_wiring.py | 19 | 0 | PASS |

**전체 PASS 합계: 119건, FAIL 0.** 모든 파일 exit code 0. 기존 24개
collector 테스트·15개 adaptive settle 테스트가 수정 전/후 모두 100%
그대로 통과해, per_query_limit이 첫 페이지 결과보다 큰 기존
테스트들이 실제로 pagination 진입을 "시도"하더라도(frame API 없는
FakePage/FakeAdaptivePage에서) 예외 없이 `pagination_exhausted`로
안전하게 종료되어 기존 반환값이 전혀 달라지지 않음을 실증했다.

## src/ui.py 무수정 확인
`git diff -- src`에 `src/ui.py` 관련 변경 없음(무수정).

## Excel·새로오픈·입력 정책 무변경 확인
`_DEFAULT_COLLECTION_ENGINE`/`_DEFAULT_PER_QUERY_LIMIT`/
`_DEFAULT_TARGET_COUNT`, 검색 조합당 1~300 입력 범위(LIMIT-300-A),
전체 목표 저장 정책, Excel 11개 열, 새로오픈 체크박스 disabled,
CAPTCHA·429 우회 금지, 재시도 0회 전부 무변경(페이지네이션은
`NetworkBrowserCollector` 내부 동작으로만 추가됨).

## 실제 네이버·Playwright live 미실행 확인
확인됨 - app.py 실행, 실제 BrowserSession/Playwright 생성, 네이버
접속, 페이지 번호 실제 클릭, Excel 생성 전부 하지 않았다. Fake 객체
기반 테스트만 수행했다.

## Git 상태(작업 종료 시점)
```
git status --short
 M PROJECT_STATE.md
 M src/pc/network_browser_collector.py
?? tests/test_pc_network_pagination.py
```
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.
`scratchpad/`(Gemini 조사 파일 포함) 61개 항목은 전부 gitignore 대상.

## 다음 단계
PAGE-300-2B-2
- 동일 검색어: 서울특별시 강동구 카페
- per_query_limit=40, target_count=40
- page 1→2만 허용(page 3 클릭 금지)
- 실제 live 정확히 1회, 재시도 0회
- CAPTCHA·429 안전 중단 확인
- 실제 final_count=40 여부, pagination 진단 필드, Excel 정합성 검증

# 2026-07-16 PAGE-300-2B-1 response 귀속 안전성 보완

## 배경 - 커밋 전 독립 검토에서 발견된 미완료 결함
직전(2026-07-16) PAGE-300-2B-1 구현은 아직 미커밋 상태에서 다음 4개
결함이 남아있었다:
1. 이전 페이지에서 늦게 도착한 candidate response를 다음 페이지 response로
   잘못 인정할 수 있음.
2. 최초 harvest와 다음 페이지 클릭 기준점 사이에 도착한 response가 어느
   페이지에서도 처리되지 않고 누락될 수 있음.
3. 페이지 버튼 클릭은 성공했지만 response timeout이면 pagination_click_count가
   실제보다 적게 기록됨.
4. 다음 페이지 response의 페이지 정체를 확인하지 않고 단순 candidate 개수
   증가만으로 성공 판정함.

## 저장된 probe 자료 재분석 - 페이지 식별 근거
`page300_network_summary.json`/`page300_poc_report.md`/`page300_poc_b2_report.md`
재확인 결과: page 2/3에 대한 실제 request/response는 probe에서 단 한 건도
캡처되지 않았고(`responses` 배열은 page 1 1건뿐), `page_variable`/
`display_variable`/`start_variable`도 전부 null이었다 - **request URL/response
JSON으로 목표 page를 식별하는 것은 불가능**하다는 점을 재확인했다(A 배제).
다만 page 1 DOM 캡처(`page300_network_summary.json`의 `dom_info[0]`)에서
활성 페이지 버튼("1")만 다른 버튼과 다른 class(`mBN2s qxokY`)를 가진다는
구조적 근거는 실측 데이터로 확인됐다 - **B: DOM 상태(클릭 전/후 class diff,
리터럴 문자열 고정 아님) + 신규 response 결합**으로 판정하기로 했다. 클릭 후
실제 전환 시 이 마커가 이동하는지는 probe가 `aria-current`만 조회해(이미
B2 리포트에서 미존재로 확인된 값) 검증하지 못했으므로, 이 부분은 판정
불가 시 `page_transition_unverified`/`next_page_identity_unverified`로
안전 폴백하도록 구현했다(Gemini+Antigravity 보충 실측 없이 code-only로
진행 - 근거 부족이 아니라 "확인 가능하면 사용, 불가능하면 안전 중단"
경로가 이미 요청서 §5/§6에 설계돼 있어 C(검증 불가로 전면 보류)가 아닌
B로 판정).

## 수정한 response 큐·sequence·processed 계약
- `_QueryObservationContext`에 `seen_response_ids`(object identity, `id()`)를
  추가해 handler 레벨에서 동일 response 객체의 중복 등록·중복 JSON parse를
  차단(§3).
- `_ensure_parsed(index)` 메모이즈는 기존과 동일하게 유지하되, harvest 범위를
  `harvested_up_to_index` 포인터로 관리해 각 candidate가 정확히 한 번만
  disjoint 범위에서 처리되도록 함(page1 harvest → drain → page2 harvest →
  drain → page3 harvest ... 서로 겹치지 않음).

## pending response drain 방식(§4)
목표 페이지 버튼을 찾아 클릭 준비가 끝난 직후, `_apply_pending_drain()`
(내부적으로 `_drain_pending_responses()` 호출)로 미처리 candidate를
"현재까지 확정된 페이지의 지연 도착분"으로 먼저 harvest하고
`candidate_count_before_click` 기준점을 그 이후로 확정한다. 이어서 DOM
`class_before`를 읽는 순간에도(실제 Playwright에서는 이 호출이 이벤트
루프에 제어권을 넘길 수 있음) 새 candidate가 도착했을 수 있어, 한 번 더
동일한 드레인을 수행해 클릭 직전까지 확실히 흡수한다(gpt-5.6-sol 1차
재검토에서 지적된 좁은 손실 구간 - 수정 반영).

## 지연된 이전 페이지 response 처리
드레인으로 흡수된 candidate는 새 page로 카운트되지 않고 기존 local dedup
집합에 병합되며, pagination_page_count/pagination_click_count에 영향을
주지 않는다.

## 목표 페이지 response 판별 방법(§5/§6)
`candidate_response_count` 증가만으로 성공 판정하지 않는다. 클릭한 버튼
locator의 `class` 속성을 클릭 전/후로 비교해(`_safe_get_attribute`, 리터럴
클래스명 미사용) 실제로 달라졌는지만 확인한다. class를 읽을 수 없으면
`pagination_stop_reason="next_page_identity_unverified"`, 읽었지만 변화가
없으면(response와 DOM 불일치) `"page_transition_unverified"`로 안전
중단하고 그 응답의 데이터는 rows에 포함하지 않는다 - 두 경우 모두
`pagination_page_count`를 증가시키지 않는다. 진단 필드
`pagination_unverified_candidate_count`/`pagination_drain_item_count`를
신규로 추가했다.

## DOM 보조 검증 방법
클릭 전 `class_before`, 응답 확인 후 `class_after`를 같은 locator에서
diff로만 비교한다. `page300_network_summary.json`의 page_1 DOM 캡처와
같은 형태(`mBN2s` → `mBN2s qxokY`)를 정상 케이스로 재현했다.

## processed response 중복 방지
handler 레벨 object identity dedup(`seen_response_ids`) + `_ensure_parsed`
인덱스 메모이즈 + harvest 범위 포인터(`harvested_up_to_index`)로 3중
보장했다.

## click count와 page count 의미(§7)
`pagination_click_count`는 `target_locator.click()`이 예외 없이 반환된
직후 증가(클릭 자체 성공 여부만 반영, 이후 timeout/identity 미확인과
무관). `pagination_page_count`(`current_page_number`)는 §5/§6 기준으로
identity가 확정된 페이지 수만 반영 - 클릭 성공만으로는 증가하지 않는다.

## 부분 rows 보존
새로 추가된 모든 안전 중단 경로(`page_transition_unverified`,
`next_page_identity_unverified` 포함)에서 그때까지 확정된 rows만 반환하고
미확인 candidate의 데이터는 병합하지 않는다.

## 추가 테스트 사례(10개, 기존 23개 유지)
1. `check_late_page1_response_after_click_not_accepted_as_page2`
2. `check_gap_between_harvest_and_click_baseline_not_lost`
3. `check_click_success_then_timeout_click_count_is_one`
4. `check_confirmed_page2_identity_via_dom_class_diff`
5. `check_unrelated_candidate_response_after_click_not_accepted`
6. `check_duplicate_response_object_registered_twice_parsed_once`
7. `check_processed_page1_candidate_not_reused_on_page2`
8. `check_response_identity_completely_unverifiable`
9. `check_dom_shows_transition_but_no_response_not_treated_as_success`
10. `check_dom_transition_explicit_mismatch_preserves_partial_rows`

## 신규 테스트 PASS/FAIL
`tests\test_pc_network_pagination.py` 단독 실행 **33/33 PASS**(기존 23 +
신규 10, FAIL 0).

## 전체 관련 회귀 파일별 PASS/FAIL
| 파일 | PASS | FAIL | 결과 |
|---|---|---|---|
| tests/test_pc_network_pagination.py | 33 | 0 | PASS |
| tests/test_pc_network_browser_collector.py | 24 | 0 | PASS |
| tests/test_pc_network_adaptive_settle.py | 15 | 0 | PASS |
| tests/test_network_product_integration_no_live.py | 11 | 0 | PASS |
| tests/test_pc_network_pipeline.py | 12 | 0 | PASS |
| tests/test_ui_network_start.py | 15 | 0 | PASS |
| tests/test_ui_network_wiring.py | 19 | 0 | PASS |

**전체 PASS 합계: 129건, FAIL 0.** (이전 119건 + 신규 10건, 전부 exit code 0)

## GPT-5.6-Sol(Codex MCP, read-only) 독립 재검토 결과
1차 검토에서 HOLD 판정: "drain 종료와 click baseline 사이 응답 누락 및
DOM 전환과 응답의 비결합 오귀속이 남아있음." 이 중 손실(누락) 결함은
`_apply_pending_drain`을 클릭 직전(class_before 조회 이후)에 한 번 더
호출하도록 수정해 해소했다. 2차 재검토 결과: 손실 구간은 닫혔음을 확인,
**최종 판정 PASS - "누락 결함은 해소되었으며, 남은 응답 귀속 불확실성은
현재 증거로 해결 불가능한 명시적 구조 한계임."**

## 남은 높음·중간 위험(문서화된 구조적 한계, 코드 결함 아님)
DOM class diff와 "새 response 도착"은 서로 인과관계로 묶여있지 않고 각각
독립적으로 확인된다 - 클릭이 실제로 DOM을 전환시켰고 그 직후 우연히
지연 도착한 이전 페이지 응답이 클릭 후 첫 신규 candidate가 되면, 오귀속될
이론적 가능성이 남아있다. `_MAX_PAGINATION_PAGES`(5)와 per_query_limit이
상한으로 작동해 폭주(runaway)는 없으나, "정확히 한 페이지만 오염된다"는
보장은 아니다(gpt-5.6-sol 2차 재검토 지적 반영 - 최초 초안의 "오염은
최대 1페이지" 서술을 정정함). 이를 완전히 닫으려면 실제 네이버에서
"DOM 전환"과 "response 도착"의 순서 보장 여부를 live로 실측해야 하며,
증거 없는 추가 휴리스틱은 페이지 번호 추측 금지 원칙에 위배되므로
넣지 않았다.

## 실제 live 미실행 확인
확인됨 - app.py 실행, 실제 BrowserSession/Playwright 생성, 네이버 접속,
페이지 번호 실제 클릭, Excel 생성 전부 하지 않았다. Fake 객체 기반 테스트와
저장된 probe 재분석만 수행했다.

## Git 상태(작업 종료 시점)
```
git status --short
 M PROJECT_STATE.md
 M src/pc/network_browser_collector.py
?? tests/test_pc_network_pagination.py
```
git add/commit/push/reset/checkout/restore 전부 수행하지 않았다.

## PAGE-300-2B-2 진입 가능 여부
HOLD 사유(page identity 검증 불가) 없이 PASS 판정 - 문서화된 구조적
한계(위 항목)를 인지한 상태로 PAGE-300-2B-2(실제 40건 live 1회)로 진입
가능하다고 판단한다. 단, PAGE-300-2B-2 live 실행 중 반드시 관찰할 것:
클릭 직후 도착하는 candidate response 개수(2개 이상이면 지연 응답
오귀속 리스크가 실측으로 확인되는 신호), pagination_unverified_candidate_count/
pagination_drain_item_count 값(0이 아니면 이번 세션에서 다루지 못한
실제 경로가 발동한 것이므로 즉시 원인 분석 필요).

# 2026-07-20 PAGE-300-2B-2 실제 page 1→2 40건 live 검증

## 기준/실행 조건
- 기준 커밋: `2c8fb071eb043cede6047f1c906ae8b14798713b`(PAGE-300-2B-1-FIX 내용
  포함, 작업 시작 시점 `git status --short` clean 확인).
- 고정 검색어: "서울특별시 강동구 카페"(query_count=1).
- per_query_limit=40, target_count=40, settle_ms=5000(production 기본값,
  harness가 변경하지 않음).
- 실행 마커: `scratchpad/arch300_page300_probe/results/page300_2b2/PAGE300_2B2_LIVE_STARTED.marker`
  (`open(path, "x")`로 원자적 생성, 실행 후 삭제하지 않음).
- production `_MAX_PAGINATION_PAGES` 원래 값=5, live 실행 구간에서만
  harness가 모듈 속성을 2로 override, try/finally로 복구 확인(복구 후
  값=5). production 소스 파일(`src/pc/network_browser_collector.py`)은
  수정하지 않았다 - harness가 import한 모듈 객체의 속성만 런타임에 바꿨다.
- 사전 회귀: 지정된 7개 테스트 파일 전부 PASS, 합계 **129 PASS / 0 FAIL**
  (기존 계약과 동일).
- 실제 브라우저 세션 1개, retry=0, 접근 페이지 1~2만(page 3 접근 없음),
  CAPTCHA·HTTP 429 없음, live 실행 정확히 1회.

## 실행 결과(요약)
- `pagination_click_count=1`, `pagination_page_count=2` - page 2 버튼
  클릭이 성공했고 DOM class diff로 page 2 전환 identity가 확정됐다(§6
  계약대로 클릭 성공만으로 page_count를 올리지 않았고, 이번 실행에서는
  실제로 identity까지 확인됨).
- `pagination_stop_reason="max_page_count_reached"`(override로 2페이지
  상한에 도달, per_query_limit(40)에는 도달하지 못함).
- page별 진단(`per_page_diagnostics`):
  - page 1: candidate=1, raw_item_count=20, new_unique_count=20,
    duplicate_count=0.
  - page 2: candidate=1, raw_item_count=0, new_unique_count=0,
    duplicate_count=0.
- `pagination_raw_item_count=20`, `pagination_unique_item_count=20`,
  `pagination_duplicate_count=0` - page별 합계와 정확히 일치(raw
  20+0=20, unique 20+0=20, dup 0+0=0).
- `pagination_unverified_candidate_count=0`,
  `pagination_drain_item_count=0` - 응답 귀속 미확인/지연 drain 경로는
  이번 실행에서 발동하지 않았다.
- **`parse_error_count=1`**(전체 쿼리 기준) - page 1이 raw 20건을 정상
  파싱했으므로, 이 1건의 parse error는 page 2 harvest 단계에서 발생한
  것으로 추정된다(candidate_response_count 총합=2, page 1 harvest에서
  이미 1개 소비, page 2 클릭 후 도착한 나머지 1개가 harvest되며
  `_ensure_parsed`가 실패 처리됨 - production 코드가 raw_item_count=0으로
  안전하게 흡수). 정확한 예외 메시지는 production이 개수만 반환하고
  원문을 노출하지 않아 이번 harness로는 확인할 수 없었다.
- place_id 기준 페이지 간 검증: page 1 고유 ID 20개, page 2 고유 ID
  0개, 교집합 0, 전체 고유 20개 - 페이지 간 중복 오염 신호는 없음.
- `before_trim_count=20`, `final_count=20`, `stop_reason="queue_exhausted"`.
- CAPTCHA·429·navigation_error·timeout 전부 없음.
- exporter 호출 1회, Excel 저장 성공(`exported=True`).
- Excel 검증: 통합_결과 11개 열(순서 포함 `MERGED_COLUMNS`와 완전 일치),
  데이터 행 20(=final_count), 새로오픈여부 20개 전부 빈칸, place_id 등
  내부 필드 노출 없음, 플레이스 URL 중복 0, 원본_모바일/원본_PC 시트는
  헤더만 존재(정상 - Network 경로는 두 시트에 데이터가 없다).
- 성능: session_ready=1.93s, orchestrator=10.87s, teardown=0.24s,
  export=0.02s, 전체=13.07s.
- production `_MAX_PAGINATION_PAGES` 실행 후 복구값=5(override=2, 원래=5
  그대로 복구 확인).

## 판정: HOLD
완전 PASS 요건(§10) 중 `parse error 0`이 충족되지 않아(parse_error_count=1)
"완전 PASS"로 보고하지 않았다. 동시에 "조건부 PASS"(page 2가 실제
마지막 페이지이거나 raw item이 20건 미만이라는 근거가 있고 오류가
없는 경우)로도 분류하지 않았다 - page 2 응답이 도착은 했으나(candidate
확인됨) 그 응답의 파싱이 실패했으므로, "네이버 자체에 page 2 데이터가
없다"와 "파싱 실패로 실제 데이터를 놓쳤다"를 현재 증거만으로 구분할 수
없기 때문이다(증거 없는 추측 금지 원칙). `pagination_unverified_candidate_count`/
`pagination_drain_item_count`는 둘 다 0으로, work order가 우려한
"지연 응답 오귀속" 경로는 발동하지 않은 것으로 확인됐다 - 이번 HOLD의
원인은 응답 귀속 문제가 아니라 **page 2 응답의 JSON/아이템 파싱
실패** 쪽으로 좁혀진다.

## page 2 추가 수집 기능 성공 여부(분리 판단)
- 클릭·DOM 전환 확인 자체: **성공**(pagination_click_count=1,
  pagination_page_count=2, class diff 기반 identity 확정).
- page 2 데이터 반영: **실패**(parse_error_count=1로 인해 raw_item_count=0,
  최종 rows에 page 2 데이터가 전혀 포함되지 않음).
- 고정 검색어 40건 목표 달성 여부: **미달**(final_count=20/40).

## 남은 위험/다음 필요 분석
- 이번 1회 실행만으로는 parse error의 정확한 원인(응답 구조 변경,
  일시적 네트워크 이슈, list 응답 스키마 예외 케이스 등)을 특정할 수
  없다 - production이 예외 메시지를 diagnostics로 노출하지 않기 때문.
- 재실행은 work order상 금지되어 있어 이번 세션에서는 추가 시도를
  하지 않았다.
- 다음 단계 전에 이 parse error의 재현성(같은 검색어로 다시 발생하는지,
  다른 검색어에서도 발생하는지)과 원인을 먼저 분석해야 한다 - 원인
  분석 없이 PAGE-300-2B-3(page 1~5 최대 100건)으로 진입하지 않는다.

## production·tests 무수정 확인
`git status --short` clean, `git diff --name-status`/`--stat`/`--check`
전부 출력 없음(변경 없음) - `src/*`, `tests/*` 무수정 확인됨. 수정은
`scratchpad/arch300_page300_probe/page300_2b2_live_40.py`(신규 harness)와
이 `PROJECT_STATE.md` append뿐이다. git add/commit/push/reset/checkout/
restore 전부 수행하지 않았다.

## 결과 파일
- `scratchpad/arch300_page300_probe/results/page300_2b2/PAGE300_2B2_LIVE_STARTED.marker`
- `scratchpad/arch300_page300_probe/results/page300_2b2/page300_2b2_live_40_result_20260720_111254.json`
- `scratchpad/arch300_page300_probe/results/page300_2b2/page300_2b2_live_40_20260720_111254.xlsx`
(전부 Git 미포함)

## 다음 단계
HOLD - PAGE-300-2B-3(page 1~5 최대 100건 live)로 임의 진입하지 않는다.
이번 parse error의 원인 분석(응답 구조 재확인, 재현성 확인)이 먼저
필요하다. 과거 PAGE 기록은 수정하거나 삭제하지 않았다.
과거 기록은 수정하거나 삭제하지 않았다.
# 2026-07-20 PAGE-300-2B-2A page 2 응답 파싱 실패 원인 진단

- PAGE-300-2B-2 HOLD 원인: page 2 candidate response의 JSON 파싱 에러(1건)로 목표(40건) 달성 실패
- 기준 커밋: 5b7f9ca
- 실행 횟수: 1회 (Playwright 프로브 스크립트)
- 검색어: "서울특별시 강동구 카페"
- page 2 클릭 수: 1회
- CAPTCHA·429 여부: 발생 안 함
- page 1·2 response 비교:
  - page 1: URL llSearch, Resource xhr, JSON Object({), Top key ["result"]
  - page 2: URL graphql, Resource etch, JSON Array([), Top key ["<list>"]
- 정확한 parse 예외: Playwright 내부 예외 playwright._impl._errors.Error: response.json: Response body is unavailable (지연 접근에 따른 바디 해제 문제)
- matcher 판정: 정상. _CANDIDATE_URL_TOKENS에 llSearch와 graphql 모두 포함되어 올바르게 후보로 선택함.
- parser 판정: 보류. JSON 바디를 읽지 못해 _extract_list_items 동작 여부를 검증할 수 없음. (단, _find_item_lists의 휴리스틱 로직이 GraphQL 배열 구조에 대응될 가능성 있음)
- lifecycle 판정: 비정상. esponse.json()을 Settle 루프에서 지연 호출하여 바디 접근 시 예외 발생.
- A/B/C/D/E 최종 분류: B. response body lifecycle 문제
- production·tests 무수정: 확인
- Git 상태: Clean (작업 전 기준)
- 추천 다음 단계: Claude Sonnet 5를 사용하여 response 수신 직후 바디를 미리 복사해두거나, 파싱 시점을 앞당기도록 
etwork_browser_collector.py 수정 (PAGE-300-2B-3)

# 2026-07-20 PAGE-300-2B-2B candidate body snapshot no-live 구현

## PAGE-300-2B-2A 원인(재확인)
page 1(allSearch, JSON object, ~78KB)은 정상 파싱되지만 page 2(graphql
POST, JSON array, ~414KB)는 production의 `_ensure_parsed`가 adaptive
settle 폴링 중 지연된 시점에 `response.json()`을 호출해
`playwright._impl._errors.Error: response.json: Response body is
unavailable`로 실패했다(response body lifecycle 문제, matcher/parser
호환성 문제 아님).

## 선택한 event 구조 / requestfinished snapshot / response callback 역할
- `_QueryObservationContext`가 raw response 객체 리스트 대신 candidate
  entry(dict) 리스트(`ctx.candidates`)와 `id(request) -> entry` 역참조
  맵(`ctx.request_id_to_candidate`)을 갖도록 변경.
- 리스너 3개로 확장:
  - `response`(`_make_response_handler`): 상태 확인(429) + candidate 판별
    (`is_candidate_response`) + entry 등록만. body 접근 없음(기존과 동일,
    정적 검사로 회귀 고정).
  - `requestfinished`(`_make_request_finished_handler`, 신규): `request.
    response()` → `response.body()`(실패 시 `response.text().encode()`
    fallback)로 즉시 bytes snapshot. content-length 헤더가 있고 상한을
    넘으면 body()조차 호출하지 않고 조기 거절(2차 검토 반영). 상한
    (`_MAX_CANDIDATE_BODY_BYTES`=2MB) 초과 시 BodyTooLarge로 안전 실패,
    원문은 저장하지 않음. 이미 resolve된 entry는 idempotent하게 무시.
  - `requestfailed`(`_make_request_failed_handler`, 신규): entry가 있으면
    RequestFailed로 표시. entry가 없어도(= response를 한 번도 받지 못하고
    실패한 표준 네트워크 실패 경로) `request.url`/`resource_type`만으로
    candidate 여부를 재판별해(2차 독립 검토 지적 반영) candidate였다면
    새 entry를 만들어 즉시 실패로 확정 - 정상 candidate가 per_query_limit에
    도달해도 이 실패가 진단에서 사라지지 않게 한다.
- 세 리스너 등록을 순회 구조로 바꿔, 등록 도중 예외가 발생하면 이미
  등록된 리스너를 즉시 해제하고 원 예외를 재전파(1차 독립 검토 지적,
  Low 등급, 반영).

## body 크기 상한 / snapshot·decode·JSON 오류 구분
`_MAX_CANDIDATE_BODY_BYTES = 2 * 1024 * 1024`. candidate entry는
`body_snapshot_ready`/`body_snapshot_error_type`/`body_snapshot_error_
message`/`body_snapshot_size`를 갖는다. harvest(`_ensure_parsed`)는
entry의 snapshot bytes에만 `json.loads`를 적용하고 Playwright Response
객체에는 다시 접근하지 않는다 - response는 왔지만 requestfinished/
requestfailed가 아직 안 온 "진짜 pending" 상태는 memoize하지 않고 다음
tick에 재확인하며, 실제 harvest 지점(`_ensure_parsed_final`, 최초 page1
harvest/per-page harvest/`_drain_pending_responses` harvest 3곳)에서만
pending을 최종적으로 error로 확정한다(candidate당 JSON parse 정확히
1회 계약 유지). 신규 진단 필드 4개(`body_snapshot_success_count`/
`body_snapshot_error_count`/`body_snapshot_total_bytes`/
`json_decode_error_count`)를 추가했고 기존 `parse_error_count`는 하위
호환 유지.

## GraphQL top-level list parser 검증
`src/pc/network_list_scraper.py`는 **수정하지 않았다**. `_extract_list_
items`/`_find_item_lists`의 기존 일반 재귀가 top-level list도 이미
안전하게 처리함을 `tests/test_pc_network_list_scraper.py`에 신규 추가한
placeholder 키 기반 synthetic fixture(실제 미확인 GraphQL 스키마를
추정하지 않음) 3건으로 확인했다(top-level list 재귀 순회/빈 list/무관한
list 오인 방지).

## 변경 파일
- `src/pc/network_browser_collector.py`(핵심 변경)
- `tests/test_pc_network_pagination.py`, `tests/test_pc_network_adaptive_
  settle.py`, `tests/test_pc_network_browser_collector.py`,
  `tests/test_network_product_integration_no_live.py`(Fake `.json()` →
  `.body()`/`.text()` + `FakeRequest` 승격, requestfinished/requestfailed
  전달 확장 - 마지막 파일은 원래 수정 허용 목록에 명시되지 않았으나 동일한
  이벤트 계약 변경으로 인해 기존 회귀(11 PASS) 유지에 필수적이라 판단해
  동일한 최소 패턴으로 갱신했다),
  `tests/test_pc_network_list_scraper.py`(GraphQL top-level list 검증
  3건 추가)
- `src/pc/network_list_scraper.py`: 무수정(검증 결과 불필요)

## GPT-5.6-Sol(Codex MCP, read-only) 독립 검토 결과(3라운드)
1차 검토 HOLD - Medium 3건(드레인 시 `_apply_pending_drain`이
`if drain_result["raw_items"]:` 조건 안에서만 `parse_error_count`를
누적해 drain된 candidate가 전부 실패하면 조용히 사라질 수 있음/
content-length 사전 확인 없이 전체 body를 할당한 뒤 크기를 검사해
실질적 메모리 상한이 아님/response 없이 실패한 request는
`request_id_to_candidate`에 없어 requestfailed가 사실상 트리거되지
않음), Low 1건(리스너 등록 도중 예외 시 이미 등록된 리스너 미해제).
Medium 3건과 Low 1건을 모두 수정 반영(위 "선택한 event 구조" 절 참고).
2차 재검토에서 drain 수정과 listener 정리는 PASS로 확인했으나,
requestfailed 미해결 부분에서 "정상 candidate가 per_query_limit에
도달해도 실패한 candidate가 진단에서 사라진다"는 거짓 성공 재현을
추가로 제시해 HOLD 유지 - 이를 반영해 requestfailed 핸들러가 미등록
request도 URL/resource_type으로 재판별하도록 추가 수정. 3차 재검토
**최종 판정: PASS** - "정상 candidate가 목표를 채워도 실패 candidate가
진단에서 사라지지 않음을 재현으로 확인, 새로운 회귀(중복 entry 생성,
성공 entry를 실패로 덮어쓰기 등) 없음."

## 남은 위험(문서화된 알려진 한계, 코드 결함 아님)
- **드레인(200ms) 중 정말로 늦게 완료되는 body**: `_drain_pending_
  responses`는 candidate 개수 변화만 200ms 관찰하고 body_snapshot_ready
  자체를 기다리지 않는다 - 이 200ms 안에 requestfinished가 끝나지 않으면
  `_ensure_parsed_final`이 그 시점에 최종적으로 error로 확정하며, 이후
  실제로 requestfinished가 도착해도 이미 error가 있어 snapshot을 하지
  않는다(§4). gpt-5.6-sol 3차 확인: 이 경로는 이제 항상
  `parse_error_count`/`body_snapshot_error_count`에 반영되므로(거짓
  성공 아님) fail-closed 동작이지만, 실제로 늦게 도착했을 body의 데이터
  자체는 수집하지 못한다(page 2처럼 큰 body가 200ms보다 오래 걸리면
  drain 경로에서 재현될 수 있음 - 다음 live에서 관찰 필요).
- **content-length 사전 검사는 완전한 메모리 hard cap이 아님**: 헤더가
  없거나, 실제보다 작게 보고되거나(과소값), 압축 응답(Content-Length가
  전송 크기이고 body()가 압축 해제 크기)인 경우 여전히 body() 호출 시
  전체 크기가 먼저 메모리에 올라간 뒤에야 상한 검사가 이뤄진다. 다만
  모든 초과/불일치 경로는 명시적 오류로 귀결되므로(조용한 데이터 손실이나
  거짓 성공 없음) 실측 body 크기(~414KB)와 상한(2MB) 격차를 고려하면
  이번 단계의 live 진입을 막을 사유는 아니라고 gpt-5.6-sol이 확인했다.
- **`candidate_response_count`의 의미가 미세하게 넓어짐**: response 없이
  실패한 candidate도 이제 이 카운트에 포함되므로, "response 이벤트 수"가
  아니라 "candidate entry 수"에 더 가깝다. 성공으로 오인되지는 않지만
  다음 단계에서 이 필드를 해석할 때 참고해야 한다.

## 신규/변경 테스트 요약
- pagination: 34 → 35 PASS(신규: page2 body 지연 재접근 PAGE-300-2B-2A
  재현 회귀, drain 전부 실패 시 parse_error_count 반영 회귀).
- adaptive_settle: 15 → 18 PASS(신규: pending snapshot이 quiet period를
  시작시키지 않음, requestfailed candidate 단독 안전 처리, body 크기
  상한 단독 안전 처리; 기존 2건은 body_call_count 기준으로 갱신).
- browser_collector: 24 → 34 PASS(신규 10건: PAGE-300-2B-2A 재현, snapshot
  실패, requestfailed 안전 처리, body 크기 상한, 중복 requestfinished,
  raw body 미노출, UTF-8 decode, json_decode_error_count 진단,
  content-length 조기 거절, response 없는 requestfailed 집계).
- network_product_integration_no_live: 11 → 11 PASS(Fake 인프라만 갱신,
  신규 케이스 없음).
- network_list_scraper(7개 회귀 파일에는 미포함, 별도 확인): 39 → 42
  PASS(GraphQL top-level list 재귀/빈 list/무관 list 3건 추가).

## 전체 관련 회귀 파일별 PASS/FAIL(최종)
| 파일 | PASS | FAIL |
|---|---|---|
| tests/test_pc_network_pagination.py | 35 | 0 |
| tests/test_pc_network_browser_collector.py | 34 | 0 |
| tests/test_pc_network_adaptive_settle.py | 18 | 0 |
| tests/test_network_product_integration_no_live.py | 11 | 0 |
| tests/test_pc_network_pipeline.py | 12 | 0 |
| tests/test_ui_network_start.py | 15 | 0 |
| tests/test_ui_network_wiring.py | 19 | 0 |

**전체 PASS 합계: 144건, FAIL 0.**(작업 전 129건 대비 신규 15건 -
requestfailed 미관측 수정에 따른 회귀 1건 포함)

## 실제 live 미실행 확인
확인됨 - BrowserSession/Playwright 실행, 네이버 접속, 실제 40건 재검증,
100건 검증, Excel 생성 전부 하지 않았다. Fake 객체와 synthetic JSON
bytes만으로 검증했다.

## Git 상태
`git status --short` 기준 변경 파일은 `src/pc/network_browser_collector.py`
+ 위 5개 테스트 파일 + 이 `PROJECT_STATE.md` append뿐이다. `src/ui.py`,
`src/exporter.py`, `src/pc/network_pipeline.py`, `src/pc/browser_session.py`,
`app.py`, `src/pc/network_list_scraper.py`는 무수정. git add/commit/push/
reset/checkout/restore 전부 수행하지 않았다.

## PAGE-300-2B-2C 진입 가능 여부
gpt-5.6-sol 3차 최종 판정 PASS - PAGE-300-2B-2C(동일 검색어, page 1→2,
per_query_limit=40, target_count=40, 실제 live 정확히 1회, retry 0,
page 3 접근 금지)로 진입 가능하다고 판단한다. 다만 gpt-5.6-sol이 제시한
live PASS 최소 조건을 그대로 채택한다: 최종 unique rows=40,
`parse_error_count==0`, `body_snapshot_error_count==0`,
`json_decode_error_count==0`, `body_snapshot_success_count==
candidate_response_count`, CAPTCHA·429·timeout·navigation_error 없음,
page 2 DOM 전환 확인 및 `pagination_unverified_candidate_count==0`.
하나라도 어긋나면 조건부 PASS가 아니라 즉시 HOLD로 판정한다. 과거 PAGE
기록은 수정하거나 삭제하지 않았다.

# 2026-07-20 PAGE-300-2B-2C body snapshot 적용 후 실제 40건 재검증

## 기준/실행 정보
- 기준 커밋: `b37d5ad8e0e92977be6b881c4dbb088099ba3dfa`(기능: Network 응답 body
  snapshot과 lifecycle 안전성 구현) - 작업 전/후 동일, 변경 없음
- 검색어: "서울특별시 강동구 카페", query_count=1
- 실행 마커: `scratchpad/arch300_page300_probe/results/page300_2b2c/
  PAGE300_2B2C_LIVE_STARTED.marker`(harness 시작 직전 `open(..., "x")`로 원자 생성,
  삭제하지 않음)
- live 실행 횟수: 정확히 1회(20260720_162022), retry_count=0, 재실행 없음
- 허용 페이지: [1, 2] - page 3 이상 접근 없음(`pagination_page_count=2`)
- production `_MAX_PAGINATION_PAGES` 원래 값 5 → live override 2 → 실행 후
  복구 값 5(`production_max_pages_after_restore=5`, 복구 성공)

## harness/사전 검증
- harness: `scratchpad/arch300_page300_probe/page300_2b2c_live_40.py`(신규,
  page300_2b2_live_40.py의 마커/설정검증/exporter counting wrapper/Excel 검증
  구조를 재사용하되 그 harness는 수정하지 않음. collector/parser/body snapshot
  로직은 harness에서 재구현하지 않고 production 함수만 호출)
- 컴파일: `py_compile` PASS
- `--check-config`: PASS(네이버 접속 없음, 실행 마커 미생성 확인)
- 사전 회귀(7개 파일, work order §9 목록 그대로): 전부 PASS, 합계 144건
  (`test_pc_network_pagination.py` 35 / `test_pc_network_browser_collector.py`
  34 / `test_pc_network_adaptive_settle.py` 18 /
  `test_network_product_integration_no_live.py` 11 /
  `test_pc_network_pipeline.py` 12 / `test_ui_network_start.py` 15 /
  `test_ui_network_wiring.py` 19) - 직전 PAGE-300-2B-2B 기록(144건)과 동일,
  회귀 없음
- parser 회귀: `test_pc_network_list_scraper.py` 42 PASS(GraphQL top-level list
  계약 포함, 직전 기록과 동일)

## live 결과(candidate/raw/unique/final)
- CAPTCHA·HTTP 429·timeout·navigation_error: 전부 발생 안 함(False)
- candidate_response_count=2, pagination_raw_item_count=20,
  pagination_unique_item_count=20, final_count=20, stop_reason=queue_exhausted
- pagination_page_count=2, pagination_click_count=1,
  pagination_stop_reason=`max_page_count_reached`(per_query_limit_reached 아님 -
  page 2가 신규 unique 0건을 반환해 override(2페이지) 상한에 그대로 도달)
- per_page_diagnostics:
  - page 1: candidate=1, raw_item_count=20, new_unique_count=20,
    duplicate_count=0, adaptive_wait_ms=1700
  - page 2: candidate=1, raw_item_count=0, new_unique_count=0,
    duplicate_count=0, adaptive_wait_ms=5000(hard cap 전체 대기 - 조기 종료
    안 됨, valid confirmed 없었기 때문)
- pagination_unverified_candidate_count=0, pagination_drain_item_count=0(§4/§6
  DOM identity 불일치·drain 관련 문제 없음 - page 2 DOM 전환 자체는 정상 확인됨)

## body snapshot 진단(이번 검증의 핵심)
- body_snapshot_success_count=2(page 1·page 2 candidate 모두 requestfinished
  시점 body snapshot 자체는 성공 - PAGE-300-2B-2A의 "response.json() 지연 접근
  실패" 문제는 재현되지 않음)
- body_snapshot_error_count=0, body_snapshot_total_bytes=78973bytes(원문은
  결과 JSON/로그에 저장하지 않음)
- **json_decode_error_count=1** - body snapshot은 성공했지만 그 bytes 중 1건
  (page 2 candidate)이 `json.loads()` 단계에서 디코드 실패
- parse_error_count=1(json_decode_error_count와 동일 candidate - 실제 harvest
  루프에서도 동일하게 error로 집계됨, 이중 집계나 누락 없음)
- graphql_page2_analysis: page2_diagnostics_present=true,
  page2_raw_item_count=0, page2_item_extraction_success=false - **parser
  (`_extract_list_items`/`_find_item_lists`)가 item을 못 찾은 것이 아니라, JSON
  디코드 자체가 실패해 parser 호출 이전 단계에서 이미 실패**했다(§15 "정상
  JSON인데 item 추출 0"인 HOLD 케이스가 아니라 §12 "JSON decode 실패" FAIL
  케이스에 해당)
- 알려진 한계(이번 harness가 새로 추가한 진단이 아님, production의 기존 계약):
  `body_snapshot_error_type`/`body_snapshot_error_message`는 candidate가
  requestfinished/requestfailed 단계에서 실패했을 때만 채워지며, snapshot
  자체는 성공했지만 이후 `json.loads()`가 실패한 경우의 구체적 예외
  타입/메시지는 현재 production 반환 계약에 노출되지 않는다(`_ensure_parsed`
  내부에서만 소비되고 버려짐) - 이번 harness는 원본 body를 별도로 다시
  파싱하지 않았으므로(작업 지시 §6/§15 금지 사항) 정확한 decode 실패 원인
  (인코딩/압축/빈 응답 등)은 이번 결과만으로는 확정할 수 없다.

## page 1·2 ID 교차 검증
- page1_unique_id_count=20, page2_unique_id_count=0(추출된 item 자체가 0건),
  page_intersection_count=0, total_unique_id_count=20
- pre_export_dedup_check: place_id 20건 전부 존재, 중복 0건, 플레이스 URL
  중복 0건

## Excel 검증
- exporter_call_count=1(정확히 1회)
- 헤더: 업체명/업종/새로오픈여부/리뷰수/주소/대표전화/플레이스 URL/수집일/
  홈페이지/인스타/블로그(11개, MERGED_COLUMNS와 완전 일치)
- data_row_count=20(final_count와 일치), 새로오픈여부 전부 빈칸, 내부 필드
  (place_id/source_city/source_district/source_subregion/source_layer/
  source_query) 미노출, 플레이스 URL 중복 0건

## 성능
session_ready_seconds=0.80, orchestrator_seconds=10.79,
session_teardown_seconds=0.25, export_seconds=0.05, total_wall_seconds=11.91

## 최종 판정: **FAIL**
work order §12 기준 "page 2 response가 candidate로 등록되고 body snapshot도
성공했으나 JSON decode 실패 → FAIL"에 정확히 해당한다
(`json_decode_error_count=1 > 0`). fail_conditions 중
`json_decode_error_present=true`만 True이고 나머지(page3 접근/body snapshot
자체 실패/exporter 중복/override 미복구/2차 live 등)는 전부 False - 이번
FAIL의 유일한 원인은 JSON decode 실패다. PAGE-300-2B-2B에서 목표로 했던
"response body lifecycle 문제 해결"은 확인됐으나(snapshot 성공률
2/2=100%), 그 다음 단계(디코드 가능한 유효 JSON인지)에서 새로운 문제가
실측으로 드러났다.

## production·tests 무수정 확인
`git status --short`/`git diff --name-status`/`git diff --stat`/
`git diff --check` 전부 출력 없음(변경 없음) - `scratchpad/`는
`.gitignore`(13행)에 의해 전체 무시되므로 신규 harness/결과 JSON/Excel/마커도
tracked 변경으로 나타나지 않는다. 이 PROJECT_STATE.md append만이 유일한
tracked 변경이다. `src/*`, `tests/*`, `app.py`, `src/ui.py`, `src/exporter.py`,
`src/pc/network_pipeline.py`, `src/pc/browser_session.py` 전부 무수정.

## 결과 파일(Git 미포함)
- `scratchpad/arch300_page300_probe/results/page300_2b2c/
  PAGE300_2B2C_LIVE_STARTED.marker`
- `scratchpad/arch300_page300_probe/results/page300_2b2c/
  page300_2b2c_live_40_result_20260720_162022.json`
- `scratchpad/arch300_page300_probe/results/page300_2b2c/
  page300_2b2c_live_40_20260720_162022.xlsx`

## 다음 단계
FAIL - production 수정 전 재-live 금지(work order §19 FAIL 분기 그대로).
production을 수정하지 않고 원인부터 좁혀야 한다: page 2 candidate의
body_snapshot bytes가 왜 `json.loads()`에서 실패하는지(BOM 이외의 인코딩,
gzip/brotli 등 압축 해제 여부, 빈 응답, truncated body 등 가능성) 확인하는
no-live 정밀 진단이 먼저 필요하다 - 구체적인 디코드 실패 타입/메시지를
production 반환 계약에 임시로(진단 전용, capture_artifacts 유사 패턴) 노출하는
별도 진단 단계를 검토해야 한다. 과거 PAGE 기록은 수정하거나 삭제하지 않았다.

# 2026-07-20 PAGE-300-2B-2D snapshot 무결성 및 JSON bytes decode 보완

## PAGE-300-2B-2C FAIL 결과(재확인)
- body_snapshot_success_count=2, body_snapshot_error_count=0,
  body_snapshot_total_bytes=78,973, json_decode_error_count=1
- 이전 독립 실측(PAGE-300-2B-2A): page1 body 약 78KB, page2 body 약 414KB
- 모순: 성공이 2건이면 합계가 약 490KB여야 하는데 실제로는 page1 크기만
  남았다 - 인코딩/압축/parser/GraphQL 배열 문제로 성급히 단정하지 않고
  snapshot 계약 자체(빈 body 처리, request-response 연결, JSON decode 방식)를
  먼저 no-live로 정밀 진단했다.

## 원인 후보와 채택된 수정
1. **성공 기준이 빈 bytes도 허용**(채택 - 가장 유력한 원인): requestfinished가
   `response.body()`로 0바이트를 받아도 기존 코드는 `body_snapshot_ready=True`로
   표시했다 - JSON 파싱 단계(`json.loads(b"")`)에서만 실패로 드러나
   `json_decode_error_count`에는 잡혔지만 `body_snapshot_total_bytes`에는 0을
   더해 "성공인데 크기 기여가 없는" 상태를 만들 수 있었다.
2. request-response 연결 실패 가능성: 구조상 이론적으로 가능성이 낮다고
   판단했으나 진단 카운터(§3)를 신설해 실측 가능하게 만들었다.
3. 동일 candidate 중복 성공 집계, JSON decode 방식(UTF-8 고정 가정) 문제:
   기존 idempotent guard로 이미 방지되고 있었으나(회귀 테스트로 재확인),
   decode 방식은 §6대로 `json.loads(bytes)` 직접 호출로 교체했다.

## snapshot 성공 기준 변경 / EmptyBody 처리
`body_snapshot_size == 0`이면 `body_snapshot_ready=False`,
`body_snapshot_error_type="EmptyBody"`로 확정하고 반환하며(BodyTooLarge 검사
이전에 수행), 성공으로 집계하지 않는다. 신규 진단 필드
`body_snapshot_empty_count`가 이 하위 집합만 별도로 센다.

## snapshot 3분류 불변식
`body_snapshot_success_count + body_snapshot_error_count +
snapshot_pending_count == candidate_response_count`가 항상 성립하도록
`_summarize_candidate_snapshots()` 단일 헬퍼로 계산을 통일했다(정상 반환과
navigation_error 조기 반환이 모두 이 헬퍼를 공유 - gpt-5.6-sol 1차 검토
Medium 지적으로 navigation_error 조기 반환이 하드코딩된 0/빈 리스트를
반환하던 문제를 발견해 반영했다).

## request-response 연결 무결성
- `unmatched_requestfinished_count`: candidate로 등록된 적 없는데 candidate
  URL/resource_type 패턴과 일치하는 request의 requestfinished가 발생하면
  증가(정상 비-candidate 리소스는 증가시키지 않음).
- `ambiguous_request_mapping_count`: 같은 request가 이미 candidate로
  등록됐는데 다른 response가 또 그 request를 참조하려 하면 기존 방어적
  dedupe 분기에서 증가시키고 두 번째 entry는 만들지 않는다.
- **gpt-5.6-sol 1차 검토 High 지적(수정 반영)**: `handle_request_finished`가
  `request.response()`를 재조회하면, ambiguous 상황에서 request가 나중에
  다른 response를 가리키도록 바뀌면 entry A의 메타데이터에 entry B의 body가
  섞일 수 있었다. candidate 등록 시점에 확정한 `entry["response"]`를
  우선 사용하도록 수정(`entry["response"]`가 없을 때만 `request.response()`
  fallback).

## JSON decode 방식 / BOM·배열 처리
`entry["body_snapshot"].decode("utf-8-sig")` 후 `json.loads(str)` 대신
`json.loads(bytes)`를 직접 호출한다(CPython 표준 json 모듈이 bytes 입력에
한해 BOM/UTF-8/UTF-16/UTF-32를 자체 감지). 압축 해제나 charset 추측 재시도는
전혀 하지 않는다. `_classify_bom`/`_classify_compression_magic`/
`_classify_first_non_whitespace_character` 3개 순수 분류 헬퍼를 추가해
candidate별 안전 진단(원본 없이 enum 라벨만)을 제공한다.

## body 크기 상한의 정확한 의미
기존 `_MAX_CANDIDATE_BODY_BYTES`(2MB)는 그대로 유지하되 의미를 명확히 했다:
snapshot 장기 보존 상한이자 명백히 큰 Content-Length의 사전 차단일 뿐,
모든 네트워크 body 할당을 완전히 막는 절대 hard cap은 아니다(content-length
헤더가 없거나 부정확하면 여전히 body() 호출 후 실제 길이로만 판단).

## 신규 진단 필드
`body_snapshot_empty_count`, `snapshot_pending_count`,
`unmatched_requestfinished_count`, `ambiguous_request_mapping_count`,
`candidate_snapshot_diagnostics`(candidate별 sequence_id/url_kind/method/
resource_type/status/content_type/content_encoding/body_snapshot_state/
body_snapshot_size/body_snapshot_error_type/json_top_level_type/
json_decode_error_type/first_non_whitespace_character/bom_type/
compression_magic/processed/generation - 원본 body·업체 row는 절대 포함하지
않음). 기존 필드(`body_snapshot_success_count`/`body_snapshot_error_count`/
`body_snapshot_total_bytes`/`json_decode_error_count`)는 그대로 유지하되
navigation_error 조기 반환을 포함한 모든 반환 경로에 동일하게 포함된다.

## 변경 파일
- `src/pc/network_browser_collector.py`(핵심 변경 - EmptyBody 판정, 3분류
  불변식 헬퍼, request-response 연결 진단, json.loads(bytes) 전환, candidate
  안전 진단 헬퍼 3종)
- `tests/test_pc_network_browser_collector.py`(신규 케이스 17건 추가 - snapshot
  total bytes 정확한 합, EmptyBody 미집계, 중복 requestfinished byte 1회 집계,
  unmatched/ambiguous request identity 2건, UTF-8 object/array/BOM/UTF-16 decode
  4건, HTML/gzip/zero-length body 3건, 3분류 불변식, candidate diagnostics
  원문 미노출, GraphQL top-level list end-to-end, navigation_error 불변식 유지)
- `tests/test_pc_network_pagination.py`(PAGE-300-2B-2C 실제 결과 재현 케이스
  1건 추가 - page1 약 78KB/page2 약 414KB 합성 body로 total_bytes 정확한 합과
  final rows=40 확인, 기존 GraphQL 소스 정적 검사 테스트를 "graphql" 부분
  문자열 하드코딩 자체가 아니라 실제 의존 지표(operationName/
  variables.input.page/variables["input"])만 검사하도록 정밀화 - url_kind
  진단 라벨이 페이지네이션 결정 로직과 무관함을 명시)
- `src/pc/network_list_scraper.py`: 무수정(이번 단계 범위 아님 - 오류가
  parser 전달 이전 단계에서 발생했기 때문)
- `tests/test_pc_network_adaptive_settle.py`: 무수정(회귀만 재확인)

## GPT-5.6-Sol(Codex MCP, read-only) 독립 검토 결과(2라운드)
1차 검토: High 1건(ambiguous request에서 request.response() 재조회 시 다른
candidate의 body가 섞일 수 있음 - 실제 재현 시나리오 제시), Medium 1건
(navigation_error 조기 반환이 3분류 불변식을 위반할 수 있음 - 재현 시나리오
제시). 둘 다 수정 반영(위 절 참고) + 재현 회귀 테스트 2건 추가.
2차 재검토: 두 수정 모두 원래 결함을 실제로 해결했으며 새로운 회귀 없음을
확인. 다만 ambiguous 재현 테스트의 이벤트 순서가 "A를 먼저 requestfinished로
확정 후 B로 교체"라 idempotent guard 때문에 수정 전 코드도 우연히 통과할
수 있었다는 테스트 강도 지적을 받아, "response(A) → response(B, ambiguous
판정) → request가 B를 가리키도록 재할당 → 최초이자 유일한 requestfinished"
순서로 재구성해 실제 결함을 확실히 가둔다(최종 재실행도 PASS).

## 남은 위험(문서화된 알려진 한계)
- unmatched_requestfinished_count/ambiguous_request_mapping_count는 정상
  Playwright 계약상 거의 발생하지 않아야 하는 방어적 진단이다 - 실제 live에서
  0이 아니게 나오면 그 자체로 이례적 신호이므로 즉시 조사 대상으로 다뤄야
  한다(정상으로 넘기면 안 됨).
- EmptyBody 판정은 "0바이트"만 잡는다 - PAGE-300-2B-2C의 78,973바이트가
  실제로 EmptyBody 때문이었는지, 아니면 여전히 다른 원인(예: 압축된 매우 작은
  응답, 트렁케이션)이었는지는 이번 no-live 수정만으로는 확정할 수 없다 -
  다음 실제 live(PAGE-300-2B-2E)에서 candidate_snapshot_diagnostics를 직접
  관찰해야 확정된다.
- gpt-5.6-sol이 지적한 대로 `body_snapshot_success_count`는 body 확보
  성공일 뿐 업체 목록 추출 성공을 의미하지 않는다 - 다음 live 판정은 반드시
  `success+error+pending==candidate_response_count`,
  `unmatched_requestfinished_count==0`, `ambiguous_request_mapping_count==0`,
  `snapshot_pending_count==0`, `body_snapshot_empty_count==0`,
  `json_decode_error_count==0`, page2 candidate의 `processed=True` 및 실제
  신규 row 존재를 모두 함께 확인해야 한다(gpt-5.6-sol 권고 그대로 채택).

## 신규 테스트 요약
- pagination: 35 → 36 PASS(PAGE-300-2B-2C 재현 1건 추가).
- browser_collector: 34 → 50 PASS(신규 17건: snapshot 무결성/EmptyBody/
  request-response 연결/JSON decode/BOM/압축/불변식/진단 누출 방지/GraphQL
  top-level list/navigation_error 불변식).
- adaptive_settle: 18 PASS(무수정, 회귀만 재확인).
- network_product_integration_no_live/pipeline/ui_network_start/
  ui_network_wiring: 무수정, 회귀만 재확인(각 11/12/15/19 PASS).
- network_list_scraper(7개 회귀 파일에는 미포함, 별도 확인): 42 PASS(무수정).

## 전체 관련 회귀 파일별 PASS/FAIL(최종)
| 파일 | PASS | FAIL |
|---|---|---|
| tests/test_pc_network_pagination.py | 36 | 0 |
| tests/test_pc_network_browser_collector.py | 50 | 0 |
| tests/test_pc_network_adaptive_settle.py | 18 | 0 |
| tests/test_network_product_integration_no_live.py | 11 | 0 |
| tests/test_pc_network_pipeline.py | 12 | 0 |
| tests/test_ui_network_start.py | 15 | 0 |
| tests/test_ui_network_wiring.py | 19 | 0 |
| tests/test_pc_network_list_scraper.py(별도) | 42 | 0 |

**7개 회귀 파일 합계: 161건, FAIL 0.**(작업 전 144건 대비 신규 17건).
list_scraper 별도 42건 포함 전체 203건, FAIL 0.

## 실제 live 미실행 확인
확인됨 - BrowserSession/Playwright 실행, 네이버 접속, page 2 실제 클릭,
40건/100건 재실행, Excel 생성 전부 하지 않았다. Fake 객체와 synthetic bytes만
사용했다.

## Git 상태
`git status --short`/`git diff --name-status` 기준 변경 파일은
`src/pc/network_browser_collector.py`, `tests/test_pc_network_browser_
collector.py`, `tests/test_pc_network_pagination.py` + 이 `PROJECT_STATE.md`
append뿐이다(작업 허용 범위와 정확히 일치). `src/pc/network_list_scraper.py`,
`src/pc/network_pipeline.py`, `src/pc/browser_session.py`, `src/ui.py`,
`src/exporter.py`, `app.py`, `tests/test_pc_network_adaptive_settle.py`,
`tests/test_network_product_integration_no_live.py`,
`tests/test_pc_network_list_scraper.py` 전부 무수정. git add/commit/push/
reset/checkout/restore 전부 수행하지 않았다.

## PAGE-300-2B-2E 진입 가능 여부
gpt-5.6-sol 2차 재검토 PASS - no-live 수정과 회귀만으로는 "실제 page2 body가
더 이상 EmptyBody가 아님"을 증명할 수 없으므로(§남은 위험), PAGE-300-2B-2E
(동일 검색어, page 1→2, per_query_limit=40/target_count=40, 실제 live 정확히
1회, retry 0, page 3 접근 금지)로 진입해 candidate_snapshot_diagnostics를
직접 관찰하는 것을 권장한다. 이번 단계에서 채택한 최소 PASS 조건(위 "남은
위험" 절 그대로)을 하나라도 어기면 조건부 PASS가 아니라 즉시 HOLD/FAIL로
판정한다. 과거 PAGE 기록은 수정하거나 삭제하지 않았다.

# 2026-07-20 PAGE-300-2B-2E snapshot 무결성 적용 후 실제 40건 재검증

## 기준/실행 정보
- 기준 커밋: `dd2ec0fa98a48e679a7f155737a41a93d4992976`(개선: Network snapshot
  무결성과 JSON bytes 진단 보강) - 작업 전/후 동일, 변경 없음
- 검색어: "서울특별시 강동구 카페", query_count=1, per_query_limit=40,
  target_count=40, settle_ms=5000
- 실행 마커: `scratchpad/arch300_page300_probe/results/page300_2b2e/
  PAGE300_2B2E_LIVE_STARTED.marker`(harness 시작 직전 `open(..., "x")`로 원자
  생성, 삭제하지 않음)
- live 실행 횟수: 정확히 1회(20260720_171700), retry_count=0, 재실행 없음
- 허용 페이지: [1, 2] - page 3 이상 접근 없음(`pagination_page_count=2`)
- production `_MAX_PAGINATION_PAGES` 원래 값 5 → live override 2 → 실행 후
  복구 값 5(`production_max_pages_after_restore=5`, 복구 성공)

## harness/사전 검증
- harness: `scratchpad/arch300_page300_probe/page300_2b2e_live_40.py`(신규,
  page300_2b2c_live_40.py의 구조를 재사용하되 그 harness는 수정하지 않음.
  collector/parser/snapshot 로직은 harness에서 재구현하지 않고 production
  함수만 호출)
- 컴파일: `py_compile` PASS
- `--check-config`: PASS(네이버 접속 없음, 실행 마커 미생성 확인, PAGE-300-2B-2D
  신규 진단 필드 10개 소스 존재 정적 확인)
- 사전 회귀(7개 파일): 전부 PASS, 합계 161건(직전 PAGE-300-2B-2D 기록과 동일,
  회귀 없음) - `test_pc_network_pagination.py` 36 / `test_pc_network_browser_
  collector.py` 50 / `test_pc_network_adaptive_settle.py` 18 /
  `test_network_product_integration_no_live.py` 11 / `test_pc_network_
  pipeline.py` 12 / `test_ui_network_start.py` 15 / `test_ui_network_
  wiring.py` 19
- parser 회귀: `test_pc_network_list_scraper.py` 42 PASS(직전 기록과 동일)

## CAPTCHA·429·오류
전부 발생 안 함(False) - active_captcha_detected=False, status_429_seen=False,
timeout=False, navigation_error=False

## candidate/pagination 결과
- candidate_response_count=2, pagination_click_count=1, pagination_page_count=2,
  pagination_stop_reason=`per_query_limit_reached`(2B-2C와 달리 max_page_count_
  reached가 아니라 목표 도달로 정상 종료 - page2가 신규 데이터를 실제로
  반환했다는 뜻)
- per_page_diagnostics:
  - page 1: candidate=1, raw_item_count=20, new_unique_count=20, duplicate=0,
    adaptive_wait_ms=1800
  - page 2: candidate=1, raw_item_count=**70**, new_unique_count=70,
    duplicate=0, adaptive_wait_ms=5000(hard cap 전체 대기)
- pagination_unverified_candidate_count=0, pagination_drain_item_count=0
- pagination_raw_item_count=90, pagination_unique_item_count=90(local, cap
  전) → per_query_limit=40으로 capped_rows=40, stop_reason=`target_reached`
  (orchestrator 레벨)

## snapshot success/error/empty/pending 및 불변식(이번 검증의 핵심)
- body_snapshot_success_count=2, body_snapshot_error_count=0,
  **body_snapshot_empty_count=0**, snapshot_pending_count=0
- unmatched_requestfinished_count=0, ambiguous_request_mapping_count=0
- json_decode_error_count=0, parse_error_count=0
- snapshot_classified_count(2) == candidate_response_count(2): **일치**
- body_snapshot_total_bytes=490,963
- success_diag_bytes(candidate_snapshot_diagnostics의 success entry
  body_snapshot_size 합) = 490,963 → **body_snapshot_total_bytes와 정확히
  일치**(PAGE-300-2B-2C의 "success=2인데 total_bytes가 page1 크기만"이던
  모순이 완전히 해소됨)

## page 1·2 candidate 안전 진단
- page 1(all_search, GET, xhr, status=200, content_type=`application/
  json;charset=UTF-8`, content_encoding=`gzip`): body_snapshot_state=success,
  body_snapshot_size=**78,390**(PAGE-300-2B-2A 실측 약 78KB와 일치),
  json_top_level_type=object, first_non_whitespace_character="{",
  bom_type=none, compression_magic=none, processed=true
- page 2(graphql_candidate, POST, fetch, status=200, content_type=
  `application/json; charset=utf-8`, content_encoding=`br`):
  body_snapshot_state=success, body_snapshot_size=**412,573**(PAGE-300-2B-2A
  실측 약 414KB와 일치), json_top_level_type=array,
  first_non_whitespace_character="[", bom_type=none, compression_magic=none,
  processed=true
- content_encoding이 gzip/br로 찍혀 있지만 body_snapshot_size/first_
  non_whitespace_character/json_top_level_type이 이미 압축 해제된 JSON
  본문 기준이다 - Playwright의 `response.body()`가 압축 해제된 bytes를
  반환하므로(브라우저 레벨에서 이미 decompress됨) production이 별도로
  압축을 해제할 필요가 없었다는 것이 실측으로 확인됐다(§6 "임의 압축 해제
  금지" 원칙과 무관 - 애초에 압축된 채로 온 적이 없었다).
- candidate가 정확히 2개(all_search 1개, graphql_candidate 1개, 그 외 0개) -
  목록 response 구분 불명확 문제 없음

## page별 ID 교차 검증
- page1_unique_id_count=20, page2_unique_id_count=20, page_intersection_
  count=0, total_unique_id_count=40(최종 export된 40행 기준 - page2의 실제
  raw/unique는 70건이었으나 per_query_limit=40 cap으로 인해 최종 40행 중
  page2 기여분은 20행만 반영됨, 참고 진단이며 production 계약 검증의 유일한
  근거는 아님)

## exporter/Excel
- exporter_call_count=1(정확히 1회)
- Excel 헤더 11개, MERGED_COLUMNS와 완전 일치, data_row_count=40(final_count와
  일치), 새로오픈여부 전부 빈칸, 업체명 빈값 0건, 플레이스 URL 중복 0건,
  내부 필드(place_id/source_city/source_district/source_subregion/
  source_layer/source_query) 미노출

## 성능
session_ready_seconds=0.98, orchestrator_seconds=10.84,
session_teardown_seconds=0.27, export_seconds=0.02, total_wall_seconds=12.12

## 최종 판정: **FULL PASS**
work order §13 FULL PASS 조건 전부 충족: fail_conditions 전부 False,
hold_conditions 전부 False, full_pass_conditions 25개 전부 True(candidate_
response_count>=2, snapshot 불변식 성립, error/empty/pending/unmatched/
ambiguous/json_decode_error/parse_error 전부 0, page1 candidate
success+object+processed, page2 candidate success+array+processed,
pagination_click_count=1, pagination_page_count=2, stop_reason=
per_query_limit_reached, final_count=40, exporter 1회, Excel 40행/11열,
새로오픈 전부 빈칸, 내부 필드 미노출, production max pages 5 복구,
unverified=0, page 교집합=0).

PAGE-300-2B-2D에서 채택한 EmptyBody 판정/3분류 불변식/request-response
연결 진단/json.loads(bytes) 전환이 실제 live에서 page 2 GraphQL candidate의
body snapshot을 정상 확보(412,573바이트, 0바이트 아님)하고 JSON decode도
정상 성공시켜, PAGE-300-2B-2C의 "success=2인데 total_bytes 불일치·decode
실패" 모순이 실제로 해소됐음을 확인했다.

## production·tests 무수정 확인
`git status --short`/`git diff --name-status`/`git diff --stat`/
`git diff --check` 전부 출력 없음(live 실행 직후 기준, PROJECT_STATE.md
append 전) - `scratchpad/`는 `.gitignore`로 전체 무시되므로 신규 harness/
결과 JSON/Excel/마커도 tracked 변경으로 나타나지 않는다. 이 PROJECT_STATE.md
append만이 유일한 tracked 변경이다. `src/*`, `tests/*`, `app.py`, `src/ui.py`,
`src/exporter.py`, `src/pc/network_pipeline.py`, `src/pc/browser_session.py`
전부 무수정.

## 결과 파일(Git 미포함)
- `scratchpad/arch300_page300_probe/results/page300_2b2e/
  PAGE300_2B2E_LIVE_STARTED.marker`
- `scratchpad/arch300_page300_probe/results/page300_2b2e/
  page300_2b2e_live_40_result_20260720_171700.json`
- `scratchpad/arch300_page300_probe/results/page300_2b2e/
  page300_2b2e_live_40_20260720_171700.xlsx`

## 다음 단계
FULL PASS - work order §17에 따라 PAGE-300-2B-3(실제 page 1~5 최대 100건
live) 진입을 다음 단계로 권장한다. 단, 이번 실측에서 page 2가 raw 70건(20건이
아님)을 반환한 사실이 새로 확인됐으므로, 100건 단계에서는 페이지당 정확히
20건이라는 가정 없이 실제 unique 누적 추이를 있는 그대로 관찰해야 한다(다음
단계의 참고 사항으로 기록, 이번 단계 판정을 바꾸지 않음). 100건 live를 이번
보고에서 임의로 시작하지 않고 중단한다. 과거 PAGE 기록은 수정하거나
삭제하지 않았다.

# 2026-07-20 PAGE-300-2B-3 실제 최대 100건 live 검증

## 기준/실행 정보
- 기준 커밋: `a42af98b2d509e34e1f8f8e214c5ca547242778c`(검증: page 2 추가
  수집으로 단일 조합 40건 달성) - 작업 전/후 동일, 변경 없음
- 검색어: "서울특별시 강동구 카페", query_count=1, per_query_limit=100,
  target_count=100, settle_ms=5000
- 실행 마커: `scratchpad/arch300_page300_probe/results/page300_2b3/
  PAGE300_2B3_LIVE_STARTED.marker`(원자 생성, 삭제하지 않음)
- live 실행 횟수: 정확히 1회(20260720_172602), retry_count=0, 재실행 없음
- production `_MAX_PAGINATION_PAGES`: **override 없이 production 기본값
  5 그대로 사용**(live_override_used=False, 실행 전/후 동일하게 5)

## harness/사전 검증
- harness: `scratchpad/arch300_page300_probe/page300_2b3_live_100.py`(신규,
  page300_2b2e_live_40.py 구조를 재사용하되 그 harness는 수정하지 않음)
- 컴파일: `py_compile` PASS
- `--check-config`: PASS(production _MAX_PAGINATION_PAGES=5 확인, PAGE-300-2B-2D
  신규 진단 필드 10개 소스 존재 정적 확인, 네이버 접속 없음, 마커 미생성)
- 사전 회귀(7개 파일): 전부 PASS, 합계 161건(직전 PAGE-300-2B-2E 기록과 동일)
- parser 회귀: 42 PASS(동일)

## 접근 페이지 / CAPTCHA·429
- 접근 페이지: **page 1, 2, 3**(page 4·5는 방문하지 않음 - page 3에서 이미
  누적 unique 100건에 도달해 정상 조기 중단, work order §11 "page 5까지
  방문하지 않았다는 이유로 실패 처리하지 않는다" 그대로 적용)
- page 6 이상 접근: 없음(`pagination_page_count=3`, production 상한 5 이내)
- CAPTCHA·HTTP 429·timeout·navigation_error: 전부 발생 안 함(False)

## candidate/snapshot 결과
- candidate_response_count=**3**, body_snapshot_success_count=3, error/empty/
  pending=0/0/0
- snapshot_classified_count(3) == candidate_response_count(3): **일치**
- body_snapshot_total_bytes=**908,004**
- success_diag_bytes(candidate_snapshot_diagnostics success entry 합) =
  **908,004** → **정확히 일치**
- unmatched_requestfinished_count=0, ambiguous_request_mapping_count=0
- json_decode_error_count=0, parse_error_count=0
- 3개 candidate 전부 body_snapshot_state=success, size>0, processed=true,
  json_decode_error_type=""

## candidate별 안전 진단(generation 기준 집계)
- generation 1(all_search, GET, xhr): success, size=78,390, object, "{"
- generation 2(graphql_candidate, POST, fetch): success, size=412,592, array,
  "["(page 2 실측과 거의 동일 - 이전 40건 단계 412,573과 19바이트 차이,
  실측 변동 범위 내)
- generation 3(graphql_candidate, POST, fetch): success, size=417,022, array,
  "["(page 3도 page 2와 동일한 graphql 엔드포인트 패턴)

## 페이지별 raw·new unique·duplicate
- page 1: candidate=1, raw=20, new_unique=20, duplicate=0, adaptive_wait_ms=1700
- page 2: candidate=1, raw=70, new_unique=70, duplicate=0, adaptive_wait_ms=5000
- page 3: candidate=1, raw=70, new_unique=70, duplicate=0, adaptive_wait_ms=5000
  (단, 누적 unique가 100에 도달하는 시점에서 orchestrator가 target_reached로
  최종 rows를 100으로 trim - page 3 raw 70건 중 실제로 최종 export에 반영된
  신규 기여분은 10건뿐)
- pagination_unverified_candidate_count=0, pagination_drain_item_count=0(§4/§6
  DOM identity 문제 없음)

## 페이지 간 ID 중복 / 누적 unique
- cumulative_by_page: page1(unique 20, 누적 20) → page2(unique 70, 누적 90)
  → page3(unique 10, 누적 100 - trim 이후 최종 rows 기준 신규 기여분)
- total_cross_page_duplicate_count=0(페이지 간 중복 ID 없음)
- total_unique_id_count=100(Excel place_id 중복 0건과 일치)

## final_count / stop reason
- before_trim_count=100, final_count=**100**
- orchestrator stop_reason=`target_reached`
- pagination_stop_reason=`per_query_limit_reached`(쿼리 내부 per_query_limit=100
  도달로 인한 정상 종료)

## exporter/Excel
- exporter_call_count=1(정확히 1회)
- Excel 헤더 11개, MERGED_COLUMNS와 완전 일치, data_row_count=**100**(final_count와
  일치), 새로오픈여부 전부 빈칸, 업체명 빈값 0건, 플레이스 URL 중복 0건(고유
  100건), 내부 필드 미노출

## 성능
session_ready_seconds=0.80, orchestrator_seconds=16.63,
session_teardown_seconds=0.26, export_seconds=0.03, total_wall_seconds=17.74
(참고: page 2·3 모두 adaptive_wait_ms=5000으로 hard cap 전체 대기 - quiet
period 조기 종료가 발생하지 않음, 다음 성능 최적화 검토 시 참고)

## 최종 판정: **FULL PASS**
work order §11 FULL PASS 조건 전부 충족: fail_conditions 전부 False,
hold_conditions 전부 False, full_pass_conditions 23개 전부 True(최대 page
5 이내, snapshot 불변식 성립, error/empty/pending/unmatched/ambiguous/
json_decode_error/parse_error 전부 0, before_trim_count>=100, final_count=100,
stop_reason=target_reached, pagination_stop_reason=per_query_limit_reached,
exporter 1회, Excel 100행/11열, 새로오픈 전부 빈칸, 내부 필드 미노출,
unverified_candidate=0). page 4·5를 방문하지 않은 것은 work order §11에 따라
실패 사유가 아니다 - page 3에서 이미 목표에 도달했다는 뜻이다.

## production·tests 무수정 확인
`git status --short`/`git diff --name-status`/`git diff --stat`/
`git diff --check` 전부 출력 없음(live 실행 직후 기준, PROJECT_STATE.md
append 전) - `scratchpad/`는 `.gitignore`로 전체 무시되므로 신규 harness/
결과 JSON/Excel/마커도 tracked 변경으로 나타나지 않는다. 이 PROJECT_STATE.md
append만이 유일한 tracked 변경이다. `src/*`, `tests/*` 전부 무수정.

## 결과 파일(Git 미포함)
- `scratchpad/arch300_page300_probe/results/page300_2b3/
  PAGE300_2B3_LIVE_STARTED.marker`
- `scratchpad/arch300_page300_probe/results/page300_2b3/
  page300_2b3_live_100_result_20260720_172602.json`
- `scratchpad/arch300_page300_probe/results/page300_2b3/
  page300_2b3_live_100_20260720_172602.xlsx`

## 다음 단계
FULL PASS - work order §18에 따라 다음 단계는 **PAGE-300-3(page 6~10 다음
페이지 번호 묶음 전환 설계)**이며, 이는 먼저 별도 PoC와 no-live 구현으로
진행해야 한다. **100건 성공 직후 곧바로 300건 live를 실행하지 않는다**(work
order §18 명시 주의사항). 이번 보고에서 page 6 이상 접근이나 300건 live를
임의로 시작하지 않고 여기서 중단한다. 과거 PAGE 기록은 수정하거나 삭제하지
않았다.

# 2026-07-20 PAGE-300-2B-4 현재 최대 5페이지로 실제 300건 검증

## 전략 배경
PAGE-300-2B-3에서 page 2·3이 각각 70건의 신규 unique를 반환한 사실이
확인되어(20+70+70+70+70=300 산술적으로 가능), page 6 이후 "다음 페이지 번호
묶음" 전환을 구현하기 전에 현재 page 1~5 제한 구현만으로 실제 300건 도달
가능성을 먼저 검증했다. production 코드는 이번 단계에서 전혀 수정하지
않았다.

## 기준/실행 정보
- 기준 커밋: `a364c2ed4ccd3e19119a74db72813bd9fa38d428`(검증: 제한
  페이지네이션으로 단일 조합 100건 달성) - 작업 전/후 동일, 변경 없음
- 검색어: "서울특별시 강동구 카페", query_count=1, per_query_limit=300,
  target_count=300, settle_ms=5000
- 실행 마커: `scratchpad/arch300_page300_probe/results/page300_2b4/
  PAGE300_2B4_LIVE_STARTED.marker`(원자 생성, 삭제하지 않음)
- live 실행 횟수: 정확히 1회(20260720_181208), retry_count=0, 재실행 없음
- production `_MAX_PAGINATION_PAGES`: override 없이 production 기본값 5
  그대로 사용(live_override_used=False, 실행 전/후 동일하게 5)

## harness/사전 검증
- harness: `scratchpad/arch300_page300_probe/page300_2b4_live_300.py`(신규,
  page300_2b3_live_100.py 구조를 재사용하되 그 harness는 수정하지 않음)
- 컴파일: `py_compile` PASS
- `--check-config`: PASS(production max pages=5, override 없음, 신규 진단
  필드 10개 확인, 네이버 접속 없음, 마커 미생성)
- 사전 회귀(7개 파일): 전부 PASS, 합계 161건(직전 기록과 동일)
- parser 회귀: 42 PASS(동일)

## 실제 접근 페이지 / CAPTCHA·429
- 실제 접근 페이지: **page 1, 2**(page 3 클릭 시도 중 타임아웃으로 중단 -
  page 3 이상 실제 도달 없음, page 6 접근도 당연히 없음)
- CAPTCHA(active_captcha_detected): **False**(마커 미감지)
- HTTP 429(status_429_seen): **False**
- HTTP **405**(candidate 응답 status): page 2로 확정된 candidate가 405
  Method Not Allowed 응답을 받음(§상세 원인 참고 - 429/CAPTCHA 마커와는
  다른 신호)

## candidate/snapshot 결과
- candidate_response_count=2, body_snapshot_success_count=2, error/empty/
  pending=0/0/0
- snapshot_classified_count(2) == candidate_response_count(2): 일치
- body_snapshot_total_bytes=78,994 == success_diag_bytes(78,994): 일치
  (snapshot 자체의 성공/바이트 계산 메커니즘은 여전히 정확 - PAGE-300-2B-2D
  수정의 회귀 아님)
- **json_decode_error_count=1, parse_error_count=1**(work order §16 FAIL
  조건에 직접 해당)
- unmatched_requestfinished_count=0, ambiguous_request_mapping_count=0(
  request-response 연결 자체는 정상)

## candidate별 안전 진단(상세 원인)
- generation 1(all_search, GET, xhr, status=200): success, size=78,411,
  object, "{", processed=true, json_decode_error_type=""(page 1 정상)
- generation 2(graphql_candidate, POST, fetch, **status=405**,
  content_type=`text/html`): body_snapshot_state=**success**(body snapshot
  자체는 583바이트를 정상 확보함 - EmptyBody 아님), json_top_level_type=""
  (JSON이 아니므로 미확정), **json_decode_error_type="JSONDecodeError"**,
  first_non_whitespace_character="**<**"(HTML 오류 페이지), processed=true
- 즉 이 candidate는 "정상 GraphQL JSON 응답"이 아니라 **네이버 서버가
  405(Method Not Allowed)와 함께 HTML 오류 페이지를 반환한 응답**이었다 -
  snapshot 무결성(PAGE-300-2B-2D)은 이 상황을 정확히 감지해 EmptyBody가
  아닌 "성공적으로 확보한 HTML 오류 body"로 정직하게 분류했고, JSON decode
  실패로 올바르게 이어졌다(거짓 성공 없음).

## pagination 진단 / 클릭 실패 상세
- pagination_click_count=1(page 2로의 클릭은 성공 - DOM class diff로
  page_count도 2로 확정됨), pagination_page_count=2
- pagination_stop_reason=**pagination_click_error**
- pagination_error_message: `TimeoutError: Locator.click: Timeout 30000ms
  exceeded. ... waiting for get_by_role("button", name="3", exact=True)
  ... locator resolved to <a href="#" role="button" ...`(page 3 버튼
  locator는 정상적으로 resolve됐으나 실제 click() 자체가 30초 타임아웃 -
  버튼이 존재/활성 상태였음에도 클릭이 완료되지 않음, 즉 포인터 이벤트가
  가로채였거나 페이지가 이전 405 오류 이후 비정상 상태였을 가능성)
- per_page_diagnostics: page 1(raw=20, new_unique=20) / page 2(raw=0,
  new_unique=0 - 405 오류로 인해 실제 데이터 없음)
- pagination_unverified_candidate_count=0, pagination_drain_item_count=0

## 페이지별 raw·최종 기여 / 누적 unique
- page 1: raw=20, parser_new_unique=20, 최종 기여=20, 누적=20
- page 2: raw=0, parser_new_unique=0, 최종 기여=0, 누적=20(변화 없음)
- total_cross_page_duplicate_count=0, total_unique_id_count=20,
  target_reached_page=None(300건 목표에 도달하지 못함)

## final_count / stop reason
- before_trim_count=20, final_count=**20**(300건과 크게 미달)
- orchestrator stop_reason=`queue_exhausted`(단일 job이 정상 종료 처리됐으나
  navigation_error가 아닌 정상 반환 경로로 빠져나온 것 - collect_query
  자체는 pagination_click_error를 rows=20과 함께 정상적으로 반환했으므로
  orchestrator는 이를 CAPTCHA/429/target_reached가 아닌 큐 소진으로 처리)
- pagination_stop_reason=`pagination_click_error`(예상된 300건 목표
  page_reached도, per_query_limit_reached도 아님)

## exporter/Excel
- exporter_call_count=1(정확히 1회), 부분 rows(20건) 정상 저장(기존 계약
  유지 - 손실 없음)
- Excel 헤더 11개, MERGED_COLUMNS와 완전 일치, data_row_count=20(final_count와
  일치), 새로오픈여부 전부 빈칸, 업체명 빈값 0건, 내부 필드 미노출

## 성능
session_ready_seconds=0.61, orchestrator_seconds=42.18(page 3 클릭 30초
타임아웃이 대부분을 차지), session_teardown_seconds=0.22,
export_seconds=0.02, total_wall_seconds=43.04

## 최종 판정: **FAIL**
work order §16 FAIL 조건 중 `json_decode_error_present=true`와
`parse_error_present=true`가 True(나머지 FAIL 조건은 전부 False - EmptyBody/
snapshot error/unmatched/ambiguous/page6 접근/override 사용/exporter
중복/부분 rows 손실/두 번째 live/production 수정/Git 작업 전부 없음).
snapshot 무결성 메커니즘(PAGE-300-2B-2D) 자체는 이번에도 정확히 동작했다 -
405 HTML 오류 응답을 "성공적으로 확보한 비-JSON body"로 정직하게 분류하고
거짓 성공을 만들지 않았다. FAIL의 근본 원인은 **네이버 서버가 두 번째
페이지 요청에 405를 반환**했고, 그 직후 **page 3 버튼 클릭이 30초간 완료되지
않은** 것이다.

## production·tests 무수정 확인
`git status --short`/`git diff --name-status`/`git diff --stat`/
`git diff --check` 전부 출력 없음(live 실행 직후 기준, PROJECT_STATE.md
append 전) - `scratchpad/`는 `.gitignore`로 전체 무시되므로 신규 harness/
결과 JSON/Excel/마커도 tracked 변경으로 나타나지 않는다. 이 PROJECT_STATE.md
append만이 유일한 tracked 변경이다. `src/*`, `tests/*` 전부 무수정.

## 결과 파일(Git 미포함)
- `scratchpad/arch300_page300_probe/results/page300_2b4/
  PAGE300_2B4_LIVE_STARTED.marker`
- `scratchpad/arch300_page300_probe/results/page300_2b4/
  page300_2b4_live_300_result_20260720_181208.json`
- `scratchpad/arch300_page300_probe/results/page300_2b4/
  page300_2b4_live_300_20260720_181208.xlsx`

## 남은 위험 / 다음 단계
FAIL - work order §16에 따라 **production 수정 전 재-live 금지**.
- 405 응답과 뒤이은 click 30초 타임아웃이 우연한 일시적 네트워크 이슈였는지,
  아니면 네이버가 짧은 시간 내 반복 페이지 요청(첫 40건 검증 이후 두 번째
  live로 100건, 그리고 오늘 세 번째로 300건 시도)을 감지해 완만하게
  제한하기 시작한 신호인지 이번 결과만으로는 확정할 수 없다 - CAPTCHA
  마커는 감지되지 않았고(active_captcha_detected=False) 429도 아니었으므로
  (status_429_seen=False), 기존 안전 중단 로직이 다루도록 설계된 신호와는
  다른 종류의 서버 반응이다.
- 원인 확정 전 production의 CAPTCHA/429 감지 로직에 405를 추가하는 등의
  수정을 시도하지 않는다(work order 범위 밖).
- 다음 단계는 **no-live 정밀 진단**(원인 확정)이어야 하며, 확정 전에는
  page 6 전환 구현이나 추가 300건 live를 시작하지 않는다. 반대 검토 AI
  (GPT-5.6-Sol)의 사용 조건("page 4·5의 DOM 전환, candidate response 또는
  GraphQL 구조가 기존 page 2·3과 다르고 저장된 진단만으로 원인을 확정할 수
  없을 때")에 해당할 가능성이 있으므로, 다음 단계에서 독립 검토 활용을
  검토할 수 있다. 과거 PAGE 기록은 수정하거나 삭제하지 않았다.

# 2026-07-20 PAGE-300-2B-4A candidate HTTP 오류 안전 중단 보강

## PAGE-300-2B-4 FAIL 결과(재확인)
- 검색어 300건 목표, page 1 정상(HTTP 200 object) → page 2 클릭 성공(DOM
  class diff로 확정) → page 2 candidate가 **HTTP 405 + text/html(583바이트)**
  반환 → snapshot은 성공(EmptyBody 아님)했지만 production이 json.loads()까지
  시도해 실패(json_decode_error_count=1, parse_error_count=1) → 이후에도
  계속 "page 3" 버튼을 클릭하려다 Locator.click()이 **30초 타임아웃**돼서야
  우연히 멈춤(의도된 안전 중단이 아니었음).

## 핵심 해석
snapshot 시스템(PAGE-300-2B-2D)은 정상 작동했다 - 문제는 candidate가 정상
JSON이 아니라 HTTP 405/HTML 오류 응답을 반환했는데도 production이 이를
구분하지 않고 JSON decode를 시도한 뒤, 계속 다음 페이지를 클릭하려 시도한
제어 흐름 결함이었다.

## candidate HTTP 오류 분류 / non-JSON 분류
- candidate entry에 신규 필드 `candidate_error_type`(기본 "") 추가.
- HTTP 상태 분류(`_classify_candidate_http_status`)는 **candidate 등록
  시점(response handler)**에 body snapshot 성공/실패와 무관하게 즉시
  확정한다(status가 200~299 범위 밖이면 "CandidateHttpError") - 최초 구현은
  이 판정을 `_ensure_parsed`의 body_snapshot_ready 분기 안에만 두어 snapshot
  자체가 실패한 non-2xx candidate가 누락되는 결함이 있었고, gpt-5.6-sol
  1차 검토(Medium)에서 지적받아 수정했다(§아래 GPT-5.6-Sol 검토 절 참고).
- HTTP 2xx(또는 status 미확인)인 candidate는 body의 첫 유효 문자가 "{"
  또는 "["가 아니면 "NonJsonCandidateBody"로 분류한다 - Content-Type
  헤더만으로 차단하지 않고 body 내용(first_non_whitespace_character) 기준
  으로만 판단하므로, Content-Type이 누락되거나 text/plain으로 잘못 표기돼도
  실제 body가 "{"/"["로 시작하면 정상 decode를 허용한다.
- 두 경우 모두 json.loads()를 아예 호출하지 않으므로 `json_decode_error_type`
  은 채우지 않는다("JSON decode 자체를 시도하지 않았기 때문").

## 다음 페이지 클릭 차단(fail-closed 계약)
- 공유 헬퍼 `_classify_page_candidate_error(ctx, start_index, end_index)`를
  신설해, 지정된 candidate 인덱스 범위에 candidate HTTP 오류 > non-JSON >
  snapshot 오류 > JSON decode 오류 우선순위로 pagination_stop_reason
  (candidate_http_error / candidate_non_json_response / candidate_snapshot_
  error / candidate_json_decode_error)을 결정한다.
- 이 헬퍼를 **3곳**에서 호출한다: (1) 새로 확정된 페이지의 메인 harvest
  직후, (2) 다음 페이지 버튼을 찾은 뒤 클릭 기준점을 확정하기 전 첫 번째
  drain 직후, (3) class_before를 읽은 뒤 추가 도착 candidate를 처리하는
  두 번째 drain 직후 - 처음에는 (1)만 구현했으나 gpt-5.6-sol 1차 검토(High)
  에서 "drain 경로로 늦게 도착하는 오류 candidate는 이 검사를 우회해 다음
  페이지 클릭이 그대로 진행될 수 있다"는 지적을 받아 (2)/(3)도 추가했다.
- 어느 경로에서든 오류가 감지되면 pagination_stop_reason을 설정하고 즉시
  break한다 - DOM class diff로 이미 확정된 pagination_page_count는 되돌리지
  않는다(페이지 전환 자체와 데이터 품질은 별개 판단).

## snapshot 의미 유지 / 429 기존 계약
- `body_snapshot_success_count=2, body_snapshot_error_count=0,
  candidate_http_error_count=1`처럼 snapshot 성공과 candidate HTTP 오류가
  동시에 성립할 수 있다(서로 다른 의미) - 불변식(success+error+pending==
  candidate_response_count)은 그대로 유지된다.
- 기존 `status_429_seen=True` 계약(429 응답이면 candidate 여부와 무관하게
  무조건 설정)은 변경하지 않았다. 429 candidate는 candidate_http_error_
  count/candidate_http_status_counts에도 추가로 집계되며, 이 중복은
  의도된 정책이다(하나는 보안 중단 신호, 다른 하나는 candidate 처리 진단).

## 신규 진단 필드
`candidate_http_error_count`, `candidate_non_json_count`,
`candidate_http_status_counts`(status별 카운트 dict),
`candidate_processing_error_count`(snapshot 실패/미확정/HTTP오류/non-JSON/
decode실패를 모두 합친 총계). 기존 `json_decode_error_count` 계산 방식도
함께 수정했다 - 이전에는 "harvest에서 error로 확정된 모든 candidate"를
셌지만(candidate_error_type 도입 전에는 동일한 의미였음), 이제는
`entry["json_decode_error_type"]`이 실제로 채워진 경우만 센다(HTTP 오류/
non-JSON 판정으로 decode 자체를 시도하지 않은 candidate는 제외). 모든
반환 경로(navigation_error 조기 반환 포함)에 기본값(0/{}/0)과 함께
포함된다(`_summarize_candidate_snapshots` 공유 헬퍼로 통일).

## raw HTML 미노출
`candidate_snapshot_diagnostics`/`pagination_error_message`/rows/전체 result
dict 어디에도 원본 HTML body가 노출되지 않음을 고유 마커 기반 테스트로 확인.

## 변경 파일
- `src/pc/network_browser_collector.py`(핵심 변경 - candidate_error_type 필드,
  HTTP 상태/non-JSON 분류, `_classify_page_candidate_error` 공유 헬퍼,
  drain 2곳 포함 3개 호출부, 신규 진단 필드 4종)
- `tests/test_pc_network_browser_collector.py`(신규 케이스 8건 추가 - HTTP
  405/403/500/429 각각, Content-Type 누락/text-plain 경로 3건, 429+EmptyBody
  이중 집계 확인; 기존 3건을 새 분류 체계에 맞게 갱신 - HTML/gzip body
  테스트가 이제 candidate_error_type=NonJsonCandidateBody를 기대하도록
  수정, json_decode_error 테스트는 body를 "{not valid json"으로 바꿔 원래
  의도(진짜 decode 실패) 유지)
- `tests/test_pc_network_pagination.py`(신규 케이스 5건 추가 - page2 HTTP
  405/non-JSON 각각 page3 클릭 차단, HTML 원문 미노출, PAGE-300-2B-4 정확
  재현, drain 경로 지연 도착 오류 재현; 기존 drain parse_error 테스트 1건을
  새 fail-closed 계약에 맞게 갱신 - 이제 drain된 오류 candidate는 다음
  페이지 클릭 자체를 막는다)
- `tests/test_pc_network_adaptive_settle.py`: 무수정(회귀만 재확인)
- `src/pc/network_list_scraper.py`: 무수정(이번 단계 범위 아님)

## GPT-5.6-Sol(Codex MCP, read-only) 독립 검토 결과(2라운드)
1차 검토: **High 1건**(drain 경로 - `_apply_pending_drain()` 호출 후 candidate
오류 상태를 재검사하지 않고 곧바로 click()으로 진행해, 클릭 직전 200ms
drain에서 늦게 harvest된 오류 candidate가 다음 페이지 클릭을 막지 못함 -
정확한 재현 시나리오와 함께 지적), **Medium 1건**(HTTP 상태 분류가
body_snapshot_ready 분기 안에만 있어 HTTP 429 + EmptyBody 같은 조합에서
candidate_http_error_count 누락 - 재현 시나리오 제시). 둘 다 수정 반영(위
절 참고) + 재현 회귀 테스트 3건 추가.
2차 재검토: 두 수정 모두 원래 결함을 실제로 해결했으며 정상적인 다중
페이지/drain 흐름에서 오탐(정상 candidate를 오류로 잘못 판정)도 발생하지
않음을 확인. 다만 **매우 좁은 이론적 타이밍 공백** 1건을 추가로 발견 - 두
번째 drain 검사 직후부터 실제 `click()` 호출 사이에 있는
`scroll_into_view_if_needed()` 실행 중 candidate가 도착하면 이 경로는
재검사되지 않는다(합성 검증 결과 405는 결국 감지되지만 page 2 클릭이 이미
1회 발생). Critical/High로 분류되지 않았으며, 기존 코드에 이미 문서화된
"DOM 전환과 response 도착의 인과관계 미보장" 같은 유사한 좁은 한계와
같은 성격이라 판단해 남은 위험으로만 기록한다.

## 남은 위험(문서화된 알려진 한계)
- `scroll_into_view_if_needed()`~`click()` 사이의 매우 좁은 타이밍 공백(위
  GPT-5.6-Sol 2차 검토 참고) - 이 구간에서 오류 candidate가 도착하면 그
  다음 클릭(1회)까지는 진행될 수 있으나, 그 이후 페이지의 harvest/drain
  단계에서는 여전히 감지되어 안전 중단된다(무한 진행 아님).
- 405가 발생한 근본 외부 원인(일시적 서버 오류/반복 요청에 대한 서버
  반응/특정 page transition 요청 실패/endpoint 내부 정책)은 이번 단계에서도
  단정하지 않았다 - production 코드에서 이 가능성들을 추측하거나 우회하는
  로직은 추가하지 않았다.
- page 1 자체가 candidate HTTP 오류/non-JSON이었을 경우 pagination 진입
  자체를 막는 로직은 이번 단계 범위에 포함하지 않았다(work order 15개
  테스트 사례에 해당 시나리오가 없어 스코프를 확장하지 않음) - 다음 단계에서
  필요성이 확인되면 별도로 검토해야 한다.

## 신규 테스트 요약
- browser_collector: 50 → 58 PASS(신규 8건: HTTP 405/403/500/429, 429+
  EmptyBody 이중 집계, Content-Type 누락/text-plain 정상 decode 3건; 기존
  3건 갱신은 PASS 수 변화 없음).
- pagination: 36 → 41 PASS(신규 5건: page2 HTTP 405/non-JSON 차단 각 1건,
  HTML 미노출 1건, PAGE-300-2B-4 정확 재현 1건, drain 경로 지연 오류 재현
  1건; 기존 1건 갱신은 PASS 수 변화 없음).
- adaptive_settle: 18 PASS(무수정, 회귀만 재확인).
- network_product_integration_no_live/pipeline/ui_network_start/
  ui_network_wiring: 무수정, 회귀만 재확인(각 11/12/15/19 PASS).
- network_list_scraper(7개 회귀 파일에는 미포함, 별도 확인): 42 PASS(무수정).

## 전체 관련 회귀 파일별 PASS/FAIL(최종)
| 파일 | PASS | FAIL |
|---|---|---|
| tests/test_pc_network_pagination.py | 41 | 0 |
| tests/test_pc_network_browser_collector.py | 58 | 0 |
| tests/test_pc_network_adaptive_settle.py | 18 | 0 |
| tests/test_network_product_integration_no_live.py | 11 | 0 |
| tests/test_pc_network_pipeline.py | 12 | 0 |
| tests/test_ui_network_start.py | 15 | 0 |
| tests/test_ui_network_wiring.py | 19 | 0 |
| tests/test_pc_network_list_scraper.py(별도) | 42 | 0 |

**7개 회귀 파일 합계: 174건, FAIL 0.**(작업 전 161건 대비 신규 13건).
list_scraper 별도 42건 포함 전체 216건, FAIL 0.

## 실제 live 미실행 확인
확인됨 - BrowserSession/Playwright 실행, 네이버 접속, 40·100·300건 live,
Excel 생성, 기존 marker 삭제 전부 하지 않았다. Fake 객체와 synthetic
response만 사용했다.

## Git 상태
`git status --short`/`git diff --name-status` 기준 변경 파일은
`src/pc/network_browser_collector.py`, `tests/test_pc_network_browser_
collector.py`, `tests/test_pc_network_pagination.py` + 이 `PROJECT_STATE.md`
append뿐이다(작업 허용 범위와 정확히 일치). `src/pc/network_list_scraper.py`,
`src/pc/network_pipeline.py`, `src/pc/browser_session.py`, `src/ui.py`,
`src/exporter.py`, `app.py`, `tests/test_pc_network_adaptive_settle.py`,
`tests/test_network_product_integration_no_live.py`,
`tests/test_pc_network_list_scraper.py` 전부 무수정. git add/commit/push/
reset/checkout/restore 전부 수행하지 않았다.

## PAGE-300-2B-4B 재검증 진입 가능 여부
gpt-5.6-sol 2차 재검토 PASS(Critical/High 결함 없음, 좁은 이론적 타이밍
공백만 남은 위험으로 기록) - 충분한 시간 간격을 둔 뒤 PAGE-300-2B-4B(동일
검색어, per_query_limit=300/target_count=300, 최대 page 5, 실제 live 정확히
1회, retry 0)로 진입해 405가 실제로 재현되는지, 재현된다면 이번 안전 중단
계약이 정확히 동작하는지, 재현되지 않는다면 300건 가능성을 재검증하는 것을
권장한다. page 6 전환 구현은 아직 진행하지 않는다. 과거 PAGE 기록은
수정하거나 삭제하지 않았다.

# 2026-07-20 PAGE-300-2B-4A-FIX scroll 이후 pre-click 최종 checkpoint 보강

## 이전 독립 검토의 잔여 타이밍 공백
PAGE-300-2B-4A GPT-5.6-Sol 최종 검토에서 지적된 잔여 공백: 두 번째 drain
검사 이후 `target_locator.scroll_into_view_if_needed()` → `target_locator.
click()` 사이에는 candidate 오류 재검사가 없었다 - scroll 실행 중 HTTP
405/non-JSON candidate가 도착해도 click() 전에 감지되지 않아 다음 페이지
클릭이 1회 실행될 수 있었다.

## scroll 중 오류 candidate 도착 재현(합성)
GPT-5.6-Sol이 읽기 전용 합성 실행으로 재현: page 2 확정 성공 →
scroll_into_view_if_needed() 실행 중 HTTP 405 candidate 도착 → 기존 코드는
재검사 없이 곧바로 click() → page3_click_calls=1(안전 중단 아님).

## 최종 pre-click drain/checkpoint
`target_locator.scroll_into_view_if_needed()`를 별도 try/except로 분리하고,
그 직후·`click()` 호출 "전"에 다음을 수행한다(`ctx.candidate_response_count
> candidate_count_before_click`일 때만 - 즉 scroll 중 실제로 새 candidate가
도착했을 때만 실행하며, 아무것도 도착하지 않으면 추가 대기 없이 곧바로
click으로 진행한다 - §8 "무조건적인 대기 추가 금지"):
1. 기존 `_apply_pending_drain` helper로 pending candidate를 harvest·parse.
2. 공유 helper `_classify_page_candidate_error(ctx, pre_click_drain_start_
   index, candidate_count_before_click)`로 오류 candidate 검사.
3. 오류가 있으면 `pagination_stop_reason`을 설정하고 click() 없이 즉시
   break.
4. 오류가 없고 흡수된 정상 candidate만으로 이미 `per_query_limit`에
   도달했다면 `per_query_limit_reached`로 종료하고 click() 생략.
5. 오류도 없고 목표도 미달일 때만 `class_before`를 다시 읽고 click() 진행.

## candidate index 범위 안전성
`pre_click_drain_start_index`(= scroll 시작 전 `candidate_count_before_
click`)부터 drain 이후 갱신된 `candidate_count_before_click`까지만 검사한다 -
이전 두 drain 구간과 겹치지 않으며(각 구간은 이전 drain이 끝난 지점부터
시작), 동일 candidate가 두 번 검사되거나 두 번 harvest되지 않는다(기존
`processed`/`generation` 계약과 object identity dedup 그대로 유지).

## 오류 candidate 차단 / 정상 late candidate 처리 / 목표 도달 시 click 생략
- scroll 중 HTTP 405/non-JSON candidate 도착 → click() 호출 전에
  `candidate_http_error`/`candidate_non_json_response`로 안전 중단,
  `pagination_error_message`는 짧고 비식별적(HTML 원문 미포함).
- scroll 중 정상 HTTP 200 JSON candidate 도착 → rows에 중복 없이 반영,
  raw/unique/duplicate 집계 갱신, 목표 미달이면 click은 정상 진행(1회).
- scroll 중 정상 candidate만으로 목표 도달 → click 생략,
  `per_query_limit_reached`로 종료.
- 부분 rows는 모든 경로에서 보존된다(오류 발생 이전까지 확정된 rows 유지).

## GPT-5.6-Sol(Codex MCP, read-only) 독립 검토 결과(3라운드)
1차 검토(이전 PAGE-300-2B-4A 세션): High 1건(drain 경로) + Medium 1건(429+
EmptyBody) - 모두 수정 완료(별도 기록).
2차 검토(이번 세션, pre-click checkpoint 구현 직후): 원래 지적된 scroll→
click 공백은 정상 해결 확인. 추가로 **Medium 2건 + Low 1건**을 새로 발견:
- **Medium 1**: scroll 중 정상 candidate를 drain으로 먼저 흡수한 경우,
  그 이후 `class_before`를 다시 읽는 동안(§ 나선형 하위 공백) 도착하는
  HTTP 405가 재검사되지 않아 click이 1회 실행될 수 있음(합성 재현 확인).
- **Medium 2**: scroll 중 candidate 자체가 HTTP 429이면
  `candidate_http_error_count`는 정상 집계되지만 `pagination_stop_reason`이
  기존 전역 우선순위(captcha>429>...)를 따르지 않고 "candidate_http_error"로
  보고됨(중단 자체는 정상, 라벨만 불일치).
- **Low**: scroll/drain으로 합류된 데이터가 `per_page_diagnostics`에
  반영되지 않아 페이지별 raw 합계와 전체 raw 집계가 어긋남(기존 drain
  경로에도 이미 있던 동작 - 이번 신규 회귀 아님).
Medium 2를 수정 반영(아래 절 참고) + 회귀 테스트 1건 추가.
3차 재검토(Medium 2 수정 확인): 429 우선순위 수정이 의도대로 동작하며
(`status_429_seen=False`인 기존 경로의 라벨은 전혀 바뀌지 않음),
captcha 우선순위와도 충돌하지 않음을 확인. 새로운 Critical/High/Medium
결함 없음. Medium 1/Low는 사용자가 이번 단계 범위를 "scroll→click 공백만
제거"로 명시적으로 한정했고(§9 "완전히 잠그는 것은 과도한 구조 변경 없이는
어렵다"), Medium 1은 이번에 닫은 공백 안에서 한 겹 더 들어간 나선형 하위
공백(class_before 재조회 자체도 이론상 무한히 재귀 가능)이라는 판단에
동의 - Critical/High로 재분류할 근거 없음, Low도 전체 rows/집계 손상이
아닌 페이지별 진단 문제라 범위 제외가 타당하다고 확인. 잔여 참고사항으로
"helper는 CAPTCHA를 새로 탐지하지 않으므로 drain 순간 CAPTCHA가 동시에
나타나면 다음 probe 시점까지는 보장 안 됨"과 "scroll 중 non-candidate 429만
도착하면 candidate_response_count가 늘지 않아 pre-click checkpoint가
실행되지 않을 수 있음(단, 이 경우도 기존 top-of-loop/post-click 429 검사가
별도로 여전히 작동)"을 추가로 언급했다 - 둘 다 이번 수정이 만든 회귀가
아닌 기존 타이밍 한계.

## 429 우선순위 수정(Medium 2)
`_classify_page_candidate_error`가 candidate 오류를 발견해 reason을
반환하려는 시점에 `ctx.status_429_seen`이 True이면, 그 reason 대신
"status_429_seen"을 반환하도록 수정했다(중단 여부는 그대로, 라벨만 기존
전역 우선순위에 맞춤). 이 함수는 main harvest 직후/drain 2곳/이번에 추가한
pre-click checkpoint까지 4곳 모두에서 공유되므로 이 한 곳의 수정으로
전부 일관되게 적용된다.

## 변경 파일
- `src/pc/network_browser_collector.py`(핵심 변경 - scroll_into_view_if_
  needed()와 click() 분리, pre-click drain/checkpoint 추가,
  `_classify_page_candidate_error`의 429 우선순위 라벨링)
- `tests/test_pc_network_pagination.py`(신규 케이스 7건 추가 - scroll 중
  HTTP 405/non-JSON 각각 차단, 정상 candidate 흡수 후 click 진행, 정상
  candidate로 목표 도달 시 click 생략, candidate 없음 시 기존 흐름 유지,
  동일 response 중복 전달 dedup, scroll 중 429 우선순위 라벨링; 기존
  `FakePaginationButtonLocator.scroll_into_view_if_needed()`에
  `responses_during_scroll` 스펙 키 지원 추가)
- `tests/test_pc_network_browser_collector.py`: 무수정(이번 라운드는
  pagination 흐름 전용이므로 신규 케이스 없음, 회귀만 재확인)
- `src/pc/network_list_scraper.py`, `src/pc/network_pipeline.py`,
  `src/pc/browser_session.py`: 무수정

## 남은 이론적 race(문서화, 이번 단계에서 닫지 않음)
- Medium 1: scroll 중 정상 candidate 흡수 후 `class_before` 재조회 중
  도착하는 오류 candidate(나선형 하위 공백 - 사용자 work order §9의
  "완전히 잠그기 어려운 잔여 이론적 race"에 해당한다고 판단해 범위 제외).
- Low: drain/scroll로 합류된 데이터가 `per_page_diagnostics`에 반영되지
  않아 페이지별 합계와 전체 합계가 어긋남(전체 rows/집계 자체는 정확 -
  기존 drain 경로에도 있던 동작, 이번 신규 회귀 아님).
- click() 호출 자체의 내부 실행 중 도착하는 response를 이전 페이지 오류로
  오인해 click을 취소하는 구조는 만들지 않았다(work order §9 명시 금지
  사항 - click 호출이 이미 시작된 이후의 응답은 다음 페이지의 정당한
  데이터로 처리되어야 한다).

## 신규 테스트 요약
- pagination: 47(2B-4A 세션 종료 시점) → 48 PASS(신규 7건: scroll 중 HTTP
  405/non-JSON 차단 각 1건, 정상 candidate 흡수 후 click 진행 1건, 정상
  candidate로 목표 도달 시 click 생략 1건, candidate 없음 시 기존 흐름
  유지 1건, 동일 response 중복 전달 dedup 1건, scroll 중 429 우선순위
  라벨링 1건).
- browser_collector: 58 PASS(무수정, 회귀만 재확인).
- adaptive_settle/product_integration_no_live/pipeline/ui_start/ui_wiring:
  무수정, 회귀만 재확인(각 18/11/12/15/19 PASS).
- network_list_scraper(별도): 42 PASS(무수정).

## 전체 관련 회귀 파일별 PASS/FAIL(최종)
| 파일 | PASS | FAIL |
|---|---|---|
| tests/test_pc_network_pagination.py | 48 | 0 |
| tests/test_pc_network_browser_collector.py | 58 | 0 |
| tests/test_pc_network_adaptive_settle.py | 18 | 0 |
| tests/test_network_product_integration_no_live.py | 11 | 0 |
| tests/test_pc_network_pipeline.py | 12 | 0 |
| tests/test_ui_network_start.py | 15 | 0 |
| tests/test_ui_network_wiring.py | 19 | 0 |
| tests/test_pc_network_list_scraper.py(별도) | 42 | 0 |

**7개 회귀 파일 합계: 181건, FAIL 0.**(작업 전 174건 대비 신규 7건).
list_scraper 별도 42건 포함 전체 223건, FAIL 0.

## 실제 live 미실행 확인
확인됨 - BrowserSession/Playwright 실행, 네이버 접속, 40·100·300건 live,
Excel 생성, 기존 marker 삭제 전부 하지 않았다. Fake 객체와 synthetic
response만 사용했다.

## Git 상태
`git status --short`/`git diff --name-status` 기준 변경 파일은
`src/pc/network_browser_collector.py`, `tests/test_pc_network_browser_
collector.py`, `tests/test_pc_network_pagination.py` + 이 `PROJECT_STATE.md`
append뿐이다(작업 허용 범위와 정확히 일치 - 이번 세션에서는 test_pc_network_
browser_collector.py 자체는 수정하지 않았지만 이전 PAGE-300-2B-4A 세션의
변경분이 여전히 uncommitted 상태로 남아 있다). `src/pc/network_list_
scraper.py`, `src/pc/network_pipeline.py`, `src/pc/browser_session.py`,
`src/ui.py`, `src/exporter.py`, `app.py`,
`tests/test_pc_network_adaptive_settle.py`,
`tests/test_network_product_integration_no_live.py`,
`tests/test_pc_network_list_scraper.py` 전부 무수정. git add/commit/push/
reset/checkout/restore 전부 수행하지 않았다.

## PAGE-300-2B-4A 최종 PASS/HOLD
**PASS** - GPT-5.6-Sol 3차 재검토에서 Critical/High/Medium(신규) 결함 없음을
확인했다. 남은 항목(Medium 1/Low)은 사용자가 명시한 범위 경계 안에서 의도적으로
문서화만 하고 남겨둔 것이며, 안전성(다음 페이지 클릭 차단·부분 rows 보존) 자체를
훼손하지 않는다.

## PAGE-300-2B-4B 진입 가능 여부
PAGE-300-2B-4A(스크롤~클릭 공백 포함 전체 안전 중단 계약)가 최종 PASS로
확인됐으므로, 이전 기록(PAGE-300-2B-4A)에서 권장한 대로 충분한 시간 간격을
둔 뒤 PAGE-300-2B-4B(동일 검색어, per_query_limit=300/target_count=300,
최대 page 5, 실제 live 정확히 1회, retry 0)로 진입하는 것을 권장한다. page 6
전환 구현은 아직 진행하지 않는다. 과거 PAGE 기록은 수정하거나 삭제하지
않았다.

# 2026-07-20 PAGE-300-2B-4B 현재 최대 5페이지 300건 one-shot 재검증

## 기준 커밋/실행 조건
기준 커밋 `5043e0d`(안정화: candidate HTTP 오류와 클릭 직전 안전 중단),
`git status --short` clean 확인 후 진입. query="서울특별시 강동구 카페"
1개, per_query_limit=target_count=300, settle_ms=5000, retry_count=0,
allowed_pages=[1,2,3,4,5], production `_MAX_PAGINATION_PAGES=5`(override
없음). 신규 harness `scratchpad/arch300_page300_probe/page300_2b4b_live_
300.py`는 기존 page300_2b4_live_300.py 패턴을 재사용하되 candidate_http_
error_count/candidate_non_json_count/candidate_http_status_counts/
candidate_processing_error_count 신규 진단 필드 기록과 work order의
FULL PASS/CONDITIONAL PASS/SAFE-STOP PASS·CAPABILITY HOLD/FAIL 4갈래
판정 로직만 추가했다. production/tests는 이 harness에서 수정하지 않았다.

## 마커
`PAGE300_2B4B_LIVE_STARTED.marker`를 `open(path, "x")`로 원자 생성,
`--check-config`는 마커를 만들지 않고 존재 여부만 확인(False). 기존 live
세션 재사용 없이 신규 BrowserSession 1개로 실행했다.

## 핵심 사전 회귀
tests/test_pc_network_pagination.py 48 PASS,
tests/test_pc_network_browser_collector.py 58 PASS,
tests/test_network_product_integration_no_live.py 11 PASS,
tests/test_pc_network_list_scraper.py 42 PASS. 합계 159건, FAIL 0.

## live 1회 결과
정확히 1회 실행(20260720_195127). page 1 candidate(HTTP 200, JSON object,
78475B)에서 raw=20/unique=20 정상 수집. page 2로 DOM 전환은 확정됐으나
page 2 candidate가 **HTTP 405 + text/html(583B)**로 응답 - candidate_
http_error_count=1, candidate_http_status_counts={'405':1}, non_json=0,
body_snapshot_error_count=0, json_decode_error_count=0(비교: 이전 PAGE-
300-2B-4 live에서 관측된 것과 동일한 405 패턴이 이번에도 재현됨). 이 오류를
감지한 즉시 **page 3 click은 시도되지 않고** 안전 중단됐다(pagination_
click_count=1, pagination_page_count=2, pagination_stop_reason=
candidate_http_error, parse_error_count=1). CAPTCHA/HTTP 429/timeout/
navigation_error 전부 없음. unmatched·ambiguous 0. snapshot 불변식
(success+error+pending==candidate_response_count, success bytes 합계
일치) 성립. page1의 rows(20건)는 그대로 보존됐다(place_id 중복 0).

## Excel/성능
exporter 정확히 1회 호출, 통합_결과 20행·11열, place URL 중복 0, 업체명
공란 0, 새로오픈여부 전부 공란, 내부 필드(place_id 등) 미노출. 전체 wall
11.12초(세션 준비 0.62s + 수집 10.26s + 종료 0.21s + export 0.02s).

## 판정
**SAFE-STOP PASS / CAPABILITY HOLD**. candidate HTTP 오류 발생 후 안전
중단 계약(추가 click 없음/retry 없음/우회 없음/부분 rows 보존/exporter
1회/HTML 원문 미노출/무한 대기 없음/production max pages 유지) 전부
충족을 확인했다 - 이는 안전 기능의 성공이며 단순 FAIL로 기록하지 않는다.
다만 page 2 자체가 서버 측 HTTP 405로 즉시 종료됐기 때문에, 현재 page
1~5 구현으로 실제 300건에 도달할 수 있는지는 이번 live로 확정되지
못했다(CAPABILITY HOLD). 동일 live를 이 harness에서 즉시 반복하지
않았다.

## 남은 위험/다음 단계
동일 검색어의 page 2 GraphQL 요청이 PAGE-300-2B-4와 PAGE-300-2B-4B 두
차례 live에서 모두 HTTP 405를 반환했다 - 우연한 1회성 장애인지 이 검색
조합/페이지에 지속되는 서버 측 특성인지는 이번 세션 범위 밖이며, 재시도나
우회 없이 그대로 기록한다. 300건 능력 검증은 여전히 HOLD 상태로 남고,
재검증 여부와 시점은 사용자 판단에 맡긴다. page 6 이상 "다음 페이지 번호
그룹" 전환 설계는 착수하지 않았다.

## 무수정/Git 확인
production(`src/*`)·`tests/*`·`app.py`·`README.md`·기존 harness·기존
marker/JSON/Excel 전부 무수정. 신규 파일은 `scratchpad/arch300_page300_
probe/page300_2b4b_live_300.py`와 그 결과물(`scratchpad/.../results/
page300_2b4b/`)뿐이며 scratchpad는 `.gitignore` 대상이라 tracked 변경은
`PROJECT_STATE.md` 뿐이다. `git status --short`/`git diff --name-status`
확인 결과 이 append 외 tracked 변경 없음. git add/commit/push/reset/
restore/checkout 전부 수행하지 않았다.
