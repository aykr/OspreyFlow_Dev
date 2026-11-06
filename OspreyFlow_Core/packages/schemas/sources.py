"""Connections and registered sources (`06_DECISIONS.md` ADR-140 decision 7; Amendment 4).

A **connection** is where sources are read from, owned by the deployment's administrators: today
one kind, `files` (the ingest root, `OSPREY_INGEST_ROOT`); SQL, API and JSON-schema connections are
phase 9's. A **source** is one table, file set or endpoint on a connection, registered once for a
dataset and carrying, at the source, its handling (marking, units, the columns a row's marking is
read from), its legal basis and its refresh policy. Every pipeline that uses it inherits those: the
Connect gate leaves the pipeline. Editing a source's governance is a new version of the source, and
every deployed pipeline using it then needs attention (Amendment 4, the owner's ruling).

**A source's profile is never stored.** The profiler masks sample values by the reader's clearance,
so a stored profile would show one reader what was masked for another (rule 3): it is computed for
whoever asks (`GET …/sources/{id}/profile`), as Profile is today.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .ingest import check_source_declarations

ConnectionKind = Literal["files"]
#: Phase 3 records a refresh policy; phase 4 executes it (ADR-140 decision 15).
RefreshTrigger = Literal["manual", "watch"]


class Connection(BaseModel):
    id: str
    kind: ConnectionKind
    name: str
    created_by: str
    created_at: datetime


class ConnectionInput(BaseModel):
    kind: ConnectionKind = "files"
    name: str = Field(min_length=1, max_length=200)


class SourceRefresh(BaseModel):
    """When the source is read again (ADR-140 decision 15). A file source's watch takes each new
    file whose whole name matches `pattern` (`*`, `?` and `[…]`, nothing else; ADR-110 Amendment
    4)."""

    trigger: RefreshTrigger = "manual"
    pattern: str | None = None


class SourceTable(BaseModel):
    id: str
    dataset_id: str
    connection_id: str
    name: str
    #: For a `files` connection, the file's location as the ingest-root listing names it.
    location: str
    connector_profile: str
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None
    refresh: SourceRefresh = Field(default_factory=SourceRefresh)
    #: A governance edit is a new version (`edit_governance`); the first is 1.
    version: int = 1
    created_by: str
    created_at: datetime
    updated_by: str | None = None
    updated_at: datetime | None = None


class RegisterSourceInput(BaseModel):
    connection_id: str
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1)
    connector_profile: str = "generic-csv"
    handling: dict[str, Any] = Field(default_factory=dict)
    legal_basis: str | None = None
    refresh: SourceRefresh = Field(default_factory=SourceRefresh)

    @field_validator("handling")
    @classmethod
    def _declarations(cls, value: dict[str, Any]) -> dict[str, Any]:
        return check_source_declarations(value)


class SourceGovernanceInput(BaseModel):
    """An edit of a source's governance, audited; a new version of the source."""

    handling: dict[str, Any]
    legal_basis: str | None = None
    refresh: SourceRefresh | None = None

    @field_validator("handling")
    @classmethod
    def _declarations(cls, value: dict[str, Any]) -> dict[str, Any]:
        return check_source_declarations(value)


class SourceLineage(BaseModel):
    """A pipeline that uses a source: what the source page lists under *Lineage*."""

    recipe_id: str
    label: str
    version: int
    status: str


class GovernanceEdited(BaseModel):
    source: SourceTable
    #: The deployed pipelines now needing attention, by label.
    needs_attention: list[str] = Field(default_factory=list)


ALL_MODELS: list[type[BaseModel]] = [
    Connection, ConnectionInput, SourceRefresh, SourceTable, RegisterSourceInput,
    SourceGovernanceInput, SourceLineage, GovernanceEdited,
]  # fmt: skip
