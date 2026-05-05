---
type: ralph
title: 파서 omnibus 성능 + scope 정합 점검 (20 iter, light)
created: 2026-05-05 23:30
updated: 2026-05-06 00:30 (1번 2번 작업 완료 후)
completion_promise: PARSER_OMNIBUS_VERIFIED
max_iterations: 20
ref:
  - wiki/lessons/scope-simplification.md
  - wiki/lessons/decision-tree-vs-matrix.md
  - feedback_data_action_tool_layers (data tool = parsing+computation, action tool = + decision evidence)
---

## Invoke (복붙)

```
/ralph-loop:ralph-loop wiki/ralph/260505_2330_ralph_parser-omnibus-perf.md 가이드 따라 모든 파서 성능 측정 강화 + scope 정합 점검 + 추가 또는 폐지 가능한 scope 발견. 시간 리소스 적게 각 iter spot 위주 batch 최대 30 회사. 모든 active 파서 G1 95 퍼센트 이상 또는 데이터 한계 정직 기록 + scope reorg 명확 결정 + data action layer 정합 검증 시 promise. --completion-promise PARSER_OMNIBUS_VERIFIED --max-iterations 20
```

# Ralph: 파서 omnibus 성능 + scope 정합

## Context

선행 작업 완료 (260505_2200 precision + 1번/2번 정리):
- shareholder_meeting_notice scope: 6 → 5 (`summary`/`board`/`compensation`/`aoi_change`/`prov_financials`)
- summary 강화: agenda hierarchy + 1호 안건 메타 (회기/사업연도/배당)
- aoi_change에 retirement raw 통합 (data tool 원칙)
- **prov_financials scope 신설** — 잠정 재무제표 4 quadrant raw (parse_provisional_financial_statement)
- `provisional_financial_statement.py` 독립 모듈 (parser.py 의존성 제거)
- 보수/퇴직 분기 정밀화 (n=226, G1 99-100% / G3 100% / G4 NPS 정합 100%)

이번 ralph 목적:
1. **모든 active 파서 G1 측정 + 강화** — 데이터 한계는 정직히 기록
2. **추가 가능한 scope 발견** — data tool 원칙 (parsing + computation, 판단 X)
3. **폐지 가능한 scope 발견** — raw 중복 / 미사용
4. **v1 dead parser 처리 결정** — 부활 또는 archive
5. **data/action tool layer 정합 점검** — 모든 파서가 어느 layer인지 명확

## 핵심 원칙 (코붕이 2026-05-05)

**Data tool 파서**:
- Parsing (raw 추출) + Computation (ratios / derived metrics / 단위 환산)
- 판단 X — LLM/사용자가 raw 보고 자체 판단
- 예: `parse_personnel_xml` (후보 경력 raw), `parse_compensation_xml` (당기/전기 raw + 인원수), `parse_provisional_financial_statement` (4 quadrant 표), `_compute_metrics` (ROE/부채비율 계산)

**Action tool 파서/logic**:
- + Decision evidence layer (정책 trigger + pre-set logic)
- 예: `_decide_retirement_pay`가 `parse_retirement_pay_xml` 결과 보고 황금낙하산 / 사외이사 퇴직금 / 지급률 2배수+ 등 trigger 분기

같은 parser를 두 layer가 공유 OK — 책임 분리 명확. 새 parser/scope 신설 시 어느 layer인지 먼저 정의.

## 가정

- No conversation context / no web search / MCP only / deterministic
- 분당 DART 1000회 hard rule (rolling cap 900)
- v2 production (`OPEN_PROXY_TOOLSET=v2`) 기준
- **light**: 각 iter spot 위주 (5-10 회사), batch 최대 30 회사 (rate-safe)
- 20 iter / 의미 있는 변경마다 commit
- 데이터 한계 발견 시 archive에 정직히 기록 (lessons/ralph-threshold-realism)

---

## 대상 파서 (audit 우선순위)

### Tier A — Active (현 v2 production 사용)

