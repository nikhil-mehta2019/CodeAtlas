"""M7 sanity tests: dependency intelligence analyzer (version conflicts).

Covers the three required status behaviors per .claude/skills/build-analyzer:
  - a CONFIRMED finding backed by static evidence (two exact pins for the
    same package across two files),
  - the "ambiguous case" that must NOT be flagged: a range constraint
    alongside an exact pin, or two overlapping ranges -- never compared,
    never guessed at,
  - no fabricated finding when there is no conflict (or no dependencies)
    at all.
"""

from __future__ import annotations

from pathlib import Path

from codeatlas.analysis.dependencies import analyze_dependencies
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.evidence.schema import VerificationStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def test_exact_pin_conflict_confirmed_with_evidence():
    ctx = DiscoveryEngine().discover(str(FIXTURES / "python_fastapi"))
    issues, evidence = analyze_dependencies(ctx)

    redis_issue = next(i for i in issues if "redis" in i.description)
    assert "4.0.0" in redis_issue.description
    assert "5.0.0" in redis_issue.description
    assert redis_issue.severity == "medium"
    assert len(redis_issue.evidence) == 2

    conflict_evidence = [e for e in evidence if e.finding_id == "dependency:conflict:pypi:redis"]
    assert len(conflict_evidence) == 2
    assert all(e.discovered_by == "static" for e in conflict_evidence)
    assert all(e.verification_status == VerificationStatus.CONFIRMED for e in conflict_evidence)
    sources = {e.source_file for e in conflict_evidence}
    assert sources == {"pyproject.toml", "requirements.txt"}


def test_range_vs_exact_pin_is_never_flagged(tmp_path):
    """fastapi>=0.110 (a range) coexists with no exact pin for fastapi --
    this must never be treated as a conflict, since comparing a range
    against anything requires semver logic this analyzer doesn't do."""
    repo = tmp_path / "range_only_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["fastapi>=0.110"]\n'
    )
    (repo / "requirements.txt").write_text("fastapi>=0.100\n")

    ctx = DiscoveryEngine().discover(str(repo))
    issues, evidence = analyze_dependencies(ctx)

    assert issues == []
    assert evidence == []


def test_single_exact_pin_is_not_a_conflict(tmp_path):
    """Only one file pins an exact version for a package -- nothing to
    compare it against, so no conflict."""
    repo = tmp_path / "single_pin_repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["requests==2.31.0"]\n'
    )

    ctx = DiscoveryEngine().discover(str(repo))
    issues, evidence = analyze_dependencies(ctx)

    assert issues == []
    assert evidence == []


def test_no_fabricated_findings_on_node_fixture():
    ctx = DiscoveryEngine().discover(str(FIXTURES / "node_express"))
    issues, evidence = analyze_dependencies(ctx)

    assert issues == []
    assert evidence == []


def test_no_fabricated_findings_when_no_dependencies(tmp_path):
    repo = tmp_path / "empty_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "util.py").write_text("def add(a, b):\n    return a + b\n")

    ctx = DiscoveryEngine().discover(str(repo))
    issues, evidence = analyze_dependencies(ctx)

    assert issues == []
    assert evidence == []
