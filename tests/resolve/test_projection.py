"""The τ threshold projection — `spec/01_DOMAIN_MODEL.md` §4."""

from __future__ import annotations

from datetime import UTC, datetime

from services.resolve.projection import compute_clusters, diff_clusters

from schemas.domain import AuditStub, Edge, Handling, Provenance, ProvenanceState, SourceRef


def _edge(edge_type: str, source: str, target: str, score: float | None = None) -> Edge:
    properties = {} if score is None else {"score": score}
    return Edge(
        id=f"{source}-{target}",
        type=edge_type,
        source=source,
        target=target,
        properties=properties,
        provenance=Provenance(
            state=ProvenanceState.INFERRED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
            first_seen=datetime.now(UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
        ),
        audit=AuditStub(created_at=datetime.now(UTC), created_by="analyst-1"),
    )


def _same_as(source: str, target: str, score: float) -> Edge:
    return _edge("SAME_AS", source, target, score)


def _not_same_as(source: str, target: str) -> Edge:
    return _edge("NOT_SAME_AS", source, target)


def test_singleton_nodes_get_their_own_cluster() -> None:
    clusters = compute_clusters(["n1", "n2"], [], [], tau=0.95)
    assert clusters["n1"] != clusters["n2"]


def test_a_same_as_edge_at_or_above_tau_merges_two_nodes() -> None:
    clusters = compute_clusters(["n1", "n2"], [_same_as("n1", "n2", 0.96)], [], tau=0.95)
    assert clusters["n1"] == clusters["n2"]


def test_a_same_as_edge_below_tau_does_not_merge() -> None:
    clusters = compute_clusters(["n1", "n2"], [_same_as("n1", "n2", 0.80)], [], tau=0.95)
    assert clusters["n1"] != clusters["n2"]


def test_raising_tau_can_split_a_cluster_lowering_it_would_have_formed() -> None:
    edges = [_same_as("n1", "n2", 0.85)]
    broad = compute_clusters(["n1", "n2"], edges, [], tau=0.80)
    strict = compute_clusters(["n1", "n2"], edges, [], tau=0.99)
    assert broad["n1"] == broad["n2"]
    assert strict["n1"] != strict["n2"]


def test_transitive_same_as_chains_into_one_cluster() -> None:
    edges = [_same_as("n1", "n2", 0.96), _same_as("n2", "n3", 0.96)]
    clusters = compute_clusters(["n1", "n2", "n3"], edges, [], tau=0.95)
    assert clusters["n1"] == clusters["n2"] == clusters["n3"]


def test_not_same_as_always_wins_over_a_qualifying_same_as_score() -> None:
    clusters = compute_clusters(
        ["n1", "n2"], [_same_as("n1", "n2", 0.999)], [_not_same_as("n1", "n2")], tau=0.95
    )
    assert clusters["n1"] != clusters["n2"]


def test_not_same_as_blocks_only_the_direct_pair_not_the_wider_transitive_chain() -> None:
    """n1-n2 is split; n2-n3 still merges — n1 and n3 end up in different clusters, since nothing
    unions them directly and n2's own split from n1 does not prevent n2 joining n3."""
    edges = [_same_as("n1", "n2", 0.96), _same_as("n2", "n3", 0.96)]
    clusters = compute_clusters(["n1", "n2", "n3"], edges, [_not_same_as("n1", "n2")], tau=0.95)
    assert clusters["n1"] != clusters["n2"]
    assert clusters["n2"] == clusters["n3"]


def test_diff_clusters_reports_zero_when_nothing_changed() -> None:
    before = {"n1": "n1", "n2": "n2"}
    delta = diff_clusters(before, dict(before))
    assert delta.merged == 0
    assert delta.split == 0
    assert delta.nodes_affected == 0


def test_diff_clusters_counts_one_merge_event_for_a_multi_node_collapse() -> None:
    before = {"n1": "n1", "n2": "n2", "n3": "n3"}
    after = {"n1": "n1", "n2": "n1", "n3": "n1"}
    delta = diff_clusters(before, after)
    assert delta.merged == 1
    assert delta.split == 0
    assert delta.nodes_affected == 3


def test_diff_clusters_counts_one_split_event() -> None:
    before = {"n1": "n1", "n2": "n1", "n3": "n1"}
    after = {"n1": "n1", "n2": "n2", "n3": "n3"}
    delta = diff_clusters(before, after)
    assert delta.merged == 0
    assert delta.split == 1
    # All three nodes are affected, not just the two whose cluster-id label changed: n1's own
    # cluster shrank from three members to one, which is as much a visible change for the
    # analyst as n2/n3 each landing in a new singleton.
    assert delta.nodes_affected == 3
