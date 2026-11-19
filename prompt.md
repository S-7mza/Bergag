# ROLE

You are a principal architect combining four skills: public-procurement domain expert (Morocco), data engineer (scraping + data modeling), applied-ML/search engineer (matching and scoring), and product strategist (B2B sales intelligence). Your job is NOT to write the scraper yet. Your job is to diagnose deeply, challenge my assumptions, and produce a rigorous architecture document, built step by step, for a tool that finds Moroccan public-procurement offers worth bidding on.

# MY CONTEXT

- I am Hamza, a technical founder (software, programming, data solutions) based in Morocco. Working languages: French, Arabic, English. Write the document in English and keep Moroccan/French/Arabic domain terms in their original form with an English gloss.
- Idea: a scraping and intelligence tool for the Moroccan public procurement portal (Portail Marocain des Marchés Publics, www.marchespublics.gov.ma, operated by the TGR).
- The portal has two big families of opportunities. Find and confirm the correct official naming: "bon de commande (BDC)" versus "marché public / appel d'offres (AO)", and map every procedure type (AO ouvert, AO restreint, concours, procédure négociée / marché négocié, accord-cadre, consultation architecturale, etc.). Also verify how the current regulation (decree 2-22-431 and its successors, in force as of today, 19 Nov 2026) defines the BDC regime, its amount thresholds, and its rules. Do not trust your memory on thresholds or legal details: verify them or mark them "to verify".
- Phase 1 scope: ACTIVE BDC only, starting from https://www.marchespublics.gov.ma/bdc/entreprise/consultation/?page=1 and following the pagination. Marchés/AO come later, but the architecture must be generic enough to absorb them without a redesign.
- The tool must serve different company types through configuration. My own profile: software, programming, and data solutions. Another profile: a company selling and installing security cameras (CCTV). For each profile, the tool must return only the offers that matter, each with a direct link and everything needed to decide, in one glance, "this offer is ~95% aligned with what I sell, here is why, here is what I must know to bid, and here is the price range I should ask."

# HOW YOU MUST WORK

1. Step by step, in a single living Markdown document (ARCHITECTURE.md). Build it phase by phase. At the end of each phase, show the new section, list the open questions, and STOP for my validation before continuing. Do not write all phases in one go.
2. Evidence discipline. Every statement about the portal, the law, or the data must carry a tag: [VERIFIED] (you observed it, with the URL or sample), [HYPOTHESIS] (plausible, needs a test), or [UNKNOWN]. Never invent field names, endpoints, thresholds, or page behavior.
3. If you can browse or fetch pages, do the recon yourself. If you cannot, say so immediately and give me a precise recon checklist and ask me for: 3 to 5 listing pages and 5 to 10 detail pages saved as HTML, a browser HAR export (network tab) of a listing visit, a detail visit, and a filtered search, and screenshots of the filters. Meanwhile, continue with clearly tagged hypotheses.
4. Challenge the status quo. In each phase include a section "Challenges to my assumptions" where you argue against my premise, propose alternatives, and recommend one with a trade-off table. Be direct. If scraping is not the best approach for some part, say so.
5. Prefer the simplest design that meets the requirements and can grow: a solo technical founder will build this. State what is MVP versus later. Every technology choice gets a short ADR (context, options, decision, consequences).
6. Keep a changelog and an "Open questions / decisions needed from Hamza" list at the top of the document.

# PHASES (execute in order, one per turn, wait for my "go" between phases)

## Phase 0: Reconnaissance of the portal (BDC first)

