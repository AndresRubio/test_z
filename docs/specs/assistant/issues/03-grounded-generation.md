# 03 — Grounded answer generation via Ollama in the Site locale

Status: ready-for-agent

## Parent

`docs/specs/assistant/PRD.md`

## What to build

An async LLM client for Ollama behind a thin interface — the codebase's single test seam — and a Generator stage on `gemma4:e4b` that turns retrieved Variants into the conversational `answer`. Answers are written in the Site locale regardless of query language, grounded exclusively in the retrieved catalog data (no invented products, prices, or attributes), and when retrieval comes back empty the answer honestly says the shop has no match instead of padding. `retrieved_products` must reflect exactly the context the Generator was given. Model names and the Ollama host come from settings.

Covers user stories 1, 3, 4, 9, 10, 23, 24.

## Acceptance criteria

- [ ] `/chat` returns a real generated answer that references only retrieved products
- [ ] Site 1 answers in German, Site 3 in English, Site 15 in Spanish — even when the query language differs
- [ ] Empty retrieval → honest no-match answer, empty products, count 0, nothing hallucinated
- [ ] API tests run with a fake LLM client through the ASGI test client — no test requires live Ollama
- [ ] A documented smoke script (or instructions) exercises the live Ollama path with the task's example query
- [ ] Ollama host and model names are configurable via environment settings with working defaults
- [ ] All behavior specified by TDD-first tests

## Blocked by

- `docs/specs/assistant/issues/02-ingest-and-retrieval.md`
