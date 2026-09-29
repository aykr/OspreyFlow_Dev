"""`split_disconnected_communities` — `06_DECISIONS.md` ADR-029's own connected-components fix.

**Why this bypasses Louvain entirely, rather than seeding a graph and hoping it reproduces the
bug.** Checked directly, not assumed: `networkx.algorithms.community.louvain_communities` already
separates two disjoint edges into two communities on a trivial graph with nothing else in it —
confirmed by running it (`{'a','b'}` and `{'c','d'}` came back as two communities, unprompted). A
conformance-level test that only feeds such a graph through the real adapter would pass whether or
not this split pass exists at all, which would be exactly the kind of test that cannot fail
against the defect it claims to guard, a shape this repository already warns against. This
file tests the
*function*, feeding it a partition that is deliberately wrong regardless of what any real Louvain
run would produce, per ADR-029's own naming, named directly rather than left implicit.
"""

from __future__ import annotations

from adapters.compute_rustworkx.communities import split_disconnected_communities


def test_split_disconnected_communities_separates_unconnected_members() -> None:
    node_ids = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("c", "d")]
    # Deliberately wrong: both pairs share one label, as an upstream Louvain call could in
    # principle produce (the exact hazard 01_DOMAIN_MODEL.md §6.3 names for Louvain, absent this
    # fix) even though {a, b} and {c, d} share no edge at all.
    wrong_partition = {"a": 0, "b": 0, "c": 0, "d": 0}

    result = split_disconnected_communities(node_ids, edges, wrong_partition)

    assert result["a"] == result["b"]
    assert result["c"] == result["d"]
    assert result["a"] != result["c"]


def test_split_disconnected_communities_leaves_a_genuinely_connected_group_alone() -> None:
    node_ids = ["a", "b", "c"]
    edges = [("a", "b"), ("b", "c")]
    partition = {"a": 0, "b": 0, "c": 0}

    result = split_disconnected_communities(node_ids, edges, partition)

    assert result["a"] == result["b"] == result["c"]


def test_split_disconnected_communities_keeps_a_true_singleton_as_its_own_group() -> None:
    node_ids = ["a", "b", "isolated"]
    edges = [("a", "b")]
    partition = {"a": 0, "b": 0, "isolated": 1}

    result = split_disconnected_communities(node_ids, edges, partition)

    assert result["a"] == result["b"]
    assert result["isolated"] != result["a"]
