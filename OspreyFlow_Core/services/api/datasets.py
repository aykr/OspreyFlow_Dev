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
    async def create(self, principal: Principal, name: str) -> Dataset: ...
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

    async def register(self, dataset: Dataset) -> Dataset:
        """A dataset with a chosen id; writing the same id again keeps the first record."""
        return self.datasets.setdefault(dataset.id, dataset)

    async def create(self, principal: Principal, name: str) -> Dataset:
        return self.add(
            Dataset(
                id=new_id(),
                name=_clean(name),
                owning_unit=principal.org_unit,
                created_at=datetime.now(UTC),
                created_by=principal.id,
            )
        )

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


class PostgresDatasetStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> PostgresDatasetStore:
        pool = await asyncpg.create_pool(dsn)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP_SQL)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def create(self, principal: Principal, name: str) -> Dataset:
        dataset = Dataset(
            id=new_id(),
            name=_clean(name),
            owning_unit=principal.org_unit,
            created_at=datetime.now(UTC),
            created_by=principal.id,
        )
        await self.add(dataset)
        return dataset

    async def register(self, dataset: Dataset) -> Dataset:
        return await self.add(dataset)

    async def add(self, dataset: Dataset) -> Dataset:
        """A dataset with a chosen id (`scripts.stamp_datasets` names the seeds' datasets).
        Writing the same id again leaves the record as it is."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO datasets (id, name, owning_unit, created_at, created_by) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING",
                dataset.id,
                dataset.name,
                dataset.owning_unit,
                dataset.created_at,
                dataset.created_by,
            )
        return dataset

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
