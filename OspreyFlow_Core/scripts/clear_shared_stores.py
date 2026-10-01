"""Clears the shared stores after the PaySim vault is verified (ADR-056 Amendment 16, stage 0b).

    python -m scripts.seed_internal paysim --clear-shared-stores --vault paysim --stop-api
    python -m scripts.seed_internal paysim --clear-shared-stores --vault paysim --stop-api \
        --confirm <vertices>:<edges>:<events>

The owner's ruling (Amendment 1): once the vault is verified, drop the shared graph database and the
shared analytics events and create them clean. Case records (the Conduit's Postgres) are not
touched. This deletes data that can only be got back by reloading, so it is built to be hard to
run by accident:

1. It refuses unless the vault is verified: accounts and transactions in its graph, no id stored
   more than once (a stray copy must be repaired first, or the clean copy is not clean), and events
   in its analytics file.
2. Without `--confirm` it only reports exactly what it would delete, and the confirmation to pass.
3. It deletes only when `--confirm` equals those counts as they are now, so the owner has seen
   them and nothing changed in between.
4. It then checks both stores are empty and says so, or fails.

It never targets a vault's own database, whatever the environment says.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import duckdb
from scripts.seed_support import (
    _count,
    ids_stored_twice,
    reset_graph_database,
    vault_locations,
)

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology


class SharedGraph(Protocol):
    async def counts(self) -> tuple[int, int]: ...

    async def reset(self) -> None: ...


class SharedEvents(Protocol):
    def count(self) -> int: ...

    def clear(self) -> None: ...


def check_shared_database(name: str) -> None:
    """The graph database this clears must be the shared one, never a vault's."""
    if name.startswith("vault_"):
        raise ValueError(
            f"{name!r} is a vault's database; this only ever clears the shared one "
            "(check ARCADEDB_DATABASE)"
        )


async def clear_shared(
    graph: SharedGraph,
    events: SharedEvents,
    *,
    vault_problems: list[str],
    confirm: str | None,
    say: Callable[[str], None] = print,
) -> int:
    """0 on success or a dry run; 2 the vault is not verified; 3 the confirmation does not match;
    4 a store is not empty afterwards."""
    if vault_problems:
        say("  clear: refused, the vault is not verified:")
        for problem in vault_problems:
            say(f"    - {problem}")
        say("  clear: nothing was changed")
        return 2
    vertices, edges = await graph.counts()
    n_events = events.count()
    token = f"{vertices}:{edges}:{n_events}"
    say(
        f"  clear: the shared stores hold {vertices:,} vertices, {edges:,} edges and "
        f"{n_events:,} events"
    )
    if confirm is None:
        say(f"  clear: dry run, nothing was changed. To delete exactly this, add --confirm {token}")
        return 0
    if confirm != token:
        say(
            f"  clear: --confirm {confirm} does not match what the stores hold now ({token}); "
            "nothing was changed"
        )
        return 3
    await graph.reset()
    events.clear()
    left = (*await graph.counts(), events.count())
    if left != (0, 0, 0):
        say(
            f"  clear: !! not empty afterwards: {left[0]} vertices, {left[1]} edges, "
            f"{left[2]} events"
        )
        return 4
    say("  clear: cleared. The shared graph database and events are empty; case records stay")
    return 0


async def vault_problems(
    client: Any,
    *,
    node_type: str,
    edge_type: str,
    events: SharedEvents,
    node_prefix: str = "paysim-acct-",
    edge_prefix: str = "paysim-tx-",
) -> list[str]:
    """Why the vault is not yet fit to replace the shared stores, one line each; empty if it is."""
    problems: list[str] = []
    if await _count(client, node_type, node_prefix) == 0:
        problems.append("the vault's graph has no accounts")
    if await _count(client, edge_type, edge_prefix) == 0:
        problems.append("the vault's graph has no transactions")
    twice = await ids_stored_twice(client, edge_type=edge_type, prefix=edge_prefix)
    if twice:
        problems.append(
            f"{len(twice)} transaction id(s) are stored more than once; run the repair first "
            "(seed_internal paysim --repair-strays --apply)"
        )
    if events.count() == 0:
        problems.append("the vault's analytics file has no events")
    return problems


class DuckEvents:
    """The events table of one analytics file. Counting opens it read-only and never creates it."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def count(self) -> int:
        if not self._path.exists():
            return 0
        con = duckdb.connect(str(self._path), read_only=True)
        try:
            return int(con.execute("SELECT count(*) FROM events").fetchone()[0])  # type: ignore[index]
        except duckdb.CatalogException:
            return 0
        finally:
            con.close()

    def clear(self) -> None:
        if not self._path.exists():
            return
        con = duckdb.connect(str(self._path))
        try:
            con.execute("DELETE FROM events")
        except duckdb.CatalogException:
            pass
        finally:
            con.close()


class ArcadeShared:
    """The shared graph database: counted with SELECT, cleared by dropping it and creating it again
    with the schema, so the Conduit finds it as a fresh install would."""

    def __init__(self, client: ArcadeDBClient, database: str) -> None:
        self._client = client
        self._database = database

    async def counts(self) -> tuple[int, int]:
        async def n(kind: str) -> int:
            rows = await self._client.sql(f"SELECT count(*) AS n FROM {kind}")
            return int(rows[0]["n"]) if rows else 0

        return await n("V"), await n("E")

    async def reset(self) -> None:
        await reset_graph_database(self._client, database=self._database)
        graph = GraphArcadeDBAdapter(self._client, load_uk_le_scheme())
        await graph.apply_schema(load_default_ontology())


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.clear_shared_stores", description=__doc__
    )
    parser.add_argument("--vault", required=True, help="The vault that must be verified first.")
    parser.add_argument("--confirm", default=None, help="The counts this run reported, as v:e:n.")
    parser.add_argument(
        "--analytics-db-path",
        default=os.environ.get(
            "ANALYTICS_DB_PATH", "../OspreyFlow_Data/_local-runtime/analytics.duckdb"
        ),
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    shared_db = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    try:
        check_shared_database(shared_db)
        found = vault_locations(args.vault, args.analytics_db_path)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    vault_client = ArcadeDBClient(ArcadeDBConfig.from_env(found.database))
    shared_client = ArcadeDBClient(ArcadeDBConfig.from_env(shared_db))
    try:
        problems = await vault_problems(
            vault_client,
            node_type=groovy_identifier(physical_type_name("Endpoint")),
            edge_type=groovy_identifier(physical_type_name("TRANSACTED")),
            events=DuckEvents(found.analytics_db_path),
        )
        return await clear_shared(
            ArcadeShared(shared_client, shared_db),
            DuckEvents(args.analytics_db_path),
            vault_problems=problems,
            confirm=args.confirm,
        )
    finally:
        await vault_client.aclose()
        await shared_client.aclose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
