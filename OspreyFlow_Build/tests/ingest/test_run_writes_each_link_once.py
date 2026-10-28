"""ADR-127 Amendment 19 (B2-9): a run combines its own writes before it writes them, one `EdgeWrite`
for each link however many rows carry it. What a mistake would do, and the case that catches it
(rule 12; each case was shown red against a planted violation, which `process/` records):

- a combined run that leaves anything other than what writing each row's link as it comes leaves,
  the amendment's stated differences excepted
  (`test_a_combined_run_leaves_what_a_run_per_row_leaves`), on R5's slice, R6 in the seed's order,
  a merge into a link an earlier load stored, and an asserted link written again with inferred
  writes, each through the stand-in and through `GraphArcadeDBAdapter.upsert_edges`;
- a buffer that batches without combining, so the store still gets a write per row
  (`test_the_run_sends_one_write_for_each_link_not_for_each_row`);
- an event or an entry in `written` left with an id the store never held, or every event given the
  first link's id (`test_each_events_edge_id_is_the_stored_link_between_its_own_ends`);
- a link counted once for each row that wrote it in the load record
  (`test_the_record_names_each_link_once_whatever_the_rows`);
- a write the adapter would refuse, found only at the flush, naming no row, with the rows before it
  already written
  (`test_a_refused_write_on_a_middle_row_fails_the_run_naming_it_and_writes_nothing`);
- combining with no handling scheme, which would merge what ADR-102 Amendment 3 keeps apart
  (`test_a_run_with_no_scheme_sends_one_write_per_row`);
- a combined link left at a revision other than the per-row path gives it
  (`test_a_link_combined_from_n_writes_holds_revision_n`);
- a `HOLDS` link counted once for a document held twice, or recorded at the wrong time
  (`test_a_document_held_twice_by_one_holder_is_one_link_counted_for_each_hold`).

The R5 cost, the file's 3,547 links sent as 3,547 writes, is `test_pid_r5_cost.py`, which is slow
and outside `make ci`. The store cases (rules 3 and 4) are in
`test_run_writes_each_link_once_live.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from services.api.studio_publish import load_with_rules
from services.ingest import engine
from services.ingest.engine import run_recipe

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.errors import OntologyError
from ontology.handling import load_uk_le_scheme
from ontology.validation import validate_properties as real_validate_properties
from schemas.domain import EdgeTypeDef, Principal
from schemas.ingest import Recipe
from tests.ingest import recipe_test_support
from tests.ingest.combined_run_support import (
    AdapterBacked,
    CountingMerging,
    Load,
    audience_recipe,
    audience_row,
    per_row,
    run,
)
from tests.ingest.pid_golden_support import (
    CALLS,
    marking,
    msisdn,
    pin_calls_slice,
    pin_calls_to_step,
    recipe_for,
    rows_of,
)
from tests.ingest.pid_golden_support import (
    ONTOLOGY as PID_ONTOLOGY,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)

BEFORE = (
    "pid_establishment_plan.csv",
    "pid_nomis_prisoners.csv",
    "pid_nomis_visits.csv",
    "pid_number_owners.csv",
)
BATCH_1 = "pid_seized_comms_batch1.csv"
BATCH_2 = "pid_seized_comms_batch2.csv"
BACKENDS = ["stand_in", "adapter"]
#: How many rows of R5's slice (the first of its file order, whole links being 69,044 rows) a case
#: is given. The stand-in and the adapter harness answer each write by scanning what they hold, so
#: the per-row reference costs minutes at the slice's full size; four thousand rows are a few dozen
#: links of a hundred rows or more each, which is what a combined run is for.
SLICE_ROWS = 4000


def _slice_rows(backend: str) -> tuple[dict[str, str], ...]:
    return pin_calls_slice()[0][:SLICE_ROWS]


def _r6_steps(backend: str) -> list[Any]:
    """R16, then R5 (the rows to R6's numbers, the first of them), then R6's two batches."""
    numbers = frozenset(msisdn(r["other_number"]) for f in (BATCH_1, BATCH_2) for r in rows_of(f))
    calls = pin_calls_to_step(numbers)
    assert calls.rows is not None
    return [*BEFORE, Load(CALLS, calls.rows[:SLICE_ROWS]), BATCH_1, BATCH_2]


def _inferred(recipe: Recipe) -> Recipe:
    """The recipe as a model-driven writer would run it: its links are `inferred`, and it is another
    recipe, so the case's row keys do not see its rows as already loaded."""
    defaults = recipe.defaults.model_copy(
        update={"provenance": {"state": "inferred", "extraction_confidence": 0.4}}
    )
    return recipe.model_copy(update={"id": f"{recipe.id}-inferred", "defaults": defaults})


def _cases(backend: str) -> dict[str, list[Any]]:
    rows = _slice_rows(backend)
    half = len(rows) // 2
    return {
        "r5_slice": [*BEFORE, Load(CALLS, rows)],
        "r6_in_seed_order": _r6_steps(backend),
        "merge_into_an_earlier_load": [
            *BEFORE,
            Load(CALLS, rows[:half], load_id="load-first-half"),
            Load(CALLS, rows[half:], load_id="load-second-half"),
        ],
        "asserted_link_written_again_with_inferred_writes": [
            *BEFORE,
            Load(CALLS, rows[:half], load_id="load-asserted"),
            Load(
                CALLS,
                rows[:half],
                recipe=_inferred(recipe_for(CALLS)),
                load_id="load-inferred",
            ),
        ],
    }


# --- equivalence ----------------------------------------------------------------------------------


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    "case",
    ["r5_slice", "r6_in_seed_order", "merge_into_an_earlier_load",
     "asserted_link_written_again_with_inferred_writes"],
)  # fmt: skip
async def test_a_combined_run_leaves_what_a_run_per_row_leaves(backend: str, case: str) -> None:
    """Every link's occurrences, interval, properties, source rows, datasets, marking, revision and
    load, every event, the load record's counts and the order of its ids, are the per-row run's.
    `weight` and its components, and the top-level properties a link stores flat, are the
    amendment's stated differences and are not compared. Catches the combiner dropping a source
    row, folding occurrences or an interval wrongly, lowering a marking or an asserted link, or
    leaving the revision, the record or an event different."""
    steps = _cases(backend)[case]
    combined, _ = await run(backend, steps)
    reference, _ = await run(backend, steps, combine=False)
    assert combined.links, "a case that stores nothing proves nothing"
    assert combined.links == reference.links
    assert combined.events == reference.events
    assert combined.reports == reference.reports
    # The two are not the same run: the combined one wrote fewer links than the rows it was given.
    assert sum(combined.calls) < sum(reference.calls)


