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
import dataclasses
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.cloud_platform.settings import load_platform
from tools.cp_policy_check import (
    FIXTURES,
    Violation,
    check_dockerfiles,
    helm_template,
    main,
    our_dockerfiles,
    pod_spec,
    render_values,
)
from tools.cp_policy_check import check_manifests as _check_manifests

KUBECONFORM = "ghcr.io/yannh/kubeconform:v0.6.7"
#: The fixtures' platform's ingress controller's namespace, the one other namespace admitted.
CONTROLLER = load_platform("client").ingress.controller_namespace


def check_manifests(docs: list[dict[str, Any]], registry: str) -> list[Violation]:
    return _check_manifests(docs, registry, controller_namespace=CONTROLLER)


@pytest.fixture(scope="module", params=["development", "production", "poc"])
def rendered(request: pytest.FixtureRequest) -> tuple[dict[str, Any], str]:
    values, registry = render_values(FIXTURES / f"{request.param}.yaml")
    return yaml.safe_load(values), registry


@pytest.fixture(scope="module", params=["development", "poc"])
def development(request: pytest.FixtureRequest) -> tuple[dict[str, Any], str]:
    """A development namespace's render, in the standard shape and in the poc shape (ADR-148
    Amendment 5): every planted fault is refused in each shape's own render."""
    values, registry = render_values(FIXTURES / f"{request.param}.yaml")
    return yaml.safe_load(values), registry


@pytest.fixture(scope="module")
def poc() -> tuple[dict[str, Any], str]:
    values, registry = render_values(FIXTURES / "poc.yaml")
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
    assert {"Ingress", "StatefulSet"} <= kinds
    # Disruption budgets in the standard shape; none in the poc shape (ADR-148 Amendment 5).
    shape = yaml.safe_load(values["files"]["osprey.yaml"])["cloud_platform"].get("shape")
    assert ("PodDisruptionBudget" in kinds) is (shape != "poc")


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


def test_a_user_other_than_10001_is_refused(development: tuple[dict[str, Any], str]) -> None:
    """ADR-148 decision 3: every rendered pod runs as 10001, not merely as someone other than
    root, so a pod given another numeric user is held to it too (reviewer point 16)."""
    values, registry = copy.deepcopy(development)
    values["podSecurity"] = {"user": 1000, "group": 1000}
    assert ("other-uid", "runAsUser is 1000, not 10001") in {
        (v.rule, v.detail) for v in check_manifests(helm_template(yaml.safe_dump(values)), registry)
    }


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
    # With the egress rows gone, each workload's own ingress goes too (Amendment 5 point 23), so
    # the internal policy admits every pod of ours again, which is refused as well.
    assert _rules(values, registry) == {"no-deny-egress", "wide-ingress"}


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


def test_a_group_other_than_10001_is_refused(development: tuple[dict[str, Any], str]) -> None:
    """ADR-148 Amendment 1 item 4: every pod runs as 10001:10001, the group as well as the user;
    planted in the values the chart reads, as a deployment's own settings would carry it."""
    values, registry = copy.deepcopy(development)
    values["podSecurity"] = {"user": 10001, "group": 1000}
    docs = helm_template(yaml.safe_dump(values))
    found = {(v.rule, v.detail) for v in check_manifests(docs, registry)}
    assert ("other-gid", "runAsGroup is 1000, not 10001") in found
    assert ("other-gid", "fsGroup is 1000, not 10001") in found
    assert {rule for rule, _ in found} == {"other-gid"}


def test_a_container_s_own_group_alone_is_refused(development: tuple[dict[str, Any], str]) -> None:
    docs, registry = _helm(development)
    _api_container(docs)["securityContext"]["runAsGroup"] = 0
    assert _found(docs, registry) == [("other-gid", "runAsGroup is 0, not 10001")]


def test_a_supplementary_group_outside_its_allowance_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    """Group 0 is Keycloak's alone (its image is built for group 0, until P10): the render gives
    it to Keycloak and passes; given to another workload, or another group to Keycloak, refused."""
    values, registry = copy.deepcopy(development)
    assert _workload(values, "keycloak")["supplementalGroups"] == [0]
    _workload(values, "api")["supplementalGroups"] = [0]
    docs = helm_template(yaml.safe_dump(values))
    assert [(v.rule, v.where, v.detail) for v in check_manifests(docs, registry)] == [
        ("supplementary-group", "Deployment/api", "supplementalGroups [0]")
    ]
    values, _ = copy.deepcopy(development)
    _workload(values, "keycloak")["supplementalGroups"] = [0, 4]
    docs = helm_template(yaml.safe_dump(values))
    assert _found(docs, registry) == [("supplementary-group", "supplementalGroups [4]")]


def _job_values(rendered: tuple[dict[str, Any], str]) -> tuple[dict[str, Any], str]:
    """The profile renders no Job today (the cluster's are the model downloads it drops), so one is
    given in the values' `jobs`, as the API's own pod, templated by the chart's `jobs.yaml`. As the
    API's pod, but holding nothing of ours: `migrate` is not one of the pods that may read our
    Secret whole or by key (point 22), nor mount a token (point 24)."""
    values, registry = copy.deepcopy(rendered)
    api = _workload(values, "api")
    env = [e for e in api.get("env", []) if "secret" not in e]
    job = {**api, "name": "migrate", "envFrom": False, "env": env, "automountToken": False}
    job.pop("serviceAccountName", None)
    values["jobs"] = [job]
    return values, registry


def _with_a_job(development: tuple[dict[str, Any], str]) -> tuple[list[dict[str, Any]], str]:
    values, registry = _job_values(development)
    docs = helm_template(yaml.safe_dump(values))
    # The Job alone, unplanted, passes but for having no ingress policy of its own (no Job is
    # rendered on this profile; P9's bring their rows), which `_apart_from_its_ingress` sets apart.
    assert {(v.rule, v.where.split("/")[0]) for v in check_manifests(docs, registry)} <= {
        ("ingress-isolation", "Job")
    }
    return docs, registry


