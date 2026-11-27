import uuid
import io
import csv
import zipfile
import mimetypes
from urllib.parse import quote
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy import select, desc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.database.session import get_db_session
from src.models.tender import Tender, Buyer, LineItem
from src.models.profile import CompanyProfile, ProfileMatch, UserTenderAction
from src.profiles.loader import load_profile, load_all_profiles, save_profile, delete_profile, DEFAULT_SECTOR_ICONS
from src.profiles.schema import CompanyProfileSchema, CatalogItem, MacroFilters, NegativeConstraints, ScoringWeights
from src.engine.scoring_cascade import ScoringCascadeEngine, invalidate_tender_cache, CascadeEvaluationResult
from src.engine.pricing_helper import PricingHelper
from src.engine.pipeline_manager import pipeline_manager
from src.engine.feedback_manager import feedback_manager
from src.scraper.client import PortalHttpClient
from src.scraper.detail_spider import DetailSpider
from src.scraper.attachment_worker import AttachmentWorker
from src.engine.ai_matching_agent import ai_matching_agent
from src.api.schemas import AIMatchingDiagnosis
from src.api.auth import User, get_current_user, require_role, user_can_access_profile
from src.engine.cancellation_tracker import (
    is_cancellation_notice,
    extract_target_cancelled_reference,
    reconcile_database_cancellations
)
from src.api.schemas import (
    TenderFeedItem, 
    TenderDetailResponse, 
    LineItemSchema, 
    UserActionRequest, 
    UserActionResponse,
    AlignmentFeedbackRequest,
    AlignmentFeedbackResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Procurement Feed"])

ALL_SECTORS_PROFILE = CompanyProfileSchema(
    version="1.0",
    tenant_id="all",
    profile_id="all",
    profile_name="Tous les Secteurs",
    icon="🌐",
    description="Mode Global : Recherche transversale multi-secteurs sans restrictions ni contraintes de profil",
    macro_filters=MacroFilters(
        categories=["Fournitures", "Services", "Travaux"],
        prestation_types=[],
        geographic_coverage={"mode": "national"},
        financial_bands={"min_amount_mad": 0.0, "max_amount_mad": 500000.0},
        minimum_deadline_hours=0
    ),
    catalog=[],
    negative_constraints=NegativeConstraints(keywords=[], disallowed_buyer_types=[]),
    scoring_weights=ScoringWeights(line_item_coverage=0.25, semantic_similarity=0.25, feasibility_proximity=0.25, commercial_attractiveness=0.25)
)

@router.get("/profiles")
async def get_available_profiles(user: User = Depends(get_current_user)):
    """Lists all authorized company profiles with rich metadata, catalog item counts, keywords, and AI scoring weights"""
    profiles = load_all_profiles()
    res = []
    if user_can_access_profile(user, "all"):
        res.append({
            "id": "all",
            "tenant_id": "all",
            "profile_name": "Tous les Secteurs",
            "icon": "🌐",
            "description": "Mode Global : Recherche transversale multi-secteurs sans restrictions de profil",
            "categories": ["Fournitures", "Services", "Travaux"],
            "catalog_count": 0,
            "keywords_count": 0,
            "negative_keywords_count": 0,
            "scoring_mode": "cascade",
            "scoring_weights": {},
            "positive_keywords_sample": [],
            "negative_keywords_sample": [],
            "file_name": "global",
        })
    for p in profiles:
        pid = p.profile_id or p.tenant_id
        if not user_can_access_profile(user, pid):
            continue
        pos_kws = []
        for c in p.catalog:
            pos_kws.extend(getattr(c, "synonyms_fr", []))
            pos_kws.extend(getattr(c, "technical_keywords", []))
        kw_count = sum(
            len(getattr(c, "synonyms_fr", [])) + len(getattr(c, "synonyms_ar", [])) + len(getattr(c, "technical_keywords", []))
            for c in p.catalog
        )
        res.append({
            "id": pid,
            "tenant_id": p.tenant_id,
            "profile_name": p.profile_name,
            "icon": p.icon or DEFAULT_SECTOR_ICONS.get(p.profile_id or "", "🏷️"),
            "description": p.description or f"Secteur {p.profile_name}",
            "categories": p.macro_filters.categories,
            "catalog_count": len(p.catalog),
            "keywords_count": kw_count,
            "negative_keywords_count": len(p.negative_constraints.keywords),
            "scoring_mode": getattr(p, "scoring_mode", "cascade"),
            "scoring_weights": p.scoring_weights.model_dump() if p.scoring_weights else {},
            "positive_keywords_sample": list(dict.fromkeys(pos_kws))[:8],
            "negative_keywords_sample": list(p.negative_constraints.keywords)[:8],
            "file_name": f"{pid}.yaml",
        })
    return res

@router.get("/profiles/{profile_id}")
async def get_profile_detail(profile_id: str, user: User = Depends(get_current_user)):
    """Returns full details of an authorized sector profile including catalog items and weights"""
    if not user_can_access_profile(user, profile_id):
        raise HTTPException(status_code=403, detail=f"Accès refusé au profil '{profile_id}' pour votre compte.")
    if profile_id.lower().strip() in ("all", "tous", "all_sectors", "*"):
        data = ALL_SECTORS_PROFILE.model_dump()
        data["id"] = "all"
        data["icon"] = "🌐"
        data["is_system_global"] = True
        return data
    try:
        profile = load_profile(profile_id)
        data = profile.model_dump()
        data["id"] = profile.profile_id or profile_id
        data["icon"] = profile.icon or DEFAULT_SECTOR_ICONS.get(profile_id, "🏷️")
        return data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Secteur '{profile_id}' non trouvé")

@router.put("/profiles/{profile_id}")
async def update_profile_configuration(
    profile_id: str,
    payload: Dict[str, Any],
    user: User = Depends(require_role(["admin"]))
):
    """Updates an existing sector profile, modifying its keywords, weights, categories, or negative constraints (Admin only)"""
    if profile_id.lower().strip() in ("all", "tous", "all_sectors", "*"):
        raise HTTPException(status_code=400, detail="Le profil global 'Tous les Secteurs' est un profil système non modifiable.")
    try:
        # Preserve or assign tenant_id & profile_id
        if "tenant_id" not in payload:
            payload["tenant_id"] = f"{profile_id}-tenant"
        if "profile_name" not in payload:
            payload["profile_name"] = profile_id.replace("_", " ").title()

        saved = save_profile(payload, profile_id)
        # Invalidate evaluation caches
        _STAGE23_CACHE = getattr(ScoringCascadeEngine, "_STAGE23_CACHE", {})
        if isinstance(_STAGE23_CACHE, dict):
            _STAGE23_CACHE.clear()

        return {
            "success": True,
            "message": f"Secteur '{saved.profile_name}' mis à jour avec succès",
            "profile": saved.model_dump()
        }
    except Exception as e:
        logger.error(f"Error updating profile {profile_id}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Erreur mise à jour secteur: {str(e)}")

@router.post("/profiles")
async def create_new_sector_profile(payload: Dict[str, Any]):
    """Creates a new sector profile with custom keywords, weights, and categories"""
    name = payload.get("profile_name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom du secteur est obligatoire")

    slug = payload.get("id") or re.sub(r'[^a-z0-9_]', '_', name.lower()).strip('_')
    if not slug:
        slug = f"sector_{int(datetime.now().timestamp())}"

    if "tenant_id" not in payload:
        payload["tenant_id"] = f"{slug}-tenant"
    if "macro_filters" not in payload:
        payload["macro_filters"] = {
            "categories": ["Fournitures", "Services", "Travaux"],
            "prestation_types": [],
            "geographic_coverage": {"mode": "national"},
            "financial_bands": {"min_amount_mad": 5000.0, "max_amount_mad": 500000.0},
            "minimum_deadline_hours": 24
        }
    if "catalog" not in payload:
        payload["catalog"] = []
    if "negative_constraints" not in payload:
        payload["negative_constraints"] = {"keywords": [], "disallowed_buyer_types": []}
    if "scoring_weights" not in payload:
        payload["scoring_weights"] = {
            "line_item_coverage": 0.45,
            "semantic_similarity: ": 0.30,
            "feasibility_proximity": 0.15,
            "commercial_attractiveness": 0.10
        }

    try:
        saved = save_profile(payload, slug)
        return {
            "success": True,
            "message": f"Nouveau secteur '{saved.profile_name}' créé avec succès",
            "profile_id": slug,
            "profile": saved.model_dump()
        }
    except Exception as e:
        logger.error(f"Error creating profile: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Erreur création secteur: {str(e)}")

@router.delete("/profiles/{profile_id}")
async def remove_sector_profile(profile_id: str):
    """Deletes a custom sector profile (standard profiles cannot be deleted)"""
    protected = {"all", "it_hardware", "software_data", "cctv_security"}
    if profile_id in protected:
        raise HTTPException(status_code=403, detail="Les secteurs standards du système ne peuvent pas être supprimés")

    success = delete_profile(profile_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Secteur '{profile_id}' introuvable")

    return {"success": True, "message": f"Secteur '{profile_id}' supprimé avec succès"}

def extract_profile_candidate_keywords(profile: CompanyProfileSchema) -> List[str]:
    """
    Extracts high-signal root keywords from profile catalog and prestation types,
    prioritized by catalog item weight (High priority first) to optimize candidate selection.
    """
    from src.engine.feedback_manager import STOPWORDS as EXTENDED_STOPWORDS
    stopwords = set(EXTENDED_STOPWORDS)

    # Collect candidate keywords with their priority weights
    weighted_candidates: Dict[str, float] = {}

    for cat in getattr(profile, "catalog", []):
        cat_weight = float(getattr(cat, "weight", 1.0))
        for phrase in getattr(cat, "synonyms_fr", []):
            cleaned = phrase.strip().lower()
            if len(cleaned) >= 3 and cleaned not in stopwords:
                weighted_candidates[cleaned] = max(weighted_candidates.get(cleaned, 0.0), cat_weight)
                for w in cleaned.split():
                    w_clean = w.strip(" ,.'-")
                    if len(w_clean) >= 3 and w_clean not in stopwords:
                        weighted_candidates[w_clean] = max(weighted_candidates.get(w_clean, 0.0), cat_weight)
        for kw in getattr(cat, "technical_keywords", []):
            kw_clean = kw.strip().lower()
            if len(kw_clean) >= 3 and kw_clean not in stopwords:
                weighted_candidates[kw_clean] = max(weighted_candidates.get(kw_clean, 0.0), cat_weight)

    # Prestation types (high baseline weight 2.5)
    macro_filters = getattr(profile, "macro_filters", None)
    if macro_filters:
        for pt in getattr(macro_filters, "prestation_types", []):
            for w in pt.lower().split():
                w_clean = w.strip(" ,.'-")
                if len(w_clean) >= 4 and w_clean not in stopwords:
                    weighted_candidates[w_clean] = max(weighted_candidates.get(w_clean, 0.0), 2.5)

    # Active Learning: Incorporate top human-confirmed domain keywords
    profile_name = getattr(profile, "profile_name", "")
    if profile_name:
        learned_words = feedback_manager.get_learned_terms(profile_name)
        for lw in learned_words[:25]:
            if lw not in stopwords and len(lw) >= 4:
                weighted_candidates[lw] = max(weighted_candidates.get(lw, 0.0), 3.0)

    # Sort descending by priority weight, then length
    sorted_keywords = sorted(
        weighted_candidates.keys(),
        key=lambda k: (weighted_candidates[k], len(k)),
        reverse=True
    )
    return [k for k in sorted_keywords if len(k) >= 3]


# Discrete interval buckets for tender deadlines (more than / between specific days, not cumulative)
# e.g. "between 1 day and 2 days", "between 2 days and 3 days", etc.
URGENCY_RANGE_MAP: Dict[str, Tuple[int, Optional[int]]] = {
    # < 1 day (closing within next 24 hours: 0 to 1 day)
    "1d": (0, 1),
    "24h": (0, 1),
    "urgent_24h": (0, 1),
    "under_1d": (0, 1),

    # Between 1 day and 2 days (24h to 48h)
    "2d": (1, 2),
    "48h": (1, 2),
    "urgent_48h": (1, 2),
    "1_2d": (1, 2),

    # Between 2 days and 3 days (48h to 72h)
    "3d": (2, 3),
    "72h": (2, 3),
    "2_3d": (2, 3),

    # Between 3 days and 4 days (72h to 96h)
    "4d": (3, 4),
    "96h": (3, 4),
    "3_4d": (3, 4),

    # Between 4 days and 7 days (4 days to 1 week)
    "1w": (4, 7),
    "5d": (4, 7),
    "7d": (4, 7),
    "4_7d": (4, 7),

    # Between 1 week and 2 weeks (7 days to 14 days)
    "2w": (7, 14),
    "14d": (7, 14),
    "1_2w": (7, 14),

    # Between 2 weeks and 1 month (14 days to 30 days)
    "1m": (14, 30),
    "30d": (14, 30),
    "2w_1m": (14, 30),

    # More than 1 month (> 30 days)
    "gt_1m": (30, None),
    "over_1m": (30, None),
    "plus_1m": (30, None)
}

urgency_range_map = URGENCY_RANGE_MAP


@router.get("/feed", response_model=List[TenderFeedItem])
async def get_tender_feed(
    response: Response,
    profile_name: str = Query("it_hardware", description="Profile configuration to score against"),
    min_score: float = Query(0.0, description="Minimum overall alignment score (0-100)"),
    search: Optional[str] = Query(None, description="Search keyword in title, reference, or line items"),
    region: Optional[str] = Query(None, description="Filter by location/region"),
    category: Optional[str] = Query(None, description="Filter by category (Fournitures, Services, etc.)"),
    urgency: Optional[str] = Query(None, description="Urgency / Deadline filter ('1d', '2d', '3d', '4d', '1w', '2w', '1m', 'urgent_24h', 'urgent_48h')"),
    status_filter: Optional[str] = Query("all", description="Status filter: 'all', 'open' (eliminate closed), 'closed'"),
    alignment_filter: Optional[str] = Query("all", description="Filter by expert alignment: 'all', 'aligned' (confirmés alignés), 'misaligned', 'unreviewed')"),
    exclude_closed: bool = Query(False, description="Whether to eliminate closed/expired offers"),
    sort_by: Optional[str] = Query("score_desc", description="Sort criteria (score_desc, score_asc, ai_score_desc, ai_score_asc, deadline_asc, deadline_desc, items_desc, items_asc, id_desc, id_asc)"),
    role: Optional[str] = Query("admin", description="Current user role for RBAC scoping"),
    limit: int = Query(2500, ge=1, le=5000),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """
    Returns dynamically filtered, ranked active procurement opportunities
    scored against the selected profile and scoped by user role & profile RBAC.
    """
    if not user_can_access_profile(user, profile_name):
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : votre compte ({user.role}) n'est pas autorisé à consulter le profil '{profile_name}'."
        )

    effective_role = role if user.role == "admin" else user.role
    is_all_sectors = bool(profile_name and profile_name.lower().strip() in ("all", "tous", "all_sectors", "*"))
    if is_all_sectors:
        profile = ALL_SECTORS_PROFILE
    else:
        try:
            profile = load_profile(profile_name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found")

    scoring_engine = ScoringCascadeEngine()

    # RBAC Enforcement: Viewers only see curated high-confidence opportunities (>=75% GO),
    # unless an explicit search query is provided (user direct keyword search is mandatory)
    effective_min_score = min_score if (search and search.strip()) else (max(min_score, 75.0) if role == "viewer" else min_score)

    # Build candidate selection query
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.status == "active")
    )

    if search and search.strip():
        search_raw = search.strip()
        clean_id_str = search_raw.lstrip('#').strip()

        if clean_id_str.isdigit():
            # Support direct portal ID or reference lookup
            stmt = stmt.where(
                or_(
                    Tender.portal_id == int(clean_id_str),
                    Tender.reference.ilike(f"%{clean_id_str}%")
                )
            )
        else:
            # Multi-word mandatory keyword search:
            # Every keyword in the user query MUST be present in the tender (AND between words)
            # across any candidate field: title, reference, location, buyer official name, or line items (OR across fields)
            search_words = [w for w in search_raw.split() if w.strip()]
            if search_words:
                word_clauses = []
                for w in search_words:
                    w_pattern = f"%{w.lower()}%"
                    word_clauses.append(
                        or_(
                            Tender.title.ilike(w_pattern),
                            Tender.reference.ilike(w_pattern),
                            Tender.execution_location.ilike(w_pattern),
                            Tender.buyer.has(Buyer.official_name.ilike(w_pattern)),
                            Tender.line_items.any(
                                or_(
                                    LineItem.designation.ilike(w_pattern),
                                    LineItem.technical_specs.ilike(w_pattern)
                                )
                            )
                        )
                    )
                stmt = stmt.where(and_(*word_clauses))
    elif not is_all_sectors:
        # Pre-filter candidates by sector keywords so the cascade scoring evaluates
        # genuine sector opportunities rather than arbitrary unrelated rows (food, fuel, cleaning).
        candidate_kws = extract_profile_candidate_keywords(profile)
        aligned_ids = list(feedback_manager.get_aligned_portal_ids(profile_name))

        if candidate_kws:
            title_conditions = [Tender.title.ilike(f"%{kw}%") for kw in candidate_kws[:40]]
            prestation_conditions = [Tender.prestation_type.ilike(f"%{kw}%") for kw in candidate_kws[:40]]
            line_conditions = [LineItem.designation.ilike(f"%{kw}%") for kw in candidate_kws[:15]]
            match_conditions = [
                *title_conditions,
                *prestation_conditions,
                Tender.line_items.any(or_(*line_conditions))
            ]
            # Ensure tenders confirmed as aligned by the user are ALWAYS included in candidates
            if aligned_ids:
                match_conditions.append(Tender.portal_id.in_(aligned_ids))

            stmt = stmt.where(or_(*match_conditions))
        elif aligned_ids:
            stmt = stmt.where(Tender.portal_id.in_(aligned_ids))

        # Dynamically exclude disjoint prestations only if they do not belong to the active profile
        profile_prestation_str = " ".join(getattr(profile.macro_filters, "prestation_types", [])).lower()
        profile_cat_str = " ".join([getattr(c, "label", "") for c in getattr(profile, "catalog", [])]).lower()
        combined_profile_terms = f"{profile_prestation_str} {profile_cat_str}"

        disjoint_candidates = ["transport", "engin", "citerne", "gardiennage", "denree", "denrée", "terrassement", "gardien"]
        for dp in disjoint_candidates:
            if dp not in combined_profile_terms:
                stmt = stmt.where(~Tender.prestation_type.ilike(f"%{dp}%"))

        # Explicit negative keywords SQL exclusion
        neg_kws = getattr(profile.negative_constraints, "keywords", [])
        if neg_kws:
            for nkw in neg_kws[:15]:
                if len(nkw) >= 4:
                    stmt = stmt.where(~Tender.title.ilike(f"%{nkw}%"))

    if region and region != "all":
        region_list = [r.strip() for r in region.split(",") if r.strip() and r.strip().lower() != "all"]
        if region_list:
            stmt = stmt.where(or_(*[Tender.execution_location.ilike(f"%{r}%") for r in region_list]))

    if category and category != "all":
        cat_clean = category.lower().strip()
        if cat_clean in ("both", "materiel_services", "fournitures_services", "materiel_service", "all_tech"):
            # Include both Fournitures (Matériel) and Services, while excluding Travaux/Civil works
            stmt = stmt.where(Tender.main_category.in_(["Fournitures", "Services"]))
        elif "," in category:
            cats = [c.strip() for c in category.split(",") if c.strip()]
            stmt = stmt.where(or_(*[Tender.main_category.ilike(f"%{c}%") for c in cats]))
        elif cat_clean in ("fournitures", "materiel", "matériel"):
            # Matériel / Fournitures alone
            stmt = stmt.where(or_(Tender.main_category.ilike("%Fourniture%"), Tender.main_category.ilike("%materiel%")))
        elif cat_clean in ("services", "service"):
            # Services alone
            stmt = stmt.where(Tender.main_category.ilike("%Service%"))
        elif cat_clean in ("travaux", "travail"):
            # Travaux alone
            stmt = stmt.where(Tender.main_category.ilike("%Travaux%"))
        else:
            stmt = stmt.where(Tender.main_category.ilike(f"%{category}%"))

    now = datetime.now(timezone.utc)
    is_open_only = (status_filter == "open" or exclude_closed)

    if is_open_only:
        stmt = stmt.where(
            Tender.deadline_at > now,
            Tender.status != "annule",
            Tender.status != "cancelled",
            ~Tender.title.ilike("%annulation%"),
            ~Tender.title.ilike("%annule et remplace%"),
            ~Tender.reference.ilike("DA%")
        )
    elif status_filter == "closed":
        stmt = stmt.where(Tender.deadline_at <= now)
    elif status_filter == "cancelled":
        stmt = stmt.where(
            or_(
                Tender.status.in_(["annule", "cancelled"]),
                Tender.title.ilike("%annulation%"),
                Tender.title.ilike("%annule et remplace%"),
                Tender.reference.ilike("DA%")
            )
        )

    # Multi-selection support for urgency / deadline intervals (e.g. "1_2d,2_3d" or "1d,2d")
    if urgency and urgency.strip() and urgency.strip().lower() != "all":
        raw_keys = [k.strip() for k in urgency.split(",") if k.strip()]
        valid_intervals = [URGENCY_RANGE_MAP[k] for k in raw_keys if k in URGENCY_RANGE_MAP]

        if valid_intervals:
            interval_conditions = []
            for min_days, max_days in valid_intervals:
                min_boundary = now + timedelta(days=min_days) if min_days > 0 else now
                if max_days is not None:
                    max_boundary = now + timedelta(days=max_days)
                    interval_conditions.append(
                        and_(Tender.deadline_at > min_boundary, Tender.deadline_at <= max_boundary)
                    )
                else:
                    interval_conditions.append(Tender.deadline_at > min_boundary)

            if interval_conditions:
                stmt = stmt.where(or_(*interval_conditions))

    # Fetch candidate pool (sized to evaluate all active tenders in DB, up to 5000)
    pool_limit = max(limit, 3000)
    stmt = stmt.order_by(Tender.deadline_at.asc()).limit(pool_limit)

    res = await session.execute(stmt)
    tenders = res.scalars().all()

    # Preload alignment feedback for all sectors or specific profile
    if is_all_sectors:
        aligned_ids = set()
        misaligned_ids = set()
        all_profs = [p.profile_id for p in load_all_profiles()] + ["all"]
        for p_id in all_profs:
            aligned_ids.update(feedback_manager.get_aligned_portal_ids(p_id))
            misaligned_ids.update(feedback_manager.get_misaligned_portal_ids(p_id))
    else:
        aligned_ids = set(feedback_manager.get_aligned_portal_ids(profile_name))
        misaligned_ids = set(feedback_manager.get_misaligned_portal_ids(profile_name))

    # Score all candidates against profile
    scored_items: List[TenderFeedItem] = []
    for t in tenders:
        tender_dict = {
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

        # Deep AI diagnosis against Programming, Web, Data & AI profile
        ai_diag = ai_matching_agent.get_cached_diagnosis(t.portal_id)
        if ai_diag is None:
            ai_diag = ai_matching_agent.diagnose_tender_dict(tender_dict)

        if is_all_sectors:
            hours_left = (t.deadline_at - now).total_seconds() / 3600.0 if t.deadline_at else 999.0
            is_urgent = 0 < hours_left < 24.0

            user_feedback = None
            if t.portal_id in aligned_ids:
                user_feedback = "aligned"
            elif t.portal_id in misaligned_ids:
                user_feedback = "misaligned"

            if t.status in ("annule", "annulé", "cancelled") or is_cancellation_notice(t.title, t.reference):
                decision_verdict = "ANNULÉ"
                overall_score = 0.0
            elif hours_left <= 0:
                decision_verdict = "CLÔTURÉ"
                overall_score = 0.0
            elif user_feedback == "misaligned":
                decision_verdict = "NO-GO"
                overall_score = 20.0
            elif user_feedback == "aligned":
                decision_verdict = "GO"
                overall_score = 100.0
            elif is_urgent:
                decision_verdict = "CONSIDER"
                overall_score = 75.0
            else:
                decision_verdict = "GO"
                overall_score = 100.0

            alignment_feedback = user_feedback
        else:
            cascade_res = await scoring_engine.evaluate_tender(tender_dict, profile)

            # Determine verdict: if officially cancelled or an annulation notice, verdict is ANNULÉ
            decision_verdict = cascade_res.decision_recommendation
            if t.status in ("annule", "annulé", "cancelled") or is_cancellation_notice(t.title, t.reference):
                decision_verdict = "ANNULÉ"
                overall_score = 0.0
            else:
                overall_score = cascade_res.overall_score
            alignment_feedback = cascade_res.alignment_feedback

        scored_items.append(
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
                match_score=overall_score,
                decision_verdict=decision_verdict,
                line_item_count=len(t.line_items),
                portal_url=f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{t.portal_id}",
                alignment_feedback=alignment_feedback,
                ai_matching=ai_diag
            )
        )

    # Eliminate closed/expired or cancelled offers if requested
    if is_open_only:
        scored_items = [
            item for item in scored_items 
            if item.decision_verdict not in ("CLÔTURÉ", "ANNULÉ")
            and not is_cancellation_notice(item.title, item.reference)
        ]
    elif status_filter == "closed":
        scored_items = [
            item for item in scored_items 
            if item.decision_verdict == "CLÔTURÉ"
        ]
    elif status_filter == "cancelled":
        scored_items = [
            item for item in scored_items 
            if item.decision_verdict == "ANNULÉ" or is_cancellation_notice(item.title, item.reference)
        ]

    # Compute comprehensive sector statistics across all scored candidate items
    total_candidates = len(scored_items)
    count_ge_80 = sum(1 for item in scored_items if item.match_score >= 80.0)
    count_ge_50 = sum(1 for item in scored_items if item.match_score >= 50.0)
    count_aligned = sum(1 for item in scored_items if item.alignment_feedback == "aligned")

    # Set response metadata headers for frontend badges
    response.headers["X-Total-Count"] = str(total_candidates)
    response.headers["X-Count-Ge-80"] = str(count_ge_80)
    response.headers["X-Count-Ge-50"] = str(count_ge_50)
    response.headers["X-Count-Aligned"] = str(count_aligned)

    # Filter by expert alignment or minimum score
    if alignment_filter == "aligned":
        feed_items = [item for item in scored_items if item.alignment_feedback == "aligned"]
    elif alignment_filter == "misaligned":
        feed_items = [item for item in scored_items if item.alignment_feedback == "misaligned"]
    elif alignment_filter == "unreviewed":
        feed_items = [item for item in scored_items if not item.alignment_feedback and item.match_score >= effective_min_score]
    else:
        # Default 'all': filter by effective minimum score
        feed_items = [item for item in scored_items if item.match_score >= effective_min_score]

    # Helper extractors for multi-criteria sorting
    def get_ai_score(item) -> float:
        if item.ai_matching:
            if hasattr(item.ai_matching, "matching_rate"):
                return float(item.ai_matching.matching_rate or 0.0)
            elif isinstance(item.ai_matching, dict):
                return float(item.ai_matching.get("matching_rate", 0.0) or 0.0)
        return 0.0

    def parse_deadline_dt(item) -> datetime:
        try:
            return datetime.strptime(item.deadline_at, "%d/%m/%Y %H:%M")
        except Exception:
            return datetime.max

    # Sorting
    if sort_by == "ai_score_desc":
        # Top AI score first, with tie-break on rule match_score and portal_id
        feed_items.sort(key=lambda x: (get_ai_score(x), x.match_score, x.portal_id), reverse=True)
    elif sort_by == "ai_score_asc":
        feed_items.sort(key=lambda x: (get_ai_score(x), x.match_score, x.portal_id))
    elif sort_by == "score_asc":
        feed_items.sort(key=lambda x: (x.match_score, get_ai_score(x), x.portal_id))
    elif sort_by == "deadline_asc":
        feed_items.sort(key=parse_deadline_dt)
    elif sort_by == "deadline_desc":
        feed_items.sort(key=parse_deadline_dt, reverse=True)
    elif sort_by == "items_desc":
        feed_items.sort(key=lambda x: (x.line_item_count, x.match_score), reverse=True)
    elif sort_by == "items_asc":
        feed_items.sort(key=lambda x: (x.line_item_count, x.match_score))
    elif sort_by == "id_desc":
        feed_items.sort(key=lambda x: x.portal_id, reverse=True)
    elif sort_by == "id_asc":
        feed_items.sort(key=lambda x: x.portal_id)
    else:  # default "score_desc"
        feed_items.sort(key=lambda x: (x.match_score, get_ai_score(x), x.portal_id), reverse=True)

    return feed_items[:limit]

@router.post("/reconcile-cancellations")
async def trigger_cancellation_reconciliation(
    session: AsyncSession = Depends(get_db_session)
):
    """
    Scans for cancellation notices and cross-links them to previous tenders published
    by the same public buyer, marking the previous tenders as cancelled ('annule').
    """
    result = await reconcile_database_cancellations(session)
    return {
        "success": True,
        "message": f"Réconciliation des annulations : {result['notices_tagged']} avis d'annulation marqués, {result['targets_cancelled']} offres cibles annulées.",
        "details": result
    }

@router.get("/tenders/{portal_id}", response_model=TenderDetailResponse)
async def get_tender_detail(
    portal_id: int,
    profile_name: str = Query("it_hardware", description="Profile configuration to score against"),
    session: AsyncSession = Depends(get_db_session)
):
    """Returns full details, specifications, line items, and real-time decision scoring for a tender"""
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.portal_id == portal_id)
    )
    res = await session.execute(stmt)
    t = res.scalar_one_or_none()

    if not t:
        raise HTTPException(status_code=404, detail=f"Tender #{portal_id} not found")

    tender_dict = {
        "portal_id": t.portal_id,
        "reference": t.reference,
        "title": t.title,
        "buyer_name": t.buyer.official_name if t.buyer else "Inconnu",
        "execution_location": t.execution_location,
        "main_category": t.main_category,
        "prestation_type": t.prestation_type,
        "published_at": t.published_at.isoformat(),
        "deadline_at": t.deadline_at.isoformat(),
        "status": t.status,
        "line_items": [
            {
                "item_order": item.item_order,
                "designation": item.designation,
                "technical_specs": item.technical_specs,
                "unit": item.unit or "U",
                "quantity": float(item.quantity) if item.quantity is not None else 1.0,
                "tva_rate": float(item.tva_rate or 20.0),
                "warranty_required": item.warranty_required
            }
            for item in t.line_items
        ]
    }

    is_all_sectors = bool(profile_name and profile_name.lower().strip() in ("all", "tous", "all_sectors", "*"))
    if is_all_sectors:
        profile = ALL_SECTORS_PROFILE
    else:
        try:
            profile = load_profile(profile_name)
        except FileNotFoundError:
            try:
                profile = load_profile("it_hardware")
            except FileNotFoundError:
                profile = load_all_profiles()[0]

    scoring_engine = ScoringCascadeEngine()
    if is_all_sectors:
        aligned_ids = set()
        misaligned_ids = set()
        all_profs = [p.profile_id for p in load_all_profiles()] + ["all"]
        for p_id in all_profs:
            aligned_ids.update(feedback_manager.get_aligned_portal_ids(p_id))
            misaligned_ids.update(feedback_manager.get_misaligned_portal_ids(p_id))

        user_feedback = None
        if t.portal_id in aligned_ids:
            user_feedback = "aligned"
        elif t.portal_id in misaligned_ids:
            user_feedback = "misaligned"

        now_utc = datetime.now(timezone.utc)
        hours_left = (t.deadline_at - now_utc).total_seconds() / 3600.0 if t.deadline_at else 999.0
        is_urgent = 0 < hours_left < 24.0

        if t.status in ("annule", "annulé", "cancelled") or is_cancellation_notice(t.title, t.reference):
            score = 0.0
            verdict = "ANNULÉ"
        elif hours_left <= 0:
            score = 0.0
            verdict = "CLÔTURÉ"
        elif user_feedback == "misaligned":
            score = 20.0
            verdict = "NO-GO"
        elif user_feedback == "aligned":
            score = 100.0
            verdict = "GO"
        elif is_urgent:
            score = 75.0
            verdict = "CONSIDER"
        else:
            score = 100.0
            verdict = "GO"

        cascade_res = CascadeEvaluationResult(
            overall_score=score,
            decision_recommendation=verdict,
            coverage_score=1.0,
            lexical_score=1.0,
            feasibility_score=1.0,
            line_item_matches=[],
            red_flags=["⚠️ Consultation sous délai court (< 24h restantes)"] if is_urgent else [],
            llm_reasoning="Mode Global (Tous les Secteurs) : Consultation affichée sans contraintes de profil sectoriel.",
            alignment_feedback=user_feedback,
            learned_exemplar_bonus=0.0
        )
    else:
        cascade_res = await scoring_engine.evaluate_tender(tender_dict, profile)

    # Deep AI Diagnosis against Programming, Web, Data & AI profile
    ai_diag = ai_matching_agent.get_cached_diagnosis(t.portal_id)
    if ai_diag is None:
        ai_diag = ai_matching_agent.diagnose_tender_dict(tender_dict)

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
        attachment_available=bool(t.attachment_available),
        attachment_url=t.attachment_url,
        match_score=cascade_res.overall_score,
        decision_verdict=cascade_res.decision_recommendation,
        coverage_score=cascade_res.coverage_score,
        red_flags=cascade_res.red_flags,
        llm_reasoning=cascade_res.llm_reasoning,
        line_item_evaluations=cascade_res.line_item_matches,
        alignment_feedback=cascade_res.alignment_feedback,
        ai_matching=ai_diag,
        line_items=[
            LineItemSchema(
                item_order=i.item_order,
                designation=i.designation,
                technical_specs=i.technical_specs,
                unit=i.unit or "U",
                quantity=float(i.quantity) if i.quantity is not None else 1.0,
                tva_rate=float(i.tva_rate or 20.0),
                warranty_required=i.warranty_required
            )
            for i in t.line_items
        ],
        portal_url=f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{t.portal_id}"
    )

