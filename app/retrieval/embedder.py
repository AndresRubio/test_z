"""Embedding seam for the semantic retrieval path (ADR 0003).

The hybrid retriever depends on this tiny Protocol, not on sentence-transformers,
so the default install (and the whole offline test suite) never imports the
heavyweight embedding stack. Tests bind a deterministic fake; production binds
``SentenceTransformerEmbedder`` below.
"""

from typing import Protocol


class Embedder(Protocol):
    """Text -> vector. Pure lists of floats, deliberately numpy-free at the seam."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding per input text, row-aligned with the input."""
        ...


class SentenceTransformerEmbedder:
    """SentenceTransformers binding behind the ``Embedder`` seam.

    The import happens lazily inside ``__init__`` — sentence-transformers is an
    optional extra (``uv sync --extra semantic``), so constructing this class is
    the moment the hybrid backend commits to the heavy dependency. If the import
    or the model load fails, the retriever factory catches it and falls back to
    BM25 so the app always boots.
    """

    # TO_EXPLAIN — model choice: all-MiniLM-L6-v2 is small (~80 MB), fast on CPU,
    # and strong for English — but it is English-centric. The golden set's
    # cross-lingual `known_limitation` case (English query against a German/Spanish
    # Site's text) only flips with a multilingual model such as
    # paraphrase-multilingual-MiniLM-L12-v2, which is a pure config swap away
    # (ZA_EMBEDDING_MODEL) precisely because the model name lives in Settings,
    # not in code.
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [[float(x) for x in row] for row in vectors]
