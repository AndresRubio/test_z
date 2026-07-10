"""Retriever construction: bind the ADR 0001 seam from configuration.

``ZA_RETRIEVER_BACKEND`` selects the binding. The hybrid backend needs the
optional embedding stack (``uv sync --extra semantic``); if it is missing or
the model fails to load, we log a clear warning and fall back to BM25 — the
app must always boot, retrieval quality degrades before availability does.
"""

import logging

from app.catalog.repository import CatalogRepository
from app.core.config import Settings
from app.retrieval.base import Retriever
from app.retrieval.bm25 import BM25Retriever

logger = logging.getLogger(__name__)


def build_retriever(settings: Settings, repository: CatalogRepository) -> Retriever:
    backend = settings.retriever_backend
    if backend == "hybrid":
        try:
            # Import inside the branch: the default install has no
            # sentence-transformers, and only this backend may require it.
            from app.retrieval.embedder import SentenceTransformerEmbedder
            from app.retrieval.hybrid import HybridRetriever

            embedder = SentenceTransformerEmbedder(settings.embedding_model)
            return HybridRetriever(
                repository,
                embedder,
                rrf_k=settings.rrf_k,
                min_similarity=settings.min_semantic_similarity,
            )
        except Exception:
            # Broad on purpose: ImportError (extra not installed) and any model
            # load failure must both degrade to BM25 instead of blocking boot.
            logger.warning(
                "hybrid retriever unavailable (is the 'semantic' extra installed? "
                "uv sync --extra semantic) — falling back to bm25",
                exc_info=True,
            )
    elif backend != "bm25":
        logger.warning("unknown retriever backend %r — falling back to bm25", backend)
    return BM25Retriever(repository)
