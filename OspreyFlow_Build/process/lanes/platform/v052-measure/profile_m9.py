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
- and the database's own list of indexes, so `by_label` is read against what is indexed.

**Read-only**: no `apply_schema` (`use_schema` sets the ontology in memory), and every query is a
`g.V()` read or `SELECT FROM schema:indexes`. Run on d under rules' lease, with rules' agreement,
after step 4's runs, with the lease's ARCADEDB_* in the environment:

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
from adapters.graph_arcadedb.builders import SearchNodesBuilder  # noqa: E402
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402
from adapters.graph_arcadedb.gremlin_literals import groovy_string_literal  # noqa: E402
from adapters.graph_arcadedb.naming import physical_type_name  # noqa: E402
from ontology.handling import load_uk_le_scheme  # noqa: E402
from ontology.packs import load_deployment_ontology  # noqa: E402

from schemas.domain import Principal  # noqa: E402

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


async def _timed(client: ArcadeDBClient, gremlin: str) -> tuple[float, int]:
    started = time.perf_counter()
    rows = await client.gremlin(gremlin)
    return (time.perf_counter() - started) * 1000, len(rows)


async def _run(database: str, repeat: int, queries: list[str]) -> int:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database=database))
    adapter = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    adapter.use_schema(load_deployment_ontology())
    indexes = await client.sql("SELECT name, typeName, properties FROM schema:indexes")
    print(f"indexes ({len(indexes)}):")
    for row in indexes:
        print(f"  {row.get('typeName')} {row.get('properties')} ({row.get('name')})")
    for query in queries:
        for name, gremlin in variants(adapter, query).items():
            try:
                runs = [await _timed(client, gremlin) for _ in range(repeat)]
            except Exception as error:  # a variant the server refuses is reported, not fatal
                print(f"{query!r} {name}: refused ({type(error).__name__}: {error})")
                continue
            ms = [round(t) for t, _n in runs]
            print(f"{query!r} {name}: {ms} ms, median {statistics.median(ms):.0f} ms, "
                  f"rows {runs[-1][1]}")  # fmt: skip
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
