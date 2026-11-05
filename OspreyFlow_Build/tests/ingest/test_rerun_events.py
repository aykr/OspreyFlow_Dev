"""A re-run of the same file holds each transaction's event once (ADR-109 Amendment 8; redesign
phase 1, ADR-140 decision 15's prerequisite).

ADR-109 Amendment 1 recorded, "not fixed", that a re-run wrote every event to the analytics store
again under a new id, doubling the timeline. ADR-127 decision 5 fixed it for every recipe with
`deduplicate`: the case keeps each loaded row's key and a re-run skips the row whole, so no event is
loaded again. `test_row_keys.py` proves that at `load_with_rules`; this proves it where the plan
asks, at the analytics store, through the Studio's own run path (`run_published_recipe`, which the
run route and the scheduler both call). What a mistake would do, and the case that catches it:

- a second run writing its events again, so the timeline doubles for a re-run file
  (`test_a_second_run_of_a_keyed_recipe_holds_each_event_once`; shown red with the key store
  answering that nothing is kept, the shape the run receives when the check is gone);
- a keyless recipe's timeline and its links' occurrences disagreeing after a re-run
  (`test_a_keyless_recipe_reloads_its_events_and_its_occurrences_together`): a recipe without
  `deduplicate` is not idempotent by design (`test_row_keys.py`'s "every row loads every time"),
  and the two counts must move together, not one of them alone."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from services.api.studio_publish import run_published_recipe, serialise_recipe

from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.analytics import EventRecord
from schemas.ingest import LoadReport, StudioRecipeDraft, StudioRecipeStatus
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import (
    CASE,
    LOADER,
    NOW,
    ONTOLOGY,
    ROWS,
    SCHEME,
    KeyStore,
    Sink,
    _recipe,
)


class RecordingAnalytics:
    """The analytics store as the run uses it: events are inserted, never replaced, so an event
    loaded twice is held twice (`load_events` inserts). Geometries are not this test's concern."""

    def __init__(self) -> None:
        self.loaded: list[EventRecord] = []

    async def load_events(self, records: list[EventRecord]) -> None:
        self.loaded.extend(records)

    async def get_geometries(self, refs: Any, principal: Any, *, version: Any) -> list[Any]:
        return []

    async def load_geometries(self, records: Any) -> None:
        return None


def _published(tmp_path: Path, *, deduplicate: bool) -> tuple[Path, StudioRecipeDraft]:
    repo = tmp_path / "repo"
    (repo / "recipes").mkdir(parents=True)
    recipe = _recipe(deduplicate=deduplicate)
    (repo / "recipes" / "private-cash.yaml").write_text(serialise_recipe(recipe))
    source = tmp_path / "cash.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(ROWS)
    draft = StudioRecipeDraft(
        recipe_id="private-cash",
        version=1,
        status=StudioRecipeStatus.PUBLISHED,
        label="Private cash",
        connector_profile="generic-csv",
        source_location=str(source),
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=NOW,
        git_path="recipes/private-cash.yaml",
        ready_for_profile=False,  # recomputed by the model; named for the type checker
    )
    return repo, draft


async def _run_twice(
    tmp_path: Path, *, deduplicate: bool, sink: Sink
) -> tuple[LoadReport, LoadReport, RecordingAnalytics, MergingGraph, int]:
    repo, draft = _published(tmp_path, deduplicate=deduplicate)
    graph, analytics = MergingGraph(ONTOLOGY), RecordingAnalytics()

    async def run(load_id: str) -> LoadReport:
        return await run_published_recipe(
            draft,
            LOADER,
            graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            load_id=load_id,
            investigation_scope=CASE,
            repo_root=repo,
            analytics=analytics,  # type: ignore[arg-type]
            media=InMemoryMediaStore(),
            scheme=SCHEME,
            sink=sink,
        )

    first = await run("load-1")
    after_first = len(analytics.loaded)
    second = await run("load-2")
    return first, second, analytics, graph, after_first


def _transaction(event: EventRecord) -> tuple[str, str, str]:
    """A transaction's identity as the source states it: who paid whom, when."""
    return (event.source_id, event.target_id, event.occurred_at.isoformat())


async def test_a_second_run_of_a_keyed_recipe_holds_each_event_once(tmp_path: Path) -> None:
    first, second, analytics, _, after_first = await _run_twice(
        tmp_path, deduplicate=True, sink=Sink(KeyStore())
    )

    # The first run is as it always was: one event per transaction, every row loaded.
    assert after_first == len(ROWS)
    assert (first.rows_read, first.rows_already_loaded, first.edges_created) == (3, 0, 3)
    # The second adds nothing to the analytics store, and says why.
    assert len(analytics.loaded) == after_first, "the re-run loaded its events again"
    assert (second.rows_read, second.rows_already_loaded, second.edges_created) == (3, 3, 0)
    transactions = [_transaction(e) for e in analytics.loaded]
    assert len(set(transactions)) == len(transactions) == len(ROWS)


async def test_a_keyless_recipe_reloads_its_events_and_its_occurrences_together(
    tmp_path: Path,
) -> None:
    _, second, analytics, graph, after_first = await _run_twice(
        tmp_path, deduplicate=False, sink=Sink(KeyStore())
    )

    assert second.rows_already_loaded == 0
    assert len(analytics.loaded) == 2 * after_first == 2 * len(ROWS)
    # Each link merged with its second write: two occurrences for two events, never one alone.
    assert len(graph.committed_edges) == len(ROWS)
    assert sorted(edge.occurrences for edge in graph.committed_edges) == [2, 2, 2]
