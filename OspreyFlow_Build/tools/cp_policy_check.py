"""`make cp-policy-check` (`spec/06_DECISIONS.md` ADR-148 decision 14): the `cloud-platform`
profile rendered, the chart templated from it with Helm, and every manifest held to the shared
platform's rules. Red on:

- a pod or container that may run as root: no `runAsNonRoot: true`, or no numeric `runAsUser`
  (the image's own user decides then, perhaps by name, which `runAsNonRoot` cannot check);
- a numeric user other than 10001 (ADR-148 decision 3);
- a group other than 10001 (`runAsGroup`, `fsGroup`), or a supplementary group, except group 0 for
  the one image built for group 0 (Keycloak, until P10; ADR-148 Amendment 1 item 4);
- a privileged container, one that may gain privilege, or one that keeps a capability;
- a port below 1024 (a container's, or a Service's);
- a `ReadWriteMany` claim, a claim's or a StatefulSet's;
- a `hostPath` volume;
- an image not from the profile's registry;
- a namespace without the deny-egress policy (Calico's, every pod, egress, deny), or one whose
  deny has no `order` or an order of 1000 or more, so the namespace's Kubernetes policies (at 1000)
  would decide egress before it (`deny-order`);
- a Calico Allow without its protocol and ports (`allow-ports`): only the rule to the cluster's API
  server by its `kubernetes` Service carries its protocol alone, as Calico takes no ports there;
- a Calico selector or namespace selector this check cannot narrow (`unreadable-selector`): an
  empty one, `has(...)`, a part-of label, `all()` in a rule; a DNS rule to any namespace but the
  platform's DNS's is no DNS rule;
- our Secret, whole or by key, to a pod not given it (`whole-secret`): by `envFrom`, a key, a
  `secret` volume or a `projected` one; a model engine's key to the gateway only for this
  deployment's keyed engines;
- a token mounted on a pod that calls no Kubernetes API, or under any account but its own; the
  bucket role's account on any pod but IRSA's, the gateway's on any but the gateway (`token`);
- **egress opened by one rule** (decision 7): an allowing egress rule with no destination, or one
  whose networks are a default route or wider than `schemas.deployment.EGRESS_WIDEST_PREFIX`
  (Calico's, or a Kubernetes policy's);
- **a pod other tenants may reach**: one no ingress policy selects (so every address may), or an
  ingress rule admitting anything but the namespace's own pods and the platform's ingress
  controller's namespace (an address block, another namespace, every source);
- a container with no memory request and limit, or no CPU request (a namespace's LimitRange would
  otherwise give it the platform's defaults, the stores included);
- a pod whose `fsGroup` is applied by walking its volumes at every start (no
  `fsGroupChangePolicy: OnRootMismatch`);
- an image of ours whose Dockerfile does not run as 10001:10001.

Each rule is shown red on a planted fault in `tests/cp_policy_check/test_cp_policy_check.py`, in the
shape Helm emits it. The platform's own Gatekeeper constraints are not published to us; when they
are, they join here (ADR-148 decision 14).

    python -m tools.cp_policy_check                       # the fixture configurations
    python -m tools.cp_policy_check --config osprey.yaml  # a deployment's own
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import ipaddress
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.helm_chart import template
from tools.licence_check import _instructions

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"
FIXTURES = BUILD / "tests" / "fixtures" / "cloud_platform"
UID = 10001

POD_KINDS = {"Deployment", "StatefulSet", "Job", "DaemonSet", "ReplicaSet", "Pod", "CronJob"}
CALICO = ("projectcalico.org/", "crd.projectcalico.org/")
#: What a Calico egress destination may select by, any one of which makes it something narrower
#: than "anywhere" (a `notNets` or `ports` alone does not).
CALICO_DESTINATIONS = {"nets", "selector", "namespaceSelector", "serviceAccounts", "services"}

#: The workloads allowed group 0 as a supplementary group, and why. Held here on its own, not read
#: from the harness's `profile.yaml`, so a render that widens that list is refused here.
GROUP_ZERO_ALLOWED = {
    "keycloak": "its image is built for any user in group 0 and builds itself at start (until P10)"
}


@dataclass(frozen=True)
class Violation:
    rule: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.where}: {self.detail}"


@dataclass(frozen=True)
class Target:
    """What one configuration renders to, and what the check holds it to."""

    values: str
    registry: str
    namespace: str
    #: Where the platform's ingress controller runs: the only other namespace admitted.
    controller_namespace: str
    #: `cloud_platform.shape` (ADR-148 Amendment 5): the poc shape's own rules apply to `poc`.
    shape: str = "standard"
    #: The platform's DNS namespace and accounts (IRSA's bucket role's, the gateway's own).
    dns_namespace: str | None = None
    irsa_account: str | None = None
    gateway_account: str | None = None


def _name(doc: dict[str, Any]) -> str:
    return f"{doc.get('kind')}/{(doc.get('metadata') or {}).get('name')}"


def _template(doc: dict[str, Any]) -> dict[str, Any] | None:
    kind = doc.get("kind")
    if kind not in POD_KINDS:
        return None
    spec = doc.get("spec") or {}
    if kind == "Pod":
        return doc
    if kind == "CronJob":
        spec = (spec.get("jobTemplate") or {}).get("spec") or {}
    return spec.get("template") or {}


def pod_spec(doc: dict[str, Any]) -> dict[str, Any] | None:
    template_ = _template(doc)
    return None if template_ is None else template_.get("spec") or {}


def _pod_labels(doc: dict[str, Any]) -> dict[str, str]:
    return ((_template(doc) or {}).get("metadata") or {}).get("labels") or {}


def _containers(spec: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for field in ("initContainers", "containers", "ephemeralContainers"):
        yield from spec.get(field) or []


def _pod_rules(doc: dict[str, Any], spec: dict[str, Any], registry: str) -> Iterator[Violation]:
    where = _name(doc)
    pod = spec.get("securityContext") or {}
    if pod.get("fsGroup", UID) != UID:
        yield Violation("other-gid", where, f"fsGroup is {pod['fsGroup']!r}, not {UID}")
    if "fsGroup" in pod and pod.get("fsGroupChangePolicy") != "OnRootMismatch":
        yield Violation(
            "fs-group-walk", where,
            "fsGroup with no fsGroupChangePolicy: OnRootMismatch: every start walks the volumes",
        )  # fmt: skip
    allowed = {0} if (doc.get("metadata") or {}).get("name") in GROUP_ZERO_ALLOWED else set()
    extra = [g for g in pod.get("supplementalGroups") or [] if g != UID and g not in allowed]
    if extra:
        yield Violation("supplementary-group", where, f"supplementalGroups {extra!r}")
    for volume in spec.get("volumes") or []:
        if "hostPath" in volume:
            yield Violation(
                "hostPath", where, f"volume {volume.get('name')} mounts the node's disk"
            )
    for container in _containers(spec):
        at = f"{where} container {container.get('name')}"
        own = container.get("securityContext") or {}
        non_root = own.get("runAsNonRoot", pod.get("runAsNonRoot"))
        user = own.get("runAsUser", pod.get("runAsUser"))
        if non_root is not True:
            yield Violation("root", at, "runAsNonRoot is not true")
        if user is None:
            yield Violation("named-uid", at, "no numeric runAsUser: the image's user decides")
        elif not isinstance(user, int) or isinstance(user, bool) or user <= 0:
            yield Violation("root", at, f"runAsUser is {user!r}")
        elif user != UID:
            yield Violation("other-uid", at, f"runAsUser is {user}, not {UID}")
        group = own.get("runAsGroup", pod.get("runAsGroup"))
        if group != UID:
            yield Violation("other-gid", at, f"runAsGroup is {group!r}, not {UID}")
        if own.get("privileged") is True:
            yield Violation("privileged", at, "privileged: true")
        if own.get("allowPrivilegeEscalation") is not False:
            yield Violation("privileged", at, "allowPrivilegeEscalation is not false")
        caps = own.get("capabilities") or {}
        if "ALL" not in (caps.get("drop") or []) or caps.get("add"):
            yield Violation("privileged", at, f"capabilities are not all dropped: {caps!r}")
        for port in container.get("ports") or []:
            number = port.get("containerPort")
            if isinstance(number, int) and number < 1024:
                yield Violation("low-port", at, f"containerPort {number}")
        image = str(container.get("image", ""))
        if not image.startswith(registry.rstrip("/") + "/"):
            yield Violation("foreign-registry", at, f"{image} is not from {registry}")
        resources = container.get("resources") or {}
        missing = [
            f"{part}.{what}"
            for part, what in (("requests", "cpu"), ("requests", "memory"), ("limits", "memory"))
            if not (resources.get(part) or {}).get(what)
        ]
        if missing:
            yield Violation("no-resources", at, "no " + ", ".join(missing))


def _claims_rwx(modes: Iterable[str] | None) -> bool:
    return "ReadWriteMany" in (modes or [])


def _is_calico(doc: dict[str, Any]) -> bool:
    return str(doc.get("apiVersion", "")).startswith(CALICO) and doc.get("kind") in {
        "NetworkPolicy",
        "GlobalNetworkPolicy",
    }


def _is_kubernetes_policy(doc: dict[str, Any]) -> bool:
    return doc.get("kind") == "NetworkPolicy" and str(doc.get("apiVersion", "")).startswith(
        "networking.k8s.io/"
    )


#: Where Calico places the namespace's Kubernetes policies: a deny at this order or after it, or
#: with no order (Calico's last), lets them decide egress first (ADR-148 Amendment 5 point 21).
KUBERNETES_POLICY_ORDER = 1000


def _selects_every_pod(spec: dict[str, Any]) -> bool:
    """A Calico policy's own selector: missing or empty is every pod, as `all()` is."""
    return str(spec.get("selector") or "all()").replace(" ", "") == "all()"


