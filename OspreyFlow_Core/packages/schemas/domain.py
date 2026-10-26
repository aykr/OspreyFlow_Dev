"""The real domain model — `spec/01_DOMAIN_MODEL.md`.

Source of truth for `GraphPort`'s DTOs and the node/edge shape every adapter
writes and reads. TypeScript types are generated from these
(`generate_ts.py`); a drift between the two fails the build
(`tools/schemas_check.py`).

Supersedes packages/schemas/_phase0_placeholders.py (since removed) for everything
`GraphPort` references. `_pending_port_placeholders.py` (the same idea for
`ComputePort`/`ModelPort`, ahead of their own real schemas) is gone for
good as of Phase 7 Stage 2 — see `tests/schemas/test_placeholder_lifecycle.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Final, Literal

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
type JudgementId = str
type GapId = str
type AssumptionId = str


# --- Ontology (01_DOMAIN_MODEL.md §1) -----------------------------------


class PoleClass(StrEnum):
    """The five-class upper ontology. Closed: a deployment may add entity
    types, never a sixth POLE class — `01_DOMAIN_MODEL.md` §1.1."""

    PERSON = "person"
    OBJECT = "object"
    LOCATION = "location"
    EVENT = "event"
    ORGANISATION = "organisation"


#: The order the POLE summary lists the five classes in (ADR-126 decision 4).
POLE_CLASS_ORDER: tuple[PoleClass, ...] = (
    PoleClass.PERSON,
    PoleClass.OBJECT,
    PoleClass.LOCATION,
    PoleClass.EVENT,
    PoleClass.ORGANISATION,
)

# The nine categorical data channels the design system defines
# (`spec/design/tokens.css`), checked for protanopia/deuteranopia
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
    #: The drawing inside the shape on the canvas (ADR-079). One of the names in the ontology JSON
    #: Schema's closed list, checked there at load; `None` draws the shape alone.
    icon: str | None = None
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
    #: ADR-081. `direct` means a loaded, established record stands behind a link of this type;
    #: `probabilistic` means it is statistically derived or an analyst's declaration. The ontology
    #: JSON Schema requires it on every authored type (an ontology that omits it is refused at
    #: load). It is `None` only for `NOT_SAME_AS`, an analyst's judgement that two nodes are
    #: different, which is outside the rule (ADR-081 Amendment 1); `SAME_AS` is `probabilistic`.
    #: The Glass draws a Direct link solid and a Probabilistic one dotted; the style is not
    #: authored.
    basis: Literal["direct", "probabilistic"] | None = None
    #: One of the nine data-channel names (`DATA_CHANNELS`), checked at load by the JSON Schema;
    #: `None` keeps the Glass's ordinary line colour.
    colour: str | None = None
    #: A whole number from 1 to 5 drawn as the line's width at the default weight; a link's weight
    #: scales it (ADR-081 Amendment 1). `None` keeps the weight-only width.
    thickness: int | None = Field(default=None, ge=1, le=5)
    #: ADR-091. The name shown to a person, in sentence case ("Communicated with"); `name` stays
    #: the key stored on every link. `None` lets the Glass derive it from `name`.
    label: str | None = Field(default=None, pattern=r"\S")
    #: ADR-090 Amendment 1, by alias (owner, 5 October 2026): names this type also answers to in
    #: the graph store. A proposal renamed at promotion keeps its links under its old name, which
    #: becomes an alias of the promoted type, so every link, restricted ones included, reads and
    #: is found as the new type with nothing rewritten. New links are written under `name` only.
    aliases: list[str] = Field(default_factory=list)
    #: ADR-090 decision 6: an analyst-proposed type an administrator promoted as Direct is Direct
    #: only from this moment; a link of it written before stays probabilistic (ADR-081 decision 2).
    direct_since: datetime | None = None
    #: ADR-090 decision 4: proposed by an analyst, not authored in `default.yaml`.
    analyst_defined: bool = False
    #: ADR-090: a proposal's own storage label, declared so its links can be written, never
    #: offered or shown; its links read as the name it is an alias of
    #: (`OntologySchema.storage_aliases`).
    hidden: bool = False
    properties: list[PropertyDef] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class OntologySchema(BaseModel):
    """The loaded, validated ontology — what `GraphPort.apply_schema` takes
    and what the schema/migration runner turns into vertex/edge types and
    the indexes in `04_VAULT_BACKEND.md` §1.4."""

    version: int
    entity_types: list[EntityTypeDef]
    edge_types: list[EdgeTypeDef]
    #: ADR-090: each proposal's storage label -> the link-type name its links read as (the
    #: proposal's name while pending, rejected, withdrawn or retired; the promoted name once
    #: promoted,
    #: merged or renamed). Applied by the graph store, so nothing is ever rewritten.
    storage_aliases: dict[str, str] = Field(default_factory=dict)
    #: ADR-090 decision 2: rises by one at every promotion and retirement; the version does not.
    overlay_revision: int = 0
    #: Each composed domain pack's name and `pack_version` (ADR-120 D10), so a recipe can pin the
    #: pack versions it was published against; empty for the core alone.
    packs: dict[str, int] = Field(default_factory=dict)
    #: Each entity and link type a composed pack defines (not widens) → that pack's name
    #: (ADR-120 Amendment 1), so a recipe pins the packs whose types it writes.
    type_packs: dict[str, str] = Field(default_factory=dict)

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
    #: record is invisible to an unauthorised one — `services/ingest/load_revert.py`
    #: is the only writer, via `GraphPort.revert_elements`
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
    #: ADR-099: the datasets this element belongs to. A write names its own; a second write of the
    #: same element adds to them, never replaces them. A case reads only elements of its datasets.
    datasets: list[str] = Field(default_factory=list)


class NodeWrite(BaseModel):
    """Pre-persistence `Node`: `id` (a ULID) and `created_at` are assigned by
    the Conduit — `packages/conduit_common/identity.py` — never by an
    adapter (`01_DOMAIN_MODEL.md` §2: "assigned by the Conduit, never by a
    source system"). The adapter's own `AuditStub` still owns `revision`,
    since only it knows a node's current revision at write time."""

    id: NodeId
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
    handling: Handling
    resolution: ResolutionState = Field(default_factory=ResolutionState)
    created_by: PrincipalId
    created_at: datetime
    load_id: str | None = None
    recipe_id: str | None = None
    recipe_version: int | None = None
    #: ADR-099: the datasets this element belongs to. A write names its own; a second write of the
    #: same element adds to them, never replaces them. A case reads only elements of its datasets.
    datasets: list[str] = Field(default_factory=list)


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
    #: ADR-120 D3: the weights-file version and rule this weight was computed under,
    #: `"<version>/<rule name>"`. `None` on a component stored before then (computed under the
    #: uncalibrated curve that preceded it); ADR-120 does not recompute those weights (`GraphPort`
    #: has no in-place edge update, and a recompute is its own record).
    parameter_set: str | None = None
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
    #: ADR-122 (Amendment 1): corpus-wide counts, never serialised. Readable in Python, where the
    #: weight is computed and recomputed; excluded from every dump, so no response can carry them.
    weight_components: WeightComponents | None = Field(default=None, exclude=True)
    #: ADR-081 step B. The link's own basis, where one was written: `probabilistic` on a link of a
    #: Direct type that is statistically derived or that an analyst declared so (with a reason,
    #: kept in the link's change history). `None` means the link takes its type's basis, which is
    #: what every link written by a loader or the resolution engine carries. A person never
    #: promotes a link to Direct, so `direct` is never written over a probabilistic type;
    #: `effective_basis` is the one place that reads the two together.
    basis: Literal["direct", "probabilistic"] | None = None
    provenance: Provenance
    handling: Handling
    audit: AuditStub
    #: ADR-099: the datasets this element belongs to. A write names its own; a second write of the
    #: same element adds to them, never replaces them. A case reads only elements of its datasets.
    datasets: list[str] = Field(default_factory=list)


def effective_basis(
    link_basis: Literal["direct", "probabilistic"] | None,
    edge_type: EdgeTypeDef | None,
    *,
    written_at: datetime | None = None,
) -> Literal["direct", "probabilistic"] | None:
    """What stands behind a link, read from the link and its type together (ADR-081 decision 2).

    A link of a Probabilistic type is always probabilistic, whatever is stored on it; a link of a
    Direct type is direct unless it carries its own probabilistic mark, or was written before the
    type was promoted as Direct (`direct_since`, ADR-090 decision 6: a person never promotes a
    link to Direct); a type with no basis (`NOT_SAME_AS`, or one the ontology does not know) gives
    none."""
    type_basis = edge_type.basis if edge_type is not None else None
    if type_basis == "probabilistic":
        return "probabilistic"
    if link_basis == "probabilistic":
        return "probabilistic"
    since = edge_type.direct_since if edge_type is not None else None
    if type_basis == "direct" and since is not None and (written_at is None or written_at < since):
        return "probabilistic"
    return type_basis


class EdgeWrite(BaseModel):
    """Pre-persistence `Edge`: `id` and `created_at` are Conduit-assigned,
    the same as `NodeWrite` — see its docstring."""

    id: EdgeId
    type: str
    source: NodeId
    target: NodeId
    properties: dict[str, Any] = Field(default_factory=dict)
    interval: Interval | None = None
    occurrences: int = 1
    #: The link's own basis (see `Edge.basis`); `None`, the usual case, means its type's.
    basis: Literal["direct", "probabilistic"] | None = None
    provenance: Provenance
    handling: Handling
    created_by: PrincipalId
    created_at: datetime
    load_id: str | None = None
    recipe_id: str | None = None
    recipe_version: int | None = None
    #: ADR-099: the datasets this element belongs to. A write names its own; a second write of the
    #: same element adds to them, never replaces them. A case reads only elements of its datasets.
    datasets: list[str] = Field(default_factory=list)


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
    #: ADR-099, the third axis: the datasets of the case this principal reads for. `None` is
    #: unlimited and only the Conduit's own background work reads so; the Conduit's principal for a
    #: request always carries a list, empty outside a case, and an empty list sees nothing.
    datasets: list[str] | None = None


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
    #: `le=8` — a real, small margin over `01_DOMAIN_MODEL.md` §6.3's own domain-modelled default
    #: of 6, not a multiplier: a `repeat().until()` traversal's cost scales with branching factor
    #: raised to `max_hops`, not linearly, so this is a disclosed, reasoned-but-unmeasured ceiling
    #: (Phase 7 Stage 5) in the same spirit as `01_DOMAIN_MODEL.md` §8.2's `supersede_node` figure
    #: and ADR-025's `LOCK_TTL_SECONDS` — a real number retires the guess; none exists yet.
    max_hops: int = Field(default=6, ge=1, le=8)
    #: `le=10` — past which an analyst is not meaningfully paging through alternative routes.
    #: Result size can never exceed `k` by construction (`.limit(k)` in the compiled query), so
    #: this bounds request cost, not a hidden larger population (`06_DECISIONS.md` ADR-033's own
    #: "THIRD" reasoning has the full argument for why paths need no `match_count`-style preview).
    k: int = Field(default=1, ge=1, le=10)
    edge_types: list[str] | None = None


class Path(BaseModel):
    """`06_DECISIONS.md` ADR-033: hydrated, not bare ids — `nodes`/`edges` carry the same shape
    `Subgraph` already does, because the one real interactive caller (the pathfinder,
    `GlassCanvas.tsx`) needs a node's own `type` to render it at all, and a node not already in
    the working set has no other source for its own properties. Widened, not redesigned: `length`
    is unchanged, and every existing caller (only conformance tests before this stage) reads
    `.length`, never `.nodes`/`.edges`, so this breaks nothing that exists."""

    nodes: list[Node]
    edges: list[Edge]
    length: int


#: ADR-116: the degree a Find connections search looks to when none is asked (01 §6.3's default),
#: and the furthest it may be asked to look (ADR-033's ceiling, `PathRequest.max_hops`).
CONNECTIONS_DEFAULT_REACH: Final[int] = 6
CONNECTIONS_CEILING: Final[int] = 8
#: ADR-116 decision 3: the routes shown at one degree, past which the answer says more exist.
CONNECTIONS_SHOWN: Final[int] = 10


class RoutesAtLength(BaseModel):
    """ADR-116: the simple routes of exactly `length` links between two nodes, as the reader may see
    them — at most the number asked for, and `more` when others exist beyond it (rule 2: never cut
    silently)."""

    length: int
    paths: list[Path]
    more: bool


class ConnectionsRequest(BaseModel):
    """ADR-116 decision 6. With no `degree`, the fewest degrees that connect the two, looked for up
    to `CONNECTIONS_DEFAULT_REACH`; with one, the routes at exactly that degree."""

    source: NodeId
    target: NodeId
    degree: int | None = Field(default=None, ge=1, le=CONNECTIONS_CEILING)
    edge_types: list[str] | None = None

    @model_validator(mode="after")
    def _two_ends(self) -> ConnectionsRequest:
        if self.source == self.target:
            raise ValueError("From and To are the same node; choose two different ones")
        return self


class Connections(BaseModel):
    """ADR-116: the answer. `degree` is `None` when no route was found up to `searched_to`; a hidden
    end and an unknown one answer alike, since no route can pass through a node the reader cannot
    see (rule 3)."""

    degree: int | None
    paths: list[Path]
    more: bool
    searched_to: int


class PatternNode(BaseModel):
    var: str
    entity_type: str | None = None
    #: Pins this variable to one already-known node — `01_DOMAIN_MODEL.md` §8.1's own widening
    #: (Phase 7 Stage 4, `06_DECISIONS.md` ADR-030): a pattern with more than one root is
    #: only compiled
    #: when every root beyond the first is pinned this way (B19's own shape — "the two principal
    #: endpoints" are nodes the analyst already selected, not an open type). An unpinned second
    #: root remains unsupported — confirmed empirically that ArcadeDB's own Gremlin `match()` step
    #: cannot introduce a genuinely independent second enumeration, so there is no general join to
    #: fall back to.
    node_id: str | None = None


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


class SavedPattern(BaseModel):
    """A persisted `PatternQuery` — Phase 7 Stage 4's own "saveable ... and versioned" promise
    (`02_GLASS_FRONTEND.md` §3.3), closed for save/load/list/version by `06_DECISIONS.md` ADR-032/
    036/040. `pattern_id` is stable across saves; `id` and `version` identify one specific save.
    Deliberately carries `owner_id` and nothing shaped like `Handling.owning_unit` or a share
    target — ADR-036 and ADR-040 both require a saved pattern readable only by its own owner until
    ADR-040 (pattern sharing) is accepted; there is no broader-audience field to widen by mistake
    because none exists yet."""

    id: str
    pattern_id: str
    version: int = Field(ge=1)
    name: str
    owner_id: str
    created_at: datetime
    definition: PatternQuery
    #: ADR-099 Amendment 3: the dataset of the case it was saved in; its owner finds it only in a
    #: case reading that dataset. `None` for one saved before, until `stamp_datasets` places it.
    dataset_id: str | None = None


class AlertMode(StrEnum):
    #: Full evidence — the referents named below are re-checked against the reading principal's
    #: own access at read time (`06_DECISIONS.md` ADR-039), never trusted from write time.
    FULL = "full"
    #: `06_DECISIONS.md` ADR-038's `notify` policy stub — written when the triggering referent was
    #: outside the recipient's access at write time. Carries no referent of any kind (not even the
    #: identifier the analyst supplied) — `referent_node_ids` is always empty for this mode, by
    #: construction, not merely by convention a caller must remember to honour.
    NOTIFY_STUB = "notify_stub"


class Alert(BaseModel):
    """A persisted alert row — `06_DECISIONS.md` ADR-038/039, Phase 7 Stage 6a's own foundation.
    Stores references to evidence, never copies (`rule_id` plus `referent_node_ids`) — access is
    re-checked at read time against those referents, not trusted from whatever was true when this
    row was written. `NOTIFY_STUB` rows never carry a referent at all, enforced by every producer
    this stage builds (`services/api/alerts.py`'s own `record_match` is the one place a row is
    constructed), not merely a convention this model documents without holding to.

    `investigation_id` (Stage 6c): a best-effort audit-shaped hint, not an access-control scope —
    the same distinction `run_studio_recipe`'s own docstring already draws for `EventRecord.
    investigation_scope`. Threaded from `ChangeStreamEntry.investigation_id`, itself threaded from
    whichever producer route was investigation-scoped at the point the triggering write happened
    (ingest); `None` for a producer that genuinely has no single investigation in scope (the
    corpus-wide resolution trigger). B14's "jump" branches a new investigation from this field via
    `InvestigationStore.create(principal, branched_from=...)` — the identical mechanism
    `branch_investigation` already uses, not new investigation-linking infrastructure. `None` here
    means the jump starts an unbranched investigation instead of one carrying that link, disclosed
    to the analyst rather than silently omitted."""

    id: str
    rule_id: str
    owner_id: str
    mode: AlertMode
    referent_node_ids: list[NodeId] = Field(default_factory=list)
    investigation_id: str | None = None
    created_at: datetime
    #: ADR-099 Amendment 3: the dataset of the case it was made in; read only in a case reading
    #: it. `None` for one made before, until `stamp_datasets` places it.
    dataset_id: str | None = None
    #: ADR-109 ruling 2 — an alert a typology rule raised carries what makes it explainable:
    #: the typology, the finding in words, the links and the events (each transaction) it cites,
    #: the span those events cover, the trigger point the rule ran at, and the `Alert` graph node
    #: written alongside it (`None` where that node was withheld; see `rule_evaluation.py`).
    #: Every reference is re-checked against the reader at read time (ADR-039), never trusted.
    typology: str | None = None
    words: str | None = None
    edge_ids: list[EdgeId] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    window: Interval | None = None
    trigger: RuleTrigger | None = None
    alert_node_id: NodeId | None = None
    #: ADR-109 phase B — the case team's triage of a rule-raised alert (ruling 3): open, claimed by
    #: one member, or closed with a disposition and its reason. A true positive is the human
    #: confirmation that makes the `Alert` node asserted (rule 5); a false positive retracts it.
    status: AlertStatus = "open"
    assignee: str | None = None
    disposition: AlertDisposition | None = None
    disposition_reason: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


#: ADR-126 decision 1: the domain packs a case can carry, defined once here. `ontology.packs`
#: sets `PACK_NAMES = get_args(DomainPack)`, so the values live in one place and `ontology` keeps
#: importing `schemas`, never the other way. Empty means the POLE core model alone.
DomainPack = Literal["fibo", "niem", "stix"]

#: `Hotlist.status`/`Monitor.status` — ADR-036's own "the monitor stops" (extended in Stage 6b to
#: a hotlist's identical owner-principal-unresolvable case) must be surfaced somewhere the analyst
#: or another owner can see it, not left as a silent skip with no visible state change. Written by
#: the evaluator (`services/api/evaluation.py`), read by the Stage 6c list panels.
WatchStatus = Literal["active", "stopped"]


class Hotlist(BaseModel):
    """A watched identifier — `02_GLASS_FRONTEND.md` §3.3: "A list of identifiers with an owner
    and a review date." Phase 7 Stage 6b/6c. Deliberately bare: an `identifier` is a normalised
    value string (the same `value_normalised` shape `Endpoint`'s own identifiers already use, not
    a node id — a hotlist entry can be created before anything resolves to a node at all, per
    ADR-038's own "an analyst can hotlist a bare phone number read off a warrant before it
    resolves to anything they can see"), an `owner_id`, and a `review_date` — no handling ceiling
    (`06_DECISIONS.md` ADR-038's option (c), recorded there as not selected, not built here).

    `status` (Stage 6c): `06_DECISIONS.md` ADR-036's own "the monitor stops" requirement, extended
    here — see `WatchStatus`'s own docstring. The investigation a jumped-to alert branches into
    comes from `Alert.investigation_id` (the *triggering* event's own investigation, threaded
    through `ChangeStreamEntry`), not from this row — a hotlist is not investigation-scoped and
    outlives any one investigation it happened to be set from."""

    id: str
    #: The canonical form (ADR-127 decision 7(b)), which a node's `value_normalised` is compared
    #: with: `+447700900310` for a number typed `07700 900310`. A text no adapter accepts is kept
    #: as written.
    identifier: str
    #: What the analyst typed, kept for display (`identifier` is what is matched). `None` only for a
    #: row from before the identifier was canonicalised and not yet read by the store.
    identifier_typed: str | None = None
    #: Whether `identifier` is canonical: `False` for a text no adapter would accept, kept as
    #: written and matched only on that exact text. `None` for a row not yet read by the store.
    identifier_canonical: bool | None = None
    owner_id: str
    review_date: date
    status: WatchStatus = "active"
    created_at: datetime
    #: ADR-099 Amendment 3: the dataset of the case it was made in; read only in a case reading
    #: it. `None` for one made before, until `stamp_datasets` places it.
    dataset_id: str | None = None


class Monitor(BaseModel):
    """A saved pattern being watched — `02_GLASS_FRONTEND.md` §3.3: "A saved visual query run...
    against new data." Phase 7 Stage 6b/6c. References a `SavedPattern` by `pattern_id`, never
    copies its own definition — `PatternStore.get_authorized` is the one place a monitor's own
    query is ever read from, the same "resolved fresh, never cached" discipline `06_DECISIONS.md`
    ADR-036 requires of a monitor's *access*, extended here to its own *definition* too, so an
    edited-then-resaved pattern is evaluated as it now reads, not as it read when the monitor was
    turned on. `owner_id` is redundant with `SavedPattern.owner_id` (a monitor cannot be turned on
    for a pattern its own creator does not own — checked at creation, not re-derived from the
    pattern on every read) but stored directly so a monitor row is self-describing without a join
    for the common "list my own monitors" case.

    `status` (Stage 6c): ADR-036's own binding requirement, quoted directly: "A stopped monitor is
    surfaced as stopped somewhere the analyst or another owner can see it (the monitor list, or the
    alert inbox) rather than silently producing nothing forever with no visible state change."
    Before Stage 6c this was true only of `evaluate_monitors_for_entry`'s own in-memory skip;
    nothing persisted or rendered it — see `WatchStatus`'s own docstring, and `Hotlist`'s own note
    on why the jump's investigation link lives on `Alert`, not here."""

    id: str
    pattern_id: str
    owner_id: str
    status: WatchStatus = "active"
    created_at: datetime
    #: ADR-099 Amendment 3: the dataset of the case it was made in; read only in a case reading
    #: it. `None` for one made before, until `stamp_datasets` places it.
    dataset_id: str | None = None


# --- Typology rules (06_DECISIONS.md ADR-109) ---------------------------------

#: The closed vocabulary of typologies a rule may run — `services/ingest/typologies.py`'s three
#: rules. Rule 8: no expression language; a rule is one of these with its parameters.
TypologyName = Literal[
    "structuring",
    "rapid_movement",
    "circular_flow",
    "kyc_screening",
    "shared_attributes",
    "document_verification",
    "pattern",
]
#: ADR-109 ruling 1: the rule chooses where it runs. `pre_commit` judges the incoming rows inside
#: the load (a hit loads with its alert; a failure holds the rows); `post_commit` runs on the
#: change stream after the load commits, best-effort.
RuleTrigger = Literal["pre_commit", "post_commit"]
RuleStatus = Literal["active", "retired"]
AlertStatus = Literal["open", "claimed", "closed"]
AlertDisposition = Literal["true_positive", "false_positive"]


class StructuringParams(BaseModel):
    typology: Literal["structuring"] = "structuring"
    #: The reportable amount; each movement below it, together above it, is the finding.
    threshold: float = Field(gt=0)
    window_days: int = Field(ge=1, le=366)
    minimum_count: int = Field(ge=2, le=1000)


class RapidMovementParams(BaseModel):
    typology: Literal["rapid_movement"] = "rapid_movement"
    within_hours: float = Field(gt=0, le=744)
    #: The share of an incoming amount that must leave again for the account to be a pass-through.
    keep_fraction: float = Field(gt=0, le=1)


class CircularFlowParams(BaseModel):
    typology: Literal["circular_flow"] = "circular_flow"
    max_hops: int = Field(ge=2, le=6)
    #: How far back the flows a cycle may be made of are read.
    window_days: int = Field(ge=1, le=366)


class KycScreeningParams(BaseModel):
    """ADR-109 phase F (the KYC addendum's Component 6): a newly loaded person or organisation
    screened against the deployment's screening lists, and — for an organisation — each natural
    person who ultimately owns at least `owner_threshold` of it, or controls it."""

    typology: Literal["kyc_screening"] = "kyc_screening"
    min_score: float = Field(default=0.9, ge=0.5, le=1)
    screen_owners: bool = True
    owner_threshold: float = Field(default=25.0, gt=0, le=100)


EndpointKindScreened = Literal["msisdn", "email", "ip", "handle"]


class SharedAttributesParams(BaseModel):
    """Component 6's synthetic-identity check: a new customer's phone, email, IP address or handle
    already used by at least `min_others` other customers."""

    typology: Literal["shared_attributes"] = "shared_attributes"
    min_others: int = Field(default=3, ge=1, le=100)
    kinds: list[EndpointKindScreened] = Field(
        default_factory=lambda: list[EndpointKindScreened](["msisdn", "email", "ip"]),
        min_length=1,
    )


class DocumentVerificationParams(BaseModel):
    """Component 7: a new customer with no valid verifying document — none, or each one expired
    or marked fraudulent."""

    typology: Literal["document_verification"] = "document_verification"


class PatternRuleParams(BaseModel):
    """ADR-109 phase D, the no-code typology builder: a sub-graph drawn in the query builder and
    saved (a `SavedPattern` the deployer owns, read afresh at each evaluation — ADR-036's own
    discipline for monitors), deployed as a rule. Matched against the stored graph, so it runs
    after commit only. A match larger than `max_matches` nodes is refused in words, never alerted on
    in part (rule 2)."""

    typology: Literal["pattern"] = "pattern"
    pattern_id: str = Field(min_length=1)
    max_matches: int = Field(default=200, ge=1, le=1000)


TypologyParams = Annotated[
    StructuringParams
    | RapidMovementParams
    | CircularFlowParams
    | KycScreeningParams
    | SharedAttributesParams
    | DocumentVerificationParams
    | PatternRuleParams,
    Field(discriminator="typology"),
]


class TypologyRuleInput(BaseModel):
    """What a case Author deploys (ADR-109 ruling 4): a typology with its parameters and the
    trigger point it runs at. `budget_ms` bounds a pre-commit evaluation; overrunning it holds the
    rows it could not judge (ruling 1, fail closed)."""

    name: str = Field(min_length=1, max_length=120)
    params: TypologyParams
    trigger: RuleTrigger = "post_commit"
    budget_ms: int = Field(default=5000, ge=100, le=60000)

    @model_validator(mode="after")
    def _a_drawn_pattern_runs_after_commit(self) -> TypologyRuleInput:
        if self.params.typology == "pattern" and self.trigger != "post_commit":
            raise ValueError(
                "a drawn pattern is matched against the stored graph, so it runs after commit"
            )
        return self


class TypologyRule(TypologyRuleInput):
    """A deployed rule. It belongs to the case it was deployed in and evaluates as its deployer's
    principal, resolved fresh at each evaluation (ADR-036, unchanged by ADR-109)."""

    id: str
    investigation_id: str
    owner_id: str
    status: RuleStatus = "active"
    created_at: datetime
    retired_at: datetime | None = None
    dataset_id: str | None = None


HeldRowStatus = Literal["held", "released", "rejected"]


class HeldRow(BaseModel):
    """A source row a pre-commit rule could not judge — it errored or overran its budget — held
    out of the graph for a reviewer (ADR-109 ruling 1, fail closed). Carries the row as read and its
    original row number, so a release loads it with its provenance unchanged; `handling` is the
    marking the recipe would have given it, and a reader is filtered by it (rule 3)."""

    id: str
    investigation_id: str
    recipe_id: str
    recipe_version: int
    load_id: str
    source: str
    row_index: int
    row: dict[str, str]
    rule_id: str
    reason: str
    handling: Handling
    status: HeldRowStatus = "held"
    held_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    dataset_id: str | None = None


class RuleAuditEntry(BaseModel):
    """One line of a case's rule audit (ADR-109 ruling 1): a deploy, retire, evaluation, firing,
    failure, hold, release or rejection. Read only by the case's Authors and the deployment admin,
    and an entry naming a node the reader cannot see is withheld whole (rule 3)."""

    recorded_at: datetime
    principal_id: str
    #: Who acted, by name (ADR-106 decision 3: looked up only for ids this page serves); absent
    #: where the directory has none, and the Glass then shows the id.
    principal_name: str | None = None
    action: str
    detail: dict[str, Any] = Field(default_factory=dict)
    result_cardinality: int = 0


class ReportCount(BaseModel):
    """One labelled figure of a report (ADR-111): a fixed label and a count, never free text."""

    label: str
    value: int = Field(ge=0)


class WeekCount(BaseModel):
    """Alerts raised in one week (Monday to Sunday) of one typology, as the reader sees them."""

    week_start: date
    typology: str
    count: int = Field(ge=0)


class OutcomeCount(BaseModel):
    """Where one typology's alerts of the period stand: open, claimed, closed true or false."""

    typology: str
    open: int = Field(default=0, ge=0)
    claimed: int = Field(default=0, ge=0)
    true_positive: int = Field(default=0, ge=0)
    false_positive: int = Field(default=0, ge=0)


class HeldFigures(BaseModel):
    """The case's held rows by what became of them — for Editors and above only, as the Held rows
    tab is (ADR-111 decision 2)."""

    held: int = Field(ge=0)
    released: int = Field(ge=0)
    rejected: int = Field(ge=0)


class KycFigures(BaseModel):
    """The case's customers — people and organisations holding a verifying document — by KYC
    status and risk band, each assessed as the reader at the moment of reading."""

    customers: int = Field(ge=0)
    verified: int = Field(ge=0)
    unverified: int = Field(ge=0)
    by_band: list[ReportCount] = Field(default_factory=list)


class PoleTypeCount(BaseModel):
    """How many nodes of one entity type the reader can see (ADR-126 decision 4). `entity_type` is
    a closed ontology type name, never an entity's own text."""

    entity_type: str
    count: int = Field(ge=1)


class PoleClassCount(BaseModel):
    """One POLE class: its total, and its types largest first, then by name, with no zero rows."""

    pole_class: PoleClass
    total: int = Field(ge=0)
    types: list[PoleTypeCount] = Field(default_factory=list)


class PoleFigures(BaseModel):
    """The POLE summary of a case (ADR-126 decision 4), from the kept per-access-class counts the
    Explore page reads: the reader's own, for the case's datasets, never a second count.

    `classes` is always the five classes in the order person, object, location, event,
    organisation. `other` holds stored types the current ontology does not know, so no node
    vanishes from the figures. `links` counts links of every type that is not `system`, a type the
    ontology does not know included. `Alert` is in no figure: alerts are the Figures tab's own
    subject. `counted_at` is when the kept counts were computed."""

    classes: list[PoleClassCount]
    other: list[PoleTypeCount] = Field(default_factory=list)
    links: int = Field(ge=0)
    counted_at: datetime

    @model_validator(mode="after")
    def _the_five_classes_in_order(self) -> PoleFigures:
        held = [c.pole_class for c in self.classes]
        if sorted(held, key=str) != sorted(POLE_CLASS_ORDER, key=str):
            raise ValueError("the POLE figures hold exactly the five classes, each once")
        if held != list(POLE_CLASS_ORDER):
            raise ValueError(
                "the POLE figures list the classes in the order "
                + ", ".join(c.value for c in POLE_CLASS_ORDER)
            )
        return self


class ReportFigures(BaseModel):
    """A case's report (`06_DECISIONS.md` ADR-111): the Reports view and the dashboards' feed are
    both this, from one computation, so they cannot disagree. Every figure is counted as its
    reader — an alert the reader cannot see whole is in no total and no bucket (rule 3). Figures
    only: labels, dates and numbers, never a name, an identifier or an alert's words."""

    period_weeks: int = Field(ge=1, le=52)
    as_of: date
    generated_at: datetime
    alerts_total: int = Field(ge=0)
    alerts_by_week: list[WeekCount] = Field(default_factory=list)
    open_by_age: list[ReportCount] = Field(default_factory=list)
    outcomes: list[OutcomeCount] = Field(default_factory=list)
    held: HeldFigures | None = None
    #: ADR-126 decision 3: set when `fibo` is among the case's packs; `None` is "this case has no
    #: KYC card", not zero customers.
    kyc: KycFigures | None = None
    #: Set when the case's packs are anything other than exactly `[fibo]`.
    pole: PoleFigures | None = None


ReportOption = Literal["shorter_period", "fewer_typologies"]
_REPORT_OPTIONS: tuple[ReportOption, ...] = ("shorter_period", "fewer_typologies")


class ReportLimitExceeded(BaseModel):
    """A report past its bound answers this, never a partial figure presented as whole (rule 2).
    `would_be` counts only what the reader can see, so the refusal itself discloses nothing."""

    error: Literal["limit_exceeded"] = "limit_exceeded"
    cap_kind: Literal["alerts", "customers"]
    cap: int
    would_be: int
    options: list[ReportOption] = Field(default_factory=lambda: list(_REPORT_OPTIONS))


class RuleAuditPage(BaseModel):
    """A page of a case's rule audit, newest first, with the total of what the reader may see —
    an entry withheld from them is neither on the page nor in the total (rule 3)."""

    entries: list[RuleAuditEntry] = Field(default_factory=list)
    total: int = Field(ge=0)


class QueuedAlert(BaseModel):
    """One row of the case's alert queue: the alert, and its finding in words with the entities
    named as the reader sees them (never an id the reader would have to look up)."""

    alert: Alert
    summary: str


class ExplainedTransaction(BaseModel):
    """One transaction an alert cites, as the reader may read it: the link it is on, its ends,
    when, and how much."""

    event_id: str
    edge_id: EdgeId
    source_id: NodeId
    target_id: NodeId
    occurred_at: datetime
    amount: float | None = None


class AlertExplanation(BaseModel):
    """What fired an alert, for the reader (ADR-109 phase B): the entities it concerns and its
    own node, the links it cites (and the `ALERTED_ON` links), and each transaction it cites. Every
    part is read as the reader; an alert any part of which the reader cannot see is not shown at
    all (ADR-039's all-or-nothing, rule 3)."""

    alert: Alert
    summary: str
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    transactions: list[ExplainedTransaction] = Field(default_factory=list)


class AlertDispositionInput(BaseModel):
    disposition: AlertDisposition
    reason: str = Field(min_length=1, max_length=2000)


class KycDocument(BaseModel):
    """A document verifying a customer, and whether it still does."""

    node_id: NodeId
    title: str | None = None
    document_kind: str | None = None
    expires_on: date | None = None
    state: Literal["valid", "expired", "fraudulent"]


class RiskFactor(BaseModel):
    """One reason a customer's baseline risk is what it is, with its weight and its words."""

    factor: str
    weight: int
    words: str


class KycStatus(BaseModel):
    """A customer's KYC status and baseline risk assessment (ADR-109 phase F, rulings 7 and 10):
    computed at each read, as the reader reads the graph, never stored. `verified` while at least
    one verifying document is valid — so an expiry or a fraud mark downgrades it the moment it
    applies, with nothing written."""

    node_id: NodeId
    name: str
    status: Literal["verified", "unverified"]
    documents: list[KycDocument] = Field(default_factory=list)
    risk_score: int = 0
    risk_band: Literal["low", "medium", "high"] = "low"
    factors: list[RiskFactor] = Field(default_factory=list)
    assessed_on: date


class RiskContribution(BaseModel):
    """One alerted entity near the target and what it contributes: its alerts, how many hops
    away, and its weight after decay."""

    node_id: NodeId
    name: str
    hops: int
    alert_ids: list[str] = Field(default_factory=list)
    summaries: list[str] = Field(default_factory=list)
    contribution: float


class NeighbourhoodRisk(BaseModel):
    """*Neighbourhood risk* (ADR-109 phase E, ruling 9's defaults): the case's alerts within
    `max_hops` of an entity, each decayed by `decay` per hop and counted for `window_days` —
    computed at read, as the reader reads the graph, never stored, so it says only what their own
    visible graph supports (rule 3)."""

    node_id: NodeId
    score: float
    max_hops: int
    decay: float
    window_days: int
    as_of: date
    contributions: list[RiskContribution] = Field(default_factory=list)


class HeldRowDecision(BaseModel):
    """A reviewer's release or rejection of named held rows — enumerated ids, never a filter
    (one decision over exactly what was seen, as bulk accept is in ADR-108 Amendment 3). A
    rejection needs its reason."""

    ids: list[str] = Field(min_length=1, max_length=1000)
    reason: str | None = Field(default=None, max_length=2000)


class Judgement(BaseModel):
    """`01_DOMAIN_MODEL.md` §5, `06_DECISIONS.md` ADR-046 (accepted), Phase 8 Stage 4b. "A
    judgement cannot be saved without at least one supporting reference" (§5) — enforced by
    `services/api/assessments.py::save_judgement`, not by this model alone (a `Field(min_length=1)`
    constraint would also reject an *update* that legitimately removes the last supporting item
    while adding a replacement in the same call — the store's own validation composes the two
    lists correctly; this model only shapes the row).

    `supporting`/`contradicting` are references, never copies (`06_DECISIONS.md` ADR-046, following
    ADR-039) — a `NodeId | EdgeId | DocumentId`, collapsed to `str` here the same way the domain
    model's own illustrative type union already is (all three are opaque ULID-shaped strings with
    no structural way to tell them apart). **Disclosed limitation, not fixed here:**
    `GraphPort` has no `get_edge`, and no document store exists yet
    (a disclosed gap, not fixed here) — only a `NodeId`
    citation can be positively confirmed visible today; an `EdgeId`/`DocumentId` citation is always
    treated as unreadable by `services/api/assessments.py`'s own access check, the same fail-closed
    default this codebase already applies everywhere else it cannot positively confirm access.

    `flagged_for_review`/`flag_reason` are not in `01_DOMAIN_MODEL.md` §5's own illustrative
    Pydantic snippet — grown past it the same way `GraphPort` and `SAME_AS`'s own properties
    each already grew past their own doc's illustrative sketch
    (`00_ARCHITECTURE.md` §2.1, `01_DOMAIN_MODEL.md` §4) — the review-flag
    loop (§5: "every judgement resting on it is flagged for review") needs somewhere to persist
    that state, and the spec names the behaviour without naming a field for it."""

    id: JudgementId
    investigation_id: str
    statement: str
    probability_band: str
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    #: **Owner ruling R7, 27 September 2026 — TENTATIVE** (the owner is revisiting it after their
    #: own usability walkthrough; `06_DECISIONS.md` ADR-046's addendum carries it in that state).
    #: Old citation id -> the id it was superseded by, filled at read time, never stored.
    #:
    #: A citation is **never rewritten** — `01_DOMAIN_MODEL.md` §2.4 and `GraphPort.supersede_edge`
    #: both say why: "it is expected to follow the `superseded_by` pointer, not be silently
    #: rewritten", because the judgement asserted something about the evidence *as it stood*.
    #: So `supporting` keeps naming the revision the analyst actually cited, and this map is what
    #: the Judgements tab renders instead — the citation resolved forward, for display only.
    #: Empty for every judgement whose citations are all current, which is almost all of them.
    resolved_citations: dict[str, str] = Field(default_factory=dict)
    author: PrincipalId
    #: The author's display name, resolved from the identity provider when the read is served and
    #: never stored (`06_DECISIONS.md` ADR-106); absent, the id is shown.
    author_name: str | None = None
    created_at: datetime
    #: Set when a cited node/edge is superseded (content change) or when a `contradicting`
    #: reference becomes unreadable (`06_DECISIONS.md` ADR-046's own "flagged for review the same
    #: way a content change already is") — never cleared automatically; a human reviewing the flag
    #: is what closes the loop, not a re-run of whatever set it.
    flagged_for_review: bool = False
    flag_reason: str | None = None


class IntelligenceGap(BaseModel):
    """`01_DOMAIN_MODEL.md` §5, Phase 8 Stage 4b."""

    id: GapId
    investigation_id: str
    question: str
    raised_by: PrincipalId
    #: Resolved at read time, never stored (ADR-106).
    raised_by_name: str | None = None
    linked_entities: list[NodeId] = Field(default_factory=list)
    status: Literal["open", "tasked", "answered", "closed"] = "open"
    created_at: datetime


class Assumption(BaseModel):
    """`01_DOMAIN_MODEL.md` §5, Phase 8 Stage 4b."""

    id: AssumptionId
    investigation_id: str
    statement: str
    if_false_impact: str
    linked_judgements: list[JudgementId] = Field(default_factory=list)
    created_at: datetime


class LinkNote(BaseModel):
    """One analyst note on one link (`06_DECISIONS.md` ADR-075). Plain text, several per link,
    kept in the investigation, shown to everyone who can see the link. Only its author changes or
    removes it. `mine` is worked out per reader when the note is served and is never stored."""

    id: str
    investigation_id: str
    edge_id: EdgeId
    author: PrincipalId
    #: Resolved at read time like `mine`, never stored (ADR-106).
    author_name: str | None = None
    body: str
    created_at: datetime
    edited_at: datetime | None = None
    mine: bool = False


class NeighbourhoodStats(BaseModel):
    node_id: NodeId
    degree: int
    degree_by_type: dict[str, int] = Field(default_factory=dict)


class Subgraph(BaseModel):
    """Nodes and links a read returned. It carries no count of what was left out (ADR-124
    Amendment 4, item 2): `filtered_count` was on it and was 0 on every read the adapter made, a
    field that claims completeness and is sent wherever a `Subgraph` is a response."""

    nodes: list[Node]
    edges: list[Edge]


class ListNodesPage(BaseModel):
    """`GraphPort.list_nodes`'s response — `06_DECISIONS.md` ADR-025,
    `01_DOMAIN_MODEL.md` §8.2. Not `limit_exceeded`'s contract (that error
    is analyst-facing, offering three interactive choices; `list_nodes` has
    no analyst in the loop, only a service-principal caller that pages).
    `next_cursor is None` is the *only* correct signal that a type's
    population is exhausted — an empty `nodes` list on its own is not: a
    page can legitimately contain zero *visible* nodes while more exist
    further on, if every node in this page's key range happens to be
    hidden from `principal`. A caller that stops on an empty page rather
    than checking `next_cursor` recreates, one layer up, exactly the
    silent truncation this codebase forbids `GraphPort` itself from
    producing."""

    nodes: list[Node]
    next_cursor: NodeId | None = None


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
    RoutesAtLength,
    ConnectionsRequest,
    Connections,
    Path,
    PatternNode,
    PatternEdge,
    PatternQuery,
    SavedPattern,
    Alert,
    Hotlist,
    Monitor,
    StructuringParams,
    RapidMovementParams,
    CircularFlowParams,
    KycScreeningParams,
    SharedAttributesParams,
    DocumentVerificationParams,
    PatternRuleParams,
    TypologyRuleInput,
    TypologyRule,
    HeldRow,
    RuleAuditEntry,
    RuleAuditPage,
    ReportCount,
    WeekCount,
    OutcomeCount,
    HeldFigures,
    KycFigures,
    PoleTypeCount,
    PoleClassCount,
    PoleFigures,
    ReportFigures,
    ReportLimitExceeded,
    QueuedAlert,
    KycDocument,
    RiskFactor,
    KycStatus,
    RiskContribution,
    NeighbourhoodRisk,
    ExplainedTransaction,
    AlertExplanation,
    AlertDispositionInput,
    HeldRowDecision,
    Judgement,
    IntelligenceGap,
    Assumption,
    LinkNote,
    NeighbourhoodStats,
    Subgraph,
    ListNodesPage,
)
