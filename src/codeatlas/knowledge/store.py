"""SQLite-backed Knowledge store — see ARCHITECTURE.md §2, §3.

Each top-level section of ``ProjectKnowledge`` is stored as its own row
keyed by ``(project_id, section)`` with a JSON payload, plus a file-hash
cache table that is the substrate for incremental re-analysis
(ARCHITECTURE.md §7). Swapping SQLite for Postgres later means replacing
this module's connection handling only — callers use the same interface.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from codeatlas.knowledge.schema import ProjectKnowledge

_SECTION_FIELDS = [
    "overview",
    "technology_stack",
    "repository_structure",
    "architecture",
    "components",
    "application_flows",
    "business_rules",
    "api_catalog",
    "database_model",
    "authentication",
    "authorization",
    "external_integrations",
    "configuration",
    "coding_standards",
    "deployment",
    "existing_tests",
    "dependencies",
    "known_issues",
    "unknowns",
    "evidence_index",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    analyzed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_sections (
    project_id TEXT NOT NULL,
    section TEXT NOT NULL,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, section),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS file_cache (
    project_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    last_analyzed_at TEXT NOT NULL,
    PRIMARY KEY (project_id, relative_path)
);
"""


class KnowledgeStore:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "knowledge.db"
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "KnowledgeStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def save(self, knowledge: ProjectKnowledge) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO projects (project_id, name, root_path, schema_version, analyzed_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(project_id) DO UPDATE SET
                 name=excluded.name, root_path=excluded.root_path,
                 schema_version=excluded.schema_version, analyzed_at=excluded.analyzed_at""",
            (
                knowledge.project_id,
                knowledge.name,
                knowledge.root_path,
                knowledge.schema_version,
                knowledge.analyzed_at.isoformat(),
            ),
        )
        dumped = knowledge.model_dump(mode="json")
        now = knowledge.analyzed_at.isoformat()
        for section in _SECTION_FIELDS:
            payload = dumped.get(section)
            import json as _json

            cur.execute(
                """INSERT INTO knowledge_sections (project_id, section, payload, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(project_id, section) DO UPDATE SET
                     payload=excluded.payload, updated_at=excluded.updated_at""",
                (knowledge.project_id, section, _json.dumps(payload), now),
            )
        self._conn.commit()

    def load(self, project_id: str) -> ProjectKnowledge | None:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT name, root_path, schema_version, analyzed_at FROM projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        name, root_path, schema_version, analyzed_at = row

        import json as _json

        sections: dict[str, object] = {}
        for sec_row in cur.execute(
            "SELECT section, payload FROM knowledge_sections WHERE project_id = ?",
            (project_id,),
        ):
            section, payload = sec_row
            sections[section] = _json.loads(payload)

        data = {
            "project_id": project_id,
            "name": name,
            "root_path": root_path,
            "schema_version": schema_version,
            "analyzed_at": analyzed_at,
            **sections,
        }
        return ProjectKnowledge.model_validate(data)

    def load_section(self, project_id: str, section: str) -> object | None:
        if section not in _SECTION_FIELDS:
            raise ValueError(f"Unknown knowledge section: {section}")
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT payload FROM knowledge_sections WHERE project_id = ? AND section = ?",
            (project_id, section),
        ).fetchone()
        if row is None:
            return None
        import json as _json

        return _json.loads(row[0])

    def list_projects(self) -> list[tuple[str, str, str]]:
        cur = self._conn.cursor()
        return cur.execute("SELECT project_id, name, root_path FROM projects").fetchall()

    # -- file hash cache, for incremental re-analysis (ARCHITECTURE.md §7) --

    def get_cached_hash(self, project_id: str, relative_path: str) -> str | None:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT content_hash FROM file_cache WHERE project_id = ? AND relative_path = ?",
            (project_id, relative_path),
        ).fetchone()
        return row[0] if row else None

    def set_cached_hash(self, project_id: str, relative_path: str, content_hash: str, timestamp: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO file_cache (project_id, relative_path, content_hash, last_analyzed_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(project_id, relative_path) DO UPDATE SET
                 content_hash=excluded.content_hash, last_analyzed_at=excluded.last_analyzed_at""",
            (project_id, relative_path, content_hash, timestamp),
        )
        self._conn.commit()
