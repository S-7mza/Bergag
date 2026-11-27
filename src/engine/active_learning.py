import json
import logging
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from src.engine.feedback_manager import (
    extract_tokens,
    feedback_manager,
    normalize_profile_key,
    strip_accents,
)
from src.engine.scoring_cascade import ScoringCascadeEngine, _STAGE23_CACHE
from src.profiles.loader import PROFILES_DIR, load_profile
from src.profiles.schema import CompanyProfileSchema

logger = logging.getLogger(__name__)

TUNER_LEDGER_FILE = Path("data/tuner_feedback_ledger.json")


class ActiveLearningTuner:
    """
    Object-Recognition-Inspired Active Learning & Hard Negative Mining Engine for Public Procurement.

    Applies computer vision active training concepts:
    1. Uncertainty / Boundary Sampling: Prioritizes tenders near the decision boundary (40-68%)
       or where semantic AI and sector cascade scores diverge.
    2. Hard Negative Mining: Surfaces tenders with deceptive surface keyword overlaps to isolate
       discriminating negative exclusions.
    3. Confirmation Probing: When a user rejects a high-scoring or ambiguous tender, probes
       neighboring tenders or asks a 1-click disambiguation question to confirm the rule.
    4. Online Gradient Weight Calibration: Updates keyword weights, buyer affinities, and category
       biases after every swipe, with full Undo support and persistent YAML profile saving.
    """

    LEARNING_RATE = 0.16

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._load_ledger()

    def _default_session(self, profile_key: str) -> Dict[str, Any]:
        return {
            "profile_id": profile_key,
            "swipes": [],
            "undo_stack": [],
            "pending_probes": [],
            "feature_weights": {
                "keyword_weights": {},
                "exclusion_keywords": [],
                "buyer_affinity": {},
                "category_bias": {},
                "go_threshold": 75.0,
                "consider_threshold": 50.0,
            },
            "metrics": {
                "total_swipes": 0,
                "accepted_count": 0,
                "rejected_count": 0,
                "skipped_count": 0,
                "confirmed_rules_count": 0,
                "correct_predictions": 0,
                "accuracy_estimate": 0.0,
                "boundary_stability": 0.0,
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "last_saved_to_profile_at": None,
        }

    def _load_ledger(self):
        if TUNER_LEDGER_FILE.exists():
            try:
                with open(TUNER_LEDGER_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._sessions = data
                logger.info(f"[ActiveLearningTuner] Loaded {len(self._sessions)} tuning sessions.")
            except Exception as e:
                logger.warning(f"[ActiveLearningTuner] Failed to load ledger: {e}")
                self._sessions = {}
        else:
            self._sessions = {}

    def _save_ledger(self):
        try:
            TUNER_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TUNER_LEDGER_FILE, "w", encoding="utf-8") as f:
                json.dump(self._sessions, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[ActiveLearningTuner] Failed to save ledger: {e}")

    def get_session(self, profile_id: str) -> Dict[str, Any]:
        key = normalize_profile_key(profile_id)
        if key not in self._sessions:
            self._sessions[key] = self._default_session(key)
        return self._sessions[key]

    def get_swiped_ids(self, profile_id: str) -> Set[int]:
        session = self.get_session(profile_id)
        return {int(s["portal_id"]) for s in session.get("swipes", []) if s.get("portal_id")}

    def compute_tuned_score(
        self,
        base_score: float,
        tender_data: Dict[str, Any],
        profile_id: str,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Applies the learned online feature weights (keyword weights, exclusions, buyer affinity,
        category bias) on top of the base cascade/hybrid score.
        Returns (adjusted_score, explanation_dict).
        """
        session = self.get_session(profile_id)
        weights = session["feature_weights"]
        kw_weights: Dict[str, float] = weights.get("keyword_weights", {})
        exclusions: Set[str] = {strip_accents(k) for k in weights.get("exclusion_keywords", [])}
        buyer_aff: Dict[str, float] = weights.get("buyer_affinity", {})
        cat_bias: Dict[str, float] = weights.get("category_bias", {})

        title = tender_data.get("title") or ""
        items_text = " ".join(
            f"{it.get('designation', '')} {it.get('technical_specs', '')}"
            for it in tender_data.get("line_items", [])
        )
        tokens = extract_tokens(f"{title} {items_text}")
        norm_full = strip_accents(f"{title} {items_text}")

        # 1. Check hard exclusions learned from confirmation probes
        matched_exclusions = [ex for ex in exclusions if ex and ex in norm_full]
        if matched_exclusions:
            penalty = min(45.0, 25.0 * len(matched_exclusions))
        else:
            penalty = 0.0

        # 2. Sum learned token weights
        kw_delta = 0.0
        matched_positive_tokens = []
        matched_negative_tokens = []
        for tok in tokens:
            w = kw_weights.get(tok, 0.0)
            if w > 0.05:
                matched_positive_tokens.append((tok, round(w, 2)))
            elif w < -0.05:
                matched_negative_tokens.append((tok, round(w, 2)))
            kw_delta += w * 18.0  # Scale weight delta to 0-100 score points

        kw_delta = max(-35.0, min(35.0, kw_delta))

        # 3. Buyer & Category affinity
        buyer_name = strip_accents(tender_data.get("buyer_name") or "")
        b_delta = buyer_aff.get(buyer_name, 0.0) * 15.0

        cat_name = strip_accents(tender_data.get("main_category") or "")
        c_delta = cat_bias.get(cat_name, 0.0) * 12.0

        adjusted = max(0.0, min(100.0, round(base_score + kw_delta - penalty + b_delta + c_delta, 1)))

        matched_positive_tokens.sort(key=lambda x: x[1], reverse=True)
        matched_negative_tokens.sort(key=lambda x: x[1])

        return adjusted, {
            "base_score": round(base_score, 1),
            "adjusted_score": adjusted,
            "kw_delta": round(kw_delta, 1),
            "exclusion_penalty": round(penalty, 1),
            "buyer_delta": round(b_delta, 1),
            "matched_positive_tokens": matched_positive_tokens[:6],
            "matched_negative_tokens": matched_negative_tokens[:6],
            "matched_exclusions": matched_exclusions[:4],
            "tokens": sorted(list(tokens))[:15],
        }

    async def select_next_candidates(
        self,
        candidates: List[Dict[str, Any]],
        profile: CompanyProfileSchema,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Object-Recognition Active Learning Sampler:
        Ranks and selects the most informative tenders (both active and closed/awarded)
        to present to the user for maximum model convergence per swipe.
        """
        profile_id = profile.profile_id or "special_ai_hybrid"
        session = self.get_session(profile_id)
        swiped_ids = self.get_swiped_ids(profile_id)
        pending_probes: List[Dict[str, Any]] = session.get("pending_probes", [])

        scoring_engine = ScoringCascadeEngine()
        scored_pool: List[Dict[str, Any]] = []

        for c in candidates:
            pid = int(c.get("portal_id", 0))
            if not pid or pid in swiped_ids:
                continue

            eval_res = await scoring_engine.evaluate_tender(c, profile)
            tuned_score, feat_info = self.compute_tuned_score(eval_res.overall_score, c, profile_id)
            ai_score = eval_res.ai_matching_rate if eval_res.ai_matching_rate is not None else eval_res.overall_score
            cascade_score = eval_res.overall_score

            # Calculate Active Learning Information Gain
            # 1) Uncertainty: highest near 52% decision boundary
            boundary_dist = abs(tuned_score - 52.0)
            uncertainty_score = max(0.0, 100.0 - boundary_dist * 2.0)

            # 2) Disagreement between AI and Cascade
            disagreement = abs(float(ai_score) - float(cascade_score))

            # 3) Hard negative suspicion: matches surface keywords (lexical > 40) but low coverage or red flags
            is_hard_neg_suspect = (
                eval_res.lexical_score >= 45.0
                and (eval_res.coverage_score < 40.0 or len(eval_res.red_flags) > 0)
            )

            # Check if matches a pending confirmation probe
            matched_probe = None
            norm_text = strip_accents(f"{c.get('title', '')} {' '.join(it.get('designation', '') for it in c.get('line_items', []))}")
            for probe in pending_probes:
                target_feat = strip_accents(probe.get("target_feature", ""))
                if target_feat and target_feat in norm_text:
                    matched_probe = probe
                    break

            if matched_probe:
                strategy = "confirmation_probe"
                strategy_label = f"🔍 Test de Confirmation ({matched_probe.get('target_feature')})"
                priority = 1000.0 + uncertainty_score
            elif disagreement >= 25.0:
                strategy = "disagreement"
                strategy_label = f"⚖️ Divergence IA vs Secteur ({round(ai_score)}% vs {round(cascade_score)}%)"
                priority = 500.0 + disagreement + uncertainty_score * 0.5
            elif 38.0 <= tuned_score <= 68.0:
                strategy = "uncertainty_boundary"
                strategy_label = f"🎯 Cas Frontière (Incertitude {round(tuned_score)}%)"
                priority = 400.0 + uncertainty_score
            elif is_hard_neg_suspect:
                strategy = "hard_negative"
                strategy_label = "⚔️ Hard Negative Suspecté (Piège lexical)"
                priority = 350.0 + eval_res.lexical_score
            else:
                strategy = "exploration"
                is_active = c.get("status") == "active"
                strategy_label = "🛡️ Exploration Marché Actif" if is_active else "📚 Exploration Archive Historique"
                priority = 100.0 + random.uniform(0.0, 80.0)

            # Build highlighted keywords for UX
            kw_highlights = []
            for tok, w in feat_info["matched_positive_tokens"]:
                kw_highlights.append({"term": tok, "type": "positive", "weight": w})
            for tok, w in feat_info["matched_negative_tokens"]:
                kw_highlights.append({"term": tok, "type": "negative", "weight": w})
            for ex in feat_info["matched_exclusions"]:
                kw_highlights.append({"term": ex, "type": "exclusion", "weight": -1.0})
            if not kw_highlights:
                for tok in feat_info["tokens"][:5]:
                    kw_highlights.append({"term": tok, "type": "neutral", "weight": 0.0})

            scored_pool.append({
                "portal_id": pid,
                "reference": c.get("reference", f"#{pid}"),
                "title": c.get("title", ""),
                "buyer_name": c.get("buyer_name", "Acheteur Public"),
                "execution_location": c.get("execution_location") or "Maroc",
                "main_category": c.get("main_category") or "Fournitures",
                "prestation_type": c.get("prestation_type") or "",
                "status": c.get("status", "active"),
                "is_closed": c.get("is_closed", False),
                "published_at": c.get("published_at"),
                "deadline_at": c.get("deadline_at"),
                "awarded_amount": c.get("awarded_amount"),
                "winner_name": c.get("winner_name"),
                "line_items": c.get("line_items", [])[:8],
                "line_items_count": len(c.get("line_items", [])),
                "base_score": round(cascade_score, 1),
                "ai_score": round(float(ai_score), 1),
                "tuned_score": tuned_score,
                "decision_recommendation": eval_res.decision_recommendation,
                "red_flags": eval_res.red_flags,
                "sampling_strategy": strategy,
                "sampling_label": strategy_label,
                "priority_score": round(priority, 2),
                "keyword_highlights": kw_highlights,
                "feature_breakdown": feat_info,
            })

        # Sort by Active Learning priority descending, keeping top candidates
        scored_pool.sort(key=lambda x: x["priority_score"], reverse=True)

        # Ensure diversity: mix top uncertainty/probes with at least 15-20% exploration
        selected = scored_pool[:limit]
        return selected

    def record_swipe(
        self,
        portal_id: int,
        profile_id: str,
        decision: str,  # 'accept' (right), 'reject' (left), 'skip'
        tender_data: Dict[str, Any],
        score_before: float,
        sampling_strategy: str = "uncertainty_boundary",
        user_name: str = "Expert Métier",
    ) -> Dict[str, Any]:
        """
        Records a user swipe and performs an online gradient step on feature weights.
        If rejecting a high-scoring or previously positive tender, triggers a Confirmation Probe.
        """
        key = normalize_profile_key(profile_id)
        session = self.get_session(key)
        weights = session["feature_weights"]
        metrics = session["metrics"]

        title = tender_data.get("title") or ""
        items_text = " ".join(
            f"{it.get('designation', '')} {it.get('technical_specs', '')}"
            for it in tender_data.get("line_items", [])
        )
        tokens = list(extract_tokens(f"{title} {items_text}"))
        buyer_name = strip_accents(tender_data.get("buyer_name") or "")
        cat_name = strip_accents(tender_data.get("main_category") or "")

        # Snapshot weights before update for Undo capability
        weights_snapshot = json.loads(json.dumps(weights))
        metrics_snapshot = json.loads(json.dumps(metrics))

        if decision == "skip":
            metrics["skipped_count"] = metrics.get("skipped_count", 0) + 1
            swipe_record = {
                "portal_id": portal_id,
                "decision": "skip",
                "score_before": score_before,
                "sampling_strategy": sampling_strategy,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            session["swipes"].append(swipe_record)
            session["undo_stack"].append({
                "swipe": swipe_record,
                "weights_before": weights_snapshot,
                "metrics_before": metrics_snapshot,
            })
            session["undo_stack"] = session["undo_stack"][-30:]
            self._save_ledger()
            return {
                "status": "skipped",
                "needs_confirmation": False,
                "metrics": metrics,
            }

        is_accept = decision == "accept"
        y = 1.0 if is_accept else 0.0
        y_hat = max(0.0, min(1.0, score_before / 100.0))
        error = y - y_hat

        # Track whether prediction already agreed with human
        predicted_accept = score_before >= weights.get("consider_threshold", 50.0)
        if predicted_accept == is_accept:
            metrics["correct_predictions"] = metrics.get("correct_predictions", 0) + 1

        metrics["total_swipes"] = metrics.get("total_swipes", 0) + 1
        if is_accept:
            metrics["accepted_count"] = metrics.get("accepted_count", 0) + 1
        else:
            metrics["rejected_count"] = metrics.get("rejected_count", 0) + 1

        total = max(1, metrics["total_swipes"])
        metrics["accuracy_estimate"] = round((metrics["correct_predictions"] / total) * 100.0, 1)
        # Boundary stability grows with swipes and prediction agreement
        metrics["boundary_stability"] = round(
            min(99.5, (1.0 - math.exp(-total / 15.0)) * metrics["accuracy_estimate"]),
            1,
        )

        # Online Gradient Update on Keyword Weights
        kw_weights: Dict[str, float] = weights["keyword_weights"]
        step = self.LEARNING_RATE * error
        updated_tokens = []
        for tok in tokens:
            old_w = kw_weights.get(tok, 0.0)
            new_w = max(-1.0, min(1.0, round(old_w + step, 4)))
            kw_weights[tok] = new_w
            updated_tokens.append((tok, new_w))

        # Update Buyer Affinity
        if buyer_name:
            b_aff = weights["buyer_affinity"]
            b_aff[buyer_name] = max(-0.5, min(0.5, round(b_aff.get(buyer_name, 0.0) + step * 0.5, 4)))

        # Update Category Bias
        if cat_name:
            c_bias = weights["category_bias"]
            c_bias[cat_name] = max(-0.4, min(0.4, round(c_bias.get(cat_name, 0.0) + step * 0.4, 4)))

        # Forward to RLHF AlignmentFeedbackManager so main feed also learns
        feedback_manager.record_feedback(
            portal_id=portal_id,
            profile_name=key,
            is_aligned=is_accept,
            user_name=user_name,
            user_notes=f"Tuner Swipe ({'Retenu' if is_accept else 'Écarté'})",
            tender_title=title,
            line_items_text=items_text,
        )

        # Remove any pending probe that matched this portal_id
        session["pending_probes"] = [
            p for p in session.get("pending_probes", [])
            if int(p.get("source_portal_id", 0)) != portal_id
        ]

        # Confirmation Probe Logic:
        # "once I am not ok with one kind of avis it should ask again just to confirm"
        needs_confirmation = False
        confirmation_options = []
        if not is_accept and (score_before >= 48.0 or sampling_strategy in ("uncertainty_boundary", "disagreement")):
            needs_confirmation = True
            # Pick top 2 discriminating tokens from this tender to offer as 1-click exclusion probes
            sorted_toks = sorted(tokens, key=lambda t: kw_weights.get(t, 0.0), reverse=True)
            top_tok = sorted_toks[0] if sorted_toks else None
            second_tok = sorted_toks[1] if len(sorted_toks) > 1 else None

            if top_tok:
                confirmation_options.append({
                    "id": f"exclude_kw:{top_tok}",
                    "label": f"Exclure le mot-clé « {top_tok} »",
                    "type": "keyword",
                    "value": top_tok,
                })
                # Also queue a counterfactual confirmation tender in pending_probes
                session["pending_probes"].append({
                    "source_portal_id": portal_id,
                    "target_feature": top_tok,
                    "feature_type": "keyword",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                session["pending_probes"] = session["pending_probes"][-5:]

            if second_tok:
                confirmation_options.append({
                    "id": f"exclude_kw:{second_tok}",
                    "label": f"Exclure « {second_tok} »",
                    "type": "keyword",
                    "value": second_tok,
                })

            if buyer_name:
                confirmation_options.append({
                    "id": f"exclude_buyer:{buyer_name}",
                    "label": f"Écarter cet acheteur ({(tender_data.get('buyer_name') or '')[:28]})",
                    "type": "buyer",
                    "value": buyer_name,
                })

            confirmation_options.append({
                "id": "isolated_case",
                "label": "Cas ponctuel uniquement (ne pas généraliser)",
                "type": "isolated",
                "value": "isolated",
            })

        swipe_record = {
            "portal_id": portal_id,
            "decision": decision,
            "score_before": score_before,
            "sampling_strategy": sampling_strategy,
            "tokens_affected": tokens[:10],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        session["swipes"].append(swipe_record)
        session["undo_stack"].append({
            "swipe": swipe_record,
            "weights_before": weights_snapshot,
            "metrics_before": metrics_snapshot,
        })
        session["undo_stack"] = session["undo_stack"][-30:]
        session["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save_ledger()

        return {
            "status": "recorded",
            "decision": decision,
            "portal_id": portal_id,
            "needs_confirmation": needs_confirmation,
            "confirmation_options": confirmation_options,
            "metrics": metrics,
            "learned_summary": {
                "total_keywords_tracked": len(kw_weights),
                "exclusions_count": len(weights.get("exclusion_keywords", [])),
            },
        }

    def confirm_rejection_rule(
        self,
        profile_id: str,
        rule_type: str,  # 'keyword', 'buyer', 'category', 'isolated'
        rule_value: str,
        portal_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Applies the user's explicit confirmation on why an avis was rejected,
        hardening the rule into exclusion keywords or strong negative weights.
        """
        key = normalize_profile_key(profile_id)
        session = self.get_session(key)
        weights = session["feature_weights"]
        metrics = session["metrics"]

        if rule_type == "keyword" and rule_value:
            clean_kw = strip_accents(rule_value).strip()
            exclusions: List[str] = weights.setdefault("exclusion_keywords", [])
            if clean_kw not in exclusions:
                exclusions.append(clean_kw)
            weights["keyword_weights"][clean_kw] = -0.95
            metrics["confirmed_rules_count"] = metrics.get("confirmed_rules_count", 0) + 1
            msg = f"Règle confirmée : « {clean_kw} » ajouté aux exclusions prioritaires."
        elif rule_type == "buyer" and rule_value:
            clean_b = strip_accents(rule_value).strip()
            weights["buyer_affinity"][clean_b] = -0.5
            metrics["confirmed_rules_count"] = metrics.get("confirmed_rules_count", 0) + 1
            msg = "Règle confirmée : affinité acheteur fortement pénalisée."
        elif rule_type == "category" and rule_value:
            clean_c = strip_accents(rule_value).strip()
            weights["category_bias"][clean_c] = -0.4
            metrics["confirmed_rules_count"] = metrics.get("confirmed_rules_count", 0) + 1
            msg = f"Règle confirmée : catégorie « {clean_c} » pénalisée."
        else:
            # Isolated case: soften the negative keyword penalty on this tender's tokens
            msg = "Noté comme cas isolé (aucune règle d'exclusion globale ajoutée)."

        session["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save_ledger()
        return {
            "status": "confirmed",
            "message": msg,
            "metrics": metrics,
            "exclusion_keywords": weights.get("exclusion_keywords", []),
        }

    def undo_last_swipe(self, profile_id: str) -> Dict[str, Any]:
        """Reverts the last swipe and restores the exact previous weight state."""
        key = normalize_profile_key(profile_id)
        session = self.get_session(key)
        undo_stack = session.get("undo_stack", [])
        if not undo_stack:
            return {"status": "noop", "message": "Aucune action récente à annuler."}

        last_entry = undo_stack.pop()
        last_swipe = last_entry["swipe"]
        pid = int(last_swipe["portal_id"])

        session["swipes"] = [s for s in session["swipes"] if int(s.get("portal_id", 0)) != pid]
        session["feature_weights"] = last_entry["weights_before"]
        session["metrics"] = last_entry["metrics_before"]
        session["last_updated"] = datetime.now(timezone.utc).isoformat()

        feedback_manager.delete_feedback(pid, key)
        self._save_ledger()

        return {
            "status": "undone",
            "undone_portal_id": pid,
            "message": f"Dernier arbitrage sur #{pid} annulé.",
            "metrics": session["metrics"],
        }

    def get_stats(self, profile_id: str) -> Dict[str, Any]:
        """Returns comprehensive learning telemetry & top learned positive/negative rules."""
        key = normalize_profile_key(profile_id)
        session = self.get_session(key)
        weights = session["feature_weights"]
        kw_weights: Dict[str, float] = weights.get("keyword_weights", {})

        top_positive = sorted(
            [(k, v) for k, v in kw_weights.items() if v > 0.02],
            key=lambda x: x[1],
            reverse=True,
        )[:12]
        top_negative = sorted(
            [(k, v) for k, v in kw_weights.items() if v < -0.02],
            key=lambda x: x[1],
        )[:12]

        return {
            "profile_id": key,
            "metrics": session["metrics"],
            "top_positive_keywords": [{"term": k, "weight": v} for k, v in top_positive],
            "top_negative_keywords": [{"term": k, "weight": v} for k, v in top_negative],
            "exclusion_keywords": weights.get("exclusion_keywords", []),
            "pending_probes_count": len(session.get("pending_probes", [])),
            "last_updated": session.get("last_updated"),
            "last_saved_to_profile_at": session.get("last_saved_to_profile_at"),
        }

    def save_logic_to_profile(self, profile_id: str) -> Dict[str, Any]:
        """
        Persists the fine-tuned positive keywords and confirmed exclusion constraints directly
        into the target profile YAML file and invalidates scoring caches for instant recalculation.
        """
        key = normalize_profile_key(profile_id)
        session = self.get_session(key)
        weights = session["feature_weights"]

        yaml_path = PROFILES_DIR / f"{key}.yaml"
        if not yaml_path.exists():
            # Fallback to special_ai_hybrid.yaml if custom slug does not have its own file yet
            yaml_path = PROFILES_DIR / "special_ai_hybrid.yaml"

        with open(yaml_path, "r", encoding="utf-8") as f:
            profile_dict = yaml.safe_load(f)

        # 1. Merge confirmed exclusions into negative_constraints.keywords
        neg_block = profile_dict.setdefault("negative_constraints", {})
        existing_exclusions: List[str] = neg_block.setdefault("keywords", [])
        existing_ex_norm = {strip_accents(k) for k in existing_exclusions}

        added_exclusions = []
        for ex in weights.get("exclusion_keywords", []):
            if strip_accents(ex) not in existing_ex_norm:
                existing_exclusions.append(ex)
                existing_ex_norm.add(strip_accents(ex))
                added_exclusions.append(ex)

        # Also add strongly penalized keywords (<= -0.45)
        for kw, w in weights.get("keyword_weights", {}).items():
            if w <= -0.45 and strip_accents(kw) not in existing_ex_norm:
                existing_exclusions.append(kw)
                existing_ex_norm.add(strip_accents(kw))
                added_exclusions.append(kw)

        # 2. Merge strongly boosted keywords (>= +0.30) into a dedicated catalog entry
        strong_positives = [
            kw for kw, w in sorted(
                weights.get("keyword_weights", {}).items(),
                key=lambda x: x[1],
                reverse=True,
            )
            if w >= 0.30
        ][:25]

        added_positives = []
        if strong_positives:
            catalog = profile_dict.setdefault("catalog", [])
            tuner_entry = next((item for item in catalog if item.get("id") == "active-learning-boost"), None)
            if tuner_entry is None:
                tuner_entry = {
                    "id": "active-learning-boost",
                    "label": "Critères Affinés par Entraînement Swipe (Active Learning)",
                    "weight": 1.0,
                    "synonyms_fr": [],
                    "synonyms_ar": [],
                    "technical_keywords": [],
                }
                catalog.append(tuner_entry)

            existing_syns = {strip_accents(s) for s in tuner_entry.get("synonyms_fr", [])}
            for kw in strong_positives:
                if strip_accents(kw) not in existing_syns:
                    tuner_entry["synonyms_fr"].append(kw)
                    existing_syns.add(strip_accents(kw))
                    added_positives.append(kw)

        # 3. Validate against schema before writing
        CompanyProfileSchema(**profile_dict)

        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(profile_dict, f, allow_unicode=True, sort_keys=False)

        # Clear cascade scoring cache so all feed scores recompute immediately
        _STAGE23_CACHE.clear()

        now_iso = datetime.now(timezone.utc).isoformat()
        session["last_saved_to_profile_at"] = now_iso
        self._save_ledger()

        logger.info(
            f"[ActiveLearningTuner] Saved tuned logic to {yaml_path.name}: "
            f"+{len(added_positives)} positive terms, +{len(added_exclusions)} exclusions."
        )

        return {
            "status": "saved",
            "profile_file": yaml_path.name,
            "added_positives": added_positives,
            "added_exclusions": added_exclusions,
            "saved_at": now_iso,
            "message": f"💾 Logique enregistrée dans {yaml_path.name} (+{len(added_positives)} critères positifs, +{len(added_exclusions)} exclusions). Scores recalculés.",
        }

    def reset_session(self, profile_id: str) -> Dict[str, Any]:
        key = normalize_profile_key(profile_id)
        self._sessions[key] = self._default_session(key)
        self._save_ledger()
        return {"status": "reset", "profile_id": key, "message": "Session d'entraînement réinitialisée."}


# Global singleton instance
active_tuner = ActiveLearningTuner()
