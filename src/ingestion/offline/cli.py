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
    export_parser.add_argument("--pages", type=int, default=5, help="Number of pages to collect (default: 5)")
    export_parser.add_argument("--page-size", type=int, default=50, help="Items per request (default: 50)")
    export_parser.add_argument("--date-start", type=str, default=None, help="Start date (DD/MM/YYYY)")
    export_parser.add_argument("--date-end", type=str, default=None, help="End date (DD/MM/YYYY)")
    export_parser.add_argument("--keyword", type=str, default=None, help="Filter keyword")
    export_parser.add_argument("--output", type=str, default=None, help="Output JSON path")

    # 2. Import Command (Server-side Database Sync)
    import_parser = subparsers.add_parser("import", help="Import an offline JSON bundle into PostgreSQL database")
    import_parser.add_argument("file", type=str, help="Path to export bundle JSON file")

    args = parser.parse_args()

    if args.command == "export":
        exporter = OfflineExporter()
        if args.awards:
            print(f"[*] Collecting {args.pages} pages of awards locally (no database required)...")
            res = await exporter.collect_awards(
                max_pages=args.pages,
                page_size=args.page_size,
                date_start=args.date_start,
                date_end=args.date_end,
                keyword=args.keyword,
                output_path=args.output
            )
            print(f"[✓] Successfully generated awards export: {res['output_file']}")
            print(f"    - Items collected: {res['item_count']}")
            print(f"    - Portal archive total: {res['portal_total_archive']}")
            print(f"    - SHA256: {res['sha256_checksum']}")
            print("\nYou can now upload this file to the server via the UI or run:")
            print(f"    python -m src.ingestion.offline.cli import {res['output_file']}")

        elif args.bdc:
            print(f"[*] Collecting {args.pages} pages of active BDCs locally (no database required)...")
            res = await exporter.collect_bdc(
                max_pages=args.pages,
                page_size=args.page_size,
                output_path=args.output
            )
            print(f"[✓] Successfully generated BDC export: {res['output_file']}")
            print(f"    - Items collected: {res['item_count']}")
            print(f"    - SHA256: {res['sha256_checksum']}")
        else:
            print("[!] Please specify --awards or --bdc to export.")
            sys.exit(1)

    elif args.command == "import":
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"[!] File not found: {file_path}")
            sys.exit(1)

        print(f"[*] Importing offline bundle '{file_path}' into PostgreSQL database...")
        importer = OfflineImporter()
        res = await importer.import_bundle(file_path)
        print(f"[✓] Import complete!")
        print(f"    - Domain: {res['domain']}")
        print(f"    - Processed items: {res['items_processed']} / {res['items_total']}")
        print(f"    - Linked to consultations: {res['linked_tenders']}")
        print(f"    - Errors: {res['errors_count']}")
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(run_cli())
