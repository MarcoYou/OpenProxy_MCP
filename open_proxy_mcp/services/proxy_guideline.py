"""v2 proxy_guideline service.

자산운용사 의결권 행사 정책 + 행사내역 + Open Proxy Guideline + 12 매트릭스 통합 조회.

데이터 위치: open_proxy_mcp/data/asset_managers/
  - _index.json (운용사 메타)
  - _consensus_matrix.json (운용사 합의/이견)
  - _decision_matrices.json (12 카테고리 의사결정 매트릭스)
  - policies/{manager_id}_{version}.json (정책)
  - records/{manager_id}_{period}.json (행사내역)

6 scope:
  - policy   : 정책 조회 (default policy_id=open_proxy)
  - record   : 운용사 실제 행사내역
  - predict  : 회사·안건 → 정책 적용 예측 (matrix scoring 추후 확장)
  - compare  : N개 정책 비교 매트릭스
  - consensus: 운용사 합의/이견 분석
  - audit    : 정책 vs 실제 행사내역 갭

데이터는 정적 (실시간 호출 X). DART API 호출 0회 (cross-domain 시만).
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from open_proxy_mcp.services.contracts import (
    AnalysisStatus,
    ToolEnvelope,
    build_usage,
)


_SUPPORTED_SCOPES = {"policy", "record", "predict", "compare", "consensus", "audit"}
_DATA_ROOT = files("open_proxy_mcp.data.asset_managers")


# ── 데이터 로딩 ──


def load_index() -> dict[str, Any]:
    """_index.json — 운용사 메타 + OPM 디폴트."""
    path = _DATA_ROOT / "_index.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(policy_id: str) -> dict[str, Any] | None:
    """정책 조회. policy_id=open_proxy면 OPM 정책, 그 외 운용사 id."""
    if policy_id == "open_proxy":
        candidates = ["open_proxy_v1.json"]
    else:
        # 최신 버전 자동 탐색 (manager_id_*.json 중 가장 최신)
        index = load_index()
        manager_meta = index.get("managers", {}).get(policy_id)
        if not manager_meta:
            return None
        policy_file = manager_meta.get("policy_file", "")
        if not policy_file:
            return None
        candidates = [policy_file.split("/")[-1]]

    policies_dir = _DATA_ROOT / "policies"
    for fname in candidates:
        try:
            return json.loads((policies_dir / fname).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
    return None


def load_records(manager_id: str, period: str = "") -> list[dict[str, Any]]:
    """행사내역 조회. period 지정 없으면 모든 period."""
    records_dir = _DATA_ROOT / "records"
    out = []
    if period:
        path = records_dir / f"{manager_id}_{period}.json"
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            pass
    else:
        # 해당 manager의 모든 period
        for entry in records_dir.iterdir():
            name = entry.name
            if name.startswith(f"{manager_id}_") and name.endswith(".json"):
                out.append(json.loads(entry.read_text(encoding="utf-8")))
    return out


def load_consensus_matrix() -> dict[str, Any]:
    """_consensus_matrix.json — 운용사 합의/이견 분석."""
    path = _DATA_ROOT / "_consensus_matrix.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_decision_matrices() -> dict[str, Any]:
    """_decision_matrices.json — 12 카테고리 의사결정 매트릭스."""
    path = _DATA_ROOT / "_decision_matrices.json"
    return json.loads(path.read_text(encoding="utf-8"))


def list_managers() -> list[str]:
    index = load_index()
    return list(index.get("managers", {}).keys())


# ── 12 카테고리 표준 ──

_CATEGORIES = [
    "financial_statements",
    "cash_dividend",
    "articles_amendment",
    "director_election",
    "audit_committee_election",
    "director_compensation",
    "treasury_share",
    "merger",
    "spin_off",
    "capital_increase_decrease",
    "cb_bw",
    "shareholder_proposal",
]

_CATEGORY_KO = {
    "financial_statements": "재무제표",
    "cash_dividend": "현금배당",
    "articles_amendment": "정관변경",
    "director_election": "이사 선임",
    "audit_committee_election": "감사위원 선임",
    "director_compensation": "이사 보수",
    "treasury_share": "자기주식",
    "merger": "합병",
    "spin_off": "분할",
    "capital_increase_decrease": "유증/감자",
    "cb_bw": "CB/BW",
    "shareholder_proposal": "주주제안",
}


# ── 안건 카테고리 자동 분류 (predict scope) ──


def classify_agenda(agenda_title: str, agenda_type_raw: str = "") -> str:
    """안건명 + 의안유형 → 12 카테고리 매핑.

    우선순위 (위→아래):
    1. 주주제안
    2. 감사위원 (선임/해임 vs 분리선출 정관 변경 분기)
    3. M&A (합병/분할/주식교환)
    4. 희석성 증권 (CB/BW > 유증/감자)
    5. 자기주식
    6. 보수/퇴직금/스톡옵션 ("이사 보수" 등 — director_election보다 먼저)
    7. 이사 선임/해임 (감사위원·보수 다 거른 후)
    8. 정관변경 (명시 + 정관 부속 안건 키워드)
    9. 배당
    10. 재무제표
    """
    text_ko = f"{agenda_type_raw} {agenda_title}"
    text_lower = text_ko.lower()

    if "주주제안" in text_ko:
        return "shareholder_proposal"

    if "감사위원" in text_ko:
        if "분리선출" in text_ko or "분리 선출" in text_ko:
            return "articles_amendment"
        if "선임" in text_ko or "해임" in text_ko or "후보" in text_ko:
            return "audit_committee_election"
        return "audit_committee_election"

    if "합병" in text_ko:
        return "merger"
    if any(k in text_ko for k in ["물적분할", "인적분할", "분할합병"]):
        return "spin_off"
    if "분할" in text_ko and "분리선출" not in text_ko:
        return "spin_off"

    if any(k in text_ko for k in ["전환사채", "신주인수권부사채"]) or "cb" in text_lower or "bw" in text_lower:
        return "cb_bw"
    if any(k in text_ko for k in ["유상증자", "무상증자", "신주발행", "주식분할", "주식병합", "액면분할", "액면병합"]):
        return "capital_increase_decrease"

    if any(k in text_ko for k in ["자기주식", "자사주", "자본감소", "감자"]):
        return "treasury_share"

    # 보수·퇴직금·스톡옵션 (이사 선임보다 먼저)
    if any(k in text_ko for k in [
        "보수한도", "보수승인", "보수액", "이사 보수", "감사 보수", "임원 보수", "임원보수",
        "퇴직금", "퇴직위로금", "퇴직금규정", "퇴직금 지급", "퇴직급여",
        "주식매수선택권", "스톡옵션", "성과급여", "성과급",
    ]):
        return "director_compensation"

    if "이사" in text_ko and ("선임" in text_ko or "해임" in text_ko):
        return "director_election"

    # 정관변경 (명시 + 부속 안건 키워드)
    articles_keywords = [
        "정관",
        "사업목적", "목적사업", "회사명", "상호 변경", "상호변경",
        "본점", "본사 소재", "본점이전",
        "회계연도",
        "전자주주총회", "전자투표", "서면투표",
        "주주총회 소집", "주주총회의 소집", "주주총회 결의",
        "의결권 대리",
        "이사회 규모", "이사회 내 위원회", "이사회 의장", "사외이사 비중",
        "시차임기제", "황금낙하산", "독약처방",
        "사외이사 명칭",
        "집중투표 규정", "집중투표제 도입", "집중투표제 배제",
    ]
    if any(k in text_ko for k in articles_keywords):
        return "articles_amendment"

    if "배당" in text_ko and "주식배당" not in text_ko:
        return "cash_dividend"
    if any(k in text_ko for k in ["재무제표", "결산", "이익잉여금"]):
        return "financial_statements"
    return "other"


# ── Scope: policy ──


def scope_policy(policy_id: str = "open_proxy", agenda_category: str = "") -> dict[str, Any]:
    """정책 조회. agenda_category 지정 시 해당 카테고리만."""
    pol = load_policy(policy_id)
    if not pol:
        return {
            "status": "error",
            "warning": f"정책 미발견: policy_id={policy_id}",
            "available_policies": ["open_proxy"] + list_managers(),
        }

    rules = pol.get("voting_rules", {})
    if agenda_category:
        if agenda_category not in rules:
            return {
                "status": "error",
                "warning": f"카테고리 미발견: {agenda_category}",
                "available_categories": list(rules.keys()),
            }
        return {
            "status": "exact",
            "policy_id": policy_id,
            "policy_meta": pol.get("policy_meta", {}),
            "category": agenda_category,
            "rule": rules[agenda_category],
        }

    return {
        "status": "exact",
        "policy_id": policy_id,
        "policy_meta": pol.get("policy_meta", {}),
        "general_principles": pol.get("general_principles", []),
        "decision_process": pol.get("decision_process", {}),
        "voting_rules_summary": {
            cat: {
                "default": rules.get(cat, {}).get("default", "not_specified"),
                "for_count": len(rules.get(cat, {}).get("for", [])),
                "against_count": len(rules.get(cat, {}).get("against", [])),
                "review_count": len(rules.get(cat, {}).get("review", [])),
            }
            for cat in _CATEGORIES
        },
        "novel_topics": pol.get("novel_topics", {}),
        "korea_specific": pol.get("korea_specific", []),
        "completeness": pol.get("completeness", {}),
    }


# ── Scope: record ──


def scope_record(
    manager: str,
    company: str = "",
    year: int = 0,
    period: str = "",
    agenda_category: str = "",
) -> dict[str, Any]:
    """운용사 실제 행사내역 조회. company/year/period/category 필터 가능."""
    if not manager:
        return {"status": "error", "warning": "manager 필수"}

    records = load_records(manager, period)
    if not records:
        return {
            "status": "error",
            "warning": f"행사내역 미발견: manager={manager}, period={period}",
            "available_managers": list_managers(),
        }

    all_votes = []
    period_summary = []
    for rec in records:
        votes = rec.get("votes", [])
        if company:
            votes = [v for v in votes if company in v.get("company", "")]
        if year:
            votes = [v for v in votes if v.get("meeting_date", "").startswith(str(year))]
        if agenda_category:
            votes = [v for v in votes if v.get("agenda_category") == agenda_category]
        all_votes.extend(votes)
        period_summary.append({
            "period": rec.get("period_label"),
            "filtered_count": len(votes),
            "original_total": rec.get("summary", {}).get("total_votes", 0),
        })

    # 결과 통계
    from collections import Counter
    decisions = Counter(v.get("decision", "") for v in all_votes)
    categories = Counter(v.get("agenda_category", "other") for v in all_votes)
    companies = Counter(v.get("company", "") for v in all_votes)

    return {
        "status": "exact" if all_votes else "partial",
        "manager": manager,
        "filters": {"company": company, "year": year, "period": period, "agenda_category": agenda_category},
        "period_summary": period_summary,
        "total_votes": len(all_votes),
        "decision_breakdown": dict(decisions),
        "category_breakdown": dict(categories.most_common(8)),
        "company_breakdown_top10": dict(companies.most_common(10)),
        "votes": all_votes[:100],  # 최대 100건 (전체 보려면 별도 query)
        "votes_truncated": len(all_votes) > 100,
    }


# ── Scope: consensus ──


def scope_consensus(agenda_category: str = "", topic_id: str = "") -> dict[str, Any]:
    """운용사 합의/이견 분석. category 필터 가능."""
    matrix = load_consensus_matrix()
    cats = matrix.get("categories", {})

    if agenda_category:
        if agenda_category not in cats:
            return {"status": "error", "warning": f"카테고리 미발견: {agenda_category}"}
        cat_data = cats[agenda_category]
        topics = cat_data.get("topics", [])
        if topic_id:
            topic = next((t for t in topics if t.get("topic_id") == topic_id), None)
            if not topic:
                return {"status": "error", "warning": f"topic 미발견: {topic_id}"}
            return {"status": "exact", "category": agenda_category, "topic": topic}
        return {
            "status": "exact",
            "category": agenda_category,
            "summary": cat_data.get("summary", {}),
            "topics": topics,
        }

    return {
        "status": "exact",
        "managers": matrix.get("managers", []),
        "global_summary": matrix.get("global_summary", {}),
        "category_summaries": {
            cat: cats.get(cat, {}).get("summary", {})
            for cat in _CATEGORIES
            if cat in cats
        },
    }


# ── Scope: compare ──


def scope_compare(compare_policies: list[str], agenda_category: str = "") -> dict[str, Any]:
    """N개 정책 비교 매트릭스. policy_id 리스트 받음."""
    if not compare_policies:
        compare_policies = ["open_proxy"] + list_managers()

    loaded = {}
    missing = []
    for pid in compare_policies:
        pol = load_policy(pid)
        if pol:
            loaded[pid] = pol
        else:
            missing.append(pid)

    if not loaded:
        return {"status": "error", "warning": "정책 모두 미발견", "missing": missing}

    if agenda_category:
        comparison = {}
        for pid, pol in loaded.items():
            r = pol.get("voting_rules", {}).get(agenda_category, {})
            comparison[pid] = {
                "default": r.get("default", "not_specified"),
                "for": r.get("for", []),
                "against": r.get("against", []),
                "review": r.get("review", []),
            }
        return {
            "status": "exact",
            "category": agenda_category,
            "policies": list(loaded.keys()),
            "missing": missing,
            "comparison": comparison,
        }

    # 전 카테고리 요약 매트릭스
    matrix = {}
    for cat in _CATEGORIES:
        matrix[cat] = {}
        for pid, pol in loaded.items():
            r = pol.get("voting_rules", {}).get(cat, {})
            matrix[cat][pid] = {
                "default": r.get("default", "not_specified"),
                "for": len(r.get("for", [])),
                "against": len(r.get("against", [])),
                "review": len(r.get("review", [])),
            }

    return {
        "status": "exact",
        "policies": list(loaded.keys()),
        "missing": missing,
        "matrix": matrix,
    }


# ── Scope: audit ──


def scope_audit(manager: str, agenda_category: str = "") -> dict[str, Any]:
    """정책 vs 실제 행사내역 갭 분석.

    - 정책에서 against criterion이 있는 카테고리에서 실제 against rate
    - 정책 충실도 점수 (높을수록 정책-실제 일치)
    """
    if not manager:
        return {"status": "error", "warning": "manager 필수"}

    pol = load_policy(manager)
    records = load_records(manager)
    if not pol or not records:
        return {
            "status": "error",
            "warning": f"정책 또는 행사내역 미발견: manager={manager}",
        }

    all_votes = []
    for rec in records:
        all_votes.extend(rec.get("votes", []))

    # 카테고리별 갭
    rules = pol.get("voting_rules", {})
    gaps = {}
    target_cats = [agenda_category] if agenda_category else _CATEGORIES
    for cat in target_cats:
        cat_votes = [v for v in all_votes if v.get("agenda_category") == cat]
        if not cat_votes:
            continue
        rule = rules.get(cat, {})
        n_total = len(cat_votes)
        n_for = sum(1 for v in cat_votes if v.get("decision") == "for")
        n_against = sum(1 for v in cat_votes if v.get("decision") == "against")
        n_abstain = sum(1 for v in cat_votes if v.get("decision") == "abstain")
        n_not_voted = sum(1 for v in cat_votes if v.get("decision") == "not_voted")
        against_rate = round(n_against / n_total * 100, 1) if n_total else 0.0

        # 정책에 against criterion 갯수
        policy_against_count = len(rule.get("against", []))
        policy_review_count = len(rule.get("review", []))

        # 갭 평가
        if policy_against_count >= 3 and against_rate < 5:
            assessment = "policy_strict_practice_lenient"
        elif policy_against_count >= 3 and against_rate >= 15:
            assessment = "policy_strict_practice_strict"
        elif policy_against_count <= 1 and against_rate >= 15:
            assessment = "policy_lenient_practice_strict"
        else:
            assessment = "balanced"

        gaps[cat] = {
            "category": cat,
            "category_ko": _CATEGORY_KO.get(cat, cat),
            "total_votes": n_total,
            "for_count": n_for,
            "against_count": n_against,
            "abstain_count": n_abstain,
            "not_voted_count": n_not_voted,
            "against_rate_pct": against_rate,
            "policy_against_criteria_count": policy_against_count,
            "policy_review_criteria_count": policy_review_count,
            "assessment": assessment,
        }

    # 전체 통계
    overall_against = sum(g["against_count"] for g in gaps.values())
    overall_total = sum(g["total_votes"] for g in gaps.values())
    overall_against_rate = round(overall_against / overall_total * 100, 1) if overall_total else 0.0

    return {
        "status": "exact",
        "manager": manager,
        "policy_meta": pol.get("policy_meta", {}),
        "overall": {
            "total_votes": overall_total,
            "total_against": overall_against,
            "overall_against_rate_pct": overall_against_rate,
        },
        "gaps": gaps,
    }


# ── Scope: predict ──


def scope_predict(
    company: str,
    agenda_title: str,
    agenda_type_raw: str = "",
    policy_id: str = "open_proxy",
    matrix_dimensions: dict[str, int] | None = None,
) -> dict[str, Any]:
    """회사·안건 → 정책 적용 예측 (간단 버전).

    안건명에서 카테고리 자동 분류 → 해당 정책 룰 + 매트릭스 표시.
    matrix_dimensions가 제공되면 매트릭스 채점 + 빙고 패턴 매칭.

    완전한 예측은 prepare_vote_before_meeting에서 다른 data tool과 결합 필요.
    여기서는 정책 룰 + 매트릭스 구조만 제공.
    """
    pol = load_policy(policy_id)
    if not pol:
        return {"status": "error", "warning": f"정책 미발견: {policy_id}"}

    matrices = load_decision_matrices()

    cat = classify_agenda(agenda_title, agenda_type_raw)
    rule = pol.get("voting_rules", {}).get(cat, {})
    matrix_id = rule.get("matrix_id") or f"matrix_{cat}"
    matrix = matrices.get("matrices", {}).get(matrix_id, {})

    # 매트릭스 채점 (dim 점수 제공된 경우)
    matrix_score = None
    bingo_match = None
    if matrix_dimensions and matrix:
        dims = matrix.get("dimensions", [])
        scored = {}
        for d in dims:
            dim_id = d.get("dim_id")
            if dim_id in matrix_dimensions:
                scored[dim_id] = matrix_dimensions[dim_id]
        raw_score = sum(scored.values())
        max_score = matrix.get("scoring", {}).get("max_score", 16)

        # 빙고 패턴 매칭 (간단 buffer)
        for pattern in matrix.get("bingo_patterns", []):
            cond = pattern.get("condition", "")
            # 패턴 매칭은 문자열 기반 simple — 실제 평가 로직은 별도 인터프리터 필요
            # 일단 패턴 후보 모두 노출
            pass

        matrix_score = {
            "dimensions_scored": scored,
            "raw_score": raw_score,
            "max_score": max_score,
            "thresholds": matrix.get("scoring", {}).get("thresholds", {}),
        }

    return {
        "status": "exact",
        "company": company,
        "agenda_title": agenda_title,
        "agenda_category": cat,
        "agenda_category_ko": _CATEGORY_KO.get(cat, cat),
        "policy_id": policy_id,
        "policy_default": rule.get("default"),
        "policy_for": rule.get("for", []),
        "policy_against": rule.get("against", []),
        "policy_review": rule.get("review", []),
        "matrix_id": matrix_id,
        "matrix": {
            "dimensions": matrix.get("dimensions", []),
            "scoring": matrix.get("scoring", {}),
            "bingo_patterns": matrix.get("bingo_patterns", []),
        } if matrix else None,
        "matrix_score": matrix_score,
        "evaluation_note": "완전한 예측은 prepare_vote_before_meeting에서 회사 상태 + 매트릭스 dim 자동 채점 필요",
    }


# ── 메인 진입점 ──


async def build_proxy_guideline_payload(
    scope: str = "policy",
    policy_id: str = "open_proxy",
    manager: str = "",
    company: str = "",
    year: int = 0,
    period: str = "",
    agenda_category: str = "",
    agenda_title: str = "",
    agenda_type_raw: str = "",
    compare_policies: list[str] | None = None,
    topic_id: str = "",
    matrix_dimensions: dict[str, int] | None = None,
) -> dict[str, Any]:
    """proxy_guideline tool 메인 진입점."""

    if scope not in _SUPPORTED_SCOPES:
        return ToolEnvelope(
            tool="proxy_guideline",
            status=AnalysisStatus.ERROR,
            warnings=[f"지원하지 않는 scope: {scope}. 가능: {sorted(_SUPPORTED_SCOPES)}"],
            data={"usage": build_usage(0)},
        ).to_dict()

    try:
        if scope == "policy":
            data = scope_policy(policy_id, agenda_category)
        elif scope == "record":
            data = scope_record(manager, company, year, period, agenda_category)
        elif scope == "consensus":
            data = scope_consensus(agenda_category, topic_id)
        elif scope == "compare":
            data = scope_compare(compare_policies or [], agenda_category)
        elif scope == "audit":
            data = scope_audit(manager, agenda_category)
        elif scope == "predict":
            data = scope_predict(company, agenda_title, agenda_type_raw, policy_id, matrix_dimensions)
        else:
            data = {"status": "error", "warning": f"unhandled scope: {scope}"}
    except Exception as e:
        return ToolEnvelope(
            tool="proxy_guideline",
            status=AnalysisStatus.ERROR,
            warnings=[f"{type(e).__name__}: {str(e)[:200]}"],
            data={"usage": build_usage(0), "scope": scope},
        ).to_dict()

    status = AnalysisStatus.EXACT
    warnings = []
    if data.get("status") == "error":
        status = AnalysisStatus.ERROR
        warnings.append(data.get("warning", "unknown error"))
    elif data.get("status") == "partial":
        status = AnalysisStatus.PARTIAL

    data["usage"] = build_usage(0)  # DART API 호출 0
    data["scope"] = scope

    subject = ""
    if scope in ("policy", "compare", "predict"):
        subject = policy_id
    elif scope in ("record", "audit"):
        subject = manager
    elif scope == "consensus":
        subject = agenda_category or "all"

    return ToolEnvelope(
        tool="proxy_guideline",
        status=status,
        subject=subject,
        warnings=warnings,
        data=data,
    ).to_dict()
