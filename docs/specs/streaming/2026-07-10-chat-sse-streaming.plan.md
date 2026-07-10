# Opt-in SSE Streaming on POST /chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `stream: true` to `POST /chat` so it responds with SSE — product cards ~1–2s in, then answer tokens as they generate — while the non-streaming path stays byte-for-byte unchanged.

**Architecture:** One addition per existing layer: `OllamaClient.chat_stream` (async generator over Ollama NDJSON), `ChatService.handle_stream` (async generator yielding validated event models), a streaming branch in the route (`StreamingResponse`), and SSE consumption in the static web console. Every SSE frame is built from a Pydantic model — never a hand-built dict — and rendered by a single `sse_frame` helper.

**Tech Stack:** FastAPI `StreamingResponse`, httpx `.stream()` NDJSON iteration, Pydantic v2, vanilla JS `fetch` + `ReadableStream` (no new dependencies anywhere).

**Spec:** `docs/specs/streaming/2026-07-10-chat-sse-streaming-design.md` (approved). Read it first.

## Global Constraints

- **`uv` + Python 3.12 only.** Run everything as `uv run pytest …` / `uv run ruff check .`. Never `pip install`, never `python3 -m venv`.
- **Never write the client's brand name** into any file — code, docs, comments, or commit messages. The `ZA_` env-var prefix is the one deliberate exception.
- **`Coding Task.docx` is gitignored** and must never be committed or referenced.
- **`app/ui` is a pure client** — no backend routes may be added for the UI.
- **Non-streaming `/chat` responses must be byte-for-byte unchanged.** The eval harness, smoke script, and README examples depend on it.
- **Stage git changes with explicit paths** (`git add <paths>`), never `git add -A` — other sessions may share this checkout.
- **No new dependencies.** Standard library, existing FastAPI/httpx/Pydantic, vanilla JS only.

---

### Task 1: SSE event models and the frame helper

**Files:**
- Modify: `app/api/schemas.py` (append after `ChatResponse`)
- Create: `app/api/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Consumes: `RetrievedProducts` (existing, `app/api/schemas.py`)
- Produces: `RetrievedEvent(retrieved_products: RetrievedProducts)`, `TokenEvent(delta: str)`, `DoneEvent(answer: str)`, `ErrorEvent(detail: str)` — all in `app.api.schemas`; `sse_frame(event) -> str` and `EVENT_NAMES: dict[type, str]` in `app.api.sse`. Tasks 3 and 4 import these exact names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sse.py`:

```python
import json

import pytest
from pydantic import BaseModel

from app.api.schemas import (
    DoneEvent,
    ErrorEvent,
    ProductCard,
    RetrievedEvent,
    RetrievedProducts,
    TokenEvent,
)
from app.api.sse import EVENT_NAMES, sse_frame
from app.retrieval.base import ScoredVariant
from tests.helpers import make_variant


def _retrieved_event():
    card = ProductCard.from_scored(ScoredVariant(variant=make_variant(), score=1.0))
    return RetrievedEvent(retrieved_products=RetrievedProducts(products=[card], count=1))


def test_every_event_type_has_a_wire_name():
    assert EVENT_NAMES == {
        RetrievedEvent: "retrieved",
        TokenEvent: "token",
        DoneEvent: "done",
        ErrorEvent: "error",
    }


@pytest.mark.parametrize(
    ("event", "name"),
    [
        (TokenEvent(delta="Hel"), "token"),
        (DoneEvent(answer="Hello"), "done"),
        (ErrorEvent(detail="the model became unavailable"), "error"),
    ],
)
def test_sse_frame_format(event, name):
    frame = sse_frame(event)
    assert frame == f"event: {name}\ndata: {event.model_dump_json()}\n\n"


def test_sse_frame_data_is_single_line_json():
    frame = sse_frame(_retrieved_event())
    lines = frame.rstrip("\n").split("\n")
    assert lines[0] == "event: retrieved"
    assert lines[1].startswith("data: ")
    payload = json.loads(lines[1][len("data: ") :])
    assert payload["retrieved_products"]["count"] == 1
    assert payload["retrieved_products"]["products"][0]["product_name"] == "Test Product"


def test_sse_frame_rejects_unregistered_models():
    class NotAnEvent(BaseModel):
        x: int

    with pytest.raises(KeyError):
        sse_frame(NotAnEvent(x=1))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_sse.py -v`
