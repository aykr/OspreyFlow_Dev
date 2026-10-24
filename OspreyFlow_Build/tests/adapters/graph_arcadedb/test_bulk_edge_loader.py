"""`BulkEdgeLoader`'s logic, driven through an in-memory transport (ADR-058).

The transport below answers from the edges it holds and **refuses what the real store refuses**
(rule 15): a write outside an open transaction, a write to a vertex that does not exist, an edge
with a label no type declares, a lookup bigger than the batch bound. It also counts every call, so
the tests can say the load costs a handful of store calls and not one per edge, which is the whole
point of the path. What it cannot prove is that the Gremlin `GremlinBulkTransport` sends runs on
ArcadeDB; that is the spike's and the conformance suite's job, not this file's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from adapters.graph_arcadedb.bulk import LOOKUP_BATCH, BulkEdgeLoader
from adapters.graph_arcadedb.naming import physical_type_name
from ontology.errors import OntologyError
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite
from tests.adapters.graph_arcadedb.edge_store import make_edge

SCHEMA = load_default_ontology()
ENDPOINT = physical_type_name("Endpoint")
PERSON = physical_type_name("Person")
LABEL = physical_type_name("TRANSACTED")
KNOWN_LABELS = {LABEL, physical_type_name("ASSOCIATE_OF"), physical_type_name("USES")}


class MemoryTransport:
    def __init__(self, vertices: Mapping[str, str]) -> None:
        self.vertices = dict(vertices)
        # {label, s, t, occurrences, reverted}, and `superseded_by` where a link was replaced
        self.stored: list[dict[str, Any]] = []
        self.calls: list[str] = []
        self.written: list[dict[str, Any]] = []  # the rows, as sent
        self.committed: list[str] = []
        self.rolled_back: list[str] = []
        self.fail_on_chunk: int | None = None
        self._open: set[str] = set()
        self._chunks = 0

    def _bounded(self, ids: Sequence[Any]) -> None:
        if len(ids) > LOOKUP_BATCH:
            raise AssertionError(f"a lookup of {len(ids)} ids exceeds the batch bound")

    async def vertex_labels(self, ids: Sequence[str]) -> dict[str, str]:
        self.calls.append("vertex_labels")
        self._bounded(ids)
        return {i: self.vertices[i] for i in ids if i in self.vertices}

    async def edge_type_is_empty(self, label: str) -> bool:
        self.calls.append("edge_type_is_empty")
        return not any(e["label"] == label for e in self.stored)

    async def stored_pairs(
        self, label: str, pairs: Sequence[tuple[str, str]], *, directed: bool
    ) -> set[tuple[str, str]]:
        self.calls.append("stored_pairs")
        self._bounded(pairs)
        live = {(e["s"], e["t"]) for e in self.stored if e["label"] == label and not e["reverted"]}
        wanted = set(pairs) if directed else set(pairs) | {(t, s) for s, t in pairs}
        return live & wanted

    @staticmethod
    def _counts(e: Mapping[str, Any], label: str) -> bool:
        """Whether a stored link is in the corpus counts: of this type, not reverted, not
        superseded (ADR-120 Amendment 5, decision 1; every read leaves out both)."""
        return e["label"] == label and not e["reverted"] and not e.get("superseded_by")

    async def corpus_total(self, label: str) -> int:
        self.calls.append("corpus_total")
        return sum(e["occurrences"] for e in self.stored if self._counts(e, label))

    async def degrees(self, label: str, ids: Sequence[str]) -> dict[str, int]:
        self.calls.append("degrees")
        self._bounded(ids)
        live = [e for e in self.stored if self._counts(e, label)]
        # `bothE()` reads a link from a node to itself back twice, so it counts twice here.
        return {
            i: sum(e["occurrences"] * ((e["s"] == i) + (e["t"] == i)) for e in live) for i in ids
        }

    async def begin(self) -> str:
        self.calls.append("begin")
        tx = f"tx-{len(self.calls)}"
        self._open.add(tx)
        return tx

    async def commit(self, tx: str) -> None:
        self.calls.append("commit")
        self._open.remove(tx)
        self.committed.append(tx)

    async def rollback(self, tx: str) -> None:
        self.calls.append("rollback")
        self._open.discard(tx)
        self.rolled_back.append(tx)

    async def write_chunk(self, label: str, rows: Sequence[Mapping[str, Any]], tx: str) -> None:
        self.calls.append("write_chunk")
        if tx not in self._open:
            raise AssertionError("a write outside an open transaction")
        if label not in KNOWN_LABELS:
            raise AssertionError(f"an edge label no type declares: {label}")
        self._chunks += 1
        if self.fail_on_chunk == self._chunks:
            raise RuntimeError("the store dropped the connection")
        for row in rows:
            if row["s"] not in self.vertices or row["t"] not in self.vertices:
                raise AssertionError("an edge written to a vertex that does not exist")
            self.written.append(dict(row))
            self.stored.append(
                {
                    "label": label,
                    "s": row["s"],
                    "t": row["t"],
                    "occurrences": row["p"]["occurrences"],
                    "reverted": False,
                }
            )


def _store(*ids: str, label: str = ENDPOINT) -> MemoryTransport:
    return MemoryTransport({i: label for i in ids})


def _load(transport: MemoryTransport, edges: list[EdgeWrite], **kwargs: Any) -> Any:
    loader = BulkEdgeLoader(transport, handling_scheme=load_uk_le_scheme())
    return asyncio.run(loader.load(SCHEMA, edges, **kwargs))


def _edge(source: str, target: str, n: int, occurrences: int = 1) -> EdgeWrite:
    return make_edge(source, target, n).model_copy(update={"occurrences": occurrences})


# --- validation parity: nothing is written for a bad batch -------------------


@pytest.mark.parametrize("fault", ["unknown_type", "bad_property", "missing_endpoint", "bad_ends"])
def test_a_bad_edge_raises_before_any_write_or_transaction(fault: str) -> None:
    """Catches the loader validating as it goes, or not at all: a batch with one bad edge must
    raise `OntologyError` before a transaction is opened, with the good edges unwritten."""
    transport = _store("a", "b", "c")
    good = [_edge("a", "b", 1), _edge("b", "c", 2)]
    bad = {
        "unknown_type": _edge("a", "c", 3).model_copy(update={"type": "NOT_A_TYPE"}),
        "bad_property": _edge("a", "c", 3).model_copy(update={"properties": {"nope": 1}}),
        "missing_endpoint": _edge("a", "ghost", 3),
        "bad_ends": _edge("a", "c", 3).model_copy(update={"type": "USES"}),  # Person to Endpoint
    }[fault]
    with pytest.raises(OntologyError):
        _load(transport, [*good, bad])
    assert "begin" not in transport.calls and transport.written == []


def test_an_empty_call_does_nothing() -> None:
    transport = _store("a")
    result = _load(transport, [])
    assert result.written == [] and result.received == 0 and transport.calls == []


def test_a_pair_loaded_twice_keeps_the_higher_handling() -> None:
    """ADR-102: within one load, a pair written SECRET then OFFICIAL is written once, SECRET."""
    transport = _store("a", "b")
    first = _edge("a", "b", 1)
    secret = first.model_copy(
        update={"handling": first.handling.model_copy(update={"classification": "SECRET"})}
    )
    _load(transport, [secret, _edge("a", "b", 2)])
    (row,) = transport.written
    assert row["p"]["handling_classification"] == "SECRET"
    assert row["p"]["handling"]["classification"] == "SECRET"


# --- the cost: a handful of store calls, not one per edge --------------------


def test_a_thousand_edges_cost_a_handful_of_store_calls() -> None:
    """Catches any per-edge store call creeping into the load: 1,200 distinct edges into an empty
    type must be written in three chunks with a few batched lookups, not 1,200 round trips."""
    ids = [f"n{i}" for i in range(1201)]
    transport = _store(*ids)
    edges = [_edge(ids[i], ids[i + 1], i) for i in range(1200)]
    result = _load(transport, edges, chunk_size=500)

    assert result.chunks == 3 and len(result.written) == 1200 and result.collisions == []
    assert len(transport.calls) <= 20, transport.calls
    assert transport.calls.count("write_chunk") == 3
    assert "corpus_total" not in transport.calls and "stored_pairs" not in transport.calls


# --- weights at the end of the load ------------------------------------------


def _components(transport: MemoryTransport) -> dict[tuple[str, str], tuple[int, int, int]]:
    return {
        (r["s"], r["t"]): (
            r["p"]["weight_components"]["corpus_source_degree"],
            r["p"]["weight_components"]["corpus_target_degree"],
            r["p"]["weight_components"]["corpus_total_occurrences"],
        )
        for r in transport.written
    }


@pytest.mark.parametrize("chunk", [1, 2, 500])
def test_weights_are_the_end_of_load_corpus_whatever_the_chunking(chunk: int) -> None:
    """Catches a weight computed against the corpus as it stood when an edge's chunk was written:
    every edge carries the whole call's total, and each end's degree over the whole call."""
    transport = _store("a", "b", "c", "d")
    _load(
        transport,
        [_edge("a", "b", 1, 1), _edge("a", "c", 2, 2), _edge("d", "b", 3, 4)],
        chunk_size=chunk,
    )
    assert _components(transport) == {
        ("a", "b"): (3, 5, 7),
        ("a", "c"): (3, 2, 7),
        ("d", "b"): (4, 5, 7),
    }


def test_what_is_already_stored_is_part_of_the_corpus() -> None:
    """Catches the load's weights ignoring existing edges: the total and the degree of a node the
    load touches include what was there before."""
    transport = _store("a", "b", "c")
    transport.stored.append(
        {"label": LABEL, "s": "a", "t": "b", "occurrences": 10, "reverted": False}
    )
    _load(transport, [_edge("a", "c", 1, 2)])
    assert _components(transport) == {("a", "c"): (12, 2, 12)}


# --- aggregating, and the pair that already exists ---------------------------


def test_repeated_pairs_are_one_written_edge_and_counted_as_received() -> None:
    transport = _store("a", "b")
    result = _load(transport, [_edge("a", "b", 1, 2), _edge("a", "b", 2, 5), _edge("a", "b", 3)])
    assert result.received == 3 and len(result.written) == 1
    (row,) = transport.written
    assert row["p"]["occurrences"] == 8 and row["p"]["audit"]["revision"] == 3


def test_a_stored_pair_is_handed_back_and_not_written() -> None:
    """Catches a stored pair being written again, merged or dropped: it comes back in `collisions`,
    nothing is written for it, and it adds nothing to the weights of what is written."""
    transport = _store("a", "b", "c", "d")
    transport.stored.append(
        {"label": LABEL, "s": "a", "t": "b", "occurrences": 3, "reverted": False}
    )
    clash, fresh = _edge("a", "b", 1, 2), _edge("c", "d", 2, 1)
    result = _load(transport, [clash, fresh])
    assert result.written == [fresh.id] and [c.id for c in result.collisions] == [clash.id]
    assert [(r["s"], r["t"]) for r in transport.written] == [("c", "d")]
    # the stored 3 are the baseline; the handed-back 2 are not in this load's total
    assert _components(transport) == {("c", "d"): (1, 1, 4)}


def test_an_undirected_pair_stored_the_other_way_round_is_a_collision() -> None:
    """Catches an undirected edge written twice because it was stored b to a and loaded a to b."""
    transport = _store("a", "b", label=PERSON)
    label = physical_type_name("ASSOCIATE_OF")
    transport.stored.append(
        {"label": label, "s": "b", "t": "a", "occurrences": 1, "reverted": False}
    )
    edge = make_edge("a", "b", 1).model_copy(update={"type": "ASSOCIATE_OF"})
    result = _load(transport, [edge])
    assert result.written == [] and [c.id for c in result.collisions] == [edge.id]


# --- chunks and failure ------------------------------------------------------


def test_each_chunk_is_its_own_transaction_and_progress_follows() -> None:
    transport = _store("a", "b", "c", "d", "e")
    seen: list[tuple[int, int]] = []
    edges = [_edge("abcde"[i], "abcde"[i + 1], i) for i in range(4)]
    _load(transport, edges, chunk_size=2, progress=lambda d, t: seen.append((d, t)))
    assert transport.calls.count("begin") == 2 == transport.calls.count("commit")
    assert seen == [(2, 4), (4, 4)]


def test_a_failed_chunk_is_rolled_back_and_the_earlier_ones_stay() -> None:
    """Catches a failure leaving a transaction open, or hiding the error: the failing chunk rolls
    back, the committed chunk before it stays (the caller reverts by load_id, ADR-058 D6), and the
    error reaches the caller."""
    transport = _store("a", "b", "c", "d", "e")
    transport.fail_on_chunk = 2
    edges = [_edge("abcde"[i], "abcde"[i + 1], i) for i in range(4)]
    with pytest.raises(RuntimeError, match="dropped the connection"):
        _load(transport, edges, chunk_size=2)
    assert len(transport.committed) == 1 and len(transport.rolled_back) == 1
    assert len(transport.written) == 2


def test_the_row_carries_what_upsert_would_store_for_a_single_edge() -> None:
    """Catches the bulk path storing a single edge differently from `upsert_edges` (one and many
    must give the same stored result): the same properties, with weight and components computed
    from the same counts."""
    from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter

    edge = _edge("a", "b", 1, 3)
    transport = _store("a", "b")
    _load(transport, [edge])
    (row,) = transport.written

    store = CountingStore()
    asyncio.run(make_adapter(store).upsert_edges([edge], "tx"))
    upserted = store.edges[("a", "b")]

    for key in ("id", "source", "target", "occurrences", "weight", "provenance", "handling"):
        assert row["p"][key] == upserted[key], key
    bulk_components = {k: v for k, v in row["p"]["weight_components"].items() if k != "computed_at"}
    upsert_components = {
        k: v for k, v in upserted["weight_components"].items() if k != "computed_at"
    }
    assert bulk_components == upsert_components
    assert row["p"]["audit"]["revision"] == upserted["audit"]["revision"] == 1


@pytest.mark.parametrize("weights_version", [1, 2, 3])
def test_a_self_loop_is_stored_the_same_by_the_bulk_path_and_an_upsert(
    weights_version: int,
) -> None:
    """ADR-120 Amendment 4. Catches a path that counts a self-loop's occurrences once in its
    node's degree (the store reads it back twice through `bothE`), or weighs it with a
    mutual-information term: the same loop, at a node with other occurrences, must store the same
    components and the same weight by either path. Both counts are 7 + 2 x 3 = 13 at the node.

    ADR-123: the term is zero from version 2, so only version 1 (pinned by index, not "latest")
    can show a path that weighs the loop with it. The version 1 case proves that: the loop's
    weight with the term left in is another number, so a path that did that would fail here."""
    from adapters.graph_arcadedb.weight import compute_weight
    from ontology.weights import load_weight_history
    from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter

    rules = load_weight_history()[weights_version - 1]
    assert rules.version == weights_version

    other, loop = _edge("a", "b", 1, 7), _edge("a", "a", 2, 3)
    transport = _store("a", "b")
    asyncio.run(
        BulkEdgeLoader(transport, rules, handling_scheme=load_uk_le_scheme()).load(
            SCHEMA, [other, loop]
        )
    )
    bulk = {row["p"]["id"]: row["p"] for row in transport.written}["edge-2"]

    store = CountingStore()
    graph = make_adapter(store, rules)
    asyncio.run(graph.upsert_edges([other], "tx"))
    asyncio.run(graph.upsert_edges([loop], "tx"))
    upserted = store.edges[("a", "a")]

    for stored in (bulk, upserted):
        assert stored["weight_components"]["corpus_source_degree"] == 13
        assert stored["weight_components"]["corpus_target_degree"] == 13
        assert stored["weight_components"]["corpus_total_occurrences"] == 10
    bulk_components = {k: v for k, v in bulk["weight_components"].items() if k != "computed_at"}
    upsert_components = {
        k: v for k, v in upserted["weight_components"].items() if k != "computed_at"
    }
    assert bulk_components == upsert_components
    assert bulk["weight"] == pytest.approx(upserted["weight"], abs=1e-9)

    from schemas.domain import WeightComponents

    components = WeightComponents.model_validate(upserted["weight_components"])
    with_the_term = compute_weight(
        components,
        edge_type="TRANSACTED",
        valid_to=None,
        now=components.computed_at,
        rules=rules,
        self_loop=False,
    )
    if weights_version == 1:
        assert abs(with_the_term - upserted["weight"]) > 1e-3, "the case must be one the term moves"
    else:
        assert with_the_term == upserted["weight"]


def test_the_memory_transport_counts_a_self_loop_twice_like_bothE() -> None:
    """The real `GremlinBulkTransport.degrees` reads a node's links with `bothE`, which returns a
    link from a node to itself twice. Catches this stand-in counting it once, which would let a
    loader that adds a self-loop's occurrences once pass every test that uses it."""
    transport = _store("a", "b")
    transport.stored += [
        {"label": LABEL, "s": "a", "t": "b", "occurrences": 7, "reverted": False},
        {"label": LABEL, "s": "a", "t": "a", "occurrences": 3, "reverted": False},
        {"label": LABEL, "s": "a", "t": "a", "occurrences": 50, "reverted": True},
    ]
    assert asyncio.run(transport.degrees(LABEL, ["a", "b"])) == {"a": 13, "b": 7}


