"""The search box looks at names and titles, not only identifiers (ADR-074).

Seen, 3 October 2026, on the Fixture Corp case: typing a person's family name, or an
organisation's name, found nothing, because the type-ahead looks only at each type's identifiers
and its `indexed` string properties and neither `Person.family_name` nor `Organisation.name` was
one. The rule these tests hold is the other half of the same decision: a property the ontology
marks sensitive is never searchable, since matching a prefix against a masked value would let a
reader who may not see it guess it.
"""

from __future__ import annotations

import pytest
from adapters.graph_arcadedb.builders import suggestion_scope
from ontology.loader import load_default_ontology


def _fields(*types: str) -> set[str]:
    _labels, fields = suggestion_scope(load_default_ontology(), tuple(types))
    return set(fields)


def test_a_person_is_found_by_family_name_and_given_names_as_well_as_by_identifier() -> None:
    fields = _fields("Person")
    assert {"family_name", "given_names", "nino", "pnc_id", "prison_number"} <= fields


def test_an_organisation_is_found_by_name_as_well_as_by_reference() -> None:
    assert {"name", "org_ref"} <= _fields("Organisation")


def test_a_document_is_found_by_title() -> None:
    assert "title" in _fields("Document")


def test_a_date_of_birth_is_never_searched() -> None:
    assert "date_of_birth" not in _fields("Person")


@pytest.mark.parametrize("entity", [e.name for e in load_default_ontology().entity_types])
def test_no_property_marked_sensitive_is_searchable(entity: str) -> None:
    ontology = load_default_ontology()
    definition = next(e for e in ontology.entity_types if e.name == entity)
    sensitive = {p.name for p in definition.properties if p.sensitivity}
    assert not (sensitive & _fields(entity))
