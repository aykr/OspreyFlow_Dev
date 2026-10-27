"""ADR-127 Amendment 37: a recipe may look an entity up by reference only on a field the graph can
find it by. The ArcadeDB adapter's `find_node` reads top-level properties, and only a type's
`identifiers` and its `indexed` properties are stored that way; a reference on any other property
never matches, so the engine would write a new, empty node for every row. What a mistake would do,
and the case that catches it:

- a reference on a property that is neither, accepted at Verify
  (`test_verify_refuses_a_reference_on_an_unindexed_property`) or at publish
  (`test_publish_refuses_a_reference_on_an_unindexed_property`), or at the rules every save and run
  makes (`test_a_reference_on_an_unindexed_property_is_refused_naming_type_and_field`);
- a reference on an identifier refused (`test_a_reference_on_an_identifier_passes`);
- a reference on an indexed property refused, or accepted only for identifiers
  (`test_a_reference_on_an_indexed_property_passes`);
- a `create` entity judged by a rule that is only for a reference
  (`test_an_entity_that_is_not_a_reference_is_not_checked`);
- the Document's `message_id`, which PID's report recipe matches on, not indexed
  (`test_document_message_id_is_indexed_and_the_pid_report_recipe_passes`).

The draft is in memory; nothing is read or written."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from services.api.studio_publish import check_before_publish
from services.api.studio_verify import run_verify
from services.ingest.recipe_rules import (
    RecipeRuleError,
    recipe_rule_violations,
    reference_match_problems,
)

from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal
from schemas.ingest import Recipe, RowTemplate, StudioRecipeDraft, StudioRecipeStatus

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
AUTHOR = Principal(id="author-o", clearance="OFFICIAL", org_unit="unit-1")
FIXTURES = Path(__file__).resolve().parents[3] / "OspreyFlow_Core/packages/demo_fixtures"


def _template(type_name: str, field: str, *, on_match: str = "reference") -> RowTemplate:
    return RowTemplate.model_validate(
        {
            "entities": [
                {
                    "ref": "thing",
                    "pole_class": "object",
                    "type": type_name,
                    "match_on": field,
                    "on_match": on_match,
                    "properties": {field: {"field": "value"}},
                }
            ],
            "edges": [],
        }
    )


def _draft(template: RowTemplate) -> StudioRecipeDraft:
    return StudioRecipeDraft(
        recipe_id="r-1",
        version=1,
        status=StudioRecipeStatus.DRAFT,
        label="Reports",
        connector_profile="generic-csv",
        source_location="reports.csv",
        handling={
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        legal_basis="Test",
        owning_unit="unit-1",
        created_by="author-o",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        row_template=template,
        ready_for_profile=True,
        verified_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


# `sent_at` is a Document property that is neither an identifier nor indexed.
UNINDEXED = _template("Document", "sent_at")


def test_a_reference_on_an_unindexed_property_is_refused_naming_type_and_field() -> None:
    (problem,) = reference_match_problems(UNINDEXED, ONTOLOGY)
    assert problem == (
        "Document cannot be found by sent_at: a reference can only match an identifier or an "
        "indexed property of the type, so this would make a new Document for every row."
    )
    assert problem in recipe_rule_violations(UNINDEXED, ONTOLOGY)


def test_a_reference_on_an_identifier_passes() -> None:
    template = _template("Person", "nino")
    assert reference_match_problems(template, ONTOLOGY) == []


def test_a_reference_on_an_indexed_property_passes() -> None:
    template = _template("Person", "family_name")
    assert reference_match_problems(template, ONTOLOGY) == []


def test_an_entity_that_is_not_a_reference_is_not_checked() -> None:
    template = _template("Document", "sent_at", on_match="create")
    assert reference_match_problems(template, ONTOLOGY) == []


async def test_verify_refuses_a_reference_on_an_unindexed_property() -> None:
    with pytest.raises(RecipeRuleError, match="Document cannot be found by sent_at"):
        await run_verify(_draft(UNINDEXED), AUTHOR, SCHEME, None, ONTOLOGY)  # type: ignore[arg-type]


def test_publish_refuses_a_reference_on_an_unindexed_property() -> None:
    with pytest.raises(RecipeRuleError, match="Document cannot be found by sent_at"):
        check_before_publish(_draft(UNINDEXED), ONTOLOGY)
    check_before_publish(_draft(_template("Person", "nino")), ONTOLOGY)


def test_document_message_id_is_indexed_and_the_pid_report_recipe_passes() -> None:
    document = ONTOLOGY.entity_type("Document")
    assert document is not None
    message_id = next(p for p in document.properties if p.name == "message_id")
    assert message_id.indexed is True
    recipe = Recipe.model_validate(
        yaml.safe_load((FIXTURES / "pid_report_incidents_recipe.yaml").read_text())
    )
    assert reference_match_problems(recipe.row_template, ONTOLOGY) == []
