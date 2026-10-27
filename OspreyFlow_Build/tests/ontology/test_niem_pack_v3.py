"""NIEM pack version 3 (`06_DECISIONS.md` ADR-120 D1 and D2): an establishment, the place links,
the throw-over incident and `PASSES_ITEMS_TO`, additions only.

Rule 12's named tests, each with the violation that turns it red:

- `test_niem_is_pack_version_3`: `pack_version` left at 2.
- `test_establishment_is_an_organisation_with_its_area_properties`: Establishment missing, or with
  the wrong pole class, channel, shape, icon, identifier or property.
- `test_no_two_types_share_a_channel_and_a_shape_in_the_deployment_ontology`: a type sharing a
  channel and shape with another (red by erroring in `load_deployment_ontology()`, since the
  loader's own `_check_entity_types` refuses a duplicate first; that is intended).
- `test_establishment_s_icon_is_one_the_schema_allows`: an icon outside the schema's closed list.
- `test_every_new_link_has_its_declared_ends_basis_direction_and_time`: a link missing, or with a
  wrong end, direction, time flag, basis, label or colour (or `PASSES_ITEMS_TO` without `channel`).
- `test_passes_items_to_is_the_pack_s_only_probabilistic_type`: a second Probabilistic type, a
  non-direct DEPICTS, or `PASSES_ITEMS_TO` absent.
- `test_every_niem_link_s_colour_is_one_of_the_nine_channels`: any pack link, old or new, with a
  colour outside the nine channels.
- `test_depicts_reaches_an_establishment`: DEPICTS not ending at Establishment, a core end lost, or
  a changed source end.
- `test_throw_over_is_an_incident_category`: `throw_over` absent, or a bad category accepted.
- `test_version_3_keeps_everything_version_2_had`: any version-2 entity type, edge type, field,
  property, enum value or end dropped or changed, or a new required property on an old type.
- `test_occurred_at_declares_its_four_optional_properties`: `lat`, `lon`, `yard` or `item_type`
  missing, of another type, or required, or `pack_version` moved off 3 (Amendment 7 puts them in
  version 3 in place).
- `test_an_occurred_at_write_with_its_position_yard_and_item_passes_validation`: any of the four
  undeclared (the graph adapter and the bulk loader refuse the write), or one made required (an
  empty properties dict is refused).
- `test_an_occurred_at_write_with_an_undeclared_key_is_still_refused`: the link type accepting any
  key (an `OCCURRED_AT` that stops refusing `recovered`).
- The `test_the_superset_check_*` tests: six plant a violation and assert `_losses` names it and
  why (a dropped enum value, a dropped edge end, a link property made required, a new required
  property on an old type, a link made a system type, an unknown key in the frozen baseline); one,
  `test_the_superset_check_accepts_a_default_written_out`, guards against a false alarm. The
  unknown-key one is
  `test_the_superset_check_refuses_an_unknown_key_in_the_old_version`.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from ontology.errors import OntologyError
from ontology.loader import _SCHEMA_PATH, load_default_ontology  # noqa: PLC2701
from ontology.packs import compose_with_packs, load_deployment_ontology, load_pack
from ontology.validation import validate_properties
from schemas.domain import DATA_CHANNELS, EdgeTypeDef, EntityTypeDef, PropertyDef

_V2 = Path(__file__).parent / "fixtures" / "niem_pack_v2.yaml"
# name, from_types, to_types, directed, temporal, basis, label, colour
_NEW_LINKS = [
    ("HELD_AT", ["Person"], ["Establishment"], True, True, "direct", "Held at", "azure"),
    (
        "PART_OF",
        ["Location"],
        ["Location", "Establishment"],
        True,
        False,
        "direct",
        "Part of",
        "moss",
    ),
    ("ADJOINS", ["Location"], ["Location"], False, False, "direct", "Adjoins", "cyan"),
    ("USED_BY", ["Location"], ["Location"], True, False, "direct", "Used by", "moss"),
    ("OCCURRED_AT", ["Incident"], ["Location"], True, True, "direct", "Occurred at", "jade"),
    (
        "PASSES_ITEMS_TO",
        ["Person"],
        ["Person"],
        True,
        True,
        "probabilistic",
        "Passes items to",
        "indigo",
    ),
]


_WIDENABLE = {"identifiers", "from_types", "to_types", "properties"}
# A presentation key may be added to a type that had none (ADR-128 Amendment 3: `icon_by_value`,
# in place, no pack version bump); once a version holds one, it may not change or be dropped.
_MAY_BE_ADDED = {"icon_by_value"}


def _property_losses(where: str, old: Any, new: Any) -> list[str]:
    losses: list[str] = []
    new_props = {p.name: p for p in new.properties}
    old_names = {p.name for p in old.properties}
    for old_prop in old.properties:
        new_prop = new_props.get(old_prop.name)
        if new_prop is None:
            losses.append(f"{where}: property '{old_prop.name}' is missing")
            continue
        for field in PropertyDef.model_fields:
            if field == "values":
                continue
            if getattr(old_prop, field) != getattr(new_prop, field):
                losses.append(
                    f"{where}: property '{old_prop.name}' {field} changed from "
                    f"{getattr(old_prop, field)!r} to {getattr(new_prop, field)!r}"
                )
        for value in sorted(set(old_prop.values or []) - set(new_prop.values or [])):
            losses.append(f"{where}: property '{old_prop.name}' lost enum value '{value}'")
    for new_prop in new.properties:
        if new_prop.name not in old_names and new_prop.required:
            losses.append(f"{where}: new property '{new_prop.name}' is required")
    return losses


def _model_losses(kind: str, old: Any, new: Any, fields: Any) -> list[str]:
    where = f"{kind} {old.name}"
    losses: list[str] = []
    for field in fields:
        if field in _WIDENABLE:
            continue
        if field in _MAY_BE_ADDED and getattr(old, field) is None:
            continue
        if getattr(old, field) != getattr(new, field):
            losses.append(
                f"{where}: {field} changed from {getattr(old, field)!r} to {getattr(new, field)!r}"
            )
    for field in ("identifiers", "from_types", "to_types"):
        if field in fields:
            for lost in sorted(set(getattr(old, field)) - set(getattr(new, field))):
                losses.append(f"{where}: {field} lost '{lost}'")
    return losses + _property_losses(where, old, new)


def _known(model: Any) -> set[str]:
    names: set[str] = set(model.model_fields)
    names |= {f.alias for f in model.model_fields.values() if f.alias}
    return names


def _assert_known_keys(old: dict[str, Any]) -> None:
    """Every key in the old version must be one the models carry (or `extends`), or
    `model_validate` would drop it and the comparison would silently ignore it."""
    for kind, model in (("entity_types", EntityTypeDef), ("edge_types", EdgeTypeDef)):
        for entry in old.get(kind) or []:
            unknown = set(entry) - _known(model) - {"extends"}
            assert not unknown, f"{entry['name']}: unknown key(s) {sorted(unknown)}"
            for prop in entry.get("properties") or []:
                unknown = set(prop) - _known(PropertyDef)
                assert not unknown, (
                    f"{entry['name']}.{prop['name']}: unknown key(s) {sorted(unknown)}"
                )


def _losses(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Everything in `old` that is missing or changed in `new`, as readable sentences.

    Both sides are validated into the domain models first, so a default written out is not a
    change. Ends and identifiers may widen or reorder; every other field must be equal."""
    _assert_known_keys(old)
    losses: list[str] = []
    if old.get("pack") != new.get("pack"):
        losses.append(f"pack changed from {old.get('pack')!r} to {new.get('pack')!r}")
    new_entities = {
        e["name"]: EntityTypeDef.model_validate(e)
        for e in new.get("entity_types") or []
        if not e.get("extends")
    }
    for entry in old.get("entity_types") or []:
        if entry.get("extends"):
            continue
        old_entity = EntityTypeDef.model_validate(entry)
        new_entity = new_entities.get(old_entity.name)
        if new_entity is None:
            losses.append(f"entity type {old_entity.name} is missing")
            continue
        losses += _model_losses("entity type", old_entity, new_entity, EntityTypeDef.model_fields)
    new_edges = {
        e["name"]: EdgeTypeDef.model_validate(e)
        for e in new.get("edge_types") or []
        if not e.get("extends")
    }
    for entry in old.get("edge_types") or []:
        if entry.get("extends"):
            continue
        old_edge = EdgeTypeDef.model_validate(entry)
        new_edge = new_edges.get(old_edge.name)
        if new_edge is None:
            losses.append(f"edge type {old_edge.name} is missing")
            continue
        losses += _model_losses("edge type", old_edge, new_edge, EdgeTypeDef.model_fields)
    return losses


