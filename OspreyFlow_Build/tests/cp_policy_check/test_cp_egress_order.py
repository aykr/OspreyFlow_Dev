"""Who reaches whom, from Helm's own output, evaluated as the platform does (ADR-148 Amendment 5
points 21-23; the orchestrator's rulings from case-b's P12 review).

Egress is Calico's: its policies by `order` (the per-workload Allows and DNS at 100, the deny at
200), the first rule that matches deciding; the namespace's Kubernetes policies sit at order 1000,
after the deny, so they never decide egress. Ingress is the Kubernetes policies': a pod selected by
any admits only what one of them admits. A workload reaches another only when both allow it.

For each workload and each destination (every other workload on its first port, the managed stores'
network, each host's network, an address on the internet, the cluster's DNS) the answer is
compared with `profile.yaml`'s `egress` rows, both ways. Needs Docker, for Helm.
"""

from __future__ import annotations

import copy
import ipaddress
import re
from typing import Any

import pytest
import yaml
from harness.cloud_platform.settings import load_platform, load_profile
from tools.cp_policy_check import (
    FIXTURES,
    _matches,
    check_manifests,
    helm_template,
    pod_spec,
    render_values,
)

CONTROLLER = load_platform("client").ingress.controller_namespace
#: Addresses on the internet, the first outside every network the render names is used.
INTERNET_CANDIDATES = ("198.51.100.77", "203.0.113.9", "192.0.2.77", "100.64.0.77")
DNS = "dns"


def _render(name: str) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    values_text, registry = render_values(FIXTURES / f"{name}.yaml")
    return helm_template(values_text), yaml.safe_load(values_text), registry


@pytest.fixture(scope="module", params=["development", "production", "poc"])
def rendered(request: pytest.FixtureRequest) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    return _render(request.param)


def _selects(selector: str, labels: dict[str, str]) -> bool:
    selector = selector.strip()
    if selector.replace(" ", "") == "all()":
        return True
    if found := re.fullmatch(r"([\w./-]+) == '([^']*)'", selector):
        return labels.get(found.group(1)) == found.group(2)
    if found := re.fullmatch(r"([\w./-]+) in \{(.*)\}", selector):
        return labels.get(found.group(1)) in re.findall(r"'([^']*)'", found.group(2))
    raise AssertionError(f"a selector this evaluator does not read: {selector!r}")


def _rule_matches(rule: dict[str, Any], dest: dict[str, Any], dns_namespace: str) -> bool:
    destination = rule.get("destination") or {}
    if "ports" in destination and dest["port"] not in destination["ports"]:
        return False
    if "services" in destination:
        wanted = (destination["services"].get("namespace"), destination["services"].get("name"))
        if dest.get("service") != wanted:
            return False
    if "selector" in destination:
        if dest.get("labels") is None or not _selects(destination["selector"], dest["labels"]):
            return False
    if "namespaceSelector" in destination:
        if dest.get("namespace") != dns_namespace:
            return False
    if "nets" in destination:
        if dest.get("ip") is None or not any(
            ipaddress.ip_address(dest["ip"]) in ipaddress.ip_network(n) for n in destination["nets"]
        ):
            return False
    return True


def _egress(docs: list[dict[str, Any]], source: dict[str, str], dest: dict[str, Any],
            dns_namespace: str) -> bool:  # fmt: skip
    calico = sorted(
        (d for d in docs if str(d.get("apiVersion", "")).startswith("projectcalico.org")
         and "Egress" in (d["spec"].get("types") or [])),
        key=lambda d: d["spec"].get("order", float("inf")),
    )  # fmt: skip
    for policy in calico:
        if not _selects(policy["spec"].get("selector", "all()"), source):
            continue
        for rule in policy["spec"].get("egress") or []:
            if _rule_matches(rule, dest, dns_namespace):
                return rule["action"] == "Allow"
    return False  # the end of the tier: a pod a policy selected is denied what none allowed


def _ingress(docs: list[dict[str, Any]], source: dict[str, str], dest: dict[str, Any]) -> bool:
    policies = [
        d for d in docs
        if d["kind"] == "NetworkPolicy" and d["apiVersion"].startswith("networking.k8s.io")
        and "Ingress" in (d["spec"].get("policyTypes") or ["Ingress"])
        and _matches(d["spec"].get("podSelector") or {}, dest["labels"])
    ]  # fmt: skip
    if not policies:
        return True
    for policy in policies:
        for rule in policy["spec"].get("ingress") or []:
            ports = [p["port"] for p in rule.get("ports") or []]
            if ports and dest["port"] not in ports:
                continue
            for peer in rule.get("from") or []:
                if set(peer) == {"podSelector"} and _matches(peer["podSelector"] or {}, source):
                    return True
    return False


