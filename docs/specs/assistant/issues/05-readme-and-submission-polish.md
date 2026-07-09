# 05 — README and submission polish

Status: ready-for-agent

## Parent

`docs/specs/assistant/PRD.md`

## What to build

The README the reviewers grade, structured exactly as the assignment demands: **High-Level Design** (pipeline diagram — Judge → Retriever → Generator with the seams marked), **Setup and Execution** (install uv + Ollama, pull the two models, `uv sync`, run; example curls for a product query per Site, an off-topic decline, and a 404), **Decisions and Trade-offs** (data-trap findings with counts and the policy for each; BM25-first and the two-model split with reasoning from the ADRs; the site-locale answer policy stated prominently as intended behavior; no-Docker rationale; internal-field exclusion), and **Future Roadmap** (evaluation harness with labeled queries, hybrid retrieval + reranker through the existing seam, query planner / agentic tool use, observability, streaming + multi-turn, containerization). Final pass: tests green, dead code removed, setup instructions proven on a clean checkout.

Covers user stories 20, 21.

## Acceptance criteria

- [ ] README contains the four mandated sections with a rendering architecture diagram
- [ ] Setup instructions verified end-to-end from a clean checkout: models pulled, `uv sync`, service starts, documented example curls return the documented shapes against live Ollama
- [ ] Data-quality findings and policies documented with the actual counts from the ingest report
- [ ] The site-locale answer policy is called out explicitly so reviewers don't read it as a bug
- [ ] Decisions section reflects the ADRs and names the consciously accepted gaps (cross-lingual, paraphrase recall, single-turn)
- [ ] Full test suite passes on the final state

## Blocked by

- `docs/specs/assistant/issues/04-judge-guardrail.md`
