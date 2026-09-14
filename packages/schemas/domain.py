"""The real domain model — `docs/01_DOMAIN_MODEL.md`.

Source of truth for `GraphPort`'s DTOs and the node/edge shape every adapter
writes and reads. TypeScript types are generated from these
(`generate_ts.py`); a drift between the two fails the build
(`scripts/schemas_check.py`).

Supersedes `packages/schemas/_phase0_placeholders.py` for everything
`GraphPort` references — see `tests/schemas/test_placeholder_lifecycle.py`
for what still lives in `_pending_port_placeholders.py` and why.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# --- Scalar identifiers -------------------------------------------------
#
# ULIDs (lexicographically sortable, time-ordered) per `01_DOMAIN_MODEL.md`
# §2: "id: NodeId  # ULID, assigned by the Conduit, never by a source system".

type NodeId = str
type EdgeId = str
type TxId = str
type ClusterId = str
type DocumentId = str
type PrincipalId = str
type OrgUnitId = str
type CommunityId = str
type CliqueScore = float
type Vector = list[float]


# --- Ontology (01_DOMAIN_MODEL.md §1) -----------------------------------


class PoleClass(StrEnum):
    """The five-class upper ontology. Closed: a deployment may add entity
    types, never a sixth POLE class — `01_DOMAIN_MODEL.md` §1.1."""

    PERSON = "person"
    OBJECT = "object"
    LOCATION = "location"
    EVENT = "event"
    ORGANISATION = "organisation"


# The nine categorical data channels the design system defines
# (`docs/design/tokens.css`), checked for protanopia/deuteranopia
# separation. Closed set: the ontology loader rejects an unknown channel
# name or a channel assigned to more than one entity type.
DATA_CHANNELS: tuple[str, ...] = (
    "ochre",
    "rose",
    "plum",
    "violet",
    "indigo",
    "azure",
    "cyan",
    "jade",
    "moss",
)

# The two system edge types ADR-006 requires from Phase 1 on. Resolution
# (Splink, Phase 6) writes `SAME_AS`; an analyst's manual split writes
# `NOT_SAME_AS`. Neither is ever user-defined or removable — the ontology
# loader injects both regardless of what a deployment's YAML says.
SAME_AS = "SAME_AS"
NOT_SAME_AS = "NOT_SAME_AS"
SYSTEM_EDGE_TYPES: tuple[str, ...] = (SAME_AS, NOT_SAME_AS)


class PropertyType(StrEnum):
    STRING = "string"
    STRING_LIST = "string[]"
    DATE = "date"
    DATETIME = "datetime"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ENUM = "enum"


class PropertyDef(BaseModel):
    name: str
    type: PropertyType
    indexed: bool = False
    required: bool = False
    sensitivity: Literal["low", "medium", "high"] | None = None
    values: list[str] | None = None

    @model_validator(mode="after")
    def _enum_needs_values(self) -> PropertyDef:
        if self.type is PropertyType.ENUM and not self.values:
            raise ValueError(f"property {self.name!r} is type 'enum' but declares no `values`")
        return self


class ResolutionConfig(BaseModel):
    """Splink blocking/comparison rules per entity type — `01_DOMAIN_MODEL.md`
    §4. Consumed by `services/resolve` from Phase 6 on; carried here because
    it is part of the ontology's per-type shape."""

    blocking: list[str] = Field(default_factory=list)
    comparisons: list[str] = Field(default_factory=list)


class EntityTypeDef(BaseModel):
    name: str
    pole_class: PoleClass
    channel: str
    shape: str
    identifiers: list[str] = Field(default_factory=list)
    properties: list[PropertyDef] = Field(default_factory=list)
    resolution: ResolutionConfig | None = None


class EdgeTypeDef(BaseModel):
    name: str
    from_types: list[str] = Field(alias="from")
    to_types: list[str] = Field(alias="to")
    directed: bool = True
    temporal: bool = False
    system: bool = False
    properties: list[PropertyDef] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class OntologySchema(BaseModel):
    """The loaded, validated ontology — what `GraphPort.apply_schema` takes
    and what the schema/migration runner turns into vertex/edge types and
    the indexes in `04_VAULT_BACKEND.md` §1.4."""

    version: int
    entity_types: list[EntityTypeDef]
    edge_types: list[EdgeTypeDef]

    def entity_type(self, name: str) -> EntityTypeDef | None:
        return next((e for e in self.entity_types if e.name == name), None)

    def edge_type(self, name: str) -> EdgeTypeDef | None:
        return next((e for e in self.edge_types if e.name == name), None)


