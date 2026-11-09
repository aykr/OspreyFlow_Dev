"""What a person owns that the case lane keeps, as Admin's *Disable…* reads it (`06_DECISIONS.md`
ADR-145 decision 6 and A4; L3.8, the case-b lane's ownership route; the admin lane's L2.5b reads it
through `admin_people.l38_owned_items`).

**The kinds.** Views and boards they made (ADR-144 decision 3: only a view's creator shares or
deletes it, so each needs a new creator), link-type proposals they made that wait for a decision
(ADR-090; ADR-143 decision 9), and the watches on items they drew that have not ended (ADR-143
Amendment 2 decision 8). Promotions they proposed and reviews waiting on them are L3.4's store, not
on main when this was built: `PROMOTION_KINDS` names them in `not_yet_listed`, and
`promotion_items` is the seam the case lane wires.

**Read in the query, never after it** (rules 3 and 4). Every statement names the administrator's
unit, through the item's case (a removed case's items are left out with it), and an item on a
dataset reads that dataset's highest allowed marking, or the deployment's highest where none is set
or there is no dataset at all (the strict side, as the Model tab's proposal words are read,
`app._reads_proposal_words`). An item the administrator does not clear is not retrieved, named or
counted. One more statement asks only whether any such item exists (`withheld`): said, never how
many, of which kind or where, as ADR-145 Amendment 5 decision 8 says another unit's cases, rules and
schedules, so that *Transfer and disable* is refused while someone else still has items to transfer
(A4: each item needs a *Transfer to…*). A view or a board is a lens on its case and holds no data
(ADR-144), so it is read at its case's unit alone, as Admin › People shows the case; a proposal and
a watch are tied to a dataset and read at its marking too.

**Words only** (rule 7): each item is placed by its case's name, which People shows. A view's,
a board's or a proposed type's name is the analyst's own writing and is never read here.
"""

from __future__ import annotations

from collections import Counter
from typing import cast

import asyncpg

from ontology.handling import HandlingScheme
from schemas.domain import Principal
from schemas.person_ownership import OwnershipItem, OwnershipKind, PersonOwnership

#: The seam for L3.4's promotion store: the kinds said in `not_yet_listed` until it is on main.
PROMOTION_KINDS: tuple[str, ...] = ("promotions waiting for review", "reviews waiting on them")

_CASE = "JOIN investigations i ON i.id = {col} AND i.removed_at IS NULL AND i.owning_unit = $2"
#: The marking an item on a dataset is read at; `$4` is the deployment's highest.
_CLEARED = "COALESCE(d.highest_marking, $4) = ANY($3::text[])"

_VIEWS_SQL = f"""
SELECT v.id, v.case_id, v.shared, v.drawing, i.name AS case_name
FROM case_views v {_CASE.format(col="v.case_id")}
WHERE v.created_by = $1
ORDER BY i.name, v.case_id, v.drawing, v.created_at, v.id
"""

_PROPOSALS_SQL = f"""
SELECT p.id, p.investigation_id AS case_id, i.name AS case_name
FROM link_type_proposals p {_CASE.format(col="p.investigation_id")}
LEFT JOIN datasets d ON d.id = p.dataset_id
WHERE p.proposed_by = $1 AND p.status = 'pending' AND p.owning_unit = $2 AND {_CLEARED}
ORDER BY i.name, p.investigation_id, p.proposed_at, p.id
"""

_WATCHES_SQL = f"""
SELECT w.id, w.case_id, i.name AS case_name
FROM drawn_watches w {_CASE.format(col="w.case_id")}
LEFT JOIN datasets d ON d.id = w.dataset_id
WHERE w.owner = $1 AND w.ended_at IS NULL AND {_CLEARED}
ORDER BY i.name, w.case_id, w.created_at, w.id
"""


#: Whether the person owns anything of these kinds the reads above leave out: the same tables, the
#: same open items, with the administrator's unit and markings negated. Answers one boolean.
_WITHHELD_SQL = f"""
SELECT EXISTS (
    SELECT 1 FROM case_views v
    JOIN investigations i ON i.id = v.case_id AND i.removed_at IS NULL
    WHERE v.created_by = $1 AND i.owning_unit IS DISTINCT FROM $2
) OR EXISTS (
    SELECT 1 FROM link_type_proposals p
    JOIN investigations i ON i.id = p.investigation_id AND i.removed_at IS NULL
    LEFT JOIN datasets d ON d.id = p.dataset_id
    WHERE p.proposed_by = $1 AND p.status = 'pending'
      AND NOT COALESCE(p.owning_unit = $2 AND i.owning_unit = $2 AND {_CLEARED}, FALSE)
) OR EXISTS (
    SELECT 1 FROM drawn_watches w
    JOIN investigations i ON i.id = w.case_id AND i.removed_at IS NULL
    LEFT JOIN datasets d ON d.id = w.dataset_id
    WHERE w.owner = $1 AND w.ended_at IS NULL
      AND NOT COALESCE(i.owning_unit = $2 AND {_CLEARED}, FALSE)
)
"""


