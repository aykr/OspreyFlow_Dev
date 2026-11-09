"""A graph for the board tests (L3.3) that holds what is written to it and refuses what the adapter
refuses (rule 15: a fake models its dependency's refusals, not only its grants).

Built on `FakeGraphPort`, which already judges each element by its own body (handling, datasets,
reverted, superseded) for the principal given, as the adapter's access step does. Added here, each
as the ArcadeDB adapter does it (`adapters/graph_arcadedb/adapter.py`):

- `upsert_nodes`: keyed on the write's id; an unknown type or an undeclared property is refused
  (`validate_properties`); a second write of the same id unions its datasets, never lowers its
  marking, and keeps an asserted body (`schemas.merge`);
- `upsert_edges`: a write merges into a live link of the same type, ends and audience
  (`audience_of`: marking, code and datasets), so a link drawn in a layer never merges into a
  loaded one; otherwise it is a new link;
- a write's provenance with its sources withheld is refused, as `serialization.py` refuses it;
- `withdraw_elements`: each live element set reverted, so every read leaves it out;
- `search_nodes` (an exact identifier) and `suggest_nodes` (`contains`, case ignored, by type),
  both filtered like every read.

Writes land only on commit; a rolled-back transaction leaves nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from conduit_common.identity import new_edge_id
from ontology.errors import OntologyError
from ontology.handling import audience_of, load_uk_le_scheme, merge_handling
from ontology.validation import validate_edge_endpoints, validate_properties
from ports.graph import NodeSuggestions, SuggestOptions
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    Node,
    NodeWrite,
    OntologySchema,
    Principal,
    Subgraph,
)
from schemas.merge import merge_datasets, merge_properties, merge_provenance

from .working_set.fakes import FakeGraphPort

SCHEME = load_uk_le_scheme()


class BoardGraph(FakeGraphPort):
    def __init__(
        self,
        ontology: OntologySchema,
        nodes: Sequence[Node] = (),
        edges: Sequence[Edge] = (),
    ) -> None:
        super().__init__(Subgraph(nodes=[], edges=[]), graph_nodes=nodes, graph_edges=edges)
        self.ontology = ontology
        self._pending: dict[str, tuple[list[NodeWrite], list[Any], list[Any], list[Any]]] = {}
        self.node_writes: list[NodeWrite] = []
        self.edge_writes: list[EdgeWrite] = []
        #: Each element `regrade_drawn` changed, in order.
        self.regrades: list[str] = []

    # --- the grading change's in-place regrade (ADR-143 Amendment 6) ---------------------------

    async def regrade_drawn(self, element_id: str, grading: Any, original: Any) -> bool:
        """As the adapter's: the drawn grade and original alone, in place, on a live drawn element
        (not reverted, not superseded); False, writing nothing, for anything else. No second write
        merges into it, so occurrences, weight, audit and resolution are as they were."""

        def regraded(element: Any) -> Any:
            drawn = element.provenance.drawn
            return element.model_copy(
                update={
                    "provenance": element.provenance.model_copy(
                        update={"drawn": drawn.model_copy(
                            update={"grading": grading, "original_grading": original}
                        )}
                    )
                }
            )  # fmt: skip

        def live_drawn(element: Any) -> bool:
            return (
                not element.audit.reverted
                and element.audit.superseded_by is None
                and element.provenance.drawn is not None
            )

        held = self._graph_nodes.get(element_id)
        if held is not None:
            if not live_drawn(held):
                return False
            self._graph_nodes[element_id] = regraded(held)
            self.regrades.append(element_id)
            return True
        for index, edge in enumerate(self._graph_edges):
            if edge.id == element_id:
                if not live_drawn(edge):
                    return False
                self._graph_edges[index] = regraded(edge)
                self.regrades.append(element_id)
                return True
        return False

    # --- reads -------------------------------------------------------------------------------

    def node(self, node_id: str) -> Node:
        return self._graph_nodes[node_id]

    def edges(self) -> list[Edge]:
        return list(self._graph_edges)

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        found = []
        for node in self._graph_nodes.values():
            entity = self.ontology.entity_type(node.type)
            keys = entity.identifiers if entity is not None else []
            if any(node.properties.get(k) == query for k in keys) and self._node_readable(
                principal, node
            ):
                found.append(node)
        return sorted(found, key=lambda n: n.id)[:limit]

    async def suggest_nodes(
        self,
        prefix: str,
        principal: Principal,
        *,
        limit: int = 10,
        options: SuggestOptions | None = None,
    ) -> NodeSuggestions:
        if not prefix:
            raise ValueError("an empty prefix is refused")
        options = options or SuggestOptions()
        if options.types:
            for t in options.types:
                if self.ontology.entity_type(t) is None:
                    raise ValueError(f"{t!r} is not a type")
        hits = []
        for node in sorted(self._graph_nodes.values(), key=lambda n: n.id):
            if options.types and node.type not in options.types:
                continue
            if not self._node_readable(principal, node):
                continue
            values = [v for v in node.properties.values() if isinstance(v, str)]
            if any(prefix.casefold() in v.casefold() for v in values):
                hits.append(node)
        return NodeSuggestions(nodes=hits[:limit], more=len(hits) > limit)

    # --- writes ------------------------------------------------------------------------------

    async def begin_transaction(self) -> str:
        tx = await super().begin_transaction()
        self._pending[tx] = ([], [], [], [])
        return tx

    async def commit_transaction(self, tx: str) -> None:
        await super().commit_transaction(tx)
        nodes, edges, withdrawals, supersessions = self._pending.pop(tx)
        for write in nodes:
            self._land_node(write)
        for write, edge_id in edges:
            self._land_edge(write, edge_id)
        for old_id, replacement, new_id in supersessions:
            self._graph_edges = [
                e.model_copy(update={"audit": e.audit.model_copy(update={"superseded_by": new_id})})
                if e.id == old_id
                else e
                for e in self._graph_edges
            ]
            self._land_edge(replacement, new_id)
        for node_ids, edge_ids, load_id in withdrawals:
            self._land_withdrawal(node_ids, edge_ids, load_id)

    async def rollback_transaction(self, tx: str) -> None:
        await super().rollback_transaction(tx)
        self._pending.pop(tx, None)

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: str) -> list[str]:
        for write in nodes:
            entity = self.ontology.entity_type(write.type)
            if entity is None:
                raise OntologyError(f"{write.type!r} is not a type in the active ontology")
            validate_properties(entity, write.properties)
            if write.provenance.sources_withheld:
                raise ValueError("a withheld provenance is never written")
        self._pending[tx][0].extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: str) -> list[str]:
        await super().upsert_edges(edges, tx)
        ids = []
        for write in edges:
            if self.ontology.edge_type(write.type) is None:
                raise OntologyError(f"{write.type!r} is not a link type in the active ontology")
            edge_type = self.ontology.edge_type(write.type)
            assert edge_type is not None
            source_type = self._ends_type(write.source, tx)
            target_type = self._ends_type(write.target, tx)
            if source_type is None or target_type is None:
                raise OntologyError("an edge end does not exist")
            validate_edge_endpoints(edge_type, source_type=source_type, target_type=target_type)
            held = self._merge_target(write)
            if held is not None:
                edge_id = held.id
            elif any(e.id == write.id for e in self._graph_edges):
                # As the adapter: edge `id` is unique, so a write of a taken id at another
                # audience is a link of its own under a new id (ADR-102 Amendment 3).
                edge_id = new_edge_id()
            else:
                edge_id = write.id
            ids.append(edge_id)
            self._pending[tx][1].append((write, edge_id))
        return ids

    def _ends_type(self, node_id: str, tx: str) -> str | None:
        held = self._graph_nodes.get(node_id)
        if held is not None:
            return held.type
        pending = [w for w in self._pending[tx][0] if w.id == node_id]
        return pending[0].type if pending else None

    async def supersede_edge(
        self, edge_id: str, replacement: EdgeWrite, tx: str, *, old_type: str
    ) -> str:
        new_id = new_edge_id()
        self._pending[tx][3].append((edge_id, replacement, new_id))
        return new_id

    async def withdraw_elements(
        self, node_ids: Sequence[str], edge_ids: Sequence[str], load_id: str, tx: str
    ) -> None:
        self._pending[tx][2].append((list(node_ids), list(edge_ids), load_id))

    def _merge_target(self, write: EdgeWrite) -> Edge | None:
        key = audience_of(write.handling, write.datasets, SCHEME)
        for edge in self._graph_edges:
            if (
                edge.type == write.type
                and edge.source == write.source
                and edge.target == write.target
                and not edge.audit.reverted
                and audience_of(edge.handling, edge.datasets, SCHEME) == key
            ):
                return edge
        return None

    def _land_node(self, write: NodeWrite) -> None:
        self.node_writes.append(write)
        held = self._graph_nodes.get(write.id)
        if held is None or held.audit.reverted:
            self._graph_nodes[write.id] = Node(
                id=write.id, type=write.type, properties=write.properties,
                provenance=write.provenance, handling=write.handling,
                resolution=write.resolution,
                audit=AuditStub(created_at=write.created_at, created_by=write.created_by,
                                load_id=write.load_id),
                datasets=sorted(set(write.datasets)),
            )  # fmt: skip
            return
        self._graph_nodes[write.id] = held.model_copy(
            update={
                "properties": merge_properties(
                    held.properties,
                    write.properties,
                    existing_provenance=held.provenance,
                    incoming_provenance=write.provenance,
                ),
                "provenance": merge_provenance(held.provenance, write.provenance),
                "handling": merge_handling(held.handling, write.handling, SCHEME),
                "datasets": merge_datasets(held.datasets, write.datasets),
                "audit": held.audit.model_copy(update={"revision": held.audit.revision + 1}),
            }
        )

    def _land_edge(self, write: EdgeWrite, edge_id: str) -> None:
        self.edge_writes.append(write)
        held = self._merge_target(write)
        if held is None or held.id != edge_id:
            self._graph_edges.append(
                Edge(
                    id=edge_id,
                    type=write.type,
                    source=write.source,
                    target=write.target,
                    properties=write.properties,
                    provenance=write.provenance,
                    handling=write.handling,
                    audit=AuditStub(created_at=write.created_at, created_by=write.created_by),
                    datasets=sorted(set(write.datasets)),
                )
            )
            return
        merged = held.model_copy(
            update={
                "properties": merge_properties(
                    held.properties,
                    write.properties,
                    existing_provenance=held.provenance,
                    incoming_provenance=write.provenance,
                ),
                "provenance": merge_provenance(held.provenance, write.provenance),
                "handling": merge_handling(held.handling, write.handling, SCHEME),
                "datasets": merge_datasets(held.datasets, write.datasets),
                "occurrences": held.occurrences + 1,
            }
        )
        self._graph_edges = [merged if e.id == held.id else e for e in self._graph_edges]

    def _land_withdrawal(self, node_ids: list[str], edge_ids: list[str], load_id: str) -> None:
        def withdrawn(audit: AuditStub) -> AuditStub:
            if audit.reverted:
                return audit
            return audit.model_copy(update={"reverted": True, "withdrawn_by_load": load_id})

        for node_id in node_ids:
            held = self._graph_nodes.get(node_id)
            if held is not None:
                self._graph_nodes[node_id] = held.model_copy(
                    update={"audit": withdrawn(held.audit)}
                )
        wanted = set(edge_ids)
        self._graph_edges = [
            e.model_copy(update={"audit": withdrawn(e.audit)}) if e.id in wanted else e
            for e in self._graph_edges
        ]


def now() -> datetime:
    return datetime.now(UTC)
