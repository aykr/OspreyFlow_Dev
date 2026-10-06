"""Wire and internal shapes for the Working-Set Service —
`spec/03_CONDUIT_MIDDLEWARE.md` §3.2 (the delta protocol) and §4 (caps,
storage, projection), `spec/00_ARCHITECTURE.md` §4.

The five delta ops below (`add`/`update`/`remove`/`reproject`/`notice`) are
`03_CONDUIT_MIDDLEWARE.md` §3.2's own illustrative examples, given real
types. `DeltaSnapshot` is not one of those five: §3.2's prose requires it
("a client that misses a sequence reconnects and requests a full snapshot
rather than attempting to patch") without giving its wire shape, so this
follows the same pattern `GraphPort` set when it grew past its own
illustrative snippet (`00_ARCHITECTURE.md` §2.1) — a real shape belongs in
code, not only in a docstring.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from schemas.domain import ClusterId, Edge, EdgeId, Node, NodeId

#: `00_ARCHITECTURE.md` §4 / `03_CONDUIT_MIDDLEWARE.md` §4 — "50,000 nodes
#: and 250,000 edges" by policy (ADR-007). Not a config value: raising the
#: figure is a revisit of the ADR once measurement supports it, not a
#: deployment-time setting.
MAX_NODES = 50_000
MAX_EDGES = 250_000

LimitOption = Literal["branch", "filter", "promote_to_batch"]
_ALL_LIMIT_OPTIONS: tuple[LimitOption, LimitOption, LimitOption] = (
    "branch",
    "filter",
    "promote_to_batch",
)


class LimitExceeded(BaseModel):
    """`03_CONDUIT_MIDDLEWARE.md` §4: "On breach the service does not
    truncate; it returns a `limit_exceeded` response naming the three
    options the Glass offers the analyst... Encode this as a typed error,
    not a generic 400". A slice anywhere near the working set is the
    defect this type exists to make structurally impossible to return by
    accident — there is no code path that produces a `Subgraph` silently
    capped at the boundary; there is only this, or success."""

    error: Literal["limit_exceeded"] = "limit_exceeded"
    cap_kind: Literal["nodes", "edges"]
    cap: int
    would_be: int
    options: tuple[LimitOption, LimitOption, LimitOption] = _ALL_LIMIT_OPTIONS


class LimitExceededError(Exception):
    """Raised by `WorkingSetService.expand`/`seed` on a cap breach. The API
    surface (next phase) catches this and renders `detail` as the typed
    body — never a generic 400 (`03_CONDUIT_MIDDLEWARE.md` §4)."""

    def __init__(self, detail: LimitExceeded) -> None:
        super().__init__(f"{detail.cap_kind} cap of {detail.cap} would be breached")
        self.detail = detail


class NothingToBranchError(Exception):
    """A branch of a chosen set of nodes (ADR-084) found nothing to copy: every id asked for is
    absent, hidden from the branching principal, or the choice was empty. One error for all three,
    on purpose, so the answer cannot be used to tell a hidden node from one that does not exist
    (`CLAUDE.md` rules 3 and 4). Raised before any case is created, so none is left behind empty."""


class NodePropertyUpdate(BaseModel):
    id: NodeId
    properties: dict[str, Any]


class DeltaAdd(BaseModel):
    seq: int
    op: Literal["add"] = "add"
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class DeltaUpdate(BaseModel):
    seq: int
    op: Literal["update"] = "update"
    nodes: list[NodePropertyUpdate] = Field(default_factory=list)


class DeltaRemove(BaseModel):
    seq: int
    op: Literal["remove"] = "remove"
    node_ids: list[NodeId] = Field(default_factory=list)


class DeltaReplaceEdge(BaseModel):
    """One link stands in for another (ADR-080): an analyst changed a link's type or details, which
    supersedes it. The old link leaves the working set and `edge` arrives in its place, in one step,
    so a client never shows both and a reconnecting client never keeps the old one."""

    seq: int
    op: Literal["replace_edge"] = "replace_edge"
    old_edge_id: EdgeId
    edge: Edge


class DeltaReproject(BaseModel):
    """A resolution-threshold change (`PUT /v1/resolution/threshold`,
    `03_CONDUIT_MIDDLEWARE.md` §3.5) re-collapses the working set at the
    new τ; this is how the client learns what moved without re-fetching
    the whole set.

    `affected_cluster_ids` (Phase 6a Stage 2) is `ClusterDelta.affected_cluster_ids`
    (`services/resolve/projection.py`) carried through unchanged — every node whose cluster
    membership moved, mapped to its new cluster id, bounded by `affected` and therefore never a
    full-working-set payload. It is what lets the Glass update cluster rendering in place instead
    of re-syncing up to the 50k cap to learn a handful of new `cluster_id` values, and it is
    already principal-safe by construction: it is derived from the same node population
    `set_resolution_threshold` filters to the calling principal before clustering, not from the
    investigation-shared set."""

    seq: int
    op: Literal["reproject"] = "reproject"
    reason: str
    merged: int = 0
    split: int = 0
    affected: int = 0
    affected_cluster_ids: dict[NodeId, ClusterId] = Field(default_factory=dict)


class DeltaNotice(BaseModel):
    """`03_CONDUIT_MIDDLEWARE.md` §3.2: "carries a count and never carries
    the withheld content, not even its identifiers" — enforced by this
    type's shape, not by caller discipline: there is no field here a
    withheld node's id could be put into."""

    seq: int
    op: Literal["notice"] = "notice"
    level: Literal["info", "warning"] = "warning"
    message: str
    count: int


