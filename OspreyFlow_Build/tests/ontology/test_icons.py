"""A type of node can name the icon drawn inside its shape (ADR-079).

The owner, on 3 October 2026: icons for nodes, by entity type, fixed in the ontology and also
definable by the analyst. This is the ontology half: `icon` is optional, its names are a closed
list held once, in the ontology's JSON Schema, and every type of the default ontology has one. The
Glass holds the matching drawings and a test there pins the two lists equal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ontology.errors import OntologyError
from ontology.loader import _SCHEMA_PATH, load_default_ontology, load_ontology  # noqa: PLC2701


def _names() -> list[str]:
    schema = json.loads(Path(_SCHEMA_PATH).read_text())
    names: list[str] = schema["$defs"]["entity_type"]["properties"]["icon"]["enum"]
    return names


def _doc(**entity: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Person",
        "pole_class": "person",
        "channel": "indigo",
        "shape": "circle",
    }
    base.update(entity)
    return {"version": 1, "entity_types": [base], "edge_types": []}


def _write(tmp_path: Path, doc: dict[str, object]) -> Path:
    path = tmp_path / "ontology.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def test_every_type_of_the_default_ontology_has_an_icon_from_the_list() -> None:
    names = set(_names())
    missing = [e.name for e in load_default_ontology().entity_types if e.icon not in names]
    assert missing == []


def test_the_list_has_no_repeats_and_is_plain_lower_case_words() -> None:
    names = _names()
    assert len(names) == len(set(names))
    # A hyphen joins the words of a name (`parcel-over-wall`, ADR-128 Amendment 3).
    assert all(n.replace("-", "").isalpha() and n == n.lower() for n in names)


def test_an_icon_is_optional(tmp_path: Path) -> None:
    schema = load_ontology(_write(tmp_path, _doc()))
    assert schema.entity_types[0].icon is None


def test_a_listed_icon_is_kept(tmp_path: Path) -> None:
    schema = load_ontology(_write(tmp_path, _doc(icon=_names()[0])))
    assert schema.entity_types[0].icon == _names()[0]


@pytest.mark.parametrize("bad", ["not-an-icon", "Person", "", "https://x.test/a.png"])
def test_a_name_that_is_not_on_the_list_is_refused(tmp_path: Path, bad: str) -> None:
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, _doc(icon=bad)))
