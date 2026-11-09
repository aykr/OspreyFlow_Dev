"""The promotion record and the layer-merge read grant (ADR-143 decisions 8 and 10; Amendment 2
decision 1; ADR-145 Amendment 4 decision 11; L3.4).

**One row per promotion**, the promotion's own load ledger: its `load_id`, trigger
(`analyst_promotion` from a board, `layer_merge` for a removed case's layer), the case and board it
came from, the dataset it goes into and the layer it comes from, who proposed it and when, its
status and review, the element ids it carries (a revert needs nothing else), the board items those
are, what it left out and why, the highest marking among its items and the dataset's unit. Ids and
counts, never data: what an item *is* stays on the element, read through the reader's own principal
(rule 3).

**Statuses.** `awaiting_review` (the dataset's policy asks for a second person), `committed` (the
load written), `rejected` (with a reason), `reverted` (by the operator command). A decision is
written only from the status it was read with, so of two reviewers at once one wins and the other is
told (`decide` returns `False`).

**The merge read grant** (Amendment 2 decision 1): opening *Merge into the dataset* for a removed
case's layer records a grant to that Author for that layer; the merge reads the layer only through
an open grant of its own; the grant closes when the merge closes (committed, rejected or cancelled)
and is never reopened. Audited by the route.

**Admin's ageing seam** (ADR-145 Amendment 6, `promotion_ageing.WaitingPromotions`): this store
answers `waiting_for_review(reader)` filtered **in its own query** by the reader's unit and the
markings their clearance reaches, and `all_waiting()` for the sweep, through `WaitingFromStore`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal, Protocol

import asyncpg

Status = Literal["awaiting_review", "committed", "rejected", "reverted"]
Trigger = Literal["analyst_promotion", "layer_merge"]


@dataclass(frozen=True)
class PromotionRecord:
    id: str
    load_id: str
    trigger: Trigger
    case_id: str
    board_id: str | None
    dataset_id: str
    layer_id: str
    proposed_by: str
    proposed_at: datetime
    status: Status
    #: The highest marking among its items, and the dataset's unit, for the seam's reader filter.
    marking: str
    unit: str
    node_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    item_ids: tuple[str, ...] = ()
    #: (item id, label, why), in the order the sheet listed them (rule 2).
    left_out: tuple[tuple[str, str, str], ...] = ()
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    reason: str | None = None
    #: A layer merge's grant, closed with it.
    grant_id: str | None = None


@dataclass(frozen=True)
class LayerGrant:
    id: str
    layer_id: str
    case_id: str
    dataset_id: str
    holder: str
    opened_at: datetime
    closed_at: datetime | None = None


class PromotionStore(Protocol):
    async def add(self, record: PromotionRecord) -> None: ...
    async def get(self, promotion_id: str) -> PromotionRecord | None: ...
    async def by_load(self, load_id: str) -> PromotionRecord | None: ...
    async def of_board(self, case_id: str, board_id: str) -> list[PromotionRecord]: ...
    async def into(self, dataset_id: str) -> list[PromotionRecord]: ...
    async def decide(
        self,
        promotion_id: str,
        *,
        was: Status,
        now: Status,
        by: str | None,
        at: datetime,
        reason: str | None = None,
    ) -> bool: ...
    async def waiting(
        self, *, unit: str | None = None, markings: Sequence[str] | None = None
    ) -> list[PromotionRecord]: ...
    async def open_grant(self, grant: LayerGrant) -> None: ...
    async def grant(self, grant_id: str) -> LayerGrant | None: ...
    async def close_grant(self, grant_id: str, at: datetime) -> None: ...


class InMemoryPromotionStore:
    def __init__(self) -> None:
        self.records: dict[str, PromotionRecord] = {}
        self.grants: dict[str, LayerGrant] = {}

    async def add(self, record: PromotionRecord) -> None:
        self.records[record.id] = record

    async def get(self, promotion_id: str) -> PromotionRecord | None:
        return self.records.get(promotion_id)

    async def by_load(self, load_id: str) -> PromotionRecord | None:
        return next((r for r in self.records.values() if r.load_id == load_id), None)

    async def of_board(self, case_id: str, board_id: str) -> list[PromotionRecord]:
        return sorted(
            (r for r in self.records.values() if r.case_id == case_id and r.board_id == board_id),
            key=lambda r: (r.proposed_at, r.id),
        )

    async def into(self, dataset_id: str) -> list[PromotionRecord]:
        return sorted(
            (r for r in self.records.values() if r.dataset_id == dataset_id),
            key=lambda r: (r.proposed_at, r.id),
            reverse=True,
        )

    async def decide(
        self,
        promotion_id: str,
        *,
        was: Status,
        now: Status,
        by: str | None,
        at: datetime,
        reason: str | None = None,
    ) -> bool:
        held = self.records.get(promotion_id)
        if held is None or held.status != was:
            return False
        if now == "reverted":
            self.records[promotion_id] = replace(held, status=now)
        else:
            self.records[promotion_id] = replace(
                held, status=now, reviewed_by=by, reviewed_at=at, reason=reason
            )
        return True

    async def waiting(
        self, *, unit: str | None = None, markings: Sequence[str] | None = None
    ) -> list[PromotionRecord]:
        return sorted(
            (
                r
                for r in self.records.values()
                if r.status == "awaiting_review"
                and (unit is None or r.unit == unit)
                and (markings is None or r.marking in markings)
            ),
            key=lambda r: (r.proposed_at, r.id),
        )

    async def open_grant(self, grant: LayerGrant) -> None:
        self.grants[grant.id] = grant

    async def grant(self, grant_id: str) -> LayerGrant | None:
        return self.grants.get(grant_id)

    async def close_grant(self, grant_id: str, at: datetime) -> None:
        held = self.grants.get(grant_id)
        if held is not None and held.closed_at is None:
            self.grants[grant_id] = replace(held, closed_at=at)


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS promotions (
    id TEXT PRIMARY KEY,
    load_id TEXT NOT NULL UNIQUE,
    trigger TEXT NOT NULL CHECK (trigger IN ('analyst_promotion', 'layer_merge')),
    case_id TEXT NOT NULL,
    board_id TEXT,
    dataset_id TEXT NOT NULL,
    layer_id TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    proposed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('awaiting_review', 'committed', 'rejected', 'reverted')),
    marking TEXT NOT NULL,
    unit TEXT NOT NULL,
    node_ids TEXT[] NOT NULL DEFAULT '{}',
    edge_ids TEXT[] NOT NULL DEFAULT '{}',
    item_ids TEXT[] NOT NULL DEFAULT '{}',
    left_out JSONB NOT NULL DEFAULT '[]',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    reason TEXT,
    grant_id TEXT
);
CREATE INDEX IF NOT EXISTS promotions_by_board ON promotions (case_id, board_id);
CREATE INDEX IF NOT EXISTS promotions_by_dataset ON promotions (dataset_id, proposed_at);
CREATE INDEX IF NOT EXISTS promotions_waiting ON promotions (unit, proposed_at)
    WHERE status = 'awaiting_review';
CREATE TABLE IF NOT EXISTS promotion_layer_grants (
    id TEXT PRIMARY KEY,
    layer_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    holder TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);
"""

