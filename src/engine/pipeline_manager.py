import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.profile import UserTenderAction
from src.models.tender import Tender

logger = logging.getLogger(__name__)

STORAGE_FILE = Path("data/pipeline_ledger.json")

class PipelineManager:
    """
    Manages the founder and team procurement pipeline:
    Shortlisted, In Preparation (Chiffrage), Bidded, Won, Lost, and Rejected tenders.
    Dual persistence: PostgreSQL with resilient JSON file fallback.
    """
    def __init__(self):
        self._memory_pipeline: Dict[int, Dict[str, Any]] = {}
        self._load_from_storage()

    def _load_from_storage(self):
        """Loads saved actions from disk fallback"""
        if STORAGE_FILE.exists():
            try:
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._memory_pipeline = {int(k): v for k, v in data.items()}
                logger.info(f"Loaded {len(self._memory_pipeline)} pipeline items from storage.")
            except Exception as e:
                logger.warning(f"Could not read pipeline storage: {e}")
                self._memory_pipeline = {}
        else:
            self._memory_pipeline = {}

    def _save_to_storage(self):
        """Saves pipeline state to disk fallback"""
        try:
            STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._memory_pipeline, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Could not save pipeline to storage: {e}")

    async def record_action(
        self,
        portal_id: int,
        action: str,
        user_notes: Optional[str] = None,
        bid_amount_mad: Optional[float] = None,
        profile_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
        tender_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Records or updates a tender in the user pipeline.
        Saves to memory/disk and syncs with PostgreSQL if available.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        action_id = str(uuid.uuid4())

        # Build pipeline record
        entry = {
            "action_id": action_id,
            "portal_id": portal_id,
            "action": action,
            "user_notes": user_notes or "",
            "bid_amount_mad": float(bid_amount_mad) if bid_amount_mad is not None else None,
            "actioned_at": now_iso,
            "profile_id": profile_id or "00000000-0000-0000-0000-000000000000"
        }

        # Merge any provided tender metadata
        if tender_metadata:
            entry.update({
                "reference": tender_metadata.get("reference", f"BDC/#{portal_id}"),
                "title": tender_metadata.get("title", f"Consultation #{portal_id}"),
                "buyer_name": tender_metadata.get("buyer_name", "Organisme Public"),
                "execution_location": tender_metadata.get("execution_location", "Maroc (National)"),
                "deadline_at": tender_metadata.get("deadline_at", "—"),
                "main_category": tender_metadata.get("main_category", "Fournitures"),
                "match_score": tender_metadata.get("match_score", 85.0)
            })
        elif portal_id in self._memory_pipeline:
            # Preserve existing metadata
            existing = self._memory_pipeline[portal_id]
            for key in ["reference", "title", "buyer_name", "execution_location", "deadline_at", "main_category", "match_score"]:
                if key in existing:
                    entry[key] = existing[key]

        # 1. Save to memory & JSON
        self._memory_pipeline[portal_id] = entry
        self._save_to_storage()

        # 2. Sync to PostgreSQL if session is active
        if session:
            try:
                prof_uuid = uuid.UUID(entry["profile_id"])
                # Look up existing action in DB
                stmt = select(UserTenderAction).where(
                    UserTenderAction.tender_id == portal_id
                )
                res = await session.execute(stmt)
                db_action = res.scalar_one_or_none()

                if db_action:
                    db_action.action = action
                    db_action.user_notes = user_notes
                    db_action.actioned_at = datetime.now(timezone.utc)
                else:
                    new_action = UserTenderAction(
                        id=uuid.UUID(action_id),
                        profile_id=prof_uuid,
                        tender_id=portal_id,
                        action=action,
                        user_notes=user_notes,
                        actioned_at=datetime.now(timezone.utc)
                    )
                    session.add(new_action)
                await session.commit()
            except Exception as e:
                logger.debug(f"DB sync skipped for pipeline action: {e}")

        logger.info(f"Pipeline updated: tender #{portal_id} set to '{action}'")
        return entry

    async def get_pipeline_items(
        self, 
        session: Optional[AsyncSession] = None,
        action_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all active items in the team pipeline.
        Tries DB first, then enriches with memory store.
        """
        items: List[Dict[str, Any]] = []

        if session:
            try:
                stmt = (
                    select(UserTenderAction, Tender)
                    .join(Tender, UserTenderAction.tender_id == Tender.portal_id)
                    .options(selectinload(Tender.buyer))
                    .order_by(desc(UserTenderAction.actioned_at))
                )
                if action_filter and action_filter != "all":
                    stmt = stmt.where(UserTenderAction.action == action_filter)

                res = await session.execute(stmt)
                rows = res.all()

                for act, t in rows:
                    mem_data = self._memory_pipeline.get(t.portal_id, {})
                    items.append({
                        "action_id": str(act.id),
                        "portal_id": t.portal_id,
                        "reference": t.reference,
                        "title": t.title,
                        "buyer_name": t.buyer.official_name if t.buyer else "Organisme Public",
                        "execution_location": t.execution_location or "Maroc (National)",
                        "deadline_at": t.deadline_at.strftime("%d/%m/%Y %H:%M") if t.deadline_at else "—",
                        "main_category": t.main_category,
                        "action": act.action,
                        "user_notes": act.user_notes or mem_data.get("user_notes", ""),
                        "bid_amount_mad": mem_data.get("bid_amount_mad"),
                        "match_score": mem_data.get("match_score", 88.0),
                        "actioned_at": act.actioned_at.strftime("%d/%m/%Y %H:%M") if act.actioned_at else ""
                    })
            except Exception as e:
                logger.debug(f"DB pipeline query fallback to storage: {e}")

        # If DB query returned nothing or session is offline, use memory/disk
        if not items:
            for p_id, item in sorted(
                self._memory_pipeline.items(), 
                key=lambda x: x[1].get("actioned_at", ""), 
                reverse=True
            ):
                if action_filter and action_filter != "all" and item.get("action") != action_filter:
                    continue
                items.append(item)

        return items

    async def remove_item(self, portal_id: int, session: Optional[AsyncSession] = None) -> bool:
        """Removes a tender from the pipeline"""
        if portal_id in self._memory_pipeline:
            del self._memory_pipeline[portal_id]
            self._save_to_storage()

        if session:
            try:
                stmt = select(UserTenderAction).where(UserTenderAction.tender_id == portal_id)
                res = await session.execute(stmt)
                db_action = res.scalar_one_or_none()
                if db_action:
                    await session.delete(db_action)
                    await session.commit()
            except Exception as e:
                logger.debug(f"DB pipeline deletion error: {e}")

        return True

pipeline_manager = PipelineManager()
