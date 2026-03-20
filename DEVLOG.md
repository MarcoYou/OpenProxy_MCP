# Dev Log

## 2026-03-19

### 프로젝트 초기 설정
- GitHub 레포 생성 (MarcoYou/OpenProxy_MCP, public)
- 프로젝트 구조 설계: `open_proxy_mcp/` 패키지 (server.py, tools/, dart/)
- 기술 스택 결정: Python + FastMCP + httpx + OpenDART API
- `.env`에 OpenDART API 키 설정, `.gitignore` 구성

### 참고 프로젝트 리서치
- **dart-mcp** — DART 재무제표 MCP 서버 분석. FastMCP 패턴, OpenDART 호출 구조 참고. 단일파일/캐싱없음 개선 필요.
- **Kensho (S&P Global)** — LLM 최적화 API 설계, dual transport, 도메인별 tool 분리 참고.
- **FactSet** — 엔터프라이즈 MCP 거버넌스 패턴 참고.
- 공통 교훈 정리: LLM 친화적 구조화, 도메인별 tool 분리, 캐싱 필수

### Step 1: OpenDART API 동작 확인 ✓
- API 키 정상 작동 확인
- 주주총회소집공고 위치 발견: `pblntf_ty=E` (기타공시)
- `report_nm`에 "소집" 포함 여부로 클라이언트 필터

### Step 2: DartClient 구현 ✓
- `dart/client.py` — API 호출 래퍼 (인증, 에러체크, JSON 파싱)
- `search_filings()` 메서드로 공시 검색 한 줄 호출 가능

### Step 3: ticker/회사명 조회 + 본문 가져오기 ✓
- `corpCode.xml` ZIP 다운로드 → 파싱 → 캐싱 (종목코드/회사명 → corp_code 변환)
- `lookup_corp_code()` — 종목코드, corp_code, 회사명 정확/부분 매치
- `search_filings_by_ticker()` — ticker로 공시 검색 편의 메서드
- `get_document()` — document.xml ZIP → XML → 텍스트 추출
- KT&G(033780) 주총 소집공고 본문 49,451자 정상 추출 확인

### 문서화
- README.md, CLAUDE.md, DEVLOG.md, references.md 작성
- homework.md 작성 (미완료 작업 추적)
- 개발 방식 확정: Build → Check → Pass 점진적 사이클

### 다음 단계 → homework.md 참조

## 2026-03-20

### 안건 파서 디버깅 루프 (계속)

**테스트 기업 8개**: 삼성전자, 세방전지, 한화, GS, 솔루엠, 현대리바트, 인포뱅크, 대양금속

**수정 사항:**
1. **정정공고 중복 파싱 해결** — `_strip_correction_preamble()` 추가. `정 정 신 고` 감지 시 마지막 `주N) 정정 후` 이후 본문만 파싱. 세방전지 14건→6건 정상화.
2. **zone 끝점 5000자 강제 컷 제거** — 끝점 패턴에 의존하도록 변경
3. **끝점 패턴 강화** — `\n` 의존 제거, 특수문자(■□○) 시작 섹션 추가, 줄바꿈 없이 이어지는 케이스 대응
4. **zone 내 줄바꿈 제거** — 제목이 여러 줄에 걸치는 케이스 해결. 삼성전자 제2호 제목 정상 추출.
5. **`_clean_title` 보강** — ①②③ 원문자 제거(한화), 끝에 매달린 `(` 제거(솔루엠 제4·5호)

**현재 상태:**
- 삼성전자 ✅, 한화 ✅, GS ✅, 현대리바트 ✅, 인포뱅크 ✅, 솔루엠 ⚠️(하위안건 누락), 세방전지 ⚠️(제2-11호 제목잘림), 대양금속 ❌(정정 포맷 변형으로 중복)

**추가 수정:**
6. **섹션 기반 파싱으로 전환** — `_strip_correction_preamble` 제거, `_extract_notice_section` 추가. '주주총회 소집공고' 본문 헤더를 `(제N기/정기/임시)` 패턴으로 식별. 정정공고 범용 대응. 대양금속, 한국화장품제조 정정 중복 해결.
7. **괄호형 안건 패턴 추가** — `(제N-M-K호)` 콜론 없이 바로 제목. 솔루엠 하위안건 파싱 해결.

**대규모 테스트 결과 (155개 기업):**

| 구분 | 건수 | 비율 |
|------|------|------|
| ✅ validate=True (정규식 파싱 성공) | 140 | 90% |
| ⚠️ validate=False (LLM fallback 대상) | 9 | 6% |
| ❌ 0건 (section 추출 실패) | 3 | 2% |
| 검색 불가 (소집공고 미제출) | 3 | 2% |

