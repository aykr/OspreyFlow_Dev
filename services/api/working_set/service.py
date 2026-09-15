"""The Working-Set Service's orchestration — `docs/03_CONDUIT_MIDDLEWARE.md`
§4, "the most important component in the Conduit". Owns four things
nothing else in the platform can safely do on its own: the cap check that
never truncates, `filtered_count`'s derivation (`01_DOMAIN_MODEL.md` §8.2),
the reconnect-or-resnapshot decision for the delta protocol (§3.2), and —
the divergence-review fix — the per-read handling projection §4 itself
requires: "The stored set is source-fidelity. The projection applied on
read is: resolution collapse at the session's τ, handling filter for the
principal, then delta computation."

**Why the store can hold more than one principal legitimately fetched.**
An investigation is not single-principal for its whole life: a branch, or
a shared team investigation (`investigations.py`'s `owning_unit` is
unit-wide, not creator-only), means a later reader's own `Principal` may
be a different, less-privileged one than whoever's `expand()`/`seed()`
call originally populated a given node. `GraphPort`'s own access filtering
at the point of fetch is still the only thing that ever decides what gets
*written* — nothing here second-guesses that, and there is no unfiltered
port call anywhere in this class. What `_project`/`project_delta` add is
a *second*, independent filter for whoever is *reading* the store back,
using the same predicate the adapter's compiled Gremlin is built from
(`ontology.handling.principal_may_view`), so a stored node that one
principal was entitled to fetch is not disclosed to a different principal
who is not.

`filtered_count`'s own derivation is unrelated arithmetic over two
properly-authorised `GraphPort` calls for the *same* expand:
`expand()` (filtered, what the analyst actually gets) and
`expand_candidate_count()` (unfiltered, no principal, count-only) — see
`ports/graph.py`'s docstring for why a bare count from the second call
cannot itself leak anything the first call didn't already legitimately
compute the boundary of.
"""

from __future__ import annotations

from collections.abc import Sequence

from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from schemas.domain import Edge, ExpandRequest, Node, NodeId, Principal

from .models import (
    MAX_EDGES,
    MAX_NODES,
    CardinalityPreview,
    DeltaAdd,
    DeltaNotice,
    DeltaRemove,
    DeltaSnapshot,
    ExpansionOutcome,
    LimitExceeded,
    LimitExceededError,
    WorkingSetDelta,
)
from .store import WorkingSetStorage


def _filtered_count(candidate_count: int, delivered_count: int) -> int:
    """`candidate_count` (`GraphPort.expand_candidate_count`) is always
    `>=` `delivered_count` (`len(Subgraph.nodes)`) by construction — the
    filtered result is a subset of the unfiltered candidates over the same
    scope. `max(..., 0)` is defensive, not load-bearing: it guards against
    an adapter bug inverting that invariant becoming a *negative* reported
    count instead of a wrong-but-visible one."""
    return max(candidate_count - delivered_count, 0)