Produce a "Site Recon Report" covering:
- Legal/ethical frame: robots.txt, terms of use, what is public versus behind login, personal-data presence (contact names, emails, phones) and how to minimize it, safe crawl rate. Explicitly list what the tool must NOT do (no captcha bypass, no authentication circumvention, no automated bid submission, no hammering).
- Technical anatomy: how listing pages are rendered (server-side HTML versus JS/XHR), pagination mechanics and its total-page signal, sort order and its stability (does a new publication shift pages, causing missed or duplicate items?), available filters and their URL parameters, session/cookie/CSRF needs, anti-bot measures, encoding, date/time formats and timezone (Africa/Casablanca), Arabic and French content handling, how a unique identifier of an offer is exposed (reference, internal id, URL), and whether a detail page URL is stable and shareable.
- Field inventory: a table of every field visible on the listing and on the detail page (name as displayed, example value, type, nullability, listing vs detail, stability, value for a decision maker: high/medium/low). Expect things like reference, objet, acheteur public / organisme, lieu d'exécution, catégorie (travaux/fournitures/services), dates (publication, limite de remise, ouverture), articles/lots with quantities and units, attached documents, estimated amount, caution, contact, status. Verify all of it.
- Lifecycle: what states an offer goes through (published, modified, extended, cancelled, closed, awarded), where BDC results/awards are published, whether closed or past BDC and results are accessible, how long they remain visible, and whether amendments overwrite the original.
- Attachments: what documents exist (cahier des prescriptions, bordereau de prix, DQE, lettre de consultation, plans), formats (PDF, scanned images, DOC, XLS, ZIP), whether they are public without login, sizes, and the OCR need.
- Other portal sections worth mining beyond active BDC: past BDC and results, avis d'appel d'offres, résultats et PV d'ouverture des plis, programmes prévisionnels of buyers, avis rectificatifs, consultations architecturales, buyer directory, any RSS, open-data, API or email-alert features. Rank them by value to a bidder.
- Output a "Recon verdict": is HTTP scraping enough, is a headless browser needed, or is there a cleaner official channel? Include a risk rating of site-structure drift.

## Phase 1: Business and decision-maker diagnosis

- Model the bidder's decision as a funnel: Discover, Qualify (fit), Feasibility (can I legally and operationally bid), Price, Decide, Prepare, Submit, Learn. For each stage list the exact questions a decision maker asks and which data answers them.
- Define "interesting offer" rigorously: hard eligibility filters (category, zone, deadline remaining, mandatory documents or certifications, amount band, bid mode) versus soft fit signals (semantic match to offering, buyer reputation, payment reliability, recurrence, strategic value).
- Specific to BDC: explain how BDC competition works in practice (small amounts, short deadlines, typically price-driven award, often to the lowest compliant bid, frequent repeat buyers, line-item quotes). Derive what that implies for the data we need and for the tool's speed (freshness SLA).
- Classify every candidate data element into Must / Should / Nice with justification, and flag what is impossible to get from this portal.
- Deliver "decision card" requirements: the exact content of the one-page view that lets a user decide in under 60 seconds.
- Challenge: is "95% aligned" a meaningful notion? Propose a precise, testable definition (precision at top-K, calibrated probability that the user would mark the offer as "worth bidding"), and how we measure it.

## Phase 2: Data architecture

Design layered storage: raw, normalized, enriched, decision layer.
- Raw layer: immutable snapshots of listing and detail pages (HTML/JSON) and attachments with content hash, fetch metadata, parser version, so we can re-parse history without re-scraping.
- Normalized layer: a canonical, source-agnostic model that covers BDC and marchés/AO. Propose entities and relationships at least for: source, tender (with type and procedure), tender_version (to track amendments and deadline changes), lot, line_item (designation, quantity, unit, specs), buyer (organisme, hierarchy, type, city/region), location (Moroccan regions/provinces/cities normalized), category and classification (propose a taxonomy mapping, noting whether an official nomenclature or CPV-like code is used), document (type, hash, extracted text, language, OCR flag), award/result (winner, amount, date), and for later: supplier/competitor.
- Enriched layer: language detection (FR/AR/mixed), translation/normalization, extracted entities (brands, models, quantities, technical specs, certifications required, amounts, deadlines), embeddings, document text extraction.
- Decision layer: company_profile, profile_match (score, breakdown, reasons, red flags, evidence snippets), price_estimate (range, method, confidence, supporting comparables), user_action (viewed, shortlisted, applied, skipped, won, lost, reason), alert.
- Specify: primary and natural keys, dedup strategy, idempotent upserts, change-detection and versioning approach, soft deletes for expired/cancelled offers, how to represent unknown versus absent, provenance per field, timezone handling, indexing and full-text strategy (including French and Arabic analyzers).
- Provide DDL-level schema for the MVP tables, an ER diagram in Mermaid, and 2 to 3 sample records as JSON from real examples if available (tagged by evidence level).
- Recommend a storage stack with a staged path (for example embedded database first, then a server database with vector and full-text support) and justify it versus alternatives. Challenge: do we need a vector store, a warehouse, or a queue at all at this stage?
- Multi-tenant readiness: which tables are global (tenders) versus per-tenant (profiles, scores, actions).