@router.get("/tenders/{portal_id}/pricing")
async def get_tender_pricing_intelligence(
    portal_id: int,
    target_margin_pct: float = Query(30.0, ge=10.0, le=60.0),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Returns real dual-sided pricing corridor:
    Calculates estimated hardware/labor base cost, floor price (P_floor),
    recommended bid quote, and queries real historical comparables.
    """
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.portal_id == portal_id)
    )
    res = await session.execute(stmt)
    t = res.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail=f"Tender #{portal_id} not found")

    # Estimate hardware/services base cost
    item_count = len(t.line_items) if t.line_items else 1
    # Average base cost estimation based on designation keywords
    title_lower = t.title.lower()
    if any(k in title_lower for k in ["camera", "video", "surveillance", "nvr"]):
        unit_cost = 4500.0
    elif any(k in title_lower for k in ["logiciel", "application", "site", "donnee"]):
        unit_cost = 8000.0
    else:
        unit_cost = 3500.0

    total_qty = sum(float(i.quantity) for i in t.line_items) if t.line_items else 1.0
    base_cost_ht = max(15000.0, min(350000.0, total_qty * unit_cost))

    # Dual-sided pricing calculation
    logistics_cost = 2500.0
    floor_price_ttc = PricingHelper.calculate_floor_price(
        estimated_hardware_cost_ht=base_cost_ht,
        target_margin_percent=0.0, # Break-even floor
        logistics_cost_mad=logistics_cost,
        tva_rate=20.0
    )

    recommended_bid_ttc = PricingHelper.calculate_floor_price(
        estimated_hardware_cost_ht=base_cost_ht,
        target_margin_percent=target_margin_pct,
        logistics_cost_mad=logistics_cost,
        tva_rate=20.0
    )

    gross_margin_mad = recommended_bid_ttc - floor_price_ttc

    # Query historical comparables
    first_word = t.title.split()[0] if t.title else ""
    comparables = await PricingHelper.get_historical_comparables(
        session=session,
        buyer_name=t.buyer.official_name if t.buyer else "",
        title_keyword=first_word,
        limit=3
    )

    return {
        "portal_id": t.portal_id,
        "reference": t.reference,
        "line_item_count": item_count,
        "base_cost_ht": round(base_cost_ht, 2),
        "floor_price_ttc": round(floor_price_ttc, 2),
        "recommended_bid_ttc": round(recommended_bid_ttc, 2),
        "gross_margin_mad": round(gross_margin_mad, 2),
        "target_margin_pct": target_margin_pct,
        "statutory_cap_mad": 500000.0, # Decree 2-22-431 Art. 91
        "is_within_statutory_cap": recommended_bid_ttc <= 500000.0,
        "historical_comparables": comparables
    }

@router.get("/tenders/{portal_id}/export-bordereau")
async def export_bordereau_csv(
    portal_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Exports official Moroccan public procurement Bordereau des Prix (BOM)
    as an Excel-compatible CSV file (utf-8-sig).
    """
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.portal_id == portal_id)
    )
    res = await session.execute(stmt)
    t = res.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail=f"Tender #{portal_id} not found")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Header metadata matching Moroccan TGR administrative standards
    buyer_name = t.buyer.official_name if t.buyer else "Organisme Public"
    writer.writerow(["ROYAUME DU MAROC"])
    writer.writerow([f"ACHETEUR PUBLIC : {buyer_name}"])
    writer.writerow([f"CONSULTATION BDC N° : {t.reference} (ID Portail : #{t.portal_id})"])
    writer.writerow([f"OBJET : {t.title}"])
    writer.writerow([f"DATE LIMITE DE DÉPÔT : {t.deadline_at.strftime('%d/%m/%Y %H:%M')}"])
    writer.writerow([])
    writer.writerow(["BORDEREAU DES PRIX - DÉTAIL ESTIMATIF"])
    writer.writerow([
        "N° Article", 
        "Désignation des Prestations", 
        "Spécifications Techniques", 
        "Unité", 
        "Quantité", 
        "Prix Unitaire HT (DH)", 
        "Taux TVA (%)", 
        "Total HT (DH)", 
        "Total TTC (DH)"
    ])

    for item in t.line_items:
        qty = float(item.quantity)
        tva = float(item.tva_rate or 20.0)
        writer.writerow([
            f"#{item.item_order}",
            item.designation,
            item.technical_specs or "Conforme aux prescriptions techniques",
            item.unit,
            f"{qty:.2f}".replace('.', ','),
            "", # To be filled by estimator
            f"{tva:.0f}%",
            "",
            ""
        ])

    csv_content = "\ufeff" + output.getvalue() # Add UTF-8 BOM for Microsoft Excel
    filename = f"Bordereau_BDC_{t.portal_id}_{t.reference.replace('/', '-')}.csv"

    return Response(
        content=csv_content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/tenders/{portal_id}/attachment/download")
async def download_tender_attachment(
    portal_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Direct 1-click download of the complete consultation archive (.ZIP containing CPS, Bordereau, etc.).
    Bypasses TGR portal authentication and WAF challenges using server-side proxying and local caching.
    """
    stmt = select(Tender).where(Tender.portal_id == portal_id)
    res = await session.execute(stmt)
    t = res.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail=f"Consultation #{portal_id} introuvable.")

    cache_dir = Path("data/attachments")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"tender_{portal_id}.zip"

    # 1. Return from disk cache if already present
    if cache_file.exists() and cache_file.stat().st_size > 0:
        zip_bytes = cache_file.read_bytes()
    else:
        # 2. Check if attachment_url is known; if not, discover it live via DetailSpider
        attachment_url = t.attachment_url
        if not attachment_url:
            client = PortalHttpClient()
            try:
                spider = DetailSpider(client)
                _, detail_data = await spider.fetch_detail(portal_id)
                attachment_url = detail_data.get("attachment_url")
                if attachment_url:
                    t.attachment_available = True
                    t.attachment_url = attachment_url
                    await session.commit()
            except Exception as e:
                logger.warning(f"Failed to auto-discover attachment URL for tender #{portal_id}: {e}")
            finally:
                await client.close()

        if not attachment_url:
            raise HTTPException(
                status_code=404,
                detail="Aucune pièce jointe (CPS / Avis) n'a été déposée par l'acheteur public pour cette consultation."
            )

        # 3. Stream binary directly through PortalHttpClient with active WAF session
        client = PortalHttpClient()
        try:
            zip_bytes = await client.download_binary(attachment_url)
            cache_file.write_bytes(zip_bytes)
        except Exception as e:
            logger.error(f"Error downloading attachment for tender #{portal_id} from portal: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Échec de téléchargement du dossier depuis le portail TGR: {e}"
            )
        finally:
            await client.close()

    clean_ref = t.reference.replace('/', '-').replace(' ', '_')
    filename = f"Dossier_CPS_BDC_{portal_id}_{clean_ref}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.get("/tenders/{portal_id}/attachment/files")
async def get_tender_attachment_files(
    portal_id: int,
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Inspects the consultation archive and lists all documents (CPS PDF, Bordereau, Avis d'achat).
    Allows direct inspection without requiring the user to extract or decompress files locally.
    """
    stmt = select(Tender).where(Tender.portal_id == portal_id)
    res = await session.execute(stmt)
    t = res.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail=f"Consultation #{portal_id} introuvable.")

    cache_dir = Path("data/attachments")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"tender_{portal_id}.zip"

    if not cache_file.exists() or cache_file.stat().st_size == 0:
        if not t.attachment_url and not t.attachment_available:
            return {
                "portal_id": portal_id,
                "available": False,
                "message": "Aucune pièce jointe disponible pour cette consultation.",
                "files": []
            }
        # Pre-fetch and cache archive
        client = PortalHttpClient()
        try:
            attachment_url = t.attachment_url
            if not attachment_url:
                spider = DetailSpider(client)
                _, detail_data = await spider.fetch_detail(portal_id)
                attachment_url = detail_data.get("attachment_url")
                if attachment_url:
                    t.attachment_available = True
                    t.attachment_url = attachment_url
                    await session.commit()
            if attachment_url:
                zip_bytes = await client.download_binary(attachment_url)
                cache_file.write_bytes(zip_bytes)
        except Exception as e:
            logger.warning(f"Could not fetch attachment archive for #{portal_id}: {e}")
            return {
                "portal_id": portal_id,
                "available": False,
                "message": f"Dossier non téléchargeable: {e}",
                "files": []
            }
        finally:
            await client.close()

    if not cache_file.exists() or cache_file.stat().st_size == 0:
        return {
            "portal_id": portal_id,
            "available": False,
            "message": "Archive vide ou introuvable.",
            "files": []
        }

    BROWSER_RENDERABLE_EXTS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".html", ".htm"}
    OFFICE_MIMES = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".ppt": "application/vnd.ms-powerpoint",
        ".txt": "text/plain; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
    }

    files_list = []
    folder_names = set()
    try:
        with zipfile.ZipFile(cache_file, 'r') as zf:
            for member in zf.namelist():
                info = zf.getinfo(member)
                if info.is_dir() or member.startswith("__MACOSX") or member.endswith(".DS_Store"):
                    continue
                base_name = member.split('/')[-1]
                folder = '/'.join(member.split('/')[:-1]) if '/' in member else ""
                if folder:
                    folder_names.add(folder)
                ext = base_name.split('.')[-1].lower() if '.' in base_name else ""
                dot_ext = f".{ext}"
                is_cps = any(k in base_name.lower() for k in ["cps", "cahier", "prescriptions", "specifications"])
                is_browser = dot_ext in BROWSER_RENDERABLE_EXTS

                if dot_ext == ".pdf":
                    target_app = "Navigateur (PDF)"
                    action_label = "Ouvrir directement le PDF"
                    action_type = "browser"
                    icon = "📄"
                elif dot_ext in (".docx", ".doc"):
                    target_app = "Microsoft Word"
                    action_label = "Ouvrir dans Microsoft Word"
                    action_type = "word"
                    icon = "📝"
                elif dot_ext in (".xlsx", ".xls"):
                    target_app = "Microsoft Excel"
                    action_label = "Ouvrir dans Microsoft Excel"
                    action_type = "excel"
                    icon = "📊"
                elif dot_ext in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
                    target_app = "Navigateur (Image)"
                    action_label = "Afficher l'image"
                    action_type = "browser"
                    icon = "🖼️"
                elif dot_ext == ".txt":
                    target_app = "Navigateur (Texte)"
                    action_label = "Lire directement"
                    action_type = "browser"
                    icon = "📋"
                else:
                    target_app = "Application associée"
                    action_label = "Télécharger / Ouvrir"
                    action_type = "generic"
                    icon = "📎"

                # Direct click URL: for browser-renderable formats opens inline; for Word/Office downloads & opens desktop app
                click_url = f"/api/tenders/{portal_id}/attachment/file?path={quote(member)}&inline={'true' if is_browser else 'false'}"

                files_list.append({
                    "filename": base_name,
                    "raw_path": member,
                    "folder": folder,
                    "extension": ext,
                    "size_bytes": info.file_size,
                    "size_formatted": f"{round(info.file_size / 1024, 1)} Ko" if info.file_size < 1048576 else f"{round(info.file_size / (1024 * 1024), 2)} Mo",
                    "is_cps": is_cps,
                    "is_browser_renderable": is_browser,
                    "target_app": target_app,
                    "action_label": action_label,
                    "action_type": action_type,
                    "icon": icon,
                    "click_url": click_url,
                    "direct_url": f"/api/tenders/{portal_id}/attachment/file?path={quote(member)}&inline=true",
                    "download_url": f"/api/tenders/{portal_id}/attachment/file?path={quote(member)}&inline=false",
                    "preview_url": f"/api/tenders/{portal_id}/attachment/text-preview?path={quote(member)}"
                })
    except Exception as e:
        logger.error(f"Error reading archive {cache_file}: {e}")

    return {
        "portal_id": portal_id,
        "available": True,
        "archive_size": cache_file.stat().st_size,
        "archive_size_formatted": f"{round(cache_file.stat().st_size / 1024, 1)} Ko" if cache_file.stat().st_size < 1048576 else f"{round(cache_file.stat().st_size / (1024 * 1024), 2)} Mo",
        "archive_download_url": f"/api/tenders/{portal_id}/attachment/download",
        "portal_direct_url": f"https://www.marchespublics.gov.ma{t.attachment_url}" if t.attachment_url else None,
        "folders": sorted(list(folder_names)),
        "file_count": len(files_list),
        "files": files_list
    }

