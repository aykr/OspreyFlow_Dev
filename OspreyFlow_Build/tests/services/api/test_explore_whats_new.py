"""What is new in a case (ADR-100 decision 7, Amendment 6): the latest loads, and what colleagues
confirmed or marked, each the reader's own.

What a mistake would do, and the case that catches it:

- a mark on a node the reader cannot see named or counted, by clearance or by dataset
  (`test_a_mark_is_named_and_counted_only_where_the_store_shows_its_node`, real ArcadeDB and
  Postgres: the store's own access step is the thing under test, not a fake's);
- loads and confirmations counted again on every opening
  (`test_loads_and_confirmations_are_kept_and_marks_are_read_each_time`);
- a mark made since the last count missing until something else is written (the same case: a
  mark writes nothing to the graph, so nothing would clear what is kept);
- a list cut at ten that says nothing of the rest (`test_what_is_not_shown_is_counted`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from services.api.config import PostgresConfig
from services.api.explore import ExploreService
from services.api.suppression import SuppressionMark, SuppressionMarkStore

from adapters.graph_arcadedb.testing import arcadedb_adapter
from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    Handling,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.explore import RecentLoads, RecentlyConfirmed

READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1", datasets=["fixture"])
SECRET_COLLEAGUE = READER.model_copy(update={"id": "colleague", "clearance": "SECRET"})
OTHER_CASE = READER.model_copy(update={"id": "elsewhere", "datasets": ["enron"]})
T0 = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def _person(*, classification: str = "OFFICIAL", datasets: list[str] | None = None) -> NodeWrite:
    return NodeWrite(
        id=new_id(),
        type="Person",
        properties={"family_name": "Test"},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator="row:1", excerpt_hash="")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification=classification, handling_code="P", originator="unit-1",
            owning_unit="unit-1",
        ),
        created_by="loader",
        created_at=datetime.now(UTC),
        datasets=datasets if datasets is not None else ["fixture"],
    )


@pytest.fixture
async def marks():
    store = await SuppressionMarkStore.connect(PostgresConfig.from_env().dsn)
    yield store
    await store.close()


async def test_a_mark_is_named_and_counted_only_where_the_store_shows_its_node(marks) -> None:
    async with arcadedb_adapter(load_default_ontology(), load_uk_le_scheme()) as graph:
        seen, secret = _person(), _person(classification="SECRET")
        enron = _person(datasets=["enron"])
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([seen, secret, enron], tx)
        await graph.commit_transaction(tx)
        case = new_id()
        await marks.mark(seen.id, case, READER, graph, reason="a duplicate")
        await marks.mark(secret.id, case, SECRET_COLLEAGUE, graph, reason="hidden from the reader")
        await marks.mark(enron.id, new_id(), OTHER_CASE, graph, reason="another dataset's")
        try:
            explore = ExploreService(graph, None)
            news = await explore.whats_new(READER, marks)
            assert [m.node.id for m in news.marked] == [seen.id]
            assert news.marked_total == 1
            assert news.marked[0].reason == "a duplicate" and news.marked[0].marked_by == "reader"
            # The filter is real: a cleared colleague in the same case sees both of its marks.
            cleared = await explore.whats_new(SECRET_COLLEAGUE, marks)
            assert {m.node.id for m in cleared.marked} == {seen.id, secret.id}
        finally:
            for node in (seen, secret):
                await marks.unmark(node.id, SECRET_COLLEAGUE, graph)
            await marks.unmark(enron.id, OTHER_CASE, graph)


class _Marks:
    def __init__(self) -> None:
        self.held: list[SuppressionMark] = []
        self.read = 0

    async def recent(self) -> list[SuppressionMark]:
        self.read += 1
        return sorted(self.held, key=lambda m: m.marked_at, reverse=True)


class _Graph:
    """Sees every node in `visible`; counts how often the store is asked for loads."""

    def __init__(self, visible: dict[str, Node]) -> None:
        self.visible = visible
        self.counted = 0

    async def recent_loads(self, principal: Principal, *, limit: int = 10) -> RecentLoads:
        self.counted += 1
        return RecentLoads(loads=[], total=0)

    async def recently_confirmed(
        self, principal: Principal, *, limit: int = 10
    ) -> RecentlyConfirmed:
        return RecentlyConfirmed(nodes=[], total=0)

    async def get_node(self, node_id: str, principal: Principal) -> Node | None:
        return self.visible.get(node_id)


class _Cache:
    def __init__(self) -> None:
        self.held: dict[str, Any] = {}

    async def get(self, signature: str, principal: Principal) -> Any | None:
        return self.held.get(signature)

    async def put(self, signature: str, principal: Principal, result: Any) -> None:
        self.held[signature] = result

    async def invalidate_prefix(self) -> None:
        self.held.clear()


def _node(node_id: str) -> Node:
    write = _person()
    return Node.model_validate(
        {
            **write.model_dump(exclude={"created_by", "created_at", "load_id", "recipe_id",
                                        "recipe_version"}),
            "id": node_id,
            "audit": {"created_at": T0, "created_by": "loader"},
        }
    )


def _mark(node_id: str, minutes: int) -> SuppressionMark:
    return SuppressionMark(
        node_id=node_id, investigation_id="case", marked_by="colleague",
        marked_at=T0 + timedelta(minutes=minutes), reason="proposed",
    )


async def test_loads_and_confirmations_are_kept_and_marks_are_read_each_time() -> None:
    graph, marks = _Graph({"n1": _node("n1"), "n2": _node("n2")}), _Marks()
    explore = ExploreService(graph, _Cache(), now=lambda: T0)  # type: ignore[arg-type]
    marks.held.append(_mark("n1", 1))
    first = await explore.whats_new(READER, marks)
    assert [m.node.id for m in first.marked] == ["n1"] and first.computed_at == T0
    marks.held.append(_mark("n2", 2))
    second = await explore.whats_new(READER, marks)
    assert graph.counted == 1, "loads were counted again on a second opening"
    assert [m.node.id for m in second.marked] == ["n2", "n1"], "a new mark waited for a write"
    assert marks.read == 2


async def test_what_is_not_shown_is_counted() -> None:
    graph = _Graph({f"n{i}": _node(f"n{i}") for i in range(12)})
    marks = _Marks()
    marks.held = [_mark(f"n{i}", i) for i in range(12)] + [_mark("hidden", 99)]
    news = await ExploreService(graph, None).whats_new(READER, marks)  # type: ignore[arg-type]
    assert len(news.marked) == 10 and news.marked_total == 12
    assert news.marked[0].node.id == "n11"
