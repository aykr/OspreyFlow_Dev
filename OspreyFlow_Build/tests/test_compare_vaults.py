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

from scripts import compare_vaults

from adapters.graph_arcadedb.bulk import BulkEdgeLoader
from ontology.handling import load_uk_le_scheme
from tests.adapters.graph_arcadedb.edge_store import make_edge
from tests.adapters.graph_arcadedb.test_bulk_edge_loader import SCHEMA, _store


def _records() -> list[dict[str, Any]]:
    """Edges as the real loader writes them: a to b twice (merged), a to c, d to b."""
    transport = _store("a", "b", "c", "d")
    edges = [make_edge("a", "b", 1), make_edge("a", "b", 2), make_edge("a", "c", 3)]
    edges.append(make_edge("d", "b", 4))
    asyncio.run(BulkEdgeLoader(transport, handling_scheme=load_uk_le_scheme()).load(SCHEMA, edges))
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


# --- three readings of one store (ADR-058 Amendment 6) ---------------------------------------


def test_the_three_readings_of_stray_copies_are_reported_side_by_side() -> None:
    """Seen: the load's `GROUP BY id` check found 6 ids stored twice, the paged scan found none.
    The report now carries the scan, the `GROUP BY id` and the plain count for each vault, so a
    disagreement between them is on the page and not a guess."""
    base = _records()
    left = compare_vaults.Graph(
        nodes=_graph(base).nodes, edges=base, grouped_twice=[], counted=len(base)
    )
    right = compare_vaults.Graph(
        nodes=_graph(base).nodes,
        edges=copy.deepcopy(base),
        grouped_twice=["x", "y", "z"],
        counted=len(base) + 3,
    )
    code, lines = _report(left, right)
    text = "\n".join(lines)
    assert "GROUP BY id (the load's own check): left 0, right 3" in text
    assert f"count(*): left {len(base)}, right {len(base) + 3}" in text
    assert "the readings disagree" in text
    assert code == 0, (
        "a stray copy is the store's defect, not a difference between the loads"
    )


def test_readings_that_agree_say_so_and_a_vault_without_them_is_not_blamed() -> None:
    base = _records()
    both = compare_vaults.Graph(
        nodes=_graph(base).nodes, edges=base, grouped_twice=[], counted=len(base)
    )
    _, lines = _report(both, both)
    assert "the three readings agree" in "\n".join(lines)
    _, lines = _report(_graph(base), _graph(base))
    assert "GROUP BY id" not in "\n".join(lines)


class _Store:
    """A store that answers only the query shapes the scan sends, and refuses any other (rule 15:
    the real parser refuses `count(*)` over a subquery, so this one does too). It also models what
    the twin showed: a read ordered by `id` is answered from the id index, one record per id,
    while a read with no ordering walks the records and meets a stray copy too."""

    def __init__(self, edges: list[dict[str, Any]], stray_ids: list[str]) -> None:
        self.edges, self.stray_ids, self.seen = edges, stray_ids, []
        self.strays = [dict(e) for e in self.edges if e["id"] in stray_ids]

    async def sql(self, query: str) -> list[dict[str, Any]]:
        self.seen.append(query)
        if "(SELECT" in query:
            raise RuntimeError("parser refuses a subquery here")
        if query.startswith("SELECT count(*) AS n FROM "):
            return [{"n": len(self.edges) + len(self.stray_ids)}]
        if "GROUP BY id" in query:
            return [{"id": i, "n": 2} for i in self.stray_ids]
        if query.startswith("SELECT FROM"):
            skip = int(query.split("SKIP ")[1].split()[0])
            limit = int(query.split("LIMIT ")[1])
            if "Endpoint" in query:
                rows = [{"id": n} for n in "abcd"]
            elif "ORDER BY id" in query:
                rows = self.edges
            else:
                rows = self.edges + self.strays
            return rows[skip : skip + limit]
        raise RuntimeError(f"unexpected query: {query}")


def test_the_scan_asks_the_store_for_all_three_readings() -> None:
    edges = _records()
    stray = [edges[0]["id"], edges[1]["id"]]
    store = _Store(edges, stray_ids=stray)
    graph = asyncio.run(compare_vaults.scan_with(store))
    assert graph.grouped_twice == stray
    assert graph.counted == len(edges) + 2
    assert any("GROUP BY id" in q for q in store.seen)


def test_the_scan_walks_the_records_so_that_a_stray_copy_is_seen_by_all_three_readings() -> (
    None
):
    """Seen on the twin: the paged read was ordered by `id`, which the store answers from the id
    index, so it found one record per id (13,068) while `count(*)` found 13,074 and `GROUP BY id`
    named 6 ids twice. A comparison that cannot see a stray copy cannot count it."""
    edges = _records()
    stray = sorted([edges[0]["id"], edges[1]["id"]])
    store = _Store(edges, stray_ids=stray)
    graph = asyncio.run(compare_vaults.scan_with(store))
    assert len(graph.edges) == len(edges) + 2
    assert compare_vaults.stored_twice(graph.edges) == stray
    left = compare_vaults.Graph(
        nodes=graph.nodes, edges=graph.edges, grouped_twice=stray, counted=graph.counted
    )
    _, lines = _report(left, left)
    assert "the three readings agree" in "\n".join(lines)


