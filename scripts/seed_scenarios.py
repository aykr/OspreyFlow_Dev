"""Seed Scenario A's and B's remaining fixture data into a rendered deployment — round 13cb.

**Why this exists: owner ruling R8, 27 September 2026.** Clause 3 of V1 END TO END is NOT REACHED,
and the bar it set is that **every row of both acceptance scenarios must be performable through
the analyst's own door on a rendered `local-lite` deployment**. Eleven rows were not, for one
reason: the deployment is seeded with `hmp` and `fixture-corp` and nothing else, so the person
layer B4–B8 walk through, the device legs B15 pivots on and the sightings B17/B18 plot were
simply not there. A row proven only in process no longer counts towards clause 3.

**What this seeds, row by row.**

| Row | What lands |
| --- | --- |
| B4, B5 | A cohort of `Person`s, each with a personal `Endpoint`, all one hop
|        | from one shared `Endpoint` |
| B7 | A second cohort sharing one messaging-handle `Endpoint` |
| B8 | *Nothing.* The `SAME_AS` is the analyst's own asserted link — see below |
| B15 | A handset (`imei`) with two SIMs (`imsi`) `PAIRED_WITH` it |
| B16, B17, B18 | Location `Event`s for that handset, ordered in time, so a track
|               | exists to brush and plot |

**B8 deliberately seeds nothing, and this is a correction to the brief that commissioned it.**
Round 13cb's brief proposed "adding the minimal comparison config for identifier-bearing types
(exact equality on the normalised identifier value, scored 1.0)" so a *scored* `SAME_AS` could be
produced. That would implement an alternative to an accepted decision record. **ADR-024** decides
that a link between identifier systems with no lexical resemblance "is a direct, asserted write,
not a probabilistic match", and `08_ACCEPTANCE_SCENARIOS.md` B8's own row already says the edge is
"asserted at score 1.0 (ADR-024's own pattern for identifier systems with no lexical overlap — a
handle and an `e164` number share none)". So the manual link *is* the specified behaviour, the
row needs no resolution machinery, and B8 is walked over the wire as an analyst asserting it.
`CLAUDE.md`: accepted decision records are not to be worked around silently.

**Ids are stable, and that is the difference from the other two seeders' posture.** `hmp` and
`fixture-corp` mint fresh ids per run; this one pins its run token to `SCENARIOS_TOKEN` so the
over-the-wire test can *find* what was seeded without being told. Re-seeding therefore upserts the
same elements rather than accumulating a second copy — idempotent, which is what a deployment
seeded more than once needs. Every derived value goes through `scenario_cohorts._stable_digest`
rather than `hash()`, because `hash()` is randomised per interpreter and this module and the test
that reads it back are different processes (that file's own docstring has the measurement).

**Rule 9.** Synthetic only, from `tests/scenarios/fixtures/`. Numbers are Ofcom's reserved
07700 900xxx drama range. Nothing here touches a real dataset or anything named in
`config/real_data_exceptions.yaml`.

Run the way `apply.py` runs the other two — inside the deployment's own network, with the Conduit
stopped:

    python -m scripts.seed_scenarios --investigation-scope <id>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from tests.scenarios.fixtures.scenario_cohorts import (
    Cohort,
    DeviceLegs,
    generate_cohort,
    generate_device_legs,
    generate_handle_cohort,
)

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_edge_id, new_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import GraphPort
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    Provenance,
    ProvenanceState,
    SourceRef,
)

_CREATED_BY = "scenarios-seed-worker"

#: Pinned so the over-the-wire test can address what was seeded. See the module docstring.
SCENARIOS_TOKEN = "scenarios"

#: The shared endpoint B4/B5's cohort converges on. A literal, for the same reason: the test
#: searches for it by value.
SHARED_ENDPOINT_ID = "scenarios-shared-endpoint"
SHARED_ENDPOINT_VALUE = "+447700900500"

#: B17's brush window centres here, and B13's seizure record is dated the same day, so "brush to
#: the seizure date" lands on the sightings rather than on an empty stretch of axis.
SEIZURE_DATE = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

#: B18's track. Four points, ordered, far enough apart to render as a trail rather than a dot.
_SIGHTING_POINTS = [
    ("Depot", 51.5074, -0.1278),
    ("Lockup", 51.5155, -0.1410),
    ("Yard", 51.5230, -0.1585),
    ("Wharf", 51.5081, -0.1900),
]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_scenarios",
        description=(
            "Seeds Scenario A's and B's remaining fixture data (owner ruling R8) into a real "
            "Conduit's ArcadeDB, under a real investigation's scope."
        ),
    )
    parser.add_argument(
        "--investigation-scope",
        required=True,
        help="The real investigation id these nodes/edges should be written under.",
    )
    return parser.parse_args(argv)


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="fixture", owning_unit="unit-1"
    )


def _provenance(label: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="fixture", locator=label, excerpt_hash="")],
        first_seen=now_utc(),
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=now_utc(), created_by=_CREATED_BY)


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


def build_shared_endpoint() -> Node:
    """The endpoint B4/B5's cohort converges on, as a stable node the test can search for."""
    return Node(
        id=SHARED_ENDPOINT_ID,
        type="Endpoint",
        properties={
            "value_raw": SHARED_ENDPOINT_VALUE,
            "value_normalised": SHARED_ENDPOINT_VALUE,
            "endpoint_kind": "msisdn",
        },
        provenance=_provenance("scenarios:shared-endpoint"),
        handling=_handling(),
        audit=_audit(),
    )


