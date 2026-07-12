# Design: Conversational maturity — gaps and improvement options

**Date:** 2026-07-11
**Status:** Options catalogue, partially implemented later the same day:
§2's option (a) (stateless `history`) and §3's option B input-side fencing
shipped; everything else remains future work. Anchored in the code by
`# TO_EXPLAIN` markers (see [In-code markers](#in-code-markers)).
**Motivation:** The Assistant today is a single-turn, stateless RAG
product-finder — one `{site_id, query}` in, one grounded answer + Product Cards
out. It answers questions well, but does not yet *hold a conversation*. This
doc records where it stands on three conversational axes — **entity
identification**, **multi-turn / follow-ups**, and the **safetynet** — and the
options for deepening each, so any one can later graduate into its own
`-design.md` (implementation checklists are working files, discarded once
executed).

The through-line of the current design: it is rigorous about what **cannot
happen** (structural safety, data quality) and about **single-turn
correctness**, but has not yet invested in what makes something *feel* like an
assistant — memory of the conversation, understanding of richer intent, and
verification of its own output.

## 1. Entity identification

**Anchor:** `app/catalog/facets.py` (detection) → `app/retrieval/bm25.py`
(application).

### Current state — partial (two rule-based slots)

| Slot | Detection | Effect on retrieval |
|------|-----------|---------------------|
| `pet_type` (DOGS/CATS) | multilingual keyword match (`detect_pet_type`) | **hard filter** — a dog query never returns a cat |
| `food_form` (DRY/WET) | multilingual keyword match (`detect_food_form`) | **soft boost** — ×1.5 match / ×0.85 miss |

The asymmetry is deliberate and sound: `pet_type` is an authoritative, always-
present clean data field, so it can safely *exclude*; `food_form` is *derived*
at ingest and often unknown, so it only *nudges* ranking (a strong lexical
match still wins). Facets are logged per query in `bm25.py`. There is **no
LLM-based extraction anywhere** — the Judge emits only a boolean `on_topic`.

### Not extracted today

Everything else a shopper says is treated as ordinary BM25 tokens, not
structured intent:

- **life-stage** (puppy / kitten / adult / senior)
- **breed / size band** (small-breed, large-breed)
- **weight band** (the data even carries encoded `<25kg` literals)
- **budget / price ceiling** ("cheap", "under €30") — `price` exists on the
  model but is never a query constraint
- **brand as a filter** — `brand` is document-boosted but never read from the query
- **dietary / health needs** — grain-free, sensitive stomach, hypoallergenic, kidney care
- **pack size / multipack**

### Options

- **A. Extend the keyword facets.** Add high-precision multilingual lists (and,
  for budget/weight, small regexes) in the existing `facets.py` style. Cheap,
  explainable, zero new infrastructure; cost is ongoing list maintenance and
  brittleness on unseen phrasings.
- **B. LLM slot-extraction step.** A Judge-sized model call that fills a typed
  slot object (life-stage, price ceiling, dietary flags, …) the Retriever can
  act on. Richer and paraphrase-robust; cost is one more model call per turn
  and a schema to validate. Naturally combines with the query-planner roadmap
  item (README Future Roadmap #3).
- **C. Hybrid.** Rules for the high-precision, always-safe slots (species,
  price); LLM for the fuzzy ones (health/dietary intent).

**Note:** new hard filters are risky — a wrong life-stage filter hides the
right product. Follow the existing rule: only slots backed by an authoritative
clean field should hard-filter; everything derived should soft-boost.

## 2. Multi-turn & follow-ups

**Anchor:** `app/api/schemas.py` (`ChatRequest`), with the consequences in
`app/chat/service.py` and `app/llm/client.py`.

### Current state — absent by construction

- The request contract is strictly `{site_id, query, stream}` with
  `extra="forbid"` — **no** `conversation_id`, **no** `history`.
- **No server-side memory**: `ChatService` holds no session store; the LLM
  `messages` are rebuilt every call as *system + single user message*.
- The UI console is display-only — each send posts just the current input.

So **"what about the wet version?" cannot work**: it arrives with no referent —
no coreference/anaphora resolution, and the Generator never sees the previous
turn or its Product Cards. The single-turn shape is a property of the contract,
not an incidental gap. (The greeting fast-path added a warmer *surface*, not
memory.)

### Options

- **A. Stateless multi-turn.** The client resends prior turns in a `history`
  field; the server stays memoryless. Simplest to reason about, no store, no
  expiry; cost is a larger request and trusting the client's transcript.
  **Shipped 2026-07-11**: `history` (max 10 validated turns) goes to the
  Generator only; the web console resends its transcript automatically.
- **B. Stateful multi-turn.** A `conversation_id` keys a short-lived
  server-side transcript store. Smaller requests, server owns the truth; cost
  is state, TTL/eviction, and a store dependency.

Either way, the hard part is the same and sits **before** the pipeline: a
**query-rewriting / coreference** step that turns "what about the wet one?"
into a self-contained query ("wet food for my dog") *before* the Judge and
Retriever — both of which are built to see one self-contained query. The
streaming contract (`handle_stream`) already threads cleanly and would not need
to change shape.

## 3. Safetynet

**Anchor:** `app/chat/service.py` at the generation step (the natural home for
an output-side check), spanning `app/llm/prompts.py` and `app/chat/judge.py`.

### Current state — strong structurally, thin behaviourally

Solid, mostly *by construction* (the strong kind of guarantee):

- **Internal-Fields leak is impossible** — the domain model has no such fields
  (`app/catalog/models.py`), so no path can leak them.
- **Cross-Site leakage prevented** — hard per-Site partitioning and per-Site indexes.
- **Topicality Judge** — fails open, few-shot-anchored; off-topic → static,
  zero-LLM decline.
- **Grounding** — the Generator prompt says *answer using ONLY the provided
  product information; never invent products, prices, or facts*; empty
  retrieval short-circuits to a static no-match so the Generator never runs
  ungrounded.
- **Availability** — conditional 503, locale enforcement, input length caps,
  data-quality quarantine at ingest.

### Undefended (the honest gaps)

- **Prompt injection** — the raw query is interpolated straight into both Judge
  and Generator prompts; no delimiting, no instruction hierarchy.
- **No output-side verification** — once the Generator runs, its answer is
  returned verbatim. Nothing checks it stayed grounded in the cards, invented
  no product/price, kept the Site locale, or leaked no system prompt.
- **Unsafe pet-health / medical advice** — no disclaimer or guardrail, and
  health-with-product queries are explicitly on-topic for the Judge.
- **Abuse / profanity** — no moderation.
- **System-prompt leakage** — internal fields are safe, but nothing stops the
  model reciting its own instructions if asked.
- **PII** — not written to app logs, but the raw query *is* exported to Phoenix
  traces when tracing is on, with no redaction.
- **No auth / rate limiting** — `/chat` and `/health` are open.

### Options

- **A. Output-side verifier.** A post-generation check (rules and/or a small
  model) that the answer is grounded in the retrieved cards, cites no invented
  product/price, is in the Site locale, and leaks no system text. The single
  highest-leverage move for trust; slots in right after generation in both the
  non-streaming and streaming paths (streaming would verify the buffered answer
  before the terminal `done`, trading back some perceived latency).
- **B. Input sanitisation / injection defence.** Delimit the user query,
  assert an instruction hierarchy in the system prompt, optionally a
  cheap injection classifier. **Partially shipped 2026-07-11**: the query is
  fenced in `<query>` tags and the generation system prompt asserts the
  hierarchy; resent `history` turns are still unfenced, no classifier.
- **C. Content safety.** A pet-health disclaimer where health intent is
  detected; a moderation pass on abusive input.
- **D. PII redaction before tracing.** Redact the query attribute on spans when
  `ZA_TRACING_ENABLED`.

## How this maps to the existing roadmap

README "Future Roadmap" already lists **multi-turn** (#4), **query planner /
agentic tool use** (#3), and **guardrail hardening** (#5). This doc deepens
those three on the conversational axis and adds two angles not yet called out:
**structured entity/slot extraction** (feeding #3) and an **output-side answer
verifier** (extending #5 beyond the input-side Judge).

## In-code markers

`# TO_EXPLAIN` comments point back to this doc — the same "explain the
trade-off where the reader will stand" convention the streaming design uses
for its required routes.py comment. The ones anchored to this doc's sections:

| Marker location | Section |
|-----------------|---------|
| `app/catalog/facets.py` | [Entity identification](#1-entity-identification) |
| `app/api/schemas.py` (`ChatRequest.history`) | [Multi-turn & follow-ups](#2-multi-turn--follow-ups) |
| `app/chat/service.py` (Judge call) | [Multi-turn & follow-ups](#2-multi-turn--follow-ups) |
| `app/chat/service.py` (generation step) | [Safetynet](#3-safetynet) |
| `app/llm/prompts.py` (query fencing) | [Safetynet](#3-safetynet) |

Further `# TO_EXPLAIN` anchors outside this doc's scope (retrieval, Ollama
tuning) are indexed in the README's "Interview anchors" table.

## Out of scope

This is an options catalogue, not a committed design and not a plan. No code
behaviour changes with it. Each section graduates into its own `-design.md`
when it is picked up for implementation.
