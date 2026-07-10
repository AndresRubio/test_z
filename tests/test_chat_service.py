import logging

import pytest

from app.catalog.repository import CatalogRepository
from app.chat.service import ChatResult, ChatService
from app.core.config import Settings
from app.core.errors import LLMUnavailableError, UnknownSiteError
from app.llm.prompts import DECLINES, NO_MATCH_ANSWERS
from app.retrieval.base import ScoredVariant
from tests.helpers import FakeLLM, make_variant

SETTINGS = Settings(_env_file=None)


class FakeJudge:
    def __init__(self, verdict: bool):
        self.verdict = verdict
        self.calls = []

    async def is_on_topic(self, query):
        self.calls.append(query)
        return self.verdict


class FakeRetriever:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def retrieve(self, site_id, query, k):
        self.calls.append((site_id, query, k))
        return self.results


def _repository():
    return CatalogRepository(
        [
            make_variant(site_id=1, locale="de-DE", currency="EUR"),
            make_variant(variant_id="2.0", site_id=3, locale="en-GB", currency="GBP"),
            make_variant(variant_id="3.0", site_id=15, locale="es-ES", currency="EUR"),
        ]
    )


def _service(verdict=True, results=None, llm=None):
    judge = FakeJudge(verdict)
    retriever = FakeRetriever(results if results is not None else [])
    llm = llm or FakeLLM(responses=["generated answer"])
    service = ChatService(
        judge=judge,
        retriever=retriever,
        llm=llm,
        repository=_repository(),
        settings=SETTINGS,
    )
    return service, judge, retriever, llm


async def test_happy_path_returns_answer_and_products():
    scored = [ScoredVariant(variant=make_variant(), score=2.0)]
    service, _, retriever, llm = _service(results=scored)
    result = await service.handle(1, "bestes Spielzeug für meinen Hund?")
    assert result == ChatResult(answer="generated answer", products=scored)
    assert retriever.calls == [(1, "bestes Spielzeug für meinen Hund?", SETTINGS.top_k)]
    generation_call = llm.calls[-1]
    assert generation_call["model"] == SETTINGS.chat_model
    assert "Test Product" in generation_call["user"]
    assert "German" in generation_call["system"]  # Site 1 answers in German


async def test_generation_language_follows_site_not_query():
    scored = [ScoredVariant(variant=make_variant(site_id=15), score=1.0)]
    service, _, _, llm = _service(results=scored)
    await service.handle(15, "dry food for my dog")  # English query, Spanish Site
    assert "Spanish" in llm.calls[-1]["system"]


async def test_unknown_site_raises_before_any_llm_call():
    service, judge, retriever, llm = _service()
    with pytest.raises(UnknownSiteError):
        await service.handle(99, "dog food")
    assert judge.calls == []
    assert retriever.calls == []
    assert llm.calls == []


async def test_off_topic_declines_in_site_locale_without_retrieval_or_generation():
    service, _, retriever, llm = _service(verdict=False)
    result = await service.handle(1, "What's the weather today?")
    assert result.answer == DECLINES["de-DE"]
    assert result.products == []
    assert retriever.calls == []
    assert llm.calls == []  # decline is a static template — zero LLM calls


async def test_off_topic_decline_is_localized_per_site():
    for site_id, locale in ((3, "en-GB"), (15, "es-ES")):
        service, _, _, _ = _service(verdict=False)
        result = await service.handle(site_id, "weather?")
        assert result.answer == DECLINES[locale]


async def test_no_match_uses_localized_template_without_generation():
    service, _, _, llm = _service(results=[])
    result = await service.handle(3, "purple unicorn saddle")
    assert result.answer == NO_MATCH_ANSWERS["en-GB"]
    assert result.products == []
    assert llm.calls == []


async def test_generation_failure_propagates():
    scored = [ScoredVariant(variant=make_variant(), score=2.0)]
    service, _, _, _ = _service(results=scored, llm=FakeLLM(error=LLMUnavailableError("down")))
    with pytest.raises(LLMUnavailableError):
        await service.handle(1, "bestes Hundefutter?")


async def test_stage_timings_are_logged(caplog):
    scored = [ScoredVariant(variant=make_variant(), score=2.0)]
    service, _, _, _ = _service(results=scored)
    with caplog.at_level(logging.INFO):
        await service.handle(1, "Hundespielzeug")
    stages = {r.stage for r in caplog.records if hasattr(r, "stage")}
    assert {"judge", "retrieve", "generate"} <= stages
    assert all(hasattr(r, "duration_ms") for r in caplog.records if hasattr(r, "stage"))
