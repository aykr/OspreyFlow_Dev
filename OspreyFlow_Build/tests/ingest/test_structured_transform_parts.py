"""ADR-104: a structured transform fills a property through a named part.

9 October 2026, the data engineer's journey: `person_name()` returns a given name and a family name,
and a recipe binding fills one property. Bound to `family_name`, the engine stored the whole
`PersonNameResult`, ontology validation raised, and the dry run (so Verify) failed outright. Spec 01
§7 calls the result "structured given/family"; how a binding takes one part of it was unwritten.
"""

from __future__ import annotations

import asyncio

import pytest
from services.ingest.engine import dry_run_recipe
from services.ingest.recipe_rules import recipe_rule_violations
from services.ingest.transforms import STRUCTURED_PARTS, apply_transform

from knowledge_adapters.errors import NormalisationError
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import (
    FieldBinding,
    Recipe,
    RecipeConnector,
    RecipeDefaults,
    RecipeEntity,
    RowTemplate,
)

ONTOLOGY = load_default_ontology()


def _person(family: str, given: str) -> RowTemplate:
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="p",
                pole_class="person",
                type="Person",
                on_match="create",
                properties={
                    "family_name": FieldBinding(field="subscriber_name", transform=family),
                    "given_names": FieldBinding(field="subscriber_name", transform=given),
                },
            )
        ]
    )


def test_a_part_of_a_person_name_is_its_text() -> None:
    assert apply_transform("person_name(part=family)", "HARGREAVE, Rowan") == "HARGREAVE"
    assert apply_transform("person_name(part=given)", "HARGREAVE, Rowan") == "Rowan"


def test_a_part_of_an_address() -> None:
    assert apply_transform("address(part=postcode)", "1 High Street, Leeds LS1 4AP") == "LS1 4AP"


def test_a_part_the_result_does_not_have_is_refused() -> None:
    with pytest.raises(NormalisationError):
        apply_transform("person_name(part=surname)", "HARGREAVE, Rowan")


def test_the_catalogue_names_the_parts_of_each_structured_transform() -> None:
    assert STRUCTURED_PARTS["person_name"] == ("family", "given")
    assert "postcode" in STRUCTURED_PARTS["address"]


def test_a_recipe_binding_a_structured_transform_with_no_part_is_refused_when_saved() -> None:
    problems = recipe_rule_violations(_person("person_name", "person_name"), ONTOLOGY)
    assert len(problems) == 2
    assert "part=family" in problems[0]


def test_a_recipe_naming_an_unknown_part_is_refused_when_saved() -> None:
    problems = recipe_rule_violations(
        _person("person_name(part=surname)", "person_name(part=given)"), ONTOLOGY
    )
    assert len(problems) == 1 and "surname" in problems[0]


def test_a_recipe_binding_each_part_dry_runs_to_the_name_in_two_properties() -> None:
    class _NoGraph:
        async def find_node(self, *args: object, **kwargs: object) -> None:
            return None

    template = _person("person_name(part=family)", "person_name(part=given)")
    assert recipe_rule_violations(template, ONTOLOGY) == []
    recipe = Recipe(
        id="r",
        version=1,
        label="subscribers",
        connector=RecipeConnector(profile="generic-csv"),
        ontology_version=ONTOLOGY.version,
        defaults=RecipeDefaults(
            handling={
                "classification": "OFFICIAL",
                "handling_code": "P",
                "originator": "unit-1",
                "owning_unit": "unit-1",
            },
            provenance={},
        ),
        row_template=template,
    )
    result = asyncio.run(
        dry_run_recipe(
            recipe,
            [{"subscriber_name": "HARGREAVE, Rowan"}],
            graph=_NoGraph(),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            principal=Principal(id="a", clearance="OFFICIAL", org_unit="unit-1"),
            source="subscribers.csv",
        )
    )
    (node,) = result.nodes
    assert node.properties["family_name"] == "HARGREAVE"
    assert node.properties["given_names"] == "Rowan"
