# Hybrid semantic retrieval behind the seam, opt-in

The Retriever seam left by ADR 0001 gets its designed second binding: a hybrid backend (`ZA_RETRIEVER_BACKEND=hybrid`) that fuses the unchanged BM25 ranking with cosine similarity over sentence embeddings (`all-MiniLM-L6-v2`) using Reciprocal Rank Fusion. RRF over score interpolation because BM25 scores (unbounded, corpus-dependent) and cosine (~[0,1]) live on incomparable scales — rank fusion needs no calibration, just one constant (`ZA_RRF_K`). The facet contract is unchanged on both legs: `pet_type` hard-filters, `food_form` soft-boosts ×1.5/×0.85; the semantic leg's analog of BM25's `score > 0` cutoff is a cosine floor (`ZA_MIN_SEMANTIC_SIMILARITY`). Variant embeddings are precomputed in memory per Site at startup (timed and logged); query embeddings sit behind a small LRU. Crucially, the whole stack is opt-in: sentence-transformers is an optional extra (`uv sync --extra semantic`), the import is lazy, and if the model is unavailable the factory logs a warning and boots on BM25 — the default install, the offline test suite, and the graded `bm25` path are untouched.

## Consequences

- BM25 stays the default; hybrid must be asked for twice (install the extra, flip the env var), so PoC setup cost is unchanged.
- `all-MiniLM-L6-v2` is English-centric: the cross-lingual `known_limitation` eval case only flips with a multilingual model (e.g. `paraphrase-multilingual-MiniLM-L12-v2`) — a config swap, no code change.
- Brute-force cosine is O(n) per query — right for ~100 Variants per Site; an ANN index (FAISS/hnswlib) or vector DB (pgvector/Qdrant) replaces the scan when catalogs grow.
- Startup pays the one-time embedding pass (model load dominates); a persisted embedding store keyed by content hash is the evolution if boot time starts to matter.
- Fused scores are RRF rank credits, not BM25 scores — downstream only orders by them, but they are not comparable across backends.
- The embedding forward pass runs synchronously in the event loop (~ms per uncached query on CPU); acceptable for the PoC, offload to a thread if it ever shows up in traces.
