"""ADR-110 Amendment 8 point 3, as Amendment 15 (the owner's ruling "Only the rows' events")
narrows it: a full snapshot with *withdraw* takes back only a dropped row's own events, by the ids
its key records. It never touches the graph: a dropped row's nodes and links stay until its load is
reverted. And what the run says is the same whatever other rows, pipelines or cases hold.

The graph is `MergingGraph`; the ledger is `WithdrawalLedger` below, which answers as
`RecipeRunStore` does (`tests/services/api/test_row_key_withdrawal_ledger.py` holds the real one to
the same answers); the events go through `studio_publish.withdraw_dropped_rows_events`, the step
`run_published_recipe` takes after the commit, into `Events`, which sets aside by id as
`withdraw_events_by_id` does (the analytics conformance suite holds both adapters to it). The live
end to end is `tests/services/api/test_snapshot_withdrawal_tells_nothing_live.py` and
`test_source_refresh_snapshot_live.py`. What a mistake would do, and the case that catches it:

- a dropped row's events left, or a kept row's taken with them, or any graph element touched
  (`test_a_second_snapshot_missing_one_row_withdraws_only_that_rows_events`);
- another row's event on the same link taken, or the run's words moving, with whoever else wrote
  that link: the same pipeline, another, or another case (rule 3;
  `test_a_dropped_rows_withdrawal_is_the_same_whoever_else_wrote_its_link`);
- a key whose record names no events taken as one that wrote none, or its events taken by link
  (`test_a_dropped_key_with_no_event_record_is_left_in_place_events_too`);
- *keep* withdrawing anything (`test_keep_withdraws_nothing`);
- a row that comes back creating a node or a link again
  (`test_a_row_that_comes_back_is_kept_again_and_creates_nothing`)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from contextlib import asynccontextmanager
from typing import Any

import pytest
from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.analytics import EventRecord
from schemas.ingest import LoadReport, Recipe, stored_digest
from services.api.recipe_runs import KeptRow
from services.api.studio_publish import load_with_rules, withdraw_dropped_rows_events

from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_elements import _key
from tests.ingest.test_row_keys import CASE, LOADER, ONTOLOGY, SCHEME, _recipe, _row

A, B, C = (
    _row("SYN-1", "SYN-2", 1),
    _row("SYN-3", "SYN-4", 2),
    _row("SYN-5", "SYN-6", 3),
)
OTHER_CASE = "case-other"


class WithdrawalLedger:
    """The ledger's row keys, records and withdrawn keys as `RecipeRunStore` keeps them, behind the
    `LoadSink` a run is given: the record and its keys land together after the graph's commit; a
    withdrawn key moves aside with the refresh's load, its event ids with it."""

    def __init__(self) -> None:
        #: (recipe, case, key) -> (load, node ids, edge ids, event ids), each None if unrecorded
        self.kept_rows: dict[tuple[str, str, str], tuple[str, Any, Any, Any]] = {}
        self.withdrawn: dict[tuple[str, str, str], tuple[str, Any, Any, Any, str]] = {}
        self.records: list[LoadReport] = []
        self.case = CASE

    # -- what `load_with_rules` asks of its sink ------------------------------------------------
    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        return {k for k in keys if (recipe_id, case, k) in self.kept_rows}

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        loads = {v[0] for k, v in self.kept_rows.items() if k[:2] == (recipe_id, case)}
        loads |= {v[0] for k, v in self.withdrawn.items() if k[:2] == (recipe_id, case)}
        from services.ingest.engine import recipe_fingerprint

        return {recipe_fingerprint(_recipe()) or "": len(loads)} if loads else {}

    def hold_row_keys(self, recipe_id: str, case: str) -> Any:
        @asynccontextmanager
        async def unheld() -> Any:
            yield

        return unheld()

    async def committed(self, report: LoadReport, *, source: str) -> None:
        self.records.append(report)
        for key in report.kept_row_keys:
            e = report.kept_row_elements.get(key)
            self.kept_rows.setdefault(
                (report.recipe_id, self.case, key),
                (report.load_id, *((None,) * 3 if e is None else
                                   (tuple(e.node_ids), tuple(e.edge_ids), tuple(e.event_ids)))),
            )  # fmt: skip
        for key in report.withdrawn_row_keys:
            at = (report.recipe_id, self.case, key)
            if at in self.withdrawn or at not in self.kept_rows:
                # As the real ledger's move does (`add_record`, and
                # `test_the_unit_files_fake_moves_keys_as_the_ledger_does`): a key already withdrawn
                # is never moved again and stays kept, and a key never kept moves nothing.
                continue
            kept = self.kept_rows.pop(at)
            self.withdrawn[(report.recipe_id, self.case, key)] = (*kept, report.load_id)

    async def geometries(self, load_id: str, refs: Sequence[str]) -> None:
        return None

    async def rule_writes(self, load_id: str, **_: Any) -> None:
        return None

    async def uncovered(self, load_id: str) -> None:
        return None

    # -- what a withdrawal asks: this pipeline's own keys in this case, and nothing else ---------
    async def dropped_row_keys(
        self, recipe_id: str, case: str, *, present: Collection[str]
    ) -> list[KeptRow]:
        return [
            KeptRow(
                row_key=k[2],
                load_id=v[0],
                node_ids=v[1],
                edge_ids=v[2],
                event_ids=v[3],
                withdrawn_before=k in self.withdrawn,
            )
            for k, v in sorted(self.kept_rows.items())
            if k[:2] == (recipe_id, case) and k[2] not in present
        ]

    async def withdrawn_row_links(
        self, recipe_id: str, case: str, keys: Sequence[str]
    ) -> dict[str, tuple[str, ...]]:
        """As the ledger: the withdrawn keys of the recipe and case among `keys`, with the links
        each one's record holds (none for a key recorded before rows recorded them)."""
        return {
            k[2]: tuple(v[2] or ())
            for k, v in self.withdrawn.items()
            if k[:2] == (recipe_id, case) and k[2] in set(keys)
        }

    async def withdrawn_row_keys_among(
        self, recipe_id: str, case: str, keys: Sequence[str]
    ) -> set[str]:
        return {
            k[2]
            for k in self.withdrawn
            if k[:2] == (recipe_id, case) and k[2] in set(keys)
        }

    async def withdrawn_event_ids(self, load_id: str) -> list[str]:
        return sorted(
            {e for v in self.withdrawn.values() if v[4] == load_id for e in v[3] or ()}
        )


