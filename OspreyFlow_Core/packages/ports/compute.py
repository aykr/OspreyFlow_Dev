"""`ComputePort` — `spec/00_ARCHITECTURE.md` §2.3, `spec/01_DOMAIN_MODEL.md` §10.

Graph algorithms: centrality, community detection, the Clique Metric, shortest
path at scale. Separate from `GraphPort`: different scaling profile (batch,
memory-hungry, tolerant of staleness) and deployment shape.

**No `Principal` on any method, deliberately** — unlike `GraphPort`/`AnalyticsPort`, which carry
one everywhere. `01_DOMAIN_MODEL.md` §10 has the full reasoning: every population-carrying request
below embeds a `Subgraph` — already what `GraphPort.expand`/`match` return, already
access-filtered — and Tier 1/2 adapters (a browser Web Worker, an in-process `rustworkx` call)
never hold a store connection at all, so a `Subgraph` is structurally the only population they can
ever see. This does not, on its own, prove a caller always assembles that `Subgraph` through an
access-filtered fetch first — the same residual `services/resolve/projection.py`'s
`compute_clusters` has — which is why `01_DOMAIN_MODEL.md` §10 names the composed caller-contract
test this port's first real caller owes, the same shape as `test_projection_access_control.py`.
"""

from __future__ import annotations

from typing import Protocol

from schemas.compute import (
    CentralityRequest,
    CliqueMetricRequest,
    CommunityRequest,
    MotifMatch,
    MotifRequest,
    OwnershipRequest,
    OwnershipTrace,
    PropagationRequest,
    PropagationResult,
)
from schemas.domain import CliqueScore, CommunityId, NodeId, Path, PathRequest


class ComputePort(Protocol):
    async def centrality(self, req: CentralityRequest) -> dict[NodeId, float]: ...
    async def communities(self, req: CommunityRequest) -> dict[NodeId, CommunityId]: ...
    async def clique_metric(self, req: CliqueMetricRequest) -> dict[NodeId, CliqueScore]: ...
    async def shortest_paths(self, req: PathRequest) -> list[Path]: ...
    #: `PathRequest` (`schemas/domain.py`) is `GraphPort.paths`'s own type, reused rather than
    #: redesigned this stage — unlike the other four methods here, it carries no `Subgraph`
    #: population, only a source/target pair, worth a design pass whenever this method gets a
    #: real caller rather than assumed identical in shape to the rest of this Protocol.
    async def temporal_motifs(self, req: MotifRequest) -> list[MotifMatch]: ...
    async def ownership(self, req: OwnershipRequest) -> OwnershipTrace:
        """Cumulative ownership and control of `req.target` (ADR-109 phase C, ruling 9): every
        simple chain of owner→owned links reaching it; a chain's share is the product of its
        percentages, an owner's the sum over its chains. A chain with a link of no stated
        percentage is `unknown` (never assumed); one through a `controls` link is `control` (no
        share). A circle of cross-holdings is traced once and flagged. Deeper than `max_depth`, or
        more chains than can be enumerated, raises `OwnershipTooComplex`."""
        ...

    async def propagate(self, req: PropagationRequest) -> PropagationResult:
        """Distance-decayed risk at `req.target` (ADR-109 phase E): each seed within `max_hops`
        contributes `seed × decay^hops` at its shortest undirected distance, once; the score is
        their sum, in one fixed order on every tier (contributions sorted, then summed)."""
        ...