class DeltaSnapshot(BaseModel):
    """The reconnect path's full-state response — see the module
    docstring. `filtered_count` rides on the snapshot the same way it will
    on every other projected read, so a client that reconnects mid-session
    sees the same "N hidden by handling" figure it would have seen by
    staying connected."""

    seq: int
    op: Literal["snapshot"] = "snapshot"
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    filtered_count: int = 0


WorkingSetDelta = Annotated[
    DeltaAdd
    | DeltaUpdate
    | DeltaRemove
    | DeltaReplaceEdge
    | DeltaReproject
    | DeltaNotice
    | DeltaSnapshot,
    Field(discriminator="op"),
]

_delta_adapter: TypeAdapter[Any] = TypeAdapter(WorkingSetDelta)


def decode_delta(data: dict[str, Any]) -> WorkingSetDelta:
    """Reconstructs the right delta subtype from its `op` discriminator —
    used by `store.py` reading a delta back out of the capped Valkey
    stream, and by `app.py`'s live WebSocket push, both of which only
    ever have a delta as plain JSON (from the Valkey stream or a Pub/Sub
    message) rather than a typed object."""
    return _delta_adapter.validate_python(data)  # type: ignore[no-any-return]


class ExpansionOutcome(BaseModel):
    """What `WorkingSetService.expand` returns on success — the delta the
    client should apply, plus the same `filtered_count` figure the status
    bar reports (`02_GLASS_FRONTEND.md` §... "6 hidden by handling")."""

    delta: DeltaAdd
    filtered_count: int
    #: ADR-098: whether the links among the expansion's nodes and the view were brought too.
    #: `not_asked` past the automatic limits; `view_full` when they would have passed the cap, so
    #: none was added (never some of them) and the canvas says so.
    links_among: Literal["added", "not_asked", "view_full"] = "not_asked"


class LinksAmongOutcome(BaseModel):
    """`POST .../links-among` (ADR-098): the delta that draws the new links, and how many."""

    delta: DeltaAdd
    added: int


class NodeNotInWorkingSetError(Exception):
    """Raised by `manual_link`/`manual_split` when either node id is not currently part of this
    investigation's working set. An analyst can only assert a resolution relationship between
    nodes they can already see in their own session — the same boundary `03_CONDUIT_MIDDLEWARE.md`
    §6 draws for every other read/write here, applied to a pair of ids instead of one."""


class SameNodeAssertionError(Exception):
    """Raised by `manual_link`/`manual_split` when `node_a == node_b` — asserting a node is (or
    is not) the same as itself is meaningless and would otherwise silently no-op through
    `compute_clusters`' own union-find rather than surfacing as the caller mistake it is."""


class ClusterNotFoundError(Exception):
    """Raised by `explain` when no node in the working set currently carries the requested
    `cluster_id` — most often a stale id from before the working set's last reproject."""


class PairwiseExplanation(BaseModel):
    """One direct `SAME_AS`/`NOT_SAME_AS` edge between two current members of an explained
    cluster — `03_CONDUIT_MIDDLEWARE.md` §3.5: "Return the per-comparison match weights, not just
    the total." `score`/`model_version`/`comparison_vector` are `None` for a manually-asserted
    edge (`manually_asserted=True`) — a human decision, not a model score, has none of those to
    report. `meets_threshold` is evaluated against the session's *current* τ, not baked in at
    write time, since the same edge can cross a threshold that later moves without the edge
    itself changing."""

    node_a: NodeId
    node_b: NodeId
    edge_type: Literal["SAME_AS", "NOT_SAME_AS"]
    score: float | None
    model_version: str | None
    comparison_vector: dict[str, Any] | None
    manually_asserted: bool
    meets_threshold: bool


class ClusterExplanation(BaseModel):
    """`GET /resolution/explain/{cluster}`'s response — every direct resolution edge between two
    of the cluster's current members, so an analyst can see *why* a transitively-clustered pair
    that does not look alike ended up together (through a third node), not only the pairs that
    individually cleared τ."""

    cluster_id: ClusterId
    member_node_ids: list[NodeId]
    pairs: list[PairwiseExplanation]


class CardinalityPreview(BaseModel):
    """`POST /expand/preview` (`03_CONDUIT_MIDDLEWARE.md` §3.2): cardinality
    only, no mutation. `would_breach` names which cap, if any, an actual
    `expand` with this request would hit — the same `LimitExceeded` shape,
    computed without writing anything."""

    candidate_node_count: int
    candidate_edge_count: int
    filtered_count: int
    would_breach: LimitExceeded | None = None


__all__ = [
    "MAX_EDGES",
    "MAX_NODES",
    "CardinalityPreview",
    "ClusterExplanation",
    "ClusterNotFoundError",
    "DeltaAdd",
    "DeltaNotice",
    "DeltaRemove",
    "DeltaReplaceEdge",
    "DeltaReproject",
    "DeltaSnapshot",
    "DeltaUpdate",
    "EdgeId",
    "decode_delta",
    "ExpansionOutcome",
    "LimitExceeded",
    "LimitExceededError",
    "LimitOption",
    "NodeId",
    "NodeNotInWorkingSetError",
    "NodePropertyUpdate",
    "PairwiseExplanation",
    "SameNodeAssertionError",
    "WorkingSetDelta",
]