@router.get("/tenders/{portal_id}/attachment/file")
async def stream_tender_attachment_single_file(
    portal_id: int,
    path: str = Query(..., description="Internal path of the document inside the ZIP archive"),
    inline: bool = Query(True, description="Whether to view file in browser (inline) or download as attachment"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Extracts and streams a single file (e.g. CPS PDF, Word docx) directly from the archive.
    - PDF / TXT / Images: served inline for instant 1-click opening in browser tabs.
    - Word / Excel / Office: served with native application MIME types so clicking triggers Microsoft Word/Excel desktop application.
    """
    cache_dir = Path("data/attachments")
    cache_file = cache_dir / f"tender_{portal_id}.zip"

    # If not cached, trigger archive download first
    if not cache_file.exists():
        await download_tender_attachment(portal_id=portal_id, session=session)

    if not cache_file.exists():
        raise HTTPException(status_code=404, detail="Archive de consultation introuvable.")

    try:
        with zipfile.ZipFile(cache_file, 'r') as zf:
            matching_names = [n for n in zf.namelist() if n == path or n.endswith(path) or path.endswith(n)]
            if not matching_names:
                raise HTTPException(status_code=404, detail=f"Fichier '{path}' introuvable dans l'archive.")
            target_name = matching_names[0]
            file_bytes = zf.read(target_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Fichier '{path}' introuvable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'extraction du document: {e}")

    filename = path.split('/')[-1]
    ext = ('.' + filename.split('.')[-1].lower()) if '.' in filename else ""
    
    OFFICE_MIMES = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".ppt": "application/vnd.ms-powerpoint",
        ".txt": "text/plain; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
    }
    BROWSER_RENDERABLE_EXTS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".html", ".htm"}

    mime_type = OFFICE_MIMES.get(ext)
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"

    # For browser-renderable files, respect inline parameter.
    # For Word/Excel, force attachment so browser hands off to Microsoft Word/Excel!
    if inline and ext in BROWSER_RENDERABLE_EXTS:
        disposition_type = "inline"
    else:
        disposition_type = "attachment"

    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={"Content-Disposition": f'{disposition_type}; filename="{filename}"'}
    )

@router.get("/tenders/{portal_id}/attachment/text-preview")
async def get_attachment_document_text_preview(
    portal_id: int,
    path: str = Query(..., description="Document path inside the ZIP archive"),
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Extracts text and tabular specifications from documents (.docx, .doc, .pdf, .txt)
    allowing instant browser preview without requiring Microsoft Word or desktop applications.
    """
    cache_dir = Path("data/attachments")
    cache_file = cache_dir / f"tender_{portal_id}.zip"

    if not cache_file.exists():
        await download_tender_attachment(portal_id=portal_id, session=session)

    if not cache_file.exists():
        raise HTTPException(status_code=404, detail="Archive introuvable.")

    try:
        with zipfile.ZipFile(cache_file, 'r') as zf:
            matching_names = [n for n in zf.namelist() if n == path or n.endswith(path) or path.endswith(n)]
            if not matching_names:
                raise HTTPException(status_code=404, detail=f"Fichier '{path}' introuvable dans l'archive.")
            target_name = matching_names[0]
            file_bytes = zf.read(target_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'extraction: {e}")

    filename = path.split('/')[-1]
    ext = filename.split('.')[-1].lower() if '.' in filename else ""

    worker = AttachmentWorker()
    if ext == "pdf":
        ef = worker._extract_pdf(file_bytes, filename)
    elif ext == "docx":
        ef = worker._extract_docx(file_bytes, filename)
    elif ext == "doc":
        ef = worker._extract_doc(file_bytes, filename)
    elif ext in ("txt", "json", "csv"):
        text = file_bytes.decode('utf-8', errors='ignore')
        from src.scraper.attachment_worker import ExtractedFile
        ef = ExtractedFile(filename=filename, extension=ext, text=text)
    else:
        raise HTTPException(status_code=400, detail=f"Format .{ext} non prévisualisable en mode texte.")

    return {
        "portal_id": portal_id,
        "filename": filename,
        "extension": ext,
        "is_scanned": ef.is_scanned,
        "ocr_applied": ef.ocr_applied,
        "text": ef.text[:35000], # Up to 35k chars for instant reading
        "text_length": len(ef.text),
        "tables": ef.tables[:15] if ef.tables else []
    }

@router.get("/pipeline")
async def get_team_pipeline(
    action: Optional[str] = Query(None, description="Filter by stage: shortlisted, in_preparation, bidded, won, lost, rejected"),
    session: AsyncSession = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    Returns all opportunities tracked by the team in the procurement pipeline
    (Mes Dossiers: Retenus, En cours de chiffrage, Soumis, Gagnés).
    """
    return await pipeline_manager.get_pipeline_items(session=session, action_filter=action)

@router.post("/actions", response_model=UserActionResponse)
async def record_user_action(
    req: UserActionRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Records or updates a tender's stage in the team pipeline
    (shortlist, in_preparation, bidded, won, lost, rejected).
    """
    entry = await pipeline_manager.record_action(
        portal_id=req.tender_id,
        action=req.action,
        user_notes=req.user_notes,
        bid_amount_mad=req.bid_amount_mad,
        profile_id=req.profile_id,
        session=session,
        tender_metadata=req.tender_metadata
    )
    return UserActionResponse(
        success=True,
        action_id=entry["action_id"],
        action=entry["action"],
        tender_id=entry["portal_id"],
        message=f"Dossier #{req.tender_id} mis à jour : {req.action}"
    )

@router.delete("/pipeline/{portal_id}")
async def remove_from_pipeline(
    portal_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    """Removes a tender from the pipeline tracking"""
    await pipeline_manager.remove_item(portal_id, session=session)
    return {"success": True, "message": f"Dossier #{portal_id} retiré du suivi."}

@router.post("/feed/feedback", response_model=AlignmentFeedbackResponse)
async def submit_alignment_feedback(
    req: AlignmentFeedbackRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Records domain expert alignment feedback on whether an avis fits a business sector/profile.
    - Boosts verified tenders (+15% score, floor 88% GO)
    - Demotes false positive misalignments (caps at 20%, NO-GO)
    - Automatically mines vocabulary to train the active learning model for future searches
    """
    stmt = (
        select(Tender)
        .options(selectinload(Tender.line_items), selectinload(Tender.buyer))
        .where(Tender.portal_id == req.portal_id)
    )
    res = await session.execute(stmt)
    tender = res.scalar_one_or_none()

    title = tender.title if tender else ""
    line_items_text = " ".join(item.designation for item in tender.line_items) if tender else ""

    feedback_entry = feedback_manager.record_feedback(
        portal_id=req.portal_id,
        profile_name=req.profile_name,
        is_aligned=req.is_aligned,
        user_notes=req.user_notes,
        tender_title=title,
        line_items_text=line_items_text
    )

    # Invalidate scoring cache so the new score recalculates with the feedback
    invalidate_tender_cache(req.portal_id, req.profile_name)

    is_all_sectors = bool(req.profile_name and req.profile_name.lower().strip() in ("all", "tous", "all_sectors", "*"))
    if is_all_sectors:
        profile = ALL_SECTORS_PROFILE
    else:
        try:
            profile = load_profile(req.profile_name)
        except FileNotFoundError:
            profile = load_all_profiles()[0]

    scoring_engine = ScoringCascadeEngine()

    tender_dict = {
        "portal_id": req.portal_id,
        "title": title,
        "reference": tender.reference if tender else f"#{req.portal_id}",
        "status": tender.status if tender else "active",
        "prestation_type": tender.prestation_type if tender else "",
        "execution_location": tender.execution_location if tender else "Maroc",
        "line_items": [
            {
                "item_order": i.item_order,
                "designation": i.designation,
                "technical_specs": i.technical_specs,
                "unit": i.unit,
                "quantity": float(i.quantity) if i.quantity is not None else 1.0,
                "tva_rate": float(i.tva_rate or 20.0),
                "warranty_required": i.warranty_required
            }
            for i in (tender.line_items if tender else [])
        ]
    }
    if is_all_sectors:
        score = 100.0 if req.is_aligned else 20.0
        verdict = "GO" if req.is_aligned else "NO-GO"
    else:
        eval_res = await scoring_engine.evaluate_tender(tender_dict, profile)
        score = eval_res.overall_score
        verdict = eval_res.decision_recommendation

    stats = feedback_manager.get_profile_stats(req.profile_name)

    return AlignmentFeedbackResponse(
        success=True,
        portal_id=req.portal_id,
        profile_name=req.profile_name,
        alignment_feedback="aligned" if req.is_aligned else "misaligned",
        updated_score=score,
        updated_verdict=verdict,
        message="Alignement confirmé (+15% score bonifié). Modèle enrichi !" if req.is_aligned else "Avis marqué hors secteur (score neutralisé).",
        learned_terms_count=stats["learned_terms_count"]
    )

@router.delete("/feed/feedback/{portal_id}")
async def delete_alignment_feedback(
    portal_id: int,
    profile_name: str = Query(..., description="Profile name to reset feedback for")
):
    """Resets human feedback for a tender back to neutral AI evaluation"""
    success = feedback_manager.delete_feedback(portal_id, profile_name)
    invalidate_tender_cache(portal_id, profile_name)
    return {"success": success, "portal_id": portal_id, "profile_name": profile_name}

@router.get("/feed/feedback/stats")
async def get_feedback_learning_stats(
    profile_name: str = Query("it_hardware", description="Profile name")
):
    """Returns RLHF alignment statistics and learned vocabulary for the profile"""
    return feedback_manager.get_profile_stats(profile_name)
