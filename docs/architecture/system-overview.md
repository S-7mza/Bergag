# System Architecture & Pipeline Flow

> **Scope:** High-level topology, end-to-end data lifecycle, and operational sequence.  
> **Source Files:** [`src/scraper/ingestion_service.py`](file:///c:/Users/7mza/mp/src/scraper/ingestion_service.py), [`src/engine/batch_manager.py`](file:///c:/Users/7mza/mp/src/engine/batch_manager.py), [`src/scheduler/jobs.py`](file:///c:/Users/7mza/mp/src/scheduler/jobs.py)

---

## 1. End-to-End Ingestion & Decision Flow

```mermaid
flowchart TD
    subgraph Portal ["Portail Marchés Publics (TGR)"]
        WAF["F5 BIG-IP WAF & Cookies (TS01c367b8, DCOOKIE)"]
        ListingEndpoint["/bdc/entreprise/consultation/?pageSize=50"]
        DetailEndpoint["/bdc/entreprise/consultation/show/{id}"]
        ResultsEndpoint["/bdc/entreprise/consultation/resultat"]
    end

    subgraph Scraper ["Scraper & Ingestion Layer (src/scraper)"]
        Client["PortalHttpClient (httpx/curl_cffi)"]
        LSpider["ListingSpider"]
        DSpider["DetailSpider"]
        RSpider["ResultsSpider"]
        AWorker["AttachmentWorker (PDF / DOCX / OCR)"]
        RawLog["RawIngestionLog (PostgreSQL Snapshot)"]
    end

    subgraph Engine ["4-Stage Cascade Engine (src/engine)"]
        S1["Stage 1: Hard Binary Filters (Deadline >= 24h, Active)"]
        S2["Stage 2: Lexical Matcher & Negative Vetoes"]
        S3["Stage 3: Line-Item BOM Catalog Coverage %"]
        S4["Stage 4: LLM Judge (Feasibility, Risks, Pricing Floor)"]
    end

    subgraph Dispatch ["Alerts & Delivery (src/alerts)"]
        Email["Gmail SMTP Dispatcher (60s Decision Card)"]
        Webhook["Webhook Dispatcher (JSON Payload)"]
    end

    subgraph Delivery ["Presentation & Analytics (src/api)"]
        API["FastAPI App (:8000)"]
        Dash["Responsive Dashboard (Tailwind + Alpine.js)"]
        Radar["Market Radar (Buyer Velocity & Competitors)"]
    end

    WAF --> Client
    Client --> LSpider & DSpider & RSpider
    LSpider --> RawLog
    DSpider --> RawLog & AWorker
    RawLog --> S1
    S1 -->|Pass| S2
    S2 -->|Pass| S3
    S3 -->|Pass| S4
    S4 -->|Score >= 80%| Email & Webhook
    S4 --> API --> Dash & Radar
```

---

## 2. Ingestion Pipeline Stages

1. **Discovery (`ListingSpider`):**
   - Queries `?pageSize=50` to fetch ~1,600 active notices across Morocco in ~32 requests.
   - Extracts: Portal ID, Reference, Buyer Name, Title, Category, Execution City, Publication & Deadline dates.
2. **Snapshot Persistence (`RawIngestionLog`):**
   - Persists raw HTML snapshots into PostgreSQL before parsing. If parser changes or DOM drifts, zero data is lost.
3. **Detail & Line-Item Extraction (`DetailSpider`):**
   - Parses Bootstrap 5 `.accordion-item` cards on `/show/{id}`.
   - Extracts: Article order, designation, unit, quantity, technical specifications.
4. **Attachment Extraction (`AttachmentWorker`):**
   - Downloads consultation ZIP archives.
   - Executes dual-pass text extraction (native `pdfplumber` -> scanned detection -> `tesseract` fallback with `fra` + `ara`).
5. **Cascade Scoring (`ScoringCascadeEngine`):**
   - Evaluates tender against declarative YAML profiles (`software_data.yaml`, `cctv_security.yaml`).
   - Yields an overall score (0–100%) and recommendation (`GO`, `CONSIDER`, `NO-GO`).
6. **Alert Dispatch (`EmailDispatcher` / `WebhookDispatcher`):**
   - Opportunities with score $\ge 80\%$ trigger immediate alerts within 120 seconds of publication.
