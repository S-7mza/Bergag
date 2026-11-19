import re
import logging
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.scraper.ingestion_service import slugify
from src.models.tender import Buyer, Tender

logger = logging.getLogger(__name__)

def clean_procurement_reference(ref: str) -> Tuple[str, int]:
    """
    Sanitizes messy procurement references (e.g. 'N° 06/2026', '35 / 2026', '178/FONC/2026/UIT')
    and extracts the underlying serial code and 4-digit budget year.
    """
    raw = ref.strip()
    raw = re.sub(r'^(?:n°|no|n\s*:|ref\s*:)\s*', '', raw, flags=re.IGNORECASE).strip()

    # Find 4-digit year (e.g. 2023, 2024, 2025, 2026)
    year_match = re.search(r'\b(202[3-9])\b', raw)
    if year_match:
        year = int(year_match.group(1))
    else:
        year = datetime.now().year

    clean_ref = re.sub(r'[^a-zA-Z0-9]+', '-', raw).strip('-').lower()
    return clean_ref, year

def compute_compound_ref_key(buyer_name: str, reference: str, year: Optional[int] = None) -> str:
    """
    Computes canonical compound key for linking:
    e.g. 'commune-rurale-de-siroua:35-2026:2026'
    """
    buyer_slug = slugify(buyer_name)
    clean_ref, detected_year = clean_procurement_reference(reference)
    final_year = year or detected_year
    return f"{buyer_slug}:{clean_ref}:{final_year}"

class AwardMatcher:
    """
    Resolves unlinked award cards from the Results archive to active/closed
    consultation records in the tenders table using multi-pass matching.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_matching_tender(self, buyer_name: str, reference: str, title: str, published_at: Optional[str] = None) -> Optional[int]:
        clean_ref, year = clean_procurement_reference(reference)
        compound_key = compute_compound_ref_key(buyer_name, reference, year)

        # Pass 1: Exact Compound Key Match
        stmt = select(Tender.portal_id).where(Tender.compound_natural_key == compound_key)
        res = await self.session.execute(stmt)
        portal_id = res.scalar_one_or_none()
        if portal_id:
            logger.debug(f"Award matched (Pass 1 Exact): {compound_key} -> #{portal_id}")
            return portal_id

        # Pass 2: Secondary Clean Reference + Buyer Slug match
        buyer_slug = slugify(buyer_name)
        stmt_buyer = (
            select(Tender.portal_id)
            .join(Buyer, Tender.buyer_id == Buyer.id)
            .where(Buyer.slug == buyer_slug)
            .where(Tender.reference.ilike(f"%{clean_ref}%"))
        )
        res_buyer = await self.session.execute(stmt_buyer)
        portal_id = res_buyer.scalar_one_or_none()
        if portal_id:
            logger.debug(f"Award matched (Pass 2 Buyer+Ref): #{portal_id}")
            return portal_id

        # Pass 3: Fuzzy Trigram Title Match if pg_trgm available
        try:
            stmt_trgm = (
                select(Tender.portal_id)
                .join(Buyer, Tender.buyer_id == Buyer.id)
                .where(Buyer.slug == buyer_slug)
                .where(text("similarity(tenders.title, :title) > 0.70"))
                .params(title=title)
                .limit(1)
            )
            res_trgm = await self.session.execute(stmt_trgm)
            portal_id = res_trgm.scalar_one_or_none()
            if portal_id:
                logger.info(f"Award matched (Pass 3 Trigram Title): #{portal_id}")
                return portal_id
        except Exception:
            # Fallback if executing on an environment without pg_trgm
            pass

        return None