def _is_egress_deny(doc: dict[str, Any]) -> bool:
    """Calico's deny: every pod, egress, a rule that denies with nothing to match."""
    if not _is_calico(doc):
        return False
    spec = doc.get("spec") or {}
    if not _selects_every_pod(spec) or "Egress" not in (spec.get("types") or []):
        return False
    return any(
        set(rule) == {"action"} and rule["action"] == "Deny" for rule in spec.get("egress") or []
    )


def _orders_first(doc: dict[str, Any]) -> bool:
    order = (doc.get("spec") or {}).get("order")
    return (
        isinstance(order, (int, float))
        and not isinstance(order, bool)
        and (order < KUBERNETES_POLICY_ORDER)
    )


def _denies_egress(doc: dict[str, Any]) -> bool:
    """The deny, run before the namespace's Kubernetes policies (`order` below 1000)."""
    return _is_egress_deny(doc) and _orders_first(doc)


def _deny_order(doc: dict[str, Any]) -> Iterator[Violation]:
    if _is_egress_deny(doc) and not _orders_first(doc):
        order = (doc.get("spec") or {}).get("order")
        yield Violation(
            "deny-order", _name(doc),
            f"order {order!r}: the deny must run before the Kubernetes policies (order "
            f"{KUBERNETES_POLICY_ORDER}), or they decide egress",
        )  # fmt: skip


