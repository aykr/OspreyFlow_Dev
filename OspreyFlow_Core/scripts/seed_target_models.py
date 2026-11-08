"""Gives every existing dataset its first domain model, live (`06_DECISIONS.md` ADR-126 Amendment 3;
L3.1b step 3).

Run inside the deployment, where Postgres is reachable:

    python -m scripts.seed_target_models --dry-run   # says what it would do
    python -m scripts.seed_target_models             # does it

Once a case's packs come from its dataset's live model (ADR-126 Amendment 2), a dataset with no
model would leave every case reading it with the POLE core alone: a case that chose FIBO would lose
its KYC figures. So each dataset with no model is given version 1, live:

- its packs are **the union of the packs chosen by the cases that read it**, each case counted for
  the one dataset it chose and no other (a case reading a composite adds to the composite's model,
  not its members'), so no case's choice reaches a dataset it does not read;
- a dataset whose cases chose none, or that no case reads, gets the POLE core alone;
- each pack is pinned at the version the loaded ontology carries.

An analyst layer is no dataset of its own and gets none. A dataset that already has a model is
named and left as it is, so a second run changes nothing. Each dataset given one is named, with its
packs, and counted.

**The dry run writes nothing by construction**, as `scripts.migrate_cases_to_one_dataset` does: it
reads the tables with plain `SELECT`s (never opening `PostgresTargetModelStore`, whose `connect`
makes its table), and every write the plan makes goes through `DryRun`, which records it.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from services.api.config import PostgresConfig
from services.api.target_models import PostgresTargetModelStore, TargetModelStore

from schemas.dataset_model import TargetModelDraftInput
from schemas.domain import Principal

ACTOR = "seed-target-models"


@dataclass(frozen=True)
class DatasetRow:
    id: str
    name: str
    kind: str


@dataclass
class Report:
    #: (dataset label, its packs) for each dataset given a model.
    seeded: list[tuple[str, list[str]]] = field(default_factory=list)
    #: Labels of datasets that already had a model, left as they are.
    kept: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)


class DryRun:
    """A model store for a dry run: each write recorded, none made."""

    def __init__(self, writes: list[str]) -> None:
        self._writes = writes

    async def open_draft(self, dataset_id: str, principal: Principal) -> Any:
        self._writes.append(f"open the first model of {dataset_id}")

    async def save_draft(
        self, dataset_id: str, given: TargetModelDraftInput, principal: Any
    ) -> Any:
        self._writes.append(f"give {dataset_id} the packs {sorted(given.packs) or 'none'}")

    async def make_live(self, dataset_id: str, version: int, principal: Any) -> Any:
        self._writes.append(f"make version {version} of {dataset_id} live")


class _Recording:
    """The real store, each write noted in the report as it is made."""

    def __init__(self, inner: TargetModelStore, writes: list[str]) -> None:
        self._inner = inner
        self._writes = writes

    async def open_draft(self, dataset_id: str, principal: Principal) -> Any:
        self._writes.append(f"open_draft {dataset_id}")
        return await self._inner.open_draft(dataset_id, principal)

    async def save_draft(
        self, dataset_id: str, given: TargetModelDraftInput, principal: Principal
    ) -> Any:
        self._writes.append(f"save_draft {dataset_id}")
        return await self._inner.save_draft(dataset_id, given, principal)

    async def make_live(self, dataset_id: str, version: int, principal: Principal) -> Any:
        self._writes.append(f"make_live {dataset_id}")
        return await self._inner.make_live(dataset_id, version, principal)


def packs_for(
    dataset_id: str, chosen: Mapping[str, str], domains: Mapping[str, Sequence[str]]
) -> list[str]:
    """The union of the packs chosen by the cases that chose `dataset_id`, and only those."""
    found: set[str] = set()
    for case, dataset in chosen.items():
        if dataset == dataset_id:
            found.update(domains.get(case) or [])
    return sorted(found)


async def seed(
    datasets: Sequence[DatasetRow],
    chosen: Mapping[str, str],
    domains: Mapping[str, Sequence[str]],
    with_a_model: set[str],
    *,
    store: Any,
    pack_versions: Mapping[str, int],
    write: bool,
    say: Callable[[str], None] = print,
) -> Report:
    report = Report()
    through = _Recording(store, report.writes) if write else DryRun(report.writes)
    seeder = Principal(id=ACTOR, clearance="OFFICIAL", org_unit="")
    for dataset in sorted(datasets, key=lambda d: (d.name, d.id)):
        if dataset.kind == "analyst_layer":
            continue
        label = f"{dataset.name} ({dataset.id})"
        if dataset.id in with_a_model:
            report.kept.append(label)
            continue
        packs = [p for p in packs_for(dataset.id, chosen, domains) if p in pack_versions]
        await through.open_draft(dataset.id, seeder)
        await through.save_draft(
            dataset.id,
            TargetModelDraftInput(packs={p: pack_versions[p] for p in packs}),  # type: ignore[misc]
            seeder,
        )
        await through.make_live(dataset.id, 1, seeder)
        report.seeded.append((label, packs))
        say(
            f"  {label}: version 1, live, " + (", ".join(packs) if packs else "the POLE core alone")
        )
    if report.kept:
        say(
            f"  {len(report.kept):,} already had a domain model, left as it is: "
            + ", ".join(report.kept)
        )
    return report


async def read_tables(
    conn: asyncpg.Connection,
) -> tuple[list[DatasetRow], dict[str, str], dict[str, list[str]], set[str]]:
    """With `SELECT`s only: every dataset, the one dataset each case chose (its first, as the
    migration leaves one), each case's chosen packs, and the datasets that already have a model."""
    datasets = [
        DatasetRow(r["id"], r["name"], r["kind"] or "source")
        for r in await conn.fetch(
            "SELECT id, name, to_jsonb(d) ->> 'kind' AS kind FROM datasets d ORDER BY name, id"
        )
    ]
    chosen = {
        r["investigation_id"]: r["dataset_id"]
        for r in await conn.fetch(
            "SELECT DISTINCT ON (c.investigation_id) c.investigation_id, c.dataset_id "
            "FROM investigation_datasets c JOIN datasets d ON d.id = c.dataset_id "
            "WHERE coalesce(to_jsonb(d) ->> 'kind', 'source') <> 'analyst_layer' "
            "ORDER BY c.investigation_id, c.position"
        )
    }
    domains = {
        r["id"]: list(r["domains"] or [])
        for r in await conn.fetch("SELECT id, domains FROM investigations")
    }
    with_a_model: set[str] = set()
    if await conn.fetchval("SELECT to_regclass('target_models') IS NOT NULL"):
        with_a_model = {
            r["dataset_id"]
            for r in await conn.fetch("SELECT DISTINCT dataset_id FROM target_models")
        }
    return datasets, chosen, domains, with_a_model


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.seed_target_models", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what it would do; write nothing."
    )
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None, *, dsn: str | None = None) -> int:
    from services.api.app import _core_types

    from ontology.packs import load_deployment_ontology

    args = _parse(argv)
    write = not args.dry_run
    print(
        "Dry run: nothing will be written." if not write else "Giving each dataset its first model."
    )
    dsn = dsn or PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    try:
        datasets, chosen, domains, with_a_model = await read_tables(conn)
    finally:
        await conn.close()
    pack_versions = load_deployment_ontology().packs
    store: PostgresTargetModelStore | None = None
    if write:
        store = await PostgresTargetModelStore.connect(dsn, core_types=_core_types())
    try:
        report = await seed(
            datasets, chosen, domains, with_a_model,
            store=store, pack_versions=pack_versions, write=write,
        )  # fmt: skip
    finally:
        if store is not None:
            await store.close()
    print(
        f"{len(report.seeded)} {'given' if write else 'to give'} a first model, "
        f"{len(report.kept)} already had one; {len(report.writes)} writes "
        + ("made." if write else "planned.")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
