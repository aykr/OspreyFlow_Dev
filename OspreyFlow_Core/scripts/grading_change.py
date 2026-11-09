"""Changes the deployment's grading scheme: `python -m scripts.grading_change --to <scheme>
--mapping <file> [--dry-run] --changed-by <principal id>` (`06_DECISIONS.md` ADR-143 decision 11 and
C13; ADR-145 O1; the logic is `services/api/grading.py`).

The mapping file names `from`, `to` and, for each part of a grade (`source`, `intelligence`,
`handling`), every grade of the old scheme and the one of the new it becomes. The command first says
how many drawn items each mapping line moves; with `--dry-run` it stops there and writes nothing.
Otherwise it rewrites each drawn node's and link's grade, keeping the grade and scheme the item had
before its first change beside the new one for good, and records the change in the audit trail with
its counts. It is refused whole, before anything is written, for a mapping that does not cover the
old scheme, a mapping from another scheme than the deployment's (`OSPREY_GRADING_SCHEME`), an item
in another scheme, or a drawn item it cannot read back.

**Who it reads as.** The deployment's top clearance with every handling code and every dataset,
as `--changed-by` in the unit `--org-unit` (default `operator`). A restricted handling code is also
scoped to the reader's unit, so an item under another unit's restricted code is unreadable, and the
change is then refused, naming the count, rather than run past it (rule 2). The clearance is the
command's, not a person's: like `revert_load`, it must never be routed through the Conduit.

**Run it inside the deployment, with the Conduit quiet**, as `revert_load` is: it needs ArcadeDB and
Postgres (`ARCADEDB_HOST` or `ARCADEDB_HTTP_PORT` set; with neither it refuses rather than reach
whatever answers on localhost:2480). A drawing made while it runs could be left in the old scheme.

**Then the setting.** The command changes the items, not `osprey.yaml`: set `grading.scheme` to the
new scheme there and start the deployment again (`ospreyflow start`), so the boards offer the new
scheme's grades. Until then a run of the same change finds every item already changed and writes
nothing. (`ospreyflow grading change`, the verb decision 11 names, is to wrap both steps.)

Exit codes: 0 changed, or the dry run's plan; 1 refused (nothing was changed); 2 stopped part way
(run it again to finish it); 64 a usage error, or no store settings.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from services.api.audit import AuditWriter
from services.api.board_store import BoardItem
from services.api.config import GradingSchemeUnknown, GradingSettings, PostgresConfig
from services.api.grading import (
    SCHEMES,
    BoardGradedItems,
    GradedItems,
    GradingIncomplete,
    GradingPlan,
    GradingRefused,
    MappingRefused,
    Registered,
    change,
    operator_reader,
    parse_mapping,
)

from schemas.domain import Principal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.grading_change",
        description="Change the grading scheme of every drawn item, keeping each one's original.",
    )
    parser.add_argument("--to", required=True, choices=SCHEMES, help="the new scheme")
    parser.add_argument("--mapping", required=True, type=Path, help="the old-to-new mapping file")
    parser.add_argument(
        "--dry-run", action="store_true", help="say what each mapping line moves; write nothing"
    )
    parser.add_argument(
        "--changed-by", required=True, help="the principal id to record as having changed it"
    )
    parser.add_argument(
        "--org-unit", default="operator", help="the unit the command reads as (default operator)"
    )
    return parser


async def run(
    *,
    to: str,
    mapping_text: str,
    current: str,
    dry_run: bool,
    items: GradedItems,
    audit: Callable[[GradingPlan], object],
    say: Callable[[str], None] = print,
) -> int:
    """The change and what to say of it; the exit code. The port and the audit are given, so a
    test needs no store."""
    try:
        mapping = parse_mapping(mapping_text)
    except MappingRefused as refused:
        say(f"The mapping is refused: {refused}. Nothing was changed.")
        return 1
    if mapping.to_scheme != to:
        say(f"--to is {to}, but the mapping is to {mapping.to_scheme}. Nothing was changed.")
        return 1
    try:
        plan = await change(
            items,
            mapping,
            current=current,
            dry_run=dry_run,
            audit=audit,  # type: ignore[arg-type]
        )
    except GradingRefused as refused:
        say(f"Refused: {refused}")
        return 1
    except GradingIncomplete as stopped:
        say(str(stopped))
        return 2
    for line in plan.lines():
        say(line)
    if dry_run:
        say("A dry run: nothing was written.")
        return 0
    say(f"Changed {plan.written} item(s) to {plan.to_scheme}, each keeping its original grade.")
    say(
        f"Now set grading.scheme: {plan.to_scheme} in osprey.yaml and start the deployment again "
        "(ospreyflow start), so the boards offer its grades."
    )
    return 0


#: As `revert_load`'s: with neither, the client would reach whatever answers on localhost:2480.
STORE_SETTINGS = ("ARCADEDB_HOST", "ARCADEDB_HTTP_PORT")

NO_STORE_SETTINGS = (
    "No store settings: nothing says where this deployment's stores are, and the defaults would "
    "reach whatever answers on localhost:2480. Run the change inside the deployment."
)

#: The board registry's live drawn nodes and links (`board_store`): a withdrawn item keeps the grade
#: it was drawn with, and pictures and match links carry none.
REGISTERED_SQL = (
    "SELECT item_id, board_id, case_id, kind, element_id, author, dataset_id, created_at, "
    "withdrawn_at, withdrawn_by, source, target, promoted_at FROM board_items "
    "WHERE withdrawn_at IS NULL AND kind IN ('node', 'link') ORDER BY created_at, item_id"
)


def registry_reader(pool: Any) -> Registered:
    """Every live drawn node and link the board registry holds, of every case."""

    async def registered() -> list[BoardItem]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(REGISTERED_SQL)
        return [BoardItem(**dict(row)) for row in rows]

    return registered


async def _main(args: argparse.Namespace) -> int:
    try:
        mapping_text = args.mapping.read_text(encoding="utf-8")
    except OSError as unread:
        print(f"The mapping file cannot be read: {unread}")
        return 64
    try:
        current = GradingSettings.from_env().scheme
    except GradingSchemeUnknown as unknown:
        print(str(unknown))
        return 64
    if not any(os.environ.get(name) for name in STORE_SETTINGS):
        print(NO_STORE_SETTINGS)
        return 64  # before any store is opened

    import asyncpg

    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme

    scheme = load_uk_le_scheme()
    dsn = PostgresConfig.from_env().dsn
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    audit_writer = await AuditWriter.connect(dsn)

    operator = Principal(id=args.changed_by, clearance="OFFICIAL", org_unit=args.org_unit)

    async def audit(plan: GradingPlan) -> None:
        await audit_writer.record(
            principal=operator,
            action="grading_change",
            resolved_query=plan.record(),
            result_cardinality=plan.written,
        )

    try:
        items = BoardGradedItems(
            GraphArcadeDBAdapter(client, scheme),
            registry_reader(pool),
            operator_reader(scheme, org_unit=args.org_unit, by=args.changed_by),
            written_by=args.changed_by,
        )
        return await run(
            to=args.to,
            mapping_text=mapping_text,
            current=current,
            dry_run=args.dry_run,
            items=items,
            audit=audit,
        )
    finally:
        await client.aclose()
        await pool.close()
        await audit_writer.close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
