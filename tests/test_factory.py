import logging
import sys

import pytest

from app.catalog.repository import CatalogRepository
from app.core.config import Settings
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.factory import build_retriever
from app.retrieval.hybrid import HybridRetriever
from tests.helpers import FakeEmbedder, make_variant


@pytest.fixture
def repository():
    return CatalogRepository([make_variant()])


def test_default_backend_is_bm25(repository):
    retriever = build_retriever(Settings(_env_file=None), repository)
    assert isinstance(retriever, BM25Retriever)


def test_hybrid_without_embedding_stack_falls_back_to_bm25(repository, monkeypatch, caplog):
    # The app must always boot: hybrid requested but the optional extra is
    # missing -> loud warning, BM25 binding.
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    settings = Settings(_env_file=None, retriever_backend="hybrid")
    with caplog.at_level(logging.WARNING, logger="app.retrieval.factory"):
        retriever = build_retriever(settings, repository)
    assert isinstance(retriever, BM25Retriever)
    assert any("falling back to bm25" in record.message for record in caplog.records)


def test_hybrid_backend_selected_and_knobs_threaded(repository, monkeypatch):
    monkeypatch.setattr(
        "app.retrieval.embedder.SentenceTransformerEmbedder",
        lambda model_name: FakeEmbedder(axes=(("food",),)),
    )
    settings = Settings(
        _env_file=None, retriever_backend="hybrid", rrf_k=7, min_semantic_similarity=0.5
    )
    retriever = build_retriever(settings, repository)
    assert isinstance(retriever, HybridRetriever)
    assert retriever._rrf_k == 7
    assert retriever._min_similarity == 0.5


def test_unknown_backend_warns_and_uses_bm25(repository, caplog):
    settings = Settings(_env_file=None, retriever_backend="quantum")
    with caplog.at_level(logging.WARNING, logger="app.retrieval.factory"):
        retriever = build_retriever(settings, repository)
    assert isinstance(retriever, BM25Retriever)
    assert any("unknown retriever backend" in record.message for record in caplog.records)
