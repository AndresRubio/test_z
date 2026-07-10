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


def test_tracing_defaults():
    s = Settings(_env_file=None)
    assert s.tracing_enabled is False
    assert s.phoenix_endpoint == "http://localhost:6006/v1/traces"
    assert s.phoenix_project_name == "assistant"
