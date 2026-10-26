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

import json
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from ulid import ULID

from conduit_common.identity import new_edge_id, new_node_id
from knowledge_adapters import ARITY
from knowledge_adapters.datetime_adapter import DatetimeResult
from knowledge_adapters.errors import NormalisationError
from ontology.errors import HandlingSchemeError, OntologyError
from ontology.handling import HandlingScheme, audience_of, merge_handling
from ontology.validation import validate_edge_endpoints, validate_properties
from ports.graph import GraphPort
from ports.media import MediaStore
from schemas.analytics import EventRecord
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeId,
    EdgeTypeDef,
    EdgeWrite,
    EntityTypeDef,
    Handling,
    Interval,
    Node,
    NodeId,
    NodeWrite,
    OntologySchema,
    Principal,
    PropertyType,
    Provenance,
    ProvenanceState,
    ResolutionState,
    SourceRef,
    TxId,
)
from schemas.ingest import (
    HANDLING_BINDABLE,
    DeduplicateConfig,
    FieldBinding,
    LoadReport,
    Recipe,
    RecipeCondition,
    RecipeEdge,
    RecipeEntity,
    RejectionRecord,
)
from schemas.merge import aggregate_edge_writes, edge_write_key, merge_interval

from .pipeline import recipe_packs
from .recipe_rules import (
    RecipeRuleError,
    check_recipe_rules,
    deduplicate_list_problems,
    handling_bindings,
    holds_content,
    literal_handling,
    template_elements,
)
from .staging import ObjectStorageConfig, StagedEdge, StagedEntity, StagedRow
from .staging import read_staged_rows as _read_staged_rows
from .staging import stage_raw_rows as _stage_raw_rows
from .staging import stage_rows as _stage_rows
from .transforms import apply_transform, connector_params_in_use


class RowRejected(Exception):
    """Raised while resolving one row — caught per row by `run_recipe`, so
    one bad row never stops the load and never leaves a partial write.

    **The reason names the cause, never the value** (9 October 2026). The report groups by reason
    (`09_INGEST_STUDIO.md` §5, "grouped by cause"), so a value in it made each bad value its own
    group; and a reason is shown to a principal the row's sample is masked from, so a value in it
    was a value the mask did not cover. The rejected value is in the row's sample."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class StaleRecipeError(Exception):
    """Raised when a recipe's `ontology_version` no longer matches the
    active ontology, or when a pack it names or writes is unpinned, absent from the ontology or
    pinned at another version than the one the ontology carries (`check_recipe_pins`, ADR-120 D10
    and Amendment 1) — `09_INGEST_STUDIO.md`: "An ontology change that
    invalidates a recipe flags it and blocks scheduled runs until someone
    opens it. Recipes never silently adapt." Whether *this particular*
    change actually invalidates the recipe is not evaluated — any version
    mismatch blocks, which is what makes the guard trustworthy rather than
    a judgement call re-litigated on every run."""


def check_recipe_pins(recipe: Recipe, ontology: OntologySchema) -> None:
    """Refuse a recipe whose pinned pack versions are not the ones the ontology carries
    (`06_DECISIONS.md` ADR-120 D10, Amendment 1). The packs checked are those the recipe names and
    those whose types its row template writes, read from the ontology it is handed; any other pin
    a hand-written recipe carries is ignored. Called by `run_recipe` only: a draft's dry run,
    Verify and Map are never pin-checked, since a draft is not yet pinned."""
    packs = recipe_packs(recipe.pipeline, recipe.row_template, ontology)
    if packs and recipe.pack_versions is None:
        raise StaleRecipeError(
            f"recipe {recipe.id!r} names or writes the pack(s) {', '.join(packs)} but is not "
            "pinned to any pack version — open and republish the recipe before running it again"
        )
    pins = recipe.pack_versions or {}
    for pack in packs:
        if pack not in ontology.packs:
            raise StaleRecipeError(
                f"recipe {recipe.id!r} needs the pack {pack!r}, which the active ontology does "
                "not carry — open and republish the recipe before running it again"
            )
        if pins.get(pack) != ontology.packs[pack]:
            raise StaleRecipeError(
                f"recipe {recipe.id!r} pins pack {pack!r} at version {pins.get(pack)}, but the "
                f"active ontology carries version {ontology.packs[pack]} — open and republish "
                "the recipe before running it again"
            )


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
    parts: list[str | None] = []
    for binding in key_bindings:
        try:
            value = _resolve_binding(binding, row, connector_defaults=connector_defaults)
        except RowRejected:
            return None
        if isinstance(value, DatetimeResult):
            value = value.utc.replace(microsecond=0).isoformat()
        parts.append(None if value is None else str(value))
    return encode_key_parts(parts)


def encode_key_parts(parts: Sequence[str | None]) -> str | None:
    """The key of a row from its canonicalised parts (ADR-127 decision 5): the hash of a JSON list
    of the parts, in the order the definition names them, with fixed separators and no ASCII
    escaping. A separator join made `("a|b", "c")` and `("a", "b|c")` one key, and an absent part
    the text `"None"`; a JSON list is unambiguous for any text. A row with an absent or empty part
    has **no key** (`None`): it loads every time and keeps none, as a part that does not resolve
    does. Only a part with nothing in it is empty: a space is a part."""
    if any(part is None or part == "" for part in parts):
        return None
    encoded = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def dedup_fingerprint(
    config: DeduplicateConfig, connector_defaults: Mapping[str, str | None] | None = None
) -> str:
    """A hash of what makes a key a key: the definition's bindings, in order, each with its fields,
    transform and map and nothing it leaves unset, **and the connector settings that feed its
    canonicalisation** (`connector_defaults`: the connector's `date_order` and `source_crs`, as
    `dedup_key` receives them). A binding records only the settings its own transform takes and
    does not name itself, so a CRS never changes a date key; one with no transform records none.
    Kept with every row key, so a run whose definition differs from the one that made the case's
    kept keys is refused (a new version, or a connector changed under it, must not apply itself to
    rows already loaded), while a new version that left both as they were has the same fingerprint
    and still skips."""
    defaults = connector_defaults or {}
    normalised: list[dict[str, object]] = []
    for binding in config.key:
        entry: dict[str, object] = dict(binding.model_dump(exclude_none=True))
        if binding.transform is not None:
            used = {
                param: defaults.get(param)
                for param in connector_params_in_use(binding.transform)
                if defaults.get(param) is not None
            }
            if used:
                entry["connector"] = used
        normalised.append(entry)
    encoded = json.dumps(normalised, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


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
                f"transform {binding.transform!r} takes {arity} field(s), got {len(binding.fields)}"
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
            raise RowRejected(_cause(exc, binding.fields)) from exc
    if binding.field is None:
        raise RowRejected("binding declares neither `field`, `fields` nor `literal`")
    field_value = row.get(binding.field)
    if field_value is None or field_value == "":
        raise RowRejected(f"required field {binding.field!r} is missing")
    if binding.map is not None:
        if field_value not in binding.map:
            raise RowRejected(f"a value of field {binding.field!r} is not in the declared map")
        return binding.map[field_value]
    if binding.transform is not None:
        try:
            return apply_transform(
                binding.transform, field_value, connector_defaults=connector_defaults
            )
        except NormalisationError as exc:
            raise RowRejected(_cause(exc, [binding.field])) from exc
    return field_value


def _cause(exc: NormalisationError, fields: Sequence[str]) -> str:
    """A normalisation failure as a cause: the adapter, the field(s) and why, not the value."""
    named = ", ".join(repr(name) for name in fields)
    noun = "field" if len(fields) == 1 else "fields"
    return f"{exc.adapter}: cannot normalise {noun} {named} — {exc.reason}"


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


def _coerced_properties(
    entity: RecipeEntity,
    properties: dict[str, Any],
    ontology: OntologySchema,
    own_text: str | None = None,
) -> dict[str, Any]:
    """An entity's resolved properties as `_write_entity` matches and writes them: an own-text
    Document's `title` defaulted to the text's first words (a bound `title` wins), then the
    declared numeric types coerced. One function, so what a write matches on and what a check
    predicts it will match on cannot drift apart."""
    base = properties
    if own_text is not None:
        base = {"title": _first_words(own_text), **base}
    return _coerce_declared_numeric_types(base, ontology.entity_type(entity.type))


def _match_key(entity: RecipeEntity, coerced: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """The identity an `on_match: reference` entity is looked up by: its type, the field it
    matches on and that field's coerced value; `None` for an entity that is not matched."""
    if entity.on_match != "reference" or not entity.match_on:
        return None
    return (entity.type, entity.match_on, str(coerced.get(entity.match_on)))


