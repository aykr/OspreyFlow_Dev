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
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts import migrate_sources
from services.api.sources import InMemorySourceStore

from schemas.ingest import StudioRecipeDraft, StudioRecipeStatus

OFFICIAL = {
    "classification": "OFFICIAL", "handling_code": "P", "originator": "u", "owning_unit": "u"
}


def _recipe(rid: str, *, dataset: str | None = "ds-a", location: str | None = "/in/a.csv",
            handling: dict[str, Any] | None = None, legal: str | None = "Synthetic",
            label: str = "Calls") -> StudioRecipeDraft:  # fmt: skip
    return StudioRecipeDraft(
        recipe_id=rid, version=1, status=StudioRecipeStatus.PUBLISHED, label=label,
        connector_profile="generic-csv", source_location=location, handling=handling or OFFICIAL,
        legal_basis=legal, owning_unit="u", created_by="e",
        created_at=datetime(2026, 1, 1, tzinfo=UTC), ready_for_profile=True, dataset_id=dataset,
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
