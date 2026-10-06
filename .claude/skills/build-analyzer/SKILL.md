---
name: build-analyzer
description: Add one new CodeAtlas repository analyzer (e.g. database, authentication, integrations, business-rules) and wire it into the existing discovery/analysis pipeline. Usage: /build-analyzer <domain>, e.g. /build-analyzer database.
---

# build-analyzer

Add exactly one new analyzer, following the pattern of the existing
analyzers in `src/codeatlas/analysis/` (`api_catalog.py`, `architecture.py`).

## Steps

1. **Inspect existing analyzer architecture.** Read `analysis/api_catalog.py`
   and `analysis/architecture.py` plus how `orchestrator/pipeline.py` calls
   them. New analyzers follow the same shape: a function that takes the
   `DiscoveryContext` (and a walker/provider as needed) and returns
   `(knowledge_objects, evidence_list)`.
2. **Identify the relevant knowledge schema** in `codeatlas/knowledge/schema.py`
   (e.g. `DatabaseModel`, `AuthenticationModel`, `ExternalIntegration`,
   `BusinessRule`). Do not change the schema unless the analyzer truly
   cannot be expressed in it — if so, propose the minimal schema addition
   and say so explicitly in the report.
3. **Identify required evidence.** What static, inspectable facts
   (file presence, import statements, decorators, config keys, ORM
   model definitions) would support `CONFIRMED` vs. `INFERRED` findings
   for this domain? List them before writing code.
4. **Implement the analyzer** using static heuristics first (regex/AST,
   consistent with `python_eco.py`/`node_eco.py`'s approach). Only use
   the `ModelProvider` abstraction (`codeatlas/llm`) for things that
   genuinely require interpretation beyond pattern matching, and always
   check `provider.is_available()` — when unavailable, mark the relevant
   fields `UNKNOWN`/`None` rather than guessing.
5. **Integrate into the pipeline**: call the analyzer from
   `orchestrator/pipeline.py` in the same style as the existing analyzers
   (collect evidence, attach `EvidenceRef`s, merge into `ProjectKnowledge`).
   Update `codeatlas/knowledge/gaps.py` if this analyzer should suppress
   an existing `Unknown` entry when it finds something.
6. **Add real tests** against the existing fixture repos
   (`tests/fixtures/sample_repos/`), extending a fixture with the minimal
   file(s) needed to exercise this analyzer if nothing currently does.
   Follow the `test_m4_analysis.py` style.
7. **Verify status behavior**: write at least one test proving a
   `CONFIRMED` finding has static evidence, one proving an ambiguous case
   comes back `INFERRED` or `UNVERIFIED` (not `CONFIRMED`), and one
   proving the analyzer returns nothing/`UNKNOWN` rather than fabricating
   a finding when there's no signal.
8. **Update documentation only where necessary**: if `documentation/generator.py`
   doesn't yet render this section meaningfully, extend its existing
   per-section renderer function rather than adding a parallel rendering
   path. Don't touch `ARCHITECTURE.md` unless the analyzer changes the
   architecture itself (new dependency, new layer) — note schema
   additions in a short changelog note instead if one exists.

## Hard rule

The analyzer must never manufacture findings. No matching evidence →
no finding (or an explicit `UNKNOWN`/`Unknown` gap entry) — never a
plausible-looking guess presented as fact.
