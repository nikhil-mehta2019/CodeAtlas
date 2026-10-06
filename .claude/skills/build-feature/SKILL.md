---
name: build-feature
description: Implement one focused CodeAtlas feature or vertical slice, reusing existing architecture. Use for a scoped change that doesn't fit the more specific build-analyzer or build-frontend-feature skills. Usage: /build-feature <short-feature-name>.
---

# build-feature

Implement exactly one feature end-to-end, as a small vertical slice, by
extending what already exists.

## Steps

1. **Inspect first.** Read the relevant parts of `src/codeatlas/` and
   `ARCHITECTURE.md` before writing anything. Find the closest existing
   pattern (an existing analyzer, store method, schema section, or CLI
   subcommand) that this feature resembles.
2. **Scope it down.** Define the smallest complete change that delivers
   the requested feature. Prefer touching 2-4 files over introducing a
   new subsystem. If the feature looks like it needs a new top-level
   package, pause and confirm that's really required by checking
   `ARCHITECTURE.md` §9's layering first.
3. **Implement only what was requested.** No speculative options, no
   unrelated cleanup, no new abstractions "for later."
4. **Reuse, don't duplicate.** Use existing schemas (`codeatlas/knowledge/schema.py`,
   `codeatlas/evidence/schema.py`), the existing `ModelProvider` abstraction,
   and existing store classes rather than writing parallel versions.
5. **Add/update tests** in `tests/unit/` following the existing
   `test_mN_*.py` naming and style. Use the fixture repos under
   `tests/fixtures/sample_repos/` where applicable; add a new fixture
   only if no existing one can exercise the feature.
6. **Run verification**: `pytest -q`, plus a real CLI run if the feature
   touches the pipeline or CLI output.
7. **Report**: what changed (files), why that was the smallest complete
   change, and the actual verification output (not a claim — the real
   pass/fail counts).

## Guardrails

- Every new finding type must carry evidence + status, per `CLAUDE.md`.
- Don't break existing tests. If a change requires updating an existing
  test's expectation, say why in the report.
