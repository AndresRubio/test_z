import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.api.schemas import (
    DoneEvent,
    ErrorEvent,
    ProductCard,
    RetrievedEvent,
    RetrievedProducts,
    TokenEvent,
)
from app.catalog.repository import CatalogRepository
from app.chat.greeting import is_greeting
from app.core.config import Settings
from app.core.errors import LLMUnavailableError
from app.core.tracing import set_output, set_retrieved_documents, span
from app.llm.prompts import (
    DECLINES,
    GREETINGS,
    NO_MATCH_ANSWERS,
    generation_system,
    generation_user_prompt,
    render_product_context,
)
from app.retrieval.base import ScoredVariant

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    answer: str
    products: list[ScoredVariant] = field(default_factory=list)


def _word_deltas(text: str) -> Iterator[str]:
    """Split a static answer into word-sized chunks (each keeps its trailing
    whitespace, so the pieces rejoin to the exact original). Lets the streaming
    path type out a template answer the same way the Generator streams tokens —
    still zero LLM calls."""
    return iter(re.findall(r"\S+\s*", text))


class ChatService:
    """One chat turn: resolve Site -> Judge -> Retriever -> Generator.

    Declines and no-match answers are static templates in the Site locale —
    off-topic traffic never reaches retrieval or generation."""

    def __init__(self, judge, retriever, llm, repository: CatalogRepository, settings: Settings):
        self._judge = judge
        self._retriever = retriever
        self._llm = llm
        self._repository = repository
        self._settings = settings

    async def handle(self, site_id: int, query: str) -> ChatResult:
        with span("chat", "CHAIN", input_value=query) as chat_span:
            chat_span.set_attribute("site_id", site_id)
            result = await self._handle_inner(site_id, query)
            set_output(chat_span, result.answer)
            return result

    async def _handle_inner(self, site_id: int, query: str) -> ChatResult:
        site = self._repository.site_for(site_id)  # UnknownSiteError -> 404

        if is_greeting(query):
            logger.info("greeting fast-path", extra={"site_id": site_id})
            return ChatResult(answer=GREETINGS[site.locale])

        if not await self._timed("judge", self._judge.is_on_topic(query)):
            logger.info("judge declined query", extra={"site_id": site_id})
            return ChatResult(answer=DECLINES[site.locale])

        with span("retrieve", "RETRIEVER", input_value=query) as retrieve_span:
            candidates = await self._timed(
                "retrieve", self._retriever.retrieve(site_id, query, self._settings.top_k)
            )
            set_retrieved_documents(
                retrieve_span,
                [(c.variant.variant_id, c.variant.product_name, c.score) for c in candidates],
            )
        if not candidates:
            logger.info("no Variants matched", extra={"site_id": site_id})
            return ChatResult(answer=NO_MATCH_ANSWERS[site.locale])

        context = render_product_context(candidates, self._settings.context_chars_per_product)
        answer = await self._timed(
            "generate",
            self._llm.chat(
                model=self._settings.chat_model,
                system=generation_system(site.locale),
                user=generation_user_prompt(query, context),
                temperature=self._settings.temperature,
            ),
        )
        return ChatResult(answer=answer, products=candidates)

    async def handle_stream(self, site_id: int, query: str) -> AsyncIterator[BaseModel]:
        """Streaming twin of handle(): same Judge/Retriever stages and spans,
        but yields validated SSE event models instead of one ChatResult.
        Raises only before the first event — after that, failures become a
        terminal ErrorEvent because HTTP 200 is already on the wire."""
        with span("chat", "CHAIN", input_value=query) as chat_span:
            chat_span.set_attribute("site_id", site_id)
            site = self._repository.site_for(site_id)  # UnknownSiteError -> 404

            if is_greeting(query):
                logger.info("greeting fast-path", extra={"site_id": site_id})
                answer = GREETINGS[site.locale]
                pace = self._settings.greeting_stream_delay_seconds
                for i, delta in enumerate(_word_deltas(answer)):
                    if i and pace:
                        await asyncio.sleep(pace)  # visible typing cadence
                    yield TokenEvent(delta=delta)
                set_output(chat_span, answer)
                yield DoneEvent(answer=answer)
                return

            if not await self._timed("judge", self._judge.is_on_topic(query)):
                logger.info("judge declined query", extra={"site_id": site_id})
                answer = DECLINES[site.locale]
                set_output(chat_span, answer)
                yield DoneEvent(answer=answer)
                return

            with span("retrieve", "RETRIEVER", input_value=query) as retrieve_span:
                candidates = await self._timed(
                    "retrieve", self._retriever.retrieve(site_id, query, self._settings.top_k)
                )
                set_retrieved_documents(
                    retrieve_span,
                    [(c.variant.variant_id, c.variant.product_name, c.score) for c in candidates],
                )
            if not candidates:
                logger.info("no Variants matched", extra={"site_id": site_id})
                answer = NO_MATCH_ANSWERS[site.locale]
                set_output(chat_span, answer)
                yield DoneEvent(answer=answer)
                return

            cards = [ProductCard.from_scored(c) for c in candidates]
            yield RetrievedEvent(
                retrieved_products=RetrievedProducts(products=cards, count=len(cards))
            )

            context = render_product_context(candidates, self._settings.context_chars_per_product)
            parts: list[str] = []
            started = time.perf_counter()
            try:
                deltas = self._llm.chat_stream(
                    model=self._settings.chat_model,
                    system=generation_system(site.locale),
                    user=generation_user_prompt(query, context),
                    temperature=self._settings.temperature,
                )
                async with aclosing(deltas):
                    async for delta in deltas:
                        parts.append(delta)
                        yield TokenEvent(delta=delta)
            except LLMUnavailableError:
                logger.warning("generation failed mid-stream", extra={"site_id": site_id})
                set_output(chat_span, "".join(parts))
                yield ErrorEvent(
                    detail="The answer could not be completed — "
                    "the language model became unavailable."
                )
                return
            finally:
                logger.info(
                    "stage complete",
                    extra={
                        "stage": "generate",
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                    },
                )
            answer = "".join(parts)
            set_output(chat_span, answer)
            yield DoneEvent(answer=answer)

    async def _timed(self, stage: str, coro):
        started = time.perf_counter()
        try:
            return await coro
        finally:
            logger.info(
                "stage complete",
                extra={
                    "stage": stage,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
