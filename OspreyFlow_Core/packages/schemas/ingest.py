"""The ingest recipe and load ledger — `09_INGEST_STUDIO.md` §6,
`01_DOMAIN_MODEL.md` §2.4's note on `AuditStub.load_id`/`recipe_id`/
`recipe_version`.

`Recipe` is the Pydantic shape of the versioned YAML file
`09_INGEST_STUDIO.md` §6 shows — the studio (Phase 5a) will be an editor for
this same file, not a second format. `LoadRecord` is the ledger entry one
execution of a recipe against one source produces: what it created, so
`services/ingest/load_revert.py` can revert a whole load as a unit
without re-deriving what belongs to it.
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from schemas.domain import Edge, EdgeId, Handling, Node, NodeId, PrincipalId, Provenance

from .connectors import load_connector_profiles

# --- Studio roles (09_INGEST_STUDIO.md §8) -------------------------------


class StudioRole(StrEnum):
    """Action authorisation for the Ingest Studio, a different axis from
    `Principal.clearance`/`receivable_handling_codes` (`AccessFilter`,
    `01_DOMAIN_MODEL.md` §2.2): holding a role permits an *action*
    (publish, schedule, approve), never grants visibility into any
    material. Arrives the same way the clearance axes already do — a
    claim (`services/api/auth.py`'s `CLAIM_ROLES`) an IdP maps onto
    `Principal.roles`, a plain list, so a principal may hold more than
    one of these; nothing implies exclusivity."""

    SOURCE_AUTHOR = "source_author"
    SOURCE_APPROVER = "source_approver"
    LOADER = "loader"


# --- Connect (09_INGEST_STUDIO.md §2) -------------------------------------


class ConnectorCatalogueEntry(BaseModel):
    """One row of §2's structured/unstructured connector tables, reproduced
    verbatim rather than derived, so the Connect screen's catalogue always
    matches the doc exactly. `id` is a `RecipeConnector.profile` value once
    a recipe is drafted against this entry.

    **`available` is derived, not declared** (round 13bf). It is `True` iff a
    `connectors/<id>.yaml` profile exists naming a reader this codebase implements —
    `packages/schemas/connectors.py` owns that, and `09_INGEST_STUDIO.md` §2's own "a validated
    YAML file in `connectors/`, so adding a new carrier's CDR layout is a file rather than a
    release" is the sentence it finally makes true. Before that it was a literal here *and* a
    second, unconnected literal in `services/api/studio_profile.py`: two hand-maintained truths
    about one fact, which is how the CDR layout came to be declared in this table and refused by
    the Studio.

    The entry still appears when unavailable; the catalogue is never trimmed down to only what
    works, since the whole point of showing it is that the gap is visible, not hidden."""

    id: str
    label: str
    group: str
    structured: bool
    available: bool = False


#: §2's "Structured connector catalogue" table, group by group.
_STRUCTURED_CATALOGUE: tuple[ConnectorCatalogueEntry, ...] = (
    ConnectorCatalogueEntry(
        id="comms-cdr-ipdr",
        label="CDR and IPDR from carriers",
        group="Communications",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="comms-subscriber-toll",
        label="Subscriber and toll reports",
        group="Communications",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="mobile-cellebrite-ufdr", label="Cellebrite UFDR", group="Mobile device", structured=True
    ),
    ConnectorCatalogueEntry(id="mobile-xry", label="XRY", group="Mobile device", structured=True),
    ConnectorCatalogueEntry(
        id="mobile-generic-forensic",
        label="Generic forensic report export",
        group="Mobile device",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="mobile-case-uco", label="CASE/UCO interchange", group="Mobile device", structured=True
    ),
    ConnectorCatalogueEntry(
        id="financial-card-transactions",
        label="Card transactions",
        group="Financial",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="financial-bank-statements", label="Bank statements", group="Financial", structured=True
    ),
    ConnectorCatalogueEntry(
        id="financial-iso20022", label="ISO 20022 (camt, pain)", group="Financial", structured=True
    ),
    ConnectorCatalogueEntry(
        id="financial-swift-mt", label="SWIFT MT", group="Financial", structured=True
    ),
    ConnectorCatalogueEntry(
        id="financial-crypto-exchange",
        label="Crypto exchange export",
        group="Financial",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="vehicle-anpr", label="ANPR", group="Vehicle and movement", structured=True
    ),
    ConnectorCatalogueEntry(
        id="vehicle-telematics", label="Telematics", group="Vehicle and movement", structured=True
    ),
    ConnectorCatalogueEntry(
        id="vehicle-travel-border",
        label="Travel and border records",
        group="Vehicle and movement",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="records-custody-incident",
        label="Custody, incident and intelligence exports",
        group="Records",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="records-case-management",
        label="Case management exports",
        group="Records",
        structured=True,
    ),
    ConnectorCatalogueEntry(
        id="generic-csv",
        label="CSV",
        group="Generic",
        structured=True,
    ),
    ConnectorCatalogueEntry(id="generic-tsv", label="TSV", group="Generic", structured=True),
    ConnectorCatalogueEntry(id="generic-json", label="JSON", group="Generic", structured=True),
    ConnectorCatalogueEntry(id="generic-jsonl", label="JSONL", group="Generic", structured=True),
    ConnectorCatalogueEntry(id="generic-xml", label="XML", group="Generic", structured=True),
    ConnectorCatalogueEntry(
        id="generic-parquet", label="Parquet", group="Generic", structured=True
    ),
    ConnectorCatalogueEntry(id="generic-excel", label="Excel", group="Generic", structured=True),
    ConnectorCatalogueEntry(
        id="generic-sql", label="SQL table or view", group="Generic", structured=True
    ),
)

#: §2's "Unstructured sources" table.
_UNSTRUCTURED_CATALOGUE: tuple[ConnectorCatalogueEntry, ...] = (
    ConnectorCatalogueEntry(
        id="doc-pdf-docx-rtf",
        label="PDF, DOCX, RTF, TXT, EML/MSG, HTML",
        group="Documents",
        structured=False,
    ),
    ConnectorCatalogueEntry(
        id="image-jpeg-png-tiff-heic",
        label="JPEG, PNG, TIFF, HEIC, scanned images",
        group="Images",
        structured=False,
    ),
    ConnectorCatalogueEntry(
        id="av-wav-mp3-m4a-mp4",
        label="WAV, MP3, M4A, MP4, interview recordings",
        group="Audio and video",
        structured=False,
    ),
    ConnectorCatalogueEntry(
        id="archive-zip-tar", label="ZIP and tarballs", group="Archives", structured=False
    ),
)


#: Where connector profiles live, relative to the repository root — `09_INGEST_STUDIO.md` §2's
#: own `connectors/`. Overridable so a deployment can ship its own layouts without a rebuild,
#: which is the other half of "a file rather than a release".
def _default_connectors_dir() -> Path:
    """The catalogue beside `packages/`, wherever the process was started from (tests now run from
    the Build folder, ADR-054); falls back to the working directory's `connectors/` for an image
    whose layout differs."""
    beside_packages = Path(__file__).resolve().parents[2] / "connectors"
    return beside_packages if beside_packages.is_dir() else Path("connectors")


CONNECTORS_DIR = Path(os.environ.get("OSPREY_CONNECTORS_DIR") or _default_connectors_dir())

_DECLARED_CATALOGUE: tuple[ConnectorCatalogueEntry, ...] = (
    _STRUCTURED_CATALOGUE + _UNSTRUCTURED_CATALOGUE
)


def connector_catalogue(directory: Path | None = None) -> tuple[ConnectorCatalogueEntry, ...]:
    """§2's catalogue with `available` filled in from the profile files actually present.

    A declared entry with no profile file is reported unavailable — visible, and honest about the
    gap. A profile file with no declared entry is **added**, because a deployment that drops in
    its own carrier layout must be able to select it; its label and group come from the file.
    """
    profiles = load_connector_profiles(directory if directory is not None else CONNECTORS_DIR)
    entries = [
        entry.model_copy(
            update={"available": entry.id in profiles and profiles[entry.id].available}
        )
        for entry in _DECLARED_CATALOGUE
    ]
    declared_ids = {entry.id for entry in _DECLARED_CATALOGUE}
    for profile in profiles.values():
        if profile.id in declared_ids:
            continue
        entries.append(
            ConnectorCatalogueEntry(
                id=profile.id,
                label=profile.label,
                group=profile.group,
                structured=profile.structured,
                available=profile.available,
            )
        )
    return tuple(entries)


#: Evaluated at import, so a profile file added while the Conduit is running needs a restart to
#: appear — the same contract the ontology and the handling scheme already have.
CONNECTOR_CATALOGUE: tuple[ConnectorCatalogueEntry, ...] = connector_catalogue()


class StudioRecipeStatus(StrEnum):
    """`09_INGEST_STUDIO.md` §6's `studio_recipes.status` values."""

    DRAFT = "draft"
    PUBLISHED = "published"
    FLAGGED = "flagged"
    SUPERSEDED = "superseded"


class DomainPackEntry(BaseModel):
    """One domain model the Studio offers (ADR-108 phase D): the POLE core, or a pack with the
    entity and link types it adds over it."""

    name: str
    label: str
    entity_types: list[str] = Field(default_factory=list)
    edge_types: list[str] = Field(default_factory=list)


class PipelineNodeKind(StrEnum):
    """The pipeline graph's closed node vocabulary (`06_DECISIONS.md` ADR-108). Closed on
    purpose: rule 8 — no expression or scripting language in the Studio; every node is a declared
    stage whose transforms remain Knowledge Adapters with golden files."""

    DOMAIN_MODEL = "domain_model"
    SOURCE = "source"
    PROFILE = "profile"
    MAP = "map"
    EXTRACT = "extract"
    ENRICH = "enrich"
    LOAD = "load"


class PipelineNode(BaseModel):
    """One stage of a pipeline. `config` carries the stage's own settings (a source node's
    connector profile and location, a domain node's pack) — its keys are each stage's declared
    vocabulary, validated by `services/ingest/pipeline.py`, never free code."""

    id: str
    kind: PipelineNodeKind
    label: str
    config: dict[str, Any] = Field(default_factory=dict)


class PipelineEdge(BaseModel):
    """A data dependency: `source` feeds `target`. The graph is acyclic (validated at save)."""

    source: str
    target: str


class PipelineGraph(BaseModel):
    """ADR-108: the recipe as a typed DAG. A v1 recipe that has none is read as its canonical
    chain (`pipeline_from_recipe`), derived at read time and never stored back."""

    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)


