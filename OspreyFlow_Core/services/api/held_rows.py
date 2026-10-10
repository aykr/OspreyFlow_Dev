"""`HeldRowStore` — the quarantine a failing pre-commit rule holds rows in (`06_DECISIONS.md`
ADR-109 ruling 1: a pre-commit rule that errors or overruns its budget fails closed). A held row
never reached the graph; it waits here, as read, with its original row number, until a reviewer
releases it (it is loaded then, provenance unchanged) or rejects it.

**Access control in the query (rule 3).** A held row is source content at the marking its recipe
would have given it, so every read filters on that marking in the `WHERE` clause — the same two
axes the adapters' `AccessFilter` compiles (classification within clearance; a restricted handling
code only to a principal who may receive it from their own unit) — and on the case. A row the
reader may not see is neither listed nor counted, and a decision on one is refused as not found.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import asyncpg

from ontology.handling import HandlingScheme
from schemas.domain import Handling, HeldRow, HeldRowStatus, Principal

from .dataset_scope import reach_clause

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS held_rows (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    recipe_id TEXT NOT NULL,
    recipe_version INTEGER NOT NULL,
    load_id TEXT NOT NULL,
    source TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    row_content JSONB NOT NULL,
    rule_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    handling JSONB NOT NULL,
    handling_classification TEXT NOT NULL,
    handling_code TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    originator TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'held',
    held_at TIMESTAMPTZ NOT NULL,
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    decision_reason TEXT,
    dataset_id TEXT
);
CREATE INDEX IF NOT EXISTS held_rows_investigation_idx ON held_rows (investigation_id, status);
"""

_COLUMNS = (
    "id, investigation_id, recipe_id, recipe_version, load_id, source, row_index, row_content, "
    "rule_id, reason, handling, status, held_at, decided_by, decided_at, decision_reason, "
    "dataset_id"
)


class HeldRowNotFoundError(Exception):
    """No such held row in this case that the reader may see — or it was already decided."""


def handling_sql(
    scheme: HandlingScheme, principal: Principal, position: int
) -> tuple[str, list[object]]:
    """`AND (...)` keeping a read to markings `principal` may read, parameters from `$position` —
    `adapters/analytics_duckdb/access_filter.py`'s predicate, for Postgres. An unknown clearance
    reads nothing; a restricted code needs receiving and the reader's unit as owner or originator.
    Returns three bound values; the caller passes `principal.org_unit` as the fourth, at the call
    itself, so the principal is seen in the query (ADR-041's gate)."""
    order = scheme.classification
    allowed = (
        order[: order.index(principal.clearance) + 1] if principal.clearance in order else []
    )
    restricted = sorted(
        c for c, d in scheme.handling_codes.items() if d.dissemination == "restricted"
    )
    receivable = [c for c in principal.receivable_handling_codes if c in restricted]
    p = position
    clause = (
        f" AND handling_classification = ANY(${p}::text[])"
        f" AND (NOT (handling_code = ANY(${p + 1}::text[]))"
        f" OR (handling_code = ANY(${p + 2}::text[])"
        f" AND (owning_unit = ${p + 3} OR originator = ${p + 3})))"
    )
    return clause, [allowed, restricted, receivable]


def _row_to_held(row: asyncpg.Record) -> HeldRow:
    def _json(value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value

    return HeldRow(
        id=row["id"],
        investigation_id=row["investigation_id"],
        recipe_id=row["recipe_id"],
        recipe_version=row["recipe_version"],
        load_id=row["load_id"],
        source=row["source"],
        row_index=row["row_index"],
        row=_json(row["row_content"]),  # type: ignore[arg-type]
        rule_id=row["rule_id"],
        reason=row["reason"],
        handling=Handling.model_validate(_json(row["handling"])),
        status=row["status"],
        held_at=row["held_at"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        decision_reason=row["decision_reason"],
        dataset_id=row["dataset_id"],
    )


class HeldRowStore:
    def __init__(self, pool: asyncpg.Pool, scheme: HandlingScheme) -> None:
        self._pool = pool
        self._scheme = scheme

    @classmethod
    async def connect(cls, dsn: str, scheme: HandlingScheme) -> HeldRowStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool, scheme)

    async def close(self) -> None:
        await self._pool.close()

    async def hold(self, rows: Sequence[HeldRow]) -> None:
        async with self._pool.acquire() as conn:
            await conn.executemany(
                f"INSERT INTO held_rows ({_COLUMNS}, handling_classification, handling_code, "
                "owning_unit, originator) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, "
                "$12, $13, $14, $15, $16, $17, $18, $19, $20, $21)",
                [
                    (
                        r.id,
                        r.investigation_id,
                        r.recipe_id,
                        r.recipe_version,
                        r.load_id,
                        r.source,
                        r.row_index,
                        json.dumps(r.row),
                        r.rule_id,
                        r.reason,
                        r.handling.model_dump_json(),
                        r.status,
                        r.held_at,
                        r.decided_by,
                        r.decided_at,
                        r.decision_reason,
                        r.dataset_id,
                        r.handling.classification,
                        r.handling.handling_code,
                        r.handling.owning_unit,
                        r.handling.originator,
                    )
                    for r in rows
                ],
            )

    async def list_authorized(
        self, investigation_id: str, principal: Principal, *, status: HeldRowStatus = "held"
    ) -> list[HeldRow]:
        marking, marking_params = handling_sql(self._scheme, principal, 3)
        reach, extra = reach_clause(principal, 7)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM held_rows WHERE investigation_id = $1 AND status = $2"
                f"{marking}{reach} ORDER BY held_at, row_index",
                investigation_id,
                status,
                *marking_params,
                principal.org_unit,
                *extra,
            )
        return [_row_to_held(r) for r in rows]

    async def get_authorized(
        self, held_id: str, investigation_id: str, principal: Principal
    ) -> HeldRow:
        marking, marking_params = handling_sql(self._scheme, principal, 3)
        reach, extra = reach_clause(principal, 7)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM held_rows WHERE id = $1 AND investigation_id = $2"
                f"{marking}{reach}",
                held_id,
                investigation_id,
                *marking_params,
                principal.org_unit,
                *extra,
            )
        if row is None:
            raise HeldRowNotFoundError(held_id)
        return _row_to_held(row)

    async def decide_for_reader(
        self,
        held_ids: Sequence[str],
        investigation_id: str,
        principal: Principal,
        *,
        status: HeldRowStatus,
        reason: str | None,
    ) -> list[HeldRow]:
        """Releases or rejects exactly these held rows, each still held and readable by the
        reviewer; any other id is refused whole (nothing decided), so a decision is never partial
        without saying so."""
        marking, marking_params = handling_sql(self._scheme, principal, 7)
        reach, extra = reach_clause(principal, 11)
        async with self._pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                "UPDATE held_rows SET status = $3, decided_by = $4, decided_at = $5, "
                f"decision_reason = $6 WHERE id = ANY($1::text[]) AND investigation_id = $2 "
                f"AND status = 'held'{marking}{reach} RETURNING {_COLUMNS}",
                list(held_ids),
                investigation_id,
                status,
                principal.id,
                datetime.now(UTC),
                reason,
                *marking_params,
                principal.org_unit,
                *extra,
            )
            if len(rows) != len(set(held_ids)):
                raise HeldRowNotFoundError(
                    ", ".join(sorted(set(held_ids) - {r["id"] for r in rows}))
                )
        return [_row_to_held(r) for r in rows]


__all__ = ["HeldRowNotFoundError", "HeldRowStore", "handling_sql"]
