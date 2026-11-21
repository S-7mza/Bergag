import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.api.main import app
from src.ingestion.offline.exporter import OfflineExporter
from src.ingestion.offline.importer import OfflineImporter, OfflineImportError
from src.models.tender import Award, Buyer, Tender

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def client():
    return TestClient(app)

@pytest.mark.asyncio
async def test_offline_exporter_awards_with_fixture(tmp_path):
    fixture_path = FIXTURES_DIR / "results_page1.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    mock_client = AsyncMock()
    mock_client.get.return_value = html

    exporter = OfflineExporter(client=mock_client)
    out_file = tmp_path / "test_export_awards.json"

    res = await exporter.collect_awards(max_pages=1, output_path=str(out_file))

    assert res["status"] == "success"
    assert res["domain"] == "awards"
    assert res["item_count"] == 10
    assert out_file.exists()

    with open(out_file, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    assert "manifest" in bundle
    assert bundle["manifest"]["domain"] == "awards"
    assert bundle["manifest"]["format_version"] == "1.0.0"
    assert bundle["manifest"]["item_count"] == 10
    assert len(bundle["manifest"]["sha256_checksum"]) == 64
    assert len(bundle["items"]) == 10

    first = bundle["items"][0]
    assert first["reference"] == "178/FONC/2026/UIT"
    assert first["winner_name"] == "L'ATELIER DU VOYAGE"
    assert first["amount_ttc"] == 10040.0

@pytest.mark.asyncio
async def test_offline_importer_invalid_bundle():
    importer = OfflineImporter()

    with pytest.raises(OfflineImportError, match="Manifeste d'exportation manquant"):
        importer.parse_bundle({"items": []})

    with pytest.raises(OfflineImportError, match="Liste d'éléments manquante"):
        importer.parse_bundle({"manifest": {"domain": "awards"}})

@pytest.mark.asyncio
async def test_offline_importer_awards_success(tmp_path):
    mock_session = AsyncMock()
    
    # Mocking internal execution for awards ingestion
    buyer_res = MagicMock()
    buyer_res.scalar_one_or_none.return_value = MagicMock(spec=Buyer, slug="commune-test")

    award_res = MagicMock()
    award_res.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [buyer_res, award_res]

    bundle = {
        "manifest": {
            "format_version": "1.0.0",
            "domain": "awards",
            "item_count": 1
        },
        "items": [
            {
                "reference": "BC-10/2026",
                "title": "Achat matériel réseau",
                "buyer_name": "Commune Test",
                "winner_name": "CISCO MAROC",
                "amount_ttc": 125000.0,
                "devis_received_count": 3,
                "status": "Attribué",
                "published_at": "2026-11-20T10:00:00+01:00"
            }
        ]
    }

    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    importer = OfflineImporter(session=mock_session)
    # Stub matcher to avoid multi-pass calls in unit test
    with patch("src.ingestion.awards.service.AwardMatcher.find_matching_tender", new_callable=AsyncMock) as mock_match:
        mock_match.return_value = None
        result = await importer.import_bundle(bundle_path)

    assert result["status"] == "success"
    assert result["domain"] == "awards"
    assert result["items_processed"] == 1
    assert result["errors_count"] == 0

def test_api_upload_offline_bundle_endpoint(client):
    test_bundle = {
        "manifest": {
            "format_version": "1.0.0",
            "domain": "awards",
            "item_count": 1
        },
        "items": [
            {
                "reference": "BC-20/2026",
                "title": "Audit sécurité SI",
                "buyer_name": "Ministère Test",
                "winner_name": "DATAPROTECT",
                "amount_ttc": 210000.0,
                "devis_received_count": 4,
                "status": "Attribué",
                "published_at": "2026-11-20T12:00:00+01:00"
            }
        ]
    }
    file_bytes = json.dumps(test_bundle).encode("utf-8")

    with patch("src.ingestion.offline.importer.OfflineImporter.import_bundle", new_callable=AsyncMock) as mock_import:
        mock_import.return_value = {
            "status": "success",
            "domain": "awards",
            "items_total": 1,
            "items_processed": 1,
            "linked_tenders": 0,
            "errors_count": 0
        }

        files = {"file": ("test_export.json", file_bytes, "application/json")}
        res = client.post("/api/admin/ingestion/awards/offline/upload", files=files)

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["domain"] == "awards"
        assert data["items_processed"] == 1

def test_api_upload_offline_bundle_invalid_extension(client):
    files = {"file": ("test_export.txt", b"invalid text", "text/plain")}
    res = client.post("/api/admin/ingestion/awards/offline/upload", files=files)
    assert res.status_code == 400
    assert "Format de fichier non supporté" in res.json()["detail"]

def test_api_sync_offline_bundle_json_endpoint(client):
    test_bundle = {
        "manifest": {
            "format_version": "1.0.0",
            "domain": "awards",
            "item_count": 1
        },
        "items": [
            {
                "reference": "BC-30/2026",
                "title": "Maintenance switchs",
                "buyer_name": "Agence Test",
                "winner_name": "OMNIDATA",
                "amount_ttc": 85000.0,
                "devis_received_count": 2,
                "status": "Attribué",
                "published_at": "2026-11-20T14:00:00+01:00"
            }
        ]
    }

    with patch("src.ingestion.offline.importer.OfflineImporter.import_bundle", new_callable=AsyncMock) as mock_import:
        mock_import.return_value = {
            "status": "success",
            "domain": "awards",
            "items_total": 1,
            "items_processed": 1,
            "linked_tenders": 0,
            "errors_count": 0
        }

        res = client.post("/api/admin/ingestion/awards/offline/sync-json", json=test_bundle)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["domain"] == "awards"
        assert data["items_processed"] == 1