def _resolve_properties(
    bindings: Mapping[str, FieldBinding],
    row: Mapping[str, str],
    *,
    connector_defaults: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for name, binding in bindings.items():
        if binding.optional and _binding_cells_empty(binding, row):
            continue  # ADR-127 Amendment 15: an empty cell leaves the property out
        value = _resolve_binding(binding, row, connector_defaults=connector_defaults)
        if binding.optional and isinstance(value, list) and not value:
            continue  # a cell of only separators: nothing was said, so nothing is written
        resolved[name] = value
    return resolved


def _binding_cells_empty(binding: FieldBinding, row: Mapping[str, str]) -> bool:
    """Whether every cell a binding reads is empty, which an `optional` binding leaves out: a blank
    cell counts as empty. A literal reads no cell. A set of columns with only some blank is not
    empty: it goes to the adapter, which refuses it (a place with half a position says so)."""
    if binding.literal is not None:
        return False
    names = binding.fields if binding.fields is not None else [binding.field]
    cells = [name for name in names if name is not None]
    return bool(cells) and all(not (row.get(name) or "").strip() for name in cells)


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
    raise RowRejected("temporal binding did not resolve to a datetime")


def _binding_columns(binding: FieldBinding) -> str:
    """The source column(s) a binding reads, for a message that names columns and never values."""
    if binding.field:
        return binding.field
    if binding.fields:
        return ", ".join(binding.fields)
    return "its time"


def _resolve_span_end(
    binding: FieldBinding,
    row: Mapping[str, str],
    *,
    connector_defaults: Mapping[str, str | None] | None = None,
) -> datetime | None:
    """The end of a span (ADR-127 decision 11), read as the start is (the connector's date order
    and the zone): `None` for an empty cell, which is a span still open. Any other cell that does
    not read as a time rejects the row, naming the column."""
    if binding.field is not None and not (row.get(binding.field) or "").strip():
        return None
    try:
        return _resolve_temporal_instant(binding, row, connector_defaults=connector_defaults)
    except RowRejected as exc:
        raise RowRejected(
            f"the end of the span ({_binding_columns(binding)}) did not resolve to a time"
        ) from exc


def edge_interval(
    instant: datetime | None, valid_to: datetime | None, span: bool
) -> Interval | None:
    """A link's `Interval` from what its row resolved to: none for a link with no time; the start
    and the end for a closed span; the start alone for a span still open (`valid_to=None`, never
    the start repeated); and the instant for both ends of a link bound to one time."""
    if instant is None:
        return None
    if span:
        return Interval(valid_from=instant, valid_to=valid_to)
    return Interval(valid_from=instant, valid_to=instant)


def _merge_override(
    defaults: Mapping[str, Any], override: Mapping[str, Any] | None
) -> dict[str, Any]:
    """A per-element `handling`/`provenance` override (`RecipeEntity.handling`/
    `.provenance`, `RecipeEdge.handling`/`.provenance` —
    `09_INGEST_STUDIO.md` §4) merged over the recipe's own defaults, override
    winning per-key. Shallow: a `Handling`/`Provenance` field is a scalar or
    a list assigned wholesale (e.g. `provenance.sources`), never a nested
    dict itself, so a key-level merge is the whole merge."""
    merged = dict(defaults)
    if override:
        merged.update(override)
    return merged


def _handling(defaults: Mapping[str, Any]) -> Handling:
    raw = dict(defaults)
    originator = raw.get("originator")
    if originator is None:
        raise RowRejected("recipe defaults.handling has no `originator`")
    raw.setdefault("owning_unit", originator)
    raw.setdefault("handling_code", "P")
    return Handling.model_validate(raw)


def recipe_binds_handling(recipe: Recipe) -> bool:
    return any(handling_bindings(e.handling) for e in template_elements(recipe.row_template))


def _require_scheme_to_judge_bound_handling(recipe: Recipe, scheme: HandlingScheme | None) -> None:
    """A recipe that binds a marking to a column is judged against the handling scheme row by row;
    a run given none refuses, rather than loading rows nothing could check (fail closed)."""
    if scheme is None and recipe_binds_handling(recipe):
        raise RecipeRuleError(
            [
                "This recipe binds a marking to a column, which is judged against the handling "
                "scheme, and this run has no handling scheme (ADR-127 decision 3)."
            ]
        )


_PART_LABELS = {
    "classification": "classification",
    "handling_code": "handling code",
    "action_code": "action code",
    "sanitisation_code": "sanitisation code",
    "originator": "originator",
    "owning_unit": "owning unit",
}


def _defined_values(scheme: HandlingScheme, part: str) -> list[str]:
    return {
        "classification": list(scheme.classification),
        "handling_code": list(scheme.handling_codes),
        "action_code": list(scheme.action_codes),
        "sanitisation_code": list(scheme.sanitisation_codes),
    }.get(part, [])


def row_handling_override(
    recipe: Recipe,
    override: dict[str, Any] | None,
    row: Mapping[str, str],
    *,
    scheme: HandlingScheme | None,
) -> dict[str, Any] | None:
    """The element's `handling` for one row, with each bound part read from its column (ADR-127
    decision 3). No bound part: `override` as it is. Otherwise a plain override (literals and the
    cells' values), or `RowRejected` with the cause:

    - a bound column the row does not have (the source has no such column);
    - an empty cell takes the element's default for that part (none, for the action and
      sanitisation codes, unless the default has one): it is left out of the override;
    - a code the scheme does not define;
    - an `originator` or `owning_unit` the recipe does not declare in `defaults.units`;
    - a part looser than the element's default, by `merge_handling`'s order: the cell may only
      tighten the marking (ADR-102 decision 1), in every part, not classification alone."""
    bindings = handling_bindings(override)
    if not bindings:
        return override
    if scheme is None:
        raise RowRejected("this run has no handling scheme to judge a bound marking against")
    literal = literal_handling(override) or {}
    base = _merge_override(recipe.defaults.handling, literal)
    try:
        default = _handling(base)
        # The scheme refuses a default it does not define, as it does a cell's.
        merge_handling(default, default, scheme)
    except HandlingSchemeError as exc:
        raise RowRejected(f"the element's default marking is not valid: {exc}") from exc
    values: dict[str, str] = {}
    for part, column in bindings.items():
        label = _PART_LABELS[part]
        if column not in row:
            raise RowRejected(
                f"{label} is bound to column {column!r}, which this source does not have"
            )
        cell = (row[column] or "").strip()
        if not cell:
            continue
        # A reason names the part and the column, never the cell: a rejection is read by people who
        # may not be cleared for what the cell says (rule 3).
        if part in ("originator", "owning_unit"):
            if cell not in recipe.defaults.units:
                raise RowRejected(
                    f"column {column!r} gives a {label} the recipe does not declare "
                    f"(declared: {', '.join(recipe.defaults.units) or 'none'})"
                )
        elif cell not in _defined_values(scheme, part):
            raise RowRejected(
                f"column {column!r} gives a {label} the handling scheme {scheme.name!r} "
                "does not define"
            )
        values[part] = cell
    bound = _handling({**base, **values})
    merged = merge_handling(bound, default, scheme)
    if merged != bound:
        for part in ("classification", "handling_code", "action_code", "sanitisation_code"):
            if getattr(merged, part) != getattr(bound, part):
                raise RowRejected(
                    f"column {bindings[part]!r} gives a {_PART_LABELS[part]} looser than the "
                    "element's default; a column may only tighten a marking"
                )
    return {**literal, **values}


def _fold_group_handling(
    recipe: Recipe,
    resolved: Sequence[_ResolvedEntity | _ResolvedEdge],
    duplicates: Sequence[Mapping[str, str]],
    *,
    scheme: HandlingScheme | None,
) -> None:
    """The survivor of a duplicate group stands for every member (`01_DOMAIN_MODEL.md` §7), so its
    bound marking is no lower than any member's: each member's is resolved as the survivor's was
    and folded in with `merge_handling`, and a member that fails (an undefined code, an undeclared
    unit, a loosening) rejects the whole group with its cause. A restricted code that the members
    give different units cannot be held by one marking, and rejects it too."""
    for item in resolved:
        element = item.entity if isinstance(item, _ResolvedEntity) else item.edge
        if item.properties is None or not handling_bindings(element.handling):
            continue
        assert scheme is not None  # the survivor's own resolution refused otherwise
        merged = _handling(_merge_override(recipe.defaults.handling, item.handling))
        for member in duplicates:
            if not _condition_holds(element.when, member):
                continue
            override = row_handling_override(recipe, element.handling, member, scheme=scheme)
            other = _handling(_merge_override(recipe.defaults.handling, override))
            first = merged
            merged = merge_handling(merged, other, scheme)
            dissemination = scheme.handling_codes[merged.handling_code].dissemination
            if dissemination == "restricted" and (first.owning_unit, first.originator) != (
                other.owning_unit,
                other.originator,
            ):
                raise RowRejected(
                    "duplicate rows name different units under a restricted handling code, "
                    "which one marking cannot hold"
                )
        parts = {
            name: getattr(merged, name)
            for name in HANDLING_BINDABLE
            if getattr(merged, name) is not None
        }
        item.handling = {**(literal_handling(element.handling) or {}), **parts}


def _refuse_unit_conflict(markings: Sequence[Handling], scheme: HandlingScheme) -> None:
    """One `Handling` holds one unit (ADR-102 decision 2). A row whose elements are marked
    restricted for different units has no single marking that is safe, so it is refused (ADR-127
    Amendment 2) rather than held at one element's unit."""
    restricted = any(
        scheme.handling_codes[h.handling_code].dissemination == "restricted" for h in markings
    )
    if restricted and len({(h.owning_unit, h.originator) for h in markings}) > 1:
        raise RowRejected(
            "its elements' markings name different units under a restricted handling code and "
            "cannot be held as one marking"
        )


def row_marking(recipe: Recipe, row: Mapping[str, str], scheme: HandlingScheme) -> Handling:
    """One marking for a whole source row, for a record that holds the row itself (a held row,
    ADR-109): no lower than any element's marking *this row* resolves to, the strictest taken
    first. A part that does not resolve gives that element's every possible marking
    (`recipe_handlings`' own floor), so a row that would have been rejected is held no lower than
    it could have been. A row whose elements are restricted for different units has no one safe
    marking: `RowRejected`, with its cause."""
    markings: list[Handling] = []
    for element in template_elements(recipe.row_template):
        if not _condition_holds(element.when, row):
            continue
        base = _merge_override(recipe.defaults.handling, literal_handling(element.handling))
        bindings = handling_bindings(element.handling)
        if not bindings:
            markings.append(_handling(base))
            continue
        try:
            override = row_handling_override(recipe, element.handling, row, scheme=scheme)
            markings.append(_handling(_merge_override(recipe.defaults.handling, override)))
        except RowRejected:
            markings.extend(_possible_markings(base, bindings, scheme, recipe.defaults.units))
    markings = markings or [_handling(recipe.defaults.handling)]
    _refuse_unit_conflict(markings, scheme)
    markings.sort(
        key=lambda h: (
            scheme.handling_codes[h.handling_code].dissemination == "restricted",
            scheme.classification.index(h.classification),
        ),
        reverse=True,
    )
    marking = markings[0]
    for other in markings[1:]:
        marking = merge_handling(marking, other, scheme)
    return marking


def _possible_markings(
    base: Mapping[str, Any],
    bindings: Mapping[str, str],
    scheme: HandlingScheme,
    units: Sequence[str],
) -> list[Handling]:
    """Every marking one bound part could give an element: the part set to each value the scheme
    defines (each declared unit, for a unit), the rest as `base`. The strictest of them is what a
    row not yet read could be marked, for a marking that may not be lower than any referent's."""
    found: list[Handling] = []
    for part in bindings:
        values = (
            list(units) if part in ("originator", "owning_unit") else _defined_values(scheme, part)
        )
        found.extend(_handling({**base, part: value}) for value in values)
    return found


def _row_override(resolved: Any, element: RecipeEntity | RecipeEdge) -> dict[str, Any] | None:
    """The `handling` override a write uses: this row's, with its columns read, else the element's
    own with any column binding left out (`_resolve_row` reads every binding, so none is left)."""
    return (
        resolved.handling if resolved.handling is not None else literal_handling(element.handling)
    )


def recipe_handlings(recipe: Recipe, scheme: HandlingScheme | None = None) -> list[Handling]:
    """Every marking this recipe can write: its defaults, and each entity's and link's override
    over them — what a row it has not yet written could carry (ADR-109: a held row's marking, and
    the stand-in for a node written in a still-open transaction). An element with a part bound to
    a column adds, given the `scheme`, every marking that part could take (ADR-127 decision 3), so
    a marking built from these is no lower than a row's. Without a scheme a bound part is left at
    its default: no caller that judges rows has none."""
    defaults = recipe.defaults.handling
    markings = [_handling(defaults)]
    for element in template_elements(recipe.row_template):
        if not element.handling:
            continue
        base = _merge_override(defaults, literal_handling(element.handling))
        markings.append(_handling(base))
        bindings = handling_bindings(element.handling)
        if bindings and scheme is not None:
            markings.extend(_possible_markings(base, bindings, scheme, recipe.defaults.units))
    return markings


def _provenance(
    defaults: Mapping[str, Any], *, source: str, row_index: int, now: datetime
) -> Provenance:
    state = defaults.get("state", "asserted")
    return Provenance(
        state=ProvenanceState(state),
        sources=[SourceRef(document_id=source, locator=f"row {row_index}", excerpt_hash="")],
        first_seen=now,
    )


def preview_handling_and_provenance(
    recipe: Recipe,
    *,
    source: str,
    row_index: int,
    now: datetime,
    handling_override: Mapping[str, Any] | None = None,
    provenance_override: Mapping[str, Any] | None = None,
) -> tuple[Handling, Provenance]:
    """What `_write_entity`/`_write_edge` would attach to a written element,
    computed the same way they do (`_handling`/`_provenance` above) but
    callable with no open transaction, no `GraphPort`, and no `_RunState` —
    `09_INGEST_STUDIO.md` §4/§5: the Map and Verify stages' shared preview
    path, so a dry run's rendered graph and a real load agree on what an
    element's handling and provenance would be, computed by one shared
    function rather than reimplemented per caller. `handling_override`/
    `provenance_override` are an element's own `RecipeEntity`/`RecipeEdge`
    `handling`/`provenance` — merged over `recipe.defaults` via
    `_merge_override` before validating, the same merge `_write_entity`/
    `_write_edge` apply for a real write."""
    return (
        _handling(_merge_override(recipe.defaults.handling, literal_handling(handling_override))),
        _provenance(
            _merge_override(recipe.defaults.provenance, provenance_override),
            source=source,
            row_index=row_index,
            now=now,
        ),
    )


#: ADR-127 Amendment 19: how many links one `upsert_edges` call carries when a run flushes the links
#: it combined. The chunking bounds one call, not the run: every chunk is in the run's one
#: transaction.
FLUSH_CHUNK = 500

#: Test-only (ADR-127 Amendment 19, "the per-row reference is the same code with a flush size of
#: one"). A test sets this to 1 to make a run with a handling scheme flush each write as it is held,
#: which is what a run without a scheme does. Never set outside a test.
_FORCE_FLUSH_SIZE: int | None = None


@dataclass
class _HeldLink:
    """One link the run has combined and not yet written (ADR-127 Amendment 19): the combined
    write, and whatever must be told the stored id once the flush has it."""

    write: EdgeWrite
    #: Whether the loader's count of created links waits on their being able to read it
    #: (`_count_hidden_merges`): a plain link does, a `HOLDS` link is counted at its write.
    counted_by_readability: bool
    #: A `HOLDS` link only: whether its holder was created by this load when it was held, which
    #: makes the link the load's own whatever the store returns (see `_write_held_content`).
    holder_created: bool | None = None
    #: The slots of `_RunState.written` holding one row's write of this link, whose id is the
    #: stored one once flushed.
    written_slots: list[int] = field(default_factory=list)
    #: The events of the rows that wrote this link, whose `edge_id` is the stored id once flushed.
    events: list[EventRecord] = field(default_factory=list)


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
    #: The handling scheme the graph adapter judges audiences with. `None` (the CLI, the site grid,
    #: the seeders, the basemap builder) means the run does not combine: it flushes each write as it
    #: is held, because without a scheme a restricted code's units cannot be told apart.
    scheme: HandlingScheme | None = None
    #: ADR-127 Amendment 19: the links held and not yet written, by `edge_write_key`, in the order
    #: each was first held.
    held_links: dict[tuple[Hashable, ...], _HeldLink] = field(default_factory=dict)
    #: Each node this run wrote or matched, by its type, so a held write is checked as the adapter
    #: checks it (its ends allow the type) without a store read.
    node_types: dict[NodeId, str] = field(default_factory=dict)
    touched_edge_lookup: set[EdgeId] = field(default_factory=set)
    created_node_ids: list[NodeId] = field(default_factory=list)
    touched_edge_ids: list[EdgeId] = field(default_factory=list)
    #: ADR-127 decision 6: `touched_edge_ids` told apart. A link is created when the store kept the
    #: id the load sent, merged when it returned another's; a second write to a link this load
    #: created is neither a new link nor a merge into another load's.
    created_edge_ids: list[EdgeId] = field(default_factory=list)
    merged_edge_ids: list[EdgeId] = field(default_factory=list)
    #: Of `merged_edge_ids`, the links `_write_edge` merged into. The count told to the loader
    #: depends on whether they may read each (`_count_hidden_merges`); a `HOLDS` link is always
    #: counted at its write and is not among them.
    merged_link_ids: list[EdgeId] = field(default_factory=list)
    merged_node_ids: list[NodeId] = field(default_factory=list)
    #: ADR-127 decision 7(a): the existing nodes matched by reference, each once, never one this
    #: load created (`LoadReport.referenced_node_ids`).
    referenced_node_ids: list[NodeId] = field(default_factory=list)
    referenced_node_lookup: set[NodeId] = field(default_factory=set)
    created_node_lookup: set[NodeId] = field(default_factory=set)
    created_edge_lookup: set[EdgeId] = field(default_factory=set)
    merged_edge_lookup: set[EdgeId] = field(default_factory=set)
    nodes_created: int = 0
    nodes_referenced: int = 0
    edges_created: int = 0
    #: Within-load cache so the same value referenced by two rows in one
    #: load resolves to one node without depending on read-your-own-write
    #: visibility from a query issued inside the same open transaction.
    local_index: dict[tuple[str, str, str], NodeId] = field(default_factory=dict)
    #: ADR-094: a row whose entity was loaded but whose file was not found; said in the report.
    content_rejections: list[RejectionRecord] = field(default_factory=list)
    #: Documents already written this load, so one file held twice is written once.
    documents_written: set[NodeId] = field(default_factory=set)
    #: ADR-109 phase F: every node this load created and every link it wrote, as written, for a
    #: caller that judges them before the commit (a pre-commit KYC rule cannot read the open
    #: transaction back). `None` when no caller asked.
    written: list[NodeWrite | EdgeWrite] | None = None


class _ResolvedEntity:
    __slots__ = ("entity", "properties", "content", "handling")

    def __init__(
        self,
        entity: RecipeEntity,
        properties: dict[str, Any] | None,
        content: dict[str, str] | None = None,
        handling: dict[str, Any] | None = None,
    ) -> None:
        #: This row's `handling` override, columns read (`row_handling_override`).
        self.handling = handling
        #: ADR-094: `{"kind", "value"}` when this entity holds content this row.
        self.content = content
        self.entity = entity
        self.properties = properties  # None means the entity's `when` did not hold this row


class _ResolvedEdge:
    __slots__ = ("edge", "properties", "instant", "valid_to", "span", "content", "handling")

    def __init__(
        self,
        edge: RecipeEdge,
        properties: dict[str, Any] | None,
        instant: datetime | None,
        content: dict[str, str] | None = None,
        handling: dict[str, Any] | None = None,
        valid_to: datetime | None = None,
        span: bool = False,
    ) -> None:
        #: This row's `handling` override, columns read (`row_handling_override`).
        self.handling = handling
        self.edge = edge
        self.properties = properties  # None means the edge's `when` did not hold this row
        self.instant = instant
        #: ADR-127 decision 11: the end of a span (`None` when open), and whether one was bound.
        self.valid_to = valid_to
        self.span = span
        #: ADR-094: `{"kind", "text"}` when the recipe marks this link's text and the row has some.
        self.content = content


def _check_values(type_def: EntityTypeDef | EdgeTypeDef | None, properties: dict[str, Any]) -> None:
    """Refuses the row when a value does not fit the type the ontology declares for its property (9
    October 2026: it raised `OntologyError` from deep in the dry run or the load, so one bad row
    failed Verify). Only the values are checked here: whether a required property is there depends
    on whether the entity is created or references one already stored, which is known later. The
    reason names the property and its type, never the value, as every rejection reason does."""
    if type_def is None:
        return  # an undeclared type is the recipe's fault, refused where it is checked
    coerced = _coerce_declared_numeric_types(properties, type_def)
    for prop in type_def.properties:
        if prop.name not in coerced:
            continue
        try:
            validate_properties(
                type_def.model_copy(update={"properties": [prop], "identifiers": []}),
                {prop.name: coerced[prop.name]},
            )
        except OntologyError:
            reason = f"{type_def.name}.{prop.name} is not a valid {prop.type.value}"
            raise RowRejected(reason) from None


def _resolve_row(
    recipe: Recipe,
    row: Mapping[str, str],
    *,
    connector_defaults: Mapping[str, str | None],
    ontology: OntologySchema | None = None,
    scheme: HandlingScheme | None = None,
) -> tuple[list[_ResolvedEntity], list[_ResolvedEdge]]:
    """Phase 1: pure resolution, no I/O. Raises `RowRejected` for the whole
    row on the first failing binding anywhere in it."""
    for part, column in recipe.defaults.handling_columns.items():
        if column not in row:
            raise RowRejected(
                f"column {column!r}, declared as the {_PART_LABELS[part]} column, "
                "is not in this source"
            )
    entities = []
    for entity in recipe.row_template.entities:
        if not _condition_holds(entity.when, row):
            entities.append(_ResolvedEntity(entity, None))
            continue
        properties = _resolve_properties(
            entity.properties, row, connector_defaults=connector_defaults
        )
        if ontology is not None:
            _check_values(ontology.entity_type(entity.type), properties)
        content = _held_content(entity, row)
        if content is None and holds_own_text(entity):
            # ADR-127 amendment: a Document that holds its own text and has none this row is not
            # loaded text-less; the row is rejected, naming the column.
            assert entity.content is not None
            raise RowRejected(
                f"{entity.content.field} is empty; a Document holds its own text, so a row with "
                "none is not loaded"
            )
        handling = row_handling_override(recipe, entity.handling, row, scheme=scheme)
        entities.append(_ResolvedEntity(entity, properties, content, handling))

    edges = []
    for edge in recipe.row_template.edges:
        if not _condition_holds(edge.when, row):
            edges.append(_ResolvedEdge(edge, None, None))
            continue
        properties = _resolve_properties(
            edge.properties, row, connector_defaults=connector_defaults
        )
        if ontology is not None:
            _check_values(ontology.edge_type(edge.type), properties)
        instant = (
            _resolve_temporal_instant(edge.temporal.at, row, connector_defaults=connector_defaults)
            if edge.temporal
            else None
        )
        span = edge.temporal is not None and edge.temporal.valid_to is not None
        valid_to = (
            _resolve_span_end(
                edge.temporal.valid_to, row, connector_defaults=connector_defaults
            )
            if edge.temporal is not None and edge.temporal.valid_to is not None
            else None
        )
        if instant is not None and valid_to is not None and valid_to < instant:
            assert edge.temporal is not None and edge.temporal.valid_to is not None
            raise RowRejected(
                f"the span ends ({_binding_columns(edge.temporal.valid_to)}) before it starts "
                f"({_binding_columns(edge.temporal.at)})"
            )
        text = row.get(edge.content.field, "") if edge.content else ""
        content = (
            {"kind": edge.content.kind, "text": text} if edge.content and text.strip() else None
        )
        handling = row_handling_override(recipe, edge.handling, row, scheme=scheme)
        edges.append(
            _ResolvedEdge(edge, properties, instant, content, handling, valid_to, span)
        )

    if scheme is not None:
        present: list[Handling] = [
            _handling(_merge_override(recipe.defaults.handling, _row_override(e, e.entity)))
            for e in entities
            if e.properties is not None
        ]
        present += [
            _handling(_merge_override(recipe.defaults.handling, _row_override(e, e.edge)))
            for e in edges
            if e.properties is not None
        ]
        _refuse_unit_conflict(present or [_handling(recipe.defaults.handling)], scheme)
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
    row_key: str | None = None,
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
        row_key=row_key,
        entities=[
            StagedEntity(
                ref=e.entity.ref,
                type=e.entity.type,
                properties=e.properties,
                content=e.content,
                handling=e.handling,
            )
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
                valid_to=e.valid_to,
                span=e.span,
                content=e.content,
                handling=e.handling,
            )
            for e in resolved_edges
            if e.properties is not None
        ],
    )


