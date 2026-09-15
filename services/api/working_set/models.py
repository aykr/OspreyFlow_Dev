"""Wire and internal shapes for the Working-Set Service —
`docs/03_CONDUIT_MIDDLEWARE.md` §3.2 (the delta protocol) and §4 (caps,
storage, projection), `docs/00_ARCHITECTURE.md` §4.

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

from schemas.domain import Edge, EdgeId, Node, NodeId

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


class DeltaReproject(BaseModel):
    """A resolution-threshold change (`PUT /v1/resolution/threshold`,
    `03_CONDUIT_MIDDLEWARE.md` §3.5) re-collapses the working set at the
    new τ; this is how the client learns what moved without re-fetching
    the whole set."""

    seq: int
    op: Literal["reproject"] = "reproject"
    reason: str
    merged: int = 0
    split: int = 0
    affected: int = 0


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
    DeltaAdd | DeltaUpdate | DeltaRemove | DeltaReproject | DeltaNotice | DeltaSnapshot,
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
    "DeltaAdd",
    "DeltaNotice",
    "DeltaRemove",
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
    "NodePropertyUpdate",
    "WorkingSetDelta",
]
