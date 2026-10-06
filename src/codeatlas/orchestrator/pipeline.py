"""Agent Orchestrator — ARCHITECTURE.md §6.

Single-pass V1 pipeline: discover (static) → analyze (static heuristics,
LLM hooks reserved for later) → assemble knowledge → detect gaps → persist
→ generate documentation. Every step is independently testable (see
tests/unit/test_m1..m6), which is what this wiring module is allowed to
assume.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codeatlas.analysis.api_catalog import analyze_api_catalog
from codeatlas.analysis.architecture import analyze_architecture
from codeatlas.analysis.authentication import analyze_authentication
from codeatlas.analysis.database import analyze_database
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.documentation.generator import generate_markdown
from codeatlas.evidence.schema import Evidence, VerificationStatus, evidence_to_ref
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
            ep.evidence = [evidence_to_ref(ev)]

        architecture, components, arch_evidence = analyze_architecture(ctx)
        all_evidence += arch_evidence
        for comp in components:
            comp_evs = [e for e in arch_evidence if e.finding_id == f"architecture:layer:{comp.kind}"]
            comp.evidence = [evidence_to_ref(e) for e in comp_evs]

        database_model, db_evidence = analyze_database(ctx, walker)
        all_evidence += db_evidence
        for table in database_model.tables:
            table_evs = [e for e in db_evidence if e.finding_id == f"database:table:{table.name}:{table.source_file}"]
            table.evidence = [evidence_to_ref(e) for e in table_evs]

        authentication, authorization, auth_evidence = analyze_authentication(ctx, walker)
        all_evidence += auth_evidence

        deployment = self._build_deployment(ctx)
        existing_tests = TestInventory(
            frameworks=ctx.result.test_frameworks,
            unit_test_files=[p for p in ctx.priority_plan.tests],
        )
        overview = self._build_overview(ctx)

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
    def _build_overview(ctx) -> Overview:
        name = Path(ctx.root_path).name
        return Overview(
            name=Finding(
                value=name,
                confidence=0.6,
                status=VerificationStatus.INFERRED,
                reasoning=(
                    "Derived from the repository's directory name; no manifest-declared "
                    "project name field was cross-checked in this pass."
                ),
            )
        )

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
