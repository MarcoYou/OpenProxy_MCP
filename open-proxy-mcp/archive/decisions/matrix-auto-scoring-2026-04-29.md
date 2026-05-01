---
type: decision
title: 12 매트릭스 자동 채점 시스템 (v1.3)
generated: 2026-04-29
related: [decision-matrix-design, open-proxy-guideline]
---

# 12 매트릭스 자동 채점 시스템 (v1.3)

## 1. 개요

`_decision_matrices.json`의 12 카테고리 매트릭스 100 dim을 OPM data tool 기반으로 자동 채점하는 시스템.
proxy_guideline scope=predict의 `auto_score=True` 옵션 (기본 ON)에서 사용.

- **자동 채점 dim**: ~85개 (data tool에서 직접 추출 또는 휴리스틱)
- **Manual dim**: ~15개 (사용자 input 필수, 데이터 미통합 영역)
- **빙고 패턴 평가**: 76 패턴 인터프리터로 자동 매칭 → for/against/review 결정

## 2. 모듈 구조

신규 파일: `open_proxy_mcp/services/proxy_guideline_scoring.py`

핵심 함수:

- `score_*` (각 dim별 채점 함수): 0/1/2/None 반환
- `auto_score_<category>` (12개 dispatch 함수): dim 점수 dict 반환
- `evaluate_bingo_pattern`: 단일 빙고 패턴 평가 (condition 표현식 → bool)
- `evaluate_all_bingo_patterns`: 매트릭스의 모든 빙고 평가
- `aggregate_score_to_decision`: 점수 + 빙고 → for/against/review 결정
- `auto_score_matrix`: 카테고리 → data tool 호출 → dim 점수 통합 진입점

## 3. 카테고리별 자동/Manual 분류

### 3.1 director_election (9 dim)

| dim_id | 모드 | 데이터 소스 |
|---|---|---|
| outside_director_independence | auto | board candidates careerDetails 5년 룰 휴리스틱 |
| tenure | auto | careerDetails 재직년수 추정 |
| concurrent_positions | auto | careerDetails "현)" 카운트 |
| attendance | auto | corp_gov_report metric 매칭 (없으면 None) |
| adverse_news | manual | Naver News API 미통합 |
| fiduciary_duty_signal | auto | related_party_transaction + ownership |
| governance_compliance_rate | auto | corp_gov_report.compliance_rate |
| diversity | auto | board summary female_count |
| bundled_slate_signal | auto | other dim 결과 + appointments 묶음 검출 |

### 3.2 director_compensation (8 dim)

| dim_id | 모드 |
|---|---|
| utilization_rate | auto (compensation_summary.priorUtilization) |
| yoy_change | auto (current vs prior limit 차이 %) |
| ceo_pay_ratio | manual (peer 데이터 미통합) |
| performance_link | manual (TSR 통합 필요) |
| stock_option_dilution | auto (휴리스틱, 정량 부족 시 yellow) |
| retirement_pay | auto (안건 텍스트 황금낙하산 매칭) |
| company_performance | manual (financial_statements 미통합) |
| clawback_say_on_pay_signal | auto (corp_gov_report 추정) |

### 3.3 articles_amendment (9 dim)

전부 auto. agenda 텍스트 키워드 기반 + disclosure_compliance만 날짜 차이 정량.

### 3.4 audit_committee_election (8 dim)

- auto (5): 3pct_rule_compliance, separate_election, independence_5year, financial_expertise, compliance_rate, fiduciary_duty_signal
- manual (2): audit_opinion_history, non_audit_fee_ratio (audit_fee_disclosure tool 미통합)

### 3.5 treasury_share (8 dim)

- auto (6): burnout_commitment, purpose_clarity, disposal_method, ownership_structure_signal, treasury_share_ratio, fiduciary_duty_signal
- manual (2): disposal_agm_approval, shareholder_return_ratio

### 3.6 cash_dividend (8 dim)

- auto (5): payout_ratio_vs_industry (history 절대값), policy_disclosure (corp_gov metric), interim_quarterly_dividend, controlling_shareholder_signal, compliance_rate
- manual (3): cash_flow_sustainability, dividend_decision_authority, shareholder_return_ratio

### 3.7 financial_statements (9 dim)

- auto (2): fiduciary_duty_signal, compliance_disclosure
- manual (7): audit_opinion, non_audit_fee_ratio, accounting_error_history, internal_control_weakness, auditor_tenure, auditor_independence_signal, climate_disclosure (KIND/ESG 통합 필요)

### 3.8 merger (8 dim)

- auto (2): controlling_shareholder_conflict, anti_takeover_signal
- manual (6): 외부평가 + MoM + 시너지 등 (정성 영역)

### 3.9 spin_off (8 dim)

- auto (3): split_method, purpose_clarity, fiduciary_duty_signal
- manual (5): 자회사 상장 + 보호 + 평가 등

### 3.10 capital_increase_decrease (8 dim)

- auto (5): preemptive_right, anti_takeover_signal, capital_decrease_type, fiduciary_duty_signal, disclosure_compliance
- manual (3): issuance_size, issuance_purpose, issuance_price

### 3.11 cb_bw (8 dim)

- auto (1): fiduciary_duty_signal
- manual (7): cb_bw_disclosure tool 미통합 영역 다수

### 3.12 shareholder_proposal (9 dim)

- auto (4): esg_sustainability, minority_shareholder_protection, controlling_shareholder_conflict, active_engagement_signal
- manual (5): 장기 가치, 비교, 자격, 미시행 이력 등

## 4. 통계

- 총 dim: 100
- 자동 채점 (auto): ~71 dim
- manual 입력 권장: ~29 dim (financial_statements, merger, cb_bw가 manual 비중 높음)

