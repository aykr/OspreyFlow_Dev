"""The chart's backups template (`templates/backups.yaml`, ADR-148 Amendment 7) as Helm emits it:
the CronJob on ArcadeDB's node with its claim, the restore Job only when a set is named, and
`make cp-policy-check`'s rules green on the render with it and **red on a fault planted in the
template itself** (the brief's exit, rule 15: the template edited as a person would edit it, then
templated by Helm). Helm runs as its pinned image, so this needs Docker (the test server's).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from tools import helm_chart
from tools.cp_policy_check import check_manifests, pod_spec

from tests.cloud_platform_backup import rendered

TEMPLATE = Path("templates") / "backups.yaml"
# cp-policy-check's default-deny on our Secret's keys (P7b) lists ArcadeDB's password for P9's
# backup (P9_rows.diff): every render with the backups passes, with nothing awaited.
AWAITED: list[str] = []


def _docs(values: dict[str, Any], *, chart: Path | None = None) -> list[dict[str, Any]]:
    target = rendered.target()
    original = helm_chart.CHART
    if chart is not None:
        helm_chart.CHART = chart
    try:
        return helm_chart.template(yaml.safe_dump(values, sort_keys=False, width=4096), target.namespace)
    finally:
        helm_chart.CHART = original


def _named(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"].startswith(name))


def _rules(docs: list[dict[str, Any]]) -> list[str]:
    target = rendered.target()
    return [f"{v.rule}: {v.where}" for v in check_manifests(
        docs, target.registry, controller_namespace=target.controller_namespace)]  # fmt: skip


@pytest.mark.parametrize("fixture", rendered.fixtures())
def test_the_render_with_its_backups_passes_the_policy_check(fixture: str) -> None:
    target = rendered.target(fixture)
    docs = helm_chart.template(target.values, target.namespace)
    found = check_manifests(docs, target.registry, controller_namespace=target.controller_namespace)
    assert [f"{v.rule}: {v.where}" for v in found] == AWAITED
    assert _named(docs, "CronJob", "ospreyflow-backup")
    assert not [d for d in docs if d["kind"] == "Job" and d["metadata"]["name"].startswith("ospreyflow-restore")]


def test_the_cronjob_runs_on_arcadedbs_node_with_its_claim_one_run_at_a_time() -> None:
    docs = _docs(rendered.values())
    cron = _named(docs, "CronJob", "ospreyflow-backup")
    assert cron["spec"]["concurrencyPolicy"] == "Forbid"
    pod = pod_spec(cron)
    assert pod is not None
    assert pod["serviceAccountName"] == "ospreyflow-backup"
    assert pod["securityContext"]["runAsUser"] == 10001
    term = pod["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][0]
    assert term["labelSelector"]["matchLabels"] == {"statefulset.kubernetes.io/pod-name": "arcadedb-0"}
    assert term["topologyKey"] == "kubernetes.io/hostname"
    assert pod["volumes"] == [{"name": "arcadedb-backups", "persistentVolumeClaim": {"claimName": "backups-arcadedb-0"}}]
    container = pod["containers"][0]
    assert container["command"][-2:] == ["services.api.platform_backup", "backup"]
    assert {"name": "arcadedb-backups", "mountPath": "/arcadedb-backups"} in container["volumeMounts"]
    assert "envFrom" not in container, "the pod reads the two passwords it uses, never the whole Secret"
    arcadedb = _named(docs, "StatefulSet", "arcadedb")
    templates = {c["metadata"]["name"] for c in arcadedb["spec"]["volumeClaimTemplates"]}
    assert "backups" in templates


def test_the_restore_job_is_rendered_only_for_a_named_set_and_in_order() -> None:
    values = rendered.values()
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    docs = _docs(values)
    job = _named(docs, "Job", "ospreyflow-restore-20261111t021500z")
    pod = pod_spec(job)
    assert pod is not None
    assert [c["name"] for c in pod["initContainers"]] == ["verify", "fetch-graph", "writers", "restore-graph"]
    env = {e["name"]: e.get("value") for e in pod["initContainers"][0]["env"]}
    assert env["OSPREY_BACKUP_WRITERS"] == ",".join(values["backups"]["writers"])  # the render's own
    assert pod["containers"][0]["name"] == "restore-analytics"
    assert {"name": "arcadedb-databases", "persistentVolumeClaim": {"claimName": "databases-arcadedb-0"}} in pod["volumes"]
    assert _rules(docs) == AWAITED


def _planted(tmp_path: Path, old: str, new: str) -> Path:
    chart = tmp_path / "chart"
    shutil.copytree(helm_chart.CHART, chart)
    path = chart / TEMPLATE
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))
    return chart


def test_the_check_is_red_on_the_template_without_its_pod_security(tmp_path: Path) -> None:
    chart = _planted(tmp_path, '{{- include "ospreyflow.backupPod" (dict "b" $b "root" $root) | nindent 10 }}',
                     "serviceAccountName: {{ $b.serviceAccountName }}")  # fmt: skip
    rules = _rules(_docs(rendered.values(), chart=chart))
    assert any(r.startswith("root: CronJob/ospreyflow-backup") or r.startswith("named-uid: CronJob/ospreyflow-backup") for r in rules), rules


def test_the_check_is_red_on_a_host_path_in_the_template(tmp_path: Path) -> None:
    chart = _planted(tmp_path, """            - name: arcadedb-backups
              persistentVolumeClaim:
                claimName: {{ $b.arcadedb.backupsClaim }}""", """            - name: arcadedb-backups
              hostPath:
                path: /var/lib/arcadedb-backups""")
    rules = _rules(_docs(rendered.values(), chart=chart))
    assert any(r.startswith("hostPath") and "ospreyflow-backup" in r for r in rules), rules


def test_the_check_is_red_on_an_image_from_elsewhere_in_the_template(tmp_path: Path) -> None:
    chart = _planted(tmp_path, '"backup" "image" $b.image', '"backup" "image" "docker.io/library/python:3.12"')
    rules = _rules(_docs(rendered.values(), chart=chart))
    assert any(r.startswith("foreign-registry") and "ospreyflow-backup" in r for r in rules), rules


def test_the_check_is_red_on_the_restore_without_its_resources(tmp_path: Path) -> None:
    chart = _planted(tmp_path, '"resources" $b.arcadedb.resources', '"resources" (dict)')
    values = rendered.values()
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    rules = _rules(_docs(values, chart=chart))
    assert any(r.startswith("no-resources") and "ospreyflow-restore" in r for r in rules), rules


def test_the_chart_with_its_backups_is_valid_kubernetes() -> None:
    values = _with_claims(rendered.values())
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    docs = _docs(values)
    done = subprocess.run(
        ["docker", "run", "--rm", "-i", "ghcr.io/yannh/kubeconform:v0.6.7", "-strict", "-summary",
         "-ignore-missing-schemas", "-kubernetes-version", "1.31.0", "-"],
        input=yaml.safe_dump_all(docs), capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr


def _with_claims(values: dict[str, Any]) -> dict[str, Any]:
    """The poc shape's Ingest root on a claim of its own (ADR-148 Amendment 5): `storage.claims`."""
    values["storage"] = {**values["storage"], "claims": [{"name": "ingest", "size": "50Gi"}]}
    return values


