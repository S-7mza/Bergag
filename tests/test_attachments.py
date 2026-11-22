import io
import pytest
from pathlib import Path
from src.scraper.attachment_worker import AttachmentWorker

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_extract_from_real_cctv_zip_fixture():
    fixture_path = FIXTURES_DIR / "sample_409807.zip"
    assert fixture_path.exists(), "CCTV attachment fixture must exist"

    with open(fixture_path, "rb") as f:
        zip_bytes = f.read()

    worker = AttachmentWorker()
    result = worker.extract_from_zip_bytes(zip_bytes, archive_name="sample_409807.zip")

    assert result.file_count == 1
    assert len(result.files) == 1

    extracted_pdf = result.files[0]
    assert extracted_pdf.extension == "pdf"
    assert "Avis d'achat" in extracted_pdf.filename
    # Verifies detection of scanned paper from rural commune
    assert extracted_pdf.is_scanned is True

def test_extract_docx_in_memory():
    from docx import Document

    # Create a synthetic docx in memory with a table
    doc = Document()
    doc.add_paragraph("Cahier des Prescriptions Spéciales")
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "Article"
    table.cell(0, 1).text = "Désignation"
    table.cell(0, 2).text = "Quantité"
    table.cell(1, 0).text = "01"
    table.cell(1, 1).text = "Serveur Rack 2U"
    table.cell(1, 2).text = "2"

    docx_bytes_io = io.BytesIO()
    doc.save(docx_bytes_io)
    docx_bytes = docx_bytes_io.getvalue()

    worker = AttachmentWorker()
    ef = worker._extract_docx(docx_bytes, "cps_test.docx")

    assert ef.extension == "docx"
    assert "Cahier des Prescriptions Spéciales" in ef.text
    assert len(ef.tables) == 1
    assert ef.tables[0][1][1] == "Serveur Rack 2U"
    assert ef.tables[0][1][2] == "2"

def test_corrupt_zip_handling():
    worker = AttachmentWorker()
    result = worker.extract_from_zip_bytes(b"not_a_valid_zip_payload", "corrupt.zip")
    assert result.file_count == 0
    assert result.combined_text == ""


def test_api_attachment_endpoints():
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, patch, MagicMock
    from src.api.main import app
    from src.database.session import get_db_session
    from src.models.tender import Tender, Buyer
    from datetime import datetime, timezone
    import zipfile

    client = TestClient(app)

    # Prepare a test zip in data/attachments/tender_777888.zip
    cache_dir = Path("data/attachments")
    cache_dir.mkdir(parents=True, exist_ok=True)
    test_zip_path = cache_dir / "tender_777888.zip"
    
    with zipfile.ZipFile(test_zip_path, "w") as zf:
        zf.writestr("dossier/CPS_Prescriptions_Techniques.pdf", b"%PDF-1.4 dummy CPS content")
        zf.writestr("dossier/Avis_d_achat_officiel.pdf", b"%PDF-1.4 dummy Avis content")

    try:
        mock_tender = Tender(
            portal_id=777888,
            source_type="bdc",
            reference="77/TEST/2026",
            compound_natural_key="buyer:77-test-2026:2026",
            buyer_id=uuid.uuid4() if 'uuid' in dir() else __import__('uuid').uuid4(),
            title="Prestation informatique et développement",
            main_category="Services",
            published_at=datetime.now(timezone.utc),
            deadline_at=datetime.now(timezone.utc),
            status="active",
            attachment_available=True,
            attachment_url="/bdc/entreprise/consultation/download/777888/9999"
        )
        mock_tender.buyer = Buyer(slug="buyer-test", official_name="Commune Test")
        mock_tender.line_items = []

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tender
        mock_session.execute.return_value = mock_result

        async def override_db():
            yield mock_session

        app.dependency_overrides[get_db_session] = override_db

        # 1. Test /api/tenders/{portal_id}/attachment/files
        res_files = client.get("/api/tenders/777888/attachment/files")
        assert res_files.status_code == 200
        data = res_files.json()
        assert data["available"] is True
        assert data["portal_id"] == 777888
        assert data["file_count"] == 2
        cps_doc = next((f for f in data["files"] if f["is_cps"]), None)
        assert cps_doc is not None
        assert "CPS" in cps_doc["filename"]
        assert "direct_url" in cps_doc

        # 2. Test /api/tenders/{portal_id}/attachment/download (ZIP archive)
        res_zip = client.get("/api/tenders/777888/attachment/download")
        assert res_zip.status_code == 200
        assert res_zip.headers["content-type"] == "application/zip"
        assert "Dossier_CPS_BDC_777888" in res_zip.headers["content-disposition"]
        assert len(res_zip.content) > 0

        # 3. Test /api/tenders/{portal_id}/attachment/file (Single PDF stream)
        res_pdf = client.get(f"/api/tenders/777888/attachment/file?path={cps_doc['raw_path']}&inline=true")
        assert res_pdf.status_code == 200
        assert res_pdf.headers["content-type"] == "application/pdf"
        assert "inline" in res_pdf.headers["content-disposition"]
        assert b"%PDF-1.4 dummy CPS content" in res_pdf.content

    finally:
        app.dependency_overrides.pop(get_db_session, None)
        if test_zip_path.exists():
            test_zip_path.unlink()


