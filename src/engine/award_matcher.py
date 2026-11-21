# Backward compatibility re-export
from src.ingestion.awards.matcher import (
    clean_procurement_reference,
    compute_compound_ref_key,
    AwardMatcher
)

__all__ = [
    "clean_procurement_reference",
    "compute_compound_ref_key",
    "AwardMatcher"
]
