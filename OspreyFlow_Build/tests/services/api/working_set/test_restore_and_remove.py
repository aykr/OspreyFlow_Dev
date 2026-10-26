"""A reader's own action never removes or downgrades what is stored that they cannot read
(ADR-124 decision 6, rules 3 and 4).

`remove` removes only ids whose stored body the reader may read, and ignores every other id with
the same response and the same history entry. A restore judges its step's members against the
current Vault (`get_nodes`, `get_edges`) and stores the Vault's bodies, never the step's recorded
ones; reconciles only the stored items in the restorer's own view; and leaves everything else
alone. What is stored and published after it is the whole stored set, which every reader projects
to their own view, so a reconnect equals a fresh full snapshot for every reader (the Phase 3
criterion); the restorer's own response is that snapshot projected for them.

Written in the unit's own order: the reclassified-node case first, red against the restore that
wrote a step's recorded body, then the rest.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.working_set import service as service_module
from services.api.working_set.models import DeltaAdd, DeltaSnapshot, LimitExceededError
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Node, Principal, Subgraph

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, SECRET_READER, edge, node

CASE = "inv-1"
IN_FIXTURE = OFFICIAL_READER.model_copy(update={"datasets": ["fixture"]})


def _in(datasets: list[str], element: Node | Edge) -> object:
    return element.model_copy(update={"datasets": datasets})


def _service(
    store: FakeWorkingSetStore,
    vault_nodes: Sequence[Node] = (),
    vault_edges: Sequence[Edge] = (),
) -> WorkingSetService:
    """A service whose Vault (the graph port's by-id reads) holds the given nodes and links."""
    graph = FakeGraphPort(
        Subgraph(nodes=[], edges=[]), graph_nodes=vault_nodes, graph_edges=vault_edges
    )
    return WorkingSetService(graph, store, SCHEME)


async def _stored_ids(store: FakeWorkingSetStore) -> tuple[set[str], set[str]]:
    return set(await store.source_fidelity_nodes(CASE)), set(
        await store.source_fidelity_edges(CASE)
    )


# --- 1. the reclassified-node case ----------------------------------------------------------------


async def test_a_restore_does_not_write_a_steps_lower_marked_body_over_a_raised_node() -> None:
    """Violation caught (rule 3): a restore that writes the step's recorded bodies. The step was
    recorded when `n` was OFFICIAL; a cleared colleague has since raised it to SECRET (the stored
    copy and the Vault's). Restoring the step by an OFFICIAL reader wrote the old, lower-marked
    body back over it, and the reader could read it. The Vault's body is the current one, and the
    reader may not read it, so nothing is written for it."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("n", "SECRET")])
    raised = node("n", "SECRET")
    service = _service(store, vault_nodes=[node("pub"), raised])
    step = [node("pub"), node("n")]  # recorded when `n` was OFFICIAL

    restored = await service.restore(CASE, step, [], OFFICIAL_READER)

    stored = await store.source_fidelity_nodes(CASE)
    assert stored["n"].handling.classification == "SECRET"
    assert {n.id for n in restored.response.nodes} == {"pub"}
    cleared = await service.sync(CASE, SECRET_READER, last_acknowledged_seq=None)
    assert isinstance(cleared[0], DeltaSnapshot) and {n.id for n in cleared[0].nodes} == {
        "pub",
        "n",
    }


# --- 2a. remove --------------------------------------------------------------------------------


async def test_remove_removes_only_ids_whose_stored_body_the_reader_may_read() -> None:
    """Violation caught (rule 3): `remove` deleting any id it was given, so a reader below a
    node's marking, naming its id, deleted a cleared colleague's work. A hidden id and an absent
    one are ignored alike, and the delta names only what was removed."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("also-pub"), node("sec", "SECRET")])

    delta = await _service(store).remove(CASE, ["pub", "sec", "ghost"], OFFICIAL_READER)

    assert delta.node_ids == ["pub"]
    assert (await _stored_ids(store))[0] == {"also-pub", "sec"}
    assert delta.removed is not None and set(delta.removed.nodes) == {"pub"}


async def test_remove_ignores_a_node_in_another_dataset_for_a_reader_of_the_case() -> None:
    """The datasets axis (ADR-099): a node outside the case's datasets is not the reader's to
    remove, whatever its marking."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [_in(["fixture"], node("mine")), _in(["enron"], node("theirs"))],  # type: ignore[list-item]
    )

    delta = await _service(store).remove(CASE, ["mine", "theirs"], IN_FIXTURE)

    assert delta.node_ids == ["mine"]
    assert (await _stored_ids(store))[0] == {"theirs"}


async def test_remove_of_a_hidden_id_and_of_an_absent_one_leave_the_same_trace() -> None:
    """Same response and same history entry: the sequence number advances the same, the delta that
    is stored and published names nothing, and what is stored is the same."""
    traces = []
    for requested in ("sec", "ghost"):
        store = FakeWorkingSetStore()
        await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
        service = _service(store)

        delta = await service.remove(CASE, [requested], OFFICIAL_READER)

        traces.append(
            (delta.seq, delta.node_ids, delta.removed, await _stored_ids(store), store._seq[CASE])
        )

    assert traces[0] == traces[1]
    assert traces[0][1] == []


# --- 2b. restore -----------------------------------------------------------------------------


async def test_a_restore_reconciles_only_the_stored_items_in_the_restorers_view() -> None:
    """Violation caught (rule 3): every stored item the step lacked was deleted. Those in the
    restorer's projected view go; a node above them stays, and so does a readable link whose end is
    above them (it is not in their view)."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE, [node("keep"), node("gone"), node("hidden", "SECRET"), node("other")]
    )
    await store.add_edges(
        CASE,
        [
            edge("gone-edge", "keep", "gone"),
            edge("to-hidden", "keep", "hidden"),  # readable, with a hidden end
            edge("secret-link", "keep", "other", "SECRET"),
        ],
    )
    held = [node("keep")]
    service = _service(store, vault_nodes=held)

    await service.restore(CASE, held, [], OFFICIAL_READER)

    nodes, edges = await _stored_ids(store)
    assert nodes == {"keep", "hidden"}  # `gone` and `other` were in the view and not in the step
    assert edges == {"to-hidden", "secret-link"}  # `gone-edge` went; the two hidden-to-them stay