class RowKeys(Protocol):
    """What a run asks of the store of loaded rows (ADR-127 decision 5): which of these row keys the
    case already kept for the recipe. `RecipeRunStore.kept_row_keys` and a `LoadSink` answer it."""

    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]: ...

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        """The definitions of `deduplicate` the case's kept keys for this recipe were made under
        (`dedup_fingerprint`), each with how many loads kept keys under it."""
        ...


class RowKeyDefinitionChanged(Exception):
    """A run's `deduplicate` is not the one the case's kept keys were made under (ADR-127 decision
    5: a new version must not apply itself to rows already loaded). A key made by another
    definition says nothing of this one's rows, so the run is refused before anything is written;
    the keys go when the loads that kept them are reverted. `loads` is how many to revert, a count
    and never an id: this message is routed."""

    def __init__(self, loads: int) -> None:
        super().__init__(
            "this recipe's `deduplicate` has changed since rows were loaded into this case: "
            f"revert the {loads} load(s) that kept keys under the earlier definition, then run it "
            "again"
        )
        self.loads = loads


class RowKeyRunInProgress(Exception):
    """Another run of this recipe into this case holds the lock that serialises them (ADR-127
    decision 5) and did not finish within the short wait. Refused before anything is written:
    run it again once the other has finished, when its rows are kept and this run skips them."""

    def __init__(self, recipe_id: str) -> None:
        super().__init__(
            "another run of this recipe into this case is in progress; run it again when it "
            "has finished"
        )
        self.recipe_id = recipe_id


