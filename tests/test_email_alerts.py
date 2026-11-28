import pytest
from pathlib import Path
from src.scraper.parser import parse_detail_page
from src.profiles.loader import load_profile
from src.engine.scoring_cascade import ScoringCascadeEngine
from src.alerts.email_dispatcher import (
    render_decision_card_html,
    render_decision_card_text,
    render_daily_digest_html,
    render_daily_digest_text,
    EmailDispatcher,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def cctv_tender_data():
    fixture_path = FIXTURES_DIR / "detail_409807.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()
    return parse_detail_page(html, portal_id=409807)

@pytest.mark.asyncio
async def test_email_decision_card_rendering_and_dispatch(cctv_tender_data):
    profile = load_profile("cctv_security")
    engine = ScoringCascadeEngine()

    result = await engine.evaluate_tender(cctv_tender_data, profile)

    # 1. Test HTML rendering
    html = render_decision_card_html(cctv_tender_data, result, profile)
    assert "#409807" in html
    assert "06/2026" in html
    assert "Commune rurale de RDADNA O. MALEK" in html
    assert "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/409807" in html
    assert "#tender=409807" in html
    assert "Fiche 60s Interactive" in html
    assert "Consulter l'Avis Portail TGR" in html
    assert "RECOMMENDED GO" in html
    assert "HIKVISION" in html

    # 2. Test Text rendering
    text = render_decision_card_text(cctv_tender_data, result, profile)
    assert "DECISION CARD" in text
    assert "409807" in text
    assert "#tender=409807" in text
    assert "RECOMMENDED GO" in text
    assert "AVIS OFFICIEL PORTAIL TGR" in text

    # 3. Test Async Dispatcher
    from unittest.mock import patch, MagicMock
    mock_smtp_inst = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_inst):
        mock_smtp_inst.__enter__.return_value = mock_smtp_inst
        dispatcher = EmailDispatcher()
        success = await dispatcher.send_decision_card(cctv_tender_data, result, profile)
        assert success is True


@pytest.mark.asyncio
async def test_daily_digest_rendering_and_dispatch():
    items = [
        {
            "portal_id": 415950,
            "reference": "BC-99/2026",
            "title": "Solution professionnelle d'intelligence artificielle générative",
            "buyer_name": "Chambre d'Artisanat Laâyoune",
            "execution_location": "LAAYOUNE",
            "deadline_at": "2026-12-05T11:00:00+00:00",
            "ai_score": 85.0,
            "cascade_score": 76.0,
            "ai_domain": "Intelligence Artificielle & Automatisation",
            "art91_headroom_mad": 320000.0,
            "red_flags": ["Licence perpétuelle souhaitée"],
            "line_items": [
                {"item_order": 1, "designation": "Licence solution IA générative", "quantity": 10, "unit": "licence"}
            ],
        }
    ]
    html = render_daily_digest_html(items, digest_date="2026-11-29", min_score=70.0)
    assert "415950" in html
    assert "IA 85%" in html
    assert "Cascade 76%" in html
    assert "320,000 MAD" in html
    assert "Licence solution IA générative" in html
    assert "https://bergag.nexenflow.com/#tender=415950" in html

    text = render_daily_digest_text(items, digest_date="2026-11-29", min_score=70.0)
    assert "415950" in text
    assert "IA: 85%" in text

    from unittest.mock import patch, MagicMock
    dispatcher = EmailDispatcher()
    # Empty list must skip without sending
    assert await dispatcher.send_daily_digest([], digest_date="2026-11-29", min_score=70.0) is False

    mock_smtp_inst = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp_inst):
        mock_smtp_inst.__enter__.return_value = mock_smtp_inst
        assert await dispatcher.send_daily_digest(items, digest_date="2026-11-29", min_score=70.0) is True


