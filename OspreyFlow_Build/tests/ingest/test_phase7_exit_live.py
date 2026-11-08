"""Phase 7's exit, live (ADR-140 Amendment 12): the pipeline the keys build, published as the
publish route builds it and run through the run route's path against a real ArcadeDB (written
through the Conduit's own `DatasetStampingGraph` and read back through the adapter) and a real
object store (the sources' raw rows, the list's rows and the staged Parquet). Every element read
back names rows of files that exist in that store; a reader of another dataset reads none of it
(rule 4).

`test_phase7_exit.py` is the same walk offline. This proves what that cannot: that the store keeps
each element's sources, and that the files the refs name are in the object store a deployment uses.

Live: run under a lease (`stack_lease.sh acquire studio …`, the ports it prints pinned,
MINIO_ENDPOINT included). Its bucket is its own, made for the run and emptied after.
"""

from __future__ import annotations

import dataclasses
import json
import os
import socket
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pyarrow.fs as pa_fs
import pyarrow.parquet as pq
import pytest
from services.api.dataset_scope import DatasetStampingGraph
from services.api.pipeline_run import run_published_pipeline
from services.ingest import staging
from services.ingest.reference_list_import import import_list
from services.ingest.staging import ObjectStorageConfig

from adapters.graph_arcadedb.testing import arcadedb_adapter
from schemas.domain import Principal
from tests.ingest.test_phase7_exit import _built_and_published
from tests.ingest.test_staged_run import ESTABLISHMENTS, FIXTURES, ONTOLOGY, SCHEME
from tests.services.api.test_studio_staging_routes import _Models

DATASET = "pid"
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1", datasets=[DATASET])
ELSEWHERE = Principal(id="analyst-2", clearance="SECRET", org_unit="unit-1", datasets=["ledger"])


def _answers(endpoint: str) -> bool:
    """Whether the pinned object store is up: the port guard pins an unset endpoint to a closed
    port, which this file then skips rather than fails on."""
    host, _, port = endpoint.rpartition(":")
    try:
        with socket.create_connection((host or "localhost", int(port)), timeout=1):
            return True
    except (OSError, ValueError):
        return False


@pytest.fixture
def storage() -> Iterator[ObjectStorageConfig]:
    # Never the default object store (localhost:9000 is stack a's): only the one a lease pins. The
    # port guard watches Python's sockets, and pyarrow's S3 client opens its own, so this refusal is
    # what keeps an offline run out of a stack's store (8 November 2026: an offline run of this file
    # wrote a bucket to stack a's store without a lease, the friction row's slip).
    endpoint = os.environ.get("MINIO_ENDPOINT", "")
    if not endpoint or not os.environ.get("OSPREY_LANE") or not _answers(endpoint):
        pytest.skip("live: run under a lease, with the MINIO_ENDPOINT and OSPREY_LANE it prints")
    config = dataclasses.replace(
        ObjectStorageConfig.from_env(), bucket=f"studio-l14-{uuid.uuid4().hex[:12]}"
    )
    yield config
    # The run's own bucket, removed whole: the store is a throwaway stack's, and the bucket is this
    # run's alone.
    fs = pa_fs.S3FileSystem(
        endpoint_override=config.endpoint, access_key=config.access_key,
        secret_key=config.secret_key, scheme="https" if config.use_ssl else "http",
        allow_bucket_deletion=True,
    )  # fmt: skip
    if fs.get_file_info(config.bucket).type != pa_fs.FileType.NotFound:
        fs.delete_dir(config.bucket)


def _held(fs: pa_fs.FileSystem, path: str) -> list[dict[str, object]] | None:
    if fs.get_file_info(path).type == pa_fs.FileType.NotFound:
        return None
    with fs.open_input_file(path) as source:
        return pq.read_table(source).to_pylist()


async def test_visits_and_contacts_is_stored_with_every_element_traceable(
    tmp_path: Path, storage: ObjectStorageConfig
) -> None:
    import_list(ESTABLISHMENTS, FIXTURES / "establishments.csv", storage=storage)
    draft, repo = await _built_and_published(tmp_path)
    load_id = f"exit-live-{uuid.uuid4().hex[:8]}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        report = await run_published_pipeline(
            draft,
            LOADER,
            graph=DatasetStampingGraph(graph, dataset=DATASET),
            ontology=ONTOLOGY,
            scheme=SCHEME,
            load_id=load_id,
            investigation_scope="case-live-1",
            repo_root=repo,
            recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
            target_models=_Models([ESTABLISHMENTS.id]),  # type: ignore[arg-type]
            staging_storage=storage,
        )
        [branch] = report.branches
        node_ids = branch.report.created_node_ids
        edge_ids = branch.report.created_edge_ids
        assert node_ids and edge_ids
        nodes = await graph.get_nodes(node_ids, LOADER)
        edges = await graph.get_edges(edge_ids, LOADER)
        assert len(nodes) == len(set(node_ids)) and len(edges) == len(set(edge_ids))
        fs = staging.filesystem(storage)
        for element in [*nodes, *edges]:
            assert element.provenance.sources, element.id
            assert '"row_key"' not in element.model_dump_json()
            for ref in element.provenance.sources:
                row = int(ref.locator.removeprefix("row "))
                if ref.document_id.startswith("reference_list:"):
                    name, version = ref.document_id.removeprefix("reference_list:").split("@v")
                    kept = f"{quote(name, safe='')}@v{version}.parquet"
                    held = _held(fs, f"{storage.bucket}/reference_lists/{DATASET}/{kept}")
                    assert held is not None and 0 <= row < len(held), ref
                    continue
                assert ref.load_id == f"{load_id}:{ref.document_id}", ref
                raw = f"{storage.bucket}/loads/{quote(ref.load_id, safe='')}/raw.parquet"
                held = _held(fs, raw)
                assert held is not None, ref
                found = [
                    h for h in held if h["source"] == ref.document_id and h["row_index"] == row
                ]
                assert len(found) == 1, ref
                assert json.loads(str(found[0]["fields_json"])), ref
        # Rule 4: a case on another dataset reads none of it, nor its sources.
        assert await graph.get_nodes(node_ids, ELSEWHERE) == []
        assert await graph.get_edges(edge_ids, ELSEWHERE) == []
