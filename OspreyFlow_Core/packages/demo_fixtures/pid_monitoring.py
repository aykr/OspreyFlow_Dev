"""The Prison Intelligence Dataset's monitoring batches (`06_DECISIONS.md` ADR-127 Amendment 41;
`process/ALERTING_MONITORING_PLAN.md`, use cases P1 and P2; rule 9: synthetic, in-repo, never real).

Two files arrive after the second seized-phone batch, in chapter 9, the week after the plan's
cut-off (Monday 4 to Sunday 10 May 2026). Both are derived from `pid_plan.build_plan` and drawn from
`random.Random` seeded by the plan's own seed, so they are the same on every run; like the
seed's files they are pure (standard library, no clock, no environment) until `write_batches`
writes them.

- **`pid_visit_bookings.csv` (P2).** The week's visit bookings, one row per booking: the visitor
  (by National Insurance number), the prisoner (by prison number), the visit's date and time, the
  contact number the visitor gave, and the booking reference. Recipe R18 (`pid-visit-bookings`)
  loads each as a booking record (a `Document`) that the visitor, the prisoner and the contact
  number are `MENTIONED_IN`; it writes no `VISITED`, because a booked visit has not happened. One
  row is the storyline's: Marcus Ellery, the outside coordinator, books a visit to Darren Ashcombe
  on Saturday 9 May at 14:00 and gives 07700 900640, the number the analyst hotlisted in chapter 9.
  The other bookers are background visitors, each giving the number they own.
- **`pid_pin_new_contacts.csv` (P1).** The week's PIN calls to numbers each account had not called
  before (the supplier's first-contact extract), one row per call, in the call log's own columns.
  Recipe R19 (`pid-pin-new-contacts`) writes each call as a `COMMUNICATED_WITH` from the PIN account
  (found by reference) to the number. One account's calls are the storyline's: Darren Ashcombe's PIN
  account calls 07700 900718 twice, the number nobody owns, which Jamie Pryce's seized handset
  called 30 times. The other calls are background prisoners' first contacts with numbers no seized
  SIM ever called.

**Every link a batch writes is new**, so the rehearsal reset can revert each load (ADR-127 decision
6 refuses a load that merged into a link it did not create): a booking is a new `Document`, and
each first contact is a pair (account, number) the plan holds no call for. A test holds this.

**What each batch must raise** is `EXPECTED_ALERTS`, in order, once the analyst has hotlisted the
coordinator's number (chapter 9) and deployed `P1_SENTENCE` after the bookings load; the golden
tests (`tests/scenarios/test_pid_monitoring_storyline.py`) load the batches through the committed
recipes and assert exactly these.
"""

from __future__ import annotations

import csv
import hashlib
import random
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .pid_plan import HANDLING_COLUMNS, LOCAL, REGIONAL, Moment, Plan, PlanHandling, cell_text

#: The two files, written under `incoming/` beside the second seized-phone batch.
VISIT_BOOKINGS = "pid_visit_bookings.csv"
PIN_NEW_CONTACTS = "pid_pin_new_contacts.csv"
INCOMING = "incoming"
BOOKINGS_RECIPE = "pid_visit_bookings_recipe.yaml"
NEW_CONTACTS_RECIPE = "pid_pin_new_contacts_recipe.yaml"

#: The week the batches cover: the Monday after the plan's cut-off (30 April 2026), to its Sunday.
WEEK_START = date(2026, 5, 4)
WEEK_END = date(2026, 5, 10)

#: The storyline's keys in the plan.
COORDINATOR = "coordinator"
THIRD_MEMBER = "third_member"
COORDINATOR_NUMBER = "number:coordinator"
UNIDENTIFIED_NUMBER = "number:unidentified"
PRYCE_HANDSET = "handset:pryce"

