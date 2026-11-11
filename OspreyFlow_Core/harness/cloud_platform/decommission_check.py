"""After a `cloud-platform` deployment is decommissioned (its rendered `DECOMMISSION.md`, ADR-148
Amendment 5), is anything it made still there?

Reads what the platform's own tools print, saved to files by the runbook's last step:

- `--objects` (one or more): `kubectl -n <namespace> get <kind> -o json`, a `List` for each kind
  the deployment makes (`KINDS`), so a kind the namespace's tenant may not list is never asked for;
- `--disks`: `aws ec2 describe-volumes` for the volumes the EBS CSI driver tagged with the
  namespace (`kubernetes.io/created-for/pvc/namespace`): the disks themselves, which outlive their
  claims and their volume objects whatever a class's reclaim policy says;
- `--volumes` (optional, where the reader may list them): `kubectl get pv -o json`;
- `--state` and `--terraform`: `tofu state list` in the namespace's Terraform folder, and the
  rendered `terraform/` folder, whose declared resources alone are ours (the folder holds the
  platform's own resources too, which are left alone);
- `--buckets`: the account's bucket names, one a line, with `--bucket-prefix` the render's
  (`<namespace>-<suffix>-`, its Terraform's `local.prefix`).

The deployment's own objects are known from the render (`--values`, the chart's values): what the
chart labels ours, what Helm annotates as the release's, our Secret, the shared claims, and each
StatefulSet's claims, whose labels are the StatefulSet's selector's, not the chart's. Anything else
is the platform's or another team's, and is listed as left alone. Exits 1 if anything is left,
naming each with how it is removed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RELEASE = "ospreyflow"
PART_OF = "app.kubernetes.io/part-of"
#: The EBS CSI driver's tag on each volume it makes for a claim: the claim's namespace.
DISK_NAMESPACE_TAG = "kubernetes.io/created-for/pvc/namespace"
DISK_CLAIM_TAG = "kubernetes.io/created-for/pvc/name"

#: Every kind the chart, the install and the Terraform make in the namespace, which the runbook
#: lists one by one (`kubectl get <kind>`): a tenant may list these, and not every kind there is.
KINDS = (
    "deployments.apps", "statefulsets.apps", "replicasets.apps", "pods", "jobs.batch",
    "cronjobs.batch", "services", "configmaps", "secrets", "persistentvolumeclaims",
    "serviceaccounts", "ingresses.networking.k8s.io", "networkpolicies.networking.k8s.io",
    "networkpolicies.projectcalico.org", "poddisruptionbudgets.policy",
)  # fmt: skip


@dataclass(frozen=True)
class Leftover:
    what: str
    why: str


@dataclass
class Leftovers:
    items: list[Leftover] = field(default_factory=list)
    not_ours: list[str] = field(default_factory=list)


def _claim_patterns(values: dict[str, Any]) -> list[re.Pattern[str]]:
    """A StatefulSet's claims are `<claim>-<statefulset>-<ordinal>`, whatever it was scaled to."""
    return [
        re.compile(rf"^{re.escape(claim['name'])}-{re.escape(w['name'])}-\d+$")
        for w in values.get("workloads", [])
        if w.get("kind") == "StatefulSet"
        for claim in w.get("claims", [])
    ]


def _our_names(values: dict[str, Any]) -> set[str]:
    storage = values.get("storage") or {}
    return {
        f"Secret/{(values.get('secrets') or {}).get('name', 'ospreyflow-secrets')}",
        "PersistentVolumeClaim/ospreyflow-shared",
        *(f"PersistentVolumeClaim/ospreyflow-{c['name']}" for c in storage.get("claims", [])),
    }


def _is_ours(item: dict[str, Any], values: dict[str, Any], names: set[str]) -> bool:
    metadata = item.get("metadata") or {}
    labels = metadata.get("labels") or {}
    what = f"{item.get('kind')}/{metadata.get('name')}"
    if labels.get(PART_OF) == RELEASE:
        return True
    if what in names:
        return True
    if (metadata.get("annotations") or {}).get("meta.helm.sh/release-name") == RELEASE:
        return True
    if item.get("kind") == "PersistentVolumeClaim":
        return any(p.match(str(metadata.get("name"))) for p in _claim_patterns(values))
    return False


def _namespace(values: dict[str, Any]) -> str:
    """The deployment's namespace, from its own configuration as the render carries it."""
    config = yaml.safe_load((values.get("files") or {}).get("osprey.yaml") or "{}") or {}
    namespace = (config.get("cloud_platform") or {}).get("namespace")
    if not namespace:
        raise SystemExit("the values carry no cloud_platform.namespace: render them first")
    return str(namespace)


