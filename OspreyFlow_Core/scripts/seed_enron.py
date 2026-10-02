"""Seeds the Enron mail corpus into a running deployment, on the owner's own machine only
(ADR-053 and its Amendment 1).

    python -m scripts.seed_internal enron --stop-api        (or: make seed-enron)

**Real data.** It refuses, with a sentence naming what is missing, unless all of these hold: the
local, gitignored exceptions list (`config/real_data_exceptions.yaml`) has an entry for `enron`
permitting `owner_run_demonstration`; the corpus is provisioned under
`OspreyFlow_Data/Enron_Mails/`; and this is a checkout, never a bundle. Nothing here downloads or
copies the corpus.

The graph takes the company's own addresses and the links between them (about one node per address
and one edge per directed pair); the analytics store takes every distinct message, one event per
recipient. See `demo_fixtures/enron.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import duckdb
from scripts.seed_support import (
    KNOWN_STRAY_ADVICE,
    EventProgress,
    clear_seeded_graph,
    events_already_loaded,
    report_ids_stored_twice,
    write_graph,
)

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from demo_fixtures import enron
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.analytics import AnalyticsPort
from schemas.domain import Handling, Principal

DATASET = "enron"
USE = "owner_run_demonstration"
FOLDER = "Enron_Mails"
CASE_NAME = "Enron corpus (real data, this machine only)"

_GRAPH_CHUNK = 40
_EVENT_CHUNK = 20_000

_HANDLING = Handling(
    classification="OFFICIAL",
    handling_code="P",
    originator="enron-demo",
    owning_unit="enron-demo",
)


class NotProvisionedError(RuntimeError):
    """The corpus may not be seeded here, and the sentence says why."""


def _is_checkout() -> bool:
    return (Path(__file__).resolve().parents[2] / ".git").exists()


def permitted_here(*, config_path: Path | None = None) -> bool:
    """Whether the local exceptions list admits this dataset for this use. A missing or unreadable
    list is a refusal, never a crash and never permission."""
    from scripts import real_data_exceptions as exceptions

    try:
        return exceptions.is_permitted(
            DATASET, USE, config_path=config_path or exceptions.CONFIG_PATH
        )
    except (OSError, ValueError):
        return False


def authorise(
    args: argparse.Namespace, *, in_checkout: bool, permitted: Callable[[], bool]
) -> Path:
    """The corpus folder, or a refusal naming the first thing that is missing."""
    if not (args.attested_permission or permitted()):
        raise NotProvisionedError(
            "The real-data exceptions list has no entry for 'enron' permitting "
            f"'{USE}' on this machine. Add one with `python -m scripts.real_data_exceptions add` "
            "(ADR-035 §C3, ADR-053); nothing was read."
        )
    if not (in_checkout or args.attested_checkout):
        raise NotProvisionedError(
            "The Enron seed only runs from a checkout of the repository, never from a built "
            "bundle: real data does not travel with one."
        )
    folder = Path(args.data_dir) / FOLDER
    if not folder.is_dir():
        raise NotProvisionedError(
            f"dataset not provisioned: {folder} is missing. Place the corpus there yourself; "
            "nothing downloads it."
        )
    return folder


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_enron", description=__doc__)
    parser.add_argument("--case-name", required=True)
    parser.add_argument("--grant", action="append", default=[], metavar="ACCOUNT=LEVEL")
    parser.add_argument("--attested-checkout", action="store_true")
    parser.add_argument(
        "--replace-graph",
        action="store_true",
        help=(
            "Delete this seed's own graph rows (ids starting enron-ep- and enron-comm-) and load "
            "again. For an interrupted load: a link written twice is counted twice."
        ),
    )
    parser.add_argument(
        "--attested-permission",
        action="store_true",
        help="The host checked the exceptions list (a container cannot see it).",
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
        "--principal-id", default=os.environ.get("OSPREY_PRINCIPAL_ID", "enron-seed-worker")
    )
    parser.add_argument("--clearance", default=os.environ.get("OSPREY_CLEARANCE", "OFFICIAL"))
    parser.add_argument("--org-unit", default=os.environ.get("OSPREY_ORG_UNIT", "unit-1"))
    return parser.parse_args(argv)


def _batches(items: Iterator[object], size: int) -> Iterator[list[object]]:
    batch: list[object] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


async def _run(args: argparse.Namespace) -> int:
    try:
        source = authorise(args, in_checkout=_is_checkout(), permitted=permitted_here)
    except NotProvisionedError as error:
        print(error, file=sys.stderr)
        return 1

    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()
    principal = Principal(id=args.principal_id, clearance=args.clearance, org_unit=args.org_unit)

    from scripts.case_seed import case_from_arguments

    case = await case_from_arguments(
        name=args.case_name, seeder=principal, grant_texts=list(args.grant)
    )
    scope = case.id
    print(f"Case {args.case_name!r} is {scope}.")

    if events_already_loaded(args.analytics_db_path, scope):
        print(
            f"Case {scope!r} already has events loaded, and loading them again would double every "
            "count. Nothing was written.",
            file=sys.stderr,
        )
        return 1

    # Pass one: the summarised links for the graph. Pass two: every message as events.
    first = enron.Tally()
    pairs = enron.summarise(enron.read_messages(source, tally=first))
    for line in first.lines():
        print(f"  {line}", flush=True)
    nodes, edges = enron.build_graph_writes(pairs, created_by=principal.id, handling=_HANDLING)

    database = os.environ.get("ARCADEDB_DATABASE", "ospreyflow")
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database))
    try:
        await client.create_database_if_absent()
        graph = GraphArcadeDBAdapter(client, scheme)
        await graph.apply_schema(ontology)
        if args.replace_graph:
            removed = await clear_seeded_graph(
                client,
                node_type=groovy_identifier(physical_type_name("Endpoint")),
                node_prefix="enron-ep-",
                edge_type=groovy_identifier(physical_type_name("COMMUNICATED_WITH")),
                edge_prefix="enron-comm-",
            )
            print(f"  graph: removed {removed[0]:,} addresses and {removed[1]:,} links")
        if nodes and await graph.get_node(nodes[0].id, principal) is not None:
            print(
                "The Enron graph is already loaded (or a load was interrupted). Nothing was "
                "written. To load again, use --replace-graph: it deletes this seed's own rows "
                "first.",
                file=sys.stderr,
            )
            return 1
        await write_graph(graph, nodes, edges, chunk=_GRAPH_CHUNK, nouns=("addresses", "links"))
        await report_ids_stored_twice(
            client,
            edge_types=[groovy_identifier(physical_type_name("COMMUNICATED_WITH"))],
            prefix="enron-comm-",
            advice=KNOWN_STRAY_ADVICE,
        )
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
            event
            for message in enron.read_messages(source)
            for event in enron.to_events(message, investigation_scope=scope, handling=_HANDLING)
        )
        report_events = EventProgress()
        for batch in _batches(events, _EVENT_CHUNK):
            await analytics.load_events(batch)  # type: ignore[arg-type]
            loaded += len(batch)
            report_events(loaded)
    finally:
        con.close()

    print(f"Seeded {len(nodes)} addresses and {len(edges)} links into the graph.")
    print(f"Loaded {loaded:,} events under investigation_scope={scope!r}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