def build_sightings(legs: DeviceLegs) -> tuple[list[Node], list[Edge]]:
    """**B16, B17, B18.** Location `Event`s for the seized handset, ordered in time.

    B18 wants "an ordered track [that] renders and animates under playback", B17 wants "location
    events for the device in that window", and B16 wants a second event set to overlay. One
    ordered sequence of `PRESENT_AT` events satisfies all three, and is the smallest thing that
    does — four points an hour apart around the seizure date, each with its own `Location`.

    The `Location` carries `geometry_ref` and `name`, the two properties
    `packages/ontology/default.yaml` declares for it; `Event` declares none, so its shape is the
    ordinary one this repository already writes (`occurred_at`, a label).
    """
    nodes: list[Node] = []
    edges: list[Edge] = []

    for index, (name, latitude, longitude) in enumerate(_SIGHTING_POINTS):
        moment = SEIZURE_DATE + timedelta(hours=index)
        location_id = f"scenarios-location-{index}"
        event_id = f"scenarios-sighting-{index}"

        nodes.append(
            Node(
                id=location_id,
                type="Location",
                properties={
                    "name": name,
                    "geometry_ref": f"POINT({longitude} {latitude})",
                },
                provenance=_provenance(f"scenarios:location:{index}"),
                handling=_handling(),
                audit=_audit(),
            )
        )
        nodes.append(
            Node(
                id=event_id,
                type="Event",
                properties={
                    "label": f"Device sighting — {name}",
                    "occurred_at": moment.isoformat(),
                    "event_type": "sighting",
                },
                provenance=_provenance(f"scenarios:sighting:{index}"),
                handling=_handling(),
                audit=_audit(),
            )
        )
        edges.append(
            Edge(
                id=new_edge_id(),
                type="PRESENT_AT",
                source=legs.handset_id,
                target=location_id,
                properties={"occurred_at": moment.isoformat(), "sequence": index},
                provenance=_provenance(f"scenarios:present-at:{index}"),
                handling=_handling(),
                audit=_audit(),
            )
        )

    return nodes, edges


async def _write(
    graph: GraphPort, nodes: list[Node], edges: list[Edge], *, load_id: str
) -> tuple[int, int]:
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([_node_write(n, load_id=load_id) for n in nodes], tx)
    await graph.upsert_edges([_edge_write(e, load_id=load_id) for e in edges], tx)
    await graph.commit_transaction(tx)
    return len(nodes), len(edges)


def build_everything() -> tuple[list[Node], list[Edge], dict[str, object]]:
    """Every element this seeder writes, plus the ids a caller needs to name afterwards.

    Separated from the writing so it can be asserted without a database — `tests/
    test_seed_scenarios.py` checks the shape, and the conformance/adapter tiers already prove the
    writing.
    """
    shared = build_shared_endpoint()
    cohort: Cohort = generate_cohort(
        shared_endpoint_id=SHARED_ENDPOINT_ID, prefix="alpha", run_token=SCENARIOS_TOKEN
    )
    handles: Cohort = generate_handle_cohort(prefix="beta", run_token=SCENARIOS_TOKEN)
    legs: DeviceLegs = generate_device_legs(
        msisdn=SHARED_ENDPOINT_VALUE, run_token=SCENARIOS_TOKEN
    )
    sighting_nodes, sighting_edges = build_sightings(legs)

    nodes = [shared, *cohort.nodes, *handles.nodes, *legs.nodes, *sighting_nodes]
    edges = [*cohort.edges, *handles.edges, *legs.edges, *sighting_edges]

    landmarks: dict[str, object] = {
        "shared_endpoint_id": SHARED_ENDPOINT_ID,
        "shared_endpoint_value": SHARED_ENDPOINT_VALUE,
        "cohort_person_ids": cohort.person_ids,
        "handle_cohort_person_ids": handles.person_ids,
        "handle_id": handles.shared_id,
        "handset_id": legs.handset_id,
        "sim_ids": legs.sim_ids,
        "sighting_event_ids": [n.id for n in sighting_nodes if n.type == "Event"],
    }
    return nodes, edges, landmarks


async def _run(args: argparse.Namespace) -> int:
    load_id = new_id()
    nodes, edges, landmarks = build_everything()

    config = ArcadeDBConfig.from_env()
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    async with ArcadeDBClient(config) as client:
        graph = GraphArcadeDBAdapter(
            client,
            ontology=ontology,
            handling_scheme=scheme,
            investigation_scope=args.investigation_scope,
        )
        node_count, edge_count = await _write(graph, nodes, edges, load_id=load_id)

    print(
        f"  seed[scenarios]: Seeded {node_count} nodes and {edge_count} edges for Scenario A/B "
        f"under investigation_scope={args.investigation_scope!r}."
    )
    print(
        f"  seed[scenarios]: B4/B5 cohort of {len(landmarks['cohort_person_ids'])} around "
        f"{SHARED_ENDPOINT_VALUE}; B7 handle cohort of "
        f"{len(landmarks['handle_cohort_person_ids'])} on {landmarks['handle_id']}."
    )
    print(
        f"  seed[scenarios]: B15 handset {landmarks['handset_id']} with "
        f"{len(landmarks['sim_ids'])} SIMs; B16-B18 "
        f"{len(landmarks['sighting_event_ids'])} sightings around {SEIZURE_DATE:%Y-%m-%d}."
    )
    print(
        "  seed[scenarios]: B8 seeds no SAME_AS — ADR-024 makes it the analyst's own asserted "
        "link, and 08's B8 row says so."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
