"""`PostgresDatasetStore` against real Postgres (`make dev-up`): the half the in-memory store in
`test_datasets.py` cannot prove, that the database itself refuses another unit's dataset, keeps a
case's datasets in the order named, and copies them to a branch (ADR-099)."""

from __future__ import annotations

import asyncpg
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


@pytest.fixture
async def fresh_dsn():
    """A schema of its own, for a table made as an older deployment made it."""
    dsn = PostgresConfig.from_env().dsn
    schema = f"datasets_test_{new_id().lower()}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    yield f"{dsn}{'&' if '?' in dsn else '?'}search_path={schema}"
    await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await conn.close()


async def test_a_case_reads_one_dataset_and_a_case_opened_from_it_takes_it(store) -> None:
    """ADR-099 Amendment 12: one dataset per case; the read set adds the case's own layer
    (`test_analyst_layer_store.py` has the layer's own cases)."""
    first = await store.create(ALICE, "Fixture Corp")
    second = await store.create(ALICE, "Enron corpus")
    case, branch = new_id(), new_id()
    await store.set_for_case(case, [second.id], ALICE)
    assert (await store.ids_of_case(case))[0] == second.id
    assert [d.name for d in await store.of_case(case, ALICE)] == ["Enron corpus"]
    await store.read_the_same_dataset(case, branch)
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
    composites; only this runs the real query. A source, a layer and an id nobody registered are
    not composites."""
    members, composite, layer = await _a_composite_and_its_case(store)
    asked = [*sorted(members), composite, layer, f"no-such-{new_id()}"]
    assert await store.composites_among(asked) == {composite}
    assert await store.composites_among(sorted(members)) == set()
    assert await store.composites_among([]) == set()


async def test_the_composite_check_fails_with_the_kind_left_out_of_the_query(
    store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, in the query's own shape: the same SQL without its `kind` condition, run against
    Postgres, answers every registered id, and the check above is red."""

    async def without_the_kind(self: PostgresDatasetStore, dataset_ids: list[str]) -> set[str]:
        async with self._pool.acquire() as conn:  # noqa: SLF001
            rows = await conn.fetch(
                "SELECT id FROM datasets WHERE id = ANY($1::text[])", list(set(dataset_ids))
            )
        return {r["id"] for r in rows}

    monkeypatch.setattr(PostgresDatasetStore, "composites_among", without_the_kind)
    members, composite, layer = await _a_composite_and_its_case(store)
    asked = [*sorted(members), composite, layer, f"no-such-{new_id()}"]
    assert await store.composites_among(asked) != {composite}


async def test_postgres_answers_the_cases_and_composites_reading_a_dataset(store) -> None:
    """For a dataset's model impact (L3.1b): each case reading the dataset directly or through a
    composite of it, and the composites having it as a member; nothing of a dataset it is not."""
    member = await store.create(ALICE, f"Member {new_id()}")
    partner = await store.create(ALICE, f"Partner {new_id()}")
    elsewhere = await store.create(ALICE, f"Elsewhere {new_id()}")
    composite = await store.create_composite(ALICE, f"Both {new_id()}", [member.id, partner.id])
    direct, through, other = new_id(), new_id(), new_id()
    await store.set_for_case(direct, [member.id], ALICE)
    await store.set_for_case(through, [composite.id], ALICE)
    await store.set_for_case(other, [elsewhere.id], ALICE)
    reading = await store.cases_reading(member.id)
    assert direct in reading and through in reading and other not in reading
    assert await store.cases_reading(partner.id) == [through]
    assert [d.id for d in await store.composites_of(member.id)] == [composite.id]
    assert await store.composites_of(elsewhere.id) == []


