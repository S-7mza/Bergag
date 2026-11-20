# FastAPI, RBAC & Market Radar Analytics

> **Scope:** Web endpoints, authentication & roles, and market intelligence radars.  
> **Source Files:** [`src/api/main.py`](file:///c:/Users/7mza/mp/src/api/main.py), [`src/api/routes/`](file:///c:/Users/7mza/mp/src/api/routes/), [`src/engine/buyer_radar.py`](file:///c:/Users/7mza/mp/src/engine/buyer_radar.py), [`src/engine/competitor_radar.py`](file:///c:/Users/7mza/mp/src/engine/competitor_radar.py)

---

## 1. API Route Structure

All endpoints run under FastAPI with automatic OpenAPI docs at `http://localhost:8000/docs`.

| Route Prefix | Module | Purpose | Access Control |
| :--- | :--- | :--- | :--- |
| `/api/auth` | `routes/auth.py` | JWT token issuing, user registration, role switcher | Public / Admin |
| `/api/tenders` | `routes/feed.py` | Active consultation feed, search, 60s decision modal | Viewer+ |
| `/api/pipeline` | `routes/feed.py` | Founder CRM pipeline (Shortlist, Chiffrage, Bid, Won) | Analyst+ |
| `/api/analytics`| `routes/analytics.py` | Buyer Radar (spend velocity) & Competitor Dossiers | Analyst+ |
| `/api/batches` | `routes/batches.py` | Ingestion batch ledger, gap analysis, reconciliation | Admin |
| `/api/crawler` | `routes/crawler.py` | Live portal crawler triggers & WAF status checks | Admin |

---

## 2. Market Intelligence Radar Logic

### Buyer Radar (`src/engine/buyer_radar.py`)
- **Statutory Cap Monitoring:** Moroccan Decree No. 2-22-431 (Article 91) caps annual BDC spend at **500,000 MAD TTC** per public buyer per budget line.
- **Velocity Tracking:** Identifies buyers whose cumulative BDC awards approach 500k MAD (e.g. > 400k MAD).
- **Predictive AO Signal:** An administration hitting its BDC ceiling is legally required to issue a formal Appel d'Offres (AO), signaling impending large contract releases.
- **Seasonality Index:** Calculates monthly expenditure concentration to pinpoint Q4 budget rush patterns.

### Competitor Radar (`src/engine/competitor_radar.py`)
- Analyzes ~340,000 historical award records (`awards` table).
- Computes metrics per supplier:
  - `total_wins`: Total awarded contracts.
  - `total_awarded_mad`: Aggregate contract value in MAD TTC.
  - `avg_contract_mad`: Mean contract size.
  - `avg_competition_density`: Average number of competing bidders per awarded consultation.

---

## 3. RBAC & Development Mode

- **Roles:** `admin` > `analyst` > `viewer`.
- **Development Switch:** When `ALLOW_ANONYMOUS_DEV_ADMIN = True` in `.env` or settings, requests without JWT headers default to an administrative role for friction-free local development.
