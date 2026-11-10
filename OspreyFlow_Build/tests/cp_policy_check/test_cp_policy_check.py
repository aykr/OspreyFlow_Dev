"""`make cp-policy-check` (`spec/06_DECISIONS.md` ADR-148 decision 14), shown green on the
profile's render and red on each planted fault (rule 15).

**Each fault is planted where it would really arise** (rule 15's second paragraph): in the values
the chart reads, then templated by Helm, so the check sees the manifest Helm emits, not a
hand-written approximation. Two faults the chart cannot express from its values (a `hostPath`, a
privileged container) are planted into Helm's own output, the shape a template edit would emit.
Helm and kubeconform run as their pinned images, so this needs Docker, as `test_helm_chart.py` does.
"""

from __future__ import annotations

import copy
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from tools.cp_policy_check import (
    FIXTURES,
    check_dockerfiles,
    check_manifests,
    helm_template,
    main,
    our_dockerfiles,
    render_values,
)

KUBECONFORM = "ghcr.io/yannh/kubeconform:v0.6.7"


@pytest.fixture(scope="module", params=["development", "production"])
def rendered(request: pytest.FixtureRequest) -> tuple[dict[str, Any], str]:
    values, registry = render_values(FIXTURES / f"{request.param}.yaml")
    return yaml.safe_load(values), registry


@pytest.fixture(scope="module")
def development() -> tuple[dict[str, Any], str]:
    values, registry = render_values(FIXTURES / "development.yaml")
    return yaml.safe_load(values), registry


def _rules(values: dict[str, Any], registry: str) -> set[str]:
    return {v.rule for v in check_manifests(helm_template(yaml.safe_dump(values)), registry)}


def _workload(values: dict[str, Any], name: str) -> dict[str, Any]:
    return next(w for w in values["workloads"] if w["name"] == name)


# ---- green -----------------------------------------------------------------------------------


def test_the_render_passes(rendered: tuple[dict[str, Any], str]) -> None:
    values, registry = rendered
    docs = helm_template(yaml.safe_dump(values))
    assert check_manifests(docs, registry) == []
    kinds = {d["kind"] for d in docs}
    assert {"Ingress", "PodDisruptionBudget", "StatefulSet"} <= kinds


def test_the_render_is_valid_kubernetes(rendered: tuple[dict[str, Any], str]) -> None:
    values, _ = rendered
    docs = helm_template(yaml.safe_dump(values))
    done = subprocess.run(
        ["docker", "run", "--rm", "-i", KUBECONFORM, "-strict", "-summary",
         "-ignore-missing-schemas",
         "-kubernetes-version", "1.31.0", "-"],
        input=yaml.safe_dump_all(docs), capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    assert re.search(r"Invalid: 0, Errors: 0", done.stdout), done.stdout


def test_our_dockerfiles_pass() -> None:
    assert check_dockerfiles(our_dockerfiles()) == []


def test_main_passes_on_the_fixtures() -> None:
    assert main([]) == 0


# ---- red, each on its own planted fault --------------------------------------------------------


def test_a_root_pod_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = copy.deepcopy(development)
    values.pop("podSecurity")  # the chart then sets no user and no runAsNonRoot
    assert {"root", "named-uid", "privileged"} <= _rules(values, registry)


def test_uid_zero_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = copy.deepcopy(development)
    values["podSecurity"] = {"user": 0, "group": 0}
    assert "root" in _rules(values, registry)


def test_a_named_uid_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = copy.deepcopy(development)
    values["podSecurity"] = {"user": None, "group": 10001}  # the image's own user decides
    assert "named-uid" in _rules(values, registry)


def test_a_named_user_in_a_dockerfile_is_refused(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.12-slim\nRUN useradd --uid 10001 osprey\nuser osprey\n", encoding="utf-8"
    )
    assert [v.rule for v in check_dockerfiles([dockerfile])] == ["named-uid"]


def test_a_read_write_many_claim_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = copy.deepcopy(development)
    values["storage"]["sharedAccessMode"] = "ReadWriteMany"
    assert _rules(values, registry) == {"rwx"}


def test_a_host_path_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = development
    docs = helm_template(yaml.safe_dump(values))
    api = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "api")
    api["spec"]["template"]["spec"].setdefault("volumes", []).append(
        {"name": "node", "hostPath": {"path": "/var/lib", "type": "Directory"}}
    )
    assert {v.rule for v in check_manifests(docs, registry)} == {"hostPath"}


def test_a_privileged_container_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = development
    docs = helm_template(yaml.safe_dump(values))
    api = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "api")
    api["spec"]["template"]["spec"]["containers"][0]["securityContext"]["privileged"] = True
    assert {v.rule for v in check_manifests(docs, registry)} == {"privileged"}


def test_a_port_below_1024_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = copy.deepcopy(development)
    _workload(values, "workspace")["ports"] = [{"port": 80, "target": 80}]
    assert _rules(values, registry) == {"low-port"}


def test_a_foreign_registry_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = copy.deepcopy(development)
    arcadedb = _workload(values, "arcadedb")
    arcadedb["image"] = "docker.io/" + arcadedb["image"].removeprefix(registry + "/")
    assert _rules(values, registry) == {"foreign-registry"}


def test_a_namespace_without_the_deny_egress_policy_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    values, registry = copy.deepcopy(development)
    values.pop("egress")
    assert _rules(values, registry) == {"no-deny-egress"}


def test_a_deny_policy_that_does_not_cover_every_pod_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    values, registry = development
    docs = helm_template(yaml.safe_dump(values))
    deny = next(d for d in docs if d["metadata"]["name"] == "ospreyflow-deny-egress")
    deny["spec"]["selector"] = "app.kubernetes.io/name == 'api'"
    assert {v.rule for v in check_manifests(docs, registry)} == {"no-deny-egress"}


def test_main_fails_on_a_planted_fault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.cp_policy_check as check

    bad = tmp_path / "Dockerfile"
    bad.write_text("FROM nginx:1.30-alpine\nUSER nginx\n", encoding="utf-8")
    monkeypatch.setattr(check, "our_dockerfiles", lambda: [*our_dockerfiles(), bad])
    assert main(["--config", str(FIXTURES / "development.yaml")]) == 1
