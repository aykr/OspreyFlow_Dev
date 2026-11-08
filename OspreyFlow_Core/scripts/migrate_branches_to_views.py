"""Turns every case made from another into a view of its original case (`06_DECISIONS.md` ADR-144
decision 6 and Amendment 1 decision 3; the owner's rulings of 8 November 2026 on L3.2's Q1-Q4).

Run inside the deployment, where Postgres, Valkey and ArcadeDB are reachable, after
`scripts.migrate_cases_to_one_dataset` (every original case needs its layer first):

    python -m scripts.migrate_branches_to_views --dry-run   # says what it would do
    python -m scripts.migrate_branches_to_views             # does it

A case made from another records the case it came from. Each such case, oldest first, is one of:

1. **Made since L3.1 by copying a case**: it reads its original's layer through a link
   (`case_layer_reads`). It becomes a view of the original; it holds nothing of its own to move.
2. **Made before L3.1** (copied, or opened from an alert; nothing told the two apart, ADR-143
   Amendment 1 item 3): `migrate_cases_to_one_dataset` gave it a layer of its own, made by that
   script. It becomes a view of the original, and **everything in its layer moves into the
   original's layer, tagged `from_branch: <its name>`**, so nothing is lost and nothing needs a
   layer of its own.
3. **Opened from an alert since L3.1**: it has a layer of its own that its maker made. It **stays
   a case** with only its origin link dropped (Q3): its maker may hold no level on the alert's
   case, so moving it there would show their work to people they never shared it with (rule 3).

A view is private to the maker of the case it came from (Q4); anyone else the case was shared with
is named in this report, so the maker can share the view. It holds the case's nodes (its working
set), its timeline window and its *Match strictness*, and names the case it came from, whose audit
stays readable. The case itself is then removed softly, its origin link and layer link dropped.

**Reported, never guessed** (ADR-144 decision 6): a case whose original is missing or removed;
one whose maker holds no level on the original (they could not open the view); one whose original
has no layer yet; one that reads no layer at all. Each stays as it was for an administrator.

**The dry run writes nothing by construction**: it reads with `SELECT`s and reads alone, and every
write goes through `DryRun`, which records it and makes nothing
(`test_migrate_branches_to_views.py`, red with the real writer handed in). A second real run finds
no case made from another left and changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass, field
from typing import Protocol

import asyncpg
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig, ValkeyConfig
from services.api.working_set.store import ValkeyWorkingSetStore
from valkey.asyncio import Valkey

from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from ontology.loader import load_default_ontology
from schemas.case_views import CaseViewInput
from schemas.domain import Interval

from .migrate_cases_to_one_dataset import ACTOR as LEGACY_LAYER_MAKER
from .stamp_datasets import _Sql, _type_names

ACTOR = "migrate-branches-to-views"
#: The tag on everything moved from a retired case's own layer (ADR-144 decision 6).
TAG = "from_branch"


@dataclass(frozen=True)
class CaseRecord:
    id: str
    name: str
    created_by: str
    owning_unit: str
    made_from: str | None
    window: Interval | None = None
    removed: bool = False

    @property
    def label(self) -> str:
        return f"{self.name or '(unnamed)'} ({self.id})"


class Reads(Protocol):
    """Everything the migration reads. Reads only."""

    async def cases(self) -> list[CaseRecord]: ...
    #: The case's own layer and who made it, or `None`.
    async def own_layer(self, case_id: str) -> tuple[str, str] | None: ...
    #: The original's layer a case made since L3.1 reads, or `None`.
    async def reads_layer(self, case_id: str) -> str | None: ...
    async def case_of_layer(self, layer_id: str) -> str | None: ...
    async def holds_a_level(self, person: str, unit: str, case_id: str) -> bool: ...
    async def other_members(self, case_id: str, maker: str) -> list[str]: ...
    async def node_ids(self, case_id: str) -> list[str]: ...
    async def threshold(self, case_id: str) -> float | None: ...
    async def elements_in(self, layer_id: str) -> int: ...


class Writes(Protocol):
    """Everything the migration writes."""

    async def save_view(self, case: CaseRecord, original: str, given: CaseViewInput) -> str: ...
    async def move_layer(self, from_layer: str, to_layer: str, tag: str) -> int: ...
    async def retire(self, case: CaseRecord) -> None: ...
    async def drop_origin(self, case: CaseRecord) -> None: ...


@dataclass
class Converted:
    case: str
    original: str
    view: str
    moved: int
    #: Others the case was shared with, to whom the view is not yet shared (Q4).
    other_members: list[str]


@dataclass
class Report:
    converted: list[Converted] = field(default_factory=list)
    #: Cases opened from an alert since L3.1, kept as cases with their origin link dropped (Q3).
    kept_as_cases: list[str] = field(default_factory=list)
    #: (case, why): left as it was, for an administrator.
    unplaced: list[tuple[str, str]] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)


class DryRun:
    """The writer for a dry run: each write is recorded and nothing is made. A layer's move counts
    what is in it, by a read."""

    def __init__(self, reads: Reads, writes: list[str]) -> None:
        self._reads = reads
        self._writes = writes

    async def save_view(self, case: CaseRecord, original: str, given: CaseViewInput) -> str:
        self._writes.append(f"save a view of case {original} from case {case.id}")
        return f"(new view of {original})"

    async def move_layer(self, from_layer: str, to_layer: str, tag: str) -> int:
        self._writes.append(f"move layer {from_layer} into {to_layer}, tagged {TAG}: {tag}")
        return await self._reads.elements_in(from_layer)

    async def retire(self, case: CaseRecord) -> None:
        self._writes.append(f"remove case {case.id}, its origin and layer links dropped")

    async def drop_origin(self, case: CaseRecord) -> None:
        self._writes.append(f"drop case {case.id}'s origin link")


async def _original_of(
    case: CaseRecord, by_id: dict[str, CaseRecord], reads: Reads, kept: set[str]
) -> str | None:
    """The case a view goes under: through the layer link if there is one; else up the chain of
    cases made from others to the first one that stays a case."""
    linked = await reads.reads_layer(case.id)
    if linked is not None:
        return await reads.case_of_layer(linked)
    seen = {case.id}
    current = case.made_from
    while current is not None and current in by_id and current not in seen:
        parent = by_id[current]
        if parent.made_from is None or current in kept:
            return current
        seen.add(current)
        current = parent.made_from
    return current


async def migrate(reads: Reads, writes: Writes, report: Report | None = None) -> Report:
    report = report if report is not None else Report()
    cases = await reads.cases()
    by_id = {c.id: c for c in cases}
    made = [c for c in cases if c.made_from is not None]

    # Q3 first, so a case made from such a case goes under it.
    kept: set[str] = set()
    for case in made:
        own = await reads.own_layer(case.id)
        if (
            own is not None
            and own[1] != LEGACY_LAYER_MAKER
            and not await reads.reads_layer(case.id)
        ):
            kept.add(case.id)

    for case in made:
        if case.id in kept:
            await writes.drop_origin(case)
            report.kept_as_cases.append(case.label)
            continue
        own = await reads.own_layer(case.id)
        if own is None and await reads.reads_layer(case.id) is None:
            report.unplaced.append((case.label, "it reads no layer, its own or its original's"))
            continue
        original_id = await _original_of(case, by_id, reads, kept)
        original = by_id.get(original_id) if original_id is not None else None
        if original is None or original.removed:
            report.unplaced.append((case.label, "its original case is missing or removed"))
            continue
        if not await reads.holds_a_level(case.created_by, case.owning_unit, original.id):
            report.unplaced.append(
                (case.label, f"its maker holds no level on its original case {original.label}")
            )
            continue
        target = await reads.own_layer(original.id)
        if own is not None and target is None:
            report.unplaced.append(
                (case.label, f"its original case {original.label} has no layer yet")
            )
            continue
        moved = 0
        if own is not None and target is not None:
            moved = await writes.move_layer(own[0], target[0], case.name or case.id)
        node_ids = await reads.node_ids(case.id)
        view = await writes.save_view(
            case,
            original.id,
            CaseViewInput(
                name=case.name or "View",
                node_ids=node_ids,
                window=case.window,
                threshold=await reads.threshold(case.id),
            ),
        )
        await writes.retire(case)
        report.converted.append(
            Converted(
                case=case.label,
                original=original.label,
                view=view,
                moved=moved,
                other_members=await reads.other_members(case.id, case.created_by),
            )
        )
    return report


# --- the deployment's stores ----------------------------------------------------------------


class DeploymentReads:
    """Postgres, Valkey and ArcadeDB, read with `SELECT`s and reads alone."""

    def __init__(
        self, conn: asyncpg.Connection, working: ValkeyWorkingSetStore, sql: _Sql, types: list[str]
    ) -> None:
        self._conn = conn
        self._working = working
        self._sql = sql
        self._types = types

    async def _has(self, table: str, column: str | None = None) -> bool:
        if column is None:
            return bool(await self._conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table))
        return bool(
            await self._conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = $1 AND column_name = $2 AND table_schema = current_schema())",
                table,
                column,
            )
        )

    async def cases(self) -> list[CaseRecord]:
        if not await self._has("investigations", "branched_from"):
            return []  # converted already, or made after L3.2: nothing is made from another
        windowed = await self._has("investigations", "branch_valid_from")
        rows = await self._conn.fetch(
            "SELECT id, name, created_by, owning_unit, branched_from, removed_at"
            + (", branch_valid_from, branch_valid_to" if windowed else "")
            + " FROM investigations ORDER BY created_at, id"
        )
        return [
            CaseRecord(
                id=r["id"], name=r["name"], created_by=r["created_by"],
                owning_unit=r["owning_unit"], made_from=r["branched_from"],
                window=(
                    Interval(valid_from=r["branch_valid_from"], valid_to=r["branch_valid_to"])
                    if windowed and r["branch_valid_from"] is not None else None
                ),
                removed=r["removed_at"] is not None,
            )
            for r in rows
        ]  # fmt: skip

    async def own_layer(self, case_id: str) -> tuple[str, str] | None:
        if not await self._has("datasets", "layer_of"):
            return None
        row = await self._conn.fetchrow(
            "SELECT id, created_by FROM datasets WHERE layer_of = $1 AND kind = 'analyst_layer'",
            case_id,
        )
        return (row["id"], row["created_by"]) if row else None

    async def reads_layer(self, case_id: str) -> str | None:
        if not await self._has("case_layer_reads"):
            return None
        return await self._conn.fetchval(
            "SELECT layer_id FROM case_layer_reads WHERE investigation_id = $1", case_id
        )

    async def case_of_layer(self, layer_id: str) -> str | None:
        return await self._conn.fetchval("SELECT layer_of FROM datasets WHERE id = $1", layer_id)

    async def holds_a_level(self, person: str, unit: str, case_id: str) -> bool:
        """ADR-052: the case's maker, a grant, or the unit-wide level of a case of their unit."""
        row = await self._conn.fetchrow(
            "SELECT created_by, owning_unit, unit_level FROM investigations WHERE id = $1", case_id
        )
        if row is None:
            return False
        if row["created_by"] == person:
            return True
        if row["owning_unit"] == unit and row["unit_level"]:
            return True
        return bool(
            await self._conn.fetchval(
                "SELECT 1 FROM investigation_grants "
                "WHERE investigation_id = $1 AND account_id = $2",
                case_id,
                person,
            )
        )

    async def other_members(self, case_id: str, maker: str) -> list[str]:
        rows = await self._conn.fetch(
            "SELECT account_id FROM investigation_grants "
            "WHERE investigation_id = $1 AND account_id <> $2 ORDER BY account_id",
            case_id,
            maker,
        )
        return [r["account_id"] for r in rows]

    async def node_ids(self, case_id: str) -> list[str]:
        return sorted(await self._working.node_ids(case_id))

    async def threshold(self, case_id: str) -> float | None:
        return await self._working.get_threshold(case_id)

    async def elements_in(self, layer_id: str) -> int:
        total = 0
        for type_name in self._types:
            total += await self._sql.count(
                f"SELECT count(*) AS count FROM {type_name} WHERE datasets CONTAINS :layer",
                {"layer": layer_id},
            )
        return total


