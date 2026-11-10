"""Removes what T1 part 4's live proof may have left on a leased stack's shared names, by its own names only.

Its first red run on stack b (10 November 2026, the lease admin took at 17:45:01Z) stopped clearing after an ArcadeDB
error. One worker's Postgres table, Valkey member and object may have stayed under the `t1probe` names. Run from
OspreyFlow_Core under the lease, by `t1p4_run.sh clean`. It prints what it removed and touches nothing else:
- ArcadeDB types `T1Probe_*` in `ospreyflow`;
- Postgres tables `t1probe_*` in `POSTGRES_DB`;
- Valkey keys `t1probe:*` in db 0;
- objects under `ospreyflow-staging/t1probe-*`.
"""

from __future__ import annotations

import asyncio
import re

PROBE = re.compile(r"^(T1Probe_|t1probe_|t1probe:|t1probe-)[0-9a-f]{8}$")


async def _arcadedb() -> list[str]:
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig

    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    try:
        if "ospreyflow" not in await client.list_databases():
            return []
        kinds = [r["name"] for r in await client.sql("SELECT name FROM schema:types") if PROBE.match(r["name"])]
        for kind in kinds:
            await client.sql(f"DROP TYPE {kind} IF EXISTS UNSAFE")
        return kinds
    finally:
        await client.aclose()


async def _postgres() -> list[str]:
    import asyncpg
    from services.api.config import PostgresConfig

    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = [r["tablename"] for r in rows if PROBE.match(r["tablename"])]
        for table in tables:
            await conn.execute(f'DROP TABLE "{table}"')
        return tables
    finally:
        await conn.close()


def _valkey() -> list[str]:
    import valkey
    from services.api.config import ValkeyConfig

    client = valkey.Valkey(**{**ValkeyConfig.from_env().client_kwargs(), "db": 0})
    try:
        keys = [k.decode() for k in client.scan_iter(match="t1probe:*") if PROBE.match(k.decode())]
        if keys:
            client.delete(*keys)
        return keys
    finally:
        client.close()  # type: ignore[no-untyped-call]


def _objects() -> list[str]:
    from pyarrow import fs as pa_fs
    from services.ingest.staging import ObjectStorageConfig, filesystem

    config = ObjectStorageConfig.named("MINIO_BUCKET", "staging")
    s3 = filesystem(config)
    if s3.get_file_info(config.bucket).type == pa_fs.FileType.NotFound:
        return []
    folders = [i.path for i in s3.get_file_info(pa_fs.FileSelector(config.bucket)) if PROBE.match(i.base_name)]
    for folder in folders:
        s3.delete_dir(folder)
    return folders


def main() -> None:
    removed = {
        "arcadedb": asyncio.run(_arcadedb()),
        "postgres": asyncio.run(_postgres()),
        "valkey": _valkey(),
        "objects": _objects(),
    }
    print(f"t1p4 clean: removed {removed}")


if __name__ == "__main__":
    main()
