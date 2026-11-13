"""The poc manifest (`poc_manifest.yaml`, ROUTE_052.md step 2): the one source for the poc shape's
containers, images, sizing, managed services, Entra registrations and egress, and the client page's
tables printed from it.

`rendered(config)` reads the same facts out of a render (the Helm values, the images list and
the Terraform), in the manifest's own shape; `differences(listed, rendered)` names every entry one
has and the other has not, both ways, and every count, image, size, readiness check or setting that
differs. An entry marked `pending: <step>` is what v0.5.2 adds and that step has not yet rendered:
its absence is no difference, and its presence while still marked is one.

    python -m harness.cloud_platform.manifest tables            # the client page's tables
    python -m harness.cloud_platform.manifest check --config x  # x's render against the manifest
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

MANIFEST = Path(__file__).with_name("poc_manifest.yaml")


def load(path: Path = MANIFEST) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# ---- the render, read in the manifest's shape ----------------------------------------------


def _repository(image: str, registry: str) -> str:
    """`<registry>/ospreyflow/api:<tag>@sha256:…` → `ospreyflow/api`."""
    path = image.removeprefix(registry + "/").split("@", 1)[0]
    name, _, tag = path.rpartition(":")
    return name if name and "/" not in tag else path


def _readiness(probe: dict[str, Any] | None) -> Any:
    if not probe:
        return "none"
    command = " ".join(probe.get("exec") or [])
    found = re.search(r"https?://[^\s'\")]+", command)
    return {
        "check": found.group(0) if found else command,
        "every_seconds": probe.get("periodSeconds"),
    }


def _sizes(resources: dict[str, Any]) -> dict[str, Any]:
    return {
        "requests": dict(resources.get("requests") or {}),
        "limits": dict(resources.get("limits") or {}),
    }


def _terraform_value(text: str, resource: str, attribute: str) -> str | None:
    block = re.search(rf'resource "{re.escape(resource)}" "[^"]+" \{{(.*?)\n\}}', text, re.S)
    if not block:
        return None
    found = re.search(rf"^\s*{re.escape(attribute)}\s*=\s*(.+)$", block.group(1), re.M)
    return found.group(1).strip().strip('"') if found else None


def rendered(config: Any, *, resolver: Any = None) -> dict[str, Any]:
    """The render of `config` (a cloud-platform `OspreyConfig`), in the manifest's shape."""
    from harness.cloud_platform.terraform import BUCKETS
    from harness.cloud_platform_backups import BUCKET_SUFFIX
    from harness.render import render

    artefacts = render(config, resolver=resolver, allow_unpinned=resolver is None).artefacts
    values = yaml.safe_load(artefacts["values.yaml"])
    images = yaml.safe_load(artefacts["images.yaml"])
    registry = images["registry"]
    terraform = "\n".join(t for n, t in artefacts.items() if n.startswith("terraform/"))

    workloads: dict[str, Any] = {}
    init: dict[str, Any] = {}
    for w in values["workloads"]:
        workloads[w["name"]] = {
            "kind": w["kind"],
            "count": w.get("replicas", 1),
            "image": _repository(w["image"], registry),
            **_sizes(w["resources"]),
            "readiness": _readiness(w.get("probe")),
        }
        for c in w.get("initContainers") or []:
            init[f"{w['name']}/{c['name']}"] = {
                "image": _repository(c["image"], registry),
                **_sizes(c.get("resources") or {}),
            }

    jobs: dict[str, Any] = {}
    backups = values.get("backups")
    if backups:
        own = {"image": _repository(backups["image"], registry), **_sizes(backups["resources"])}
        claims = [c for c in (values.get("storage") or {}).get("claims") or []]
        jobs["ospreyflow-backup"] = {"kind": "CronJob", "schedule": backups["schedule"], **own}
        if claims:
            jobs["ospreyflow-backup-claims"] = {
                "kind": "CronJob",
                "schedule": backups["schedule"],
                **own,
            }
        if backups.get("restorable"):
            graph = backups["arcadedb"]
            jobs["ospreyflow-restore-<set>"] = {
                "kind": "Job",
                **own,
                "restore-graph": {
                    "image": _repository(graph["image"], registry),
                    **_sizes(graph["resources"]),
                },
            }
            if claims:
                jobs["ospreyflow-restore-claims-<set>"] = {"kind": "Job", **own}

    search = values.get("searchIndex")
    if search:
        started = {
            "ospreyflow-search-rebuild": (
                "suspended, started by the runbooks (a restore ends with it)"
            ),
            "ospreyflow-search-drift": "suspended, started by the runbooks",
        }
        for job in search["jobs"]:
            jobs[job["name"]] = {
                "kind": "CronJob",
                "schedule": started.get(job["name"], "suspended"),
                "image": _repository(search["image"], registry),
                **_sizes(search["resources"]),
            }

    listed_images: dict[str, Any] = {}
    for image in images["images"]:
        name = _repository(image["target"], registry)
        if "dockerfile" in image:
            listed_images[name] = {"ours": True, "built_from": image["dockerfile"]}
        else:
            listed_images[name] = {"ours": False, "upstream": image["source"].split("@", 1)[0]}

    def rds(attribute: str) -> str | None:
        return _terraform_value(terraform, "aws_db_instance", attribute)

    def cache(attribute: str) -> str | None:
        return _terraform_value(terraform, "aws_elasticache_replication_group", attribute)

    databases: dict[str, Any] = {}
    database = rds("db_name")
    if database:
        databases[database] = {}
    for key in init:
        if key.endswith("-db"):  # a database made by its service's own step on the instance
            databases[key.split("/", 1)[1].removesuffix("-db")] = {}
    if any(w["name"] == "superset" for w in values["workloads"]):
        # Superset makes its own settings database at its first start (`osprey_entrypoint.py`), as
        # on Small (ADR-148 Amendment 11), named by its environment or its default.
        databases[values["environment"].get("SUPERSET_METADATA_DB", "superset")] = {}
    parameter = re.search(r'name\s*=\s*"max_connections"\s*\n\s*value\s*=\s*"(\d+)"', terraform)
    backups_bucket = 'resource "aws_s3_bucket" "backups"' in terraform
    managed: dict[str, Any] = {
        "rds": {
            "engine": f"postgres {rds('engine_version')}",
            "class": rds("instance_class"),
            "max_connections": int(parameter.group(1)) if parameter else None,
            "point_in_time_days": int(rds("backup_retention_period") or 0),
            "databases": databases,
        },
        "elasticache": {
            "engine": f"redis {cache('engine_version')}",
            "node_type": cache("node_type"),
            "nodes": int(cache("num_cache_clusters") or 0),
        },
        "s3": {"buckets": [*BUCKETS, BUCKET_SUFFIX] if backups_bucket else list(BUCKETS)},
    }
    if 'resource "aws_opensearch_domain"' in terraform:
        managed["opensearch"] = {
            "engine": _terraform_value(terraform, "aws_opensearch_domain", "engine_version"),
            "instance_type": re.search(r'instance_type\s*=\s*"([^"]+)"', terraform).group(1),  # type: ignore[union-attr]
            "data_nodes": int(re.search(r"instance_count\s*=\s*(\d+)", terraform).group(1)),  # type: ignore[union-attr]
            "signing": values["environment"].get("OPENSEARCH_SIGNING"),
        }
    egress: dict[str, Any] = {h["host"]: {} for h in values["egress"]["hosts"]}
    return {
        "workloads": workloads,
        "init_containers": init,
        "jobs": jobs,
        "images": listed_images,
        "managed": managed,
        "egress": egress,
    }