| Parser | 사용 layer | 사용처 | 마지막 audit | G1 status |
|---|---|---|---|---|
| `parse_agenda_xml` | data | shareholder_meeting summary (안건 트리) | 직접 audit X | 미측정 |
| `parse_agenda_details_xml` | data | shareholder_meeting + retirement chain | 직접 audit X | 미측정 |
| `parse_meeting_info_xml` | data | shareholder_meeting summary (회의 정보) | 직접 audit X | 미측정 |
| `parse_personnel_xml` | data + action | director_evaluation + board scope | 260504 7 iter | 89% (data limit 확정) |
| `parse_aoi_xml` | data | aoi_change scope (정관변경) | 직접 audit X | 미측정 |
| `parse_compensation_xml` | data + action | compensation scope + proxy_advise chain | 260505 precision (간접) | 99%+ |
| `parse_retirement_pay_xml` | data + action | aoi_change (raw) + proxy_advise (decision) | 260505 precision | 100% |
| `parse_corrections_xml` | data | summary correction_summary | 직접 audit X | 미측정 |
| `parse_provisional_financial_statement` | data + action | prov_financials scope + proxy_advise facts | 260505 1번 작업 (1 sample) | 미측정 (n=1) |

### Tier B — v1 dead (부활/archive 결정 필요)

| Parser | 현 상태 | 부활 가치 |
|---|---|---|
| `parse_treasury_share_xml` | tools/parser.py:3508 (v1 only) | 검증 필요 — treasury_share tool이 cover하면 archive |
| `parse_capital_reserve_xml` | tools/parser.py:3593 (v1 only) | 검증 필요 — articles_amendment에 통합되어 있는지 확인 |
| `parse_financials_xml` | tools/parser.py:2626 (v1 only) | **이미 부활** — services/provisional_financial_statement.py로 이동 (260505 1번). parser.py 본체 archive 검토 |

### Tier C — services 내 도메인 파서 (별도)

financial_metrics / treasury_share / dividend_v2 / ownership_structure / corp_gov_report 등의 도메인 services는 별도 ralph (이번 범위 X — 이미 충분히 audit됨 또는 별도 작업).

---

## 성공 기준 (모두 충족 시 promise)

### G1. 모든 Tier A 파서 G1 ≥95% (또는 데이터 한계 정직 기록)
KOSPI 200 + KOSDAQ 50 (light — 30 회사 batch + spot)에서 각 Tier A 파서가:
- "안건 detect됨" case 중 raw 추출 성공률 ≥95%
- 미달 시 archive에 fail 케이스 보존 + 데이터 한계 audit 작성

### G2. v1 dead parser 처리 결정 명확
- `parse_treasury_share_xml` → archive 또는 잔여 사용처 확인
- `parse_capital_reserve_xml` → archive 또는 articles_amendment 통합 검증
- `parse_financials_xml` (parser.py 본체) → archive (이미 services로 이동됨)

### G3. scope 추가/폐지 결정
이번 ralph 범위에서 발견한 scope 후보:
- 폐지: 미사용 scope 발견 시 (예: dividend `detail`이 `summary`와 raw 중복인지)
- 추가: 새 raw 노출 가치 발견 시 (data tool 원칙 준수)
각 결정에 근거 (사용 빈도 / data tool 원칙 정합 / raw 중복) 명시.

### G4. data/action tool layer 정합 검증
각 파서가 어느 layer인지 확인:
- 모든 data tool 파서: 판단 X (decision logic 포함하지 않음)
- 모든 action tool 사용 파서: data tool helper + 별도 decision layer 분리
- 위반 케이스 발견 시 fix

---

## 작업 plan (20 iter, light 단위)

### Phase 0 — Universe 확장 (iter 1, KOSDAQ 강화)

KOSDAQ 현재 top 50만 있음 → 샘플 부족. top 150까지 확장 (코붕이 의견).

#### iter 1. KOSDAQ universe top 50 → top 150 확장
- KIND 시총 ranking 크롤링 (`https://kind.krx.co.kr` 시총 page) 또는 KRX 정보광장
- KOSDAQ ticker list × 시총 sort top 150 → CSV
- 출력: `wiki/architecture/audits/data/260506_universe_kosdaq_150.csv`
- DART API 호출 X (KIND 웹 크롤링만, 분당 ~30 page rate-safe)

### Phase 1 — Tier A 파서 통합 audit (iter 2-5, **확장 sample**)

**핵심**: 30 회사 spot batch로 7 parser 모두 audit (master script). KOSPI 150 + KOSDAQ 150 = **300 회사** 광범위.

#### iter 2. Master spot script 작성 + 첫 batch (KOSPI 0-30)
- `scripts/spot_parser_omnibus.py` — 1 회사당 1 doc fetch + 7 parser 호출 + G1 metrics 일괄
- 첫 30 회사 batch — ~90 DART calls
- 결과: `wiki/architecture/audits/data/260505_parser_omnibus/iter02_kospi_0-30.json`

#### iter 3. KOSPI 30-150 + KOSDAQ 0-100 batch chain
- 5 batch chain × 30 회사 = 150 KOSPI + 100 KOSDAQ = 250 회사
- 각 batch sleep 30s → ~50분 분산
- 누적 ~750 DART calls (cross-iter stop hook gap으로 자연 분산)

