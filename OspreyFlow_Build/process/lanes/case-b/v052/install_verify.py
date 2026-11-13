"""Step 6's verifier (ROUTE_052 step 6, process/lanes/case-b/BRIEF_v052.md): a live poc deployment held to
the poc manifest (`harness/cloud_platform/poc_manifest.yaml`), entry by entry.

**Every listed item becomes a check, or the run stops before anything runs** ("listed but not exercised"):
a section, an entry, a key inside an entry, a database with no known reader, a job step nobody named, or an
entry still marked `pending` (a step that has not rendered it: a dry run may pass `--allow-pending`, the
install test may not). What each check asks of the deployment:

| Manifest | Check |
|---|---|
| workloads | the Deployment or StatefulSet exists, of its kind; desired and ready replicas both its count; the running image, requests and limits its entry's; a readiness probe exactly when it lists one |
| init_containers | in its workload's pod, from its image at its sizes, exited 0 |
| jobs | a CronJob at its schedule (or held suspended, when its schedule says so), image and sizes, with a run that succeeded (a held one started by the driver: `kubectl create job --from=cronjob/…`); a Job template (`<set>`) with a run that succeeded, every listed step exited 0, `restore-graph` from its image at its sizes |
| images | pushed: the registry answers the render's reference for it |
| managed.rds | it answers, its major version and `max_connections` the entry's |
| managed.rds.databases | a session on it from a pod of its reader (DATABASE_READERS) |
| managed.elasticache, .opensearch | a connection from a pod of its reader (STORE_READERS) |
| managed.s3.buckets | holds at least one object, written by the deployment |
| entra | the stand-in tenant granted a token to the registration (the API: a token for its audience) |
| egress | a pod of the namespace reaches each host on 443, **and is refused an unlisted one** |
| (all of it) | the deployment's own render agrees with the manifest (`manifest.differences`): what only AWS can show (an instance class, node type or engine string; built_from and upstream) is held there, and said so |

`verify(manifest, deployment)` runs the plan against anything with `Deployment`'s methods; `KindDeployment`
reads R1's kind cluster (r1_kind.py, the platform lane's, imported and not changed). Run from OspreyFlow_Core:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/install_verify.py plan [--allow-pending]
    bash ../OspreyFlow_Build/process/lanes/platform/gates/r1_kind.sh py \\
        ../../case-b/v052/install_verify.py verify [--allow-pending]   # on the kind cluster, under a lease
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
#: Whole-manifest words, held by the render check (the render is of this version and shape).
WORDS = {"version", "shape"}
WORKLOAD_KEYS = {"kind", "count", "image", "requests", "limits", "readiness", "pending"}
INIT_KEYS = {"image", "requests", "limits", "pending"}
JOB_KEYS = {"kind", "schedule", "when", "image", "requests", "limits", "steps", "restore-graph", "pending"}
#: The recovery runbook's restore steps (cloud_platform_backups), each a container of the restore Job.
JOB_STEPS = {"verify", "fetch-graph", "writers", "restore-graph", "restore-analytics", "restore-claims"}
IMAGE_KEYS = {"ours", "built_from", "upstream", "pending"}
MANAGED_KEYS = {
    "rds": {"engine", "class", "max_connections", "databases", "pending"},
    "elasticache": {"engine", "node_type", "nodes", "pending"},
    "s3": {"buckets", "pending"},
    # `signing` (3a: sigv4) is exercised by the reader check (the api reaches the domain only by signing)
    # and its value held by the render check, as the instance type is.
    "opensearch": {"engine", "instance_type", "data_nodes", "signing", "pending"},
}
ENTRA_KEYS = {"kind", "redirect", "grants", "exposes", "app_roles", "pending"}
ENTRA_REGISTRATIONS = {"glass", "api", "superset", "report-sync"}
#: Which workload reads each database: a session from one of its pods is what "reached" means.
DATABASE_READERS: dict[str, tuple[str, ...]] = {
    "ospreyflow": ("api", "worker"),
    "litellm": ("litellm",),
    "superset": ("superset",),
}
STORE_READERS: dict[str, tuple[str, ...]] = {"elasticache": ("api", "worker"), "opensearch": ("api",)}
#: A host no poc namespace is allowed (documentation's own domain, RFC 2606).
UNLISTED_HOST = "example.com"
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
    def rds_setting(self, name: str) -> str | None: ...
    def database_readers(self, database: str) -> set[str]: ...
    def store_readers(self, store: str) -> set[str]: ...
    def bucket_objects(self, bucket: str) -> int: ...
    def entra_used(self, registration: str) -> bool: ...
    def connects(self, host: str) -> bool: ...
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
    found: list[tuple[str, Any]] = []
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
        if got.get("ready") != w["count"]:
            problems.append(f"ready {got.get('ready')} of {w['count']}")
        if bool(got.get("probe")) != (w["readiness"] != "none"):
            problems.append(f"readiness probe {'present' if got.get('probe') else 'absent'}, listed {w['readiness']!r}")
        return _verdict(problems, f"{got['ready']}/{w['count']} ready")
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
        if "restore-graph" in j and "restore-graph" in steps:
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


def _readers(found: set[str], expected: tuple[str, ...], what: str) -> tuple[bool, str]:
    mine = found & set(expected)
    if mine:
        return True, f"reached by {', '.join(sorted(mine))}"
    return False, f"no session from {' or '.join(expected)}" + (f" (only {', '.join(sorted(found))})" if found else "")


def _database(db: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: _readers(d.database_readers(db), DATABASE_READERS[db], db)


def _store(store: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: _readers(d.store_readers(store), STORE_READERS[store], store)


def _bucket(bucket: str) -> Callable[[Deployment], tuple[bool, str]]:
    def run(d: Deployment) -> tuple[bool, str]:
        n = d.bucket_objects(bucket)
        return (n > 0, f"{n} object(s)" if n else "empty: nothing written")
    return run


def _entra(name: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: (True, "granted a token") if d.entra_used(name) else (False, "the tenant granted it no token")


def _egress(host: str) -> Callable[[Deployment], tuple[bool, str]]:
    return lambda d: (True, "reached on 443") if d.connects(host) else (False, "refused or unreachable on 443")


def _unlisted(d: Deployment) -> tuple[bool, str]:
    return (False, f"{UNLISTED_HOST} reached on 443: egress is open") if d.connects(UNLISTED_HOST) else (True, "refused")


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

    def keys(entry: str, got: dict[str, Any], known: set[str]) -> None:
        unknown.extend(f"{entry}: {k}" for k in got if k not in known)

    for name, w in (m.get("workloads") or {}).items():
        keys(f"workloads.{name}", w, WORKLOAD_KEYS)
        add(f"workloads.{name}", "ready, at its image and sizes", _workload(name, w))
    for key, c in (m.get("init_containers") or {}).items():
        keys(f"init_containers.{key}", c, INIT_KEYS)
        add(f"init_containers.{key}", "ran first and exited 0", _init(key, c))
    for name, j in (m.get("jobs") or {}).items():
        keys(f"jobs.{name}", j, JOB_KEYS)
        unknown.extend(f"jobs.{name}: steps {s}" for s in j.get("steps", []) if s not in JOB_STEPS)
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
            for db in settings.get("databases") or {}:
                if db not in DATABASE_READERS:
                    unknown.append(f"managed.rds.databases.{db} (no known reader)")
                    continue
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
    for host in m.get("egress") or {}:
        add(f"egress.{host}", "reached on 443", _egress(host))
    checks.append(Check(UNLISTED_HOST_CHECK, "refused", _unlisted))
    checks.append(Check(RENDER_CHECK, "the deployment's render agrees", _render))
    if unknown:
        raise NotExercised(unknown)
    return checks


#: The buckets the services write (harness.cloud_platform.terraform.BUCKETS and the backups' own).
KNOWN_BUCKETS = {"media", "staging", "site-images", "tile-cache", "backups"}


def verify(m: dict[str, Any], d: Deployment, *, allow_pending: bool = False) -> list[Result]:
    results = []
    for check in plan(m, allow_pending=allow_pending):
        try:
            ok, said = check.run(d)
        except Exception as error:  # noqa: BLE001 - a check that cannot read its answer has failed, not passed
            ok, said = False, f"{type(error).__name__}: {error}"
        results.append(Result(check.entry, check.what, ok, said))
    return results


# ---- the kind cluster's readings (pure, tested against the shapes kubectl and the stores answer) ----


def _repository(image: str, registry: str) -> str:
    from harness.cloud_platform.manifest import _repository as repo

    return repo(image, registry)


def _sizes(container: dict[str, Any]) -> dict[str, Any]:
    r = container.get("resources") or {}
    return {"requests": dict(r.get("requests") or {}), "limits": dict(r.get("limits") or {})}


def read_workload(obj: dict[str, Any], registry: str) -> dict[str, Any]:
    """A Deployment or StatefulSet as kubectl returns it (`readyReplicas` left out when none is ready)."""
    main = obj["spec"]["template"]["spec"]["containers"][0]
    return {
        "kind": obj["kind"],
        "desired": obj["spec"].get("replicas", 1),
        "ready": (obj.get("status") or {}).get("readyReplicas", 0),
        "image": _repository(main["image"], registry),
        **_sizes(main),
        "probe": "readinessProbe" in main,
    }


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


def _by_ip(pods: list[dict[str, Any]]) -> dict[str, str]:
    return {p["status"]["podIP"]: p["metadata"]["labels"]["app.kubernetes.io/name"]
            for p in pods if (p.get("status") or {}).get("podIP") and "app.kubernetes.io/name" in (p["metadata"].get("labels") or {})}


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
    found = set()
    for addr in re.findall(r"\baddr=([0-9.]+):\d+", listing):
        if addr in names:
            found.add(names[addr])
    return found


_GRANTED = re.compile(r"^entra-standin: granted \S+ client=(\S+) audience=(\S+)", re.MULTILINE)


def granted_clients(log: str) -> set[str]:
    """The stand-in tenant's grants (one line per token issued; refusals name no grant)."""
    return {m.group(1) for m in _GRANTED.finditer(log)}


