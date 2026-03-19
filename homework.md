# Homework

## 해야 할 일

### OCR 파이프라인
- [ ] 공시 본문 내 이미지(BSM, 확인서 등) OCR 처리 기능 추가
- [ ] img2table + PaddleOCR 조합 검토
- [ ] get_document()에서 이미지 파일명 분리 반환 구조 만들기

### 기업 검색 개선
- [ ] 영문 브랜드명(KT&G 등) → corp_code 매핑 지원 (별칭 또는 영문명 API)

### Step 4: FastMCP 서버 구축
- [ ] server.py 작성 (FastMCP 진입점)
- [ ] tools/shareholder.py 작성 — 주주총회 소집공고 검색 + 본문 조회 MCP tool
- [ ] get_document()에서 이미지 파일명 본문에서 제거 + 별도 목록으로 분리 반환
- [ ] Claude Desktop 또는 Claude Code에서 실제 연동 테스트