def _too_wide(net: str) -> str:
    from schemas.deployment import too_wide_for_egress

    try:
        ipaddress.ip_network(net, strict=False)
    except ValueError:
        return f"{net!r} is not a network"
    return too_wide_for_egress(net) or ""


#: ADR-148 Amendment 5 point 22: who may read our Secret whole, and the keys of it each other pod
#: is given by name. Default-deny: a pod not in `NAMED_SECRET_ALLOWED` may hold no key of ours, so a
#: new workload (case-b's Laurium) is refused one until it is listed here. Held here on its own, as
#: the group-0 list is, not read from the harness's `profile.yaml`, so a render that widens either
#: is refused here.
WHOLE_SECRET_ALLOWED = frozenset({"api", "worker", "report-sync"})
NAMED_SECRET_ALLOWED: dict[str, frozenset[str]] = {
    "arcadedb": frozenset({"OSPREY_ARCADEDB_CLUSTER_TOKEN", "OSPREY_ARCADEDB_PASSWORD"}),
    "clickhouse": frozenset({"OSPREY_CLICKHOUSE_PASSWORD"}),
    "keycloak": frozenset({"OSPREY_KEYCLOAK_ADMIN", "OSPREY_KEYCLOAK_ADMIN_PASSWORD",
                           "OSPREY_KEYCLOAK_DB_PASSWORD"}),
    # The engines' keys are not listed: this deployment's keyed engines' alone (`_engine_keys`),
    # the single `models.provider`'s (`OSPREY_MODEL_PROVIDER_KEY`) only when it is keyed.
    "litellm": frozenset({"OSPREY_LITELLM_DB_PASSWORD", "OSPREY_LITELLM_MASTER_SECRET",
                          "OSPREY_LITELLM_SALT_SECRET"}),
    "superset": frozenset({"SUPERSET_SECRET_KEY", "SUPERSET_OIDC_CLIENT_SECRET",
                           "SUPERSET_GUEST_TOKEN_SECRET", "SUPERSET_EMBEDDER_PASSWORD",
                           "REPORT_MART_READER_PASSWORD"}),
}  # fmt: skip
#: The gateway also holds each of this deployment's keyed engines' keys (ADR-135 Amendments 4 and
#: 7): read from the deployment's own `osprey.yaml` in what Helm printed, never by a prefix, so an
#: IAM-role engine's held key is refused it.
ENGINE_KEYS_TO = "litellm"


def _engine_keys(docs: list[dict[str, Any]]) -> frozenset[str]:
    """This deployment's keyed engines' keys, from the `osprey.yaml` Helm printed (the files
    ConfigMap): `harness.render.model_key_variables`, the variables the render itself names."""
    import yaml
    from harness.render import model_key_variables

    from schemas.deployment import OspreyConfig

    for doc in docs:
        if doc.get("kind") == "ConfigMap" and "osprey.yaml" in (doc.get("data") or {}):
            config = OspreyConfig.model_validate(yaml.safe_load(doc["data"]["osprey.yaml"]))
            return frozenset(model_key_variables(config).values())
    return frozenset()