## Phase 3: Ingestion and scraping architecture

- Pipeline design: discovery (listing crawl), fetch (detail), parse, validate, load, enrich, score, notify. Define each component's contract and failure modes.
- Scheduling: incremental versus full crawl, adaptive frequency (deadline-driven refresh: more frequent re-checks as the deadline approaches, to catch amendments), time-of-day patterns of publication, backfill strategy for history.
- Reliability: retries with backoff, politeness and rate limits, circuit breakers, resumable crawls, handling of pagination drift, detection of "the site changed" (schema/DOM drift alarms), parser versioning, and golden-file regression tests with saved HTML fixtures.
- Observability: metrics (new offers per run, parse success rate per field, freshness lag, attachment fetch success), logs, alerting, and a data-quality dashboard spec. Define data-quality rules (for example deadline must be in the future for active offers, reference uniqueness, required fields completeness) and what happens on violation.
- Attachment pipeline: download, type sniffing, text extraction, OCR for scans (Arabic and French), size limits, storage, and cost control.
- Technology recommendation with trade-offs (language, HTTP client versus headless browser, orchestration, storage, hosting) suited to a one-person team, with a "start tiny" version and an "at scale" version. Include rough cost and effort estimates.
- Challenge: should we scrape at all for the rest of the product, versus subscribing to the portal's own alert mechanisms, versus buying from an existing commercial tender aggregator, versus a hybrid? Provide an honest build/buy/hybrid analysis, including legal and maintenance risk.

## Phase 4: Company profile configuration (the multi-industry engine)

- Design a declarative profile config (YAML or JSON) that makes the tool industry-agnostic. Include: company identity and legal status, offering catalog (products/services with synonyms and FR/AR/EN keywords, brands carried, technical keywords, typical unit prices or cost + margin), negative keywords and exclusions, categories (travaux/fournitures/services), geographic coverage (regions/cities, travel radius), amount bands (min/max), deadline constraints (minimum days remaining), buyer whitelist/blacklist and buyer types, certifications/qualifications/classifications held, capacity limits (max concurrent contracts), required documents the company can provide (attestations fiscales, CNSS, RC, etc.), language preferences, alert channels and frequency, and scoring weights.
- Provide two complete example profiles: (a) software, programming and data solutions (Hamza), (b) CCTV supply and installation. For each, show 10 positive example offer titles, 10 negative or ambiguous ones, and the tricky edge cases (for example "maintenance informatique" for IT hardware versus software development, "vidéosurveillance" bundled inside a larger works contract).
- Explain a profile bootstrap flow: the user describes the business in plain language, an LLM proposes the config, the user edits it, and then the tool back-tests the config against already collected offers to show what it would have returned.
- Challenge: keywords versus taxonomy versus semantic profile. Recommend a hybrid and justify.

## Phase 5: Matching and scoring engine

- Design a cascade (cheap to expensive): (1) hard filters from the profile, (2) lexical match (BM25 or similar, with FR/AR normalization, stemming/lemmatization, synonym expansion), (3) semantic match (multilingual embeddings between offer text and the offering catalog), (4) LLM judge on the top-N only, producing structured output: fit score, requirement-by-requirement analysis, extracted must-haves, disqualifiers, missing information, quoted evidence from the source text, and a "why/why not" explanation. Specify prompts' structure, JSON output schema, guardrails against hallucination, caching, and cost per 1,000 offers.
- Line-item-level matching for BDC: match each article/line to the product catalog, compute coverage percentage (how much of the BDC I can actually supply), and detect "partial fit" or "bundle with items I cannot supply".
- Score composition: define sub-scores (relevance, eligibility, feasibility, commercial attractiveness, urgency, competition intensity), weights configurable per profile, a calibrated final probability, a confidence level, and explicit red flags.
- Evaluation plan: build a labeled set (I label 100 to 200 offers per profile via a simple thumbs up/down with reason), metrics (precision@K, recall of known-good offers, false-positive cost), an error-analysis loop, and active learning from user actions (applied, skipped, won, lost).
- Challenge: what accuracy is realistic given that BDC descriptions are often short and vague? Define the fallback behavior when the text is insufficient (flag "needs attachment analysis" and trigger deeper extraction).

## Phase 6: Pricing intelligence

