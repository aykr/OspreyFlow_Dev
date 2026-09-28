"""The audit stream — `spec/03_CONDUIT_MIDDLEWARE.md` §6: "Every read,
expansion, path query, pattern run, document view and export records
principal, timestamp, the resolved query, result cardinality, and — where
the action crosses a handling boundary — the justification the analyst
supplied." And `spec/00_ARCHITECTURE.md` §5: "an unaudited read in this
domain is worse than a refused one."

**Fail closed, deliberately the one place in the platform that does**
(`03_CONDUIT_MIDDLEWARE.md` §8: "The audit stream is unavailable. Reject
reads. This is the one case where the platform fails closed."). `record()`
never swallows a write failure — it raises `AuditWriteError`, and every
caller in `app.py` writes the audit row *before* returning a result to the
client, for a read and a mutation alike, so a failed audit write means
nothing reaches the analyst, not that a partial or unaudited result slips
through.

**Append-only in intent, not yet in database-enforced grant.** The table
this bootstraps has no `UPDATE`/`DELETE` grant applied by this module —
that is a deployment-time Postgres role/grant concern
(`05_DEPLOYMENT.md`'s harness territory, not a `CREATE TABLE` statement
running from application code), named here so it is not mistaken for an
oversight: nothing in `services/api` ever issues an `UPDATE` or `DELETE`
against this table, but the database itself does not yet refuse one from
a different role.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from schemas.domain import Principal

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL,
    principal_id TEXT NOT NULL,
    action TEXT NOT NULL,
    investigation_id TEXT,
    resolved_query JSONB NOT NULL,
    result_cardinality INTEGER NOT NULL,
    justification TEXT
);
CREATE INDEX IF NOT EXISTS audit_log_investigation_id_idx
    ON audit_log (investigation_id);
CREATE INDEX IF NOT EXISTS audit_log_principal_id_idx
    ON audit_log (principal_id);
"""


class AuditWriteError(Exception):
    """Wraps the underlying `asyncpg` failure. `app.py` maps this to a
    distinct HTTP status from an ordinary 500, so "the audit stream is
    down" is visible in the response as the specific, named failure mode
    `03_CONDUIT_MIDDLEWARE.md` §8 calls out, not generic server trouble."""


class AuditWriter:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> AuditWriter:
        # `min_size`/`max_size` — `hotlists.py::HotlistStore.connect`'s own comment has the full
        # Stage 6c connection-ceiling reasoning. Sized larger than the control-plane stores: every
        # route audits, so this is this deployment's own busiest store, not a low-traffic one.
        pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def record(
        self,
        *,
        principal: Principal,
        action: str,
        resolved_query: dict[str, Any],
        result_cardinality: int,
        investigation_id: str | None = None,
        justification: str | None = None,
    ) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO audit_log "
                    "(recorded_at, principal_id, action, investigation_id, "
                    " resolved_query, result_cardinality, justification) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    datetime.now(UTC),
                    principal.id,
                    action,
                    investigation_id,
                    json.dumps(resolved_query),
                    result_cardinality,
                    justification,
                )
        except (OSError, asyncpg.PostgresError) as exc:
            raise AuditWriteError(f"audit write failed for action {action!r}: {exc}") from exc
