"""An Ingest Studio recipe belongs to its dataset (`06_DECISIONS.md` ADR-099 Amendment 3, part d),
in the database itself: a draft made in a case of one dataset is found, listed and versioned only
in a case reading that dataset, inside its unit as before; one made before the amendment names no
dataset and stays the unit's everywhere until `stamp_datasets` places it. Real Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.config import PostgresConfig
from services.api.studio_recipes import StudioRecipeNotFoundError, StudioRecipeStore

from conduit_common.identity import new_id
from schemas.domain import Principal


def _author() -> Principal:
    return Principal(id="author-1", clearance="OFFICIAL", org_unit=f"unit-{new_id()}")


def _in(principal: Principal, *datasets: str) -> Principal:
    return principal.model_copy(update={"datasets": list(datasets)})


@pytest.fixture
async def store():
    s = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def _draft(store: StudioRecipeStore, principal: Principal):  # type: ignore[no-untyped-def]
    return await store.create_draft(
        principal,
        label="Calls",
        connector_profile="csv",
        source_location="/var/lib/osprey/ingest/calls.csv",
        handling={"classification": "OFFICIAL"},
        legal_basis="RIPA 2000",
    )


async def test_a_draft_made_in_a_case_is_its_datasets(store: StudioRecipeStore) -> None:
    author = _author()
    draft = await _draft(store, _in(author, "fixture-corp"))
    assert draft.dataset_id == "fixture-corp"
    assert (await store.get_authorized(draft.recipe_id, _in(author, "fixture-corp"))).recipe_id
    assert [d.recipe_id for d in await store.list_drafts(_in(author, "fixture-corp"))] == [
        draft.recipe_id
    ]
    assert [d.recipe_id for d in await store.list_all(_in(author, "fixture-corp"))] == [
        draft.recipe_id
    ]


async def test_a_draft_is_not_found_in_a_case_of_another_dataset(store: StudioRecipeStore) -> None:
    author = _author()
    draft = await _draft(store, _in(author, "fixture-corp"))
    with pytest.raises(StudioRecipeNotFoundError):
        await store.get_authorized(draft.recipe_id, _in(author, "enron"))
    assert await store.list_drafts(_in(author, "enron")) == []
    assert await store.list_all(_in(author, "enron")) == []


async def test_a_new_version_stays_in_its_recipes_dataset(store: StudioRecipeStore) -> None:
    author = _author()
    draft = await _draft(store, _in(author, "fixture-corp"))
    await store.mark_verified(draft.recipe_id, draft.version, now=datetime.now(UTC))
    await store.publish(
        draft.recipe_id,
        _in(author, "fixture-corp"),
        ontology_version=1,
        git_path="recipes/x.yaml",
        schedule_cron=None,
        schedule_watch=None,
        now=datetime.now(UTC),
    )
    again = await store.create_new_version(
        draft.recipe_id, _in(author, "enron", "fixture-corp"), now=datetime.now(UTC)
    )
    assert again.version == 2 and again.dataset_id == "fixture-corp"


async def test_a_draft_made_before_the_amendment_stays_its_units(store: StudioRecipeStore) -> None:
    author = _author()
    older = await _draft(store, author)  # no case: no dataset
    assert older.dataset_id is None
    assert [d.recipe_id for d in await store.list_drafts(_in(author, "enron"))] == [
        older.recipe_id
    ]
