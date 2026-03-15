"""
Tool: 기사 본문 요약 (900자 이내).
규칙 기반 기본 구현 + 확장 포인트(LLM).
"""
from src.config import EJARN_USE_LLM_SUMMARY, OPENAI_API_KEY

MAX_SUMMARY_LEN = 900


def summarize_text(text: str, max_chars: int = MAX_SUMMARY_LEN) -> str:
    """
    본문을 max_chars 이내로 요약한다.
    LLM 사용 설정이면 _summarize_with_llm 호출, 아니면 규칙 기반.

    Parameters
    ----------
    text : str
        원문 본문.
    max_chars : int
        요약 최대 글자 수.

    Returns
    -------
    str
        요약문.
    """
    if EJARN_USE_LLM_SUMMARY and OPENAI_API_KEY:
        return _summarize_with_llm(text, max_chars)
    return _summarize_rule_based(text, max_chars)


def _summarize_rule_based(text: str, max_chars: int) -> str:
    """첫 문단 위주로 자르고 공백 정리."""
    if not text or not text.strip():
        return ""
    text = text.strip()
    # 첫 두 문단 정도까지 취한 뒤 길이 제한
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out = []
    length = 0
    for p in paragraphs:
        if length + len(p) + 2 <= max_chars:
            out.append(p)
            length += len(p) + 2
        else:
            # 마지막 문단이 길면 잘라서 추가
            remain = max_chars - length - 4
            if remain > 20:
                out.append(p[:remain].rstrip() + "…")
            break
    summary = "\n\n".join(out) if out else text[:max_chars].rstrip() + "…"
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rstrip() + "…"
    return summary


def _summarize_with_llm(text: str, max_chars: int) -> str:
    """확장 포인트: OpenAI 등 LLM으로 요약. 미구현 시 규칙 기반으로 폴백."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        truncated = text[:6000] if len(text) > 6000 else text
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"다음 HVAC&R 산업 기사를 한국어로 {max_chars}자 이내로 요약하세요. 마크다운 없이 평문으로만 출력하고, 반드시 {max_chars}자를 넘지 마세요."},
                {"role": "user", "content": truncated},
            ],
            max_tokens=400,
        )
        summary = (r.choices[0].message.content or "").strip()
        if len(summary) > max_chars:
            summary = summary[: max_chars - 1].rstrip() + "…"
        return summary
    except Exception:
        return _summarize_rule_based(text, max_chars)
