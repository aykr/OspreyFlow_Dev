"""A release of held rows is a load of its own, so it runs the drawn watches as every load does
(spec 01, *A load meeting a drawn item*; ADR-143 Amendment 2 decision 8; L3.H2 part 1), and the
read-set's level check is the app's own (L3.H2 part 3).

The route runs as the app runs it (`release_held_rows_route`), the release's own load stood in for
(`release_held_rows`, its report as the engine would give it), and the drawn watch run for real
through the board world's stores: its graph filters by handling as the adapter does (rule 15).

What a mistake would do, and the case that catches it:

- a release meeting a drawn item and raising nothing (the carry this step closes):
  `test_a_release_meeting_a_drawn_item_raises_its_owners_alert_and_says_so`, red with the route's
  call planted out;
- the releaser told another owner's alert (rules 3 and 7):
  `test_a_release_tells_the_releaser_only_of_their_own_drawn_watch_alerts`;
- a failing drawn watch failing the release, or failing unaudited:
  `test_a_failing_drawn_watch_never_fails_the_release_and_is_audited`;
- a second copy of the level check, which can drift from the app's:
  `test_the_read_sets_level_check_is_the_apps_own`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from services.api import app as app_module
from services.api import drawn_watches
from services.api.board_store import InMemoryBoardItemStore

from schemas.domain import Alert, Principal
from schemas.ingest import LoadReport

from .test_boards import ONTOLOGY, PEOPLE, K, _board, _item, _loaded, world  # noqa: F401
from .test_load_records import SCHEME, Ledger, _held, _published_recipe


class _Alerts:
    def __init__(self) -> None:
        self.saved: list[Alert] = []

    async def save(self, alert: Alert, **kwargs: Any) -> None:
        self.saved.append(alert)


class _Owners:
    """Token Exchange as the resolver gives it: each owner resolved afresh."""

    async def resolve_for_owner(self, owner_id: str) -> Principal | None:
        return PEOPLE.get(owner_id)


class _Held:
    def __init__(self) -> None:
        self.held = [_held("load-0").model_copy(update={"investigation_id": K})]

    async def get_authorized(self, held_id: str, investigation_id: str, principal: Any) -> Any:
        return self.held[0]

    async def decide_for_reader(self, ids: Any, case: str, principal: Any, **kw: Any) -> Any:
        return self.held


async def _release(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    who: str,
    loaded: list[str],
    alerts: _Alerts,
) -> Any:
    """The route, its release loading `loaded` into `src` under load `load-r`."""

    async def release(*args: Any, **kwargs: Any) -> LoadReport:
        return LoadReport(load_id="load-r", recipe_id="r", recipe_version=2, rows_read=1,
                          nodes_created=len(loaded), created_node_ids=loaded)  # fmt: skip

    async def rule_gate(*args: Any, **kwargs: Any) -> Any:
        return object()

    monkeypatch.setattr(app_module, "release_held_rows", release)
    monkeypatch.setattr(app_module, "_rule_gate", rule_gate)
    monkeypatch.setattr(app_module, "load_published_recipe", lambda *a, **k: object())
    recipe = _published_recipe().model_copy(
        update={"git_path": "recipes/x.yaml", "dataset_id": "src"}
    )
    return await app_module.release_held_rows_route(
        investigation=SimpleNamespace(id=K),  # type: ignore[arg-type]
        recipe=recipe,
        principal=PEOPLE[who],
        body=SimpleNamespace(ids=["h"], reason=None),  # type: ignore[arg-type]
        graph=world.graph, ontology=ONTOLOGY, analytics=1, media=1,  # type: ignore[arg-type]
        repo_root=1, audit=world.audit, valkey=1, handling_scheme=SCHEME,  # type: ignore[arg-type]
        alerts_store=alerts, principal_resolver=_Owners(),  # type: ignore[arg-type]
        typology_rules=1, held_rows=_Held(), screening_lists=1, compute=1,  # type: ignore[arg-type]
        kyc_expiries=1, patterns_store=1, recipe_runs=Ledger(),  # type: ignore[arg-type]
        board_items=world.items, datasets=world.datasets,  # type: ignore[arg-type]
        investigations=world.cases,  # type: ignore[arg-type]
    )  # fmt: skip


def _tall(who: str = "alice") -> dict[str, Any]:
    return _item(_board(who), who=who, label="Tall",
                 properties={"family_name": "Tall", "pnc_id": "PNC-1"})  # fmt: skip


def _load(world: SimpleNamespace, node_id: str, **props: Any) -> str:  # noqa: F811
    world.graph._graph_nodes[node_id] = _loaded(node_id, **props)
    return node_id


async def test_a_release_meeting_a_drawn_item_raises_its_owners_alert_and_says_so(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drawn = _tall()
    released = _load(world, "p-released", family_name="Tall", pnc_id="PNC-1")
    alerts = _Alerts()
    view = await _release(world, monkeypatch, "alice", [released], alerts)
    (alert,) = alerts.saved
    assert alert.rule_id.startswith("drawn_watch:") and alert.owner_id == "alice"
    assert alert.investigation_id == K
    assert set(alert.referent_node_ids) == {drawn["element_id"], released}
    assert view.drawn_watch_alerts == 1
    # Claimed once: the same row released again raises nothing more.
    again = await _release(world, monkeypatch, "alice", [released], alerts)
    assert len(alerts.saved) == 1 and again.drawn_watch_alerts == 0


async def test_a_release_tells_the_releaser_only_of_their_own_drawn_watch_alerts(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dora releases; Alice's drawn item is met. Alice's alert is raised, and Dora is told of no
    alert, so the release says nothing of another person's drawn items (rules 3 and 7)."""
    _tall("alice")
    released = _load(world, "p-released", family_name="Tall", pnc_id="PNC-1")
    alerts = _Alerts()
    view = await _release(world, monkeypatch, "dora", [released], alerts)
    assert [a.owner_id for a in alerts.saved] == ["alice"]
    assert view.drawn_watch_alerts == 0


async def test_a_failing_drawn_watch_never_fails_the_release_and_is_audited(
    world: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tall()
    released = _load(world, "p-released", family_name="Tall", pnc_id="PNC-1")

    async def broken(self: Any, dataset_id: str) -> Any:
        raise RuntimeError("the board store is down")

    monkeypatch.setattr(InMemoryBoardItemStore, "active_watches_on", broken)
    view = await _release(world, monkeypatch, "alice", [released], _Alerts())
    assert view.load_id == "load-r" and view.drawn_watch_alerts == 0
    (failed,) = [r for r in world.audit.records if r["action"] == "watch_evaluation_failed"]
    assert failed["resolved_query"]["load_id"] == "load-r"
    assert failed["resolved_query"]["drawn_watches"] is True


def test_the_read_sets_level_check_is_the_apps_own() -> None:
    """One level check for the read set (`dataset_scope.holds_a_level_in`), which the app's own
    scope (`scope_to_case`) and the drawn watches both use, never a copy that could drift."""
    from services.api.dataset_scope import holds_a_level_in

    assert app_module.holds_a_level_in is holds_a_level_in
    assert drawn_watches.holds_a_level_in is holds_a_level_in
