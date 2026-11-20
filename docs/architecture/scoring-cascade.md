# 4-Stage Cascade Scoring Engine

> **Scope:** Evaluation pipeline, threshold rules, line-item matching, and LLM Judge.  
> **Source Files:** [`src/engine/scoring_cascade.py`](file:///c:/Users/7mza/mp/src/engine/scoring_cascade.py), [`src/engine/hard_filters.py`](file:///c:/Users/7mza/mp/src/engine/hard_filters.py), [`src/engine/lexical_matcher.py`](file:///c:/Users/7mza/mp/src/engine/lexical_matcher.py), [`src/engine/line_item_matcher.py`](file:///c:/Users/7mza/mp/src/engine/line_item_matcher.py), [`src/engine/llm_judge.py`](file:///c:/Users/7mza/mp/src/engine/llm_judge.py)

---

## 1. Cascade Design Philosophy

The cascade operates hierarchically from lowest computational cost to highest:

```
[ All Ingested Tenders ]
          │
  Stage 1: Hard Binary Filters       (Time: < 1ms  | Cost: 0 tokens)  --> Discards 70%
          │
  Stage 2: Lexical Match & Vetoes    (Time: ~2ms  | Cost: 0 tokens)  --> Discards 20%
          │
  Stage 3: BOM Catalog Coverage %    (Time: ~5ms  | Cost: 0 tokens)  --> Discards 7%
          │
  Stage 4: LLM Judge & Feasibility   (Time: ~1.2s | Cost: ~600 tokens)--> High Quality 3%
```

---

## 2. Stage Breakdown

### Stage 1: Hard Binary Elimination Gate
- **Status check:** Must be `active` (rejects `annulé`, `infructueux`, `clôturé`).
- **Deadline check:** Remaining submission window must be $\ge 24$ hours (configurable in profile).
- **Macro-category match:** Must match profile's allowed categories (e.g., `Fournitures`, `Services`).
- **Geographic exclusions:** Disqualifies excluded regions if specified in profile.
- **Output:** Disqualification returns `overall_score = 0.0`, `decision_recommendation = "NO-GO"`.

### Stage 2: Lexical & Negative Veto
- **Negative Vetoes:** Instant disqualification if tender contains veto keywords (e.g., *travaux de maçonnerie*, *traiteur*, *gardiennage*, *peinture*, *nettoyage*).
- **Positive Keywords:** Weighted score based on presence of core domain keywords (e.g., *logiciel*, *développement*, *nvr*, *serveur*, *api*).

### Stage 3: Line-Item BOM Catalog Coverage %
- Evaluates individual line items from the tender's `.accordion-item` table against the profile's product/service catalog.
- **Coverage Formula:**
  $$\text{Coverage Score} = \frac{\sum \text{Matched Line Items}}{\text{Total Line Items}} \times 100$$
- Profiles define minimum required catalog coverage (default: $\ge 60\%$).

### Stage 4: LLM Judge (Gemini / OpenAI)
- Invoked only for candidates that pass Stages 1–3.
- Evaluates:
  1. **Technical Feasibility:** Can the team deliver the required scope within the stated deadline?
  2. **Hidden Red Flags:** Unrealistic requirements, ambiguous specs, punitive penalties.
  3. **Pricing Corridor:** Estimation of expected bid floor and margin guidance.
- Output: Feasibility score (0–100%), concise reasoning summary, and identified red flags.

---

## 3. Evaluation Result Schema

Defined in [`src/engine/scoring_cascade.py`](file:///c:/Users/7mza/mp/src/engine/scoring_cascade.py):

```python
@dataclass
class CascadeEvaluationResult:
    overall_score: float              # 0.0 to 100.0
    decision_recommendation: str      # 'GO' (>=80), 'CONSIDER' (60-79), 'NO-GO' (<60)
    coverage_score: float             # Line-item BOM coverage percentage
    lexical_score: float              # Keyword & constraint score
    feasibility_score: float          # LLM feasibility rating
    line_item_matches: List[Dict]     # Mapped line items with catalog matches
    red_flags: List[str]              # Reasons for disqualification or caution
    llm_reasoning: str                # Qualitative LLM decision memo
```
