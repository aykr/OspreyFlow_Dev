"""Reverts a promotion: `python -m scripts.revert_promotion <load_id> --reverted-by <principal id>
[--dry-run]` (`06_DECISIONS.md` ADR-143 decision 8; the logic is
`services/api/promotions.py`'s `revert_promotion`).

A promotion is a load (trigger `analyst_promotion` or `layer_merge`) that added a dataset to drawn
elements of a case's analyst layer. Its revert takes that dataset back from exactly those elements,
in one transaction, so each is in the case's layer only again, as it was before; records the
promotion `reverted`; clears its board items' `promoted_at`; audits it under `--reverted-by`; and
clears the Conduit's kept results (`cache:*` in the shared Valkey), since what was counted included
the promoted elements. Nothing is deleted.

**Quiesce the Conduit**, as for any load's revert (ADR-127 Amendment 9). An online revert from the
board waits for the owner's ruling on ADR-143 open question 2; until then this command is the only
way, and it must never be routed through the Conduit.

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
from typing import Any

from services.api.audit import AuditWriter
from services.api.board_store import PostgresBoardItemStore
from services.api.cache import invalidate_every_cache
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.promotion_store import PostgresPromotionStore, PromotionStore
from services.api.promotions import PromotionRefused, revert_promotion
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
) -> int:
    record = await store.by_load(load_id)
    if record is None:
        print(f"No promotion has the load id {load_id}. Nothing was changed.")
        return 1
    says = (
        f"promotion {load_id} into {record.dataset_id} from case {record.case_id}: "
        f"{len(record.node_ids)} items and {len(record.edge_ids)} links"
    )
    if record.status != "committed":
        print(f"Refused: {says} is {record.status}, not committed. Nothing was changed.")
        return 1
    if stop_if_dry(dry_run, says):
        return 0
    by = Principal(id=reverted_by, clearance="OFFICIAL", org_unit=record.unit)
    # Audited before anything is written (ADR-127 Amendment 23's order).
    await audit.record(
        principal=by,
        action="revert_promotion",
        investigation_id=record.case_id,
        resolved_query={"load_id": load_id, "dataset_id": record.dataset_id,
                        "node_ids": list(record.node_ids), "edge_ids": list(record.edge_ids)},
        result_cardinality=len(record.node_ids) + len(record.edge_ids),
    )  # fmt: skip
    try:
        await revert_promotion(record, graph, store, items)
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
    audit = await AuditWriter.connect(dsn)
    valkey_config = ValkeyConfig.from_env()
    valkey = Valkey(host=valkey_config.host, port=valkey_config.port, db=valkey_config.db)
    try:
        return await run(
            args.load_id, reverted_by=args.reverted_by, dry_run=args.dry_run, store=store,
            graph=GraphArcadeDBAdapter(client, load_uk_le_scheme()), items=items, audit=audit,
            invalidate=lambda: invalidate_every_cache(valkey),
        )  # fmt: skip
    finally:
        await client.aclose()
        await store.close()
        await items.close()
        await audit.close()
        await valkey.aclose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