Expected: FAIL — `ImportError: cannot import name 'RetrievedEvent'`.

- [ ] **Step 3: Implement the models and helper**

Append to `app/api/schemas.py` (after `ChatResponse`, before `HealthResponse`):

```python
class RetrievedEvent(BaseModel):
    """SSE `retrieved`: sent once, the moment retrieval completes."""

    retrieved_products: RetrievedProducts


class TokenEvent(BaseModel):
    """SSE `token`: one incremental answer delta."""

    delta: str


class DoneEvent(BaseModel):
    """SSE `done`: terminal on success; carries the full accumulated answer."""

    answer: str


class ErrorEvent(BaseModel):
    """SSE `error`: terminal on mid-stream failure (HTTP 200 is already sent)."""

    detail: str
```

Create `app/api/sse.py`:

```python
from pydantic import BaseModel

from app.api.schemas import DoneEvent, ErrorEvent, RetrievedEvent, TokenEvent

EVENT_NAMES: dict[type, str] = {
    RetrievedEvent: "retrieved",
    TokenEvent: "token",
    DoneEvent: "done",
    ErrorEvent: "error",
}


def sse_frame(event: BaseModel) -> str:
    """The only place SSE frame text is assembled. Accepts only the four
    registered event models — every byte on the wire went through Pydantic."""
    name = EVENT_NAMES[type(event)]
    return f"event: {name}\ndata: {event.model_dump_json()}\n\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_sse.py -v`
Expected: 6 passed (4 test functions, one parametrized ×3).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check app/api/schemas.py app/api/sse.py tests/test_sse.py
git add app/api/schemas.py app/api/sse.py tests/test_sse.py
git commit -m "feat(api): SSE event models and single frame helper"
```

---

### Task 2: OllamaClient.chat_stream

**Files:**
- Modify: `app/llm/client.py`
- Test: `tests/test_ollama_client.py` (append)

**Interfaces:**
- Consumes: existing `span`, `set_llm_details`, `set_output` from `app.core.tracing`; `LLMUnavailableError` from `app.core.errors`.
- Produces: `OllamaClient.chat_stream(model: str, system: str, user: str, *, temperature: float = 0.0) -> AsyncIterator[str]` — yields content deltas; raises `LLMUnavailableError` on transport/HTTP/malformed-line failure. Task 3's fake mirrors this signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ollama_client.py`:

```python
def _ndjson(*objects):
    return ("\n".join(json.dumps(o) for o in objects) + "\n").encode()


async def test_chat_stream_yields_deltas_and_sets_stream_true():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=_ndjson(
                {"message": {"role": "assistant", "content": "Hel"}, "done": False},
                {"message": {"role": "assistant", "content": "lo"}, "done": False},
                {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "prompt_eval_count": 5,
                    "eval_count": 2,
                },
            ),
        )

    client = make_client(handler)
    deltas = [d async for d in client.chat_stream("gemma4:e4b", "sys", "user msg", temperature=0.7)]
    assert deltas == ["Hel", "lo"]
    assert captured["json"]["stream"] is True
    assert captured["json"]["model"] == "gemma4:e4b"
    assert captured["json"]["options"]["temperature"] == 0.7
    assert captured["json"]["messages"][0] == {"role": "system", "content": "sys"}
    assert captured["json"]["messages"][1] == {"role": "user", "content": "user msg"}


async def test_chat_stream_connect_error_raises_llm_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = make_client(handler)
    with pytest.raises(LLMUnavailableError):
        async for _ in client.chat_stream("m", "s", "u"):
            pass


async def test_chat_stream_http_error_status_raises_llm_unavailable():
    client = make_client(lambda req: httpx.Response(500, content=b'{"error": "boom"}'))
    with pytest.raises(LLMUnavailableError):
        async for _ in client.chat_stream("m", "s", "u"):
            pass


async def test_chat_stream_malformed_line_raises_llm_unavailable():
    client = make_client(lambda req: httpx.Response(200, content=b"not json\n"))
    with pytest.raises(LLMUnavailableError):
        async for _ in client.chat_stream("m", "s", "u"):
            pass


async def test_chat_stream_skips_blank_lines_and_empty_deltas():
    content = _ndjson(
        {"message": {"content": "Hi"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ).replace(b"\n", b"\n\n")  # inject blank lines between records
    client = make_client(lambda req: httpx.Response(200, content=content))
    deltas = [d async for d in client.chat_stream("m", "s", "u")]
    assert deltas == ["Hi"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ollama_client.py -v -k chat_stream`
