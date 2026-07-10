# Ingestion Review Write-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the ingestion story to the graded README (a "Data & Ingestion" walkthrough and an ingestion-focused "Conclusions" section), slim the now-duplicated Decisions table to a pointer, and annotate + commit the reviewed plan doc.

**Architecture:** Docs-only — four tasks, one commit each, no code changes. All prose is provided verbatim below; every number in it was re-measured against `product_catalog_dataset.json` on 2026-07-10 (see the approved spec, `docs/specs/assistant/2026-07-10-ingestion-review-design.md`). Copy the text exactly; do not re-derive or "improve" figures.

**Tech Stack:** Markdown, `uv run pytest` for verification, git.

## Global Constraints

- **Never write the client's brand name** into any file or commit message. All content you need is provided verbatim in this plan and contains none — do not add any yourself. The `ZA_` env-var prefix is a deliberate exception and stays.
- **`uv` + Python 3.12 only**: the only commands you need are `uv run pytest` and `git`.
- The README is the graded write-up — copy the provided text exactly, typos-and-all review happens at the gate.
- The branch (`feature/web-ui`) is shared with another active session. Commit normally on top of HEAD; never `--amend`, never rebase. If a file changed under you, re-read it and re-apply the edit to the current content.
- Every commit message ends with the trailer line shown in each commit step.

---

### Task 1: Add the "Data & Ingestion" README section

**Files:**
- Modify: `README.md` — insert a new `## Data & Ingestion` section between the High-Level Design bullet list (ends `→ 503 (see the note on the conditional 503 in Decisions).`) and the `## Setup and Execution` heading; also update one cross-reference in the Catalog bullet.

**Interfaces:**
- Produces: the `## Data & Ingestion` heading (GitHub anchor `#data--ingestion`), which Task 2's pointer paragraph links to.

- [ ] **Step 1: Update the Catalog bullet's cross-reference**

In `README.md`, in the High-Level Design bullet list, change this line pair:

```markdown
- **Catalog** (`app/catalog`): ingest applies five data-quality policies to
  `product_catalog_dataset.json` and reports what it did (see Decisions), then
```

to:

```markdown
- **Catalog** (`app/catalog`): ingest applies five data-quality policies to
  `product_catalog_dataset.json` and reports what it did (see
  [Data & Ingestion](#data--ingestion)), then
```

- [ ] **Step 2: Insert the new section**

Insert the following, verbatim, immediately after the last High-Level Design bullet (the `- **API** …` bullet ending `… conditional 503 in Decisions).`) and before `## Setup and Execution`, separated by blank lines:

