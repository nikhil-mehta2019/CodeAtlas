"""External integrations analyzer — static detection of third-party
service integrations (ARCHITECTURE.md §13; product spec §13 "External
Integration Discovery").

V1 scope, honestly stated:

- Integration **identity** (provider + purpose + API) comes from declared
  dependency names, reusing the Discovery Engine's already-parsed
  Dependency list (same pattern as ``codeatlas.analysis.database`` /
  ``authentication``). A handful of representative providers per category
  (payment, email, SMS/video messaging, team messaging, cloud object
  storage, authentication providers, message queues) are recognized —
  this is not an exhaustive catalog, consistent with the spec's own
  "V1 does not need perfect support for every ecosystem" scoping applied
  here to third-party integrations.
- Broad, multi-purpose SDKs (``boto3``, ``aws-sdk``) confirm the
  *provider* (AWS) but not a specific purpose — which AWS service is
  actually used cannot be determined without deeper call-site analysis,
  so their purpose is reported honestly as "unspecified" and the finding
  is INFERRED rather than CONFIRMED.
- **Webhook usage** is only attributed to a specific integration when a
  route declaration contains both the literal word "webhook" and that
  provider's name token on the same line — a bare "/webhook" route with
  no provider name is never guessed at.
- **Configuration keys** are matched by provider-name-token substring
  against environment/config key *names* found in files the Discovery
  Engine's priority plan already flagged as configuration — only names,
  never values. Every excerpt taken from a config file is additionally
  passed through ``codeatlas.repository.secrets.redact`` as defense in
  depth, since this is the first analyzer that reads ``.env``-style files
  (previous analyzers only ever read source code).

Nothing here calls an LLM. No dependency match → no integration finding.
"""

from __future__ import annotations

import itertools
import re

from codeatlas.discovery.engine import DiscoveryContext
from codeatlas.evidence.schema import Evidence, SourceLocation, VerificationStatus
from codeatlas.knowledge.schema import ExternalIntegration
from codeatlas.repository.secrets import redact

_MAX_FILES_SCANNED = 200

# dependency name (lowercase) -> (provider, purpose, api_hint, is_specific)
# is_specific=False means the dependency is a broad, multi-purpose SDK:
# provider identity is solid, but the purpose guess is not, so it is
# reported as INFERRED rather than CONFIRMED.
_INTEGRATION_DEPENDENCIES: dict[str, tuple[str, str, str | None, bool]] = {
    "stripe": ("Stripe", "Payment processing", "Stripe API", True),
    "braintree": ("Braintree", "Payment processing", "Braintree API", True),
    "paypal-rest-sdk": ("PayPal", "Payment processing", "PayPal REST API", True),
    "paypalrestsdk": ("PayPal", "Payment processing", "PayPal REST API", True),
    "razorpay": ("Razorpay", "Payment processing", "Razorpay API", True),
    "sendgrid": ("SendGrid", "Email delivery", "SendGrid API", True),
    "@sendgrid/mail": ("SendGrid", "Email delivery", "SendGrid API", True),
    "nodemailer": ("Nodemailer (SMTP)", "Email delivery", None, True),
    "postmark": ("Postmark", "Email delivery", "Postmark API", True),
    "twilio": ("Twilio", "SMS/voice/video messaging", "Twilio API", True),
    "@slack/web-api": ("Slack", "Team messaging", "Slack Web API", True),
    "slack-sdk": ("Slack", "Team messaging", "Slack Web API", True),
    "boto3": (
        "AWS",
        "Unspecified AWS service usage (broad SDK; exact service not determined statically)",
        "AWS SDK",
        False,
    ),
    "aws-sdk": (
        "AWS",
        "Unspecified AWS service usage (broad SDK; exact service not determined statically)",
        "AWS SDK",
        False,
    ),
    "@aws-sdk/client-s3": ("AWS S3", "Cloud object storage", "AWS S3 API", True),
    "google-cloud-storage": ("Google Cloud Storage", "Cloud object storage", "GCS API", True),
    "@google-cloud/storage": ("Google Cloud Storage", "Cloud object storage", "GCS API", True),
    "azure-storage-blob": ("Azure Blob Storage", "Cloud object storage", "Azure Storage API", True),
    "auth0": ("Auth0", "Authentication provider", "Auth0 API", True),
    "auth0-python": ("Auth0", "Authentication provider", "Auth0 API", True),
    "mux-python": ("Mux", "Video platform", "Mux API", True),
    "@mux/mux-node": ("Mux", "Video platform", "Mux API", True),
    "kafkajs": ("Kafka", "Message queue/streaming", None, True),
    "kafka-python": ("Kafka", "Message queue/streaming", None, True),
    "amqplib": ("RabbitMQ", "Message queue", None, True),
    "pika": ("RabbitMQ", "Message queue", None, True),
}

_ROUTE_LINE_PATTERN = re.compile(
    r"@(?:app|router)\.(?:get|post|put|patch|delete)\(|(?:app|router)\.(?:get|post|put|patch|delete)\("
)
_ENV_KEY_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*[=:]")


