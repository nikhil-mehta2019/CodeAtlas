# CLAUDE.md

Persistent rules for every Claude session working on CodeAtlas. These
rules do not expire between tasks and do not need to be repeated in task
prompts.

## What this is

CodeAtlas is a real-world AI Software Quality Agent, not a demo. The
repository already contains a working V1 foundation: architecture
(`ARCHITECTURE.md`), knowledge/evidence schemas, repository ingestion,
discovery engine, API/architecture analyzers, gap detection, documentation
generation, an LLM provider abstraction, and a passing test suite. **This
foundation is the source of truth. Preserve it.**

## Before changing anything

- Read the existing implementation (and `ARCHITECTURE.md`) before
  changing architecture, schemas, or established patterns.
- Identify the closest existing pattern and extend it. Do not introduce a
  parallel way of doing something the codebase already does.
- Do not break existing behavior without a clear, stated reason.

## How to work

- Prefer small, complete vertical slices over broad, partial changes.
- Avoid unnecessary abstractions, speculative generality, and rewrites.
  Extend the existing architecture; do not replace it.
- Do not re-explain CodeAtlas's architecture or coding style in task
  prompts — that context belongs here, once. Use the skills under
  `.claude/skills/` for recurring workflows instead of restating process
  each time.

## Evidence and honesty are product requirements, not style preferences

- Never present inferred information as confirmed. Every finding carries
  a status: `CONFIRMED`, `INFERRED`, `UNVERIFIED`, `CONTRADICTED`, or
  `UNKNOWN`.
- `CONFIRMED` requires at least one statically-discovered Evidence record
  (see `codeatlas/evidence/schema.py::assert_status_supported`). Never
  weaken or bypass this rule to make a finding look more certain.
- Never fabricate implementation, analysis output, test results, or
  project knowledge. If something isn't implemented or couldn't be
  determined, say so explicitly — do not simulate or mock it and present
  it as real.
- An analyzer must never manufacture findings. No evidence, no finding —
  report `UNKNOWN` instead.

## Verification

- Verify changes before declaring them complete: run the actual test
  suite and, where relevant, the actual CLI end-to-end path.
- Never claim PASS without having actually run the verification. Report
  PASS / FAIL / PARTIAL / BLOCKED honestly.
- Add focused tests for new behavior; keep using the existing test suite
  rather than replacing it.

## Security

- Keep secret detection/redaction intact. Never log, store, or display
  secret values, API keys, or credentials from an analyzed repository.
- Keep the repository walker's path confinement intact — analysis must
  stay confined to the target repo root.

## Keeping this file accurate

- Keep commands, setup steps, and verification instructions here and in
  `README.md` accurate. If a command changes, update the doc in the same
  change.
- This file holds durable rules only — no feature specifications. Feature
  intent belongs in `ARCHITECTURE.md`, issues, or task prompts.
