"""The fuzzy match (ADR-140 decision 13; ADR-006 Amendment 1; rules 5 and 6; the redesign's phase 8;
`services/ingest/fuzzy_match.py`, `fuzzy_links.py`). Each case runs the real call sites: the save
gate (`staging_rule_violations`), the steps (`run_staging`), and Map through the staged run and Test
(`staged_run.run_staged_recipe`, `dry_run_staged_recipe`). What a mistake would do, and the case
that catches it:

- the step merging the two records into one node, or writing its SAME_AS asserted
  (`test_a_match_leaves_two_nodes_and_one_inferred_same_as`; red if the step writes one node);
- a value Map binds from a matched column written as fact
  (`test_a_value_bound_from_a_matched_column_is_inferred_with_the_score`; red if asserted);
- a row below the threshold dropped, or not counted (`test_a_row_below_the_threshold_is_kept_and_
  counted`);
- the threshold not being part of the version (`test_two_thresholds_are_two_versions_and_two_
  counts`);
- the SAME_AS confirming itself, by a second run or a threshold (`test_the_same_as_stays_inferred_
  until_a_person_confirms_it`);
- a later step carrying a matched value under another name (`test_a_fuzzy_match_is_the_last_step`);
- a SAME_AS between two things of different kinds, or from the wrong row (`test_the_same_as_…`).
"""

from __future__ import annotations

from typing import Any

import pytest
from services.extract.writer import confirm_edge
from services.ingest.fuzzy_links import fuzzy_link_problems
from services.ingest.fuzzy_match import run_fuzzy_step
from services.ingest.recipe_rules import RecipeRuleError
from services.ingest.staged_run import dry_run_staged_recipe, run_staged_recipe
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import (
    StagedTable,
    run_staging,
    source_table,
    staging_rule_violations,
)

from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Edge, Principal, ProvenanceState
from schemas.ingest import Recipe
from schemas.staging import FuzzyMatchStep
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    ValidatingGraph,
    local_staging,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
ANALYST = Principal(id="analyst-1", clearance="SECRET", org_unit="unit-1")

VISITS = [
    {"booking_id": "VB-1", "family": "WHITLOW", "given": "Shona"},
    {"booking_id": "VB-2", "family": "ELLERY", "given": "Mark"},
    {"booking_id": "VB-3", "family": "OKAFOR", "given": "Ada"},
    {"booking_id": "VB-4", "family": "PRICE", "given": "Tom"},
    {"booking_id": "VB-5", "family": "ODEH", "given": "Sami"},
]
OWNERS = [
    {"owner": "WHITLOW"}, {"owner": "ELERY"}, {"owner": "ODE"}, {"owner": "PRYCE"},
    {"owner": "NOBODY"},
]  # fmt: skip


def _step(threshold: float = 0.6, **update: Any) -> dict[str, Any]:
    return {
        "id": "visitor_owner", "kind": "fuzzy_match", "label": "Fuzzy match: visitor ≈ owner",
        "left": "visits", "right": "owners",
        "compare": [{"left": "family", "right": "owner", "method": "jaro_winkler"}],
        "threshold": threshold, "add": [{"column": "owner", "as": "matched_owner"}],
        "same_as": {"left": "visitor", "right": "matched"},
    } | update  # fmt: skip


def _recipe(threshold: float = 0.6, version: int = 1) -> Recipe:
    return Recipe.model_validate(
        {
            "id": "visitors", "version": version, "label": "Visitors and owners",
            "connector": {"profile": "generic-csv"}, "ontology_version": ONTOLOGY.version,
            "defaults": {
                "legal_basis": "Synthetic", "provenance": {"state": "asserted"},
                "handling": {"classification": "OFFICIAL", "handling_code": "P",
                             "originator": "unit-1", "owning_unit": "unit-1"},
            },
            "staging": [_step(threshold)],
            "row_template": {
                "entities": [
                    {"ref": "booking", "pole_class": "object", "type": "Document",
                     "properties": {"message_id": {"field": "booking_id"},
                                    "document_kind": {"literal": "other"}}},
                    {"ref": "visitor", "pole_class": "person", "type": "Person",
                     "properties": {"family_name": {"field": "family"},
                                    "given_names": {"field": "given"}}},
                    {"ref": "matched", "pole_class": "person", "type": "Person",
                     "when": {"field": "matched_owner", "is": "not_null"},
                     "properties": {"family_name": {"field": "matched_owner"}}},
                ],
                "edges": [
                    {"type": "MENTIONED_IN", "from": "visitor", "to": "booking"},
                    {"type": "MENTIONED_IN", "from": "matched", "to": "booking"},
                ],
            },
        }
    )  # fmt: skip


