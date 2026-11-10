"""A staged run refused at the deployment's ceiling removes its step tables from the real object
store (ADR-148 Amendment 3 point 2; the lane review of L1.10b, item 5). Live: MinIO on the leased
stack.

`test_deployment_ceiling_staged.py` proves the removal over the test store (`LocalStore`), whose
`delete_file` is written to behave as the object store's. This file measures it against the object
store itself, through `staging.filesystem` (pyarrow's S3 file system), so the fake's word is not the
only evidence:
- a refused staged load leaves none of its step tables in the bucket —
  `test_a_refused_staged_load_leaves_no_step_table_in_the_object_store`;
- the control, a load the ceiling passes, whose step tables are there to be found —
  `test_a_staged_load_within_the_ceiling_keeps_its_step_tables_in_the_object_store`.

Each test runs in a bucket of its own, removed whole in teardown whether it passes or fails, and is
skipped unless a lease pins the object store it may write (`test_phase7_exit_live.py`'s fixture: an
offline run never reaches a stack's store, since pyarrow's S3 client opens its own sockets, past the
port guard).

Synthetic rows (rule 9): phase 7's visits and contacts, a booking marked SECRET in a bound column,
joined to an owner marked alike (`test_deployment_ceiling_staged.marked_inputs`), since a Join never
puts a row under another's differing marking.
"""

from __future__ import annotations

import dataclasses
import os
import socket
import uuid
from collections.abc import Iterator

import pyarrow.fs as pa_fs
import pytest
from services.ingest import staging
from services.ingest.ceiling import CEILING_ENV, AboveTheDeploymentCeiling
from services.ingest.staged_run import run_staged_recipe
from services.ingest.staging import ObjectStorageConfig

from schemas.domain import Principal
from tests.ingest.recipe_test_support import ValidatingGraph
from tests.ingest.test_staged_run import ONTOLOGY, RECIPE, SCHEME
from tests.services.api.test_deployment_ceiling_staged import joined_owners, marked_inputs

LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
STEPS = ("with_establishment", "with_owner", "titled")


def _answers(endpoint: str) -> bool:
    """Whether the pinned object store is up: an unset endpoint is pinned to a closed port."""
    host, _, port = endpoint.rpartition(":")
    try:
        with socket.create_connection((host or "localhost", int(port)), timeout=1):
            return True
    except (OSError, ValueError):
        return False


@pytest.fixture
def storage() -> Iterator[ObjectStorageConfig]:
    """The leased stack's object store, in a bucket of this test's own, removed whole afterwards.
    Never the default store (localhost:9000 is stack a's)."""
    endpoint = os.environ.get("MINIO_ENDPOINT", "")
    if not endpoint or not os.environ.get("OSPREY_LANE") or not _answers(endpoint):
        pytest.skip("live: run under a lease, with the MINIO_ENDPOINT and OSPREY_LANE it prints")
    config = dataclasses.replace(
        ObjectStorageConfig.from_env(), bucket=f"studio-b-ceiling-{uuid.uuid4().hex[:12]}"
    )
    yield config
    fs = pa_fs.S3FileSystem(
        endpoint_override=config.endpoint, access_key=config.access_key,
        secret_key=config.secret_key, scheme="https" if config.use_ssl else "http",
        allow_bucket_deletion=True,
    )  # fmt: skip
    if fs.get_file_info(config.bucket).type != pa_fs.FileType.NotFound:
        fs.delete_dir(config.bucket)


def _held(storage: ObjectStorageConfig, load_id: str) -> list[str]:
    """The load's step tables the object store holds."""
    fs = staging.filesystem(storage)
    return [
        step
        for step in STEPS
        if fs.get_file_info(f"{storage.bucket}/loads/{load_id}/staged/{step}.parquet").type
        != pa_fs.FileType.NotFound
    ]


async def _load(storage: ObjectStorageConfig, load_id: str, planted: str) -> ValidatingGraph:
    sources, lists = marked_inputs(planted)  # owners marked as the bookings they join (L1.7)
    entities = [
        e.model_copy(update={"handling": {"classification": {"field": "marking"}}})
        if e.ref == "booking" else e
        for e in RECIPE.row_template.entities
    ]  # fmt: skip
    recipe = RECIPE.model_copy(
        update={"row_template": RECIPE.row_template.model_copy(update={"entities": entities})}
    )
    graph = ValidatingGraph(ONTOLOGY)
    tx = await graph.begin_transaction()
    await run_staged_recipe(
        recipe, sources=sources, lists=lists, dataset_id="pid",
        graph=graph, ontology=ONTOLOGY, tx=tx, principal=LOADER,  # type: ignore[arg-type]
        load_id=load_id, investigation_scope="case-1", storage=storage, scheme=SCHEME,
        subscribed=(),
    )  # fmt: skip
    await graph.commit_transaction(tx)  # the caller commits, as the staged engine's own tests do
    return graph


async def test_a_refused_staged_load_leaves_no_step_table_in_the_object_store(
    storage: ObjectStorageConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    load_id = f"ceiling-refused-{uuid.uuid4().hex[:12]}"
    with pytest.raises(AboveTheDeploymentCeiling) as refused:
        await _load(storage, load_id, "SECRET")
    assert refused.value.kind == "load"
    assert _held(storage, load_id) == [], "a refused load left its step tables in the object store"


async def test_a_staged_load_within_the_ceiling_keeps_its_step_tables_in_the_object_store(
    storage: ObjectStorageConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    load_id = f"ceiling-passed-{uuid.uuid4().hex[:12]}"
    graph = await _load(storage, load_id, "OFFICIAL")
    assert joined_owners(graph) == {"ELLERY", "WHITLOW"}, "the join met no marked owner"
    assert _held(storage, load_id) == list(STEPS)
