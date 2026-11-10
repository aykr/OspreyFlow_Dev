"""A load meeting a drawn item (ADR-143 Amendment 2 decision 8; ADR-146 decision 4; L3.6).

Drawing an item sets a watch for it on the case's dataset (L3.3). After a load into that dataset,
each node it loaded that looks like the drawn item, by the board's own rule (*Looks like a loaded
item*: the same identifier, or a name alike, of the same type), raises one `drawn_watch` alert in
the watch's case, routed as the one queue routes (L2.10, wired when it lands). These cases prove
the run itself, through the board world's fakes (the graph's handling filter is the adapter's, rule
15):

- one alert per match per case, however often a load meets it again (`claim_match`);
- nothing for a loaded node the owner may not see, of another type or unalike, already decided on
  the board, of another dataset, or for a watch ended (its item withdrawn) or an owner gone;
- each case its own alert for the same loaded node.

What a reader of the queue is shown (withheld whole from one who may not see the drawn item: no
count, no bucket) is the queue's read, red at the adapter once L2.10 lands.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from services.api.change_stream import ChangeStreamEntry
from services.api.datasets import COMPOSITE, Dataset
from services.api.drawn_watches import (
    DrawnWatchMatch,
    DrawnWatchRun,
    case_read_set,
    holds_a_level_in,
)
from services.api.investigations import AccessLevel
from services.api.recipe_run import _run_drawn_watches_best_effort

from schemas.domain import Alert, Principal

from .test_boards import ONTOLOGY, PEOPLE, B, K, _as, _board, _item, _loaded, world  # noqa: F401


@pytest.fixture
def run(world: SimpleNamespace) -> Iterator[SimpleNamespace]:  # noqa: F811
    raised: list[DrawnWatchMatch] = []
    gone: set[str] = set()

    async def owner_of(account: str) -> Principal | None:
        return None if account in gone else PEOPLE.get(account)

    async def raise_alert(match: DrawnWatchMatch) -> None:
        raised.append(match)

    yield SimpleNamespace(
        world=world, raised=raised, gone=gone,
        run=DrawnWatchRun(items=world.items, graph=world.graph, ontology=ONTOLOGY,
                          owner_of=owner_of, datasets=world.datasets,
                          holds_a_level=holds_a_level_in(world.cases), raise_alert=raise_alert),
    )  # fmt: skip


def _load(run: SimpleNamespace, node_id: str, marking: str = "OFFICIAL", **props: Any) -> str:
    """A node a load wrote into `src`."""
    run.world.graph._graph_nodes[node_id] = _loaded(node_id, marking, **props)
    return node_id


def _tall(**over: Any) -> dict[str, Any]:
    return _item(_board(), label="Tall", properties={"family_name": "Tall", "pnc_id": "PNC-1"},
                 **over)  # fmt: skip


async def test_a_loaded_node_like_a_drawn_item_raises_one_alert_per_match_per_case(
    run: SimpleNamespace,
) -> None:
    drawn = _tall()
    first = _load(run, "p-new", family_name="Tall", pnc_id="PNC-1")
    assert await run.run.after_load("src", [first], load_id="load-1") == 1
    (match,) = run.raised
    assert (match.watch.case_id, match.drawn.id, match.loaded.id) == (K, drawn["element_id"], first)
    assert (match.score, match.why, match.load_id) == (1.0, "the same pnc_id", "load-1")
    # The same node loaded again: no second alert (one per match per case).
    assert await run.run.after_load("src", [first], load_id="load-2") == 0
    # Another node like it: its own alert.
    second = _load(run, "p-newer", family_name="Tall")
    assert await run.run.after_load("src", [second], load_id="load-3") == 1
    assert [(m.loaded.id, m.why) for m in run.raised[1:]] == [(second, "a name alike")]


async def test_nothing_is_raised_for_a_node_unalike_of_another_type_or_drawn(
    run: SimpleNamespace,
) -> None:
    _tall()
    unalike = _load(run, "p-unalike", family_name="Quite different")
    other_type = _loaded("o-tall").model_copy(
        update={"type": "Organisation", "properties": {"name": "Tall"}}
    )
    run.world.graph._graph_nodes[other_type.id] = other_type
    # Another drawn item, alike it and promoted into `src` (so in the load's dataset): drawn,
    # never loaded, so never a match.
    other_drawn = _item(_board(), label="Tall", properties={"family_name": "Tall"})["element_id"]
    held = run.world.graph._graph_nodes[other_drawn]
    run.world.graph._graph_nodes[other_drawn] = held.model_copy(
        update={"datasets": sorted({*held.datasets, "src"})}
    )
    assert await run.run.after_load("src", [unalike, other_type.id, other_drawn]) == 0
    assert run.raised == []


async def test_nothing_is_raised_for_a_node_the_owner_may_not_see(run: SimpleNamespace) -> None:
    """Bob (OFFICIAL) drew it; a SECRET node alike it is never read for him, so never matched,
    never claimed (rule 3)."""
    _item(_board("bob"), who="bob", label="Tall", properties={"family_name": "Tall"})
    hidden = _load(run, "p-hidden", "SECRET", family_name="Tall")
    assert await run.run.after_load("src", [hidden]) == 0
    assert run.raised == []
    assert run.world.items.matches == {}


async def test_nothing_is_raised_for_another_datasets_load_an_ended_watch_or_an_owner_gone(
    run: SimpleNamespace,
) -> None:
    drawn = _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    assert await run.run.after_load("other", [alike]) == 0  # the watch is on src
    run.gone.add("alice")
    assert await run.run.after_load("src", [alike]) == 0  # its owner no longer resolves
    run.gone.clear()
    withdrawn = _as("alice").post(f"/v1/investigations/{K}/board-items/{drawn['item_id']}/withdraw")
    assert withdrawn.status_code == 200, withdrawn.text
    assert await run.run.after_load("src", [alike]) == 0  # its item withdrawn: the watch ended
    assert run.raised == []


async def test_a_pair_decided_on_the_board_raises_nothing(run: SimpleNamespace) -> None:
    """*Not the same* (or *Same*) already decided between the two: there is nothing to tell."""
    board = _board()
    drawn = _item(board, properties={"family_name": "Mercer", "nino": "AB123456C"})
    decided = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/matches",
        json={"drawn": drawn["element_id"], "loaded": "p-loaded", "same": False},
    )
    assert decided.status_code == 201, decided.text
    assert await run.run.after_load("src", ["p-loaded"]) == 0
    assert run.raised == []


async def test_each_case_gets_its_own_alert_for_the_same_loaded_node(run: SimpleNamespace) -> None:
    _tall()
    _item(_board("carol", B), who="carol", case=B, label="Tall",
          properties={"family_name": "Tall"})  # fmt: skip
    alike = _load(run, "p-alike", family_name="Tall")
    assert await run.run.after_load("src", [alike]) == 2
    assert sorted(m.watch.case_id for m in run.raised) == sorted([K, B])
    assert await run.run.after_load("src", [alike]) == 0


async def test_a_load_counted_by_what_it_raised_never_by_what_it_read(
    run: SimpleNamespace,
) -> None:
    """The run says how many alerts it raised, for the run's report; a node read but unmatched,
    or hidden, is not in it (rule 7). Bob (OFFICIAL) drew it."""
    _item(_board("bob"), who="bob", label="Tall", properties={"family_name": "Tall"})
    alike = _load(run, "p-alike", family_name="Tall")
    hidden = _load(run, "p-hidden", "SECRET", family_name="Tall")
    assert await run.run.after_load("src", [alike, hidden, "no-such-node"]) == 1
    assert datetime.now(UTC) >= run.raised[0].matched_at


async def test_nothing_is_raised_once_the_case_reads_the_dataset_no_more(
    run: SimpleNamespace,
) -> None:
    """The watch is on the case's dataset; a case that has moved off it is told nothing of a load
    into it (its readers no longer read it)."""
    _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    run.world.datasets.cases[K] = ["other"]
    assert await run.run.after_load("src", [alike]) == 0
    assert run.raised == []


# --- after a recipe run (`recipe_run._run_drawn_watches_best_effort`) ----------------------------


class _Alerts:
    """`AlertStore.save` as the run calls it: the alert and the markings of what it cites."""

    def __init__(self, fails: bool = False) -> None:
        self.saved: list[tuple[Alert, list[Any]]] = []
        self.fails = fails

    async def save(self, alert: Alert, *, handlings: Any = ()) -> None:
        if self.fails:
            raise RuntimeError("the alert store is down")
        self.saved.append((alert, list(handlings)))


class _Owners:
    """`PrincipalResolver.resolve_for_owner`: each owner resolved afresh, `None` for one gone."""

    async def resolve_for_owner(self, owner_id: str) -> Principal | None:
        return PEOPLE.get(owner_id)


LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")


def _deps(run: SimpleNamespace, alerts: _Alerts, **over: Any) -> Any:
    held = {"board_items": run.world.items, "datasets": run.world.datasets,
            "graph": run.world.graph, "ontology": ONTOLOGY, "principal_resolver": _Owners(),
            "alerts_store": alerts, "audit": run.world.audit,
            "investigations": run.world.cases}  # fmt: skip
    return SimpleNamespace(**{**held, **over})


def _entry(*node_ids: str) -> ChangeStreamEntry:
    return ChangeStreamEntry(
        entry_id="e-1", source="ingest", node_ids=list(node_ids), edge_ids=[],
        investigation_id=K, recorded_at=datetime.now(UTC),
    )  # fmt: skip


async def _after_run(
    deps: Any, *node_ids: str, dataset: str | None = "src", loader: Principal = LOADER
) -> int:
    return await _run_drawn_watches_best_effort(
        deps, _entry(*node_ids), dataset_id=dataset, principal=loader, investigation_id=K,
        load_id="load-9",
    )  # fmt: skip


async def test_a_recipe_run_raises_the_drawn_watch_alert_into_the_queue(
    run: SimpleNamespace,
) -> None:
    """The loader is not the owner: Alice is resolved afresh and read as herself. The alert saved
    is hers, in her case, citing both, with both markings."""
    drawn = _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    alerts = _Alerts()
    await _after_run(_deps(run, alerts), alike)
    ((alert, handlings),) = alerts.saved
    assert alert.rule_id.startswith("drawn_watch:")
    assert (alert.owner_id, alert.investigation_id, alert.dataset_id) == ("alice", K, "src")
    assert alert.referent_node_ids == [drawn["element_id"], alike]
    assert len(handlings) == 2


async def test_a_run_without_the_drawn_watch_stores_or_a_dataset_raises_nothing(
    run: SimpleNamespace,
) -> None:
    _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    alerts = _Alerts()
    await _after_run(_deps(run, alerts, board_items=None), alike)
    await _after_run(_deps(run, alerts, datasets=None), alike)
    await _after_run(_deps(run, alerts, investigations=None), alike)
    await _after_run(_deps(run, alerts), alike, dataset=None)
    assert alerts.saved == [] and run.world.items.matches == {}
    # Nothing tried at all: no failure to audit either.
    assert [r for r in run.world.audit.records if r["action"] == "watch_evaluation_failed"] == []


async def test_a_failing_drawn_watch_run_is_audited_never_the_loads_failure(
    run: SimpleNamespace,
) -> None:
    _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    await _after_run(_deps(run, _Alerts(fails=True)), alike)  # does not raise
    (failed,) = [r for r in run.world.audit.records if r["action"] == "watch_evaluation_failed"]
    assert failed["resolved_query"] == {"load_id": "load-9", "drawn_watches": True,
                                        "error": "the alert store is down"}  # fmt: skip


async def test_a_recipe_run_runs_the_drawn_watches_on_the_dataset_it_loaded_into(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`run_recipe_as`, the one run path (the route, the scheduler and the seed), runs the drawn
    watches after the other watches, on the recipe's dataset, with what the load published."""
    import dataclasses
    from unittest.mock import MagicMock

    from services.api import recipe_run as run_module

    from adapters.media_objectstore.testing import InMemoryMediaStore
    from schemas.ingest import LoadReport

    seen: list[dict[str, Any]] = []

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    async def loaded(*args: Any, **kwargs: Any) -> LoadReport:
        return LoadReport(load_id="load-7", recipe_id="r", recipe_version=1, nodes_created=1)

    async def published(*args: Any, **kwargs: Any) -> ChangeStreamEntry:
        return _entry("p-new")

    async def drawn_run(deps: Any, entry: ChangeStreamEntry, **kwargs: Any) -> int:
        seen.append({"node_ids": entry.node_ids, **kwargs})
        return 2

    async def started(**kwargs: Any) -> str:
        return "run-1"

    monkeypatch.setattr(run_module, "run_published_recipe", loaded)
    monkeypatch.setattr(run_module, "_rule_gate", nothing)
    monkeypatch.setattr(
        run_module.resolution_trigger_module, "submit_post_ingest_resolution_jobs", nothing
    )
    monkeypatch.setattr(
        run_module, "ChangeStreamWriter", lambda valkey: SimpleNamespace(publish=published)
    )
    monkeypatch.setattr(run_module, "_evaluate_watches_best_effort", nothing)
    monkeypatch.setattr(run_module, "_run_drawn_watches_best_effort", drawn_run)
    monkeypatch.setattr(run_module, "resolve_source_handling", lambda recipe: None)
    runs = MagicMock()
    runs.start, runs.finish = started, nothing
    stand_ins: dict[str, Any] = {
        "recipe_runs": runs, "audit": SimpleNamespace(record=nothing),
        "media": InMemoryMediaStore(), "config": SimpleNamespace(post_ingest_resolution=False),
    }  # fmt: skip
    names = [f.name for f in dataclasses.fields(run_module.RecipeRunDeps)]
    deps = run_module.RecipeRunDeps(**{n: stand_ins.get(n, object()) for n in names})
    recipe = SimpleNamespace(recipe_id="r", version=1, pipeline=None, row_template=None,
                             dataset_id="src")  # fmt: skip
    report = await run_module.run_recipe_as(
        deps, principal=LOADER, recipe=recipe,  # type: ignore[arg-type]
        investigation_id=K, source_location="x.csv", trigger="manual",
    )  # fmt: skip
    assert len(seen) == 1, "the drawn watches were not run after the load"
    # L3.H1: the count the run gave back is the report's.
    assert report.drawn_watch_alerts == 2
    call = seen[0]
    assert (call["node_ids"], call["dataset_id"], call["investigation_id"]) == (["p-new"], "src", K)
    assert call["principal"] is LOADER and call["load_id"]


