"""Places every case on one dataset and gives it its analyst layer (`06_DECISIONS.md` ADR-099
Amendment 12 item 9, ADR-140 Amendment 7, ADR-143 decision 1).

Run inside the deployment, where Postgres is reachable; the Conduit may keep running:

    python -m scripts.migrate_cases_to_one_dataset --dry-run   # says what it would do
    python -m scripts.migrate_cases_to_one_dataset             # does it

For each case, oldest first:

1. A case that chose one dataset keeps it.
2. A case that names several source datasets of its own unit reads a **composite** of them instead:
   one composite per distinct set in a unit, reused by every case naming that set, named for its
   members, its egress the strictest of theirs (`datasets.compose_for_case`). Nothing is copied: a
   composite is read as its members, so the case reads exactly what it read before.
3. Every case it placed gets its **analyst layer**, empty, if it has none.
4. A case it cannot place is **reported, never guessed**: one that reads nothing, one naming a
   dataset of another unit, one naming a composite beside another dataset.

Then, on a real run, it builds the one-row-per-case index on `investigation_datasets`, which is what
makes "one dataset per case" a rule of the store rather than of the code; the index is refused while
any case still names two, so it says whether it was built.

**The dry run writes nothing by construction:** every write goes through the store it is handed,
and a dry run is handed `DryRun`, which records each write and returns a stand-in instead of making
it (`test_migrate_cases_to_one_dataset.py` shows it red with the real store handed in its place). A
second real run finds every case placed and changes nothing.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import asyncpg
from services.api.config import PostgresConfig
from services.api.datasets import (
    COMPOSITE,
    SOURCE,
    Dataset,
    DatasetStore,
    PostgresDatasetStore,
    compose_for_case,
    index_one_dataset_per_case,
)

from schemas.admin import DatasetEgress
from schemas.domain import Principal

from .stamp_datasets import CaseRow, _cases

ACTOR = "migrate-cases-to-one-dataset"


@dataclass
class Report:
    kept: list[str] = field(default_factory=list)
    #: (case id, the composite it now reads, whether the composite was made by this run).
    composed: list[tuple[str, str, bool]] = field(default_factory=list)
    layers_made: list[str] = field(default_factory=list)
    #: Each case not placed, with why, in words.
    unplaced: list[str] = field(default_factory=list)
    #: Every write made (or, in a dry run, that would be made), in order.
    writes: list[str] = field(default_factory=list)


class DryRun:
    """A `DatasetStore` for a dry run: reads are the real store's, writes are recorded and not
    made. What a write would return is a stand-in that says it is one."""

    def __init__(self, inner: DatasetStore, writes: list[str]) -> None:
        self._inner = inner
        self._writes = writes

    def __getattr__(self, name: str) -> Any:
        if name in {"chosen_of_case", "layer_of_case", "list_all", "egress_of", "ids_of_case"}:
            return getattr(self._inner, name)
        raise AttributeError(f"a dry run does not call {name}")

    async def create_composite(
        self,
        principal: Principal,
        name: str,
        member_ids: Sequence[str],
        *,
        suffix_if_taken: bool = False,
    ) -> Dataset:
        self._writes.append(f"create composite {name!r} of {', '.join(member_ids)}")
        return Dataset(
            id=f"(new composite: {name})",
            name=name,
            owning_unit=principal.org_unit,
            created_at=datetime.now(UTC),
            created_by=principal.id,
            kind=COMPOSITE,
            members=list(member_ids),
        )

    async def set_egress(self, dataset_id: str, egress: DatasetEgress) -> tuple[Any, Dataset]:
        self._writes.append(f"set egress of {dataset_id} to {egress}")
        stand_in = Dataset(
            id=dataset_id,
            name=dataset_id,
            owning_unit="",
            created_at=datetime.now(UTC),
            created_by=ACTOR,
            egress=egress,
        )
        return "none", stand_in

    async def set_for_case(
        self,
        investigation_id: str,
        dataset_ids: Sequence[str],
        principal: Principal,
        *,
        case_name: str | None = None,
    ) -> list[Dataset]:
        self._writes.append(f"case {investigation_id} reads {', '.join(dataset_ids)}")
        return []

    async def ensure_layer(
        self, investigation_id: str, *, unit: str, created_by: str, case_name: str | None = None
    ) -> str:
        self._writes.append(f"make the analyst layer of case {investigation_id}")
        return f"(new layer of {investigation_id})"


class _Recording:
    """The real store, with each write noted in the report as it is made."""

    def __init__(self, inner: DatasetStore, writes: list[str]) -> None:
        self._inner = inner
        self._writes = writes

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name in {"create_composite", "set_egress", "set_for_case", "ensure_layer"}:

            async def noted(*args: Any, **kwargs: Any) -> Any:
                self._writes.append(f"{name} {args[0] if args else ''}".strip())
                return await attr(*args, **kwargs)

            return noted
        return attr


def store_for(store: DatasetStore, *, write: bool, writes: list[str]) -> Any:
    """The store the migration writes through: the real one on a real run, `DryRun` otherwise."""
    return _Recording(store, writes) if write else DryRun(store, writes)


def _seeder(case: CaseRow) -> Principal:
    return Principal(id=ACTOR, clearance="OFFICIAL", org_unit=case.owning_unit)


async def migrate(
    store: DatasetStore,
    cases: Sequence[CaseRow],
    *,
    write: bool,
    say: Callable[[str], None] = print,
) -> Report:
    report = Report()
    through = store_for(store, write=write, writes=report.writes)
    # One composite per distinct set in a unit: those that exist, then those this run makes.
    composites: dict[tuple[str, frozenset[str]], str] = {
        (d.owning_unit, frozenset(d.members)): d.id
        for d in await store.list_all()
        if d.kind == COMPOSITE
    }
    for case in cases:
        label = f"{case.name or 'Unnamed case'} ({case.id})"
        chosen = await store.chosen_of_case(case.id)
        if not chosen:
            report.unplaced.append(f"{label}: reads no dataset, so there is nothing to place it on")
            continue
        if {d.owning_unit for d in chosen} != {case.owning_unit}:
            report.unplaced.append(f"{label}: names a dataset of another unit")
            continue
        if len(chosen) == 1:
            report.kept.append(case.id)
            say(f"  {label}: reads {chosen[0].name}, kept")
        elif any(d.kind != SOURCE for d in chosen):
            report.unplaced.append(f"{label}: names a composite beside another dataset")
            continue
        else:
            members = [d.id for d in chosen]
            key = (case.owning_unit, frozenset(members))
            held = composites.get(key)
            if held is not None:
                await through.set_for_case(case.id, [held], _seeder(case), case_name=case.name)
                report.composed.append((case.id, held, False))
            else:
                made = await compose_for_case(
                    through, case.id, members, _seeder(case), case_name=case.name
                )
                composites[key] = made
                report.composed.append((case.id, made, True))
            say(f"  {label}: names {len(members)} datasets, now reads a composite of them")
        if await store.layer_of_case(case.id) is None:
            await through.ensure_layer(
                case.id, unit=case.owning_unit, created_by=ACTOR, case_name=case.name
            )
            report.layers_made.append(case.id)
    for line in report.unplaced:
        say(f"  not placed: {line}")
    return report


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.migrate_cases_to_one_dataset", description=__doc__
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what it would do; write nothing."
    )
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    write = not args.dry_run
    print(
        "Dry run: nothing will be written." if not write else "Placing every case on one dataset."
    )
    dsn = PostgresConfig.from_env().dsn
    store = await PostgresDatasetStore.connect(dsn)
    try:
        report = await migrate(store, await _cases(dsn), write=write)
        if write:
            conn = await asyncpg.connect(dsn)
            try:
                indexed = await index_one_dataset_per_case(conn)
            finally:
                await conn.close()
            print(
                "One dataset per case is now a rule of the store."
                if indexed
                else "Some case still names two datasets; the one-per-case index is not built."
            )
    finally:
        await store.close()
    made = sum(1 for _, _, new in report.composed if new)
    print(
        f"{len(report.kept)} kept, {len(report.composed)} on a composite ({made} made), "
        f"{len(report.layers_made)} layers {'made' if write else 'to make'}, "
        f"{len(report.unplaced)} not placed; {len(report.writes)} writes "
        f"{'made' if write else 'that would be made'}."
    )
    print("Done." if write else "Dry run finished: nothing was written.")
    return 1 if report.unplaced else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
