"""The graph stand-in the recipe tests load into (`MergingGraph`) merges a repeated pair as the
real adapter does (rule 15: a fake does what the real store does). Both go through the shared rule
`schemas.merge`; this test writes the same links through the stand-in and through the adapter over
its in-memory store and compares what each holds. What a mistake would do, and the case that catches
it:

- the stand-in keeping the first write as it did, so a golden test sees one occurrence where the real
  store holds five (`test_the_stand_in_holds_what_the_adapter_holds`);
- a merge that outlives a rollback (`test_a_rollback_puts_back_what_a_merge_replaced`);
- a merge across audiences (`test_a_write_of_another_audience_is_a_link_of_its_own`);
- a later write the adapter would refuse being merged before it is refused
  (`test_a_later_write_the_adapter_would_refuse_is_refused_before_any_merge`);
- the pair's links of one audience merged into the first held and not the one the adapter picks
  (`test_a_pair_holding_two_links_of_one_audience_is_merged_into_the_one_the_adapter_picks`);
- a node that is reverted and not superseded still named as existing, or one that is also
  superseded left out, unlike the adapter's `render_live_node_ids_sql`
  (`test_a_reverted_node_is_absent_unless_it_is_also_superseded`);
- the recipe tests' replay of a link's marking assuming the first write wins, where the store keeps
  a link of another audience apart (`test_the_marking_replay_models_the_links_the_stand_in_stores`)."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

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


def test_a_pair_holding_two_links_of_one_audience_is_merged_into_the_one_the_adapter_picks() -> (
    None
):
    """The higher revision, then the later creation, then the greater id: never the first held."""
    older = make_edge("a", "b", 1)
    newer = make_edge("a", "b", 2).model_copy(
        update={"created_at": older.created_at + timedelta(days=1)}
    )
    greater = make_edge("a", "b", 3).model_copy(
        update={"id": "edge-zz", "created_at": older.created_at}
    )

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


class _NodeStore:
    """The part of the store `GraphArcadeDBAdapter.existing_node_ids` asks: the stored types with a
    unique `id` index, and the SQL `render_live_node_ids_sql` renders, answered by evaluating the
    rendered text itself (not by being told its meaning): the `WHERE` clause is an `OR` of atoms
    over `reverted` and `superseded_by`, each judged as SQL does, a `NULL` comparison being unknown
    and so not a match. Any other text is refused, as the real store would not answer it as this
    does."""

    def __init__(self, rows: dict[str, tuple[bool | None, str | None]]) -> None:
        self.rows = rows
        self.asked: list[str] = []

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        if command == "SELECT name, type, indexes FROM schema:types":
            return [
                {
                    "name": "Endpoint",
                    "type": "vertex",
                    "indexes": [{"unique": True, "properties": ["id"]}],
                }
            ]
        match = re.fullmatch(
            r"SELECT id FROM `Endpoint` WHERE id IN :ids(?: AND \((?P<clause>[^()]+)\))?", command
        )
        if match is None or params is None:
            raise AssertionError(f"unexpected SQL: {command}")
        self.asked.append(command)
        clause = match.group("clause")
        atoms = [] if clause is None else clause.split(" OR ")
        known = {
            "reverted = false": lambda reverted, sup: reverted is not None and reverted is False,
            "reverted IS NULL": lambda reverted, sup: reverted is None,
            "superseded_by IS NOT NULL": lambda reverted, sup: sup is not None,
        }
        for atom in atoms:
            if atom not in known:
                raise AssertionError(f"a clause this store cannot judge: {atom!r}")
        return [
            {"id": node_id}
            for node_id in params["ids"]
            if node_id in self.rows
            and (not atoms or any(known[a](*self.rows[node_id]) for a in atoms))
        ]


def test_a_reverted_node_is_absent_unless_it_is_also_superseded() -> None:
    """`existing_node_ids` as the adapter's, which asks `render_live_node_ids_sql` (ADR-127
    Amendment 8): a node that is reverted and not superseded is absent (a write onto it is a fresh
    create); a node both reverted and superseded is still named, because a write to it still merges.
    The stand-in is compared with the adapter over the same stored states, as the cases above are,
    and not with sets written by hand."""
    #: id -> (reverted, superseded_by) as the store holds a vertex; a never-reverted node holds
    #: `NULL` or `false`.
    states: dict[str, tuple[bool | None, str | None]] = {
        "live-null": (None, None),
        "live-false": (False, None),
        "reverted": (True, None),
        "reverted-and-superseded": (True, "other"),
        "superseded": (False, "other"),
        "superseded-null": (None, "other"),
    }
    ids = [*states, "never-written"]

    async def from_adapter() -> set[str]:
        store = _NodeStore(states)
        adapter = make_adapter(store)  # type: ignore[arg-type]
        found = await adapter.existing_node_ids(ids)
        assert store.asked, "the adapter asked the store"
        return found

    async def from_stand_in() -> set[str]:
        graph = MergingGraph(ONTOLOGY)
        graph.committed_nodes = [SimpleNamespace(id=i) for i in states]  # type: ignore[list-item]
        await graph.revert_elements([i for i, (r, _) in states.items() if r], [], None)
        graph.superseded.update(i for i, (_, s) in states.items() if s)
        return await graph.existing_node_ids(ids)

    real = asyncio.run(from_adapter())
    assert 0 < len(real) < len(states), "the adapter's answer tells a reverted node from a live one"
    assert asyncio.run(from_stand_in()) == real


def test_the_marking_replay_models_the_links_the_stand_in_stores() -> None:
    """The recipe tests' expectation for a link's marking (`pid_golden_support.link_markings`, which
    `replay` uses) must be what the stand-in stores for the same writes, in one load or across loads:
    a write of the same audience merges and the first write's units stay, so another unit under a
    permitted code does not make a second link; a write of another classification, or of another
    unit under a restricted code, is a link of its own. Not first-write-wins."""
    from tests.ingest.pid_golden_support import link_markings, marking

    local = ("OFFICIAL", "P", None, None, "fenwick-moor-security", "fenwick-moor-security")
    regional = ("OFFICIAL", "P", None, None, "regional-intel-unit", "regional-intel-unit")
    secret = ("SECRET", "P", None, None, "regional-intel-unit", "regional-intel-unit")
    restricted_local = (
        "OFFICIAL",
        "R",
        None,
        None,
        "fenwick-moor-security",
        "fenwick-moor-security",
    )
    restricted_regional = (
        "OFFICIAL",
        "R",
        None,
        None,
        "regional-intel-unit",
        "regional-intel-unit",
    )
    cases = [
        [local, regional],  # one audience: one link, at the first write's units
        [regional, local],
        [local, secret, regional],  # another classification is a link of its own
        [local, restricted_local, restricted_regional],  # a restricted code splits by unit
        [restricted_regional, regional, restricted_local, local],
    ]

    def write(n: int, mark: tuple[object, ...]):  # type: ignore[no-untyped-def]
        edge = make_edge("a", "b", n)
        return edge.model_copy(
            update={
                "handling": edge.handling.model_copy(
                    update=dict(
                        zip(
                            (
                                "classification",
                                "handling_code",
                                "action_code",
                                "sanitisation_code",
                                "originator",
                                "owning_unit",
                            ),
                            mark,
                            strict=True,
                        )
                    )
                )
            }
        )

    async def stored(marks: list[tuple[object, ...]]) -> list[tuple[object, ...]]:
        graph = MergingGraph(ONTOLOGY)
        graph._type_of = lambda _id: "Endpoint"  # type: ignore[method-assign]
        for n, mark in enumerate(marks, start=1):
            tx = await graph.begin_transaction()
            await graph.upsert_edges([write(n, mark)], tx)
            await graph.commit_transaction(tx)
        return sorted((marking(e.handling) for e in graph.committed_edges), key=repr)

    for marks in cases:
        assert asyncio.run(stored(marks)) == sorted(link_markings(marks), key=repr), marks
    assert len(link_markings([local, secret])) == 2 and len(link_markings([local, regional])) == 1