- Define what price guidance a bidder needs and what data can support it: buyer's estimated amount if published, historical awards for similar objects and same buyer, winning bids and unit prices from results/PV pages, price dispersion, the company's own cost + margin from the profile, seasonality and inflation adjustments.
- Methods: comparable retrieval (similar past BDC and marchés), unit-price extraction and normalization (units, VAT HT/TTC, currency), a price range with confidence, a "probable winning price" band for price-driven awards, and a "floor price" computed from the user's cost and minimum margin. Be explicit about what cannot be estimated reliably and how the tool should say so instead of guessing.
- Verify whether historical award data for BDC is actually available on the portal, how far back, and in what form. If it is not, propose alternatives (accumulate our own history from day one, so start capturing results immediately).
- Challenge: is price estimation realistic for BDC with heterogenous items? Propose the minimum viable price helper and a roadmap to something better.

## Phase 7: Product surface and workflow

- Ranked feed with filters, saved searches, the decision card, direct deep link to the original offer, deadline countdown, document checklist ("what you need to submit"), watchlist, notes, status pipeline (new, reviewing, preparing, submitted, won, lost, skipped).
- Alerts: channels (email, Telegram, WhatsApp, Slack), digest versus real-time, deadline reminders, amendment alerts ("deadline extended", "offer cancelled", "documents changed").
- Exports and integrations (CSV, Google Sheets, CRM).
- Define the MVP surface (could be a simple dashboard or even a daily digest) versus later.
- Privacy and security: data minimization, tenant isolation, secrets, backups, and retention rules.

## Phase 8: Beyond the obvious: opportunity ideas from the portal

Think hard and propose, with value, feasibility, and data-requirement ratings, ideas such as (go beyond this list and rank by impact versus effort):
- Buyer intelligence: who buys what, how often, typical amounts, seasonality, payment and cancellation behavior, which buyers repeatedly issue BDC that fit my offer.
- Early-signal radar: programmes prévisionnels and recurring annual purchases to predict upcoming BDC and AO before publication.
- BDC to AO pipeline: spot buyers whose BDC volume suggests they will tender a larger marché.
- Competitor tracking: who wins what, at what price, win rates by buyer and category.
- Subcontracting and partnership opportunities hidden inside large marchés and works contracts.
- Market sizing and white-space analysis per profile (where demand exists that nobody serves well).
- Compliance and document readiness: checklist generation per offer, expiry tracking of the company's own attestations.
- Amendment and cancellation watcher.
- Bid/no-bid recommendation with expected value (probability of winning times margin minus preparation cost).
- Generation of draft quotation or administrative dossier skeletons (without automating submission).
- Cross-source enrichment (buyer websites, official gazette, other public datasets) if legally and technically sound.
For each idea state which tables and fields it requires, so that the Phase 2 schema already supports the high-value ones.

## Phase 9: Roadmap, risks, and acceptance criteria

- Milestones with deliverables and acceptance criteria, for example: M1 recon complete and field inventory validated; M2 active-BDC ingestion running reliably with raw storage; M3 normalized model with change tracking; M4 two profiles with filtering and scoring; M5 decision card and alerts; M6 pricing helper; M7 marchés/AO ingestion; M8 external-user readiness.
- KPIs: parse success rate per field, freshness lag (publication to ingestion), duplicate rate, precision@10 per profile, share of offers with complete decision data, time from alert to decision.
- Risk register: portal structure changes, blocking or legal exposure, data quality, attachment OCR quality, LLM cost and hallucination, scope creep, single-person bus factor. Mitigations for each.
- Final consolidated "Decision log" and "Next 14 days" plan.

# DOCUMENT FORMAT RULES

- One file, ARCHITECTURE.md, with: title, changelog, open-questions list, table of contents, then phases as sections.
- Use tables for field inventories and trade-offs, Mermaid for diagrams (system context, pipeline, ER model, offer lifecycle state machine), ADR blocks for decisions, and concrete schemas and examples (DDL, JSON, YAML) wherever a concept would otherwise be vague.
- Be dense and precise. No filler, no generic advice. Every recommendation must tie back to a decision a bidder has to make.

# START NOW

Begin with Phase 0 only. First tell me in 5 lines whether you can browse the portal yourself. If yes, perform the recon and deliver the Site Recon Report. If no, deliver the exact recon checklist and the list of samples you need from me, plus a clearly tagged hypothesis-based draft of the field inventory. Then stop and wait for my validation before Phase 1.