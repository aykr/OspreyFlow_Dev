"""Branching a reader's own view, narrowed by a filter (ADR-124 decision 2, "open a filtered
branch"; rules 2, 3 and 4).

A less-cleared colleague's work can push a more-cleared reader's view past the cap. The reader's way
out is a new case built on the server from their own projected view, narrowed to entity types, a
date window, or both: types select nodes; the window selects links whose interval overlaps it, and
a link with no interval is kept; a link is kept only when both its ends are. Nothing is ever copied
that the reader may not read, a filter naming a type that only hidden material holds gives what a
type that does not exist gives, and a result past the cap is `limit_exceeded` with the filtered
figures, the reader's own, before any case is created.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from services.api.app import (
    app,
    get_audit,
    get_datasets,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.working_set import service as service_module
from services.api.working_set.models import (
    BranchFilter,
    LimitExceededError,
    NothingToBranchError,
)
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Interval, Node, Principal, Subgraph

from ..test_branch_tabs_routes import ALICE, _FakeInvestigations
from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_visible_link import OFFICIAL_READER, SCHEME, edge, node

CASE = "inv-1"
JAN = datetime(2026, 1, 1, tzinfo=UTC)
MAR = datetime(2026, 3, 1, tzinfo=UTC)
JUN = datetime(2026, 6, 1, tzinfo=UTC)
DEC = datetime(2026, 12, 1, tzinfo=UTC)


def _typed(node_id: str, node_type: str, classification: str = "OFFICIAL") -> Node:
    return node(node_id, classification).model_copy(update={"type": node_type})


def _timed(
    edge_id: str, source: str, target: str, start: datetime | None, end: datetime | None
) -> Edge:
    interval = None if start is None else Interval(valid_from=start, valid_to=end)
    return edge(edge_id, source, target).model_copy(update={"interval": interval})


def _service(store: FakeWorkingSetStore) -> WorkingSetService:
    return WorkingSetService(FakeGraphPort(Subgraph(nodes=[], edges=[])), store, SCHEME)


async def _held() -> FakeWorkingSetStore:
    """Two people, a vehicle, and a SECRET `Weapon`; links with and without a time."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            _typed("p1", "Person"),
            _typed("p2", "Person"),
            _typed("v1", "Vehicle"),
            _typed("w1", "Weapon", "SECRET"),
        ],
    )
    await store.add_edges(
        CASE,
        [
            _timed("early", "p1", "p2", JAN, MAR),
            _timed("late", "p1", "p2", JUN, DEC),
            _timed("untimed", "p1", "v1", None, None),
            _timed("open-ended", "p2", "v1", MAR, None),
            _timed("to-weapon", "p1", "w1", None, None),
        ],
    )
    return store


# --- the filter ------------------------------------------------------------------------------


def test_a_filter_must_choose_something_and_a_window_must_run_forwards() -> None:
    with pytest.raises(ValidationError):
        BranchFilter()
    with pytest.raises(ValidationError):
        BranchFilter(valid_from=DEC, valid_to=JAN)
    assert BranchFilter(entity_types=[]).entity_types == []  # a choice of nothing: refused later


async def test_entity_types_select_nodes_and_a_link_needs_both_its_ends() -> None:
    contents = await _service(await _held()).branch_filtered_contents(
        CASE, OFFICIAL_READER, BranchFilter(entity_types=["Person"])
    )

    nodes, edges = contents
    assert {n.id for n in nodes} == {"p1", "p2"}
    assert {e.id for e in edges} == {"early", "late"}  # the links to the vehicle lost an end


async def test_a_window_selects_the_links_whose_interval_overlaps_it_and_keeps_untimed_ones() -> (
    None
):
    nodes, edges = await _service(await _held()).branch_filtered_contents(
        CASE,
        OFFICIAL_READER,
        BranchFilter(valid_from=datetime(2026, 5, 1, tzinfo=UTC), valid_to=JUN),
    )

    assert {n.id for n in nodes} == {"p1", "p2", "v1"}  # a window never selects nodes
    assert {e.id for e in edges} == {"late", "untimed", "open-ended"}


async def test_types_and_a_window_together_narrow_both() -> None:
    nodes, edges = await _service(await _held()).branch_filtered_contents(
        CASE, OFFICIAL_READER, BranchFilter(entity_types=["Person"], valid_to=MAR)
    )

    assert {n.id for n in nodes} == {"p1", "p2"} and {e.id for e in edges} == {"early"}


async def test_a_choice_that_leaves_nothing_is_refused_as_branch_refuses() -> None:
    with pytest.raises(NothingToBranchError):
        await _service(await _held()).branch_filtered_contents(
            CASE, OFFICIAL_READER, BranchFilter(entity_types=["Organisation"])
        )
    with pytest.raises(NothingToBranchError):
        await _service(await _held()).branch_filtered_contents(
            CASE, OFFICIAL_READER, BranchFilter(entity_types=[])
        )