def _sources() -> dict[str, StagedTable]:
    return {
        "visits": source_table("visits", VISITS, load_id="ld-v"),
        "owners": source_table("owners", OWNERS, load_id="ld-o"),
    }


async def _load(recipe: Recipe, graph: ValidatingGraph | None = None, load_id: str = "ld-1") -> Any:
    graph = graph or ValidatingGraph(ONTOLOGY)
    tx = await graph.begin_transaction()
    done = await run_staged_recipe(
        recipe, sources=_sources(), lists={}, dataset_id="pid", graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY, tx=tx, principal=LOADER, load_id=load_id,  # type: ignore[arg-type]
        investigation_scope="case-1", storage=ObjectStorageConfig(bucket="staging"), scheme=SCHEME,
        subscribed=(),
    )  # fmt: skip
    await graph.commit_transaction(tx)
    return done, graph


def _persons(graph: ValidatingGraph) -> dict[str, list[Any]]:
    found: dict[str, list[Any]] = {}
    for node in graph.committed_nodes:
        if node.type == "Person":
            found.setdefault(str(node.properties["family_name"]), []).append(node)
    return found


def test_the_step_keeps_every_left_row_and_scores_its_best_match() -> None:
    out, report = run_fuzzy_step(
        FuzzyMatchStep.model_validate(_step(0.6)), *(_sources()[n] for n in ("visits", "owners"))
    )
    got = [(r.cells["family"], r.cells["matched_owner"], r.cells["match_score"]) for r in out.rows]
    assert [g[0] for g in got] == ["WHITLOW", "ELLERY", "OKAFOR", "PRICE", "ODEH"]
    assert [(g[1] is not None) for g in got] == [True, True, False, False, True]
    assert got[1][1] == "ELERY" and float(got[1][2]) >= 0.6
    # A matched row names both rows, as a Join's does; a row below the threshold its own only.
    assert [(r.source, r.row_index) for r in out.rows[1].refs] == [("visits", 1), ("owners", 1)]
    assert [(r.source, r.row_index) for r in out.rows[2].refs] == [("visits", 2)]
    assert (report.rows_in, report.rows_out, report.matched, report.unmatched) == (5, 5, 3, 2)
    assert report.threshold == 0.6 and report.right_unmatched == 2


async def test_a_match_leaves_two_nodes_and_one_inferred_same_as() -> None:
    """ADR-006 Amendment 1 item 2; rule 6. Red if the step writes one node: the visitor and the
    owner it matched are two Persons, joined by one scored, inferred SAME_AS."""
    _done, graph = await _load(_recipe(0.6))
    persons = _persons(graph)
    visitor, matched = persons["ELLERY"][0], persons["ELERY"][0]
    assert visitor.id != matched.id
    same_as = [e for e in graph.committed_edges if e.type == "SAME_AS"]
    assert len(same_as) == 3  # WHITLOW, ELLERY, ODEH matched
    link = next(e for e in same_as if {e.source, e.target} == {visitor.id, matched.id})
    assert (link.source, link.target) == (visitor.id, matched.id)
    assert link.provenance.state is ProvenanceState.INFERRED
    assert link.properties["score"] == link.provenance.extraction_confidence >= 0.6
    assert '"threshold": 0.6' in str(link.properties["comparison_vector"])
    assert link.provenance.extracted_by == "fuzzy_match:visitor_owner"
    # Its sources are the two rows it matched, each with the load that read it.
    assert {(s.document_id, s.locator, s.load_id) for s in link.provenance.sources} == {
        ("visits", "row 1", "ld-v"), ("owners", "row 1", "ld-o"),
    }  # fmt: skip
    # Same-name rows were not folded into one record either: WHITLOW the visitor, WHITLOW the owner.
    assert len(persons["WHITLOW"]) == 2