@dataclass
class Resolved:
    """`resolve_rows`'s answer with what decision 5 adds: the rows a case had already loaded."""

    staged_rows: list[StagedRow]
    rejections: list[RejectionRecord]
    rows_read: int
    rows_deduplicated: int
    rows_already_loaded: int = 0


def row_group_keys(recipe: Recipe, rows: Sequence[Mapping[str, str]]) -> list[str | None]:
    """Each row's deduplication key, by `dedup_key` (canonicalised, then hashed: the one
    canonicalisation `01_DOMAIN_MODEL.md` §7 rule 2 describes), or `None` for a row whose key
    fields did not resolve, and for every row of a recipe with no `deduplicate`."""
    if recipe.deduplicate is None:
        return [None] * len(rows)
    defaults = connector_key_defaults(recipe)
    return [dedup_key(row, recipe.deduplicate.key, connector_defaults=defaults) for row in rows]


def connector_key_defaults(recipe: Recipe) -> Mapping[str, str | None]:
    """The connector settings that reach a key part's transform: what `dedup_key` resolves with and
    what `dedup_fingerprint` records."""
    return {
        "date_order": recipe.connector.date_order,
        "source_crs": recipe.connector.source_crs,
    }


def recipe_fingerprint(recipe: Recipe) -> str | None:
    """The fingerprint of the recipe's `deduplicate` under its own connector, or `None` without."""
    if recipe.deduplicate is None:
        return None
    return dedup_fingerprint(recipe.deduplicate, connector_key_defaults(recipe))


async def kept_among(
    recipe: Recipe,
    rows: Sequence[Mapping[str, str]],
    row_keys: RowKeys | None,
    case: str | None,
) -> frozenset[str]:
    """The keys among `rows` that `case` has already kept for `recipe`: asked of the store, and only
    when the recipe has `deduplicate`. No store or no case is nothing kept (a run outside a case
    keeps no keys and skips no row). Keys the case kept under another definition of `deduplicate`
    (or the same one under other connector settings) refuse the run (`RowKeyDefinitionChanged`),
    **a recipe with no `deduplicate` included**: removing it would reload every row the case
    holds, so it is asked too, and refused while any key is kept for (recipe, case)."""
    if row_keys is None or case is None:
        return frozenset()
    if recipe.deduplicate is None:
        held = await row_keys.fingerprints(recipe.id, case)
        if held:
            raise RowKeyDefinitionChanged(sum(held.values()))
        return frozenset()
    mine = dedup_fingerprint(recipe.deduplicate, connector_key_defaults(recipe))
    others = {
        fingerprint: loads
        for fingerprint, loads in (await row_keys.fingerprints(recipe.id, case)).items()
        if fingerprint != mine
    }
    if others:
        raise RowKeyDefinitionChanged(sum(others.values()))
    keys = sorted({k for k in row_group_keys(recipe, rows) if k is not None})
    return frozenset(await row_keys.kept(recipe.id, case, keys)) if keys else frozenset()


