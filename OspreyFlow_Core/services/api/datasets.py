"""Datasets, and the datasets each case may read (`06_DECISIONS.md` ADR-099).

A dataset is a named body of data held by a unit: the Enron corpus, Fixture Corp, a body of data
loaded through the Ingest Studio. Every node and link carries the datasets that wrote it, and a case
reads only elements of its own datasets, enforced in the graph adapter with the handling axes
(`AccessFilter.gremlin_structural_step`). This module holds the two records that limit rests on:
the datasets of each unit, and the datasets of each case.

**Who may name what.** A case names at least one dataset, every one of its own unit. A dataset of
another unit and one that does not exist are refused with the same answer, so a refusal says
nothing about another unit's data. Changing a case's datasets is its Author's (the route's level);
a branch takes its parent's.

**Names are unique within a unit (ADR-099 Amendment 6),** ignoring case and spacing, so two of a
unit's datasets never read alike; the id stays what every element and case refers to. A dataset
asked for by name is refused when the name is taken; the one a case makes for itself, and a seed's,
take a suffix instead ("Branch of Enron (2)").
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

import asyncpg
from pydantic import BaseModel, Field

from conduit_common.identity import new_id
from schemas.domain import Principal

MAX_DATASET_NAME = 200


class Dataset(BaseModel):
    id: str
    name: str
    owning_unit: str
    created_at: datetime
    created_by: str


class CreateDatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_DATASET_NAME)


class CaseDatasetsRequest(BaseModel):
    dataset_ids: list[str] = Field(min_length=1, max_length=100)


class DatasetRefusedError(Exception):
    """A case was given no dataset, or one that is not of the principal's unit (or not at all):
    one answer for both, so the refusal does not say whether another unit holds it."""


class DatasetStore(Protocol):
    async def create(
        self, principal: Principal, name: str, *, suffix_if_taken: bool = False
    ) -> Dataset: ...
    async def known(self, dataset_ids: Sequence[str]) -> set[str]: ...
    async def register(self, dataset: Dataset) -> Dataset: ...
    async def list_for_unit(self, unit: str) -> list[Dataset]: ...
    async def of_case(self, investigation_id: str) -> list[Dataset]: ...
    async def ids_of_case(self, investigation_id: str) -> list[str]: ...
    async def set_for_case(
        self, investigation_id: str, dataset_ids: Sequence[str], principal: Principal
    ) -> list[Dataset]: ...
    async def copy_case(self, from_investigation_id: str, to_investigation_id: str) -> None: ...


def _clean(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise DatasetRefusedError("a dataset needs a name")
    return cleaned[:MAX_DATASET_NAME]


def name_key(name: str) -> str:
    """What two names must differ in: case and spacing aside."""
    return " ".join(name.split()).casefold()


def _taken(name: str) -> DatasetRefusedError:
    return DatasetRefusedError(f"A dataset named {name!r} already exists in your unit.")


def _suffixed(name: str, n: int) -> str:
    suffix = f" ({n})"
    return name[: MAX_DATASET_NAME - len(suffix)] + suffix


def _ordered(dataset_ids: Sequence[str]) -> list[str]:
    ordered = list(dict.fromkeys(dataset_ids))
    if not ordered:
        raise DatasetRefusedError("a case reads at least one dataset")
    return ordered


class InMemoryDatasetStore:
    """The same calls with no Postgres, for tests and a process without one."""

    def __init__(self) -> None:
        self.datasets: dict[str, Dataset] = {}
        self.cases: dict[str, list[str]] = {}

    def add(self, dataset: Dataset) -> Dataset:
        self.datasets[dataset.id] = dataset
        return dataset

    def _free_name(self, unit: str, name: str, *, suffix_if_taken: bool) -> str:
        taken = {name_key(d.name) for d in self.datasets.values() if d.owning_unit == unit}
        if name_key(name) not in taken:
            return name
        if not suffix_if_taken:
            raise _taken(name)
        n = 2
        while name_key(_suffixed(name, n)) in taken:
            n += 1
        return _suffixed(name, n)

    async def register(self, dataset: Dataset) -> Dataset:
        """A dataset with a chosen id; writing the same id again keeps the first record."""
        if dataset.id in self.datasets:
            return self.datasets[dataset.id]
        name = self._free_name(dataset.owning_unit, _clean(dataset.name), suffix_if_taken=True)
        return self.add(dataset.model_copy(update={"name": name}))

    async def create(
        self, principal: Principal, name: str, *, suffix_if_taken: bool = False
    ) -> Dataset:
        cleaned = self._free_name(principal.org_unit, _clean(name), suffix_if_taken=suffix_if_taken)
        return self.add(
            Dataset(
                id=new_id(),
                name=cleaned,
                owning_unit=principal.org_unit,
                created_at=datetime.now(UTC),
                created_by=principal.id,
            )
        )

    async def known(self, dataset_ids: Sequence[str]) -> set[str]:
        return {d for d in dataset_ids if d in self.datasets}

    async def list_for_unit(self, unit: str) -> list[Dataset]:
        return sorted(
            (d for d in self.datasets.values() if d.owning_unit == unit), key=lambda d: d.name
        )

    async def of_case(self, investigation_id: str) -> list[Dataset]:
        return [self.datasets[i] for i in self.cases.get(investigation_id, [])]

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        return list(self.cases.get(investigation_id, []))

    async def set_for_case(
        self, investigation_id: str, dataset_ids: Sequence[str], principal: Principal
    ) -> list[Dataset]:
        ordered = _ordered(dataset_ids)
        for dataset_id in ordered:
            held = self.datasets.get(dataset_id)
            if held is None or held.owning_unit != principal.org_unit:
                raise DatasetRefusedError(dataset_id)
        self.cases[investigation_id] = ordered
        return await self.of_case(investigation_id)

    async def copy_case(self, from_investigation_id: str, to_investigation_id: str) -> None:
        self.cases[to_investigation_id] = list(self.cases.get(from_investigation_id, []))


_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owning_unit TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS datasets_unit_idx ON datasets (owning_unit, name);
CREATE TABLE IF NOT EXISTS investigation_datasets (
    investigation_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets (id),
    position INTEGER NOT NULL,
    PRIMARY KEY (investigation_id, dataset_id)
);
"""

