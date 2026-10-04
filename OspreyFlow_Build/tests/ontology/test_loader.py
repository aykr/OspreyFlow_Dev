"""Ontology loader — `spec/01_DOMAIN_MODEL.md` §1, `spec/06_DECISIONS.md` ADR-006.

Written before `packages/ontology/loader.py` existed, per the Phase 1 plan's
test-first ordering.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology, load_ontology
from schemas.domain import NOT_SAME_AS, SAME_AS, PoleClass


def _write(tmp_path: Path, doc: dict[str, object]) -> Path:
    path = tmp_path / "ontology.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def _minimal_doc(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "version": 1,
        "entity_types": [
            {"name": "Person", "pole_class": "person", "channel": "indigo", "shape": "circle"},
        ],
        "edge_types": [],
    }
    doc.update(overrides)
    return doc


def test_default_ontology_loads_with_nine_entity_types() -> None:
    schema = load_default_ontology()
    assert len(schema.entity_types) == 9
    assert {e.pole_class for e in schema.entity_types} <= set(PoleClass)


def test_default_ontology_channels_are_all_distinct() -> None:
    schema = load_default_ontology()
    channels = [e.channel for e in schema.entity_types]
    assert len(channels) == len(set(channels))


def test_loader_always_injects_same_as_and_not_same_as() -> None:
    schema = load_default_ontology()
    names = {e.name for e in schema.edge_types}
    assert SAME_AS in names
    assert NOT_SAME_AS in names
    for system_name in (SAME_AS, NOT_SAME_AS):
        edge = schema.edge_type(system_name)
        assert edge is not None
        assert edge.system is True
        assert edge.from_types == ["*"]
        assert edge.to_types == ["*"]
        assert edge.directed is False


def test_loader_allows_sharing_a_channel_with_a_distinct_shape(tmp_path: Path) -> None:
    """Sharing a hue is permitted — shape is always carried alongside it, so
    two entity types with the same channel and different shapes remain
    distinguishable (`01_DOMAIN_MODEL.md` §1.1, rule 2)."""
    doc = _minimal_doc(
        entity_types=[
            {"name": "Person", "pole_class": "person", "channel": "indigo", "shape": "circle"},
            {"name": "Suspect", "pole_class": "person", "channel": "indigo", "shape": "square"},
        ]
    )
    schema = load_ontology(_write(tmp_path, doc))
    assert {e.name for e in schema.entity_types} == {"Person", "Suspect"}


def test_loader_rejects_sharing_both_channel_and_shape(tmp_path: Path) -> None:
    doc = _minimal_doc(
        entity_types=[
            {"name": "Person", "pole_class": "person", "channel": "indigo", "shape": "circle"},
            {"name": "Suspect", "pole_class": "person", "channel": "indigo", "shape": "circle"},
        ]
    )
    with pytest.raises(OntologyError, match="more than one entity type"):
        load_ontology(_write(tmp_path, doc))


def test_loader_rejects_unknown_channel(tmp_path: Path) -> None:
    doc = _minimal_doc(
        entity_types=[
            {"name": "Person", "pole_class": "person", "channel": "crimson", "shape": "circle"},
        ]
    )
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, doc))


def test_loader_rejects_unknown_pole_class(tmp_path: Path) -> None:
    doc = _minimal_doc(
        entity_types=[
            {"name": "Person", "pole_class": "suspect", "channel": "indigo", "shape": "circle"},
        ]
    )
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, doc))


def test_loader_allows_a_tenth_entity_type_sharing_a_channel_with_a_new_shape(
    tmp_path: Path,
) -> None:
    """A deployment needing a tenth entity type gives it an existing channel
    and a distinct shape — the escape hatch `01_DOMAIN_MODEL.md` §1.1
    describes, not a rejected configuration."""
    channels = ["ochre", "rose", "plum", "violet", "indigo", "azure", "cyan", "jade", "moss"]
    entity_types = [
        {"name": f"Type{i}", "pole_class": "object", "channel": ch, "shape": "square"}
        for i, ch in enumerate(channels)
    ]
    entity_types.append(
        {"name": "TypeTen", "pole_class": "object", "channel": "ochre", "shape": "triangle"}
    )
    doc = _minimal_doc(entity_types=entity_types)
    schema = load_ontology(_write(tmp_path, doc))
    assert len(schema.entity_types) == 10


def test_loader_rejects_redefined_same_as(tmp_path: Path) -> None:
    doc = _minimal_doc(
        edge_types=[
            {
                "name": "SAME_AS",
                "from": ["Person"],
                "to": ["Person"],
                "directed": True,
                "basis": "direct",
            }
        ]
    )
    with pytest.raises(OntologyError, match="system edge type"):
        load_ontology(_write(tmp_path, doc))


def test_loader_rejects_edge_type_with_unknown_endpoint(tmp_path: Path) -> None:
    doc = _minimal_doc(
        edge_types=[
            {"name": "OWNS", "from": ["Person"], "to": ["Spaceship"], "basis": "direct"}
        ],
    )
    with pytest.raises(OntologyError, match="Spaceship"):
        load_ontology(_write(tmp_path, doc))


def test_loader_rejects_duplicate_entity_type_names(tmp_path: Path) -> None:
    doc = _minimal_doc(
        entity_types=[
            {"name": "Person", "pole_class": "person", "channel": "indigo", "shape": "circle"},
            {"name": "Person", "pole_class": "object", "channel": "cyan", "shape": "square"},
        ]
    )
    with pytest.raises(OntologyError, match="duplicate entity type"):
        load_ontology(_write(tmp_path, doc))


def test_loader_rejects_malformed_yaml_against_json_schema(tmp_path: Path) -> None:
    doc = _minimal_doc()
    del doc["version"]
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, doc))


def test_edge_type_wildcard_endpoint_is_allowed(tmp_path: Path) -> None:
    doc = _minimal_doc(
        edge_types=[
            {"name": "MENTIONED_IN", "from": ["*"], "to": ["Person"], "basis": "direct"}
        ],
    )
    schema = load_ontology(_write(tmp_path, doc))
    assert schema.edge_type("MENTIONED_IN") is not None
