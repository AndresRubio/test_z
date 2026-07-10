import json
import logging

from app.core.errors import LLMUnavailableError
from app.core.tracing import set_output, span
from app.llm.prompts import JUDGE_SYSTEM, judge_user_prompt

logger = logging.getLogger(__name__)


class Judge:
    """Pipeline stage 1: prompt-only topicality verdict on the tiny model.

    Fails open on any failure — a false decline hurts customers more than an
    answer that is grounded in catalog data anyway (PRD trade-off)."""

    def __init__(self, llm, model: str, num_predict: int = 16):
        self._llm = llm
        self._model = model
        # The verdict is a tiny JSON boolean — cap generation so the model
        # stops early instead of running to its default token limit.
        self._num_predict = num_predict

    async def is_on_topic(self, query: str) -> bool:
        with span("judge", "GUARDRAIL", input_value=query) as judge_span:
            verdict = await self._classify(query)
            set_output(judge_span, str(verdict))
            return verdict

    async def _classify(self, query: str) -> bool:
        try:
            raw = await self._llm.chat(
                model=self._model,
                system=JUDGE_SYSTEM,
                user=judge_user_prompt(query),
                temperature=0.0,
                json_mode=True,
                num_predict=self._num_predict,
            )
        except LLMUnavailableError as exc:
            logger.warning("judge unavailable (%s); failing open", exc)
            return True
        try:
            verdict = json.loads(raw).get("on_topic")
        except (json.JSONDecodeError, AttributeError, TypeError):
            verdict = None
        if isinstance(verdict, bool):
            return verdict
        logger.warning("judge verdict unparseable (%r); failing open", raw)
        return True
