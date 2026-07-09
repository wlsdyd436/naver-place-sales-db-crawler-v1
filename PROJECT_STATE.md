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
- release_candidate 생성은 위 리스크 검토 완료 전까지 보류.