def _a_job(docs: list[dict[str, Any]]) -> dict[str, Any]:
    jobs = [d for d in docs if d["kind"] == "Job"]
    assert len(jobs) == 1, jobs
    return jobs[0]


def test_a_job_s_pod_is_held_to_the_rules(development: tuple[dict[str, Any], str]) -> None:
    """The chart's Jobs (`jobs.yaml`) are pods the check reads: a fault in one alone is refused."""
    docs, registry = _with_a_job(development)
    job = _a_job(docs)
    job["spec"]["template"]["spec"]["containers"][0]["securityContext"]["privileged"] = True
    found = _apart_from_its_ingress(check_manifests(docs, registry), job)
    assert [(v.rule, v.where.split(" ")[0], v.detail) for v in found] == [
        ("privileged", _name_of(job), "privileged: true")
    ]


def test_a_cron_job_s_pod_is_held_to_the_rules(development: tuple[dict[str, Any], str]) -> None:
    """A CronJob's pod sits a level deeper (`jobTemplate.spec.template`); P9's scheduled backup is
    one. Planted as Helm would emit a CronJob made from one of the chart's own Jobs."""
    docs, registry = _with_a_job(development)
    job = _a_job(docs)
    job["spec"]["template"]["spec"]["containers"][0]["securityContext"]["privileged"] = True
    cron = {
        "apiVersion": "batch/v1",
        "kind": "CronJob",
        "metadata": {**job["metadata"], "name": job["metadata"]["name"] + "-nightly"},
        "spec": {"schedule": "0 2 * * *", "jobTemplate": {"spec": job["spec"]}},
    }
    docs = [cron if d is job else d for d in docs]
    found = _apart_from_its_ingress(check_manifests(docs, registry), cron)
    assert [(v.rule, v.where.split(" ")[0], v.detail) for v in found] == [
        ("privileged", _name_of(cron), "privileged: true")
    ]


def _apart_from_its_ingress(found: list[Violation], planted: dict[str, Any]) -> list[Violation]:
    """A planted Job's pod has no ingress policy of its own (the profile renders no Job; P9's
    backups bring theirs with their rows), so it is also refused as one any address may reach:
    that finding is the planted pod's alone, and set apart here."""
    unselected = [v for v in found if v.rule == "ingress-isolation"]
    assert [v.where for v in unselected] == [_name_of(planted)] * len(unselected)
    return [v for v in found if v.rule != "ingress-isolation"]


def _name_of(doc: dict[str, Any]) -> str:
    return f"{doc['kind']}/{doc['metadata']['name']}"


# ---- egress opened by one rule (ADR-148 decision 7; the independent review of P7, item 3) --------
# Planted in the values the render emits (`egress.hosts`, `egress.managedNets`,
# `networkPolicy.openEgress`), then templated, so each fault is the policy Helm would apply.


def _given_to_the_conduit(values: dict[str, Any], host: str) -> None:
    """A host is rendered in the policy of each workload that reaches it (Amendment 5 point 21):
    planted as the render gives one to the Conduit."""
    api = next(w for w in values["egress"]["workloads"] if w["name"] == "api")
    api.setdefault("hosts", []).append(host)


@pytest.mark.parametrize(
    ("net", "why"),
    [
        ("0.0.0.0/0", "0.0.0.0/0 is a default route"),
        ("::/0", "::/0 is a default route"),
        ("10.0.0.0/8", "10.0.0.0/8 is wider than /16"),
        ("2001:db8::/32", "2001:db8::/32 is wider than /48"),
    ],
)
def test_a_host_s_network_that_opens_egress_is_refused(
    development: tuple[dict[str, Any], str], net: str, why: str
) -> None:
    values, registry = copy.deepcopy(development)
    values["egress"]["hosts"].append({"host": "api.example.org", "nets": [net], "ports": [443]})
    _given_to_the_conduit(values, "api.example.org")
    [(rule, detail)] = _found(helm_template(yaml.safe_dump(values)), registry)
    assert rule == "open-egress" and detail.startswith(why)


def test_managed_networks_that_open_egress_are_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    values, registry = copy.deepcopy(development)
    values["egress"]["managedNets"] = ["0.0.0.0/0"]
    found = _found(helm_template(yaml.safe_dump(values)), registry)
    # Refused in the policy of each workload that reads a managed store (Amendment 5 point 21).
    assert found and all(
        rule == "open-egress" and detail.startswith("0.0.0.0/0 is a default route")
        for rule, detail in found
    )


def test_a_platform_s_widest_networks_pass(development: tuple[dict[str, Any], str]) -> None:
    """The cap's own edge: a /16 (the client's shared VPC is one) and a /48 pass."""
    values, registry = copy.deepcopy(development)
    values["egress"]["hosts"].append(
        {"host": "a.example.org", "nets": ["10.1.0.0/16"], "ports": [443]}
    )
    _given_to_the_conduit(values, "a.example.org")
    values["egress"]["hosts"].append(
        {"host": "b.example.org", "nets": ["2001:db8:1::/48"], "ports": [443]}
    )
    _given_to_the_conduit(values, "b.example.org")
    assert _found(helm_template(yaml.safe_dump(values)), registry) == []


def test_an_allow_rule_with_no_destination_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    """Calico's Allow with no destination allows every address; planted as a template edit would
    emit it, in the allow policy before the deny, with its protocol and ports (so `allow-ports` is
    satisfied and only the destination is missing)."""
    docs, registry = _helm(development)
    allow = _doc(docs, "NetworkPolicy", "default.ospreyflow-egress-api")
    allow["spec"]["egress"].append(
        {"action": "Allow", "protocol": "TCP", "destination": {"ports": [443]}}
    )
    [(rule, detail)] = _found(docs, registry)
    assert rule == "open-egress" and detail.startswith("an Allow rule with no destination")