_COLUMNS = "d.id, d.name, d.owning_unit, d.created_at, d.created_by"

#: The name a unit's datasets may not share, case and spacing aside (`name_key`).
_NAME_KEY_SQL = "lower(regexp_replace(btrim(name), '\\s+', ' ', 'g'))"


async def _tell_apart_and_index(conn: asyncpg.Connection) -> None:
    """Before the unique index: names a unit already holds twice are told apart, the earliest
    keeping its name and each later one a suffix, so a deployment made before ADR-099 Amendment 6
    starts rather than failing to build the index."""
    exists = await conn.fetchval(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'datasets_unit_name_unique'"
    )
    if exists:
        return
    rows = await conn.fetch(
        f"SELECT id, name, owning_unit, {_NAME_KEY_SQL} AS key FROM datasets "
        "ORDER BY owning_unit, created_at, id"
    )
    taken: dict[str, set[str]] = {}
    for row in rows:
        keys = taken.setdefault(row["owning_unit"], set())
        if row["key"] not in keys:
            keys.add(row["key"])
            continue
        n = 2
        while name_key(_suffixed(row["name"], n)) in keys:
            n += 1
        renamed = _suffixed(row["name"], n)
        keys.add(name_key(renamed))
        await conn.execute("UPDATE datasets SET name = $1 WHERE id = $2", renamed, row["id"])
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS datasets_unit_name_unique "
        f"ON datasets (owning_unit, {_NAME_KEY_SQL})"
    )


class PostgresDatasetStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresDatasetStore:
        # Bounded, as every store here is: the default ten-connection floor per store pushed the
        # lifespan past its ceiling
        # (`test_app_lifespan_does_not_reopen_the_unbounded_pool_ceiling`).
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
            await _tell_apart_and_index(conn)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(
        self, principal: Principal, name: str, *, suffix_if_taken: bool = False
    ) -> Dataset:
        dataset = Dataset(
            id=new_id(),
            name=_clean(name),
            owning_unit=principal.org_unit,
            created_at=datetime.now(UTC),
            created_by=principal.id,
        )
        return await self._insert(dataset, suffix_if_taken=suffix_if_taken)

    async def register(self, dataset: Dataset) -> Dataset:
        """A dataset with a chosen id (`scripts.stamp_datasets` names the seeds' datasets).
        Writing the same id again leaves the record as it is; a name another of the unit's
        datasets holds takes a suffix."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM datasets d WHERE d.id = $1", dataset.id
            )
        if row is not None:
            return Dataset(**dict(row))
        return await self._insert(
            dataset.model_copy(update={"name": _clean(dataset.name)}), suffix_if_taken=True
        )

    async def add(self, dataset: Dataset) -> Dataset:
        return await self.register(dataset)

    async def _insert(self, dataset: Dataset, *, suffix_if_taken: bool) -> Dataset:
        name, n = dataset.name, 2
        while True:
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO datasets (id, name, owning_unit, created_at, created_by) "
                        "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
                        dataset.id,
                        name,
                        dataset.owning_unit,
                        dataset.created_at,
                        dataset.created_by,
                    )
                return dataset.model_copy(update={"name": name})
            except asyncpg.UniqueViolationError as exc:
                if not suffix_if_taken:
                    raise _taken(dataset.name) from exc
                name, n = _suffixed(dataset.name, n), n + 1

    async def known(self, dataset_ids: Sequence[str]) -> set[str]:
        if not dataset_ids:
            return set()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM datasets WHERE id = ANY($1::text[])", list(set(dataset_ids))
            )
        return {r["id"] for r in rows}

    async def list_for_unit(self, unit: str) -> list[Dataset]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM datasets d WHERE d.owning_unit = $1 ORDER BY d.name",
                unit,
            )
        return [Dataset(**dict(r)) for r in rows]

    async def of_case(self, investigation_id: str) -> list[Dataset]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM investigation_datasets c "
                "JOIN datasets d ON d.id = c.dataset_id "
                "WHERE c.investigation_id = $1 ORDER BY c.position",
                investigation_id,
            )
        return [Dataset(**dict(r)) for r in rows]

    async def ids_of_case(self, investigation_id: str) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT dataset_id FROM investigation_datasets WHERE investigation_id = $1 "
                "ORDER BY position",
                investigation_id,
            )
        return [r["dataset_id"] for r in rows]

    async def set_for_case(
        self, investigation_id: str, dataset_ids: Sequence[str], principal: Principal
    ) -> list[Dataset]:
        ordered = _ordered(dataset_ids)
        async with self._pool.acquire() as conn, conn.transaction():
            held = await conn.fetch(
                "SELECT id FROM datasets WHERE id = ANY($1::text[]) AND owning_unit = $2",
                ordered,
                principal.org_unit,
            )
            if {r["id"] for r in held} != set(ordered):
                raise DatasetRefusedError("not every dataset is one of this unit's")
            await conn.execute(
                "DELETE FROM investigation_datasets WHERE investigation_id = $1", investigation_id
            )
            await conn.executemany(
                "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
                "VALUES ($1, $2, $3)",
                [(investigation_id, d, i) for i, d in enumerate(ordered)],
            )
        return await self.of_case(investigation_id)

    async def copy_case(self, from_investigation_id: str, to_investigation_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
                "SELECT $2, dataset_id, position FROM investigation_datasets "
                "WHERE investigation_id = $1 ON CONFLICT DO NOTHING",
                from_investigation_id,
                to_investigation_id,
            )


__all__: Sequence[str] = (
    "CaseDatasetsRequest",
    "CreateDatasetRequest",
    "Dataset",
    "DatasetRefusedError",
    "DatasetStore",
    "InMemoryDatasetStore",
    "PostgresDatasetStore",
)
