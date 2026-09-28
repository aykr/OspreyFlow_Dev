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
| A15 | One `Endpoint` marked `sanitisation_code: S2`, which blocks an export by name |
| B15 | A handset (`imei`) with the SIM it held *before* the swap; B13's ingest brings the other |
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
import os
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import duckdb
from tests.scenarios.fixtures.scenario_cohorts import (
    Cohort,
    DeviceLegs,
    generate_cohort,
    generate_device_legs,
    generate_handle_cohort,
)
from tests.scenarios.fixtures.seizure_record import SEIZURE_DATE as _SEIZURE_DAY

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_edge_id, now_utc
from ontology.handling import HandlingScheme, load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.graph import GraphPort
from schemas.analytics import EventRecord
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Handling,
    Interval,
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

#: **A15's consult-originator item — round 13cdc.** `08_ACCEPTANCE_SCENARIOS.md` A15: "Items
#: marked consult-originator block the export by name; export proceeds only with a recorded
#: justification and carries a withheld-item manifest." Nothing in any seeded population carried
#: `sanitisation_code: "S2"`, so that clause had never been walked on a deployment.
#:
#: **It lives here rather than in Fixture Corp, deliberately.** REPORT-13b recorded why: Fixture
#: Corp's population is what ADR-035 §C5's re-measured resolution scores are computed from, and
#: adding a node to it moves those numbers. Scenario A's own population is the right home, and
#: `tests/scenarios/test_fixture_corp_shape.py` stays untouched.
CONSULT_ORIGINATOR_NODE_ID = "scenarios-consult-originator-endpoint"
CONSULT_ORIGINATOR_VALUE = "+447700900999"
SHARED_ENDPOINT_VALUE = "+447700900500"

#: **The seizure fixture's own date, not one invented here.** B17 brushes "to the seizure date",
#: so the sightings must sit on the day `seizure_record.py` says the device was seized — a
#: different date would put the track outside the window an analyst actually brushes to. Noon,
#: because that fixture's date carries no time of day and a track needs somewhere to start.
SEIZURE_DATE = _SEIZURE_DAY.replace(hour=12)

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
    parser.add_argument(
        "--analytics-db-path", default=os.environ.get("ANALYTICS_DB_PATH", "data/analytics.duckdb")
    )
    return parser.parse_args(argv)


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="fixture", owning_unit="unit-1"
    )


def _consult_originator_handling() -> Handling:
    """`S2` is the UK LE scheme's consult-originator code — checked against
    `ontology.handling.load_uk_le_scheme()`, not assumed from the letter.

    `sanitisation_code` never gates a *read* (`schemas/domain.py`'s own note): this node is
    readable by the demo analyst exactly like any other, and it is the **export** boundary that
    must stop on it. That is the distinction A15 exists to prove, and seeding a node the analyst
    could not see would prove the wrong one.
    """
    return Handling(
        classification="OFFICIAL",
        handling_code="P",
        originator="fixture",
        owning_unit="unit-1",
        sanitisation_code="S2",
    )


