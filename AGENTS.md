# Agent instructions

Async **FastAPI RAG chatbot API** ("Assistant") over a per-Site pet-supplies
product catalog, **fully offline via Ollama** (no API keys). `POST /chat` runs a
**Judge → Retriever → Generator** pipeline; `GET /health` reports readiness.

Orientation, in order: domain vocabulary is in `CONTEXT.md` (read it — the terms
Site / Variant / Product Card / Internal Fields are used precisely everywhere),
design rationale in `docs/adr/`, and the graded write-up in `README.md`.

## Hard constraints (non-negotiable)

- **`uv` + Python 3.12 only.** Never `pip install`, never `python3 -m venv`. Use
  `uv sync`, `uv run …`, `uv add …`.
- **Never write the client's brand name** into any file — code, docs, comments,
  or commit messages. The **`ZA_` env-var prefix is the one deliberate
  exception** and stays; do not "normalize" it away.
- **`Coding Task.docx` is gitignored** (it contains the brand name) and must
  never be committed.

## Commands

```bash
uv sync                                   # provision Python 3.12 venv + deps
uv run pytest                             # full suite — offline, no Ollama needed
uv run pytest tests/test_ingest.py -v     # one file
uv run pytest tests/test_ingest.py::test_real_dataset_counts_match_the_known_traps -v   # one test
uv run pytest -k judge -v                 # by keyword
uv run ruff check app tests evals         # lint

uv run uvicorn app.main:app               # run the API (needs Ollama up)
#   …then open http://localhost:8000/ — built-in web test console (app/ui)
scripts/smoke.sh                          # live smoke (needs server + Ollama)
uv run python -m evals.run_eval --base-url http://localhost:8000   # golden-set eval
```

Ollama models (once): `ollama pull gemma4:e2b` (Judge) and `ollama pull gemma4:e4b`
(Generator). Config is env-driven via the `ZA_` prefix — see `.env.example` for
every knob and its default.

## Architecture (the big picture)

The request flow is `app/api/routes.py` → `app/chat/service.py::ChatService.handle`,
which orchestrates three stages, each isolated behind its own module:

1. **Judge** (`app/chat/judge.py`, model `gemma4:e2b`) — prompt-only topicality
   check. **Fails open**: any unparseable/failed verdict proceeds to retrieval
   with a warning. Off-topic → static decline, no further LLM calls.
2. **Retriever** (`app/retrieval/`) — `base.py` defines the `Retriever` Protocol,
   the **deliberate seam** for future vector/hybrid/reranker backends (ADR 0001).
   `bm25.py` is the PoC binding: per-Site BM25, name/brand ×3 boost, `score > 0`.
3. **Generator** (`app/llm/`, model `gemma4:e4b`) — answers **always in the Site
   locale**, regardless of query language (intended; see README).

Cross-cutting design facts that span files and must not be regressed:

- **`ChatService.handle` resolves the Site first** — unknown `site_id` → 404
  *before* any LLM call. Then Judge → decline → retrieve → no-match → generate.
  Declines and no-match answers are **static templates** (zero LLM cost), so a
  **503 only surfaces when a query actually reaches the Generator** (conditional
  by design).
- **`OllamaClient` (`app/llm/client.py`) is the single test seam.** Tests inject a
  fake or an httpx `MockTransport`; nothing else talks to the network. It (a)
  only closes a client it *owns* (`_owns_client`), and (b) maps a malformed 200
  body to `LLMUnavailableError`. Both are hardening fixes — preserve them.
- **Internal Fields are excluded by construction, not by filtering.**
  `app/catalog/models.py` never parses `margin_pct`, `monthly_sales_units`,
  `revenue_last_30d`, or raw `stock_units` into the domain model, so they cannot
  leak into a response. Keep it structural.
- **Ingest (`app/catalog/ingest.py`) applies five data-quality policies** and
  reports counts in an `IngestReport`; the exact counts for the real dataset are
  pinned by `test_real_dataset_counts_match_the_known_traps` — that test is the
  guard if you touch ingest. Note `strip_html` strips tags **then** unescapes,
  deliberately **preserving** decoded operators like `<25kg`; do not re-add
  bracket stripping.
- **Repository (`app/catalog/repository.py`)** hard-partitions Variants by Site;
  Site catalogs are disjoint.
- **Tracing (`app/core/tracing.py`)** is a true no-op unless `ZA_TRACING_ENABLED`;
  the Phoenix/OpenInference import is lazy.
- **`app/ui/` is a pure client.** One static page served at `GET /`
  (excluded from the OpenAPI schema); it consumes only `/chat` and `/health`
  and must never require backend changes.

Tests mirror `app/` one-to-one under `tests/`, are fully offline, and share
doubles from `tests/helpers.py` (`FakeLLM`, factories) and `tests/conftest.py`.

## Known limitations (tracked, intentional)

`evals/golden_set.json` marks one case `known_limitation` (excluded from the
headline count): cross-lingual retrieval (BM25 is language-blind, ADR 0001); the
vector/hybrid path is the designed fix. **Do not mask it by reworking the query**
— hiding a gap was flagged as an integrity gap once already.

The `gemma4:e2b` Judge false-decline (`site15-judge-false-decline`) was a second
known-limitation; it is now **fixed, not masked** — few-shot examples in
`JUDGE_SYSTEM` make the tiny Judge classify the unreworded query correctly while
still declining off-topic, so it is a scored (non-known-limitation) case again.

## Agent skills

### Issue tracker

Issues are tracked as local markdown files under `docs/specs/<feature>/` in this repo; no remote tracker, no PR triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles use their default names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
