# Web UI for manual testing and demos — design

**Date:** 2026-07-10

**Status:** implemented · partially superseded — the console gained SSE
streaming the same evening and `history` resending for multi-turn the next
day; see `docs/specs/streaming/2026-07-10-chat-sse-streaming-design.md` and
`docs/specs/conversation/2026-07-11-conversational-improvements-design.md`.

## Goal

A browser UI to exercise the Assistant API, replacing curl for day-to-day
testing while being clean enough to demo. It is a **pure client** of the
existing API: it uses only what `POST /chat` and `GET /health` already return.
No backend, schema, or pipeline changes.

## Decisions made during brainstorming

- **Audience:** both a dev test harness and a demo surface ("both").
- **Depth:** pure client; no debug/introspection endpoint is added.
- **Approach:** hand-rolled static page served by the existing FastAPI app.
  Gradio and Chainlit were considered and rejected: heavy dependency trees,
  a second process/port, and theme systems that fight exact brand styling.
- **Brand constraint:** the client's brand name never appears in any file
  (per AGENTS.md). The UI matches the look of the client's public site via
  **sampled hex values only**, stored under neutral CSS custom-property names
  (`--brand-primary`, `--brand-accent`, `--surface`, …). No logo, no brand
  name, no downloaded assets.

## Architecture

- New module `app/ui/` containing `static/index.html` — one self-contained
  file with inline CSS and JS. No build step, no framework, no new
  dependencies (`pyproject.toml` untouched).
- A small UI router in `app/ui/` serves the file at `GET /`; `create_app`
  includes it. `app/api/routes.py` stays JSON-only (true at the time — it now
  also serves the SSE stream; see the status note above).
- Run flow is unchanged: `uv run uvicorn app.main:app`, then open
  `http://localhost:8000/`.

## Layout & behavior

Single screen, chat-style:

- **Header:** app title, Site picker (dropdown populated from `/health`
  `sites`), status pill for Ollama reachable/unreachable from the same call.
- **Transcript:** user and assistant bubbles. An assistant reply renders the
  `answer` text plus a card grid of `retrieved_products`: product/variant
  name, brand, pet-type chip, price + currency, discount badge, star rating
  with count, in/out-of-stock badge. Each reply has a "view raw JSON" toggle.
- **Composer:** text input + send button, Enter to send; input disabled with
  a typing indicator while a request is in flight.
- Exchanges were stateless, matching the API at the time (the server still
  is; the console now resends `history` client-side — see the status note
  above). Switching Site mid-session applies to the next message only.

## Error handling

- `503` (Generator unreachable — conditional by design) → warning-styled
  system bubble; network errors render the same way.
- `404` unknown site cannot occur via the dropdown; blank queries are blocked
  client-side, mirroring the API's `422` validation.
- If `/health` fails on load, show a "server not running?" banner instead of
  an empty site picker, with a retry button.

## Testing & docs

- `tests/test_ui.py`, offline like the rest of the suite: `GET /` returns
  200 with `text/html` and the page references `/chat`.
- A test asserting the brand name is *absent* would itself have to contain
  the name, so that constraint remains a review-discipline rule, not a test.
- README and AGENTS.md get a short note documenting the UI URL.
- `scripts/smoke.sh`, evals, and all existing tests are untouched.

## Out of scope

- Streaming (the API did not stream at the time — since shipped, see the
  status note above).
- Conversation memory / multi-turn context (the API is stateless; client-side
  `history` resending was added later — same note).
- Pipeline introspection (Judge verdict, BM25 scores, timings) — would
  require API changes; revisit only if the pure client proves insufficient.
