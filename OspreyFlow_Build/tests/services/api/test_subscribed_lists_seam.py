"""The seam between the screening-list connector and L1.4's staged pipeline (`06_DECISIONS.md` ADR-140
Amendment 13 point 10; Amendment 12 decision 7): a dataset's Lookups read its own lists and the
deployment-wide lists it subscribes to, by id, and nothing else. The object store is the real keeper
over a local folder (L1.4's `local_staging`).

What a mistake would do, and the case that catches it:
- a deployment-wide list a dataset does not subscribe to read by its Lookup, at the save gate or in a
  run — `test_a_lookup_reads_a_deployment_list_only_while_the_dataset_subscribes`;
- a subscribed list refused by the gate, or its rows not reaching the run —
  `test_a_subscribed_lists_rows_reach_the_run`;
- one dataset's subscription read for another — the first case, for `ds-b`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from services.api.list_connector import (
    InMemoryListStore,
    ParquetListRows,
    deployment_reference,
)
from services.api.studio_staging import dataset_reference_lists, subscribed_in
from services.ingest.reference_list_import import lists_for_run
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import StagingError, staging_rule_violations

from schemas.list_connector import BlankListMapping, DeploymentListInput
from schemas.staging import LookupStep
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (autouse)

STORAGE = ObjectStorageConfig.from_env()
ROW = {"ref": "CL-001", "primary_name": "Orvald Penmarric", "aliases": None, "date_of_birth": None,
       "nationality": "XA", "identifiers": None, "programme": None, "listing": "sanction",
       "entity_type": "Person"}  # fmt: skip


class _Models:
    async def live(self, dataset_id: str) -> object:
        return SimpleNamespace(reference_lists=[])


async def _kept_list(store: InMemoryListStore) -> str:
    made = await store.add(
        DeploymentListInput(name="Client list", template="blank", location="client.csv",
                            mapping=BlankListMapping(ref="ref", primary_name="primary_name")),
        "admin-1",
    )  # fmt: skip
    ParquetListRows(STORAGE).write(deployment_reference(made, 1), [ROW])
    assert await store.apply_version(made.id, previous=0, version=1, digest="d", entries=1,
                                     at=made.created_at)  # fmt: skip
    return made.id


def _lookup() -> LookupStep:
    return LookupStep(id="screen", kind="lookup", input="customers", list="Client list",
                      on="name", add=[{"column": "programme"}])  # type: ignore[arg-type,call-arg]  # fmt: skip


async def test_a_lookup_reads_a_deployment_list_only_while_the_dataset_subscribes(
    tmp_path: Path,
) -> None:
    store = InMemoryListStore()
    list_id = await _kept_list(store)
    for dataset, expect_readable in (("ds-a", True), ("ds-b", False)):
        if dataset == "ds-a":
            await store.subscribe("ds-a", list_id, "author-1")
        refs = await dataset_reference_lists(_Models(), dataset, STORAGE, lists=store)
        gate = staging_rule_violations([_lookup()], sources=["customers"], lists=refs,
                                       dataset_id=dataset, subscribed=subscribed_in(refs))  # fmt: skip
        assert (gate == []) is expect_readable, (dataset, gate)
    await store.unsubscribe("ds-a", list_id)
    refs = await dataset_reference_lists(_Models(), "ds-a", STORAGE, lists=store)
    assert refs == []
    with pytest.raises(StagingError, match="names no list"):
        lists_for_run([_lookup()], refs, dataset_id="ds-a", storage=STORAGE,
                      subscribed=subscribed_in(refs))  # fmt: skip


async def test_a_subscribed_lists_rows_reach_the_run(tmp_path: Path) -> None:
    store = InMemoryListStore()
    list_id = await _kept_list(store)
    await store.subscribe("ds-a", list_id, "author-1")
    refs = await dataset_reference_lists(_Models(), "ds-a", STORAGE, lists=store)
    lists = lists_for_run([_lookup()], refs, dataset_id="ds-a", storage=STORAGE,
                          subscribed=subscribed_in(refs))  # fmt: skip
    assert [r.cells["primary_name"] for r in lists["Client list"].rows] == ["Orvald Penmarric"]