# ---- the comparison --------------------------------------------------------------------------


#: What each section's entries are compared on (the rest of an entry is the page's words alone).
_COMPARED = {
    "workloads": ("kind", "count", "image", "requests", "limits", "readiness"),
    "init_containers": ("image", "requests", "limits"),
    "jobs": ("kind", "schedule", "image", "requests", "limits", "restore-graph"),
    "images": ("ours", "built_from", "upstream"),
    "egress": (),
}


def _entries(listed: dict[str, Any], got: dict[str, Any], label: str) -> list[str]:
    found: list[str] = []
    for name, entry in listed.items():
        pending = isinstance(entry, dict) and entry.get("pending")
        if name not in got:
            if not pending:
                found.append(f"listed, not rendered: {label} {name}")
        elif pending:
            found.append(f"rendered though marked pending ({pending}): {label} {name}")
    found += [f"rendered, not listed: {label} {name}" for name in got if name not in listed]
    return found


def _settings(
    listed: dict[str, Any], got: dict[str, Any], label: str, keys: tuple[str, ...]
) -> list[str]:
    found = []
    for key in keys:
        if key in listed and listed[key] != got.get(key):
            found.append(
                f"differs: {label} {key}: listed {listed[key]!r}, rendered {got.get(key)!r}"
            )
        elif key not in listed and key in got and key != "schedule":
            found.append(f"differs: {label} {key}: listed nothing, rendered {got[key]!r}")
    return found