def test_the_open_egress_policy_is_refused(development: tuple[dict[str, Any], str]) -> None:
    """The cluster's open-egress `NetworkPolicy` (`egress: [{}]`), rendered from the values that
    switch it on."""
    values, registry = copy.deepcopy(development)
    values["networkPolicy"]["openEgress"] = True
    [(rule, detail)] = _found(helm_template(yaml.safe_dump(values)), registry)
    assert rule == "open-egress" and detail.startswith("an egress rule to everywhere")


@pytest.mark.parametrize(
    ("cidr", "why"),
    [
        ("0.0.0.0/0", "0.0.0.0/0 is a default route"),
        ("::/0", "::/0 is a default route"),
        ("10.0.0.0/8", "10.0.0.0/8 is wider than /16"),
        ("2001:db8::/32", "2001:db8::/32 is wider than /48"),
    ],
)
def test_a_kubernetes_egress_address_block_that_opens_egress_is_refused(
    development: tuple[dict[str, Any], str], cidr: str, why: str
) -> None:
    """A Kubernetes `NetworkPolicy` egress rule whose `to` is an `ipBlock` (the round-2 review's
    first unproven branch). Planted as the cluster's chart emits its internal policy (not rendered
    on this profile), with a second `to` rule beside its pods rule: it has a `to`, so only the
    address-block branch can see it."""
    docs, registry = _helm(development)
    docs.append(_egress_policy([{"to": [{"ipBlock": {"cidr": cidr}}]}]))
    [(rule, where, detail)] = _isolation(docs, registry)
    assert (rule, where) == ("open-egress", "NetworkPolicy/ospreyflow-internal")
    assert detail.startswith(why)


def _egress_policy(extra: list[dict[str, Any]]) -> dict[str, Any]:
    """The cluster's internal policy's egress half, every pod of ours to every pod of ours, with
    `extra` rules beside it (Kubernetes' egress, which the deny's order leaves undecided here)."""
    ours = {"podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "ospreyflow"}}}
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "ospreyflow-internal"},
        "spec": {**ours, "policyTypes": ["Egress"], "egress": [{"to": [ours]}, *extra]},
    }


def test_a_kubernetes_egress_address_block_within_the_cap_passes(
    development: tuple[dict[str, Any], str],
) -> None:
    """The branch's other side: a /16 address block is not refused."""
    docs, registry = _helm(development)
    docs.append(_egress_policy([{"to": [{"ipBlock": {"cidr": "10.1.0.0/16"}}]}]))
    assert _isolation(docs, registry) == []


# ---- other tenants (the independent review of P7, item 4) ------------------------------------


def _isolation(docs: list[dict[str, Any]], registry: str) -> list[tuple[str, str, str]]:
    return [(v.rule, v.where, v.detail) for v in check_manifests(docs, registry)]


def test_a_dropped_internal_policy_leaves_pods_open_and_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    docs, registry = _helm(development)
    # Each workload's own ingress policy (Amendment 5 point 23); the Conduit's dropped.
    docs = [d for d in docs if (d.get("metadata") or {}).get("name") != "ospreyflow-ingress-api"]
    found = _isolation(docs, registry)
    assert {rule for rule, _, _ in found} == {"ingress-isolation"}
    # The doors stay selected by the controller's policy; every other pod is left open.
    assert ("ingress-isolation", "Deployment/api",
            "no ingress policy selects its pods, so any address may reach them") in found  # fmt: skip
    assert not [w for _, w, _ in found if w in {"Deployment/workspace", "StatefulSet/keycloak"}]


def test_a_widened_ingress_policy_is_refused(development: tuple[dict[str, Any], str]) -> None:
    """Planted three ways a template edit would emit: the controller's policy admitting every
    namespace, the internal one admitting another namespace, and an address block."""
    docs, registry = _helm(development)
    _doc(docs, "NetworkPolicy", "ospreyflow-from-ingress")["spec"]["ingress"][0]["from"] = [
        {"namespaceSelector": {}}
    ]
    [(rule, where, detail)] = _isolation(docs, registry)
    assert (rule, where) == ("ingress-isolation", "NetworkPolicy/ospreyflow-from-ingress")
    assert detail.startswith("admits namespaces all")

    docs, registry = _helm(development)
    internal = _doc(docs, "NetworkPolicy", "ospreyflow-ingress-api")
    internal["spec"]["ingress"][0]["from"].append(
        {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "other-tenant"}}}
    )
    [(rule, where, _)] = _isolation(docs, registry)
    assert (rule, where) == ("ingress-isolation", "NetworkPolicy/ospreyflow-ingress-api")

    docs, registry = _helm(development)
    internal = _doc(docs, "NetworkPolicy", "ospreyflow-ingress-api")
    internal["spec"]["ingress"][0]["from"].append({"ipBlock": {"cidr": "10.0.0.0/8"}})
    [(rule, where, detail)] = _isolation(docs, registry)
    assert (rule, detail) == ("ingress-isolation", "admits {'cidr': '10.0.0.0/8'}")


def test_an_ingress_controller_namespace_not_the_platform_s_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    """Planted in the values the chart reads: the Ingress's policy admitting a namespace that is
    not the platform's controller's (another tenant's)."""
    values, registry = copy.deepcopy(development)
    values["ingress"]["controllerNamespace"] = "other-tenant"
    [(rule, where, detail)] = _isolation(helm_template(yaml.safe_dump(values)), registry)
    assert (rule, where) == ("ingress-isolation", "NetworkPolicy/ospreyflow-from-ingress")
    assert "not the ingress controller's (ingress-controllers) alone" in detail


def test_the_public_policy_admitting_every_address_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    """Without the platform's Ingress the chart renders the cluster's `ospreyflow-public` (every
    source); the render never does, and the check refuses it if it is."""
    values, registry = copy.deepcopy(development)
    values["ingress"]["enabled"] = False
    found = _isolation(helm_template(yaml.safe_dump(values)), registry)
    assert ("ingress-isolation", "NetworkPolicy/ospreyflow-public") in {(r, w) for r, w, _ in found}


