# Hybrid semantic retrieval behind the seam, opt-in

The Retriever seam left by ADR 0001 gets its designed second binding: a hybrid backend (`ZA_RETRIEVER_BACKEND=hybrid`) that fuses the unchanged BM25 ranking with cosine similarity over sentence embeddings (`all-MiniLM-L6-v2`) using Reciprocal Rank Fusion. RRF over score interpolation because BM25 scores (unbounded, corpus-dependent) and cosine (~[0,1]) live on incomparable scales — rank fusion needs no calibration, just one constant (`ZA_RRF_K`). The facet contract is unchanged on both legs: `pet_type` hard-filters, `food_form` soft-boosts ×1.5/×0.85; the semantic leg's analog of BM25's `score > 0` cutoff is a cosine floor (`ZA_MIN_SEMANTIC_SIMILARITY`). Variant embeddings are precomputed in memory per Site at startup (timed and logged); query embeddings sit behind a small LRU. Crucially, the whole stack is opt-in: sentence-transformers is an optional extra (`uv sync --extra semantic`), the import is lazy, and if the model is unavailable the factory logs a warning and boots on BM25 — the default install, the offline test suite, and the graded `bm25` path are untouched.

## Consequences

- BM25 stays the default; hybrid must be asked for twice (install the extra, flip the env var), so PoC setup cost is unchanged.
- `all-MiniLM-L6-v2` is English-centric: the cross-lingual `known_limitation` eval case only flips with a multilingual model (e.g. `paraphrase-multilingual-MiniLM-L12-v2`) — a config swap, no code change.
- Brute-force cosine is O(n) per query — right for ~100 Variants per Site; an ANN index (FAISS/hnswlib) or vector DB (pgvector/Qdrant) replaces the scan when catalogs grow.
- Startup pays the one-time embedding pass (model load dominates); a persisted embedding store keyed by content hash is the evolution if boot time starts to matter.
- Fused scores are RRF rank credits, not BM25 scores — downstream only orders by them, but they are not comparable across backends.
- The embedding forward pass runs synchronously in the event loop (~ms per uncached query on CPU); acceptable for the PoC, offload to a thread if it ever shows up in traces.

## Measured on the golden set (2026-07-11, live eval)

Ran `evals/run_eval.py` against both backends on the real catalog — the numbers
that keep hybrid opt-in:

| Backend | Headline | Cross-lingual case | Regressions |
|---|---|---|---|
| `bm25` (default) | **12/12** | KNOWN-FAIL (as documented) | — |
| `hybrid` | 11/12 | **PASS** — even English-centric MiniLM carries enough signal for "durable floating ball" → German toy | `site3-cat-kidney` drops out of top-5 |

The regression is instructive, not random: for "wet food for a cat with kidney
problems", BM25 ranks Hill's k/d Kidney Care **#1** (rare exact token, score
10.2) while the semantic leg ranks it **#33** (generic wet-cat-food similarity
dominates; the Variant is DRY-form so it is also soft-damped ×0.85). RRF's
two-list agreement then lands it at fused rank 11: single-leg excellence on a
rare exact term loses to two-leg mediocrity — the classic RRF failure mode.
Deliberately **not** fixed by tuning `ZA_RRF_K`/weights against a 13-case
golden set (that is overfitting, and the repo already flagged masking a gap as
an integrity issue once); the designed fixes are a cross-encoder reranker over
the fused top-k and/or learned per-leg weights once there is data to fit them
(README roadmap #1). Until a configuration passes the *whole* golden set,
`bm25` stays the default.
