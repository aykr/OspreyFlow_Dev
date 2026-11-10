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

Synthetic rows (rule 9): phase 7's visits and contacts, a booking marked SECRET in a bound column.
"""

from __future__ import annotations

import uuid
from typing import Any

import pyarrow.fs as pa_fs
import pytest
from services.ingest import staging
from services.ingest.ceiling import CEILING_ENV, AboveTheDeploymentCeiling
from services.ingest.staged_run import run_staged_recipe
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import source_table

from schemas.domain import Principal
from tests.ingest.recipe_test_support import ValidatingGraph
from tests.ingest.test_staged_run import ONTOLOGY, RECIPE, SCHEME, _rows, inputs

LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
STEPS = ("with_establishment", "with_owner", "titled")


def _storage() -> ObjectStorageConfig:
    return ObjectStorageConfig.from_env()


def _held(load_id: str) -> list[str]:
    """The load's step tables the object store holds."""
    storage = _storage()
    fs = staging.filesystem(storage)
    return [
        step
        for step in STEPS
        if fs.get_file_info(f"{storage.bucket}/loads/{load_id}/staged/{step}.parquet").type
        != pa_fs.FileType.NotFound
    ]


async def _load(load_id: str, planted: str) -> Any:
    sources, lists = inputs()
    bookings = [
        {**row, "marking": planted if index == 1 else "OFFICIAL"}
        for index, row in enumerate(_rows("visit_bookings.csv"))
    ]
    sources["visit_bookings"] = source_table(
        "visit_bookings", bookings, load_id=f"{load_id}-vb", key=["booking_id"]
    )
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
    return await run_staged_recipe(
        recipe, sources=sources, lists=lists, dataset_id="pid",
        graph=graph, ontology=ONTOLOGY, tx=tx, principal=LOADER,  # type: ignore[arg-type]
        load_id=load_id, investigation_scope="case-1", storage=_storage(), scheme=SCHEME,
    )  # fmt: skip


async def test_a_refused_staged_load_leaves_no_step_table_in_the_object_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    load_id = f"ceiling-refused-{uuid.uuid4().hex[:12]}"
    with pytest.raises(AboveTheDeploymentCeiling) as refused:
        await _load(load_id, "SECRET")
    assert refused.value.kind == "load"
    assert _held(load_id) == [], "a refused load left its step tables in the object store"


async def test_a_staged_load_within_the_ceiling_keeps_its_step_tables_in_the_object_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CEILING_ENV, "OFFICIAL")
    load_id = f"ceiling-passed-{uuid.uuid4().hex[:12]}"
    await _load(load_id, "OFFICIAL")
    assert _held(load_id) == list(STEPS)
