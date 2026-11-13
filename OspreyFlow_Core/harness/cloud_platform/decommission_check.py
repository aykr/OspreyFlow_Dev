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

from harness.cloud_platform_backups import BUCKET_SUFFIX, KEPT_AT_DECOMMISSION

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


#: The operator's two choices for the backups bucket and its key at a decommission; neither is
#: assumed.
BACKUP_CHOICES = ("keep", "destroy")
_DESTROYING = (
    "destroy was chosen for the backups, and it is still there: run DECOMMISSION.md's step 7 with "
    "BACKUPS=destroy again (it empties the bucket, removes it and schedules the key's deletion)"
)


class ListingRefused(ValueError):
    """A listing the check cannot vouch for (the wrong account or region, or no answer at all): a
    listing that says nothing must not read as nothing left."""


@dataclass
class Leftovers:
    items: list[Leftover] = field(default_factory=list)
    not_ours: list[str] = field(default_factory=list)
    #: The decommission's one named exception (ADR-148 Amendment 7): the backups bucket and its key,
    #: kept so no decommission makes a retained set unreadable. Reported, never a leftover, when the
    #: operator chose to keep them (the audit's ruling 3: there is no default).
    kept: list[str] = field(default_factory=list)
    #: The operator's choice for the backups bucket and its key, `keep` or `destroy`.
    backups: str = ""


def _claim_patterns(values: dict[str, Any]) -> list[re.Pattern[str]]:
    """A StatefulSet's claims are `<claim>-<statefulset>-<ordinal>`, whatever it was scaled to."""
    return [
        re.compile(rf"^{re.escape(claim['name'])}-{re.escape(w['name'])}-\d+$")
        for w in values.get("workloads", [])
        if w.get("kind") == "StatefulSet"
        for claim in w.get("claims", [])
    ]


def _config(values: dict[str, Any]) -> dict[str, Any]:
    """The deployment's own configuration, as the render carries it in its values."""
    return yaml.safe_load((values.get("files") or {}).get("osprey.yaml") or "{}") or {}


def _platform(values: dict[str, Any]) -> Any:
    from harness.cloud_platform.settings import load_platform

    return load_platform((_config(values).get("cloud_platform") or {}).get("platform", "client"))


def _our_names(values: dict[str, Any]) -> set[str]:
    """What the deployment made by name: our Secret, the shared claims, and what the namespace's
    Terraform writes into the namespace (the managed stores' Secrets, the bucket role's service
    account), none of which carries the chart's label."""
    storage = values.get("storage") or {}
    secrets = _platform(values).secrets
    return {
        f"Secret/{(values.get('secrets') or {}).get('name', 'ospreyflow-secrets')}",
        "PersistentVolumeClaim/ospreyflow-shared",
        *(f"PersistentVolumeClaim/ospreyflow-{c['name']}" for c in storage.get("claims", [])),
        *(f"Secret/{s.name}" for s in (secrets.postgres, secrets.redis, secrets.s3,
                                       secrets.opensearch)),
        f"ServiceAccount/{secrets.irsa.service_account}",
    }  # fmt: skip


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
    # Helm's own record of the release, kept by `helm uninstall --keep-history`.
    if item.get("kind") == "Secret" and str(metadata.get("name")).startswith(
        f"sh.helm.release.v1.{RELEASE}."
    ):
        return True
    if item.get("kind") == "PersistentVolumeClaim":
        return any(p.match(str(metadata.get("name"))) for p in _claim_patterns(values))
    return False


def _namespace(values: dict[str, Any]) -> str:
    """The deployment's namespace, from its own configuration as the render carries it."""
    namespace = (_config(values).get("cloud_platform") or {}).get("namespace")
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


def _ours_in_state(address: str, declared: set[str], module: str | None) -> str | None:
    """The `type.name` of `address` if it is one of the rendered Terraform's resources where the
    deployment's files sit: the folder's root, or `module.<module>` when the environments
    repository wraps them in one. A resource of the same type and name in another module is the
    platform's."""
    parts = re.sub(r"\[[^\]]*\]", "", address).split(".")
    if module is not None:
        if parts[:2] != ["module", module]:
            return None
        parts = parts[2:]
    if parts[:1] == ["module"] or len(parts) != 2:
        return None
    resource = ".".join(parts)
    return resource if resource in declared else None


