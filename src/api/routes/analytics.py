import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import get_db_session
from src.engine.competitor_radar import CompetitorRadar
from src.engine.buyer_radar import BuyerRadar
from src.scraper.ao_spider import AoSpider
from src.scraper.client import PortalHttpClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Market Intelligence Radar"])

@router.get("/competitors")
async def get_top_competitors(
    limit: int = Query(15, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="Filter by title keyword"),
    buyer: Optional[str] = Query(None, description="Filter by public buyer or city"),
    year: Optional[int] = Query(None, description="Filter by award year"),
    months: Optional[int] = Query(None, ge=1, le=60, description="Filter by last N months"),
    sort_by: str = Query("amount", description="Sort by: amount, wins, avg_amount, competition"),
    session: AsyncSession = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    Returns top-performing suppliers based on historical award volume,
    total value (MAD TTC), and average pricing density.
    """
    radar = CompetitorRadar(session)
    return await radar.get_top_competitors(
        limit=limit,
        title_keyword=keyword,
        buyer_keyword=buyer,
        year=year,
        months=months,
        sort_by=sort_by,
    )

@router.get("/competitors/{winner_name}")
async def get_competitor_profile(
    winner_name: str,
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Retrieves full intelligence dossier for a specific winning contractor.
    """
    radar = CompetitorRadar(session)
    result = await radar.get_competitor_profile(winner_name)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=f"No award records found for '{winner_name}'")
    return result

@router.get("/buyers")
async def get_buyer_spending_velocity(
    year: Optional[int] = Query(None, description="Fiscal year (defaults to current year)"),
    buyer: Optional[str] = Query(None, description="Filter by buyer name or city"),
    keyword: Optional[str] = Query(None, description="Filter by title keyword"),
    alert: str = Query("all", description="Alert filter: all, ao_imminent, warning, available"),
    limit: int = Query(30, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    Tracks annual BDC spending per public buyer against the 500,000 MAD Article 91
    statutory limit, flagging upcoming formal Marchés Publics (Appels d'Offres).
    """
    radar = BuyerRadar(session)
    return await radar.get_buyer_spending_velocity(
        year=year,
        buyer_keyword=buyer,
        title_keyword=keyword,
        alert_filter=alert,
        limit=limit,
    )

@router.get("/seasonality")
async def get_seasonality_radar(
    session: AsyncSession = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Returns monthly award volume distribution and Q4 budget acceleration metrics.
    """
    radar = BuyerRadar(session)
    return await radar.get_seasonality_radar()

