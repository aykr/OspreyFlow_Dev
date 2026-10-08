"""The Explore panel's figures, kept (`06_DECISIONS.md` ADR-100's cost rule, Amendment 3).

Counted live they took 8.4 s (what the case holds) and 7.8 s (the top ten) on the Enron case,
measured, so each is computed once and kept in Valkey, keyed by the reader's access class, which
includes the case's datasets (`cache.principal_class`): never counted once for everyone and
filtered afterwards. What is kept is cleared on every graph write the Conduit makes, and lasts an
hour at most for a write it does not see (a seed run from its own container). Each figure says
when it was counted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from schemas.analytics import EventFilter, HistogramBucketing, HistogramRequest
from schemas.domain import Principal
from schemas.explore import BusiestDays, BusyDay, RankedLinks, RankedNodes, TypeCounts

#: A day, the busiest days' bucket.
DAY_SECONDS = 86_400

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

    async def busiest_links(
        self,
        principal: Principal,
        *,
        edge_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> RankedLinks:
        signature = f"explore:{_VERSION}:busiest-links:{edge_type or '*'}:{limit}:{offset}"
        if self._cache is not None and (held := await self._cache.get(signature, principal)):
            return RankedLinks.model_validate(held)
        ranked = (
            await self._graph.busiest_links(
                principal, edge_type=edge_type, limit=limit, offset=offset
            )
        ).model_copy(update={"computed_at": self._now()})
        if self._cache is not None:
            await self._cache.put(signature, principal, ranked.model_dump(mode="json"))
        return ranked

    async def busiest_days(
        self,
        principal: Principal,
        analytics: AnalyticsPort,
        case_events: EventFilter,
        *,
        limit: int = 10,
        offset: int = 0,
    ) -> BusiestDays:
        """The case's days by events (ADR-100 decision 5), from its daily histogram. Events belong
        to a case, not a dataset (ADR-099 decision 7), so what is kept is keyed by the case's own
        filter too (its scope and, on a branch, the parents' links it reads)."""
        scope = hashlib.sha256(case_events.model_dump_json().encode()).hexdigest()[:16]
        signature = f"explore:{_VERSION}:busiest-days:{scope}:{limit}:{offset}"
        if self._cache is not None and (held := await self._cache.get(signature, principal)):
            return BusiestDays.model_validate(held)
        histogram = await analytics.histogram(
            HistogramRequest(
                filter=case_events,
                bucketing=HistogramBucketing.FIXED_INTERVAL,
                interval_seconds=DAY_SECONDS,
            ),
            principal,
        )
        ranked = sorted(
            (b for b in histogram.buckets if b.start is not None and b.end is not None and b.count),
            key=lambda b: (-b.count, b.start),
        )
        days = BusiestDays(
            days=[
                BusyDay(start=b.start, end=b.end, count=b.count)  # type: ignore[arg-type]
                for b in ranked[offset : offset + limit]
            ],
            total=len(ranked),
            offset=offset,
            computed_at=self._now(),
        )
        if self._cache is not None:
            await self._cache.put(signature, principal, days.model_dump(mode="json"))
        return days

    async def invalidate(self) -> None:
        if self._cache is not None:
            await self._cache.invalidate_prefix()
