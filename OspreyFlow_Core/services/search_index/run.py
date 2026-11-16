"""The indexer (ADR-150 decision 2): on a shape with an OpenSearch configured (`OPENSEARCH_URL` or
`OPENSEARCH_HOST` set), one process at a time drains the outboxes, the one holding a lease in
Valkey. It runs in the worker process where the profile renders one, and in the Conduit's own
lifespan, beside its job loop, where it renders none (local-lite, Small; Amendment 4): both
start it through `start_index_feed`, so the two never differ. Two drainers at once could each
read a node, and the one that read it first could write after the other, leaving the older
state; one holder never can. A replica that stops holding the lease (it was slow past the lease)
stops before its next batch, and its batch's rows stay in the outbox until the new holder sends
them."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from schemas.domain import OntologySchema

from .client import SearchIndexConfig, search_client
from .indexer import SearchIndexer, TextFeedSource, ensure_index

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


@dataclass
class IndexFeed:
    """A running feed: its task, the event that stops it, and the client it alone opened."""

    task: asyncio.Task[None]
    stop: asyncio.Event
    alias: str
    closing: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def close(self, timeout: float | None = None) -> None:
        """Stops the feed and closes its client. The batch in hand finishes and its rows are
        cleared; past `timeout` it is cancelled, and its rows stay in the outbox for the next
        holder (delivery is at least once, ADR-150 decision 2)."""
        self.stop.set()
        try:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=timeout)
        except TimeoutError:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        for close in self.closing:
            await close()


def start_index_feed(
    source: Any,
    texts: TextFeedSource,
    store: LeaseStore,
    me: str,
    schema: OntologySchema,
    *,
    stop: asyncio.Event | None = None,
    environ: Mapping[str, str] | None = None,
    idle_seconds: float = 1.0,
) -> IndexFeed | None:
    """The one way a process starts the feed: None where no OpenSearch is configured (nothing
    indexes, and search stays on the graph's). `source` is the graph adapter itself, whose narrow
    port only the indexer names (`test_index_feed_reach.py`); `store` is the process's Valkey;
    `me` names this process in the lease, distinct from every other process's."""
    if not configured(environ):
        return None
    config = SearchIndexConfig.from_env(environ)
    client = search_client(config)
    indexer = SearchIndexer(source, texts, client, config.alias, schema)
    stop = stop or asyncio.Event()
    task = asyncio.create_task(run_indexer(indexer, store, me, stop, idle_seconds=idle_seconds))
    return IndexFeed(task=task, stop=stop, alias=config.alias, closing=[client.close])
