---
type: lesson
title: 파서 정밀화 검증 — 가정 vs 실측, parser audit 자체 부정확
date: 2026-05-08
related:
  - wiki/ralph/260508_0207_ralph_parser-precision.md
  - wiki/architecture/audits/260508_parser_audit.md
  - wiki/lessons/law-layer-precision-260508.md
---

# 파서 정밀화 검증 — 실측 결과

## 배경

Parser audit (260508_parser_audit) 결론: 40 파서 중 2개 (`parse_personnel_xml` careerDetails + `parse_aoi_xml` amendments) 보강 필요. 

Ralph 5 (260508_0207_ralph_parser-precision)에서 두 파서를 직접 실측 검증.

## 발견

### 1. parse_personnel_xml careerDetails — 0% 누락

**가정 (legacy local todo + parser audit)**: 서진/펩트론/심텍/고영 등 audit 후보 careerDetails 비어있음 → 5년 룰 long_tenure_concerns 작동 X.

**실측**: 분쟁 14 회사 + KOSPI 30 회사 = **44 회사 / 225 후보**:
- careerDetails 비어있음: **0건 (0.0%)**
- careerCompanyGroups 비어있음: **0건**

**결론**: 가정 부정확. TO_DO 정보가 stale (옛 batch v7b 시점의 발견이 그 후 어딘가에서 fix됨). 현재 시점 parse_personnel_xml은 강건.

5년 룰 미작동 진짜 원인은 careerDetails 추출이 아닌 `_classify_director_tenure` logic 자체 — 별도 ralph 영역.

### 2. parse_aoi_xml amendments — 1.66% 누락 (모두 source 한계)

**가정 (parser audit)**: KOSPI 200 audit 일부 회사 amendments 비어있음 — clause/label 추출 누락 fallback 필요.

**실측**: KOSPI 200 전체:
- 정관변경 안건 OK: 178
- 정관변경 안건 + amendments=[]: 3 (**1.66%**)
- 누락 3건: 기업은행 / 한국금융지주 / HD현대건설기계

**raw 분석**: 3건 모두 **source 본문에 정관변경 detail 없음**:
- 기업은행 / 한국금융지주: 안건 list만 본문, 변경전/후 detail 별첨 PDF
- HD현대건설기계: 변경전/후 키워드 자체 없음 (안건 list만)

→ parse_aoi_xml 한계가 아니라 source 한계. PDF fallback (3-tier 2단계)에서 catch 영역.

**결론**: parser 강화 불필요. 1.66% 누락은 별첨 PDF 처리 ralph 별도 검토.

## 핵심 교훈

### 1. audit는 1차 가설이지 결론이 아니다

본 parser audit (260508_parser_audit)는 코드 정적 분석 + 문서 기반 진단. 실측 데이터 검증 없이 "보강 필요" 결론. Ralph 5 실측 후 그 결론이 부정확함을 확인.

→ **audit는 가설**, ralph가 실측 검증. 두 단계 분리 패턴 유지.

### 2. TO_DO 정보의 staleness

legacy local todo에 있던 "서진/펩트론/심텍/고영 careerDetails 누락" 정보는 옛 batch v7b 시점 (2026-05-04). 그 사이 코드 / source 어딘가 변경되어 현재는 누락 없음. 

→ **수동 todo 항목은 작성 시점 명시 + 주기적 재검증 없이는 쉽게 stale해진다**. 완료 추적은 git history와 관련 wiki 시점 문서로 흡수하는 편이 안전하다.

### 3. parser audit의 분류 framework은 유효

40 파서 분류 (A 명명형 25 / B raw 보존 1 / C 혼합 14)는 적정. raw vs 파싱 결정 framework도 정합. 단 "어디를 보강" 결론은 실측 필요.

### 4. PDF fallback 영역

aoi 누락 1.66% 모두 source detail 없는 별첨 PDF 케이스. PDF fallback 검증 + 효과 측정이 별도 가치 있음.

## 영향 범위

- `wiki/ralph/260508_0207_ralph_parser-precision.md` — iter 1, 4 검증 결과 + iter 5-6 skip + iter 7 promise
- `wiki/architecture/audits/260508_parser_audit.md` — Ralph 5 실측 결과 추가, 권장 update (두 파서 보강 → 무효화)
- legacy local todo — "서진/펩트론/심텍/고영 careerDetails" 항목은 stale로 판명
- code 변경 X (parser 보강 불필요)

## 다음 ralph 후보 (재정렬)

| 우선순위 | ralph | 비고 |
|---|---|---|
| 🟡 1 | `_law_layer` 룰 슬림화 + amendments raw 통합 | proxy_advise 응답에 본문 raw 노출 (LLM 판단 영역 명시화) |
| 🟢 2 | PDF fallback (3-tier 2단계) 검증 | 1.66% 누락 (별첨 PDF) catch 가능 여부 |
| 🟢 3 | `_classify_director_tenure` logic (5년 룰) | careerDetails 정상 추출인데 5년 룰 트리거 X — 별도 진단 |

## archive

- `wiki/architecture/audits/260508_parser_audit.md` (수정 — 실측 결과 추가)
- 진단 sample: 분쟁 14 + KOSPI 200 + KOSDAQ 100 + 분쟁 20 = 280 회사 (Ralph 4 audit data 재활용)