class Events:
    """The analytics store's events as `withdraw_events_by_id` and `restore_withdrawn_events` keep
    them: set aside by id, never by link."""

    def __init__(self) -> None:
        self.live: dict[str, EventRecord] = {}
        self.aside: dict[str, tuple[EventRecord, str]] = {}

    async def withdraw_events_by_id(
        self, event_ids: Sequence[str], load_id: str
    ) -> int:
        moved = [i for i in dict.fromkeys(event_ids) if i in self.live]
        for i in moved:
            self.aside[i] = (self.live.pop(i), load_id)
        return len(moved)

    def on_links(self) -> list[tuple[str, str]]:
        """Each live event as (its link, its time): what a timeline reader sees, without ids."""
        return sorted(
            (e.edge_id, e.occurred_at.isoformat()) for e in self.live.values()
        )


async def _snapshot(
    graph: MergingGraph,
    ledger: WithdrawalLedger,
    rows: list[dict[str, str]],
    load_id: str,
    *,
    withdraw: bool = True,
    recipe: Recipe | None = None,
    events: Events | None = None,
    case: str = CASE,
) -> LoadReport:
    ledger.case = case
    report, written, _ = await load_with_rules(
        recipe or _recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope=case,
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=ledger,  # type: ignore[arg-type]
        withdraw_dropped=withdraw,
    )
    assert report.rejections == [], report.rejections
    if events is not None:
        # As `run_published_recipe`: the dropped rows' events go first, then the run's own land.
        await withdraw_dropped_rows_events(report, ledger, events)  # type: ignore[arg-type]
        events.live.update({e.event_id: e for e in written})
    ledger.case = CASE
    return report


