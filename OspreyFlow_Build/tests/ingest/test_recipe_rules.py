"""ADR-081 step D: a relationship the Ingest Studio writes from the source's own records is Direct,
so a recipe that names a Probabilistic type is refused, when it is saved and again when it runs
(ADR-081 Amendment 1 item 7). What a mistake would do: a loader would write rows of `SAME_AS`, or of
any Probabilistic type, as if a source had recorded them, and they would be drawn as if a person or
the resolution engine had judged them.

The run-time refusal is shown here against a graph that fails on any write, because the refusal
must come before the first one."""

from __future__ import annotations

import pytest
from services.ingest.engine import run_recipe
from services.ingest.recipe_rules import RecipeRuleError, recipe_rule_violations

from ontology.loader import load_default_ontology
from schemas.domain import EdgeTypeDef, Principal
from schemas.ingest import (
    FieldBinding,
    Recipe,
    RecipeConnector,
    RecipeEdge,
    RecipeEntity,
    RowTemplate,
)

ONTOLOGY = load_default_ontology()
ANALYST = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1")


def _template(edge_type: str) -> RowTemplate:
    person = {"family_name": FieldBinding(field="name")}
    return RowTemplate(
        entities=[
            RecipeEntity(ref="a", pole_class="person", type="Person", properties=person),
            RecipeEntity(ref="b", pole_class="person", type="Person", properties=person),
        ],
        edges=[RecipeEdge.model_validate({"type": edge_type, "from": "a", "to": "b"})],
    )


def _with_probabilistic_type() -> object:
    extra = EdgeTypeDef.model_validate(
        {"name": "LIKELY_KNOWS", "from": ["Person"], "to": ["Person"], "basis": "probabilistic"}
    )
    return ONTOLOGY.model_copy(update={"edge_types": [*ONTOLOGY.edge_types, extra]})


def test_a_direct_type_is_accepted() -> None:
    assert recipe_rule_violations(_template("ASSOCIATE_OF"), ONTOLOGY) == []


def test_a_probabilistic_type_is_refused_by_name_with_the_reason() -> None:
    (problem,) = recipe_rule_violations(_template("LIKELY_KNOWS"), _with_probabilistic_type())  # type: ignore[arg-type]
    assert "LIKELY_KNOWS" in problem and "Probabilistic" in problem


def test_same_as_is_refused_since_a_source_never_records_a_resolution_match() -> None:
    (problem,) = recipe_rule_violations(_template("SAME_AS"), ONTOLOGY)
    assert "SAME_AS" in problem


def test_not_same_as_is_refused_since_it_is_an_analysts_judgement() -> None:
    (problem,) = recipe_rule_violations(_template("NOT_SAME_AS"), ONTOLOGY)
    assert "NOT_SAME_AS" in problem


def test_a_type_the_ontology_does_not_have_is_refused() -> None:
    (problem,) = recipe_rule_violations(_template("NO_SUCH_TYPE"), ONTOLOGY)
    assert "NO_SUCH_TYPE" in problem


async def test_a_run_is_refused_before_anything_is_written() -> None:
    recipe = Recipe(
        id="r1",
        version=1,
        label="Probabilistic loader",
        connector=RecipeConnector(profile="csv"),
        ontology_version=ONTOLOGY.version,
        row_template=_template("SAME_AS"),
    )

    class Graph:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"the graph was asked to {name} before the recipe was refused")

    with pytest.raises(RecipeRuleError, match="SAME_AS"):
        await run_recipe(
            recipe,
            iter([{"name": "Ada"}]),
            graph=Graph(),  # type: ignore[arg-type]
            ontology=ONTOLOGY,
            tx="tx-1",  # type: ignore[arg-type]
            principal=ANALYST,
            load_id="load-1",
            investigation_scope="case-1",
            source="rows.csv",
        )