def test_a_group_by_that_finds_ids_the_scan_does_not_is_a_disagreement_on_its_own() -> (
    None
):
    """The case seen on the twin: `GROUP BY id` names ids stored twice while the scan and the
    count both show one record per id. Each reading alone looks sound; only the three together
    show it."""
    base = _records()
    nodes = _graph(base).nodes
    left = compare_vaults.Graph(
        nodes=nodes, edges=base, grouped_twice=[], counted=len(base)
    )
    right = compare_vaults.Graph(
        nodes=nodes, edges=copy.deepcopy(base), grouped_twice=["x"], counted=len(base)
    )
    _, lines = _report(left, right)
    assert "the readings disagree" in "\n".join(lines)


def test_the_recompute_uses_the_store_s_rules_and_counts_a_self_loop_twice() -> None:
    """ADR-120 Amendment 4. Catches a recomputation that (a) weighs with another type's rule than
    the one the vault's edges carry (the scan reads TRANSACTED, heavy at 6; the default rule is
    heavy at 10, so a weight under it is not the stored one), and (b) counts a self-loop once in
    its node's degree, as it did, where the adapter and the bulk loader count it twice and weigh it
    with no mutual-information term."""
    from adapters.graph_arcadedb.weight import compute_weight
    from ontology.weights import load_weight_rules
    from schemas.domain import WeightComponents

    transport = _store("a", "b")
    edges = [make_edge("a", "a", 1).model_copy(update={"occurrences": 3}), make_edge("a", "b", 2)]
    asyncio.run(BulkEdgeLoader(transport, handling_scheme=load_uk_le_scheme()).load(SCHEMA, edges))
    records = [dict(row["p"]) for row in transport.written]
    by_id = {str(r["id"]): r for r in records}
    loop, pair = by_id["edge-1"], by_id["edge-2"]

    # (b) the self-loop's 3 occurrences are counted twice at `a`, plus the other link's 1.
    assert loop["weight_components"]["corpus_source_degree"] == 7
    recomputed = compare_vaults.recomputed_components(records)
    assert recomputed["edge-1"]["corpus_source_degree"] == 7
    assert recomputed["edge-1"]["corpus_target_degree"] == 7
    assert recomputed["edge-2"]["corpus_source_degree"] == 7
    assert recomputed["edge-2"]["corpus_target_degree"] == 1
    assert compare_vaults.component_mismatches(records) == []

    # (a) the stored weight of `pair` is the TRANSACTED rule's for its own components; the same
    # components under the default rule (heavy 10, not 6) give another weight, and planting that
    # on the very record whose components produced it is a mismatch only because of the rule.
    rules = load_weight_rules()
    assert rules.rule_for("TRANSACTED")[0] == "TRANSACTED"
    components = WeightComponents.model_validate(pair["weight_components"])
    assert components.parameter_set == f"{rules.version}/TRANSACTED"
    under_default = compute_weight(
        components,
        edge_type="USES",
        valid_to=None,
        now=components.computed_at,
        rules=rules,
        self_loop=False,
    )
    assert abs(under_default - float(pair["weight"])) > 1e-6
    planted = copy.deepcopy(records)
    (target,) = (r for r in planted if r["id"] == pair["id"])
    target["weight"] = under_default
    assert target["weight_components"] == pair["weight_components"]
    lines = compare_vaults.component_mismatches(planted)
    assert len(lines) == 1 and pair["id"] in lines[0] and "components give" in lines[0]


# --- each weight is recomputed under the version its parameter set names (ADR-120 Amendment 4) ---


def _two_version_history(tmp_path: Any) -> Any:
    """The shipped version 1, and a version 2 with another beta and alpha (midpoint and scale
    re-derived): a weight computed under version 1 is not the one version 2 gives. (Beta alone
    would not do: at recency 1 a beta change cancels against the midpoint it moves.)"""
    import yaml

    from tests.adapters.graph_arcadedb.test_weight_rules import FROZEN, _raw_versions

    first = _raw_versions(FROZEN)[0]
    second = copy.deepcopy(first)
    second.update(version=2, alpha=0.6, beta=0.3, midpoint=0.3 + 0.6 / 3, scale=0.6 / 3)
    path = tmp_path / "weights.yaml"
    path.write_text(yaml.safe_dump({"versions": [first, second]}), encoding="utf-8")
    return path


