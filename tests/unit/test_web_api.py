"""Tests for the initial web API layer (codeatlas.web.app).

Not named test_mN_*.py deliberately: this is a new layer added on top of
the M1-M8 milestone sequence in ARCHITECTURE.md, not one of its numbered
items, so a fabricated "M9" label would be more misleading than helpful.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from codeatlas.web.app import app

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"

client = TestClient(app)


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_without_configured_root_fails_closed(monkeypatch):
    monkeypatch.delenv("CODEATLAS_API_ALLOWED_ROOT", raising=False)
    resp = client.post("/analyze", json={"repo_path": "python_fastapi"})
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


def test_analyze_real_fixture_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEATLAS_API_ALLOWED_ROOT", str(FIXTURES))
    monkeypatch.setenv("CODEATLAS_API_DATA_DIR", str(tmp_path / "data"))

    resp = client.post("/analyze", json={"repo_path": "python_fastapi"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["knowledge"]["project_id"]
    assert any(ep["path"] == "/health" for ep in body["knowledge"]["api_catalog"])
    # A CONFIRMED finding must carry real evidence, same rule the CLI/report enforce.
    mechanism = body["knowledge"]["authentication"]["mechanism"]
    assert mechanism is not None
    assert mechanism["status"] == "CONFIRMED"
    assert mechanism["evidence"], "CONFIRMED finding returned over the API must carry evidence"

    assert "# CodeAtlas Project Report" in body["markdown_report"]
    assert "/health" in body["markdown_report"]


def test_analyze_rejects_path_traversal_outside_allowed_root(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEATLAS_API_ALLOWED_ROOT", str(FIXTURES / "python_fastapi"))
    monkeypatch.setenv("CODEATLAS_API_DATA_DIR", str(tmp_path / "data"))

    resp = client.post("/analyze", json={"repo_path": "../node_express"})
    assert resp.status_code == 403
    assert "outside" in resp.json()["detail"]


def test_analyze_rejects_nonexistent_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEATLAS_API_ALLOWED_ROOT", str(FIXTURES))
    monkeypatch.setenv("CODEATLAS_API_DATA_DIR", str(tmp_path / "data"))

    resp = client.post("/analyze", json={"repo_path": "does_not_exist"})
    assert resp.status_code == 404


@pytest.mark.parametrize("bad_path", ["/etc", "/etc/passwd", "../../../../etc"])
def test_analyze_rejects_absolute_and_deep_traversal_paths(monkeypatch, tmp_path, bad_path):
    monkeypatch.setenv("CODEATLAS_API_ALLOWED_ROOT", str(FIXTURES / "python_fastapi"))
    monkeypatch.setenv("CODEATLAS_API_DATA_DIR", str(tmp_path / "data"))

    resp = client.post("/analyze", json={"repo_path": bad_path})
    assert resp.status_code in (403, 404)  # never 200, and never a raw file read
