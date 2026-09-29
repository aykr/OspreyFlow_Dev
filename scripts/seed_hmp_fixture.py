"""Seeds a real, running Conduit's stores with the HMP fixture — the
concrete mechanism that makes `08_ACCEPTANCE_SCENARIOS.md` Scenario A
(A3–A11) demonstrable against a live Glass, not only against automated tests.

**No `osprey` CLI** (`CLAUDE.md`'s own Conventions, reconfirmed
this phase) — a plain, directly-runnable script now, the same correction
already made for `revert_load` (Phase 2) and the local-basemap build
(Checkpoint 1). `python -m scripts.seed_hmp_fixture` is what an eventual
`osprey seed --fixture hmp` wraps.

**Why `--investigation-scope` is required, not defaulted.** Every existing
HMP test builds the fixture under `tests/scenarios/fixtures/hmp_graph.py`'s
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
the repo root — this module imports `tests.scenarios.fixtures.hmp_graph`
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

import duckdb
from tests.scenarios.fixtures.hmp_graph import build_hmp_graph

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.analytics import AnalyticsPort
from schemas.domain import Principal


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_hmp_fixture",
        description=(
            "Seeds the HMP fixture (Location/Person/Organisation graph + incident events) "
            "into a real Conduit's stores, under a real investigation's scope."
        ),
    )
    parser.add_argument(
        "--investigation-scope",
        required=True,
        help=(
            "The real investigation id events should be tagged with "
            "(EventFilter.investigation_scope)."
        ),
    )
    parser.add_argument(
        "--analytics-db-path",
        # The Data folder (ADR-054); the same string as the Conduit's default, kept equal by
        # `tests/test_data_folder.py`.
        default=os.environ.get(
            "ANALYTICS_DB_PATH", "OspreyFlow_Data/_local-runtime/analytics.duckdb"
        ),
    )
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "hmp-seed-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, scheme)
    await graph.apply_schema(ontology)

    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)

    try:
        result = await build_hmp_graph(
            graph=graph,
            ontology=ontology,
            principal=principal,
            investigation_scope=args.investigation_scope,
        )
    finally:
        await client.aclose()

    Path(args.analytics_db_path).parent.mkdir(parents=True, exist_ok=True)
    analytics_con = duckdb.connect(args.analytics_db_path)
    try:
        create_events_table(analytics_con)
        create_geometries_table(analytics_con)
        analytics: AnalyticsPort = AnalyticsDuckDBAdapter(analytics_con, scheme)
        await analytics.load_events(result.current_window_events)
        await analytics.load_events(result.prior_period_events)
    finally:
        analytics_con.close()

    print(f"Seeded {len(result.person_node_ids)} Person nodes, {len(result.yard_node_ids)} yards.")
    print(
        f"Loaded {len(result.current_window_events)} current-window events and "
        f"{len(result.prior_period_events)} prior-period events under "
        f"investigation_scope={args.investigation_scope!r}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
