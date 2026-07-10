from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration; every value overridable via ZA_* env vars."""

    model_config = SettingsConfigDict(env_prefix="ZA_", env_file=".env")

    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "gemma4:e4b"  # Generator (ADR 0002)
    judge_model: str = "gemma4:e2b"  # Judge — tiny model (ADR 0002)
    top_k: int = 5
    # Retrieval backend (ADR 0003): "bm25" (default, zero extra deps) or
    # "hybrid" (BM25 + embedding cosine fused with RRF; needs the optional
    # `semantic` extra — falls back to bm25 with a warning if unavailable).
    retriever_backend: str = "bm25"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rrf_k: int = 60  # RRF constant: higher spreads rank credit deeper into each list
    min_semantic_similarity: float = 0.25  # cosine floor; analog of BM25's score > 0
    context_chars_per_product: int = 600
    # Pacing for streamed static templates (e.g. greetings): a small per-word
    # delay so the typing effect is visible instead of arriving in one burst.
    greeting_stream_delay_seconds: float = 0.035
    llm_timeout_seconds: float = 60.0
    temperature: float = 0.2
    catalog_path: Path = Path("product_catalog_dataset.json")
    max_plausible_price: float = 500.0  # ingest quarantine threshold
    tracing_enabled: bool = False
    phoenix_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "assistant"
