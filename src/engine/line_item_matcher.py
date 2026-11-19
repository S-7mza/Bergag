import re
from typing import Tuple, List, Dict, Any
from src.profiles.schema import CompanyProfileSchema

class LineItemMatcher:
    """
    Stage 3: Line-Item Catalog Mapping & Bill of Materials (BOM) Coverage.
    Decomposes each individual article requested by the public buyer and determines:
    1. Can the company actually supply this specific item?
    2. What percentage of the overall consultation can the company deliver?
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
            # If no line items present in HTML, coverage is 0.0
            return 0.0, [], []

        item_evaluations = []
        matched_count = 0
        unmatched_items = []

        for item in line_items:
            desig = item.get("designation", "")
            specs = item.get("technical_specs", "")
            full_item_text = f"{desig} {specs}".lower()

            best_catalog_match = None
            highest_score = 0.0

            for cat_sku in profile.catalog:
                triggers = set(cat_sku.synonyms_fr + cat_sku.synonyms_ar + cat_sku.technical_keywords)
                hits = 0
                for trigger in triggers:
                    trig_lower = trigger.lower()
                    if trig_lower in full_item_text:
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

