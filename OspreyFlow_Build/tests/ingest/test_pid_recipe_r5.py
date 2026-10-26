"""R5, `pid-pin-calls` (ADR-127 decision 12): the prison PIN phone calls, on Brief 1's real file, in
the `pin-calls-csv` layout (ISO-8601 instants with their offset, no `date_order`), loaded after R11,
R1, R3 and R16 as the seed does, so a number a visitor owns is the one node. Every expectation comes
from `pid_plan`.

**The demo profile's file holds about 100,000 rows** (ADR-120 Amendment 17; 100,080 with the
planted duplicates). This test loads a slice of it (`pin_calls_slice`), which keeps the case quick:
every row of every link (one PIN account to one number) that holds a planted duplicate, that ends
at the coordinator's number, or that ends at one of the first three numbers the file writes in
other forms;
plus, for each number in the slice, the link its first row sits on (so the raw form kept is the
plan's). A slice holds each link whole, so the plan's own counts for those links are exact. The
slice's size is asserted against the plan, not typed. The whole-file run is the coordinator's, on a
quiet stack.

**What the layout does not do (Amendment 18).** The duplicate key is the PIN account, the number
through `msisdn`, the instant through `datetime` and `duration_s`, each as the file writes it. No
existing Knowledge Adapter trims and upper-cases a PIN account without also removing inner spaces
(`account_ref` does both), and none reads a duration as an integer, so those two parts are the
cell's text; this file writes them in one form, which
`test_the_file_writes_pin_accounts_and_durations_in_one_form` records.

What a mistake would do, and the case that catches it:

- a planted duplicate loaded twice, or a same-call-different-sequence row not folded, or a call of
  another duration folded: the key must canonicalise the number and the instant and hold the
  duration but not the sequence (`test_the_planted_duplicates_fold`,
  `test_a_repeat_under_a_new_sequence_folds_and_a_changed_duration_does_not`);
- a number written in another form making a second `Endpoint`, or not the one a visitor owns
  (`test_pid_phone_variants_collapse_to_one_endpoint`);
- a PIN account or number not as the plan holds it, or a prisoner not using their PIN
  (`test_every_pin_and_number_is_one_endpoint_as_the_plan_holds_it`);
- a call lost, or not at its exact time, or its link not the plan's
  (`test_every_call_is_a_communicated_with_link_at_its_time`);
- an element at a marking other than the first creating row's, as the plan's rows replayed in the
  seed's order give it (`test_every_element_carries_the_marking_its_first_row_gives`);
- a re-run adding anything (`test_a_second_run_creates_nothing`)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from demo_fixtures import pid_files
from tests.ingest.pid_golden_support import (
    CALLS,
    CASE,
    COORDINATOR_NUMBER,
    PLAN,
    assert_exact_instants,
    assert_loaded_markings,
    is_national,
    keys_in,
    load,
    loaded,
    msisdn,
    pin_call_of,
    pin_calls_slice,
    pin_calls_slice_step,
    pin_link_of,
    replay,
    rows_of,
)
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)
from tests.ingest.test_row_keys import Sink

FILE = CALLS
BEFORE = (
    "pid_establishment_plan.csv",
    "pid_nomis_prisoners.csv",
    "pid_nomis_visits.csv",
    "pid_number_owners.csv",
)


def _slice() -> list[dict[str, str]]:
    return list(pin_calls_slice()[0])


def _planned(kind: str) -> dict[tuple[str, str], Any]:
    """The plan's links of one type that the slice's links are, keyed by (PIN account, number) for a
    call link and (prisoner number, PIN account) for a PIN link."""
    wanted = {pin_link_of(r) for r in _slice()}
    prisoners = {r["nomis_id"] for r in _slice()}
    out = {}
    _, link_keys = keys_in(FILE)
    keep = set(link_keys)
    for lk in PLAN.links:
        if lk.key not in keep or lk.link_type != kind:
            continue
        src, tgt = PLAN.entity(lk.source), PLAN.entity(lk.target)
        if kind == "COMMUNICATED_WITH":
            pair = (str(src.properties["handle"]), str(tgt.properties["value_normalised"]))
            if pair in wanted:
                out[pair] = lk
        else:
            pair = (str(src.properties["prison_number"]), str(tgt.properties["handle"]))
            if pair[0] in prisoners:
                out[pair] = lk
    return out


@pytest.fixture(scope="module")
async def calls() -> dict[str, Any]:
    graph, store, _ = await loaded(*BEFORE)
    before = {n.id for n in graph.committed_nodes}
    report, events = await load(graph, FILE, Sink(store, CASE), rows=_slice())
    assert report.rejections == [], report.rejections[:3]
    return {"graph": graph, "store": store, "report": report, "events": events, "before": before}


def _label(graph: MergingGraph) -> dict[str, str]:
    out = {}
    for n in graph.committed_nodes:
        for name in ("handle", "value_normalised", "prison_number", "nino"):
            if name in n.properties:
                out[n.id] = str(n.properties[name])
                break
    return out


async def test_the_slice_is_whole_links_and_its_size_is_the_plans(calls: dict[str, Any]) -> None:
    planned = _planned("COMMUNICATED_WITH")
    assert {pin_link_of(r) for r in _slice()} == set(planned)
    planted = pid_files.EXACT_DUPLICATES + pid_files.SEQUENCE_DUPLICATES
    assert len(_slice()) == sum(lk.occurrences for lk in planned.values()) + planted
    by_call = Counter(pin_call_of(r) for r in _slice())
    assert sum(n - 1 for n in by_call.values()) == planted, "the slice holds every planted row"
    assert len(planned) >= 77


def test_the_file_writes_pin_accounts_and_durations_in_one_form() -> None:
    """The recipe's key holds `pin_account` and `duration_s` as written (no existing transform
    trims and upper-cases a PIN account alone, or reads a duration as an integer), which is sound
    only while the file writes each one way. This holds the file to it: if it ever writes `pin-x`
    beside `PIN-X`, or `60` beside `060`, this fails, and the key needs the transform."""
    rows = rows_of(FILE)
    assert all(r["pin_account"] == r["pin_account"].strip().upper() for r in rows)
    assert all(r["duration_s"] == str(int(r["duration_s"])) for r in rows)


async def test_the_planted_duplicates_fold(calls: dict[str, Any]) -> None:
    """Forty rows copy an earlier row byte for byte and forty repeat an earlier call under a new
    sequence number. All eighty fold into the call they repeat (`rows_deduplicated`), never a second
    call, and not an `already loaded` row (that is a re-run)."""
    report, events = calls["report"], calls["events"]
    planted = pid_files.EXACT_DUPLICATES + pid_files.SEQUENCE_DUPLICATES
    rows = _slice()
    assert report.rows_deduplicated == planted == 80
    assert report.rows_already_loaded == 0
    assert report.rows_read == len(rows)
    assert len(events) == len(rows) - planted == len({pin_call_of(r) for r in rows})
    sequences: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for r in rows:
        sequences[pin_call_of(r)].append(r["sequence"])
    assert sum(1 for s in sequences.values() if len(set(s)) > 1) == pid_files.SEQUENCE_DUPLICATES, (
        "a repeat under a new sequence number is in the slice for each one the file plants"
    )
    assert sum(len(s) - len(set(s)) for s in sequences.values()) == pid_files.EXACT_DUPLICATES, (
        "a row copied byte for byte is in the slice for each one the file plants"
    )


async def test_a_repeat_under_a_new_sequence_folds_and_a_changed_duration_does_not() -> None:
    """The key leaves `sequence` out and holds `duration_s`: a row repeated under a new sequence
    number is the call it repeats, and a row at the same instant with another duration is another
    call (two calls between a pair at one second are two calls). Its own graph, so the module's is
    not touched."""
    graph, store, _ = await loaded(*BEFORE)
    base = _slice()[0]
    repeat = {**base, "sequence": "9000001"}
    exact = dict(base)
    longer = {**base, "duration_s": str(int(base["duration_s"]) + 1), "sequence": "9000002"}
    report, events = await load(
        graph, FILE, Sink(store, CASE), "load-folds", rows=[base, repeat, exact, longer]
    )
    assert report.rejections == []
    assert report.rows_deduplicated == 2, (
        "the repeat and the exact copy fold; the longer call does not"
    )
    assert len(events) == 2
    link = next(
        e
        for e in graph.committed_edges
        if e.type == "COMMUNICATED_WITH" and e.id in set(report.touched_edge_ids)
    )
    assert link.occurrences == 2


async def test_pid_phone_variants_collapse_to_one_endpoint(calls: dict[str, Any]) -> None:
    """Brief 2 section 8. The slice writes numbers in all four forms; each number is one node, whose
    raw form is the one it was first written in, which is the plan's `value_raw`."""
    graph = calls["graph"]
    forms = {r["called_number"] for r in _slice() if not is_national(r["called_number"])}
    assert (
        forms
        and any(f.startswith("+44 ") for f in forms)
        and any(f.startswith("0044 ") for f in forms)
    )
    assert any(f.startswith("44") for f in forms), "the bare 44 form"
    msisdns = [
        n
        for n in graph.committed_nodes
        if n.type == "Endpoint" and n.properties.get("endpoint_kind") == "msisdn"
    ]
    normalised = [str(n.properties["value_normalised"]) for n in msisdns]
    assert len(normalised) == len(set(normalised)), "a number is two Endpoints"
    stored = {str(n.properties["value_normalised"]): n for n in msisdns}
    written = {msisdn(r["called_number"]) for r in _slice()}
    assert written <= set(stored)
    for entity in (PLAN.entity(lk.target) for lk in _planned("COMMUNICATED_WITH").values()):
        node = stored[str(entity.properties["value_normalised"])]
        assert node.properties == dict(entity.properties), entity.key
        assert node.properties["value_raw"] == entity.properties["value_raw"]
        assert is_national(str(node.properties["value_raw"])), (
            "first written form is the national one"
        )
    assert any(
        len({r["called_number"] for r in _slice() if msisdn(r["called_number"]) == number}) > 1
        for number in written
    ), "a number written more than one way is in the slice"


