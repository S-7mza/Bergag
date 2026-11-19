# Phase 0: Site Recon Report (BDC section)

Portail Marocain des Marchés Publics, observed 19 Nov 2026. Prepared for Hamza.

**Can the portal be browsed?** Partly. The active BDC listing, one detail page, the results section and the last results page were fetched.

- The fetcher returns rendered text, not raw HTML or network traffic. Form parameters, XHR calls, cookies, headers, `robots.txt` and the DOM could not be seen.
- Everything below is tagged \[VERIFIED\] (observed on 19 Nov 2026), \[HYPOTHESIS\] or \[UNKNOWN\].
- The last section lists the samples needed to close the gaps.

## 1. Naming (what the portal actually calls things)

- &#91;VERIFIED\] The BDC section is titled "Liste des avis d'achat". Cancellation notices say "avis d'achat sur bon de commande". In the UI, a BDC is an **avis d'achat** and a response is a **devis** ("date limite de réception des devis").
- &#91;VERIFIED\] BDC lives in a separate app under `/bdc/entreprise/consultation/`. The main portal, `index.php?page=entreprise.EntrepriseHome`, is where AO/marchés presumably live. It was not inspected.
- &#91;VERIFIED\] Two BDC sub-sections exist: **Consultations** (active) and **Résultats des avis d'achat** (awards).
- &#91;UNKNOWN\] Legal thresholds and the current decree. Memory suggests decree 2-22-431, but this is not verified and must not be relied on until sourced.

## 2. Legal and ethical frame

- &#91;VERIFIED\] Listing, detail and results are readable without login (the page shows "Invité"). Participation requires login: "vous devez d'abord vous connecter".
- &#91;UNKNOWN\] `robots.txt` and the terms of use. They could not be fetched and need to be opened manually.
- &#91;HYPOTHESIS\] Personal data is minimal in guest view: buyers are institutions and winners are companies. Some winners may be sole proprietors, so store only company name and amount.
- Proposed guardrails (to be validated):
  - at most 1 request per second, with an identifiable User-Agent
  - no login automation, no captcha bypass, no bid submission
  - no bulk attachment download until the terms are checked

## 3. Technical anatomy

| Aspect | Finding |
| --- | --- |
| Rendering | \[VERIFIED\] Full content returned without visible JS dependence, so likely server-rendered HTML. \[HYPOTHESIS\] A headless browser is not needed. |
| Active listing size | \[VERIFIED\] 1,605 results, 161 pages at 10 per page. A page-size selector offers 10, 20, 30 and 50 (URL parameter \[UNKNOWN\]). |
| Pagination | \[VERIFIED\] `?page=N`. |
| Sort order | \[VERIFIED on page 1 sample\] Closing date descending (16 Mar 2027, 31 Dec 2026, 3 Dec, 30 Nov, …). It is not sorted by publication date. |
| Drift risk | \[HYPOTHESIS\] Offers leave the list as deadlines pass and new ones are inserted, so page offsets shift during a crawl. Mitigation: crawl at 50 per page (about 33 pages) in one pass and dedupe on the portal id. |
| Stable ID | \[VERIFIED\] Detail URL is `/bdc/entreprise/consultation/show/{id}`, an integer (seen from 316430 to 410298). IDs are not chronological. |
| Reference | \[VERIFIED\] Not unique. "06/2026" and "07/2026" are per-buyer series. Natural key is (buyer, reference, year), but the portal id is the primary key. |
| Filters | \[VERIFIED\] Keyword, reference, objet, closing-date range, publication-date range, main category, nature de prestation, acheteur, lieu d'exécution. Their URL parameters are \[UNKNOWN\]. |
| Dates | \[VERIFIED\] `dd/mm/yyyy HH:MM` on detail, and "30 nov. 2026 à 14:00" on the listing. Timezone is \[UNKNOWN\], presumably Africa/Casablanca. |
| Results volume | \[VERIFIED\] 338,891 results on the first fetch, 339,851 on the last-page fetch minutes later. The jump is unexplained: it could be cache nodes or a burst of publications. Treat it as a drift signal. |
| Results history | \[VERIFIED\] Sorted by publication date descending. Page 33890 shows 9 Oct 2023 and pagination continues to page 33986, so history goes back to at least Oct 2023. The true start is \[UNKNOWN\]. |

## 4. Field inventory

### Listing (active)

| Field | Example | Notes | Value |
| --- | --- | --- | --- |
| Clôture datetime | 30 nov. 2026 à 14:00 |  | High |
| Reference | 06/2026 |  | Medium |
| Status badge | Annulé | Appears inside the "active" list | High |
| Objet | Achat et pose de caméra… | Free text, up to paragraph length | High |
| Buyer | Commune rurale de RDADNA O. MALEK |  | High |
| Location | BENSLIMANE, or about 75 provinces for national buyers | Must be an array | Medium |
| Detail link | `/show/409807` | Gives the id | n/a |

### Detail (guest view)

| Field | Example | Value |
| --- | --- | --- |
| Objet |  | High |
| Acheteur public |  | High |
| Date mise en ligne | 18/11/2026 16:15 | Medium |
| Date limite de réception des devis | 27/11/2026 14:00 | High |
| Lieu d'exécution |  | Medium |
| Catégorie principale | Travaux / Fournitures / Services | Medium, see Challenge 2 |
| Nature de prestation | Travaux d'installation de matériels divers | Medium |
| Pièces jointes | A .zip at `/download/{offerId}/{fileId}` | High if accessible |
| Articles (line items) | Number, designation, specs text, unit, quantity, TVA %, "garanties exigées" | **Very high** |

