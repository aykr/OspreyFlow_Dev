"""Why step 4's search pages took about 860 ms p50 when one page now takes about 100 ms (the owner's
question; the orchestrator, 14 November 2026: "explain the gap with a measurement, not a guess").
The same sends as step 4's M5, `exact`, 20 discarded and 200 timed, one after another, as
`measure_search.measure` sends them (its own `_request` and `_send`), each send's time kept, in
three arms run by the step 4 runner, so each candidate is measured:

- **A, today's tree at the poc's limits** (the Conduit at 2 CPUs and 4 GB, as step 4 ran);
- **B, today's tree without them** (`STEP4_NO_LIMITS=1`): what the CPU cap accounts for;
- **D, step 4's own tree (8ba5ed6) at the poc's limits**: whether the code then accounts for it.
  Its runner builds the Conduit from that tree; this script is run from today's, `--wire-only`.

Within each arm the times are shown by place in the run (sends 1–20, 21–100, 101–200), so warm-up
shows; the sends are one at a time, so no request queues behind another, and "in sequence" is the
shape of every arm alike. In arm A it also times, in process against d's stores, the one graph read
that differs between the trees: the merge's `edges_among` among a page's hits (ADR-124 Amendment
20, 3c96ba7, not in step 4's tree), today's (`GraphArcadeDBAdapter.edges_among`) beside the query
step 4's tree sent (`render_edges_among_gremlin` as at e684ef1, below word for word), for the
first 20 pages' own hits as m10-measure.

**Read-only**: searches over the wire (each writes its own audit row, as M5 did) and Gremlin reads.
Run on d under rules' lease, with rules' agreement, from `OspreyFlow_Core`, each arm in the runner:

    A: .venv/bin/python ../OspreyFlow_Build/process/lanes/platform/v052-measure/step4_stack.py \\
         --case <the case> -- .venv/bin/python ../OspreyFlow_Build/process/lanes/platform/\\
         v052-measure/profile_gap.py --arm A --database <B's database> --queries <queries.jsonl>
    B: the same with STEP4_NO_LIMITS=1 in the environment and --arm B --wire-only
    D: from a checkout of 8ba5ed6, its own step4_stack.py, the command this file in today's tree
       with --arm D --wire-only

It prints each arm's figures, and writes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
sys.path[:0] = [str(CORE), str(CORE / "packages")]

from scripts import measure_search  # noqa: E402

#: As step 4's run sent M5 (`tests/perf/test_search_budget_live.py`: 20 discarded, 200 timed).
WARMUP, N = 20, 200
#: The pages whose hits the in-process comparison asks about.
PAGES = 20


def _percentile(values: list[float], share: float) -> float:
    return measure_search._percentile(values, share)


def wire(base: str, case: str, token: str, queries: list[dict[str, Any]]) -> dict[str, Any]:
    """M5's sends, as `measure_search.measure` makes them, each send's time and its page's ids."""
    mine = [q for q in queries if q["class"] == "exact"]
    if not mine:
        raise SystemExit("profile_gap: the queries have no exact row")
    times: list[float] = []
    pages: list[list[str]] = []
    for i in range(WARMUP + N):
        path, body = measure_search._request(case, mine[i % len(mine)])
        ms, answer, error = measure_search._send(base, path, body, token)
        if answer is None:
            raise SystemExit(f"profile_gap: send {i + 1} answered {error}")
        if i < WARMUP:
            continue
        times.append(ms)
        if len(pages) < PAGES:
            pages.append([n["id"] for n in answer.get("nodes", [])])
    return {"times": times, "pages": pages}


def say_wire(arm: str, times: list[float]) -> None:
    print(f"arm {arm}, over the wire, exact, {len(times)} sends after {WARMUP} discarded: "
          f"p50 {_percentile(times, 0.5):.1f} ms, p95 {_percentile(times, 0.95):.1f}, "
          f"max {max(times):.1f}")  # fmt: skip
    for lo, hi in ((0, 20), (20, 100), (100, 200)):
        part = times[lo:hi]
        if part:
            print(f"  sends {lo + 1}-{lo + len(part)}: median {statistics.median(part):.1f} ms")


def old_edges_among(node_ids: list[str], has_access: str) -> str:
    """`render_edges_among_gremlin` as at e684ef1 (step 4's tree), with no edge types given and
    the merge's two (`SAME_AS`, `NOT_SAME_AS`) as `_matches` asks: word for word but the labels,
    which the caller passes."""
    from adapters.graph_arcadedb.gremlin_literals import (
        groovy_args_literal,
        groovy_string_list_literal,
    )
    from adapters.graph_arcadedb.naming import physical_edge_labels

    ids = groovy_string_list_literal(sorted(set(node_ids)))
    physical = [label for t in ("SAME_AS", "NOT_SAME_AS") for label in physical_edge_labels(t)]
    label_filter = f".hasLabel({groovy_args_literal(physical)})"
    return (
        f'g.V().has("id",within({ids})).{has_access}'
        f".outE(){label_filter}.{has_access}"
        f'.where(inV().has("id",within({ids})).{has_access})'
        ".dedup().elementMap()"
    )


async def in_process(database: str, pages: list[list[str]]) -> None:
    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme
    from ontology.packs import load_deployment_ontology

    from schemas.domain import Principal

    measure = Principal(
        id="m10-measure", clearance="OFFICIAL-SENSITIVE", org_unit="unit-intel",
        receivable_handling_codes=["P", "C"], datasets=["cs-intel"],
    )  # fmt: skip
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database=database))
    adapter = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    adapter.use_schema(load_deployment_ontology())
    has_access = adapter._access.gremlin_has_step(measure)
    asked = [p for p in pages if len(set(p)) >= 2]  # the merge asks only of two or more
    per_page = statistics.median([len(p) for p in asked]) if asked else 0
    print(f"in process, the merge's edges_among for {len(asked)} pages' hits "
          f"({per_page:g} ids a page):")  # fmt: skip
    for name, run in (
        ("today's (ADR-124 Am 20)", lambda p: adapter.edges_among(
            p, measure, edge_types=["SAME_AS", "NOT_SAME_AS"])),
        ("step 4's tree (e684ef1)", lambda p: client.gremlin(old_edges_among(p, has_access))),
    ):  # fmt: skip
        times = []
        links = 0
        for page in asked:
            started = time.perf_counter()
            found = await run(page)
            times.append((time.perf_counter() - started) * 1000)
            links += len(found)
        print(f"  {name}: median {statistics.median(times):.1f} ms, max {max(times):.1f}, "
              f"{links} links in all")  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", required=True, choices=["A", "B", "D"])
    parser.add_argument("--database", default="ospreyflow")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--wire-only", action="store_true")
    args = parser.parse_args(argv)
    base, case = os.environ["OSPREY_MEASURE_BASE"], os.environ["OSPREY_MEASURE_CASE"]
    rows = [json.loads(line) for line in args.queries.read_text(encoding="utf-8").splitlines()
            if line.strip()]  # fmt: skip
    print(f"arm {args.arm}: STEP4_NO_LIMITS={os.environ.get('STEP4_NO_LIMITS', '')!r}")
    found = wire(base, case, os.environ["OSPREY_MEASURE_TOKEN"], rows)
    say_wire(args.arm, found["times"])
    if not args.wire_only:
        asyncio.run(in_process(args.database, found["pages"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
