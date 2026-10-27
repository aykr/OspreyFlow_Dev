"""An entity type may choose its icon by the value of one enum property (ADR-128 Decision 4, B7).

The ontology declares, per type, `icon_by_value`: the one enum property it reads, and a map from
some of that property's values to glyph names. The rules, each with the test that would fail
without it:

- The six glyphs ADR-128 Amendment 3 adds are on the closed list:
  `test_the_six_new_glyphs_are_on_the_list`.
- A glyph the list does not hold is refused, at load for a core file and at composition for a pack
  (a pack is not run through the JSON Schema): the `test_a_map_naming_*` and `test_a_pack_*` tests.
- The property must be one of the type's own, must be an enum, and each mapped value must be one
  of its values: `test_a_map_on_*`, `test_a_value_that_is_not_in_the_enum_*`.
- The shipped maps are exactly the ones the amendment names, and `Endpoint`'s type icon is the
  neutral `device`: `test_the_default_ontology_maps_endpoint_kind`,
  `test_the_niem_pack_maps_incident_category`.
- Nothing is bumped, so no recipe is flagged: `test_no_version_was_bumped_for_this`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from ontology.errors import OntologyError
from ontology.loader import _SCHEMA_PATH, load_default_ontology, load_ontology  # noqa: PLC2701
from ontology.packs import compose_with_packs
from schemas.domain import EntityTypeDef

_NEW_GLYPHS = {"keypad", "account", "parcel-over-wall", "clash", "crowd", "magnifier"}


def _names() -> list[str]:
    schema = json.loads(Path(_SCHEMA_PATH).read_text())
    names: list[str] = schema["$defs"]["entity_type"]["properties"]["icon"]["enum"]
    return names


def _entity(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Endpoint",
        "pole_class": "object",
        "channel": "cyan",
        "shape": "hexagon",
        "icon": "device",
        "properties": [
            {"name": "endpoint_kind", "type": "enum", "values": ["msisdn", "email", "handle"]},
            # Holds `values` without being an enum: only the type check can refuse a map.
            {"name": "value_raw", "type": "string", "values": ["msisdn"]},
        ],
        "icon_by_value": {
            "property": "endpoint_kind",
            "icons": {"msisdn": "phone", "handle": "keypad"},
        },
    }
    base.update(extra)
    return base


def _write(tmp_path: Path, entity: dict[str, Any]) -> Path:
    path = tmp_path / "ontology.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "entity_types": [entity], "edge_types": []}))
    return path


def test_the_six_new_glyphs_are_on_the_list() -> None:
    names = _names()
    assert _NEW_GLYPHS <= set(names)
    assert len(names) == 26


def test_a_valid_map_is_kept(tmp_path: Path) -> None:
    schema = load_ontology(_write(tmp_path, _entity()))
    declared = schema.entity_types[0].icon_by_value
    assert declared is not None
    assert declared.property == "endpoint_kind"
    assert declared.icons == {"msisdn": "phone", "handle": "keypad"}


def test_a_map_is_optional(tmp_path: Path) -> None:
    entity = _entity()
    del entity["icon_by_value"]
    assert load_ontology(_write(tmp_path, entity)).entity_types[0].icon_by_value is None


@pytest.mark.parametrize("bad", ["not-an-icon", "Phone", "", "https://x.test/a.png"])
def test_a_map_naming_a_glyph_not_on_the_list_is_refused(tmp_path: Path, bad: str) -> None:
    entity = _entity(icon_by_value={"property": "endpoint_kind", "icons": {"msisdn": bad}})
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, entity))


def test_a_map_on_a_property_the_type_does_not_have_is_refused(tmp_path: Path) -> None:
    entity = _entity(icon_by_value={"property": "kind", "icons": {"msisdn": "phone"}})
    with pytest.raises(OntologyError, match="kind"):
        load_ontology(_write(tmp_path, entity))


def test_a_map_on_a_property_that_is_not_an_enum_is_refused(tmp_path: Path) -> None:
    entity = _entity(icon_by_value={"property": "value_raw", "icons": {"msisdn": "phone"}})
    with pytest.raises(OntologyError, match="not an enum"):
        load_ontology(_write(tmp_path, entity))


def test_a_value_that_is_not_in_the_enum_is_refused(tmp_path: Path) -> None:
    entity = _entity(icon_by_value={"property": "endpoint_kind", "icons": {"fax": "phone"}})
    with pytest.raises(OntologyError, match="fax"):
        load_ontology(_write(tmp_path, entity))


def test_an_empty_map_is_refused(tmp_path: Path) -> None:
    entity = _entity(icon_by_value={"property": "endpoint_kind", "icons": {}})
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, entity))


def test_an_unknown_key_in_the_map_is_refused(tmp_path: Path) -> None:
    entity = _entity(
        icon_by_value={"property": "endpoint_kind", "icons": {"msisdn": "phone"}, "x": 1}
    )
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, entity))


def test_a_pack_with_a_bad_map_is_refused_at_composition(monkeypatch: pytest.MonkeyPatch) -> None:
    # A pack is not run through the JSON Schema, so composition has to make the same checks.
    bad = _entity(
        name="Handset",
        channel="plum",
        icon_by_value={"property": "endpoint_kind", "icons": {"msisdn": "not-an-icon"}},
    )
    pack = {"pack": "niem", "pack_version": 1, "entity_types": [bad], "edge_types": []}
    monkeypatch.setattr("ontology.packs.load_pack", lambda name: pack)
    with pytest.raises(OntologyError, match="not-an-icon"):
        compose_with_packs(load_default_ontology(), ["niem"])


def test_a_pack_with_a_map_on_a_missing_property_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _entity(
        name="Handset", channel="plum", icon_by_value={"property": "nope", "icons": {"a": "phone"}}
    )
    pack = {"pack": "niem", "pack_version": 1, "entity_types": [bad], "edge_types": []}
    monkeypatch.setattr("ontology.packs.load_pack", lambda name: pack)
    with pytest.raises(OntologyError, match="nope"):
        compose_with_packs(load_default_ontology(), ["niem"])


def test_the_default_ontology_maps_endpoint_kind() -> None:
    endpoint = {e.name: e for e in load_default_ontology().entity_types}["Endpoint"]
    assert endpoint.icon == "device"
    assert endpoint.icon_by_value is not None
    assert endpoint.icon_by_value.property == "endpoint_kind"
    assert endpoint.icon_by_value.icons == {
        "msisdn": "phone",
        "handle": "keypad",
        "account": "account",
    }


def test_the_niem_pack_maps_incident_category() -> None:
    schema = compose_with_packs(load_default_ontology(), ["niem"])
    incident: EntityTypeDef = {e.name: e for e in schema.entity_types}["Incident"]
    assert incident.icon == "shield"
    assert incident.icon_by_value is not None
    assert incident.icon_by_value.property == "category"
    # `other` is left out, so it keeps the type's icon.
    assert incident.icon_by_value.icons == {
        "throw_over": "parcel-over-wall",
        "assault": "clash",
        "disorder": "crowd",
        "find": "magnifier",
    }


def test_no_version_was_bumped_for_this() -> None:
    # ADR-128 Amendment 3: presentation keys change in place, so no recipe's pin is flagged.
    assert load_default_ontology().version == 16
    raw = yaml.safe_load((Path(_SCHEMA_PATH).parent.parent / "packs" / "niem.yaml").read_text())
    assert raw["pack_version"] == 3
