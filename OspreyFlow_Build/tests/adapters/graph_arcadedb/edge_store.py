"""A shared in-memory stand-in for the part of ArcadeDB the edge-weight path reads and writes.

It answers as the real one does where it matters (it refuses a query it does not recognise, and
computes every answer from the edges actually written), so a test that carries a total or an
aggregate wrongly sees different stored components, and a different weight too under weights
version 1 only (the corpus counts reach the weight through gamma, which is 0 from version 2,
ADR-123). Used by the tests of `upsert_edges`' per-call total and
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
        self.sql_sent: list[tuple[str, dict[str, Any]]] = []
        #: The first link written for each pair; `links` has every link, since a pair may hold
        #: several (ADR-102 Amendment 3: one link per audience).
        self.edges: dict[tuple[str, str], dict[str, Any]] = {}
        self.links: list[dict[str, Any]] = []

    @staticmethod
    def _counts(edge: dict[str, Any], query: str) -> bool:
        """Whether a count query sees this edge, as the real store answers it: a link with
        `superseded_by` is left out only if the query says `hasNot("superseded_by")`, so a query
        that forgot the step still counts it (ADR-120 Amendment 5)."""
        return not ('hasNot("superseded_by")' in query and edge.get("superseded_by"))

    async def sql(
        self, command: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[dict[str, Any]]:
        """The one SQL the adapter sends here: which of `ids` a type's unique `id` index holds, so
        a new link's id is checked by the index and not by a scan of the type."""
        self.sql_sent.append((command, dict(params or {})))
        match = re.fullmatch(r"SELECT id FROM `(\w+)` WHERE id IN :ids", command)
        if match is None or params is None:
            raise AssertionError(f"unexpected SQL: {command}")
        held = {link["id"] for link in self.links}
        return [{"id": i} for i in params["ids"] if i in held]

    def corpus_total_queries(self) -> int:
        return sum(1 for q in self.queries if q.startswith("g.V().outE("))

    async def gremlin(
        self, query: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[Any]:
        self.queries.append(query)
        if query.endswith(".label()"):
            return [{"result": physical_type_name(NODE_TYPE)}]
        if query.startswith("g.V().outE("):  # the corpus total, one whole-corpus traversal
            seen = [e for e in self.edges.values() if self._counts(e, query)]
            return [{"result": sum(e["occurrences"] for e in seen)}]
        if ".elementMap()" in query:  # an existing edge for this pair
            quoted = literals(query)  # id, source, label, reverted, superseded_by, id, target
            src, tgt = quoted[1], quoted[-1]
            # As the real store answers it: a link marked reverted or superseded is left out only if
            # the query says so, so a query that forgot the step would still find it.
            return [
                link
                for link in self.links
                if (link["_src"], link["_tgt"]) == (src, tgt)
                and not ('has("reverted",false)' in query and link.get("reverted"))
                and not ('hasNot("superseded_by")' in query and link.get("superseded_by"))
            ]

        if ".values(" in query and ".sum()" in query:  # one vertex's own weighted degree
            vertex = literals(query)[1]
            # `bothE()` reads a link from a node to itself back twice, so it counts twice here.
            return [
                {
                    "result": sum(
                        e["occurrences"] * ((s == vertex) + (t == vertex))
                        for (s, t), e in self.edges.items()
                        if self._counts(e, query)
                    )
                }
            ]
        if ".addE(" in query:
            assert params is not None
            record = {key.removeprefix("prop_"): value for key, value in params.items()}
            if any(link["id"] == record["id"] for link in self.links):
                # Edge `id` is UNIQUE per type (`schema.py`): the real store refuses the write.
                raise AssertionError(f"duplicate edge id {record['id']!r}: the unique index refuses")
            record["_src"], record["_tgt"] = params["src"], params["tgt"]
            self.links.append(record)
            self.edges.setdefault((params["src"], params["tgt"]), record)
            return []
        if query.startswith('g.E().has("id"'):  # a merge into an existing edge
            assert params is not None
            for record in self.links:
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


def make_adapter(
    store: CountingStore, weight_rules: Any = None
) -> adapter_module.GraphArcadeDBAdapter:
    """`weight_rules` pins a version of the weights file (ADR-123); none takes the latest."""
    graph = adapter_module.GraphArcadeDBAdapter(
        store,  # type: ignore[arg-type]
        load_uk_le_scheme(),
        weight_rules=weight_rules,
    )
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
