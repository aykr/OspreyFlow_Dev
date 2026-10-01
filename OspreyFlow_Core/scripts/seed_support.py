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

import asyncio
import inspect
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple, Protocol

import duckdb
import httpx

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
    on_batch: Callable[[str, int], Awaitable[None] | None] | None = None,
) -> None:
    """Nodes first, then edges, each in small transactions (ArcadeDB fails larger ones with
    "Error in execution in lock"). A failing batch is rolled back and the error raised.
    `on_batch(noun, index)` is called after each batch is committed, with its position among that
    noun's batches (counted from 0): a reproduction uses it to line a stored duplicate up with the
    batch that wrote it. A coroutine function is awaited before the next batch starts."""
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
            if on_batch is not None:
                hooked = on_batch(noun, start // chunk)
                if inspect.isawaitable(hooked):
                    await hooked
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


_VAULT_ID = re.compile(r"[a-z][a-z0-9-]{0,30}")


class VaultLocations(NamedTuple):
    """Where one vault keeps its stores (ADR-056, stage 0)."""

    database: str
    analytics_db_path: str


def vault_locations(vault: str, analytics_db_path: str) -> VaultLocations:
    """The graph database and the analytics file for vault `vault`, derived from its id and from
    where the deployment keeps its analytics file: `vault_<id>` (hyphens become underscores, which
    ArcadeDB accepts) and `<analytics directory>/vaults/<id>/analytics.duckdb`. The id is short,
    lower-case and stable; anything else is refused, so it can never build a path outside
    `vaults/`."""
    if not _VAULT_ID.fullmatch(vault):
        raise ValueError(
            f"{vault!r} is not a vault id: lower-case letters, digits and hyphens, starting with "
            "a letter, at most 31 characters"
        )
    base = Path(analytics_db_path).parent / "vaults" / vault / "analytics.duckdb"
    return VaultLocations("vault_" + vault.replace("-", "_"), str(base))


class _Lifecycle(Protocol):
    async def drop_database(self) -> None: ...

    async def create_database_if_absent(self) -> None: ...

    async def list_databases(self) -> list[str]: ...


async def reset_graph_database(
    client: _Lifecycle,
    *,
    database: str,
    say: Callable[[str], None] = print,
    wait_seconds: float = 600.0,
    poll_seconds: float = 5.0,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> None:
    """Drop the whole graph database and create it again empty (ADR-055 Amendment 9). Everything in
    it goes, every case's graph rows, which is why it is only ever run when explicitly asked for.
    Seen: after interrupted loads and a forced truncate the storage held a record ArcadeDB could
    not read back, and row-level clean-up could not repair that. A client timeout on the drop is
    waited out, as with the truncate: the server carries on."""
    say(f"  reset: dropping the graph database {database!r} (all graph data, every case)")
    try:
        await client.drop_database()
    except httpx.TimeoutException:
        say("  reset: the drop is taking longer than the client waits; watching it")
        waited = 0.0
        while database in await client.list_databases():
            if waited >= wait_seconds:
                raise CleanUpIncomplete(
                    f"database {database!r} still exists {int(wait_seconds)}s after the drop"
                ) from None
            await sleep(poll_seconds)
            waited += poll_seconds
    if database in await client.list_databases():
        raise CleanUpIncomplete(f"database {database!r} still exists after the drop")
    await client.create_database_if_absent()
    say(f"  reset: {database!r} created again, empty")


async def _rows_in(client: _Sql, type_name: str) -> int:
    rows = await client.sql(f"SELECT count(*) AS n FROM {type_name}")
    return int(rows[0]["n"]) if rows else 0


async def _truncate_and_wait(
    client: _Sql,
    type_name: str,
    *,
    say: Callable[[str], None],
    wait_seconds: float,
    poll_seconds: float,
    sleep: Callable[[float], Awaitable[object]],
) -> None:
    """Truncate one type. Seen: the HTTP client gives up after 30 seconds, and emptying tens of
    thousands of rows takes longer; the server carries on regardless. So a client timeout is not a
    failure: wait, counting the rows left (a count that itself times out is retried), until the
    type is empty or `wait_seconds` have passed (ADR-055 Amendment 8)."""
    try:
        await client.sql(f"TRUNCATE TYPE {type_name} UNSAFE")
        say(f"  clean-up: {type_name} emptied")
        return
    except httpx.TimeoutException:
        say(f"  clean-up: {type_name} is taking longer than the client waits; watching it")
    waited = 0.0
    while waited <= wait_seconds:
        await sleep(poll_seconds)
        waited += poll_seconds
        try:
            left = await _rows_in(client, type_name)
        except httpx.TimeoutException:
            say(f"  clean-up: {type_name} is still busy ({int(waited)}s)")
            continue
        if left == 0:
            say(f"  clean-up: {type_name} emptied ({int(waited)}s)")
            return
        say(f"  clean-up: {type_name} has {left:,} rows left ({int(waited)}s)")
    raise CleanUpIncomplete(
        f"{type_name} was still not empty {int(wait_seconds)}s after the truncate was sent; "
        "ArcadeDB may still be working, so run --inspect to see"
    )


async def _truncate_if_only_this_seed(
    client: _Sql,
    types: list[tuple[str, str]],
    *,
    cause: ArcadeDBError,
    say: Callable[[str], None] = print,
    wait_seconds: float = 1800.0,
    poll_seconds: float = 10.0,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> None:
    """A row-by-row delete hit a record ArcadeDB could not find (interrupted loads left a dangling
    link; ADR-055 Amendment 7). Empty the types instead, edges first, but only if every row in
    each type carries this seed's prefix: the types are shared with other datasets, so a type that
    holds anything else is left alone and the clean-up fails."""
    for type_name, prefix in types:
        every = await _rows_in(client, type_name)
        ours = await _count(client, type_name, prefix)
        if every != ours:
            raise CleanUpIncomplete(
                f"{every - ours:,} rows in {type_name} are not this seed's, so it was not "
                f"truncated; the row delete failed with: {cause}"
            )
    say("  clean-up: the row delete could not continue; emptying the two types instead")
    for type_name, _ in types:
        await _truncate_and_wait(
            client,
            type_name,
            say=say,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            sleep=sleep,
        )


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
    client: _Sql,
    *,
    node_type: str,
    node_prefix: str,
    edge_type: str,
    edge_prefix: str,
    say: Callable[[str], None] = print,
    wait_seconds: float = 1800.0,
    poll_seconds: float = 10.0,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> tuple[int, int]:
    """Delete this seed's own graph rows, and only those: every statement is scoped by the seed's
    id prefix, because the account type and the edge types are shared with other datasets.
    Transactions first, then accounts. Returns `(accounts, transactions)` deleted. Raises if any
    are left, so a fresh load is never written on top of leftovers.

    Why this exists (ADR-055 Amendment 4): writing a transaction that already exists adds to its
    occurrence count, so an interrupted load cannot simply be resumed."""
    accounts = await _count(client, node_type, node_prefix)
    transactions = await _count(client, edge_type, edge_prefix)
    say(f"  clean-up: {accounts:,} accounts and {transactions:,} transactions to remove")
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
            say=say,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            sleep=sleep,
        )
    left = await _count(client, node_type, node_prefix) + await _count(
        client, edge_type, edge_prefix
    )
    if left:
        raise CleanUpIncomplete(f"{left:,} of this seed's graph rows are left after deleting")
    return accounts, transactions


def _quoted(value: str) -> str:
    """`value` for inside a single-quoted SQL literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def _report(
    client: _Sql, lines: list[str], label: str, statement: str
) -> list[dict[str, object]]:
    """Run one read-only probe and add its result, or its failure, to `lines`."""
    try:
        rows = await client.sql(statement)
    except ArcadeDBError as error:
        lines.append(f"{label}: FAILED {error}")
        return []
    lines.append(f"{label}: {rows}")
    return rows


def _stored_twice(row: dict[str, object]) -> bool:
    """A `GROUP BY id` row that names an id and counts it more than once."""
    count = row.get("n")
    return isinstance(count, int) and count > 1 and bool(row.get("id"))


class RepairAnomaly(RuntimeError):
    """A removal did not leave the graph as expected; the repair stopped, touching nothing else."""


@dataclass
class RepairReport:
    #: (id, the records removed or that would be) for each id handled. A missing edge has none.
    planned: list[tuple[str, list[str]]] = field(default_factory=list)
    #: Records deleted.
    removed: int = 0
    #: Ids written again, each checked to be stored once and reached once.
    written: list[str] = field(default_factory=list)
    #: (id, why) for each id left alone because it is not what the repair expects.
    skipped: list[tuple[str, str]] = field(default_factory=list)


#: Writes one edge, by id, through the normal write path (the caller knows how to build it).
Rewrite = Callable[[str], Awaitable[None]]


_RID = re.compile(r"#\d+:\d+")


async def ids_stored_twice(client: _Sql, *, edge_type: str, prefix: str = "") -> list[str]:
    """Ids under `prefix` that a scan of the edge type finds more than once. A scan, not an index
    lookup: the index can show one record where a scan finds two (ADR-056 Amendment 12)."""
    rows = await client.sql(
        f"SELECT id, count(*) AS n FROM {edge_type} GROUP BY id ORDER BY n DESC LIMIT 1000"
    )
    return sorted(
        str(r["id"]) for r in rows if _stored_twice(r) and str(r["id"]).startswith(prefix)
    )


#: What a seed says about ids stored twice: there is no repair (ADR-056 Amendment 19).
KNOWN_STRAY_ADVICE = (
    "a known ArcadeDB defect with no repair (ADR-056 Amendment 19); the product does not count them"
)


async def report_ids_stored_twice(
    client: _Sql,
    *,
    edge_types: Sequence[str],
    prefix: str = "",
    say: Callable[[str], None] = print,
    advice: str,
) -> int:
    """The check every seed ends with: how many ids a scan finds stored more than once, said
    loudly when there are any and plainly when there are none (silence cannot be told from a check
    that did not run). Returns the count."""
    found: list[str] = []
    for edge_type in edge_types:
        found += await ids_stored_twice(client, edge_type=edge_type, prefix=prefix)
    if not found:
        say("  check: no id stored more than once")
        return 0
    say(f"  check: !! {len(found)} id(s) stored more than once (ArcadeDB wrote a stray copy).")
    say("  check: a traversal reaches each edge once; a scan-based count sees both records.")
    say(f"  check: {advice}")
    return len(found)


async def _reachable_rids(
    client: _Sql, edge_type: str, edge_id: str, source: str
) -> tuple[list[str], int]:
    """The records of this edge id the source vertex's own edge list reaches, and how many that is,
    asked the way the product reads edges (a traversal), not by scanning the type."""
    base = (
        f'g.V().has("id",{groovy_string_literal(source)}).outE({groovy_string_literal(edge_type)})'
        f'.has("id",{groovy_string_literal(edge_id)})'
    )
    rows = await client.gremlin(base + ".id()")
    counted = await client.gremlin(base + ".count()")
    reached = [str(r.get("result")) for r in rows]
    return reached, int(counted[0]["result"]) if counted else 0


async def _records_of(client: _Sql, edge_type: str, edge_id: str) -> list[dict[str, Any]]:
    """Every stored record of this id, by a scan (`LIKE`), never the index."""
    rows = await client.sql(
        f"SELECT @rid AS rid, id, source FROM {edge_type} WHERE id LIKE '{_quoted(edge_id)}'"
    )
    return [r for r in rows if r.get("id") == edge_id]


async def _check_stored_once_and_reached(
    client: _Sql, edge_type: str, edge_id: str, source: str, *, after: str
) -> None:
    """One record stored, and the source's edge list reaches it once: both, because a stray is
    stored but not reached and a lost link is reached by nothing (ADR-056 Amendments 15 and 17)."""
    stored = await _records_of(client, edge_type, edge_id)
    _, reached = await _reachable_rids(client, edge_type, edge_id, source)
    if len(stored) != 1 or reached != 1:
        raise RepairAnomaly(
            f"{edge_id}: after {after}, {len(stored)} record(s) are stored and the source reaches "
            f"{reached}; stopped before touching any other id"
        )


async def stored_edge_ids(
    client: _Sql, *, edge_type: str, prefix: str = "", page: int = 5000
) -> set[str]:
    """Every id stored under `prefix`, read a page at a time (a scan, not the index)."""
    found: set[str] = set()
    skip = 0
    while True:
        rows = await client.sql(
            f"SELECT id FROM {edge_type} WHERE id LIKE '{_quoted(prefix)}%' "
            f"ORDER BY id SKIP {skip} LIMIT {page}"
        )
        found.update(str(r["id"]) for r in rows)
        if len(rows) < page:
            return found
        skip += page


async def restore_missing_edges(
    client: _Sql,
    *,
    edge_type: str,
    prefix: str = "",
    expected: Mapping[str, str],
    rewrite: Rewrite,
    say: Callable[[str], None] = print,
    apply: bool = False,
    limit: int | None = None,
    page: int = 5000,
) -> RepairReport:
    """Write the edges the dataset has and the store lacks. `expected` maps each edge id the load
    writes to its source vertex id. A dry run unless `apply`; after each write the id is checked
    (stored once, reached once) and the first failure raises `RepairAnomaly`. Ids stored that the
    dataset does not write are reported and left alone."""
    report = RepairReport()
    stored = await stored_edge_ids(client, edge_type=edge_type, prefix=prefix, page=page)
    extra = sorted(stored - set(expected))
    if extra:
        say(f"  {len(extra)} stored id(s) are not ones this load writes (left alone): {extra[:5]}")
    missing = sorted(set(expected) - stored)
    if not missing:
        say(f"  restore: nothing is missing ({len(expected):,} expected, all stored)")
        return report
    say(f"  restore: {len(missing):,} of {len(expected):,} expected edge(s) are not stored")
    for edge_id in missing:
        if limit is not None and len(report.planned) >= limit:
            break
        report.planned.append((edge_id, []))
        say(f"  {edge_id}: stored 0 times; {'writing it' if apply else 'would write it'}")
        if not apply:
            continue
        await rewrite(edge_id)
        await _check_stored_once_and_reached(
            client, edge_type, edge_id, expected[edge_id], after="writing it"
        )
        report.written.append(edge_id)
    return report


async def repair_ids_stored_twice(
    client: _Sql,
    *,
    edge_type: str,
    prefix: str = "",
    expected: Mapping[str, str],
    rewrite: Rewrite,
    say: Callable[[str], None] = print,
    apply: bool = False,
    limit: int | None = None,
) -> RepairReport:
    """Put right each id a scan finds stored more than once: remove every copy, then write the edge
    once through the normal write path.

    It does not keep one copy and delete the other: run against a real ArcadeDB, deleting the stray
    by its record id removed the real record too (ADR-056 Amendment 17). So nothing is assumed about
    which record a delete touches: every copy is removed, none may be left, and the edge is written
    again and checked (stored once, reached once). It deletes records, so: a dry run unless `apply`;
    one id at a time; an id is left alone unless its copies are what the dataset says they should
    be; `RepairAnomaly` stops the run at the first id that does not check out; `limit` handles only
    that many ids."""
    report = RepairReport()
    for edge_id in await ids_stored_twice(client, edge_type=edge_type, prefix=prefix):
        if limit is not None and len(report.planned) >= limit:
            break
        copies = await _records_of(client, edge_type, edge_id)
        rids = [str(r["rid"]) for r in copies]
        sources = {str(r.get("source")) for r in copies}
        if edge_id not in expected:
            why = "it is not an edge this load writes, so it cannot be written again"
        elif len(copies) < 2 or not all(_RID.fullmatch(r) for r in rids):
            why = "its stored copies are not what the repair expects"
        elif sources != {expected[edge_id]}:
            why = "its stored copies do not start where the dataset says they should"
        else:
            why = ""
        if why:
            report.skipped.append((edge_id, why))
            say(f"  {edge_id}: left alone ({why})")
            continue
        report.planned.append((edge_id, rids))
        verb = "removing" if apply else "would remove"
        say(
            f"  {edge_id}: stored {len(rids)} times ({', '.join(rids)}); {verb} every copy, "
            f"then {'writing' if apply else 'write'} it once"
        )
        if not apply:
            continue
        for rid in rids:
            if any(r["rid"] == rid for r in await _records_of(client, edge_type, edge_id)):
                await client.sql(f"DELETE FROM {edge_type} WHERE @rid = {rid}")
                report.removed += 1
        left = await _records_of(client, edge_type, edge_id)
        if left:
            raise RepairAnomaly(
                f"{edge_id}: {len(left)} record(s) are still stored after removing every copy; "
                "nothing was written and no other id was touched"
            )
        await rewrite(edge_id)
        await _check_stored_once_and_reached(
            client,
            edge_type,
            edge_id,
            expected[edge_id],
            after="removing every copy and writing it",
        )
        report.written.append(edge_id)
    return report


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
            f"{edge_type}: the ids stored most often (n > 1 means a duplicate)",
            f"SELECT id, count(*) AS n FROM {edge_type} GROUP BY id ORDER BY n DESC LIMIT 1000",
        ),
        (
            f"{node_type}: the ids stored most often (n > 1 means a duplicate)",
            f"SELECT id, count(*) AS n FROM {node_type} GROUP BY id ORDER BY n DESC LIMIT 5",
        ),
        (
            f"{edge_type}: total of the occurrence counts",
            f"SELECT sum(occurrences) AS total FROM {edge_type}",
        ),
        (
            f"three {edge_type} ids {edge_prefix}...",
            f"SELECT id FROM {edge_type} WHERE id LIKE '{edge_prefix}%' LIMIT 3",
        ),
    ]
    if record:
        probes.append((f"record {record}", f"SELECT FROM {record}"))
    lines: list[str] = []
    most_stored: list[dict[str, object]] = []
    for label, statement in probes:
        try:
            rows = await client.sql(statement)
            if label.startswith(f"{edge_type}: the ids stored most often"):
                # Five are shown; the rest are counted, from the rows, because ArcadeDB's parser
                # refuses `SELECT count(*) FROM (SELECT ...)`.
                most_stored = rows
                lines.append(f"{label}: {rows[:5]}")
                twice = sum(1 for r in rows if _stored_twice(r))
                more = " (at least: the query stops at 1,000 ids)" if len(rows) >= 1000 else ""
                lines.append(f"{edge_type}: ids stored more than once: {twice}{more}")
            else:
                lines.append(f"{label}: {rows}")
        except ArcadeDBError as error:
            lines.append(f"{label}: FAILED {error}")
    # A duplicated id is shown as the records themselves: the merge key is the source-target pair,
    # so two records with one id mean the lookup missed the first, or the endpoints differ.
    duplicates = [r for r in most_stored if _stored_twice(r)]
    if duplicates:
        first_id = str(duplicates[0]["id"])
        rows = await _report(
            client,
            lines,
            f"{edge_type}: both records of {first_id}",
            f"SELECT FROM {edge_type} WHERE id LIKE '{_quoted(first_id)}'",
        )
        # A vertex reachable twice would make one traversal write two edges, so each end of the
        # first duplicate is looked up by a scan (`LIKE`), which an index cannot answer.
        ends = {str(r[k]) for r in rows for k in ("source", "target") if r.get(k)}
        for vertex_id in sorted(ends):
            await _report(
                client,
                lines,
                f"{node_type}: records with id {vertex_id}",
                f"SELECT @rid AS rid, id FROM {node_type} WHERE id LIKE '{_quoted(vertex_id)}'",
            )
        for row in duplicates[1:10]:
            dup_id = str(row["id"])
            await _report(
                client,
                lines,
                f"{edge_type}: {dup_id} (rid, source, target)",
                f"SELECT @rid AS rid, source, target FROM {edge_type} "
                f"WHERE id LIKE '{_quoted(dup_id)}'",
            )
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


def events_summary(analytics_db_path: Path | str) -> list[str]:
    """What an analytics file holds, as report lines, opened read-only so it cannot change
    anything: the event count per case. A missing file, a missing table, and a file the Conduit has
    open (DuckDB allows one writer) are each reported as what they are (ADR-056, stage 0)."""
    path = Path(analytics_db_path)
    if not path.exists():
        return [f"analytics file {path}: does not exist"]
    try:
        con = duckdb.connect(str(path), read_only=True)
    except (duckdb.IOException, duckdb.ConnectionException) as error:
        return [f"analytics file {path}: cannot be opened now ({str(error).splitlines()[0]})"]
    try:
        try:
            rows = con.execute(
                "SELECT investigation_scope, count(*) FROM events GROUP BY 1 ORDER BY 1"
            ).fetchall()
        except duckdb.CatalogException:
            return [f"analytics file {path}: no events table"]
    finally:
        con.close()
    if not rows:
        return [f"analytics file {path}: events table is empty"]
    return [f"analytics file {path}: {n:,} events in case {scope}" for scope, n in rows]
