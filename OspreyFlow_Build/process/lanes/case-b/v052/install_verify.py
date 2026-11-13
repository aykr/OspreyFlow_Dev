"""Step 6's verifier (ROUTE_052 step 6, process/lanes/case-b/BRIEF_v052.md): a live poc deployment held to
the poc manifest (`harness/cloud_platform/poc_manifest.yaml`), entry by entry, after the upgrade.

**Every listed item becomes a check, or the run stops before anything runs** ("listed but not exercised"):
a section, an entry, a key anywhere inside one, a database with no known reader, a job step nobody named, a
bucket nobody writes, or an entry still marked `pending` (a step that has not rendered it: a dry run may pass
`--allow-pending`, the install test may not). What each check asks of the deployment:

| Manifest | Check |
|---|---|
| version | against the candidate's commit, named by the run (`--candidate`, the copy's HEAD the upgrade rendered from): each of our images runs tagged with it (the render tags ours `<repository>:<commit>`, `render.git_sha`), and the deployment's own release (`OSPREY_RELEASE_VERSION`, the `ospreyflow-env` ConfigMap, `render.release_version`) is the manifest's version (a tagged candidate) or `dev-<that commit>` (untagged, as before the tag); `dev-unknown`, `unknown` or another commit fails, so a kept render that is itself v0.5.1's fails. And every container of every workload and job template, init containers too, runs the candidate's own reference where the render pinned its repository (the kept render's values, `:<commit>@<digest>`) |
| shape | the deployed configuration (the `ospreyflow-files` ConfigMap's `osprey.yaml`) is of this shape |
| workloads | the Deployment or StatefulSet exists, of its kind; the rollout finished: the controller has observed the latest generation, total, updated, ready and available replicas all its count, none unavailable (a crash-looping candidate beside a still-Ready old pod fails), a StatefulSet's current and update revisions one; the template's image, requests and limits its entry's; a readiness probe exactly when it lists one (the probe's content is the render check's) |
| init_containers | in a running pod of its workload, from its image at its sizes, exited 0 |
| jobs | a CronJob at its schedule (or held suspended, when its schedule says so), image and sizes, with a run of its own command at the candidate's image that succeeded (a held one started by the driver: `kubectl create job --from=cronjob/…`); a Job template (`<set>`) with a run that succeeded, every listed step exited 0, `restore-graph` from its image at its sizes |
| images | pushed: the registry answers the render's reference for it |
| managed.rds | it answers, its major version and `max_connections` the entry's |
| managed.rds.databases | a session on it from a running pod of its reader (DATABASE_READERS) |
| managed.elasticache | a connection from a running pod of its reader (STORE_READERS) |
| managed.opensearch | from each reader's pod, the deployment's own search client (`services.search_index.client`, rules' ADR-150 client) counts the alias, signed, and is answered with documents; the same count sent unsigned by the same transport is refused 403 (the domain admits only a signed request, so an answer to an unsigned one means the reader reached something else) |
| managed.s3.buckets | holds at least one object, written by the deployment |
| entra | the stand-in tenant granted a token to the registration (the API: a token for its audience). **Its `kind`, `redirect`, `grants`, `exposes` and `app_roles` are not checked**: the stand-in enforces its own registrations (platform's `r1_kind_entra.yaml`), not the manifest's, and hands out whatever roles it holds. They are the client administrator's words; a change to them is caught by no check here |
| egress | a pod of the namespace reaches each host on 443 (a `<placeholder>` names no host and fails), **and is blocked from an address no entry lists**, which the kind node itself (outside the policy) does reach: a node with no route out is no evidence. A probe that cannot answer (the exec failed, a name did not resolve) fails the check, never passes it |
| (all of it) | the deployment's own render agrees with the manifest (`manifest.differences`): what only AWS can show (an instance class, node type or engine string, RDS's point-in-time days; built_from and upstream) is held there |

`verify(manifest, deployment)` runs the plan against anything with `Deployment`'s methods; `KindDeployment`
reads R1's kind cluster (r1_kind.py, the platform lane's, imported and not changed). Run from OspreyFlow_Core:

    PYTHONPATH=.:packages:cli .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/install_verify.py plan [--allow-pending]
    bash ../OspreyFlow_Build/process/lanes/platform/gates/r1_kind.sh py \\
        ../../case-b/v052/install_verify.py verify --candidate <commit> [--allow-pending]   # on kind, under a lease
"""


from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

# ---- what the verifier knows how to check ---------------------------------------------------------

