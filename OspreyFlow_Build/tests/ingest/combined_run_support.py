"""What the tests of a run that combines its own writes share (ADR-127 Amendment 19). Not a test
module.

**Two graphs to run against.** `CountingMerging` is the recipe tests' stand-in (`MergingGraph`) that
also records the size of each `upsert_edges` call. `AdapterBacked` sends the same calls to the real
`GraphArcadeDBAdapter.upsert_edges` over the `CountingStore` harness of
`tests/adapters/graph_arcadedb/test_merge_rules_shared_by_both_paths.py`, so a combined run is held
to what the adapter's own merge leaves, not only to a stand-in's. Nodes are the stand-in's in both
(`CountingStore` holds no vertices); the store is told each node's type, as the real one reads it.

**The per-row reference.** A run with a flush size of one is the same code as a combined run, with
each write written as it is held (`per_row`): not a second path. `snapshot` reads what a run left
(every link by the nodes it joins and its audience, every event by the link it names, the report's
counts) so a combined run and its per-row reference can be compared field by field. The differences
the amendment states are the ones the snapshot leaves out: `weight` and its components, which are a
snapshot of the moment a link is written, and the properties stored flat on a link.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from services.ingest import engine

from adapters.graph_arcadedb.naming import logical_type_name, physical_type_name
from ontology.handling import audience_of
from schemas.domain import Handling
from schemas.ingest import Recipe
from tests.adapters.graph_arcadedb.edge_store import CountingStore, literals, make_adapter
from tests.ingest.pid_golden_support import (
    _IDENTIFIERS,
    CASE,
    ONTOLOGY,
    SCHEME,
    Step,
    load,
    marking,
)
from tests.ingest.recipe_test_support import MergingGraph
from tests.ingest.test_row_keys import KeyStore, Sink


@contextmanager
def per_row() -> Iterator[None]:
    """A run with a flush size of one: each write is written as it is held (the engine's own
    test-only setting), which is what a run without a handling scheme does."""
    saved = engine._FORCE_FLUSH_SIZE
    engine._FORCE_FLUSH_SIZE = 1
    try:
        yield
    finally:
        engine._FORCE_FLUSH_SIZE = saved


class CountingMerging(MergingGraph):
    """The recipe stand-in, recording the size of every `upsert_edges` call."""

    def __init__(self, ontology: Any) -> None:
        super().__init__(ontology)
        self.edge_calls: list[int] = []

    @property
    def edges_sent(self) -> int:
        return sum(self.edge_calls)

    async def upsert_edges(self, edges: Any, tx: object) -> list[str]:
        edges = list(edges)
        self.edge_calls.append(len(edges))
        return await super().upsert_edges(edges, tx)

    def stored_links(self) -> list[dict[str, Any]]:
        return [
            {
                "id": e.id,
                "type": e.type,
                "source": e.source,
                "target": e.target,
                "occurrences": e.occurrences,
                "interval": e.interval.model_dump(mode="json") if e.interval else None,
                "properties": dict(e.properties),
                "sources": [(s.document_id, s.locator) for s in e.provenance.sources],
                "state": e.provenance.state.value,
                "datasets": sorted(e.datasets),
                "handling": e.handling,
                "revision": self._revision.get(e.id, e.writes),
                "load_id": e.load_id,
                "recipe_id": e.recipe_id,
            }
            for e in self.committed_edges
        ]


class TypedStore(CountingStore):
    """`CountingStore` that knows each vertex's type and each link's label, so a run of several
    link types between typed nodes meets what the real store answers: the vertex's label, and only
    the links of the label asked for, in either direction for an undirected type."""

    def __init__(self, node_type: Any) -> None:
        super().__init__()
        self._node_type = node_type

    async def gremlin(
        self, query: str, *, params: dict[str, Any] | None = None, session_id: Any = None
    ) -> list[Any]:
        if query.endswith(".label()"):
            self.queries.append(query)
            found = self._node_type(literals(query)[1])
            return [] if found is None else [{"result": physical_type_name(found)}]
        if ".elementMap()" in query:
            self.queries.append(query)
            # The literals, in order: id, source, label, reverted, superseded_by, id, target.
            quoted = literals(query)
            src, label, tgt = quoted[1], quoted[2], quoted[-1]
            both = "bothE" in query
            return [
                link
                for link in self.links
                if link["_label"] == label
                and (
                    (link["_src"], link["_tgt"]) == (src, tgt)
                    or (both and (link["_src"], link["_tgt"]) == (tgt, src))
                )
                and not ('has("reverted",false)' in query and link.get("reverted"))
                and not ('hasNot("superseded_by")' in query and link.get("superseded_by"))
            ]
        result = await super().gremlin(query, params=params, session_id=session_id)
        if ".addE(" in query:
            match = re.search(r'addE\("(\w+)"\)', query)
            assert match is not None
            self.links[-1]["_label"] = match.group(1)
        return result


class AdapterBacked(CountingMerging):
    """The stand-in for everything but links, which go through the real adapter's `upsert_edges`."""

    def __init__(self, ontology: Any) -> None:
        super().__init__(ontology)
        self.store = TypedStore(self._type_of)
        self.adapter = make_adapter(self.store)
        self.adapter._schema = ontology

    async def upsert_edges(self, edges: Any, tx: object) -> list[str]:
        edges = list(edges)
        self.edge_calls.append(len(edges))
        return await self.adapter.upsert_edges(edges, str(tx))

    async def get_edges(self, edge_ids: Sequence[str], principal: Any) -> list[Any]:
        known = {link["id"] for link in self.store.links}
        return [SimpleNamespace(id=i) for i in sorted(set(edge_ids) & known)]

    def stored_links(self) -> list[dict[str, Any]]:
        return [
            {
                "id": link["id"],
                "type": logical_type_name(link["_label"]),
                "source": link["_src"],
                "target": link["_tgt"],
                "occurrences": link["occurrences"],
                "interval": link.get("interval"),
                "properties": dict(link["properties"]),
                "sources": [
                    (s["document_id"], s["locator"]) for s in link["provenance"]["sources"]
                ],
                "state": link["provenance"]["state"],
                "datasets": sorted(link["datasets"]),
                "handling": Handling.model_validate(link["handling"]),
                "revision": link["audit"]["revision"],
                "load_id": link["audit"]["load_id"],
                "recipe_id": link["audit"].get("recipe_id"),
            }
            for link in self.store.links
        ]


