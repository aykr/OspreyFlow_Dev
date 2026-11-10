"""`PostgresBoardItemStore` and a board in `PostgresCaseViewStore`, against real Postgres (a lane's
leased test stack; ADR-143 decision 5 and Amendment 2 decision 8; L3.3). Each test in a schema of
its own.

The case filter the in-memory store proves in `test_boards.py` is held here by the SQL: every read
names its case, so another case's item is never retrieved.
`test_the_postgres_case_check_fails_with_the_case_planted_out` shows the clause is what keeps it.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.board_store import (
    BoardItem,
    ItemKind,
    PostgresBoardItemStore,
    new_item,
    new_watch,
)
from services.api.case_views import (
    NotTheViewsCreator,
    PostgresCaseViewStore,
    ViewNotFound,
)
from services.api.config import PostgresConfig

from conduit_common.identity import new_id
from schemas.case_views import NodePosition

K, B = "case-k", "case-b"


@pytest.fixture
async def dsn() -> AsyncIterator[str]:
    base = PostgresConfig.from_env().dsn
    schema = f"boards_{new_id().lower()}"
    admin = await asyncpg.connect(base)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    yield f"{base}{'&' if '?' in base else '?'}search_path={schema}"
    await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.close()


@pytest.fixture
async def items(dsn: str) -> AsyncIterator[PostgresBoardItemStore]:
    held = await PostgresBoardItemStore.connect(dsn)
    yield held
    await held.close()


@pytest.fixture
async def views(dsn: str) -> AsyncIterator[PostgresCaseViewStore]:
    held = await PostgresCaseViewStore.connect(dsn)
    yield held
    await held.close()


def _drawn(board: str = "b-1", case: str = K, kind: ItemKind = "node", **more: str) -> BoardItem:
    return new_item(
        board_id=board, case_id=case, kind=kind, element_id=new_id(), author="alice",
        dataset_id="layer-k", **more,  # type: ignore[arg-type]
    )  # fmt: skip


async def test_an_item_and_its_watch_round_trip_by_case(items: PostgresBoardItemStore) -> None:
    item = _drawn()
    watch = new_watch(item, dataset_id="src")
    await items.add(item, watch)
    assert await items.get(K, item.item_id) == item
    assert await items.on_board(K, "b-1") == [item]
    assert await items.by_element(K, item.element_id) == item
    assert [w.id for w in await items.active_watches(K)] == [watch.id]
    # Another case finds none of it.
    assert await items.get(B, item.item_id) is None
    assert await items.on_board(B, "b-1") == []
    assert await items.in_case(B) == []
    assert await items.active_watches(B) == []


async def test_withdrawing_ends_the_watch_and_only_in_its_case(
    items: PostgresBoardItemStore,
) -> None:
    item = _drawn()
    await items.add(item, new_watch(item, dataset_id="src"))
    assert await items.withdraw(B, [item.item_id], "carol", datetime.now(UTC)) == 0
    assert len(await items.active_watches(K)) == 1
    assert await items.withdraw(K, [item.item_id], "alice", datetime.now(UTC)) == 1
    assert await items.active_watches(K) == []
    held = await items.get(K, item.item_id)
    assert held is not None and held.withdrawn_by == "alice"


async def test_a_match_and_a_promotion_are_kept(items: PostgresBoardItemStore) -> None:
    """The orchestrator's review of L3.3: a decision is registered (`match`), and the registry holds
    when an element was promoted, which a withdrawal reads instead of the element."""
    from dataclasses import replace

    match = _drawn(kind="match", source="n-1", target="n-2")
    promoted = replace(_drawn(kind="link", source="n-1", target="n-3"),
                       promoted_at=datetime(2026, 11, 8, tzinfo=UTC))  # fmt: skip
    await items.add(match, None)
    await items.add(promoted, None)
    assert await items.get(K, match.item_id) == match
    assert await items.get(K, promoted.item_id) == promoted


async def test_a_links_ends_are_kept(items: PostgresBoardItemStore) -> None:
    link = _drawn(kind="link", source="n-1", target="n-2")
    await items.add(link, None)
    held = await items.get(K, link.item_id)
    assert held is not None and (held.source, held.target) == ("n-1", "n-2")


class _CaseClausePlanted:
    """The store's own connection, every statement it sends with its `case_id = $1` clause made
    true: the plant is in the real SQL of every read and of the withdrawal, not a stand-in."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _planted(query: str) -> str:
        assert "case_id = $1" in query, query
        return query.replace("case_id = $1", "($1::text IS NOT NULL)")

    async def fetch(self, query: str, *args: object) -> object:
        return await self._conn.fetch(self._planted(query), *args)

    async def fetchrow(self, query: str, *args: object) -> object:
        return await self._conn.fetchrow(self._planted(query), *args)

    async def execute(self, query: str, *args: object) -> object:
        return await self._conn.execute(self._planted(query), *args)

    def transaction(self) -> object:
        return self._conn.transaction()


