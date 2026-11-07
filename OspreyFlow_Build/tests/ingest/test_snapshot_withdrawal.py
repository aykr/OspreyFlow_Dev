"""ADR-110 Amendment 8 point 3, as Amendment 15 narrows it: a full snapshot with *withdraw* takes
back exactly a dropped row's links and their events, never a node, and nothing another row or
another load still holds; and what the run says is the same whatever the loader may not read.

The graph is `MergingGraph` (the real store's link merge, and now its withdrawal and restore); the
ledger is `WithdrawalLedger` below, which answers as `RecipeRunStore` does
(`tests/services/api/test_row_key_withdrawal_ledger.py` holds the real one to the same answers).
The live end to end, events, metering and revert included, is
`tests/services/api/test_source_refresh_snapshot_live.py`. What a mistake would do, and the case
that catches it:

- a dropped row's link left in place, or a kept row's taken with it
  (`test_a_second_snapshot_missing_one_row_withdraws_exactly_that_rows_links`);
- a node withdrawn at all, whoever else names it or rests a link on it (Amendment 15, rule 3's
  hidden degree; `test_a_dropped_rows_nodes_stay_whatever_names_them`);
- a link a kept row of the same pipeline also wrote withdrawn, or kept silently
  (`test_a_link_a_kept_row_also_wrote_stays_and_is_counted`);
- a link another pipeline's kept row also wrote counted, so the figure tells of a row the loader
  may not read (`test_a_link_another_pipelines_row_holds_stays_and_is_not_counted`);
- a key kept before rows recorded what they wrote taken for one that wrote nothing
  (`test_a_dropped_key_with_no_record_is_left_in_place_and_counted`);
- *keep* withdrawing anything (`test_keep_withdraws_nothing`);
- a row that comes back not linked again (`test_a_row_that_comes_back_is_loaded_again`);
- a count of kept links telling the loader of a link they may not read (rule 3,
  `test_a_kept_link_the_loader_may_not_read_is_not_counted`)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from contextlib import asynccontextmanager
from typing import Any

import pytest
from services.api.recipe_runs import KeptRow
from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.ingest import LoadReport, Recipe
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_elements import _key
from tests.ingest.test_row_keys import CASE, LOADER, ONTOLOGY, SCHEME, _recipe, _row

A, B, C = _row("SYN-1", "SYN-2", 1), _row("SYN-3", "SYN-4", 2), _row("SYN-5", "SYN-6", 3)


class WithdrawalLedger:
    """The ledger's row keys, records and withdrawn keys as `RecipeRunStore` keeps them, behind the
    `LoadSink` a run is given: the record and its keys land together after the graph's commit; a
    withdrawn key moves aside with the refresh's load; the questions are answered over everything
    kept, of every recipe and case."""

    def __init__(self) -> None:
        #: (recipe, case, key) -> (load, node ids or None, edge ids or None)
        self.kept_rows: dict[tuple[str, str, str], tuple[str, Any, Any]] = {}
        self.withdrawn: dict[tuple[str, str, str], tuple[str, Any, Any, str]] = {}
        self.records: list[LoadReport] = []

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
            elements = report.kept_row_elements.get(key)
            self.kept_rows.setdefault(
                (report.recipe_id, CASE, key),
                (
                    report.load_id,
                    None if elements is None else tuple(elements.node_ids),
                    None if elements is None else tuple(elements.edge_ids),
                ),
            )
        for key in report.withdrawn_row_keys:
            load, nodes, edges = self.kept_rows.pop((report.recipe_id, CASE, key))
            self.withdrawn[(report.recipe_id, CASE, key)] = (load, nodes, edges, report.load_id)

    async def geometries(self, load_id: str, refs: Sequence[str]) -> None:
        return None

    async def rule_writes(self, load_id: str, **_: Any) -> None:
        return None

    async def uncovered(self, load_id: str) -> None:
        return None

    # -- what a withdrawal asks ------------------------------------------------------------------
    async def dropped_row_keys(
        self, recipe_id: str, case: str, *, present: Collection[str]
    ) -> list[KeptRow]:
        return [
            KeptRow(row_key=k[2], load_id=v[0], node_ids=v[1], edge_ids=v[2])
            for k, v in sorted(self.kept_rows.items())
            if k[:2] == (recipe_id, case) and k[2] not in present
        ]

    async def elements_kept_by_other_rows(
        self,
        node_ids: Sequence[str],
        edge_ids: Sequence[str],
        *,
        recipe_id: str,
        case: str,
        excluding: Sequence[str],
        only_this_pipeline: bool = False,
    ) -> tuple[set[str], set[str]]:
        nodes: set[str] = set()
        edges: set[str] = set()
        for (recipe, kept_case, key), (_, kept_nodes, kept_edges) in self.kept_rows.items():
            if (recipe, kept_case) == (recipe_id, case) and key in set(excluding):
                continue
            if only_this_pipeline and (recipe, kept_case) != (recipe_id, case):
                continue
            nodes |= set(kept_nodes or ()) & set(node_ids)
            edges |= set(kept_edges or ()) & set(edge_ids)
        return nodes, edges

    async def elements_in_other_records(
        self, node_ids: Sequence[str], edge_ids: Sequence[str], *, excluding_loads: Sequence[str]
    ) -> tuple[set[str], set[str]]:
        nodes: set[str] = set()
        edges: set[str] = set()
        for record in self.records:
            if record.load_id in set(excluding_loads):
                continue
            nodes |= {*record.created_node_ids, *record.merged_node_ids} & set(node_ids)
            edges |= {*record.touched_edge_ids} & set(edge_ids)
        return nodes, edges


async def _snapshot(
    graph: MergingGraph,
    ledger: WithdrawalLedger,
    rows: list[dict[str, str]],
    load_id: str,
    *,
    withdraw: bool = True,
    recipe: Recipe | None = None,
) -> LoadReport:
    report, _, _ = await load_with_rules(
        recipe or _recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id,
        investigation_scope=CASE,
        source="private_cash.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=ledger,  # type: ignore[arg-type]
        withdraw_dropped=withdraw,
    )
    assert report.rejections == [], report.rejections
    return report


def _live_values(graph: MergingGraph) -> set[str]:
    return {str(n.properties["value_normalised"]) for n in graph.live_nodes.values()}


def _live_links(graph: MergingGraph) -> set[str]:
    return {e.id for e in graph.committed_edges if e.id not in graph.reverted}


async def test_a_second_snapshot_missing_one_row_withdraws_exactly_that_rows_links() -> None:
    graph, ledger = MergingGraph(ONTOLOGY), WithdrawalLedger()
    first = await _snapshot(graph, ledger, [A, B, C], "load-1")
    b_elements = first.kept_row_elements[_key(B)]

    second = await _snapshot(graph, ledger, [A, C], "load-2")

    assert second.withdrawn_node_ids == [], "Amendment 15: never a node"
    assert second.withdrawn_edge_ids == b_elements.edge_ids
    assert second.withdrawn_row_keys == [_key(B)]
    assert (second.rows_withdrawn, second.links_kept_an_occurrence) == (1, 0)
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5", "SYN-6"}
    assert len(_live_links(graph)) == 2
    assert graph.withdrawn == {i: "load-2" for i in b_elements.edge_ids}
    # The key is withdrawn, not kept: a third snapshot does not drop it again.
    assert (CASE, _key(B)) not in {(k[1], k[2]) for k in ledger.kept_rows}
    third = await _snapshot(graph, ledger, [A, C], "load-3")
    assert third.withdrawn_row_keys == [] and third.rows_withdrawn == 0


def _payers_only() -> Recipe:
    """Another pipeline, with a key, whose rows match a payer and write no link: a node it names
    has no live link of its, so only its kept row's record says it is held."""
    document = _recipe().model_dump(by_alias=True)
    document["id"] = "payers-only"
    template = document["row_template"]
    template["entities"] = [e for e in template["entities"] if e["ref"] == "from"]
    template["edges"] = []
    return Recipe.model_validate(document)


