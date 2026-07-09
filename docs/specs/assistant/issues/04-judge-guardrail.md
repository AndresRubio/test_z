# 04 — Judge guardrail: prompt-only topicality check before retrieval

Status: ready-for-agent

## Parent

`docs/specs/assistant/PRD.md`

## What to build

The Judge as pipeline stage 1: a prompt-only structured verdict on `gemma4:e2b` deciding whether the query is answerable from the catalog (products and their attributes, including ingredients and feeding recommendations). Off-topic queries — including pet trivia with no product angle — short-circuit before retrieval with a polite decline written in the Site locale and an empty products list. An unparseable verdict fails open (proceeds to retrieval) with a warning log; that trade-off is documented. With this slice, all functional requirements of the assignment are met.

Covers user stories 11, 12, 24.

## Acceptance criteria

- [ ] "What's the weather today?" is politely declined in the Site locale with empty products, count 0
- [ ] "Do dogs dream?" (pet trivia, no product angle) is declined; the task's example product query passes through unchanged
- [ ] Off-topic queries trigger no retrieval and no generator call (observable via the fake LLM client and stage logs)
- [ ] Unparseable Judge output proceeds to retrieval and logs a warning
- [ ] Judge model is configurable via settings, defaulting to the tiny model
- [ ] All behavior specified by TDD-first tests with scripted Judge verdicts

## Blocked by

- `docs/specs/assistant/issues/03-grounded-generation.md`
