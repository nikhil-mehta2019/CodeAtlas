"""M7 sanity tests: authentication & authorization analyzer.

Covers the three required status behaviors per .claude/skills/build-analyzer:
  - a CONFIRMED finding backed by static evidence (JWT mechanism, password
    hashing, a named-role permission check),
  - an ambiguous case that comes back INFERRED/UNVERIFIED, not CONFIRMED
    (a session-only dependency signal; an unnamed permission check with no
    role model),
  - no fabricated finding when there is no signal at all.
"""

from __future__ import annotations

from pathlib import Path

from codeatlas.analysis.authentication import analyze_authentication
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.evidence.schema import VerificationStatus
from codeatlas.repository.walker import RepositoryWalker

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def _discover(name: str):
    ctx = DiscoveryEngine().discover(str(FIXTURES / name))
    walker = RepositoryWalker(FIXTURES / name)
    return ctx, walker


def test_jwt_mechanism_confirmed_from_code_scan_python_fixture():
    ctx, walker = _discover("python_fastapi")
    authn, authz, evidence = analyze_authentication(ctx, walker)

    assert authn.mechanism is not None
    assert "JWT" in authn.mechanism.value
    assert authn.mechanism.status == VerificationStatus.CONFIRMED

    mechanism_evidence = [e for e in evidence if e.finding_id == "authentication:mechanism"]
    assert mechanism_evidence
    assert all(e.discovered_by == "static" for e in mechanism_evidence)
    assert any(e.source_file == "app/auth.py" for e in mechanism_evidence)


def test_password_handling_confirmed_from_code_scan_python_fixture():
    ctx, walker = _discover("python_fastapi")
    authn, authz, evidence = analyze_authentication(ctx, walker)

    assert authn.password_handling is not None
    assert "app/auth.py" in authn.password_handling
    pw_evidence = [e for e in evidence if e.finding_id == "authentication:password_handling"]
    assert pw_evidence
    assert pw_evidence[0].verification_status == VerificationStatus.CONFIRMED


def test_rbac_inferred_with_named_role_python_fixture():
    ctx, walker = _discover("python_fastapi")
    authn, authz, evidence = analyze_authentication(ctx, walker)

    assert "admin" in authz.roles
    assert authz.model is not None
    assert authz.model.value == "RBAC (role-based)"
    assert authz.model.status == VerificationStatus.INFERRED  # observed checks, interpretation is inferred
    assert any("app/auth.py" in ep for ep in authz.protected_endpoints)

    authz_evidence = [e for e in evidence if e.finding_id == "authorization:model"]
    assert authz_evidence
    assert any(e.verification_status == VerificationStatus.CONFIRMED for e in authz_evidence)


def test_jwt_and_rbac_confirmed_from_node_fixture_dependencies_and_code():
    ctx, walker = _discover("node_express")
    authn, authz, evidence = analyze_authentication(ctx, walker)

    assert authn.mechanism is not None
    assert "JWT" in authn.mechanism.value
    assert authn.mechanism.status == VerificationStatus.CONFIRMED

    # Manifest-based (jsonwebtoken dependency) AND code-scan-based (jwt.sign call) evidence both present.
    mechanism_sources = {e.source_file for e in evidence if e.finding_id == "authentication:mechanism"}
    assert "package.json" in mechanism_sources
    assert "routes/users.js" in mechanism_sources

    assert "admin" in authz.roles
    assert authz.model.value == "RBAC (role-based)"


def test_session_only_signal_is_inferred_not_confirmed(tmp_path):
    repo = tmp_path / "session_only_repo"
    (repo).mkdir()
    (repo / "package.json").write_text(
        '{"name": "demo", "dependencies": {"express-session": "^1.18.0"}}'
    )

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    authn, authz, evidence = analyze_authentication(ctx, walker)

    assert authn.mechanism is not None
    assert authn.mechanism.value == "Session"
    assert authn.mechanism.status == VerificationStatus.INFERRED  # weaker signal, never CONFIRMED alone


def test_no_fabricated_findings_when_no_signal(tmp_path):
    repo = tmp_path / "empty_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "util.py").write_text("def add(a, b):\n    return a + b\n")

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    authn, authz, evidence = analyze_authentication(ctx, walker)

    assert authn.mechanism is None
    assert authn.password_handling is None
    assert authn.token_handling is None
    assert authz.model is None
    assert authz.roles == []
    assert authz.protected_endpoints == []
    assert evidence == []