#: P2's booking: Marcus Ellery books an in-person visit to Darren Ashcombe for Saturday 9 May at
#: 14:00, on Monday 4 May at 10:17, and gives his own number as the contact.
STORY_BOOKED_AT = datetime(2026, 5, 4, 10, 17, tzinfo=UTC)
STORY_VISIT_AT = datetime(2026, 5, 9, 14, 0, tzinfo=UTC)
#: P1's calls: Darren Ashcombe's PIN account calls the number nobody owns, twice.
STORY_CALLS: tuple[tuple[datetime, int], ...] = (
    (datetime(2026, 5, 5, 18, 42, tzinfo=UTC), 312),
    (datetime(2026, 5, 7, 19, 5, tzinfo=UTC), 95),
)
#: How many background rows each batch carries beside the storyline's.
BACKGROUND_BOOKINGS = 7
BACKGROUND_CONTACTS = 10

BOOKINGS_HEADER = (
    "booking_ref", "booked_at", "visit_at", "visitor_nino", "visitor_family_name",
    "visitor_given_names", "nomis_id", "contact_number", "channel", "title", *HANDLING_COLUMNS,
)  # fmt: skip
#: The call log's own columns (`pid_files.header_for("pid_pin_calls.csv")`), so the same connector
#: profile reads both.
NEW_CONTACTS_HEADER = (
    "nomis_id", "pin_account", "called_number", "call_start", "duration_s", "direction",
    "sequence", *HANDLING_COLUMNS,
)  # fmt: skip

#: The rule the analyst writes as a sentence in chapter 9 (ADR-133 decision 1), deployed after the
#: bookings load: "When an Endpoint whose endpoint kind is msisdn is within 2 steps of a Device,
#: raise a high-severity alert for the case, after each load commits." A phone number is within
#: two steps of a handset only through a seized SIM that called it (`PAIRED_WITH` then
#: `COMMUNICATED_WITH`): no other path in the plan reaches a `Device` in two steps. Plain data, so
#: this module imports nothing; `schemas.sentences.RuleSentence` validates it.
P1_RULE_NAME = "Calls to a number on a seized handset"
P1_SENTENCE: Mapping[str, Any] = {
    "subject": "Endpoint",
    "conditions": [{"op": "equals", "property": "endpoint_kind", "value": "msisdn"}],
    "relationship": {"kind": "within_steps", "steps": 2, "other_type": "Device"},
    "severity": "high",
    "team": "case",
    "runs": "post_commit",
    "scope": "this_case",
}


@dataclass(frozen=True)
class MonitoringStage:
    """One chapter-9 load after the second seized-phone batch: its file, its recipe, its moment."""

    file: str
    recipe: str
    moment: Moment


#: The order the presenter loads them in chapter 9, after `pid_files.BATCH_2` (ADR-127 Amendment
#: 41): the bookings first, then — once the analyst has deployed `P1_SENTENCE` — the new contacts.
MONITORING_STAGES: tuple[MonitoringStage, ...] = (
    MonitoringStage(VISIT_BOOKINGS, BOOKINGS_RECIPE, "chapter9"),
    MonitoringStage(PIN_NEW_CONTACTS, NEW_CONTACTS_RECIPE, "chapter9"),
)


@dataclass(frozen=True)
class ExpectedAlert:
    """One alert chapter 9 raises: the file whose load raises it, its kind (`hotlist` or
    `sentence`), and the `value_normalised` of the number it names."""

    file: str
    kind: str
    number: str


#: Chapter 9's alerts, in the order they are raised: the second seized-phone batch and the bookings
#: each touch the coordinator's hotlisted number (H1, H2); the new contacts touch the number on
#: Pryce's seized handset, which the P1 rule flags (S1). Nothing else.
EXPECTED_ALERTS: tuple[ExpectedAlert, ...] = (
    ExpectedAlert("pid_seized_comms_batch2.csv", "hotlist", "+447700900640"),
    ExpectedAlert(VISIT_BOOKINGS, "hotlist", "+447700900640"),
    ExpectedAlert(PIN_NEW_CONTACTS, "sentence", "+447700900718"),
)


