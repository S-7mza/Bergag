import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import select, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tender import Tender

logger = logging.getLogger(__name__)

CANCELLATION_TITLE_REGEX = re.compile(
    r"d[\xe9e]cision\s+d[\'\u2019]annulation|"
    r"avis\s+d[\'\u2019]annulation|"
    r"\bannulation\s+(?:de|du|d[\'\u2019]avis)\b|"
    r"annule\s+et\s+remplace|"
    r"^d[\xe9e]cision\s+d[\'\u2019]annul|"
    r"^annulation\b|"
    r"إلغاء\s+(?:طلب\s+العروض|الاستشارة|سند\s+الطلب)|"
    r"قرار\s+إلغاء",
    re.IGNORECASE
)

TARGET_REF_PATTERNS = [
    # 1. Standard: bon(s) de commande(s) / avis d'achat / consultation n° XX/YYYY
    re.compile(
        r"(?:bons?\s+de\s+commandes?|avis(?:\s+d[\'\u2019]achat)?|consultations?)\s*"
        r"(?:sur\s+bons?\s+de\s+commandes?)?\s*"
        r"(?:de\s+bons?\s+de\s+commandes?)?\s*"
        r"(?:n[\xb0\xba\.]?\s*:?\s*|\s+n\s*[\xb0\xba\.]?\s*:?\s*)([A-Za-z0-9_\-\./]+)",
        re.IGNORECASE
    ),
    # 2. Annule et remplace avis d'achat XX/YYYY
    re.compile(
        r"annule\s+et\s+remplace\s+(?:avis\s+(?:d[\'\u2019]achat\s+)?)?(?:n[\xb0\xba\.]?\s*:?\s*)?([A-Za-z0-9_\-\./]+)",
        re.IGNORECASE
    ),
    # 3. Vu le bon de commande N° 68467/2026 or Vu l'avis d'achat relatif au dit bon de commande N°43/2026
    re.compile(
        r"relatif\s+au\s+dit\s+bon\s+de\s+commande\s+N[\xb0\xba\.]?\s*([A-Za-z0-9_\-\./]+)",
        re.IGNORECASE
    ),
    re.compile(
        r"vu\s+le\s+bon\s+de\s+commande\s+N[\xb0\xba\.]?\s*([A-Za-z0-9_\-\./]+)",
        re.IGNORECASE
    )
]

STOP_TARGETS = {"de", "du", "des", "le", "la", "les", "sur", "au", "aux", "par", "avis"}


def is_cancellation_notice(title: Optional[str], reference: Optional[str]) -> bool:
    """
    Returns True if the consultation is itself an administrative cancellation notice
    (Avis d'Annulation / Décision d'Annulation / Annule et Remplace).
    """
    title_clean = (title or "").strip()
    ref_clean = (reference or "").strip()

    if ref_clean.upper().startswith("DA") and len(ref_clean) > 2:
        return True

    return bool(CANCELLATION_TITLE_REGEX.search(title_clean))


def extract_target_cancelled_reference(title: Optional[str], reference: Optional[str]) -> Optional[str]:
    """
    Extracts the previous consultation reference that this cancellation notice revokes.
    Examples:
      - 'Décision d'annulation du bon de commande N°32-2026' -> '32-2026'
      - 'Décision d'annulation d’avis d’achat sur bon de commande n° 13-BC/2026' -> '13-BC/2026'
      - 'FOURNITURES DE MATÉRIEL (Annule et remplace Avis 30/2026)' -> '30/2026'
      - Ref 'DA15-BC/2026' -> '15-BC/2026'
    """
    title_clean = re.sub(r"\s+", " ", title or "").strip()
    ref_clean = (reference or "").strip()

    for pattern in TARGET_REF_PATTERNS:
        match = pattern.search(title_clean)
        if match:
            target = match.group(1).strip(" :.-'\"")
            if len(target) >= 2 and target.lower() not in STOP_TARGETS:
                return target

    # Fallback to DA reference prefix (e.g. DA13-BC/2026 -> 13-BC/2026)
    if ref_clean.upper().startswith("DA") and len(ref_clean) > 3:
        return ref_clean[2:].strip(" -_/")

    return None


async def reconcile_database_cancellations(session: AsyncSession) -> Dict[str, Any]:
    """
    Scans PostgreSQL for all cancellation notices, marks the notices themselves as 'annule',
    and propagates cancellation to any matching target tenders previously published by the same buyer.
    """
    stmt = select(Tender).where(
        or_(
            Tender.title.ilike("%annulation%"),
            Tender.title.ilike("%annul%"),
            Tender.reference.ilike("DA%")
        )
    )
    res = await session.execute(stmt)
    candidates = res.scalars().all()

    notices_tagged = 0
    targets_cancelled = 0
    linked_cancellations: List[Dict[str, Any]] = []

    for t in candidates:
        if is_cancellation_notice(t.title, t.reference):
            if t.status != "annule":
                t.status = "annule"
                notices_tagged += 1

            target_ref = extract_target_cancelled_reference(t.title, t.reference)
            if target_ref:
                # Find previous consultations from the same buyer or matching reference
                target_stmt = select(Tender).where(
                    Tender.portal_id != t.portal_id,
                    or_(
                        Tender.reference == target_ref,
                        Tender.reference.ilike(f"%{target_ref}%"),
                        Tender.compound_natural_key.ilike(f"%{target_ref}%")
                    )
                )
                if t.buyer_id:
                    # Prefer exact buyer match
                    buyer_target_stmt = target_stmt.where(Tender.buyer_id == t.buyer_id)
                    tgt_res = await session.execute(buyer_target_stmt)
                    targets = tgt_res.scalars().all()
                    if not targets:
                        # Fallback to global reference match
                        tgt_res = await session.execute(target_stmt)
                        targets = tgt_res.scalars().all()
                else:
                    tgt_res = await session.execute(target_stmt)
                    targets = tgt_res.scalars().all()

                for tgt in targets:
                    if tgt.status != "annule":
                        tgt.status = "annule"
                        targets_cancelled += 1
                        linked_cancellations.append({
                            "notice_portal_id": t.portal_id,
                            "notice_reference": t.reference,
                            "target_portal_id": tgt.portal_id,
                            "target_reference": tgt.reference,
                            "buyer": t.buyer.official_name if t.buyer else "Inconnu"
                        })

    if notices_tagged > 0 or targets_cancelled > 0:
        await session.commit()
        logger.info(
            f"Cancellation Reconciliation: Tagged {notices_tagged} notices as 'annule', "
            f"propagated cancellation to {targets_cancelled} target tenders."
        )

    return {
        "notices_tagged": notices_tagged,
        "targets_cancelled": targets_cancelled,
        "linked_cancellations": linked_cancellations
    }
