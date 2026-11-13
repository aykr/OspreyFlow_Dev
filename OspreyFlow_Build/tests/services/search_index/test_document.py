"""ADR-150 decision 3: the search document a node and a Document's text get, offline."""

from __future__ import annotations

from datetime import UTC, datetime

from ontology.loader import load_default_ontology
from schemas.domain import AuditStub, Handling, Node, Provenance, ProvenanceState, SourceRef
from services.search_index.document import (
    node_document,
    phonetic_codes,
    searchable_fields,
    text_document,
)

ONTOLOGY = load_default_ontology()
WHEN = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = SourceRef(document_id="files/people.csv", locator="row 1", excerpt_hash="e" * 64)


def _node(type_: str, properties: dict, datasets: list[str], **handling: str) -> Node:
    return Node(
        id="n-1",
        type=type_,
        properties=properties,
        provenance=Provenance(state=ProvenanceState.ASSERTED, sources=[SOURCE], first_seen=WHEN),
        handling=Handling(
            classification=handling.get("classification", "SECRET"),
            handling_code=handling.get("code", "P"),
            originator="unit-9",
            owning_unit="unit-7",
        ),
        audit=AuditStub(created_at=WHEN, created_by="loader-1"),
        datasets=datasets,
    )


def test_the_names_are_the_ontologys_indexed_and_not_sensitive_strings() -> None:
    identifiers, names, date = searchable_fields(ONTOLOGY, "Person")
    assert {"family_name", "given_names"} <= set(names)
    assert {"nino", "pnc_id"} <= set(identifiers)
    assert "date_of_birth" not in names + identifiers
    assert date is None
    assert searchable_fields(ONTOLOGY, "Document")[2] == "sent_at"


def test_a_nodes_document_copies_its_access_fields_and_holds_no_cluster_or_source() -> None:
    node = _node(
        "Person",
        {"family_name": "Smyth", "given_names": "Muhammad", "nino": "AB123456C",
         "date_of_birth": "1980-01-01"},
        ["Z9", "Z1"],
    )  # fmt: skip
    doc = node_document(node, ONTOLOGY)
    assert doc["kind"] == "node" and doc["id"] == doc["node_id"] == "n-1"
    assert doc["datasets"] == ["Z1", "Z9"]
    assert (doc["handling_classification"], doc["handling_code"]) == ("SECRET", "P")
    assert (doc["owning_unit"], doc["originator"]) == ("unit-7", "unit-9")
    assert "AB123456C" in doc["identifiers"]
    assert {"Smyth", "Muhammad"} <= set(doc["names"])
    assert "1980-01-01" not in str(doc), "a sensitive property is never indexed"
    assert not {"cluster", "same_as", "provenance", "sources", "text"} & set(doc)
    assert {"SM0", "XMT", "MHMT"} <= set(doc["names_phonetic"])
    assert doc["date"] == WHEN.isoformat()


def test_a_gazetteer_place_carries_its_name_alone() -> None:
    """Name only (ADR-147 Amendments 1 and 3): not even an identifier withholding would leave, such
    as a postcode, which no gazetteer rule withholds from a reader."""
    place = _node("Location", {"name": "Old Bailey", "osm_id": "w123", "uprn": "100023",
                               "postcode": "EC4M 7EH"}, ["gazetteer-osm-london"])  # fmt: skip
    doc = node_document(place, ONTOLOGY)
    assert doc["names"] == ["Old Bailey"] and doc["identifiers"] == []
    assert not {"w123", "100023", "EC4M 7EH"} & set(str(doc).split("'"))


def test_a_documents_text_is_a_document_of_its_own_read_by_its_unit() -> None:
    node = _node("Document", {"title": "Statement", "sent_at": "2026-02-03T10:00:00+00:00"}, ["Z1"])
    doc = node_document(node, ONTOLOGY)
    assert "text" not in doc and doc["date"] == "2026-02-03T10:00:00+00:00"
    text = text_document(node, "He met Mohamad at the docks.", "unit-3")
    assert text["kind"] == "text" and text["id"] == "text:n-1" and text["node_id"] == "n-1"
    assert text["text_owning_unit"] == "unit-3"
    assert (text["handling_classification"], text["datasets"]) == ("SECRET", ["Z1"])


def test_the_phonetic_codes_fold_spelling_variants_together() -> None:
    assert phonetic_codes("Mohammed") == phonetic_codes("Muhammad") == phonetic_codes("Mohamad")
    assert set(phonetic_codes("Smith")) == set(phonetic_codes("Smyth"))
    assert phonetic_codes("Zoë") == phonetic_codes("Zoe")
    assert "" not in phonetic_codes("Smith")