def _live_values(graph: MergingGraph) -> set[str]:
    return {str(n.properties["value_normalised"]) for n in graph.live_nodes.values()}


def _live_links(graph: MergingGraph) -> set[str]:
    return {e.id for e in graph.committed_edges if e.id not in graph.reverted}


async def test_a_second_snapshot_missing_one_row_withdraws_only_that_rows_events() -> (
    None
):
    graph, ledger, events = MergingGraph(ONTOLOGY), WithdrawalLedger(), Events()
    first = await _snapshot(graph, ledger, [A, B, C], "load-1", events=events)
    b_events = set(first.kept_row_elements[_key(B)].event_ids)
    assert len(b_events) == 1 and len(events.live) == 3
    nodes, links = _live_values(graph), _live_links(graph)

    second = await _snapshot(graph, ledger, [A, C], "load-2", events=events)

    assert second.withdrawn_row_keys == [_key(B)] and second.rows_withdrawn == 1
    assert (second.withdrawn_node_ids, second.withdrawn_edge_ids) == ([], []), (
        "never the graph"
    )
    assert (_live_values(graph), _live_links(graph), graph.withdrawn) == (
        nodes,
        links,
        {},
    )
    assert set(events.aside) == b_events and {v[1] for v in events.aside.values()} == {
        "load-2"
    }
    assert len(events.live) == 2
    assert second.links_kept_an_occurrence == 0 and second.refresh_notes == []
    # The key is withdrawn, not kept: a third snapshot does not drop it again.
    assert (CASE, _key(B)) not in {(k[1], k[2]) for k in ledger.kept_rows}
    third = await _snapshot(graph, ledger, [A, C], "load-3", events=events)
    assert third.withdrawn_row_keys == [] and len(events.aside) == 1


def _what_the_loader_is_told(report: LoadReport) -> tuple[Any, ...]:
    return (
        report.rows_withdrawn, report.rows_left_in_place, report.links_kept_an_occurrence,
        report.refresh_notes, report.withdrawn_node_ids, report.withdrawn_edge_ids,
        report.nodes_created, report.edges_created,
    )  # fmt: skip


@pytest.mark.parametrize(
    "also_written_by", ["nobody", "a kept row of this pipeline", "another pipelines kept row",
                        "another cases kept row"],
)  # fmt: skip
async def test_a_dropped_rows_withdrawal_is_the_same_whoever_else_wrote_its_link(
    also_written_by: str,
) -> None:
    """Amendment 15, rule 3: the dropped row A takes back its own event alone. Another row's event
    on A's link stays, whoever wrote it; the graph is untouched; and the run tells the loader the
    same as when nobody else wrote the link."""
    graph, ledger, events = MergingGraph(ONTOLOGY), WithdrawalLedger(), Events()
    again = _row("SYN-1", "SYN-2", 5)  # A's pair: A's link, another occurrence
    own_rows = (
        [A, B, again] if also_written_by == "a kept row of this pipeline" else [A, B]
    )
    first = await _snapshot(graph, ledger, own_rows, "load-1", events=events)
    if also_written_by == "another pipelines kept row":
        other = _recipe().model_copy(update={"id": "another-pipeline"})
        await _snapshot(graph, ledger, [again], "load-o", withdraw=False, recipe=other,
                        events=events)  # fmt: skip
    if also_written_by == "another cases kept row":
        await _snapshot(graph, ledger, [again], "load-c", withdraw=False, events=events,
                        case=OTHER_CASE)  # fmt: skip
    a_events = set(first.kept_row_elements[_key(A)].event_ids)
    others = {i: e for i, e in events.live.items() if i not in a_events}
    nodes, links = _live_values(graph), _live_links(graph)

    snapshot = [B, again] if also_written_by == "a kept row of this pipeline" else [B]
    second = await _snapshot(graph, ledger, snapshot, "load-2", events=events)

    assert set(events.aside) == a_events
    assert events.live == others, "every other row's event stays, on A's link too"
    assert (_live_values(graph), _live_links(graph), graph.withdrawn) == (
        nodes,
        links,
        {},
    )
    assert _what_the_loader_is_told(second) == (1, 0, 0, [], [], [], 0, 0)


