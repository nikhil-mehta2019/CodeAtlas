"""M7 sanity tests: coding standards analyzer.

Covers the three required status behaviors per .claude/skills/build-analyzer:
  - a CONFIRMED finding backed by static evidence (naming conventions,
    dependency-injection usage, confirmed test-file naming),
  - an ambiguous/weaker case that comes back INFERRED, not CONFIRMED
    (the Repository-pattern naming signal, and a genuinely mixed naming
    sample),
  - no fabricated finding when there is no signal (or not enough
    samples) at all.
"""

from __future__ import annotations

from pathlib import Path

from codeatlas.analysis.coding_standards import analyze_coding_standards
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.evidence.schema import VerificationStatus
from codeatlas.repository.walker import RepositoryWalker

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def _discover(name: str):
    ctx = DiscoveryEngine().discover(str(FIXTURES / name))
    walker = RepositoryWalker(FIXTURES / name)
    return ctx, walker


def test_naming_conventions_confirmed_with_evidence():
    ctx, walker = _discover("python_fastapi")
    standards, evidence = analyze_coding_standards(ctx, walker)

    assert any("snake_case" in o for o in standards.observed)
    assert any("PascalCase" in o for o in standards.observed)
    assert standards.recommended_improvements == []  # never a style opinion in this pass

    naming_evidence = [e for e in evidence if e.finding_id.startswith("coding_standards:naming:")]
    assert naming_evidence
    assert all(e.discovered_by == "static" for e in naming_evidence)
    assert any(e.verification_status == VerificationStatus.CONFIRMED for e in naming_evidence)


def test_dependency_injection_confirmed_with_evidence():
    ctx, walker = _discover("python_fastapi")
    standards, evidence = analyze_coding_standards(ctx, walker)

    assert any("Depends" in p for p in standards.design_patterns_observed)
    di_evidence = next(e for e in evidence if e.finding_id == "coding_standards:pattern:dependency_injection")
    assert di_evidence.verification_status == VerificationStatus.CONFIRMED
    assert di_evidence.source_file == "app/main.py"


def test_repository_pattern_is_inferred_not_confirmed():
    ctx, walker = _discover("python_fastapi")
    standards, evidence = analyze_coding_standards(ctx, walker)

    assert any("Repository" in p for p in standards.design_patterns_observed)
    repo_evidence = next(e for e in evidence if e.finding_id == "coding_standards:pattern:repository")
    assert repo_evidence.verification_status == VerificationStatus.INFERRED  # naming != confirmed behavior
    assert repo_evidence.confidence < 0.85


def test_test_file_naming_confirmed_with_sufficient_sample(tmp_path):
    repo = tmp_path / "well_tested_repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("def run():\n    pass\n")
    for name in ("alpha", "beta", "gamma", "delta", "epsilon"):
        (repo / "tests" / f"test_{name}.py").write_text("def test_it():\n    assert True\n")

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    standards, evidence = analyze_coding_standards(ctx, walker)

    assert any("test_*.py" in o for o in standards.observed)
    test_evidence = next(e for e in evidence if e.finding_id == "coding_standards:naming:test_file")
    assert test_evidence.verification_status == VerificationStatus.CONFIRMED


def test_mixed_naming_sample_produces_no_claim(tmp_path):
    repo = tmp_path / "mixed_naming_repo"
    (repo / "src").mkdir(parents=True)
    # 3 snake_case, 3 camelCase -> no majority -> no honest claim to make.
    (repo / "src" / "a.py").write_text(
        "def snake_one():\n    pass\n"
        "def snake_two():\n    pass\n"
        "def snake_three():\n    pass\n"
        "def camelOne():\n    pass\n"
        "def camelTwo():\n    pass\n"
        "def camelThree():\n    pass\n"
    )

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    standards, evidence = analyze_coding_standards(ctx, walker)

    assert standards.observed == []
    assert standards.design_patterns_observed == []
    assert evidence == []


def test_no_fabricated_findings_on_node_fixture_python_only_scope():
    ctx, walker = _discover("node_express")
    standards, evidence = analyze_coding_standards(ctx, walker)

    assert standards.observed == []
    assert standards.design_patterns_observed == []
    assert evidence == []


def test_no_fabricated_findings_when_no_signal(tmp_path):
    repo = tmp_path / "empty_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "util.py").write_text("x = 1\n")

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    standards, evidence = analyze_coding_standards(ctx, walker)

    assert standards.observed == []
    assert standards.design_patterns_observed == []
    assert evidence == []
