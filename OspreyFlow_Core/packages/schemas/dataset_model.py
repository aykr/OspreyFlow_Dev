"""A dataset's domain model and reference lists, its home case and the owners named for it at *Make
live* (L3.1b; `01_DOMAIN_MODEL.md`).

- **`TargetModel`** (ADR-140 decisions 4 and 5, R12; called the *domain model* on screen, ADR-140
  Amendment 9 decision 1): the POLE core, always on, plus the dataset's pinned starter packs, its
  own extensions and its reference lists. Exactly one version is `live`, at most one is a `draft`
  (N+1), and every earlier one is `previous` and read-only; a revert makes a new draft, never
  rewrites a version. An extension is retired, never deleted.
- **`ReferenceList`**: a list the dataset's model refers to by key. A `screening` list (ADR-140
  Amendment 9 decision 3) is imported once for the deployment and subscribed to per dataset; its
  refresh schedule is ADR-133 Amendment 3's `ListSchedule`, which it absorbs.
- **The owners named at a dataset's first *Make live*** (ADR-145 Amendment 4 decision 4): people, a
  team, or both, as Admin › System's setting allows (decision 7); never a service account. They
  become the Authors of the dataset's **home case** (decision 2), one per dataset per deployment
  until releases bring a second environment (the stated reading of decision 5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.domain import DomainPack, PoleClass, PrincipalId, PropertyType
from schemas.monitoring import ListSchedule

#: R12: one `live`, at most one `draft`, every earlier version `previous`.
TargetModelState = Literal["draft", "live", "previous"]

#: What an extension adds: an entity type under one of the POLE classes, a link type, or a property
#: on a type.
ExtensionKind = Literal["entity_type", "link_type", "property"]


#: What a type does with a record that matches one already held: the two values the recipe
#: engine's `on_match` takes (`schemas.ingest.RecipeEntity`), and no others. `reference` uses the
#: record already held; `create` makes a new one each time.
MatchingMode = Literal["reference", "create"]


class MatchingRule(BaseModel):
    """A type's rule for when two records are the same (ADR-140 Amendment 22 item 3; the owner's
    ruling of 21 November 2026: it lives on the type record, not on each pipeline's element).

    `match_on` is the field a record is found by and `on_match` what the engine does when it finds
    one: the same two values the recipe engine takes today (`match_on` and `on_match`). A rule is
    only as good as the matching code can make it: `match_on` must name one of the type's
    identifiers or one of its indexed properties, because the store answers a lookup for those and
    no others (`services/ingest/recipe_rules.py`, `reference_match_problems`). The store refuses a
    rule that does not (`target_models._refuse_a_rule_a_reference_cannot_use`)."""

    model_config = ConfigDict(extra="forbid")

    match_on: str = Field(min_length=1)
    on_match: MatchingMode = "reference"


class ModelExtension(BaseModel):
    """A type or property the dataset's own model adds beyond the core and its packs (ADR-140
    decision 4; today's analyst-proposed type, ADR-090). Retired, never deleted: a rename is "add
    the new, retire the old".

    **An entity type's record** carries its class (one of the five POLE classes, closed), its
    identifiers and its matching rule (ADR-140 Amendment 22 item 3). **A property's record**
    names the type it is on, its value type and whether it is indexed (the ontology's own
    `PropertyDef.indexed`). Every one of these is optional, so an extension saved before they
    existed still reads (a type with no class says so on screen) and is never changed by reading
    it; a field that belongs to the other kind is refused."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: ExtensionKind
    #: The type a property is on; `None` for a type.
    on_type: str | None = None
    #: The model version that added it.
    added_in: int = Field(ge=1)
    #: The model version that retired it; `None` while it is in force.
    retired_in: int | None = Field(default=None, ge=1)
    #: An entity type's POLE class; `None` for one saved without (and for a link type or property).
    pole_class: PoleClass | None = None
    #: An entity type's identifiers, as the ontology's `EntityTypeDef.identifiers` has them.
    identifiers: list[str] = Field(default_factory=list)
    #: An entity type's rule for when two records are the same; `None` for none.
    matching: MatchingRule | None = None
    #: A property's value type; `None` for one saved without.
    value_type: PropertyType | None = None
    #: Whether a property is indexed (a lookup finds a record by it); false for a type.
    indexed: bool = False

    @model_validator(mode="after")
    def _a_property_names_its_type(self) -> ModelExtension:
        if (self.kind == "property") != (self.on_type is not None):
            raise ValueError("a property names the type it is on, and a type names none")
        if self.retired_in is not None and self.retired_in <= self.added_in:
            raise ValueError("an extension is retired after the version that added it")
        return self

    @model_validator(mode="after")
    def _a_field_belongs_to_its_kind(self) -> ModelExtension:
        if self.kind != "entity_type" and (
            self.pole_class is not None or self.identifiers or self.matching is not None
        ):
            raise ValueError("a class, identifiers and a matching rule belong to an entity type")
        if self.kind != "property" and (self.value_type is not None or self.indexed):
            raise ValueError("a value type and an indexed flag belong to a property")
        return self


