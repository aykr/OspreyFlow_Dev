"""`ComputePort` domain types — `spec/00_ARCHITECTURE.md` §2.3, `spec/01_DOMAIN_MODEL.md` §10.

Real types replacing `_pending_port_placeholders`'s stand-ins — Phase 7 Stage 2, ahead of any
adapter (the conformance suite, and the schemas it needs, come before the
adapter that would otherwise define the contract by accident). See
`tests/schemas/test_placeholder_lifecycle.py` for the retirement this completes.

**Every population-carrying request embeds `Subgraph` directly, and `ComputePort` itself takes no
`Principal`, deliberately** — `01_DOMAIN_MODEL.md` §10 has the full reasoning: a `Subgraph` is
already what `GraphPort.expand`/`match` return, already access-filtered, and Tier 1/2 adapters
(a browser Web Worker, an in-process `rustworkx` call) never hold a store connection at all, so
there is no other population for them to reach. This makes the input *structurally* the only
population a `ComputePort` adapter can ever see — it does not, by itself, prove a *caller* always
assembles that `Subgraph` through an access-filtered fetch first, the same residual
`compute_clusters` (`services/resolve/projection.py`) already has; that composed claim is
`test_projection_access_control.py`'s own shape of test, owed by whichever stage builds
`ComputePort`'s first real caller.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schemas.domain import Edge, EdgeId, Interval, Node, NodeId, Subgraph

CentralityMetric = Literal[
    "degree",
    "weighted_degree",
    "betweenness",
    "eigenvector",
    "pagerank",
    "clustering_coefficient",
]


class CentralityRequest(BaseModel):
    """One method, one selector — `02_GLASS_FRONTEND.md`'s metrics panel and `01_DOMAIN_MODEL.md`
    §6.3's algorithm table both name every one of `CentralityMetric`'s values as a single float per
    node; `weighted_degree` uses `Edge.weight` (§6.1's own formula), not raw occurrence counts."""

    subgraph: Subgraph
    metric: CentralityMetric


class StructureNode(BaseModel):
    id: NodeId
    type: str


class StructureEdge(BaseModel):
    id: EdgeId
    source: NodeId
    target: NodeId
    weight: float = 1.0


class LinkStructure(BaseModel):
    """A graph as only its structure (ADR-100 Amendment 5): each node's id and type, each link's
    id, ends and weight. What groups are found from in a large case, whose records read in full are
    hundreds of megabytes (measured: 1.6 KB a link on the Enron case)."""

    nodes: list[StructureNode]
    edges: list[StructureEdge]


class CommunityRequest(BaseModel):
    """Louvain, with a connected-components split pass — `06_DECISIONS.md` ADR-029: Leiden
    (`01_DOMAIN_MODEL.md` §6.3's own original preference) is unavailable on either compute tier —
    no browser-ecosystem implementation with the maturity this build requires, and the standard
    Python route (`leidenalg`) is GPL, the same dependency ADR-021 already rejected for Splink.
    The split pass closes §6.3's own specific objection to Louvain (it can merge two disconnected
    components into one labelled community) without restoring Leiden's own partition quality — a
    disclosed trade, not a free fix. No algorithm choice is exposed; only one is sanctioned.

    Of exactly one graph: the records (`subgraph`, the canvas's own), or only their structure
    (`structure`, a whole case's, ADR-100 Amendment 5). The algorithm reads ids and ends alone."""

    subgraph: Subgraph | None = None
    structure: LinkStructure | None = None

    @model_validator(mode="after")
    def _exactly_one_graph(self) -> CommunityRequest:
        if (self.subgraph is None) == (self.structure is None):
            raise ValueError("a community request is of exactly one graph: subgraph or structure")
        return self

    def ids_and_ends(self) -> tuple[list[NodeId], list[tuple[NodeId, NodeId]]]:
        graph: Subgraph | LinkStructure = self.subgraph or self.structure  # type: ignore[assignment]
        return [n.id for n in graph.nodes], [(e.source, e.target) for e in graph.edges]


class CliqueMetricRequest(BaseModel):
    """`01_DOMAIN_MODEL.md` §6.2's exact formula. `k_min`/`k_max` are that section's own stated
    defaults, overridable the same way the edge-weight formula's α/β/γ are deployment
    configuration, never hardcoded into an adapter."""

    subgraph: Subgraph
    k_min: int = 4
    k_max: int = 30


MotifType = Literal["convoy", "relay", "burst"]


class MotifRequest(BaseModel):
    """Real types, honestly scoped — a disclosed gap: this schema exists because
    `_pending_port_placeholders.py`'s retirement needs it,
    not because any phase's bullet list has yet claimed the convoy/relay/burst algorithms
    themselves. `distance_tolerance`/`time_tolerance_seconds` are named directly from
    `02_GLASS_FRONTEND.md`'s own Convoy analysis line ("co-located within a distance and time
    tolerance; tolerances are user-set and shown") — `relay`/`burst` have no comparably specific
    spec text yet, so their own parameter needs are left to whichever stage actually builds them."""

    subgraph: Subgraph
    motif_type: MotifType
    distance_tolerance: float | None = None
    time_tolerance_seconds: float | None = None


class MotifMatch(BaseModel):
    motif_type: MotifType
    node_ids: list[NodeId]
    interval: Interval | None = None


# --- Ownership (06_DECISIONS.md ADR-109 phase C, ruling 9) -------------------


class OwnershipLink(BaseModel):
    """One link of a corporate structure, owner to owned: `owns` with its percentage (0–100;
    `None` when the record states none), or `controls` (control without a stated share)."""

    id: EdgeId
    source: NodeId
    target: NodeId
    kind: Literal["owns", "controls"]
    percent: float | None = Field(default=None, ge=0, le=100)


class OwnershipRequest(BaseModel):
    """Who ultimately owns or controls `target`, through every chain of `links` that reaches
    it. `nodes` carry each party's type, so a natural person is told apart."""

    target: NodeId
    nodes: list[StructureNode]
    links: list[OwnershipLink]
    #: The share at or above which a natural person is a beneficial owner (5AMLD's 25 by default).
    threshold: float = Field(default=25.0, gt=0, le=100)
    #: The longest chain traced; a longer structure is refused, never traced in part (rule 2).
    max_depth: int = Field(default=10, ge=1, le=20)


class OwnershipPath(BaseModel):
    """One chain from an owner to the target, its links in order. `ownership`: every link owns
    with a stated percentage, and `share` is their product (as a percentage). `unknown`: a link
    states no percentage, so the share is not known. `control`: a link controls rather than owns,
    so the chain confers control, not a share."""

    link_ids: list[EdgeId]
    kind: Literal["ownership", "unknown", "control"]
    share: float | None = None


class OwnerTrace(BaseModel):
    node_id: NodeId
    node_type: str
    #: The sum of the known shares of every ownership chain — a lower bound when `share_unknown`.
    cumulative_percent: float
    share_unknown: bool = False
    controls: bool = False
    paths: list[OwnershipPath] = Field(default_factory=list)
    #: A natural person at or above the threshold, or holding control.
    beneficial_owner: bool = False
    #: A natural person below the threshold whose share is partly unknown: it may be more.
    possible_beneficial_owner: bool = False


class OwnershipTrace(BaseModel):
    target: NodeId
    threshold: float
    #: Every party with a chain to the target, the largest known share first.
    owners: list[OwnerTrace] = Field(default_factory=list)
    #: Each set of parties that own one another in a circle (traced once, never looped; flagged).
    cycles: list[list[NodeId]] = Field(default_factory=list)


class OwnershipView(BaseModel):
    """An ownership trace as the Glass shows it: the trace, and the parties and links it was
    computed over, read as the reader (ADR-109 phase C)."""

    trace: OwnershipTrace
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


# --- Risk propagation (06_DECISIONS.md ADR-109 phase E, ruling 9's D4 defaults) -


class PropagationRequest(BaseModel):
    """How much risk reaches `target` from the seeds around it: each seed's weight decayed by
    `decay` per hop of its *shortest* distance (links undirected), counted once, out to `max_hops`.
    The structure is whatever the caller read as the reader — so a seed, or a path, the reader
    cannot see contributes nothing (rule 3)."""

    target: NodeId
    nodes: list[StructureNode]
    edges: list[StructureEdge]
    seeds: dict[NodeId, float]
    max_hops: int = Field(default=2, ge=0, le=4)
    decay: float = Field(default=0.5, gt=0, le=1)


class PropagationContribution(BaseModel):
    node_id: NodeId
    hops: int
    seed: float
    contribution: float


class PropagationResult(BaseModel):
    target: NodeId
    score: float
    #: Largest contribution first, ties by id.
    contributions: list[PropagationContribution] = Field(default_factory=list)


class OwnershipTooComplex(Exception):
    """A structure deeper than `max_depth`, or with more chains than a trace will enumerate:
    refused in words rather than traced in part (rule 2)."""


ALL_MODELS: tuple[type[BaseModel], ...] = (
    CentralityRequest,
    CommunityRequest,
    LinkStructure,
    StructureNode,
    StructureEdge,
    CliqueMetricRequest,
    MotifRequest,
    MotifMatch,
    OwnershipLink,
    OwnershipRequest,
    OwnershipPath,
    OwnerTrace,
    OwnershipTrace,
    OwnershipView,
    PropagationRequest,
    PropagationContribution,
    PropagationResult,
)