def build_consult_originator_node() -> Node:
    """One `Endpoint` marked `S2`, for A15's export block."""
    return Node(
        id=CONSULT_ORIGINATOR_NODE_ID,
        type="Endpoint",
        properties={
            "value_raw": CONSULT_ORIGINATOR_VALUE,
            "value_normalised": CONSULT_ORIGINATOR_VALUE,
            "endpoint_kind": "msisdn",
        },
        provenance=_provenance("scenarios:consult-originator"),
        handling=_consult_originator_handling(),
        audit=_audit(),
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
        interval=edge.interval,
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
    """**B16, B17, B18.** The seized handset's locations, ordered in time.

    **The time lives on the edge, not on an `Event` node — the ontology said so, twice.** A first
    attempt minted `Event` nodes carrying `occurred_at`/`label`/`event_type`; `Event` declares no
    properties at all in `packages/ontology/default.yaml`, and `validate_properties` refused them
    by name. `PRESENT_AT` is declared `temporal: true` and `Device -> Location`, which is the same
    statement made where it belongs: *when* a device was somewhere is a property of the visit, not
    of a free-floating event object. So each sighting is one `PRESENT_AT` edge with its own
    `interval`, and the `Location` it points at.

    That is also what B17 needs to be a real test rather than a data check: a temporal window
    filters on the edge's interval, so "brush to the seizure date" restricts these edges. Four
    points an hour apart give a window something to include and something to exclude.
    """
    nodes: list[Node] = []
    edges: list[Edge] = []

    for index, (name, latitude, longitude) in enumerate(_SIGHTING_POINTS):
        moment = SEIZURE_DATE + timedelta(hours=index)
        location_id = f"scenarios-location-{index}"

        nodes.append(
            Node(
                id=location_id,
                type="Location",
                properties={"name": name, "geometry_ref": f"POINT({longitude} {latitude})"},
                provenance=_provenance(f"scenarios:location:{index}"),
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
                interval=Interval(valid_from=moment, valid_to=moment),
                provenance=_provenance(f"scenarios:present-at:{index}"),
                handling=_handling(),
                audit=_audit(),
            )
        )

    return nodes, edges


def build_sighting_events(edges: Sequence[Edge], *, investigation_scope: str) -> list[EventRecord]:
    """**B18's trail, in the store the Glass reads it from — round 13cde.**

    The graph edges above are what B15/B17 pivot and brush on; the Glass's snail trail is a
    different read — `POST /v1/analytics/sightings`, `AnalyticsPort.list_sightings` over the
    analytics store's `events` rows, filtered on `source_id`/`target_id`. Seeding only the edges
    left that read empty: measured in a real browser, the Glass sent the handset, the scope and
    the seizure-day window and got `[]` back, while the over-the-wire B18 case — reading the
    graph — passed. Two tiers, two populations.

    `EventRecord`'s own docstring makes an event "one occurrence of" a summarised graph edge, so
    each sighting is written as both, tied by `edge_id` — the same pairing the HMP fixture's
    events carry. Event ids are pinned, like every other id this module writes, so a re-seed can
    recognise what it already loaded (`load_sighting_events`).
    """
    points = {
        f"scenarios-location-{index}": (latitude, longitude)
        for index, (_, latitude, longitude) in enumerate(_SIGHTING_POINTS)
    }
    events: list[EventRecord] = []
    for edge in edges:
        if edge.type != "PRESENT_AT" or edge.target not in points:
            continue
        assert edge.interval is not None  # `build_sightings` gives every sighting its moment
        latitude, longitude = points[edge.target]
        events.append(
            EventRecord(
                event_id=f"scenarios-sighting-{edge.target.removeprefix('scenarios-location-')}",
                edge_id=edge.id,
                edge_type=edge.type,
                source_id=edge.source,
                target_id=edge.target,
                occurred_at=edge.interval.valid_from,
                lat=latitude,
                lon=longitude,
                investigation_scope=investigation_scope,
                handling=edge.handling,
            )
        )
    return events


async def load_sighting_events(
    con: duckdb.DuckDBPyConnection, scheme: HandlingScheme, events: Sequence[EventRecord]
) -> int:
    """Loads the sightings not already present, and returns how many it wrote.

    `events` has no primary key and `load_events` is a plain insert, so without this a second
    seed would double the track — four sightings drawn as eight, each pair on one instant.
    Existing ids are read back and skipped, the same way the grid route treats its geometries.
    """
    create_events_table(con)
    create_geometries_table(con)
    wanted = [e.event_id for e in events]
    if not wanted:
        return 0
    placeholders = ",".join("?" for _ in wanted)
    present = {
        row[0]
        for row in con.execute(
            f"SELECT event_id FROM events WHERE event_id IN ({placeholders})", wanted
        ).fetchall()
    }
    missing = [e for e in events if e.event_id not in present]
    await AnalyticsDuckDBAdapter(con, scheme).load_events(missing)
    return len(missing)


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
    # **The earlier state only — see `generate_device_legs`' own docstring.** B13 ingests the
    # later seizure record, and that ingest is what must create the swapped SIM; seeding it here
    # left the ingest with nothing to do and the hotlist never fired.
    legs: DeviceLegs = generate_device_legs(run_token=SCENARIOS_TOKEN, include_swapped_sim=False)
    sighting_nodes, sighting_edges = build_sightings(legs)

    consult = build_consult_originator_node()
    nodes = [shared, consult, *cohort.nodes, *handles.nodes, *legs.nodes, *sighting_nodes]
    edges = [*cohort.edges, *handles.edges, *legs.edges, *sighting_edges]

    landmarks: dict[str, object] = {
        "shared_endpoint_id": SHARED_ENDPOINT_ID,
        "shared_endpoint_value": SHARED_ENDPOINT_VALUE,
        "consult_originator_node_id": CONSULT_ORIGINATOR_NODE_ID,
        "consult_originator_value": CONSULT_ORIGINATOR_VALUE,
        "cohort_person_ids": cohort.person_ids,
        "handle_cohort_person_ids": handles.person_ids,
        "handle_id": handles.shared_id,
        "handset_id": legs.handset_id,
        "sim_ids": legs.sim_ids,
        "sighting_location_ids": [n.id for n in sighting_nodes if n.type == "Location"],
    }
    return nodes, edges, landmarks


async def _run(args: argparse.Namespace) -> int:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    # The same setup the other two seeders use, and for the same reasons: the database name comes
    # from the deployment's own environment, the database is created if this is a first seed, and
    # the schema is applied before any write so the types exist.
    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, scheme)
    await graph.apply_schema(ontology)

    # A readable load id rather than a fresh ULID, matching `fixture-corp`'s own shape: this is
    # the join key into the load ledger, and "which seed put this here" is the question it gets
    # asked. It is stable across re-seeds for the same reason the element ids are.
    load_id = f"scenarios:{args.investigation_scope}"
    nodes, edges, landmarks = build_everything()
    node_count, edge_count = await _write(graph, nodes, edges, load_id=load_id)

    # The analytics half — the same file and the same env fallback `seed_hmp_fixture` uses, and
    # the same reason this runs with the Conduit stopped: DuckDB's lock is exclusive.
    Path(args.analytics_db_path).parent.mkdir(parents=True, exist_ok=True)
    analytics_con = duckdb.connect(args.analytics_db_path)
    try:
        loaded = await load_sighting_events(
            analytics_con,
            scheme,
            build_sighting_events(edges, investigation_scope=args.investigation_scope),
        )
    finally:
        analytics_con.close()

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
        f"{len(landmarks['sighting_location_ids'])} sightings around {SEIZURE_DATE:%Y-%m-%d}; "
        f"{loaded} sighting events newly loaded into the analytics store for B18's trail."
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