class TargetModel(BaseModel):
    """One version of a dataset's domain model (R3, R12)."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    version: int = Field(ge=1)
    state: TargetModelState
    #: Each starter pack in force, at its pinned version; empty is the POLE core alone.
    packs: dict[DomainPack, int] = Field(default_factory=dict)
    extensions: list[ModelExtension] = Field(default_factory=list)
    #: The reference lists the model refers to, by id.
    reference_lists: list[str] = Field(default_factory=list)
    created_at: datetime
    created_by: PrincipalId
    #: Set when the version is made live; `None` for a draft never made live.
    made_live_at: datetime | None = None
    made_live_by: PrincipalId | None = None
    #: The version a revert copied, for a draft made by *Revert*; `None` otherwise.
    reverted_from: int | None = Field(default=None, ge=1)
    #: Which copy of the draft this is: an opaque token the store makes when the draft is opened and
    #: changes on every save, and never one a draft had before. The version alone cannot tell two
    #: copies of one draft apart (a save keeps it; a draft discarded and opened again at the same
    #: live version takes it again), so a save and a discard carry both (ADR-152 X5). `None` only
    #: for a row written past the store.
    revision: str | None = Field(default=None, min_length=1, max_length=64)


class TargetModelDraftInput(BaseModel):
    """Saving the dataset's draft: its packs, extensions and lists as the editor leaves them.

    The store's own callers (the import, the link-type acceptance, the seed) build this and confirm
    a version through the store's `expected_version` argument where they mean to. The route's
    body is `TargetModelDraftSave`, which carries the version a person's copy was read at."""

    model_config = ConfigDict(extra="forbid")

    packs: dict[DomainPack, int] = Field(default_factory=dict)
    extensions: list[ModelExtension] = Field(default_factory=list)
    reference_lists: list[str] = Field(default_factory=list)


class TargetModelDraftSave(TargetModelDraftInput):
    """`PUT /v1/datasets/{dataset_id}/model/draft`: the draft as the editor leaves it, and the
    version their copy of it was read at (ADR-152 X5; the owner's ruling of 21 November 2026). A
    save made over a draft that is no longer that version is refused in the store's words, and a
    body with no version is refused too, so a client that does not send one cannot skip the
    check. A separate model, not a field of the input, so the callers that build the input
    directly are not given a version they could set and have nothing read.

    `expected_revision` is the revision the same copy was read at (`TargetModel.revision`): where it
    is sent, a draft that was saved again, or discarded and opened again, since is refused too, even
    at the same version, which a version alone cannot tell. The Studio page always sends it; it is
    optional here so a caller that holds only a version (its check is the version's) still works."""

    expected_version: int = Field(ge=1)
    expected_revision: str | None = Field(default=None, min_length=1, max_length=64)


#: ADR-140 Amendment 9 decision 3: a `screening` list is screened against; a `reference` list is
#: looked up by key.
ReferenceListKind = Literal["reference", "screening"]


class ReferenceList(BaseModel):
    """A list the dataset's model refers to (ADR-140 decision 4). Its rows are loaded data, never
    part of a release's bundle when the list is licensed (ADR-140 Amendment 9 decision 4)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    dataset_id: str
    name: str = Field(min_length=1)
    kind: ReferenceListKind
    #: The column that identifies a row.
    key_column: str = Field(min_length=1)
    version: int = Field(ge=1)
    #: How often it is refreshed; `None` when it is refreshed by hand only.
    schedule: ListSchedule | None = None


#: ADR-145 Amendment 4 decision 7: who may be named a dataset's owner, set in Admin › System.
DatasetOwnersMayBe = Literal["people_and_teams", "people_only", "teams_only"]


class DatasetOwnerSetting(BaseModel):
    """Admin › System's *Dataset owners may be* (ADR-145 Amendment 4 decision 7); it governs *Make
    live* and *Change owner…*."""

    model_config = ConfigDict(extra="forbid")

    owners_may_be: DatasetOwnersMayBe = "people_and_teams"


class DatasetOwners(BaseModel):
    """Who answers for a dataset: people, a team, or both (ADR-145 Amendment 4 decision 4). Checked
    against the System setting and for service accounts where it is given, so the refusal is in
    words; here only that it names someone."""

    model_config = ConfigDict(extra="forbid")

    people: list[PrincipalId] = Field(default_factory=list)
    #: A team (ADR-112 Amendment 5), by its role's name; `None` for none.
    team: str | None = None

    @model_validator(mode="after")
    def _names_someone(self) -> DatasetOwners:
        if not self.people and self.team is None:
            raise ValueError("a dataset cannot go live without someone who answers for it")
        return self


class MakeLiveInput(BaseModel):
    """`POST /v1/datasets/{dataset_id}/model/make-live`. `owners` is asked for at the dataset's
    first *Make live* in the deployment and refused when given again; the maker is proposed first
    by the screen, never by the Conduit on the person's behalf."""

    model_config = ConfigDict(extra="forbid")

    #: The draft version being made live, so a draft changed since it was opened is refused.
    version: int = Field(ge=1)
    owners: DatasetOwners | None = None