def resolve_rows(
    recipe: Recipe,
    rows: Iterable[Mapping[str, str]],
    *,
    load_id: str,
    source: str,
    ontology: OntologySchema | None = None,
    row_numbers: Sequence[int] | None = None,
    scheme: HandlingScheme | None = None,
) -> tuple[list[StagedRow], list[RejectionRecord], int, int]:
    """`resolve_rows_keyed` with no rows already loaded, as its callers had it before decision 5:
    `(staged_rows, rejections, rows_read, rows_deduplicated)`."""
    done = resolve_rows_keyed(
        recipe,
        rows,
        load_id=load_id,
        source=source,
        ontology=ontology,
        row_numbers=row_numbers,
        scheme=scheme,
    )
    return done.staged_rows, done.rejections, done.rows_read, done.rows_deduplicated


def resolve_rows_keyed(
    recipe: Recipe,
    rows: Iterable[Mapping[str, str]],
    *,
    load_id: str,
    source: str,
    ontology: OntologySchema | None = None,
    row_numbers: Sequence[int] | None = None,
    scheme: HandlingScheme | None = None,
    already_loaded: frozenset[str] = frozenset(),
) -> Resolved:
    """Phase 1 of `run_recipe`, extracted so staging sits between
    resolution and load rather than being folded invisibly into one
    function. Returns `(staged_rows, rejections, rows_read,
    rows_deduplicated)` — pure, no I/O of any kind, including no object
    storage: `run_recipe` is the only caller that writes anything.

    `row_numbers`, when given, is each row's number in the source it was first read from — a held
    row released later (ADR-109 ruling 1) keeps the provenance locator it would have had.

    `already_loaded` (ADR-127 decision 5): the keys the case has kept for the recipe. A group of
    rows with such a key is left out whole, whatever the recipe's version, and each of its rows is
    counted in `rows_already_loaded`; `rows_deduplicated` then counts only the duplicates folded
    among the groups that are loaded. Each staged row carries its group's key, for the case to keep
    once the row has loaded."""
    connector_defaults = connector_key_defaults(recipe)
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
    skipped = [key for key in group_order if key in already_loaded]
    rows_already_loaded = sum(len(groups[key]) for key in skipped)
    group_order = [key for key in group_order if key not in already_loaded]
    rows_deduplicated = (rows_read - rows_already_loaded) - len(group_order)

    def number(position: int) -> int:
        return row_numbers[position] if row_numbers is not None else position

    staged_rows: list[StagedRow] = []
    rejections: list[RejectionRecord] = []
    for key in group_order:
        position, *duplicate_positions = groups[key]
        row = materialized_rows[position]
        row_index = number(position)
        duplicate_row_indices = [number(p) for p in duplicate_positions]
        try:
            resolved_entities, resolved_edges = _resolve_row(
                recipe, row, connector_defaults=connector_defaults, ontology=ontology, scheme=scheme
            )
            if duplicate_positions:
                _fold_group_handling(
                    recipe,
                    [*resolved_entities, *resolved_edges],
                    [materialized_rows[p] for p in duplicate_positions],
                    scheme=scheme,
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
                row_key=None if key.startswith("__unkeyed_") else key,
            )
        )

    return Resolved(staged_rows, rejections, rows_read, rows_deduplicated, rows_already_loaded)


def _note_referenced(state: _RunState, node_id: NodeId) -> None:
    """Remember a node matched by reference, once, unless this load created it (a node written by an
    earlier row and found again by a later one is this load's own, not one it merely touched)."""
    if node_id in state.created_node_lookup or node_id in state.referenced_node_lookup:
        return
    state.referenced_node_lookup.add(node_id)
    state.referenced_node_ids.append(node_id)


async def _write_entity(
    resolved: _ResolvedEntity,
    *,
    row_index: int,
    now: datetime,
    state: _RunState,
    own_text_media: MediaStore | None = None,
) -> NodeId | None:
    """`own_text_media`: the media store, for a `Document` that holds its own text (ADR-127
    decision 1). Its text is put there, and `object_ref` and `media_kind: text` written onto the
    Document, only when a node is about to be written: a Document matched by reference is not
    rewritten by the row (it keeps the `object_ref` it has) and no object is stored for it. The
    title is a bound `title` if there is one, else the text's first words; it is settled before the
    match, so a recipe may match on it."""
    if resolved.properties is None:
        return None
    entity = resolved.entity
    own_text = (
        resolved.content["value"]
        if own_text_media is not None and resolved.content is not None
        else None
    )
    properties = _coerced_properties(entity, resolved.properties, state.ontology, own_text)
    match_key = _match_key(entity, properties)
    handling = _handling(
        _merge_override(state.recipe.defaults.handling, _row_override(resolved, entity))
    )
    provenance = _provenance(
        _merge_override(state.recipe.defaults.provenance, entity.provenance),
        source=state.source,
        row_index=row_index,
        now=now,
    )

    if match_key is not None:
        cached = state.local_index.get(match_key)
        if cached is not None:
            state.nodes_referenced += 1
            _note_referenced(state, cached)
            state.node_types[cached] = entity.type
            return cached
        existing = await state.graph.find_node(
            entity.type, match_key[1], match_key[2], state.principal
        )
        if existing is not None:
            state.local_index[match_key] = existing.id
            state.nodes_referenced += 1
            _note_referenced(state, existing.id)
            state.node_types[existing.id] = entity.type
            return existing.id

    if own_text is not None and own_text_media is not None:
        ref = await own_text_media.put(own_text.encode("utf-8"), "text/plain")
        properties = {**properties, "object_ref": ref, "media_kind": _MEDIA_KIND["document_text"]}

    write = NodeWrite(
        id=new_node_id(),
        type=entity.type,
        properties=properties,
        provenance=provenance,
        handling=handling,
        created_by=state.principal.id,
        created_at=now,
        load_id=state.load_id,
        recipe_id=state.recipe.id,
        recipe_version=state.recipe.version,
    )
    (node_id,) = await state.graph.upsert_nodes([write], state.tx)
    state.created_node_ids.append(node_id)
    state.created_node_lookup.add(node_id)
    state.node_types[node_id] = entity.type
    state.nodes_created += 1
    if state.written is not None:
        state.written.append(write.model_copy(update={"id": node_id}))
    if match_key is not None:
        state.local_index[match_key] = node_id
    return node_id


