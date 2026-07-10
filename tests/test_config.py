from pathlib import Path

from app.core.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.chat_model == "gemma4:e4b"
    assert s.judge_model == "gemma4:e2b"
    assert s.top_k == 5
    assert s.context_chars_per_product == 600
    assert s.llm_timeout_seconds == 60.0
    assert s.temperature == 0.2
    assert s.catalog_path == Path("product_catalog_dataset.json")
    assert s.max_plausible_price == 500.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("ZA_CHAT_MODEL", "qwen3:8b")
    monkeypatch.setenv("ZA_JUDGE_MODEL", "gemma4:e4b")
    monkeypatch.setenv("ZA_TOP_K", "3")
    s = Settings(_env_file=None)
    assert s.chat_model == "qwen3:8b"
    assert s.judge_model == "gemma4:e4b"
    assert s.top_k == 3


def test_retrieval_defaults():
    s = Settings(_env_file=None)
    assert s.retriever_backend == "bm25"  # hybrid is strictly opt-in (ADR 0003)
    assert s.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert s.rrf_k == 60
    assert s.min_semantic_similarity == 0.25


def test_retrieval_env_override(monkeypatch):
    monkeypatch.setenv("ZA_RETRIEVER_BACKEND", "hybrid")
    monkeypatch.setenv(
        "ZA_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    monkeypatch.setenv("ZA_RRF_K", "20")
    monkeypatch.setenv("ZA_MIN_SEMANTIC_SIMILARITY", "0.4")
    s = Settings(_env_file=None)
    assert s.retriever_backend == "hybrid"
    assert s.embedding_model.endswith("paraphrase-multilingual-MiniLM-L12-v2")
    assert s.rrf_k == 20
    assert s.min_semantic_similarity == 0.4


def test_tracing_defaults():
    s = Settings(_env_file=None)
    assert s.tracing_enabled is False
    assert s.phoenix_endpoint == "http://localhost:6006/v1/traces"
    assert s.phoenix_project_name == "assistant"
