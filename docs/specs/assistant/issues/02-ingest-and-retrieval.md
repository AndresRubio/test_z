# 02 — Ingest with data-quality policies + BM25 retrieval returning Product Cards

Status: done — shipped; verified by the offline test suite (ingest policies and BM25 against the real dataset), the live smoke script, and the golden-set eval's retrieval expectations

## Parent

`docs/specs/assistant/PRD.md`

## What to build

Catalog ingest that applies the five data-quality policies and emits an ingest report, plus a BM25 Retriever behind the Retriever interface, wired into `/chat` so real Product Cards come back (the answer stays canned in this slice). Policies: drop exact duplicate rows; quarantine Variants failing a price-plausibility check; keep the first record of a pet-type-conflicting duplicate and log the conflict; derive `in_stock` from stock units; null the rating when the rating count is 0. The Retriever searches only within the requested Site over HTML-stripped text, returning Variants by relevance. The Product Card response model contains no Internal Fields by construction.

Covers user stories 2, 5, 6, 7, 8, 13, 14, 15, 22 (retriever seam), 24.

## Acceptance criteria

- [x] Ingest report states, for the provided dataset: 12 exact duplicates dropped, 24 Variants quarantined for implausible prices, 1 pet-type conflict logged, 8 Variants marked out of stock, 198 ratings nulled
- [x] Quarantined Variants are absent from retrieval results
- [x] "dry food for a puppy with a sensitive stomach" on Site 3 retrieves sensitive/puppy dry-food Variants; equivalent locale-language queries work on Sites 1 and 15
- [x] Results never include Variants from another Site
- [x] Product Card serialization contains no margin, sales, revenue, or raw stock-unit fields; rating is null where rating count is 0; `in_stock` is boolean; price carries the Site currency
- [x] `/chat` returns retrieved Product Cards ordered by relevance with correct `count`
- [x] All policies and retrieval behaviors specified by TDD-first tests (plain-function tests for ingest/retriever, ASGI tests for the contract)

## Blocked by

- `docs/specs/assistant/issues/01-walking-skeleton.md`
