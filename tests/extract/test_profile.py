"""`services/extract/profile.py` — `docs/09_INGEST_STUDIO.md` §4. Runs against the real default
ontology (`packages/ontology/default.yaml`), the same discipline `tests/resolve/test_resolver.py`
already established for a schema-generation module with no live infra needed.
"""

from __future__ import annotations

import pytest
from services.extract.profile import (
    DEFAULT_CONFIDENCE_FLOOR,
    ExtractionProfile,
    ExtractionProfileError,
    build_schema,
)

from ontology.loader import load_default_ontology

ONTOLOGY = load_default_ontology()


def test_build_schema_has_one_array_property_per_selected_entity_type() -> None:
    profile = ExtractionProfile(["Person", "Event"])
    schema = build_schema(profile, ONTOLOGY)

    assert set(schema["properties"]) == {"Person", "Event"}
    assert schema["required"] == ["Person", "Event"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["Person"]["type"] == "array"


def test_person_item_schema_carries_its_declared_properties_and_confidence() -> None:
    profile = ExtractionProfile(["Person"])
    schema = build_schema(profile, ONTOLOGY)

    item = schema["properties"]["Person"]["items"]
    assert item["type"] == "object"
    assert item["additionalProperties"] is False
    assert set(item["properties"]) == {
        "family_name",
        "given_names",
        "date_of_birth",
        "aliases",
        "confidence",
    }
    # `family_name` is `required: true` on the ontology's own `Person` definition; the others
    # are not, so only it plus `confidence` are required here.
    assert set(item["required"]) == {"family_name", "confidence"}
    # No `minimum`/`maximum` — found live against the real CI-pinned model, not assumed: a small
    # model can report confidence outside 0..1 (e.g. a 0-100 scale), and a schema bound the model
    # fails makes constrained decoding retry-and-fail the whole call rather than merely
    # miscalibrate (`build_schema`'s own docstring has the full finding; `candidates.py`
    # normalises defensively instead).
    assert item["properties"]["confidence"] == {"type": "number"}


def test_property_type_mapping_covers_every_kind_person_and_endpoint_use() -> None:
    profile = ExtractionProfile(["Person", "Endpoint"])
    schema = build_schema(profile, ONTOLOGY)

    person_props = schema["properties"]["Person"]["items"]["properties"]
    assert person_props["family_name"] == {"type": "string"}
    assert person_props["date_of_birth"] == {"type": "string", "format": "date"}
    assert person_props["aliases"] == {"type": "array", "items": {"type": "string"}}

    endpoint_props = schema["properties"]["Endpoint"]["items"]["properties"]
    assert endpoint_props["endpoint_kind"] == {
        "type": "string",
        "enum": ["msisdn", "imsi", "email", "handle", "iban", "card"],
    }


def test_event_has_no_declared_properties_but_still_gets_a_confidence_field() -> None:
    """`Event` (`packages/ontology/default.yaml`) declares no `properties` at all — the schema
    generator must not choke on an entity type with nothing beyond its POLE/channel/shape."""
    profile = ExtractionProfile(["Event"])
    schema = build_schema(profile, ONTOLOGY)

    item = schema["properties"]["Event"]["items"]
    assert set(item["properties"]) == {"confidence"}
    assert item["required"] == ["confidence"]


def test_unknown_entity_type_raises_at_schema_build_time() -> None:
    profile = ExtractionProfile(["NotARealType"])
    with pytest.raises(ExtractionProfileError):
        build_schema(profile, ONTOLOGY)


def test_identifiers_are_not_offered_to_the_model() -> None:
    """`Person.identifiers` (`nino`, `pnc_id`, ...) are deliberately excluded — `profile.py`'s own
    module docstring has the reasoning."""
    profile = ExtractionProfile(["Person"])
    schema = build_schema(profile, ONTOLOGY)

    item_properties = schema["properties"]["Person"]["items"]["properties"]
    assert "nino" not in item_properties
    assert "pnc_id" not in item_properties


def test_confidence_floor_defaults_and_overrides() -> None:
    profile = ExtractionProfile(["Person", "Event"], confidence_floors={"Event": 0.9})

    assert profile.confidence_floor_for("Person") == DEFAULT_CONFIDENCE_FLOOR
    assert profile.confidence_floor_for("Event") == 0.9