@pytest.mark.parametrize("recorded", ["nothing", "its nodes and links, not its events"])
async def test_a_dropped_key_with_no_event_record_is_left_in_place_events_too(
    recorded: str,
) -> None:
    """A key kept before rows recorded what they wrote (Amendment 8), or what they wrote but not
    their events (before Amendment 15), names no events: it is left kept, its events stay, and the
    run says so. Never a fallback to its links' events."""
    graph, ledger, events = MergingGraph(ONTOLOGY), WithdrawalLedger(), Events()
    await _snapshot(graph, ledger, [A, B], "load-1", events=events)
    load, nodes, edges, _ = ledger.kept_rows[("private-cash", CASE, _key(A))]
    unrecorded = (None, None) if recorded == "nothing" else (nodes, edges)
    ledger.kept_rows[("private-cash", CASE, _key(A))] = (load, *unrecorded, None)
    before = events.on_links()

    nodes, links = _live_values(graph), _live_links(graph)

    second = await _snapshot(graph, ledger, [B], "load-2", events=events)

    assert second.withdrawn_row_keys == [] and events.aside == {}
    assert (second.rows_withdrawn, second.rows_left_in_place) == (0, 1)
    words = "1 dropped row was loaded before rows recorded the events they wrote, and was left in "
    assert second.refresh_notes == [words + "place, its events too"]
    assert events.on_links() == before
    assert (_live_values(graph), _live_links(graph), graph.withdrawn) == (
        nodes,
        links,
        {},
    )
    assert ("private-cash", CASE, _key(A)) in ledger.kept_rows


async def test_keep_withdraws_nothing() -> None:
    graph, ledger, events = MergingGraph(ONTOLOGY), WithdrawalLedger(), Events()
    await _snapshot(graph, ledger, [A, B], "load-1", withdraw=False, events=events)
    second = await _snapshot(
        graph, ledger, [B], "load-2", withdraw=False, events=events
    )
    assert (
        second.withdrawn_row_keys == [] and graph.withdrawn == {} and events.aside == {}
    )
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}
    # A merge with no row coming back says nothing.
    again = await _snapshot(
        graph, ledger, [_row("SYN-3", "SYN-4", 8)], "load-3", withdraw=False
    )
    assert again.merged_edge_ids and again.refresh_notes == []


async def test_a_row_that_comes_back_is_kept_again_and_creates_nothing() -> None:
    """Its nodes and its link never left (Amendment 15), so the row matches them and merges into its
    link: no node or link is created, and its new event is the timeline's only one for it."""
    graph, ledger, events = MergingGraph(ONTOLOGY), WithdrawalLedger(), Events()
    first = await _snapshot(graph, ledger, [A, B], "load-1", events=events)
    await _snapshot(graph, ledger, [B], "load-2", events=events)
    links = _live_links(graph)
    (a_link,) = first.kept_row_elements[_key(A)].edge_ids
    as_it_was = await graph.read_link_state(a_link)

    back = await _snapshot(graph, ledger, [A, B], "load-3", events=events)

    assert back.rows_already_loaded == 1 and back.kept_row_keys == [_key(A)]
    assert (back.nodes_created, back.edges_created, back.created_edge_ids) == (0, 0, [])
    assert _live_links(graph) == links and graph.withdrawn == {}
    assert len(events.live) == 2, "B's, and A's new one; A's first stays set aside"
    # ADR-110 Amendment 16: the merge is A's own, kept as the link was before it, so the load
    # reverts; no words say otherwise.
    (kept,) = back.own_key_merges
    assert kept.model_copy(update={"left_digest": None}) == as_it_was
    left = await graph.read_link_state(a_link)
    assert left is not None and kept.left_digest == stored_digest(left.stored), "as the load left it"
    assert back.refresh_notes == []


