"""ADR-110 decision 6: the run ledger. Every run, manual or scheduled, is a row in `recipe_runs`
with its outcome, its counts and the failure in words; a slot that did not run (refused, blocked,
skipped, missed) is a row too, so the history says what happened to every slot.

Against the throwaway Postgres (`POSTGRES_PORT`). The rows' readers (Admin, the Studio, the Glass's
*Data feeds*) are their routes' to filter (decisions 8 and 9); this store keeps each row's source
handling so they can."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from services.api.alerts import AlertStore
from services.api.config import PostgresConfig
from services.api.held_rows import HeldRowStore
from services.api.recipe_runs import RecipeRunStore

from conduit_common.identity import new_id
from ontology.handling import load_uk_le_scheme
from schemas.domain import Alert, AlertMode, Handling, HeldRow
from schemas.ingest import LoadRecord, LoadReport, RejectionRecord

SOURCE = Handling(
    classification="OFFICIAL", handling_code="P", owning_unit="unit-1", originator="unit-1"
)
T0 = datetime(2026, 10, 13, 6, 0, tzinfo=UTC)


@pytest.fixture
async def runs() -> AsyncIterator[RecipeRunStore]:
    store = await RecipeRunStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


async def test_a_run_is_started_then_finished_with_its_counts(runs: RecipeRunStore) -> None:
    recipe = new_id()
    run_id = await runs.start(
        recipe_id=recipe, recipe_version=3, investigation_id="case-1", trigger="manual",
        slot=None, run_as="analyst-1", source=SOURCE, now=T0,
    )
    (running,) = await runs.for_recipe(recipe)
    assert running.outcome == "running" and running.finished_at is None
    report = LoadReport(
        load_id="load-1", recipe_id=recipe, recipe_version=3, rows_read=10, nodes_created=4,
        nodes_referenced=2, edges_created=5, rows_held=1,
        rejections=[RejectionRecord(row_index=7, reason="no date", sample="")],
    )
    await runs.finish(run_id, report=report, now=T0 + timedelta(seconds=9))
    (done,) = await runs.for_recipe(recipe)
    assert done.outcome == "succeeded"
    assert (done.rows_read, done.nodes_created, done.nodes_referenced, done.edges_created) == (
        10, 4, 2, 5,
    )
    assert (done.rows_rejected, done.rows_held, done.load_id) == (1, 1, "load-1")
    assert done.finished_at == T0 + timedelta(seconds=9)
    assert done.source == SOURCE and done.run_as == "analyst-1"


async def test_a_failed_run_keeps_the_failure_in_words(runs: RecipeRunStore) -> None:
    recipe = new_id()
    run_id = await runs.start(
        recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
        slot=T0, run_as="analyst-1", source=SOURCE, now=T0,
    )
    await runs.fail(run_id, failure="the source file is missing", now=T0)
    (row,) = await runs.for_recipe(recipe)
    assert (row.outcome, row.failure, row.slot) == ("failed", "the source file is missing", T0)


@pytest.mark.parametrize("outcome", ["refused", "blocked", "skipped", "missed"])
async def test_a_slot_that_did_not_run_is_a_row_too(runs: RecipeRunStore, outcome: str) -> None:
    recipe = new_id()
    await runs.record_not_run(
        recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
        slot=T0, run_as="analyst-1", source=SOURCE, outcome=outcome,  # type: ignore[arg-type]
        failure=f"{outcome} for a reason", now=T0,
    )
    (row,) = await runs.for_recipe(recipe)
    assert row.outcome == outcome and row.started_at == row.finished_at == T0
    assert row.failure == f"{outcome} for a reason" and row.rows_read is None


async def test_an_outcome_it_does_not_know_is_refused(runs: RecipeRunStore) -> None:
    with pytest.raises(ValueError, match="outcome"):
        await runs.record_not_run(
            recipe_id=new_id(), recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0, run_as="analyst-1", source=SOURCE, outcome="succeeded",  # type: ignore[arg-type]
            failure=None, now=T0,
        )


async def test_history_is_newest_first(runs: RecipeRunStore) -> None:
    recipe = new_id()
    for minutes in (0, 2, 1):
        await runs.record_not_run(
            recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0 + timedelta(minutes=minutes), run_as="a", source=SOURCE, outcome="missed",
            failure=None, now=T0 + timedelta(minutes=minutes),
        )
    assert [r.slot for r in await runs.for_recipe(recipe)] == [
        T0 + timedelta(minutes=m) for m in (2, 1, 0)
    ]


async def test_refusals_in_a_row_are_counted_and_a_success_resets_them(
    runs: RecipeRunStore,
) -> None:
    """Decision 3: three refused scheduled runs in a row pause the schedule."""
    recipe = new_id()

    async def refuse(minute: int) -> None:
        await runs.record_not_run(
            recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0 + timedelta(minutes=minute), run_as="a", source=SOURCE, outcome="refused",
            failure="owner revoked", now=T0 + timedelta(minutes=minute),
        )

    await refuse(0)
    await refuse(1)
    assert await runs.refusals_in_a_row(recipe) == 2
    ok = await runs.start(
        recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
        slot=T0 + timedelta(minutes=2), run_as="a", source=SOURCE, now=T0 + timedelta(minutes=2),
    )
    await runs.finish(
        ok, report=LoadReport(load_id="l", recipe_id=recipe, recipe_version=1),
        now=T0 + timedelta(minutes=2),
    )
    assert await runs.refusals_in_a_row(recipe) == 0
    await refuse(3)
    assert await runs.refusals_in_a_row(recipe) == 1


async def test_a_refusal_that_does_not_count_is_skipped_over_not_counted(
    runs: RecipeRunStore,
) -> None:
    """ADR-110 Amendment 3: an unreachable identity provider neither counts nor resets."""
    recipe = new_id()
    for minute, counts in enumerate([True, False, True, False]):
        await runs.record_not_run(
            recipe_id=recipe, recipe_version=1, investigation_id="case-1", trigger="schedule",
            slot=T0 + timedelta(minutes=minute), run_as="a", source=SOURCE, outcome="refused",
            failure="x", now=T0 + timedelta(minutes=minute), counts_toward_pause=counts,
        )  # fmt: skip
    assert await runs.refusals_in_a_row(recipe) == 2


# --- ADR-127 decision 6, Amendment 5: the load's record, kept beside the run -------------------


def _record(load_id: str, recipe: str, **changes: object) -> LoadRecord:
    return LoadRecord(
        load_id=load_id, recipe_id=recipe, recipe_version=3, source="private_cash.csv",
        started_at=T0, completed_at=T0, created_by="analyst-1", investigation_id="case-1",
        created_node_ids=["n1", "n2"], merged_node_ids=["doc-shared"],
        created_edge_ids=["e-new"], merged_edge_ids=["e-old"],
        touched_edge_ids=["e-new", "e-old"], events_stamped=True, **changes,
    )  # fmt: skip


async def _started(runs: RecipeRunStore, recipe: str, trigger: str = "manual") -> str:
    return await runs.start(
        recipe_id=recipe, recipe_version=3, investigation_id="case-1", trigger=trigger,  # type: ignore[arg-type]
        slot=None, run_as="analyst-1", source=SOURCE, now=T0,
    )  # fmt: skip


async def test_a_runs_record_round_trips_with_created_and_merged_kept_apart(
    runs: RecipeRunStore,
) -> None:
    recipe = new_id()
    run_id = await _started(runs, recipe)
    load_id = new_id()
    await runs.add_record(run_id, _record(load_id, recipe))
    kept = await runs.load_record(load_id)
    assert kept is not None
    assert (kept.created_node_ids, kept.merged_node_ids) == (["n1", "n2"], ["doc-shared"])
    assert (kept.created_edge_ids, kept.merged_edge_ids) == (["e-new"], ["e-old"])
    assert kept.investigation_id == "case-1" and kept.events_stamped is True
    assert kept.released_from is None and (kept.recipe_id, kept.recipe_version) == (recipe, 3)


async def test_a_record_written_at_the_commit_is_there_when_the_run_then_fails(
    runs: RecipeRunStore,
) -> None:
    """The record is appended to a run that is still `running`; a failure after it leaves it."""
    recipe = new_id()
    run_id = await _started(runs, recipe)
    load_id = new_id()
    await runs.add_record(run_id, _record(load_id, recipe))
    await runs.fail(run_id, failure="the analytics store is down", now=T0)
    assert (await runs.load_record(load_id)) is not None
    (row,) = await runs.for_recipe(recipe)
    assert row.outcome == "failed"


async def test_a_pipeline_runs_branch_records_are_each_found_by_their_own_load_id(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe).model_copy(update={"source": "two.csv"}))
    await runs.finish(
        run_id, report=LoadReport(load_id=base, recipe_id=recipe, recipe_version=3), now=T0
    )
    second = await runs.load_record(f"{base}:s2")
    assert second is not None and second.source == "two.csv"
    first = await runs.load_record(f"{base}:s1")
    assert first is not None and first.source == "private_cash.csv"
    assert await runs.load_record(base) is None


async def test_the_geometry_refs_a_load_inserted_are_added_to_its_own_record_only(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    await runs.add_geometries(run_id, f"{base}:s2", ["g1", "g2"])
    first, second = await runs.load_record(f"{base}:s1"), await runs.load_record(f"{base}:s2")
    assert first is not None and first.created_geometry_refs == []
    assert second is not None and second.created_geometry_refs == ["g1", "g2"]
    assert second.created_edge_ids == ["e-new"], "the rest of the record is as it was"


async def test_what_an_alert_after_the_commit_wrote_is_added_to_its_loads_record_only(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    await runs.add_rule_writes(
        run_id, f"{base}:s2", node_ids=["alert-1"], created_edge_ids=["l-new"], merged_edge_ids=["l-old"]
    )
    first, second = await runs.load_record(f"{base}:s1"), await runs.load_record(f"{base}:s2")
    assert first is not None and first.created_node_ids == ["n1", "n2"]
    assert second is not None
    assert second.created_node_ids == ["n1", "n2", "alert-1"]
    assert second.created_edge_ids == ["e-new", "l-new"] and second.merged_edge_ids == ["e-old", "l-old"]
    assert second.touched_edge_ids == ["e-new", "e-old", "l-new", "l-old"]
    assert second.source == "private_cash.csv", "the rest of the record is as it was"


async def test_a_load_a_stage_wrote_for_is_marked_uncovered_and_the_other_is_not(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    await runs.mark_uncovered(run_id, f"{base}:s1")
    first, second = await runs.load_record(f"{base}:s1"), await runs.load_record(f"{base}:s2")
    assert first is not None and first.uncovered_writes is True
    assert second is not None and second.uncovered_writes is False


async def test_a_release_keeps_where_it_was_released_from(runs: RecipeRunStore) -> None:
    recipe = new_id()
    run_id = await _started(runs, recipe, "release")
    load_id, original = new_id(), new_id()
    await runs.add_record(run_id, _record(load_id, recipe, released_from=original))
    kept = await runs.load_record(load_id)
    assert kept is not None and kept.released_from == original
    assert [r.trigger for r in await runs.for_recipe(recipe)] == ["release"]


async def test_a_run_with_no_record_has_none_and_an_unknown_load_has_none(
    runs: RecipeRunStore,
) -> None:
    recipe = new_id()
    run_id = await _started(runs, recipe)
    load_id = new_id()
    await runs.finish(
        run_id, report=LoadReport(load_id=load_id, recipe_id=recipe, recipe_version=3), now=T0
    )
    assert await runs.load_record(load_id) is None
    assert await runs.load_record(new_id()) is None


async def test_a_ledger_made_before_records_is_brought_forward_and_keeps_its_runs() -> None:
    """`CREATE TABLE IF NOT EXISTS` leaves an old `recipe_runs` as it was; connecting must add the
    column, or every later `finish` fails on it. Run in a schema of its own, so the shared ledger
    is not touched."""
    import asyncpg
    from services.api import recipe_runs as module

    schema = f"mig_{new_id().lower().replace('-', '')[:20]}"
    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(f"SET search_path TO {schema}")
        await conn.execute(module._BOOTSTRAP_SQL.replace(module._ADD_LOAD_RECORDS, ""))
        columns = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = 'recipe_runs'", schema,
            )
        }  # fmt: skip
        assert "load_records" not in columns
        await conn.execute(
            "INSERT INTO recipe_runs (run_id, recipe_id, recipe_version, investigation_id, "
            "trigger, run_as, source_handling, started_at, outcome) VALUES "
            "('old', 'r', 1, 'case-1', 'manual', 'a', $1::jsonb, now(), 'succeeded')",
            SOURCE.model_dump_json(),
        )
        await conn.execute(module._BOOTSTRAP_SQL)
        await conn.execute(module._BOOTSTRAP_SQL)  # and again: a no-op on a ledger that has it
        assert await conn.fetchval("SELECT load_records FROM recipe_runs WHERE run_id = 'old'") is None
    finally:
        await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await conn.close()


# --- ADR-127 Amendments 5 and 6, B2-4c: what the revert asks of the ledger -----------------------


async def test_a_pipeline_runs_branches_are_found_by_the_run_prefix_and_not_by_a_longer_id(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    await runs.add_record(run_id, _record(f"{base}0:s1", recipe))  # `base` followed by a digit
    found = await runs.records_with_prefix(f"{base}:")
    assert sorted(r.load_id for r in found) == [f"{base}:s1", f"{base}:s2"]
    assert await runs.records_with_prefix(f"{new_id()}:") == []


async def test_the_releases_of_a_load_are_found_by_released_from(runs: RecipeRunStore) -> None:
    recipe, held, other = new_id(), new_id(), new_id()
    parent = await _started(runs, recipe)
    await runs.add_record(parent, _record(held, recipe))
    for i, source in enumerate((held, held, other)):
        release = await _started(runs, recipe, trigger="release")
        await runs.add_record(release, _record(f"{held}-rel-{i}", recipe, released_from=source))
    found = await runs.releases_of(held)
    assert sorted(r.load_id for r in found) == [f"{held}-rel-0", f"{held}-rel-1"]
    assert await runs.releases_of(new_id()) == []


async def test_a_record_is_marked_reverted_and_its_neighbours_are_not(
    runs: RecipeRunStore,
) -> None:
    recipe, base = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _record(f"{base}:s1", recipe))
    await runs.add_record(run_id, _record(f"{base}:s2", recipe))
    at = T0 + timedelta(hours=1)
    await runs.mark_reverted(f"{base}:s1", reverted_by="operator-1", at=at)
    first, second = await runs.load_record(f"{base}:s1"), await runs.load_record(f"{base}:s2")
    assert first is not None and (first.reverted_at, first.reverted_by) == (at, "operator-1")
    assert second is not None and (second.reverted_at, second.reverted_by) == (None, None)
    # A revert is not a supersession: a ledger reader must not mistake one for the other.
    assert (first.superseded_at, first.superseded_by) == (None, None)
    # The record is otherwise as it was, and the branches keep their order in the row.
    assert first.created_node_ids == ["n1", "n2"] and first.events_stamped is True
    assert [r.load_id for r in await runs.records_with_prefix(f"{base}:")] == [
        f"{base}:s1", f"{base}:s2",
    ]  # fmt: skip


async def test_the_records_that_merged_into_given_elements_are_found_unreverted_only(
    runs: RecipeRunStore,
) -> None:
    """ADR-127 Amendment 6: a revert refuses while an unreverted record outside it lists one of its
    created nodes or links as merged into. Matched on either list, a reverted record is left out."""
    recipe = new_id()
    run_id = await _started(runs, recipe)
    link, node, other = new_id(), new_id(), new_id()

    def merging(load_id: str, *, nodes: list[str], links: list[str]) -> LoadRecord:
        return _record(load_id, recipe).model_copy(
            update={"merged_node_ids": nodes, "merged_edge_ids": links}
        )

    await runs.add_record(run_id, merging("by-link", nodes=[], links=[link, other]))
    await runs.add_record(run_id, merging("by-node", nodes=[node], links=[]))
    await runs.add_record(run_id, merging("by-neither", nodes=[], links=[other]))
    await runs.add_record(run_id, merging("by-both-but-reverted", nodes=[], links=[link]))
    await runs.mark_reverted("by-both-but-reverted", reverted_by="operator-1", at=T0)
    found = await runs.records_merging([node], [link])
    assert sorted(r.load_id for r in found) == ["by-link", "by-node"]
    assert await runs.records_merging([], []) == []
    assert await runs.records_merging([new_id()], [new_id()]) == []


async def test_marking_a_load_the_ledger_holds_no_record_of_is_an_error(
    runs: RecipeRunStore,
) -> None:
    with pytest.raises(KeyError):
        await runs.mark_reverted(new_id(), reverted_by="operator-1", at=T0)


# --- the same revert's other two stores (held rows, the alert queue) --------------------------
#
# `tests/ingest/test_revert_load.py` proves the revert's logic against fakes that hold to these two
# methods; these show the SQL does what the fakes say. `discard_for_load` rejects a load's rows
# still held, leaves rows already released or rejected, touches no other load's and returns 0 the
# second time. `close_for_elements` closes the alerts that are the load's own or cite a reverted
# node or link, once, with no disposition, and leaves every other alert, closed ones included.


@pytest.fixture
async def held() -> AsyncIterator[HeldRowStore]:
    store = await HeldRowStore.connect(PostgresConfig.from_env().dsn, load_uk_le_scheme())
    try:
        yield store
    finally:
        await store.close()


@pytest.fixture
async def alerts() -> AsyncIterator[AlertStore]:
    store = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        yield store
    finally:
        await store.close()


def _row(load_id: str, index: int, status: str = "held") -> HeldRow:
    return HeldRow(
        id=new_id(), investigation_id="case-1", recipe_id="r", recipe_version=1, load_id=load_id,
        source="s.csv", row_index=index, row={"a": "1"}, rule_id="rule-1", reason="overran",
        handling=SOURCE, status=status, held_at=T0,  # type: ignore[arg-type]
    )  # fmt: skip


async def test_the_rows_of_a_reverted_load_still_held_are_rejected_and_no_others(
    held: HeldRowStore,
) -> None:
    load, other = new_id(), new_id()
    rows = [_row(load, 0), _row(load, 1), _row(load, 2, "released"), _row(other, 0)]
    await held.hold(rows)
    assert await held.discard_for_load(load, discarded_by="operator-1", at=T0) == 2
    assert await held.discard_for_load(load, discarded_by="operator-1", at=T0) == 0
    pending = await held._pool.fetch(
        "SELECT load_id, status, decided_by, decision_reason FROM held_rows "
        "WHERE load_id = ANY($1::text[]) ORDER BY load_id, row_index",
        [load, other],
    )
    by = {(r["load_id"], r["status"]) for r in pending}
    assert by == {(load, "rejected"), (load, "released"), (other, "held")}
    rejected = [r for r in pending if r["status"] == "rejected"]
    assert {r["decided_by"] for r in rejected} == {"operator-1"}
    assert all(load in r["decision_reason"] for r in rejected)


def _alert(node: str | None, status: str = "open", **fields: object) -> Alert:
    return Alert(
        id=new_id(), rule_id="rule-1", owner_id="owner-1", mode=AlertMode.NOTIFY_STUB,
        investigation_id="case-1", created_at=T0, alert_node_id=node, status=status,  # type: ignore[arg-type]
        **fields,  # type: ignore[arg-type]
    )  # fmt: skip


async def test_the_alerts_resting_on_reverted_elements_are_closed_once_and_no_others(
    alerts: AlertStore,
) -> None:
    """An alert is closed when its own node, a node it cites or a link it cites is one of the
    reverted ids; one that cites none of them, and one already closed, are left as they were."""
    own, cited_node, cited_link = new_id(), new_id(), new_id()
    closed_node, kept_node, kept_link = new_id(), new_id(), new_id()
    by_own = _alert(own)
    by_node = _alert(new_id(), referent_node_ids=[cited_node])
    by_link = _alert(new_id(), edge_ids=[cited_link])
    theirs = _alert(kept_node, referent_node_ids=[kept_node], edge_ids=[kept_link])
    done = _alert(closed_node, "closed")
    plain = _alert(None)  # no node, nothing cited
    for alert in (by_own, by_node, by_link, theirs, done, plain):
        await alerts.save(alert)
    closed = await alerts.close_for_elements(
        [own, cited_node, closed_node, new_id()], [cited_link, new_id()],
        closed_by="operator-1", at=T0, reason="load x was reverted",
    )  # fmt: skip
    assert closed == 3, "its own, one citing a node, one citing a link; the closed one not again"
    again = await alerts.close_for_elements(
        [own], [cited_link], closed_by="operator-1", at=T0, reason="x"
    )
    assert again == 0
    nothing = await alerts.close_for_elements([], [], closed_by="o", at=T0, reason="x")
    assert nothing == 0
    ids = [a.id for a in (by_own, by_node, by_link, theirs, done, plain)]
    rows = {
        r["id"]: r
        for r in await alerts._pool.fetch(
            "SELECT id, status, decided_by, disposition, disposition_reason FROM alerts "
            "WHERE id = ANY($1::text[])",
            ids,
        )
    }
    for alert in (by_own, by_node, by_link):
        assert rows[alert.id]["status"] == "closed" and rows[alert.id]["decided_by"] == "operator-1"
        assert rows[alert.id]["disposition"] is None
        assert rows[alert.id]["disposition_reason"] == "load x was reverted"
    assert rows[theirs.id]["status"] == "open" and rows[plain.id]["status"] == "open"
    assert rows[done.id]["decided_by"] is None, "a closed alert keeps who closed it"


async def test_alerts_citing_events_are_listed_open_and_closed_by_id(alerts: AlertStore) -> None:
    """ADR-127 Amendment 8 (B2-4c2): a revert closes the alerts that cite an event it retracts. The
    store lists the alerts not yet closed that name events, with the ids they name, and closes
    named ones by id, once."""
    cites, cites_other, none, done = new_id(), new_id(), new_id(), new_id()
    made = [
        _alert(None, event_ids=["ev-a", "ev-b"]).model_copy(update={"id": cites}),
        _alert(None, event_ids=["ev-z"]).model_copy(update={"id": cites_other}),
        _alert(None).model_copy(update={"id": none}),
        _alert(None, "closed", event_ids=["ev-a"]).model_copy(update={"id": done}),
    ]
    for alert in made:
        await alerts.save(alert)
    listed = await alerts.alerts_citing_events()
    assert listed[cites] == ["ev-a", "ev-b"] and listed[cites_other] == ["ev-z"]
    assert none not in listed and done not in listed, "no events named, and already closed"
    closed = await alerts.close_by_ids([cites, done], closed_by="operator-1", at=T0, reason="r")
    assert closed == 1, "the open one; a closed alert is not touched again"
    assert await alerts.close_by_ids([cites], closed_by="operator-1", at=T0, reason="r") == 0
    assert await alerts.close_by_ids([], closed_by="operator-1", at=T0, reason="r") == 0
    row = await alerts._pool.fetchrow(
        "SELECT status, decided_by, disposition, disposition_reason FROM alerts WHERE id = $1",
        cites,
    )
    assert (row["status"], row["decided_by"], row["disposition"]) == ("closed", "operator-1", None)
    assert row["disposition_reason"] == "r"
    other = await alerts._pool.fetchrow("SELECT status FROM alerts WHERE id = $1", cites_other)
    assert other["status"] == "open"


# --- ADR-127 decision 5, B2-5: the rows a recipe has loaded into a case --------------------------
#
# Each case here makes its own recipe, case, load ids and keys (`new_id()`), because this ledger is
# a real database that outlives the run: a record is found by load id across every run
# (`load_record`), and a release frees every key of a load id, so fixed ids from one case would
# find or free another's (a first version of these used `load-a` throughout, and the record of an
# earlier case answered "is the record gone?").


def _keyed(load_id: str, recipe: str, case: str) -> LoadRecord:
    return _record(load_id, recipe).model_copy(
        update={"investigation_id": case, "merged_node_ids": [], "merged_edge_ids": []}
    )


async def test_the_keys_of_a_load_are_kept_for_its_recipe_and_case_and_read_back(
    runs: RecipeRunStore,
) -> None:
    recipe, other_recipe, case, other_case = new_id(), new_id(), new_id(), new_id()
    k1, k2, k3 = new_id(), new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(new_id(), recipe, case), row_keys=[k1, k2, k2])
    assert await runs.kept_row_keys(recipe, case, [k1, k2, k3]) == {k1, k2}
    # Rule 3: per recipe and per case. Another case, or another recipe, keeps its own.
    assert await runs.kept_row_keys(recipe, other_case, [k1, k2]) == set()
    assert await runs.kept_row_keys(other_recipe, case, [k1, k2]) == set()
    assert await runs.kept_row_keys(recipe, case, []) == set()
    assert await runs.kept(recipe, case, [k1]) == {k1}, "the engine's `RowKeys` question"


async def test_a_key_already_kept_is_left_as_it_was_and_a_new_version_reads_the_same_keys(
    runs: RecipeRunStore,
) -> None:
    recipe, case, first, second = new_id(), new_id(), new_id(), new_id()
    k1, k2 = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(first, recipe, case), row_keys=[k1])
    await runs.add_record(run_id, _keyed(second, recipe, case), row_keys=[k1, k2])
    rows = await runs._pool.fetch(
        "SELECT row_key, load_id FROM loaded_row_keys WHERE recipe_id = $1", recipe
    )
    assert {(r["row_key"], r["load_id"]) for r in rows} == {(k1, first), (k2, second)}
    # The key is of the recipe and the case, not of a version: asked by id alone.
    assert await runs.kept_row_keys(recipe, case, [k1, k2]) == {k1, k2}


async def test_the_record_and_its_keys_land_together_or_neither(runs: RecipeRunStore) -> None:
    """One transaction (`add_record`): a key the column refuses (a NUL byte, which Postgres text
    cannot hold) fails the second statement, and the first (the record's append) and the keys
    before it in the same batch go with it. Read from the run's own row, not by load id across the
    ledger, so no other run's record can answer."""
    recipe, case, load, good = new_id(), new_id(), new_id(), new_id()
    run_id = await _started(runs, recipe)
    with pytest.raises(Exception):  # noqa: B017 (asyncpg's own error, whichever it names)
        await runs.add_record(
            run_id, _keyed(load, recipe, case), row_keys=[good, "bad\x00key"]
        )
    on_the_run = await runs._pool.fetchval(
        "SELECT load_records FROM recipe_runs WHERE run_id = $1", run_id
    )
    assert on_the_run is None, "the record was not appended"
    assert await runs.load_record(load) is None
    assert await runs.kept_row_keys(recipe, case, [good]) == set(), "nor the key before the bad one"
    # And the run is not poisoned: the same call, without the bad key, lands whole.
    await runs.add_record(run_id, _keyed(load, recipe, case), row_keys=[good])
    assert await runs.load_record(load) is not None
    assert await runs.kept_row_keys(recipe, case, [good]) == {good}


async def test_releasing_a_loads_keys_frees_exactly_its_own_and_a_second_release_frees_none(
    runs: RecipeRunStore,
) -> None:
    recipe, case = new_id(), new_id()
    load_a, load_b, load_c = new_id(), new_id(), new_id()
    k1, k2, k3 = new_id(), new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(run_id, _keyed(load_a, recipe, case), row_keys=[k1, k2])
    await runs.add_record(run_id, _keyed(load_b, recipe, case), row_keys=[k3])
    assert await runs.release_row_keys([load_a]) == 2
    assert await runs.release_row_keys([load_a]) == 0
    assert await runs.release_row_keys([]) == 0
    assert await runs.kept_row_keys(recipe, case, [k1, k2, k3]) == {k3}
    # Released, a rerun may keep them again.
    await runs.add_record(run_id, _keyed(load_c, recipe, case), row_keys=[k1])
    assert await runs.kept_row_keys(recipe, case, [k1]) == {k1}


async def test_the_key_table_is_indexed_for_the_lookup_and_for_the_release(
    runs: RecipeRunStore,
) -> None:
    """The primary key is the lookup (`row_key = ANY(...)` for one recipe and case) and the index on
    `load_id` is what a revert releases by: neither is a scan of a million-row table."""
    rows = await runs._pool.fetch(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'loaded_row_keys'"
    )
    definitions = " ".join(r["indexdef"] for r in rows)
    assert "(recipe_id, investigation_id, row_key)" in definitions
    assert "(load_id)" in definitions


# --- ADR-127 decision 5: the definition that made a key, and the lock that serialises runs ------


async def test_each_key_is_kept_with_the_fingerprint_of_the_definition_that_made_it(
    runs: RecipeRunStore,
) -> None:
    recipe, case = new_id(), new_id()
    old, new = new_id(), new_id()
    first, second, third = new_id(), new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id, _keyed(first, recipe, case), row_keys=[new_id()], row_key_fingerprint=old
    )
    await runs.add_record(
        run_id, _keyed(second, recipe, case), row_keys=[new_id()], row_key_fingerprint=old
    )
    await runs.add_record(
        run_id, _keyed(third, recipe, case), row_keys=[new_id()], row_key_fingerprint=new
    )
    # How many loads kept keys under each: what a refusal names (a count, never an id).
    assert await runs.fingerprints(recipe, case) == {old: 2, new: 1}
    # Per recipe and case: another case sees none of it.
    assert await runs.fingerprints(recipe, new_id()) == {}
    # A revert releases a load's keys, and with them its place in the count.
    await runs.release_row_keys([first, second])
    assert await runs.fingerprints(recipe, case) == {new: 1}


