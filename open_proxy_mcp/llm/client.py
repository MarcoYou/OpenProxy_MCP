"""LLM fallback for agenda parsing — Claude (default) / OpenAI"""

import json
import os
import logging

logger = logging.getLogger(__name__)

AGENDA_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "number": {"type": "string", "description": "의안 번호 (예: 제1호, 제2-1호)"},
            "title": {"type": "string", "description": "의안 제목"},
            "children": {
                "type": "array",
                "items": {"$ref": "#/items"},
                "description": "하위 의안 목록",
            },
        },
        "required": ["number", "title"],
    },
}

SYSTEM_PROMPT = """주주총회 소집공고의 안건 영역 텍스트가 주어집니다.
의안(안건) 목록을 아래 JSON 배열로 추출하세요.

규칙:
- 제N호 → 루트 안건, 제N-M호 → 하위, 제N-M-K호 → 3단계 하위
- children에 하위 안건 배열. 없으면 빈 배열
- number는 "제1호", "제2-1호" 형태 (공백 없이)
- title은 의안 제목만 (번호, 기호 제외)
- 보고사항은 제외, 의결사항(부의안건)만 추출

JSON 배열만 출력하세요. 설명 없이."""

USER_PROMPT_TEMPLATE = """아래 텍스트에서 의안 목록을 JSON으로 추출하세요:

{zone_text}"""


async def extract_agenda_with_llm(zone_text: str, provider: str = "claude") -> list[dict]:
    """zone 텍스트를 LLM에 보내 안건 트리 구조를 추출

    Args:
        zone_text: 회의목적사항 영역 텍스트
        provider: "claude" (기본) 또는 "openai"

    Returns:
        parse_agenda_items와 동일한 구조의 list[dict]
        실패 시 빈 리스트 반환
    """
    user_msg = USER_PROMPT_TEMPLATE.format(zone_text=zone_text[:3000])

    try:
        if provider == "openai":
            raw = await _call_openai(user_msg)
        else:
            raw = await _call_claude(user_msg)

        items = json.loads(raw)
        return _normalize_llm_output(items)
    except Exception as e:
        logger.error(f"LLM fallback 실패 ({provider}): {e}")
        return []


async def _call_claude(user_msg: str) -> str:
    """Anthropic Claude Sonnet 호출"""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text


async def _call_openai(user_msg: str) -> str:
    """OpenAI GPT 호출"""
    import openai

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다")

    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    return response.choices[0].message.content


def _normalize_llm_output(items: list[dict], level1: int = 1) -> list[dict]:
    """LLM JSON 출력을 parse_agenda_items 반환 구조로 정규화"""
    result = []
    for item in items:
        number = item.get("number", "")
        title = item.get("title", "")

        # 번호에서 level 추출
        import re
        m = re.match(r'제(\d+)(?:-(\d+))?(?:-(\d+))?호', number.replace(" ", ""))
        if m:
            l1 = int(m.group(1))
            l2 = int(m.group(2)) if m.group(2) else None
            l3 = int(m.group(3)) if m.group(3) else None
        else:
            l1 = level1
            l2 = None
            l3 = None
            level1 += 1

        children_raw = item.get("children", [])
        children = _normalize_llm_output(children_raw, level1=1) if children_raw else []

        result.append({
            "number": number,
            "level1": l1,
            "level2": l2,
            "level3": l3,
            "title": title,
            "source": None,
            "conditional": None,
            "children": children,
        })

    return result
