"""The fast recogniser's findings as the ontology's entities (`06_DECISIONS.md` ADR-098 decision
2): Stanza's labels mapped to Person, Organisation and Location, emails and phone numbers found by
pattern as Endpoints, each a pending suggestion with its exact span, named for the recogniser."""

from __future__ import annotations

import hashlib

from services.extract.recognised import properties_for, recognised_candidates

from ontology.loader import load_default_ontology
from ports.recognise import RecognisedEntity, RecogniseResult
from schemas.domain import Handling

HANDLING = Handling(
    classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
)
TEXT = (
    "Kenneth Lay met Enron staff in Houston on Monday; "
    "write to ken.lay@enron.com or call +44 7911 123456."
)


def _result(*entities: tuple[str, str]) -> RecogniseResult:
    found = []
    for label, words in entities:
        start = TEXT.index(words)
        found.append(RecognisedEntity(label=label, text=words, start=start, end=start + len(words)))
    return RecogniseResult(recogniser="stanza:1.10.1", entities=found)


def _candidates(result: RecogniseResult):  # type: ignore[no-untyped-def]
    return recognised_candidates(result, TEXT, "doc-1", HANDLING, load_default_ontology())


def test_labels_become_people_organisations_and_places_and_others_are_left_out() -> None:
    found = _candidates(
        _result(("PERSON", "Kenneth Lay"), ("ORG", "Enron"), ("GPE", "Houston"), ("DATE", "Monday"))
    )
    by_type = {
        (c.entity_type, c.properties.get("name") or c.properties.get("family_name")) for c in found
    }
    assert ("Person", "Lay") in by_type
    assert ("Organisation", "Enron") in by_type
    assert ("Location", "Houston") in by_type
    assert not any("Monday" in str(c.properties) for c in found)


def test_each_finding_has_its_exact_span_hash_and_names_the_recogniser() -> None:
    (person,) = [
        c for c in _candidates(_result(("PERSON", "Kenneth Lay"))) if c.entity_type == "Person"
    ]
    start = TEXT.index("Kenneth Lay")
    assert person.locator == f"char span {start}-{start + 11}"
    assert person.excerpt_hash == hashlib.sha256(b"Kenneth Lay").hexdigest()
    assert person.model == "stanza:1.10.1"
    assert person.handling == HANDLING
    assert person.properties == {"family_name": "Lay", "given_names": "Kenneth"}


def test_emails_and_phone_numbers_are_found_by_pattern_as_endpoints() -> None:
    endpoints = [c for c in _candidates(_result()) if c.entity_type == "Endpoint"]
    values = {(c.properties["endpoint_kind"], c.properties["value_normalised"]) for c in endpoints}
    assert ("email", "ken.lay@enron.com") in values
    assert ("msisdn", "+447911123456") in values
    for c in endpoints:
        start, end = (int(x) for x in c.locator.removeprefix("char span ").split("-"))
        assert TEXT[start:end] == c.properties["value_raw"]


def test_a_mention_found_twice_is_one_finding() -> None:
    found = _candidates(_result(("PERSON", "Kenneth Lay"), ("PERSON", "Kenneth Lay")))
    assert len([c for c in found if c.entity_type == "Person"]) == 1


def test_a_date_or_a_short_number_is_not_a_phone() -> None:
    text = "Meet on 06/10/2026 at 10:30, room 4512."
    result = RecogniseResult(recogniser="stanza:1.10.1", entities=[])
    found = recognised_candidates(result, text, "doc-1", HANDLING, load_default_ontology())
    assert [c for c in found if c.entity_type == "Endpoint"] == []


def test_properties_for_marked_or_recognised_words() -> None:
    assert properties_for("Person", "Dana  MERCER") == {
        "family_name": "MERCER",
        "given_names": "Dana",
    }
    assert properties_for("Organisation", "Enron Corp") == {"name": "Enron Corp"}
    assert (
        properties_for("Endpoint", "Ken.Lay@Enron.com")["value_normalised"] == "ken.lay@enron.com"
    )
