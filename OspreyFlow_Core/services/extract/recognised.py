"""The fast recogniser's findings as the ontology's entities (`06_DECISIONS.md` ADR-098 decision 2).

Stanza answers spans with labels of its own; here each becomes a pending `ExtractionCandidate`
of an ontology type, with its exact span as the locator (the Dossier's `char span` form) and the
hash of the words, named for the recogniser and version that found it. PERSON is a Person, ORG an
Organisation, GPE, LOC and FAC a Location; other labels (dates, money, quantities) are not
proposed. Email addresses (a pattern) and phone numbers (`phonenumbers`' own matcher, valid numbers
only, so a date or a room number is not one) are proposed as Endpoints. A mention found twice is
one finding. Nothing is accepted here (rule 5).

Stanza gives no score, so `confidence` is 1.0 and means only "found"; the reader names the
recogniser instead of showing a percentage.
"""

from __future__ import annotations

import hashlib
import re

import phonenumbers

from conduit_common.identity import new_id
from ports.recognise import RecogniseResult
from schemas.domain import Handling, OntologySchema

from .candidates import ExtractionCandidate

LABEL_TYPES: dict[str, str] = {
    "PERSON": "Person",
    "ORG": "Organisation",
    "GPE": "Location",
    "LOC": "Location",
    "FAC": "Location",
}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def properties_for(entity_type: str, words: str) -> dict[str, str]:
    """An entity's properties from the words naming it: a person's last word is the family name and
    the rest the given names; an endpoint is its value; anything else is named by the words."""
    words = " ".join(words.split())
    if entity_type == "Person":
        *given, family = words.split(" ")
        return {"family_name": family, **({"given_names": " ".join(given)} if given else {})}
    if entity_type == "Endpoint":
        return {"value_raw": words, "value_normalised": words.lower()}
    return {"name": words}


def _candidate(
    entity_type: str,
    properties: dict[str, str],
    start: int,
    end: int,
    text: str,
    document_id: str,
    handling: Handling,
    recogniser: str,
) -> ExtractionCandidate:
    return ExtractionCandidate(
        id=new_id(),
        document_id=document_id,
        entity_type=entity_type,
        properties=properties,
        confidence=1.0,
        model=recogniser,
        locator=f"char span {start}-{end}",
        excerpt_hash=hashlib.sha256(text[start:end].encode("utf-8")).hexdigest(),
        handling=handling,
    )


def recognised_candidates(
    result: RecogniseResult,
    text: str,
    document_id: str,
    handling: Handling,
    ontology: OntologySchema,
    *,
    default_region: str = "GB",
) -> list[ExtractionCandidate]:
    known = {t.name for t in ontology.entity_types}
    found: list[ExtractionCandidate] = []
    seen: set[tuple[str, int, int]] = set()

    def add(entity_type: str, properties: dict[str, str], start: int, end: int) -> None:
        key = (entity_type, start, end)
        if entity_type not in known or key in seen:
            return
        seen.add(key)
        found.append(
            _candidate(
                entity_type, properties, start, end, text, document_id, handling, result.recogniser
            )
        )

    for entity in result.entities:
        entity_type = LABEL_TYPES.get(entity.label)
        if entity_type is None or text[entity.start : entity.end] != entity.text:
            continue
        add(entity_type, properties_for(entity_type, entity.text), entity.start, entity.end)

    for match in _EMAIL.finditer(text):
        address = match.group(0)
        add(
            "Endpoint",
            {"value_raw": address, "value_normalised": address.lower(), "endpoint_kind": "email"},
            match.start(),
            match.end(),
        )
    for number in phonenumbers.PhoneNumberMatcher(
        text, default_region, leniency=phonenumbers.Leniency.VALID
    ):
        add(
            "Endpoint",
            {
                "value_raw": number.raw_string,
                "value_normalised": phonenumbers.format_number(
                    number.number, phonenumbers.PhoneNumberFormat.E164
                ),
                "endpoint_kind": "msisdn",
            },
            number.start,
            number.end,
        )
    return found