Not visible to a guest \[VERIFIED absence\]: estimated amount, provisional guarantee, contact person, evaluation criteria. They may exist behind login or inside the zip.

The camera BDC (#409807) has 7 structured line items, for example 14 × 5MP camera ("HIKVISION ou similaire"), 1 × 16-channel DVR, 4 × HDD, 300 m cable. That is the right granularity for matching and for the "how much of this can I supply" calculation.

### Results (awards)

| Field | Example | Value |
| --- | --- | --- |
| Status | Attribué / Infructueux | High |
| Published at | 17/11/2026 14:56 |  |
| Reference, objet, buyer |  |  |
| Nombre de devis reçus | 4 to 52 in the samples | **Very high** (competition intensity) |
| Entreprise attributaire |  | **Very high** (competitor tracking) |
| Montant TTC | 16,446.00 MAD | **Very high** (price benchmark) |

&#91;UNKNOWN\] Whether result rows link to the original detail page, and whether closed offers' detail pages and line items stay accessible. This is the biggest open technical question.

## 5. Lifecycle

- &#91;VERIFIED\] Observed states: active, Annulé (in the active list), Attribué, Infructueux.
- &#91;VERIFIED\] **Cancellations are sometimes published as new offers.** Id 351070 is titled "DÉCISION D'ANNULATION DE L'AVIS D'ACHAT N° 1/2026…", names the awardee and the reason, and carries its own reference and deadline.
- &#91;UNKNOWN\] Whether amendments overwrite the original, whether there is a version history, and how long closed offers stay visible.

## 6. Attachments

- &#91;VERIFIED\] One .zip per offer, with typos in the file name ("serveillance"). Contents are \[UNKNOWN\].
- &#91;HYPOTHESIS\] The zip holds the avis, a bordereau, and possibly the technical specification, in PDF or DOC and sometimes scanned. That means text extraction and OCR work in Phase 3.

## 7. Other sections, ranked by value

1. **Résultats des avis d'achat.** Biggest finding: about 340k awards with bidder count, winner and total amount, going back to at least 2023. It is the only public source of price and competition data, so capturing it should start now.
2. **Active consultations.** The discovery feed.
3. **Main-portal AO/marchés.** Not inspected, so the section list is \[UNKNOWN\]. Next recon target after BDC.
4. **Programmes prévisionnels, rectificatifs, buyer directory.** \[UNKNOWN\] whether they exist on the portal.

## 8. Verdict

- Plain HTTP scraping with an HTML parser should be enough. Drift risk is medium: a simple server-rendered app, but the sort order and the free-text fields are messy.
- No official API or open-data channel was visible.
- Block and legal risk: \[UNKNOWN\] until `robots.txt` and the terms are read.

## 9. Challenges to the starting assumptions

1. **"Start with active BDC" is the wrong center of gravity.** The results archive is the asset: it feeds price benchmarks, competitor tracking, win rates and buyer behavior. Recommendation: two pipelines from day one. A, active offers, polled hourly, with every active offer snapshotted at discovery in case closed pages disappear. B, a results backfill and then daily ingestion.
2. **The taxonomy cannot be trusted alone.** The CCTV supply-and-install BDC is filed under "Travaux d'installation de matériels divers". The list of about 300 "nature de prestation" values (with ONDA- and ANCFCC-specific variants such as "Systèmes vidéo surveillance (ONDA)") is a useful coarse prefilter, but matching must run on objet plus line items.
3. **For a software and data profile, BDC may be thin.** A page-1 sample of 10 active offers had one CCTV item, one network and fibre job, and no software. That is anecdotal. The relevant nature values are "Achat de matériel technique, de logiciels et de matériel informatique", "Entretien et maintenance de logiciels et de progiciels" and "Études, conseil et formation". Counting how many active and historical offers hit them is a cheap feasibility test, to run before building anything heavy. Marchés/AO may matter more for a software and data business.
4. **"95% aligned" is feasible for BDC supply offers**, because line items carry brand and specs. It is not feasible from the listing title alone.
5. **Hourly polling is enough.** The camera BDC was online 18 to 27 Nov, a 9-day window, so there is no need for real-time infrastructure.
6. **Pricing caveat.** Award amounts are totals TTC, not unit prices. Unit-level benchmarking only works if closed offers' line items remain readable and can be joined to results by portal id or (buyer, reference, year).

## 10. Needed to close Phase 0

1. Contents of `https://www.marchespublics.gov.ma/robots.txt`, plus the terms-of-use text.
2. A HAR export (browser network tab) of: opening the listing, applying a keyword filter, changing page size to 50, opening a detail page, opening the results list.
3. The saved HTML of one listing page, one detail page and one results page.
4. The zip from offer 409807, to see its contents.
5. The detail page of an old closed offer, and whether it opens from the results list.
6. Which profile to build first (the software and data profile, or CCTV as the easier test case), and whether AO/marchés recon should come next.

Next step: Phase 1 (business and decision-maker diagnosis), once the items above are provided or the open points are kept as hypotheses.
