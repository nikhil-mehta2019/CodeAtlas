"""Documentation Engine — renders the 19-section report from structured
knowledge only (spec §19: "generated from structured data, not
independently hallucinated by a second AI process"). No LLM call happens
in this module.
"""

from __future__ import annotations

from codeatlas.knowledge.schema import Finding, ProjectKnowledge

_STATUS_EMOJI = {
    "CONFIRMED": "✅",
    "INFERRED": "🟡",
    "UNVERIFIED": "⚠️",
    "CONTRADICTED": "❌",
    "UNKNOWN": "❔",
}


def _fmt_finding(label: str, finding: Finding | None, indent: str = "") -> list[str]:
    if finding is None:
        return [f"{indent}- **{label}:** ❔ UNKNOWN"]
    badge = _STATUS_EMOJI.get(finding.status.value, "")
    lines = [
        f"{indent}- **{label}:** {finding.value} {badge} *{finding.status.value}* "
        f"(confidence: {finding.confidence:.0%})"
    ]
    if finding.reasoning:
        lines.append(f"{indent}  - Reasoning: {finding.reasoning}")
    if finding.evidence:
        ev_list = ", ".join(f"`{e.source_file}`" for e in finding.evidence[:5])
        lines.append(f"{indent}  - Evidence: {ev_list}")
    return lines


def generate_markdown(knowledge: ProjectKnowledge) -> str:
    sections = [
        _section_overview(knowledge),
        _section_tech_stack(knowledge),
        _section_repo_structure(knowledge),
        _section_architecture(knowledge),
        _section_components(knowledge),
        _section_flows(knowledge),
        _section_business_rules(knowledge),
        _section_api(knowledge),
        _section_database(knowledge),
        _section_auth(knowledge),
        _section_integrations(knowledge),
        _section_configuration(knowledge),
        _section_coding_standards(knowledge),
        _section_deployment(knowledge),
        _section_tests(knowledge),
        _section_dependencies(knowledge),
        _section_known_issues(knowledge),
        _section_unknowns(knowledge),
        _section_evidence_index(knowledge),
    ]
    header = (
        f"# CodeAtlas Project Report — {knowledge.name}\n\n"
        f"- **Project ID:** `{knowledge.project_id}`\n"
        f"- **Root path:** `{knowledge.root_path}`\n"
        f"- **Analyzed at:** {knowledge.analyzed_at.isoformat()}\n"
        f"- **Schema version:** {knowledge.schema_version}\n\n"
        "> Legend: ✅ CONFIRMED · 🟡 INFERRED · ⚠️ UNVERIFIED · ❌ CONTRADICTED · ❔ UNKNOWN\n\n"
    )
    return header + "\n\n".join(sections) + "\n"


def _section_overview(k: ProjectKnowledge) -> str:
    lines = ["## 1. Project Overview"]
    lines += _fmt_finding("Name", k.overview.name)
    lines += _fmt_finding("Purpose", k.overview.purpose)
    lines += _fmt_finding("Users", k.overview.users)
    lines += _fmt_finding("Summary", k.overview.summary)
    return "\n".join(lines)


def _section_tech_stack(k: ProjectKnowledge) -> str:
    lines = ["## 2. Technology Stack"]
    if not k.technology_stack.items:
        lines.append("❔ No technology items recorded.")
    for item in k.technology_stack.items:
        version = f" `{item.version}`" if item.version else ""
        badge = _STATUS_EMOJI.get(item.status.value, "")
        lines.append(f"- **[{item.category}]** {item.name}{version} {badge} *{item.status.value}*")
    return "\n".join(lines)


def _section_repo_structure(k: ProjectKnowledge) -> str:
    lines = ["## 3. Repository Structure"]
    rs = k.repository_structure
    if rs is None:
        lines.append("❔ Not analyzed.")
        return "\n".join(lines)
    lines.append(f"- Total files discovered: {rs.total_files}")
    lines.append(f"- Files analyzed (readable, not excluded): {rs.total_files_analyzed}")
    if rs.excluded_paths:
        lines.append(f"- Excluded directories: {', '.join(rs.excluded_paths[:15])}" + (" …" if len(rs.excluded_paths) > 15 else ""))
    lines.append("")
    lines.append("| Directory | Files | Languages |")
    lines.append("|---|---|---|")
    for d in rs.directories[:40]:
        langs = ", ".join(f"{ext}:{count}" for ext, count in sorted(d.language_breakdown.items()))
        lines.append(f"| `{d.path}` | {d.file_count} | {langs} |")
    if len(rs.directories) > 40:
        lines.append(f"| … {len(rs.directories) - 40} more directories not shown … | | |")
    return "\n".join(lines)


