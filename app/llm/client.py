import json
from collections.abc import AsyncIterator

import httpx

from app.core.errors import LLMUnavailableError
from app.core.tracing import set_llm_details, set_output, span


class OllamaClient:
    """Thin async wrapper around the Ollama HTTP chat API.

    The one seam every test substitutes; a hosted provider client can replace
    it for production without touching the pipeline (PRD story 23)."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        *,
        num_thread: int | None = None,
        num_ctx: int = 4096,
        top_p: float = 0.9,
        keep_alive: str = "30m",
    ):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        )
        self._num_thread = num_thread
        self._num_ctx = num_ctx
        self._top_p = top_p
        self._keep_alive = keep_alive

    def _options(self, temperature: float, num_predict: int | None = None) -> dict:
        """Per-call Ollama `options`: only keys that are actually set are sent,
        so an unset num_thread leaves Ollama's own auto-detection in charge."""
        options: dict = {
            "temperature": temperature,
            "num_ctx": self._num_ctx,
            "top_p": self._top_p,
        }
        if self._num_thread is not None:
            options["num_thread"] = self._num_thread
        if num_predict is not None:
            options["num_predict"] = num_predict
        return options

    @staticmethod
    def _messages(system: str, history: list[dict[str, str]] | None, user: str) -> list[dict]:
        """system, then the client-resent prior turns, then the current user
        message — the stateless multi-turn shape (design doc § Multi-turn)."""
        return [
            {"role": "system", "content": system},
            *(history or []),
            {"role": "user", "content": user},
        ]

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        json_mode: bool = False,
        history: list[dict[str, str]] | None = None,
        num_predict: int | None = None,
    ) -> str:
        payload: dict = {
            "model": model,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": self._options(temperature, num_predict),
            "messages": self._messages(system, history, user),
        }
        if json_mode:
            payload["format"] = "json"
        with span("ollama.chat", "LLM", input_value=user) as llm_span:
            try:
                response = await self._client.post("/api/chat", json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(f"Ollama chat call failed: {exc}") from exc
            try:
                data = response.json()
                content = data["message"]["content"]
            except (KeyError, TypeError, ValueError) as exc:
                raise LLMUnavailableError(
                    f"Ollama chat returned an unexpected body: {exc}"
                ) from exc
            set_llm_details(
                llm_span,
                model=model,
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
            )
            set_output(llm_span, content)
            return content

    async def chat_stream(
        self,
        model: str,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """Streaming variant of chat: yields content deltas as Ollama emits
        them (NDJSON lines). The final line carries the token counts, so the
        LLM span keeps the same attributes as the non-streaming path."""
        payload: dict = {
            "model": model,
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": self._options(temperature),
            "messages": self._messages(system, history, user),
        }
        with span("ollama.chat", "LLM", input_value=user) as llm_span:
            chunks: list[str] = []
            prompt_tokens: int | None = None
            completion_tokens: int | None = None
            try:
                async with self._client.stream("POST", "/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except ValueError as exc:
                            raise LLMUnavailableError(
                                f"Ollama stream returned a non-JSON line: {exc}"
                            ) from exc
                        delta = (data.get("message") or {}).get("content", "")
                        if delta:
                            chunks.append(delta)
                            yield delta
                        if data.get("done"):
                            prompt_tokens = data.get("prompt_eval_count")
                            completion_tokens = data.get("eval_count")
            except httpx.HTTPError as exc:
                raise LLMUnavailableError(f"Ollama streaming chat call failed: {exc}") from exc
            set_llm_details(
                llm_span,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            set_output(llm_span, "".join(chunks))

    async def is_reachable(self) -> bool:
        try:
            response = await self._client.get("/api/tags", timeout=2.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
