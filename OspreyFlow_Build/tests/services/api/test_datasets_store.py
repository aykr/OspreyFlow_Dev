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


async def test_a_case_reads_one_dataset_and_a_branch_takes_it(store) -> None:
    """ADR-099 Amendment 12: one dataset per case; the read set adds the case's own layer
    (`test_analyst_layer_store.py` has the layer's own cases)."""
    first = await store.create(ALICE, "Fixture Corp")
    second = await store.create(ALICE, "Enron corpus")
    case, branch = new_id(), new_id()
    await store.set_for_case(case, [second.id], ALICE)
    assert (await store.ids_of_case(case))[0] == second.id
    assert [d.name for d in await store.of_case(case, ALICE)] == ["Enron corpus"]
    await store.copy_case(case, branch)
    assert [d.id for d in await store.of_case(branch, ALICE)] == [second.id]
    await store.set_for_case(case, [first.id], ALICE)
    assert [d.id for d in await store.of_case(case, ALICE)] == [first.id]


async def test_another_units_dataset_is_refused_and_nothing_changes(store) -> None:
    alice = ALICE.model_copy(update={"org_unit": f"unit-{new_id()}"})  # a unit of its own
    mine = await store.create(alice, "Mine")
    theirs = await store.create(CAROL, "Theirs")
    case = new_id()
    await store.set_for_case(case, [mine.id], alice)
    with pytest.raises(DatasetRefusedError):
        await store.set_for_case(case, [theirs.id], alice)
    with pytest.raises(DatasetRefusedError):
        await store.set_for_case(case, ["no-such-dataset"], alice)
    assert [d.id for d in await store.of_case(case, alice)] == [mine.id]
    assert [d.id for d in await store.list_for(alice)] == [mine.id]


async def test_postgres_names_no_dataset_to_a_reader_with_no_role(store) -> None:
    """ADR-099 Amendment 11 (the owner, 4 November 2026: "No: no role, no list"): the reader's
    holding a right is a condition of the query itself, so Postgres returns no row of the unit's
    datasets, or of a case's, to a person given a unit before a role — and the same rows as before
    to a person with one. Rule 3's existence clause: the role-less answer is the same empty list
    for a unit holding datasets as for one holding none."""
    unit = f"unit-{new_id()}"
    author = Principal(id="author", clearance="OFFICIAL", org_unit=unit, roles=["analyst"])
    await store.create(author, "Fixture Corp")
    second = await store.create(author, "Enron corpus")
    case = new_id()
    await store.set_for_case(case, [second.id], author)

    for roles in ([], ["default-roles-osprey", "offline_access"]):
        reader = author.model_copy(update={"id": "arrival", "roles": roles})
        assert await store.list_for(reader) == []
        assert await store.of_case(case, reader) == []
        elsewhere = reader.model_copy(update={"org_unit": f"unit-{new_id()}"})
        assert await store.list_for(elsewhere) == []

    for roles in (["analyst"], ["reports_viewer"], ["right:read_reports"]):
        reader = author.model_copy(update={"id": "reader", "roles": roles})
        assert [d.name for d in await store.list_for(reader)] == ["Enron corpus", "Fixture Corp"]
        assert [d.id for d in await store.of_case(case, reader)] == [second.id]


async def _a_composite_and_its_case(store) -> tuple[set[str], str, str]:
    """A source, a composite of two, and a case reading the composite (so it has a layer)."""
    first = await store.create(ALICE, f"Members A {new_id()}")
    second = await store.create(ALICE, f"Members B {new_id()}")
    composite = await store.create_composite(ALICE, f"Both {new_id()}", [first.id, second.id])
    case = new_id()
    await store.set_for_case(case, [composite.id], ALICE)
    layer = await store.ensure_layer(case, unit=ALICE.org_unit, created_by=ALICE.id)
    return {first.id, second.id}, composite.id, layer


async def test_postgres_answers_which_ids_are_composites(store) -> None:
    """ADR-099 Amendment 15: the stamping graph's last word asks the store which ids are
    composites; the test registries answer `set()`, so only this proves the real query. A source,
    a layer and an id nobody registered are not composites."""
    members, composite, layer = await _a_composite_and_its_case(store)
    asked = [*sorted(members), composite, layer, f"no-such-{new_id()}"]
    assert await store.composites_among(asked) == {composite}
    assert await store.composites_among(sorted(members)) == set()
    assert await store.composites_among([]) == set()


async def test_the_composite_check_fails_answered_as_the_fakes_answer(
    store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: with the store answering as the test registries do, the check above is red."""

    async def as_the_fakes(self: object, dataset_ids: object) -> set[str]:
        return set()

    monkeypatch.setattr(PostgresDatasetStore, "composites_among", as_the_fakes)
    _members, composite, _layer = await _a_composite_and_its_case(store)
    assert await store.composites_among([composite]) != {composite}
