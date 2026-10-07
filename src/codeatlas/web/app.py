"""CodeAtlas REST API — initial skeleton (ARCHITECTURE.md §9's new "Web
API Layer").

This is an **initialization**, not the full product surface: one real
endpoint wrapping the existing `Orchestrator`, proven to work end-to-end,
with the one security property that cannot be deferred — a network
caller must never be able to make this process read an arbitrary path on
its host filesystem.

Trust model change from the CLI, stated plainly: the CLI trusts whoever
runs it to only ever point it at paths they're already allowed to read
(their own machine, their own shell). A network caller is not the person
operating this process, so `repo_path` is never trusted as given — see
`_resolve_confined_repo_path`.

What is deliberately NOT built in this initialization (tracked gaps, not
oversights):
- No repo upload / git-clone support. `POST /analyze` only accepts a
  path that is already present under a server-configured root
  (`CODEATLAS_API_ALLOWED_ROOT`). Accepting arbitrary uploaded content
  is a materially bigger feature (storage, cleanup, size limits) than
  "initialize the layer."
- No job queue / async execution tracking. `Orchestrator.run()` is
  file-I/O-bound and synchronous; it is called from a plain (non-async)
  route function so FastAPI/Starlette run it in its default worker
  thread pool rather than blocking the event loop. ARCHITECTURE.md §1
  already states V1 needs no task queue — nothing here changes that.
- No authentication/authorization on the endpoints themselves. Running
  this server at all is an operator decision; this module does not make
  it safe to expose on an untrusted network by itself. Documented as a
  known limitation, not papered over.
- No client-supplied `data_dir`. Where the knowledge base and evidence
  are written is server-configured (`CODEATLAS_API_DATA_DIR`), for the
  same reason `repo_path` is confined: a second client-controlled
  filesystem path is a second thing to validate, and the API doesn't
  need to expose it to do its job.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from codeatlas.knowledge.schema import ProjectKnowledge
from codeatlas.orchestrator.pipeline import Orchestrator

app = FastAPI(
    title="CodeAtlas API",
    description="AI Software Quality Agent — discovery & understanding, over HTTP.",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    status: str = "ok"


class AnalyzeRequest(BaseModel):
    repo_path: str = Field(
        ...,
        description=(
            "Path to the repository to analyze, relative to or under "
            "CODEATLAS_API_ALLOWED_ROOT. Absolute paths outside that root are rejected."
        ),
    )


class AnalyzeResponse(BaseModel):
    knowledge: ProjectKnowledge
    markdown_report: str


class ConfigurationError(RuntimeError):
    """Raised when the server-side environment isn't configured safely."""


def _allowed_root() -> Path:
    raw = os.environ.get("CODEATLAS_API_ALLOWED_ROOT")
    if not raw:
        # Fail closed: no configured root means no path is ever trusted,
        # rather than defaulting to "anything on disk is fair game."
        raise ConfigurationError(
            "CODEATLAS_API_ALLOWED_ROOT is not set; this server is not configured "
            "to analyze any repository path."
        )
    return Path(raw).resolve()


def _data_dir() -> Path:
    raw = os.environ.get("CODEATLAS_API_DATA_DIR")
    path = Path(raw).resolve() if raw else Path(tempfile.gettempdir()) / "codeatlas-api"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_confined_repo_path(repo_path: str) -> Path:
    """Resolve `repo_path` under the configured allowed root, or raise.

    Mirrors codeatlas.repository.walker.RepositoryWalker's own path
    confinement (CLAUDE.md: "Keep the repository walker's path
    confinement intact"), applied at the network boundary rather than
    the filesystem-walk boundary -- the earliest point an untrusted path
    string exists, before anything downstream ever sees it.
    """
    root = _allowed_root()
    candidate = (root / repo_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"'{repo_path}' resolves outside the server's allowed root.",
        ) from None
    if not candidate.is_dir():
        raise HTTPException(status_code=404, detail=f"No such repository directory: '{repo_path}'.")
    return candidate


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        confined_path = _resolve_confined_repo_path(request.repo_path)
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    orchestrator = Orchestrator(data_dir=_data_dir())
    try:
        run = orchestrator.run(str(confined_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AnalyzeResponse(knowledge=run.knowledge, markdown_report=run.markdown_report)
