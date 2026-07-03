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
- test_pc_list_scraper.py PASS 21
- test_pc_browser_session.py PASS 15
- test_pc_pipeline.py PASS 8