class SchemaReport(BaseModel):
    migration_id: str
    applied_entity_types: list[str]
    applied_edge_types: list[str]
    indexes_created: list[str]
    reversible: bool = True


# --- Handling (01_DOMAIN_MODEL.md §2.2) ---------------------------------


class Handling(BaseModel):
    classification: str
    handling_code: str
    action_code: str | None = None
    sanitisation_code: str | None = None
    originator: OrgUnitId
    owning_unit: OrgUnitId
    review_date: date | None = None
    legal_basis: str | None = None


# --- Provenance (01_DOMAIN_MODEL.md §2.1) -------------------------------


class ProvenanceState(StrEnum):
    ASSERTED = "asserted"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


class SourceRef(BaseModel):
    document_id: DocumentId
    locator: str
    excerpt_hash: str


class Provenance(BaseModel):
    state: ProvenanceState
    sources: list[SourceRef]
    extracted_by: str | None = None
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    first_seen: datetime
    last_confirmed: datetime | None = None
    confirmed_by: PrincipalId | None = None

    @model_validator(mode="after")
    def _invariants(self) -> Provenance:
        if not self.sources:
            raise ValueError("provenance.sources must never be empty")
        if self.state is ProvenanceState.ASSERTED and self.extraction_confidence is not None:
            raise ValueError("extraction_confidence must be null for asserted provenance")
        return self


# --- Resolution state (01_DOMAIN_MODEL.md §2.3, §4) ---------------------
#
# Never a merge (ADR-006): a cluster is a view over `SAME_AS` scores at the
# session threshold, not a storage-level union. There is deliberately no
# field or method anywhere in this module that combines two `NodeId`s into
# one record.


class ResolutionState(BaseModel):
    cluster_id: ClusterId | None = None
    cluster_score: float | None = Field(default=None, ge=0.0, le=1.0)
    resolution_run: str | None = None
    manually_linked: list[NodeId] = Field(default_factory=list)
    manually_split: list[NodeId] = Field(default_factory=list)


# --- Audit stub (01_DOMAIN_MODEL.md §2.4) -------------------------------


class AuditStub(BaseModel):
    created_at: datetime
    created_by: PrincipalId
    revision: int = 1
    #: A `NodeId` on a `Node`'s audit, an `EdgeId` on an `Edge`'s — this
    #: block is shared by both (§3: "structurally identical, plus...").
    #: `GraphPort.supersede_node`/`supersede_edge` are the only writers.
    superseded_by: str | None = None
    #: The load that produced this element, and the recipe behind that
    #: load (ADR-018: "every loaded element is stamped with the recipe
    #: version that produced it"). `None` for elements written outside a
    #: recipe load — a conformance-suite fixture, a manual `SAME_AS`, a
    #: Splink write. `load_id` is the join key into the load ledger
    #: (`services/ingest`'s `LoadRecord`) for the full source/recipe
    #: detail; `recipe_id`/`recipe_version` are denormalised onto every
    #: element too, so "everything `cdr-carrier-a` version 4 produced" is
    #: a property filter on the graph itself, not a join through the
    #: ledger — the "query rather than an excavation" ADR-018 asks for.
    load_id: str | None = None
    recipe_id: str | None = None
    recipe_version: int | None = None
    #: A universal axis, not principal-dependent: a reverted element is
    #: invisible to every read, any clearance, the same way a `SECRET`
    #: record is invisible to an unauthorised one — `services/ingest`'s
    #: `revert_load` is the only writer, via `GraphPort.revert_elements`
    #: (Phase 2; `01_DOMAIN_MODEL.md` §2.4).
    reverted: bool = False


# --- The node and edge records (01_DOMAIN_MODEL.md §2-3) ----------------


class Node(BaseModel):
    id: NodeId
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
    handling: Handling
    resolution: ResolutionState = Field(default_factory=ResolutionState)
    audit: AuditStub


class NodeWrite(BaseModel):
    """Pre-persistence `Node`: the adapter assigns `id` (a ULID) and the
    audit block's `created_at`/`revision` on write."""

    type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
    handling: Handling
    resolution: ResolutionState = Field(default_factory=ResolutionState)
    created_by: PrincipalId
    load_id: str | None = None
    recipe_id: str | None = None
    recipe_version: int | None = None


class Interval(BaseModel):
    valid_from: datetime
    valid_to: datetime | None = None


