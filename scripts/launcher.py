"""
Moroccan Public Procurement Intelligence Engine - Windows Launcher & Local Executer
Provides interactive menu for:
1. Starting local web dashboard & launching browser
2. Extracting awards / results into portable JSON bundles (offline, no DB needed)
3. Extracting active BDC notices into portable JSON bundles (All active avis, sorting old-to-new, resumable)
4. Uploading bundles to live production server (https://bergag.ma or custom)
5. Importing bundles into local PostgreSQL database
6. Resuming interrupted crawls from checkpoint
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
from typing import Optional, List, Dict, Any

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
  ✔ Collecteur Hors-Ligne Résilient avec Sauvegarde Incrémentale & Reprise
  ✔ Extraction Triée (Ancien -> Nouveau) & Synchronisation Serveur Distant{TermColor.RESET}
--------------------------------------------------------------------------------
    """
    print(banner)

def get_exports_dir() -> Path:
    p = ROOT_DIR / "data" / "offline_exports"
    p.mkdir(parents=True, exist_ok=True)
    return p

def list_recent_exports():
    exp_dir = get_exports_dir()
    files = sorted(exp_dir.glob("export_*.json"), key=os.path.getmtime, reverse=True)
    return files

def clean_input(val: str | None) -> str | None:
    if not val:
        return None
    val = val.strip()
    low = val.lower()
    if low in (
        "aucun", "none", "null", "non", "tout", "all", "*", "",
        "tous", "tous les secteurs", "tous secteurs", "tout secteur",
        "tous les marches", "tous les marchés", "tous marches", "tous marchés"
    ):
        return None
    return val

def clean_date(val: str | None) -> str | None:
    import re
    val = clean_input(val)
    if not val:
        return None
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", val):
        parts = val.split("/")
        return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}"
    print(f"    {TermColor.YELLOW}[!] Date '{val}' ignorée car non reconnue (format requis: JJ/MM/AAAA).{TermColor.RESET}")
    return None

async def run_awards_export(pages: Optional[int] = 5, keyword: str = None, date_start: str = None, date_end: str = None, resume: bool = True):
    from src.ingestion.offline.exporter import OfflineExporter
    keyword = clean_input(keyword)
    date_start = clean_date(date_start)
    date_end = clean_date(date_end)

    pages_label = "TOUT l'Historique disponible (Archive complète)" if (pages is None or pages <= 0) else f"{pages} pages (~{pages * 50} attributions)"

    print(f"\n{TermColor.YELLOW}[*] Démarrage de la collecte locale des attributions...{TermColor.RESET}")
    print(f"    - Périmètre       : {TermColor.BOLD}{pages_label}{TermColor.RESET}")
    print(f"    - Filtre mot-clé  : {keyword if keyword else 'Aucun (Tous les secteurs)'}")
    print(f"    - Période         : {('du ' + date_start if date_start else '') + (' au ' + date_end if date_end else '') if (date_start or date_end) else 'Historique complet'}")
    print(f"    - Source portail  : https://www.marchespublics.gov.ma/bdc/entreprise/consultation/resultat")
    print(f"    - Mode            : Autonome (Sauvegarde incrémentale sur disque)\n")

    exporter = OfflineExporter()

    def progress_cb(info):
        p = info.get("page")
        tot = info.get("total_pages")
        cnt = info.get("items_collected")
        tot_arc = info.get("portal_total")
        print(f"  [+] Page {p}/{tot} | {cnt} attributions enregistrées (Total portail: {tot_arc})...", end="\r")

    try:
        res = await exporter.collect_awards(
            max_pages=pages,
            page_size=50,
            keyword=keyword,
            date_start=date_start,
            date_end=date_end,
            resume=resume,
            progress_callback=progress_cb
        )
        
        print(f"\n\n{TermColor.GREEN}{TermColor.BOLD}[✓] Collecte locale terminée avec succès !{TermColor.RESET}")
        print(f"    📁 Fichier généré       : {TermColor.CYAN}{Path(res['output_file']).resolve()}{TermColor.RESET}")
        print(f"    📊 Attributions sauvées : {res['item_count']}")
        print(f"    🌐 Total portail TGR    : {res['portal_total_archive']}")
        print(f"    🔒 Empreinte SHA256     : {res['sha256_checksum']}")
        return res
    except KeyboardInterrupt:
        print(f"\n\n{TermColor.YELLOW}[!] Collecte interrompue par l'utilisateur. Données déjà collectées enregistrées.{TermColor.RESET}")
        return None
    except Exception as e:
        print(f"\n{TermColor.RED}[!] Erreur lors de la collecte : {e}{TermColor.RESET}")
        return None