_COLUMNS = (
    "id, load_id, trigger, case_id, board_id, dataset_id, layer_id, proposed_by, proposed_at, "
    "status, marking, unit, node_ids, edge_ids, item_ids, left_out, reviewed_by, reviewed_at, "
    "reason, grant_id"
)
_GRANT_COLUMNS = "id, layer_id, case_id, dataset_id, holder, opened_at, closed_at"


def _record(row: Any) -> PromotionRecord:
    held = {k: row[k] for k in _COLUMNS.split(", ")}
    left = held.pop("left_out")
    left = json.loads(left) if isinstance(left, str) else left
    return PromotionRecord(
        **{k: v for k, v in held.items() if k not in ("node_ids", "edge_ids", "item_ids")},
        node_ids=tuple(held["node_ids"] or ()),
        edge_ids=tuple(held["edge_ids"] or ()),
        item_ids=tuple(held["item_ids"] or ()),
        left_out=tuple(tuple(x) for x in left or ()),
    )


class PostgresPromotionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresPromotionStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def add(self, record: PromotionRecord) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO promotions ({_COLUMNS}) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, "
                "$10, $11, $12, $13, $14, $15, $16::jsonb, $17, $18, $19, $20)",
                record.id, record.load_id, record.trigger, record.case_id, record.board_id,
                record.dataset_id, record.layer_id, record.proposed_by, record.proposed_at,
                record.status, record.marking, record.unit, list(record.node_ids),
                list(record.edge_ids), list(record.item_ids),
                json.dumps([list(x) for x in record.left_out]), record.reviewed_by,
                record.reviewed_at, record.reason, record.grant_id,
            )  # fmt: skip

    async def get(self, promotion_id: str) -> PromotionRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM promotions WHERE id = $1", promotion_id
            )
        return _record(row) if row is not None else None

    async def by_load(self, load_id: str) -> PromotionRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM promotions WHERE load_id = $1", load_id
            )
        return _record(row) if row is not None else None

    async def of_board(self, case_id: str, board_id: str) -> list[PromotionRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM promotions WHERE case_id = $1 AND board_id = $2 "
                "ORDER BY proposed_at, id",
                case_id,
                board_id,
            )
        return [_record(r) for r in rows]

    async def into(self, dataset_id: str) -> list[PromotionRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM promotions WHERE dataset_id = $1 "
                "ORDER BY proposed_at DESC, id DESC",
                dataset_id,
            )
        return [_record(r) for r in rows]

    async def decide(
        self,
        promotion_id: str,
        *,
        was: Status,
        now: Status,
        by: str | None,
        at: datetime,
        reason: str | None = None,
    ) -> bool:
        async with self._pool.acquire() as conn:
            if now == "reverted":
                done = await conn.execute(
                    "UPDATE promotions SET status = $3 WHERE id = $1 AND status = $2",
                    promotion_id, was, now,
                )  # fmt: skip
            else:
                done = await conn.execute(
                    "UPDATE promotions SET status = $3, reviewed_by = $4, reviewed_at = $5, "
                    "reason = $6 WHERE id = $1 AND status = $2",
                    promotion_id, was, now, by, at, reason,
                )  # fmt: skip
        return str(done).endswith(" 1")

    async def waiting(
        self, *, unit: str | None = None, markings: Sequence[str] | None = None
    ) -> list[PromotionRecord]:
        # The reader's filter is in the WHERE clause (rule 3): a promotion of another unit, or
        # marked above the reader's clearance, is never read out of the table for them.
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM promotions WHERE status = 'awaiting_review' "
                "AND ($1::text IS NULL OR unit = $1) "
                "AND ($2::text[] IS NULL OR marking = ANY($2::text[])) "
                "ORDER BY proposed_at, id",
                unit,
                list(markings) if markings is not None else None,
            )
        return [_record(r) for r in rows]

    async def open_grant(self, grant: LayerGrant) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO promotion_layer_grants ({_GRANT_COLUMNS}) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                grant.id, grant.layer_id, grant.case_id, grant.dataset_id, grant.holder,
                grant.opened_at, grant.closed_at,
            )  # fmt: skip

    async def grant(self, grant_id: str) -> LayerGrant | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_GRANT_COLUMNS} FROM promotion_layer_grants WHERE id = $1", grant_id
            )
        return LayerGrant(**{k: row[k] for k in _GRANT_COLUMNS.split(", ")}) if row else None

    async def close_grant(self, grant_id: str, at: datetime) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE promotion_layer_grants SET closed_at = $2 "
                "WHERE id = $1 AND closed_at IS NULL",
                grant_id,
                at,
            )


