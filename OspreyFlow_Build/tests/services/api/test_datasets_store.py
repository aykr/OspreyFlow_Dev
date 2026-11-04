"""`PostgresDatasetStore` against real Postgres (`make dev-up`): the half the in-memory store in
`test_datasets.py` cannot prove, that the database itself refuses another unit's dataset, keeps a
case's datasets in the order named, and copies them to a branch (ADR-099)."""

from __future__ import annotations

import pytest
from services.api.config import PostgresConfig
from services.api.datasets import DatasetRefusedError, PostgresDatasetStore

from conduit_common.identity import new_id
from schemas.domain import Principal

ALICE = Principal(
    id="alice", clearance="OFFICIAL", org_unit=f"unit-{new_id()}", roles=["analyst"]
)
CAROL = Principal(id="carol", clearance="OFFICIAL", org_unit=f"unit-{new_id()}")


@pytest.fixture
async def store():
    s = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_cases_datasets_are_kept_in_order_and_copied_to_a_branch(store) -> None:
    first = await store.create(ALICE, "Fixture Corp")
    second = await store.create(ALICE, "Enron corpus")
    case, branch = new_id(), new_id()
    await store.set_for_case(case, [second.id, first.id], ALICE)
    assert await store.ids_of_case(case) == [second.id, first.id]
    assert [d.name for d in await store.of_case(case, ALICE)] == ["Enron corpus", "Fixture Corp"]
    await store.copy_case(case, branch)
    assert await store.ids_of_case(branch) == [second.id, first.id]
    await store.set_for_case(case, [first.id], ALICE)
    assert await store.ids_of_case(case) == [first.id]


async def test_another_units_dataset_is_refused_and_nothing_changes(store) -> None:
    alice = ALICE.model_copy(update={"org_unit": f"unit-{new_id()}"})  # a unit of its own
    mine = await store.create(alice, "Mine")
    theirs = await store.create(CAROL, "Theirs")
    case = new_id()
    await store.set_for_case(case, [mine.id], alice)
    with pytest.raises(DatasetRefusedError):
        await store.set_for_case(case, [mine.id, theirs.id], alice)
    with pytest.raises(DatasetRefusedError):
        await store.set_for_case(case, [mine.id, "no-such-dataset"], alice)
    assert await store.ids_of_case(case) == [mine.id]
    assert [d.id for d in await store.list_for(alice)] == [mine.id]


async def test_postgres_names_no_dataset_to_a_reader_with_no_role(store) -> None:
    """ADR-099 Amendment 11 (the owner, 4 November 2026: "No: no role, no list"): the reader's
    holding a right is a condition of the query itself, so Postgres returns no row of the unit's
    datasets, or of a case's, to a person given a unit before a role — and the same rows as before
    to a person with one. Rule 3's existence clause: the role-less answer is the same empty list
    for a unit holding datasets as for one holding none."""
    unit = f"unit-{new_id()}"
    author = Principal(id="author", clearance="OFFICIAL", org_unit=unit, roles=["analyst"])
    first = await store.create(author, "Fixture Corp")
    second = await store.create(author, "Enron corpus")
    case = new_id()
    await store.set_for_case(case, [second.id, first.id], author)

    for roles in ([], ["default-roles-osprey", "offline_access"]):
        reader = author.model_copy(update={"id": "arrival", "roles": roles})
        assert await store.list_for(reader) == []
        assert await store.of_case(case, reader) == []
        elsewhere = reader.model_copy(update={"org_unit": f"unit-{new_id()}"})
        assert await store.list_for(elsewhere) == []

    for roles in (["analyst"], ["reports_viewer"], ["right:read_reports"]):
        reader = author.model_copy(update={"id": "reader", "roles": roles})
        assert [d.name for d in await store.list_for(reader)] == ["Enron corpus", "Fixture Corp"]
        assert [d.id for d in await store.of_case(case, reader)] == [second.id, first.id]
