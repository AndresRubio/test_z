import httpx

from app.core.errors import LLMUnavailableError


class OllamaClient:
    """Thin async wrapper around the Ollama HTTP chat API.

    The one seam every test substitutes; a hosted provider client can replace
    it for production without touching the pipeline (PRD story 23)."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        )

    async def chat(
        self,
        model: str,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> str:
        payload: dict = {
            "model": model,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama chat call failed: {exc}") from exc
        try:
            return response.json()["message"]["content"]
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMUnavailableError(f"Ollama chat returned an unexpected body: {exc}") from exc

    async def is_reachable(self) -> bool:
        try:
            response = await self._client.get("/api/tags", timeout=2.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
