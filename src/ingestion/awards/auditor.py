import logging
from typing import Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tender import Award

logger = logging.getLogger(__name__)

class AwardsAuditor:
    """
    Computes real-time health, depth, and data-integrity metrics
    for the Moroccan public procurement awards repository.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_stats(self) -> Dict[str, Any]:
        """
        Gathers comprehensive statistics on the 'awards' table.
        """
        # Overall counts
        stmt_total = select(func.count(Award.id))
        total_res = await self.session.execute(stmt_total)
        total_count = total_res.scalar() or 0

        if total_count == 0:
            return {
                "total_awards": 0,
                "total_awarded": 0,
                "total_infructueux": 0,
                "total_awarded_mad": 0.0,
                "avg_contract_mad": 0.0,
                "avg_competition_density": 0.0,
                "linked_tenders_count": 0,
                "linkage_rate_pct": 0.0,
                "unique_winners_count": 0,
                "unique_buyers_count": 0,
                "latest_award_date": None,
                "is_fallback_active": True,
                "status_label": "Mode Simulation (Base vide)",
                "status_badge_class": "bg-amber-500/10 text-amber-400 border border-amber-500/30"
            }

        # Status breakdowns & sums
        stmt_breakdown = (
            select(
                Award.status,
                func.count(Award.id).label("count"),
                func.sum(Award.amount_ttc).label("sum_amount"),
                func.avg(Award.amount_ttc).label("avg_amount"),
                func.avg(Award.devis_received_count).label("avg_devis")
            )
            .group_by(Award.status)
        )
        b_res = await self.session.execute(stmt_breakdown)
        b_rows = b_res.all()

        total_awarded = 0
        total_infructueux = 0
        total_awarded_mad = 0.0
        avg_contract_mad = 0.0
        avg_density = 0.0

        for r in b_rows:
            if r.status == "Attribué":
                total_awarded = r.count
                total_awarded_mad = float(r.sum_amount or 0.0)
                avg_contract_mad = float(r.avg_amount or 0.0)
                avg_density = float(r.avg_devis or 0.0)
            elif r.status == "Infructueux":
                total_infructueux = r.count

        # Linked consultations count
        stmt_linked = select(func.count(Award.id)).where(Award.tender_id.isnot(None))
        linked_res = await self.session.execute(stmt_linked)
        linked_count = linked_res.scalar() or 0
        linkage_rate = round((linked_count / total_count * 100.0), 1) if total_count > 0 else 0.0

        # Unique winners and buyers
        stmt_winners = select(func.count(func.distinct(Award.winner_name))).where(
            (Award.winner_name != "") & (Award.winner_name != "—")
        )
        winners_count = (await self.session.execute(stmt_winners)).scalar() or 0

        stmt_buyers = select(func.count(func.distinct(Award.buyer_name_raw)))
        buyers_count = (await self.session.execute(stmt_buyers)).scalar() or 0

        # Latest publication date
        stmt_latest = select(func.max(Award.published_at))
        latest_date = (await self.session.execute(stmt_latest)).scalar()
        latest_str = latest_date.strftime("%d/%m/%Y %H:%M") if latest_date else None

        return {
            "total_awards": total_count,
            "total_awarded": total_awarded,
            "total_infructueux": total_infructueux,
            "total_awarded_mad": round(total_awarded_mad, 2),
            "avg_contract_mad": round(avg_contract_mad, 2),
            "avg_competition_density": round(avg_density, 1),
            "linked_tenders_count": linked_count,
            "linkage_rate_pct": linkage_rate,
            "unique_winners_count": winners_count,
            "unique_buyers_count": buyers_count,
            "latest_award_date": latest_str,
            "is_fallback_active": False,
            "status_label": "Données Réelles en direct",
            "status_badge_class": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
        }