async def test_a_step_member_the_restorer_may_not_read_is_not_added() -> None:
    """Step items the restorer may not read are not added (decision 6): a member the Vault holds
    above the restorer is absent from `get_nodes` for them, and a cleared reader's view of the
    result holds everything they may see."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("old")])
    held = [node("pub"), node("sec", "SECRET")]
    service = _service(store, vault_nodes=held)

    restored = await service.restore(CASE, held, [], OFFICIAL_READER)

    assert (await _stored_ids(store))[0] == {"pub"}
    assert {n.id for n in restored.response.nodes} == {"pub"}
    cleared = await service.sync(CASE, SECRET_READER, last_acknowledged_seq=None)
    assert {n.id for n in cleared[0].nodes} == {"pub"}  # type: ignore[attr-defined]


async def test_a_stored_readable_member_the_vault_now_withholds_is_left_untouched() -> None:
    """A step member whose stored body the restorer may read but which the Vault now withholds is
    left stored and untouched: not rewritten with the step's body, not removed as stale."""
    store = FakeWorkingSetStore()
    stored = node("m").model_copy(update={"properties": {"name": "as stored"}})
    await store.add_nodes(CASE, [stored])
    service = _service(store, vault_nodes=[node("m", "SECRET")])  # the Vault has raised it

    await service.restore(
        CASE, [node("m").model_copy(update={"properties": {"name": "as recorded"}})], [],
        OFFICIAL_READER,
    )  # fmt: skip

    assert (await store.source_fidelity_nodes(CASE))["m"].properties == {"name": "as stored"}


