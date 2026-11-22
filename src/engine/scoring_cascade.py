import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from src.profiles.schema import CompanyProfileSchema
from src.engine.hard_filters import evaluate_hard_filters
from src.engine.lexical_matcher import LexicalMatcher
from src.engine.line_item_matcher import LineItemMatcher
from src.engine.llm_judge import LLMJudge

logger = logging.getLogger(__name__)

@dataclass
class CascadeEvaluationResult:
    overall_score: float
    decision_recommendation: str  # 'GO', 'CONSIDER', 'NO-GO', 'CLÔTURÉ', 'ANNULÉ'
    coverage_score: float
    lexical_score: float
    feasibility_score: float
    line_item_matches: List[Dict[str, Any]]
    red_flags: List[str]
    llm_reasoning: str

class ScoringCascadeEngine:
    """
    Unified 4-Stage Cascade Scoring Engine:
    Stage 1: Hard Binary Elimination Gate & Pre-conditions
    Stage 2: Lexical Veto & BM25/Token Match
    Stage 3: Line-Item BOM Catalog Coverage %
    Stage 4: LLM Judge & Margin Estimation
    
    Guarantees:
    - Business relevance (BOM coverage & lexical match) is always accurately computed.
    - Operational timing constraints (expired deadlines, urgent deadlines) produce
      clear, informative decision verdicts ('CLÔTURÉ', 'CONSIDER (Urgent)', 'GO', 'NO-GO').
    """
    def __init__(self, llm_judge: LLMJudge | None = None):
        self.llm_judge = llm_judge or LLMJudge()

    async def evaluate_tender(
        self, 
        tender_data: Dict[str, Any], 
        profile: CompanyProfileSchema
    ) -> CascadeEvaluationResult:
        # --- Stage 1: Operational Gates & Pre-conditions ---
        is_eligible, hard_reasons = evaluate_hard_filters(tender_data, profile)

        # Cancelled tenders are immediately dropped at Stage 1
        is_cancelled = any("annul" in r.lower() for r in hard_reasons) or (tender_data.get("status") or "").lower().strip() in ("annule", "annulé")
        if is_cancelled:
            return CascadeEvaluationResult(
                overall_score=0.0,
                decision_recommendation="NO-GO",
                coverage_score=0.0,
                lexical_score=0.0,
                feasibility_score=0.0,
                line_item_matches=[],
                red_flags=["Tender is officially cancelled ('Annulé')."],
                llm_reasoning="Disqualified at Stage 1 (Hard Gate): Tender is officially cancelled ('Annulé')."
            )

        # Build full text for lexical search
        full_text = f"{tender_data.get('title', '')} {tender_data.get('prestation_type', '')}"
        for item in tender_data.get("line_items", []):
            full_text += f" {item.get('designation', '')} {item.get('technical_specs', '')}"

        # --- Stage 2: Lexical Match & Negative Keyword Veto ---
        passed_lexical, veto_reason, lexical_score = LexicalMatcher.evaluate(full_text, profile)

        # If hard negative keyword veto (e.g. gardiennage, traiteur, maçonnerie): instant elimination
        if not passed_lexical:
            return CascadeEvaluationResult(
                overall_score=0.0,
                decision_recommendation="NO-GO",
                coverage_score=0.0,
                lexical_score=0.0,
                feasibility_score=0.0,
                line_item_matches=[],
                red_flags=[veto_reason or "Veto par mot-clé négatif exclu"],
                llm_reasoning=f"Disqualifié par exclusion négative : {veto_reason}"
            )

        # --- Stage 3: Line-Item Catalog Mapping (BOM Coverage) ---
        line_items = tender_data.get("line_items", [])
        coverage_score, item_evals, unmatched_items = LineItemMatcher.match_line_items(
            line_items, 
            profile
        )

        weights = profile.scoring_weights
        has_geo_issue = any("régions" in r.lower() for r in hard_reasons)
        feasibility_score = 50.0 if has_geo_issue else 100.0

        # Technical Alignment Score (based on actual products, specifications, and keywords)
        tech_alignment_score = (
            (coverage_score * weights.line_item_coverage) +
            (lexical_score * weights.semantic_similarity) +
            (feasibility_score * weights.feasibility_proximity)
        )
        tech_alignment_score = min(100.0, max(0.0, tech_alignment_score))

        # --- Stage 4: Decision Synthesis & Operational Verdict ---
        red_flags = list(hard_reasons)
        is_cancelled = any("annulée" in r.lower() for r in hard_reasons)
        is_expired = any("dépassée" in r.lower() or "clôturé" in r.lower() for r in hard_reasons)
        is_urgent = any("court" in r.lower() or "urgent" in r.lower() for r in hard_reasons)

        if is_cancelled:
            overall_score = round(tech_alignment_score, 1)
            verdict = "ANNULÉ"
            reasoning = "Consultation officiellement annulée par l'acheteur public."
        elif is_expired:
            overall_score = round(tech_alignment_score, 1)
            verdict = "CLÔTURÉ"
            covered_count = len(line_items) - len(unmatched_items)
            reasoning = (
                f"Date limite de dépôt dépassée. Alignement technique du catalogue : "
                f"{coverage_score:.0f}% d'articles couverts ({covered_count}/{len(line_items)} articles)."
            )
        elif tech_alignment_score >= 65.0:
            # High-confidence candidate: Evaluate with LLM judge or structured heuristics
            judge_res = await self.llm_judge.evaluate_candidate(
                tender_data, profile, coverage_score, unmatched_items
            )
            final_score = round((tech_alignment_score * 0.7) + (judge_res["fit_score"] * 0.3), 1)
            verdict = judge_res["match_verdict"]
            reasoning = judge_res["deliverability_analysis"]
            red_flags.extend(judge_res.get("red_flags", []))
            overall_score = final_score
            
            if is_urgent and verdict == "GO":
                verdict = "CONSIDER"
                red_flags.append("Délai de soumission très court (< 24h)")
        else:
            overall_score = round(tech_alignment_score, 1)
            verdict = "CONSIDER" if overall_score >= 45.0 else "NO-GO"
            reasoning = f"Évaluation catalogue : {coverage_score:.0f}% d'articles couverts, score lexical {lexical_score:.0f}%."
            if unmatched_items:
                red_flags.append(f"Articles non couverts : {', '.join(unmatched_items[:3])}")

        return CascadeEvaluationResult(
            overall_score=overall_score,
            decision_recommendation=verdict,
            coverage_score=coverage_score,
            lexical_score=lexical_score,
            feasibility_score=feasibility_score,
            line_item_matches=item_evals,
            red_flags=red_flags,
            llm_reasoning=reasoning
        )
