"""The graph stand-in the recipe tests load into (`MergingGraph`) merges a repeated pair as the
real adapter does (rule 15: a fake does what the real store does). Both go through the shared rule
`schemas.merge`; this test writes the same links through the stand-in and through the adapter over
its in-memory store and compares what each holds. What a mistake would do, and the case that catches
it:

- the stand-in keeping the first write as it did, so a golden test sees one occurrence where the real
  store holds five (`test_the_stand_in_holds_what_the_adapter_holds`);
- a merge that outlives a rollback (`test_a_rollback_puts_back_what_a_merge_replaced`);
- a merge across audiences (`test_a_write_of_another_audience_is_a_link_of_its_own`)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from ontology.loader import load_default_ontology
from schemas.domain import Interval
from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter, make_edge
from tests.ingest.recipe_test_support import MergingGraph

T0 = datetime(2026, 1, 1, tzinfo=UTC)
ONTOLOGY = load_default_ontology()


def _writes() -> list:  # type: ignore[type-arg]
    def span(n: int, start: int, end: int | None, **changes: object):  # type: ignore[no-untyped-def]
        return make_edge("a", "b", n).model_copy(
            update={
                "interval": Interval(
                    valid_from=T0 + timedelta(days=start),
                    valid_to=None if end is None else T0 + timedelta(days=end),
                ),
                **changes,
            }
        )

    return [
        span(1, 5, 6, occurrences=2, properties={"amount": 1.0}),
        span(2, 1, 9, properties={"amount": 2.0}),
        span(3, 3, None, occurrences=4, properties={"amount": 3.0}),
    ]


async def _into_stand_in(writes: list) -> MergingGraph:  # type: ignore[type-arg]
    graph = MergingGraph(ONTOLOGY)
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([], tx)
    for write in writes:
        graph._type_of = lambda _id: "Endpoint"  # type: ignore[method-assign]
        await graph.upsert_edges([write], tx)
    await graph.commit_transaction(tx)
    return graph


def test_the_stand_in_holds_what_the_adapter_holds() -> None:
    writes = _writes()
    store = CountingStore()
    adapter = make_adapter(store)
    for write in writes:
        asyncio.run(adapter.upsert_edges([write], "tx"))
    (stored,) = store.links
    stand_in = asyncio.run(_into_stand_in(writes))
    (held,) = [e for e in stand_in.committed_edges if e.type == "TRANSACTED"]
    assert held.occurrences == stored["occurrences"] == 7
    assert held.interval is not None
    assert held.interval.model_dump(mode="json") == stored["interval"]
    assert held.interval.valid_to is None, "an open write among closed ones leaves it open"
    assert held.properties == stored["properties"] == {"amount": 3.0}
    assert [(s.document_id, s.locator) for s in held.provenance.sources] == [
        (s["document_id"], s["locator"]) for s in stored["provenance"]["sources"]
    ]
    assert held.id == stored["id"] == "edge-1"


def test_a_rollback_puts_back_what_a_merge_replaced() -> None:
    async def go() -> tuple[int, int]:
        graph = MergingGraph(ONTOLOGY)
        graph._type_of = lambda _id: "Endpoint"  # type: ignore[method-assign]
        first, second = _writes()[:2]
        tx = await graph.begin_transaction()
        await graph.upsert_edges([first], tx)
        await graph.commit_transaction(tx)
        tx = await graph.begin_transaction()
        await graph.upsert_edges([second], tx)
        merged = graph.committed_edges[0].occurrences
        await graph.rollback_transaction(tx)
        return merged, graph.committed_edges[0].occurrences

    during, after = asyncio.run(go())
    assert during == 3 and after == 2


def test_a_write_of_another_audience_is_a_link_of_its_own() -> None:
    async def go() -> int:
        graph = MergingGraph(ONTOLOGY)
        graph._type_of = lambda _id: "Endpoint"  # type: ignore[method-assign]
        plain = make_edge("a", "b", 1)
        secret = make_edge("a", "b", 2)
        secret = secret.model_copy(
            update={"handling": secret.handling.model_copy(update={"classification": "SECRET"})}
        )
        tx = await graph.begin_transaction()
        await graph.upsert_edges([plain], tx)
        await graph.upsert_edges([secret], tx)
        await graph.commit_transaction(tx)
        return len(graph.committed_edges)

    assert asyncio.run(go()) == 2


# --- the adapter checks every write before it looks for a link to merge into, and chooses
# deterministically among the links a pair holds (ADR-102 Amendment 4) ------------------------------

import pytest  # noqa: E402
from ontology.errors import OntologyError  # noqa: E402


def test_a_later_write_the_adapter_would_refuse_is_refused_before_any_merge() -> None:
    """The adapter validates the type, the properties and the ends of every write first, then looks
    for the link to merge into. A second write of a repeated pair with an undeclared property is
    refused by the adapter, so it is by the stand-in, and the link it would have merged into is
    left as it was."""
    first = make_edge("a", "b", 1)
    bad = make_edge("a", "b", 2).model_copy(update={"properties": {"not_declared": 1}})

    store = CountingStore()
    adapter = make_adapter(store)
    asyncio.run(adapter.upsert_edges([first], "tx"))
    with pytest.raises(OntologyError):
        asyncio.run(adapter.upsert_edges([bad], "tx"))

    async def go() -> int:
        graph = MergingGraph(ONTOLOGY)
        graph._type_of = lambda _id: "Endpoint"  # type: ignore[method-assign]
        tx = await graph.begin_transaction()
        await graph.upsert_edges([first], tx)
        with pytest.raises(OntologyError):
            await graph.upsert_edges([bad], tx)
        return graph.open_edges[0].occurrences

    assert asyncio.run(go()) == 1, "the refused write added no occurrence"


def test_a_pair_holding_two_links_of_one_audience_is_merged_into_the_one_the_adapter_picks() -> None:
    """The higher revision, then the later creation, then the greater id: never the first held."""
    older = make_edge("a", "b", 1)
    newer = make_edge("a", "b", 2).model_copy(update={"created_at": older.created_at + timedelta(days=1)})
    greater = make_edge("a", "b", 3).model_copy(update={"id": "edge-zz", "created_at": older.created_at})

    async def merged_into(held: list, revisions: dict[str, int]) -> str:  # type: ignore[type-arg]
        graph = MergingGraph(ONTOLOGY)
        graph._type_of = lambda _id: "Endpoint"  # type: ignore[method-assign]
        graph.committed_edges.extend(held)
        graph._revision.update(revisions)
        tx = await graph.begin_transaction()
        (chosen,) = await graph.upsert_edges([make_edge("a", "b", 9)], tx)
        return chosen

    # The higher revision wins over a later creation.
    assert asyncio.run(merged_into([older, newer], {older.id: 3, newer.id: 1})) == older.id
    # At one revision, the later creation.
    assert asyncio.run(merged_into([older, newer], {})) == newer.id
    # At one revision and one creation, the greater id.
    twin = older.model_copy(update={"id": "edge-zz"})
    assert asyncio.run(merged_into([older, twin], {})) == "edge-zz"
    assert greater.id == "edge-zz"
