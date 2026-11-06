"""Metering, part 1 (ADR-110 Amendment 6 point 9), through the one run path and into the ledger:
`run_recipe_as` times the run, counts what it put to the object store, stamps the report and the
ledger row, and the Admin area's view withholds the figures as it withholds every count (rule 3).
Against the throwaway Postgres; the load itself is replaced, since what is under test is the
metering around it.

What a mistake would do, and the case that catches it:

- the object store's bytes not counted, because the run was handed the store itself rather than
  the counting one (`test_a_run_is_metered_on_its_report_and_in_the_ledger`);
- the figures lost on the way to the ledger (the same case);
- a failed run given figures it did not finish (`test_a_failed_run_records_no_metering`);
- the figures shown to a reader who may not view the source
  (`test_the_admin_view_withholds_the_metering_with_the_counts`)."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
import services.api.app as app_module
import services.api.recipe_run as run_module
from services.api.config import PostgresConfig
from services.api.recipe_runs import RecipeRunStore

from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.domain import Handling, Principal
from schemas.ingest import LoadReport, RunMetering

SOURCE = Handling(
    classification="SECRET", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _deps(runs: RecipeRunStore) -> app_module.RecipeRunDeps:
    names = [f.name for f in dataclasses.fields(app_module.RecipeRunDeps)]
    stand_ins: dict[str, Any] = {"recipe_runs": runs, "media": InMemoryMediaStore()}
    return app_module.RecipeRunDeps(**{n: stand_ins.get(n, object()) for n in names})  # type: ignore[arg-type]


async def _run(runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch, fail: bool = False) -> Any:
    recipe_id = new_id()

    async def execute(deps: Any, **kwargs: Any) -> LoadReport:
        # What a load puts: a held content item's bytes, twice (content-addressed, kept once).
        await kwargs["media"].put(b"0123456789", "text/plain")
        await kwargs["media"].put(b"0123456789", "text/plain")
        if fail:
            raise RuntimeError("the events could not be written")
        return LoadReport(
            load_id=new_id(), recipe_id=recipe_id, recipe_version=2, rows_read=3,
            created_node_ids=["n1", "n2"], touched_edge_ids=["e1"], markings=[SOURCE],
        )  # fmt: skip

    monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
    monkeypatch.setattr(run_module, "resolve_source_handling", lambda recipe: SOURCE)
    try:
        report = await run_module.run_recipe_as(
            _deps(runs),
            principal=LOADER,
            recipe=SimpleNamespace(recipe_id=recipe_id, version=2),  # type: ignore[arg-type]
            investigation_id="case-1",
            source_location=None,
            trigger="source_refresh",
        )
    except RuntimeError:
        report = None
    (row,) = await runs.for_recipe(recipe_id)
    return report, row


async def test_a_run_is_metered_on_its_report_and_in_the_ledger(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, row = await _run(runs, monkeypatch)
    metering = report.metering
    assert isinstance(metering, RunMetering) and metering.wall_ms >= 0
    assert (metering.rows_read, metering.graph_writes, metering.object_store_bytes) == (3, 3, 20)
    assert (metering.rows_staged, metering.parquet_bytes) == (None, None)
    assert row.metering == metering, "the ledger keeps what the report says"


async def test_a_failed_run_records_no_metering(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    report, row = await _run(runs, monkeypatch, fail=True)
    assert report is None and row.outcome == "failed" and row.metering is None


async def test_the_admin_view_withholds_the_metering_with_the_counts(
    runs: RecipeRunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, row = await _run(runs, monkeypatch)
    scheme = load_uk_le_scheme()
    cleared = app_module._schedule_run_view(row, LOADER, scheme)
    assert cleared.metering == row.metering and not cleared.withheld
    below = Principal(id="b", clearance="OFFICIAL", org_unit="unit-1")
    withheld = app_module._schedule_run_view(row, below, scheme)
    assert withheld.withheld and withheld.metering is None
