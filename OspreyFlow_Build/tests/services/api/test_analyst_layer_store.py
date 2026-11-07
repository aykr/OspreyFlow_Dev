"""`PostgresDatasetStore`'s analyst layers and one dataset per case, against real Postgres
(`make dev-up`, under the stack lease): the half `test_analyst_layer.py` cannot prove in memory,
that the queries themselves leave layers out and the indexes hold (ADR-143 decision 1; ADR-099
Amendments 12 and 13)."""

from __future__ import annotations

import asyncpg
import pytest
from services.api.config import PostgresConfig
from services.api.datasets import (
    ANALYST_LAYER,
    BranchLayerError,
    DatasetRefusedError,
    PostgresDatasetStore,
    UnknownDatasetEgressError,
    index_one_dataset_per_case,
)

from conduit_common.identity import new_id
from schemas.domain import Principal


def _analyst() -> Principal:
    return Principal(
        id="alice", clearance="OFFICIAL", org_unit=f"unit-{new_id()}", roles=["analyst"]
    )


@pytest.fixture
async def fresh_dsn():
    """A schema of its own, so a check over the whole table (the one-row index, the name index)
    is not decided by rows other tests left in the shared database. asyncpg passes an unknown
    DSN parameter on as a server setting, so `search_path` points every connection at it."""
    dsn = PostgresConfig.from_env().dsn
    schema = f"layer_test_{new_id().lower()}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f'CREATE SCHEMA "{schema}"')
    sep = "&" if "?" in dsn else "?"
    yield f"{dsn}{sep}search_path={schema}"
    await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await conn.close()


@pytest.fixture
async def store():
    s = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    yield s
    await s.close()


async def test_a_case_reads_its_source_and_its_own_layer_and_lists_never_show_it(store) -> None:
    alice = _analyst()
    source = await store.create(alice, "Source")
    case_a, case_b = new_id(), new_id()
    await store.set_for_case(case_a, [source.id], alice, case_name="Case A")
    await store.set_for_case(case_b, [source.id], alice, case_name="Case B")
    layer_a, layer_b = await store.layer_of_case(case_a), await store.layer_of_case(case_b)
    assert layer_a and layer_b and layer_a != layer_b
    assert await store.ids_of_case(case_a) == [source.id, layer_a]
    assert await store.ids_of_case(case_b) == [source.id, layer_b]
    no_role = alice.model_copy(update={"roles": []})
    listed = {d.id for d in await store.list_all()}
    for reader in (alice, no_role):
        listed |= {d.id for d in await store.list_for(reader)}
        listed |= {d.id for d in await store.of_case(case_a, reader)}
    assert layer_a not in listed and layer_b not in listed
    # Its kind is in the row itself (not only inferred from `layer_of`).
    held = (await store.egress_of([layer_a]))[layer_a]
    assert (held.kind, held.layer_of) == (ANALYST_LAYER, case_a)


async def test_the_list_check_fails_with_the_condition_planted_out(store, monkeypatch) -> None:
    """Rule 15: with the one condition every Postgres list carries replaced by `TRUE`, the layer
    is listed, by `list_for` and by `list_all` alike, so the test above could have seen it."""
    from services.api import datasets as datasets_module

    monkeypatch.setattr(datasets_module, "_OFFERED", "TRUE")
    alice = _analyst()
    source = await store.create(alice, "Source")
    case = new_id()
    await store.set_for_case(case, [source.id], alice)
    layer = await store.layer_of_case(case)
    assert layer in {d.id for d in await store.list_for(alice)}
    assert layer in {d.id for d in await store.list_all()}


async def test_a_layer_is_refused_as_a_missing_dataset_and_its_name_is_free(store) -> None:
    alice = _analyst()
    source = await store.create(alice, "Source")
    case = new_id()
    await store.set_for_case(case, [source.id], alice, case_name="Shipping")
    layer = await store.layer_of_case(case)
    assert layer
    for named in (layer, "no-such-dataset"):
        with pytest.raises(DatasetRefusedError):
            await store.set_for_case(new_id(), [named], alice)
        with pytest.raises(DatasetRefusedError):
            await store.create_composite(alice, f"With {named}", [source.id, named])
    from services.api.datasets import layer_name

    taken = layer_name("Shipping", case)  # the layer's own name, which no response carries
    assert (await store.create(alice, taken)).name == taken


async def test_a_case_reads_one_dataset_and_a_composite_reads_its_own_id_first(store) -> None:
    alice = _analyst()
    first, second = await store.create(alice, "First"), await store.create(alice, "Second")
    case = new_id()
    with pytest.raises(DatasetRefusedError):
        await store.set_for_case(case, [first.id, second.id], alice)
    both = await store.create_composite(alice, "Both", [first.id, second.id])
    await store.set_for_case(case, [both.id], alice)
    layer = await store.layer_of_case(case)
    assert await store.ids_of_case(case) == [both.id, first.id, second.id, layer]
    assert [d.id for d in await store.of_case(case, alice)] == [both.id]


