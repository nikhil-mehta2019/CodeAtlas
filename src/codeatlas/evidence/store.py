"""File-based Evidence store — see ARCHITECTURE.md §2, §4.

Each Evidence record is written as its own JSON file, keyed by
``evidence_id``, under ``<data_dir>/<project_id>/evidence/``. Keeping
evidence out of the SQLite knowledge DB makes individual findings easy to
diff, audit, and inspect without a database client.
"""

from __future__ import annotations

import json
from pathlib import Path

from codeatlas.evidence.schema import Evidence


class EvidenceStore:
    def __init__(self, data_dir: str | Path, project_id: str):
        self.project_id = project_id
        self.dir = Path(data_dir) / project_id / "evidence"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, evidence_id: str) -> Path:
        return self.dir / f"{evidence_id}.json"

    def save(self, evidence: Evidence) -> None:
        self._path_for(evidence.evidence_id).write_text(
            evidence.model_dump_json(indent=2), encoding="utf-8"
        )

    def save_many(self, evidence_list: list[Evidence]) -> None:
        for e in evidence_list:
            self.save(e)

    def load(self, evidence_id: str) -> Evidence:
        path = self._path_for(evidence_id)
        return Evidence.model_validate_json(path.read_text(encoding="utf-8"))

    def load_all(self) -> list[Evidence]:
        records: list[Evidence] = []
        for path in sorted(self.dir.glob("*.json")):
            records.append(Evidence.model_validate_json(path.read_text(encoding="utf-8")))
        return records

    def load_for_finding(self, finding_id: str) -> list[Evidence]:
        return [e for e in self.load_all() if e.finding_id == finding_id]
