"""proxy_guideline 자동 채점 모듈 (v1.3, 2026-04-29).

12 매트릭스 × ~8 dim = 100 dim 자동 채점.

채점 모드:
  - auto         : OPM data tool 기반 자동 추출 + 정량 룰
  - heuristic    : 텍스트 패턴 + 휴리스틱 (보수적)
  - manual       : 사용자 input 필수 (adverse_news, ESG strategic 등)

채점 결과:
  - 0 (red), 1 (yellow), 2 (green)
  - None : 데이터 부족 → 빙고 평가 시 conservative skip

빙고 패턴 인터프리터:
  - condition 표현식 파싱 (`dim_a=0 AND dim_b=0`)
  - 점수 dict 평가 → trigger 시 decision 반환
  - 자연어 condition은 best-effort (evaluable한 패턴만 수행)
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from open_proxy_mcp.services.contracts import AnalysisStatus

logger = logging.getLogger(__name__)


# ── 점수 표준 ──

SCORE_GREEN = 2
SCORE_YELLOW = 1
SCORE_RED = 0
SCORE_UNKNOWN = None  # 데이터 부족 → conservative skip


# ── 키워드 사전 (텍스트 패턴 매칭용) ──

_RECENT_EMPLOYMENT_KW = (
    "현)", "(현)", "(現)", "現)", "現 ", "현 ",
    "재직", "근무", "임직원", "직원", "팀장", "본부장", "사장", "부장",
)
_BUSINESS_RELATIONSHIP_KW = (
    "거래", "공급", "납품", "용역", "고문", "자문",
)
_ADVERSE_KW = (
    "배임", "횡령", "분식", "유죄", "기소", "고발", "처벌",
    "회계부정", "회계처리위반", "감리", "조치", "검찰",
)


# ── 헬퍼 ──


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _years_since(date_str: str) -> int | None:
    """'2020.03' / '2020-03-01' / '2020' → 오늘 기준 경과 년수."""
    if not date_str:
        return None
    digits = "".join(ch for ch in str(date_str) if ch.isdigit())
    if len(digits) < 4:
        return None
    try:
        year = int(digits[:4])
        return date.today().year - year
    except ValueError:
        return None


def _career_text(candidate: dict[str, Any]) -> str:
    """후보자 careerDetails 문자열 합치기."""
    parts: list[str] = []
    parts.append(candidate.get("mainJob", "") or "")
    for cd in candidate.get("careerDetails", []) or []:
        parts.append(f"{cd.get('period', '')} {cd.get('content', '')}")
    return " ".join(p for p in parts if p)


# ── matrix_director_election ──


def score_outside_director_independence(candidates: list[dict[str, Any]]) -> int | None:
    """5년 룰 + 거래관계 검증.

    green: 모든 사외이사 후보 5년 내 임직원 X + 거래관계 X
    yellow: 5년 내 1-2년 의심 또는 약한 거래
    red: 5년 내 회사·계열 임직원 또는 명백 거래 관계 (강행규정 §542의8)
    """
    outside_candidates = [
        c for c in candidates
        if "사외" in (c.get("roleType", "") or "")
        or "사외" in (c.get("agenda_title", "") or "")
    ]
    if not outside_candidates:
        # 모든 후보를 사외이사로 가정 못 하면 None
        outside_candidates = candidates
    if not outside_candidates:
        return None

    worst = SCORE_GREEN
    for c in outside_candidates:
        career = _career_text(c)
        # majorShareholderRelation = "있음" / "없음"
        major_relation = (c.get("majorShareholderRelation", "") or "").strip()
        recent3y = (c.get("recent3yTransactions", "") or "").strip()

        red_signal = False
        yellow_signal = False

        # 5년 룰: career에 최근 5년(=2020+) 임직원 표시
        for cd in c.get("careerDetails", []) or []:
            period = cd.get("period", "") or ""
            content = cd.get("content", "") or ""
            yrs_back = _years_since(period.split("~")[0].strip() if period else "")
            if yrs_back is None:
                continue
            if yrs_back <= 5 and any(kw in content for kw in _RECENT_EMPLOYMENT_KW):
                # 회사 자체 또는 계열사 임직원 — 보수적 red
                red_signal = True

        # 거래관계
        if recent3y and recent3y not in ("없음", "-", ""):
            # 거래내역 발견
            if any(kw in recent3y for kw in _BUSINESS_RELATIONSHIP_KW):
                red_signal = True
            else:
                yellow_signal = True

        # 최대주주 관계 명시
        if major_relation and major_relation not in ("없음", "-", "독립"):
            yellow_signal = True

        if red_signal:
            worst = min(worst, SCORE_RED)
        elif yellow_signal:
            worst = min(worst, SCORE_YELLOW)

    return worst


def score_tenure(candidates: list[dict[str, Any]]) -> int | None:
    """사외이사 6년/9년 룰.

    green: ≤5년
    yellow: 5-6년
    red: >6년 (계열사 합산 9년)
    """
    if not candidates:
        return None

    worst = SCORE_GREEN
    found_any = False
    for c in candidates:
        if "사외" not in (c.get("roleType", "") or ""):
            continue
        # careerDetails에서 현 회사 재직 시작 추정
        first_year = None
        for cd in c.get("careerDetails", []) or []:
            period = cd.get("period", "") or ""
            content = cd.get("content", "") or ""
            if any(kw in content for kw in _RECENT_EMPLOYMENT_KW):
                yrs_back = _years_since(period.split("~")[0].strip() if period else "")
                if yrs_back is not None:
                    first_year = max(first_year or 0, yrs_back)
        if first_year is None:
            continue
        found_any = True
        if first_year > 6:
            worst = min(worst, SCORE_RED)
        elif first_year >= 5:
            worst = min(worst, SCORE_YELLOW)

    return worst if found_any else None


def score_concurrent_positions(candidates: list[dict[str, Any]]) -> int | None:
    """겸직 갯수 평가.

    green: 1개 이내 (본인 회사 포함)
    yellow: 2개
    red: 사외이사 3개사 이상 또는 상장사 임원 2개사 이상

    카운트 방식: careerDetails의 "(현)" 표시 항목 수.
    mainJob은 careerDetails에 동일 항목 있으면 중복으로 카운트하지 않음.
    """
    if not candidates:
        return None

    max_count = 0
    for c in candidates:
        # careerDetails에서 (현) 표시 항목 수
        count = 0
        for cd in c.get("careerDetails", []) or []:
            content = (cd.get("content", "") or "")
            if any(kw in content for kw in ("(현)", "현)", "(現)", "現)")):
                count += 1
        # careerDetails 없으면 mainJob 1개로 fallback
        if count == 0 and c.get("mainJob"):
            count = 1
        max_count = max(max_count, count)

    if max_count == 0:
        return None
    if max_count >= 3:
        return SCORE_RED
    if max_count == 2:
        return SCORE_YELLOW
    return SCORE_GREEN


def score_attendance(corp_gov_data: dict[str, Any] | None) -> int | None:
    """이사회 출석률.

    green: ≥90%
    yellow: 75-89%
    red: <75%

    corp_gov_report에서 이사회 출석 관련 metric 우선 사용. 데이터 부족 시 None.
    """
    if not corp_gov_data:
        return None

    # corp_gov_report metrics에서 attendance 라벨 검색
    metrics = corp_gov_data.get("metrics", []) or corp_gov_data.get("metrics_summary", [])
    for m in metrics:
        label = m.get("label", "") or ""
        if "출석" in label or "attendance" in label.lower():
            current = m.get("current", "") or ""
            if current in ("X", "×", "미준수"):
                return SCORE_RED
            if current in ("O", "○", "준수"):
                return SCORE_GREEN
    # 데이터 부족
    return None


def score_adverse_news_manual(score: int | None = None) -> int | None:
    """사용자 input 받는 dim. 자동 채점 안 함."""
    return score


def score_fiduciary_duty_signal(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
) -> int | None:
    """충실의무 §382의3 위반 신호.

    green: 신호 없음
    yellow: 약한 신호 (대주주 우호 패턴)
    red: 명백 위반 신호 (자기거래 + 사외이사 추천 일치, 총수일가 후보)
    """
    yellow = False
    red = False

    if related_party_data:
        # equity_deal 또는 supply_contract 합산
        equity = related_party_data.get("equity_deal", {}) or {}
        supply = related_party_data.get("supply_contract", {}) or {}
        equity_count = len(equity.get("items", []) or [])
        supply_count = len(supply.get("items", []) or [])
        if equity_count > 0 and supply_count > 0:
            yellow = True
        if equity_count >= 3:
            red = True

    if ownership_data:
        related_total = _safe_float(ownership_data.get("summary", {}).get("related_total_pct"))
        if related_total is not None:
            if related_total >= 50:
                yellow = True
            if related_total >= 60:
                red = True
        # control_map 신호
        cm = ownership_data.get("control_map", {}) or {}
        flags = cm.get("flags", {}) or {}
        if flags.get("registry_majority"):
            yellow = True

    if red:
        return SCORE_RED
    if yellow:
        return SCORE_YELLOW
    return SCORE_GREEN if (related_party_data or ownership_data) else None


def score_governance_compliance_rate(corp_gov_data: dict[str, Any] | None) -> int | None:
    """KRX 15원칙 준수율.

    green: ≥80%
    yellow: 60-79%
    red: <60%
    """
    if not corp_gov_data:
        return None
    rate = _safe_float(corp_gov_data.get("compliance_rate"))
    if rate is None:
        # report_meta 안에서도 검색
        meta = corp_gov_data.get("report_meta", {}) or {}
        rate = _safe_float(meta.get("compliance_rate"))
    if rate is None:
        return None
    if rate >= 80:
        return SCORE_GREEN
    if rate >= 60:
        return SCORE_YELLOW
    return SCORE_RED


def score_diversity(board_data: dict[str, Any] | None) -> int | None:
    """이사회 다양성 (성별 + 전문성).

    green: 여성 1명+ + 전문성 다양 (자산 2조원+ 의무)
    yellow: 여성 1명+ 또는 전문성 다양
    red: 둘 다 X
    """
    if not board_data:
        return None
    summary = board_data.get("summary", {}) or board_data.get("board_summary", {})
    female_count = _safe_int(summary.get("female_count"))
    if female_count is None:
        # 후보자 직접 카운트
        appointments = board_data.get("appointments", []) or []
        female_count = 0
        for a in appointments:
            for c in a.get("candidates", []) or []:
                # birthDate 기반 성별 추측 안 함. 별도 필드 없으면 None
                pass
        female_count = None

    if female_count is None:
        return None
    if female_count >= 1:
        return SCORE_GREEN  # 보수적: 여성 1명+ 이상은 일단 green
    return SCORE_RED


def score_bundled_slate_signal(
    appointments: list[dict[str, Any]],
    other_dim_scores: dict[str, int],
) -> int | None:
    """묶음 선임 + 한 명이라도 거버넌스 결격.

    green: 개별 표결 또는 묶음 + 모든 후보 격조 양호
    yellow: 묶음 + 일부 후보 yellow
    red: 묶음 + 한 명이라도 다른 dim red
    """
    if not appointments:
        return None
    bundled = any(len(a.get("candidates", []) or []) >= 2 for a in appointments)
    if not bundled:
        return SCORE_GREEN

    # 다른 dim의 red/yellow signal 활용
    red_count = sum(1 for v in other_dim_scores.values() if v == SCORE_RED)
    yellow_count = sum(1 for v in other_dim_scores.values() if v == SCORE_YELLOW)
    if red_count >= 1:
        return SCORE_RED
    if yellow_count >= 2:
        return SCORE_YELLOW
    return SCORE_GREEN


# ── matrix_director_compensation ──


def score_utilization_rate(comp_data: dict[str, Any] | None) -> int | None:
    """전기 보수한도 소진율.

    green: 70-95% (적정 활용)
    yellow: 50-69% 또는 95-100%
    red: <30% 또는 >100%
    """
    if not comp_data:
        return None
    summary = comp_data.get("compensation_summary", {}) or comp_data.get("summary", {})
    utilization = _safe_float(summary.get("priorUtilization"))
    if utilization is None:
        return None
    if utilization < 30 or utilization > 100:
        return SCORE_RED
    if 70 <= utilization <= 95:
        return SCORE_GREEN
    return SCORE_YELLOW


def score_yoy_change(comp_data: dict[str, Any] | None) -> int | None:
    """전년 대비 한도 변동.

    green: ±10% 이내
    yellow: 10-50% 변동
    red: >50% 인상
    """
    if not comp_data:
        return None
    summary = comp_data.get("compensation_summary", {}) or comp_data.get("summary", {})
    cur = _safe_float(summary.get("currentTotalLimit"))
    prior = _safe_float(summary.get("priorTotalLimit"))
    if cur is None or prior is None or prior <= 0:
        return None
    delta_pct = (cur - prior) / prior * 100
    if abs(delta_pct) <= 10:
        return SCORE_GREEN
    if delta_pct > 50:
        return SCORE_RED
    return SCORE_YELLOW


def score_ceo_pay_ratio_manual(score: int | None = None) -> int | None:
    """CEO 보수/직원 평균 — peer 데이터 미통합. 사용자 input."""
    return score


def score_performance_link_manual(score: int | None = None) -> int | None:
    """TSR 연계 공시 — 텍스트 분석 미통합. 사용자 input."""
    return score


def score_stock_option_dilution(comp_data: dict[str, Any] | None) -> int | None:
    """스톡옵션 희석률.

    green: <2%
    yellow: 2-5%
    red: >5%
    """
    if not comp_data:
        return None
    summary = comp_data.get("compensation_summary", {}) or comp_data.get("summary", {})
    items = comp_data.get("items", []) or []
    # 스톡옵션 희석 정량 데이터가 별도 필드로 추출되지 않은 경우 None
    so_dilution = _safe_float(summary.get("stock_option_dilution_pct"))
    if so_dilution is None:
        # items 텍스트에서 휴리스틱 검색
        for item in items:
            title = (item.get("title", "") or "")
            if "스톡옵션" in title or "주식매수선택권" in title:
                # 정량 정보 없으면 보수적 yellow
                return SCORE_YELLOW
        return None
    if so_dilution > 5:
        return SCORE_RED
    if so_dilution >= 2:
        return SCORE_YELLOW
    return SCORE_GREEN


def score_retirement_pay(agenda_titles: list[str]) -> int | None:
    """퇴직금 황금낙하산 신호.

    green: 변경 없음 또는 표준 범위
    yellow: 10-20% 인상 (정당 사유)
    red: 황금낙하산 또는 연봉 3배 초과
    """
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if any(kw in text for kw in ("황금낙하산", "낙하산")):
        return SCORE_RED
    if "퇴직금" in text or "퇴직위로금" in text:
        # 변경 안건 발견 — 정량 세부 없으면 yellow (보수)
        return SCORE_YELLOW
    return SCORE_GREEN


def score_company_performance_manual(score: int | None = None) -> int | None:
    """적자 + TSR — financial_statements 통합 시 자동화. 현재 manual."""
    return score


def score_clawback_say_on_pay_signal(corp_gov_data: dict[str, Any] | None) -> int | None:
    """Clawback 정책 + Say-on-Pay.

    KRX 15 metrics 또는 보수정책 공시 텍스트에서 추정.
    데이터 부족 시 None.
    """
    if not corp_gov_data:
        return None
    metrics = corp_gov_data.get("metrics", []) or corp_gov_data.get("metrics_summary", [])
    has_clawback = False
    for m in metrics:
        label = m.get("label", "") or ""
        current = m.get("current", "") or ""
        if "최고경영자 승계" in label and current in ("O", "○", "준수"):
            # 승계정책 운영은 부분 신호
            has_clawback = True
    if has_clawback:
        return SCORE_YELLOW
    return SCORE_RED if metrics else None


# ── matrix_articles_amendment ──


def score_shareholder_rights_impact(agenda_titles: list[str]) -> int | None:
    """주주권리 영향.

    green: 주주권 강화 (전자투표, 집중투표, 소집공고 강화)
    yellow: 중립
    red: 주주권 축소
    """
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    pos_kw = ("전자투표", "집중투표", "소집공고", "전자주주총회", "서면투표", "주주제안권")
    neg_kw = ("초다수의결", "황금낙하산", "차등의결권", "시차임기제", "독약처방", "소집청구권 제한")
    has_pos = any(k in text for k in pos_kw)
    has_neg = any(k in text for k in neg_kw)
    if has_neg:
        return SCORE_RED
    if has_pos:
        return SCORE_GREEN
    return SCORE_YELLOW


def score_board_independence(agenda_titles: list[str]) -> int | None:
    """이사회 독립성 영향."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    pos_kw = ("사외이사 비중 확대", "의장-CEO 분리", "선임사외이사", "LID")
    neg_kw = ("사외이사 비중 축소", "시차임기제", "사외이사 명칭")
    if any(k in text for k in neg_kw):
        return SCORE_RED
    if any(k in text for k in pos_kw):
        return SCORE_GREEN
    return SCORE_YELLOW


