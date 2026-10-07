"""Dependency intelligence analyzer — static detection of version
conflicts across declared dependencies (product spec §17, "Dependency
Intelligence").

V1 scope, honestly stated:

- This pass detects exactly one thing: the SAME package name pinned to
  DIFFERENT EXACT versions across multiple declarations within the same
  ecosystem (e.g. ``requirements.txt`` pins ``requests==2.25.0`` while
  ``pyproject.toml`` pins ``requests==2.31.0``). Two different exact pins
  for the same package is an unambiguous, directly observable conflict —
  CONFIRMED, no interpretation needed.
- Version **ranges** (``>=2.25``, ``^1.2.0``, ``~1.0``, ...) are never
  compared against each other for compatibility. Determining whether two
  ranges actually overlap requires real semver range-intersection logic
  with ecosystem-specific operator semantics (npm's ``^``/``~`` differ
  from Python's ``>=``/``~=``), which this pass does not implement — a
  range mismatch is not flagged at all, rather than guessed at. This is
  the honest reason exact-pin-vs-exact-pin is the only comparison made.
- **Potentially outdated packages are NOT detected in this pass.** That
  requires live network access to a package registry (PyPI/npm) to know
  the current latest version, which is out of scope for a static
  analyzer and not part of this architecture (ARCHITECTURE.md §2/§8).
  An explicit, tracked gap — not silently skipped.
- **Internal/workspace dependency classification** (e.g. npm ``file:``/
  ``workspace:`` references) and **infrastructure-dependency
  identification** are also not implemented here: the former has no
  natural home in the current ``Dependency`` schema without a change
  (deferred rather than folded into this slice); the latter already
  substantially overlaps ``codeatlas.analysis.database`` and
  ``codeatlas.analysis.integrations``, which already identify database/
  queue/cloud-SDK dependencies from the same raw dependency list.
- Findings are represented as ``KnownIssue`` entries — the schema's
  existing slot for "a real, concrete problem found," not a new
  ``Finding`` kind — each backed by real ``Evidence`` pointing at every
  conflicting declaration. ``KnownIssue`` has no ``VerificationStatus``
  field of its own (its existence is itself the claim), so this module
  self-enforces the "no finding without evidence" rule directly rather
  than going through ``orchestrator.pipeline._link_evidence`` (which
  requires a ``.status`` attribute `KnownIssue` doesn't have).

Nothing here calls an LLM, and nothing here makes network requests. No
conflicting exact pin → no finding, never a guessed compatibility
judgment.
"""

from __future__ import annotations

import re

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, VerificationStatus, evidence_to_ref
from codeatlas.knowledge.schema import Dependency, KnownIssue

_NPM_EXACT_VERSION = re.compile(r"^\d+(\.\d+){0,2}([-+].*)?$")


def _exact_pin(ecosystem: str, version: str | None) -> str | None:
    """Return the normalized exact version string if ``version`` is an
    unambiguous exact pin for this ecosystem, else None (a range,
    missing version, or an unrecognized/special reference)."""
    if not version:
        return None
    v = version.strip()

    if ecosystem == "pypi":
        if v.startswith("==") and not any(ch in v[2:] for ch in ",|"):
            return v[2:].strip()
        return None

    if ecosystem == "npm":
        if _NPM_EXACT_VERSION.match(v):
            return v
        return None

    return None


def analyze_dependencies(ctx: DiscoveryContext) -> tuple[list[KnownIssue], list[Evidence]]:
    all_evidence: list[Evidence] = []
    issues: list[KnownIssue] = []

    groups: dict[tuple[str, str], list[Dependency]] = {}
    for dep in ctx.result.dependencies:
        groups.setdefault((dep.ecosystem, dep.name.lower()), []).append(dep)

    for (ecosystem, name_lower), deps in groups.items():
        pinned = [(dep, pin) for dep in deps if (pin := _exact_pin(ecosystem, dep.version)) is not None]
        distinct_versions = sorted({pin for _, pin in pinned})
        if len(distinct_versions) < 2:
            continue

        conflict_evidence: list[Evidence] = []
        for dep, pin in pinned:
            excerpt = f"{dep.name}=={pin}" if ecosystem == "pypi" else f'"{dep.name}": "{pin}"'
            conflict_evidence.append(
                Evidence(
                    finding_id=f"dependency:conflict:{ecosystem}:{name_lower}",
                    source_file=dep.source_file,
                    excerpt=excerpt,
                    reasoning=f"'{dep.name}' is pinned to exact version {pin} in {dep.source_file}.",
                    confidence=0.9,
                    verification_status=VerificationStatus.CONFIRMED,
                    discovered_by="static",
                )
            )

        # Self-enforced: never emit a KnownIssue without real evidence behind it.
        assert conflict_evidence, "a detected conflict must always have >=2 pinned declarations as evidence"
        all_evidence.extend(conflict_evidence)

        display_name = deps[0].name
        issues.append(
            KnownIssue(
                description=(
                    f"'{display_name}' is pinned to conflicting exact versions across the "
                    f"repository: {', '.join(distinct_versions)}. This can cause install "
                    "failures or inconsistent behavior depending on which manifest resolves first."
                ),
                severity="medium",
                source_file=pinned[0][0].source_file,
                evidence=[evidence_to_ref(e) for e in conflict_evidence],
            )
        )

    return issues, all_evidence
