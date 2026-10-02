"""Measures how fast edges can be loaded, on scratch databases only (ADR-058 D10).

    python -m scripts.spike_bulk_transport            # about a thousand edges, three chunk sizes
    python -m scripts.spike_bulk_transport --edges 3000

What it settles. `BulkEdgeLoader` (packages/adapters/graph_arcadedb/bulk.py) was written and
unit-tested against a stand-in; its Gremlin shapes (`within`, `project`/`by`, `coalesce`, a closure
that adds one edge per row) have never run against a real ArcadeDB. This runs each shape, says
which fail, times the load at several chunk sizes against the upsert path on the same data, and
checks that every method leaves the same edges behind and counts any edge id a scan finds twice
(the stray-record defect, ADR-056 Amendment 19).

Safety. It touches only databases whose names start `spike_bulk_`, creates each one itself and drops
it afterwards (`refuse_unless_scratch` stops it naming anything else; a test shows that refusal
firing). It never opens the working database. Run it with the store idle: a timing taken while
another load writes is contaminated by that load (`process/CLAUDE.md` rule 14).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from scripts.seed_support import ids_stored_twice

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.bulk import GremlinBulkTransport
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from demo_fixtures.paysim import PaysimRow, build_graph_writes
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, NodeWrite

SCRATCH_PREFIX = "spike_bulk_"
CHUNK_SIZES = (100, 500, 2000)
UPSERT_CHUNK = 40  # what every seed uses (ArcadeDB fails larger upsert transactions)
EDGE_TYPE = "TRANSACTED"

_HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="spike", owning_unit="spike"
)


class NotScratchError(Exception):
    """The script was about to touch a database that is not its own scratch one."""


def refuse_unless_scratch(database: str) -> str:
    if not database.startswith(SCRATCH_PREFIX):
        raise NotScratchError(
            f"refusing to touch {database!r}: the spike only uses databases named {SCRATCH_PREFIX}*"
        )
    return database


def synthetic_writes(edges: int) -> tuple[list[NodeWrite], list[EdgeWrite]]:
    """PaySim-shaped writes with no data in them: about one account per 1.4 edges, so accounts are
    shared between edges, and every tenth transaction repeats an earlier pair (the merge path)."""
    accounts = max(2, int(edges / 1.4))
    rows: list[PaysimRow] = []
    for i in range(edges):
        if i and i % 10 == 0:
            origin, destination = rows[i // 2].origin, rows[i // 2].destination
        else:
            origin, destination = f"A{(i * 7) % accounts}", f"B{(i * 13 + 1) % accounts}"
        rows.append(
            PaysimRow(
                index=i,
                step=1 + i % 700,
                type="TRANSFER",
                amount=float(10 + i % 90),
                origin=origin,
                destination=destination,
                is_fraud=0,
                is_flagged=0,
            )
        )
    return build_graph_writes(rows, created_by="spike", handling=_HANDLING)


@dataclass
class Outcome:
    label: str
    seconds: float | None = None
    edges: dict[str, int] = field(default_factory=dict)  # edge id -> occurrences
    strays: int = 0
    note: str = ""

    def line(self, edges_written: int) -> str:
        if self.seconds is None:
            return f"  {self.label}: FAILED ({self.note})"
        rate = edges_written / self.seconds if self.seconds else float("inf")
        extra = f"; {self.note}" if self.note else ""
        return (
            f"  {self.label}: {self.seconds:.1f} s for {edges_written:,} edges "
            f"({rate:,.0f} edges/s), {len(self.edges):,} stored, "
            f"{self.strays} id(s) stored twice{extra}"
        )


def differences(reference: Mapping[str, int], other: Mapping[str, int]) -> list[str]:
    """What differs between two stored edge sets: ids missing either way, and occurrences that
    disagree. Empty means the two methods left the same edges behind."""
    found = [f"only in the reference: {i}" for i in sorted(set(reference) - set(other))]
    found += [f"only in the other: {i}" for i in sorted(set(other) - set(reference))]
    found += [
        f"{i}: occurrences {reference[i]} against {other[i]}"
        for i in sorted(set(reference) & set(other))
        if reference[i] != other[i]
    ]
    return found


async def _stored_edges(client: ArcadeDBClient) -> dict[str, int]:
    label = groovy_identifier(physical_type_name(EDGE_TYPE))
    rows = await client.sql(f"SELECT id, occurrences FROM {label}")
    return {str(r["id"]): int(r["occurrences"]) for r in rows}


async def _fresh(name: str, nodes: list[NodeWrite]) -> tuple[ArcadeDBClient, GraphArcadeDBAdapter]:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(refuse_unless_scratch(name)))
    await client.drop_database_named(name)
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    for start in range(0, len(nodes), UPSERT_CHUNK):
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(nodes[start : start + UPSERT_CHUNK], tx)
        await graph.commit_transaction(tx)
    return client, graph


async def _drop(client: ArcadeDBClient, name: str) -> None:
    await client.drop_database_named(refuse_unless_scratch(name))
    await client.aclose()


async def _measure(
    label: str,
    name: str,
    nodes: list[NodeWrite],
    load: Callable[[GraphArcadeDBAdapter, ArcadeDBClient], Awaitable[str]],
) -> Outcome:
    """One method on its own freshly created database: time the load only, then read back."""
    outcome = Outcome(label)
    client, graph = await _fresh(name, nodes)
    try:
        started = time.perf_counter()
        try:
            outcome.note = await load(graph, client)
        except Exception as error:  # reported as a line, never a crash: the point is to find out
            outcome.note = f"{type(error).__name__}: {str(error)[:200]}"
            return outcome
        outcome.seconds = time.perf_counter() - started
        outcome.edges = await _stored_edges(client)
        outcome.strays = len(
            await ids_stored_twice(
                client, edge_type=groovy_identifier(physical_type_name(EDGE_TYPE))
            )
        )
        return outcome
    finally:
        await _drop(client, name)


async def _sql_script(client: ArcadeDBClient, edges: list[EdgeWrite], chunk: int) -> str:
    """Candidate B, timing only: one `sqlscript` call per chunk with a `CREATE EDGE` per row. It
    writes just the id and occurrences, so it is compared for speed, not for equivalence."""
    node = groovy_identifier(physical_type_name("Endpoint"))
    label = groovy_identifier(physical_type_name(EDGE_TYPE))
    for start in range(0, len(edges), chunk):
        part = edges[start : start + chunk]
        statements: list[str] = []
        params: dict[str, Any] = {}
        for n, edge in enumerate(part):
            statements.append(
                f"CREATE EDGE {label} FROM (SELECT FROM {node} WHERE id = :s{n}) "
                f"TO (SELECT FROM {node} WHERE id = :t{n}) SET id = :i{n}, occurrences = :o{n};"
            )
            params |= {f"s{n}": edge.source, f"t{n}": edge.target, f"i{n}": edge.id, f"o{n}": 1}
        await client.command(
            "sqlscript", "BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;", params=params
        )
    return "timing only: writes id and occurrences, not the full edge"


async def _shape_checks(
    client: ArcadeDBClient, nodes: list[NodeWrite], edges: list[EdgeWrite]
) -> list[str]:
    """Run each query shape the loader uses against a populated database and say which work."""
    transport = GremlinBulkTransport(client)
    label = groovy_identifier(physical_type_name(EDGE_TYPE))
    ids = [n.id for n in nodes[:5]]
    pairs = [(e.source, e.target) for e in edges[:5]]
    checks: list[tuple[str, Callable[[], Awaitable[Any]]]] = [
        ("vertex_labels", lambda: transport.vertex_labels(ids)),
        ("edge_type_is_empty", lambda: transport.edge_type_is_empty(label)),
        ("stored_pairs (directed)", lambda: transport.stored_pairs(label, pairs, directed=True)),
        ("stored_pairs (undirected)", lambda: transport.stored_pairs(label, pairs, directed=False)),
        ("corpus_total", lambda: transport.corpus_total(label)),
        ("degrees", lambda: transport.degrees(label, ids)),
    ]
    lines = []
    for name, call in checks:
        try:
            result = await call()
            lines.append(f"  shape {name}: ok ({_brief(result)})")
        except Exception as error:
            lines.append(f"  shape {name}: FAILED ({type(error).__name__}: {str(error)[:200]})")
    return lines


def _brief(result: Any) -> str:
    text = repr(result)
    return text if len(text) <= 80 else text[:77] + "..."


async def run(edge_count: int, say: Callable[[str], None] = print) -> int:
    nodes, edges = synthetic_writes(edge_count)
    stamp = datetime.now(UTC).strftime("%H%M%S")
    say(f"spike: {len(nodes):,} accounts, {len(edges):,} transactions (scratch databases only)")

    async def by_upsert(graph: GraphArcadeDBAdapter, _: ArcadeDBClient) -> str:
        for start in range(0, len(edges), UPSERT_CHUNK):
            tx = await graph.begin_transaction()
            await graph.upsert_edges(edges[start : start + UPSERT_CHUNK], tx)
            await graph.commit_transaction(tx)
        return f"chunks of {UPSERT_CHUNK}"

    reference = await _measure(
        "upsert (today's path)", f"{SCRATCH_PREFIX}up_{stamp}", nodes, by_upsert
    )
    outcomes = [reference]
    for size in CHUNK_SIZES:

        async def by_bulk(graph: GraphArcadeDBAdapter, _: ArcadeDBClient, size: int = size) -> str:
            result = await graph.bulk_load_edges(edges, chunk_size=size)
            return f"{result.chunks} chunk(s), {len(result.collisions)} collision(s)"

        outcomes.append(
            await _measure(
                f"bulk, Gremlin, chunks of {size}",
                f"{SCRATCH_PREFIX}g{size}_{stamp}",
                nodes,
                by_bulk,
            )
        )

    async def by_sql(_: GraphArcadeDBAdapter, client: ArcadeDBClient) -> str:
        return await _sql_script(client, edges, 500)

    outcomes.append(
        await _measure(
            "bulk, SQL script, chunks of 500", f"{SCRATCH_PREFIX}sql_{stamp}", nodes, by_sql
        )
    )

    say("speed and strays:")
    for outcome in outcomes:
        say(outcome.line(len(edges)))
    say("equivalence with the upsert path (stored edge ids and occurrences):")
    worst = 0
    for outcome in outcomes[1:-1]:
        if outcome.seconds is None or reference.seconds is None:
            say(f"  {outcome.label}: not compared (it failed, or so did the reference)")
            worst = 1
            continue
        found = differences(reference.edges, outcome.edges)
        say(f"  {outcome.label}: {'identical' if not found else f'{len(found)} difference(s)'}")
        for line in found[:5]:
            say(f"    {line}")
        worst = worst or int(bool(found))

    say("query shapes against a populated scratch database:")
    name = f"{SCRATCH_PREFIX}shapes_{stamp}"
    client, graph = await _fresh(name, nodes)
    try:
        for start in range(0, min(len(edges), 200), UPSERT_CHUNK):
            tx = await graph.begin_transaction()
            await graph.upsert_edges(edges[start : start + UPSERT_CHUNK], tx)
            await graph.commit_transaction(tx)
        for line in await _shape_checks(client, nodes, edges):
            say(line)
            worst = worst or int("FAILED" in line)
    finally:
        await _drop(client, name)
    say("spike: scratch databases dropped. Nothing else was touched.")
    return worst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--edges", type=int, default=1000)
    args = parser.parse_args(argv)
    return asyncio.run(run(args.edges))


if __name__ == "__main__":
    sys.exit(main())
