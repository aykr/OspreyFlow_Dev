"""One search document per node, and one per Document's text (ADR-150 decision 3).

Built from the node as stored (`IndexFeedSource.nodes_for_index`), through the same `Node` the
Glass receives, with `withhold_sources` applied as for a reader of the node's own datasets: nothing
a reader of the node could not already be sent is searchable (rule 7). A gazetteer's place carries
its name only (ADR-147 Amendments 1 and 3). The access fields are copied verbatim; the query side
filters by them (ADR-149). No cluster or `SAME_AS` field: a cluster id would say hidden members
exist."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

import phonetics
from services.api.identifier_reading import search_alternative

from ontology.handling import is_gazetteer_held, withhold_sources
from schemas.domain import Node, OntologySchema, Principal, PropertyType

#: The indexer's reader: whoever reads the node's own datasets, so what is withheld from such a
#: reader is withheld from the index.
_INDEXER = "search-indexer"
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def text_document_id(node_id: str) -> str:
    return f"text:{node_id}"


def phonetic_codes(text: str) -> list[str]:
    """The Double Metaphone codes (primary and alternate) of each word of `text`, an empty code
    dropped, in order without repeats. The query side calls this same function (ADR-150 decision 3),
    so a name and a query are reduced alike: accents folded, case ignored."""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    codes: list[str] = []
    for word in _TOKEN.findall(folded.lower()):
        for code in phonetics.dmetaphone(word):
            if code and code not in codes:
                codes.append(code)
    return codes


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v.strip()]
    return []


def searchable_fields(
    schema: OntologySchema, entity_type: str
) -> tuple[list[str], list[str], str | None]:
    """The type's identifiers, its names (string properties marked `indexed` that are not
    identifiers and not sensitive, the type-ahead's set, ADR-074) and its date property (the first
    datetime one that is not sensitive), from the ontology, never from a fixed list."""
    entity = schema.entity_type(entity_type)
    if entity is None:
        return [], [], None
    sensitive = {p.name for p in entity.properties if p.sensitivity}
    declared = {p.name: p.type for p in entity.properties}
    strings = (PropertyType.STRING, PropertyType.STRING_LIST)
    identifiers = [
        f
        for f in entity.identifiers
        if f not in sensitive and declared.get(f, PropertyType.STRING) in strings
    ]
    names = [
        p.name
        for p in entity.properties
        if p.indexed and p.type in strings and p.name not in sensitive and p.name not in identifiers
    ]
    date = next(
        (
            p.name
            for p in entity.properties
            if p.type is PropertyType.DATETIME and not p.sensitivity
        ),
        None,
    )
    return identifiers, names, date


def _as_its_reader(node: Node) -> Node:
    reader = Principal(
        id=_INDEXER,
        clearance=node.handling.classification,
        org_unit=node.handling.owning_unit or _INDEXER,
        datasets=list(node.datasets),
    )
    return withhold_sources(node, reader)


def _access(node: Node) -> dict[str, Any]:
    return {
        "datasets": sorted(node.datasets),
        "handling_classification": node.handling.classification,
        "handling_code": node.handling.handling_code,
        "owning_unit": node.handling.owning_unit,
        "originator": node.handling.originator,
    }


def node_document(node: Node, schema: OntologySchema) -> dict[str, Any]:
    """The node's search document (`kind: node`), keyed by its id."""
    seen = _as_its_reader(node)
    identifiers_of, names_of, date_of = searchable_fields(schema, seen.type)
    props = seen.properties
    if is_gazetteer_held(seen):
        identifiers: list[str] = []
        names = _strings(props.get("name"))
    else:
        identifiers = [v for f in identifiers_of for v in _strings(props.get(f))]
        identifiers += [a for v in list(identifiers) if (a := search_alternative(v)) is not None]
        names = [v for f in names_of for v in _strings(props.get(f))]
    date = props.get(date_of) if date_of else None
    return {
        "kind": "node",
        "id": seen.id,
        "node_id": seen.id,
        "type": seen.type,
        **_access(seen),
        "identifiers": list(dict.fromkeys(identifiers)),
        "names": list(dict.fromkeys(names)),
        "names_phonetic": list(dict.fromkeys(c for n in names for c in phonetic_codes(n))),
        "date": date if isinstance(date, str) and date else seen.audit.created_at.isoformat(),
    }


def text_document(node: Node, text: str, text_owning_unit: str) -> dict[str, Any]:
    """A Document's text (`kind: text`): read only by the text's owning unit, so never on the node's
    own document (ADR-150 decision 3)."""
    return {
        "kind": "text",
        "id": text_document_id(node.id),
        "node_id": node.id,
        "type": node.type,
        **_access(node),
        "text_owning_unit": text_owning_unit,
        "text": text,
    }


def fingerprint(document: dict[str, Any]) -> str:
    """The drift check's per-document fingerprint (ADR-150 decision 5): every indexed field."""
    return hashlib.sha256(json.dumps(document, sort_keys=True, default=str).encode()).hexdigest()


def documents_for(
    node: Node, schema: OntologySchema, texts: dict[str, tuple[str, str]]
) -> Iterable[dict[str, Any]]:
    """The node's document, and its text's where it has one (`texts`: node id -> (text, unit))."""
    yield node_document(node, schema)
    if node.id in texts:
        text, unit = texts[node.id]
        yield text_document(node, text, unit)
