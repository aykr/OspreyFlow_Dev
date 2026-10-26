"""Query/analytics result caching — `spec/03_CONDUIT_MIDDLEWARE.md` §7:
three layers, three invalidation stories, kept separate "or you will
invalidate the wrong one".

Layer 1 (working set, `ws:{investigation_id}`, invalidated explicitly on
mutation) is `store.ValkeyWorkingSetStore` itself — that layer is not
duplicated here. This module is the other two: query-result and
analytics-result caches, both **keyed by `principal_class`, never
`principal_id`** — "the set of handling codes a principal may receive, not
the person... caching by person while keying on query is how
access-control leaks happen." Phase 3 ships no query or analytics
endpoint yet (`03_CONDUIT_MIDDLEWARE.md` §3.3 is a later phase), so
nothing in this phase's own route surface calls `CachedQuery` — it exists
now, correctly keyed and tested, so that surface has a cache layer to use
from its first commit rather than retrofitting the access-control-correct
key scheme onto a cache someone keyed by `principal_id` because it was
the obvious first thing to reach for.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from valkey.asyncio import Valkey

from conduit_common.valkey_compat import reply as _reply
from schemas.domain import Principal


def principal_class(principal: Principal) -> str:
    """A stable hash of the *set of handling codes a principal may
    receive* (`03_CONDUIT_MIDDLEWARE.md` §7) — not `clearance` alone.
    `01_DOMAIN_MODEL.md` §2.2's table makes `org_unit` part of what gates
    a *restricted* `handling_code`, so two principals in different units
    are a different access class even at the same clearance, and hashing
    codes without `org_unit` would let them share a cache entry a
    restricted-dissemination rule says they should not. `receivable_
    handling_codes` is sorted so the same set in a different claim order
    hashes identically. The case's `datasets` are an access axis like handling (ADR-099), so they
    are part of the class too, sorted; `None` (unlimited background work) and `[]` (nothing) stay
    distinct."""
    payload = json.dumps(
        {
            "clearance": principal.clearance,
            "org_unit": principal.org_unit,
            "receivable_handling_codes": sorted(principal.receivable_handling_codes),
            "datasets": None if principal.datasets is None else sorted(set(principal.datasets)),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_key(prefix: str, query_signature: str, p_class: str) -> str:
    digest = hashlib.sha256(f"{query_signature}:{p_class}".encode()).hexdigest()
    return f"cache:{prefix}:{digest}"


class CachedQuery:
    """A get-or-compute cache over one Valkey `db`, generic in what it
    stores (JSON-serialisable results) and in the TTL — the query-result
    layer (300s) and the analytics-result layer (900s),
    `03_CONDUIT_MIDDLEWARE.md` §7's own figures, are two instances of this
    with different `prefix`/`ttl_seconds`, not two classes."""

    def __init__(self, client: Valkey, *, prefix: str, ttl_seconds: int) -> None:
        self._client = client
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds

    async def get(self, query_signature: str, principal: Principal) -> Any | None:
        key = _cache_key(self._prefix, query_signature, principal_class(principal))
        raw = await _reply(self._client.get(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def put(self, query_signature: str, principal: Principal, result: Any) -> None:
        key = _cache_key(self._prefix, query_signature, principal_class(principal))
        await _reply(self._client.set(key, json.dumps(result), ex=self._ttl_seconds))

    async def invalidate_prefix(self) -> None:
        """`03_CONDUIT_MIDDLEWARE.md` §7: query results invalidate "on
        graph write to touched types", analytics results "on partition
        load". Both are coarse, deployment-wide invalidations in this
        phase's implementation — scoping invalidation to the specific
        touched types/partitions is real work with no caller yet to prove
        it against (`03_CONDUIT_MIDDLEWARE.md` §3.3's endpoints), so it is
        named here as the gap it is rather than built against a caller
        that doesn't exist."""
        await _delete_prefix(self._client, self._prefix)


async def _delete_prefix(client: Valkey, prefix: str) -> None:
    """Every key `cache:<prefix>:*`, by `SCAN` (never `KEYS`) in batches of 500."""
    cursor = 0
    pattern = f"cache:{prefix}:*"
    while True:
        cursor, keys = await _reply(client.scan(cursor, match=pattern, count=500))
        if keys:
            await _reply(client.delete(*keys))
        if cursor == 0:
            break


def query_result_cache(client: Valkey) -> CachedQuery:
    return CachedQuery(client, prefix="query", ttl_seconds=300)


def analytics_result_cache(client: Valkey) -> CachedQuery:
    return CachedQuery(client, prefix="analytics", ttl_seconds=900)


#: Every kind of kept result the Conduit holds, by the `cache:<prefix>:` its keys carry. They live
#: in the shared Valkey, so one process clearing a prefix clears it for every Conduit instance. The
#: revert (`services/ingest/load_revert.py`) clears all of them, since a reverted load's events and
#: elements are in whatever was counted before it; a test holds that each `CachedQuery` the Conduit
#: builds is named here (`test_every_cache_the_conduit_keeps_is_one_the_revert_clears`).
CACHE_PREFIXES = ("explore", "query", "analytics")


async def invalidate_every_cache(client: Valkey) -> None:
    """Clears every kept result (`CACHE_PREFIXES`) from the shared Valkey: for a process outside the
    Conduit, a revert, whose message to every instance is these keys going."""
    for prefix in CACHE_PREFIXES:
        await _delete_prefix(client, prefix)