# --- admin's ageing seam (ADR-145 Amendment 6) ---------------------------------------------------


class _Datasets(Protocol):
    async def egress_of(self, dataset_ids: Sequence[str]) -> dict[str, Any]: ...


@dataclass
class WaitingFromStore:
    """`promotion_ageing.WaitingPromotions` (admin's seam), answered from this store. `pending`
    builds the seam's own record (`promotion_ageing.PendingPromotion`) so this module imports
    nothing of admin's; `clears` gives the markings a clearance reaches (the deployment's
    scheme)."""

    store: PromotionStore
    datasets: _Datasets
    pending: Callable[..., Any]
    clears: Callable[[str], Sequence[str]]
    recorded: bool = field(default=True)

    async def _as_pending(self, records: Sequence[PromotionRecord]) -> list[Any]:
        held = await self.datasets.egress_of(sorted({r.dataset_id for r in records}))
        out = []
        for r in records:
            dataset = held.get(r.dataset_id)
            if dataset is None:
                continue
            out.append(
                self.pending(
                    promotion_id=r.id, load_id=r.load_id, dataset_id=r.dataset_id,
                    dataset_name=dataset.name, dataset_unit=r.unit, proposed_by=r.proposed_by,
                    proposed_at=r.proposed_at, dataset_marking=dataset.highest_marking,
                )
            )  # fmt: skip
        return out

    async def waiting_for_review(self, reader: Any) -> list[Any]:
        return await self._as_pending(
            await self.store.waiting(unit=reader.org_unit, markings=self.clears(reader.clearance))
        )

    async def all_waiting(self) -> list[Any]:
        return await self._as_pending(await self.store.waiting())
