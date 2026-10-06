"""Python ecosystem detector — deep support (ARCHITECTURE.md §2, §11 risk note)."""

from __future__ import annotations

import re
import tomllib

from codeatlas.discovery.base import make_evidence_kwargs_static
from codeatlas.discovery.result import DiscoveryResult
from codeatlas.evidence.schema import Evidence
from codeatlas.knowledge.schema import ConfigurationItem, Dependency, TechnologyItem
from codeatlas.repository.walker import RepoTree, RepositoryWalker

_FRAMEWORK_MARKERS = {
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "pyramid": "Pyramid",
    "tornado": "Tornado",
    "starlette": "Starlette",
    "sanic": "Sanic",
}

_TEST_MARKERS = {
    "pytest": "pytest",
    "unittest2": "unittest",
    "nose2": "nose2",
    "hypothesis": "hypothesis",
}

_REQ_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*([><=!~]+[0-9A-Za-z.\-,]*)?")


class PythonEcosystemDetector:
    name = "python"

    def applies(self, tree: RepoTree) -> bool:
        names = {f.relative_path.rsplit("/", 1)[-1] for f in tree.files if not f.excluded}
        return bool(
            names & {"pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "manage.py"}
        ) or any(f.relative_path.endswith(".py") for f in tree.readable_files)

    def detect(self, tree: RepoTree, walker: RepositoryWalker) -> DiscoveryResult:
        result = DiscoveryResult()
        files_by_name = {f.relative_path.rsplit("/", 1)[-1]: f for f in tree.files if not f.excluded}

        result.technology_items.append(
            TechnologyItem(category="language", name="Python")
        )
        result.evidence.append(
            Evidence(
                finding_id="tech:language:python",
                source_file=next(
                    (f.relative_path for f in tree.readable_files if f.relative_path.endswith(".py")),
                    "pyproject.toml",
                ),
                excerpt="*.py source files present",
                **make_evidence_kwargs_static("Repository contains Python source files."),
            )
        )

        if "pyproject.toml" in files_by_name:
            self._parse_pyproject(files_by_name["pyproject.toml"], walker, result)
        if "requirements.txt" in files_by_name:
            self._parse_requirements(files_by_name["requirements.txt"], walker, result)
        if "manage.py" in files_by_name:
            result.technology_items.append(TechnologyItem(category="framework", name="Django"))
            result.evidence.append(
                Evidence(
                    finding_id="tech:framework:django",
                    source_file=files_by_name["manage.py"].relative_path,
                    excerpt="manage.py present",
                    **make_evidence_kwargs_static("Django projects generate a manage.py entry point."),
                )
            )

        self._scan_imports_for_frameworks(tree, walker, result)

        if any(f.relative_path.startswith(("tests/", "test/")) or "/tests/" in f.relative_path for f in tree.readable_files):
            if "pytest" not in result.test_frameworks:
                result.test_frameworks.append("pytest (assumed; tests/ directory present)")

        return result

    def _parse_pyproject(self, file, walker: RepositoryWalker, result: DiscoveryResult) -> None:
        try:
            raw = walker.read_text(file)
            data = tomllib.loads(raw)
        except Exception:
            result.notes.append(f"Failed to parse {file.relative_path}; skipped.")
            return

        project = data.get("project", {})
        deps = project.get("dependencies", [])
        for dep in deps:
            name_match = _REQ_LINE.match(dep)
            if not name_match:
                continue
            dep_name = name_match.group(1)
            result.dependencies.append(
                Dependency(name=dep_name, version=name_match.group(2), kind="direct", ecosystem="pypi", source_file=file.relative_path)
            )
            self._maybe_framework_or_test(dep_name, file.relative_path, result)

        if "tool" in data and "poetry" in data["tool"]:
            result.technology_items.append(TechnologyItem(category="package_manager", name="Poetry"))
            result.evidence.append(
                Evidence(
                    finding_id="tech:pkgmgr:poetry",
                    source_file=file.relative_path,
                    excerpt="[tool.poetry] table present",
                    **make_evidence_kwargs_static("pyproject.toml declares a [tool.poetry] section."),
                )
            )
        elif "project" in data:
            result.technology_items.append(TechnologyItem(category="package_manager", name="pip/PEP 621"))

        if (req_py := project.get("requires-python")):
            result.technology_items.append(
                TechnologyItem(category="runtime", name="Python", version=req_py)
            )

    def _parse_requirements(self, file, walker: RepositoryWalker, result: DiscoveryResult) -> None:
        try:
            raw = walker.read_text(file)
        except Exception:
            result.notes.append(f"Failed to read {file.relative_path}; skipped.")
            return
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = _REQ_LINE.match(line)
            if not m:
                continue
            dep_name = m.group(1)
            result.dependencies.append(
                Dependency(name=dep_name, version=m.group(2), kind="direct", ecosystem="pypi", source_file=file.relative_path)
            )
            self._maybe_framework_or_test(dep_name, file.relative_path, result)
        result.technology_items.append(TechnologyItem(category="package_manager", name="pip"))

    def _maybe_framework_or_test(self, dep_name: str, source_file: str, result: DiscoveryResult) -> None:
        key = dep_name.lower()
        if key in _FRAMEWORK_MARKERS:
            fw = _FRAMEWORK_MARKERS[key]
            if not any(t.name == fw for t in result.technology_items):
                result.technology_items.append(TechnologyItem(category="framework", name=fw))
                result.evidence.append(
                    Evidence(
                        finding_id=f"tech:framework:{key}",
                        source_file=source_file,
                        excerpt=f"dependency '{dep_name}' declared",
                        **make_evidence_kwargs_static(f"'{dep_name}' is a direct dependency, identifying the {fw} framework."),
                    )
                )
        if key in _TEST_MARKERS and _TEST_MARKERS[key] not in result.test_frameworks:
            result.test_frameworks.append(_TEST_MARKERS[key])

    def _scan_imports_for_frameworks(self, tree: RepoTree, walker: RepositoryWalker, result: DiscoveryResult) -> None:
        """Fallback signal when no manifest declares the framework directly
        (e.g. framework vendored, or manifest parsing failed)."""
        known = {t.name.lower() for t in result.technology_items}
        import_pattern = re.compile(r"^\s*(?:from|import)\s+([A-Za-z0-9_]+)")
        checked = 0
        for f in tree.readable_files:
            if not f.relative_path.endswith(".py") or checked > 200:
                continue
            checked += 1
            try:
                text = walker.read_text(f, max_bytes=4000)
            except Exception:
                continue
            for line in text.splitlines()[:50]:
                m = import_pattern.match(line)
                if not m:
                    continue
                mod = m.group(1).lower()
                if mod in _FRAMEWORK_MARKERS and _FRAMEWORK_MARKERS[mod].lower() not in known:
                    fw = _FRAMEWORK_MARKERS[mod]
                    known.add(fw.lower())
                    result.technology_items.append(TechnologyItem(category="framework", name=fw))
                    result.evidence.append(
                        Evidence(
                            finding_id=f"tech:framework:{mod}",
                            source_file=f.relative_path,
                            excerpt=line.strip()[:120],
                            **make_evidence_kwargs_static(f"Source file imports '{mod}', identifying the {fw} framework."),
                        )
                    )
