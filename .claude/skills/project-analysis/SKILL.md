---
name: project-analysis
description: Work on CodeAtlas's core project-understanding workflow (discovery through knowledge/evidence/documentation) while preserving the existing model. Use when the task touches the analysis engine broadly rather than one analyzer or feature.
---

# project-analysis

For work that spans the core understanding pipeline itself — discovery,
technology detection, architecture inference, components, APIs,
database, auth/authz, integrations, business rules, configuration,
coding standards, deployment, existing tests, knowledge gaps, evidence —
rather than one isolated analyzer or feature.

## Before changing anything

Re-read `ARCHITECTURE.md` §3-§7 (Knowledge schema, Evidence schema,
Discovery workflow, Agent orchestration, Large-repo strategy) and walk
the real call path: `orchestrator/pipeline.py` →
`discovery/engine.py` → individual analyzers → `knowledge/gaps.py` →
`documentation/generator.py`. Confirm the mental model still matches the
code before proposing or making a change.

## Non-negotiables to preserve

- Discovery stays static and zero-LLM-cost; it never calls a model
  provider.
- Every significant finding across every domain area keeps: **Finding,
  Evidence, Source, Location, Confidence, Status**.
- Status is always one of: `CONFIRMED`, `INFERRED`, `UNVERIFIED`,
  `CONTRADICTED`, `UNKNOWN` — never a bare boolean or free-text guess.
- `CONFIRMED` requires static evidence (enforced in
  `codeatlas/evidence/schema.py`) — do not loosen this to make a change
  easier.
- Gaps are first-class: if a domain area can't be determined, it must
  surface through `knowledge/gaps.py` as an `Unknown`, not be silently
  omitted.
- Documentation is generated from structured `ProjectKnowledge` only —
  never from a second free-form LLM pass over the findings.

## Workflow

1. Scope the change to the specific stage(s) of the pipeline it actually
   touches; avoid rippling edits across unrelated analyzers.
2. Extend existing schema/store/pipeline code rather than introducing a
   parallel mechanism for the same concern.
3. Add or update tests that exercise the real pipeline (prefer the
   existing fixture repos in `tests/fixtures/sample_repos/`) over tests
   that only check isolated functions.
4. Run `pytest -q` and a real CLI run; report actual results.
5. If the change affects milestone scope (§10 of `ARCHITECTURE.md`),
   note that explicitly so the architecture doc can be updated in a
   follow-up — don't silently let it drift out of sync.
