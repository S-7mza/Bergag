# Testing & Development Runbook

> **Scope:** Pytest commands, test fixture usage, database migrations, and local environment.  
> **Source Files:** [`pytest.ini`](file:///c:/Users/7mza/mp/pytest.ini), [`tests/`](file:///c:/Users/7mza/mp/tests/), [`alembic.ini`](file:///c:/Users/7mza/mp/alembic.ini), [`docker-compose.yml`](file:///c:/Users/7mza/mp/docker-compose.yml)

---

## 1. Running Tests with Pytest

All test paths and async loop configurations are defined in [`pytest.ini`](file:///c:/Users/7mza/mp/pytest.ini).

```powershell
# Run the entire test suite (46 tests, ~1.5s - 90s depending on live tests)
pytest

# Run fast unit & parser tests only (< 1 second)
pytest tests/test_parsers.py tests/test_profiles.py tests/test_results_spider.py -v

# Run scoring cascade tests
pytest tests/test_scoring_cascade.py -v

# Run API endpoint tests
pytest tests/test_api.py -v

# Run attachment and OCR tests
pytest tests/test_attachments.py -v
```

---

## 2. Test Fixture Strategy

Deterministic, offline testing is prioritized using real DOM snapshots in `tests/fixtures/`:
- `tests/fixtures/active_listing_page1.html`: 50-item active BDC listing page.
- `tests/fixtures/detail_409807.html`: Full consultation detail page with Bootstrap 5 `.accordion-item` line items.
- `tests/fixtures/results_page1.html`: Historical award results page with winning amounts.
- `tests/fixtures/sample_409807.zip`: Real consultation attachment archive.

When writing new parser or scoring tests, always use offline fixtures rather than calling external portals.

---

## 3. Database & Migrations (Alembic)

```powershell
# Apply all pending migrations to PostgreSQL
alembic upgrade head

# Create an automatic revision after modifying models in src/models/
alembic revision --autogenerate -m "add_feature_column"

# Rollback one migration
alembic downgrade -1
```

---

## 4. Local Development Environment

```powershell
# 1. Start PostgreSQL 16 + pgvector container
docker-compose up -d postgres

# 2. Run the FastAPI development server
uvicorn src.api.main:app --reload --port 8000

# 3. Access web dashboard & API docs
# Dashboard: http://localhost:8000
# Swagger:   http://localhost:8000/docs
```
