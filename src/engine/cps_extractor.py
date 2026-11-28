import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ATTACHMENTS_DIR = Path("data/attachments")
EXTRACTED_CACHE_DIR = ATTACHMENTS_DIR / "extracted"


class CPSFindings(BaseModel):
    has_attachment_text: bool = False
    caution_provisoire: Optional[str] = None
    execution_delay: Optional[str] = None
    warranty_period: Optional[str] = None
    site_visit_required: bool = False
    certifications_required: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)
    penalties_mentioned: bool = False
    cps_excerpt: str = ""


class CPSDeterministicExtractor:
    """
    Zero-cost local deterministic extractor for Moroccan public procurement
    CPS / Cahier des Charges / Bordereau documents (PDF, DOCX, DOC, OCR).
    """

    @staticmethod
    def get_cached_attachment_text(portal_id: int) -> str:
        """
        Returns cached extracted text for a tender's .zip archive if present on disk.
        Extracts and caches on first hit if tender_{portal_id}.zip already exists.
        """
        if not portal_id:
            return ""
        txt_path = EXTRACTED_CACHE_DIR / f"{portal_id}.txt"
        if txt_path.exists():
            try:
                return txt_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return ""

        zip_path = ATTACHMENTS_DIR / f"tender_{portal_id}.zip"
        if zip_path.exists() and zip_path.stat().st_size > 0:
            try:
                from src.scraper.attachment_worker import AttachmentWorker

                worker = AttachmentWorker()
                res = worker.extract_from_zip_bytes(zip_path.read_bytes(), archive_name=zip_path.name)
                text = (res.combined_text or "").strip()
                if text:
                    EXTRACTED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    txt_path.write_text(text, encoding="utf-8")
                return text
            except Exception as e:
                logger.debug(f"Failed local ZIP extraction for #{portal_id}: {e}")
        return ""

    @classmethod
    def extract(cls, tender_data: Dict[str, Any], attachment_text: Optional[str] = None) -> CPSFindings:
        portal_id = tender_data.get("portal_id")
        raw_att = attachment_text if attachment_text is not None else (
            cls.get_cached_attachment_text(int(portal_id)) if portal_id else ""
        )

        # Combine tender metadata + line items + attachment text
        parts = [
            tender_data.get("title") or "",
            tender_data.get("prestation_type") or "",
        ]
        for item in tender_data.get("line_items", []):
            parts.append(item.get("designation") or "")
            parts.append(item.get("technical_specs") or "")
            if item.get("warranty_required"):
                parts.append(f"Garantie {item['warranty_required']}")

        if raw_att:
            parts.append(raw_att)

        corpus = "\n".join(p for p in parts if p)
        if not corpus.strip():
            return CPSFindings(has_attachment_text=bool(raw_att))

        # 1. Caution provisoire
        caution = None
        m_caut = re.search(
            r"caution(?:nement)?\s+provisoire\s*[:\-]?\s*([^\n.;]{3,55})",
            corpus,
            re.IGNORECASE,
        )
        if m_caut:
            caution = " ".join(m_caut.group(1).split())[:60]

        # 2. Execution delay
        delay = None
        m_delay = re.search(
            r"d[ée]lai\s+d['’]ex[ée]cution\s*[:\-]?\s*(\d+\s*(?:jours?|mois|semaines?|ans?))",
            corpus,
            re.IGNORECASE,
        )
        if m_delay:
            delay = m_delay.group(1).strip()

        # 3. Warranty period
        warranty = None
        m_war = re.search(
            r"(?:d[ée]lai\s+de\s+)?garantie\s*[:\-]?\s*(\d+\s*(?:mois|ans?|ann[ée]es?))",
            corpus,
            re.IGNORECASE,
        )
        if m_war:
            warranty = m_war.group(1).strip()

        # 4. Site visit requirement
        site_visit = bool(
            re.search(r"\bvisite\s+(?:des\s+lieux|obligatoire)\b", corpus, re.IGNORECASE)
        )

        # 5. Certifications / Agréments
        cert_patterns = [
            (r"\biso\s*27001\b", "ISO 27001"),
            (r"\biso\s*9001\b", "ISO 9001"),
            (r"\bcndp\b", "Conformité CNDP (Loi 09-08)"),
            (r"\bdgssi\b", "Référentiel DGSSI"),
            (r"\bagr[ée]ment\b", "Agrément requis"),
            (r"\bcertificat\s+de\s+qualification\b", "Certificat de qualification"),
            (r"\battestation\s+de\s+r[ée]f[ée]rence\b", "Attestations de référence"),
        ]
        certs = [label for pat, label in cert_patterns if re.search(pat, corpus, re.IGNORECASE)]

        # 6. Key deliverables
        deliverable_patterns = [
            (r"\bcode\s+source\b", "Code source"),
            (r"\bdocumentation\s+technique\b", "Documentation technique"),
            (r"\bformation\s+(?:des\s+)?utilisateurs?\b", "Formation utilisateurs"),
            (r"\bmaintenance\s+(?:corrective|pr[ée]ventive|[ée]volutive|applicative)\b", "Maintenance / TMA"),
            (r"\bformation\b", "Formation"),
            (r"\bh[ée]bergement\b", "Hébergement"),
            (r"\bmigration\s+de\s+donn[ée]es\b", "Migration de données"),
        ]
        deliverables = []
        for pat, label in deliverable_patterns:
            if re.search(pat, corpus, re.IGNORECASE) and label not in deliverables:
                deliverables.append(label)

        penalties = bool(re.search(r"\bp[ée]nalit[ée]s?\s+de\s+retard\b", corpus, re.IGNORECASE))

        excerpt = ""
        if raw_att:
            excerpt = " ".join(raw_att.split())[:1500]

        return CPSFindings(
            has_attachment_text=bool(raw_att),
            caution_provisoire=caution,
            execution_delay=delay,
            warranty_period=warranty,
            site_visit_required=site_visit,
            certifications_required=certs,
            deliverables=deliverables[:6],
            penalties_mentioned=penalties,
            cps_excerpt=excerpt,
        )