async def run_awards_monthly_export(
    year: int = 2026,
    start_month: int = 1,
    end_month: int = 12,
    max_pages_per_month: Optional[int] = None,
    keyword: Optional[str] = None
):
    from src.ingestion.offline.exporter import OfflineExporter
    exporter = OfflineExporter()
    keyword = clean_input(keyword)

    pages_desc = "TOUTES les pages de chaque mois" if (max_pages_per_month is None or max_pages_per_month <= 0) else f"Max {max_pages_per_month} pages/mois (~{max_pages_per_month * 50} avis)"

    print(f"\n{TermColor.YELLOW}[*] Démarrage de la collecte mensuelle des attributions pour l'année {year}...{TermColor.RESET}")
    print(f"    - Mois cibles     : de {start_month:02d}/{year} à {end_month:02d}/{year}")
    print(f"    - Volume par mois : {pages_desc}")
    print(f"    - Filtre mot-clé  : {keyword if keyword else 'Aucun (Tous les secteurs)'}")
    print(f"    - Sortie          : Un fichier JSON individuel par mois dans data/offline_exports/\n")

    def progress_cb(info):
        m = info.get("current_month")
        y = info.get("current_year")
        p = info.get("page")
        tot = info.get("total_pages") or "?"
        cnt = info.get("items_collected")
        prefix = f"[{m:02d}/{y}] " if (m and y) else ""
        print(f"  {prefix}Page {p}/{tot} | {cnt} avis enregistrés...", end="\r")

    try:
        results = await exporter.collect_awards_by_months(
            year=year,
            start_month=start_month,
            end_month=end_month,
            max_pages_per_month=max_pages_per_month,
            keyword=keyword,
            progress_callback=progress_cb
        )
        print(f"\n\n{TermColor.GREEN}{TermColor.BOLD}[✓] Collecte mensuelle par lots terminée avec succès !{TermColor.RESET}")
        total_awards = sum(r.get("item_count", 0) for r in results)
        print(f"    📊 Fichiers mensuels générés : {len(results)}")
        print(f"    📈 Total attributions sauvées : {total_awards}")
        for r in results:
            print(f"       • Mois {r['month']:02d}/{r['year']} : {r['item_count']} avis -> {Path(r['output_file']).name}")
        return results
    except KeyboardInterrupt:
        print(f"\n\n{TermColor.YELLOW}[!] Collecte mensuelle interrompue par l'utilisateur. Mois déjà traités conservés.{TermColor.RESET}")
        return None
    except Exception as e:
        print(f"\n{TermColor.RED}[!] Erreur lors de la collecte mensuelle : {e}{TermColor.RESET}")
        return None

