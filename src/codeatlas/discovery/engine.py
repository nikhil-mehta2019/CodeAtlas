"""Discovery Engine — orchestrates ecosystem + infra detectors and the
priority-path builder into one static, zero-LLM-cost pass over a
repository. See ARCHITECTURE.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from codeatlas.discovery.ecosystems.node_eco import NodeEcosystemDetector
from codeatlas.discovery.ecosystems.python_eco import PythonEcosystemDetector
from codeatlas.discovery.ecosystems.shallow import SHALLOW_DETECTORS
from codeatlas.discovery.infra import detect_infra
from codeatlas.discovery.priority import PriorityPlan, build_priority_plan
from codeatlas.discovery.result import DiscoveryResult
from codeatlas.knowledge.schema import DirectoryInfo, RepositoryStructure
from codeatlas.repository.identity import derive_project_id
from codeatlas.repository.walker import RepoTree, RepositoryWalker

_ECOSYSTEM_DETECTORS = [PythonEcosystemDetector(), NodeEcosystemDetector(), *SHALLOW_DETECTORS]


@dataclass
class DiscoveryContext:
    project_id: str
    root_path: str
    tree: RepoTree
    result: DiscoveryResult
    priority_plan: PriorityPlan
    repository_structure: RepositoryStructure
    ecosystems_detected: list[str] = field(default_factory=list)


class DiscoveryEngine:
    def discover(self, repo_path: str) -> DiscoveryContext:
        walker = RepositoryWalker(repo_path)
        tree = walker.walk()
        fingerprint = walker.repository_fingerprint(tree)
        project_id = derive_project_id(repo_path, fingerprint)

        result = DiscoveryResult()
        ecosystems_detected: list[str] = []
        for detector in _ECOSYSTEM_DETECTORS:
            if detector.applies(tree):
                ecosystems_detected.append(detector.name)
                result.merge(detector.detect(tree, walker))

        result.merge(detect_infra(tree))

        priority_plan = build_priority_plan(tree)
        repo_structure = self._build_repository_structure(str(walker.root), tree)

        return DiscoveryContext(
            project_id=project_id,
            root_path=str(walker.root),
            tree=tree,
            result=result,
            priority_plan=priority_plan,
            repository_structure=repo_structure,
            ecosystems_detected=ecosystems_detected,
        )

    @staticmethod
    def _build_repository_structure(root_path: str, tree: RepoTree) -> RepositoryStructure:
        dir_stats: dict[str, dict[str, int]] = {}
        excluded_paths: set[str] = set()
        analyzed_count = 0

        for f in tree.files:
            directory = f.relative_path.rsplit("/", 1)[0] if "/" in f.relative_path else "."
            if f.excluded:
                excluded_paths.add(directory)
                continue
            analyzed_count += 1
            stats = dir_stats.setdefault(directory, {})
            ext = f.relative_path.rsplit(".", 1)[-1] if "." in f.relative_path.rsplit("/", 1)[-1] else "noext"
            stats[ext] = stats.get(ext, 0) + 1

        directories = [
            DirectoryInfo(path=path, file_count=sum(stats.values()), language_breakdown=stats)
            for path, stats in sorted(dir_stats.items())
        ]

        return RepositoryStructure(
            root_path=root_path,
            total_files=len(tree.files),
            total_files_analyzed=analyzed_count,
            excluded_paths=sorted(excluded_paths),
            directories=directories,
        )
