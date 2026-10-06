"""M7 sanity tests: external integrations analyzer.

Covers the three required status behaviors per .claude/skills/build-analyzer:
  - a CONFIRMED finding backed by static evidence (Stripe: dependency +
    webhook route + config key, all tied together),
  - an ambiguous case that comes back INFERRED, not CONFIRMED (a broad,
    multi-purpose SDK like aws-sdk, whose specific purpose is unknown),
  - no fabricated finding when there is no signal at all.
"""

from __future__ import annotations

from pathlib import Path

from codeatlas.analysis.integrations import analyze_integrations
from codeatlas.discovery.engine import DiscoveryEngine
from codeatlas.evidence.schema import VerificationStatus
from codeatlas.repository.walker import RepositoryWalker

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_repos"


def _discover(name: str):
    ctx = DiscoveryEngine().discover(str(FIXTURES / name))
    walker = RepositoryWalker(FIXTURES / name)
    return ctx, walker


def test_stripe_confirmed_with_dependency_webhook_and_config_evidence():
    ctx, walker = _discover("python_fastapi")
    integrations, evidence = analyze_integrations(ctx, walker)

    stripe = next(i for i in integrations if i.provider == "Stripe")
    assert stripe.status == VerificationStatus.CONFIRMED
    assert stripe.purpose == "Payment processing"
    assert stripe.webhook is True
    assert "STRIPE_API_KEY" in stripe.configuration_keys
    assert "STRIPE_WEBHOOK_SECRET" in stripe.configuration_keys

    stripe_evidence = [e for e in evidence if e.finding_id == "integration:stripe"]
    assert stripe_evidence
    assert all(e.discovered_by == "static" for e in stripe_evidence)
    # At least one evidence record for each signal: dependency, webhook route, config key.
    reasonings = " ".join(e.reasoning for e in stripe_evidence)
    assert "dependency" in reasonings
    assert "webhook" in reasonings.lower()
    assert "Configuration key" in reasonings

    # Secret values never appear in evidence excerpts, even though the config
    # file this analyzer read contains "changeme" placeholder values.
    assert all("changeme" not in e.excerpt for e in stripe_evidence)


def test_broad_sdk_is_inferred_not_confirmed():
    ctx, walker = _discover("node_express")
    integrations, evidence = analyze_integrations(ctx, walker)

    aws = next(i for i in integrations if i.provider == "AWS")
    assert aws.status == VerificationStatus.INFERRED  # provider identity is solid, purpose is a guess
    assert "unspecified" in aws.purpose.lower()
    assert aws.confidence < 0.6


def test_no_fabricated_findings_when_no_signal(tmp_path):
    repo = tmp_path / "empty_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "util.py").write_text("def add(a, b):\n    return a + b\n")

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    integrations, evidence = analyze_integrations(ctx, walker)

    assert integrations == []
    assert evidence == []


def test_webhook_never_attributed_without_provider_name_in_route(tmp_path):
    repo = tmp_path / "generic_webhook_repo"
    (repo / "app").mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["stripe>=7.0"]\n'
    )
    (repo / "app" / "main.py").write_text(
        'from fastapi import FastAPI\n\napp = FastAPI()\n\n'
        '@app.post("/webhooks/generic")\ndef generic_webhook():\n    return {}\n'
    )

    ctx = DiscoveryEngine().discover(str(repo))
    walker = RepositoryWalker(repo)
    integrations, evidence = analyze_integrations(ctx, walker)

    stripe = next(i for i in integrations if i.provider == "Stripe")
    assert stripe.webhook is False  # route says "webhook" but never names "stripe" -> not attributed
