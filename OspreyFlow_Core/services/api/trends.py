"""Trend reports (`06_DECISIONS.md` ADR-113 decisions 1 and 2): what a builder may offer from the
deployment's ontology, the check every definition passes before it is saved or run, its translation
into the analytics port's closed `TrendRequest`, and the store of saved definitions.

A definition names only what the ontology declares: temporal link types (the events the analytics
store holds), a numeric property for a sum, a categorical property for a series or a filter. A
link type's aliases (ADR-090) are read with it, and an alias's series counts under the type's name.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import asyncpg

from conduit_common.identity import new_id
from schemas.analytics import (
    EventFilter,
    TrendMeasure,
    TrendPoint,
    TrendRequest,
    TrendResult,
)
from schemas.domain import EdgeTypeDef, Interval, OntologySchema, Principal, PropertyType
from schemas.trends import (
    BY_EVENT_TYPE,
    TrendDefinition,
    TrendDefinitionInput,
    TrendEventTypeOption,
    TrendFieldOption,
    TrendOptions,
)

_NUMBER = {PropertyType.INTEGER, PropertyType.FLOAT}
_CATEGORY = {PropertyType.ENUM, PropertyType.STRING, PropertyType.BOOLEAN}


class TrendDefinitionRefused(ValueError):
    """A definition naming what the ontology does not declare; said in words (a 422)."""


def _event_types(ontology: OntologySchema) -> list[EdgeTypeDef]:
    return [e for e in ontology.edge_types if e.temporal and not e.hidden and not e.system]


def _label(edge: EdgeTypeDef) -> str:
    return edge.label or edge.name.replace("_", " ").capitalize()


def trend_options(ontology: OntologySchema) -> TrendOptions:
    options = []
    for edge in _event_types(ontology):
        fields = [
            TrendFieldOption(
                name=p.name,
                kind="number" if p.type in _NUMBER else "category",
                values=list(p.values or []),
            )
            for p in edge.properties
            if p.type in _NUMBER | _CATEGORY and p.sensitivity != "high"
        ]
        options.append(TrendEventTypeOption(name=edge.name, label=_label(edge), fields=fields))
    return TrendOptions(event_types=options)


def validate_definition(defn: TrendDefinitionInput, ontology: OntologySchema) -> None:
    """Refuses, in words, anything the ontology does not declare for every chosen event type."""
    offered = {o.name: o for o in trend_options(ontology).event_types}
    unknown = [t for t in defn.event_types if t not in offered]
    if unknown:
        raise TrendDefinitionRefused(f"not an event type of this deployment: {', '.join(unknown)}")
    chosen = [offered[t] for t in dict.fromkeys(defn.event_types)]

    def declared(name: str, kind: str) -> list[TrendFieldOption]:
        found = [
            next((f for f in o.fields if f.name == name and f.kind == kind), None) for o in chosen
        ]
        missing = [o.label for o, f in zip(chosen, found, strict=True) if f is None]
        if missing:
            what = "numeric" if kind == "number" else "categorical"
            raise TrendDefinitionRefused(
                f"{name!r} is not a {what} property of: {', '.join(missing)}"
            )
        return [f for f in found if f is not None]

    if defn.measure is TrendMeasure.SUM:
        if not defn.measure_field:
            raise TrendDefinitionRefused("a sum needs the numeric property it adds up")
        declared(defn.measure_field, "number")
    elif defn.measure_field:
        raise TrendDefinitionRefused("a count adds up no property; leave the property empty")
    if defn.group_by and defn.group_by != BY_EVENT_TYPE:
        declared(defn.group_by, "category")
    for f in defn.filters:
        fields = declared(f.field, "category")
        allowed = {v for field in fields for v in field.values}
        if allowed and f.value not in allowed:
            raise TrendDefinitionRefused(f"{f.value!r} is not a value of {f.field!r}")


def _storage_names(ontology: OntologySchema, names: Sequence[str]) -> dict[str, str]:
    """Every stored name an event of these types may carry -> the type's own name."""
    out: dict[str, str] = {}
    for name in names:
        edge = ontology.edge_type(name)
        out[name] = name
        for alias in edge.aliases if edge else []:
            out[alias] = name
    for stored, shown in ontology.storage_aliases.items():
        if shown in names:
            out[stored] = shown
    return out


def to_request(
    defn: TrendDefinitionInput, ontology: OntologySchema, case_id: str, now: datetime
) -> tuple[TrendRequest, datetime]:
    start = now - timedelta(weeks=defn.weeks)
    names = _storage_names(ontology, defn.event_types)
    request = TrendRequest(
        filter=EventFilter(
            investigation_scope=case_id,
            window=Interval(valid_from=start, valid_to=now),
            edge_types=sorted(names),
            value_filters={f.field: [f.value] for f in defn.filters},
        ),
        interval=defn.interval,
        measure=defn.measure,
        measure_field=defn.measure_field,
        group_by="edge_type" if defn.group_by == BY_EVENT_TYPE else defn.group_by,
    )
    return request, start


def name_series(
    result: TrendResult, defn: TrendDefinitionInput, ontology: OntologySchema
) -> TrendResult:
    """A series by event type is shown under each type's own name, its aliases' events with it."""
    if defn.group_by != BY_EVENT_TYPE:
        return result
    names = _storage_names(ontology, defn.event_types)
    merged: dict[tuple[datetime, str | None], float] = {}
    for p in result.points:
        key = (p.period_start, names.get(p.series or "", p.series))
        merged[key] = merged.get(key, 0.0) + p.value
    points = [TrendPoint(period_start=k[0], series=k[1], value=v) for k, v in sorted(
        merged.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))]  # fmt: skip
    return result.model_copy(
        update={"points": points, "series": sorted({p.series for p in points if p.series})}
    )


def highest(classifications: Sequence[str], order: Sequence[str]) -> str | None:
    """The highest of these classifications by the deployment's scheme; an unknown one ranks above
    every known one, so a snapshot is never marked lower than something it counted."""
    if not classifications:
        return None
    rank = {c: i for i, c in enumerate(order)}
    return max(classifications, key=lambda c: rank.get(c, len(order)))


_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS trend_definitions (
    id TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL,
    definition JSONB NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS trend_definitions_case ON trend_definitions (investigation_id);
"""


class TrendStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> TrendStore:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
        async with pool.acquire() as conn:
            await conn.execute(_BOOTSTRAP)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @staticmethod
    def _row(row: asyncpg.Record) -> TrendDefinition:
        return TrendDefinition(
            **json.loads(row["definition"]),
            id=row["id"],
            investigation_id=row["investigation_id"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def create(
        self, case_id: str, defn: TrendDefinitionInput, by: Principal
    ) -> TrendDefinition:
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO trend_definitions VALUES ($1, $2, $3, $4, $5, $5) RETURNING *",
                new_id(), case_id, defn.model_dump_json(), by.id, now,
            )  # fmt: skip
        assert row is not None
        return self._row(row)

    async def list_for_case(self, case_id: str) -> list[TrendDefinition]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM trend_definitions WHERE investigation_id = $1 ORDER BY created_at",
                case_id,
            )
        return [self._row(r) for r in rows]

    async def get(self, case_id: str, trend_id: str) -> TrendDefinition | None:
        """Only within its own case: another case's trend is not found."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM trend_definitions WHERE id = $1 AND investigation_id = $2",
                trend_id, case_id,
            )  # fmt: skip
        return self._row(row) if row else None

    async def delete(self, case_id: str, trend_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM trend_definitions WHERE id = $1 AND investigation_id = $2",
                trend_id, case_id,
            )  # fmt: skip
        return str(result).endswith(" 1")
