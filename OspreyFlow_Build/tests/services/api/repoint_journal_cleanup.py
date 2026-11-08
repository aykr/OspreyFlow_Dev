"""Teardown for any test that writes repoint journal records (`AlertStore.repointing`, ADR-109
Amendment 10) into the shared test database: the records it made are removed when it ends, failed or
not, so no other file meets them (twice, leftovers in shared tables turned other files red). Rows
made while the test ran are its own: only the lane holding the lease runs against the stack, one
test at a time.

Since the removal hides what a test left, a run that sets `REPOINT_RECORDS_LEFT` to a file path has
each test's leftovers counted first, before they are removed, one line per test that left any:
its id, then how many records it left unapplied, applied (waiting for a purge) and held open. That
count, not a count of the table after the run, is what says whether the journal leaves records."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig


def _append(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as out:
        out.write(line)


@pytest.fixture(autouse=True)
async def remove_repoint_records(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    started = datetime.now(UTC)
    try:
        yield
    finally:
        try:
            conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
        except OSError:
            return  # no store reached: a test that never wrote one
        try:
            try:
                left = await conn.fetchrow(
                    "SELECT count(*) FILTER (WHERE NOT applied) AS unapplied, "
                    "count(*) FILTER (WHERE applied) AS applied, "
                    "count(*) FILTER (WHERE held_open) AS held_open "
                    "FROM alert_repoint_records WHERE recorded_at >= $1",
                    started,
                )
                log = os.environ.get("REPOINT_RECORDS_LEFT")
                if log and left is not None and any(left.values()):
                    _append(
                        log,
                        f"{request.node.nodeid} unapplied={left['unapplied']} "
                        f"applied={left['applied']} held_open={left['held_open']}\n",
                    )
                await conn.execute(
                    "DELETE FROM alert_repoint_records WHERE recorded_at >= $1", started
                )
            except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
                pass
        finally:
            await conn.close()