SECTIONS = {"version", "shape", "workloads", "init_containers", "jobs", "images", "managed", "entra", "egress"}
WORKLOAD_KEYS = {"kind", "count", "image", "requests", "limits", "readiness", "pending"}
INIT_KEYS = {"image", "requests", "limits", "pending"}
JOB_KEYS = {"kind", "schedule", "when", "image", "requests", "limits", "steps", "restore-graph", "pending"}
RESTORE_GRAPH_KEYS = {"image", "requests", "limits"}
#: The recovery runbook's restore steps (cloud_platform_backups), each a container of the restore Job.
JOB_STEPS = {"verify", "fetch-graph", "writers", "restore-graph", "restore-analytics", "restore-claims"}
IMAGE_KEYS = {"ours", "built_from", "upstream", "pending"}
MANAGED_KEYS = {
    # `point_in_time_days` (the Terraform's backup_retention_period) only AWS can show: held by the render check.
    "rds": {"engine", "class", "max_connections", "point_in_time_days", "databases", "pending"},
    "elasticache": {"engine", "node_type", "nodes", "pending"},
    "s3": {"buckets", "pending"},
    # `signing` (3a: sigv4) is exercised by the reader check (the api reaches the domain only by signing)
    # and its value held by the render check, as the instance type is.
    "opensearch": {"engine", "instance_type", "data_nodes", "signing", "pending"},
}
DATABASE_KEYS = {"pending"}
ENTRA_KEYS = {"kind", "redirect", "grants", "exposes", "app_roles", "pending"}
ENTRA_REGISTRATIONS = {"glass", "api", "superset", "report-sync"}
EGRESS_KEYS = {"pending"}  # every host on 443: a port key would be unplaced
#: Which workload reads each database: a session from one of its pods is what "reached" means.
DATABASE_READERS: dict[str, tuple[str, ...]] = {
    "ospreyflow": ("api", "worker"),
    "litellm": ("litellm",),
    "superset": ("superset",),
}
STORE_READERS: dict[str, tuple[str, ...]] = {"elasticache": ("api", "worker"), "opensearch": ("api",)}
#: The buckets the services write (harness.cloud_platform.terraform.BUCKETS and the backups' own).
KNOWN_BUCKETS = {"media", "staging", "site-images", "tile-cache", "backups"}
#: An address no poc namespace may reach: an address, so the probe asks the policy and not DNS.
UNLISTED_HOST = "1.1.1.1"
UNLISTED_HOST_CHECK = f"egress (unlisted: {UNLISTED_HOST})"
RENDER_CHECK = "render (agrees with the manifest)"


class NotExercised(Exception):
    """Listed but not exercised: the run stops before any check runs."""

    def __init__(self, entries: list[str]) -> None:
        self.entries = entries
        super().__init__("listed but not exercised:\n  " + "\n  ".join(entries))


class Deployment(Protocol):
    def workload(self, name: str) -> dict[str, Any] | None: ...
    def init_container(self, key: str) -> dict[str, Any] | None: ...
    def job(self, name: str) -> dict[str, Any] | None: ...
    def image_pushed(self, repository: str) -> bool: ...
    def candidate(self) -> str | None: ...
    def release(self) -> str | None: ...
    def rds_setting(self, name: str) -> str | None: ...
    def database_readers(self, database: str) -> set[str]: ...
    def store_readers(self, store: str) -> set[str]: ...
    def bucket_objects(self, bucket: str) -> int: ...
    def entra_used(self, registration: str) -> bool: ...
    def connects(self, host: str) -> bool: ...
    def reachable_outside(self, host: str) -> bool: ...
    def shape(self) -> str: ...
    def render_differences(self) -> list[str]: ...


@dataclass(frozen=True)
class Check:
    entry: str
    what: str
    run: Callable[[Deployment], tuple[bool, str]]


@dataclass(frozen=True)
class Result:
    entry: str
    what: str
    ok: bool
    said: str


# ---- the manifest's entries -------------------------------------------------------------------


def _pending(entry: Any) -> str | None:
    return entry.get("pending") if isinstance(entry, dict) else None


def entries(m: dict[str, Any], *, pending: bool = True) -> list[str]:
    """Every checkable entry of the manifest, as `section.name` (managed ones one level deeper)."""
    found: list[tuple[str, Any]] = [(k, None) for k in ("version", "shape") if k in m]
    for section in ("workloads", "init_containers", "jobs", "images", "entra", "egress"):
        found += [(f"{section}.{n}", e) for n, e in (m.get(section) or {}).items()]
    for service, settings in (m.get("managed") or {}).items():
        if service == "s3":
            found += [(f"managed.s3.buckets.{b}", settings) for b in settings.get("buckets", [])]
            continue
        found.append((f"managed.{service}", settings))
        for db, entry in (settings.get("databases") or {}).items():
            found.append((f"managed.{service}.databases.{db}", entry or settings))
    return [e for e, entry in found if pending or not _pending(entry)]


def skipped_pending(m: dict[str, Any]) -> list[str]:
    every, ready = entries(m), set(entries(m, pending=False))
    return [e for e in every if e not in ready]


def without_pending(m: dict[str, Any]) -> dict[str, Any]:
    """The manifest as the candidate should have it: every `pending` marker gone."""
    out = copy.deepcopy(m)

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("pending", None)
            for value in node.values():
                strip(value)

    strip(out)
    return out


# ---- the checks ---------------------------------------------------------------------------------


def _same(listed: Any, got: Any) -> bool:
    if isinstance(listed, dict) and isinstance(got, dict):
        return {k: str(v) for k, v in listed.items()} == {k: str(v) for k, v in got.items()}
    return str(listed) == str(got)


def _compare(entry: dict[str, Any], got: dict[str, Any], keys: Iterable[str]) -> list[str]:
    return [f"{k}: listed {entry[k]!r}, found {got.get(k)!r}" for k in keys if k in entry and not _same(entry[k], got.get(k))]


def _verdict(problems: list[str], fine: str) -> tuple[bool, str]:
    return (not problems, "; ".join(problems) if problems else fine)


