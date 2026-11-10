"""What a board holds, by id only, and the watches drawing sets (ADR-143 decisions 4 and 5;
Amendment 2 decision 8; L3.3).

**Ids, never data.** The registry says which graph elements were drawn on which board of which case,
by whom, and whether they were withdrawn. What an item *is* (its type, label, marking, grading,
source) lives on the element in the graph, in the case's analyst layer or its drawn dataset, and is
read through the reader's own principal, filtered in the adapter (rule 3). So a registry row tells a
reader nothing the graph would not: an id the adapter will not return to them is simply not shown.

**Every read names its case** (rule 3: access in the query): an item of another case's board is
absent from the answer exactly as an item that does not exist is.

**A watch per drawn item** (Amendment 2 decision 8), owned by the item's author, kept with the
case, on the case's dataset; withdrawing the item ends it. A load meeting it raises a `drawn_watch`
alert in the one queue: that is L3.6's, with the rules lane's L2.10, which read `active_watches`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import asyncpg

from conduit_common.identity import new_id
from schemas.boards import DrawnWatch

#: `match`: a *Same* or *Not the same* link a decision wrote, registered so that withdrawing its
#: drawn node finds it as it finds a drawn link (the orchestrator's review of L3.3).
ItemKind = Literal["node", "link", "picture", "match"]


@dataclass(frozen=True)
class BoardItem:
    item_id: str
    board_id: str
    case_id: str
    kind: ItemKind
    element_id: str
    author: str
    #: The dataset it was written into: the case's analyst layer, or its drawn dataset.
    dataset_id: str
    created_at: datetime
    withdrawn_at: datetime | None = None
    withdrawn_by: str | None = None
    #: A link's ends (a picture's: its Document and the drawn node it depicts), so a withdrawal
    #: finds every drawn link resting on a node from the registry, by id, with no graph read.
    source: str | None = None
    target: str | None = None
    #: When the element was promoted into a dataset (L3.4 sets it). A withdrawal reads this, never
    #: the element, so a promoted link the withdrawer may not see is left in place and tells them
    #: nothing (the orchestrator's ruling (a), 8 November 2026).
    promoted_at: datetime | None = None


class BoardItemStore(Protocol):
    async def add(self, item: BoardItem, watch: DrawnWatch | None) -> None: ...
    async def on_board(self, case_id: str, board_id: str) -> list[BoardItem]: ...
    async def in_case(self, case_id: str) -> list[BoardItem]: ...
    async def get(self, case_id: str, item_id: str) -> BoardItem | None: ...
    async def by_element(self, case_id: str, element_id: str) -> BoardItem | None: ...
    async def withdraw(
        self, case_id: str, item_ids: Sequence[str], by: str, at: datetime
    ) -> int: ...
    async def active_watches(self, case_id: str) -> list[DrawnWatch]: ...
    #: L3.6: every case's live watches on one dataset, for a load into it (ADR-146 decision 4: a
    #: watch is run by every load into its dataset, whatever pipeline loads it).
    async def active_watches_on(self, dataset_id: str) -> list[DrawnWatch]: ...
    #: L3.6: a match claimed once per case (the drawn element and the loaded node, in the watch's
    #: case): true for the first claim alone, so one alert is raised per match per case, whatever
    #: loads it again. The claim is the dedupe; it is kept when the watch ends.
    async def claim_match(self, watch: DrawnWatch, loaded_id: str, at: datetime) -> bool: ...
    #: L3.4: a promotion's items marked when it commits, cleared when it is reverted.
    async def mark_promoted(
        self, case_id: str, item_ids: Sequence[str], at: datetime | None
    ) -> None: ...


def new_item(
    *,
    board_id: str,
    case_id: str,
    kind: ItemKind,
    element_id: str,
    author: str,
    dataset_id: str,
    item_id: str | None = None,
    source: str | None = None,
    target: str | None = None,
) -> BoardItem:
    return BoardItem(
        item_id=item_id or new_id(),
        board_id=board_id,
        case_id=case_id,
        kind=kind,
        element_id=element_id,
        author=author,
        dataset_id=dataset_id,
        created_at=datetime.now(UTC),
        source=source,
        target=target,
    )


def new_watch(item: BoardItem, *, dataset_id: str | None) -> DrawnWatch:
    """The watch drawing `item` sets: on the case's dataset, owned by the item's author."""
    return DrawnWatch(
        id=new_id(),
        item_id=item.item_id,
        element_id=item.element_id,
        case_id=item.case_id,
        dataset_id=dataset_id,
        owner=item.author,
        created_at=item.created_at,
    )


class InMemoryBoardItemStore:
    def __init__(self) -> None:
        self.items: dict[str, BoardItem] = {}
        self.watches: dict[str, DrawnWatch] = {}
        self.matches: dict[tuple[str, str, str], datetime] = {}

    async def add(self, item: BoardItem, watch: DrawnWatch | None) -> None:
        self.items[item.item_id] = item
        if watch is not None:
            self.watches[watch.id] = watch

    async def on_board(self, case_id: str, board_id: str) -> list[BoardItem]:
        return sorted(
            (i for i in self.items.values() if i.case_id == case_id and i.board_id == board_id),
            key=lambda i: (i.created_at, i.item_id),
        )

    async def in_case(self, case_id: str) -> list[BoardItem]:
        return sorted(
            (i for i in self.items.values() if i.case_id == case_id),
            key=lambda i: (i.created_at, i.item_id),
        )

    async def get(self, case_id: str, item_id: str) -> BoardItem | None:
        item = self.items.get(item_id)
        return item if item is not None and item.case_id == case_id else None

    async def by_element(self, case_id: str, element_id: str) -> BoardItem | None:
        for item in self.items.values():
            if item.case_id == case_id and item.element_id == element_id:
                return item
        return None

    async def withdraw(self, case_id: str, item_ids: Sequence[str], by: str, at: datetime) -> int:
        wanted = set(item_ids)
        for item_id, item in list(self.items.items()):
            if item_id in wanted and item.case_id == case_id and item.withdrawn_at is None:
                self.items[item_id] = replace(item, withdrawn_at=at, withdrawn_by=by)
        ended = 0
        for watch_id, watch in list(self.watches.items()):
            if watch.case_id == case_id and watch.item_id in wanted and watch.ended_at is None:
                self.watches[watch_id] = watch.model_copy(update={"ended_at": at})
                ended += 1
        return ended

    async def active_watches(self, case_id: str) -> list[DrawnWatch]:
        return sorted(
            (w for w in self.watches.values() if w.case_id == case_id and w.ended_at is None),
            key=lambda w: (w.created_at, w.id),
        )

    async def active_watches_on(self, dataset_id: str) -> list[DrawnWatch]:
        return sorted(
            (w for w in self.watches.values() if w.dataset_id == dataset_id and w.ended_at is None),
            key=lambda w: (w.created_at, w.id),
        )

    async def claim_match(self, watch: DrawnWatch, loaded_id: str, at: datetime) -> bool:
        key = (watch.case_id, watch.element_id, loaded_id)
        if key in self.matches:
            return False
        self.matches[key] = at
        return True

    async def mark_promoted(
        self, case_id: str, item_ids: Sequence[str], at: datetime | None
    ) -> None:
        for item_id in item_ids:
            item = self.items.get(item_id)
            if item is not None and item.case_id == case_id:
                self.items[item_id] = replace(item, promoted_at=at)


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS board_items (
    item_id TEXT PRIMARY KEY,
    board_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('node', 'link', 'picture', 'match')),
    element_id TEXT NOT NULL,
    author TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    withdrawn_at TIMESTAMPTZ,
    withdrawn_by TEXT,
    source TEXT,
    target TEXT,
    promoted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS board_items_by_board ON board_items (case_id, board_id);
CREATE INDEX IF NOT EXISTS board_items_by_element ON board_items (case_id, element_id);
CREATE TABLE IF NOT EXISTS drawn_watches (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES board_items (item_id),
    element_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    dataset_id TEXT,
    owner TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS drawn_watches_by_case ON drawn_watches (case_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS drawn_watches_by_dataset ON drawn_watches (dataset_id)
    WHERE ended_at IS NULL;
-- L3.6: each drawn watch's match, once per case (the drawn element and the loaded node).
CREATE TABLE IF NOT EXISTS drawn_watch_matches (
    case_id TEXT NOT NULL,
    element_id TEXT NOT NULL,
    loaded_id TEXT NOT NULL,
    watch_id TEXT NOT NULL,
    matched_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (case_id, element_id, loaded_id)
);
"""

