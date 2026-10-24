"""Trend reports (`06_DECISIONS.md` ADR-113 decision 1): a saved, closed definition per case — event
types from the deployment ontology, a measure, a period, an optional series and optional filters.
Nothing in it is a formula; every choice is checked against the ontology before it is saved or run.
Generated into TypeScript for the Glass's trend builder."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.analytics import TrendInterval, TrendMeasure, TrendResult

#: Group by the event's type rather than by one of its properties.
BY_EVENT_TYPE = "event_type"


class TrendFilter(BaseModel):
    """Only events whose property equals this value."""

    field: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=200)


class TrendDefinitionInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    event_types: list[str] = Field(min_length=1, max_length=12)
    measure: TrendMeasure = TrendMeasure.COUNT
    #: A numeric property every chosen event type declares; only for a sum.
    measure_field: str | None = None
    interval: TrendInterval = TrendInterval.WEEK
    #: How far back, in weeks, from now.
    weeks: int = Field(default=12, ge=1, le=104)
    #: `event_type`, or a categorical property every chosen event type declares; none for a single
    #: series.
    group_by: str | None = None
    filters: list[TrendFilter] = Field(default_factory=list, max_length=5)


class TrendDefinition(TrendDefinitionInput):
    id: str
    investigation_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    #: ADR-126 decision 6: the definition uses a link type outside the case's domain packs as they
    #: stand now. Computed on read, never stored; such a trend still runs, and a pack holding it
    #: still refreshes.
    outside_case_domains: bool = False


class TrendFieldOption(BaseModel):
    name: str
    kind: Literal["number", "category"]
    #: An enumeration's values, when the ontology declares them.
    values: list[str] = Field(default_factory=list)


class TrendEventTypeOption(BaseModel):
    name: str
    label: str
    fields: list[TrendFieldOption] = Field(default_factory=list)


class TrendOptions(BaseModel):
    """What the builder may offer for this deployment's ontology: its temporal link types and,
    for each, the properties a sum or a series may use."""

    event_types: list[TrendEventTypeOption]


class TrendFigures(BaseModel):
    """A trend computed for the reader at `as_of` — never stored; a pack keeps a snapshot."""

    definition: TrendDefinitionInput
    result: TrendResult
    as_of: datetime
    window_start: datetime
    #: The highest classification among the events counted, by the deployment's handling scheme.
    marking: str | None = None


TrendOption = Literal["shorter_period", "monthly_interval", "fewer_series"]
_TREND_OPTIONS: tuple[TrendOption, ...] = ("shorter_period", "monthly_interval", "fewer_series")


class TrendLimitExceededBody(BaseModel):
    error: Literal["limit_exceeded"] = "limit_exceeded"
    cap_kind: Literal["periods", "series"]
    cap: int
    would_be: int
    options: list[TrendOption] = Field(default_factory=lambda: list(_TREND_OPTIONS))


ALL_MODELS: tuple[type[BaseModel], ...] = (
    TrendFilter,
    TrendDefinitionInput,
    TrendDefinition,
    TrendFieldOption,
    TrendEventTypeOption,
    TrendOptions,
    TrendFigures,
    TrendLimitExceededBody,
)