class WorkingSetService:
    def __init__(
        self, graph: GraphPort, store: WorkingSetStorage, handling_scheme: HandlingScheme
    ) -> None:
        self._graph = graph
        self._store = store
        self._scheme = handling_scheme

    def _project(
        self, nodes: Sequence[Node], edges: Sequence[Edge], principal: Principal
    ) -> tuple[list[Node], list[Edge], int]:
        """The read-time handling filter `03_CONDUIT_MIDDLEWARE.md` §4
        requires. An edge is visible only if both its own handling block
        clears *and* both endpoints are among the visible nodes — an edge
        whose handling alone would pass but which points at a node this
        principal cannot see would itself disclose that hidden node's
        existence, exactly the leak `principal_may_view` exists to
        prevent at node level."""
        visible_nodes = [
            n for n in nodes if principal_may_view(n.handling, principal, self._scheme)
        ]
        visible_node_ids = {n.id for n in visible_nodes}
        visible_edges = [
            e
            for e in edges
            if principal_may_view(e.handling, principal, self._scheme)
            and e.source in visible_node_ids
            and e.target in visible_node_ids
        ]
        hidden_count = (len(nodes) - len(visible_nodes)) + (len(edges) - len(visible_edges))
        return visible_nodes, visible_edges, hidden_count

    def project_delta(
        self, delta: WorkingSetDelta, principal: Principal
    ) -> tuple[WorkingSetDelta, int]:
        """Re-filters one already-recorded delta for `principal` — the
        replay-on-reconnect path (`sync`) and the live WebSocket push
        (`app.py`'s `_forward_notifications`) both need this: a delta
        recorded when a *different* principal populated the store must
        not reach *this* principal's socket or reconnect catch-up
        verbatim. Returns the filtered delta and how much of it was
        hidden, so a caller handling several deltas at once (`sync`) can
        aggregate one `DeltaNotice` rather than emitting one per delta.
        `DeltaRemove`/`DeltaReproject`/`DeltaNotice` carry nothing
        disclosable and pass through unchanged, hidden count zero."""
        if isinstance(delta, DeltaAdd):
            nodes, edges, hidden = self._project(delta.nodes, delta.edges, principal)
            return delta.model_copy(update={"nodes": nodes, "edges": edges}), hidden
        if isinstance(delta, DeltaSnapshot):
            nodes, edges, hidden = self._project(delta.nodes, delta.edges, principal)
            return (
                delta.model_copy(update={"nodes": nodes, "edges": edges, "filtered_count": hidden}),
                hidden,
            )
        return delta, 0

    async def seed(
        self,
        investigation_id: str,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        principal: Principal,
    ) -> ExpansionOutcome:
        """`POST /seed` (`03_CONDUIT_MIDDLEWARE.md` §3.2) — from a search
        result or saved subgraph. Unlike `expand`, the input here is
        caller-supplied `Node`/`Edge` objects, not the output of a
        `GraphPort` call this service already trusts — so `seed` is the
        one write path that must itself validate the seeding principal
        can see what they are handing in, via the same `_project` used on
        every read. Without this, a principal could write content into a
        store a *different*, later reader is authorised to open that not
        even the seeder themselves could legitimately see: a poisoning
        vector the read-time filter alone does not close, since it only
        ever narrows what a read discloses, never what a write accepts.
        Redaction is not deletion here either (`00_ARCHITECTURE.md` §5):
        anything the seeder submitted but is not entitled to see is
        silently dropped from what gets stored, and `filtered_count`
        reports how much — the same field `expand` uses, same meaning,
        just measured against the caller's own submission instead of
        against `expand_candidate_count`, since there is no single
        `ExpandRequest` scope to ask that about here."""
        visible_nodes, visible_edges, hidden = self._project(nodes, edges, principal)
        return await self._add(
            investigation_id, visible_nodes, visible_edges, filtered_count=hidden
        )

    async def expand(
        self, investigation_id: str, req: ExpandRequest, principal: Principal
    ) -> ExpansionOutcome:
        """`POST /expand`. Two `GraphPort` calls over the *same* `req`:
        the filtered result the analyst receives, and the unfiltered
        candidate count this service is the first authority able to
        compare it against (`01_DOMAIN_MODEL.md` §8.2)."""
        subgraph = await self._graph.expand(req, principal)
        candidate_count = await self._graph.expand_candidate_count(req)
        filtered_count = _filtered_count(candidate_count, len(subgraph.nodes))
        return await self._add(
            investigation_id, subgraph.nodes, subgraph.edges, filtered_count=filtered_count
        )

    async def expand_preview(
        self, investigation_id: str, req: ExpandRequest, principal: Principal
    ) -> CardinalityPreview:
        """`POST /expand/preview` — cardinality only, no mutation
        (`03_CONDUIT_MIDDLEWARE.md` §3.2). Runs the same two `GraphPort`
        calls `expand` does, and the same cap arithmetic, but never calls
        `_add` — nothing is written to the store or appended to the delta
        stream."""
        subgraph = await self._graph.expand(req, principal)
        candidate_count = await self._graph.expand_candidate_count(req)
        filtered_count = _filtered_count(candidate_count, len(subgraph.nodes))

        existing_node_ids = await self._store.node_ids(investigation_id)
        existing_edge_ids = await self._store.edge_ids(investigation_id)
        new_node_count = len({n.id for n in subgraph.nodes} - existing_node_ids)
        new_edge_count = len({e.id for e in subgraph.edges} - existing_edge_ids)

        would_be_nodes = len(existing_node_ids) + new_node_count
        would_be_edges = len(existing_edge_ids) + new_edge_count
        would_breach = _cap_breach(would_be_nodes, would_be_edges)

        return CardinalityPreview(
            candidate_node_count=would_be_nodes,
            candidate_edge_count=would_be_edges,
            filtered_count=filtered_count,
            would_breach=would_breach,
        )

    async def _add(
        self,
        investigation_id: str,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        *,
        filtered_count: int,
    ) -> ExpansionOutcome:
        """`03_CONDUIT_MIDDLEWARE.md` §4: "On breach the service does not
        truncate". The cap check runs — and can raise — *before* any
        write, so a would-be-breaching call never partially lands: it is
        rejected whole, or it succeeds whole, never a silent slice of
        either the requested nodes or the requested edges."""
        existing_node_ids = await self._store.node_ids(investigation_id)
        existing_edge_ids = await self._store.edge_ids(investigation_id)

        new_nodes = [n for n in nodes if n.id not in existing_node_ids]
        new_edges = [e for e in edges if e.id not in existing_edge_ids]

        would_be_nodes = len(existing_node_ids) + len(new_nodes)
        would_be_edges = len(existing_edge_ids) + len(new_edges)
        breach = _cap_breach(would_be_nodes, would_be_edges)
        if breach is not None:
            raise LimitExceededError(breach)

        await self._store.add_nodes(investigation_id, new_nodes)
        await self._store.add_edges(investigation_id, new_edges)

        seq = await self._store.next_seq(investigation_id)
        delta = DeltaAdd(seq=seq, nodes=list(nodes), edges=list(edges))
        await self._store.append_delta(investigation_id, delta)

        return ExpansionOutcome(delta=delta, filtered_count=filtered_count)

    async def branch(
        self, source_investigation_id: str, new_investigation_id: str, principal: Principal
    ) -> ExpansionOutcome:
        """`POST /investigations/{id}/branch` — one of the cap breach's
        three options made real: "fork the working set into a new
        investigation" (`03_CONDUIT_MIDDLEWARE.md` §3.1). Copies only
        what `principal` (the branching principal) can see from the
        source's source-fidelity set into `new_investigation_id`, filtered
        the same way any other read is — you cannot fork what you cannot
        see, and the source may hold content only a *different*,
        more-privileged principal ever contributed. A branch is a
        snapshot at the moment it forks, not a live link back to the
        source, so later expansion of either side never touches the
        other."""
        nodes = await self._store.source_fidelity_nodes(source_investigation_id)
        edges = await self._store.source_fidelity_edges(source_investigation_id)
        visible_nodes, visible_edges, hidden = self._project(
            list(nodes.values()), list(edges.values()), principal
        )
        return await self._add(
            new_investigation_id, visible_nodes, visible_edges, filtered_count=hidden
        )

    async def current_membership(self, investigation_id: str) -> tuple[list[Node], list[Edge]]:
        """The full source-fidelity (unfiltered) membership — `app.py`'s
        history step recording calls this right after any mutation, so a
        step captures what actually exists in the working set, not one
        principal's filtered view of it. Deliberately unfiltered: `restore`
        re-projects fresh against whoever is restoring, and cannot do that
        correctly from a body that was already filtered for someone else
        (`history.py`'s module docstring)."""
        nodes = await self._store.source_fidelity_nodes(investigation_id)
        edges = await self._store.source_fidelity_edges(investigation_id)
        return list(nodes.values()), list(edges.values())

    async def restore(
        self,
        investigation_id: str,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        principal: Principal,
    ) -> DeltaSnapshot:
        """`POST /history/{step}` (`03_CONDUIT_MIDDLEWARE.md` §3.1):
        replaces the working set's current membership with a previously
        recorded step's stored bodies, re-projecting the handling filter
        fresh against `principal` — never reinstating whatever was visible
        when the step was written, since a principal's access may have
        narrowed since, or a different, less-privileged principal on a
        shared investigation may be the one restoring
        (`history.py`'s module docstring; `tests/services/api/
        test_history.py`'s narrower-clearance-restore case is the proof).

        Never calls `store.clear()` — that would also drop the seq
        counter, and a restore's `DeltaSnapshot` must carry the *next*
        monotonic seq, continuing the same sequence every other delta
        does, not restart it. Both nodes and edges are reconciled the same
        way instead: whatever is no longer in the target set is removed
        (`remove_nodes`/`remove_edges`), then the target set is re-added
        (`add_nodes`/`add_edges` are upserts). Edges need this exactly as
        much as nodes do — an edge added *after* the step was recorded,
        between two nodes both still present at that step, has both
        endpoints intact and would never be excluded by `_project`'s
        endpoint check, so without an explicit `remove_edges` pass it
        would silently survive a restore that is supposed to erase it."""
        visible_nodes, visible_edges, hidden = self._project(nodes, edges, principal)

        existing_node_ids = await self._store.node_ids(investigation_id)
        target_node_ids = {n.id for n in visible_nodes}
        stale_node_ids = existing_node_ids - target_node_ids
        if stale_node_ids:
            await self._store.remove_nodes(investigation_id, list(stale_node_ids))

        existing_edge_ids = await self._store.edge_ids(investigation_id)
        target_edge_ids = {e.id for e in visible_edges}
        stale_edge_ids = existing_edge_ids - target_edge_ids
        if stale_edge_ids:
            await self._store.remove_edges(investigation_id, list(stale_edge_ids))

        await self._store.add_nodes(investigation_id, visible_nodes)
        await self._store.add_edges(investigation_id, visible_edges)

        seq = await self._store.next_seq(investigation_id)
        snapshot = DeltaSnapshot(
            seq=seq, nodes=visible_nodes, edges=visible_edges, filtered_count=hidden
        )
        await self._store.append_delta(investigation_id, snapshot)
        return snapshot

    async def remove(self, investigation_id: str, node_ids: Sequence[NodeId]) -> int:
        """`DELETE /nodes` — "remove from the working set (not from the
        Vault)" (`03_CONDUIT_MIDDLEWARE.md` §3.2). Removal never breaches a
        cap, so there is no check to run here — only the delta to record."""
        await self._store.remove_nodes(investigation_id, node_ids)
        seq = await self._store.next_seq(investigation_id)
        delta = DeltaRemove(seq=seq, node_ids=list(node_ids))
        await self._store.append_delta(investigation_id, delta)
        return seq

    async def sync(
        self, investigation_id: str, principal: Principal, *, last_acknowledged_seq: int | None
    ) -> list[WorkingSetDelta]:
        """The reconnect decision (`03_CONDUIT_MIDDLEWARE.md` §3.2): a
        client with no prior sequence (`last_acknowledged_seq is None`, a
        first connect) or one whose last-seen sequence has fallen off the
        capped delta stream gets a full `DeltaSnapshot`. A client that is
        merely behind gets exactly the deltas it missed, in order — never
        a patch attempt when the gap can't be proven closed. This is what
        makes "disconnects mid-stream, reconnects and arrives at a
        byte-identical set" true regardless of how long the gap was —
        **for `principal`'s own view of it**: every delta returned here is
        re-projected via `project_delta` before it leaves this method,
        since the stream may hold entries a *different* principal
        originally populated (§4's per-read handling filter). A single
        aggregate `DeltaNotice` reports however much this call hid, rather
        than one notice per re-filtered delta."""
        if last_acknowledged_seq is not None:
            raw_deltas = await self._store.deltas_after(investigation_id, last_acknowledged_seq)
            if raw_deltas is not None:
                projected: list[WorkingSetDelta] = []
                hidden_total = 0
                for raw in raw_deltas:
                    delta, hidden = self.project_delta(raw, principal)
                    projected.append(delta)
                    hidden_total += hidden
                if hidden_total > 0:
                    top_seq = projected[-1].seq
                    projected.append(
                        DeltaNotice(
                            seq=top_seq,
                            message=f"{hidden_total} item(s) withheld by handling policy",
                            count=hidden_total,
                        )
                    )
                return projected

        nodes = await self._store.source_fidelity_nodes(investigation_id)
        edges = await self._store.source_fidelity_edges(investigation_id)
        seq = await self._store.current_seq(investigation_id)
        visible_nodes, visible_edges, hidden = self._project(
            list(nodes.values()), list(edges.values()), principal
        )
        return [
            DeltaSnapshot(
                seq=seq,
                nodes=visible_nodes,
                edges=visible_edges,
                filtered_count=hidden,
            )
        ]


def _cap_breach(would_be_nodes: int, would_be_edges: int) -> LimitExceeded | None:
    """Nodes are checked before edges: `03_CONDUIT_MIDDLEWARE.md` §4 names
    "50,000 nodes, 250,000 edges" in that order, and a request that would
    breach both reports the node cap — the more fundamental of the two,
    since a working set is edgeless without its nodes."""
    if would_be_nodes > MAX_NODES:
        return LimitExceeded(cap_kind="nodes", cap=MAX_NODES, would_be=would_be_nodes)
    if would_be_edges > MAX_EDGES:
        return LimitExceeded(cap_kind="edges", cap=MAX_EDGES, would_be=would_be_edges)
    return None
