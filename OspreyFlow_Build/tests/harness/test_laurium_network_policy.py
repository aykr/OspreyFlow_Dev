"""Laurium reaches the gateway and nothing else (`06_DECISIONS.md` ADR-135 Amendment 6, P12 part 2;
the orchestrator's ruling of 11 November): read from **Helm's own output** for the cloud-platform
render with Laurium chosen, evaluated **in Calico's order**, which is what decides on that
profile.

Calico reads the policies selecting a pod in order (a Kubernetes NetworkPolicy at 1000); the first
rule whose match holds ends it with its action, an explicit Deny included; a policy that selected
the pod and matched nothing denies at the end of its tier. Today the namespace's `allow-egress`
(order 100, selector `all()`) admits every pod to every pod, the managed stores' networks and each
allowed host (case-b's finding of 11 November). **Platform's P7b replaces it** (the orchestrator's
relay of 11 November): one Calico policy per source workload,
`default.ospreyflow-egress-<workload>`, from `profile.yaml`'s `egress.paths`, with only
`default.ospreyflow-allow-dns` on `all()`; Laurium is held by its row there, `laurium: [litellm]`
(`process/lanes/case-b/P12p2_egress_paths.md`), not by a policy of its own.

**Until P7b and that row land, the Helm-read cases are `xfail(strict=True)`** (`UNTIL_P7B`): they
fail now (Laurium reaches everything), and the day they pass the mark fails them, so it is taken
off. The evaluator itself is proven now on hand-written manifests in P7b's announced shape.

Laurium's pod, once P7b lands: **the gateway on 4000 and DNS, allowed; the gateway on another port,
ArcadeDB, ClickHouse, a managed store's network, an allowed outside host, denied.** Into it: the
Conduit and the workers, allowed; any other pod, denied (ingress is not in P7b's design as relayed:
asked of the orchestrator). Controls show the evaluator still lets the Conduit reach a store and the
managed stores, so a denial means something; and the manifests with Laurium's own egress policy
taken out (the shape Helm emits, less that document) show Laurium reaching all of it, red.

Needs Docker (Helm's pinned image, `tools.helm_chart`): run on the test server, never on the Mac.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from functools import cache
from typing import Any

import pytest
import yaml
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver, helm_template

from schemas.deployment import OspreyConfig

NAMESPACE = "ospreyflow-dev"
POD_IP = "10.42.0.10"


@dataclass(frozen=True)
class Endpoint:
    """One end of a connection: a pod (its labels, its namespace's labels) or an address."""

    labels: dict[str, str] = field(default_factory=dict)
    namespace: str = NAMESPACE
    ip: str = POD_IP
    port: int = 0
    protocol: str = "TCP"

    @property
    def namespace_labels(self) -> dict[str, str]:
        return {"kubernetes.io/metadata.name": self.namespace}

    @property
    def is_pod(self) -> bool:
        return bool(self.labels)


def pod(name: str, port: int = 0, protocol: str = "TCP") -> Endpoint:
    return Endpoint(
        labels={"app.kubernetes.io/name": name, "app.kubernetes.io/part-of": "ospreyflow"},
        port=port,
        protocol=protocol,
    )


# --- Calico's selectors, as far as the chart writes them -------------------------------------

_TERM = re.compile(
    r"^\s*(?:(all\(\))|([\w./-]+)\s*(==|!=)\s*'([^']*)'|([\w./-]+)\s+in\s+\{([^}]*)\})\s*$"
)


def calico_selects(selector: str, labels: dict[str, str]) -> bool:
    """`all()`, `k == 'v'`, `k != 'v'`, `k in {'a', 'b'}`, joined by `&&`; any other shape is
    refused, so a selector this cannot read fails the test instead of being guessed at."""
    for term in selector.split("&&"):
        m = _TERM.match(term)
        if m is None:
            raise AssertionError(f"a Calico selector this test cannot read: {selector!r}")
        if m.group(1):
            continue
        if m.group(2):
            value = labels.get(m.group(2))
            if (value == m.group(4)) != (m.group(3) == "=="):
                return False
            continue
        allowed = {v.strip().strip("'") for v in m.group(6).split(",")}
        if labels.get(m.group(5)) not in allowed:
            return False
    return True


def k8s_selects(selector: dict[str, Any], labels: dict[str, str]) -> bool:
    for key, value in (selector.get("matchLabels") or {}).items():
        if labels.get(key) != value:
            return False
    for expr in selector.get("matchExpressions") or []:
        value, values = labels.get(expr["key"]), expr.get("values") or []
        op = expr["operator"]
        if op == "In" and value not in values:
            return False
        if op == "NotIn" and value in values:
            return False
        if op == "Exists" and value is None:
            return False
        if op == "DoesNotExist" and value is not None:
            return False
    return True


def _ports_hold(ports: list[Any] | None, peer: Endpoint) -> bool:
    return not ports or peer.port in {
        int(p if not isinstance(p, dict) else p["port"]) for p in ports
    }


def _in_nets(nets: list[str] | None, ip: str) -> bool:
    return any(
        ipaddress.ip_address(ip) in ipaddress.ip_network(n, strict=False) for n in nets or []
    )


def _calico_peer_holds(spec: dict[str, Any] | None, peer: Endpoint) -> bool:
    if not spec:
        return True
    if "nets" in spec and not _in_nets(spec["nets"], peer.ip):
        return False
    if "namespaceSelector" in spec:
        if not peer.is_pod or not calico_selects(spec["namespaceSelector"], peer.namespace_labels):
            return False
    elif "selector" in spec and peer.namespace != NAMESPACE:
        return False
    if "selector" in spec and (
        not peer.is_pod or not calico_selects(spec["selector"], peer.labels)
    ):
        return False
    return _ports_hold(spec.get("ports"), peer)


def _calico_rule_holds(rule: dict[str, Any], peer: Endpoint, direction: str) -> bool:
    """For Egress `peer` is the destination; for Ingress the source, its `port` the subject's own
    (a Calico rule names the ports on its destination either way)."""
    if "protocol" in rule and rule["protocol"] != peer.protocol:
        return False
    destination = rule.get("destination") or {}
    if direction == "Egress":
        return _calico_peer_holds(destination, peer)
    return _ports_hold(destination.get("ports"), peer) and _calico_peer_holds(
        rule.get("source"), peer
    )


def _k8s_rule_holds(rule: dict[str, Any], peer: Endpoint, direction: str) -> bool:
    ports = rule.get("ports") or []
    if ports and not any(
        int(p["port"]) == peer.port and p.get("protocol", "TCP") == peer.protocol for p in ports
    ):
        return False
    peers = rule.get("to" if direction == "Egress" else "from")
    if not peers:
        return True
    for p in peers:
        if "ipBlock" in p:
            if _in_nets([p["ipBlock"]["cidr"]], peer.ip):
                return True
            continue
        if not peer.is_pod:
            continue
        if "namespaceSelector" in p:
            if not k8s_selects(p["namespaceSelector"], peer.namespace_labels):
                continue
        elif peer.namespace != NAMESPACE:
            continue
        if "podSelector" in p and not k8s_selects(p["podSelector"], peer.labels):
            continue
        return True
    return False


def decide(docs: list[dict[str, Any]], subject: Endpoint, peer: Endpoint, direction: str) -> str:
    """Calico's answer for `subject`'s traffic to (Egress) or from (Ingress) `peer`."""
    ordered: list[tuple[float, str, dict[str, Any]]] = []
    for doc in docs:
        if doc.get("kind") != "NetworkPolicy":
            continue
        spec = doc.get("spec") or {}
        if doc.get("apiVersion", "").startswith("projectcalico.org"):
            if direction in spec.get("types", []) and calico_selects(
                spec["selector"], subject.labels
            ):
                ordered.append((float(spec.get("order", 1000)), "calico", spec))
        elif direction in spec.get("policyTypes", []) and k8s_selects(
            spec["podSelector"], subject.labels
        ):
            ordered.append((1000.0, "k8s", spec))
    ordered.sort(key=lambda o: o[0])
    for _, kind, spec in ordered:
        rules = spec.get("egress" if direction == "Egress" else "ingress") or []
        for rule in rules:
            if kind == "calico" and _calico_rule_holds(rule, peer, direction):
                return str(rule["action"])
            if kind == "k8s" and _k8s_rule_holds(rule, peer, direction):
                return "Allow"
    return "Deny" if ordered else "Allow"


# --- the render ---------------------------------------------------------------------------------


def _values(name: str) -> tuple[str, dict[str, Any]]:
    raw: dict[str, Any] = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text("utf-8"))
    raw["models"] = {**raw.get("models", {}), "extraction_engine": "laurium"}
    text = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["values.yaml"]
    return text, yaml.safe_load(text)


