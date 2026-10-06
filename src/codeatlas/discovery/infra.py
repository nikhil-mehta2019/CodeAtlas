"""Infrastructure detection — Docker, CI/CD, IaC. Static facts only."""

from __future__ import annotations

from codeatlas.discovery.base import make_evidence_kwargs_static
from codeatlas.discovery.result import DiscoveryResult
from codeatlas.evidence.schema import Evidence
from codeatlas.knowledge.schema import TechnologyItem
from codeatlas.repository.walker import RepoTree


def detect_infra(tree: RepoTree) -> DiscoveryResult:
    result = DiscoveryResult()
    paths = [f.relative_path for f in tree.files if not f.excluded]

    dockerfile = next((p for p in paths if p.rsplit("/", 1)[-1] == "Dockerfile" or p.endswith(".Dockerfile")), None)
    compose = next((p for p in paths if p.rsplit("/", 1)[-1] in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")), None)
    if dockerfile:
        result.infra_signals["dockerized"] = True
        result.evidence.append(
            Evidence(
                finding_id="infra:docker",
                source_file=dockerfile,
                excerpt="Dockerfile present",
                **make_evidence_kwargs_static("Dockerfile found in repository."),
            )
        )
    if compose:
        result.infra_signals["docker_compose"] = True
        result.evidence.append(
            Evidence(
                finding_id="infra:docker_compose",
                source_file=compose,
                excerpt="docker-compose file present",
                **make_evidence_kwargs_static("Docker Compose file found in repository."),
            )
        )

    ci_signals = {
        "github_actions": lambda p: p.startswith(".github/workflows/"),
        "gitlab_ci": lambda p: p.rsplit("/", 1)[-1] == ".gitlab-ci.yml",
        "circleci": lambda p: p.startswith(".circleci/"),
        "jenkins": lambda p: p.rsplit("/", 1)[-1] == "Jenkinsfile",
        "azure_pipelines": lambda p: p.rsplit("/", 1)[-1] in ("azure-pipelines.yml", "azure-pipelines.yaml"),
        "travis_ci": lambda p: p.rsplit("/", 1)[-1] == ".travis.yml",
    }
    for key, predicate in ci_signals.items():
        match = next((p for p in paths if predicate(p)), None)
        if match:
            result.infra_signals[key] = True
            result.technology_items.append(TechnologyItem(category="build_tool", name=key.replace("_", " ").title()))
            result.evidence.append(
                Evidence(
                    finding_id=f"infra:ci:{key}",
                    source_file=match,
                    excerpt=f"{match} present",
                    **make_evidence_kwargs_static(f"CI configuration for {key.replace('_', ' ')} found."),
                )
            )

    terraform_files = [p for p in paths if p.endswith(".tf")]
    if terraform_files:
        result.infra_signals["terraform"] = True
        result.evidence.append(
            Evidence(
                finding_id="infra:terraform",
                source_file=terraform_files[0],
                excerpt=f"{len(terraform_files)} .tf file(s) present",
                **make_evidence_kwargs_static("Terraform configuration files found."),
            )
        )

    k8s_manifests = [
        p for p in paths
        if p.endswith((".yaml", ".yml")) and any(seg in p.lower() for seg in ("k8s", "kubernetes", "helm"))
    ]
    if k8s_manifests:
        result.infra_signals["kubernetes"] = True
        result.notes.append(f"Possible Kubernetes manifests found ({len(k8s_manifests)}); not deeply parsed in V1.")

    return result
