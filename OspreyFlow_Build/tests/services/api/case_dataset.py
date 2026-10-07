"""A case and the data written for it share one dataset, for route tests that run the real app
over real stores (ADR-099).

Since ADR-099 a case reads only its own datasets, so a test that writes nodes straight into the
graph and then reads them through a case must put both in the same dataset, as a real load into the
case does. `dataset_for(principal)` is that dataset (one per unit, since a case may only name its
own unit's); `give_case_its_dataset` records it as the case's."""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.config import PostgresConfig
from services.api.datasets import Dataset, PostgresDatasetStore

from schemas.domain import Principal


def dataset_for(principal: Principal) -> str:
    return f"route-test-{principal.org_unit}"


async def give_case_its_dataset(investigation_id: str, principal: Principal) -> None:
    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.add(
            Dataset(
                id=dataset_for(principal),
                name="Route test data",
                owning_unit=principal.org_unit,
                created_at=datetime.now(UTC),
                created_by="test",
            )
        )
        await store.set_for_case(investigation_id, [dataset_for(principal)], principal)
    finally:
        await store.close()