def _exactly(docs: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def _env(container: dict[str, Any]) -> dict[str, Any]:
    return {e["name"]: e.get("value", e.get("valueFrom")) for e in container.get("env", [])}


def test_the_standard_shape_has_no_claims_run() -> None:
    docs = _docs(rendered.values())
    assert not [d for d in docs if d["metadata"]["name"].startswith("ospreyflow-backup-claims")]
    main = pod_spec(_exactly(docs, "CronJob", "ospreyflow-backup"))
    assert main is not None
    env = _env(main["containers"][0])
    assert "OSPREY_BACKUP_CLAIMS" not in env
    # Each run names its set by its Job's name, the schedule slot (platform_backup.set_of).
    assert env["OSPREY_BACKUP_JOB"] == {"fieldRef": {"fieldPath": "metadata.labels['batch.kubernetes.io/job-name']"}}


def test_the_claims_run_is_beside_the_shared_pods_on_the_same_schedule_read_only() -> None:
    docs = _docs(_with_claims(rendered.values()))
    main = _exactly(docs, "CronJob", "ospreyflow-backup")
    claims = _exactly(docs, "CronJob", "ospreyflow-backup-claims")
    assert claims["spec"]["schedule"] == main["spec"]["schedule"]
    assert claims["spec"]["concurrencyPolicy"] == "Forbid"
    pod = pod_spec(claims)
    assert pod is not None
    assert pod["serviceAccountName"] == "ospreyflow-backup"
    term = pod["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][0]
    assert term == {"labelSelector": {"matchLabels": {"ospreyflow.io/shared": "true"}},
                    "topologyKey": "kubernetes.io/hostname"}  # fmt: skip
    assert pod["volumes"] == [{"name": "claim-ingest",
                               "persistentVolumeClaim": {"claimName": "ospreyflow-ingest", "readOnly": True}}]  # fmt: skip
    container = pod["containers"][0]
    assert container["command"][-1] == "backup-claims"
    assert {"name": "claim-ingest", "mountPath": "/claims/ingest"} in container["volumeMounts"]
    assert "envFrom" not in container
    for cron in (main, claims):
        spec = pod_spec(cron)
        assert spec is not None
        env = _env(spec["containers"][0])
        assert env["OSPREY_BACKUP_CLAIMS"] == "ingest", cron["metadata"]["name"]
        assert "fieldRef" in env["OSPREY_BACKUP_JOB"]
    assert _rules(docs) == AWAITED


def test_a_restore_with_claims_puts_them_back_in_a_job_of_its_own() -> None:
    values = _with_claims(rendered.values())
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    docs = _docs(values)
    job = _exactly(docs, "Job", "ospreyflow-restore-claims-20261111t021500z")
    pod = pod_spec(job)
    assert pod is not None
    assert pod["containers"][0]["command"][-3:] == ["restore-claims", "--set", "20261111T021500Z"]
    assert [c["name"] for c in pod["initContainers"]] == ["verify"], "every part checked before a claim is replaced"
    assert pod["volumes"] == [{"name": "claim-ingest", "persistentVolumeClaim": {"claimName": "ospreyflow-ingest"}}]
    assert "affinity" not in pod, "the claims' pods are stopped for a restore; the claim is free"
    assert _exactly(docs, "Job", "ospreyflow-restore-20261111t021500z")
    assert _rules(docs) == AWAITED


def test_the_check_is_red_on_the_claims_run_without_its_pod_security(tmp_path: Path) -> None:
    old = '{{- include "ospreyflow.backupPod" (dict "b" $b "root" $root) | nindent 10 }}'
    chart = tmp_path / "chart"
    shutil.copytree(helm_chart.CHART, chart)
    path = chart / TEMPLATE
    text = path.read_text()
    first = text.index(old)
    second = text.index(old, first + 1)  # the claims CronJob's, after the main one's
    path.write_text(text[:second] + "serviceAccountName: {{ $b.serviceAccountName }}" + text[second + len(old):])
    rules = _rules(_docs(_with_claims(rendered.values()), chart=chart))
    assert any("CronJob/ospreyflow-backup-claims" in r for r in rules), rules
    assert not any(r.endswith("CronJob/ospreyflow-backup") for r in rules), rules


def test_the_backups_account_may_see_pods_and_nothing_else() -> None:
    """The restore's writers check (Amendment 7): a Role to get and list the namespace's pods, bound
    to the backup's service account alone."""
    docs = _docs(rendered.values())
    role = _exactly(docs, "Role", "ospreyflow-backup-pods")
    assert role["rules"] == [{"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list"]}]
    binding = _exactly(docs, "RoleBinding", "ospreyflow-backup-pods")
    assert [s["name"] for s in binding["subjects"]] == ["ospreyflow-backup"]
    assert binding["roleRef"]["name"] == "ospreyflow-backup-pods"


def test_a_refused_run_is_never_retried() -> None:
    docs = _docs(_with_claims(rendered.values()))
    for name in ("ospreyflow-backup", "ospreyflow-backup-claims"):
        assert _exactly(docs, "CronJob", name)["spec"]["jobTemplate"]["spec"]["backoffLimit"] == 0


def test_a_restore_beyond_one_copy_of_each_store_is_refused_in_words() -> None:
    """The orchestrator's round 2, item 13: the restore is proven for one ArcadeDB and one ClickHouse
    copy; the production shape's restore is refused by the render, in the operator's words."""
    values = rendered.values("production")
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    with pytest.raises(helm_chart.HelmFailed, match="its restore is not supported yet"):
        _docs(values)
    assert _named(_docs(rendered.values("production")), "CronJob", "ospreyflow-backup"), "the backups still run"


def test_the_restore_needs_its_writers_named() -> None:
    values = rendered.values()
    del values["backups"]["writers"]
    with pytest.raises(helm_chart.HelmFailed, match="backups.writers"):
        _docs(values)


def test_the_writers_are_checked_again_just_before_arcadedbs_databases_are_replaced() -> None:
    values = rendered.values()
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    pod = pod_spec(_named(_docs(values), "Job", "ospreyflow-restore-20261111t021500z"))
    assert pod is not None
    names = [c["name"] for c in pod["initContainers"]]
    assert names[names.index("restore-graph") - 1] == "writers"
    assert pod["initContainers"][names.index("writers")]["command"][-1] == "writers"


def test_each_of_p9s_pods_runs_as_its_own_account_with_its_token() -> None:
    """P7b's `token` rule: the backup, the claims run and both restores each name their own service
    account and mount its token (their role, IRSA, and the restore's writers check); P9 renders no other
    pod."""
    values = _with_claims(rendered.values())
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    docs = [d for d in _docs(values) if d["kind"] in ("CronJob", "Job")]
    names = {d["metadata"]["name"] for d in docs}
    assert names == {"ospreyflow-backup", "ospreyflow-backup-claims", "ospreyflow-restore-20261111t021500z",
                     "ospreyflow-restore-claims-20261111t021500z"}  # fmt: skip
    for doc in docs:
        pod = pod_spec(doc)
        assert pod is not None
        assert pod["serviceAccountName"] == "ospreyflow-backup", doc["metadata"]["name"]
        assert pod["automountServiceAccountToken"] is True, doc["metadata"]["name"]


@pytest.mark.parametrize("named", ["latest", "20261111", "20261111T021500", "x20261111T021500Z", "20261111T021500Z;"])
def test_a_restore_names_one_set_or_is_refused(named: str) -> None:
    """`latest`, resolved again by each step, could restore two sets if one finished between them:
    the restore names its set once, as `sets` lists it (the orchestrator's review, item 6)."""
    values = rendered.values()
    values["backups"]["restore"] = {"set": named}
    with pytest.raises(helm_chart.HelmFailed, match="is not a set's name"):
        _docs(values)


def test_the_schedules_are_utc() -> None:
    docs = _docs(_with_claims(rendered.values()))
    for name in ("ospreyflow-backup", "ospreyflow-backup-claims"):
        assert _exactly(docs, "CronJob", name)["spec"]["timeZone"] == "Etc/UTC", name


def test_arcadedbs_restore_step_runs_the_script_and_check_from_the_deployments_files() -> None:
    """restore-graph runs `deploy/backups/restore-graph.sh` with its check, both given to the Job
    from the deployment's own files (`ospreyflow-files`), the database the render's."""
    from harness import cloud_platform_backups as backups

    values = rendered.values()
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    docs = _docs(values)
    pod = pod_spec(_named(docs, "Job", "ospreyflow-restore-20261111t021500z"))
    assert pod is not None
    step = next(c for c in pod["initContainers"] if c["name"] == "restore-graph")
    database = values["backups"]["arcadedb"]["database"]
    assert step["command"] == ["sh", "/restore-graph/restore-graph.sh", database, f"/restore/{database}.zip",
                               "/home/arcadedb/databases", "/restore-graph/CheckDatabase.java"]  # fmt: skip
    mounts = {m["mountPath"]: m for m in step["volumeMounts"]}
    files = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "ospreyflow-files")
    for key, source in backups.RESTORE_GRAPH_FILES.items():
        path = f"/restore-graph/{source}"
        assert mounts[path]["name"] == "files" and mounts[path]["subPath"] == key and mounts[path]["readOnly"]
        assert files["data"][key] == (backups.RESTORE_GRAPH_SOURCES / source).read_text(encoding="utf-8")
    assert {"name": "files", "configMap": {"name": "ospreyflow-files"}} in pod["volumes"]