def _pod_name(doc: dict[str, Any]) -> str:
    """A pod by its workload's name: a Job's own name carries a hash of its steps."""
    return str(_pod_labels(doc).get("app.kubernetes.io/name")
               or (doc.get("metadata") or {}).get("name"))  # fmt: skip


def _secret_volumes(spec: dict[str, Any], secret: str) -> Iterator[tuple[str, list[str] | None]]:
    """Each volume of `secret`'s: its name, and the keys it carries (None: every key). A `secret`
    volume, or a `projected` one's `secret` source."""
    for volume in spec.get("volumes") or []:
        held = volume.get("secret") or {}
        if held.get("secretName") == secret:
            items = held.get("items")
            yield str(volume.get("name")), [i.get("key") for i in items] if items else None
        for source in (volume.get("projected") or {}).get("sources") or []:
            held = source.get("secret") or {}
            if held.get("name") == secret:
                items = held.get("items")
                yield str(volume.get("name")), [i.get("key") for i in items] if items else None


def _whole_secret(
    doc: dict[str, Any], spec: dict[str, Any], secret: str, engine_keys: frozenset[str]
) -> Iterator[Violation]:
    """Amendment 5 point 22: our Secret (`secrets.name` in the values: the stores' passwords, the
    gateway's master key) whole only to the workloads that read it whole, and to every other pod
    only the keys it is listed as reading, by name; none to a pod not listed. Read however the pod
    reads it: `envFrom`, a key, or a volume, `secret` or `projected`."""
    workload = _pod_name(doc)
    if workload in WHOLE_SECRET_ALLOWED:
        return
    allowed = NAMED_SECRET_ALLOWED.get(workload, frozenset())
    if workload == ENGINE_KEYS_TO:
        allowed = allowed | engine_keys
    for volume, keys in _secret_volumes(spec, secret):
        at = f"{_name(doc)} volume {volume}"
        if keys is None:
            yield Violation("whole-secret", at, f"mounts {secret} whole")
        for key in [k for k in keys or [] if k not in allowed]:
            yield Violation("whole-secret", at, f"is given {secret}'s {key}")
    for container in _containers(spec):
        at = f"{_name(doc)}/{container.get('name')}"
        for source in container.get("envFrom") or []:
            if (source.get("secretRef") or {}).get("name") == secret:
                yield Violation("whole-secret", at, f"reads {secret} whole")
        for variable in container.get("env") or []:
            ref = (variable.get("valueFrom") or {}).get("secretKeyRef") or {}
            key = str(ref.get("key"))
            if ref.get("name") == secret and key not in allowed:
                yield Violation("whole-secret", at, f"is given {secret}'s {key}")


#: Amendment 5 point 24: the pods that may mount their service account's token, each only with an
#: account of its own: IRSA's (the Conduit, the workers, the report sync), the gateway's with
#: Bedrock, and P9's backup and restore pods (their web identity; a restore also asks the API
#: whether the writers have stopped). Held here, not read from the render.
TOKEN_ALLOWED = frozenset({"api", "worker", "report-sync", "litellm",
                           "backup", "backup-claims", "restore", "restore-claims"})  # fmt: skip


#: Whose account each holds: IRSA's bucket role (the platform's `secrets.irsa.service_account`) is
#: the Conduit's, the workers' and the report sync's alone; the gateway's own role
#: (`gateway_service_account`) the gateway's alone; P9's pods each an account of their own.
IRSA_PODS = frozenset({"api", "worker", "report-sync"})


def _token(
    doc: dict[str, Any], spec: dict[str, Any], irsa: str, gateway: str | None
) -> Iterator[Violation]:
    """Amendment 5 point 24: a pod whose token is mounted (Kubernetes' default, unless
    `automountServiceAccountToken` is false) must be one that needs it, under its own account. An
    account is held to its pods whether or not the token is mounted: IRSA's webhook gives a pod its
    role's web identity by the account alone."""
    pod = _pod_name(doc)
    where = _name(doc)
    # `serviceAccount` is the older field Kubernetes still reads when `serviceAccountName` is unset.
    account = str(spec.get("serviceAccountName") or spec.get("serviceAccount") or "default")
    if account == irsa and pod not in IRSA_PODS:
        yield Violation("token", where, f"runs as {irsa}, the bucket role's account")
    if gateway and account == gateway and pod != "litellm":
        yield Violation("token", where, f"runs as {gateway}, the gateway's account")
    if spec.get("automountServiceAccountToken") is False:
        return
    if pod not in TOKEN_ALLOWED:
        yield Violation("token", where, "mounts its service account's token")
    elif account == "default":
        yield Violation("token", where, "mounts the namespace's default account's token")
    elif pod in IRSA_PODS and account != irsa:
        yield Violation("token", where, f"mounts {account}'s token, not {irsa}'s")
    elif pod == "litellm" and account != gateway:
        yield Violation("token", where, f"mounts {account}'s token, not the gateway's own")
    elif pod not in IRSA_PODS | {"litellm"} and account in {irsa, gateway}:
        yield Violation("token", where, f"mounts {account}'s token, not an account of its own")


