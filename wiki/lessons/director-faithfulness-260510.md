---
type: lesson
title: 사외이사 충실성 강화 — 겸직 카운트 + 사내이사 독립성 표기 정정 (Ralph 9)
date: 2026-05-10
related:
  - wiki/ralph/260510_1100_ralph_director-faithfulness-enhancement.md
related_decisions: [260510_1130_decision_director-faithfulness]
related_ralph: [260510_1100_ralph_director-faithfulness-enhancement]
related_audits: [architecture/audits/data/260510_director_faithfulness/iter1_findings]
---

# Ralph 9 — 사외이사 충실성 강화 회고

## 배경

메리츠금융지주 proxy_advise 응답 검토 시 사용자 피드백:
1. 김용범 사내이사 "독립성 충족" 표시 부적절 (마치 독립이라 오인)
2. 충실성에 사외이사 겸직 카운트 추가 필요 (다른 회사 사외이사 또 하면 우려)
3. 최대주주 특수관계인 → 독립성에 유지

## 핵심 발견

### 1. careerDetails 데이터 가용성 충분

510 회사 audit:
- 사외이사 후보 798
- careerDetails 있는 후보 98.4%
- 겸직 신호 (현재 + 사외이사) 있는 회사 19.6%

→ DART API careerDetails로 자동 카운트 실현 가능.

### 2. false positive — 본 회사 사외이사 표기

careerDetails에 후보 본인의 본 회사 사외이사 직책 들어있는 케이스 多 (하나금융지주/우리금융지주/에이피알 등). 단순 키워드 카운트 시 false positive.

→ logic v3 — 본 회사명 매칭 자동 검출 + 본 회사 표기 X면 후보 본인 +1.

### 3. v3 정확 카운트 (510 회사)

| 항목 | 수치 |
|---|---:|
| 사외이사 후보 | 815 |
| concerns 후보 (≥2개 사외이사) | 108 (13.3%) |
| strong 후보 (≥3개) | 22 (2.7%) |
| **concerns 회사** | **64 / 493 (13.0%)** |
| **strong 회사** | **13 / 493 (2.6%)** |

iter 1 단순 키워드 96 회사 → v3 정확 64 회사. **false positive 32 회사 제거**.

## 코드 변경

### director_evaluation.py

```python
def count_outside_director_positions(candidate, own_company_name):
    """후보 사외이사 직책 총 갯수 (본 회사 자동 포함).

    careerDetails 중:
    - period에 '현재' / '현직' / '재직' 마커
    - content에 '사외이사' / '독립이사' 키워드 (regex)
    - 본 회사명 매칭 자동 검출 → 본 회사 표기 X면 +1
    """
```

`evaluate_faithfulness` / `evaluate_faithfulness_basic`에 통합. 사외이사/독립이사 한정 적용.

faithfulness summary 통합:
- audit_history red_flag → "concerns"
- strong_concerns_concurrent (≥3개) → "concerns"
- concerns_concurrent (≥2개) → "weak_concerns"
- single_position (1개) → 기존 그대로 ("raw_disclosed")

### proxy_advise.py — _extract_facts

사내이사 독립성 표기 정정:
```python
if is_outside:
    facts["independence"] = (eval_match.get("independence") or {}).get("summary")
else:
    facts["independence"] = "독립성 평가 비대상 (사내이사)"
```

사외이사 한정 겸직 facts 노출:
```python
facts["concurrent_outside_positions"] = co.get("total")
facts["concurrent_summary"] = co.get("summary")
```

## 단위 검증

| 후보 | 회사 | role | 결과 |
|---|---|---|---|
| 김용범 | 메리츠 | 사내이사 | "독립성 평가 비대상 (사내이사)" ✓ |
| 존림/노균 | 삼성바이오 | 사내이사 | "독립성 평가 비대상 (사내이사)" ✓ |
| 조홍희 | 메리츠 | 사외이사 | 겸직 1 (single, 본 회사만) ✓ |
| 김정연 | 삼성바이오 | 사외이사 | 겸직 **3 strong** (한국타이어+한화손해보험+본) ✓ |
| 박진규 | LG에너지솔루션 | 사외이사 | 겸직 **2 concerns** (롯데이노베이트+본) ✓ |
| 이명규 | LG에너지솔루션 | 사외이사 | 겸직 1 (single) ✓ |

## decision 영향

`_decide_director_election`은 `audit_history_check.summary`만 활용 → faithfulness.summary 변경에 **decision 영향 0**.

facts에 신규 표기 (concurrent_outside_positions / concurrent_summary) 추가 → LLM 직접 검토용. 향후 decision logic에 통합 가능 (별도 ralph).

## 핵심 교훈

### 1. 작은 sample만 보고 판단 금지
초기 메리츠금융지주 4명만 보고 "데이터 없다"고 판단. 510 회사 광범위 audit 결과 98.4% 채워짐. 사용자 지적 후 spot 진행 — 정확한 데이터 가용성 확인.

### 2. false positive 안전장치
단순 키워드 카운트 → 본 회사 사외이사 false positive. 본 회사명 매칭 + 후보 본인 보장 logic으로 정확도 ↑.

### 3. 사내이사 표기 정정
"충족" / "독립" 표기는 사외이사 영역. 사내이사는 명시적 "비대상" 표기로 오인 방지.

## 다음 ralph 후보

1. _decide_director_election에 concurrent_summary 통합 (strong → REVIEW)
2. 충실성 다른 항목 강화 (성과 평가 정확도)
3. director_evaluation 응답에 careerDetails raw 노출 (LLM 직접 검토)

## archive

- `architecture/audits/data/260510_director_faithfulness/iter1_concurrent_audit.json`
- `architecture/audits/data/260510_director_faithfulness/iter2_concurrent_v3.json`
- `architecture/audits/data/260510_director_faithfulness/iter1_findings.md`
