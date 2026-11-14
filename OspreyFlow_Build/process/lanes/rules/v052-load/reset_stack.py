"""Empties the leased lane stack after the calibration (DESIGN.md "Wall time"), so the real load
starts from nothing: the graph database dropped and made again, every table of the stack's
Postgres and ClickHouse databases dropped (each store's code makes its own again on next use), and
every index in its OpenSearch deleted. Only a throwaway lane stack: it refuses unless OSPREY_LANE is
set and the ports are a lane stack's (the port guard's table). Run from OspreyFlow_Core through
`stack_lease.sh remote rules -- .venv/bin/python ../OspreyFlow_Build/process/lanes/rules/v052-load/reset_stack.py`."""

from __future__ import annotations

import asyncio
import os
import sys
import urllib.request

sys.path[:0] = [".", "packages", "../OspreyFlow_Build"]

import asyncpg  # noqa: E402

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402
from services.api.config import PostgresConfig  # noqa: E402
from tests.port_guard import stack_ports  # noqa: E402


def _refuse_unless_a_lane_stack() -> None:
    lane_ports = stack_ports()
    port = int(os.environ.get("ARCADEDB_HTTP_PORT", "0"))
    if not os.environ.get("OSPREY_LANE") or port not in lane_ports or lane_ports[port][0] == "a":
        sys.exit("refused: this resets only a leased server lane stack (b to g), under its lease")


async def main() -> None:
    _refuse_unless_a_lane_stack()
    graph = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    if "ospreyflow" in await graph.list_databases():
        await graph.drop_database()
    await graph.create_database_if_absent()
    await graph.aclose()
    print("graph: ospreyflow dropped and made again")
    conn = await asyncpg.connect(PostgresConfig.from_env().dsn)
    await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await conn.close()
    print("postgres: the public schema dropped and made again")
    ch = f"http://localhost:{os.environ['CLICKHOUSE_HTTP_PORT']}/"
    auth = {"X-ClickHouse-User": os.environ["CLICKHOUSE_USER"], "X-ClickHouse-Key": os.environ["CLICKHOUSE_PASSWORD"]}
    def ask(sql: str) -> str:
        req = urllib.request.Request(ch, data=sql.encode(), headers=auth)
        return urllib.request.urlopen(req, timeout=60).read().decode()
    for table in ask("SELECT name FROM system.tables WHERE database = currentDatabase()").split():
        ask(f"DROP TABLE IF EXISTS `{table}`")
    print("clickhouse: every table dropped")
    os_url = f"http://localhost:{os.environ['OPENSEARCH_PORT']}"
    req = urllib.request.Request(f"{os_url}/_all", method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as exc:  # noqa: BLE001 - an empty cluster answers 404 on some versions
        print(f"opensearch: {exc}")
    print("opensearch: every index deleted")


if __name__ == "__main__":
    asyncio.run(main())
