# PROGRESS — Assistant PoC handoff

> Handoff note for an agent picking this up cold. The work is **complete and
> submission-ready**; this file explains what exists, why, and what (little) is
> left to decide. Read this first, then the plan and the README.

## TL;DR status

- **State:** all 15 planned tasks implemented, reviewed, and committed. Final
  whole-branch review returned **submission-ready**; its findings were applied.
- **Git:** branch `main`, HEAD `111cc50`, **25 commits** (one logical unit per
  task + review fixes). Working tree is clean except for one untracked file —
  see [Open items](#open-items--decisions-pending).
- **Tests:** `93 passed, 0 warnings`; `ruff check` clean. (Re-run to confirm —
  commands below.)
- **Live eval:** `11/11` against real Ollama, plus **2 deliberately documented
  known-limitations** (not failures — see below).

## What this is

A proof-of-concept async **FastAPI RAG chatbot API** ("Assistant") over a
per-Site pet-supplies product catalog, **fully offline via Ollama** (no API
keys). Reviewers run it locally. It is a hiring take-home graded on engineering
rigor, RAG/agentic reasoning, data awareness, and trade-off transparency.

Contract:
- `POST /chat {site_id, query}` → `{answer, retrieved_products: {products: [ProductCard], count}}`
- `GET /health`

Pipeline: **Judge → Retriever → Generator**.
- **Judge** (`gemma4:e2b`, tiny): prompt-only topicality check; **fails open**.
- **Retriever**: per-Site **BM25** (`rank-bm25`), name/brand ×3 boost, `score > 0`
  filter, behind a `Retriever` Protocol seam (the designed extension point).
- **Generator** (`gemma4:e4b`, larger): answers **always in the Site locale**.

Sites: 1 = de-DE/EUR, 3 = en-GB/GBP, 15 = es-ES/EUR.

## Hard constraints (do NOT violate)

These are standing rules from the project owner — persisted in memory, not
derivable from the code:

1. **Python 3.12 + `uv` only.** Never `pip install`, never `python3 -m venv`.
   Use `uv sync` / `uv run` / `uv add`.
2. **Never write the client's brand name** into any file (code, docs, comments,
   commits). The README calls it "a multi-shop pet-supplies platform." The one
   deliberate brand-adjacent exception the owner chose to keep is the **`ZA_`
   env-var prefix** — keep it; do not "fix" it.
3. **`Coding Task.docx` is gitignored and must never be committed** (it contains
   the brand name). The `~$…docx` lock file next to it is just Word's open-file
   marker; leave it, it is also ignored.

## Architecture / file map

```
app/
  core/       config.py (Settings, ZA_ prefix)  errors.py  logging.py  tracing.py
  catalog/    models.py (Site, Variant)  ingest.py  repository.py
  retrieval/  base.py (ScoredVariant + Retriever Protocol = the seam)  bm25.py
  llm/        client.py (OllamaClient — the single test seam)  prompts.py
  chat/       judge.py  service.py (ChatService.handle — orchestrates the pipeline)
  api/        schemas.py (ProductCard etc.)  routes.py
  main.py     create_app() lifespan wiring; 404/422/503 handlers
evals/        golden_set.json  run_eval.py (structural hit-rate + Judge checks)
scripts/      smoke.sh
tests/        one test_*.py per module (offline; httpx MockTransport, FakeLLM)
docs/superpowers/plans/2026-07-10-assistant.md   ← the authoritative 15-task plan
```

Key design facts a successor must not regress:
- **Internal Fields** (`margin_pct`, `monthly_sales_units`, `revenue_last_30d`,
  raw `stock_units`) are **never parsed into the domain model** → excluded from
  responses by construction, not by filtering. Keep it that way.
- `OllamaClient` is the **only** seam mocked in tests. It: (a) only closes a
  client it *owns* (`_owns_client = client is None`); (b) maps a malformed 200
  body to `LLMUnavailableError`. Both were hardening fixes — preserve them.
- `Judge._classify` **fails open** on `json.JSONDecodeError | AttributeError |
  TypeError` (TypeError covers null LLM content).
- `ChatService.handle` resolves the Site **first** (unknown → 404 before any LLM
  call), then Judge → static decline → retrieve → static no-match → generate.
  Declines and no-match answers are **static templates** (no LLM call).
- `strip_html` strips tags **then** unescapes, **preserving** decoded comparison
  operators like `<25kg` / `>40kg` (45 real feeding statements depend on this).
  Do not add bracket-stripping back.

## Locked decisions (already made — do not re-litigate)

