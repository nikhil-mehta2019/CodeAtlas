"""API catalog analyzer — static route extraction (ARCHITECTURE.md §10).

V1 scope, honestly stated: this extracts method+path+source location from
route declarations using regex heuristics for Express-style JS/TS routers
and FastAPI/Flask-style Python decorators. It does NOT parse OpenAPI specs
yet, and it does NOT fill ``purpose``/request/response shape unless an LLM
provider is available (those fields stay ``None``, which the gap detector
will surface as UNKNOWN rather than guessed).
"""

from __future__ import annotations

import re

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, VerificationStatus
from codeatlas.knowledge.schema import ApiEndpoint

_PY_ROUTE = re.compile(
    r"@(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]"
)
_JS_ROUTE = re.compile(
    r"(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]"
)


def analyze_api_catalog(ctx: DiscoveryContext, walker) -> tuple[list[ApiEndpoint], list[Evidence]]:
    endpoints: list[ApiEndpoint] = []
    evidence: list[Evidence] = []

    candidate_files = [
        f for f in ctx.tree.readable_files
        if f.relative_path.endswith((".py", ".js", ".ts"))
        and (
            f.relative_path in ctx.priority_plan.controllers_routes
            or f.relative_path in ctx.priority_plan.entry_points
        )
    ]

    for f in candidate_files:
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        pattern = _PY_ROUTE if f.relative_path.endswith(".py") else _JS_ROUTE
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = pattern.search(line)
            if not m:
                continue
            method, path = m.group(1).upper(), m.group(2)
            finding_id = f"api:{method}:{path}:{f.relative_path}:{lineno}"
            ev = Evidence(
                finding_id=finding_id,
                source_file=f.relative_path,
                location={"file": f.relative_path, "line_start": lineno, "line_end": lineno},
                excerpt=line.strip()[:160],
                reasoning=f"Route decorator/call for {method} {path} found at line {lineno}.",
                confidence=0.9,
                verification_status=VerificationStatus.CONFIRMED,
                discovered_by="static",
            )
            evidence.append(ev)
            endpoints.append(
                ApiEndpoint(
                    method=method,
                    path=path,
                    source_file=f.relative_path,
                    status=VerificationStatus.CONFIRMED,
                    confidence=0.9,
                    evidence=[],  # filled by caller after evidence is persisted and refs known
                )
            )

    return endpoints, evidence