def check_source_declarations(value: dict[str, Any]) -> dict[str, Any]:
    """What a source's handling declares beside its marking (ADR-127 decision 3), as Connect and a
    PATCH's merged result are judged: `units` a list of non-empty unit names (stripped), and
    `handling_columns` a map of parts to column names, which needs `units` if it names a unit
    part. Anything else is refused with its cause."""
    value = dict(value)
    if "units" in value:
        units = value["units"]
        if not isinstance(units, list) or any(
            not isinstance(u, str) or not u.strip() for u in units
        ):
            raise ValueError("handling units must be a list of non-empty unit names")
        value["units"] = [u.strip() for u in units]
    if "handling_columns" in value:
        value["handling_columns"] = check_handling_columns(value["handling_columns"])
        unit_parts = [p for p in ("originator", "owning_unit") if p in value["handling_columns"]]
        if unit_parts and not value.get("units"):
            raise ValueError(
                f"handling_columns declares a column for {' and '.join(unit_parts)} but the "
                "source lists no units: a cell may name only a unit the source declares in "
                "units"
            )
    return value


class ConnectDraftInput(BaseModel):
    """What Connect (§2) actually collects: a connector choice and the
    three mandatory gate answers. Nothing here is optional except
    `legal_basis`'s presence at draft-creation time — a draft may be saved
    mid-entry, but `StudioRecipeDraft.ready_for_profile` stays `False`
    until all three are set, and §2 is explicit that Profile itself is
    unreachable until they are."""

    label: str
    connector_profile: str
    #: §2: "where the data is" — a path or URI (`RecipeConnector` carries no
    #: location field yet; wiring an actual upload is Profile-stage scope,
    #: not Connect's, since Profile is what first needs to read bytes).
    source_location: str | None = None
    #: §2: "what the handling marking on it is" — merged into
    #: `RecipeDefaults.handling` once Map exists to act on it.
    handling: dict[str, Any] = Field(default_factory=dict)
    #: §2: "what the legal basis for processing it is".
    legal_basis: str | None = None
    #: ADR-127 decision 5: the fields that make a source row the same row again, as a recipe's
    #: `deduplicate` takes them. Absent leaves the draft's own as it is; an empty `key` clears it.
    #: Judged at save against the source's columns (`services/ingest/recipe_rules.py`).
    deduplicate: DeduplicateConfig | None = None

    @field_validator("handling")
    @classmethod
    def _units_are_names(cls, value: dict[str, Any]) -> dict[str, Any]:
        """ADR-127 decision 3: refused here, as a 422, not left for the recipe to fail on."""
        return check_source_declarations(value)