class WeightComponents(BaseModel):
    """Inputs to `01_DOMAIN_MODEL.md` §6.1's weight formula, captured at
    load time. `weight` on `Edge` is a load-time snapshot, using the
    corpus as it stood then — never treat it as frozen ground truth. These
    counts are what make an honest recompute (the working set; a corpus
    that has since grown) arithmetic over stored numbers rather than a
    full corpus rescan."""

    occurrences: int = Field(ge=0)
    corpus_pair_count: int = Field(ge=0)  # this pair's occurrences, corpus-wide, this edge type
    corpus_source_degree: int = Field(ge=0)  # source's occurrences of this edge type, corpus-wide
    corpus_target_degree: int = Field(ge=0)
    corpus_total_occurrences: int = Field(ge=0)  # every edge of this type, corpus-wide
    computed_at: datetime  # when the corpus-wide counts above were taken


class Edge(BaseModel):
    id: EdgeId
    type: str
    source: NodeId
    target: NodeId
    properties: dict[str, Any] = Field(default_factory=dict)
    interval: Interval | None = None
    occurrences: int = 1
    weight: float = 0.0
    weight_components: WeightComponents | None = None
    provenance: Provenance
    handling: Handling
    audit: AuditStub


class EdgeWrite(BaseModel):
    type: str
    source: NodeId
    target: NodeId
    properties: dict[str, Any] = Field(default_factory=dict)
    interval: Interval | None = None
    occurrences: int = 1
    provenance: Provenance
    handling: Handling
    created_by: PrincipalId
    load_id: str | None = None
    recipe_id: str | None = None
    recipe_version: int | None = None


# --- Principal (00_ARCHITECTURE.md §5) ----------------------------------


class Principal(BaseModel):
    """Resolved by the Conduit from the session token and passed into every
    `GraphPort` read. Two axes gate visibility (`01_DOMAIN_MODEL.md` §2.2):
    `clearance` is a classification value from the deployment's active
    handling scheme (`Handling.classification`), dominance-ordered;
    `receivable_handling_codes` is the set of `Handling.handling_code`
    values this principal may receive at all — checked only for a
    `handling_code` whose scheme entry is `dissemination: restricted`, and
    then also scoped to `org_unit` matching the record's `owning_unit` or
    `originator`. `action_code` and `sanitisation_code` never gate a read —
    the first constrains what may be *done*, the second is the export
    gate's reason for existing."""

    id: PrincipalId
    clearance: str
    org_unit: OrgUnitId
    receivable_handling_codes: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


# --- GraphPort request/response types (00_ARCHITECTURE.md §2.1) --------


class ExpandRequest(BaseModel):
    node_ids: list[NodeId]
    depth: int = Field(default=1, ge=1, le=4)
    edge_types: list[str] | None = None
    direction: Literal["out", "in", "both"] = "both"
    temporal_window: Interval | None = None


class PathRequest(BaseModel):
    source: NodeId
    target: NodeId
    max_hops: int = Field(default=6, ge=1)
    k: int = Field(default=1, ge=1)
    edge_types: list[str] | None = None


class Path(BaseModel):
    nodes: list[NodeId]
    edges: list[EdgeId]
    length: int


class PatternNode(BaseModel):
    var: str
    entity_type: str | None = None


class PatternEdge(BaseModel):
    edge_type: str
    from_var: str
    to_var: str


class PatternQuery(BaseModel):
    """A bounded pattern description the Conduit compiles from a fixed set
    of builders — never free-form Gremlin (ADR-003)."""

    nodes: list[PatternNode]
    edges: list[PatternEdge]
    limit: int = Field(default=1000, ge=1)


class NeighbourhoodStats(BaseModel):
    node_id: NodeId
    degree: int
    degree_by_type: dict[str, int] = Field(default_factory=dict)


class Subgraph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    filtered_count: int = 0


ALL_MODELS: tuple[type[BaseModel], ...] = (
    PropertyDef,
    ResolutionConfig,
    EntityTypeDef,
    EdgeTypeDef,
    OntologySchema,
    SchemaReport,
    Handling,
    SourceRef,
    Provenance,
    ResolutionState,
    AuditStub,
    Node,
    NodeWrite,
    Interval,
    WeightComponents,
    Edge,
    EdgeWrite,
    Principal,
    ExpandRequest,
    PathRequest,
    Path,
    PatternNode,
    PatternEdge,
    PatternQuery,
    NeighbourhoodStats,
    Subgraph,
)