async def test_the_coordinators_number_is_the_node_r16_made(calls: dict[str, Any]) -> None:
    graph = calls["graph"]
    coordinator = [
        n
        for n in graph.committed_nodes
        if n.properties.get("value_normalised") == COORDINATOR_NUMBER
    ]
    assert len(coordinator) == 1
    assert coordinator[0].id in calls["before"], "R5 made the coordinator's number again"
    assert any(
        e.target == coordinator[0].id and e.type == "COMMUNICATED_WITH"
        for e in graph.committed_edges
    )
    assert coordinator[0].handling.owning_unit == "regional-intel-unit"


async def test_every_pin_and_number_is_one_endpoint_as_the_plan_holds_it(
    calls: dict[str, Any],
) -> None:
    graph, report = calls["graph"], calls["report"]
    planned_calls = _planned("COMMUNICATED_WITH")
    handles = {
        str(PLAN.entity(lk.source).properties["handle"]): PLAN.entity(lk.source)
        for lk in planned_calls.values()
    }
    stored = {
        str(n.properties["handle"]): n
        for n in graph.committed_nodes
        if n.type == "Endpoint" and "handle" in n.properties
    }
    assert set(stored) == set(handles)
    for handle, entity in handles.items():
        assert stored[handle].properties == dict(entity.properties), handle
        assert stored[handle].properties["endpoint_kind"] == "handle"
    numbers = {msisdn(r["called_number"]) for r in _slice()}
    new_numbers = len(
        [n for n in graph.committed_nodes if n.type == "Endpoint" and n.id not in calls["before"]]
    ) - len(handles)
    assert report.nodes_created == len(handles) + new_numbers
    assert new_numbers == len(numbers) - len(
        [
            n
            for n in graph.committed_nodes
            if n.id in calls["before"] and n.properties.get("value_normalised") in numbers
        ]
    )
    names = _label(graph)
    used = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "USES" and names.get(e.target) in handles
    }
    planned_uses = _planned("USES")
    assert set(used) == set(planned_uses)
    per_prisoner = Counter(r["nomis_id"] for r in {pin_call_of(r): r for r in _slice()}.values())
    for pair, lk in planned_uses.items():
        assert used[pair].properties == dict(lk.properties) == {}, pair
        assert used[pair].occurrences == per_prisoner[pair[0]] <= lk.occurrences, pair


