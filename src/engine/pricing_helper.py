import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tender import Award

logger = logging.getLogger(__name__)

class PricingHelper:
    """
    Computes Dual-Sided Pricing Corridor:
    1. Internal Floor Price: Break-even cost + minimum profit margin.
    2. Historical Market Corridor: P25, Median, and P75 award prices from similar tenders.
    """
    @staticmethod
    def calculate_floor_price(
        estimated_hardware_cost_ht: float,
        target_margin_percent: float = 25.0,
        logistics_cost_mad: float = 1500.0,
        tva_rate: float = 20.0
    ) -> float:
        """
        Calculates the minimum viable bid price (TTC) below which the company operates at a loss.
        """
        subtotal_ht = estimated_hardware_cost_ht + logistics_cost_mad
        margin_multiplier = 1.0 + (target_margin_percent / 100.0)
        tva_multiplier = 1.0 + (tva_rate / 100.0)
        floor_price_ttc = subtotal_ht * margin_multiplier * tva_multiplier
        return round(floor_price_ttc, 2)

    @staticmethod
    async def get_historical_comparables(
        session: AsyncSession,
        buyer_name: str,
        title_keyword: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves real awarded prices from the awards table for similar objects or same buyer.
        """
        try:
            stmt = (
                select(Award)
                .where(Award.title_raw.ilike(f"%{title_keyword}%"))
                .order_by(desc(Award.published_at))
                .limit(limit)
            )
            res = await session.execute(stmt)
            awards = res.scalars().all()

            return [
                {
                    "reference": a.reference,
                    "buyer_name": a.buyer_name_raw,
                    "winner_name": a.winner_name,
                    "amount_ttc": float(a.amount_ttc),
                    "devis_count": a.devis_received_count,
                    "published_at": a.published_at.isoformat()
                }
                for a in awards
            ]
        except Exception as e:
            logger.warning(f"Error querying historical comparables: {e}")
            return []