async def test_the_inferred_rewrite_leaves_the_asserted_link_asserted() -> None:
    """The case above only compares the two runs, and an engine that lowered the link on both would
    pass it. Held to the rule itself (`01_DOMAIN_MODEL.md` §2.1): after the second load every link
    is still asserted, and its occurrences hold both loads' rows."""
    steps = _cases("stand_in")["asserted_link_written_again_with_inferred_writes"]
    combined, _ = await run("stand_in", steps)
    calls = {k: v for k, v in combined.links.items() if k[0] == "COMMUNICATED_WITH"}
    assert calls
    assert {v["state"] for v in calls.values()} == {"asserted"}
    assert all(v["revision"] >= 2 for v in calls.values())


# --- the cost -------------------------------------------------------------------------------------


@pytest.mark.parametrize("backend", BACKENDS)
async def test_the_run_sends_one_write_for_each_link_not_for_each_row(backend: str) -> None:
    """Catches a buffer that holds writes and flushes them without combining: the store would still
    be sent a write per row. The slice's calls are several thousand rows on a few dozen links, so
    R5's load sends exactly the links it makes or merges into (its `touched_edge_ids`), where the
    per-row run sends a write for every row's two links."""
    rows = _slice_rows(backend)
    steps: list[Any] = [*BEFORE, Load(CALLS, rows)]
    combined, _ = await run(backend, steps)
    reference, _ = await run(backend, steps, combine=False)
    sent = sum(combined.calls_by_load[-1])
    touched = combined.reports[-1]["touched"]
    assert sent == len(touched) == len(set(touched))
    assert len(rows) > 10 * sent, "a slice with many rows to a link, or the case proves nothing"
    assert sum(reference.calls_by_load[-1]) > 10 * sent
    assert combined.calls_by_load[-1] == [sent], "one call, as the links are few"


