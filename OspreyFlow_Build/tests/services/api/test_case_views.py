"""Case views (ADR-144 decisions 1-4; `01_DOMAIN_MODEL.md` §2.2c; L3.2 part B), through the real
app: the real `get_principal`, which scopes the reader to the case's read set, and the case's own
level check. The graph is `FakeGraphPort`, which judges each element by its own body (handling and
datasets) for the principal given, as the adapter's access step does.

What a mistake here would do, and the case that catches it:

- a view handing a reader what it stored rather than what they may see now, so an item hidden from
  them, or gone, is named to them: `test_a_view_shows_the_rest_and_counts_the_missing`, red with
  the view returning its stored selection
  (`test_the_missing_check_fails_with_the_stored_selection_returned`);
- another member of the case seeing, opening, sharing or deleting a private view:
  `test_a_private_view_is_invisible_to_another_member`, red with the store's visibility planted out
  (`test_the_privacy_check_fails_with_the_visibility_planted_out`);
- deleting a view deleting what is on it: `test_deleting_a_view_leaves_everything_drawn_in_place`,
  red with a cascading delete planted (`test_the_delete_check_fails_with_a_cascade_planted`);
- a reader with no level on the case reaching any view route, or telling the case exists from the
  answer: `test_every_view_route_refuses_a_non_member` (rule 4);
- a person without `investigate` (a Reports Viewer) saving, sharing or deleting a view:
  `test_saving_sharing_and_deleting_need_investigate`.

The same visibility on real Postgres is in `test_case_views_store.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import case_views as case_views_module
from services.api.app import app
from services.api.case_views import InMemoryCaseViewStore
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.working_set.service import WorkingSetService

from schemas.domain import Edge, Node, Principal, Subgraph

from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

UNIT = "unit-1"
PEOPLE = {
    "alice": Principal(id="alice", clearance="SECRET", org_unit=UNIT, roles=["analyst"]),
    "bob": Principal(id="bob", clearance="OFFICIAL", org_unit=UNIT, roles=["analyst"]),
    "carol": Principal(id="carol", clearance="SECRET", org_unit=UNIT, roles=["analyst"]),
    "rita": Principal(id="rita", clearance="SECRET", org_unit=UNIT, roles=["reports_viewer"]),
}
CASE = "case-k"
#: Alice is the case's Author, Bob an Editor and Rita a Viewer; Carol, of the same unit, holds none.
LEVELS = {"alice": AccessLevel.AUTHOR, "bob": AccessLevel.EDITOR, "rita": AccessLevel.VIEWER}
#: A second case, Bob's, of which Alice is an Editor too: a view is reached only through its own.
OTHER = "case-b"
CASES = {CASE: LEVELS, OTHER: {"bob": AccessLevel.AUTHOR, "alice": AccessLevel.EDITOR}}


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return PEOPLE[token]


class _Investigations:
    """One case, with the levels above: none is a 404, too low a 403, as the real store answers."""

    case = Investigation(
        id=CASE,
        name="Kestrel",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
        created_by="alice",
        owning_unit=UNIT,
    )

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        level = CASES.get(investigation_id, {}).get(principal.id)
        if level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError(investigation_id)
        return self.case.model_copy(update={"id": investigation_id})


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


def _in(dataset: str, element: Node | Edge) -> Any:
    return element.model_copy(update={"datasets": [dataset]})


class _World:
    def __init__(self) -> None:
        self.datasets = InMemoryDatasetStore()
        for dataset_id, name in (("src", "Prison intel"), ("other", "Not read by the case")):
            self.datasets.datasets[dataset_id] = Dataset(
                id=dataset_id,
                name=name,
                owning_unit=UNIT,
                created_at=datetime(2026, 11, 1, tzinfo=UTC),
                created_by="alice",
            )
        self.datasets.cases[CASE] = ["src"]
        self.graph_nodes = [
            _in("src", node("open")),
            _in("src", node("near")),
            _in("src", node("secret", "SECRET")),
            # Readable by its marking, but in a dataset the case does not read.
            _in("other", node("elsewhere")),
        ]
        self.graph_edges = [_in("src", edge("e-open-near", "open", "near"))]
        self.graph = FakeGraphPort(
            Subgraph(nodes=[], edges=[]), graph_nodes=self.graph_nodes, graph_edges=self.graph_edges
        )
        self.working = FakeWorkingSetStore()
        self.views = InMemoryCaseViewStore()
        self.audit = _Audit()


@pytest.fixture
def world() -> Iterator[_World]:
    held = _World()
    state = {
        "principal_resolver": _Resolver(),
        "investigations": _Investigations(),
        "datasets": held.datasets,
        "audit": held.audit,
        "graph": held.graph,
        "working_set": WorkingSetService(held.graph, held.working, SCHEME),
        "case_views": held.views,
        "target_models": None,
    }
    saved = {k: getattr(app.state, k, None) for k in state}
    for key, value in state.items():
        setattr(app.state, key, value)
    try:
        yield held
    finally:
        for key, value in saved.items():
            setattr(app.state, key, value)


def _as(who: str) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {who}"})


VIEWS = f"/v1/investigations/{CASE}/views"
CHOSEN = ["open", "near", "secret", "elsewhere", "never-held"]
LAYOUT = {i: {"x": float(n), "y": 0.0} for n, i in enumerate(CHOSEN)}


def _saved(who: str = "alice", *, shared: bool = False, **body: Any) -> str:
    response = _as(who).post(
        VIEWS, json={"name": "Kestrel's contacts", "node_ids": CHOSEN, "layout": LAYOUT, **body}
    )
    assert response.status_code == 201, response.json()
    view_id = response.json()["id"]
    if shared:
        assert _as(who).post(f"{VIEWS}/{view_id}/share").status_code == 200
    return str(view_id)


# --- live, never a copy -----------------------------------------------------------------------


def _bob_opens_alices_shared_view() -> Any:
    view_id = _saved(shared=True)
    return _as("bob").get(f"{VIEWS}/{view_id}")


def test_a_view_shows_the_rest_and_counts_the_missing(world: _World) -> None:
    """Bob (OFFICIAL) opens Alice's shared view of five chosen ids: he sees the two he may read and
    the link between them, and a count of three he cannot, never which: the SECRET node, the node in
    a dataset the case does not read, and an id nobody holds read alike."""
    response = _bob_opens_alices_shared_view()
    assert response.status_code == 200, response.json()
    opened = response.json()
    assert sorted(n["id"] for n in opened["nodes"]) == ["near", "open"]
    assert [e["id"] for e in opened["edges"]] == ["e-open-near"]
    assert opened["missing"] == 3
    assert opened["view"]["chosen"] == 5
    # Nowhere in the answer: not as an item, not in the view's own fields, not in its layout.
    for hidden in ("secret", "elsewhere", "never-held"):
        assert hidden not in response.text
    assert sorted(opened["layout"]) == ["near", "open"]


def test_no_listing_names_a_chosen_node(world: _World) -> None:
    """The case's view list, for every member, and the saved and the shared view, each carry the
    selection's count, never its ids or their positions: the selection is its creator's (rules 3
    and 7). Red with the stored ids restored to the wire (a33cd65's `CaseView`, sent as stored):
    `process/lanes/case/L3.2_RED_RECORD.md`."""
    response = _as("alice").post(VIEWS, json={"name": "Mine", "node_ids": CHOSEN, "layout": LAYOUT})
    view_id = response.json()["id"]
    shared = _as("alice").post(f"{VIEWS}/{view_id}/share")
    listed = [_as(who).get(VIEWS) for who in LEVELS]  # every member: Author, Editor and Viewer
    assert all(len(answer.json()) == 1 for answer in listed)
    for answer in (response, shared, *listed):
        for hidden in ("secret", "elsewhere", "never-held"):
            assert hidden not in answer.text
        assert "node_ids" not in answer.text and "layout" not in answer.text


def test_the_view_reads_as_its_reader_not_its_creator(world: _World) -> None:
    """Alice (SECRET) opening her own view sees the SECRET node too: the same view, read live for
    each reader."""
    view_id = _saved()
    opened = _as("alice").get(f"{VIEWS}/{view_id}").json()
    assert sorted(n["id"] for n in opened["nodes"]) == ["near", "open", "secret"]
    assert opened["missing"] == 2


def test_the_missing_check_fails_with_the_stored_selection_returned(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, at the real call site's shape: `open_view` reading the selection through
    `_read_selection` with the principal it is given. Planted to hand back what the view stored,
    read without the reader's scope, the hidden nodes reach Bob and nothing is missing."""

    async def stored(graph: Any, node_ids: Any, principal: Principal) -> Any:
        unscoped = principal.model_copy(update={"datasets": None, "clearance": "SECRET"})
        nodes = await graph.get_nodes(list(node_ids), unscoped)
        return nodes, await graph.edges_among([n.id for n in nodes], unscoped)

    monkeypatch.setattr(case_views_module, "_read_selection", stored)
    opened = _bob_opens_alices_shared_view().json()
    assert "secret" in {n["id"] for n in opened["nodes"]}
    assert opened["missing"] != 3


def test_a_filtered_view_reads_the_readers_own_projection(world: _World) -> None:
    """A filtered view narrows the case's working set as the reader may see it, now."""
    import asyncio

    asyncio.run(
        world.working.add_nodes(
            CASE,
            [
                world.graph_nodes[0],
                world.graph_nodes[2],
                world.graph_nodes[1].model_copy(update={"type": "Vehicle"}),
            ],
        )
    )
    view_id = _saved(node_ids=None, filter={"entity_types": ["Person"]}, shared=True)
    opened = _as("bob").get(f"{VIEWS}/{view_id}").json()
    assert [n["id"] for n in opened["nodes"]] == ["open"]
    assert opened["missing"] == 0


# --- private until shared ---------------------------------------------------------------------


def test_a_private_view_is_invisible_to_another_member(world: _World) -> None:
    """Alice's private view: Bob, an Editor of the case, does not see it listed, and opening,
    sharing or deleting it answers exactly as for a view that does not exist. Shared, he sees it
    and opens it at his own level."""
    view_id = _saved()
    bob = _as("bob")
    assert bob.get(VIEWS).json() == []
    absent = bob.get(f"{VIEWS}/no-such-view")
    for response in (
        bob.get(f"{VIEWS}/{view_id}"),
        bob.post(f"{VIEWS}/{view_id}/share"),
        bob.delete(f"{VIEWS}/{view_id}"),
    ):
        assert (response.status_code, response.json()) == (404, absent.json())
    assert absent.status_code == 404
    assert not world.views.views[view_id].shared

    assert _as("alice").post(f"{VIEWS}/{view_id}/share").status_code == 200
    assert [v["id"] for v in bob.get(VIEWS).json()] == [view_id]
    assert bob.get(f"{VIEWS}/{view_id}").json()["missing"] == 3


def test_the_privacy_check_fails_with_the_visibility_planted_out(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the store's own visibility (`visible_to`, which every in-memory read asks) planted
    out, Bob lists and opens Alice's private view."""
    monkeypatch.setattr(case_views_module, "visible_to", lambda view, reader: True)
    view_id = _saved()
    assert [v["id"] for v in _as("bob").get(VIEWS).json()] == [view_id]
    assert _as("bob").get(f"{VIEWS}/{view_id}").status_code == 200


# --- only its creator deletes it, and deleting deletes nothing else ---------------------------


def _draw_on_the_case(world: _World) -> tuple[set[str], set[str]]:
    import asyncio

    asyncio.run(world.working.add_nodes(CASE, world.graph_nodes[:3]))
    asyncio.run(world.working.add_edges(CASE, world.graph_edges))
    return _on_the_case(world)


def _on_the_case(world: _World) -> tuple[set[str], set[str]]:
    import asyncio

    return asyncio.run(world.working.node_ids(CASE)), asyncio.run(world.working.edge_ids(CASE))


def test_deleting_a_view_leaves_everything_drawn_in_place(world: _World) -> None:
    """Bob may not delete Alice's shared view (403, in words: he can already see it). Alice deletes
    it; every node and link of the case, and in the graph, is still there."""
    before = _draw_on_the_case(world)
    view_id = _saved(shared=True)
    refused = _as("bob").delete(f"{VIEWS}/{view_id}")
    assert refused.status_code == 403
    assert refused.json()["error"] == "not_the_views_creator"
    assert "Only the person who saved this view" in refused.json()["detail"]

    assert _as("alice").delete(f"{VIEWS}/{view_id}").status_code == 204
    assert view_id not in world.views.views
    assert _on_the_case(world) == before
    assert _as("alice").get(f"{VIEWS}/{view_id}").status_code == 404


def test_the_delete_check_fails_with_a_cascade_planted(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: a delete that also clears the view's chosen nodes from the case (the cascade ADR-144
    forbids), planted into the store's delete, takes them off the case."""
    before = _draw_on_the_case(world)
    view_id = _saved()
    real_delete = InMemoryCaseViewStore.delete

    async def cascading(self: InMemoryCaseViewStore, case_id: str, vid: str, reader: str) -> None:
        view = await self.get(case_id, vid, reader)
        await world.working.remove_nodes(case_id, view.node_ids or [])
        await real_delete(self, case_id, vid, reader)

    monkeypatch.setattr(InMemoryCaseViewStore, "delete", cascading)
    assert _as("alice").delete(f"{VIEWS}/{view_id}").status_code == 204
    assert _on_the_case(world) != before


# --- the case's own gate, first (rule 4) ------------------------------------------------------


def test_every_view_route_refuses_a_non_member(world: _World) -> None:
    """Carol, of the case's unit and cleared higher than Bob, holds no level on it: every view
    route answers her exactly as it answers for a case that does not exist, and she saves
    nothing."""
    view_id = _saved(shared=True)
    carol = _as("carol")

    def routes(case: str) -> list[Any]:
        base = f"/v1/investigations/{case}/views"
        return [
            carol.get(base),
            carol.post(base, json={"name": "Mine", "node_ids": ["open"]}),
            carol.get(f"{base}/{view_id}"),
            carol.post(f"{base}/{view_id}/share"),
            carol.delete(f"{base}/{view_id}"),
        ]

    for refused, missing in zip(routes(CASE), routes("no-such-case"), strict=True):
        assert refused.status_code == 404
        assert (refused.status_code, refused.json()) == (missing.status_code, missing.json())
    assert [v.created_by for v in world.views.views.values()] == ["alice"]


def test_saving_sharing_and_deleting_need_investigate(world: _World) -> None:
    """Rita, a Reports Viewer with a Viewer level, may list and open a shared view but not save,
    share or delete one."""
    view_id = _saved(shared=True)
    rita = _as("rita")
    assert [v["id"] for v in rita.get(VIEWS).json()] == [view_id]
    assert rita.get(f"{VIEWS}/{view_id}").status_code == 200
    assert rita.post(VIEWS, json={"name": "Mine", "node_ids": ["open"]}).status_code == 403
    assert rita.post(f"{VIEWS}/{view_id}/share").status_code == 403
    assert rita.delete(f"{VIEWS}/{view_id}").status_code == 403
    assert len(world.views.views) == 1


def test_a_view_shows_one_lens(world: _World) -> None:
    """Exactly one of a node selection or a filter."""
    both = _as("alice").post(
        VIEWS, json={"name": "Both", "node_ids": ["open"], "filter": {"entity_types": ["Person"]}}
    )
    neither = _as("alice").post(VIEWS, json={"name": "Neither"})
    assert (both.status_code, neither.status_code) == (422, 422)
    assert world.views.views == {}


# --- a view's conversation (L3.2's Q2, the owner's ruling of 8 November 2026) ------------------


class _Questions:
    """The questions service as the routes call it, over the real in-memory store: one entry in
    the case's own conversation and one kept with a view."""

    def __init__(self, view_id: str) -> None:
        from services.api.questions import InMemoryQuestionStore, QuestionEntry

        self.store = InMemoryQuestionStore()
        for entry_id, kept_with in (("q-case", None), ("q-view", view_id)):
            self.store.entries.append(
                QuestionEntry(
                    id=entry_id, investigation_id=CASE, author="alice", question="Who?",
                    answer="Dana.", model="local-model", view_id=kept_with,
                    created_at=datetime(2026, 11, 8, tzinfo=UTC),
                )  # fmt: skip
            )
        self.asked: list[dict[str, Any]] = []

    async def history(
        self, investigation_id: str, principal: Principal, *, view_id: str | None = None
    ) -> list[Any]:
        from services.api.questions import QuestionAnswer

        return [
            QuestionAnswer(
                id=e.id, author=e.author, question=e.question, answer=e.answer, citations=[],
                candidates=[], unplaced=0, created_at=e.created_at,
            )  # fmt: skip
            for e in await self.store.list_for_case(investigation_id, view_id)
        ]


@pytest.fixture
def conversation(world: _World) -> Iterator[tuple[_Questions, str]]:
    from services.api.app import get_principal_names, get_questions

    view_id = _saved()  # Alice's, private
    questions = _Questions(view_id)

    class _Names:
        async def display_names(self, ids: Any) -> dict[str, str]:
            return {}

    app.dependency_overrides[get_questions] = lambda: questions
    app.dependency_overrides[get_principal_names] = lambda: _Names()
    try:
        yield questions, view_id
    finally:
        app.dependency_overrides.pop(get_questions, None)
        app.dependency_overrides.pop(get_principal_names, None)


def _ids(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [q["id"] for q in response.json()]


def test_a_private_views_conversation_is_read_by_its_creator_alone(
    world: _World, conversation: tuple[_Questions, str]
) -> None:
    """Bob, an Editor of the case, is answered 404 for Alice's private view's conversation, as for
    a view that does not exist, and the case's own conversation never carries it. Alice reads it;
    shared, Bob does."""
    _, view_id = conversation
    q = f"/v1/investigations/{CASE}/questions"
    refused = _as("bob").get(q, params={"view_id": view_id})
    missing = _as("bob").get(q, params={"view_id": "no-such-view"})
    assert (refused.status_code, refused.json()) == (404, missing.json())
    assert _ids(_as("bob").get(q)) == ["q-case"]
    assert _ids(_as("alice").get(q, params={"view_id": view_id})) == ["q-view"]
    assert _as("alice").post(f"{VIEWS}/{view_id}/share").status_code == 200
    assert _ids(_as("bob").get(q, params={"view_id": view_id})) == ["q-view"]


def test_the_conversation_check_fails_with_the_view_check_removed(
    world: _World, conversation: tuple[_Questions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the view check (the store's own visibility, which the route asks) planted out, Bob
    reads Alice's private view's conversation."""
    _, view_id = conversation
    monkeypatch.setattr(case_views_module, "visible_to", lambda view, reader: True)
    q = f"/v1/investigations/{CASE}/questions"
    assert _ids(_as("bob").get(q, params={"view_id": view_id})) == ["q-view"]


def test_asking_in_a_private_view_is_refused_to_another_member(
    world: _World, conversation: tuple[_Questions, str]
) -> None:
    """Asking in Alice's private view is refused to Bob before the model is asked anything."""
    questions, view_id = conversation
    asked = _as("bob").post(
        f"/v1/investigations/{CASE}/questions", json={"question": "Who?", "view_id": view_id}
    )
    assert asked.status_code == 404 and asked.json() == {"error": "view_not_found"}


async def test_the_store_never_mixes_a_views_conversation_with_the_cases() -> None:
    from services.api.questions import InMemoryQuestionStore

    store = _Questions("v-1").store
    assert isinstance(store, InMemoryQuestionStore)
    assert [e.id for e in await store.list_for_case(CASE)] == ["q-case"]
    assert [e.id for e in await store.list_for_case(CASE, "v-1")] == ["q-view"]
    assert await store.list_for_case(CASE, "v-2") == []


# --- a private view's proposals (the lane review's blocker 3) -----------------------------------


@pytest.fixture
def proposals(world: _World) -> Iterator[tuple[Any, str, str]]:
    """Alice's private view, and a proposal its conversation made on a Document, kept with the
    view, in a candidate store that refuses what the Postgres store refuses (`view_clause`)."""
    import asyncio

    from services.api.app import get_extraction_candidates
    from services.extract.candidates import ExtractionCandidate

    from .test_case_writes import HANDLING
    from .test_email_extraction import InMemoryCandidates

    view_id = _saved()
    candidates = InMemoryCandidates()
    (record,) = asyncio.run(
        candidates.store(
            [
                ExtractionCandidate(
                    id="cand-v", document_id="doc-1", entity_type="Person",
                    properties={"family_name": "MERCER"}, confidence=0.9, model="local-model",
                    locator="char span 0-6", excerpt_hash="", handling=HANDLING,
                )  # fmt: skip
            ],
            PEOPLE["alice"],
            view_id=view_id,
        )
    )
    from services.api.app import get_questions, get_valkey

    class _NotAsked:
        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"refused before the questions service: {name}")

    app.dependency_overrides[get_extraction_candidates] = lambda: candidates
    app.dependency_overrides[get_questions] = lambda: _NotAsked()
    app.dependency_overrides[get_valkey] = lambda: _NotAsked()
    try:
        yield candidates, view_id, record.id
    finally:
        for dependency in (get_extraction_candidates, get_questions, get_valkey):
            app.dependency_overrides.pop(dependency, None)


def test_a_private_views_proposals_are_not_read_through_the_case(
    world: _World, proposals: tuple[Any, str, str]
) -> None:
    """Bob, an Editor of the case, finds none of the proposals of Alice's private view's
    conversation through the case's review routes: not listed, and not accepted or rejected, each
    answered as for a candidate that does not exist; nothing is reviewed."""
    candidates, _view_id, candidate = proposals
    base = f"/v1/investigations/{CASE}/ingest/candidates"
    bob = _as("bob")
    assert bob.get(base, params={"document_id": "doc-1"}).json() == []
    for verb in ("accept", "reject"):
        refused = bob.post(f"{base}/{candidate}/{verb}", json={})
        missing = bob.post(f"{base}/no-such/{verb}", json={})
        assert (refused.status_code, refused.json()) == (missing.status_code, missing.json())
    assert candidates.records[candidate].status.value == "pending"


def test_a_private_views_proposals_need_the_view_to_be_seen(
    world: _World, proposals: tuple[Any, str, str]
) -> None:
    """Through the question routes, a proposal kept with Alice's private view is refused to Bob
    as for a view that does not exist, whatever view he names."""
    _, view_id, candidate = proposals
    q = f"/v1/investigations/{CASE}/questions/candidates/{candidate}"
    for verb in ("accept", "reject"):
        refused = _as("bob").post(f"{q}/{verb}", params={"view_id": view_id})
        assert (refused.status_code, refused.json()) == (404, {"error": "view_not_found"})


def test_the_proposal_check_fails_with_the_view_clause_planted_out(
    world: _World, proposals: tuple[Any, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: the store's view clause planted out (here the fake's, which mirrors
    `view_clause`), Bob lists the private view's proposal through the case."""
    from . import test_email_extraction

    monkeypatch.setattr(test_email_extraction, "_in_reach", lambda record, principal: True)
    listed = _as("bob").get(
        f"/v1/investigations/{CASE}/ingest/candidates", params={"document_id": "doc-1"}
    )
    assert [r["id"] for r in listed.json()] == [proposals[2]]


def test_a_view_is_reached_only_through_its_own_case(world: _World) -> None:
    """Rule 4: Alice's shared view of Kestrel, asked for through Bob's other case, where both hold
    a level, answers as a view that does not exist on every route, and is not listed there."""
    world.datasets.cases[OTHER] = ["src"]
    view_id = _saved(shared=True)
    other = f"/v1/investigations/{OTHER}/views"
    for who in ("alice", "bob"):
        client = _as(who)
        assert client.get(other).json() == []
        for response in (
            client.get(f"{other}/{view_id}"),
            client.post(f"{other}/{view_id}/share"),
            client.delete(f"{other}/{view_id}"),
        ):
            assert (response.status_code, response.json()) == (404, {"error": "view_not_found"})
    assert view_id in world.views.views


def test_the_own_case_check_fails_with_the_case_planted_out(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15, red: the store's `get` planted to find a view by id whatever its case."""

    async def any_case(self: InMemoryCaseViewStore, case_id: str, view_id: str, reader: str) -> Any:
        view = self.views.get(view_id)
        if view is None or not case_views_module.visible_to(view, reader):
            raise case_views_module.ViewNotFound(view_id)
        return view

    monkeypatch.setattr(InMemoryCaseViewStore, "get", any_case)
    world.datasets.cases[OTHER] = ["src"]
    view_id = _saved(shared=True)
    assert _as("bob").get(f"/v1/investigations/{OTHER}/views/{view_id}").status_code == 200


# --- no branch route (ADR-144 Amendment 1's test) ---------------------------------------------

BRANCH_PATHS = ["/branch", "/branch-by-filter", "/branch/x"]


def _no_branch_route_answers(path_tail: str) -> None:
    for method in ("GET", "POST", "PUT", "DELETE"):
        answered = _as("alice").request(method, f"/v1/investigations/{CASE}{path_tail}", json={})
        assert answered.status_code in (404, 405), (method, path_tail, answered.status_code)
        assert answered.status_code == 404 or method != "POST", (method, path_tail)


@pytest.mark.parametrize("tail", BRANCH_PATHS)
def test_no_route_under_a_case_makes_a_branch(world: _World, tail: str) -> None:
    """ADR-144 Amendment 1: `/v1/investigations/*/branch*` answers 404; no route under it exists."""
    _no_branch_route_answers(tail)
    assert not [r for r in app.routes if "/branch" in getattr(r, "path", "")]


def test_the_no_branch_route_check_fails_with_one_put_back(world: _World) -> None:
    """Rule 15, red: a branch route put back is found, by the request and by the route table."""
    from fastapi.routing import APIRoute

    async def branch() -> dict[str, str]:
        return {"id": "a-branch"}

    app.router.routes.append(
        APIRoute("/v1/investigations/{investigation_id}/branch", branch, methods=["POST"])
    )
    try:
        with pytest.raises(AssertionError):
            _no_branch_route_answers("/branch")
    finally:
        app.router.routes.pop()
    assert not [r for r in app.routes if "/branch" in getattr(r, "path", "")]


def test_a_deleted_views_conversation_and_proposals_are_read_by_no_one(
    world: _World, proposals: tuple[Any, str, str], conversation: tuple[Any, str]
) -> None:
    """Spec 03 §3.1b: once Alice deletes her view, its conversation and its pending proposal stay
    stored and are read by no route, hers included: the view is gone, so nothing lets a request
    into it."""
    candidates, view_id, candidate = proposals
    questions, conversation_view = conversation
    # The two fixtures each saved a view; delete both, as their creator.
    for gone in {view_id, conversation_view}:
        assert _as("alice").delete(f"{VIEWS}/{gone}").status_code == 204
    q = f"/v1/investigations/{CASE}/questions"
    assert _as("alice").get(q, params={"view_id": conversation_view}).status_code == 404
    assert _ids(_as("alice").get(q)) == ["q-case"]
    assert _as("alice").get(
        f"/v1/investigations/{CASE}/ingest/candidates", params={"document_id": "doc-1"}
    ).json() == []
    accepted = _as("alice").post(f"{q}/candidates/{candidate}/accept", params={"view_id": view_id})
    assert accepted.status_code == 404
    assert candidates.records[candidate].status.value == "pending"
    assert [e.id for e in questions.store.entries] == ["q-case", "q-view"]  # kept, read by none


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", VIEWS), ("POST", VIEWS), ("GET", f"{VIEWS}/v"), ("POST", f"{VIEWS}/v/share"),
     ("DELETE", f"{VIEWS}/v")],
)  # fmt: skip
def test_a_view_route_without_a_token_is_refused(world: _World, method: str, path: str) -> None:
    answered = TestClient(app).request(method, path, json={"name": "x", "node_ids": ["a"]})
    assert answered.status_code in (401, 403)
    assert world.views.views == {}
