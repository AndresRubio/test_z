# PRD: Assistant (PoC)

Status: ready-for-agent

## Problem Statement

Customers of a multi-shop pet-supplies platform can't ask natural-language questions like "What's the best dry food for a puppy with a sensitive stomach?" — they must browse and filter manually. Each shop (Site) has its own catalog, language, and currency, so any assistant must answer strictly within one Site's context. This PoC is also a hiring take-home: reviewers must be able to run it locally, offline, with no API keys, and judge the engineering reasoning behind it.

## Solution

An async chatbot API: `POST /chat` accepts a `site_id` and a natural-language `query`, and returns a conversational `answer` grounded exclusively in that Site's product catalog, plus the curated `retrieved_products` (Product Cards) used as context. A prompt-only Judge on a tiny local model declines off-topic queries before any retrieval; a BM25 Retriever finds candidate Variants within the Site; a larger local model generates the answer in the Site's locale. All models run on Ollama — fully offline. Catalog ingest detects and handles the dataset's quality defects and reports what it did.

## User Stories

1. As a customer, I want to ask product questions in natural language, so that I can find suitable products without browsing categories.
2. As a customer, I want recommendations drawn only from my shop's catalog, so that I am never offered a product I can't buy.
3. As a customer on the German shop, I want the answer in German (Spanish shop → Spanish, UK shop → English), so that the experience matches my shop.
4. As a customer, I want answers grounded in real catalog data, so that claims about products are trustworthy.
5. As a customer, I want to see the products the answer was based on, so that I can inspect details and act on the recommendation.
6. As a customer, I want prices shown with my shop's currency, so that I know what I would actually pay.
7. As a customer, I want to know whether a recommended Variant is in stock, so that I'm not sent to a dead end.
8. As a customer, I want unrated products to show no rating rather than "0/5", so that new products aren't misrepresented as terrible.
9. As a customer, I want ingredient and feeding questions answered from the catalog's own data, so that dietary advice matches the actual product.
10. As a customer, I want an honest "we don't carry a match" answer when nothing fits, so that I'm not steered to irrelevant products.
11. As a customer, I want off-topic questions politely declined in my shop's language, so that I understand what the assistant is for.
12. As the business, I want off-topic queries rejected before retrieval and generation, so that compute isn't wasted on out-of-scope traffic.
13. As the business, I want Internal Fields (margin, sales, revenue, raw stock counts) never to appear in any API response, so that competitive data doesn't leak.
14. As the business, I want Variants with implausible prices quarantined at ingest, so that customers never see a corrupted €1000 food pack.
15. As a catalog manager, I want ingest to report duplicates, quarantines, and data conflicts (e.g. a Variant listed as both DOGS and CATS), so that defects can be fixed upstream.
16. As a frontend developer, I want a stable, typed JSON contract with an explicit Product Card schema, so that I can build UI against it safely.
17. As a frontend developer, I want unknown `site_id` to return a clear 404 and malformed requests a 422, so that integration bugs fail loudly.
18. As an operator, I want a health endpoint, so that the service can be probed by infrastructure.
19. As an operator, I want structured logs with request IDs and per-stage timings, so that I can see where latency and failures occur.
20. As a reviewer, I want setup with no API keys — local models only — so that I can run the PoC offline on my machine.
21. As a reviewer, I want the README to explain design decisions and consciously accepted trade-offs, so that I can evaluate the reasoning, not just the code.
22. As a maintainer, I want every pipeline stage behind an interface, so that a query planner, hybrid retrieval, or a reranker can slot in without rewrites.
23. As a maintainer, I want the LLM runtime behind a thin client interface, so that a hosted provider can replace Ollama for production.
24. As a maintainer, I want a TDD suite asserting external behavior only, so that stage implementations can be swapped with confidence.

## Implementation Decisions

