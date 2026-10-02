"""The vault comparison says the two loads agree only when they do (ADR-058 D9).

The records in the "agreeing" case are not hand-written: they are what the real `BulkEdgeLoader`
sends to a store, so the comparison's own recomputation of the weight components is checked
against the loader's, two separate implementations of the same counts. Every kind of difference
is then planted and must be reported (rule 15: a check that has only seen agreement has not been
tested).
"""

from __future__ import annotations

import asyncio
import copy
from typing import Any

from adapters.graph_arcadedb.bulk import BulkEdgeLoader
from scripts import compare_vaults

from tests.adapters.graph_arcadedb.edge_store import make_edge
from tests.adapters.graph_arcadedb.test_bulk_edge_loader import SCHEMA, _store


def _records() -> list[dict[str, Any]]:
    """Edges as the real loader writes them: a to b twice (merged), a to c, d to b."""
    transport = _store("a", "b", "c", "d")
    edges = [make_edge("a", "b", 1), make_edge("a", "b", 2), make_edge("a", "c", 3)]
    edges.append(make_edge("d", "b", 4))
    asyncio.run(BulkEdgeLoader(transport).load(SCHEMA, edges))
    return [dict(row["p"]) for row in transport.written]


def _graph(edges: list[dict[str, Any]]) -> compare_vaults.Graph:
    nodes = [{"id": n, "value_raw": n} for n in "abcd"]
    return compare_vaults.Graph(nodes=nodes, edges=edges)


def _report(
    left: compare_vaults.Graph, right: compare_vaults.Graph
) -> tuple[int, list[str]]:
    lines: list[str] = []
    return compare_vaults.report(left, right, say=lines.append), lines


def test_two_loads_of_the_same_edges_agree() -> None:
    """The baseline: what the loader writes, compared with itself, agrees, and the recomputed
    components match the loader's (degrees 3 and 5 for a to b, total 7, as the conformance case
    expects)."""
    code, lines = _report(_graph(_records()), _graph(copy.deepcopy(_records())))
    assert code == 0 and lines[-1] == "result: the vaults agree"
    assert compare_vaults.component_mismatches(_records()) == []


def _plant(change: Any) -> tuple[int, str]:
    right = _records()
    change(right)
    code, lines = _report(_graph(_records()), _graph(right))
    return code, "\n".join(lines)


def test_a_missing_edge_is_reported() -> None:
    """Catches an edge the bulk path lost."""
    code, text = _plant(lambda rs: rs.pop())
    assert code == 1 and "only in the left vault" in text


def test_an_extra_edge_is_reported() -> None:
    """Catches an edge the bulk path invented, or wrote under a second id."""
    code, text = _plant(lambda rs: rs.append({**rs[0], "id": "edge-extra"}))
    assert code == 1 and "only in the right vault" in text


def test_a_different_occurrence_count_is_reported() -> None:
    """Catches aggregation adding the wrong amount."""
    code, text = _plant(lambda rs: rs[0].update(occurrences=99))
    assert code == 1 and "occurrences is 2 on the left, 99 on the right" in text


def test_a_lost_provenance_source_is_reported() -> None:
    """Catches a merged pair keeping one source row instead of both."""
    code, text = _plant(lambda rs: rs[0]["provenance"]["sources"].pop())
    assert code == 1 and "provenance" in text


def test_a_different_handling_endpoint_or_load_stamp_is_reported() -> None:
    """Catches the fields a bulk row could drop: handling, endpoints, load id and recipe."""
    for change, word in (
        (lambda rs: rs[0]["handling"].update(classification="SECRET"), "handling"),
        (lambda rs: rs[0].update(target="c"), "target"),
        (lambda rs: rs[0]["audit"].update(load_id="other"), "audit"),
        (lambda rs: rs[0]["audit"].update(recipe_id="other"), "audit"),
    ):
        code, text = _plant(change)
        assert code == 1 and word in text, word


def test_the_clock_alone_is_not_a_difference() -> None:
    """Catches a comparison that fails every pair of loads because their timestamps differ."""

    def move_clocks(rs: list[dict[str, Any]]) -> None:
        for r in rs:
            r["audit"]["created_at"] = "2020-01-01T00:00:00Z"
            r["weight_components"]["computed_at"] = "2020-01-01T00:00:00Z"
            r["provenance"]["first_seen"] = "2020-01-01T00:00:00Z"

    assert _plant(move_clocks)[0] == 0


def test_a_stored_degree_that_the_vault_does_not_bear_out_is_reported() -> None:
    """Catches a bulk load weighing against the wrong corpus: a stored degree or total that is
    not what the vault's own edges give."""
    for key in (
        "corpus_source_degree",
        "corpus_target_degree",
        "corpus_total_occurrences",
    ):
        code, text = _plant(
            lambda rs, key=key: rs[1]["weight_components"].update({key: 777})
        )
        assert code == 1 and key in text, key


def test_a_stored_weight_that_does_not_follow_from_its_components_is_reported() -> None:
    """Catches a weight computed from different numbers than the ones stored beside it."""
    code, text = _plant(lambda rs: rs[0].update(weight=rs[0]["weight"] + 0.25))
    assert code == 1 and "components give" in text


def test_a_reverted_edge_is_not_part_of_the_vaults_corpus() -> None:
    """Catches degrees that count an edge the product treats as gone."""
    records = _records()
    records.append({**records[0], "id": "gone", "reverted": True, "occurrences": 50})
    assert compare_vaults.component_mismatches(records) == []


def test_ids_stored_twice_are_counted_on_each_side_and_do_not_fail_the_comparison() -> (
    None
):
    """The stray-record defect is the store's and parked (ADR-056 Amendment 19): it is reported on
    each side so the bulk path's rate can be read against the upsert path's, but a stray copy of
    an otherwise identical edge is not a difference between the loads."""
    left = _records()
    right = _records()
    right.append(copy.deepcopy(right[0]))
    code, lines = _report(_graph(left), _graph(right))
    assert any("left 0, right 1" in line for line in lines)
    assert compare_vaults.stored_twice(right) == [right[0]["id"]]
    assert code == 0


def test_an_empty_right_vault_is_a_difference_not_agreement() -> None:
    """Catches comparing against a vault that was never loaded and calling it equal."""
    code, text = _plant(lambda rs: rs.clear())
    assert code == 1 and "only in the left vault" in text
