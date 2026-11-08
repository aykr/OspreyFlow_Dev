"""Teardown for any test that writes repoint journal records (`AlertStore.repointing`, ADR-109
Amendment 10) into the shared test database: the records and successors it made are removed when it
ends, failed or not, so no other file meets them (twice, leftovers in shared tables turned other
files red). Rows made while the test ran are its own: only the lane holding the lease runs against
the stack, one test at a time."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from services.api.config import PostgresConfig


@pytest.fixture(autouse=True)
async def remove_repoint_records() -> AsyncIterator[None]:
    started = datetime.now(UTC)
    try:
        yield
    finally:
        try:
            conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
        except OSError:
            return  # no store reached: a test that never wrote one
        try:
            for table in ("alert_repoint_records",):
                try:
                    await conn.execute(f"DELETE FROM {table} WHERE recorded_at >= $1", started)
                except asyncpg.UndefinedTableError:
                    pass
        finally:
            await conn.close()
