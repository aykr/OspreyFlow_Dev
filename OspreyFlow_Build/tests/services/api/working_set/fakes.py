"""In-memory fakes for `WorkingSetService` unit tests. `WorkingSetStorage`
and the two `GraphPort` methods the service calls are both structural
(`Protocol`), so exercising the service's own logic — the cap check over the reader's
view, the access index, the reconnect gap detection — needs neither
a live Valkey nor a live ArcadeDB. `tests/services/api/
test_valkey_store.py` covers `ValkeyWorkingSetStore` itself against the
real thing, once `make dev-up` exists to provide one.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

from services.api.rule_evaluation import handling_readable
from services.api.working_set.access_index import (
    AccessCounts,
    AccessEntries,
    CountedIndex,
    IndexState,
    signature_id,
    signature_of,
)
from services.api.working_set.models import WorkingSetDelta, decode_delta, lacks_record
from services.api.working_set.store import EdgeRewrite, _refuse_a_move

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    Handling,
    Node,
    NodeId,
    Path,
    Principal,
    Provenance,
    ProvenanceState,
    RoutesAtLength,
    SourceRef,
    Subgraph,
    TxId,
)

_SCHEME = load_uk_le_scheme()

#: Epoch tokens for the fake's access index: one new token for each case's life.
_EPOCHS = itertools.count(1)

#: `FakeGraphPort.get_node`'s own default "visible" response — its content is never asserted on
#: by any test; only whether `get_node` was called and whether it returned `None` is.
_FAKE_VISIBLE_NODE = Node(
    id="fake-visible-node",
    type="Person",
    properties={},
    provenance=Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    ),
    handling=Handling(
        classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
    ),
    audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="fixture"),
)


class FakeWorkingSetStore:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[NodeId, Node]] = {}
        self._edges: dict[str, dict[EdgeId, Edge]] = {}
        self._seq: dict[str, int] = {}
        #: The access index, kept beside the bodies as the Valkey store keeps it (ADR-124
        #: Amendment 4): written by the same methods that write the bodies, never derived from
        #: them on read, so a method that forgets it is a difference a test can see.
        self._index: dict[str, IndexState] = {}
        self._deltas: dict[str, list[WorkingSetDelta]] = {}
        self._thresholds: dict[str, float] = {}
        #: Set to simulate the capped stream trimming older entries —
        #: `None` means unbounded (the default; most tests don't care).
        self.stream_maxlen: int | None = None
        #: Called by `rewrite_edges_if_unchanged` between its read and its write, with the case id.
        self._between_read_and_write: Callable[[str], Awaitable[None]] | None = None

    def _n(self, investigation_id: str) -> dict[NodeId, Node]:
        return self._nodes.setdefault(investigation_id, {})

    def _e(self, investigation_id: str) -> dict[EdgeId, Edge]:
        return self._edges.setdefault(investigation_id, {})

    def _d(self, investigation_id: str) -> list[WorkingSetDelta]:
        return self._deltas.setdefault(investigation_id, [])

    async def source_fidelity_nodes(self, investigation_id: str) -> dict[NodeId, Node]:
        return dict(self._n(investigation_id))

    async def source_fidelity_edges(self, investigation_id: str) -> dict[EdgeId, Edge]:
        return dict(self._e(investigation_id))

    async def node_ids(self, investigation_id: str) -> set[NodeId]:
        return set(self._n(investigation_id))

    async def edge_ids(self, investigation_id: str) -> set[EdgeId]:
        return set(self._e(investigation_id))

    async def get_edge(self, investigation_id: str, edge_id: EdgeId) -> Edge | None:
        return self._e(investigation_id).get(edge_id)

    async def get_node(self, investigation_id: str, node_id: NodeId) -> Node | None:
        return self._n(investigation_id).get(node_id)

    def _state(self, investigation_id: str) -> IndexState:
        return self._index.setdefault(investigation_id, IndexState())

    async def add_nodes(self, investigation_id: str, nodes: Sequence[Node]) -> None:
        if not nodes:
            return
        self._n(investigation_id).update({n.id: n for n in nodes})
        state = self._state(investigation_id)
        for n in nodes:
            signature = signature_of(n.handling, n.datasets)
            state.set_node(n.id, signature_id(signature), signature)
        state.written(f"epoch-{next(_EPOCHS)}")

    async def add_edges(self, investigation_id: str, edges: Sequence[Edge]) -> None:
        if not edges:
            return
        self._e(investigation_id).update({e.id: e for e in edges})
        state = self._state(investigation_id)
        for e in edges:
            signature = signature_of(e.handling, e.datasets)
            state.set_edge(e.id, signature_id(signature), signature, e.source, e.target)
        state.written(f"epoch-{next(_EPOCHS)}")

    async def rewrite_edges_if_unchanged(
        self, investigation_id: str, rewrite: Callable[[Edge], Edge | None]
    ) -> EdgeRewrite:
        """The store's conditional rewrite, over this fake's bodies: a link is replaced only if the
        body in the fake is still the one that was read (equal as a model), so a link a test
        removes or replaces from `_between_read_and_write` is skipped."""
        read = dict(self._e(investigation_id))
        changes: list[tuple[Edge, Edge]] = []
        for old in read.values():
            new = rewrite(old)
            if new is None:
                continue
            _refuse_a_move(old, new)
            changes.append((old, new))
        if self._between_read_and_write is not None:
            await self._between_read_and_write(investigation_id)
        rewritten = 0
        for old, new in changes:
            if self._e(investigation_id).get(old.id) == old:
                self._e(investigation_id)[old.id] = new
                rewritten += 1
        return EdgeRewrite(rewritten=rewritten, skipped=len(changes) - rewritten)

    async def remove_nodes(self, investigation_id: str, node_ids: Sequence[NodeId]) -> None:
        if not node_ids:
            return
        store = self._n(investigation_id)
        state = self._state(investigation_id)
        for node_id in node_ids:
            store.pop(node_id, None)
            state.remove_node(node_id)
        state.written(f"epoch-{next(_EPOCHS)}")

    async def remove_edges(self, investigation_id: str, edge_ids: Sequence[EdgeId]) -> None:
        if not edge_ids:
            return
        store = self._e(investigation_id)
        state = self._state(investigation_id)
        for edge_id in edge_ids:
            store.pop(edge_id, None)
            state.remove_edge(edge_id)
        state.written(f"epoch-{next(_EPOCHS)}")

    async def access_counts(self, investigation_id: str) -> AccessCounts:
        return self._state(investigation_id).counts()

    async def access_entries(
        self, investigation_id: str, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId]
    ) -> AccessEntries:
        return self._state(investigation_id).entries(list(node_ids), list(edge_ids))

    async def adjacent_edge_ids(
        self, investigation_id: str, node_ids: Sequence[NodeId]
    ) -> dict[NodeId, list[EdgeId]]:
        return self._state(investigation_id).adjacent(list(node_ids))

    async def stored_node_signatures(self, investigation_id: str) -> dict[NodeId, str]:
        return dict(self._state(investigation_id).index.nodes)

    async def counted_index(self, investigation_id: str) -> CountedIndex:
        """Everything the index holds, for the consistency tests."""
        return self._state(investigation_id).index

    async def node_count(self, investigation_id: str) -> int:
        return len(self._n(investigation_id))

    async def edge_count(self, investigation_id: str) -> int:
        return len(self._e(investigation_id))

    async def next_seq(self, investigation_id: str) -> int:
        self._seq[investigation_id] = self._seq.get(investigation_id, 0) + 1
        return self._seq[investigation_id]

    async def current_seq(self, investigation_id: str) -> int:
        return self._seq.get(investigation_id, 0)

    async def append_delta(self, investigation_id: str, delta: WorkingSetDelta) -> None:
        deltas = self._d(investigation_id)
        # As the real stream: what is stored is JSON, and what is read back is what decoding that
        # makes of it, so a form that does not survive the trip does not survive it here.
        deltas.append(decode_delta(json.loads(delta.model_dump_json())))
        if self.stream_maxlen is not None and len(deltas) > self.stream_maxlen:
            del deltas[: len(deltas) - self.stream_maxlen]

    async def deltas_after(
        self, investigation_id: str, since_seq: int
    ) -> list[WorkingSetDelta] | None:
        current = await self.current_seq(investigation_id)
        if since_seq >= current:
            return []
        # Filter to "after `since_seq`" first, the same way `XRANGE
        # (since_seq-0 +` does against the real stream — only *then* is
        # the first entry's seq meaningful as "the oldest retained entry
        # the client doesn't already have", which is what the gap check
        # below actually needs to compare against.
        after = [d for d in self._d(investigation_id) if d.seq > since_seq]
        if not after or after[0].seq != since_seq + 1:
            return None  # trimmed past what the client last saw
        if any(lacks_record(d) for d in after):
            return None  # as the real store: a removal with no record cannot be projected
        return after

    async def clear(self, investigation_id: str) -> None:
        self._nodes.pop(investigation_id, None)
        self._edges.pop(investigation_id, None)
        self._index.pop(investigation_id, None)
        self._seq.pop(investigation_id, None)
        self._deltas.pop(investigation_id, None)
        self._thresholds.pop(investigation_id, None)

    async def get_threshold(self, investigation_id: str) -> float | None:
        return self._thresholds.get(investigation_id)

    async def set_threshold(self, investigation_id: str, tau: float) -> None:
        self._thresholds[investigation_id] = tau


class FakeGraphPort:
    """`expand` plus the transaction/`upsert_edges` trio
    `manual_link`/`manual_split` need — the full set `WorkingSetService` actually calls, still no
    real ArcadeDB. Configure `expand_result` per test; `expand_requests`
    records every call for assertions like "the same request drove both calls". `committed_edges`
    records every edge a test's `manual_link`/`manual_split` call actually persisted (only after
    `commit_transaction`, never after a `rollback_transaction`), so a test can assert on the write
    without needing a real transactional store."""

    def __init__(
        self,
        expand_result: Subgraph,
        *,
        hidden_node_ids: frozenset[NodeId] = frozenset(),
        graph_edges: Sequence[Edge] = (),
        graph_nodes: Sequence[Node] = (),
        superseded_node_ids: frozenset[NodeId] = frozenset(),
        hidden_edge_ids: frozenset[EdgeId] = frozenset(),
        superseded_edge_ids: frozenset[EdgeId] = frozenset(),
    ) -> None:
        self.expand_result = expand_result
        #: The graph's links, for `edges_among` (ADR-098) and `get_edges` (ADR-124). The links
        #: `expand_result` returns are in the graph too (see `_world_edges`).
        self._graph_edges = list(graph_edges)
        self.edges_among_requests: list[tuple[list[NodeId], Principal]] = []
        #: The nodes `get_nodes` and `get_edges` (ADR-124) can find, besides those `expand_result`
        #: returns (see `_world_nodes`): an id outside both is absent, as an id the Vault never held
        #: is. "Hidden" therefore means present but unreadable: each element is judged by its own
        #: body, for the principal given, as the adapter's access step judges it.
        self._graph_nodes = {n.id: n for n in graph_nodes}
        #: Overrides, kept for tests that name an id rather than build a body: left out whatever
        #: the body says, as `hidden_node_ids` is.
        self._superseded_node_ids = superseded_node_ids
        self._hidden_edge_ids = hidden_edge_ids
        self._superseded_edge_ids = superseded_edge_ids
        self.get_nodes_requests: list[tuple[list[NodeId], Principal]] = []
        self.get_edges_requests: list[tuple[list[EdgeId], Principal]] = []
        self.paths_at_length_requests: list[tuple[NodeId, NodeId, int, Principal]] = []
        self.expand_requests: list[ExpandRequest] = []
        self.get_node_requests: list[tuple[NodeId, Principal]] = []
        self.committed_edges: list[EdgeWrite] = []
        self._pending_edges: dict[TxId, list[EdgeWrite]] = {}
        self._next_tx = 0
        #: Only for `get_node`, which predates ADR-124 and is not a stand-in for the adapter: every
        #: id not named here is visible to every principal, an id nobody holds included
        #: (`tests/resolve/test_projection_access_control.py` proves the real filtering against the
        #: real adapter). A test that only cares about `_manual_assertion`'s own *call shape* (does
        #: it call `get_node` and honour a `None` result) configures this. `get_nodes`,
        #: `get_edges` and `edges_among` also leave these ids out, as an override.
        self._hidden_node_ids = hidden_node_ids

    async def get_node(
        self, node_id: NodeId, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        # Predates ADR-124 and is left as it was: it returns a visible node for any id not marked
        # hidden. `get_nodes` and `get_edges` below do not copy that.
        self.get_node_requests.append((node_id, principal))
        if node_id in self._hidden_node_ids:
            return None
        return _FAKE_VISIBLE_NODE

    def _world_nodes(self) -> dict[NodeId, Node]:
        """What a lookup by id can find: `graph_nodes` and the nodes `expand_result` returns."""
        return {**{n.id: n for n in self.expand_result.nodes}, **self._graph_nodes}

    def _world_edges(self) -> dict[EdgeId, Edge]:
        """The links `graph_edges` holds and the links `expand_result` returns."""
        return {
            **{e.id: e for e in self.expand_result.edges},
            **{e.id: e for e in self._graph_edges},
        }

    @staticmethod
    def _body_readable(
        principal: Principal, element: Node | Edge, *, superseded: bool, hidden: bool
    ) -> bool:
        """The adapter's access step, on the element's own body: handling, datasets, a superseded
        body, a reverted body; and the explicit overrides."""
        if hidden or superseded or element.audit.superseded_by is not None:
            return False
        if element.audit.reverted:
            return False
        if principal.datasets is not None and not set(principal.datasets) & set(element.datasets):
            return False
        return handling_readable(_SCHEME, principal, element.handling)

    def _node_readable(self, principal: Principal, node: Node) -> bool:
        return self._body_readable(
            principal,
            node,
            superseded=node.id in self._superseded_node_ids,
            hidden=node.id in self._hidden_node_ids,
        )

    def _edge_readable(self, principal: Principal, edge: Edge) -> bool:
        return self._body_readable(
            principal,
            edge,
            superseded=edge.id in self._superseded_edge_ids,
            hidden=edge.id in self._hidden_edge_ids,
        )

    async def strip_provenance_references(self, prefix: str) -> int:
        """The port's one-off rewrite, over every link this fake holds (`graph_edges` and the links
        `expand_result` returns): the provenance entries whose `document_id` starts with `prefix`
        are removed, whether or not the link is hidden, superseded or reverted, and the number of
        links that changed is returned."""
        changed = 0

        def stripped(edge: Edge) -> Edge:
            nonlocal changed
            kept = [s for s in edge.provenance.sources if not s.document_id.startswith(prefix)]
            if len(kept) == len(edge.provenance.sources):
                return edge
            changed += 1
            return edge.model_copy(
                update={"provenance": edge.provenance.model_copy(update={"sources": kept})}
            )

        self._graph_edges = [stripped(e) for e in self._graph_edges]
        self.expand_result = self.expand_result.model_copy(
            update={"edges": [stripped(e) for e in self.expand_result.edges]}
        )
        return changed

    async def get_nodes(self, node_ids: Sequence[NodeId], principal: Principal) -> list[Node]:
        """ADR-124's read by id. Unlike `get_node` above, this finds only what the fake holds and
        judges each node by its own body for `principal`: an absent, an unreadable, a superseded
        and a reverted id are left out alike, each node once, ordered by id."""
        # A bare str is a sequence of characters: refused as the adapter does.
        if isinstance(node_ids, str):
            raise TypeError("ids must be a sequence of ids, not a single string")
        self.get_nodes_requests.append((list(node_ids), principal))
        world = self._world_nodes()
        return [
            world[i]
            for i in sorted(set(node_ids))
            if i in world and self._node_readable(principal, world[i])
        ]

    async def get_edges(self, edge_ids: Sequence[EdgeId], principal: Principal) -> list[Edge]:
        """ADR-124's read by id: a link comes back only when it is held, it is readable by its own
        body, and both its ends are held and readable by theirs."""
        # A bare str is a sequence of characters: refused as the adapter does.
        if isinstance(edge_ids, str):
            raise TypeError("ids must be a sequence of ids, not a single string")
        self.get_edges_requests.append((list(edge_ids), principal))
        nodes = self._world_nodes()
        edges = self._world_edges()
        found: list[Edge] = []
        for edge_id in sorted(set(edge_ids)):
            edge = edges.get(edge_id)
            if edge is None or not self._edge_readable(principal, edge):
                continue
            ends = (nodes.get(edge.source), nodes.get(edge.target))
            if all(end is not None and self._node_readable(principal, end) for end in ends):
                found.append(edge)
        return found

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        self.expand_requests.append(req)
        return self.expand_result

    async def edges_among(
        self,
        node_ids: Sequence[NodeId],
        principal: Principal,
        edge_types: list[str] | None = None,
    ) -> list[Edge]:
        self.edges_among_requests.append((list(node_ids), principal))
        asked = set(node_ids)
        nodes = self._world_nodes()

        def end_readable(node_id: NodeId) -> bool:
            # An end the fake holds no body for (a node the test keeps only in its store) is
            # judged by the override sets alone, as before ADR-124.
            if node_id in nodes:
                return self._node_readable(principal, nodes[node_id])
            return node_id not in self._hidden_node_ids | self._superseded_node_ids

        return [
            e
            for e in self._world_edges().values()
            if e.source in asked
            and e.target in asked
            and (not edge_types or e.type in edge_types)
            and self._edge_readable(principal, e)
            and end_readable(e.source)
            and end_readable(e.target)
        ]

    async def paths_at_length(
        self,
        source: NodeId,
        target: NodeId,
        length: int,
        limit: int,
        principal: Principal,
        *,
        edge_types: list[str] | None = None,
    ) -> RoutesAtLength:
        """ADR-116's search over this fake's links: the simple routes of exactly `length` links,
        either way along each, never through a hidden node — as the real adapter refuses a route
        through what the reader cannot see (its conformance suite proves that, not this)."""
        self.paths_at_length_requests.append((source, target, length, principal))
        found: list[Path] = []

        def walk(at: NodeId, seen: list[NodeId], edges: list[Edge]) -> None:
            if len(edges) == length:
                if at == target:
                    nodes = [_FAKE_VISIBLE_NODE.model_copy(update={"id": n}) for n in seen]
                    found.append(Path(nodes=nodes, edges=list(edges), length=length))
                return
            for e in self._graph_edges:
                if edge_types and e.type not in edge_types:
                    continue
                other = e.target if e.source == at else e.source if e.target == at else None
                if other is None or other in seen or other in self._hidden_node_ids:
                    continue
                walk(other, [*seen, other], [*edges, e])

        if source not in self._hidden_node_ids and target not in self._hidden_node_ids:
            walk(source, [source], [])
        return RoutesAtLength(length=length, paths=found[:limit], more=len(found) > limit)

    async def begin_transaction(self) -> TxId:
        self._next_tx += 1
        tx = f"tx-{self._next_tx}"
        self._pending_edges[tx] = []
        return tx

    async def commit_transaction(self, tx: TxId) -> None:
        self.committed_edges.extend(self._pending_edges.pop(tx))

    async def rollback_transaction(self, tx: TxId) -> None:
        self._pending_edges.pop(tx, None)

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]:
        self._pending_edges[tx].extend(edges)
        return [e.id for e in edges]
