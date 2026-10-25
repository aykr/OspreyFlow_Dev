"""`/seed` stores what the Vault holds, never what the caller wrote (ADR-124 decision 7, rules 3
and 4).

`WorkingSetService.seed` took the caller's `Node` and `Edge` bodies and judged them by their own
handling, so a body forged to look readable (OFFICIAL for an id that is SECRET in the Vault) was
stored, and a hidden id's presence could be told from an absent one's by what came back. Now every
submitted id is read through the graph port's by-id reads (`get_nodes`, `get_edges`) for the
seeding principal, and the Vault's bodies are stored; a caller's body is used only for its id. A
link is kept only if each end is seeded in the request (and returned) or already in the reader's
view ("Verify each link"). A hidden id, a superseded id and an id the Vault does not hold give the
same response and the same following snapshot.

Against `FakeGraphPort`, whose `get_nodes` and `get_edges` hold only what a test gives it and leave
out an absent, unreadable, superseded or reverted id alike, as the adapter does (rule 15: a fake
that accepted an absent id would let every case here pass over the defect). The same cases against
ArcadeDB are `test_seed_against_the_vault.py`.
"""

from __future__ import annotations

import pytest
from services.api.working_set import service as service_module
from services.api.working_set.models import LimitExceededError
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Node, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, edge, node

CASE = "inv-1"


def _real(node_id: str, classification: str = "OFFICIAL") -> Node:
    """The Vault's body: a name only the Vault knows."""
    return node(node_id, classification).model_copy(update={"properties": {"name": "the vault's"}})


def _forged(node_id: str) -> Node:
    """A body forged to look readable, whatever the id is in the Vault."""
    return node(node_id, "OFFICIAL").model_copy(update={"properties": {"name": "forged"}})


def _service(
    store: FakeWorkingSetStore,
    vault_nodes: list[Node],
    vault_edges: list[Edge] = (),  # type: ignore[assignment]
    **overrides: object,
) -> tuple[WorkingSetService, FakeGraphPort]:
    graph = FakeGraphPort(
        Subgraph(nodes=[], edges=[]),
        graph_nodes=vault_nodes,
        graph_edges=vault_edges,
        **overrides,  # type: ignore[arg-type]
    )
    return WorkingSetService(graph, store, SCHEME), graph


# --- the Vault's bodies are stored ---------------------------------------------------------------


async def test_the_vaults_body_is_stored_and_the_callers_is_used_only_for_its_id() -> None:
    """Violation caught: the caller's body stored as submitted, so a forged name, type or marking
    lands in a store a later, differently cleared reader opens."""
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real("ok")])

    outcome = await service.seed(CASE, [_forged("ok")], [], OFFICIAL_READER)

    stored = await store.source_fidelity_nodes(CASE)
    assert stored["ok"].properties == {"name": "the vault's"}
    assert [n.properties for n in outcome.delta.nodes] == [{"name": "the vault's"}]


async def test_a_body_marked_official_for_an_id_that_is_secret_in_the_vault_is_not_stored() -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real("ok"), _real("real-secret", "SECRET")])

    outcome = await service.seed(CASE, [_forged("ok"), _forged("real-secret")], [], OFFICIAL_READER)

    assert set(await store.source_fidelity_nodes(CASE)) == {"ok"}
    assert [n.id for n in outcome.delta.nodes] == ["ok"]


async def test_the_nodes_come_back_in_the_order_they_were_submitted() -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real("b"), _real("a"), _real("c")])

    outcome = await service.seed(
        CASE, [_forged("c"), _forged("a"), _forged("b")], [], OFFICIAL_READER
    )

    assert [n.id for n in outcome.delta.nodes] == ["c", "a", "b"]


# --- a hidden id, a superseded id and an absent id are the same -----------------------------------