#: The registry's columns, in `BoardItem`'s order, and its row reader: exported for a reader of
#: the registry outside this store (the grading change, `scripts.grading_change`; CARRIES, L3.6).
ITEM_COLUMNS = (
    "item_id, board_id, case_id, kind, element_id, author, dataset_id, created_at, withdrawn_at, "
    "withdrawn_by, source, target, promoted_at"
)
_WATCH_COLUMNS = "id, item_id, element_id, case_id, dataset_id, owner, created_at, ended_at"


def item_from_row(row: Any) -> BoardItem:
    return BoardItem(**{k: row[k] for k in ITEM_COLUMNS.split(", ")})


def _watch(row: Any) -> DrawnWatch:
    return DrawnWatch.model_validate({k: row[k] for k in _WATCH_COLUMNS.split(", ")})


class PostgresBoardItemStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresBoardItemStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def add(self, item: BoardItem, watch: DrawnWatch | None) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"INSERT INTO board_items ({ITEM_COLUMNS}) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
                item.item_id, item.board_id, item.case_id, item.kind, item.element_id,
                item.author, item.dataset_id, item.created_at, item.withdrawn_at,
                item.withdrawn_by, item.source, item.target, item.promoted_at,
            )  # fmt: skip
            if watch is not None:
                await conn.execute(
                    f"INSERT INTO drawn_watches ({_WATCH_COLUMNS}) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                    watch.id, watch.item_id, watch.element_id, watch.case_id, watch.dataset_id,
                    watch.owner, watch.created_at, watch.ended_at,
                )  # fmt: skip

    async def on_board(self, case_id: str, board_id: str) -> list[BoardItem]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {ITEM_COLUMNS} FROM board_items WHERE case_id = $1 AND board_id = $2 "
                "ORDER BY created_at, item_id",
                case_id,
                board_id,
            )
        return [item_from_row(r) for r in rows]

    async def in_case(self, case_id: str) -> list[BoardItem]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {ITEM_COLUMNS} FROM board_items WHERE case_id = $1 "
                "ORDER BY created_at, item_id",
                case_id,
            )
        return [item_from_row(r) for r in rows]

    async def get(self, case_id: str, item_id: str) -> BoardItem | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {ITEM_COLUMNS} FROM board_items WHERE case_id = $1 AND item_id = $2",
                case_id,
                item_id,
            )
        return item_from_row(row) if row is not None else None

    async def by_element(self, case_id: str, element_id: str) -> BoardItem | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {ITEM_COLUMNS} FROM board_items WHERE case_id = $1 AND element_id = $2 "
                "ORDER BY created_at LIMIT 1",
                case_id,
                element_id,
            )
        return item_from_row(row) if row is not None else None

    async def withdraw(self, case_id: str, item_ids: Sequence[str], by: str, at: datetime) -> int:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE board_items SET withdrawn_at = $3, withdrawn_by = $4 "
                "WHERE case_id = $1 AND item_id = ANY($2::text[]) AND withdrawn_at IS NULL",
                case_id,
                list(item_ids),
                at,
                by,
            )
            ended = await conn.fetch(
                "UPDATE drawn_watches SET ended_at = $3 WHERE case_id = $1 "
                "AND item_id = ANY($2::text[]) AND ended_at IS NULL RETURNING id",
                case_id,
                list(item_ids),
                at,
            )
        return len(ended)

    async def active_watches(self, case_id: str) -> list[DrawnWatch]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_WATCH_COLUMNS} FROM drawn_watches WHERE case_id = $1 "
                "AND ended_at IS NULL ORDER BY created_at, id",
                case_id,
            )
        return [_watch(r) for r in rows]

    async def active_watches_on(self, dataset_id: str) -> list[DrawnWatch]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_WATCH_COLUMNS} FROM drawn_watches WHERE dataset_id = $1 "
                "AND ended_at IS NULL ORDER BY created_at, id",
                dataset_id,
            )
        return [_watch(r) for r in rows]

    async def claim_match(self, watch: DrawnWatch, loaded_id: str, at: datetime) -> bool:
        async with self._pool.acquire() as conn:
            done = await conn.execute(
                "INSERT INTO drawn_watch_matches (case_id, element_id, loaded_id, watch_id, "
                "matched_at) VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
                watch.case_id, watch.element_id, loaded_id, watch.id, at,
            )  # fmt: skip
        return bool(done == "INSERT 0 1")

    async def mark_promoted(
        self, case_id: str, item_ids: Sequence[str], at: datetime | None
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE board_items SET promoted_at = $3 "
                "WHERE case_id = $1 AND item_id = ANY($2::text[])",
                case_id,
                list(item_ids),
                at,
            )
