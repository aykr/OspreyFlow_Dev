"""`WorkingSetService` — `spec/03_CONDUIT_MIDDLEWARE.md` §4,
this phase's exit criterion. Exercises the cap check, the expansion's outcome (which carries no
count of what the filter left out, ADR-124 decision 1) and the reconnect/resnapshot decision against
`FakeWorkingSetStore`/`FakeGraphPort` — the service's own logic, not
`ValkeyWorkingSetStore` or a real adapter, which is why this needs neither
Valkey nor ArcadeDB to run."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.working_set.models import (
    MAX_EDGES,
    MAX_NODES,
    DeltaSnapshot,
    LimitExceededError,
)
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

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
SCHEME = load_uk_le_scheme()


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL",
        handling_code="P",
        originator="unit-1",
        owning_unit="unit-1",
    )


def _provenance() -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
        first_seen=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1")


def _node(node_id: str, node_type: str = "Person") -> Node:
    return Node(
        id=node_id,
        type=node_type,
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


def _edge(edge_id: str, source: str, target: str) -> Edge:
    return Edge(
        id=edge_id,
        type="ASSOCIATE_OF",
        source=source,
        target=target,
        provenance=_provenance(),
        handling=_handling(),
        audit=_audit(),
    )


# --- seed ---------------------------------------------------------------


async def test_seed_writes_nodes_and_edges_and_reports_seq_one() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)

    outcome = await service.seed("inv-1", [_node("n1")], [], PRINCIPAL)

    assert outcome.delta.seq == 1
    assert [n.id for n in outcome.delta.nodes] == ["n1"]
    assert await store.node_count("inv-1") == 1


# --- expand ---------------------------------------------------------------


async def test_expand_adds_what_the_graph_returned_and_asks_for_no_count_of_the_rest() -> None:
    """ADR-124 decision 1: an expansion's outcome is its delta, and the service no longer asks the
    graph for a count of what lay beyond it to subtract from it (the port has no such method): a
    figure tied to a seed and a link type can be made to point at the one hidden link it counts."""
    store = FakeWorkingSetStore()
    delivered = Subgraph(nodes=[_node("hub"), _node("visible")], edges=[])
    graph = FakeGraphPort(expand_result=delivered)
    service = WorkingSetService(graph, store, SCHEME)

    req = ExpandRequest(node_ids=["hub"], depth=1)
    outcome = await service.expand("inv-1", req, PRINCIPAL)

    assert {n.id for n in outcome.delta.nodes} == {"hub", "visible"}
    assert "filtered_count" not in outcome.model_dump()
    assert graph.expand_requests == [req]


async def test_expand_never_double_counts_a_node_already_in_the_working_set() -> None:
    """Re-expanding into a frontier that overlaps the existing working set
    must not charge the cap for nodes already held — only genuinely new
    ones count toward `would_be`."""
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [_node("hub")])

    delivered = Subgraph(nodes=[_node("hub"), _node("new")], edges=[])
    graph = FakeGraphPort(expand_result=delivered)
    service = WorkingSetService(graph, store, SCHEME)

    await service.expand("inv-1", ExpandRequest(node_ids=["hub"], depth=1), PRINCIPAL)

    assert await store.node_count("inv-1") == 2  # hub (already there) + new, not 3


# --- the cap: never truncates, always the typed error --------------------


async def test_expand_past_the_node_cap_raises_limit_exceeded_with_all_three_options() -> None:
    store = FakeWorkingSetStore()
    too_many = [_node(f"n{i}") for i in range(MAX_NODES + 1)]
    graph = FakeGraphPort(expand_result=Subgraph(nodes=too_many, edges=[]))
    service = WorkingSetService(graph, store, SCHEME)

    with pytest.raises(LimitExceededError) as excinfo:
        await service.expand("inv-1", ExpandRequest(node_ids=["seed"], depth=1), PRINCIPAL)

    detail = excinfo.value.detail
    assert detail.error == "limit_exceeded"
    assert detail.cap_kind == "nodes"
    assert detail.cap == MAX_NODES
    assert detail.would_be == MAX_NODES + 1
    assert set(detail.options) == {"branch", "filter", "promote_to_batch"}
    # Never a partial write: the rejected expansion leaves nothing behind.
    assert await store.node_count("inv-1") == 0


async def test_expand_past_the_edge_cap_raises_limit_exceeded() -> None:
    store = FakeWorkingSetStore()
    nodes = [_node("a"), _node("b")]
    too_many_edges = [_edge(f"e{i}", "a", "b") for i in range(MAX_EDGES + 1)]
    graph = FakeGraphPort(
        expand_result=Subgraph(nodes=nodes, edges=too_many_edges),
    )
    service = WorkingSetService(graph, store, SCHEME)

    with pytest.raises(LimitExceededError) as excinfo:
        await service.expand("inv-1", ExpandRequest(node_ids=["a"], depth=1), PRINCIPAL)

    assert excinfo.value.detail.cap_kind == "edges"
    assert excinfo.value.detail.cap == MAX_EDGES
    assert await store.edge_count("inv-1") == 0


async def test_a_breach_leaves_the_sequence_counter_untouched() -> None:
    """A rejected expansion must not advance `seq` — otherwise a client
    would see a gap in the sequence for an action that, from the server's
    point of view, never happened."""
    store = FakeWorkingSetStore()
    too_many = [_node(f"n{i}") for i in range(MAX_NODES + 1)]
    graph = FakeGraphPort(expand_result=Subgraph(nodes=too_many, edges=[]))
    service = WorkingSetService(graph, store, SCHEME)

    with pytest.raises(LimitExceededError):
        await service.expand("inv-1", ExpandRequest(node_ids=["seed"], depth=1), PRINCIPAL)

    assert await store.current_seq("inv-1") == 0


# --- reconnect: patch when possible, resnapshot when not -----------------


async def test_sync_with_no_prior_seq_returns_a_full_snapshot() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)
    await service.seed("inv-1", [_node("n1"), _node("n2")], [], PRINCIPAL)

    result = await service.sync("inv-1", PRINCIPAL, last_acknowledged_seq=None)

    assert len(result) == 1
    snapshot = result[0]
    assert isinstance(snapshot, DeltaSnapshot)
    assert {n.id for n in snapshot.nodes} == {"n1", "n2"}
    assert snapshot.seq == 1


async def test_sync_within_the_retained_stream_returns_only_the_missed_deltas() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)
    await service.seed("inv-1", [_node("n1")], [], PRINCIPAL)  # seq 1
    await service.seed("inv-1", [_node("n2")], [], PRINCIPAL)  # seq 2
    await service.seed("inv-1", [_node("n3")], [], PRINCIPAL)  # seq 3

    result = await service.sync("inv-1", PRINCIPAL, last_acknowledged_seq=1)

    assert [d.seq for d in result] == [2, 3]
    assert all(d.op == "add" for d in result)


async def test_sync_past_a_trimmed_gap_resnapshots_instead_of_patching() -> None:
    """`03_CONDUIT_MIDDLEWARE.md` §3.2: "reconnects and requests a full
    snapshot rather than attempting to patch" — the byte-identical-set
    guarantee depends on this: a client behind by more than the capped
    stream retains must never be served a partial, gapped patch."""
    store = FakeWorkingSetStore()
    store.stream_maxlen = 2  # only the last two deltas survive
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)
    await service.seed("inv-1", [_node("n1")], [], PRINCIPAL)  # seq 1 — acked, then trimmed
    await service.seed("inv-1", [_node("n2")], [], PRINCIPAL)  # seq 2 — trimmed before return
    await service.seed("inv-1", [_node("n3")], [], PRINCIPAL)  # seq 3 — retained
    await service.seed("inv-1", [_node("n4")], [], PRINCIPAL)  # seq 4 — retained

    result = await service.sync("inv-1", PRINCIPAL, last_acknowledged_seq=1)

    assert len(result) == 1
    snapshot = result[0]
    assert isinstance(snapshot, DeltaSnapshot)
    assert {n.id for n in snapshot.nodes} == {"n1", "n2", "n3", "n4"}
    assert snapshot.seq == 4


async def test_sync_already_caught_up_returns_nothing_to_apply() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)
    await service.seed("inv-1", [_node("n1")], [], PRINCIPAL)  # seq 1

    result = await service.sync("inv-1", PRINCIPAL, last_acknowledged_seq=1)

    assert result == []


# --- current_membership / restore (named-step history, Phase 4) ----------

CLEARED = Principal(id="analyst-secret", clearance="SECRET", org_unit="unit-1")


def _node_with_classification(node_id: str, classification: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=_provenance(),
        handling=Handling(
            classification=classification,
            handling_code="P",
            originator="unit-1",
            owning_unit="unit-1",
        ),
        audit=_audit(),
    )


async def test_current_membership_returns_the_full_unfiltered_store_contents() -> None:
    """`app.py`'s history-step recording needs the *unfiltered* membership —
    `current_membership` takes no `principal` at all, unlike every read
    method on this service, precisely so a step can later be re-projected
    for whoever restores it rather than baking in one principal's view."""
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)
    secret_node = _node_with_classification("secret-1", "SECRET")
    await store.add_nodes("inv-1", [_node("n1"), secret_node])

    nodes, edges = await service.current_membership("inv-1")

    assert {n.id for n in nodes} == {"n1", "secret-1"}
    assert edges == []