def _section_architecture(k: ProjectKnowledge) -> str:
    lines = ["## 4. Architecture"]
    lines += _fmt_finding("Style", k.architecture.style)
    if k.architecture.layers:
        lines.append(f"- **Layers detected:** {', '.join(k.architecture.layers)}")
    if k.architecture.entry_points:
        lines.append(f"- **Entry points:** {', '.join(f'`{p}`' for p in k.architecture.entry_points)}")
    if k.architecture.mermaid_diagram:
        lines.append("\n```mermaid")
        lines.append(k.architecture.mermaid_diagram)
        lines.append("```")
    return "\n".join(lines)


def _section_components(k: ProjectKnowledge) -> str:
    lines = ["## 5. Component Documentation"]
    if not k.components:
        lines.append("❔ No components identified in this pass.")
    for c in k.components:
        lines.append(f"### {c.name} (`{c.kind}`)")
        lines.append(f"- Path: `{c.path}`")
        if c.depends_on:
            lines.append(f"- Depends on: {', '.join(c.depends_on)}")
        lines += _fmt_finding("Description", c.description, indent="")
    return "\n".join(lines)


def _section_flows(k: ProjectKnowledge) -> str:
    lines = ["## 6. Application Flows"]
    if not k.application_flows:
        lines.append("❔ No application flows reconstructed in this pass.")
    for flow in k.application_flows:
        badge = _STATUS_EMOJI.get(flow.status.value, "")
        lines.append(f"### {flow.name} {badge} *{flow.status.value}* (confidence: {flow.confidence:.0%})")
        lines.append(flow.description)
        for step in flow.steps:
            lines.append(f"  1. {step}")
    return "\n".join(lines)


def _section_business_rules(k: ProjectKnowledge) -> str:
    lines = ["## 7. Business Rules"]
    if not k.business_rules:
        lines.append("❔ No business rules extracted in this pass.")
    for r in k.business_rules:
        badge = _STATUS_EMOJI.get(r.status.value, "")
        kind = "Explicit rule" if r.explicit else "Inferred rule"
        lines.append(f"- [{r.kind}] **{kind}:** {r.rule} {badge} *{r.status.value}* (confidence: {r.confidence:.0%})")
    return "\n".join(lines)


def _section_api(k: ProjectKnowledge) -> str:
    lines = ["## 8. API Documentation"]
    if not k.api_catalog:
        lines.append("❔ No API endpoints detected in this pass.")
    for ep in k.api_catalog:
        badge = _STATUS_EMOJI.get(ep.status.value, "")
        lines.append(f"### `{ep.method} {ep.path}` {badge} *{ep.status.value}*")
        lines.append(f"- Source: `{ep.source_file}`")
        lines += _fmt_finding("Purpose", ep.purpose)
        lines.append(f"- Authentication: {ep.authentication or '❔ UNKNOWN'}")
        lines.append(f"- Authorization: {ep.authorization or '❔ UNKNOWN'}")
    return "\n".join(lines)


def _section_database(k: ProjectKnowledge) -> str:
    lines = ["## 9. Database Documentation"]
    lines += _fmt_finding("Engine", k.database_model.engine)
    lines += _fmt_finding("ORM", k.database_model.orm)
    if not k.database_model.tables:
        lines.append("❔ No tables/collections identified in this pass.")
    for t in k.database_model.tables:
        lines.append(f"### Table/Model: `{t.name}` *{t.status.value}*")
        for col in t.columns:
            flags = []
            if col.primary_key:
                flags.append("PK")
            if col.foreign_key_to:
                flags.append(f"FK→{col.foreign_key_to}")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  - `{col.name}` {col.type or ''}{flag_str}")
    return "\n".join(lines)


def _section_auth(k: ProjectKnowledge) -> str:
    lines = ["## 10. Authentication & Authorization"]
    lines += _fmt_finding("Authentication mechanism", k.authentication.mechanism)
    if k.authentication.token_handling:
        lines.append(f"- Token handling: {k.authentication.token_handling}")
    if k.authentication.password_handling:
        lines.append(f"- Password handling: {k.authentication.password_handling}")
    lines += _fmt_finding("Authorization model", k.authorization.model)
    if k.authorization.roles:
        lines.append(f"- Roles observed: {', '.join(k.authorization.roles)}")
    if k.authorization.protected_endpoints:
        lines.append(f"- Protected endpoints: {', '.join(k.authorization.protected_endpoints)}")
    return "\n".join(lines)