# --- Reading the plan ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _World:
    """What the batches are drawn from, read once from the plan."""

    #: PIN account key -> its prisoner's key.
    pin_owner: Mapping[str, str]
    #: Number key -> its owner's key (a visitor or the coordinator).
    number_owner: Mapping[str, str]
    #: (PIN account key, number key) pairs the call log already holds.
    called: frozenset[tuple[str, str]]
    #: Numbers a seized SIM called: within two steps of a handset.
    seized_numbers: frozenset[str]
    #: (visitor, prisoner) pairs of every visit, in plan order.
    visits: tuple[tuple[str, str], ...]
    #: Prisoners held at Fenwick Moor.
    fenwick: frozenset[str]


def _world(plan: Plan) -> _World:
    kind = {
        e.key: str(e.properties.get("endpoint_kind", ""))
        for e in plan.entities
        if e.entity_type == "Endpoint"
    }
    pin_owner: dict[str, str] = {}
    number_owner: dict[str, str] = {}
    called: set[tuple[str, str]] = set()
    seized: set[str] = set()
    visits: list[tuple[str, str]] = []
    fenwick: set[str] = set()
    for lk in plan.links:
        if lk.link_type == "USES" and kind.get(lk.target) == "handle":
            pin_owner[lk.target] = lk.source
        elif lk.link_type == "USES" and kind.get(lk.target) == "msisdn":
            number_owner[lk.target] = lk.source
        elif lk.link_type == "COMMUNICATED_WITH":
            if kind.get(lk.source) == "handle":
                called.add((lk.source, lk.target))
            elif kind.get(lk.source) == "imsi":
                seized.add(lk.target)
        elif lk.link_type == "VISITED":
            visits.append((lk.source, lk.target))
        elif lk.link_type == "HELD_AT" and lk.target == "est:fenwick-moor":
            fenwick.add(lk.source)
    return _World(
        pin_owner=pin_owner,
        number_owner=number_owner,
        called=frozenset(called),
        seized_numbers=frozenset(seized),
        visits=tuple(visits),
        fenwick=frozenset(fenwick),
    )


