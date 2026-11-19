import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.database.session import get_db_session
from src.models.tender import Tender, Buyer, LineItem
from src.models.profile import CompanyProfile, ProfileMatch, UserTenderAction
from src.profiles.loader import load_profile, load_all_profiles
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.api.schemas import (
    TenderFeedItem, 
    TenderDetailResponse, 
    LineItemSchema, 
    UserActionRequest, 
    UserActionResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Procurement Feed"])

@router.get("/profiles")
async def get_available_profiles():
    """Lists all loaded company profiles"""
    profiles = load_all_profiles()
    return [
        {
            "tenant_id": p.tenant_id,
            "profile_name": p.profile_name,
            "categories": p.macro_filters.categories,
            "catalog_count": len(p.catalog)
        }
        for p in profiles
    ]

@router.get("/feed", response_model=List[TenderFeedItem])
async def get_tender_feed(
    profile_name: str = Query("cctv_security", description="Profile configuration to score against"),
    min_score: float = Query(0.0, description="Minimum overall alignment score (0-100)"),
    search: Optional[str] = Query(None, description="Search keyword in title or buyer"),
    region: Optional[str] = Query(None, description="Filter by location/region"),
    category: Optional[str] = Query(None, description="Filter by category (Fournitures, Services, etc.)"),
    urgency: Optional[str] = Query(None, description="Urgency filter (urgent_24h, urgent_48h)"),
    role: Optional[str] = Query("admin", description="Current user role for RBAC scoping"),
    limit: int = Query(60, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Returns dynamically filtered, ranked active procurement opportunities
    scored against the selected profile and scoped by user role.
    """
    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")

    scoring_engine = ScoringCascadeEngine()

    # RBAC Enforcement: Viewers only see curated high-confidence opportunities (>=75% GO)
    effective_min_score = max(min_score, 75.0) if role == "viewer" else min_score

    # Query active tenders
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.status == "active")
        .order_by(Tender.deadline_at.asc())
        .limit(limit)
    )

    if search:
        search_pattern = f"%{search.lower()}%"
        stmt = stmt.where(Tender.title.ilike(search_pattern))

    if region and region != "all":
        stmt = stmt.where(Tender.execution_location.ilike(f"%{region}%"))

    if category and category != "all":
        stmt = stmt.where(Tender.main_category.ilike(f"%{category}%"))

    now = datetime.now(timezone.utc)
    if urgency == "urgent_24h":
        stmt = stmt.where(Tender.deadline_at <= (now + timedelta(hours=24)))
    elif urgency == "urgent_48h":
        stmt = stmt.where(Tender.deadline_at <= (now + timedelta(hours=48)))

    res = await session.execute(stmt)
    tenders = res.scalars().all()

    feed_items = []
    for t in tenders:
        tender_dict = {
            "portal_id": t.portal_id,
            "reference": t.reference,
            "title": t.title,
            "buyer_name": t.buyer.official_name if t.buyer else "Inconnu",
            "execution_location": t.execution_location,
            "main_category": t.main_category,
            "published_at": t.published_at.isoformat(),
            "deadline_at": t.deadline_at.isoformat(),
            "status": t.status,
            "line_items": [
                {
                    "item_order": item.item_order,
                    "designation": item.designation,
                    "technical_specs": item.technical_specs,
                    "unit": item.unit,
                    "quantity": float(item.quantity),
                    "tva_rate": float(item.tva_rate or 20.0),
                    "warranty_required": item.warranty_required
                }
                for item in t.line_items
            ]
        }

        # Score on the fly
        cascade_res = await scoring_engine.evaluate_tender(tender_dict, profile)

        if cascade_res.overall_score >= effective_min_score:
            feed_items.append(
                TenderFeedItem(
                    portal_id=t.portal_id,
                    reference=t.reference,
                    title=t.title,
                    buyer_name=t.buyer.official_name if t.buyer else "Acheteur Inconnu",
                    execution_location=t.execution_location or "Maroc (National)",
                    main_category=t.main_category,
                    published_at=t.published_at.strftime("%d/%m/%Y %H:%M"),
                    deadline_at=t.deadline_at.strftime("%d/%m/%Y %H:%M"),
                    status=t.status,
                    match_score=cascade_res.overall_score,
                    decision_verdict=cascade_res.decision_recommendation,
                    line_item_count=len(t.line_items),
                    portal_url=f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{t.portal_id}"
                )
            )

    # Sort by match score descending
    feed_items.sort(key=lambda x: x.match_score, reverse=True)
    return feed_items

@router.get("/tenders/{portal_id}", response_model=TenderDetailResponse)
async def get_tender_detail(
    portal_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """Returns full details, specifications, and line items for a tender"""
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.portal_id == portal_id)
    )
    res = await session.execute(stmt)
    t = res.scalar_one_or_none()

    if not t:
        raise HTTPException(status_code=404, detail=f"Tender #{portal_id} not found")

    return TenderDetailResponse(
        portal_id=t.portal_id,
        reference=t.reference,
        title=t.title,
        buyer_name=t.buyer.official_name if t.buyer else "Acheteur Inconnu",
        execution_location=t.execution_location or "Maroc (National)",
        main_category=t.main_category,
        prestation_type=t.prestation_type,
        published_at=t.published_at.strftime("%d/%m/%Y %H:%M"),
        deadline_at=t.deadline_at.strftime("%d/%m/%Y %H:%M"),
        status=t.status,
        attachment_available=t.attachment_available,
        attachment_url=t.attachment_url,
        line_items=[
            LineItemSchema(
                item_order=i.item_order,
                designation=i.designation,
                technical_specs=i.technical_specs,
                unit=i.unit,
                quantity=float(i.quantity),
                tva_rate=float(i.tva_rate or 20.0),
                warranty_required=i.warranty_required
            )
            for i in t.line_items
        ],
        portal_url=f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{t.portal_id}"
    )

@router.post("/actions", response_model=UserActionResponse)
async def record_user_action(
    req: UserActionRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Records founder actions (shortlist, ignore, applied, won, lost)
    for active learning feedback loop.
    """
    try:
        profile_uuid = uuid.UUID(req.profile_id)
    except ValueError:
        profile_uuid = uuid.uuid4()

    stmt = select(Tender).where(Tender.portal_id == req.tender_id)
    res = await session.execute(stmt)
    tender = res.scalar_one_or_none()

    tender_uuid = tender.id if tender else uuid.uuid4()

    action = UserTenderAction(
        profile_id=profile_uuid,
        tender_id=tender_uuid,
        action=req.action,
        feedback_notes=req.feedback_notes,
        bid_amount_mad=req.bid_amount_mad
    )
    session.add(action)
    await session.commit()
    await session.refresh(action)

    logger.info(f"Recorded action '{req.action}' for tender #{req.tender_id}")

    return UserActionResponse(
        action_id=action.id,
        tender_id=req.tender_id,
        action=action.action,
        created_at=action.created_at.isoformat()
    )
