"""Changes the deployment's grading scheme (`06_DECISIONS.md` ADR-143 decision 11 and Amendment 6;
the owner's ruling C13; ADR-145 O1; the logic is `services/api/grading.py`). Run through
`ospreyflow grading change`, which runs this inside the deployment with the Conduit stopped and
then sets `grading.scheme` and starts the deployment again; run directly it does only the items:

    python -m scripts.grading_change --to <scheme or scheme file> --mapping <file> --dry-run \
        --changed-by <id>
    python -m scripts.grading_change --to <scheme or scheme file> --mapping <file> \
        --confirm <the dry run's token> --changed-by <id>

Run it only inside the deployment, as the verb does: on the host its stores and its Conduit check
cannot reach the deployment's own.

The mapping file names `from`, `to` and, for each part of a grade (`source`, `intelligence`,
`handling`), every grade of the old scheme and the one of the new it becomes. `--to` is a built-in
scheme (5x5x5, 3x5x2) or a scheme file (`scheme`, `source`, `intelligence`, `handling`).

**A dry run first** (C13). The dry run says how many drawn items each mapping line moves, writes
nothing (no audit record, no table made) and gives a token. The change itself is refused without
that token, or when the drawn items have changed since (another drawing, an edit), or for another
mapping. It then regrades each drawn node and link in place, keeping the grade and scheme the item
had before its first change beside the new one for good, and records the change in the audit trail
before the first write and after the last. Refused whole, before anything is written, for a mapping
that does not cover the old scheme, a mapping from another scheme than the deployment's
(`OSPREY_GRADING_SCHEME`), an item in a third scheme, or a drawn item it cannot read back, naming
the items.

**The Conduit stopped.** The change is refused unless the Conduit is known to be stopped: no
connection can be made to `--conduit-url` (default `http://api:8000`, its name on the deployment's
network). Any answer, a timeout or any other failure refuses it: a drawing or an edit made during
the run, or between the run and the restart in the new scheme, would be in the old scheme.
`ospreyflow grading change --stop-api` stops it, and starts it again in the new scheme.

**Who it reads as.** The deployment's top clearance with every handling code and every dataset,
as `--changed-by` in the unit `--org-unit` (default `operator`). An item it cannot read back, for
any reason, refuses the change, naming it (rule 2). `--changed-by` is recorded in the audit trail
as typed, and said to be (`changed_by_as_typed`): this command runs outside the Conduit, where no
sign-in says who someone is. The verb passes `cli:<the operator's account>`.

**No ontology.** The change writes the grade alone (`GraphPort.regrade_drawn`), which no ontology
checks, and reads only what is stored, a proposed link type's links among them (read under their
stored label's name, `logical_type_name`). So it applies none: no DDL, nothing composed. It reads
every case's board registry
(`board_store`'s own columns), the one read of `board_items` that names no case: an operator's
change of the whole deployment, outside the Conduit, answered to no reader.

Exit codes: 0 changed, or the dry run's plan; 1 refused before any write (nothing was changed); 2
stopped part way, or failed unforeseen (the dry run and the same change again finish it); 64 a
usage error, or no store settings (nothing was opened).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import traceback
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import yaml
from pydantic import ValidationError
from services.api.board_store import ITEM_COLUMNS, item_from_row
from services.api.config import GradingSchemeUnknown, GradingSettings, PostgresConfig
from services.api.grading import (
    BoardGradedItems,
    Copies,
    GradedItems,
    GradingIncomplete,
    GradingPlan,
    GradingRefused,
    MappingRefused,
    Registered,
    built_in_schemes,
    change,
    operator_reader,
    parse_mapping,
)

from schemas.domain import GRADING_PARTS, GradingSchemeAnswer, Principal

if TYPE_CHECKING:
    from adapters.graph_arcadedb.client import ArcadeDBClient
    from ontology.handling import HandlingScheme


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.grading_change",
        description="Change the grading scheme of every drawn item, keeping each one's original.",
    )
    parser.add_argument(
        "--to", required=True, help="the new scheme: 5x5x5, 3x5x2, or a scheme file (.yaml)"
    )
    parser.add_argument("--mapping", required=True, type=Path, help="the old-to-new mapping file")
    first = parser.add_mutually_exclusive_group(required=True)
    first.add_argument(
        "--dry-run", action="store_true", help="say what each mapping line moves; write nothing"
    )
    first.add_argument("--confirm", help="the token the dry run of this mapping gave")
    parser.add_argument(
        "--changed-by", required=True, help="the id recorded as having changed it, as typed"
    )
    parser.add_argument(
        "--org-unit", default="operator", help="the unit the command reads as (default operator)"
    )
    parser.add_argument(
        "--conduit-url",
        default=os.environ.get("OSPREY_CONDUIT_URL", "http://api:8000"),
        help="where the Conduit would answer if running (default http://api:8000)",
    )
    return parser


class TargetRefused(Exception):
    """`--to` names no scheme and no readable scheme file."""


def target_scheme(to: str, read: Callable[[Path], str] | None = None) -> GradingSchemeAnswer:
    """`--to`: a built-in scheme by name, or a scheme file, read and checked."""
    if to in GRADING_PARTS:
        return GradingSchemeAnswer.of(to)
    if not to.endswith((".yaml", ".yml")):
        raise TargetRefused(
            f"--to {to!r} is neither a grading scheme ({', '.join(GRADING_PARTS)}) nor a scheme "
            "file (.yaml)"
        )
    try:
        text = (read or (lambda p: p.read_text(encoding="utf-8")))(Path(to))
        return GradingSchemeAnswer.model_validate(yaml.safe_load(text))
    except (OSError, yaml.YAMLError) as unread:
        raise TargetRefused(f"the scheme file {to} cannot be read: {unread}") from None
    except ValidationError as bad:
        raise TargetRefused(f"{to} is not a grading scheme: {bad}") from None


async def run(
    *,
    target: GradingSchemeAnswer,
    mapping_text: str,
    current: GradingSchemeAnswer,
    dry_run: bool,
    items: GradedItems,
    audit: Callable[[GradingPlan], Awaitable[None]],
    confirm: str | None = None,
    say: Callable[[str], None] = print,
) -> int:
    """The change and what to say of it; the exit code. The port and the audit are given, so a
    test needs no store."""
    schemes = {**built_in_schemes(), current.scheme: current, target.scheme: target}
    try:
        mapping = parse_mapping(mapping_text, schemes)
    except MappingRefused as refused:
        say(f"The mapping is refused: {refused}. Nothing was changed.")
        return 1
    if mapping.to_scheme != target.scheme:
        say(
            f"--to is {target.scheme}, but the mapping is to {mapping.to_scheme}. "
            "Nothing was changed."
        )
        return 1

    def announce(plan: GradingPlan) -> None:
        # Said before the first write: what each mapping line moves.
        for line in plan.lines():
            say(line)

    try:
        plan = await change(
            items,
            mapping,
            current=current,
            target=target,
            dry_run=dry_run,
            confirm=confirm,
            audit=audit,
            announce=announce,
        )
    except GradingRefused as refused:
        say(f"Refused: {refused}")
        return 1
    except GradingIncomplete as stopped:
        say(str(stopped))
        return 2
    if dry_run:
        say(
            f"A dry run: nothing was written. To make this change, add --confirm {plan.token}"
        )
        return 0
    say(f"Changed {plan.written} item(s) to {plan.to_scheme}, each keeping its original grade.")
    return 0


#: As `revert_load`'s: with neither, the client would reach whatever answers on localhost:2480.
STORE_SETTINGS = ("ARCADEDB_HOST", "ARCADEDB_HTTP_PORT")

NO_STORE_SETTINGS = (
    "No store settings: nothing says where this deployment's stores are, and the defaults would "
    "reach whatever answers on localhost:2480. Run the change inside the deployment "
    "(ospreyflow grading change)."
)

#: The board registry's live drawn nodes and links (`board_store`): a withdrawn item keeps the grade
#: it was drawn with, and pictures and match links carry none.
REGISTERED_SQL = (
    f"SELECT {ITEM_COLUMNS} FROM board_items "
    "WHERE withdrawn_at IS NULL AND kind IN ('node', 'link') ORDER BY created_at, item_id"
)


def registry_reader(pool: Any) -> Registered:
    """Every live drawn node and link the board registry holds, of every case: none where nothing
    was ever drawn (no table: this read never makes one)."""
    import asyncpg

    async def registered() -> list[Any]:
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(REGISTERED_SQL)
            except asyncpg.UndefinedTableError:
                return []
        return [item_from_row(row) for row in rows]

    return registered


def copies_reader(pool: Any) -> Copies:
    """Every committed drawn merge's written copies (ADR-143 Amendment 7): drawn items in no
    board's registry, graded in the deployment's scheme all the same (decision 11). None where no
    merge ever ran (no table: this read never makes one)."""
    import asyncpg
    from services.api.promotion_store import COMMITTED_COPIES_SQL

    async def copies() -> list[tuple[str, str]]:
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(COMMITTED_COPIES_SQL)
            except asyncpg.UndefinedTableError:
                return []
        return [(row["kind"], row["written_id"]) for row in rows]

    return copies


def graded_items(
    client: ArcadeDBClient,
    scheme: HandlingScheme,
    registered: Registered,
    reader: Principal,
    copies: Copies | None = None,
) -> BoardGradedItems:
    """The command's port: the bare graph adapter, with no ontology applied (it reads what is
    stored and writes the grade alone), over the board registry and the drawn merges' copies."""
    from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter

    return BoardGradedItems(GraphArcadeDBAdapter(client, scheme), registered, reader, copies)