# --- the refresh's revert (ADR-110 Amendment 8 point 5) ---------------------------------------
#
# What a mistake would do, and the case that catches it:
# - a revert of the refresh that leaves the dropped row's key aside or its events out
#   (`test_reverting_the_refresh_restores_the_dropped_rows_key_and_its_events`);
# - a refresh recorded before Amendment 15, with nodes and links withdrawn, not given them back
#   (`test_a_refresh_recorded_with_withdrawn_nodes_and_links_reverts_them_back`);
# - a revert that restores a row a later load has kept again, so it is held twice
#   (`test_the_refreshs_revert_is_refused_while_a_row_it_withdrew_is_kept_again`);
# - a revert of the load that created the row leaving it for the refresh's revert to bring back
#   (`test_after_the_creating_load_is_reverted_the_refreshs_revert_restores_nothing`).

from datetime import UTC, datetime

from services.ingest.load_ledger import load_record_from_report
from services.ingest.load_revert import RevertDeps, RevertRefused, revert

from tests.ingest.test_revert_load import (
    Alerts,
    Analytics,
    Audit,
    Held,
    Ledger,
    Steps,
    WorkingSets,
    no_caches,
)

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)


class RefreshLedger(Ledger):
    """`test_revert_load.Ledger` over the records `WithdrawalLedger` was given, with its keys: the
    release, the restore of withdrawn keys and the count of those kept again, as
    `RecipeRunStore` answers them (`test_row_key_withdrawal_ledger.py`)."""

    def __init__(self, keys: WithdrawalLedger) -> None:
        super().__init__(
            *(
                load_record_from_report(r, source="private_cash.csv", created_by="loader-1",
                                        started_at=NOW, now=NOW, investigation_id=CASE)
                for r in keys.records
            )
        )  # fmt: skip
        self.keys = keys

    async def release_row_keys(self, load_ids: Any) -> int:
        await super().release_row_keys(load_ids)
        gone = [k for k, v in self.keys.kept_rows.items() if v[0] in set(load_ids)]
        gone_aside = [
            k for k, v in self.keys.withdrawn.items() if v[0] in set(load_ids)
        ]
        for k in gone:
            del self.keys.kept_rows[k]
        for k in gone_aside:
            del self.keys.withdrawn[k]
        return len(gone) + len(gone_aside)

    async def withdrawn_keys_kept_again(self, load_id: str) -> int:
        return sum(
            1
            for k, v in self.keys.withdrawn.items()
            if v[4] == load_id and k in self.keys.kept_rows
        )

    async def restore_withdrawn_row_keys(self, load_id: str) -> int:
        back = [
            k for k, v in self.keys.withdrawn.items()
            if v[4] == load_id and k not in self.keys.kept_rows
        ]  # fmt: skip
        for k in back:
            load, nodes, edges, event_ids, _ = self.keys.withdrawn.pop(k)
            self.keys.kept_rows[k] = (load, nodes, edges, event_ids)
        return len(back)


class RefreshAnalytics(Analytics):
    """The analytics fake, with events set aside by a refresh and put back by its revert."""

    def __init__(self, steps: Steps) -> None:
        super().__init__(steps)
        self.restored: list[str] = []

    async def restore_withdrawn_events(self, load_id: str) -> int:
        self.steps.hit("events_restored", load_id)
        self.restored.append(load_id)
        return 0


