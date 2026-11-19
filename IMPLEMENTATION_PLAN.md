# Engineering Implementation Plan: Moroccan Public Procurement Intelligence System

**Target Platform:** Portail Marocain des Marchés Publics (`marchespublics.gov.ma` / TGR)  
**Blueprint Reference:** [`ARCHITECTURE.md`](file:///c:/Users/7mza/mp/ARCHITECTURE.md)  
**Stakeholder & Engineer:** Hamza (Solo Technical Founder)  
**Author:** Principal Architect  
**Date:** November 19, 2026  
**Document Status:** Actionable Implementation Baseline — Version 1.0.0  

---

## 1. Executive Summary & Strategy for a Solo Technical Founder

As a solo technical founder, your primary operational risks are **scope creep**, **portal WAF/DOM drift**, and **maintenance fatigue**. To maximize velocity and deliver value within the first 14 days, this implementation plan adheres to three strict engineering principles:

1. **Zero-Fluff Monolith First:** A single clean Python repository using `uv` (or `poetry`), `SQLAlchemy 2.0` / `SQLModel`, `FastAPI`, and `APScheduler`. No premature microservices, no Kafka, no distributed task broker overhead for MVP.
2. **Deterministic Data Pipeline:** The scraper saves raw HTML snapshots to PostgreSQL before touching any business logic. Even if parsers fail or the portal DOM shifts, zero data is lost.
3. **Decoupled Delivery Surface:** Deliver the initial product experience via a high-utility **Telegram Bot** before spending time building custom web frontends. A Telegram push alert with inline action buttons gives you an interactive decision surface immediately.

---

## 2. Target Repository Architecture & File Layout

```
mp-intelligence/
├── docker-compose.yml              # PostgreSQL 16 + pgvector + pg_trgm container
├── pyproject.toml                  # Dependencies managed via uv / poetry
├── .env.example                    # DB credentials, LLM keys, Telegram tokens
├── Makefile                        # Dev commands (lint, test, crawl, backfill)
│
├── src/
│   ├── __init__.py
│   ├── config.py                   # Pydantic BaseSettings (env variables)
│   ├── database.py                 # Async SQLAlchemy engine & session maker
│   │
│   ├── models/                     # Database Models (SQLAlchemy / SQLModel)
│   │   ├── raw.py                  # RawIngestionLog
│   │   ├── tender.py               # Tender, Buyer, LineItem, Award
│   │   ├── profile.py              # CompanyProfile, ProfileMatch
│   │   └── actions.py              # UserAction, FeedbackLog
│   │
│   ├── scraper/                    # Ingestion & Web Scraping Engine
│   │   ├── client.py               # WAF-resilient HTTP client (curl_cffi / persistent session)
│   │   ├── listing_spider.py       # Crawls /bdc/entreprise/consultation/ (?pageSize=50)
│   │   ├── detail_spider.py        # Fetches /bdc/entreprise/consultation/show/{id}
│   │   ├── results_spider.py       # Crawls /bdc/entreprise/consultation/resultat
│   │   ├── attachment_worker.py    # Downloads ZIPs, unpacks, runs OCR (tesseract)
│   │   └── parser.py               # Pure BeautifulSoup4 / lxml DOM extraction functions
│   │
│   ├── profiles/                   # Profile Configuration Engine
│   │   ├── schema.py               # Pydantic validator for YAML profiles
│   │   ├── loader.py               # Loads & validates profiles from /configs/
│   │   └── configs/
│   │       ├── software_data.yaml  # Hamza's primary company profile
│   │       └── cctv_security.yaml  # Benchmark physical security profile
│   │
│   ├── engine/                     # Matching, Scoring & Intelligence
│   │   ├── hard_filters.py         # Stage 1: Fast SQL binary elimination
│   │   ├── lexical_ranker.py       # Stage 2: French/Arabic BM25 & keyword matcher
│   │   ├── vector_embedder.py      # Stage 3: pgvector cosine similarity & line-item coverage
│   │   ├── llm_judge.py            # Stage 4: Structured LLM evaluator (Gemini / OpenAI)
│   │   └── pricing_helper.py       # Computes floor price & historical comparable corridor
│   │
│   ├── scheduler/                  # Ingestion & Alerting Jobs
│   │   └── jobs.py                 # APScheduler hourly cron & daily results sync
│   │
│   ├── alerts/                     # Notification Dispatcher
│   │   ├── telegram_bot.py         # Interactive Decision Card bot & callback handler
│   │   └── formatter.py            # Formats 60-second Decision Card text & markdown
│   │
│   └── api/                        # Lightweight FastAPI Surface
│       ├── main.py                 # App entrypoint
│       └── routes/
│           ├── feed.py             # Filtered & ranked tender endpoints
│           └── feedback.py         # User thumbs-up/down & action tracking
│
├── tests/
│   ├── fixtures/                   # Golden HTML fixtures captured from portal
│   │   ├── listing_page_1.html     # Real active listing HTML
│   │   ├── detail_409807.html      # Real detail page with line items
│   │   └── results_page_1.html     # Real results page with award cards
│   ├── test_client.py              # WAF navigation tests
│   ├── test_parsers.py             # Regression tests against golden fixtures
│   ├── test_scoring.py             # Match engine verification on test tenders
│   └── test_profiles.py            # Profile schema validation tests
```

---

## 3. Milestones, Deliverables & Acceptance Criteria

```mermaid
gantt
    title Moroccan Procurement Intelligence System — Implementation Timeline
    dateFormat  YYYY-MM-DD
    section Foundation
    M0: Setup & Infra & Fixtures        :done, m0, 2026-11-20, 2d
    M1: Active BDC Scraping Pipeline    :active, m1, after m0, 3d
    section Core Intelligence
    M2: Results Archive & Join Engine   :m2, after m1, 2d
    M3: Attachments & Multilingual OCR  :m3, after m2, 2d
    M4: Profile Engine & Embeddings     :m4, after m3, 2d
    M5: 4-Stage Scoring Cascade         :m5, after m4, 3d
    section Product Delivery
    M6: Telegram Alert Bot & Decision Card :m6, after m5, 2d
    M7: Web Feed & Active Learning      :m7, after m6, 3d
    M8: Strategic Intelligence & Marchés:m8, after m7, 4d
```

### Milestone 0: Infrastructure, Database & Golden Fixtures (Days 1–2)
* **Goal:** Zero-friction local development environment with complete database schema and offline testing assets.
* **Deliverables:**
  1. `docker-compose.yml` deploying PostgreSQL 16 with `pgvector` and `pg_trgm`.
  2. Alembic migration scripts initializing the complete schema from [`ARCHITECTURE.md`](file:///c:/Users/7mza/mp/ARCHITECTURE.md#62-postgresql-ddl-for-mvp).
  3. Golden fixture suite in `tests/fixtures/` capturing 3 listing pages, 5 detail pages (including CCTV #409807), and 3 results pages.
* **Acceptance Criteria:**
  * Running `pytest tests/` passes 100% offline without hitting live network.
  * Database cleanly executes all DDL and can insert/query vector embeddings and JSONB structures.

---

### Milestone 1: Resilient Active BDC Ingestion Worker (Days 3–5)
* **Goal:** High-speed, rate-controlled crawler that fetches all active consultations and parses structured line items into PostgreSQL.
* **Deliverables:**
  1. `src/scraper/client.py`: Python `curl_cffi` client with TLS/JA3 impersonation, persistent cookie jar (`TS01c367b8`, `DCOOKIE`), and 1.0s polite rate limiter.
  2. `src/scraper/listing_spider.py`: Crawls `/bdc/entreprise/consultation/?search_consultation_entreprise[pageSize]=50&page={n}`.
  3. `src/scraper/detail_spider.py`: Fetches detail pages (`/show/{id}`) and extracts metadata, buyer hierarchy, dates, and the complete line-item table (`line_items`).
  4. Raw snapshotting: every HTTP response stored in `raw_ingestion_log` with SHA-256 hash.
* **Acceptance Criteria:**
  * Pipeline crawls all ~1,600 active portal notices across ~32 pages in $< 60$ seconds.
  * Ingestion achieves $> 99\%$ parse success rate across visible fields (title, deadline, buyer, line items).
  * 0 HTTP 403 / 429 WAF blocks encountered.
  * Duplicate crawls execute idempotently without corrupting or duplicating existing records.

---

### Milestone 2: Historical Results Archive & Natural-Key Joining (Days 6–7)
* **Goal:** Ingest historical award cards and link them to active/closed consultations to establish market pricing benchmarks.
* **Deliverables:**
  1. `src/scraper/results_spider.py`: Crawls `/bdc/entreprise/consultation/resultat`.
  2. Ingestion pipeline capturing status (`Attribué` / `Infructueux`), publication date, reference, buyer name, devis received count, winner name, and total TTC amount.
  3. Compound natural key joiner linking `awards` to `tenders` on `(buyer_slug, clean_reference, publication_year)` with trigram fallback.
* **Acceptance Criteria:**
  * Successful backfill of latest ~10,000 awards into the `awards` table.
  * Compound key join links $> 75\%$ of recent awards back to captured consultation detail records.
  * Buyer win-rate and devis-count statistics queryable in $< 50$ms.

---

### Milestone 3: Attachment Pipeline & Multilingual OCR (Days 8–9)
* **Goal:** Automated downloading and text extraction of `.zip` tender dossiers.
* **Deliverables:**
  1. `src/scraper/attachment_worker.py`: Downloads ZIP from `/download/{portal_id}/{file_id}`.
  2. Extraction module with dual-pass reading:
     * Fast path: `pdfplumber` for digital PDFs.
     * Slow path: `pytesseract` with `fra+ara` models for scanned bitmap pages.
  3. Extracted text stored in database and indexed for lexical search.
* **Acceptance Criteria:**
  * Successfully downloads and extracts tender archive for sample #409807.
  * OCR processes a 3-page scanned Moroccan communal specification in $< 4$ seconds on standard CPU.
  * Non-blocking execution: attachment processing runs asynchronously without stalling listing crawls.

---

### Milestone 4: Multi-Industry Profile Engine & Catalog Embeddings (Days 10–11)
* **Goal:** Declarative YAML profile validator and pre-computed vector space for target industries.
* **Deliverables:**
  1. `src/profiles/schema.py`: Pydantic model enforcing YAML profile schema rules.
  2. Two validated production profile configs:
     * `software_data.yaml` (Hamza's custom software & data engineering business).
     * `cctv_security.yaml` (Benchmark CCTV supply & installation business).
  3. Profile catalog embedding generator using OpenAI `text-embedding-3-small` (or local multilingual E5).
* **Acceptance Criteria:**
  * Profiles load and validate strictly; invalid syntax or missing required fields raise immediate exceptions.
  * Embedded catalog vectors stored in `company_profiles` metadata and indexed via `pgvector`.

---

### Milestone 5: 4-Stage Matching & Scoring Cascade (Days 12–14)
* **Goal:** Precision scoring engine that filters noise and produces the calibrated "~95% alignment" metric.
* **Deliverables:**
  1. `Stage 1`: SQL-level hard gate filtering (status, deadline, location, amount).
  2. `Stage 2`: Lexical BM25 and keyword match using PostgreSQL French dictionary and trigram indices.
  3. `Stage 3`: Vector cosine similarity and **Line-Item Coverage Calculation** across extracted bill of materials.
  4. `Stage 4`: LLM Judge evaluator using Gemini 1.5 Flash / GPT-4o-mini with structured JSON output schema.
  5. Price helper calculating $P_{\text{floor}}$ and historical market winning corridor.
* **Acceptance Criteria:**
  * CCTV tender #409807 scored against `cctv_security.yaml` produces score $\ge 90\%$ with 100% line-item coverage.
  * CCTV tender #409807 scored against `software_data.yaml` produces score $< 20\%$ and is rejected at Stage 1/2.
  * Average end-to-end scoring cost is $< \$0.002$ per evaluated tender.

---

### Milestone 6: Gmail SMTP Decision Card & Real-Time Alerts (Days 15–16)
* **Goal:** Immediate user-facing product delivery directly to Hamza's Gmail inbox.
* **Deliverables:**
  1. `src/alerts/email_dispatcher.py`: Gmail SMTP dispatcher using STARTTLS (`smtp.gmail.com:587`).
  2. Formatted 60-Second HTML Decision Card message generator with mobile-responsive design, status badges, countdown clock, and line-item BOM table.
  3. Deep-link button: `[ 📄 Consulter l'Avis Officiel sur le Portail ]`.
  4. Plain-text fallback for legacy email clients.
* **Acceptance Criteria:**
  * When a high-alignment offer (score $\ge 80\%$) is ingested, a responsive HTML Decision Card arrives in Gmail within 120 seconds of publication.
  * Direct portal links resolve correctly to `/bdc/entreprise/consultation/show/{portal_id}`.

---

### Milestone 7: Web Feed & Active Learning Feedback Loop (Completed)
* **Goal:** Centralized operational dashboard for review and error analysis.
* **Deliverables:**
  1. `src/api/main.py`: FastAPI server delivering the single-page responsive procurement dashboard (Tailwind + Alpine.js).
  2. `src/api/routes/feed.py`: REST endpoints (`/api/feed`, `/api/tenders/{id}`, `/api/profiles`, `/api/actions`).
  3. Interactive 60-Second Decision Card modal with full line-item BOM breakdown.
  4. Founder action tracker recording Shortlist/Applied/Reject feedback into `user_tender_actions`.

---

### Milestone 8: Strategic Intelligence & Marchés Publics Extension (Days 20–24)
* **Goal:** Expand scope to large-scale *marchés publics* (AO) and predictive buyer analytics.
* **Deliverables:**
  1. Integration of main portal tender scraper (`index.php?page=entreprise.EntrepriseHome`).
  2. Buyer Seasonality & Budget Exhaustion Radar (Q4 spend surge prediction).
  3. Competitor Intelligence Dossiers (historical win rates, price discounting patterns).
* **Acceptance Criteria:**
  * Pipeline seamlessly absorbs formal AO notices into the existing canonical `tenders` schema.
  * Competitor report reveals top 5 winning suppliers for any given public buyer.

---

## 4. Concrete "Next 14 Days" Daily Execution Plan

This day-by-day checklist guides your first two weeks of building:

### Week 1: Foundation & Bulletproof Ingestion

* [ ] **Day 1 (Setup & Storage):**
  * Initialize git repository: `git init mp-intelligence`.
  * Create `docker-compose.yml` with PostgreSQL 16 + pgvector. Run `docker compose up -d`.
  * Write Alembic migration script executing the DDL from [`ARCHITECTURE.md`](file:///c:/Users/7mza/mp/ARCHITECTURE.md#62-postgresql-ddl-for-mvp).
  * Verify extensions: `SELECT * FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');`.
* [ ] **Day 2 (Fixture Harvesting & Client Proof):**
  * Use curl or Python script to save 3 real listing pages and 5 detail pages (including ID 409807) to `tests/fixtures/`.
  * Implement `src/scraper/client.py` using `curl_cffi` with browser TLS fingerprinting and session cookie persistence.
  * Write unit test confirming client receives HTTP 200 from live portal without WAF blocks.
* [ ] **Day 3 (Listing Parser & Database Upsert):**
  * Write `src/scraper/parser.py`: extract listing fields (`portal_id`, `reference`, `title`, `buyer_name`, `deadline_at`, `status`).
  * Implement `src/scraper/listing_spider.py` with pagination loop (`pageSize=50`).
  * Implement idempotent database upsert using SQLAlchemy `on_conflict_do_update`.
* [ ] **Day 4 (Detail Page & Line-Item Table Extraction):**
  * Implement `detail_spider.py`: fetch `/bdc/entreprise/consultation/show/{id}`.
  * Parse `#article--table--body`: extract `item_order`, `designation`, `technical_specs`, `unit`, `quantity`, `tva_rate`.
  * Store raw page in `raw_ingestion_log`; persist parsed records in `line_items`.
* [ ] **Day 5 (End-to-End Active Ingestion Test):**
  * Wire scheduler to crawl all active BDC pages sequentially.
  * Verify database populated with ~1,600 tenders and ~6,000+ line items.
  * Benchmark performance: full active crawl must finish in $< 90$ seconds at 1 req/sec.
* [ ] **Day 6 (Results Archive Spider):**
  * Implement `src/scraper/results_spider.py` targeting `/bdc/entreprise/consultation/resultat`.
  * Parse `<article class="bdc-card">`: extract reference, title, buyer, winner, amount TTC, devis count.
  * Backfill latest 5,000 historical award records into `awards`.
* [ ] **Day 7 (Award-to-Consultation Joining Logic):**
  * Implement natural key compound joiner on `(buyer_slug, clean_reference, year)`.
  * Measure match rate between awards and captured consultations.
  * Implement fallback trigram similarity matching for messy references.

### Week 2: Matching Engine, LLM Judge & Telegram Delivery

* [ ] **Day 8 (Attachment Downloader & Fast-Path PDF):**
  * Implement `attachment_worker.py`: download ZIP from `/download/{portal_id}/{file_id}`.
  * Extract archive in-memory using `zipfile`; inspect enclosed PDF files.
  * Implement fast-path text extraction via `pdfplumber`.
* [ ] **Day 9 (OCR Fallback for Scanned Tenders):**
  * Integrate `pytesseract` with `fra+ara` models for scanned bitmaps.
  * Test OCR extraction against Moroccan commune scanned stamps and Arabic text.
  * Persist extracted text in `tenders.description` or attachment table.
* [ ] **Day 10 (Profile Engine & Vector Setup):**
  * Implement Pydantic schema in `src/profiles/schema.py`.
  * Create `configs/software_data.yaml` and `configs/cctv_security.yaml`.
  * Generate embeddings for catalog SKUs using `text-embedding-3-small` and store in PostgreSQL.
* [ ] **Day 11 (Cascade Scoring Implementation):**
  * Implement Stage 1 (SQL hard gates: deadline $\ge 24$h, status = active, geographic filter).
  * Implement Stage 2 (French/Arabic BM25 lexical screen).
  * Implement Stage 3 (pgvector cosine similarity + Line-Item Coverage percentage calculation).
* [ ] **Day 12 (LLM Judge Integration):**
  * Implement Stage 4: `src/engine/llm_judge.py` using Gemini 1.5 Flash (or OpenAI) with structured JSON output.
  * Feed top candidate tenders (Stage 3 score $> 65$) to LLM Judge.
  * Extract deliverability analysis, red flags, and executive summary.
* [ ] **Day 13 (Telegram Bot & Decision Card Formatter):**
  * Create Telegram bot via BotFather; save token in `.env`.
  * Implement `src/alerts/telegram_bot.py` and `formatter.py` to format the 60-Second Decision Card.
  * Implement inline action buttons: `[ ⭐ Shortlist ]`, `[ 📄 Open Portal ]`, `[ ❌ Skip ]`.
* [ ] **Day 14 (End-to-End Validation & Live Polling):**
  * Set APScheduler to poll live portal hourly (08:00 to 18:00 GMT+1).
  * Validate that new matching BDCs trigger instant Telegram Decision Cards on your phone.
  * Review first 20 alerts, click inline buttons, and verify actions recorded in `user_tender_actions`.

---

## 5. Data Quality, Golden Fixtures & Testing Framework

To ensure system reliability without manual monitoring, the test harness enforces three automated test suites:

### 5.1 Golden Fixture Regression Tests (`pytest tests/test_parsers.py`)
* Never test parsers against live network endpoints during continuous integration.
* Every parser function operates on static, committed HTML files in `tests/fixtures/`.
* *Test Assertions:*
  1. `test_parse_active_listing_extracts_50_items()`
  2. `test_parse_cctv_detail_extracts_exact_4_line_items_and_zip_link()`
  3. `test_parse_results_extracts_winner_amount_and_devis_count()`
  4. `test_arabic_text_normalization_preserves_characters()`

### 5.2 Real-Time Data Quality Alarms (`src/scraper/observability.py`)
During live hourly crawls, the system computes automated health metrics. A Telegram administrative alert is raised if:
* Parse success rate drops below $95\%$ across any required field.
* Zero new consultations are detected over a 24-hour business-day period (indicates possible portal endpoint change).
* Crawler encounters 2 consecutive HTTP 403 / 429 status codes (indicates WAF challenge or IP rate limit).
* Database write latency exceeds 500ms.

---

## 6. Risk Register & Solo-Founder Mitigation Strategies

| Risk Description | Probability | Impact | Early Warning Indicator | Actionable Mitigation Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **F5 WAF Blocks Scraper IP** | Medium | High | HTTP 403 Forbidden on listing requests. | Rotate residential proxy fallback; enforce strict 1.0s jittered delay; reuse persistent browser cookies (`TS01c367b8`); maintain realistic TLS/JA3 client fingerprint via `curl_cffi`. |
| **Portal Changes DOM Structure** | High | High | Detail parser returns 0 line items on active pages. | Golden fixture regression tests detect DOM breakage immediately; raw HTML snapshots in `raw_ingestion_log` allow re-parsing historical data once parser is updated. |
| **BDC Results Lack Direct IDs** | Confirmed [VERIFIED] | Medium | Results cards do not contain `/show/{id}` links. | Join results to consultations using compound natural key `(buyer_slug, clean_reference, year)` with secondary trigram title matching. |
| **LLM API Costs Balloon** | Low | Medium | Daily token expenditure exceeds budget. | Strict 4-stage cascade ensures only top ~3-5% of tenders reach LLM Judge; use high-efficiency model (Gemini 1.5 Flash); cache LLM evaluations on content hash. |
| **Founder Bus Factor / Burnout** | High | Critical | Manual bid review takes $> 2$ hours per day. | **60-Second Decision Card** delivered via Telegram enables complete go/no-go decisions in under 1 minute per offer; automated draft quote export eliminates manual clerical work. |

---

## 7. Cost & Infrastructure Budget (MVP Stage)

| Component | Provider / Technology | Monthly Cost (USD) | Scaling Threshold |
| :--- | :--- | :--- | :--- |
| **Compute & Database** | Hetzner / DigitalOcean (2 vCPU, 4GB RAM, 80GB SSD) | \$12.00 / month | Easily handles PostgreSQL, scraper, and web backend up to 500,000 tenders. |
| **WAF / Residential Proxies** | Direct connection (fallback: Webshare / BrightData) | \$0.00 – \$10.00 / month | Direct connection works with `curl_cffi`; fallback proxy only if IP blocked. |
| **Embeddings API** | OpenAI (`text-embedding-3-small`) | ~\$0.50 / month | Pre-embedding company catalogs and active tenders costs pennies at 1,600 tenders/mo. |
| **LLM Judge API** | Google Gemini 1.5 Flash / OpenAI GPT-4o-mini | ~\$3.00 – \$6.00 / month | ~50 evaluations/day $\times$ 30 days = 1,500 evaluations $\times$ \$0.002. |
| **Alert Delivery** | Telegram Bot API | \$0.00 (Free) | Unlimited push messages and interactive callbacks. |
| **Domain & SSL** | Cloudflare + Namecheap | \$1.00 / month | Standard domain management. |
| **Total Estimated Run Rate**| — | **~\$16.50 – \$29.50 / mo** | Sustainable indefinitely for a solo technical founder. |

---

*End of Engineering Implementation Plan. Ready for execution starting with Milestone 0 and Day 1 tasks.*

