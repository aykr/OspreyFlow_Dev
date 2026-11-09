"""`ownership.owned_items` against real Postgres (a lane's leased test stack; ADR-145 decision 6 and A4;
L3.8). Each test in a schema of its own, dropped in teardown whether it passes or fails.

What the person owns is read in the SQL, each statement naming the administrator's unit and the
markings they clear (rule 3): another unit's items, and an item on a dataset marked above the
administrator's clearance, are never retrieved, so they are neither named nor counted. What a mistake
would do, and the case that catches it (each shown red with its clause planted out,
`process/lanes/case-b/L3.8_RED_RECORD.md`):

- the unit clause dropped: `test_another_units_items_are_left_out`;
- the clearance clause dropped, or a dataset with no marking read as unmarked rather than the
  deployment's highest: `test_an_item_above_the_administrators_clearance_is_never_named_nor_counted`;
- a view's, a board's or a type's analyst-written name in a label (rule 7):
  `test_labels_name_the_case_and_never_what_the_analyst_wrote`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.board_store import PostgresBoardItemStore
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig
from services.api.datasets import PostgresDatasetStore
from services.api.investigations import InvestigationStore
from services.api.link_type_store import LinkTypeProposalStore
from services.api.person_ownership import PROMOTION_KINDS, PostgresOwnershipStore

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

T0 = datetime(2026, 11, 9, tzinfo=UTC)
SCHEME = load_uk_le_scheme()
ADMIN = Principal(id="adm-1", clearance="SECRET", org_unit="unit-1", roles=["osprey-admin"])
SECRET_WORDS = "Operation Nightjar contacts"


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"ownership_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    finally:
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


@pytest.fixture
async def conn(dsn: str) -> AsyncIterator[asyncpg.Connection]:
    """The tables as their own stores make them, so the reads meet the real columns."""
    for store in (InvestigationStore, PostgresCaseViewStore, PostgresBoardItemStore,
                  LinkTypeProposalStore, PostgresDatasetStore):  # fmt: skip
        held = await store.connect(dsn)  # type: ignore[attr-defined]
        await held.close()
    held_conn = await asyncpg.connect(dsn)
    try:
        yield held_conn
    finally:
        await held_conn.close()


@pytest.fixture
async def ownership(dsn: str, conn: asyncpg.Connection) -> AsyncIterator[PostgresOwnershipStore]:
    del conn
    store = await PostgresOwnershipStore.connect(dsn)
    try:
        yield store
    finally:
        await store.close()


async def _case(conn: asyncpg.Connection, case_id: str, name: str, *, unit: str = "unit-1",
                removed: bool = False) -> None:  # fmt: skip
    await conn.execute(
        "INSERT INTO investigations (id, created_at, created_by, owning_unit, name, removed_at) "
        "VALUES ($1, $2, 'seed', $3, $4, $5)",
        case_id, T0, unit, name, T0 if removed else None,
    )  # fmt: skip


async def _dataset(conn: asyncpg.Connection, dataset_id: str, marking: str | None) -> None:
    await conn.execute(
        "INSERT INTO datasets (id, name, owning_unit, created_at, created_by, highest_marking) "
        "VALUES ($1, $1, 'unit-1', $2, 'seed', $3)",
        dataset_id, T0, marking,
    )  # fmt: skip


async def _view(conn: asyncpg.Connection, case_id: str, by: str, *, board: bool = False,
                shared: bool = False, name: str = SECRET_WORDS) -> str:  # fmt: skip
    view_id = f"v-{new_id()}"
    await conn.execute(
        "INSERT INTO case_views (id, case_id, name, created_by, created_at, shared, lens, drawing) "
        "VALUES ($1, $2, $3, $4, $5, $6, '{}'::jsonb, $7)",
        view_id, case_id, name, by, T0, shared, board,
    )  # fmt: skip
    return view_id


async def _proposal(conn: asyncpg.Connection, case_id: str, by: str, *, unit: str = "unit-1",
                    status: str = "pending", dataset: str | None = None) -> str:  # fmt: skip
    proposal_id = f"p-{new_id()}"
    await conn.execute(
        "INSERT INTO link_type_proposals (id, name, label, from_types, to_types, directed, "
        "investigation_id, owning_unit, proposed_by, proposed_at, reason, status, dataset_id) "
        "VALUES ($1, 'NIGHTJAR_CONTACT', $2, ARRAY['Person'], ARRAY['Person'], TRUE, $3, $4, $5, "
        "$6, $2, $7, $8)",
        proposal_id, SECRET_WORDS, case_id, unit, by, T0, status, dataset,
    )  # fmt: skip
    return proposal_id


async def _watch(conn: asyncpg.Connection, case_id: str, owner: str, *, dataset: str | None,
                 ended: bool = False) -> str:  # fmt: skip
    item_id, watch_id = f"i-{new_id()}", f"w-{new_id()}"
    await conn.execute(
        "INSERT INTO board_items (item_id, board_id, case_id, kind, element_id, author, "
        "dataset_id, created_at) VALUES ($1, 'b-1', $2, 'node', 'el-1', $3, $4, $5)",
        item_id, case_id, owner, dataset or "ds-none", T0,
    )  # fmt: skip
    await conn.execute(
        "INSERT INTO drawn_watches (id, item_id, element_id, case_id, dataset_id, owner, "
        "created_at, ended_at) VALUES ($1, $2, 'el-1', $3, $4, $5, $6, $7)",
        watch_id, item_id, case_id, dataset, owner, T0, T0 if ended else None,
    )  # fmt: skip
    return watch_id


async def test_each_kind_the_person_owns_is_listed_by_its_case(
    conn: asyncpg.Connection, ownership: PostgresOwnershipStore
) -> None:
    await _case(conn, "c-k", "Kestrel")
    await _dataset(conn, "ds-off", "OFFICIAL")
    view = await _view(conn, "c-k", "ana-1")
    shared = await _view(conn, "c-k", "ana-1", shared=True)
    board = await _view(conn, "c-k", "ana-1", board=True)
    proposal = await _proposal(conn, "c-k", "ana-1", dataset="ds-off")
    watch = await _watch(conn, "c-k", "ana-1", dataset="ds-off")

    owned = await ownership.owned_by("ana-1", admin=ADMIN, scheme=SCHEME)

    by_id = {i.id: i for i in owned.items}
    assert set(by_id) == {view, shared, board, proposal, watch}
    assert by_id[view].kind == "view" and by_id[view].label == "A private view of the case Kestrel"
    assert by_id[shared].label == "A shared view of the case Kestrel"
    assert (
        by_id[board].kind == "board" and by_id[board].label == "A private board of the case Kestrel"
    )
    assert by_id[proposal].kind == "link_type_proposal"
    assert by_id[watch].kind == "drawn_watch"
    assert {i.investigation_id for i in owned.items} == {"c-k"}
    assert owned.counts == {"view": 2, "board": 1, "link_type_proposal": 1, "drawn_watch": 1}
    assert owned.not_yet_listed == list(PROMOTION_KINDS)


async def test_what_is_no_longer_theirs_or_no_longer_open_is_left_out(
    conn: asyncpg.Connection, ownership: PostgresOwnershipStore
) -> None:
    await _case(conn, "c-k", "Kestrel")
    await _case(conn, "c-gone", "Gone", removed=True)
    await _dataset(conn, "ds-off", "OFFICIAL")
    await _view(conn, "c-k", "ana-2")
    await _view(conn, "c-gone", "ana-1")
    await _proposal(conn, "c-k", "ana-1", status="promoted", dataset="ds-off")
    await _proposal(conn, "c-k", "ana-2", dataset="ds-off")
    await _watch(conn, "c-k", "ana-1", dataset="ds-off", ended=True)

    owned = await ownership.owned_by("ana-1", admin=ADMIN, scheme=SCHEME)

    assert owned.items == [] and owned.counts == {}


async def test_another_units_items_are_left_out(
    conn: asyncpg.Connection, ownership: PostgresOwnershipStore
) -> None:
    await _case(conn, "c-k", "Kestrel")
    await _case(conn, "c-other", "Harrier", unit="unit-2")
    await _dataset(conn, "ds-off", "OFFICIAL")
    mine = await _view(conn, "c-k", "ana-1")
    await _view(conn, "c-other", "ana-1")
    await _view(conn, "c-other", "ana-1", board=True)
    await _proposal(conn, "c-other", "ana-1", unit="unit-2", dataset="ds-off")
    await _watch(conn, "c-other", "ana-1", dataset="ds-off")

    owned = await ownership.owned_by("ana-1", admin=ADMIN, scheme=SCHEME)

    assert [i.id for i in owned.items] == [mine]
    assert owned.counts == {"view": 1}
    assert "Harrier" not in owned.model_dump_json() and "c-other" not in owned.model_dump_json()
    # An administrator with no unit reads nothing at all (default-deny).
    unitless = ADMIN.model_copy(update={"org_unit": None})
    assert (await ownership.owned_by("ana-1", admin=unitless, scheme=SCHEME)).items == []


async def test_an_item_above_the_administrators_clearance_is_never_named_nor_counted(
    conn: asyncpg.Connection, ownership: PostgresOwnershipStore
) -> None:
    await _case(conn, "c-k", "Kestrel")
    await _dataset(conn, "ds-off", "OFFICIAL")
    await _dataset(conn, "ds-top", "TOP SECRET")
    await _dataset(conn, "ds-unmarked", None)
    seen = {await _proposal(conn, "c-k", "ana-1", dataset="ds-off"),
            await _watch(conn, "c-k", "ana-1", dataset="ds-off")}  # fmt: skip
    hidden = {
        await _proposal(conn, "c-k", "ana-1", dataset="ds-top"),
        await _watch(conn, "c-k", "ana-1", dataset="ds-top"),
        # No marking set reads as the deployment's highest (the strict side, as the Model tab's).
        await _proposal(conn, "c-k", "ana-1", dataset="ds-unmarked"),
        await _watch(conn, "c-k", "ana-1", dataset="ds-unmarked"),
        await _proposal(conn, "c-k", "ana-1", dataset=None),
    }

    owned = await ownership.owned_by("ana-1", admin=ADMIN, scheme=SCHEME)

    assert {i.id for i in owned.items} == seen
    assert owned.counts == {"link_type_proposal": 1, "drawn_watch": 1}
    assert not any(h in owned.model_dump_json() for h in hidden)
    # An administrator cleared to the top sees all of them.
    top = ADMIN.model_copy(update={"clearance": "TOP SECRET"})
    assert {i.id for i in (await ownership.owned_by("ana-1", admin=top, scheme=SCHEME)).items} == (
        seen | hidden
    )


async def test_labels_name_the_case_and_never_what_the_analyst_wrote(
    conn: asyncpg.Connection, ownership: PostgresOwnershipStore
) -> None:
    await _case(conn, "c-k", "Kestrel")
    await _case(conn, "c-unnamed", "")
    await _dataset(conn, "ds-off", "OFFICIAL")
    await _view(conn, "c-k", "ana-1")
    await _view(conn, "c-k", "ana-1", board=True, shared=True)
    await _proposal(conn, "c-k", "ana-1", dataset="ds-off")
    await _watch(conn, "c-k", "ana-1", dataset="ds-off")
    await _view(conn, "c-unnamed", "ana-1")

    owned = await ownership.owned_by("ana-1", admin=ADMIN, scheme=SCHEME)

    wire = owned.model_dump_json()
    assert SECRET_WORDS not in wire and "NIGHTJAR" not in wire
    assert "A private view of the case c-unnamed" in {i.label for i in owned.items}
    assert {i.label for i in owned.items if i.investigation_id == "c-k"} == {
        "A private view of the case Kestrel",
        "A shared board of the case Kestrel",
        "A proposed link type in the case Kestrel, waiting for a decision",
        "A watch on an item they drew in the case Kestrel",
    }
