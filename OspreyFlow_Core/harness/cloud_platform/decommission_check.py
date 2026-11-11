"""After a `cloud-platform` deployment is decommissioned (its rendered `DECOMMISSION.md`, ADR-148
Amendment 5), is anything it made still there?

Reads what the platform's own tools print, saved to files by the runbook's last step:

- `--objects`: `kubectl -n <namespace> get <every kind> -o json` (a `List`);
- `--volumes`: `kubectl get pv -o json` (the cluster's volumes, which outlive their claims);
- `--state`: `tofu state list` in the namespace's Terraform folder (empty after `tofu destroy`);
- `--buckets`: the account's bucket names, one a line, with `--bucket-prefix` the render's
  (`<namespace>-<suffix>-`, its Terraform's `local.prefix`).

The deployment's own objects are known from the render (`--values`, the chart's values): what the
chart labels ours, our Secret, the shared claims, and each StatefulSet's claims, whose labels are
the StatefulSet's selector's, not the chart's. Anything else in the namespace is the platform's or
another team's, and is listed as left alone. Exits 1 if anything is left, naming each with how it
is removed.
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
    if labels.get(PART_OF) == RELEASE or what in names:
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


def _removal(kind: str, name: str, namespace: str) -> str:
    return f"kubectl -n {namespace} delete {kind.lower()} {name}"


def _state_why(address: str) -> str:
    resource = address.split(".")[-2] if address.count(".") >= 1 else address
    if resource.startswith("aws_iam"):
        return "an IAM role or policy, which outlives the namespace: run `tofu destroy` again"
    if resource.startswith("aws_kms_alias"):
        return "a KMS key alias, which outlives the namespace: run `tofu destroy` again"
    return "still in the namespace's Terraform state: run `tofu destroy` again"


def check(
    values: dict[str, Any],
    *,
    objects: dict[str, Any],
    volumes: dict[str, Any],
    state: str,
    buckets: str,
    bucket_prefix: str,
) -> Leftovers:
    found = Leftovers()
    names = _our_names(values)
    namespace = _namespace(values)
    ours_claims: set[str] = set()
    for item in objects.get("items") or []:
        metadata = item.get("metadata") or {}
        what = f"{item.get('kind')}/{metadata.get('name')}"
        if _is_ours(item, values, names):
            if item.get("kind") == "PersistentVolumeClaim":
                ours_claims.add(str(metadata.get("name")))
            found.items.append(
                Leftover(
                    what, _removal(str(item.get("kind")), str(metadata.get("name")), namespace)
                )
            )
        else:
            found.not_ours.append(what)
    patterns = _claim_patterns(values)
    for volume in volumes.get("items") or []:
        ref = (volume.get("spec") or {}).get("claimRef") or {}
        claim = str(ref.get("name") or "")
        if ref.get("namespace") != namespace:
            continue
        claim_is_ours = (
            claim in ours_claims
            or f"PersistentVolumeClaim/{claim}" in names
            or any(p.match(claim) for p in patterns)
        )
        if claim_is_ours:
            name = (volume.get("metadata") or {}).get("name")
            found.items.append(
                Leftover(
                    f"PersistentVolume/{name}",
                    f"its claim {claim} was ours; its disk is kept: kubectl delete pv {name}, "
                    "then delete the disk it names",
                )
            )
    for address in (line.strip() for line in state.splitlines()):
        if address:
            found.items.append(Leftover(f"terraform/{address}", _state_why(address)))
    for bucket in (line.strip() for line in buckets.splitlines()):
        if bucket and bucket.startswith(bucket_prefix):
            found.items.append(
                Leftover(
                    f"bucket/{bucket}", f"empty it, then delete it: aws s3 rb s3://{bucket} --force"
                )
            )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--values", required=True, type=Path)
    parser.add_argument("--objects", required=True, type=Path)
    parser.add_argument("--volumes", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--buckets", required=True, type=Path)
    parser.add_argument("--bucket-prefix", required=True)
    args = parser.parse_args(argv)
    text = args.values.read_text(encoding="utf-8")
    found = check(
        yaml.safe_load(text),
        objects=json.loads(args.objects.read_text(encoding="utf-8")),
        volumes=json.loads(args.volumes.read_text(encoding="utf-8")),
        state=args.state.read_text(encoding="utf-8"),
        buckets=args.buckets.read_text(encoding="utf-8"),
        bucket_prefix=args.bucket_prefix,
    )
    for name in sorted(found.not_ours):
        print(f"left alone (not the deployment's): {name}")
    for item in found.items:
        print(f"LEFT BEHIND  {item.what}: {item.why}")
    print(f"decommission check: {len(found.items)} thing(s) left behind")
    return 1 if found.items else 0


if __name__ == "__main__":
    sys.exit(main())
