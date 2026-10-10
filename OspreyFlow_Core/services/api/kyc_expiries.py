"""Verifying documents' expiries, for the daily sweep (`06_DECISIONS.md` ADR-109 phase F, ruling
7). A document lapsing is the clock passing, not a write, so the change stream never sees it: each
load records the expiry of every verifying document it writes, and the sweep asks this store which
lapsed since it last ran — a bounded read by date, not a walk of every Document in the graph.
Recorded per case; what the documents and customers are is read from the graph again at the sweep,
as each rule's deployer, never trusted from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import asyncpg

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS kyc_expiries (
    investigation_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    expires_on DATE NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (investigation_id, document_id, customer_id)
);
CREATE INDEX IF NOT EXISTS kyc_expiries_on_idx ON kyc_expiries (expires_on);
"""


@dataclass(frozen=True)
class Lapse:
    investigation_id: str
    document_id: str
    customer_id: str
    expires_on: date


class KycExpiryStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> KycExpiryStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def record(self, investigation_id: str, pairs: Sequence[tuple[str, str, str]]) -> int:
        """`(document_id, customer_id, expires_on)` each; a later load's expiry replaces an
        earlier one for the same document and customer."""
        if not pairs:
            return 0
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO kyc_expiries (investigation_id, document_id, customer_id, expires_on, "
                "recorded_at) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (investigation_id, "
                "document_id, customer_id) DO UPDATE SET expires_on = EXCLUDED.expires_on, "
                "recorded_at = EXCLUDED.recorded_at",
                [(investigation_id, d, c, date.fromisoformat(e), now) for d, c, e in pairs],
            )
        return len(pairs)

    async def lapsed(self, *, after: date | None, before: date) -> list[Lapse]:
        """Documents whose expiry fell in `[after, before)` — expired by `before`, and not already
        swept (`after` is the day the last sweep ran, `None` for the first)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT investigation_id, document_id, customer_id, expires_on FROM kyc_expiries "
                "WHERE expires_on < $1 AND ($2::date IS NULL OR expires_on >= $2) "
                "ORDER BY investigation_id, expires_on, document_id",
                before,
                after,
            )
        return [
            Lapse(r["investigation_id"], r["document_id"], r["customer_id"], r["expires_on"])
            for r in rows
        ]


__all__ = ["KycExpiryStore", "Lapse"]