def _with_calico_ingress(docs: list[dict[str, Any]], source: dict[str, Any]) -> None:
    """The allow policy given Calico ingress, as a template edit would emit it: `Ingress` added to
    its types and one Allow rule from `source`."""
    allow = _doc(docs, "NetworkPolicy", "default.ospreyflow-egress-api")
    allow["spec"]["types"] = ["Egress", "Ingress"]
    allow["spec"]["ingress"] = [{"action": "Allow", "protocol": "TCP", "source": source}]


@pytest.mark.parametrize(
    "source",
    [
        {"selector": "all()", "namespaceSelector": "all()"},  # every namespace's pods
        {"nets": ["10.0.0.0/8"]},  # addresses
        {},  # every source
    ],
    ids=["another-namespace", "nets", "no-source"],
)
def test_a_calico_ingress_allow_beyond_a_selector_is_refused(
    development: tuple[dict[str, Any], str], source: dict[str, Any]
) -> None:
    """A Calico ingress Allow whose source is more than a selector (the round-2 review's second
    unproven branch). The namespace's Kubernetes policies still select every pod, so only the
    Calico branch can see it."""
    docs, registry = _helm(development)
    _with_calico_ingress(docs, source)
    # `all()` is a selector this check cannot narrow as well (`unreadable-selector`), set apart.
    [(rule, where, detail)] = [f for f in _isolation(docs, registry)
                               if f[0] != "unreadable-selector"]  # fmt: skip
    assert (rule, where) == ("ingress-isolation", "NetworkPolicy/default.ospreyflow-egress-api")
    assert detail.startswith("a Calico rule admitting beyond the namespace's own pods")


def test_a_calico_ingress_allow_in_a_policy_with_no_types_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    """Calico gives a policy with no `types` Ingress unless it has egress rules alone, so ingress
    rules without `types` are applied (the round-2 self-review, point 2). Planted as a new Calico
    policy a template might emit, ingress rules and no `types`."""
    docs, registry = _helm(development)
    allow = copy.deepcopy(_doc(docs, "NetworkPolicy", "default.ospreyflow-egress-api"))
    allow["metadata"]["name"] = "default.ospreyflow-allow-ingress"
    allow["spec"] = {
        "tier": "default", "order": 100, "selector": "all()",
        "ingress": [{"action": "Allow", "source": {"nets": ["10.0.0.0/8"]}}],
    }  # fmt: skip
    docs.append(allow)
    [(rule, where, detail)] = _isolation(docs, registry)
    assert (rule, where) == ("ingress-isolation", "NetworkPolicy/default.ospreyflow-allow-ingress")
    assert detail.startswith("a Calico rule admitting beyond the namespace's own pods")


def test_a_calico_ingress_allow_from_a_selector_alone_passes(
    development: tuple[dict[str, Any], str],
) -> None:
    """The branch's other side: a source of a selector alone (this namespace's pods, by name)
    passes."""
    docs, registry = _helm(development)
    _with_calico_ingress(docs, {"selector": "app.kubernetes.io/name == 'workspace'"})
    assert _isolation(docs, registry) == []


# ---- resources and the volumes' group (the independent review of P7, items 8 and 11) ------------


def test_a_container_without_resources_is_refused(development: tuple[dict[str, Any], str]) -> None:
    values, registry = copy.deepcopy(development)
    _workload(values, "arcadedb").pop("resources")
    keycloak = _workload(values, "keycloak")
    keycloak["initContainers"][0]["resources"] = {"requests": {"cpu": "100m"}}
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.where, v.detail) for v in found] == [
        ("no-resources", "StatefulSet/arcadedb container arcadedb",
         "no requests.cpu, requests.memory, limits.memory"),
        ("no-resources", "StatefulSet/keycloak container keycloak-db",
         "no requests.memory, limits.memory"),
    ]  # fmt: skip


def test_a_volume_walk_at_every_start_is_refused(development: tuple[dict[str, Any], str]) -> None:
    """`fsGroup` without `fsGroupChangePolicy: OnRootMismatch` re-owns every file of a store's claim
    at each start; planted as the chart's pod spec emitted it before the policy was added."""
    docs, registry = _helm(development)
    arcadedb = _doc(docs, "StatefulSet", "arcadedb")
    assert pod_spec(arcadedb)["securityContext"]["fsGroupChangePolicy"] == "OnRootMismatch"  # type: ignore[index]
    del pod_spec(arcadedb)["securityContext"]["fsGroupChangePolicy"]  # type: ignore[index]
    [(rule, detail)] = _found(docs, registry)
    assert rule == "fs-group-walk" and detail.startswith("fsGroup with no fsGroupChangePolicy")