class DeploymentWrites:
    """The real run's writes: views in Postgres, layers moved in ArcadeDB, the cases retired."""

    def __init__(
        self,
        conn: asyncpg.Connection,
        views: PostgresCaseViewStore,
        sql: _Sql,
        types: list[str],
        writes: list[str],
    ) -> None:
        self._conn = conn
        self._views = views
        self._sql = sql
        self._types = types
        self._writes = writes

    async def save_view(self, case: CaseRecord, original: str, given: CaseViewInput) -> str:
        view = await self._views.save(original, given, case.created_by, converted_from_case=case.id)
        self._writes.append(f"saved view {view.id} of case {original} from case {case.id}")
        return view.id

    async def move_layer(self, from_layer: str, to_layer: str, tag: str) -> int:
        """Every node and link naming `from_layer` names `to_layer` in its place and carries the
        tag. Nothing else on it changes; nothing is deleted."""
        moved = 0
        for type_name in self._types:
            rows = await self._sql.query(
                f"SELECT @rid AS rid, datasets FROM {type_name} WHERE datasets CONTAINS :layer",
                {"layer": from_layer},
            )
            for row in rows:
                held = [d for d in (row.get("datasets") or []) if d != from_layer]
                datasets = held + ([to_layer] if to_layer not in held else [])
                await self._sql.query(
                    f"UPDATE {row['rid']} SET datasets = :ds, {TAG} = :tag",
                    {"ds": datasets, "tag": tag},
                )
                moved += 1
        self._writes.append(f"moved {moved} from layer {from_layer} into {to_layer}")
        return moved

    async def retire(self, case: CaseRecord) -> None:
        async with self._conn.transaction():
            await self._conn.execute(
                "UPDATE investigations SET removed_at = COALESCE(removed_at, now()), "
                "removed_by = COALESCE(removed_by, $2), branched_from = NULL WHERE id = $1",
                case.id,
                ACTOR,
            )
            if await self._conn.fetchval("SELECT to_regclass('case_layer_reads') IS NOT NULL"):
                await self._conn.execute(
                    "DELETE FROM case_layer_reads WHERE investigation_id = $1", case.id
                )
        self._writes.append(f"removed case {case.id}")

    async def drop_origin(self, case: CaseRecord) -> None:
        await self._conn.execute(
            "UPDATE investigations SET branched_from = NULL WHERE id = $1", case.id
        )
        self._writes.append(f"dropped case {case.id}'s origin link")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="say what it would do")
    return parser.parse_args(argv)


