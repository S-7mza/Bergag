#!/usr/bin/env python3
"""
Standalone Script: Autonomous AI Avis Diagnostician & DB Matching Updater.
Loops on the procurement notices ('avis après avis') in the database,
inspects the content deeply, computes the special AI Matching Rate locally
(Programming, Web, Data & AI profile) without external APIs, and writes
directly into the PostgreSQL database ('company_profiles' and 'profile_matches')
along with JSON dual-persistence fallback in 'data/ai_diagnoses_ledger.json'.
"""
import sys
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.database.session import async_session_factory
from src.engine.ai_matching_agent import ai_matching_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_matching_runner")

async def main():
    print("=" * 70)
    print("🤖 ANTIGRAVITY AI PROCUREMENT AGENT: AVIS-AFTER-AVIS DB SYNC")
    print("Target Profile: Programming, Web, Data & AI (Decree 2-22-431)")
    print("=" * 70)

    try:
        async with async_session_factory() as session:
            print("\n🔄 Connecting to PostgreSQL database...")
            report = await ai_matching_agent.sync_avis_diagnoses_to_db(
                session=session,
                profile_name="software_data",
                limit=5000,
                force_refresh=True
            )

            print(f"\n✅ Diagnostic & DB Sync Completed Successfully!")
            print(f"   • Total avis scanned & diagnosed: {report['total_scanned']}")
            print(f"   • Database matches created:       {report['matches_created']}")
            print(f"   • Database matches updated:       {report['matches_updated']}")
            print(f"   • Target Company Profile:         {report['profile_name']}")
            print(f"   • Dual-persistence ledger:        data/ai_diagnoses_ledger.json")

            print("\n📊 Rating Distribution:")
            for rating, count in report["rating_distribution"].items():
                print(f"   • {rating:<16}: {count}")

            print("\n🏆 Top Ranked Opportunities for Web, Dev & Data:")
            for idx, opp in enumerate(report["top_opportunities"][:10], start=1):
                techs = ", ".join(opp["detected_technologies"][:3]) or "Général"
                print(f"   {idx:2d}. [Match: {opp['matching_rate']:5.1f}% | {opp['rating_label']:<15}] #{opp['portal_id']} - {opp['title'][:55]}...")
                print(f"       Acheteur: {opp['buyer_name']} | Stack: {techs}")

    except Exception as e:
        print(f"\n⚠️ Database connection deferred or unavailable: {e}")
        print("📁 Operating in Dual-Persistence mode using local ledger (data/ai_diagnoses_ledger.json).")

if __name__ == "__main__":
    asyncio.run(main())