def _deps(graph: MergingGraph, ledger: RefreshLedger, steps: Steps) -> RevertDeps:
    return RevertDeps(
        ledger=ledger,
        graph=graph,  # type: ignore[arg-type]
        analytics=RefreshAnalytics(steps),  # type: ignore[arg-type]
        held_rows=Held(steps),
        alerts=Alerts(steps),
        audit=Audit(steps),
        working_sets=WorkingSets(steps),
        invalidate_caches=no_caches,
    )


async def test_reverting_the_refresh_restores_the_dropped_rows_key_and_its_events() -> (
    None
):
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, keys, [A, B], "load-1")
    new_row = _row("SYN-1", "SYN-9", 7)
    second = await _snapshot(graph, keys, [B, new_row], "load-2")
    assert second.rows_withdrawn == 1 and (
        second.withdrawn_node_ids,
        second.withdrawn_edge_ids,
    ) == ([], [])
    assert len(_live_links(graph)) == 3, "A's stays, with B's and the new row's"

    steps = Steps()
    deps = _deps(graph, RefreshLedger(keys), steps)
    await revert("load-2", reverted_by="operator-1", deps=deps, now=NOW)

    assert graph.withdrawn == {} and len(_live_links(graph)) == 2
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}, (
        "SYN-9 was the refresh's"
    )
    assert {k[2] for k in keys.kept_rows} == {_key(A), _key(B)} and keys.withdrawn == {}
    assert deps.analytics.restored == ["load-2"]  # type: ignore[attr-defined]
    # Its events are put back before its own are retracted, so neither step undoes the other.
    order = [
        entry[0] for entry in steps.log if entry[0] in {"events_restored", "events"}
    ]
    assert order == ["events_restored", "events"]


async def test_the_refreshs_revert_is_refused_while_a_row_it_withdrew_is_kept_again() -> (
    None
):
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    await _snapshot(graph, keys, [A, B], "load-3")  # A comes back: loaded again
    live = _live_values(graph), set(graph.withdrawn)

    with pytest.raises(RevertRefused) as refused:
        await revert("load-2", reverted_by="operator-1",
                     deps=_deps(graph, RefreshLedger(keys), Steps()), now=NOW)  # fmt: skip

    (refusal,) = refused.value.refusals
    assert refusal.reason == "withdrawn_rows_loaded_again" and refusal.count == 1
    assert "1 row(s) it withdrew were loaded again by a later load" in refusal.words()
    assert (_live_values(graph), set(graph.withdrawn)) == live, "nothing changed"


async def test_a_returning_rows_load_reverts_and_puts_its_link_back_then_the_refresh_then_the_first() -> (
    None
):
    """ADR-110 Amendment 16 (the owner's option A): the returning row's merge into its own
    withdrawn key's link is the row's own. Its load reverts, putting the link back exactly as the
    refresh left it; then the refresh reverts, giving the row back to the first load; then the
    first load reverts, and nothing of either row is left. Before the amendment the three were
    each refused (ADR-127 decision 6)."""
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    first = await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    (a_link,) = first.kept_row_elements[_key(A)].edge_ids
    after_the_refresh = await graph.read_link_state(a_link)
    await _snapshot(graph, keys, [A, B], "load-3")
    assert await graph.read_link_state(a_link) != after_the_refresh
    ledger = RefreshLedger(keys)  # one ledger: each revert is recorded for the next

    reverted = await revert("load-3", reverted_by="operator-1",
                            deps=_deps(graph, ledger, Steps()), now=NOW)  # fmt: skip

    (load_3,) = reverted.reverted
    assert (load_3.load_id, load_3.links_put_back, load_3.links) == ("load-3", 1, 0)
    assert await graph.read_link_state(a_link) == after_the_refresh, "exactly as it was"
    assert (CASE, _key(A)) not in {k[1:] for k in keys.kept_rows}
    await revert("load-2", reverted_by="operator-1",
                 deps=_deps(graph, ledger, Steps()), now=NOW)  # fmt: skip
    assert {k[2] for k in keys.kept_rows} == {_key(A), _key(B)} and keys.withdrawn == {}
    await revert("load-1", reverted_by="operator-1",
                 deps=_deps(graph, ledger, Steps()), now=NOW)  # fmt: skip
    assert _live_values(graph) == set() and _live_links(graph) == set()


