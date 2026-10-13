"""ADR-114 decision 9's statelessness proof, for analytics: two Conduit processes on one shared
ClickHouse serve one case's events alike, and the second keeps answering after the first is killed.

`test_statelessness.py` proves continuity through ArcadeDB, Valkey and Postgres and says why it
could not prove it for analytics: each process had its own DuckDB file, since DuckDB takes an
exclusive lock. On ClickHouse the store is shared, so the claim can be made and is made here —
over the wire, against two real `uvicorn` processes, one killed outright.

Events are written straight into the shared store, as the ingest engine writes them, so the test
measures what each Conduit reads rather than which one wrote. Needs the live stack the other
statelessness test needs, plus ClickHouse (`CLICKHOUSE_HTTP_PORT`).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from ulid import ULID

from adapters.analytics_clickhouse.adapter import AnalyticsClickHouseAdapter
from adapters.analytics_clickhouse.client import ClickHouseClient, ClickHouseSettings
from adapters.analytics_clickhouse.schema import create_tables
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventRecord
from schemas.domain import Handling
from tests.services.api.test_statelessness import _bearer, _ConduitInstance


@pytest.fixture
def database() -> Iterator[str]:
    name = f"stateless_{str(ULID()).lower()}"
    yield name

    async def drop() -> None:
        client = ClickHouseClient(ClickHouseSettings.from_env(name))
        await client.command(f"DROP DATABASE IF EXISTS {name}", database=None)
        await client.aclose()

    asyncio.run(drop())


@pytest.fixture
def two_clickhouse_instances(
    jwks_url: str, database: str
) -> Iterator[tuple[_ConduitInstance, _ConduitInstance]]:
    env = {"OSPREY_ANALYTICS_ENGINE": "clickhouse", "CLICKHOUSE_DATABASE": database}
    instances: list[_ConduitInstance] = []
    try:
        instances.append(_ConduitInstance(jwks_url, extra_env=env))
        instances.append(_ConduitInstance(jwks_url, extra_env=env))
        yield instances[0], instances[1]
    finally:
        for instance in instances:
            if instance._process.poll() is None:
                instance._process.kill()
                instance._process.wait(timeout=10)


def _load(database: str, case: str, count: int) -> None:
    """What an ingest run does: events into the case's scope, through the adapter's write path."""

    async def load() -> None:
        client = ClickHouseClient(ClickHouseSettings.from_env(database))
        await create_tables(client)
        adapter = AnalyticsClickHouseAdapter(client, load_uk_le_scheme())
        await adapter.load_events(
            [
                EventRecord(
                    event_id=str(ULID()),
                    edge_id=f"e{n}",
                    edge_type="COMMUNICATED_WITH" if n % 2 else "MET",
                    source_id="a",
                    target_id="b",
                    occurred_at=datetime(2026, 1, 1 + n, 12, tzinfo=UTC),
                    investigation_scope=case,
                    handling=Handling(
                        classification="OFFICIAL",
                        handling_code="P",
                        owning_unit="unit-1",
                        originator="unit-1",
                    ),
                )
                for n in range(count)
            ]
        )
        await client.aclose()

    asyncio.run(load())


def _histogram(instance: _ConduitInstance, case: str, headers: dict[str, str]) -> dict[str, int]:
    response = httpx.post(
        f"{instance.base_url}/v1/analytics/histogram",
        headers=headers,
        json={
            "filter": {"investigation_scope": case},
            "bucketing": "categorical",
            "field": "edge_type",
        },
        timeout=30,
    )
    assert response.status_code == 200, response.text
    return {b["label"]: b["count"] for b in response.json()["buckets"]}


def test_two_conduits_on_one_clickhouse_answer_alike_and_the_second_survives_the_first(
    two_clickhouse_instances: tuple[_ConduitInstance, _ConduitInstance],
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    database: str,
) -> None:
    assert os.environ.get("CLICKHOUSE_HTTP_PORT"), "needs the live ClickHouse"
    instance_a, instance_b = two_clickhouse_instances
    headers = _bearer(keypair[0])
    created = httpx.post(f"{instance_a.base_url}/v1/investigations", headers=headers)
    assert created.status_code == 201, created.text
    case = created.json()["id"]

    _load(database, case, 5)
    expected = {"COMMUNICATED_WITH": 2, "MET": 3}
    assert _histogram(instance_a, case, headers) == expected
    assert _histogram(instance_b, case, headers) == expected

    instance_a.kill()
    _load(database, case, 1)  # written after A is gone; B must see it too
    assert _histogram(instance_b, case, headers) == {"COMMUNICATED_WITH": 2, "MET": 4}
