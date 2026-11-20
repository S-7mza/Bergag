import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from datetime import datetime

from src.models.tender import Tender, Buyer, LineItem
from src.scraper.ingestion_service import IngestionService


@pytest.mark.asyncio
async def test_ingestion_service_tender_exists():
    mock_session = AsyncMock()
    mock_client = MagicMock()
    service = IngestionService(mock_session, mock_client)

    # Mock count result
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_session.execute.return_value = mock_result

    exists = await service.tender_exists(409807)
    assert exists is True

    mock_result.scalar.return_value = 0
    exists_false = await service.tender_exists(999999)
    assert exists_false is False


@pytest.mark.asyncio
async def test_ingestion_service_filter_non_existing_ids():
    mock_session = AsyncMock()
    mock_client = MagicMock()
    service = IngestionService(mock_session, mock_client)

    # Suppose 409807 and 409808 are in DB, 409809 is not
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [409807, 409808]
    mock_session.execute.return_value = mock_result

    non_existing = await service.filter_non_existing_ids([409807, 409808, 409809])
    assert non_existing == [409809]


@pytest.mark.asyncio
async def test_ingest_tender_detail_skips_when_already_in_db():
    mock_session = AsyncMock()
    mock_client = MagicMock()
    service = IngestionService(mock_session, mock_client)

    # Existing tender in DB
    existing_tender = MagicMock(spec=Tender)
    existing_tender.portal_id = 409807
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_tender
    mock_session.execute.return_value = mock_result

    detail_data = {
        "portal_id": 409807,
        "reference": "BC/01/2026",
        "buyer_name": "Commune Test",
        "title": "Achat matériel",
        "main_category": "Fournitures"
    }

    result = await service.ingest_tender_detail(detail_data, skip_if_exists=True)
    assert result == existing_tender
    # Ensure line items were NOT touched (no delete executed)
    assert mock_session.delete.call_count == 0


@pytest.mark.asyncio
async def test_remediate_missing_portal_ids_checks_db_first():
    from src.engine.batch_manager import IngestionBatchManager

    bm = IngestionBatchManager()
    bm.active_batch = None

    # Mock async session to pretend 409807 is already in DB
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [409807]
    mock_session.execute.return_value = mock_result

    with patch("src.engine.batch_manager.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = mock_session

        # Passing [409807] which is already in DB
        res = await bm.remediate_missing_portal_ids(portal_ids=[409807])
        assert res["status"] == "noop"
        assert res["imported_count"] == 0
        assert "déjà présents en base de données" in res["message"]


@pytest.mark.asyncio
async def test_reconcile_missing_active_tenders_checks_db_first():
    from src.engine.batch_manager import IngestionBatchManager

    bm = IngestionBatchManager()

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [409807, 409808]
    mock_session.execute.return_value = mock_result

    with patch("src.engine.batch_manager.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = mock_session

        res = await bm.reconcile_missing_active_tenders(portal_ids=[409807, 409808])
        assert res["status"] == "noop"
        assert res["imported_count"] == 0
        assert "déjà 100% présents" in res["message"]