async def test_postgres_holds_one_home_case_per_dataset_and_the_owner_setting(store) -> None:
    """ADR-145 Amendment 4 decisions 2 and 7: a dataset's home case, once; a case the home of at
    most one dataset; the System setting kept, the default until set."""
    from datetime import UTC, datetime

    from services.api.datasets import HomeCaseHeld

    from schemas.dataset_model import HomeCase

    first = await store.create(ALICE, f"Home A {new_id()}")
    second = await store.create(ALICE, f"Home B {new_id()}")
    home, other = new_id(), new_id()
    made = datetime(2026, 11, 8, tzinfo=UTC)
    assert await store.home_case_of(first.id) is None
    await store.set_home_case(
        HomeCase(dataset_id=first.id, investigation_id=home, made_at=made, made_by="alice")
    )
    held = await store.home_case_of(first.id)
    assert held is not None and held.investigation_id == home
    assert await store.dataset_of_home_case(home) == first.id
    assert await store.dataset_of_home_case(other) is None
    with pytest.raises(HomeCaseHeld):
        await store.set_home_case(
            HomeCase(dataset_id=first.id, investigation_id=other, made_at=made, made_by="alice")
        )
    with pytest.raises(HomeCaseHeld):
        await store.set_home_case(
            HomeCase(dataset_id=second.id, investigation_id=home, made_at=made, made_by="alice")
        )
    before = await store.owner_setting()
    try:
        await store.set_owner_setting("people_only")
        assert await store.owner_setting() == "people_only"
    finally:
        await store.set_owner_setting(before)


async def test_postgres_holds_a_drawn_dataset_for_its_home_case_alone(store) -> None:
    """ADR-143 Amendment 2 decisions 3 and 5: the kind `drawn` stored (the check widened), its
    highest marking kept, its home case reading it with a layer, never offered for another case
    to choose and refused when one names it."""
    from services.api.datasets import DRAWN, DatasetRefusedError

    home, other = new_id(), new_id()
    drawn = await store.create_drawn(
        ALICE, f"Drawing {new_id()}", highest_marking="OFFICIAL", home_case=home
    )
    assert (drawn.kind, drawn.highest_marking) == (DRAWN, "OFFICIAL")
    (held,) = [d for d in await store.list_all() if d.id == drawn.id]
    assert (held.kind, held.highest_marking) == (DRAWN, "OFFICIAL")
    assert [d.id for d in await store.chosen_of_case(home)] == [drawn.id]
    assert await store.layer_of_case(home) is not None
    assert drawn.id not in [d.id for d in await store.list_for(ALICE)]
    with pytest.raises(DatasetRefusedError):
        await store.set_for_case(other, [drawn.id], ALICE)
    assert await store.chosen_of_case(other) == []


@pytest.mark.parametrize("planted_out", [False, True], ids=["held", "the-kind-check-removed"])
async def test_postgres_never_copies_a_drawn_dataset(
    store, monkeypatch: pytest.MonkeyPatch, planted_out: bool
) -> None:
    """The round-1 review's blocker 1: `read_the_same_dataset` (the alert jump's copy) refuses a
    case reading a drawn dataset before it writes; red with the kind check removed, when the copy
    reads the drawing from a second case."""
    from services.api import datasets as datasets_module
    from services.api.datasets import DrawnNotCopied

    if planted_out:
        monkeypatch.setattr(datasets_module, "refuse_copying_drawn", lambda _kinds: None)
    home = new_id()
    drawn = await store.create_drawn(
        ALICE, f"Drawing {new_id()}", highest_marking="OFFICIAL", home_case=home
    )
    copy = new_id()
    if planted_out:
        await store.read_the_same_dataset(home, copy, case_name="Copy", created_by=ALICE.id)
        assert drawn.id in [d.id for d in await store.chosen_of_case(copy)]
    else:
        with pytest.raises(DrawnNotCopied):
            await store.read_the_same_dataset(home, copy, case_name="Copy", created_by=ALICE.id)
        assert await store.chosen_of_case(copy) == []
        assert await store.layer_of_case(copy) is None


