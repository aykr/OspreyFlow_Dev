"""Step 3h (the orchestrator's ruling of 14 November 2026; rule 6, "collapses them at query time"): a node arrives in a
reader's working set with the cluster it is in at the case's τ.

Before, cluster ids reached the canvas only in a threshold or manual-resolution delta, and only for nodes whose
membership changed (`services/resolve/projection.py`'s `diff_clusters`). A pair already merged at the case's τ
therefore never carried one, so *Explain cluster* was never offered for the very pairs it explains. Found live
(`process/lanes/case/gates/live-redesign/RECORD.md`).

**Per reader, never shared (rule 3).** A cluster id is a node id (the cluster's root), and a cluster joined through a
member one reader may not see tells that reader the member is there. So each seed's and expand's clusters are computed
for the reader asking, over the members they may see and the SAME_AS links among them the adapter gives them, and go
back on their own response only (`ExpansionOutcome.clusters`). Nothing is appended to the shared stream, and nothing is
written to the stored nodes.

What fails if each part is wrong: an already-merged pair seeded with no shared cluster id; the second member, seeded
alone after the first, not joining it; a member the reader may not see contributing a cluster id or joining one; the
clusters sent to every reader on the stream, or written to the shared store.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.working_set.models import DeltaReproject
from services.api.working_set.service import WorkingSetService

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Edge,
    ExpandRequest,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)

from .fakes import FakeGraphPort, FakeWorkingSetStore

SCHEME = load_uk_le_scheme()
INVESTIGATION = "inv-1"
CLEARED = Principal(id="analyst-1", clearance="SECRET", org_unit="u")
NOT_CLEARED = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="u")


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification, handling_code="P", originator="u", owning_unit="u"
    )


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="d", locator="l", excerpt_hash="")],
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="analyst-1")


def _person(node_id: str, classification: str = "OFFICIAL") -> Node:
    return Node(
        id=node_id,
        type="Person",
        properties={},
        provenance=_provenance(),
        handling=_handling(classification),
        audit=_audit(),
    )


def _same_as(node_a: str, node_b: str, score: float = 0.999991) -> Edge:
    return Edge(
        id=f"{node_a}-{node_b}",
        type="SAME_AS",
        source=node_a,
        target=node_b,
        properties={"score": score},
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


class AdapterLikeGraph(FakeGraphPort):
    """`expand` as the adapter answers it, for the reader asking (rule 15: the fake refuses what the real one
    refuses): the requested nodes and their neighbours over the requested link types, each node, and each link
    and both its ends, readable by the reader's own body, as `get_nodes` already judges. The shared fake's
    `expand` returns what a test configures whoever asks, which cannot hold a test of two readers."""

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        self.expand_requests.append(req)
        world_nodes, world_edges = self._world_nodes(), self._world_edges()
        asked = set(req.node_ids)
        links = [
            e
            for e in world_edges.values()
            if (not req.edge_types or e.type in req.edge_types)
            and (e.source in asked or e.target in asked)
            and self._edge_readable(principal, e)
            and all(
                end in world_nodes and self._node_readable(principal, world_nodes[end])
                for end in (e.source, e.target)
            )
        ]
        ids = asked | {end for e in links for end in (e.source, e.target)}
        nodes = [
            world_nodes[i]
            for i in sorted(ids)
            if i in world_nodes and self._node_readable(principal, world_nodes[i])
        ]
        return Subgraph(nodes=nodes, edges=links)


def _service(nodes: list[Node], edges: list[Edge]) -> tuple[WorkingSetService, FakeWorkingSetStore]:
    store = FakeWorkingSetStore()
    graph = AdapterLikeGraph(Subgraph(nodes=[], edges=[]), graph_nodes=nodes, graph_edges=edges)
    return WorkingSetService(graph, store, SCHEME), store


def _shared(clusters: DeltaReproject | None, *ids: str) -> str | None:
    """The one cluster id `ids` share in `clusters`, or None if they do not all share one."""
    if clusters is None:
        return None
    found = {clusters.affected_cluster_ids.get(i) for i in ids}
    return found.pop() if len(found) == 1 and None not in found else None


async def test_a_pair_already_merged_at_the_cases_threshold_arrives_with_a_shared_cluster_id() -> (
    None
):
    a, b = _person("p-a"), _person("p-b")
    service, _ = _service([a, b], [_same_as("p-a", "p-b")])
    outcome = await service.seed(INVESTIGATION, [a, b], [], CLEARED)
    assert _shared(outcome.clusters, "p-a", "p-b") is not None


async def test_the_second_member_seeded_alone_joins_the_first_already_on_the_canvas() -> None:
    a, b = _person("p-a"), _person("p-b")
    service, _ = _service([a, b], [_same_as("p-a", "p-b")])
    first = await service.seed(INVESTIGATION, [a], [], CLEARED)
    # One member alone is in no multi-member cluster: nothing to say.
    assert first.clusters is None or "p-a" not in first.clusters.affected_cluster_ids
    second = await service.seed(INVESTIGATION, [b], [], CLEARED)
    assert _shared(second.clusters, "p-a", "p-b") is not None


async def test_a_pair_below_the_threshold_is_two_singletons_and_says_nothing() -> None:
    a, b = _person("p-a"), _person("p-b")
    service, _ = _service([a, b], [_same_as("p-a", "p-b", score=0.5)])
    outcome = await service.seed(INVESTIGATION, [a, b], [], CLEARED)
    assert outcome.clusters is None or not outcome.clusters.affected_cluster_ids


async def test_a_member_hidden_from_the_reader_gives_the_other_no_cluster_id() -> None:
    # The cleared reader puts both on; the reader not cleared for the SECRET member seeds the
    # OFFICIAL one. For them, it is in no cluster: the hidden member neither contributes a cluster
    # id nor joins one, so nothing says it is there (rule 3).
    a, hidden = _person("p-a"), _person("p-z", classification="SECRET")
    service, _ = _service([a, hidden], [_same_as("p-a", "p-z")])
    cleared = await service.seed(INVESTIGATION, [a, hidden], [], CLEARED)
    assert _shared(cleared.clusters, "p-a", "p-z") is not None
    other = await service.seed(INVESTIGATION, [a], [], NOT_CLEARED)
    assert other.clusters is None or not other.clusters.affected_cluster_ids
    # And no value of theirs is the hidden id, whichever key it might sit under.
    assert other.clusters is None or "p-z" not in set(other.clusters.affected_cluster_ids.values())


async def test_the_clusters_go_on_the_readers_own_response_never_the_shared_stream_or_store() -> (
    None
):
    a, b = _person("p-a"), _person("p-b")
    service, store = _service([a, b], [_same_as("p-a", "p-b")])
    outcome = await service.seed(INVESTIGATION, [a, b], [], CLEARED)
    assert outcome.clusters is not None
    deltas = await store.deltas_after(INVESTIGATION, 0) or []
    assert not any(isinstance(d, DeltaReproject) for d in deltas)
    stored = await store.source_fidelity_nodes(INVESTIGATION)
    assert all(n.resolution.cluster_id is None for n in stored.values())


async def test_an_expansion_that_brings_the_other_member_joins_them() -> None:
    a, b = _person("p-a"), _person("p-b")
    service, _ = _service([a, b], [_same_as("p-a", "p-b")])
    await service.seed(INVESTIGATION, [a], [], CLEARED)
    outcome = await service.expand(
        INVESTIGATION, ExpandRequest(node_ids=["p-a"], depth=1, edge_types=["SAME_AS"]), CLEARED
    )
    assert _shared(outcome.clusters, "p-a", "p-b") is not None


async def test_another_readers_threshold_move_gives_no_cluster_id_through_a_member_this_one_may_not_see() -> (
    None
):
    # The leak ADR-124 Amendment 19 closes. V and X are joined only through H, which B is not cleared for. A is,
    # and moves the threshold: A's own answer carries the cluster. B is sent no cluster id for V or X, neither in
    # the stream's delta nor in B's own snapshot: V and X joined, to B, would tell B that something B cannot see
    # joins them (rule 3). Before the amendment the move wrote the cluster onto the case's stored nodes and put
    # it on the shared stream, keys cut to what B may read, values not.
    # The move must change the cluster, or it affects nothing and nothing could leak (the first version of
    # this test moved Balanced to Strict at 0.999991, stayed green with the old path planted back, and so
    # proved nothing: rule 15). Apart at Strict, merged at Balanced: the move joins V, H and X, and the
    # cluster's id is its smallest member's, `p-h`, the hidden one's.
    from services.resolve.projection import THRESHOLD_BALANCED, THRESHOLD_STRICT

    v, h, x = _person("p-v"), _person("p-h", classification="SECRET"), _person("p-x")
    service, store = _service(
        [v, h, x], [_same_as("p-v", "p-h", 0.97), _same_as("p-h", "p-x", 0.97)]
    )
    await store.set_threshold(INVESTIGATION, THRESHOLD_STRICT)
    await service.seed(INVESTIGATION, [v, h, x], [], CLEARED)

    moved = await service.set_resolution_threshold(INVESTIGATION, THRESHOLD_BALANCED, CLEARED)
    assert set(moved.delta.affected_cluster_ids.values()) == {"p-h"}, (
        "the move did not join them, so it tests nothing"
    )
    shared_after = [
        d
        for d in (await store.deltas_after(INVESTIGATION, 0) or [])
        if isinstance(d, DeltaReproject)
    ]
    assert shared_after, "the move put nothing on the shared stream"
    known = await store.source_fidelity_nodes(INVESTIGATION)
    for stored in shared_after:
        sent = service.project_delta(stored, NOT_CLEARED, known)
        assert isinstance(sent, DeltaReproject) and sent.affected_cluster_ids == {}
    (snapshot,) = await service.sync(INVESTIGATION, NOT_CLEARED, last_acknowledged_seq=None)
    assert {n.id: n.resolution.cluster_id for n in snapshot.nodes} == {"p-v": None, "p-x": None}
    # A's own: the three, one cluster.
    (cleared,) = await service.sync(INVESTIGATION, CLEARED, last_acknowledged_seq=None)
    assert len({n.resolution.cluster_id for n in cleared.nodes}) == 1 and None not in {
        n.resolution.cluster_id for n in cleared.nodes
    }


async def test_a_cluster_id_stored_before_the_amendment_reaches_no_reader() -> None:
    # Stored nodes may still carry a cluster_id a threshold move wrote before ADR-124 Amendment 19: it is ignored on
    # every read (`_without_cluster` in `_project`), so no snapshot and no delta sends it, and each reader's own
    # clusters stand in its place.
    v = _person("p-v").model_copy(
        update={"resolution": _person("p-v").resolution.model_copy(update={"cluster_id": "p-h"})}
    )
    x = _person("p-x").model_copy(
        update={"resolution": _person("p-x").resolution.model_copy(update={"cluster_id": "p-h"})}
    )
    service, store = _service([v, x], [])
    await store.add_nodes(INVESTIGATION, [v, x])
    (snapshot,) = await service.sync(INVESTIGATION, NOT_CLEARED, last_acknowledged_seq=None)
    assert {n.id: n.resolution.cluster_id for n in snapshot.nodes} == {"p-v": None, "p-x": None}
    from services.api.working_set.models import DeltaAdd

    sent = service.project_delta(
        DeltaAdd(seq=1, nodes=[v, x], edges=[]),
        NOT_CLEARED,
        await store.source_fidelity_nodes(INVESTIGATION),
    )
    assert all(n.resolution.cluster_id is None for n in sent.nodes)  # type: ignore[union-attr]
