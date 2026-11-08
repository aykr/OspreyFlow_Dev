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

`--dry-run` writes nothing; it lists what a run would re-mark. Idempotent: a second run
finds every node at its marking and reports 0. Not done here: a case's working-set copy of an old
node keeps the marking it was copied with until the case's next read of it from the graph.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass, field

from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.rule_evaluation import alert_handling
from services.resolve.trigger import service_principal

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_node_id, now_utc
from ontology.handling import HandlingScheme, load_uk_le_scheme
from ports.graph import GraphPort
from schemas.domain import NodeWrite


@dataclass
class RemarkReport:
    """What a run changed, or would change. `remarked` is what a second run must report empty."""

    remarked: list[str] = field(default_factory=list)
    unsafe: list[str] = field(default_factory=list)
    checked: int = 0


async def remark(
    graph: GraphPort,
    alerts: AlertStore,
    scheme: HandlingScheme,
    *,
    dry_run: bool,
    investigation_id: str | None = None,
) -> RemarkReport:
    """Every alert's node (or one case's, `investigation_id`), re-marked where it is below what it
    rests on now; with `dry_run`, listed and not changed."""
    reader = service_principal(scheme)
    report = RemarkReport()
    for alert in await alerts.with_alert_nodes(investigation_id=investigation_id):
        assert alert.alert_node_id is not None
        node = await graph.get_node(alert.alert_node_id, reader)
        if node is None:
            continue  # taken back or superseded since: nothing to re-mark
        report.checked += 1
        referents = await graph.get_nodes(sorted(set(alert.referent_node_ids)), reader)
        links = await graph.get_edges(sorted(set(alert.edge_ids)), reader) if alert.edge_ids else []
        rests_on = [node.handling, *(n.handling for n in referents), *(e.handling for e in links),
                    *(await alerts.handlings_of(alert.id) or [])]  # fmt: skip
        required = alert_handling(scheme, rests_on)
        if required is None:
            report.unsafe.append(alert.id)
            continue
        if required == node.handling:
            continue
        report.remarked.append(alert.id)
        if dry_run:
            continue
        tx = await graph.begin_transaction()
        try:
            revision = await graph.supersede_node(
                node.id,
                NodeWrite(
                    id=new_node_id(),
                    type=node.type,
                    properties=node.properties,
                    provenance=node.provenance,
                    handling=required,
                    created_by="remark_alert_nodes",
                    created_at=now_utc(),
                    datasets=node.datasets,
                ),  # fmt: skip
                tx,
            )
        except Exception:
            await graph.rollback_transaction(tx)
            raise
        await graph.commit_transaction(tx)
        await alerts.set_alert_node(alert.id, revision, was=node.id)
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
    try:
        report = await remark(
            GraphArcadeDBAdapter(client, scheme), alerts, scheme, dry_run=args.dry_run
        )
    finally:
        await client.aclose()
        await alerts.close()
    verb = "would be re-marked" if args.dry_run else "re-marked"
    print(f"{report.checked} alert node(s) checked; {len(report.remarked)} {verb}.")
    for alert_id in report.remarked:
        print(f"  {alert_id}")
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
