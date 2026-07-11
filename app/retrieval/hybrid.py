"""Hybrid retrieval: BM25 and embedding cosine similarity fused with RRF (ADR 0003).

Two ranked lists per query, one seam-shaped result:

* **Lexical** — the existing ``BM25Retriever`` (ADR 0001), reused as-is, so its
  ``score > 0`` cutoff, ``pet_type`` hard filter, and ``food_form`` soft boost
  keep working unchanged.
* **Semantic** — cosine similarity between the query embedding and Variant
  embeddings precomputed per Site at startup, under the *same* facet rules:
  ``pet_type`` hard-filters (authoritative data), ``food_form`` soft-boosts via
  the shared ×1.5/×0.85 adjustment.

Reciprocal Rank Fusion then merges the two orderings, so a Variant that both
lists like outranks one that only a single list likes, and a paraphrase or
cross-lingual match invisible to BM25 can still surface via the semantic leg.
"""

import asyncio
import logging
import math
import time
from functools import lru_cache

from app.catalog import facets
from app.catalog.models import Variant
from app.catalog.repository import CatalogRepository
from app.core.errors import UnknownSiteError
from app.retrieval.base import ScoredVariant
from app.retrieval.bm25 import BM25Retriever, adjust_for_food_form, tokenize
from app.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)

# Each leg contributes its top slice to the fusion pool: deeper than any sane k
# so RRF sees enough of both rankings, small enough that rank credit stays
# meaningful on ~100-Variant Site catalogs.
_FUSION_POOL = 50
_QUERY_CACHE_SIZE = 256


def _embedding_text(variant: Variant) -> str:
    # What the vector "means": the buyer-facing prose. Ingredients and feeding
    # tables are token soup (percentages, additive codes) that dilutes a
    # sentence embedding, so unlike the BM25 document they are left out here —
    # the lexical leg still covers exact-term hits inside them.
    return " ".join(
        [
            variant.product_name,
            variant.brand,
            variant.variant_name,
            variant.summary,
            variant.description,
        ]
    )


def _normalized(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return list(vector)
    return [x / norm for x in vector]


class HybridRetriever:
    """BM25 + embedding retrieval fused with Reciprocal Rank Fusion.

    Satisfies the ``Retriever`` Protocol (ADR 0001 seam); selected via
    ``ZA_RETRIEVER_BACKEND=hybrid`` and constructed by
    ``app.retrieval.factory.build_retriever``.
    """

    def __init__(
        self,
        repository: CatalogRepository,
        embedder: Embedder,
        *,
        bm25: BM25Retriever | None = None,
        rrf_k: int = 60,
        min_similarity: float = 0.25,
    ):
        self._bm25 = bm25 or BM25Retriever(repository)
        self._embedder = embedder
        self._rrf_k = rrf_k
        # The semantic analog of BM25's `score > 0` relevance cutoff: cosine
        # similarity is almost never <= 0 for real sentence embeddings, so "any
        # positive score" would admit every Variant on every query. Below this
        # floor a Variant is treated as having no semantic signal and simply
        # does not enter the semantic leg (it can still arrive via BM25).
        self._min_similarity = min_similarity
        # TO_EXPLAIN — startup precompute vs a persisted embedding store: the
        # corpus is ~300 Variants, so embedding everything in-memory at boot
        # costs seconds once and keeps the PoC dependency-free (no disk cache
        # to invalidate when the catalog file changes). The evolution path when
        # catalogs grow or boot time matters: persist vectors keyed by a
        # content hash (sqlite/parquet), or move them into the same vector DB
        # that would replace the brute-force scan below.
        started = time.perf_counter()
        self._variants: dict[int, list[Variant]] = {}
        self._vectors: dict[int, list[list[float]]] = {}
        total = 0
        for site_id in repository.site_ids():
            variants = repository.variants_for_site(site_id)
            vectors = embedder.encode([_embedding_text(v) for v in variants])
            self._variants[site_id] = variants
            self._vectors[site_id] = [_normalized(vec) for vec in vectors]
            total += len(variants)
        logger.info(
            "variant embeddings precomputed",
            extra={
                "variant_count": total,
                "site_count": len(self._variants),
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
        # Per-instance LRU over the raw query string: repeated and follow-up
        # queries skip the embedding forward pass entirely.
        self._embed_query = lru_cache(maxsize=_QUERY_CACHE_SIZE)(self._embed_query_uncached)

    def _embed_query_uncached(self, query: str) -> tuple[float, ...]:
        return tuple(_normalized(self._embedder.encode([query])[0]))

    async def retrieve(self, site_id: int, query: str, k: int) -> list[ScoredVariant]:
        if site_id not in self._variants:
            raise UnknownSiteError(site_id, sorted(self._variants))
        if not tokenize(query):
            return []
        pool = max(k, _FUSION_POOL)
        lexical = [scored.variant for scored in await self._bm25.retrieve(site_id, query, pool)]
        # The model forward pass is the one genuinely slow step here: isolated
        # live polling measured each novel query's encode stalling the event
        # loop ~30-50 ms when run inline. Off-loop, concurrent requests no
        # longer feel it. The LRU cache sits inside `_embed_query`, so repeat
        # queries pay only the thread hop.
        query_vec = await asyncio.to_thread(self._embed_query, query)
        semantic = self._semantic_ranking(site_id, query, pool, query_vec)

        # TO_EXPLAIN — fusion choice: RRF over weighted score interpolation
        # because BM25 scores (unbounded, corpus-dependent) and cosine (~[0,1])
        # live on incomparable scales; rank fusion needs no calibration and one
        # well-understood constant. Evolution: learned per-leg weights once
        # there is click/eval data to fit them, then a cross-encoder reranker
        # over the fused top-k for precision at the cost of per-query latency.
        fused: dict[Variant, float] = {}
        for ranked in (lexical, semantic):
            for rank, variant in enumerate(ranked, start=1):
                fused[variant] = fused.get(variant, 0.0) + 1.0 / (self._rrf_k + rank)
        ordered = sorted(fused.items(), key=lambda item: item[1], reverse=True)
        if lexical or semantic:
            logger.info(
                "hybrid fusion",
                extra={
                    "site_id": site_id,
                    "lexical_candidates": len(lexical),
                    "semantic_candidates": len(semantic),
                    "fused_candidates": len(fused),
                },
            )
        return [ScoredVariant(variant=v, score=s) for v, s in ordered[:k]]

    def _semantic_ranking(
        self, site_id: int, query: str, pool: int, query_vec: tuple[float, ...]
    ) -> list[Variant]:
        pet = facets.detect_pet_type(query)  # authoritative -> hard filter
        form = facets.detect_food_form(query)  # text-derived -> soft re-rank
        scored: list[tuple[Variant, float]] = []
        # TO_EXPLAIN — brute-force cosine over in-memory vectors is O(n) per
        # query: exactly right for ~100 Variants per Site (a few thousand
        # multiplies, microseconds), and it keeps the PoC free of index
        # dependencies. When catalogs grow past ~10^5 Variants the evolution is
        # an ANN index (FAISS, hnswlib) behind this same method, or a vector DB
        # (pgvector, Qdrant) once embeddings should also survive restarts.
        for variant, vec in zip(self._variants[site_id], self._vectors[site_id], strict=True):
            if pet is not None and variant.pet_type != pet:
                continue  # a dog query never returns a cat, on either leg
            similarity = sum(q * d for q, d in zip(query_vec, vec, strict=True))
            if similarity < self._min_similarity:
                continue
            scored.append((variant, adjust_for_food_form(similarity, variant, form)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [variant for variant, _ in scored[:pool]]
