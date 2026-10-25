"""What a recipe may declare, checked when it is saved and again when it runs.

ADR-081 step D (and Amendment 1 item 7): a relationship the Ingest Studio writes from the source's
own records is **Direct**, because a loaded record stands behind it. A recipe that names a
Probabilistic type is refused, as is one naming `SAME_AS` (the resolution engine's alone) or
`NOT_SAME_AS` (an analyst's judgement), or a type the ontology does not have. No expression
language is involved (rule 8): each rule reads only what the recipe declares.
"""

from __future__ import annotations

from services.ingest.transforms import STRUCTURED_PARTS, transform_name_and_part

from schemas.domain import NOT_SAME_AS, OntologySchema
from schemas.ingest import RowTemplate

FILE_KINDS = frozenset({"image_file", "video_file"})


class RecipeRuleError(Exception):
    """A recipe declares something the rules above refuse; the message names each problem."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def recipe_rule_violations(template: RowTemplate, ontology: OntologySchema) -> list[str]:
    """Every problem with `template` against `ontology`, in the recipe's order; empty if none."""
    problems: list[str] = []
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


def check_recipe_rules(template: RowTemplate, ontology: OntologySchema) -> None:
    problems = recipe_rule_violations(template, ontology)
    if problems:
        raise RecipeRuleError(problems)
