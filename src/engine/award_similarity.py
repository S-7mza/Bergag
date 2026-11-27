import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tender import Award, Tender

_FRENCH_PROCUREMENT_STOPWORDS: Set[str] = {
    "achat", "fourniture", "fournitures", "acquisition", "mise", "place",
    "profit", "travaux", "prestation", "prestations", "service", "services",
    "relatif", "relative", "relatifs", "relatives", "concernant", "cadre",
    "direction", "provinciale", "regionale", "region", "province", "commune",
    "ministere", "academie", "delegation", "etablissement", "centre", "siege",
    "exercice", "annee", "lot", "unique", "divers", "diverses", "autre",
    "autres", "pour", "dans", "avec", "sans", "sous", "entre", "vers",
    "chez", "sur", "par", "des", "les", "une", "aux", "est", "sont",
    "qui", "que", "dont", "maroc", "marche", "bdc", "bon", "commande",
    "consultation", "avis", "objet", "etc", "suite", "titre", "annuel",
    "annuelle", "besoins", "realisation", "execution", "equipement",
    "equipements", "materiel", "materiels",
}


def normalize_text(text: str) -> str:
    """Lowercase, strip accents, and normalize punctuation to spaces."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_str.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_meaningful_tokens(text: str, extra_texts: Optional[List[str]] = None) -> List[str]:
    """Extract ordered unique domain tokens, filtering French procurement boilerplate."""
    combined = normalize_text(text)
    if extra_texts:
        combined = f"{combined} " + " ".join(normalize_text(t) for t in extra_texts if t)
    seen: Set[str] = set()
    tokens: List[str] = []
    for tok in combined.split():
        if len(tok) < 3 or tok.isdigit() or tok in _FRENCH_PROCUREMENT_STOPWORDS:
            continue
        if tok not in seen:
            seen.add(tok)
            tokens.append(tok)
    return tokens


def extract_bigrams(tokens: List[str]) -> Set[str]:
    """Build adjacent token bigrams for phrase-level similarity."""
    if len(tokens) < 2:
        return set()
    return {f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)}


def _percentile(sorted_vals: List[float], pct: float) -> float:
    """Compute linear-interpolated percentile from a sorted non-empty list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