async def test_nothing_is_raised_for_an_owner_who_may_no_longer_open_the_case(
    run: SimpleNamespace,
) -> None:
    """Rule 3: removed from the case, Alice is read as nothing of it — no claim, no alert — though
    her account still resolves and the case still reads the dataset."""
    _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    run.world.cases.grants[K].pop("alice")
    assert await run.run.after_load("src", [alike]) == 0
    assert run.raised == [] and run.world.items.matches == {}
    run.world.cases.grants[K]["alice"] = AccessLevel.VIEWER  # any level is enough to be told
    assert await run.run.after_load("src", [alike]) == 1


async def test_a_watch_in_a_case_reading_a_composite_is_run_by_a_load_into_a_member(
    run: SimpleNamespace,
) -> None:
    """The watch is set on what the case chose, the composite; a load writes into a member."""
    run.world.datasets.add(
        Dataset(id="comp", name="Both", owning_unit="unit-1", created_by="eng", kind=COMPOSITE,
                members=["src"], created_at=datetime(2026, 11, 1, tzinfo=UTC))
    )  # fmt: skip
    run.world.datasets.cases[K] = ["comp"]
    _tall()
    assert [w.dataset_id for w in run.world.items.watches.values()] == ["comp"]
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    assert await run.run.after_load("src", [alike]) == 1
    assert run.raised[0].loaded.id == alike