async def test_a_restore_stores_the_vaults_current_body_and_never_the_steps_stale_one() -> None:
    """Violation caught: the step's recorded body written over a newer one. The Vault's current
    body is what is stored."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("m")])
    current = node("m").model_copy(update={"properties": {"name": "current"}})
    service = _service(store, vault_nodes=[current])
    recorded = node("m").model_copy(update={"properties": {"name": "recorded long ago"}})

    await service.restore(CASE, [recorded], [], OFFICIAL_READER)

    assert (await store.source_fidelity_nodes(CASE))["m"].properties == {"name": "current"}


async def test_a_restore_adds_only_the_links_the_vault_gives_the_restorer() -> None:
    """`get_edges` returns a link only when it and both its ends are readable: a step link to a
    node above the restorer is not added."""
    store = FakeWorkingSetStore()
    held = [node("a"), node("b"), node("s", "SECRET")]
    links = [edge("ab", "a", "b"), edge("as", "a", "s")]
    service = _service(store, vault_nodes=held, vault_edges=links)

    await service.restore(CASE, held, links, OFFICIAL_READER)

    nodes, edges = await _stored_ids(store)
    assert nodes == {"a", "b"} and edges == {"ab"}


async def test_a_restore_applies_the_cases_dataset_scope() -> None:
    """The datasets axis (ADR-099): for a reader scoped to the case, a step member in another
    dataset is not added, a stored item outside the case's datasets is not theirs to reconcile and
    stays, and a stored in-dataset item the step lacks goes."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            _in(["fixture"], node("stale")),  # type: ignore[list-item]
            _in(["enron"], node("elsewhere")),  # type: ignore[list-item]
        ],
    )
    mine = _in(["fixture"], node("mine"))
    theirs = _in(["enron"], node("theirs"))
    service = _service(store, vault_nodes=[mine, theirs])  # type: ignore[list-item]

    await service.restore(CASE, [mine, theirs], [], IN_FIXTURE)  # type: ignore[list-item]

    assert (await _stored_ids(store))[0] == {"mine", "elsewhere"}


# --- 3. a reconnect equals a fresh full snapshot --------------------------------------------------


async def _client_state(deltas: Sequence[object]) -> tuple[set[str], set[str]]:
    """What a client holds after applying `deltas` to nothing, as the Glass applies them (a
    snapshot replaces; an addition adds): the node ids and the link ids."""
    nodes: set[str] = set()
    edges: set[str] = set()
    for delta in deltas:
        if isinstance(delta, DeltaSnapshot):
            nodes, edges = {n.id for n in delta.nodes}, {e.id for e in delta.edges}
        elif isinstance(delta, DeltaAdd):
            nodes |= {n.id for n in delta.nodes}
            edges |= {e.id for e in delta.edges}
    return nodes, edges


async def test_a_more_cleared_readers_catch_up_equals_a_fresh_snapshot_after_a_restore() -> None:
    """Violation caught (the Phase 3 criterion, for every reader): a restore by a reader below a
    colleague's work. The restorer's own view of the result was what was published, so a
    more-cleared reader who reconnects a step behind is caught up to the restorer's narrower set,
    and a fresh snapshot (from the stored set, which kept the colleague's work) differs. The
    published snapshot holds the whole stored set, and each reader projects it."""
    store = FakeWorkingSetStore()
    held = [node("pub"), node("sec", "SECRET"), node("other")]
    links = [edge("pub-other", "pub", "other"), edge("secret-link", "pub", "other", "SECRET")]
    service = _service(store, vault_nodes=held, vault_edges=links)
    await service.seed(CASE, held, links, SECRET_READER)  # seq 1: what the cleared reader holds
    step_nodes = [node("pub"), node("other")]  # recorded before `sec` arrived

    await service.restore(CASE, step_nodes, [edge("pub-other", "pub", "other")], OFFICIAL_READER)

    caught_up = await service.sync(CASE, SECRET_READER, last_acknowledged_seq=1)
    fresh = await service.sync(CASE, SECRET_READER, last_acknowledged_seq=None)
    state_caught_up = await _client_state(caught_up)
    state_fresh = await _client_state(fresh)
    assert state_caught_up == state_fresh
    assert "sec" in state_fresh[0] and "secret-link" in state_fresh[1]


# --- 4. on the routes ----------------------------------------------------------------------------


class _Recorder:
    """A Valkey that keeps what is published, and a history store that keeps what is recorded."""

    def __init__(self) -> None:
        self.published: list[str] = []
        self.steps: list[dict[str, object]] = []
        self.step_nodes: list[Node] = []
        self.step_edges: list[Edge] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append(message)
        return 1

    async def record_step(self, investigation_id: str, **kwargs: object) -> object:
        self.steps.append(kwargs)
        return object()

    async def get_step(self, investigation_id: str, step_id: str) -> object:
        return SimpleNamespace(label="Seeded", nodes=self.step_nodes, edges=self.step_edges)

    async def record(self, **kwargs: object) -> None:
        return None


