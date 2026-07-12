# BM25-first retrieval behind a Retriever seam

For a fully offline PoC over a tiny corpus (~100 Variants per Site), the
Retriever is bound to lexical BM25 rather than embeddings. An AI-role reviewer
would assume the opposite, so the reasons on record:

- The corpus is small enough that lexical recall is strong.
- The assignment's own example queries match catalog text literally.
- Skipping an embedding model keeps setup to the two chat-model `ollama pull`s
  and nothing else.
- The `Retriever` interface is the deliberate seam for the production path:
  multilingual vector search, hybrid fusion (RRF), then a reranker.

## Consequences

- Cross-lingual queries (e.g. an English question against the Spanish site's
  text) will miss; this is accepted and documented, not a bug.
- Paraphrase recall is weaker than embeddings; mitigated only by corpus size.
- Per-locale tokenization (German compounds, Spanish diacritics) stays basic
  in the PoC.