async def test_a_value_bound_from_a_matched_column_is_inferred_with_the_score() -> None:
    """R13: Map binds the matched owner's name, so the Person written from it, and the link that
    joins it, are inferred with the score; the left row's own visitor stays asserted."""
    _done, graph = await _load(_recipe(0.6))
    persons = _persons(graph)
    matched, visitor = persons["ELERY"][0], persons["ELLERY"][0]
    assert matched.provenance.state is ProvenanceState.INFERRED
    assert 0.6 <= (matched.provenance.extraction_confidence or 0) < 1
    assert visitor.provenance.state is ProvenanceState.ASSERTED
    links = [e for e in graph.committed_edges if e.type == "MENTIONED_IN"]
    assert {e.provenance.state for e in links if e.source == matched.id} == {
        ProvenanceState.INFERRED
    }
    assert {e.provenance.state for e in links if e.source == visitor.id} == {
        ProvenanceState.ASSERTED
    }


async def test_a_row_below_the_threshold_is_kept_and_counted() -> None:
    done, graph = await _load(_recipe(0.6))
    (count,) = done.report.staging_steps
    assert (count.kind, count.matched, count.unmatched, count.threshold) == (
        "fuzzy_match", 3, 2, 0.6,
    )  # fmt: skip
    persons = _persons(graph)
    # OKAFOR and PRICE matched nothing at 0.6: written, each with no SAME_AS and no matched owner.
    for name in ("OKAFOR", "PRICE"):
        (person,) = persons[name]
        assert not [e for e in graph.committed_edges if e.type == "SAME_AS" and person.id in
                    (e.source, e.target)]  # fmt: skip
    assert "PRYCE" not in persons
    assert len(done.staging.output.rows) == len(VISITS)


async def test_two_thresholds_are_two_versions_and_two_counts() -> None:
    """ADR-006 Amendment 1 item 4: the threshold is part of the version, and a run says which."""
    strict, loose = _recipe(0.9, version=1), _recipe(0.5, version=2)
    assert strict.model_dump(mode="json") != loose.model_dump(mode="json")
    done_strict, graph_strict = await _load(strict)
    done_loose, graph_loose = await _load(loose)
    matched = [d.report.staging_steps[0].matched for d in (done_strict, done_loose)]
    assert matched[0] < matched[1]
    for graph, version, threshold in ((graph_strict, 1, 0.9), (graph_loose, 2, 0.5)):
        for link in (e for e in graph.committed_edges if e.type == "SAME_AS"):
            vector = str(link.properties["comparison_vector"])
            assert f'"pipeline": "visitors@v{version}"' in vector
            assert f'"threshold": {threshold}' in vector
            assert link.recipe_version == version


async def test_test_and_the_load_write_the_same_same_as() -> None:
    tested = await dry_run_staged_recipe(
        _recipe(0.6), sources=_sources(), lists={}, dataset_id="pid",
        graph=ValidatingGraph(ONTOLOGY), ontology=ONTOLOGY, principal=LOADER,  # type: ignore[arg-type]
        scheme=SCHEME, subscribed=(),
    )  # fmt: skip
    same_as = [e for e in tested.result.edges if e.type == "SAME_AS"]
    assert len(same_as) == 3
    assert {e.provenance.state for e in same_as} == {ProvenanceState.INFERRED}
    assert tested.result.edges_by_type["SAME_AS"].created == 3


async def test_the_same_as_stays_inferred_until_a_person_confirms_it() -> None:
    """Rule 5: no threshold, no second run and no later load promotes it; only a person's own
    confirmation, which names them."""
    graph = MergingGraph(ONTOLOGY)
    await _load(_recipe(0.6), graph, load_id="ld-1")
    await _load(_recipe(0.6), graph, load_id="ld-2")
    links = [e for e in graph.committed_edges if e.type == "SAME_AS"]
    assert links and {e.provenance.state for e in links} == {ProvenanceState.INFERRED}
    assert all(e.provenance.confirmed_by is None for e in links)
    stored = links[0]
    edge = Edge.model_validate(
        {**stored.model_dump(), "audit": {"created_at": stored.created_at,
                                          "created_by": stored.created_by, "revision": 1}}
    )  # fmt: skip
    # The one way it becomes fact: `confirm_inferred`'s own write, naming the person (its route's
    # write path; the live file confirms one through the ArcadeDB adapter).

    class _Supersedes:
        async def supersede_edge(self, old: str, new: Any, tx: object, *, old_type: str) -> str:
            self.replaced = (old, new)
            return str(new.id)

    port = _Supersedes()
    await confirm_edge(port, edge, ANALYST, tx="tx")  # type: ignore[arg-type]
    old, replacement = port.replaced
    assert old == stored.id and replacement.type == "SAME_AS"
    assert replacement.provenance.state is ProvenanceState.ASSERTED
    assert replacement.provenance.confirmed_by == ANALYST.id