def _section_integrations(k: ProjectKnowledge) -> str:
    lines = ["## 11. External Integrations"]
    if not k.external_integrations:
        lines.append("❔ No external integrations detected in this pass.")
    for i in k.external_integrations:
        badge = _STATUS_EMOJI.get(i.status.value, "")
        lines.append(f"- **{i.provider}** ({i.purpose}) {badge} *{i.status.value}* (confidence: {i.confidence:.0%})")
    return "\n".join(lines)


def _section_configuration(k: ProjectKnowledge) -> str:
    lines = ["## 12. Configuration"]
    lines.append("*Configuration key names only — values are never captured or displayed.*")
    if not k.configuration:
        lines.append("❔ No configuration items identified in this pass.")
    for c in k.configuration:
        req = "required" if c.required else "optional" if c.required is False else "unknown"
        lines.append(f"- `{c.key}` ({req}) — {c.source_file}")
    return "\n".join(lines)


def _section_coding_standards(k: ProjectKnowledge) -> str:
    lines = ["## 13. Coding Standards"]
    lines.append("### Observed")
    if not k.coding_standards.observed:
        lines.append("❔ Not analyzed in this pass.")
    for o in k.coding_standards.observed:
        lines.append(f"- {o}")
    lines.append("### Recommended Improvements (separate from observed standards)")
    for r in k.coding_standards.recommended_improvements:
        lines.append(f"- {r}")
    return "\n".join(lines)


def _section_deployment(k: ProjectKnowledge) -> str:
    lines = ["## 14. Deployment"]
    lines += _fmt_finding("Build process", k.deployment.build_process)
    lines += _fmt_finding("Containerized", k.deployment.containerized)
    lines += _fmt_finding("CI/CD", k.deployment.ci_cd)
    lines += _fmt_finding("Hosting", k.deployment.hosting)
    if k.deployment.ports:
        lines.append(f"- Ports: {', '.join(str(p) for p in k.deployment.ports)}")
    return "\n".join(lines)


def _section_tests(k: ProjectKnowledge) -> str:
    lines = ["## 15. Existing Tests"]
    t = k.existing_tests
    lines.append(f"- Frameworks detected: {', '.join(t.frameworks) if t.frameworks else '❔ none detected'}")
    lines.append(f"- Unit test files: {len(t.unit_test_files)}")
    lines.append(f"- Integration test files: {len(t.integration_test_files)}")
    lines.append(f"- E2E test files: {len(t.e2e_test_files)}")
    if t.areas_with_no_detected_tests:
        lines.append(f"- Areas with no detected tests: {', '.join(t.areas_with_no_detected_tests)}")
    lines.append(f"- Note: {t.note}")
    return "\n".join(lines)


def _section_dependencies(k: ProjectKnowledge) -> str:
    lines = ["## 16. Dependencies"]
    if not k.dependencies:
        lines.append("❔ No dependencies parsed in this pass.")
    by_ecosystem: dict[str, list] = {}
    for d in k.dependencies:
        by_ecosystem.setdefault(d.ecosystem, []).append(d)
    for eco, deps in by_ecosystem.items():
        lines.append(f"### {eco} ({len(deps)})")
        for d in deps[:50]:
            lines.append(f"- {d.name} {d.version or ''} ({d.kind})")
        if len(deps) > 50:
            lines.append(f"- … {len(deps) - 50} more not shown …")
    return "\n".join(lines)


def _section_known_issues(k: ProjectKnowledge) -> str:
    lines = ["## 17. Known Issues"]
    if not k.known_issues:
        lines.append("None recorded in this pass.")
    for issue in k.known_issues:
        lines.append(f"- [{issue.severity}] {issue.description}")
    return "\n".join(lines)


def _section_unknowns(k: ProjectKnowledge) -> str:
    lines = ["## 18. Unknowns and Verification Gaps"]
    lines.append(
        "This is a first-class section, not an afterthought: everything the product "
        "specification asks this system to determine, but which this pass could not "
        "confirm, is listed here rather than silently omitted."
    )
    if not k.unknowns:
        lines.append("No gaps recorded — review Known Issues and per-section statuses regardless.")
    for u in k.unknowns:
        lines.append(f"- **[{u.area}] {u.topic}:** {u.reason}")
    return "\n".join(lines)


def _section_evidence_index(k: ProjectKnowledge) -> str:
    lines = ["## 19. Evidence Index"]
    if not k.evidence_index:
        lines.append("No top-level evidence index entries recorded; see per-section evidence above.")
    for ref in k.evidence_index:
        lines.append(f"- `{ref.evidence_id}` — `{ref.source_file}` — {ref.summary}")
    return "\n".join(lines)
