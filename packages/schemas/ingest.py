"""The ingest recipe and load ledger — `09_INGEST_STUDIO.md` §6,
`01_DOMAIN_MODEL.md` §2.4's note on `AuditStub.load_id`/`recipe_id`/
`recipe_version`.

`Recipe` is the Pydantic shape of the versioned YAML file
`09_INGEST_STUDIO.md` §6 shows — the studio (Phase 5a) will be an editor for
this same file, not a second format. `LoadRecord` is the ledger entry one
execution of a recipe against one source produces: what it created, so
`services/ingest`'s `revert_load` can supersede a whole load as a unit
without re-deriving what belongs to it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.domain import EdgeId, NodeId, PrincipalId

# --- The recipe (09_INGEST_STUDIO.md §6) ---------------------------------


class RecipeConnector(BaseModel):
    profile: str
    delimiter: str = ","
    encoding: str = "utf-8"
    header_rows: int = 1
    #: `01_DOMAIN_MODEL.md` §7: an ambiguous date order (`03/04/2026`) has
    #: no safe default with both the UK and the US in scope (ADR-017).
    #: Declared once for the whole source; a field's own `datetime(...)`
    #: transform may still override it explicitly.
    date_order: Literal["dmy", "mdy"] | None = None
    #: `00_ARCHITECTURE.md` §1.2.2, ADR-017: the coordinate reference
    #: system this source's coordinates are expressed in (an EPSG code,
    #: e.g. `EPSG:27700`). Declared once for the whole source, the same
    #: way `date_order` is — a coordinate pair with no declared and no
    #: self-describing CRS is rejected rather than guessed.
    source_crs: str | None = None


class RecipeDefaults(BaseModel):
    provenance: dict[str, Any] = Field(default_factory=dict)
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None


class FieldBinding(BaseModel):
    """One property's source: a source field (optionally passed through a
    Knowledge Adapter `transform`), a `literal`, or a value `map` — never
    an expression (`09_INGEST_STUDIO.md` §4: "no expression language").

    `fields` is the multi-column alternative to `field`, for a transform
    that genuinely needs more than one source value — a coordinate pair,
    or a British National Grid reference split across a letter pair and
    two numeric columns. It is still one declared transform over named
    source columns, not an expression: nothing computes which fields to
    combine, the recipe states them outright. How many columns a given
    transform takes is the adapter's own declared arity
    (`knowledge_adapters.ARITY`), not a fixed count here — two is not
    special, it is just what a coordinate pair happens to need."""

    field: str | None = None
    fields: list[str] | None = None
    literal: Any | None = None
    transform: str | None = None
    map: dict[str, str] | None = None


class DeduplicateConfig(BaseModel):
    #: §7 rule 2: every key field is canonicalised through its own
    #: Knowledge Adapter before hashing — `FieldBinding`, the exact same
    #: shape (and the exact same resolution path) a row-template property
    #: uses, not a second implementation of "apply a transform."
    key: list[FieldBinding]


class RecipeCondition(BaseModel):
    """A `when` clause — `09_INGEST_STUDIO.md` §4's conditional elements."""

    field: str
    is_: Literal["not_null", "null"] | None = Field(default=None, alias="is")
    equals: Any | None = None

    model_config = {"populate_by_name": True}


class RecipeEntity(BaseModel):
    ref: str
    pole_class: str
    type: str
    match_on: str | None = None
    on_match: Literal["reference", "create"] = "create"
    when: RecipeCondition | None = None
    properties: dict[str, FieldBinding] = Field(default_factory=dict)


class TemporalBinding(BaseModel):
    at: FieldBinding


class RecipeEdge(BaseModel):
    type: str
    from_ref: str = Field(alias="from")
    to_ref: str = Field(alias="to")
    when: RecipeCondition | None = None
    temporal: TemporalBinding | None = None
    properties: dict[str, FieldBinding] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class UnmappedField(BaseModel):
    field: str
    action: Literal["ignore"] = "ignore"
    note: str | None = None


class RowTemplate(BaseModel):
    entities: list[RecipeEntity]
    edges: list[RecipeEdge] = Field(default_factory=list)


class ScheduleConfig(BaseModel):
    cron: str | None = None
    watch: str | None = None


class Recipe(BaseModel):
    id: str
    version: int
    label: str
    connector: RecipeConnector
    ontology_version: int
    defaults: RecipeDefaults = Field(default_factory=RecipeDefaults)
    deduplicate: DeduplicateConfig | None = None
    row_template: RowTemplate
    unmapped_fields: list[UnmappedField] = Field(default_factory=list)
    schedule: ScheduleConfig | None = None


# --- Rejections and the load report (09_INGEST_STUDIO.md §5) -------------


class RejectionRecord(BaseModel):
    """One rejected row, grouped by cause in the load report — never a
    silent coercion (`01_DOMAIN_MODEL.md` §7)."""

    row_index: int
    reason: str
    sample: str


class LoadReport(BaseModel):
    load_id: str
    recipe_id: str
    recipe_version: int
    rows_read: int = 0
    rows_deduplicated: int = 0
    nodes_created: int = 0
    nodes_referenced: int = 0
    edges_created: int = 0
    rejections: list[RejectionRecord] = Field(default_factory=list)
    #: Only the nodes THIS load created — never a node it merely
    #: referenced, and never an edge it only extended (§9.1, when this
    #: becomes a `LoadRecord`, records only what revert may safely
    #: supersede without touching another load's contribution).
    created_node_ids: list[NodeId] = Field(default_factory=list)
    touched_edge_ids: list[EdgeId] = Field(default_factory=list)


# --- The load ledger (01_DOMAIN_MODEL.md §2.4, ADR-018) -------------------


class LoadRecord(BaseModel):
    """One execution of a recipe against a source — the persisted form of
    a `LoadReport`. `created_node_ids` is only the nodes this load
    created, never one it merely referenced; `touched_edge_ids` is every
    edge it wrote to, created or merged into. This asymmetry is what makes
    `revert_load` safe: reverting a node this load created can never
    affect another load, but an edge is shared the moment two loads touch
    the same pair, which is why `GraphArcadeDBAdapter.revert_elements`
    only ever sets a flag rather than deleting — the audit trail (and any
    other load's claim on the same edge) stays intact regardless. Every
    element also carries `load_id` on its own `AuditStub`, so filtering
    the graph directly by load or recipe version never needs this ledger
    at all; the ledger is for load-level operations (revert, history) a
    per-element stamp cannot answer by itself."""

    load_id: str
    recipe_id: str
    recipe_version: int
    source: str
    started_at: datetime
    completed_at: datetime | None = None
    created_by: PrincipalId
    created_node_ids: list[NodeId] = Field(default_factory=list)
    touched_edge_ids: list[EdgeId] = Field(default_factory=list)
    rejected_count: int = 0
    superseded_at: datetime | None = None
    superseded_by: PrincipalId | None = None


ALL_MODELS: tuple[type[BaseModel], ...] = (
    RecipeConnector,
    RecipeDefaults,
    DeduplicateConfig,
    FieldBinding,
    RecipeCondition,
    RecipeEntity,
    TemporalBinding,
    RecipeEdge,
    UnmappedField,
    RowTemplate,
    ScheduleConfig,
    Recipe,
    RejectionRecord,
    LoadReport,
    LoadRecord,
)
