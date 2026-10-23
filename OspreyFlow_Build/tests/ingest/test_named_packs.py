"""The packs a recipe pins (`06_DECISIONS.md` ADR-120 D10 and Amendment 1): the packs its pipeline's
domain node names, and the packs that define a type its row template writes.

What each test checks, and the violation that fails it:
- `test_a_pipeline_s_domain_node_names_its_pack`: the pack a domain node names being left out, so
  a recipe on that pack runs unchecked.
- `test_a_domain_node_naming_the_core_names_no_pack`: the core pack `pole` being listed, which
  would make a recipe on the core alone demand a pin.
- `test_a_domain_node_with_no_pack_key_names_no_pack`: a domain node with an empty config raising
  or being read as naming a pack.
- `test_a_recipe_with_no_pipeline_names_no_pack`: a v1 recipe (no pipeline) raising, or being
  treated as naming a pack.
- `test_written_packs_maps_each_written_type_to_its_defining_pack`: an entity or link type of a
  pack, written under the core, not pinning that pack (the Ledger recipes' own case); or a core
  type (`Person`) being attributed to a pack.
- `test_a_core_type_and_a_widened_type_write_no_pack`: a `TRANSACTED` between two core `Endpoint`s
  pinning FIBO because FIBO widens `TRANSACTED`.
- `test_a_referenced_and_a_conditional_entity_count`: an `on_match: reference` entity or a `when`
  entity being skipped, so the pin set misses a pack the recipe writes on some rows.
- `test_recipe_packs_is_the_union_of_named_and_written`: either source being dropped from the
  union, or a pack in both being listed twice.
"""

from __future__ import annotations

from ontology.packs import load_deployment_ontology
from schemas.ingest import (
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    RecipeCondition,
    RecipeEdge,
    RecipeEntity,
    RowTemplate,
)


def _domain(config: dict[str, object]) -> PipelineGraph:
    return PipelineGraph(
        nodes=[
            PipelineNode(
                id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain", config=config
            ),
            PipelineNode(id="source", kind=PipelineNodeKind.SOURCE, label="source"),
        ],
        edges=[],
    )


def _entity(ref: str, pole_class: str, type_: str, **extra: object) -> RecipeEntity:
    return RecipeEntity(ref=ref, pole_class=pole_class, type=type_, **extra)  # type: ignore[arg-type]


def _edge(type_: str, from_ref: str, to_ref: str) -> RecipeEdge:
    return RecipeEdge.model_validate({"type": type_, "from": from_ref, "to": to_ref})


def test_a_pipeline_s_domain_node_names_its_pack() -> None:
    from services.ingest.pipeline import named_packs

    assert named_packs(_domain({"pack": "niem"})) == ["niem"]


def test_a_domain_node_naming_the_core_names_no_pack() -> None:
    from services.ingest.pipeline import named_packs

    assert named_packs(_domain({"pack": "pole"})) == []


def test_a_domain_node_with_no_pack_key_names_no_pack() -> None:
    from services.ingest.pipeline import named_packs

    assert named_packs(_domain({})) == []


def test_a_recipe_with_no_pipeline_names_no_pack() -> None:
    from services.ingest.pipeline import named_packs

    assert named_packs(None) == []


def test_written_packs_maps_each_written_type_to_its_defining_pack() -> None:
    from services.ingest.pipeline import written_packs

    template = RowTemplate(
        entities=[
            _entity("p", "person", "Person"),
            _entity("a", "object", "Account"),
        ],
        edges=[_edge("HOLDS_ACCOUNT", "p", "a")],
    )
    assert written_packs(template, load_deployment_ontology()) == ["fibo"]


def test_a_core_type_and_a_widened_type_write_no_pack() -> None:
    from services.ingest.pipeline import written_packs

    template = RowTemplate(
        entities=[
            _entity("a", "object", "Endpoint"),
            _entity("b", "object", "Endpoint"),
        ],
        edges=[_edge("TRANSACTED", "a", "b")],
    )
    assert written_packs(template, load_deployment_ontology()) == []


def test_a_referenced_and_a_conditional_entity_count() -> None:
    from services.ingest.pipeline import written_packs

    template = RowTemplate(
        entities=[
            _entity("a", "object", "Account", match_on="number", on_match="reference"),
            _entity(
                "i",
                "event",
                "Incident",
                when=RecipeCondition(field="incident_ref", equals="yes"),
            ),
        ]
    )
    assert written_packs(template, load_deployment_ontology()) == ["fibo", "niem"]


def test_recipe_packs_is_the_union_of_named_and_written() -> None:
    from services.ingest.pipeline import recipe_packs

    template = RowTemplate(entities=[_entity("a", "object", "Account")])
    assert recipe_packs(_domain({"pack": "niem"}), template, load_deployment_ontology()) == [
        "fibo",
        "niem",
    ]
    # A pack both named and written is listed once.
    assert recipe_packs(_domain({"pack": "fibo"}), template, load_deployment_ontology()) == ["fibo"]