@cache
def _manifests(name: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text, values = _values(name)
    return helm_template(text, NAMESPACE), values


def _outside(values: dict[str, Any]) -> tuple[Endpoint, Endpoint]:
    egress = values["egress"]
    managed = ipaddress.ip_network(egress["managedNets"][0], strict=False)
    host_nets = [n for h in egress.get("hosts", []) for n in h["nets"]]
    assert host_nets, "the render names no outside host to try"
    host = ipaddress.ip_network(host_nets[0], strict=False)
    return Endpoint(ip=str(next(managed.hosts())), port=5432), Endpoint(
        ip=str(next(host.hosts())), port=443
    )


def _dns(values: dict[str, Any], protocol: str) -> Endpoint:
    return Endpoint(
        labels={"k8s-app": "kube-dns"},
        namespace=values["egress"]["dnsNamespace"],
        port=53,
        protocol=protocol,
    )


FIXTURE_NAMES = ["development", "production"]
LAURIUM = pod("laurium")
#: P7b's policy for Laurium's egress, by platform's naming.
LAURIUM_EGRESS = "default.ospreyflow-egress-laurium"
UNTIL_P7B = pytest.mark.xfail(
    strict=True,
    reason="until P7b's per-workload egress (platform, ADR-148 Amendment 5) and case-b's "
    "`laurium: [litellm]` row land: today allow-egress (all()) admits Laurium to everything",
)


@UNTIL_P7B
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_laurium_reaches_the_gateway_and_dns_alone(name: str) -> None:
    docs, values = _manifests(name)
    managed, host = _outside(values)
    answers = {
        "gateway:4000": decide(docs, LAURIUM, pod("litellm", 4000), "Egress"),
        "dns/udp": decide(docs, LAURIUM, _dns(values, "UDP"), "Egress"),
        "dns/tcp": decide(docs, LAURIUM, _dns(values, "TCP"), "Egress"),
        "gateway:5432": decide(docs, LAURIUM, pod("litellm", 5432), "Egress"),
        "arcadedb:2480": decide(docs, LAURIUM, pod("arcadedb", 2480), "Egress"),
        "clickhouse:8123": decide(docs, LAURIUM, pod("clickhouse", 8123), "Egress"),
        "api:8000": decide(docs, LAURIUM, pod("api", 8000), "Egress"),
        "a managed store": decide(docs, LAURIUM, managed, "Egress"),
        "an outside host": decide(docs, LAURIUM, host, "Egress"),
    }
    assert answers == {
        "gateway:4000": "Allow", "dns/udp": "Allow", "dns/tcp": "Allow",
        "gateway:5432": "Deny", "arcadedb:2480": "Deny", "clickhouse:8123": "Deny",
        "api:8000": "Deny", "a managed store": "Deny", "an outside host": "Deny",
    }  # fmt: skip


@UNTIL_P7B
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_only_the_conduit_and_the_workers_reach_laurium(name: str) -> None:
    docs, _ = _manifests(name)
    into = {
        who: decide(docs, pod("laurium", 8000), pod(who, 8000), "Ingress")
        for who in ("api", "worker", "workspace", "arcadedb", "litellm")
    }
    assert into == {
        "api": "Allow",
        "worker": "Allow",
        "workspace": "Deny",
        "arcadedb": "Deny",
        "litellm": "Deny",
    }


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_the_evaluator_still_lets_the_conduit_through(name: str) -> None:
    """Controls: the Conduit reaches a store and the managed stores, so a Deny above is the
    policies', not an evaluator that denies everything."""
    docs, values = _manifests(name)
    managed, _ = _outside(values)
    assert decide(docs, pod("api"), pod("arcadedb", 2480), "Egress") == "Allow"
    assert decide(docs, pod("api"), managed, "Egress") == "Allow"
    assert decide(docs, pod("api"), pod("litellm", 4000), "Egress") == "Allow"


@UNTIL_P7B
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_without_lauriums_own_policy_it_reaches_everything(name: str) -> None:
    """Red first, in the shape Helm emits: the same manifests less Laurium's own Calico policy, and
    the namespace's allow-egress lets Laurium reach the stores, the managed stores and the outside.
    This is what the test above would fail on."""
    docs, values = _manifests(name)
    managed, host = _outside(values)
    without = [d for d in docs if (d.get("metadata") or {}).get("name") != LAURIUM_EGRESS]
    assert len(without) == len(docs) - 1, "Laurium's egress policy was not rendered"
    assert decide(without, LAURIUM, pod("arcadedb", 2480), "Egress") == "Allow"
    assert decide(without, LAURIUM, managed, "Egress") == "Allow"
    assert decide(without, LAURIUM, host, "Egress") == "Allow"


def test_nothing_of_lauriums_policy_without_laurium() -> None:
    """A regression guard: true today for want of any Laurium policy; after P7b it is what fails if
    Laurium's row renders a policy for a deployment that did not choose it."""
    raw: dict[str, Any] = yaml.safe_load((FIXTURES / "development.yaml").read_text("utf-8"))
    text = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["values.yaml"]
    names = {(d.get("metadata") or {}).get("name") for d in helm_template(text, NAMESPACE)}
    assert not {n for n in names if n and "laurium" in n}


# --- the evaluator itself, on hand-written manifests in P7b's announced shape (offline) --------


def _calico(name: str, order: int, selector: str, egress: list[dict[str, Any]]) -> dict[str, Any]:
    return {"apiVersion": "projectcalico.org/v3", "kind": "NetworkPolicy",
            "metadata": {"name": name},
            "spec": {"tier": "default", "order": order, "selector": selector,
                     "types": ["Egress"], "egress": egress}}  # fmt: skip


def _p7b_shape(paths: dict[str, list[tuple[str, int]]]) -> list[dict[str, Any]]:
    dns = [{"action": "Allow", "protocol": proto,
            "destination": {"namespaceSelector": "kubernetes.io/metadata.name == 'kube-system'",
                            "ports": [53]}} for proto in ("UDP", "TCP")]  # fmt: skip
    docs = [_calico("default.ospreyflow-allow-dns", 100, "all()", dns)]
    for source, targets in paths.items():
        rules = [{"action": "Allow", "protocol": "TCP",
                  "destination": {"selector": f"app.kubernetes.io/name in {{'{t}'}}",
                                  "ports": [port]}} for t, port in targets]  # fmt: skip
        docs.append(
            _calico(
                f"default.ospreyflow-egress-{source}",
                100,
                f"app.kubernetes.io/name == '{source}'",
                rules,
            )  # fmt: skip
        )
    docs.append(_calico("default.ospreyflow-deny-egress", 200, "all()", [{"action": "Deny"}]))
    return docs


DNS_UDP = Endpoint(labels={"k8s-app": "kube-dns"}, namespace="kube-system", port=53, protocol="UDP")


def test_the_evaluator_reads_p7bs_shape_as_calico_does() -> None:
    docs = _p7b_shape(
        {"laurium": [("litellm", 4000)], "api": [("arcadedb", 2480), ("laurium", 8000)]}
    )
    assert decide(docs, LAURIUM, pod("litellm", 4000), "Egress") == "Allow"
    assert decide(docs, LAURIUM, DNS_UDP, "Egress") == "Allow"
    assert decide(docs, LAURIUM, pod("litellm", 5432), "Egress") == "Deny"
    assert decide(docs, LAURIUM, pod("arcadedb", 2480), "Egress") == "Deny"
    assert decide(docs, LAURIUM, Endpoint(ip="52.95.150.1", port=443), "Egress") == "Deny"
    assert decide(docs, pod("api"), pod("laurium", 8000), "Egress") == "Allow"
    assert decide(docs, pod("api"), pod("arcadedb", 2480), "Egress") == "Allow"


def test_the_evaluator_lets_an_all_selector_through_as_today() -> None:
    """Today's allow-egress shape: every pod to every pod and the nets, before the deny."""
    today = [
        _calico("default.ospreyflow-allow-egress", 100, "all()",
                [{"action": "Allow", "destination": {"selector": "all()"}},
                 {"action": "Allow", "destination": {"nets": ["10.0.0.0/16"]}}]),
        _calico("default.ospreyflow-deny-egress", 200, "all()", [{"action": "Deny"}]),
    ]  # fmt: skip
    assert decide(today, LAURIUM, pod("arcadedb", 2480), "Egress") == "Allow"
    assert decide(today, LAURIUM, Endpoint(ip="10.0.3.4", port=5432), "Egress") == "Allow"
    assert decide(today, LAURIUM, Endpoint(ip="52.95.150.1", port=443), "Egress") == "Deny"


def test_the_evaluator_refuses_a_selector_it_cannot_read() -> None:
    with pytest.raises(AssertionError, match="cannot read"):
        calico_selects("has(app.kubernetes.io/name)", {})
