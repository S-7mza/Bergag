---
name: radar-analytics
description: >-
  Use this skill when querying, analyzing, testing, or updating Buyer Radar spending
  velocity (Decree 2-22-431 Article 91 cap), seasonality detection, and Competitor
  Radar supplier intelligence.
---

# Market Radar & Intelligence Analytics

This skill guides the agent through querying, validating, and testing strategic market intelligence metrics extracted from Moroccan public procurement data.

## Core Intelligence Domains

### 1. Buyer Radar (`src/engine/buyer_radar.py`)
- **Statutory Limit:** 500,000 MAD TTC annual BDC cap (Article 91 of Decree No. 2-22-431).
- **Velocity Metrics:**
  - `total_spent_mad`: Cumulative awarded BDC amount in current fiscal year.
  - `cap_percentage`: `(total_spent_mad / 500,000.0) * 100`.
  - `cap_warning`: Triggered when spend reaches $> 400,000$ MAD (signals impending formal Appel d'Offres).
- **Seasonality Index:** Monthly spend concentration identifying Q4 budget rushes.

### 2. Competitor Radar (`src/engine/competitor_radar.py`)
- Aggregates supplier awards across historical records (~340,000 awards).
- Computes:
  - Top winning suppliers by contract volume and aggregate MAD.
  - Average contract value (`avg_contract_mad`).
  - Competition density (`avg_competition_density`: mean number of competing quotes submitted).

## Operational Procedures

### 1. Testing Radar Logic & Endpoints

Run the dedicated analytics test suite:
```powershell
pytest tests/test_analytics.py -v
```
Validates:
- Spending velocity calculations and cap warnings.
- Monthly seasonality aggregation.
- Top competitor aggregation and filtering by title keyword.
- Fast execution of `/api/analytics/buyer-radar` and `/api/analytics/competitors`.

### 2. Testing Analytics Endpoints Locally

When the FastAPI server is running:
```powershell
# Query Buyer Radar spending velocity
Invoke-RestMethod -Uri "http://localhost:8000/api/analytics/buyer-radar?year=2026"

# Query Competitor Dossiers
Invoke-RestMethod -Uri "http://localhost:8000/api/analytics/competitors?limit=10"
```