def score_supermajority_voting(agenda_titles: list[str]) -> int | None:
    """초다수의결 조항."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if "초다수의결" in text and ("도입" in text or "신설" in text):
        return SCORE_RED
    if "초다수의결" in text and ("삭제" in text or "제한" in text):
        return SCORE_GREEN
    return SCORE_YELLOW


def score_anti_takeover_provisions(agenda_titles: list[str]) -> int | None:
    """경영권 방어 조항."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if any(k in text for k in ("황금낙하산", "시차임기제", "차등의결권", "독약처방")):
        return SCORE_RED
    return SCORE_GREEN


def score_disclosure_compliance(
    notice_disclosure_date: str,
    meeting_date: str,
) -> int | None:
    """사전 공시 적정성 (5영업일 표준, KRX 4주 권고).

    green: 4주+ (28일+)
    yellow: 5영업일~4주
    red: 5영업일 미만 (강행규정 §542의4 위반)
    """
    if not notice_disclosure_date or not meeting_date:
        return None
    try:
        n = datetime.strptime(notice_disclosure_date[:10].replace("-", ""), "%Y%m%d").date()
        m = datetime.strptime(meeting_date[:10].replace("-", ""), "%Y%m%d").date()
        delta = (m - n).days
    except Exception:
        return None
    if delta < 5:
        return SCORE_RED
    if delta < 28:
        return SCORE_YELLOW
    return SCORE_GREEN


