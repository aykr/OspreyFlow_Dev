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
        level = LEVELS.get(principal.id)
        if investigation_id != CASE or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError(investigation_id)
        return self.case


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
