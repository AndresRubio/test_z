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


def test_ollama_tuning_defaults():
    s = Settings(_env_file=None)
    assert s.num_thread is None  # None -> Ollama auto-detects
    assert s.num_ctx == 4096
    assert s.top_p == 0.9
    assert s.keep_alive == "30m"
    assert s.judge_num_predict == 16


def test_ollama_tuning_env_override(monkeypatch):
    monkeypatch.setenv("ZA_NUM_THREAD", "8")
    monkeypatch.setenv("ZA_NUM_CTX", "8192")
    monkeypatch.setenv("ZA_TOP_P", "0.5")
    monkeypatch.setenv("ZA_KEEP_ALIVE", "1h")
    monkeypatch.setenv("ZA_JUDGE_NUM_PREDICT", "32")
    s = Settings(_env_file=None)
    assert s.num_thread == 8
    assert s.num_ctx == 8192
    assert s.top_p == 0.5
    assert s.keep_alive == "1h"
    assert s.judge_num_predict == 32
