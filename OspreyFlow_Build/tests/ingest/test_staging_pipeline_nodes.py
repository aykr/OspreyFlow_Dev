"""ADR-140 Amendment 12 (Q1 (a), the orchestrator's settlement of 8 November 2026): a pipeline's
staging steps are nodes of its graph, and the recipe's `staging:` list is built from them in run
order at save and publish, never kept beside them.

What a mistake would do, and the case that catches it:

- a step's record changed on its way through the graph (a key dropped, an alias written under its
  Python name, a label lost), so what publishes is not what the drawer showed
  (`test_a_staging_list_round_trips_through_the_pipeline_identically`);
- the list built in the graph's stored node order rather than run order, so a step reads one
  written after it (`test_the_staging_list_is_in_run_order_whatever_the_node_order`);
- a step whose config is not its kind's record, or whose edges say something its config does not,
  saved without a word (`test_a_step_s_bad_record_is_refused_in_words`,
  `test_a_step_whose_edges_disagree_with_what_it_reads_is_refused`,
  `test_the_last_step_must_feed_map`).
"""

from __future__ import annotations

from pathlib import Path

from services.ingest.pipeline import (
    pipeline_rule_violations,
    pipeline_with_staging,
    staging_from_pipeline,
)
from services.ingest.recipe_loader import load_recipe

from schemas.ingest import PipelineEdge, PipelineGraph, PipelineNode, PipelineNodeKind

FIXTURES = Path(__file__).parent / "fixtures" / "visits_and_contacts"
RECIPE = load_recipe(FIXTURES / "visits_and_contacts_recipe.yaml")


def _base() -> PipelineGraph:
    """The exit's pipeline before its steps: a domain model, two sources, Map and Load."""
    return PipelineGraph(
        nodes=[
            PipelineNode(id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="Domain model"),
            PipelineNode(id="visit_bookings", kind=PipelineNodeKind.SOURCE, label="Visit bookings"),
            PipelineNode(id="number_owners", kind=PipelineNodeKind.SOURCE, label="Number owners"),
            PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
            PipelineNode(id="load", kind=PipelineNodeKind.LOAD, label="Load"),
        ],
        edges=[
            PipelineEdge(source="domain", target="visit_bookings"),
            PipelineEdge(source="domain", target="number_owners"),
            PipelineEdge(source="visit_bookings", target="map"),
            PipelineEdge(source="map", target="load"),
        ],
    )


def test_a_staging_list_round_trips_through_the_pipeline_identically() -> None:
    assert RECIPE.staging
    graph = pipeline_with_staging(_base(), RECIPE.staging)
    assert pipeline_rule_violations(graph) == []
    back = staging_from_pipeline(graph)
    assert back is not None
    assert [s.model_dump(by_alias=True) for s in back] == [
        s.model_dump(by_alias=True) for s in RECIPE.staging
    ]
    # And the steps sit between the sources and Map: the source no longer feeds Map directly.
    edges = {(e.source, e.target) for e in graph.edges}
    assert ("visit_bookings", "map") not in edges
    assert ("visit_bookings", "with_establishment") in edges
    assert ("number_owners", "with_owner") in edges
    assert ("titled", "map") in edges


def test_a_pipeline_without_steps_has_no_staging() -> None:
    assert staging_from_pipeline(_base()) is None


def test_the_staging_list_is_in_run_order_whatever_the_node_order() -> None:
    assert RECIPE.staging
    graph = pipeline_with_staging(_base(), RECIPE.staging)
    graph.nodes.reverse()
    back = staging_from_pipeline(graph)
    assert back is not None
    assert [s.id for s in back] == ["with_establishment", "with_owner", "titled"]


def test_a_step_s_bad_record_is_refused_in_words() -> None:
    assert RECIPE.staging
    graph = pipeline_with_staging(_base(), RECIPE.staging)
    join = next(n for n in graph.nodes if n.id == "with_owner")
    join.config = {k: v for k, v in join.config.items() if k != "right_key"}
    join.config["expression"] = "left.x == right.y"
    problems = pipeline_rule_violations(graph)
    assert any("with_owner" in p and "right_key" in p for p in problems), problems
    assert any("with_owner" in p and "expression" in p for p in problems), problems


def test_a_step_whose_edges_disagree_with_what_it_reads_is_refused() -> None:
    assert RECIPE.staging
    graph = pipeline_with_staging(_base(), RECIPE.staging)
    cut = ("number_owners", "with_owner")
    graph.edges = [e for e in graph.edges if (e.source, e.target) != cut]
    problems = pipeline_rule_violations(graph)
    assert (
        "step 'with_owner' reads 'number_owners', but no line joins them on the pipeline"
        in problems
    ), problems


def test_the_last_step_must_feed_map() -> None:
    assert RECIPE.staging
    graph = pipeline_with_staging(_base(), RECIPE.staging)
    graph.edges = [e for e in graph.edges if (e.source, e.target) != ("titled", "map")]
    problems = pipeline_rule_violations(graph)
    assert "the last step, 'titled', feeds no Map: Map reads the last step's table" in problems


def test_a_half_set_step_is_refused_in_plain_words() -> None:
    """What a drawer shows while a step is being set: what it still needs, never a validator's
    phrasing (the save gate's words, which the drawer's sample repeats)."""
    graph = _base()
    graph.nodes.append(
        PipelineNode(
            id="lookup", kind=PipelineNodeKind.LOOKUP, label="Lookup",
            config={"input": "visit_bookings", "list": "", "add": []},
        )  # fmt: skip
    )
    graph.edges.append(PipelineEdge(source="visit_bookings", target="lookup"))
    problems = pipeline_rule_violations(graph)
    assert [p for p in problems if p.startswith("step 'lookup'")] == [
        "step 'lookup' needs 'list'",
        "step 'lookup' needs 'on'",
        "step 'lookup' needs at least 1 in 'add'",
    ]