def test_a_second_write_of_the_same_self_loop_counts_both_writes_twice() -> None:
    """ADR-120 Amendment 4. Catches an upsert that counts a stored self-loop twice but a new write
    of it once (or the reverse): with 7 at the node from another link, a self-loop written at 3
    and again at 2 leaves 7 + 2 x 3 + 2 x 2 = 17 in its node's degree, the pair at 5, and the
    type's total at 12."""
    from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter

    store = CountingStore()
    graph = make_adapter(store)
    asyncio.run(graph.upsert_edges([_edge("a", "b", 1, 7)], "tx"))
    asyncio.run(graph.upsert_edges([_edge("a", "a", 2, 3)], "tx"))
    asyncio.run(graph.upsert_edges([_edge("a", "a", 3, 2)], "tx"))

    components = store.edges[("a", "a")]["weight_components"]
    assert components["occurrences"] == components["corpus_pair_count"] == 5
    assert components["corpus_source_degree"] == components["corpus_target_degree"] == 17
    assert components["corpus_total_occurrences"] == 12


def test_the_memory_transport_leaves_a_superseded_link_out_of_the_counts() -> None:
    """ADR-120 Amendment 5, decision 1: the real degree and total queries leave out a link with
    `superseded_by`, as every read does. Catches this stand-in filtering only `reverted`, which
    would let a loader that counted a superseded link pass every test that uses it (rule 15: the
    fake refuses what the store refuses). Reverted and superseded are left out alike."""
    transport = _store("a", "b")
    transport.stored += [
        {"label": LABEL, "s": "a", "t": "b", "occurrences": 2, "reverted": False},
        {
            "label": LABEL,
            "s": "a",
            "t": "b",
            "occurrences": 5,
            "reverted": False,
            "superseded_by": "edge-2",
        },
        {"label": LABEL, "s": "a", "t": "b", "occurrences": 50, "reverted": True},
    ]
    assert asyncio.run(transport.degrees(LABEL, ["a", "b"])) == {"a": 2, "b": 2}
    assert asyncio.run(transport.corpus_total(LABEL)) == 2


