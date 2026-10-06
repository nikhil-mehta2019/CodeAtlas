"""Shallow ecosystem detectors — manifest presence only, honestly labeled.

These confirm language/framework identity from a manifest file (a direct,
static fact) but do NOT parse dependency lists or deeper structure the way
the Python and Node detectors do. Each one appends a note to
``DiscoveryResult.notes`` saying exactly that, so the final report never
implies a depth of analysis that didn't happen (spec §31: No Fake
Completion).
"""

from __future__ import annotations

from dataclasses import dataclass

from codeatlas.discovery.base import make_evidence_kwargs_static
from codeatlas.discovery.result import DiscoveryResult
from codeatlas.evidence.schema import Evidence
from codeatlas.knowledge.schema import TechnologyItem
from codeatlas.repository.walker import RepoTree, RepositoryWalker


@dataclass
class _ManifestDetector:
    name: str
    language: str
    manifest_suffixes: tuple[str, ...]
    manifest_exact_names: tuple[str, ...] = ()

    def applies(self, tree: RepoTree) -> bool:
        return self._find_manifest(tree) is not None

    def _find_manifest(self, tree: RepoTree):
        for f in tree.files:
            if f.excluded:
                continue
            base = f.relative_path.rsplit("/", 1)[-1]
            if base in self.manifest_exact_names or base.endswith(self.manifest_suffixes):
                return f
        return None

    def detect(self, tree: RepoTree, walker: RepositoryWalker) -> DiscoveryResult:
        result = DiscoveryResult()
        manifest = self._find_manifest(tree)
        if manifest is None:
            return result
        result.technology_items.append(TechnologyItem(category="language", name=self.language))
        result.evidence.append(
            Evidence(
                finding_id=f"tech:language:{self.name}",
                source_file=manifest.relative_path,
                excerpt=f"manifest file '{manifest.relative_path}' present",
                **make_evidence_kwargs_static(
                    f"Presence of {manifest.relative_path} identifies a {self.language} project."
                ),
            )
        )
        result.notes.append(
            f"Shallow detector for {self.language}: manifest located, but dependency "
            f"list and deeper structure were not parsed in V1."
        )
        return result


DotNetDetector = _ManifestDetector(name="dotnet", language=".NET (C#)", manifest_suffixes=(".csproj", ".sln"))
JavaDetector = _ManifestDetector(
    name="java", language="Java", manifest_suffixes=(), manifest_exact_names=("pom.xml", "build.gradle", "build.gradle.kts")
)
GoDetector = _ManifestDetector(name="go", language="Go", manifest_suffixes=(), manifest_exact_names=("go.mod",))
PhpDetector = _ManifestDetector(name="php", language="PHP", manifest_suffixes=(), manifest_exact_names=("composer.json",))

SHALLOW_DETECTORS = [DotNetDetector, JavaDetector, GoDetector, PhpDetector]
