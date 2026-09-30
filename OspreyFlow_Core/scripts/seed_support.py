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

from adapters.graph_arcadedb.client import ArcadeDBError
from adapters.graph_arcadedb.gremlin_literals import groovy_string_literal
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

    async def gremlin(
        self,
        command: str,
        *,
        params: Mapping[str, Any] | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]: ...


async def _count(client: _Sql, type_name: str, prefix: str) -> int:
    rows = await client.sql(f"SELECT count(*) AS n FROM {type_name} WHERE id LIKE '{prefix}%'")
    return int(rows[0]["n"]) if rows else 0


def _is_parse_error(error: ArcadeDBError) -> bool:
    return "ParseException" in (error.exception_class or "")


def _is_missing_record(error: ArcadeDBError) -> bool:
    return error.status_code == 404 or "RecordNotFound" in (error.exception_class or "")


async def _truncate_if_only_this_seed(
    client: _Sql, types: list[tuple[str, str]], *, cause: ArcadeDBError
) -> None:
    """A row-by-row delete hit a record ArcadeDB could not find (interrupted loads left a dangling
    link; ADR-055 Amendment 7). Empty the types instead, edges first, but only if every row in
    each type carries this seed's prefix: the types are shared with other datasets, so a type that
    holds anything else is left alone and the clean-up fails."""
    for type_name, prefix in types:
        rows = await client.sql(f"SELECT count(*) AS n FROM {type_name}")
        every = int(rows[0]["n"]) if rows else 0
        ours = await _count(client, type_name, prefix)
        if every != ours:
            raise CleanUpIncomplete(
                f"{every - ours:,} rows in {type_name} are not this seed's, so it was not "
                f"truncated; the row delete failed with: {cause}"
            )
    for type_name, _ in types:
        await client.sql(f"TRUNCATE TYPE {type_name} UNSAFE")


async def _delete_scoped(client: _Sql, *, kind: str, type_name: str, prefix: str) -> None:
    """Delete this type's rows whose id starts with `prefix`, trying the ways ArcadeDB documents.

    Seen: ArcadeDB refused `DELETE EDGE ...` outright (a ParseException), and its SQL differs from
    the OrientDB dialect it descends from, which I had assumed. So the forms are tried in turn, and
    only a *parse* refusal moves on to the next one: any other error (a lock, a full disk) is
    raised, not worked around. Every form is scoped by the label and the id prefix. If none is
    accepted, the error names each one, so the owner can see what was attempted."""
    literal = groovy_string_literal
    step = "E" if kind == "EDGE" else "V"
    forms = [
        f"DELETE FROM {type_name} WHERE id LIKE '{prefix}%'",
        f"DELETE {kind} {type_name} WHERE id LIKE '{prefix}%'",
        f"g.{step}().hasLabel({literal(type_name)})"
        f".has('id', TextP.startingWith({literal(prefix)})).drop()",
    ]
    refused: list[str] = []
    for form in forms:
        try:
            if form.startswith("g."):
                await client.gremlin(form)
            else:
                await client.sql(form)
        except ArcadeDBError as error:
            if not _is_parse_error(error):
                raise
            refused.append(form)
            continue
        return
    raise CleanUpIncomplete(
        "ArcadeDB accepted none of the delete forms tried, so nothing was deleted: "
        + "; ".join(refused)
    )


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
    try:
        await _delete_scoped(client, kind="EDGE", type_name=edge_type, prefix=edge_prefix)
        await _delete_scoped(client, kind="VERTEX", type_name=node_type, prefix=node_prefix)
    except ArcadeDBError as error:
        if not _is_missing_record(error):
            raise
        await _truncate_if_only_this_seed(
            client,
            [(edge_type, edge_prefix), (node_type, node_prefix)],
            cause=error,
        )
    left = await _count(client, node_type, node_prefix) + await _count(
        client, edge_type, edge_prefix
    )
    if left:
        raise CleanUpIncomplete(f"{left:,} of this seed's graph rows are left after deleting")
    return accounts, transactions


async def inspect_graph(
    client: _Sql,
    *,
    node_type: str,
    node_prefix: str,
    edge_type: str,
    edge_prefix: str,
    record: str | None = None,
) -> list[str]:
    """What the graph holds, as report lines, by `SELECT` only (it cannot change anything). Each
    probe is reported on its own, and one that fails is reported as the failure and the rest still
    run: an unreadable record is itself the evidence (ADR-055 Amendment 6)."""
    probes: list[tuple[str, str]] = [
        (f"{node_type} (every row)", f"SELECT count(*) AS n FROM {node_type}"),
        (
            f"{node_type} with ids {node_prefix}...",
            f"SELECT count(*) AS n FROM {node_type} WHERE id LIKE '{node_prefix}%'",
        ),
        (f"{edge_type} (every row)", f"SELECT count(*) AS n FROM {edge_type}"),
        (
            f"{edge_type} with ids {edge_prefix}...",
            f"SELECT count(*) AS n FROM {edge_type} WHERE id LIKE '{edge_prefix}%'",
        ),
        (
            f"three {edge_type} ids {edge_prefix}...",
            f"SELECT id FROM {edge_type} WHERE id LIKE '{edge_prefix}%' LIMIT 3",
        ),
    ]
    if record:
        probes.append((f"record {record}", f"SELECT FROM {record}"))
    lines: list[str] = []
    for label, statement in probes:
        try:
            rows = await client.sql(statement)
            lines.append(f"{label}: {rows}")
        except ArcadeDBError as error:
            lines.append(f"{label}: FAILED {error}")
    return lines


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