async def test_a_match_whose_alert_could_not_be_saved_is_raised_by_the_next_load(
    run: SimpleNamespace,
) -> None:
    """The claim is given back when the save fails, so "one per match" never becomes none."""
    _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")
    alerts = _Alerts(fails=True)
    await _after_run(_deps(run, alerts), alike)
    assert run.world.items.matches == {}
    alerts.fails = False
    await _after_run(_deps(run, alerts), alike)
    assert len(alerts.saved) == 1
    await _after_run(_deps(run, alerts), alike)
    assert len(alerts.saved) == 1  # and claimed once raised


async def test_a_borrowed_layer_is_read_only_for_an_owner_holding_a_level_on_its_case() -> None:
    """`case_read_set` as `scope_to_case`: a case made from another before L3.2 reads the
    original's layer only for one who may open the original."""
    from services.api.datasets import InMemoryDatasetStore

    store = InMemoryDatasetStore()
    store.cases["copy"] = ["src"]
    original_layer = await store.ensure_layer("orig", unit="unit-1", created_by="alice")
    store.layer_reads["copy"] = original_layer
    allowed: set[tuple[str, str]] = {("alice", "orig")}

    async def holds(p: Principal, case: str) -> bool:
        return (p.id, case) in allowed

    assert original_layer in await case_read_set(store, "copy", PEOPLE["alice"], holds)
    assert original_layer not in await case_read_set(store, "copy", PEOPLE["bob"], holds)


