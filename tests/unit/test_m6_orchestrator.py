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


def test_authentication_and_authorization_evidence_is_propagated(tmp_path):
    """Regression test: analyze_authentication() has always returned real
    Evidence (finding_id 'authentication:*' / 'authorization:*'), but the
    orchestrator never backfilled it onto AuthenticationModel.evidence /
    AuthorizationModel.evidence the way every other analyzer's result is
    backfilled (see e.g. the database table / component backfills a few
    lines above this call in pipeline.py). Both fields stayed permanently
    empty even though the underlying evidence existed and was persisted.
    """
    orchestrator = Orchestrator(data_dir=tmp_path / "data")
    run = orchestrator.run(str(FIXTURES / "python_fastapi"))

    authn = run.knowledge.authentication
    authz = run.knowledge.authorization

    assert authn.mechanism is not None  # JWT is detected in this fixture
    assert authn.evidence, "AuthenticationModel.evidence must not be empty when a mechanism was found"
    assert all(ref.evidence_id for ref in authn.evidence)

    assert authz.model is not None  # a role-gated check is detected in this fixture
    assert authz.evidence, "AuthorizationModel.evidence must not be empty when an authorization model was found"

    # Backfilled refs must point at evidence that was actually persisted,
    # not fabricated placeholders.
    from codeatlas.evidence.store import EvidenceStore

    store = EvidenceStore(tmp_path / "data", run.knowledge.project_id)
    persisted_ids = {e.evidence_id for e in store.load_all()}
    for ref in authn.evidence + authz.evidence:
        assert ref.evidence_id in persisted_ids
