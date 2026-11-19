# Antigravity Moroccan Public Procurement Intelligence Engine
### Autonomous Opportunity Discovery & Strategic Market Intelligence for `marchespublics.gov.ma`

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-emerald.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 1. Overview & Operational Context

In Morocco, public procurement is governed by **Decree No. 2-22-431** (*Décret relatif aux marchés publics*), promulgated on March 8, 2023. This system monitors, ingests, analyzes, and alerts on opportunities published on the official Treasury portal (**TGR** — `marchespublics.gov.ma`), with specialized intelligence across two procurement channels:

1. **Bons de Commande (BDC — Article 91):**
   - Statutory annual cap of **500,000 MAD TTC** per public buyer per budget line.
   - Ultra-short publication window: minimum **48 hours** before mandatory quote submission.
   - Strict *Moins-Disant* (lowest compliant bidder) award criteria based on line-item quotes (*Bordereau des Prix*).
2. **Appels d'Offres & Marchés Publics (AO):**
   - Formal tenders exceeding the 500k MAD threshold.
   - Predictive Buyer Radar tracking cumulative BDC spend velocity to identify administrations about to reach their cap and legally forced to issue large-scale public tenders.

---

## 2. System Architecture

```
                       [ Portail Marchespublics.gov.ma ]
                                      |
                           (F5 BIG-IP WAF & Cookie Loop)
                                      |
                      [ src/scraper/client.py (httpx) ]
                                      |
             +------------------------+------------------------+
             |                                                 |
   [ Listing Spider (?pageSize=50) ]              [ Results Spider (/resultat) ]
             |                                                 |
   [ Detail Spider (/show/{id}) ]                 [ 340,000 Historical Awards ]
             |                                                 |
   [ Attachment Worker (PDF/DOCX/OCR) ]                        |
             |                                                 |
             +------------------------+------------------------+
                                      |
                      [ PostgreSQL 16 + pgvector ]
                       (Immutable Raw HTML Logs)
                                      |
                    [ 4-Stage Cascade Scoring Engine ]
                      1. Hard Gate Binary Filters
                      2. Lexical & Negative Vetoes
                      3. Line-Item BOM Catalog Coverage
                      4. LLM Judge & Pricing Corridor
                                      |
             +------------------------+------------------------+
             |                                                 |
    Score >= 80% (GO)                                     Active Feed
             |                                                 |
[ Gmail SMTP Dispatcher ]                           [ FastAPI Dashboard & Modal ]
 (60s Decision Card Email)                          (Tailwind + Alpine.js /:8000)
                                                               |
                                                    [ Strategic Market Radar ]
                                                    - Top Winning Competitors
                                                    - Buyer Budget Velocity (Art. 91)
                                                    - Q4 Seasonality Surge (42%+)
```

---

## 3. Key Capabilities & Milestones Completed

- **WAF-Resilient Ingestion:** Navigates F5 BIG-IP ASM security mechanisms using persistent session cookies (`TS01c367b8`, `DCOOKIE`) and realistic TLS browser handshakes, achieving $< 2.5$s page latency.
- **Fast Pagination:** Employs `search_consultation_entreprise[pageSize]=50` to ingest all ~1,600 active notices across Morocco in ~32 HTTP requests ($\approx 45$ seconds).
- **Deep Line-Item Extraction:** Extracts line items directly from Bootstrap 5 `.accordion-item` cards, capturing article orders, designations, units, quantities, and technical specifications.
- **Compound Natural Key Joiner:** Resolves historical results back to consultations via `(buyer_slug, clean_reference, publication_year)`, bypassing the portal's lack of direct consultation IDs.
- **Scanned Attachment OCR Worker:** Dual-pass document reader with native text extraction (`pypdf`/`pdfplumber`), automatic scanned bitmap detection, and `tesseract` fallback (`fra` + `ara`) alongside `.docx` and legacy `.doc` support.
- **Multi-Industry Declarative Profiles:** Configured via human-readable YAML files:
  - `software_data.yaml`: Hamza's core profile (DevOps, Custom Web/Mobile Apps, Data Engineering, Dashboards).
  - `cctv_security.yaml`: Benchmark physical security profile (IP Cameras, NVR, Switches, Cabling).
