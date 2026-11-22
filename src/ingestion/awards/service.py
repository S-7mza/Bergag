import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.scraper.client import PortalHttpClient
from src.scraper.results_spider import ResultsSpider
from src.ingestion.awards.matcher import AwardMatcher, compute_compound_ref_key
from src.ingestion.utils import slugify
from src.models.raw import RawIngestionLog
from src.models.tender import Award, Tender, Buyer

logger = logging.getLogger(__name__)

class AwardsIngestionService:
    """
    Dedicated domain service for Awards & Results ingestion:
    - Atomically ingests award records into the 'awards' table
    - Normalizes compound reference keys
    - Cross-links awards with existing active/closed Tenders
    - Updates Tender lifecycle status ('attribue', 'infructueux')
    - Resolves public buyer entities
    """
    def __init__(self, session: AsyncSession, client: Optional[PortalHttpClient] = None):
        self.session = session
        self.client = client
        self.spider = ResultsSpider(client) if client else None
        self.matcher = AwardMatcher(session)
        self._buyer_cache = {}

    async def get_or_create_buyer(self, official_name: str, location_hint: Optional[str] = None) -> Buyer:
        slug = slugify(official_name)[:255]
        if slug in self._buyer_cache:
            return self._buyer_cache[slug]

        stmt = select(Buyer).where(Buyer.slug == slug)
        res = await self.session.execute(stmt)
        buyer = res.scalar_one_or_none()

        if not buyer:
            buyer_type = "commune" if "commune" in official_name.lower() else "organisme"
            buyer = Buyer(
                slug=slug,
                official_name=official_name,
                buyer_type=buyer_type[:64],
                city=location_hint[:64] if location_hint else None
            )
            self.session.add(buyer)
            await self.session.flush()

        self._buyer_cache[slug] = buyer
        return buyer

    async def ingest_award(self, award_data: dict, raw_log: Optional[RawIngestionLog] = None) -> Award:
        """
        Idempotently inserts or updates an Award notice in the PostgreSQL database.
        Resolves compound natural key, links to canonical Tender if present,
        and ensures transactional consistency.
        """
        if raw_log:
            self.session.add(raw_log)

        buyer_name = (award_data.get("buyer_name") or "Acheteur Inconnu").strip()
        reference = (award_data.get("reference") or "").strip()[:64]
        title = (award_data.get("title") or "").strip()
        winner_name = (award_data.get("winner_name") or "—").strip()
        status = (award_data.get("status") or "Attribué").strip()[:32]

        # 1. Resolve Buyer entity
        await self.get_or_create_buyer(buyer_name)

        # 2. Compute canonical compound key
        compound_key = compute_compound_ref_key(buyer_name, reference)[:255]

        # 3. Attempt multi-pass cross-linking with tender consultation
        tender_id = await self.matcher.find_matching_tender(
            buyer_name=buyer_name,
            reference=reference,
            title=title,
            published_at=award_data.get("published_at")
        )

        # 4. Safe datetime parsing with timezone
        pub_raw = award_data.get("published_at")
        if isinstance(pub_raw, datetime):
            pub_dt = pub_raw if pub_raw.tzinfo else pub_raw.replace(tzinfo=timezone.utc)
        elif isinstance(pub_raw, str):
            try:
                pub_dt = datetime.fromisoformat(pub_raw)
                if not pub_dt.tzinfo:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:
                pub_dt = datetime.now(timezone.utc)
        else:
            pub_dt = datetime.now(timezone.utc)

        # 5. Amount TTC and Devis count
        try:
            amount = Decimal(str(award_data.get("amount_ttc", 0.0) or 0.0))
        except Exception:
            amount = Decimal("0.00")

        devis_count = award_data.get("devis_received_count")
        if devis_count is not None:
            try:
                devis_count = int(devis_count)
            except (ValueError, TypeError):
                devis_count = None

        # 6. Idempotency check: query existing award by compound_ref_key and winner_name
        stmt = (
            select(Award)
            .where(Award.compound_ref_key == compound_key)
            .where(Award.winner_name == winner_name)
        )
        res = await self.session.execute(stmt)
        award = res.scalar_one_or_none()

        if award:
            # Update existing record
            award.amount_ttc = amount
            award.devis_received_count = devis_count
            award.status = status
            award.title_raw = title
            award.buyer_name_raw = buyer_name
            if tender_id and not award.tender_id:
                award.tender_id = tender_id
            logger.debug(f"Updated existing award {compound_key} [{winner_name}]")
        else:
            # Create new award record
            winner_id = award_data.get("winner_identifier")
            award = Award(
                tender_id=tender_id,
                compound_ref_key=compound_key,
                reference=reference,
                buyer_name_raw=buyer_name,
                title_raw=title,
                winner_name=winner_name,
                winner_identifier=str(winner_id)[:64] if winner_id else None,
                amount_ttc=amount,
                devis_received_count=devis_count,
                status=status,
                published_at=pub_dt
            )
            self.session.add(award)
            logger.debug(f"Created new award {compound_key} [{winner_name}] -> #{tender_id or 'unlinked'}")

        # 7. If linked to an active tender, transition its status
        if tender_id:
            stmt_tender = select(Tender).where(Tender.portal_id == tender_id)
            tender_res = await self.session.execute(stmt_tender)
            linked_tender = tender_res.scalar_one_or_none()
            if linked_tender:
                linked_tender.status = "attribue" if status == "Attribué" else "infructueux"

        await self.session.flush()
        return award
