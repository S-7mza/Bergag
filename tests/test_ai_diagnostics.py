import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app
from src.database.session import get_db_session
from src.models.tender import Tender, Buyer, LineItem
from src.engine.ai_diagnostician import AIAvisDiagnostician, AIMatchingDiagnosis
from src.engine.ai_matching_agent import AIAvisMatchingAgent, ai_matching_agent

@pytest.fixture
def client():
    return TestClient(app)

def test_diagnose_pure_web_and_software():
    tender_data = {
        "portal_id": 101,
        "reference": "BC/WEB/2026",
        "title": "Développement et refonte du portail web institutionnel et application mobile",
        "buyer_name": "Ministère de la Transition Numérique",
        "main_category": "Services",
        "prestation_type": "Entretien et maintenance de logiciels et de progiciels",
        "execution_location": "Rabat",
        "deadline_at": (datetime.now() + timedelta(days=10)).isoformat(),
        "line_items": [
            {
                "item_order": 1,
                "designation": "Conception UI/UX et développement front-end React.js responsive",
                "technical_specs": "Interface moderne avec Tailwind CSS et intégration API REST",
                "quantity": 1.0,
                "unit": "Forfait"
            },
            {
                "item_order": 2,
                "designation": "Développement backend Node.js / Python et base de données PostgreSQL",
                "technical_specs": "Architecture microservices avec Docker et documentation Swagger",
                "quantity": 1.0,
                "unit": "Forfait"
            },
            {
                "item_order": 3,
                "designation": "Application mobile cross-platform Flutter pour iOS et Android",
                "technical_specs": "Authentification sécurisée et notifications push",
                "quantity": 1.0,
                "unit": "Forfait"
            }
        ]
    }

    diag = AIAvisDiagnostician.diagnose_tender(tender_data)
    assert diag.matching_rate >= 80.0
    assert diag.rating_label in ("EXCELLENT_MATCH", "STRONG_MATCH")
    assert diag.verdict == "GO"
    assert diag.hardware_dependency == "NONE"
    assert "React.js" in diag.detected_technologies or "Python" in diag.detected_technologies
    assert "Flutter" in diag.detected_technologies
    assert diag.sub_scores.get("web_development", 0) > 50.0
    assert "🚀 Opportunité Prioritaire" in diag.strategic_recommendation or "Candidature" in diag.strategic_recommendation

def test_diagnose_data_engineering_and_bi():
    tender_data = {
        "portal_id": 102,
        "reference": "BC/BI/2026",
        "title": "Mise en place d'une plateforme de Business Intelligence et tableaux de bord décisionnels",
        "buyer_name": "Agence Nationale des Ports",
        "main_category": "Services",
        "prestation_type": "Études, conseil et formation",
        "execution_location": "Casablanca",
        "deadline_at": (datetime.now() + timedelta(days=7)).isoformat(),
        "line_items": [
            {
                "item_order": 1,
                "designation": "Modélisation du Data Warehouse et pipelines ETL de collecte",
                "technical_specs": "Pipelines SQL et intégration données hétérogènes PostgreSQL / Oracle",
                "quantity": 1.0,
                "unit": "Forfait"
            },
            {
                "item_order": 2,
                "designation": "Conception de tableaux de bord Power BI et rapports automatisés",
                "technical_specs": "Dashboards KPI pour la direction générale avec actualisation quotidienne",
                "quantity": 1.0,
                "unit": "Forfait"
            }
        ]
    }

    diag = AIAvisDiagnostician.diagnose_tender(tender_data)
    assert diag.matching_rate >= 75.0
    assert diag.rating_label in ("EXCELLENT_MATCH", "STRONG_MATCH")
    assert diag.verdict == "GO"
    assert diag.hardware_dependency == "NONE"
    assert diag.sub_scores.get("data_engineering_bi", 0) > 50.0
    assert any("Power BI" in t or "Dashboard" in t or "ETL" in t for t in diag.detected_technologies)