def declared_resources(terraform: dict[str, str]) -> set[str]:
    """`<type>.<name>` of every resource the rendered Terraform declares (`resource "t" "n"`)."""
    return {
        f"{kind}.{name}"
        for text in terraform.values()
        for kind, name in re.findall(r'^resource "([a-z0-9_]+)" "([A-Za-z0-9_-]+)"', text, re.M)
    }


def _resource_of(address: str) -> str:
    """`module.x.aws_iam_role.service` or `aws_s3_bucket.store["media"]` → `type.name`."""
    parts = re.sub(r"\[[^\]]*\]", "", address).split(".")
    while parts[:1] == ["module"] and len(parts) > 2:
        parts = parts[2:]
    return ".".join(parts)


def _state_why(resource: str) -> str:
    if resource.startswith("aws_iam"):
        return "an IAM role or policy, which outlives the namespace: apply the removal again"
    if resource.startswith("aws_kms_alias"):
        return "a KMS key alias, which outlives the namespace: apply the removal again"
    return "still in the namespace's Terraform state: apply the removal again"


def check(
    values: dict[str, Any],
    *,
    objects: list[dict[str, Any]],
    state: str,
    terraform: dict[str, str],
    buckets: str,
    bucket_prefix: str,
    disks: dict[str, Any] | None = None,
    volumes: dict[str, Any] | None = None,
) -> Leftovers:
    found = Leftovers()
    names = _our_names(values)
    namespace = _namespace(values)
    for listing in objects:
        for item in listing.get("items") or []:
            metadata = item.get("metadata") or {}
            what = f"{item.get('kind')}/{metadata.get('name')}"
            if _is_ours(item, values, names):
                kind, name = str(item.get("kind")).lower(), metadata.get("name")
                found.items.append(Leftover(what, f"kubectl -n {namespace} delete {kind} {name}"))
            else:
                found.not_ours.append(what)
    for disk in (disks or {}).get("Volumes") or []:
        tags = {t.get("Key"): t.get("Value") for t in disk.get("Tags") or []}
        if tags.get(DISK_NAMESPACE_TAG) == namespace:
            volume = disk.get("VolumeId")
            found.items.append(
                Leftover(
                    f"disk/{volume}",
                    f"the disk of claim {tags.get(DISK_CLAIM_TAG, '?')} is kept: "
                    f"aws ec2 delete-volume --volume-id {volume}",
                )
            )
    patterns = _claim_patterns(values)
    for volume in (volumes or {}).get("items") or []:
        ref = (volume.get("spec") or {}).get("claimRef") or {}
        claim = str(ref.get("name") or "")
        if ref.get("namespace") != namespace:
            continue
        if f"PersistentVolumeClaim/{claim}" in names or any(p.match(claim) for p in patterns):
            name = (volume.get("metadata") or {}).get("name")
            found.items.append(
                Leftover(
                    f"PersistentVolume/{name}",
                    f"its claim {claim} was ours: kubectl delete pv {name}, then its disk",
                )
            )
    ours = declared_resources(terraform)
    for address in (line.strip() for line in state.splitlines()):
        if not address:
            continue
        resource = _resource_of(address)
        if resource in ours:
            found.items.append(Leftover(f"terraform/{address}", _state_why(resource)))
        else:
            found.not_ours.append(f"terraform/{address}")
    for bucket in (line.strip() for line in buckets.splitlines()):
        if bucket and bucket.startswith(bucket_prefix):
            found.items.append(
                Leftover(
                    f"bucket/{bucket}", f"empty it, then delete it: aws s3 rb s3://{bucket} --force"
                )
            )
    return found


def _json(path: Path | None) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path is not None else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--values", required=True, type=Path)
    parser.add_argument("--objects", required=True, type=Path, action="append")
    parser.add_argument("--disks", type=Path)
    parser.add_argument("--volumes", type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--terraform", required=True, type=Path)
    parser.add_argument("--buckets", required=True, type=Path)
    parser.add_argument("--bucket-prefix", required=True)
    args = parser.parse_args(argv)
    found = check(
        yaml.safe_load(args.values.read_text(encoding="utf-8")),
        objects=[json.loads(p.read_text(encoding="utf-8")) for p in args.objects],
        state=args.state.read_text(encoding="utf-8"),
        terraform={
            p.name: p.read_text(encoding="utf-8") for p in sorted(args.terraform.glob("*.tf"))
        },
        buckets=args.buckets.read_text(encoding="utf-8"),
        bucket_prefix=args.bucket_prefix,
        disks=_json(args.disks),
        volumes=_json(args.volumes),
    )
    for name in sorted(found.not_ours):
        print(f"left alone (not the deployment's): {name}")
    for item in found.items:
        print(f"LEFT BEHIND  {item.what}: {item.why}")
    print(f"decommission check: {len(found.items)} thing(s) left behind")
    return 1 if found.items else 0


if __name__ == "__main__":
    sys.exit(main())
