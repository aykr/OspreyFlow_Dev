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
    """Pre-persistence `Edge`: `id` and `created_at` are Conduit-assigned,
    the same as `NodeWrite` — see its docstring."""

    id: EdgeId
    type: str
    source: NodeId
    target: NodeId
    properties: dict[str, Any] = Field(default_factory=dict)
    interval: Interval | None = None
    occurrences: int = 1
    provenance: Provenance
    handling: Handling
    created_by: PrincipalId
    created_at: datetime
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
    identifier: str
    owner_id: str
    review_date: date
    status: WatchStatus = "active"
    created_at: datetime


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
    Pydantic snippet — grown past it the same way `GraphPort`, `SAME_AS`'s own properties and
    `Subgraph.filtered_count` each already grew past their own doc's illustrative sketch
    (`00_ARCHITECTURE.md` §2.1, `01_DOMAIN_MODEL.md` §4, §8.2's own precedent) — the review-flag
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
    body: str
    created_at: datetime
    edited_at: datetime | None = None
    mine: bool = False


class NeighbourhoodStats(BaseModel):
    node_id: NodeId
    degree: int
    degree_by_type: dict[str, int] = Field(default_factory=dict)


class Subgraph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    filtered_count: int = 0


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
    Path,
    PatternNode,
    PatternEdge,
    PatternQuery,
    SavedPattern,
    Alert,
    Hotlist,
    Monitor,
    Judgement,
    IntelligenceGap,
    Assumption,
    LinkNote,
    NeighbourhoodStats,
    Subgraph,
    ListNodesPage,
)
