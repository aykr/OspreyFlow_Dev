"""Seeds a real, running Conduit's stores with the HMP fixture — the
concrete mechanism that makes `08_ACCEPTANCE_SCENARIOS.md` Scenario A
(A3–A11) demonstrable against a live Glass, not only against automated tests.

**No `osprey` CLI** (`CLAUDE.md`'s own Conventions, reconfirmed
this phase) — a plain, directly-runnable script now, the same correction
already made for `revert_load` (Phase 2) and the local-basemap build
(Checkpoint 1). `python -m scripts.seed_hmp_fixture` is what an eventual
`osprey seed --fixture hmp` wraps.

**Why `--investigation-scope` is required, not defaulted.** Every existing
HMP test builds the fixture under `packages/demo_fixtures/hmp_graph.py`'s
own `INVESTIGATION_SCOPE` constant (`"case-hmp-fixture"`), which is fine
for a test that asserts entirely within its own process. A live demo needs
the events tagged with the *real* investigation id an analyst is actually
using in a running Glass session, since `EventFilter.investigation_scope`
is what every `/v1/analytics/*` route filters on — passing the wrong scope
here would seed data no query in the running session could ever see. Get
the real id from `POST /v1/investigations`'s own response (or the Glass's
`sessionStorage["ospreyflow.investigationId"]` in a browser dev console).

This writes to both stores a real Conduit reads from: `build_hmp_graph`
against the same ArcadeDB, then `AnalyticsPort.load_events` against the
same persistent analytics DuckDB file (`ANALYTICS_DB_PATH`,
`services/api/config.py`'s own default) — not a bypass of either.

Run as `PYTHONPATH=.:packages python -m scripts.seed_hmp_fixture ...` from
the repo root — this module imports `demo_fixtures.hmp_graph`
directly rather than duplicating the fixture, the same reason
`tests/services/api/test_statelessness.py`'s own spawned `uvicorn`
subprocess needs `PYTHONPATH` set explicitly: neither `pytest`'s own
`pythonpath = ["packages"]` (`pyproject.toml`) nor a bare `python -m`
invocation puts the repo root and `packages/` on `sys.path` by itself.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import cast

import duckdb
from scripts.case_seed import add_case_arguments, check_case_arguments, scope_for
from scripts.seed_support import KNOWN_STRAY_ADVICE, report_ids_stored_twice
from services.api.dataset_scope import stamping

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from demo_fixtures.datasets import HMP
from demo_fixtures.hmp_graph import build_hmp_graph, lookup_person_ids
from demo_fixtures.hmp_network import (
    FIRST_INCIDENT_REF,
    geometry_records,
    write_hmp_network,
    write_hmp_places,
)
from demo_fixtures.hmp_population import PRINCIPAL_SUBJECT_PRISON_NUMBER
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import EventRecord
from schemas.domain import Principal


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_hmp_fixture",
        description=(
            "Seeds the HMP fixture (Location/Person/Organisation graph + incident events) "
            "into a real Conduit's stores, under a real investigation's scope."
        ),
    )
    add_case_arguments(parser)
    parser.add_argument(
        "--analytics-db-path",
        # The Data folder (ADR-054); the same string as the Conduit's default, kept equal by
        # `tests/test_data_folder.py`.
        default=os.environ.get(
            "ANALYTICS_DB_PATH", "../OspreyFlow_Data/_local-runtime/analytics.duckdb"
        ),
    )
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "hmp-seed-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    args = parser.parse_args(argv)
    check_case_arguments(parser, args)
    return args


async def _run(args: argparse.Namespace) -> int:
    # ADR-117: the network's incidents and custody links are the NIEM pack's, and its accounts
    # FIBO's, so the store gets the core and every pack, as the Ledger seed applies it.
    ontology = load_deployment_ontology()
    scheme = load_uk_le_scheme()

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = cast(
        GraphPort, stamping(GraphArcadeDBAdapter(client, scheme), dataset=HMP.id)
    )
    await graph.apply_schema(ontology)

    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)
    scope = await scope_for(args, seeder=principal, dataset=HMP)

    # ADR-117: safe to run again. A deployment seeded before the network existed (v0.1.x) has the
    # population already; writing it again would add every incident a second time, so then only
    # the network is written. One that has the network too gains only what it lacks (its places).
    events: list[EventRecord] = []
    network_events: list[EventRecord] = []
    try:
        if await graph.find_node("Incident", "incident_ref", FIRST_INCIDENT_REF, principal):
            print("The HMP pack and its network are already here.")
        elif await graph.find_node(
            "Person", "prison_number", PRINCIPAL_SUBJECT_PRISON_NUMBER, principal
        ):
            person_ids = await lookup_person_ids(graph, principal)
            print(
                f"The HMP population is already here ({len(person_ids)} people); "
                "adding its network."
            )
            network_events = await write_hmp_network(
                graph=graph, person_ids=person_ids, principal=principal, investigation_scope=scope
            )
        else:
            result = await build_hmp_graph(
                graph=graph,
                ontology=ontology,
                principal=principal,
                investigation_scope=scope,
            )
            person_ids = result.person_node_ids
            events += result.current_window_events + result.prior_period_events
            print(
                f"Seeded {len(person_ids)} Person nodes, {len(result.yard_node_ids)} yards, "
                f"{len(result.current_window_events)} current-window and "
                f"{len(result.prior_period_events)} prior-period incident events."
            )
            network_events = await write_hmp_network(
                graph=graph, person_ids=person_ids, principal=principal, investigation_scope=scope
            )
        events += network_events
        if await write_hmp_places(graph=graph, principal=principal):
            print("Put the prison, its yards, the towns and the accounts on the map.")
        await report_ids_stored_twice(
            client,
            edge_types=[groovy_identifier(physical_type_name(e.name)) for e in ontology.edge_types],
            say=lambda line: print(f"{line} (whole shared graph)"),
            advice=KNOWN_STRAY_ADVICE,
        )
    finally:
        await client.aclose()

    Path(args.analytics_db_path).parent.mkdir(parents=True, exist_ok=True)
    analytics_con = duckdb.connect(args.analytics_db_path)
    try:
        create_events_table(analytics_con)
        create_geometries_table(analytics_con)
        analytics: AnalyticsPort = AnalyticsDuckDBAdapter(analytics_con, scheme)
        await analytics.load_events(events)
        # Insert-only, keyed by ref: a point already in the partition is not loaded twice.
        wanted = geometry_records()
        held = {
            record.geometry_ref
            for record in await analytics.get_geometries(
                [record.geometry_ref for record in wanted], principal, version=1
            )
        }
        await analytics.load_geometries([r for r in wanted if r.geometry_ref not in held])
    finally:
        analytics_con.close()

    print(
        f"Loaded {len(network_events)} network events (calls, visits, payments, custody, "
        f"incidents); {len(events)} events in all under investigation_scope={scope!r}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