# --- ids ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("backend", BACKENDS)
async def test_each_events_edge_id_is_the_stored_link_between_its_own_ends(backend: str) -> None:
    """Catches an event left with the id of the row's own write (never stored when the write was
    combined into another's), or every event given the first link's id. Each event's `edge_id`
    must be the id of the stored link between its own `source_id` and `target_id` at its own
    handling's audience: `Snapshot.events` holds the key of the link the event names beside the key
    its ends and handling give, and the two are the same, and are the per-row run's."""
    rows = _slice_rows(backend)
    combined, _ = await run(backend, [*BEFORE, Load(CALLS, rows)])
    reference, _ = await run(backend, [*BEFORE, Load(CALLS, rows)], combine=False)
    assert len(combined.events) > 100
    for expected, named, *_ in combined.events:
        assert named == expected, "the event names a link that is not the one between its ends"
    assert combined.events == reference.events
    named_links = {named for _, named, *_ in combined.events}
    assert len(named_links) > 10, "events spread over their own links, not one"


async def test_a_written_entry_takes_the_stored_id_of_its_own_link() -> None:
    """`written` (what a pre-commit rule judges) has one entry for each row's write of a link, as
    the per-row path gave, and each takes the stored id of its link at the flush. Catches an entry
    left with the id the row's own write carried, which is no link the store holds."""
    graph = CountingMerging(PID_ONTOLOGY)
    written: list[Any] = []
    tx = await graph.begin_transaction()
    recipe = _pair_recipe()
    rows = [_pair_row("a", "b", n) for n in range(6)]
    await run_recipe(
        recipe,
        rows,
        graph=graph,  # type: ignore[arg-type]
        ontology=PID_ONTOLOGY,
        tx=tx,
        principal=LOADER,
        load_id="load-w",
        investigation_scope="case-1",
        source="rows.csv",
        scheme=SCHEME,
        written=written,
    )
    await graph.commit_transaction(tx)
    stored = {e.id for e in graph.committed_edges}
    links = [w for w in written if getattr(w, "source", None) is not None]
    assert len(links) == 6, "one entry for each row's write"
    assert {w.id for w in links} == stored and len(stored) == 1


async def test_the_record_names_each_link_once_whatever_the_rows() -> None:
    """The load record and the change stream name the links a load touched, once each
    (`touched_edge_ids`), in the order each was first touched. Six rows to one link and two to
    another name two ids, the first link's first."""
    graph = CountingMerging(PID_ONTOLOGY)
    rows = [
        *[_pair_row("a", "b", n) for n in range(6)],
        *[_pair_row("c", "d", n) for n in range(2)],
        _pair_row("a", "b", 9),
    ]
    report = await _load_pairs(graph, rows)
    by_ends = {(e.source, e.target): e.id for e in graph.committed_edges}
    names = {n.id: n.properties["value_normalised"] for n in graph.committed_nodes}
    order = [(names[s], names[t]) for (s, t), i in by_ends.items() if i in report.touched_edge_ids]
    assert len(report.touched_edge_ids) == len(set(report.touched_edge_ids)) == 2
    assert [
        (names[e.source], names[e.target])
        for i in report.touched_edge_ids
        for e in graph.committed_edges
        if e.id == i
    ] == [("a", "b"), ("c", "d")]
    assert report.edges_created == 2
    assert len(report.created_edge_ids) == 2 and report.merged_edge_ids == []
    assert order  # the two links are the ones the record names


# --- a refusal ------------------------------------------------------------------------------------