def test_a_fuzzy_match_is_the_last_step() -> None:
    step = FuzzyMatchStep.model_validate(_step(0.6))
    after = {"id": "renamed", "kind": "derive", "input": "visitor_owner", "column": "o2",
             "operation": "normalise", "columns": ["matched_owner"],
             "settings": {"adapter": "person_name"}}  # fmt: skip
    from schemas.staging import DeriveStep

    problems = staging_rule_violations(
        [step, DeriveStep.model_validate(after)],
        sources=["visits", "owners"], lists=[], dataset_id="pid", marked=(), subscribed=()
    )  # fmt: skip
    assert any("is the last step" in p for p in problems), problems
    assert staging_rule_violations([step], sources=["visits", "owners"], lists=[],
                                   dataset_id="pid", marked=(), subscribed=()) == []  # fmt: skip


@pytest.mark.parametrize(
    ("same_as", "words"),
    [
        ({"left": "visitor", "right": "nobody"}, "does not have"),
        ({"left": "booking", "right": "matched"}, "joins a Document to a Person"),
        ({"left": "matched", "right": "visitor"}, "is written from a matched column"),
    ],
)
def test_the_same_as_names_two_elements_of_one_type_from_the_right_rows(
    same_as: dict[str, str], words: str
) -> None:
    recipe = _recipe(0.6)
    assert fuzzy_link_problems(recipe) == []
    wrong = recipe.model_copy(
        update={"staging": [FuzzyMatchStep.model_validate(_step(0.6, same_as=same_as))]}
    )
    assert any(words in p for p in fuzzy_link_problems(wrong)), fuzzy_link_problems(wrong)


async def test_a_run_whose_same_as_is_wrong_is_refused_before_anything_is_written() -> None:
    wrong = _recipe(0.6).model_copy(
        update={"staging": [FuzzyMatchStep.model_validate(
            _step(0.6, same_as={"left": "visitor", "right": "nobody"})
        )]}
    )  # fmt: skip
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError):
        await _load(wrong, graph)
    assert graph.committed_nodes == [] and graph.committed_edges == []


def test_a_step_with_too_many_pairs_and_no_blocking_key_is_refused() -> None:
    """Rule 2: never truncated; refused in words with the way out."""
    from services.ingest import fuzzy_match
    from services.ingest.staging_catalogue import StagingError

    many = source_table("visits", [{"family": f"N{i}"} for i in range(1100)], load_id="L")
    owners = source_table("owners", [{"owner": f"N{i}"} for i in range(1000)], load_id="O")
    with pytest.raises(StagingError) as refused:
        run_fuzzy_step(FuzzyMatchStep.model_validate(_step(0.6)), many, owners)
    assert any("block_on" in p for p in refused.value.problems)
    assert fuzzy_match.FUZZY_PAIR_LIMIT == 1_000_000
    # With a thousand owners the prior that any one pair matches is one in a thousand, so an exact
    # name alone scores near a half: the threshold is the author's to set (and is the version's).
    blocked = FuzzyMatchStep.model_validate(
        _step(0.4, block_on=[{"left": "family", "right": "owner", "method": "exact"}])
    )
    small = source_table("visits", [{"family": f"N{i}"} for i in range(1100)], load_id="L")
    out, report = run_fuzzy_step(blocked, small, owners)
    assert report.matched == 1000 and report.unmatched == 100 and len(out.rows) == 1100


def test_run_staging_runs_a_fuzzy_match_at_the_real_call_site() -> None:
    result = run_staging(
        [FuzzyMatchStep.model_validate(_step(0.6))], sources=_sources(), lists={}, dataset_id="pid", marked=(),
        subscribed=()
    )
    assert result.reports[0].matched == 3
    assert "match_score" in result.output.columns