def test_diagnose_pure_hardware_supplies_rejection():
    tender_data = {
        "portal_id": 103,
        "reference": "BC/HW/2026",
        "title": "Acquisition de matériel informatique et imprimantes pour les services administratifs",
        "buyer_name": "Commune de Marrakech",
        "main_category": "Fournitures",
        "prestation_type": "Achat de matériel technique, de logiciels et de matériel informatique",
        "execution_location": "Marrakech",
        "deadline_at": (datetime.now() + timedelta(days=5)).isoformat(),
        "line_items": [
            {
                "item_order": 1,
                "designation": "Ordinateur de bureau complet avec écran 24 pouces",
                "technical_specs": "Intel Core i5, 16 Go RAM, 512 Go SSD",
                "quantity": 25.0,
                "unit": "U"
            },
            {
                "item_order": 2,
                "designation": "Imprimante laser multifonction monochrome",
                "technical_specs": "Vitesse 40 ppm, bac 500 feuilles",
                "quantity": 10.0,
                "unit": "U"
            },
            {
                "item_order": 3,
                "designation": "Cartouches d'encre et toners de rechange",
                "technical_specs": "Consommables d'origine constructeur",
                "quantity": 50.0,
                "unit": "U"
            }
        ]
    }

    diag = AIAvisDiagnostician.diagnose_tender(tender_data)
    assert diag.matching_rate < 30.0
    assert diag.rating_label in ("LOW_MATCH", "MISMATCH")
    assert diag.hardware_dependency == "HIGH"
    assert "⛔ Ignorer" in diag.strategic_recommendation or "matérielle" in diag.strategic_recommendation

def test_diagnose_non_it_veto():
    tender_data = {
        "portal_id": 104,
        "reference": "BC/CARB/2026",
        "title": "Fourniture de carburants et lubrifiants pour le parc de véhicules communaux",
        "buyer_name": "Commune de Fès",
        "main_category": "Fournitures",
        "prestation_type": "Fourniture de carburants",
        "deadline_at": (datetime.now() + timedelta(days=4)).isoformat(),
        "line_items": [
            {"item_order": 1, "designation": "Gasoil pour camions et bennes", "quantity": 10000.0, "unit": "Litres"}
        ]
    }

    diag = AIAvisDiagnostician.diagnose_tender(tender_data)
    assert diag.matching_rate == 0.0
    assert diag.rating_label == "MISMATCH"
    assert diag.verdict == "NO-GO"
    assert "Hors Secteur" in diag.primary_domain or "Exclusion" in diag.diagnostic_summary

def test_diagnose_cancelled_notice():
    tender_data = {
        "portal_id": 105,
        "reference": "DA/999/2026",
        "title": "Avis d'annulation de la consultation relative au développement logiciel",
        "buyer_name": "Commune de Tanger",
        "main_category": "Services",
        "status": "annule"
    }

    diag = AIAvisDiagnostician.diagnose_tender(tender_data)
    assert diag.matching_rate == 0.0
    assert diag.verdict == "NO-GO"
    assert "Annulée" in diag.primary_domain or "annulé" in diag.strategic_recommendation.lower()


