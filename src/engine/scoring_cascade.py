import logging
from dataclasses import dataclass
from typing import Dict, Any, List
from src.profiles.schema import CompanyProfileSchema
from src.engine.hard_filters import evaluate_hard_filters
from src.engine.lexical_matcher import LexicalMatcher
from src.engine.line_item_matcher import LineItemMatcher
from src.engine.llm_judge import LLMJudge

logger = logging.getLogger(__name__)

@dataclass
class CascadeEvaluationResult:
    overall_score: float
    decision_recommendation: str  # 'GO', 'CONSIDER', 'NO-GO'
    coverage_score: float
    lexical_score: float
    feasibility_score: float
    line_item_matches: List[Dict[str, Any]]
    red_flags: List[str]
    llm_reasoning: str

class ScoringCascadeEngine:
    """
    Unified 4-Stage Cascade Scoring Engine:
    Stage 1: Hard Binary Elimination Gate
    Stage 2: Lexical Veto & BM25 Match
    Stage 3: Line-Item BOM Catalog Coverage
    Stage 4: LLM Judge & Margin Estimation
    """
    def __init__(self, llm_judge: LLMJudge | None = None):
        self.llm_judge = llm_judge or LLMJudge()

    async def evaluate_tender(
        self, 
        tender_data: Dict[str, Any], 
        profile: CompanyProfileSchema
    ) -> CascadeEvaluationResult:
        # --- Stage 1: Hard Gates ---
        is_eligible, hard_reasons = evaluate_hard_filters(tender_data, profile)
        if not is_eligible:
            return CascadeEvaluationResult(
                overall_score=0.0,
                decision_recommendation="NO-GO",
                coverage_score=0.0,
                lexical_score=0.0,
                feasibility_score=0.0,
                line_item_matches=[],
                red_flags=hard_reasons,
                llm_reasoning=f"Disqualified at Stage 1 (Hard Gate): {'; '.join(hard_reasons)}"
            )

        # Build full text for lexical search
        full_text = f"{tender_data.get('title', '')} {tender_data.get('prestation_type', '')}"
        for item in tender_data.get("line_items", []):
            full_text += f" {item.get('designation', '')} {item.get('technical_specs', '')}"

        # --- Stage 2: Lexical Match & Veto ---
        passed_lexical, veto_reason, lexical_score = LexicalMatcher.evaluate(full_text, profile)
        if not passed_lexical:
            return CascadeEvaluationResult(
                overall_score=0.0,
                decision_recommendation="NO-GO",
                coverage_score=0.0,
                lexical_score=0.0,
                feasibility_score=0.0,
                line_item_matches=[],
                red_flags=[veto_reason or "Vetoed by keyword constraint"],
                llm_reasoning=f"Disqualified at Stage 2: {veto_reason}"
            )

        # --- Stage 3: Line-Item Catalog Mapping ---
        coverage_score, item_evals, unmatched_items = LineItemMatcher.match_line_items(
            tender_data.get("line_items", []), 
            profile
        )

        weights = profile.scoring_weights
        feasibility_score = 100.0  # Passed hard location filter

        # Composite mathematical score
        composite_score = (
            (coverage_score * weights.line_item_coverage) +
            (lexical_score * weights.semantic_similarity) +
            (feasibility_score * weights.feasibility_proximity)
        )
        composite_score = min(100.0, max(0.0, composite_score))

        # --- Stage 4: LLM Judge on top candidates ---
        if composite_score >= 65.0:
            judge_res = await self.llm_judge.evaluate_candidate(
                tender_data, profile, coverage_score, unmatched_items
            )
            final_score = round((composite_score * 0.7) + (judge_res["fit_score"] * 0.3), 1)
            verdict = judge_res["match_verdict"]
            reasoning = judge_res["deliverability_analysis"]
            red_flags = judge_res["red_flags"]
        else:
            final_score = round(composite_score, 1)
            verdict = "CONSIDER" if final_score >= 45.0 else "NO-GO"
            reasoning = f"Evaluated by catalog matching: {coverage_score:.0f}% line-item coverage."
            red_flags = [f"Unmatched items: {', '.join(unmatched_items[:3])}"] if unmatched_items else []

        return CascadeEvaluationResult(
            overall_score=final_score,
            decision_recommendation=verdict,
            coverage_score=coverage_score,
            lexical_score=lexical_score,
            feasibility_score=feasibility_score,
            line_item_matches=item_evals,
            red_flags=red_flags,
            llm_reasoning=reasoning
        )

