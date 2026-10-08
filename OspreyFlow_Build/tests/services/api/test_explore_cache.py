"""The Explore panel's figures are kept, not counted on each opening (ADR-100's cost rule, measured:
8.4 s for the counts and 7.8 s for the top ten on the Enron case, Amendment 3).

Kept per access class, which includes the case's datasets (`cache.principal_class`), never once
for everyone and filtered afterwards. What a mistake would do, and the case that catches it:

- every opening counting again (`test_a_second_opening_is_served_from_what_was_kept`);
- one case, or one clearance, served another's figures
  (`test_another_case_or_clearance_is_counted_for_itself`);
- one page or type served for another (`test_each_page_and_type_is_kept_apart`);
- figures kept past a write that changed them
  (`test_a_write_through_the_conduit_clears_what_was_kept`);
- figures that do not say when they were counted (`test_figures_say_when_they_were_counted`).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from services.api.cache import principal_class
from services.api.dataset_scope import stamping
from services.api.explore import ExploreService

from schemas.domain import Principal
from schemas.explore import RankedNodes, TypeCounts

ENRON = Principal(id="a", clearance="OFFICIAL", org_unit="u", datasets=["enron"])
FIXTURE = ENRON.model_copy(update={"datasets": ["fixture-corp"]})
SECRET_ENRON = ENRON.model_copy(update={"clearance": "SECRET"})
T0 = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


class _Cache:
    """`CachedQuery`'s shape, in memory, keyed as it keys."""

    def __init__(self) -> None:
        self.held: dict[tuple[str, str], Any] = {}

    async def get(self, signature: str, principal: Principal) -> Any | None:
        return self.held.get((signature, principal_class(principal)))

    async def put(self, signature: str, principal: Principal, result: Any) -> None:
        self.held[(signature, principal_class(principal))] = result

    async def invalidate_prefix(self) -> None:
        self.held.clear()


