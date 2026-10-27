"""What a recipe may declare, checked when it is saved and again when it runs.

ADR-081 step D (and Amendment 1 item 7): a relationship the Ingest Studio writes from the source's
own records is **Direct**, because a loaded record stands behind it. A recipe that names a
Probabilistic type is refused, as is one naming `SAME_AS` (the resolution engine's alone) or
`NOT_SAME_AS` (an analyst's judgement), or a type the ontology does not have. No expression
language is involved (rule 8): each rule reads only what the recipe declares.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from services.ingest.transforms import STRUCTURED_PARTS, gives_a_list, transform_name_and_part

from knowledge_adapters import ARITY
from ontology.errors import HandlingSchemeError
from ontology.handling import HandlingScheme, merge_handling
from schemas.domain import NOT_SAME_AS, Handling, OntologySchema
from schemas.ingest import DeduplicateConfig, RecipeEdge, RecipeEntity, RowTemplate

FILE_KINDS = frozenset({"image_file", "video_file"})


def deduplicate_list_problems(config: DeduplicateConfig) -> list[str]:
    """A key part bound through an adapter whose output is a list (`split`): a key part is one
    value. Judged at save with the rest (`deduplicate_problems`) and again at run, which has no
    header to judge columns by."""
    return [
        f"deduplicate key {position}: transform {binding.transform!r} gives a list, and a key part "
        "is one value"
        for position, binding in enumerate(config.key, start=1)
        if gives_a_list(binding.transform)
    ]


def deduplicate_problems(
    config: DeduplicateConfig, source_columns: Sequence[str] | None
) -> list[str]:
    """What a `deduplicate` (ADR-127 decision 5) declares that the source cannot support, each in
    words: a key that names no source column (a literal alone puts every row in one group, which
    loads one row of the file), a column the source does not have (when its columns are known: the
    header of the file, `None` when it cannot be read, in which case a column is judged row by row
    at run), and a multi-column binding with no transform or the wrong number of columns (the
    engine's `fields` rule, `ARITY`). The same shapes `dedup_key` resolves, so what passes here is
    what a run can key."""
    problems: list[str] = deduplicate_list_problems(config)
    named_any = False
    known = set(source_columns) if source_columns is not None else None
    for position, binding in enumerate(config.key, start=1):
        if binding.optional:
            problems.append(
                f"deduplicate key {position}: `optional` applies to a property binding only"
            )
        columns = list(binding.fields or ([binding.field] if binding.field else []))
        if not columns and binding.literal is None:
            problems.append(f"deduplicate key {position} names no source column")
            continue
        if columns:
            named_any = True
        if binding.fields is not None:
            if binding.transform is None:
                problems.append(
                    f"deduplicate key {position}: a `fields` binding must declare a `transform`"
                )
            elif ARITY.get(binding.transform) is None:
                problems.append(
                    f"deduplicate key {position}: transform {binding.transform!r} does not "
                    "support a multi-field `fields` binding"
                )
            elif len(binding.fields) != ARITY[binding.transform]:
                problems.append(
                    f"deduplicate key {position}: transform {binding.transform!r} takes "
                    f"{ARITY[binding.transform]} field(s), got {len(binding.fields)}"
                )
        if known is not None:
            for column in columns:
                if column not in known:
                    problems.append(
                        f"deduplicate key {position} names {column!r}, which is not a column of "
                        "the source"
                    )
    if config.key and not named_any:
        problems.append("deduplicate key names no source column (a literal alone keys nothing)")
    return problems


def template_elements(template: RowTemplate) -> list[RecipeEntity | RecipeEdge]:
    """Every entity and link of `template`, entities first."""
    return [*template.entities, *template.edges]


def handling_bindings(override: Mapping[str, Any] | None) -> dict[str, str]:
    """The parts of an element's `handling` bound to a column (ADR-127 decision 3), as
    `{part: column}`."""
    return {
        name: str(item["field"])
        for name, item in (override or {}).items()
        if isinstance(item, dict) and "field" in item
    }


def literal_handling(override: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """`override` without its column bindings: what is fixed for every row."""
    if override is None:
        return None
    return {k: v for k, v in override.items() if not isinstance(v, dict)}


def _owner(element: RecipeEntity | RecipeEdge) -> str:
    return (
        f"entity {element.ref!r}" if isinstance(element, RecipeEntity) else f"link {element.type!r}"
    )


def handling_baseline_problems(
    template: RowTemplate,
    defaults_handling: Mapping[str, Any] | None,
    scheme: HandlingScheme | None,
) -> list[str]:
    """Each element's `handling` and `provenance` as the recipe declares them, before any row:

    - a `handling` key `Handling` does not have (`clasification`) is refused, not dropped;
    - a column bound in `provenance` is refused (provenance has no per-row source; `_provenance`
      would fail the whole run on it);
    - given `defaults_handling` and a `scheme`, the element's literal override over the defaults may
      only tighten them in every part (`merge_handling`'s order), the check ADR-127 decision 3 makes
      of a cell, made of the recipe's own fixed values too."""
    problems: list[str] = []
    known = set(Handling.model_fields)
    for element in template_elements(template):
        owner = _owner(element)
        for name in element.handling or {}:
            if name not in known:
                problems.append(
                    f"{owner} sets handling {name!r}, which a marking does not have "
                    f"({', '.join(sorted(known))})."
                )
        for name, value in (element.provenance or {}).items():
            if isinstance(value, dict):
                problems.append(
                    f"{owner} binds provenance {name!r} to a column; provenance cannot come from "
                    "a column, only fixed values (state)."
                )
        literal = literal_handling(element.handling)
        if not literal or defaults_handling is None or scheme is None:
            continue
        try:
            default = Handling.model_validate(_complete_defaults(defaults_handling))
            bound = Handling.model_validate({**_complete_defaults(defaults_handling), **literal})
            merged = merge_handling(bound, default, scheme)
        except HandlingSchemeError as exc:
            problems.append(f"{owner} sets a handling the scheme does not define: {exc}.")
            continue
        except ValueError as exc:
            problems.append(f"{owner} sets a handling that is not a valid marking: {exc}")
            continue
        if merged != bound:
            for part in ("classification", "handling_code", "action_code", "sanitisation_code"):
                if getattr(merged, part) != getattr(bound, part):
                    problems.append(
                        f"{owner} sets handling {part} {getattr(bound, part)!r}, which is looser "
                        f"than the source's {getattr(default, part)!r}; an element may only "
                        "tighten the source's marking."
                    )
    return problems


def _complete_defaults(defaults_handling: Mapping[str, Any]) -> dict[str, Any]:
    """The source's marking with the `originator` an old draft may lack filled as `Handling`
    needs, and `owning_unit` as the engine does (`_handling`)."""
    raw = dict(defaults_handling)
    raw.pop("units", None)
    if raw.get("originator") is not None:
        raw.setdefault("owning_unit", raw["originator"])
    raw.setdefault("handling_code", "P")
    return raw


class RecipeRuleError(Exception):
    """A recipe declares something the rules above refuse; the message names each problem."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _written(entity: RecipeEntity) -> set[str]:
    """The properties an entity's template writes: its bound ones, and a `title` for a Document
    holding its own text, which the engine takes from the text's first words when none is bound
    (ADR-127 decision 1; `engine.holds_own_text`, not imported, since the engine imports this)."""
    written = set(entity.properties)
    if (
        entity.type == "Document"
        and entity.content is not None
        and entity.content.kind == "document_text"
    ):
        written.add("title")
    return written


def reference_match_problems(
    template: RowTemplate, ontology: OntologySchema, *, complete: bool = True
) -> list[str]:
    """ADR-127 Amendment 37: an entity looked up by reference (`on_match: reference`) is found by
    `GraphPort.find_node`, which the store answers only for a type's `identifiers` and its
    `indexed` properties, and the adapter stores one of those as a top-level field only when the
    node is written with it. A reference on any other property, or on a field the entity's own
    template does not write (the lookup value is then the text "None" on every row), never
    matches, so the engine would write a new, empty node for every row; each such entity is
    refused here, in one sentence. An entity that is not a reference, one with no `match_on`, and a
    type the ontology lacks (refused elsewhere) are not judged.

    `complete=False` is a template still being built (a Map save): the field must be findable, but
    the entity need not bind it yet, so a half-built template can still be saved. Verify, publish
    and the run judge a complete template."""
    problems: list[str] = []
    for entity in template.entities:
        if entity.on_match != "reference" or not entity.match_on:
            continue
        type_def = ontology.entity_type(entity.type)
        if type_def is None:
            continue
        findable = set(type_def.identifiers) | {p.name for p in type_def.properties if p.indexed}
        if entity.match_on not in findable:
            problems.append(
                f"{entity.type} cannot be found by {entity.match_on}: a reference can only match "
                f"an identifier or an indexed property of the type, so this would make a new "
                f"{entity.type} for every row."
            )
        elif complete and entity.match_on not in _written(entity):
            problems.append(
                f"{entity.type} cannot be found by {entity.match_on}: the entity does not write "
                f"{entity.match_on}, and a reference can only match a stored identifier or "
                f"indexed property, so this would make a new {entity.type} for every row."
            )
    return problems


def check_reference_matches(template: RowTemplate, ontology: OntologySchema) -> None:
    """`reference_match_problems`, raised as `RecipeRuleError` for Verify and publish."""
    problems = reference_match_problems(template, ontology)
    if problems:
        raise RecipeRuleError(problems)


def recipe_rule_violations(
    template: RowTemplate,
    ontology: OntologySchema,
    *,
    source_columns: Collection[str] | None = None,
    units: Collection[str] | None = None,
    defaults_handling: Mapping[str, Any] | None = None,
    scheme: HandlingScheme | None = None,
    handling_columns: Mapping[str, str] | None = None,
    declared_columns: Mapping[str, str] | None = None,
    complete: bool = True,
) -> list[str]:
    """Every problem with `template` against `ontology`, in the recipe's order; empty if none.
    `complete=False` at a Map save, where the template may still be half built (see
    `reference_match_problems`).

    `source_columns` (what the source has, when it is known: at Map save, from its header; a run
    has the rows and checks each) and `units` (the recipe's declared units, `defaults.units`)
    judge an element's `handling` bound to a column (ADR-127 decision 3): the column must exist,
    and a bound `originator` or `owning_unit` needs a units list to be checked against.

    `defaults_handling` and `scheme` judge each element's literal handling against the source's own
    marking in every part (ADR-127 decision 3: tighten only; ADR-102 decision 1), not classification
    alone. Without a scheme that check is not made. Any element's `handling` key that `Handling`
    does not have, and a column bound in `provenance`, are refused: neither would be read."""
    problems: list[str] = []
    problems.extend(handling_baseline_problems(template, defaults_handling, scheme))
    problems.extend(reference_match_problems(template, ontology, complete=complete))
    # A column Connect declares as carrying a part must be bound by some element: else the
    # source's rows load at the default marking whatever that column says (rule 3). Judged at save
    # and at run (`declared_columns`); a binding to an undeclared column is refused at save only
    # (`handling_columns`), since a recipe written before Connect declared anything has none.
    # Every entity and link must bind it, links and references included: `on_match: reference` is
    # match-or-create, so on a miss the node is written at its unbound marking, and a held content
    # Document, its `HOLDS` link and a geometry point are written from the row too. A matched node
    # keeps its stored marking whether or not it binds, so binding a reference is harmless. An
    # element with a `when` still has to bind.
    for declared_part, declared_name in (declared_columns or {}).items():
        for element in template_elements(template):
            if handling_bindings(element.handling).get(declared_part) != declared_name:
                name = element.ref if isinstance(element, RecipeEntity) else element.type
                problems.append(
                    f"element {name!r} does not bind {declared_part}, which the source declares "
                    f"in column {declared_name!r}."
                )
    if source_columns is not None:
        for declared_part, declared_name in (handling_columns or {}).items():
            if declared_name not in source_columns:
                problems.append(
                    f"Connect declares {declared_name!r} as the {declared_part} column, which the "
                    f"source does not have (its columns: {', '.join(source_columns)})."
                )
    for element in template_elements(template):
        owner = (
            f"entity {element.ref!r}"
            if isinstance(element, RecipeEntity)
            else f"link {element.type!r}"
        )
        for bound_part, column in handling_bindings(element.handling).items():
            if source_columns is not None and column not in source_columns:
                problems.append(
                    f"{owner} binds handling {bound_part} to column {column!r}, which the source "
                    f"does not have (its columns: {', '.join(source_columns)})."
                )
            if handling_columns is not None and handling_columns.get(bound_part) != column:
                declared_column = handling_columns.get(bound_part)
                problems.append(
                    f"{owner} binds handling {bound_part} to column {column!r}, but Connect "
                    + (
                        f"has declared {declared_column!r} as the column that carries it."
                        if declared_column
                        else "has declared no column for it: declare it there first."
                    )
                )
            if bound_part in ("originator", "owning_unit") and not units:
                problems.append(
                    f"{owner} binds handling {bound_part} to a column, but the recipe declares no "
                    "units: a cell may name only a unit the recipe lists (units), so declare them."
                )
    # ADR-104: a structured transform fills a property through one named part, so a binding that
    # names none (or one the result does not have) is refused here, when the recipe is saved.
    owners = [(entity.ref, entity.properties) for entity in template.entities] + [
        (edge.type, edge.properties) for edge in template.edges
    ]
    for owner, properties in owners:
        for prop, binding in properties.items():
            parsed = transform_name_and_part(binding.transform) if binding.transform else None
            if parsed is None or parsed[0] not in STRUCTURED_PARTS:
                continue
            name, part = parsed
            parts = STRUCTURED_PARTS[name]
            if part is None:
                problems.append(
                    f"{owner}.{prop} uses {name}, which gives {' and '.join(parts)}: choose the "
                    f"part it takes, for example {name}(part={parts[0]})."
                )
            elif part not in parts:
                problems.append(
                    f"{owner}.{prop} asks {name} for {part!r}, which it does not give "
                    f"(its parts: {', '.join(parts)})."
                )
    # ADR-127 decision 2: an edge names its ends by the refs the template declares. A ref that is
    # declared but whose entity is skipped by its `when` on one row is normal (the edge is not
    # written for that row); a ref nothing declares is a template error, never a silent skip.
    declared = {entity.ref for entity in template.entities}
    for edge in template.edges:
        for end, ref in (("from", edge.from_ref), ("to", edge.to_ref)):
            if ref not in declared:
                problems.append(
                    f"{edge.type!r} names {ref!r} as its {end!r} end, but no entity in the row "
                    f"template has that ref (declared: {', '.join(sorted(declared)) or 'none'})."
                )
    # ADR-127 amendment: a Document holds only its own text. A file on a Document would be written
    # as a content Document held by `HOLDS`, which the ontology does not allow from a Document.
    for entity in template.entities:
        if (
            entity.type == "Document"
            and entity.content is not None
            and entity.content.kind in FILE_KINDS
        ):
            problems.append(
                f"{entity.ref!r} is a Document and marks {entity.content.field!r} as a file "
                f"({entity.content.kind}). A Document holds only its own text "
                "(content kind document_text); a file is held by the entity it belongs to "
                "(ADR-094)."
            )
    # ADR-127: the text's place in the media store is the engine's to write, never a column's.
    for entity in template.entities:
        if entity.type == "Document" and entity.content is not None:
            for name in ("object_ref", "media_kind"):
                if name in entity.properties and entity.content.kind == "document_text":
                    problems.append(
                        f"{entity.ref!r} is a Document that holds its own text, which sets "
                        f"{name!r} itself; it cannot be bound to a column."
                    )
    # ADR-127 Amendment 15: `optional` leaves a property out when its cell is empty, so it is
    # only for a property the ontology does not require, and not the one an entity is matched on
    # (no match key, no match); a time binding has no property to leave out.
    for entity in template.entities:
        entity_def = ontology.entity_type(entity.type)
        required = {p.name for p in entity_def.properties if p.required} if entity_def else set()
        for prop, binding in entity.properties.items():
            if not binding.optional:
                continue
            if prop in required:
                problems.append(
                    f"entity {entity.ref!r} marks {prop!r} optional, but {entity.type} requires "
                    f"it: a required property cannot be left out."
                )
            elif prop == entity.match_on:
                problems.append(
                    f"entity {entity.ref!r} marks {prop!r} optional, but it is the property the "
                    "entity is matched on: with no value there is nothing to match."
                )
    for entity in template.entities:
        matched = entity.properties.get(entity.match_on) if entity.match_on else None
        if matched is not None and gives_a_list(matched.transform):
            problems.append(
                f"entity {entity.ref!r} is matched on {entity.match_on!r}, bound through "
                f"{matched.transform!r}, which gives a list: an entity is matched on one value."
            )
    for edge in template.edges:
        edge_def = ontology.edge_type(edge.type)
        required = {p.name for p in edge_def.properties if p.required} if edge_def else set()
        for prop, binding in edge.properties.items():
            if binding.optional and prop in required:
                problems.append(
                    f"{edge.type!r} marks {prop!r} optional, but the type requires it: a required "
                    "property cannot be left out."
                )
        for label, time_binding in (
            ("time", edge.temporal.at if edge.temporal else None),
            ("end", edge.temporal.valid_to if edge.temporal else None),
        ):
            if time_binding is not None and time_binding.optional:
                problems.append(
                    f"{edge.type!r} marks its {label} optional: `optional` applies to a property "
                    "binding only."
                )
    # ADR-127 decision 11: the end of a span is one column of the source (an empty cell is a span
    # still open), so a value, a map or several columns have no meaning there.
    for edge in template.edges:
        span_end = edge.temporal.valid_to if edge.temporal is not None else None
        if span_end is None:
            continue
        one_column = (
            span_end.field is not None
            and not span_end.fields
            and span_end.literal is None
            and not span_end.map
        )
        if not one_column:
            problems.append(
                f"{edge.type!r} binds the end of its span (valid_to) to something other than one "
                "column of the source: name the column that holds it."
            )
        elif source_columns is not None and span_end.field not in source_columns:
            problems.append(
                f"{edge.type!r} binds the end of its span (valid_to) to column {span_end.field!r}, "
                f"which the source does not have (its columns: {', '.join(source_columns)})."
            )
    for edge in template.edges:
        type_def = ontology.edge_type(edge.type)
        if type_def is None:
            problems.append(
                f"{edge.type!r} is not a relationship type in ontology version {ontology.version}."
            )
        elif edge.type == NOT_SAME_AS:
            problems.append(
                f"{edge.type!r} records an analyst's judgement that two nodes differ; no source "
                "records it, so a recipe cannot write it."
            )
        elif type_def.basis != "direct":
            problems.append(
                f"{edge.type!r} is a Probabilistic relationship type. A recipe writes what the "
                "source records, which is Direct (ADR-081); choose a Direct type."
            )
        if edge.content is not None and edge.content.kind in FILE_KINDS:
            problems.append(
                f"{edge.type!r} marks {edge.content.field!r} as a file. A link carries text; a "
                "file is held by an entity (ADR-094): mark it on the entity that holds it."
            )
        if edge.content is not None and edge.temporal is None:
            problems.append(
                f"{edge.type!r} marks {edge.content.field!r} as its text but has no time: a link's "
                "text is kept on its events, and only a link with a time has events (ADR-094)."
            )
    return problems


def holds_content(template: RowTemplate) -> bool:
    """Whether any entity in `template` holds content, which needs the media store."""
    return any(entity.content is not None for entity in template.entities)


def check_recipe_rules(
    template: RowTemplate,
    ontology: OntologySchema,
    *,
    source_columns: Collection[str] | None = None,
    units: Collection[str] | None = None,
    defaults_handling: Mapping[str, Any] | None = None,
    scheme: HandlingScheme | None = None,
    handling_columns: Mapping[str, str] | None = None,
    declared_columns: Mapping[str, str] | None = None,
    complete: bool = True,
) -> None:
    problems = recipe_rule_violations(
        template,
        ontology,
        source_columns=source_columns,
        units=units,
        defaults_handling=defaults_handling,
        scheme=scheme,
        handling_columns=handling_columns,
        declared_columns=declared_columns,
        complete=complete,
    )
    if problems:
        raise RecipeRuleError(problems)
