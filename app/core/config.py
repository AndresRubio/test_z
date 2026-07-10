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
    # Pacing for streamed static templates (e.g. greetings): a small per-word
    # delay so the typing effect is visible instead of arriving in one burst.
    greeting_stream_delay_seconds: float = 0.035
    llm_timeout_seconds: float = 60.0
    temperature: float = 0.2
    # TO_EXPLAIN — the Ollama tuning story behind the four knobs below.
    # `keep_alive` is the big latency win: without it Ollama unloads a model
    # after ~5 minutes idle and the next call pays a multi-second cold load;
    # "30m" keeps both models warm across a whole demo session. `num_thread`
    # pins inference threads — on Apple Silicon, Ollama's auto choice uses the
    # performance cores, so only set this to claim more (or fewer) cores
    # deliberately; None means "let Ollama decide". `num_ctx` is the context
    # window: bigger fits more product context and history but costs memory and
    # prompt-processing latency roughly linearly — 4096 comfortably holds
    # top_k=5 cards plus 10 history turns. `top_p` bounds nucleus sampling so
    # the low-temperature Generator cannot wander into the long tail. All four
    # ride through OllamaClient's `options`/payload — the same single seam a
    # hosted-LLM client would replace, where these knobs become provider params
    # or disappear (a hosted model is always warm).
    num_thread: int | None = None  # inference CPU threads; None -> Ollama auto
    num_ctx: int = 4096  # context window (tokens)
    top_p: float = 0.9  # nucleus sampling cutoff
    keep_alive: str = "30m"  # keep models loaded between calls
    # The Judge emits a tiny JSON boolean; capping its generation budget stops
    # it early instead of letting it ramble to the model's default limit.
    judge_num_predict: int = 16
    catalog_path: Path = Path("product_catalog_dataset.json")
    max_plausible_price: float = 500.0  # ingest quarantine threshold
    tracing_enabled: bool = False
    phoenix_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "assistant"
