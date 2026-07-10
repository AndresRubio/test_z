# Coding Session Plan — Catalog Ingest & Data-Cleaning Pipeline

Status: implemented — reviewed 2026-07-10

**Parent:** `docs/specs/assistant/PRD.md` · **Implements:** ingest half of `docs/specs/assistant/issues/02-ingest-and-retrieval.md` · **References:** ADR 0001 (BM25-first behind a seam), `CONTEXT.md` (glossary)

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

## 1. Why this exists (context)

The Assistant is an offline PoC: a `POST /chat` API that answers pet-supplies questions grounded strictly in one Site's catalog, models running locally on Ollama, no API keys. Retrieval is **BM25-first** (ADR 0001); embeddings/vector/hybrid are deliberate future seams.

Ingest is the stage that turns the raw `product_catalog_dataset.json` into a clean, Site-scoped corpus the Retriever can search and the Generator can trust. The dataset ships with deliberate quality traps — handling them is a grading criterion ("data awareness"). This plan builds ingest so that every trap is handled by an explicit, tested policy, Internal Fields can never leak into a response, and the cleaned output is equally consumable by today's BM25 index and a future vector/hybrid retriever. That last point is the "keep data clean for the next step" goal.

**Domain vocabulary (from `CONTEXT.md`):** *Site* (one shop; sets catalog subset, language, currency; catalogs disjoint) · *Product* (marketing entity) · *Variant* (purchasable unit; one row = one Variant on one Site) · *Pet Type* (DOGS/CATS) · *Internal Fields* (`margin_pct`, `monthly_sales_units`, `revenue_last_30d`, raw `stock_units` — never in an API response) · *Retriever* (candidate Variants within a Site; BM25 now, seam for vector/hybrid) · *Product Card* (curated, customer-safe view of a Variant).

**The dataset:** 300 rows = Variants, one flat JSON array, 22 fields. Cleanly segmented into 3 Sites × 100 — Site 1 (de-DE, EUR), Site 3 (en-GB, GBP), Site 15 (es-ES, EUR); catalogs disjoint; 150 DOGS / 150 CATS. 154 distinct Products (~1.95 Variants each). Core identity/segmentation fields 100% populated; food-only fields (`ingredients`, `feeding_recommendations`) empty in 77 / 86 rows.

**The quality traps (verified counts):**

1. 12 exact-duplicate rows (same `variant_id`, byte-identical).
2. 1 pet-type-conflicting duplicate — `variant_id 2422691.0` listed as both DOGS and CATS.
3. 24 implausibly-priced Variants — the €950–1000 cluster (nothing else above €215.64; PRD frames the trap as €500–1000 food packs).
4. 198 unrated Variants carrying `rating_average: 0.0` (should read as "no rating").
5. 8 zero-stock Variants.
6. Internal Fields sit adjacent to customer-facing ones on every row.
7. HTML markup + entities in all text fields (`description` 298/300, `summary` 258/300, …), including tables, lists, `<img>`, `<a>`.

## 2. Goal & scope

**In scope (this session):** a deterministic, idempotent ingest — raw JSON → validated Variants → policy-cleaned Variants → per-Site corpus + Product Card projection + ingest report; the five data-quality policies + HTML/text normalization + Internal-Field exclusion by construction; TDD-first.

