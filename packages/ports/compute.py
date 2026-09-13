"""`ComputePort` — `docs/00_ARCHITECTURE.md` §2.3.

Graph algorithms: centrality, community detection, the Clique Metric, shortest
path at scale. Separate from `GraphPort`: different scaling profile (batch,
memory-hungry, tolerant of staleness) and deployment shape.
"""

from __future__ import annotations

from typing import Protocol

from schemas._pending_port_placeholders import (
    CentralityRequest,
    CliqueMetricRequest,
    CommunityRequest,
    MotifMatch,
    MotifRequest,
)
from schemas.domain import CliqueScore, CommunityId, NodeId, Path, PathRequest


class ComputePort(Protocol):
    async def centrality(self, req: CentralityRequest) -> dict[NodeId, float]: ...
    async def communities(self, req: CommunityRequest) -> dict[NodeId, CommunityId]: ...
    async def clique_metric(self, req: CliqueMetricRequest) -> dict[NodeId, CliqueScore]: ...
    async def shortest_paths(self, req: PathRequest) -> list[Path]: ...
    async def temporal_motifs(self, req: MotifRequest) -> list[MotifMatch]: ...
