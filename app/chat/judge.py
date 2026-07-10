import json
import logging

from app.core.errors import LLMUnavailableError
from app.llm.prompts import JUDGE_SYSTEM, judge_user_prompt

logger = logging.getLogger(__name__)


class Judge:
    """Pipeline stage 1: prompt-only topicality verdict on the tiny model.

    Fails open on any failure — a false decline hurts customers more than an
    answer that is grounded in catalog data anyway (PRD trade-off)."""

    def __init__(self, llm, model: str):
        self._llm = llm
        self._model = model

    async def is_on_topic(self, query: str) -> bool:
        try:
            raw = await self._llm.chat(
                model=self._model,
                system=JUDGE_SYSTEM,
                user=judge_user_prompt(query),
                temperature=0.0,
                json_mode=True,
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
