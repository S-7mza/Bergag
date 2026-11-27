import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.scraper.ao_spider import AoSpider
from src.engine.buyer_radar import BuyerRadar, LEGAL_BDC_ANNUAL_CEILING_MAD
from src.engine.competitor_radar import CompetitorRadar

SAMPLE_AO_HTML = """
<div class="table-results">
    <tbody>
        <tr id="ligne_1">
            <td class="reference">AO-01/2026</td>
            <td class="objet">Acquisition et installation d'un système de vidéosurveillance urbaine</td>
            <td class="organisme">Commune de Casablanca</td>
            <td class="date-limite">15/04/2026 11:00</td>
            <td><a href="index.php?page=entreprise.EntrepriseDetailConsultation&consultationId=987654">Détail</a></td>
        </tr>
        <tr id="ligne_2">
            <td class="reference">AO-02/2026/Sante</td>
            <td class="objet">Etude et audit des systèmes d'information hospitaliers</td>
            <td class="organisme">Ministère de la Santé</td>
            <td class="date-limite">20/04/2026 14:00</td>
            <td><a href="index.php?page=entreprise.EntrepriseDetailConsultation&consultationId=987655">Détail</a></td>
        </tr>
    </tbody>
</div>
"""

@pytest.fixture
def client():
    return TestClient(app)

def test_ao_spider_parser():
    """Verifies that AoSpider correctly parses formal Marchés Publics listings."""
    mock_client = AsyncMock()
    spider = AoSpider(client=mock_client)
    tenders = spider.parse_ao_listing(SAMPLE_AO_HTML)

    assert len(tenders) == 2
    
    ao1 = tenders[0]
    assert ao1["portal_id"] == 987654
    assert ao1["reference"] == "AO-01/2026"
    assert "vidéosurveillance" in ao1["title"].lower()
    assert ao1["buyer_name"] == "Commune de Casablanca"
    assert ao1["source_type"] == "marche_public"
    assert ao1["main_category"] == "Fournitures"

    ao2 = tenders[1]
    assert ao2["portal_id"] == 987655
    assert ao2["reference"] == "AO-02/2026/Sante"
    assert ao2["main_category"] == "Services"  # detected 'etude'

@pytest.mark.asyncio
async def test_buyer_radar_spending_velocity():
    """Verifies that BuyerRadar detects Article 91 cap exhaustion and triggers the AO alarm."""
    mock_session = AsyncMock()

    # Mock SQL execution return rows: one buyer with 450,000 MAD (90%), another with 100,000 MAD (20%)
    mock_row_critical = MagicMock()
    mock_row_critical.buyer_name_raw = "Commune de Fès"
    mock_row_critical.bdc_count = 12
    mock_row_critical.total_spent_mad = 450000.0
    mock_row_critical.avg_bdc_mad = 37500.0

    mock_row_normal = MagicMock()
    mock_row_normal.buyer_name_raw = "Région Rabat-Salé-Kénitra"
    mock_row_normal.bdc_count = 3
    mock_row_normal.total_spent_mad = 100000.0
    mock_row_normal.avg_bdc_mad = 33333.3

    mock_res = MagicMock()
    mock_res.all.return_value = [mock_row_critical, mock_row_normal]
    mock_session.execute.return_value = mock_res

    radar = BuyerRadar(mock_session)
    stats = await radar.get_buyer_spending_velocity(year=2026)

    assert len(stats) == 2

    # Check critical buyer (>400k MAD triggers upcoming_ao_signal)
    critical = stats[0]
    assert critical["buyer_name"] == "Commune de Fès"
    assert critical["budget_exhaustion_pct"] == 90.0
    assert critical["upcoming_ao_signal"] is True
    assert "CRITICAL" in critical["signal_rationale"]
    assert "Article 91" in critical["signal_rationale"]

    # Check normal buyer
    normal = stats[1]
    assert normal["buyer_name"] == "Région Rabat-Salé-Kénitra"
    assert normal["budget_exhaustion_pct"] == 20.0
    assert normal["upcoming_ao_signal"] is False

@pytest.mark.asyncio
async def test_buyer_radar_seasonality():
    """Verifies monthly spend aggregation and Q4 concentration percentage."""
    mock_session = AsyncMock()

    # 100k in month 3, 100k in month 6, 200k in month 11, 200k in month 12 (Total = 600k, Q4 = 400k = 66.7%)
    row1 = MagicMock(month=3, awards_count=5, monthly_mad=100000.0)
    row2 = MagicMock(month=6, awards_count=5, monthly_mad=100000.0)
    row3 = MagicMock(month=11, awards_count=10, monthly_mad=200000.0)
    row4 = MagicMock(month=12, awards_count=10, monthly_mad=200000.0)

    mock_res = MagicMock()
    mock_res.all.return_value = [row1, row2, row3, row4]
    mock_session.execute.return_value = mock_res

    radar = BuyerRadar(mock_session)
    seasonality = await radar.get_seasonality_radar()

    assert len(seasonality["monthly_distribution"]) == 4
    assert seasonality["q4_concentration_pct"] == pytest.approx(66.7, abs=0.1)
    assert "Q4 (Oct-Dec) represents 66.7%" in seasonality["seasonality_insight"]

