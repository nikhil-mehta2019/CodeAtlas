"""Gap / Unknown detection — ARCHITECTURE.md §3, spec §18.

Scans a fully-assembled ``ProjectKnowledge`` and records, as first-class
``Unknown`` entries, every major question the product spec asks (§2) that
the pipeline could not answer. This runs last in the orchestrator so it
sees the final state of every section.
"""

from __future__ import annotations

from codeatlas.knowledge.schema import ProjectKnowledge, Unknown


def detect_gaps(knowledge: ProjectKnowledge) -> list[Unknown]:
    gaps: list[Unknown] = []

    if knowledge.overview.purpose is None:
        gaps.append(Unknown(
            topic="Application purpose",
            reason="No README, docs, or analyzed source clearly stated what problem the application solves.",
            area="overview",
        ))
    if knowledge.overview.users is None:
        gaps.append(Unknown(
            topic="Target users",
            reason="No evidence (docs, role names, personas) identified who uses this application.",
            area="overview",
        ))

    if not knowledge.application_flows:
        gaps.append(Unknown(
            topic="Application flows",
            reason="No user-facing workflows (registration, checkout, etc.) were reconstructed in this pass.",
            area="application_flows",
        ))

    if not knowledge.business_rules:
        gaps.append(Unknown(
            topic="Business rules",
            reason="No validation, authorization, or workflow rules were extracted in this pass.",
            area="business_rules",
        ))

    if not knowledge.api_catalog:
        gaps.append(Unknown(
            topic="API catalog",
            reason="No API routes were detected by the static route-extraction heuristics "
                   "(the ecosystem may not be one V1's regex patterns cover, or there may be no HTTP API).",
            area="api_catalog",
        ))

    if knowledge.database_model.engine is None and not knowledge.database_model.tables:
        gaps.append(Unknown(
            topic="Database engine and schema",
            reason="No ORM models, migrations, or connection configuration were found or parsed.",
            area="database_model",
        ))

    if knowledge.authentication.mechanism is None:
        gaps.append(Unknown(
            topic="Authentication mechanism",
            reason="No JWT/session/OAuth signal was confirmed in auth-related files.",
            area="authentication",
        ))

    if knowledge.authorization.model is None:
        gaps.append(Unknown(
            topic="Authorization model",
            reason="No role/permission model was confirmed.",
            area="authorization",
        ))

    if not knowledge.external_integrations:
        gaps.append(Unknown(
            topic="External integrations",
            reason="No third-party API/payment/email/storage integrations were detected in this pass.",
            area="external_integrations",
        ))

    if knowledge.deployment.hosting is None:
        gaps.append(Unknown(
            topic="Production hosting target",
            reason="No cloud provider or hosting target could be determined from repository contents alone; "
                   "this generally requires runtime/infra access this tool does not have.",
            area="deployment",
        ))

    if not knowledge.existing_tests.unit_test_files and not knowledge.existing_tests.integration_test_files:
        gaps.append(Unknown(
            topic="Test coverage",
            reason="No test files were located; actual coverage cannot be measured without executing tests, "
                   "which V1 does not do.",
            area="existing_tests",
        ))

    if not knowledge.coding_standards.observed:
        gaps.append(Unknown(
            topic="Coding standards",
            reason="Coding-convention analysis was not run in this pass.",
            area="coding_standards",
        ))

    return gaps