- **4-Stage Cascade Scoring:** Minimizes inference latency and eliminates LLM token waste:
  1. *Stage 1 (Hard Filters):* Deadline $\ge 24$h, active status, macro-category eligibility.
  2. *Stage 2 (Lexical & Vetoes):* Negative constraints veto out-of-scope services instantly (e.g., civil engineering, catering, mechanical maintenance).
  3. *Stage 3 (BOM Coverage %):* Calculates exact catalog coverage across line items.
  4. *Stage 4 (LLM Judge):* Evaluates risks, execution feasibility, and competitive floor price.
- **60-Second Decision Card via Gmail SMTP:** Generates responsive HTML email alerts delivered to the founder's phone within 120 seconds of publication, featuring clickable official portal links and line-item summaries.
- **Live Feed Web Dashboard:** Single-page dashboard built with Tailwind CSS and Alpine.js (zero node build step required) offering instant filtering, search, and detailed modal views.
- **Strategic Market Intelligence Radar:**
  - *Competitor Dossiers:* Aggregates top winning suppliers, win rates, and average contract values.
  - *Buyer Budget Velocity:* Flags administrations with cumulative BDC spend approaching 500k MAD, warning of upcoming formal Appels d'Offres (AO).
  - *Seasonality Detection:* Analyzes monthly spend concentration confirming Q4 fiscal budget rushes.

---

## 4. Repository Structure

```
mp/
├── docker-compose.yml              # PostgreSQL 16 + pgvector, ingestion-worker, web app
├── Dockerfile                      # Debian multi-stage image with Tesseract OCR (fra+ara) & Poppler
├── alembic.ini                     # Alembic configuration
├── alembic/
│   └── versions/
│       └── 001_initial_schema.py   # PostgreSQL DDL migrations
├── src/
│   ├── config/
│   │   └── settings.py             # Pydantic BaseSettings (.env loading)
│   ├── database/
│   │   └── session.py              # Async SQLAlchemy 2.0 session factory
│   ├── models/
│   │   ├── base.py                 # Declarative Base
│   │   ├── raw.py                  # RawIngestionLog
│   │   ├── tender.py               # Tender, Buyer, LineItem, Award
│   │   └── profile.py              # CompanyProfile, ProfileMatch, UserTenderAction
│   ├── scraper/
│   │   ├── client.py               # WAF-resilient HTTP client
│   │   ├── parser.py               # BeautifulSoup4 DOM parsing functions
│   │   ├── listing_spider.py       # Active BDC listing crawler
│   │   ├── detail_spider.py        # Accordion line-item detail spider
│   │   ├── results_spider.py       # Historical awards scraper
│   │   ├── ao_spider.py            # Main portal Marchés Publics / AO scraper
│   │   ├── attachment_worker.py    # PDF text & OCR fallback worker
│   │   ├── ingestion_service.py    # Idempotent upserts and raw log archiving
│   │   └── results_service.py      # Results backfill and status updates
│   ├── profiles/
│   │   ├── schema.py               # Pydantic schema for YAML profiles
│   │   ├── loader.py               # Profile configuration loader
│   │   └── configs/
│   │       ├── software_data.yaml  # Software development & data engineering profile
│   │       └── cctv_security.yaml  # CCTV & physical security profile
│   ├── engine/
│   │   ├── hard_filters.py         # Stage 1 binary screening
│   │   ├── lexical_matcher.py      # Stage 2 negative constraint screening
│   │   ├── line_item_matcher.py    # Stage 3 BOM coverage calculator
│   │   ├── llm_judge.py            # Stage 4 structured LLM evaluation
│   │   ├── pricing_helper.py       # Floor price & historical comparable estimator
│   │   ├── scoring_cascade.py      # 4-stage orchestrator
│   │   ├── award_matcher.py        # Compound natural key joiner
│   │   ├── competitor_radar.py     # Competitor win count & volume analysis
│   │   └── buyer_radar.py          # Buyer spend velocity & Article 91 escalation alarm
│   ├── alerts/
│   │   └── email_dispatcher.py     # Gmail SMTP STARTTLS Decision Card sender
│   ├── scheduler/
│   │   └── jobs.py                 # Autonomous ingestion & alerting daemon
│   └── api/
│       ├── main.py                 # FastAPI application & HTML dashboard
│       ├── schemas.py              # Pydantic response models
│       └── routes/
│           ├── feed.py             # Feed, detail, and feedback endpoints
│           └── analytics.py        # Competitor & buyer radar REST endpoints
└── tests/
    ├── fixtures/                   # Golden HTML fixtures from the live portal
    ├── test_api.py                 # FastAPI route tests
    ├── test_analytics.py           # Competitor, BuyerRadar, and AoSpider unit tests
    ├── test_attachments.py         # Dual-pass OCR and attachment parsing tests
    ├── test_client_live.py         # WAF navigation verification
    ├── test_email_alerts.py        # Email rendering and dispatch tests
    ├── test_parsers.py             # BeautifulSoup DOM parsing regression tests
    ├── test_profiles.py            # Profile schema validation tests
    ├── test_results_spider.py      # Award parsing and compound key join tests
    ├── test_scoring_cascade.py     # 4-stage scoring pipeline tests
    └── test_spiders.py             # Listing and detail spider tests
```

