"""The headless ingest recipe execution engine — `09_INGEST_STUDIO.md` §6,
`03_CONDUIT_MIDDLEWARE.md` §5.1. This lands headless in Phase 2; the Ingest
Studio (Phase 5a) is a visual editor over this same recipe format and
drives this same engine, never a second execution path (ADR-018).

**Deduplication first, on the source row's own values** —
`01_DOMAIN_MODEL.md` §7's CDR content-hash rule, generalised to whatever
key the recipe declares.

**Resolve the whole row before writing any of it.** Every `FieldBinding` for
every entity and edge in the row template is resolved — pure computation,
no I/O — before the first `GraphPort` write for that row happens. A
normaliser failure on the third property must not leave the first entity's
node already written; rejecting a row is all-or-nothing.

**Stage twice, not once, and stage(raw) comes first.**
`03_CONDUIT_MIDDLEWARE.md` §5.1: `run_recipe` writes every source row to
Parquet exactly as the connector produced it *before* `resolve_rows`
(normalisation) touches any of it, then writes `resolve_rows`'s resolved,
deduplicated `StagedRow`s to a second Parquet dataset and reads that
back before the first `GraphPort` write. Staging only the post-transform
rows — this module's original shape — meant "re-run against the raw
value" was only true for fields a recipe happened to bind twice; that was
a real defect (`staging.py`'s module docstring), not a design choice. The
load step's actual input is what the normalised stage returns, not the
in-memory list `resolve_rows` produced, so that round trip stays
load-bearing, not cosmetic — the raw stage is not re-read within the same
run at all; it exists for a later one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from ulid import ULID

from knowledge_adapters import ARITY
from knowledge_adapters.datetime_adapter import DatetimeResult
from knowledge_adapters.errors import NormalisationError
from ports.graph import GraphPort
from schemas.analytics import EventRecord
from schemas.domain import (
    EdgeId,
    EdgeTypeDef,
    EdgeWrite,
    EntityTypeDef,
    Handling,
    Interval,
    NodeId,
    NodeWrite,
    OntologySchema,
    Principal,
    PropertyType,
    Provenance,
    ProvenanceState,
    SourceRef,
    TxId,
)
from schemas.ingest import (
    FieldBinding,
    LoadReport,
    Recipe,
    RecipeCondition,
    RecipeEdge,
    RecipeEntity,
    RejectionRecord,
)

from .staging import ObjectStorageConfig, StagedEdge, StagedEntity, StagedRow
from .staging import read_staged_rows as _read_staged_rows
from .staging import stage_raw_rows as _stage_raw_rows
from .staging import stage_rows as _stage_rows
from .transforms import apply_transform


class RowRejected(Exception):
    """Raised while resolving one row — caught per row by `run_recipe`, so
    one bad row never stops the load and never leaves a partial write."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class StaleRecipeError(Exception):
    """Raised when a recipe's `ontology_version` no longer matches the
    active ontology — `09_INGEST_STUDIO.md`: "An ontology change that
    invalidates a recipe flags it and blocks scheduled runs until someone
    opens it. Recipes never silently adapt." Whether *this particular*
    change actually invalidates the recipe is not evaluated — any version
    mismatch blocks, which is what makes the guard trustworthy rather than
    a judgement call re-litigated on every run."""


def dedup_key(
    row: Mapping[str, str],
    key_bindings: list[FieldBinding],
    *,
    connector_defaults: Mapping[str, str | None] | None = None,
) -> str | None:
    """`01_DOMAIN_MODEL.md` §7 rule 2: every key field is canonicalised
    through its own Knowledge Adapter before hashing — the same
    resolution path a row-template property uses, not a second
    implementation. `start_ts_to_second` means the normalised UTC instant
    truncated to the second, not the source string.

    Returns `None` when a key field fails to resolve — such a row cannot
    be safely matched against anything, including a genuine duplicate of
    itself, so the caller treats it as its own singleton group and lets
    the normal per-row resolution reject it with the same underlying
    error, rather than this function inventing a second rejection path.
    """
    parts: list[str] = []
    for binding in key_bindings:
        try:
            value = _resolve_binding(binding, row, connector_defaults=connector_defaults)
        except RowRejected:
            return None
        if isinstance(value, DatetimeResult):
            value = value.utc.replace(microsecond=0).isoformat()
        parts.append(str(value))
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def _condition_holds(condition: RecipeCondition | None, row: Mapping[str, str]) -> bool:
    if condition is None:
        return True
    value = row.get(condition.field)
    present = value is not None and value != ""
    if condition.is_ == "not_null":
        return present
    if condition.is_ == "null":
        return not present
    if condition.equals is not None:
        return bool(value == condition.equals)
    return True


