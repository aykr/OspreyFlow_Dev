"""ADR-110 Amendment 6 point 5: the source watches the executor runs, from the stores.

`StoredSourceWatches` pairs every source with a folder watch with each *deployed* pipeline of its
dataset reading its location (published, or needing attention, which the executor records
blocked). A draft is never run by a refresh, and another dataset's pipeline reading a file of the
same name is not this source's. The stores stand in as their in-memory twins; `using_source` is
the real store's question, answered here as it answers it (every status but a previous version).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from services.api.source_refresh import StoredSourceWatches
from services.api.sources import FILES_CONNECTION_ID, InMemorySourceStore

from schemas.domain import Principal
from schemas.ingest import StudioRecipeStatus
from schemas.sources import RegisterSourceInput, SourceRefresh

OWNER = Principal(id="eng-1", clearance="OFFICIAL", org_unit="unit-1", roles=["data_engineer"])


class _Recipes:
    def __init__(self, by_place: dict[tuple[str, str], list[Any]]) -> None:
        self.by_place = by_place

    async def using_source(self, dataset_id: str, location: str) -> list[Any]:
        return list(self.by_place.get((dataset_id, location), []))


def _recipe(recipe_id: str, status: StudioRecipeStatus) -> Any:
    return SimpleNamespace(recipe_id=recipe_id, status=status)


async def test_each_watched_source_is_paired_with_its_deployed_readers_alone() -> None:
    sources = InMemorySourceStore()

    async def register(dataset: str, name: str, refresh: SourceRefresh) -> Any:
        body = RegisterSourceInput(
            connection_id=FILES_CONNECTION_ID,
            name=name,
            location=f"{dataset}/{name}",
            refresh=refresh,
        )
        return await sources.register(dataset, body, OWNER)

    watch = SourceRefresh(trigger="watch", pattern="calls-*.csv")
    watched = await register("ds-1", "calls.csv", watch)
    await register("ds-1", "visits.csv", SourceRefresh())
    recipes = _Recipes(
        {
            ("ds-1", "ds-1/calls.csv"): [
                _recipe("deployed", StudioRecipeStatus.PUBLISHED),
                _recipe("needs-attention", StudioRecipeStatus.FLAGGED),
                _recipe("draft", StudioRecipeStatus.DRAFT),
            ],
            ("ds-1", "ds-1/visits.csv"): [_recipe("by-hand", StudioRecipeStatus.PUBLISHED)],
            ("ds-2", "ds-1/calls.csv"): [_recipe("other-dataset", StudioRecipeStatus.PUBLISHED)],
        }
    )
    pairs = await StoredSourceWatches(sources, recipes).watching()
    assert [r.recipe_id for r, _ in pairs] == ["deployed", "needs-attention"]
    watch = pairs[0][1]
    assert (watch.source_id, watch.dataset_id, watch.pattern) == (watched.id, "ds-1", "calls-*.csv")
    assert (watch.owner, watch.set_at, watch.paused) == ("eng-1", watched.refresh.set_at, False)


async def test_pausing_through_the_watches_pauses_the_sources_policy() -> None:
    sources = InMemorySourceStore()
    body = RegisterSourceInput(
        connection_id=FILES_CONNECTION_ID, name="c", location="ds-1/c.csv",
        refresh=SourceRefresh(trigger="watch", pattern="c-*.csv"),
    )  # fmt: skip
    made = await sources.register("ds-1", body, OWNER)
    watches = StoredSourceWatches(sources, _Recipes({}))
    await watches.set_paused(made.id, paused=True, reason="three refusals")
    assert (await sources.get("ds-1", made.id)).refresh.paused is True
