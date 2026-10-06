"""Evidence schema — see ARCHITECTURE.md §4.

Every conclusion the system reaches must be traceable to Evidence records.
The rules enforced here (not just documented) are:

  * CONFIRMED status requires at least one Evidence record produced by a
    deterministic/static source (``discovered_by == "static"``). An LLM can
    never single-handedly promote a finding to CONFIRMED.
  * Evidence excerpts are expected to already be secret-redacted by the
    caller (see ``codeatlas.repository.secrets``) before construction —
    this module does not re-scan, it trusts the pipeline contract.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


class VerificationStatus(str, enum.Enum):
    """How sure we are that a finding reflects reality."""

    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


class DiscoverySource(str, enum.Enum):
    """Who produced a piece of evidence."""

    STATIC = "static"
    LLM = "llm"


class SourceLocation(BaseModel):
    """Where in a file the evidence was found, when known."""

    file: str
    line_start: int | None = None
    line_end: int | None = None
    symbol: str | None = None  # function/class/route name, when applicable


class Evidence(BaseModel):
    """A single piece of evidence supporting (or contradicting) a finding."""

    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    finding_id: str
    source_file: str
    location: SourceLocation | None = None
    excerpt: str = Field(default="", max_length=2000)
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    verification_status: VerificationStatus
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discovered_by: str  # "static" or "llm:<model-id>"

    @field_validator("confidence")
    @classmethod
    def _round_confidence(cls, v: float) -> float:
        return round(v, 4)

    @property
    def source(self) -> DiscoverySource:
        return DiscoverySource.STATIC if self.discovered_by == "static" else DiscoverySource.LLM


class EvidenceRef(BaseModel):
    """A lightweight pointer to an Evidence record, embedded in Knowledge."""

    evidence_id: str
    source_file: str
    summary: str


def evidence_to_ref(evidence: Evidence) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence.evidence_id,
        source_file=evidence.source_file,
        summary=evidence.reasoning[:200],
    )


class EvidenceSetError(ValueError):
    """Raised when a set of evidence cannot support the claimed status."""


def assert_status_supported(
    status: VerificationStatus, evidence: list[Evidence]
) -> None:
    """Enforce the CONFIRMED-requires-static-evidence rule.

    Raises EvidenceSetError if the invariant is violated, so a bug upstream
    fails loudly at construction time instead of silently shipping a
    hallucinated "fact".
    """
    if status == VerificationStatus.UNKNOWN:
        return  # UNKNOWN is allowed to have zero evidence by definition.
    if not evidence:
        raise EvidenceSetError(
            f"Status {status} requires at least one Evidence record; got none."
        )
    if status == VerificationStatus.CONFIRMED:
        if not any(e.discovered_by == "static" for e in evidence):
            raise EvidenceSetError(
                "CONFIRMED requires at least one static (deterministic) "
                "Evidence record; all evidence here was LLM-derived."
            )
