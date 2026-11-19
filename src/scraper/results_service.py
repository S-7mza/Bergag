import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.scraper.client import PortalHttpClient
from src.scraper.results_spider import ResultsSpider
from src.engine.award_matcher import AwardMatcher, compute_compound_ref_key
from src.models.raw import RawIngestionLog
from src.models.tender import Award, Tender

logger = logging.getLogger(__name__)

class ResultsService:
    """
    Orchestrates historical results scraping, linking awards to consultations,
    and recording competition pricing benchmarks into the database.
    """
    def __init__(self, session: AsyncSession, client: PortalHttpClient):
        self.session = session
        self.client = client
        self.spider = ResultsSpider(client)
        self.matcher = AwardMatcher(session)

    async def ingest_award(self, award_data: dict, raw_log: Optional[RawIngestionLog] = None) -> Award:
        if raw_log:
            self.session.add(raw_log)

        buyer_name = award_data["buyer_name"] or "Acheteur Inconnu"
        reference = award_data["reference"]
        compound_key = compute_compound_ref_key(buyer_name, reference)

        # Attempt to link with captured consultation
        tender_id = await self.matcher.find_matching_tender(
            buyer_name=buyer_name,
            reference=reference,
            title=award_data["title"],
            published_at=award_data.get("published_at")
        )

        pub_dt = datetime.fromisoformat(award_data["published_at"]) if award_data.get("published_at") else datetime.now()

        # Check existing award by compound_ref_key and winner
        stmt = (
            select(Award)
            .where(Award.compound_ref_key == compound_key)
            .where(Award.winner_name == award_data["winner_name"])
        )
        res = await self.session.execute(stmt)
        award = res.scalar_one_or_none()

        amount = Decimal(str(award_data.get("amount_ttc", 0.0)))
        devis_count = award_data.get("devis_received_count")

        if award:
            # Update existing
            award.amount_ttc = amount
            award.devis_received_count = devis_count
            award.status = award_data["status"]
            if tender_id and not award.tender_id:
                award.tender_id = tender_id
        else:
            # Create new
            award = Award(
                tender_id=tender_id,
                compound_ref_key=compound_key,
                reference=reference,
                buyer_name_raw=buyer_name,
                title_raw=award_data["title"],
                winner_name=award_data["winner_name"],
                amount_ttc=amount,
                devis_received_count=devis_count,
                status=award_data["status"],
                published_at=pub_dt
            )
            self.session.add(award)

        # If tender linked, update tender status accordingly
        if tender_id:
            stmt_tender = select(Tender).where(Tender.portal_id == tender_id)
            tender_res = await self.session.execute(stmt_tender)
            linked_tender = tender_res.scalar_one_or_none()
            if linked_tender:
                linked_tender.status = "attribue" if award_data["status"] == "Attribué" else "infructueux"

        await self.session.flush()
        return award

    async def run_results_sync(self, max_pages: int = 5) -> int:
        """Syncs recent award results and backfills competition benchmarks"""
        total_ingested = 0
        for page in range(1, max_pages + 1):
            try:
                raw_log, awards = await self.spider.fetch_page(page=page)
                self.session.add(raw_log)
                await self.session.commit()

                if not awards:
                    logger.info(f"Results page {page} returned 0 awards. Reached archive end.")
                    break

                for a in awards:
                    try:
                        await self.ingest_award(a)
                        await self.session.commit()
                        total_ingested += 1
                    except Exception as e:
                        logger.error(f"Failed to ingest award {a.get('reference')}: {e}")
                        await self.session.rollback()

            except Exception as e:
                logger.error(f"Failed to crawl results page {page}: {e}")
                break

        return total_ingested

