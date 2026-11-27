import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.main import _run_scheduled_check_once
from src.engine.batch_manager import IngestionBatchRecord


def _mock_empty_db_factory():
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_res)

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session
    mock_factory.return_value.__aexit__.return_value = False
    return mock_factory


@pytest.mark.asyncio
async def test_scheduler_triggers_daily_full_sync_when_stale():
    mock_factory = _mock_empty_db_factory()
    with patch("src.database.session.async_session_factory", mock_factory), \
         patch("src.engine.batch_manager.batch_manager") as mock_bm:
        mock_bm.active_batch = None
        mock_bm.batches = []
        mock_bm.execute_active_sync_batch = AsyncMock()
        mock_bm.execute_batch = AsyncMock()

        outcome = await _run_scheduled_check_once()
        assert outcome == "daily_full_sync"
        mock_bm.execute_active_sync_batch.assert_awaited_once()
        mock_bm.execute_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_triggers_hourly_batch_when_daily_done_but_hour_elapsed():
    mock_factory = _mock_empty_db_factory()
    now = datetime.now()
    old_full_sync = IngestionBatchRecord(
        batch_id="B-FULL",
        trigger_type="active_sync_100_pct",
        status="completed",
        started_at=now - timedelta(hours=3),
        completed_at=now - timedelta(hours=3),
    )

    with patch("src.database.session.async_session_factory", mock_factory), \
         patch("src.engine.batch_manager.batch_manager") as mock_bm:
        mock_bm.active_batch = None
        mock_bm.batches = [old_full_sync]
        mock_bm.execute_active_sync_batch = AsyncMock()
        mock_bm.execute_batch = AsyncMock()

        outcome = await _run_scheduled_check_once()
        assert outcome == "hourly_batch"
        mock_bm.execute_batch.assert_awaited_once_with(
            pages=5, trigger_type="scheduled", user_name="Système (Auto)"
        )
        mock_bm.execute_active_sync_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_skips_when_up_to_date():
    mock_factory = _mock_empty_db_factory()
    now = datetime.now()
    recent_full = IngestionBatchRecord(
        batch_id="B-FULL-RECENT",
        trigger_type="active_sync_100_pct",
        status="completed",
        started_at=now - timedelta(minutes=20),
        completed_at=now - timedelta(minutes=15),
    )

    with patch("src.database.session.async_session_factory", mock_factory), \
         patch("src.engine.batch_manager.batch_manager") as mock_bm:
        mock_bm.active_batch = None
        mock_bm.batches = [recent_full]
        mock_bm.execute_active_sync_batch = AsyncMock()
        mock_bm.execute_batch = AsyncMock()

        outcome = await _run_scheduled_check_once()
        assert outcome == "up_to_date"
        mock_bm.execute_active_sync_batch.assert_not_awaited()
        mock_bm.execute_batch.assert_not_awaited()
