"""What the Explore panel reads from the store — `spec/06_DECISIONS.md` ADR-100.

Every figure here is the reading principal's own (`CLAUDE.md` rules 3 and 7): counted in the store
with the access and dataset steps every read uses, so a node the principal cannot see is in no
count, ranking or degree. Nothing here carries a count of what is hidden.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from schemas.domain import Edge, Node, PatternQuery


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


class RankedLink(BaseModel):
    edge: Edge
    #: Both ends, so the pair can be named without another read.
    source: Node
    target: Node


class RankedLinks(BaseModel):
    """One page of links by how many records each stands for (`Edge.occurrences`: an Enron link's
    messages), most first, ties by id. `total` is how many are ranked (rule 2)."""

    links: list[RankedLink]
    total: int
    offset: int
    #: When the Conduit ranked them (ADR-100 Amendment 3: they are kept); `None` from the store.
    computed_at: datetime | None = None


class BusyDay(BaseModel):
    start: datetime
    end: datetime
    #: Dated events (an Enron message per recipient) on the day.
    count: int


class BusiestDays(BaseModel):
    """One page of the case's days by events, most first, ties by date; `total` is how many days
    have any (rule 2)."""

    days: list[BusyDay]
    total: int
    offset: int
    computed_at: datetime | None = None


class Group(BaseModel):
    """One community of the case (Louvain with the split pass, ADR-029), named by its member with
    the most links inside it."""

    id: str
    size: int
    dominant_type: str
    central: Node
    central_links: int


class Bridge(BaseModel):
    """A node whose links reach groups other than its own: how many, and how many links it has."""

    node: Node
    groups_reached: int
    links: int


class Groups(BaseModel):
    """The largest groups and the strongest bridges; what is not shown is counted (rule 2)."""

    groups: list[Group]
    total_groups: int
    not_shown_groups: int
    bridges: list[Bridge]
    total_bridges: int
    computed_at: datetime | None = None


class LoadSummary(BaseModel):
    """One load into the case's datasets (ADR-100 decision 7), as far as the reader can see it:
    only what it wrote that they can see is counted, and `latest` is the newest of those."""

    #: `None` for what was written outside a recipe load (a seed, a hand-made link).
    load_id: str | None
    recipe_id: str | None = None
    recipe_version: int | None = None
    nodes: int
    #: Links counted only when both their ends can be seen, the same rule a degree follows.
    links: int
    latest: datetime


class RecentLoads(BaseModel):
    """The latest loads first (ties by id); `total` is how many there are (rule 2)."""

    loads: list[LoadSummary]
    total: int


class ConfirmedNode(BaseModel):
    node: Node
    confirmed_at: datetime
    confirmed_by: str


class RecentlyConfirmed(BaseModel):
    """Nodes an analyst has confirmed (`provenance.last_confirmed`), the latest first, ties by id;
    `total` is how many are confirmed (rule 2)."""

    nodes: list[ConfirmedNode]
    total: int


class MarkedNode(BaseModel):
    """A node an analyst has marked for suppression (owner ruling R7): a proposal, not a change."""

    node: Node
    marked_at: datetime
    marked_by: str
    reason: str


class WhatsNew(BaseModel):
    """ADR-100 decision 7: the latest loads into the case's datasets, and what colleagues
    confirmed or marked in them, each the latest first with how many there are in all."""

    loads: list[LoadSummary]
    loads_total: int
    confirmed: list[ConfirmedNode]
    confirmed_total: int
    marked: list[MarkedNode]
    marked_total: int
    #: When the loads and confirmations were counted (they are kept, Amendment 3); the marks are
    #: read on every request, since marking writes nothing to the graph that would clear them.
    computed_at: datetime | None = None


class StarterQuestion(BaseModel):
    """A query-builder pattern that suits the case's types (ADR-100 decision 8, Amendment 7), run
    with one action."""

    #: Stable for the same types: the run route rebuilds the question from it.
    id: str
    question: str
    pattern: PatternQuery


class StarterQuestions(BaseModel):
    """The first few that suit the case, and how many suit it in all (rule 2)."""

    questions: list[StarterQuestion]
    total: int


ALL_MODELS = (
    TypeCounts,
    RankedNode,
    RankedNodes,
    RankedLink,
    RankedLinks,
    BusyDay,
    BusiestDays,
    Group,
    Bridge,
    Groups,
    LoadSummary,
    RecentLoads,
    ConfirmedNode,
    RecentlyConfirmed,
    MarkedNode,
    WhatsNew,
    StarterQuestion,
    StarterQuestions,
)
