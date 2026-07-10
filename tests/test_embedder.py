import sys

import pytest


def test_module_imports_without_the_semantic_extra():
    # The whole point of the lazy import: the default install (no
    # sentence-transformers) must import this module without error.
    import app.retrieval.embedder as embedder

    assert hasattr(embedder, "Embedder")
    assert hasattr(embedder, "SentenceTransformerEmbedder")


def test_construction_raises_import_error_when_extra_missing(monkeypatch):
    from app.retrieval.embedder import SentenceTransformerEmbedder

    # None in sys.modules makes `import sentence_transformers` raise
    # ImportError deterministically, whether or not the extra is installed.
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(ImportError):
        SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
