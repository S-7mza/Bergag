import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, desc, extract
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tender import Award, Buyer, Tender

logger = logging.getLogger(__name__)

LEGAL_BDC_ANNUAL_CEILING_MAD = 500000.0  # Decree 2-22-431 Article 91

class BuyerRadar:
    """
    Monitors public buyer spending velocity, seasonality, and detects
    upcoming large-scale Marchés Publics (Appels d'Offres) when BDC caps are reached.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_buyer_spending_velocity(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Calculates cumulative annual BDC spend per public buyer and flags
        those approaching the 500,000 MAD statutory limit (Article 91).
        """
        target_year = year or datetime.now().year

        stmt = (
            select(
                Award.buyer_name_raw,
                func.count(Award.id).label("bdc_count"),
                func.sum(Award.amount_ttc).label("total_spent_mad"),
                func.avg(Award.amount_ttc).label("avg_bdc_mad")
            )
            .where(Award.status == "Attribué")
            .where(extract("year", Award.published_at) == target_year)
            .group_by(Award.buyer_name_raw)
            .order_by(desc("total_spent_mad"))
            .limit(30)
        )

        res = await self.session.execute(stmt)
        rows = res.all()

        results = []
        for r in rows:
            spent = float(r.total_spent_mad or 0.0)
            exhaustion_pct = min(100.0, (spent / LEGAL_BDC_ANNUAL_CEILING_MAD) * 100.0)
            
            # Predict upcoming formal tender (Marché Public / AO)
            upcoming_ao_signal = False
            signal_rationale = "Spend within regular operational BDC band."
            if spent >= 400000.0:
                upcoming_ao_signal = True
                signal_rationale = (
                    f"CRITICAL: Buyer has consumed {exhaustion_pct:.0f}% ({spent:,.0f} MAD) "
                    f"of the legal 500k MAD BDC limit (Article 91). A formal Marché Public (AO) "
                    f"is required to avoid illegal contract splitting."
                )
            elif spent >= 250000.0:
                signal_rationale = f"Moderate exhaustion ({exhaustion_pct:.0f}%). Approaching annual threshold."

            results.append({
                "buyer_name": r.buyer_name_raw,
                "year": target_year,
                "bdc_count": r.bdc_count,
                "total_spent_mad": spent,
                "avg_bdc_mad": float(r.avg_bdc_mad or 0.0),
                "budget_exhaustion_pct": round(exhaustion_pct, 1),
                "upcoming_ao_signal": upcoming_ao_signal,
                "signal_rationale": signal_rationale
            })

        return results

    async def get_seasonality_radar(self) -> Dict[str, Any]:
        """
        Analyzes historical monthly publication volume to pinpoint Q4 budget rush patterns.
        """
        stmt = (
            select(
                extract("month", Award.published_at).label("month"),
                func.count(Award.id).label("awards_count"),
                func.sum(Award.amount_ttc).label("monthly_mad")
            )
            .where(Award.status == "Attribué")
            .group_by("month")
            .order_by("month")
        )

        res = await self.session.execute(stmt)
        monthly_stats = []
        q4_spend = 0.0
        total_spend = 0.0

        for r in res.all():
            m = int(r.month)
            mad = float(r.monthly_mad or 0.0)
            total_spend += mad
            if m in [10, 11, 12]:
                q4_spend += mad

            monthly_stats.append({
                "month": m,
                "awards_count": r.awards_count,
                "total_mad": mad
            })

        q4_concentration_pct = (q4_spend / total_spend * 100.0) if total_spend > 0 else 0.0

        return {
            "monthly_distribution": monthly_stats,
            "q4_concentration_pct": round(q4_concentration_pct, 1),
            "seasonality_insight": (
                f"Q4 (Oct-Dec) represents {q4_concentration_pct:.1f}% of total annual procurement spend, "
                "confirming that Moroccan administrations accelerate purchasing before fiscal year-end."
            )
        }
