"""ADR-124 Amendment 21's equivalence case, live on stack d (the orchestrator's ruling, 14 November
2026): `search_nodes` as built (`g.V().<match_any_field's or()>.<access>.dedup().limit(101)`,
main's text word for word) beside the new one (`GraphArcadeDBAdapter.search_nodes`, candidates by
SQL first), over step 4's own queries and queries drawn from B that are known to match, as several
readers. Every query must give the same set of node ids and the same `more` (the 101st row, as
`search_service._from_graph` asks one past `FALLBACK_DEPTH`) both ways. Read-only: Gremlin reads,
`SELECT @rid` lookups by one field, and `schema:types`.

The queries:
- step 4's first 100 `names` rows (M3: typos, variants, sound-alikes; mostly matching nothing, since
  an exact search compares one property, and the count says so) and its 200 `exact` rows (M5);
- 200 drawn from B's files by `--seed`, each a value a node holds in a searchable field, across
  every field B fills (family names, identifiers, numbers, place and organisation names), so the
  set cannot pass by matching nothing.

The readers: a request reader of the twelve client-size datasets (OFFICIAL-SENSITIVE, P C,
unit-intel), a restricted one (OFFICIAL, P, unit-records, three datasets) on every query, and an
unlimited principal (`datasets` None, which matches the gazetteer-only identifiers too, SECRET,
P C R) on the 200 known to match. Two queries are sent at a time.

    cd OspreyFlow_Core && .venv/bin/python \\
        ../OspreyFlow_Build/process/lanes/rules/adr124-am21/equivalence.py \\
        --from ~/osprey-load/b-1.0 --queries ~/osprey-load/step4/queries.jsonl \\
        --out ~/osprey-load/am21/equivalence.jsonl

It prints one line per difference and a summary, and writes every comparison to `--out`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
sys.path[:0] = [str(CORE), str(CORE / "packages")]

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter  # noqa: E402
from adapters.graph_arcadedb.builders import match_any_field  # noqa: E402
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig  # noqa: E402
from adapters.graph_arcadedb.gremlin_literals import groovy_string_literal  # noqa: E402
from ontology.handling import load_uk_le_scheme  # noqa: E402
from ontology.packs import load_deployment_ontology  # noqa: E402

from schemas.domain import Principal  # noqa: E402

ONE_PAST = 101
DATASETS = [
    "cs-nominals", "cs-custody", "cs-companies", "cs-subscribers", "cs-calls", "cs-cells",
    "cs-transactions", "cs-sars", "cs-intel", "cs-casefiles", "cs-covert", "cs-watchlist",
]  # fmt: skip
READERS = {
    "request": Principal(id="am21-request", clearance="OFFICIAL-SENSITIVE", org_unit="unit-intel",
                         receivable_handling_codes=["P", "C"], datasets=DATASETS),
    "restricted": Principal(id="am21-restricted", clearance="OFFICIAL", org_unit="unit-records",
                            receivable_handling_codes=["P"],
                            datasets=["cs-nominals", "cs-companies", "cs-intel"]),
    "unlimited": Principal(id="am21-unlimited", clearance="SECRET", org_unit="unit-intel",
                           receivable_handling_codes=["P", "C", "R"], datasets=None),
}  # fmt: skip
#: (type, field, how many) drawn from B: every searchable field B fills, 200 in all.
DRAWN = [
    ("Person", "family_name", 30), ("Person", "nino", 20), ("Person", "pnc_id", 15),
    ("Person", "prison_number", 10), ("Endpoint", "e164", 20), ("Endpoint", "value_normalised", 20),
    ("Location", "name", 20), ("Location", "postcode", 15), ("Location", "site_ref", 10),
    ("Organisation", "name", 20), ("Organisation", "org_ref", 10), ("Device", "imei", 10),
]  # fmt: skip


def drawn(folder: Path, seed: int) -> list[dict[str, str]]:
    """Values B's nodes hold, by type and field, chosen by a hash of the seed and the value."""
    want = {(t, f): n for t, f, n in DRAWN}
    seen: dict[tuple[str, str], set[str]] = {k: set() for k in want}
    for path in sorted(folder.glob("*/*.nodes.jsonl")):
        with path.open(encoding="utf-8") as rows:
            for line in rows:
                row = json.loads(line)
                for (t, f), values in seen.items():
                    value = row["props"].get(f) if row["type"] == t else None
                    if isinstance(value, str) and value:
                        values.add(value)
    out = []
    for (t, f), n in want.items():
        ranked = sorted(seen[(t, f)], key=lambda v: hashlib.sha256(f"{seed}:{v}".encode()).digest())
        out += [{"set": "drawn", "field": f"{t}.{f}", "query": v} for v in ranked[:n]]
    return out


