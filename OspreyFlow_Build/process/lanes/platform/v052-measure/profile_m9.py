"""M9's slow fallback, profiled (the orchestrator, 14 November 2026): with OpenSearch stopped, a
name search answered from the graph in 5.3-5.5 s at 642,460 nodes against the 5 s figure. This times
`GraphPort.search_nodes`' own query (`SearchNodesBuilder`, as `_from_graph` sends it: one past
`FALLBACK_DEPTH`) beside variants that each take one part away, to find what dominates:

- `current`: the query as sent (every identifier and indexed field in one `or()`, no label, the
  access filter, `limit(101)`);
- `no_access`: the same without the access filter's `has` steps;
- `limit_20`: the same with `limit(20)` (the one-past read's cost);
- `count`: how many vertices match the `or()` alone (the matching, with no rows built);
- `by_label`: one `hasLabel(T).has(f, v)` per type and its own fields, unioned, with the access
  filter: the shape a type's index can serve; it leaves out `match_any_field`'s gazetteer guard (a
  request reader matches a gazetteer node on its name alone), so it times the shape and is not
  itself a fix;
- `by_sql`: the shape ADR-124 Amendments 18 and 20 built for the write path and `edges_among`, as a
  fix would build it: one SQL query per type and its own field (`SELECT @rid AS rid FROM <T> WHERE
  <f> = :q`, the value bound, each answered from that type's index), sent together, then Gremlin
  from those record ids with `match_any_field`'s gazetteer guard on the non-name matches and the
  access filter, `dedup().limit(101)` (two Gremlin calls, names and others, merged); timed whole,
  and its ids compared with `current`'s, so a fix of this shape is known to answer the same;
- and the database's own list of indexes, so `by_label` and `by_sql` are read against what is
  indexed.

**Read-only**: no `apply_schema` (`use_schema` sets the ontology in memory), and every query is a
`g.V()` read, a `SELECT @rid` by one indexed field, or `SELECT FROM schema:indexes`. Run on d under
rules' lease, with rules' agreement, after step 4's runs, with the lease's ARCADEDB_* in the
environment:

    cd OspreyFlow_Core && .venv/bin/python \\
        ../OspreyFlow_Build/process/lanes/platform/v052-measure/profile_m9.py \\
        --database <B's database> --repeat 3 "Tomasz Kellly" "Meagan Illiams" ...

It prints one line per query and variant (each repeat's ms, then the median) and writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
sys.path[:0] = [str(CORE), str(CORE / "packages")]

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter  # noqa: E402
from adapters.graph_arcadedb.builders import (  # noqa: E402
    GAZETTEER_MATCH_FIELDS,
    SearchNodesBuilder,
)
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402
from adapters.graph_arcadedb.gremlin_literals import (  # noqa: E402
    groovy_identifier,
    groovy_string_list_literal,
    groovy_string_literal,
)
from adapters.graph_arcadedb.naming import physical_type_name  # noqa: E402
from ontology.handling import load_uk_le_scheme  # noqa: E402
from ontology.packs import load_deployment_ontology  # noqa: E402

from schemas.domain import Principal  # noqa: E402
from schemas.mapconfig import GAZETTEER_DATASET_PREFIX, GAZETTEER_ONLY_IDENTIFIERS  # noqa: E402

#: The fallback's depth plus the one past it that says a cut was made (search_service.py).
ONE_PAST = 101
#: M9's own measuring subject, as rules granted it on d (step4_stack.SUBJECTS' m10-measure).
MEASURE = Principal(
    id="m10-measure",
    clearance="OFFICIAL-SENSITIVE",
    org_unit="unit-intel",
    receivable_handling_codes=["P", "C"],
    datasets=["cs-intel"],
)


def variants(adapter: GraphArcadeDBAdapter, query: str) -> dict[str, str]:
    schema = adapter._require_schema()
    fields = sorted(
        {f for e in schema.entity_types for f in e.identifiers}
        | {p.name for e in schema.entity_types for p in e.properties if p.indexed}
    )
    access = adapter._access
    current = SearchNodesBuilder(tuple(fields), query, limit=ONE_PAST).render_gremlin(
        access, MEASURE
    )
    has_access = access.gremlin_has_step(MEASURE)
    value = groovy_string_literal(query)
    matched = current.removeprefix("g.V().").split(f".{has_access}.")[0]
    pairs = []
    for entity in schema.entity_types:
        own = sorted(set(entity.identifiers) | {p.name for p in entity.properties if p.indexed})
        label = groovy_string_literal(physical_type_name(entity.name))
        pairs += [f"__.V().hasLabel({label}).has({groovy_string_literal(f)},{value})" for f in own]
    return {
        "current": current,
        "no_access": f"g.V().{matched}.dedup().limit({ONE_PAST}).elementMap()",
        "limit_20": current.replace(f".limit({ONE_PAST}).", ".limit(20)."),
        "count": f"g.V().{matched}.count()",
        "by_label": (
            f"g.inject(1).union({','.join(pairs)}).{has_access}.dedup().limit({ONE_PAST})"
            ".elementMap()"
        ),
    }


async def _timed(client: ArcadeDBClient, gremlin: str) -> tuple[float, set[str]]:
    started = time.perf_counter()
    rows = await client.gremlin(gremlin)
    took = (time.perf_counter() - started) * 1000
    # `count` answers one number, not rows: it is shown as `count=<n>`.
    return took, {str(r.get("id")) if isinstance(r, dict) else f"count={r}" for r in rows}


async def _by_sql(adapter: GraphArcadeDBAdapter, query: str) -> tuple[float, set[str]]:
    """`by_sql`, timed whole: the SQL lookups, together, then the two Gremlin calls."""
    client = adapter._client
    schema = adapter._require_schema()
    pairs = [
        (physical_type_name(e.name), f)
        for e in schema.entity_types
        for f in sorted(set(e.identifiers) | {p.name for p in e.properties if p.indexed})
        if f not in GAZETTEER_ONLY_IDENTIFIERS  # MEASURE is a request reader (ADR-147 Am 3)
    ]
    has_access = adapter._access.gremlin_has_step(MEASURE)
    prefix = groovy_string_literal(GAZETTEER_DATASET_PREFIX)
    guard = (
        f'__.not(__.or(__.values("datasets").unfold().is(TextP.startingWith({prefix})),'
        '__.values("provenance").select("gazetteer")))'
    )
    started = time.perf_counter()
    answers = await asyncio.gather(
        *(
            client.sql(
                f"SELECT @rid AS rid FROM `{groovy_identifier(t)}`"
                f" WHERE `{groovy_identifier(f)}` = :q",
                params={"q": query},
            )
            for t, f in pairs
        )
    )
    names: set[str] = set()
    others: set[str] = set()
    for (_t, f), rows in zip(pairs, answers, strict=True):
        (names if f in GAZETTEER_MATCH_FIELDS else others).update(str(r["rid"]) for r in rows)
    others -= names
    tail = f".{has_access}.dedup().limit({ONE_PAST}).elementMap()"
    rows: list[dict[str, object]] = []
    if names:
        rows += await client.gremlin(f"g.V({groovy_string_list_literal(sorted(names))}){tail}")
    if others:
        rows += await client.gremlin(
            f"g.V({groovy_string_list_literal(sorted(others))}).filter({guard}){tail}"
        )
    ids = sorted({str(r.get("id")) for r in rows})[:ONE_PAST]
    return (time.perf_counter() - started) * 1000, set(ids)


async def _run(database: str, repeat: int, queries: list[str]) -> int:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database=database))
    adapter = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    adapter.use_schema(load_deployment_ontology())
    indexes = await client.sql("SELECT name, typeName, properties FROM schema:indexes")
    print(f"indexes ({len(indexes)}):")
    for row in indexes:
        print(f"  {row.get('typeName')} {row.get('properties')} ({row.get('name')})")
    for query in queries:
        timed = {
            name: (lambda g=gremlin: _timed(client, g))
            for name, gremlin in variants(adapter, query).items()
        }
        timed["by_sql"] = lambda q=query: _by_sql(adapter, q)
        current: set[str] | None = None
        for name, run in timed.items():
            try:
                runs = [await run() for _ in range(repeat)]
            except Exception as error:  # a variant the server refuses is reported, not fatal
                print(f"{query!r} {name}: refused ({type(error).__name__}: {error})")
                continue
            ms = [round(t) for t, _ids in runs]
            ids = runs[-1][1]
            current = ids if name == "current" else current
            same = (
                ""
                if name in ("current", "count") or current is None
                else (f", ids {'the same as' if ids == current else 'NOT the same as'} current's")
            )
            shown = next(iter(ids)) if name == "count" and ids else f"rows {len(ids)}"
            print(f"{query!r} {name}: {ms} ms, median {statistics.median(ms):.0f} ms, "
                  f"{shown}{same}")  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", default="ospreyflow")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("queries", nargs="+")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.database, args.repeat, args.queries))


if __name__ == "__main__":
    raise SystemExit(main())
