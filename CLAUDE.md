# OPM (OpenProxy MCP)

## 프로젝트 개요
DART(전자공시시스템) 데이터를 MCP 프로토콜로 제공하는 Python 서버. 약칭 **OPM**.
주주총회 소집공고를 시작으로, 재무정보 등 DART 전체 공시 데이터로 확장 예정.

## 기술 스택
- Python
- FastMCP (`mcp.server.fastmcp`) — 데코레이터 기반 MCP 서버 프레임워크
- httpx — async HTTP 클라이언트
- python-dotenv — 환경변수 관리
- BeautifulSoup4 + lxml — DART 문서 HTML 파싱 (테이블 구조 보존, lxml 30% 빠름)
- OpenDART API (https://opendart.fss.or.kr/)

## 프로젝트 구조
```
open_proxy_mcp/       # 메인 패키지
  __init__.py
  server.py           # FastMCP 서버 진입점
  tools/              # MCP tool 정의 (도메인별 분리)
    shareholder.py    # 주주총회 소집공고 관련 (5 tools + 캐시 + 포매터)
    parser.py         # 소집공고 파싱 — 안건 트리 + 안건 상세 + 비안건 (bs4+regex)
  dart/               # OpenDART API 클라이언트
    client.py         # API 호출 래퍼 (인증, 에러핸들링, 캐싱, HTML 보존)
  llm/                # LLM fallback 클라이언트
    client.py         # 파서 실패 시 LLM으로 안건 추출
```

## 설계 원칙
- 각 DART API 도메인(공시, 재무, 지분 등)은 `dart/` 하위 모듈로 분리
- MCP tool은 `tools/` 하위에 도메인별로 분리
- API 키는 `.env`에서 관리, 절대 커밋하지 않음
- corpCode.xml 등 무거운 데이터는 캐싱 적용
- 입력값(날짜 형식 등) 검증 처리
- 단일 파일 모놀리스 지양, 모듈 분리 유지

## CLAUDE.md 작성 원칙
**이 파일은 가볍게 유지할 것.** 상세 내용을 여기에 직접 쓰지 않고, 특정 케이스에 어떤 문서를 참고해야 하는지 포인터로 안내하는 방식으로 작성한다.
- 파서 상세/벤치마크/실패 케이스 → `DEVLOG.md` 참조
- 참고 프로젝트 상세 → `references.md` 참조
- 미완료 작업 → `homework.md` 참조
- 프로젝트 히스토리 → `git log` 참조

## 개발 방식
- **점진적 빌드**: 한 번에 하나씩 만들고 확인하고 넘어감
- **Build → Check → Pass** 사이클:
  1. 작은 단위 하나 구현 (build 1 case)
  2. 실행/테스트로 동작 확인 (check)
  3. 문제 있으면 수정, 통과하면 다음 단계로 (pass)
- 유저가 각 단계를 이해하고 넘어가는 것이 우선 — 속도보다 이해
- 새로운 개념이 나오면 설명 먼저, 코드 나중
- DEVLOG.md에 날짜별 작업 내역을 지속적으로 기록 (뭘 했는지, 다음 단계는 뭔지). 작업 중간중간 꾸준히 업데이트할 것. 하루 끝에 **오늘의 성과**와 **오늘의 실패/한계**를 반드시 기록.
- commit + push를 자주, 꾸준히 할 것 (유저가 별도 지시하지 않아도). 의미 있는 변경이 생길 때마다 커밋.
- homework.md를 확인하고 대화 시작 시 미완료 항목을 유저에게 리마인드. 완료된 항목은 제거.

## 참고 프로젝트 (상세 → references.md)
- **dart-mcp** — DART 재무제표 MCP. FastMCP 패턴/OpenDART 호출 구조 참고. 단일파일/캐싱없음은 개선 대상.
- **Kensho (S&P Global)** — LLM 최적화 API 설계, 도메인별 tool 분리, dual transport(stdio+SSE) 참고.
- **FactSet** — 엔터프라이즈 MCP 거버넌스 패턴(Central Registry, Proxied Access), 데이터셋별 tool 구조 참고.
- 공통 교훈: raw API 그대로 노출하지 말고 LLM이 쓰기 쉽게 구조화, 도메인별 tool 분리, 캐싱 필수

## 파서 아키텍처
파서 상세(패턴 목록, 실패 케이스 분류, 벤치마크 결과 등)는 **DEVLOG.md**의 해당 날짜 항목 참조.

**파싱 파이프라인:**
1. `client.py` — DART API에서 HTML+text 동시 반환
2. `parser.py` — bs4(lxml)로 HTML 섹션 경계 추출 → regex로 안건 패턴 매치
3. 실패 시 text-only regex fallback → 그래도 실패 시 LLM fallback

**현재 처리율:** 250건 기준 93% (bs4+regex), 나머지 7%는 LLM fallback 대상.

## 파서 테스트-개선 루프
1. 전체 소집공고 검색 (250건+)
2. `parse_agenda_items()` 실행, `validate_agenda_result()` 체크
3. 실패 케이스 zone 텍스트 확인 → 패턴 추가
4. **250건 전수 regression 테스트** — 기존 성공 깨짐 없는지 반드시 확인
5. 반복

## 주요 커맨드
```bash
pip install -r requirements.txt    # 의존성 설치
python -m open_proxy_mcp           # 서버 실행
```
