# Moroccan Public Procurement Domain Guide

> **Scope:** Legal rules, Decree No. 2-22-431, BDC vs AO regimes, and TGR portal anatomy.  
> **Reference Law:** Moroccan Decree No. 2-22-431 (*Décret relatif aux marchés publics*), effective since September 1, 2023.

---

## 1. Procurement Regimes: BDC vs Marchés Publics (AO)

Moroccan public procurement through the Treasury portal (`marchespublics.gov.ma` / TGR) is divided into two primary operational channels:

| Parameter | Bon de Commande (BDC — Article 91) | Appel d'Offres (AO / Marché Public) |
| :--- | :--- | :--- |
| **Legal Ceiling** | Max **500,000 MAD TTC** per year per buyer per budget line | Above **500,000 MAD TTC** (unlimited) |
| **Submission Window** | Ultra-short: minimum **48 hours** (typically 3–7 days) | Standard: **21 to 40 days** |
| **Award Criteria** | Strict *Moins-Disant* (lowest compliant bidder) | *Mieux-Disant* or *Moins-Disant* with technical grading |
| **Bid Guarantees** | None required (zero *cautionnement provisoire*) | Mandatory bank guarantees (*cautionnement*) |
| **Paperwork** | Devis / Quote + Bordereau des Prix | Heavy: administrative dossier, technical file, CPS signoff |
| **Strategic Value** | High-velocity cashflow, fast decision loop | Large scale revenue, high barrier to entry |

---

## 2. Key Domain Rules Implemented in Code

1. **Article 91 Spend Ceiling (Buyer Velocity):**
   - The system aggregates all BDC awards per buyer per fiscal year.
   - When a public buyer reaches ~450k–500k MAD in BDC spend, the system triggers a **Predictive AO Alert**: that administration can no longer issue BDCs for that category and must launch a full Appel d'Offres.
2. **Moins-Disant Pricing Corridor:**
   - Because BDC awards are legally awarded to the lowest compliant bidder, Stage 4 evaluates competitive price floors based on historical award averages in that buyer's region.
3. **Publication Velocity & Urgency:**
   - Because submission windows can close in as little as 48 hours, the ingestion scheduler runs hourly and alerts are dispatched via SMTP within 120 seconds of discovery.

---

## 3. Procurement Terminology Glossary

- **BDC (*Bon de Commande*):** Purchase order consultation published under Article 91.
- **AO (*Appel d'Offres*):** Formal tender notice for major public contracts.
- **Bordereau des Prix (BP):** Schedule of prices detailing article descriptions, quantities, and units.
- **CPS (*Cahier des Prescriptions Spéciales*):** Detailed technical specifications dossier.
- **Moins-Disant:** Lowest-priced quote satisfying all stated technical criteria.
- **TGR (*Trésorerie Générale du Royaume*):** Ministry of Economy and Finance body running `marchespublics.gov.ma`.