class _Graph:
    def __init__(self) -> None:
        self.counted: list[Principal] = []
        self.ranked: list[tuple[str | None, int, int]] = []

    async def type_counts(self, principal: Principal) -> TypeCounts:
        self.counted.append(principal)
        return TypeCounts(nodes={"Endpoint": len(self.counted)}, edges={})

    async def most_connected(
        self,
        principal: Principal,
        *,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> RankedNodes:
        self.ranked.append((entity_type, limit, offset))
        return RankedNodes(nodes=[], total=len(self.ranked), offset=offset)

    async def upsert_nodes(self, nodes: Sequence[Any], tx: Any) -> list[str]:
        return [n.id for n in nodes]

    async def revert_elements(
        self, node_ids: Sequence[str], edge_ids: Sequence[str], tx: Any
    ) -> None:
        return None


def _service() -> tuple[ExploreService, _Graph, _Cache]:
    graph, cache = _Graph(), _Cache()
    return ExploreService(graph, cache, now=lambda: T0), graph, cache  # type: ignore[arg-type]


async def test_a_second_opening_is_served_from_what_was_kept() -> None:
    service, graph, _ = _service()
    first = await service.counts(ENRON)
    again = await service.counts(ENRON)
    assert again == first and len(graph.counted) == 1
    await service.most_connected(ENRON)
    await service.most_connected(ENRON)
    assert len(graph.ranked) == 1


async def test_another_case_or_clearance_is_counted_for_itself() -> None:
    service, graph, _ = _service()
    await service.counts(ENRON)
    await service.counts(FIXTURE)
    await service.counts(SECRET_ENRON)
    assert [p.datasets for p in graph.counted] == [["enron"], ["fixture-corp"], ["enron"]]
    assert [p.clearance for p in graph.counted][2] == "SECRET"


async def test_each_page_and_type_is_kept_apart() -> None:
    service, graph, _ = _service()
    await service.most_connected(ENRON)
    await service.most_connected(ENRON, offset=10)
    await service.most_connected(ENRON, entity_type="Endpoint", limit=5)
    await service.most_connected(ENRON, entity_type="Endpoint", limit=5)
    assert graph.ranked == [(None, 10, 0), (None, 10, 10), ("Endpoint", 5, 0)]


async def test_a_write_through_the_conduit_clears_what_was_kept() -> None:
    service, graph, _ = _service()
    await service.counts(ENRON)
    written = stamping(graph)  # type: ignore[arg-type]
    written.after_write(service.invalidate)
    from tests.services.api.test_dataset_integrity import _node

    await written.upsert_nodes([_node("n1", ["enron"])], "tx")
    await service.counts(ENRON)
    assert len(graph.counted) == 2


async def test_figures_say_when_they_were_counted() -> None:
    service, _, _ = _service()
    assert (await service.counts(ENRON)).computed_at == T0
    assert (await service.most_connected(ENRON)).computed_at == T0


async def test_a_revert_through_the_conduit_clears_what_was_kept_too() -> None:
    service, graph, _ = _service()
    await service.counts(ENRON)
    written = stamping(graph)  # type: ignore[arg-type]
    written.after_write(service.invalidate)
    await written.revert_elements(["n1"], [], "tx")
    await service.counts(ENRON)
    assert len(graph.counted) == 2


class _Analytics:
    """`AnalyticsPort.histogram`'s shape: one bucket per day with events, as the DuckDB adapter
    answers (no empty days)."""

    def __init__(self) -> None:
        self.asked: list[Any] = []

    async def histogram(self, req: Any, principal: Principal) -> Any:
        from schemas.analytics import Histogram, HistogramBucket, HistogramBucketing

        self.asked.append(req)
        day = lambda d: datetime(2001, 5, d, tzinfo=UTC)  # noqa: E731
        counts = {1: 5, 2: 40, 3: 40, 4: 7}
        return Histogram(
            bucketing=HistogramBucketing.FIXED_INTERVAL,
            buckets=[
                HistogramBucket(start=day(d), end=day(d + 1), count=c) for d, c in counts.items()
            ],
            total=sum(counts.values()),
        )


async def test_the_busiest_days_rank_by_events_ties_by_date_and_page() -> None:
    from schemas.analytics import EventFilter

    service, _, _ = _service()
    analytics = _Analytics()
    case_filter = EventFilter(investigation_scope="case-e")
    first = await service.busiest_days(ENRON, analytics, case_filter, limit=2)  # type: ignore[arg-type]
    assert [(d.start.day, d.count) for d in first.days] == [(2, 40), (3, 40)]
    assert first.total == 4 and first.computed_at == T0
    rest = await service.busiest_days(ENRON, analytics, case_filter, limit=2, offset=2)  # type: ignore[arg-type]
    assert [(d.start.day, d.count) for d in rest.days] == [(4, 7), (1, 5)]
    # One day's buckets, asked of the case's own events.
    (req, *_) = analytics.asked
    assert req.interval_seconds == 86_400 and req.filter.investigation_scope == "case-e"


async def test_the_busiest_days_are_kept_per_case_as_events_belong_to_a_case() -> None:
    from schemas.analytics import EventFilter

    service, _, _ = _service()
    analytics = _Analytics()
    await service.busiest_days(ENRON, analytics, EventFilter(investigation_scope="case-e"))  # type: ignore[arg-type]
    await service.busiest_days(ENRON, analytics, EventFilter(investigation_scope="case-e"))  # type: ignore[arg-type]
    await service.busiest_days(ENRON, analytics, EventFilter(investigation_scope="case-f"))  # type: ignore[arg-type]
    assert [r.filter.investigation_scope for r in analytics.asked] == ["case-e", "case-f"]


async def test_the_busiest_links_are_kept_like_the_rest() -> None:
    service, graph, _ = _service()
    calls: list[Any] = []

    async def busiest_links(principal, *, edge_type=None, limit=10, offset=0):  # type: ignore[no-untyped-def]
        from schemas.explore import RankedLinks

        calls.append((edge_type, limit, offset))
        return RankedLinks(links=[], total=0, offset=offset)

    graph.busiest_links = busiest_links  # type: ignore[attr-defined]
    await service.busiest_links(ENRON)
    again = await service.busiest_links(ENRON)
    assert calls == [(None, 10, 0)] and again.computed_at == T0
