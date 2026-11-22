import re
import unicodedata
from typing import Tuple, List, Dict, Any
from src.profiles.schema import CompanyProfileSchema

def strip_accents(text: str) -> str:
    """Normalizes text by removing diacritics / accents"""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

_PATTERN_CACHE: Dict[str, re.Pattern] = {}

def _get_compiled_pattern(term: str) -> re.Pattern:
    pat = _PATTERN_CACHE.get(term)
    if pat is None:
        pat = re.compile(rf'\b{re.escape(term)}(?:s|x)?\b', re.IGNORECASE)
        _PATTERN_CACHE[term] = pat
    return pat

class LineItemMatcher:
    """
    Stage 3: Line-Item Catalog Mapping & Bill of Materials (BOM) Coverage.
    Decomposes each individual article requested by the public buyer and determines:
    1. Can the company actually supply this specific item?
    2. What percentage of the overall consultation can the company deliver?
    Normalizes accents to ensure robust matching across Moroccan designations and specs.
    """
    @staticmethod
    def match_line_items(
        line_items: List[Dict[str, Any]], 
        profile: CompanyProfileSchema
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        """
        Returns:
            (coverage_score: float 0-100, 
             item_evaluations: list[dict], 
             unmatched_designations: list[str])
        """
        if not line_items:
            return 0.0, [], []

        item_evaluations = []
        matched_count = 0
        unmatched_items = []

        for item in line_items:
            desig = item.get("designation", "")
            specs = item.get("technical_specs", "") or ""
            full_item_text = strip_accents(f"{desig} {specs}")

            best_catalog_match = None
            highest_score = 0.0

            for cat_sku in profile.catalog:
                triggers = set(cat_sku.synonyms_fr + cat_sku.synonyms_ar + cat_sku.technical_keywords)
                hits = 0
                for trigger in triggers:
                    trig_norm = strip_accents(trigger).strip()
                    if not trig_norm:
                        continue

                    if " " in trig_norm:
                        # Multi-word phrase match (e.g. 'application web')
                        if _get_compiled_pattern(trig_norm).search(full_item_text):
                            hits += 1
                        else:
                            # Token subset with word boundaries
                            trig_words = [w for w in trig_norm.split() if len(w) > 2]
                            if trig_words and all(_get_compiled_pattern(w).search(full_item_text) for w in trig_words):
                                hits += 1
                    else:
                        # Single word / acronym: MUST match on exact word boundaries!
                        if _get_compiled_pattern(trig_norm).search(full_item_text):
                            hits += 1

                if hits > 0:
                    score = min(1.0, 0.4 + (hits * 0.2)) * cat_sku.weight
                    if score > highest_score:
                        highest_score = score
                        best_catalog_match = cat_sku.id

            is_matched = highest_score >= 0.50
            if is_matched:
                matched_count += 1
            else:
                unmatched_items.append(desig)

            item_evaluations.append({
                "item_order": item.get("item_order"),
                "designation": desig,
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "is_matched": is_matched,
                "matched_catalog_sku": best_catalog_match,
                "confidence_score": round(highest_score * 100, 1)
            })

        total_items = len(line_items)
        coverage_ratio = (matched_count / total_items) * 100.0 if total_items > 0 else 0.0
        return round(coverage_ratio, 2), item_evaluations, unmatched_items