def _workload(name: str, w: dict[str, Any]) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        got = d.workload(name)
        if got is None:
            return False, "absent"
        problems = _compare(w, got, ("kind", "image", "requests", "limits"))
        if got.get("desired") != w["count"]:
            problems.append(f"desired {got.get('desired')}, listed {w['count']}")
        if not got.get("settled"):
            problems.append("not yet rolled out (the controller has not observed the latest generation)")
        if got.get("replicas") != w["count"]:
            problems.append(f"{got.get('replicas')} replicas, listed {w['count']} (a rollout still holding the old pod)")
        for field in ("updated", "ready", "available"):
            if got.get(field) != w["count"]:
                problems.append(f"{field} {got.get(field)} of {w['count']}")
        if got.get("unavailable"):
            problems.append(f"{got.get('unavailable')} unavailable")
        if got.get("revisions_match") is False:
            problems.append("current and update revisions differ (the update has not finished)")
        if bool(got.get("probe")) != (w["readiness"] != "none"):
            problems.append(f"readiness probe {'present' if got.get('probe') else 'absent'}, listed {w['readiness']!r}")
        return _verdict(problems, f"{got['ready']}/{w['count']} ready, rolled out")
    return run


def _same_release(tag: str | None, version: str) -> bool:
    return tag is not None and tag.removeprefix("v") == str(version).removeprefix("v")


#: A commit as git names it: render.git_sha's full form; `dev-<short>` holds `rev-parse --short`'s (7 or more).
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def release_matches(release: str | None, version: str, candidate: str) -> tuple[bool, str]:
    """The deployment's release as `render.release_version` writes it: the manifest's version when the candidate's
    checkout was tagged with it, else `dev-<short commit>`, which must be the candidate's."""
    if _same_release(release, version):
        return True, f"release {release}"
    if release and release.startswith("dev-"):
        short = release.removeprefix("dev-")
        if re.fullmatch(r"[0-9a-f]{7,40}", short) and candidate.startswith(short):
            return True, f"release {release}, the candidate's commit, untagged"
    return False, f"the deployment's release is {release or 'not recorded'} (OSPREY_RELEASE_VERSION), not {version} or dev-{candidate[:7]}"


def _version(m: dict[str, Any]) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        candidate = d.candidate() or ""
        if not _COMMIT.fullmatch(candidate):
            return False, f"no candidate commit named ({candidate or 'none'}): --candidate takes the full commit the upgrade rendered from"
        ours = {repo for repo, image in (m.get("images") or {}).items() if image.get("ours")}
        behind = []
        ok, said = release_matches(d.release(), m["version"], candidate)
        if not ok:
            behind.append(said)
        for section, read in (("workloads", d.workload), ("jobs", d.job)):
            for name, entry in (m.get(section) or {}).items():
                got = read(name)
                if got is None:
                    continue  # absent: its own check fails
                if not got.get("current"):
                    behind.append(f"{name} (not the candidate's reference)")
                elif entry.get("image") in ours and got.get("tag") != candidate:
                    behind.append(f"{name} (tagged {got.get('tag')}, not the candidate's commit)")
        if behind:
            return False, f"not on {m['version']}'s candidate {candidate[:12]}: {', '.join(behind)}"
        return True, f"{said}; every workload and job on the candidate's images ({candidate[:12]})"
    return run


def _shape(m: dict[str, Any]) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        got = d.shape()
        return (got == m["shape"], f"shape {got}" + ("" if got == m["shape"] else f", listed {m['shape']}"))
    return run


def _init(key: str, c: dict[str, Any]) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        got = d.init_container(key)
        if got is None:
            return False, "absent"
        problems = _compare(c, got, ("image", "requests", "limits"))
        if got.get("exit_code") != 0:
            problems.append(f"exit {got.get('exit_code')}")
        return _verdict(problems, "ran and exited 0")
    return run


def _job(name: str, j: dict[str, Any]) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        got = d.job(name)
        if got is None:
            return False, "absent (never run)" if j["kind"] == "Job" else "absent"
        held = str(j.get("schedule", "")).startswith("suspended")  # held suspended, started by the runbooks
        problems = _compare(j, got, ("kind", "image", "requests", "limits") if held else ("kind", "schedule", "image", "requests", "limits"))
        if held and got.get("suspended") is not True:
            problems.append(f"not suspended (schedule {got.get('schedule')!r} runs by itself)")
        if not got.get("succeeded"):
            problems.append("no run succeeded")
        steps = got.get("steps") or {}
        for step in j.get("steps", []):
            if step not in steps:
                problems.append(f"step {step} absent")
            elif steps[step].get("exit_code") != 0:
                problems.append(f"step {step} exit {steps[step].get('exit_code')}")
        if "restore-graph" in j:
            if "restore-graph" not in steps:
                problems.append("step restore-graph absent")
            else:
                problems += [f"restore-graph {p}" for p in _compare(j["restore-graph"], steps["restore-graph"], ("image", "requests", "limits"))]
        return _verdict(problems, "a run succeeded")
    return run