def score_agm_to_board_shift(agenda_titles: list[str]) -> int | None:
    """주총 → 이사회 결의 사항 이관."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if "이사회 결의" in text and any(k in text for k in ("합병", "분할", "이사 선임", "이사 해임")):
        return SCORE_RED
    if "이사회 결의" in text:
        return SCORE_YELLOW
    return SCORE_GREEN


def score_company_name_change_signal(agenda_titles: list[str]) -> int | None:
    """회사명 변경 신호."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    has_name_change = any(k in text for k in ("회사명", "상호 변경", "상호변경", "사명 변경"))
    if not has_name_change:
        return SCORE_GREEN
    has_royalty = any(k in text for k in ("로열티", "사용료", "브랜드 사용"))
    if has_royalty:
        return SCORE_RED
    return SCORE_YELLOW


def score_korea_2026_law_alignment_articles(agenda_titles: list[str]) -> int | None:
    """2026 신법 부합성 (정관변경)."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    pos_kw = ("전자주총", "독립이사 1/3", "선임사외이사 도입", "집중투표 도입")
    neg_kw = ("집중투표 배제", "집중투표제 배제")
    if any(k in text for k in neg_kw):
        return SCORE_RED
    if any(k in text for k in pos_kw):
        return SCORE_GREEN
    return SCORE_YELLOW


def score_bundled_articles_signal(
    agenda_titles: list[str],
    other_dim_scores: dict[str, int],
) -> int | None:
    """정관변경 묶음 상정 시 부정 조항 우세 평가."""
    text = " ".join(agenda_titles or [])
    if not text or "정관" not in text:
        return None
    bundled = sum(1 for t in agenda_titles or [] if "정관" in t) >= 1 and len(agenda_titles or []) >= 3
    red_count = sum(1 for v in other_dim_scores.values() if v == SCORE_RED)
    if bundled and red_count >= 1:
        return SCORE_RED
    if bundled and any(v == SCORE_YELLOW for v in other_dim_scores.values()):
        return SCORE_YELLOW
    return SCORE_GREEN


# ── matrix_audit_committee_election ──


def score_3pct_rule_compliance(agenda_titles: list[str]) -> int | None:
    """3% 룰 회피 시도 여부."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if "감사위원" in text and "분리선출" in text:
        return SCORE_GREEN
    if "감사위원회 도입" in text or "감사위원회 전환" in text:
        # 회피 시도 가능성
        return SCORE_RED
    return SCORE_YELLOW


def score_separate_election(agenda_titles: list[str]) -> int | None:
    """감사위원 분리선출."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if "분리선출" in text or "분리 선출" in text:
        # 갯수 카운트
        count = text.count("분리선출") + text.count("분리 선출")
        if count >= 2:
            return SCORE_GREEN
        return SCORE_YELLOW
    if "감사위원" in text:
        # 분리선출 없음 - 자산 1조원+ 의무 위반 가능성
        return SCORE_RED
    return None


def score_audit_opinion_history_manual(score: int | None = None) -> int | None:
    """후보자 5년 내 적정 외 감사의견 — 외부 데이터 통합 필요. manual."""
    return score


def score_non_audit_fee_ratio_manual(score: int | None = None) -> int | None:
    """비감사용역/감사용역 비율 — audit_fee_disclosure tool 미통합. manual."""
    return score


def score_independence_5year_audit(candidates: list[dict[str, Any]]) -> int | None:
    """감사위원 5년 룰 + 임직원 검증 — 사외이사와 동일."""
    return score_outside_director_independence(candidates)


def score_financial_expertise(candidates: list[dict[str, Any]]) -> int | None:
    """재무·회계 전문성 (§542의11 ②)."""
    if not candidates:
        return None
    has_expert = False
    expert_kw = ("CPA", "회계사", "재무", "회계학", "경영학 박사", "경영대학", "공인회계사")
    for c in candidates:
        career = _career_text(c)
        if any(kw in career for kw in expert_kw):
            has_expert = True
            break
    if has_expert:
        return SCORE_GREEN
    return SCORE_RED


def score_compliance_rate_audit(corp_gov_data: dict[str, Any] | None) -> int | None:
    """감사위원회 관련 준수율."""
    return score_governance_compliance_rate(corp_gov_data)


# ── matrix_treasury_share ──


def score_burnout_commitment(
    treasury_data: dict[str, Any] | None,
    agenda_titles: list[str],
    meeting_date: str = "",
) -> int | None:
    """1년 내 소각 commitment (2026.03 신법)."""
    text = " ".join(agenda_titles or [])
    if treasury_data:
        events = treasury_data.get("events", []) or []
        cancel = [e for e in events if e.get("event") in ("cancelation", "soak")]
        if cancel:
            return SCORE_GREEN
    if "소각" in text:
        # 의향 표시
        return SCORE_YELLOW
    if "자기주식" in text or "자사주" in text:
        # 자기주식 안건 + 소각 commitment 부재
        return SCORE_RED
    return None


def score_purpose_clarity(agenda_titles: list[str]) -> int | None:
    """취득·처분 목적 명확성."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    pos_kw = ("임직원", "M&A", "주주 환원", "주주환원")
    neg_kw = ("경영권 방어", "단순 보유")
    if any(k in text for k in neg_kw):
        return SCORE_RED
    if any(k in text for k in pos_kw):
        return SCORE_GREEN
    return SCORE_YELLOW


def score_disposal_method(treasury_data: dict[str, Any] | None) -> int | None:
    """처분 방법."""
    if not treasury_data:
        return None
    events = treasury_data.get("events", []) or []
    disposals = [e for e in events if e.get("event") == "disposal_decision"]
    if not disposals:
        return None
    for d in disposals:
        # 제3자 배정 검출
        method = (d.get("method", "") or d.get("disposal_type", "") or "")
        if "제3자" in method or "사모" in method:
            return SCORE_RED
        if "공개시장" in method or "장내" in method:
            return SCORE_GREEN
    return SCORE_YELLOW


def score_disposal_agm_approval_manual(score: int | None = None) -> int | None:
    """처분 주총 승인 — 정관 텍스트 분석 필요. manual."""
    return score


def score_ownership_structure_signal(ownership_data: dict[str, Any] | None) -> int | None:
    """지배주주·우호세력 의결권 강화 신호."""
    if not ownership_data:
        return None
    cm = ownership_data.get("control_map", {}) or {}
    flags = cm.get("flags", {}) or {}
    if flags.get("registry_majority"):
        return SCORE_YELLOW
    return SCORE_GREEN


def score_treasury_share_ratio(ownership_data: dict[str, Any] | None) -> int | None:
    """회사 자사주 비중 (시총 대비).

    green: <3%
    yellow: 3-7%
    red: >7%
    """
    if not ownership_data:
        return None
    summary = ownership_data.get("summary", {}) or {}
    treasury_pct = _safe_float(summary.get("treasury_pct"))
    if treasury_pct is None:
        return None
    if treasury_pct > 7:
        return SCORE_RED
    if treasury_pct >= 3:
        return SCORE_YELLOW
    return SCORE_GREEN


def score_shareholder_return_ratio_manual(score: int | None = None) -> int | None:
    """주주환원율 — 통합 계산 미통합. manual."""
    return score


def score_fiduciary_duty_signal_treasury(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
) -> int | None:
    """자사주 처분 시 충실의무 신호."""
    return score_fiduciary_duty_signal(related_party_data, ownership_data)


# ── matrix_cash_dividend ──


