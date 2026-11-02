"""Seeds the `cyber-intrusion` demo pack (`06_DECISIONS.md` ADR-138) into a running deployment's
graph.

    PYTHONPATH=.:packages python -m scripts.seed_cyber_intrusion --case-name "…" [--grant a=level]
    (or: ospreyflow demo add cyber-intrusion)

Writes the graph `demo_fixtures.cyber_intrusion.graph()` makes from its STIX 2.1 bundle — a threat
actor, a campaign, a backdoor, two command-and-control servers, the indicators and the observed
traffic — into the dataset `cyber-intrusion` (ADR-099), and makes its case, whose `domains` are
`stix` (ADR-126) unless the install gives a starter's. Run inside the deployment's network by
`scripts.seed_internal`, as every seed is. Running it twice changes nothing: every id is fixed, and
the store merges a write of an element it holds.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import cast

from scripts.case_seed import add_case_arguments, check_case_arguments, scope_for
from services.api.dataset_scope import stamping

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import now_utc
from demo_fixtures import cyber_intrusion
from demo_fixtures.datasets import CYBER_INTRUSION
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.graph import GraphPort
from schemas.domain import Edge, EdgeWrite, Node, NodeWrite, Principal

_CREATED_BY = "cyber-intrusion-seed-worker"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_cyber_intrusion",
        description="Seeds the synthetic STIX 2.1 cyber intrusion (ADR-138) into its own case.",
    )
    add_case_arguments(parser)
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", _CREATED_BY)
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    args = parser.parse_args(argv)
    check_case_arguments(parser, args)
    return args


def node_writes(load_id: str) -> list[NodeWrite]:
    return [_node_write(node, load_id) for node in cyber_intrusion.graph().nodes]


def edge_writes(load_id: str) -> list[EdgeWrite]:
    return [_edge_write(edge, load_id) for edge in cyber_intrusion.graph().edges]


def _node_write(node: Node, load_id: str) -> NodeWrite:
    return NodeWrite(
        id=node.id, type=node.type, properties=node.properties, provenance=node.provenance,
        handling=node.handling, created_by=_CREATED_BY, created_at=now_utc(), load_id=load_id,
    )  # fmt: skip


def _edge_write(edge: Edge, load_id: str) -> EdgeWrite:
    return EdgeWrite(
        id=edge.id, type=edge.type, source=edge.source, target=edge.target,
        properties=edge.properties, interval=edge.interval, provenance=edge.provenance,
        handling=edge.handling, created_by=_CREATED_BY, created_at=now_utc(), load_id=load_id,
    )  # fmt: skip


async def _run(args: argparse.Namespace) -> int:
    scheme = load_uk_le_scheme()
    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = cast(
        GraphPort,
        stamping(GraphArcadeDBAdapter(client, scheme), dataset=CYBER_INTRUSION.id),
    )
    try:
        await graph.apply_schema(load_deployment_ontology())
        principal = Principal(
            id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit
        )
        scope = await scope_for(args, seeder=principal, dataset=CYBER_INTRUSION)
        load_id = f"cyber-intrusion:{scope}"
        nodes, edges = node_writes(load_id), edge_writes(load_id)
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(nodes, tx)
        await graph.upsert_edges(edges, tx)
        await graph.commit_transaction(tx)
    finally:
        await client.aclose()
    print(
        f"Seeded the cyber intrusion: {len(nodes)} nodes and {len(edges)} links from a STIX 2.1 "
        f"bundle of {len(cyber_intrusion.stix_objects())} objects."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
