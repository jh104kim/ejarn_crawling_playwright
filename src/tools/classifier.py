"""
Tool: 기사 분류/태깅
- company
- related_comp (Recipro/Rotary/Scroll)
- product_type (Compressor/HVAC/Refrigeration/Component/Solution)
- market_segment (Residential/Commercial/Industrial/Infrastructure)
- refrigerant (HFC/HFO/Natural/Low-GWP/Unknown)
- application (Cooling/Heating/Refrigeration/Heat Recovery/Multi-purpose)
- technology (Efficiency/Control/AI/Sustainability/Compact/Design/Manufacturing)
- category (Product/Technology/Business/Manufacturing/Market)
"""
import json
import re
from typing import List

from src.schemas import (
    ApplicationType,
    CategoryType,
    CompType,
    MarketSegmentType,
    ProductType,
    RefrigerantType,
    TechnologyType,
)
from src.config import EJARN_USE_LLM_CLASSIFY, OPENAI_API_KEY


KNOWN_COMPANIES = [
    "Daikin", "Carrier", "Mitsubishi Electric", "Mitsubishi", "Panasonic", "Copeland",
    "Viessmann", "Trane", "Johnson Controls", "Danfoss", "Hitachi", "LG",
    "Samsung", "Gree", "Midea", "Toshiba", "Emerson", "Bosch", "Fujitsu",
]

COMP_KEYWORDS = {
    "Recipro": ["reciprocating", "piston compressor", "recipro", "reciprocat"],
    "Rotary": ["rotary compressor", "rolling piston", "rotary"],
    "Scroll": ["scroll compressor", "scroll"],
}

PRODUCT_KEYWORDS = {
    "Compressor": ["compressor", "compression", "scroll", "rotary", "reciprocating"],
    "HVAC": ["hvac", "air conditioner", "air conditioning", "vrf", "vrv", "heat pump", "chiller"],
    "Refrigeration": ["refrigeration", "cold chain", "freezer", "refrigerator", "showcase", "cold room"],
    "Component": ["valve", "motor", "inverter", "heat exchanger", "controller board", "component", "part"],
    "Solution": ["software", "platform", "service", "controls", "monitoring", "analytics", "solution"],
}

MARKET_SEGMENT_KEYWORDS = {
    "Residential": ["residential", "home", "household", "domestic"],
    "Commercial": ["commercial", "building", "retail", "office", "hotel", "mall"],
    "Industrial": ["industrial", "factory", "plant", "process", "manufacturing"],
    "Infrastructure": ["data center", "logistics", "public", "infrastructure", "district heating", "utility"],
}

REFRIGERANT_KEYWORDS = {
    "HFC/HFO": ["r32", "r410a", "r454b", "hfc", "hfo"],
    "Natural": ["r290", "co2", "r744", "ammonia", "r717", "propane", "natural refrigerant"],
    "Low-GWP": ["low-gwp", "low gwp", "gwp reduction", "low global warming potential"],
}

APPLICATION_KEYWORDS = {
    "Cooling": ["cooling", "air conditioning", "temperature control", "cool"],
    "Heating": ["heating", "hot water", "space heating", "warm"],
    "Refrigeration": ["refrigeration", "freezing", "cold storage", "cold chain"],
    "Heat Recovery": ["heat recovery", "waste heat", "recover heat"],
    "Multi-purpose": ["multi-purpose", "multi purpose", "all-in-one", "both heating and cooling"],
}

TECHNOLOGY_KEYWORDS = {
    "Efficiency": ["efficient", "efficiency", "performance", "cop", "sepr", "seer"],
    "Control/AI": ["control", "ai", "automation", "software", "analytics", "digital twin"],
    "Sustainability": ["sustainability", "decarbonization", "low-gwp", "net zero", "green"],
    "Compact/Design": ["compact", "design", "lightweight", "smaller footprint", "space saving"],
    "Manufacturing": ["manufacturing", "production process", "facility", "line", "plant"],
}

CATEGORY_KEYWORDS = {
    "Product": ["launch", "unveil", "introduce", "new model", "new series", "new product"],
    "Technology": ["technology", "r&d", "innovation", "efficiency", "performance", "quality"],
    "Business": ["investment", "acquisition", "partnership", "strategy", "funding", "revenue"],
    "Manufacturing": ["factory", "plant", "production", "capacity", "manufacturing"],
    "Market": ["market", "demand", "trend", "expo", "conference", "regulation", "policy"],
}


def _norm_text(title: str, body: str) -> str:
    return f"{title} {body}".lower()


def _dedupe_str_list(values: List[str]) -> List[str]:
    return list(dict.fromkeys(values))


def _keyword_pick(text: str, mapping: dict) -> List[str]:
    found = []
    for label, keywords in mapping.items():
        if any(kw.lower() in text for kw in keywords):
            found.append(label)
    return _dedupe_str_list(found)


