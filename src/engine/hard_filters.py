import logging
from datetime import datetime, timezone
from typing import Tuple, List
from src.profiles.schema import CompanyProfileSchema
from src.engine.cancellation_tracker import is_cancellation_notice

from src.engine.lexical_matcher import strip_accents

logger = logging.getLogger(__name__)

# Moroccan city/province -> official region mapping (accent-stripped lowercase)
_MOROCCO_CITY_TO_REGION = {
    "casablanca": "casablanca-settat", "mohammedia": "casablanca-settat", "settat": "casablanca-settat",
    "el jadida": "casablanca-settat", "berrechid": "casablanca-settat", "nouaceur": "casablanca-settat",
    "benslimane": "casablanca-settat", "mediouna": "casablanca-settat", "sidi bennour": "casablanca-settat",
    "rabat": "rabat-sale-kenitra", "sale": "rabat-sale-kenitra", "kenitra": "rabat-sale-kenitra",
    "temara": "rabat-sale-kenitra", "skhirat": "rabat-sale-kenitra", "khemisset": "rabat-sale-kenitra",
    "sidi kacem": "rabat-sale-kenitra", "sidi slimane": "rabat-sale-kenitra",
    "tanger": "tanger-tetouan-al hoceima", "assilah": "tanger-tetouan-al hoceima",
    "tetouan": "tanger-tetouan-al hoceima", "al hoceima": "tanger-tetouan-al hoceima",
    "hoceima": "tanger-tetouan-al hoceima", "chefchaouen": "tanger-tetouan-al hoceima",
    "larache": "tanger-tetouan-al hoceima", "ouazzane": "tanger-tetouan-al hoceima",
    "marrakech": "marrakech-safi", "safi": "marrakech-safi", "essaouira": "marrakech-safi",
    "al haouz": "marrakech-safi", "haouz": "marrakech-safi", "el kelaa": "marrakech-safi",
    "youssoufia": "marrakech-safi", "chichaoua": "marrakech-safi", "rehamna": "marrakech-safi",
    "fes": "fes-meknes", "meknes": "fes-meknes", "taza": "fes-meknes", "ifrane": "fes-meknes",
    "sefrou": "fes-meknes", "el hajeb": "fes-meknes", "taounate": "fes-meknes", "boulemane": "fes-meknes",
    "agadir": "souss-massa", "inezgane": "souss-massa", "taroudant": "souss-massa",
    "tiznit": "souss-massa", "chtouka": "souss-massa", "tata": "souss-massa",
    "oujda": "oriental", "nador": "oriental", "berkane": "oriental", "driouch": "oriental", "guercif": "oriental",
    "beni mellal": "beni mellal-khenifra", "khenifra": "beni mellal-khenifra", "khouribga": "beni mellal-khenifra",
    "laayoune": "laayoune-sakia el hamra", "dakhla": "dakhla-oued ed-dahab", "oued ed dahab": "dakhla-oued ed-dahab",
    "errachidia": "draa-tafilalet", "ouarzazate": "draa-tafilalet", "tinghir": "draa-tafilalet", "zagora": "draa-tafilalet",
}

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
    preferred_regions = [strip_accents(r) for r in geo.get("preferred_regions", [])]
    exec_loc_raw = tender_data.get("execution_location") or ""
    exec_loc = strip_accents(exec_loc_raw)
    if preferred_regions and exec_loc:
        matched_geo = (
            "national" in exec_loc
            or any(pref in exec_loc for pref in preferred_regions)
            or any(
                city in exec_loc and region in preferred_regions
                for city, region in _MOROCCO_CITY_TO_REGION.items()
            )
        )
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

    # 5. Prestation Type Filter (eliminate fundamentally disjoint public procurement categories)
    allowed_prestations = [p.lower() for p in (getattr(profile.macro_filters, "prestation_types", None) or [])]
    tender_prestation = (tender_data.get("prestation_type") or "").lower()
    if allowed_prestations and tender_prestation:
        # Check for explicitly disjoint Moroccan procurement prestation families
        disjoint_indicators = [
            "transport", "engin", "engins", "citerne", "citernes", "vehicule", "véhicule",
            "carburant", "gasoil", "lubrifiant", "alimentation", "denree", "denrée",
            "gardiennage", "securite des locaux", "nettoyage", "jardinage", "espaces verts",
            "construction", "voirie", "assainissement", "plomberie", "peinture", "maconnerie"
        ]
        if any(ind in tender_prestation for ind in disjoint_indicators):
            reasons.append(
                f"Prestation '{tender_data.get('prestation_type')}' incompatible avec le profil "
                f"({', '.join(profile.macro_filters.prestation_types[:2])})."
            )

    is_eligible = len(reasons) == 0
    return is_eligible, reasons