async def _answer_for(unreadable: str) -> tuple[dict[str, object], dict[str, object]]:
    """The response and the following snapshot when `[ok, <the unreadable id>]` is seeded."""
    store = FakeWorkingSetStore()
    service, _ = _service(
        store,
        [_real("ok"), _real("hidden-id", "SECRET"), _real("old-revision")],
        superseded_node_ids=frozenset({"old-revision"}),
    )
    outcome = await service.seed(CASE, [_forged("ok"), _forged(unreadable)], [], OFFICIAL_READER)
    (snapshot,) = await service.sync(CASE, OFFICIAL_READER, last_acknowledged_seq=None)
    return outcome.model_dump(mode="json"), snapshot.model_dump(mode="json")


async def test_hidden_superseded_and_absent_ids_give_the_same_response_and_snapshot() -> None:
    """Violation caught (rule 4): `/seed` as a membership test. Ids are derived and can be guessed;
    a body submitted under a stored hidden id used to be dropped from the store but echoed in the
    response's delta. All three answer alike now: no error, and the same following snapshot."""
    hidden = await _answer_for("hidden-id")
    superseded = await _answer_for("old-revision")
    absent = await _answer_for("never-existed")

    assert hidden == superseded == absent
    assert [n["id"] for n in hidden[0]["delta"]["nodes"]] == ["ok"]  # type: ignore[index]


async def test_a_stored_hidden_id_is_not_disturbed_or_revealed_by_a_seed_that_names_it() -> None:
    """The stored hidden node stays as it is, and the answer is that of an id nobody holds."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_real("sec", "SECRET")])
    service, _ = _service(store, [_real("sec", "SECRET"), _real("ok")])

    outcome = await service.seed(CASE, [_forged("sec"), _forged("ok")], [], OFFICIAL_READER)

    assert [n.id for n in outcome.delta.nodes] == ["ok"]
    assert (await store.source_fidelity_nodes(CASE))["sec"].handling.classification == "SECRET"


# --- links: verified in the Vault, and each end seeded or on the canvas ---------------------------


async def test_a_link_whose_real_end_is_hidden_is_dropped_whatever_the_forged_body_says() -> None:
    """Violation caught: a link judged by the caller's bodies, which could name a hidden node's id
    as OFFICIAL and have the link stored to it."""
    store = FakeWorkingSetStore()
    service, _ = _service(
        store,
        [_real("ok"), _real("secret-end", "SECRET")],
        [edge("to-secret", "ok", "secret-end")],
    )

    outcome = await service.seed(
        CASE,
        [_forged("ok"), _forged("secret-end")],
        [edge("to-secret", "ok", "secret-end")],
        OFFICIAL_READER,
    )

    assert outcome.delta.edges == []
    assert await store.edge_ids(CASE) == set()


async def test_a_link_between_two_seeded_nodes_is_stored_with_the_vaults_body() -> None:
    store = FakeWorkingSetStore()
    vault_link = edge("ab", "a", "b").model_copy(update={"properties": {"since": "the vault's"}})
    service, _ = _service(store, [_real("a"), _real("b")], [vault_link])

    await service.seed(CASE, [_forged("a"), _forged("b")], [edge("ab", "a", "b")], OFFICIAL_READER)

    stored = await store.source_fidelity_edges(CASE)
    assert stored["ab"].properties == {"since": "the vault's"}


async def test_a_link_to_a_node_already_in_the_readers_view_is_kept() -> None:
    """Verify each link: an end need not be in the request if the reader already has it."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_real("onscreen")])
    service, _ = _service(
        store, [_real("new"), _real("onscreen")], [edge("n-o", "new", "onscreen")]
    )

    outcome = await service.seed(
        CASE, [_forged("new")], [edge("n-o", "new", "onscreen")], OFFICIAL_READER
    )

    assert [e.id for e in outcome.delta.edges] == ["n-o"]


