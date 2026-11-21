"""
Moroccan Public Procurement Intelligence Engine - Windows Launcher & Local Executer
Provides interactive menu for:
1. Starting local web dashboard & launching browser
2. Extracting awards / results into portable JSON bundles (offline, no DB needed)
3. Extracting active BDC notices into portable JSON bundles
4. Uploading bundles to live production server (https://bergag.ma or custom)
5. Importing bundles into local PostgreSQL database
"""

import os
import sys
import time
import json
import asyncio
import argparse
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime

# Add root directory to pythonpath
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Color helpers for Windows terminal
class TermColor:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def print_banner():
    banner = f"""{TermColor.CYAN}{TermColor.BOLD}
================================================================================
  🇲🇦  MARCHÉS PUBLICS MAROC - SUITE D'INTELLIGENCE ÉCONOMIQUE & DÉCIDEURS
================================================================================{TermColor.RESET}
  {TermColor.GREEN}✔ Surveillance BDC Décret 2-22-431 (Art. 91) & Appels d'Offres (AO)
  ✔ Moteur de Cascade de Scoring & Détection de Fournisseurs
  ✔ Collecteur Hors-Ligne & Synchronisation Serveur Distant{TermColor.RESET}
--------------------------------------------------------------------------------
    """
    print(banner)

def get_exports_dir() -> Path:
    p = ROOT_DIR / "data" / "offline_exports"
    p.mkdir(parents=True, exist_ok=True)
    return p

def list_recent_exports():
    exp_dir = get_exports_dir()
    files = sorted(exp_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    return files

async def run_awards_export(pages: int = 5, keyword: str = None, date_start: str = None, date_end: str = None):
    from src.ingestion.offline.exporter import OfflineExporter
    print(f"\n{TermColor.YELLOW}[*] Démarrage de la collecte locale des attributions...{TermColor.RESET}")
    print(f"    - Pages demandées : {pages} (~{pages * 50} attributions)")
    if keyword:
        print(f"    - Filtre mot-clé  : {keyword}")
    if date_start or date_end:
        print(f"    - Période         : du {date_start or '*'} au {date_end or '*'}")
    print(f"    - Source portail  : https://www.marchespublics.gov.ma/bdc/entreprise/consultation/resultat")
    print(f"    - Mode            : Autonome (Aucune base de données requise)\n")

    exporter = OfflineExporter()
    res = await exporter.collect_awards(
        max_pages=pages,
        page_size=50,
        keyword=keyword,
        date_start=date_start,
        date_end=date_end
    )
    
    print(f"\n{TermColor.GREEN}{TermColor.BOLD}[✓] Collecte locale terminée avec succès !{TermColor.RESET}")
    print(f"    📁 Fichier généré       : {TermColor.CYAN}{res['output_file']}{TermColor.RESET}")
    print(f"    📊 Attributions sauvées : {res['item_count']}")
    print(f"    🌐 Total portail TGR    : {res['portal_total_archive']}")
    print(f"    🔒 Empreinte SHA256     : {res['sha256_checksum']}")
    print(f"\nCe fichier est prêt à être téléversé dans le serveur en ligne.")
    return res

async def run_bdc_export(pages: int = 5):
    from src.ingestion.offline.exporter import OfflineExporter
    print(f"\n{TermColor.YELLOW}[*] Démarrage de la collecte locale des BDC actifs avec bordereaux...{TermColor.RESET}")
    print(f"    - Pages demandées : {pages} (~{pages * 50} consultations)")
    
    exporter = OfflineExporter()
    res = await exporter.collect_bdc(max_pages=pages, page_size=50)
    
    print(f"\n{TermColor.GREEN}{TermColor.BOLD}[✓] Collecte BDC terminée avec succès !{TermColor.RESET}")
    print(f"    📁 Fichier généré    : {TermColor.CYAN}{res['output_file']}{TermColor.RESET}")
    print(f"    📊 Avis enregistrés  : {res['item_count']}")
    print(f"    🔒 Empreinte SHA256  : {res['sha256_checksum']}")
    return res

async def upload_file_to_live_server(file_path: Path, server_url: str):
    import httpx
    if not file_path.exists():
        print(f"{TermColor.RED}[!] Fichier introuvable : {file_path}{TermColor.RESET}")
        return

    # Normalize URL
    server_url = server_url.rstrip("/")
    target_endpoint = f"{server_url}/api/admin/ingestion/awards/offline/upload"

    print(f"\n{TermColor.YELLOW}[*] Envoi du bundle vers le serveur en ligne : {target_endpoint}...{TermColor.RESET}")
    print(f"    - Fichier : {file_path.name} ({round(file_path.stat().st_size / 1024, 1)} KB)")

    try:
        async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "application/json")}
                resp = await client.post(target_endpoint, files=files)

            if resp.status_code == 200:
                data = resp.json()
                print(f"\n{TermColor.GREEN}{TermColor.BOLD}[✓] Synchronisation réussie sur le serveur !{TermColor.RESET}")
                print(f"    - Domaine traité : {data.get('domain')}")
                print(f"    - Éléments importés : {data.get('items_processed')} / {data.get('items_total')}")
                print(f"    - Consultations liées : {data.get('linked_tenders')}")
                print(f"    - Erreurs : {data.get('errors_count')}")
            else:
                print(f"{TermColor.RED}[!] Erreur serveur HTTP {resp.status_code} :{TermColor.RESET}")
                print(resp.text)
    except Exception as e:
        print(f"{TermColor.RED}[!] Échec de connexion au serveur distant : {e}{TermColor.RESET}")