async def withheld(
    conn: asyncpg.Connection, person: str, *, admin_unit: str | None, cleared: list[str], top: str
) -> bool:
    """Whether the person owns items of these kinds the administrator may not see: never which."""
    return bool(await conn.fetchval(_WITHHELD_SQL, person, admin_unit, cleared, top))


def cleared_markings(admin: Principal, scheme: HandlingScheme) -> list[str]:
    """The markings the administrator clears; none for a clearance the scheme does not know."""
    return [m for m in scheme.classification if scheme.clears(admin.clearance, m)]


async def promotion_items(
    conn: asyncpg.Connection, person: str, *, admin_unit: str | None, cleared: list[str], top: str
) -> list[OwnershipItem]:
    """The seam for L3.4's promotion store, wired by the case lane once it is on main: promotions
    the person proposed that wait for review, and reviews waiting on them. None until then."""
    del conn, person, admin_unit, cleared, top
    return []


def _case(row: asyncpg.Record) -> str:
    return str(row["case_name"] or row["case_id"])


async def owned_items(
    conn: asyncpg.Connection, person: str, *, admin_unit: str | None, cleared: list[str], top: str
) -> list[OwnershipItem]:
    """Everything of these kinds the person owns in the administrator's unit, within the markings
    they clear (`cleared`; `top`, the deployment's highest). Takes a connection, so *Transfer and
    disable* can read it again inside its own transaction."""
    items: list[OwnershipItem] = []
    for row in await conn.fetch(_VIEWS_SQL, person, admin_unit):
        what = "board" if row["drawing"] else "view"
        reach = "shared" if row["shared"] else "private"
        items.append(
            OwnershipItem(
                kind=cast("OwnershipKind", what),
                id=row["id"],
                investigation_id=row["case_id"],
                label=f"A {reach} {what} of the case {_case(row)}",
            )
        )
    for row in await conn.fetch(_PROPOSALS_SQL, person, admin_unit, cleared, top):
        items.append(
            OwnershipItem(
                kind="link_type_proposal",
                id=row["id"],
                investigation_id=row["case_id"],
                label=f"A proposed link type in the case {_case(row)}, waiting for a decision",
            )
        )
    for row in await conn.fetch(_WATCHES_SQL, person, admin_unit, cleared, top):
        items.append(
            OwnershipItem(
                kind="drawn_watch",
                id=row["id"],
                investigation_id=row["case_id"],
                label=f"A watch on an item they drew in the case {_case(row)}",
            )
        )
    items.extend(
        await promotion_items(conn, person, admin_unit=admin_unit, cleared=cleared, top=top)
    )
    return items


def ownership_of(
    person: str, items: list[OwnershipItem], *, withheld: bool = False
) -> PersonOwnership:
    counts = Counter(i.kind for i in items)
    return PersonOwnership(
        person=person,
        items=items,
        counts=dict(counts),
        withheld=withheld,
        not_yet_listed=list(PROMOTION_KINDS),
    )


class PostgresOwnershipStore:
    """Reads only: it owns none of the tables it reads (the case views', the boards', the link
    types' and the datasets' stores make them)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresOwnershipStore:
        return cls(await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2))

    async def close(self) -> None:
        await self._pool.close()

    async def owned_by(
        self, person: str, *, admin: Principal, scheme: HandlingScheme
    ) -> PersonOwnership:
        unit, top = admin.org_unit, scheme.classification[-1]
        cleared = cleared_markings(admin, scheme)
        async with (
            self._pool.acquire() as conn,
            conn.transaction(isolation="repeatable_read", readonly=True),
        ):
            items = await owned_items(conn, person, admin_unit=unit, cleared=cleared, top=top)
            hidden = await withheld(conn, person, admin_unit=unit, cleared=cleared, top=top)
        return ownership_of(person, items, withheld=hidden)


__all__ = [
    "PROMOTION_KINDS",
    "PostgresOwnershipStore",
    "cleared_markings",
    "owned_items",
    "ownership_of",
    "promotion_items",
    "withheld",
]
