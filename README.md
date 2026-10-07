# CodeAtlas — AI Software Quality Agent (V1)

CodeAtlas analyzes a software repository and builds a structured,
evidence-backed understanding of it: what it is, what it's built with, how
it's put together, and — just as importantly — what could **not** be
determined. See `ARCHITECTURE.md` for the full design and the product
specification it implements.

## Status

V1 scope only: **Discovery → Understanding → Knowledge Base →
Documentation → Evidence → Gap Detection.** Test execution, autonomous
fixing, and browser automation are explicitly out of scope for this
version — see `ARCHITECTURE.md` §12.

Implemented and tested (61 passing tests, `pytest`):
- Repository layer: path-confined walker, gitignore-aware exclusion,
  secret detection/redaction.
- Evidence + Knowledge schemas with the CONFIRMED-requires-static-evidence
  rule actively enforced at every evidence-backfill site in
  `orchestrator/pipeline.py` (not just available as a standalone,
  independently-unit-tested function) — except `TechnologyItem` entries,
  an explicit, tracked gap (see `ARCHITECTURE.md` §4).
- Discovery engine: deep support for **Python** and **Node.js/TypeScript**;
  shallow (manifest-presence-only, honestly labeled) support for **.NET,
  Java, Go, PHP**; Docker/CI/IaC infra detection; priority-path builder.
- Model provider abstraction (`ModelProvider` protocol) with an Anthropic
  implementation and a Null fallback — AI-assisted analysis degrades to
  "UNKNOWN", never to a fabricated answer, when no API key is configured.
- Analyzers: static route extraction (API catalog) for
  Express/FastAPI/Flask-style route declarations; architecture/component
  inference from discovered directory structure, with a generated Mermaid
  diagram; database analyzer (engine + ORM/ODM from declared dependencies,
  migrations from the priority plan + `alembic.ini`, table/column schema
  for SQLAlchemy declarative models and Prisma schema files);
  authentication/authorization analyzer (JWT/OAuth2/session mechanism
  from dependencies and JWT call-site scanning, password-hashing library
  usage, and an RBAC-vs-ad-hoc authorization classification from
  role/permission-check scanning); external integrations analyzer
  (third-party providers from declared dependencies, webhook attribution
  only when a route names both "webhook" and the provider, config-file
  key *names* matched to a provider — values are never captured);
  business rules analyzer (Python-only: Pydantic `Field` validation
  constraints, role-gated business actions, Enum-based state membership
  — never asserting which state transitions are valid); coding standards
  analyzer (Python-only: measured naming-convention consistency via
  `ast`, test-file naming convention, FastAPI `Depends(...)`
  dependency-injection usage, `*Repository`-suffixed class naming —
  `recommended_improvements` is always left empty, per the spec's own
  instruction not to call something a violation just for differing from
  a preferred style); dependency intelligence analyzer (detects the same
  package pinned to different *exact* versions across multiple
  declarations, reported as a `KnownIssue` — version ranges are never
  compared for compatibility, and "potentially outdated" is not detected
  since that needs live package-registry network access).
- Gap/Unknown detector covering every major question the spec asks (§2).
- Documentation generator: renders the full 19-section report from
  structured knowledge only — no second LLM pass hallucinating prose.
- CLI (`codeatlas analyze <path>`) and SQLite/file-based persistence.

**Not yet implemented** (tracked, not hidden — see `ARCHITECTURE.md` §10,
§12): Node/TS business rules and coding-standards conventions; outdated-
package detection, internal/workspace dependency classification, and
version-range compatibility checking (the dependency analyzer only
compares exact-pin-vs-exact-pin); Django ORM/Mongoose table-schema
parsing (engine/ORM identity for them is detected, columns are not);
API-key authentication detection; LLM-assisted analysis (the plumbing
exists, no analyzer calls it yet); OpenAPI spec parsing; incremental
re-analysis as a CLI command;
human review/correction workflow.

## Quick start

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest

codeatlas analyze /path/to/some/repo
```

No `ANTHROPIC_API_KEY` is required for any of the above — discovery and
the current analyzers are 100% static. Set `ANTHROPIC_API_KEY` (and
optionally `CODEATLAS_MODEL`) to make `codeatlas.llm.get_default_provider()`
return a live Anthropic provider once LLM-assisted analyzers are added.

## Layout

See `ARCHITECTURE.md` §9 for the full layered layout and the reasoning
behind it.
