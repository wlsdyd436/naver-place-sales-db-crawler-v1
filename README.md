# 네이버 플레이스 영업 DB 수집기 V1.2

지역 기반 소상공인 영업을 하는 광고대행사, POS/키오스크 영업자, 식자재 유통업체를 위한 **영업 DB 엑셀 수집 도구**입니다.

현재 V1.2는 GUI 실행 진입점인 `app.py`를 기준으로 동작합니다. Basic Mode는 모바일 웹 기반 빠른 수집, Premium Mode는 모바일 기본 데이터와 PC 리스트 기반 리뷰수/신규오픈 정보를 안전하게 병합하는 방식입니다.

---

## 1. V1.2 핵심 방향

- GUI 기반 실행 (`app.py`)
- Basic Mode: 모바일 웹 `m.map.naver.com` 기반 빠른 영업 DB 수집
- Premium Mode: Basic 결과에 PC 리스트 기반 리뷰수/신규오픈 여부 보강
- 검색 결과 리스트 화면 중심 수집
- 상세 페이지 클릭/진입 제외
- 무리한 우회보다 최소 수집과 안정성 우선
- Excel 저장을 통한 즉시 영업 활용

V1 기준 검색 흐름:

```text
https://m.map.naver.com/search.naver?query={지역+업종}
```

Premium Mode는 PC 네이버 지도 `searchIframe`의 리스트 화면만 사용하며, 상세 페이지 `entryIframe`에는 진입하지 않습니다.

---

## 2. 수집 필드

Basic Mode 수집 대상:

- 업체명
- 업종
- 주소
- 대표전화
- 플레이스 URL
- 수집일

Premium Mode 통합 결과:

- 업체명
- 업종
- 새로오픈여부
- 리뷰수
- 주소
- 대표전화
- 플레이스 URL
- 수집일

제외 항목:

- 영업시간
- 평점
- 상세 페이지 내부 정보
- 대표자명
- 개인 휴대폰 번호
- 개인 이메일

---

## 3. 결과물

수집 결과는 Excel 파일로 저장합니다.

실제 저장 경로 예시:

```text
output/naver_place_basic_db_YYYYMMDD_HHMMSS.xlsx
output/naver_place_premium_db_YYYYMMDD_HHMMSS.xlsx
```

Basic 출력 컬럼:

| 컬럼명 | 설명 |
|---|---|
| 업체명 | 네이버 플레이스 등록 업체명 |
| 업종 | 카테고리 (추출 불안정, 빈 값 허용) |
| 주소 | 사업장 주소 ("주소보기" 접두사 제거 처리됨) |
| 대표전화 | tel: href 기준 추출, 없으면 빈 값 |
| 플레이스 URL | `m.place.naver.com/place/{id}/home` 형식 |
| 수집일 | 수집 실행일 (YYYY-MM-DD) |

Premium 출력은 `통합_결과`, `원본_모바일`, `원본_PC` 3개 시트로 저장됩니다.

---

## 4. 프로젝트 구조

```text
naver-place-sales-db-crawler-v1/
├── README.md
├── LEGAL_NOTICE.md
├── PROJECT_STATE.md
├── implementation_plan.md
├── requirements.txt
├── .env.example
├── app.py
├── build.bat
├── docs/
│   ├── 경쟁 상품 조사.txt
│   ├── 고객 문제 정의.txt
│   └── 판매 가능성 검증 (ROI 분석).txt
├── src/
│   ├── crawler.py
│   ├── parser.py
│   ├── exporter.py
│   ├── merger.py
│   ├── pc_crawler.py
│   └── ui.py
├── tests/
│   └── test_excel_validation.py
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

- Basic Mode: 빠른 전화영업 DB 수집
- Premium Mode: 리뷰수·신규오픈 여부 보강

### 실제 테스트 완료 키워드

- `대전 카페` — 10건 수집 확인
- `대전 미용실` — 10건 수집 확인
- `대전 치킨` — 10건 수집 확인

### 주의사항

- 업종 추출은 불안정할 수 있으며, 빈 값으로 출력될 수 있습니다 (오탐 방지 정책).
- 수집 건수는 검색 결과 DOM 구조에 따라 `limit` 미만이 될 수 있습니다.
- 대량/반복 수집은 네이버 이용약관 위반 가능성이 있으니 자제합니다.
- 수집된 데이터의 활용 방법은 반드시 `LEGAL_NOTICE.md`를 확인하세요.

---

## 6. 법적 주의

본 프로젝트는 공개 사업장 대표 정보를 영업 조사 및 방문/전화 영업 준비용으로 정리하는 도구입니다.

광고성 문자, 이메일, 카카오톡 등 전자적 광고 발송은 관련 법령에 따른 수신 동의와 수신거부 절차를 준수해야 합니다. 자세한 내용은 `LEGAL_NOTICE.md`를 확인해야 합니다.