async def test_every_call_is_a_communicated_with_link_at_its_time(calls: dict[str, Any]) -> None:
    graph, events = calls["graph"], calls["events"]
    names = _label(graph)
    stored = {
        (names[e.source], names[e.target]): e
        for e in graph.committed_edges
        if e.type == "COMMUNICATED_WITH" and names.get(e.source, "").startswith("PIN-")
    }
    planned = _planned("COMMUNICATED_WITH")
    assert set(stored) == set(planned)
    instants: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for event in events:
        instants[(names[event.source_id], names[event.target_id])].append(event.occurred_at)
    for pair, lk in planned.items():
        edge = stored[pair]
        seen = sorted(instants[pair])
        assert edge.properties == dict(lk.properties) == {}, pair
        assert edge.occurrences == lk.occurrences == len(seen), pair
        assert_exact_instants(lk, seen)
        assert edge.interval is not None
        assert (edge.interval.valid_from, edge.interval.valid_to) == (seen[0], seen[-1]), pair
    # Every event is at the `call_start` of the first row of a distinct call, to the second.
    first_of_call: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in _slice():
        first_of_call.setdefault(pin_call_of(row), row)
    assert sorted(e.occurred_at for e in events) == sorted(
        datetime.fromisoformat(r["call_start"]) for r in first_of_call.values()
    )