class _Investigations:
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        if investigation_id != CASE:
            raise InvestigationNotFoundError(investigation_id)
        when = datetime(2026, 10, 1, tzinfo=UTC)
        return Investigation(id=CASE, created_at=when, created_by="analyst-1", owning_unit="unit-1")


@contextmanager
def _routes(
    service: WorkingSetService, recorder: _Recorder, reader: Principal
) -> Iterator[TestClient]:
    editor = reader.model_copy(update={"roles": ["analyst"], "org_unit": "unit-1"})
    app.dependency_overrides[get_principal] = lambda: editor
    app.dependency_overrides[get_working_set] = lambda: service
    app.dependency_overrides[get_audit] = lambda: recorder
    app.dependency_overrides[get_history] = lambda: recorder
    app.dependency_overrides[get_investigations] = lambda: _Investigations()
    app.dependency_overrides[get_valkey] = lambda: recorder
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


async def test_the_restore_route_answers_the_restorers_view_and_publishes_the_whole() -> None:
    """Violation caught (rule 3): the route answering with the stored whole, so the restorer is sent
    what they may not read; or publishing the restorer's view, so every other socket is narrowed to
    it. Restore records no history step."""
    store = FakeWorkingSetStore()
    held = [node("pub"), node("sec", "SECRET")]
    await store.add_nodes(CASE, held)
    service = _service(store, vault_nodes=held)
    recorder = _Recorder()
    recorder.step_nodes = [node("pub")]

    with _routes(service, recorder, OFFICIAL_READER) as client:
        response = client.post(f"/v1/investigations/{CASE}/history/step-1")

    assert response.status_code == 200
    body = response.json()
    assert [n["id"] for n in body["nodes"]] == ["pub"]
    assert body.get("withheld") is None and "sec" not in response.text
    (message,) = recorder.published
    published = json.loads(message)
    assert {n["id"] for n in published["nodes"]} == {"pub", "sec"}  # the whole stored set
    assert published.get("withheld") is None
    assert recorder.steps == []  # restore records no step


async def test_remove_answers_and_records_the_same_for_a_hidden_id_and_an_absent_one() -> None:
    """Same response and same history entry (decision 6): an analyst naming a hidden id cannot tell
    it from a missing one by the answer or by the label the history records."""
    traces = []
    for requested in ("sec", "ghost"):
        store = FakeWorkingSetStore()
        await store.add_nodes(CASE, [node("pub"), node("sec", "SECRET")])
        recorder = _Recorder()
        with _routes(_service(store), recorder, OFFICIAL_READER) as client:
            response = client.request(
                "DELETE", f"/v1/investigations/{CASE}/nodes", json={"node_ids": [requested]}
            )
        traces.append(
            (
                response.status_code,
                response.json(),
                [step["label"] for step in recorder.steps],
                [json.loads(m)["node_ids"] for m in recorder.published],
            )
        )

    assert traces[0] == traces[1]
    assert traces[0][3] == [[]]  # the delta names nothing: nothing was removed


# --- 5. a restore is bounded by the restorer's own view (rule 2, decision 2) ----------------------


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> int:
    """The node cap at three, so that the cap is reached without fifty thousand nodes."""
    monkeypatch.setattr(service_module, "MAX_NODES", 3)
    return 3


async def _nothing_moved(store: FakeWorkingSetStore, before: tuple[object, ...]) -> None:
    assert (
        await _stored_ids(store),
        await store.current_seq(CASE),
        await store.deltas_after(CASE, 0),
    ) == before