**Out of scope (seams / other issues):** the BM25 Retriever implementation and `/chat` wiring (issue 02's retrieval half — this plan produces its clean input); embeddings, vector/hybrid/rerank, chunking, cross-lingual (ADR 0001 seams); Judge/Generator/API contract (issues 01/03/04); image/media retention in the Product Card (media is stripped, not stored).

## 3. Target outcomes — numbers to hit

(from PRD "Further Notes" / issue 02 acceptance criteria)

- Exact duplicates dropped: **12**
- Pet-type conflicts kept-first + logged: **1** (`variant_id 2422691.0`)
- Implausibly-priced Variants quarantined: **24**
- Variants marked `in_stock = false`: **8**
- Ratings nulled (`rating_count == 0`): **198**
- Internal Fields in any Product Card: **0**
- HTML tags/entities left in normalized text: **0**
- Retrieval results crossing Sites: **0**

**Record accounting:** 300 raw → drop 12 exact dups → drop the conflicting duplicate's second row (keep first) → **287 unique Variants** → 24 quarantined (excluded from retrieval, retained in report) → **~263 retrievable** across the 3 Sites.

## 4. Data contracts

**Input — `RawVariant` (22 fields).** Identity: `product_id:int`, `article_id:int`, `variant_id:str`. Segmentation: `site_id:int`, `locale:str`, `pet_type:str`. Content (HTML): `brands`, `product_name`, `variant_name`, `summary`, `description`, `ingredients`, `feeding_recommendations`. Commercial: `price:float`, `currency:str`, `discount_label:str|null`, `rating_average:float`, `rating_count:int`. Internal: `stock_units:int`, `margin_pct:float`, `monthly_sales_units:int`, `revenue_last_30d:float`.

**Output — `ProductCard` (customer-safe; Internal Fields excluded by construction).** `product_id`, `article_id`, `variant_id`, `product_name`, `variant_name`, `brand`, `pet_type`, `price`, `currency`, `discount_label`, `rating` (null when `rating_count == 0`), `rating_count`, `in_stock:bool`. The model has no margin/sales/revenue/stock fields. *(`ingredients` & `feeding_recommendations` are kept on the internal cleaned Variant for grounding per user story 9, but are not Product Card fields.)*

**Output — `IngestReport`.** Counts per policy, the quarantine list (`variant_id` + reason + price), and the conflict log (`variant_id` + differing field + kept row).

## 5. The pipeline — steps for the session

Each step is a pure function; a driver composes them. Order matters where noted.

1. **Load & validate** — parse the array; validate each row into `RawVariant` (types + required core fields). Malformed → quarantine with reason (none expected here). *Verify: 300 load.*
2. **Drop exact duplicates** — collapse byte-identical rows (group by `variant_id`, compare full record). *Verify: 12 dropped.*
3. **Resolve pet-type conflicts** — for a `variant_id` whose rows differ on `pet_type`, keep the first in input order, log the conflict. *Verify: 1 logged; `2422691.0` appears once. (After 2–3: 287 unique.)*
4. **Quarantine implausible prices** — flag `price >= PRICE_MAX_PLAUSIBLE` (config constant in the €215.64–€950 gap; default 500.0). Quarantined Variants are excluded from the corpus but recorded. *Verify: 24 quarantined.*
5. **Normalize text** — for `summary`/`description`/`ingredients`/`feeding_recommendations`: parse HTML with a real parser (not regex), strip tags, decode entities (`&nbsp;`, `&amp;`, …), `<li>`→bullets / `<br>`→newline, linearize `<table>`→"label: value" lines (preserve nutrition data), drop `<img>`/`<a>` markup (keep anchor text), collapse whitespace. Leave `product_name`/`variant_name` untouched (already clean). *Verify: no residual tags/entities; a nutrition table stays readable.*
6. **Derive customer-safe fields** — `in_stock = stock_units > 0`; `rating = null` when `rating_count == 0`; carry `currency` with `price`. *Verify: 8 out of stock; 198 ratings null.*
7. **Project to Product Card** — map each retained, non-quarantined Variant through the `ProductCard` allow-list. Internal Fields absent by construction. *Verify: serialized Card has no margin/sales/revenue/stock; includes currency; null-rating rule holds.*
8. **Build per-Site corpus** — group cleaned Variants by `site_id` (1/3/15); assemble the HTML-free searchable text (`brands + product_name + variant_name + summary + description + ingredients + feeding`) for indexing. This is the seam boundary: BM25 consumes it now; a vector/hybrid retriever consumes the same corpus later without rework. *Verify: 3 partitions; no foreign-Site leakage.*
9. **Emit ingest report** — assemble counts + quarantine list + conflict log; log at startup. *Verify: equals §3 numbers.*
10. **Invariant gate (fail loud)** — assert before hand-off: 0 Internal Fields in any Card, 0 HTML in normalized text, `variant_id` unique within each Site, quarantined absent from the corpus. Any violation raises. *Verify: passes on real data; a crafted bad row trips it.*

## 6. Testing (TDD-first, per PRD)

Plain-function tests run each policy against the real `product_catalog_dataset.json` (or trimmed fixtures) and assert the §3 numbers. A serialization test asserts the Product Card carries no Internal Fields and honors the null-rating/currency rules. Tests assert external outcomes only (counts, shapes, quarantine/report contents) — never private call patterns. Red-green-refactor: the failing test for each policy is written first.

## 7. Decisions & open items

**Resolved by the PRD:** conflict tie-break = keep first deterministically + log; implausible price = quarantine (not repair); Internal Fields = excluded by construction (allow-list model); no embeddings/chunking/images in the PoC.

**Confirm while coding:** the `PRICE_MAX_PLAUSIBLE` value (any value in €215.64–€950 yields exactly 24; default `500.0` to match the PRD's "€500–1000" framing); retaining `ingredients`/`feeding` on the internal Variant for grounding (recommended: yes, per user story 9).

## 8. Acceptance criteria

- [ ] Ingest report: 12 exact dups dropped, 24 quarantined, 1 pet-type conflict logged, 8 out of stock, 198 ratings nulled
- [ ] Quarantined Variants absent from the per-Site corpus
- [ ] Product Card serialization: no margin/sales/revenue/raw-stock fields; rating null when count 0; `in_stock` boolean; price carries Site currency
- [ ] Normalized text has no HTML tags or entities; nutrition tables stay readable
- [ ] Cleaned corpus partitioned by Site; no cross-Site leakage
- [ ] Every policy specified by a TDD-first plain-function test against the real dataset

## 9. Suggested module layout

`models.py` (RawVariant, ProductCard, IngestReport — Pydantic) · `normalize.py` (HTML/text cleaning, pure) · `ingest.py` (policies + driver → per-Site corpus + report) · `tests/test_ingest.py`, `tests/test_normalize.py`, `tests/test_product_card.py`

## References

PRD (`docs/specs/assistant/PRD.md`) · Issue 02 (`docs/specs/assistant/issues/02-ingest-and-retrieval.md`) · ADR 0001 (`docs/adr/0001-bm25-first-retrieval-behind-a-seam.md`) · Glossary (`CONTEXT.md`)