def test_diagnose_printer_compatibility_specs_not_software():
    """
    Regression for BDC #411863: Printer/Scanner specs mentioning 'compatibilité Android, iOS'
    and 'services Cloud compatibles' must NOT be classified as Génie Logiciel / Cloud & DevOps.
    """
    tender_data = {
        "portal_id": 411863,
        "reference": "002/2026",
        "title": "Achat de matériel de bureau pour la Faculté d'Economie et de Gestion de Safi",
        "buyer_name": "FACULTE D'ECONOMIE ET DE GESTION DE SAFI",
        "main_category": "Fournitures",
        "prestation_type": "Achat de matériel et de mobilier de bureau",
        "line_items": [
            {
                "designation": "Imprimante Multifonction Laser Monochrome A3",
                "technical_specs": "Systèmes compatibles : Windows 10/11, macOS ; compatibilité Android, iOS/iPadOS. Numérisation vers services Cloud compatibles. Fonctions usuelles et interface tactile."
            },
            {
                "designation": "Duplicopieur A4/A3",
                "technical_specs": "Capacité d'impression 100.000 pages/mois, USB 2.0, Ethernet."
            },
            {
                "designation": "Scanner A3",
                "technical_specs": "Scanner de bureau A3 avec chargeur 300 feuilles, USB 3.1."
            },
        ],
    }

    diag = AIAvisDiagnostician.diagnose_tender(tender_data)
    assert diag.hardware_dependency == "HIGH"
    assert diag.verdict == "NO-GO"
    assert diag.rating_label == "MISMATCH"
    assert diag.matching_rate < 20.0
    assert diag.sub_scores.get("software_programming", 0.0) == 0.0
    assert diag.sub_scores.get("cloud_devops", 0.0) == 0.0
    assert "Android" not in diag.detected_technologies
    assert "iOS Mobile" not in diag.detected_technologies
    assert "UI/UX" not in diag.detected_technologies
    assert "Cloud Architecture" not in diag.detected_technologies

def test_agent_diagnose_endpoints_with_mock_db(client):
    now = datetime.now(timezone.utc)
    t_web = Tender(
        portal_id=777001,
        source_type="bdc",
        reference="BC/DEV/2026",
        compound_natural_key="buyer-dev:BC/DEV/2026:2026",
        buyer_id=uuid.uuid4(),
        title="Développement d'une plateforme web et API REST Python",
        main_category="Services",
        prestation_type="Entretien et maintenance de logiciels et de progiciels",
        execution_location="Rabat",
        published_at=now - timedelta(days=1),
        deadline_at=now + timedelta(days=6),
        status="active"
    )
    t_web.buyer = Buyer(slug="buyer-dev", official_name="Ministère du Numérique", buyer_type="ministère")
    item1 = LineItem(
        id=uuid.uuid4(),
        tender_id=777001,
        item_order=1,
        designation="Développement frontend React et backend FastAPI",
        technical_specs="Architecture Cloud Docker",
        unit="Forfait",
        quantity=1.0,
        tva_rate=20.0
    )
    t_web.line_items = [item1]

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [t_web]
    mock_res.scalar_one_or_none.return_value = t_web

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_res

    app.dependency_overrides[get_db_session] = lambda: mock_session
    from src.api.auth import create_session_token
    admin_headers = {"Authorization": f"Bearer {create_session_token('admin@bergag.ma', 'admin')}"}

    try:
        # 1. Test single avis diagnosis endpoint
        single_res = client.get("/api/agent/diagnose/777001?force_refresh=true")
        assert single_res.status_code == 200
        single_data = single_res.json()
        assert single_data["matching_rate"] >= 70.0
        assert single_data["verdict"] == "GO"
        assert single_data["rating_label"] in ("EXCELLENT_MATCH", "STRONG_MATCH")

        # 2. Test batch diagnosis endpoint
        batch_res = client.post("/api/agent/diagnose-batch", json={
            "limit": 5,
            "open_only": False,
            "force_refresh": True
        }, headers=admin_headers)
        assert batch_res.status_code == 200
        batch_data = batch_res.json()
        assert batch_data["success"] is True
        assert batch_data["total_scanned"] == 1
        assert "rating_distribution" in batch_data
        assert "top_technologies" in batch_data

        # 3. Test report endpoint
        report_res = client.get("/api/agent/diagnostics/report?limit=5")
        assert report_res.status_code == 200
        report_data = report_res.json()
        assert report_data["success"] is True

        # 4. Test feed includes ai_matching
        feed_res = client.get("/api/feed?profile_name=software_data&limit=5", headers=admin_headers)
        assert feed_res.status_code == 200
        items = feed_res.json()
        assert len(items) == 1
        assert "ai_matching" in items[0]
        assert items[0]["ai_matching"] is not None
        assert items[0]["ai_matching"]["matching_rate"] >= 70.0
        assert items[0]["ai_matching"]["primary_domain"] != ""

        # 5. Test detail includes ai_matching
        detail_res = client.get("/api/tenders/777001?profile_name=software_data", headers=admin_headers)
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert "ai_matching" in detail_data
        assert detail_data["ai_matching"]["matching_rate"] >= 70.0

        # 6. Test direct database sync endpoint (POST /api/agent/sync-db)
        sync_res = client.post("/api/agent/sync-db?limit=5&force_refresh=true", headers=admin_headers)
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["success"] is True
        assert "Synchronisation terminée" in sync_data["message"]
        assert sync_data["data"]["total_scanned"] == 1
    finally:
        app.dependency_overrides.pop(get_db_session, None)

