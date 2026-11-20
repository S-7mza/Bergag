---
name: procurement-pipeline
description: >-
  Use this skill when running, testing, debugging, or verifying the Moroccan public
  procurement ingestion spiders (Listing, Detail, Results, AO), batch reconciliation,
  and the 4-stage cascade scoring engine.
---

# Moroccan Public Procurement Ingestion & Scoring Pipeline

This skill guides the agent through operating and verifying the ingestion spiders and cascade scoring engine for `marchespublics.gov.ma`.

## Quick Architecture Reference

- **Spiders (`src/scraper/`):**
  - `ListingSpider`: Fetches active notices with `?pageSize=50`.
  - `DetailSpider`: Fetches `/show/{id}` and parses `.accordion-item` line items.
  - `ResultsSpider`: Fetches `/resultat` and computes compound natural keys.
- **Scoring Cascade (`src/engine/scoring_cascade.py`):**
  - Stage 1: Hard binary gates (deadline, category, status).
  - Stage 2: Lexical matching and negative keyword vetoes.
  - Stage 3: Line-item BOM catalog coverage percentage.
  - Stage 4: LLM Judge for qualitative risk and margin evaluation.

## Operational Procedures

### 1. Verifying Parser Integrity (Offline)

When testing or updating parser logic without hitting the live government portal:
```powershell
pytest tests/test_parsers.py -v
```
All parser tests load offline fixtures from `tests/fixtures/`. Ensure that:
- `line_items` list contains correct article designations, quantities, and units.
- `compound_natural_key` adheres to `{slug}:{clean_ref}:{year}`.

### 2. Testing the 4-Stage Scoring Cascade

To verify scoring against active profiles (`software_data.yaml` and `cctv_security.yaml`):
```powershell
pytest tests/test_scoring_cascade.py -v
```
Key assertions:
- CCTV tender matches CCTV profile with score $\ge 80\%$ (`GO`).
- CCTV tender is rejected by Software profile with score $0\%$ (`NO-GO`).
- Cancelled tender is rejected at Stage 1 before lexical or LLM inference.
- Negative veto keywords immediately abort evaluation with zero token cost.

### 3. Triggering Manual Ingestion Batch via API

To test batch ingestion through the local FastAPI server:
```powershell
# In PowerShell:
Invoke-RestMethod -Uri "http://localhost:8000/api/batches/trigger" -Method POST -Body '{"pages": 1}' -ContentType "application/json"
```
Verify batch metrics in `data/batches_ledger.json` or by querying `/api/batches`.
