"""Project Knowledge schema — see ARCHITECTURE.md §3.

``Finding[T]`` is the generic wrapper that every *conclusion* (as opposed
to a raw discovered fact) in the knowledge base is expressed through. It
bundles the value with its confidence, verification status, evidence
pointers, and reasoning so that "we concluded X" and "we are sure of X"
can never be collapsed into one untyped field.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from codeatlas.evidence.schema import EvidenceRef, VerificationStatus

SCHEMA_VERSION = "0.1.0"

T = TypeVar("T")


class Finding(BaseModel, Generic[T]):
    value: T
    confidence: float = Field(ge=0.0, le=1.0)
    status: VerificationStatus
    evidence: list[EvidenceRef] = Field(default_factory=list)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Overview & technology stack
# ---------------------------------------------------------------------------


class Overview(BaseModel):
    name: Finding[str] | None = None
    purpose: Finding[str] | None = None
    users: Finding[str] | None = None
    summary: Finding[str] | None = None


class TechnologyItem(BaseModel):
    category: str  # "language" | "framework" | "runtime" | "package_manager" | "build_tool"
    name: str
    version: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.CONFIRMED


class TechnologyStack(BaseModel):
    items: list[TechnologyItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Repository structure
# ---------------------------------------------------------------------------


class DirectoryInfo(BaseModel):
    path: str
    file_count: int
    role: str | None = None  # e.g. "controllers", "tests", "migrations"
    language_breakdown: dict[str, int] = Field(default_factory=dict)


class RepositoryStructure(BaseModel):
    root_path: str
    total_files: int
    total_files_analyzed: int
    excluded_paths: list[str] = Field(default_factory=list)
    directories: list[DirectoryInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Architecture & components
# ---------------------------------------------------------------------------


class Architecture(BaseModel):
    style: Finding[str] | None = None  # e.g. "layered monolith", "microservices"
    layers: list[str] = Field(default_factory=list)
    mermaid_diagram: str | None = None
    entry_points: list[str] = Field(default_factory=list)


class Component(BaseModel):
    name: str
    kind: str  # "service" | "module" | "controller" | "library" | ...
    path: str
    depends_on: list[str] = Field(default_factory=list)
    description: Finding[str] | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Application flows & business rules
# ---------------------------------------------------------------------------


class ApplicationFlow(BaseModel):
    name: str
    description: str
    steps: list[str] = Field(default_factory=list)
    status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class BusinessRule(BaseModel):
    rule: str
    kind: str  # "validation" | "authorization" | "workflow" | "state_transition" | "constraint"
    explicit: bool  # True = explicit rule found in code/docs; False = inferred
    status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API catalog
# ---------------------------------------------------------------------------


class ApiEndpoint(BaseModel):
    method: str
    path: str
    purpose: Finding[str] | None = None
    authentication: str | None = None
    authorization: str | None = None
    request_shape: str | None = None
    response_shape: str | None = None
    error_responses: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    database_impact: str | None = None
    external_integrations: list[str] = Field(default_factory=list)
    source_file: str
    status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Database model
# ---------------------------------------------------------------------------


class ColumnInfo(BaseModel):
    name: str
    type: str | None = None
    nullable: bool | None = None
    primary_key: bool = False
    foreign_key_to: str | None = None


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)
    source_file: str | None = None
    status: VerificationStatus = VerificationStatus.INFERRED
    evidence: list[EvidenceRef] = Field(default_factory=list)


class DatabaseModel(BaseModel):
    engine: Finding[str] | None = None  # e.g. "PostgreSQL", "MongoDB"
    tables: list[TableInfo] = Field(default_factory=list)
    migrations_found: list[str] = Field(default_factory=list)
    orm: Finding[str] | None = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class AuthenticationModel(BaseModel):
    mechanism: Finding[str] | None = None  # "JWT" | "session" | "OAuth2" | ...
    token_handling: str | None = None
    password_handling: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AuthorizationModel(BaseModel):
    model: Finding[str] | None = None  # "RBAC" | "ABAC" | "ad-hoc checks"
    roles: list[str] = Field(default_factory=list)
    protected_endpoints: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# External integrations
# ---------------------------------------------------------------------------


class ExternalIntegration(BaseModel):
    purpose: str
    provider: str
    api: str | None = None
    authentication_method: str | None = None
    webhook: bool = False
    retry_behavior: str | None = None
    failure_handling: str | None = None
    configuration_keys: list[str] = Field(default_factory=list)  # names only, never values
    status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration, coding standards, deployment, tests, dependencies
# ---------------------------------------------------------------------------


class ConfigurationItem(BaseModel):
    key: str
    required: bool | None = None
    source_file: str
    description: str | None = None
    # Never store actual secret values here — see codeatlas.repository.secrets.


class CodingStandards(BaseModel):
    observed: list[str] = Field(default_factory=list)  # e.g. "PascalCase for C# classes"
    recommended_improvements: list[str] = Field(default_factory=list)
    design_patterns_observed: list[str] = Field(default_factory=list)


class DeploymentModel(BaseModel):
    build_process: Finding[str] | None = None
    containerized: Finding[bool] | None = None
    ci_cd: Finding[str] | None = None
    hosting: Finding[str] | None = None
    ports: list[int] = Field(default_factory=list)
    background_workers: list[str] = Field(default_factory=list)
    scheduled_jobs: list[str] = Field(default_factory=list)


class TestInventory(BaseModel):
    frameworks: list[str] = Field(default_factory=list)
    unit_test_files: list[str] = Field(default_factory=list)
    integration_test_files: list[str] = Field(default_factory=list)
    e2e_test_files: list[str] = Field(default_factory=list)
    areas_with_no_detected_tests: list[str] = Field(default_factory=list)
    note: str = (
        "Coverage percentages are not reported because they cannot be "
        "measured without executing the test suite, which V1 does not do."
    )


class Dependency(BaseModel):
    name: str
    version: str | None = None
    kind: str  # "direct" | "dev" | "transitive"
    ecosystem: str  # "pypi" | "npm" | "nuget" | "maven" | "go" | "composer"
    source_file: str


# ---------------------------------------------------------------------------
# Known issues & unknowns
# ---------------------------------------------------------------------------


class KnownIssue(BaseModel):
    description: str
    severity: str  # "low" | "medium" | "high"
    source_file: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class Unknown(BaseModel):
    topic: str
    reason: str  # what was looked for and why it couldn't be determined
    area: str  # which KB section this pertains to


# ---------------------------------------------------------------------------
# Top-level container
# ---------------------------------------------------------------------------


class ProjectKnowledge(BaseModel):
    schema_version: str = SCHEMA_VERSION
    project_id: str
    name: str
    root_path: str
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    overview: Overview = Field(default_factory=Overview)
    technology_stack: TechnologyStack = Field(default_factory=TechnologyStack)
    repository_structure: RepositoryStructure | None = None
    architecture: Architecture = Field(default_factory=Architecture)
    components: list[Component] = Field(default_factory=list)
    application_flows: list[ApplicationFlow] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)
    api_catalog: list[ApiEndpoint] = Field(default_factory=list)
    database_model: DatabaseModel = Field(default_factory=DatabaseModel)
    authentication: AuthenticationModel = Field(default_factory=AuthenticationModel)
    authorization: AuthorizationModel = Field(default_factory=AuthorizationModel)
    external_integrations: list[ExternalIntegration] = Field(default_factory=list)
    configuration: list[ConfigurationItem] = Field(default_factory=list)
    coding_standards: CodingStandards = Field(default_factory=CodingStandards)
    deployment: DeploymentModel = Field(default_factory=DeploymentModel)
    existing_tests: TestInventory = Field(default_factory=TestInventory)
    dependencies: list[Dependency] = Field(default_factory=list)
    known_issues: list[KnownIssue] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)
    evidence_index: list[EvidenceRef] = Field(default_factory=list)