# --- rule 4: a branch never holds what the reader may not read ------------------------------


async def test_a_branch_never_holds_what_the_reader_may_not_read() -> None:
    """Violation caught (rule 3): the filter applied to the stored bodies, so a type the reader
    cannot see carries its nodes, and the links to them, into the new case."""
    nodes, edges = await _service(await _held()).branch_filtered_contents(
        CASE, OFFICIAL_READER, BranchFilter(entity_types=["Person", "Weapon", "Vehicle"])
    )

    assert "w1" not in {n.id for n in nodes}
    assert "to-weapon" not in {e.id for e in edges}
    assert {n.id for n in nodes} == {"p1", "p2", "v1"}


async def test_a_type_only_hidden_material_holds_gives_what_an_absent_type_gives() -> None:
    """Violation caught (rule 4): an answer that differs for `Weapon` (held, above the reader) and
    `Unicorn` (held by no one): a refused choice for one and a copy for the other, or a different
    error. Both are `NothingToBranchError`."""
    outcomes = []
    for chosen in ("Weapon", "Unicorn"):
        try:
            await _service(await _held()).branch_filtered_contents(
                CASE, OFFICIAL_READER, BranchFilter(entity_types=[chosen])
            )
            outcomes.append("copied")
        except NothingToBranchError as error:
            outcomes.append(type(error).__name__)

    assert outcomes == ["NothingToBranchError", "NothingToBranchError"]


# --- rule 2 and rule 3: the cap, over the reader's own filtered view --------------------------


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "MAX_NODES", 2)


async def test_a_filtered_view_past_the_cap_is_refused_with_the_filtered_figures(
    small_cap: None,
) -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_typed(f"p{i}", "Person") for i in range(3)])

    with pytest.raises(LimitExceededError) as refused:
        await _service(store).branch_filtered_contents(
            CASE, OFFICIAL_READER, BranchFilter(entity_types=["Person"])
        )

    detail = refused.value.detail
    assert (detail.cap_kind, detail.cap, detail.would_be) == ("nodes", 2, 3)


async def test_hidden_stored_material_moves_neither_the_figure_nor_the_outcome(
    small_cap: None,
) -> None:
    """Violation caught (rule 3): a figure counted over the stored whole, so a reader could learn
    how much is hidden. Cases differing only in hidden stored nodes give the same figure."""
    results = []
    for hidden in (0, 4):
        store = FakeWorkingSetStore()
        await store.add_nodes(
            CASE,
            [
                *(_typed(f"p{i}", "Person") for i in range(3)),
                *(_typed(f"w{i}", "Person", "SECRET") for i in range(hidden)),
            ],
        )
        with pytest.raises(LimitExceededError) as refused:
            await _service(store).branch_filtered_contents(
                CASE, OFFICIAL_READER, BranchFilter(entity_types=["Person"])
            )
        results.append(refused.value.detail.model_dump())

    assert results[0] == results[1] and results[0]["would_be"] == 3


# --- the route -------------------------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.steps: list[dict[str, Any]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def record_step(self, investigation_id: str, **kwargs: Any) -> object:
        self.steps.append({"investigation_id": investigation_id, **kwargs})
        return object()

    async def record(self, **kwargs: object) -> None:
        return None


class _Datasets:
    """Records which case's datasets were copied to which."""

    def __init__(self) -> None:
        self.copies: list[tuple[str, str]] = []

    async def copy_case(self, source: str, new: str) -> None:
        self.copies.append((source, new))


@contextmanager
def _route(
    store: FakeWorkingSetStore, reader: Principal = ALICE
) -> Iterator[tuple[TestClient, _Recorder, _FakeInvestigations]]:
    recorder = _Recorder()
    investigations = _FakeInvestigations()
    datasets = _Datasets()
    investigations.datasets = datasets  # type: ignore[attr-defined]
    app.dependency_overrides[get_datasets] = lambda: datasets
    app.dependency_overrides[get_principal] = lambda: reader
    app.dependency_overrides[get_working_set] = lambda: _service(store)
    app.dependency_overrides[get_audit] = lambda: recorder
    app.dependency_overrides[get_history] = lambda: recorder
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_valkey] = lambda: recorder
    try:
        yield TestClient(app), recorder, investigations
    finally:
        app.dependency_overrides.clear()


URL = f"/v1/investigations/{CASE}/branch-by-filter"


