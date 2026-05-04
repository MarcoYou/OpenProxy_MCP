"""주총 1번 안건 (재무제표 승인) 본문에서 당기 (FY current) raw 추출.

DART 주총소집공고 본문 안에는 1번 안건으로 보통 당기 재무제표 요약 (당기/전기 손익 + 자산/부채/자본 + 이익잉여금처분) 표가 첨부됨.

본 파서는 정규식 기반:
- "당기순이익(손실)" 또는 "당기순이익" 키워드 다음의 숫자 페어 (당기/전기) 추출
- "매출액", "영업이익", "자산총계", "부채총계", "자본총계" 등 동일 패턴

매핑: success/soft-fail.
- success: 표 형태 + 명확한 키워드 + 숫자 추출
- soft-fail: 키워드 발견 but 숫자 패턴 매칭 X (이미지 표 / 서식 다양)
"""

from __future__ import annotations

import re
from typing import Any

# 핵심 metric 키워드
_FY_KEYWORDS = {
    "net_income_krw": ["당기순이익(손실)", "당기순이익", "당기손익", "당기 순이익"],
    "revenue_krw": ["매출액", "수익(매출액)", "영업수익"],
    "operating_profit_krw": ["영업이익(손실)", "영업이익", "영업손익"],
    "total_assets_krw": ["자산총계", "자산 총계"],
    "total_liabilities_krw": ["부채총계", "부채 총계"],
    "total_equity_krw": ["자본총계", "자본 총계"],
}

# 숫자 패턴 — 콤마 포함, 괄호 (음수), 마이너스, 소숫점
_NUM_PATTERN = re.compile(r"(\(?-?\s*\d[\d,]*(?:\.\d+)?\)?)")


def _parse_num(s: str) -> int | None:
    """'(977,063)' / '515,011' / '-1,234' → int (백만원 단위는 호출자 책임)."""
    s = s.strip()
    neg = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
        neg = True
    if s.startswith("-"):
        s = s[1:].strip()
        neg = True
    s = s.replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        v = int(float(s))
        return -v if neg else v
    except ValueError:
        return None


def parse_fy_from_agm_doc(text: str) -> dict[str, Any]:
    """주총소집공고 text에서 1번 안건 (재무제표 승인) FY raw 추출.

    Returns:
      {
        "fy_current_net_income_krw_mn": ...,  # 백만원 단위 (DART 표기 그대로)
        "fy_prior_net_income_krw_mn": ...,
        "fy_current_revenue_krw_mn": ...,
        ... (None if not found)
        "extraction_status": "success" / "partial" / "no_data",
        "matched_keywords": [...],
      }
    """
    if not text:
        return {"extraction_status": "no_data", "matched_keywords": []}

    result: dict[str, Any] = {}
    matched: list[str] = []

    # 한글 조사 감지 (false-positive 방지) — 표 셀이 아닌 본문 문장 패턴
    _KOREAN_PARTICLE = re.compile(r"^\s*(은|는|이|가|을|를|에|의|와|과|로|에서|에게|부터|까지|만|에 대한|에 따라)")

    for metric_key, keywords in _FY_KEYWORDS.items():
        for kw in keywords:
            # 모든 occurrence 검색 — 첫 번째가 본문 문장이면 다음 시도
            search_start = 0
            while True:
                idx = text.find(kw, search_start)
                if idx < 0:
                    break
                # 키워드 직후 (next 5 chars) 한글 조사면 skip
                after = text[idx + len(kw): idx + len(kw) + 8]
                if _KOREAN_PARTICLE.match(after):
                    search_start = idx + len(kw)
                    continue
                # 표 셀 패턴 — 키워드 다음 우선 공백/숫자/괄호만
                window = text[idx + len(kw): idx + len(kw) + 200]
                window_norm = re.sub(r"\s+", " ", window).strip()
                nums = _NUM_PATTERN.findall(window_norm)
                clean = []
                for n in nums:
                    v = _parse_num(n)
                    # 매출/영업이익/자산/부채/자본은 매우 큰 숫자 (>= 1,000 백만원 = 10억)
                    # 순이익은 적자 작은 회사도 가능 — but 보통 절대값 >= 100
                    min_abs = 1000 if metric_key != "net_income_krw" else 100
                    if v is not None and abs(v) >= min_abs:
                        clean.append(v)
                    if len(clean) >= 2:
                        break
                if len(clean) >= 2:
                    result[f"fy_current_{metric_key}_mn"] = clean[0]
                    result[f"fy_prior_{metric_key}_mn"] = clean[1]
                    matched.append(metric_key)
                    break
                search_start = idx + len(kw)
            if metric_key in matched:
                break

    if matched:
        result["extraction_status"] = "success" if len(matched) >= 3 else "partial"
    else:
        result["extraction_status"] = "no_data"
    result["matched_keywords"] = matched
    return result


def extract_fy_from_meeting_payload(meeting_summary_payload: dict[str, Any] | None,
                                     dart_doc_text: str | None) -> dict[str, Any]:
    """meeting_summary payload + DART doc text → fy raw dict.

    meeting_summary는 일반적으로 doc 본문 직접 노출 X — text 인자로 받아 처리.
    """
    if not dart_doc_text:
        return {"extraction_status": "no_data", "matched_keywords": []}
    return parse_fy_from_agm_doc(dart_doc_text)
