"""The pipeline graph (`06_DECISIONS.md` ADR-108, phase A): a typed DAG whose node kinds are a
closed vocabulary, into which every v1 recipe migrates as one straight chain — a pure function
with golden shapes, so nothing ever guesses what an old recipe meant.

Rule 12's question, answered: the test that fails if the vocabulary opened up is
`test_an_unknown_node_kind_is_refused_by_the_schema`; the one that fails if a cycle slipped past
validation is `test_a_cycle_is_refused`; the one that fails if migration dropped a stage is
`test_a_v1_recipe_migrates_to_the_canonical_chain`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from services.ingest.pipeline import pipeline_from_recipe, pipeline_rule_violations

from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    StudioRecipeDraft,
    StudioRecipeStatus,
)


def _draft(**overrides: object) -> StudioRecipeDraft:
    base: dict[str, object] = dict(
        recipe_id="r1",
        version=3,
        status=StudioRecipeStatus.DRAFT,
        label="Carrier B phone records",
        connector_profile="cell-site-csv",
        source_location="uploaded/carrier-b.csv",
        handling={"classification": "OFFICIAL"},
        legal_basis="RIPA s22",
        owning_unit="unit-1",
        created_by="analyst-1",
        created_at=datetime(2026, 10, 9, tzinfo=UTC),
    )
    base.update(overrides)
    return StudioRecipeDraft.model_validate(base)


def _node(node_id: str, kind: PipelineNodeKind) -> PipelineNode:
    return PipelineNode(id=node_id, kind=kind, label=node_id)


def _graph(nodes: list[PipelineNode], edges: list[tuple[str, str]]) -> PipelineGraph:
    return PipelineGraph(
        nodes=nodes, edges=[PipelineEdge(source=a, target=b) for a, b in edges]
    )


CHAIN = [
    _node("domain", PipelineNodeKind.DOMAIN_MODEL),
    _node("source", PipelineNodeKind.SOURCE),
    _node("profile", PipelineNodeKind.PROFILE),
    _node("map", PipelineNodeKind.MAP),
    _node("load", PipelineNodeKind.LOAD),
]
CHAIN_EDGES = [("domain", "source"), ("source", "profile"), ("profile", "map"), ("map", "load")]


def test_a_v1_recipe_migrates_to_the_canonical_chain() -> None:
    graph = pipeline_from_recipe(_draft())
    assert [n.kind for n in graph.nodes] == [
        PipelineNodeKind.DOMAIN_MODEL,
        PipelineNodeKind.SOURCE,
        PipelineNodeKind.PROFILE,
        PipelineNodeKind.MAP,
        PipelineNodeKind.LOAD,
    ]
    assert [(e.source, e.target) for e in graph.edges] == CHAIN_EDGES
    # Each node carries what its stage needs, taken from the v1 fields, never invented.
    by_id = {n.id: n for n in graph.nodes}
    assert by_id["source"].config["connector_profile"] == "cell-site-csv"
    assert by_id["source"].config["source_location"] == "uploaded/carrier-b.csv"
    assert by_id["domain"].config["pack"] == "pole"  # the core model, until packs (phase D)
    assert pipeline_rule_violations(graph) == []


def test_migration_is_pure_and_never_stored(fresh: None = None) -> None:
    draft = _draft()
    assert draft.pipeline is None  # a v1 draft holds no graph; it is derived at read time
    first = pipeline_from_recipe(draft)
    second = pipeline_from_recipe(draft)
    assert first == second


def test_an_unknown_node_kind_is_refused_by_the_schema() -> None:
    with pytest.raises(ValidationError):
        PipelineNode.model_validate({"id": "x", "kind": "python_script", "label": "x"})


def test_a_cycle_is_refused() -> None:
    graph = _graph(CHAIN, [*CHAIN_EDGES, ("load", "source")])
    assert any("cycle" in problem for problem in pipeline_rule_violations(graph))


def test_exactly_one_domain_model_root_is_required() -> None:
    headless = _graph(CHAIN[1:], CHAIN_EDGES[1:])
    assert any("domain model" in problem for problem in pipeline_rule_violations(headless))
    two = _graph(
        [*CHAIN, _node("domain2", PipelineNodeKind.DOMAIN_MODEL)],
        [*CHAIN_EDGES, ("domain2", "source")],
    )
    assert any("one domain model" in problem for problem in pipeline_rule_violations(two))


def test_a_source_that_reaches_no_load_is_refused() -> None:
    dangling = _graph(
        [*CHAIN, _node("source2", PipelineNodeKind.SOURCE)],
        [*CHAIN_EDGES, ("domain", "source2")],
    )
    assert any("reaches no load" in problem for problem in pipeline_rule_violations(dangling))


def test_an_edge_naming_a_missing_node_is_refused() -> None:
    graph = _graph(CHAIN, [*CHAIN_EDGES, ("map", "ghost")])
    assert any("ghost" in problem for problem in pipeline_rule_violations(graph))


def test_an_extract_belongs_downstream_of_a_map_and_nowhere_else() -> None:
    placed = _graph(
        [*CHAIN, _node("extract", PipelineNodeKind.EXTRACT), _node("load2", PipelineNodeKind.LOAD)],
        [*CHAIN_EDGES, ("map", "extract"), ("extract", "load2")],
    )
    assert pipeline_rule_violations(placed) == []
    misplaced = _graph(
        [*CHAIN, _node("extract", PipelineNodeKind.EXTRACT), _node("load2", PipelineNodeKind.LOAD)],
        [*CHAIN_EDGES, ("source", "extract"), ("extract", "load2")],
    )
    assert any("extract" in problem for problem in pipeline_rule_violations(misplaced))


def test_a_domain_node_names_a_known_pack_or_the_core() -> None:
    """ADR-108 phase D: the domain model is the POLE core or a named pack; a typo is a save-time
    violation, never a silent fallback."""
    good = _graph(
        [
            PipelineNode(
                id="domain", kind=PipelineNodeKind.DOMAIN_MODEL, label="D", config={"pack": "stix"}
            ),
            *CHAIN[1:],
        ],
        CHAIN_EDGES,
    )
    assert pipeline_rule_violations(good) == []
    unknown = _graph(
        [
            PipelineNode(
                id="domain",
                kind=PipelineNodeKind.DOMAIN_MODEL,
                label="D",
                config={"pack": "marvel"},
            ),
            *CHAIN[1:],
        ],
        CHAIN_EDGES,
    )
    assert any("marvel" in problem for problem in pipeline_rule_violations(unknown))
