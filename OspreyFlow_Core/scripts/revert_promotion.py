"""Reverts a promotion: `python -m scripts.revert_promotion <load_id> --reverted-by <principal id>
[--dry-run]` (`06_DECISIONS.md` ADR-143 decision 8; the logic is
`revert_promotion` below, in this operator module alone).

A promotion is a load (trigger `analyst_promotion`, `layer_merge` or `drawn_merge`) that added a
dataset to drawn elements of a case's analyst layer or of a drawn dataset. Its revert takes that
dataset back from exactly those elements, in one transaction, so each is in the case's layer only
again, as it was before; records the promotion `reverted`; clears its board items' `promoted_at`;
audits it under `--reverted-by`; and clears the Conduit's kept results (`cache:*` in the shared
Valkey), since what was counted included the promoted elements. Nothing is deleted. A drawn
dataset's merge (L3.9) is undone whole: its matches' `SAME_AS`, and its retyped copies with their
links and `SAME_AS` back (Amendment 7), withdrawn in the same transaction,
then its case back on its drawing and the views it made boards again (ADR-143 Amendment 2 decision
7, reverted).

**Stop the Conduit**, as for any load's revert (ADR-127 Amendment 9): the command opens a bare
connection to the Conduit's address (`OSPREY_CONDUIT_URL`, default `http://api:8000`; no route is
asked) and goes on only when it can tell the Conduit is stopped (its host resolves and the
connection is refused): an answer, a name that does not
resolve, a timeout, anything else refuses. There is no online revert:
the owner settled ADR-143 open question 2 as (a), this command alone (Amendment 5 decision 8), and
it must never be routed through the Conduit.

`--dry-run` says what would be reverted and writes nothing: it reads the promotion's record alone.

Run it inside the deployment's network (its `deployment.env`), where ArcadeDB, Postgres and Valkey
are reachable; with no store settings it refuses rather than reach whatever answers on
localhost:2480.

Exit codes: 0 reverted (or the dry run's report), 1 refused (nothing changed), 64 no store settings.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal

from services.api.audit import AuditWriter
from services.api.board_store import PostgresBoardItemStore
from services.api.cache import invalidate_every_cache
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.datasets import PostgresDatasetStore
from services.api.drawn_merge import MergeCommit
from services.api.promotion_store import PostgresPromotionStore, PromotionRecord, PromotionStore
from services.api.promotions import LAYER_DELETE_PREFIX, LAYER_DELETER, PromotionRefused
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

STORE_SETTINGS = ("ARCADEDB_HOST", "ARCADEDB_HTTP_PORT")
NO_STORE_SETTINGS = (
    "No store settings: nothing says where this deployment's stores are, and the defaults would "
    "reach whatever answers on localhost:2480. Run it inside the deployment instead."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("load_id", help="the promotion's load id (promotion-…)")
    parser.add_argument("--reverted-by", required=True, help="the principal doing this")
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    return parser


async def revert_promotion(
    record: PromotionRecord,
    graph: Any,
    store: PromotionStore,
    items: Any,
    merge: Any | None = None,
) -> PromotionRecord:
    """The revert of a committed promotion: the dataset taken back from exactly its elements in
    one transaction, the promotion recorded `reverted`, its items' `promoted_at` cleared. The
    operator command's core, run with the Conduit stopped (ADR-127
    Amendment 9); never a route (ADR-143 open question 2, settled (a): Amendment 5 decision 8).

    Refused, as a load's revert is (ADR-127 Amendment 6, `live_edges_touching`), while a
    live link other than the promotion's own and the case's own unpromoted drawing rests on one of
    its nodes: another case's link or a later load's would be left resting on a node gone from the
    dataset. A promotion from a layer since deleted takes its elements out with the layer."""
    if record.status != "committed":
        raise PromotionRefused(
            "not_committed",
            f"Promotion {record.load_id} is {record.status}: nothing to revert.",
        )
    drawn_merge = record.trigger == "drawn_merge"
    if drawn_merge and merge is None:
        raise PromotionRefused("no_merge", "A drawn dataset's merge is reverted with its stores.")
    # A drawn merge's own matches rest on its nodes, and go with it.
    matched = await store.matches_of(record.id) if drawn_merge else []
    own_matches = {r.edge_id for r in matched if r.edge_id}
    # Its retyped copies (Amendment 7) go with it too: their links and `SAME_AS` are its own, and
    # a link written since onto a copy refuses the revert as one onto a promoted node does.
    copies = await store.copies_of(record.id) if drawn_merge else []
    copy_nodes = [c.written_id for c in copies if c.kind == "node" and c.written_id]
    own_matches |= {c.written_id for c in copies if c.kind == "link" and c.written_id}
    own_matches |= {c.same_as_id for c in copies if c.same_as_id}
    # A drawn link that went in as a copy stays drawn, resting where it was drawn.
    own_matches |= {c.original for c in copies if c.kind == "link"}
    held = await items.in_case(record.case_id)
    own_drawing = {
        i.element_id for i in held
        if i.kind != "node" and i.withdrawn_at is None and i.promoted_at is None
    }  # fmt: skip
    layer_deleted = await store.layer_deleted(record.layer_id)
    tx = await graph.begin_transaction()
    try:
        # Whatever the operator may read (the unfiltered lookup a load's revert asks too): this
        # is an operator's command, never a route, and the one module outside the load revert
        # that names it (`test_unfiltered_node_lookup_confined.py`). Read inside the revert's own
        # transaction, so the check and the writes are one view of the graph (the independent
        # review of L3.4, item 4).
        resting = await graph.live_edges_touching([*record.node_ids, *copy_nodes], tx=tx)
        others = set(resting) - set(record.edge_ids) - own_drawing - own_matches
        if others:
            raise PromotionRefused(
                "links_rest_on_it",
                f"{len(others)} link(s) written since rest on its items: revert those first.",
            )
        await graph.revert_promotion(record.load_id, record.dataset_id, tx)
        if drawn_merge and merge is not None:  # refused above without it
            await merge.undo_writes(record, tx)
        if layer_deleted:
            await graph.withdraw_layer(
                record.layer_id, f"{LAYER_DELETE_PREFIX}{record.case_id}", tx
            )
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    if not await store.decide(
        record.id, was="committed", now="reverted", by=None, at=datetime.now(UTC)
    ):
        await graph.rollback_transaction(tx)
        raise PromotionRefused("already_decided", "This promotion has changed since it was read.")
    await graph.commit_transaction(tx)
    await items.mark_promoted(record.case_id, list(record.item_ids), None)
    if drawn_merge and merge is not None:
        await merge.undo(record)
    if layer_deleted:
        await items.withdraw(
            record.case_id, list(record.item_ids), LAYER_DELETER, datetime.now(UTC)
        )
    return replace(record, status="reverted")


#: Where the Conduit answers inside the deployment's network (`harness/reporting.py`'s
#: `REPORT_SYNC_CONDUIT_URL`), and its unauthenticated liveness route.
CONDUIT_URL_SETTING = "OSPREY_CONDUIT_URL"
DEFAULT_CONDUIT_URL = "http://api:8000"
CONDUIT_RUNNING = (
    "Refused: the Conduit is running, and a promotion's revert needs it stopped (ADR-127 "
    "Amendment 9; ADR-143 Amendment 5 decision 8): a running Conduit could write a link onto its "
    "items between the check and the revert. Stop it and run again. Nothing was changed."
)
CONDUIT_UNKNOWN = (
    "Refused: this command cannot tell whether the Conduit is stopped ({why}). Run it inside the "
    "deployment's network, or set OSPREY_CONDUIT_URL to where the Conduit answers. Nothing was "
    "changed."
)
Conduit = Literal["running", "stopped", "unknown"]


async def conduit_state() -> tuple[Conduit, str]:
    """Whether the Conduit is running, asked of its address (`OSPREY_CONDUIT_URL`, default
    `http://api:8000`). Fails closed: `stopped` only when its host resolves and the connection is
    refused (nothing listens there); a connection accepted is `running` (something holds the
    Conduit's port); a name that does not resolve (run from the host, say), a timeout or any other
    failure is `unknown`, which refuses as `running` does (the lane review, finding 2). Asked as a
    TCP connect: an HTTP client folds a refusal into its other failures."""
    import socket
    from urllib.parse import urlsplit

    parts = urlsplit(os.environ.get(CONDUIT_URL_SETTING, DEFAULT_CONDUIT_URL))
    host, port = parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80)
    try:
        await asyncio.get_running_loop().getaddrinfo(host, port)
    except (socket.gaierror, UnicodeError) as unresolved:
        return "unknown", f"{host} does not resolve here: {unresolved}"
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3.0)
    except ConnectionRefusedError:
        return "stopped", ""
    except (OSError, TimeoutError) as failed:
        return "unknown", f"{host}:{port}: {failed or type(failed).__name__}"
    writer.close()
    return "running", ""


def stop_if_dry(dry_run: bool, says: str) -> bool:
    """The dry run's one stop, before the audit and before anything is written."""
    if dry_run:
        print(f"Would revert {says}, leaving each in the case's layer only. Nothing was written.")
    return dry_run


async def run(
    load_id: str,
    *,
    reverted_by: str,
    dry_run: bool,
    store: PromotionStore,
    graph: Any,
    items: Any,
    audit: Any,
    invalidate: Any,
    conduit: Any = conduit_state,
    merge: Any | None = None,
) -> int:
    record = await store.by_load(load_id)
    if record is None:
        print(f"No promotion has the load id {load_id}. Nothing was changed.")
        return 1
    # A drawn merge's retyped copies (ADR-143 Amendment 7) are its own writes, withdrawn with it:
    # said, and audited by what the load wrote.
    copies = await store.copies_of(record.id) if record.trigger == "drawn_merge" else []
    written = [{"original": c.original, "written": c.written_id, "same_as": c.same_as_id}
               for c in copies]  # fmt: skip
    says = (
        f"promotion {load_id} into {record.dataset_id} from case {record.case_id}: "
        f"{len(record.node_ids)} items and {len(record.edge_ids)} links"
        + (f", and {len(copies)} new item(s) of another type written for it" if copies else "")
    )
    if record.status != "committed":
        print(f"Refused: {says} is {record.status}, not committed. Nothing was changed.")
        return 1
    if stop_if_dry(dry_run, says):
        return 0
    state, why = await conduit()
    if state != "stopped":
        print(CONDUIT_RUNNING if state == "running" else CONDUIT_UNKNOWN.format(why=why))
        return 1
    by = Principal(id=reverted_by, clearance="OFFICIAL", org_unit=record.unit)
    # Audited before anything is written (ADR-127 Amendment 23's order).
    await audit.record(
        principal=by,
        action="revert_promotion",
        investigation_id=record.case_id,
        resolved_query={"load_id": load_id, "dataset_id": record.dataset_id,
                        "node_ids": list(record.node_ids), "edge_ids": list(record.edge_ids),
                        **({"copies": written} if written else {})},
        result_cardinality=len(record.node_ids) + len(record.edge_ids) + len(copies),
    )  # fmt: skip
    try:
        await revert_promotion(record, graph, store, items, merge)
    except PromotionRefused as refused:
        # Audited before it was tried, so its refusal is audited too: the trail says it did not
        # happen.
        await audit.record(
            principal=by,
            action="revert_promotion_refused",
            investigation_id=record.case_id,
            resolved_query={"load_id": load_id, "error": refused.code},
            result_cardinality=0,
        )
        print(f"Refused: {refused.message} Nothing was changed.")
        return 1
    await invalidate()
    print(f"Reverted {says}.")
    return 0


async def _main(args: argparse.Namespace) -> int:
    if not any(os.environ.get(name) for name in STORE_SETTINGS):
        print(NO_STORE_SETTINGS)
        return 64
    dsn = PostgresConfig.from_env().dsn
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    store = await PostgresPromotionStore.connect(dsn)
    items = await PostgresBoardItemStore.connect(dsn)
    datasets = await PostgresDatasetStore.connect(dsn)
    views = await PostgresCaseViewStore.connect(dsn)
    audit = await AuditWriter.connect(dsn)
    scheme = load_uk_le_scheme()
    graph = GraphArcadeDBAdapter(client, scheme)
    valkey_config = ValkeyConfig.from_env()
    valkey = Valkey(host=valkey_config.host, port=valkey_config.port, db=valkey_config.db)
    try:
        return await run(
            args.load_id, reverted_by=args.reverted_by, dry_run=args.dry_run, store=store,
            graph=graph, items=items, audit=audit,
            invalidate=lambda: invalidate_every_cache(valkey),
            merge=MergeCommit(promotions_store=store, graph=graph, datasets=datasets, views=views,
                              items=items, scheme=scheme),
        )  # fmt: skip
    finally:
        await client.aclose()
        await store.close()
        await items.close()
        await datasets.close()
        await views.close()
        await audit.close()
        await valkey.aclose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
