"""The overview the Glass starts on — `spec/06_DECISIONS.md` ADR-057.

A community here is the one `02_GLASS_FRONTEND.md` §3.2 defines (Louvain with a connected-components
split pass, ADR-029), never a resolution cluster. Nothing in this module can carry a count of hidden
elements: no field here can hold one, and the test
`test_the_overview_never_carries_the_count_of_hidden_elements` would fail if one were added.
(`Subgraph` had a `filtered_count` until ADR-124 U2c removed it.)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.domain import CommunityId, NodeId


class OverviewCluster(BaseModel):
    """One community, drawn as a meta-node."""

    id: CommunityId
    size: int
    node_type_counts: dict[str, int]
    dominant_type: str
    internal_edge_count: int
    #: A few members, in id order, so the Glass can label the meta-node and offer a starting point.
    sample_node_ids: list[NodeId] = Field(default_factory=list)


class OverviewLink(BaseModel):
    """Edges between two shown communities. The pair is in id order; direction is not kept."""

    source_cluster: CommunityId
    target_cluster: CommunityId
    edge_count: int


class Overview(BaseModel):
    """`clusters` are the largest communities (ties by id). Everything else is counted exactly,
    never dropped: shown plus not shown always equals the total (`CLAUDE.md` rule 2)."""

    vault: str
    clusters: list[OverviewCluster]
    links: list[OverviewLink]
    total_nodes: int
    total_edges: int
    total_clusters: int
    not_shown_clusters: int
    not_shown_nodes: int
