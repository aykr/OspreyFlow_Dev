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

from pydantic import BaseModel

from schemas.domain import Interval, NodeId, Subgraph

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


class CommunityRequest(BaseModel):
    """Louvain, with a connected-components split pass — `06_DECISIONS.md` ADR-029: Leiden
    (`01_DOMAIN_MODEL.md` §6.3's own original preference) is unavailable on either compute tier —
    no browser-ecosystem implementation with the maturity this build requires, and the standard
    Python route (`leidenalg`) is GPL, the same dependency ADR-021 already rejected for Splink.
    The split pass closes §6.3's own specific objection to Louvain (it can merge two disconnected
    components into one labelled community) without restoring Leiden's own partition quality — a
    disclosed trade, not a free fix. No algorithm choice is exposed; only one is sanctioned."""

    subgraph: Subgraph


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


ALL_MODELS: tuple[type[BaseModel], ...] = (
    CentralityRequest,
    CommunityRequest,
    CliqueMetricRequest,
    MotifRequest,
    MotifMatch,
)
