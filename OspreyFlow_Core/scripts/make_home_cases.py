"""Gives every existing dataset its home case (`06_DECISIONS.md` ADR-145 Amendment 4 decision 2;
L3.1b step 4).

Run inside the deployment, where Postgres and the identity provider are reachable:

    python -m scripts.make_home_cases --dry-run   # says what it would do
    python -m scripts.make_home_cases             # does it

A dataset made live from now on gets its home case at its first *Make live*, whose owners become its
Authors. A dataset that existed before has none, so each is given one now:

- **named for the dataset**, of its unit, reading it;
- **its Author is the dataset's `created_by`**, named in the output, when the identity provider's
  directory holds that account as a person (the orchestrator's answer, 8 November 2026);
- **where `created_by` is a service account, a disabled account or one gone**, or the directory
  cannot be asked, the home case is given **no Author**. It is named and counted as "needs an
  owner", for Admin › Datasets' *Change owner…*, and nobody is made its Author by default (ADR-112
  Amendment 5: a service account owns nothing);
- **one per dataset per deployment** (the reading of decision 5): a dataset that already has one is
  left as it is, so a second run changes nothing. The claim is held by the store's key on the
  dataset's id and made before the case reads anything, so two runs at once, or a run and a
  *Make live*, still give it one: the loser removes the case it made. An analyst layer is no
  dataset of its own and gets none.

**The dry run writes nothing by construction**, as `scripts.migrate_cases_to_one_dataset` does: it
reads with plain `SELECT`s, never opening a store whose `connect` makes tables, and records every
write the plan would make.
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

from schemas.dataset_model import HomeCase
from schemas.domain import Principal

ACTOR = "make-home-cases"


@dataclass(frozen=True)
class DatasetRow:
    id: str
    name: str
    owning_unit: str
    kind: str
    created_by: str


@dataclass
class Report:
    #: (dataset label, the Author given) for each home case made with one.
    owned: list[tuple[str, str]] = field(default_factory=list)
    #: Labels of datasets whose home case was given no Author.
    needs_an_owner: list[str] = field(default_factory=list)
    #: Labels of datasets that already had a home case.
    kept: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)


class DryRun:
    """The stores for a dry run: each write recorded, none made."""

    def __init__(self, writes: list[str]) -> None:
        self._writes = writes

    async def make(self, dataset: DatasetRow, author: str | None) -> bool:
        self._writes.append(f"make the home case of {dataset.id}")
        self._writes.append(f"record {dataset.id}'s home case")
        self._writes.append(f"case reads {dataset.id}")
        self._writes.append(f"make {author} its Author" if author else "leave it with no Author")
        return True


class Real:
    """The real stores, each write noted as it is made."""

    def __init__(self, investigations: Any, datasets: Any, writes: list[str]) -> None:
        self._investigations = investigations
        self._datasets = datasets
        self._writes = writes

    async def make(self, dataset: DatasetRow, author: str | None) -> bool:
        """Whether this run made the home case. The claim is the first write after the case: a
        dataset another run (or a *Make live*) claimed meanwhile keeps its own, and the case made
        here is removed, so a dataset never has two (the round-1 review's must-fix 8)."""
        from services.api.datasets import HomeCaseHeld
        from services.api.investigations import AccessLevel

        maker = Principal(id=ACTOR, clearance="OFFICIAL", org_unit=dataset.owning_unit)
        home = await self._investigations.create(maker, name=dataset.name)
        self._writes.append(f"create {home.id}")
        try:
            await self._datasets.set_home_case(
                HomeCase(dataset_id=dataset.id, investigation_id=home.id,
                         made_at=datetime.now(UTC), made_by=ACTOR)
            )  # fmt: skip
        except HomeCaseHeld:
            await self._investigations.remove(home.id, by=maker)
            self._writes.append(f"remove {home.id}: {dataset.id} has its home case already")
            return False
        self._writes.append(f"set_home_case {dataset.id}")
        await self._datasets.set_for_case(home.id, [dataset.id], maker, case_name=home.name)
        self._writes.append(f"set_for_case {home.id}")
        if author is not None:
            await self._investigations.set_grant(home.id, author, AccessLevel.AUTHOR, by=maker)
        await self._investigations.remove_grant(home.id, ACTOR, by=maker)
        self._writes.append(f"grants of {home.id}")
        return True


async def make_homes(
    datasets: Sequence[DatasetRow],
    with_a_home: set[str],
    persons: set[str] | None,
    *,
    through: Any,
    report: Report | None = None,
    say: Callable[[str], None] = print,
) -> Report:
    """`through` writes into `report.writes`, the same list, so the count is what was planned or
    made."""
    report = report if report is not None else Report()
    for dataset in sorted(datasets, key=lambda d: (d.name, d.id)):
        if dataset.kind == "analyst_layer":
            continue
        label = f"{dataset.name} ({dataset.id})"
        if dataset.id in with_a_home:
            report.kept.append(label)
            continue
        author = (
            dataset.created_by if persons is not None and dataset.created_by in persons else None
        )
        if not await through.make(dataset, author):
            report.kept.append(label)
            say(f"  {label}: kept the home case it was given meanwhile")
            continue
        if author is None:
            report.needs_an_owner.append(label)
            say(f"  {label}: home case made, needs an owner (made by {dataset.created_by})")
        else:
            report.owned.append((label, author))
            say(f"  {label}: home case made, its Author {author}")
    if report.needs_an_owner:
        count = len(report.needs_an_owner)
        say(
            f"  {count:,} {'home case needs' if count == 1 else 'home cases need'} an owner, "
            "for Admin › Datasets' Change owner…: " + ", ".join(report.needs_an_owner)
        )
    if report.kept:
        say(f"  {len(report.kept):,} already had a home case: " + ", ".join(report.kept))
    return report


async def read_tables(conn: asyncpg.Connection) -> tuple[list[DatasetRow], set[str]]:
    """With `SELECT`s only: every dataset, and those that already have a home case."""
    datasets = [
        DatasetRow(r["id"], r["name"], r["owning_unit"], r["kind"] or "source", r["created_by"])
        for r in await conn.fetch(
            "SELECT id, name, owning_unit, created_by, to_jsonb(d) ->> 'kind' AS kind "
            "FROM datasets d ORDER BY name, id"
        )
    ]
    with_a_home: set[str] = set()
    if await conn.fetchval("SELECT to_regclass('home_cases') IS NOT NULL"):
        with_a_home = {
            r["dataset_id"] for r in await conn.fetch("SELECT dataset_id FROM home_cases")
        }
    return datasets, with_a_home


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.make_home_cases", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what it would do; write nothing."
    )
    return parser.parse_args(argv)