@pytest.mark.parametrize(
    "named_by", ["nothing", "a kept row", "another pipelines kept row", "the snapshots own new row",
                 "a keyless loads live link"],
)  # fmt: skip
async def test_a_dropped_rows_nodes_stay_whatever_names_them(named_by: str) -> None:
    """Amendment 15: whether a node may go depends on rows and links the loader may not read, so
    none goes, and the run reads the same in every case."""
    graph, ledger = MergingGraph(ONTOLOGY), WithdrawalLedger()
    first_rows = [A, B, _row("SYN-1", "SYN-7", 4)] if named_by == "a kept row" else [A, B]
    await _snapshot(graph, ledger, first_rows, "load-1")
    if named_by == "another pipelines kept row":
        await _snapshot(graph, ledger, [A], "load-p", withdraw=False, recipe=_payers_only())
    if named_by == "a keyless loads live link":
        keyless = _recipe(deduplicate=False).model_copy(update={"id": "other-pipeline"})
        await _snapshot(graph, ledger, [_row("SYN-2", "SYN-8", 6)], "load-x", withdraw=False,
                        recipe=keyless)  # fmt: skip
    snapshot = [
        B,
        *([_row("SYN-1", "SYN-9", 7)] if named_by == "the snapshots own new row" else []),
    ]
    if named_by == "a kept row":
        snapshot.append(_row("SYN-1", "SYN-7", 4))

    second = await _snapshot(graph, ledger, snapshot, "load-2")

    assert second.withdrawn_node_ids == []
    assert {"SYN-1", "SYN-2"} <= _live_values(graph)
    assert (second.rows_withdrawn, second.links_kept_an_occurrence) == (1, 0)