def score_payout_ratio_vs_industry(dividend_data: dict[str, Any] | None) -> int | None:
    """배당성향 vs 동종업계 — peer 데이터 부족 시 history 절대값 기반.

    green: history 5%+ 안정
    yellow: history 변동 또는 1-5%
    red: 0% 또는 미공시
    """
    if not dividend_data:
        return None
    history = dividend_data.get("history", []) or []
    if not history:
        return None
    payout_ratios = [
        _safe_float(h.get("payout_ratio")) for h in history if h.get("payout_ratio") is not None
    ]
    payout_ratios = [r for r in payout_ratios if r is not None]
    if not payout_ratios:
        return SCORE_YELLOW
    avg = sum(payout_ratios) / len(payout_ratios)
    if avg < 5:
        return SCORE_RED
    if avg < 15:
        return SCORE_YELLOW
    return SCORE_GREEN


def score_policy_disclosure_dividend(corp_gov_data: dict[str, Any] | None) -> int | None:
    """배당정책 공시."""
    if not corp_gov_data:
        return None
    metrics = corp_gov_data.get("metrics", []) or corp_gov_data.get("metrics_summary", [])
    for m in metrics:
        label = m.get("label", "") or ""
        current = m.get("current", "") or ""
        if "배당" in label and "예측가능성" in label:
            if current in ("O", "○", "준수"):
                return SCORE_GREEN
            if current in ("X", "×", "미준수"):
                return SCORE_RED
        if "배당" in label and "통지" in label:
            if current in ("O", "○", "준수"):
                return SCORE_GREEN
            if current in ("X", "×", "미준수"):
                return SCORE_YELLOW
    return None


def score_cash_flow_sustainability_manual(score: int | None = None) -> int | None:
    """영업현금흐름 — financial_statements 통합 필요. manual."""
    return score


def score_interim_quarterly_dividend(dividend_data: dict[str, Any] | None) -> int | None:
    """중간/분기 배당 채택."""
    if not dividend_data:
        return None
    signals = dividend_data.get("policy_signals", {}) or {}
    if signals.get("has_quarterly_pattern"):
        return SCORE_GREEN
    history = dividend_data.get("history", []) or []
    has_multi = any(_safe_int(h.get("decision_count")) and h["decision_count"] > 1 for h in history)
    if has_multi:
        return SCORE_GREEN
    return SCORE_YELLOW


def score_dividend_decision_authority_manual(score: int | None = None) -> int | None:
    """배당 결정 주체 — 정관 텍스트 분석. manual."""
    return score


def score_shareholder_return_ratio_dividend(score: int | None = None) -> int | None:
    """주주환원율 (배당 + 자사주). 통합 미가능. manual."""
    return score


def score_controlling_shareholder_signal(ownership_data: dict[str, Any] | None) -> int | None:
    """지배주주 자금화 신호."""
    if not ownership_data:
        return None
    summary = ownership_data.get("summary", {}) or {}
    related = _safe_float(summary.get("related_total_pct"))
    if related is None:
        return None
    if related >= 60:
        return SCORE_RED
    if related >= 30:
        return SCORE_YELLOW
    return SCORE_GREEN


def score_compliance_rate_dividend(corp_gov_data: dict[str, Any] | None) -> int | None:
    """배당 관련 준수율."""
    return score_governance_compliance_rate(corp_gov_data)


# ── matrix_financial_statements ──


def score_audit_opinion_manual(score: int | None = None) -> int | None:
    """감사 의견 — KIND 감사보고서 통합 필요. manual."""
    return score


def score_non_audit_fee_ratio_fs_manual(score: int | None = None) -> int | None:
    """비감사용역 비율. manual."""
    return score


def score_accounting_error_history_manual(score: int | None = None) -> int | None:
    """회계오류 정정공시 — KIND 통합 필요. manual."""
    return score


def score_internal_control_weakness_manual(score: int | None = None) -> int | None:
    """내부통제 평가. manual."""
    return score


def score_auditor_tenure_manual(score: int | None = None) -> int | None:
    """감사인 재직년수. manual."""
    return score


def score_auditor_independence_signal_manual(score: int | None = None) -> int | None:
    """감사인-임원진 관계. manual."""
    return score


def score_fiduciary_duty_signal_fs(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
) -> int | None:
    """재무제표 충실의무 신호."""
    return score_fiduciary_duty_signal(related_party_data, ownership_data)


def score_compliance_disclosure_fs(corp_gov_data: dict[str, Any] | None) -> int | None:
    """재무 관련 준수율."""
    return score_governance_compliance_rate(corp_gov_data)


def score_climate_disclosure_manual(score: int | None = None) -> int | None:
    """TCFD 공시 — esg_disclosure tool 미통합. manual."""
    return score


# ── matrix_merger ──


def score_merger_ratio_fairness_manual(score: int | None = None) -> int | None:
    """합병비율 공정성 — 외부평가 데이터 통합 필요. manual."""
    return score


def score_fairness_opinion_independence_manual(score: int | None = None) -> int | None:
    return score


def score_controlling_shareholder_conflict(ownership_data: dict[str, Any] | None) -> int | None:
    """지배주주 이해상충."""
    if not ownership_data:
        return None
    cm = ownership_data.get("control_map", {}) or {}
    flags = cm.get("flags", {}) or {}
    if flags.get("registry_majority"):
        return SCORE_RED
    if flags.get("registry_over_30pct"):
        return SCORE_YELLOW
    return SCORE_GREEN


def score_MoM_simulation_manual(score: int | None = None) -> int | None:
    """MoM 시뮬레이션 — 시뮬레이션 결과 없으면 manual."""
    return score


def score_synergy_clarity_manual(score: int | None = None) -> int | None:
    """시너지 명확성 — LLM 분석 필요. manual."""
    return score


def score_appraisal_right_manual(score: int | None = None) -> int | None:
    """매수청구권 가격 — 텍스트 분석 필요. manual."""
    return score


def score_anti_takeover_signal_merger(agenda_titles: list[str]) -> int | None:
    """왕관보석/그린메일 신호."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if any(k in text for k in ("왕관보석", "그린메일", "자진 상장폐지", "자진상장폐지")):
        return SCORE_RED
    return SCORE_GREEN


def score_stakeholder_impact_manual(score: int | None = None) -> int | None:
    return score


# ── matrix_spin_off ──


def score_subsidiary_listing_plan_manual(score: int | None = None) -> int | None:
    return score


def score_split_method(agenda_titles: list[str]) -> int | None:
    """인적 vs 물적분할."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    has_physical = "물적분할" in text
    has_personal = "인적분할" in text
    has_sweetener = "신주 우선 청약권" in text or "우선청약권" in text
    if has_physical and not has_sweetener:
        return SCORE_RED
    if has_physical and has_sweetener:
        return SCORE_YELLOW
    if has_personal:
        return SCORE_GREEN
    return None


def score_minority_shareholder_protection_manual(score: int | None = None) -> int | None:
    return score


def score_fairness_evaluation_manual(score: int | None = None) -> int | None:
    return score


def score_purpose_clarity_spin(agenda_titles: list[str]) -> int | None:
    """분할 목적."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    pos_kw = ("사업 분리", "전문화")
    neg_kw = ("지배주주", "지주회사")
    if any(k in text for k in neg_kw):
        return SCORE_RED
    if any(k in text for k in pos_kw):
        return SCORE_GREEN
    return SCORE_YELLOW


def score_fiduciary_duty_signal_spin(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
) -> int | None:
    return score_fiduciary_duty_signal(related_party_data, ownership_data)


def score_korea_2026_law_compliance_spin_manual(score: int | None = None) -> int | None:
    """2026.07 신법 — 자산 + 면제사유 분석 필요. manual."""
    return score


def score_info_disclosure_spin_manual(score: int | None = None) -> int | None:
    return score


# ── matrix_capital_increase_decrease ──


def score_issuance_size_manual(score: int | None = None) -> int | None:
    """발행예정주식수 증가율 — share_authorization 데이터 필요. manual."""
    return score


def score_preemptive_right(agenda_titles: list[str]) -> int | None:
    """신주인수권 보장."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if "주주배정" in text or "주주 배정" in text:
        return SCORE_GREEN
    if "제3자 배정" in text or "제3자배정" in text:
        return SCORE_YELLOW
    if "신주인수권 배제" in text:
        return SCORE_RED
    return None


def score_anti_takeover_signal_capital(agenda_titles: list[str]) -> int | None:
    """경영권 방어 신호."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if "경영권 분쟁" in text and "신주발행" in text:
        return SCORE_RED
    return SCORE_GREEN


def score_issuance_purpose_manual(score: int | None = None) -> int | None:
    return score


def score_issuance_price_manual(score: int | None = None) -> int | None:
    return score


def score_capital_decrease_type(agenda_titles: list[str]) -> int | None:
    """자본감소 유형."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if "무상감자" in text:
        # 정당 사유 없으면 red
        if "회생" not in text and "구조조정" not in text:
            return SCORE_RED
        return SCORE_YELLOW
    if "유상감자" in text:
        return SCORE_GREEN
    if "감자" in text:
        return SCORE_YELLOW
    return None


def score_fiduciary_duty_signal_capital(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
) -> int | None:
    return score_fiduciary_duty_signal(related_party_data, ownership_data)