async def conduit_answers(url: str, transport: httpx.AsyncBaseTransport | None = None) -> bool:
    """Whether a Conduit may be running at `url`. Only a connection that cannot be made (no
    Conduit listening, or none by that name on the deployment's network: it is stopped) says no.
    Any answer, of any status, is a running Conduit, and a timeout or any other failure is not
    known to be stopped: both say yes, so the check fails closed."""
    try:
        async with httpx.AsyncClient(timeout=3.0, transport=transport) as client:
            await client.get(f"{url.rstrip('/')}/healthz")
    except httpx.ConnectError:
        return False
    except httpx.HTTPError:
        return True
    return True


CONDUIT_RUNNING = (
    "Refused: the Conduit is running at {url}. A drawing or an edit during the change, or before "
    "the deployment starts again in the new scheme, would be in the old one. Stop it first "
    "(ospreyflow grading change --stop-api stops it, and starts it again after). Nothing was "
    "changed."
)


async def _main(
    args: argparse.Namespace,
    *,
    answers: Callable[[str], Awaitable[bool]] = conduit_answers,
) -> int:
    try:
        mapping_text = args.mapping.read_text(encoding="utf-8")
    except OSError as unread:
        print(f"The mapping file cannot be read: {unread}")
        return 64
    try:
        current = GradingSettings.from_env().grades
    except GradingSchemeUnknown as unknown:
        print(str(unknown))
        return 64
    try:
        target = target_scheme(args.to)
    except TargetRefused as refused:
        print(f"{refused}. Nothing was changed.")
        return 64
    if not any(os.environ.get(name) for name in STORE_SETTINGS):
        print(NO_STORE_SETTINGS)
        return 64  # before any store is opened
    if not args.dry_run and await answers(args.conduit_url):
        print(CONDUIT_RUNNING.format(url=args.conduit_url))
        return 1

    import asyncpg
    from services.api.audit import AuditWriter

    from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
    from ontology.handling import load_uk_le_scheme

    scheme = load_uk_le_scheme()
    dsn = PostgresConfig.from_env().dsn
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    # The audit's table is made by its `connect()`, so it is opened only at the first record: a
    # dry run, or a change refused before any write, makes nothing.
    audit_writer: AuditWriter | None = None
    operator = Principal(id=args.changed_by, clearance="OFFICIAL", org_unit=args.org_unit)

    async def audit(plan: GradingPlan) -> None:
        nonlocal audit_writer
        assert not args.dry_run, "a dry run is never audited"
        if audit_writer is None:
            audit_writer = await AuditWriter.connect(dsn)
        await audit_writer.record(
            principal=operator,
            action="grading_change",
            resolved_query={**plan.record(), "changed_by_as_typed": True},
            result_cardinality=plan.written,
        )

    try:
        items = graded_items(
            client,
            scheme,
            registry_reader(pool),
            operator_reader(scheme, org_unit=args.org_unit, by=args.changed_by),
            copies_reader(pool),
        )
        return await run(
            target=target,
            mapping_text=mapping_text,
            current=current,
            dry_run=args.dry_run,
            confirm=args.confirm,
            items=items,
            audit=audit,
        )
    finally:
        await client.aclose()
        await pool.close()
        if audit_writer is not None:
            await audit_writer.close()


#: An unforeseen failure: not known to have written nothing, so never a refusal's exit (1).
STOPPED = 2


def main(argv: list[str] | None = None) -> int:
    """Exit 1 is said only by a refusal made before any write; anything unforeseen (a store or
    audit failure, a bug) exits 2, "stopped part way", so the verb never treats a failure after a
    write as nothing changed."""
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_main(args))
    except Exception:
        traceback.print_exc()
        print(
            "The change stopped unexpectedly; some items may be changed. Run the dry run and the "
            "same change again to finish it."
        )
        return STOPPED


if __name__ == "__main__":
    raise SystemExit(main())
