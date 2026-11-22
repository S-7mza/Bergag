import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class LineItemSchema(BaseModel):
    item_order: int
    designation: str
    technical_specs: Optional[str] = None
    unit: str = "U"
    quantity: float
    tva_rate: float = 20.0
    warranty_required: Optional[str] = None

class TenderFeedItem(BaseModel):
    portal_id: int
    reference: str
    title: str
    buyer_name: str
    execution_location: Optional[str] = None
    main_category: str
    published_at: str
    deadline_at: str
    status: str
    match_score: float = 0.0
    decision_verdict: str = "PENDING"
    line_item_count: int = 0
    portal_url: str

class TenderDetailResponse(BaseModel):
    portal_id: int
    reference: str
    title: str
    buyer_name: str
    execution_location: Optional[str] = None
    main_category: str
    prestation_type: Optional[str] = None
    published_at: str
    deadline_at: str
    status: str
    attachment_available: bool = False
    attachment_url: Optional[str] = None
    line_items: List[LineItemSchema]
    portal_url: str
    match_score: float = 0.0
    decision_verdict: str = "PENDING"
    coverage_score: float = 0.0
    red_flags: List[str] = []
    llm_reasoning: Optional[str] = None
    line_item_evaluations: List[Dict[str, Any]] = []

class UserActionRequest(BaseModel):
    profile_id: Optional[str] = "00000000-0000-0000-0000-000000000000"
    tender_id: int
    action: str = Field(..., pattern="^(viewed|shortlisted|in_preparation|bidded|won|lost|rejected)$")
    rejection_reason: Optional[str] = None
    user_notes: Optional[str] = None
    bid_amount_mad: Optional[float] = None
    tender_metadata: Optional[Dict[str, Any]] = None

class UserActionResponse(BaseModel):
    success: bool
    action_id: str
    action: str
    tender_id: int
    message: Optional[str] = None
