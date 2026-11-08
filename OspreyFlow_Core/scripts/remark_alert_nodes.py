"""Re-marks the `Alert` nodes written before `7fac778` below the links their alerts cite.

Until L2.8 (ADR-146 decision 10, the orchestrator's item ii) a rule's `Alert` node was marked no
lower than its entities and transactions, but not the links it cites, so a link marked above its
ends left the node, and the finding's words it carries, readable to someone who may not see the
link (rule 3). From `7fac778` a new node counts its links; this script re-marks what was written
before. Run it once per deployment, inside the network where ArcadeDB and Postgres are reachable,
first with `--dry-run`:

    python -m scripts.remark_alert_nodes --dry-run
    python -m scripts.remark_alert_nodes

For each alert with a node, its required marking is the highest of what it rests on now, read as
the service principal: its entities, the links it cites, its node's own marking (never lowered), and
the transactions its raiser read (the alert's stored handlings). A node below it is superseded by a
revision at that marking (`supersede_node`, which carries its `ALERTED_ON` links to the new node,
whose SECRET end then hides each from a reader below it) and the alert is pointed at the revision,
only if it still names the old one. An alert whose referents' restricted markings belong to
different units has no single safe marking; it is listed, not changed.

Then every working set (Valkey) holding a copy of a node it re-marked loses that copy and its
links, and the case's delta stream is deleted: a stored copy keeps the marking it was copied with
and is served from the store, not read again from the graph, so it would still go to a reader
below the new marking. With the stream gone, `deltas_after` finds a gap and every client of the
case is sent a full projected snapshot from what is stored now. The re-marked revision is not put
in its place: the case's analysts open the alert again to draw it, at its marking.

`--dry-run` writes nothing; it lists what a run would re-mark. Idempotent: a second run finds every
node at its marking and no copy of an old one, and reports 0.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

from services.api.alerts import AlertStore, RemarkReport, remark_alerts
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.working_set.store import ValkeyWorkingSetStore, WorkingSetStorage
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import HandlingScheme, load_uk_le_scheme
from ports.graph import GraphPort


async def remark(
    graph: GraphPort,
    alerts: AlertStore,
    scheme: HandlingScheme,
    *,
    dry_run: bool,
    investigation_id: str | None = None,
    working_sets: WorkingSetStorage | None = None,
    valkey: Any = None,
) -> RemarkReport:
    """Every alert's node (or one case's, `investigation_id`), re-marked where it is below what it
    rests on now (`alerts.remark_alerts`, which every repoint also runs); with `dry_run`, listed and
    not changed."""
    rows = await alerts.with_alert_nodes(investigation_id=investigation_id)
    report = await remark_alerts(graph, alerts, scheme, rows, dry_run=dry_run)
    if working_sets is not None and not dry_run:
        old = {a.alert_node_id for a in rows if a.alert_node_id and a.id in report.remarked}
        report.cases_purged = await purge_working_sets(working_sets, valkey, old) if old else 0
    return report


async def purge_working_sets(store: WorkingSetStorage, valkey: Any, old_node_ids: set[str]) -> int:
    """Every case's stored copy of a re-marked node, and its links, removed, and the case's delta
    stream deleted so its clients take a fresh snapshot. Returns how many cases changed."""
    changed = 0
    for case in await store.case_ids():
        held = sorted(await store.node_ids(case) & old_node_ids)
        if not held:
            continue
        links = {e for ids in (await store.adjacent_edge_ids(case, held)).values() for e in ids}
        await store.remove_edges(case, sorted(links))
        await store.remove_nodes(case, held)
        await valkey.delete(f"ws:{case}:deltas")
        changed += 1
    return changed


async def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.remark_alert_nodes")
    parser.add_argument("--dry-run", action="store_true", help="list what a run would re-mark")
    args = parser.parse_args(argv)
    scheme = load_uk_le_scheme()
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    alerts = await AlertStore.connect(PostgresConfig.from_env().dsn)
    valkey_config = ValkeyConfig.from_env()
    valkey = Valkey(host=valkey_config.host, port=valkey_config.port, db=valkey_config.db)
    try:
        report = await remark(
            GraphArcadeDBAdapter(client, scheme), alerts, scheme, dry_run=args.dry_run,
            working_sets=ValkeyWorkingSetStore(valkey), valkey=valkey,
        )  # fmt: skip
    finally:
        await client.aclose()
        await alerts.close()
        await valkey.aclose()
    verb = "would be re-marked" if args.dry_run else "re-marked"
    print(f"{report.checked} alert node(s) checked; {len(report.remarked)} {verb}.")
    for alert_id in report.remarked:
        print(f"  {alert_id}")
    if not args.dry_run:
        print(f"{report.cases_purged} working set(s) lost a stale copy and will snapshot afresh.")
    if report.unsafe:
        print(f"{len(report.unsafe)} alert(s) have no single safe marking and were left: "
              + ", ".join(report.unsafe))  # fmt: skip
    if not report.remarked:
        print("Nothing needed changing.")
    elif not args.dry_run:
        print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