- **Runtime**: async Python service (FastAPI), dependencies managed with uv. Fully offline: all LLM calls go to a local Ollama server. No Docker for the PoC (host GPU access and model-pull UX; containerization is a roadmap item).
- **Models**: `gemma4:e4b` for answer generation; `gemma4:e2b` for the Judge. Two-model split per ADR 0002 — right-sizing per stage, independently testable guardrail.
- **API contract**: `POST /chat` takes `{site_id: int, query: str}` (both required). Success returns `{"answer": <string>, "retrieved_products": {"products": [<Product Card>...], "count": <int>}}`, products ordered by relevance. Unknown Site → 404 whose detail names the valid Sites; malformed body → 422. `GET /health` for probes. Single-turn only.
- **Product Card** (customer-safe): product/article/variant identifiers, product name, variant name, brand, pet type, price + currency, discount label, rating (null when the Variant has no ratings) + rating count, and an `in_stock` boolean. Internal Fields are excluded by construction — the response model has no such fields.
- **Pipeline**: a plain deterministic chain — Judge → Retriever → Generator — each stage behind an interface. No query planner or tool-calling loop in the PoC; those are the named seams for the agentic roadmap.
- **Judge**: prompt-only topicality check on the tiny model, returning a structured verdict before retrieval. On-topic = answerable from the catalog (products and their attributes, including ingredients and feeding recommendations). Pet trivia without a product angle is declined. Declines are polite, in the Site locale, with an empty products list. An unparseable verdict fails open (proceed to retrieval) with a warning log — false declines hurt customers more than a leaked answer grounded only in catalog data.
- **Retriever**: BM25 over per-Site indexes (HTML stripped, basic normalization), per ADR 0001. The Retriever interface is the seam for multilingual vector search, hybrid fusion, and a reranker. Known accepted gaps: cross-lingual queries and paraphrase recall.
- **Generator**: answers in the Site locale regardless of query language (branding-consistency decision — must be prominent in the README so it reads as intended behavior). Grounded exclusively in the retrieved Product Cards' source data; when retrieval is empty, the answer honestly says no match was found and nothing is invented.
- **Site registry**: derived from the dataset (Site → locale, currency); Sites 1 (de-DE, EUR), 3 (en-GB, GBP), 15 (es-ES, EUR) with disjoint catalogs.
- **Ingest policies** (all actions summarized in an ingest report): drop exact duplicate rows; quarantine Variants failing a price-plausibility check; on conflicting duplicates (same Variant, different pet type) keep the first deterministically and log the conflict; map `stock_units` to an `in_stock` boolean; treat `rating_average` as null when `rating_count` is 0.
- **Configuration**: environment-driven settings (model names, Ollama host, data path, top-k) with sane defaults.
- **Observability (PoC level)**: structured logging with request IDs and stage timings; deeper observability is roadmap.

## Testing Decisions

- **Discipline**: TDD (red-green-refactor) for every slice — tests are written before the implementation they specify.
- **What makes a good test here**: assert external behavior only — HTTP responses, contract shapes, policy outcomes — never internal call patterns or private structure.
- **The single seam**: the injected LLM client. API-level tests drive real HTTP through the ASGI test client with a fake client scripting Judge verdicts and generator answers; ingest, retrieval, site filtering, mapping, and error paths all run real code under those tests.
- **Pure-unit layer**: ingest policies and the BM25 Retriever are tested as plain functions against the real dataset (or trimmed fixtures) — no substitution needed.
- **LLM output quality** (does e4b actually answer well?) is not asserted in CI: a documented manual smoke script against live Ollama covers it; a labeled-query evaluation harness is a roadmap item.
- **Prior art**: none — greenfield repo.

## Out of Scope

- Multi-turn conversation and streaming responses
- Vector, hybrid, or reranked retrieval (the seam exists; implementations are roadmap)
- Query planner or tool-calling agent loop
- Cross-lingual retrieval
- Docker/containerization, CI pipelines, auth, and rate limiting
- Automated LLM-quality evaluation harness
- Git repository setup and submission logistics (Andres handles these)

## Further Notes

- The dataset contains deliberate quality traps; handling them is graded ("data awareness"): 12 exact duplicate rows, 1 pet-type-conflicting duplicate, 24 implausibly priced Variants (€500–1000 small food packs), 198 unrated Variants with `rating_average: 0.0`, 8 zero-stock Variants, Internal Fields adjacent to customer-facing ones, and HTML markup in all text fields.
- Reviewer setup must remain: install uv + Ollama, pull the two models, `uv sync`, run. Any addition to that list needs strong justification.
- Domain vocabulary lives in the repo glossary (Site, Product, Variant, Pet Type, Internal Fields, Judge, Retriever, Product Card) — use it in code and docs. ADRs 0001 and 0002 record the retrieval and model-split decisions.
