---
type: readme
title: lessons/ — 작업 회고
updated: 2026-06-01
---

# lessons/

작업하면서 배운 것 + 결정의 trade-off. 시점에 묶지 않은 정체성 문서 (`{topic}.md`).

각 페이지 schema:
- **Context**: 왜 이걸 다뤘나
- **Did**: 무엇을 했나
- **Improved**: 무엇이 나아졌나
- **Trade-off**: 무엇을 잃었나
- **Takeaway**: 다음에 반복할 원칙

## 목록 (2026-06-01 기준)

1. [[acode-semantic-markers]] — DART 본문 ACODE 발견 → text regex 한계 돌파, 99% 안정성
2. [[scope-simplification]] — tool 안 specialized scope 폐지 → 사용자 라우팅 단순화
3. [[time-axis-tool-split]] — shareholder_meeting을 사전(notice)/사후(results)로 분리 → fragility 격리
4. [[hard-rate-limit]] — DART 분당 1000회 hard rule을 코드로 강제 → 차단 사고 재발 방지
5. [[ralph-threshold-realism]] — 표준 서식 99% / 자유 텍스트 90% — 데이터 자체 한계가 threshold 결정
6. [[decision-vs-raw-separation]] — decision logic은 tool 안에서, raw expose는 외부 tool로
7. [[enrichment-as-infrastructure]] — facts/risk/citation/근거공고 = 검증 가능한 응답의 핵심
8. [[distribution-calibrated-thresholds]] — classification cutoff은 prior 직관이 아니라 audit 표본 분포 본 후 정함
9. [[decision-tree-vs-matrix]] — 안건 결정 2가지 방식 (매트릭스 vs 트리), 안건 성격이 방식 결정
10. [[perf-timing-260524]] — stage timing 먼저, 의미 보존 범위에서만 latency 개선
11. [[agenda-relation-parser-260525]] — agenda relation은 결론이 아니라 자동 판단을 멈추는 guardrail, KOSPI300 parser regression 0 확인
12. [[agenda-classification-260507]] — agenda parent/child short-circuit와 high-impact 분류
13. [[classify-high-impact-260508]] — high-impact 안건 분류 threshold와 false positive 회피
14. [[law-layer-260508]] — 법령 layer 도입의 결정/검증 분리
15. [[law-layer-precision-260508]] — 법령 layer 정밀화와 parent pattern guard
16. [[law-layer-body-260510]] — 제목 매칭 한계와 body fallback
17. [[parser-precision-260508]] — 파서 정밀화 판단 기준: source 한계 vs parser 한계 분리
18. [[parser-omnibus-260506]] — parser omnibus 검증과 DART table edge case
19. [[agenda-hierarchy-260510]] — 호수 hierarchy 추출과 D 패턴 fallback
20. [[subagenda-mapping-260510]] — sub-agenda와 amendment 1:1 매핑
21. [[director-faithfulness-260510]] — 사외이사 겸직/충실성 fact 노출
22. [[career-parser-concat-260510]] — careerDetails concat/boundary 처리
23. [[260510_daily-summary]] — 2026-05-10 일일 작업 요약
