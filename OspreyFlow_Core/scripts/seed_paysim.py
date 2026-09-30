"""Seeds the PaySim mobile-money dataset into a running deployment (ADR-055).

    PYTHONPATH=.:packages python -m scripts.seed_paysim --investigation-scope <case id>

The analytics store takes every row (6.36 million events). The graph takes the fraud neighbourhood
only (about 70,000 accounts and 65,000 transactions). The data is synthetic, classified `internal`,
never committed, and read from `OspreyFlow_Data/PaySIM_Dataset/`. Simulator authors to cite:
E. A. Lopez-Rojas, A. Elmir and S. Axelsson, "PaySim: A financial mobile money simulator for fraud
detection", EMSS 2016. The data licence on the Kaggle copy has not been verified.

Needs ArcadeDB reachable on `localhost:2480` (the launched deployment publishes it to this machine
only) and the ArcadeDB password in `ARCADEDB_PASSWORD`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import duckdb

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from demo_fixtures.paysim import (
    build_graph_writes,
    fraud_accounts,
    read_paysim,
    to_event,
)
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.domain import Handling, Principal

FILE_NAME = "PS_20174392719_1491204439457_log.csv"
CASE_NAME = "PaySim mobile money (internal)"
CITATION = (
    'Lopez-Rojas, Elmir and Axelsson, "PaySim: A financial mobile money simulator for fraud '
    'detection", EMSS 2016.'
)

#: ArcadeDB commits fail with "Error in execution in lock" on larger transactions (the HMP fixture
#: measured this on the owner's machine), so writes go in small batches.
_GRAPH_CHUNK = 40
_EVENT_CHUNK = 50_000

_HANDLING = Handling(
    classification="OFFICIAL",
    handling_code="P",
    originator="paysim-demo",
    owning_unit="paysim-demo",
)


class NotProvisionedError(RuntimeError):
    """The dataset is not where the seed may read it from."""


def _is_checkout() -> bool:
    return (Path(__file__).resolve().parents[2] / ".git").exists()


def resolve_source(data_dir: Path, *, is_checkout: bool) -> Path:
    """The file, or a refusal. Refuses from a bundle: an internal dataset is never seeded from an
    artefact that left this project (ADR-035 §C1, as ADR-053 does for Enron)."""
    if not is_checkout:
        raise NotProvisionedError(
            "The PaySim seed only runs from a checkout of the repository, never from a built "
            "bundle: an internal dataset does not travel with one."
        )
    path = data_dir / "PaySIM_Dataset" / FILE_NAME
    if not path.is_file():
        raise NotProvisionedError(
            f"dataset not provisioned: {path} is missing. Place the PaySim log there (it is not "
            "committed and cannot be downloaded from a build machine)."
        )
    return path


def _batches(items: Iterator[object], size: int) -> Iterator[list[object]]:
    batch: list[object] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_paysim", description=__doc__)
    parser.add_argument(
        "--investigation-scope",
        default=None,
        help="Write into this existing case. Give this or --case-name.",
    )
    parser.add_argument(
        "--case-name",
        default=None,
        help="Make (or reuse) a case of this name in the Conduit's database and load into it.",
    )
    parser.add_argument(
        "--grant",
        action="append",
        default=[],
        metavar="ACCOUNT=LEVEL",
        help="With --case-name: the level an account holds on the case. Repeatable.",
    )
    parser.add_argument(
        "--attested-checkout",
        action="store_true",
        help=(
            "The host-side command verified the scripts and this data came from a checkout "
            "(a container has no .git to check)."
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("OSPREYFLOW_INTERNAL_DEMO_DATA_DIR", "../OspreyFlow_Data"),
    )
    parser.add_argument(
        "--analytics-db-path",
        default=os.environ.get(
            "ANALYTICS_DB_PATH", "../OspreyFlow_Data/_local-runtime/analytics.duckdb"
        ),
    )
    parser.add_argument(
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "paysim-seed-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    args = parser.parse_args(argv)
    if bool(args.investigation_scope) == bool(args.case_name):
        parser.error("give exactly one of --investigation-scope and --case-name")
    return args


def scope_and_source(args: argparse.Namespace, *, in_checkout: bool) -> Path:
    """The data file, from a checkout or a checkout the host has attested to, else a refusal."""
    return resolve_source(
        Path(args.data_dir), is_checkout=in_checkout or bool(args.attested_checkout)
    )


async def _load_graph(graph: GraphPort, source: Path, principal: Principal) -> tuple[int, int]:
    accounts = fraud_accounts(read_paysim(source))
    touching = [r for r in read_paysim(source) if r.origin in accounts or r.destination in accounts]
    nodes, edges = build_graph_writes(touching, created_by=principal.id, handling=_HANDLING)
    if nodes and await graph.get_node(nodes[0].id, principal) is not None:
        raise NotProvisionedError(
            "The PaySim graph is already loaded. Nothing was written; revert the earlier load "
            "before seeding again."
        )
    for start in range(0, len(nodes), _GRAPH_CHUNK):
        tx = await graph.begin_transaction()
        try:
            await graph.upsert_nodes(nodes[start : start + _GRAPH_CHUNK], tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
    for start in range(0, len(edges), _GRAPH_CHUNK):
        tx = await graph.begin_transaction()
        try:
            await graph.upsert_edges(edges[start : start + _GRAPH_CHUNK], tx)
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
    return len(nodes), len(edges)


async def _run(args: argparse.Namespace) -> int:
    try:
        source = scope_and_source(args, in_checkout=_is_checkout())
    except NotProvisionedError as error:
        print(error, file=sys.stderr)
        return 1

    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)
    scope = args.investigation_scope
    if args.case_name:
        # Inside the deployment the Conduit's Postgres is reachable, and the case is made through
        # the same store the routes use, so the demo accounts can open it (ADR-052).
        from scripts.case_seed import ensure_case, parse_grant
        from services.api.config import PostgresConfig
        from services.api.investigations import InvestigationStore

        case_store = await InvestigationStore.connect(PostgresConfig.from_env().dsn)
        try:
            case = await ensure_case(
                case_store,
                name=args.case_name,
                seeder=principal,
                grants=dict(parse_grant(g) for g in args.grant),
            )
        finally:
            await case_store.close()
        scope = case.id
        print(f"Case {args.case_name!r} is {scope}.")

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    try:
        await client.create_database_if_absent()
        graph = GraphArcadeDBAdapter(client, scheme)
        await graph.apply_schema(ontology)
        node_count, edge_count = await _load_graph(graph, source, principal)
    except NotProvisionedError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        await client.aclose()

    Path(args.analytics_db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(args.analytics_db_path)
    loaded = 0
    try:
        create_events_table(con)
        create_geometries_table(con)
        analytics: AnalyticsPort = AnalyticsDuckDBAdapter(con, scheme)
        events = (
            to_event(r, investigation_scope=scope, handling=_HANDLING) for r in read_paysim(source)
        )
        for batch in _batches(events, _EVENT_CHUNK):
            await analytics.load_events(batch)  # type: ignore[arg-type]
            loaded += len(batch)
            print(f"  {loaded:,} events loaded", flush=True)
    finally:
        con.close()

    print(f"Seeded {node_count} accounts and {edge_count} transactions into the graph.")
    print(f"Loaded {loaded:,} events under investigation_scope={scope!r}.")
    print(f"Cite: {CITATION}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
