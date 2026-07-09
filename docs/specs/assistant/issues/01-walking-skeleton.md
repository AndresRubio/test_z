# 01 — Walking skeleton: contract-complete /chat with stub pipeline

Status: ready-for-agent

## Parent

`docs/specs/assistant/PRD.md`

## What to build

A runnable uv-managed FastAPI service exposing the full external contract with a stub pipeline behind it. `POST /chat` validates `{site_id, query}`, resolves the Site against a registry derived from the catalog dataset (1, 3, 15), and returns the exact response shape — `{"answer": <stub string>, "retrieved_products": {"products": [], "count": 0}}`. Unknown Site → 404 whose detail names the valid Sites; malformed body → 422. `GET /health` responds for probes. Structured logging with a request ID per request. This slice proves the contract, config, and app wiring end-to-end before any intelligence exists.

Covers user stories 16, 17, 18, 20 (partially), 24.

## Acceptance criteria

- [ ] Fresh checkout: `uv sync` then a single documented run command starts the service
- [ ] `POST /chat` with a valid `site_id` returns 200 and the full contract shape (stub answer, empty products, count 0)
- [ ] `POST /chat` with `site_id` 7 returns 404 and the error detail names Sites 1, 3, 15
- [ ] Missing or wrongly-typed `site_id`/`query` returns 422
- [ ] `GET /health` returns 200
- [ ] Each request logs a request ID; logs are structured
- [ ] All behavior above is specified by TDD-first tests through the ASGI test client

## Blocked by

None - can start immediately