async def _persons(ids: Sequence[str], names: Any) -> set[str] | None:
    found: set[str] | None = await names.people(sorted(set(ids)))
    return found


async def _main(argv: list[str] | None = None, *, dsn: str | None = None, names: Any = None) -> int:
    from services.api.datasets import PostgresDatasetStore
    from services.api.investigations import InvestigationStore

    args = _parse(argv)
    write = not args.dry_run
    print(
        "Dry run: nothing will be written." if not write else "Giving each dataset its home case."
    )
    dsn = dsn or PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    try:
        datasets, with_a_home = await read_tables(conn)
    finally:
        await conn.close()
    owned_names = names is None
    if names is None:
        from services.api.config import ApiConfig
        from services.api.principal_names import PrincipalNameDirectory

        names = PrincipalNameDirectory(ApiConfig.from_env())
    try:
        persons = await _persons([d.created_by for d in datasets], names)
    finally:
        if owned_names:
            await names.aclose()
    report = Report()
    if write:
        investigations = await InvestigationStore.connect(dsn)
        store = await PostgresDatasetStore.connect(dsn)
        try:
            await make_homes(
                datasets, with_a_home, persons,
                through=Real(investigations, store, report.writes), report=report,
            )  # fmt: skip
        finally:
            await investigations.close()
            await store.close()
    else:
        await make_homes(
            datasets, with_a_home, persons, through=DryRun(report.writes), report=report
        )
    made = len(report.owned) + len(report.needs_an_owner)
    print(
        f"{made} home cases {'made' if write else 'to make'}, {len(report.needs_an_owner)} "
        f"needing an owner, {len(report.kept)} already had one; {len(report.writes)} writes "
        + ("made." if write else "planned.")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
