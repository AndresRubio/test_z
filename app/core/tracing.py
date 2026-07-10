import logging
from contextlib import contextmanager

from openinference.semconv.trace import DocumentAttributes, SpanAttributes
from opentelemetry import trace

from app.core.config import Settings

logger = logging.getLogger(__name__)

_TRACER_NAME = "assistant"


def setup_tracing(settings: Settings) -> bool:
    """Install the Phoenix tracer provider when ZA_TRACING_ENABLED=true.

    Disabled (default): nothing is installed; get_tracer() yields OpenTelemetry's
    no-op tracer and every helper below becomes a no-op."""
    if not settings.tracing_enabled:
        return False
    from phoenix.otel import register  # lazy: never imported when disabled

    register(
        endpoint=settings.phoenix_endpoint,
        project_name=settings.phoenix_project_name,
        batch=True,
        set_global_tracer_provider=True,
    )
    logger.info("Phoenix tracing enabled -> %s", settings.phoenix_endpoint)
    return True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def span(name: str, kind: str, input_value: str | None = None):
    """OpenInference-annotated span. kind: CHAIN | LLM | RETRIEVER | GUARDRAIL."""
    with get_tracer().start_as_current_span(name) as otel_span:
        otel_span.set_attribute(SpanAttributes.OPENINFERENCE_SPAN_KIND, kind)
        if input_value is not None:
            otel_span.set_attribute(SpanAttributes.INPUT_VALUE, input_value)
        yield otel_span


def set_output(otel_span, value: str) -> None:
    otel_span.set_attribute(SpanAttributes.OUTPUT_VALUE, value)


def set_retrieved_documents(otel_span, documents: list[tuple[str, str, float]]) -> None:
    """documents: (id, content, score) triples in rank order."""
    for i, (doc_id, content, score) in enumerate(documents):
        prefix = f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}."
        otel_span.set_attribute(prefix + DocumentAttributes.DOCUMENT_ID, doc_id)
        otel_span.set_attribute(prefix + DocumentAttributes.DOCUMENT_CONTENT, content)
        otel_span.set_attribute(prefix + DocumentAttributes.DOCUMENT_SCORE, score)


def set_llm_details(
    otel_span,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    otel_span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model)
    if prompt_tokens is not None:
        otel_span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, prompt_tokens)
    if completion_tokens is not None:
        otel_span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, completion_tokens)
