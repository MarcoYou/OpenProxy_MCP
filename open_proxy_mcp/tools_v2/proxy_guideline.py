"""v2 proxy_guideline public tool — 자산운용사 의결권 정책 + 행사내역 + OPM Guideline 통합."""

from __future__ import annotations

from typing import Any

from open_proxy_mcp.services.contracts import as_pretty_json
from open_proxy_mcp.services.proxy_guideline import (
    _CATEGORIES,
    _CATEGORY_KO,
    build_proxy_guideline_payload,
)


def _render_error(payload: dict[str, Any]) -> str:
    lines = [f"# proxy_guideline: {payload.get('subject', '')}", ""]
    for warning in payload.get("warnings", []):
        lines.append(f"- {warning}")
    return "\n".join(lines)


def _render_policy(data: dict[str, Any]) -> str:
    pid = data.get("policy_id", "")
    meta = data.get("policy_meta", {})
    lines = [f"# 정책: {meta.get('manager_name', pid)} (`{pid}`)", ""]
    lines.append(f"- type: `{meta.get('type', '?')}`")
    lines.append(f"- version: `{meta.get('version', '?')}`")
    lines.append(f"- effective_date: `{meta.get('effective_date', '?')}`")
    if meta.get("external_advisor"):
        lines.append(f"- external_advisor: `{meta['external_advisor']}`")
    lines.append("")

    if data.get("category"):
        # 단일 카테고리 상세
        lines.append(f"## 카테고리: {_CATEGORY_KO.get(data['category'], data['category'])}")
        rule = data.get("rule", {})
        lines.append(f"- default: `{rule.get('default', 'not_specified')}`")
        for key, label in [("for", "찬성 기준"), ("against", "반대 기준"), ("review", "검토 권고"), ("abstain", "기권")]:
            items = rule.get(key, [])
            if items:
                lines.append(f"\n### {label} ({len(items)})")
                for item in items[:8]:
                    lines.append(f"- **{item.get('criterion', '')}**")
                    if item.get("source_text"):
                        lines.append(f"  - 원문: {item['source_text'][:150]}")
                    if item.get("section"):
                        lines.append(f"  - section: `{item['section']}`")
        return "\n".join(lines)

    # 전체 정책 요약
    if data.get("general_principles"):
        lines.append("## 일반 원칙")
        for p in data["general_principles"][:6]:
            lines.append(f"- {p}")
        lines.append("")

    lines.append("## 12 카테고리 룰 요약")
    lines.append("| 카테고리 | default | for | against | review |")
    lines.append("|---|---|---|---|---|")
    for cat in _CATEGORIES:
        s = data.get("voting_rules_summary", {}).get(cat, {})
        lines.append(
            f"| {_CATEGORY_KO.get(cat, cat)} | `{s.get('default', '?')}` "
            f"| {s.get('for_count', 0)} | {s.get('against_count', 0)} | {s.get('review_count', 0)} |"
        )

    if data.get("novel_topics"):
        lines.append(f"\n## Novel Topics ({len(data['novel_topics'])})")
        for tid, t in list(data["novel_topics"].items())[:8]:
            lines.append(f"- **{tid}** (`{t.get('default', '?')}`): {t.get('rationale', '')[:100]}")

    if data.get("korea_specific"):
        lines.append(f"\n## 한국 특수 룰 ({len(data['korea_specific'])})")
        for k in data["korea_specific"][:8]:
            lines.append(f"- {k}")

    completeness = data.get("completeness", {})
    if completeness:
        lines.append(f"\n- coverage: {completeness.get('categories_covered', '?')}/12, confidence: `{completeness.get('extraction_confidence', '?')}`")

    return "\n".join(lines)


