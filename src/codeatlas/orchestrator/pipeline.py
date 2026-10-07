"""Agent Orchestrator — ARCHITECTURE.md §6.

Single-pass V1 pipeline: discover (static) → analyze (static heuristics,
LLM hooks reserved for later) → assemble knowledge → detect gaps → persist
→ generate documentation. Every step is independently testable (see
tests/unit/test_m1..m6), which is what this wiring module is allowed to
assume.

Every status-bearing knowledge object's evidence is backfilled through
``_link_evidence``, which also enforces the CONFIRMED-requires-static-
evidence invariant (ARCHITECTURE.md §4) via
``codeatlas.evidence.schema.assert_status_supported``. That function has
existed since M1 but was never actually wired into a construction path
until now -- it was unit-tested in isolation but dormant everywhere else,
so nothing would have caught a future analyzer shipping a fabricated
CONFIRMED claim.

Known, deliberate scope limit: ``TechnologyItem`` entries (``ctx.result.
technology_items`` / ``ProjectKnowledge.technology_stack.items``) are
NOT covered by this enforcement. Several ecosystem/infra detectors
(``python_eco.py``, ``node_eco.py``, ``shallow.py``) create
``TechnologyItem`` instances with their default ``status=CONFIRMED``
without creating or linking a matching ``Evidence`` record for every one
of them (e.g. the Python runtime-version item, pip-from-requirements.txt,
npm script notes). Turning on enforcement there would require auditing
and fixing every detector file -- a discovery-engine-wide change, not a
pipeline-wiring one -- so it is intentionally left for a separate task
rather than folded into this slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codeatlas.analysis.api_catalog import analyze_api_catalog
from codeatlas.analysis.architecture import analyze_architecture
from codeatlas.analysis.authentication import analyze_authentication
from codeatlas.analysis.business_rules import analyze_business_rules
from codeatlas.analysis.coding_standards import analyze_coding_standards
from codeatlas.analysis.database import analyze_database
from codeatlas.analysis.integrations import analyze_integrations, provider_token
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.documentation.generator import generate_markdown
from codeatlas.evidence.schema import Evidence, VerificationStatus, assert_status_supported, evidence_to_ref
from codeatlas.evidence.store import EvidenceStore
from codeatlas.knowledge.gaps import detect_gaps
from codeatlas.knowledge.schema import (
    DeploymentModel,
    Finding,
    Overview,
    ProjectKnowledge,
    TechnologyStack,
    TestInventory,
)
from codeatlas.knowledge.store import KnowledgeStore
from codeatlas.repository.walker import RepositoryWalker


def _link_evidence(target, matching_evidence: list[Evidence]) -> None:
    """Backfill ``target.evidence`` from ``matching_evidence`` and enforce
    the CONFIRMED-requires-static-evidence invariant in the same step.

    ``target`` is any object exposing ``.status`` (a ``VerificationStatus``)
    and ``.evidence`` (a ``list[EvidenceRef]``) directly -- a ``Finding``,
    or one of the knowledge objects that carry those two fields themselves
    (``ApiEndpoint``, ``BusinessRule``, ``TableInfo``, ``ExternalIntegration``,
    ``AuthenticationModel``, ``AuthorizationModel``).
    """
    assert_status_supported(target.status, matching_evidence)
    target.evidence = [evidence_to_ref(e) for e in matching_evidence]


@dataclass
class AnalysisRun:
    knowledge: ProjectKnowledge
    markdown_report: str
    data_dir: Path


class Orchestrator:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    def run(self, repo_path: str) -> AnalysisRun:
        ctx = DiscoveryEngine().discover(repo_path)
        walker = RepositoryWalker(ctx.root_path)

        all_evidence: list[Evidence] = list(ctx.result.evidence)

        api_endpoints, api_evidence = analyze_api_catalog(ctx, walker)
        all_evidence += api_evidence
        for ep, ev in zip(api_endpoints, api_evidence):
            _link_evidence(ep, [ev])

        architecture, components, arch_evidence = analyze_architecture(ctx)
        all_evidence += arch_evidence
        for comp in components:
            comp_evs = [e for e in arch_evidence if e.finding_id == f"architecture:layer:{comp.kind}"]
            comp.evidence = [evidence_to_ref(e) for e in comp_evs]  # kept for schema completeness; not rendered
            if comp.description is not None:
                _link_evidence(comp.description, comp_evs)
        if architecture.style is not None:
            # The style conclusion is derived from the full set of detected layers,
            # so every layer's evidence supports it.
            _link_evidence(architecture.style, arch_evidence)

        database_model, db_evidence = analyze_database(ctx, walker)
        all_evidence += db_evidence
        for table in database_model.tables:
            table_evs = [e for e in db_evidence if e.finding_id == f"database:table:{table.name}:{table.source_file}"]
            _link_evidence(table, table_evs)
        if database_model.engine is not None:
            _link_evidence(database_model.engine, [e for e in db_evidence if e.finding_id == "database:engine"])
        if database_model.orm is not None:
            _link_evidence(database_model.orm, [e for e in db_evidence if e.finding_id == "database:orm"])

        authentication, authorization, auth_evidence = analyze_authentication(ctx, walker)
        all_evidence += auth_evidence
        # AuthenticationModel/AuthorizationModel have no .status of their own (only
        # their nested mechanism/model Finding does), so _link_evidence doesn't apply
        # to them directly -- the invariant is enforced on the nested Finding instead.
        if authentication.mechanism is not None:
            mechanism_evs = [e for e in auth_evidence if e.finding_id == "authentication:mechanism"]
            _link_evidence(authentication.mechanism, mechanism_evs)
        authentication.evidence = [
            evidence_to_ref(e) for e in auth_evidence if e.finding_id.startswith("authentication:")
        ]
        if authorization.model is not None:
            model_evs = [e for e in auth_evidence if e.finding_id == "authorization:model"]
            _link_evidence(authorization.model, model_evs)
        authorization.evidence = [
            evidence_to_ref(e) for e in auth_evidence if e.finding_id.startswith("authorization:")
        ]

        external_integrations, integration_evidence = analyze_integrations(ctx, walker)
        all_evidence += integration_evidence
        for integration in external_integrations:
            token = provider_token(integration.provider)
            integration_evs = [e for e in integration_evidence if e.finding_id == f"integration:{token}"]
            _link_evidence(integration, integration_evs)

        business_rules, rule_evidence = analyze_business_rules(ctx, walker)
        all_evidence += rule_evidence
        for rule, ev in zip(business_rules, rule_evidence):
            _link_evidence(rule, [ev])

        coding_standards, standards_evidence = analyze_coding_standards(ctx, walker)
        all_evidence += standards_evidence

        deployment = self._build_deployment(ctx)
        if deployment.containerized is not None:
            _link_evidence(
                deployment.containerized, [e for e in ctx.result.evidence if e.finding_id == "infra:docker"]
            )
        if deployment.ci_cd is not None:
            _link_evidence(
                deployment.ci_cd, [e for e in ctx.result.evidence if e.finding_id.startswith("infra:ci:")]
            )

        existing_tests = TestInventory(
            frameworks=ctx.result.test_frameworks,
            unit_test_files=[p for p in ctx.priority_plan.tests],
        )
        overview, overview_evidence = self._build_overview(ctx)
        all_evidence.append(overview_evidence)
        _link_evidence(overview.name, [overview_evidence])

        knowledge = ProjectKnowledge(
            project_id=ctx.project_id,
            name=Path(ctx.root_path).name,
            root_path=ctx.root_path,
            overview=overview,
            technology_stack=TechnologyStack(items=ctx.result.technology_items),
            repository_structure=ctx.repository_structure,
            architecture=architecture,
            components=components,
            api_catalog=api_endpoints,
            database_model=database_model,
            authentication=authentication,
            authorization=authorization,
            external_integrations=external_integrations,
            business_rules=business_rules,
            coding_standards=coding_standards,
            dependencies=ctx.result.dependencies,
            deployment=deployment,
            existing_tests=existing_tests,
            evidence_index=[evidence_to_ref(e) for e in all_evidence],
        )
        knowledge.unknowns = detect_gaps(knowledge)

        evidence_store = EvidenceStore(self.data_dir, ctx.project_id)
        evidence_store.save_many(all_evidence)

        knowledge_store = KnowledgeStore(self.data_dir)
        knowledge_store.save(knowledge)
        knowledge_store.close()

        markdown_report = generate_markdown(knowledge)

        return AnalysisRun(knowledge=knowledge, markdown_report=markdown_report, data_dir=self.data_dir)

    @staticmethod
    def _build_overview(ctx) -> tuple[Overview, Evidence]:
        name = Path(ctx.root_path).name
        reasoning = (
            "Derived from the repository's directory name; no manifest-declared "
            "project name field was cross-checked in this pass."
        )
        # The directory name itself has no dedicated Evidence record from
        # discovery (unlike manifest-derived facts) -- it's a fact about the
        # repository root, not about a file within it, so one is created here.
        evidence = Evidence(
            finding_id="overview:name",
            source_file=".",
            excerpt=f"repository directory name: '{name}'",
            reasoning=reasoning,
            confidence=0.6,
            verification_status=VerificationStatus.INFERRED,
            discovered_by="static",
        )
        overview = Overview(
            name=Finding(value=name, confidence=0.6, status=VerificationStatus.INFERRED, reasoning=reasoning)
        )
        return overview, evidence

    @staticmethod
    def _build_deployment(ctx) -> DeploymentModel:
        signals = ctx.result.infra_signals
        containerized = None
        if "dockerized" in signals:
            containerized = Finding(
                value=True,
                confidence=0.95,
                status=VerificationStatus.CONFIRMED,
                reasoning="A Dockerfile was found in the repository.",
            )

        ci_cd = None
        ci_keys = [k for k in signals if k not in ("dockerized", "docker_compose", "terraform", "kubernetes")]
        if ci_keys:
            ci_cd = Finding(
                value=", ".join(k.replace("_", " ").title() for k in ci_keys),
                confidence=0.9,
                status=VerificationStatus.CONFIRMED,
                reasoning=f"CI configuration file(s) found identifying: {', '.join(ci_keys)}.",
            )

        return DeploymentModel(containerized=containerized, ci_cd=ci_cd)
