"""The Working-Set Service's orchestration — `spec/03_CONDUIT_MIDDLEWARE.md`
§4, "the most important component in the Conduit". Owns four things
nothing else in the platform can safely do on its own: the cap check that
never truncates (counted over the reader's own projected view, ADR-124 decision 2),
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

No count of what a reader may not read leaves this class (ADR-124 decision 1): a figure tied to a
seed, a link type or a colleague's action can be made to point at the one item it counts. The caps
are the same: each is counted over `_project` of the stored set for the reader asking, plus what the
request adds, so a stored item the reader may not read moves no figure they are shown.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from services.api.access import narrow_to_visible
from services.api.cache import principal_class
from services.api.change_stream import ChangeStreamEntry, ChangeStreamWriter
from services.resolve.projection import DEFAULT_THRESHOLD, compute_clusters, diff_clusters
from valkey.asyncio import Valkey

from conduit_common.identity import new_edge_id, now_utc
from ontology.errors import HandlingSchemeError
from ontology.handling import HandlingScheme, principal_may_read, principal_may_view
from ports.graph import GraphPort
from schemas.domain import (
    CONNECTIONS_SHOWN,
    NOT_SAME_AS,
    SAME_AS,
    AuditStub,
    ClusterId,
    Edge,
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    Node,
    NodeId,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .access_index import ABSENT, AccessEntries, AccessSignature
from .models import (
    MAX_EDGES,
    MAX_NODES,
    CardinalityPreview,
    ClusterExplanation,
    ClusterNotFoundError,
    DeltaAdd,
    DeltaRemove,
    DeltaRemoveSent,
    DeltaReplaceEdge,
    DeltaReplaceEdgeSent,
    DeltaReproject,
    DeltaSnapshot,
    ExpansionOutcome,
    LimitExceeded,
    LimitExceededError,
    LinksAmongOutcome,
    NodeNotInWorkingSetError,
    NothingToBranchError,
    PairwiseExplanation,
    RemovedElement,
    RemovedRecord,
    ResolutionOutcome,
    SameNodeAssertionError,
    WorkingSetDelta,
    WorkingSetDeltaSent,
)
from .store import WorkingSetStorage


def _decode_comparison_vector(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    result: dict[str, Any] = json.loads(raw)
    return result


#: ADR-124 decision 4: the only two reasons a `DeltaReproject` is sent with. What the service stores
#: is one of them too; an older entry may hold prose that names ids, and is sent as the threshold.
REASON_THRESHOLD = "resolution_threshold"
REASON_MANUAL = "manual_resolution"

#: ADR-098 decision 1: an expansion that adds at most this many new nodes, into a view of at most
#: `AUTO_LINKS_MAX_VIEW_NODES`, also brings the links among its nodes and the view. Beyond either,
#: the canvas offers *Show links among these*.
AUTO_LINKS_MAX_NEW_NODES = 100
AUTO_LINKS_MAX_VIEW_NODES = 2_000

#: How many readable-signature sets one service keeps (`WorkingSetService._reader_counts`). Each is
#: a handful of short keys, so the bound is only a bound.
READABLE_CACHE_SIZE = 256

#: How many ids one membership read of the counted index takes (`_ReaderCounts.visible_among`).
_MEMBERSHIP_CHUNK = 5_000


class _SignaturesRenumbered(Exception):
    """The entries were read at another epoch than the signature table they would be judged by."""


@dataclass
class _ReaderCounts:
    """One reader's figures for a case, read at one moment (ADR-124 decision 2, Amendment 4): how
    many nodes and links are in their projected view, and what is needed to say whether some named
    ids are. Never the view itself: nothing the caps and previews need is the whole set.

    `readable` is the signature keys in use (a node or a link carries them) that the reader may
    read; `nodes` and `edges` are the sums of the store's counts over them (a link counts when its
    own signature and both ends' are readable, and an end that is not stored never is).
    `judgements` is the memo of which signature keys the reader may read, shared with the service's
    cache; a signature is judged when something carries it and not before.

    `epoch` is the epoch the signature table was read at. A rebuild that renumbers the signatures
    replaces it, and the numbers in entries read afterwards name other signatures than this table
    does; `would_add` notices (the entries carry the epoch they were read at), calls `reload`,
    which reads the counts again and replaces `signatures`, `readable`, `nodes` and `edges` here,
    and starts over. Callers read `nodes` and `edges` after `would_add`, never before."""

    store: WorkingSetStorage
    case: str
    principal: Principal
    scheme: HandlingScheme
    signatures: Mapping[str, AccessSignature]
    judgements: dict[str, bool]
    readable: frozenset[str]
    nodes: int
    edges: int
    epoch: str = ""
    reload: Callable[[], Awaitable[None]] | None = None

    def is_readable(self, key: str | None) -> bool:
        """Whether the reader may read signature `key`; one the store has no definition for (a
        signature stored since the counts were read) is not."""
        if key is None or key not in self.signatures:
            return False
        if key not in self.judgements:
            signature = self.signatures[key]
            self.judgements[key] = principal_may_read(
                signature.handling(), list(signature.datasets), self.principal, self.scheme
            )
        return self.judgements[key]

    def visibly_stored(self, entries: AccessEntries) -> tuple[set[NodeId], set[EdgeId]]:
        """Of the ids `entries` was read for, those in the reader's view now: a node whose
        signature they may read, a link whose own and both ends' signatures they may read."""
        nodes = {i for i, sig in entries.nodes.items() if self.is_readable(sig)}
        edges = {
            i
            for i, (sig, source, target) in entries.edges.items()
            if self.is_readable(sig)
            and self.is_readable(entries.ends.get(source))
            and self.is_readable(entries.ends.get(target))
        }
        return nodes, edges

    async def would_add(
        self,
        node_ids: Iterable[NodeId],
        edge_ids: Iterable[EdgeId],
        nodes: Iterable[Node] = (),
    ) -> tuple[int, int, AccessEntries]:
        """How many of these ids are not yet in the reader's view, and the entries they were judged
        by (also what says which of them the store holds at all).

        **A node the store does not hold completes the links stored at it.** Removing a node leaves
        its links stored with that end `absent`; when the node comes back they join the view
        whether or not the request names them. For each such new node the links at it are read
        (the adjacency holds them whether or not the node is stored), and each that the reader may
        read, whose other end is stored and readable or is one of the new nodes, is counted too
        (once, and not again if the request names it). `nodes` gives the bodies of the new nodes,
        which says whether a new node is readable; an id with no body is taken to be.

        **A renumbering between the counts and the entries** is met by reading the counts again
        and starting over, once; a second one raises (nothing is served from a table that keeps
        changing)."""
        for attempt in (0, 1):
            try:
                return await self._would_add_once(node_ids, edge_ids, nodes)
            except _SignaturesRenumbered:
                if attempt or self.reload is None:
                    raise
                await self.reload()
        raise AssertionError("unreachable")  # pragma: no cover

    async def _entries(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId]
    ) -> AccessEntries:
        entries = await self.store.access_entries(self.case, node_ids, edge_ids)
        if entries.epoch != self.epoch:
            raise _SignaturesRenumbered
        return entries

    async def _would_add_once(
        self,
        node_ids: Iterable[NodeId],
        edge_ids: Iterable[EdgeId],
        nodes: Iterable[Node],
    ) -> tuple[int, int, AccessEntries]:
        node_list = list(dict.fromkeys(node_ids))
        edge_list = list(dict.fromkeys(edge_ids))
        entries = await self._entries(node_list, edge_list)
        visible_nodes, visible_edges = self.visibly_stored(entries)
        new_edges = len(edge_list) - len(visible_edges)
        arriving = [n for n in node_list if n not in entries.nodes]
        if arriving:
            bodies = {n.id: n for n in nodes}
            arriving_readable = {
                n: (
                    principal_may_read(
                        bodies[n].handling, bodies[n].datasets, self.principal, self.scheme
                    )
                    if n in bodies
                    else True
                )
                for n in arriving
            }
            at = await self.store.adjacent_edge_ids(self.case, arriving)
            completed_ids = sorted({e for es in at.values() for e in es} - set(edge_list))
            if completed_ids:
                links = await self._entries([], completed_ids)
                for sig, source, target in links.edges.values():
                    if self.is_readable(sig) and all(
                        arriving_readable[end]
                        if end in arriving_readable
                        else self.is_readable(links.ends.get(end))
                        for end in (source, target)
                    ):
                        new_edges += 1
        return len(node_list) - len(visible_nodes), new_edges, entries

    async def visibly_stored_among(self, node_ids: Iterable[NodeId]) -> set[NodeId]:
        """Of the named ids, those the store holds and the reader may read: the membership read of
        the counted access index, one entry per id asked about (ADR-124 decision 3). An id the store
        holds but the reader may not read is not in the result, exactly as one it does not hold is
        not: nothing downstream can tell them apart."""
        nodes, _ = await self.visible_among(node_ids, ())
        return nodes

    async def visible_among(
        self, node_ids: Iterable[NodeId], edge_ids: Iterable[EdgeId]
    ) -> tuple[set[NodeId], set[EdgeId]]:
        """Of the named node and link ids, those in the reader's view now: a node whose signature
        they may read, a link whose own and both ends' signatures they may read, an end that is not
        stored never. Read from the counted index in chunks (`_MEMBERSHIP_CHUNK` ids to a read), so
        that a restore's whole case is a bounded number of reads and no body. A renumbering met
        between the counts and the entries is handled as `would_add` handles it."""
        nodes: set[NodeId] = set()
        edges: set[EdgeId] = set()
        node_list = list(dict.fromkeys(node_ids))
        edge_list = list(dict.fromkeys(edge_ids))
        for start in range(0, len(node_list), _MEMBERSHIP_CHUNK):
            chunk = node_list[start : start + _MEMBERSHIP_CHUNK]
            nodes |= (await self._visible_chunk(chunk, []))[0]
        for start in range(0, len(edge_list), _MEMBERSHIP_CHUNK):
            chunk = edge_list[start : start + _MEMBERSHIP_CHUNK]
            edges |= (await self._visible_chunk([], chunk))[1]
        return nodes, edges

    async def _visible_chunk(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId]
    ) -> tuple[set[NodeId], set[EdgeId]]:
        for attempt in (0, 1):
            try:
                entries = await self._entries(node_ids, edge_ids)
            except _SignaturesRenumbered:
                if attempt or self.reload is None:
                    raise
                await self.reload()
            else:
                return self.visibly_stored(entries)
        raise AssertionError("unreachable")  # pragma: no cover

    async def visible_node_ids(self) -> set[NodeId]:
        """The ids of the reader's visible nodes. Only for a view the counts have shown to be
        small (`expand` asks the graph for the links among them): reads the store's node entries."""
        return {
            node_id
            for node_id, sig in (await self.store.stored_node_signatures(self.case)).items()
            if self.is_readable(sig)
        }


