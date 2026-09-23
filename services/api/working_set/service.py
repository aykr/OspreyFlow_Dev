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

import json
from collections.abc import Sequence
from typing import Any

from services.api.access import narrow_to_visible
from services.api.change_stream import ChangeStreamEntry, ChangeStreamWriter
from services.resolve.projection import DEFAULT_THRESHOLD, compute_clusters, diff_clusters
from valkey.asyncio import Valkey

from conduit_common.identity import new_edge_id, now_utc
from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from schemas.domain import (
    NOT_SAME_AS,
    SAME_AS,
    AuditStub,
    ClusterId,
    Edge,
    EdgeWrite,
    ExpandRequest,
    Node,
    NodeId,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .models import (
    MAX_EDGES,
    MAX_NODES,
    CardinalityPreview,
    ClusterExplanation,
    ClusterNotFoundError,
    DeltaAdd,
    DeltaNotice,
    DeltaRemove,
    DeltaReproject,
    DeltaSnapshot,
    ExpansionOutcome,
    LimitExceeded,
    LimitExceededError,
    NodeNotInWorkingSetError,
    PairwiseExplanation,
    SameNodeAssertionError,
    WorkingSetDelta,
)
from .store import WorkingSetStorage


def _decode_comparison_vector(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    result: dict[str, Any] = json.loads(raw)
    return result


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
        self,
        graph: GraphPort,
        store: WorkingSetStorage,
        handling_scheme: HandlingScheme,
        *,
        valkey: Valkey | None = None,
    ) -> None:
        self._graph = graph
        self._store = store
        self._scheme = handling_scheme
        # Optional, default `None` — every existing test constructing this service directly keeps
        # working unchanged; `app.py`'s own production wiring passes the real client. When given,
        # a manual `SAME_AS`/`NOT_SAME_AS` write publishes to the corpus-wide change stream
        # (`06_DECISIONS.md` ADR-037's own amendment names manual assertion, B11's mechanism, as
        # one of its three accepted producers — `services/api/change_stream.py`'s own docstring).
        self._valkey = valkey

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

    async def get_resolution_threshold(self, investigation_id: str) -> float:
        """`GET /v1/resolution/threshold` (`03_CONDUIT_MIDDLEWARE.md` §3.5). `None` in the store
        means no `PUT` has ever run for this investigation — `DEFAULT_THRESHOLD` (Balanced, 0.95,
        `01_DOMAIN_MODEL.md` §4's three detents) is the session's starting point, not a stored
        value that happens to equal it."""
        stored = await self._store.get_threshold(investigation_id)
        return stored if stored is not None else DEFAULT_THRESHOLD

    async def set_resolution_threshold(
        self, investigation_id: str, tau: float, principal: Principal
    ) -> DeltaReproject:
        """`PUT /v1/resolution/threshold` (`03_CONDUIT_MIDDLEWARE.md` §3.5, §4): "resolution
        collapse at the session's τ" re-projected against the *full* source-fidelity node set —
        not merely the nodes a single prior `expand()` happened to include — since a threshold
        change can affect any two nodes currently in the working set, not only ones a specific
        delta touched.

        Resolution edges are fetched via the same `GraphPort.expand()` every other read uses,
        scoped to `SAME_AS`/`NOT_SAME_AS` via `ExpandRequest.edge_types` — no new `GraphPort`
        method needed, and the same access filter every other read already goes through
        (`03_CONDUIT_MIDDLEWARE.md` §6: "Filtering in the Conduit after retrieval is forbidden").

        The delta this returns/records carries the three summary counts `01_DOMAIN_MODEL.md` §4's
        own example gives ("3 entities merged, 1 split, 47 nodes affected") plus, since Phase 6a
        Stage 2, the affected nodes' own new cluster ids (`DeltaReproject.affected_cluster_ids`) —
        never the full working set, bounded by `affected` — so a client can update cluster
        rendering in place instead of re-fetching via `sync`/`current_membership` on every move.

        `node_ids` is narrowed to `principal`'s own visible subset of the investigation-shared
        population before either `compute_clusters` call — access control lives in the adapter.
        `source_fidelity_
        nodes` is investigation-shared, not scoped to this caller's clearance (the same fact
        `_manual_assertion` documents). Checked precisely: this does *not* leak through the
        `merged`/`split`/`affected` counts themselves — `GraphPort.expand` already excludes any
        edge with either endpoint hidden from `principal` (`test_projection_access_control.py`),
        so a node this principal cannot see always arrives with no edges and sits in
        `compute_clusters`' union-find as an untouched singleton at every τ, never registering as
        affected. What an unfiltered population actually breaks is the *write*: `compute_clusters`
        returns a full mapping over whatever ids it is given, and persisting that mapping for a
        hidden node would silently reset its own `resolution.cluster_id` — collapsing state a
        better-cleared principal legitimately established — purely because this principal called
        this endpoint. Narrowing to the visible subset closes that write path, not a read leak.
        `expand`'s own access-filtered seed query (`render_seed_nodes_gremlin`) already returns
        exactly the principal-visible subset of any seed list, including a seed with no matching
        edges at all, so intersecting the requested `node_ids` with `subgraph.nodes`'
        own ids is sufficient — no separate `get_node` round trip per node is needed the way
        `_manual_assertion` needs one per *named* node, because here the full candidate set is
        already the thing being visibility-checked in bulk. Narrowing itself is
        `services/api/access.py`'s `narrow_to_visible` — shared with `explain_cluster` below and,
        since Phase 6a Stage 4, the Dossier's own assembly, rather than a third independent copy
        of this exact pattern."""
        old_tau = await self.get_resolution_threshold(investigation_id)
        nodes_by_id = await self._store.source_fidelity_nodes(investigation_id)
        node_ids = list(nodes_by_id.keys())

        result = await narrow_to_visible(
            self._graph, node_ids, principal, edge_types=[SAME_AS, NOT_SAME_AS]
        )
        visible_ids = list(result.nodes.keys())
        same_as_edges = [e for e in result.edges if e.type == SAME_AS]
        not_same_as_edges = [e for e in result.edges if e.type == NOT_SAME_AS]

        before = compute_clusters(visible_ids, same_as_edges, not_same_as_edges, old_tau)
        after = compute_clusters(visible_ids, same_as_edges, not_same_as_edges, tau)
        delta_counts = diff_clusters(before, after)

        updated_nodes = [
            node.model_copy(
                update={
                    "resolution": node.resolution.model_copy(update={"cluster_id": after[node_id]})
                }
            )
            for node_id, node in nodes_by_id.items()
            if node_id in after
        ]
        if updated_nodes:
            await self._store.add_nodes(investigation_id, updated_nodes)
        await self._store.set_threshold(investigation_id, tau)

        seq = await self._store.next_seq(investigation_id)
        delta = DeltaReproject(
            seq=seq,
            reason=f"resolution threshold changed from {old_tau} to {tau}",
            merged=delta_counts.merged,
            split=delta_counts.split,
            affected=delta_counts.nodes_affected,
            affected_cluster_ids=delta_counts.affected_cluster_ids,
        )
        await self._store.append_delta(investigation_id, delta)
        return delta

    async def manual_link(
        self, investigation_id: str, node_a: NodeId, node_b: NodeId, principal: Principal
    ) -> tuple[DeltaReproject, ChangeStreamEntry | None]:
        """`POST /v1/resolution/link` (`03_CONDUIT_MIDDLEWARE.md` §3.5): "analyst-asserted
        `SAME_AS`" — `01_DOMAIN_MODEL.md` §4: "a manual link is a `SAME_AS` with score 1.0 and
        `provenance.state = asserted`." Only `score` is set on the new edge: `model_version`/
        `comparison_vector` are Splink's own output fields (`01_DOMAIN_MODEL.md` §4), and a manual
        decision was not produced by any model run — leaving them unset rather than inventing a
        placeholder value keeps `explain`'s `manually_asserted` flag the one honest signal for
        "why is this pair linked", not a fabricated model tag.

        Returns the change-stream entry `_manual_assertion` published alongside the reprojection
        (Phase 7 Stage 6c) — `app.py`'s `link_resolution_route` is the one caller with a live
        principal in scope to evaluate hotlists/monitors against it; `manual_split` below returns
        the identical shape for interface consistency, but a `NOT_SAME_AS` write can only shrink a
        pattern's match set (`06_DECISIONS.md` ADR-037's own "removing an edge can only shrink a
        match set, never grow it"), so nothing calls evaluation from that route."""
        return await self._manual_assertion(
            investigation_id,
            node_a,
            node_b,
            principal,
            edge_type=SAME_AS,
            properties={"score": 1.0},
            reason="link",
        )

    async def manual_split(
        self, investigation_id: str, node_a: NodeId, node_b: NodeId, principal: Principal
    ) -> tuple[DeltaReproject, ChangeStreamEntry | None]:
        """`POST /v1/resolution/split` (`03_CONDUIT_MIDDLEWARE.md` §3.5): "analyst-asserted
        `NOT_SAME_AS`" — `01_DOMAIN_MODEL.md` §4: "a manual split is a `NOT_SAME_AS` edge that the
        projection always honours and no future resolution run may override." `compute_clusters`
        already enforces the "always honours" half (`projection.py`'s own docstring;
        `test_a_manual_split_survives_even_at_a_broad_threshold` is the proof); the "no future run
        may override" half is `services/resolve/conflicts.py`'s job, once a corpus-wide resolution
        run actually happens — recording, not silently re-merging, is that module's whole point."""
        return await self._manual_assertion(
            investigation_id,
            node_a,
            node_b,
            principal,
            edge_type=NOT_SAME_AS,
            properties={},
            reason="split",
        )

    async def _manual_assertion(
        self,
        investigation_id: str,
        node_a: NodeId,
        node_b: NodeId,
        principal: Principal,
        *,
        edge_type: str,
        properties: dict[str, Any],
        reason: str,
    ) -> tuple[DeltaReproject, ChangeStreamEntry | None]:
        if node_a == node_b:
            raise SameNodeAssertionError(node_a)

        nodes_by_id = await self._store.source_fidelity_nodes(investigation_id)
        if node_a not in nodes_by_id or node_b not in nodes_by_id:
            raise NodeNotInWorkingSetError(f"{node_a}, {node_b}")

        # `source_fidelity_nodes` is the *investigation-shared* set (`WorkingSetStorage`'s own
        # docstring: "one Valkey hash per investigation"), not a projection scoped to this specific
        # caller's own clearance — two principals can share one investigation at different
        # clearances, both passing `AuthorizedInvestigationDep` via the same `org_unit`. Membership
        # in that shared dict is necessary but not sufficient: re-verify both nodes are visible to
        # *this* principal specifically, via the same principal-scoped `GraphPort.get_node` every
        # other read already goes through, before writing a permanent edge naming them. `None`
        # here is indistinguishable from "not in the working set" — the same existence-leak
        # discipline the route already applies to `NodeNotInWorkingSetError`, extended to a write
        # no silent-truncation exception applies to.
        if await self._graph.get_node(node_a, principal) is None:
            raise NodeNotInWorkingSetError(node_a)
        if await self._graph.get_node(node_b, principal) is None:
            raise NodeNotInWorkingSetError(node_b)

        node_ids = list(nodes_by_id.keys())
        tau = await self.get_resolution_threshold(investigation_id)

        # Same narrowing `set_resolution_threshold` applies, and for the same reason: this
        # investigation-shared `node_ids` list is not scoped to `principal`'s own clearance. The
        # `node_a`/`node_b` check above proves those two specific nodes are visible; it says
        # nothing about the rest of the population `compute_clusters` runs over. Per that method's
        # own docstring, this is a write-path fix, not a read leak: `merged`/`split`/`affected`
        # can't be inflated by a hidden node with no visible edges (it's an untouched singleton at
        # every τ), but persisting `compute_clusters`' output unfiltered would still let this call
        # silently reset a hidden node's own stored `cluster_id`.
        resolution_edges: list[Edge] = []
        visible_ids: list[NodeId] = []
        if node_ids:
            subgraph = await self._graph.expand(
                ExpandRequest(node_ids=node_ids, depth=1, edge_types=[SAME_AS, NOT_SAME_AS]),
                principal,
            )
            resolution_edges = subgraph.edges
            visible = {n.id for n in subgraph.nodes}
            visible_ids = [node_id for node_id in node_ids if node_id in visible]
        same_as_edges = [e for e in resolution_edges if e.type == SAME_AS]
        not_same_as_edges = [e for e in resolution_edges if e.type == NOT_SAME_AS]
        before = compute_clusters(visible_ids, same_as_edges, not_same_as_edges, tau)

        now = now_utc()
        new_edge = Edge(
            id=new_edge_id(),
            type=edge_type,
            source=node_a,
            target=node_b,
            properties=properties,
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[
                    SourceRef(
                        document_id=f"manual:{node_a}:{node_b}",
                        locator=principal.id,
                        excerpt_hash="",
                    )
                ],
                first_seen=now,
            ),
            handling=nodes_by_id[node_a].handling,
            audit=AuditStub(created_at=now, created_by=principal.id),
        )
        edge_write = EdgeWrite(
            id=new_edge.id,
            type=edge_type,
            source=node_a,
            target=node_b,
            properties=properties,
            provenance=new_edge.provenance,
            handling=new_edge.handling,
            created_by=principal.id,
            created_at=now,
        )

        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_edges([edge_write], tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)

        entry: ChangeStreamEntry | None = None
        if self._valkey is not None:
            entry = await ChangeStreamWriter(self._valkey).publish(
                "manual_assertion", edge_ids=[new_edge.id], investigation_id=investigation_id
            )

        if edge_type == SAME_AS:
            same_as_edges = [*same_as_edges, new_edge]
        else:
            not_same_as_edges = [*not_same_as_edges, new_edge]
        after = compute_clusters(visible_ids, same_as_edges, not_same_as_edges, tau)
        delta_counts = diff_clusters(before, after)

        updated_nodes = [
            node.model_copy(
                update={
                    "resolution": node.resolution.model_copy(update={"cluster_id": after[node_id]})
                }
            )
            for node_id, node in nodes_by_id.items()
            if node_id in after
        ]
        if updated_nodes:
            await self._store.add_nodes(investigation_id, updated_nodes)

        seq = await self._store.next_seq(investigation_id)
        delta = DeltaReproject(
            seq=seq,
            reason=f"manual {reason} between {node_a} and {node_b}",
            merged=delta_counts.merged,
            split=delta_counts.split,
            affected=delta_counts.nodes_affected,
            affected_cluster_ids=delta_counts.affected_cluster_ids,
        )
        await self._store.append_delta(investigation_id, delta)
        return delta, entry

    async def explain_cluster(
        self, investigation_id: str, cluster_id: ClusterId, principal: Principal
    ) -> ClusterExplanation:
        """`GET /v1/resolution/explain/{cluster}` (`03_CONDUIT_MIDDLEWARE.md` §3.5): "the
        comparison vector and score that produced a cluster... Return the per-comparison match
        weights, not just the total." Reads the working set's *last-computed*
        `resolution.cluster_id` annotation — `set_resolution_threshold`/`manual_link`/
        `manual_split` are the only writers of it — rather than recomputing clusters fresh, so
        what an analyst sees explained is exactly the clustering their session is currently
        showing, not whatever a threshold that happens to be current right now would produce.

        Found alongside Phase 6a Stage 2's own `set_resolution_threshold` gap, same cause: this
        route names a `cluster_id`, not individual nodes, so nothing upstream of this method had
        ever checked that every member of that cluster is visible to `principal` — a lower-
        clearance principal naming a cluster containing a hidden node would previously get that
        node's own id back directly in `member_node_ids`, worse than an aggregate-count leak. The
        candidate membership (from investigation-shared, unfiltered `source_fidelity_nodes`) is
        narrowed to `expand`'s own principal-filtered result before being returned, the same
        pattern as `set_resolution_threshold`; an empty result after narrowing raises
        `ClusterNotFoundError`, indistinguishable from the cluster never having existed, per
        the same existence-leak discipline access control must hold to."""
        nodes_by_id = await self._store.source_fidelity_nodes(investigation_id)
        candidate_ids = {
            node_id
            for node_id, node in nodes_by_id.items()
            if node.resolution.cluster_id == cluster_id
        }
        if not candidate_ids:
            raise ClusterNotFoundError(cluster_id)

        tau = await self.get_resolution_threshold(investigation_id)
        result = await narrow_to_visible(
            self._graph, list(candidate_ids), principal, edge_types=[SAME_AS, NOT_SAME_AS]
        )
        resolution_edges = result.edges
        member_ids = set(result.nodes.keys())
        if not member_ids:
            raise ClusterNotFoundError(cluster_id)

        pairs = [
            PairwiseExplanation(
                node_a=edge.source,
                node_b=edge.target,
                edge_type=edge.type,  # type: ignore[arg-type]
                score=edge.properties.get("score"),
                model_version=edge.properties.get("model_version"),
                comparison_vector=_decode_comparison_vector(
                    edge.properties.get("comparison_vector")
                ),
                manually_asserted=edge.provenance.state == ProvenanceState.ASSERTED,
                meets_threshold=(edge.properties.get("score") or 0.0) >= tau,
            )
            for edge in resolution_edges
            if edge.source in member_ids and edge.target in member_ids
        ]
        return ClusterExplanation(
            cluster_id=cluster_id, member_node_ids=sorted(member_ids), pairs=pairs
        )

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

    async def withheld_count_for(self, investigation_id: str, principal: Principal) -> int:
        """The export gate's own trusted source for the withheld-item manifest
        (`06_DECISIONS.md` ADR-045, `services/api/export.py::submit_export`) — computed here,
        server-side against `principal`'s own current access over the investigation's real,
        unfiltered membership, never accepted from a client submission. The identical arithmetic
        `_project` already uses for the status bar's own "N hidden by handling" figure
        (`02_GLASS_FRONTEND.md` §2) and every delta this service emits, reused rather than a second
        count invented for export: an artefact's own manifest should say the same thing the status
        bar already told this analyst all session, not a second, independently-computed number
        that could drift from it. A client-supplied count would let an artefact state that nothing
        was withheld when items were — an active misstatement of completeness, not merely an
        omission, which is a materially worse failure than the leak ADR-045's own `disclose`
        default already accepts the cost of."""
        nodes, edges = await self.current_membership(investigation_id)
        _, _, hidden = self._project(nodes, edges, principal)
        return hidden

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
