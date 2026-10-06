"""Project identity derivation — ARCHITECTURE.md §8 (project isolation)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def derive_project_id(root_path: str | Path, fingerprint: str) -> str:
    """Stable id from the repo's folder name + content fingerprint.

    Two different repos checked out under the same folder name never
    collide (the fingerprint differs); re-analyzing the same repo in place
    reuses the same id (same folder name, and the fingerprint only changes
    when file contents/listing actually change).
    """
    root = Path(root_path).resolve()
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", root.name).strip("-").lower() or "project"
    short = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    return f"{slug}-{short}-{fingerprint[:8]}"
