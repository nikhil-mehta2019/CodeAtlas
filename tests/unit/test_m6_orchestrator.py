"""M6 end-to-end test: full pipeline against a real fixture repo."""

from __future__ import annotations

from pathlib import Path

from codeatlas.orchestrator.pipeline import Orchestrator

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def test_full_pipeline_on_python_fastapi_fixture(tmp_path):
    orchestrator = Orchestrator(data_dir=tmp_path / "data")
    run = orchestrator.run(str(FIXTURES / "python_fastapi"))

    assert run.knowledge.project_id
    assert any(ep.path == "/health" for ep in run.knowledge.api_catalog)
    assert run.knowledge.deployment.containerized is not None
    assert run.knowledge.deployment.containerized.value is True
    assert run.knowledge.deployment.ci_cd is not None

    # Evidence actually persisted to disk and re-loadable.
    from codeatlas.evidence.store import EvidenceStore

    store = EvidenceStore(tmp_path / "data", run.knowledge.project_id)
    loaded = store.load_all()
    assert len(loaded) > 0

    # Knowledge actually persisted and re-loadable from SQLite.
    from codeatlas.knowledge.store import KnowledgeStore

    kstore = KnowledgeStore(tmp_path / "data")
    reloaded = kstore.load(run.knowledge.project_id)
    assert reloaded is not None
    assert reloaded.name == run.knowledge.name
    kstore.close()

    # Report mentions the detected API route and flags at least one gap.
    assert "/health" in run.markdown_report
    assert "Unknowns and Verification Gaps" in run.markdown_report
    assert len(run.knowledge.unknowns) > 0