def _dns_selector(dns_namespace: str) -> str:
    return f"kubernetes.io/metadata.name == '{dns_namespace}'"


def _is_dns(rule: dict[str, Any], dns_namespace: str) -> bool:
    """A rule to the cluster's DNS alone: the platform's DNS's namespace by name, port 53, nothing
    else."""
    destination = rule.get("destination") or {}
    return (
        rule.get("protocol") in {"UDP", "TCP"}
        and set(destination) == {"namespaceSelector", "ports"}
        and str(destination.get("namespaceSelector")).strip() == _dns_selector(dns_namespace)
        and destination.get("ports") == [53]
    )


#: The selectors this check can narrow: a pod by its workload's name, one or a list.
_BY_NAME = re.compile(r"app\.kubernetes\.io/name == '[a-z0-9-]+'")
_BY_NAMES = re.compile(r"app\.kubernetes\.io/name in \{\s*'[a-z0-9-]+'(\s*,\s*'[a-z0-9-]+')*\s*\}")


def _readable(selector: Any) -> bool:
    text = str(selector).strip() if isinstance(selector, str) else ""
    return bool(_BY_NAME.fullmatch(text) or _BY_NAMES.fullmatch(text))


def _selectors(doc: dict[str, Any], dns_namespace: str) -> Iterator[Violation]:
    """Amendment 5 point 21: every Calico selector is one this check can read, or it is refused:
    the policy's own (every pod, or a workload by name), and each rule's (a workload by name; a
    namespace only the platform's DNS's, in a DNS rule)."""
    if not _is_calico(doc):
        return
    where = _name(doc)
    spec = doc.get("spec") or {}
    own = spec.get("selector")
    if own is not None and str(own).strip() and not _selects_every_pod(spec) and not _readable(own):
        yield Violation("unreadable-selector", where, f"selects pods by {own!r}")
    if "namespaceSelector" in spec:
        yield Violation(
            "unreadable-selector", where, f"selects namespaces by {spec['namespaceSelector']!r}"
        )
    for field, peer in (("egress", "destination"), ("ingress", "source")):
        for rule in spec.get(field) or []:
            ends = rule.get(peer) or {}
            for field_name in ("notSelector", "notNamespaceSelector"):
                if field_name in ends:
                    yield Violation(
                        "unreadable-selector", where, f"a rule's {field_name} {ends[field_name]!r}"
                    )
            accounts = ends.get("serviceAccounts") or {}
            if "selector" in accounts:
                yield Violation(
                    "unreadable-selector", where,
                    f"a rule's service-account selector {accounts['selector']!r}",
                )  # fmt: skip
            if "selector" in ends and not _readable(ends["selector"]):
                yield Violation(
                    "unreadable-selector", where, f"a rule's selector {ends['selector']!r}"
                )
            if "namespaceSelector" in ends and not (
                field == "egress" and _is_dns(rule, dns_namespace)
            ):
                yield Violation(
                    "unreadable-selector", where,
                    f"a rule's namespace selector {ends['namespaceSelector']!r}: only a DNS "
                    f"rule to {dns_namespace} may name a namespace",
                )  # fmt: skip


def _is_api_server(rule: dict[str, Any]) -> bool:
    """The one Allow without ports: TCP to the cluster's API server by its `kubernetes` Service,
    which is all the rule names (Calico takes no ports beside `services` on an egress rule)."""
    return (
        rule.get("protocol") == "TCP"
        and set(rule) == {"action", "protocol", "destination"}
        and (
            rule.get("destination") == {"services": {"name": "kubernetes", "namespace": "default"}}
        )
    )


def _allow_ports(doc: dict[str, Any]) -> Iterator[Violation]:
    """Amendment 5 point 21: every Calico Allow names its protocol and its ports, each a single
    port by number: a range (`"1:65535"`) or a named port is refused."""
    if not _is_calico(doc):
        return
    for rule in (doc.get("spec") or {}).get("egress") or []:
        if rule.get("action") != "Allow" or _is_api_server(rule):
            continue
        ports = (rule.get("destination") or {}).get("ports")
        if rule.get("protocol") not in {"TCP", "UDP"} or not ports:
            yield Violation(
                "allow-ports", _name(doc), f"an Allow without its protocol and ports: {rule}"
            )
        elif not all(_one_port(port) for port in ports):
            yield Violation(
                "allow-ports", _name(doc), f"an Allow by a range or a named port: {ports}"
            )


