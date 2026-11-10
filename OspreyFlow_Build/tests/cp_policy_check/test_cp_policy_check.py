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
    pod_spec,
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


def test_the_ingress_routes_each_path_and_admits_each_path_s_service(tmp_path: Path) -> None:
    """Helm's own Ingress for a GOV.UK deployment: `id.<host>/assets/govuk` to the workspace before
    `/` to Keycloak (as Caddy routes it), the named certificate, and the controller admitted to
    both services; the values alone cannot show the template reads them."""
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["appearance"] = {"brand": "govuk"}
    raw["cloud_platform"]["tls_secret"] = "ospreyflow-tls"
    config = tmp_path / "govuk.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    values, _ = render_values(config)
    docs = helm_template(values)
    ingress = next(d for d in docs if d["kind"] == "Ingress")
    assert ingress["spec"]["tls"][0]["secretName"] == "ospreyflow-tls"
    rules = {r["host"]: r["http"]["paths"] for r in ingress["spec"]["rules"]}
    identity = [(p["path"], p["backend"]["service"]["name"])
                for p in rules["id.ospreyflow-dev.apps.example.org"]]  # fmt: skip
    assert identity == [("/assets/govuk", "workspace"), ("/", "keycloak")]
    policy = next(
        d for d in docs
        if d["kind"] == "NetworkPolicy" and d["metadata"]["name"] == "ospreyflow-from-ingress"
    )  # fmt: skip
    admitted = policy["spec"]["podSelector"]["matchExpressions"][0]["values"]
    assert set(admitted) == {"workspace", "keycloak"}
    assert {p["port"] for p in policy["spec"]["ingress"][0]["ports"]} == {8080}


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
    deny = next(d for d in docs if d["metadata"]["name"] == "default.ospreyflow-deny-egress")
    deny["spec"]["selector"] = "app.kubernetes.io/name == 'api'"
    assert {v.rule for v in check_manifests(docs, registry)} == {"no-deny-egress"}


# ---- red, each branch of the check alone (reviewer point 2) -----------------------------------
# Planted in Helm's own output, the shape a template edit would emit, so each fires alone; each is
# asserted by its own branch's words, so a test is not satisfied by a neighbouring branch.


def _helm(development: tuple[dict[str, Any], str]) -> tuple[list[dict[str, Any]], str]:
    values, registry = development
    return helm_template(yaml.safe_dump(values)), registry


def _doc(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def _found(docs: list[dict[str, Any]], registry: str) -> list[tuple[str, str]]:
    return [(v.rule, v.detail) for v in check_manifests(docs, registry)]


def _api_container(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return _doc(docs, "Deployment", "api")["spec"]["template"]["spec"]["containers"][0]


def test_privilege_escalation_alone_is_refused(development: tuple[dict[str, Any], str]) -> None:
    docs, registry = _helm(development)
    _api_container(docs)["securityContext"]["allowPrivilegeEscalation"] = True
    assert _found(docs, registry) == [("privileged", "allowPrivilegeEscalation is not false")]


def test_a_capability_added_alone_is_refused(development: tuple[dict[str, Any], str]) -> None:
    docs, registry = _helm(development)
    _api_container(docs)["securityContext"]["capabilities"]["add"] = ["NET_ADMIN"]
    [(rule, detail)] = _found(docs, registry)
    assert rule == "privileged" and detail.startswith("capabilities are not all dropped")


def test_capabilities_not_dropped_alone_is_refused(development: tuple[dict[str, Any], str]) -> None:
    docs, registry = _helm(development)
    _api_container(docs)["securityContext"]["capabilities"] = {"drop": ["NET_RAW"]}
    [(rule, detail)] = _found(docs, registry)
    assert rule == "privileged" and detail.startswith("capabilities are not all dropped")


def test_run_as_non_root_false_with_a_numeric_user_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    docs, registry = _helm(development)
    _api_container(docs)["securityContext"]["runAsNonRoot"] = False
    assert _found(docs, registry) == [("root", "runAsNonRoot is not true")]


def test_an_init_container_is_held_to_the_rules(development: tuple[dict[str, Any], str]) -> None:
    docs, registry = _helm(development)
    keycloak = next(d for d in docs if d["metadata"]["name"] == "keycloak" and pod_spec(d))
    init = pod_spec(keycloak)["initContainers"][0]  # type: ignore[index]
    init["securityContext"]["allowPrivilegeEscalation"] = True
    found = check_manifests(docs, registry)
    assert [(v.rule, v.where.endswith(init["name"])) for v in found] == [("privileged", True)]


def test_a_container_port_below_1024_alone_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    docs, registry = _helm(development)
    _api_container(docs)["ports"] = [{"containerPort": 80}]
    assert _found(docs, registry) == [("low-port", "containerPort 80")]


def test_a_service_port_below_1024_alone_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    docs, registry = _helm(development)
    _doc(docs, "Service", "api")["spec"]["ports"][0]["port"] = 443
    assert _found(docs, registry) == [("low-port", "port 443")]


def test_a_service_target_port_below_1024_alone_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    docs, registry = _helm(development)
    _doc(docs, "Service", "api")["spec"]["ports"][0]["targetPort"] = 80
    assert _found(docs, registry) == [("low-port", "targetPort 80")]


def test_a_stateful_set_s_read_write_many_claim_template_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    docs, registry = _helm(development)
    arcadedb = _doc(docs, "StatefulSet", "arcadedb")
    claim = arcadedb["spec"]["volumeClaimTemplates"][0]
    claim["spec"]["accessModes"] = ["ReadWriteMany"]
    assert _found(docs, registry) == [("rwx", f"claim {claim['metadata']['name']}")]


def test_main_fails_on_a_planted_fault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.cp_policy_check as check

    bad = tmp_path / "Dockerfile"
    bad.write_text("FROM nginx:1.30-alpine\nUSER nginx\n", encoding="utf-8")
    monkeypatch.setattr(check, "our_dockerfiles", lambda: [*our_dockerfiles(), bad])
    assert main(["--config", str(FIXTURES / "development.yaml")]) == 1
