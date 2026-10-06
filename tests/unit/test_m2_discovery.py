"""M2 sanity tests: discovery engine against the synthetic fixture repos."""

from __future__ import annotations

from pathlib import Path

from codeatlas.discovery.engine import DiscoveryEngine

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def test_discovery_on_python_fastapi_fixture():
    engine = DiscoveryEngine()
    ctx = engine.discover(str(FIXTURES / "python_fastapi"))

    assert "python" in ctx.ecosystems_detected
    tech_names = {t.name for t in ctx.result.technology_items}
    assert "Python" in tech_names
    assert "FastAPI" in tech_names
    assert "Poetry" in tech_names

    dep_names = {d.name for d in ctx.result.dependencies}
    assert "fastapi" in dep_names
    assert "uvicorn" in dep_names

    assert ctx.result.infra_signals.get("dockerized") is True
    assert ctx.result.infra_signals.get("github_actions") is True

    # Evidence must exist for the FastAPI finding and be static.
    fastapi_evidence = [e for e in ctx.result.evidence if e.finding_id == "tech:framework:fastapi"]
    assert fastapi_evidence
    assert fastapi_evidence[0].discovered_by == "static"

    # Priority plan should surface the entry point, auth file, config, tests, docs.
    ordered = ctx.priority_plan.ordered()
    assert "app/main.py" in ordered
    assert "app/auth.py" in ordered
    assert "tests/test_health.py" in ordered
    assert "README.md" in ordered

    assert ctx.repository_structure.total_files >= 6


def test_discovery_on_node_express_fixture():
    engine = DiscoveryEngine()
    ctx = engine.discover(str(FIXTURES / "node_express"))

    assert "node" in ctx.ecosystems_detected
    tech_names = {t.name for t in ctx.result.technology_items}
    assert "JavaScript" in tech_names
    assert "Express" in tech_names
    assert "npm" in tech_names

    dep_names = {d.name for d in ctx.result.dependencies}
    assert "express" in dep_names
    assert "Jest" in ctx.result.test_frameworks

    ordered = ctx.priority_plan.ordered()
    assert "src/index.js" in ordered
    assert any("routes" in p for p in ordered)
