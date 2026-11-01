"""Recipes R18 (`pid-visit-bookings`) and R19 (`pid-pin-new-contacts`), the loads of chapter 9's two
monitoring batches (`spec/06_DECISIONS.md` ADR-127 Amendment 41), held to their files. Every
expectation is derived from `pid_monitoring` and the plan, never typed; each file is loaded by
`load_with_rules` through its committed recipe on the golden tests' graph stand-in, after the seed's
files it finds by reference, in the seed's order. What a mistake would do, and the case that catches
it:

- a booking written as anything but a new record the visitor, the prisoner and the number are
  mentioned in — a `VISITED` for a visit that has not happened, a second visitor, a contact number
  made anew instead of found — `test_each_booking_is_a_new_record_naming_the_visitor_the_prisoner_and_the_number`;
- a first contact written as anything but one new `COMMUNICATED_WITH` per pair, timed at its calls,
  from the account R5 made — or a `USES` merged into R5's link, so the reset could not revert it —
  `test_each_first_contact_is_a_new_link_from_the_account_r5_made`;
- either load merging into a link the seed made (ADR-127 decision 6) —
  `test_neither_load_merges_into_a_link_it_did_not_create`;
- either file loaded twice writing twice (decision 5) — `test_a_second_run_of_each_creates_nothing`;
- a row's marking not its own handling columns' — `test_every_element_carries_its_rows_marking`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from demo_fixtures import pid_monitoring
from tests.ingest.pid_golden_support import (
    PLAN,
    Step,
    load,
    loaded,
    marking,
    msisdn,
    row_marking,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import Sink

BOOKINGS = pid_monitoring.VISIT_BOOKINGS
CONTACTS = pid_monitoring.PIN_NEW_CONTACTS
CALLS = "pid_pin_calls.csv"


def _calls_on(accounts: set[str]) -> Step:
    """The call file's rows on the accounts the first contacts name, whole: R5 makes each account
    and ties it to its prisoner; the numbers called are found by R16 or made by these rows."""
    rows = tuple(r for r in rows_of(CALLS) if r["pin_account"] in accounts)
    return Step(CALLS, rows, lambda row: row.values["pin_account"] in accounts)


def _before() -> list[str | Step]:
    accounts = {r["pin_account"] for r in pid_monitoring.new_contact_rows(PLAN)}
    return [
        "pid_establishment_plan.csv",
        "pid_nomis_prisoners.csv",
        "pid_nomis_visits.csv",
        "pid_number_owners.csv",
        _calls_on(accounts),
    ]


@pytest.fixture
async def world() -> Any:
    graph, store, _ = await loaded(*_before())
    before_edges = {e.id for e in graph.committed_edges}
    reports = {}
    for file in (BOOKINGS, CONTACTS):
        report, _events = await load(graph, file, Sink(store, "pid-case"))
        assert report.rejections == [], (file, report.rejections[:3])
        reports[file] = report
    return graph, store, reports, before_edges


def _by(graph: MergingGraph, prop: str, value: str) -> Any:
    (found,) = [n for n in graph.live_nodes.values() if str(n.properties.get(prop)) == value]
    return found


def _rows(file: str) -> Iterator[dict[str, str]]:
    yield from rows_of(file)


async def test_each_booking_is_a_new_record_naming_the_visitor_the_prisoner_and_the_number(
    world: Any,
) -> None:
    graph, _store, reports, _before_edges = world
    for row in _rows(BOOKINGS):
        booking = _by(graph, "message_id", row["booking_ref"])
        assert booking.type == "Document" and booking.properties["title"] == row["title"]
        assert booking.properties["sent_at"] == row["booked_at"]
        mentioned = {e.source for e in graph.committed_edges
                     if e.type == "MENTIONED_IN" and e.target == booking.id}  # fmt: skip
        expected = {
            _by(graph, "nino", row["visitor_nino"]).id,
            _by(graph, "prison_number", row["nomis_id"]).id,
            _by(graph, "value_normalised", msisdn(row["contact_number"])).id,
        }
        assert mentioned == expected, row["booking_ref"]
    report = reports[BOOKINGS]
    assert report.nodes_created == 8, "the eight bookings, and no person or number made anew"
    assert report.edges_created == 24
    assert not [e for e in graph.committed_edges if e.type == "VISITED" and e.load_id == report.load_id]


async def test_each_first_contact_is_a_new_link_from_the_account_r5_made(world: Any) -> None:
    graph, _store, reports, before_edges = world
    pairs: dict[tuple[str, str], list[str]] = {}
    for row in _rows(CONTACTS):
        pairs.setdefault((row["pin_account"], msisdn(row["called_number"])), []).append(
            row["call_start"]
        )
    report = reports[CONTACTS]
    assert report.edges_created == len(pairs) == 11
    for (account, number), starts in pairs.items():
        source, target = _by(graph, "value_normalised", account), _by(graph, "value_normalised", number)
        (link,) = [e for e in graph.committed_edges if e.type == "COMMUNICATED_WITH"
                   and (e.source, e.target) == (source.id, target.id)]  # fmt: skip
        assert link.id not in before_edges and link.occurrences == len(starts)
        assert link.interval is not None
        assert link.interval.valid_from.isoformat() == min(starts)
        held = [e for e in graph.committed_edges if e.type == "USES" and e.target == source.id]
        assert len(held) == 1 and held[0].id in before_edges, "the account R5 tied to its prisoner"


async def test_neither_load_merges_into_a_link_it_did_not_create(world: Any) -> None:
    _graph, _store, reports, _before_edges = world
    for file in (BOOKINGS, CONTACTS):
        report = reports[file]
        assert report.merged_edge_ids == [] and report.merged_node_ids == [], file


async def test_a_second_run_of_each_creates_nothing(world: Any) -> None:
    graph, store, _reports, _before_edges = world
    for file, rows in ((BOOKINGS, 8), (CONTACTS, 14)):
        report, events = await load(graph, file, Sink(store, "pid-case"), load_id=f"again-{file}")
        assert (report.nodes_created, report.edges_created, len(events)) == (0, 0, 0), file
        assert report.rows_already_loaded == rows


async def test_every_element_carries_its_rows_marking(world: Any) -> None:
    graph, _store, reports, _before_edges = world
    for file in (BOOKINGS, CONTACTS):
        report = reports[file]
        made = {e.id: e for e in graph.committed_edges if e.load_id == report.load_id}
        marks = {row_marking(r) for r in _rows(file)}
        assert made and {marking(e.handling) for e in made.values()} <= marks, file
    for row in _rows(BOOKINGS):
        assert marking(_by(graph, "message_id", row["booking_ref"]).handling) == row_marking(row)
