"""Reverts a load: `python -m scripts.revert_load <load_id> --reverted-by <principal id>`
(`06_DECISIONS.md` ADR-127 decision 6; the logic is `services/ingest/load_revert.py`).

`<load_id>` is a load's id, a pipeline branch's id (`<run>:<node>`), or a pipeline run's id, which
means every branch of it. The principal is recorded as `reverted_by` in the run ledger and in the
audit trail; it is not checked against anyone, so name the person who is doing this.

Run it inside the network where ArcadeDB, Postgres and the analytics store are reachable. The
analytics store is opened first, so a store that cannot be opened stops the command before it
changes anything. **With the DuckDB engine the analytics file belongs to one process:** stop the
Conduit before running this, or the file cannot be opened. ClickHouse has no such limit.

Exit codes: 0 reverted, 1 refused (nothing was changed), 2 stopped part way (run it again to
complete it: every step can be repeated), 64 `--show-ids` asked without a principal to read as.

A refusal names its reason and a count. With `--show-ids` it also lists the ids of what the load
merged into, but only those the `--reverted-by` principal can read, asked of the graph as that
principal; the rest stay a count, because a link's id told to someone who may not read that link
says it exists. The principal is built the way the seed scripts build theirs, from arguments:
`--clearance` and `--org-unit` (and `--dataset`, `--receivable-code` where it has them). Without a
clearance and a unit there is nothing to read as, and `--show-ids` is refused before anything runs.

**The working sets, the history and the caches.** The revert also takes the load's nodes and links
(and the links at those nodes) out of every case's working set in Valkey, whoever may read them,
publishes each case's removal so every Conduit instance projects it for its connected readers,
takes them out of the stored history steps, closes the alerts that cite its events, and clears the
Conduit's kept results (`cache:*` in the same Valkey, so every instance at once). It needs the
Valkey the Conduit uses (`VALKEY_*`). It also releases the row keys each load kept for its case
(ADR-127 decision 5), so a rerun of the file loads those rows again.

**Quiesce the Conduit.** Run a revert with the Conduit quiet. With the DuckDB engine that is
required, since the analytics file belongs to one process. With ClickHouse it is advised: a Conduit
left running can race the revert (an expand that read the graph before the graph step can add an
element to a case after it was removed), and the revert guards for it only by removing from the
working sets a second time as its last step before the ledger mark, which finds what was added back
in between and nothing a later write adds.

**The clearance is self-declared.** `--clearance` and `--org-unit` are whatever the operator types:
nothing checks them against the identity provider, so the `--show-ids` filter is a courtesy, not
access control. The script must never be routed through the Conduit (a route, a worker, a button),
where a caller's own clearance is what the access step has to be given.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from services.api.alerts import AlertStore
from services.api.analytics_store import open_analytics
from services.api.audit import AuditWriter
from services.api.cache import invalidate_every_cache
from services.api.config import DEFAULT_ANALYTICS_DB_PATH, PostgresConfig, ValkeyConfig
from services.api.held_rows import HeldRowStore
from services.api.history import InvestigationHistoryStore
from services.api.recipe_runs import RecipeRunStore
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore
from services.api.working_set_revert import WorkingSetReverter
from services.ingest.load_revert import (
    Refusal,
    RevertDeps,
    RevertIncomplete,
    RevertRefused,
    RevertResult,
    revert,
)
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from ports.graph import GraphPort
from schemas.domain import Principal

Revert = Callable[..., Awaitable[RevertResult]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.revert_load", description="Revert a load, its releases first."
    )
    parser.add_argument("load_id", help="a load's id, a branch's id, or a pipeline run's id")
    parser.add_argument(
        "--reverted-by", required=True, help="the principal id to record as having reverted it"
    )
    parser.add_argument(
        "--show-ids",
        action="store_true",
        help=(
            "in a refusal, also list the ids of the elements the load merged into that "
            "--reverted-by can read (needs --clearance and --org-unit)"
        ),
    )
    parser.add_argument("--clearance", help="the principal's clearance, for --show-ids")
    parser.add_argument("--org-unit", help="the principal's unit, for --show-ids")
    parser.add_argument(
        "--dataset",
        action="append",
        default=None,
        help="a dataset the principal reads (repeat); none given reads every dataset",
    )
    parser.add_argument(
        "--receivable-code",
        action="append",
        default=[],
        help="a restricted handling code the principal may receive (repeat)",
    )
    return parser


def viewer_from(args: argparse.Namespace) -> Principal | None:
    """The principal `--show-ids` reads as, or `None` when the arguments do not make one: both a
    clearance and a unit are needed, as for the seed scripts' principal."""
    if not args.clearance or not args.org_unit:
        return None
    return Principal(
        id=args.reverted_by,
        clearance=args.clearance,
        org_unit=args.org_unit,
        receivable_handling_codes=list(args.receivable_code),
        datasets=args.dataset,
    )