**정규식으로 처리 불가한 패턴 (LLM fallback 대상):**
- `제` 없는 비표준 하위안건 번호 (`2-1호`, `3-1호` 등) — 제목에 합침됨
- 후보자 테이블이 제목에 딸려오는 케이스
- section 추출 실패 (문서 구조가 비표준)
- 번호 중복 / 번호 누락
- 정정공고 section 오배치

### 하이브리드 LLM Fallback 구현

**구조:**
```
get_meeting_agenda(rcept_no)
        │
        ▼
  get_document (캐싱)
        │ text
        ▼
  parse_agenda_items(text) ── 정규식 파싱
        │ agenda[]
        ▼
  validate_agenda_result()
  (0건/중복/제목200자↑)
        │
   ✅ True ───────────────────────────┐
        │ ❌ False                    │
        ▼                             │
  extract_notice_section()            │
  extract_agenda_zone()               │
        │                             │
   zone 없음 ──┐    zone 있음         │
        │       │         │           │
        ▼       │         ▼           │
  [HARD FAIL]   │   [SOFT FAIL]      │
  "안건 영역    │   LLM fallback     │
   찾을 수 없음"│   (gpt-5.4-mini)   │
                │         │           │
                │    validate again   │
                │         │           │
                │    ✅ ─────────┐    │
                │         │      │    │
                │    ❌   │      │    │
                │         ▼      ▼    ▼
                │   [HARD FAIL]  format_agenda_tree()
                │   "정규식+LLM       │
                │    모두 실패"       ▼
                │              마크다운 응답
                │
                ▼
           로그 기록
```

**구현 파일:**
- `open_proxy_mcp/llm/client.py` — LLM 호출 (Claude Sonnet 기본, OpenAI 대체)
- `open_proxy_mcp/tools/parser.py` — `validate_agenda_result()` 추가
- `open_proxy_mcp/tools/shareholder.py` — `get_meeting_agenda`에 fallback 로직

**트리거 조건 (validate_agenda_result):**
- 빈 리스트 (0건)
- 같은 number 중복 (정정공고 잔류)
- 제목 200자 초과 (zone 텍스트 딸려옴)

**토큰 사용:** 정규식 성공 시 0, fallback 시 zone 크기만큼 (500~1500자)

**DLQ:** 로그만 남김 (별도 저장소 없음)

**use_llm 옵션:** `get_meeting_agenda(rcept_no, use_llm=False)` 기본. True 시 fallback 활성화.

### 오늘의 성과
- 안건 파서를 섹션 기반으로 전면 리팩토링 — 정정공고 포맷 변형에 범용 대응
- 155개 기업 대규모 테스트 완료, 정규식만으로 90% 처리율 달성
- 하이브리드 LLM fallback 구현 (gpt-5.4-mini) — hard/soft fail 구분, use_llm 옵션
- zone 끝점 패턴, _clean_title 잔류 문자 제거 등 반복 개선으로 처리율 점진적 상승

### 오늘의 실패 / 한계
- `제` 없는 비표준 하위안건 번호(`2-1호`, `3-1호`)는 정규식으로 안전하게 잡을 수 없음 — 오매치 위험
- 후보자 테이블이 제목에 딸려오는 케이스도 정규식 경계로 분리 불가
- section 추출 실패 3건(한국항공우주, 두산밥캣, HD현대마린엔진) — 문서 구조가 비표준
- LLM fallback 실제 e2e 테스트는 OpenAI만 완료, Anthropic API는 미테스트
- 터미널 강제 종료로 이전 대화 메모리 유실 — 작업 맥락 복구에 시간 소요

## 2026-03-21

### get_agenda_detail — 안건 상세 파싱 tool 신설

**배경:** 기존 `get_meeting_agenda`는 안건 **제목 트리**만 추출. 안건별 상세 내용(재무제표, 정관변경 비교표, 이사 후보 정보 등)은 `III. 경영참고사항 > 2. 목적사항별 기재사항`에 있으나 파싱하지 않고 있었음.

**핵심 발견:** `client.py`의 `get_document()`가 HTML→plain text 변환 시 `<table>` 구조를 모두 제거. BeautifulSoup으로 HTML을 직접 파싱하면 테이블 구조를 자연스럽게 보존 가능.

**구현:**
- `client.py` — `get_document()` 반환에 `html` 필드 추가 (raw HTML 보존)
- `parser.py` — `parse_agenda_details(html)` 추가 (BeautifulSoup 기반)
  - DART XML 구조: `<section-2>` > `<library>` > `<section-3>` > `<title>□카테고리` > `<p>■제N호` > `<table>`
  - `<table>` → 마크다운 테이블 변환, 단일 셀 테이블은 텍스트로 반환
  - `<p>` 내 여러 항목 합쳐진 경우 `_split_p_lines()`로 분리
  - 서브섹션(`가.`~`하.`) 감지, `※` 조건부 노트 분리
