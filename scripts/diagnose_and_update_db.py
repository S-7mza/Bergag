#!/usr/bin/env python3
"""
Standalone Script: Autonomous AI Avis Diagnostician & DB Matching Updater.
Loops on the procurement notices ('avis après avis'), inspects the content deeply,
computes the special AI Matching Rate locally without external APIs, and writes
directly into the PostgreSQL database ('company_profiles' and 'profile_matches')
along with JSON dual-persistence fallback in 'data/ai_diagnoses_ledger.json'.
"""
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.engine.ai_diagnostician import AIAvisDiagnostician, AIMatchingDiagnosis
from src.engine.ai_matching_agent import ai_matching_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_matching_runner")

async def run_db_sync() -> bool:
    """Attempts direct PostgreSQL sync if database is reachable"""
    from src.database.session import async_session_factory
    try:
        async with async_session_factory() as session:
            print("🔄 Connected to PostgreSQL database. Running DB matching sync...")
            report = await ai_matching_agent.sync_avis_diagnoses_to_db(
                session=session,
                profile_name="software_data",
                limit=5000,
                force_refresh=True
            )
            print(f"✅ DB Sync Complete: {report['total_scanned']} avis updated in PostgreSQL.")
            return True
    except Exception as e:
        print(f"ℹ️ PostgreSQL direct connection unavailable ({e}).")
        return False

def run_offline_notices_diagnosis():
    """
    Diagnoses all available exported notices notice-after-notice ('avis après avis'),
    validates technical compatibility against the Programming, Web, Data & AI profile,
    and updates the persistent ledger.
    """
    export_files = [
        Path("data/offline_exports/export_bdc_all_old_to_new_20261121_233139.json"),
        Path("data/offline_exports/export_bdc_20261121_231237.json"),
    ]

    notices: List[Dict[str, Any]] = []
    seen_ids = set()

    for ef in export_files:
        if ef.exists():
            try:
                with open(ef, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    items = content.get("items", []) if isinstance(content, dict) else content
                    for it in items:
                        pid = it.get("portal_id")
                        if pid and pid not in seen_ids:
                            seen_ids.add(pid)
                            notices.append(it)
            except Exception as e:
                logger.warning(f"Could not read {ef}: {e}")

    if not notices:
        print("⚠️ No offline notices found to process.")
        return

    print(f"\n🚀 Starting Deep AI Diagnostic Loop across {len(notices)} notices notice-after-notice...")
    print("   Profile: Programming, Web, Data & AI Solutions (Decree 2-22-431)")
    print("-" * 70)

    rating_counts = {
        "EXCELLENT_MATCH": 0,
        "STRONG_MATCH": 0,
        "MODERATE_MATCH": 0,
        "LOW_MATCH": 0,
        "MISMATCH": 0
    }
    top_matches: List[Dict[str, Any]] = []
    tech_frequency: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}

    for idx, notice in enumerate(notices, start=1):
        portal_id = notice.get("portal_id")
        diag = AIAvisDiagnostician.diagnose_tender(notice)

        # Record in agent's cache and persistent store
        ai_matching_agent._diagnoses_cache[portal_id] = diag.model_dump()

        rating_counts[diag.rating_label] = rating_counts.get(diag.rating_label, 0) + 1
        domain_counts[diag.primary_domain] = domain_counts.get(diag.primary_domain, 0) + 1

        for tech in diag.detected_technologies:
            tech_frequency[tech] = tech_frequency.get(tech, 0) + 1

        if diag.matching_rate >= 40.0:
            top_matches.append({
                "portal_id": portal_id,
                "reference": notice.get("reference", "N/A"),
                "title": notice.get("title", ""),
                "buyer_name": notice.get("buyer_name", "Inconnu"),
                "matching_rate": diag.matching_rate,
                "rating_label": diag.rating_label,
                "verdict": diag.verdict,
                "primary_domain": diag.primary_domain,
                "detected_technologies": diag.detected_technologies,
                "recommendation": diag.strategic_recommendation
            })

        if idx % 250 == 0 or idx == len(notices):
            print(f"   ⏳ Diagnosed {idx}/{len(notices)} avis ({(idx/len(notices)*100):.1f}%)...")

    # Persist all diagnoses atomically
    ai_matching_agent._persist_ledger()

    top_matches.sort(key=lambda x: x["matching_rate"], reverse=True)

    print("\n" + "=" * 70)
    print("📊 AI DIAGNOSTIC REPORT: PROGRAMMING, WEB, DATA & AI PROFILE")
    print("=" * 70)
    print(f"Total Notices Inspected: {len(notices):,}")
    print(f"Dual-Persistence Ledger: data/ai_diagnoses_ledger.json ({len(ai_matching_agent._diagnoses_cache):,} cached)")

    print("\n📈 Rating Distribution:")
    for label, count in rating_counts.items():
        pct = (count / len(notices)) * 100
        bar = "█" * int(pct / 2)
        print(f"   {label:<16}: {count:5d} ({pct:5.1f}%) {bar}")

    print("\n🏢 Top Domains Detected:")
    for dom, cnt in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:6]:
        print(f"   • {dom:<38}: {cnt:4d} avis")

    print("\n🛠️ In-Demand Technologies in Moroccan Public Procurement:")
    for tech, cnt in sorted(tech_frequency.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   • {tech:<25}: {cnt:4d} avis")

    print("\n🏆 Top Identified Matching Opportunities (Web, Software & Data):")
    for i, opp in enumerate(top_matches[:12], start=1):
        stack_str = ", ".join(opp["detected_technologies"][:4]) or "Général"
        print(f"\n   #{i:02d} [{opp['matching_rate']:5.1f}% | {opp['rating_label']}] Portal ID: {opp['portal_id']} (Réf: {opp['reference']})")
        print(f"       Objet:   {opp['title'][:75]}")
        print(f"       Client:  {opp['buyer_name']}")
        print(f"       Domaine: {opp['primary_domain']} | Stack: {stack_str}")
        print(f"       Conseil: {opp['recommendation']}")

async def main():
    print("=" * 70)
    print("🤖 AUTONOMOUS AI AVIS DIAGNOSTIC & MATCHING ENGINE")
    print("Local, High-Precision Inspection (No External API Required)")
    print("=" * 70)

    # 1. Attempt database sync
    synced_db = await run_db_sync()

    # 2. Loop across notices
    run_offline_notices_diagnosis()

if __name__ == "__main__":
    asyncio.run(main())
