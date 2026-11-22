import uuid
import io
import csv
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.database.session import get_db_session
from src.models.tender import Tender, Buyer, LineItem
from src.models.profile import CompanyProfile, ProfileMatch, UserTenderAction
from src.profiles.loader import load_profile, load_all_profiles
from src.profiles.schema import CompanyProfileSchema
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.engine.pricing_helper import PricingHelper
from src.engine.pipeline_manager import pipeline_manager
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

def extract_profile_candidate_keywords(profile: CompanyProfileSchema) -> List[str]:
    """
    Extracts high-signal root keywords from profile catalog and prestation types
    to filter candidate tenders from PostgreSQL before scoring.
    """
    stopwords = {
        "pour", "dans", "avec", "sans", "sous", "vers", "chez", "tout", "tous", "toute", "toutes",
        "achat", "achats", "fourniture", "fournitures", "acquisition", "travaux", "service", "services",
        "autre", "autres", "divers", "diverses", "prestation", "prestations", "materiel", "matériel",
        "equipement", "équipement", "equipements", "équipements", "lot", "lots", "d'un", "d'une",
        "des", "les", "une", "par", "sur", "marche", "marché"
    }
    keywords = set()
    for cat in getattr(profile, "catalog", []):
        for phrase in getattr(cat, "synonyms_fr", []):
            cleaned = phrase.strip().lower()
            if len(cleaned) >= 3 and cleaned not in stopwords:
                keywords.add(cleaned)
                for w in cleaned.split():
                    w_clean = w.strip(" ,.'-")
                    if len(w_clean) >= 3 and w_clean not in stopwords:
                        keywords.add(w_clean)
        for kw in getattr(cat, "technical_keywords", []):
            kw_clean = kw.strip().lower()
            if len(kw_clean) >= 3 and kw_clean not in stopwords:
                keywords.add(kw_clean)

    # Prestation types
    macro_filters = getattr(profile, "macro_filters", None)
    if macro_filters:
        for pt in getattr(macro_filters, "prestation_types", []):
            for w in pt.lower().split():
                w_clean = w.strip(" ,.'-")
                if len(w_clean) >= 4 and w_clean not in stopwords:
                    keywords.add(w_clean)

    return [k for k in keywords if len(k) >= 3]


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
    exclude_closed: bool = Query(False, description="Whether to eliminate closed/expired offers"),
    sort_by: Optional[str] = Query("score_desc", description="Sort criteria (score_desc, deadline_asc, items_desc, id_desc)"),
    role: Optional[str] = Query("admin", description="Current user role for RBAC scoping"),
    limit: int = Query(2500, ge=1, le=5000),
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

    # Build candidate selection query
    stmt = (
        select(Tender)
        .options(selectinload(Tender.buyer), selectinload(Tender.line_items))
        .where(Tender.status == "active")
    )

    if search and search.strip():
        search_raw = search.strip()
        search_pattern = f"%{search_raw.lower()}%"
        search_conditions = [
            Tender.title.ilike(search_pattern),
            Tender.reference.ilike(search_pattern),
            Tender.execution_location.ilike(search_pattern),
            Tender.buyer.has(Buyer.name.ilike(search_pattern)),
            Tender.line_items.any(LineItem.designation.ilike(search_pattern))
        ]
        # Support direct portal ID lookup (e.g. "410796" or "#410796")
        clean_id_str = search_raw.lstrip('#').strip()
        if clean_id_str.isdigit():
            search_conditions.append(Tender.portal_id == int(clean_id_str))

        stmt = stmt.where(or_(*search_conditions))
    else:
        # Pre-filter candidates by sector keywords so the cascade scoring evaluates
        # genuine sector opportunities rather than arbitrary unrelated rows (food, fuel, cleaning).
        candidate_kws = extract_profile_candidate_keywords(profile)
        if candidate_kws:
            title_conditions = [Tender.title.ilike(f"%{kw}%") for kw in candidate_kws[:40]]
            prestation_conditions = [Tender.prestation_type.ilike(f"%{kw}%") for kw in candidate_kws[:40]]
            line_conditions = [LineItem.designation.ilike(f"%{kw}%") for kw in candidate_kws[:15]]
            stmt = stmt.where(
                or_(
                    *title_conditions,
                    *prestation_conditions,
                    Tender.line_items.any(or_(*line_conditions))
                )
            )

    if region and region != "all":
        stmt = stmt.where(Tender.execution_location.ilike(f"%{region}%"))

    if category and category != "all":
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

    # Urgency / Deadline filtering (closing in 1d, 2d, 3d, 4d, 1w, 2w, 1m)
    urgency_days_map = {
        "1d": 1,
        "24h": 1,
        "urgent_24h": 1,
        "2d": 2,
        "48h": 2,
        "urgent_48h": 2,
        "3d": 3,
        "72h": 3,
        "4d": 4,
        "96h": 4,
        "5d": 5,
        "1w": 7,
        "7d": 7,
        "2w": 14,
        "14d": 14,
        "1m": 30,
        "30d": 30
    }
    if urgency and urgency in urgency_days_map:
        days_limit = urgency_days_map[urgency]
        stmt = stmt.where(
            Tender.deadline_at > now,
            Tender.deadline_at <= (now + timedelta(days=days_limit))
        )

    # Fetch candidate pool (sized to evaluate all active tenders in DB, up to 5000)
    pool_limit = max(limit, 3000)
    stmt = stmt.order_by(Tender.deadline_at.asc()).limit(pool_limit)

    res = await session.execute(stmt)
    tenders = res.scalars().all()

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

        cascade_res = await scoring_engine.evaluate_tender(tender_dict, profile)

        # Determine verdict: if officially cancelled or an annulation notice, verdict is ANNULÉ
        decision_verdict = cascade_res.decision_recommendation
        if t.status in ("annule", "annulé", "cancelled") or is_cancellation_notice(t.title, t.reference):
            decision_verdict = "ANNULÉ"
            overall_score = 0.0
        else:
            overall_score = cascade_res.overall_score

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
                portal_url=f"https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/{t.portal_id}"
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

    # Set response metadata headers for frontend badges
    response.headers["X-Total-Count"] = str(total_candidates)
    response.headers["X-Count-Ge-80"] = str(count_ge_80)
    response.headers["X-Count-Ge-50"] = str(count_ge_50)

    # Filter by effective minimum score
    feed_items = [item for item in scored_items if item.match_score >= effective_min_score]

    # Sorting
    if sort_by == "deadline_asc":
        feed_items.sort(key=lambda x: x.deadline_at)
    elif sort_by == "items_desc":
        feed_items.sort(key=lambda x: x.line_item_count, reverse=True)
    elif sort_by == "id_desc":
        feed_items.sort(key=lambda x: x.portal_id, reverse=True)
    else:  # "score_desc"
        feed_items.sort(key=lambda x: x.match_score, reverse=True)

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
                "unit": item.unit,
                "quantity": float(item.quantity),
                "tva_rate": float(item.tva_rate or 20.0),
                "warranty_required": item.warranty_required
            }
            for item in t.line_items
        ]
    }

    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        try:
            profile = load_profile("it_hardware")
        except FileNotFoundError:
            profile = load_all_profiles()[0]

    scoring_engine = ScoringCascadeEngine()
    cascade_res = await scoring_engine.evaluate_tender(tender_dict, profile)

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
        match_score=cascade_res.overall_score,
        decision_verdict=cascade_res.decision_recommendation,
        coverage_score=cascade_res.coverage_score,
        red_flags=cascade_res.red_flags,
        llm_reasoning=cascade_res.llm_reasoning,
        line_item_evaluations=cascade_res.line_item_matches,
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
