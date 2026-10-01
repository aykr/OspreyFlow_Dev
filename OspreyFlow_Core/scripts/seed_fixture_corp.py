"""Seeds a real, running Conduit's ArcadeDB with Fixture Corp (R24) — `06_DECISIONS.md` ADR-035
§C5, Phase 8 Stage 4a. Fixture Corp is the `shipped`-class demo an analyst review runs against
(ADR-035 §C1), so this is the concrete mechanism that makes it loadable into a live Glass session,
the same role `seed_hmp_fixture.py` plays for Scenario A.

**No `osprey` CLI** (`CLAUDE.md`'s own Conventions) — a plain, directly-runnable script, the shape
an eventual `osprey seed --fixture fixture-corp` would wrap. `python -m scripts.seed_fixture_corp`
from the repo root, with `PYTHONPATH=.:packages` set (neither `pytest`'s own `pythonpath =
["packages"]` nor a bare `python -m` invocation puts the repo root and `packages/` on `sys.path`
by itself — the same note `seed_hmp_fixture.py` already carries).

Writes three independent sub-fixtures from `packages/demo_fixtures/fixture_corp.py` into one
real `GraphPort`, under the given `--investigation-scope`:

- The four resolution `Person` pairs, plus the real `SAME_AS` edges Splink computes over them —
  so an analyst opening the demo sees ADR-035 §C5's own "visibly different projections" the
  moment they move the resolution threshold, without first having to trigger a corpus-wide
  resolution run by hand.
- The three community rings — visible as Louvain community hulls the moment the metrics panel's
  community-detection view is opened.
- The path-spoke hub, for the pathfinder to walk end to end (B21,
  `08_ACCEPTANCE_SCENARIOS.md`).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from scripts.case_seed import add_case_arguments, check_case_arguments, scope_for
from scripts.seed_support import KNOWN_STRAY_ADVICE, report_ids_stored_twice
from services.resolve.same_as_writer import write_same_as_edges

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from conduit_common.identity import now_utc
from demo_fixtures.fixture_corp import (
    build_path_spokes,
    generate_community_rings,
    generate_resolution_persons,
)
from demo_fixtures.fixture_corp_resolution import resolve_fixture_corp_pairs
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import GraphPort
from schemas.domain import Edge, EdgeWrite, Node, NodeWrite, Principal

_CREATED_BY = "fixture-corp-seed-worker"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_fixture_corp",
        description=(
            "Seeds Fixture Corp (R24, 06_DECISIONS.md ADR-035 §C5) into a real Conduit's "
            "ArcadeDB, under a real investigation's scope."
        ),
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


def _node_write(node: Node, *, load_id: str) -> NodeWrite:
    return NodeWrite(
        id=node.id,
        type=node.type,
        properties=node.properties,
        provenance=node.provenance,
        handling=node.handling,
        created_by=_CREATED_BY,
        created_at=now_utc(),
        load_id=load_id,
    )


def _edge_write(edge: Edge, *, load_id: str) -> EdgeWrite:
    return EdgeWrite(
        id=edge.id,
        type=edge.type,
        source=edge.source,
        target=edge.target,
        properties=edge.properties,
        provenance=edge.provenance,
        handling=edge.handling,
        created_by=_CREATED_BY,
        created_at=now_utc(),
        load_id=load_id,
    )


async def _seed_resolution_persons(graph: GraphPort, *, load_id: str) -> tuple[int, int]:
    pairs = generate_resolution_persons()
    person_nodes = [p.node_a for p in pairs] + [p.node_b for p in pairs]
    scheme = load_uk_le_scheme()

    # One resolution pass, shared with `test_fixture_corp_shape.py` — see
    # `fixture_corp_resolution.py`'s own docstring. Assembling this call here a second time is
    # exactly how the seed and the test could come to measure different populations without
    # anything failing.
    candidates = resolve_fixture_corp_pairs()
    nodes_by_id = {n.id: n for n in person_nodes}

    tx = await graph.begin_transaction()
    await graph.upsert_nodes([_node_write(n, load_id=load_id) for n in person_nodes], tx)
    edge_ids = await write_same_as_edges(
        graph, candidates, nodes_by_id, created_by=_CREATED_BY, tx=tx, scheme=scheme
    )
    await graph.commit_transaction(tx)
    return len(person_nodes), len(edge_ids)


async def _seed_community_rings(graph: GraphPort, *, load_id: str) -> tuple[int, int]:
    result = generate_community_rings()
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([_node_write(n, load_id=load_id) for n in result.nodes], tx)
    await graph.upsert_edges([_edge_write(e, load_id=load_id) for e in result.edges], tx)
    await graph.commit_transaction(tx)
    return len(result.nodes), len(result.edges)


async def _run(args: argparse.Namespace) -> int:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, scheme)
    await graph.apply_schema(ontology)

    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)
    scope = await scope_for(args, seeder=principal)
    load_id = f"fixture-corp:{scope}"
    try:
        resolution_nodes, resolution_edges = await _seed_resolution_persons(graph, load_id=load_id)
        ring_nodes, ring_edges = await _seed_community_rings(graph, load_id=load_id)
        spokes = await build_path_spokes(graph)
        await report_ids_stored_twice(
            client,
            edge_types=[groovy_identifier(physical_type_name(e.name)) for e in ontology.edge_types],
            say=lambda line: print(f"{line} (whole shared graph)"),
            advice=KNOWN_STRAY_ADVICE,
        )
    finally:
        await client.aclose()

    print(
        f"Seeded {resolution_nodes} resolution Person nodes and {resolution_edges} real "
        f"SAME_AS edges."
    )
    print(f"Seeded {ring_nodes} community-ring nodes and {ring_edges} edges across 3 rings.")
    print(
        f"Seeded the path-spoke hub {spokes.hub_id!r} with spokes of length "
        f"{sorted(spokes.terminal_by_length)}, including a SECRET shortcut on the "
        f"length-{spokes.shortcut_spoke_length} spoke."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
