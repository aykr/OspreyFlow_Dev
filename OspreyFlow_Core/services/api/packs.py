"""Case report packs (`06_DECISIONS.md` ADR-113 decisions 3 to 5, Amendment 1): the rules that
decide who reads which item, and the store of packs, their items and their published versions.

An item keeps every distinct handling it rests on — a trend snapshot's counted events, an
assessment's supporting entities, a chosen entity, a note's own marking — and a reader gets the item
only if they may view each of them (rule 3). Classification alone is not enough: a restricted
handling code limits a record to its units whatever the reader's clearance. An entity or an
assessment is also checked again as the reader, against the graph now, so one reclassified since it
was added is withheld too. A reader is told how many items were withheld, never which: items are
served in order, without their positions, so a withheld one leaves no gap.

A published version is a copy of the draft's items at that moment, never a view of them: the draft
can change afterwards and the version does not.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import asyncpg
from pydantic import BaseModel, Field

from conduit_common.identity import new_id
from ontology.errors import HandlingSchemeError
from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from schemas.analytics import CountedHandling
from schemas.domain import Handling, Judgement, Node, Principal
from schemas.packs import (
    AssessmentSnapshot,
    EntitySnapshot,
    PackItem,
    PackItemKind,
    PackVersionSummary,
    ReportPack,
)
from schemas.trends import TrendFigures

from .alert_queue import node_name
from .assessments import judgement_visible_to, resolve_superseded_citation
from .trends import highest


class PackItemRefused(ValueError):
    """An item that cannot be added or changed as asked; said in words (a 422)."""


class PackHasWithheldItems(Exception):
    """Publishing refused: the draft holds items the publisher may not see (a 409, with the
    count)."""

    def __init__(self, withheld: int) -> None:
        super().__init__(f"{withheld} item(s) in this pack are withheld from you")
        self.withheld = withheld


class StoredPackItem(PackItem):
    """An item with what it rests on. The handlings stay in the Conduit: a reader is served a
    `PackItem`."""

    handlings: list[Handling] = Field(default_factory=list)

    def served(self) -> PackItem:
        return PackItem.model_validate(self.model_dump(exclude={"handlings"}))


class PackVersion(BaseModel):
    pack_id: str
    version: int
    published_at: datetime
    published_by: str
    items: list[StoredPackItem]
    withdrawn_at: datetime | None = None
    withdrawn_by: str | None = None
    withdrawal_reason: str | None = None

    def summary(self) -> PackVersionSummary:
        return PackVersionSummary.model_validate(self.model_dump(exclude={"pack_id", "items"}))


# --- who reads which item ---------------------------------------------------------------------


def item_visible(handlings: Sequence[Handling], reader: Principal, scheme: HandlingScheme) -> bool:
    """The reader may view every handling the item rests on. A handling this scheme does not know
    (the scheme changed since the item was added) is not viewable: fail closed."""
    try:
        return all(principal_may_view(h, reader, scheme) for h in handlings)
    except HandlingSchemeError:
        return False


def marking_of(handlings: Sequence[Handling], scheme: HandlingScheme) -> str:
    """The highest classification the item rests on; an item resting on nothing (a trend that
    counted no event) is marked at the scheme's lowest."""
    return (
        highest([h.classification for h in handlings], scheme.classification)
        or (scheme.classification[0])
    )


async def readable(
    items: Sequence[StoredPackItem],
    reader: Principal,
    scheme: HandlingScheme,
    graph: GraphPort,
    case_id: str,
) -> tuple[list[StoredPackItem], int]:
    """The items this reader gets, in order, and how many were withheld from them."""
    shown: list[StoredPackItem] = []
    for item in items:
        if item_visible(item.handlings, reader, scheme) and await _still_visible(
            item, reader, graph, case_id
        ):
            shown.append(item)
    return shown, len(items) - len(shown)


async def _still_visible(
    item: StoredPackItem, reader: Principal, graph: GraphPort, case_id: str
) -> bool:
    if item.entity is not None:
        node_id = item.entity.node_id
        return await graph.get_node(node_id, reader) is not None or (
            await resolve_superseded_citation(graph, reader, node_id) is not None
        )
    if item.assessment is not None:
        a = item.assessment
        judgement = Judgement(
            id=a.judgement_id,
            investigation_id=case_id,
            statement=a.statement,
            probability_band=a.probability_band,
            supporting=a.supporting,
            contradicting=a.contradicting,
            author=a.author,
            created_at=a.created_at,
        )
        return await judgement_visible_to(judgement, reader, graph)
    return True


