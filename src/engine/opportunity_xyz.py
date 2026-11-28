from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.engine.cps_extractor import CPSFindings


class AttentionDriver(BaseModel):
    axis: str = Field(..., description="X (Technical), Y (Commercial), Z (Win/Risk), or RISK")
    impact: str = Field(..., description="e.g. +25 pts, -15 pts, INFO")
    label: str
    detail: str


class OpportunityXYZResult(BaseModel):
    opportunity_score: float = Field(..., ge=0.0, le=100.0)
    technical_fit_x: float = Field(..., ge=0.0, le=100.0)
    commercial_value_y: float = Field(..., ge=0.0, le=100.0)
    win_probability_z: float = Field(..., ge=0.0, le=100.0)
    priority_tier: str = Field(..., description="P1, P2, P3, ARCHIVE")
    attention_drivers: List[AttentionDriver] = Field(default_factory=list)
    cps_findings: Optional[CPSFindings] = None
    source: str = Field(default="engine", description="'engine' or 'antigravity'")


class OpportunityXYZEngine:
    """
    Explains WHY an offer deserves attention via the 3-axis Bid/No-Bid framework:
      - X (45%): Technical & Scope Fit (pillars, custom vs COTS, hardware dilution, CPS deliverables)
      - Y (30%): Commercial & Budget Potential (Art. 91 headroom, historical award price corridor, AO scale)
      - Z (25%): Win Probability & Execution Risk (deadline buffer, incumbent concentration, CPS hurdles)
    """

    @staticmethod
    def evaluate(
        tender_data: Dict[str, Any],
        technical_fit_x: float,
        hardware_dependency: str = "NONE",
        primary_domain: str = "",
        cps_findings: Optional[CPSFindings] = None,
        buyer_spent_ytd_mad: Optional[float] = None,
        similar_awards_median_mad: Optional[float] = None,
        similar_awards_count: int = 0,
        incumbent_share_pct: Optional[float] = None,
    ) -> OpportunityXYZResult:
        drivers: List[AttentionDriver] = []
        x_score = round(max(0.0, min(100.0, technical_fit_x)), 1)

        # --- Axis X Drivers ---
        if x_score >= 75.0 and hardware_dependency in ("NONE", "LOW"):
            drivers.append(AttentionDriver(
                axis="X",
                impact="+25 pts",
                label="Adéquation Technique Forte",
                detail=f"{primary_domain or 'Périmètre logiciel/web'} aligné à {x_score:.0f}% (dépendance matérielle : {hardware_dependency}).",
            ))
        elif hardware_dependency == "HIGH":
            drivers.append(AttentionDriver(
                axis="RISK",
                impact="-30 pts",
                label="Forte Dominance Matérielle",
                detail="Marché orienté fourniture physique ; marge faible sans partenariat grossiste.",
            ))

        if cps_findings and cps_findings.deliverables:
            drivers.append(AttentionDriver(
                axis="X",
                impact="+10 pts",
                label="Livrables Logiciels Identifiés (CPS)",
                detail=", ".join(cps_findings.deliverables[:4]),
            ))

        # --- Axis Y: Commercial & Budget Potential ---
        y_score = 55.0  # Neutral baseline when historical award context isn't loaded
        source_type = (tender_data.get("source_type") or "bdc").lower()

        if source_type == "marche_public":
            y_score += 20.0
            drivers.append(AttentionDriver(
                axis="Y",
                impact="+20 pts",
                label="Appel d'Offres Formel (AO)",
                detail="Enveloppe budgétaire supérieure au plafond BDC (Art. 91 > 500k MAD).",
            ))

        if similar_awards_median_mad is not None and similar_awards_median_mad > 0:
            if similar_awards_median_mad >= 200000.0:
                y_score += 25.0
                drivers.append(AttentionDriver(
                    axis="Y",
                    impact="+25 pts",
                    label="Forte Valeur Estimée",
                    detail=f"Médiane historique sur avis similaires ({similar_awards_count} cas) : {similar_awards_median_mad:,.0f} MAD TTC.",
                ))
            elif similar_awards_median_mad >= 80000.0:
                y_score += 12.0
                drivers.append(AttentionDriver(
                    axis="Y",
                    impact="+12 pts",
                    label="Enveloppe Commerciale Attractrice",
                    detail=f"Corridor historique estimé : ~{similar_awards_median_mad:,.0f} MAD TTC.",
                ))
            else:
                y_score -= 10.0
                drivers.append(AttentionDriver(
                    axis="Y",
                    impact="-10 pts",
                    label="Petit Ticket Historique",
                    detail=f"Médiane historique modeste ({similar_awards_median_mad:,.0f} MAD TTC).",
                ))

        if buyer_spent_ytd_mad is not None:
            headroom = max(0.0, 500000.0 - buyer_spent_ytd_mad)
            if headroom >= 200000.0:
                y_score += 15.0
                drivers.append(AttentionDriver(
                    axis="Y",
                    impact="+15 pts",
                    label="Marge Art. 91 Confortable",
                    detail=f"L'acheteur dispose encore de {headroom:,.0f} MAD sur son plafond annuel BDC.",
                ))
            elif headroom < 60000.0 and source_type != "marche_public":
                y_score -= 15.0
                drivers.append(AttentionDriver(
                    axis="RISK",
                    impact="-15 pts",
                    label="Plafond Art. 91 Quasi Saturé",
                    detail=f"Seulement {headroom:,.0f} MAD restants avant le seuil d'AO obligatoire.",
                ))

        if cps_findings and any("TMA" in d or "Maintenance" in d for d in cps_findings.deliverables):
            y_score += 10.0
            drivers.append(AttentionDriver(
                axis="Y",
                impact="+10 pts",
                label="Potentiel Récurrent (TMA)",
                detail="Prestation de maintenance applicative / évolutive favorisant la récurrence.",
            ))

        y_score = round(max(0.0, min(100.0, y_score)), 1)

        # --- Axis Z: Win Probability & Execution Risk ---
        z_score = 70.0
        dl_str = tender_data.get("deadline_at")
        if dl_str:
            try:
                dl_dt = datetime.fromisoformat(str(dl_str).replace("Z", "+00:00"))
                if dl_dt.tzinfo is None:
                    dl_dt = dl_dt.replace(tzinfo=timezone.utc)
                hours_left = (dl_dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
                if hours_left <= 0:
                    z_score = 0.0
                elif hours_left < 24.0:
                    z_score -= 35.0
                    drivers.append(AttentionDriver(
                        axis="RISK",
                        impact="-35 pts",
                        label="Délai Critique (< 24h)",
                        detail=f"Plus que {hours_left:.1f}h avant clôture : risque élevé de dossier incomplet.",
                    ))
                elif hours_left >= 120.0:
                    z_score += 15.0
                    drivers.append(AttentionDriver(
                        axis="Z",
                        impact="+15 pts",
                        label="Fenêtre de Préparation Optimale",
                        detail=f"{hours_left / 24.0:.0f} jours disponibles pour chiffrer et soigner le mémoire technique.",
                    ))
            except Exception:
                pass

        if incumbent_share_pct is not None:
            if incumbent_share_pct >= 60.0:
                z_score -= 20.0
                drivers.append(AttentionDriver(
                    axis="RISK",
                    impact="-20 pts",
                    label="Forte Concentration Concurrentielle",
                    detail=f"Un titulaire sortant capte {incumbent_share_pct:.0f}% des marchés similaires de cet acheteur.",
                ))
            elif incumbent_share_pct <= 30.0:
                z_score += 12.0
                drivers.append(AttentionDriver(
                    axis="Z",
                    impact="+12 pts",
                    label="Concurrence Ouverte",
                    detail="Historique d'attribution diversifié sans monopole dominant.",
                ))

        if cps_findings:
            if cps_findings.site_visit_required:
                z_score -= 10.0
                drivers.append(AttentionDriver(
                    axis="RISK",
                    impact="-10 pts",
                    label="Visite des Lieux Obligatoire",
                    detail="Exigence logistique détectée dans le dossier.",
                ))
            if cps_findings.certifications_required:
                z_score -= 5.0
                drivers.append(AttentionDriver(
                    axis="RISK",
                    impact="-5 pts",
                    label="Qualifications / Certifications",
                    detail=", ".join(cps_findings.certifications_required[:3]),
                ))

        z_score = round(max(0.0, min(100.0, z_score)), 1)

        # Composite Opportunity Score
        opp_score = round(max(0.0, min(100.0, (x_score * 0.45) + (y_score * 0.30) + (z_score * 0.25))), 1)

        if opp_score >= 76.0 and x_score >= 65.0 and hardware_dependency in ("NONE", "LOW"):
            tier = "P1"
        elif opp_score >= 55.0 and x_score >= 40.0:
            tier = "P2"
        elif opp_score >= 35.0:
            tier = "P3"
        else:
            tier = "ARCHIVE"

        return OpportunityXYZResult(
            opportunity_score=opp_score,
            technical_fit_x=x_score,
            commercial_value_y=y_score,
            win_probability_z=z_score,
            priority_tier=tier,
            attention_drivers=drivers[:8],
            cps_findings=cps_findings,
            source="engine",
        )


async def fetch_market_context_for_tender(session: Any, tender: Any) -> Dict[str, Any]:
    """
    Safely fetches Buyer YTD Art. 91 spend + historical AwardSimilarityEngine
    corridor & incumbent concentration for a Tender ORM object.
    """
    ctx: Dict[str, Any] = {
        "buyer_spent_ytd_mad": None,
        "similar_awards_median_mad": None,
        "similar_awards_count": 0,
        "incumbent_share_pct": None,
    }
    if not session or not tender:
        return ctx

    try:
        from datetime import datetime
        from sqlalchemy import select, func, extract
        from src.models.tender import Award
        from src.engine.award_similarity import AwardSimilarityEngine

        buyer_name = tender.buyer.official_name if getattr(tender, "buyer", None) else ""
        if buyer_name:
            yr = datetime.now().year
            spend_stmt = (
                select(func.sum(Award.amount_ttc))
                .where(Award.status == "Attribué")
                .where(extract("year", Award.published_at) == yr)
                .where(Award.buyer_name_raw.ilike(f"%{buyer_name[:40]}%"))
            )
            spent_val = await session.scalar(spend_stmt)
            if spent_val is not None:
                ctx["buyer_spent_ytd_mad"] = float(spent_val)

        sim = await AwardSimilarityEngine.find_similar_awards(session, tender, min_similarity=25.0, limit=10)
        est = sim.get("price_estimation") or {}
        if est.get("median_mad"):
            ctx["similar_awards_median_mad"] = float(est["median_mad"])
        matches = sim.get("similar_awards") or []
        ctx["similar_awards_count"] = len(matches)

        competitors = sim.get("top_competitors") or []
        if competitors and len(matches) >= 2:
            top_wins = competitors[0].get("wins", 0)
            ctx["incumbent_share_pct"] = round((top_wins / len(matches)) * 100.0, 1)
    except Exception:
        pass

    return ctx
