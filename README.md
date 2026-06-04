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

예상 파일명:

```text
output/{지역}_{업종}_영업DB_{수집일}.xlsx
```

예상 컬럼:

- 업체명
- 업종
- 주소
- 대표전화
- 플레이스 URL
- 수집일
- 영업상태
- 연락담당자
- 최근연락일
- 메모

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

## 5. 실행 방향

아직 V1 구현 전 문서 정리 단계입니다.

구현 후 예상 실행 예시는 아래와 같습니다.

```powershell
python main.py --region "강남구" --keyword "음식점"
```

실행 결과는 `output/` 폴더의 Excel 파일로 확인합니다.

---

## 6. 법적 주의

본 프로젝트는 공개 사업장 대표 정보를 영업 조사 및 방문/전화 영업 준비용으로 정리하는 도구입니다.

광고성 문자, 이메일, 카카오톡 등 전자적 광고 발송은 관련 법령에 따른 수신 동의와 수신거부 절차를 준수해야 합니다. 자세한 내용은 `LEGAL_NOTICE.md`를 확인해야 합니다.