async def test_restore_replaces_membership_and_emits_the_next_monotonic_seq() -> None:
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)
    await service.seed("inv-1", [_node("n1")], [], PRINCIPAL)  # seq 1
    await service.seed("inv-1", [_node("n2")], [], PRINCIPAL)  # seq 2 — current membership: n1, n2

    # Restore to a step recorded back when only n1 existed.
    snapshot = (await service.restore("inv-1", [_node("n1")], [], PRINCIPAL)).response

    assert isinstance(snapshot, DeltaSnapshot)
    assert snapshot.seq == 3  # continues the sequence, never resets to 1
    assert {n.id for n in snapshot.nodes} == {"n1"}
    assert await store.node_ids("inv-1") == {"n1"}  # n2 removed, not left behind


async def test_restore_removes_an_edge_added_after_the_recorded_step_between_persisting_nodes() -> (
    None
):
    """The bug this guards against: `n1` and `n2` both exist at the
    recorded step and both still exist afterwards — an edge added between
    them *after* the step was recorded has every endpoint intact, so it is
    never excluded by `_project`'s endpoint check and would silently
    survive a restore that only reconciled nodes. Restoring to the step
    (recorded with no edges) must remove it."""
    store = FakeWorkingSetStore()
    graph = FakeGraphPort(expand_result=Subgraph(nodes=[], edges=[]))
    service = WorkingSetService(graph, store, SCHEME)
    await service.seed("inv-1", [_node("n1"), _node("n2")], [], PRINCIPAL)  # seq 1 — the step

    # Recorded step: n1, n2, no edges (mirrors `current_membership` right
    # after the seed above).
    recorded_step_nodes = [_node("n1"), _node("n2")]

    # An edge added later, between the same two persisting nodes. Both
    # endpoints are resubmitted alongside it — `_project`'s visibility
    # check is scoped to what a single call submits, not the store's
    # accumulated state, so a bare edge with no nodes in the same call
    # would be filtered out as having no visible endpoint at all.
    await service.seed(
        "inv-1", [_node("n1"), _node("n2")], [_edge("e1", "n1", "n2")], PRINCIPAL
    )  # seq 2
    assert await store.edge_ids("inv-1") == {"e1"}

    snapshot = (await service.restore("inv-1", recorded_step_nodes, [], PRINCIPAL)).response

    assert snapshot.edges == []
    assert await store.edge_ids("inv-1") == set()  # not left behind
    assert {n.id for n in snapshot.nodes} == {"n1", "n2"}  # both persisting nodes still present


