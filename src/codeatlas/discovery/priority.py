"""Priority-path builder — ARCHITECTURE.md §5 step 4, §7.

Produces an ordered list of repo-relative paths the Analysis Engine should
look at, highest-signal first, so the orchestrator never needs to dump the
whole repository into an LLM context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codeatlas.repository.walker import RepoTree

_ENTRY_POINT_NAMES = {
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "server.js", "server.ts", "main.ts",
    "Program.cs", "Startup.cs",
    "Main.java", "Application.java",
    "main.go",
    "index.php", "public/index.php",
}

_CONFIG_PATTERNS = re.compile(
    r"(^|/)(\.env(\..+)?|settings\.py|config\.py|appsettings.*\.json|application\.ya?ml|application\.properties)$",
    re.IGNORECASE,
)

_CONTROLLER_DIR_PATTERN = re.compile(r"(^|/)(controllers?|routes?|api|views|handlers?|resolvers?)(/|$)", re.IGNORECASE)
_SERVICE_DIR_PATTERN = re.compile(r"(^|/)(services?|models?|entities|domain|repositories)(/|$)", re.IGNORECASE)
_MIGRATION_DIR_PATTERN = re.compile(r"(^|/)(migrations?|db/migrate|alembic)(/|$)", re.IGNORECASE)
_AUTH_PATTERN = re.compile(r"(^|/)[^/]*(auth|jwt|login|session|oauth|permission|rbac|authoriz)[^/]*$", re.IGNORECASE)
_TEST_DIR_PATTERN = re.compile(r"(^|/)(tests?|spec|__tests__)(/|$)", re.IGNORECASE)
_DOC_PATTERN = re.compile(r"(^|/)(README.*|docs?/.*|CONTRIBUTING.*|ARCHITECTURE.*)$", re.IGNORECASE)


@dataclass
class PriorityPlan:
    entry_points: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    controllers_routes: list[str] = field(default_factory=list)
    services_models: list[str] = field(default_factory=list)
    migrations: list[str] = field(default_factory=list)
    auth: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)

    def ordered(self) -> list[str]:
        """Flattened, de-duplicated, in the priority order the spec (§9) lists."""
        seen: set[str] = set()
        out: list[str] = []
        for bucket in (
            self.entry_points, self.config_files, self.controllers_routes,
            self.services_models, self.migrations, self.auth, self.tests, self.docs,
        ):
            for p in bucket:
                if p not in seen:
                    seen.add(p)
                    out.append(p)
        return out


def build_priority_plan(tree: RepoTree) -> PriorityPlan:
    plan = PriorityPlan()
    for f in tree.readable_files:
        p = f.relative_path
        base = p.rsplit("/", 1)[-1]

        if base in _ENTRY_POINT_NAMES or p in _ENTRY_POINT_NAMES:
            plan.entry_points.append(p)
        if _CONFIG_PATTERNS.search(p):
            plan.config_files.append(p)
        if _CONTROLLER_DIR_PATTERN.search(p):
            plan.controllers_routes.append(p)
        if _SERVICE_DIR_PATTERN.search(p):
            plan.services_models.append(p)
        if _MIGRATION_DIR_PATTERN.search(p):
            plan.migrations.append(p)
        if _AUTH_PATTERN.search(p):
            plan.auth.append(p)
        if _TEST_DIR_PATTERN.search(p):
            plan.tests.append(p)
        if _DOC_PATTERN.search(p):
            plan.docs.append(p)

    return plan
