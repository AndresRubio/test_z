import logging
import time
from dataclasses import dataclass, field

from app.catalog.repository import CatalogRepository
from app.core.config import Settings
from app.core.tracing import set_output, set_retrieved_documents, span
from app.llm.prompts import (
    DECLINES,
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
