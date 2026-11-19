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

