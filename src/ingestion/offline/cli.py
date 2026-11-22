import asyncio
import argparse
import sys
from pathlib import Path
from src.ingestion.offline.exporter import OfflineExporter
from src.ingestion.offline.importer import OfflineImporter

async def run_cli():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Moroccan Public Procurement - Offline Data Collection & Synchronization CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to execute")

    # 1. Export Command (Local Collector without DB)
    export_parser = subparsers.add_parser("export", help="Collect data locally from portal and save offline JSON bundle")
    export_parser.add_argument("--awards", action="store_true", help="Collect historical awards & results")
    export_parser.add_argument("--bdc", action="store_true", help="Collect active BDC notices with line items")
    export_parser.add_argument("--all", action="store_true", help="Collect ALL active pages available on the portal")
    export_parser.add_argument("--by-month", action="store_true", help="Collect awards in structured month-by-month bulks")
    export_parser.add_argument("--year", type=int, default=None, help="Year for month-by-month collection (e.g. 2026)")
    export_parser.add_argument("--months", type=int, default=None, help="Number of rolling past months to collect (e.g. 3, 6, 12)")
    export_parser.add_argument("--order", choices=["asc", "desc"], default="desc", help="Sort order: 'asc' (oldest to newest) or 'desc' (newest to oldest)")
    export_parser.add_argument("--pages", type=int, default=5, help="Number of pages to collect (default: 5)")
    export_parser.add_argument("--page-size", type=int, default=50, help="Items per request (default: 50)")
    export_parser.add_argument("--date-start", type=str, default=None, help="Start date (DD/MM/YYYY)")
    export_parser.add_argument("--date-end", type=str, default=None, help="End date (DD/MM/YYYY)")
    export_parser.add_argument("--keyword", type=str, default=None, help="Filter keyword")
    export_parser.add_argument("--no-resume", action="store_true", help="Start a new collection without resuming checkpoint")
    export_parser.add_argument("--output", type=str, default=None, help="Output JSON path")

    # 2. Status Command
    status_parser = subparsers.add_parser("status", help="Show active checkpoint and progress of interrupted collections")

    # 3. Resume Command
    resume_parser = subparsers.add_parser("resume", help="Resume interrupted data collection")
    resume_parser.add_argument("--domain", choices=["bdc", "awards"], default="bdc", help="Domain to resume (default: bdc)")

    # 4. Import Command (Server-side Database Sync)
    import_parser = subparsers.add_parser("import", help="Import an offline JSON bundle into PostgreSQL database")
    import_parser.add_argument("file", type=str, help="Path to export bundle JSON file")

    args = parser.parse_args()

    if args.command == "status":
        print("======================================================================")
        print("  ÉTAT DES COLLECTES EN COURS (CHECKPOINTS HORS-LIGNE)")
        print("======================================================================\n")
        exporter = OfflineExporter()
        for dom in ["bdc", "awards"]:
            cp = exporter.get_checkpoint(dom)
            if cp:
                print(f"[*] Domaine : {dom.upper()}")
                print(f"    - Fichier cible      : {cp.get('output_file')}")
                print(f"    - Éléments collectés : {cp.get('items_count', 0)}")
                print(f"    - Pages terminées    : {len(cp.get('completed_pages', []))} / {len(cp.get('target_pages', []))}")
                print(f"    - Dernière page      : {cp.get('last_completed_page')}")
                print(f"    - Ordre              : {cp.get('order', 'desc')}")
                print(f"    - Statut             : {cp.get('status')}")
                print(f"    - Mise à jour        : {cp.get('last_updated_at')}\n")
            else:
                print(f"[-] Domaine {dom.upper()} : Aucune collecte interrompue.\n")

    elif args.command == "resume":
        exporter = OfflineExporter()
        cp = exporter.get_checkpoint(args.domain)
        if not cp:
            print(f"[!] Aucun checkpoint trouvé pour le domaine '{args.domain}'.")
            sys.exit(0)
        print(f"[*] Reprise de la collecte {args.domain.upper()}...")
        print(f"    - Fichier   : {cp.get('output_file')}")
        print(f"    - Déjà fait : {len(cp.get('completed_pages', []))} / {len(cp.get('target_pages', []))} pages ({cp.get('items_count')} avis)")
        
        def cli_progress(p):
            print(f"  -> Page {p.get('current_page')} | Total avis collectés : {p.get('items_collected')}")

        if args.domain == "bdc":
            res = await exporter.collect_bdc(
                max_pages=None,
                resume=True,
                order=cp.get("order", "desc"),
                output_path=cp.get("output_file"),
                progress_callback=cli_progress
            )
            print(f"\n[✓] Collecte BDC terminée avec succès : {res['item_count']} avis enregistrés.")
        else:
            res = await exporter.collect_awards(
                resume=True,
                output_path=cp.get("output_file")
            )
            print(f"\n[✓] Collecte Attributions terminée avec succès : {res['item_count']} avis enregistrés.")

    elif args.command == "export":
        exporter = OfflineExporter()
        if args.awards:
            if args.by_month or args.year or args.months:
                from datetime import datetime
                if args.months:
                    print(f"[*] Collecte des attributions par lots mensuels (Derniers {args.months} mois)...")
                    month_results = await exporter.collect_awards_recent_months(
                        n_months=args.months,
                        max_pages_per_month=None if args.all else args.pages,
                        page_size=args.page_size,
                        keyword=args.keyword
                    )
                else:
                    target_year = args.year or datetime.now().year
                    print(f"[*] Collecte des attributions par lots mensuels pour l'année {target_year}...")
                    month_results = await exporter.collect_awards_by_months(
                        year=target_year,
                        max_pages_per_month=None if args.all else args.pages,
                        page_size=args.page_size,
                        keyword=args.keyword
                    )
                print(f"\n[✓] Collecte mensuelle terminée : {len(month_results)} fichiers JSON générés dans data/offline_exports/")
                total_items = sum(m.get("item_count", 0) for m in month_results)
                print(f"    - Total attributions collectées : {total_items}")
            else:
                pages = None if args.all else args.pages
                pages_label = "TOUT l'historique disponible" if args.all else f"{args.pages} pages"
                print(f"[*] Collecte des attributions ({pages_label})...")
                res = await exporter.collect_awards(
                    max_pages=pages,
                    page_size=args.page_size,
                    date_start=args.date_start,
                    date_end=args.date_end,
                    keyword=args.keyword,
                    output_path=args.output,
                    resume=not args.no_resume
                )
                print(f"[✓] Export attributions généré : {res['output_file']}")
                print(f"    - Éléments collectés : {res['item_count']}")
                print(f"    - Total portail      : {res['portal_total_archive']}")
                print(f"    - SHA256             : {res['sha256_checksum']}")

        elif args.bdc:
            pages = None if args.all else args.pages
            order_label = "du plus ancien au plus récent" if args.order == "asc" else "du plus récent au plus ancien"
            pages_label = "TOUS les avis actifs" if args.all else f"{args.pages} pages"
            print(f"[*] Collecte des BDC actifs ({pages_label}, tri: {order_label})...")
            
            def bdc_cli_cb(p):
                print(f"  [+] Page {p.get('current_page')}/{p.get('total_pages')} | {p.get('items_collected')} avis enregistrés", end="\r")

            res = await exporter.collect_bdc(
                max_pages=pages,
                page_size=args.page_size,
                order=args.order,
                resume=not args.no_resume,
                output_path=args.output,
                progress_callback=bdc_cli_cb
            )
            print(f"\n[✓] Export BDC généré : {res['output_file']}")
            print(f"    - Éléments enregistrés : {res['item_count']}")
            print(f"    - Total actif portail  : {res['total_active_archive']}")
            print(f"    - SHA256               : {res['sha256_checksum']}")
        else:
            print("[!] Veuillez spécifier --awards ou --bdc.")
            sys.exit(1)

    elif args.command == "import":
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"[!] Fichier introuvable : {file_path}")
            sys.exit(1)

        print(f"[*] Importation du bundle '{file_path}' dans PostgreSQL...")
        importer = OfflineImporter()
        res = await importer.import_bundle(file_path)
        print(f"[✓] Importation terminée !")
        print(f"    - Domaine           : {res['domain']}")
        print(f"    - Éléments traités  : {res['items_processed']} / {res['items_total']}")
        print(f"    - Liaisons BDC      : {res['linked_tenders']}")
        print(f"    - Erreurs           : {res['errors_count']}")
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(run_cli())
