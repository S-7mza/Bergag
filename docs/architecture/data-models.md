# Database Schema & ORM Models

> **Scope:** PostgreSQL database tables, ORM relationships, compound keys, and data integrity.  
> **Source Files:** [`src/models/tender.py`](file:///c:/Users/7mza/mp/src/models/tender.py), [`src/models/raw.py`](file:///c:/Users/7mza/mp/src/models/raw.py), [`src/models/batch.py`](file:///c:/Users/7mza/mp/src/models/batch.py), [`src/models/user.py`](file:///c:/Users/7mza/mp/src/models/user.py), [`src/models/profile.py`](file:///c:/Users/7mza/mp/src/models/profile.py)

---

## 1. Entity-Relationship Model

```mermaid
erDiagram
    Buyer ||--o{ Tender : publishes
    Tender ||--o{ LineItem : contains
    Tender ||--o{ UserTenderAction : tracked_by
    User ||--o{ UserTenderAction : logs
    Buyer ||--o{ Award : historical_awards
    RawIngestionLog }|--|| Tender : raw_snapshot

    Buyer {
        uuid id PK
        string slug UK "Normalized unique buyer slug"
        string official_name
        string buyer_type "commune, ministere, organisme"
        string region
        string city
    }

    Tender {
        bigint portal_id PK "Official portal consultation ID"
        string source_type "bdc or ao"
        string reference "Reference (e.g., 04/2026/CUC)"
        string compound_natural_key UK "slug:clean_ref:year"
        uuid buyer_id FK
        text title
        string main_category "Fournitures, Services, Travaux"
        timestamp published_at
        timestamp deadline_at
        string status "active, annule, attribue"
        boolean attachment_available
    }

    LineItem {
        uuid id PK
        bigint tender_id FK
        int order_index
        text designation "Article name"
        string unit "U, Forfait, Mètre, Lot"
        numeric quantity
        text technical_specs
    }

    Award {
        uuid id PK
        bigint portal_id "Optional portal ID"
        string compound_natural_key INDEX
        string buyer_name_raw
        string winner_name "Supplier name"
        numeric amount_ttc "Total awarded MAD"
        int devis_received_count "Competition density"
        timestamp published_at
        string status "Attribué, Infructueux"
    }
```

---

## 2. Key Architectural Invariants

### 1. Compound Natural Key (`compound_natural_key`)
- **Problem:** The Moroccan public procurement portal does not expose persistent foreign keys between active consultations and historical awards tables.
- **Solution:** A deterministic compound natural key:
  $$\text{Key} = \text{buyer\_slug} : \text{clean\_reference} : \text{publication\_year}$$
- Generated via `compute_compound_ref_key()` in [`src/scraper/results_spider.py`](file:///c:/Users/7mza/mp/src/scraper/results_spider.py).

### 2. Immutable Raw Snapshots (`RawIngestionLog`)
- Before any parsing or normalization, full raw HTML is stored in `raw_ingestion_logs`.
- Enables retrospective reprocessing if DOM parsers are upgraded or bug fixes are applied.

### 3. Dual-Persistence for Operational State
- `IngestionBatch`: Stores crawl metrics, error logs, and card counts in PostgreSQL, with JSON file backup in `data/batches_ledger.json`.
- `UserTenderAction`: Founder pipeline state (Shortlisted, Chiffrage, Bidded, Won, Lost) mirrored in `data/pipeline_ledger.json`.