def score_disclosure_compliance_capital(
    notice_disclosure_date: str,
    meeting_date: str,
) -> int | None:
    return score_disclosure_compliance(notice_disclosure_date, meeting_date)


# ── matrix_cb_bw ──


def score_agm_resolution_cb_manual(score: int | None = None) -> int | None:
    """주총 결의 정관 채택 — 정관 분석 필요. manual."""
    return score


def score_dilution_rate_cb_manual(score: int | None = None) -> int | None:
    return score


def score_refixing_clause_cb_manual(score: int | None = None) -> int | None:
    return score


def score_call_option_cb_manual(score: int | None = None) -> int | None:
    return score


def score_third_party_independence_cb_manual(score: int | None = None) -> int | None:
    return score


def score_conversion_price_cb_manual(score: int | None = None) -> int | None:
    return score


def score_issuance_purpose_cb_manual(score: int | None = None) -> int | None:
    return score


def score_fiduciary_duty_signal_cb(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
) -> int | None:
    return score_fiduciary_duty_signal(related_party_data, ownership_data)


# ── matrix_shareholder_proposal ──


def score_esg_sustainability(agenda_titles: list[str]) -> int | None:
    """ESG/지속가능성 강화 안건."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    if any(k in text for k in ("TCFD", "Net-zero", "넷제로", "탄소중립", "다양성")):
        return SCORE_GREEN
    if any(k in text for k in ("ESG", "지속가능", "환경")):
        return SCORE_YELLOW
    return SCORE_RED


def score_minority_shareholder_protection_proposal(agenda_titles: list[str]) -> int | None:
    """소수주주 권리 강화 안건."""
    text = " ".join(agenda_titles or [])
    if not text:
        return None
    pos_kw = ("분리선출", "신주발행 주총 승인", "주주 정보권")
    if any(k in text for k in pos_kw):
        return SCORE_GREEN
    return SCORE_YELLOW


def score_long_term_value_alignment_manual(score: int | None = None) -> int | None:
    return score


def score_controlling_shareholder_conflict_proposal(ownership_data: dict[str, Any] | None) -> int | None:
    """제안자 이해상충."""
    return score_controlling_shareholder_conflict(ownership_data)


def score_board_proposal_competition_manual(score: int | None = None) -> int | None:
    return score


def score_proposer_independence_manual(score: int | None = None) -> int | None:
    return score


def score_non_implementation_history_manual(score: int | None = None) -> int | None:
    return score


def score_korea_specific_dispute_manual(score: int | None = None) -> int | None:
    return score


def score_active_engagement_signal(agenda_category: str) -> int | None:
    """행동주의 적극 행사 원칙.

    중대 사항(합병/영업양수도/임원/정관변경) → red (silent 금지)
    일반 routine → green
    """
    critical = {"merger", "spin_off", "director_election", "audit_committee_election", "articles_amendment"}
    middle = {"director_compensation", "treasury_share", "capital_increase_decrease", "cb_bw"}
    routine = {"financial_statements", "cash_dividend"}

    if agenda_category in critical:
        return SCORE_RED  # silent 금지 트리거
    if agenda_category in middle:
        return SCORE_YELLOW
    return SCORE_GREEN


# ── 빙고 패턴 인터프리터 ──


_CONDITION_RE = re.compile(r"(\w+)\s*(=|≥|≤|<|>)\s*(-?\d+)")


def _parse_condition_clause(
    clause: str,
    scores: dict[str, int],
    *,
    excluded_dims: set[str] | None = None,
) -> bool | None:
    """간단 표현식 평가 (`dim_id=0`, `dim_id≥1`).

    반환: True/False, 또는 None (평가 불가).
    excluded_dims: "others ≥1" 같은 표현에서 제외할 dim 집합.
    """
    clause = clause.strip()
    if not clause:
        return None
    excluded = excluded_dims or set()
    # 자연어 (`모든 dim = 2` 등) — best-effort
    compact = clause.replace(" ", "")
    if "모든dim" in compact and "=2" in compact:
        return all(v == 2 for v in scores.values()) if scores else None
    if ("모든dim" in compact or "모든dim" in compact) and "≥1" in compact:
        return all(v >= 1 for v in scores.values()) if scores else None
    if "others" in clause.lower():
        # "others ≥1" — 이미 매칭 처리한 dim (excluded) 제외하고 나머지 모두 ≥1
        target = {k: v for k, v in scores.items() if k not in excluded}
        if not target:
            return True  # 다른 dim 없으면 vacuously true
        if "≥1" in compact or ">=1" in compact:
            return all(v >= 1 for v in target.values())
        if "=2" in compact:
            return all(v == 2 for v in target.values())
        return None
    # "안건일 ≥ 2026-03-06" 등 시점 조건 — 평가 불가, 호출자에서 처리
    if "안건일" in clause or "안건이" in clause or "회사" in clause or "자산" in clause:
        return None

    m = _CONDITION_RE.search(clause)
    if not m:
        return None
    dim_id, op, val_str = m.group(1), m.group(2), m.group(3)
    try:
        val = int(val_str)
    except ValueError:
        return None
    if dim_id not in scores:
        return None
    actual = scores[dim_id]
    if op == "=":
        return actual == val
    if op in ("≥", ">="):
        return actual >= val
    if op in ("≤", "<="):
        return actual <= val
    if op == "<":
        return actual < val
    if op == ">":
        return actual > val
    return None


def evaluate_bingo_pattern(
    pattern: dict[str, Any],
    scores: dict[str, int],
    *,
    agenda_date: str | None = None,
    agenda_category: str | None = None,
) -> tuple[bool, str | None]:
    """단일 빙고 패턴 평가.

    Returns:
        (matched, reason). matched=True면 패턴 트리거. reason은 매칭 근거 또는 skip 사유.
    """
    condition = pattern.get("condition", "") or ""
    if not condition:
        return (False, "no condition")

    # 시점 조건 (안건일 ≥ YYYY-MM-DD)
    date_match = re.search(r"안건일\s*≥\s*(\d{4}-\d{2}-\d{2})", condition)
    date_ok = True
    if date_match:
        if not agenda_date:
            return (False, "agenda_date not provided for time-conditional pattern")
        try:
            threshold = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
            d = datetime.strptime(agenda_date[:10], "%Y-%m-%d").date()
            date_ok = d >= threshold
        except Exception:
            date_ok = False

    # 카테고리 조건 (안건이 ...)
    cat_ok = True
    if "안건이" in condition:
        if not agenda_category:
            return (False, "agenda_category required")
        # 휴리스틱 매핑
        cat_kw = {
            "사외이사 선임": ("director_election",),
            "이사·감사 선임": ("director_election", "audit_committee_election"),
            "보수한도": ("director_compensation",),
            "정관 변경": ("articles_amendment",),
            "director_election": ("director_election",),
        }
        cat_ok = False
        for kw, cats in cat_kw.items():
            if kw in condition and agenda_category in cats:
                cat_ok = True
                break
        if not cat_ok and "director_election과 연계" in condition:
            cat_ok = agenda_category == "director_election"

    # 조건절 분리 (AND)
    # "AND" 또는 " AND " 단위로 split
    clauses = re.split(r"\s+AND\s+", condition, flags=re.IGNORECASE)

    # 첫 패스: dim_id 명시 절에서 사용된 dim 집합 추출 (others 평가용)
    matched_dims: set[str] = set()
    for clause in clauses:
        m = _CONDITION_RE.search(clause)
        if m:
            matched_dims.add(m.group(1))

    all_clauses_pass = True
    evaluated_count = 0
    for clause in clauses:
        # 시점 조건 / 카테고리 조건은 위에서 처리, 여기서 skip
        if "안건일" in clause or "안건이" in clause:
            continue
        # 회사 속성 조건 (자산 ≥ 2조원) — 평가 불가
        if "자산" in clause or "회사" in clause:
            # 보수적 skip — pattern miss
            return (False, f"unevaluable clause: {clause.strip()}")
        result = _parse_condition_clause(clause, scores, excluded_dims=matched_dims)
        if result is None:
            return (False, f"unevaluable clause: {clause.strip()}")
        evaluated_count += 1
        if not result:
            all_clauses_pass = False
            break

    if evaluated_count == 0:
        return (False, "no evaluable clause")

    matched = all_clauses_pass and date_ok and cat_ok
    return (matched, "matched" if matched else "score mismatch")


def evaluate_all_bingo_patterns(
    matrix: dict[str, Any],
    scores: dict[str, int],
    *,
    agenda_date: str | None = None,
    agenda_category: str | None = None,
) -> list[dict[str, Any]]:
    """매트릭스의 모든 빙고 패턴 평가."""
    out: list[dict[str, Any]] = []
    for pattern in matrix.get("bingo_patterns", []) or []:
        matched, reason = evaluate_bingo_pattern(
            pattern, scores,
            agenda_date=agenda_date, agenda_category=agenda_category,
        )
        if matched:
            out.append({
                "pattern_id": pattern.get("pattern_id", ""),
                "decision": pattern.get("decision", ""),
                "condition": pattern.get("condition", ""),
                "rationale": pattern.get("rationale", ""),
                "matched": True,
            })
    return out


# ── 점수 합산 + 임계값 매핑 ──


def aggregate_score_to_decision(
    scores: dict[str, int],
    matrix: dict[str, Any],
    bingo_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    """점수 + 빙고 매칭 → for/against/review 결정.

    빙고 우선:
      - against 빙고 1+ → against
      - for 빙고 1+ AND against 빙고 0 → for (보수적 — review pattern 있으면 review)
      - review 빙고 1+ → review

    점수 fallback:
      - 모든 dim ≥1 + total ≥12 → for
      - 2+ dim red 또는 total ≤7 → against
      - else → review
    """
    valid_scores = {k: v for k, v in scores.items() if v is not None}
    raw_score = sum(valid_scores.values())
    total_dims = len(matrix.get("dimensions", []) or [])
    max_score = total_dims * 2

    red_count = sum(1 for v in valid_scores.values() if v == 0)
    none_count = sum(1 for v in scores.values() if v is None)

    decision = None
    decision_source = ""
    triggered_pattern_ids: list[str] = []

    # 빙고 우선
    against_bingos = [b for b in bingo_matches if b["decision"] == "against"]
    review_bingos = [b for b in bingo_matches if b["decision"] == "review"]
    for_bingos = [b for b in bingo_matches if b["decision"] == "for"]

    if against_bingos:
        decision = "against"
        decision_source = "bingo_against"
        triggered_pattern_ids = [b["pattern_id"] for b in against_bingos]
    elif review_bingos:
        decision = "review"
        decision_source = "bingo_review"
        triggered_pattern_ids = [b["pattern_id"] for b in review_bingos]
    elif for_bingos and not against_bingos:
        decision = "for"
        decision_source = "bingo_for"
        triggered_pattern_ids = [b["pattern_id"] for b in for_bingos]

    # 점수 기반 fallback
    if decision is None:
        # against thresholds
        if red_count >= 2:
            decision = "against"
            decision_source = "score_red_2plus"
        elif valid_scores and raw_score <= 7 and none_count <= total_dims / 3:
            # 데이터 충분 + 점수 낮으면 against
            decision = "against"
            decision_source = "score_low"
        elif valid_scores and raw_score >= 12 and red_count == 0 and not any(v is None for v in scores.values()):
            decision = "for"
            decision_source = "score_high"
        else:
            decision = "review"
            decision_source = "score_mid"

    # 안전망: 데이터 부족 (none_count 절반 이상) → review로 강제 (unknown으로 결정 못 함)
    if none_count >= total_dims / 2 and decision in ("for", "against"):
        # 단, 빙고 트리거된 경우는 강한 신호이므로 유지
        if not triggered_pattern_ids:
            decision = "review"
            decision_source += "_conservative_unknown"

    return {
        "decision": decision,
        "decision_source": decision_source,
        "triggered_pattern_ids": triggered_pattern_ids,
        "raw_score": raw_score,
        "max_score": max_score,
        "red_count": red_count,
        "yellow_count": sum(1 for v in valid_scores.values() if v == 1),
        "green_count": sum(1 for v in valid_scores.values() if v == 2),
        "unknown_count": none_count,
        "scored_dim_count": len(valid_scores),
        "total_dim_count": total_dims,
    }


# ── 카테고리별 자동 채점 dispatch ──


def auto_score_director_election(
    candidates: list[dict[str, Any]],
    appointments: list[dict[str, Any]],
    corp_gov_data: dict[str, Any] | None,
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    """matrix_director_election 자동 채점."""
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}

    scores["outside_director_independence"] = score_outside_director_independence(candidates)
    scores["tenure"] = score_tenure(candidates)
    scores["concurrent_positions"] = score_concurrent_positions(candidates)
    scores["attendance"] = score_attendance(corp_gov_data)
    scores["adverse_news"] = score_adverse_news_manual(user_dimensions.get("adverse_news"))
    scores["fiduciary_duty_signal"] = score_fiduciary_duty_signal(related_party_data, ownership_data)
    scores["governance_compliance_rate"] = score_governance_compliance_rate(corp_gov_data)
    scores["diversity"] = score_diversity({"appointments": appointments, "summary": {}})
    # bundled은 다른 dim 점수 알아야 함 → 마지막
    other_scores = {k: v for k, v in scores.items() if v is not None}
    scores["bundled_slate_signal"] = score_bundled_slate_signal(appointments, other_scores)

    # user override
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v

    return scores


def auto_score_director_compensation(
    comp_data: dict[str, Any] | None,
    agenda_titles: list[str],
    corp_gov_data: dict[str, Any] | None,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["utilization_rate"] = score_utilization_rate(comp_data)
    scores["yoy_change"] = score_yoy_change(comp_data)
    scores["ceo_pay_ratio"] = score_ceo_pay_ratio_manual(user_dimensions.get("ceo_pay_ratio"))
    scores["performance_link"] = score_performance_link_manual(user_dimensions.get("performance_link"))
    scores["stock_option_dilution"] = score_stock_option_dilution(comp_data)
    scores["retirement_pay"] = score_retirement_pay(agenda_titles)
    scores["company_performance"] = score_company_performance_manual(user_dimensions.get("company_performance"))
    scores["clawback_say_on_pay_signal"] = score_clawback_say_on_pay_signal(corp_gov_data)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_articles_amendment(
    agenda_titles: list[str],
    notice_disclosure_date: str,
    meeting_date: str,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["shareholder_rights_impact"] = score_shareholder_rights_impact(agenda_titles)
    scores["board_independence"] = score_board_independence(agenda_titles)
    scores["supermajority_voting"] = score_supermajority_voting(agenda_titles)
    scores["anti_takeover_provisions"] = score_anti_takeover_provisions(agenda_titles)
    scores["disclosure_compliance"] = score_disclosure_compliance(notice_disclosure_date, meeting_date)
    scores["agm_to_board_shift"] = score_agm_to_board_shift(agenda_titles)
    scores["company_name_change_signal"] = score_company_name_change_signal(agenda_titles)
    scores["korea_2026_law_alignment"] = score_korea_2026_law_alignment_articles(agenda_titles)
    other_scores = {k: v for k, v in scores.items() if v is not None}
    scores["bundled_articles_signal"] = score_bundled_articles_signal(agenda_titles, other_scores)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_audit_committee_election(
    candidates: list[dict[str, Any]],
    agenda_titles: list[str],
    corp_gov_data: dict[str, Any] | None,
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["3pct_rule_compliance"] = score_3pct_rule_compliance(agenda_titles)
    scores["separate_election"] = score_separate_election(agenda_titles)
    scores["audit_opinion_history"] = score_audit_opinion_history_manual(user_dimensions.get("audit_opinion_history"))
    scores["non_audit_fee_ratio"] = score_non_audit_fee_ratio_manual(user_dimensions.get("non_audit_fee_ratio"))
    scores["independence_5year"] = score_independence_5year_audit(candidates)
    scores["financial_expertise"] = score_financial_expertise(candidates)
    scores["fiduciary_duty_signal"] = score_fiduciary_duty_signal(related_party_data, ownership_data)
    scores["compliance_rate"] = score_compliance_rate_audit(corp_gov_data)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_treasury_share(
    treasury_data: dict[str, Any] | None,
    agenda_titles: list[str],
    ownership_data: dict[str, Any] | None,
    related_party_data: dict[str, Any] | None,
    meeting_date: str = "",
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["burnout_commitment"] = score_burnout_commitment(treasury_data, agenda_titles, meeting_date)
    scores["purpose_clarity"] = score_purpose_clarity(agenda_titles)
    scores["disposal_method"] = score_disposal_method(treasury_data)
    scores["disposal_agm_approval"] = score_disposal_agm_approval_manual(user_dimensions.get("disposal_agm_approval"))
    scores["ownership_structure_signal"] = score_ownership_structure_signal(ownership_data)
    scores["treasury_share_ratio"] = score_treasury_share_ratio(ownership_data)
    scores["shareholder_return_ratio"] = score_shareholder_return_ratio_manual(user_dimensions.get("shareholder_return_ratio"))
    scores["fiduciary_duty_signal"] = score_fiduciary_duty_signal_treasury(related_party_data, ownership_data)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_cash_dividend(
    dividend_data: dict[str, Any] | None,
    corp_gov_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["payout_ratio_vs_industry"] = score_payout_ratio_vs_industry(dividend_data)
    scores["policy_disclosure"] = score_policy_disclosure_dividend(corp_gov_data)
    scores["cash_flow_sustainability"] = score_cash_flow_sustainability_manual(user_dimensions.get("cash_flow_sustainability"))
    scores["interim_quarterly_dividend"] = score_interim_quarterly_dividend(dividend_data)
    scores["dividend_decision_authority"] = score_dividend_decision_authority_manual(user_dimensions.get("dividend_decision_authority"))
    scores["shareholder_return_ratio"] = score_shareholder_return_ratio_dividend(user_dimensions.get("shareholder_return_ratio"))
    scores["controlling_shareholder_signal"] = score_controlling_shareholder_signal(ownership_data)
    scores["compliance_rate"] = score_compliance_rate_dividend(corp_gov_data)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_financial_statements(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
    corp_gov_data: dict[str, Any] | None,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["audit_opinion"] = score_audit_opinion_manual(user_dimensions.get("audit_opinion"))
    scores["non_audit_fee_ratio"] = score_non_audit_fee_ratio_fs_manual(user_dimensions.get("non_audit_fee_ratio"))
    scores["accounting_error_history"] = score_accounting_error_history_manual(user_dimensions.get("accounting_error_history"))
    scores["internal_control_weakness"] = score_internal_control_weakness_manual(user_dimensions.get("internal_control_weakness"))
    scores["auditor_tenure"] = score_auditor_tenure_manual(user_dimensions.get("auditor_tenure"))
    scores["auditor_independence_signal"] = score_auditor_independence_signal_manual(user_dimensions.get("auditor_independence_signal"))
    scores["fiduciary_duty_signal"] = score_fiduciary_duty_signal_fs(related_party_data, ownership_data)
    scores["compliance_disclosure"] = score_compliance_disclosure_fs(corp_gov_data)
    scores["climate_disclosure"] = score_climate_disclosure_manual(user_dimensions.get("climate_disclosure"))
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_merger(
    ownership_data: dict[str, Any] | None,
    agenda_titles: list[str],
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["merger_ratio_fairness"] = score_merger_ratio_fairness_manual(user_dimensions.get("merger_ratio_fairness"))
    scores["fairness_opinion_independence"] = score_fairness_opinion_independence_manual(user_dimensions.get("fairness_opinion_independence"))
    scores["controlling_shareholder_conflict"] = score_controlling_shareholder_conflict(ownership_data)
    scores["MoM_simulation"] = score_MoM_simulation_manual(user_dimensions.get("MoM_simulation"))
    scores["synergy_clarity"] = score_synergy_clarity_manual(user_dimensions.get("synergy_clarity"))
    scores["appraisal_right"] = score_appraisal_right_manual(user_dimensions.get("appraisal_right"))
    scores["anti_takeover_signal"] = score_anti_takeover_signal_merger(agenda_titles)
    scores["stakeholder_impact"] = score_stakeholder_impact_manual(user_dimensions.get("stakeholder_impact"))
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_spin_off(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
    agenda_titles: list[str],
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["subsidiary_listing_plan"] = score_subsidiary_listing_plan_manual(user_dimensions.get("subsidiary_listing_plan"))
    scores["split_method"] = score_split_method(agenda_titles)
    scores["minority_shareholder_protection"] = score_minority_shareholder_protection_manual(user_dimensions.get("minority_shareholder_protection"))
    scores["fairness_evaluation"] = score_fairness_evaluation_manual(user_dimensions.get("fairness_evaluation"))
    scores["purpose_clarity"] = score_purpose_clarity_spin(agenda_titles)
    scores["fiduciary_duty_signal"] = score_fiduciary_duty_signal_spin(related_party_data, ownership_data)
    scores["korea_2026_law_compliance"] = score_korea_2026_law_compliance_spin_manual(user_dimensions.get("korea_2026_law_compliance"))
    scores["info_disclosure"] = score_info_disclosure_spin_manual(user_dimensions.get("info_disclosure"))
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_capital_increase_decrease(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
    agenda_titles: list[str],
    notice_disclosure_date: str,
    meeting_date: str,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["issuance_size"] = score_issuance_size_manual(user_dimensions.get("issuance_size"))
    scores["preemptive_right"] = score_preemptive_right(agenda_titles)
    scores["anti_takeover_signal"] = score_anti_takeover_signal_capital(agenda_titles)
    scores["issuance_purpose"] = score_issuance_purpose_manual(user_dimensions.get("issuance_purpose"))
    scores["issuance_price"] = score_issuance_price_manual(user_dimensions.get("issuance_price"))
    scores["capital_decrease_type"] = score_capital_decrease_type(agenda_titles)
    scores["fiduciary_duty_signal"] = score_fiduciary_duty_signal_capital(related_party_data, ownership_data)
    scores["disclosure_compliance"] = score_disclosure_compliance_capital(notice_disclosure_date, meeting_date)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_cb_bw(
    related_party_data: dict[str, Any] | None,
    ownership_data: dict[str, Any] | None,
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["agm_resolution"] = score_agm_resolution_cb_manual(user_dimensions.get("agm_resolution"))
    scores["dilution_rate"] = score_dilution_rate_cb_manual(user_dimensions.get("dilution_rate"))
    scores["refixing_clause"] = score_refixing_clause_cb_manual(user_dimensions.get("refixing_clause"))
    scores["call_option"] = score_call_option_cb_manual(user_dimensions.get("call_option"))
    scores["third_party_independence"] = score_third_party_independence_cb_manual(user_dimensions.get("third_party_independence"))
    scores["conversion_price"] = score_conversion_price_cb_manual(user_dimensions.get("conversion_price"))
    scores["issuance_purpose"] = score_issuance_purpose_cb_manual(user_dimensions.get("issuance_purpose"))
    scores["fiduciary_duty_signal"] = score_fiduciary_duty_signal_cb(related_party_data, ownership_data)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


def auto_score_shareholder_proposal(
    ownership_data: dict[str, Any] | None,
    agenda_titles: list[str],
    agenda_category_for_engagement: str = "",
    user_dimensions: dict[str, int] | None = None,
) -> dict[str, int | None]:
    user_dimensions = user_dimensions or {}
    scores: dict[str, int | None] = {}
    scores["esg_sustainability"] = score_esg_sustainability(agenda_titles)
    scores["minority_shareholder_protection"] = score_minority_shareholder_protection_proposal(agenda_titles)
    scores["long_term_value_alignment"] = score_long_term_value_alignment_manual(user_dimensions.get("long_term_value_alignment"))
    scores["controlling_shareholder_conflict"] = score_controlling_shareholder_conflict_proposal(ownership_data)
    scores["board_proposal_competition"] = score_board_proposal_competition_manual(user_dimensions.get("board_proposal_competition"))
    scores["proposer_independence"] = score_proposer_independence_manual(user_dimensions.get("proposer_independence"))
    scores["non_implementation_history"] = score_non_implementation_history_manual(user_dimensions.get("non_implementation_history"))
    scores["korea_specific_dispute"] = score_korea_specific_dispute_manual(user_dimensions.get("korea_specific_dispute"))
    scores["active_engagement_signal"] = score_active_engagement_signal(agenda_category_for_engagement)
    for k, v in user_dimensions.items():
        if k in scores and v is not None:
            scores[k] = v
    return scores


# ── 카테고리 → 채점 함수 + 필요 데이터 매핑 ──


_CATEGORY_TO_SCORER = {
    "director_election": auto_score_director_election,
    "director_compensation": auto_score_director_compensation,
    "articles_amendment": auto_score_articles_amendment,
    "audit_committee_election": auto_score_audit_committee_election,
    "treasury_share": auto_score_treasury_share,
    "cash_dividend": auto_score_cash_dividend,
    "financial_statements": auto_score_financial_statements,
    "merger": auto_score_merger,
    "spin_off": auto_score_spin_off,
    "capital_increase_decrease": auto_score_capital_increase_decrease,
    "cb_bw": auto_score_cb_bw,
    "shareholder_proposal": auto_score_shareholder_proposal,
}


# ── manual 입력 필요한 dim 목록 ──


_MANUAL_DIMS = {
    "director_election": ["adverse_news"],
    "director_compensation": ["ceo_pay_ratio", "performance_link", "company_performance"],
    "articles_amendment": [],
    "audit_committee_election": ["audit_opinion_history", "non_audit_fee_ratio"],
    "treasury_share": ["disposal_agm_approval", "shareholder_return_ratio"],
    "cash_dividend": [
        "cash_flow_sustainability", "dividend_decision_authority", "shareholder_return_ratio",
    ],
    "financial_statements": [
        "audit_opinion", "non_audit_fee_ratio", "accounting_error_history",
        "internal_control_weakness", "auditor_tenure", "auditor_independence_signal",
        "climate_disclosure",
    ],
    "merger": [
        "merger_ratio_fairness", "fairness_opinion_independence", "MoM_simulation",
        "synergy_clarity", "appraisal_right", "stakeholder_impact",
    ],
    "spin_off": [
        "subsidiary_listing_plan", "minority_shareholder_protection", "fairness_evaluation",
        "korea_2026_law_compliance", "info_disclosure",
    ],
    "capital_increase_decrease": [
        "issuance_size", "issuance_purpose", "issuance_price",
    ],
    "cb_bw": [
        "agm_resolution", "dilution_rate", "refixing_clause", "call_option",
        "third_party_independence", "conversion_price", "issuance_purpose",
    ],
    "shareholder_proposal": [
        "long_term_value_alignment", "board_proposal_competition", "proposer_independence",
        "non_implementation_history", "korea_specific_dispute",
    ],
}


def manual_dims_for_category(category: str) -> list[str]:
    """해당 카테고리에서 manual input 필요한 dim 목록."""
    return list(_MANUAL_DIMS.get(category, []))


def auto_dims_for_category(category: str, total_dims: list[str]) -> list[str]:
    """카테고리에서 자동 채점 가능한 dim 목록."""
    manual = set(_MANUAL_DIMS.get(category, []))
    return [d for d in total_dims if d not in manual]


# ── 통합: scope_predict 자동 채점 진입점 ──


async def auto_score_matrix(
    company_query: str,
    agenda_category: str,
    *,
    agenda_titles: list[str] | None = None,
    user_dimensions: dict[str, int] | None = None,
    meeting_date: str = "",
    notice_disclosure_date: str = "",
) -> dict[str, Any]:
    """카테고리 → data tool 호출 → dim 점수 dict.

    Returns:
        {
            "scores": {dim_id: int|None},
            "manual_dims": [...],
            "auto_dims": [...],
            "data_calls": {tool: status},
            "warnings": [...]
        }
    """
    # 지연 import (circular 방지)
    from open_proxy_mcp.services.corp_gov_report import build_corp_gov_report_payload
    from open_proxy_mcp.services.dividend_v2 import build_dividend_payload
    from open_proxy_mcp.services.ownership_structure import build_ownership_structure_payload
    from open_proxy_mcp.services.related_party_transaction import (
        build_related_party_transaction_payload,
    )
    from open_proxy_mcp.services.shareholder_meeting import build_shareholder_meeting_payload
    from open_proxy_mcp.services.treasury_share import build_treasury_share_payload

    import asyncio

    agenda_titles = agenda_titles or []
    user_dimensions = user_dimensions or {}
    warnings: list[str] = []
    data_calls: dict[str, str] = {}

    if agenda_category not in _CATEGORY_TO_SCORER:
        return {
            "scores": {},
            "manual_dims": [],
            "auto_dims": [],
            "data_calls": data_calls,
            "warnings": [f"카테고리 미지원: {agenda_category}"],
        }

    # 어떤 data tool 호출 필요한지 카테고리별 결정
    needs_board = agenda_category in ("director_election", "audit_committee_election")
    needs_compensation = agenda_category == "director_compensation"
    needs_corp_gov = agenda_category in (
        "director_election", "audit_committee_election", "director_compensation",
        "cash_dividend", "financial_statements",
    )
    needs_ownership = agenda_category in (
        "director_election", "audit_committee_election", "treasury_share", "merger",
        "spin_off", "capital_increase_decrease", "cb_bw", "cash_dividend",
        "shareholder_proposal", "financial_statements",
    )
    needs_related_party = agenda_category in (
        "director_election", "audit_committee_election", "treasury_share", "spin_off",
        "capital_increase_decrease", "cb_bw", "financial_statements",
    )
    needs_treasury = agenda_category == "treasury_share"
    needs_dividend = agenda_category == "cash_dividend"

    # 병렬 호출
    coros = []
    keys = []
    if needs_board:
        coros.append(build_shareholder_meeting_payload(company_query, scope="board"))
        keys.append("board")
    if needs_compensation:
        coros.append(build_shareholder_meeting_payload(company_query, scope="compensation"))
        keys.append("compensation")
    if needs_corp_gov:
        coros.append(build_corp_gov_report_payload(company_query, scope="metrics"))
        keys.append("corp_gov")
    if needs_ownership:
        coros.append(build_ownership_structure_payload(company_query, scope="control_map"))
        keys.append("ownership")
    if needs_related_party:
        coros.append(build_related_party_transaction_payload(company_query, scope="summary"))
        keys.append("related_party")
    if needs_treasury:
        coros.append(build_treasury_share_payload(company_query, scope="summary"))
        keys.append("treasury")
    if needs_dividend:
        coros.append(build_dividend_payload(company_query, scope="summary"))
        keys.append("dividend")

    payloads: dict[str, dict[str, Any]] = {}
    if coros:
        try:
            results = await asyncio.gather(*coros, return_exceptions=True)
        except Exception as exc:
            results = [exc] * len(coros)
        for k, r in zip(keys, results):
            if isinstance(r, BaseException):
                payloads[k] = {}
                data_calls[k] = f"error: {type(r).__name__}"
                warnings.append(f"{k} fetch 실패: {type(r).__name__}")
            else:
                payloads[k] = r
                data_calls[k] = r.get("status", "unknown") if isinstance(r, dict) else "unknown"

    # candidates / appointments
    candidates: list[dict[str, Any]] = []
    appointments: list[dict[str, Any]] = []
    board_payload = payloads.get("board", {})
    if board_payload:
        b = board_payload.get("data", {}).get("board", {}) or {}
        appointments = b.get("appointments", []) or []
        for a in appointments:
            for c in a.get("candidates", []) or []:
                # role context 보존
                cc = dict(c)
                cc["agenda_title"] = a.get("title", "")
                candidates.append(cc)

    comp_data = payloads.get("compensation", {}).get("data", {}) if "compensation" in payloads else None
    corp_gov_data = payloads.get("corp_gov", {}).get("data", {}) if "corp_gov" in payloads else None
    ownership_data = payloads.get("ownership", {}).get("data", {}) if "ownership" in payloads else None
    related_party_data = payloads.get("related_party", {}).get("data", {}) if "related_party" in payloads else None
    treasury_data = payloads.get("treasury", {}).get("data", {}) if "treasury" in payloads else None
    dividend_data = payloads.get("dividend", {}).get("data", {}) if "dividend" in payloads else None

    # 디스패치
    if agenda_category == "director_election":
        scores = auto_score_director_election(
            candidates, appointments, corp_gov_data, related_party_data, ownership_data,
            user_dimensions=user_dimensions,
        )
    elif agenda_category == "director_compensation":
        scores = auto_score_director_compensation(
            comp_data, agenda_titles, corp_gov_data, user_dimensions=user_dimensions,
        )
    elif agenda_category == "articles_amendment":
        scores = auto_score_articles_amendment(
            agenda_titles, notice_disclosure_date, meeting_date, user_dimensions=user_dimensions,
        )
    elif agenda_category == "audit_committee_election":
        scores = auto_score_audit_committee_election(
            candidates, agenda_titles, corp_gov_data, related_party_data, ownership_data,
            user_dimensions=user_dimensions,
        )
    elif agenda_category == "treasury_share":
        scores = auto_score_treasury_share(
            treasury_data, agenda_titles, ownership_data, related_party_data,
            meeting_date=meeting_date, user_dimensions=user_dimensions,
        )
    elif agenda_category == "cash_dividend":
        scores = auto_score_cash_dividend(
            dividend_data, corp_gov_data, ownership_data, user_dimensions=user_dimensions,
        )
    elif agenda_category == "financial_statements":
        scores = auto_score_financial_statements(
            related_party_data, ownership_data, corp_gov_data, user_dimensions=user_dimensions,
        )
    elif agenda_category == "merger":
        scores = auto_score_merger(ownership_data, agenda_titles, user_dimensions=user_dimensions)
    elif agenda_category == "spin_off":
        scores = auto_score_spin_off(
            related_party_data, ownership_data, agenda_titles, user_dimensions=user_dimensions,
        )
    elif agenda_category == "capital_increase_decrease":
        scores = auto_score_capital_increase_decrease(
            related_party_data, ownership_data, agenda_titles,
            notice_disclosure_date, meeting_date, user_dimensions=user_dimensions,
        )
    elif agenda_category == "cb_bw":
        scores = auto_score_cb_bw(
            related_party_data, ownership_data, user_dimensions=user_dimensions,
        )
    elif agenda_category == "shareholder_proposal":
        scores = auto_score_shareholder_proposal(
            ownership_data, agenda_titles, agenda_category, user_dimensions=user_dimensions,
        )
    else:
        scores = {}

    return {
        "scores": scores,
        "manual_dims": manual_dims_for_category(agenda_category),
        "auto_dims": [k for k in scores.keys() if k not in _MANUAL_DIMS.get(agenda_category, [])],
        "data_calls": data_calls,
        "warnings": warnings,
    }