def _classify_labels_llm(title: str, body: str, valid: List[str], instruction: str, max_tokens: int = 90) -> List[str]:
    if not (EJARN_USE_LLM_CLASSIFY and OPENAI_API_KEY):
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        text = title + "\n" + (body[:3500] if len(body) > 3500 else body)
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an HVAC&R classifier. "
                        f"Choose labels from: {valid}. "
                        "Return JSON array only. "
                        "Use only labels with clear evidence from title/body. "
                        + instruction
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=max_tokens,
        )
        content = (r.choices[0].message.content or "").strip()
        arr = json.loads(content) if content else []
        return _dedupe_str_list([x for x in arr if x in valid])
    except Exception:
        return []


def classify_company(title: str, body: str) -> List[str]:
    text = f"{title} {body}"
    found = [name for name in KNOWN_COMPANIES if re.search(rf"\b{re.escape(name)}\b", text, flags=re.IGNORECASE)]

    # 제목 첫 토큰 기반 보정: "Company Name: ..." 패턴
    head = title.split(":", 1)[0].strip()
    if 2 <= len(head) <= 60 and any(ch.isalpha() for ch in head):
        if any(x in head.lower() for x in ["launch", "introduce", "unveil", "opens", "expands"]):
            pass
        else:
            if head not in found and len(head.split()) <= 4:
                found.insert(0, head)

    return _dedupe_str_list(found)


def classify_comp(title: str, body: str) -> List[CompType]:
    valid = ["Recipro", "Rotary", "Scroll"]
    llm = _classify_labels_llm(
        title,
        body,
        valid,
        "Comp rules: Recipro=reciprocating/piston, Rotary=rolling-piston/rotary, Scroll=scroll compressor.",
        max_tokens=50,
    )
    if llm:
        return llm
    return _keyword_pick(_norm_text(title, body), COMP_KEYWORDS)


def classify_product_type(title: str, body: str) -> List[ProductType]:
    valid = ["Compressor", "HVAC", "Refrigeration", "Component", "Solution"]
    llm = _classify_labels_llm(
        title,
        body,
        valid,
        "Product rules: Compressor=compressor itself; HVAC=AC/heat pump/VRF/chiller; Refrigeration=cold chain/showcase/freezer; Component=parts; Solution=software/control/service/platform.",
    )
    if llm:
        return llm
    return _keyword_pick(_norm_text(title, body), PRODUCT_KEYWORDS)


def classify_market_segment(title: str, body: str) -> List[MarketSegmentType]:
    valid = ["Residential", "Commercial", "Industrial", "Infrastructure"]
    llm = _classify_labels_llm(
        title,
        body,
        valid,
        "Market rules: Residential=home; Commercial=building/retail; Industrial=factory/process; Infrastructure=data-center/public/logistics.",
    )
    if llm:
        return llm
    return _keyword_pick(_norm_text(title, body), MARKET_SEGMENT_KEYWORDS)


def classify_refrigerant(title: str, body: str) -> List[RefrigerantType]:
    valid = ["HFC/HFO", "Natural", "Low-GWP", "Unknown"]
    llm = _classify_labels_llm(
        title,
        body,
        valid,
        "Refrigerant rules: HFC/HFO includes R32/R410A/R454B; Natural includes R290/CO2/Ammonia; Low-GWP when only low-GWP is emphasized without exact refrigerant; Unknown when no refrigerant info.",
    )
    if llm:
        return llm

    text = _norm_text(title, body)
    found = _keyword_pick(text, REFRIGERANT_KEYWORDS)
    if not found:
        return ["Unknown"]
    return found


def classify_application(title: str, body: str) -> List[ApplicationType]:
    valid = ["Cooling", "Heating", "Refrigeration", "Heat Recovery", "Multi-purpose"]
    llm = _classify_labels_llm(
        title,
        body,
        valid,
        "Application rules: Cooling, Heating, Refrigeration, Heat Recovery; Multi-purpose when mixed or unclear single use.",
    )
    if llm:
        return llm

    found = _keyword_pick(_norm_text(title, body), APPLICATION_KEYWORDS)
    if not found:
        return ["Multi-purpose"]
    return found


def classify_technology(title: str, body: str) -> List[TechnologyType]:
    valid = ["Efficiency", "Control/AI", "Sustainability", "Compact/Design", "Manufacturing"]
    llm = _classify_labels_llm(
        title,
        body,
        valid,
        "Technology rules: Efficiency, Control/AI, Sustainability, Compact/Design, Manufacturing process.",
    )
    if llm:
        return llm
    return _keyword_pick(_norm_text(title, body), TECHNOLOGY_KEYWORDS)


def classify_category(title: str, body: str) -> List[CategoryType]:
    valid = ["Product", "Technology", "Business", "Manufacturing", "Market"]
    llm = _classify_labels_llm(
        title,
        body,
        valid,
        "Category rules: Product=new product launch; Technology=performance/quality/R&D; Business=investment/M&A/partnership; Manufacturing=factory/production/capacity; Market=market trend/expo/regulation/industry trend.",
    )
    if llm:
        return llm

    found = _keyword_pick(_norm_text(title, body), CATEGORY_KEYWORDS)
    if not found:
        return ["Market"]
    return found