#### iter 4. KOSDAQ 100-150 batch 추가 + 분석
- 마지막 50 KOSDAQ — ~150 calls
- 누적 결과 통합

#### iter 5. 결과 분석 + 각 parser G1 측정 (DART X)
- 300 회사 통합 G1 — 7 parser 동시 측정
- fail case archive
- parse_personnel_xml: 89% data limit 재확인 (재시도 X)
- KOSDAQ vs KOSPI 분포 차이 비교

### Phase 2 — Tier B v1 dead 결정 (iter 6-7, **DART 호출 0**)

#### iter 6. v1 dead parser 사용처 재확인 (정적 grep — DART X)
- `parse_treasury_share_xml` / `parse_capital_reserve_xml` 잔여 사용처 grep
- v2 services 어디에도 안 쓰면 archive 결정
- v1 tools/shareholder.py에서만 쓰이면 v1 dead로 분류

#### iter 7. `parse_financials_xml` parser.py 본체 archive (정적 — DART X)
- services로 이미 이동됨 — parser.py 본체 + 의존 helper들 archive
- v1 tools/shareholder.py import 정리

### Phase 3 — scope reorg 발견 (iter 8-13, 대부분 정적 분석 + 소량 spot)

대부분 코드 정적 분석 (DART X). 필요한 경우만 5 회사 spot (각 ~15 calls).

#### iter 8. dividend tool scope 검토 (정적 + 5 회사 spot if needed)
- summary / detail / history 3 scope 차이 — 코드 정적 비교

#### iter 9. ownership_structure scope 검토 (정적)
- 5 scope 중 raw 중복 check

#### iter 10. financial_metrics scope 검토 (정적 + 5 회사 spot)
- 6 scope (summary / yearly / quarterly / yoy / qoq / audit_opinion)

#### iter 11. proxy_contest scope 검토 (정적)

#### iter 12. treasury_share + corp_gov_report + value_up 빠른 정적

#### iter 13. layer 정합 검증 (G4) — 정적 분석
- 모든 data tool 파서가 decision logic 포함하지 않는지 grep + review
- action tool 사용 파서가 data helper + 별도 decision layer로 분리되어 있는지 확인

### Phase 4 — fix + 검증 (iter 14-18)

#### iter 14-16. 발견된 fix 적용 (parser 강화 / scope 폐지 또는 신설)
- 대부분 코드 변경 + smoke test (5 회사 spot, ~15 calls)

#### iter 17-18. 회귀 spot (KOSPI 30 + KOSDAQ 30 = 60 회사 batch)
- 변경된 모든 부분 재검증
- ~180 calls

### Phase 5 — 문서화 + promise (iter 19-20)

#### iter 19-20. wiki 정리 (decisions / log / tools 페이지 update) + promise 발행 (DART X)

---

## 총 DART 호출 추정 (KOSDAQ 확장 반영)

| Phase | iter | DART calls 추정 |
|---|---|---|
| Phase 0 (KOSDAQ universe 확장 — KIND 크롤링) | 1 | KIND ~30 page (DART X) |
| Phase 1 (parser audit, KOSPI 150 + KOSDAQ 150 = 300 회사) | 2-5 | ~900 calls (300 × 3) |
| Phase 2 (v1 dead 정적) | 6-7 | 0 |
| Phase 3 (scope reorg, 대부분 정적) | 8-13 | ~75 calls (5 회사 × 5 spot) |
| Phase 4 (fix + 회귀 60 회사) | 14-18 | ~225 calls (smoke + 회귀) |
| Phase 5 (문서화) | 19-20 | 0 |
| **총합** | 20 iter | **~1200 calls** (DART) + KIND 별도 |

→ **분산 시간 (수 시간 분리, iter간 stop hook gap)** 으로 분당 cap 900 미달 ✓
→ Phase 1 단일 batch 30 회사 ~90 calls / 6-12분 분산 → cap 900 micro 단위도 안전

---

## 영향 범위

- `open_proxy_mcp/tools/parser.py` — Tier A 파서 강화 + Tier B archive 검토
- `open_proxy_mcp/services/*.py` — services 내 파서 영향 시
- `open_proxy_mcp/tools_v2/*.py` — scope param 변경 (폐지/신설)
- `wiki/lessons/` — 새 lesson 추가 (parser layer / scope 정리 결과)
- `wiki/decisions/` — 결정 문서
- `wiki/architecture/audits/data/260505_parser_omnibus/` — 검증 데이터