def test_a_superseded_link_is_not_in_the_corpus_a_bulk_load_weighs_against() -> None:
    """ADR-120 Amendment 5, decision 1. Catches the bulk path weighing a new link against counts
    that include a link already replaced: a link a -> b stored at 5 and superseded by one at 2,
    then a -> c loaded at 4. The loaded link's degree at `a` is the successor's 2 plus its own 4,
    and the type's total is 2 + 4, not 5 + 2 + 4."""
    transport = _store("a", "b", "c")
    transport.stored += [
        {
            "label": LABEL,
            "s": "a",
            "t": "b",
            "occurrences": 5,
            "reverted": False,
            "superseded_by": "edge-2",
        },
        {"label": LABEL, "s": "a", "t": "b", "occurrences": 2, "reverted": False},
    ]
    _load(transport, [_edge("a", "c", 1, 4)])
    assert _components(transport) == {("a", "c"): (6, 4, 6)}


class _RecordingClient:
    """Stands in for `ArcadeDBClient` and records the Gremlin it is sent."""

    def __init__(self) -> None:
        self.scripts: list[str] = []

    async def gremlin(
        self, script: str, *, params: Mapping[str, Any] | None = None, **_: Any
    ) -> list[Any]:
        self.scripts.append(script)
        return []


def test_the_gremlin_the_bulk_transport_sends_leaves_out_superseded_links() -> None:
    """ADR-120 Amendment 5, decision 1. Catches `GremlinBulkTransport.degrees` or `corpus_total`
    filtering only `reverted`: each script the transport sends for a count must exclude a link
    with `superseded_by` too, as the adapter's own reads do (`hasNot("superseded_by")`). The
    in-memory transport above cannot show this; it models the store, not the script."""
    from adapters.graph_arcadedb.bulk import GremlinBulkTransport

    client = _RecordingClient()
    transport = GremlinBulkTransport(client)  # type: ignore[arg-type]
    asyncio.run(transport.degrees(LABEL, ["a"]))
    asyncio.run(transport.corpus_total(LABEL))

    assert len(client.scripts) == 2
    for script in client.scripts:
        assert '.has("reverted", false)' in script, script
        assert 'hasNot("superseded_by")' in script, script