async def test_a_drawn_item_re_marked_above_its_owner_raises_nothing_and_claims_nothing(
    run: SimpleNamespace,
) -> None:
    """Rule 3: the run reads the drawn item as its owner, through the adapter. Bob (OFFICIAL) drew
    it; once it is re-marked SECRET it is not his to see, so a load meeting it neither raises an
    alert nor spends the one alert per match."""
    drawn = _item(_board("bob"), who="bob", label="Tall", properties={"family_name": "Tall"})
    held = run.world.graph._graph_nodes[drawn["element_id"]]
    run.world.graph._graph_nodes[drawn["element_id"]] = held.model_copy(
        update={"handling": held.handling.model_copy(update={"classification": "SECRET"})}
    )
    alike = _load(run, "p-alike", family_name="Tall")
    alerts = _Alerts()
    await _after_run(_deps(run, alerts), alike)
    assert alerts.saved == [] and run.world.items.matches == {}


async def test_one_watchs_failure_never_skips_the_others(run: SimpleNamespace) -> None:
    """Two cases' watches on the same dataset: the first's save fails, the second is still raised,
    and the failure is raised once both have run (for the caller to audit)."""
    _tall()
    _item(_board("carol", B), who="carol", case=B, label="Tall", properties={"family_name": "Tall"})
    alike = _load(run, "p-alike", family_name="Tall")
    saved: list[str] = []

    async def raise_alert(match: DrawnWatchMatch) -> None:
        if not saved:  # whichever watch runs first
            saved.append("failed")
            raise RuntimeError("the alert store is down")
        saved.append(match.watch.case_id)

    run.run.raise_alert = raise_alert
    with pytest.raises(RuntimeError, match="the alert store is down"):
        await run.run.after_load("src", [alike])
    assert saved[0] == "failed" and len(saved) == 2 and saved[1] in (K, B)