async def test_a_link_with_an_end_neither_seeded_nor_in_the_view_is_dropped() -> None:
    """The link is readable in the Vault with both ends readable there, but one end is on nobody's
    canvas and not in this request: it is not verified, so it is not stored."""
    store = FakeWorkingSetStore()
    service, _ = _service(
        store, [_real("new"), _real("elsewhere")], [edge("n-e", "new", "elsewhere")]
    )

    outcome = await service.seed(
        CASE, [_forged("new")], [edge("n-e", "new", "elsewhere")], OFFICIAL_READER
    )

    assert outcome.delta.edges == []
    assert [n.id for n in outcome.delta.nodes] == ["new"]


async def test_a_link_to_a_stored_hidden_node_is_dropped_as_a_link_to_an_absent_one_is() -> None:
    """The end is on the store but not in the reader's view: the same as an end that is not."""
    answers = []
    for stored_hidden in (True, False):
        store = FakeWorkingSetStore()
        if stored_hidden:
            await store.add_nodes(CASE, [_real("far", "SECRET")])
        service, _ = _service(
            store, [_real("new"), _real("far", "SECRET")], [edge("l", "new", "far")]
        )
        outcome = await service.seed(
            CASE, [_forged("new")], [edge("l", "new", "far")], OFFICIAL_READER
        )
        answers.append(outcome.model_dump(mode="json"))

    assert answers[0] == answers[1]
    assert answers[0]["delta"]["edges"] == []


# --- the reads: one by-id read each, for the seeding principal ---------------------------------


async def test_seed_reads_the_submitted_ids_once_through_each_by_id_read() -> None:
    """The cost: one extra by-id read per seed, of nodes and of links, for the principal seeding."""
    store = FakeWorkingSetStore()
    service, graph = _service(store, [_real("a"), _real("b")], [edge("ab", "a", "b")])

    await service.seed(CASE, [_forged("a"), _forged("b")], [edge("ab", "a", "b")], OFFICIAL_READER)

    assert graph.get_nodes_requests == [(["a", "b"], OFFICIAL_READER)]
    assert graph.get_edges_requests == [(["ab"], OFFICIAL_READER)]


async def test_a_seed_for_a_reader_scoped_to_the_cases_datasets_stores_only_theirs() -> None:
    """ADR-099: the Vault's by-id read is for the case-scoped principal, so a node in another
    dataset is left out, whatever the caller's body says."""
    store = FakeWorkingSetStore()
    mine = _real("mine").model_copy(update={"datasets": ["fixture"]})
    theirs = _real("theirs").model_copy(update={"datasets": ["enron"]})
    service, _ = _service(store, [mine, theirs])
    scoped = OFFICIAL_READER.model_copy(update={"datasets": ["fixture"]})

    await service.seed(CASE, [_forged("mine"), _forged("theirs")], [], scoped)

    assert set(await store.source_fidelity_nodes(CASE)) == {"mine"}


# --- the cap is counted on the reader's view after the filtering ----------------------------------


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "MAX_NODES", 3)


async def test_what_the_vault_refuses_does_not_count_towards_the_cap(small_cap: None) -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(
        store,
        [_real(f"n{i}") for i in range(3)] + [_real(f"h{i}", "SECRET") for i in range(4)],
    )
    submitted = [_forged(f"n{i}") for i in range(3)] + [_forged(f"h{i}") for i in range(4)]

    outcome = await service.seed(CASE, submitted, [], OFFICIAL_READER)

    assert len(outcome.delta.nodes) == 3


async def test_a_seed_past_the_cap_after_the_filtering_is_refused_with_the_readers_figure(
    small_cap: None,
) -> None:
    store = FakeWorkingSetStore()
    service, _ = _service(store, [_real(f"n{i}") for i in range(4)])

    with pytest.raises(LimitExceededError) as refused:
        await service.seed(CASE, [_forged(f"n{i}") for i in range(4)], [], OFFICIAL_READER)

    assert refused.value.detail.would_be == 4
    assert await store.node_ids(CASE) == set()
