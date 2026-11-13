"""ADR-150 decision 2, offline: the indexer runs only where an OpenSearch is configured, and one
worker replica at a time drains, the one holding the Valkey lease."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from services.search_index import run


class _Valkey:
    """`set(nx=True, ex=…)`, `get` and `expire` as Valkey answers them; no clock (a lease lasts)."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    async def set(self, name: str, value: str, *, nx: bool = False, ex: int | None = None) -> Any:
        if nx and name in self.data:
            return None
        self.data[name] = value.encode()
        return True

    async def get(self, name: str) -> Any:
        return self.data.get(name)

    async def expire(self, name: str, time: int) -> Any:
        return name in self.data


class _Indexer:
    client = object()
    alias = "a"

    def __init__(self) -> None:
        self.drained = 0

    async def drain_once(self) -> int:
        self.drained += 1
        return 0


def test_nothing_indexes_where_no_opensearch_is_configured() -> None:
    assert not run.configured({})
    assert not run.configured({"OPENSEARCH_PORT": "9200"})
    assert run.configured({"OPENSEARCH_HOST": "opensearch"})
    assert run.configured({"OPENSEARCH_URL": "https://x"})


async def test_the_lease_is_one_replicas_and_renewed_by_it() -> None:
    store = _Valkey()
    assert await run.hold_lease(store, "worker-1")
    assert not await run.hold_lease(store, "worker-2")
    assert await run.hold_lease(store, "worker-1")


async def test_only_the_replica_holding_the_lease_drains(monkeypatch: pytest.MonkeyPatch) -> None:
    async def made(client: Any, alias: str) -> None:
        return None

    monkeypatch.setattr(run, "ensure_index", made)
    store, stop = _Valkey(), asyncio.Event()
    first, second = _Indexer(), _Indexer()
    tasks = [
        asyncio.create_task(run.run_indexer(first, store, "worker-1", stop, idle_seconds=0.01)),  # type: ignore[arg-type]
        asyncio.create_task(run.run_indexer(second, store, "worker-2", stop, idle_seconds=0.01)),  # type: ignore[arg-type]
    ]
    await asyncio.sleep(0.2)
    stop.set()
    await asyncio.gather(*tasks)
    assert (first.drained > 0) != (second.drained > 0), (first.drained, second.drained)