@dataclass(frozen=True)
class Load:
    """One load of a sequence: a file of the plan, the rows of it to load (all, if none), and the
    recipe to load it through (its committed one, if none)."""

    file: str
    rows: tuple[dict[str, str], ...] | None = None
    recipe: Recipe | None = None
    load_id: str | None = None


def loads(*steps: str | Step | Load) -> list[Load]:
    out: list[Load] = []
    for step in steps:
        if isinstance(step, Load):
            out.append(step)
        elif isinstance(step, Step):
            out.append(Load(step.file, step.rows))
        else:
            out.append(Load(step))
    return out


@dataclass
class Snapshot:
    """What a sequence of loads left, in terms that do not depend on the ids a run minted."""

    #: (type, source node, target node, audience) -> what the link holds.
    links: dict[tuple[Any, ...], dict[str, Any]] = field(default_factory=dict)
    #: One entry per event: what the event is, and the key of the link its `edge_id` names.
    events: list[tuple[Any, ...]] = field(default_factory=list)
    #: One entry per load: the report's counts, with its link ids told as keys.
    reports: list[dict[str, Any]] = field(default_factory=list)
    #: The size of every `upsert_edges` call the run made.
    calls: list[int] = field(default_factory=list)
    #: The same, for each load in turn.
    calls_by_load: list[list[int]] = field(default_factory=list)


def node_names(graph: MergingGraph) -> dict[str, tuple[str, str, str]]:
    """Each node by what names it: its type and its first identifying property."""
    names: dict[str, tuple[str, str, str]] = {}
    for node in graph.committed_nodes:
        for name in (*_IDENTIFIERS, "imsi", "handle", "email", "e164", "pnc_id"):
            if name in node.properties:
                names[node.id] = (node.type, name, str(node.properties[name]))
                break
        else:
            names[node.id] = (node.type, "*", repr(sorted(node.properties.items())))
    assert len(set(names.values())) == len(names), "two nodes hold one name: a node made twice"
    return names


def link_key(
    names: dict[str, tuple[str, str, str]],
    kind: str,
    source: str,
    target: str,
    handling: Handling,
    datasets: Sequence[str],
) -> tuple[Any, ...]:
    ends: tuple[Any, ...] = (names[source], names[target])
    edge_type = ONTOLOGY.edge_type(kind)
    assert edge_type is not None
    if not edge_type.directed:
        ends = tuple(sorted(ends))
    return (kind, *ends, audience_of(handling, datasets, SCHEME))


