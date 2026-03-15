"""
LangChain 에이전트: System / Human / AI / Tool 흐름으로 기사 수집 오케스트레이션.
Tool 호출 중심, 최종 출력은 ArticleCollection JSON.
"""
import json
import re
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from src.config import OPENAI_API_KEY
from src.agent_prompts import SYSTEM_PROMPT
from src.agent_tools import AGENT_TOOLS

# Tool 이름 -> 실제 호출 함수 매핑
TOOL_MAP = {t.name: t for t in AGENT_TOOLS}


def _run_tool(name: str, args: dict) -> str:
    """Tool 이름과 인자로 실행 후 문자열 반환."""
    tool = TOOL_MAP.get(name)
    if not tool:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = tool.invoke(args)
        if isinstance(result, (list, dict)):
            return json.dumps(result, ensure_ascii=False)
        return str(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(
    human_query: str = "최신 기사 10개 추출해줘.",
    max_iterations: int = 100,
    model: str = "gpt-4o",
) -> str:
    """
    에이전트 실행: System → Human → (AI ↔ Tool)* → 최종 AI(ArticleCollection JSON).

    Parameters
    ----------
    human_query : str
        사용자 요청.
    max_iterations : int
        AI/Tool 교차 최대 횟수.
    model : str
        OpenAI 채팅 모델.

    Returns
    -------
    str
        최종 AI 메시지 내용 (ArticleCollection JSON 문자열).
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 .env에 설정되어야 합니다.")

    llm = ChatOpenAI(model=model, api_key=OPENAI_API_KEY).bind_tools(AGENT_TOOLS)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_query),
    ]

    for _ in range(max_iterations):
        response = llm.invoke(messages)
        if not isinstance(response, AIMessage):
            break
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            # Tool 호출 없음 → 최종 응답
            return (response.content or "").strip()

        for tc in response.tool_calls:
            if isinstance(tc, dict):
                name, args = tc.get("name", ""), tc.get("args") or {}
                tid = tc.get("id") or tc.get("tool_call_id", "")
            else:
                name = getattr(tc, "name", "")
                args = getattr(tc, "args", None) or {}
                tid = getattr(tc, "id", None) or getattr(tc, "tool_call_id", "")
            result = _run_tool(name, args)
            messages.append(ToolMessage(content=result, tool_call_id=tid or ""))

    return (messages[-1].content or "").strip() if messages else ""


def run_agent_and_parse(
    human_query: str = "최신 기사 10개 추출해줘.",
    max_iterations: int = 100,
):
    """에이전트 실행 후 응답에서 JSON 추출해 ArticleCollection으로 파싱."""
    from src.schemas import ArticleCollection

    raw = run_agent(human_query=human_query, max_iterations=max_iterations)
    # JSON 블록 추출 (```json ... ``` 또는 그냥 {...} )
    json_str = raw
    m = re.search(r"\{[\s\S]*\"source\"[\s\S]*\"items\"[\s\S]*\}", raw)
    if m:
        json_str = m.group(0)
    try:
        data = json.loads(json_str)
        return ArticleCollection.model_validate(data)
    except Exception:
        return raw