def _one_port(port: Any) -> bool:
    return isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535


def _wide_egress(doc: dict[str, Any], dns_namespace: str) -> Iterator[Violation]:
    """ADR-148 Amendment 5 point 21: egress is each workload's own. Under a Calico policy that
    selects every pod, the only Allow is DNS: anything more would give every pod, the Glass and the
    recogniser among them, what one workload needs."""
    if not _is_calico(doc):
        return
    spec = doc.get("spec") or {}
    if not _selects_every_pod(spec):
        return
    for rule in spec.get("egress") or []:
        if rule.get("action") == "Allow" and not _is_dns(rule, dns_namespace):
            yield Violation("wide-egress", _name(doc), f"every pod allowed: {rule}")


def _names_workloads(selector: dict[str, Any]) -> bool:
    """A pod selector this check can narrow: workloads by name alone (`matchLabels` of the name, or
    one `In` expression on it). Anything else (every pod, the part-of label, `Exists`, an instance
    label) may admit every pod of ours."""
    labels = selector.get("matchLabels") or {}
    expressions = selector.get("matchExpressions") or []
    if labels and not expressions:
        return set(labels) == {"app.kubernetes.io/name"}
    if expressions and not labels and len(expressions) == 1:
        [only] = expressions
        return (only.get("key") == "app.kubernetes.io/name" and only.get("operator") == "In"
                and bool(only.get("values")))  # fmt: skip
    return False


def _wide_ingress(doc: dict[str, Any]) -> Iterator[Violation]:
    """ADR-148 Amendment 5 point 23: a pod admits, in the namespace, only the workloads whose paths
    name it; an ingress rule admitting every pod of the deployment's (or every pod) is refused."""
    if not _is_kubernetes_policy(doc) or not _admits_ingress(doc.get("spec") or {}):
        return
    for rule in (doc.get("spec") or {}).get("ingress") or []:
        for peer in rule.get("from") or []:
            if set(peer) == {"podSelector"} and not _names_workloads(peer["podSelector"] or {}):
                yield Violation("wide-ingress", _name(doc), f"admits pods it cannot name: {peer}")


def _egress_rules(doc: dict[str, Any]) -> Iterator[Violation]:
    """Decision 7: no one rule opens the namespace's egress."""
    where = _name(doc)
    spec = doc.get("spec") or {}
    if _is_calico(doc):
        for rule in spec.get("egress") or []:
            if rule.get("action") != "Allow":
                continue
            destination = rule.get("destination") or {}
            if not CALICO_DESTINATIONS & set(destination):
                yield Violation("open-egress", where, f"an Allow rule with no destination: {rule}")
            for net in destination.get("nets") or []:
                if why := _too_wide(net):
                    yield Violation("open-egress", where, why)
    elif _is_kubernetes_policy(doc):
        for rule in spec.get("egress") or []:
            if not rule.get("to"):
                yield Violation("open-egress", where, f"an egress rule to everywhere: {rule}")
            for peer in rule.get("to") or []:
                cidr = (peer.get("ipBlock") or {}).get("cidr")
                if cidr and (why := _too_wide(cidr)):
                    yield Violation("open-egress", where, why)


def _matches(selector: dict[str, Any], labels: dict[str, str]) -> bool:
    """A Kubernetes label selector against a pod's labels (`{}` selects every pod)."""
    if any(labels.get(k) != v for k, v in (selector.get("matchLabels") or {}).items()):
        return False
    for expression in selector.get("matchExpressions") or []:
        key, operator = expression["key"], expression["operator"]
        values = expression.get("values") or []
        held = labels.get(key)
        if operator == "In" and held not in values:
            return False
        if operator == "NotIn" and held in values:
            return False
        if operator == "Exists" and key not in labels:
            return False
        if operator == "DoesNotExist" and key in labels:
            return False
    return True


def _admits_ingress(spec: dict[str, Any]) -> bool:
    types = spec.get("policyTypes")
    return "Ingress" in types if types else True  # Kubernetes' own default


def _calico_admits_ingress(spec: dict[str, Any]) -> bool:
    """Calico's own default: a policy with no `types` is an Ingress policy unless it has egress
    rules and no ingress rules."""
    types = spec.get("types")
    if types:
        return "Ingress" in types
    return bool(spec.get("ingress")) or not spec.get("egress")