def test_the_gremlin_the_upsert_path_sends_for_counts_leaves_out_superseded_links() -> None:
    """ADR-120 Amendment 5, decision 1. Catches `upsert_edges` weighing a link against a degree
    or total query that filters only `reverted`: every query the write sends that sums occurrences
    must also exclude `superseded_by`. This tests `upsert_edges` only; `supersede_edge`'s own
    weighing (it marks the old link before weighing the replacement) is proven by the conformance
    case `test_a_superseded_link_does_not_count_in_the_corpus`, which needs a live store."""
    from tests.adapters.graph_arcadedb.edge_store import CountingStore, make_adapter

    store = CountingStore()
    graph = make_adapter(store)
    asyncio.run(graph.upsert_edges([_edge("a", "b", 1, 3)], "tx"))

    sums = [q for q in store.queries if ".sum()" in q]
    assert len(sums) >= 3, "expected a degree at each end and the type's total"
    for query in sums:
        assert 'hasNot("superseded_by")' in query, query


def test_the_counting_store_leaves_a_superseded_link_out_only_when_the_query_asks() -> None:
    """ADR-120 Amendment 5, decision 1. Catches the in-memory store behind the upsert-path tests
    counting a link with `superseded_by` whatever the query says: a query with
    `hasNot("superseded_by")` must not see it, one without must (so a production query that forgot
    the step still shows the superseded link's occurrences, as the real store would)."""
    from tests.adapters.graph_arcadedb.edge_store import CountingStore

    store = CountingStore()
    store.edges[("a", "b")] = {"id": "e1", "occurrences": 5, "superseded_by": "e2"}
    store.edges[("a", "c")] = {"id": "e3", "occurrences": 2}
    base_degree = "g.V().has(\"id\",'a').bothE('x').has(\"reverted\",false)"
    base_total = "g.V().outE('x').has(\"reverted\",false)"
    tail = '.values("occurrences").sum()'
    excluded = '.hasNot("superseded_by")'

    async def ask(query: str) -> int:
        return int((await store.gremlin(query))[0]["result"])

    assert asyncio.run(ask(base_degree + excluded + tail)) == 2
    assert asyncio.run(ask(base_degree + tail)) == 7
    assert asyncio.run(ask(base_total + excluded + tail)) == 2
    assert asyncio.run(ask(base_total + tail)) == 7