@pytest.mark.asyncio
async def test_direct_db_sync_method():
    now = datetime.now(timezone.utc)
    t_web = Tender(
        portal_id=888002,
        source_type="bdc",
        reference="BC/DATA/2026",
        compound_natural_key="buyer-data:BC/DATA/2026:2026",
        buyer_id=uuid.uuid4(),
        title="Plateforme Data et Décisionnel PowerBI",
        main_category="Services",
        prestation_type="Entretien et maintenance de logiciels",
        published_at=now,
        deadline_at=now + timedelta(days=7),
        status="active"
    )
    t_web.buyer = Buyer(slug="buyer-data", official_name="Ministère B", buyer_type="ministère")
    item = LineItem(
        id=uuid.uuid4(),
        tender_id=888002,
        item_order=1,
        designation="Tableaux de bord Power BI et pipelines ETL",
        technical_specs="Données SQL et modélisation Data Warehouse",
        quantity=1.0,
        unit="U"
    )
    t_web.line_items = [item]

    mock_prof_res = MagicMock()
    mock_prof_res.scalars.return_value.first.return_value = None

    mock_match_res = MagicMock()
    mock_match_res.scalars.return_value.all.return_value = []

    mock_tenders_res = MagicMock()
    mock_tenders_res.scalars.return_value.all.return_value = [t_web]

    mock_session = AsyncMock()
    mock_session.execute.side_effect = [mock_prof_res, mock_match_res, mock_tenders_res]

    agent = AIAvisMatchingAgent()
    result = await agent.sync_avis_diagnoses_to_db(
        session=mock_session,
        profile_name="software_data",
        limit=10,
        force_refresh=True
    )

    assert result["total_scanned"] == 1
    assert result["matches_created"] == 1
    assert mock_session.add.called
    assert mock_session.commit.called
    assert len(result["top_opportunities"]) == 1
    assert result["top_opportunities"][0]["matching_rate"] >= 70.0


