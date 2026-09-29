"""The extraction profile and its schema generator — `09_INGEST_STUDIO.md` §4: "For unstructured
sources, stage 3 is an **extraction profile**: which POLE classes and concrete types to extract,
as a checklist over the ontology; the schema handed to the model for constrained decoding,
generated from that selection; per-type confidence floor...; which Knowledge Adapters run over
extracted values." `packages/schemas/model.py`'s own docstring names this exact generator as
"Stage 6's schema to design" — `ExtractionRequest.json_schema` was deliberately left
caller-supplied and schema-agnostic through Stages 1–5 (ADR-005) for exactly this to fill in.

A profile selects entity type *names*, not POLE classes directly — an ontology entity type
already declares its own `pole_class` (`packages/ontology/default.yaml`), so "checklist over the
ontology, grouped by POLE class" is a Glass-side presentation concern over the same flat list of
type names this module takes; nothing here needs a separate POLE-class grouping abstraction of
its own.

**Deliberately not built: a persisted, versioned profile registry** the way `studio_recipes`
gives structured recipes their own (`09_INGEST_STUDIO.md` §6). Nothing in the Phase 6 outcome
bullet ("extraction profiles in the studio: POLE-class checklist generating the
constrained-decoding schema, per-type confidence floors, adapter selection") asks for publish/
version/schedule semantics the way a recipe explicitly does — only the schema-generation
capability. A profile here is inline, caller-supplied configuration on each extraction run, not a
database row with its own lifecycle — a disclosed scoping choice, not an oversight.

**Deliberately not built: entity `identifiers`.** Only an entity type's declared `properties` are
offered to the model — `identifiers` (`nino`, `pnc_id`, `e164`, ...) are exactly the
deterministically-matchable fields a *structured* recipe's `match_on`/`on_match: reference` exist
for (`01_DOMAIN_MODEL.md` §4: "deterministic identifiers bypass the probabilistic path"), and are
not the kind of value free prose reliably renders in a directly-extractable form.
"""

from __future__ import annotations

from typing import Any

from schemas.domain import EntityTypeDef, OntologySchema, PropertyType

DEFAULT_CONFIDENCE_FLOOR = 0.5

#: One JSON Schema fragment per `PropertyType` — `date`/`datetime` become `string` with a
#: `format` hint (JSON Schema has no native temporal type); `enum` carries its own closed
#: `values` list straight through, the same closed-vocabulary discipline ADR-018 already applies
#: to Knowledge Adapters, just expressed as a schema constraint instead of a registry lookup.
_STRING_LIST_SCHEMA: dict[str, Any] = {"type": "array", "items": {"type": "string"}}


def _json_type_for(prop_type: PropertyType, values: list[str] | None) -> dict[str, Any]:
    if prop_type is PropertyType.STRING:
        return {"type": "string"}
    if prop_type is PropertyType.STRING_LIST:
        return dict(_STRING_LIST_SCHEMA)
    if prop_type is PropertyType.DATE:
        return {"type": "string", "format": "date"}
    if prop_type is PropertyType.DATETIME:
        return {"type": "string", "format": "date-time"}
    if prop_type is PropertyType.INTEGER:
        return {"type": "integer"}
    if prop_type is PropertyType.FLOAT:
        return {"type": "number"}
    if prop_type is PropertyType.BOOLEAN:
        return {"type": "boolean"}
    if prop_type is PropertyType.ENUM:
        return {"type": "string", "enum": list(values or [])}
    raise AssertionError(f"unhandled PropertyType: {prop_type!r}")  # pragma: no cover


class ExtractionProfileError(Exception):
    """Raised by `build_schema` for a profile naming an entity type the loaded ontology does not
    declare — checked at schema-build time, the same "fail before the model call, not after"
    discipline `packages/ontology/loader.py`'s own business-rule checks follow for the ontology
    itself."""


class ExtractionProfile:
    """`entity_types` are ontology entity type names, e.g. `["Person", "Event"]` — the "checklist"
    (`09_INGEST_STUDIO.md` §4). `confidence_floors` overrides `default_confidence_floor` per type;
    a type not listed there uses the default. `adapters` maps an entity type name to
    `{property_name: knowledge_adapter_name}` — resolved through the same closed registry
    `services/ingest/transforms.py.apply_transform` already uses, not a second one."""

    def __init__(
        self,
        entity_types: list[str],
        *,
        default_confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
        confidence_floors: dict[str, float] | None = None,
        adapters: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.entity_types = entity_types
        self.default_confidence_floor = default_confidence_floor
        self.confidence_floors = confidence_floors or {}
        self.adapters = adapters or {}

    def confidence_floor_for(self, entity_type: str) -> float:
        return self.confidence_floors.get(entity_type, self.default_confidence_floor)


def entity_type_def(ontology: OntologySchema, name: str) -> EntityTypeDef:
    for entity_type in ontology.entity_types:
        if entity_type.name == name:
            return entity_type
    raise ExtractionProfileError(
        f"extraction profile names entity type {name!r}, which the loaded ontology "
        f"(version {ontology.version}) does not declare"
    )


def build_schema(profile: ExtractionProfile, ontology: OntologySchema) -> dict[str, Any]:
    """One array-valued top-level property per selected entity type, each item shaped from that
    type's declared `properties` plus a model-reported `confidence` (`01_DOMAIN_MODEL.md` §2.1:
    "`extraction_confidence` ... 0..1, model-reported") — the per-type confidence floor
    (`09_INGEST_STUDIO.md` §4) is applied afterwards in `candidates.py`, against this same field,
    not baked into the schema itself. Every selected type is `required` at the top level so the
    model always emits the key, even as an empty array, matching the golden set's own
    `WITNESS_STATEMENT_SCHEMA` precedent (`tests/scenarios/fixtures/witness_statement.py`) rather
    than leaving "the model didn't mention this type" ambiguous between "found nothing" and
    "omitted the key".

    `confidence` deliberately has no `minimum`/`maximum` bound in the schema, found live against
    the real CI-pinned model, not assumed: the small model this ships against reports confidence
    on a 0–100 scale as often as 0–1 (`qwen2.5:0.5b-instruct` returned `97` for a person it was
    confident about). `adapters/model_litellm/client.py`'s constrained-decoding validator rejects
    and *retries the whole call* against a schema bound that value fails — three failed attempts
    raise `ExtractionFailedError` and the run produces nothing at all, which is a strictly worse
    failure mode than an out-of-range confidence value candidates.py can normalise defensively.
    `candidates.py`'s own docstring has the normalisation this schema's own permissiveness makes
    necessary."""
    type_schemas: dict[str, Any] = {}
    for name in profile.entity_types:
        entity_type = entity_type_def(ontology, name)
        item_properties: dict[str, Any] = {
            prop.name: _json_type_for(prop.type, prop.values) for prop in entity_type.properties
        }
        item_properties["confidence"] = {"type": "number"}
        required = [p.name for p in entity_type.properties if p.required] + ["confidence"]
        type_schemas[name] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": item_properties,
                "required": required,
                "additionalProperties": False,
            },
        }

    return {
        "type": "object",
        "properties": type_schemas,
        "required": list(profile.entity_types),
        "additionalProperties": False,
    }
