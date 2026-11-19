import re
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.scraper.client import PortalHttpClient
from src.scraper.listing_spider import ListingSpider
from src.scraper.detail_spider import DetailSpider
from src.models.raw import RawIngestionLog
from src.models.tender import Buyer, Tender, LineItem

logger = logging.getLogger(__name__)

def slugify(text: str) -> str:
    """Normalizes French/Arabic buyer names into a clean URL-safe slug"""
    text = text.lower().strip()
    text = re.sub(r'[àáâãäå]', 'a', text)
    text = re.sub(r'[èéêë]', 'e', text)
    text = re.sub(r'[ìíîï]', 'i', text)
    text = re.sub(r'[òóôõö]', 'o', text)
    text = re.sub(r'[ùúûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

class IngestionService:
    """
    Orchestrates the active BDC ingestion pipeline:
    Discovery -> Change Detection -> Detail Fetch -> Raw Snapshot -> DB Upsert.
    """
    def __init__(self, session: AsyncSession, client: PortalHttpClient):
        self.session = session
        self.client = client
        self.listing_spider = ListingSpider(client)
        self.detail_spider = DetailSpider(client)

    async def get_or_create_buyer(self, official_name: str, location_hint: Optional[str] = None) -> Buyer:
        slug = slugify(official_name)
        if not slug:
            slug = "acheteur-inconnu"

        stmt = select(Buyer).where(Buyer.slug == slug)
        res = await self.session.execute(stmt)
        buyer = res.scalar_one_or_none()

        if not buyer:
            buyer_type = "commune" if "commune" in official_name.lower() else "organisme"
            buyer = Buyer(
                slug=slug,
                official_name=official_name,
                buyer_type=buyer_type,
                city=location_hint
            )
            self.session.add(buyer)
            await self.session.flush()

        return buyer

    async def ingest_tender_detail(self, detail_data: dict, raw_log: Optional[RawIngestionLog] = None) -> Tender:
        """Atomically saves raw snapshot and upserts Tender + LineItems into DB"""
        if raw_log:
            self.session.add(raw_log)

        portal_id = detail_data["portal_id"]
        reference = detail_data["reference"]
        buyer_name = detail_data["buyer_name"] or "Acheteur Inconnu"
        
        # Resolve Buyer
        buyer = await self.get_or_create_buyer(buyer_name, detail_data.get("execution_location"))

        # Determine year
        year = datetime.now().year
        if detail_data.get("deadline_at"):
            try:
                year = datetime.fromisoformat(detail_data["deadline_at"]).year
            except Exception:
                pass

        clean_ref = re.sub(r'[^a-zA-Z0-9]', '-', reference).strip('-')
        compound_key = f"{buyer.slug}:{clean_ref}:{year}"

        # Check existing tender
        stmt = select(Tender).where(Tender.portal_id == portal_id)
        res = await self.session.execute(stmt)
        tender = res.scalar_one_or_none()

        published_dt = datetime.fromisoformat(detail_data["published_at"]) if detail_data.get("published_at") else datetime.now()
        deadline_dt = datetime.fromisoformat(detail_data["deadline_at"]) if detail_data.get("deadline_at") else datetime.now()

        if tender:
            # Update existing tender
            tender.deadline_at = deadline_dt
            tender.title = detail_data["title"]
            tender.main_category = detail_data["main_category"]
            tender.prestation_type = detail_data.get("prestation_type")
            tender.execution_location = detail_data.get("execution_location")
            tender.attachment_available = detail_data.get("attachment_available", False)
            tender.attachment_url = detail_data.get("attachment_url")
            
            # Clear old line items and replace
            stmt_delete = select(LineItem).where(LineItem.tender_id == portal_id)
            old_items = (await self.session.execute(stmt_delete)).scalars().all()
            for old in old_items:
                await self.session.delete(old)
        else:
            # Create new tender
            tender = Tender(
                portal_id=portal_id,
                source_type="bdc",
                reference=reference,
                compound_natural_key=compound_key,
                buyer_id=buyer.id,
                title=detail_data["title"],
                main_category=detail_data["main_category"],
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
            line_item = LineItem(
                tender_id=portal_id,
                item_order=item["item_order"],
                designation=item["designation"],
                technical_specs=item.get("technical_specs"),
                unit=item.get("unit", "U"),
                quantity=Decimal(str(item.get("quantity", 1.0))),
                tva_rate=Decimal(str(item.get("tva_rate", 20.0))),
                warranty_required=item.get("warranty_required")
            )
            self.session.add(line_item)

        await self.session.flush()
        return tender