- **Two-model split** (Judge `gemma4:e2b`, Generator `gemma4:e4b`) — ADR 0002.
- **Unknown site → 404** naming the valid Sites.
- **Answers always in the Site locale**, regardless of query language (a tourist
  asking in English on the German shop gets German — intended, documented).
- **Judge fails open** on unparseable/failed verdict.
- **BM25 first, behind a seam** (ADR 0001); vector/hybrid/reranker is the roadmap.
- Hand-rolled pipeline (no LangChain/LlamaIndex); no Docker for the app;
  single-turn/stateless. All rationalized in the README.

## Data-quality policies (verified against the real 300-row dataset)

Ingest applies five policies and reports counts in an `IngestReport`:

| Finding | Policy | Count |
|---|---|---|
| exact duplicate rows | dropped | 12 |
| Variant listed as both DOGS and CATS (site 15) | keep first, log conflict | 1 |
| unrated rows `rating_average: 0.0, rating_count: 0` | rating nulled | 198 (raw-feed) |
| implausible €950–1000 food/litter prices | quarantined (`ZA_MAX_PLAUSIBLE_PRICE`) | 24 |
| zero-stock rows | kept, exposed `in_stock: false` | 8 |

Result: **263 variants kept**; 174 of the kept variants are unrated. These exact
numbers are pinned in `tests/test_ingest.py::test_real_dataset_counts_match_the_known_traps`
— if you change ingest, that test is the guard.

## Two documented known-limitations (intentional, tracked — not bugs to "fix" quietly)

Both live in `evals/golden_set.json` with `"known_limitation": true` and are
excluded from the headline eval count:

1. **`crosslingual-english-on-german-site`** — BM25 is language-blind (ADR 0001);
   the vector/hybrid path is the designed fix.
2. **`site15-judge-false-decline`** — `gemma4:e2b` reproducibly mis-declines a
   valid Spanish query (its reasoning says on-topic, its JSON says `false`).
   Fail-open cannot catch a *well-formed but wrong* verdict. Disclosed in the
   README trade-offs + roadmap. **Do not mask this by rewording the query** — an
   earlier attempt to do that was flagged as an integrity gap in review. The fix
   is a stronger/few-shot Judge (roadmap), not hiding the case.

> A background investigation session (`task_6ec0257c`, "Investigate Judge
> false-decline on weight-control query") was spawned separately and runs
> independently. If it produced findings, fold them into limitation #2's roadmap
> item — do not let it silently rewrite the eval to make the case pass.

## How to run / verify

```bash
# Models (once)
ollama pull gemma4:e2b
ollama pull gemma4:e4b

# Env (Python 3.12 + deps — uv provisions everything)
uv sync

# Tests (offline — no Ollama needed), lint
uv run pytest                        # expect: 93 passed, 0 warnings
uv run ruff check app tests evals    # expect: clean

# Server
uv run uvicorn app.main:app

# Live smoke + eval (need server + Ollama running)
scripts/smoke.sh
uv run python -m evals.run_eval --base-url http://localhost:8000   # expect 11/11
```

Optional tracing (true no-op when off): `ZA_TRACING_ENABLED=true` with an Arize
Phoenix container on `:6006`. OpenInference spans: `chat` (CHAIN), `judge`
(GUARDRAIL), `retrieve` (RETRIEVER), `ollama.chat` (LLM).

## Open items / decisions pending

1. **Untracked file:** `docs/specs/assistant/ingest-pipeline.plan.md` is present
   but not committed (appeared after the tree was last clean — likely from the
   background investigation session). Decide whether it belongs in the repo
   before it's committed by accident. It was **not** part of the 15-task plan.
2. **What ships in the submission:** `docs/` planning artifacts and
   `AGENTS.md` / `CONTEXT.md` are currently tracked. `docs/agents/` and the plan
   file itself are gitignored. The owner should decide whether the planning
   material ships with the take-home or is stripped.
3. **Git submission logistics** (remote, push) are the **owner's** to handle per
   the PRD. Local history is clean and ready.

## Where the detail lives

- **Authoritative plan (all 15 tasks, full code, TDD steps):**
  `docs/superpowers/plans/2026-07-10-assistant.md`
- **Per-task execution ledger** (commit ranges, per-task fixes, accumulated
  minor findings, final-review outcome):
  the SDD progress ledger in this session's scratchpad
  (`…/scratchpad/sdd/progress.md`). It records, task by task, every defect the
  review loop caught — e.g. the `strip_html` operator-corruption fix (`cbc5e45`),
  the BM25 tiny-corpus negative-IDF fixture fix, and the Judge false-decline
  integrity resolution (`c10daf6`).
- **Graded write-up:** `README.md` — the 4 mandated sections, architecture
  mermaid diagram, ingest table, and the trade-off/roadmap disclosures.
