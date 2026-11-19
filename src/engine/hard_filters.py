import logging
from datetime import datetime, timezone
from typing import Tuple, List
from src.profiles.schema import CompanyProfileSchema

logger = logging.getLogger(__name__)

def evaluate_hard_filters(tender_data: dict, profile: CompanyProfileSchema) -> Tuple[bool, List[str]]:
    """
    Stage 1: Binary Elimination Gate (Cost: $0.00).
    Evaluates mandatory eligibility criteria: status, deadline buffer,
    geographic coverage, and financial capacity.
    
    Returns:
        (is_eligible: bool, rejection_reasons: list[str])
    """
    reasons = []

    # 1. Status Filter
    status = tender_data.get("status", "active").lower()
    if status == "annule":
        reasons.append("Tender is officially cancelled ('Annulé').")

    # 2. Deadline Remaining Buffer
    deadline_at_str = tender_data.get("deadline_at")
    if deadline_at_str:
        try:
            deadline_dt = datetime.fromisoformat(deadline_at_str)
            now_dt = datetime.now(timezone.utc)
            # Normalize to UTC for comparison
            if deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            
            hours_remaining = (deadline_dt - now_dt).total_seconds() / 3600.0
            min_hours = profile.macro_filters.minimum_deadline_hours
            if hours_remaining < min_hours:
                reasons.append(
                    f"Deadline too urgent: {hours_remaining:.1f}h remaining "
                    f"(profile minimum: {min_hours}h)."
                )
        except Exception as e:
            logger.warning(f"Error parsing deadline for hard filter: {e}")

    # 3. Geographic Coverage Filter
    geo = profile.macro_filters.geographic_coverage
    if geo.get("mode") == "regional":
        preferred_regions = [r.lower() for r in geo.get("preferred_regions", [])]
        exec_loc = (tender_data.get("execution_location") or "").lower()
        if preferred_regions and exec_loc:
            matched_geo = any(pref in exec_loc for pref in preferred_regions)
            # If execution location is strictly specified and doesn't match preferred regions
            if not matched_geo and "national" not in exec_loc:
                reasons.append(
                    f"Execution location '{tender_data.get('execution_location')}' "
                    f"is outside target regions: {geo.get('preferred_regions')}."
                )

    # 4. Main Category Filter
    allowed_categories = profile.macro_filters.categories
    tender_cat = tender_data.get("main_category")
    if allowed_categories and tender_cat:
        if tender_cat not in allowed_categories:
            reasons.append(
                f"Main category '{tender_cat}' not allowed by profile "
                f"(allowed: {allowed_categories})."
            )

    is_eligible = len(reasons) == 0
    return is_eligible, reasons