async def test_a_claim_not_given_back_keeps_the_saves_own_failure(
    run: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tall()
    alike = _load(run, "p-alike", family_name="Tall", pnc_id="PNC-1")

    async def failing_save(match: DrawnWatchMatch) -> None:
        raise RuntimeError("the alert store is down")

    async def failing_release(watch: Any, loaded_id: str) -> None:
        raise ConnectionError("the board store is down too")

    run.run.raise_alert = failing_save
    monkeypatch.setattr(run.world.items, "release_match", failing_release)
    with pytest.raises(RuntimeError, match="the alert store is down"):
        await run.run.after_load("src", [alike])


async def test_a_runs_report_counts_only_the_drawn_watch_alerts_raised_for_its_own_principal(
    run: SimpleNamespace,
) -> None:
    """L3.H1 (ADR-146 decision 4): Alice's watch in K and Carol's in B both match. Alice's own run
    is told of hers alone; a loader who owns neither is told of none, though both are raised (a
    drawn watch's alert is its owner's alone: rules 3 and 7)."""
    _tall()
    _item(_board("carol", B), who="carol", case=B, label="Tall", properties={"family_name": "Tall"})
    alike = _load(run, "p-alike", family_name="Tall")
    alerts = _Alerts()
    assert await _after_run(_deps(run, alerts), alike, loader=PEOPLE["alice"]) == 1
    assert len(alerts.saved) == 2
    newer = _load(run, "p-newer", family_name="Tall")
    assert await _after_run(_deps(run, alerts), newer) == 0  # LOADER owns no watch
    assert len(alerts.saved) == 4
    failing = _Alerts(fails=True)
    assert await _after_run(_deps(run, failing), _load(run, "p-x", family_name="Tall")) == 0


def test_the_routes_view_says_the_count_and_a_withheld_one_says_none() -> None:
    """The route answers the report as a view (`report_view`): the count is carried; where the
    loader may not view every marking the load wrote, every count is withheld, this one too."""
    from services.api.load_records import report_view

    from ontology.handling import load_uk_le_scheme
    from schemas.ingest import LoadReport

    scheme = load_uk_le_scheme()
    report = LoadReport(load_id="l", recipe_id="r", recipe_version=1, drawn_watch_alerts=3)
    assert report_view(report, PEOPLE["alice"], scheme).drawn_watch_alerts == 3
    marking = {"classification": "SECRET", "handling_code": "P", "originator": "u",
               "owning_unit": "u"}  # fmt: skip
    secret = LoadReport.model_validate({**report.model_dump(), "markings": [marking]})
    held = report_view(secret, PEOPLE["bob"], scheme)
    assert held.withheld and held.drawn_watch_alerts == 0
