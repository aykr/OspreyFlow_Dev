"""P9's pods as built against their rows in P7b's `profile.yaml` (ADR-148 Amendment 5 point 21,
Amendment 7): each backup and restore pod is a row by its own `app.kubernetes.io/name`, runs under
the backups' own account (never the IRSA account, never the gateway's), and its row reaches exactly
what its containers' commands call, on the ports they call it on: ArcadeDB, ClickHouse, the
cluster's API (the writers check), S3 and STS. What a command calls is read from
`services.api.platform_backup` itself, by its call graph, so a command that starts calling a store
or the API without its row (or a row kept after its command stops) is red here.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest
import yaml
from harness import cloud_platform_backups as backups
from harness.cloud_platform.settings import KUBE_API, load_platform, load_profile
from services.api import platform_backup
from tools import helm_chart
from tools.cp_policy_check import check_manifests, pod_spec

from tests.cloud_platform_backup import rendered
from tests.cloud_platform_backup.test_backups_chart import AWAITED

# What each reach is, in the module's own names: the method or function a call must reach.
REACHES = {
    "arcadedb": {"arcadedb_backup"},
    "clickhouse": {"clickhouse", "clickhouse_backup", "clickhouse_restore"},
    KUBE_API: {"_pods"},
}
SET = "20261111T021500Z"
# P7b's rows as P9 checked them after P7b landed: `restore-claims` runs the writers check and had no
# `kube-api`; `restore` had ArcadeDB, which none of its commands calls. The platform lane's
# `process/lanes/case/P9_rows.diff` gives the rows; until it is applied the two cases are held red.
_PATHS = load_profile().egress.paths
ROWS_LANDED = KUBE_API in _PATHS.get("restore-claims", []) and "arcadedb" not in _PATHS["restore"]
_UNTIL_THE_DIFF = pytest.mark.xfail(
    not ROWS_LANDED, strict=True, reason="P9_rows.diff (the platform lane's) not yet applied"
)


def _names(node: ast.AST) -> set[str]:
    """The names a piece of code refers to, called or passed (`(pods or _pods)(selector)`)."""
    return {n.id if isinstance(n, ast.Name) else n.attr
            for n in ast.walk(node) if isinstance(n, ast.Name | ast.Attribute)}  # fmt: skip


def _calls() -> dict[str, set[str]]:
    """Each function's and method's name in the module, with the names it refers to."""
    tree = ast.parse(inspect.getsource(platform_backup))
    return {n.name: _names(n) for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _reached(names: set[str], calls: dict[str, set[str]]) -> set[str]:
    seen, todo = set(), list(names)
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo += calls.get(name, ())
    return seen


def _commands() -> dict[str, set[str]]:
    """Each subcommand of `main`, with what its branch reaches (`REACHES`'s keys)."""
    calls = _calls()
    main = next(n for n in ast.walk(ast.parse(inspect.getsource(platform_backup)))
                if isinstance(n, ast.FunctionDef) and n.name == "main")  # fmt: skip
    out: dict[str, set[str]] = {}
    for node in ast.walk(main):
        test = node.test if isinstance(node, ast.If) else None
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Attribute)
                and test.left.attr == "command" and isinstance(test.comparators[0], ast.Constant)):  # fmt: skip
            names = set().union(*(_names(stmt) for stmt in node.body))
            reached = _reached(names, calls)
            out[test.comparators[0].value] = {k for k, via in REACHES.items() if via & reached}
    return out


def _docs() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every P9 pod rendered: the poc's claim of its own, and a restore named."""
    values = rendered.values()
    values["storage"] = {**values["storage"], "claims": [{"name": "ingest", "size": "50Gi"}]}
    values["backups"]["restore"] = {"set": SET}
    target = rendered.target()
    return helm_chart.template(yaml.safe_dump(values, sort_keys=False, width=4096), target.namespace), values


