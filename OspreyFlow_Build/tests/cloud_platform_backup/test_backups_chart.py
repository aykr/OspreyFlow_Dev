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
    assert check_manifests(docs, target.registry, controller_namespace=target.controller_namespace) == []
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
    assert [c["name"] for c in pod["initContainers"]] == ["fetch-graph", "restore-graph"]
    assert pod["containers"][0]["name"] == "restore-analytics"
    assert {"name": "arcadedb-databases", "persistentVolumeClaim": {"claimName": "databases-arcadedb-0"}} in pod["volumes"]
    assert _rules(docs) == []


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
    values = rendered.values()
    values["backups"]["restore"] = {"set": "20261111T021500Z"}
    docs = _docs(values)
    done = subprocess.run(
        ["docker", "run", "--rm", "-i", "ghcr.io/yannh/kubeconform:v0.6.7", "-strict", "-summary",
         "-ignore-missing-schemas", "-kubernetes-version", "1.31.0", "-"],
        input=yaml.safe_dump_all(docs), capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
