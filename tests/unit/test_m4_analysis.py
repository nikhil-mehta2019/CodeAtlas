"""M4 sanity tests: API catalog + architecture analyzers, gap detector."""

from __future__ import annotations

from pathlib import Path

from codeatlas.analysis.api_catalog import analyze_api_catalog
from codeatlas.analysis.architecture import analyze_architecture
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.evidence.schema import VerificationStatus
from codeatlas.knowledge.gaps import detect_gaps
from codeatlas.knowledge.schema import ProjectKnowledge
from codeatlas.repository.walker import RepositoryWalker

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def test_api_catalog_detects_fastapi_route():
    ctx = DiscoveryEngine().discover(str(FIXTURES / "python_fastapi"))
    walker = RepositoryWalker(FIXTURES / "python_fastapi")
    endpoints, evidence = analyze_api_catalog(ctx, walker)

    assert any(e.method == "GET" and e.path == "/health" for e in endpoints)
    assert all(e.discovered_by == "static" for e in evidence)
    assert all(e.verification_status == VerificationStatus.CONFIRMED for e in evidence)


def test_api_catalog_detects_express_route():
    ctx = DiscoveryEngine().discover(str(FIXTURES / "node_express"))
    walker = RepositoryWalker(FIXTURES / "node_express")
    endpoints, evidence = analyze_api_catalog(ctx, walker)

    paths = {(e.method, e.path) for e in endpoints}
    assert ("GET", "/health") in paths
    assert ("GET", "/users") in paths


def test_architecture_infers_layers_from_fixture():
    ctx = DiscoveryEngine().discover(str(FIXTURES / "python_fastapi"))
    architecture, components, evidence = analyze_architecture(ctx)

    assert "authentication/authorization layer" in architecture.layers
    assert any(c.kind == "auth" for c in components)
    assert architecture.mermaid_diagram is not None
    assert "graph TD" in architecture.mermaid_diagram


def test_gap_detector_flags_missing_sections():
    knowledge = ProjectKnowledge(project_id="p1", name="demo", root_path="/tmp/demo")
    gaps = detect_gaps(knowledge)
    topics = {g.topic for g in gaps}
    assert "Application purpose" in topics
    assert "API catalog" in topics
    assert "Database engine and schema" in topics
    assert "Authentication mechanism" in topics
