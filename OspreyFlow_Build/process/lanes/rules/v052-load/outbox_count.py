"""Prints the search index's two outboxes' sizes, `graph <n> text <n>` (ADR-150 decisions 1 and 3):
`IndexPending` in the graph and `search_text_pending` in Postgres. Read-only. Run from OspreyFlow_Core
under the lease (`stack_lease.sh remote`), by `drain_index.sh`."""

from __future__ import annotations

import asyncio
import sys

sys.path[:0] = [".", "packages"]

import asyncpg  # noqa: E402

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402
from services.api.config import PostgresConfig  # noqa: E402


async def main() -> None:
    graph = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    rows = await graph.sql("SELECT count(*) AS n FROM IndexPending")
    await graph.aclose()
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    text = await conn.fetchval("SELECT count(*) FROM search_text_pending")
    await conn.close()
    print(f"graph {int(rows[0]['n'])} text {int(text)}")


if __name__ == "__main__":
    asyncio.run(main())
