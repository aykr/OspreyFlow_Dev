"""Property and edge-endpoint validation — `01_DOMAIN_MODEL.md` §2:
"validated against the ontology's property definitions"."""

from __future__ import annotations

import pytest

from ontology.errors import OntologyError
from ontology.validation import validate_edge_endpoints, validate_properties
from schemas.domain import EdgeTypeDef, EntityTypeDef, PropertyDef

PERSON = EntityTypeDef(
    name="Person",
    pole_class="person",
    channel="indigo",
    shape="circle",
    identifiers=["nino"],
    properties=[
        PropertyDef(name="family_name", type="string", required=True),
        PropertyDef(name="age", type="integer"),
        PropertyDef(name="tags", type="string[]"),
        PropertyDef(name="risk", type="enum", values=["low", "high"]),
    ],
)

USES = EdgeTypeDef(name="USES", from_types=["Person"], to_types=["Endpoint", "Device"])
MENTIONED_IN = EdgeTypeDef(name="MENTIONED_IN", from_types=["*"], to_types=["Document"])


def test_missing_required_property_is_rejected() -> None:
    with pytest.raises(OntologyError, match="family_name"):
        validate_properties(PERSON, {})


def test_unknown_property_key_is_rejected() -> None:
    with pytest.raises(OntologyError, match="alien_field"):
        validate_properties(PERSON, {"family_name": "Doe", "alien_field": "x"})


def test_identifier_key_is_accepted_without_a_declared_type() -> None:
    validate_properties(PERSON, {"family_name": "Doe", "nino": "AB123456C"})


def test_wrong_type_is_rejected() -> None:
    with pytest.raises(OntologyError, match="age"):
        validate_properties(PERSON, {"family_name": "Doe", "age": "not a number"})


def test_string_list_type_checked_element_wise() -> None:
    with pytest.raises(OntologyError, match="tags"):
        validate_properties(PERSON, {"family_name": "Doe", "tags": ["ok", 5]})


def test_enum_rejects_a_value_outside_the_declared_set() -> None:
    with pytest.raises(OntologyError, match="risk"):
        validate_properties(PERSON, {"family_name": "Doe", "risk": "extreme"})


def test_valid_properties_pass() -> None:
    validate_properties(
        PERSON, {"family_name": "Doe", "age": 40, "tags": ["a", "b"], "risk": "low"}
    )


def test_edge_endpoint_type_mismatch_is_rejected() -> None:
    with pytest.raises(OntologyError, match="Vehicle"):
        validate_edge_endpoints(USES, source_type="Person", target_type="Vehicle")


def test_edge_endpoint_within_declared_set_passes() -> None:
    validate_edge_endpoints(USES, source_type="Person", target_type="Endpoint")


def test_wildcard_endpoint_accepts_anything() -> None:
    validate_edge_endpoints(MENTIONED_IN, source_type="Vehicle", target_type="Document")
