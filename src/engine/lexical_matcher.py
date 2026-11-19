import re
from typing import Tuple, List
from src.profiles.schema import CompanyProfileSchema

def tokenize(text: str) -> set[str]:
    """Extracts lowercase alphanumeric word tokens"""
    tokens = re.findall(r'\b[a-zA-Z0-9_\u0600-\u06FF]{3,}\b', text.lower())
    return set(tokens)

class LexicalMatcher:
    """
    Stage 2: Lexical Keyword & Negative Constraints Filter.
    1. Checks for negative keyword exclusions (Instant Veto).
    2. Computes weighted lexical match score against profile catalog synonyms & tech keywords.
    """
    @staticmethod
    def evaluate(tender_text: str, profile: CompanyProfileSchema) -> Tuple[bool, str | None, float]:
        """
        Returns:
            (passed: bool, veto_reason: Optional[str], score: float 0.0 to 100.0)
        """
        lower_text = tender_text.lower()

        # 1. Negative Keyword Gate (Instant Veto)
        for neg_word in profile.negative_constraints.keywords:
            pattern = rf'\b{re.escape(neg_word.lower())}\b'
            if re.search(pattern, lower_text):
                return False, f"Vetoed by negative constraint keyword: '{neg_word}'", 0.0

        # 2. Positive Lexical & Synonym Scoring
        tokens = tokenize(tender_text)
        total_weight = 0.0
        matched_weight = 0.0

        for item in profile.catalog:
            item_weight = item.weight
            total_weight += item_weight

            # Collect all positive triggers for this SKU
            triggers = set(item.synonyms_fr + item.synonyms_ar + item.technical_keywords)
            
            # Check if any trigger matches
            matched = False
            for trigger in triggers:
                trig_lower = trigger.lower()
                if " " in trig_lower:
                    if trig_lower in lower_text:
                        matched = True
                        break
                else:
                    if trig_lower in tokens or trig_lower in lower_text:
                        matched = True
                        break

            if matched:
                matched_weight += item_weight

        if total_weight == 0.0:
            return True, None, 0.0

        lexical_score = min(100.0, (matched_weight / total_weight) * 100.0)
        return True, None, round(lexical_score, 2)

