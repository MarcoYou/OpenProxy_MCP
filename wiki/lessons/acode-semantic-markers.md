---
type: lesson
title: ACODE semantic markers — text regex 한계 돌파
context: treasury 결과보고서 4종 본문 파싱 (ralph iter 1~2)
date_learned: 2026-05-04
---

# ACODE semantic markers

## Context

자기주식 결과보고서 4종 (취득/처분/신탁상황/신탁해지) 본문 파싱 시 합계·수량 추출이 필요했다. DART 표준 서식 표 (자본시장법 시행령 별지) 형태이지만 `doc.text` (text 추출)에서는 표 cell 경계가 사라져 정규식 매칭이 불안정했다.

## Did

**iter 1 (실패 접근)**: 키워드 + 인접 숫자 정규식
```python
m = re.search(r"취득가액?\s*총액\s*\(?\s*원\s*\)?[\s\S]{0,30}?([\d,]{8,})", clean)
```
→ 여러 cell의 숫자가 한 줄로 풀려서 첫 번째 잘못된 숫자 매칭 빈번. 추출률 0%에 가까움.

**iter 2 (성공)**: HTML 본문 inspection 중 발견 — DART XML 본문에 ACODE 속성:
```xml
<TE ACODE="ACQ_AMT" ...>7,174,299,854,900</TE>
<TE ACODE="DSP_AMT" ...>406,606,709,400</TE>
<TE ACODE="OBJ_OTH" ...>직원</TE>
```

ACODE는 자본시장법 시행령 별지 표준 서식의 system field id — 회사·정정 무관 동일.

helper:
```python
def _extract_acode(html, code):
    m = re.search(rf'<T[EDH]\s+[^>]*ACODE="{re.escape(code)}"[^>]*>([\s\S]*?)</T[EDH]>', html)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else None
```

## Improved

| Metric | iter 1 | iter 2 |
|---|---|---|
| 취득결과 | 0 fields | 12 fields |
| 처분결과 | 0 fields | 12 fields |
| 신탁취득상황 | 0 fields | 7 fields |
| 신탁해지결과 | 1 field | 10 fields |
| **G1 본문 파싱 성공률** | ~0% | **100%** (KOSPI 100 + KOSDAQ 50 검증) |

## Trade-off

- **HTML 본문 의존**: text 기반 fallback도 유지해야 (HTML 추출 fail 시).
- **field name 추정 위험**: ACODE 카탈로그가 공식 문서화 안 됨. 직접 본문 grep으로 발견 + sample 검증 필수.
- **취득/처분 결정 등 다른 공시는 ACODE 패턴 다름**: 동일 카탈로그 가정하면 안 됨.

## Takeaway

- **표준 서식 본문 파싱 시 항상 XML semantic anchor 먼저 확인**. text regex는 fallback.
- 발견한 ACODE는 wiki에 카탈로그 (`wiki/rules/disclosures/{공시}.md`).
- 99% threshold가 비현실적이지 않다 — 표준 서식 (강제 양식)이면 도달 가능. 자유 텍스트와 구분.

## 관련

- [[ralph-threshold-realism]] (어떤 데이터에 99% target이 valid한지)
- 코드: `services/treasury_share.py` `_extract_acode()`, `_acode_int()`
- audit: [[architecture/audits/260505_0530_audit_treasury_execution_iter1-8]]
