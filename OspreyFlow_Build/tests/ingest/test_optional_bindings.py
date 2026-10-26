"""ADR-127 Amendment 15: a list value for a `string[]` property, and a binding that may be left out.

A cell becomes a list through the `split` adapter, and the engine takes that list for a property the
ontology declares `string[]` and for nothing else. A binding marked `optional: true` leaves its
property out of the node when its cell is empty, instead of rejecting the row (which is what every
empty bound cell does without it). What a mistake would do, and the case that catches it:

- a list written to a scalar property, which the store would refuse mid-load
  (`test_a_list_is_refused_for_a_scalar_property_naming_the_property`);
- a list refused for the `string[]` it is for (`test_a_split_cell_is_a_list_for_a_string_list_property`);
- an empty cell under `optional` rejecting the row, or writing an empty list, which says "no aliases"
  where the source said nothing (`test_an_empty_cell_under_optional_leaves_the_property_out`);
- `optional` changing what every recipe does, because the default moved
  (`test_without_optional_an_empty_cell_still_rejects_the_row`);
- `optional` hiding a bad value, not only an empty one
  (`test_optional_does_not_excuse_a_value_that_does_not_read`);
- a cell with only separators or spaces writing an empty list
  (`test_a_cell_that_splits_to_nothing_under_optional_leaves_the_property_out`)."""

from __future__ import annotations

from typing import Any

from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    ValidatingGraph,
    local_staging,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1")


def _recipe(**bindings: dict[str, Any]) -> Recipe:
    properties = {
        "prison_number": {"field": "nomis_id"},
        "family_name": {"field": "family_name"},
        **bindings,
    }
    return Recipe.model_validate(
        {
            "id": "r",
            "version": 1,
            "label": "People",
            "connector": {"profile": "csv"},
            "ontology_version": ONTOLOGY.version,
            "pack_versions": {},
            "defaults": {
                "provenance": {"state": "asserted"},
                "handling": {
                    "classification": "OFFICIAL",
                    "handling_code": "P",
                    "originator": "unit-1",
                    "owning_unit": "unit-1",
                },
            },
            "row_template": {
                "entities": [
                    {
                        "ref": "p",
                        "pole_class": "person",
                        "type": "Person",
                        "match_on": "prison_number",
                        "on_match": "reference",
                        "properties": properties,
                    }
                ],
                "edges": [],
            },
        }
    )


def _row(number: str, aliases: str, family: str = "Vance") -> dict[str, str]:
    return {"nomis_id": number, "family_name": family, "aliases": aliases}


