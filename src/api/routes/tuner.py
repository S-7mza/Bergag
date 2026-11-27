import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.auth import User, require_role
from src.database.session import get_db_session
from src.engine.active_learning import active_tuner
from src.models.tender import Tender
from src.profiles.loader import load_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tuner", tags=["Active Learning Swipe Tuner"])


class SwipeRequest(BaseModel):
    portal_id: int
    profile_id: str = Field(default="special_ai_hybrid")
    decision: str = Field(..., pattern="^(accept|reject|skip)$")
    score_before: float = Field(default=50.0)
    sampling_strategy: str = Field(default="uncertainty_boundary")


class ConfirmRuleRequest(BaseModel):
    profile_id: str = Field(default="special_ai_hybrid")
    rule_type: str = Field(..., pattern="^(keyword|buyer|category|isolated)$")
    rule_value: str = Field(default="")
    portal_id: Optional[int] = None


class ProfileActionRequest(BaseModel):
    profile_id: str = Field(default="special_ai_hybrid")


def _serialize_tender_for_tuner(t: Tender, now_utc: datetime) -> Dict[str, Any]:
    deadline_dt = t.deadline_at
    if deadline_dt and deadline_dt.tzinfo is None:
        deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
    is_closed = bool(t.status != "active" or (deadline_dt and deadline_dt <= now_utc))
    return {
        "portal_id": t.portal_id,
        "reference": t.reference,
        "title": t.title,
        "buyer_name": t.buyer.official_name if t.buyer else "Acheteur Public",
        "execution_location": t.execution_location or "Maroc",
        "main_category": t.main_category or "Fournitures",
        "prestation_type": t.prestation_type or "",
        "status": t.status,
        "is_closed": is_closed,
        "published_at": t.published_at.isoformat() if t.published_at else None,
        "deadline_at": t.deadline_at.isoformat() if t.deadline_at else None,
        "line_items": [
            {
                "item_order": li.item_order,
                "designation": li.designation,
                "quantity": float(li.quantity) if li.quantity is not None else 1.0,
                "unit": li.unit or "U",
                "technical_specs": li.technical_specs or "",
            }
            for li in sorted(t.line_items, key=lambda x: x.item_order)
        ],
    }


@router.get("/cards")
async def get_tuner_cards(
    profile_id: str = Query("special_ai_hybrid", description="Profil cible à affiner"),
    scope: str = Query("all", description="Portée : 'all' (actifs + clos), 'active', 'closed'"),
    limit: int = Query(12, ge=1, le=30),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """
    Returns an actively sampled deck of tender cards (both active and closed)
    prioritized by Information Gain (uncertainty sampling, confirmation probes, hard negatives).
    """
    try:
        profile = load_profile(profile_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

    now_utc = datetime.now(timezone.utc)
    swiped_ids = active_tuner.get_swiped_ids(profile_id)

    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .order_by(desc(Tender.portal_id))
        .limit(220)
    )
    if scope == "active":
        stmt = stmt.where(Tender.status == "active", Tender.deadline_at > now_utc)
    elif scope == "closed":
        stmt = stmt.where((Tender.status != "active") | (Tender.deadline_at <= now_utc))

    if swiped_ids:
        # Exclude already-swiped IDs up to a reasonable chunk
        stmt = stmt.where(Tender.portal_id.notin_(list(swiped_ids)[:500]))

    res = await session.execute(stmt)
    tenders = res.scalars().all()

    candidates = [_serialize_tender_for_tuner(t, now_utc) for t in tenders]
    selected_cards = await active_tuner.select_next_candidates(
        candidates=candidates,
        profile=profile,
        limit=limit,
    )

    stats = active_tuner.get_stats(profile_id)
    return {
        "profile_id": profile_id,
        "profile_name": profile.profile_name,
        "cards": selected_cards,
        "remaining_in_pool": max(0, len(candidates) - len(selected_cards)),
        "stats": stats,
    }


@router.post("/swipe")
async def record_tuner_swipe(
    req: SwipeRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """
    Records a swipe (Right = Accept, Left = Reject, Skip) and applies an online gradient step
    to the profile's feature weights. Triggers confirmation probes on unexpected rejections.
    """
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.portal_id == req.portal_id)
    )
    res = await session.execute(stmt)
    tender = res.scalar_one_or_none()

    if tender:
        tender_data = _serialize_tender_for_tuner(tender, datetime.now(timezone.utc))
    else:
        tender_data = {"portal_id": req.portal_id, "title": "", "line_items": []}

    return active_tuner.record_swipe(
        portal_id=req.portal_id,
        profile_id=req.profile_id,
        decision=req.decision,
        tender_data=tender_data,
        score_before=req.score_before,
        sampling_strategy=req.sampling_strategy,
        user_name=user.full_name,
    )


@router.post("/confirm-rule")
async def confirm_tuner_rule(
    req: ConfirmRuleRequest,
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """Confirms a specific exclusion rule or disambiguation reason after a rejection."""
    return active_tuner.confirm_rejection_rule(
        profile_id=req.profile_id,
        rule_type=req.rule_type,
        rule_value=req.rule_value,
        portal_id=req.portal_id,
    )


@router.post("/undo")
async def undo_tuner_swipe(
    req: ProfileActionRequest,
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """Reverts the last swipe and restores the exact previous weights."""
    return active_tuner.undo_last_swipe(req.profile_id)


@router.get("/stats")
async def get_tuner_stats(
    profile_id: str = Query("special_ai_hybrid"),
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """Returns current Active Learning session telemetry and learned rules."""
    return active_tuner.get_stats(profile_id)


@router.post("/save-logic")
async def save_tuner_logic(
    req: ProfileActionRequest,
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """
    Persists learned criteria and exclusions permanently into the profile YAML configuration
    and clears scoring caches so the main feed reflects the refined logic immediately.
    """
    try:
        return active_tuner.save_logic_to_profile(req.profile_id)
    except Exception as e:
        logger.error(f"[TunerRoute] Failed to save logic: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la sauvegarde : {e}")


@router.post("/reset")
async def reset_tuner_session(
    req: ProfileActionRequest,
    user: User = Depends(require_role(["admin", "analyst"])),
):
    """Resets the active learning session for a profile."""
    return active_tuner.reset_session(req.profile_id)
