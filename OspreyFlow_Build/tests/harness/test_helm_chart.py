"""The chart `deploy/helm/ospreyflow` holds 05 §3b's promises (ADR-114 Amendment 10 point 5):
rendered with `helm template` from the values `harness.render` writes, valid against Kubernetes'
own schemas, no Secret in it, nothing published but the proxy, every store on volumes of its own.

Helm and kubeconform run as their pinned images, so the check needs Docker and nothing else —
CI's runners have it. Without Docker this fails rather than skipping: a skipped chart check proves
nothing about the chart.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.render import REPO_ROOT, render

from tests.harness.test_cluster_render import AWS, AZURE, _resolver, cluster_config

CHART = REPO_ROOT / "deploy" / "helm" / "ospreyflow"
HELM = "alpine/helm:3.16.3"
KUBECONFORM = "ghcr.io/yannh/kubeconform:v0.6.7"


def _docker(*args: str, stdin: str | None = None) -> str:
    done = subprocess.run(
        ["docker", "run", "--rm", "-i", *args], input=stdin, capture_output=True, text=True,
        timeout=300, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr or done.stdout
    return done.stdout


def helm_template(values: str | None) -> str:
    mounts = ["-v", f"{CHART}:/chart:ro"]
    if values is None:
        return _docker(*mounts, HELM, "template", "ospreyflow", "/chart", "--namespace", "osprey")
    return _docker(
        *mounts, HELM, "template", "ospreyflow", "/chart", "--namespace", "osprey", "-f", "-",
        stdin=values,
    )  # fmt: skip


def manifests_for(external: dict[str, Any]) -> list[dict[str, Any]]:
    values = render(cluster_config(external), resolver=_resolver).artefacts["values.yaml"]
    return [doc for doc in yaml.safe_load_all(helm_template(values)) if doc]


@pytest.fixture(scope="module", params=["aws", "azure"])
def manifests(request: pytest.FixtureRequest) -> list[dict[str, Any]]:
    return manifests_for(AWS if request.param == "aws" else AZURE)


def _of(manifests: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [m for m in manifests if m["kind"] == kind]


def _pod_specs(manifests: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (m["metadata"]["name"], m["spec"]["template"])
        for m in manifests
        if m["kind"] in {"Deployment", "StatefulSet", "Job"}
    ]


def test_the_chart_is_valid_kubernetes(manifests: list[dict[str, Any]]) -> None:
    text = yaml.safe_dump_all(manifests)
    said = _docker(
        KUBECONFORM, "-strict", "-summary", "-kubernetes-version", "1.31.0", "-", stdin=text
    )
    found = re.search(r"(\d+) resources found .* Valid: (\d+), Invalid: 0, Errors: 0", said)
    assert found and found[1] == found[2] == str(len(manifests)), said


def test_the_chart_holds_no_secret(manifests: list[dict[str, Any]]) -> None:
    assert not _of(manifests, "Secret")
    for _, template in _pod_specs(manifests):
        for container in [*template["spec"].get("initContainers", []),
                          *template["spec"]["containers"]]:  # fmt: skip
            for entry in container.get("env", []):
                if re.search("(PASSWORD|SECRET|_TOKEN)$", entry["name"]):
                    assert "value" not in entry or "$(" in entry["value"], entry


def test_nothing_but_the_proxy_is_published(manifests: list[dict[str, Any]]) -> None:
    published = [s["metadata"]["name"] for s in _of(manifests, "Service")
                 if s["spec"].get("type") in {"LoadBalancer", "NodePort"}]  # fmt: skip
    assert published == ["proxy"]
    public = [name for name, t in _pod_specs(manifests)
              if t["metadata"]["labels"].get("ospreyflow.io/public") == "true"]  # fmt: skip
    assert public == ["proxy"]
    policies = {p["metadata"]["name"]: p["spec"] for p in _of(manifests, "NetworkPolicy")}
    internal = policies["ospreyflow-internal"]
    assert internal["policyTypes"] == ["Ingress", "Egress"]
    assert internal["ingress"] == [
        {"from": [{"podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "ospreyflow"}}}]}
    ]


def test_only_what_needs_a_route_out_has_one(manifests: list[dict[str, Any]]) -> None:
    reaching = {t["metadata"]["labels"]["app.kubernetes.io/name"] for _, t in _pod_specs(manifests)
                if t["metadata"]["labels"].get("ospreyflow.io/egress") == "true"}  # fmt: skip
    for server in ("ollama", "whisper", "arcadedb", "clickhouse", "litellm", "ner", "workspace"):
        assert server not in reaching, server
    assert {"ollama-models", "whisper-models", "api", "worker", "keycloak", "proxy"} <= reaching


def test_every_store_has_its_volumes_and_its_peers_by_name(
    manifests: list[dict[str, Any]],
) -> None:
    services = {s["metadata"]["name"]: s["spec"] for s in _of(manifests, "Service")}
    for store in _of(manifests, "StatefulSet"):
        name, spec = store["metadata"]["name"], store["spec"]
        headless = services[spec["serviceName"]]
        assert headless["clusterIP"] == "None" and headless["publishNotReadyAddresses"], name
        assert spec["podManagementPolicy"] == "Parallel", name
        if name != "keycloak":  # its data is in the managed Postgres
            assert spec["volumeClaimTemplates"], name


def test_every_service_selects_a_workload(manifests: list[dict[str, Any]]) -> None:
    pods = [t["metadata"]["labels"] for _, t in _pod_specs(manifests)]
    for service in _of(manifests, "Service"):
        selector = service["spec"]["selector"]
        assert any(selector.items() <= labels.items() for labels in pods), service["metadata"]


def test_a_variable_is_defined_before_it_is_named(manifests: list[dict[str, Any]]) -> None:
    """Kubernetes expands `$(NAME)` only from variables defined earlier in the container's own
    list; a later or missing one stays the literal text, silently (a password of `$(X)`)."""
    for name, template in _pod_specs(manifests):
        for container in [*template["spec"].get("initContainers", []),
                          *template["spec"]["containers"]]:  # fmt: skip
            defined: set[str] = set()
            for entry in container.get("env", []):
                for used in re.findall(r"(?<!\$)\$\(([A-Za-z_][A-Za-z0-9_]*)\)",
                                       entry.get("value", "")):  # fmt: skip
                    assert used in defined, (name, entry["name"], used)
                defined.add(entry["name"])
            for arg in [*container.get("command", []), *container.get("args", [])]:
                for used in re.findall(r"(?<!\$)\$\(([A-Za-z_][A-Za-z0-9_]*)\)", arg):
                    assert used in defined, (name, used)


def test_the_files_fit_a_configmap(manifests: list[dict[str, Any]]) -> None:
    for config_map in _of(manifests, "ConfigMap"):
        assert len(yaml.safe_dump(config_map).encode()) < 1_000_000, config_map["metadata"]


def test_the_chart_on_its_own_defaults_creates_nothing() -> None:
    assert [doc for doc in yaml.safe_load_all(helm_template(None)) if doc] == []


def test_the_chart_ignores_files_the_sync_tool_adds() -> None:
    assert "Icon?" in (CHART / ".helmignore").read_text(encoding="utf-8").splitlines()


def test_the_chart_is_where_the_values_say() -> None:
    assert (CHART / "Chart.yaml").is_file()
    assert Path(CHART / "templates" / "workloads.yaml").is_file()