def _resolve_binding(
    binding: FieldBinding,
    row: Mapping[str, str],
    *,
    connector_defaults: Mapping[str, str | None] | None = None,
) -> object:
    if binding.literal is not None:
        return binding.literal
    if binding.fields is not None:
        # The multi-column path. There is no bare-passthrough or `map`
        # case here: combining several source columns only makes sense
        # through a declared transform, and only one whose arity — how
        # many columns it takes — is declared in `knowledge_adapters.ARITY`
        # (a British National Grid reference split across a letter pair
        # and two numeric columns is three; a plain easting/northing pair
        # is two — the count is the adapter's to declare, not a fixed
        # assumption here).
        if binding.transform is None:
            raise RowRejected("a `fields` binding must declare a `transform`")
        arity = ARITY.get(binding.transform)
        if arity is None:
            raise RowRejected(
                f"transform {binding.transform!r} does not support a multi-field `fields` binding"
            )
        if len(binding.fields) != arity:
            raise RowRejected(
                f"transform {binding.transform!r} takes {arity} field(s), "
                f"got {len(binding.fields)}"
            )
        values: list[str] = []
        for name in binding.fields:
            value = row.get(name)
            if value is None or value == "":
                raise RowRejected(f"required field {name!r} is missing")
            values.append(value)
        try:
            return apply_transform(
                binding.transform, tuple(values), connector_defaults=connector_defaults
            )
        except NormalisationError as exc:
            raise RowRejected(str(exc)) from exc
    if binding.field is None:
        raise RowRejected("binding declares neither `field`, `fields` nor `literal`")
    field_value = row.get(binding.field)
    if field_value is None or field_value == "":
        raise RowRejected(f"required field {binding.field!r} is missing")
    if binding.map is not None:
        if field_value not in binding.map:
            raise RowRejected(
                f"value {field_value!r} for field {binding.field!r} is not in the declared map"
            )
        return binding.map[field_value]
    if binding.transform is not None:
        try:
            return apply_transform(
                binding.transform, field_value, connector_defaults=connector_defaults
            )
        except NormalisationError as exc:
            raise RowRejected(str(exc)) from exc
    return field_value


def _coerce_declared_numeric_types(
    properties: dict[str, Any], type_def: EntityTypeDef | EdgeTypeDef | None
) -> dict[str, Any]:
    """A plain field binding (no `transform`, no `map`) is a bare CSV
    string. Coercing it to what the ontology actually declares —
    `integer`/`float` only, never `string` — happens here, against the
    ontology's own type, rather than by guessing from the value's shape
    (`01621926368` looks numeric and must not become one; a Knowledge
    Adapter or a `map` result is never touched here, only what a plain
    binding left as a raw string)."""
    if type_def is None:
        return properties
    declared = {p.name: p for p in type_def.properties}
    coerced = dict(properties)
    for name, value in properties.items():
        if not isinstance(value, str):
            continue
        prop = declared.get(name)
        if prop is None:
            continue
        try:
            if prop.type is PropertyType.INTEGER:
                coerced[name] = int(value)
            elif prop.type is PropertyType.FLOAT:
                coerced[name] = float(value)
        except ValueError:
            pass  # left as the original string; validate_properties will reject it
    return coerced