def _image(repository: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: (True, "pushed") if d.image_pushed(repository) else (False, "not in the registry")


def _rds(r: dict[str, Any]) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        version = d.rds_setting("server_version")
        if version is None:
            return False, "not reached"
        problems = []
        major = r["engine"].split()[-1]
        if version.split(".")[0] != major:
            problems.append(f"server_version {version}, listed {r['engine']}")
        connections = d.rds_setting("max_connections")
        if str(connections) != str(r["max_connections"]):
            problems.append(f"max_connections {connections}, listed {r['max_connections']}")
        return _verdict(problems, f"postgres {version}, max_connections {connections}")
    return run


def _readers(found: set[str], expected: tuple[str, ...]) -> tuple[bool, str]:
    mine = found & set(expected)
    if mine:
        return True, f"reached by {', '.join(sorted(mine))}"
    return False, f"no session from {' or '.join(expected)}" + (f" (only {', '.join(sorted(found))})" if found else "")


def _database(db: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: _readers(d.database_readers(db), DATABASE_READERS[db])


def _store(store: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: _readers(d.store_readers(store), STORE_READERS[store])


def _bucket(bucket: str) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        n = d.bucket_objects(bucket)
        return (n > 0, f"{n} object(s)" if n else "empty: nothing written")
    return run


def _entra(name: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: (True, "granted a token") if d.entra_used(name) else (False, "the tenant granted it no token")


def _egress(host: str) -> Callable[[Deployment], tuple[bool, str]]:
    if host.startswith("<"):
        # The manifest's words for an address only the deployment knows: nothing here can probe it.
        return lambda d: (False, f"{host} is a placeholder, not a host: the manifest names no address to probe")
    return lambda d: (True, "reached on 443") if d.connects(host) else (False, "blocked on 443")


def _unlisted(d: Deployment) -> tuple[bool, str]:
    if d.connects(UNLISTED_HOST):
        return False, f"{UNLISTED_HOST} reached on 443: egress is open"
    if not d.reachable_outside(UNLISTED_HOST):
        return False, "blocked, but not reachable from outside the policy either (the node): no evidence the policy blocked it"
    return True, "blocked, though reachable from outside the policy"


def _render(d: Deployment) -> tuple[bool, str]:
    found = d.render_differences()
    return (not found, "; ".join(found) if found else "the render agrees")


def plan(m: dict[str, Any], *, allow_pending: bool = False) -> list[Check]:
    """One check per listed item, or `NotExercised` naming every item with none."""
    unknown: list[str] = [s for s in m if s not in SECTIONS]
    checks: list[Check] = []
    pending = set(skipped_pending(m))
    if pending and not allow_pending:
        unknown += [f"{e}: still pending at the install test" for e in sorted(pending)]

    def add(entry: str, what: str, run: Callable[[Deployment], tuple[bool, str]]) -> None:
        if entry not in pending:
            checks.append(Check(entry, what, run))

    def keys(entry: str, got: Any, known: set[str]) -> None:
        if not isinstance(got, dict):
            unknown.append(f"{entry}: not an entry ({got!r})")
            return
        unknown.extend(f"{entry}: {k}" for k in got if k not in known)

    if "version" in m:
        add("version", "the candidate's images running", _version(m))
    if "shape" in m:
        add("shape", "the deployment's shape", _shape(m))
    for name, w in (m.get("workloads") or {}).items():
        keys(f"workloads.{name}", w, WORKLOAD_KEYS)
        add(f"workloads.{name}", "rolled out and ready, at its image and sizes", _workload(name, w))
    for key, c in (m.get("init_containers") or {}).items():
        keys(f"init_containers.{key}", c, INIT_KEYS)
        add(f"init_containers.{key}", "ran first and exited 0", _init(key, c))
    for name, j in (m.get("jobs") or {}).items():
        keys(f"jobs.{name}", j, JOB_KEYS)
        if isinstance(j, dict):
            unknown.extend(f"jobs.{name}: steps {s}" for s in j.get("steps", []) if s not in JOB_STEPS)
            if "restore-graph" in j:
                keys(f"jobs.{name}.restore-graph", j["restore-graph"], RESTORE_GRAPH_KEYS)
        add(f"jobs.{name}", "a run succeeded", _job(name, j))
    for repo, image in (m.get("images") or {}).items():
        keys(f"images.{repo}", image, IMAGE_KEYS)
        add(f"images.{repo}", "pushed", _image(repo))
    for service, settings in (m.get("managed") or {}).items():
        if service not in MANAGED_KEYS:
            unknown.append(f"managed.{service}")
            continue
        keys(f"managed.{service}", settings, MANAGED_KEYS[service])
        if service == "rds":
            add("managed.rds", "answers, at its version and max_connections", _rds(settings))
            for db, entry in (settings.get("databases") or {}).items():
                if db not in DATABASE_READERS:
                    unknown.append(f"managed.rds.databases.{db} (no known reader)")
                    continue
                keys(f"managed.rds.databases.{db}", entry or {}, DATABASE_KEYS)
                add(f"managed.rds.databases.{db}", "reached by its reader", _database(db))
        elif service == "s3":
            for b in settings.get("buckets", []):
                if b not in KNOWN_BUCKETS:
                    unknown.append(f"managed.s3.buckets.{b}")
                    continue
                add(f"managed.s3.buckets.{b}", "written", _bucket(b))
        else:
            add(f"managed.{service}", "reached by its reader", _store(service))
    for name, reg in (m.get("entra") or {}).items():
        if name not in ENTRA_REGISTRATIONS:
            unknown.append(f"entra.{name}")
            continue
        keys(f"entra.{name}", reg, ENTRA_KEYS)
        add(f"entra.{name}", "used", _entra(name))
    for host, entry in (m.get("egress") or {}).items():
        keys(f"egress.{host}", entry or {}, EGRESS_KEYS)
        add(f"egress.{host}", "reached on 443", _egress(host))
    checks.append(Check(UNLISTED_HOST_CHECK, "blocked", _unlisted))
    checks.append(Check(RENDER_CHECK, "the deployment's render agrees", _render))
    if unknown:
        raise NotExercised(unknown)
    return checks


def verify(m: dict[str, Any], d: Deployment, *, allow_pending: bool = False) -> list[Result]:
    results = []
    for check in plan(m, allow_pending=allow_pending):
        try:
            ok, said = check.run(d)
        except KeyboardInterrupt:
            raise
        except BaseException as error:  # noqa: BLE001 - a check that cannot read its answer has failed, not passed (r1's shell exits)
            ok, said = False, f"{type(error).__name__}: {error}"
        results.append(Result(check.entry, check.what, ok, said))
    return results


# ---- the kind cluster's readings (pure, tested against the shapes kubectl and the stores answer) ----


def _repository(image: str, registry: str) -> str:
    from harness.cloud_platform.manifest import _repository as repo

    return repo(image, registry)


def _sizes(container: dict[str, Any]) -> dict[str, Any]:
    from harness.cloud_platform.manifest import _sizes as sizes

    return sizes(container.get("resources") or {})


def current(spec: dict[str, Any], registry: str, expected: dict[str, str]) -> bool:
    """A pod template on the candidate: its main container's repository pinned by the render, and every
    container (init containers too) whose repository the render pinned running exactly that reference."""
    containers = (spec.get("initContainers") or []) + spec["containers"]
    if _repository(spec["containers"][0]["image"], registry) not in expected:
        return False
    return all(expected[r] == c["image"] for c in containers if (r := _repository(c["image"], registry)) in expected)


def read_workload(obj: dict[str, Any], registry: str, *, expected: dict[str, str]) -> dict[str, Any]:
    """A Deployment or StatefulSet as kubectl returns it (`readyReplicas`, `updatedReplicas` left out when 0).
    `expected` maps a repository to the candidate's full reference (the render's)."""
    main = obj["spec"]["template"]["spec"]["containers"][0]
    status = obj.get("status") or {}
    repository = _repository(main["image"], registry)
    revisions = (status.get("currentRevision"), status.get("updateRevision"))
    return {
        "kind": obj["kind"],
        "desired": obj["spec"].get("replicas", 1),
        "replicas": status.get("replicas", 0),
        "ready": status.get("readyReplicas", 0),
        "updated": status.get("updatedReplicas", 0),
        "available": status.get("availableReplicas", 0),
        "unavailable": status.get("unavailableReplicas", 0),
        "revisions_match": None if None in revisions else revisions[0] == revisions[1],
        "settled": status.get("observedGeneration", 0) >= (obj.get("metadata") or {}).get("generation", 0),
        "image": repository,
        "current": current(obj["spec"]["template"]["spec"], registry, expected),
        "tag": tag_of(main["image"]),
        **_sizes(main),
        "probe": "readinessProbe" in main,
    }


def tag_of(reference: str) -> str | None:
    """`reg:5001/ospreyflow/api:<commit>@sha256:…` → `<commit>`; None when the reference has no tag."""
    last = reference.split("@", 1)[0].rsplit("/", 1)[-1]
    return last.split(":", 1)[1] if ":" in last else None


def release_of(configmap: dict[str, Any] | None) -> str | None:
    """The deployment's release as the render wrote it into the `ospreyflow-env` ConfigMap."""
    if configmap is None:
        raise LookupError("no ospreyflow-env ConfigMap in the namespace")
    return (configmap.get("data") or {}).get("OSPREY_RELEASE_VERSION")


def references_from_values(values: dict[str, Any], registry: str) -> dict[str, str]:
    """The candidate's image reference for each repository, as its pods run them: the render's values
    (`<repository>[:tag]@<digest>` once pinned), not images.yaml's tag-only push targets."""
    found: list[str] = []
    for w in values.get("workloads") or []:
        found.append(w["image"])
        found += [c["image"] for c in w.get("initContainers") or []]
    backups = values.get("backups") or {}
    if backups.get("image"):
        found.append(backups["image"])
    if (backups.get("arcadedb") or {}).get("image"):
        found.append(backups["arcadedb"]["image"])
    out: dict[str, str] = {}
    for ref in found:
        repo = _repository(ref, registry)
        if out.setdefault(repo, ref) != ref:
            raise ValueError(f"two references for {repo} in one render: {out[repo]} and {ref}")
    return out


def shape_of(configmap: dict[str, Any] | None) -> str:
    """The shape in the deployed configuration (`ospreyflow-files`' `osprey.yaml`; left out means standard)."""
    import yaml

    if not configmap or "osprey.yaml" not in (configmap.get("data") or {}):
        raise LookupError("no deployed configuration (the ospreyflow-files ConfigMap's osprey.yaml)")
    config = yaml.safe_load(configmap["data"]["osprey.yaml"]) or {}
    return str((config.get("cloud_platform") or {}).get("shape") or "standard")


def _exit(status: dict[str, Any] | None) -> int | None:
    if not status:
        return None
    done = (status.get("state") or {}).get("terminated") or (status.get("lastState") or {}).get("terminated")
    return done.get("exitCode") if done else None


def read_job(job: dict[str, Any], pods: list[dict[str, Any]], registry: str) -> dict[str, Any]:
    """A Job and its pods: each container a step, with its exit code (None while it has not run)."""
    spec = job["spec"]["template"]["spec"]
    statuses: dict[str, dict[str, Any]] = {}
    for pod in pods:
        st = pod.get("status") or {}
        for s in (st.get("initContainerStatuses") or []) + (st.get("containerStatuses") or []):
            if _exit(s) is not None or s["name"] not in statuses:
                statuses[s["name"]] = s
    steps = {}
    for c in (spec.get("initContainers") or []) + spec["containers"]:
        steps[c["name"]] = {"image": _repository(c["image"], registry), **_sizes(c), "exit_code": _exit(statuses.get(c["name"]))}
    main = spec["containers"][0]
    return {"kind": "Job", "image": _repository(main["image"], registry), **_sizes(main),
            "succeeded": (job.get("status") or {}).get("succeeded", 0), "steps": steps}


def cron_runs(cron: dict[str, Any], jobs: list[dict[str, Any]], name: str) -> int:
    """The CronJob's own successful runs: owned by it, its command and args unchanged (the runbook's
    `backup-sets-*` listing is made from it with another command), at its own image (the candidate's,
    not a run from before the upgrade)."""
    template = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    mine = 0
    for job in jobs:
        if not any(o.get("kind") == "CronJob" and o.get("name") == name for o in job["metadata"].get("ownerReferences") or []):
            continue
        c = job["spec"]["template"]["spec"]["containers"][0]
        if (c.get("image"), c.get("command"), c.get("args")) != (template.get("image"), template.get("command"), template.get("args")):
            continue
        mine += 1 if (job.get("status") or {}).get("succeeded") else 0
    return mine


def runs_of_template(name: str, job_names: Iterable[str], templates: Iterable[str]) -> list[str]:
    """The runs of a `<set>` Job template, never those of a longer template sharing its prefix."""
    prefix = name.split("<set>", 1)[0]
    longer = [t.split("<set>", 1)[0] for t in templates if "<set>" in t and t != name and t.startswith(prefix)]
    return [j for j in job_names if j.startswith(prefix) and not any(j.startswith(p) for p in longer)]


def _running(pods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in pods if (p.get("status") or {}).get("phase") == "Running"]


def _by_ip(pods: list[dict[str, Any]]) -> dict[str, str]:
    return {p["status"]["podIP"]: p["metadata"]["labels"]["app.kubernetes.io/name"]
            for p in _running(pods) if p["status"].get("podIP") and "app.kubernetes.io/name" in (p["metadata"].get("labels") or {})}


def readers_from_sessions(rows: str, database: str, pods: list[dict[str, Any]]) -> set[str]:
    """`datname|client_addr` rows from pg_stat_activity: the workloads holding a session on `database`."""
    names = _by_ip(pods)
    found = set()
    for line in rows.splitlines():
        db, _, addr = line.partition("|")
        if db == database and addr in names:
            found.add(names[addr])
    return found


def readers_from_client_list(listing: str, pods: list[dict[str, Any]]) -> set[str]:
    """Valkey's CLIENT LIST: the workloads with a connection open."""
    names = _by_ip(pods)
    return {names[a] for a in re.findall(r"\baddr=([0-9.]+):\d+", listing) if a in names}


_GRANTED = re.compile(r"^entra-standin: granted \S+ client=(\S+) audience=(\S+)", re.MULTILINE)


def granted_clients(log: str) -> set[str]:
    """The stand-in tenant's grants: one line per token issued, asked of platform (README); refusals name no grant."""
    return {m.group(1) for m in _GRANTED.finditer(log)}


def granted_audiences(log: str) -> set[str]:
    return {m.group(2) for m in _GRANTED.finditer(log)}


#: Run in the api pod: `open` (connected), `blocked` (refused or timed out); anything else is no answer.
PROBE = ("import socket, sys\ntry:\n    socket.create_connection((sys.argv[1], 443), timeout=5).close(); print('open')\n"
         "except socket.gaierror:\n    print('dns')\nexcept OSError:\n    print('blocked')")


#: Run in a reader's pod (`python -c`): the deployment's own search client (rules' services/search_index/client.py,
#: ADR-150 decision 7, with the pod's OPENSEARCH_* settings and IRSA credentials) counts the alias signed; then the
#: same count through the same transport, hosts and timeout, with no signer. One JSON line.
SEARCH_PROBE = """
import asyncio, json


async def ask(client, alias):
    try:
        return {"status": 200, "count": (await client.count(index=alias)).get("count")}
    except Exception as error:
        status = getattr(error, "status_code", None)
        return {"status": status if isinstance(status, int) else None, "error": str(error)[:300]}
    finally:
        await client.close()


async def main():
    from opensearchpy import AsyncHttpConnection, AsyncOpenSearch
    from services.search_index.client import SearchIndexConfig, search_client

    config = SearchIndexConfig.from_env()
    signed = await ask(search_client(config), config.alias)
    bare = AsyncOpenSearch(hosts=[config.url], connection_class=AsyncHttpConnection, timeout=30)
    return {"signing": config.signing, "alias": config.alias, "signed": signed, "unsigned": await ask(bare, config.alias)}


try:
    answer = asyncio.run(main())
except BaseException as error:  # r1's kubectl keeps stdout alone: the reason goes there, as the one line
    answer = {"failed": f"{type(error).__name__}: {error}"[:400]}
print(json.dumps(answer))
"""


def search_answer(out: str) -> tuple[bool, str]:
    """SEARCH_PROBE's line: a reader reached the domain when it signs, its signed count is answered with
    documents, and the unsigned count is refused 403 (the domain's refusal of an unsigned request)."""
    lines = [line for line in out.strip().splitlines() if line.startswith("{")]
    try:
        answer = json.loads(lines[-1])
    except (IndexError, ValueError):
        return False, f"the search probe gave no answer: {out.strip()[-300:]!r}"
    if "failed" in answer:
        return False, f"the search probe failed in the reader's pod: {answer['failed']}"
    alias, signed, unsigned = answer.get("alias"), answer.get("signed") or {}, answer.get("unsigned") or {}
    if answer.get("signing") != "sigv4":
        return False, f"the reader's signing is {answer.get('signing')!r}, not sigv4"
    if signed.get("status") != 200:
        return False, f"a signed count on {alias} was refused: {signed.get('status')} {signed.get('error', '')}".rstrip()
    if not isinstance(signed.get("count"), int) or signed["count"] < 1:
        return False, f"{alias} holds no documents (count {signed.get('count')!r})"
    if unsigned.get("status") != 403 or "not authorized" not in str(unsigned.get("error", "")):
        return False, (f"an unsigned count on {alias} was answered {unsigned.get('status')}, not refused 403 as the domain "
                       f"refuses (\"not authorized\"): not the domain")
    return True, f"{signed['count']} documents in {alias}, signed; unsigned refused 403"


def probe_answer(out: str) -> bool:
    answer = out.strip()
    if answer == "open":
        return True
    if answer == "blocked":
        return False
    raise LookupError(f"the egress probe gave no answer about the policy: {answer[:200]!r}")


# ---- the kind cluster -----------------------------------------------------------------------------


class KindDeployment:
    """R1's kind cluster (r1_kind.py), read through kubectl: the deployment in its namespace, the
    platform's stand-ins in theirs. Every read is of the live thing; nothing is taken from the render
    but the candidate's image references and the render check's own comparison."""

    def __init__(self, r1: Any, *, registry: str, expected: dict[str, str], clients: dict[str, str],
                 api_audiences: set[str], bucket_prefix: str, jobs: Iterable[str], config: Any = None,
                 candidate: str | None = None) -> None:
        self.r1, self.registry, self.expected, self.config = r1, registry, expected, config
        self.clients, self.api_audiences, self.bucket_prefix = clients, api_audiences, bucket_prefix
        self.job_names = list(jobs)
        self._candidate = candidate

    def candidate(self) -> str | None:
        return self._candidate

    def _get(self, *args: str) -> Any:
        out = self.r1.kubectl("-n", self.r1.NS, "get", *args, "-o", "json", check=False)
        return json.loads(out) if out.strip() else None

    def _pods(self) -> list[dict[str, Any]]:
        return self._get("pods")["items"]

    def workload(self, name: str) -> dict[str, Any] | None:
        for kind in ("deployment", "statefulset"):
            obj = self._get(kind, name)
            if obj:
                return read_workload(obj, self.registry, expected=self.expected)
        return None

    def init_container(self, key: str) -> dict[str, Any] | None:
        workload, _, container = key.partition("/")
        pods = [p for p in _running(self._pods()) if (p["metadata"].get("labels") or {}).get("app.kubernetes.io/name") == workload]
        pods.sort(key=lambda p: p["metadata"].get("creationTimestamp", ""), reverse=True)  # the newest: the candidate's
        for pod in pods:
            spec = next((c for c in pod["spec"].get("initContainers") or [] if c["name"] == container), None)
            if spec:
                status = next((s for s in pod["status"].get("initContainerStatuses") or [] if s["name"] == container), None)
                return {"image": _repository(spec["image"], self.registry), **_sizes(spec), "exit_code": _exit(status)}
        return None

    def job(self, name: str) -> dict[str, Any] | None:
        jobs = self._get("jobs")["items"]
        if "<set>" not in name:
            cron = self._get("cronjob", name)
            if not cron:
                return None
            template = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            spec = template["containers"][0]
            return {"kind": "CronJob", "schedule": cron["spec"]["schedule"], "suspended": bool(cron["spec"].get("suspend")),
                    "image": _repository(spec["image"], self.registry), **_sizes(spec), "succeeded": cron_runs(cron, jobs, name),
                    "steps": {}, "current": current(template, self.registry, self.expected), "tag": tag_of(spec["image"])}
        names = runs_of_template(name, [j["metadata"]["name"] for j in jobs], self.job_names)
        runs = [j for j in jobs if j["metadata"]["name"] in names]
        if not runs:
            return None
        runs.sort(key=lambda j: j["metadata"].get("creationTimestamp", ""))  # the newest last: the candidate's
        done = [j for j in runs if (j.get("status") or {}).get("succeeded")] or runs
        job = done[-1]
        pods = [p for p in self._pods() if (p["metadata"].get("labels") or {}).get("job-name") == job["metadata"]["name"]]
        return {**read_job(job, pods, self.registry),
                "current": current(job["spec"]["template"]["spec"], self.registry, self.expected),
                "tag": tag_of(job["spec"]["template"]["spec"]["containers"][0]["image"])}

    def image_pushed(self, repository: str) -> bool:
        return bool(self.r1.sh("docker", "manifest", "inspect", "--insecure", self.expected[repository], check=False).strip())

    def _postgres(self, sql: str) -> str:
        return self.r1.kubectl("-n", self.r1.MANAGED, "exec", "statefulset/postgres", "--", "psql", "-U", "postgres",
                               "-d", "postgres", "-Atc", sql)

    def release(self) -> str | None:
        return release_of(self._get("configmap", "ospreyflow-env"))

    def rds_setting(self, name: str) -> str | None:
        return self._postgres(f"SHOW {name}").strip() or None

    def database_readers(self, database: str) -> set[str]:
        rows = self._postgres("SELECT datname || '|' || coalesce(host(client_addr), '') FROM pg_stat_activity WHERE datname IS NOT NULL")
        return readers_from_sessions(rows, database, self._pods())

    def store_readers(self, store: str) -> set[str]:
        if store == "elasticache":
            listing = self.r1.kubectl("-n", self.r1.MANAGED, "exec", "statefulset/valkey", "--", "valkey-cli", "--tls",
                                      "--insecure", "-a", self.r1.PASSWORD, "--no-auth-warning", "CLIENT", "LIST")
            return readers_from_client_list(listing, self._pods())
        if store == "opensearch":
            found, refused = set(), []
            for reader in STORE_READERS[store]:
                out = self.r1.kubectl("-n", self.r1.NS, "exec", f"deployment/{reader}", "--", "/app/.venv/bin/python", "-c",
                                      SEARCH_PROBE, check=False)
                ok, said = search_answer(out)
                if ok:
                    found.add(reader)
                else:
                    refused.append(f"{reader}: {said}")
            if refused:
                raise LookupError("; ".join(refused))
            return found
        raise NotImplementedError(f"no reader check for {store}")

    def bucket_objects(self, bucket: str) -> int:
        if not self.bucket_prefix:
            raise LookupError("no bucket prefix in R1's state (r1_kind.py terraform saves it as `prefix`)")
        name = f"{self.bucket_prefix}{bucket}"
        code = f"import pathlib; p = pathlib.Path('/data') / {name!r}; print(len(list(p.glob('*.json'))) if p.is_dir() else 0)"
        return int(self.r1.s3_exec(code).strip())

    def entra_used(self, registration: str) -> bool:
        log = self.r1.kubectl("-n", self.r1.MANAGED, "logs", "deployment/entra-standin", "--tail=-1")
        if registration == "api":
            return bool(granted_audiences(log) & self.api_audiences)
        return self.clients[registration] in granted_clients(log)

    def connects(self, host: str) -> bool:
        out = self.r1.kubectl("-n", self.r1.NS, "exec", "deployment/api", "--", "/app/.venv/bin/python", "-c", PROBE, host, check=False)
        return probe_answer(out)

    def reachable_outside(self, host: str) -> bool:
        """The positive control: the kind node itself, which no NetworkPolicy governs."""
        out = self.r1.sh("docker", "exec", "osprey-r1-control-plane", "bash", "-c",
                         f"timeout 5 bash -c '</dev/tcp/{host}/443' 2>/dev/null && echo open || echo blocked", check=False)
        return probe_answer(out)

    def shape(self) -> str:
        return shape_of(self._get("configmap", "ospreyflow-files"))

    def render_differences(self) -> list[str]:
        from harness.cloud_platform.manifest import differences, load, rendered

        if self.config is None:
            raise LookupError("no configuration to render")
        return differences(load(), rendered(self.config))


# ---- the command --------------------------------------------------------------------------------


def report(results: list[Result], skipped: list[str]) -> str:
    lines = [f"{'PASS' if r.ok else 'FAIL'} {r.entry}: {r.what}: {r.said}" for r in results]
    lines += [f"SKIP {e}: still pending (a dry run's --allow-pending)" for e in skipped]
    failed = sum(not r.ok for r in results)
    lines.append(f"{len(results)} checks, {failed} failed" + (f", {len(skipped)} pending skipped" if skipped else ""))
    return "\n".join(lines)


def _kind(m: dict[str, Any], candidate: str | None) -> KindDeployment:  # pragma: no cover - the live half, run under a lease
    import yaml

    gates = Path(__file__).resolve().parents[2] / "platform" / "gates"
    sys.path.insert(0, str(gates))
    import r1_kind as r1  # the platform lane's driver, imported and not changed
    from harness.render import load_config

    config = load_config(r1.CONFIG)
    if not (r1.KEPT / "values.yaml").exists():  # the render the install used, kept by r1_kind.keep_render
        raise SystemExit(f"no kept render at {r1.KEPT}: run the candidate's install through r1_kind.py first")
    images = yaml.safe_load((r1.KEPT / "images.yaml").read_text())
    values = yaml.safe_load((r1.KEPT / "values.yaml").read_text())
    raw = yaml.safe_load(r1.CONFIG.read_text())
    claims = raw["cloud_platform"]["claims"]
    entra = gates / "r1_kind_entra.yaml"
    others = yaml.safe_load(entra.read_text()) if entra.exists() else {}
    clients = {"glass": claims["client_id"], **{k: v["client_id"] for k, v in (others or {}).items()}}
    expected = references_from_values(values, images["registry"])
    return KindDeployment(r1, registry=images["registry"], expected=expected, config=config, clients=clients,
                          api_audiences={claims["api_client_id"], f"api://{claims['api_client_id']}"},
                          bucket_prefix=r1.state().get("prefix", ""), jobs=m["jobs"], candidate=candidate)


def main(argv: list[str] | None = None) -> int:
    from harness.cloud_platform.manifest import load

    parser = argparse.ArgumentParser(prog="install_verify", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("verb", choices=("plan", "verify"))
    parser.add_argument("--allow-pending", action="store_true", help="a dry run before every step has rendered")
    parser.add_argument("--candidate", help="verify: the full commit the upgrade rendered from (the copy's HEAD that ran it)")
    args = parser.parse_args(argv)
    m = load()
    try:
        checks = plan(m, allow_pending=args.allow_pending)
    except NotExercised as stopped:
        print(f"STOP {stopped}")
        return 2
    skipped = skipped_pending(m) if args.allow_pending else []
    if args.verb == "plan":
        print("\n".join(f"{c.entry}: {c.what}" for c in checks) + f"\n{len(checks)} checks planned")
        print("\n".join(f"SKIP {e}: still pending" for e in skipped))
        return 0
    if args.verb == "verify" and not args.candidate:
        parser.error("verify needs --candidate <the full commit the upgrade rendered from>")
    results = verify(m, _kind(m, args.candidate), allow_pending=args.allow_pending)
    print(report(results, skipped))
    return 1 if any(not r.ok for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
