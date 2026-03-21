# OPM Blueprint — 현재 구조 + 문제점 + 방향

## 1. 현재 Tool 체계 (10개 + 향후 2개)

```
agm_steward(ticker)  ← 오케스트레이터 (한 번에 요약)
│
├─ agm_search(ticker)        소집공고 검색 + 정정 태깅
├─ agm_info(rcept_no)        회의 정보 + 정정 요약
├─ agm_agenda(rcept_no)      안건 제목 트리 (세부의안 포함)
├─ agm_corrections(rcept_no) 정정 전/후 비교
│
├─ agm_items(rcept_no)       안건 본문 블록 (범용 raw)
│   │
│   ├─ agm_financials        재무제표 정규화 (BS/IS/자본변동표/처분계산서)
│   ├─ agm_personnel         이사/감사 선임·해임 정규화
│   ├─ agm_aoi               정관변경 정규화 (변경전/변경후 비교)
│   ├─ (향후) agm_proposals  주주제안 정규화 (의안 제목 + 요지)
│   └─ (향후) agm_ocr        이미지 OCR
│
└─ agm_document(rcept_no)    원문 텍스트

안건 유형별 tool 매핑:
  재무제표 승인 → agm_financials (테이블 정규화)
  이사/감사 선임·해임 → agm_personnel (후보자 정보)
  정관변경 → agm_aoi (변경전/변경후 비교)
  주주제안 → agm_proposals (의안 요지) [향후]
  보수한도/자사주/기타 → agm_items (raw 블록)
```

## 2. 데이터 흐름

```
DART API (document.xml ZIP)
  │
  ▼
get_document(rcept_no)
  │ {text, html, images}
  │ (캐싱: _doc_cache, 30건 LRU)
  ▼
┌────────────────────────────────────────────────────┐
│  parser.py — 파싱 레이어                            │
│                                                     │
│  [공통 소스]                                        │
│  ├─ parse_agenda_items(text, html) → 안건 트리      │
│  ├─ parse_meeting_info(text, html) → 회의 정보      │
│  └─ parse_agenda_details(html)     → 안건 상세 블록 │
│                                                     │
│  [특화 파서] — 각각 HTML에서 독립적으로 파싱         │
│  ├─ parse_financial_statements(html) → 재무제표     │
│  ├─ parse_personnel(html)            → 인사 정보    │
│  ├─ parse_aoi(html)                  → 정관변경     │
│  └─ parse_correction_details(html)   → 정정 사항    │
│                                                     │
│  모든 파서: bs4(lxml) 우선 → text regex fallback     │
└────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────┐
│  shareholder.py — MCP tool 레이어                   │
│                                                     │
│  각 tool은 parser 결과를 포매팅                     │
│  format="md" → LLM용 마크다운                       │
│  format="json" → 프론트엔드용 v3 스키마             │
│                                                     │
│  format_krw() — 단위 변환 유틸 (백만원→조/억)       │
│  use_llm / max_fallback_length — fallback 옵션      │
└────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────┐
│  프론트엔드 (OpenProxy/frontend)                    │
│                                                     │
│  pipeline/*.json — MCP에서 생성한 v3 JSON           │
│  mockData.ts — JSON → Company 객체 변환             │
│  AgendaAnalysis.tsx — 렌더링                        │
│    ├─ FinancialTable (계층 트리, 변화율)             │
│    ├─ CharterChangesSection (접이식 카드)            │
│    ├─ CandidatesSection (후보자 정보)                │
│    └─ RetainedEarningsTable (처분계산서)             │
└────────────────────────────────────────────────────┘
```

## 3. 현재 문제점

### 문제 A: 특화 파서들이 서로 모름

```
parse_agenda_items()    → 세부의안 번호 (제2-1호~제2-8호) 알고 있음
parse_aoi()             → 변경 조항 테이블 파싱하지만, 세부의안 번호 모름
parse_personnel()       → 후보자 테이블 파싱하지만, agm_agenda 결과 모름
```

각 특화 파서가 **독립적으로 HTML을 파싱**해서 서로의 결과를 참조하지 않음.
→ LG화학처럼 테이블에 세부의안 번호가 없으면 매핑 불가.

### 문제 B: HTML→마크다운→재파싱 구조

```
HTML <table>
  → _table_to_markdown()   마크다운 문자열로 변환
  → parse_aoi()에서 _parse_md_table()로 다시 파싱
  → 변환 과정에서 행 구조/colspan 정보 손실
```

경력 테이블에서 기간/내용이 별도 `<tr>`인데 마크다운 변환 시 합쳐지는 이유.
재무제표는 HTML 직접 파싱(parse_financial_statements)이라 이 문제 없음.

### 문제 C: 체이닝이 실제로 안 됨

blueprint에 "체이닝"이라고 적었지만, 실제로는:
- agm_financials: HTML 직접 파싱 (agm_items 결과 안 씀)
- agm_personnel: HTML 직접 파싱 (agm_agenda 결과 안 씀)
- agm_aoi: HTML 직접 파싱 (agm_agenda 결과 안 씀)

각 tool이 독립적으로 HTML에서 추출. "체이닝"은 agm_steward에서 여러 파서를
순차 호출하는 것뿐.

## 4. 해결 방향

### 방향 1: 파서 간 데이터 전달 (추천)

```python
# 현재
aoi = parse_aoi(html)                    # 세부의안 번호 모름

# 개선
agenda = parse_agenda_items(text, html)   # 세부의안 번호 확보
aoi = parse_aoi(html, sub_agendas=agenda) # 세부의안 목록 참조하여 매핑
personnel = parse_personnel(html, agenda=agenda)  # 안건 번호 참조
```

- parse_aoi에 세부의안 목록을 넘겨서, 제목 키워드로 charterChanges에 번호 부여
- parse_personnel에 안건 목록을 넘겨서, 어떤 안건의 후보자인지 명확히

### 방향 2: HTML 직접 파싱 확대 (근본 해결)

```python
# 현재: parse_agenda_details → 마크다운 블록 → 특화 파서에서 재파싱
# 개선: 특화 파서가 HTML <table>을 직접 파싱

# parse_personnel의 경력 테이블:
#   현재: 마크다운 테이블 → _parse_md_table → 기간/내용 합쳐짐
#   개선: HTML <table> → <tr> 행 단위 직접 추출 → 기간/내용 분리
```

parse_financial_statements는 이미 이 방식. parse_personnel/parse_aoi도 동일하게.

### 방향 3: 통합 파서 (장기)

```python
# 한 번의 HTML 순회로 모든 정보 추출
result = parse_agm_document(html)
# result.agenda_tree, result.financials, result.personnel, result.aoi, ...
```

현재는 같은 HTML을 여러 파서가 반복 파싱. 통합하면 효율적이지만 복잡도 증가.

## 5. 우선순위

1. **방향 1 적용** — parse_aoi에 세부의안 전달 (즉시 해결 가능)
2. **방향 2 적용** — parse_personnel 경력 HTML 직접 파싱 (경력 빈 content 해결)
3. 방향 3은 향후 리팩토링 시
