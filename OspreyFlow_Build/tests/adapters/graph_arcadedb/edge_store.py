"""A shared in-memory stand-in for the part of ArcadeDB the edge-weight path reads and writes.

It answers as the real one does where it matters (it refuses a query it does not recognise, and
computes every answer from the edges actually written), so a test that carries a total or an
aggregate wrongly sees a different weight. Used by the tests of `upsert_edges`' per-call total and
of the shared merge rules (ADR-056 Amendment 22, ADR-058).
"""

from __future__ import annotations

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


class CountingStore:
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
            quoted = literals(query)  # id, source, label, reverted, superseded_by, id, target
            src, tgt = quoted[1], quoted[-1]
            found = self.edges.get((src, tgt))
            return [found] if found else []
        if ".values(" in query and ".sum()" in query:  # one vertex's own weighted degree
            vertex = literals(query)[1]
            # `bothE()` reads a link from a node to itself back twice, so it counts twice here.
            return [
                {
                    "result": sum(
                        e["occurrences"] * ((s == vertex) + (t == vertex))
                        for (s, t), e in self.edges.items()
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


def literals(query: str) -> list[str]:
    """Every quoted literal in `query` (the adapter writes ids single-quoted), in order."""
    return [m.group(2) for m in re.finditer(r"([\"'])(.*?)\1", query)]


def make_edge(source: str, target: str, n: int) -> EdgeWrite:
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


def make_adapter(store: CountingStore) -> adapter_module.GraphArcadeDBAdapter:
    graph = adapter_module.GraphArcadeDBAdapter(store, load_uk_le_scheme())  # type: ignore[arg-type]
    # `apply_schema` creates types in a live store; the weights only need the ontology in place.
    graph._schema = load_default_ontology()
    return graph


def without_clock(components: Any) -> Any:
    """`computed_at` is the call's own clock reading, so it differs between calls by design."""
    as_dict = dict(components if isinstance(components, dict) else components.model_dump())
    as_dict.pop("computed_at", None)
    return as_dict


def weights(store: CountingStore) -> dict[tuple[str, str], tuple[Any, Any, Any]]:
    return {
        pair: (e["occurrences"], e["weight"], without_clock(e["weight_components"]))
        for pair, e in store.edges.items()
    }
