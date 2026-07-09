from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration; every value overridable via ZA_* env vars."""

    model_config = SettingsConfigDict(env_prefix="ZA_", env_file=".env")

    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "gemma4:e4b"  # Generator (ADR 0002)
    judge_model: str = "gemma4:e2b"  # Judge — tiny model (ADR 0002)
    top_k: int = 5
    context_chars_per_product: int = 600
    llm_timeout_seconds: float = 60.0
    temperature: float = 0.2
    catalog_path: Path = Path("product_catalog_dataset.json")
    max_plausible_price: float = 500.0  # ingest quarantine threshold