def _refuse_a_duration(real: Callable[..., None]) -> Callable[..., None]:
    """`validate_properties` as an ontology that refuses one value of a link's duration would give
    it: the whole link type's properties (not the one-property copy the row check makes) with a
    duration of thirteen are refused, by the engine's own check as by the stand-in store's."""

    def refuse(type_def: Any, properties: dict[str, Any]) -> None:
        if (
            isinstance(type_def, EdgeTypeDef)
            and len(type_def.properties) > 1
            and properties.get("duration_s") in (13, 13.0)
        ):
            raise OntologyError("a duration of thirteen is refused")
        real(type_def, properties)

    return refuse


async def test_a_refused_write_on_a_middle_row_fails_the_run_naming_it_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refused write is on a row that is neither its link's first nor its last, so a check made
    only on the first write held, or only at the flush, does not meet it where the row is known.
    Catches validation left to the flush, which fails the run but names no row and has written the
    links before it, and validation that checks only the first write of a link."""
    monkeypatch.setattr(engine, "validate_properties", _refuse_a_duration(real_validate_properties))
    monkeypatch.setattr(
        recipe_test_support, "validate_properties", _refuse_a_duration(real_validate_properties)
    )
    graph = CountingMerging(PID_ONTOLOGY)
    rows = [_pair_row("a", "b", n) for n in range(7)]
    rows[3]["duration"] = "13"
    with pytest.raises(OntologyError) as raised:
        await _load_pairs(graph, rows)
    # ADR-131: the row is named as a person counts it, the fourth data row as row 4.
    assert "row 4:" in str(raised.value), "the error names the row whose write was refused"
    assert graph.open_edges == [] and graph.committed_edges == [], "nothing was written"
    assert graph.edge_calls == [], "not so much as a call to write a link"


# --- no scheme ------------------------------------------------------------------------------------


async def test_a_run_with_no_scheme_sends_one_write_per_row() -> None:
    """Without a handling scheme a restricted code's units cannot be told apart, so a run combines
    nothing: each row's link is sent as it is held (the CLI, the site grid, the seeders and the
    basemap builder). The record still names each link once."""
    graph = CountingMerging(PID_ONTOLOGY)
    rows = [_pair_row("a", "b", n) for n in range(5)]
    report = await _load_pairs(graph, rows, scheme=None)
    assert graph.edge_calls == [1, 1, 1, 1, 1]
    (link,) = graph.committed_edges
    assert link.occurrences == 5
    assert len(report.touched_edge_ids) == 1 and report.edges_created == 1


async def test_a_run_with_a_scheme_sends_the_same_rows_as_one_write() -> None:
    graph = CountingMerging(PID_ONTOLOGY)
    rows = [_pair_row("a", "b", n) for n in range(5)]
    await _load_pairs(graph, rows)
    assert graph.edge_calls == [1]
    (link,) = graph.committed_edges
    assert link.occurrences == 5 and link.writes == 5


# --- audiences ------------------------------------------------------------------------------------


async def _audience_run(backend: str, rows: list[dict[str, str]], *, combine: bool) -> Any:
    graph: CountingMerging = (
        CountingMerging(PID_ONTOLOGY) if backend == "stand_in" else AdapterBacked(PID_ONTOLOGY)
    )
    with per_row() if not combine else _plain():
        report, _events, _held = await load_with_rules(
            audience_recipe(),
            rows,
            LOADER,
            graph=graph,  # type: ignore[arg-type]
            ontology=PID_ONTOLOGY,
            load_id="load-1",
            investigation_scope="case-1",
            source="pairs.csv",
            media=InMemoryMediaStore(),
            rules=None,
            scheme=SCHEME,
        )
    assert report.rejections == [], report.rejections
    return graph


@pytest.mark.parametrize("backend", BACKENDS)
async def test_a_pair_at_two_classifications_is_two_links_combined_as_it_is_per_row(
    backend: str,
) -> None:
    """ADR-102 Amendment 3 in the engine's buffer: OFFICIAL rows and a SECRET row between one pair
    are two links, the OFFICIAL ones combined. Catches a buffer keyed on the pair alone, which
    leaves one link at SECRET. (The reader's side of this, against a real store, is the live
    file's.)"""
    rows = [audience_row(), audience_row(classification="SECRET"), audience_row(), audience_row()]
    for combine in (True, False):
        graph = await _audience_run(backend, rows, combine=combine)
        links = sorted(
            (link["marking"][0], link["occurrences"], link["revision"])
            for link in _links(graph)
            if link["type"] == "COMMUNICATED_WITH"
        )
        assert links == [("OFFICIAL", 3, 3), ("SECRET", 1, 1)], f"combined: {combine}"
        assert graph.edge_calls == ([2] if combine else [1, 1, 1, 1])


@pytest.mark.parametrize("backend", BACKENDS)
async def test_a_restricted_pair_for_two_units_is_two_links_combined_as_it_is_per_row(
    backend: str,
) -> None:
    """Under a restricted code the units are part of the audience: two units' rows between one pair
    are two links. Catches a buffer keyed on the classification alone, which would hand one unit's
    rows to the other."""
    one = {"handling_code": "R", "originator": "unit-1", "owning_unit": "unit-1"}
    two = {"handling_code": "R", "originator": "unit-2", "owning_unit": "unit-2"}
    rows = [audience_row(**one), audience_row(**two), audience_row(**one)]
    for combine in (True, False):
        graph = await _audience_run(backend, rows, combine=combine)
        links = sorted(
            (link["marking"][5], link["occurrences"], link["revision"])
            for link in _links(graph)
            if link["type"] == "COMMUNICATED_WITH"
        )
        assert links == [("unit-1", 2, 2), ("unit-2", 1, 1)], f"combined: {combine}"
        assert graph.edge_calls == ([2] if combine else [1, 1, 1])


def _links(graph: CountingMerging) -> list[dict[str, Any]]:
    out = graph.stored_links()
    for link in out:
        link["marking"] = marking(link["handling"])
    return out


# --- the transaction ----------------------------------------------------------------------------


async def test_a_load_cancelled_between_begin_and_commit_rolls_back() -> None:
    """Amendment 21: the load's guard rolls back on `BaseException`, so a cancelled request (which
    raises `CancelledError`, not an `Exception`) does not leave its transaction open. The load is
    stopped in the flush, after the rows and before the commit. Catches a guard that catches only
    `Exception`."""
    entered = asyncio.Event()

    class Stalling(CountingMerging):
        async def upsert_edges(self, edges: Any, tx: object) -> list[str]:
            entered.set()
            await asyncio.sleep(60)
            return await super().upsert_edges(edges, tx)

    graph = Stalling(PID_ONTOLOGY)
    task = asyncio.create_task(_load_pairs(graph, [_pair_row("a", "b", n) for n in range(3)]))
    await asyncio.wait_for(entered.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert graph.rolled_back == 1 and graph.commits == 0
    assert graph.committed_edges == [] and graph.open_edges == []


async def test_a_failing_rollback_does_not_replace_the_cancellation() -> None:
    """Amendment 21: the rollback in the guard may itself fail (the session had expired: ArcadeDB's
    404). The failure is logged and the original `CancelledError` still propagates, so the caller's
    cancellation is not turned into a database error. Catches a guard that lets the rollback's
    exception through."""
    from adapters.graph_arcadedb.client import ArcadeDBError

    entered = asyncio.Event()

    class Expired(CountingMerging):
        async def upsert_edges(self, edges: Any, tx: object) -> list[str]:
            entered.set()
            await asyncio.sleep(60)
            return await super().upsert_edges(edges, tx)

        async def rollback_transaction(self, tx: object) -> None:
            raise ArcadeDBError("session expired", status_code=404)

    graph = Expired(PID_ONTOLOGY)
    task = asyncio.create_task(_load_pairs(graph, [_pair_row("a", "b", n) for n in range(3)]))
    await asyncio.wait_for(entered.wait(), 10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_a_failing_rollback_does_not_replace_the_error_in_the_held_row_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second guard in `load_with_rules`, around the held rows' markings: a cancellation there,
    with a rollback that fails, is still the cancellation. Reached by a rule that holds a row and
    a marking step that is cancelled."""
    from services.api import studio_publish

    from adapters.graph_arcadedb.client import ArcadeDBError
    from tests.ingest.test_handling_from_columns_review import FakeRules

    def cancelled(*args: Any, **kwargs: Any) -> Any:
        raise asyncio.CancelledError

    class Expired(CountingMerging):
        """The first rollback is the hold's own, and works; the guard's, after it, fails."""

        async def rollback_transaction(self, tx: object) -> None:
            if self.rolled_back >= 1:
                raise ArcadeDBError("session expired", status_code=404)
            await super().rollback_transaction(tx)

    monkeypatch.setattr(studio_publish, "held_rows_for", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await load_with_rules(
            _pair_recipe(),
            [_pair_row("a", "b", n) for n in range(4)],
            LOADER,
            graph=Expired(PID_ONTOLOGY),  # type: ignore[arg-type]
            ontology=PID_ONTOLOGY,
            load_id="load-held",
            investigation_scope="case-1",
            source="pairs.csv",
            media=InMemoryMediaStore(),
            rules=FakeRules(hold_rows=(1,)),  # type: ignore[arg-type]
            scheme=SCHEME,
        )


async def test_a_second_pass_after_held_rows_leaves_no_write_of_the_first() -> None:
    """ADR-109 ruling 1 with a combined run: a pre-commit rule holds a row, the transaction is
    rolled back and the load runs again without it. The first pass's combined link was written (at
    the end of its rows) and is rolled back with the transaction; the second pass writes its own,
    from the rows it keeps, and the stored link is that alone. Catches a buffer that outlives its
    run, which would carry the first pass's rows into the second."""
    from tests.ingest.test_handling_from_columns_review import FakeRules

    graph = CountingMerging(PID_ONTOLOGY)
    rules = FakeRules(hold_rows=(2,))
    report, _events, skipped = await load_with_rules(
        _pair_recipe(),
        [_pair_row("a", "b", n) for n in range(6)],
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=PID_ONTOLOGY,
        load_id="load-held",
        investigation_scope="case-1",
        source="pairs.csv",
        media=InMemoryMediaStore(),
        rules=rules,  # type: ignore[arg-type]
        scheme=SCHEME,
    )
    assert skipped == frozenset({2}) and report.rows_held == 1
    assert graph.rolled_back == 1 and graph.commits == 1
    assert graph.edge_calls == [1, 1], "one link written in each pass"
    (stored,) = graph.committed_edges
    assert stored.occurrences == 5 and graph._revision[stored.id] == 5
    assert "row 2" not in [s.locator for s in stored.provenance.sources]
    assert len(graph.discarded_edges) == 1 and graph.discarded_edges[0].occurrences == 6


# --- the revision ---------------------------------------------------------------------------------


@pytest.mark.parametrize("backend", BACKENDS)
async def test_a_link_combined_from_n_writes_holds_revision_n(backend: str) -> None:
    """The stored revision of a link written by N rows is N, as the per-row path leaves it (the
    revision counts the writes merged into a link, and picks among a pair's links). Catches a
    combined write that stands for one."""
    rows = [_pair_row("a", "b", n) for n in range(7)]
    graph: CountingMerging = (
        CountingMerging(PID_ONTOLOGY) if backend == "stand_in" else AdapterBacked(PID_ONTOLOGY)
    )
    await _load_pairs(graph, rows)
    (link,) = graph.stored_links()
    assert link["revision"] == 7 and link["occurrences"] == 7
    other: CountingMerging = (
        CountingMerging(PID_ONTOLOGY) if backend == "stand_in" else AdapterBacked(PID_ONTOLOGY)
    )
    with per_row():
        await _load_pairs(other, rows)
    (reference,) = other.stored_links()
    assert reference["revision"] == link["revision"]
    # And on top of a link an earlier load left: 7 and then 3 more.
    await _load_pairs(graph, [_pair_row("a", "b", n) for n in range(10, 13)], load="load-2")
    (merged,) = graph.stored_links()
    assert merged["revision"] == 10 and merged["occurrences"] == 10


# --- HOLDS ----------------------------------------------------------------------------------------


async def test_a_document_held_twice_by_one_holder_is_one_link_counted_for_each_hold() -> None:
    """A `HOLDS` link is buffered with the rest. Two rows of one holder carrying one text hold one
    document twice: one link, whose count of created links is per held write, as the per-row path
    gave it, and which the record names once."""
    rows = [
        {"phone": "07911123456", "item": "Shopping list: tape, ten bags."},
        {"phone": "07911123456", "item": "Shopping list: tape, ten bags."},
    ]
    outcomes = []
    for combine in (True, False):
        graph = CountingMerging(PID_ONTOLOGY)
        tx = await graph.begin_transaction()
        with per_row() if not combine else _plain():
            report, _ = await run_recipe(
                _held_recipe(),
                rows,
                graph=graph,  # type: ignore[arg-type]
                ontology=PID_ONTOLOGY,
                tx=tx,
                principal=LOADER,
                load_id="load-h",
                investigation_scope="case-1",
                source="export.csv",
                media=InMemoryMediaStore(),
                scheme=SCHEME,
            )
        await graph.commit_transaction(tx)
        holds = [e for e in graph.committed_edges if e.type == "HOLDS"]
        outcomes.append(
            (
                len(holds),
                holds[0].occurrences,
                report.edges_created,
                len(report.touched_edge_ids),
                len(report.created_edge_ids),
                graph.edge_calls,
            )
        )
    combined, reference = outcomes
    assert combined[:5] == reference[:5] == (1, 2, 2, 1, 1)
    assert combined[5] == [1] and reference[5] == [1, 1]


# --- helpers --------------------------------------------------------------------------------------

SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1")
_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}


@contextmanager
def _plain() -> Iterator[None]:
    yield


def _endpoint(ref: str, column: str) -> dict[str, Any]:
    return {
        "ref": ref,
        "pole_class": "object",
        "type": "Endpoint",
        "match_on": "value_normalised",
        "on_match": "reference",
        "properties": {
            "value_raw": {"field": column},
            "value_normalised": {"field": column},
            "endpoint_kind": {"literal": "handle"},
        },
    }


def _pair_recipe() -> Recipe:
    """Two handles and a call between them, at a duration, no time (so no event)."""
    return Recipe.model_validate(
        {
            "id": "pairs",
            "version": 1,
            "label": "Pairs",
            "connector": {"profile": "csv"},
            "ontology_version": PID_ONTOLOGY.version,
            "pack_versions": {},
            "defaults": {"provenance": {"state": "asserted"}, "handling": _HANDLING},
            "row_template": {
                "entities": [_endpoint("a", "from"), _endpoint("b", "to")],
                "edges": [
                    {
                        "type": "COMMUNICATED_WITH",
                        "from": "a",
                        "to": "b",
                        "properties": {"duration_s": {"field": "duration"}},
                    }
                ],
            },
        }
    )


def _held_recipe() -> Recipe:
    return Recipe.model_validate(
        {
            "id": "held",
            "version": 1,
            "label": "Phone extraction",
            "connector": {"profile": "csv"},
            "ontology_version": PID_ONTOLOGY.version,
            "pack_versions": {},
            "defaults": {"provenance": {"state": "asserted"}, "handling": _HANDLING},
            "row_template": {
                "entities": [
                    {
                        "ref": "phone",
                        "pole_class": "object",
                        "type": "Endpoint",
                        "match_on": "value_normalised",
                        "on_match": "reference",
                        "properties": {
                            "value_raw": {"field": "phone"},
                            "value_normalised": {"field": "phone", "transform": "msisdn"},
                            "endpoint_kind": {"literal": "msisdn"},
                        },
                        "content": {"kind": "document_text", "field": "item"},
                    }
                ]
            },
        }
    )


def _pair_row(source: str, target: str, n: int) -> dict[str, str]:
    return {"from": source, "to": target, "duration": str(10 + n)}


async def _load_pairs(
    graph: MergingGraph,
    rows: list[dict[str, str]],
    *,
    scheme: Any = SCHEME,
    load: str = "load-1",
) -> Any:
    report, _events, _held = await load_with_rules(
        _pair_recipe(),
        rows,
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=PID_ONTOLOGY,
        load_id=load,
        investigation_scope="case-1",
        source="pairs.csv",
        media=InMemoryMediaStore(),
        rules=None,
        scheme=scheme,
    )
    return report
