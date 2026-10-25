"""ADR-127 decision 6: a load's record says which links it created and, separately, which existing
links it merged occurrences into. A revert marks the created ones reverted and refuses a load that
merged into another load's link, because that would take back data the other load wrote, and the
occurrence counts of a merged link cannot be split (Amendment 5). What a mistake would do:

- a merge counted as created, so a revert reverts another load's link
  (`test_a_second_load_merging_into_the_first_loads_link_records_it_as_merged_not_created`);
- a load's own repeated write to its own link counted as a merge, so every load with a repeated pair
  would be refused its own revert (`test_a_load_merging_into_its_own_link_is_not_a_merge`);
- a `HOLDS` link, whose id is fixed by its two ends and so cannot tell a new link from a merged
  one, counted as created for a holder an earlier load wrote
  (`test_a_content_link_from_an_existing_holder_is_recorded_as_merged`);
- a held content `Document`, whose id is `content:<hash of its bytes>` and so is the same for the
  same text from another holder, an earlier load or a Files-tab upload, counted as created when it
  already exists, so a revert marks reverted a document another load holds
  (`test_a_content_document_that_already_exists_is_recorded_as_merged_not_created`);
- an undirected link written the other way round, or a link written after its predecessor was
  reverted, judged differently from how the store judges it
  (`test_an_undirected_link_written_the_other_way_round_is_a_merge`,
  `test_a_write_after_the_link_was_reverted_is_a_new_link`);
- the stamp that tells a revert the load's events can be retracted missing
  (`test_the_record_says_its_events_were_stamped`).

The run is `load_with_rules` against the shared merging graph stand-in (`recipe_test_support.py`'s
`MergingGraph`), which merges as `upsert_edges` does (`graph_arcadedb/adapter.py`,
`_find_existing_edge`): a second write of the same type between the same two parties merges into the
first link when both have one audience (ADR-102 Amendment 3), an undirected type merges a write the
other way round too, and a reverted or superseded link is not merged into. The plain stand-in keeps
every write, which would make each merge case here vacuous (rule 15)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from services.api.studio_publish import load_with_rules
from services.ingest.load_ledger import load_record_from_report

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Principal
from schemas.ingest import LoadReport, Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    ValidatingGraph,
    local_staging,
)

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


def _endpoint(ref: str, column: str, *, content: bool = False) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "ref": ref,
        "pole_class": "object",
        "type": "Endpoint",
        "match_on": "value_normalised",
        "on_match": "reference",
        "properties": {
            "value_normalised": {"field": column},
            "endpoint_kind": {"literal": "account"},
        },
    }
    if content:
        entity["content"] = {"kind": "document_text", "field": "memo"}
    return entity


def _person(ref: str, column: str) -> dict[str, Any]:
    return {
        "ref": ref,
        "pole_class": "person",
        "type": "Person",
        "match_on": "nino",
        "on_match": "reference",
        "properties": {"nino": {"field": column}, "family_name": {"literal": "Synthetic"}},
    }


def _associates() -> Recipe:
    """Two people and an undirected `ASSOCIATE_OF` between them."""
    recipe = _recipe()
    document = recipe.model_dump(by_alias=True)
    document["row_template"] = {
        "entities": [_person("a", "payer"), _person("b", "payee")],
        "edges": [{"type": "ASSOCIATE_OF", "from": "a", "to": "b"}],
    }
    return Recipe.model_validate(document)


def _recipe(*, content: bool = False) -> Recipe:
    return Recipe.model_validate(
        {
            "id": "private-cash",
            "version": 1,
            "label": "Private cash",
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
                "entities": [_endpoint("from", "payer", content=content), _endpoint("to", "payee")],
                "edges": [
                    {
                        "type": "TRANSACTED",
                        "from": "from",
                        "to": "to",
                        "temporal": {"at": {"field": "paid_at", "transform": "datetime"}},
                    }
                ],
            },
        }
    )


def _row(payer: str, payee: str, day: int, memo: str = "") -> dict[str, str]:
    return {
        "payer": payer,
        "payee": payee,
        "paid_at": f"2026-03-0{day}T09:00:00+00:00",
        "memo": memo,
    }


async def _load(
    graph: ValidatingGraph,
    rows: list[dict[str, str]],
    load_id: str,
    *,
    content: bool = False,
    recipe: Recipe | None = None,
) -> LoadReport:
    report, _events, _held = await load_with_rules(
        recipe or _recipe(content=content),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope="case-1",
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
    )
    assert report.rejections == [], report.rejections
    return report


async def test_a_first_load_records_its_links_as_created_and_none_as_merged() -> None:
    graph = MergingGraph(ONTOLOGY)
    report = await _load(graph, [_row("SYN-1", "SYN-2", 1), _row("SYN-3", "SYN-4", 2)], "load-1")
    assert len(report.created_edge_ids) == 2
    assert report.merged_edge_ids == []
    assert sorted(report.touched_edge_ids) == sorted(report.created_edge_ids)


async def test_a_second_load_merging_into_the_first_loads_link_records_it_as_merged_not_created() -> None:
    graph = MergingGraph(ONTOLOGY)
    first = await _load(graph, [_row("SYN-1", "SYN-2", 1)], "load-1")
    second = await _load(graph, [_row("SYN-1", "SYN-2", 2), _row("SYN-5", "SYN-6", 3)], "load-2")
    (earlier,) = first.created_edge_ids
    assert second.merged_edge_ids == [earlier]
    assert earlier not in second.created_edge_ids
    assert len(second.created_edge_ids) == 1, "the new pair is this load's own link"
    assert sorted(second.touched_edge_ids) == sorted([earlier, *second.created_edge_ids])


async def test_a_load_merging_into_its_own_link_is_not_a_merge() -> None:
    graph = MergingGraph(ONTOLOGY)
    report = await _load(
        graph, [_row("SYN-1", "SYN-2", 1), _row("SYN-1", "SYN-2", 2)], "load-1"
    )
    assert len(report.created_edge_ids) == 1
    assert report.merged_edge_ids == []


async def test_a_content_link_from_a_new_holder_is_created() -> None:
    graph = MergingGraph(ONTOLOGY)
    report = await _load(graph, [_row("SYN-1", "SYN-2", 1, memo="a note")], "load-1", content=True)
    holds = [e for e in graph.committed_edges if e.type == "HOLDS"]
    assert len(holds) == 1
    assert holds[0].id in report.created_edge_ids
    assert report.merged_edge_ids == []


async def test_a_content_link_from_an_existing_holder_is_recorded_as_merged() -> None:
    """The holder `SYN-1` is an earlier load's, and the port cannot say whether this load's `HOLDS`
    link from it is new (its id is fixed by its ends, so the id returned is the id sent either
    way). It is recorded as merged, so a revert refuses naming it rather than risk taking back a
    link another load wrote."""
    graph = MergingGraph(ONTOLOGY)
    await _load(graph, [_row("SYN-1", "SYN-2", 1)], "load-1")
    report = await _load(graph, [_row("SYN-1", "SYN-9", 2, memo="a note")], "load-2", content=True)
    holds = [e for e in graph.committed_edges if e.type == "HOLDS"]
    assert len(holds) == 1
    assert holds[0].id in report.merged_edge_ids
    assert holds[0].id not in report.created_edge_ids


async def test_the_record_keeps_created_and_merged_apart_and_says_its_events_were_stamped() -> None:
    graph = MergingGraph(ONTOLOGY)
    first = await _load(graph, [_row("SYN-1", "SYN-2", 1)], "load-1")
    second = await _load(graph, [_row("SYN-1", "SYN-2", 2), _row("SYN-5", "SYN-6", 3)], "load-2")
    now = datetime(2026, 10, 25, tzinfo=UTC)
    record = load_record_from_report(
        second,
        source="private_cash.csv",
        created_by="loader-1",
        started_at=now,
        now=now,
        investigation_id="case-1",
    )
    assert record.created_edge_ids == second.created_edge_ids
    assert record.merged_edge_ids == first.created_edge_ids
    assert record.created_node_ids == second.created_node_ids
    assert record.investigation_id == "case-1"
    assert record.released_from is None
    assert record.events_stamped is True


def test_a_record_with_no_stamp_marker_reads_as_not_stamped() -> None:
    """A record written before events carried a `load_id` has no `events_stamped`, and must read as
    false, not as true: the revert refuses it (Amendment 5)."""
    from schemas.ingest import LoadRecord

    old = LoadRecord.model_validate(
        {
            "load_id": "old",
            "recipe_id": "r",
            "recipe_version": 1,
            "source": "s",
            "started_at": "2026-01-01T00:00:00Z",
            "created_by": "loader-1",
        }
    )
    assert old.events_stamped is False
    assert old.released_from is None and old.merged_edge_ids == []


async def test_a_content_document_that_already_exists_is_recorded_as_merged_not_created() -> None:
    """The document's id is `content:<hash of the bytes>`, so a second holder of the same text, in
    the same load or a later one, names the document the first one wrote. A later load's upsert
    merges into it, and a revert must not take it back."""
    graph = MergingGraph(ONTOLOGY)
    first = await _load(graph, [_row("SYN-1", "SYN-2", 1, memo="a note")], "load-1", content=True)
    second = await _load(graph, [_row("SYN-7", "SYN-8", 2, memo="a note")], "load-2", content=True)
    (document,) = [n for n in graph.committed_nodes if n.type == "Document"][:1]
    assert document.id in first.created_node_ids
    assert document.id in second.merged_node_ids
    assert document.id not in second.created_node_ids
    assert second.nodes_referenced >= 1
    # The new holder is this load's own, so its link to the shared document is its own too.
    second_holds = [e for e in graph.committed_edges if e.type == "HOLDS"][1:]
    assert second_holds and all(e.id in second.created_edge_ids for e in second_holds)


async def test_a_content_document_written_fresh_is_created_and_once_per_load() -> None:
    graph = MergingGraph(ONTOLOGY)
    report = await _load(
        graph,
        [_row("SYN-1", "SYN-2", 1, memo="a note"), _row("SYN-3", "SYN-4", 2, memo="a note")],
        "load-1",
        content=True,
    )
    documents = [n for n in graph.committed_nodes if n.type == "Document"]
    assert len(documents) == 1
    assert report.created_node_ids.count(documents[0].id) == 1
    assert report.merged_node_ids == []


async def test_an_undirected_link_written_the_other_way_round_is_a_merge() -> None:
    graph = MergingGraph(ONTOLOGY)
    recipe = _associates()
    first = await _load(graph, [{"payer": "AB123456C", "payee": "AB654321D"}], "load-1", recipe=recipe)
    second = await _load(graph, [{"payer": "AB654321D", "payee": "AB123456C"}], "load-2", recipe=recipe)
    (earlier,) = first.created_edge_ids
    assert second.merged_edge_ids == [earlier] and second.created_edge_ids == []


async def test_a_write_after_the_link_was_reverted_is_a_new_link() -> None:
    graph = MergingGraph(ONTOLOGY)
    first = await _load(graph, [_row("SYN-1", "SYN-2", 1)], "load-1")
    graph.reverted.update(first.created_edge_ids)
    second = await _load(graph, [_row("SYN-1", "SYN-2", 2)], "load-2")
    assert len(second.created_edge_ids) == 1
    assert second.created_edge_ids != first.created_edge_ids
    assert second.merged_edge_ids == []


class BlindGraph(MergingGraph):
    """A store whose access-filtered reads show this loader nothing: `get_nodes` finds no node, as
    for a loader cleared for none of what is there. The unfiltered `existing_node_ids` still does."""

    async def get_nodes(self, node_ids: Any, principal: Any) -> list[Any]:
        return []


async def test_a_content_document_the_loader_cannot_read_is_still_recorded_as_merged() -> None:
    """The document an earlier load wrote is at a marking this loader may not read. An
    access-filtered lookup would find it absent, record it as created, and a revert would take it
    back from the load that holds it."""
    graph = BlindGraph(ONTOLOGY)
    await _load(graph, [_row("SYN-1", "SYN-2", 1, memo="a note")], "load-1", content=True)
    second = await _load(graph, [_row("SYN-7", "SYN-8", 2, memo="a note")], "load-2", content=True)
    (document,) = [n for n in graph.committed_nodes if n.type == "Document"][:1]
    assert document.id in second.merged_node_ids
    assert document.id not in second.created_node_ids


def _counts(report: LoadReport) -> tuple[int, int, int]:
    return report.nodes_created, report.nodes_referenced, report.edges_created


async def test_the_counts_say_nothing_of_a_content_document_the_loader_cannot_read() -> None:
    """Rule 3: `LoadReportView` returns `nodes_created` and `nodes_referenced`. A loader not cleared
    for the document an earlier load wrote must get the counts of a store that never held it: if
    the unfiltered answer moved a count, the loader would learn that the content exists somewhere
    they may not look. A loader who may read it is told it was referenced."""
    rows = [_row("SYN-7", "SYN-8", 2, memo="a note")]
    fresh = await _load(MergingGraph(ONTOLOGY), rows, "load-2", content=True)

    async def second_load(graph: MergingGraph) -> LoadReport:
        await _load(graph, [_row("SYN-1", "SYN-2", 1, memo="a note")], "load-1", content=True)
        return await _load(graph, rows, "load-2", content=True)

    blind = await second_load(BlindGraph(ONTOLOGY))
    seeing = await second_load(MergingGraph(ONTOLOGY))
    assert _counts(blind) == _counts(fresh), "no more and no less than a store without it"
    assert seeing.nodes_referenced == fresh.nodes_referenced + 1
    assert seeing.nodes_created == fresh.nodes_created - 1
    assert seeing.edges_created == fresh.edges_created
    # The record still says what the unfiltered check found, for either loader.
    assert blind.merged_node_ids == seeing.merged_node_ids != []
    assert not set(blind.merged_node_ids) & set(blind.created_node_ids)


class BlindToEdges(MergingGraph):
    """A loader cleared for none of the links already there: `get_edges` shows them nothing, while
    the edge upsert (which is not access-filtered) still merges into them."""

    async def get_edges(self, edge_ids: Any, principal: Any) -> list[Any]:
        return []


async def test_the_counts_say_nothing_of_a_link_the_loader_cannot_read() -> None:
    """Rule 3: the edge upsert is unfiltered, so when a loader writes A-B while a link they may not
    read already joins A and B, the store merges into it. If `edges_created` did not rise, the
    loader would learn, from `LoadReportView` and the ledger's count, that such a link exists. A
    loader who cannot read it gets the counts of a store without it; one who can read it is told
    the link was not created. Both records name it as merged."""

    firsts: list[LoadReport] = []

    async def second_load(graph: MergingGraph, first_rows: list[dict[str, str]]) -> LoadReport:
        firsts.append(await _load(graph, first_rows, "load-1"))
        return await _load(graph, [_row("SYN-1", "SYN-2", 3)], "load-2")

    # The control holds the same endpoints but no link between them: its second load creates one.
    control_rows = [_row("SYN-1", "SYN-8", 1), _row("SYN-9", "SYN-2", 2)]
    existing_rows = [_row("SYN-1", "SYN-2", 1), _row("SYN-1", "SYN-8", 2), _row("SYN-9", "SYN-2", 2)]
    control = await second_load(MergingGraph(ONTOLOGY), control_rows)
    blind = await second_load(BlindToEdges(ONTOLOGY), existing_rows)
    seeing = await second_load(MergingGraph(ONTOLOGY), existing_rows)

    assert _counts(blind) == _counts(control), "no more and no less than a store without the link"
    assert control.edges_created == 1
    assert seeing.edges_created == control.edges_created - 1 == 0
    _, blind_first, seeing_first = firsts
    for report, first in ((blind, blind_first), (seeing, seeing_first)):
        # The first load's A-B link is its first row's: the one the second load merged into.
        assert report.merged_edge_ids == [first.created_edge_ids[0]], "the record keeps the true split"
        assert report.created_edge_ids == []


def _at(classification: str) -> Recipe:
    """The private-cash recipe with every element marked `classification`."""
    recipe = _recipe()
    handling = {**recipe.defaults.handling, "classification": classification}
    return recipe.model_copy(update={"defaults": recipe.defaults.model_copy(update={"handling": handling})})


async def test_a_write_of_another_audience_is_recorded_as_created_and_the_same_one_as_merged() -> None:
    """ADR-102 Amendment 3 and the record: a SECRET write onto an OFFICIAL link is a link of its own
    and so created, not merged; a second OFFICIAL write still merges into the first and is merged."""
    graph = MergingGraph(ONTOLOGY)
    first = await _load(graph, [_row("SYN-1", "SYN-2", 1)], "load-1")
    secret = await _load(graph, [_row("SYN-1", "SYN-2", 2)], "load-2", recipe=_at("SECRET"))
    official = await _load(graph, [_row("SYN-1", "SYN-2", 3)], "load-3")
    (original,) = first.created_edge_ids
    assert len(secret.created_edge_ids) == 1 and secret.merged_edge_ids == []
    assert secret.created_edge_ids != [original]
    assert official.merged_edge_ids == [original] and official.created_edge_ids == []
    assert len([e for e in graph.committed_edges if e.type == "TRANSACTED"]) == 2


async def test_a_content_link_in_another_audience_gets_a_new_id_and_is_recorded_as_created() -> None:
    """`HOLDS` has an id derived from its two ends. A second load of the same text from the same
    holder, at another classification, cannot merge into the first load's link (another audience)
    and cannot create under its id (unique): it is a link of its own under a new id. The holder
    exists already, so the id alone cannot say the link is new; the id the store returned can: it is
    not the one sent, so the link is the load's own."""
    graph = MergingGraph(ONTOLOGY)
    await _load(graph, [_row("SYN-1", "SYN-2", 1, memo="a note")], "load-1", content=True)
    second_recipe = _at("SECRET").model_copy(
        update={"row_template": _recipe(content=True).row_template}
    )
    second = await _load(graph, [_row("SYN-1", "SYN-2", 2, memo="a note")], "load-2", recipe=second_recipe)
    holds = [e for e in graph.committed_edges if e.type == "HOLDS"]
    assert len(holds) == 2 and len({e.id for e in holds}) == 2
    held_by_second = [e for e in holds if e.handling.classification == "SECRET"]
    assert len(held_by_second) == 1
    assert held_by_second[0].id in second.created_edge_ids
    assert held_by_second[0].id not in second.merged_edge_ids