async def test_a_returning_rows_revert_is_refused_once_another_case_wrote_its_link() -> None:
    """ADR-110 Amendment 16, rule 3: another case's load of the same pair merged into the link
    after the row came back, so putting it back would take that write away. Refused, nothing
    changed, and the words name neither that load nor its case."""
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    await _snapshot(graph, keys, [A, B], "load-3")
    await _snapshot(graph, keys, [A], "their-load", case="their-case", withdraw=False)
    live = _live_values(graph), _live_links(graph)

    with pytest.raises(RevertRefused) as refused:
        await revert("load-3", reverted_by="operator-1",
                     deps=_deps(graph, RefreshLedger(keys), Steps()), now=NOW)  # fmt: skip

    (refusal,) = refused.value.refusals
    assert (refusal.reason, refusal.count) == ("own_link_written_since", 1)
    words = refusal.words()
    assert "1 link(s) a returning row of it merged into were written again since" in words
    assert "their" not in words, "no other load or case is named"
    assert (_live_values(graph), _live_links(graph)) == live, "nothing changed"


async def test_a_case_holding_the_put_back_link_drops_its_merged_copy_and_is_told() -> None:
    """ADR-110 Amendment 16: a case with the link on its canvas holds the merged copy. The revert
    takes it out of every working set (both passes), so the canvas keeps no stale copy and its next
    expand reads the restored link, and tells the change stream the link changed, for the case."""
    import dataclasses

    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    first = await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    await _snapshot(graph, keys, [A, B], "load-3")
    (a_link,) = first.kept_row_elements[_key(A)].edge_ids
    told: list[tuple[list[str], str | None]] = []

    async def links_changed(edge_ids: list[str], case: str | None) -> None:
        told.append((list(edge_ids), case))

    steps = Steps()
    deps = dataclasses.replace(_deps(graph, RefreshLedger(keys), steps), links_changed=links_changed)
    deps.working_sets.cases = {"a-canvas": {a_link}}  # type: ignore[attr-defined]

    await revert("load-3", reverted_by="operator-1", deps=deps, now=NOW)

    assert deps.working_sets.cases["a-canvas"] == set(), "no stale merged copy"  # type: ignore[attr-defined]
    removals = [s for s in steps.log if s[0] in ("working_sets", "working_sets_again")]
    assert [a_link in s[2].split(",") for s in removals] == [True, True]
    assert told == [([a_link], CASE)]


async def test_a_returning_rows_revert_is_refused_once_an_analyst_corrected_its_link() -> None:
    """ADR-110 Amendment 16: a correction (`superseded`) leaves the link's last load and revision
    alone, so only the whole stored record shows it was written since. Refused, nothing changed,
    and the corrected link is never brought back live beside its successor."""
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    first = await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    await _snapshot(graph, keys, [A, B], "load-3")
    (a_link,) = first.kept_row_elements[_key(A)].edge_ids
    graph.superseded.add(a_link)  # an analyst's correction, as `supersede_edge` marks it
    before = await graph.read_link_state(a_link)

    with pytest.raises(RevertRefused) as refused:
        await revert("load-3", reverted_by="operator-1",
                     deps=_deps(graph, RefreshLedger(keys), Steps()), now=NOW)  # fmt: skip

    assert [(r.reason, r.count) for r in refused.value.refusals] == [("own_link_written_since", 1)]
    assert await graph.read_link_state(a_link) == before and a_link in graph.superseded


