# Design: Opt-in SSE streaming on POST /chat

**Date:** 2026-07-10
**Status:** Implemented (see this plan's commits on main)
**Motivation:** Generation takes ~30s wall-clock on local Ollama. Streaming is
the cheapest fix for the *perceived* latency: product cards appear ~1–2s in
(after retrieval), and the answer types itself out as tokens arrive.

## Decisions made during brainstorming

1. **Same endpoint, opt-in flag** — `stream: bool = False` on `ChatRequest`
   (OpenAI/Ollama convention), not a separate route and not SSE-by-default.
   With `stream` false or omitted, `POST /chat` behaves byte-for-byte as today:
   the eval harness, smoke script, tests, and README examples stay untouched.
2. **Staged events** — the stream delivers `retrieved` (cards) as soon as
   retrieval finishes, then `token` deltas, then a terminal `done`. Not
   tokens-only: early cards are half the perceived-latency win.
3. **Per-event validation, with the trade-off stated in code** — see below.

## Contract

`POST /chat` with `"stream": true` responds `200 text/event-stream`. Frames:

| event       | data model        | when                                        |
|-------------|-------------------|---------------------------------------------|
| `retrieved` | `RetrievedEvent`  | once, when retrieval completes (skipped on decline/no-match) |
| `token`     | `TokenEvent`      | one per generation delta                     |
| `done`      | `DoneEvent`       | terminal on every successful turn            |
| `error`     | `ErrorEvent`      | terminal, only on mid-stream failure         |

Decline and no-match turns emit a single `done` frame carrying the static
template answer — same cost profile as today (decline = one Judge call, zero
Generator calls).

## Event models (the validation answer)

FastAPI's `response_model` cannot validate a `StreamingResponse`, so
whole-response validation moves one layer down: every frame is constructed as
a Pydantic model in `app/api/schemas.py` and serialized with
`model_dump_json()` — nothing goes on the wire that didn't pass a model.

```python
class RetrievedEvent(BaseModel):
    retrieved_products: RetrievedProducts  # reuses the /chat card models verbatim

class TokenEvent(BaseModel):
    delta: str

class DoneEvent(BaseModel):
    answer: str  # full accumulated answer — client-side checksum/replace

class ErrorEvent(BaseModel):
    detail: str
```

One helper renders frames — `sse_frame(event: BaseModel) -> str`, which looks
the wire name up in an `EVENT_NAMES` type registry →
`event: {name}\ndata: {model_dump_json()}\n\n` — and is the only place frame
text is assembled. It accepts only the four registered event models —
anything else fails the registry lookup.

**Required code comment (demo requirement).** At the streaming branch in
`app/api/routes.py`, this comment must appear, stating the validation
trade-off and the alternatives with their costs:

```python
# Streaming trades whole-response validation for latency: FastAPI cannot
# apply `response_model` to a StreamingResponse, so validation is per-event
# (every frame is a Pydantic model from api/schemas.py, never a hand-built
# dict). If per-frame guarantees ever aren't enough, the alternatives are:
# buffer the complete answer and validate it before sending — which gives
# back the ~30s perceived latency this endpoint exists to hide — or make
# non-streaming fast enough to not need SSE via a faster inference server,
# which trades hosted-GPU cost against free local Ollama.
```

## Layering — one addition per existing layer

- **`OllamaClient.chat_stream(...)`** (`app/llm/client.py`): async generator;
  identical payload to `chat` but `"stream": True`; iterates Ollama's NDJSON
  lines and yields `message.content` deltas. Ollama's final NDJSON object
  carries `prompt_eval_count`/`eval_count`, so the `ollama.chat` LLM span
  keeps its token counts; `set_output` receives the accumulated text.
- **`ChatService.handle_stream(site_id, query)`** (`app/chat/service.py`):
  async generator yielding event models. Site resolution, Judge, and
  Retriever run exactly as in `_handle_inner` — same spans, same `_timed`
  stage logging. Yields `RetrievedEvent` after retrieval, `TokenEvent` per
  delta, `DoneEvent` last.
- **Route** (`app/api/routes.py`): `if payload.stream: return
  StreamingResponse(...)`; else the existing path, character-for-character.
- **No changes** to Judge, Retriever, repository, config, or prompts.

## Error handling

Once the first byte streams, HTTP 200 is committed — mid-stream failures
cannot become status codes. Rules:

- **Pre-stream failures keep their status codes.** Unknown site → 404 and
  judge-stage `LLMUnavailableError` → 503 both occur before the response
  starts, because the service generator runs judge (and raises) before the
  route begins streaming. The route awaits the generator's first event before
  constructing the `StreamingResponse` to guarantee this.
- **Mid-stream generation failure** → terminal `ErrorEvent` frame, stream
  closes. Never a silent truncation.
- **Client rule (documented):** a stream that ends without `done` or `error`
  is a transport failure.

## Tracing

The `chat` CHAIN span wraps the generator's full lifetime — it now measures
time-to-last-token. `set_output` gets the accumulated answer. Judge, retrieve,
and LLM spans are unchanged in kind and attributes.

## UI console

`app/ui/static/index.html` (pure client — no backend routes added):
sends `"stream": true`, parses the SSE stream via `fetch` +
`ReadableStream` (`EventSource` cannot POST; no new dependencies), renders
cards on `retrieved`, appends deltas on `token`, finalizes on `done`,
shows the existing error style on `error`. If the response's content-type is
not `text/event-stream`, falls back to the current JSON handling.

## Testing

Existing pattern: substitute the LLM seam.

- Fake `chat_stream` yielding scripted deltas.
- Frame ordering: `retrieved` → `token`\* → `done`.
- Every frame parses back into its event model (closes the validation loop).
- Decline path: single `done`, no `retrieved`, no generator call.
- Mid-stream failure: `error` frame terminates the stream.
- Unknown site with `stream: true` → 404 (pre-stream status preserved).
- **Regression:** `stream: false` and omitted-field responses are unchanged
  against the current `ChatResponse` contract.

## Out of scope

Multi-turn memory, structured citations, token-based context budgeting,
hosted-LLM clients (all tracked in the roadmap). No changes to the eval
harness — it keeps using the non-streaming path.