def _rng(plan: Plan, part: str) -> random.Random:
    digest = hashlib.sha256(f"{plan.seed}|monitoring|{part}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _cast(plan: Plan) -> frozenset[str]:
    from .pid_plan import CAST

    return frozenset(k for k in CAST if k in {e.key for e in plan.entities})


def _marking(handling: PlanHandling) -> dict[str, str]:
    return {
        "classification": handling.classification,
        "handling_code": handling.handling_code,
        "action_code": handling.action_code or "",
        "sanitisation_code": handling.sanitisation_code or "",
        "originator": handling.originator,
        "owning_unit": handling.owning_unit,
    }


def _row_marking(*handlings: PlanHandling) -> dict[str, str]:
    """A row is marked as the regional unit's when any element it names is, else the local unit's —
    the rule the plan's own call and visit rows follow."""
    return _marking(REGIONAL if any(h == REGIONAL for h in handlings) else LOCAL)


def _at(day: date, minute_of_day: int) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(minutes=minute_of_day)


# --- The visit bookings (P2) ---------------------------------------------------------------------


def _channel_words(channel: str) -> str:
    return {"in_person": "social visit", "video": "video call"}.get(channel, channel)


def _booking(
    plan: Plan,
    ref: str,
    visitor: str,
    prisoner: str,
    number: str,
    booked_at: datetime,
    visit_at: datetime,
    channel: str,
) -> dict[str, str]:
    who, held, phone = plan.entity(visitor), plan.entity(prisoner), plan.entity(number)
    return {
        "booking_ref": ref,
        "booked_at": cell_text(booked_at),
        "visit_at": cell_text(visit_at),
        "visitor_nino": str(who.properties["nino"]),
        "visitor_family_name": str(who.properties["family_name"]),
        "visitor_given_names": str(who.properties["given_names"]),
        "nomis_id": str(held.properties["prison_number"]),
        "contact_number": str(phone.properties["value_raw"]),
        "channel": channel,
        "title": (
            f"Visit booking {ref}: {_channel_words(channel)} on "
            f"{visit_at.strftime('%A')} {visit_at.day} {visit_at.strftime('%B %Y')} at "
            f"{visit_at.strftime('%H:%M')}"
        ),
        **_row_marking(who.handling, held.handling, phone.handling),
    }


def booking_rows(plan: Plan) -> list[dict[str, str]]:
    """The week's bookings, by when each was made: the storyline's, and `BACKGROUND_BOOKINGS`
    background visitors each booking a visit to a Fenwick Moor prisoner they have visited before,
    giving the number they own. No background visitor's number is one a seized SIM called, so the
    bookings touch no number the P1 rule would flag, and none is the coordinator's."""
    if plan.profile != "demo":
        return []
    world = _world(plan)
    owned = {owner: number for number, owner in world.number_owner.items()}
    cast = _cast(plan)
    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for visitor, prisoner in world.visits:
        number = owned.get(visitor)
        if (
            visitor in seen
            or visitor in cast
            or prisoner in cast
            or prisoner not in world.fenwick
            or number is None
            or number in world.seized_numbers
        ):
            continue
        seen.add(visitor)
        candidates.append((visitor, prisoner))
    rng = _rng(plan, "bookings")
    chosen = rng.sample(candidates, BACKGROUND_BOOKINGS)
    drafts: list[tuple[datetime, str, str, str, datetime, str]] = []
    for visitor, prisoner in chosen:
        day = WEEK_START + timedelta(days=rng.randrange(5))  # booked Monday to Friday
        booked_at = _at(day, rng.randrange(9 * 60, 17 * 60))
        visit_day = day + timedelta(days=rng.randrange(3, 10))
        visit_at = _at(visit_day, rng.choice((10 * 60, 14 * 60, 15 * 60 + 30)))
        channel = rng.choice(("in_person", "in_person", "video"))
        drafts.append((booked_at, visitor, prisoner, owned[visitor], visit_at, channel))
    drafts.append(
        (STORY_BOOKED_AT, COORDINATOR, THIRD_MEMBER, COORDINATOR_NUMBER, STORY_VISIT_AT,
         "in_person")
    )  # fmt: skip
    drafts.sort(key=lambda d: (d[0], d[1]))
    return [
        _booking(plan, f"VB-2605-{i:03d}", visitor, prisoner, number, booked, visit, channel)
        for i, (booked, visitor, prisoner, number, visit, channel) in enumerate(drafts, start=1)
    ]


# --- The PIN first contacts (P1) -----------------------------------------------------------------


def _call(
    plan: Plan, pin: str, number: str, start: datetime, duration: int, prisoner: str
) -> dict[str, str]:
    account, phone, held = plan.entity(pin), plan.entity(number), plan.entity(prisoner)
    return {
        "nomis_id": str(held.properties["prison_number"]),
        "pin_account": str(account.properties["handle"]),
        "called_number": str(phone.properties["value_raw"]),
        "call_start": cell_text(start),
        "duration_s": str(duration),
        "direction": "outbound",
        "sequence": "",
        **_row_marking(phone.handling, account.handling),
    }


def new_contact_rows(plan: Plan) -> list[dict[str, str]]:
    """The week's first contacts, by call start: Darren Ashcombe's two calls to the number nobody
    owns, and `BACKGROUND_CONTACTS` background Fenwick Moor prisoners each calling, once or twice,
    an outside number their account never called that no seized SIM called either and that is
    neither the coordinator's nor the unidentified number. Every (account, number) pair is new."""
    if plan.profile != "demo":
        return []
    world = _world(plan)
    cast = _cast(plan)
    pin_of = {prisoner: pin for pin, prisoner in world.pin_owner.items()}
    if (pin_of[THIRD_MEMBER], UNIDENTIFIED_NUMBER) in world.called:
        raise ValueError("the third member's account already calls the unidentified number")
    accounts = sorted(
        pin for pin, prisoner in world.pin_owner.items()
        if prisoner in world.fenwick and prisoner not in cast
    )  # fmt: skip
    numbers = sorted(
        e.key for e in plan.entities
        if e.properties.get("endpoint_kind") == "msisdn"
        and e.key not in world.seized_numbers
        and e.key not in (COORDINATOR_NUMBER, UNIDENTIFIED_NUMBER)
        and world.number_owner.get(e.key) not in cast
    )  # fmt: skip
    rng = _rng(plan, "new-contacts")
    calls: list[tuple[datetime, str, str, int, str]] = []
    used: set[str] = set()
    for pin in rng.sample(accounts, BACKGROUND_CONTACTS):
        number = rng.choice([n for n in numbers if (pin, n) not in world.called and n not in used])
        used.add(number)
        for _ in range(rng.choice((1, 1, 2))):
            day = WEEK_START + timedelta(days=rng.randrange(7))
            start = _at(day, rng.randrange(8 * 60, 20 * 60))
            calls.append((start, pin, number, rng.randint(20, 1_800), world.pin_owner[pin]))
    pin = pin_of[THIRD_MEMBER]
    for start, duration in STORY_CALLS:
        calls.append((start, pin, UNIDENTIFIED_NUMBER, duration, THIRD_MEMBER))
    calls.sort(key=lambda c: (c[0], c[1]))
    rows = [_call(plan, pin, number, start, d, who) for start, pin, number, d, who in calls]
    for i, row in enumerate(rows, start=1):
        row["sequence"] = str(i)
    return rows


# --- Writing -------------------------------------------------------------------------------------


ROWS = {VISIT_BOOKINGS: booking_rows, PIN_NEW_CONTACTS: new_contact_rows}
HEADERS: dict[str, tuple[str, ...]] = {
    VISIT_BOOKINGS: BOOKINGS_HEADER,
    PIN_NEW_CONTACTS: NEW_CONTACTS_HEADER,
}


def rows_of(plan: Plan, file: str) -> list[dict[str, str]]:
    """A batch's rows, in the order they are written. `KeyError` for a file that is not one."""
    return ROWS[file](plan)


def output_name(file: str) -> str:
    return f"{INCOMING}/{file}"


@dataclass(frozen=True)
class WrittenBatch:
    name: str  # relative to the output folder, with `/` separators
    rows: int
    bytes: int
    sha256: str


def _write(path: Path, header: Sequence[str], rows: Iterator[Mapping[str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow([row.get(c, "") for c in header])
            count += 1
    return count


def write_batches(plan: Plan, out_dir: Path) -> list[WrittenBatch]:
    """Writes the two batches under `out_dir/incoming/` (the demo profile only) and answers each
    one written. A second call rewrites them byte for byte."""
    written: list[WrittenBatch] = []
    for stage in MONITORING_STAGES:
        rows = rows_of(plan, stage.file)
        if not rows:
            continue
        name = output_name(stage.file)
        path = out_dir / name
        count = _write(path, HEADERS[stage.file], iter(rows))
        data = path.read_bytes()
        written.append(WrittenBatch(name, count, len(data), hashlib.sha256(data).hexdigest()))
    return written


__all__ = [
    "BOOKINGS_RECIPE",
    "EXPECTED_ALERTS",
    "MONITORING_STAGES",
    "NEW_CONTACTS_RECIPE",
    "P1_RULE_NAME",
    "P1_SENTENCE",
    "PIN_NEW_CONTACTS",
    "VISIT_BOOKINGS",
    "ExpectedAlert",
    "MonitoringStage",
    "WrittenBatch",
    "booking_rows",
    "new_contact_rows",
    "rows_of",
    "write_batches",
]