class StudioRecipeDraft(BaseModel):
    """The Connect-stage view of one `studio_recipes` row (§6) — not the
    full `Recipe`, which does not exist until Map supplies a
    `row_template` and Publish supplies a `git_path`."""

    recipe_id: str
    version: int
    status: StudioRecipeStatus
    label: str
    connector_profile: str | None = None
    source_location: str | None = None
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None
    owning_unit: str
    created_by: PrincipalId
    #: Resolved at read time, never stored (`06_DECISIONS.md` ADR-106).
    created_by_name: str | None = None
    created_at: datetime
    #: §2: Connect cannot proceed to Profile without all three gate answers.
    #: Profile enforces this server-side too (`services/api/studio_profile.
    #: py`'s `RecipeNotReadyForProfileError`/`SourceHandlingIncompleteError`)
    #: — this field is what the Connect screen gates its own "Continue"
    #: action on, and the two checks are meant to agree: a draft this field
    #: calls ready should never then fail Profile's own handling check.
    #: Always overwritten by `_compute_ready_for_profile` below regardless
    #: of what a caller passes — never something a caller can set
    #: independently of the fields it actually reflects. (A
    #: `@computed_field` property would have been the more obvious choice,
    #: but `generate_ts.py`'s `model_json_schema()` call uses the default
    #: "validation" mode, which omits computed fields entirely — this way
    #: the field, and the gate it reports, actually reach the generated TS
    #: type and the Connect screen.)
    ready_for_profile: bool
    #: Map's (§4) own state on the draft — `None`/`[]` until Map has ever
    #: saved (`PUT /v1/ingest/recipes/{id}/row-template`). A draft is a row,
    #: not client state (§6), and Map's draft spans sessions the same way
    #: Connect's does, so the row template lives here rather than only in
    #: the Glass's own component state.
    row_template: RowTemplate | None = None
    unmapped_fields: list[UnmappedField] = Field(default_factory=list)
    #: ADR-127 decision 5: what makes a source row the same row again, carried through Publish into
    #: the committed recipe and kept on a new version. `None` keeps no keys and loads every row
    #: every time.
    deduplicate: DeduplicateConfig | None = None
    #: Publish's own state (§6) — every field below is `None` while
    #: `status='draft'`. `verified_at` is set by a *successful* run of
    #: `POST .../verify` (`services/api/studio_verify.py`'s `run_verify`
    #: completing without raising) and cleared by any subsequent edit
    #: (`update_draft`/`update_row_template`) — "Verify must pass before
    #: publish" (§5) is enforced against this flag, not re-derived from a
    #: fresh dry run at publish time. The rest are set once, by `publish`,
    #: and never revisited except `schedule_cron`/`schedule_watch`, which a
    #: later `PATCH .../schedule` may change without touching anything else.
    verified_at: datetime | None = None
    ontology_version: int | None = None
    #: ADR-120 D10, Amendment 1: the pack versions it was published against. `None` = not pinned;
    #: `{}` = pinned, names and writes no pack.
    pack_versions: dict[str, int] | None = None
    git_path: str | None = None
    published_by: PrincipalId | None = None
    #: Resolved at read time, never stored (ADR-106).
    published_by_name: str | None = None
    published_at: datetime | None = None
    schedule_cron: str | None = None
    schedule_watch: str | None = None
    #: ADR-110 decision 7: the time zone `schedule_cron` is read in (Europe/London when unset).
    schedule_timezone: str | None = None
    #: ADR-110 decision 3 and Amendment 2: who last set the schedule, and when. A scheduled run acts
    #: as this person, never as the system.
    schedule_owner: PrincipalId | None = None
    schedule_set_at: datetime | None = None
    #: The case the schedule was set in: whose rules judge each scheduled load, and whose datasets
    #: the owner reads it through (`scope_to_case`), as a *Run now* there would be.
    schedule_case: str | None = None
    #: ADR-110 decisions 3 and 8: paused by a person, or by three refused runs in a row, and why.
    schedule_paused: bool = False
    schedule_paused_reason: str | None = None
    #: ADR-099 Amendment 3: the dataset of the case it was made in; found, listed and run only in a
    #: case reading it. `None` for one made before, until `stamp_datasets` places it.
    dataset_id: str | None = None
    #: ADR-108: the recipe as a typed DAG. `None` for a v1 recipe, which reads as its canonical
    #: chain through `pipeline_from_recipe` — derived, never stored back.
    pipeline: PipelineGraph | None = None

    @model_validator(mode="before")
    @classmethod
    def _compute_ready_for_profile(cls, data: object) -> object:
        if isinstance(data, dict):
            data = dict(data)
            handling = data.get("handling")
            # A non-empty `handling` dict used to be enough — but "OFFICIAL"
            # alone (classification with no handling_code/originator/
            # owning_unit) is truthy and still leaves Profile unable to
            # build a `Handling` to mask against. Requiring it to actually
            # construct one is what makes `ready_for_profile=True` a real
            # promise rather than an empty-dict check.
            handling_complete = False
            if isinstance(handling, dict):
                try:
                    Handling(**handling)
                except ValidationError:
                    handling_complete = False
                else:
                    handling_complete = True
            data["ready_for_profile"] = bool(
                data.get("source_location") and handling_complete and data.get("legal_basis")
            )
        return data


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


