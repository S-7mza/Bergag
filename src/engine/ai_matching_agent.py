import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.engine.ai_diagnostician import AIAvisDiagnostician, AIMatchingDiagnosis
from src.models.tender import Tender

logger = logging.getLogger(__name__)

LEDGER_PATH = Path("data/ai_diagnoses_ledger.json")

class AIAvisMatchingAgent:
    """
    Autonomous AI Agent that iterates notice-after-notice ('avis après avis'),
    inspects the full tender text, specifications, and line items without external APIs,
    performs deep technical diagnostics, and directly updates matching rates in the
    database (tables 'company_profiles' and 'profile_matches') with JSON dual-persistence.
    """

    def __init__(self, ledger_file: Optional[Path] = None):
        self.ledger_file = ledger_file or LEDGER_PATH
        self._diagnoses_cache: Dict[int, Dict[str, Any]] = {}
        self._load_ledger()

    def _load_ledger(self):
        """Loads persistent JSON ledger of AI matching diagnoses"""
        if self.ledger_file.exists():
            try:
                with open(self.ledger_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._diagnoses_cache = {int(k): v for k, v in data.items()}
                logger.info(f"Loaded {len(self._diagnoses_cache)} cached AI diagnoses from {self.ledger_file}")
            except Exception as e:
                logger.warning(f"Could not load AI diagnoses ledger: {e}")
                self._diagnoses_cache = {}

    def _persist_ledger(self):
        """Dual-persistence: writes AI matching diagnoses ledger to disk atomically"""
        try:
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.ledger_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._diagnoses_cache, f, ensure_ascii=False, indent=2)
            temp_file.replace(self.ledger_file)
        except Exception as e:
            logger.error(f"Failed to persist AI diagnoses ledger: {e}")

    def get_cached_diagnosis(self, portal_id: int) -> Optional[AIMatchingDiagnosis]:
        """Returns cached diagnosis if available (with in-memory model instance cache)"""
        if not hasattr(self, "_parsed_models_cache"):
            self._parsed_models_cache: Dict[int, AIMatchingDiagnosis] = {}
        if portal_id in self._parsed_models_cache:
            return self._parsed_models_cache[portal_id]
        cached = self._diagnoses_cache.get(portal_id)
        if cached:
            try:
                model = AIMatchingDiagnosis(**cached)
                self._parsed_models_cache[portal_id] = model
                return model
            except Exception:
                return None
        return None

    def diagnose_tender_dict(self, tender_dict: Dict[str, Any], persist: bool = True) -> AIMatchingDiagnosis:
        """Diagnoses a raw tender dictionary and records the result"""
        portal_id = tender_dict.get("portal_id")
        diagnosis = AIAvisDiagnostician.diagnose_tender(tender_dict)
        if portal_id:
            pid = int(portal_id)
            self._diagnoses_cache[pid] = diagnosis.model_dump()
            if hasattr(self, "_parsed_models_cache"):
                self._parsed_models_cache[pid] = diagnosis
            if persist:
                self._persist_ledger()
        return diagnosis

    async def diagnose_single_avis(
        self,
        portal_id: int,
        session: AsyncSession,
        force_refresh: bool = False
    ) -> AIMatchingDiagnosis:
        """
        Deeply inspects a single avis from DB by portal_id.
        """
        if not force_refresh:
            cached = self.get_cached_diagnosis(portal_id)
            if cached:
                return cached

        stmt = (
            select(Tender)
            .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
            .where(Tender.portal_id == portal_id)
        )
        res = await session.execute(stmt)
        tender = res.scalar_one_or_none()

        if not tender:
            raise ValueError(f"Avis / Tender #{portal_id} introuvable dans la base de données")

        tender_dict = self._serialize_tender(tender)
        diagnosis = AIAvisDiagnostician.diagnose_tender(tender_dict)
        self._diagnoses_cache[portal_id] = diagnosis.model_dump()
        self._persist_ledger()
        return diagnosis

    async def diagnose_batch(
        self,
        session: AsyncSession,
        limit: int = 500,
        open_only: bool = False,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Iterates notice after notice ('avis après avis') across the procurement database,
        diagnosing each offer deeply and compiling a comprehensive diagnostic report.
        """
        stmt = (
            select(Tender)
            .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        )
        if open_only:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(
                Tender.deadline_at > now,
                Tender.status != "annule",
                Tender.status != "cancelled"
            )

        stmt = stmt.order_by(Tender.deadline_at.asc()).limit(limit)
        res = await session.execute(stmt)
        tenders = res.scalars().all()

        total_scanned = len(tenders)
        diagnosed_list: List[Dict[str, Any]] = []

        rating_counts = {
            "EXCELLENT_MATCH": 0,
            "STRONG_MATCH": 0,
            "MODERATE_MATCH": 0,
            "LOW_MATCH": 0,
            "MISMATCH": 0
        }
        domain_distribution: Dict[str, int] = {}
        tech_counter: Dict[str, int] = {}

        for t in tenders:
            portal_id = t.portal_id
            if not force_refresh and portal_id in self._diagnoses_cache:
                diag_data = self._diagnoses_cache[portal_id]
                diag = AIMatchingDiagnosis(**diag_data)
            else:
                tender_dict = self._serialize_tender(t)
                diag = AIAvisDiagnostician.diagnose_tender(tender_dict)
                self._diagnoses_cache[portal_id] = diag.model_dump()

            rating_counts[diag.rating_label] = rating_counts.get(diag.rating_label, 0) + 1
            domain_distribution[diag.primary_domain] = domain_distribution.get(diag.primary_domain, 0) + 1

            for tech in diag.detected_technologies:
                tech_counter[tech] = tech_counter.get(tech, 0) + 1

            diagnosed_list.append({
                "portal_id": t.portal_id,
                "reference": t.reference,
                "title": t.title,
                "buyer_name": t.buyer.official_name if t.buyer else "Inconnu",
                "deadline_at": t.deadline_at.strftime("%d/%m/%Y %H:%M") if t.deadline_at else "Non spécifiée",
                "matching_rate": diag.matching_rate,
                "rating_label": diag.rating_label,
                "verdict": diag.verdict,
                "primary_domain": diag.primary_domain,
                "detected_technologies": diag.detected_technologies,
                "strategic_recommendation": diag.strategic_recommendation,
                "summary": diag.diagnostic_summary
            })

        self._persist_ledger()

        # Sort opportunities by matching rate descending
        diagnosed_list.sort(key=lambda x: x["matching_rate"], reverse=True)

        # Top in-demand technologies in the public sector
        top_techs = sorted(tech_counter.items(), key=lambda x: x[1], reverse=True)[:15]

        return {
            "total_scanned": total_scanned,
            "rating_distribution": rating_counts,
            "domain_distribution": domain_distribution,
            "top_technologies": dict(top_techs),
            "top_opportunities": diagnosed_list[:20],
            "all_opportunities": diagnosed_list
        }

    async def sync_avis_diagnoses_to_db(
        self,
        session: AsyncSession,
        profile_name: str = "software_data",
        limit: int = 5000,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Loops on the avis in the database notice after notice ('avis après avis'),
        deeply inspects the details and line-item specs without external APIs,
        and directly updates the matching rates and diagnostics in the PostgreSQL
        database (tables 'company_profiles' and 'profile_matches') with dual-persistence
        fallback in data/ai_diagnoses_ledger.json.
        """
        from decimal import Decimal
        import uuid
        from src.models.profile import CompanyProfile, ProfileMatch
        from src.profiles.loader import load_profile

        # 1. Resolve or create the CompanyProfile database entity
        try:
            profile_obj = load_profile(profile_name)
            profile_yaml = Path(f"src/profiles/configs/{profile_name}.yaml").read_text(encoding="utf-8")
        except Exception:
            profile_yaml = ""
            profile_obj = None

        target_tenant = profile_obj.tenant_id if profile_obj else "hamza-solutions"
        target_name = profile_obj.profile_name if profile_obj else "Software, Web & Data Solutions"

        prof_stmt = select(CompanyProfile).where(
            or_(
                CompanyProfile.tenant_id == target_tenant,
                CompanyProfile.profile_name.ilike(f"%{profile_name}%")
            )
        )
        prof_res = await session.execute(prof_stmt)
        company_profile = prof_res.scalars().first()

        if not company_profile:
            company_profile = CompanyProfile(
                id=uuid.uuid4(),
                tenant_id=target_tenant,
                profile_name=target_name,
                config_yaml=profile_yaml,
                is_active=True
            )
            session.add(company_profile)
            await session.flush()
        else:
            if profile_yaml and company_profile.config_yaml != profile_yaml:
                company_profile.config_yaml = profile_yaml
                company_profile.profile_name = target_name
                await session.flush()

        # 2. Pre-fetch existing matches for this profile
        matches_stmt = select(ProfileMatch).where(ProfileMatch.profile_id == company_profile.id)
        matches_res = await session.execute(matches_stmt)
        existing_matches = {
            getattr(m, "tender_id", getattr(m, "portal_id", None)): m 
            for m in matches_res.scalars().all()
            if getattr(m, "tender_id", getattr(m, "portal_id", None)) is not None
        }

        # 3. Fetch all candidate tenders with full details
        tenders_stmt = (
            select(Tender)
            .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
            .order_by(Tender.deadline_at.asc())
            .limit(limit)
        )
        tenders_res = await session.execute(tenders_stmt)
        tenders = tenders_res.scalars().all()

        total_scanned = len(tenders)
        matches_created = 0
        matches_updated = 0
        rating_distribution: Dict[str, int] = {}
        top_matches: List[Dict[str, Any]] = []

        now_utc = datetime.now(timezone.utc)

        # 4. Loop on the avis notice after notice
        for t in tenders:
            portal_id = t.portal_id
            tender_dict = self._serialize_tender(t)
            diag = AIAvisDiagnostician.diagnose_tender(tender_dict)

            # Dual-persistence cache
            self._diagnoses_cache[portal_id] = diag.model_dump()

            rating_distribution[diag.rating_label] = rating_distribution.get(diag.rating_label, 0) + 1

            overall_val = Decimal(str(diag.matching_rate))
            sem_val = Decimal(str(diag.sub_scores.get("software_programming", 0.0)))
            feas_val = Decimal("100.00" if diag.deliverability_feasibility == "HIGH" else ("60.00" if diag.deliverability_feasibility == "MEDIUM" else "30.00"))
            comm_val = Decimal("100.00" if diag.hardware_dependency == "NONE" else ("60.00" if diag.hardware_dependency == "LOW" else "25.00"))

            line_item_data = {
                "matching_rate": diag.matching_rate,
                "rating_label": diag.rating_label,
                "verdict": diag.verdict,
                "primary_domain": diag.primary_domain,
                "pillar_scores": diag.sub_scores,
                "detected_technologies": diag.detected_technologies,
                "hardware_dependency": diag.hardware_dependency,
                "deliverability_feasibility": diag.deliverability_feasibility
            }
            llm_text = f"{diag.strategic_recommendation}\n\n{diag.diagnostic_summary}"

            match_row = existing_matches.get(portal_id)
            if match_row is None:
                match_row = ProfileMatch(
                    id=uuid.uuid4(),
                    profile_id=company_profile.id,
                    tender_id=portal_id,
                    overall_score=overall_val,
                    coverage_score=overall_val,
                    semantic_score=sem_val,
                    feasibility_score=feas_val,
                    commercial_score=comm_val,
                    decision_recommendation=diag.verdict,
                    line_item_matches=line_item_data,
                    red_flags=diag.red_flags_and_gaps,
                    llm_reasoning=llm_text,
                    evaluated_at=now_utc
                )
                session.add(match_row)
                matches_created += 1
            else:
                match_row.overall_score = overall_val
                match_row.coverage_score = overall_val
                match_row.semantic_score = sem_val
                match_row.feasibility_score = feas_val
                match_row.commercial_score = comm_val
                match_row.decision_recommendation = diag.verdict
                match_row.line_item_matches = line_item_data
                match_row.red_flags = diag.red_flags_and_gaps
                match_row.llm_reasoning = llm_text
                match_row.evaluated_at = now_utc
                matches_updated += 1

            top_matches.append({
                "portal_id": t.portal_id,
                "reference": t.reference,
                "title": t.title,
                "buyer_name": t.buyer.official_name if t.buyer else "Inconnu",
                "matching_rate": diag.matching_rate,
                "rating_label": diag.rating_label,
                "verdict": diag.verdict,
                "primary_domain": diag.primary_domain,
                "detected_technologies": diag.detected_technologies
            })

        await session.commit()
        self._persist_ledger()

        top_matches.sort(key=lambda x: x["matching_rate"], reverse=True)

        logger.info(
            f"AI Matching DB Sync complete: {total_scanned} avis scanned, "
            f"{matches_created} matches created, {matches_updated} updated."
        )

        return {
            "total_scanned": total_scanned,
            "matches_created": matches_created,
            "matches_updated": matches_updated,
            "profile_id": str(company_profile.id),
            "profile_name": company_profile.profile_name,
            "rating_distribution": rating_distribution,
            "top_opportunities": top_matches[:20]
        }

    def _serialize_tender(self, t: Tender) -> Dict[str, Any]:
        """Serializes ORM Tender into standard dictionary for deep diagnosis"""
        return {
            "portal_id": t.portal_id,
            "reference": t.reference,
            "title": t.title,
            "buyer_name": t.buyer.official_name if t.buyer else "Inconnu",
            "execution_location": t.execution_location,
            "main_category": t.main_category,
            "prestation_type": t.prestation_type,
            "published_at": t.published_at.isoformat() if t.published_at else "",
            "deadline_at": t.deadline_at.isoformat() if t.deadline_at else "",
            "status": t.status,
            "line_items": [
                {
                    "item_order": item.item_order,
                    "designation": item.designation,
                    "technical_specs": item.technical_specs,
                    "unit": item.unit,
                    "quantity": float(item.quantity) if item.quantity is not None else 1.0,
                    "tva_rate": float(item.tva_rate or 20.0),
                    "warranty_required": item.warranty_required
                }
                for item in t.line_items
            ]
        }

# Global singleton instance
ai_matching_agent = AIAvisMatchingAgent()