@pytest.mark.asyncio
async def test_run_daily_digest_job_filters_new_offers_above_70():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch
    from src.scheduler.jobs import run_daily_digest_job
    from src.models.tender import DailyAlertLog

    future = datetime.now(timezone.utc) + timedelta(days=3)

    t_already_sent = SimpleNamespace(
        portal_id=1001, reference="R1", title="Développement portail web Laravel React",
        buyer=SimpleNamespace(official_name="Ministère A"), execution_location="RABAT",
        main_category="Services", prestation_type="Développement logiciel", status="active",
        deadline_at=future,
        line_items=[SimpleNamespace(item_order=1, designation="Développement portail web & API", technical_specs="React FastAPI PostgreSQL", quantity=1, unit="F")],
    )
    t_low_score = SimpleNamespace(
        portal_id=1002, reference="R2", title="Fourniture de ciment et gravette",
        buyer=SimpleNamespace(official_name="Commune B"), execution_location="FES",
        main_category="Travaux", prestation_type="Travaux", status="active",
        deadline_at=future,
        line_items=[SimpleNamespace(item_order=1, designation="Ciment CPJ45", technical_specs="Sac 50kg", quantity=100, unit="U")],
    )
    t_new_high = SimpleNamespace(
        portal_id=1003, reference="R3", title="Développement plateforme BI Datawarehouse & Python FastAPI",
        buyer=SimpleNamespace(official_name="Agence C"), execution_location="CASABLANCA",
        main_category="Services", prestation_type="Génie logiciel et Data BI", status="active",
        deadline_at=future,
        line_items=[SimpleNamespace(item_order=1, designation="Plateforme décisionnelle BI PowerBI Python", technical_specs="ETL Datawarehouse FastAPI PostgreSQL", quantity=1, unit="F")],
    )

    mock_session = MagicMock()
    sent_res = MagicMock()
    sent_res.scalars.return_value.all.return_value = [1001]  # 1001 already sent previously
    tenders_res = MagicMock()
    tenders_res.scalars.return_value.all.return_value = [t_already_sent, t_low_score, t_new_high]
    mock_session.execute = AsyncMock(side_effect=[sent_res, tenders_res])
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    class _Ctx:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_dispatcher = MagicMock()
    fake_dispatcher.recipient = "hamza@bergag.ma"
    fake_dispatcher.send_daily_digest = AsyncMock(return_value=True)

    with patch("src.engine.opportunity_xyz.fetch_market_context_for_tender", new=AsyncMock(return_value={"buyer_spent_ytd_mad": 100000.0})):
        res = await run_daily_digest_job(
            min_score=70.0,
            digest_date="2026-11-29",
            session_factory=lambda: _Ctx(),
            email_dispatcher=fake_dispatcher,
        )

    assert res["sent"] is True
    assert res["count"] == 1
    sent_items = fake_dispatcher.send_daily_digest.call_args[0][0]
    assert [i["portal_id"] for i in sent_items] == [1003]
    assert mock_session.add.call_count == 1
    added_log = mock_session.add.call_args[0][0]
    assert isinstance(added_log, DailyAlertLog)
    assert added_log.portal_id == 1003
    assert added_log.digest_date == "2026-11-29"


@pytest.mark.asyncio
async def test_email_history_manager_and_admin_endpoints(tmp_path):
    from unittest.mock import patch, AsyncMock
    from fastapi.testclient import TestClient
    from src.alerts.email_dispatcher import EmailHistoryManager
    from src.api.main import app
    from src.api.auth import create_session_token

    mgr = EmailHistoryManager(ledger_path=tmp_path / "email_history.json")
    entry = await mgr.record(
        email_type="daily_digest",
        recipient="admin@bergag.ma",
        subject="Digest Test 08h00",
        status="sent",
        html_content="<html><body><h1>Digest</h1></body></html>",
        text_content="Digest",
        portal_ids=[415950, 415635],
    )
    assert entry["offers_count"] == 2

    history = await mgr.list_history(limit=10)
    assert len(history) == 1
    assert "html_content" not in history[0]
    assert history[0]["subject"] == "Digest Test 08h00"

    detail = await mgr.get_detail(entry["id"])
    assert detail is not None
    assert "<h1>Digest</h1>" in detail["html_content"]

    token = create_session_token("admin@bergag.ma", "admin")
    client = TestClient(app)
    with patch("src.alerts.email_dispatcher.email_history_manager", mgr):
        res_list = client.get("/api/admin/emails/history", headers={"Authorization": f"Bearer {token}"})
        assert res_list.status_code == 200
        assert res_list.json()["count"] == 1

        res_detail = client.get(f"/api/admin/emails/history/{entry['id']}", headers={"Authorization": f"Bearer {token}"})
        assert res_detail.status_code == 200
        assert "<h1>Digest</h1>" in res_detail.json()["email"]["html_content"]

