"""The Prison Intelligence Dataset's monitoring batches (`spec/06_DECISIONS.md` ADR-127 Amendment 41;
`packages/demo_fixtures/pid_monitoring.py`): the week's visit bookings (P2) and PIN first contacts
(P1), derived from the plan, with no store. What each case would catch:

- a batch that differs between two runs, which no golden test could hold —
  `test_the_batches_are_the_same_every_time`;
- a batch writing a link the seed already holds, so the load merges into it and the rehearsal reset
  refuses to revert it (ADR-127 decision 6) — `test_every_link_the_batches_write_is_new`;
- a first contact with a number some seized SIM called, which the P1 rule would flag beside the
  storyline's (the golden test's "exactly one alert" would then be two) —
  `test_only_the_story_number_is_within_two_steps_of_a_handset`;
- a booking giving a number the P1 rule or the chapter-9 hotlist would see, other than the
  storyline's — `test_the_bookings_touch_no_number_the_rule_would_flag`;
- a story row moved or lost — `test_the_story_rows_are_the_amendments`;
- a batch written somewhere the listing shows, or without its six handling columns —
  `test_the_batches_are_written_under_incoming_with_their_handling_columns`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from demo_fixtures import pid_files, pid_monitoring, pid_plan
from knowledge_adapters import REGISTRY

PLAN = pid_plan.build_plan("demo")


def _kind(key: str) -> str:
    return str(PLAN.entity(key).properties.get("endpoint_kind", ""))


def _by_value() -> dict[str, str]:
    """Each outside number's and PIN account's plan key, by the value a row writes."""
    out: dict[str, str] = {}
    for e in PLAN.entities:
        if _kind(e.key) == "msisdn":
            out[str(e.properties["value_normalised"])] = e.key
        elif _kind(e.key) == "handle":
            out[str(e.properties["handle"])] = e.key
    return out


def _msisdn(raw: str) -> str:
    return str(REGISTRY["msisdn"](raw))


def _two_steps_from_a_device() -> set[str]:
    """Every node within two links of a `Device` in the whole plan, every moment's links included:
    the reach of the P1 rule's `within_steps` relationship."""
    neighbours: dict[str, set[str]] = {}
    for lk in PLAN.links:
        neighbours.setdefault(lk.source, set()).add(lk.target)
        neighbours.setdefault(lk.target, set()).add(lk.source)
    devices = {e.key for e in PLAN.entities if e.entity_type == "Device"}
    one = {n for d in devices for n in neighbours.get(d, set())}
    return one | {n for o in one for n in neighbours.get(o, set())}


def test_the_batches_are_the_same_every_time(tmp_path: Path) -> None:
    again = pid_plan.build_plan("demo")
    for file in (pid_monitoring.VISIT_BOOKINGS, pid_monitoring.PIN_NEW_CONTACTS):
        assert pid_monitoring.rows_of(PLAN, file) == pid_monitoring.rows_of(again, file)
    first = pid_monitoring.write_batches(PLAN, tmp_path / "a")
    second = pid_monitoring.write_batches(again, tmp_path / "b")
    assert [(b.name, b.sha256) for b in first] == [(b.name, b.sha256) for b in second]
    assert pid_monitoring.rows_of(pid_plan.build_plan("scale"), pid_monitoring.VISIT_BOOKINGS) == []


def test_every_link_the_batches_write_is_new() -> None:
    by_value = _by_value()
    called = {
        (lk.source, lk.target)
        for lk in PLAN.links
        if lk.link_type == "COMMUNICATED_WITH" and _kind(lk.source) == "handle"
    }
    pairs = [
        (by_value[row["pin_account"]], by_value[_msisdn(row["called_number"])])
        for row in pid_monitoring.new_contact_rows(PLAN)
    ]
    assert pairs and not set(pairs) & called, "a first contact the call log already holds"
    refs = [row["booking_ref"] for row in pid_monitoring.booking_rows(PLAN)]
    assert len(refs) == len(set(refs)) == 8, "each booking is a record of its own"
    assert not {e.properties.get("message_id") for e in PLAN.entities} & set(refs)


def test_only_the_story_number_is_within_two_steps_of_a_handset() -> None:
    by_value = _by_value()
    near = _two_steps_from_a_device()
    numbers = {by_value[_msisdn(r["called_number"])] for r in pid_monitoring.new_contact_rows(PLAN)}
    flagged = {n for n in numbers if n in near}
    assert flagged == {pid_monitoring.UNIDENTIFIED_NUMBER}
    # It is within two steps through the SIM seized with Pryce's handset, and no other path.
    assert pid_monitoring.UNIDENTIFIED_NUMBER in near
    assert pid_monitoring.COORDINATOR_NUMBER not in numbers


def test_the_bookings_touch_no_number_the_rule_would_flag() -> None:
    by_value = _by_value()
    near = _two_steps_from_a_device()
    rows = pid_monitoring.booking_rows(PLAN)
    contacts = [by_value[_msisdn(r["contact_number"])] for r in rows]
    story = [c for c in contacts if c == pid_monitoring.COORDINATOR_NUMBER]
    assert len(story) == 1, "the coordinator's number is given once, in the storyline's booking"
    # The coordinator's is within two steps of the batch-2 handset (chapter 9): the reason the rule
    # is deployed after the bookings load. No background booking's number is.
    assert {c for c in contacts if c in near} == {pid_monitoring.COORDINATOR_NUMBER}


def test_the_story_rows_are_the_amendments() -> None:
    bookings = pid_monitoring.booking_rows(PLAN)
    story = next(r for r in bookings if r["visitor_nino"] == "QQ336199B")
    assert (story["booking_ref"], story["nomis_id"], story["contact_number"]) == (
        "VB-2605-001", "Z2558ZZ", "07700 900640")  # fmt: skip
    assert story["title"] == "Visit booking VB-2605-001: social visit on Saturday 9 May 2026 at 14:00"
    visit = datetime.fromisoformat(story["visit_at"])
    assert all(datetime.fromisoformat(r["booked_at"]) < visit for r in bookings), (
        "the visit is after every booking in the file, so the load's alert comes before it"
    )
    calls = pid_monitoring.new_contact_rows(PLAN)
    assert len(calls) == 14
    darren = [r for r in calls if r["pin_account"] == "PIN-Z2558ZZ"]
    assert [(r["called_number"], r["call_start"], r["duration_s"]) for r in darren] == [
        ("07700 900718", "2026-05-05T18:42:00+00:00", "312"),
        ("07700 900718", "2026-05-07T19:05:00+00:00", "95"),
    ]
    for row in [*bookings, *calls]:
        at = datetime.fromisoformat(row.get("booked_at") or row["call_start"]).date()
        assert pid_monitoring.WEEK_START <= at <= pid_monitoring.WEEK_END


def test_the_batches_are_written_under_incoming_with_their_handling_columns(tmp_path: Path) -> None:
    report = pid_files.write_files(PLAN, tmp_path)
    names = {f.name for f in report.files}
    assert {"incoming/pid_visit_bookings.csv", "incoming/pid_pin_new_contacts.csv"} <= names
    for file in (pid_monitoring.VISIT_BOOKINGS, pid_monitoring.PIN_NEW_CONTACTS):
        header = (tmp_path / "incoming" / file).read_text(encoding="utf-8").splitlines()[0]
        assert set(pid_plan.HANDLING_COLUMNS) <= set(header.split(","))
        assert pid_files.header_for(file) == header.split(",")
        assert not (tmp_path / file).exists(), "out of the listing until chapter 9"
