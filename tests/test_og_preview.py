import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api.main import app
from src.database.session import get_db_session
from src.models.tender import Buyer, Tender


@pytest.fixture
def client():
    return TestClient(app)


def _mock_db_with_tender(tender_obj):
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = tender_obj
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_res
    return mock_session


def test_default_dashboard_og_tags_and_image(client):
    mock_session = _mock_db_with_tender(None)
    app.dependency_overrides[get_db_session] = lambda: mock_session
    try:
        res = client.get(
            "/",
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "bergag.nexenflow.com",
            },
        )
        assert res.status_code == 200
        assert '<meta property="og:title" content="Bergag • Veille Marchés Publics Maroc &amp; Intelligence IA">' in res.text
        assert '<meta property="og:image" content="https://bergag.nexenflow.com/og-image.png">' in res.text
        assert '<meta property="og:url" content="https://bergag.nexenflow.com/">' in res.text
        assert '<meta name="twitter:card" content="summary_large_image">' in res.text

        img_res = client.get("/og-image.png")
        assert img_res.status_code == 200
        assert img_res.headers["content-type"] == "image/png"
        img = Image.open(io.BytesIO(img_res.content))
        assert img.size == (1200, 630)
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_avis_deep_link_og_tags_and_image(client):
    now = datetime.now(timezone.utc)
    tender = Tender(
        portal_id=777001,
        source_type="bdc",
        reference="BC/WEB/2026",
        compound_natural_key="buyer-web:BC/WEB/2026:2026",
        buyer_id=uuid.uuid4(),
        title="Développement d'une plateforme web et API REST Python",
        main_category="Services",
        prestation_type="Entretien et maintenance de logiciels",
        execution_location="Rabat",
        published_at=now - timedelta(days=1),
        deadline_at=now + timedelta(days=5),
        status="active",
    )
    tender.buyer = Buyer(
        slug="buyer-web",
        official_name="Ministère de la Transition Numérique",
        buyer_type="ministère",
    )

    mock_session = _mock_db_with_tender(tender)
    app.dependency_overrides[get_db_session] = lambda: mock_session
    try:
        res = client.get(
            "/avis/777001",
            headers={
                "x-forwarded-proto": "https",
                "x-forwarded-host": "bergag.nexenflow.com",
            },
        )
        assert res.status_code == 200
        assert "[BC/WEB/2026] Développement d&#x27;une plateforme web et API REST Python" in res.text
        assert "Ministère de la Transition Numérique" in res.text
        assert "Rabat" in res.text
        assert '<meta property="og:image" content="https://bergag.nexenflow.com/og-image/avis/777001.png">' in res.text
        assert '<meta property="og:url" content="https://bergag.nexenflow.com/avis/777001">' in res.text

        img_res = client.get("/og-image/avis/777001.png")
        assert img_res.status_code == 200
        assert img_res.headers["content-type"] == "image/png"
        img = Image.open(io.BytesIO(img_res.content))
        assert img.size == (1200, 630)
    finally:
        app.dependency_overrides.pop(get_db_session, None)