자동 채점 비중이 카테고리마다 다른 이유: data tool 통합 정도. 향후 audit_fee_disclosure / esg_disclosure / cb_bw_disclosure tool 추가 시 자동 채점 비중 90%+로 상승 예정.

## 5. 빙고 패턴 인터프리터

### 5.1 condition 표현식 파싱

지원 문법:

```
dim_id=0           # 정확히 0 (red)
dim_id=2           # 정확히 2 (green)
dim_id≥1           # 1 이상
dim_a=0 AND dim_b=0   # 모두 만족
others ≥1          # 다른 dim (이미 매칭한 dim 제외) 모두 ≥1
모든 dim = 2       # 전체 dim green
```

### 5.2 시점 + 카테고리 조건

`안건일 ≥ 2026-03-06` → meeting_date 비교, threshold 미만이면 패턴 skip
`안건이 사외이사 선임` → agenda_category 매칭

### 5.3 평가 불가 조건 (skip)

- `자산 ≥ 2조원`: 회사 자산 통합 미가능 → 보수적 skip
- `회사 독립이사 비율 < 1/3`: board composition 메타 통합 필요

skip 시 패턴 미트리거 (보수적 — false negative 우선).

## 6. 점수 → 결정 매핑

`aggregate_score_to_decision` 로직:

1. **빙고 우선**:
   - against 빙고 1+ → against
   - review 빙고 1+ → review
   - for 빙고 + against/review 빙고 0 → for

2. **점수 fallback** (빙고 미트리거):
   - 2+ dim red → against
   - raw_score ≤ 7 + 데이터 충분 → against
   - raw_score ≥ 12 + red 0 + unknown 0 → for
   - else → review

3. **안전망 (conservative)**:
   - unknown ≥ total/2 + 빙고 미트리거 → review로 강제
   - 채점 오류 발생 시 → review

## 7. predict scope 자동 채점 통합

기존 사용 (수동 입력만):

```python
matrix_dimensions = {"outside_director_independence": 0, "fiduciary_duty_signal": 0}
result = await build_proxy_guideline_payload(
    scope="predict",
    company="KT&G",
    agenda_title="...",
    matrix_dimensions=matrix_dimensions,
    auto_score=False,
)
```

신규 사용 (자동 채점):

```python
result = await build_proxy_guideline_payload(
    scope="predict",
    company="KT&G",
    agenda_title="사외이사 김용기 선임의 건",
    auto_score=True,  # 기본
)

# result.data.auto_decision = {decision: against, raw_score: 6, ...}
# result.data.bingo_matches = [...]
# result.data.matrix_score.dimensions_scored = {...}
# result.data.manual_dims = ["adverse_news"]  # 입력 권장 안내
```

manual override 가능:

```python
result = await build_proxy_guideline_payload(
    scope="predict",
    company="KT&G",
    agenda_title="...",
    auto_score=True,
    matrix_dimensions={"adverse_news": 0},  # 자동 채점 결과에 사용자 input 합쳐 평가
)
```

## 8. prepare_vote_brief 통합

`auto_score_matrix=True` 옵션으로 안건별 자동 채점 활성화:

```python
result = await build_vote_brief_payload(
    company_query="KT&G",
    auto_score_matrix=True,
)
# result.data.proxy_guideline_brief.agenda_recommendations[i].auto_score = {
#     "decision": "against", "raw_score": 6, "triggered_pattern_ids": [...]
# }
```

상위 5건만 자동 채점 (cost 보호). 카테고리 중복 시 1회만 채점.

## 9. 검증 결과 (KT&G + 삼성전자)

### 9.1 KT&G 사외이사 선임

- 카테고리: director_election
- 자동 결정: **AGAINST** (score_red_2plus)
- 점수: 6/18 (red 3, unknown 3)
- 채점 dim: outside_director_independence=0, tenure=0, concurrent_positions=0, fiduciary_duty_signal=2, governance_compliance_rate=2, bundled_slate_signal=2
- unknown: attendance, adverse_news, diversity (데이터 부족)
- data_calls: board=exact, corp_gov=exact, ownership=exact, related_party=exact

### 9.2 삼성전자 보수한도

- 카테고리: director_compensation
- 자동 결정: **REVIEW** (score_mid)
- 점수: 6/16 (red 0, unknown 4)
- 채점 dim: utilization_rate=2, yoy_change=1, retirement_pay=2, clawback_say_on_pay_signal=1
- unknown: ceo_pay_ratio, performance_link, stock_option_dilution, company_performance (manual 영역)
- data_calls: compensation=exact, corp_gov=exact

두 회사 모두 정상 작동. 각각 against / review 결정에 도달. 데이터 부족(unknown) 시 conservative review로 fallback하는 안전망 정상 동작 확인.

## 10. 진화 방향

- audit_fee_disclosure tool 추가 → audit 카테고리 자동 비중 증가
- search_naver_news + LLM 분류 → adverse_news, audit_opinion_history 자동화
- esg_disclosure tool → climate_disclosure 자동화
- cb_bw_disclosure tool → cb_bw 카테고리 자동 채점 비중 80%+
- 회사 자산 통합 (own_corp_metadata) → "자산 ≥ 2조원" 조건 평가 가능

## 11. 안전망

- 채점 오류 발생 시 conservative review로 fallback (`scope_predict` try/except)
- unknown dim 절반 이상이면 for/against 강제로 review 변환 (단, 빙고 트리거 시 유지)
- disclaimer 메시지 자동 포함: "최종 판단은 사용자가 검토 후 결정"
- manual dim 명시적 표시 + 입력 가이드
