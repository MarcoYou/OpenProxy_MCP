---
type: lesson
title: ralph threshold realism — 표준 서식 vs 자유 텍스트
context: 두 ralph (parse_personnel 89%, treasury 100%) 비교
date_learned: 2026-05-05
---

# ralph threshold realism

## Context

두 ralph가 비슷한 시기에 진행됨:

| ralph | target | 결과 | 데이터 성격 |
|---|---|---|---|
| parse_personnel_xml | career_period 95% | **89.0%** (도달 X) | 후보 약력 자유 텍스트 (회사명/기간 자유 형식) |
| treasury 결과보고서 | G1 99% / G2 99% | **100% / 100%** | 자본시장법 시행령 별지 표준 서식 (강제 양식) |

같은 99% target을 두고 한쪽은 데이터 한계로 fail, 다른 쪽은 over-achieve. threshold 정할 때 이 차이를 미리 인식해야.

## Did

**parse_personnel ralph**:
- 7 iter 진행 (role normalize 88.7→100%, period content year extract +0.3%p)
- 78 fail 후보 본문 정밀 검증: HTML 본문에도 year 정보 없는 case 다수
- "(주)포스코엠텍 감사팀장(주)나눔테크 전무이사" 같은 단순 직책+회사명 — 시작 연도 본문에 X
- parser fix 효과 무 → **본문 데이터 자체 한계**
- archive: `wiki/architecture/audits/data/260504_parse_personnel_failure_archive/`
- 정직 fallback (95% relax 또는 ralph cancel)

**treasury 결과보고서 ralph**:
- 처음 ±3일 fallback으로 G2 96% — 99% 미달
- ACODE semantic markers 발견 (자본시장법 시행령 별지 표준 서식의 system field id)
- main_report_date 매칭 + ±7일 fallback + trust 사이클 fallback + lookback 분리
- iter 15: G2 adjusted 100% (332/332) — 99% over

## Improved

- **차이의 근본**: 표준 서식 (강제 양식, system field id 존재) ↔ 자유 텍스트 (작성자 마음대로)
- 표준 서식: ACODE 같은 anchor가 있어서 99%+ 도달 가능
- 자유 텍스트: 본문에 정보 자체가 없으면 ML/heuristic도 한계 (raw 데이터 noise)

threshold 설정 가이드라인:
- **법적 강제 양식 (자본시장법 별지, 사업보고서 표 등)**: ≥99%
- **반자유 텍스트 (DART 본문 자유 서술 + 일부 표)**: ≥90-95%
- **완전 자유 텍스트 (후보 약력, 사유 등)**: ≥80-90% (또는 자체 데이터 한계 audit 후 결정)

## Trade-off

- **threshold 너무 너그러우면 (default 80%) 진짜 90-95% 가능한데도 멈춤**. user 지적: "표준 서식 표 데이터인데 99%는 되어야 하지 않겠니" — 도전적 target이 더 결과 좋을 수 있음.
- **threshold 너무 strict하면 데이터 한계 무시 + ralph 끝없이 돌림 + 정직성 약화** (false promise 유혹).
- **balance**: 데이터 성격 미리 평가 + threshold 정한 뒤, 도달 실패 시 archive에 데이터 한계 정직히 기록 (parse_personnel 패턴).

## Takeaway

- **ralph threshold는 데이터 성격 평가 후 정함**. 표준 서식 99%, 자유 텍스트 90% — 데이터가 결정.
- 표준 서식: 본문 grep으로 ACODE/system marker 먼저 확인. 있으면 99% target valid.
- 자유 텍스트: archive에 fail 케이스 raw 보존 + 데이터 한계 audit 작성. fail = ralph 실패 X, 한계 발견 = ralph 성공.
- ralph cancel은 정직 fallback의 한 form. promise X = ralph fail X.
- user (코붕이) 원칙: "데이터/근거가 없는데 FOR/AGAINST/REVIEW 반환하지 말라" — threshold 미달 시 NO_DATA / fallback 명시. 정직성 우선.

## 관련

- [[acode-semantic-markers]] (표준 서식 99% 도달 케이스)
- audit: `260504_2200_audit_proxy_advise_framework_iter1-8` (parse_personnel + framework)
- audit: `260505_0530_audit_treasury_execution_iter1-8` (treasury 100% 도달)
- 정직 fallback 케이스: `wiki/architecture/audits/data/260504_parse_personnel_failure_archive/iter07_data_limit_confirmed.md`