async def test_a_branch_holds_no_layer_and_reads_its_originals(store) -> None:
    """ADR-144 Amendment 1 decision 2 (the owner, 7 November 2026), on Postgres: a branch, a branch
    of a branch included, holds no layer of its own and reads its original's, read-only."""
    alice = _analyst()
    source = await store.create(alice, "Source")
    parent, branch, twig = new_id(), new_id(), new_id()
    await store.set_for_case(parent, [source.id], alice)
    layer = await store.layer_of_case(parent)
    await store.copy_case(parent, branch)
    await store.copy_case(branch, twig)
    for case in (branch, twig):
        assert await store.layer_of_case(case) is None
        assert await store.read_only_layer_of(case) == layer
        assert await store.ids_of_case(case) == [source.id, layer]
    with pytest.raises(BranchLayerError):
        await store.ensure_layer(branch, unit=alice.org_unit, created_by=alice.id)


async def test_a_case_opened_from_an_alert_keeps_a_layer_of_its_own(store) -> None:
    """The exception (ADR-143 Amendment 1 item 3): its maker may hold no level on the original."""
    alice = _analyst()
    source = await store.create(alice, "Source")
    parent, jump = new_id(), new_id()
    await store.set_for_case(parent, [source.id], alice)
    await store.copy_case(parent, jump, created_by="bob", as_a_branch=False)
    own = await store.layer_of_case(jump)
    assert own not in (None, await store.layer_of_case(parent))
    assert await store.read_only_layer_of(jump) is None
    assert await store.ids_of_case(jump) == [source.id, own]


async def test_a_layers_egress_is_the_strictest_of_its_cases(store) -> None:
    alice = _analyst()
    source = await store.create(alice, "Source")
    await store.set_egress(source.id, "contracted")
    case = new_id()
    await store.set_for_case(case, [source.id], alice)
    layer = await store.layer_of_case(case)
    assert (await store.egress_of([layer]))[layer].egress == "contracted"
    # An administrator cannot set it: refused as a dataset that does not exist.
    with pytest.raises(UnknownDatasetEgressError):
        await store.set_egress(layer, "any")
    assert (await store.egress_of([layer]))[layer].egress == "contracted"


async def test_a_composite_cases_layer_takes_the_strictest_of_members_that_differ(store) -> None:
    """ADR-136 Amendment 1 on Postgres: members `any` and `contracted`, the composite set to `any`
    by an administrator; the layer takes `contracted`, under that member's name."""
    alice = _analyst()
    loose, tight = await store.create(alice, "Loose"), await store.create(alice, "Tight")
    await store.set_egress(loose.id, "any")
    await store.set_egress(tight.id, "contracted")
    both = await store.create_composite(alice, "Loose and tight", [loose.id, tight.id])
    await store.set_egress(both.id, "any")
    case = new_id()
    await store.set_for_case(case, [both.id], alice)
    layer = await store.layer_of_case(case)
    held = (await store.egress_of([layer]))[layer]
    assert (held.egress, held.name) == ("contracted", "Tight")


async def test_the_one_dataset_index_is_refused_while_a_case_names_two(fresh_dsn) -> None:
    """The store's rule, shown both ways (rule 15): with a case naming two the index is not
    built; once none does it is, and it then refuses a second row."""
    dsn = fresh_dsn
    store = await PostgresDatasetStore.connect(dsn)
    conn = await asyncpg.connect(dsn)
    try:
        alice = _analyst()
        first, second = await store.create(alice, "First"), await store.create(alice, "Second")
        case = new_id()
        await conn.execute("DROP INDEX IF EXISTS investigation_datasets_one_per_case")
        await conn.executemany(
            "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
            "VALUES ($1, $2, $3)",
            [(case, first.id, 0), (case, second.id, 1)],
        )
        assert await index_one_dataset_per_case(conn) is False
        await store.set_for_case(case, [first.id], alice)
        assert await index_one_dataset_per_case(conn) is True
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
                "VALUES ($1, $2, 1)",
                case,
                second.id,
            )
    finally:
        await conn.close()
        await store.close()


async def test_a_name_index_made_before_layers_is_rebuilt_to_leave_them_out(fresh_dsn) -> None:
    dsn = fresh_dsn
    await (await PostgresDatasetStore.connect(dsn)).close()  # the tables, as a deployment has them
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DROP INDEX IF EXISTS datasets_unit_name_unique")
        await conn.execute(
            "CREATE UNIQUE INDEX datasets_unit_name_unique ON datasets "
            "(owning_unit, lower(regexp_replace(btrim(name), '\\s+', ' ', 'g')))"
        )
        store = await PostgresDatasetStore.connect(dsn)
        await store.close()
        indexdef = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'datasets_unit_name_unique' "
            "AND schemaname = current_schema()"
        )
        assert "analyst_layer" in indexdef
    finally:
        await conn.close()