def analyze_integrations(ctx: DiscoveryContext, walker) -> tuple[list[ExternalIntegration], list[Evidence]]:
    evidence: list[Evidence] = []
    integrations_by_provider: dict[str, ExternalIntegration] = {}
    finding_id_by_provider: dict[str, str] = {}

    for dep in ctx.result.dependencies:
        match = _INTEGRATION_DEPENDENCIES.get(dep.name.lower())
        if match is None:
            continue
        provider, purpose, api_hint, specific = match
        finding_id = f"integration:{provider_token(provider)}"
        finding_id_by_provider[provider] = finding_id

        status = VerificationStatus.CONFIRMED if specific else VerificationStatus.INFERRED
        confidence = 0.85 if specific else 0.55

        evidence.append(
            Evidence(
                finding_id=finding_id,
                source_file=dep.source_file,
                excerpt=f"dependency '{dep.name}' declared",
                reasoning=f"'{dep.name}' is a declared dependency, identifying an integration with {provider}.",
                confidence=confidence,
                verification_status=status,
                discovered_by="static",
            )
        )

        if provider not in integrations_by_provider:
            integrations_by_provider[provider] = ExternalIntegration(
                purpose=purpose, provider=provider, api=api_hint, status=status, confidence=confidence
            )
        else:
            existing = integrations_by_provider[provider]
            if existing.status != VerificationStatus.CONFIRMED and status == VerificationStatus.CONFIRMED:
                existing.status = status
                existing.confidence = max(existing.confidence, confidence)

    _attach_webhooks(ctx, walker, integrations_by_provider, finding_id_by_provider, evidence)
    _attach_configuration_keys(ctx, walker, integrations_by_provider, finding_id_by_provider, evidence)

    return list(integrations_by_provider.values()), evidence


def provider_token(provider: str) -> str:
    first_word = provider.split()[0]
    return re.sub(r"[^A-Za-z0-9]+", "", first_word).lower()


def _candidate_files(ctx: DiscoveryContext, paths: list[str]):
    files_by_path = {f.relative_path: f for f in ctx.tree.readable_files}
    for path in itertools.islice(paths, _MAX_FILES_SCANNED):
        f = files_by_path.get(path)
        if f is not None:
            yield f


def _attach_webhooks(
    ctx: DiscoveryContext,
    walker,
    integrations_by_provider: dict[str, ExternalIntegration],
    finding_id_by_provider: dict[str, str],
    evidence: list[Evidence],
) -> None:
    if not integrations_by_provider:
        return

    candidate_paths = list(itertools.chain(ctx.priority_plan.controllers_routes, ctx.priority_plan.entry_points))
    for f in _candidate_files(ctx, candidate_paths):
        if not f.relative_path.endswith((".py", ".js", ".ts")):
            continue
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "webhook" not in line.lower() or not _ROUTE_LINE_PATTERN.search(line):
                continue
            for provider, integration in integrations_by_provider.items():
                token = provider_token(provider)
                if token and token in line.lower() and not integration.webhook:
                    integration.webhook = True
                    evidence.append(
                        Evidence(
                            finding_id=finding_id_by_provider[provider],
                            source_file=f.relative_path,
                            location=SourceLocation(file=f.relative_path, line_start=lineno, line_end=lineno),
                            excerpt=line.strip()[:160],
                            reasoning=(
                                f"Route declaration at {f.relative_path}:{lineno} references both "
                                f"'webhook' and '{provider}'."
                            ),
                            confidence=0.75,
                            verification_status=VerificationStatus.CONFIRMED,
                            discovered_by="static",
                        )
                    )


def _attach_configuration_keys(
    ctx: DiscoveryContext,
    walker,
    integrations_by_provider: dict[str, ExternalIntegration],
    finding_id_by_provider: dict[str, str],
    evidence: list[Evidence],
) -> None:
    if not integrations_by_provider:
        return

    for f in _candidate_files(ctx, ctx.priority_plan.config_files):
        try:
            text = walker.read_text(f)
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = _ENV_KEY_PATTERN.match(line)
            if not m:
                continue
            key_name = m.group(1)
            for provider, integration in integrations_by_provider.items():
                token = provider_token(provider)
                if token and token in key_name.lower() and key_name not in integration.configuration_keys:
                    integration.configuration_keys.append(key_name)
                    # Defense in depth: this is the only analyzer that reads .env-style
                    # files, so redact the excerpt even though only the key name (never
                    # the value) is captured by the regex above.
                    safe_excerpt = redact(key_name).text
                    evidence.append(
                        Evidence(
                            finding_id=finding_id_by_provider[provider],
                            source_file=f.relative_path,
                            location=SourceLocation(file=f.relative_path, line_start=lineno, line_end=lineno),
                            excerpt=safe_excerpt,
                            reasoning=(
                                f"Configuration key '{key_name}' at {f.relative_path}:{lineno} "
                                f"references '{provider}' by name. Only the key name is captured, never its value."
                            ),
                            confidence=0.7,
                            verification_status=VerificationStatus.CONFIRMED,
                            discovered_by="static",
                        )
                    )
