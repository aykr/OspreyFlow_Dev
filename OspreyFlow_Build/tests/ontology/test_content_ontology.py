"""ADR-094 step 2: the ontology that holds content. Every content item is a `Document` with a
`media_kind`; a file is kept in the object store and the Document carries only its reference; content
held by an entity is linked to it by `HOLDS`, which is Direct. Version 12: every recipe pinned to 11
is flagged once to be re-pinned (spec 09 §4)."""

from __future__ import annotations

import pytest

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology
from ontology.validation import validate_edge_endpoints, validate_properties

ONTOLOGY = load_default_ontology()


def test_the_ontology_is_version_12() -> None:
    assert ONTOLOGY.version == 12


def test_a_document_declares_its_media_kind_and_its_file_reference() -> None:
    document = ONTOLOGY.entity_type("Document")
    assert document is not None
    validate_properties(document, {"title": "Photo", "media_kind": "image", "object_ref": "media/ab12.jpg"})
    with pytest.raises(OntologyError):
        validate_properties(document, {"media_kind": "hologram"})


@pytest.mark.parametrize("holder", ["Device", "Endpoint", "Person", "Organisation"])
def test_holds_links_a_holder_to_a_document_and_is_direct(holder: str) -> None:
    holds = ONTOLOGY.edge_type("HOLDS")
    assert holds is not None and holds.basis == "direct" and holds.directed
    validate_edge_endpoints(holds, source_type=holder, target_type="Document")


def test_holds_refuses_an_end_it_does_not_declare() -> None:
    holds = ONTOLOGY.edge_type("HOLDS")
    assert holds is not None
    with pytest.raises(OntologyError):
        validate_edge_endpoints(holds, source_type="Location", target_type="Document")
    with pytest.raises(OntologyError):
        validate_edge_endpoints(holds, source_type="Device", target_type="Person")
