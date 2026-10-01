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
from scripts.seed_support import (
    RepairAnomaly,
    clear_seeded_graph,
    events_already_loaded,
    events_summary,
    inspect_graph,
    repair_ids_stored_twice,
    report_ids_stored_twice,
    reset_graph_database,
    vault_locations,
    write_graph,
)

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
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
        "--replace-graph",
        action="store_true",
        help=(
            "Delete this seed's own graph rows (ids starting paysim-acct- and paysim-tx-) and "
            "load again. For an interrupted load: a transaction written twice is counted twice."
        ),
    )
    parser.add_argument(
        "--vault",
        default=None,
        help=(
            "Load into this dataset's own vault (ADR-056): its own graph database and analytics "
            "file, derived from the id. Without it, the shared database and file are used."
        ),
    )
    parser.add_argument(
        "--reset-graph-database",
        action="store_true",
        help=(
            "Drop the whole graph database and create it again empty before loading. For a "
            "database whose storage is damaged. Deletes every case's graph rows, so only on "
            "request."
        ),
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Read-only: report what the graph holds, write nothing, and stop.",
    )
    parser.add_argument(
        "--inspect-record", default=None, help="With --inspect: a record id to read."
    )
    parser.add_argument(
        "--repair-strays",
        action="store_true",
        help=(
            "Find ids a scan sees stored twice (ArcadeDB wrote a stray copy, ADR-056 Amendment 16) "
            "and, with --apply, remove the copy the source vertex does not reach. A dry run "
            "without --apply. Writes no case and loads nothing."
        ),
    )
    parser.add_argument(
        "--apply", action="store_true", help="With --repair-strays: actually remove the strays."
    )
    parser.add_argument(
        "--repair-limit",
        type=int,
        default=None,
        help="With --repair-strays: repair only this many ids (the first run should be one).",
    )
    parser.add_argument(
        "--graph-fraud-rows",
        type=int,
        default=None,
        help=(
            "Write to the graph only the first N fraud transactions and everything touching their "
            "accounts (the full neighbourhood is 74,000 accounts and takes hours). The analytics "
            "store always gets every row."
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
    if args.apply and not args.repair_strays:
        parser.error("--apply only goes with --repair-strays")
    if not (args.inspect or args.repair_strays) and (
        bool(args.investigation_scope) == bool(args.case_name)
    ):
        parser.error("give exactly one of --investigation-scope and --case-name")
    return args


def scope_and_source(args: argparse.Namespace, *, in_checkout: bool) -> Path:
    """The data file, from a checkout or a checkout the host has attested to, else a refusal."""
    return resolve_source(
        Path(args.data_dir), is_checkout=in_checkout or bool(args.attested_checkout)
    )


async def _load_graph(
    graph: GraphPort, source: Path, principal: Principal, *, fraud_rows: int | None = None
) -> tuple[int, int]:
    accounts = fraud_accounts(read_paysim(source), limit=fraud_rows)
    touching = [r for r in read_paysim(source) if r.origin in accounts or r.destination in accounts]
    nodes, edges = build_graph_writes(touching, created_by=principal.id, handling=_HANDLING)
    if nodes and await graph.get_node(nodes[0].id, principal) is not None:
        raise NotProvisionedError(
            "The PaySim graph is already loaded (or a load was interrupted). Nothing was written. "
            "To load again, use --replace-graph: it deletes this seed's own rows first, because "
            "a transaction written twice is counted twice."
        )
    await write_graph(graph, nodes, edges, chunk=_GRAPH_CHUNK, nouns=("accounts", "transactions"))
    return len(nodes), len(edges)


def _locations(args: argparse.Namespace) -> tuple[str, str]:
    """The graph database and analytics file to use: the vault's own, or the shared ones."""
    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    if args.vault is None:
        return database, args.analytics_db_path
    found = vault_locations(args.vault, args.analytics_db_path)
    return found.database, found.analytics_db_path


async def _inspect(args: argparse.Namespace) -> int:
    """Read-only. Uses only `SELECT`, so it is safe with the Conduit running."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(_locations(args)[0]))
    try:
        for line in await inspect_graph(
            client,
            node_type=groovy_identifier(physical_type_name("Endpoint")),
            node_prefix="paysim-acct-",
            edge_type=groovy_identifier(physical_type_name("TRANSACTED")),
            edge_prefix="paysim-tx-",
            record=args.inspect_record,
        ):
            print(f"  {line}")
    finally:
        await client.aclose()
    for line in events_summary(_locations(args)[1]):
        print(f"  {line}")
    return 0


async def _repair(args: argparse.Namespace) -> int:
    """Remove stray edge records from this seed's own transactions. A dry run unless `--apply`."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(_locations(args)[0]))
    try:
        try:
            report = await repair_ids_stored_twice(
                client,
                edge_type=groovy_identifier(physical_type_name("TRANSACTED")),
                prefix="paysim-tx-",
                apply=args.apply,
                limit=args.repair_limit,
            )
        except RepairAnomaly as error:
            print(f"repair stopped: {error}", file=sys.stderr)
            return 3
    finally:
        await client.aclose()
    if not report.planned and not report.skipped:
        print("  repair: no id is stored more than once; nothing to do")
    elif args.apply:
        print(f"  repair: removed {report.removed} stray record(s) for {len(report.planned)} id(s)")
    else:
        print(
            f"  repair: dry run; {len(report.planned)} id(s) would be repaired, "
            f"{len(report.skipped)} left alone. Nothing was changed."
        )
    return 1 if report.skipped else 0


async def _run(args: argparse.Namespace) -> int:
    try:
        database, analytics_path = _locations(args)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if args.inspect:
        return await _inspect(args)
    if args.repair_strays:
        return await _repair(args)
    if args.vault is not None:
        print(f"  vault {args.vault!r}: graph database {database}, analytics file {analytics_path}")
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
        from scripts.case_seed import case_from_arguments

        case = await case_from_arguments(
            name=args.case_name, seeder=principal, grant_texts=list(args.grant)
        )
        scope = case.id
        print(f"Case {args.case_name!r} is {scope}.")

    if events_already_loaded(analytics_path, scope):
        print(
            f"Case {scope!r} already has events loaded, and loading them again would double every "
            "count. Nothing was written.",
            file=sys.stderr,
        )
        return 1

    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    try:
        if args.reset_graph_database:
            await reset_graph_database(client, database=database)
        await client.create_database_if_absent()
        graph = GraphArcadeDBAdapter(client, scheme)
        await graph.apply_schema(ontology)
        if args.replace_graph and not args.reset_graph_database:
            removed = await clear_seeded_graph(
                client,
                node_type=groovy_identifier(physical_type_name("Endpoint")),
                node_prefix="paysim-acct-",
                edge_type=groovy_identifier(physical_type_name("TRANSACTED")),
                edge_prefix="paysim-tx-",
            )
            print(f"  graph: removed {removed[0]:,} accounts and {removed[1]:,} transactions")
        node_count, edge_count = await _load_graph(
            graph, source, principal, fraud_rows=args.graph_fraud_rows
        )
        vault_flag = f" --vault {args.vault}" if args.vault else ""
        strays = await report_ids_stored_twice(
            client,
            edge_types=[groovy_identifier(physical_type_name("TRANSACTED"))],
            prefix="paysim-tx-",
            repair_command=(
                f"python -m scripts.seed_internal paysim --repair-strays{vault_flag}  "
                "(add --apply to remove them)"
            ),
        )
    except NotProvisionedError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        await client.aclose()

    Path(analytics_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(analytics_path)
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
    if strays:
        print(
            f"The load finished, but {strays} transaction id(s) are stored more than once; see "
            "the check above.",
            file=sys.stderr,
        )
        return 4
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
