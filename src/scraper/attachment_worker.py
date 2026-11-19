import io
import shutil
import zipfile
import logging
import subprocess
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import pypdf
from src.scraper.client import PortalHttpClient

logger = logging.getLogger(__name__)

# Check if external binaries are available in system environment
HAS_TESSERACT = shutil.which("tesseract") is not None
HAS_ANTIWORD = shutil.which("antiword") is not None

if HAS_TESSERACT:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        HAS_TESSERACT = False

try:
    from docx import Document
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False

@dataclass
class ExtractedFile:
    filename: str
    extension: str
    text: str
    tables: List[List[List[str]]] = field(default_factory=list) # List of tables, each table is rows of cells
    is_scanned: bool = False
    ocr_applied: bool = False

@dataclass
class ArchiveExtractionResult:
    archive_name: str
    file_count: int
    files: List[ExtractedFile]
    combined_text: str
    combined_tables: List[List[List[str]]]

class AttachmentWorker:
    """
    Downloads tender .zip archives from /download/{portal_id}/{file_id}
    and extracts text and tabular specifications across PDF, Word (.docx/.doc),
    with dual-pass PDF reading and multilingual Arabic/French OCR fallback.
    """
    def __init__(self, client: Optional[PortalHttpClient] = None):
        self.client = client

    def extract_from_zip_bytes(self, zip_bytes: bytes, archive_name: str = "dossier.zip") -> ArchiveExtractionResult:
        """Extracts and parses all supported documents inside a ZIP archive"""
        extracted_files: List[ExtractedFile] = []
        all_text_chunks: List[str] = []
        all_tables: List[List[List[str]]] = []

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                for member_name in zf.namelist():
                    # Skip internal OS artifacts (__MACOSX, .DS_Store)
                    if member_name.startswith("__MACOSX") or member_name.endswith(".DS_Store"):
                        continue

                    lower_name = member_name.lower()
                    data = zf.read(member_name)

                    if lower_name.endswith(".pdf"):
                        ef = self._extract_pdf(data, member_name)
                    elif lower_name.endswith(".docx"):
                        ef = self._extract_docx(data, member_name)
                    elif lower_name.endswith(".doc"):
                        ef = self._extract_doc(data, member_name)
                    else:
                        logger.debug(f"Skipping unsupported file extension: {member_name}")
                        continue

                    extracted_files.append(ef)
                    if ef.text:
                        all_text_chunks.append(f"--- File: {ef.filename} ---\n{ef.text}")
                    if ef.tables:
                        all_tables.extend(ef.tables)

        except zipfile.BadZipFile as e:
            logger.error(f"Corrupt or invalid ZIP archive '{archive_name}': {e}")

        return ArchiveExtractionResult(
            archive_name=archive_name,
            file_count=len(extracted_files),
            files=extracted_files,
            combined_text="\n\n".join(all_text_chunks),
            combined_tables=all_tables
        )

    def _extract_pdf(self, pdf_bytes: bytes, filename: str) -> ExtractedFile:
        """Dual-pass PDF extraction: native digital text first, scanned OCR fallback"""
        text_pages: List[str] = []
        is_scanned = False
        ocr_applied = False

        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                # If native text is present (> 50 chars per page), use it
                if len(page_text.strip()) > 50:
                    text_pages.append(page_text.strip())
                else:
                    # Page appears to be a scanned bitmap
                    if len(page.images) > 0:
                        is_scanned = True
                        if HAS_TESSERACT:
                            # Apply OCR to embedded images
                            for img in page.images:
                                try:
                                    pil_img = Image.open(io.BytesIO(img.data))
                                    ocr_text = pytesseract.image_to_string(pil_img, lang="fra+ara")
                                    if ocr_text.strip():
                                        text_pages.append(ocr_text.strip())
                                        ocr_applied = True
                                except Exception as ocr_err:
                                    logger.warning(f"OCR failed on image in {filename}: {ocr_err}")

        except Exception as e:
            logger.error(f"Error reading PDF '{filename}': {e}")

        return ExtractedFile(
            filename=filename,
            extension="pdf",
            text="\n".join(text_pages),
            is_scanned=is_scanned,
            ocr_applied=ocr_applied
        )

    def _extract_docx(self, docx_bytes: bytes, filename: str) -> ExtractedFile:
        """Extracts narrative paragraphs and structured tables from modern .docx files"""
        if not HAS_PYTHON_DOCX:
            logger.warning("python-docx not installed; skipping .docx parsing")
            return ExtractedFile(filename=filename, extension="docx", text="")

        paragraphs: List[str] = []
        tables: List[List[List[str]]] = []

        try:
            doc = Document(io.BytesIO(docx_bytes))
            for p in doc.paragraphs:
                clean = p.text.strip()
                if clean:
                    paragraphs.append(clean)

            # Extract tables (Bordereau des prix / DQE)
            for tbl in doc.tables:
                table_grid = []
                for row in tbl.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    if any(row_cells):
                        table_grid.append(row_cells)
                if table_grid:
                    tables.append(table_grid)

        except Exception as e:
            logger.error(f"Error reading .docx file '{filename}': {e}")

        return ExtractedFile(
            filename=filename,
            extension="docx",
            text="\n".join(paragraphs),
            tables=tables
        )

    def _extract_doc(self, doc_bytes: bytes, filename: str) -> ExtractedFile:
        """Extracts text from legacy Microsoft Word 97-2003 binary format using antiword"""
        if not HAS_ANTIWORD:
            logger.info("antiword binary not found in environment; skipping legacy .doc extraction")
            return ExtractedFile(filename=filename, extension="doc", text="")

        try:
            # Run antiword on binary stream via stdin
            process = subprocess.run(
                ["antiword", "-m", "UTF-8.txt", "-"],
                input=doc_bytes,
                capture_output=True,
                check=False
            )
            raw_text = process.stdout.decode('utf-8', errors='ignore') if process.returncode == 0 else ""
            return ExtractedFile(filename=filename, extension="doc", text=raw_text.strip())
        except Exception as e:
            logger.error(f"Error running antiword on '{filename}': {e}")
            return ExtractedFile(filename=filename, extension="doc", text="")

    async def download_and_extract(self, download_url: str) -> ArchiveExtractionResult:
        """Downloads the ZIP from portal and executes multi-format extraction"""
        if not self.client:
            raise ValueError("PortalHttpClient is required to download attachments")

        logger.info(f"AttachmentWorker: Downloading archive from {download_url}")
        zip_bytes = await self.client.download_binary(download_url)
        archive_name = download_url.split('/')[-1] + ".zip"
        return self.extract_from_zip_bytes(zip_bytes, archive_name=archive_name)