class HomeCase(BaseModel):
    """A dataset's home case (ADR-145 Amendment 4 decision 2): holds its reports, its dataset-wide
    alerts and its promotion reviews; cannot be removed while the dataset exists. Every source,
    composite and drawn dataset has one; an analyst layer never does."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    investigation_id: str
    made_at: datetime
    #: Who made it: the first *Make live*'s maker, `scripts.make_home_cases`, or the drawing.
    made_by: PrincipalId


class DatasetModelView(BaseModel):
    """`GET /v1/datasets/{dataset_id}/model`: the live version and the open draft, each `None` when
    there is none (a dataset with neither has no model yet)."""

    live: TargetModel | None = None
    draft: TargetModel | None = None


class RevertModelInput(BaseModel):
    """`POST /v1/datasets/{dataset_id}/model/revert`: the earlier version to copy into a new draft
    (N+2, never a rewrite of it)."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class ImpactedPipeline(BaseModel):
    """A deployed pipeline of the dataset that writes a type the draft changes or retires: *Make
    live* marks it as needing attention and pauses its schedule, with the reason."""

    recipe_id: str
    label: str
    #: The changed or retired types it writes, sorted.
    writes: list[str]


class ImpactedCase(BaseModel):
    """A case reading the dataset (directly or through a composite) that the reader may open.
    Cases they may not open are not listed and not counted (rule 7)."""

    investigation_id: str
    name: str | None = None


class ModelImpact(BaseModel):
    """`GET /v1/datasets/{dataset_id}/model/impact` (R12, ADR-140 decision 5): what making the
    draft live would change, read before anything does. Loaded data is never rewritten."""

    dataset_id: str
    #: The live version it is measured against; `None` for a dataset's first model.
    live_version: int | None
    draft_version: int
    packs_added: list[DomainPack] = Field(default_factory=list)
    packs_removed: list[DomainPack] = Field(default_factory=list)
    #: A pack kept at another pinned version.
    packs_repinned: list[DomainPack] = Field(default_factory=list)
    extensions_added: list[str] = Field(default_factory=list)
    extensions_retired: list[str] = Field(default_factory=list)
    #: An extension the draft has in force again (a revert to a version that had it).
    extensions_restored: list[str] = Field(default_factory=list)
    #: Every entity and link type whose definition changes: the types of each pack added, removed
    #: or repinned, and each extension added, retired or restored; sorted.
    changed_types: list[str] = Field(default_factory=list)
    pipelines: list[ImpactedPipeline] = Field(default_factory=list)
    cases: list[ImpactedCase] = Field(default_factory=list)
    #: The composites that have the dataset as a member and that one of the reader's own cases
    #: reads, by name; never one they may not read, and no count of the rest (rule 7).
    composites: list[str] = Field(default_factory=list)


class MadeLive(BaseModel):
    """`POST /v1/datasets/{dataset_id}/model/make-live`'s answer: the version now live, the one it
    replaced, and each pipeline marked as needing attention, its schedule paused with the reason."""

    live: TargetModel
    previous: TargetModel | None = None
    flagged: list[ImpactedPipeline] = Field(default_factory=list)


class DrawnDatasetInput(BaseModel):
    """`POST /v1/datasets/drawn` (ADR-143 Amendment 2 decision 5; ADR-140 Amendment 9 decision 2):
    *New drawing board* with no case makes, in one step, a dataset of kind `drawn` named after the
    drawing, its domain model live at version 1 (the starter pack chosen, or the POLE core alone),
    and its home case, with the maker as its Author. The board itself is L3.3's."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    #: The starter pack the analyst picks; `None` for the POLE core alone.
    pack: DomainPack | None = None
    #: The highest marking the drawn dataset may hold, within the maker's own clearance (refused
    #: above it); a classification of the deployment's handling scheme.
    highest_marking: str = Field(min_length=1)


ALL_MODELS: tuple[type[BaseModel], ...] = (
    MatchingRule,
    ModelExtension,
    TargetModel,
    TargetModelDraftInput,
    TargetModelDraftSave,
    ReferenceList,
    DatasetOwnerSetting,
    DatasetOwners,
    MakeLiveInput,
    HomeCase,
    DatasetModelView,
    RevertModelInput,
    ImpactedPipeline,
    ImpactedCase,
    ModelImpact,
    MadeLive,
    DrawnDatasetInput,
)
