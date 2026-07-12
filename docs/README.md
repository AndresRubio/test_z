# Docs

How this folder is organized:

- **`adr/`** — Architecture Decision Records: one numbered record per
  decision that shapes the system; the filenames are the index.
- **`specs/<feature>/`** — point-in-time design records, one folder per
  feature (`assistant` is the core PoC; the sibling folders are follow-up
  features): dated design docs plus, for `assistant`,
  the PRD and the ingest plan. Their bodies are kept essentially as written
  so the decision trail stays honest; where reality moved on, a status note
  or inline annotation says so. (Throwaway execution checklists were removed
  once implemented.) The repo-root `README.md` is the up-to-date view — these
  are the working records behind it.
- **`specs/assistant/issues/`** — the work breakdown the PoC was built from:
  five vertical slices (walking skeleton → ingest/retrieval → generation →
  guardrail → write-up), each with the acceptance criteria it shipped
  against. All done; kept as the record of how the work was sequenced.

Suggested reading order for a reviewer: root `README.md` → `CONTEXT.md`
(domain vocabulary) → `docs/adr/` → `docs/specs/assistant/PRD.md` → the dated
design docs for whichever feature you are looking at.

Curious how this was built? [`code-workflow-schema.html`](code-workflow-schema.html)
(in this folder — open it in a browser) is a visual map of the AI-assisted workflow
behind the PoC — the assignment encourages AI-assisted work, and the specs and
issues in this folder are that process's records.