def granted_audiences(log: str) -> set[str]:
    return {m.group(2) for m in _GRANTED.finditer(log)}


# ---- the kind cluster -----------------------------------------------------------------------------


class KindDeployment:
    """R1's kind cluster (r1_kind.py), read through kubectl: the deployment in its namespace, the
    platform's stand-ins in theirs. Every read is of the live thing; nothing is taken from the render
    but the image references to look up and the render check's own comparison."""

    def __init__(self, r1: Any, *, registry: str, render: dict[str, Any], config: Any, clients: dict[str, str],
                 api_audiences: set[str], bucket_prefix: str, hosts: dict[str, str], jobs: Iterable[str]) -> None:
        self.r1, self.registry, self.render, self.config = r1, registry, render, config
        self.clients, self.api_audiences, self.bucket_prefix, self.hosts = clients, api_audiences, bucket_prefix, hosts
        self.job_names = list(jobs)

    def _get(self, *args: str) -> Any:
        out = self.r1.kubectl("-n", self.r1.NS, "get", *args, "-o", "json", check=False)
        return json.loads(out) if out.strip() else None

    def _pods(self) -> list[dict[str, Any]]:
        return self._get("pods")["items"]

    def workload(self, name: str) -> dict[str, Any] | None:
        for kind in ("deployment", "statefulset"):
            obj = self._get(kind, name)
            if obj:
                return read_workload(obj, self.registry)
        return None

    def init_container(self, key: str) -> dict[str, Any] | None:
        workload, _, container = key.partition("/")
        pods = [p for p in self._pods() if (p["metadata"].get("labels") or {}).get("app.kubernetes.io/name") == workload]
        for pod in pods:
            spec = next((c for c in pod["spec"].get("initContainers") or [] if c["name"] == container), None)
            if spec:
                status = next((s for s in pod["status"].get("initContainerStatuses") or [] if s["name"] == container), None)
                return {"image": _repository(spec["image"], self.registry), **_sizes(spec), "exit_code": _exit(status)}
        return None

    def job(self, name: str) -> dict[str, Any] | None:
        if "<set>" not in name:
            cron = self._get("cronjob", name)
            if not cron:
                return None
            spec = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
            runs = [j for j in self._get("jobs")["items"] if any(o.get("name") == name for o in j["metadata"].get("ownerReferences") or [])]
            return {"kind": "CronJob", "schedule": cron["spec"]["schedule"], "suspended": bool(cron["spec"].get("suspend")), "image": _repository(spec["image"], self.registry),
                    **_sizes(spec), "succeeded": sum((j.get("status") or {}).get("succeeded", 0) for j in runs), "steps": {}}
        prefix = name.split("<set>", 1)[0]
        longer = [n.split("<set>", 1)[0] for n in self.job_names if "<set>" in n and n != name and n.startswith(prefix)]
        runs = [j for j in self._get("jobs")["items"]
                if j["metadata"]["name"].startswith(prefix) and not any(j["metadata"]["name"].startswith(p) for p in longer)]
        if not runs:
            return None
        done = [j for j in runs if (j.get("status") or {}).get("succeeded")] or runs
        job = done[-1]
        pods = [p for p in self._pods() if (p["metadata"].get("labels") or {}).get("job-name") == job["metadata"]["name"]]
        return read_job(job, pods, self.registry)

    def image_pushed(self, repository: str) -> bool:
        target = next(i["target"] for i in self.render["images.yaml"]["images"] if _repository(i["target"], self.registry) == repository)
        return bool(self.r1.sh("docker", "manifest", "inspect", "--insecure", target, check=False).strip())

    def _postgres(self, sql: str, database: str = "postgres") -> str:
        return self.r1.kubectl("-n", self.r1.MANAGED, "exec", "statefulset/postgres", "--", "psql", "-U", "postgres",
                               "-d", database, "-Atc", sql)

    def rds_setting(self, name: str) -> str | None:
        out = self._postgres(f"SHOW {name}").strip()
        return out or None

    def database_readers(self, database: str) -> set[str]:
        rows = self._postgres("SELECT datname || '|' || coalesce(host(client_addr), '') FROM pg_stat_activity WHERE datname IS NOT NULL")
        return readers_from_sessions(rows, database, self._pods())

    def store_readers(self, store: str) -> set[str]:
        if store == "elasticache":
            listing = self.r1.kubectl("-n", self.r1.MANAGED, "exec", "statefulset/valkey", "--", "valkey-cli", "--tls",
                                      "--insecure", "-a", self.r1.PASSWORD, "--no-auth-warning", "CLIENT", "LIST")
            return readers_from_client_list(listing, self._pods())
        raise NotImplementedError(f"no stand-in for {store} on kind yet (v052-opensearch): the check fails until one exists")

    def bucket_objects(self, bucket: str) -> int:
        name = f"{self.bucket_prefix}{bucket}"
        code = f"import pathlib; p = pathlib.Path('/data') / {name!r}; print(len(list(p.glob('*.json'))) if p.is_dir() else 0)"
        return int(self.r1.s3_exec(code).strip() or 0)

    def entra_used(self, registration: str) -> bool:
        log = self.r1.kubectl("-n", self.r1.MANAGED, "logs", "deployment/entra-standin", "--tail=-1")
        if registration == "api":
            return bool(granted_audiences(log) & self.api_audiences)
        return self.clients[registration] in granted_clients(log)

    def connects(self, host: str) -> bool:
        target = self.hosts.get(host, host)
        if target.startswith("<"):
            raise LookupError(f"no address given for {host}")
        code = ("import socket, sys\ntry:\n    socket.create_connection((sys.argv[1], 443), timeout=5).close(); print('open')\n"
                "except OSError:\n    print('refused')")
        out = self.r1.kubectl("-n", self.r1.NS, "exec", "deployment/api", "--", "/app/.venv/bin/python", "-c", code, target, check=False)
        return out.strip() == "open"

    def render_differences(self) -> list[str]:
        from harness.cloud_platform.manifest import differences, load, rendered

        return differences(load(), rendered(self.config))


