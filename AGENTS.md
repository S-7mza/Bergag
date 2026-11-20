# AI Agent Operational Guide (`AGENTS.md`)
> **Target:** Autonomous AI Agents (Antigravity, Cursor, Claude Code, Copilot)  
> **Efficiency Mandate:** Minimize token consumption and execution latency. Use this file as your root mental model. Do **not** ingest the monolithic `ARCHITECTURE.md` (~71 KB) unless specifically requested. Read modular topic guides in [`docs/`](./docs/README.md) on demand.

---

## 1. System in 30 Seconds

- **What:** Autonomous Moroccan Public Procurement Intelligence & Opportunity Engine (`marchespublics.gov.ma` / TGR).
- **Core Domain:** Monitors **Bons de Commande (BDC)** under Moroccan Decree No. 2-22-431 (Article 91, ≤ 500,000 MAD TTC annual cap per buyer line) and formal **Appels d'Offres (AO)**.
- **Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (`asyncpg` + `asyncio`), PostgreSQL 16 (`pgvector`), Alembic, BeautifulSoup4/lxml, `httpx`/`curl_cffi`, Pytest, Tailwind CSS + Alpine.js.

---

## 2. Fast Command Cheat Sheet

Always execute from the repository root (`c:\Users\7mza\mp`):

| Action | Command | Expected Output / Notes |
| :--- | :--- | :--- |
| **Run all tests** | `pytest` | 46 tests passing in < 2s (via `pytest.ini`) |
| **Run single test** | `pytest tests/test_parsers.py -v` | Instant execution of specific module tests |
| **Start dev server** | `uvicorn src.api.main:app --reload --port 8000` | FastAPI dashboard at `http://localhost:8000` |
| **Run DB migrations** | `alembic upgrade head` | Migrates PostgreSQL database schema |
| **Create migration** | `alembic revision --autogenerate -m "description"` | Generates version in `alembic/versions/` |
| **Format & lint check**| `ruff check .` or `python -m py_compile <file>` | Fast syntax verification |

---

## 3. Directory Layout & Mental Map

```
mp/
├── AGENTS.md                  # <-- You are here: Root agent instructions (< 1.5k tokens)
├── pytest.ini                 # Configured with pythonpath = . for zero-friction testing
├── docs/                      # Modular progressive disclosure documentation
│   ├── README.md              # Documentation navigation index & topic selector
│   ├── architecture/          # System overview, cascade scoring, and data models
│   ├── modules/               # Scraper & WAF, attachment OCR worker, API & analytics
│   ├── domain/                # Moroccan procurement legal framework (Decree 2-22-431)
│   └── runbooks/              # Testing, database operations, development runbooks
├── .agents/skills/            # Antigravity progressive disclosure skills
│   ├── procurement-pipeline/  # Runbook skill for ingestion & scoring pipeline
│   └── radar-analytics/       # Runbook skill for Buyer & Competitor radar
├── src/
│   ├── alerts/                # Email (Gmail SMTP) & Webhook notification dispatchers
│   ├── api/                   # FastAPI application, auth/RBAC, and route handlers
│   ├── config/                # Pydantic BaseSettings (`settings.py`) loading `.env`
│   ├── database/              # Async SQLAlchemy engine & session factory (`session.py`)
│   ├── engine/                # Cascade scoring, Buyer Radar, Competitor Radar, Pipeline
│   ├── models/                # SQLAlchemy models (Tender, Buyer, LineItem, Award, Batch, User)
│   ├── profiles/              # Multi-industry YAML profiles (`software_data.yaml`, `cctv_security.yaml`)
│   ├── scheduler/             # APScheduler jobs for periodic crawling & reconciliation
│   └── scraper/               # WAF-resilient HTTP client, spiders (Listing, Detail, Results, AO)
└── tests/                     # Pytest suite with offline HTML fixtures in `tests/fixtures/`
```

---

## 4. Architectural Rules & Invariants

1. **Progressive Disclosure:** Never load large markdown files into context. If you need details on a specific component, read only the corresponding file in [`docs/`](./docs/README.md).
2. **Async SQLAlchemy 2.0:** Always use modern 2.0 syntax (`select()`, `scalar_one_or_none()`, `scalars().all()`) and async sessions via `async with async_session_factory() as session:`. Never use legacy 1.x query syntax (`session.query()`).
3. **Compound Natural Keys:** Public procurement consultations are indexed and joined using `compound_natural_key`: `"{buyer_slug}:{clean_reference}:{publication_year}"`.
4. **Scraper & WAF Resilience:** The portal uses F5 BIG-IP ASM. Always reuse persistent cookies (`TS01c367b8`, `DCOOKIE`) via `PortalHttpClient`. Never bypass or hammer; adhere to polite crawl delays.
5. **Testing Discipline:** Always prefer offline HTML fixtures in `tests/fixtures/` (`active_listing_page1.html`, `detail_409807.html`, `results_page1.html`, `sample_409807.zip`) to keep tests deterministic and offline-capable.
6. **Data Dual-Persistence:** Critical batch records and user actions maintain dual persistence: PostgreSQL database tables with JSON fallback in `data/` (`batches_ledger.json`, `pipeline_ledger.json`).

---

## 5. Topic Documentation Index

Before exploring code blindly, open the exact guide you need:
- [System Architecture & Flow](./docs/architecture/system-overview.md)
- [4-Stage Cascade Scoring Engine](./docs/architecture/scoring-cascade.md)
- [Database Schema & ORM Models](./docs/architecture/data-models.md)
- [Scraper, WAF Navigation & Spiders](./docs/modules/scraper-and-waf.md)
- [Attachment Worker & OCR Pipeline](./docs/modules/attachment-worker.md)
- [FastAPI, RBAC & Market Radars](./docs/modules/api-and-analytics.md)
- [Moroccan Procurement Domain Rules (Decree 2-22-431)](./docs/domain/moroccan-procurement.md)
- [Testing & Development Runbook](./docs/runbooks/testing-and-dev.md)