async def test_a_restore_that_would_pass_the_cap_for_the_restorer_is_refused_whole(
    small_cap: int,
) -> None:
    """Violation caught (rule 2, decision 2): steps record the whole stored set, which has no
    case-wide ceiling, so a cleared restorer's resulting view can pass the cap; the restore wrote it
    and sent it with no check. The restorer's own figures are counted before any write, and a
    breach raises the typed `limit_exceeded` with its three options and nothing is written: no add,
    no removal, no sequence number, no delta."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("old")])
    held = [node(f"n{i}") for i in range(4)]
    service = _service(store, vault_nodes=held)
    before = (await _stored_ids(store), await store.current_seq(CASE), [])

    with pytest.raises(LimitExceededError) as refused:
        await service.restore(CASE, held, [], OFFICIAL_READER)

    detail = refused.value.detail
    assert (detail.cap_kind, detail.cap, detail.would_be) == ("nodes", small_cap, 4)
    assert set(detail.options) == {"branch", "filter", "promote_to_batch"}
    await _nothing_moved(store, before)


async def test_hidden_items_move_neither_the_restores_figure_nor_its_outcome(
    small_cap: int,
) -> None:
    """Violation caught (rule 3): a figure counted over the stored whole, or over every id the step
    names, so a restorer could learn how much is hidden by when a restore is refused. Steps record
    the whole stored set unfiltered, so hidden ids are in them too. Four cases differ only in what
    the restorer may not read: nothing; five stored nodes outside the step; five hidden ids in the
    step that are stored; five hidden ids in the step that only the Vault holds. Each gives the
    same figure when refused (4) and the same outcome when not."""
    hidden = [node(f"h{i}", "SECRET") for i in range(5)]
    outcomes: dict[str, list[tuple[str, int | None]]] = {}
    for variant in (
        "none",
        "stored outside the step",
        "stored in the step",
        "vault only in the step",
    ):
        outcomes[variant] = []
        for readable_in_step in (3, 4):
            store = FakeWorkingSetStore()
            readable = [node(f"n{i}") for i in range(readable_in_step)]
            if variant in ("stored outside the step", "stored in the step"):
                await store.add_nodes(CASE, hidden)
            step = readable + (hidden if "in the step" in variant else [])
            held_by_the_vault = readable + (hidden if variant != "none" else [])
            service = _service(store, vault_nodes=held_by_the_vault)
            try:
                await service.restore(CASE, step, [], OFFICIAL_READER)
                outcomes[variant].append(("restored", None))
            except LimitExceededError as refused:
                outcomes[variant].append(("refused", refused.detail.would_be))

    assert outcomes["none"] == [("restored", None), ("refused", 4)]
    assert all(found == outcomes["none"] for found in outcomes.values()), outcomes


async def test_a_restore_counts_what_it_leaves_in_the_restorers_view(small_cap: int) -> None:
    """A step member the restorer may read in the store and the Vault now withholds is left stored
    and stays in their view, so it counts: three the Vault gives and one left untouched is four."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("left-alone")])
    given = [node(f"n{i}") for i in range(3)]
    service = _service(store, vault_nodes=[*given, node("left-alone", "SECRET")])

    with pytest.raises(LimitExceededError) as refused:
        await service.restore(CASE, [*given, node("left-alone")], [], OFFICIAL_READER)

    assert refused.value.detail.would_be == 4


async def test_the_restore_route_turns_a_breach_into_the_standard_limit_exceeded(
    small_cap: int,
) -> None:
    """The route answers as expand's does (the app's one handler): 409, `limit_exceeded`, the
    restorer's figures and the three options; nothing is published or recorded."""
    store = FakeWorkingSetStore()
    held = [node(f"n{i}") for i in range(4)]
    service = _service(store, vault_nodes=held)
    recorder = _Recorder()
    recorder.step_nodes = held

    with _routes(service, recorder, OFFICIAL_READER) as client:
        response = client.post(f"/v1/investigations/{CASE}/history/step-1")

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "limit_exceeded" and (body["cap_kind"], body["would_be"]) == (
        "nodes",
        4,
    )
    assert body["options"] == ["branch", "filter", "promote_to_batch"]
    assert recorder.published == [] and recorder.steps == []
    assert await _stored_ids(store) == (set(), set())


# --- 6. reconciled after the adds ----------------------------------------------------------------


async def test_a_stored_link_the_adds_bring_into_the_restorers_view_is_reconciled() -> None:
    """Violation caught: the stale set read before the adds. A stored link not in the step, whose
    end was above the restorer, is outside their view until the restore writes that end from the
    Vault, where it has since been declassified; read before, it was left, and the restorer's view
    then held a link the restore should have reconciled."""
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [node("pub"), node("m", "SECRET")])
    await store.add_edges(CASE, [edge("to-m", "pub", "m")])  # readable, with a hidden end
    declassified = node("m")
    service = _service(store, vault_nodes=[node("pub"), declassified])

    await service.restore(CASE, [node("pub"), node("m", "SECRET")], [], OFFICIAL_READER)

    nodes, edges = await _stored_ids(store)
    assert nodes == {"pub", "m"} and edges == set()