async def import_file_to_local_db(file_path: Path):
    from src.ingestion.offline.importer import OfflineImporter
    print(f"\n{TermColor.YELLOW}[*] Importation du fichier dans PostgreSQL local...{TermColor.RESET}")
    importer = OfflineImporter()
    try:
        res = await importer.import_bundle(file_path)
        print(f"\n{TermColor.GREEN}[✓] Importation locale terminée : {res['items_processed']} éléments insérés.{TermColor.RESET}")
    except Exception as e:
        print(f"{TermColor.RED}[!] Erreur lors de l'importation locale : {e}{TermColor.RESET}")

def start_local_dashboard():
    print(f"\n{TermColor.GREEN}[*] Démarrage du serveur web local (FastAPI / Uvicorn)...{TermColor.RESET}")
    print(f"    - URL Locale : {TermColor.CYAN}http://localhost:8000{TermColor.RESET}")
    print(f"    - Appuyez sur Ctrl+C dans cette fenêtre pour arrêter le serveur.\n")

    # Open browser after a short delay
    def open_browser():
        time.sleep(2.0)
        webbrowser.open("http://localhost:8000")

    import threading
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()

    # Run uvicorn
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)

async def test_portal_connection():
    from src.scraper.client import PortalHttpClient
    print(f"\n{TermColor.YELLOW}[*] Test de la connectivité avec marchespublics.gov.ma (WAF F5 BIG-IP)...{TermColor.RESET}")
    client = PortalHttpClient()
    try:
        resp = await client.get("https://www.marchespublics.gov.ma/bdc/entreprise/consultation/resultat")
        if resp.status_code == 200:
            print(f"{TermColor.GREEN}[✓] Connexion réussie (HTTP 200). Le WAF F5 autorise nos requêtes.{TermColor.RESET}")
            print(f"    - Cookies de session reçus : {len(client.cookies)} cookies")
        else:
            print(f"{TermColor.YELLOW}[!] Réponse portail : HTTP {resp.status_code}{TermColor.RESET}")
    except Exception as e:
        print(f"{TermColor.RED}[!] Erreur de connexion au portail : {e}{TermColor.RESET}")
    finally:
        await client.close()

def open_exports_folder():
    exp_dir = get_exports_dir()
    print(f"\n{TermColor.CYAN}[*] Ouverture du dossier : {exp_dir}{TermColor.RESET}")
    os.startfile(str(exp_dir))

