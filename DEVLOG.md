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

**남은 이슈 → 하이브리드 LLM fallback 구조로 해결 예정:**
- 정정공고 포맷 변형 (마커 없는 케이스)
- 제목 잘림 엣지 케이스
- `(제N-M-K호)` 괄호 패턴 하위안건 누락
- fallback: 파서 실패/의심 시 zone 텍스트를 LLM API에 넘겨 구조화
