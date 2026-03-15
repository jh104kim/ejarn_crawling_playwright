"""
eJARN 기사 수집 결과의 Pydantic 스키마.
"""
from typing import List, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

CompType = Literal["Recipro", "Rotary", "Scroll"]
ProductType = Literal["Compressor", "HVAC", "Refrigeration", "Component", "Solution"]
MarketSegmentType = Literal["Residential", "Commercial", "Industrial", "Infrastructure"]
RefrigerantType = Literal["HFC/HFO", "Natural", "Low-GWP", "Unknown"]
ApplicationType = Literal["Cooling", "Heating", "Refrigeration", "Heat Recovery", "Multi-purpose"]
TechnologyType = Literal["Efficiency", "Control/AI", "Sustainability", "Compact/Design", "Manufacturing"]
CategoryType = Literal["Product", "Technology", "Business", "Manufacturing", "Market"]


class ArticleItem(BaseModel):
    """기사 한 건의 정규화된 구조."""

    date: str = Field(description="기사 날짜. 가능하면 YYYY-MM-DD")
    topic: str = Field(description="기사 제목")
    summary: str = Field(description="기사 핵심 요약. 900자 이내", max_length=900)
    link: HttpUrl = Field(description="기사 상세 URL")
    source_topic: str = Field(default="", description="상위 토픽명 (예: Air Conditioners)")
    source_topic_url: str = Field(default="", description="상위 토픽 URL")
    related_titles: List[str] = Field(default_factory=list, description="동일 토픽 내 나머지 기사 제목 목록")
    company: List[str] = Field(default_factory=list, description="기사에서 식별된 기업명")
    related_comp: List[CompType] = Field(default_factory=list)
    product_type: List[ProductType] = Field(default_factory=list)
    market_segment: List[MarketSegmentType] = Field(default_factory=list)
    refrigerant: List[RefrigerantType] = Field(default_factory=list)
    application: List[ApplicationType] = Field(default_factory=list)
    technology: List[TechnologyType] = Field(default_factory=list)
    category: List[CategoryType] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _trim_summary(cls, value):
        if value is None:
            return ""
        text = str(value).strip()
        if len(text) > 900:
            return text[:899].rstrip() + "…"
        return text

    @field_validator(
        "company",
        "related_titles",
        "related_comp",
        "product_type",
        "market_segment",
        "refrigerant",
        "application",
        "technology",
        "category",
        mode="before",
    )
    @classmethod
    def _dedupe_list(cls, value):
        if not value:
            return []
        if not isinstance(value, list):
            value = [value]
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _ensure_defaults(self):
        if not self.refrigerant:
            self.refrigerant = ["Unknown"]
        if not self.application:
            self.application = ["Multi-purpose"]
        if not self.category:
            self.category = ["Market"]
        return self


class ArticleCollection(BaseModel):
    """수집 결과 전체."""

    source: str = Field(description="수집 소스 식별자, 예: eJARN")
    collected_at: str = Field(description="수집 시각 ISO 형식")
    items: List[ArticleItem] = Field(default_factory=list)
