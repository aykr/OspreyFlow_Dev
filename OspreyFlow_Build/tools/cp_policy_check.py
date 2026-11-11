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
- a namespace without the deny-egress policy (Calico's, every pod, egress, deny);
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
import hashlib
import ipaddress
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


def _denies_egress(doc: dict[str, Any]) -> bool:
    """Calico's deny: every pod (`all()`), egress, a rule that denies with nothing to match."""
    if not _is_calico(doc):
        return False
    spec = doc.get("spec") or {}
    if spec.get("selector", "all()").replace(" ", "") != "all()":
        return False
    if "Egress" not in (spec.get("types") or []):
        return False
    return any(
        set(rule) == {"action"} and rule["action"] == "Deny" for rule in spec.get("egress") or []
    )


def _too_wide(net: str) -> str:
    from schemas.deployment import too_wide_for_egress

    try:
        ipaddress.ip_network(net, strict=False)
    except ValueError:
        return f"{net!r} is not a network"
    return too_wide_for_egress(net) or ""


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
        if not _is_calico(doc) or "Ingress" not in ((doc.get("spec") or {}).get("types") or []):
            continue
        for rule in (doc.get("spec") or {}).get("ingress") or []:
            source = rule.get("source") or {}
            if rule.get("action") == "Allow" and set(source) != {"selector"}:
                yield Violation(
                    "ingress-isolation", _name(doc),
                    f"a Calico rule admitting beyond the namespace's own pods: {rule}",
                )  # fmt: skip


def check_manifests(
    docs: list[dict[str, Any]], registry: str, *, controller_namespace: str
) -> list[Violation]:
    """Every rule but the Dockerfiles', over what `helm template` printed."""
    found: list[Violation] = []
    for doc in docs:
        spec = pod_spec(doc)
        if spec is not None:
            found += _pod_rules(doc, spec, registry)
        found += _egress_rules(doc)
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
    )


def render_values(config_path: Path) -> tuple[str, str]:
    """The profile's `values.yaml` for `config_path`, and the registry it names."""
    target = render(config_path)
    return target.values, target.registry


def check(target: Target) -> tuple[int, list[Violation]]:
    """`target` templated into its own namespace and held to every manifest rule."""
    docs = helm_template(target.values, target.namespace)
    violations = check_manifests(
        docs, target.registry, controller_namespace=target.controller_namespace
    )
    return len(docs), violations


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
