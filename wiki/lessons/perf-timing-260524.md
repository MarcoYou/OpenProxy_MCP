---
type: lesson
title: performance timing — 먼저 재고, 의미 보존 범위 안에서만 줄인다
context: 2026-05-24 data tools latency pass
date_learned: 2026-05-24
related:
  - wiki/architecture/audits/260510_data_tools_perf_audit.md
  - wiki/architecture/audits/data/260524_tool_timing_audit.json
related_audits:
  - 260510_data_tools_perf_audit
---

# performance timing

## Context

`LG화학 2026 정기주총 안건` 질의에서 OPM 응답이 느리게 느껴졌다. 처음에는 LLM timeout처럼 보였지만, 실제 병목은 tool 내부에서 DART `list.json`, `document.xml`, cross-tool helper를 어떤 순서와 범위로 호출하느냐였다.

이번 작업은 public data tools에 `data.timings_ms`를 넣고, `LG화학`, `삼성전자`, `KT&G` 3개 회사로 반복 측정하면서 low-risk latency를 줄인 pass다.

## Did

- `shareholder_meeting_notice`: `select_notice_candidate` timing을 세분화하고, 결산월 기반 annual window + 최신 후보 1건 우선 fetch를 적용했다.
- `treasury_share`: 결과보고서 검색을 전체 공시(`pblntf_ty=""`)에서 `B/I/E` title scan 1회로 바꾸고, DS005 API 호출과 병렬화했다.
- `dividend`: 선배당/감액배당 metadata detection과 과거 연도 `alotMatter` 조회를 앞당겨 다른 DART 호출과 overlap했다.
- `filing_search`: page 1에서 `total_count`를 확인한 뒤 page 2+ fetch를 병렬화했다.
- `corp_gov_report`: summary 계열은 2년, `filings/timeline`은 4년으로 검색 window를 scope별 분리했다.
- `value_up`: search timing을 세분화했고, 현재 병목이 아님을 확인했다.
- `pblntf_ty` 코드표와 treasury `B/I/E` 검색 정책을 문서화했다.

## Improved

- `shareholder_meeting_notice`: LG화학 기준 약 5.9s 경로가 약 1.8s 이하로 내려갔다.
- `treasury_share`: 삼성전자 2.7s급 경로가 약 0.9s 수준으로 내려갔다.
- `corp_gov_report`: summary 기준 4년 scan을 2년으로 줄여 0.2-0.46s 범위로 내려갔다.
- `dividend`: metadata detection 대기를 overlap해 삼성전자/KT&G에서 의미 있는 단축이 있었다.
- `value_up`: `dart_search`가 100-140ms 수준으로 확인되어 추가 최적화 대상에서 제외했다.

## Trade-off

- `timings_ms`가 public data에 노출된다. 디버그에는 유용하지만, 장기적으로는 `debug=true` 또는 tool-internal diagnostics로 숨길 수 있다.
- `corp_gov_report` summary 계열은 2년 window라 최신 보고서 탐색에 맞춘다. 대신 과거 제출 이력은 `filings/timeline` scope에서만 보존한다.
- `dividend`와 `treasury_share`의 남은 병목은 검색 범위 축소, cache, body enrich optional화 없이는 크게 줄이기 어렵다. 여기부터는 정확도/coverage trade-off가 생긴다.

## Failed experiments

- `treasury_share`에서 `B/I/E` 공시유형 자체를 병렬 fetch하는 실험은 실측상 title search가 줄지 않거나 오히려 늘어 폐기했다.
- `treasury_share`에서 `B`를 빼고 `I/E`만 보는 것은 샘플상 가능해 보였지만, 커버리지 리스크 때문에 보류했다.
- `treasury_share` body enrich optional화는 소각금액/결과보고서 실제 집행값 품질을 떨어뜨려 보류했다.
- `corp_gov_report` 전체를 2년으로 줄이는 대신 `filings/timeline`은 4년 유지했다. timeline 의미를 보존하기 위해서다.

## Takeaway

- **먼저 stage timing을 넣고, 숫자 없이 최적화하지 않는다.** timeout처럼 보여도 실제 병목은 다른 upstream일 수 있다.
- **검색 범위 축소는 scope 의미와 같이 설계한다.** summary는 최신값, timeline은 과거 이력이라는 의미가 다르다.
- **공시 검색은 pblntf_ty를 먼저 좁히고, 그 다음 제목 필터를 건다.** 전체 공시 순회는 느리고 누락 위험도 있다.
- **독립 upstream은 가능한 한 앞에서 시작한다.** 병렬화 자체보다 “대기를 겹치는 위치”가 중요하다.
- **실패한 최적화도 문서화한다.** 같은 병렬화 아이디어를 반복 실험하지 않게 한다.
- **남은 병목이 trade-off를 요구하면 멈춘다.** 성능보다 coverage와 evidence 품질이 더 중요한 tool이 있다.

## Related commits

- `fd6ee6c` Improve shareholder meeting notice latency diagnostics
- `558e509` Add proxy advise timing diagnostics
- `189d5af` Break down notice candidate timing
- `430be9a` Use fiscal month for annual meeting search
- `508def5` Fetch one annual notice candidate first
- `26ef440` Add timing diagnostics to core data tools
- `799fa4b` Optimize treasury share title scan
- `1cfffc8` Document disclosure type filters
- `df35e95` Overlap dividend metadata lookups
- `267346a` Parallelize paged filing scans
- `13d643b` Break down corp gov report timings
- `ff305e0` Break down value up search timings
- `a66e558` Shorten corp gov summary report search

## Related

- [[260510_data_tools_perf_audit]]
- [[pblntf-ty-필터링]]
- [[treasury_share]]
- [[dividend]]
- [[corp_gov_report]]
