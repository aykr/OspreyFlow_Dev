"""The screening-list connector in Studio › Sources (`06_DECISIONS.md` ADR-140 Amendment 9
decision 3; Amendment 13).

A screening list is **imported once for the deployment** from a file in the ingest folder, through a
**mapping template** for its format (OFAC SDN, OFSI consolidated, the UK Sanctions List, UN, EU,
OpenSanctions where licensed) or, for a list no template covers, the **blank** template: the list's
own columns picked one by one for the one screening shape, saved as that list's own mapping. No
template holds an expression (rule 8): a mapping is column names and closed choices only.

Each import that changes the list's rows is a **new version**, its rows kept at
`<bucket>/reference_lists/deployment/<name>@v<version>.parquet` (Amendment 11's path); the same rows
again are no new version. A dataset **subscribes** to a list **by its id**, never its name (L1.3's
finding: two lists may share a name), and a dataset's rules and Lookups are offered only its own
lists and the lists it subscribes to.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.monitoring import ListSchedule
from schemas.screening import RealDataUse

#: The formats a template maps, and `blank` for a list no template covers.
ListTemplate = Literal[
    "ofac_sdn",
    "ofsi_consolidated",
    "uk_sanctions_list",
    "un_consolidated",
    "eu_consolidated",
    "opensanctions",
    "blank",
]
#: What separates many values in one cell of a client's CSV (aliases, identifiers).
ManySeparator = Literal["|", ";", ","]
#: What one import or refresh did (as ADR-133's refreshes say it).
ListImportOutcome = Literal["updated", "unchanged", "refused", "failed"]

_COLUMN = Field(min_length=1, max_length=120)
_LIST_NAME = r"^[A-Za-z0-9][A-Za-z0-9 ()_.,'-]{0,119}$"


class BlankListMapping(BaseModel):
    """A client's own list, mapped field by field: each screening field is one of the file's
    columns, or none. A person or an organisation is either one for every row, or read from a
    column whose cells must say `Person` or `Organisation` (any other value refuses its row)."""

    model_config = ConfigDict(extra="forbid")

    ref: str = _COLUMN
    primary_name: str = _COLUMN
    aliases: str | None = Field(default=None, max_length=120)
    date_of_birth: str | None = Field(default=None, max_length=120)
    nationality: str | None = Field(default=None, max_length=120)
    identifiers: str | None = Field(default=None, max_length=120)
    programme: str | None = Field(default=None, max_length=120)
    separator: ManySeparator = "|"
    entity_type: Literal["Person", "Organisation"] | None = "Person"
    entity_type_column: str | None = Field(default=None, max_length=120)
    listing: Literal["sanction", "pep", "adverse_media"] = "sanction"

    @model_validator(mode="after")
    def _one_way_to_type(self) -> BlankListMapping:
        if (self.entity_type is None) == (self.entity_type_column is None):
            raise ValueError(
                "say either that every row is a person or an organisation, or the column that says"
            )
        return self


class DeploymentListInput(BaseModel):
    """Importing a list for the deployment. `location` is a file inside the ingest folder. A list
    that is not one of OspreyFlow's synthetic files is real data: it names its dataset, which this
    device's `real_data_exceptions.yaml` must admit (rule 9), as ADR-133's lists do."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_LIST_NAME)
    template: ListTemplate
    location: str = Field(min_length=1, max_length=400)
    mapping: BlankListMapping | None = None
    dataset: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}$")
    use: RealDataUse = "local_development"

    @model_validator(mode="after")
    def _mapping_for_blank_only(self) -> DeploymentListInput:
        if self.template == "blank" and self.mapping is None:
            raise ValueError("the blank template needs the list's own mapping, field by field")
        if self.template != "blank" and self.mapping is not None:
            raise ValueError(
                "only the blank template takes a mapping; a format's template is fixed"
            )
        return self


class DeploymentList(BaseModel):
    """A deployment-wide screening list as Studio › Sources shows it."""

    id: str
    name: str
    template: ListTemplate
    location: str
    mapping: BlankListMapping | None = None
    dataset: str | None = None
    synthetic: bool = True
    licence: str
    licence_confirmed: bool = True
    licence_note: str | None = None
    #: `0` until its first import succeeds.
    version: int = 0
    entries: int = 0
    updated_at: datetime | None = None
    attempted_at: datetime | None = None
    failure: str | None = None
    schedule: ListSchedule | None = None
    schedule_words: str | None = None
    next_refresh: datetime | None = None
    created_by: str
    created_at: datetime


class ListImport(BaseModel):
    """One import or refresh: what it did, in words, and what it changed."""

    list_id: str
    outcome: ListImportOutcome
    version: int | None = None
    previous_version: int | None = None
    added: int = 0
    changed: int = 0
    delisted: int = 0
    trigger: Literal["manual", "schedule"] = "manual"
    words: str


class DatasetOwnListImportInput(BaseModel):
    """A dataset's own reference list's rows, imported from one of the dataset's own files (a CSV
    with a header row). The list's record is the one the dataset's live domain model names."""

    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=1, max_length=400)
    #: For a list's first import only: its name and the column that identifies a row. A later
    #: import takes the list's record from the version kept before it (Amendment 12).
    name: str | None = Field(default=None, min_length=1, max_length=120)
    key_column: str | None = Field(default=None, min_length=1, max_length=120)


class OfferedList(BaseModel):
    """A list a dataset's rule or Lookup may read: its own, or a deployment-wide one it subscribes
    to. Never another dataset's."""

    id: str
    name: str
    kind: Literal["reference", "screening"]
    version: int
    deployment_wide: bool


class SubscribableList(BaseModel):
    """A deployment-wide list as a dataset's source author sees it to subscribe to: what it is and
    how current, never where its file is, who added it, the real dataset it is, its mapping or its
    failure's words, which are for whoever may load screening lists (the lane review of L1.6)."""

    id: str
    name: str
    template: ListTemplate
    version: int = 0
    entries: int = 0
    updated_at: datetime | None = None
    #: Whether its last import failed; the words are the list managers'.
    failing: bool = False
    schedule_words: str | None = None


class DatasetSubscriptions(BaseModel):
    """The deployment-wide lists, and which of them this dataset subscribes to, by id."""

    lists: list[SubscribableList]
    subscribed: list[str]


class ListImports(BaseModel):
    """A list's latest imports, newest first, and whether older ones were left out (rule 2)."""

    imports: list[ListImport]
    more: bool = False


ALL_MODELS: list[type[BaseModel]] = [
    BlankListMapping,
    DeploymentListInput,
    DeploymentList,
    ListImport,
    DatasetOwnListImportInput,
    OfferedList,
    SubscribableList,
    DatasetSubscriptions,
    ListImports,
]
