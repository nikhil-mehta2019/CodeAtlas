"""Node.js / TypeScript ecosystem detector — deep support.

Covers plain Node, Express, NestJS, React, Next.js, Angular, Vue as
dependency-name signals (ARCHITECTURE.md §2 scopes deep AST parsing to
Python in V1; other ecosystems use manifest + dependency-name heuristics,
which is still a deterministic/static fact: "package.json lists 'react'
as a dependency" is directly observable, not a guess).
"""

from __future__ import annotations

import json

from codeatlas.discovery.base import make_evidence_kwargs_static
from codeatlas.discovery.result import DiscoveryResult
from codeatlas.evidence.schema import Evidence
from codeatlas.knowledge.schema import ConfigurationItem, Dependency, TechnologyItem
from codeatlas.repository.walker import RepoTree, RepositoryWalker

_FRAMEWORK_DEP_MARKERS = {
    "react": "React",
    "next": "Next.js",
    "@angular/core": "Angular",
    "vue": "Vue.js",
    "express": "Express",
    "@nestjs/core": "NestJS",
    "fastify": "Fastify",
    "koa": "Koa",
    "svelte": "Svelte",
    "@remix-run/react": "Remix",
}

_TEST_DEP_MARKERS = {
    "jest": "Jest",
    "mocha": "Mocha",
    "vitest": "Vitest",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "@playwright/test": "Playwright",
    "jasmine": "Jasmine",
    "ava": "AVA",
}

_LOCKFILE_TO_MANAGER = {
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
}


class NodeEcosystemDetector:
    name = "node"

    def applies(self, tree: RepoTree) -> bool:
        return any(f.relative_path.rsplit("/", 1)[-1] == "package.json" and not f.excluded for f in tree.files)

    def detect(self, tree: RepoTree, walker: RepositoryWalker) -> DiscoveryResult:
        result = DiscoveryResult()
        pkg_files = [f for f in tree.files if f.relative_path.rsplit("/", 1)[-1] == "package.json" and not f.excluded]
        # Root package.json first, then any nested ones (monorepo signal).
        pkg_files.sort(key=lambda f: f.relative_path.count("/"))

        has_typescript = any(f.relative_path.endswith((".ts", ".tsx")) for f in tree.readable_files)
        result.technology_items.append(TechnologyItem(category="language", name="TypeScript" if has_typescript else "JavaScript"))

        for pkg_file in pkg_files[:5]:  # cap for very large monorepos
            self._parse_package_json(pkg_file, walker, result)

        for lockfile_name, manager in _LOCKFILE_TO_MANAGER.items():
            if any(f.relative_path.rsplit("/", 1)[-1] == lockfile_name for f in tree.files):
                result.technology_items.append(TechnologyItem(category="package_manager", name=manager))
                result.evidence.append(
                    Evidence(
                        finding_id=f"tech:pkgmgr:{manager}",
                        source_file=lockfile_name,
                        excerpt=f"{lockfile_name} present",
                        **make_evidence_kwargs_static(f"Presence of {lockfile_name} identifies {manager} as the package manager."),
                    )
                )
                break

        return result

    def _parse_package_json(self, pkg_file, walker: RepositoryWalker, result: DiscoveryResult) -> None:
        try:
            raw = walker.read_text(pkg_file)
            data = json.loads(raw)
        except Exception:
            result.notes.append(f"Failed to parse {pkg_file.relative_path}; skipped.")
            return

        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        direct_deps = data.get("dependencies", {})

        for name, version in deps.items():
            kind = "direct" if name in direct_deps else "dev"
            result.dependencies.append(
                Dependency(name=name, version=version, kind=kind, ecosystem="npm", source_file=pkg_file.relative_path)
            )
            key = name.lower()
            if key in _FRAMEWORK_DEP_MARKERS:
                fw = _FRAMEWORK_DEP_MARKERS[key]
                if not any(t.name == fw for t in result.technology_items):
                    result.technology_items.append(TechnologyItem(category="framework", name=fw, version=version))
                    result.evidence.append(
                        Evidence(
                            finding_id=f"tech:framework:{key}",
                            source_file=pkg_file.relative_path,
                            excerpt=f'"{name}": "{version}"',
                            **make_evidence_kwargs_static(f"'{name}' is declared in package.json, identifying the {fw} framework."),
                        )
                    )
            if key in _TEST_DEP_MARKERS and _TEST_DEP_MARKERS[key] not in result.test_frameworks:
                result.test_frameworks.append(_TEST_DEP_MARKERS[key])

        engines = data.get("engines", {})
        if "node" in engines:
            result.technology_items.append(TechnologyItem(category="runtime", name="Node.js", version=engines["node"]))

        for script_name in data.get("scripts", {}):
            result.notes.append(f"npm script '{script_name}' found in {pkg_file.relative_path}")