@pytest.mark.asyncio
async def test_competitor_radar_top_winners():
    """Verifies competitor ranking queries."""
    mock_session = AsyncMock()

    row1 = MagicMock(
        winner_name="SOCIETE MAROCAINE DE SECURITE SARL",
        total_wins=15,
        total_awarded_mad=3500000.0,
        avg_contract_mad=233333.3,
        total_devis=48
    )

    mock_res = MagicMock()
    mock_res.all.return_value = [row1]
    mock_session.execute.return_value = mock_res

    radar = CompetitorRadar(mock_session)
    top = await radar.get_top_competitors(limit=5)

    assert len(top) == 1
    assert top[0]["winner_name"] == "SOCIETE MAROCAINE DE SECURITE SARL"
    assert top[0]["total_wins"] == 15
    assert top[0]["total_awarded_mad"] == 3500000.0
    assert top[0]["total_devis"] == 48

def test_api_analytics_endpoints(client):
    """Tests FastAPI /api/analytics endpoints with mocked radar calls."""
    with patch("src.api.routes.analytics.CompetitorRadar.get_top_competitors") as mock_top, \
         patch("src.api.routes.analytics.CompetitorRadar.get_competitor_profile") as mock_profile, \
         patch("src.api.routes.analytics.BuyerRadar.get_buyer_spending_velocity") as mock_buyers, \
         patch("src.api.routes.analytics.BuyerRadar.get_seasonality_radar") as mock_seas:

        mock_top.return_value = [
            {"winner_name": "TECH DATA SARL", "total_wins": 8, "total_awarded_mad": 1200000.0, "avg_contract_mad": 150000.0, "avg_competition_density": 2.5}
        ]
        mock_profile.return_value = {
            "winner_name": "TECH DATA SARL",
            "found": True,
            "total_recorded_wins": 8,
            "total_awarded_mad": 1200000.0,
            "recent_wins": []
        }
        mock_buyers.return_value = [
            {"buyer_name": "Commune de Rabat", "year": 2026, "total_spent_mad": 420000.0, "budget_exhaustion_pct": 84.0, "upcoming_ao_signal": True}
        ]
        mock_seas.return_value = {
            "monthly_distribution": [],
            "q4_concentration_pct": 45.5,
            "seasonality_insight": "Test insight"
        }

        # Test GET /api/analytics/competitors
        res_comp = client.get("/api/analytics/competitors?limit=10")
        assert res_comp.status_code == 200
        comp_data = res_comp.json()
        assert len(comp_data) == 1
        assert comp_data[0]["winner_name"] == "TECH DATA SARL"

        # Test GET /api/analytics/competitors/{name}
        res_prof = client.get("/api/analytics/competitors/TECH DATA SARL")
        assert res_prof.status_code == 200
        prof_data = res_prof.json()
        assert prof_data["total_recorded_wins"] == 8

        # Test GET /api/analytics/buyers
        res_buyers = client.get("/api/analytics/buyers?year=2026")
        assert res_buyers.status_code == 200
        buyer_data = res_buyers.json()
        assert len(buyer_data) == 1
        assert buyer_data[0]["upcoming_ao_signal"] is True

        # Test GET /api/analytics/seasonality
        res_seas = client.get("/api/analytics/seasonality")
        assert res_seas.status_code == 200
        seas_data = res_seas.json()
        assert seas_data["q4_concentration_pct"] == 45.5


@pytest.mark.asyncio
async def test_competitor_profile_nature_classification_and_sorting():
    from datetime import datetime, timezone
    from src.engine.competitor_radar import classify_award_nature
    from src.models.tender import Award

    assert classify_award_nature("Développement d'une plateforme web") == "Développement & Solutions IT"
    assert classify_award_nature("Achat de matériel informatique") == "Matériel IT, Réseau & Sécurité"
    assert classify_award_nature("Acquisition de mobilier de bureau") == "Achat Produits & Équipements"
    assert classify_award_nature("Prestation de nettoyage des locaux") == "Services & Maintenance"

    mock_session = AsyncMock()
    a1 = MagicMock(
        spec=Award,
        reference="01/2026",
        title_raw="Prestation de maintenance préventive",
        buyer_name_raw="MINISTERE X",
        amount_ttc=50000.0,
        devis_received_count=4,
        published_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    a2 = MagicMock(
        spec=Award,
        reference="02/2026",
        title_raw="Développement d'une application mobile",
        buyer_name_raw="MINISTERE Y",
        amount_ttc=120000.0,
        devis_received_count=3,
        published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    a3 = MagicMock(
        spec=Award,
        reference="03/2026",
        title_raw="Achat de fournitures de bureau",
        buyer_name_raw="MINISTERE Z",
        amount_ttc=30000.0,
        devis_received_count=7,
        published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [a1, a2, a3]
    mock_session.execute.return_value = mock_res

    radar = CompetitorRadar(mock_session)
    profile = await radar.get_competitor_profile("TECH DATA SARL")

    assert profile["found"] is True
    assert len(profile["recent_wins"]) == 3
    natures = [w["nature"] for w in profile["recent_wins"]]
    assert natures == sorted(natures)
    assert len(profile["nature_breakdown"]) == 3

