"""The corpus total behind an edge's weight is read once per `upsert_edges` call, not once per edge
(ADR-056 Amendment 22).

Seen, 1 October 2026, loading the Enron corpus (233,890 links): every edge written asked the store
for the total weight of every edge of its type, a query that visits the whole corpus. The cost of
a write therefore grew with everything already loaded: 146 s per 1,000 links at the start and 230 s
per 1,000 at 82,000 links, a projected 17 hours. The total only has to be read once per call and
carried forward, because the call's own writes are the only change it can see.

The store below answers as the real one does where it matters here: it refuses a query it does not
recognise, and it computes every answer from the edges actually written, so a total that is carried
forward wrongly changes a weight and fails the comparison with the one-at-a-time result.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from adapters.graph_arcadedb import adapter as adapter_module
from adapters.graph_arcadedb.naming import physical_type_name
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, Provenance, ProvenanceState, SourceRef

EDGE_TYPE = "TRANSACTED"
NODE_TYPE = "Endpoint"


class _CountingStore:
    """In-memory stand-in for the part of ArcadeDB the weight path reads and writes."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.edges: dict[tuple[str, str], dict[str, Any]] = {}

    def corpus_total_queries(self) -> int:
        return sum(1 for q in self.queries if q.startswith("g.V().outE("))

    async def gremlin(
        self, query: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[Any]:
        self.queries.append(query)
        if query.endswith(".label()"):
            return [{"result": physical_type_name(NODE_TYPE)}]
        if query.startswith("g.V().outE("):  # the corpus total, one whole-corpus traversal
            return [{"result": sum(e["occurrences"] for e in self.edges.values())}]
        if ".elementMap()" in query:  # an existing edge for this pair
            literals = _literals(query)  # id, source, label, reverted, id, target
            src, tgt = literals[1], literals[5]
            found = self.edges.get((src, tgt))
            return [found] if found else []
        if ".values(" in query and ".sum()" in query:  # one vertex's own weighted degree
            vertex = _literals(query)[1]
            return [
                {
                    "result": sum(
                        e["occurrences"] for (s, t), e in self.edges.items() if vertex in (s, t)
                    )
                }
            ]
        if ".addE(" in query:
            assert params is not None
            record = {key.removeprefix("prop_"): value for key, value in params.items()}
            self.edges[(params["src"], params["tgt"])] = record
            return []
        if query.startswith('g.E().has("id"'):  # a merge into an existing edge
            assert params is not None
            for record in self.edges.values():
                if record["id"] == params["prop_id"]:
                    record.update({k.removeprefix("prop_"): v for k, v in params.items()})
            return []
        raise AssertionError(f"unexpected query: {query}")


def _literals(query: str) -> list[str]:
    """Every quoted literal in `query` (the adapter writes ids single-quoted), in order."""
    return [m.group(2) for m in re.finditer(r"([\"'])(.*?)\1", query)]


def _edge(source: str, target: str, n: int) -> EdgeWrite:
    now = datetime.now(UTC)
    return EdgeWrite(
        id=f"edge-{n}",
        type=EDGE_TYPE,
        source=source,
        target=target,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fixture", locator=f"row-{n}", excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
        ),
        created_by="test",
        created_at=now,
    )


def _batch() -> list[EdgeWrite]:
    """Forty writes, with the pair a to b recurring so the merge path is exercised too."""
    writes = [_edge(f"n{i}", f"n{i + 1}", i) for i in range(37)]
    writes += [_edge("a", "b", 100), _edge("a", "b", 101), _edge("b", "a", 102)]
    return writes


def _adapter(store: _CountingStore) -> adapter_module.GraphArcadeDBAdapter:
    graph = adapter_module.GraphArcadeDBAdapter(store, load_uk_le_scheme())  # type: ignore[arg-type]
    # `apply_schema` creates types in a live store; the weights only need the ontology in place.
    graph._schema = load_default_ontology()
    return graph


def _without_clock(components: Any) -> Any:
    """`computed_at` is the call's own clock reading, so it differs between calls by design."""
    as_dict = dict(components if isinstance(components, dict) else components.model_dump())
    as_dict.pop("computed_at", None)
    return as_dict


def _weights(store: _CountingStore) -> dict[tuple[str, str], tuple[Any, Any, Any]]:
    return {
        pair: (e["occurrences"], e["weight"], _without_clock(e["weight_components"]))
        for pair, e in store.edges.items()
    }


def test_a_batch_reads_the_corpus_total_once() -> None:
    """Catches the corpus total being asked for once per edge: forty writes would cost forty
    whole-corpus traversals, the quadratic load that took 17 hours projected on Enron."""
    store = _CountingStore()
    asyncio.run(_adapter(store).upsert_edges(_batch(), "tx"))
    assert store.corpus_total_queries() == 1


def test_a_batch_weighs_each_edge_as_if_written_one_at_a_time() -> None:
    """Catches the carried-forward total drifting from the stored one: skipping the call's own
    delta, adding it twice, or not adding it for a merge into an existing pair would each change a
    weight, so the batch and the one-at-a-time loads would disagree."""
    batched = _CountingStore()
    asyncio.run(_adapter(batched).upsert_edges(_batch(), "tx"))

    one_by_one = _CountingStore()
    graph = _adapter(one_by_one)
    for write in _batch():
        asyncio.run(graph.upsert_edges([write], "tx"))

    assert one_by_one.corpus_total_queries() == len(_batch())  # the unchanged behaviour per call
    assert _weights(batched) == _weights(one_by_one)


def test_nothing_is_carried_from_one_call_to_the_next() -> None:
    """Catches the total being kept on the adapter between calls: a second call must read the
    store again, because anything else may have written or reverted since the first."""
    store = _CountingStore()
    graph = _adapter(store)
    asyncio.run(graph.upsert_edges(_batch()[:5], "tx"))
    asyncio.run(graph.upsert_edges(_batch()[5:10], "tx"))
    assert store.corpus_total_queries() == 2
