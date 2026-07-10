import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.catalog.repository import CatalogRepository
from app.chat.judge import Judge
from app.chat.service import ChatService
from app.core.config import Settings
from app.core.tracing import setup_tracing
from app.llm.client import OllamaClient
from app.retrieval.base import ScoredVariant
from tests.helpers import FakeLLM, make_variant

# The global provider can be set only once per process; other test modules run
# with the default no-op/proxy tracer, so their spans cost nothing.
_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_PROVIDER)


@pytest.fixture(autouse=True)
def clear_spans():
    _EXPORTER.clear()
    yield


def _finished():
    return {s.name: s for s in _EXPORTER.get_finished_spans()}


def test_setup_tracing_disabled_is_noop():
    assert setup_tracing(Settings(_env_file=None)) is False


def test_setup_tracing_enabled_calls_register(monkeypatch):
    import phoenix.otel

    calls = {}

    def fake_register(**kwargs):
        calls.update(kwargs)
        return _PROVIDER

    monkeypatch.setattr(phoenix.otel, "register", fake_register)
    assert setup_tracing(Settings(_env_file=None, tracing_enabled=True)) is True
    assert calls["endpoint"] == "http://localhost:6006/v1/traces"
    assert calls["project_name"] == "assistant"
    assert calls["batch"] is True


class FakeJudge:
    async def is_on_topic(self, query):
        return True


class FakeRetriever:
    def __init__(self, results):
        self.results = results

    async def retrieve(self, site_id, query, k):
        return self.results


async def test_chat_flow_emits_openinference_spans():
    scored = [ScoredVariant(variant=make_variant(), score=2.5)]
    service = ChatService(
        judge=FakeJudge(), retriever=FakeRetriever(scored),
        llm=FakeLLM(responses=["an answer"]),
        repository=CatalogRepository([make_variant()]),
        settings=Settings(_env_file=None),
    )
    await service.handle(1, "toy for my dog")
    spans = _finished()
    assert {"chat", "retrieve"} <= set(spans)
    chat = spans["chat"].attributes
    assert chat["openinference.span.kind"] == "CHAIN"
    assert chat["input.value"] == "toy for my dog"
    assert chat["output.value"] == "an answer"
    assert chat["site_id"] == 1
    retrieve = spans["retrieve"].attributes
    assert retrieve["openinference.span.kind"] == "RETRIEVER"
    assert retrieve["retrieval.documents.0.document.id"] == "1.0"
    assert retrieve["retrieval.documents.0.document.content"] == "Test Product"
    assert retrieve["retrieval.documents.0.document.score"] == 2.5


async def test_judge_emits_guardrail_span():
    judge = Judge(FakeLLM(responses=['{"on_topic": true}']), "gemma4:e2b")
    assert await judge.is_on_topic("dog food") is True
    guard = _finished()["judge"].attributes
    assert guard["openinference.span.kind"] == "GUARDRAIL"
    assert guard["input.value"] == "dog food"
    assert guard["output.value"] == "True"


async def test_ollama_chat_emits_llm_span_with_token_counts():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "message": {"content": "hi"}, "prompt_eval_count": 12, "eval_count": 5,
        })

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t")
    client = OllamaClient("http://t", 5.0, client=http)
    await client.chat("gemma4:e4b", "sys", "hello")
    llm_span = _finished()["ollama.chat"].attributes
    assert llm_span["openinference.span.kind"] == "LLM"
    assert llm_span["llm.model_name"] == "gemma4:e4b"
    assert llm_span["llm.token_count.prompt"] == 12
    assert llm_span["llm.token_count.completion"] == 5
    assert llm_span["input.value"] == "hello"
    assert llm_span["output.value"] == "hi"
