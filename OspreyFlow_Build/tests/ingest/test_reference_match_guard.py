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
- a reference on a field the entity never writes: `find_node` can only match a stored top-level
  property, and the adapter stores an identifier there only when the node is written with it, so
  `match_on: e164` on an Endpoint whose template binds `value_normalised` and not `e164` looks up
  the text "None" on every row and makes a node per row
  (`test_a_reference_on_a_field_the_entity_does_not_write_is_refused`,
  `test_the_adapter_stores_an_identifier_top_level_only_when_it_is_written`);
- the guard refusing a shipped recipe (`test_every_shipped_recipe_passes_the_reference_guard`);
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


def _endpoint_template(match_on: str, bound: dict[str, str]) -> RowTemplate:
    return RowTemplate.model_validate(
        {
            "entities": [
                {
                    "ref": "number",
                    "pole_class": "object",
                    "type": "Endpoint",
                    "match_on": match_on,
                    "on_match": "reference",
                    "properties": {name: {"field": column} for name, column in bound.items()},
                }
            ],
            "edges": [],
        }
    )


def test_a_reference_on_a_field_the_entity_does_not_write_is_refused() -> None:
    """`e164` is a declared Endpoint identifier, but this template writes `value_normalised` and
    `endpoint_kind` only: every row would look up "None" and create its own node."""
    template = _endpoint_template("e164", {"value_normalised": "number", "endpoint_kind": "kind"})
    (problem,) = reference_match_problems(template, ONTOLOGY)
    assert problem == (
        "Endpoint cannot be found by e164: the entity does not write e164, and a reference can "
        "only match a stored identifier or indexed property, so this would make a new Endpoint "
        "for every row."
    )
    assert problem in recipe_rule_violations(template, ONTOLOGY)


def test_a_reference_on_an_endpoint_identifier_the_entity_writes_passes() -> None:
    template = _endpoint_template("e164", {"e164": "number", "value_normalised": "number"})
    assert reference_match_problems(template, ONTOLOGY) == []


def test_the_adapter_stores_an_identifier_top_level_only_when_it_is_written() -> None:
    """The ground for the two cases above, read from the adapter's own serialiser: `e164` is
    flattened into its own field when the write carries it, and absent when it does not."""
    from adapters.graph_arcadedb.serialization import node_write_to_properties
    from schemas.domain import (
        AuditStub,
        Handling,
        NodeWrite,
        Provenance,
        ProvenanceState,
        SourceRef,
    )

    endpoint = ONTOLOGY.entity_type("Endpoint")
    assert endpoint is not None

    def stored(properties: dict[str, str]) -> dict[str, object]:
        write = NodeWrite(
            id="n-1",
            type="Endpoint",
            properties=properties,
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[SourceRef(document_id="d", locator="r:1", excerpt_hash="")],
                first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            handling=Handling(
                classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
            ),
            created_by="loader",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        audit = AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader")
        return node_write_to_properties(write, node_id="n-1", audit=audit, entity_type=endpoint)

    assert stored({"e164": "+447700900123", "value_normalised": "+447700900123"})["e164"] == (
        "+447700900123"
    )
    assert "e164" not in stored({"value_normalised": "+447700900123"})


def _shipped_recipes() -> list[Path]:
    root = Path(__file__).resolve().parents[3]
    return sorted(
        [
            *(root / "OspreyFlow_Core/packages/demo_fixtures").glob("*.yaml"),
            *(root / "OspreyFlow_Core/recipes").glob("*.yaml"),
            *(root / "OspreyFlow_Build/tests/scenarios/fixtures").glob("*.yaml"),
        ]
    )


def test_every_shipped_recipe_passes_the_reference_guard() -> None:
    """Read only. A recipe the guard now refuses would stop loading the day it is published."""
    judged = 0
    for path in _shipped_recipes():
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict) or "row_template" not in raw:
            continue
        template = Recipe.model_validate(raw).row_template
        judged += 1
        assert reference_match_problems(template, ONTOLOGY) == [], path.name
    assert judged >= 20, "the scan found no recipes: the paths are wrong"


def test_a_half_built_template_saves_but_an_unfindable_field_is_still_refused_at_save() -> None:
    """A Map save may hold a template still being built (`complete=False`): an entity that does
    not yet bind its `match_on` is saved, as the route test of an empty row template requires. A
    `match_on` no lookup can ever answer is refused even then, and the complete check at Verify,
    publish and run still refuses the unbound one (found by the live route tests, 27 October
    2026)."""
    unbound = _endpoint_template("value_normalised", {})
    assert reference_match_problems(unbound, ONTOLOGY, complete=False) == []
    assert recipe_rule_violations(unbound, ONTOLOGY, complete=False) == []
    assert reference_match_problems(unbound, ONTOLOGY) != []
    unfindable = _template("Document", "sent_at")
    assert reference_match_problems(unfindable, ONTOLOGY, complete=False) != []
