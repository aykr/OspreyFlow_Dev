"""ADR-110 Amendment 8 point 2: each kept row key records what its row wrote.

A full snapshot with *withdraw* takes back exactly a dropped row's elements, so a load must say, per
kept key, the nodes its row wrote or matched and the links it wrote (created or merged into). What a
mistake would do, and the case that catches it:

- a row's record missing a node it only matched (an `on_match: reference` hit, in this load or an
  earlier one), so the node is withdrawn under another row that still names it
  (`test_each_key_records_the_nodes_its_row_wrote_or_matched_and_its_links`,
  `test_a_node_an_earlier_load_wrote_is_recorded_for_the_row_that_matched_it`);
- a link two rows combined into one recorded under only the first row, so the second row's record
  does not keep it (`test_a_link_two_rows_combined_into_is_recorded_under_both`);
- the provisional id a write was sent with recorded instead of the id the store returned
  (`test_a_link_merged_into_an_earlier_loads_records_the_stored_id`);
- an entry for a row that kept no key (held, rejected, already loaded), or none for one that did
  (`test_the_record_has_an_entry_for_exactly_the_kept_keys`);
- the record in a route's answer (`test_no_route_answer_carries_the_row_record`)."""

from __future__ import annotations

from services.api.load_records import report_view
from services.ingest.engine import row_group_keys

from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import (
    LOADER,
    ONTOLOGY,
    ROWS,
    SCHEME,
    KeyStore,
    Sink,
    _load,
    _recipe,
    _row,
)


def _key(row: dict[str, str]) -> str:
    """The row's key as the run makes it (`row_group_keys`, the recipe's own `deduplicate`)."""
    (key,) = row_group_keys(_recipe(), [row])
    assert key is not None
    return key


def _endpoint_ids(graph: MergingGraph) -> dict[str, str]:
    """Each endpoint's value, to the id the graph holds it under."""
    return {str(n.properties["value_normalised"]): n.id for n in graph.committed_nodes}


def _link_between(graph: MergingGraph, a: str, b: str) -> str:
    ids = _endpoint_ids(graph)
    (link,) = [e.id for e in graph.committed_edges if {e.source, e.target} == {ids[a], ids[b]}]
    return link


async def test_each_key_records_the_nodes_its_row_wrote_or_matched_and_its_links() -> None:
    graph = MergingGraph(ONTOLOGY)
    rows = [_row("SYN-1", "SYN-2", 1), _row("SYN-1", "SYN-3", 2)]
    report, _ = await _load(graph, rows, "load-1", Sink(KeyStore()))
    ids = _endpoint_ids(graph)

    first, second = (report.kept_row_elements[_key(r)] for r in rows)
    assert sorted(first.node_ids) == sorted([ids["SYN-1"], ids["SYN-2"]])
    assert first.edge_ids == [_link_between(graph, "SYN-1", "SYN-2")]
    # SYN-1 was written by the first row and only matched by the second: both name it.
    assert sorted(second.node_ids) == sorted([ids["SYN-1"], ids["SYN-3"]])
    assert second.edge_ids == [_link_between(graph, "SYN-1", "SYN-3")]


async def test_a_link_two_rows_combined_into_is_recorded_under_both() -> None:
    graph = MergingGraph(ONTOLOGY)
    rows = [_row("SYN-1", "SYN-2", 1), _row("SYN-1", "SYN-2", 2)]
    report, _ = await _load(graph, rows, "load-1", Sink(KeyStore()))

    link = _link_between(graph, "SYN-1", "SYN-2")
    assert [report.kept_row_elements[_key(r)].edge_ids for r in rows] == [[link], [link]]


async def test_a_node_an_earlier_load_wrote_is_recorded_for_the_row_that_matched_it() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    await _load(graph, [_row("SYN-1", "SYN-2", 1)], "load-1", Sink(store))
    later = _row("SYN-1", "SYN-9", 4)
    report, _ = await _load(graph, [later], "load-2", Sink(store))

    ids = _endpoint_ids(graph)
    assert ids["SYN-1"] not in report.created_node_ids, "matched, not created"
    assert sorted(report.kept_row_elements[_key(later)].node_ids) == sorted(
        [ids["SYN-1"], ids["SYN-9"]]
    )


async def test_a_link_merged_into_an_earlier_loads_records_the_stored_id() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    await _load(graph, [_row("SYN-1", "SYN-2", 1)], "load-1", Sink(store))
    again = _row("SYN-1", "SYN-2", 5)
    report, _ = await _load(graph, [again], "load-2", Sink(store))

    link = _link_between(graph, "SYN-1", "SYN-2")
    assert report.merged_edge_ids == [link]
    assert report.kept_row_elements[_key(again)].edge_ids == [link]


async def test_the_record_has_an_entry_for_exactly_the_kept_keys() -> None:
    graph, store = MergingGraph(ONTOLOGY), KeyStore()
    await _load(graph, ROWS[:1], "load-1", Sink(store))
    # The first row is already loaded; the second is in the file twice.
    rows = [ROWS[0], ROWS[1], ROWS[1], ROWS[2]]
    report, _ = await _load(graph, rows, "load-2", Sink(store))

    assert report.rows_already_loaded == 1
    assert sorted(report.kept_row_elements) == sorted(report.kept_row_keys)
    assert sorted(report.kept_row_elements) == sorted([_key(ROWS[1]), _key(ROWS[2])])


async def test_no_route_answer_carries_the_row_record() -> None:
    graph = MergingGraph(ONTOLOGY)
    report, _ = await _load(graph, ROWS, "load-1", Sink(KeyStore()))
    assert report.kept_row_elements
    view = report_view(report, LOADER, SCHEME).model_dump()
    assert "kept_row_elements" not in view
    words = str(view)
    for elements in report.kept_row_elements.values():
        for element_id in [*elements.node_ids, *elements.edge_ids]:
            assert element_id not in words