def _disks(
    disks: dict[str, Any], namespace: str, region: str, account: str | None
) -> list[dict[str, Any]]:
    """The listing's volumes, once it says it is the cluster's account's, in the platform's region:
    `aws ec2 describe-volumes`, wrapped by the runbook with the account and region it asked."""
    if not isinstance(disks.get("Volumes"), list):
        raise ListingRefused("the disks listing holds no Volumes: describe-volumes did not answer")
    if disks.get("Region") != region:
        raise ListingRefused(
            f"the disks were listed in {disks.get('Region')!r}, not the platform's {region!r}"
        )
    if account is None or str(disks.get("Account")) != account:
        raise ListingRefused(
            f"the disks were listed in account {disks.get('Account')!r}, not the cluster's "
            f"({account!r}, --disks-account)"
        )
    return list(disks["Volumes"])


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
    disks_account: str | None = None,
    volumes: dict[str, Any] | None = None,
    module: str | None = None,
    backups: str,
) -> Leftovers:
    """`backups` is the operator's choice for the backups bucket and its key (the ADR-148 audit's
    ruling 3, v0.5.2: no default): `keep`, and they are reported as kept; `destroy`, and they are
    the deployment's like anything else, left behind if they are still there."""
    if backups not in BACKUP_CHOICES:
        raise ValueError(f"the backups: choose keep or destroy, not {backups!r}")
    found = Leftovers(backups=backups)
    destroying = backups == "destroy"
    names = _our_names(values)
    namespace = _namespace(values)
    for listing in objects:
        for item in listing.get("items") or []:
            metadata = item.get("metadata") or {}
            what = f"{item.get('kind')}/{metadata.get('name')}"
            if _is_ours(item, values, names):
                group = str(item.get("apiVersion", "")).rpartition("/")[0]
                kind = str(item.get("kind")).lower() + (f".{group}" if group else "")
                name = metadata.get("name")
                found.items.append(Leftover(what, f"kubectl -n {namespace} delete {kind} {name}"))
            else:
                found.not_ours.append(what)
    patterns = _claim_patterns(values)

    def our_claim(claim: str) -> bool:
        return f"PersistentVolumeClaim/{claim}" in names or any(p.match(claim) for p in patterns)

    region = _platform(values).aws_region
    for disk in _disks(disks, namespace, region, disks_account) if disks is not None else []:
        tags = {t.get("Key"): t.get("Value") for t in disk.get("Tags") or []}
        if tags.get(DISK_NAMESPACE_TAG) == namespace and our_claim(str(tags.get(DISK_CLAIM_TAG))):
            volume = disk.get("VolumeId")
            found.items.append(
                Leftover(
                    f"disk/{volume}",
                    f"the disk of claim {tags.get(DISK_CLAIM_TAG, '?')} is kept: "
                    f"aws ec2 delete-volume --region {region} --volume-id {volume}",
                )
            )
    for volume in (volumes or {}).get("items") or []:
        ref = (volume.get("spec") or {}).get("claimRef") or {}
        claim = str(ref.get("name") or "")
        if ref.get("namespace") != namespace:
            continue
        if our_claim(claim):
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
        resource = _ours_in_state(address, ours, module)
        if resource in KEPT_AT_DECOMMISSION and destroying:
            found.items.append(Leftover(f"terraform/{address}", _DESTROYING))
        elif resource in KEPT_AT_DECOMMISSION:
            found.kept.append(f"terraform/{address}")
        elif resource is not None:
            found.items.append(Leftover(f"terraform/{address}", _state_why(resource)))
        else:
            found.not_ours.append(f"terraform/{address}")
    for bucket in (line.strip() for line in buckets.splitlines()):
        if bucket == bucket_prefix + BUCKET_SUFFIX and destroying:
            found.items.append(Leftover(f"bucket/{bucket}", _DESTROYING))
        elif bucket == bucket_prefix + BUCKET_SUFFIX:
            found.kept.append(f"bucket/{bucket}")
        elif bucket and bucket.startswith(bucket_prefix):
            found.items.append(
                Leftover(
                    f"bucket/{bucket}",
                    "empty it of every version and delete marker as DECOMMISSION.md's step 6 does, "
                    f"then: aws s3api delete-bucket --region {region} --bucket {bucket}",
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
    parser.add_argument("--disks-account", help="the cluster's AWS account, which holds its disks")
    parser.add_argument("--module", help="the module the environments repository puts ours in")
    parser.add_argument("--volumes", type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--terraform", required=True, type=Path)
    parser.add_argument("--buckets", required=True, type=Path)
    parser.add_argument("--bucket-prefix", required=True)
    parser.add_argument(
        "--backups", required=True, choices=BACKUP_CHOICES,
        help="the operator's choice for the backups bucket and its key (no default)",
    )  # fmt: skip
    args = parser.parse_args(argv)
    try:
        found = _run(args)
    except ListingRefused as refused:
        print(f"decommission check: refused: {refused}", file=sys.stderr)
        return 2
    report(found)
    return 1 if found.items else 0


def report(found: Leftovers) -> None:
    """The decommission's record: what was left alone, what was kept, the operator's choice for the
    backups (stated whichever it was), and anything left behind."""
    for name in sorted(found.not_ours):
        print(f"left alone (not the deployment's): {name}")
    for name in found.kept:
        print(f"kept: the backups (retention): {name}")
    if found.backups == "keep":
        print("backups: kept (the operator chose keep)")
    elif found.backups == "destroy":
        left = any(i.why == _DESTROYING for i in found.items)
        print("backups: " + ("destroy was chosen; still there (below)" if left else "destroyed")
              + " (the operator chose destroy)")  # fmt: skip
    for item in found.items:
        print(f"LEFT BEHIND  {item.what}: {item.why}")
    print(f"decommission check: {len(found.items)} thing(s) left behind")


def _run(args: argparse.Namespace) -> Leftovers:
    return check(
        yaml.safe_load(args.values.read_text(encoding="utf-8")),
        objects=[json.loads(p.read_text(encoding="utf-8")) for p in args.objects],
        state=args.state.read_text(encoding="utf-8"),
        terraform={
            p.name: p.read_text(encoding="utf-8") for p in sorted(args.terraform.glob("*.tf"))
        },
        buckets=args.buckets.read_text(encoding="utf-8"),
        bucket_prefix=args.bucket_prefix,
        disks=_json(args.disks),
        disks_account=args.disks_account,
        volumes=_json(args.volumes),
        module=args.module,
        backups=args.backups,
    )


if __name__ == "__main__":
    sys.exit(main())