```markdown
## Data & Ingestion

The dataset (`product_catalog_dataset.json`) is 300 rows — one row is one
Variant on one Site — split cleanly across three disjoint Sites × 100 rows
(1 = de-DE/EUR, 3 = en-GB/GBP, 15 = es-ES/EUR), 22 fields per row, 150 DOGS /
150 CATS. It ships with deliberate data-quality traps. Ingest
(`app/catalog/ingest.py`) runs once at startup, is deterministic, and defuses
every trap with an explicit policy; every count below is pinned by
`test_real_dataset_counts_match_the_known_traps`, so any ingest change that
shifts an outcome fails the suite.

Walking the pipeline, trap by trap:

1. **Same row twice.** 12 rows are byte-identical copies of another row →
   dropped. Duplicates are keyed by (`site_id`, `variant_id`) and compared as
   full records, so only true copies are dropped silently.
2. **One Variant, two species.** Variant `2422691.0` (site 15) appears twice —
   once as DOGS, once as CATS. Same key, different content: a conflict, not a
   copy. The first record is kept (deterministic, idempotent) and the conflict
   is logged as a warning.
3. **Unrated products look terrible.** 198 raw rows carry
   `rating_average: 0.0` with `rating_count: 0`. Taken literally, "no rating
   yet" reads as "worst possible rating" — so the rating is nulled whenever
   the count is 0. (Counting nuance: 198 counts raw feed rows as a
   source-quality signal; after dedup 192 distinct Variants are affected, 174
   of which survive quarantine.)
4. **The €950 food packs.** 24 Variants cluster at €950–1000 — food and
   cat-litter multi-packs — while nothing else in the catalog costs more than
   €215.64. They are quarantined, not repaired: excluded from retrieval but
   counted and logged with their prices. The threshold
   (`ZA_MAX_PLAUSIBLE_PRICE`, default 500) sits in that wide empty gap; a
   production version would use per-category outlier statistics instead of
   one flat cap.
5. **Zero stock.** 8 Variants have zero stock units. They stay retrievable —
   hiding them would hide the product a customer asks about — but are exposed
   as `in_stock: false` so the answer can steer to alternatives.
6. **HTML everywhere.** Markup or entities appear in every `description`
   (300/300) and in most `summary` (272/300), `ingredients` (217/300) and
   `feeding_recommendations` (209/300) fields — tables (176 rows), lists
   (297 rows), inline markup, encoded entities. Text is normalized by
   stripping tags *first* and decoding entities *second*: the order matters,
   because the catalog encodes real comparisons as entities (`&lt;25kg` →
   `<25kg`) and decoding first would let the tag-stripper eat legitimate
   content. Verified against the real data: nutrition and size tables
   collapse to readable text. Product and variant names are already clean and
   pass through untouched.
7. **Internal Fields sit next to public ones.** Every row carries
   `margin_pct`, `monthly_sales_units`, `revenue_last_30d` and raw
   `stock_units` adjacent to customer-facing fields. They are excluded **by
   construction**: the domain model (`app/catalog/models.py`) has no such
   fields, so no code path — present or future — can leak them into a
   response.

Beyond the advertised traps, profiling also found **2 rows with an empty
`brands` field** (`56322.18`/`56322.19`, site 15, two sizes of one product;
no sibling row carries the brand, so it is not repairable from within the
dataset). They are kept as-is: the brand appears verbatim in `product_name`,
so retrieval is unaffected, and the only visible effect is an empty `brand`
string on those two Product Cards. A production ingest would backfill the
field from the name, or null it.

**Record accounting:** 300 raw → −12 exact duplicates → −1 conflicting
duplicate → 287 unique Variants → −24 quarantined → **263 retrievable**
across Sites 1/3/15.

**What downstream gets:** per-Site, HTML-free, customer-safe Variants,
hard-partitioned by `CatalogRepository`; a per-Site BM25 index built over the
cleaned text with a name/brand boost; an `IngestReport` with all counts,
logged at startup.

**Deliberate simplifications** — a fuller pipeline would add these; the PoC
consciously trades them away:

- The report carries counts only; per-row quarantine and conflict detail goes
  to warning logs rather than a structured quarantine list.
- HTML is stripped with a regex, not a structure-preserving parser
  (`<li>` → bullets, tables → "label: value" lines). Verified adequate on
  this dataset: zero cell-concatenation cases, readable tables.
- A malformed row fails ingest loudly at startup instead of being quarantined
  with a reason: for a startup-ingest PoC, a broken feed should stop the
  service, not degrade it silently.
- The searchable text is assembled inside the BM25 binding; the retrieval
  seam is the `Retriever` protocol itself, so a vector successor re-derives
  its corpus from the same cleaned Variants.
```

- [ ] **Step 3: Verify the edit**

Run: `grep -n "^## " README.md`
Expected: `## Data & Ingestion` appears between `## High-Level Design` and `## Setup and Execution`.

Run: `grep -c "263 retrievable" README.md`
Expected: `1`

Run: `uv run pytest`
Expected: all tests pass (the README repeats the pinned counts; the suite proves them — spec requires a passing suite before any docs commit).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add Data & Ingestion walkthrough to README

Trap-by-trap pipeline walkthrough with pinned counts, record accounting
(300 -> 287 -> 263), the empty-brands profiling observation, and the
deliberate simplifications vs. a fuller ingest.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Slim the Decisions data-quality block to a pointer

