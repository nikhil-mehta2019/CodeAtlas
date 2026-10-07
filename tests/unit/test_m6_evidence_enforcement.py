"""M6/M7 regression tests: the CONFIRMED-requires-static-evidence
invariant (ARCHITECTURE.md §4) is now an active guard in the pipeline,
not just a dormant, independently-unit-tested function.

``codeatlas.evidence.schema.assert_status_supported`` existed since M1
and was exercised in isolation by ``test_m1_foundations.py``, but nothing
in ``orchestrator/pipeline.py`` ever called it -- a future analyzer bug
that attached ``status=CONFIRMED`` to a knowledge object with no (or only
LLM-derived) evidence would have shipped silently. ``pipeline.py``'s
``_link_evidence`` helper now calls it at every backfill site.

Known, deliberate scope limit (see pipeline.py's module docstring):
``TechnologyItem`` entries are not covered by this enforcement yet --
several ecosystem/infra detectors don't create a matching Evidence
record for every item they produce, and fixing that is a discovery-
engine-wide change, not pipeline wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codeatlas.evidence.schema import Evidence, EvidenceSetError, VerificationStatus
from codeatlas.orchestrator.pipeline import Orchestrator, _link_evidence

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


class _FakeFinding:
    """Minimal stand-in exposing .status/.evidence, mirroring Finding."""

    def __init__(self, status: VerificationStatus):
        self.status = status
        self.evidence = []


def _static_evidence(status: VerificationStatus = VerificationStatus.CONFIRMED) -> Evidence:
    return Evidence(
        finding_id="test:x",
        source_file="x.py",
        reasoning="r",
        confidence=0.9,
        verification_status=status,
        discovered_by="static",
    )


def _llm_evidence() -> Evidence:
    return Evidence(
        finding_id="test:x",
        source_file="x.py",
        reasoning="r",
        confidence=0.9,
        verification_status=VerificationStatus.CONFIRMED,
        discovered_by="llm:claude",
    )


def test_link_evidence_raises_on_confirmed_with_no_evidence():
    target = _FakeFinding(VerificationStatus.CONFIRMED)
    with pytest.raises(EvidenceSetError):
        _link_evidence(target, [])


def test_link_evidence_raises_on_confirmed_with_only_llm_evidence():
    target = _FakeFinding(VerificationStatus.CONFIRMED)
    with pytest.raises(EvidenceSetError):
        _link_evidence(target, [_llm_evidence()])


def test_link_evidence_raises_on_inferred_with_no_evidence():
    target = _FakeFinding(VerificationStatus.INFERRED)
    with pytest.raises(EvidenceSetError):
        _link_evidence(target, [])


def test_link_evidence_allows_unknown_with_no_evidence():
    target = _FakeFinding(VerificationStatus.UNKNOWN)
    _link_evidence(target, [])  # must not raise
    assert target.evidence == []


def test_link_evidence_succeeds_and_backfills_on_valid_input():
    target = _FakeFinding(VerificationStatus.CONFIRMED)
    ev = _static_evidence()
    _link_evidence(target, [ev])
    assert len(target.evidence) == 1
    assert target.evidence[0].evidence_id == ev.evidence_id


@pytest.mark.parametrize("fixture_name", ["python_fastapi", "node_express"])
def test_full_pipeline_never_violates_the_invariant(tmp_path, fixture_name):
    """End-to-end sweep: every status-bearing object the pipeline covers
    (everything except the documented TechnologyItem gap) must have
    non-empty evidence whenever its status is not UNKNOWN, after a real
    run against each fixture. If pipeline.py ever regresses a backfill,
    this either raises during the run itself (the guard firing) or this
    sweep catches it after the fact.
    """
    orchestrator = Orchestrator(data_dir=tmp_path / "data")
    run = orchestrator.run(str(FIXTURES / fixture_name))
    k = run.knowledge

    findings = [
        k.overview.name,
        k.architecture.style,
        k.database_model.engine,
        k.database_model.orm,
        k.authentication.mechanism,
        k.authorization.model,
        k.deployment.containerized,
        k.deployment.ci_cd,
    ]
    for f in findings:
        if f is not None and f.status != VerificationStatus.UNKNOWN:
            assert f.evidence, f"Finding with value={f.value!r} status={f.status} has no evidence"

    for comp in k.components:
        if comp.description is not None and comp.description.status != VerificationStatus.UNKNOWN:
            assert comp.description.evidence

    for obj in (*k.api_catalog, *k.business_rules, *k.database_model.tables, *k.external_integrations):
        if obj.status != VerificationStatus.UNKNOWN:
            assert obj.evidence, f"{type(obj).__name__} with status={obj.status} has no evidence"
