"""`profile: cluster` renders the chart's values from the same services as compose —
`spec/05_DEPLOYMENT.md` §3b, `spec/06_DECISIONS.md` ADR-114 Amendment 12.

The chart's own promises (the manifests valid, nothing but the proxy published, no Secret in them)
are checked against the chart itself in `test_helm_chart.py`; these are the values' promises.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pytest
import yaml
from harness.cluster import REPLICAS, ClusterNotRenderable
from harness.render import render

from schemas.deployment import OspreyConfig

MANAGED = {
    "postgres": {"host": "db.example.internal"},
    "valkey": {"host": "cache.example.internal", "port": 6380, "tls": True},
}
AWS = {**MANAGED, "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
       "search": {"url": "https://search-osprey.eu-west-2.es.amazonaws.com"}}  # fmt: skip
AZURE = {**MANAGED, "media": {"blob_account": "ospreymedia1a2b"}}


def _resolver(ref: str) -> str:
    return "sha256:" + hashlib.sha256(ref.encode()).hexdigest()


def cluster_config(external: dict[str, Any] = AWS, **more: Any) -> OspreyConfig:
    return OspreyConfig.model_validate(
        {
            "profile": "cluster",
            "components": {"analytics_engine": "clickhouse"},
            "network": {"public_origin": "https://osprey.example.org"},
            "reporting": {"sync": True, "superset": True},
            "external": external,
            **more,
        }
    )


def values_for(config: OspreyConfig) -> dict[str, Any]:
    return yaml.safe_load(render(config, resolver=_resolver).artefacts["values.yaml"])


def _workloads(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {w["name"]: w for w in values["workloads"]}


def _containers(values: dict[str, Any]) -> list[dict[str, Any]]:
    pods = [*values["workloads"], *values["jobs"]]
    return [*pods, *(c for p in pods for c in p.get("initContainers", []))]


def test_a_cluster_renders_the_charts_values_and_its_lock() -> None:
    result = render(cluster_config(), resolver=_resolver)
    assert set(result.artefacts) == {"values.yaml", "versions.lock"}
    lock = yaml.safe_load(result.artefacts["versions.lock"])["images"]
    values = values_for(cluster_config())
    ran = {c["name"] for c in [*values["workloads"], *values["jobs"]]} | {"keycloak-db"}
    assert {entry["service"] for entry in lock} == ran


def test_no_workload_runs_what_the_cloud_runs() -> None:
    aws = _workloads(values_for(cluster_config(AWS)))
    assert not {"postgres", "valkey", "objectstore", "opensearch"} & set(aws)
    azure = _workloads(values_for(cluster_config(AZURE)))
    # Azure has no managed S3 or OpenSearch: SeaweedFS beside Blob media, OpenSearch in the cluster.
    assert azure["objectstore"]["kind"] == azure["opensearch"]["kind"] == "StatefulSet"
    assert not {"postgres", "valkey"} & set(azure)


def test_the_replicas_are_the_specifications() -> None:
    workloads = _workloads(values_for(cluster_config()))
    assert {name: workloads[name]["replicas"] for name in REPLICAS} == {
        "workspace": 2, "api": 2, "report-sync": 2, "superset": 2, "worker": 3, "proxy": 2,
        "keycloak": 2, "arcadedb": 3, "clickhouse": 2, "clickhouse-keeper": 3,
    }  # fmt: skip


def test_every_store_keeps_its_data_on_a_volume_of_its_own() -> None:
    workloads = _workloads(values_for(cluster_config(AZURE)))
    for store in ("arcadedb", "clickhouse", "clickhouse-keeper", "objectstore", "opensearch"):
        assert workloads[store]["kind"] == "StatefulSet" and workloads[store]["claims"], store
    assert [c["mountPath"] for c in workloads["arcadedb"]["claims"]] == [
        "/home/arcadedb/databases",
        "/home/arcadedb/config",
    ]
    assert not [w for w in workloads.values() if w["kind"] == "Deployment" and "claims" in w]


def test_every_image_is_pinned_by_digest() -> None:
    for container in _containers(values_for(cluster_config())):
        assert re.search(r"@sha256:[0-9a-f]{64}$", container["image"]), container["name"]


def test_the_job_workers_are_the_releases_own_images() -> None:
    workloads = _workloads(values_for(cluster_config()))
    api = workloads["api"]["image"].split("@")[0]
    registry, tag = api.rsplit("/", 1)[0], api.rsplit(":", 1)[1]
    for worker in ("worker", "report-sync", "superset"):
        assert workloads[worker]["image"].startswith(f"{registry}/{worker}:{tag}@"), worker
    # The report sync's own image starts the sync; the Conduit's entrypoint is not carried over.
    assert "command" not in workloads["report-sync"]


def test_only_the_proxy_is_public() -> None:
    assert [w["name"] for w in values_for(cluster_config())["workloads"] if w.get("public")] == [
        "proxy"
    ]


def test_no_compose_variable_survives_the_translation() -> None:
    text = render(cluster_config(), resolver=_resolver).artefacts["values.yaml"]
    assert not re.findall(r"\$\{[A-Z][A-Z0-9_]*(?::?[-?][^}]*)?\}", text)


def test_every_secret_a_workload_reads_is_listed_for_the_install() -> None:
    values = values_for(cluster_config())
    named = {
        e["secret"] for c in _containers(values) for e in c.get("env", []) if "secret" in e
    }
    assert named and named <= set(values["secrets"]["keys"])
    assert values["secrets"]["defaults"] == {"OSPREY_KEYCLOAK_ADMIN": "admin",
                                             "OSPREY_POSTGRES_USER": "osprey"}  # fmt: skip


def test_no_secret_is_in_the_values() -> None:
    values = values_for(cluster_config())
    assert not [k for k in values["environment"] if re.search("(PASSWORD|SECRET|_TOKEN|_KEY)$", k)]
    for container in _containers(values):
        for entry in container.get("env", []):
            if re.search("(PASSWORD|SECRET|_TOKEN)$", entry["name"]):
                assert "value" not in entry or "$(" in entry["value"], entry


def test_the_stores_are_clustered() -> None:
    values = values_for(cluster_config())
    workloads = _workloads(values)
    java = next(e["value"] for e in workloads["arcadedb"]["env"] if e["name"] == "JAVA_OPTS")
    assert "-Darcadedb.ha.enabled=true" in java and "-Darcadedb.gremlin.engine=groovy" in java
    assert "-Darcadedb.server.name=$(POD_NAME)" in java
    assert "arcadedb-2.arcadedb-headless:2434:2480" in java
    environment = values["environment"]
    assert environment["ARCADEDB_HA"] == "true"  # ADR-101 Amendment 2
    assert environment["CLICKHOUSE_CLUSTER"] == "osprey"  # ADR-114 Amendment 12
    assert (environment["VALKEY_HOST"], environment["VALKEY_PORT"], environment["VALKEY_TLS"]) == (
        "cache.example.internal", "6380", "true",
    )  # fmt: skip
    clickhouse_files = {f["key"] for f in workloads["clickhouse"]["files"]}
    assert clickhouse_files == {"clickhouse.xml", "clickhouse-users.xml"}
    assert "<database_replicated_allow_only_replicated_engine>1<" in values["files"][
        "clickhouse-users.xml"
    ]
    assert "clickhouse-1.clickhouse-headless" in values["files"]["clickhouse.xml"]
    keycloak = {e["name"]: e.get("value") for e in workloads["keycloak"]["env"]}
    assert keycloak["KC_CACHE_STACK"] == "kubernetes" and workloads["keycloak"]["jgroups"]


def test_keycloaks_database_is_made_before_it_starts() -> None:
    keycloak = _workloads(values_for(cluster_config()))["keycloak"]
    assert [c["name"] for c in keycloak["initContainers"]] == ["keycloak-db"]
    assert "-h db.example.internal" in keycloak["initContainers"][0]["args"][0]


def test_a_model_server_has_no_route_out_and_its_download_has() -> None:
    values = values_for(cluster_config())
    workloads = _workloads(values)
    assert workloads["ollama"]["egress"] is False and workloads["whisper"]["egress"] is False
    assert {j["name"]: j["egress"] for j in values["jobs"]} == {
        "ollama-models": True,
        "whisper-models": True,
    }


def test_the_speech_server_waits_for_its_download_to_be_marked_done() -> None:
    values = values_for(cluster_config())
    job = next(j for j in values["jobs"] if j["name"] == "whisper-models")
    mark = "/home/ubuntu/.cache/huggingface/.ospreyflow-whisper-models-done"
    assert job["args"][0].endswith(f"&& touch {mark}")
    wait = _workloads(values)["whisper"]["initContainers"][0]
    assert wait["args"] == [f"until [ -e {mark} ]; do sleep 5; done"]
    assert wait["shared"] == job["shared"]


def test_the_proxy_opens_no_loopback_door_on_a_cluster() -> None:
    caddyfile = values_for(cluster_config())["files"]["Caddyfile"]
    assert "arcadedb:2480" not in caddyfile and "http://:2480" not in caddyfile
    assert "reverse_proxy workspace:8080" in caddyfile


def test_the_evidence_folder_is_read_only_but_its_upload_folder() -> None:
    api = _workloads(values_for(cluster_config()))["api"]
    shared = {s["mountPath"]: (s["subPath"], s["readOnly"]) for s in api["shared"]}
    assert shared["/var/lib/osprey/ingest"] == ("ingest", True)
    assert shared["/var/lib/osprey/ingest/uploaded"] == ("ingest/uploaded", False)


@pytest.mark.parametrize(
    ("components", "said"),
    [
        ({"analytics_engine": "duckdb"}, "DuckDB would give each replica its own events"),
        ({"analytics_engine": "clickhouse", "graph_store": "janusgraph"}, "ArcadeDB's Raft"),
        ({"analytics_engine": "clickhouse", "source_path": "/src"}, "pulls the release's images"),
    ],
)
def test_what_a_cluster_cannot_run_is_refused_in_words(
    components: dict[str, str], said: str
) -> None:
    config = OspreyConfig.model_validate(
        {"profile": "cluster", "components": components, "external": AWS}
    )
    with pytest.raises(ClusterNotRenderable, match=re.escape(said)):
        render(config, resolver=_resolver)


def test_the_compose_profiles_still_render_compose() -> None:
    assert "compose.yaml" in render(OspreyConfig(), resolver=_resolver).artefacts


def test_a_variable_inside_a_value_is_defined_before_the_value_that_names_it() -> None:
    """Kubernetes expands `$(NAME)` only from earlier entries; compose's `${NAME}` inside a longer
    value becomes the variable first, then the value naming it."""
    from harness.cluster import _Translator

    translate = _Translator({"HEAP": "-Xmx1G"})
    env = translate.env({"OPTS": "-p=${PASS:?set} ${HEAP:-x}", "PLAIN": "a$$b", "WHOLE": "${PASS}"})
    assert env == [
        {"name": "PASS", "secret": "PASS"},
        {"name": "HEAP", "config": "HEAP"},
        {"name": "OPTS", "value": "-p=$(PASS) $(HEAP)"},
        {"name": "PLAIN", "value": "a$b"},
        {"name": "WHOLE", "secret": "PASS"},
    ]
    assert translate.secret_keys == {"PASS"}