def _pods(docs: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    out = {}
    for doc in docs:
        spec = pod_spec(doc)
        if spec is not None and doc["kind"] in ("Deployment", "StatefulSet"):
            labels = doc["spec"]["template"]["metadata"]["labels"]
            out[labels["app.kubernetes.io/name"]] = labels
    return out


def _internet(values: dict[str, Any]) -> str:
    named = [ipaddress.ip_network(n) for h in values["egress"]["hosts"] for n in h["nets"]]
    named += [ipaddress.ip_network(n) for n in values["egress"]["managedNets"]]
    return next(a for a in INTERNET_CANDIDATES
                if not any(ipaddress.ip_address(a) in n for n in named))  # fmt: skip


def _one_address(nets: list[str]) -> str:
    return str(next(ipaddress.ip_network(nets[0]).hosts()))


def _reaches(docs: list[dict[str, Any]], values: dict[str, Any], source: str, dest: dict[str, Any]
             ) -> bool:  # fmt: skip
    pods = _pods(docs)
    dns = values["egress"]["dnsNamespace"]
    out = _egress(docs, pods[source], dest, dns)
    if dest.get("labels") is not None:
        return out and _ingress(docs, pods[source], dest)
    return out


def test_who_reaches_whom_is_the_rows_and_nothing_more(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    docs, values, _ = rendered
    egress = load_profile().egress
    pods = _pods(docs)
    ports = {w["name"]: [p["port"] for p in w.get("ports", [])] for w in values["workloads"]}
    rows = {r["name"]: r for r in values["egress"]["workloads"]}
    managed = _one_address(values["egress"]["managedNets"])
    for source in pods:
        assert _reaches(docs, values, source, {"namespace": values["egress"]["dnsNamespace"],
                                               "port": 53}), source  # fmt: skip
        assert not _reaches(docs, values, source, {"ip": _internet(values), "port": 443}), source
        assert _reaches(docs, values, source, {"ip": managed, "port": 5432}) == (
            source in egress.managed
        ), source
        # On their own ports alone (the final review's item 5): never another.
        assert not _reaches(docs, values, source, {"ip": managed, "port": 22}), source
        for host in values["egress"]["hosts"]:
            given = host["host"] in rows[source].get("hosts", [])
            address = _one_address(host["nets"])
            for port in host["ports"]:
                assert _reaches(docs, values, source, {"ip": address, "port": port}) == given, (
                    source, host["host"], port)  # fmt: skip
            assert not _reaches(docs, values, source, {"ip": address, "port": 22}), source
        for target, labels in pods.items():
            if not ports.get(target):
                continue
            dest = {"labels": labels, "port": ports[target][0]}
            assert _reaches(docs, values, source, dest) == (
                target in egress.paths.get(source, [])
            ), (source, target)


def test_case_b_s_cases(rendered: tuple[list[dict[str, Any]], dict[str, Any], str]) -> None:
    """The cases case-b named: the Glass and the recogniser reach no store and no host; the Glass
    reaches the Conduit and nothing else of ours; the gateway is reached by the Conduit alone; and
    ClickHouse reaches S3 for its BACKUP TO S3 (P9)."""
    docs, values, _ = rendered
    pods = _pods(docs)
    s3 = next(h for h in values["egress"]["hosts"] if h["host"].startswith("s3."))
    for source in ("ner", "workspace"):
        assert not _reaches(docs, values, source, {"ip": _one_address(s3["nets"]), "port": 443})
        assert not _reaches(
            docs,
            values,
            source,
            {"ip": _one_address(values["egress"]["managedNets"]), "port": 5432},
        )
    assert _reaches(docs, values, "clickhouse", {"ip": _one_address(s3["nets"]), "port": 443})
    if "litellm" in pods:
        callers = [
            s for s in pods if _reaches(docs, values, s, {"labels": pods["litellm"], "port": 4000})
        ]
        paths = load_profile().egress.paths
        assert callers == sorted(s for s in pods if "litellm" in paths.get(s, []))
        assert "api" in callers and not {"workspace", "ner", "superset"} & set(callers)


# ---- the rules, each red on the shape it refuses -----------------------------------------------


def test_the_one_allow_for_every_pod_is_refused(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    """The policy P7 rendered, planted back in Helm's own output: every pod allowed every pod, the
    managed stores and every host, before the deny."""
    docs, values, registry = rendered
    old = copy.deepcopy(
        next(d for d in docs if d["metadata"]["name"] == "default.ospreyflow-allow-dns")
    )
    old["metadata"]["name"] = "default.ospreyflow-allow-egress"
    old["spec"]["egress"] += [
        {"action": "Allow", "destination": {"selector": "all()"}},
        {"action": "Allow", "destination": {"nets": values["egress"]["managedNets"]}},
    ]
    found = check_manifests([*docs, old], registry, controller_namespace=CONTROLLER)
    # P7's policy as it was: an Allow under every pod, by `all()`, with no ports; each refused.
    where = "NetworkPolicy/default.ospreyflow-allow-egress"
    assert {(v.rule, v.where) for v in found} == {
        ("wide-egress", where),
        ("unreadable-selector", where),
        ("allow-ports", where),
    }
    assert _reaches(
        [*docs, old],
        values,
        "ner",
        {"ip": _one_address(values["egress"]["managedNets"]), "port": 5432},
    )


def test_ingress_from_every_pod_of_ours_is_refused(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    """P7's internal policy's ingress half, planted back as the cluster's chart renders it: every
    pod of ours admitted to all. On this profile the internal policy is not rendered at all."""
    docs, _, registry = copy.deepcopy(rendered)
    assert not [d for d in docs if d["metadata"]["name"] == "ospreyflow-internal"]
    docs.append(_kubernetes_policy("ospreyflow-internal", ingress=[
        {"from": [{"podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "ospreyflow"}}}]}
    ]))  # fmt: skip
    found = check_manifests(docs, registry, controller_namespace=CONTROLLER)
    assert [(v.rule, v.where) for v in found] == [
        ("wide-ingress", "NetworkPolicy/ospreyflow-internal")
    ]


def _kubernetes_policy(name: str, **rules: list[dict[str, Any]]) -> dict[str, Any]:
    """A Kubernetes NetworkPolicy over every pod of ours, as the chart emits one."""
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": name},
        "spec": {
            "podSelector": {"matchLabels": {"app.kubernetes.io/part-of": "ospreyflow"}},
            "policyTypes": [k.capitalize() for k in rules],
            **rules,
        },
    }


@pytest.mark.parametrize("workload", ["workspace", "ner", "superset"])
def test_the_whole_secret_to_a_pod_that_reads_none_is_refused(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str], workload: str,
) -> None:  # fmt: skip
    docs, _, registry = copy.deepcopy(rendered)
    doc = next((d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == workload),
               None)  # fmt: skip
    if doc is None:
        pytest.skip(f"{workload} is not rendered here")
    container = doc["spec"]["template"]["spec"]["containers"][0]
    container.setdefault("envFrom", []).append({"secretRef": {"name": "ospreyflow-secrets"}})
    found = check_manifests(docs, registry, controller_namespace=CONTROLLER)
    assert [(v.rule, v.detail) for v in found] == [
        ("whole-secret", "reads ospreyflow-secrets whole")
    ]


def test_a_store_s_password_named_to_superset_is_refused(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    docs, _, registry = copy.deepcopy(rendered)
    doc = next((d for d in docs if d["metadata"]["name"] == "superset" and pod_spec(d)), None)
    if doc is None:
        pytest.skip("superset is not rendered here")
    container = doc["spec"]["template"]["spec"]["containers"][0]
    container.setdefault("env", []).append(
        {
            "name": "ARCADEDB_ROOT_PASSWORD",
            "valueFrom": {
                "secretKeyRef": {"name": "ospreyflow-secrets", "key": "ARCADEDB_ROOT_PASSWORD"}
            },
        }
    )
    found = check_manifests(docs, registry, controller_namespace=CONTROLLER)
    assert [(v.rule, v.detail) for v in found] == [
        ("whole-secret", "is given ospreyflow-secrets's ARCADEDB_ROOT_PASSWORD")
    ]


@pytest.mark.parametrize("job", ["ospreyflow-search-rebuild", "ospreyflow-search-drift"])
def test_the_search_index_s_jobs_hold_the_graph_s_password_alone(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str], job: str
) -> None:
    """v0.5.2 step 3a: the rebuild and the drift check (ADR-150) read the graph's password by name
    and the domain's address from the platform's secret; given our Secret whole, or another key of
    it, they are refused as any pod not listed is (the gate's lists widened for these two alone)."""
    docs, _, registry = copy.deepcopy(rendered)
    doc = next((d for d in docs if d["kind"] == "CronJob" and d["metadata"]["name"] == job), None)
    if doc is None:
        pytest.skip(f"{job} is not rendered here")
    assert check_manifests(docs, registry, controller_namespace=CONTROLLER) == []
    container = pod_spec(doc)["containers"][0]
    container.setdefault("envFrom", []).append({"secretRef": {"name": "ospreyflow-secrets"}})
    container.setdefault("env", []).append({"name": "OSPREY_LITELLM_MASTER_SECRET", "valueFrom": {
        "secretKeyRef": {"name": "ospreyflow-secrets", "key": "OSPREY_LITELLM_MASTER_SECRET"}}})  # fmt: skip
    found = check_manifests(docs, registry, controller_namespace=CONTROLLER)
    assert sorted((v.rule, v.detail) for v in found) == [
        ("whole-secret", "is given ospreyflow-secrets's OSPREY_LITELLM_MASTER_SECRET"),
        ("whole-secret", "reads ospreyflow-secrets whole"),
    ]


def test_the_claims_backup_reads_the_shared_claim_s_parts_read_only(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    """The ADR-148 audit's ruling 3 (v0.5.2), in Helm's own output: the claims backup mounts the
    shared claim's three folders read-only, each at its part's name, and names them to the runner."""
    docs, _, _ = rendered
    job = next(d for d in docs if d["kind"] == "CronJob" and d["metadata"]["name"] == "ospreyflow-backup-claims")
    spec = pod_spec(job)
    container = spec["containers"][0]
    mounts = {m["mountPath"]: m for m in container["volumeMounts"] if m["name"] == "shared"}
    assert {path: (m["subPath"], m.get("readOnly")) for path, m in mounts.items()} == {
        "/claims/shared-recipes": ("data/recipes", True),
        "/claims/shared-model-settings": ("model-settings", True),
        "/claims/shared-map-settings": ("map-settings", True),
    }
    [shared] = [v for v in spec["volumes"] if v["name"] == "shared"]
    assert shared["persistentVolumeClaim"] == {"claimName": "ospreyflow-shared", "readOnly": True}
    named = next(e["value"] for e in container["env"] if e["name"] == "OSPREY_BACKUP_CLAIMS").split(",")
    assert {"shared-recipes", "shared-model-settings", "shared-map-settings"} <= set(named)


def test_p9_s_pods_reach_their_stores_and_a_restore_the_api_and_no_more(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    """P9's pods by their own rows (the render's `egress_policy(..., others=...)`), evaluated in
    Helm's own output: the backup reaches ArcadeDB and ClickHouse, the restore ClickHouse alone,
    each admitted; the claims' runs reach none of ours; the two restores alone reach the cluster's
    API; each reaches S3 and STS and nothing else outside; ClickHouse reaches S3."""
    docs, values, registry = rendered
    pods_of_p9 = tuple(load_profile().egress.others)
    labels = {name: {"app.kubernetes.io/name": name, "app.kubernetes.io/part-of": "ospreyflow"}
              for name in pods_of_p9}  # fmt: skip
    pods = {**_pods(docs), **labels}
    dns = values["egress"]["dnsNamespace"]

    def reaches(source: str, dest: dict[str, Any]) -> bool:
        allowed = _egress(docs, pods[source], dest, dns)
        return allowed and (dest.get("labels") is None or _ingress(docs, pods[source], dest))

    api_server = {"service": ("default", "kubernetes"), "port": 443}
    assert sorted(p for p in pods if reaches(p, api_server)) == ["restore", "restore-claims"]
    stores = {"backup": {"arcadedb", "clickhouse"}, "restore": {"clickhouse"},
              "backup-claims": set(), "restore-claims": set()}  # fmt: skip
    for source, reached in stores.items():
        assert reaches(source, {"labels": pods["arcadedb"], "port": 2480}) == ("arcadedb" in reached), source
        assert reaches(source, {"labels": pods["clickhouse"], "port": 8123}) == ("clickhouse" in reached), source
        assert not reaches(source, {"labels": pods["api"], "port": 8000}), source
        assert not reaches(source, {"ip": _internet(values), "port": 443}), source
        for host in values["egress"]["hosts"]:
            outside = {"ip": _one_address(host["nets"]), "port": 443}
            assert reaches(source, outside) == host["host"].startswith(("s3.", "sts.")), (
                source, host["host"])  # fmt: skip
    assert not [h for h in values["egress"]["hosts"] if h["host"].startswith("kms.")]
    s3 = next(h for h in values["egress"]["hosts"] if h["host"].startswith("s3."))
    assert reaches("clickhouse", {"ip": _one_address(s3["nets"]), "port": 443})
    found = check_manifests(docs, registry, controller_namespace=CONTROLLER)
    assert not [v for v in found if v.rule in {"wide-egress", "wide-ingress", "open-egress"}]


def test_a_secret_of_its_own_for_clickhouse_and_p9_s_pods_passes(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    """The ClickHouse backup user's password in a Secret of its own (P9's `backups.tf`), read by
    ClickHouse whole and by key: not our Secret, so the whole-secret rule passes it, as it refuses
    ours read the same way (`test_the_whole_secret_to_a_pod_that_reads_none_is_refused`)."""
    docs, _, registry = copy.deepcopy(rendered)
    doc = next(d for d in docs if d["metadata"]["name"] == "clickhouse" and pod_spec(d))
    container = pod_spec(doc)["containers"][0]
    own = "ospreyflow-clickhouse-backup"
    container.setdefault("envFrom", []).append({"secretRef": {"name": own}})
    container.setdefault("env", []).append(
        {"name": "CLICKHOUSE_BACKUP_PASSWORD",
         "valueFrom": {"secretKeyRef": {"name": own, "key": "password"}}}
    )  # fmt: skip
    assert not [v for v in check_manifests(docs, registry, controller_namespace=CONTROLLER)
                if v.rule == "whole-secret"]  # fmt: skip
    container["envFrom"].append({"secretRef": {"name": "ospreyflow-secrets"}})
    found = check_manifests(docs, registry, controller_namespace=CONTROLLER)
    assert [(v.rule, v.detail) for v in found if v.rule == "whole-secret"] == [
        ("whole-secret", "reads ospreyflow-secrets whole")
    ]


def test_the_seed_holds_the_graph_s_and_clickhouse_s_passwords_alone_and_no_token(
    rendered: tuple[list[dict[str, Any]], dict[str, Any], str],
) -> None:
    """The POC seed path's Job (ADR-148 Amendment 14), in Helm's own output: the graph's and
    ClickHouse's passwords by name, no token. Given our Secret whole or another key of it, or its
    account's token, or IRSA's account, it is refused as any pod not listed is."""
    docs, _, registry = copy.deepcopy(rendered)
    cronjobs = {d["metadata"]["name"]: d for d in docs if d["kind"] == "CronJob"}
    doc = cronjobs.get("ospreyflow-seed")
    if doc is None:
        pytest.skip("the seed is the poc's alone")
    assert check_manifests(docs, registry, controller_namespace=CONTROLLER) == []
    spec = pod_spec(doc)
    assert spec["automountServiceAccountToken"] is False and "serviceAccountName" not in spec
    container = spec["containers"][0]
    refs = [e.get("valueFrom", {}).get("secretKeyRef", {}) for e in container["env"]]
    held = sorted(r["key"] for r in refs if r.get("name") == "ospreyflow-secrets")
    assert held == ["ARCADEDB_ROOT_PASSWORD", "CLICKHOUSE_PASSWORD"]
    another = {"name": "ospreyflow-secrets", "key": "OSPREY_OIDC_CLIENT_SECRET"}
    given = {"name": "OSPREY_OIDC_CLIENT_SECRET", "valueFrom": {"secretKeyRef": another}}
    container["env"].append(given)
    spec["automountServiceAccountToken"] = True
    found = check_manifests(docs, registry, controller_namespace=CONTROLLER)
    assert sorted((v.rule, v.detail) for v in found) == [
        ("token", "mounts its service account's token"),
        ("whole-secret", "is given ospreyflow-secrets's OSPREY_OIDC_CLIENT_SECRET"),
    ]


def test_every_cronjob_the_poc_chart_renders_is_in_the_manifest() -> None:
    """ADR-148 Amendment 12, rendered and not listed, read from Helm's own output rather than from
    the values keys the manifest's builder already knows: a new standing Job (the seed's, Amendment
    14) was invisible to the both-ways check while the manifest read only the keys it knew."""
    from harness.cloud_platform import SEED_JOB, manifest

    docs, _, _ = _render("poc")
    rendered = {d["metadata"]["name"] for d in docs if d["kind"] == "CronJob"}
    listed = manifest.load()["jobs"]
    assert rendered - set(listed) == set()
    # And the other way: every CronJob the manifest lists is one Helm renders.
    assert {n for n, j in listed.items() if j["kind"] == "CronJob"} - rendered == set()
    # The seed's own, as rendered: held suspended, bounded, no token.
    seed = next(d for d in docs if d["kind"] == "CronJob" and d["metadata"]["name"] == SEED_JOB)
    assert seed["spec"]["suspend"] is True
    assert seed["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"] == 2100
    assert pod_spec(seed)["automountServiceAccountToken"] is False