async def run_awards_recent_months_export(
    n_months: int = 6,
    max_pages_per_month: Optional[int] = None,
    keyword: Optional[str] = None
):
    from src.ingestion.offline.exporter import OfflineExporter
    exporter = OfflineExporter()
    keyword = clean_input(keyword)

    pages_desc = "TOUTES les pages de chaque mois" if (max_pages_per_month is None or max_pages_per_month <= 0) else f"Max {max_pages_per_month} pages/mois"

    print(f"\n{TermColor.YELLOW}[*] Démarrage de la collecte des {n_months} derniers mois glissants...{TermColor.RESET}")
    print(f"    - Périmètre       : Derniers {n_months} mois")
    print(f"    - Volume par mois : {pages_desc}")
    print(f"    - Filtre mot-clé  : {keyword if keyword else 'Aucun'}\n")

    def progress_cb(info):
        m = info.get("current_month")
        y = info.get("current_year")
        p = info.get("page")
        tot = info.get("total_pages") or "?"
        cnt = info.get("items_collected")
        prefix = f"[{m:02d}/{y}] " if (m and y) else ""
        print(f"  {prefix}Page {p}/{tot} | {cnt} avis enregistrés...", end="\r")

    try:
        results = await exporter.collect_awards_recent_months(
            n_months=n_months,
            max_pages_per_month=max_pages_per_month,
            keyword=keyword,
            progress_callback=progress_cb
        )
        print(f"\n\n{TermColor.GREEN}{TermColor.BOLD}[✓] Collecte des {n_months} derniers mois terminée avec succès !{TermColor.RESET}")
        total_awards = sum(r.get("item_count", 0) for r in results)
        print(f"    📊 Fichiers mensuels générés : {len(results)}")
        print(f"    📈 Total attributions sauvées : {total_awards}")
        for r in results:
            print(f"       • Mois {r['month']:02d}/{r['year']} : {r['item_count']} avis -> {Path(r['output_file']).name}")
        return results
    except KeyboardInterrupt:
        print(f"\n\n{TermColor.YELLOW}[!] Collecte interrompue par l'utilisateur.{TermColor.RESET}")
        return None
    except Exception as e:
        print(f"\n{TermColor.RED}[!] Erreur lors de la collecte : {e}{TermColor.RESET}")
        return None

async def run_bdc_export(pages: int | None = 5, order: str = "asc", resume: bool = True):
    from src.ingestion.offline.exporter import OfflineExporter
    exporter = OfflineExporter()

    order_label = "Du plus ancien au plus récent (Ordre chronologique)" if order == "asc" else "Du plus récent au plus ancien"
    pages_label = "TOUS les avis actifs du portail (Intégralité)" if (pages is None or pages <= 0) else f"{pages} pages (~{pages * 50} consultations)"

    print(f"\n{TermColor.YELLOW}[*] Démarrage de la collecte locale des BDC actifs...{TermColor.RESET}")
    print(f"    - Périmètre : {TermColor.BOLD}{pages_label}{TermColor.RESET}")
    print(f"    - Tri       : {TermColor.CYAN}{order_label}{TermColor.RESET}")
    print(f"    - Reprise   : {'Activée (Sauvegarde continue sur disque)' if resume else 'Nouvelle collecte'}")
    print(f"    - Astuce    : Vous pouvez interrompre (Ctrl+C) à tout moment sans rien perdre !\n")

    def progress_cb(info):
        curr_p = info.get("current_page")
        tot_p = info.get("total_pages")
        items = info.get("items_collected")
        c_idx = info.get("card_index")
        c_tot = info.get("cards_on_page")
        tot_active = info.get("total_active_portal")
        title = (info.get("current_item") or {}).get("title", "")[:40]
        ref = (info.get("current_item") or {}).get("reference", "")
        sys.stdout.write(f"\r  [{curr_p}/{tot_p}] Avis {c_idx}/{c_tot} | Total : {items}/{tot_active} avis | {ref}: {title}...   ")
        sys.stdout.flush()

    try:
        res = await exporter.collect_bdc(
            max_pages=pages,
            page_size=50,
            order=order,
            resume=resume,
            progress_callback=progress_cb
        )
        print("\n")
        print(f"{TermColor.GREEN}{TermColor.BOLD}[✓] Collecte BDC terminée avec succès !{TermColor.RESET}")
        print(f"    📁 Fichier généré       : {TermColor.CYAN}{Path(res['output_file']).resolve()}{TermColor.RESET}")
        print(f"    📊 Avis enregistrés     : {res['item_count']} consultations avec bordereaux")
        print(f"    🌐 Total actif portail  : {res['total_active_archive']} avis")
        print(f"    🔒 Empreinte SHA256     : {res['sha256_checksum']}")
        print(f"    ⏱️  Durée                : {res['duration_seconds']}s")
        return res
    except KeyboardInterrupt:
        print(f"\n\n{TermColor.YELLOW}[!] Collecte interrompue par l'utilisateur (Ctrl+C).{TermColor.RESET}")
        print(f"    - {TermColor.GREEN}Toutes les pages traitées sont déjà enregistrées sur votre disque.{TermColor.RESET}")
        print(f"    - Vous pouvez reprendre à tout moment en choisissant l'option [R] dans le menu !")
        return None
    except Exception as e:
        print(f"\n\n{TermColor.RED}[!] Erreur lors de la collecte : {e}{TermColor.RESET}")
        print(f"    - Point de sauvegarde (checkpoint) conservé pour reprise.")
        return None