async def test_a_link_a_kept_row_also_wrote_stays_and_is_counted() -> None:
    graph, ledger = MergingGraph(ONTOLOGY), WithdrawalLedger()
    again = _row("SYN-1", "SYN-2", 5)  # the same pair as A: one link, two occurrences
    await _snapshot(graph, ledger, [A, again], "load-1")
    links = _live_links(graph)

    second = await _snapshot(graph, ledger, [again], "load-2")

    assert second.withdrawn_node_ids == [] and second.withdrawn_edge_ids == []
    assert (second.rows_withdrawn, second.links_kept_an_occurrence) == (1, 1)
    assert _live_links(graph) == links
    assert "1 link kept an occurrence from a dropped row" in second.refresh_notes


async def test_a_link_another_pipelines_row_holds_stays_and_is_not_counted() -> None:
    """Amendment 15: another pipeline's kept row keeps the link silently. The loader may read the
    link, but not necessarily the row, so the count would tell of it."""
    graph, ledger = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, ledger, [A, B], "load-1")
    other = _recipe().model_copy(update={"id": "another-pipeline"})
    await _snapshot(graph, ledger, [A], "load-o", withdraw=False, recipe=other)
    links = _live_links(graph)

    second = await _snapshot(graph, ledger, [B], "load-2")

    assert second.withdrawn_edge_ids == [], "the other pipeline's row holds A's link"
    assert _live_links(graph) == links
    assert (second.rows_withdrawn, second.links_kept_an_occurrence) == (1, 0)
    assert not any("kept an occurrence" in note for note in second.refresh_notes)


async def test_a_dropped_key_with_no_record_is_left_in_place_and_counted() -> None:
    graph, ledger = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, ledger, [A, B], "load-1")
    # As a key kept before Amendment 8: its record unknown.
    load, _, _ = ledger.kept_rows[("private-cash", CASE, _key(A))]
    ledger.kept_rows[("private-cash", CASE, _key(A))] = (load, None, None)

    second = await _snapshot(graph, ledger, [B], "load-2")

    assert second.withdrawn_node_ids == [] and second.withdrawn_row_keys == []
    assert (second.rows_withdrawn, second.rows_left_in_place) == (0, 1)
    assert (
        "1 dropped row was loaded before rows recorded what they wrote, and was left in place"
        in second.refresh_notes
    )
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}


async def test_keep_withdraws_nothing() -> None:
    graph, ledger = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, ledger, [A, B], "load-1", withdraw=False)
    second = await _snapshot(graph, ledger, [B], "load-2", withdraw=False)
    assert second.withdrawn_row_keys == [] and graph.withdrawn == {}
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}


async def test_a_row_that_comes_back_is_loaded_again() -> None:
    graph, ledger = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, ledger, [A, B], "load-1")
    await _snapshot(graph, ledger, [B], "load-2")
    withdrawn = set(graph.withdrawn)

    back = await _snapshot(graph, ledger, [A, B], "load-3")

    assert back.rows_already_loaded == 1 and back.kept_row_keys == [_key(A)]
    # Its nodes never left (Amendment 15); its link, withdrawn, is written again, not matched.
    assert back.nodes_created == 0
    assert back.created_edge_ids and not set(back.created_edge_ids) & withdrawn
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}
    assert len(_live_links(graph)) == 2


class BlindToEdges(MergingGraph):
    """The loader may read no link (rule 3's case): `get_edges` answers nothing."""

    async def get_edges(self, edge_ids: Sequence[str], principal: Any) -> list[Any]:
        return []