## 비목표 (이번 ralph X)

- 도메인 services 깊이 audit (financial_metrics / treasury_share / ownership_structure 등 — 별도 ralph)
- 새 tool 추가 (audit_fee_disclosure / esg_disclosure 등)
- 운용사 majority cache normalize
- KOSDAQ universe 확장
- proxy_advise (action tool) decision logic 변경

## Rate limit 설계 (DART 분당 1000회 hard rule)

**design 핵심**: parser audit은 같은 AGM notice doc에서 여러 parser 호출 가능 → **1 회사당 1 doc fetch + N parser** (in-memory). 호출 수 폭증 X.

### Per-iter budget
- batch: 최대 30 회사 / concurrency 2 / 회사당 ~3 DART call (corp_code → search_filings → get_document)
- 30 회사 × 3 calls = **~90 calls/batch**. concurrency 2면 ~6-12분 분산.
- spot iter: 5-10 회사 = ~30 calls. 매우 안전.
- **단일 iter 최대 90 calls** ≪ cap 900/min ✓

### Master spot script (Tier A 파서 통합 audit)
iter 1-7을 7 batch (= 7 × 90 calls)로 돌리는 대신, **1 master batch로 통합**:
- 30 회사 spot 1회 → 각 회사의 AGM notice doc 1회 fetch
- 같은 html을 7 parser (`parse_agenda_xml` / `parse_agenda_details_xml` / `parse_meeting_info_xml` / `parse_personnel_xml` / `parse_aoi_xml` / `parse_compensation_xml` / `parse_provisional_financial_statement` / `parse_corrections_xml` / `parse_retirement_pay_xml`)에 모두 호출
- 결과 dict로 모은 다음 G1 metrics 일괄 계산

**호출 수**: 30 회사 × 3 calls = **90 calls** (parser 추가는 in-memory, DART 호출 X). iter 1 → 7 통합 가능.

### Cross-iter 안전
- 각 iter는 stop hook gap (수 분 ~ 수십 분)으로 분리 — DART rolling window 자연 reset
- 누적 영향 X (process 분리)

### Sequential batch 원칙
- 다중 batch chain 시 30s sleep 명시
- `client.py`의 rolling cap 900 hard guard 자동 throttle 신뢰

### 위험: 동시 다중 ralph
- 다른 ralph 또는 사용자 호출과 **동시에 실행 시 cap 초과 위험**
- mitigation: 이 ralph 단독 실행 (다른 ralph 동시 시작 금지)
- 실수 시 client.py의 rolling cap 900이 hard throttle (block 회피)

## 가설 / 위험

- **위험 1 (light 제약)**: 20 iter / 작은 batch — 깊은 audit 어려움. 정직하게 spot 위주 + 발견된 issue archive 기록.
- **위험 2 (parse_personnel data limit)**: 이미 89%로 확정된 데이터 한계. 재시도 X — 정직 인정.
- **위험 3 (scope 폐지 후 caller 영향)**: 변경 시 회귀 spot 필수.
- **위험 4 (parser.py 본체 archive)**: v1 tools/shareholder.py import 깨짐. v1 dead라 무방. 단 import 시점 fail 위험 회피 위해 alias 또는 parser.py 잔존 결정 필요.
- **위험 5 (rate limit)**: 위 design 따라 단일 iter ≤90 calls. 동시 다중 ralph 금지. client.py rolling cap 900 hard throttle 신뢰.

## archive 폴더

`wiki/architecture/audits/data/260505_parser_omnibus/`

---

## iteration log
(작성하면서 update)

### iter 1 — KOSDAQ universe top 50 → 150 확장 (KIND 크롤링)
(작성 예정)

### iter 2 — Master spot script + KOSPI 0-30 batch
(작성 예정)

### iter 3 — KOSPI 30-150 + KOSDAQ 0-100 batch chain (5 batch)
(작성 예정)

### iter 4 — KOSDAQ 100-150 batch + 분석
(작성 예정)

### iter 5 — 300 회사 통합 G1 측정 (DART X)
(작성 예정)

### iter 6-7 — v1 dead parser archive (정적, DART X)
(작성 예정)

### iter 8-13 — scope reorg 검토 (대부분 정적 + 소량 spot)
(작성 예정)

### iter 14-16 — fix 적용 + smoke test
(작성 예정)

### iter 17-18 — 회귀 spot (KOSPI 30 + KOSDAQ 30)
(작성 예정)

### iter 19-20 — 문서화 + promise
(작성 예정)
