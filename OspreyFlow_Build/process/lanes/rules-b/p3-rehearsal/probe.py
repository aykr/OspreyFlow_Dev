"""rules-b P3: the leased stack's responsiveness while the basemap's tiles stage runs beside it. Every
10 s, one ArcadeDB SQL round trip and one Postgres `SELECT 1` on a fresh connection, each timed; a line
per sample (`t ms_arcadedb ms_postgres`), until the file named by its argument exists. Run from
OspreyFlow_Core with the lease's ports. Prints no password or port."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import asyncpg
from services.api.config import PostgresConfig

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig


async def main(stop: Path) -> int:
    client = ArcadeDBClient(ArcadeDBConfig.from_env("rulesb_p3_probe"))
    await client.create_database_if_absent()
    dsn = PostgresConfig.from_env().dsn
    started = time.monotonic()
    try:
        while not stop.exists():
            t0 = time.perf_counter()
            await client.sql("SELECT count(*) FROM schema:types")
            a = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            con = await asyncpg.connect(dsn)
            await con.fetchval("SELECT 1")
            await con.close()
            p = (time.perf_counter() - t0) * 1000
            print(f"{time.monotonic() - started:7.0f} {a:8.1f} {p:8.1f}", flush=True)
            await asyncio.sleep(10)
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(Path(sys.argv[1]))))
