"""Architecture & component analyzer — ARCHITECTURE.md §7 of the spec.

Static-heuristic baseline that works with zero LLM calls (architecture
*style* is inferred from discovered directory roles, never fabricated).
When a ``ModelProvider`` is available and willing, its output is treated
as an additional, separately-labeled INFERRED opinion — it never replaces
or masks the static evidence.
"""

from __future__ import annotations

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, VerificationStatus
from codeatlas.knowledge.schema import Architecture, Component, Finding

_ROLE_PATTERNS = {
    "controllers_routes": "controller/route layer",
    "services_models": "service/domain layer",
    "migrations": "database migration layer",
    "auth": "authentication/authorization layer",
}


def analyze_architecture(ctx: DiscoveryContext) -> tuple[Architecture, list[Component], list[Evidence]]:
    evidence: list[Evidence] = []
    components: list[Component] = []
    layers: list[str] = []

    plan = ctx.priority_plan
    bucket_map = {
        "controllers_routes": plan.controllers_routes,
        "services_models": plan.services_models,
        "migrations": plan.migrations,
        "auth": plan.auth,
    }

    for bucket_name, paths in bucket_map.items():
        if not paths:
            continue
        layer_label = _ROLE_PATTERNS[bucket_name]
        layers.append(layer_label)
        directory = _common_directory(paths)
        finding_id = f"architecture:layer:{bucket_name}"
        ev = Evidence(
            finding_id=finding_id,
            source_file=directory or paths[0],
            excerpt=f"{len(paths)} file(s) matched the {bucket_name} naming pattern",
            reasoning=(
                f"{len(paths)} files under '{directory}' match naming conventions for a "
                f"{layer_label} (e.g. directory/file names containing "
                f"'{bucket_name.replace('_', '/')}')."
            ),
            confidence=0.75,
            verification_status=VerificationStatus.INFERRED,
            discovered_by="static",
        )
        evidence.append(ev)
        components.append(
            Component(
                name=directory or bucket_name,
                kind=bucket_name,
                path=directory or "",
                description=Finding(
                    value=f"Inferred {layer_label} based on {len(paths)} matching file(s).",
                    confidence=0.75,
                    status=VerificationStatus.INFERRED,
                    reasoning=ev.reasoning,
                ),
            )
        )

    style: Finding[str] | None = None
    if len(layers) >= 2:
        style = Finding(
            value="Layered architecture",
            confidence=0.7,
            status=VerificationStatus.INFERRED,
            reasoning=(
                f"Repository structure separates {', '.join(layers)}, which is "
                "consistent with a layered architecture. Not confirmed by runtime "
                "inspection — directory naming conventions can be misleading."
            ),
        )
    elif layers:
        style = Finding(
            value="Unclear / single-layer structure",
            confidence=0.4,
            status=VerificationStatus.UNVERIFIED,
            reasoning=f"Only one structural layer ({layers[0]}) was detected; insufficient signal to classify architecture style.",
        )

    mermaid = _build_mermaid(layers, plan.entry_points)

    architecture = Architecture(
        style=style,
        layers=layers,
        mermaid_diagram=mermaid,
        entry_points=plan.entry_points,
    )
    return architecture, components, evidence


def _common_directory(paths: list[str]) -> str | None:
    dirs = {p.rsplit("/", 1)[0] if "/" in p else "." for p in paths}
    if len(dirs) == 1:
        return next(iter(dirs))
    return sorted(dirs, key=len)[0] if dirs else None


def _build_mermaid(layers: list[str], entry_points: list[str]) -> str | None:
    if not layers and not entry_points:
        return None
    lines = ["graph TD"]
    prev = "Client"
    if entry_points:
        lines.append(f'  {prev}["Client"] --> EP["Entry Point(s)"]')
        prev = "EP"
    for i, layer in enumerate(layers):
        node_id = f"L{i}"
        safe_label = layer.replace('"', "'")
        lines.append(f'  {prev} --> {node_id}["{safe_label}"]')
        prev = node_id
    return "\n".join(lines)