async def run(
    backend: str, steps: Sequence[str | Step | Load], *, combine: bool = True
) -> tuple[Snapshot, MergingGraph]:
    """The loads in order, each through `load_with_rules` against a fresh graph (`stand_in` or
    `adapter`), combined, or per row when `combine` is false; then what they left."""
    graph: CountingMerging = (
        CountingMerging(ONTOLOGY) if backend == "stand_in" else AdapterBacked(ONTOLOGY)
    )
    store = KeyStore()
    events: list[Any] = []
    reports: list[Any] = []
    by_load: list[list[int]] = []
    with per_row() if not combine else _nothing():
        for step in loads(*steps):
            before = len(graph.edge_calls)
            report, step_events = await load(
                graph,
                step.file,
                Sink(store, CASE),
                step.load_id,
                list(step.rows) if step.rows is not None else None,
                step.recipe,
            )
            assert report.rejections == [], (step.file, report.rejections[:3])
            by_load.append(graph.edge_calls[before:])
            reports.append(report)
            events.extend(step_events)
    out = snapshot(graph, events, reports)
    out.calls_by_load = by_load
    return out, graph


@contextmanager
def _nothing() -> Iterator[None]:
    yield


def snapshot(graph: CountingMerging, events: Sequence[Any], reports: Sequence[Any]) -> Snapshot:
    names = node_names(graph)
    out = Snapshot(calls=list(graph.edge_calls))
    by_id: dict[str, tuple[Any, ...]] = {}
    for link in graph.stored_links():
        key = link_key(
            names, link["type"], link["source"], link["target"], link["handling"], link["datasets"]
        )
        assert key not in out.links, ("a link made twice for one audience", key)
        by_id[link["id"]] = key
        out.links[key] = {
            "occurrences": link["occurrences"],
            "interval": link["interval"],
            "properties": link["properties"],
            "sources": link["sources"],
            "state": link["state"],
            "datasets": link["datasets"],
            "marking": marking(link["handling"]),
            "revision": link["revision"],
            "load_id": link["load_id"],
            "recipe_id": link["recipe_id"],
        }
    for event in events:
        expected = link_key(
            names, event.edge_type, event.source_id, event.target_id, event.handling, []
        )
        out.events.append(
            (
                expected,
                by_id.get(event.edge_id),
                event.occurred_at,
                tuple(event.properties.get("source_rows", ())),
                marking(event.handling),
            )
        )
    for report in reports:
        out.reports.append(
            {
                "edges_created": report.edges_created,
                "nodes_created": report.nodes_created,
                "nodes_referenced": report.nodes_referenced,
                "rows_read": report.rows_read,
                "rows_deduplicated": report.rows_deduplicated,
                "rows_already_loaded": report.rows_already_loaded,
                "kept_row_keys": list(report.kept_row_keys),
                "touched": [by_id.get(i, i) for i in report.touched_edge_ids],
                "created": [by_id.get(i, i) for i in report.created_edge_ids],
                "merged": [by_id.get(i, i) for i in report.merged_edge_ids],
                "merged_nodes": len(report.merged_node_ids),
                "created_nodes": len(report.created_node_ids),
            }
        )
    return out


# --- a pair written in more than one audience (ADR-102 Amendment 3) -----------------------------

PARTS = ("classification", "handling_code", "originator", "owning_unit")
BASE = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


def _bound_parts() -> dict[str, Any]:
    return {part: {"field": part} for part in PARTS}


def _endpoint(ref: str, column: str) -> dict[str, Any]:
    return {
        "ref": ref,
        "pole_class": "object",
        "type": "Endpoint",
        "match_on": "value_normalised",
        "on_match": "reference",
        "properties": {
            "value_raw": {"field": column},
            "value_normalised": {"field": column},
            "endpoint_kind": {"literal": "handle"},
        },
        "handling": _bound_parts(),
    }


def audience_recipe() -> Recipe:
    """Two handles and a call between them, each element's marking bound from the row's columns."""
    return Recipe.model_validate(
        {
            "id": "pairs-live",
            "version": 1,
            "label": "Pairs",
            "connector": {"profile": "csv"},
            "ontology_version": ONTOLOGY.version,
            "pack_versions": {},
            "defaults": {
                "provenance": {"state": "asserted"},
                "handling": BASE,
                "units": ["unit-1", "unit-2"],
                "handling_columns": {part: part for part in PARTS},
            },
            "row_template": {
                "entities": [_endpoint("a", "from"), _endpoint("b", "to")],
                "edges": [
                    {
                        "type": "COMMUNICATED_WITH",
                        "from": "a",
                        "to": "b",
                        "handling": _bound_parts(),
                        "properties": {"duration_s": {"field": "duration"}},
                        "temporal": {"at": {"field": "at", "transform": "datetime"}},
                    }
                ],
            },
        }
    )


def audience_row(**marking: str) -> dict[str, str]:
    """One row: the same two handles, a call of 30 s at a time, at the base marking unless `marking`
    says otherwise."""
    return {
        "from": "ZA1234ZZ",
        "to": "ZB5678ZZ",
        "duration": "30",
        "at": "2026-03-01T10:00:00+00:00",
        **BASE,
        **marking,
    }