def interactive_menu():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print_banner()
        print(f"{TermColor.BOLD}Choisissez une action :{TermColor.RESET}\n")
        print(f"  {TermColor.GREEN}[1] 🚀 Lancer le Dashboard Local & Ouvrir le Navigateur (http://localhost:8000){TermColor.RESET}")
        print(f"  {TermColor.CYAN}[2] 📥 Ingestion : Collecter les Attributions (Awards) dans un Fichier Local JSON{TermColor.RESET}")
        print(f"  {TermColor.CYAN}[3] 📋 Ingestion : Collecter les Bons de Commande (BDC Actifs) dans un Fichier Local JSON{TermColor.RESET}")
        print(f"  {TermColor.YELLOW}[4] ☁️  Téléverser un Fichier Local vers le Serveur en Ligne (Live Sync){TermColor.RESET}")
        print(f"  {TermColor.DIM}[5] 💾 Importer un Fichier Local dans PostgreSQL Local{TermColor.RESET}")
        print(f"  [6] 📁 Ouvrir le dossier des fichiers exportés (data/offline_exports)")
        print(f"  [7] 🌐 Tester la connexion au portail des Marchés Publics (TGR / WAF)")
        print(f"  {TermColor.RED}[0] ❌ Quitter{TermColor.RESET}\n")

        choice = input(f"{TermColor.BOLD}Entrez votre choix [0-7] : {TermColor.RESET}").strip()

        if choice == "1":
            start_local_dashboard()
            break
        elif choice == "2":
            p_in = input("\nNombre de pages à collecter (Défaut: 5 pages = ~250 attributions) [Entrée=5] : ").strip()
            pages = int(p_in) if p_in.isdigit() and int(p_in) > 0 else 5
            kw = input("Mot-clé de filtrage optionnel (ex: informatique, gardiennage) [Entrée=aucun] : ").strip() or None
            dt_s = input("Date début publication (JJ/MM/AAAA) [Entrée=aucun] : ").strip() or None
            dt_e = input("Date fin publication (JJ/MM/AAAA) [Entrée=aucun] : ").strip() or None
            asyncio.run(run_awards_export(pages=pages, keyword=kw, date_start=dt_s, date_end=dt_e))
            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour revenir au menu principal...{TermColor.RESET}")
        elif choice == "3":
            p_in = input("\nNombre de pages BDC à collecter (Défaut: 5 pages) [Entrée=5] : ").strip()
            pages = int(p_in) if p_in.isdigit() and int(p_in) > 0 else 5
            asyncio.run(run_bdc_export(pages=pages))
            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour revenir au menu principal...{TermColor.RESET}")
        elif choice == "4":
            recent = list_recent_exports()
            if not recent:
                print(f"\n{TermColor.YELLOW}[!] Aucun fichier d'export trouvé dans data/offline_exports/{TermColor.RESET}")
                input(f"\n{TermColor.DIM}Appuyez sur Entrée pour continuer...{TermColor.RESET}")
                continue
            print(f"\n{TermColor.BOLD}Fichiers d'export récents disponibles :{TermColor.RESET}")
            for idx, f in enumerate(recent[:8], 1):
                sz = round(f.stat().st_size / 1024, 1)
                print(f"  [{idx}] {f.name} ({sz} KB)")
            f_choice = input(f"\nSélectionnez le fichier [1-{min(8, len(recent))}] ou collez un chemin complet : ").strip()
            target_path = None
            if f_choice.isdigit() and 1 <= int(f_choice) <= len(recent):
                target_path = recent[int(f_choice) - 1]
            elif f_choice:
                target_path = Path(f_choice)

            if target_path and target_path.exists():
                srv = input(f"URL du serveur distant [Défaut: https://bergag.ma] : ").strip() or "https://bergag.ma"
                asyncio.run(upload_file_to_live_server(target_path, srv))
            else:
                print(f"{TermColor.RED}[!] Fichier invalide.{TermColor.RESET}")
            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour revenir au menu principal...{TermColor.RESET}")
        elif choice == "5":
            recent = list_recent_exports()
            if not recent:
                print(f"\n{TermColor.YELLOW}[!] Aucun fichier d'export trouvé.{TermColor.RESET}")
                input(f"\n{TermColor.DIM}Appuyez sur Entrée...{TermColor.RESET}")
                continue
            for idx, f in enumerate(recent[:8], 1):
                print(f"  [{idx}] {f.name}")
            f_choice = input(f"Sélectionnez le fichier à importer en local : ").strip()
            if f_choice.isdigit() and 1 <= int(f_choice) <= len(recent):
                asyncio.run(import_file_to_local_db(recent[int(f_choice) - 1]))
            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour continuer...{TermColor.RESET}")
        elif choice == "6":
            open_exports_folder()
            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour revenir au menu principal...{TermColor.RESET}")
        elif choice == "7":
            asyncio.run(test_portal_connection())
            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour revenir au menu principal...{TermColor.RESET}")
        elif choice == "0":
            print(f"\n{TermColor.CYAN}Au revoir !{TermColor.RESET}")
            break

def main():
    parser = argparse.ArgumentParser(description="Lanceur & Exécuteur Local - Marchés Publics Maroc")
    parser.add_argument("--web", action="store_true", help="Démarrer directement le serveur web local")
    parser.add_argument("--awards", action="store_true", help="Extraire directement les attributions en fichier JSON")
    parser.add_argument("--bdc", action="store_true", help="Extraire directement les BDC en fichier JSON")
    parser.add_argument("--pages", type=int, default=5, help="Nombre de pages à collecter")
    parser.add_argument("--keyword", type=str, default=None, help="Mot-clé de filtrage")
    parser.add_argument("--upload", type=str, default=None, help="Chemin du fichier JSON à téléverser")
    parser.add_argument("--server", type=str, default="https://bergag.ma", help="URL du serveur cible")

    args = parser.parse_args()

    if args.web:
        start_local_dashboard()
    elif args.awards:
        asyncio.run(run_awards_export(pages=args.pages, keyword=args.keyword))
    elif args.bdc:
        asyncio.run(run_bdc_export(pages=args.pages))
    elif args.upload:
        asyncio.run(upload_file_to_live_server(Path(args.upload), args.server))
    else:
        interactive_menu()

if __name__ == "__main__":
    main()
