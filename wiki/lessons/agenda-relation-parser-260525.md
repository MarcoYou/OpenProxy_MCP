---
type: lesson
title: agenda-relation-parser-260525
date: 2026-05-25
related:
  - wiki/tools/shareholder_meeting_notice.md
  - wiki/tools/proxy_advise_before_meeting.md
  - wiki/architecture/audits/260525_0200_audit_agenda-relation-kospi300.md
---

# Agenda Relation Parser Lesson

## Context

`proxy_advise_before_meeting`이 주주제안/조건부/대안형 안건을 자동 FOR/AGAINST로 과감하게 판단하면, 실제 의결권 자문 보고서에서는 위험하다. 특히 고려아연처럼 경영권 분쟁과 주주제안이 섞인 공고는 앞부분 안건명만 보고 결론을 내리면 오판한다.

## Did

- `shareholder_meeting_notice` agenda node에 proposer/relation metadata를 추가했다.
- `proxy_advise_before_meeting`은 full agenda tree를 사용하고, 절차성/대안형/조건부 안건을 기본 REVIEW로 보수화했다.
- 50개 로컬 corpus, KOSPI300, KOSDAQ top 50을 돌려 relation 분포와 false positive를 확인했다.
- KOSPI300 재실행에서 파싱 실패 `requires_review`를 0으로 낮췄다.

## Improved

- 한샘: 제목부 정기/임시 판별 우선으로 정기주총을 임시로 오판하지 않는다.
- 호텔신라: `4. 목적사항` 정정공고형 안건 목록을 잡는다.
- SNT홀딩스: 후보자 표 헤더가 안건 제목에 붙지 않는다.
- 해성디에스: `제N호 의안.` 마침표형과 배당 주석 뒤 안건을 잡는다.
- no_filing: 결산월과 예상 정기주총 window를 함께 설명한다.

## Trade-off

- relation metadata는 의결권 판단을 대체하지 않는다. 자동 판단이 불확실한 경우 REVIEW가 늘어날 수 있다.
- 정정공고 fallback은 더 많은 비표준 텍스트를 스캔하므로, future false positive는 계속 audit로 확인해야 한다.
- large corpus JSON은 회귀 검증에는 유용하지만 repo size 부담이 있다. 향후에는 대표 corpus와 요약 결과를 분리 보관하는 정책을 검토한다.

## Takeaway

주총 안건 파싱은 "의안 번호 regex"보다 "문서 구조 boundary"가 더 중요하다. 정기/임시, 목적사항 시작점, 주석 종료점, 후보자 표 시작점을 각각 독립 경계로 보강해야 한다.

의결권 판단 layer에서는 파싱된 relation을 결론으로 쓰지 말고, 자동 FOR/AGAINST를 멈추는 guardrail로 쓰는 것이 더 안전하다.

## 관련

- [[260525_0200_audit_agenda-relation-kospi300]]
- [[shareholder_meeting_notice]]
- [[proxy_advise_before_meeting]]
