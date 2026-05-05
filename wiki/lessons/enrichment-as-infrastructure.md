---
type: lesson
title: enrichment — facts/risk/citation/근거공고가 검증 가능한 응답 인프라
context: proxy_advise framework enrichment ralph (2026-05-04)
date_learned: 2026-05-04
---

# enrichment as infrastructure

## Context

이전 proxy_advise 응답 (단순화 전):
```yaml
agenda_title: "제25기 재무제표 승인의 건"
decision: FOR
reason: "감사의견 적정 + 자본잠식 없음"
```

문제: "왜 적정인지?" 사용자가 별도 검증 어려움. raw 데이터는 다른 tool (financial_metrics, corp_gov_report) 호출해야 확인 가능. round-trip + 인지 부담.

## Did

decisions 응답에 **enrichment fields** 추가 (ralph framework iter 1~8):

```yaml
agenda_decisions:
  - decision: FOR
    reason: "감사의견 적정 + 자본잠식 없음"
    facts:                                        # 정량 fact dict
      audit_opinion: "적정"
      net_income_krw: 515011000000
      capital_impairment_status: "normal"
      fy_current_net_income_krw_mn: -977063     # 1번 안건 본문 raw (FY25)
      fy_current_revenue_krw_mn: 1646811
    risk_factors:                                 # 위험 신호 list
      - "완전 자본잠식"
      - "장기연임"
    policy_citation: "OPM Guideline §재무제표 — 감사의견 적정 + 자본잠식 없음 시 FOR"
    policy_basis: "Open Proxy / case_by_case → OPM fallback"
    evidence_rcept_no: "20260224004273"           # DART viewer link
    appointment_type: "renewed"                   # 신임/연임 auto detect
```

후보별 raw (`candidates_evaluations[]`):
- main_job (전문성 hint)
- recommendation_reason_raw (회사 추천 사유)
- career_company_groups (경력)
- audit_history_check (과거 회사 회계 risk)

## Improved

- **사용자 자기검증 가능**: 결정 + 근거 + 출처 한 응답에. round-trip X.
- **LLM이 raw 보고 추가 판단 가능**: facts는 정량, risk_factors는 정성, policy_citation은 정책 근거. 셋 다 trace 가능.
- **NO_DATA 명시**: 데이터 없을 때 자동 FOR/REVIEW 대신 NO_DATA 반환 (사용자: "데이터/근거 없는데 자동 결정 X" 정책 반영).
- ralph framework iter1~8: 4 dimension (결격/독립성/전문성/과거행적) 노출률 100% (566/566 candidates) 검증.

## Trade-off

- **응답 size 증가**: 안건당 facts/risk/citation 추가. 한 회사 ~10 안건이면 token 배 정도 늘어남.
- **upstream chain 6개 fixed**: facts 만들려면 financial_metrics + ownership + corp_gov_report + director_evaluation 모두 필요. 사용자가 "안건만 보고 싶어도" 6 chain 발생 (다만 병렬, 5-15s).
- **enrichment 정확도가 OPM logic 정확도에 의존**: facts 추출 (특히 1번 안건 본문 FY raw)이 wrong이면 결정 자체 신뢰성 영향.

## Takeaway

- **AI tool 응답은 사용자가 즉시 검증할 수 있어야 한다** — decision 단독은 black box. enrichment (facts + risk + citation + 근거 link)는 transparency infrastructure.
- **3 layer enrichment 패턴**:
  1. facts (정량 — 검증 가능한 숫자)
  2. risk_factors (정성 — 위험 신호 list)
  3. policy_citation (rule — 어떤 정책 근거)
  + evidence link (rcept_no → DART viewer)
- **decision/AI는 fact 위에**: 결정 logic만으로 답하지 말고 "왜?" 같이 답해야. fact 명시 → 사용자가 logic 검증 가능.
- **NO_DATA 분기 중요**: 데이터 없을 때 자동 default decision은 위험. 명시적 NO_DATA가 정직.
- enrichment를 "예쁜 표"로 보지 말 것 — analytical infrastructure.

## 관련

- [[decision-vs-raw-separation]] (raw expose scope 폐지의 보완: enrichment로 raw 일부 제공)
- [[ralph-threshold-realism]] (enrichment 검증도 데이터 한계 고려)
- audit: `260504_2200_audit_proxy_advise_framework_iter1-8`
- 코드: `services/proxy_advise.py` `_extract_facts()`, `_extract_risks()`, `_policy_citation()`, `services/agm_first_agenda_fy.py`
