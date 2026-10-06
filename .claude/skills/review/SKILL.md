---
name: review
description: Review existing CodeAtlas implementation for correctness, architecture consistency, security, and evidence integrity, without rewriting it. Usage: /review <area>, e.g. /review database-analyzer.
---

# review

Review, report, do not rewrite. This skill produces findings; it does
not apply fixes unless the user explicitly asks in a follow-up.

## Steps

1. Identify the target area's files (an analyzer, the store layer, the
   CLI, etc.) and read them fully, plus the parts of `ARCHITECTURE.md`
   and `CLAUDE.md` they're supposed to follow.
2. Review against each of the following, only where relevant to the
   target area:
   - **Correctness** — logic errors, edge cases, incorrect assumptions.
   - **Architecture consistency** — does it follow the layering in
     `ARCHITECTURE.md` §1 and reuse existing abstractions, or does it
     quietly duplicate/bypass them?
   - **Security** — path confinement, secret redaction, no execution of
     repository code, no leaked credentials in evidence/logs.
   - **Maintainability** — naming, function size, unnecessary complexity.
   - **Error handling** — are failures swallowed silently, or surfaced
     as `UNKNOWN`/an explicit error rather than a false success?
   - **Test quality** — do tests assert real behavior (status + evidence
     correctness), or just that code runs without raising?
   - **Regression risk** — could this change break another analyzer,
     the store schema, or the CLI output format?
   - **Evidence integrity** — does every `CONFIRMED` finding trace to
     static evidence? Any finding presented without a status?

## Report

List actionable findings, each with: file/location, what's wrong, why it
matters, and a suggested fix (described, not applied). Do not modify
code as part of this skill.
