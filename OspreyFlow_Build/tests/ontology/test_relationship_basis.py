"""A relationship type declares its basis, and may carry a colour and a thickness (ADR-081).

The owner, on 3 October 2026: every relationship type is classified Direct (a direct, established
database link) or Probabilistic, and every declaration may carry a line colour and thickness.
Amendment 1 settled the details this file pins: `basis` is required on every authored type;
`SAME_AS` is probabilistic; `NOT_SAME_AS` is an analyst's judgement and sits outside the rule, so it
has none; a colour is one of the nine data-channel names; a thickness is a whole number from 1 to 5.

Written before the loader and the schema changed, so the first run of each case was red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ontology.errors import OntologyError
from ontology.loader import _SCHEMA_PATH, load_default_ontology, load_ontology  # noqa: PLC2701
from schemas.domain import DATA_CHANNELS, NOT_SAME_AS, SAME_AS, EdgeTypeDef


def _doc(**edge: object) -> dict[str, object]:
    base: dict[str, object] = {"name": "KNOWS", "from": ["Person"], "to": ["Person"]}
    base.update(edge)
    return {
        "version": 1,
        "entity_types": [
            {"name": "Person", "pole_class": "person", "channel": "indigo", "shape": "circle"}
        ],
        "edge_types": [base],
    }


def _write(tmp_path: Path, doc: dict[str, object]) -> Path:
    path = tmp_path / "ontology.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def test_every_authored_type_of_the_default_ontology_is_direct() -> None:
    authored = [e for e in load_default_ontology().edge_types if not e.system]
    assert authored, "the default ontology declares no relationship types at all"
    assert [e.name for e in authored if e.basis != "direct"] == []


def test_same_as_is_probabilistic() -> None:
    assert load_default_ontology().edge_type(SAME_AS).basis == "probabilistic"  # type: ignore[union-attr]


def test_not_same_as_has_no_basis() -> None:
    assert load_default_ontology().edge_type(NOT_SAME_AS).basis is None  # type: ignore[union-attr]


@pytest.mark.parametrize("basis", ["direct", "probabilistic"])
def test_a_declared_basis_is_kept(tmp_path: Path, basis: str) -> None:
    schema = load_ontology(_write(tmp_path, _doc(basis=basis)))
    assert schema.edge_type("KNOWS").basis == basis  # type: ignore[union-attr]


def test_a_type_that_omits_its_basis_is_refused(tmp_path: Path) -> None:
    with pytest.raises(OntologyError, match="basis"):
        load_ontology(_write(tmp_path, _doc()))


@pytest.mark.parametrize("bad", ["Direct", "indirect", "", "inferred", True, 1])
def test_a_basis_that_is_not_one_of_the_two_is_refused(tmp_path: Path, bad: object) -> None:
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, _doc(basis=bad)))


def test_colour_and_thickness_are_optional(tmp_path: Path) -> None:
    edge = load_ontology(_write(tmp_path, _doc(basis="direct"))).edge_type("KNOWS")
    assert edge is not None
    assert (edge.colour, edge.thickness) == (None, None)


@pytest.mark.parametrize("colour", DATA_CHANNELS)
def test_each_of_the_nine_channel_names_is_a_colour(tmp_path: Path, colour: str) -> None:
    schema = load_ontology(_write(tmp_path, _doc(basis="direct", colour=colour)))
    assert schema.edge_type("KNOWS").colour == colour  # type: ignore[union-attr]


@pytest.mark.parametrize("bad", ["red", "#ff0000", "Indigo", "", "n7", 3])
def test_a_colour_outside_the_nine_is_refused(tmp_path: Path, bad: object) -> None:
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, _doc(basis="direct", colour=bad)))


@pytest.mark.parametrize("thickness", [1, 2, 3, 4, 5])
def test_a_thickness_from_one_to_five_is_kept(tmp_path: Path, thickness: int) -> None:
    schema = load_ontology(_write(tmp_path, _doc(basis="direct", thickness=thickness)))
    assert schema.edge_type("KNOWS").thickness == thickness  # type: ignore[union-attr]


@pytest.mark.parametrize("bad", [0, 6, -1, 2.5, "3", True])
def test_a_thickness_that_is_not_a_whole_number_from_one_to_five_is_refused(
    tmp_path: Path, bad: object
) -> None:
    with pytest.raises(OntologyError):
        load_ontology(_write(tmp_path, _doc(basis="direct", thickness=bad)))


@pytest.mark.parametrize("bad", [0, 6])
def test_the_model_refuses_a_thickness_outside_the_range_too(bad: int) -> None:
    with pytest.raises(ValidationError):
        EdgeTypeDef(name="X", **{"from": ["*"], "to": ["*"]}, thickness=bad)


def test_the_schema_colour_list_is_the_data_channel_list() -> None:
    schema = json.loads(Path(_SCHEMA_PATH).read_text())
    assert schema["$defs"]["edge_type"]["properties"]["colour"]["enum"] == list(DATA_CHANNELS)


def test_the_schema_requires_basis_on_an_edge_type() -> None:
    schema = json.loads(Path(_SCHEMA_PATH).read_text())
    assert "basis" in schema["$defs"]["edge_type"]["required"]
