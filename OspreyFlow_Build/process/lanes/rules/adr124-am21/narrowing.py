"""ADR-124 Amendment 21's candidate fields narrowed to each type's flattened ones, shown to answer
as the widened version did, live on stack d, over the same 1,200 comparisons `equivalence.py` ran
(the orchestrator's ruling, 14 November 2026). The widened version (every field a type declares)
equalled the query as built in all 1,200 (run 20261114T175011Z onwards, `equivalence.widened.jsonl`),
so the narrowed one equalling the widened one in all 1,200 makes it equal the query as built too.
Each comparison is of the whole set of matches (`limit` 100,000) and `more` at the fallback's depth.
Read-only: `SELECT @rid` lookups by one field, Gremlin reads and `schema:types`.

    cd OspreyFlow_Core && .venv/bin/python \\
        ../OspreyFlow_Build/process/lanes/rules/adr124-am21/narrowing.py \\
        --from ~/osprey-load/b-1.0 --queries ~/osprey-load/step4/queries.jsonl \\
        --out ~/osprey-load/am21/narrowing.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]

import equivalence as eq  # noqa: E402

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter  # noqa: E402
from adapters.graph_arcadedb.builders import render_field_record_id_lookup_sql  # noqa: E402
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402
from adapters.graph_arcadedb.naming import physical_type_name  # noqa: E402
from ontology.handling import load_uk_le_scheme  # noqa: E402
from ontology.packs import load_deployment_ontology  # noqa: E402
from schemas.mapconfig import GAZETTEER_ONLY_IDENTIFIERS  # noqa: E402


class Widened(GraphArcadeDBAdapter):
    """`_search_candidates` as first built: every field a type declares, flattened or not."""

    async def _search_candidates(self, schema, identifier_fields, query, principal):  # type: ignore[no-untyped-def]
        asked = set(identifier_fields)
        if principal.datasets is not None:
            asked -= set(GAZETTEER_ONLY_IDENTIFIERS)
        stored = set(await self._types_with_unique_id("vertex"))
        pairs = [
            (physical_type_name(e.name), f)
            for e in schema.entity_types
            if physical_type_name(e.name) in stored
            for f in sorted(asked & ({p.name for p in e.properties} | set(e.identifiers)))
        ]
        found = await asyncio.gather(*(
            self._client.sql(render_field_record_id_lookup_sql(t, f), params={"value": query})
            for t, f in pairs
        ))  # fmt: skip
        return sorted({str(r["rid"]) for rows in found for r in rows})


async def run(args: argparse.Namespace) -> int:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database=args.database))
    narrowed = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    widened = Widened(client, load_uk_le_scheme())
    for adapter in (narrowed, widened):
        adapter.use_schema(load_deployment_ontology())
    asked, matching = eq.step4(args.queries), eq.drawn(args.folder, args.seed)
    work = [(q, r) for q in [*asked, *matching] for r in ("request", "restricted")]
    work += [(q, "unlimited") for q in matching]
    print(f"am21 narrowing: {len(work)} comparisons, narrowed against widened", flush=True)
    done: list[dict[str, Any]] = []
    try:
        for q, reader in work:
            principal = eq.READERS[reader]
            a = sorted(
                n.id for n in await narrowed.search_nodes(q["query"], principal, limit=eq.EVERY)
            )
            b = sorted(
                n.id for n in await widened.search_nodes(q["query"], principal, limit=eq.EVERY)
            )
            row = {**q, "reader": reader, "narrowed": len(a), "widened": len(b), "same": a == b,
                   "more": len(a) > eq.ONE_PAST - 1}  # fmt: skip
            done.append(row)
            if not row["same"]:
                print(f"DIFFERENT {json.dumps(row, sort_keys=True)}", flush=True)
    finally:
        await client.aclose()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in done), encoding="utf-8"
    )
    hit = sum(1 for r in done if r["narrowed"] > 0)
    differ = sum(1 for r in done if not r["same"])
    print(f"am21 narrowing: {len(done) - differ} of {len(done)} the same, {differ} different; "
          f"{hit} matched at least one node, {sum(r['more'] for r in done)} past the depth")  # fmt: skip
    return 1 if differ else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="folder", required=True, type=Path)
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--database", default="ospreyflow")
    parser.add_argument("--seed", type=int, default=21)
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
