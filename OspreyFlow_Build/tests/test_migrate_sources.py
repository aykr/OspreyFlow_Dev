"""Each existing recipe's source becomes a registered source (ADR-140 Amendment 4; redesign
phase 3).

`scripts.migrate_sources` plans from the recipe registry and registers what it plans, after a dry
run. What a mistake would do, and the case that catches it:

- one file registered twice for a dataset, once per recipe reading it
  (`test_recipes_sharing_a_file_make_one_source`);
- a source given one recipe's marking when another recipe reads the same file under a different one
  (`test_recipes_disagreeing_on_a_files_governance_register_nothing_and_say_so`);
- a recipe with no dataset or no file planned anyway
  (`test_a_recipe_with_no_dataset_or_file_is_left`);
- a second run registering again (`test_a_file_already_registered_is_not_planned_again`);
- a dry run that writes (`test_a_dry_run_registers_nothing`).

And phase 4 (ADR-110 Amendment 6 point 7, the owner's ruling "Watches move; cron stays"): each
pipeline's folder watch moves onto the source it reads, with its owner, when it was set and whether
it is paused, and the pipeline's own watch is cleared; its cron stays.

- a watch moved without its owner, its time or its pause, so a moved paused chapter 9 watch runs at
  once, or takes a file that arrived before it was set
  (`test_a_watch_moves_onto_its_source_with_its_owner_time_and_pause`);
- the pipeline's own watch left, so it would run again if the source's were set by hand (the same);
- one pattern chosen when the pipelines reading a source watch it under different ones, or two
  owners (`test_pipelines_watching_one_source_differently_are_left_and_named`);
- a watch moved onto a source a keyless pipeline reads, which a refresh never runs
  (`test_a_source_a_keyless_pipeline_reads_is_left_in_words`);
- a source's own policy overwritten (`test_a_source_with_a_policy_of_its_own_is_left`);
- a dry run that moves, or a second run that moves again (`test_a_dry_run_moves_nothing_and_a_run_moves_each_once`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts import migrate_sources
from services.api.sources import InMemorySourceStore

from schemas.ingest import DeduplicateConfig, FieldBinding, StudioRecipeDraft, StudioRecipeStatus

OFFICIAL = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "u",
    "owning_unit": "u",
}


def _recipe(rid: str, *, dataset: str | None = "ds-a", location: str | None = "/in/a.csv",
            handling: dict[str, Any] | None = None, legal: str | None = "Synthetic",
            label: str = "Calls", **schedule: Any) -> StudioRecipeDraft:  # fmt: skip
    return StudioRecipeDraft(
        recipe_id=rid, version=1, status=StudioRecipeStatus.PUBLISHED, label=label,
        connector_profile="generic-csv", source_location=location, handling=handling or OFFICIAL,
        legal_basis=legal, owning_unit="u", created_by="e",
        created_at=datetime(2026, 1, 1, tzinfo=UTC), ready_for_profile=True, dataset_id=dataset,
        **schedule,
    )  # fmt: skip


def test_recipes_sharing_a_file_make_one_source() -> None:
    plan = migrate_sources.plan(
        [_recipe("r1"), _recipe("r2", label="Calls again")], registered=set()
    )
    assert [(p.dataset_id, p.body.location) for p in plan.register] == [("ds-a", "/in/a.csv")]
    assert plan.register[0].body.name == "a.csv"
    assert plan.register[0].body.handling == OFFICIAL
    assert plan.register[0].recipes == ["Calls", "Calls again"]
    twice = migrate_sources.plan([_recipe("r1"), _recipe("r3")], registered=set())
    assert twice.register[0].recipes == ["Calls"], "a label is named once"


def test_recipes_disagreeing_on_a_files_governance_register_nothing_and_say_so() -> None:
    secret = OFFICIAL | {"classification": "SECRET"}
    plan = migrate_sources.plan([_recipe("r1"), _recipe("r2", handling=secret)], registered=set())
    assert plan.register == []
    assert [(c.dataset_id, c.location) for c in plan.conflicts] == [("ds-a", "/in/a.csv")]


def test_a_recipe_with_no_dataset_or_file_is_left() -> None:
    plan = migrate_sources.plan(
        [_recipe("r1", dataset=None), _recipe("r2", location=None)], registered=set()
    )
    assert plan.register == [] and plan.left == 2


def test_a_file_already_registered_is_not_planned_again() -> None:
    plan = migrate_sources.plan([_recipe("r1")], registered={("ds-a", "/in/a.csv")})
    assert plan.register == [] and plan.already == 1


async def test_a_dry_run_registers_nothing_and_a_run_registers_each_once() -> None:
    store = InMemorySourceStore()
    recipes = [_recipe("r1"), _recipe("r2", dataset="ds-b", location="/in/b.csv")]
    said = await migrate_sources.migrate(recipes, store, dry_run=True)
    assert await store.list_for("ds-a") == [] and any("would register" in s for s in said)
    await migrate_sources.migrate(recipes, store, dry_run=False)
    await migrate_sources.migrate(recipes, store, dry_run=False)
    assert [s.location for s in await store.list_for("ds-a")] == ["/in/a.csv"]
    assert [s.location for s in await store.list_for("ds-b")] == ["/in/b.csv"]


# --- phase 4: the watches move onto their sources ---------------------------------------------

SET_AT = datetime(2026, 6, 1, 12, tzinfo=UTC)
KEY = DeduplicateConfig(key=[FieldBinding(field="caller")])
PAUSED = "waiting for its chapter 9 step: resume it on the Studio's Runs tab"


def _watching(rid: str, pattern: str = "a.csv", owner: str = "engineer-1", **more: Any) -> Any:
    fields: dict[str, Any] = {
        "schedule_watch": pattern, "schedule_owner": owner, "schedule_set_at": SET_AT,
        "schedule_case": "case-1", "deduplicate": KEY,
    }  # fmt: skip
    return _recipe(rid, **(fields | more))


class _RecipeWatches:
    """The recipe store's one write here, as `StudioRecipeStore.clear_watch` does it: the watch
    goes, the cron and its owner stay."""

    def __init__(self, recipes: list[StudioRecipeDraft]) -> None:
        self.by_id = {r.recipe_id: r for r in recipes}

    async def clear_watch(self, recipe_id: str) -> None:
        self.by_id[recipe_id] = self.by_id[recipe_id].model_copy(update={"schedule_watch": None})

    @property
    def recipes(self) -> list[StudioRecipeDraft]:
        return list(self.by_id.values())


async def _moved(recipes: list[StudioRecipeDraft], **kwargs: Any) -> tuple[Any, Any, list[str]]:
    store, watches = InMemorySourceStore(), _RecipeWatches(recipes)
    said = await migrate_sources.migrate(
        watches.recipes, store, dry_run=False, watches=watches, **kwargs
    )
    return store, watches, said


async def test_a_watch_moves_onto_its_source_with_its_owner_time_and_pause() -> None:
    chapter_9 = _watching(
        "r1", schedule_paused=True, schedule_paused_reason=PAUSED, schedule_cron="0 6 * * *"
    )
    store, watches, said = await _moved([chapter_9])
    (source,) = await store.list_for("ds-a")
    refresh = source.refresh
    assert (refresh.trigger, refresh.pattern, refresh.owner, refresh.set_at) == (
        "watch",
        "a.csv",
        "engineer-1",
        SET_AT,
    )
    assert (refresh.paused, refresh.paused_reason) == (True, PAUSED)
    assert (refresh.mode, refresh.dropped_rows) == ("snapshot", "keep"), "as it ran before"
    assert source.version == 1, "a moved watch is not a governance edit"
    moved = watches.by_id["r1"]
    assert moved.schedule_watch is None and moved.schedule_cron == "0 6 * * *", "cron stays"
    assert any("moved the watch of Calls onto a.csv for ds-a, paused" in s for s in said)


async def test_pipelines_watching_one_source_differently_are_left_and_named() -> None:
    patterns = [_watching("r1", label="Calls"), _watching("r2", "a*.csv", label="Calls again")]
    owners = [
        _watching("r3", dataset="ds-b", label="Visits"),
        _watching("r4", dataset="ds-b", owner="engineer-2", label="Visits again"),
    ]
    store, watches, said = await _moved([*patterns, *owners])
    for dataset in ("ds-a", "ds-b"):
        (source,) = await store.list_for(dataset)
        assert source.refresh.trigger == "manual"
    assert all(r.schedule_watch for r in watches.recipes), "nothing cleared"
    assert any(
        "left the watches on a.csv for ds-a: Calls, Calls again watch it under different "
        "patterns" in s
        for s in said
    )
    assert any("Visits, Visits again watch it for different owners" in s for s in said)


async def test_a_source_a_keyless_pipeline_reads_is_left_in_words() -> None:
    keyless = _recipe("r2", label="Old calls")
    store, watches, said = await _moved([_watching("r1"), keyless])
    (source,) = await store.list_for("ds-a")
    assert source.refresh.trigger == "manual"
    assert watches.by_id["r1"].schedule_watch == "a.csv"
    assert any("Old calls has no deduplication key" in s for s in said)


async def test_a_source_with_a_policy_of_its_own_is_left() -> None:
    from schemas.sources import RegisterSourceInput, SourceRefresh

    store, watches = InMemorySourceStore(), _RecipeWatches([_watching("r1")])
    own = SourceRefresh(trigger="watch", pattern="a-*.csv")
    await store.register(
        "ds-a",
        RegisterSourceInput(
            connection_id=migrate_sources.FILES_CONNECTION_ID, name="a.csv", location="/in/a.csv", handling=OFFICIAL,
            legal_basis="Synthetic", refresh=own,
        ),
        migrate_sources.MIGRATION,
    )  # fmt: skip
    said = await migrate_sources.migrate(watches.recipes, store, dry_run=False, watches=watches)
    (source,) = await store.list_for("ds-a")
    assert source.refresh.pattern == "a-*.csv" and source.refresh.owner != "engineer-1"
    assert watches.by_id["r1"].schedule_watch == "a.csv"
    assert any("a.csv for ds-a has a refresh policy of its own" in s for s in said)


async def test_a_dry_run_moves_nothing_and_a_run_moves_each_once() -> None:
    store, watches = InMemorySourceStore(), _RecipeWatches([_watching("r1")])
    said = await migrate_sources.migrate(watches.recipes, store, dry_run=True, watches=watches)
    assert await store.list_for("ds-a") == []
    assert watches.by_id["r1"].schedule_watch == "a.csv"
    assert any("would move the watch of Calls onto a.csv for ds-a" in s for s in said)
    await migrate_sources.migrate(watches.recipes, store, dry_run=False, watches=watches)
    again = await migrate_sources.migrate(watches.recipes, store, dry_run=False, watches=watches)
    assert not any("moved the watch" in s for s in again)
    assert any("0 watch(es) to move" in s for s in again)
