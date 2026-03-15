"""
LangChain Tool 래퍼: fetch_latest_list, fetch_article_detail, summarize_article, classify_*.
에이전트가 호출하는 기사 분류 Tool 정의.
"""
from langchain_core.tools import tool

from src.tools.fetcher import fetch_article_list as _fetch_list, fetch_article_detail as _fetch_detail
from src.tools.summarizer import summarize_text
from src.tools.classifier import (
    classify_application,
    classify_category,
    classify_company,
    classify_comp,
    classify_market_segment,
    classify_product_type,
    classify_refrigerant,
    classify_technology,
)


@tool
def fetch_latest_list(max_items: int = 10) -> list:
    """JARN/eJARN 최신 기사 목록 추출. 반환: [{"link": url, "date_str": "YYYY.MM.DD", "title": "..."}, ...]"""
    entries = _fetch_list(max_items=max_items)
    return [{"link": e.link, "date_str": e.date_str, "title": e.title} for e in entries]


@tool
def fetch_article_detail(link: str) -> dict:
    """개별 기사 링크의 날짜/제목/본문 추출. 반환: {"link", "date_str", "topic", "body"}"""
    d = _fetch_detail(link)
    return {"link": d.link, "date_str": d.date_str, "topic": d.topic, "body": d.body}


@tool
def summarize_article(body: str) -> str:
    """기사 본문을 500자 이내로 요약. 본문이 비어 있으면 빈 문자열 반환."""
    return summarize_text(body) if body else ""


@tool
def classify_comp_tool(topic: str, body: str) -> list[str]:
    """related_comp 분류: Recipro / Rotary / Scroll 중 해당하는 것 리스트 반환."""
    return list(classify_comp(topic, body))


@tool
def classify_category_tool(topic: str, body: str) -> list[str]:
    """category 분류: Product/Technology/Business/Manufacturing/Market 중 해당하는 것 리스트 반환."""
    return list(classify_category(topic, body))


@tool
def classify_product_type_tool(topic: str, body: str) -> list[str]:
    """제품 분류: Compressor/HVAC/Refrigeration/Component/Solution 중 해당하는 것 리스트 반환."""
    return list(classify_product_type(topic, body))


@tool
def classify_company_tool(topic: str, body: str) -> list[str]:
    """company 분류: 기사에서 식별되는 기업명 리스트 반환."""
    return list(classify_company(topic, body))


@tool
def classify_market_segment_tool(topic: str, body: str) -> list[str]:
    """market_segment 분류: Residential/Commercial/Industrial/Infrastructure."""
    return list(classify_market_segment(topic, body))


@tool
def classify_refrigerant_tool(topic: str, body: str) -> list[str]:
    """refrigerant 분류: HFC/HFO/Natural/Low-GWP/Unknown."""
    return list(classify_refrigerant(topic, body))


@tool
def classify_application_tool(topic: str, body: str) -> list[str]:
    """application 분류: Cooling/Heating/Refrigeration/Heat Recovery/Multi-purpose."""
    return list(classify_application(topic, body))


@tool
def classify_technology_tool(topic: str, body: str) -> list[str]:
    """technology 분류: Efficiency/Control-AI/Sustainability/Compact-Design/Manufacturing."""
    return list(classify_technology(topic, body))


AGENT_TOOLS = [
    fetch_latest_list,
    fetch_article_detail,
    summarize_article,
    classify_company_tool,
    classify_comp_tool,
    classify_product_type_tool,
    classify_market_segment_tool,
    classify_refrigerant_tool,
    classify_application_tool,
    classify_technology_tool,
    classify_category_tool,
]