def _pods(docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """P9's pods (its CronJobs' and Jobs'), by their `app.kubernetes.io/name`."""
    out = {}
    for doc in docs:
        pod = pod_spec(doc)
        if pod is not None and doc["kind"] in ("Job", "CronJob"):
            out[doc["metadata"]["labels"]["app.kubernetes.io/name"]] = pod
    return out


def _env(container: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, str]:
    """A container's environment as Kubernetes gives it, the ConfigMap's keys read from the render."""
    maps = {d["metadata"]["name"]: d.get("data", {}) for d in docs if d["kind"] == "ConfigMap"}
    out = {}
    for e in container.get("env", []):
        ref = e.get("valueFrom", {}).get("configMapKeyRef")
        if ref:
            out[e["name"]] = maps[ref["name"]][ref["key"]]
        elif "value" in e:
            out[e["name"]] = e["value"]
    for source in container.get("envFrom", []):
        if "configMapRef" in source:
            out = {**maps[source["configMapRef"]["name"]], **out}
    return out


def _what_the_pod_calls(
    pod: dict[str, Any], commands: dict[str, set[str]], docs: list[dict[str, Any]]
) -> dict[str, set[int]]:
    """What a pod's containers call, each store on the port its environment names."""
    out: dict[str, set[int]] = {}
    for container in [*pod.get("initContainers", []), *pod["containers"]]:
        command = container["command"]
        if "services.api.platform_backup" not in command:
            # ArcadeDB's own restore (deploy/backups/restore-graph.sh), from the zip on the pod's
            # scratch into its databases claim, checked and swapped there: it calls nothing.
            assert command[:2] == ["sh", "/restore-graph/restore-graph.sh"], command
            continue
        name = command[command.index("services.api.platform_backup") + 1]
        assert name in commands, f"{name}: a command the module's main does not have"
        env = _env(container, docs)
        port = {"arcadedb": int(env.get("ARCADEDB_HTTP_PORT", "2480")),
                "clickhouse": int(env.get("CLICKHOUSE_HTTP_PORT", "8123")), KUBE_API: 443}  # fmt: skip
        for reached in commands[name]:
            out.setdefault(reached, set()).add(port[reached])
    return out


def test_the_module_s_commands_are_read_as_they_call() -> None:
    """The reading the test relies on, held to what the offline tests show each command doing."""
    commands = _commands()
    assert commands["backup"] == {"arcadedb", "clickhouse"}
    assert commands["backup-claims"] == set()
    assert commands["fetch-graph"] == set()
    assert commands["writers"] == {KUBE_API}
    assert commands["verify"] == {KUBE_API}
    assert commands["restore-analytics"] == {"clickhouse", KUBE_API}
    assert commands["restore-claims"] == {KUBE_API}


def test_p9_s_pods_are_rows_by_their_own_names_under_their_own_account() -> None:
    docs, values = _docs()
    cfg = rendered.config()
    assert cfg.cloud_platform is not None
    irsa = load_platform(cfg.cloud_platform.platform).secrets.irsa
    found = _pods(docs)
    for name, pod in found.items():
        assert pod["serviceAccountName"] == backups.SERVICE_ACCOUNT, name
        assert pod["serviceAccountName"] not in {irsa.service_account, irsa.gateway_service_account}, name
    assert set(found) == set(load_profile().egress.others) == {"backup", "backup-claims", "restore", "restore-claims"}
    clickhouse = next(w for w in values["workloads"] if w["name"] == "clickhouse")
    assert clickhouse["serviceAccountName"] == backups.CLICKHOUSE_SERVICE_ACCOUNT


@pytest.mark.parametrize(
    "name",
    ["backup", "backup-claims", pytest.param("restore", marks=_UNTIL_THE_DIFF),
     pytest.param("restore-claims", marks=_UNTIL_THE_DIFF)],
)  # fmt: skip
def test_each_pod_s_row_reaches_what_its_commands_call_and_no_more(name: str) -> None:
    docs, values = _docs()
    commands = _commands()
    calls = _what_the_pod_calls(_pods(docs)[name], commands, docs)
    row = next(r for r in values["egress"]["workloads"] if r["name"] == name)
    to_pods = {t["name"]: set(t["ports"]) for t in row.get("toPods", [])}
    stores = {k: v for k, v in calls.items() if k != KUBE_API}
    assert set(to_pods) == set(stores), f"{name}: its row reaches {sorted(to_pods)}, its commands {sorted(stores)}"
    for store, ports in stores.items():
        assert ports <= to_pods[store], f"{name}: {store} on {sorted(ports)}, its row {sorted(to_pods[store])}"
    assert row.get("toKubeApi", False) == (KUBE_API in calls), (
        f"{name}: the writers check {'is' if KUBE_API in calls else 'is not'} run, "
        f"its row {'reaches' if row.get('toKubeApi') else 'does not reach'} the cluster's API"
    )
    hosts = {h.split(".")[0] for h in row.get("hosts", [])}
    assert hosts == {"s3", "sts"}, f"{name}: {sorted(row.get('hosts', []))}"
    assert "fromPods" not in row and not row.get("managed"), name


def test_only_the_backup_s_own_container_holds_a_key_of_our_secret() -> None:
    """P7b's default-deny on our Secret's keys (Amendment 5 point 22): ArcadeDB's password to the
    container that calls ArcadeDB, the backup's, and to no other of P9's containers; none whole."""
    docs, values = _docs()
    ours = values["secrets"]["name"]
    held = {}
    for name, pod in _pods(docs).items():
        for container in [*pod.get("initContainers", []), *pod["containers"]]:
            assert not [s for s in container.get("envFrom", []) if "secretRef" in s], container["name"]
            keys = [e["valueFrom"]["secretKeyRef"]["key"] for e in container.get("env", [])
                    if (e.get("valueFrom") or {}).get("secretKeyRef", {}).get("name") == ours]  # fmt: skip
            if keys:
                held[f"{name}/{container['name']}"] = keys
    assert held == {"backup/backup": ["ARCADEDB_ROOT_PASSWORD"]}


@pytest.mark.parametrize("name", ["backup-claims", "restore", "restore-claims"])
def test_the_policy_check_refuses_our_key_to_another_of_p9_s_pods(name: str) -> None:
    """cp-policy-check's allowance names the backup alone: ArcadeDB's password planted on another
    of P9's pods, as the render writes it (a `secretKeyRef` of our Secret), is `whole-secret`."""
    docs, values = _docs()
    target = rendered.target()

    def found() -> list[str]:
        return [f"{v.rule}: {v.where}" for v in check_manifests(
            docs, target.registry, controller_namespace=target.controller_namespace)]  # fmt: skip

    assert found() == AWAITED
    owner = next(d for d in docs if d["kind"] in ("Job", "CronJob")
                 and d["metadata"]["labels"]["app.kubernetes.io/name"] == name)  # fmt: skip
    container = pod_spec(owner)["containers"][0]
    container.setdefault("env", []).append(
        {"name": "ARCADEDB_ROOT_PASSWORD", "valueFrom": {"secretKeyRef": {
            "name": values["secrets"]["name"], "key": "ARCADEDB_ROOT_PASSWORD"}}})  # fmt: skip
    where = f"{owner['kind']}/{owner['metadata']['name']}/{container['name']}"
    assert sorted(f for f in found() if f.startswith("whole-secret")) == sorted([*AWAITED, f"whole-secret: {where}"])


# ---- each container's Secret keys, from its command (the orchestrator's review, item 2) ----------


def _secret_keys(container: dict[str, Any]) -> set[tuple[str, str]]:
    return {(e["valueFrom"]["secretKeyRef"]["name"], e["valueFrom"]["secretKeyRef"]["key"])
            for e in container.get("env", []) if (e.get("valueFrom") or {}).get("secretKeyRef")}  # fmt: skip


def test_each_container_holds_the_secret_keys_its_command_calls_for_and_no_more() -> None:
    """As each pod's egress is held to what its commands call, each container's Secret keys are:
    the bucket's and its key's (every runner's, to start); ArcadeDB's password where the command
    calls ArcadeDB (the backup's alone); ClickHouse's backup user's where it calls ClickHouse (the
    backup's and restore-analytics'); none in ArcadeDB's own restore step."""
    docs, values = _docs()
    commands = _commands()
    ours = values["secrets"]["name"]
    every = {(backups.OUTPUT_SECRET, backups.OUTPUT_KEYS["bucket"]),
             (backups.OUTPUT_SECRET, backups.OUTPUT_KEYS["kms_key"])}  # fmt: skip
    by_store = {"arcadedb": {(ours, "ARCADEDB_ROOT_PASSWORD")},
                "clickhouse": {(backups.BACKUP_SECRET, backups.BACKUP_SECRET_KEY)}, KUBE_API: set()}  # fmt: skip
    held = {}
    for name, pod in _pods(docs).items():
        for container in [*pod.get("initContainers", []), *pod["containers"]]:
            command = container["command"]
            if "services.api.platform_backup" in command:
                verb = command[command.index("services.api.platform_backup") + 1]
                expected = every.union(*(by_store[r] for r in commands[verb]))
            else:
                expected = set()
            held[f"{name}/{container['name']}"] = _secret_keys(container)
            assert held[f"{name}/{container['name']}"] == expected, (name, container["name"])
    assert {k for k, v in held.items() if (ours, "ARCADEDB_ROOT_PASSWORD") in v} == {"backup/backup"}
    assert {k for k, v in held.items() if (backups.BACKUP_SECRET, backups.BACKUP_SECRET_KEY) in v} == {
        "backup/backup", "restore/restore-analytics"}