async def test_restore_reprojects_handling_fresh_against_the_requesting_principal() -> None:
    """The narrower-clearance-restore case: a step recorded while a
    broader-clearance principal had a SECRET node visible must not hand
    that node back to a narrower-clearance principal restoring the same
    step later — restore re-projects at request time, it does not reinstate
    whatever was visible when the step was written."""
    store = FakeWorkingSetStore()
    official_node = _node_with_classification("official-1", "OFFICIAL")
    secret_node = _node_with_classification("secret-1", "SECRET")
    # The Vault holds both (a restore judges the step's members against it, ADR-124 decision 6).
    graph = FakeGraphPort(
        expand_result=Subgraph(nodes=[], edges=[]), graph_nodes=[official_node, secret_node]
    )
    service = WorkingSetService(graph, store, SCHEME)
    # The step, as actually recorded (unfiltered — `current_membership`'s
    # own contract): both nodes, regardless of who was viewing when it
    # happened.
    recorded_step_nodes = [official_node, secret_node]

    snapshot = (await service.restore("inv-1", recorded_step_nodes, [], PRINCIPAL)).response

    assert PRINCIPAL.clearance == "OFFICIAL"
    assert {n.id for n in snapshot.nodes} == {"official-1"}  # not secret-1
    assert "filtered_count" not in snapshot.model_dump()
    # The store itself must reflect the narrower view too, not just the
    # response — a later `sync`/reconnect must not resurrect it either.
    assert await store.node_ids("inv-1") == {"official-1"}

    # The same step, restored by a principal who *can* see SECRET, gets both.
    broader_snapshot = (await service.restore("inv-1", recorded_step_nodes, [], CLEARED)).response
    assert {n.id for n in broader_snapshot.nodes} == {"official-1", "secret-1"}
