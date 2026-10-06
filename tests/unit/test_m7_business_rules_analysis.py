"""M7 sanity tests: business rules analyzer.

Covers the three required status behaviors per .claude/skills/build-analyzer:
  - a CONFIRMED finding backed by static evidence (Pydantic Field
    constraint, role-gated action, enum state membership),
  - an "ambiguous case" check: a Field with a default is correctly NOT
    reported as required (it would be dishonest to call it required),
  - no fabricated finding when there is no signal at all.
"""

from __future__ import annotations

from pathlib import Path

from codeatlas.analysis.business_rules import analyze_business_rules
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.evidence.schema import VerificationStatus
from codeatlas.repository.walker import RepositoryWalker

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def _discover(name: str):
    ctx = DiscoveryEngine().discover(str(FIXTURES / name))
    walker = RepositoryWalker(FIXTURES / name)
    return ctx, walker


def test_pydantic_validation_rules_confirmed_with_evidence():
    ctx, walker = _discover("python_fastapi")
    rules, evidence = analyze_business_rules(ctx, walker)

    email_rule = next(r for r in rules if "email" in r.rule)
    assert email_rule.kind == "validation"
    assert email_rule.explicit is True
    assert email_rule.status == VerificationStatus.CONFIRMED
    assert "is required" in email_rule.rule
    assert "min_length=5" in email_rule.rule

    age_rule = next(r for r in rules if "age" in r.rule)
    assert "is required" not in age_rule.rule  # has a default -> honestly not reported as required
    assert "ge=0" in age_rule.rule and "le=120" in age_rule.rule

    validation_evidence = [e for e in evidence if e.finding_id.startswith("business_rule:validation:")]
    assert validation_evidence
    assert all(e.discovered_by == "static" for e in validation_evidence)
    assert all(e.source_file == "app/schemas.py" for e in validation_evidence)


def test_role_gated_action_rule_confirmed_with_evidence():
    ctx, walker = _discover("python_fastapi")
    rules, evidence = analyze_business_rules(ctx, walker)

    auth_rule = next(r for r in rules if r.kind == "authorization")
    assert auth_rule.explicit is True
    assert auth_rule.status == VerificationStatus.CONFIRMED
    assert "role 'admin'" in auth_rule.rule
    assert "delete_user" in auth_rule.rule

    rule_evidence = [e for e in evidence if e.finding_id.startswith("business_rule:authorization:")]
    assert rule_evidence
    assert rule_evidence[0].source_file == "app/auth.py"


def test_state_enum_rule_confirmed_without_asserting_transitions():
    ctx, walker = _discover("python_fastapi")
    rules, evidence = analyze_business_rules(ctx, walker)

    state_rule = next(r for r in rules if r.kind == "state_transition")
    assert state_rule.status == VerificationStatus.CONFIRMED
    assert "OrderStatus" in state_rule.rule
    assert "PENDING" in state_rule.rule and "SHIPPED" in state_rule.rule and "DELIVERED" in state_rule.rule
    # Never asserts which transitions are valid -- only the known set of states.
    assert "transition" not in state_rule.rule.lower()

    state_evidence = next(e for e in evidence if e.finding_id.startswith("business_rule:state:"))
    assert "No transition logic" in state_evidence.reasoning


def test_bare_login_required_is_not_treated_as_a_business_rule(tmp_path):
    repo = tmp_path / "bare_login_repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "views.py").write_text(
        "from functools import wraps\n\n"
        "def login_required(func):\n"
        "    @wraps(func)\n"
        "    def wrapper(*a, **kw):\n"
        "        return func(*a, **kw)\n"
        "    return wrapper\n\n"
        "@login_required\n"
        "def dashboard():\n"
        "    return {}\n"
    )

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    rules, evidence = analyze_business_rules(ctx, walker)

    assert not any(r.kind == "authorization" for r in rules)


def test_no_fabricated_findings_when_no_signal(tmp_path):
    repo = tmp_path / "empty_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "util.py").write_text("def add(a, b):\n    return a + b\n")

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    rules, evidence = analyze_business_rules(ctx, walker)

    assert rules == []
    assert evidence == []
