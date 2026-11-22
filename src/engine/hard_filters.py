import logging
from datetime import datetime, timezone
from typing import Tuple, List
from src.profiles.schema import CompanyProfileSchema
from src.engine.cancellation_tracker import is_cancellation_notice

logger = logging.getLogger(__name__)

def evaluate_hard_filters(tender_data: dict, profile: CompanyProfileSchema) -> Tuple[bool, List[str]]:
    """
    Stage 1: Binary Elimination Gate & Pre-conditions.
    Evaluates mandatory operational criteria: status, submission deadline,
    geographic coverage, and category alignment.
    
    Returns:
        (is_eligible: bool, rejection_reasons: list[str])
    """
    reasons = []

    # 1. Status Filter (both in-place cancellation and published cancellation notices)
    status = (tender_data.get("status") or "active").lower().strip()
    is_cancelled_notice = is_cancellation_notice(tender_data.get("title"), tender_data.get("reference"))
    if status in ("annule", "annulé", "cancelled") or is_cancelled_notice:
        reasons.append("Consultation officiellement annulée par l'acheteur (ou avis de décision d'annulation).")

    # 2. Deadline Remaining Buffer
    deadline_at_str = tender_data.get("deadline_at")
    if deadline_at_str:
        try:
            deadline_dt = datetime.fromisoformat(deadline_at_str)
            now_dt = datetime.now(timezone.utc)
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            
            hours_remaining = (deadline_dt - now_dt).total_seconds() / 3600.0
            min_hours = profile.macro_filters.minimum_deadline_hours

            if hours_remaining <= 0:
                reasons.append("Date limite de dépôt dépassée (Consultation clôturée).")
            elif hours_remaining < min_hours:
                reasons.append(
                    f"Délai de réponse très court ({hours_remaining:.1f}h restantes - minimum profil: {min_hours}h)."
                )
        except Exception as e:
            logger.warning(f"Error parsing deadline for hard filter: {e}")

    # 3. Geographic Coverage Filter
    geo = profile.macro_filters.geographic_coverage
    preferred_regions = [r.lower() for r in geo.get("preferred_regions", [])]
    exec_loc = (tender_data.get("execution_location") or "").lower()
    if preferred_regions and exec_loc:
        matched_geo = any(pref in exec_loc for pref in preferred_regions) or "national" in exec_loc
        if not matched_geo:
            if geo.get("mode") == "regional":
                reasons.append(
                    f"Lieu d'exécution '{tender_data.get('execution_location')}' "
                    f"en dehors des régions cibles: {geo.get('preferred_regions')}."
                )
            else:
                reasons.append(
                    f"Lieu d'exécution '{tender_data.get('execution_location')}' "
                    f"hors territoire prioritaire ({', '.join(geo.get('preferred_regions', []))})."
                )

    # 4. Main Category Filter
    allowed_categories = [c.lower() for c in (profile.macro_filters.categories or [])]
    tender_cat = (tender_data.get("main_category") or "").lower()
    if allowed_categories and tender_cat:
        if tender_cat not in allowed_categories:
            reasons.append(
                f"Catégorie '{tender_data.get('main_category')}' non ciblée "
                f"(profil: {profile.macro_filters.categories})."
            )

    is_eligible = len(reasons) == 0
    return is_eligible, reasons