async def test_within_the_cap_the_route_creates_the_case_as_a_branch_is_created() -> None:
    store = await _held()
    with _route(store) as (client, recorder, investigations):
        response = client.post(URL, json={"entity_types": ["Person"]})

    assert response.status_code == 201
    body = response.json()
    assert body["branched_from"] == CASE and body["created_by"] == "alice"
    assert body["name"] == "Branch of Fixture Corp"
    (published,) = recorder.published
    assert {n["id"] for n in __import__("json").loads(published[1])["nodes"]} == {"p1", "p2"}
    assert [step["investigation_id"] for step in recorder.steps] == [body["id"]]
    assert recorder.steps[0]["label"] == f"Branched from {CASE}"  # today's label; U8 fixes it
    assert [c.id for c in investigations.created] == [body["id"]]


async def test_past_the_cap_the_route_answers_limit_exceeded_and_creates_nothing(
    small_cap: None,
) -> None:
    store = FakeWorkingSetStore()
    await store.add_nodes(CASE, [_typed(f"p{i}", "Person") for i in range(3)])
    with _route(store) as (client, recorder, investigations):
        response = client.post(URL, json={"entity_types": ["Person"]})

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "limit_exceeded" and (body["cap_kind"], body["would_be"]) == (
        "nodes",
        3,
    )
    assert investigations.created == [] and recorder.published == [] and recorder.steps == []


async def test_the_routes_answer_for_a_hidden_type_is_the_answer_for_an_absent_one() -> None:
    """Rule 4, on the route: the same status and body, and no case created, for a type only hidden
    material holds and a type that is absent."""
    traces = []
    for chosen in ("Weapon", "Unicorn"):
        with _route(await _held()) as (client, recorder, investigations):
            response = client.post(URL, json={"entity_types": [chosen]})
        traces.append(
            (response.status_code, response.json(), investigations.created, recorder.steps)
        )

    assert traces[0] == traces[1]
    assert traces[0][0] == 422 and traces[0][1] == {"error": "nothing_to_branch"}


async def test_a_request_that_chooses_nothing_is_refused() -> None:
    with _route(await _held()) as (client, _, investigations):
        response = client.post(URL, json={})

    assert response.status_code == 422 and investigations.created == []


async def test_the_filtered_branch_takes_its_parents_domain_packs_as_a_branch_does() -> None:
    """ADR-126 Amendment 1: a filtered branch is the same kind of case as the one it was made from.
    The packs the parent holds are the packs `create` is given, and a parent never chosen (NULL)
    or chosen as POLE (`[]`) passes on exactly that."""
    asked = []
    for case, packs in (("mixed", ["fibo", "niem"]), ("unchosen", None), ("pole", [])):
        store = FakeWorkingSetStore()
        await store.add_nodes(case, [_typed("p1", "Person")])
        with _route(store) as (client, _, investigations):
            investigations.add(case, "A case", owner=ALICE, domains=packs)
            response = client.post(
                f"/v1/investigations/{case}/branch-by-filter", json={"entity_types": ["Person"]}
            )
            assert response.status_code == 201, (case, response.json())
            asked.append(investigations.asked_domains)

    assert asked == [[["fibo", "niem"]], [None], [[]]]


async def test_the_filtered_branch_takes_its_parents_datasets() -> None:
    """Decision 2: it copies the parent's datasets (ADR-099), from the parent to the new case."""
    with _route(await _held()) as (client, _, investigations):
        response = client.post(URL, json={"entity_types": ["Person"]})

    assert response.status_code == 201
    assert investigations.datasets.copies == [(CASE, response.json()["id"])]  # type: ignore[attr-defined]


async def test_a_branch_made_for_a_reader_scoped_to_the_cases_datasets_holds_only_theirs() -> None:
    """The datasets axis (ADR-099): a node and a link outside the case's datasets are not in the
    reader's view, so they are not in what is copied, whatever their marking."""
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [
            _typed("mine", "Person").model_copy(update={"datasets": ["fixture"]}),
            _typed("also-mine", "Person").model_copy(update={"datasets": ["fixture"]}),
            _typed("theirs", "Person").model_copy(update={"datasets": ["enron"]}),
        ],
    )
    await store.add_edges(
        CASE,
        [
            edge("in-case", "mine", "also-mine").model_copy(update={"datasets": ["fixture"]}),
            edge("elsewhere", "mine", "theirs").model_copy(update={"datasets": ["enron"]}),
        ],
    )
    scoped = ALICE.model_copy(update={"datasets": ["fixture"]})
    with _route(store, scoped) as (client, recorder, _):
        response = client.post(URL, json={"entity_types": ["Person"]})

    assert response.status_code == 201
    (published,) = recorder.published
    delta = __import__("json").loads(published[1])
    assert {n["id"] for n in delta["nodes"]} == {"mine", "also-mine"}
    assert {e["id"] for e in delta["edges"]} == {"in-case"}