async def test_every_element_carries_the_marking_its_first_row_gives(
    calls: dict[str, Any],
) -> None:
    """ADR-127 Amendment 18: an element several rows name is created at the marking of the first
    row, in the seed's load order, that creates it. The plan's own rows are replayed in that order
    (R11, R1, R3, R16, then the slice), through the store's merge rule for a link, and every node
    and link stored is held to the result. Nothing is typed here."""
    graph = calls["graph"]
    assert_loaded_markings(graph, replay(*BEFORE, pin_calls_slice_step()))


async def test_the_same_call_written_another_way_is_the_same_call(calls: dict[str, Any]) -> None:
    """The duplicate key canonicalises before it hashes (`01_DOMAIN_MODEL.md` §7 rule 2): the same
    call with its number in another form and its start at the same instant under another offset is
    the call already kept, whatever the file's planted duplicates happen to look like."""
    graph, store = calls["graph"], calls["store"]
    originals = [r for r in _slice() if is_national(r["called_number"])][:3]
    rewritten = []
    for form, row in enumerate(originals):
        digits = "".join(c for c in row["called_number"] if c.isdigit())
        number = (
            f"+44 {row['called_number'][1:]}",
            f"0044 {row['called_number'][1:]}",
            f"44{digits[1:]}",
        )[form]
        start = datetime.fromisoformat(row["call_start"]).astimezone(timezone(timedelta(hours=1)))
        rewritten.append({**row, "called_number": number, "call_start": start.isoformat()})
    assert all(
        r["called_number"] != o["called_number"] for r, o in zip(rewritten, originals, strict=True)
    )
    assert all(
        r["call_start"] != o["call_start"] for r, o in zip(rewritten, originals, strict=True)
    )
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    report, events = await load(graph, FILE, Sink(store, CASE), "load-forms", rows=rewritten)
    assert report.rejections == []
    assert report.rows_already_loaded == 3
    assert (report.nodes_created, report.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before


async def test_a_second_run_creates_nothing(calls: dict[str, Any]) -> None:
    graph, store = calls["graph"], calls["store"]
    before = (len(graph.committed_nodes), len(graph.committed_edges))
    second, events = await load(graph, FILE, Sink(store, CASE), "load-2", rows=_slice())
    # Every row's key is now kept, the folded ones too (they share their survivor's key).
    assert second.rows_already_loaded == len(_slice())
    assert second.rows_deduplicated == 0
    assert (second.nodes_created, second.edges_created, events) == (0, 0, [])
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == before