def highest_marking(items: Sequence[PackItem], scheme: HandlingScheme) -> str | None:
    return highest([i.marking for i in items], scheme.classification)


def reorder_visible(current: Sequence[str], visible: set[str], wanted: Sequence[str]) -> list[str]:
    """The reader's visible items put in `wanted`'s order, in the places the visible items held;
    every withheld item keeps its own place. `wanted` must name each visible item exactly once."""
    mine = [i for i in current if i in visible]
    if len(wanted) != len(set(wanted)) or set(wanted) != set(mine):
        raise ValueError("the new order must name each item you can see exactly once")
    order = iter(wanted)
    return [next(order) if i in visible else i for i in current]


# --- building an item, as its adder ---------------------------------------------------------


def _item(
    kind: PackItemKind,
    by: Principal,
    handlings: list[Handling],
    scheme: HandlingScheme,
    **content: Any,
) -> StoredPackItem:
    return StoredPackItem(
        id=new_id(),
        kind=kind,
        marking=marking_of(handlings, scheme),
        added_by=by.id,
        added_at=datetime.now(UTC),
        handlings=handlings,
        **content,
    )


def counted(handlings: Sequence[CountedHandling]) -> list[Handling]:
    return [Handling(**h.model_dump()) for h in handlings]


def trend_item(
    trend_id: str, figures: TrendFigures, by: Principal, scheme: HandlingScheme
) -> StoredPackItem:
    """A dated snapshot: the figures as the adder counted them, the definition, the time."""
    return _item(
        "trend", by, counted(figures.result.handlings), scheme, trend_id=trend_id, trend=figures
    )


async def assessment_item(
    judgement: Judgement, by: Principal, scheme: HandlingScheme, graph: GraphPort
) -> StoredPackItem | None:
    """The judgement as written now, resting on its supporting entities as the adder sees them;
    `None` if the adder cannot verify each of them (ADR-046's hide-in-full rule)."""
    if not await judgement_visible_to(judgement, by, graph):
        return None
    handlings: list[Handling] = []
    for ref in judgement.supporting:
        node = await graph.get_node(ref, by)
        if node is None:
            successor = await resolve_superseded_citation(graph, by, ref)
            node = await graph.get_node(successor, by) if successor else None
        if node is None:
            return None
        handlings.append(node.handling)
    snapshot = AssessmentSnapshot(
        judgement_id=judgement.id,
        statement=judgement.statement,
        probability_band=judgement.probability_band,
        supporting=list(judgement.supporting),
        contradicting=list(judgement.contradicting),
        author=judgement.author,
        created_at=judgement.created_at,
    )
    return _item("assessment", by, handlings, scheme, assessment=snapshot)


def entity_item(node: Node, caption: str, by: Principal, scheme: HandlingScheme) -> StoredPackItem:
    snapshot = EntitySnapshot(
        node_id=node.id, entity_type=node.type, name=node_name(node), caption=caption
    )
    return _item("entity", by, [node.handling], scheme, entity=snapshot)


def note_item(
    text: str,
    classification: str | None,
    handling_code: str | None,
    by: Principal,
    scheme: HandlingScheme,
) -> StoredPackItem:
    """A note is marked as its author says — never assumed, never above what they may view."""
    if not classification:
        raise PackItemRefused("a note needs its marking")
    if classification not in scheme.classification:
        raise PackItemRefused(f"{classification!r} is not a classification of this deployment")
    code = handling_code or next(
        c for c, d in scheme.handling_codes.items() if d.dissemination == "permitted"
    )
    handling = Handling(
        classification=classification,
        handling_code=code,
        owning_unit=by.org_unit,
        originator=by.org_unit,
    )
    if not item_visible([handling], by, scheme):
        raise PackItemRefused("a note cannot be marked above what its author may read")
    return _item("note", by, [handling], scheme, note=text)


# --- the store -----------------------------------------------------------------------------


