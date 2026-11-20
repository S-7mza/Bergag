# Scraper, WAF Navigation & Spiders

> **Scope:** HTTP client architecture, F5 BIG-IP WAF bypass, cookies, and spider implementations.  
> **Source Files:** [`src/scraper/client.py`](file:///c:/Users/7mza/mp/src/scraper/client.py), [`src/scraper/listing_spider.py`](file:///c:/Users/7mza/mp/src/scraper/listing_spider.py), [`src/scraper/detail_spider.py`](file:///c:/Users/7mza/mp/src/scraper/detail_spider.py), [`src/scraper/results_spider.py`](file:///c:/Users/7mza/mp/src/scraper/results_spider.py), [`src/scraper/ao_spider.py`](file:///c:/Users/7mza/mp/src/scraper/ao_spider.py)

---

## 1. WAF Navigation Architecture (F5 BIG-IP ASM)

The Treasury portal (`marchespublics.gov.ma`) is guarded by F5 BIG-IP Application Security Manager (ASM).

### Key Mechanics
1. **Cookie Lifecycle:** The WAF sets initial cookies (`TS01c367b8` and `DCOOKIE`) on the first GET request. If these cookies are not persisted across subsequent requests, the WAF returns `403 Forbidden` or challenge redirects.
2. **Client Implementation (`PortalHttpClient`):**
   - Built on `httpx.AsyncClient` with browser TLS fingerprint emulation.
   - Maintains an in-memory cookie jar persisting session tokens across requests.
   - Handles automatic retry with exponential backoff on transient errors (tenacity).
   - Polite crawling: default rate limit is 1.0s between requests (`SCRAPER_RATE_LIMIT_SECONDS`).

---

## 2. Spider Inventory

| Spider | Target Endpoint | Key Responsibility | Optimization |
| :--- | :--- | :--- | :--- |
| `ListingSpider` | `/bdc/entreprise/consultation/?page={p}` | Ingests active BDC notices | Injects `search_consultation_entreprise[pageSize]=50` to retrieve 50 items/page instead of 10, reducing requests by 80%. |
| `DetailSpider` | `/bdc/entreprise/consultation/show/{id}` | Extracts full tender details & line items | Parses Bootstrap 5 `.accordion-item` elements for Article designations, quantities, units, and specs. |
| `ResultsSpider` | `/bdc/entreprise/consultation/resultat` | Ingests historical award records | Normalizes references with `clean_procurement_reference()` and computes compound natural keys. |
| `AOSpider` | `/index.php?page=entreprise.EntrepriseAdvancedSearch` | Ingests formal Appels d'Offres (> 500k MAD) | Extracts formal tender notices and budget lines. |

---

## 3. Parsing Line Items from Bootstrap 5 Accordions

Inside [`src/scraper/parser.py`](file:///c:/Users/7mza/mp/src/scraper/parser.py):
- Articles are enclosed in `.accordion-item` cards.
- The accordion button contains the article number and title.
- Inside `.accordion-body`, key-value fields are extracted:
  - *Quantité* (`quantity`)
  - *Unité* (`unit`: U, Forfait, Mètre, etc.)
  - *Spécifications techniques* (`technical_specs`)
- Parsed into `LineItem` ORM entities and fed directly to Stage 3 BOM matching.