def test_a_configuration_of_another_profile_is_refused_in_words(tmp_path: Path) -> None:
    config = tmp_path / "osprey.yaml"
    config.write_text("profile: local-lite\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="profile: local-lite, and `make cp-policy-check` checks"):
        render_values(config)


def test_main_fails_on_a_planted_fault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.cp_policy_check as check

    bad = tmp_path / "Dockerfile"
    bad.write_text("FROM nginx:1.30-alpine\nUSER nginx\n", encoding="utf-8")
    monkeypatch.setattr(check, "our_dockerfiles", lambda: [*our_dockerfiles(), bad])
    assert main(["--config", str(FIXTURES / "development.yaml")]) == 1


# ---- the poc shape's own claim (ADR-148 Amendment 5) -----------------------------------------


def test_the_poc_shape_s_own_claim_is_rendered_and_mounted(
    poc: tuple[dict[str, Any], str],
) -> None:
    """Helm's own output: `ospreyflow-ingest`, ReadWriteOnce on the platform's class and kept on
    uninstall, mounted by the Conduit at the Ingest root, and no Keeper StatefulSet or disruption
    budget."""
    docs, registry = _helm(poc)
    claim = _doc(docs, "PersistentVolumeClaim", "ospreyflow-ingest")
    assert claim["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert claim["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    spec = pod_spec(_doc(docs, "Deployment", "api"))
    assert spec is not None
    volumes = {v["name"]: v for v in spec["volumes"]}
    assert volumes["claim-ingest"]["persistentVolumeClaim"]["claimName"] == "ospreyflow-ingest"
    mounts = {m["mountPath"]: m["name"] for m in spec["containers"][0]["volumeMounts"]}
    assert mounts["/var/lib/osprey/ingest"] == "claim-ingest"
    assert mounts["/var/lib/osprey/data"] == "shared"
    assert not [d for d in docs if d["kind"] == "PodDisruptionBudget"]
    assert not [d for d in docs if d["metadata"]["name"] == "clickhouse-keeper"]
    assert _found(docs, registry) == []


def test_the_poc_shape_s_own_claim_read_write_many_is_refused(
    poc: tuple[dict[str, Any], str],
) -> None:
    """Planted in Helm's own output: the Ingest root's claim alone made ReadWriteMany."""
    docs, registry = _helm(poc)
    _doc(docs, "PersistentVolumeClaim", "ospreyflow-ingest")["spec"]["accessModes"] = [
        "ReadWriteMany"
    ]
    assert _found(docs, registry) == [("rwx", "accessModes ReadWriteMany")]


def test_a_poc_container_without_a_cpu_limit_is_refused(
    poc: tuple[dict[str, Any], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The self-review of P7b, point 15: `make cp-policy-check` itself holds the poc shape's CPU
    limits, planted in Helm's own output and found through `check`, the path `main` takes; the
    standard shape names none and is not held to it."""
    import tools.cp_policy_check as cp

    docs, _ = _helm(poc)
    _api_container(docs)["resources"]["limits"].pop("cpu")
    monkeypatch.setattr(cp, "helm_template", lambda *_a, **_k: docs)
    target = cp.render(FIXTURES / "poc.yaml")
    assert target.shape == "poc"
    _, found = cp.check(target)
    assert [(v.rule, v.where) for v in found] == [("no-cpu-limit", "Deployment/api/api")]
    standard = cp.render(FIXTURES / "development.yaml")
    assert standard.shape == "standard"
    _, found = cp.check(standard)
    assert "no-cpu-limit" not in {v.rule for v in found}


# ---- the service account's token (Amendment 5 point 24) ----------------------------------------


@pytest.mark.parametrize("workload", ["workspace", "ner", "superset", "keycloak", "arcadedb",
                                      "clickhouse", "litellm"])  # fmt: skip
def test_a_token_mounted_where_no_kubernetes_api_is_called_is_refused(
    rendered: tuple[dict[str, Any], str], workload: str
) -> None:
    """The shape a render that forgets the setting gives: no `automountToken`, so the chart writes
    nothing and Kubernetes mounts the token by default. The gateway is here too: without Bedrock it
    has no account of its own."""
    values, registry = copy.deepcopy(rendered)
    pod = next((w for w in values["workloads"] if w["name"] == workload), None)
    if pod is None:
        pytest.skip(f"{workload} is not rendered here")
    assert pod.pop("automountToken") is False
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.where.split("/")[1]) for v in found] == [("token", workload)]


def test_a_token_in_a_job_is_refused(rendered: tuple[dict[str, Any], str]) -> None:
    """A Job by its pod's name (its own name carries a hash of its steps)."""
    values, registry = _job_values(rendered)
    docs = helm_template(yaml.safe_dump(values))
    assert not [v for v in check_manifests(docs, registry) if v.rule == "token"]
    values["jobs"][0]["automountToken"] = True
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.where.split("/")[0]) for v in found if v.rule != "ingress-isolation"] == [
        ("token", "Job")
    ]


def test_the_irsa_pods_mount_their_tokens_and_pass(rendered: tuple[dict[str, Any], str]) -> None:
    values, registry = rendered
    docs = helm_template(yaml.safe_dump(values))
    specs = {d["metadata"]["name"]: pod_spec(d) for d in docs if d["kind"] == "Deployment"}
    for name in {"api", "worker", "report-sync"} & set(specs):
        assert specs[name]["automountServiceAccountToken"] is True, name
        assert specs[name]["serviceAccountName"], name
    assert specs["workspace"]["automountServiceAccountToken"] is False
    # An IRSA pod that lost its account is refused, though named as one that may hold a token.
    values = copy.deepcopy(values)
    api = next(w for w in values["workloads"] if w["name"] == "api")
    api.pop("serviceAccountName")
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.where) for v in found] == [("token", "Deployment/api")]


# ---- a key of ours by name, default-deny (Amendment 5 point 22) --------------------------------


def _secret_violations(values: dict[str, Any], registry: str) -> list[tuple[str, str]]:
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    return [(v.where, v.detail) for v in found if v.rule == "whole-secret"]


def test_a_new_workload_given_one_key_of_ours_is_refused(
    rendered: tuple[dict[str, Any], str],
) -> None:
    """A workload the check has never heard of (as case-b's Laurium is today), given one key of
    our Secret by name, the way the render names one: refused, with no edit to the check."""
    values, registry = copy.deepcopy(rendered)
    newcomer = copy.deepcopy(_workload(values, "ner"))
    newcomer["name"] = "newcomer"
    values["workloads"].append(newcomer)
    assert _secret_violations(values, registry) == []  # holding none, it passes
    newcomer.setdefault("env", []).append(
        {"name": "ARCADEDB_PASSWORD", "secret": "OSPREY_ARCADEDB_PASSWORD"}
    )
    assert _secret_violations(values, registry) == [
        ("Deployment/newcomer/newcomer", "is given ospreyflow-secrets's OSPREY_ARCADEDB_PASSWORD")
    ]


