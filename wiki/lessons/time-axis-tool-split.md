---
type: lesson
title: 시점 분리 — shareholder_meeting을 notice/results로 split
context: shareholder_meeting tool 분리 (2026-05-04)
date_learned: 2026-05-04
---

# 시점 분리 (notice + results)

## Context

기존 `shareholder_meeting` tool은 한 entry point에서 두 다른 source를 묶었음:
- **DART API/XML** 기반 사전 (소집공고, 안건, 이사후보, 보수한도, 정관변경) — 0.5-1.5s, 안정적
- **KIND web scraping** 기반 사후 (의결 결과) — 4.9s, fragile (KIND 변경 시 깨짐)

scope 7개 (summary/agenda/board/compensation/aoi_change/results/full) 중 results만 KIND 의존. full은 모든 scope 병렬 ~8s.

## Did

이미 존재하는 시점 분리 패턴 (`proxy_advise_before_meeting` / `proxy_result_after_meeting`)을 따라 shareholder_meeting 분리:

- **`shareholder_meeting_notice`** (사전, DART): summary / agenda / board / compensation / aoi_change / full (results 제외)
- **`shareholder_meeting_results`** (사후, KIND): results 단일

서비스 (`services/shareholder_meeting.py`)는 그대로 두고 (단일 `build_shareholder_meeting_payload`), public tool만 두 개로 분리. 공유 render helper는 `tools_v2/_shareholder_meeting_render.py` (`_` prefix로 auto-discovery 제외).

## Improved

- **fragility 격리**: KIND 장애가 사전 (notice) tool에 영향 X. notice는 DART API만 사용해 안정.
- **사용자 의도 명확**: "주총 안건" vs "주총 결과" — Claude.ai가 도구 선택 쉬움.
- **docstring 짧아짐**: 1 tool에 7 scope 설명 → 2 tool에 6+1 scope. Claude.ai 동적 tool loading 부담 ↓.
- **proxy_advise/proxy_result 패턴과 consistency** — 시점 분리가 OPM 도메인 표준 패턴 됨.

## Trade-off

- **tool count +1** (16 → 17, 그리고 다시 16으로 정리됨; screen_events drop으로 net 0).
- **"주총 전후 다" 케이스 두 번 호출** (다만 거의 없는 패턴 — 사용자는 시점 명확히 알고 있음).
- **shared render helper 모듈 추가**: `_shareholder_meeting_render.py` 도입 (tools_v2 auto-discovery 회피용 `_` prefix).

## Takeaway

- **두 source의 안정성·시점이 다르면 분리**. 한 tool에 묶는 건 일견 단순하지만 fragility 전파 위험 + 사용자 의도 모호.
- **service는 단일, public tool만 분리**가 깔끔 — 코드 중복 X, layer 책임 분리 (service = data, tools_v2 = public surface).
- 시점 분리는 OPM 도메인의 자연스러운 axis (주총 사전/사후, 정정공시 사전/사후 등). 같은 패턴 다른 domain에도 적용 가능.

## 관련

- [[scope-simplification]] (scope 줄이는 다른 axis)
- proxy_advise_before / proxy_result_after — 같은 시점 분리 패턴
- 코드: `tools_v2/shareholder_meeting_notice.py`, `shareholder_meeting_results.py`, `_shareholder_meeting_render.py`
- commit: `4638669` (2026-05-04)