def differences(listed: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """Every difference between the manifest and a render, both ways; empty when they agree."""
    found: list[str] = []
    for section, keys in _COMPARED.items():
        found += _entries(listed[section], got[section], section)
        for name, entry in listed[section].items():
            if name in got[section] and not entry.get("pending"):
                found += _settings(entry, got[section][name], f"{section} {name}", keys)
    managed, made = listed["managed"], got["managed"]
    for service in ("rds", "elasticache", "s3", "opensearch"):
        mine, theirs = managed.get(service), made.get(service)
        pending = isinstance(mine, dict) and mine.get("pending")
        if mine is None and theirs is not None:
            found.append(f"rendered, not listed: managed {service}")
        elif theirs is None and mine is not None and not pending:
            found.append(f"listed, not rendered: managed {service}")
        elif theirs is not None and pending:
            found.append(f"rendered though marked pending ({pending}): managed {service}")
        elif mine is not None and theirs is not None:
            keys = tuple(k for k in mine if k not in ("databases", "pending"))
            found += _settings(mine, theirs, service, keys)
    found += _entries(managed["rds"]["databases"], made["rds"]["databases"], "rds database")
    return found


# ---- the client page's tables ----------------------------------------------------------------


def _quantity(value: str) -> float:
    """CPU in cores, memory in GiB."""
    text = str(value)
    if text.endswith("m"):
        return int(text[:-1]) / 1000
    for suffix, scale in (("Gi", 1.0), ("Mi", 1 / 1024)):
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * scale
    return float(text)


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _later(entry: Any) -> str:
    return f" ({entry['pending']})" if isinstance(entry, dict) and entry.get("pending") else ""


def tables(listed: dict[str, Any] | None = None) -> str:
    """The client page's tables, from the manifest and nothing else."""
    m = listed if listed is not None else load()
    out = [f"# OspreyFlow {m['version']}, cloud-platform, shape: {m['shape']}", ""]
    out += [
        "## Containers",
        "",
        "| Workload | Kind | Count | Image | CPU request / limit | Memory request / limit "
        "| Ready when |",
        "|---|---|---|---|---|---|---|",
    ]
    totals = [0, 0.0, 0.0, 0.0, 0.0]
    for name, w in m["workloads"].items():
        ready = w["readiness"] if w["readiness"] == "none" else w["readiness"]["check"]
        out.append(
            f"| {name}{_later(w)} | {w['kind']} | {w['count']} | `{w['image']}` | "
            f"{w['requests']['cpu']} / {w['limits']['cpu']} | {w['requests']['memory']} / "
            f"{w['limits']['memory']} | {ready} |"
        )
        for i, (part, key) in enumerate(
            (("requests", "cpu"), ("limits", "cpu"), ("requests", "memory"), ("limits", "memory"))
        ):
            totals[i + 1] += w["count"] * _quantity(w[part][key])
        totals[0] += w["count"]
    out.append(
        f"| **Total** | | **{totals[0]}** | | "
        f"**{_number(totals[1])} / {_number(totals[2])} CPU** | "
        f"**{_number(totals[3])} / {_number(totals[4])} GiB** | |"
    )
    for name, c in m["init_containers"].items():
        out.append(
            f"| {name} (init) | | | `{c['image']}` | "
            f"{c['requests']['cpu']} / {c['limits']['cpu']} | "
            f"{c['requests']['memory']} / {c['limits']['memory']} | runs first |"
        )
    out += [
        "",
        "## Jobs and CronJobs",
        "",
        "| Name | Kind | When | Image | CPU request / limit | Memory request / limit |",
        "|---|---|---|---|---|---|",
    ]
    for name, j in m["jobs"].items():
        when = j.get("schedule") or j.get("when", "")
        out.append(
            f"| `{name}` | {j['kind']} | {when} | `{j['image']}` | {j['requests']['cpu']} / "
            f"{j['limits']['cpu']} | {j['requests']['memory']} / {j['limits']['memory']} |"
        )
        if "restore-graph" in j:
            g = j["restore-graph"]
            out.append(
                f"| `{name}`, step restore-graph | | | `{g['image']}` | {g['requests']['cpu']} / "
                f"{g['limits']['cpu']} | {g['requests']['memory']} / {g['limits']['memory']} |"
            )
    out += [
        "",
        "## Images and ECR repositories",
        "",
        "| ECR repository | Ours or upstream | From |",
        "|---|---|---|",
    ]
    for name, image in m["images"].items():
        source = (
            f"built from `{image['built_from']}`"
            if image["ours"]
            else f"copied from `{image['upstream']}`"
        )
        out.append(
            f"| `{name}`{_later(image)} | {'ours' if image['ours'] else 'upstream'} | {source} |"
        )
    out += ["", "## Managed services", "", "| Service | Setting | Value |", "|---|---|---|"]
    for service, settings in m["managed"].items():
        label = {
            "rds": "RDS PostgreSQL",
            "elasticache": "ElastiCache",
            "s3": "S3",
            "opensearch": "OpenSearch Service",
        }.get(service, service) + _later(settings)
        for key, value in settings.items():
            if key == "pending":
                continue
            if key == "databases":
                value = ", ".join(f"{d}{_later(v)}" for d, v in value.items())
            elif isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            out.append(f"| {label} | {key.replace('_', ' ')} | {value} |")
    out += [
        "",
        "## Entra ID registrations",
        "",
        "| Registration | Kind | Details |",
        "|---|---|---|",
    ]
    for name, reg in m["entra"].items():
        details = "; ".join(
            f"{k.replace('_', ' ')}: {', '.join(v) if isinstance(v, list) else v}"
            for k, v in reg.items()
            if k not in ("kind", "pending")
        )
        out.append(f"| {name}{_later(reg)} | {reg['kind']} | {details} |")
    out += ["", "## Egress", "", "| Host | Port |", "|---|---|"]
    out += [f"| `{host}`{_later(entry)} | 443 |" for host, entry in m["egress"].items()]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness.cloud_platform.manifest",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    sub.add_parser("tables", help="print the client page's tables from the manifest")
    check = sub.add_parser("check", help="compare a deployment's render with the manifest")
    check.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.verb == "tables":
        sys.stdout.write(tables())
        return 0
    from harness.render import load_config

    found = differences(load(), rendered(load_config(args.config)))
    for line in found:
        print(line)
    print("manifest: the render agrees" if not found else f"manifest: {len(found)} difference(s)")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