# --- the adapter declares the capability and keeps its own refusals ----------


def _adapter(transport: MemoryTransport) -> Any:
    from adapters.graph_arcadedb import adapter as adapter_module
    from ontology.handling import load_uk_le_scheme

    return adapter_module.GraphArcadeDBAdapter(
        None,  # type: ignore[arg-type]  # the bulk path goes through the transport only
        load_uk_le_scheme(),
        bulk_transport=transport,
    )


def test_the_adapter_declares_the_bulk_capability_through_the_port() -> None:
    """Catches the engine's capability check (`isinstance(adapter, BulkGraphLoader)`) failing for
    an adapter that has the method, or passing for one that does not."""
    from ports.graph import BulkGraphLoader

    assert isinstance(_adapter(_store()), BulkGraphLoader)
    assert not isinstance(object(), BulkGraphLoader)


def test_the_adapter_refuses_a_bulk_load_until_a_schema_is_applied() -> None:
    """Catches the bulk path skipping the refusal `upsert_edges` has (rule 15: a double must refuse
    what the real store refuses; the adapter refuses every write until `apply_schema` has run)."""
    transport = _store("a", "b")
    graph = _adapter(transport)
    with pytest.raises(OntologyError, match="apply_schema"):
        asyncio.run(graph.bulk_load_edges([_edge("a", "b", 1)]))
    assert transport.calls == []
    graph._schema = SCHEMA
    result = asyncio.run(graph.bulk_load_edges([_edge("a", "b", 1)]))
    assert len(result.written) == 1
