# Scripts

## `smoke.sh`

A manual end-to-end smoke test. It curls a running server through the full
`/chat` contract and prints each response, so a reviewer can eyeball the real
LLM answers — the one check that covers answer *quality*, which CI does not
assert.

**Requires:** Ollama running with both models pulled, and the service started
(`uv run uvicorn app.main:app`).

```bash
scripts/smoke.sh [base-url]   # default: http://localhost:8000
```

Covers, in order: `GET /health`; the assignment's example query on Site 3 (en);
German (Site 1) and Spanish (Site 15) product queries; an off-topic query that
should decline with no products; and an unknown Site that should return 404.
Exits non-zero on the first failure; prints `== smoke OK ==` when all pass.
