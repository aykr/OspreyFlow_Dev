"""ADR-081 step D: a relationship the Ingest Studio writes from the source's own records is Direct,
so a recipe that names a Probabilistic type is refused, when it is saved and again when it runs
(ADR-081 Amendment 1 item 7). What a mistake would do: a loader would write rows of `SAME_AS`, or of
any Probabilistic type, as if a source had recorded them, and they would be drawn as if a person or
the resolution engine had judged them.

The run-time refusal is shown here against a graph that fails on any write, because the refusal
must come before the first one."""

from __future__ import annotations

import pytest
from services.ingest.engine import StaleRecipeError, run_recipe
from services.ingest.recipe_rules import (
    RecipeRuleError,
    deduplicate_problems,
    recipe_rule_violations,
)

from ontology.loader import load_default_ontology
from ontology.packs import load_deployment_ontology
from schemas.domain import EdgeTypeDef, Principal
from schemas.ingest import (
    DeduplicateConfig,
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


def test_a_recipe_naming_passes_items_to_is_refused() -> None:
    """ADR-120 D8: `PASSES_ITEMS_TO` is a Probabilistic link of the NIEM pack, an inference from
    the case and never a record a source makes. Red if a recipe can write it, so a loader would
    assert as sourced fact what only an analyst or a model can infer."""
    from services.ingest.recipe_rules import check_recipe_rules

    from ontology.packs import load_deployment_ontology

    with pytest.raises(RecipeRuleError, match="PASSES_ITEMS_TO") as refused:
        check_recipe_rules(_template("PASSES_ITEMS_TO"), load_deployment_ontology())
    assert "Probabilistic" in str(refused.value)


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


class _NoGraph:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the graph was asked to {name} before the recipe was refused")


async def _run_naming_passes_items_to(pack_versions: dict[str, int] | None) -> None:
    ontology = load_deployment_ontology()
    recipe = Recipe(
        id="r2",
        version=1,
        label="A loader that names a Probabilistic NIEM link",
        connector=RecipeConnector(profile="csv"),
        ontology_version=ontology.version,
        pack_versions=pack_versions,
        row_template=_template("PASSES_ITEMS_TO"),
    )
    await run_recipe(
        recipe,
        iter([{"name": "Ada"}]),
        graph=_NoGraph(),  # type: ignore[arg-type]
        ontology=ontology,
        tx="tx-1",  # type: ignore[arg-type]
        principal=ANALYST,
        load_id="load-2",
        investigation_scope="case-1",
        source="rows.csv",
    )


async def test_a_run_naming_passes_items_to_is_refused_by_the_rule_before_any_write() -> None:
    """ADR-120 D8 at run time. The recipe is pinned to the NIEM pack at the version the composed
    ontology carries (3), so the pin check passes and it is the rule that refuses it: a run that
    reached a write would assert, as a source's record, a link only an analyst or a model can
    infer."""
    assert load_deployment_ontology().packs["niem"] == 3
    with pytest.raises(RecipeRuleError, match="PASSES_ITEMS_TO") as refused:
        await _run_naming_passes_items_to({"niem": 3})
    assert "Probabilistic" in str(refused.value)


async def test_the_same_run_unpinned_is_refused_by_the_pin_check_not_the_rule() -> None:
    """The control for the case above: without the pin the run stops earlier, at the pack check,
    so the pin is what lets the first case reach the rule it is about."""
    with pytest.raises(StaleRecipeError, match="not pinned"):
        await _run_naming_passes_items_to(None)


# --- ADR-127 decision 11: a link's span end is one column of the source, checked at Map save ------


def _span_template(valid_to: dict[str, object]) -> RowTemplate:
    template = _template("ASSOCIATE_OF")
    edge = RecipeEdge.model_validate(
        {
            "type": "ASSOCIATE_OF",
            "from": "a",
            "to": "b",
            "temporal": {"at": {"field": "start"}, "valid_to": valid_to},
        }
    )
    return template.model_copy(update={"edges": [edge]})


def test_a_span_end_bound_to_a_source_column_is_accepted() -> None:
    template = _span_template({"field": "end", "transform": "datetime"})
    assert (
        recipe_rule_violations(template, ONTOLOGY, source_columns=["name", "start", "end"]) == []
    )


def test_a_span_end_naming_a_column_the_source_lacks_is_refused_by_name() -> None:
    template = _span_template({"field": "ended"})
    (problem,) = recipe_rule_violations(template, ONTOLOGY, source_columns=["name", "start", "end"])
    assert "ended" in problem and "end" in problem and "source" in problem


def test_a_span_end_must_be_one_column_not_a_value_or_several() -> None:
    for binding in ({"literal": "2026-01-01"}, {"fields": ["a", "b"], "transform": "datetime"}, {}):
        (problem,) = recipe_rule_violations(_span_template(binding), ONTOLOGY)
        assert "end" in problem and "one column" in problem, (binding, problem)


# --- ADR-127 Amendment 15: `optional` only on a property the ontology does not require -------------


def _optional_template(entity_type: str, prop: str, *, match_on: str | None = None) -> RowTemplate:
    return RowTemplate.model_validate(
        {
            "entities": [
                {
                    "ref": "a",
                    "pole_class": "person",
                    "type": entity_type,
                    "match_on": match_on,
                    "on_match": "reference" if match_on else "create",
                    "properties": {prop: {"field": "x", "optional": True}},
                }
            ],
            "edges": [],
        }
    )


def test_optional_on_a_property_the_ontology_does_not_require_is_accepted() -> None:
    assert recipe_rule_violations(_optional_template("Person", "aliases"), ONTOLOGY) == []


def test_optional_on_a_required_property_is_refused_naming_the_entity_and_the_property() -> None:
    (problem,) = recipe_rule_violations(_optional_template("Person", "family_name"), ONTOLOGY)
    assert "family_name" in problem and "required" in problem and "'a'" in problem


def test_optional_on_the_property_an_entity_is_matched_on_is_refused() -> None:
    template = _optional_template("Person", "prison_number", match_on="prison_number")
    problems = recipe_rule_violations(template, ONTOLOGY)
    assert any("prison_number" in p and "matched on" in p for p in problems), problems


def test_optional_on_a_link_property_follows_the_same_rule() -> None:
    template = RowTemplate.model_validate(
        {
            "entities": [
                {"ref": "a", "pole_class": "person", "type": "Person", "properties": {}},
                {"ref": "b", "pole_class": "person", "type": "Person", "properties": {}},
            ],
            "edges": [
                {
                    "type": "ASSOCIATE_OF",
                    "from": "a",
                    "to": "b",
                    "properties": {"nonesuch": {"field": "x", "optional": True}},
                }
            ],
        }
    )
    # A property the type does not declare is not required, so `optional` is not what is wrong.
    assert not any("optional" in p for p in recipe_rule_violations(template, ONTOLOGY))


def test_optional_is_refused_on_a_time_binding() -> None:
    template = _span_template({"field": "end", "optional": True})
    problems = recipe_rule_violations(template, ONTOLOGY, source_columns=["name", "start", "end"])
    assert any("optional" in p and "property" in p for p in problems), problems


# --- ADR-127 Amendment 15: a list-valued transform is no key ---------------------------------------


def test_a_list_valued_transform_on_a_deduplicate_key_part_is_refused() -> None:
    config = DeduplicateConfig.model_validate({"key": [{"field": "aliases", "transform": "split"}]})
    (problem,) = deduplicate_problems(config, ["aliases"])
    assert "deduplicate key 1" in problem and "list" in problem and "split" in problem
    plain = DeduplicateConfig.model_validate({"key": [{"field": "aliases", "transform": "msisdn"}]})
    assert deduplicate_problems(plain, ["aliases"]) == []


def test_a_list_valued_transform_on_an_entitys_match_on_binding_is_refused() -> None:
    template = RowTemplate.model_validate(
        {
            "entities": [
                {
                    "ref": "a",
                    "pole_class": "person",
                    "type": "Person",
                    "match_on": "aliases",
                    "on_match": "reference",
                    "properties": {"aliases": {"field": "x", "transform": "split"}},
                }
            ],
            "edges": [],
        }
    )
    problems = recipe_rule_violations(template, ONTOLOGY)
    assert any("aliases" in p and "matched on" in p and "list" in p for p in problems), problems
    ok = template.model_copy(deep=True)
    ok.entities[0].properties["aliases"].transform = None
    assert not any("matched on" in p for p in recipe_rule_violations(ok, ONTOLOGY))
