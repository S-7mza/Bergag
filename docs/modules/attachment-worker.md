# Attachment Worker & Document OCR Pipeline

> **Scope:** Consultation ZIP extraction, native text extraction, and Tesseract OCR fallback.  
> **Source Files:** [`src/scraper/attachment_worker.py`](file:///c:/Users/7mza/mp/src/scraper/attachment_worker.py), [`Dockerfile`](file:///c:/Users/7mza/mp/Dockerfile), [`tests/test_attachments.py`](file:///c:/Users/7mza/mp/tests/test_attachments.py)

---

## 1. Document Extraction Pipeline

Public buyers attach requirement dossiers (CPS, Bordereau des Prix, Lettres de consultation) as ZIP archives containing PDF, Word, or scanned bitmap files.

```mermaid
flowchart TD
    Zip["Consultation Attachment (.zip)"]
    Unpack["In-Memory Unpack (zipfile)"]
    TypeCheck{"File Type?"}
    Docx["DOCX: python-docx"]
    PdfNative["PDF: pdfplumber / pypdf"]
    ScanCheck{"Char Count < 50 / Page?"}
    OCR["Tesseract OCR (fra + ara) via pdf2image"]
    TextOutput["Normalized Full Text Buffer"]

    Zip --> Unpack --> TypeCheck
    TypeCheck -->|*.docx| Docx --> TextOutput
    TypeCheck -->|*.pdf| PdfNative --> ScanCheck
    ScanCheck -->|No (Native Text)| TextOutput
    ScanCheck -->|Yes (Scanned Bitmap)| OCR --> TextOutput
```

---

## 2. Key Processing Rules

1. **In-Memory Streaming:** Small archives are processed directly in-memory using `io.BytesIO` to prevent disk thrashing.
2. **Dual-Pass PDF Extraction:**
   - **Pass 1 (Native):** Fast extraction using `pypdf` / `pdfplumber` (< 0.1s per page).
   - **Pass 2 (OCR Fallback):** If average page text density is $< 50$ characters, the document is flagged as a scanned bitmap.
   - Converts PDF pages to images using `pdf2image` (Poppler) and passes them to `pytesseract` with `-l fra+ara` (French + Arabic).
3. **Corrupt File Resilience:** Unpack errors or malformed ZIP archives fail gracefully without crashing the ingestion worker.