class AwardSimilarityEngine:
    """
    Measures similarity between a consultation (active or closed) and historical
    awarded notices (`awards` table) to derive:
      1. Statistical & similarity-weighted price estimation corridor (MAD TTC)
      2. Recurring winning competitors on similar notices
      3. Ranked comparable awards with similarity breakdown
    """

    @staticmethod
    def score_award_similarity(
        tender_tokens: List[str],
        tender_bigrams: Set[str],
        tender_buyer_norm: str,
        award_title: str,
        award_buyer: str,
        published_at: Optional[datetime],
        now: Optional[datetime] = None,
    ) -> Tuple[float, bool, List[str]]:
        """
        Compute similarity percentage (0..100), same-buyer flag, and matched terms.
        Weights:
          - Weighted Dice/Jaccard token overlap: up to 68 pts
          - Bigram phrase overlap: up to 16 pts
          - Same public buyer overlap: up to 10 pts
          - Recency (<= 24 months): up to 6 pts
        """
        award_tokens = extract_meaningful_tokens(award_title)
        if not tender_tokens or not award_tokens:
            return 0.0, False, []

        tender_set = set(tender_tokens)
        award_set = set(award_tokens)
        matched = [t for t in tender_tokens if t in award_set]
        if not matched:
            return 0.0, False, []

        # Specificity weight: longer technical words carry slightly more signal
        def _tok_weight(tok: str) -> float:
            return 1.35 if len(tok) >= 7 else 1.0

        matched_w = sum(_tok_weight(t) for t in matched)
        tender_w = sum(_tok_weight(t) for t in tender_set)
        award_w = sum(_tok_weight(t) for t in award_set)
        dice_score = (2.0 * matched_w) / max(tender_w + award_w, 1e-6)
        lexical_pts = min(68.0, dice_score * 78.0)

        # Bigram phrase bonus
        award_bigrams = extract_bigrams(award_tokens)
        bigram_pts = 0.0
        if tender_bigrams and award_bigrams:
            shared_bigrams = tender_bigrams & award_bigrams
            if shared_bigrams:
                bigram_pts = min(16.0, len(shared_bigrams) * 8.0)

        # Same public buyer bonus
        same_buyer = False
        buyer_pts = 0.0
        award_buyer_norm = normalize_text(award_buyer)
        if tender_buyer_norm and award_buyer_norm:
            if tender_buyer_norm == award_buyer_norm or (
                len(tender_buyer_norm) >= 8
                and (tender_buyer_norm in award_buyer_norm or award_buyer_norm in tender_buyer_norm)
            ):
                same_buyer = True
                buyer_pts = 10.0
            else:
                b_toks_a = {t for t in tender_buyer_norm.split() if len(t) >= 4}
                b_toks_b = {t for t in award_buyer_norm.split() if len(t) >= 4}
                if len(b_toks_a & b_toks_b) >= 2:
                    same_buyer = True
                    buyer_pts = 7.0

        # Recency bonus
        recency_pts = 3.0
        if published_at is not None:
            ref_now = now or datetime.now(timezone.utc)
            pub = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (ref_now - pub).total_seconds() / 86400.0)
            if age_days <= 180:
                recency_pts = 6.0
            elif age_days <= 365:
                recency_pts = 5.0
            elif age_days <= 730:
                recency_pts = 3.5
            else:
                recency_pts = 1.5

        total_score = round(min(100.0, lexical_pts + bigram_pts + buyer_pts + recency_pts), 1)
        return total_score, same_buyer, matched[:6]

    @classmethod
    def analyze_candidates(
        cls,
        tender_title: str,
        buyer_name: str,
        line_item_titles: List[str],
        candidates: List[Award],
        min_similarity: float = 20.0,
        limit: int = 12,
    ) -> Dict[str, Any]:
        """Pure in-memory similarity scoring, price corridor & competitor aggregation."""
        tender_tokens = extract_meaningful_tokens(tender_title, extra_texts=line_item_titles[:8])
        tender_bigrams = extract_bigrams(extract_meaningful_tokens(tender_title))
        tender_buyer_norm = normalize_text(buyer_name)
        now = datetime.now(timezone.utc)

        scored: List[Dict[str, Any]] = []
        for award in candidates:
            sim_pct, same_buyer, matched_terms = cls.score_award_similarity(
                tender_tokens=tender_tokens,
                tender_bigrams=tender_bigrams,
                tender_buyer_norm=tender_buyer_norm,
                award_title=award.title_raw or "",
                award_buyer=award.buyer_name_raw or "",
                published_at=award.published_at,
                now=now,
            )
            if sim_pct < min_similarity:
                continue

            amount = float(award.amount_ttc or 0.0)
            scored.append({
                "award_id": str(award.id),
                "reference": award.reference,
                "title": award.title_raw,
                "buyer_name": award.buyer_name_raw,
                "winner_name": award.winner_name,
                "amount_ttc": round(amount, 2),
                "devis_received_count": award.devis_received_count,
                "status": award.status,
                "published_at": award.published_at.strftime("%d/%m/%Y") if award.published_at else "—",
                "published_iso": award.published_at.isoformat() if award.published_at else None,
                "similarity_pct": sim_pct,
                "same_buyer": same_buyer,
                "matched_terms": matched_terms,
            })

        scored.sort(key=lambda x: (x["similarity_pct"], x["published_iso"] or ""), reverse=True)

        # Price estimation over Attribué awards with positive amount
        priced = [s for s in scored if s["amount_ttc"] > 0 and s["status"] == "Attribué"]
        amounts_sorted = sorted(s["amount_ttc"] for s in priced)

        if priced:
            weight_sum = sum(s["similarity_pct"] for s in priced) or 1.0
            weighted_avg = sum(s["amount_ttc"] * s["similarity_pct"] for s in priced) / weight_sum
            devis_vals = [s["devis_received_count"] for s in priced if s["devis_received_count"] and s["devis_received_count"] > 0]
            avg_devis = round(sum(devis_vals) / len(devis_vals), 1) if devis_vals else None

            if avg_devis is None:
                comp_level = "Inconnue"
            elif avg_devis <= 2.2:
                comp_level = "Faible"
            elif avg_devis <= 4.5:
                comp_level = "Modérée"
            else:
                comp_level = "Forte"

            top_sim = priced[0]["similarity_pct"]
            if len(priced) >= 6 and top_sim >= 55.0:
                confidence = "Élevée"
            elif len(priced) >= 3 and top_sim >= 35.0:
                confidence = "Moyenne"
            else:
                confidence = "Faible"

            price_estimation = {
                "sample_size": len(priced),
                "confidence": confidence,
                "min_mad": round(amounts_sorted[0], 2),
                "p25_mad": round(_percentile(amounts_sorted, 25), 2),
                "median_mad": round(_percentile(amounts_sorted, 50), 2),
                "weighted_avg_mad": round(weighted_avg, 2),
                "p75_mad": round(_percentile(amounts_sorted, 75), 2),
                "max_mad": round(amounts_sorted[-1], 2),
                "avg_devis_count": avg_devis,
                "competition_level": comp_level,
            }
        else:
            price_estimation = {
                "sample_size": 0,
                "confidence": "Aucune",
                "min_mad": 0.0,
                "p25_mad": 0.0,
                "median_mad": 0.0,
                "weighted_avg_mad": 0.0,
                "p75_mad": 0.0,
                "max_mad": 0.0,
                "avg_devis_count": None,
                "competition_level": "Inconnue",
            }

        # Competitor aggregation across similar awarded notices
        comp_map: Dict[str, Dict[str, Any]] = {}
        for s in priced:
            winner = (s["winner_name"] or "").strip()
            if not winner or winner in {"—", "-", "N/A"}:
                continue
            entry = comp_map.setdefault(winner, {
                "winner_name": winner,
                "wins_count": 0,
                "same_buyer_wins": 0,
                "amounts": [],
                "max_similarity_pct": 0.0,
                "devis_counts": [],
            })
            entry["wins_count"] += 1
            if s["same_buyer"]:
                entry["same_buyer_wins"] += 1
            entry["amounts"].append(s["amount_ttc"])
            if s["similarity_pct"] > entry["max_similarity_pct"]:
                entry["max_similarity_pct"] = s["similarity_pct"]
            if s["devis_received_count"]:
                entry["devis_counts"].append(s["devis_received_count"])

        top_competitors: List[Dict[str, Any]] = []
        for entry in comp_map.values():
            amts = entry["amounts"]
            d_cnts = entry["devis_counts"]
            top_competitors.append({
                "winner_name": entry["winner_name"],
                "wins_count": entry["wins_count"],
                "same_buyer_wins": entry["same_buyer_wins"],
                "avg_amount_mad": round(sum(amts) / len(amts), 2),
                "min_amount_mad": round(min(amts), 2),
                "max_amount_mad": round(max(amts), 2),
                "max_similarity_pct": entry["max_similarity_pct"],
                "avg_devis_count": round(sum(d_cnts) / len(d_cnts), 1) if d_cnts else None,
            })

        top_competitors.sort(
            key=lambda c: (c["wins_count"], c["same_buyer_wins"], c["max_similarity_pct"]),
            reverse=True,
        )

        return {
            "keywords_used": tender_tokens[:6],
            "total_matched": len(scored),
            "price_estimation": price_estimation,
            "top_competitors": top_competitors[:8],
            "similar_awards": scored[:limit],
        }

    @classmethod
    async def find_similar_awards(
        cls,
        session: AsyncSession,
        tender: Tender,
        min_similarity: float = 20.0,
        limit: int = 12,
        candidate_pool_limit: int = 180,
    ) -> Dict[str, Any]:
        """Query candidate historical awards from DB and score similarity for a tender."""
        line_titles = [li.designation for li in (tender.line_items or []) if getattr(li, "designation", None)]
        buyer_name = tender.buyer.official_name if tender.buyer else ""
        tokens = extract_meaningful_tokens(tender.title or "", extra_texts=line_titles[:6])

        # Prioritize longer / more specific keywords for DB candidate retrieval
        search_keywords = sorted(tokens, key=len, reverse=True)[:5]
        if not search_keywords:
            return {
                "portal_id": tender.portal_id,
                "tender_title": tender.title,
                **cls.analyze_candidates(
                    tender_title=tender.title or "",
                    buyer_name=buyer_name,
                    line_item_titles=line_titles,
                    candidates=[],
                    min_similarity=min_similarity,
                    limit=limit,
                ),
            }

        filters = [Award.title_raw.ilike(f"%{kw}%") for kw in search_keywords]
        stmt = (
            select(Award)
            .where(Award.status == "Attribué")
            .where(Award.amount_ttc > 0)
            .where(or_(*filters))
            .order_by(desc(Award.published_at))
            .limit(candidate_pool_limit)
        )
        res = await session.execute(stmt)
        candidates = list(res.scalars().all())

        analysis = cls.analyze_candidates(
            tender_title=tender.title or "",
            buyer_name=buyer_name,
            line_item_titles=line_titles,
            candidates=candidates,
            min_similarity=min_similarity,
            limit=limit,
        )
        return {
            "portal_id": tender.portal_id,
            "tender_title": tender.title,
            **analysis,
        }