def print_report(report: Report, *, write: bool) -> None:
    for c in report.converted:
        shared = f"; also shared with {', '.join(c.other_members)}" if c.other_members else ""
        print(
            f"  view: {c.case} becomes a private view of {c.original}, "
            f"{c.moved} items moved into its layer{shared}"
        )
    for label in report.kept_as_cases:
        print(f"  kept as a case: {label}, opened from an alert since L3.1; origin link dropped")
    for label, why in report.unplaced:
        print(f"  not placed: {label}: {why}")
    print(
        f"{len(report.converted)} {'became' if write else 'would become'} views, in "
        f"{len({c.original for c in report.converted})} cases; "
        f"{len(report.kept_as_cases)} kept as cases; {len(report.unplaced)} not placed; "
        f"{len(report.writes)} writes {'made' if write else 'that would be made'}."
    )


async def _main(argv: list[str] | None = None, *, dsn: str | None = None) -> int:
    args = _parse(argv)
    write = not args.dry_run
    print("Dry run: nothing will be written." if not write else "Turning cases into views.")
    dsn = dsn or PostgresConfig.from_env().dsn
    client = ArcadeDBClient(
        ArcadeDBConfig.from_env(os.environ.get("ARCADEDB_DATABASE", "ospreyflow"))
    )
    valkey_config = ValkeyConfig.from_env()
    valkey = Valkey(host=valkey_config.host, port=valkey_config.port, db=valkey_config.db)
    conn = await asyncpg.connect(dsn)
    sql = _Sql(client)
    types = _type_names(load_default_ontology())
    report = Report()
    try:
        reads = DeploymentReads(conn, ValkeyWorkingSetStore(valkey), sql, types)
        if not write:
            await migrate(reads, DryRun(reads, report.writes), report)
        else:
            views = await PostgresCaseViewStore.connect(dsn)
            try:
                await migrate(
                    reads, DeploymentWrites(conn, views, sql, types, report.writes), report
                )
            finally:
                await views.close()
    finally:
        await conn.close()
        await client.aclose()
        await valkey.aclose()
    print_report(report, write=write)
    print("Done." if write else "Dry run finished: nothing was written.")
    return 1 if report.unplaced else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
