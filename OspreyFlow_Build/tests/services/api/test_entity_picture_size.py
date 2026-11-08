"""A picture's file size is stored with it when it is attached (ADR-143 Amendment 2 decision 2; the
owner's ruling of 8 November 2026, R4 (a)), so Admin › Datasets counts a case's layer's pictures
in the graph store (`GraphPort.dataset_footprints`) without its object ref leaving the adapter.

Violation caught: the image Document written without `size_bytes`, so every picture counts 0 in
its layer's size. Shown red with the write at attach removed (`entity_pictures._attach`). The
ontology must declare the property, or every attach is refused: the Document is validated against
the default ontology here too."""

from __future__ import annotations

from ontology.validation import validate_properties

from .test_entity_picture_stored_link_ids import HANDLING, ONTOLOGY, READER, _service

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 1000


async def test_an_attached_picture_carries_its_size_in_bytes() -> None:
    service, graph, _ = await _service()
    await service.set("inv-1", "car-1", READER, name="car.png", data=PNG, handling=HANDLING)
    (document,) = [n for n in graph.nodes.values() if n.type == "Document"]
    assert document.properties["media_kind"] == "image"
    assert document.properties["size_bytes"] == len(PNG) == 1008
    (document_type,) = [t for t in ONTOLOGY.entity_types if t.name == "Document"]
    validate_properties(document_type, document.properties)