def step4(path: Path) -> list[dict[str, str]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    names = [r for r in rows if r["class"] == "names"][:100]
    exact = [r for r in rows if r["class"] == "exact"][:200]
    return [{"set": f"step4-{r['class']}", "field": "", "query": r["query"]} for r in names + exact]


#: Past the fallback's depth, each answer is some 101 of the matches, chosen by where the query
#: starts: both are then asked for every match, and the whole sets compared.
EVERY = 100_000


def old_query(
    adapter: GraphArcadeDBAdapter, query: str, principal: Principal, limit: int = ONE_PAST
) -> str:
    """Main's `SearchNodesBuilder` before Amendment 21, word for word, at the fallback's depth."""
    schema = adapter._require_schema()
    fields = sorted(
        {f for e in schema.entity_types for f in e.identifiers}
        | {p.name for e in schema.entity_types for p in e.properties if p.indexed}
    )
    value = groovy_string_literal(query)
    matched = match_any_field(
        lambda field: f"__.has({groovy_string_literal(field)},{value})", tuple(fields), principal
    )
    has_access = adapter._access.gremlin_has_step(principal)
    return f"g.V().{matched}.{has_access}.dedup().limit({limit}).elementMap()"


async def compare(
    adapter: GraphArcadeDBAdapter, client: ArcadeDBClient, q: dict[str, str], reader: str
) -> dict[str, Any]:
    principal = READERS[reader]
    started = time.perf_counter()
    old_rows = await client.gremlin(old_query(adapter, q["query"], principal))
    old_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    new_nodes = await adapter.search_nodes(q["query"], principal, limit=ONE_PAST)
    new_ms = (time.perf_counter() - started) * 1000
    old_ids = sorted({str(r["id"]) for r in old_rows})
    new_ids = sorted(n.id for n in new_nodes)
    old_more, new_more = len(old_ids) > ONE_PAST - 1, len(new_ids) > ONE_PAST - 1
    if old_more or new_more:
        every_old = await client.gremlin(old_query(adapter, q["query"], principal, EVERY))
        every_new = await adapter.search_nodes(q["query"], principal, limit=EVERY)
        whole = sorted({str(r["id"]) for r in every_old}) == sorted(n.id for n in every_new)
        same = whole and old_more == new_more
    else:
        same = old_ids == new_ids
    return {
        **q, "reader": reader, "old": len(old_ids), "new": len(new_ids),
        "old_more": old_more, "new_more": new_more, "same": same,
        "only_old": [i for i in old_ids if i not in set(new_ids)][:10],
        "only_new": [i for i in new_ids if i not in set(old_ids)][:10],
        "old_ms": round(old_ms), "new_ms": round(new_ms),
    }  # fmt: skip


async def run(args: argparse.Namespace) -> int:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database=args.database))
    adapter = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    adapter.use_schema(load_deployment_ontology())
    asked = step4(args.queries)
    matching = drawn(args.folder, args.seed)
    work = [(q, r) for q in [*asked, *matching] for r in ("request", "restricted")]
    work += [(q, "unlimited") for q in matching]
    print(f"am21 equivalence: {len(asked)} of step 4's, {len(matching)} drawn (seed {args.seed}), "
          f"{len(work)} comparisons, two at a time", flush=True)  # fmt: skip
    gate = asyncio.Semaphore(2)
    done: list[dict[str, Any]] = []
    args.out.parent.mkdir(parents=True, exist_ok=True)

    async def one(q: dict[str, str], reader: str) -> None:
        async with gate:
            result = await compare(adapter, client, q, reader)
        done.append(result)
        if not result["same"]:
            print(f"DIFFERENT {json.dumps(result, sort_keys=True)}", flush=True)
        if len(done) % 100 == 0:
            print(f"  {len(done)} of {len(work)}", flush=True)

    try:
        await asyncio.gather(*(one(q, r) for q, r in work))
    finally:
        await client.aclose()
    with args.out.open("w", encoding="utf-8") as f:
        for row in done:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    differ = [r for r in done if not r["same"]]
    for group in sorted({(r["set"], r["reader"]) for r in done}):
        rows = [r for r in done if (r["set"], r["reader"]) == group]
        hit = sum(1 for r in rows if r["old"] > 0)
        olds = sorted(r["old_ms"] for r in rows)
        news = sorted(r["new_ms"] for r in rows)
        print(f"{group[0]:14} {group[1]:10} n={len(rows):3} matched>=1: {hit:3} "
              f"more: {sum(r['old_more'] for r in rows)} same: {sum(r['same'] for r in rows):3} "
              f"old p50 {olds[len(olds)//2]} ms, new p50 {news[len(news)//2]} ms "
              f"p95 {news[int(len(news)*0.95)-1]} ms")  # fmt: skip
    print(f"am21 equivalence: {len(done) - len(differ)} of {len(done)} the same, "
          f"{len(differ)} different")  # fmt: skip
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
