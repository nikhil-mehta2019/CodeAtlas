"""Ecosystem detector protocol — see ARCHITECTURE.md §5, §9.

Adding support for a new ecosystem means writing one class that satisfies
this protocol and registering it in ``codeatlas.discovery.engine`` — no
other code needs to change. This is the extensibility seam the spec
asks for explicitly (§1: "do not design the system only around one
language").
"""

from __future__ import annotations

from typing import Protocol

from codeatlas.discovery.result import DiscoveryResult
from codeatlas.repository.walker import RepoTree, RepositoryWalker


class EcosystemDetector(Protocol):
    name: str

    def applies(self, tree: RepoTree) -> bool:
        """Cheap check: does this repo look like it uses this ecosystem?"""
        ...

    def detect(self, tree: RepoTree, walker: RepositoryWalker) -> DiscoveryResult:
        """Full detection pass. Only called when ``applies`` returned True."""
        ...


def make_evidence_kwargs_static(reasoning: str, confidence: float = 0.95) -> dict:
    """Shared defaults for the static evidence every detector produces."""
    from codeatlas.evidence.schema import VerificationStatus

    return {
        "reasoning": reasoning,
        "confidence": confidence,
        "verification_status": VerificationStatus.CONFIRMED,
        "discovered_by": "static",
    }
