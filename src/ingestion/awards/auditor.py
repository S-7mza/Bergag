import calendar
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tender import Award

logger = logging.getLogger(__name__)

MONTH_LABELS_FR = {
    1: "Jan", 2: "Fév", 3: "Mar", 4: "Avr", 5: "Mai", 6: "Juin",
    7: "Juil", 8: "Août", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Déc"
}
MONTH_FULL_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}

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

    async def get_monthly_coverage(self, year: Optional[int] = None) -> Dict[str, Any]:
        """
        Returns a 12-month coverage breakdown for the requested year (DB counts,
        date span inside each month, and any available local offline export counts),
        so operators know immediately which months are complete, partial, or missing.
        """
        now = datetime.now(timezone.utc)
        target_year = year or now.year

        # 1. Discover available years in DB (always include current & target year)
        stmt_years = (
            select(extract("year", Award.published_at).label("yr"))
            .where(Award.published_at.isnot(None))
            .distinct()
        )
        yr_rows = (await self.session.execute(stmt_years)).scalars().all()
        years_set = {int(y) for y in yr_rows if y is not None}
        years_set.add(now.year)
        years_set.add(target_year)
        available_years = sorted(years_set, reverse=True)

        # 2. Aggregate awards per month for target_year
        stmt_monthly = (
            select(
                extract("month", Award.published_at).label("mo"),
                func.count(Award.id).label("cnt"),
                func.min(Award.published_at).label("min_dt"),
                func.max(Award.published_at).label("max_dt"),
                func.count(func.distinct(func.date(Award.published_at))).label("active_days"),
                func.sum(Award.amount_ttc).label("sum_mad"),
            )
            .where(
                Award.published_at.isnot(None),
                extract("year", Award.published_at) == target_year,
            )
            .group_by(extract("month", Award.published_at))
        )
        m_rows = (await self.session.execute(stmt_monthly)).all()
        by_month: Dict[int, Any] = {int(r.mo): r for r in m_rows if r.mo is not None}

        # 3. Check local offline export bundles (if present)
        exports_dir = Path("data/offline_exports")
        offline_counts: Dict[int, int] = {}
        if exports_dir.exists():
            for m in range(1, 13):
                exp_file = exports_dir / f"export_awards_{target_year}_{m:02d}.json"
                if exp_file.exists():
                    try:
                        with open(exp_file, "r", encoding="utf-8") as f:
                            bundle = json.load(f)
                        manifest_cnt = bundle.get("manifest", {}).get("item_count")
                        offline_counts[m] = int(manifest_cnt) if manifest_cnt is not None else len(bundle.get("items", []))
                    except Exception:
                        pass

        # 4. Build 12-month coverage cards
        months_data: List[Dict[str, Any]] = []
        missing_months: List[int] = []
        partial_months: List[int] = []
        total_year = 0
        total_mad_year = 0.0
        covered_months_count = 0
        max_month_count = 0

        for m in range(1, 13):
            days_in_month = calendar.monthrange(target_year, m)[1]
            row = by_month.get(m)
            db_count = int(row.cnt) if row else 0
            total_mad = float(row.sum_mad or 0.0) if row else 0.0
            active_days = int(row.active_days or 0) if row else 0
            min_dt = row.min_dt if row else None
            max_dt = row.max_dt if row else None

            total_year += db_count
            total_mad_year += total_mad
            if db_count > max_month_count:
                max_month_count = db_count
            if db_count > 0:
                covered_months_count += 1

            is_future = (target_year, m) > (now.year, now.month)
            is_current_month = (target_year, m) == (now.year, now.month)

            if is_future:
                status = "future"
                status_label = "À venir"
            elif db_count == 0:
                status = "empty"
                status_label = "Manquant"
                missing_months.append(m)
            else:
                min_day = min_dt.day if min_dt else 1
                max_day = max_dt.day if max_dt else days_in_month
                if is_current_month:
                    is_partial = (min_day > 3) or ((now.day - max_day) > 2)
                else:
                    is_partial = (min_day > 3) or (max_day < days_in_month - 3) or (active_days < 5)

                if is_partial:
                    status = "partial"
                    status_label = "Partiel"
                    partial_months.append(m)
                else:
                    status = "complete"
                    status_label = "Complet"

            months_data.append({
                "month": m,
                "label": MONTH_LABELS_FR[m],
                "full_label": MONTH_FULL_FR[m],
                "db_count": db_count,
                "offline_count": offline_counts.get(m, 0),
                "total_mad": round(total_mad, 2),
                "min_date": min_dt.strftime("%Y-%m-%d") if min_dt else None,
                "max_date": max_dt.strftime("%Y-%m-%d") if max_dt else None,
                "min_day_label": min_dt.strftime("%d/%m") if min_dt else None,
                "max_day_label": max_dt.strftime("%d/%m") if max_dt else None,
                "active_days": active_days,
                "days_in_month": days_in_month,
                "status": status,
                "status_label": status_label,
                "date_start_input": f"01/{m:02d}/{target_year}",
                "date_end_input": f"{days_in_month:02d}/{m:02d}/{target_year}",
            })

        return {
            "year": target_year,
            "available_years": available_years,
            "total_awards_year": total_year,
            "total_mad_year": round(total_mad_year, 2),
            "covered_months_count": covered_months_count,
            "missing_months": missing_months,
            "partial_months": partial_months,
            "max_month_count": max_month_count,
            "months": months_data,
        }
