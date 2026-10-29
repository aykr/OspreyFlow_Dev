"""Seeds the Prison Intelligence Dataset's scale cohort into a running deployment (ADR-127
Amendment 40, "the scale cohort is seeded by the plan writer, as its own pack").

    ospreyflow demo add prison-intelligence-scale

Directly runnable, as `PYTHONPATH=.:packages python -m scripts.seed_pid_scale --case-name NAME`,
and run through `scripts.seed_internal` with the bulk loader and the Conduit stopped, as for any
seed.

**What it writes.** `pid_writes.writes(build_plan("scale"), "seed",
dataset="prison-intelligence-scale", ...)` through the dataset-stamping adapter: 3,000 prisoners,
exactly 30,000 links, 7,176 nodes. The case it makes reads that dataset alone, carries the NIEM
pack (`datasets.PID_SCALE`) and is shared with the demo accounts as every seeded case is. The scale
plan has no calls, reports, pictures or analytics events, so there is no analytics file to open.

**What it gives up.** The writes create no load record, so the rehearsal reset does not touch the
scale case and Data feeds do not list it. Before writing, the seed counts what the scale dataset
holds: the whole cohort means a second run, which says so and writes nothing; none means a first
run; anything between means a run stopped part-way, and it refuses, since writing again would merge
the stored links a second time. Removing the case's data needs a fresh deployment, as for the other
directly written packs.

**The paste list.** `python -m scripts.write_pid_files --out DIR --profile scale` writes the 3,000
prisoners' numbers as `scale_cohort_list.txt`, for Add many from a list (under its 5,000 cap).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from scripts.case_seed import add_case_arguments, check_case_arguments, scope_for
from scripts.seed_support import write_graph
from services.api.dataset_scope import stamping

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from demo_fixtures import pid_plan, pid_writes
from demo_fixtures.datasets import PID_SCALE
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.graph import GraphPort
from schemas.domain import EdgeWrite, NodeWrite, Principal

#: Nodes per transaction. The same as the other directly written seeds (ArcadeDB fails larger ones
#: with "Error in execution in lock"); the edges go in bulk, in `BULK_CHUNK`s.
_GRAPH_CHUNK = 40


class PartialCohort(RuntimeError):
    """The store holds part of the cohort: a run stopped part-way."""


@dataclass(frozen=True)
class SeedResult:
    """What one run wrote; `already_here` is a run that found the cohort stored, so wrote none."""

    nodes: int
    links: int
    already_here: bool


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_pid_scale",
        description=(
            "Seeds the Prison Intelligence Dataset's scale cohort (3,000 prisoners, 30,000 "
            "links, six establishments) into a real Conduit's graph, under a case that reads "
            "only that dataset."
        ),
    )
    add_case_arguments(parser)
    parser.add_argument(
        "--method",
        choices=("upsert", "bulk"),
        default="bulk",
        help=(
            "How the graph links are written (ADR-058). 'bulk' (the default) writes them in "
            "chunks through the adapter's bulk loader; 'upsert' is the older, slower path."
        ),
    )
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "pid-scale-seed-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    args = parser.parse_args(argv)
    check_case_arguments(parser, args)
    return args


def scale_writes(created_at: datetime) -> tuple[list[NodeWrite], list[EdgeWrite]]:
    """Every node and link of the scale plan, in the scale dataset alone."""
    return pid_writes.writes(
        pid_plan.build_plan("scale"), "seed", dataset=PID_SCALE.id, created_at=created_at
    )


async def stored(graph: GraphPort, principal: Principal) -> tuple[int, int]:
    """(nodes, links) the scale dataset holds, counted in the store as a reader of that dataset
    alone, so another pack's elements are never taken for the cohort."""
    reader = principal.model_copy(update={"datasets": [PID_SCALE.id]})
    counts = await graph.type_counts(reader)
    return sum(counts.nodes.values()), sum(counts.edges.values())


async def seed_scale(
    graph: GraphPort, principal: Principal, *, created_at: datetime, method: str = "bulk"
) -> SeedResult:
    """Writes the scale cohort through `graph` (which must stamp the scale dataset). With the whole
    cohort already stored it says so and writes nothing; with part of it, it refuses."""
    nodes, edges = scale_writes(created_at)
    held = await stored(graph, principal)
    if held == (len(nodes), len(edges)):
        print("The scale cohort is already here; nothing was written.")
        return SeedResult(nodes=0, links=0, already_here=True)
    if held != (0, 0):
        raise PartialCohort(
            f"The store holds part of the scale cohort ({held[0]:,} of {len(nodes):,} nodes and "
            f"{held[1]:,} of {len(edges):,} links): a run stopped part-way. Writing again would "
            "merge the stored links a second time, so nothing was written; the cohort needs a "
            "fresh deployment."
        )
    await write_graph(
        graph, nodes, edges, chunk=_GRAPH_CHUNK, nouns=("nodes", "links"), method=method
    )
    return SeedResult(nodes=len(nodes), links=len(edges), already_here=False)


async def _run(args: argparse.Namespace) -> int:
    # The NIEM pack's types (custody, incidents) are in the deployment's ontology, as the other
    # seeds apply it.
    ontology = load_deployment_ontology()
    scheme = load_uk_le_scheme()

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)
    try:
        await client.create_database_if_absent()
        graph = cast(
            GraphPort, stamping(GraphArcadeDBAdapter(client, scheme), dataset=PID_SCALE.id)
        )
        await graph.apply_schema(ontology)
        await scope_for(args, seeder=principal, dataset=PID_SCALE)
        result = await seed_scale(
            graph, principal, created_at=datetime.now(UTC), method=args.method
        )
    finally:
        await client.aclose()

    if not result.already_here:
        print(f"Seeded {result.nodes:,} nodes and {result.links:,} links into the graph.")
    print(
        "For the paste list: python -m scripts.write_pid_files --out DIR --profile scale "
        "writes scale_cohort_list.txt (3,000 prison numbers, for Add many from a list)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
