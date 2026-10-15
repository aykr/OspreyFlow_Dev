"""Seeds the Enron mail corpus into a running deployment (ADR-053; ADR-114 Amendment 23).

    ospreyflow demo add enron --file enron_mail_20150507.tar.gz

**Real data.** It refuses, with a sentence naming what is missing, unless all of these hold: the
corpus was accepted on this machine (`ospreyflow demo add enron` keeps the record beside it) or
the owner's local exceptions list (`config/real_data_exceptions.yaml`) has an entry for `enron`
permitting `owner_run_demonstration`; the corpus is unpacked under the demo data folder's
`Enron_Mails/`; and this is a checkout, never a bundle. Nothing here downloads or copies the corpus.

The graph takes the company's own addresses and the links between them (about one node per address
and one edge per directed pair); the analytics store takes every distinct message, one event per
recipient. See `scripts/enron_mail.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import duckdb
from scripts import enron_mail as enron
from scripts.seed_support import (
    KNOWN_STRAY_ADVICE,
    EventProgress,
    clear_seeded_graph,
    clear_seeded_links,
    delete_case_events,
    events_already_loaded,
    report_ids_stored_twice,
    write_graph,
)
from services.api.dataset_scope import stamping

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.analytics_duckdb.schema import create_events_table, create_geometries_table
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from demo_fixtures.datasets import ENRON
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.domain import Handling, Principal

DATASET = "enron"
USE = "owner_run_demonstration"
FOLDER = "Enron_Mails"
CASE_NAME = "Enron corpus (real data)"

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
    """A user's checkout has the product at its root; the developer repository one folder down."""
    here = Path(__file__).resolve()
    return (here.parents[1] / ".git").exists() or (here.parents[2] / ".git").exists()


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
            "The Enron corpus has not been accepted on this machine: add it with `ospreyflow demo "
            "add enron --file <the file from CMU>`, which says what it is and asks first "
            "(ADR-114 Amendment 23); nothing was read."
        )
    if not (in_checkout or args.attested_checkout):
        raise NotProvisionedError(
            "The Enron seed only runs from a checkout of the repository, never from a built "
            "bundle: real data does not travel with one."
        )
    folder = Path(args.data_dir) / FOLDER
    if not folder.is_dir():
        raise NotProvisionedError(
            f"dataset not provisioned: {folder} is missing. `ospreyflow demo add enron --file "
            "<the file from CMU>` unpacks it there; nothing downloads it."
        )
    return folder


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_enron", description=__doc__
    )
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
        "--replace-links",
        action="store_true",
        help=(
            "Delete this seed's own email links (ids starting enron-comm-) and write them again, "
            "keeping every address and every other link to them (an analyst's Documents and "
            "marked entities). For a loader whose link counts changed (7 October 2026: copies of "
            "one email were counted as several); use with --replace-events for the events."
        ),
    )
    parser.add_argument(
        "--replace-events",
        action="store_true",
        help=(
            "Delete this case's own events and load them again, keeping the graph as it is. For a "
            "loader that now carries more on each event (ADR-089: the excerpt grew to 4,000 "
            "characters); without it a second events load is refused, since it would double every "
            "count."
        ),
    )
    parser.add_argument(
        "--method",
        choices=("upsert", "bulk"),
        default="bulk",
        help=(
            "How the graph links are written (ADR-058 Amendment 5): 'bulk', the default, in chunks "
            "through the adapter's bulk loader; 'upsert', the older path, one round trip set per "
            "link."
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
    args = parser.parse_args(argv)
    if args.replace_links and args.replace_graph:
        parser.error(
            "--replace-links keeps the addresses; --replace-graph deletes them: one, not both"
        )
    return args


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
        name=args.case_name, seeder=principal, grant_texts=list(args.grant), dataset=ENRON
    )
    scope = case.id
    print(f"Case {args.case_name!r} is {scope}.")

    plan = events_plan(
        already_loaded=events_already_loaded(args.analytics_db_path, scope),
        replace_events=args.replace_events,
        replace_links=args.replace_links,
    )
    if plan == "refuse":
        print(
            f"Case {scope!r} already has events loaded, and loading them again would double every "
            "count. Nothing was written. To load them again, use --replace-events: it deletes "
            "this case's own events first and keeps the graph.",
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
        graph = cast(
            GraphPort, stamping(GraphArcadeDBAdapter(client, scheme), dataset=ENRON.id)
        )
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
        if args.replace_links:
            removed_links = await clear_seeded_links(
                client,
                edge_type=groovy_identifier(physical_type_name("COMMUNICATED_WITH")),
                edge_prefix="enron-comm-",
            )
            print(f"  graph: removed {removed_links:,} links; every address kept")
        graph_present = bool(nodes) and await graph.get_node(nodes[0].id, principal) is not None
        step = graph_plan(
            present=graph_present,
            replace_graph=args.replace_graph,
            replace_links=args.replace_links,
            events=plan,
        )
        if step == "links":
            await write_graph(
                graph,
                [],
                edges,
                chunk=_GRAPH_CHUNK,
                nouns=("addresses", "links"),
                method=args.method,
            )
        elif step == "keep":
            # Only the events are being replaced: the graph stays exactly as it is.
            print("  graph: kept as it is (--replace-events reloads the events only)")
        elif step == "refuse":
            print(
                "The Enron graph is already loaded (or a load was interrupted). Nothing was "
                "written. To load again, use --replace-graph: it deletes this seed's own rows "
                "first.",
                file=sys.stderr,
            )
            return 1
        else:
            await write_graph(
                graph,
                nodes,
                edges,
                chunk=_GRAPH_CHUNK,
                nouns=("addresses", "links"),
                method=args.method,
            )
        await report_ids_stored_twice(
            client,
            edge_types=[groovy_identifier(physical_type_name("COMMUNICATED_WITH"))],
            prefix="enron-comm-",
            advice=KNOWN_STRAY_ADVICE,
        )
    finally:
        await client.aclose()

    if plan == "keep":
        print(f"Seeded {len(nodes)} addresses and {len(edges)} links into the graph.")
        print("  events: kept as they were; only the links were rewritten")
        return 0
    Path(args.analytics_db_path).parent.mkdir(parents=True, exist_ok=True)
    if plan == "replace":
        removed = delete_case_events(args.analytics_db_path, scope)
        print(f"  events: removed {removed:,} of this case's own, to load them again")
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


def graph_plan(*, present: bool, replace_graph: bool, replace_links: bool, events: str) -> str:
    """What the graph phase does, once `--replace-graph` has (or has not) cleared the graph:
    `write` all of it, `links` (the addresses kept, every email link written again), `keep` it as
    it is (only the events are being replaced), or `refuse` a second load over the first."""
    if not present:  # nothing to keep: with no addresses, links alone would have no ends
        return "write"
    if replace_links:
        return "links"
    if events == "replace":
        return "keep"
    return "refuse"


def events_plan(
    *, already_loaded: bool, replace_events: bool, replace_links: bool = False
) -> str:
    """What to do about a case's events: load them for the first time, replace them because the
    caller asked, `keep` them when only the links are being rewritten (the events are already
    right, and loading them again would double every count), or refuse because they are there and
    loading again would double every count."""
    if not already_loaded:
        return "load"
    if replace_events:
        return "replace"
    return "keep" if replace_links else "refuse"


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv if argv is not None else sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
