"""The Explore panel's figures, kept (`06_DECISIONS.md` ADR-100's cost rule, Amendment 3).

Counted live they took 8.4 s (what the case holds) and 7.8 s (the top ten) on the Enron case,
measured, so each is computed once and kept in Valkey, keyed by the reader's access class, which
includes the case's datasets (`cache.principal_class`): never counted once for everyone and
filtered afterwards. What is kept is cleared on every graph write the Conduit makes, and lasts an
hour at most for a write it does not see (a seed run from its own container). Each figure says
when it was counted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from ports.graph import GraphPort
from schemas.domain import Principal
from schemas.explore import RankedNodes, TypeCounts

#: How long a figure is kept when no write the Conduit sees clears it first.
EXPLORE_TTL_SECONDS = 3600
#: Bumped when what is kept changes shape, so an older entry is never read as a newer one.
_VERSION = "v1"


class ExploreCache(Protocol):
    async def get(self, query_signature: str, principal: Principal) -> Any | None: ...
    async def put(self, query_signature: str, principal: Principal, result: Any) -> None: ...
    async def invalidate_prefix(self) -> None: ...


def _now() -> datetime:
    return datetime.now(UTC)


class ExploreService:
    def __init__(
        self,
        graph: GraphPort,
        cache: ExploreCache | None,
        *,
        now: Callable[[], datetime] = _now,
    ) -> None:
        self._graph = graph
        self._cache = cache
        self._now = now

    async def counts(self, principal: Principal) -> TypeCounts:
        signature = f"explore:{_VERSION}:counts"
        if self._cache is not None and (held := await self._cache.get(signature, principal)):
            return TypeCounts.model_validate(held)
        counts = (await self._graph.type_counts(principal)).model_copy(
            update={"computed_at": self._now()}
        )
        if self._cache is not None:
            await self._cache.put(signature, principal, counts.model_dump(mode="json"))
        return counts

    async def most_connected(
        self,
        principal: Principal,
        *,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> RankedNodes:
        signature = f"explore:{_VERSION}:most-connected:{entity_type or '*'}:{limit}:{offset}"
        if self._cache is not None and (held := await self._cache.get(signature, principal)):
            return RankedNodes.model_validate(held)
        ranked = (
            await self._graph.most_connected(
                principal, entity_type=entity_type, limit=limit, offset=offset
            )
        ).model_copy(update={"computed_at": self._now()})
        if self._cache is not None:
            await self._cache.put(signature, principal, ranked.model_dump(mode="json"))
        return ranked

    async def invalidate(self) -> None:
        if self._cache is not None:
            await self._cache.invalidate_prefix()
