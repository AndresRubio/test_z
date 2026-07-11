# Evals — golden-set retrieval checks

An offline, reproducible scorecard for the Assistant's retrieval and guardrail
behavior. It runs a small set of hand-labeled queries against a **running**
`/chat` and checks the response — the evidence behind the numbers quoted in the
root [README](../README.md#measured-results) and [ADR 0003](../docs/adr/0003-hybrid-semantic-retrieval.md).

## What it checks (and what it doesn't)

Checks are **structural**, not subjective — no LLM-as-judge scoring here (that
is future work, see the README roadmap). Each case in
[`golden_set.json`](golden_set.json) declares one of two expectations:

- **`products`** — the response must retrieve *at least one* of the expected
  `product_id`s. Exercises the full **Judge → Retriever → Generator** path.
- **`empty_products`** — the query must be declined with no products, proving
  the **Judge** caught an off-topic question before retrieval.

The 13 cases span all three Sites and all three catalog languages (German,
Spanish, English): product queries, off-topic declines (including pet trivia
with no product angle), a Judge false-decline regression guard, and one
cross-lingual case.

## Running it

Needs a live server and both Ollama models pulled (unlike `tests/`, which is
fully offline). Start the app first, then:

```bash
uv run python -m evals.run_eval --base-url http://localhost:8000
```

Add `--strict` to exit non-zero if any **scored** case fails — suitable for CI.

## Reading the output

Each line is `PASS`, `FAIL`, or `KNOWN-FAIL`, followed by the case id. The
headline counts **12 scored cases**; the 13th carries `known_limitation: true`
and is reported but excluded from the score.

```
Headline: 12/12 passed (1 known-limitation failures excluded)
```

Two cases are worth a reviewer's attention:

- **`crosslingual-english-on-german-site`** (`known_limitation`) — an English
  query against the German Site's text. BM25 is language-blind, so it is
  *expected* to miss on the default backend. This is the accepted gap from
  [ADR 0001](../docs/adr/0001-bm25-first-retrieval-behind-a-seam.md), not a bug;
  the semantic backend (ADR 0003) is the designed fix and flips this case to
  PASS. It is scored out rather than hidden.
- **`site15-judge-false-decline`** — a regression guard capturing the exact
  phrasing the Judge once mis-declined (well-formed JSON verdict of `false`
  while its own reasoning said on-topic — a failure fail-open cannot catch).
  Kept **unreworded** on purpose so any regression re-surfaces the original
  input.

## Files

| File | Role |
|---|---|
| `golden_set.json` | The 13 labeled cases (query, Site, expected outcome). |
| `run_eval.py` | Runner: posts each query to `/chat`, scores structurally, prints the headline. |