_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS report_packs (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS report_packs_case ON report_packs (investigation_id);
CREATE TABLE IF NOT EXISTS report_pack_items (
    id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL REFERENCES report_packs (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    item JSONB NOT NULL,
    replaced_by TEXT,
    replaced_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS report_pack_items_pack ON report_pack_items (pack_id);
CREATE TABLE IF NOT EXISTS report_pack_versions (
    pack_id TEXT NOT NULL REFERENCES report_packs (id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    published_by TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    items JSONB NOT NULL,
    withdrawn_by TEXT,
    withdrawn_at TIMESTAMPTZ,
    withdrawal_reason TEXT,
    PRIMARY KEY (pack_id, version)
);
"""


def _stored(item: str | dict[str, object], **extra: object) -> StoredPackItem:
    data = json.loads(item) if isinstance(item, str) else item
    return StoredPackItem.model_validate({**data, **extra})


def _json(item: StoredPackItem) -> str:
    return item.model_dump_json(exclude={"replaced_at", "replaced_by"})


class PackStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PackStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    # --- packs

    async def create(self, case_id: str, title: str, by: Principal) -> ReportPack:
        now = datetime.now(UTC)
        pack = ReportPack(
            id=new_id(),
            investigation_id=case_id,
            title=title,
            created_by=by.id,
            created_at=now,
            updated_at=now,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO report_packs VALUES ($1, $2, $3, $4, $5, $5)",
                pack.id,
                case_id,
                title,
                by.id,
                now,
            )
        return pack

    async def _pack(self, row: asyncpg.Record) -> ReportPack:
        return ReportPack(
            id=row["id"],
            investigation_id=row["investigation_id"],
            title=row["title"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            versions=await self.versions(row["id"]),
        )

    async def list_for_case(self, case_id: str) -> list[ReportPack]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM report_packs WHERE investigation_id = $1 ORDER BY created_at",
                case_id,
            )
        return [await self._pack(r) for r in rows]

    async def get(self, case_id: str, pack_id: str) -> ReportPack | None:
        """Only within its own case: another case's pack is not found."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM report_packs WHERE id = $1 AND investigation_id = $2",
                pack_id,
                case_id,
            )
        return await self._pack(row) if row else None

    async def _touch(self, conn: asyncpg.Connection, pack_id: str) -> None:
        await conn.execute(
            "UPDATE report_packs SET updated_at = $2 WHERE id = $1", pack_id, datetime.now(UTC)
        )

    # --- the draft's items

    async def items(self, pack_id: str) -> list[StoredPackItem]:
        """The draft's current items, in order."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT item FROM report_pack_items WHERE pack_id = $1 AND replaced_by IS NULL "
                "ORDER BY position",
                pack_id,
            )
        return [_stored(r["item"]) for r in rows]

    async def add_item(self, pack_id: str, item: StoredPackItem) -> StoredPackItem:
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO report_pack_items (id, pack_id, position, item) VALUES ($1, $2, "
                "(SELECT COALESCE(MAX(position), 0) + 1 FROM report_pack_items WHERE pack_id = $2),"
                " $3)",
                item.id,
                pack_id,
                _json(item),
            )
            await self._touch(conn, pack_id)
        return item

    async def remove_item(self, pack_id: str, item_id: str) -> bool:
        """A current item only; an earlier snapshot stays in the history."""
        async with self._pool.acquire() as conn, conn.transaction():
            result = await conn.execute(
                "DELETE FROM report_pack_items WHERE id = $1 AND pack_id = $2 "
                "AND replaced_by IS NULL",
                item_id,
                pack_id,
            )
            await self._touch(conn, pack_id)
        return str(result).endswith(" 1")

    async def set_order(self, pack_id: str, item_ids: Sequence[str]) -> None:
        """`item_ids` is the whole draft in its new order (the route keeps withheld items'
        places)."""
        async with self._pool.acquire() as conn, conn.transaction():
            current = {
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM report_pack_items WHERE pack_id = $1 AND replaced_by IS NULL "
                    "FOR UPDATE",
                    pack_id,
                )
            }
            if set(item_ids) != current or len(item_ids) != len(current):
                raise PackItemRefused("the draft changed while it was being reordered")
            await conn.executemany(
                "UPDATE report_pack_items SET position = $2 WHERE id = $1",
                [(item_id, n) for n, item_id in enumerate(item_ids, start=1)],
            )
            await self._touch(conn, pack_id)

    async def replace_item(self, pack_id: str, old_id: str, new: StoredPackItem) -> bool:
        """A refresh: `new` takes the old item's place; the old one is kept, marked replaced."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            position = await conn.fetchval(
                "UPDATE report_pack_items SET replaced_by = $3, replaced_at = $4 "
                "WHERE id = $1 AND pack_id = $2 AND replaced_by IS NULL RETURNING position",
                old_id,
                pack_id,
                new.id,
                now,
            )
            if position is None:
                return False
            await conn.execute(
                "INSERT INTO report_pack_items (id, pack_id, position, item) "
                "VALUES ($1, $2, $3, $4)",
                new.id,
                pack_id,
                position,
                _json(new),
            )
            await self._touch(conn, pack_id)
        return True

    async def earlier_snapshots(self, pack_id: str) -> list[StoredPackItem]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT item, replaced_by, replaced_at FROM report_pack_items "
                "WHERE pack_id = $1 AND replaced_by IS NOT NULL ORDER BY replaced_at",
                pack_id,
            )
        return [
            _stored(r["item"], replaced_by=r["replaced_by"], replaced_at=r["replaced_at"])
            for r in rows
        ]

    # --- versions

    @staticmethod
    def _version(row: asyncpg.Record) -> PackVersion:
        return PackVersion(
            pack_id=row["pack_id"],
            version=row["version"],
            published_at=row["published_at"],
            published_by=row["published_by"],
            items=[_stored(i) for i in json.loads(row["items"])],
            withdrawn_at=row["withdrawn_at"],
            withdrawn_by=row["withdrawn_by"],
            withdrawal_reason=row["withdrawal_reason"],
        )

    async def publish(self, pack_id: str, by: Principal) -> PackVersion:
        """A new, immutable version: a copy of the draft's items now."""
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT id FROM report_packs WHERE id = $1 FOR UPDATE", pack_id)
            rows = await conn.fetch(
                "SELECT item FROM report_pack_items WHERE pack_id = $1 AND replaced_by IS NULL "
                "ORDER BY position",
                pack_id,
            )
            items = "[" + ",".join(r["item"] for r in rows) + "]"
            row = await conn.fetchrow(
                "INSERT INTO report_pack_versions (pack_id, version, published_by, published_at, "
                "items) VALUES ($1, (SELECT COALESCE(MAX(version), 0) + 1 FROM "
                "report_pack_versions WHERE pack_id = $1), $2, $3, $4) RETURNING *",
                pack_id,
                by.id,
                now,
                items,
            )
            await self._touch(conn, pack_id)
        assert row is not None
        return self._version(row)

    async def versions(self, pack_id: str) -> list[PackVersionSummary]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM report_pack_versions WHERE pack_id = $1 ORDER BY version", pack_id
            )
        return [self._version(r).summary() for r in rows]

    async def version(self, pack_id: str, version: int) -> PackVersion | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM report_pack_versions WHERE pack_id = $1 AND version = $2",
                pack_id,
                version,
            )
        return self._version(row) if row else None

    async def latest_published(self, pack_id: str) -> PackVersion | None:
        """The newest version not withdrawn: what *Reports → Published* shows."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM report_pack_versions WHERE pack_id = $1 AND withdrawn_at IS NULL "
                "ORDER BY version DESC LIMIT 1",
                pack_id,
            )
        return self._version(row) if row else None

    async def published_for_case(self, case_id: str) -> list[tuple[ReportPack, PackVersion]]:
        out = []
        for pack in await self.list_for_case(case_id):
            version = await self.latest_published(pack.id)
            if version is not None:
                out.append((pack, version))
        return out

    async def withdraw(self, pack_id: str, version: int, by: Principal, reason: str) -> bool:
        """Recorded once: who, when and why. The version itself is kept."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE report_pack_versions SET withdrawn_by = $3, withdrawn_at = $4, "
                "withdrawal_reason = $5 WHERE pack_id = $1 AND version = $2 "
                "AND withdrawn_at IS NULL",
                pack_id,
                version,
                by.id,
                datetime.now(UTC),
                reason,
            )
        return str(result).endswith(" 1")