**Files:**
- Modify: `README.md` — inside `## Decisions and Trade-offs`, replace the data-quality bold paragraph + 7-row table with a pointer paragraph.

**Interfaces:**
- Consumes: the `#data--ingestion` anchor created in Task 1.

- [ ] **Step 1: Replace the block**

In `README.md`, delete this entire block (the bold intro line, the blank line, and the 9 table lines):

```markdown
**Data quality: the catalog is booby-trapped; ingest defuses it and reports.**

| Finding (this dataset) | Policy |
|---|---|
| 12 exact duplicate rows | dropped |
| 1 Variant listed as both DOGS and CATS (site 15, `2422691.0`) | first record kept, conflict logged |
| 198 unrated Variants with `rating_average: 0.0` | rating nulled — an unrated product must not look like a terrible one |
| 24 Variants at implausible €950–1000 for food/litter multi-packs | quarantined (threshold `ZA_MAX_PLAUSIBLE_PRICE`); a production version would use per-category outlier statistics instead of one flat cap |
| 8 Variants with zero stock | kept retrievable, exposed as `in_stock: false` so the answer can steer to alternatives |
| HTML markup in all text fields | stripped before indexing and prompting |
| Internal Fields (`margin_pct`, `monthly_sales_units`, `revenue_last_30d`, raw `stock_units`) | never parsed into the domain model — excluded from responses by construction |
```

and put this single paragraph in its place:

```markdown
**Data quality: the catalog is booby-trapped; ingest defuses every trap with
an explicit, tested policy.** Twelve duplicate rows, a two-species Variant, a
€950–1000 price cluster, zero-rating-as-unrated, zero stock, HTML in every
description, Internal Fields adjacent to public ones — each finding, the
policy chosen, and the exact counts are walked through in
[Data & Ingestion](#data--ingestion) above.
```

- [ ] **Step 2: Verify the edit**

Run: `grep -c "| Finding (this dataset) | Policy |" README.md`
Expected: `0`

Run: `grep -c "(#data--ingestion)" README.md`
Expected: `2` (the Catalog bullet from Task 1 + this pointer)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: slim Decisions data-quality table to a pointer

The 7-row table's content moved into the Data & Ingestion walkthrough;
Decisions keeps the claim and links there.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Add the "Conclusions" README section

**Files:**
- Modify: `README.md` — insert a new `## Conclusions` section immediately before `## Future Roadmap`.

**Interfaces:**
- Consumes: nothing from other tasks (independent of Tasks 1–2 in content, but keep task order so commits read coherently).

- [ ] **Step 1: Insert the section**

Insert the following, verbatim, immediately before the `## Future Roadmap` heading, separated by blank lines:

```markdown
## Conclusions

What the data work of this PoC demonstrates:

1. **Data quality is a deliverable, not preprocessing.** The catalog's traps
   are the assignment's data-awareness test; each one is met by an explicit,
   named policy with a pinned count. Nothing is silently "cleaned".
2. **Policies over repairs.** Quarantine, don't fix (24 prices); null, don't
   guess (198 ratings); keep-first and log, don't merge (1 conflict).
   Deterministic and auditable beats clever: an ingest you can explain in one
   page is an ingest you can defend.
3. **Safety by construction beats filtering.** Internal Fields cannot leak
   because the domain model has no fields to hold them. A structural
   guarantee is verified by reading one model; a filter would have to be
   verified on every code path, every time a new one is added.
4. **Pin reality in tests.** `test_real_dataset_counts_match_the_known_traps`
   turns the dataset's traps into a permanent regression guard: any ingest
   change that shifts an outcome — a count, a leaked tag, a cross-Site row —
   fails the suite loudly.
5. **Clean once, serve every retriever.** The per-Site, HTML-free corpus is
   what makes the retrieval seam real: BM25 consumes it today; the planned
   vector/hybrid successor consumes the same corpus tomorrow with zero ingest
   rework. What production would change is known and bounded: per-category
   outlier statistics instead of a flat price cap, a refresh pipeline instead
   of startup ingest, a structured quarantine report for operations, and
   backfill-or-null for the two empty-brand rows.
```