# ---- the command --------------------------------------------------------------------------------


def report(results: list[Result], skipped: list[str]) -> str:
    lines = [f"{'PASS' if r.ok else 'FAIL'} {r.entry}: {r.what}: {r.said}" for r in results]
    lines += [f"SKIP {e}: still pending (a dry run's --allow-pending)" for e in skipped]
    failed = sum(not r.ok for r in results)
    lines.append(f"{len(results)} checks, {failed} failed" + (f", {len(skipped)} pending skipped" if skipped else ""))
    return "\n".join(lines)


def _kind(m: dict[str, Any]) -> KindDeployment:  # pragma: no cover - the live half, run under a lease
    import yaml

    gates = Path(__file__).resolve().parents[2] / "platform" / "gates"
    sys.path.insert(0, str(gates))
    import r1_kind as r1  # the platform lane's driver, imported and not changed
    from harness.render import load_config, render

    config = load_config(r1.CONFIG)
    artefacts = render(config, resolver=lambda ref: None, allow_unpinned=True).artefacts
    images = yaml.safe_load(artefacts["images.yaml"])
    claims = yaml.safe_load(r1.CONFIG.read_text())["cloud_platform"]["claims"]
    entra = gates / "r1_kind_entra.yaml"
    others = yaml.safe_load(entra.read_text()) if entra.exists() else {}
    clients = {"glass": claims["client_id"], **{k: v["client_id"] for k, v in (others or {}).items()}}
    state = r1.state()
    return KindDeployment(r1, registry=images["registry"], render={"images.yaml": images}, config=config, clients=clients,
                          api_audiences={claims["api_client_id"], f"api://{claims['api_client_id']}"},
                          bucket_prefix=state.get("bucket_prefix", ""), hosts=state.get("egress_hosts", {}), jobs=m["jobs"])


def main(argv: list[str] | None = None) -> int:
    from harness.cloud_platform.manifest import load

    parser = argparse.ArgumentParser(prog="install_verify", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("verb", choices=("plan", "verify"))
    parser.add_argument("--allow-pending", action="store_true", help="a dry run before every step has rendered")
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
    results = verify(m, _kind(m), allow_pending=args.allow_pending)
    print(report(results, skipped))
    return 1 if any(not r.ok for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