def test_the_gateway_holds_this_deployment_s_engines_keys_and_no_store_s(
    rendered: tuple[dict[str, Any], str],
) -> None:
    """The gateway holds the keys of this deployment's keyed engines alone, read from its own
    `osprey.yaml` (ADR-135 Amendments 4 and 7): an engine's key it does not have is refused, as a
    store's password is."""
    values, registry = copy.deepcopy(rendered)
    assert _secret_violations(values, registry) == []
    gateway = _workload(values, "litellm")
    gateway["env"].append({"name": "OSPREY_MODEL_KEY_ANTHROPIC",
                           "secret": "OSPREY_MODEL_KEY_ANTHROPIC"})  # fmt: skip
    gateway["env"].append({"name": "ARCADEDB_PASSWORD", "secret": "OSPREY_ARCADEDB_PASSWORD"})
    assert _secret_violations(values, registry) == [
        ("Deployment/litellm/litellm", "is given ospreyflow-secrets's OSPREY_MODEL_KEY_ANTHROPIC"),
        ("Deployment/litellm/litellm", "is given ospreyflow-secrets's OSPREY_ARCADEDB_PASSWORD"),
    ]


def _bedrock() -> tuple[dict[str, Any], str]:
    values, registry = render_values(FIXTURES / "production-bedrock.yaml")
    return yaml.safe_load(values), registry


def test_an_iam_role_engine_s_held_key_is_refused_to_the_gateway() -> None:
    """`production-bedrock` has a keyed engine (openai) and an IAM-role one (bedrock): the gateway
    is given the first's key as rendered and passes; the second's held key, planted beside it in
    the render's own shape, is refused (ADR-135 Amendments 4 and 7)."""
    values, registry = _bedrock()
    gateway = _workload(values, "litellm")
    assert [e for e in gateway["env"] if e.get("secret") == "OSPREY_MODEL_KEY_OPENAI"]
    assert _secret_violations(values, registry) == []
    gateway["env"].append(
        {"name": "OSPREY_MODEL_KEY_BEDROCK", "secret": "OSPREY_MODEL_KEY_BEDROCK"}
    )
    assert _secret_violations(values, registry) == [
        ("Deployment/litellm/litellm", "is given ospreyflow-secrets's OSPREY_MODEL_KEY_BEDROCK")
    ]


# ---- the final review of P7b: the checks as wide as the rules ----------------------------------


def test_the_internal_policy_is_not_rendered_on_a_shared_platform(
    rendered: tuple[dict[str, Any], str],
) -> None:
    """Item 1: egress is Calico's alone here. P7's internal policy's egress half (every pod of ours
    to every pod, and every namespace's DNS) is not rendered: no Kubernetes policy here types
    Egress, so none could decide egress if the deny's order ever let it."""
    values, _ = rendered
    docs = helm_template(yaml.safe_dump(values))
    assert not [d for d in docs if d["metadata"]["name"] == "ospreyflow-internal"]
    assert not [d["metadata"]["name"] for d in docs if d["kind"] == "NetworkPolicy"
                and d["apiVersion"].startswith("networking.k8s.io")
                and "Egress" in (d["spec"].get("policyTypes") or [])]  # fmt: skip


@pytest.mark.parametrize("order", [None, 1000, 1500], ids=["no-order", "at-1000", "after-1000"])
def test_a_deny_that_runs_after_the_kubernetes_policies_is_refused(
    development: tuple[dict[str, Any], str], order: int | None
) -> None:
    """Item 1: the deny counts only when it runs before Calico's place for the Kubernetes
    policies (order 1000); with no order Calico runs it last."""
    docs, registry = _helm(development)
    deny = _doc(docs, "NetworkPolicy", "default.ospreyflow-deny-egress")
    assert deny["spec"]["order"] == 200 and _found(docs, registry) == []
    if order is None:
        deny["spec"].pop("order")
    else:
        deny["spec"]["order"] = order
    assert {rule for rule, _ in _found(docs, registry)} == {"deny-order", "no-deny-egress"}


@pytest.mark.parametrize("shape", ["secret", "secret-items", "projected"])
def test_our_secret_by_volume_is_refused(
    development: tuple[dict[str, Any], str], shape: str
) -> None:
    """Item 2: our Secret mounted, not only read into the environment: a `secret` volume (whole,
    or by its items), or a `projected` volume's `secret` source, on a pod given none."""
    docs, registry = _helm(development)
    spec = pod_spec(_doc(docs, "Deployment", "workspace"))
    assert spec is not None
    items = [{"key": "OSPREY_ARCADEDB_PASSWORD", "path": "arcadedb"}]
    volume = {
        "secret": {"name": "ours", "secret": {"secretName": "ospreyflow-secrets"}},
        "secret-items": {
            "name": "ours", "secret": {"secretName": "ospreyflow-secrets", "items": items}
        },
        "projected": {
            "name": "ours", "projected": {"sources": [{"secret": {"name": "ospreyflow-secrets"}}]}
        },
    }[shape]  # fmt: skip
    spec.setdefault("volumes", []).append(volume)
    detail = (
        "is given ospreyflow-secrets's OSPREY_ARCADEDB_PASSWORD"
        if shape == "secret-items" else "mounts ospreyflow-secrets whole"
    )  # fmt: skip
    assert _found(docs, registry) == [("whole-secret", detail)]


def test_the_secret_s_name_is_the_values() -> None:
    """Item 2: our Secret is whatever the values name it (`secrets.name`), as the chart reads it:
    a deployment naming its own is held to it."""
    from tools.cp_policy_check import check, render

    target = render(FIXTURES / "development.yaml")
    values = yaml.safe_load(target.values)
    values["secrets"]["name"] = "tenant-app-secrets"
    _workload(values, "workspace")["noSecret"] = False  # the chart then gives it ours whole
    _, found = check(dataclasses.replace(target, values=yaml.safe_dump(values)))
    assert [(v.rule, v.detail) for v in found] == [
        ("whole-secret", "reads tenant-app-secrets whole")
    ]