Expected: 5 FAIL — `AttributeError: 'OllamaClient' object has no attribute 'chat_stream'`.

- [ ] **Step 3: Implement chat_stream**

In `app/llm/client.py`, add `import json` and `from collections.abc import AsyncIterator` at the top, then add this method to `OllamaClient` after `chat`:

```python
    async def chat_stream(
        self,
        model: str,
        system: str,
        user: str,
        *,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        """Streaming variant of chat: yields content deltas as Ollama emits
        them (NDJSON lines). The final line carries the token counts, so the
        LLM span keeps the same attributes as the non-streaming path."""
        payload: dict = {
            "model": model,
            "stream": True,
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
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
```

- [ ] **Step 4: Run the full client test file**

Run: `uv run pytest tests/test_ollama_client.py -v`
Expected: all pass (existing 9 + new 5).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check app/llm/client.py tests/test_ollama_client.py
git add app/llm/client.py tests/test_ollama_client.py
git commit -m "feat(llm): streaming chat over Ollama NDJSON with span token counts"
```

---

### Task 3: ChatService.handle_stream

**Files:**
- Modify: `app/chat/service.py`
- Modify: `tests/helpers.py` (extend `FakeLLM`)
- Test: `tests/test_chat_service.py` (append)

**Interfaces:**
- Consumes: `RetrievedEvent`, `TokenEvent`, `DoneEvent`, `ErrorEvent`, `ProductCard`, `RetrievedProducts` from `app.api.schemas` (Task 1); `chat_stream` signature (Task 2).
- Produces: `ChatService.handle_stream(site_id: int, query: str) -> AsyncIterator[BaseModel]` yielding those event models. Raises `UnknownSiteError` / `LLMUnavailableError` **only before the first event**; after that, failures become a terminal `ErrorEvent`. Task 4 relies on exactly this raise-before-first-event guarantee.

- [ ] **Step 1: Extend FakeLLM with chat_stream**

In `tests/helpers.py`, replace the `FakeLLM.__init__` and add `chat_stream` after `chat`:

```python
    def __init__(self, responses=None, error=None, deltas=None, stream_error=None):
        self.responses = list(responses or [])
        self.error = error
        self.deltas = list(deltas or [])
        self.stream_error = stream_error
        self.calls = []
```

```python
    async def chat_stream(self, model, system, user, *, temperature=0.0):
        self.calls.append(
            {
                "model": model,
                "system": system,
                "user": user,
                "temperature": temperature,
                "streaming": True,
            }
        )
        if self.error is not None:
            raise self.error
        for delta in self.deltas:
            yield delta
        if self.stream_error is not None:
            raise self.stream_error
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_chat_service.py` (add `from app.api.schemas import DoneEvent, ErrorEvent, RetrievedEvent, TokenEvent` to the imports):

```python
async def _events(service, site_id, query):
    return [event async for event in service.handle_stream(site_id, query)]


async def test_stream_happy_path_yields_retrieved_tokens_done():
    scored = [ScoredVariant(variant=make_variant(), score=2.0)]
    llm = FakeLLM(deltas=["Try ", "Test ", "Product"])
    service, _, _, _ = _service(results=scored, llm=llm)
    events = await _events(service, 1, "bestes Hundefutter?")
    assert isinstance(events[0], RetrievedEvent)
    assert events[0].retrieved_products.count == 1
    assert events[0].retrieved_products.products[0].product_name == "Test Product"
    assert [e.delta for e in events[1:-1]] == ["Try ", "Test ", "Product"]
    assert all(isinstance(e, TokenEvent) for e in events[1:-1])
    assert events[-1] == DoneEvent(answer="Try Test Product")
    generation_call = llm.calls[-1]
    assert generation_call["model"] == SETTINGS.chat_model
    assert "German" in generation_call["system"]


async def test_stream_decline_is_single_done_with_zero_generator_calls():
    service, _, retriever, llm = _service(verdict=False)
    events = await _events(service, 1, "What's the weather today?")
    assert events == [DoneEvent(answer=DECLINES["de-DE"])]
    assert retriever.calls == []
    assert llm.calls == []


