# Homework

## 완료

### Step 4: FastMCP 서버 구축 ✓
- [x] server.py 작성 (FastMCP 진입점)
- [x] tools/shareholder.py 작성 — 주주총회 소집공고 검색 + 본문 조회 MCP tool 4개
- [x] get_document()에서 이미지 파일명 본문에서 제거 + 별도 목록으로 분리 반환

### 안건 파서 (parser.py) ✓
- [x] 정규식 기반 안건 트리 파싱 (표준 + 괄호형 패턴)
- [x] 섹션 기반 파싱 — 정정공고 범용 대응
- [x] 250개 기업 대규모 테스트 — 93% 처리율 (bs4+regex)
- [x] validate_agenda_result() 품질 검사
- [x] 하이브리드 LLM fallback (gpt-5.4-mini, use_llm 옵션)
- [x] hard fail / soft fail 구분
- [x] BeautifulSoup + lxml 기반 섹션 추출 (text regex fallback 유지)
- [x] lookahead 경계 강화 (하위안건/테이블헤더/정관변경)

### 안건 상세 파싱 (get_agenda_detail) ✓
- [x] BeautifulSoup으로 HTML 직접 파싱 — 테이블은 마크다운 테이블, 텍스트는 텍스트
- [x] KT&G 8개 안건 검증 통과

## 해야 할 일

### OCR 파이프라인
- [ ] 공시 본문 내 이미지(BSM, 확인서 등) OCR 처리 기능 추가
- [ ] img2table + PaddleOCR 조합 검토
- [ ] get_document()에서 이미지 파일명 분리 반환 구조 만들기

### 기업 검색 개선
- [ ] 영문 브랜드명(KT&G 등) → corp_code 매핑 지원 (별칭 또는 영문명 API)

### 연동 테스트
- [ ] Claude Desktop 또는 Claude Code에서 실제 연동 테스트

### 파서 개선 (LLM fallback으로 커버 중)
- [x] `제` 없는 비표준 하위안건 번호 패턴 대응 (lookahead 경계로 해결)
- [x] 후보자 테이블 제목 분리 (테이블 헤더 경계로 해결)
- [ ] Claude API (Anthropic) fallback 추가 (현재 OpenAI만 테스트 완료)
- [ ] `get_agenda_detail` 다기업 검증 (현재 KT&G만 상세 확인)

### feat/agenda-tree-bs4 브랜치 → main 머지
- [ ] 최종 리뷰 후 main에 머지