async def test_postgres_widens_an_old_kind_check_to_take_drawn(fresh_dsn: str) -> None:
    """A deployment made before drawn datasets has the column's check without `drawn`: `connect`
    widens it once, and a second `connect` changes nothing."""
    conn = await asyncpg.connect(fresh_dsn)
    try:
        await conn.execute(
            "CREATE TABLE datasets (id TEXT PRIMARY KEY, name TEXT NOT NULL, owning_unit TEXT "
            "NOT NULL, created_at TIMESTAMPTZ NOT NULL, created_by TEXT NOT NULL, kind TEXT NOT "
            "NULL DEFAULT 'source' CHECK (kind IN ('source', 'composite', 'analyst_layer')))"
        )
        for _ in range(2):
            s = await PostgresDatasetStore.connect(fresh_dsn)
            await s.close()
        checks = await conn.fetch(
            "SELECT pg_get_constraintdef(c.oid) AS d FROM pg_constraint c JOIN pg_class t "
            "ON t.oid = c.conrelid WHERE t.relname = 'datasets' AND c.contype = 'c' "
            "AND t.relnamespace = current_schema()::regnamespace "
            "AND pg_get_constraintdef(c.oid) LIKE '%kind%'"
        )
        assert len(checks) == 1 and "drawn" in checks[0]["d"]
    finally:
        await conn.close()


async def test_postgres_merges_a_drawn_dataset_once_and_its_revert_undoes_it(
    fresh_dsn: str,
) -> None:
    """ADR-143 Amendment 2 decision 7 (L3.9): once merged, the drawing's home case reads the target,
    its layer and the drawing itself (read-only), and no other case reads the drawing; a second
    merge is refused; the revert puts the case back as it was. In a schema of its own, dropped
    after (the stacks are shared)."""
    from dataclasses import replace
    from datetime import UTC, datetime

    from services.api.datasets import DrawnAlreadyMerged, DrawnMerged

    s = await PostgresDatasetStore.connect(fresh_dsn)
    try:
        home, other = new_id(), new_id()
        drawn = await s.create_drawn(
            ALICE, f"Drawing {new_id()}", highest_marking="OFFICIAL", home_case=home
        )
        target = await s.create(ALICE, f"Target {new_id()}")
        layer = await s.layer_of_case(home)
        before = await s.ids_of_case(home)
        assert before == [drawn.id, layer]
        merged = DrawnMerged(
            dataset_id=drawn.id, into=target.id, load_id=f"promotion-{new_id()}", case_id=home,
            merged_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        )  # fmt: skip
        await s.merge_drawn(merged)
        assert [d.id for d in await s.chosen_of_case(home)] == [target.id]
        assert await s.ids_of_case(home) == [target.id, layer, drawn.id]
        assert await s.drawn_merged_of(drawn.id) == merged
        with pytest.raises(DrawnAlreadyMerged):
            await s.merge_drawn(replace(merged, load_id=f"promotion-{new_id()}"))
        await s.set_for_case(other, [target.id], ALICE)
        assert drawn.id not in await s.ids_of_case(other)
        assert await s.unmerge_drawn(drawn.id) == merged
        assert await s.ids_of_case(home) == before
        assert await s.drawn_merged_of(drawn.id) is None
        assert await s.unmerge_drawn(drawn.id) is None
    finally:
        await s.close()


async def test_postgres_refuses_a_merge_whose_case_does_not_read_the_drawing(
    fresh_dsn: str,
) -> None:
    """The claim moves the drawing's own case onto the target, in one transaction: a case that
    does not read the drawing moves nothing, so the claim is refused and nothing of it is kept (a
    merge recorded with its case left on the drawing would read the target from no case)."""
    from datetime import UTC, datetime

    from services.api.datasets import DrawnAlreadyMerged, DrawnMerged

    s = await PostgresDatasetStore.connect(fresh_dsn)
    try:
        home, stranger = new_id(), new_id()
        drawn = await s.create_drawn(
            ALICE, f"Drawing {new_id()}", highest_marking="OFFICIAL", home_case=home
        )
        target = await s.create(ALICE, f"Target {new_id()}")
        before = await s.ids_of_case(home)
        with pytest.raises(DrawnAlreadyMerged):
            await s.merge_drawn(
                DrawnMerged(
                    dataset_id=drawn.id, into=target.id, load_id=f"promotion-{new_id()}",
                    case_id=stranger, merged_at=datetime(2026, 11, 10, 9, 0, tzinfo=UTC),
                )
            )  # fmt: skip
        assert await s.drawn_merged_of(drawn.id) is None
        assert await s.ids_of_case(home) == before
    finally:
        await s.close()
