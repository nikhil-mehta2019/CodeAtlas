"""Path-confined, gitignore-aware repository walker — ARCHITECTURE.md §5, §8.

This is the *only* place in the codebase allowed to touch the target
repository's filesystem directly. Every other layer receives
``RepoFile``/``RepoTree`` objects from here, never raw paths it resolves
itself — that is what makes the "confined under repo root" guarantee
actually hold.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from codeatlas.repository.filters import (
    DEFAULT_EXCLUDED_DIRS,
    LOCKFILE_NAMES,
    MAX_READABLE_FILE_BYTES,
    is_probably_binary,
    load_gitignore_spec,
)


class PathEscapeError(ValueError):
    """Raised when a resolved path would fall outside the repository root."""


@dataclass(frozen=True)
class RepoFile:
    """A file discovered under the repository root.

    ``relative_path`` uses forward slashes regardless of host OS, so
    evidence source paths are stable across platforms.
    """

    relative_path: str
    absolute_path: Path
    size_bytes: int
    is_binary: bool
    is_lockfile: bool
    excluded: bool  # True if it matched an exclusion rule (still recorded)
    exclusion_reason: str | None = None


@dataclass
class RepoTree:
    root: Path
    files: list[RepoFile] = field(default_factory=list)

    @property
    def readable_files(self) -> list[RepoFile]:
        return [f for f in self.files if not f.excluded and not f.is_binary]


class RepositoryWalker:
    """Walks a repository once, applying exclusion rules, staying confined
    to ``root``."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"Repository root does not exist or is not a directory: {self.root}")
        self._gitignore_spec = load_gitignore_spec(self.root)

    def resolve_confined(self, relative_path: str) -> Path:
        """Resolve a repo-relative path, raising if it escapes the root.

        Guards against ``..`` traversal and symlink escapes alike —
        both the lexical path and the resolved real path are checked.
        """
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise PathEscapeError(
                f"Path '{relative_path}' resolves outside repository root {self.root}"
            ) from None
        return candidate

    def _is_gitignored(self, rel_posix: str) -> bool:
        if self._gitignore_spec is None:
            return False
        return self._gitignore_spec.match_file(rel_posix)

    def walk(self) -> RepoTree:
        tree = RepoTree(root=self.root)
        for path in sorted(self.root.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(self.root)
            rel_posix = rel.as_posix()

            if any(part in DEFAULT_EXCLUDED_DIRS for part in rel.parts[:-1]):
                tree.files.append(
                    RepoFile(
                        relative_path=rel_posix,
                        absolute_path=path,
                        size_bytes=self._safe_size(path),
                        is_binary=False,
                        is_lockfile=path.name in LOCKFILE_NAMES,
                        excluded=True,
                        exclusion_reason="vendor_or_build_dir",
                    )
                )
                continue

            if self._is_gitignored(rel_posix):
                tree.files.append(
                    RepoFile(
                        relative_path=rel_posix,
                        absolute_path=path,
                        size_bytes=self._safe_size(path),
                        is_binary=False,
                        is_lockfile=path.name in LOCKFILE_NAMES,
                        excluded=True,
                        exclusion_reason="gitignored",
                    )
                )
                continue

            size = self._safe_size(path)
            binary = is_probably_binary(path)
            too_large = size > MAX_READABLE_FILE_BYTES

            tree.files.append(
                RepoFile(
                    relative_path=rel_posix,
                    absolute_path=path,
                    size_bytes=size,
                    is_binary=binary,
                    is_lockfile=path.name in LOCKFILE_NAMES,
                    excluded=too_large,
                    exclusion_reason="too_large" if too_large else None,
                )
            )
        return tree

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def read_text(self, repo_file: RepoFile, max_bytes: int = MAX_READABLE_FILE_BYTES) -> str:
        """Read a file's text content, confined and size-capped."""
        confined = self.resolve_confined(repo_file.relative_path)
        if repo_file.is_binary:
            raise ValueError(f"Refusing to read binary-flagged file as text: {repo_file.relative_path}")
        data = confined.read_bytes()[:max_bytes]
        return data.decode("utf-8", errors="replace")

    def content_hash(self, repo_file: RepoFile) -> str:
        confined = self.resolve_confined(repo_file.relative_path)
        h = hashlib.sha256()
        try:
            h.update(confined.read_bytes())
        except OSError:
            h.update(repo_file.relative_path.encode())
        return h.hexdigest()

    def repository_fingerprint(self, tree: RepoTree | None = None) -> str:
        """Content-hash of the whole tree's (path, size) listing — used to
        derive a stable project_id and as the basis for the incremental-
        analysis cache (ARCHITECTURE.md §7)."""
        h = hashlib.sha256()
        tree = tree if tree is not None else self.walk()
        for f in sorted(tree.files, key=lambda f: f.relative_path):
            h.update(f"{f.relative_path}:{f.size_bytes}\n".encode())
        return h.hexdigest()[:16]