async def upload_file_to_live_server(file_path: Path, server_url: str):
    import httpx
    if not file_path.exists():
        print(f"{TermColor.RED}[!] Fichier introuvable : {file_path}{TermColor.RESET}")
        return

    server_url = server_url.rstrip("/")

    # Detect domain from manifest or filename
    domain = "bdc" if "bdc" in file_path.name.lower() else "awards"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            head = f.read(2048)
            if '"domain": "bdc"' in head or '"domain":"bdc"' in head:
                domain = "bdc"
            elif '"domain": "awards"' in head or '"domain":"awards"' in head:
                domain = "awards"
    except Exception:
        pass

    # Candidate endpoints in order of preference
    candidate_endpoints = [
        f"{server_url}/api/admin/ingestion/offline/upload",
        f"{server_url}/api/admin/ingestion/{domain}/offline/upload",
        f"{server_url}/api/admin/ingestion/awards/offline/upload"
    ]

    size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
    size_kb = round(file_path.stat().st_size / 1024, 1)
    size_display = f"{size_mb} MB" if size_mb >= 1.0 else f"{size_kb} KB"

    print(f"\n{TermColor.YELLOW}[*] Préparation du téléversement vers le serveur distant ({server_url})...{TermColor.RESET}")
    print(f"    - Fichier local       : {file_path.name}")
    print(f"    - Taille              : {size_display}")
    print(f"    - Domaine détecté     : {TermColor.BOLD}{domain.upper()}{TermColor.RESET}")

    last_status = None
    last_response_text = ""
    success = False

    # Timeout scaled with file size (min 180s, up to 600s for large 10MB+ files)
    upload_timeout = max(180.0, file_path.stat().st_size / 20000)

    try:
        async with httpx.AsyncClient(timeout=upload_timeout, verify=False) as client:
            multipart_endpoints = [
                f"{server_url}/api/admin/ingestion/offline/upload",
                f"{server_url}/api/admin/ingestion/{domain}/offline/upload",
                f"{server_url}/api/admin/ingestion/awards/offline/upload"
            ]

            last_status = None
            needs_json_fallback = False

            for endpoint in multipart_endpoints:
                print(f"    -> Tentative d'envoi multipart vers : {endpoint}...", end="\r")
                try:
                    with open(file_path, "rb") as f:
                        files = {"file": (file_path.name, f, "application/json")}
                        resp = await client.post(endpoint, files=files)
                    last_status = resp.status_code
                except Exception:
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    print(f"\n\n{TermColor.GREEN}{TermColor.BOLD}[✓] Synchronisation réussie sur le serveur !{TermColor.RESET}")
                    print(f"    - Endpoint utilisé    : {endpoint}")
                    print(f"    - Domaine traité      : {data.get('domain', domain).upper()}")
                    print(f"    - Éléments importés   : {data.get('items_processed')} / {data.get('items_total')}")
                    print(f"    - Consultations liées : {data.get('linked_tenders', 0)}")
                    print(f"    - Erreurs             : {data.get('errors_count', 0)}")
                    return
                elif resp.status_code == 503:
                    print(f"\n{TermColor.YELLOW}[!] Serveur sans module multipart (503). Bascule automatique vers le mode JSON direct...{TermColor.RESET}")
                    needs_json_fallback = True
                    break
                elif resp.status_code == 404:
                    continue
                else:
                    print(f"\n{TermColor.YELLOW}[!] Réponse HTTP {resp.status_code} sur {endpoint}. Tentative en mode JSON direct...{TermColor.RESET}")
                    needs_json_fallback = True
                    break

            # 2. Try JSON payload endpoints (fallback when multipart is absent or failed)
            json_endpoints = [
                f"{server_url}/api/admin/ingestion/offline/sync-json",
                f"{server_url}/api/admin/ingestion/{domain}/offline/sync-json",
                f"{server_url}/api/admin/ingestion/awards/offline/sync-json"
            ]
            print(f"    -> Lecture du bundle JSON pour transmission directe...")
            with open(file_path, "rb") as f:
                file_content = f.read()

            headers = {"Content-Type": "application/json"}
            for j_ep in json_endpoints:
                print(f"    -> Tentative directe (JSON payload) vers : {j_ep}...", end="\r")
                try:
                    resp = await client.post(j_ep, content=file_content, headers=headers)
                    last_status = resp.status_code
                    if resp.status_code == 200:
                        data = resp.json()
                        print(f"\n\n{TermColor.GREEN}{TermColor.BOLD}[✓] Synchronisation réussie sur le serveur (Mode JSON direct) !{TermColor.RESET}")
                        print(f"    - Endpoint utilisé    : {j_ep}")
                        print(f"    - Domaine traité      : {data.get('domain', domain).upper()}")
                        print(f"    - Éléments importés   : {data.get('items_processed')} / {data.get('items_total')}")
                        print(f"    - Consultations liées : {data.get('linked_tenders', 0)}")
                        print(f"    - Erreurs             : {data.get('errors_count', 0)}")
                        return
                    elif resp.status_code == 404:
                        continue
                    else:
                        print(f"\n\n{TermColor.RED}[!] Erreur HTTP {resp.status_code} sur {j_ep} :{TermColor.RESET}")
                        print(f"    {resp.text[:300]}")
                        return
                except Exception:
                    continue

            # If all failed:
            print(f"\n\n{TermColor.RED}{TermColor.BOLD}[!] Échec de synchronisation : Le serveur a répondu HTTP {last_status or 404}.{TermColor.RESET}")
            print(f"    - Serveur ciblé : {server_url}")
            print(f"\n{TermColor.YELLOW}💡 Explication & Résolution :{TermColor.RESET}")
            print(f"    1. Assurez-vous que le serveur ({server_url}) est à jour (git pull && docker compose restart web).")
            print(f"\n    2. Si vous souhaitez importer ces données directement dans votre base locale :")
            print(f"       -> Utilisez l'option {TermColor.BOLD}[5] 💾 Importer un Fichier Local dans PostgreSQL Local{TermColor.RESET} du menu principal.")
            print(f"       -> L'importation s'exécutera instantanément en local sans dépendre du serveur distant !")

    except httpx.ConnectError:
        print(f"\n\n{TermColor.RED}[!] Impossible de joindre le serveur distant à l'adresse : {server_url}{TermColor.RESET}")
        print(f"    Vérifiez que le serveur est démarré et que votre VPN/réseau est connecté.")
    except Exception as e:
        print(f"\n\n{TermColor.RED}[!] Erreur lors de l'envoi au serveur distant : {e}{TermColor.RESET}")

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

    def open_browser():
        time.sleep(2.0)
        webbrowser.open("http://localhost:8000")

    import threading
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()

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
    resolved_path = str(exp_dir.resolve())
    print(f"\n{TermColor.CYAN}[*] Ouverture du dossier dans l'Explorateur Windows :{TermColor.RESET}")
    print(f"    {resolved_path}")
    os.startfile(resolved_path)

