# References

## 1. dart-mcp
- **URL:** https://github.com/2geonhyup/dart-mcp
- **목적:** DART 정기공시(사업보고서, 반/분기보고서)에서 재무제표를 XBRL 파싱하여 MCP tool로 제공
- **스택:** Python, FastMCP (`mcp.server.fastmcp`), httpx
- **Tools:** 재무 요약, 상세 재무제표, 사업정보, JSON 폴백, 현재날짜
- **참고할 점:**
  - `@mcp.tool()` 데코레이터 패턴
  - OpenDART API 호출 구조 (corpCode.xml, list.json, document.xml, fnlttXbrl.xml)
  - XBRL 파싱 로직, 인코딩 폴백 (UTF-8 → EUC-KR → CP949)
  - 공시 제출 지연 감안 날짜 보정 (+95일)
  - Context 객체 활용한 progress reporting
- **개선 대상:**
  - 1,525줄 단일 파일 모놀리스
  - corpCode.xml (20MB) 매번 새로 다운로드 — 캐싱 없음
  - 주주총회 소집공고 미지원 (`pblntf_ty=A`만)
  - 테스트/rate limiting 없음
  - 입력값 검증 없음

## 2. Kensho LLM-Ready API (S&P Global)
- **URL:** https://docs.kensho.com/llmreadyapi/mcp
- **목적:** S&P Global 금융 데이터를 LLM 최적화된 MCP tool로 제공
- **데이터:** 재무제표, 기업관계, 어닝콜 트랜스크립트, 기업정보, M&A, 시세/시장 데이터
- **스택:** Python (`pip install kensho-kfinance`), Poetry
- **참고할 점:**
  - LLM 최적화 API 설계 — raw API를 그대로 노출하지 않고 function-calling에 맞게 재구조화
  - Dual transport: stdio (로컬/Claude Desktop) + SSE (원격/호스팅)
  - 인증 유연성: refresh token(개발), key pair OAuth(프로덕션), 브라우저 OAuth(폴백)
  - Privacy boundary: 자연어는 백엔드에 전달 안 됨, deterministic API 호출만 전달
  - 도메인별 데이터셋 구조 (fundamentals, transcripts, M&A 등)
- **참고:** `python -m kfinance.mcp --stdio`로 실행, Claude Desktop config 예시 제공
- **접근:** 무료 trial 있음, 엔터프라이즈는 별도 계약

## 3. FactSet AI-Ready Data MCP
- **URL:** https://developer.factset.com/mcp/factset-ai-ready-data-mcp
- **목적:** FactSet 금융 데이터를 "sans intermediary" (중간 레이어 없이) MCP로 직접 제공
- **데이터:** Fundamentals, Consensus Estimates, Ownership, M&A, Pricing, People, Events, Supply Chain, Geographic Revenue
- **참고할 점:**
  - 엔터프라이즈 MCP 거버넌스 패턴 3가지:
    - Central Tool Registry — 모든 tool/resource의 단일 진실 원천
    - Proxied Access Pattern — tool 이름 기반 라우팅 + 인증
    - Controller/Worker Pattern — 계층적 배포, capability 집약
  - "Production-grade MCP" 포지셔닝 — 엔터프라이즈 안정성과 governed access 강조
  - 데이터셋별 tool 분리 (monolithic search 지양)
  - 800+ 기관 사용자 베타 거침 (2025.12)
- **접근:** 엔터프라이즈 구독, Databricks Marketplace에서도 제공

## 공통 설계 교훈
1. **LLM 최적화 tool 설계** — raw API를 그대로 MCP tool로 만들지 않고, LLM이 function-calling하기 쉽게 구조 단순화
2. **도메인별 tool 분리** — 하나의 generic search가 아닌, 도메인 특화 tool (e.g., `get_financials`, `search_filings`, `get_disclosure_text`)
3. **캐싱 필수** — 무거운 리소스(기업 코드, 공시 목록 등)는 반드시 캐싱
4. **Dual transport** — stdio (로컬 개발) + SSE/Streamable HTTP (원격 배포) 지원
5. **인증 계층화** — 개발/테스트용 간단 인증 + 프로덕션용 OAuth