async def test_a_kept_link_the_loader_may_not_read_is_not_counted() -> None:
    graph, ledger = BlindToEdges(ONTOLOGY), WithdrawalLedger()
    again = _row("SYN-1", "SYN-2", 5)
    await _snapshot(graph, ledger, [A, again], "load-1")
    second = await _snapshot(graph, ledger, [again], "load-2")
    assert second.links_kept_an_occurrence == 0
    assert not any("kept an occurrence" in note for note in second.refresh_notes)
    assert second.withdrawn_edge_ids == [], "still kept: only the count is withheld"


# --- the refresh's revert (ADR-110 Amendment 8 point 5) ---------------------------------------
#
# What a mistake would do, and the case that catches it:
# - a revert of the refresh that leaves the dropped row withdrawn, its key aside or its events out
#   (`test_reverting_the_refresh_restores_the_dropped_row_its_key_and_its_events`);
# - a revert that restores a row a later load has kept again, so it is held twice
#   (`test_the_refreshs_revert_is_refused_while_a_row_it_withdrew_is_kept_again`);
# - a revert of the load that created the row leaving it for the refresh's revert to bring back
#   (`test_after_the_creating_load_is_reverted_the_refreshs_revert_restores_nothing`).

from datetime import UTC, datetime  # noqa: E402

from services.ingest.load_ledger import load_record_from_report  # noqa: E402
from services.ingest.load_revert import RevertDeps, RevertRefused, revert  # noqa: E402

from tests.ingest.test_revert_load import (  # noqa: E402
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
        gone_aside = [k for k, v in self.keys.withdrawn.items() if v[0] in set(load_ids)]
        for k in gone:
            del self.keys.kept_rows[k]
        for k in gone_aside:
            del self.keys.withdrawn[k]
        return len(gone) + len(gone_aside)

    async def withdrawn_keys_kept_again(self, load_id: str) -> int:
        return sum(
            1
            for k, v in self.keys.withdrawn.items()
            if v[3] == load_id and k in self.keys.kept_rows
        )

    async def restore_withdrawn_row_keys(self, load_id: str) -> int:
        back = [
            k for k, v in self.keys.withdrawn.items()
            if v[3] == load_id and k not in self.keys.kept_rows
        ]  # fmt: skip
        for k in back:
            load, nodes, edges, _ = self.keys.withdrawn.pop(k)
            self.keys.kept_rows[k] = (load, nodes, edges)
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


async def test_reverting_the_refresh_restores_the_dropped_row_its_key_and_its_events() -> None:
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, keys, [A, B], "load-1")
    new_row = _row("SYN-1", "SYN-9", 7)
    second = await _snapshot(graph, keys, [B, new_row], "load-2")
    assert second.withdrawn_edge_ids and second.withdrawn_node_ids == []
    assert len(_live_links(graph)) == 2, "B's and the new row's: A's is withdrawn"

    steps = Steps()
    deps = _deps(graph, RefreshLedger(keys), steps)
    await revert("load-2", reverted_by="operator-1", deps=deps, now=NOW)

    assert graph.withdrawn == {}
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}, "SYN-9 was the refresh's"
    assert {k[2] for k in keys.kept_rows} == {_key(A), _key(B)} and keys.withdrawn == {}
    assert deps.analytics.restored == ["load-2"]  # type: ignore[attr-defined]
    # Its events are put back before its own are retracted, so neither step undoes the other.
    order = [entry[0] for entry in steps.log if entry[0] in {"events_restored", "events"}]
    assert order == ["events_restored", "events"]


async def test_the_refreshs_revert_is_refused_while_a_row_it_withdrew_is_kept_again() -> None:
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
    # Reverting the later load first lets it through.
    ledger = RefreshLedger(keys)
    await revert("load-3", reverted_by="operator-1", deps=_deps(graph, ledger, Steps()), now=NOW)
    await revert("load-2", reverted_by="operator-1", deps=_deps(graph, ledger, Steps()), now=NOW)
    assert _live_values(graph) == {"SYN-1", "SYN-2", "SYN-3", "SYN-4"}


async def test_after_the_creating_load_is_reverted_the_refreshs_revert_restores_nothing() -> None:
    graph, keys = MergingGraph(ONTOLOGY), WithdrawalLedger()
    await _snapshot(graph, keys, [A, B], "load-1")
    await _snapshot(graph, keys, [B], "load-2")
    ledger = RefreshLedger(keys)

    await revert("load-1", reverted_by="operator-1", deps=_deps(graph, ledger, Steps()), now=NOW)
    await revert("load-2", reverted_by="operator-1", deps=_deps(graph, ledger, Steps()), now=NOW)

    assert _live_values(graph) == set()
    assert keys.kept_rows == {} and keys.withdrawn == {}