def _ingress_rules(docs: list[dict[str, Any]], controller_namespace: str) -> Iterator[Violation]:
    """Other tenants: every pod is selected by an ingress policy, and every ingress rule admits the
    namespace's own pods or the platform's ingress controller's namespace, nothing else."""
    policies = [
        d for d in docs if _is_kubernetes_policy(d) and _admits_ingress(d.get("spec") or {})
    ]
    selectors = [(p.get("spec") or {}).get("podSelector") or {} for p in policies]
    controller = {"kubernetes.io/metadata.name": controller_namespace}
    for doc in docs:
        if _template(doc) is None:
            continue
        labels = _pod_labels(doc)
        if not any(_matches(selector, labels) for selector in selectors):
            yield Violation(
                "ingress-isolation", _name(doc),
                "no ingress policy selects its pods, so any address may reach them",
            )  # fmt: skip
    for policy in policies:
        where = _name(policy)
        for rule in (policy.get("spec") or {}).get("ingress") or []:
            if not rule.get("from"):
                yield Violation("ingress-isolation", where, f"a rule admitting any source: {rule}")
            for peer in rule.get("from") or []:
                if "ipBlock" in peer:
                    yield Violation("ingress-isolation", where, f"admits {peer['ipBlock']}")
                elif "namespaceSelector" in peer:
                    selector = peer["namespaceSelector"] or {}
                    if selector != {"matchLabels": controller}:
                        yield Violation(
                            "ingress-isolation", where,
                            f"admits namespaces {selector or 'all'}, not the ingress "
                            f"controller's ({controller_namespace}) alone",
                        )  # fmt: skip
    for doc in docs:
        if not _is_calico(doc) or not _calico_admits_ingress(doc.get("spec") or {}):
            continue
        for rule in (doc.get("spec") or {}).get("ingress") or []:
            source = rule.get("source") or {}
            if rule.get("action") == "Allow" and set(source) != {"selector"}:
                yield Violation(
                    "ingress-isolation", _name(doc),
                    f"a Calico rule admitting beyond the namespace's own pods: {rule}",
                )  # fmt: skip


def check_manifests(
    docs: list[dict[str, Any]],
    registry: str,
    *,
    controller_namespace: str,
    secret: str | None = None,
    dns_namespace: str | None = None,
    irsa_account: str | None = None,
    gateway_account: str | None = None,
) -> list[Violation]:
    """Every rule but the Dockerfiles', over what `helm template` printed. `secret` is the values'
    `secrets.name`; the DNS namespace and the accounts are the platform's (`check` passes each from
    its target; left out, the chart's default name and the fixtures' platform's)."""
    defaults = _defaults()
    secret = secret or defaults["secret"]
    dns_namespace = dns_namespace or defaults["dns_namespace"]
    irsa_account = irsa_account or defaults["irsa_account"]
    gateway_account = gateway_account or defaults["gateway_account"]
    engine_keys = _engine_keys(docs)
    found: list[Violation] = []
    for doc in docs:
        spec = pod_spec(doc)
        if spec is not None:
            found += _pod_rules(doc, spec, registry)
            found += _whole_secret(doc, spec, secret, engine_keys)
            found += _token(doc, spec, irsa_account, gateway_account)
        found += _egress_rules(doc)
        found += _wide_egress(doc, dns_namespace)
        found += _wide_ingress(doc)
        found += _deny_order(doc)
        found += _selectors(doc, dns_namespace)
        found += _allow_ports(doc)
        kind = doc.get("kind")
        if kind == "PersistentVolumeClaim" and _claims_rwx(
            (doc.get("spec") or {}).get("accessModes")
        ):
            found.append(Violation("rwx", _name(doc), "accessModes ReadWriteMany"))
        if kind == "StatefulSet":
            for claim in (doc.get("spec") or {}).get("volumeClaimTemplates") or []:
                if _claims_rwx((claim.get("spec") or {}).get("accessModes")):
                    found.append(Violation("rwx", _name(doc), f"claim {claim['metadata']['name']}"))
        if kind == "Service":
            for port in (doc.get("spec") or {}).get("ports") or []:
                for field in ("port", "targetPort"):
                    number = port.get(field)
                    if isinstance(number, int) and number < 1024:
                        found.append(Violation("low-port", _name(doc), f"{field} {number}"))
    found += _ingress_rules(docs, controller_namespace)
    if not any(_denies_egress(doc) for doc in docs):
        found.append(Violation("no-deny-egress", "namespace", "no Calico policy denies egress"))
    return found


@functools.cache
def _defaults() -> dict[str, str | None]:
    """The chart's own `secrets.name` and the fixtures' platform's DNS namespace and accounts."""
    import yaml
    from harness.cloud_platform.settings import load_platform

    platform = load_platform("client")
    chart = yaml.safe_load(
        (CORE / "deploy" / "helm" / "ospreyflow" / "values.yaml").read_text(encoding="utf-8")
    )
    return {
        "secret": chart["secrets"]["name"],
        "dns_namespace": platform.egress.dns_namespace,
        "irsa_account": platform.secrets.irsa.service_account,
        "gateway_account": platform.secrets.irsa.gateway_service_account,
    }


