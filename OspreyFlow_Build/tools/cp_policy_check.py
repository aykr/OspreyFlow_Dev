"""`make cp-policy-check` (`spec/06_DECISIONS.md` ADR-148 decision 14): the `cloud-platform`
profile rendered, the chart templated from it with Helm, and every manifest held to the shared
platform's rules. Red on:

- a pod or container that may run as root: no `runAsNonRoot: true`, or no numeric `runAsUser`
  (the image's own user decides then, perhaps by name, which `runAsNonRoot` cannot check);
- a privileged container, one that may gain privilege, or one that keeps a capability;
- a port below 1024 (a container's, or a Service's);
- a `ReadWriteMany` claim, a claim's or a StatefulSet's;
- a `hostPath` volume;
- an image not from the profile's registry;
- a namespace without the deny-egress policy (Calico's, every pod, egress, deny);
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
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"
CHART = CORE / "deploy" / "helm" / "ospreyflow"
FIXTURES = BUILD / "tests" / "fixtures" / "cloud_platform"
HELM = "alpine/helm:3.16.3"
UID = 10001

POD_KINDS = {"Deployment", "StatefulSet", "Job", "DaemonSet", "ReplicaSet", "Pod", "CronJob"}


@dataclass(frozen=True)
class Violation:
    rule: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.where}: {self.detail}"


def _name(doc: dict[str, Any]) -> str:
    return f"{doc.get('kind')}/{(doc.get('metadata') or {}).get('name')}"


def pod_spec(doc: dict[str, Any]) -> dict[str, Any] | None:
    kind = doc.get("kind")
    if kind not in POD_KINDS:
        return None
    spec = doc.get("spec") or {}
    if kind == "Pod":
        return spec
    if kind == "CronJob":
        spec = (spec.get("jobTemplate") or {}).get("spec") or {}
    return (spec.get("template") or {}).get("spec") or {}


def _containers(spec: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for field in ("initContainers", "containers", "ephemeralContainers"):
        yield from spec.get(field) or []


def _pod_rules(doc: dict[str, Any], spec: dict[str, Any], registry: str) -> Iterator[Violation]:
    where = _name(doc)
    pod = spec.get("securityContext") or {}
    for volume in spec.get("volumes") or []:
        if "hostPath" in volume:
            yield Violation("hostPath", where, f"volume {volume.get('name')} mounts the node's disk")
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


def _claims_rwx(modes: Iterable[str] | None) -> bool:
    return "ReadWriteMany" in (modes or [])


def _denies_egress(doc: dict[str, Any]) -> bool:
    """Calico's deny: every pod (`all()`), egress, a rule that denies with nothing to match."""
    if not str(doc.get("apiVersion", "")).startswith(("projectcalico.org/", "crd.projectcalico.org/")):
        return False
    if doc.get("kind") not in {"NetworkPolicy", "GlobalNetworkPolicy"}:
        return False
    spec = doc.get("spec") or {}
    if spec.get("selector", "all()").replace(" ", "") != "all()":
        return False
    if "Egress" not in (spec.get("types") or []):
        return False
    return any(set(rule) == {"action"} and rule["action"] == "Deny" for rule in spec.get("egress") or [])


def check_manifests(docs: list[dict[str, Any]], registry: str) -> list[Violation]:
    """Every rule but the Dockerfiles', over what `helm template` printed."""
    found: list[Violation] = []
    for doc in docs:
        spec = pod_spec(doc)
        if spec is not None:
            found += _pod_rules(doc, spec, registry)
        kind = doc.get("kind")
        if kind == "PersistentVolumeClaim" and _claims_rwx((doc.get("spec") or {}).get("accessModes")):
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
    if not any(_denies_egress(doc) for doc in docs):
        found.append(Violation("no-deny-egress", "namespace", "no Calico policy denies egress"))
    return found


def dockerfile_user(text: str) -> str | None:
    last_stage = re.split(r"^\s*FROM\s", text, flags=re.MULTILINE | re.IGNORECASE)[-1]
    users = re.findall(r"^\s*USER\s+(\S+)\s*$", last_stage, flags=re.MULTILINE | re.IGNORECASE)
    return users[-1] if users else None


def check_dockerfiles(paths: Iterable[Path]) -> list[Violation]:
    return [
        Violation("named-uid", str(path), f"USER {user} is not {UID}:{UID}")
        for path in paths
        if (user := dockerfile_user(path.read_text(encoding="utf-8"))) != f"{UID}:{UID}"
    ]


def our_dockerfiles() -> list[Path]:
    return sorted(
        p for p in CORE.rglob("Dockerfile*")
        if p.is_file() and not {"node_modules", ".venv"} & set(p.parts)
    )  # fmt: skip


def _resolver(ref: str) -> str:
    """A stand-in digest for each reference, so the check needs no registry and is stable."""
    return "sha256:" + hashlib.sha256(ref.encode()).hexdigest()


def helm_template(values: str) -> list[dict[str, Any]]:
    done = subprocess.run(
        ["docker", "run", "--rm", "-i", "-v", f"{CHART}:/chart:ro", HELM, "template", "ospreyflow",
         "/chart", "--namespace", "ospreyflow-dev", "-f", "-"],
        input=values, capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    if done.returncode != 0:
        raise RuntimeError(f"helm template failed: {done.stderr or done.stdout}")
    return [doc for doc in yaml.safe_load_all(done.stdout) if doc]


def render_values(config_path: Path) -> tuple[str, str]:
    """The profile's `values.yaml` for `config_path`, and the registry it names."""
    from harness.render import load_config, render

    config = load_config(config_path)
    registry = config.cloud_platform.registry
    if registry is None:
        raise SystemExit(f"{config_path} names no cloud_platform.registry")
    return render(config, resolver=_resolver).artefacts["values.yaml"], registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, action="append",
                        help="an osprey.yaml at profile: cloud-platform (default: the fixtures)")
    args = parser.parse_args(argv)
    configs = args.config or sorted(FIXTURES.glob("*.yaml"))
    found = check_dockerfiles(our_dockerfiles())
    for config_path in configs:
        values, registry = render_values(config_path)
        docs = helm_template(values)
        violations = check_manifests(docs, registry)
        print(f"{config_path.name}: {len(docs)} manifests, {len(violations)} violation(s)")
        found += violations
    for violation in found:
        print(f"  {violation}")
    print(f"cp-policy-check: {len(found)} violation(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