def _resolve_properties(
    bindings: Mapping[str, FieldBinding],
    row: Mapping[str, str],
    *,
    connector_defaults: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    return {
        name: _resolve_binding(binding, row, connector_defaults=connector_defaults)
        for name, binding in bindings.items()
    }


def _resolve_temporal_instant(
    binding: FieldBinding,
    row: Mapping[str, str],
    *,
    connector_defaults: Mapping[str, str | None] | None = None,
) -> datetime:
    value = _resolve_binding(binding, row, connector_defaults=connector_defaults)
    if isinstance(value, DatetimeResult):
        return value.utc
    if isinstance(value, datetime):
        return value
    raise RowRejected(f"temporal binding did not resolve to a datetime: {value!r}")


def _handling(defaults: Mapping[str, Any]) -> Handling:
    raw = dict(defaults)
    originator = raw.get("originator")
    if originator is None:
        raise RowRejected("recipe defaults.handling has no `originator`")
    raw.setdefault("owning_unit", originator)
    raw.setdefault("handling_code", "P")
    return Handling.model_validate(raw)


def _provenance(
    defaults: Mapping[str, Any], *, source: str, row_index: int, now: datetime
) -> Provenance:
    state = defaults.get("state", "asserted")
    return Provenance(
        state=ProvenanceState(state),
        sources=[SourceRef(document_id=source, locator=f"row {row_index}", excerpt_hash="")],
        first_seen=now,
    )


@dataclass
class _RunState:
    graph: GraphPort
    tx: TxId
    principal: Principal
    load_id: str
    recipe: Recipe
    ontology: OntologySchema
    source: str
    investigation_scope: str
    created_node_ids: list[NodeId] = field(default_factory=list)
    touched_edge_ids: list[EdgeId] = field(default_factory=list)
    nodes_created: int = 0
    nodes_referenced: int = 0
    edges_written: int = 0
    #: Within-load cache so the same value referenced by two rows in one
    #: load resolves to one node without depending on read-your-own-write
    #: visibility from a query issued inside the same open transaction.
    local_index: dict[tuple[str, str], NodeId] = field(default_factory=dict)


class _ResolvedEntity:
    __slots__ = ("entity", "properties")

    def __init__(self, entity: RecipeEntity, properties: dict[str, Any] | None) -> None:
        self.entity = entity
        self.properties = properties  # None means the entity's `when` did not hold this row


class _ResolvedEdge:
    __slots__ = ("edge", "properties", "instant")

    def __init__(
        self, edge: RecipeEdge, properties: dict[str, Any] | None, instant: datetime | None
    ) -> None:
        self.edge = edge
        self.properties = properties  # None means the edge's `when` did not hold this row
        self.instant = instant


def _resolve_row(
    recipe: Recipe,
    row: Mapping[str, str],
    *,
    connector_defaults: Mapping[str, str | None],
) -> tuple[list[_ResolvedEntity], list[_ResolvedEdge]]:
    """Phase 1: pure resolution, no I/O. Raises `RowRejected` for the whole
    row on the first failing binding anywhere in it."""
    entities = []
    for entity in recipe.row_template.entities:
        if not _condition_holds(entity.when, row):
            entities.append(_ResolvedEntity(entity, None))
            continue
        properties = _resolve_properties(
            entity.properties, row, connector_defaults=connector_defaults
        )
        entities.append(_ResolvedEntity(entity, properties))

    edges = []
    for edge in recipe.row_template.edges:
        if not _condition_holds(edge.when, row):
            edges.append(_ResolvedEdge(edge, None, None))
            continue
        properties = _resolve_properties(
            edge.properties, row, connector_defaults=connector_defaults
        )
        instant = (
            _resolve_temporal_instant(edge.temporal.at, row, connector_defaults=connector_defaults)
            if edge.temporal
            else None
        )
        edges.append(_ResolvedEdge(edge, properties, instant))

    return entities, edges


def _to_staged_row(
    resolved_entities: list[_ResolvedEntity],
    resolved_edges: list[_ResolvedEdge],
    *,
    load_id: str,
    recipe_id: str,
    recipe_version: int,
    source: str,
    row_index: int,
    duplicate_row_indices: list[int],
) -> StagedRow:
    """A conditional entity/edge whose `when` did not hold this row
    (`properties is None`) is simply omitted — the load step processes
    whichever refs are present in the staged row and treats an absent one
    exactly like a conditionally-skipped one, so nothing downstream needs
    to know staging happened at all."""
    return StagedRow(
        load_id=load_id,
        recipe_id=recipe_id,
        recipe_version=recipe_version,
        source=source,
        row_index=row_index,
        duplicate_row_indices=duplicate_row_indices,
        entities=[
            StagedEntity(ref=e.entity.ref, type=e.entity.type, properties=e.properties)
            for e in resolved_entities
            if e.properties is not None
        ],
        edges=[
            StagedEdge(
                type=e.edge.type,
                from_ref=e.edge.from_ref,
                to_ref=e.edge.to_ref,
                properties=e.properties,
                instant=e.instant,
            )
            for e in resolved_edges
            if e.properties is not None
        ],
    )


def resolve_rows(
    recipe: Recipe,
    rows: Iterable[Mapping[str, str]],
    *,
    load_id: str,
    source: str,
) -> tuple[list[StagedRow], list[RejectionRecord], int, int]:
    """Phase 1 of `run_recipe`, extracted so staging sits between
    resolution and load rather than being folded invisibly into one
    function. Returns `(staged_rows, rejections, rows_read,
    rows_deduplicated)` — pure, no I/O of any kind, including no object
    storage: `run_recipe` is the only caller that writes anything."""
    connector_defaults: Mapping[str, str | None] = {
        "date_order": recipe.connector.date_order,
        "source_crs": recipe.connector.source_crs,
    }
    dedup_fields = recipe.deduplicate.key if recipe.deduplicate else None

    # Materialised once and pre-grouped by dedup key, so the survivor of
    # each group can carry every duplicate's row index into its provenance
    # — a single streaming pass could only ever skip a duplicate, not
    # attribute it (`01_DOMAIN_MODEL.md` §7: "retaining every source row
    # reference on the surviving event").
    materialized_rows = list(rows)
    rows_read = len(materialized_rows)
    groups: dict[str, list[int]] = {}
    group_order: list[str] = []
    for row_index, row in enumerate(materialized_rows):
        key = None
        if dedup_fields is not None:
            key = dedup_key(row, dedup_fields, connector_defaults=connector_defaults)
        if key is None:
            # No dedup key declared, or this row's key fields failed to
            # resolve — either way it cannot be matched against anything,
            # so it gets its own singleton group and the normal per-row
            # resolution below rejects it with the real reason.
            key = f"__unkeyed_{row_index}"
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(row_index)
    rows_deduplicated = rows_read - len(group_order)

    staged_rows: list[StagedRow] = []
    rejections: list[RejectionRecord] = []
    for key in group_order:
        row_index, *duplicate_row_indices = groups[key]
        row = materialized_rows[row_index]
        try:
            resolved_entities, resolved_edges = _resolve_row(
                recipe, row, connector_defaults=connector_defaults
            )
        except RowRejected as exc:
            rejections.append(
                RejectionRecord(row_index=row_index, reason=exc.reason, sample=str(dict(row)))
            )
            continue
        staged_rows.append(
            _to_staged_row(
                resolved_entities,
                resolved_edges,
                load_id=load_id,
                recipe_id=recipe.id,
                recipe_version=recipe.version,
                source=source,
                row_index=row_index,
                duplicate_row_indices=duplicate_row_indices,
            )
        )

    return staged_rows, rejections, rows_read, rows_deduplicated


async def _write_entity(
    resolved: _ResolvedEntity, *, row_index: int, now: datetime, state: _RunState
) -> NodeId | None:
    if resolved.properties is None:
        return None
    entity = resolved.entity
    properties = _coerce_declared_numeric_types(
        resolved.properties, state.ontology.entity_type(entity.type)
    )
    handling = _handling(state.recipe.defaults.handling)
    provenance = _provenance(
        state.recipe.defaults.provenance, source=state.source, row_index=row_index, now=now
    )

    if entity.on_match == "reference" and entity.match_on:
        match_value = str(properties.get(entity.match_on))
        cache_key = (entity.type, match_value)
        cached = state.local_index.get(cache_key)
        if cached is not None:
            state.nodes_referenced += 1
            return cached
        existing = await state.graph.find_node(
            entity.type, entity.match_on, match_value, state.principal
        )
        if existing is not None:
            state.local_index[cache_key] = existing.id
            state.nodes_referenced += 1
            return existing.id

    write = NodeWrite(
        type=entity.type,
        properties=properties,
        provenance=provenance,
        handling=handling,
        created_by=state.principal.id,
        load_id=state.load_id,
        recipe_id=state.recipe.id,
        recipe_version=state.recipe.version,
    )
    (node_id,) = await state.graph.upsert_nodes([write], state.tx)
    state.created_node_ids.append(node_id)
    state.nodes_created += 1
    if entity.on_match == "reference" and entity.match_on:
        match_value = str(properties.get(entity.match_on))
        state.local_index[(entity.type, match_value)] = node_id
    return node_id


async def _write_edge(
    resolved: _ResolvedEdge,
    refs: Mapping[str, NodeId],
    *,
    row_index: int,
    duplicate_row_indices: list[int],
    now: datetime,
    state: _RunState,
    events: list[EventRecord],
) -> None:
    if resolved.properties is None:
        return
    edge = resolved.edge
    source_id = refs.get(edge.from_ref)
    target_id = refs.get(edge.to_ref)
    if source_id is None or target_id is None:
        return  # an endpoint entity was conditionally absent this row

    properties = _coerce_declared_numeric_types(
        resolved.properties, state.ontology.edge_type(edge.type)
    )
    handling = _handling(state.recipe.defaults.handling)
    provenance = _provenance(
        state.recipe.defaults.provenance, source=state.source, row_index=row_index, now=now
    )
    # `01_DOMAIN_MODEL.md` §7: duplicate rows collapse to one event, but
    # every source row reference is retained on the survivor — every
    # collapsed duplicate's row index, not just the representative row's.
    for duplicate_index in duplicate_row_indices:
        provenance.sources.append(
            SourceRef(document_id=state.source, locator=f"row {duplicate_index}", excerpt_hash="")
        )
    interval = (
        Interval(valid_from=resolved.instant, valid_to=resolved.instant)
        if resolved.instant
        else None
    )

    write = EdgeWrite(
        type=edge.type,
        source=source_id,
        target=target_id,
        properties=properties,
        interval=interval,
        occurrences=1,
        provenance=provenance,
        handling=handling,
        created_by=state.principal.id,
        load_id=state.load_id,
        recipe_id=state.recipe.id,
        recipe_version=state.recipe.version,
    )
    (edge_id,) = await state.graph.upsert_edges([write], state.tx)
    state.touched_edge_ids.append(edge_id)
    state.edges_written += 1

    if resolved.instant is not None:
        # The event's own properties carry the full set of source rows it
        # summarises — the surviving event's provenance chain, same as the
        # edge's above.
        event_properties = {
            **properties,
            "source_rows": [row_index, *duplicate_row_indices],
        }
        events.append(
            EventRecord(
                event_id=str(ULID()),
                edge_id=edge_id,
                edge_type=edge.type,
                source_id=source_id,
                target_id=target_id,
                occurred_at=resolved.instant,
                duration_s=_as_float(properties.get("duration_s")),
                cell_site=_as_str(properties.get("cell_site")),
                lat=_as_float(properties.get("lat")),
                lon=_as_float(properties.get("lon")),
                direction=_as_str(properties.get("direction")),
                properties=event_properties,
                investigation_scope=state.investigation_scope,
                handling=handling,
            )
        )


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _as_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _staged_entity_to_resolved(staged: StagedEntity, recipe: Recipe) -> _ResolvedEntity:
    entities_by_ref = {e.ref: e for e in recipe.row_template.entities}
    recipe_entity = entities_by_ref[staged.ref]
    return _ResolvedEntity(recipe_entity, staged.properties)


def _staged_edge_to_resolved(staged: StagedEdge) -> _ResolvedEdge:
    # match_on/on_match are entity-only concerns; an edge's row-template
    # config beyond type/from/to (`when`, `temporal`) was already applied
    # during resolution, so a minimal `RecipeEdge` carrying just what
    # `_write_edge` actually reads (`type`, `from_ref`, `to_ref`) is enough
    # — not a lookup into `recipe.row_template.edges`, which has no stable
    # per-edge identity to look up by.
    recipe_edge = RecipeEdge.model_validate(
        {"type": staged.type, "from": staged.from_ref, "to": staged.to_ref}
    )
    return _ResolvedEdge(recipe_edge, staged.properties, staged.instant)


async def run_recipe(
    recipe: Recipe,
    rows: Iterable[Mapping[str, str]],
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    tx: TxId,
    principal: Principal,
    load_id: str,
    investigation_scope: str,
    source: str,
    storage: ObjectStorageConfig | None = None,
) -> tuple[LoadReport, list[EventRecord]]:
    if recipe.ontology_version != ontology.version:
        raise StaleRecipeError(
            f"recipe {recipe.id!r} targets ontology version {recipe.ontology_version}, but the "
            f"active ontology is version {ontology.version} — open and re-publish the recipe "
            "before running it again"
        )

    # Materialised once, immediately, so `stage_raw_rows` sees every field
    # exactly as the connector produced it — before `resolve_rows` (the
    # pipeline's "normalise" step) touches any of it.
    # `03_CONDUIT_MIDDLEWARE.md` §5.1: raw staging happens first, and only
    # it makes re-resolution and schema migration possible without a
    # re-upload; staging only the post-transform rows, this module's
    # original shape, was a defect, not a design choice.
    materialized_rows = list(rows)
    storage = storage or ObjectStorageConfig.from_env()
    _stage_raw_rows(materialized_rows, storage=storage, load_id=load_id, source=source)

    staged_rows, rejections, rows_read, rows_deduplicated = resolve_rows(
        recipe, materialized_rows, load_id=load_id, source=source
    )

    # Stage the normalised rows, then read back — the loop below iterates
    # `loaded_rows`, not `staged_rows`, so a bug that only shows up after a
    # real Parquet round trip (a type MinIO/Arrow cannot represent, an
    # encoding mismatch) fails here, not silently.
    staged_path = _stage_rows(staged_rows, storage=storage, load_id=load_id)
    loaded_rows = _read_staged_rows(staged_path, storage=storage)

    state = _RunState(
        graph=graph,
        tx=tx,
        principal=principal,
        load_id=load_id,
        recipe=recipe,
        ontology=ontology,
        source=source,
        investigation_scope=investigation_scope,
    )
    events: list[EventRecord] = []

    for staged_row in loaded_rows:
        now = datetime.now(UTC)
        refs: dict[str, NodeId] = {}
        for staged_entity in staged_row.entities:
            resolved_entity = _staged_entity_to_resolved(staged_entity, recipe)
            node_id = await _write_entity(
                resolved_entity, row_index=staged_row.row_index, now=now, state=state
            )
            if node_id is not None:
                refs[staged_entity.ref] = node_id
        for staged_edge in staged_row.edges:
            resolved_edge = _staged_edge_to_resolved(staged_edge)
            await _write_edge(
                resolved_edge,
                refs,
                row_index=staged_row.row_index,
                duplicate_row_indices=staged_row.duplicate_row_indices,
                now=now,
                state=state,
                events=events,
            )

    report = LoadReport(
        load_id=load_id,
        recipe_id=recipe.id,
        recipe_version=recipe.version,
        rows_read=rows_read,
        rows_deduplicated=rows_deduplicated,
        nodes_created=state.nodes_created,
        nodes_referenced=state.nodes_referenced,
        edges_created=state.edges_written,
        rejections=rejections,
        created_node_ids=state.created_node_ids,
        touched_edge_ids=state.touched_edge_ids,
    )
    return report, events
