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

**The monitoring week** (`06_DECISIONS.md` ADR-108 Amendment 5, use cases A1 to A4). The seed
also writes the bank's next weekly export under `<ingest root>/uploaded/ledger/incoming/` (which
the Studio's listing does not show), the synthetic UK Sanctions List's version 1 at
`uploaded/ledger/lists/uk_sanctions_list.xml` and its version 2 under `incoming/`, and subscribes
"UK Sanctions List (synthetic)" to that file through the `uk_sanctions_list` connector, without
refreshing it (a refresh re-screens, which is the administrator's step on screen). Three mid-demo
commands copy files only, so the Conduit stays up (`python -m scripts.seed_internal ledger <flag>`):

    python -m scripts.seed_ledger_fixture --release-week-2        # the week's export, listed
    python -m scripts.seed_ledger_fixture --release-list-update   # the list's version 2 in place
    python -m scripts.seed_ledger_fixture --reset-week-2          # both put back; says what stays
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import cast

import duckdb
import yaml
from scripts.case_seed import add_case_arguments, check_case_arguments, parse_grant, scope_for
from scripts.load_screening_list import parse_list
from scripts.seed_support import KNOWN_STRAY_ADVICE, report_ids_stored_twice
from services.api.config import PostgresConfig
from services.api.dataset_scope import stamping
from services.api.ingest_sources import UPLOAD_SUBDIR, ingest_root
from services.api.investigations import AccessLevel
from services.api.media_store import open_media_store
from services.api.rule_evaluation import transaction_key
from services.api.screening import ScreeningListStore
from services.api.typology_rules import TypologyRuleStore

from adapters.analytics_duckdb.adapter import AnalyticsDuckDBAdapter
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from adapters.graph_arcadedb.gremlin_literals import groovy_identifier
from adapters.graph_arcadedb.naming import physical_type_name
from demo_fixtures import ledger_monitoring
from demo_fixtures.datasets import LEDGER
from demo_fixtures.ledger import build_ledger_graph, geometry_records
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import EventFilter, EventListRequest
from schemas.domain import Principal, TypologyRuleInput
from schemas.screening import ScreeningSubscriptionInput

SCREENING_LIST = (
    Path(__file__).resolve().parents[1] / "packages/demo_fixtures/screening_list_synthetic.yaml"
)


LISTS_FOLDER = SCREENING_LIST.parent / "screening_lists"
#: The mid-demo steps (ADR-108 Amendment 5), each a file copy that leaves the Conduit running.
MID_DEMO_STEPS = ("--release-week-2", "--release-list-update", "--reset-week-2")
#: Where the list's version 2 waits until it is released over the subscribed file.
LIST_V2_WAITING = "uk_sanctions_list_v2.xml"


class SeedRefusal(Exception):
    """A mid-demo step refused, in words, before anything was copied."""


def listed_folder(root: Path) -> Path:
    """The dataset's folder the Studio lists: `<root>/uploaded/ledger/`."""
    return root / UPLOAD_SUBDIR / LEDGER.id


def incoming_folder(root: Path) -> Path:
    """Beneath the listed folder, where the listing does not look: the week waits here."""
    return listed_folder(root) / ledger_monitoring.INCOMING


def list_file(root: Path) -> Path:
    """The file the UK Sanctions List subscription reads."""
    return listed_folder(root) / ledger_monitoring.UK_LIST_FILE


def list_location() -> str:
    """The subscription's location, relative to the ingest root (as `check_location` reads it)."""
    return f"{UPLOAD_SUBDIR}/{LEDGER.id}/{ledger_monitoring.UK_LIST_FILE}"


def _place(source: Path, destination: Path) -> None:
    """Copies `source` to `destination` whole or not at all, through a hidden part file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.parent / f".{destination.name}.part"
    try:
        shutil.copyfile(source, part)
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)


def write_monitoring_files(root: Path) -> list[str]:
    """The week's export under `incoming/`, the list's version 1 where the subscription reads it
    and its version 2 under `incoming/`. A second call rewrites every file byte for byte (so a
    reseed puts version 1 back). Answers what it wrote, in words."""
    written = ledger_monitoring.write_batches(listed_folder(root))
    _place(LISTS_FOLDER / ledger_monitoring.UK_LIST_V1, list_file(root))
    _place(LISTS_FOLDER / ledger_monitoring.UK_LIST_V2, incoming_folder(root) / LIST_V2_WAITING)
    return [
        *(f"wrote {w.name} ({w.rows} rows) under {listed_folder(root)}" for w in written),
        f"wrote the UK Sanctions List's version 1 at {list_file(root)}",
        f"wrote its version 2 at {incoming_folder(root) / LIST_V2_WAITING}",
    ]


def release_week_2(root: Path) -> str:
    """The week's export from `incoming/` into the listed folder, where the Studio offers it."""
    source = incoming_folder(root) / ledger_monitoring.WEEK_2
    destination = listed_folder(root) / ledger_monitoring.WEEK_2
    if not source.is_file():
        raise SeedRefusal(
            f"{ledger_monitoring.WEEK_2} is not at {source}: seed the dataset first "
            "(`ospreyflow demo add operation-ledger`)"
        )
    if destination.is_file() and destination.read_bytes() == source.read_bytes():
        return f"{ledger_monitoring.WEEK_2} is already in {listed_folder(root)}; nothing changed"
    _place(source, destination)
    return f"released {ledger_monitoring.WEEK_2} into {listed_folder(root)}"


def release_list_update(root: Path) -> str:
    """The list's version 2 over the subscribed file; *Refresh now* then applies and re-screens."""
    source = incoming_folder(root) / LIST_V2_WAITING
    if not source.is_file():
        raise SeedRefusal(
            f"the list's version 2 is not at {source}: seed the dataset first "
            "(`ospreyflow demo add operation-ledger`)"
        )
    if list_file(root).is_file() and list_file(root).read_bytes() == source.read_bytes():
        return "the UK Sanctions List's file is already version 2; nothing changed"
    _place(source, list_file(root))
    return (
        f"released the UK Sanctions List's version 2 over {list_file(root)}: refresh it in "
        "Monitoring → Lists (Refresh now) to apply it and re-screen"
    )


#: What `--reset-week-2` cannot undo, said every time it runs.
CANNOT_UNDO = (
    "the week's load: revert it with `python -m scripts.revert_load <load id> --reverted-by <you>` "
    "(the load id is on the Studio's run; stop the Conduit first with the DuckDB engine)",
    "the rules deployed and the hotlist made in the rehearsal: retire them in Monitoring",
    "the alerts the week and the list update raised, and their closes",
    "the list's applied versions: refresh the list after this reset to apply version 1 again (it "
    "delists the added designation and raises nothing)",
)


def reset_week_2(root: Path) -> str:
    """The released export removed from the listed folder, and the list's version 1 put back at the
    subscribed file; then what it cannot undo, in words."""
    lines: list[str] = []
    released = listed_folder(root) / ledger_monitoring.WEEK_2
    if released.is_file():
        released.unlink()
        lines.append(f"removed {ledger_monitoring.WEEK_2} from {listed_folder(root)}")
    else:
        lines.append(f"{ledger_monitoring.WEEK_2} was not in {listed_folder(root)}")
    _place(LISTS_FOLDER / ledger_monitoring.UK_LIST_V1, list_file(root))
    lines.append(f"put the UK Sanctions List's version 1 back at {list_file(root)}")
    lines.append("It cannot undo:")
    lines.extend(f"  - {item}" for item in CANNOT_UNDO)
    return "\n".join(lines)


def run_mid_demo(step: str, root: Path) -> str:
    if step == "--release-week-2":
        return release_week_2(root)
    if step == "--release-list-update":
        return release_list_update(root)
    if step == "--reset-week-2":
        return reset_week_2(root)
    raise SeedRefusal(f"{step} is not one of {', '.join(MID_DEMO_STEPS)}")


async def subscribe_uk_list(store: ScreeningListStore, by: str) -> str:
    """Subscribes the synthetic UK Sanctions List to the seed's file, unless a list of that name is
    there already (a reseed leaves its versions as they are). Never refreshes it."""
    if await store.subscription(ledger_monitoring.UK_LIST_NAME) is not None:
        return f"{ledger_monitoring.UK_LIST_NAME!r} is subscribed already"
    await store.subscribe(
        ScreeningSubscriptionInput(
            list_name=ledger_monitoring.UK_LIST_NAME,
            source=ledger_monitoring.UK_LIST_SOURCE,  # type: ignore[arg-type]
            location=list_location(),
        ),
        by,
        synthetic=True,
    )
    return (
        f"subscribed {ledger_monitoring.UK_LIST_NAME!r} to {list_location()} (not yet refreshed: "
        "refresh it in Monitoring → Lists)"
    )


async def deploy_screening_rule(
    rules: TypologyRuleStore,
    case: str,
    grants: list[str],
    *,
    clearance: str,
    org_unit: str,
) -> str:
    """Makes the case's screening rule live (step 9d finding 4): A3's list update raises its alert
    only through an active `kyc_screening` rule, and the seed had never deployed one. Deployed from
    the KYC screening template's defaults (`ledger_monitoring.SCREENING`), after each load commits,
    in the Ledger's dataset, **as the case's Author** (the first `--grant ACCOUNT=author`), as that
    Author would from Monitoring → Rules → Templates: a case rule is the Author's to deploy, and the
    list refresh runs it as its deployer, so it must be an account the identity provider knows,
    never the seed's own worker. Left as it is when one of that name is live already (a reseed);
    deployed afresh when a rehearsal retired it."""
    authors = [a for a, level in map(parse_grant, grants) if level is AccessLevel.AUTHOR]
    name = ledger_monitoring.SCREENING_NAME
    if not authors:
        return f"{name!r} was not deployed: no case Author was granted (--grant ACCOUNT=author)"
    author = Principal(id=authors[0], clearance=clearance, org_unit=org_unit, datasets=[LEDGER.id])
    live = [
        r
        for r in await rules.list_for_case(case, author)
        if r.status == "active" and r.name == name and r.params.typology == "kyc_screening"
    ]
    if live:
        return f"{name!r} is live already"
    await rules.create(
        author,
        case,
        TypologyRuleInput.model_validate(
            {"name": name, "params": dict(ledger_monitoring.SCREENING)}
        ),
    )
    return f"deployed {name!r} from the KYC screening template, as the case's Author"


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
    # `seed_internal`'s mid-demo runner passes the demo engineer's subject; file steps need none.
    parser.add_argument("--run-as", default=None, help=argparse.SUPPRESS)
    steps = parser.add_mutually_exclusive_group()
    for step in MID_DEMO_STEPS:
        steps.add_argument(step, action="store_true")
    args = parser.parse_args(argv)
    if not any(getattr(args, s.lstrip("-").replace("-", "_")) for s in MID_DEMO_STEPS):
        check_case_arguments(parser, args)
    return args


def mid_demo_step(args: argparse.Namespace) -> str | None:
    for step in MID_DEMO_STEPS:
        if getattr(args, step.lstrip("-").replace("-", "_")):
            return step
    return None


async def _event_keys(
    analytics: AnalyticsPort, principal: Principal, scope: str
) -> set[tuple[object, ...]]:
    """Every event already in the case, as its transaction key — paged to the end."""
    keys: set[tuple[object, ...]] = set()
    offset = 0
    while True:
        page = await analytics.list_events(
            EventListRequest(
                filter=EventFilter(investigation_scope=scope), offset=offset, limit=200
            ),
            principal,
        )
        keys.update(transaction_key(e) for e in page.events)
        offset += len(page.events)
        if not page.events or offset >= page.total:
            return keys


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

    media = open_media_store()
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
        # A re-seed into the same case must not write each transaction's event again (the
        # analytics store inserts; ADR-109 Amendment 1): only events not already there load,
        # judged by the one definition of "the same transaction" the typology rules use.
        already = await _event_keys(analytics, principal, scope)
        await analytics.load_events(
            [e for e in result.events if transaction_key(e) not in already]
        )
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
    monitoring = write_monitoring_files(ingest_root())
    screening = await ScreeningListStore.connect(PostgresConfig.from_env().dsn)
    try:
        await screening.replace_list(list_name, entries)
        monitoring.append(await subscribe_uk_list(screening, principal.id))
    finally:
        await screening.close()
    rules = await TypologyRuleStore.connect(PostgresConfig.from_env().dsn)
    try:
        monitoring.append(
            await deploy_screening_rule(
                rules, scope, list(args.grant), clearance=args.clearance, org_unit=args.org_unit
            )
        )
    finally:
        await rules.close()

    print(
        f"Seeded Operation Ledger: {result.transactions_loaded} transactions "
        f"({len(result.events)} timeline events), the SAR "
        f"({result.sar_document_id or 'not written: its recipe wrote no document'}), and "
        f"{len(geometry_records())} map points under investigation_scope={scope!r}; "
        f"the screening list {list_name!r} ({len(entries)} synthetic entries)."
    )
    print("The monitoring week (ADR-108 Amendment 5): " + "; ".join(monitoring) + ".")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    step = mid_demo_step(args)
    if step is not None:
        try:
            print(run_mid_demo(step, ingest_root()))
        except SeedRefusal as refused:
            print(f"refused: {refused}", file=sys.stderr)
            return 1
        return 0
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
