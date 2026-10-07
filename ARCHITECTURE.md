# CodeAtlas — AI Software Quality Agent — Architecture (V1)

Status: **Proposed and being implemented incrementally.** This document is the
single source of truth for scope and design decisions. Update it when a
decision changes; do not let code and this document drift apart.

## 0. Scope of V1

V1 implements only:

```
Project Discovery → Project Understanding → Knowledge Base →
Documentation → Evidence → Unknown/Gap Detection
```

V1 explicitly does **NOT** implement (see §14): test execution, browser
automation, autonomous code fixing, performance/security test *execution*,
or multi-tenant services. The architecture below leaves seams for all of
these without a rewrite.

**Update (post-initial-V1):** a thin REST API layer (`codeatlas.web`) now
exists alongside the CLI, wrapping the same `Orchestrator` — see §1 and
§13. It is an initial skeleton, not a hosted, production-ready service:
no auth, no multi-tenancy, no upload/clone support. Running it on an
untrusted network is an operator decision this layer does not make safe
by itself.

## 1. Production Architecture

Layered pipeline, each layer a separate Python package with a narrow
interface. Nothing above the Repository Layer touches the filesystem
directly; nothing below the Analysis Engine talks to an LLM.

```
┌─────────────────────────────────────────────────────────────┐
│ Web API Layer (codeatlas.web) — FastAPI, optional [api] extra │
├─────────────────────────────────────────────────────────────┤
│ CLI / Library API (codeatlas.cli / codeatlas.api)            │
├─────────────────────────────────────────────────────────────┤
│ Agent Orchestrator (codeatlas.orchestrator)                   │
│   drives: discover → analyze → validate → store → document   │
├─────────────────────────────────────────────────────────────┤
│ Discovery Engine │ Analysis Engine │ Documentation Engine     │
│ (static, no LLM) │ (static + LLM)  │ (templated from KB)      │
├─────────────────────────────────────────────────────────────┤
│ Knowledge Engine (schema + SQLite store + gap detection)      │
├─────────────────────────────────────────────────────────────┤
│ Evidence Engine (schema + file-based evidence store)          │
├─────────────────────────────────────────────────────────────┤
│ Model Provider Abstraction (codeatlas.llm) — swappable         │
├─────────────────────────────────────────────────────────────┤
│ Repository Layer (codeatlas.repository) — safe FS access       │
└─────────────────────────────────────────────────────────────┘
```

Dependency rule: higher layers import lower layers, never the reverse.
`codeatlas.web` currently calls `Orchestrator` directly (the same way
`codeatlas.cli` does), not through `codeatlas.api` — that library-API
module is still just a named, not-yet-built sibling in this diagram, so
there is nothing for the web layer to route through yet. If `codeatlas.api`
is built later, `codeatlas.web` should be refactored to call through it
rather than duplicating the orchestration call, but that refactor is not
part of this change.
The Analysis Engine depends on the LLM abstraction's *interface*
(`ModelProvider` protocol), never on a concrete provider (e.g. the
`anthropic` SDK) — that keeps the model swappable per §25 of the spec.

## 2. Technology Stack

- **Language:** Python 3.11+ (3.13 available in this environment).
- **Packaging:** `pyproject.toml` + `uv` for dependency management.
- **Data models:** `pydantic` v2 — gives strong typing, JSON schema export
  (useful for future API responses), and validation for free.
- **Knowledge store:** SQLite via `sqlite3` (stdlib) with a thin repository
  pattern — swappable for Postgres later without touching callers.
- **Evidence store:** JSON files on disk, one per evidence record, indexed
  by SQLite rows that point at them (keeps large evidence blobs out of the
  DB, makes evidence individually diffable/auditable).
- **File discovery:** stdlib `pathlib` + `pathspec` (gitignore-style
  matching) for exclusion rules; no shelling out to `git` required for
  core discovery (git metadata is a bonus signal, not a dependency).
