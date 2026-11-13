"""The poc manifest (`harness/cloud_platform/poc_manifest.yaml`, ROUTE_052.md step 2): the one source for
the poc shape's containers, images, sizing, managed services, Entra registrations and egress, held to
the render of the synthetic poc deployment **both ways**.

What a mistake would do, and the case that catches it (rule 12):
- something rendered that the client page never lists (a container, an init container, an image, a
  Job, a database, an egress host) — `test_rendered_but_not_listed_is_named`, one plant per kind;
- something listed that the render does not make — `test_listed_but_not_rendered_is_named`;
- a count, image, request, limit, readiness check, schedule or managed setting that differs —
  `test_a_differing_size_or_setting_is_named`;
- v0.5.2's additions (Superset, the report sync, OpenSearch) left marked pending once their step
  renders them — `test_rendered_though_marked_pending_is_named`;
- the client page's tables kept by hand — `test_the_tables_are_printed_from_the_manifest_alone`.

Each plant edits a copy of the manifest and compares it with the real render (rule 15: the render's
own shape, not a hand-written one).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
import yaml
from harness.cloud_platform import manifest

from tests.harness.test_cloud_platform_render import _config
from tools.cp_policy_check import _resolver


@pytest.fixture(scope="module")
def rendered() -> dict[str, Any]:
    return manifest.rendered(_config("poc"), resolver=_resolver)


@pytest.fixture
def listed() -> dict[str, Any]:
    return copy.deepcopy(manifest.load())


def test_the_manifest_and_the_render_agree(rendered: dict[str, Any], listed: dict[str, Any]) -> None:
    assert manifest.differences(listed, rendered) == []


@pytest.mark.parametrize(
    ("section", "name", "words"),
    [
        ("workloads", "ner", "rendered, not listed: workloads ner"),
        ("init_containers", "litellm/litellm-db", "rendered, not listed: init_containers litellm/litellm-db"),
        ("jobs", "ospreyflow-backup-claims", "rendered, not listed: jobs ospreyflow-backup-claims"),
        ("images", "postgres", "rendered, not listed: images postgres"),
        ("egress", "sts.eu-west-2.amazonaws.com", "rendered, not listed: egress sts.eu-west-2.amazonaws.com"),
    ],
)  # fmt: skip
def test_rendered_but_not_listed_is_named(
    rendered: dict[str, Any], listed: dict[str, Any], section: str, name: str, words: str
) -> None:
    del listed[section][name]
    assert words in manifest.differences(listed, rendered)


def test_a_database_rendered_but_not_listed_is_named(
    rendered: dict[str, Any], listed: dict[str, Any]
) -> None:
    del listed["managed"]["rds"]["databases"]["litellm"]
    assert "rendered, not listed: rds database litellm" in manifest.differences(listed, rendered)


@pytest.mark.parametrize(
    ("section", "name", "entry"),
    [
        ("workloads", "ghost", {"kind": "Deployment", "count": 1, "image": "ospreyflow/api",
                                "requests": {}, "limits": {}, "readiness": "none"}),
        ("init_containers", "api/ghost", {"image": "postgres", "requests": {}, "limits": {}}),
        ("jobs", "ospreyflow-ghost", {"kind": "CronJob", "image": "ospreyflow/api"}),
        ("images", "ospreyflow/ghost", {"ours": True, "built_from": "x"}),
        ("egress", "ghost.example.org", {}),
    ],
)  # fmt: skip
def test_listed_but_not_rendered_is_named(
    rendered: dict[str, Any], listed: dict[str, Any], section: str, name: str, entry: dict[str, Any]
) -> None:
    listed[section][name] = entry
    assert f"listed, not rendered: {section} {name}" in manifest.differences(listed, rendered)


@pytest.mark.parametrize(
    ("path", "value", "words"),
    [
        (("workloads", "api", "count"), 2, "workloads api count"),
        (("workloads", "api", "image"), "ospreyflow/worker", "workloads api image"),
        (("workloads", "arcadedb", "requests", "memory"), "8Gi", "workloads arcadedb requests"),
        (("workloads", "clickhouse", "limits", "cpu"), "4", "workloads clickhouse limits"),
        (("workloads", "api", "readiness"), {"check": "http://127.0.0.1:9999/", "every_seconds": 5},
         "workloads api readiness"),
        (("workloads", "worker", "readiness"), {"check": "http://127.0.0.1:8000/healthz", "every_seconds": 5},
         "workloads worker readiness"),
        (("init_containers", "litellm/litellm-db", "limits", "memory"), "1Gi", "init_containers litellm/litellm-db limits"),
        (("jobs", "ospreyflow-backup", "schedule"), "0 3 * * *", "jobs ospreyflow-backup schedule"),
        (("jobs", "ospreyflow-restore-<set>", "restore-graph", "requests", "memory"), "2Gi",
         "jobs ospreyflow-restore-<set> restore-graph"),
        (("images", "arcadedata/arcadedb", "upstream"), "arcadedata/arcadedb:25.1.1", "images arcadedata/arcadedb upstream"),
        (("images", "ospreyflow/api", "built_from"), "services/worker/Dockerfile", "images ospreyflow/api built_from"),
        (("managed", "rds", "class"), "db.t4g.small", "rds class"),
        (("managed", "rds", "max_connections"), 750, "rds max_connections"),
        (("managed", "elasticache", "node_type"), "cache.t4g.medium", "elasticache node_type"),
        (("managed", "s3", "buckets"), ["media"], "s3 buckets"),
    ],
)  # fmt: skip
def test_a_differing_size_or_setting_is_named(
    rendered: dict[str, Any], listed: dict[str, Any], path: tuple[str, ...], value: Any, words: str
) -> None:
    target = listed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    found = manifest.differences(listed, rendered)
    assert any(line.startswith(f"differs: {words}") for line in found), found


@pytest.mark.parametrize(
    "path",
    [("workloads", "api"), ("images", "ospreyflow/api"), ("egress", "s3.eu-west-2.amazonaws.com"),
     ("managed", "rds", "databases", "litellm")],
)  # fmt: skip
def test_rendered_though_marked_pending_is_named(
    rendered: dict[str, Any], listed: dict[str, Any], path: tuple[str, ...]
) -> None:
    target = listed
    for key in path:
        target = target[key]
    target["pending"] = "v052-something"
    found = manifest.differences(listed, rendered)
    assert any("rendered though marked pending (v052-something)" in line for line in found), found


def test_every_pending_entry_names_a_v052_step(listed: dict[str, Any]) -> None:
    steps = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "pending" in node:
                steps.add(node["pending"])
            for value in node.values():
                walk(value)

    walk(listed)
    assert steps == {"v052-superset"}  # v052-opensearch rendered at 3a


def test_the_tables_are_printed_from_the_manifest_alone(listed: dict[str, Any]) -> None:
    text = manifest.tables(listed)
    for heading in ("Containers", "Jobs and CronJobs", "Images and ECR repositories",
                    "Managed services", "Entra ID registrations", "Egress"):  # fmt: skip
        assert f"## {heading}" in text, heading
    assert "ospreyflow/superset" in text and "db.t4g.large" in text and "1000" in text
    assert "superset" in text and "report-sync" in text and "OpenSearch" in text
    # Totals from the manifest's own rows, v0.5.2's additions in them.
    assert "| **Total** | | **10** |" in text
    listed["workloads"]["superset"]["requests"]["memory"] = "3Gi"
    assert manifest.tables(listed) != text  # nothing printed is held anywhere else
    assert yaml.safe_load(manifest.MANIFEST.read_text())["version"] == "v0.5.2"