#: The file extensions each content kind accepts, and the content type each is kept under.
_FILE_TYPES = {
    "image_file": {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
        "heic": "image/heic",
    },
    "video_file": {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"},
}
_MEDIA_KIND = {"document_text": "text", "image_file": "image", "video_file": "video"}


def _held_content(entity: RecipeEntity, row: Mapping[str, str]) -> dict[str, str] | None:
    """Pure checks on the content an entity holds this row (ADR-094); the file itself is read when
    it is written. Rejects the row for a path outside the export's folder or of the wrong kind."""
    if entity.content is None:
        return None
    value = (row.get(entity.content.field) or "").strip()
    if not value:
        return None
    kind = entity.content.kind
    if kind in _FILE_TYPES:
        path = PurePosixPath(value.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise RowRejected(
                f"{entity.content.field} {value!r} is outside the export's own folder; a file "
                "is named by a path below the folder the export is in"
            )
        if path.suffix.lower().lstrip(".") not in _FILE_TYPES[kind]:
            noun = "an image" if kind == "image_file" else "a video"
            raise RowRejected(
                f"{entity.content.field} {value!r} is not {noun} file "
                f"({', '.join(sorted(_FILE_TYPES[kind]))})"
            )
    return {"kind": kind, "value": value}


def _first_words(text: str) -> str:
    words = " ".join(text.split())
    return words if len(words) <= 60 else f"{words[:57]}…"


def holds_own_text(entity: RecipeEntity) -> bool:
    """ADR-127 decision 1: a `Document` entity whose `content` is `document_text` holds its own
    text. The text is written onto that Document itself, with no content node and no `HOLDS`
    (which the ontology does not allow from a Document). On any other entity `content` is held:
    a content Document, linked by `HOLDS`."""
    return (
        entity.type == "Document"
        and entity.content is not None
        and entity.content.kind == "document_text"
    )


async def _write_held_content(
    resolved: _ResolvedEntity,
    holder_id: NodeId,
    media: MediaStore,
    *,
    row_index: int,
    now: datetime,
    state: _RunState,
) -> None:
    """The content `resolved` holds, kept in the media store; a `Document` naming it (one per
    file however many hold it); and a `HOLDS` link from the holder (ADR-094)."""
    assert resolved.content is not None
    kind, value = resolved.content["kind"], resolved.content["value"]
    entity = resolved.entity
    if kind == "document_text":
        data, content_type, title = value.encode("utf-8"), "text/plain", _first_words(value)
    else:
        base = Path(state.source).parent.resolve()
        path = (base / value).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            field_name = entity.content.field if entity.content else "content"
            state.content_rejections.append(
                RejectionRecord(
                    row_index=row_index,
                    reason=(
                        f"{field_name} {value!r} not found next to the export; the "
                        f"{entity.type} was loaded without it"
                    ),
                    sample="",
                )
            )
            return
        data = path.read_bytes()
        content_type = _FILE_TYPES[kind][path.suffix.lower().lstrip(".")]
        title = path.name
    ref = await media.put(data, content_type)
    document_id = f"content:{sha256(ref.encode()).hexdigest()[:32]}"
    handling = _handling(
        _merge_override(state.recipe.defaults.handling, _row_override(resolved, entity))
    )
    provenance = _provenance(
        _merge_override(state.recipe.defaults.provenance, entity.provenance),
        source=state.source,
        row_index=row_index,
        now=now,
    )
    if document_id not in state.documents_written:
        # The id is the hash of the bytes, so it is the same for the same text from another holder,
        # an earlier load or a Files-tab upload, and the upsert merges into a document already
        # there. Looked up first (ADR-127 decision 6): created only when absent. The check is the
        # port's internal, unfiltered one: an access-filtered read would show a loader a document
        # above their clearance as absent, and the record would call another load's node created.
        existed = document_id in await state.graph.existing_node_ids([document_id])
        # What the loader is told (the counts) comes only from what they may read: a document they
        # cannot read counts as created, as in a store without it, or the counts would say that
        # the content exists somewhere they may not look (rule 3). The unfiltered answer feeds the
        # record's `merged_node_ids` alone.
        readable = existed and bool(await state.graph.get_nodes([document_id], state.principal))
        document = NodeWrite(
            id=document_id,
            type="Document",
            properties={"title": title, "media_kind": _MEDIA_KIND[kind], "object_ref": ref},
            provenance=provenance,
            handling=handling,
            created_by=state.principal.id,
            created_at=now,
            load_id=state.load_id,
            recipe_id=state.recipe.id,
            recipe_version=state.recipe.version,
        )
        await state.graph.upsert_nodes([document], state.tx)
        state.node_types[document_id] = "Document"
        state.documents_written.add(document_id)
        if existed:
            state.merged_node_ids.append(document_id)
        else:
            state.created_node_ids.append(document_id)
            state.created_node_lookup.add(document_id)
        if readable:
            state.nodes_referenced += 1
        else:
            state.nodes_created += 1
    holds = EdgeWrite(
        id=f"{document_id}:held-by:{holder_id}",
        type="HOLDS",
        source=holder_id,
        target=document_id,
        provenance=provenance,
        handling=handling,
        created_by=state.principal.id,
        created_at=now,
        load_id=state.load_id,
        recipe_id=state.recipe.id,
        recipe_version=state.recipe.version,
    )
    # Counted per held write: its id is the document's and holder's, so a returned id cannot tell a
    # new HOLDS link from one merged into (unlike `_write_edge` below).
    state.edges_created += 1
    # The record cannot rest on that id either. A holder this load created has no earlier link, so
    # the link is its own; any other holder's may already hold this document, and is recorded as
    # merged so a revert refuses naming it rather than take back another load's link. One thing the
    # id does say: the store returns a new id only for a link of its own, when a link of another
    # audience holds the id sent (ADR-102 Amendment 3), so a returned id that is not the one sent
    # is the load's own link whoever the holder is. Both are settled at the flush
    # (`_settle_link`), with the holder's state as it is now.
    await _hold_edge(
        state,
        holds,
        row_index=row_index,
        counted_by_readability=False,
        holder_created=holder_id in state.created_node_lookup,
    )


def _note_edge(
    state: _RunState, edge_id: EdgeId, *, created: bool, counted_by_readability: bool = False
) -> None:
    """Records a link the load wrote as created or merged (ADR-127 decision 6), once each. A write
    to a link this load already created adds nothing: it is the load's own, not an earlier one's."""
    if edge_id in state.created_edge_lookup:
        return
    if created:
        state.created_edge_ids.append(edge_id)
        state.created_edge_lookup.add(edge_id)
    elif edge_id not in state.merged_edge_lookup:
        state.merged_edge_ids.append(edge_id)
        state.merged_edge_lookup.add(edge_id)
        if counted_by_readability:
            state.merged_link_ids.append(edge_id)


async def _count_hidden_merges(state: _RunState) -> None:
    """The edge upsert is not access-filtered, so a write between two nodes that a link the loader
    may not read already joins merges into it, and `edges_created` would not rise: the count would
    tell the loader the link exists (rule 3). A link merged into counts as created unless the
    loader can read it, as in a store without it. One `get_edges` for the whole load; the record
    keeps the true split (`created_edge_ids` and `merged_edge_ids`) whatever is counted."""
    if not state.merged_link_ids:
        return
    readable = {e.id for e in await state.graph.get_edges(state.merged_link_ids, state.principal)}
    state.edges_created += sum(1 for edge_id in state.merged_link_ids if edge_id not in readable)


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
    handling = _handling(
        _merge_override(state.recipe.defaults.handling, _row_override(resolved, edge))
    )
    provenance = _provenance(
        _merge_override(state.recipe.defaults.provenance, edge.provenance),
        source=state.source,
        row_index=row_index,
        now=now,
    )
    # `01_DOMAIN_MODEL.md` §7: duplicate rows collapse to one event, but
    # every source row reference is retained on the survivor — every
    # collapsed duplicate's row index, not just the representative row's.
    for duplicate_index in duplicate_row_indices:
        provenance.sources.append(
            SourceRef(document_id=state.source, locator=f"row {duplicate_index}", excerpt_hash="")
        )
    interval = edge_interval(resolved.instant, resolved.valid_to, resolved.span)

    write = EdgeWrite(
        id=new_edge_id(),
        type=edge.type,
        source=source_id,
        target=target_id,
        properties=properties,
        interval=interval,
        occurrences=1,
        provenance=provenance,
        handling=handling,
        created_by=state.principal.id,
        created_at=now,
        load_id=state.load_id,
        recipe_id=state.recipe.id,
        recipe_version=state.recipe.version,
    )
    event: EventRecord | None = None
    if resolved.instant is not None:
        # The event's own properties carry the full set of source rows it
        # summarises — the surviving event's provenance chain, same as the
        # edge's above.
        event_properties = {
            **properties,
            "source_rows": [row_index, *duplicate_row_indices],
            # ADR-094: the link's text, where the reader and extraction read an email's.
            **_content_properties(resolved.content),
        }
        event = EventRecord(
            event_id=str(ULID()),
            # This row's own write's id, until the flush gives the link's stored one.
            edge_id=write.id,
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
            # ADR-127 decision 6: so a revert can retract this event with its load.
            load_id=state.load_id,
        )
        events.append(event)
    # Held, not written: the run combines its writes to one per link and writes them at the end of
    # its rows (ADR-127 Amendment 19). The event, and this row's entry in `written`, take the
    # stored id of their link then.
    await _hold_edge(
        state,
        write,
        row_index=row_index,
        counted_by_readability=True,
        event=event,
        record_written=True,
    )


def _refuse_held_write(state: _RunState, write: EdgeWrite, *, row_index: int) -> None:
    """What `GraphArcadeDBAdapter.upsert_edges` refuses before it writes, checked as the write is
    held so the refusal names the row (ADR-127 Amendment 19): a type the ontology lacks, a property
    it does not allow, an end its type does not allow. An end this run never wrote or matched is the
    flush's to refuse, as the adapter does."""
    try:
        edge_type = state.ontology.edge_type(write.type)
        if edge_type is None:
            raise OntologyError(f"{write.type!r} is not a type in the active ontology")
        validate_properties(edge_type, write.properties)
        source_type = state.node_types.get(write.source)
        target_type = state.node_types.get(write.target)
        if source_type is not None and target_type is not None:
            validate_edge_endpoints(edge_type, source_type=source_type, target_type=target_type)
    except OntologyError as error:
        raise OntologyError(f"row {row_index}: {error}") from error


async def _hold_edge(
    state: _RunState,
    write: EdgeWrite,
    *,
    row_index: int,
    counted_by_readability: bool,
    holder_created: bool | None = None,
    event: EventRecord | None = None,
    record_written: bool = False,
) -> None:
    """Hold one row's link write (ADR-127 Amendment 19). It is checked as the adapter would check
    it, then combined into the write already held for its link (`aggregate_edge_writes`, keyed as it
    keys: the type, the pair and the audience under the handling scheme), or held as that link's
    first. A run with no scheme, or a test's flush size of one, flushes at once, so nothing is
    combined and each write is its own."""
    _refuse_held_write(state, write, row_index=row_index)
    scheme = state.scheme

    def directed(name: str) -> bool:
        edge_type = state.ontology.edge_type(name)
        return bool(edge_type.directed) if edge_type is not None else True

    def audience(edge: EdgeWrite) -> Hashable:
        # With no scheme nothing is combined (each write is flushed as it is held), so no audience
        # is read: the key is never compared with another's.
        return audience_of(edge.handling, edge.datasets, scheme) if scheme is not None else ()

    def handling(old: Handling, new: Handling) -> Handling:
        assert scheme is not None  # a run with no scheme flushes each write, so never folds
        return merge_handling(old, new, scheme)

    key = edge_write_key(write, directed=directed, audience=audience)
    held = state.held_links.get(key)
    if held is None:
        held = _HeldLink(
            write=write,
            counted_by_readability=counted_by_readability,
            holder_created=holder_created,
        )
        state.held_links[key] = held
    else:
        (folded,) = aggregate_edge_writes(
            [held.write, write], directed=directed, handling=handling, audience=audience
        )
        held.write = folded.write
    if event is not None:
        held.events.append(event)
    if record_written and state.written is not None:
        held.written_slots.append(len(state.written))
        state.written.append(write)
    if scheme is None or _FORCE_FLUSH_SIZE == 1:
        await _flush_held_links(state)


async def _flush_held_links(state: _RunState) -> None:
    """Write the held links with `upsert_edges`, in the order each was first held, in chunks of
    `FLUSH_CHUNK`, and settle each with the stored id it came back with (ADR-127 Amendment 19)."""
    held = list(state.held_links.values())
    state.held_links.clear()
    for start in range(0, len(held), FLUSH_CHUNK):
        chunk = held[start : start + FLUSH_CHUNK]
        ids = await state.graph.upsert_edges([link.write for link in chunk], state.tx)
        for link, edge_id in zip(chunk, ids, strict=True):
            _settle_link(state, link, edge_id)


def _settle_link(state: _RunState, link: _HeldLink, edge_id: EdgeId) -> None:
    """What a written link tells the run: its stored id, once in the load's touched links, noted
    created or merged, counted, and handed to its events and its rows' entries in `written`."""
    if edge_id not in state.touched_edge_lookup:
        state.touched_edge_lookup.add(edge_id)
        state.touched_edge_ids.append(edge_id)
    kept_the_id = edge_id == link.write.id
    if link.holder_created is None:
        # A link is created only when the store kept the id this write was sent. A second call
        # between the same two parties merges into the link already there, and `upsert_edges`
        # returns that link's id: counting every write said "236 edges created" for 141 links
        # (9 October 2026). The combined write has its first row's id, as that row's write did.
        _note_edge(
            state, edge_id, created=kept_the_id, counted_by_readability=link.counted_by_readability
        )
        if kept_the_id:
            state.edges_created += 1
    else:
        # A `HOLDS` link was counted per held write when it was held.
        _note_edge(
            state,
            edge_id,
            created=link.holder_created or not kept_the_id,
            counted_by_readability=link.counted_by_readability,
        )
    for event in link.events:
        event.edge_id = edge_id
    if state.written is not None:
        for slot in link.written_slots:
            state.written[slot] = state.written[slot].model_copy(update={"id": edge_id})


def _content_properties(content: dict[str, str] | None) -> dict[str, Any]:
    """The event properties a link's text becomes: the whole text, as an email's body is kept
    (ADR-095 decisions 3 and 5). `excerpt` keeps its name; `truncated` stays, always false."""
    if not content:
        return {}
    text = content["text"]
    return {
        "excerpt": text,
        "truncated": False,
        "content_kind": content["kind"],
    }


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _as_str(value: object) -> str | None:
    return str(value) if value is not None else None


# --- Dry run (Verify — 09_INGEST_STUDIO.md §5) ----------------------------
#
# No `GraphPort` write, ever — the property that makes this a dry run rather
# than a load. No Parquet staging either: `_stage_raw_rows`/`_stage_rows` are
# themselves persistent writes (to object storage), and §5 says "producing
# no persistent writes" without carving out an exception for the staging
# tier, so this goes straight from `resolve_rows()`'s in-memory `StagedRow`s
# into simulation. `on_match: reference` is the one place this must still
# touch the real graph: it calls the same `GraphPort.find_node` under the
# same `Principal` `_write_entity` calls for a real load — an access-filtered
# miss returns `None` exactly like any other read, so a principal who cannot
# see a matching node sees this entity as "would create," never as evidence
# that a higher-classification match exists. That guarantee falls out of
# reusing the one lookup path everything else already goes through; nothing
# below re-derives or loosens it.


@dataclass
class DryRunEntityCount:
    created: int = 0
    referenced: int = 0


@dataclass
class DryRunEdgeCount:
    created: int = 0


@dataclass
class DryRunResult:
    rows_read: int
    rows_deduplicated: int
    entities_by_type: dict[str, DryRunEntityCount]
    edges_by_type: dict[str, DryRunEdgeCount]
    rejections: list[RejectionRecord]
    nodes: list[Node]
    edges: list[Edge]
    #: The subset of `nodes` this dry run would create — never one it
    #: merely referenced (the same asymmetry `LoadReport.created_node_ids`
    #: already draws). `services/api/studio_verify.py` uses exactly this
    #: set to decide which node's properties to shape-mask when the
    #: requesting principal cannot clear the source's own classification —
    #: a referenced node's values are never masked here, since `find_node`'s
    #: own access filter (not this set) is what already decided this
    #: principal may see that particular node at all.
    created_node_ids: frozenset[NodeId]
    #: ADR-127 decision 5: the rows of the sample the case already kept a key for, which a run
    #: would skip: counted as the run counts them.
    rows_already_loaded: int = 0


@dataclass
class _DryRunState:
    graph: GraphPort
    principal: Principal
    recipe: Recipe
    ontology: OntologySchema
    source: str
    now: datetime
    scheme: HandlingScheme | None = None
    nodes: dict[NodeId, Node] = field(default_factory=dict)
    #: Keyed by (edge type, source id, target id, audience) — same-pair edges of one audience merge
    #: within the sample, mirroring `GraphArcadeDBAdapter.upsert_edges`'s real merge (ADR-102
    #: Amendment 3), so "how many distinct links" reads the same way here as after a real load.
    edges: dict[tuple[Any, ...], Edge] = field(default_factory=dict)
    entities_by_type: dict[str, DryRunEntityCount] = field(default_factory=dict)
    edges_by_type: dict[str, DryRunEdgeCount] = field(default_factory=dict)
    local_index: dict[tuple[str, str, str], NodeId] = field(default_factory=dict)
    created_node_ids: set[NodeId] = field(default_factory=set)


async def _dry_run_entity(
    resolved: _ResolvedEntity, *, row_index: int, state: _DryRunState
) -> NodeId | None:
    if resolved.properties is None:
        return None
    entity = resolved.entity
    entity_type_def = state.ontology.entity_type(entity.type)
    own_text = resolved.content["value"] if holds_own_text(entity) and resolved.content else None
    properties = _coerced_properties(entity, resolved.properties, state.ontology, own_text)
    match_key = _match_key(entity, properties)
    counts = state.entities_by_type.setdefault(entity.type, DryRunEntityCount())

    if match_key is not None:
        cached = state.local_index.get(match_key)
        if cached is not None:
            counts.referenced += 1
            return cached
        existing = await state.graph.find_node(
            entity.type, match_key[1], match_key[2], state.principal
        )
        if existing is not None:
            # The real node, as-is — its own stored handling/provenance/id,
            # never re-derived. `find_node`'s own access filter is what
            # decided this principal may see it at all.
            state.local_index[match_key] = existing.id
            state.nodes[existing.id] = existing
            counts.referenced += 1
            return existing.id

    # Only the "would create" path is checked against the ontology — the
    # same asymmetry `GraphArcadeDBAdapter.upsert_nodes` already has for a
    # real load: `validate_properties` only ever runs for a `NodeWrite`,
    # never for a referenced hit's already-stored properties. A recipe that
    # would fail here would fail identically, uncaught, at real load time —
    # §5's "Verify must pass before Publish" is a hollow promise if this
    # class of failure only ever surfaces after Publish.
    if entity_type_def is None:
        raise OntologyError(f"{entity.type!r} is not a type in the active ontology")
    validate_properties(entity_type_def, properties)

    handling = _handling(
        _merge_override(state.recipe.defaults.handling, _row_override(resolved, entity))
    )
    provenance = _provenance(
        _merge_override(state.recipe.defaults.provenance, entity.provenance),
        source=state.source,
        row_index=row_index,
        now=state.now,
    )
    node_id = new_node_id()
    node = Node(
        id=node_id,
        type=entity.type,
        properties=properties,
        provenance=provenance,
        handling=handling,
        resolution=ResolutionState(),
        audit=AuditStub(created_at=state.now, created_by=state.principal.id, revision=1),
    )
    state.nodes[node_id] = node
    state.created_node_ids.add(node_id)
    counts.created += 1
    if match_key is not None:
        state.local_index[match_key] = node_id
    return node_id


def _dry_run_edge(
    resolved: _ResolvedEdge,
    refs: Mapping[str, NodeId],
    *,
    row_index: int,
    state: _DryRunState,
) -> None:
    if resolved.properties is None:
        return
    edge = resolved.edge
    source_id = refs.get(edge.from_ref)
    target_id = refs.get(edge.to_ref)
    if source_id is None or target_id is None:
        return  # an endpoint entity was conditionally absent this row

    edge_type_def = state.ontology.edge_type(edge.type)
    properties = _coerce_declared_numeric_types(resolved.properties, edge_type_def)
    handling = _handling(
        _merge_override(state.recipe.defaults.handling, _row_override(resolved, edge))
    )
    # One link per audience (ADR-102 Amendment 3), as a real load makes them. The dry run writes no
    # datasets, so they are the same for every simulated link. With no scheme no code is known to be
    # restricted, as `audience_of` reads a code the scheme does not define: the units are left out.
    audience = (
        audience_of(handling, (), state.scheme)
        if state.scheme is not None
        else (handling.classification, handling.handling_code, (), None, None)
    )
    key = (edge.type, source_id, target_id, audience)
    existing = state.edges.get(key)
    if existing is not None:
        existing.occurrences = (existing.occurrences or 1) + 1
        # As the real load merges them (ADR-127 decision 11): the earliest start and the latest end,
        # and open if either is.
        existing.interval = merge_interval(
            existing.interval, edge_interval(resolved.instant, resolved.valid_to, resolved.span)
        )
        return

    # Same real-load parity as `_dry_run_entity`'s own check —
    # `GraphArcadeDBAdapter.upsert_edges` validates type, properties and
    # endpoint compatibility before ever writing; a merge into an existing
    # preview edge (above) skips this precisely because a real merge write
    # skips re-validating an edge that already exists too.
    if edge_type_def is None:
        raise OntologyError(f"{edge.type!r} is not a type in the active ontology")
    validate_properties(edge_type_def, properties)
    validate_edge_endpoints(
        edge_type_def,
        source_type=state.nodes[source_id].type,
        target_type=state.nodes[target_id].type,
    )

    provenance = _provenance(
        _merge_override(state.recipe.defaults.provenance, edge.provenance),
        source=state.source,
        row_index=row_index,
        now=state.now,
    )
    interval = edge_interval(resolved.instant, resolved.valid_to, resolved.span)
    state.edges[key] = Edge(
        id=new_edge_id(),
        type=edge.type,
        source=source_id,
        target=target_id,
        properties=properties,
        interval=interval,
        occurrences=1,
        provenance=provenance,
        handling=handling,
        audit=AuditStub(created_at=state.now, created_by=state.principal.id, revision=1),
    )
    state.edges_by_type.setdefault(edge.type, DryRunEdgeCount()).created += 1


async def dry_run_recipe(
    recipe: Recipe,
    rows: Iterable[Mapping[str, str]],
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    principal: Principal,
    source: str,
    scheme: HandlingScheme | None = None,
    row_keys: RowKeys | None = None,
    investigation_scope: str | None = None,
) -> DryRunResult:
    """Verify (`09_INGEST_STUDIO.md` §5): the same `resolve_rows()` output
    Map's own preview machinery is built on, simulated instead of loaded.
    `load_id="dry-run"` is never persisted anywhere — `resolve_rows` only
    threads it onto `StagedRow`s that this function itself consumes and
    discards."""
    _require_scheme_to_judge_bound_handling(recipe, scheme)
    sample = list(rows)
    # Judged as the run judges (ADR-127 decision 5), by asking the store and writing nothing.
    already = await kept_among(recipe, sample, row_keys, investigation_scope)
    resolved = resolve_rows_keyed(
        recipe,
        sample,
        load_id="dry-run",
        source=source,
        ontology=ontology,
        scheme=scheme,
        already_loaded=already,
    )
    staged_rows, rejections = resolved.staged_rows, resolved.rejections
    rows_read, rows_deduplicated = resolved.rows_read, resolved.rows_deduplicated
    state = _DryRunState(
        graph=graph,
        principal=principal,
        recipe=recipe,
        ontology=ontology,
        source=source,
        now=datetime.now(UTC),
        scheme=scheme,
    )
    for staged_row in staged_rows:
        refs: dict[str, NodeId] = {}
        for staged_entity in staged_row.entities:
            resolved_entity = _staged_entity_to_resolved(staged_entity, recipe)
            node_id = await _dry_run_entity(
                resolved_entity, row_index=staged_row.row_index, state=state
            )
            if node_id is not None:
                refs[staged_entity.ref] = node_id
        for staged_edge in staged_row.edges:
            resolved_edge = _staged_edge_to_resolved(staged_edge)
            _dry_run_edge(resolved_edge, refs, row_index=staged_row.row_index, state=state)

    # `weight` here is a local, within-sample density signal — `min(1.0,
    # occurrences / 5)` — not `GraphArcadeDBAdapter._weigh_edge`'s real
    # corpus-wide formula. That formula lives past `GraphPort`'s own
    # interface (adapter-internal Gremlin over corpus-wide degree stats);
    # reaching for it here would mean a new port method this stage doesn't
    # need, or duplicating adapter internals engine.py has never depended
    # on. Still enough to make a dense pair visually heavier than a sparse
    # one — the actual diagnostic §5 asks Verify's canvas for.
    for edge in state.edges.values():
        edge.weight = min(1.0, (edge.occurrences or 1) / 5)

    return DryRunResult(
        rows_read=rows_read,
        rows_deduplicated=rows_deduplicated,
        rows_already_loaded=resolved.rows_already_loaded,
        entities_by_type=state.entities_by_type,
        edges_by_type=state.edges_by_type,
        rejections=rejections,
        nodes=list(state.nodes.values()),
        edges=list(state.edges.values()),
        created_node_ids=frozenset(state.created_node_ids),
    )


def _staged_entity_to_resolved(staged: StagedEntity, recipe: Recipe) -> _ResolvedEntity:
    entities_by_ref = {e.ref: e for e in recipe.row_template.entities}
    recipe_entity = entities_by_ref[staged.ref]
    return _ResolvedEntity(recipe_entity, staged.properties, staged.content, staged.handling)


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
    return _ResolvedEdge(
        recipe_edge,
        staged.properties,
        staged.instant,
        staged.content,
        staged.handling,
        staged.valid_to,
        staged.span,
    )


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
    media: MediaStore | None = None,
    skip_row_indices: frozenset[int] = frozenset(),
    row_numbers: Sequence[int] | None = None,
    written: list[NodeWrite | EdgeWrite] | None = None,
    scheme: HandlingScheme | None = None,
    row_keys: RowKeys | None = None,
) -> tuple[LoadReport, list[EventRecord]]:
    """`row_keys` (ADR-127 decision 5): the store of loaded rows. A recipe with `deduplicate` skips
    a row whose key the case (`investigation_scope`) already kept, whatever the recipe's version,
    and the report counts it in `rows_already_loaded`; the keys of the rows this load wrote are in
    `LoadReport.kept_row_keys`, for the caller to keep in the transaction that records the load.
    `skip_row_indices`: rows resolved but not written — those a failing pre-commit rule holds
    (ADR-109 ruling 1); a held row's duplicates go with it, as they share its survivor.
    `row_numbers` as `resolve_rows` takes it. `written`, when given, receives every node this load
    created and every link it wrote (ADR-109 phase F)."""
    if recipe.ontology_version != ontology.version:
        raise StaleRecipeError(
            f"recipe {recipe.id!r} targets ontology version {recipe.ontology_version}, but the "
            f"active ontology is version {ontology.version} — open and re-publish the recipe "
            "before running it again"
        )
    # ADR-120 D10, Amendment 1: the packs it names or writes, at the versions it was published at.
    check_recipe_pins(recipe, ontology)

    # ADR-081 step D: refused again at run, before anything is written (Amendment 1 item 7).
    check_recipe_rules(
        recipe.row_template,
        ontology,
        units=recipe.defaults.units,
        defaults_handling=recipe.defaults.handling,
        scheme=scheme,
        declared_columns=recipe.defaults.handling_columns,
    )
    if recipe.deduplicate is not None:
        key_problems = deduplicate_list_problems(recipe.deduplicate)
        if key_problems:
            raise RecipeRuleError(key_problems)
    _require_scheme_to_judge_bound_handling(recipe, scheme)
    if holds_content(recipe.row_template) and media is None:
        raise RecipeRuleError(
            [
                "This recipe marks content an entity holds, which is kept in the deployment's "
                "media store, and this run has no media store (ADR-094)."
            ]
        )
    # Materialised once, immediately, so `stage_raw_rows` sees every field
    # exactly as the connector produced it — before `resolve_rows` (the
    # pipeline's "normalise" step) touches any of it.
    # `03_CONDUIT_MIDDLEWARE.md` §5.1: raw staging happens first, and only
    # it makes re-resolution and schema migration possible without a
    # re-upload; staging only the post-transform rows, this module's
    # original shape, was a defect, not a design choice.
    materialized_rows = list(rows)
    # Before anything is staged or written: a run under a changed `deduplicate` is refused whole.
    already = await kept_among(recipe, materialized_rows, row_keys, investigation_scope)
    storage = storage or ObjectStorageConfig.from_env()
    _stage_raw_rows(materialized_rows, storage=storage, load_id=load_id, source=source)

    resolved = resolve_rows_keyed(
        recipe,
        materialized_rows,
        load_id=load_id,
        source=source,
        ontology=ontology,
        row_numbers=row_numbers,
        scheme=scheme,
        already_loaded=already,
    )
    staged_rows, rejections = resolved.staged_rows, resolved.rejections
    rows_read, rows_deduplicated = resolved.rows_read, resolved.rows_deduplicated

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
        written=written,
        scheme=scheme,
    )
    events: list[EventRecord] = []

    for staged_row in loaded_rows:
        if staged_row.row_index in skip_row_indices:
            continue
        now = datetime.now(UTC)
        refs: dict[str, NodeId] = {}
        for staged_entity in staged_row.entities:
            resolved_entity = _staged_entity_to_resolved(staged_entity, recipe)
            own_text = holds_own_text(resolved_entity.entity)
            node_id = await _write_entity(
                resolved_entity,
                row_index=staged_row.row_index,
                now=now,
                state=state,
                own_text_media=media if own_text else None,
            )
            if node_id is not None:
                refs[staged_entity.ref] = node_id
                if resolved_entity.content and media is not None and not own_text:
                    await _write_held_content(
                        resolved_entity,
                        node_id,
                        media,
                        row_index=staged_row.row_index,
                        now=now,
                        state=state,
                    )
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

    # ADR-127 Amendment 19: the links the rows wrote, combined to one each, are written now, before
    # the hidden merges are counted and the report is built, so both see stored ids only.
    await _flush_held_links(state)
    await _count_hidden_merges(state)
    report = LoadReport(
        load_id=load_id,
        recipe_id=recipe.id,
        recipe_version=recipe.version,
        rows_read=rows_read,
        rows_deduplicated=rows_deduplicated,
        rows_already_loaded=resolved.rows_already_loaded,
        row_key_fingerprint=recipe_fingerprint(recipe),
        # The groups this load wrote: not a held row (`skip_row_indices`), not a rejected one, not
        # one already loaded; each key once.
        kept_row_keys=list(
            dict.fromkeys(
                r.row_key
                for r in loaded_rows
                if r.row_key is not None and r.row_index not in skip_row_indices
            )
        ),
        nodes_created=state.nodes_created,
        nodes_referenced=state.nodes_referenced,
        edges_created=state.edges_created,
        rejections=[*rejections, *state.content_rejections],
        created_node_ids=state.created_node_ids,
        referenced_node_ids=state.referenced_node_ids,
        touched_edge_ids=state.touched_edge_ids,
        created_edge_ids=state.created_edge_ids,
        merged_edge_ids=state.merged_edge_ids,
        merged_node_ids=state.merged_node_ids,
    )
    return report, events
