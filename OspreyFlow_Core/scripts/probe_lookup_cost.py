"""Times one account lookup by id four ways as the graph grows, on a scratch database only.

    python -m scripts.probe_lookup_cost                       # 1,000, 5,000 and 15,000 accounts
    python -m scripts.probe_lookup_cost --sizes 2000,10000

(ADR-058 Amendment 5.) The upsert path's cost per edge followed the account count (10 ms at 773
accounts, 79 ms at 13,426) and a bulk edge cost about 23 ms for two Gremlin `has("id", ...)`
lookups, against 0.3 ms for the same two lookups in SQL. The hypothesis is that the Gremlin lookup
walks the vertex type where the SQL one uses the id index. This does not assume it. At each size
it times, over the same accounts:

  gremlin_has_id        g.V().has("id", X).elementMap()               what the adapter sends today
  gremlin_label_has_id  g.V().hasLabel(T).has("id", X).elementMap()  label first, then the property
  gremlin_has_label_id  g.V().has(T, "id", X).elementMap()            label and property together
  sql_where_id          SELECT FROM T WHERE id = :id                  what the SQL script uses

and lists the indexes the store holds on the account type. A lookup that stays flat as accounts
grow uses an index; one that grows with them scans. The answer decides whether `upsert_*` needs the
same change as the bulk path.

Safety. As the bulk spike: only databases named `spike_bulk_*`, created and dropped by this script
(`refuse_unless_scratch` stops anything else), leftovers from an interrupted run swept first. Run
with the store idle: a timing taken while another load writes is contaminated by it
(`process/CLAUDE.md` rule 14).
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from scripts.spike_bulk_transport import (
    SCRATCH_PREFIX,
    UPSERT_CHUNK,
    _fresh,
    refuse_unless_scratch,
    sweep_leftovers,
    synthetic_writes,
)

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier, groovy_string_literal
from adapters.graph_arcadedb.naming import physical_type_name

DEFAULT_SIZES = (1000, 5000, 15000)
LOOKUPS = 30  # accounts looked up at each size, spread across the whole set
SHAPES = ("gremlin_has_id", "gremlin_label_has_id", "gremlin_has_label_id", "sql_where_id")


@dataclass(frozen=True)
class Lookup:
    language: str
    command: str
    params: dict[str, Any] | None = None


def lookup_shapes(label: str, node_id: str) -> dict[str, Lookup]:
    """The four ways of finding one account. The first is character for character what the
    adapter sends (`adapter.py`, `g.V().has("id", ...).elementMap()`), so a result for it is a
    result for the adapter."""
    lit = groovy_string_literal(node_id)
    typ = groovy_string_literal(label)
    return {
        "gremlin_has_id": Lookup("gremlin", f'g.V().has("id",{lit}).elementMap()'),
        "gremlin_label_has_id": Lookup(
            "gremlin", f'g.V().hasLabel({typ}).has("id",{lit}).elementMap()'
        ),
        "gremlin_has_label_id": Lookup("gremlin", f'g.V().has({typ},"id",{lit}).elementMap()'),
        "sql_where_id": Lookup("sql", f"SELECT FROM {label} WHERE id = :id", {"id": node_id}),
    }


@dataclass
class SizeResult:
    accounts: int
    #: shape -> milliseconds per lookup, one entry per account looked up
    times: dict[str, list[float]] = field(default_factory=dict)
    #: shape -> why it failed, when it did
    failed: dict[str, str] = field(default_factory=dict)

    def median(self, shape: str) -> float | None:
        values = self.times.get(shape)
        return statistics.median(values) if values else None


class WrongAnswer(Exception):
    """A lookup returned something other than the one account asked for."""


async def time_lookup(client: Any, lookup: Lookup, node_id: str) -> float:
    """Milliseconds for one lookup. It must find exactly the account asked for: a lookup that is
    fast because it found nothing is not a fast lookup."""
    began = time.perf_counter()
    rows = await client.command(lookup.language, lookup.command, params=lookup.params)
    elapsed = (time.perf_counter() - began) * 1000
    if len(rows) != 1 or node_id not in {str(v) for v in _values(rows[0])}:
        raise WrongAnswer(f"{len(rows)} row(s) for {node_id!r}")
    return elapsed


def _values(row: Any) -> list[Any]:
    """Every scalar in a returned element, however the language shapes it."""
    if isinstance(row, dict):
        return [x for v in row.values() for x in _values(v)]
    if isinstance(row, list):
        return [x for v in row for x in _values(v)]
    return [row]


def spread(ids: Sequence[str], count: int) -> list[str]:
    """`count` ids taken evenly across `ids`, so early and late accounts are both looked up."""
    if len(ids) <= count:
        return list(ids)
    return [ids[i * len(ids) // count] for i in range(count)]


async def measure_size(client: Any, label: str, ids: Sequence[str]) -> SizeResult:
    result = SizeResult(accounts=len(ids))
    sample = spread(ids, LOOKUPS)
    for shape in SHAPES:
        times: list[float] = []
        try:
            await time_lookup(client, lookup_shapes(label, sample[0])[shape], sample[0])  # warm-up
            for node_id in sample:
                times.append(
                    await time_lookup(client, lookup_shapes(label, node_id)[shape], node_id)
                )
        except Exception as error:  # reported as a line, never a crash: the point is to find out
            result.failed[shape] = f"{type(error).__name__}: {str(error)[:160]}"
            continue
        result.times[shape] = times
    return result


def table(results: Sequence[SizeResult]) -> list[str]:
    """Median milliseconds per lookup, by accounts and shape, and how each grew."""
    head = f"  {'accounts':>9}  " + "  ".join(f"{s:>20}" for s in SHAPES)
    lines = [head]
    for r in results:
        cells = []
        for shape in SHAPES:
            m = r.median(shape)
            cells.append(f"{'FAILED' if m is None else f'{m:.2f} ms':>20}")
        lines.append(f"  {r.accounts:>9,}  " + "  ".join(cells))
    first, last = results[0], results[-1]
    for shape in SHAPES:
        a, b = first.median(shape), last.median(shape)
        if a is None or b is None:
            lines.append(f"  {shape}: no growth figure (a size failed)")
            continue
        lines.append(
            f"  {shape}: {b / a:.1f} times as slow at {last.accounts:,} accounts as at "
            f"{first.accounts:,}"
        )
    for r in results:
        for shape, why in r.failed.items():
            lines.append(f"  {shape} at {r.accounts:,}: FAILED ({why})")
    return lines


async def index_lines(client: Any, label: str) -> list[str]:
    """What indexes the store holds on the account type, so a lookup that is flat or slow can be
    read against whether an id index exists at all."""
    try:
        rows = await client.sql("SELECT FROM schema:indexes")
    except Exception as error:
        return [f"  could not list indexes ({type(error).__name__}: {str(error)[:120]})"]
    mine = [r for r in rows if str(r.get("typeName", "")) == label]
    if not mine:
        return [f"  no index on {label} (the store lists {len(rows)} in all)"]
    return [
        f"  index {r.get('name')}: properties {r.get('properties')}, unique {r.get('unique')}"
        for r in mine
    ]


async def run(
    sizes: Sequence[int],
    say: Callable[[str], None] = print,
) -> int:
    started = time.perf_counter()
    stamp = datetime.now(UTC).strftime("%H%M%S")
    name = refuse_unless_scratch(f"{SCRATCH_PREFIX}lookup_{stamp}")
    label = groovy_identifier(physical_type_name("Endpoint"))
    nodes, _ = synthetic_writes(int(max(sizes) * 1.4) + 10)
    ids = [n.id for n in nodes]
    if len(ids) < max(sizes):
        say(f"probe: only {len(ids):,} accounts can be made, fewer than {max(sizes):,}")
        return 1
    say(f"probe: lookups at {', '.join(f'{s:,}' for s in sizes)} accounts (scratch database only)")
    sweeper = ArcadeDBClient(
        ArcadeDBConfig.from_env(refuse_unless_scratch(f"{SCRATCH_PREFIX}sweep"))
    )
    try:
        for dropped in await sweep_leftovers(sweeper):
            say(f"probe: dropped {dropped}, left by an earlier run that was interrupted")
    finally:
        await sweeper.aclose()

    client, graph = await _fresh(name, [])
    results: list[SizeResult] = []
    try:
        written = 0
        for size in sorted(sizes):
            while written < size:
                chunk = nodes[written : min(size, written + UPSERT_CHUNK)]
                tx = await graph.begin_transaction()
                await graph.upsert_nodes(chunk, tx)
                await graph.commit_transaction(tx)
                written += len(chunk)
                if written % 1000 < UPSERT_CHUNK:
                    elapsed = int(time.perf_counter() - started)
                    print(
                        f"  ... [{elapsed // 60:02d}:{elapsed % 60:02d}] {written:,} of {size:,} "
                        "accounts written",
                        flush=True,
                    )
            print(f"  ... timing lookups at {size:,} accounts", flush=True)
            results.append(await measure_size(client, label, ids[:size]))
        say("median milliseconds for one lookup of one account by id:")
        for line in table(results):
            say(line)
        say(f"indexes on {label}:")
        for line in await index_lines(client, label):
            say(line)
    finally:
        await client.drop_database_named(refuse_unless_scratch(name))
        await client.aclose()
    say("probe: scratch database dropped. Nothing else was touched.")
    return int(any(r.failed for r in results))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES))
    args = parser.parse_args(argv)
    sizes = [int(s) for s in args.sizes.split(",")]
    return asyncio.run(run(sizes))


if __name__ == "__main__":
    sys.exit(main())
