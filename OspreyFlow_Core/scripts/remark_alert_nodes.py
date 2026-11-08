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
links (`WorkingSetService.remove_reverted`: each case's stream dropped and one removal appended,
so its clients are sent a fresh projected snapshot): a stored copy keeps the marking it was copied
with and is served from the store, so it would still go to a reader below the new marking. The
run's re-marks are one record of the alert store's repoint journal, so a run that fails part-way
is finished, and its copies purged, by the next settle and working-set read, or the next run.

`--dry-run` writes nothing; it lists what a run would re-mark. Idempotent: a second run finds every
node at its marking and no copy of an old one, and reports 0. A dry run still opens the alert
store, whose start-up DDL creates its tables if absent.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from services.api.alerts import AlertStore, RemarkReport, purge_remarked_copies, remark_alerts
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.working_set.service import WorkingSetService
from services.api.working_set.store import ValkeyWorkingSetStore
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
    working_set: WorkingSetService | None = None,
) -> RemarkReport:
    """Every alert's node (or one case's, `investigation_id`), re-marked where it is below what it
    rests on now (`alerts.remark_alerts`, which every repoint also runs); with `dry_run`, listed and
    not changed. A run's re-marks are one record of the alert store's repoint journal (ADR-109
    Amendment 10): each supersede recorded before its commit, so a run that fails part-way is
    finished by the next settle, and the superseded nodes' working-set copies purged, by this run
    or, after a failure, by the next working-set read or run (`purge_remarked_copies`)."""
    rows = await alerts.with_alert_nodes(investigation_id=investigation_id)
    if dry_run:
        return await remark_alerts(graph, alerts, scheme, rows, dry_run=True)
    if working_set is not None:
        await purge_remarked_copies(alerts, working_set)  # what an earlier run left to purge
    async with alerts.repointing(graph) as repoint:
        report = await remark_alerts(graph, alerts, scheme, rows, on_supersede=repoint.record_node)
    if working_set is not None and repoint.remarked_nodes:
        await working_set.remove_reverted(repoint.remarked_nodes, [])
        await repoint.purged()
        report.cases_purged = len(repoint.remarked_nodes)
    return report


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
    graph = GraphArcadeDBAdapter(client, scheme)
    try:
        report = await remark(
            graph, alerts, scheme, dry_run=args.dry_run,
            working_set=WorkingSetService(graph, ValkeyWorkingSetStore(valkey), scheme),
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
        print(f"{report.cases_purged} superseded node(s) removed from the working sets.")
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
