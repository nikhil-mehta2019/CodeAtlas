"""M1 sanity tests: schemas, evidence invariants, repository walker, secrets, stores."""

from __future__ import annotations

import pytest

from codeatlas.evidence.schema import (
    Evidence,
    EvidenceSetError,
    VerificationStatus,
    assert_status_supported,
)
from codeatlas.evidence.store import EvidenceStore
from codeatlas.knowledge.schema import Finding, Overview, ProjectKnowledge
from codeatlas.knowledge.store import KnowledgeStore
from codeatlas.repository.identity import derive_project_id
from codeatlas.repository.secrets import redact
from codeatlas.repository.walker import PathEscapeError, RepositoryWalker


def _make_evidence(discovered_by: str, status: VerificationStatus) -> Evidence:
    return Evidence(
        finding_id="f1",
        source_file="app/main.py",
        reasoning="found it",
        confidence=0.9,
        verification_status=status,
        discovered_by=discovered_by,
    )


def test_confirmed_requires_static_evidence():
    llm_only = [_make_evidence("llm:claude", VerificationStatus.CONFIRMED)]
    with pytest.raises(EvidenceSetError):
        assert_status_supported(VerificationStatus.CONFIRMED, llm_only)

    with_static = [_make_evidence("static", VerificationStatus.CONFIRMED)]
    assert_status_supported(VerificationStatus.CONFIRMED, with_static)  # no raise


def test_unknown_allows_no_evidence():
    assert_status_supported(VerificationStatus.UNKNOWN, [])


def test_non_unknown_requires_at_least_one_evidence():
    with pytest.raises(EvidenceSetError):
        assert_status_supported(VerificationStatus.INFERRED, [])


def test_secret_redaction():
    text = 'AWS_SECRET_ACCESS_KEY = "AKIAABCDEFGHIJKLMNOP"'
    result = redact(text)
    assert "AKIAABCDEFGHIJKLMNOP" not in result.text
    assert result.had_match


def test_walker_confines_paths(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("print('hi')\n")
    walker = RepositoryWalker(repo)

    with pytest.raises(PathEscapeError):
        walker.resolve_confined("../outside.txt")

    resolved = walker.resolve_confined("src/a.py")
    assert resolved.exists()


def test_walker_walk_and_read(tmp_path):
    repo = tmp_path / "repo2"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "junk.js").write_text("ignored")

    walker = RepositoryWalker(repo)
    tree = walker.walk()
    paths = {f.relative_path for f in tree.readable_files}
    assert "main.py" in paths
    assert not any("node_modules" in p for p in paths)


def test_project_id_derivation_stable():
    pid1 = derive_project_id("/tmp/repo", "abc123")
    pid2 = derive_project_id("/tmp/repo", "abc123")
    assert pid1 == pid2


def test_knowledge_store_roundtrip(tmp_path):
    knowledge = ProjectKnowledge(
        project_id="proj-1",
        name="Demo",
        root_path="/tmp/demo",
        overview=Overview(
            name=Finding(value="Demo", confidence=1.0, status=VerificationStatus.CONFIRMED)
        ),
    )
    store = KnowledgeStore(tmp_path / "data")
    store.save(knowledge)
    loaded = store.load("proj-1")
    assert loaded is not None
    assert loaded.overview.name.value == "Demo"
    store.close()


def test_evidence_store_roundtrip(tmp_path):
    store = EvidenceStore(tmp_path / "data", "proj-1")
    ev = _make_evidence("static", VerificationStatus.CONFIRMED)
    store.save(ev)
    loaded = store.load(ev.evidence_id)
    assert loaded.source_file == "app/main.py"
    assert store.load_for_finding("f1")[0].evidence_id == ev.evidence_id
