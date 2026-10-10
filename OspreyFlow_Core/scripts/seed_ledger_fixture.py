"""Seeds Operation Ledger (the synthetic financial-fraud fixture, ADR-108 Amendment 4) into a
real Conduit's stores, under a real investigation's scope — run through `scripts.seed_internal
ledger`, inside the deployment's own network, the way every internal demo seeds.

What lands, and which surface it feeds: FIBO `Account`s and temporal `TRANSACTED` money flows
through the real engine (the network and the timeline); the companies, their registered offices
and the branch points in the geometry partition (the map); the SAR narrative as held content in
the media store (the reader's extraction, and the model's questions); HALE's control of the shell
written `inferred` (rule 5, drawn dashed until a person confirms it).

Mirrors `scripts/seed_hmp_fixture.py`; `tests/scenarios/test_ledger_graph.py` proves the build
itself against a live ArcadeDB, so this script is wiring, not logic.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import cast

import duckdb
import yaml
from scripts.case_seed import add_case_arguments, check_case_arguments, scope_for
from scripts.load_screening_list import parse_list
from scripts.seed_support import KNOWN_STRAY_ADVICE, report_ids_stored_twice
from services.api.config import PostgresConfig
from services.api.dataset_scope import stamping
from services.api.screening import ScreeningListStore

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from adapters.media_objectstore import MediaStoreConfig, ObjectStoreMediaStore
from demo_fixtures.datasets import LEDGER
from demo_fixtures.ledger import build_ledger_graph, geometry_records
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.domain import Principal

SCREENING_LIST = (
    Path(__file__).resolve().parents[1] / "packages/demo_fixtures/screening_list_synthetic.yaml"
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_ledger_fixture",
        description=(
            "Seeds Operation Ledger (FIBO accounts, the structuring money flow, the SAR and the "
            "registered offices) into a real Conduit's stores, under a real investigation's scope."
        ),
    )
    add_case_arguments(parser)
    parser.add_argument(
        "--analytics-db-path",
        default=os.environ.get(
            "ANALYTICS_DB_PATH", "../OspreyFlow_Data/_local-runtime/analytics.duckdb"
        ),
    )
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "ledger-seed-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "verify"))
    args = parser.parse_args(argv)
    check_case_arguments(parser, args)
    return args


async def _run(args: argparse.Namespace) -> int:
    # The deployment ontology, not the bare core: the whole point of this fixture is FIBO's
    # Account and money-flow vocabulary reaching the store (ADR-108 Amendment 4).
    ontology = load_deployment_ontology()
    scheme = load_uk_le_scheme()

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    await client.create_database_if_absent()
    graph = cast(GraphPort, stamping(GraphArcadeDBAdapter(client, scheme), dataset=LEDGER.id))
    await graph.apply_schema(ontology)

    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)
    scope = await scope_for(args, seeder=principal, dataset=LEDGER)

    media = ObjectStoreMediaStore(MediaStoreConfig.from_env())
    try:
        result = await build_ledger_graph(
            graph=graph,
            ontology=ontology,
            principal=principal,
            investigation_scope=scope,
            media=media,
        )
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
        from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table

        create_events_table(analytics_con)
        create_geometries_table(analytics_con)
        analytics: AnalyticsPort = AnalyticsDuckDBAdapter(analytics_con, scheme)
        await analytics.load_events(result.events)
        # Insert-only, keyed by ref: a re-seeded point already in the partition is not loaded twice.
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

    # ADR-109 phase F: the synthetic screening list the KYC rules screen against (rule 9: synthetic,
    # in-repo). Replaced whole, so a re-seed leaves one copy of it.
    list_name, entries = parse_list(
        yaml.safe_load(SCREENING_LIST.read_text(encoding="utf-8")), use="local_development"
    )
    screening = await ScreeningListStore.connect(PostgresConfig.from_env().dsn)
    try:
        await screening.replace_list(list_name, entries)
    finally:
        await screening.close()

    print(
        f"Seeded Operation Ledger: {result.transactions_loaded} transactions "
        f"({len(result.events)} timeline events), the SAR "
        f"({result.sar_document_id or 'not written — no media store?'}), and "
        f"{len(geometry_records())} map points under investigation_scope={scope!r}; "
        f"the screening list {list_name!r} ({len(entries)} synthetic entries)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