class _PlantedPool:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @contextlib.asynccontextmanager
    async def acquire(self) -> AsyncIterator[_CaseClausePlanted]:
        async with self._pool.acquire() as conn:
            yield _CaseClausePlanted(conn)


async def test_the_postgres_case_check_fails_with_the_case_planted_out(
    items: PostgresBoardItemStore,
) -> None:
    """Rule 15: each read and the withdrawal, with its own `case_id` clause made true in the SQL
    it sends, hands case B what is K's; the round-trip test above is what fails then."""
    item = _drawn()
    watch = new_watch(item, dataset_id="src")
    await items.add(item, watch)
    real = items._pool
    items._pool = _PlantedPool(real)  # type: ignore[assignment]
    try:
        assert await items.get(B, item.item_id) is not None
        assert await items.on_board(B, "b-1") != []
        assert await items.in_case(B) != []
        assert await items.by_element(B, item.element_id) is not None
        assert await items.active_watches(B) != []
        assert await items.withdraw(B, [item.item_id], "carol", datetime.now(UTC)) == 1
    finally:
        items._pool = real


async def test_a_board_is_kept_apart_from_views_and_changed_only_by_its_creator(
    views: PostgresCaseViewStore,
) -> None:
    board = await views.save_board(K, "Wing B", "alice", node_ids=["n-1", "n-1", "n-2"])
    assert board.drawing and board.node_ids == ["n-1", "n-2"]
    assert await views.visible_in(K, "alice") == []
    assert [b.id for b in await views.boards_in(K, "alice")] == [board.id]
    assert await views.boards_in(K, "bob") == []  # private until shared
    moved = await views.update_board(
        K, board.id, "alice", add_node_ids=["n-3", "n-1"], layout={"n-3": NodePosition(x=1, y=2)}
    )
    assert moved.node_ids == ["n-1", "n-2", "n-3"] and moved.layout["n-3"].x == 1
    assert (await views.get(K, board.id, "alice")).layout["n-3"].y == 2
    await views.share(K, board.id, "alice")
    with pytest.raises(NotTheViewsCreator):
        await views.update_board(K, board.id, "bob", layout={})
    with pytest.raises(ViewNotFound):
        await views.update_board(B, board.id, "alice", layout={})


# --- L3.6: the drawn watches a load into a dataset runs, and each match claimed once per case ----


async def test_a_datasets_live_watches_are_listed_across_cases_and_an_ended_one_is_not(
    items: PostgresBoardItemStore,
) -> None:
    in_k, in_b, elsewhere, ended = _drawn(), _drawn(case=B), _drawn(), _drawn()
    watches = {}
    for item, dataset in ((in_k, "src"), (in_b, "src"), (elsewhere, "other"), (ended, "src")):
        watches[item.item_id] = new_watch(item, dataset_id=dataset)
        await items.add(item, watches[item.item_id])
    assert await items.withdraw(K, [ended.item_id], "alice", datetime.now(UTC)) == 1
    on_src = {w.id for w in await items.active_watches_on("src")}
    assert on_src == {watches[in_k.item_id].id, watches[in_b.item_id].id}
    assert [w.id for w in await items.active_watches_on("other")] == [
        watches[elsewhere.item_id].id
    ]


async def test_a_match_is_claimed_once_per_case_whatever_loads_it_again(
    items: PostgresBoardItemStore,
) -> None:
    """One alert per match per case: the first claim of (case, drawn element, loaded node) alone
    is true; the same loaded node meeting another case's watch is that case's own first."""
    item = _drawn()
    watch = new_watch(item, dataset_id="src")
    await items.add(item, watch)
    at = datetime.now(UTC)
    assert await items.claim_match(watch, "p-loaded", at) is True
    assert await items.claim_match(watch, "p-loaded", at) is False
    assert await items.claim_match(watch, "p-other", at) is True
    elsewhere = watch.model_copy(update={"case_id": B, "id": "w-b"})
    assert await items.claim_match(elsewhere, "p-loaded", at) is True