def _render_record(data: dict[str, Any]) -> str:
    mgr = data.get("manager", "")
    filters = data.get("filters", {})
    lines = [f"# 행사내역: `{mgr}`", ""]
    lines.append(f"- 필터: company=`{filters.get('company') or '-'}`, year=`{filters.get('year') or '-'}`, period=`{filters.get('period') or '-'}`, category=`{filters.get('agenda_category') or '-'}`")
    lines.append(f"- 매칭 votes: **{data.get('total_votes', 0)}건**")
    lines.append("")

    period_summary = data.get("period_summary", [])
    if period_summary:
        lines.append("## Period Summary")
        for p in period_summary:
            lines.append(f"- {p.get('period', '')}: 필터 후 {p.get('filtered_count', 0)} / 원본 {p.get('original_total', 0)}")
        lines.append("")

    decisions = data.get("decision_breakdown", {})
    if decisions:
        total = sum(decisions.values()) or 1
        lines.append("## 의사결정 분포")
        for k, v in decisions.items():
            lines.append(f"- {k}: {v} ({v/total*100:.1f}%)")
        lines.append("")

    cats = data.get("category_breakdown", {})
    if cats:
        lines.append("## 카테고리 분포 (Top 8)")
        for cat, n in cats.items():
            lines.append(f"- {_CATEGORY_KO.get(cat, cat)}: {n}")
        lines.append("")

    companies = data.get("company_breakdown_top10", {})
    if companies:
        lines.append("## 회사별 (Top 10)")
        for c, n in companies.items():
            lines.append(f"- {c}: {n}건")
        lines.append("")

    votes = data.get("votes", [])[:15]
    if votes:
        lines.append(f"## 샘플 votes (최대 15건, 전체 {data.get('total_votes', 0)})")
        for v in votes:
            lines.append(
                f"- {v.get('meeting_date', '')} | {v.get('company', '')} | "
                f"{v.get('agenda_category', '')} | **{v.get('decision', '')}** — {v.get('agenda_title', '')[:60]}"
            )
        if data.get("votes_truncated"):
            lines.append(f"- ... (총 {data.get('total_votes', 0)}건, period/year/category 좁히면 더 정확)")
    return "\n".join(lines)


def _render_consensus(data: dict[str, Any]) -> str:
    lines = ["# 운용사 합의/이견 분석", ""]
    if data.get("category"):
        cat = data["category"]
        lines.append(f"## 카테고리: {_CATEGORY_KO.get(cat, cat)}")
        if data.get("topic"):
            t = data["topic"]
            lines.append(f"\n### Topic: {t.get('topic_label', t.get('topic_id', ''))}")
            lines.append(f"- 합의 수준: `{t.get('agreement_level', '?')}` ({t.get('agreement_count', 0)}/N 합의)")
            positions = t.get("positions", {})
            if positions:
                lines.append("- 운용사 입장:")
                for mgr, pos in positions.items():
                    lines.append(f"  - {mgr}: `{pos}`")
            for ev in t.get("evidence", [])[:5]:
                lines.append(f"  - 근거 ({ev.get('manager', '')}): {ev.get('criterion', '')[:80]}")
            if t.get("opm_seed"):
                lines.append(f"\n**OPM seed**: {t['opm_seed']}")
            return "\n".join(lines)

        summary = data.get("summary", {})
        lines.append(f"- 총 토픽: {summary.get('total_topics', 0)}")
        lines.append(f"- 합의 (consensus 4+): {summary.get('consensus_count', 0)}")
        lines.append(f"- 다수 (majority 3): {summary.get('majority_count', 0)}")
        lines.append(f"- 이견 (divergence): {summary.get('divergence_count', 0)}")
        lines.append(f"- 소수 (minority 1-2): {summary.get('minority_count', 0)}")
        lines.append("")
        lines.append(f"## Topics ({summary.get('total_topics', 0)})")
        for t in data.get("topics", [])[:15]:
            lines.append(
                f"- **{t.get('topic_label', t.get('topic_id', ''))}** "
                f"(`{t.get('agreement_level', '?')}`, {t.get('agreement_count', 0)}명)"
            )
            if t.get("opm_seed"):
                lines.append(f"  - OPM seed: {t['opm_seed'][:120]}")
        return "\n".join(lines)

    # 전체 요약
    managers = data.get("managers", [])
    gs = data.get("global_summary", {})
    lines.append(f"- 분석 대상 운용사: {', '.join(managers)} ({len(managers)}명)")
    lines.append(f"- 총 토픽: {gs.get('total_topics', 0)}")
    lines.append(f"- 합의: {gs.get('consensus_topics', 0)} / 다수: {gs.get('majority_topics', 0)} / 이견: {gs.get('divergence_topics', 0)} / 소수: {gs.get('minority_topics', 0)}")
    lines.append("")
    lines.append("## 카테고리별 요약")
    lines.append("| 카테고리 | 총 토픽 | 합의 | 다수 | 이견 | 소수 |")
    lines.append("|---|---|---|---|---|---|")
    for cat in _CATEGORIES:
        s = data.get("category_summaries", {}).get(cat, {})
        if s:
            lines.append(
                f"| {_CATEGORY_KO.get(cat, cat)} | {s.get('total_topics', 0)} | "
                f"{s.get('consensus_count', 0)} | {s.get('majority_count', 0)} | "
                f"{s.get('divergence_count', 0)} | {s.get('minority_count', 0)} |"
            )
    return "\n".join(lines)