async def _readable(refusal: Refusal, graph: GraphPort, viewer: Principal) -> list[str]:
    """Of the ids a refusal holds, those `viewer` can read: asked of the graph as `viewer`, which
    leaves out what the access step hides."""
    if refusal.reason == "merged_nodes":
        return [n.id for n in await graph.get_nodes(list(refusal.ids), viewer)]
    return [e.id for e in await graph.get_edges(list(refusal.ids), viewer)]


async def run(
    load_id: str,
    *,
    reverted_by: str,
    deps: RevertDeps,
    now: datetime,
    show_ids: bool = False,
    viewer: Principal | None = None,
    say: Callable[[str], None] = print,
    revert: Revert = revert,
) -> int:
    """The revert and what to say of it; the exit code. `say` and `revert` are replaceable so a test
    needs no store."""
    if show_ids and viewer is None:
        say("--show-ids needs a principal to read as: give --clearance and --org-unit.")
        return 64
    try:
        result = await revert(load_id, reverted_by=reverted_by, deps=deps, now=now)
    except RevertRefused as refused:
        for refusal in refused.refusals:
            say(refusal.words())
            if show_ids and viewer is not None and refusal.ids:
                readable = await _readable(refusal, deps.graph, viewer)
                if readable:
                    say("  " + ", ".join(readable))
                if len(refusal.ids) > len(readable):
                    say(f"  and {len(refusal.ids) - len(readable)} more, not shown")
        say("Refused: nothing was changed.")
        if not show_ids and any(r.ids for r in refused.refusals):
            say("(--show-ids lists those you can read; it needs --clearance and --org-unit.)")
        return 1
    except RevertIncomplete as incomplete:
        for done in incomplete.done:
            say(f"Reverted {done.load_id}.")
        say(str(incomplete))
        return 2
    for done in result.reverted:
        say(
            f"Reverted {done.load_id}: {done.nodes} node(s), {done.links} link(s), "
            f"{done.events} event(s), {done.geometries} point(s), "
            f"{done.held_rows} held row(s) discarded, {done.alerts} alert(s) closed."
        )
        if done.cases:
            say(f"  {done.cases} working set(s) cleared of it, and each connected reader told.")
        if done.alerts_citing_events:
            say(f"  {done.alerts_citing_events} alert(s) citing its events closed.")
        if done.nodes_left_alone:
            say(
                f"  {done.nodes_left_alone} node(s) left alone: a later load wrote them again "
                "after this one."
            )
        if done.geometries_kept:
            say(f"  {done.geometries_kept} point(s) kept: a live node still names them.")
    for earlier in result.already_reverted:
        say(f"{earlier} was already reverted, and was left.")
    return 0


async def _main(args: argparse.Namespace) -> int:
    if args.show_ids and viewer_from(args) is None:
        print("--show-ids needs a principal to read as: give --clearance and --org-unit.")
        return 64  # before any store is opened
    scheme = load_uk_le_scheme()
    dsn = PostgresConfig.from_env().dsn
    # Opened first: a store that will not open stops the command before it changes anything.
    analytics, close_analytics = await open_analytics(
        os.environ.get("OSPREY_ANALYTICS_ENGINE", "duckdb"),
        duckdb_path=os.environ.get("ANALYTICS_DB_PATH", DEFAULT_ANALYTICS_DB_PATH),
        handling_scheme=scheme,
    )
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    ledger = await RecipeRunStore.connect(dsn)
    held = await HeldRowStore.connect(dsn, scheme)
    alerts = await AlertStore.connect(dsn)
    audit = await AuditWriter.connect(dsn)
    history = await InvestigationHistoryStore.connect(dsn)
    valkey_config = ValkeyConfig.from_env()
    valkey = Valkey(host=valkey_config.host, port=valkey_config.port, db=valkey_config.db)
    try:
        graph = GraphArcadeDBAdapter(client, scheme)
        # From outside the Conduit, as `strip_change_provenance` reaches the working sets: the
        # store on Valkey, the removal published on each case's channel, the stored history, and
        # the kept results, which are keys in the same Valkey.
        working_sets = WorkingSetReverter(
            WorkingSetService(graph, ValkeyWorkingSetStore(valkey), scheme, valkey=valkey),
            valkey,
            history,
        )
        deps = RevertDeps(
            ledger=ledger,
            graph=graph,
            analytics=analytics,
            held_rows=held,
            alerts=alerts,
            audit=audit,
            working_sets=working_sets,
            invalidate_caches=lambda: invalidate_every_cache(valkey),
        )
        return await run(
            args.load_id,
            reverted_by=args.reverted_by,
            deps=deps,
            now=datetime.now(UTC),
            show_ids=args.show_ids,
            viewer=viewer_from(args),
        )
    finally:
        await client.aclose()
        await ledger.close()
        await held.close()
        await alerts.close()
        await audit.close()
        await history.close()
        await valkey.aclose()
        await close_analytics()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
