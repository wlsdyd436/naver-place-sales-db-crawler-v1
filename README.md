# 네이버 플레이스 영업 DB 수집기 V1

지역 기반 소상공인 영업을 하는 광고대행사, POS/키오스크 영업자, 식자재 유통업체를 위한 **영업 DB 엑셀 수집 도구**입니다.

V1은 PC 네이버 지도 iframe 구조가 아니라 **모바일 웹 `m.map.naver.com` 검색 결과 리스트**를 기준으로 합니다. 상세 페이지에 들어가지 않고 리스트 화면에서 바로 확인 가능한 공개 사업장 정보만 수집하는 방향입니다.

---

## 1. V1 핵심 방향

- 모바일 웹 `m.map.naver.com` 기반
- iframe 없는 단일 DOM 구조 활용
- 검색 결과 리스트 화면 중심 수집
- 상세 페이지 클릭/진입 제외
- 무리한 우회보다 최소 수집과 안정성 우선
- Excel 저장을 통한 즉시 영업 활용

V1 기준 검색 흐름:

```text
https://m.map.naver.com/search.naver?query={지역+업종}
```

PC 네이버 지도 `map.naver.com/v5/search`, `searchIframe`, `entryIframe` 기반 접근은 V1 대상이 아닙니다.

---

## 2. V1 수집 필드

수집 대상:

- 업체명
- 업종
- 주소
- 대표전화
- 플레이스 URL
- 수집일

V1 제외 항목:

- 리뷰 수
- 영업시간
- 평점
- 상세 페이지 내부 정보
- 대표자명
- 개인 휴대폰 번호
- 개인 이메일

---

## 3. 결과물

수집 결과는 Excel 파일로 저장합니다.

실제 저장 경로:

```text
output/naver_place_sales_db.xlsx
```

V1 실제 출력 컬럼 (총 6개):

| 컬럼명 | 설명 |
|---|---|
| 업체명 | 네이버 플레이스 등록 업체명 |
| 업종 | 카테고리 (추출 불안정, 빈 값 허용) |
| 주소 | 사업장 주소 ("주소보기" 접두사 제거 처리됨) |
| 대표전화 | tel: href 기준 추출, 없으면 빈 값 |
| 플레이스 URL | `m.place.naver.com/place/{id}/home` 형식 |
| 수집일 | 수집 실행일 (YYYY-MM-DD) |

> **주의**: 영업상태, 연락담당자, 최근연락일, 메모 컬럼은 V1 범위 외입니다. Excel에서 직접 추가하여 사용하세요.

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
├── main.py
├── src/
│   ├── crawler.py
│   ├── parser.py
│   └── exporter.py
└── output/
```

---

## 5. 실행 방법 (V1 MVP 완료)

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

`main.py` 상단의 설정값을 수정한 후 실행합니다.

```python
# main.py 상단 설정값
KEYWORD = "대전 카페"   # 검색 키워드 (지역 + 업종)
LIMIT = 10              # 수집 목표 건수
OUTPUT_PATH = "output/naver_place_sales_db.xlsx"  # 저장 경로
```

```powershell
python main.py
```

실행 결과는 `output/naver_place_sales_db.xlsx` 파일로 저장됩니다.

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
