"""Discovery Engine — orchestrates ecosystem + infra detectors and the
priority-path builder into one static, zero-LLM-cost pass over a
repository. See ARCHITECTURE.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from codeatlas.discovery.ecosystems.node_eco import NodeEcosystemDetector
from codeatlas.discovery.ecosystems.python_eco import PythonEcosystemDetector
from codeatlas.discovery.ecosystems.shallow import SHALLOW_DETECTORS
from codeatlas.discovery.infra import detect_infra
from codeatlas.discovery.priority import PriorityPlan, build_priority_plan
from codeatlas.discovery.result import DiscoveryResult
from codeatlas.knowledge.schema import ConfigurationItem, DirectoryInfo, RepositoryStructure
from codeatlas.repository.identity import derive_project_id
from codeatlas.repository.walker import RepoTree, RepositoryWalker

_ECOSYSTEM_DETECTORS = [PythonEcosystemDetector(), NodeEcosystemDetector(), *SHALLOW_DETECTORS]
_ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


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
        self._discover_environment_configuration(tree, walker, priority_plan, result)
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
    def _discover_environment_configuration(
        tree: RepoTree,
        walker: RepositoryWalker,
        priority_plan: PriorityPlan,
        result: DiscoveryResult,
    ) -> None:
        """Record names from readable ``.env`` files without reading values into knowledge.

        Configuration values can contain credentials, so this intentionally recognizes
        only assignment keys in files already admitted by the repository walker. Gitignored
        and otherwise excluded files remain out of scope.
        """
        files_by_path = {file.relative_path: file for file in tree.readable_files}
        for path in priority_plan.config_files:
            filename = path.rsplit("/", 1)[-1]
            if not filename.startswith(".env"):
                continue
            repo_file = files_by_path.get(path)
            if repo_file is None:
                continue
            try:
                text = walker.read_text(repo_file)
            except Exception:
                result.notes.append(f"Failed to read configuration file {path}; skipped.")
                continue
            for line in text.splitlines():
                match = _ENV_ASSIGNMENT.match(line)
                if match is None:
                    continue
                key = match.group(1)
                if any(item.key == key and item.source_file == path for item in result.configuration_items):
                    continue
                result.configuration_items.append(
                    ConfigurationItem(key=key, required=None, source_file=path)
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