- **AST/code parsing:** stdlib `ast` for Python; regex/line-based heuristics
  for other ecosystems in V1 (tree-sitter is a natural V1.1 upgrade — see
  §14 — kept behind the same `Detector`/`Analyzer` interfaces so swapping
  the parsing backend later doesn't change call sites).
- **LLM:** `anthropic` Python SDK behind `codeatlas.llm.ModelProvider`.
  Default model configurable via env var, not hardcoded.
- **CLI:** stdlib `argparse` (no framework dependency for a handful of
  subcommands).
- **Testing:** `pytest`.

No web framework, no browser automation, no task queue in V1 — nothing
here needs them yet, and adding them later is additive, not a rewrite.

## 3. Project Knowledge Schema

Implemented as pydantic models in `codeatlas/knowledge/schema.py`. Top
level:

```
ProjectKnowledge
├── project_id, name, root_path, analyzed_at
├── overview: Overview
├── technology_stack: TechnologyStack
├── repository_structure: RepositoryStructure
├── architecture: Architecture
├── components: list[Component]
├── application_flows: list[ApplicationFlow]
├── business_rules: list[BusinessRule]
├── api_catalog: list[ApiEndpoint]
├── database_model: DatabaseModel
├── authentication: AuthenticationModel
├── authorization: AuthorizationModel
├── external_integrations: list[ExternalIntegration]
├── configuration: list[ConfigurationItem]
├── coding_standards: CodingStandards
├── deployment: DeploymentModel
├── existing_tests: TestInventory
├── dependencies: list[Dependency]
├── known_issues: list[KnownIssue]
├── unknowns: list[Unknown]
└── evidence_index: list[EvidenceRef]   # pointers into the Evidence Engine
```

Every field that represents a *conclusion* (not a raw discovered fact)
carries a `VerificationStatus` and a list of `EvidenceRef` — see §4. This
is enforced at the type level: `Finding[T]` is a generic wrapper
`{value: T, confidence: float, status: VerificationStatus, evidence: list[EvidenceRef], reasoning: str}`
reused across the schema, so nothing can report a conclusion without also
carrying its status and evidence pointers.

Storage: each top-level section is a row keyed by `(project_id, section)`
in SQLite, JSON-encoded. Querying "give me the API catalog" is a single
indexed lookup; future agents don't need to parse one giant document.

## 4. Evidence Schema

```
Evidence
├── evidence_id (uuid)
├── finding_id            # the knowledge item this supports
├── source_file           # repo-relative path
├── source_location       # line range or symbol name, when known
├── excerpt               # short, secret-redacted snippet
├── reasoning             # why this excerpt supports the finding
├── confidence: float     # 0..1
├── verification_status: CONFIRMED | INFERRED | UNVERIFIED | CONTRADICTED | UNKNOWN
├── discovered_at: datetime
└── discovered_by: "static" | "llm:<model-id>"
```

Rules enforced in code, not just convention:
- `CONFIRMED` requires at least one `Evidence` record with `discovered_by == "static"`
  (i.e. a human or deterministic parser, not the LLM, can point at the exact
  line). An LLM-only claim can never be `CONFIRMED`.
- Every `Finding` must carry ≥1 `EvidenceRef`, or it must be `UNKNOWN`
  with an explanation of what was looked for and not found.
- Evidence excerpts pass through the secret-redaction filter (§8 below)
  before they are ever written to disk.

These rules are checked by `codeatlas.evidence.schema.assert_status_supported`,
called at every evidence-backfill site in `orchestrator/pipeline.py` via its
`_link_evidence` helper — a construction-time guard, not just a convention
analyzer authors are expected to follow. **Known, deliberate exception:**
`TechnologyItem` entries (`TechnologyStack.items`) are not yet covered —
several ecosystem/infra detectors don't create a matching `Evidence`
record for every item they produce (e.g. a Python runtime-version item),
and fixing that needs per-detector changes, not pipeline wiring. Tracked
as open work, not silently ignored.

## 5. Discovery Workflow

Discovery is static, deterministic, and runs with **zero LLM calls** —
these are facts, not interpretations.

```
1. Repository Layer walks the tree once, gitignore-aware, skipping
   vendor/build/binary/lock-file content (still records their existence).
2. Ecosystem detectors run against manifest files (package.json,
   pyproject.toml/requirements.txt, *.csproj, pom.xml/build.gradle,
   go.mod, composer.json, ...) to determine language(s), framework(s),
   package manager(s), runtime version hints.
3. Infra detectors look for Dockerfile, docker-compose.yml, CI config
   (.github/workflows, .gitlab-ci.yml, etc.), IaC files.
4. A priority list of "high-signal" paths is built: entry points,
   config files, manifests, controllers/routes directories, service/
   model directories, migrations, auth-related files, test directories,
   README/docs. This ordering feeds the Analysis Engine next.
5. Every fact from steps 2-4 is written as CONFIRMED knowledge with
   Evidence pointing at the exact file (and line, where applicable).
```

## 6. Agent Orchestration Model

```
Orchestrator.run(repo_path):
    ctx = DiscoveryEngine.discover(repo_path)        # static, cheap
    KnowledgeStore.save(ctx.facts)                   # CONFIRMED facts
    plan = Orchestrator.build_analysis_plan(ctx)      # prioritized targets
    for step in plan:
        result = AnalysisEngine.run(step, ctx, knowledge_so_far)
        EvidenceStore.save(result.evidence)
        KnowledgeStore.merge(result.findings)
        gaps = GapDetector.update(knowledge_so_far)
    DocumentationEngine.generate(KnowledgeStore.load(project_id))
```

This is a single-pass pipeline for V1 (no iterative "investigate deeper"
loop yet — that's the natural extension point once V1's single-pass
analyzers exist and we can measure where they fall short). Each analyzer
is independent and idempotent given the same discovery context, which is
what makes §7 (incremental analysis) addable later without restructuring.

## 7. Large-Repository / Incremental Strategy

- **Never load the whole repo into one LLM context.** The orchestrator
  only ever hands an analyzer the specific files its discovery step
  flagged as relevant (e.g. "these 6 files look like auth middleware"),
  plus short structural summaries of neighbors, not full file dumps.
- **Prioritization** per §5 step 4: entry points → config/manifests →
  controllers/routes → services/models → db/migrations → auth →
  integrations → tests → docs. Deep analysis walks this order and stops
  expanding a branch once confidence is high enough or a budget
  (file count / token count per analyzer) is exhausted.
- **Chunking:** large files are split by top-level symbol (function/class)
  for Python via `ast`; for other languages, by blank-line-delimited
  blocks in V1 (tree-sitter-based symbol chunking is the planned upgrade).
- **Caching/dedup:** discovery results are keyed by file content hash;
  re-analyzing an unchanged file is a cache hit, not re-sent to the LLM.
- **Incremental re-analysis (§22 of the spec):** the content-hash cache
  is exactly what makes "detect changed files → analyze only affected
  areas" possible later — it's a filter on the same pipeline, not new
  infrastructure. Not fully wired as a CLI command in V1; the hash cache
  is built now so it is not a later rewrite.

## 8. Security / Sandbox Boundary

- All filesystem access goes through `codeatlas.repository`, which
  resolves and confines every path under the given repo root (rejects
  `..` escapes and symlink escapes).
- **No repository code is ever executed.** V1 only reads files; it never
  runs `npm install`, `pip install`, a build, or any script found in the
  target repo. (Execution is explicitly a later phase per the product
  vision — V1 does not touch it.)
- **Secret detection/redaction** (`codeatlas.repository.secrets`) scans
  every excerpt before it is stored as Evidence or written to a log:
  regex rules for common key formats (AWS, generic `_KEY`/`_SECRET`/
  `_TOKEN` assignments, private key headers, connection strings with
  embedded credentials) plus a Shannon-entropy check on assigned string
  literals. Matches are replaced with `«REDACTED:<rule-name»` before
  anything touches disk or stdout.
- **Project isolation:** knowledge/evidence are stored per `project_id`
  (derived from repo path + content hash), in separate SQLite rows / evidence
  directories — no shared mutable state between projects.
- **Known limitation, by design, not oversight:** this process still runs
  with the permissions of the host container. True sandboxing (a locked
  down subprocess/VM with no network and a read-only bind mount) matters
  most once V1 adds code *execution* (the test-running phases in the
  product vision) — it is out of scope for a read-only static/LLM analyzer
  and is called out here so it isn't silently forgotten when that phase
  starts.

## 9. Initial Folder Structure

```
CodeAtlas/
├── ARCHITECTURE.md
├── README.md
├── pyproject.toml
├── src/codeatlas/
│   ├── repository/        # safe FS walker, filters, secret redaction
│   ├── discovery/          # ecosystem + infra detectors (no LLM)
│   ├── llm/                # ModelProvider protocol + providers
│   ├── analysis/           # LLM-assisted analyzers (one per KB section)
│   ├── evidence/           # Evidence schema + store
│   ├── knowledge/          # ProjectKnowledge schema + store + gap detection
│   ├── documentation/      # Markdown generator from the KB
│   ├── orchestrator/       # pipeline wiring
│   ├── web/                # FastAPI REST API (optional [api] extra)
│   └── cli.py
└── tests/
    ├── unit/
    └── fixtures/sample_repos/   # tiny synthetic repos per ecosystem
```

## 10. V1 Milestones

1. **M1 — Foundations:** schemas (Knowledge + Evidence), repository layer,
   secret redaction, SQLite store, file-based evidence store. *No LLM
   required to test this milestone.*
2. **M2 — Discovery Engine:** ecosystem detectors (start: Python, Node/TS;
   then .NET, Java, Go, PHP), infra detectors, priority-path builder.
   Produces CONFIRMED facts end-to-end on a real repo.
3. **M3 — Model Provider Abstraction:** `ModelProvider` protocol, Anthropic
   implementation, a `NullProvider` for offline/no-key runs so the
   pipeline degrades gracefully (AI sections → UNKNOWN, not fake data).
4. **M4 — First Analyzers:** architecture/component inference and API
   catalog discovery (highest value, most verifiable). Gap detector.
5. **M5 — Documentation Engine:** generate the 19-section report from
   structured knowledge, including the Unknowns/Evidence Index sections.
6. **M6 — CLI + end-to-end run** against a real multi-file repo, plus
   unit/integration tests.
7. **M7 — Remaining analyzers:** business rules, database model, auth,
   integrations, coding standards, deployment, test inventory,
   dependencies — added one at a time, each validated against a real repo
   before moving to the next.
   - **Database model: done.** `codeatlas/analysis/database.py` detects
     engine + ORM/ODM from declared dependencies, migrations from the
     existing priority plan + `alembic.ini`, and table/column schema for
     SQLAlchemy declarative models and Prisma schema files.
   - **Authentication & authorization: done.** `codeatlas/analysis/authentication.py`
     detects the auth mechanism (JWT/OAuth2/session) from dependency names
     and direct JWT call-site scanning, password-hashing library usage,
     and a role/permission-check scan feeding an RBAC-vs-ad-hoc
     authorization classification.
   - **External integrations: done.** `codeatlas/analysis/integrations.py`
     detects third-party providers (payment, email, SMS/video, team
     messaging, cloud storage, auth providers, message queues) from
     declared dependency names, attributes webhook routes only when a
     route both says "webhook" and names the provider, and matches
     config-file key *names* (never values) to a provider. Broad,
     multi-purpose SDKs (`boto3`, `aws-sdk`) confirm the provider but not
     a specific purpose, so they're INFERRED rather than CONFIRMED.
   - **Business rules: done, Python-only.** `codeatlas/analysis/business_rules.py`
     detects explicit Pydantic `Field(...)` validation constraints,
     role-gated business actions (reusing the role-decorator pattern
     `authentication.py` already scans for, but phrased as a per-action
     rule), and Enum-based state membership (never asserting which
     transitions between states are valid). Node/TS validation-library
     parsing (Joi/Zod/Yup) and JS route+role business rules are an
     explicit, tracked gap, not implemented in this slice.
   - **Coding standards: done, Python-only.** `codeatlas/analysis/coding_standards.py`
     measures (never asserts from a handful of examples) naming-convention
     consistency for functions and classes using Python's `ast` module,
     test-file naming convention (reusing the priority plan's test file
     list), FastAPI `Depends(...)` dependency-injection usage, and
     `*Repository`-suffixed class naming. `recommended_improvements` is
     always left empty in this pass — per the spec's explicit instruction
     not to call something a violation just for differing from a
     preferred style, and no project-specific baseline is configured.
     Node/TS conventions are an explicit, tracked gap.
   - **Dependency intelligence: done, narrow scope.** `codeatlas/analysis/dependencies.py`
     detects exactly one thing — the same package pinned to different
     *exact* versions across multiple declarations (e.g.
     `requirements.txt` vs `pyproject.toml`), reported as a `KnownIssue`.
     Version ranges are never compared for compatibility (no semver
     range-intersection logic is implemented), so a range-vs-range or
     range-vs-pin mismatch is never flagged — explicit, tracked gaps, as
     are "potentially outdated packages" (would need live package-
     registry network access, out of scope for this architecture) and
     internal/workspace dependency classification (no schema field for
     it yet). Still open in M7: deployment depth.
8. **M8 — Real-world validation** against the project types listed in
   spec §28.

M1-M6 and the database, authentication, integrations, business-rules,
coding-standards, and dependency-intelligence slices of M7 are
implemented and tested; deployment depth is the one M7 item still open.

## 11. Major Technical Risks

- **LLM hallucination leaking into CONFIRMED status.** Mitigated by the
  hard rule in §4 (CONFIRMED requires static evidence) enforced in code,
  not just prompting.
- **Cost/latency on large repos.** Mitigated by prioritization + chunking
  + caching (§7), but real budgets will need tuning against real repos —
  expect this number to move after M8.
- **Ecosystem breadth vs. depth.** Supporting 10 ecosystems well is a lot
  of surface area; V1 goes deep on 1-2 (Python, Node/TS) and shallow-but-
  honest (clearly marked UNKNOWN rather than guessed) on the rest, per the
  spec's own "V1 does not need perfect support for every ecosystem" note.
- **Secret redaction false negatives.** Regex/entropy heuristics will miss
  some secret formats. This is a defense-in-depth layer, not a guarantee;
  documented as a known limitation, not sold as complete protection.
- **Evidence/Knowledge schema churn.** Locking the schema too early could
  force painful migrations once real repos reveal gaps. Mitigated by
  versioning the schema (`schema_version` field) from day one.

## 12. Explicitly NOT Built in V1

- Test execution / test running engine
- Browser automation / UI testing
- Autonomous code fixing
- Performance testing execution
- Security testing *execution* (active scanning/attacks) — static
  understanding of auth/authz only
- Hosted, production-ready web **UI**, or any multi-tenant backend
  service. A minimal REST **API** skeleton now exists (`codeatlas.web`,
  §13) — one endpoint wrapping the orchestrator, no auth, no upload/
  clone support, no job queue. This is not the same thing as a hosted
  product, and running it on an untrusted network is still an operator
  decision this layer does not make safe by itself.
- Real sandboxed code execution environment (no code execution happens at
  all in V1, so this isn't built yet — see §8)
- Full tree-sitter-based parsing for every ecosystem (regex/AST-stdlib
  heuristics stand in for non-Python ecosystems in V1)
- Fully automated incremental re-analysis as a CLI command (the caching
  substrate is built; the "watch for changes and re-run" command is not)

## 13. Web API Layer (`codeatlas.web`)

Added after initial V1, by explicit request, as a genuinely new
architectural layer (not a vertical slice) — scoped deliberately narrow:

- **Dependency placement:** `fastapi`/`uvicorn` are an optional
  `[project.optional-dependencies] api` extra, not a core dependency.
  CLI/library-only installs stay dependency-light, matching §2's
  original "no web framework... nothing here needs it" reasoning —
  until something explicitly opts in via `pip install codeatlas[api]`.
- **Endpoints (initial skeleton):** `GET /health` (liveness) and
  `POST /analyze` (wraps `Orchestrator.run()`, returns `ProjectKnowledge`
  + the Markdown report as JSON — reusing the existing pydantic schema
  directly as the response model, no parallel API schema).
- **Trust boundary, stated plainly:** the CLI trusts whoever runs it to
  only point it at paths they already have filesystem access to. A
  network caller is not that person, so `repo_path` is never trusted as
  given. It is resolved and confined under a server-configured
  `CODEATLAS_API_ALLOWED_ROOT` (mirroring `RepositoryWalker`'s own path
  confinement, applied at the network boundary instead); any path
  escaping that root — absolute paths included — is rejected with 403.
  If `CODEATLAS_API_ALLOWED_ROOT` is unset, every analysis request fails
  closed with 503 rather than defaulting to "anything on disk is fair
  game." `CODEATLAS_API_DATA_DIR` (where the knowledge base/evidence are
  written) is likewise server-configured, never client-supplied — one
  fewer filesystem path for a network caller to control.
- **Execution model:** `Orchestrator.run()` is synchronous and file-I/O
  bound; the route function is a plain (non-`async`) function, so
  FastAPI/Starlette run it in its default worker thread pool rather than
  blocking the event loop. No job queue, no background-task tracking —
  consistent with §1's "no task queue in V1" and still true here.
- **Deliberately not built in this initialization:** repo upload or
  git-clone support (a materially bigger feature — storage, cleanup,
  size limits — than initializing the layer); authentication/
  authorization on the endpoints (running this server at all remains an
  operator decision this layer does not make safe by itself);
  multi-tenancy; a `codeatlas.api` library-API indirection (the web
  layer calls `Orchestrator` directly today, matching how the CLI
  already does it — see §1's note on this).

## 14. Authentication Architecture for `codeatlas.web` (Design Only — Not Implemented)

**Revision note:** this section originally recommended a static API-key
scheme for a handful of trusted internal callers. The product direction
has since been clarified: CodeAtlas is a browser-based product where an
end user signs up, logs in, creates projects, and runs analyses. A
shared API key cannot express "this is Alice's project, not Bob's," so
that recommendation is replaced below with a first-party user-account
system. Nothing in the old §14.3/§14.4 interface (`AuthProvider` /
`Principal` / `ApiKeyAuthProvider`) survives this revision except the
general shape ("a narrow interface, one concrete implementation behind
it") — see §14.4.

**Disambiguation, stated up front, unchanged from the prior revision:**
this section is about authenticating *end users of CodeAtlas's own
product* — who can sign up, log in, and own projects in this system. It
has nothing to do with `codeatlas.analysis.authentication`, which
studies how a *target repository being analyzed* handles auth. The two
are unrelated systems that happen to share the word "authentication";
conflating them while implementing this would be a real mistake. (It is
a genuinely amusing coincidence that `codeatlas.analysis.authentication`
already knows how to *detect* bcrypt/password-hashing usage in other
people's codebases — §14.5 below chooses a hashing algorithm for
CodeAtlas's own use, which is a product decision, not something that
analyzer produces or consumes.)

This section remains a design, written in response to an explicit
"design only, do not implement" request. No code, schema, or dependency
exists for anything below — `codeatlas.web` still has zero
authentication today, exactly as §13 documents.

### 14.1 Problem, restated for the real product shape

Right now, anyone who can reach the server can call `/analyze` for any
repository under `CODEATLAS_API_ALLOWED_ROOT`, with no caller identity
at all. The real product needs more than "reject anonymous callers": it
needs **accounts** (so a person can come back and see their own past
work), **ownership** (so Alice's projects aren't Bob's to read or run),
and a browser-appropriate credential (a cookie a `<form>` POST or
`fetch()` call carries automatically — not a bearer token a human has to
paste into a header).

### 14.2 Design goals

- Real user accounts: email/password signup, login, logout, password
  reset — the full lifecycle, not just "reject anonymous."
- Server-side sessions, not stateless tokens (JWT or otherwise) and not
  Starlette's built-in `SessionMiddleware` either — that middleware
  signs session *data* into the cookie itself (stateless, just
  tamper-evident); this design puts only an opaque session ID in the
  cookie and keeps the actual session record server-side, so a session
  can be revoked (logout, password reset, admin action) by deleting one
  row, not by waiting for a token to expire. This distinction is worth
  stating explicitly because the two are easy to conflate and only one
  of them is "server-side sessions" in the sense asked for.
- `User → Project → Analysis` ownership as real, enforced data
  relationships, not just documentation — every protected endpoint
  checks the requesting user owns the resource before touching it.
- Fail closed, consistent with precedent already set in §13
  (`CODEATLAS_API_ALLOWED_ROOT` / `CODEATLAS_API_DATA_DIR`): missing
  configuration (e.g. no session-signing/storage setup) means the
  protected surface refuses to serve, never silently falls back to
  "open."
- Stay proportionate to what was actually asked for: first-party
  email/password accounts, server-side sessions, cookies, CSRF
  protection, password reset, and ownership. No OAuth/social login, no
  external identity provider, no billing/subscriptions, no
  speculative multi-tenant infrastructure (organizations, teams, roles,
  per-tenant quotas) beyond the single-owner `Project`/`Analysis`
  relationship actually requested. SQLite, matching the project's
  existing storage choice (§2) and keeping a second real database out of
  scope for V1.
- Preserve CLI functionality exactly as-is: `codeatlas.cli`,
  `Orchestrator`, `KnowledgeStore`, and `EvidenceStore` are untouched by
  everything below. The CLI's trust model (whoever runs it already has
  filesystem access) doesn't need accounts, sessions, or ownership —
  see §14.11.

### 14.3 Data model

A new SQLite database, physically separate from `knowledge.db`
(`accounts.db`, written with stdlib `sqlite3` the same way
`KnowledgeStore` already is — §2's "thin repository pattern," no ORM
introduced). Separating it from `knowledge.db` means a compromise of
analysis data doesn't directly expose password hashes, and vice versa,
and it keeps "data CodeAtlas's own product owns about its users" cleanly
apart from "data CodeAtlas produced by analyzing someone else's repo."

```
User
├── id (uuid)
├── email (unique, case-insensitively normalized)
├── password_hash (argon2id — see §14.5)
├── created_at
└── email_verified: bool = False   # see §14.9 -- deferred, column reserved

Session
├── id (opaque random token -- this is the only session "state" the browser holds)
├── user_id → User
├── created_at
├── expires_at
├── last_seen_at
└── revoked: bool = False          # set on logout / password reset, not deleted immediately (audit)

PasswordResetToken
├── id
├── user_id → User
├── token_hash                     # the token itself is never stored -- same reasoning as password_hash
├── created_at
├── expires_at                     # short-lived, e.g. 30-60 minutes
└── used_at: datetime | None

Project
├── id (uuid)
├── owner_user_id → User
├── name
└── created_at

Analysis
├── id (uuid)
├── project_id → Project
├── knowledge_project_id           # the EXISTING ProjectKnowledge.project_id string -- see naming note below
├── requested_by_user_id → User
├── status                         # "pending" | "completed" | "failed" -- see §14.8 on execution model
└── created_at
```

**Naming collision, flagged rather than silently resolved:** the
existing `ProjectKnowledge.project_id` (§3) is a content-hash-derived
identifier for *what was analyzed* — it has nothing to do with the
`Project` entity above, which is a user-facing *ownership/organization*
concept (e.g. "Alice's Backend Repo"). Having both called "project" is
a real naming collision this design does not think is fine to ship
as-is — §14.12 lists it as an open decision (e.g. rename the ownership
entity to `Workspace` or rename the knowledge concept, rather than
guessing which one changes).

`Analysis` is the join between the two worlds: it belongs to a `Project`
(ownership) and points at a `knowledge_project_id` (the actual
`ProjectKnowledge` row, still living in the existing, unchanged
`KnowledgeStore`/`EvidenceStore`). Authorization checks happen entirely
in `accounts.db` (does this user own this `Project`?) before ever
touching `knowledge.db` — the existing knowledge/evidence storage layer
is reused as-is, not duplicated or modified, per `CLAUDE.md`'s "reuse,
don't duplicate."

### 14.4 Interface shape (kept from the prior revision)

The prior design's instinct — a narrow interface with one concrete
implementation behind it, mirroring `codeatlas.llm.ModelProvider` — still
applies, just scoped to what's actually swappable here: how a request is
mapped to a `User`.

```
SessionStore (protocol, codeatlas.web.accounts — not yet created)
    def create(user_id) -> Session
    def get(session_id) -> Session | None   # None if missing, expired, or revoked
    def revoke(session_id) -> None
    def revoke_all_for_user(user_id) -> None   # used on password reset

PasswordHasher (protocol)
    def hash(password: str) -> str
    def verify(password: str, password_hash: str) -> bool
```

A FastAPI dependency (`require_user`) reads the session-id cookie, calls
`SessionStore.get`, loads the associated `User` if the session is valid,
and raises `401` otherwise — this is what `/projects`, `/analyze`, etc.
depend on. `SessionStore`/`PasswordHasher` being protocols (not a
concrete SQLite class hardcoded into every route) is what keeps this
swappable later without a rewrite, the same reasoning §14 originally
gave for `AuthProvider`.

### 14.5 Signup, login, logout

- **`POST /auth/signup`** `{email, password}` → validate email format
  and password (minimum length is the main requirement; full policy is
  a tunable, not fixed here) → reject if the email is already
  registered (generic error, doesn't leak *why* beyond "already in
  use" since that's unavoidable for signup specifically) → hash the
  password (§14.6) → create `User` → create a `Session` → set the
  session cookie (§14.7) → respond with the user's own public profile
  (id, email, created_at) — **a password hash is never present in any
  response body, ever.**
- **`POST /auth/login`** `{email, password}` → look up by normalized
  email → verify password against the stored hash → on success, create
  a `Session` and set the cookie; on failure, a single generic "invalid
  email or password" for both "no such user" and "wrong password" (this
  is the standard mitigation for account enumeration via the login
  endpoint specifically — note the signup endpoint above cannot offer
  the same protection, since it must tell the user their email is
  already registered to be usable at all; that's a real, known tradeoff,
  not an oversight).
- **`POST /auth/logout`** → revoke the current session server-side
  (`SessionStore.revoke`) and clear the cookie. Revoking server-side,
  not just clearing the cookie client-side, is what makes this a real
  logout rather than a cosmetic one (a copied cookie value would
  otherwise keep working).
- **Brute-force protection** (login attempt rate limiting / lockout) is
  a real, known gap this design does not solve — flagged in §14.12, not
  silently assumed away.

### 14.6 Password hashing

**Argon2id**, via the `argon2-cffi` package (new dependency, `api`
extra only — the CLI never needs it) — currently the first choice in
OWASP's Password Storage Cheat Sheet, memory-hard (meaningfully more
GPU/ASIC-crack-resistant than bcrypt), and its `verify` function is
timing-safe by construction, so no separate constant-time-compare logic
needs to be written. bcrypt (via the `bcrypt` package) is an acceptable
fallback if `argon2-cffi`'s native-build requirement is ever a problem
in a target deployment environment — flagged as a real alternative, not
dismissed, but Argon2id is the recommendation pending the sign-off in
§14.12.

### 14.7 Sessions and cookies

- Session ID: `secrets.token_urlsafe(32)` (stdlib, no new dependency) —
  this is the only value stored in the cookie. The actual session
  record (user, timestamps, revoked flag) lives server-side in
  `accounts.db`, per §14.2's explicit "not Starlette's `SessionMiddleware`"
  note.
- Cookie attributes:
  - `HttpOnly` — JavaScript cannot read it, which is what makes stealing
    the session via XSS meaningfully harder.
  - `Secure` — sent only over HTTPS. In local development over plain
    HTTP this would silently stop the cookie from being set at all; the
    recommendation is an env-var-gated dev-mode override (matching the
    project's existing env-var-configuration convention), not loosening
    the default.
  - `SameSite=Lax` — blocks the cookie from being sent on cross-site
    `POST` requests (the primary CSRF vector) while still working for
    normal top-level navigation (e.g. following a link from an email).
    `Strict` is stronger but breaks that case; `Lax` is the standard
    pragmatic default and pairs with §14.8's explicit CSRF token as
    defense in depth, not as the sole defense.
  - `Path=/`, and an expiry — recommend a sliding window (e.g. 14 days,
    refreshed on activity via `last_seen_at`) over a hard fixed expiry,
    but this is a tunable, not fixed here.

### 14.8 CSRF protection

Cookies are sent automatically by the browser on same-site requests,
which is exactly what makes a plain cookie-authenticated endpoint
vulnerable to CSRF (a third-party site can trigger a request that
carries the victim's cookie without their intent). `SameSite=Lax`
(§14.7) is the primary defense; on top of it, state-changing endpoints
(`POST`/`PUT`/`DELETE` — signup/login are the exception, since there's
no session yet to protect at that point) require the classic
**double-submit cookie** pattern:

1. On login/signup, in addition to the `HttpOnly` session cookie, set a
   second, *non*-`HttpOnly` cookie carrying a random CSRF token.
2. The frontend JS reads that cookie and sends its value back on every
   state-changing request as a custom header (e.g. `X-CSRF-Token`).
3. The server rejects the request unless the header value matches the
   CSRF cookie value.

A third-party site can make the browser attach the session cookie
automatically, but it cannot read the CSRF cookie's value (same-origin
policy) to put it in the header — so a forged cross-site request fails
this check even if `SameSite` were somehow bypassed. No new dependency
needed; this is stdlib `secrets` plus a comparison, matching the
project's general preference for minimal dependencies.

### 14.9 API authentication and authorization

- Every protected route depends on `require_user` (§14.4): no valid
  session cookie → `401`.
- Authorization is ownership-based, not role-based (no roles/RBAC exist
  in this design — there is exactly one kind of relationship: a `User`
  owns a `Project`): a route operating on a `Project` or `Analysis`
  loads it and checks `project.owner_user_id == current_user.id` (or
  the equivalent through `Analysis.project_id`) before doing anything
  else; mismatch → `404`, not `403` — returning `404` for "exists but
  not yours" rather than `403` avoids confirming to an authenticated-
  but-unauthorized caller that a given project ID exists at all, which
  is standard practice for resource-level authorization.
- The existing `/analyze` endpoint (§13) as it stands today — a single
  server-filesystem `repo_path` confined to `CODEATLAS_API_ALLOWED_ROOT`
  — does not fit a signup-based product where arbitrary end users don't
  have paths on the server's filesystem to point at. This design does
  **not** solve that: it is the same "repo upload / git-clone support"
  gap §13 already named as deliberately deferred ("a materially bigger
  feature... than initializing the layer"), now simply more visible
  because accounts make self-serve project creation a real expectation.
  Until repo ingestion is designed, a real end user's only path to an
  `Analysis` is still a repository already present under
  `CODEATLAS_API_ALLOWED_ROOT` — meaning V1 of the authenticated product
  is realistically usable for an operator-curated set of repositories
  (e.g. an internal company deployment), not yet a true "paste your
  GitHub URL" self-serve flow. Naming this gap honestly here, rather
  than letting "add accounts" quietly imply "and now arbitrary repos
  work too," is the point of calling it out.
- Execution model is unchanged from §13: `Orchestrator.run()` stays
  synchronous, called from a plain (non-`async`) route in FastAPI's
  default thread pool. `Analysis.status` exists in the data model
  (§14.3) to let a future async/job-queue execution model be introduced
  without a schema rewrite, but nothing here builds that queue — this
  is the same "don't block a future decision, don't build it either"
  posture as the original §14.3 Principal/data-isolation split.

### 14.10 Password reset architecture

1. **`POST /auth/password-reset/request`** `{email}` → always return
   the same generic response ("if that email is registered, a reset
   link was sent"), regardless of whether the email exists — this is
   the standard mitigation for user enumeration via the reset flow. If
   the user does exist: generate a random token (`secrets.token_urlsafe`),
   store only its hash (`PasswordResetToken.token_hash`, §14.3 — same
   "never store the raw secret" reasoning as session IDs and passwords)
   with a short expiry (30-60 minutes), and deliver the raw token to the
   user via a reset link.
2. **Actually delivering that link requires sending an email** —
   CodeAtlas has no email-sending integration today. This design
   specifies the *token* architecture fully; which email provider (or
   whether to just log the link in a non-production/dev mode) is a
   genuine open integration decision, not decided here — see §14.12.
3. **`POST /auth/password-reset/confirm`** `{token, new_password}` →
   look up by the *hash* of the submitted token, reject if not found,
   expired, or already used → hash and set the new password → mark the
   token used → **revoke every existing session for that user**
   (`SessionStore.revoke_all_for_user`) — a password reset should force
   re-login everywhere, including on a device an attacker may have
   stolen a session from, which is exactly why `revoke_all_for_user`
   exists in §14.4's interface and not just single-session revoke.

### 14.11 CLI functionality is unaffected

`codeatlas.cli`, `Orchestrator`, `KnowledgeStore`, and `EvidenceStore`
are not touched by anything in this section. The CLI's trust model —
whoever runs it already has filesystem access to the repo they're
pointing it at — has no use for accounts, sessions, or ownership, and
nothing here changes how `codeatlas analyze <path>` works. `accounts.db`
is created and read only by `codeatlas.web`.

### 14.12 Explicitly out of scope / deferred (named, not silently skipped)

- **OAuth / social login** — not designed here, per explicit instruction.
- **External identity provider** — not designed here, per explicit
  instruction. If ever added, it should be additive behind the same
  `SessionStore`/`require_user` seam (§14.4), not a parallel auth path.
- **Billing / subscriptions** — not designed here, per explicit
  instruction; no plan/quota concept exists anywhere above.
- **Speculative multi-tenant infrastructure** — no organizations, teams,
  roles, or per-tenant resource quotas. The only ownership relationship
  is the single-owner `User → Project` one actually requested.
- **Email delivery integration** — the password-reset *token* lifecycle
  is fully designed (§14.10); which provider sends the email, or how
  dev/local environments see the link at all, is not.
- **Email verification** — the `User.email_verified` column is reserved
  in §14.3's schema sketch but no verification flow is designed; accounts
  are usable immediately after signup in this design.
- **Brute-force / credential-stuffing protection** (login rate limiting,
  lockout, CAPTCHA) — a real, known gap, not assumed away; flagged as
  follow-up hardening.
- **Repo ingestion for self-serve project creation** (upload or
  git-clone) — restates §13's existing deferral; §14.9 explains why
  accounts alone don't resolve it.
- **Multi-user collaboration on a single `Project`** (sharing, roles
  within a project) — out of scope; the model is strictly single-owner.

### 14.13 Open decisions needing sign-off before implementation

Per `CLAUDE.md`, named here rather than decided unilaterally:

1. **The `Project`/`project_id` naming collision** (§14.3) — rename the
   new ownership entity (e.g. `Workspace`), rename the existing
   knowledge concept, or something else.
2. **Password hashing algorithm:** Argon2id via `argon2-cffi`
   (recommended, §14.6) vs. bcrypt, trading a native-build dependency
   for broader out-of-the-box availability in some environments.
3. **Session expiry policy:** sliding window vs. fixed, and the actual
   duration.
4. **`404` vs. `403`** for "authenticated but not the owner" (§14.9
   recommends `404`, to avoid confirming a resource's existence to an
   unauthorized caller — some products prefer the more explicit `403`
   at the cost of that leak).
5. **Email delivery provider** for password reset (§14.10/§14.12), or
   an explicit decision to defer it and only support dev-mode link
   logging until a provider is chosen.
6. **Password policy specifics** (minimum length, common-password
   blocklist, etc.) beyond "has a minimum length," which this design
   treats as a tunable rather than fixing a number.