---

## 5. Quick Start & Local Setup

### 5.1 Prerequisites
- Python 3.12+
- Docker & Docker Compose (optional, for PostgreSQL + pgvector)

### 5.2 Environment Setup
Copy the environment template and configure your credentials:
```bash
cp .env.example .env
```

Edit `.env` with your settings:
```ini
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mp_intelligence

# Gmail SMTP Alert Dispatcher
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx    # 16-character Google App Password
ALERT_RECIPIENT_EMAIL=your_email@gmail.com

# LLM Reasoning Engine (Stage 4)
GEMINI_API_KEY=your_gemini_api_key
```

### 5.3 Install Dependencies
```bash
pip install -r requirements.txt
```

### 5.4 Database Migrations
Run Alembic migrations to initialize the schema:
```bash
alembic upgrade head
```

### 5.5 Run Unit & Regression Tests
Execute the full test suite (28 passing tests):
```bash
python -m pytest tests/
```

### 5.6 Launch the Dashboard & REST API
```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) to view the live dashboard.

### 5.7 Run an Autonomous Crawl & Ingestion Cycle
To trigger a manual ingestion cycle that crawls active notices, extracts line items, scores candidates against all profiles, and sends email alerts:
```bash
python -m src.scheduler.jobs
```

---

## 6. Docker Deployment

To run the complete system (PostgreSQL 16 + pgvector, the Web Dashboard, and the scheduled ingestion worker) in containers:

```bash
docker compose up -d --build
```

Services:
- **`db`**: PostgreSQL 16 on port `5432` with pre-installed `pgvector` and `pg_trgm`.
- **`web`**: FastAPI dashboard on port `8000`.
- **`ingestion-worker`**: Background scheduled crawl daemon.

---

## 7. Adding Custom Company Profiles

Company profiles reside in `src/profiles/configs/*.yaml`. To add a new company profile:

1. Create `src/profiles/configs/my_profile.yaml`:
```yaml
tenant_id: "your-uuid"
profile_name: "mon_entreprise"
macro_filters:
  categories: ["Fournitures", "Services"]
  eligible_regions: []  # Empty for all Morocco
  min_submission_hours: 24
catalog:
  - sku: "SKU-01"
    name: "Nom du produit ou service"
    category: "Fournitures"
    keywords: ["mot-cle-1", "mot-cle-2"]
    negative_keywords: ["travaux", "maconnerie"]
    typical_margin_pct: 35.0
```
2. The scoring cascade and dashboard will automatically discover and load the new profile on next run.

---

## 8. Verification & Test Coverage

The test suite covers every layer of the architecture:
- `test_client_live.py`: Real-time WAF connectivity test.
- `test_parsers.py`: DOM parsing of active listings, Bootstrap 5 accordions, and results cards against offline golden fixtures.
- `test_attachments.py`: PDF native extraction, scanned page detection, and modern/legacy Word documents.
- `test_scoring_cascade.py`: Stage 1 hard gates, Stage 2 lexical vetoes, Stage 3 line-item BOM coverage, and Stage 4 decision recommendations.
- `test_results_spider.py`: Compound reference key normalization (`commune-rurale-de-siroua:35-2026:2026`).
- `test_analytics.py`: Competitor volume rankings, Article 91 buyer spend velocity alarms, and formal AO parser.
- `test_email_alerts.py`: Mobile-responsive HTML Decision Card generation and Gmail SMTP STARTTLS dispatch.

Run:
```bash
python -m pytest tests/ -v
```
Output:
```
======================== 28 passed, 1 warning in 6.46s ========================
```
