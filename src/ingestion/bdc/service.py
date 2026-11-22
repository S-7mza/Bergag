import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Sequence
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.scraper.client import PortalHttpClient
from src.scraper.listing_spider import ListingSpider
from src.scraper.detail_spider import DetailSpider
from src.ingestion.utils import slugify
from src.ingestion.awards.matcher import compute_compound_ref_key
from src.models.raw import RawIngestionLog
from src.models.tender import Buyer, Tender, LineItem

logger = logging.getLogger(__name__)

class BdcIngestionService:
    """
    Orchestrates the active BDC ingestion pipeline:
    Discovery -> DB Existence Gate -> Detail Fetch -> Raw Snapshot -> DB Upsert.
    """
    def __init__(self, session: AsyncSession, client: Optional[PortalHttpClient] = None):
        self.session = session
        self.client = client
        self.listing_spider = ListingSpider(client) if client else None
        self.detail_spider = DetailSpider(client) if client else None
        self._buyer_cache = {}

    async def tender_exists(self, portal_id: int) -> bool:
        """Checks 1st if a consultation ID already exists in the database"""
        if not portal_id:
            return False
        stmt = select(func.count()).select_from(Tender).where(Tender.portal_id == int(portal_id))
        res = await self.session.execute(stmt)
        return (res.scalar() or 0) > 0

    async def filter_non_existing_ids(self, portal_ids: Sequence[int]) -> List[int]:
        """Filters a collection of IDs to return ONLY non-existing IDs (checks DB 1st)"""
        if not portal_ids:
            return []
        int_ids = [int(p) for p in portal_ids if p is not None]
        if not int_ids:
            return []
        stmt = select(Tender.portal_id).where(Tender.portal_id.in_(int_ids))
        res = await self.session.execute(stmt)
        existing_ids = set(res.scalars().all())
        return [pid for pid in int_ids if pid not in existing_ids]

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

    async def ingest_tender_detail(
        self,
        detail_data: dict,
        raw_log: Optional[RawIngestionLog] = None,
        skip_if_exists: bool = True
    ) -> Tender:
        """Atomically saves raw snapshot and inserts/updates Tender + LineItems into DB"""
        portal_id = int(detail_data["portal_id"])
        reference = (detail_data.get("reference") or "").strip()[:64]
        buyer_name = (detail_data.get("buyer_name") or "Acheteur Inconnu").strip()

        # Check 1st: if tender is already in DB and skip_if_exists is True, return immediately
        stmt = select(Tender).where(Tender.portal_id == portal_id)
        res = await self.session.execute(stmt)
        tender = res.scalar_one_or_none()

        if tender and skip_if_exists:
            logger.info(f"Tender #{portal_id} already exists in database. Skipping duplicate ingestion.")
            return tender

        if raw_log:
            self.session.add(raw_log)

        # Resolve Buyer
        buyer = await self.get_or_create_buyer(buyer_name, detail_data.get("execution_location"))

        # Determine year
        year = datetime.now().year
        if detail_data.get("deadline_at"):
            try:
                year = datetime.fromisoformat(detail_data["deadline_at"]).year
            except Exception:
                pass

        # Standardized compound natural key matching AwardMatcher
        compound_key = compute_compound_ref_key(buyer.official_name, reference, year)[:255]

        def safe_dt(val: Optional[str]) -> datetime:
            if not val:
                return datetime.now(timezone.utc)
            try:
                dt = datetime.fromisoformat(val)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                return datetime.now(timezone.utc)

        published_dt = safe_dt(detail_data.get("published_at"))
        deadline_dt = safe_dt(detail_data.get("deadline_at"))
        main_category = (detail_data.get("main_category") or "Fournitures")[:32]

        if tender:
            # Explicit update requested (skip_if_exists=False)
            tender.deadline_at = deadline_dt
            tender.title = detail_data.get("title", "")
            tender.main_category = main_category
            tender.prestation_type = detail_data.get("prestation_type")
            tender.execution_location = detail_data.get("execution_location")
            tender.attachment_available = detail_data.get("attachment_available", False)
            tender.attachment_url = detail_data.get("attachment_url")
            tender.compound_natural_key = compound_key
            
            # Clear old line items and replace
            stmt_delete = select(LineItem).where(LineItem.tender_id == portal_id)
            old_items = (await self.session.execute(stmt_delete)).scalars().all()
            for old in old_items:
                await self.session.delete(old)
        else:
            # Create new tender
            tender = Tender(
                portal_id=portal_id,
                source_type=(detail_data.get("source_type") or "bdc")[:32],
                reference=reference,
                compound_natural_key=compound_key,
                buyer_id=buyer.id,
                title=detail_data.get("title", ""),
                main_category=main_category,
                prestation_type=detail_data.get("prestation_type"),
                execution_location=detail_data.get("execution_location"),
                published_at=published_dt,
                deadline_at=deadline_dt,
                status="active",
                attachment_available=detail_data.get("attachment_available", False),
                attachment_url=detail_data.get("attachment_url")
            )
            self.session.add(tender)

        await self.session.flush()

        # Insert structured line items
        for item in detail_data.get("line_items", []):
            qty_raw = item.get("quantity", 1.0)
            try:
                qty_dec = Decimal(str(qty_raw if qty_raw is not None else 1.0))
            except Exception:
                qty_dec = Decimal("1.00")

            tva_raw = item.get("tva_rate", 20.0)
            try:
                tva_dec = Decimal(str(tva_raw if tva_raw is not None else 20.0))
            except Exception:
                tva_dec = Decimal("20.00")

            extracted_brand = item.get("extracted_brand")

            line_item = LineItem(
                tender_id=portal_id,
                item_order=int(item.get("item_order", 1)),
                designation=str(item.get("designation") or "Item"),
                technical_specs=item.get("technical_specs"),
                unit=str(item.get("unit") or "U")[:32],
                quantity=qty_dec,
                tva_rate=tva_dec,
                warranty_required=item.get("warranty_required"),
                extracted_brand=str(extracted_brand)[:128] if extracted_brand else None
            )
            self.session.add(line_item)

        await self.session.flush()
        return tender
