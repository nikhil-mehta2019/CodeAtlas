"""M5 sanity test: documentation generator renders all 19 sections and
never fabricates values for empty sections (renders UNKNOWN markers)."""

from __future__ import annotations

from codeatlas.documentation.generator import generate_markdown
from codeatlas.evidence.schema import VerificationStatus
from codeatlas.knowledge.schema import Finding, Overview, ProjectKnowledge, Unknown


def test_generate_markdown_renders_all_sections_for_minimal_knowledge():
    knowledge = ProjectKnowledge(
        project_id="p1",
        name="Demo",
        root_path="/tmp/demo",
        overview=Overview(
            name=Finding(value="Demo", confidence=1.0, status=VerificationStatus.CONFIRMED)
        ),
        unknowns=[Unknown(topic="Database engine", reason="No ORM found.", area="database_model")],
    )
    md = generate_markdown(knowledge)

    for heading in [
        "## 1. Project Overview", "## 2. Technology Stack", "## 3. Repository Structure",
        "## 4. Architecture", "## 5. Component Documentation", "## 6. Application Flows",
        "## 7. Business Rules", "## 8. API Documentation", "## 9. Database Documentation",
        "## 10. Authentication & Authorization", "## 11. External Integrations",
        "## 12. Configuration", "## 13. Coding Standards", "## 14. Deployment",
        "## 15. Existing Tests", "## 16. Dependencies", "## 17. Known Issues",
        "## 18. Unknowns and Verification Gaps", "## 19. Evidence Index",
    ]:
        assert heading in md

    assert "Demo" in md
    assert "Database engine" in md
    assert "❔" in md  # UNKNOWN markers present for unanalyzed sections