def _calico(docs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return _doc(docs, "NetworkPolicy", name)


def test_an_empty_selector_selects_every_pod_and_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    """Item 4: Calico reads an empty selector as every pod, so a workload's Allows under one are
    every pod's."""
    docs, registry = _helm(development)
    _calico(docs, "default.ospreyflow-egress-api")["spec"]["selector"] = ""
    found = _found(docs, registry)
    assert found and {rule for rule, _ in found} == {"wide-egress"}


def test_a_dns_rule_to_every_namespace_is_refused(
    development: tuple[dict[str, Any], str],
) -> None:
    """Item 4: a destination `namespaceSelector: all()` is no DNS rule: every namespace."""
    docs, registry = _helm(development)
    dns = _calico(docs, "default.ospreyflow-allow-dns")
    dns["spec"]["egress"][0]["destination"]["namespaceSelector"] = "all()"
    assert {rule for rule, _ in _found(docs, registry)} == {"wide-egress", "unreadable-selector"}


def test_a_dns_rule_to_another_namespace_is_not_dns(
    development: tuple[dict[str, Any], str],
) -> None:
    """Item 4: the DNS rule names the platform's DNS's namespace, not merely some namespace."""
    docs, registry = _helm(development)
    dns = _calico(docs, "default.ospreyflow-allow-dns")
    dns["spec"]["egress"][1]["destination"]["namespaceSelector"] = (
        "kubernetes.io/metadata.name == 'default'"
    )
    assert {rule for rule, _ in _found(docs, registry)} == {"wide-egress", "unreadable-selector"}


@pytest.mark.parametrize(
    ("where", "selector"),
    [
        ("policy", "app.kubernetes.io/part-of == 'ospreyflow'"),
        ("policy", "has(app.kubernetes.io/name)"),
        ("rule", "has(app.kubernetes.io/name)"),
        ("rule", "all()"),
        ("rule", ""),
    ],
    ids=["policy-part-of", "policy-has", "rule-has", "rule-all", "rule-empty"],
)
def test_a_selector_this_check_cannot_narrow_is_refused(
    development: tuple[dict[str, Any], str], where: str, selector: str
) -> None:
    docs, registry = _helm(development)
    policy = _calico(docs, "default.ospreyflow-egress-api")
    if where == "policy":
        policy["spec"]["selector"] = selector
    else:
        policy["spec"]["egress"][0]["destination"]["selector"] = selector
    assert "unreadable-selector" in {rule for rule, _ in _found(docs, registry)}


@pytest.mark.parametrize(
    "peer",
    [
        {"matchExpressions": [{"key": "app.kubernetes.io/name", "operator": "Exists"}]},
        {"matchLabels": {"app.kubernetes.io/instance": "ospreyflow"}},
        {"matchLabels": {"app.kubernetes.io/part-of": "ospreyflow"}},
        {},
    ],
    ids=["exists", "instance", "part-of", "every-pod"],
)
def test_an_ingress_peer_this_check_cannot_name_is_refused(
    development: tuple[dict[str, Any], str], peer: dict[str, Any]
) -> None:
    """Item 4: a workload's ingress admits workloads by name alone."""
    docs, registry = _helm(development)
    policy = _doc(docs, "NetworkPolicy", "ospreyflow-ingress-api")
    policy["spec"]["ingress"][0]["from"] = [{"podSelector": peer}]
    assert {rule for rule, _ in _found(docs, registry)} == {"wide-ingress"}


API_SERVER_RULE = {
    "action": "Allow",
    "protocol": "TCP",
    "destination": {"services": {"name": "kubernetes", "namespace": "default"}},
}


def test_every_allow_names_its_protocol_and_ports(
    development: tuple[dict[str, Any], str],
) -> None:
    """Item 5: every Allow, the managed stores' and each host's included, names its protocol and
    ports; the rule to the API server by its Service alone carries its protocol only. A ports-less
    Allow planted beside that rule is refused, and so is a `services` rule to any other Service."""
    docs, registry = _helm(development)
    restore = _calico(docs, "default.ospreyflow-egress-restore")
    egress = restore["spec"]["egress"]
    assert API_SERVER_RULE in egress and _found(docs, registry) == []
    nets = next(r for r in egress if "nets" in r["destination"])["destination"]["nets"]
    egress.append({"action": "Allow", "destination": {"nets": nets}})
    assert [rule for rule, _ in _found(docs, registry)] == ["allow-ports"]
    egress.pop()
    other = copy.deepcopy(API_SERVER_RULE)
    other["destination"]["services"] = {"name": "superset", "namespace": "ospreyflow-dev"}
    egress.append(other)
    assert [rule for rule, _ in _found(docs, registry)] == ["allow-ports"]


def test_the_gateway_never_runs_as_the_bucket_role() -> None:
    """Item 6: the bucket role's account is IRSA's pods' alone, the gateway's own the gateway's,
    whether or not a token is mounted (IRSA's webhook gives the role by the account alone)."""
    values, registry = _bedrock()
    irsa = _workload(values, "api")["serviceAccountName"]
    gateway = _workload(values, "litellm")
    assert gateway["serviceAccountName"] != irsa
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert not [v for v in found if v.rule == "token"]
    gateway["serviceAccountName"] = irsa
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.where) for v in found if v.rule == "token"] == [
        ("token", "Deployment/litellm"),
        ("token", "Deployment/litellm"),
    ]
    values, registry = _bedrock()
    _workload(values, "superset")["serviceAccountName"] = irsa  # no token, the role all the same
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.detail) for v in found if v.rule == "token"] == [
        ("token", f"runs as {irsa}, the bucket role's account")
    ]


@pytest.mark.parametrize("account", ["default", None], ids=["named", "none"])
def test_a_p9_pod_under_the_default_account_is_refused(
    development: tuple[dict[str, Any], str], account: str | None
) -> None:
    """Item 6: P9's backup pod mounts its token under an account of its own; under the
    namespace's default account (named, or by naming none) it is refused."""
    values, registry = _job_values(development)
    job = values["jobs"][0]
    job.update(name="backup", automountToken=True, serviceAccountName="ospreyflow-backup")
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert not [v for v in found if v.rule == "token"]
    if account is None:
        job.pop("serviceAccountName")
    else:
        job["serviceAccountName"] = account
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.detail) for v in found if v.rule == "token"] == [
        ("token", "mounts the namespace's default account's token")
    ]