#: The parts of a marking a column may carry, per element (ADR-127 decision 3,
#: `09_INGEST_STUDIO.md` §4: "a column can carry either"). `review_date` and `legal_basis` are the
#: source's, set once at Connect.
HANDLING_BINDABLE: tuple[str, ...] = (
    "classification",
    "handling_code",
    "action_code",
    "sanitisation_code",
    "originator",
    "owning_unit",
)


class HandlingFieldBinding(BaseModel):
    """One part of an element's marking read from a source column per row (ADR-127 decision 3):
    `{field: <column>}`. An empty cell takes the element's default for that part; a cell may only
    tighten it (`merge_handling`'s order), and a unit must be one the recipe declares."""

    field: str

    model_config = {"extra": "forbid"}


def check_handling_override(value: dict[str, Any] | None, *, owner: str) -> dict[str, Any] | None:
    """An element's `handling` is literal values and, for the six parts a column may carry, a
    `{field: <column>}` binding. Anything else in a dict's place is refused where the recipe is
    read, so it cannot reach a run as a pydantic error from `Handling`."""
    for name, item in (value or {}).items():
        if not isinstance(item, dict):
            continue
        if name not in HANDLING_BINDABLE:
            raise ValueError(
                f"{owner} handling {name!r} cannot be bound to a column "
                f"(a column may carry: {', '.join(HANDLING_BINDABLE)})"
            )
        try:
            HandlingFieldBinding.model_validate(item)
        except ValidationError as exc:
            raise ValueError(
                f"{owner} handling {name!r} is bound as {{field: <column>}} and nothing else"
            ) from exc
    return value


def check_handling_columns(value: object) -> dict[str, str]:
    """`handling_columns`: which source column carries each part of a marking, as Connect declares
    it (ADR-127 decision 3). A part outside the six, or a column that is not a non-empty name, is
    refused; names are stripped."""
    if not isinstance(value, dict):
        raise ValueError("handling_columns must map a handling part to a column name")
    declared: dict[str, str] = {}
    for part, column in value.items():
        if part not in HANDLING_BINDABLE:
            raise ValueError(
                f"handling_columns names {part!r}, which a column cannot carry "
                f"({', '.join(HANDLING_BINDABLE)})"
            )
        if not isinstance(column, str) or not column.strip():
            raise ValueError(f"handling_columns {part!r} must name a non-empty column")
        declared[part] = column.strip()
    return declared


class RecipeDefaults(BaseModel):
    provenance: dict[str, Any] = Field(default_factory=dict)
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None
    #: ADR-127 decision 3: the units the source's rows may name as `originator` or `owning_unit`
    #: when an element binds either from a column. Beside the source's handling; empty means none
    #: may be bound.
    units: list[str] = Field(default_factory=list)
    #: Which source column carries each part of a marking, as Connect declares it: a read of the
    #: source before a template exists (Profile) judges each row by these, and Map save refuses a
    #: binding to a column not declared for its part.
    handling_columns: dict[str, str] = Field(default_factory=dict)

    @field_validator("handling_columns", mode="before")
    @classmethod
    def _columns_are_declared_parts(cls, value: object) -> dict[str, str]:
        return check_handling_columns(value)

    @classmethod
    def for_source(cls, handling: dict[str, Any], legal_basis: str | None) -> RecipeDefaults:
        """The defaults of a draft: its source handling, with the `units` that ride beside it
        (ADR-127 decision 3) taken out as the recipe's own list, not part of any one marking."""
        return cls(
            handling={k: v for k, v in handling.items() if k not in ("units", "handling_columns")},
            provenance={},
            legal_basis=legal_basis,
            units=[str(u) for u in handling.get("units", [])],
            handling_columns=dict(handling.get("handling_columns") or {}),
        )

    @field_validator("handling")
    @classmethod
    def _defaults_are_not_bound(cls, value: dict[str, Any]) -> dict[str, Any]:
        for name, item in value.items():
            if isinstance(item, dict):
                raise ValueError(
                    f"defaults handling {name!r} cannot be bound to a column: the defaults are "
                    "what a bound cell falls back on; bind it on an element's own handling"
                )
        return value


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
    #: ADR-127 Amendment 15: on a property's binding, an empty cell leaves the property out of the
    #: node instead of rejecting the row. `None` (and `False`) is the default: an empty bound cell
    #: rejects the row, as it always has. A property the ontology requires, the one an entity is
    #: matched on, and a time or key binding cannot be optional (refused where the recipe is saved).
    optional: bool | None = None


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


class ContentBinding(BaseModel):
    """ADR-094: a source column whose value the model can read. On a link it is the link's message
    or document text, written to the link's event (never the graph link), where the reader and
    extraction read it, as they read an Enron email's excerpt. A column named outright, never an
    expression (rule 8)."""

    #: On a link: `message_text` or `document_text`. On an entity (content it holds, linked by
    #: `HOLDS`): `document_text`, or a file named by a path relative to the export's own folder,
    #: `image_file` or `video_file`. On a `Document` entity, `document_text` is the Document's own
    #: text (ADR-127 decision 1): written onto that Document, with no content node and no `HOLDS`.
    kind: Literal["message_text", "document_text", "image_file", "video_file"]
    field: str


