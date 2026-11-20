# Documentation Hub & Agent Progressive Disclosure Index

> **Agent Instruction:** Read only the document that directly addresses your current task. Each modular guide is self-contained and concise (< 1,000 tokens) to minimize token consumption and inference latency.

---

## 1. Quick Task Locator ("Where to Look")

| If your task is... | Read this document | Size |
| :--- | :--- | :--- |
| **Understand overall system flow & components** | [`docs/architecture/system-overview.md`](./architecture/system-overview.md) | ~800 tokens |
| **Modify or debug the 4-stage scoring cascade** | [`docs/architecture/scoring-cascade.md`](./architecture/scoring-cascade.md) | ~900 tokens |
| **Inspect DB tables, models, or foreign keys** | [`docs/architecture/data-models.md`](./architecture/data-models.md) | ~900 tokens |
| **Update spiders or debug WAF cookie handling** | [`docs/modules/scraper-and-waf.md`](./modules/scraper-and-waf.md) | ~850 tokens |
| **Work on PDF, DOCX, or Tesseract OCR extraction**| [`docs/modules/attachment-worker.md`](./modules/attachment-worker.md) | ~700 tokens |
| **Modify FastAPI endpoints, RBAC, or Radar logic**| [`docs/modules/api-and-analytics.md`](./modules/api-and-analytics.md) | ~850 tokens |
| **Clarify Moroccan procurement laws (Decree 2-22-431)**| [`docs/domain/moroccan-procurement.md`](./domain/moroccan-procurement.md) | ~750 tokens |
| **Run tests, create migrations, or debug locally** | [`docs/runbooks/testing-and-dev.md`](./runbooks/testing-and-dev.md) | ~600 tokens |

---

## 2. Progressive Disclosure Architecture

```
docs/
├── README.md                      # Documentation Index (this file)
├── architecture/
│   ├── system-overview.md         # End-to-end topology & data lifecycles
│   ├── scoring-cascade.md         # Hard filters, Lexical matcher, BOM coverage, LLM Judge
│   └── data-models.md             # PostgreSQL tables, ORM relationships, compound keys
├── modules/
│   ├── scraper-and-waf.md         # PortalHttpClient, ListingSpider, DetailSpider, ResultsSpider
│   ├── attachment-worker.md       # Document unpacker, native PDF, Tesseract OCR fallback
│   └── api-and-analytics.md       # FastAPI routes, JWT/RBAC, Buyer Radar, Competitor Radar
├── domain/
│   └── moroccan-procurement.md    # Legal rules: Decree 2-22-431, BDC Art. 91, AO thresholds
└── runbooks/
    └── testing-and-dev.md         # Pytest commands, fixtures, migrations, env configs
```

---

## 3. Legacy Monolithic Documentation

The original architectural blueprint created during initial design is preserved for historical reference:
- [`ARCHITECTURE.md`](file:///c:/Users/7mza/mp/ARCHITECTURE.md) (71 KB historical monolithic reference).
- Note for AI Agents: **Do not** ingest `ARCHITECTURE.md` unless the user explicitly requests historical design notes. The modular docs in `docs/` reflect the actual working implementation.