def test_the_conduit_and_the_workers_are_told_the_ceiling(
    rendered: tuple[dict[str, Any], str],
) -> None:
    """Item 7: with `deployment.highest_marking` unset, the Conduit's and the workers' containers
    read OFFICIAL-SENSITIVE from the settings they are given (ADR-148 Amendment 5 point 8), and no
    variable of their own says otherwise."""
    values, _ = rendered
    written = yaml.safe_load(values["files"]["osprey.yaml"])
    assert "highest_marking" not in (written.get("deployment") or {})
    docs = helm_template(yaml.safe_dump(values))
    settings = _doc(docs, "ConfigMap", "ospreyflow-env")["data"]
    assert settings["OSPREY_HIGHEST_MARKING"] == "OFFICIAL-SENSITIVE"
    for name in ("api", "worker"):
        spec = pod_spec(_doc(docs, "Deployment", name))
        assert spec is not None
        for container in spec["containers"]:
            maps = [s["configMapRef"]["name"] for s in container.get("envFrom") or []
                    if "configMapRef" in s]  # fmt: skip
            assert maps == ["ospreyflow-env"], (name, maps)
            told = [e for e in container.get("env") or [] if e["name"] == "OSPREY_HIGHEST_MARKING"]
            assert not told, (name, told)


# ---- the final review's second pass ------------------------------------------------------------


def test_a_keyless_single_provider_s_key_is_refused_to_the_gateway(tmp_path: Path) -> None:
    """Item 1: the single `models.provider`'s key (`OSPREY_MODEL_PROVIDER_KEY`) is the gateway's
    only when that provider is keyed. A single IAM-role provider (Bedrock) has none, so the key,
    planted on the gateway in the render's own shape, is refused."""
    raw = yaml.safe_load((FIXTURES / "production-bedrock.yaml").read_text(encoding="utf-8"))
    bedrock = next(p for p in raw["models"]["providers"] if p["name"] == "bedrock")
    raw["models"] = {"local_only": False, "provider": bedrock}
    config = tmp_path / "osprey.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    text, registry = render_values(config)
    values = yaml.safe_load(text)
    assert _secret_violations(values, registry) == []
    _workload(values, "litellm")["env"].append(
        {"name": "OSPREY_MODEL_PROVIDER_KEY", "secret": "OSPREY_MODEL_PROVIDER_KEY"}
    )
    assert _secret_violations(values, registry) == [
        ("Deployment/litellm/litellm", "is given ospreyflow-secrets's OSPREY_MODEL_PROVIDER_KEY")
    ]


def test_the_gateway_s_account_on_another_pod_is_refused() -> None:
    """Item 2: the gateway's own account (Bedrock's role) is the gateway's alone: on the dashboards,
    even with no token mounted, refused."""
    values, registry = _bedrock()
    gateway = _workload(values, "litellm")["serviceAccountName"]
    _workload(values, "superset")["serviceAccountName"] = gateway
    found = check_manifests(helm_template(yaml.safe_dump(values)), registry)
    assert [(v.rule, v.where, v.detail) for v in found if v.rule == "token"] == [
        ("token", "Deployment/superset", f"runs as {gateway}, the gateway's account")
    ]


def test_the_older_service_account_field_is_read() -> None:
    """Item 5: Kubernetes still reads `serviceAccount` when `serviceAccountName` is unset, so the
    bucket role's account named there on the dashboards is refused as by the newer field."""
    values, registry = _bedrock()
    irsa = _workload(values, "api")["serviceAccountName"]
    docs = helm_template(yaml.safe_dump(values))
    spec = pod_spec(_doc(docs, "Deployment", "superset"))
    assert spec is not None and "serviceAccountName" not in spec
    spec["serviceAccount"] = irsa
    assert [(v.rule, v.detail) for v in check_manifests(docs, registry) if v.rule == "token"] == [
        ("token", f"runs as {irsa}, the bucket role's account")
    ]


@pytest.mark.parametrize("ports", [["1:65535"], [443, "8000:9000"], ["https"]],
                         ids=["every-port", "a-range", "a-named-port"])  # fmt: skip
def test_an_allow_by_a_range_or_a_named_port_is_refused(
    development: tuple[dict[str, Any], str], ports: list[Any]
) -> None:
    """Item 4: single ports by number alone; Calico's range string opens every port in it."""
    docs, registry = _helm(development)
    policy = _calico(docs, "default.ospreyflow-egress-api")
    rule = next(r for r in policy["spec"]["egress"] if "nets" in r["destination"])
    rule["destination"]["ports"] = ports
    assert _found(docs, registry) == [
        ("allow-ports", f"an Allow by a range or a named port: {ports}")
    ]


@pytest.mark.parametrize(
    "ends",
    [
        {"notSelector": "app.kubernetes.io/name == 'workspace'"},
        {"serviceAccounts": {"selector": "all()"}},
        {"notNamespaceSelector": "kubernetes.io/metadata.name == 'kube-system'"},
    ],
    ids=["not-selector", "service-account-selector", "not-namespace-selector"],
)
def test_a_rule_s_negative_or_account_selector_is_refused(
    development: tuple[dict[str, Any], str], ends: dict[str, Any]
) -> None:
    """Item 5: a rule's `notSelector`, `notNamespaceSelector` or `serviceAccounts.selector` is
    one this check cannot narrow (everything but, or every account's pods)."""
    docs, registry = _helm(development)
    policy = _calico(docs, "default.ospreyflow-egress-api")
    policy["spec"]["egress"][0]["destination"].update(ends)
    assert {rule for rule, _ in _found(docs, registry)} == {"unreadable-selector"}
