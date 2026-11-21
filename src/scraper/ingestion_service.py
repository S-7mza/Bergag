# Backward compatibility re-export
from src.ingestion.utils import slugify
from src.ingestion.bdc.service import BdcIngestionService as IngestionService

__all__ = [
    "slugify",
    "IngestionService"
]
