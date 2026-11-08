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

from schemas.domain import DomainPack, PrincipalId
from schemas.monitoring import ListSchedule

#: R12: one `live`, at most one `draft`, every earlier version `previous`.
TargetModelState = Literal["draft", "live", "previous"]

#: What an extension adds: an entity type under one of the POLE classes, a link type, or a property
#: on a type.
ExtensionKind = Literal["entity_type", "link_type", "property"]


class ModelExtension(BaseModel):
    """A type or property the dataset's own model adds beyond the core and its packs (ADR-140
    decision 4; today's analyst-proposed type, ADR-090). Retired, never deleted: a rename is "add
    the new, retire the old"."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: ExtensionKind
    #: The type a property is on; `None` for a type.
    on_type: str | None = None
    #: The model version that added it.
    added_in: int = Field(ge=1)
    #: The model version that retired it; `None` while it is in force.
    retired_in: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _a_property_names_its_type(self) -> ModelExtension:
        if (self.kind == "property") != (self.on_type is not None):
            raise ValueError("a property names the type it is on, and a type names none")
        if self.retired_in is not None and self.retired_in <= self.added_in:
            raise ValueError("an extension is retired after the version that added it")
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


class TargetModelDraftInput(BaseModel):
    """Saving the dataset's draft: its packs, extensions and lists as the editor leaves them."""

    model_config = ConfigDict(extra="forbid")

    packs: dict[DomainPack, int] = Field(default_factory=dict)
    extensions: list[ModelExtension] = Field(default_factory=list)
    reference_lists: list[str] = Field(default_factory=list)


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


ALL_MODELS: tuple[type[BaseModel], ...] = (
    ModelExtension,
    TargetModel,
    TargetModelDraftInput,
    ReferenceList,
    DatasetOwnerSetting,
    DatasetOwners,
    MakeLiveInput,
    HomeCase,
)
