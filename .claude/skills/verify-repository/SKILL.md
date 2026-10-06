---
name: verify-repository
description: Verify the current state of the CodeAtlas repository before major development work — read-only. Use before starting a new feature/analyzer, after pulling changes, or when asked to check whether the repo is healthy.
---

# verify-repository

Read-only health check of the current repository state. Never edit files.

## Steps

1. Read `ARCHITECTURE.md` and `README.md` to recall current scope and
   stated milestones (M1–M6 and beyond).
2. Skim `src/codeatlas/` structure (`ls`/`find`) and compare it against
   what `ARCHITECTURE.md` §9 describes. Note any drift.
3. Run the test suite: `source .venv/bin/activate && pytest -q` (create
   the venv with `uv venv && uv pip install -e ".[dev]"` first if missing).
4. Run the CLI end-to-end against a fixture repo to confirm the real
   path still works, not just unit tests:
   `python -m codeatlas.cli analyze tests/fixtures/sample_repos/python_fastapi --data-dir /tmp/verify_run`
   Inspect the generated `report.md` for sane output (sections present,
   CONFIRMED findings have evidence, no crash, no fabricated-looking
   content).
5. Check for incomplete or misleading state: TODOs presented as done,
   analyzers that silently swallow errors, findings without evidence,
   `CONFIRMED` status without static evidence (should be structurally
   impossible per `codeatlas/evidence/schema.py` — spot-check it still is).

## Report

End with exactly one of:

- **PASS** — tests pass, CLI runs end-to-end, no regressions found.
- **PARTIAL** — runs, but with gaps worth flagging (list them).
- **FAIL** — tests or the CLI path are broken (name what and where).
- **BLOCKED** — could not complete verification (e.g. missing
  environment) — state what's needed.

Include: test pass/fail counts, whether the CLI run succeeded, and any
drift between code and `ARCHITECTURE.md`. Do not modify code during this
skill — if something needs fixing, report it for a separate task.