async def test_stream_no_match_is_single_done():
    service, _, _, llm = _service(results=[])
    events = await _events(service, 3, "purple unicorn saddle")
    assert events == [DoneEvent(answer=NO_MATCH_ANSWERS["en-GB"])]
    assert llm.calls == []


async def test_stream_unknown_site_raises_before_any_event():
    service, judge, _, llm = _service()
    with pytest.raises(UnknownSiteError):
        await _events(service, 99, "dog food")
    assert judge.calls == []
    assert llm.calls == []


async def test_stream_mid_generation_failure_yields_error_event():
    scored = [ScoredVariant(variant=make_variant(), score=2.0)]
    llm = FakeLLM(deltas=["par", "tial"], stream_error=LLMUnavailableError("down"))
    service, _, _, _ = _service(results=scored, llm=llm)
    events = await _events(service, 1, "Hundefutter")
    assert isinstance(events[0], RetrievedEvent)
    assert [e.delta for e in events[1:-1]] == ["par", "tial"]
    assert isinstance(events[-1], ErrorEvent)


async def test_stream_stage_timings_are_logged(caplog):
    scored = [ScoredVariant(variant=make_variant(), score=2.0)]
    service, _, _, _ = _service(results=scored, llm=FakeLLM(deltas=["ok"]))
    with caplog.at_level(logging.INFO):
        await _events(service, 1, "Hundespielzeug")
    stages = {r.stage for r in caplog.records if hasattr(r, "stage")}
    assert {"judge", "retrieve", "generate"} <= stages
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_chat_service.py -v -k stream`
Expected: 6 FAIL — `AttributeError: 'ChatService' object has no attribute 'handle_stream'`.

- [ ] **Step 4: Implement handle_stream**

In `app/chat/service.py`: extend the imports —

```python
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.api.schemas import (
    DoneEvent,
    ErrorEvent,
    ProductCard,
    RetrievedEvent,
    RetrievedProducts,
    TokenEvent,
)
from app.core.errors import LLMUnavailableError
```

then add this method to `ChatService` after `_handle_inner`:

```python
    async def handle_stream(self, site_id: int, query: str) -> AsyncIterator[BaseModel]:
        """Streaming twin of handle(): same Judge/Retriever stages and spans,
        but yields validated SSE event models instead of one ChatResult.
        Raises only before the first event — after that, failures become a
        terminal ErrorEvent because HTTP 200 is already on the wire."""
        with span("chat", "CHAIN", input_value=query) as chat_span:
            chat_span.set_attribute("site_id", site_id)
            site = self._repository.site_for(site_id)  # UnknownSiteError -> 404

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
                async for delta in self._llm.chat_stream(
                    model=self._settings.chat_model,
                    system=generation_system(site.locale),
                    user=generation_user_prompt(query, context),
                    temperature=self._settings.temperature,
                ):
                    parts.append(delta)
                    yield TokenEvent(delta=delta)
            except LLMUnavailableError:
                logger.warning("generation failed mid-stream", extra={"site_id": site_id})
                set_output(chat_span, "".join(parts))
                yield ErrorEvent(
                    detail="The answer could not be completed — the language model became unavailable."
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
```

Note the deliberate duplication of the judge/retrieve stages from `_handle_inner`: the non-streaming path must stay untouched (global constraint), and the two paths diverge at every yield point — sharing them would tangle a frozen code path.

- [ ] **Step 5: Run the full service test file, then the whole suite**

Run: `uv run pytest tests/test_chat_service.py -v` — expected: all pass (existing 8 + new 6).
Run: `uv run pytest` — expected: all pass, no regressions.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check app/chat/service.py tests/helpers.py tests/test_chat_service.py
git add app/chat/service.py tests/helpers.py tests/test_chat_service.py
git commit -m "feat(chat): streaming service path yielding validated SSE events"
```

---

### Task 4: Route streaming branch, stream flag, and the required trade-off comment

**Files:**
- Modify: `app/api/schemas.py` (`ChatRequest`)
- Modify: `app/api/routes.py`
- Test: `tests/test_api.py` (append)

**Interfaces:**
- Consumes: `handle_stream` raise-before-first-event guarantee (Task 3); `sse_frame` (Task 1).
- Produces: `POST /chat` with `"stream": true` → `200 text/event-stream`; `stream` false/omitted → today's JSON path, character-for-character.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py` (add `import json` and `from app.api.schemas import DoneEvent, ErrorEvent, ProductCard, RetrievedEvent, RetrievedProducts, TokenEvent` to the imports):

```python
class StubStreamingChatService:
    """Streaming stand-in: replays scripted events, or raises pre-stream."""

    def __init__(self, events=None, error=None):
        self.events = list(events or [])
        self.error = error

    async def handle_stream(self, site_id, query):
        if self.error is not None:
            raise self.error
        for event in self.events:
            yield event


def _card():
    return ProductCard.from_scored(
        ScoredVariant(variant=make_variant(product_id=42), score=1.5)
    )


def parse_frames(text):
    frames = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n"))
        frames.append((fields["event"], json.loads(fields["data"])))
    return frames


async def test_chat_stream_true_returns_event_stream_in_order():
    events = [
        RetrievedEvent(retrieved_products=RetrievedProducts(products=[_card()], count=1)),
        TokenEvent(delta="Hel"),
        TokenEvent(delta="lo"),
        DoneEvent(answer="Hello"),
    ]
    async with client_for(StubStreamingChatService(events=events)) as client:
        response = await client.post(
            "/chat", json={"site_id": 1, "query": "dog toy", "stream": True}
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = parse_frames(response.text)
    assert [name for name, _ in frames] == ["retrieved", "token", "token", "done"]
    assert frames[0][1]["retrieved_products"]["products"][0]["product_id"] == 42
    assert frames[-1][1] == {"answer": "Hello"}


async def test_chat_stream_decline_is_single_done_frame():
    service = StubStreamingChatService(events=[DoneEvent(answer="I can only help with products.")])
    async with client_for(service) as client:
        response = await client.post(
            "/chat", json={"site_id": 1, "query": "weather", "stream": True}
        )
    assert parse_frames(response.text) == [
        ("done", {"answer": "I can only help with products."})
    ]


async def test_chat_stream_unknown_site_is_a_real_404():
    service = StubStreamingChatService(error=UnknownSiteError(7, [1, 3, 15]))
    async with client_for(service) as client:
        response = await client.post(
            "/chat", json={"site_id": 7, "query": "dog food", "stream": True}
        )
    assert response.status_code == 404


async def test_chat_stream_judge_unavailable_is_a_real_503():
    service = StubStreamingChatService(error=LLMUnavailableError("down"))
    async with client_for(service) as client:
        response = await client.post(
            "/chat", json={"site_id": 1, "query": "dog food", "stream": True}
        )
    assert response.status_code == 503


async def test_chat_stream_mid_stream_failure_ends_with_error_frame():
    events = [
        RetrievedEvent(retrieved_products=RetrievedProducts(products=[_card()], count=1)),
        TokenEvent(delta="par"),
        ErrorEvent(detail="the model became unavailable"),
    ]
    async with client_for(StubStreamingChatService(events=events)) as client:
        response = await client.post(
            "/chat", json={"site_id": 1, "query": "dog food", "stream": True}
        )
    assert response.status_code == 200
    assert [name for name, _ in parse_frames(response.text)] == ["retrieved", "token", "error"]


async def test_chat_stream_false_and_omitted_are_byte_identical():
    scored = ScoredVariant(variant=make_variant(product_id=42), score=1.5)
    result = ChatResult(answer="try this", products=[scored])
    async with client_for(StubChatService(result=result)) as client:
        omitted = await client.post("/chat", json={"site_id": 1, "query": "dog toy"})
        explicit = await client.post(
            "/chat", json={"site_id": 1, "query": "dog toy", "stream": False}
        )
    assert omitted.status_code == explicit.status_code == 200
    assert omitted.headers["content-type"] == explicit.headers["content-type"] == "application/json"
    assert omitted.content == explicit.content
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_api.py -v -k stream`
Expected: FAIL — the `stream` key is rejected with 422 (`ChatRequest` has `extra="forbid"`), so every streaming test errors on status.

- [ ] **Step 3: Add the stream flag to ChatRequest**

In `app/api/schemas.py`, add one field to `ChatRequest` after `query`:

```python
    stream: bool = False
```

- [ ] **Step 4: Implement the streaming branch**

Replace the `chat` route in `app/api/routes.py` with:

```python
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ProductCard,
    RetrievedProducts,
)
from app.api.sse import sse_frame

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    service = request.app.state.chat_service

    if payload.stream:
        # Streaming trades whole-response validation for latency: FastAPI cannot
        # apply `response_model` to a StreamingResponse, so validation is per-event
        # (every frame is a Pydantic model from api/schemas.py, never a hand-built
        # dict). If per-frame guarantees ever aren't enough, the alternatives are:
        # buffer the complete answer and validate it before sending — which gives
        # back the ~30s perceived latency this endpoint exists to hide — or make
        # non-streaming fast enough to not need SSE via a faster inference server,
        # which trades hosted-GPU cost against free local Ollama.
        events = service.handle_stream(payload.site_id, payload.query)
        # Pull the first event before committing the response so pre-stream
        # failures (unknown site, judge-stage LLM down) still map to 404/503.
        first = await anext(events)

        async def frames() -> AsyncIterator[str]:
            yield sse_frame(first)
            async for event in events:
                yield sse_frame(event)

        return StreamingResponse(frames(), media_type="text/event-stream")

    result = await service.handle(payload.site_id, payload.query)
    cards = [ProductCard.from_scored(s) for s in result.products]
    return ChatResponse(
        answer=result.answer,
        retrieved_products=RetrievedProducts(products=cards, count=len(cards)),
    )
```

The required trade-off comment above is verbatim from the spec — do not reword it. `response_model=ChatResponse` stays on the decorator: FastAPI skips it when a `Response` instance is returned, so it still validates the non-streaming path and documents the JSON contract in OpenAPI.

- [ ] **Step 5: Run the full API test file, then the whole suite**

Run: `uv run pytest tests/test_api.py -v` — expected: all pass (existing 13 incl. parametrized + new 6).
Run: `uv run pytest` — expected: all pass.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check app/api/routes.py app/api/schemas.py tests/test_api.py
git add app/api/routes.py app/api/schemas.py tests/test_api.py
git commit -m "feat(api): opt-in SSE streaming on POST /chat behind stream flag"
```

---

### Task 5: Web console consumes the stream

**Files:**
- Modify: `app/ui/static/index.html` (script section only — `app/ui` stays a pure client)
- Test: `tests/test_ui.py` (append)

**Interfaces:**
- Consumes: the SSE contract from Task 4 (`retrieved` / `token` / `done` / `error` frames; non-SSE content type ⇒ JSON fallback).
- Produces: no programmatic interface — user-facing behavior only.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui.py` (match the file's existing `client()` helper and test style):

```python
async def test_console_requests_streaming_and_parses_sse():
    async with client() as c:
        response = await c.get("/")
    assert "stream: true" in response.text  # JS object literal in the fetch body
    assert "text/event-stream" in response.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_ui.py -v`
Expected: the new test FAILS on the `"stream: true"` assertion; existing tests pass.

- [ ] **Step 3: Implement streaming in the console script**

Three edits inside the `<script>` block of `app/ui/static/index.html`.

**(a)** After the `renderAnswer` function, add an SSE reader and a streaming renderer:

```javascript
  async function readSse(response, handlers) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        let event = "";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (event && data && handlers[event]) handlers[event](JSON.parse(data));
      }
    }
  }

  function renderStream(siteId) {
    // Builds the assistant bubble incrementally: meta + cards on `retrieved`,
    // answer text on `token`, raw-JSON details on `done`.
    const wrap = document.createElement("div");
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = "Site " + siteId + " · retrieving…";
    wrap.append(meta);
    const answer = answerNode("");
    wrap.append(answer);
    addBubble("assistant", wrap);

    let retrieved = { products: [], count: 0 };
    let text = "";
    return {
      retrieved(payload) {
        retrieved = payload.retrieved_products;
        meta.textContent = "Site " + siteId + " · " + retrieved.count + " product(s) retrieved";
        if (retrieved.count > 0) {
          const cards = document.createElement("div");
          cards.className = "cards";
          for (const card of retrieved.products) cards.append(renderCard(card));
          wrap.append(cards);
        }
      },
      token(payload) {
        text += payload.delta;
        answer.textContent = text;
      },
      done(payload) {
        meta.textContent = "Site " + siteId + " · " + retrieved.count + " product(s) retrieved";
        answer.textContent = payload.answer;
        const raw = document.createElement("details");
        raw.className = "raw";
        const summary = document.createElement("summary");
        summary.textContent = "raw JSON";
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(
          { answer: payload.answer, retrieved_products: retrieved }, null, 2
        );
        raw.append(summary, pre);
        wrap.append(raw);
      },
      error(payload) {
        addBubble("warning", textNode(payload.detail));
      },
    };
  }
```

If `answerNode("")` produces a node whose text lives in a child element, adjust `answer.textContent` to target that child — check `answerNode`'s definition (around line 354) while implementing.

**(b)** In the submit handler, change the fetch body to request streaming:

```javascript
        body: JSON.stringify({ site_id: siteId, query, stream: true }),
```

**(c)** Replace the `if (response.ok) { … }` success block of the submit handler with:

```javascript
    if (response.ok) {
      const contentType = response.headers.get("content-type") || "";
      try {
        if (contentType.startsWith("text/event-stream")) {
          await readSse(response, renderStream(siteId));
        } else {
          // Fallback: server answered with plain JSON (e.g. older server).
          renderAnswer(siteId, await response.json());
        }
        queryInput.value = ""; // clear only once the reply is shown
      } catch {
        // The server responded, but the body was not the shape we expected.
        addBubble("warning", textNode("Unexpected response from server — the reply could not be read."));
      }
    } else {
```

(The `else` branch and everything after it stay exactly as they are.)

- [ ] **Step 4: Run the UI tests**

Run: `uv run pytest tests/test_ui.py -v`
Expected: all pass.

- [ ] **Step 5: Live verification in the browser**

Requires Ollama running locally with the project's models pulled.

1. Start the app: `uv run uvicorn app.main:create_app --factory --port 8000` (or the repo's documented run command — check README "Setup and Execution" and use that).
2. Open `http://localhost:8000/`, pick Site 1, ask "Welches Hundefutter empfiehlst du?".
3. Confirm: product cards appear after ~1–2s, the answer text grows incrementally, and the final bubble has the raw-JSON details block.
4. Confirm the decline path: ask "What's the weather?" — a single localized decline answer appears, no cards.
5. Stop the server.

If Ollama is not available, verify the wire format instead with the test suite only, and say so explicitly when reporting.

- [ ] **Step 6: Commit**

```bash
git add app/ui/static/index.html tests/test_ui.py
git commit -m "feat(ui): console renders SSE stream — early cards, typing answer"
```

---

### Task 6: Documentation and final verification

**Files:**
- Modify: `README.md` (Setup and Execution — after the `/health` curl example, before the `### PyCharm` heading)
- Modify: `docs/specs/streaming/2026-07-10-chat-sse-streaming-design.md` (status line only)

**Interfaces:**
- Consumes: the shipped contract from Tasks 4–5.
- Produces: user-facing docs; the final green suite.

- [ ] **Step 1: Document streaming in the README**

In `README.md`, after the `curl -s localhost:8000/health | python3 -m json.tool` line (around line 158) and before `### PyCharm`, insert:

````markdown
Streaming (opt-in): add `"stream": true` and the same endpoint answers as
Server-Sent Events — a `retrieved` frame with the product cards as soon as
retrieval finishes, `token` frames as the answer generates, then a terminal
`done` (full answer) or `error` (mid-stream failure; the HTTP status is
already 200 by then). A stream that ends without `done` or `error` is a
transport failure. Declines and no-match answers arrive as a single `done`.

```bash
curl -sN localhost:8000/chat -X POST -H 'Content-Type: application/json' \
  -d '{"site_id": 1, "query": "Welches Hundefutter empfiehlst du?", "stream": true}'
```
````

- [ ] **Step 2: Mark the spec as implemented**

In `docs/specs/streaming/2026-07-10-chat-sse-streaming-design.md`, change the `**Status:**` line to:

```markdown
**Status:** Implemented (see this plan's commits on main)
```

- [ ] **Step 3: Full-suite verification — read the complete output**

```bash
uv run pytest
uv run ruff check .
```

Expected: every test passes (count them against the pre-plan baseline of 123 + the ~18 added by Tasks 1–5), ruff reports no issues. Read the full output, not the tail.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/specs/streaming/2026-07-10-chat-sse-streaming-design.md
git commit -m "docs: document opt-in SSE streaming for POST /chat"
```
