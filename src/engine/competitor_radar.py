import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tender import Award

logger = logging.getLogger(__name__)

class CompetitorRadar:
    """
    Analyzes the historical awards archive (~340,000 records) to extract
    strategic competitor intelligence: top winners, win rates, and price aggressiveness.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_top_competitors(self, limit: int = 15, title_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Calculates the top winning suppliers by total volume and total contract value (MAD TTC).
        """
        stmt = (
            select(
                Award.winner_name,
                func.count(Award.id).label("total_wins"),
                func.sum(Award.amount_ttc).label("total_awarded_mad"),
                func.avg(Award.amount_ttc).label("avg_contract_mad"),
                func.avg(Award.devis_received_count).label("avg_competition_density")
            )
            .where(Award.status == "Attribué")
            .where(Award.winner_name != "")
            .where(Award.winner_name != "—")
        )

        if title_keyword:
            stmt = stmt.where(Award.title_raw.ilike(f"%{title_keyword}%"))

        stmt = (
            stmt.group_by(Award.winner_name)
            .order_by(desc("total_awarded_mad"))
            .limit(limit)
        )

        res = await self.session.execute(stmt)
        rows = res.all()

        return [
            {
                "winner_name": r.winner_name,
                "total_wins": r.total_wins,
                "total_awarded_mad": float(r.total_awarded_mad or 0.0),
                "avg_contract_mad": float(r.avg_contract_mad or 0.0),
                "avg_competition_density": round(float(r.avg_competition_density or 0.0), 1)
            }
            for r in rows
        ]

    async def get_competitor_profile(self, winner_name: str) -> Dict[str, Any]:
        """
        Generates a 360-degree intelligence dossier for a specific competitor.
        """
        stmt = (
            select(Award)
            .where(Award.winner_name.ilike(winner_name.strip()))
            .order_by(desc(Award.published_at))
            .limit(50)
        )
        res = await self.session.execute(stmt)
        awards = res.scalars().all()

        if not awards:
            return {"winner_name": winner_name, "found": False, "awards": []}

        total_mad = sum(a.amount_ttc for a in awards)
        buyers_set = {a.buyer_name_raw for a in awards}

        return {
            "winner_name": winner_name,
            "found": True,
            "total_recorded_wins": len(awards),
            "total_awarded_mad": float(total_mad),
            "avg_amount_mad": float(total_mad / len(awards)) if awards else 0.0,
            "unique_buyers_count": len(buyers_set),
            "top_client_buyers": list(buyers_set)[:5],
            "recent_wins": [
                {
                    "reference": a.reference,
                    "title": a.title_raw,
                    "buyer": a.buyer_name_raw,
                    "amount_ttc": float(a.amount_ttc),
                    "awarded_at": a.published_at.strftime("%d/%m/%Y")
                }
                for a in awards[:10]
            ]
        }
