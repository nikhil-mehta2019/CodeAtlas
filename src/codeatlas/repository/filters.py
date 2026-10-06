"""Exclusion rules for the repository walker — see ARCHITECTURE.md §5, §8.

Two separate concerns, kept separate on purpose:

  * ``DEFAULT_EXCLUDED_DIRS`` / ``is_probably_binary`` — content we never
    read into memory (vendor code, build output, binaries). Their
    *existence* is still recorded by the walker; we just don't open them.
  * ``.gitignore``-style patterns via ``pathspec`` — project-specific
    exclusions the repo author already declared.
"""

from __future__ import annotations

from pathlib import Path

import pathspec

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "dist",
    "build",
    "out",
    "target",
    "bin",
    "obj",
    ".next",
    ".nuxt",
    ".idea",
    ".vs",
    ".vscode",
    "coverage",
    ".gradle",
    ".terraform",
    "bower_components",
    "packages",  # NuGet classic-style package dir
    ".cache",
}

# Files whose *content* is rarely useful to read but whose existence is a
# strong signal (lockfiles confirm a package manager, for instance).
LOCKFILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "composer.lock",
    "Gemfile.lock",
    "go.sum",
    "Cargo.lock",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".jar", ".war",
    ".pyc", ".pyo", ".o", ".a",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".db", ".sqlite", ".sqlite3",
}

MAX_READABLE_FILE_BYTES = 1_000_000  # 1 MB; larger files are recorded, not read


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as f:
            chunk = f.read(2048)
    except OSError:
        return True
    return b"\x00" in chunk


def load_gitignore_spec(repo_root: Path) -> pathspec.PathSpec | None:
    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        return None
    try:
        lines = gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)
