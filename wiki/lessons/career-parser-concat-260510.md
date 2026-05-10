---
type: lesson
title: careerDetails parser concat 분리 강화 — XML 직책 boundary split (Ralph 10)
date: 2026-05-10
related:
  - wiki/ralph/260510_1200_ralph_career-parser-concat.md
related_decisions: [260510_1130_decision_director-faithfulness, 260510_1230_decision_career-parser-concat]
related_ralph: [260510_1200_ralph_career-parser-concat, 260510_1100_ralph_director-faithfulness-enhancement]
related_audits: [architecture/audits/data/260510_career_concat/iter4_findings]
---

# Ralph 10 — careerDetails parser concat 분리 강화 회고

## 배경

Ralph 9 (사외이사 겸직 카운트) 구현 후 메리츠금융지주 진단 시 발견:
- raw HTML 표 셀에 4개 period + 4개 직책 concat
- parser 추출은 2 entries만 (절반 누락)
- "2011~현재 법무법인 태평양 고문" 같은 현직 본업 entries 모두 누락

## 진단 흐름 — 표면이 아닌 깊은 곳

| 단계 | 처음 가설 | 실제 |
|---|---|---|
| 1 | _split_concatenated_career_entry (clean 단계) 추가하면 해결 | ❌ 이미 잘못된 entries 받음 |
| 2 | _extract_career_from_html (1단계) 결과 정확? | ❌ None 반환 (메리츠 case 1단계 실패) |
| 3 | fallback 2단계 (md table parsing) 결과 분석 | ✅ 진짜 fix 위치 |

진짜 문제: fallback 2단계의 contents 분리 logic이 "법무법인" prefix만 사용 → 4 직책 → 2개로만 split (periods 4 + contents 2 mismatch).

## 핵심 fix — 직책 boundary split

```python
def _split_content_by_role_endings(content: str) -> list[str]:
    """직책 끝 boundary 기반 split.
    
    예: "서울지방국세청 조사4국장국세청 법인납세국장서울지방국세청장법무법인 태평양 고문"
        → ['서울지방국세청 조사4국장', '국세청 법인납세국장',
           '서울지방국세청장', '법무법인 태평양 고문']
    """
    # 직책 끝 키워드: 국장 / 청장 / 위원장 / 위원 / 사외이사 / 고문 / 사장 /
    #               부회장 / 회장 / 본부장 / 교수 / 회원 등 30+
    # boundary 위치마다 split
```

fallback 2단계 통합:
```python
# periods >= 2 + contents < periods → boundary split 시도
if len(periods) >= 2 and len(contents) < len(periods):
    boundary_split = _split_content_by_role_endings(contents_raw)
    if len(boundary_split) == len(periods):  # N 정확 일치만
        contents = boundary_split
```

## 검증 결과

### 메리츠금융지주

| 후보 | Before | After |
|---|---:|---:|
| 조홍희 | 2 | **4** (2010, 2011~현재 회수) |
| 김우진 | 1 | **5** (5년 단위 5직급 split) |
| 김명애 / 김연미 | 1 / 1 | 1 / 1 (period 1개 case) |

### 510 회사 회귀

| 항목 | Before | After | 변화 |
|---|---:|---:|---|
| concerns 후보 (≥2) | 108 | 112 | +4 |
| strong 후보 (≥3) | 22 | 20 | -2 |
| concerns 회사 | 64 | 66 | +2 |
| strong 회사 | 13 | 11 | -2 |

→ entries 정확도 ↑ → 분류 더 정확 (일부 strong→concerns 이동, +4 후보 신규 catch).

## 핵심 교훈

### 1. parser 강화는 깊은 위치 필요
표면 logic (_clean_career_details)은 이미 정제된 entries 받음. 진짜 문제는 raw 추출 단계 (_extract_career_from_html / fallback 2단계). 디버깅 시 pipeline 전체 흐름 추적 필수.

### 2. 안전 fallback (N 정확 일치만)
boundary split 결과가 periods 수와 정확 일치할 때만 채택. 그 외엔 원본 유지 → false positive 0.

### 3. period 1개 + content multi 케이스 (G5)
같은 시기 여러 직책 거치는 케이스 (학교 직급 변화). period 단일 → split logic 진입 X. 별도 architect 필요.

### 4. XML only 가설 검증 ✓
HTML viewer fallback 추가 없이 XML raw만으로 데이터 회수 가능. parser 정확도가 핵심.

## 다음 ralph 후보

1. period 1개 + content multi-roles 케이스 (메리츠 김명애/김연미 같은)
2. _extract_career_from_html 1단계 재진단 (왜 메리츠 case에 None 반환?)
3. 다른 회사 careerDetails 표 layout variation 탐색

## archive

- `architecture/audits/data/260510_career_concat/iter1_concat_audit.json`
- `architecture/audits/data/260510_career_concat/iter4_findings.md`
