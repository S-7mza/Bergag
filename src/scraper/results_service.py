import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.scraper.client import PortalHttpClient
from src.ingestion.awards.service import AwardsIngestionService
from src.ingestion.awards.pipeline import AwardsIngestionPipeline
from src.models.raw import RawIngestionLog
from src.models.tender import Award

logger = logging.getLogger(__name__)

class ResultsService:
    """
    Backward-compatibility wrapper delegating to AwardsIngestionService and AwardsIngestionPipeline.
    """
    def __init__(self, session: AsyncSession, client: PortalHttpClient):
        self.session = session
        self.client = client
        self._service = AwardsIngestionService(session, client)
        self.spider = self._service.spider
        self.matcher = self._service.matcher

    async def ingest_award(self, award_data: dict, raw_log: Optional[RawIngestionLog] = None) -> Award:
        return await self._service.ingest_award(award_data, raw_log=raw_log)

    async def run_results_sync(self, max_pages: int = 5) -> int:
        pipeline = AwardsIngestionPipeline(self.client)
        result = await pipeline.run(max_pages=max_pages)
        return result.get("awards_ingested", 0)