def _render_compare(data: dict[str, Any]) -> str:
    lines = ["# 정책 비교 매트릭스", ""]
    policies = data.get("policies", [])
    lines.append(f"- 비교 정책: {', '.join(policies)} ({len(policies)}개)")
    if data.get("missing"):
        lines.append(f"- 미발견: {', '.join(data['missing'])}")
    lines.append("")

    if data.get("category"):
        cat = data["category"]
        lines.append(f"## 카테고리: {_CATEGORY_KO.get(cat, cat)}")
        for pid, info in data.get("comparison", {}).items():
            lines.append(f"\n### {pid}")
            lines.append(f"- default: `{info.get('default', '?')}`")
            for key, label in [("for", "찬성"), ("against", "반대"), ("review", "검토")]:
                items = info.get(key, [])
                if items:
                    lines.append(f"- **{label} ({len(items)})**")
                    for item in items[:3]:
                        lines.append(f"  - {item.get('criterion', '')[:80]}")
        return "\n".join(lines)

    # 전 카테고리 매트릭스
    matrix = data.get("matrix", {})
    if matrix:
        header = "| 카테고리 | " + " | ".join(policies) + " |"
        sep = "|---|" + "|".join(["---"] * len(policies)) + "|"
        lines.append(header)
        lines.append(sep)
        for cat in _CATEGORIES:
            row = [_CATEGORY_KO.get(cat, cat)]
            for pid in policies:
                cell = matrix.get(cat, {}).get(pid, {})
                d = cell.get("default", "?")[:8]
                a = cell.get("against", 0)
                row.append(f"`{d}` (a={a})")
            lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _render_audit(data: dict[str, Any]) -> str:
    mgr = data.get("manager", "")
    overall = data.get("overall", {})
    lines = [f"# 정책 vs 실제 갭 audit: `{mgr}`", ""]
    lines.append(f"- 정책 type: `{data.get('policy_meta', {}).get('type', '?')}`")
    lines.append(f"- 총 행사: {overall.get('total_votes', 0)}건, against {overall.get('total_against', 0)} ({overall.get('overall_against_rate_pct', 0)}%)")
    lines.append("")
    lines.append("## 카테고리별 갭")
    lines.append("| 카테고리 | votes | for | against | against% | 정책 against | 정책 review | assessment |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for cat in _CATEGORIES:
        g = data.get("gaps", {}).get(cat)
        if not g:
            continue
        lines.append(
            f"| {g.get('category_ko', cat)} | {g.get('total_votes', 0)} | "
            f"{g.get('for_count', 0)} | {g.get('against_count', 0)} | "
            f"**{g.get('against_rate_pct', 0)}%** | {g.get('policy_against_criteria_count', 0)} | "
            f"{g.get('policy_review_criteria_count', 0)} | `{g.get('assessment', '?')}` |"
        )
    lines.append("")
    lines.append("**Assessment 의미**:")
    lines.append("- `policy_strict_practice_lenient`: 정책은 엄격 (3+ against criteria)인데 실제 against rate 5% 미만 — **정책-실제 괴리 큼**")
    lines.append("- `policy_strict_practice_strict`: 정책 엄격 + 실제 against ≥15% — 일관성 있음")
    lines.append("- `policy_lenient_practice_strict`: 정책 약한데 실제 against 적극 — practice가 leading")
    lines.append("- `balanced`: 균형")
    return "\n".join(lines)


def _render_predict(data: dict[str, Any]) -> str:
    lines = [f"# 예측: {data.get('company', '')}", ""]
    lines.append(f"- 안건: {data.get('agenda_title', '')}")
    lines.append(f"- 분류: **{data.get('agenda_category_ko', '?')}** (`{data.get('agenda_category', '?')}`)")
    lines.append(f"- 정책: `{data.get('policy_id', '?')}`")
    lines.append(f"- 정책 default: `{data.get('policy_default', '?')}`")
    if data.get("auto_score_enabled"):
        lines.append("- 자동 채점: ENABLED")
    lines.append("")

    # 자동 채점 결정 (먼저 표시)
    auto_decision = data.get("auto_decision")
    if auto_decision:
        decision = auto_decision.get("decision", "?")
        emoji = {"for": "[FOR]", "against": "[AGAINST]", "review": "[REVIEW]"}.get(decision, "[?]")
        lines.append(f"## OPM 자동 결정: **{emoji} {decision.upper()}**")
        lines.append(f"- 결정 근거: `{auto_decision.get('decision_source', '?')}`")
        lines.append(
            f"- 점수: {auto_decision.get('raw_score', 0)} / {auto_decision.get('max_score', 16)} "
            f"(red {auto_decision.get('red_count', 0)} / yellow {auto_decision.get('yellow_count', 0)} "
            f"/ green {auto_decision.get('green_count', 0)} / unknown {auto_decision.get('unknown_count', 0)})"
        )
        triggered = auto_decision.get("triggered_pattern_ids", [])
        if triggered:
            lines.append(f"- 트리거 빙고: `{', '.join(triggered)}`")
        lines.append("")

    bingo_matches = data.get("bingo_matches", [])
    if bingo_matches:
        lines.append(f"## 매칭된 빙고 패턴 ({len(bingo_matches)})")
        for b in bingo_matches[:5]:
            lines.append(
                f"- **{b.get('pattern_id', '')}** → `{b.get('decision', '?')}` — "
                f"{b.get('rationale', '')[:100]}"
            )
            lines.append(f"  - condition: `{b.get('condition', '')[:100]}`")
        lines.append("")

    # 자동 채점 dim 결과
    matrix_score = data.get("matrix_score")
    if matrix_score:
        scored = matrix_score.get("dimensions_scored", {})
        if scored:
            lines.append("## Dim 채점 결과")
            lines.append("| dim_id | 점수 | 상태 |")
            lines.append("|---|---|---|")
            for dim_id, score in scored.items():
                if score is None:
                    label = "데이터 부족"
                elif score == 0:
                    label = "RED (0)"
                elif score == 1:
                    label = "YELLOW (1)"
                elif score == 2:
                    label = "GREEN (2)"
                else:
                    label = str(score)
                score_str = "-" if score is None else str(score)
                lines.append(f"| `{dim_id}` | {score_str} | {label} |")
            lines.append("")

    # data tool 호출 결과
    data_calls = data.get("data_calls", {})
    if data_calls:
        lines.append("## Data tool 호출 결과")
        for tool, status in data_calls.items():
            lines.append(f"- `{tool}`: `{status}`")
        lines.append("")

    # manual dim 안내
    manual_dims = data.get("manual_dims", [])
    if manual_dims:
        lines.append(f"## Manual 입력 권장 dim ({len(manual_dims)})")
        lines.append("자동 채점 불가 — `matrix_dimensions={\"dim_id\": 0|1|2}` 형태로 사용자 입력 권장:")
        for dim in manual_dims:
            lines.append(f"- `{dim}`")
        lines.append("")

    # 정책 룰
    for key, label in [("policy_for", "찬성 기준"), ("policy_against", "반대 기준"), ("policy_review", "검토 기준")]:
        items = data.get(key, [])
        if items:
            lines.append(f"## 정책: {label} ({len(items)})")
            for item in items[:5]:
                lines.append(f"- {item.get('criterion', '')[:120]}")
            lines.append("")

    matrix = data.get("matrix")
    if matrix:
        lines.append(f"## 매트릭스 정의 (`{data.get('matrix_id', '?')}`)")
        lines.append(f"- dimensions: {len(matrix.get('dimensions', []))} 차원")
        lines.append(f"- bingo patterns: {len(matrix.get('bingo_patterns', []))} 패턴")
        thresholds = matrix.get("scoring", {}).get("thresholds", {})
        if thresholds:
            lines.append(f"- 임계값: for `{thresholds.get('for', '')}` / review `{thresholds.get('review', '')}` / against `{thresholds.get('against', '')}`")

    if data.get("warnings"):
        lines.append("\n## Warnings")
        for w in data["warnings"][:8]:
            lines.append(f"- {w}")

    disclaimer = data.get("disclaimer")
    if disclaimer:
        lines.append(f"\n_{disclaimer}_")

    note = data.get("evaluation_note")
    if note:
        lines.append(f"\n*{note}*")
    return "\n".join(lines)


def _render_nps_record(data: dict[str, Any]) -> str:
    f = data.get("filters", {})
    rows = data.get("matched_rows", [])
    details = data.get("details", [])
    lines = ["# 국민연금 의결권 행사내역", ""]
    lines.append(f"- 회사: `{f.get('company') or '-'}` (ticker `{f.get('ticker') or '-'}`, NPS `{f.get('nps_code') or '-'}`)")
    lines.append(f"- 기간: {f.get('start_date', '?')} ~ {f.get('end_date', '?')} (year `{f.get('year', '?')}`)")
    lines.append(f"- list source: `{data.get('list_source', '?')}` (전체 {data.get('list_total_in_window', 0)}건 중 매칭 **{data.get('matched_count', 0)}건**)")
    lines.append("")

    if rows:
        lines.append("## 매칭 주총")
        lines.append("| 회사 | NPS | ticker | 일자 | 구분 |")
        lines.append("|---|---|---|---|---|")
        for r in rows[:20]:
            lines.append(
                f"| {r.get('company_name', '')} | `{r.get('nps_code', '')}` | "
                f"`{r.get('ticker', '')}` | {r.get('gmos_date', '')} | {r.get('gmos_kind_label', '')} |"
            )
        if len(rows) > 20:
            lines.append(f"\n_... +{len(rows) - 20}건 (필터 좁히면 더 정확)_")
        lines.append("")

    if details:
        lines.append(f"## 안건별 의결권 (상세 {len(details)}건)")
        for d in details:
            company = d.get("company_name", "?")
            gmos = d.get("gmos_date", d.get("gmos_ymd", ""))
            kind = d.get("gmos_kind", d.get("gmos_kind_cd", ""))
            summary = d.get("summary", {})
            lines.append(
                f"\n### {company} — {gmos} ({kind}) — "
                f"총 {summary.get('total', 0)} / 찬성 {summary.get('for', 0)} / 반대 {summary.get('against', 0)} / 기권 {summary.get('abstain', 0)}"
            )
            lines.append("| 의안번호 | 의안내용 | 행사 | 반대시 사유 | 근거조항 |")
            lines.append("|---|---|---|---|---|")
            for it in d.get("items", []):
                title = (it.get("agenda_title", "") or "")[:60]
                reason = (it.get("against_reason", "") or "")[:80]
                clause = (it.get("rule_clause", "") or "")[:30]
                lines.append(
                    f"| {it.get('agenda_no', '')} | {title} | **{it.get('decision_label', '')}** "
                    f"| {reason} | {clause} |"
                )

    if data.get("detail_errors"):
        lines.append(f"\n## detail 오류 ({len(data['detail_errors'])}건)")
        for e in data["detail_errors"][:5]:
            lines.append(f"- {e}")

    note = data.get("ticker_mapping_note")
    if note:
        lines.append(f"\n_매핑: {note}_")
    return "\n".join(lines)


def _render(payload: dict[str, Any]) -> str:
    data = payload.get("data", {})
    scope = data.get("scope", "")
    if scope == "policy":
        return _render_policy(data)
    if scope == "record":
        return _render_record(data)
    if scope == "consensus":
        return _render_consensus(data)
    if scope == "compare":
        return _render_compare(data)
    if scope == "audit":
        return _render_audit(data)
    if scope == "predict":
        return _render_predict(data)
    if scope == "nps_record":
        return _render_nps_record(data)
    return _render_error(payload)


def register_tools(mcp):

    @mcp.tool()
    async def proxy_guideline(
        scope: str = "policy",
        policy_id: str = "open_proxy",
        manager: str = "",
        company: str = "",
        ticker: str = "",
        nps_code: str = "",
        year: int = 0,
        period: str = "",
        start_date: str = "",
        end_date: str = "",
        agenda_category: str = "",
        agenda_title: str = "",
        agenda_type_raw: str = "",
        compare_policies: list[str] | None = None,
        topic_id: str = "",
        matrix_dimensions: dict[str, int] | None = None,
        auto_score: bool = True,
        meeting_date: str = "",
        notice_disclosure_date: str = "",
        extra_agenda_titles: list[str] | None = None,
        fetch_detail: bool = True,
        force_refresh: bool = False,
        max_details: int = 5,
        format: str = "md",
    ) -> str:
        """desc: 자산운용사 의결권 행사 정책 + 행사내역 + Open Proxy Guideline + 12 카테고리 매트릭스 자동 채점 + 국민연금(NPS) 통합 조회. 7 운용사 (mirae_asset/samsung/samsung_active/truston/kim/align_partners/baring) 정책+행사내역 + OPM 자체 모범 정책 (open_proxy) + 국민연금(fund.nps.or.kr 직접 크롤링). predict scope는 12 매트릭스 100 dim 중 ~85 dim 자동 채점 + 빙고 패턴 평가 → for/against/review 자동 결정. 베어링은 ISS Korea 글로벌 표준 직접 채택. 얼라인은 행동주의 펀드.
        when: 운용사 정책 비교, 특정 회사 행사내역 조회, OPM Guideline 안건 적용 (auto_score=True 시 회사 데이터 자동 호출), 합의/이견 분석, 정책 vs 실제 갭 audit, 국민연금 안건별 의결권 행사내역 조회 (캠페인 표 예측 핵심 변수). prepare_vote_before_meeting의 vote_style 옵션 백엔드.
        rule: DART API 호출 0회 (정적 데이터, NPS는 fund.nps.or.kr 크롤링). predict의 auto_score=True는 추가 data tool 호출 (board, corp_gov, ownership 등). 매트릭스 채점 오류 시 conservative review로 fallback. manual dim (adverse_news 등) 명시적 표시.
        scopes:
          - policy: 정책 조회. policy_id 지정 (default open_proxy). agenda_category로 단일 카테고리 상세.
          - record: 운용사 행사내역. manager 필수 + company/year/period/category 필터.
          - predict: 회사·안건 → 정책 적용 예측 + 매트릭스 자동 채점. auto_score=True (기본) 시 ~85 dim 자동 + 빙고 평가. matrix_dimensions로 manual override.
          - compare: N개 정책 비교. compare_policies 리스트 (default 모든 운용사 + open_proxy).
          - consensus: 운용사 합의/이견 분석. agenda_category + topic_id 필터.
          - audit: 정책 vs 실제 행사내역 갭. manager 필수.
          - nps_record: 국민연금 의결권 행사내역. company / ticker / nps_code 중 1개 + year (default 올해). NPS 코드 5자리 + '0' = 표준 6자리 티커.
        ref: open-proxy-guideline, decision-matrix-design, matrix-auto-scoring-2026-04-29, voting-policy-consensus-matrix, nps-voting-disclosure
        """
        payload = await build_proxy_guideline_payload(
            scope=scope,
            policy_id=policy_id,
            manager=manager,
            company=company,
            ticker=ticker,
            nps_code=nps_code,
            year=year,
            period=period,
            start_date=start_date,
            end_date=end_date,
            agenda_category=agenda_category,
            agenda_title=agenda_title,
            agenda_type_raw=agenda_type_raw,
            compare_policies=compare_policies or [],
            topic_id=topic_id,
            matrix_dimensions=matrix_dimensions,
            auto_score=auto_score,
            meeting_date=meeting_date,
            notice_disclosure_date=notice_disclosure_date,
            extra_agenda_titles=extra_agenda_titles,
            fetch_detail=fetch_detail,
            force_refresh=force_refresh,
            max_details=max_details,
        )
        if format == "json":
            return as_pretty_json(payload)
        if payload.get("status") in {"error", "ambiguous"}:
            return _render_error(payload)
        return _render(payload)
