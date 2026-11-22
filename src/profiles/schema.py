from typing import Any, Literal
from pydantic import BaseModel, Field

class MacroFilters(BaseModel):
    categories: list[str] = Field(default_factory=list)
    prestation_types: list[str] = Field(default_factory=list)
    geographic_coverage: dict[str, Any] = Field(default_factory=dict)
    financial_bands: dict[str, float] = Field(default_factory=dict)
    minimum_deadline_hours: int = 24

class CatalogItem(BaseModel):
    id: str
    label: str
    weight: float = 1.0
    synonyms_fr: list[str] = Field(default_factory=list)
    synonyms_ar: list[str] = Field(default_factory=list)
    technical_keywords: list[str] = Field(default_factory=list)

class NegativeConstraints(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    disallowed_buyer_types: list[str] = Field(default_factory=list)

class ScoringWeights(BaseModel):
    line_item_coverage: float = 0.40
    semantic_similarity: float = 0.30
    feasibility_proximity: float = 0.15
    commercial_attractiveness: float = 0.15

class CompanyProfileSchema(BaseModel):
    version: str = "1.0"
    tenant_id: str
    profile_id: str | None = None
    profile_name: str
    icon: str | None = None
    description: str | None = None
    contact_email: str | None = None
    macro_filters: MacroFilters
    catalog: list[CatalogItem]
    negative_constraints: NegativeConstraints
    scoring_weights: ScoringWeights