async def test_a_load_that_kept_no_keys_leaves_no_fingerprint(runs: RecipeRunStore) -> None:
    recipe, case = new_id(), new_id()
    run_id = await _started(runs, recipe)
    await runs.add_record(
        run_id, _keyed(new_id(), recipe, case), row_keys=[], row_key_fingerprint=new_id()
    )
    assert await runs.fingerprints(recipe, case) == {}


async def test_a_second_holder_of_the_lock_is_refused_after_a_short_wait_and_not_before_it_is_free(
    runs: RecipeRunStore,
) -> None:
    import asyncio

    from services.ingest.engine import RowKeyRunInProgress

    recipe, case = new_id(), new_id()
    async with runs.hold_row_keys(recipe, case):
        with pytest.raises(RowKeyRunInProgress):
            async with runs.hold_row_keys(recipe, case, wait_seconds=0.3):
                raise AssertionError("two runs held one recipe in one case")
        # Another recipe, or another case, is not held up.
        async with runs.hold_row_keys(new_id(), case, wait_seconds=0.3):
            pass
        async with runs.hold_row_keys(recipe, new_id(), wait_seconds=0.3):
            pass
    # Released: the next holder takes it at once.
    async with runs.hold_row_keys(recipe, case, wait_seconds=0.3):
        pass

    # A waiter that the holder lets go of inside its wait takes the lock then.
    async def hold_briefly() -> None:
        async with runs.hold_row_keys(recipe, case):
            await asyncio.sleep(0.5)

    holder = asyncio.create_task(hold_briefly())
    await asyncio.sleep(0.1)
    async with runs.hold_row_keys(recipe, case, wait_seconds=5.0):
        pass
    await holder