class RecipeEntity(BaseModel):
    ref: str
    pole_class: str
    type: str
    match_on: str | None = None
    on_match: Literal["reference", "create"] = "create"
    when: RecipeCondition | None = None
    properties: dict[str, FieldBinding] = Field(default_factory=dict)
    #: `09_INGEST_STUDIO.md` §4: "Provenance and handling... overridable per
    #: element." Merged over `recipe.defaults.handling`/`.provenance` by the
    #: write path and by `preview_handling_and_provenance()`
    #: (`services/ingest/engine.py`) — never used unconditionally on its
    #: own. Map (§3's independent-minimums rule) only ever lets this
    #: tighten, never loosen, the source-level marking set at Connect —
    #: enforced at save time (`services/api/studio_map.py`'s
    #: `validate_handling_tightens`), not re-checked per row at run time.
    handling: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None

    @field_validator("handling")
    @classmethod
    def _handling_bindings(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return check_handling_override(value, owner="entity")

    #: ADR-094: content this entity holds (a phone's saved note, photo or video), kept in the media
    #: store and linked to the entity by `HOLDS`.
    content: ContentBinding | None = None


class TemporalBinding(BaseModel):
    """A link's time. `at` is its start, or its only instant; `valid_to`, when bound, makes it a
    span (ADR-127 decision 11): the end, read from a column of its own. An empty end cell is a span
    still open (`Interval.valid_to` of `None`). Without `valid_to` the link is one instant, as
    before: its end is its start."""

    at: FieldBinding
    valid_to: FieldBinding | None = None


class RecipeEdge(BaseModel):
    type: str
    from_ref: str = Field(alias="from")
    to_ref: str = Field(alias="to")
    when: RecipeCondition | None = None
    temporal: TemporalBinding | None = None
    properties: dict[str, FieldBinding] = Field(default_factory=dict)
    #: ADR-094: the column holding this link's message or document text, if it has one.
    content: ContentBinding | None = None
    #: Same per-element override as `RecipeEntity.handling`/`.provenance` above.
    handling: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None

    @field_validator("handling")
    @classmethod
    def _handling_bindings(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return check_handling_override(value, owner="link")

    model_config = {"populate_by_name": True}


class UnmappedField(BaseModel):
    field: str
    action: Literal["ignore"] = "ignore"
    note: str | None = None


class RowTemplate(BaseModel):
    entities: list[RecipeEntity]
    edges: list[RecipeEdge] = Field(default_factory=list)


# --- Map (09_INGEST_STUDIO.md §4) -----------------------------------------


class TransformDescriptor(BaseModel):
    """One entry of the Knowledge Adapter catalogue Map's transform picker
    reads from — `packages/knowledge_adapters.REGISTRY`/`ARITY`, never
    hand-duplicated here. `arity` is `1` for every adapter absent from
    `ARITY` (that module's own docstring: such an adapter "does not support
    `fields` at all"), so the studio only ever offers a `fields` picker
    with more than one slot for a transform that actually declared one."""

    name: str
    arity: int = Field(ge=1)
    #: ADR-104: for a structured transform, the parts a binding takes one of (`person_name(part=
    #: family)`); empty for any other.
    parts: list[str] = Field(default_factory=list)


class RowTemplateUpdateInput(BaseModel):
    """Body of `PUT /v1/ingest/recipes/{id}/row-template` — Map's save,
    the same "a draft is a row, not client state" discipline Connect's own
    `ConnectDraftInput` already follows (§6)."""

    row_template: RowTemplate
    unmapped_fields: list[UnmappedField] = Field(default_factory=list)


class MapSampleRow(BaseModel):
    """One raw row from the same bounded sample Profile reads — §4's "the
    template is always shown bound to a real row, and the analyst can page
    through." Shape-masked exactly like `ColumnProfile.sample_values`
    (`09_INGEST_STUDIO.md` §3's independent-minimums rule) when the
    principal isn't cleared for the source's own handling marking."""

    row_index: int = Field(ge=0)
    values: dict[str, str]
    values_masked: bool
    #: `True` once `row_index` is the last row in the bounded sample —
    #: what the scrubber's "▸" disables against, never a silent clamp.
    is_last_row: bool


class MapHandlingPreviewRequest(BaseModel):
    """Body of `POST /v1/ingest/recipes/{id}/map/handling-preview` — what
    `preview_handling_and_provenance()` (`services/ingest/engine.py`) would
    compute for one in-progress element, before it is saved onto the
    template at all."""

    row_index: int = Field(ge=0)
    handling_override: dict[str, Any] | None = None
    provenance_override: dict[str, Any] | None = None


class MapHandlingPreviewResult(BaseModel):
    handling: Handling
    provenance: Provenance


class ScheduleConfig(BaseModel):
    cron: str | None = None
    watch: str | None = None


# --- Publish (09_INGEST_STUDIO.md §6) -------------------------------------


class PublishRecipeInput(BaseModel):
    """Body of `POST /v1/ingest/recipes/{id}/publish` — schedule is
    optional at publish time (a recipe may be published unscheduled, run
    only on demand) and settable/changeable later via `ScheduleUpdateInput`
    without republishing the mapping itself."""

    schedule_cron: str | None = None
    schedule_watch: str | None = None
    #: ADR-110 decision 7: the zone the schedule is read in; Europe/London when not given.
    schedule_timezone: str | None = None


class ScheduleUpdateInput(BaseModel):
    """Body of `PATCH /v1/ingest/recipes/{id}/schedule` — §8's "schedule
    it", kept separate from `publish` so changing when a recipe runs never
    requires bumping its version or re-verifying a mapping that hasn't
    changed."""

    schedule_cron: str | None = None
    schedule_watch: str | None = None
    #: ADR-110 decision 7: the zone the schedule is read in; Europe/London when not given.
    schedule_timezone: str | None = None


class SchedulePreviewInput(BaseModel):
    """Body of `POST /v1/ingest/schedule-preview` (ADR-110 decision 7): a schedule to explain
    before it is saved. `after` defaults to now."""

    cron: str
    timezone: str | None = None
    after: datetime | None = None


class SchedulePreview(BaseModel):
    """The schedule in words and its next five runs, in UTC."""

    words: str
    next_runs: list[datetime]


class RunRecipeInput(BaseModel):
    """Body of `POST /v1/investigations/{id}/ingest/recipes/{id}/run` —
    §8: "Loader: run a published recipe against a file", not necessarily
    the one Connect recorded. `source_location` is optional: omitted, the
    run repeats against the recipe's own recorded location (a plain
    re-run); given, it overrides just this run, the ordinary shape of a
    Loader's day — a fresh day's export through an already-mapped recipe."""

    source_location: str | None = None


class Recipe(BaseModel):
    id: str
    version: int
    label: str
    connector: RecipeConnector
    ontology_version: int
    #: ADR-120 D10, Amendment 1: `None` = not pinned; `{}` = pinned, names and writes no pack.
    pack_versions: dict[str, int] | None = None
    defaults: RecipeDefaults = Field(default_factory=RecipeDefaults)
    deduplicate: DeduplicateConfig | None = None
    row_template: RowTemplate
    unmapped_fields: list[UnmappedField] = Field(default_factory=list)
    schedule: ScheduleConfig | None = None
    #: ADR-108 phase C: the published topology the runner executes. `None` on every recipe
    #: published before phase C (and on a v1 draft) — those run as the one canonical chain, and
    #: their committed YAML stays byte-for-byte what it was (`exclude_none` at serialisation).
    pipeline: PipelineGraph | None = None


# --- Rejections and the load report (09_INGEST_STUDIO.md §5) -------------


class RejectionRecord(BaseModel):
    """One rejected row, grouped by cause in the load report — never a
    silent coercion (`01_DOMAIN_MODEL.md` §7)."""

    row_index: int
    reason: str
    sample: str
    #: Rule 3, ADR-127 Amendment 26: the marking of the rejected row, which `sample` (the whole
    #: row) is held at. A route answers a reader who cannot view it with the sample withheld
    #: (`load_records.report_view`), and never returns the marking itself. `None` where nothing of
    #: the row is in `sample`.
    marking: Handling | None = None
    #: Set where the row's marking could not be resolved: `sample` is then withheld from every
    #: reader, whatever their clearance, codes or unit (no unit is one nobody may hold).
    sample_unreadable: bool = False


class LoadReport(BaseModel):
    load_id: str
    recipe_id: str
    recipe_version: int
    rows_read: int = 0
    rows_deduplicated: int = 0
    #: ADR-127 decision 5: of `rows_read`, the rows a recipe with `deduplicate` did not load because
    #: this case already kept their key (whatever the recipe's version): a count of the loader's
    #: own source rows, never of anything another case holds. Rows folded into a survivor of the
    #: same file are `rows_deduplicated`, and not these.
    rows_already_loaded: int = 0
    nodes_created: int = 0
    nodes_referenced: int = 0
    edges_created: int = 0
    rejections: list[RejectionRecord] = Field(default_factory=list)
    #: The keys (canonicalised, then hashed) of the groups of rows this load wrote, for a recipe
    #: with `deduplicate`: kept for the case, with the load, in the transaction that records it
    #: (`RecipeRunStore.add_record`). A row held, rejected or already loaded has none. Hashes of the
    #: loader's own source rows, held for the ledger alone: never in `LoadReportView`.
    kept_row_keys: list[str] = Field(default_factory=list)
    #: A hash of the `deduplicate` definition the keys above were made under (`dedup_fingerprint`),
    #: kept with them: a run under another definition is refused while keys under this one are
    #: kept for the case. `None` for a recipe without `deduplicate`.
    row_key_fingerprint: str | None = None
    #: Only the nodes THIS load created — never a node it merely
    #: referenced, and never an edge it only extended (§9.1, when this
    #: becomes a `LoadRecord`, records only what revert may safely
    #: supersede without touching another load's contribution).
    created_node_ids: list[NodeId] = Field(default_factory=list)
    #: ADR-127 decision 7(a): the existing nodes this load matched by reference (`on_match:
    #: reference`), each once and never one it created itself. For the change-stream entry alone,
    #: which names what a run touched so a hotlist or a monitor sees it; not in the load's record
    #: (a revert never takes back what the load did not write) and never in a route's answer.
    referenced_node_ids: list[NodeId] = Field(default_factory=list)
    touched_edge_ids: list[EdgeId] = Field(default_factory=list)
    #: ADR-127 decision 6: of `touched_edge_ids`, the links this load wrote new, and the existing
    #: links it merged occurrences into, kept apart so a revert can tell its own links from another
    #: load's. A `HOLDS` link from a holder this load did not create is recorded as merged, since
    #: the port cannot say whether it was new (`engine._write_content`).
    created_edge_ids: list[EdgeId] = Field(default_factory=list)
    merged_edge_ids: list[EdgeId] = Field(default_factory=list)
    #: The nodes this load wrote that already existed (a held content `Document`, whose id is the
    #: hash of its bytes, may be another load's or a Files-tab upload's), kept out of
    #: `created_node_ids` so a revert never takes back what another load holds.
    merged_node_ids: list[NodeId] = Field(default_factory=list)
    #: What the case's rules wrote into the load (an `Alert`, its `ALERTED_ON` links, what a finding
    #: writes alongside): the load's, so its record lists them, but held apart from the lists above,
    #: which the change stream and the enrich stage read as what the recipe wrote. Monitors must not
    #: see an alert as a new ingest node (ADR-127 decision 6).
    rule_node_ids: list[NodeId] = Field(default_factory=list)
    rule_created_edge_ids: list[EdgeId] = Field(default_factory=list)
    rule_merged_edge_ids: list[EdgeId] = Field(default_factory=list)
    #: ADR-109 ruling 1: rows a pre-commit rule could not judge, held out of the graph for review,
    #: and what the case's pre-commit rules did, in words — never a silent part-load (rule 2).
    rows_held: int = 0
    rule_notes: list[str] = Field(default_factory=list)
    #: Rule 3, ADR-127 Amendment 23: every distinct marking this load's rows were written at (each
    #: element the engine resolved for a row, once), in the order first met. A count of what the
    #: load wrote includes rows at each of them, so a reader who may not view one of them is shown
    #: none of the counts (`services/api/load_records.report_view`, `_schedule_run_view`). Kept in
    #: the run ledger beside the run; never in a route's answer.
    markings: list[Handling] = Field(default_factory=list)


# --- The pipeline run report (06_DECISIONS.md ADR-108 phase C) -------------


class LoadReportView(BaseModel):
    """What a route answers for a load: the counts and the words, never the id lists. `LoadReport`
    keeps `created_node_ids`, `created_edge_ids`, `merged_edge_ids` and the rest for the load's own
    record; handed to the loader, `merged_edge_ids` would say a link pre-existed whether or not
    they may read it (rules 3 and 7, ADR-127 decision 6)."""

    load_id: str
    recipe_id: str
    recipe_version: int
    rows_read: int = 0
    rows_deduplicated: int = 0
    rows_already_loaded: int = 0
    nodes_created: int = 0
    nodes_referenced: int = 0
    edges_created: int = 0
    rejections: list[RejectionRecord] = Field(default_factory=list)
    rows_held: int = 0
    rule_notes: list[str] = Field(default_factory=list)
    #: Rule 3, ADR-127 Amendment 23: set where the reader may not view every marking the load's
    #: rows were written at. Every count above is then zero and the lists empty: a count of what a
    #: load wrote is a read.
    withheld: bool = False


class BranchRunReport(BaseModel):
    """One source branch's run: which source node fed it, where it read from, and the branch's
    own `LoadReport`. Each branch has its own `load_id`, so a branch remains independently
    revertible (`09_INGEST_STUDIO.md` §9.1)."""

    source_id: str
    source_label: str
    source_location: str | None = None
    report: LoadReport


class ExtractStageReport(BaseModel):
    """One extract node's run, loud about everything it did and refused (rules 2 and 5): how many
    documents it read, where its findings went, how many carried an overridden handling, and every
    refusal in words — a stage that could not run says so here, never silently does nothing."""

    node_id: str
    library: str
    output: str
    documents_read: int = 0
    candidates_queued: int = 0
    nodes_written_inferred: int = 0
    #: Findings written under the node's own `handling_override` instead of the source document's
    #: handling (ruling Q2: allowed, Author-gated, reason mandatory, loud here).
    handling_overridden: int = 0
    override_reason: str | None = None
    refusals: list[str] = Field(default_factory=list)
    #: Rule 3, ADR-127 Amendment 26: the marking of each document the stage read and of what it
    #: wrote (the `handling_override` where it has one), once each: the counts include them.
    markings: list[Handling] = Field(default_factory=list)


class EnrichStageReport(BaseModel):
    """One enrich node's run (ruling Q5: local gazetteers first, online only via the deployment's
    configured allow-list, disclosed per run). A `SAME_AS` match is `inferred`, never a merge."""

    node_id: str
    geocoder: str
    locations_considered: int = 0
    matched_local: int = 0
    matched_online: int = 0
    unmatched: int = 0
    refusals: list[str] = Field(default_factory=list)


class PipelineRunReport(BaseModel):
    """A whole pipeline's run (ADR-108 phase C): every branch's `LoadReport`, every extract and
    enrich stage's own account, and the aggregates the post-run machinery (resolution trigger,
    change stream, audit) reads uniformly with a plain `LoadReport`."""

    load_id: str
    recipe_id: str
    recipe_version: int
    branches: list[BranchRunReport] = Field(default_factory=list)
    extracts: list[ExtractStageReport] = Field(default_factory=list)
    enriches: list[EnrichStageReport] = Field(default_factory=list)
    rows_read: int = 0
    rows_already_loaded: int = 0
    nodes_created: int = 0
    nodes_referenced: int = 0
    edges_created: int = 0
    rejections: list[RejectionRecord] = Field(default_factory=list)
    created_node_ids: list[NodeId] = Field(default_factory=list)
    #: The branches' `referenced_node_ids`, each once (ADR-127 decision 7(a)).
    referenced_node_ids: list[NodeId] = Field(default_factory=list)
    touched_edge_ids: list[EdgeId] = Field(default_factory=list)
    #: The branches' held rows and rule notes, summed (ADR-109 ruling 1).
    rows_held: int = 0
    rule_notes: list[str] = Field(default_factory=list)
    #: The union of the branches' `markings`, each once (rule 3, ADR-127 Amendment 23).
    markings: list[Handling] = Field(default_factory=list)


class BranchRunReportView(BaseModel):
    """`BranchRunReport` as a route answers it: the branch's `LoadReportView`."""

    source_id: str
    source_label: str
    source_location: str | None = None
    report: LoadReportView


class PipelineRunReportView(BaseModel):
    """`PipelineRunReport` as a route answers it: counts and words, no id lists, each branch a
    `LoadReportView` (see `LoadReportView`)."""

    load_id: str
    recipe_id: str
    recipe_version: int
    branches: list[BranchRunReportView] = Field(default_factory=list)
    extracts: list[ExtractStageReport] = Field(default_factory=list)
    enriches: list[EnrichStageReport] = Field(default_factory=list)
    rows_read: int = 0
    rows_already_loaded: int = 0
    nodes_created: int = 0
    nodes_referenced: int = 0
    edges_created: int = 0
    rejections: list[RejectionRecord] = Field(default_factory=list)
    rows_held: int = 0
    rule_notes: list[str] = Field(default_factory=list)
    #: As `LoadReportView.withheld`: the reader may not view every marking the run's rows were
    #: written at, so the counts are zero and the branches and stages are left out.
    withheld: bool = False


# --- Verify (09_INGEST_STUDIO.md §5) --------------------------------------


class VerifyEntityCount(BaseModel):
    """Per entity-type counts for one dry run — §5: "Counts. Nodes and
    edges by type, how many referenced an existing node and how many
    created one." """

    created: int = 0
    referenced: int = 0


class VerifyEdgeCount(BaseModel):
    """An edge has no `match_on`/`on_match` of its own (`RecipeEdge` never
    declares one) — every edge the dry run resolves is "created" in the
    sense of "this recipe would write it"; same-pair edges within the
    sample still merge into one, occurrence-counted, the way a real load's
    `GraphArcadeDBAdapter.upsert_edges` merges them."""

    created: int = 0


class RejectionGroup(BaseModel):
    """§5: "The rejection report, grouped by cause with samples." `count`
    is always the true total for this reason — `samples` is capped
    (studio_verify.py), but the count itself never is, so a reason with
    400 rejections still reads as 400, not silently as however many
    samples happened to ride along."""

    reason: str
    count: int
    samples: list[RejectionRecord]


class VerifyReport(BaseModel):
    """The dry run's three outputs (§5) in one response: counts,
    `rejections`, and the graph it would make (`nodes`/`edges`) — the same
    `schemas.domain.Node`/`Edge` shapes `GlassCanvas` already renders, not
    a second preview-only shape invented for this screen."""

    rows_read: int
    rows_deduplicated: int
    #: ADR-127 decision 5: of the sample, the rows a run would skip because the case already kept
    #: their key. Judged exactly as the run judges, and nothing is written.
    rows_already_loaded: int = 0
    #: §3's own sample-size rule ("10,000 rows or the whole file, whichever
    #: is smaller"), restated here the same way `SourceProfile` states it —
    #: `False` means the source has more rows than this dry run covered.
    sample_is_whole_source: bool
    #: §3's independent-minimums rule, extended to Verify: `True` when the
    #: requesting principal cannot clear the *source's own* classification,
    #: in which case every would-create node/edge's property values below
    #: are shape-masked — the same rule that already stops Profile's and
    #: Map's sample views from being read in full by a principal who
    #: couldn't clear the source, applied here so Verify isn't a way around
    #: it.
    values_masked: bool
    entities_by_type: dict[str, VerifyEntityCount] = Field(default_factory=dict)
    edges_by_type: dict[str, VerifyEdgeCount] = Field(default_factory=dict)
    rejections: list[RejectionGroup] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


# --- The load ledger (01_DOMAIN_MODEL.md §2.4, ADR-018) -------------------


class LoadRecord(BaseModel):
    """One execution of a recipe against a source — the persisted form of
    a `LoadReport`. `created_node_ids` is only the nodes this load
    created, never one it merely referenced; `touched_edge_ids` is every
    edge it wrote to, created or merged into. The revert
    (`services/ingest/load_revert.py`) reads the created lists only and refuses a load that
    merged: an element a load created can be taken back without affecting another load, but
    one it merged into is shared, and `GraphArcadeDBAdapter.revert_elements` only ever sets a
    flag rather than deleting, so the audit trail stays intact regardless. Every
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
    #: ADR-127 decision 6, Amendment 5: what the run ledger keeps beside the run, so a revert needs
    #: nothing else. The case the load wrote; the links it created, and apart from them the existing
    #: links it merged occurrences into (a load that merged is refused a revert, naming them); the
    #: load a release of held rows was released from; and whether its analytics events carry the
    #: `load_id` (`AnalyticsPort.retract_load` can remove them). A record written before events
    #: were stamped has none of these keys, and reads as not stamped: a revert refuses it.
    investigation_id: str | None = None
    created_edge_ids: list[EdgeId] = Field(default_factory=list)
    merged_edge_ids: list[EdgeId] = Field(default_factory=list)
    #: The existing nodes the load wrote again (see `LoadReport.merged_node_ids`), and the geometry
    #: refs it inserted that were not already present, so a revert can remove exactly those.
    merged_node_ids: list[NodeId] = Field(default_factory=list)
    created_geometry_refs: list[str] = Field(default_factory=list)
    #: True when an extract or enrich stage fed by this load wrote a node, link or point: those are
    #: in no record, so a revert of the load would leave them, and it refuses (Amendment 6).
    uncovered_writes: bool = False
    released_from: str | None = None
    events_stamped: bool = False
    superseded_by: PrincipalId | None = None
    #: Who reverted the load and when (ADR-127 decision 6, `services/ingest/load_revert.py`):
    #: written last by a revert, so a record with `reverted_at` is one whose revert finished. Apart
    #: from `superseded_*`, which say a record was replaced and which a revert never writes. A
    #: record from before has neither, and reads as not reverted.
    reverted_at: datetime | None = None
    reverted_by: PrincipalId | None = None


ALL_MODELS: tuple[type[BaseModel], ...] = (
    ConnectorCatalogueEntry,
    ConnectDraftInput,
    DomainPackEntry,
    PipelineNode,
    PipelineEdge,
    PipelineGraph,
    StudioRecipeDraft,
    RecipeConnector,
    RecipeDefaults,
    DeduplicateConfig,
    FieldBinding,
    HandlingFieldBinding,
    RecipeCondition,
    RecipeEntity,
    TemporalBinding,
    RecipeEdge,
    UnmappedField,
    RowTemplate,
    TransformDescriptor,
    RowTemplateUpdateInput,
    MapSampleRow,
    MapHandlingPreviewRequest,
    MapHandlingPreviewResult,
    ScheduleConfig,
    PublishRecipeInput,
    ScheduleUpdateInput,
    SchedulePreviewInput,
    SchedulePreview,
    RunRecipeInput,
    Recipe,
    RejectionRecord,
    LoadReport,
    BranchRunReport,
    ExtractStageReport,
    EnrichStageReport,
    PipelineRunReport,
    LoadReportView,
    BranchRunReportView,
    PipelineRunReportView,
    VerifyEntityCount,
    VerifyEdgeCount,
    RejectionGroup,
    VerifyReport,
    LoadRecord,
)