async def _load(recipe: Recipe, rows: list[dict[str, str]]) -> tuple[Any, ValidatingGraph]:
    graph = ValidatingGraph(ONTOLOGY)
    report, _events, _held = await load_with_rules(
        recipe,
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id="load-1",
        investigation_scope="case-1",
        source="people.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    return report, graph


def _by_number(graph: ValidatingGraph) -> dict[str, dict[str, Any]]:
    return {str(n.properties["prison_number"]): n.properties for n in graph.committed_nodes}


ALIASES = {"field": "aliases", "transform": "split"}


async def test_a_split_cell_is_a_list_for_a_string_list_property() -> None:
    report, graph = await _load(_recipe(aliases=ALIASES), [_row("Z1ZZ", "Cally V| Cal |Cally V")])
    assert report.rejections == [], report.rejections
    assert _by_number(graph)["Z1ZZ"]["aliases"] == ["Cally V", "Cal"]


async def test_a_list_is_refused_for_a_scalar_property_naming_the_property() -> None:
    """The row is rejected with the property and its type, never the value."""
    report, graph = await _load(
        _recipe(given_names={"field": "aliases", "transform": "split"}), [_row("Z1ZZ", "a|b")]
    )
    (rejection,) = report.rejections
    assert "Person.given_names" in rejection.reason and "string" in rejection.reason
    assert "a|b" not in rejection.reason
    assert graph.committed_nodes == []


async def test_an_empty_cell_under_optional_leaves_the_property_out() -> None:
    recipe = _recipe(aliases={**ALIASES, "optional": True})
    report, graph = await _load(recipe, [_row("Z1ZZ", ""), _row("Z2ZZ", "Cally V")])
    assert report.rejections == [], report.rejections
    people = _by_number(graph)
    assert "aliases" not in people["Z1ZZ"], "left out, not an empty list"
    assert people["Z2ZZ"]["aliases"] == ["Cally V"]


async def test_a_cell_that_splits_to_nothing_under_optional_leaves_the_property_out() -> None:
    recipe = _recipe(aliases={**ALIASES, "optional": True})
    report, graph = await _load(recipe, [_row("Z1ZZ", " "), _row("Z2ZZ", "|"), _row("Z3ZZ", " | ")])
    assert report.rejections == []
    assert all("aliases" not in p for p in _by_number(graph).values())


async def test_without_optional_an_empty_cell_still_rejects_the_row() -> None:
    report, graph = await _load(_recipe(aliases=ALIASES), [_row("Z1ZZ", ""), _row("Z2ZZ", "a")])
    (rejection,) = report.rejections
    assert rejection.row_index == 0 and "aliases" in rejection.reason
    assert set(_by_number(graph)) == {"Z2ZZ"}


async def test_optional_does_not_excuse_a_value_that_does_not_read() -> None:
    """Only an empty cell is left out: a cell the adapter refuses still rejects the row."""
    recipe = _recipe(
        given_names={"field": "aliases", "transform": "msisdn", "optional": True}
    )
    report, graph = await _load(recipe, [_row("Z1ZZ", "not a number"), _row("Z2ZZ", "")])
    assert [r.row_index for r in report.rejections] == [0]
    assert set(_by_number(graph)) == {"Z2ZZ"}


async def test_optional_on_a_plain_text_binding_leaves_it_out_when_empty() -> None:
    recipe = _recipe(given_names={"field": "given", "optional": True})
    rows = [{"nomis_id": "Z1ZZ", "family_name": "Vance", "given": ""},
            {"nomis_id": "Z2ZZ", "family_name": "Vance", "given": "Ryan"}]  # fmt: skip
    report, graph = await _load(recipe, rows)
    assert report.rejections == []
    people = _by_number(graph)
    assert "given_names" not in people["Z1ZZ"] and people["Z2ZZ"]["given_names"] == "Ryan"


async def test_a_set_of_columns_is_left_out_only_when_every_cell_is_empty() -> None:
    """A binding over several columns (a coordinate pair) is left out when all its cells are blank.
    One cell filled and one empty goes to the adapter's own judgement, which refuses it: leaving it
    out would write a place with half a position and say nothing."""
    pair = {
        "fields": ["x", "y"],
        "transform": "geometry_ref",
        "optional": True,
    }
    recipe = Recipe.model_validate(
        {
            **_recipe().model_dump(by_alias=True),
            "connector": {"profile": "csv", "source_crs": "EPSG:4326"},
            "row_template": {
                "entities": [
                    {
                        "ref": "l",
                        "pole_class": "location",
                        "type": "Location",
                        "on_match": "create",
                        "properties": {"name": {"field": "name"}, "geometry_ref": pair},
                    }
                ],
                "edges": [],
            },
        }
    )
    rows = [
        {"name": "both", "x": "-0.1", "y": "51.5"},
        {"name": "neither", "x": "", "y": " "},
        {"name": "only-x", "x": "-0.1", "y": ""},
        {"name": "only-y", "x": "", "y": "51.5"},
    ]
    report, graph = await _load(recipe, rows)
    assert sorted(r.row_index for r in report.rejections) == [2, 3], report.rejections
    assert all("required field" in r.reason for r in report.rejections), report.rejections
    stored = {str(n.properties["name"]): n.properties for n in graph.committed_nodes}
    assert set(stored) == {"both", "neither"}
    assert "geometry_ref" in stored["both"] and "geometry_ref" not in stored["neither"]


async def test_a_run_refuses_a_list_valued_transform_as_a_deduplicate_key_or_a_match() -> None:
    """Refused again at run, before anything is written, as the recipe rules are."""
    import pytest
    from services.ingest.recipe_rules import RecipeRuleError

    keyed = _recipe(aliases=ALIASES).model_copy(
        update={
            "deduplicate": {"key": [{"field": "aliases", "transform": "split"}]},  # type: ignore[arg-type]
        }
    )
    keyed = Recipe.model_validate(keyed.model_dump(by_alias=True))
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError, match="deduplicate key 1"):
        await load_with_rules(
            keyed, [_row("Z1ZZ", "a")], LOADER, graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY, load_id="l", investigation_scope="c", source="f",
            media=InMemoryMediaStore(), rules=None, scheme=SCHEME,
        )  # fmt: skip
    assert graph.committed_nodes == []

    matched = Recipe.model_validate(
        {
            **_recipe().model_dump(by_alias=True),
            "row_template": {
                "entities": [
                    {
                        "ref": "p",
                        "pole_class": "person",
                        "type": "Person",
                        "match_on": "aliases",
                        "on_match": "reference",
                        "properties": {
                            "family_name": {"field": "family_name"},
                            "aliases": ALIASES,
                        },
                    }
                ],
                "edges": [],
            },
        }
    )
    with pytest.raises(RecipeRuleError, match="matched on"):
        await load_with_rules(
            matched, [_row("Z1ZZ", "a")], LOADER, graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY, load_id="l", investigation_scope="c", source="f",
            media=InMemoryMediaStore(), rules=None, scheme=SCHEME,
        )  # fmt: skip
    assert graph.committed_nodes == []
