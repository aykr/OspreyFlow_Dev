"""What the Explore panel reads from the store — `spec/06_DECISIONS.md` ADR-100.

Every figure here is the reading principal's own (`CLAUDE.md` rules 3 and 7): counted in the store
with the access and dataset steps every read uses, so a node the principal cannot see is in no
count, ranking or degree. Nothing here carries a count of what is hidden.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.domain import Node


class TypeCounts(BaseModel):
    """How many nodes of each entity type, and links of each link type, the principal can see. A
    link counts only when both its ends can be seen, the same rule a degree follows."""

    nodes: dict[str, int] = Field(default_factory=dict)
    edges: dict[str, int] = Field(default_factory=dict)
    #: When the Conduit counted them (ADR-100 Amendment 3: they are kept); `None` from the store.
    computed_at: datetime | None = None


class RankedNode(BaseModel):
    node: Node
    #: Links to nodes the principal can see, of every type.
    degree: int


class RankedNodes(BaseModel):
    """One page of nodes by degree, most first (ties by id). `total` is how many nodes the ranking
    is of, so a "top 10" says of how many, and a page beyond it is asked for, never implied
    (`CLAUDE.md` rule 2)."""

    nodes: list[RankedNode]
    total: int
    offset: int
    #: When the Conduit ranked them (ADR-100 Amendment 3: they are kept); `None` from the store.
    computed_at: datetime | None = None


ALL_MODELS = (TypeCounts, RankedNode, RankedNodes)