def final_user(text: str) -> str | None:
    """The `USER` the image's last stage runs as, or None when its last stage sets none; read with
    `make licence-check`'s parser (continued lines joined, comments left out, any case)."""
    user: str | None = None
    for instruction in _instructions(text):
        word, _, rest = instruction.partition(" ")
        if word.upper() == "FROM":
            user = None  # a new stage starts as its base's user
        elif word.upper() == "USER":
            user = rest.strip()
    return user


def check_dockerfiles(paths: Iterable[Path]) -> list[Violation]:
    return [
        Violation("named-uid", str(path), f"USER {user} is not {UID}:{UID}")
        for path in paths
        if (user := final_user(path.read_text(encoding="utf-8"))) != f"{UID}:{UID}"
    ]


def our_dockerfiles() -> list[Path]:
    return sorted(
        p for p in CORE.rglob("Dockerfile*")
        if p.is_file() and not {"node_modules", ".venv"} & set(p.parts)
    )  # fmt: skip


def _resolver(ref: str) -> str:
    """A stand-in digest for each reference, so the check needs no registry and is stable."""
    return "sha256:" + hashlib.sha256(ref.encode()).hexdigest()


def helm_template(values: str, namespace: str = "ospreyflow-dev") -> list[dict[str, Any]]:
    """The chart's manifests for `values`, into `namespace` (`tools.helm_chart`'s runner)."""
    return template(values, namespace)


def render(config_path: Path) -> Target:
    """The profile's `values.yaml` for `config_path`, and what the check holds it to. A
    configuration of another profile is refused in words, not with a traceback."""
    from harness.cloud_platform.settings import load_platform
    from harness.render import load_config
    from harness.render import render as render_config

    config = load_config(config_path)
    cloud = config.cloud_platform
    if cloud is None:
        raise SystemExit(
            f"{config_path} is profile: {config.profile.value}, and `make cp-policy-check` "
            "checks a cloud-platform deployment's render alone (profile: cloud-platform)"
        )
    if cloud.registry is None or cloud.namespace is None:
        raise SystemExit(f"{config_path} names no cloud_platform.registry or namespace")
    platform = load_platform(cloud.platform)
    return Target(
        values=render_config(config, resolver=_resolver).artefacts["values.yaml"],
        registry=cloud.registry,
        namespace=cloud.namespace,
        controller_namespace=platform.ingress.controller_namespace,
        shape=cloud.shape,
        dns_namespace=platform.egress.dns_namespace,
        irsa_account=platform.secrets.irsa.service_account,
        gateway_account=platform.secrets.irsa.gateway_service_account,
    )


def render_values(config_path: Path) -> tuple[str, str]:
    """The profile's `values.yaml` for `config_path`, and the registry it names."""
    target = render(config_path)
    return target.values, target.registry


def check(target: Target) -> tuple[int, list[Violation]]:
    """`target` templated into its own namespace and held to every manifest rule."""
    import yaml

    docs = helm_template(target.values, target.namespace)
    violations = check_manifests(
        docs, target.registry, controller_namespace=target.controller_namespace,
        secret=yaml.safe_load(target.values)["secrets"]["name"],
        dns_namespace=target.dns_namespace, irsa_account=target.irsa_account,
        gateway_account=target.gateway_account,
    )  # fmt: skip
    if target.shape == "poc":
        violations += list(poc_rules(docs))
    return len(docs), violations


def poc_rules(docs: list[dict[str, Any]]) -> Iterator[Violation]:
    """ADR-148 Amendment 5: in the poc shape every container names a CPU limit, so a namespace's
    LimitRange gives it none of its own and a quota on `limits.cpu` admits its pod."""
    for doc in docs:
        spec = pod_spec(doc)
        for container in _containers(spec or {}):
            if not ((container.get("resources") or {}).get("limits") or {}).get("cpu"):
                yield Violation(
                    "no-cpu-limit", f"{_name(doc)}/{container.get('name')}", "no limits.cpu"
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--config",
        type=Path,
        action="append",
        help="an osprey.yaml at profile: cloud-platform (default: the fixtures)",
    )
    args = parser.parse_args(argv)
    configs = args.config or sorted(FIXTURES.glob("*.yaml"))
    found = check_dockerfiles(our_dockerfiles())
    for config_path in configs:
        count, violations = check(render(config_path))
        print(f"{config_path.name}: {count} manifests, {len(violations)} violation(s)")
        found += violations
    for violation in found:
        print(f"  {violation}")
    print(f"cp-policy-check: {len(found)} violation(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
