"""The indexer in the worker process (ADR-150 decision 2): on a shape with an OpenSearch
configured (`OPENSEARCH_URL` or `OPENSEARCH_HOST` set), one worker replica at a time drains the
outboxes, the one holding a lease in Valkey. Two drainers at once could each read a node, and the
one that read it first could write after the other, leaving the older state; one holder never
can. A replica that stops holding the lease (it was slow past the lease) stops before its next
batch, and its batch's rows stay in the outbox until the new holder sends them."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from typing import Any, Protocol

from .indexer import SearchIndexer, ensure_index

log = logging.getLogger(__name__)

LEASE_KEY = "search-index:indexer"
LEASE_SECONDS = 30


class LeaseStore(Protocol):
    """Valkey's own `set`, `get` and `expire`, as the asyncio client gives them."""

    def set(self, name: Any, value: Any, *args: Any, **kwargs: Any) -> Any: ...

    def get(self, name: Any) -> Any: ...

    def expire(self, name: Any, time: Any, *args: Any, **kwargs: Any) -> Any: ...


def configured(environ: Mapping[str, str] | None = None) -> bool:
    """Whether this shape has an OpenSearch: an address was given. Where none is, nothing indexes
    and the search box keeps the graph's search (ROUTE_052 requirement c)."""
    env = os.environ if environ is None else environ
    return bool((env.get("OPENSEARCH_URL") or env.get("OPENSEARCH_HOST") or "").strip())


async def hold_lease(store: LeaseStore, me: str) -> bool:
    """True while `me` holds the indexer's lease, taking it when it is free and renewing it when it
    is ours."""
    if await store.set(LEASE_KEY, me, nx=True, ex=LEASE_SECONDS):
        return True
    held = await store.get(LEASE_KEY)
    if isinstance(held, bytes):
        held = held.decode()
    if held == me:
        await store.expire(LEASE_KEY, LEASE_SECONDS)
        return True
    return False


async def run_indexer(
    indexer: SearchIndexer,
    store: LeaseStore,
    me: str,
    stop: asyncio.Event,
    *,
    idle_seconds: float = 1.0,
) -> None:
    """Drains while this replica holds the lease, until `stop` is set."""
    ready = False
    while not stop.is_set():
        done = 0
        try:
            if await hold_lease(store, me):
                if not ready:
                    await ensure_index(indexer.client, indexer.alias)
                    ready = True
                done = await indexer.drain_once()
        except Exception:  # noqa: BLE001 - the batch stays in its outbox; said, then retried
            log.exception("search index: a batch failed and stays in the outbox")
        if done == 0:
            try:
                await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
            except TimeoutError:
                pass