def interactive_menu():
    from src.ingestion.offline.exporter import OfflineExporter
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print_banner()

        # Check for active checkpoints
        bdc_cp = OfflineExporter.get_checkpoint("bdc")
        awards_cp = OfflineExporter.get_checkpoint("awards")

        if bdc_cp:
            done_pages = len(bdc_cp.get("completed_pages", []))
            tot_pages = len(bdc_cp.get("target_pages", []))
            items = bdc_cp.get("items_count", 0)
            print(f"  {TermColor.YELLOW}⚡ REPRISE DISPONIBLE (BDC) : {items} avis sauvés ({done_pages}/{tot_pages} pages). Option [R] pour continuer !{TermColor.RESET}\n")
        elif awards_cp:
            done_pages = len(awards_cp.get("completed_pages", []))
            items = awards_cp.get("item_count", 0)
            print(f"  {TermColor.YELLOW}⚡ REPRISE DISPONIBLE (Awards) : {items} attributions sauvées ({done_pages} pages). Option [R] pour continuer !{TermColor.RESET}\n")

        print(f"{TermColor.BOLD}Choisissez une action :{TermColor.RESET}\n")
        print(f"  {TermColor.GREEN}[1] 🚀 Lancer le Dashboard Local & Ouvrir le Navigateur (http://localhost:8000){TermColor.RESET}")
        print(f"  {TermColor.CYAN}[2] 📥 Ingestion : Collecter les Attributions (Awards) dans un Fichier Local JSON{TermColor.RESET}")
        print(f"  {TermColor.CYAN}[3] 📋 Ingestion : Collecter TOUS les BDC Actifs (Trié Ancien -> Nouveau, Reprenable){TermColor.RESET}")
        if bdc_cp or awards_cp:
            print(f"  {TermColor.YELLOW}[R] ▶️  Reprendre la Collecte Interrompue{TermColor.RESET}")
        print(f"  {TermColor.YELLOW}[4] ☁️  Téléverser un Fichier Local vers le Serveur en Ligne (Live Sync){TermColor.RESET}")
        print(f"  {TermColor.DIM}[5] 💾 Importer un Fichier Local dans PostgreSQL Local{TermColor.RESET}")
        print(f"  [6] 📁 Ouvrir le dossier des fichiers exportés (data/offline_exports)")
        print(f"  [7] 🌐 Tester la connexion au portail des Marchés Publics (TGR / WAF)")
        print(f"  {TermColor.RED}[0] ❌ Quitter{TermColor.RESET}\n")

        choice = input(f"{TermColor.BOLD}Entrez votre choix : {TermColor.RESET}").strip()

        if choice == "1":
            start_local_dashboard()
            break
        elif choice == "2":
            print(f"\n{TermColor.BOLD}=== PÉRIMÈTRE DE COLLECTE DES ATTRIBUTIONS (AWARDS) ==={TermColor.RESET}")
            print(f"  {TermColor.GREEN}[1] 📅 Mode Mensuel par Lots (Recommandé pour gros volumes - Mois par Mois){TermColor.RESET}")
            print(f"  {TermColor.CYAN}[2] 🌐 Mode TOUT l'Historique (Archive complète de la page 1 jusqu'à la fin){TermColor.RESET}")
            print(f"  {TermColor.YELLOW}[3] 📄 Mode Pages Récentes (ex: 5 pages = 250 avis, 20 pages = 1 000 avis){TermColor.RESET}")
            print(f"  [4] 🎯 Mode Filtre par Dates & Mots-clés (Personnalisé)")
            print(f"  {TermColor.RED}[0] ⬅️  Retour au menu principal{TermColor.RESET}\n")

            sub_choice = input(f"{TermColor.BOLD}Votre choix [1-4, Entrée=1] : {TermColor.RESET}").strip() or "1"

            if sub_choice == "1":
                now_dt = datetime.now()
                print(f"\n{TermColor.BOLD}Sélectionnez la période mensuelle :{TermColor.RESET}")
                print(f"  [1] 📅 Année {now_dt.year} (Mois par Mois, de Janvier au mois en cours)")
                print("  [2] ⏳ Les 3 derniers mois glissants")
                print("  [3] ⏳ Les 6 derniers mois glissants")
                print(f"  [4] 📅 Année précédente ({now_dt.year - 1} complète)")
                print("  [5] 🗓️  Choisir une autre année spécifique (ex: 2024, 2023)")
                m_choice = input("Votre choix [1-5, Entrée=1] : ").strip() or "1"

                p_in = input("\nNombre max de pages par mois (Entrée = TOUT le mois sans limite) : ").strip()
                max_p = int(p_in) if p_in.isdigit() and int(p_in) > 0 else None
                kw = input("Mot-clé optionnel de filtrage [Entrée = Tous les secteurs] : ").strip() or None

                if m_choice == "1":
                    asyncio.run(run_awards_monthly_export(year=now_dt.year, start_month=1, end_month=now_dt.month, max_pages_per_month=max_p, keyword=kw))
                elif m_choice == "2":
                    asyncio.run(run_awards_recent_months_export(n_months=3, max_pages_per_month=max_p, keyword=kw))
                elif m_choice == "3":
                    asyncio.run(run_awards_recent_months_export(n_months=6, max_pages_per_month=max_p, keyword=kw))
                elif m_choice == "4":
                    asyncio.run(run_awards_monthly_export(year=now_dt.year - 1, start_month=1, end_month=12, max_pages_per_month=max_p, keyword=kw))
                elif m_choice == "5":
                    yr_in = input("Entrez l'année (ex: 2024) : ").strip()
                    yr = int(yr_in) if yr_in.isdigit() else 2024
                    asyncio.run(run_awards_monthly_export(year=yr, start_month=1, end_month=12, max_pages_per_month=max_p, keyword=kw))

            elif sub_choice == "2":
                print(f"\n{TermColor.YELLOW}[*] Collecte de TOUT l'historique des attributions (depuis la page 1)...{TermColor.RESET}")
                kw = input("Mot-clé optionnel de filtrage [Entrée = Tout l'historique] : ").strip() or None
                asyncio.run(run_awards_export(pages=None, keyword=kw, resume=True))

            elif sub_choice == "3":
                p_in = input("\nNombre de pages à collecter [Défaut: 5 pages = ~250 avis] : ").strip()
                pages = int(p_in) if p_in.isdigit() and int(p_in) > 0 else 5
                kw = input("Mot-clé optionnel de filtrage [Entrée = Aucun] : ").strip() or None
                asyncio.run(run_awards_export(pages=pages, keyword=kw, resume=False))

            elif sub_choice == "4":
                dt_s = input("\nDate début publication (JJ/MM/AAAA) [Entrée = Début archive] : ").strip() or None
                dt_e = input("Date fin publication (JJ/MM/AAAA) [Entrée = Date du jour] : ").strip() or None
                kw = input("Mot-clé de filtrage optionnel : ").strip() or None
                p_in = input("Nombre max de pages (Entrée = TOUTES les pages de la période) : ").strip()
                pages = int(p_in) if p_in.isdigit() and int(p_in) > 0 else None
                asyncio.run(run_awards_export(pages=pages, keyword=kw, date_start=dt_s, date_end=dt_e, resume=True))

            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour revenir au menu principal...{TermColor.RESET}")

        elif choice == "3":
            # Checkpoint check
            resume_existing = True
            if bdc_cp:
                print(f"\n{TermColor.YELLOW}[!] Une collecte BDC est actuellement en pause ({bdc_cp.get('items_count')} avis déjà sauvés).{TermColor.RESET}")
                print("  [1] ▶️  Reprendre là où elle s'est arrêtée")
                print("  [2] 🔄 Supprimer et recommencer une nouvelle collecte")
                c_mode = input("Votre choix [1 ou 2, Entrée=1] : ").strip()
                if c_mode == "2":
                    OfflineExporter.clear_checkpoint("bdc")
                    resume_existing = False

            if not bdc_cp or not resume_existing:
                print(f"\n{TermColor.BOLD}1. Périmètre de collecte des avis actifs :{TermColor.RESET}")
                print("  [1] 🌐 TOUS les avis actifs du portail (Actuellement ~41 pages = ~2027 avis)")
                print("  [2] 📄 Nombre spécifique de pages (ex: 5 pages = 250 avis)")
                scope_choice = input("Votre choix [1 ou 2, Entrée=1 pour TOUT] : ").strip()

                target_pages = None
                if scope_choice == "2":
                    p_in = input("Nombre de pages à collecter [Défaut: 5] : ").strip()
                    target_pages = int(p_in) if p_in.isdigit() and int(p_in) > 0 else 5

                print(f"\n{TermColor.BOLD}2. Ordre de tri chronologique :{TermColor.RESET}")
                print("  [1] ⏳ Du plus ancien au plus récent (Ordre chronologique croissant - Idéal pour ne rien rater)")
                print("  [2] ⚡ Du plus récent au plus ancien (Nouveaux avis d'abord)")
                sort_choice = input("Votre choix [1 ou 2, Entrée=1 (Ancien -> Nouveau)] : ").strip()
                order = "desc" if sort_choice == "2" else "asc"

                asyncio.run(run_bdc_export(pages=target_pages, order=order, resume=False))
            else:
                asyncio.run(run_bdc_export(pages=None, resume=True))

            input(f"\n{TermColor.DIM}Appuyez sur Entrée pour revenir au menu principal...{TermColor.RESET}")

        elif choice.lower() == "r":
            if bdc_cp:
                asyncio.run(run_bdc_export(pages=None, resume=True))
            elif awards_cp:
                asyncio.run(run_awards_export(resume=True))
            else:
                print(f"\n{TermColor.YELLOW}[!] Aucune collecte à reprendre.{TermColor.RESET}")
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
    parser.add_argument("--all", action="store_true", help="Extraire TOUS les avis actifs du portail ou TOUT l'historique des attributions")
    parser.add_argument("--by-month", action="store_true", help="Extraire les attributions par lots mensuels (Mois par Mois)")
    parser.add_argument("--year", type=int, default=None, help="Année cible pour l'extraction mensuelle (ex: 2026)")
    parser.add_argument("--months", type=int, default=None, help="Nombre de derniers mois glissants à extraire (ex: 3, 6, 12)")
    parser.add_argument("--order", choices=["asc", "desc"], default="asc", help="Ordre de tri: 'asc' (ancien -> nouveau) ou 'desc' (nouveau -> ancien)")
    parser.add_argument("--pages", type=int, default=5, help="Nombre de pages à collecter")
    parser.add_argument("--resume", action="store_true", help="Reprendre la collecte en cours")
    parser.add_argument("--keyword", type=str, default=None, help="Mot-clé de filtrage")
    parser.add_argument("--upload", type=str, default=None, help="Chemin du fichier JSON à téléverser")
    parser.add_argument("--server", type=str, default="https://bergag.ma", help="URL du serveur cible")

    args = parser.parse_args()

    if args.web:
        start_local_dashboard()
    elif args.resume:
        asyncio.run(run_bdc_export(pages=None, resume=True))
    elif args.awards:
        if args.by_month or args.year or args.months:
            if args.months:
                asyncio.run(run_awards_recent_months_export(n_months=args.months, max_pages_per_month=None if args.all else args.pages, keyword=args.keyword))
            else:
                target_year = args.year or datetime.now().year
                asyncio.run(run_awards_monthly_export(year=target_year, max_pages_per_month=None if args.all else args.pages, keyword=args.keyword))
        else:
            p = None if args.all else args.pages
            asyncio.run(run_awards_export(pages=p, keyword=args.keyword))
    elif args.bdc:
        p = None if args.all else args.pages
        asyncio.run(run_bdc_export(pages=p, order=args.order, resume=False))
    elif args.upload:
        asyncio.run(upload_file_to_live_server(Path(args.upload), args.server))
    else:
        interactive_menu()

if __name__ == "__main__":
    main()