async def test_the_lock_is_released_when_the_holder_fails_or_is_cancelled(
    runs: RecipeRunStore,
) -> None:
    import asyncio

    recipe, case = new_id(), new_id()
    with pytest.raises(RuntimeError):
        async with runs.hold_row_keys(recipe, case):
            raise RuntimeError("the load failed")
    async with runs.hold_row_keys(recipe, case, wait_seconds=0.3):
        pass

    entered = asyncio.Event()

    async def hold_forever() -> None:
        async with runs.hold_row_keys(recipe, case):
            entered.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(hold_forever())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with runs.hold_row_keys(recipe, case, wait_seconds=2.0):
        pass


async def test_the_lock_is_held_on_a_connection_of_its_own_until_released(
    runs: RecipeRunStore,
) -> None:
    """Session-level, so it outlives any one statement and ends with the session: while held, the
    server shows it, and it is gone when the block ends."""
    recipe, case = new_id(), new_id()
    count = "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted"
    before = await runs._pool.fetchval(count)
    async with runs.hold_row_keys(recipe, case):
        assert await runs._pool.fetchval(count) == before + 1
    assert await runs._pool.fetchval(count) == before


async def test_more_runs_of_distinct_recipes_than_the_pool_has_connections_all_complete(
    runs: RecipeRunStore,
) -> None:
    """Each running load holds the row-key lock for its whole run and then needs the pool to write
    its record. A lock that took a pooled connection would, with every connection held by a lock,
    leave every run waiting for the connection to write with: a deadlock. Six runs against a pool
    of four must all finish and keep their records."""
    import asyncio

    pool_max = runs._pool.get_max_size()
    count = pool_max + 2
    case = new_id()
    recipes = [new_id() for _ in range(count)]
    all_holding = asyncio.Event()
    holding = 0

    async def one_run(recipe: str) -> str:
        nonlocal holding
        async with runs.hold_row_keys(recipe, case, wait_seconds=5.0):
            holding += 1
            if holding == count:
                all_holding.set()
            # Every run is inside its lock before any writes: the worst case for the pool.
            await all_holding.wait()
            load_id = new_id()
            run_id = await _started(runs, recipe)
            await runs.add_record(
                run_id,
                _keyed(load_id, recipe, case),
                row_keys=[f"k-{load_id}"],
                row_key_fingerprint="fp",
            )
            return load_id

    loads = await asyncio.wait_for(asyncio.gather(*(one_run(r) for r in recipes)), timeout=20)
    assert len(set(loads)) == count
    for load_id in loads:
        assert await runs.load_record(load_id) is not None
