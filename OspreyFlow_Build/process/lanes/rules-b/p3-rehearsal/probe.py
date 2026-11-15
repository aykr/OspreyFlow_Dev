"""rules-b P3: the leased stack's responsiveness while the basemap's tiles stage runs beside it. Every
5 s, one ArcadeDB SQL round trip and one Postgres `SELECT 1` on a fresh connection, each timed; a line
per sample (`t ms_arcadedb ms_postgres`), until the file named by its argument exists. The first
sample (the connection and the database's creation) is marked `warmup` and left out of the figures. Its
throwaway database is dropped at the end (the review's 9). Run from OspreyFlow_Core with the lease's
ports. Prints no password or port; errors go to stderr, never into the samples (the review's 3)."""

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
    first = True
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
            tag = "warmup" if first else "sample"
            first = False
            print(f"{tag} {time.monotonic() - started:7.0f} {a:8.1f} {p:8.1f}", flush=True)
            await asyncio.sleep(5)
    finally:
        try:
            await client.drop_database()
        finally:
            await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(Path(sys.argv[1]))))
