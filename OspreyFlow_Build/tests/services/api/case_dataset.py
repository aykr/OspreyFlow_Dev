"""A case and the data written for it share one dataset, for route tests that run the real app
over real stores (ADR-099).

Since ADR-099 a case reads only its own datasets, so a test that writes nodes straight into the
graph and then reads them through a case must put both in the same dataset, as a real load into the
case does. `dataset_for(principal)` is that dataset (one per unit, since a case may only name its
own unit's); `give_case_its_dataset` records it as the case's."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
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


def new_case(name: str | None = None, **body: object) -> dict[str, object]:
    """A `POST /v1/investigations` body for a case over a new, empty dataset of the caller's unit
    (ADR-099 Amendment 12 item 6: a case names one dataset, or a new one; the Conduit no longer
    makes one for a case that names none). The dataset's name is unique, so a test may make many."""
    from uuid import uuid4

    made: dict[str, object] = {"new_dataset_name": f"Test data {uuid4().hex[:12]}", **body}
    if name is not None:
        made["name"] = name
    return made


#: The layer `in_a_case_with_a_layer` holds for a test.
TEST_LAYER = "analyst-layer-of-the-test-case"


@pytest.fixture
def in_a_case_with_a_layer(monkeypatch: pytest.MonkeyPatch) -> str:
    """For a test that drives an analyst's own writer (a mark made by hand, a manual link or split)
    directly, outside any request: the writer then holds a case's layer, as it does under a route
    (ADR-143 Amendment 1), and refuses without one. Nothing else of the case's scope is set."""
    from services.api import dataset_scope

    monkeypatch.setattr(dataset_scope, "analyst_layer", lambda: TEST_LAYER)
    return TEST_LAYER