def test_diagnose_false_positive_regressions():
    """
    Regression suite for real-world active avis false positives identified in ledger audit:
    - #410803: 'correction de la vue' must NOT trigger Vue.js / Web & Portails
    - #409380: 'Adobe Creative Cloud' must NOT trigger Cloud & DevOps 100%
    - #409833: 'imprimantes et logiciel anti virus' must NOT trigger Génie Logiciel 100% / Cloud 75%
    - #411216: 'photocopieuses' must be flagged as HIGH hardware and 0% software
    - #409542: 'travaux d'aménagement' must be vetoed as non-IT
    - #410919: 'tableaux magnétiques' must be vetoed as non-IT
    - #411071: 'développement humain (INDH)' must NOT trigger Génie Logiciel
    """
    # 1. #410803 - Lunettes de correction de la vue
    diag_vue = AIAvisDiagnostician.diagnose_tender({
        "portal_id": 410803,
        "title": "Achat de lunettes de correction de la vue pour les personnes indigentes",
        "main_category": "Fournitures",
        "line_items": [{"designation": "Lunettes médicales de correction de la vue", "technical_specs": "Monture + verres"}]
    })
    assert diag_vue.matching_rate == 0.0
    assert diag_vue.sub_scores["web_development"] == 0.0
    assert diag_vue.verdict == "NO-GO"

    # 2. #409380 - Adobe Creative Cloud
    diag_adobe = AIAvisDiagnostician.diagnose_tender({
        "portal_id": 409380,
        "title": "Achat d'un Abonnement Adobe Creative Cloud « Tout Creative Cloud » pour une année",
        "main_category": "Fournitures",
        "line_items": [
            {"designation": "Abonnement Adobe Creative Cloud", "technical_specs": "Licence Creative Cloud 1 an"}
        ]
    })
    assert diag_adobe.sub_scores["cloud_devops"] == 0.0
    assert diag_adobe.matching_rate <= 25.0
    assert diag_adobe.verdict in ("NO-GO", "CONSIDER")

    # 3. #409833 - Imprimantes + Antivirus
    diag_av = AIAvisDiagnostician.diagnose_tender({
        "portal_id": 409833,
        "title": "ACHAT D'IMPRIMANTES ET DE LOGICIEL ANTI VIRUS",
        "main_category": "Fournitures",
        "line_items": [
            {"designation": "Imprimante laser", "technical_specs": "Imprimante réseau"},
            {"designation": "Logiciel anti virus", "technical_specs": "Licence antivirus 1 an"}
        ]
    })
    assert diag_av.sub_scores["software_programming"] < 30.0
    assert diag_av.sub_scores["cloud_devops"] == 0.0
    assert diag_av.matching_rate <= 25.0

    # 4. #411216 - Photocopieuses
    diag_photo = AIAvisDiagnostician.diagnose_tender({
        "portal_id": 411216,
        "title": "Achat des photocopieuses pour la circonscription judiciaire de Tétouan",
        "main_category": "Fournitures",
        "line_items": [
            {"designation": "Photocopieuse multifonction", "technical_specs": "Compatibilité cloud et impression mobile"}
        ]
    })
    assert diag_photo.hardware_dependency == "HIGH"
    assert diag_photo.sub_scores["software_programming"] == 0.0
    assert diag_photo.sub_scores["cloud_devops"] == 0.0
    assert diag_photo.verdict == "NO-GO"

    # 5. #409542 - Travaux d'aménagement
    diag_btp = AIAvisDiagnostician.diagnose_tender({
        "portal_id": 409542,
        "title": "Travaux d'aménagement au profit du CHP Fkih ben Salah",
        "main_category": "Travaux",
        "line_items": [{"designation": "Aménagement des locaux", "technical_specs": "Cloisons et peinture"}]
    })
    assert diag_btp.matching_rate == 0.0
    assert diag_btp.verdict == "NO-GO"

    # 6. #410919 - Tableaux magnétiques
    diag_tab = AIAvisDiagnostician.diagnose_tender({
        "portal_id": 410919,
        "title": "Achat de tableaux magnétiques destinés au programme de lutte contre l'analphabétisme",
        "main_category": "Fournitures",
        "line_items": [{"designation": "Tableau magnétique blanc", "technical_specs": "Dimensions 120x240"}]
    })
    assert diag_tab.matching_rate == 0.0
    assert diag_tab.verdict == "NO-GO"

    # 7. #411071 - Sessions de formation INDH (développement humain != génie logiciel)
    diag_indh = AIAvisDiagnostician.diagnose_tender({
        "portal_id": 411071,
        "title": "Organisation des sessions de formation au profit de l'écosystème de l'INDH",
        "main_category": "Services",
        "line_items": [{"designation": "Formation et développement humain", "technical_specs": "Ateliers de renforcement des capacités"}]
    })
    assert diag_indh.sub_scores["software_programming"] == 0.0
    assert diag_indh.matching_rate < 20.0


