import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from src.profiles.schema import CompanyProfileSchema
from src.engine.hard_filters import evaluate_hard_filters
from src.engine.lexical_matcher import LexicalMatcher
from src.engine.line_item_matcher import LineItemMatcher
from src.engine.llm_judge import LLMJudge
from src.engine.cancellation_tracker import is_cancellation_notice, extract_target_cancelled_reference
from src.engine.feedback_manager import feedback_manager

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
    alignment_feedback: Optional[str] = None # 'aligned', 'misaligned', or None
    learned_exemplar_bonus: float = 0.0

# In-memory evaluation cache: (portal_id, profile_name) -> (passed_lexical, veto_reason, lexical_score, coverage_score, item_evals, unmatched_items)
_STAGE23_CACHE: Dict[Tuple[int, str], Tuple[bool, Optional[str], float, float, List[Dict[str, Any]], List[str]]] = {}

def invalidate_tender_cache(portal_id: int, profile_name: Optional[str] = None):
    """Invalidates cached scoring results when feedback or tender data changes"""
    keys_to_delete = [
        k for k in _STAGE23_CACHE.keys() 
        if k[0] == portal_id and (profile_name is None or k[1] == profile_name)
    ]
    for k in keys_to_delete:
        del _STAGE23_CACHE[k]

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

        # Cancelled tenders (or cancellation notices) are immediately dropped at Stage 1
        is_cancelled = (
            any("annul" in r.lower() for r in hard_reasons)
            or (tender_data.get("status") or "").lower().strip() in ("annule", "annulé", "cancelled")
            or is_cancellation_notice(tender_data.get("title"), tender_data.get("reference"))
        )
        if is_cancelled:
            target_ref = extract_target_cancelled_reference(tender_data.get("title"), tender_data.get("reference"))
            target_msg = f" (Avis d'annulation visant réf: {target_ref})" if target_ref else ""
            return CascadeEvaluationResult(
                overall_score=0.0,
                decision_recommendation="NO-GO",
                coverage_score=0.0,
                lexical_score=0.0,
                feasibility_score=0.0,
                line_item_matches=[],
                red_flags=[f"Tender is officially cancelled ('Annulé'){target_msg}."],
                llm_reasoning=f"Disqualified at Stage 1 (Hard Gate): Tender is officially cancelled ('Annulé'){target_msg}."
            )

        # --- Stages 2 & 3: Lexical Matching & BOM Catalog Coverage (with in-memory cache) ---
        line_items = tender_data.get("line_items", [])
        portal_id = tender_data.get("portal_id")
        cache_key = (portal_id, profile.profile_name) if portal_id else None

        cached_stage23 = _STAGE23_CACHE.get(cache_key) if cache_key else None
        if cached_stage23 is not None:
            passed_lexical, veto_reason, lexical_score, coverage_score, item_evals, unmatched_items = cached_stage23
        else:
            # Build full text for lexical search
            full_text = f"{tender_data.get('title', '')} {tender_data.get('prestation_type', '')}"
            for item in line_items:
                full_text += f" {item.get('designation', '')} {item.get('technical_specs', '')}"

            # --- Stage 2: Lexical Match & Negative Keyword Veto ---
            passed_lexical, veto_reason, lexical_score = LexicalMatcher.evaluate(full_text, profile)

            coverage_score, item_evals, unmatched_items = 0.0, [], []
            if passed_lexical:
                # --- Stage 3: Line-Item Catalog Mapping (BOM Coverage) ---
                coverage_score, item_evals, unmatched_items = LineItemMatcher.match_line_items(
                    line_items, 
                    profile
                )

            if cache_key:
                _STAGE23_CACHE[cache_key] = (passed_lexical, veto_reason, lexical_score, coverage_score, item_evals, unmatched_items)

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

        weights = profile.scoring_weights
        has_geo_issue = any("région" in r.lower() or "territoire" in r.lower() for r in hard_reasons)
        feasibility_score = 40.0 if has_geo_issue else 100.0

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

        # --- Stage 5: Domain Expert Reinforcement (RLHF) & Active Learning Adjustment ---
        feedback = feedback_manager.get_feedback(portal_id, profile.profile_name) if portal_id else None
        feedback_status = None
        learned_bonus = 0.0

        if feedback is not None:
            if feedback.get("is_aligned"):
                feedback_status = "aligned"
                if not is_cancelled and not is_expired:
                    overall_score = max(88.0, min(100.0, round(overall_score + 15.0, 1)))
                    verdict = "GO"
                    reasoning = f"✅ Alignement confirmé par l'expert ({feedback.get('user_name', 'Analyste')}) : score bonifié (+15%)."
            else:
                feedback_status = "misaligned"
                overall_score = min(20.0, overall_score)
                verdict = "NO-GO"
                reasoning = f"❌ Signalé hors secteur par l'expert ({feedback.get('user_name', 'Analyste')}) : Faux positif exclu."
                red_flags.append("Signalé hors secteur par l'analyste métier.")
        else:
            # Active Learning vocabulary adjustment for unreviewed tenders
            full_tender_text = f"{tender_data.get('title', '')} {tender_data.get('prestation_type', '')}"
            learned_delta, matched_terms = feedback_manager.calculate_active_learning_adjustment(full_tender_text, profile.profile_name)
            if learned_delta != 0.0 and not is_cancelled and not is_expired:
                overall_score = min(100.0, max(0.0, round(overall_score + learned_delta, 1)))
                learned_bonus = learned_delta
                if overall_score >= 80.0 and verdict not in ("CLÔTURÉ", "ANNULÉ") and not is_urgent:
                    verdict = "GO"
                elif overall_score >= 50.0 and verdict == "NO-GO":
                    verdict = "CONSIDER"
                if matched_terms:
                    reasoning += f" • 🧠 Modèle calibré par retours d'expérience (+{learned_delta}% sur: {', '.join(matched_terms[:3])})"

        return CascadeEvaluationResult(
            overall_score=overall_score,
            decision_recommendation=verdict,
            coverage_score=coverage_score,
            lexical_score=lexical_score,
            feasibility_score=feasibility_score,
            line_item_matches=item_evals,
            red_flags=red_flags,
            llm_reasoning=reasoning,
            alignment_feedback=feedback_status,
            learned_exemplar_bonus=learned_bonus
        )