@dataclass(frozen=True)
class Restored:
    """What a restore makes: the snapshot that is stored and published, which every reader projects
    to their own view (ADR-124 decision 6), and the restorer's own response, which is that snapshot
    projected for the restorer and never the stored whole."""

    published: DeltaSnapshot
    response: DeltaSnapshot


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
        #: Which signatures a reader may read, by (case, epoch, signatures version, access class):
        #: see `_reader_counts`. Per service, never shared between processes or between stores.
        self._readable: OrderedDict[tuple[str, str, int, str], dict[str, bool]] = OrderedDict()

    def _project(
        self,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        principal: Principal,
        known: Mapping[NodeId, Node] | None = None,
    ) -> tuple[list[Node], list[Edge], int]:
        """The read-time handling filter `03_CONDUIT_MIDDLEWARE.md` §4
        requires. An edge is visible only if both its own handling block
        clears *and* both endpoints are among the visible nodes — an edge
        whose handling alone would pass but which points at a node this
        principal cannot see would itself disclose that hidden node's
        existence, exactly the leak `principal_may_view` exists to
        prevent at node level."""
        # A link's ends are judged against `nodes` and, where given, the rest of the working set
        # (`known`): a delta replayed or pushed alone carries only its own nodes, and a link from
        # one of them to a node already on the canvas is the reader's to see (9 October 2026: it was
        # dropped as though hidden). A link whose end is in neither has left the view: it is left
        # out, since nothing is withheld from the reader by it.
        ends = {**(known or {}), **{n.id: n for n in nodes}}
        readable = {
            node_id
            for node_id, n in ends.items()
            if principal_may_read(n.handling, n.datasets, principal, self._scheme)
        }
        visible_nodes = [n for n in nodes if n.id in readable]
        visible_edges: list[Edge] = []
        hidden_edges = 0
        for e in edges:
            if e.source not in ends or e.target not in ends:
                continue
            if (
                principal_may_read(e.handling, e.datasets, principal, self._scheme)
                and e.source in readable
                and e.target in readable
            ):
                visible_edges.append(e)
            else:
                hidden_edges += 1
        hidden_count = (len(nodes) - len(visible_nodes)) + hidden_edges
        return visible_nodes, visible_edges, hidden_count

    def project_delta(
        self,
        delta: WorkingSetDelta,
        principal: Principal,
        known: Mapping[NodeId, Node] | None = None,
    ) -> WorkingSetDeltaSent:
        """Re-filters one already-recorded delta for `principal` — the
        replay-on-reconnect path (`sync`) and the live WebSocket push
        (`app.py`'s `_forward_notifications`) both need this: a delta
        recorded when a *different* principal populated the store must
        not reach *this* principal's socket or reconnect catch-up
        verbatim. It returns the delta alone: how much it hid is not reported to anyone
        (ADR-124 decision 1).

        **Every delta is projected** (decision 4): a removal names ids and a replacement names two
        links, so each carries a record of what it names (`DeltaRemove.removed`,
        `DeltaReplaceEdge.removed`) from which this decides what `principal` is sent, and the
        sent forms never hold the record. A reproject is sent with a fixed reason code and only
        the cluster keys the reader may read. `known` is the working set's nodes, which a link's
        ends and a cluster's keys are judged against; without it no end or key can be judged and
        none is sent."""
        if isinstance(delta, DeltaAdd):
            nodes, edges, _ = self._project(delta.nodes, delta.edges, principal, known)
            return delta.model_copy(update={"nodes": nodes, "edges": edges})
        if isinstance(delta, DeltaSnapshot):
            nodes, edges, _ = self._project(delta.nodes, delta.edges, principal)
            # `withheld` is `sync`'s full snapshot's alone (ADR-124 decision 5): whatever a stored
            # snapshot carries, replayed or pushed, is not sent.
            return delta.model_copy(update={"nodes": nodes, "edges": edges, "withheld": None})
        if isinstance(delta, DeltaRemove):
            return self._project_removal(delta, principal, known)
        if isinstance(delta, DeltaReplaceEdge):
            return self._project_replacement(delta, principal, known)
        if isinstance(delta, DeltaReproject):
            readable = {
                node_id
                for node_id in delta.affected_cluster_ids
                if node_id in (known or {})
                and principal_may_read(
                    (known or {})[node_id].handling,
                    (known or {})[node_id].datasets,
                    principal,
                    self._scheme,
                )
            }
            return DeltaReproject(
                seq=delta.seq,
                reason=REASON_MANUAL if delta.reason == REASON_MANUAL else REASON_THRESHOLD,
                affected_cluster_ids={
                    k: v for k, v in delta.affected_cluster_ids.items() if k in readable
                },
            )
        # No rule for it, so nothing to send: a delta of a kind added later names ids of its own,
        # and passing it on unprojected is how a hidden one reaches a socket.
        raise TypeError(f"no projection for a delta of type {type(delta).__name__}")

    def _may_read_element(self, element: RemovedElement | None, principal: Principal) -> bool:
        return element is not None and principal_may_read(
            element.handling, element.datasets, principal, self._scheme
        )

    def _may_read_ends(
        self,
        ends: Sequence[NodeId | None],
        principal: Principal,
        known: Mapping[NodeId, Node] | None,
        removed: RemovedRecord | None = None,
    ) -> bool:
        """Whether `principal` may read every one of these nodes, judged by the working set's body
        (`known`) or, for a node removed in the same delta, by its record. A node found in neither
        cannot be judged and is not readable: the safe side."""
        for end in ends:
            if end is None:
                return False
            body = (known or {}).get(end)
            if body is not None:
                if not principal_may_read(body.handling, body.datasets, principal, self._scheme):
                    return False
            elif not self._may_read_element((removed.nodes if removed else {}).get(end), principal):
                return False
        return True

    def _project_removal(
        self, delta: DeltaRemove, principal: Principal, known: Mapping[NodeId, Node] | None
    ) -> DeltaRemoveSent:
        record = delta.removed or RemovedRecord()
        node_ids = [
            node_id
            for node_id in delta.node_ids
            if self._may_read_element(record.nodes.get(node_id), principal)
        ]
        edge_ids = [
            edge_id
            for edge_id in delta.edge_ids
            if (element := record.edges.get(edge_id)) is not None
            and self._may_read_element(element, principal)
            and self._may_read_ends([element.source, element.target], principal, known, record)
        ]
        return DeltaRemoveSent(seq=delta.seq, node_ids=node_ids, edge_ids=edge_ids)

    def _project_replacement(
        self, delta: DeltaReplaceEdge, principal: Principal, known: Mapping[NodeId, Node] | None
    ) -> DeltaAdd | DeltaRemoveSent | DeltaReplaceEdgeSent:
        """The four rows of ADR-124 decision 4: the replace, the new link alone as an addition, the
        old link alone as a removal, or nothing. Each half is judged by its own marking and both of
        its ends."""
        new = delta.edge
        new_ok = principal_may_read(
            new.handling, new.datasets, principal, self._scheme
        ) and self._may_read_ends([new.source, new.target], principal, known)
        old = delta.removed
        old_ok = (
            old is not None
            and self._may_read_element(old, principal)
            and self._may_read_ends([old.source, old.target], principal, known)
        )
        if old_ok and new_ok:
            return DeltaReplaceEdgeSent(seq=delta.seq, old_edge_id=delta.old_edge_id, edge=new)
        if new_ok:
            return DeltaAdd(seq=delta.seq, edges=[new])
        if old_ok:
            return DeltaRemoveSent(seq=delta.seq, edge_ids=[delta.old_edge_id])
        return DeltaRemoveSent(seq=delta.seq)

    async def project_live(
        self, investigation_id: str, delta: WorkingSetDelta, principal: Principal
    ) -> WorkingSetDeltaSent:
        """A live push, projected for `principal` with its links' ends judged against the working
        set as it now stands (`_project`'s `known`)."""
        known = await self._store.source_fidelity_nodes(investigation_id)
        return self.project_delta(delta, principal, known)

    async def get_resolution_threshold(self, investigation_id: str) -> float:
        """`GET /v1/resolution/threshold` (`03_CONDUIT_MIDDLEWARE.md` §3.5). `None` in the store
        means no `PUT` has ever run for this investigation — `DEFAULT_THRESHOLD` (Balanced, 0.95,
        `01_DOMAIN_MODEL.md` §4's three detents) is the session's starting point, not a stored
        value that happens to equal it."""
        stored = await self._store.get_threshold(investigation_id)
        return stored if stored is not None else DEFAULT_THRESHOLD

    async def set_resolution_threshold(
        self, investigation_id: str, tau: float, principal: Principal
    ) -> ResolutionOutcome:
        """`PUT /v1/resolution/threshold` (`03_CONDUIT_MIDDLEWARE.md` §3.5, §4): "resolution
        collapse at the session's τ" re-projected against the *full* source-fidelity node set —
        not merely the nodes a single prior `expand()` happened to include — since a threshold
        change can affect any two nodes currently in the working set, not only ones a specific
        delta touched.

        Resolution edges are fetched via the same `GraphPort.expand()` every other read uses,
        scoped to `SAME_AS`/`NOT_SAME_AS` via `ExpandRequest.edge_types` — no new `GraphPort`
        method needed, and the same access filter every other read already goes through
        (`03_CONDUIT_MIDDLEWARE.md` §6: "Filtering in the Conduit after retrieval is forbidden").

        The outcome this returns carries the three summary counts `01_DOMAIN_MODEL.md` §4's own
        example gives ("3 entities merged, 1 split, 47 nodes affected"), the acting analyst's own,
        from their own view; the delta it records, which every reader receives, does not (ADR-124
        decision 1). The delta carries, since Phase 6a Stage 2, the affected nodes' own new cluster
        ids (`DeltaReproject.affected_cluster_ids`) — never the full working set — so a client
        can update cluster rendering in place instead of re-fetching via `sync`/`current_membership`
        on every move.

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
            reason=REASON_THRESHOLD,
            affected_cluster_ids=delta_counts.affected_cluster_ids,
        )
        await self._store.append_delta(investigation_id, delta)
        return ResolutionOutcome(
            delta=delta,
            merged=delta_counts.merged,
            split=delta_counts.split,
            affected=delta_counts.nodes_affected,
        )

    async def manual_link(
        self, investigation_id: str, node_a: NodeId, node_b: NodeId, principal: Principal
    ) -> tuple[ResolutionOutcome, ChangeStreamEntry | None]:
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
    ) -> tuple[ResolutionOutcome, ChangeStreamEntry | None]:
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
    ) -> tuple[ResolutionOutcome, ChangeStreamEntry | None]:
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
            reason=REASON_MANUAL,
            affected_cluster_ids=delta_counts.affected_cluster_ids,
        )
        await self._store.append_delta(investigation_id, delta)
        outcome = ResolutionOutcome(
            delta=delta,
            merged=delta_counts.merged,
            split=delta_counts.split,
            affected=delta_counts.nodes_affected,
        )
        return outcome, entry

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

    async def _reader_counts(self, investigation_id: str, principal: Principal) -> _ReaderCounts:
        """`principal`'s own figures for the case (ADR-124 decision 2): the nodes and links in their
        projected view, which is what `_project` keeps of the stored set, where a link counts only
        when it and both its ends are readable. Not a count of readable elements one by one: a
        readable link to a node the reader may not read is not in their view, and counting it would
        let the figure move with the hidden node. Every cap and every preview figure is these
        counts plus what the request adds.

        **From counts, not the set** (Amendment 4): reading and validating every body cost 3.2 s of
        a 3.4 s preview at 50,000 nodes and 100,000 links, and loading an entry per element still
        cost 1.1 s at 250,000 links. The store keeps, in the transaction of each write, the
        number of nodes of each signature and of links of each (link, source end, target end)
        signatures, with `ABSENT` for an end that is not stored. Which signatures the reader may
        read is `principal_may_read` over the signature table alone, which is small; the figures
        are sums over the readable ones. The same rules as `_project`, which
        `test_access_index.py` holds this to after every one of a run of random writes.

        **Which signatures are readable is kept** by (case, epoch, signatures version, access
        class). The signatures version counts up when a signature is first stored, so a case that
        gains a signature is a new key; the epoch is new after a `clear`, which restarts the
        signatures' keys, so a case that starts again is never taken for the one before. The access
        class (`cache.principal_class`: clearance, the receivable codes, `org_unit`, the datasets)
        is part of the key because a reader of another class must never be given another's
        readable set: that would be a rule 3 matter."""
        view = _ReaderCounts(
            self._store,
            investigation_id,
            principal,
            self._scheme,
            {},
            {},
            frozenset(),
            0,
            0,
        )

        async def reload() -> None:
            await self._read_counts_into(view)

        view.reload = reload
        await reload()
        return view

    async def _read_counts_into(self, view: _ReaderCounts) -> None:
        """Read the case's counts and set `view` from them: its signature table and epoch, the
        memo of judgements for (case, epoch, signatures version, access class), the readable
        signatures and the figures. Also what a request does again when a renumbering is met
        between its reads (`_ReaderCounts.would_add`)."""
        investigation_id, principal = view.case, view.principal
        counts = await self._store.access_counts(investigation_id)
        key = (investigation_id, counts.epoch, counts.sigs_version, principal_class(principal))
        judgements = self._readable.get(key)
        if judgements is None:
            judgements = self._readable[key] = {}
            while len(self._readable) > READABLE_CACHE_SIZE:
                self._readable.popitem(last=False)
        else:
            self._readable.move_to_end(key)
        view.signatures = counts.signatures
        view.judgements = judgements
        view.epoch = counts.epoch
        # Only signatures something carries are judged: the table keeps one for as long as the case
        # lives, and one whose handling code the scheme has since dropped cannot be judged.
        in_use = {k for k, n in counts.node_counts.items() if n > 0} | {
            k for triple, n in counts.edge_counts.items() if n > 0 for k in triple if k != ABSENT
        }
        view.readable = frozenset(k for k in in_use if view.is_readable(k))
        view.nodes = sum(n for k, n in counts.node_counts.items() if k in view.readable)
        view.edges = sum(
            n
            for (edge_sig, source_sig, target_sig), n in counts.edge_counts.items()
            if edge_sig in view.readable
            and source_sig in view.readable
            and target_sig in view.readable
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
        silently dropped from what gets stored, and the outcome says nothing of how much
        (ADR-124 decision 1)."""
        visible_nodes, visible_edges, _ = self._project(nodes, edges, principal)
        return await self._add(investigation_id, visible_nodes, visible_edges, principal)

    async def expand(
        self, investigation_id: str, req: ExpandRequest, principal: Principal
    ) -> ExpansionOutcome:
        """`POST /expand`: the filtered result the analyst receives, added to the working set. No
        figure for what the filter left out is asked for or returned (ADR-124 decision 1)."""
        subgraph = await self._graph.expand(req, principal)
        # ADR-098: the links the expansion did not walk along, among its nodes and the view, when
        # it is small enough to ask; all of them or, if they would pass the cap, none. The view is
        # the reader's own (ADR-124 decision 2): a stored node they may not read is not in it, so
        # neither the choice to ask nor the cap moves with it.
        view = await self._reader_counts(investigation_id, principal)
        new_ids = {n.id for n in subgraph.nodes}
        new_count, _, _ = await view.would_add(new_ids, ())
        view_size = view.nodes + new_count
        if new_count > AUTO_LINKS_MAX_NEW_NODES or view_size > AUTO_LINKS_MAX_VIEW_NODES:
            outcome = await self._add(
                investigation_id, subgraph.nodes, subgraph.edges, principal, view=view
            )
            return outcome.model_copy(update={"links_among": "not_asked"})
        # The view is small here, so its nodes can be named for the graph.
        among = await self._graph.edges_among(
            sorted(await view.visible_node_ids() | new_ids), principal
        )
        walked = {e.id for e in subgraph.edges}
        extra = [e for e in among if e.id not in walked]
        try:
            outcome = await self._add(
                investigation_id,
                subgraph.nodes,
                [*subgraph.edges, *extra],
                principal,
                view=view,
            )
            return outcome.model_copy(update={"links_among": "added"})
        except LimitExceededError:
            if not extra:
                raise
        outcome = await self._add(
            investigation_id, subgraph.nodes, subgraph.edges, principal, view=view
        )
        return outcome.model_copy(update={"links_among": "view_full"})

    async def links_among(
        self,
        investigation_id: str,
        principal: Principal,
        node_ids: Sequence[NodeId] | None = None,
        degree: int = 1,
    ) -> LinksAmongOutcome:
        """`POST .../links-among` (ADR-098): the links among the named nodes that are in the view,
        or among the whole view, added all or none against the cap (rule 2). The graph read is
        access-filtered for `principal` in the adapter (rule 3).

        Past one degree (Amendment 4), also the routes between each pair of them: the fewest
        degrees that join the pair, up to `degree`, as ADR-116 finds them (`paths_at_length`, the
        reader's search in the adapter), their nodes and links added with the direct ones."""
        # What the reader may read of the ids named, before anything else (ADR-124 decision 3): a
        # stored id they may not read is dropped here exactly as one the store does not hold is, so
        # nothing after this, in the result or in the time it takes, depends on which it was.
        reader = await self._reader_counts(investigation_id, principal)
        ids = (
            await reader.visible_node_ids()
            if node_ids is None
            else await reader.visibly_stored_among(node_ids)
        )
        among = await self._graph.edges_among(sorted(ids), principal)
        route_nodes: dict[NodeId, Node] = {}
        route_edges: dict[EdgeId, Edge] = {e.id: e for e in among}
        unconnected = more = 0
        if degree > 1:
            chosen = sorted(ids)
            for i, source in enumerate(chosen):
                for target in chosen[i + 1 :]:
                    for length in range(1, degree + 1):
                        routes = await self._graph.paths_at_length(
                            source, target, length, CONNECTIONS_SHOWN, principal
                        )
                        if routes.paths:
                            for path in routes.paths:
                                route_nodes.update({n.id: n for n in path.nodes})
                                route_edges.update({e.id: e for e in path.edges})
                            more += routes.more
                            break
                    else:
                        unconnected += 1
        existing_nodes = await self._store.node_ids(investigation_id)
        existing_edges = await self._store.edge_ids(investigation_id)
        new_nodes = [n for n in route_nodes.values() if n.id not in existing_nodes]
        new = [e for e in route_edges.values() if e.id not in existing_edges]
        outcome = await self._add(investigation_id, new_nodes, new, principal)
        return LinksAmongOutcome(
            delta=outcome.delta, added=len(new), added_nodes=len(new_nodes), degree=degree,
            unconnected_pairs=unconnected, more_routes_pairs=more,
        )  # fmt: skip

    async def expand_preview(
        self, investigation_id: str, req: ExpandRequest, principal: Principal
    ) -> CardinalityPreview:
        """`POST /expand/preview` — cardinality only, no mutation
        (`03_CONDUIT_MIDDLEWARE.md` §3.2). Runs the same `GraphPort` read `expand` does, and the
        same cap arithmetic, over the reader's own projected view plus what the request adds
        (ADR-124 decision 2), but never calls `_add` — nothing is written to the store or appended
        to the delta stream. The counts are the same with and without a stored item the reader may
        not read, so a per-type preview cannot be used to find one."""
        subgraph = await self._graph.expand(req, principal)
        view = await self._reader_counts(investigation_id, principal)
        new_nodes, new_edges, _ = await view.would_add(
            (n.id for n in subgraph.nodes), (e.id for e in subgraph.edges), subgraph.nodes
        )
        would_be_nodes = view.nodes + new_nodes
        would_be_edges = view.edges + new_edges
        return CardinalityPreview(
            candidate_node_count=would_be_nodes,
            candidate_edge_count=would_be_edges,
            would_breach=_cap_breach(would_be_nodes, would_be_edges),
        )

    async def add_written(
        self,
        investigation_id: str,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        principal: Principal,
    ) -> DeltaAdd:
        """Puts nodes and links this Conduit has just written into the case's working set and
        returns the delta that says so (ADR-089: the Document an email becomes, and an entity
        accepted from it). Nothing is filtered here: the caller wrote them under a handling it
        could itself see, and the cap check and the sequence are `_add`'s own, counted over
        `principal`'s own view (ADR-124 decision 2).

        ADR-099: the copy is stamped as the write was (`DatasetStampingGraph`), each element that
        names no dataset given the request's case's first; otherwise the canvas, drawn from these
        copies, would hold back what the case has just written."""
        from ..dataset_scope import case_datasets

        held = case_datasets()
        if held:
            into = [held[0]]
            nodes = [n if n.datasets else n.model_copy(update={"datasets": into}) for n in nodes]
            edges = [e if e.datasets else e.model_copy(update={"datasets": into}) for e in edges]
        outcome = await self._add(investigation_id, nodes, edges, principal)
        return outcome.delta

    async def ensure_room(
        self,
        investigation_id: str,
        node_ids: Sequence[str],
        edge_ids: Sequence[str],
        principal: Principal,
    ) -> None:
        """Raises `LimitExceededError` if adding these ids would take `principal`'s own view of the
        case past its cap (ADR-124 decision 2). For a caller that writes the graph first and then
        adds what it wrote: it asks here before writing, so a refused request leaves nothing in the
        graph either (rule 2, ADR-092)."""
        view = await self._reader_counts(investigation_id, principal)
        new_nodes, new_edges, _ = await view.would_add(node_ids, edge_ids)
        breach = _cap_breach(view.nodes + new_nodes, view.edges + new_edges)
        if breach is not None:
            raise LimitExceededError(breach)

    async def _new_within_cap(
        self,
        investigation_id: str,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        principal: Principal,
        view: _ReaderCounts | None = None,
    ) -> tuple[list[Node], list[Edge]]:
        """What of `nodes` and `edges` is new to the store, refusing the whole request if it would
        take `principal`'s own view past the cap. The stored set decides what is written (the
        store's entries for these ids say which it holds); the reader's view decides what is
        counted (ADR-124 decision 2). `view` is given by a caller that has just read it."""
        view = view or await self._reader_counts(investigation_id, principal)
        new_in_view_nodes, new_in_view_edges, entries = await view.would_add(
            (n.id for n in nodes), (e.id for e in edges), nodes
        )
        new_nodes = [n for n in nodes if n.id not in entries.nodes]
        new_edges = [e for e in edges if e.id not in entries.edges]
        breach = _cap_breach(view.nodes + new_in_view_nodes, view.edges + new_in_view_edges)
        if breach is not None:
            raise LimitExceededError(breach)
        return new_nodes, new_edges

    async def _add(
        self,
        investigation_id: str,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        principal: Principal,
        *,
        view: _ReaderCounts | None = None,
        empty_on_failure: bool = False,
    ) -> ExpansionOutcome:
        """`03_CONDUIT_MIDDLEWARE.md` §4: "On breach the service does not
        truncate". The cap check runs — and can raise — *before* any
        write, so a would-be-breaching call never partially lands: it is
        rejected whole, or it succeeds whole, never a silent slice of
        either the requested nodes or the requested edges."""
        new_nodes, new_edges = await self._new_within_cap(
            investigation_id, nodes, edges, principal, view
        )

        try:
            await self._store.add_nodes(investigation_id, new_nodes)
            await self._store.add_edges(investigation_id, new_edges)

            seq = await self._store.next_seq(investigation_id)
            delta = DeltaAdd(seq=seq, nodes=list(nodes), edges=list(edges))
            await self._store.append_delta(investigation_id, delta)
        except BaseException:
            if empty_on_failure:
                # A write of several chunks that stopped part-way: the case it was filling is
                # emptied, so that what is left is nothing rather than something that looks like
                # a complete copy.
                await self._store.clear(investigation_id)
            raise

        return ExpansionOutcome(delta=delta)

    async def branch_contents(
        self,
        source_investigation_id: str,
        principal: Principal,
        node_ids: Sequence[NodeId] | None = None,
    ) -> tuple[list[Node], list[Edge], int]:
        """What a branch of `source_investigation_id` would hold for `principal`: the nodes and
        links, and the hidden count. Without `node_ids` that is the whole working set, as before.
        With them (ADR-084) it is the chosen nodes and only the links whose two ends are both
        chosen. Either way it is read from the source-fidelity set and then projected for the
        branching principal, so a node they may not see is never copied, and asking for one reads
        exactly as asking for an id that does not exist: it is simply absent, the hidden count is 0
        and, if nothing is left, `NothingToBranchError` is the same whatever the reason. Nothing is
        written, so a route can call this before it creates the new case."""
        nodes = await self._store.source_fidelity_nodes(source_investigation_id)
        edges = await self._store.source_fidelity_edges(source_investigation_id)
        if node_ids is None:
            visible_nodes, visible_edges, hidden = self._project(
                list(nodes.values()), list(edges.values()), principal
            )
            return visible_nodes, visible_edges, hidden
        chosen = set(node_ids)
        picked = [n for n in nodes.values() if n.id in chosen]
        between = [e for e in edges.values() if e.source in chosen and e.target in chosen]
        visible_nodes, visible_edges, _ = self._project(picked, between, principal)
        if not visible_nodes:
            raise NothingToBranchError
        # The hidden count is 0 on purpose: a figure here would tell the asker how many of the
        # ids they named exist but are hidden from them.
        return visible_nodes, visible_edges, 0

    async def branch(
        self,
        source_investigation_id: str,
        new_investigation_id: str,
        principal: Principal,
        node_ids: Sequence[NodeId] | None = None,
    ) -> ExpansionOutcome:
        """`POST /investigations/{id}/branch` — one of the cap breach's
        three options made real: "fork the working set into a new
        investigation" (`03_CONDUIT_MIDDLEWARE.md` §3.1). Copies only
        what `principal` (the branching principal) can see from the
        source's source-fidelity set into `new_investigation_id`, filtered
        the same way any other read is — you cannot fork what you cannot
        see, and the source may hold content only a *different*,
        more-privileged principal ever contributed. With `node_ids` it copies only those nodes
        and the links between them (ADR-084; `branch_contents` has the rules). A branch is a
        snapshot at the moment it forks, not a live link back to the
        source, so later expansion of either side never touches the
        other."""
        visible_nodes, visible_edges, _ = await self.branch_contents(
            source_investigation_id, principal, node_ids
        )
        return await self._add(
            new_investigation_id, visible_nodes, visible_edges, principal, empty_on_failure=True
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

    async def visible_membership(
        self, investigation_id: str, principal: Principal
    ) -> tuple[list[Node], list[Edge]]:
        """The working set as `principal` may see it, with the same `_project` every list read
        runs: what the change form's offered types are read from (ADR-090)."""
        nodes, edges = await self.current_membership(investigation_id)
        visible_nodes, visible_edges, _ = self._project(nodes, edges, principal)
        return visible_nodes, visible_edges

    async def visible_node(
        self, investigation_id: str, node_id: NodeId, principal: Principal
    ) -> Node | None:
        """The node `node_id` as `principal` may see it in this case, or `None`: not in the working
        set and above `principal` read the same, as `visible_edge` has it (ADR-092's reader)."""
        found = await self._store.get_node(investigation_id, node_id)
        if found is None:
            return None
        visible, _, _ = self._project([found], [], principal)
        return visible[0] if visible else None

    async def visible_edge(
        self, investigation_id: str, edge_id: EdgeId, principal: Principal
    ) -> Edge | None:
        """The link `edge_id` as `principal` may see it, or `None`.

        `None` covers three cases that must read identically to the caller: the link is not in
        this investigation's working set, its own handling is above `principal`, or one of its
        ends is (or has left the working set). Link notes use this as their whole access
        question — a note is readable and writable exactly when its link is visible — so a
        refusal here must not reveal which of the three it was, the same rule `_project` already
        follows for every list read. It reads the one link and its two ends, not the whole set,
        and runs the same `_project` the lists use, so the two can never disagree."""
        edge = await self._store.get_edge(investigation_id, edge_id)
        if edge is None:
            return None
        ends = [
            end
            for end in (
                await self._store.get_node(investigation_id, edge.source),
                await self._store.get_node(investigation_id, edge.target),
            )
            if end is not None
        ]
        _, visible, _ = self._project(ends, [edge], principal)
        return visible[0] if visible else None

    async def end_types(self, investigation_id: str, edge: Edge) -> tuple[str, str] | None:
        """The entity types at the two ends of `edge`, from the working set, or `None` if either end
        has left it. A change of a link's type has to be checked against them."""
        source = await self._store.get_node(investigation_id, edge.source)
        target = await self._store.get_node(investigation_id, edge.target)
        if source is None or target is None:
            return None
        return source.type, target.type

    async def replace_edge(
        self, investigation_id: str, old_edge: Edge, new_edge: Edge
    ) -> DeltaReplaceEdge:
        """Swaps one link for its replacement in the working set and records the step, so a client
        that reconnects is told of it. Membership only: nothing is checked here, the caller has
        already shown the principal may change the old link (`link_changes.py`).

        The delta records what the old link was (its handling, datasets and ends) so that each
        reader's projection can be decided from it (ADR-124 decision 4). The record is of the
        working set's own stored copy of the old link, which is what its readers were sent (the
        caller's may be the Vault's, whose datasets and marking can differ); the caller's is used
        when the working set holds none, in which case no reader has it on a canvas.

        The new link is stamped with the case's first dataset when it names none, as `add_written`
        stamps what the Conduit writes (ADR-099): otherwise the copy the canvas is drawn from
        belongs to none, and a reader scoped to the case is never sent it."""
        from ..dataset_scope import case_datasets

        held = case_datasets()
        if held and not new_edge.datasets:
            new_edge = new_edge.model_copy(update={"datasets": [held[0]]})
        stored = await self._store.get_edge(investigation_id, old_edge.id) or old_edge
        await self._store.remove_edges(investigation_id, [old_edge.id])
        await self._store.add_edges(investigation_id, [new_edge])
        seq = await self._store.next_seq(investigation_id)
        delta = DeltaReplaceEdge(
            seq=seq,
            old_edge_id=old_edge.id,
            edge=new_edge,
            removed=RemovedElement(
                handling=stored.handling,
                datasets=list(stored.datasets),
                source=stored.source,
                target=stored.target,
            ),
        )
        await self._store.append_delta(investigation_id, delta)
        return delta

    async def withheld_count_for(self, investigation_id: str, principal: Principal) -> int:
        """The export gate's own trusted source for the withheld-item manifest
        (`06_DECISIONS.md` ADR-045, `services/api/export.py::submit_export`) — computed here,
        server-side against `principal`'s own current access over the investigation's real,
        unfiltered membership, never accepted from a client submission. The arithmetic is
        `_project`'s own, reused rather than a second count invented for export. It is the one
        withheld figure still computed: the status bar's "N hidden by handling" and the notices that
        shared it were removed (ADR-124 decision 1), and U9 replaces this count with a yes or no.
        A client-supplied count would let an artefact state that nothing was withheld when items
        were — an active misstatement of completeness, not merely an omission, which is a
        materially worse failure than the leak ADR-045's own `disclose` default already accepts
        the cost of."""
        nodes, edges = await self.current_membership(investigation_id)
        _, _, hidden = self._project(nodes, edges, principal)
        return hidden

    async def restore(
        self,
        investigation_id: str,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        principal: Principal,
    ) -> Restored:
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
        way instead: the target set is added first (`add_nodes`/`add_edges` are
        upserts), then whatever is no longer in it is removed (`remove_edges`, then
        `remove_nodes`), so that a failure part-way never leaves less than the case held.
        Edges need this exactly as much as nodes do — an edge added *after* the step was recorded,
        between two nodes both still present at that step, has both
        endpoints intact and would never be excluded by `_project`'s
        endpoint check, so without an explicit `remove_edges` pass it
        would silently survive a restore that is supposed to erase it."""
        step_node_ids = {n.id for n in nodes}
        step_edge_ids = {e.id for e in edges}

        # The step's members are judged against the Vault as it is now, for this restorer (the
        # case's datasets are in `principal`, ADR-099): what comes back is what is stored, the
        # Vault's current bodies and never the step's recorded ones, so a node raised since is not
        # written back at its old marking, and a member the restorer may not read is not added.
        vault_nodes = await self._graph.get_nodes(sorted(step_node_ids), principal)
        vault_edges = await self._graph.get_edges(sorted(step_edge_ids), principal)

        # The cap, before anything is written (rule 2, decision 2). The restorer's own view after
        # this restore is the Vault's readable members plus the step members they may read in the
        # store that the Vault now withholds, which are left stored and stay in it; everything else
        # in their view is reconciled away, and what is outside it is not counted. Steps record the
        # whole stored set, which has no ceiling, so this is the restorer's figure and never the
        # stored whole's (rule 3). On a breach: the typed `limit_exceeded`, and nothing written.
        reader = await self._reader_counts(investigation_id, principal)
        vault_node_ids = {n.id for n in vault_nodes}
        vault_edge_ids = {e.id for e in vault_edges}
        stored_node_ids = await self._store.node_ids(investigation_id)
        stored_edge_ids = await self._store.edge_ids(investigation_id)
        left_nodes, left_edges = await reader.visible_among(
            (step_node_ids & stored_node_ids) - vault_node_ids,
            (step_edge_ids & stored_edge_ids) - vault_edge_ids,
        )
        breach = _cap_breach(len(vault_node_ids | left_nodes), len(vault_edge_ids | left_edges))
        if breach is not None:
            raise LimitExceededError(breach)

        # The adds first and the removes last (links before nodes): the writes are chunked and a
        # failure part-way leaves a superset of what the case held, never a loss.
        await self._store.add_nodes(investigation_id, vault_nodes)
        await self._store.add_edges(investigation_id, vault_edges)

        # What the step lacks is reconciled only where it is in the restorer's own view (the test
        # decision 2 uses); everything else stays stored, a readable link to a hidden end included.
        # Read after the adds: a member the Vault has declassified is written by them, which can
        # bring a stored link of theirs into the restorer's view.
        reader = await self._reader_counts(investigation_id, principal)
        stale_node_ids, stale_edge_ids = await reader.visible_among(
            await self._store.node_ids(investigation_id) - step_node_ids,
            await self._store.edge_ids(investigation_id) - step_edge_ids,
        )
        if stale_edge_ids:
            await self._store.remove_edges(investigation_id, sorted(stale_edge_ids))
        if stale_node_ids:
            await self._store.remove_nodes(investigation_id, sorted(stale_node_ids))

        # What is stored and published is the whole stored set, with no flag: every reader,
        # replaying it or receiving it live, projects it to their own view (`project_delta`), so a
        # reconnect equals a full snapshot for every reader. The restorer's response is that
        # snapshot projected for them, never the whole.
        all_nodes = list((await self._store.source_fidelity_nodes(investigation_id)).values())
        all_edges = list((await self._store.source_fidelity_edges(investigation_id)).values())
        seq = await self._store.next_seq(investigation_id)
        snapshot = DeltaSnapshot(seq=seq, nodes=all_nodes, edges=all_edges)
        await self._store.append_delta(investigation_id, snapshot)
        response = self.project_delta(snapshot, principal)
        assert isinstance(response, DeltaSnapshot)
        return Restored(published=snapshot, response=response)

    async def _record_of_nodes(
        self, investigation_id: str, node_ids: Sequence[NodeId]
    ) -> RemovedRecord:
        """What each stored node of `node_ids` is, as `principal_may_read` judges it: its handling
        and datasets, which are its signature in the counted index (`access_counts` holds the
        table, `access_entries` each node's number, one `HMGET`). An id the store does not hold has
        no entry. A renumbering between the two reads is met by reading again, once."""
        ids = list(dict.fromkeys(node_ids))
        for attempt in (0, 1):
            # The entries first, then the table: signatures are only ever added to it within an
            # epoch, so a signature an entry names (written before the entries were read) is
            # defined by a table read after them. The other order leaves a node written between the
            # two with an entry the table does not define, and it drops out of the record.
            entries = await self._store.access_entries(investigation_id, ids, [])
            counts = await self._store.access_counts(investigation_id)
            if entries.epoch == counts.epoch:
                break
            if attempt:
                raise RuntimeError("the access index kept being renumbered under a removal")
        record = RemovedRecord()
        for node_id, key in entries.nodes.items():
            signature = counts.signatures.get(key)
            if signature is not None:
                record.nodes[node_id] = RemovedElement(
                    handling=signature.handling(), datasets=list(signature.datasets)
                )
        return record

    async def remove(
        self, investigation_id: str, node_ids: Sequence[NodeId], principal: Principal
    ) -> DeltaRemove:
        """`DELETE /nodes` — "remove from the working set (not from the
        Vault)" (`03_CONDUIT_MIDDLEWARE.md` §3.2). Removal never breaches a
        cap, so there is no check to run here — only the delta to record.

        What each node was is read before it is removed, from the counted access index and not from
        the bodies (one lookup for all the ids), and the delta records it (ADR-124 decision 4):
        that is what lets every reader be sent only the ids they may read.
        The delta is the stored form, which holds the record; the route publishes it as it is and
        sends nothing of it to anyone (`project_delta`)."""
        # Only ids whose stored body the reader may read are removed (decision 6): a hidden id and
        # an absent one are ignored alike, with the same response and the same history entry, and
        # the delta names only what was removed.
        reader = await self._reader_counts(investigation_id, principal)
        removable = await reader.visibly_stored_among(node_ids)
        removed_ids = [i for i in dict.fromkeys(node_ids) if i in removable]
        record = await self._record_of_nodes(investigation_id, removed_ids)
        await self._store.remove_nodes(investigation_id, removed_ids)
        seq = await self._store.next_seq(investigation_id)
        delta = DeltaRemove(seq=seq, node_ids=removed_ids, removed=record)
        await self._store.append_delta(investigation_id, delta)
        return delta

    async def sync(
        self, investigation_id: str, principal: Principal, *, last_acknowledged_seq: int | None
    ) -> list[WorkingSetDeltaSent]:
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
        originally populated (§4's per-read handling filter). Nothing says how much was
        left out: no notice, no count (ADR-124 decision 1)."""
        if last_acknowledged_seq is not None:
            raw_deltas = await self._store.deltas_after(investigation_id, last_acknowledged_seq)
            if raw_deltas is not None:
                known = await self._store.source_fidelity_nodes(investigation_id)
                return [self.project_delta(raw, principal, known) for raw in raw_deltas]

        nodes = await self._store.source_fidelity_nodes(investigation_id)
        edges = await self._store.source_fidelity_edges(investigation_id)
        seq = await self._store.current_seq(investigation_id)
        visible_nodes, visible_edges, _ = self._project(
            list(nodes.values()), list(edges.values()), principal
        )
        return [
            DeltaSnapshot(
                seq=seq,
                nodes=visible_nodes,
                edges=visible_edges,
                withheld=await self._holds_what_the_reader_may_not_view(
                    investigation_id, principal
                ),
            )
        ]

    async def _holds_what_the_reader_may_not_view(
        self, investigation_id: str, principal: Principal
    ) -> bool:
        """The standing sentence's flag (ADR-124 decision 5): whether the case's stored set holds
        any node or link whose own stored handling `principal` may not view.

        **From the counted index, at a fixed cost** (Amendment 4): the signatures that some stored
        node, or some stored link, carries (a count above zero), judged by `principal_may_view`,
        which is handling alone. A signature folds the element's datasets in with its handling, and
        the judgement here ignores them: material outside the case's datasets that the reader is
        cleared for is outside the case's world, not withheld from it (ADR-099). A link counts by
        its own signature, the first of its triple, and never by its ends: a readable link to a
        hidden node is not withheld through the link, the node is withheld on its own. A signature
        whose handling code the scheme no longer defines cannot be judged and counts as withheld.
        Nothing is read per element."""
        counts = await self._store.access_counts(investigation_id)
        in_use = {key for key, n in counts.node_counts.items() if n > 0} | {
            triple[0] for triple, n in counts.edge_counts.items() if n > 0
        }
        for key in in_use:
            signature = counts.signatures.get(key)
            if signature is None:
                return True
            try:
                if not principal_may_view(signature.handling(), principal, self._scheme):
                    return True
            except HandlingSchemeError:
                return True
        return False


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