- `shareholder.py` — `get_agenda_detail(rcept_no, agenda_no, format)` tool 등록
  - `agenda_no` 미지정 시 전체, `"2"` 지정 시 제2호 + 하위 전체 반환
  - `format="md"` 마크다운 / `format="json"` 구조화 JSON

**검증:** KT&G(20260225005779) 8개 안건 전체 파싱 성공. 재무제표 테이블, 정관변경 비교표, 이사 후보 정보 테이블 모두 정상 변환.

### 안건 트리 파서 개선 — bs4 + regex 강화

**1단계: bs4 기반 섹션 추출 (`_extract_agenda_zone_html`)**
- `<section-1>/<title>주주총회 소집공고` 태그로 섹션 경계를 정확히 잡음
- 기존 text regex는 "경영참고사항 참조" 등 인라인 텍스트에 end_pattern 오발동 → zone 잘림
- HTML은 `<section-1>` 범위가 정확하여 이 문제 해결
- 효과: +7건 (하나기술, 레이저옵텍, 삼보모터스, 벡트, 하이퍼코퍼레이션, 플럼라인생명과학, 폴라리스오피스)

**2단계: regex 패턴 개선**
- AGENDA_RE에 `안건` 키워드 추가 (기존 `의안`만): +1건 (에스바이오메딕스)
- AGENDA_NO_COLON_RE 신설 — 콜론 없이 `제N호 의안 제목` 형태: +1건 (글로벌에스엠)
- zone 시작 패턴에 `부의사항` 추가: +1건 (우리산업홀딩스)

**3단계: lookahead 경계 강화 (`_AGENDA_BOUNDARY`)**
- `N-M호` (제 없는 하위안건): +4건 (일진디스플, 시큐브, 대진첨단소재, 삼익악기)
- 후보자 테이블 헤더 (`성명 생년월일`): +2건 (보해양조, 에코마케팅)
- 정관변경 비교 테이블 (`변경전 내용`): +1건 (삼양케이씨아이)

**처리율 변화 (250건 기준):**

| 단계 | 성공 | 비율 |
|------|------|------|
| 이전 (text regex only) | 219 | 87% |
| + bs4 섹션 추출 | 226 | 90% |
| + regex 패턴 개선 | 229 | 91% |
| + lookahead 경계 강화 | **234** | **93%** |

**regression 0건** — 250건 전수 테스트에서 기존 성공 케이스 영향 없음.

### 파서 엔진 벤치마크

**BeautifulSoup 파서 비교 (250건 전수 테스트):**

| 파서 | zone 성공 | 속도 | 결과 차이 |
|------|-----------|------|----------|
| html.parser | 246/250 | 89ms/doc | baseline |
| **lxml** | **246/250** | **62ms/doc (30%↑)** | **0건** |
| html5lib | 246/250 | 159ms/doc (79%↓) | 0건 |

→ lxml을 기본 파서로 채택 (없으면 html.parser fallback)

**regex 라이브러리 평가:**
- `re` 대비 60% 느림
- `\p{Hangul}`은 DART에서 불필요 (자모 443자 추가 매치하나 사용 안 함)
- `[가-하]` 범위는 오히려 `갸`, `거` 등 오매치 — 명시적 나열이 안전
- → 도입하지 않음

### 남은 실패 케이스 분류 (13개 기업, LLM fallback 대상)

| 원인 | 건수 | 기업 |
|------|------|------|
| 비표준 구조 / 기타 | 5 | 유니온바이오메트릭스, 메타바이오메드, 차바이오텍, 동일산업, 와이바이오로직스 |
| zone 추출 실패 | 3 | 인천유나이티드, 아스플로, 태양금속공업(이미지 기반) |
| 번호 중복 | 2 | 솔루엠, 신라교역 |
| 기타 | 3 | 남성, 프로이천, 삼보산업 |

### 오늘의 성과
- `get_agenda_detail` tool 신설 — 안건별 상세 내용을 테이블/텍스트 구분하여 파싱
- BeautifulSoup + lxml 도입으로 HTML 구조 직접 활용
- 안건 트리 파서 처리율 87% → 93% 개선 (250건 기준, +15건, regression 0)
- 파서 엔진 / regex 라이브러리 벤치마크 — 실측 근거로 기술 선택

### 오늘의 실패 / 한계
- 13개 기업은 여전히 정규식으로 해결 불가 — LLM fallback 필요
- `get_agenda_detail`의 다기업 검증 미완 (KT&G만 상세 확인)
- lxml-xml 파서는 DART 문서의 대소문자 혼용 때문에 사용 불가
