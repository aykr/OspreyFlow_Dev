"""What every dataset seed shares (ADR-055 Amendment 3).

**Progress.** A graph write to a real ArcadeDB is one lookup and one write per element over HTTP and
can take hours; a seed that says nothing looks hung. `write_graph` prints a line every so many
batches, with the elapsed time.

**Events are never loaded twice.** The analytics load is an INSERT, so a second run into the same
case would double every count. `events_already_loaded` lets a seed refuse *before* the long graph
phase. (The graph write is an upsert keyed on id, so repeating it is harmless, which is what makes
an interrupted load resumable.)
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import duckdb

from ports.graph import GraphPort

#: A progress line every this many graph batches, so a slow write is visible as slow.
PROGRESS_EVERY = 25


async def write_graph(
    graph: GraphPort,
    nodes: Sequence[Any],
    edges: Sequence[Any],
    *,
    chunk: int,
    nouns: tuple[str, str],
    progress: Callable[[str], None] | None = None,
) -> None:
    """Nodes first, then edges, each in small transactions (ArcadeDB fails larger ones with
    "Error in execution in lock"). A failing batch is rolled back and the error raised."""
    say = progress or (lambda line: print(line, flush=True))
    say(f"  graph: writing {len(nodes):,} {nouns[0]} and {len(edges):,} {nouns[1]}")
    for noun, items, upsert in (
        (nouns[0], nodes, graph.upsert_nodes),
        (nouns[1], edges, graph.upsert_edges),
    ):
        started = time.monotonic()
        for start in range(0, len(items), chunk):
            tx = await graph.begin_transaction()
            try:
                await upsert(items[start : start + chunk], tx)
            except Exception:
                await graph.rollback_transaction(tx)
                raise
            await graph.commit_transaction(tx)
            done = min(start + chunk, len(items))
            if (start // chunk) % PROGRESS_EVERY == 0 or done == len(items):
                seconds = int(time.monotonic() - started)
                say(f"  graph: {done:,} of {len(items):,} {noun} written ({seconds}s)")


class CleanUpIncomplete(RuntimeError):
    """Rows the clean-up meant to delete are still there."""


class _Sql(Protocol):
    async def sql(
        self,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]: ...


async def _count(client: _Sql, type_name: str, prefix: str) -> int:
    rows = await client.sql(f"SELECT count(*) AS n FROM {type_name} WHERE id LIKE '{prefix}%'")
    return int(rows[0]["n"]) if rows else 0


async def clear_seeded_graph(
    client: _Sql, *, node_type: str, node_prefix: str, edge_type: str, edge_prefix: str
) -> tuple[int, int]:
    """Delete this seed's own graph rows, and only those: every statement is scoped by the seed's
    id prefix, because the account type and the edge types are shared with other datasets.
    Transactions first, then accounts. Returns `(accounts, transactions)` deleted. Raises if any
    are left, so a fresh load is never written on top of leftovers.

    Why this exists (ADR-055 Amendment 4): writing a transaction that already exists adds to its
    occurrence count, so an interrupted load cannot simply be resumed."""
    accounts = await _count(client, node_type, node_prefix)
    transactions = await _count(client, edge_type, edge_prefix)
    await client.sql(f"DELETE EDGE {edge_type} WHERE id LIKE '{edge_prefix}%'")
    await client.sql(f"DELETE VERTEX {node_type} WHERE id LIKE '{node_prefix}%'")
    left = await _count(client, node_type, node_prefix) + await _count(
        client, edge_type, edge_prefix
    )
    if left:
        raise CleanUpIncomplete(f"{left:,} of this seed's graph rows are left after deleting")
    return accounts, transactions


def events_already_loaded(analytics_db_path: Path | str, scope: str) -> bool:
    """Whether the case already has events. A missing file or table means it has none yet."""
    path = Path(analytics_db_path)
    if not path.exists():
        return False
    con = duckdb.connect(str(path))
    try:
        try:
            row = con.execute(
                "SELECT count(*) FROM events WHERE investigation_scope = ?", [scope]
            ).fetchone()
        except duckdb.CatalogException:
            return False
        return bool(row and row[0] > 0)
    finally:
        con.close()
