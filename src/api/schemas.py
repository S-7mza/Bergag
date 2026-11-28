import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from src.engine.ai_diagnostician import AIMatchingDiagnosis

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
    alignment_feedback: Optional[str] = None # 'aligned', 'misaligned', or None
    ai_matching: Optional[AIMatchingDiagnosis] = None # Deep AI Matching Diagnosis
    xyz_evaluation: Optional[Dict[str, Any]] = None
    antigravity_study: Optional[Dict[str, Any]] = None

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
    alignment_feedback: Optional[str] = None # 'aligned', 'misaligned', or None
    ai_matching: Optional[AIMatchingDiagnosis] = None # Deep AI Matching Diagnosis
    xyz_evaluation: Optional[Dict[str, Any]] = None
    antigravity_study: Optional[Dict[str, Any]] = None

class AlignmentFeedbackRequest(BaseModel):
    portal_id: int
    profile_name: str
    is_aligned: bool
    user_notes: Optional[str] = None

class AlignmentFeedbackResponse(BaseModel):
    success: bool
    portal_id: int
    profile_name: str
    alignment_feedback: str
    updated_score: float
    updated_verdict: str
    message: str
    learned_terms_count: int

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

class DiagnoseBatchRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=2000)
    open_only: bool = Field(default=False)
    force_refresh: bool = Field(default=False)

class DiagnoseBatchResponse(BaseModel):
    success: bool
    total_scanned: int
    rating_distribution: Dict[str, int]
    domain_distribution: Dict[str, int]
    top_technologies: Dict[str, int]
    top_opportunities: List[Dict[str, Any]]