- [ ] **Step 2: Verify the edit**

Run: `grep -n "^## " README.md`
Expected: `## Conclusions` appears between `## Decisions and Trade-offs` and `## Future Roadmap`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add ingestion-focused Conclusions section to README

Five conclusions from the data work: quality-as-deliverable, policies over
repairs, safety by construction, pinned-reality tests, clean-once corpus.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Annotate and commit the ingest plan doc

**Files:**
- Modify: `docs/specs/assistant/ingest-pipeline.plan.md` (currently **untracked** — this task also brings it under version control).

**Interfaces:**
- Consumes: the review outcomes recorded in `docs/specs/assistant/2026-07-10-ingestion-review-design.md` (already committed); the Outcome text below mirrors them.

- [ ] **Step 1: Flip the status line**

In `docs/specs/assistant/ingest-pipeline.plan.md`, change:

```markdown
Status: ready-for-agent
```

to:

```markdown
Status: implemented — reviewed 2026-07-10
```

- [ ] **Step 2: Insert the Outcome block**

Insert the following, verbatim, immediately after the `**Parent:** …` line and before `## 1. Why this exists (context)`, separated by blank lines:

```markdown
## Outcome (review of 2026-07-10)

This plan arrived after the ingest it describes was already built
(`app/catalog/ingest.py`). Reviewed against the implementation — full
analysis in `2026-07-10-ingestion-review-design.md`:

- **Implemented as planned:** the five data-quality policies and every §3
  target count (12 / 1 / 198 / 24 / 8; 300 → 287 → 263, verified by
  `test_real_dataset_counts_match_the_known_traps`); HTML normalization with
  entity-encoded comparisons preserved (`<25kg`); Internal-Field exclusion by
  construction; per-Site partition; configurable threshold
  (`ZA_MAX_PLAUSIBLE_PRICE`).
- **Deviated — rich report (§4):** `IngestReport` carries counts only;
  per-row quarantine/conflict detail goes to warning logs. PoC scope call.
- **Deviated — normalization (§5.5):** regex strip-then-unescape instead of
  a structure-preserving parser; verified readable output on the real
  dataset (176 rows with tables, zero cell-concatenation cases).
- **Deviated — malformed rows (§5.1):** ingest fails loudly at startup
  instead of quarantining with a reason; a broken feed should stop a
  startup-ingest service, not degrade it silently.
- **Deviated — invariant gate (§5.10):** the invariants are held by
  construction (Internal Fields) and by the pinned real-dataset test
  (HTML-free text, counts, per-Site partition) rather than runtime asserts.
- **Deviated — corpus assembly (§5.8):** searchable text is assembled in
  `bm25.py`; the seam is the `Retriever` protocol, so a vector successor
  re-derives its corpus from the same cleaned Variants.
- **Deviated — module layout (§9):** one `ingest.py` + one `test_ingest.py`;
  cosmetic.
- **Found beyond the plan:** 2 empty-brand rows (`56322.18`/`56322.19`,
  site 15) kept with `brand: ""` — the brand is verbatim in `product_name`;
  documented in the README's Data & Ingestion section.
```

- [ ] **Step 3: Verify the edit**

Run: `grep -n "Status:" docs/specs/assistant/ingest-pipeline.plan.md`
Expected: exactly one line: `Status: implemented — reviewed 2026-07-10`

Run: `grep -c "## Outcome (review of 2026-07-10)" docs/specs/assistant/ingest-pipeline.plan.md`
Expected: `1`

- [ ] **Step 4: Commit**

```bash
git add docs/specs/assistant/ingest-pipeline.plan.md
git commit -m "docs: annotate ingest plan with review outcome and track it

Status flipped to implemented; Outcome block records per-item
implemented-as-planned vs. deviated-with-reason, mirroring the
ingestion-review design doc.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