def _v2() -> dict[str, Any]:
    raw = yaml.safe_load(_V2.read_text())
    assert isinstance(raw, dict)
    return raw


def _entity(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    return next(e for e in raw["entity_types"] if e["name"] == name)


def _edge(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    return next(e for e in raw["edge_types"] if e["name"] == name)


def test_niem_is_pack_version_3() -> None:
    assert load_pack("niem")["pack_version"] == 3


def test_establishment_is_an_organisation_with_its_area_properties() -> None:
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    entities = {e.name: e for e in composed.entity_types}
    assert "Establishment" in entities
    establishment = entities["Establishment"]
    assert establishment.pole_class == "organisation"
    assert establishment.channel == "azure"
    assert establishment.shape == "diamond"
    assert establishment.icon == "building"
    assert establishment.identifiers == ["establishment_ref"]
    props = {p.name: p for p in establishment.properties}
    expected = {
        "name": ("string", True, True),
        "establishment_ref": ("string", True, True),
        "niu_area": ("string", False, True),
        "soct_region": ("string", False, True),
        "security_category": ("string", False, False),
    }
    assert set(props) == set(expected)
    for name, (type_, required, indexed) in expected.items():
        assert props[name].type == type_, name
        assert bool(props[name].required) is required, name
        assert bool(props[name].indexed) is indexed, name


def test_no_two_types_share_a_channel_and_a_shape_in_the_deployment_ontology() -> None:
    pairs = [(e.channel, e.shape) for e in load_deployment_ontology().entity_types]
    assert len(pairs) == len(set(pairs)), pairs


def test_establishment_s_icon_is_one_the_schema_allows() -> None:
    schema = json.loads(Path(_SCHEMA_PATH).read_text())
    allowed = schema["$defs"]["entity_type"]["properties"]["icon"]["enum"]
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    establishment = next(e for e in composed.entity_types if e.name == "Establishment")
    assert establishment.icon in allowed


@pytest.mark.parametrize(
    ("name", "from_types", "to_types", "directed", "temporal", "basis", "label", "colour"),
    _NEW_LINKS,
)
def test_every_new_link_has_its_declared_ends_basis_direction_and_time(
    name: str,
    from_types: list[str],
    to_types: list[str],
    directed: bool,
    temporal: bool,
    basis: str,
    label: str,
    colour: str,
) -> None:
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    edges = {e.name: e for e in composed.edge_types}
    assert name in edges
    edge = edges[name]
    assert edge.from_types == from_types
    assert edge.to_types == to_types
    assert edge.directed is directed
    assert edge.temporal is temporal
    # A pack edge skips the JSON Schema, so a missing basis would otherwise pass unnoticed.
    assert edge.basis == basis
    assert edge.label == label
    assert edge.colour == colour
    if name == "PASSES_ITEMS_TO":
        channel = next(p for p in edge.properties if p.name == "channel")
        assert channel.type == "string"


def test_passes_items_to_is_the_pack_s_only_probabilistic_type() -> None:
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    edges = {e.name: e for e in composed.edge_types}
    assert "PASSES_ITEMS_TO" in edges
    assert edges["DEPICTS"].basis == "direct"
    for edge in load_pack("niem")["edge_types"]:
        if edge["name"] == "PASSES_ITEMS_TO":
            assert edge["basis"] == "probabilistic"
        elif not edge.get("extends"):  # a widening entry restates no basis
            assert edge["basis"] == "direct", edge["name"]


def test_every_niem_link_s_colour_is_one_of_the_nine_channels() -> None:
    for edge in load_pack("niem")["edge_types"]:
        colour = edge.get("colour")
        if colour is not None:
            assert colour in DATA_CHANNELS, edge["name"]


def test_depicts_reaches_an_establishment() -> None:
    core_depicts = load_default_ontology().edge_type("DEPICTS")
    assert core_depicts is not None
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    depicts = next(e for e in composed.edge_types if e.name == "DEPICTS")
    assert "Establishment" in depicts.to_types
    for core_end in core_depicts.to_types:
        assert core_end in depicts.to_types, core_end
    assert depicts.from_types == ["Document"]


def test_throw_over_is_an_incident_category() -> None:
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    incident = next(e for e in composed.entity_types if e.name == "Incident")
    category = next(p for p in incident.properties if p.name == "category")
    assert category.values is not None and "throw_over" in category.values
    validate_properties(incident, {"category": "throw_over"})
    with pytest.raises(OntologyError, match="does not match declared type"):
        validate_properties(incident, {"category": "catapult"})


def test_version_3_keeps_everything_version_2_had() -> None:
    assert _losses(_v2(), load_pack("niem")) == []


def test_the_superset_check_reports_a_dropped_enum_value() -> None:
    mutated = copy.deepcopy(load_pack("niem"))
    category = next(
        p for p in _entity("Incident", mutated)["properties"] if p["name"] == "category"
    )
    category["values"].remove("find")
    losses = _losses(_v2(), mutated)
    assert losses
    assert any("find" in loss for loss in losses), losses


def test_the_superset_check_reports_a_dropped_edge_end() -> None:
    mutated = copy.deepcopy(load_pack("niem"))
    _edge("ROLE_IN", mutated)["to"].remove("Incident")
    losses = _losses(_v2(), mutated)
    assert losses
    assert any("ROLE_IN" in loss for loss in losses), losses


def _planted() -> dict[str, Any]:
    return copy.deepcopy(load_pack("niem"))


def _prop(entry: dict[str, Any], name: str) -> dict[str, Any]:
    return next(p for p in entry["properties"] if p["name"] == name)


def test_the_superset_check_reports_a_link_property_made_required() -> None:
    mutated = _planted()
    _prop(_edge("VISITED", mutated), "channel")["required"] = True
    losses = _losses(_v2(), mutated)
    assert any(
        "VISITED" in loss and "required changed from False to True" in loss for loss in losses
    ), losses


def test_the_superset_check_reports_a_new_required_property_on_an_old_type() -> None:
    mutated = _planted()
    _entity("Incident", mutated)["properties"].append(
        {"name": "severity", "type": "string", "required": True}
    )
    losses = _losses(_v2(), mutated)
    assert any(
        "Incident" in loss and "severity" in loss and "is required" in loss for loss in losses
    ), losses


def test_the_superset_check_reports_a_link_made_a_system_type() -> None:
    mutated = _planted()
    _edge("VISITED", mutated)["system"] = True
    losses = _losses(_v2(), mutated)
    assert any("VISITED" in loss and "system" in loss for loss in losses), losses


def test_the_superset_check_accepts_a_default_written_out() -> None:
    mutated = _planted()
    _prop(_edge("SHARED_CELL_WITH", mutated), "cell")["indexed"] = False
    _edge("CO_DEFENDANT_OF", mutated)["temporal"] = False
    assert _losses(_v2(), mutated) == []


def test_the_superset_check_refuses_an_unknown_key_in_the_old_version() -> None:
    old = copy.deepcopy(_v2())
    _edge("VISITED", old)["mystery"] = 1
    # The check raises (AssertionError) rather than reporting: a baseline with a key the models
    # would drop is a broken baseline, not a loss.
    with pytest.raises(AssertionError, match="mystery"):
        _losses(old, load_pack("niem"))


# ADR-120 Amendment 7 decision 1: a throw-over's position, yard and item ride on its link.
_OCCURRED_AT_PROPERTIES = {
    "lat": "float",
    "lon": "float",
    "yard": "string",
    "item_type": "string",
}


def _occurred_at() -> EdgeTypeDef:
    composed = compose_with_packs(load_default_ontology(), ["niem"])
    return next(e for e in composed.edge_types if e.name == "OCCURRED_AT")


def test_occurred_at_declares_its_four_optional_properties() -> None:
    declared = {p.name: p for p in _occurred_at().properties}
    assert {name: p.type.value for name, p in declared.items()} == _OCCURRED_AT_PROPERTIES
    assert not any(p.required for p in declared.values())
    # Still version 3 itself, not a version 4 (Amendment 7: nothing has loaded or pinned it).
    assert load_pack("niem")["pack_version"] == 3


def test_an_occurred_at_write_with_its_position_yard_and_item_passes_validation() -> None:
    validate_properties(
        _occurred_at(), {"lat": 51.43, "lon": -1.15, "yard": "03", "item_type": "mobile phone"}
    )
    # None is required, so a find or an assault placed in a cell carries none of them.
    validate_properties(_occurred_at(), {})


def test_an_occurred_at_write_with_an_undeclared_key_is_still_refused() -> None:
    # The message must name `recovered` alone: while the four are undeclared it names them too.
    with pytest.raises(
        OntologyError, match=re.escape("'OCCURRED_AT' does not declare property 'recovered'")
    ):
        validate_properties(_occurred_at(), {"lat": 51.43, "recovered": "yes"})


def test_the_superset_check_refuses_a_changed_icon_map() -> None:
    # An icon map the old version already held may not change or go (ADR-128 Amendment 3); only
    # adding one to a type that had none is allowed.
    old = _v2()
    _entity("Incident", old)["icon_by_value"] = {
        "property": "category",
        "icons": {"find": "magnifier"},
    }
    changed = copy.deepcopy(old)
    _entity("Incident", changed)["icon_by_value"]["icons"]["find"] = "crowd"
    assert any("icon_by_value changed" in loss for loss in _losses(old, changed))
    dropped = copy.deepcopy(old)
    del _entity("Incident", dropped)["icon_by_value"]
    assert any("icon_by_value changed" in loss for loss in _losses(old, dropped))
    assert _losses(old, copy.deepcopy(old)) == []
