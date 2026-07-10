# Ingestion review — design for the write-up and gap-analysis record

Date: 2026-07-10 · Status: approved · Scope: **docs-only** (no code changes)

## Why

A separately produced plan (`docs/specs/assistant/ingest-pipeline.plan.md`)
describes a fuller ingest pipeline than the one implemented in
`app/catalog/ingest.py`. This design records the comparison, decides what to do
about each gap, and specifies the README additions that make the ingestion
story — problems found, policies chosen, counts proven — explicit for the
graded write-up.

## Gap analysis (plan vs. implementation)

Verified against the code and the real dataset on 2026-07-10. The suite's
pinned test (`test_real_dataset_counts_match_the_known_traps`) passes; all
counts below re-checked directly.

| Plan item | In project? | Decision |
|---|---|---|
| Five data-quality policies with pinned counts (12 dups, 1 conflict, 198 ratings nulled, 24 quarantined, 8 out-of-stock; 300 → 287 → 263) | Yes — implemented and test-pinned | Nothing to do |
| HTML normalization with `<25kg` preservation | Yes — regex strip-then-unescape, documented in `strip_html` | Nothing to do |
| Internal Fields excluded by construction | Yes — `Variant`/`ProductCard` have no such fields | Nothing to do |
| Per-Site partition + per-Site BM25 | Yes — `CatalogRepository`, `BM25Retriever` | Nothing to do |
| Configurable price threshold | Yes — `ZA_MAX_PLAUSIBLE_PRICE` → `Settings.max_plausible_price` → `load_catalog` | Nothing to do |
| Rich `IngestReport` (quarantine list with id/price/reason; conflict log with differing field) | No — counts only; per-row detail in warning logs | **Keep as-is**; document as a deliberate PoC simplification |
| Structure-preserving HTML parser (`<li>`→bullets, table→"label: value") | No — regex stripper | **Keep as-is**; verified on the real dataset: 176 rows contain tables, zero cell-concatenation cases, cleaned table text stays readable |
| Malformed-row quarantine with reason | No — raises `ValueError` at startup | **Keep as-is**; a broken feed should stop a startup-ingest service loudly, not degrade it silently |
| Runtime invariant gate before hand-off | No — invariants held by construction + pinned tests | **Keep as-is**; document the equivalence |
| Searchable corpus assembled in ingest (seam artifact) | No — assembled in `bm25.py::_document_tokens` | **Keep as-is**; the seam is the `Retriever` protocol, a vector successor re-derives text from the same cleaned Variants |
| Module layout (`normalize.py`, three test files) | No — one `ingest.py`, one `test_ingest.py` | **Keep as-is**; cosmetic |

Conclusion of the review: **every functional requirement of the plan is met**;
every gap is an explainability/robustness extra that the PoC deliberately
trades away. No code change is warranted; the gaps become write-up material.

### An eighth observation, beyond the advertised traps

Profiling also surfaced a data-quality wart that neither the plan nor the
seven known traps mention: **2 rows with an empty `brands` field** — variants
`56322.18` and `56322.19` (site 15, two sizes of the same weight-control dog
food). No sibling row carries the brand, so it cannot be repaired from within
the dataset. Both rows survive ingest into the kept 263 with `brand: ""`.

Decision (within docs-only scope): **keep the code as-is, document it.**
Impact is limited — the brand name appears verbatim in `product_name`, so the
BM25 name/brand boost still matches brand queries; the only visible effect is
an empty `brand` string in those two Product Cards. The README walkthrough
gets an "also found in profiling" note, and the production line in the
Conclusions gains "backfill or null empty brands". Finding it shows the
profiling went beyond the traps the assignment advertises.

## Deliverables

### 1. README section "Data & Ingestion"

Placed after "High-Level Design", before "Setup and Execution".

- **Opening:** 300 rows (one row = one Variant on one Site), 3 disjoint Sites,
  22 fields, deliberate quality traps; ingest runs once at startup,
  deterministic; all outcomes pinned by
  `test_real_dataset_counts_match_the_known_traps`.