async def test_a_merge_into_a_link_that_is_not_the_rows_own_still_refuses_the_revert() -> None:
    """ADR-127 decision 6 stands for every other merge: a new row on the dropped row's pair (not
    the dropped row coming back) merges into its link, and its load is refused as before."""
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    another_day = _row("SYN-1", "SYN-2", 9)  # A's pair, another row
    later = await _snapshot(graph, keys, [another_day, B], "load-3")
    assert later.own_key_merges == [] and later.merged_edge_ids

    with pytest.raises(RevertRefused) as refused:
        await revert("load-3", reverted_by="operator-1",
                     deps=_deps(graph, RefreshLedger(keys), Steps()), now=NOW)  # fmt: skip

    assert [r.reason for r in refused.value.refusals] == ["merged_links"]


async def test_after_the_creating_load_is_reverted_the_refreshs_revert_restores_nothing() -> (
    None
):
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    ledger = RefreshLedger(keys)

    await revert(
        "load-1", reverted_by="operator-1", deps=_deps(graph, ledger, Steps()), now=NOW
    )
    await revert(
        "load-2", reverted_by="operator-1", deps=_deps(graph, ledger, Steps()), now=NOW
    )

    assert _live_values(graph) == set()
    assert keys.kept_rows == {} and keys.withdrawn == {}


async def test_a_refresh_recorded_with_withdrawn_nodes_and_links_reverts_them_back() -> (
    None
):
    """A record written before Amendment 15 (under Amendment 8 point 3) may list withdrawn nodes and
    links: its revert puts them back, as the graph's `restore_withdrawn` of the load always has.
    The refresh is built as such a load was: its withdrawal marked in the graph, and in its record."""
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    first = await _snapshot(graph, keys, [A, B], "load-1")
    second = await _snapshot(graph, keys, [B], "load-2")
    a = first.kept_row_elements[_key(A)]
    tx = await graph.begin_transaction()
    await graph.withdraw_elements(a.node_ids, a.edge_ids, "load-2", tx)
    await graph.commit_transaction(tx)
    second.withdrawn_node_ids, second.withdrawn_edge_ids = (
        list(a.node_ids),
        list(a.edge_ids),
    )
    assert "SYN-1" not in _live_values(graph)

    await revert("load-2", reverted_by="operator-1",
                 deps=_deps(graph, RefreshLedger(keys), Steps()), now=NOW)  # fmt: skip

    assert graph.withdrawn == {} and len(_live_links(graph)) == 2
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}


async def test_a_row_dropped_after_coming_back_is_left_in_place_in_words() -> None:
    """Drop, come back, drop again: the second drop cannot move the key aside (the first
    withdrawal's entry stands, and neither revert can clear it under Amendment 15), so the row is
    left in place, its new event too, and the run says so. The fake skips a second move as the real
    ledger's guard does, so a planner that named the key would be seen here: in the report and the
    count, not in an error."""
    graph, ledger, events = MergingGraph(ONTOLOGY), WithdrawalLedger(), Events()
    await _snapshot(graph, ledger, [A, B], "load-1", events=events)
    await _snapshot(graph, ledger, [B], "load-2", events=events)
    await _snapshot(graph, ledger, [A, B], "load-3", events=events)
    before = events.on_links()

    again = await _snapshot(graph, ledger, [B], "load-4", events=events)

    assert (
        again.withdrawn_row_keys,
        again.rows_withdrawn,
        again.rows_left_in_place,
    ) == ([], 0, 1)
    assert (again.withdrawn_node_ids, again.withdrawn_edge_ids) == ([], []), (
        "never the graph"
    )
    assert events.on_links() == before
    words = "1 dropped row had come back after an earlier refresh withdrew it, and was left in "
    assert again.refresh_notes == [
        words
        + "place, its events too, until that refresh can be reverted (ADR-110 Amendment 15)"
    ]