def test_a_weight_is_recomputed_under_the_version_its_parameter_set_names(tmp_path: Any) -> None:
    """Catches a recomputation that always uses the latest version: weights stored under version 1
    are not mismatches once a version 2 exists, and a stored weight that is version 1's under a
    parameter set naming version 2 is one. A version the file does not hold is a mismatch too."""
    path = _two_version_history(tmp_path)
    records = _records()
    assert all(r["weight_components"]["parameter_set"] == "1/TRANSACTED" for r in records)
    assert compare_vaults.component_mismatches(records, weights_path=path) == []

    relabelled = copy.deepcopy(records)
    relabelled[0]["weight_components"]["parameter_set"] = "2/TRANSACTED"
    lines = compare_vaults.component_mismatches(relabelled, weights_path=path)
    assert len(lines) == 1 and relabelled[0]["id"] in lines[0] and "components give" in lines[0]

    unknown = copy.deepcopy(records)
    unknown[0]["weight_components"]["parameter_set"] = "3/TRANSACTED"
    lines = compare_vaults.component_mismatches(unknown, weights_path=path)
    assert len(lines) == 1 and "3/TRANSACTED" in lines[0] and "parameter_set" in lines[0]


def test_a_component_with_no_parameter_set_is_legacy_and_not_a_mismatch() -> None:
    """Catches a legacy component (written before ADR-120) being recomputed under today's rules and
    reported as a weight mismatch, or counted against the run: it is listed apart, with its
    weight left alone, and the run's status reflects only real mismatches."""
    records = _records()
    legacy = copy.deepcopy(records)
    for r in legacy:
        r["weight_components"].pop("parameter_set")
        r["weight"] = 0.123  # not what any rule gives, and not to be recomputed
    assert compare_vaults.component_mismatches(legacy) == []
    assert compare_vaults.legacy_components(legacy) == sorted(str(r["id"]) for r in legacy)
    assert compare_vaults.legacy_components(records) == []

    code, lines = _report(_graph(_records()), _graph(legacy))
    text = "\n".join(lines)
    assert code == 0, text
    assert f"{len(legacy)} component(s) stored before ADR-120" in text and "legacy" in text

    # A real mismatch beside the legacy ones still fails the run.
    mixed = copy.deepcopy(legacy)
    mixed[0]["weight_components"]["parameter_set"] = "1/TRANSACTED"
    mixed[0]["weight"] += 0.25
    code, lines = _report(_graph(_records()), _graph(mixed))
    assert code == 1 and "components give" in "\n".join(lines)


def test_a_parameter_set_naming_another_rule_is_a_mismatch() -> None:
    """Catches a vault of TRANSACTED links whose components say another rule computed them: the
    weight would be right for that rule and the label wrong, so it is reported as a mismatch."""
    records = _records()
    planted = copy.deepcopy(records)
    planted[0]["weight_components"]["parameter_set"] = "1/default"
    lines = compare_vaults.component_mismatches(planted)
    assert len(lines) == 1
    assert planted[0]["id"] in lines[0] and "parameter_set" in lines[0]
    assert "1/default" in lines[0] and "1/TRANSACTED" in lines[0]
    code, _ = _report(_graph(_records()), _graph(planted))
    assert code == 1


def test_a_legacy_component_is_skipped_entirely() -> None:
    """Catches a legacy component (no parameter_set, written before ADR-120) being held to today's
    counts: a self-loop stored when an upsert counted it once has a smaller stored degree than the
    store gives now, and that is not a mismatch. Nothing about it is compared or recomputed; it is
    reported as legacy only."""
    transport = _store("a", "b")
    edges = [make_edge("a", "a", 1).model_copy(update={"occurrences": 3}), make_edge("a", "b", 2)]
    asyncio.run(BulkEdgeLoader(transport, handling_scheme=load_uk_le_scheme()).load(SCHEMA, edges))
    records = [dict(row["p"]) for row in transport.written]
    loop = next(r for r in records if r["id"] == "edge-1")
    assert loop["weight_components"]["corpus_source_degree"] == 7
    for r in records:
        r["weight_components"].pop("parameter_set")
    # What an upsert stored before it counted a loop twice: 3 once, plus the other link's 1.
    loop["weight_components"]["corpus_source_degree"] = 4
    loop["weight_components"]["corpus_target_degree"] = 4
    loop["weight"] = 0.123

    assert compare_vaults.component_mismatches(records) == []
    assert compare_vaults.legacy_components(records) == ["edge-1", "edge-2"]
    code, lines = _report(_graph(copy.deepcopy(records)), _graph(records))
    assert code == 0, "\n".join(lines)


def test_the_legacy_line_lists_the_first_ids_like_the_mismatch_lines() -> None:
    """Catches a legacy count with no ids to look at: the report prints the first `show` legacy ids
    and how many more, as it does for mismatches."""
    legacy = _records()
    for r in legacy:
        r["weight_components"].pop("parameter_set")
    ids = sorted(str(r["id"]) for r in legacy)
    assert len(ids) == 3
    lines: list[str] = []
    compare_vaults.report(_graph(_records()), _graph(legacy), say=lines.append, show=2)
    start = next(
        i for i, line in enumerate(lines) if "3 component(s) stored before ADR-120" in line
    )
    assert [line.strip() for line in lines[start + 1 : start + 4]] == [
        ids[0],
        ids[1],
        "... and 1 more",
    ]