- **Stage walkthrough** in pipeline order, each stage titled by the trap it
  defuses, stating finding → policy → count:
  1. *Same row twice* — 12 byte-identical duplicates → dropped (keyed by
     `site_id` + `variant_id`, full-record equality).
  2. *One Variant, two species* — `2422691.0` as both DOGS and CATS → keep
     first deterministically, log the conflict.
  3. *Unrated products look terrible* — 198 raw rows with
     `rating_average: 0.0`, `rating_count: 0` → rating nulled; include the
     counting nuance (198 raw / 192 post-dedup / 174 among kept).
  4. *The €950 food packs* — 24 rows at €950–1000 vs. €215.64 max elsewhere →
     quarantined; `ZA_MAX_PLAUSIBLE_PRICE=500` sits in the gap; production
     would use per-category outlier statistics.
  5. *Zero stock* — 8 rows → kept retrievable as `in_stock: false` so answers
     can steer to alternatives.
  6. *HTML everywhere* — markup or entities in every `description` (300/300),
     most `summary` (272/300), `ingredients` (217/300), `feeding` (209/300);
     names/brands clean (left untouched) → strip tags **then** decode
     entities, preserving real content like `<25kg`; tables (176 rows) verified
     to collapse to readable text.
  7. *Internal Fields next to public ones* — margin/sales/revenue/raw stock →
     excluded by construction: the domain model never parses them.
- **Also found in profiling** (not an advertised trap): 2 rows with an empty
  `brands` field (`56322.18`/`56322.19`, site 15, same product; brand not
  recoverable from any sibling row) → kept with `brand: ""` — the brand is
  verbatim in `product_name`, so retrieval is unaffected; a production ingest
  would backfill from the name or null the field.
- **Record accounting:** 300 → −12 dups → −1 conflict → 287 unique → −24
  quarantined → **263 retrievable** (Sites 1/3/15).
- **What downstream gets:** per-Site, HTML-free, customer-safe Variants;
  per-Site BM25 indexes; `IngestReport` counts logged at startup.
- **Deliberate simplifications:** counts-only report (detail in warning logs);
  regex stripper, not a structure-preserving parser (verified adequate here);
  fail-loud on malformed rows, not quarantine; corpus text assembled in the
  BM25 binding (the seam is the `Retriever` protocol).

### 2. README section "Conclusions"

Placed immediately before "Future Roadmap". Ingestion-focused, five
conclusions, each 2–3 sentences:

1. **Data quality is a deliverable, not preprocessing** — every trap met by an
   explicit, named, counted policy.
2. **Policies over repairs** — quarantine, don't fix; null, don't guess;
   keep-first and log, don't merge. Deterministic and auditable beats clever.
3. **Safety by construction beats filtering** — a model with no Internal
   Fields is verifiable at a glance; a filter must be verified on every path.
4. **Pin reality in tests** — the real-dataset test turns the traps into a
   permanent regression guard.
5. **Clean once, serve every retriever** — the cleaned per-Site corpus is what
   makes the retrieval seam real; ends with one honest line on what production
   would change (per-category outlier statistics, refresh pipeline instead of
   startup ingest, richer report for ops, backfill-or-null for the two
   empty-brand rows).

### 3. README "Decisions and Trade-offs" slim-down

The 7-row data-quality table is replaced by a short paragraph: the claim
("the catalog is booby-trapped; ingest defuses every trap with an explicit,
tested policy") plus a pointer to Data & Ingestion. No content is lost — it
moves into the walkthrough.

### 4. Plan-doc annotation

`docs/specs/assistant/ingest-pipeline.plan.md`: flip status to
`implemented — reviewed 2026-07-10` and add an **Outcome** block at the top
recording, per plan item, "implemented as planned" or "deviated + reason",
mirroring the gap-analysis table above. Commit the file (it is currently
untracked).

## Verification

- Every number written into the README is re-measured against
  `product_catalog_dataset.json` (done for all figures listed here, including
  the €215.64 max plausible price, the €950/€1000 quarantine cluster, the
  conflict variant `2422691.0` on site 15, and the 2 empty-brand rows).
- `uv run pytest` must pass before the docs commit (the README repeats the
  pinned counts; the suite proves them).
- Hard constraint: the client's brand name appears nowhere.

## Out of scope

Any code change (richer report, invariant gate, parser-based normalization,
corpus relocation) — considered and rejected above; recorded as deliberate
simplifications instead. The BM25/Judge/Generator write-up sections beyond the
slim-down pointer.
