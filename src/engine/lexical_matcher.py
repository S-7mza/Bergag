import re
import unicodedata
from typing import Tuple, List, Optional
from src.profiles.schema import CompanyProfileSchema

def strip_accents(text: str) -> str:
    """Normalizes text by removing diacritics / accents (e.g. matériel -> materiel)"""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

def tokenize(text: str) -> set[str]:
    """Extracts lowercase normalized alphanumeric word tokens"""
    norm = strip_accents(text)
    tokens = re.findall(r'\b[a-zA-Z0-9_\u0600-\u06FF]{3,}\b', norm)
    return set(tokens)

class LexicalMatcher:
    """
    Stage 2: Lexical Keyword & Negative Constraints Filter.
    1. Checks for negative keyword exclusions (Instant Veto).
    2. Computes weighted lexical match score against profile catalog synonyms & tech keywords.
    Normalizes accents to ensure robust matching across Moroccan tender titles and descriptions.
    """
    @staticmethod
    def evaluate(tender_text: str, profile: CompanyProfileSchema) -> Tuple[bool, Optional[str], float]:
        """
        Returns:
            (passed: bool, veto_reason: Optional[str], score: float 0.0 to 100.0)
        """
        if not tender_text:
            return True, None, 0.0

        norm_tender = strip_accents(tender_text)
        tokens = tokenize(tender_text)

        # 1. Negative Keyword Gate (Instant Veto)
        for neg_word in profile.negative_constraints.keywords:
            neg_norm = strip_accents(neg_word).strip()
            if not neg_norm:
                continue
            # Match singular, plural (s/x), and feminine forms (e/es) so "photocopieur" matches "photocopieurs"
            pattern = rf'\b{re.escape(neg_norm)}(?:s|x|es|e)?\b'
            if re.search(pattern, norm_tender):
                return False, f"Veto par mot-clé négatif exclu : '{neg_word}'", 0.0

        # 2. Positive Lexical & Synonym Scoring
        total_weight = 0.0
        matched_weight = 0.0

        for item in profile.catalog:
            item_weight = item.weight
            total_weight += item_weight

            # Collect all positive triggers for this SKU
            triggers = set(item.synonyms_fr + item.synonyms_ar + item.technical_keywords)
            
            matched = False
            for trigger in triggers:
                trig_norm = strip_accents(trigger).strip()
                if not trig_norm:
                    continue

                if " " in trig_norm:
                    pattern = rf'\b{re.escape(trig_norm)}(?:s|x)?\b'
                    if re.search(pattern, norm_tender):
                        matched = True
                        break
                    # Multi-word token subset match with word boundaries
                    trig_words = [w for w in trig_norm.split() if len(w) > 2]
                    if trig_words and all(w in tokens or re.search(rf'\b{re.escape(w)}(?:s|x)?\b', norm_tender) for w in trig_words):
                        matched = True
                        break
                else:
                    # Single word / acronym: MUST match on exact word boundaries, never raw substring
                    # e.g. "api" must match word "API", NOT inside "papier"
                    pattern = rf'\b{re.escape(trig_norm)}(?:s|x)?\b'
                    if trig_norm in tokens or re.search(pattern, norm_tender):
                        matched = True
                        break

            if matched:
                matched_weight += item_weight

        if total_weight == 0.0:
            return True, None, 0.0

        lexical_score = min(100.0, (matched_weight / total_weight) * 100.0)
        return True, None, round(lexical_score, 2)
