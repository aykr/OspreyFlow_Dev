"""The Prison Intelligence Dataset's plan, proved without a store (ADR-120 D3 to D9, Amendments
4 and 7; the build brief `01_DOMAIN_MODEL_AND_GENERATOR_BRIEF.md` section 5).

`demo_fixtures.pid_plan.build_plan` returns the whole case as keys, never ids: entities, links,
call aggregates, report texts and picture subjects. Nothing here opens a store, a socket or a
file outside `tmp_path`; every check computes its figure from the plan's own entities and links, so
a constant that drifts from the data it describes fails (rule 12), and the real components stand
in for the real consumers: the `msisdn` adapter, `MatchBuilder`, `ComputeRustworkxAdapter`,
`compute_weight` with the shipped weights file, and the composed deployment ontology. What each
group of tests guards:

- the throw-over statistics (window and cut-off, yards, hours, weekdays, every incident's place and
  item, the four hotspot yards beside Wing F, the map points, Amendment 7's `OCCURRED_AT`
  properties): the demo's chapters 2 and 3 would show a different pattern from the one claimed;
- the report selection (229 by one pattern, 68 used, the F2 illicit-item reports, a real selection,
  short extractable text): chapter 5's figures and the Questions module's 80,000-character ceiling;
- handling (one SECRET link, 12 `S2`, 20 `A1`, two units): the access-control scenes and the
  export gate;
- the script's own numbers, each at the two moments the demo shows it (the seed alone, Act 1, and
  after chapter 4 has loaded the reports): J1's links, J2's four PIN accounts, J5's two degrees by
  five and six routes and the unconnected prisoner, J7's betweenness; and chapter 6, the four
  gaps absent by construction, the seized handsets found with the relays, the chapter 9 batch,
  `PASSES_ITEMS_TO` as the one inferred item;
- identifiers and numbers (D4 `Z####ZZ`, `QQ`, `SYN-`, `PC-`, `PIN-`, Luhn IMEIs; D5 drama ranges,
  and no number any other fixture or seed produces);
- the weights (D3: cell-share occurrences are weeks shared; Amendment 7 decision 2: the principal's
  payment and call circle weighs as the amendment says, advisory, with the check shown able to
  fail);
- volumes and structure (both profiles, every link end exists, every type and property declared
  in the core and NIEM version 3, no PID name in any other fixture).

The older synthetic prison fixture is never opened, imported or named: the collision tests find
other fixtures and seeds by discovery (D5).

Which tests read repository files (everything else reads only the plan): the number-collision
discovery imports and calls every other fixture's and seed's generators (with the network and
subprocesses refused and the working directory in `tmp_path`) and reads the `*.csv` files under
`demo_fixtures/`; the name test reads every other file under `demo_fixtures/`; the number-search
test reads the source files of `OspreyFlow_Build/tests` and `OspreyFlow_Core/apps`, `packages` and
`scripts`; the determinism test starts two Python subprocesses to build the plan under two hash
seeds.

Limits, stated: the advisory circle counts final totals, where the store snapshots the counts at
write time (stage 5's binding test reads the store's own); and the discovery runs in this
process on this checkout, so a generator that writes an absolute path outside `tmp_path` is not
contained by it, only by the network, process and working-directory guards.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import itertools
import math
import os
import pkgutil
import random
import re
import socket
import subprocess
import sys
import types
import warnings
from collections import Counter, deque
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

import pytest

import demo_fixtures
from adapters.compute_rustworkx.adapter import ComputeRustworkxAdapter
from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.builders import MatchBuilder
from adapters.graph_arcadedb.weight import compute_weight
from demo_fixtures import pid_names, pid_plan
from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.imei import imei
from knowledge_adapters.imsi import imsi
from knowledge_adapters.msisdn import msisdn
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from ontology.packs import load_deployment_ontology, load_pack
from ontology.validation import validate_edge_endpoints, validate_properties
from ontology.weights import load_weight_rules
from schemas.compute import CentralityRequest
from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Node,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
    WeightComponents,
)

# --- What the specification states, written out here so a constant cannot drift with its data ----

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
PRYCE = "report:pryce"
HASH_SEED_PROGRAM = (
    "import hashlib\n"
    "from demo_fixtures import pid_plan\n"
    "print(hashlib.sha256(repr(pid_plan.build_plan('demo')).encode()).hexdigest())\n"
)
ZONE_REF = "pid:est1:zone:wing-f"
WING_F_REF = "pid:est1:wing:F"
LANDING_F1_REF = "pid:est1:landing:F1"
LANDING_F2_REF = "pid:est1:landing:F2"
WING_F_POINT = (51.43000, -1.15000)
EXTENT = (51.33, 51.60, -1.59, -0.55)  # lat min, lat max, lon min, lon max (the Berkshire extract)

EXPECTED_YARDS = {
    "03": 36, "04": 35, "05": 35, "06": 30,
    "01": 16, "02": 16, "07": 16, "08": 16, "09": 16, "10": 16, "11": 15, "12": 15,
}  # fmt: skip
EXPECTED_HOURS = {h: 25 for h in (8, 9, 10, 11, 13, 14)}
EXPECTED_HOURS[15] = 23
EXPECTED_HOURS.update({h: 6 for h in (7, 12, 16, 17)})
EXPECTED_HOURS.update({h: 5 for h in (*range(0, 7), *range(18, 24))})
EXPECTED_WEEKDAYS = {"Sun": 50, "Sat": 40, "Mon": 34, "Tue": 34, "Wed": 34, "Thu": 35, "Fri": 35}
EXPECTED_ITEMS = {"mobile phone": 70, "drugs": 90, "tobacco": 50, "SIM card": 30, "other": 22}
WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
HOTSPOTS = {"03", "04", "05", "06"}

CAST_PRISONERS = (
    "principal", "brother", "third_member",
    *(f"relay_{i}" for i in range(1, 6)),
    *(f"cellmate_{i}" for i in range(1, 5)),
    "larkhill_1", "larkhill_2",
    *(f"calder_{i}" for i in range(1, 8)),
)  # fmt: skip
CAST_OUTSIDERS = (
    "coordinator", "payer", "arrested_outside", "mother", "partner", "sister", "friend",
    *(f"outside_{i}" for i in range(1, 7)),
)  # fmt: skip
CAST_PEOPLE = frozenset(CAST_PRISONERS) | frozenset(CAST_OUTSIDERS)
CAST_CELLS = ("F1-03", "F1-07", "F1-11", "F2-05", "F2-09", "F2-14", "F2-17", "F2-18", "F2-21")
CAST_ENDPOINTS = frozenset(
    {f"pin:{k}" for k in CAST_PRISONERS}
    | {"cash:principal", "cash:relay_1", "cash:relay_2"}
    | {"number:coordinator", "number:unidentified", "account:payer"}
)
#: The sixteen cast PIN accounts that call background numbers, because every PIN account calls
#: at least one number (spec 7) and the table gives these no call (spec 4 and 14.6, D3 narrowed).
PIN_CALLERS = frozenset(
    f"pin:{k}"
    for k in CAST_PRISONERS
    if k not in ("principal", "brother", "relay_1", "relay_2", "relay_3")
)
CAST_STATIC = (
    CAST_PEOPLE
    | CAST_ENDPOINTS
    | {f"cell:{c}" for c in CAST_CELLS}
    | {"est:fenwick-moor", "ocg:larkhill-lane", "ocg:calder-street"}
    | {f"incident:find_0{i}" for i in range(1, 8)}
    | {"incident:assault_1", "incident:assault_2", "incident:disorder_1", "incident:disorder_2"}
    | {"report:p1", "report:p2", "report:p3", PRYCE, "place:arrest-site"}
)
ILLICIT_WORDS = ("phone", "handset", "sim card", "drugs", "tobacco", "spice", "contraband")
UK_NUMBER = re.compile(r"(?<![\w+])(?:\+44[\s-]?(?:\(0\))?|0)\d(?:[\s-]?\d){8,9}(?!\d)")
SPEC_ALLOWED_BACKGROUND = frozenset(
    {
        "HELD_AT", "PRESENT_AT", "PART_OF", "ADJOINS", "USED_BY", "SHARED_CELL_WITH", "VISITED",
        "USES", "COMMUNICATED_WITH", "TRANSACTED", "ASSOCIATE_OF", "FAMILY_OF",
        "CO_DEFENDANT_OF", "IN_CONFLICT_WITH", "ROLE_IN", "MENTIONED_IN", "OCCURRED_AT", "DEPICTS",
    }
)  # fmt: skip


# --- Small helpers --------------------------------------------------------------------------------


def _as_dt(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    assert isinstance(value, str), f"not a date or a timestamp: {value!r}"
    return datetime.fromisoformat(value)


def _as_date(value: object) -> date:
    return _as_dt(value).date()


def _same_moment(a: object, b: object) -> bool:
    if isinstance(a, datetime) and isinstance(b, datetime):
        return a == b
    return _as_date(a) == _as_date(b)


def _utc(value: object) -> datetime:
    moment = _as_dt(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + (
        math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _in_pid_block(e164: str) -> bool:
    if not e164.startswith("+44"):
        return False
    national = e164[3:]
    if len(national) != 10 or not national.isdigit():
        return False
    n = int(national)
    return (
        7_700_900_600 <= n <= 7_700_900_899
        or 1_164_960_000 <= n <= 1_164_960_599
        or 1_174_960_000 <= n <= 1_174_960_599
    )


def _uk_numbers(text: str) -> set[str]:
    out: set[str] = set()
    for match in UK_NUMBER.finditer(text):
        try:
            out.add(msisdn(match.group(0)))
        except Exception:  # not a number the adapter accepts: no number to collect
            continue
    return out


def _adjacency(links: Iterable[Any]) -> dict[str, Counter[str]]:
    adj: dict[str, Counter[str]] = {}
    for link in links:
        if link.source == link.target:
            continue
        adj.setdefault(link.source, Counter())[link.target] += 1
        adj.setdefault(link.target, Counter())[link.source] += 1
    return adj


def _distance(links: Iterable[Any], start: str, goal: str) -> int | None:
    adj = _adjacency(links)
    seen = {start: 0}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        for nxt in adj.get(here, ()):
            if nxt not in seen:
                seen[nxt] = seen[here] + 1
                queue.append(nxt)
    return seen.get(goal)


class View:
    """One plan with the indexes the tests share, built once per profile."""

    def __init__(self, plan: Any) -> None:
        self.plan = plan
        self.ent: dict[str, Any] = {e.key: e for e in plan.entities}
        self.all_links: list[Any] = list(plan.links)

    @cached_property
    def visible(self) -> list[Any]:
        """What the demo analyst sees once chapter 4 has loaded the reports (no SECRET link)."""
        return self.at("chapter4")

    def at(self, moment: Any, *, cleared: bool = False) -> list[Any]:
        return list(pid_plan.links_at(self.plan, moment, secret_cleared=cleared))

    @cached_property
    def site(self) -> dict[str, str]:
        return {
            str(e.properties["site_ref"]): e.key
            for e in self.plan.entities
            if "site_ref" in e.properties
        }

    def of_type(self, entity_type: str) -> list[Any]:
        return [e for e in self.plan.entities if e.entity_type == entity_type]

    def links(self, link_type: str, *, everything: bool = False) -> list[Any]:
        pool = self.all_links if everything else self.visible
        return [link for link in pool if link.link_type == link_type]

    def touching(self, key: str, *, everything: bool = False) -> list[Any]:
        pool = self.all_links if everything else self.visible
        return [link for link in pool if key in (link.source, link.target)]

    def etype(self, key: str) -> str:
        return str(self.ent[key].entity_type)

    @cached_property
    def visitor_keys(self) -> frozenset[str]:
        """Everyone who is the source of a visit: the outsiders Brief 2's R3 creates."""
        return frozenset(lk.source for lk in self.all_links if lk.link_type == "VISITED")

    @cached_property
    def area_column(self) -> dict[str, str]:
        """For each area-to-report link, the report-file column it comes from: the report's
        first area is `area_ref`, its second `area_ref_2`, its third `area_ref_3`."""
        seen: Counter[str] = Counter()
        out: dict[str, str] = {}
        for lk in self.all_links:
            if (
                lk.link_type == "MENTIONED_IN"
                and self.etype(lk.source) == "Location"
                and lk.target in self.reports
            ):
                n = seen[lk.target]
                seen[lk.target] += 1
                out[lk.key] = "area_ref" if n == 0 else f"area_ref_{n + 1}"
        return out

    @cached_property
    def prisoners(self) -> list[Any]:
        return [e for e in self.of_type("Person") if "prison_number" in e.properties]

    @cached_property
    def throw_overs(self) -> list[Any]:
        return [e for e in self.of_type("Incident") if e.properties.get("category") == "throw_over"]

    @cached_property
    def yard_of(self) -> dict[str, str]:
        """Throw-over incident key -> the yard's key, from its one `OCCURRED_AT` link."""
        out: dict[str, str] = {}
        keys = {e.key for e in self.throw_overs}
        for link in self.links("OCCURRED_AT", everything=True):
            if link.source in keys:
                assert link.source not in out, f"{link.source} occurred at two places"
                out[link.source] = link.target
        return out

    def yard_code(self, key: str) -> str:
        ref = str(self.ent[key].properties.get("site_ref", ""))
        assert ":yard:" in ref, f"{key} is not a yard: {ref!r}"
        return ref.rsplit(":", 1)[1]

    @cached_property
    def reports(self) -> frozenset[str]:
        """Every intelligence report: a text Document (there is no extract any more)."""
        return frozenset(
            e.key for e in self.of_type("Document") if e.properties.get("media_kind") == "text"
        )

    @cached_property
    def mentions(self) -> dict[str, list[str]]:
        """Report key -> sources of the analyst's visible `MENTIONED_IN` links."""
        out: dict[str, list[str]] = {}
        for link in self.links("MENTIONED_IN"):
            if link.target in self.reports:
                out.setdefault(link.target, []).append(link.source)
        return out

    def persons_in(self, report: str) -> list[str]:
        return [s for s in self.mentions.get(report, []) if self.etype(s) == "Person"]

    def areas_of(self, report: str) -> list[str]:
        return [s for s in self.mentions.get(report, []) if self.etype(s) == "Location"]

    def report_day(self, report: str) -> date:
        return _as_date(self.ent[report].properties["sent_at"])

    @cached_property
    def hotspot_keys(self) -> frozenset[str]:
        return frozenset(self.site[f"pid:est1:yard:{c}"] for c in sorted(HOTSPOTS))

    @cached_property
    def hotspot_days(self) -> frozenset[date]:
        return frozenset(
            _as_date(e.properties["occurred_at"])
            for e in self.throw_overs
            if self.yard_of[e.key] in self.hotspot_keys
        )

    @cached_property
    def selected(self) -> frozenset[str]:
        """The brief's rule, applied to the plan's own links and dates."""
        wing_f = self.site[WING_F_REF]
        return frozenset(
            r
            for r in self.reports
            if (wing_f in self.areas_of(r) or set(self.areas_of(r)) & self.hotspot_keys)
            and self.report_day(r) in self.hotspot_days
        )

    @cached_property
    def used(self) -> frozenset[str]:
        """The reports of the selection that name people. `report:pryce` names two but lies
        outside the zone, so it is not one of the 68 (checked in its own test)."""
        return frozenset(r for r in self.selected if self.persons_in(r))

    def present_at_cut_off(self, landing_ref: str) -> set[str]:
        """Persons whose stay in a cell of the landing includes the cut-off."""
        landing = self.site[landing_ref]
        cells = {link.source for link in self.links("PART_OF") if link.target == landing}
        cut = _as_date(pid_plan.CUT_OFF)
        out: set[str] = set()
        for link in self.links("PRESENT_AT"):
            if link.target not in cells or self.etype(link.source) != "Person":
                continue
            first = None if link.first_seen is None else _as_date(link.first_seen)
            last = None if link.last_seen is None else _as_date(link.last_seen)
            if (first is None or first <= cut) and (last is None or last >= cut):
                out.add(link.source)
        return out

    @cached_property
    def adjacency(self) -> dict[str, Counter[str]]:
        return _adjacency(self.visible)

    def component(self, start: str, *, everything: bool = False) -> set[str]:
        pool = self.all_links if everything else self.visible
        neighbours: dict[str, set[str]] = {}
        for link in pool:
            neighbours.setdefault(link.source, set()).add(link.target)
            neighbours.setdefault(link.target, set()).add(link.source)
        seen = {start}
        queue = deque([start])
        while queue:
            for nxt in neighbours.get(queue.popleft(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def cast_keys(self) -> set[str]:
        keys = set(CAST_STATIC) & set(self.ent)
        keys |= {e.key for e in self.of_type("Device")}
        keys |= {
            e.key for e in self.of_type("Endpoint") if e.properties.get("endpoint_kind") == "imsi"
        }
        keys |= {f"picture:{k}" for k in keys if f"picture:{k}" in self.ent}
        return keys


@pytest.fixture(scope="module")
def demo() -> View:
    return View(pid_plan.build_plan("demo"))


@pytest.fixture(scope="module")
def scale() -> View:
    return View(pid_plan.build_plan("scale"))


@pytest.fixture(scope="module")
def ontology() -> Any:
    return load_deployment_ontology()


# --- Determinism, the window, and the throw-over statistics (ADR-120 D6; brief 5.5) ---------------


def _cast_link_signature(view: View) -> list[tuple[Any, ...]]:
    keys = view.cast_keys()
    return sorted(
        (
            link.link_type, link.source, link.target, link.occurrences,
            repr(link.first_seen), repr(link.last_seen), link.provenance,
            sorted(link.properties.items()),
        )
        for link in view.all_links
        if link.source in keys and link.target in keys
    )  # fmt: skip


def test_the_plan_is_deterministic(demo: View) -> None:
    again = pid_plan.build_plan("demo", pid_plan.SEED)
    assert again == demo.plan
    other = View(pid_plan.build_plan("demo", seed=pid_plan.SEED + 1))
    assert other.plan != demo.plan, "another seed must change the background"
    assert other.plan.links != demo.plan.links
    # The cast is the same whatever the seed: every link among its keys, to the last property.
    assert _cast_link_signature(other) == _cast_link_signature(demo)
    assert len(_cast_link_signature(demo)) > 100, "the comparison must cover the cast's links"
    # Nor does the plan move with the interpreter's hash seed: two fresh processes, one digest.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join(sys.path)}
    digests = set()
    for hash_seed in ("1", "2"):
        out = subprocess.run(
            [sys.executable, "-c", HASH_SEED_PROGRAM],
            env={**env, "PYTHONHASHSEED": hash_seed},
            capture_output=True,
            text=True,
            check=True,
        )
        digests.add(out.stdout.strip())
    assert len(digests) == 1 and len(next(iter(digests))) == 64


def test_window_cut_off_and_weekday_of_the_first_day(demo: View) -> None:
    assert pid_plan.SEED == 120
    start = _as_date(pid_plan.WINDOW_START)
    end = _as_date(pid_plan.WINDOW_END)
    cut = _as_date(pid_plan.CUT_OFF)
    assert start == date(2026, 3, 1)
    assert WEEKDAY_NAMES[start.weekday()] == "Sun"
    assert end == date(2026, 4, 30)
    assert cut == date(2026, 4, 30)
    assert (end - start).days + 1 == 61
    days = [_as_date(e.properties["occurred_at"]) for e in demo.throw_overs]
    assert min(days) >= start and max(days) <= end
    # Nothing is dated after the intelligence cut-off: links, incidents, reports.
    for link in demo.all_links:
        for moment in (link.first_seen, link.last_seen):
            assert moment is None or _as_date(moment) <= cut, f"{link.key} is after the cut-off"
    for ent in demo.plan.entities:
        for name in ("occurred_at", "sent_at"):
            if name in ent.properties:
                assert _as_date(ent.properties[name]) <= cut, f"{ent.key}.{name} after cut-off"
    # The call weeks: Monday 1 September 2025 to the week holding the cut-off.
    first_call_week = date(2025, 9, 1)
    assert first_call_week.weekday() == 0
    assert pid_plan.CALL_WEEKS == 35
    last_call_week = date.fromordinal(first_call_week.toordinal() + 7 * (pid_plan.CALL_WEEKS - 1))
    assert last_call_week == date(2026, 4, 27)
    assert last_call_week <= cut < date.fromordinal(last_call_week.toordinal() + 7)
    assert all(len(c.weekly) == pid_plan.CALL_WEEKS for c in demo.plan.calls)


def test_throw_overs_by_yard_are_exactly_the_multiset(demo: View) -> None:
    counts = Counter(demo.yard_code(demo.yard_of[e.key]) for e in demo.throw_overs)
    assert counts == Counter(EXPECTED_YARDS)
    assert counts == Counter({str(k): v for k, v in pid_plan.YARD_COUNTS.items()})
    assert sum(counts.values()) == pid_plan.TOTAL_THROW_OVERS == 262 == len(demo.throw_overs)
    assert {str(c) for c in pid_plan.HOTSPOT_YARDS} == HOTSPOTS
    hot = sum(counts[c] for c in HOTSPOTS)
    assert hot == 136
    assert round(100 * hot / 262, 1) == 51.9
    others = [n for code, n in counts.items() if code not in HOTSPOTS]
    assert len(others) == 8 and sum(others) == 126
    assert min(counts[c] for c in HOTSPOTS) > max(others), "every hotspot above every other yard"


def test_throw_overs_by_hour_are_exactly_the_multiset(demo: View) -> None:
    counts = Counter(_as_dt(e.properties["occurred_at"]).hour for e in demo.throw_overs)
    assert counts == Counter(EXPECTED_HOURS)
    assert counts == Counter({int(k): v for k, v in pid_plan.HOUR_COUNTS.items()})
    peak = sum(counts[h] for h in (8, 9, 10, 11, 13, 14, 15))
    assert peak == 173
    assert round(100 * peak / 262, 1) == 66.0
    assert sum(counts.values()) - peak == 89


def test_throw_overs_by_weekday_are_exactly_the_multiset(demo: View) -> None:
    counts = Counter(
        WEEKDAY_NAMES[_as_dt(e.properties["occurred_at"]).weekday()] for e in demo.throw_overs
    )
    assert counts == Counter(EXPECTED_WEEKDAYS)
    # WEEKDAY_COUNTS is keyed by `date.weekday()` (0 = Monday), as HistogramBucket.weekday is.
    assert counts == Counter({WEEKDAY_NAMES[int(k)]: v for k, v in pid_plan.WEEKDAY_COUNTS.items()})
    assert set(pid_plan.WEEKDAY_COUNTS) == set(range(7))
    weekend = counts["Sat"] + counts["Sun"]
    assert weekend == 90 and round(100 * weekend / 262, 1) == 34.4
    assert counts["Sun"] == 50 and round(100 * counts["Sun"] / 262, 1) == 19.1
    assert sum(counts[d] for d in ("Mon", "Tue", "Wed", "Thu", "Fri")) == 172


def test_every_throw_over_carries_its_place_and_item_inside_the_window(demo: View) -> None:
    start, end = _as_date(pid_plan.WINDOW_START), _as_date(pid_plan.WINDOW_END)
    refs: list[str] = []
    for inc in demo.throw_overs:
        props = inc.properties
        refs.append(str(props["incident_ref"]))
        assert re.fullmatch(r"pid:est1:inc:to:\d{4}", refs[-1]), refs[-1]
        assert props["item"] in EXPECTED_ITEMS
        assert start <= _as_date(props["occurred_at"]) <= end
        links = [
            lk for lk in demo.all_links if lk.link_type == "OCCURRED_AT" and lk.source == inc.key
        ]
        assert len(links) == 1, f"{inc.key} must have exactly one OCCURRED_AT"
        (link,) = links
        assert demo.etype(link.target) == "Location"
        assert ":est1:yard:" in str(demo.ent[link.target].properties["site_ref"])
        assert _same_moment(link.first_seen, props["occurred_at"])
        assert _same_moment(link.last_seen, props["occurred_at"])
        assert link.occurrences == 1
    assert len(refs) == len(set(refs)) == 262
    items = Counter(e.properties["item"] for e in demo.throw_overs)
    assert items == Counter(EXPECTED_ITEMS)
    assert items == Counter(dict(pid_plan.ITEM_COUNTS))


def test_the_four_hotspot_yards_adjoin_and_are_used_by_wing_f_and_no_other_does(
    demo: View,
) -> None:
    wing_f = demo.site[WING_F_REF]
    yards = {c: demo.site[f"pid:est1:yard:{c}"] for c in EXPECTED_YARDS}
    assert len(yards) == 12
    wings = {w: demo.site[f"pid:est1:wing:{w}"] for w in "ABCDEF"}
    assert len(wings) == 6

    def wings_beside(link_type: str, yard: str) -> set[str]:
        out: set[str] = set()
        for link in demo.links(link_type):
            ends = {link.source, link.target}  # USED_BY is read in either direction
            if yard in ends:
                out |= (ends - {yard}) & set(wings.values())
        return out

    for code, key in yards.items():
        for link_type in ("ADJOINS", "USED_BY"):
            beside = wings_beside(link_type, key)
            if code in HOTSPOTS:
                assert beside == {wing_f}, f"hotspot yard {code} {link_type}: {beside}"
            else:
                assert beside and wing_f not in beside, f"yard {code} {link_type}: {beside}"
    for link_type in ("ADJOINS", "USED_BY"):
        touching_f = {c for c, key in yards.items() if wing_f in wings_beside(link_type, key)}
        assert touching_f == HOTSPOTS


def _throw_over_points(view: View) -> dict[str, list[tuple[float, float]]]:
    points: dict[str, list[tuple[float, float]]] = {}
    for link in view.links("OCCURRED_AT", everything=True):
        if link.source in view.yard_of:
            code = view.yard_code(link.target)
            points.setdefault(code, []).append(
                (float(link.properties["lat"]), float(link.properties["lon"]))
            )
    return points


def test_the_map_points_sit_in_the_basemap_and_a_boundary_round_wing_f_takes_only_the_hotspots(
    demo: View,
) -> None:
    place = pid_plan.PLACE_POINTS
    wing_f = demo.site[WING_F_REF]
    assert demo.site[ZONE_REF] in place
    assert place[wing_f] == pytest.approx(WING_F_POINT)
    lat_lo, lat_hi, lon_lo, lon_hi = EXTENT
    assert tuple(pid_plan.BASEMAP_EXTENT) == EXTENT
    yard_point = {c: place[demo.site[f"pid:est1:yard:{c}"]] for c in EXPECTED_YARDS}
    for code, (lat, lon) in yard_point.items():
        assert lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi, f"outside extract: {code}"
        assert _metres((lat, lon), (51.5, -0.6)) > 5_000, code
    for code in HOTSPOTS:
        assert _metres(yard_point[code], WING_F_POINT) <= 150, code
    for code in set(yard_point) - HOTSPOTS:
        assert _metres(yard_point[code], WING_F_POINT) > 300, code
        for hot in HOTSPOTS:
            assert _metres(yard_point[code], yard_point[hot]) > 300, (code, hot)
    # Every throw-over sits within the jitter (0.00005 degrees) of its own yard's point.
    points = _throw_over_points(demo)
    assert set(points) == set(EXPECTED_YARDS)
    for code, pts in points.items():
        for lat, lon in pts:
            assert abs(lat - yard_point[code][0]) <= 0.00005 + 1e-9, code
            assert abs(lon - yard_point[code][1]) <= 0.00005 + 1e-9, code
    # A boundary round Wing F, 200 metres out, takes every hotspot event and no other.
    inside = Counter(
        code for code, pts in points.items() for p in pts if _metres(p, WING_F_POINT) <= 200
    )
    assert set(inside) == HOTSPOTS
    assert sum(inside.values()) == 136
    # The arrest site: a mapped place well outside the zone, where report:pryce is set.
    site = demo.site["pid:out:place:arrest-01"]
    lat, lon = place[site]
    assert lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi
    assert _metres((lat, lon), WING_F_POINT) > 2_000
    assert site not in {
        lk.source for lk in demo.links("PART_OF") if lk.target == demo.site[ZONE_REF]
    }
    assert site in demo.areas_of(PRYCE)
    # Every place reference is the PID's own.
    for ent in demo.of_type("Location"):
        assert str(ent.properties["site_ref"]).startswith("pid:"), ent.key
        if "geometry_ref" in ent.properties:
            assert str(ent.properties["geometry_ref"]).startswith("pid:"), ent.key


# --- The reports: one pattern, the selection, the used reports (brief 5.5) ------------------------


def test_229_reports_meet_the_rule(demo: View) -> None:
    assert len(demo.selected) == pid_plan.REPORTS_SELECTED == 229
    wing_f = demo.site[WING_F_REF]
    in_yards = {r for r in demo.selected if set(demo.areas_of(r)) & demo.hotspot_keys}
    on_wing = demo.selected - in_yards
    assert (len(on_wing), len(in_yards)) == (177, 52)
    assert all(wing_f in demo.areas_of(r) for r in demo.selected), "a yard report also names Wing F"
    # The date half of the rule is real: reports about the right place on a day with no hotspot
    # throw-over are not selected.
    area_only = {
        r
        for r in demo.reports
        if wing_f in demo.areas_of(r) or set(demo.areas_of(r)) & demo.hotspot_keys
    }
    assert len(area_only) > len(demo.selected)
    assert all(demo.report_day(r) not in demo.hotspot_days for r in area_only - demo.selected)


def test_the_one_pattern_selects_the_same_229(demo: View) -> None:
    pattern = PatternQuery.model_validate(pid_plan.REPORT_PATTERN)
    nodes = {n.var: n for n in pattern.nodes}
    assert {v: n.entity_type for v, n in nodes.items()} == {
        "zone": "Location", "area": "Location", "report": "Document",
        "incident": "Incident", "yard": "Location",
    }  # fmt: skip
    assert {(e.edge_type, e.from_var, e.to_var) for e in pattern.edges} == {
        ("PART_OF", "area", "zone"),
        ("MENTIONED_IN", "area", "report"),
        ("MENTIONED_IN", "incident", "report"),
        ("OCCURRED_AT", "incident", "yard"),
        ("PART_OF", "yard", "zone"),
    }
    zone = nodes["zone"].node_id
    assert zone is not None and zone in demo.ent
    assert demo.ent[zone].properties["site_ref"] == ZONE_REF
    assert [n.var for n in pattern.nodes if n.node_id] == ["zone"], "one pinned root only"
    # The real compiler takes it as one chain, pins the zone, and tells the Locations apart.
    reader = Principal(id="r", clearance="OFFICIAL", org_unit="u", datasets=["pid"])
    compiled = MatchBuilder(pattern)._render_single_chain(AccessFilter(load_uk_le_scheme()), reader)
    assert isinstance(compiled, str), "the pattern must compile as one chain"
    assert f"'{zone}'" in compiled
    assert compiled.count(".where(neq(") == 3, "area, yard and zone are three distinct Locations"
    # Its semantics, emulated over the plan exactly as the compiled chain reads it.
    in_zone = {lk.source for lk in demo.links("PART_OF") if lk.target == zone}
    areas_in_zone = {k for k in in_zone if demo.etype(k) == nodes["area"].entity_type}
    yards_in_zone = {k for k in in_zone if demo.etype(k) == nodes["yard"].entity_type}
    mentioned_by: dict[str, set[str]] = {}
    for link in demo.links("MENTIONED_IN"):
        mentioned_by.setdefault(link.target, set()).add(link.source)
    occurred_at: dict[str, set[str]] = {}
    for link in demo.links("OCCURRED_AT"):
        occurred_at.setdefault(link.source, set()).add(link.target)
    matched_reports: set[str] = set()
    bound: set[str] = {zone}
    for doc in (e.key for e in demo.of_type("Document")):
        sources = mentioned_by.get(doc, set())
        areas = {s for s in sources if s in areas_in_zone and s != zone}
        incidents = {s for s in sources if demo.etype(s) == "Incident"}
        for incident in incidents:
            for yard in occurred_at.get(incident, set()) & yards_in_zone:
                usable = {a for a in areas if a != yard} if yard != zone else set()
                if usable:
                    matched_reports.add(doc)
                    bound |= {doc, incident, yard} | usable
    assert matched_reports == set(demo.selected)
    assert len(matched_reports) == pid_plan.REPORTS_SELECTED == 229
    assert len(bound) <= pattern.limit, "the pattern's own limit must not cut the match short"


def test_68_reports_name_people_57_on_wing_f_and_11_in_the_yards(demo: View) -> None:
    assert len(demo.used) == pid_plan.REPORTS_USED == 68
    assert demo.used <= demo.selected
    assert len(demo.selected - demo.used) == 161, "the other 161 name nobody"
    in_yards = {r for r in demo.used if set(demo.areas_of(r)) & demo.hotspot_keys}
    on_wing = demo.used - in_yards
    assert (len(on_wing), len(in_yards)) == (57, 11)
    f1, f2 = demo.site[LANDING_F1_REF], demo.site[LANDING_F2_REF]
    assert {r for r in on_wing if f1 in demo.areas_of(r)}.isdisjoint(
        {r for r in on_wing if f2 in demo.areas_of(r)}
    )
    assert sum(f1 in demo.areas_of(r) for r in on_wing) == 25
    assert sum(f2 in demo.areas_of(r) for r in on_wing) == 32
    # Only persons make a report "used": a free-text report is mentioned by places and incidents.
    for r in demo.selected - demo.used:
        assert demo.persons_in(r) == []
    # One report names people outside the selection: the arrest, set away from the zone.
    assert {r for r in demo.reports if demo.persons_in(r)} - demo.used == {PRYCE}
    assert sorted(demo.persons_in(PRYCE)) == ["arrested_outside", "principal"]
    assert PRYCE not in demo.selected


def _names_an_item(text: str) -> bool:
    return any(w in text.lower() for w in ILLICIT_WORDS)


def _f2_illicit(view: View) -> list[str]:
    """The plan's own list, held to the text both ways: each of the 23 names an item and no
    other used F2 report does."""
    f2 = view.site[LANDING_F2_REF]
    keys = sorted(pid_plan.F2_ILLICIT_REPORT_KEYS)
    used_f2 = {r for r in view.used if f2 in view.areas_of(r)}
    assert set(keys) <= used_f2, "every illicit report is a used F2 report"
    for r in used_f2:
        assert _names_an_item(view.plan.report_texts[r]) == (r in keys), r
    return keys


def test_23_f2_illicit_reports_name_28_prisoners_13_in_a_group_3_more_than_once_the_principal_most(
    demo: View,
) -> None:
    illicit = _f2_illicit(demo)
    assert len(illicit) == pid_plan.F2_ILLICIT_REPORTS == 23
    assert {"report:p1", "report:p2", "report:p3"} <= set(illicit)
    f2 = demo.site[LANDING_F2_REF]
    used_f2 = {r for r in demo.used if f2 in demo.areas_of(r)}
    assert len(used_f2) == 32 and len(used_f2) - len(illicit) == 9
    named = Counter(p for r in illicit for p in demo.persons_in(r))
    assert len(named) == pid_plan.F2_ILLICIT_PRISONERS == 28
    assert sum(named.values()) == 32
    in_group = {
        link.source for link in demo.links("MEMBER_OF") if demo.etype(link.target) == "Organisation"
    }
    assert len({p for p in named if p in in_group}) == pid_plan.F2_ILLICIT_IN_GROUP == 13
    more_than_once = {p for p, n in named.items() if n > 1}
    assert len(more_than_once) == pid_plan.F2_ILLICIT_NAMED_MORE_THAN_ONCE == 3
    assert more_than_once == {"principal", "brother", "relay_1"}
    assert (named["principal"], named["brother"], named["relay_1"]) == (3, 2, 2)
    assert [p for p, n in named.items() if n == 3] == ["principal"]
    assert {
        "principal", "brother", "relay_1", "relay_2", "relay_3", "relay_4", "relay_5",
        "larkhill_1", "larkhill_2", *(f"calder_{i}" for i in range(1, 8)),
    } <= set(named)  # fmt: skip
    background = set(named) - CAST_PEOPLE
    assert len(background) == 12
    on_f2 = demo.present_at_cut_off(LANDING_F2_REF)
    assert background <= on_f2, "the twelve are on landing F2"
    assert not background & in_group
    # Across every report, nobody but the principal is named three times; third_member never.
    everyone = Counter(p for r in demo.reports for p in demo.persons_in(r))
    assert everyone["principal"] >= 3
    assert all(n < 3 for p, n in everyone.items() if p != "principal")
    assert everyone["third_member"] == 0
    # The other 45 used reports name background prisoners only.
    rest = demo.used - set(illicit)
    assert len(rest) == 45
    assert not {p for r in rest for p in demo.persons_in(r)} & CAST_PEOPLE
    # The rule holds for other seeds too, and the illicit set is the same whatever the seed.
    for seed in (1, 2):
        other = View(pid_plan.build_plan("demo", seed=seed))
        counts = Counter(p for r in other.reports for p in other.persons_in(r))
        assert counts["principal"] >= 3 and counts["third_member"] == 0
        assert all(n < 3 for p, n in counts.items() if p != "principal"), (
            seed,
            counts.most_common(4),
        )
        assert set(_f2_illicit(other)) == set(pid_plan.F2_ILLICIT_REPORT_KEYS)


def test_the_selection_is_a_real_selection(demo: View) -> None:
    assert len(demo.reports) == pid_plan.REPORTS_TOTAL == 350
    assert set(demo.plan.report_texts) == demo.reports
    not_selected = demo.reports - demo.selected
    assert len(not_selected) == 121
    wing_f = demo.site[WING_F_REF]
    in_zone = {
        r
        for r in not_selected
        if wing_f in demo.areas_of(r) or set(demo.areas_of(r)) & demo.hotspot_keys
    }
    elsewhere = not_selected - in_zone
    assert (len(in_zone), len(elsewhere)) == (40, 81)
    assert all(date(2026, 1, 5) <= demo.report_day(r) <= date(2026, 2, 27) for r in in_zone)
    assert all(date(2026, 1, 5) <= demo.report_day(r) <= date(2026, 4, 30) for r in elsewhere)
    assert all(demo.report_day(r) < _as_date(pid_plan.WINDOW_START) for r in in_zone), (
        "no throw-over data before the window, so the date rule excludes them"
    )
    assert not any(wing_f in demo.areas_of(r) for r in elsewhere)
    assert demo.selected < demo.reports


def test_report_text_is_short_extractable_and_names_who_it_mentions(demo: View) -> None:
    texts = demo.plan.report_texts
    assert all(len(texts[r]) < 1_000 for r in texts)
    assert sum(len(texts[r]) for r in demo.used) < 80_000
    for r in demo.reports:
        props = demo.ent[r].properties
        assert props["document_kind"] == "other"
        sent = _as_dt(props["sent_at"])
        assert (sent.hour, sent.minute) == (9, 0), f"{r} is sent at 09:00"
        assert str(props["title"]).strip()
        assert all(len(str(v)) < 200 for v in props.values()), "text lives in the media store"
        assert texts[r] not in {str(v) for v in props.values()}
    # Every text names, by family name or nickname, every person the report is linked to.
    for report, text in texts.items():
        for person in demo.persons_in(report):
            props = demo.ent[person].properties
            names = [str(props["family_name"]), *map(str, props.get("aliases", []))]
            assert any(re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE) for n in names), (
                f"{report} does not name {person} ({names})"
            )
    # The extraction scene's raw material.
    cally = [
        r
        for r in demo.reports
        if "principal" in demo.persons_in(r)
        and re.search(r"\bCally V\b", texts[r])
        and "Vance" not in texts[r]
    ]
    assert cally, "one report must call the principal only 'Cally V'"
    mo = [
        r
        for r in demo.reports
        if re.search(r"\bMo\b", texts[r])
        and "Ellery" not in texts[r]
        and "Marcus" not in texts[r]
        and "7700900640" in re.sub(r"[\s+]", "", texts[r])
    ]
    assert mo, "one report must call the coordinator only 'Mo', with his number"
    joined = "\n".join(texts.values())
    for form in ("07700 900640", "+44 7700 900640", "07700900640"):
        assert form in joined, f"the number is never written as {form!r}"
    f2 = demo.site[LANDING_F2_REF]
    line_reports = [
        r
        for r in demo.used
        if f2 in demo.areas_of(r)
        and re.search(r"\bline\b", texts[r], re.IGNORECASE)
        and re.search(r"between cells|after lock-up", texts[r], re.IGNORECASE)
    ]
    assert len(line_reports) >= 4, "four F2 reports describe the line between cells"


# --- Handling (brief 5.3) -----------------------------------------------------------------------


def _custody(view: View) -> dict[str, str]:
    """Prisoner key -> the establishment of its one open custody (an end date of None)."""
    open_at: dict[str, list[str]] = {}
    for lk in view.links("HELD_AT", everything=True):
        if lk.last_seen is None:
            open_at.setdefault(lk.source, []).append(lk.target)
    assert all(len(v) == 1 for v in open_at.values())
    return {k: v[0] for k, v in open_at.items()}


def test_handling_one_secret_link_12_s2_20_a1_and_only_two_units(demo: View, scale: View) -> None:
    for view, secrets in ((demo, 1), (scale, 0)):
        items: list[Any] = [*view.plan.entities, *view.all_links]
        above = [i for i in items if i.handling.classification != "OFFICIAL"]
        assert len(above) == secrets
        assert all(i.handling.handling_code == "P" for i in items)
        units = {u for i in items for u in (i.handling.originator, i.handling.owning_unit)}
        assert units == {"fenwick-moor-security", "regional-intel-unit"}, "two units, both profiles"
        everything = pid_plan.links_at(view.plan, "chapter9", secret_cleared=True)
        analyst = pid_plan.links_at(view.plan, "chapter9", secret_cleared=False)
        assert len(everything) == len(view.all_links)
        assert len(analyst) == len(view.all_links) - secrets
    (secret,) = [
        i for i in [*demo.plan.entities, *demo.all_links] if i.handling.classification != "OFFICIAL"
    ]
    assert secret.handling.classification == "SECRET"
    assert (secret.link_type, secret.source, secret.target) == (
        "IN_CONFLICT_WITH", "principal", "calder_3",
    )  # fmt: skip
    assert secret.properties["reason"] == "covert source"
    assert secret.handling.originator == secret.handling.owning_unit == "regional-intel-unit"
    # Reports: 12 consult-originator, 20 covert-development, disjoint, across all 350.
    s2 = {r for r in demo.reports if demo.ent[r].handling.sanitisation_code == "S2"}
    a1 = {r for r in demo.reports if demo.ent[r].handling.action_code == "A1"}
    assert (len(s2), len(a1)) == (12, 20)
    assert not s2 & a1
    assert demo.ent["report:p2"].handling.sanitisation_code == "S2"
    assert len(a1 & demo.used) >= 3
    for view in (demo, scale):
        items = [*view.plan.entities, *view.all_links]
        assert {i.handling.sanitisation_code for i in items} <= {None, "S2"}
        assert {i.handling.action_code for i in items} <= {None, "A1"}
    # Who holds what in the demo: regional data at the regional unit, Fenwick Moor's at its own.
    regional = ["arrested_outside", "handset:pryce", "sim:pryce", PRYCE, "coordinator", "payer",
                *(f"outside_{i}" for i in range(1, 7)),
                "est:saltmarsh-grange", "est:brindle-heath", *sorted(a1)]  # fmt: skip
    for key in regional:
        h = demo.ent[key].handling
        assert (h.originator, h.owning_unit) == ("regional-intel-unit",) * 2, key
    for key in ("principal", "relay_1", "est:fenwick-moor", "cell:F2-14"):
        assert demo.ent[key].handling.owning_unit == "fenwick-moor-security", key
    for r in demo.reports - a1 - {PRYCE}:
        assert demo.ent[r].handling.owning_unit == "fenwick-moor-security", r
    # Both profiles: Fenwick Moor's data is local, every other establishment's data, its
    # visitors', its incidents' and its accounts', is regional.
    for view, fenwick in ((demo, "est:fenwick-moor"), (scale, "scale:est:fenwick-moor")):

        def expected(est: str, fenwick: str = fenwick) -> str:
            return "fenwick-moor-security" if est == fenwick else "regional-intel-unit"

        custody = _custody(view)
        assert set(custody) == {p.key for p in view.prisoners}
        unit_of: dict[str, str] = {}
        for prisoner in view.prisoners:
            h = prisoner.handling
            assert (h.originator, h.owning_unit) == (expected(custody[prisoner.key]),) * 2
            unit_of[prisoner.key] = h.owning_unit
        for est in view.of_type("Establishment"):
            assert est.handling.owning_unit == expected(est.key), est.key
        visited: dict[str, set[str]] = {}
        for lk in view.links("VISITED", everything=True):
            if lk.target in unit_of and lk.source not in unit_of:
                visited.setdefault(lk.source, set()).add(lk.target)
        for visitor, targets in visited.items():
            if visitor in CAST_PEOPLE:
                continue
            units = {unit_of[t] for t in targets}
            assert len(units) == 1, f"{visitor} visits prisoners of two units"
            assert view.ent[visitor].handling.owning_unit in units, visitor
            unit_of[visitor] = next(iter(units))
        for lk in view.links("USES", everything=True):
            owner = lk.source
            if owner in unit_of and view.etype(lk.target) == "Endpoint":
                assert view.ent[lk.target].handling.owning_unit == unit_of[owner], lk.target
        for lk in view.links("ROLE_IN", everything=True):
            incident = view.ent[lk.target]
            if ":bg:" in incident.key and lk.source in unit_of:
                assert incident.handling.owning_unit == unit_of[lk.source], incident.key


# --- The script's own numbers: J1, J2, J5, J7, chapter 6, the gaps, the finds --------------------


def _degree(links: Iterable[Any], key: str = "principal") -> int:
    return sum((lk.source == key) + (lk.target == key) for lk in links)


def test_j1_the_principal_has_49_links_as_the_analyst_and_50_cleared_to_secret(
    demo: View,
) -> None:
    after_chapter_4 = {
        "DEPICTS": 1, "HELD_AT": 1, "MEMBER_OF": 1, "FAMILY_OF": 1, "CO_DEFENDANT_OF": 2,
        "USES": 2, "PRESENT_AT": 5, "MENTIONED_IN": 4, "VISITED": 12, "SHARED_CELL_WITH": 7,
        "PASSES_ITEMS_TO": 3, "ASSOCIATE_OF": 2, "ROLE_IN": 6, "IN_CONFLICT_WITH": 2,
    }  # fmt: skip
    act_1 = {k: v for k, v in after_chapter_4.items() if k != "MENTIONED_IN"}
    assert sum(after_chapter_4.values()) == 49 and sum(act_1.values()) == 45
    assert pid_plan.PRINCIPAL_LINK_COUNT == 49 and pid_plan.PRINCIPAL_LINK_COUNT_SECRET == 50
    assert pid_plan.PRINCIPAL_LINK_COUNT_ACT1 == 45
    assert pid_plan.PRINCIPAL_LINK_COUNT_ACT1_SECRET == 46
    assert Counter(pid_plan.PRINCIPAL_LINKS_BY_TYPE) == Counter(after_chapter_4)
    for moment, counts, plain, secret in (
        ("seed", act_1, 45, 46),
        ("chapter4", after_chapter_4, 49, 50),
    ):
        analyst = pid_plan.links_at(demo.plan, moment, secret_cleared=False)  # type: ignore[arg-type]
        cleared = pid_plan.links_at(demo.plan, moment, secret_cleared=True)  # type: ignore[arg-type]
        assert _degree(analyst) == plain, moment
        assert _degree(cleared) == secret, moment
        touching = [lk for lk in analyst if "principal" in (lk.source, lk.target)]
        assert Counter(lk.link_type for lk in touching) == Counter(counts), moment
        # His picture link is among them, because "With all links" returns and counts it.
        assert any(
            lk.link_type == "DEPICTS" and lk.source == "picture:principal" for lk in touching
        )
        # The one more is the SECRET link.
        extra = [
            lk for lk in cleared if "principal" in (lk.source, lk.target) and lk not in analyst
        ]
        assert [(lk.link_type, lk.target) for lk in extra] == [("IN_CONFLICT_WITH", "calder_3")]
    # What chapter 4 adds to the principal's star is exactly his four reports.
    seed_keys = {lk.key for lk in demo.at("seed")}
    added = [lk for lk in demo.at("chapter4") if lk.key not in seed_keys]
    assert all(
        demo.etype(lk.target) == "Document" or demo.etype(lk.source) == "Document" for lk in added
    )
    assert {lk.target for lk in added if lk.source == "principal"} == {
        "report:p1", "report:p2", "report:p3", PRYCE,
    }  # fmt: skip
    assert {lk.key for lk in demo.plan.links_of("principal")} >= {
        lk.key for lk in demo.at("chapter4") if "principal" in (lk.source, lk.target)
    }


def _repository_text_files() -> Iterable[Path]:
    """Source files of the four places the search covers, leaving out the PID's own files."""
    core = Path(demo_fixtures.__file__).resolve().parents[2]
    roots = [
        Path(__file__).resolve().parents[1],
        core / "apps",
        core / "packages",
        core / "scripts",
    ]
    skip = {"node_modules", ".venv", "__pycache__", "dist", ".git", "licences"}
    suffixes = {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".mjs",
        ".json",
        ".yaml",
        ".yml",
        ".csv",
        ".md",
        ".txt",
    }
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in suffixes and not skip & set(path.parts):
                if not path.name.startswith(("pid_", "test_pid_")):
                    yield path


def _national(digits: str) -> str:
    """A run of digits reduced to its national significant number: no `0044` or `44` country
    code, no trunk `0`."""
    if digits.startswith("0044"):
        digits = digits[4:]
    elif digits.startswith("44") and len(digits) >= 11:
        digits = digits[2:]
    return digits[1:] if digits.startswith("0") else digits


def _writes(text: str, national: set[str]) -> bool:
    """Whether any run of digits (with spaces, hyphens, brackets and a `+`) in the text is one
    of the numbers, however it is spaced or prefixed."""
    for run in re.finditer(r"[+\d](?:[\d \t+()-]*\d)?", text):
        if _national(re.sub(r"\D", "", run.group(0))) in national:
            return True
    return False


def test_j2_four_pin_accounts_call_the_coordinators_number(demo: View, tmp_path: Path) -> None:
    number = demo.ent["number:coordinator"]
    assert number.properties["value_raw"] == "07700 900640"
    assert msisdn("07700 900640") == msisdn("+44 7700 900640") == "+447700900640"
    assert msisdn(str(number.properties["value_raw"])) == "+447700900640"
    assert number.properties["value_normalised"] == "+447700900640"
    ones = [
        e.key
        for e in demo.of_type("Endpoint")
        if e.properties["value_normalised"] == "+447700900640"
    ]
    assert ones == ["number:coordinator"], "exactly one Endpoint carries the coordinator's number"
    unidentified = demo.ent["number:unidentified"].properties
    other = msisdn(str(unidentified["value_raw"]))
    assert other == unidentified["value_normalised"] != "+447700900777"
    four = {"pin:principal", "pin:relay_1", "pin:relay_2", "pin:relay_3"}
    for moment in ("seed", "chapter4"):
        callers = {
            lk.source
            for lk in demo.at(moment)
            if lk.link_type == "COMMUNICATED_WITH" and lk.target == "number:coordinator"
        }
        assert callers == four, moment
    assert {
        lk.source
        for lk in demo.at("chapter9")
        if lk.link_type == "COMMUNICATED_WITH" and lk.target == "number:coordinator"
    } == four | {"sim:batch2"}
    for pin in four:
        assert demo.ent[pin].properties["endpoint_kind"] == "handle"
        assert str(demo.ent[pin].properties["value_normalised"]).startswith("PIN-")
    owners = {
        lk.source
        for lk in demo.links("USES")
        if lk.target in four and demo.etype(lk.source) == "Person"
    }
    assert owners == {"principal", "relay_1", "relay_2", "relay_3"}
    # What each of them calls, from the call aggregates the stage-5 file is written from.
    callees: dict[str, set[str]] = {}
    for call in demo.plan.calls:
        callees.setdefault(call.pin, set()).add(call.number)
    assert callees["pin:principal"] == {"number:coordinator", "number:unidentified"}
    assert callees["pin:relay_1"] == {"number:coordinator"}
    assert callees["pin:relay_3"] == {"number:coordinator"}
    calls_to = [lk for lk in demo.links("COMMUNICATED_WITH") if lk.target == "number:unidentified"]
    assert {lk.source for lk in calls_to} == {
        "pin:principal", "pin:relay_2", "pin:brother", "sim:pryce",
    }  # fmt: skip
    assert all(lk.occurrences == (30 if lk.source == "sim:pryce" else 12) for lk in calls_to)
    assert all(_as_date(lk.first_seen) >= date(2026, 1, 1) for lk in calls_to)
    # Neither of the two numbers is written in any other file of the repository, so a search for
    # either finds the PID's data and nothing else.
    national = {"7700900640", _national(re.sub(r"\D", "", str(other)))}
    # The search is shown able to find each way of writing the number, in a file of its own.
    for i, form in enumerate(
        ("07700 900640", "+44 7700 900640", "447700900640", "0044 7700 900640", "07700 900 640",
         "+44 (0)7700 900640", "7700900640"),
    ):  # fmt: skip
        planted = tmp_path / f"planted_{i}.txt"
        planted.write_text(f"ring {form} after lock-up\n")
        assert _writes(planted.read_text(), national), f"the search misses {form!r}"
    assert not _writes("ring 07700 900641 and 0116 496 0000 and 20260430", national)
    searched = 0
    for path in _repository_text_files():
        searched += 1
        assert not _writes(path.read_text(errors="ignore"), national), (
            f"{path} writes a number the PID's search relies on"
        )
    assert searched > 200, f"the search read only {searched} files"


def test_j5_principal_and_relay_4_are_two_degrees_apart_by_6_routes(demo: View) -> None:
    assert pid_plan.PAIR_DEGREES == 2
    assert pid_plan.PAIR_ROUTES == 6 and pid_plan.PAIR_ROUTES_ACT1 == 5
    for moment, expected in (
        ("seed", pid_plan.PAIR_ROUTES_ACT1),
        ("chapter4", pid_plan.PAIR_ROUTES),
    ):
        links = demo.at(moment)
        adj = _adjacency(links)
        assert adj["principal"].get("relay_4", 0) == 0, "no direct link of any type"
        assert _distance(links, "principal", "relay_4") == pid_plan.PAIR_DEGREES, moment
        # Two-link routes, counted per pair of links: every type, inferred and DEPICTS included.
        routes = sum(
            adj["principal"][x] * adj["relay_4"][x]
            for x in adj["principal"]
            if x != "relay_4" and x in adj["relay_4"]
        )
        assert routes == expected, moment
        assert not any(lk.link_type == "NOT_SAME_AS" for lk in links)
    assert (pid_plan.PAIR_ROUTES, pid_plan.PAIR_ROUTES_ACT1) == (6, 5)
    # The J5 intrusion check: every link between the cast and the background is one of four
    # kinds, and only these (15.3). (a) a named cast PIN account calls an outside number; (b) a
    # seized SIM calls an outside number; (c) larkhill_1/2, calder_1..7 and cellmate_1..4 have
    # background cell-mates, in cells that are not cast cells; (d) the structural links, the
    # report links and the pictures.
    cast = demo.cast_keys()
    devices = {e.key for e in demo.of_type("Device")}
    sims = {e.key for e in demo.of_type("Endpoint") if e.properties.get("endpoint_kind") == "imsi"}
    actors = (CAST_PEOPLE | CAST_ENDPOINTS | devices | sims) & set(demo.ent)
    cast_cells = {f"cell:{c}" for c in CAST_CELLS}
    roommates = {*(f"larkhill_{i}" for i in (1, 2)), *(f"calder_{i}" for i in range(1, 8)),
                 *(f"cellmate_{i}" for i in range(1, 5))}  # fmt: skip
    found: Counter[str] = Counter()
    for link in demo.all_links:
        for here, there in ((link.source, link.target), (link.target, link.source)):
            if here not in actors or there in cast:
                continue
            outside_number = demo.ent[there].properties.get("endpoint_kind") == "msisdn"
            call = link.link_type == "COMMUNICATED_WITH" and here == link.source and outside_number
            if call and here in PIN_CALLERS:
                kind = "a"
            elif call and here in sims:
                kind = "b"
            elif (
                link.link_type == "SHARED_CELL_WITH"
                and here in roommates
                and demo.etype(there) == "Person"
                and there not in CAST_PEOPLE
            ):
                kind = "c"
            elif (
                link.link_type == "PRESENT_AT"
                and here in roommates
                and there not in cast_cells
                and here == link.source
            ):
                kind = "c"
            elif link.link_type == "MENTIONED_IN" and there in demo.reports:
                kind = "d"
            else:
                raise AssertionError(
                    f"an uninvited link at the cast: {link.link_type} {link.source} {link.target}"
                )
            found[kind] += 1
    assert set(found) == {"a", "b", "c", "d"}, found
    # The principal and relay_1..5 share cells with nobody but as the table says.
    table = {
        "principal": {"cellmate_1", "cellmate_2", "cellmate_3", "relay_2", "cellmate_4",
                      "relay_3", "relay_1"},
        "relay_1": {"principal"}, "relay_2": {"principal"}, "relay_3": {"principal"},
        "relay_4": set(), "relay_5": set(),
    }  # fmt: skip
    for who, partners in table.items():
        got = {
            lk.target if lk.source == who else lk.source
            for lk in demo.all_links
            if lk.link_type == "SHARED_CELL_WITH" and who in (lk.source, lk.target)
        }
        assert got == partners, who
    for link in demo.links("PRESENT_AT", everything=True):
        if link.target in cast_cells:
            assert link.source in cast, f"{link.source} occupies a cast cell"
    for who in ("brother", "third_member"):
        assert not [
            lk
            for lk in demo.all_links
            if lk.link_type == "SHARED_CELL_WITH" and who in (lk.source, lk.target)
        ], who


def test_j5_the_unconnected_prisoner_has_no_route(demo: View) -> None:
    assert "unconnected" in demo.ent
    for everything in (False, True):  # the analyst's view, then the view cleared to SECRET
        reach = demo.component("unconnected", everything=everything)
        assert "principal" not in reach
        assert "relay_4" not in reach
        assert "est:fenwick-moor" not in reach and "est:saltmarsh-grange" not in reach
        assert "est:brindle-heath" in reach
    # Brindle Heath is its own component: nothing, of any kind, joins it to the other two.
    brindle = demo.component("est:brindle-heath", everything=True)
    for other in ("est:fenwick-moor", "est:saltmarsh-grange"):
        assert not brindle & demo.component(other, everything=True)
    called_inside = {c.number for c in demo.plan.calls if c.pin in brindle}
    called_outside = {c.number for c in demo.plan.calls if c.pin not in brindle}
    assert not called_inside & called_outside, "no number is called from both components"
    held_there = {
        lk.source
        for lk in demo.links("HELD_AT", everything=True)
        if lk.target == "est:brindle-heath"
    }
    assert len(held_there) == 120 and held_there <= brindle


def _subgraph(view: View, keys: set[str], links: list[Any]) -> Subgraph:
    prov = Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="pid-plan", locator="plan", excerpt_hash="0")],
        first_seen=EPOCH,
    )
    handling = Handling(
        classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
    )
    audit = AuditStub(created_at=EPOCH, created_by="test")
    return Subgraph(
        nodes=[
            Node(id=k, type=view.etype(k), provenance=prov, handling=handling, audit=audit)
            for k in sorted(keys)
        ],
        edges=[
            Edge(
                id=lk.key, type=lk.link_type, source=lk.source, target=lk.target,
                provenance=prov, handling=handling, audit=audit,
            )
            for lk in links
        ],
    )  # fmt: skip


async def test_j7_the_principal_ranks_first_by_betweenness_then_the_relays_who_call_the_coordinator(
    demo: View,
) -> None:
    assert pid_plan.PRINCIPAL_BETWEENNESS == pid_plan.PRINCIPAL_BETWEENNESS_ACT1 == 0.87
    for moment, expected in (
        ("seed", pid_plan.PRINCIPAL_BETWEENNESS_ACT1),
        ("chapter4", pid_plan.PRINCIPAL_BETWEENNESS),
    ):
        # The working set, from the spec's own words: the principal, every far end of his visible
        # links, the coordinator's number and every far end of its visible links.
        visible = demo.at(moment)
        adj = _adjacency(visible)
        keys = {"principal"} | set(adj["principal"])
        keys |= {"number:coordinator"} | set(adj["number:coordinator"])
        links = [
            lk
            for lk in visible
            if lk.source in keys and lk.target in keys and lk.source != lk.target
        ]
        helper_keys, helper_links = pid_plan.j7_working_set(demo.plan, moment=moment)  # type: ignore[arg-type]
        assert set(helper_keys) == keys, moment
        assert {lk.key for lk in helper_links} == {lk.key for lk in links}, moment
        if moment == "seed":
            assert not keys & demo.reports, "no report is loaded yet in Act 1"
        result = await ComputeRustworkxAdapter().centrality(
            CentralityRequest(subgraph=_subgraph(demo, keys, links), metric="betweenness")
        )
        ranked = sorted(result.items(), key=lambda kv: kv[1], reverse=True)
        assert ranked[0][0] == "principal", moment
        assert ranked[0][1] >= 2 * ranked[1][1], moment
        assert {k for k, _ in ranked[1:4]} == {"relay_1", "relay_2", "relay_3"}, moment
        assert round(result["principal"], 2) == expected, moment
    assert (
        pid_plan.j7_working_set(demo.plan)[0]
        == pid_plan.j7_working_set(demo.plan, moment="chapter4")[0]
    ), "the default moment is chapter 4"


def test_ch6_the_coordinator_visits_the_principal_and_one_payer_funds_three_prisoners(
    demo: View,
) -> None:
    visits = {
        (lk.source, lk.target): lk for lk in demo.links("VISITED") if lk.source == "coordinator"
    }
    assert visits[("coordinator", "principal")].occurrences == 9
    assert visits[("coordinator", "principal")].properties["channel"] == "in_person"
    assert visits[("coordinator", "relay_3")].occurrences == 4
    assert visits[("coordinator", "relay_3")].properties["channel"] == "video"
    paid = [lk for lk in demo.links("VISITED") if lk.source == "payer" or lk.target == "payer"]
    # The table reads "VISITED coordinator -> principal (9), payer (6) ...": each visits him.
    assert [(lk.source, lk.target) for lk in paid] == [("payer", "principal")]
    assert paid[0].occurrences == 6 and paid[0].properties["channel"] == "in_person"
    # The six outside associates are visitors (Brief 2 R7 loads a visit, not an association).
    for i in range(1, 7):
        (visit,) = [lk for lk in demo.links("VISITED") if lk.source == f"outside_{i}"]
        assert (visit.target, visit.occurrences) == ("principal", 2)
        assert visit.properties["channel"] == "in_person"
    assert {
        lk.target if lk.source == "principal" else lk.source
        for lk in demo.links("ASSOCIATE_OF")
        if "principal" in (lk.source, lk.target)
    } == {"larkhill_1", "larkhill_2"}
    transfers = demo.links("TRANSACTED")
    from_payer = [lk for lk in transfers if lk.source == "account:payer"]
    assert {lk.target: lk.occurrences for lk in from_payer} == {
        "cash:principal": 8, "cash:relay_1": 7, "cash:relay_2": 7,
    }  # fmt: skip
    for lk in from_payer:
        assert lk.properties["transaction_type"] == "TRANSFER"
        assert float(lk.properties["amount"]) > 0
    funded = {
        link.source
        for link in demo.links("USES")
        if link.target in {lk.target for lk in from_payer} and demo.etype(link.source) == "Person"
    }
    assert funded == {"principal", "relay_1", "relay_2"}
    three = {"cash:principal", "cash:relay_1", "cash:relay_2"}
    into_cash = {lk.source for lk in transfers if lk.target in three}
    assert into_cash == {"account:payer"}, "one payer, not several"
    assert any(lk.source == "payer" and lk.target == "account:payer" for lk in demo.links("USES"))
    assert "coordinator" not in {lk.source for lk in demo.links("HELD_AT", everything=True)}
    # The shared-number pattern is present beside it: four PIN accounts, one number.
    assert (
        len(
            {
                lk.source
                for lk in demo.links("COMMUNICATED_WITH")
                if lk.target == "number:coordinator"
            }
        )
        == 4
    )


def test_the_four_gaps_are_absent_by_construction(demo: View) -> None:
    # 1. third_member is named in no document: no link to a text Document, no name in any text.
    for link in demo.all_links:
        if "third_member" in (link.source, link.target):
            other = link.target if link.source == "third_member" else link.source
            if demo.etype(other) == "Document":
                assert demo.ent[other].properties["media_kind"] == "image", (
                    f"third_member is joined to a text document by {link.link_type}"
                )
    third = demo.ent["third_member"].properties
    for text in demo.plan.report_texts.values():
        assert str(third["family_name"]).lower() not in text.lower()
    # 2. The unidentified number has no owner anywhere: only calls reach it, from PIN accounts
    # and from the SIM taken from Pryce, whose handset was found with nobody.
    owning = {"USES", "HOLDS", "PAIRED_WITH"}
    reaching = demo.touching("number:unidentified", everything=True)
    assert reaching and all(lk.link_type == "COMMUNICATED_WITH" for lk in reaching)
    assert {lk.source for lk in reaching} <= {e.key for e in demo.of_type("Endpoint")}
    for key in ("handset:pryce", "sim:pryce"):
        assert not [
            lk
            for lk in demo.touching(key, everything=True)
            if lk.link_type in ("USES", "HOLDS") or lk.target == key and lk.link_type == "USES"
        ], f"{key} has an owner"
    assert not any(
        lk.link_type in owning
        and demo.etype(lk.source if lk.target == "number:unidentified" else lk.target)
        in ("Person", "Organisation")
        for lk in reaching
    )
    # 3. The found account has no holder because it is nowhere in the data: it is written once,
    # in the text of the report about the arrest, and no entity carries it.
    assert "account:found" not in demo.ent
    for ent in demo.plan.entities:
        assert not any("SYN-00988" in str(v) for v in ent.properties.values()), ent.key
    mentioning = [r for r, text in demo.plan.report_texts.items() if "SYN-00988" in text]
    assert mentioning == [PRYCE]
    # 4. No person is linked to the act of throwing, by any link, in any direction.
    throw = {e.key for e in demo.throw_overs}
    persons = {e.key for e in demo.of_type("Person")}
    for link in demo.all_links:
        if link.source in throw or link.target in throw:
            other = link.target if link.source in throw else link.source
            assert other not in persons, f"{other} is linked to a throw-over by {link.link_type}"
    assert not any(lk.link_type == "ROLE_IN" and lk.target in throw for lk in demo.all_links)


def _present_on(view: View, cell: str, day: date) -> set[str]:
    out: set[str] = set()
    for lk in view.links("PRESENT_AT", everything=True):
        if lk.target != cell or view.etype(lk.source) != "Person":
            continue
        first = None if lk.first_seen is None else _as_date(lk.first_seen)
        last = None if lk.last_seen is None else _as_date(lk.last_seen)
        if (first is None or first <= day) and (last is None or last >= day):
            out.add(lk.source)
    return out


def test_phones_are_found_in_relay_cells_after_the_coordinators_calls_surge(demo: View) -> None:
    surge = date(2025, 12, 1)
    week_of_surge = (surge - date(2025, 9, 1)).days // 7
    assert week_of_surge == 13
    callers = {c.pin: c for c in demo.plan.calls if c.number == "number:coordinator"}
    assert set(callers) == {"pin:principal", "pin:relay_1", "pin:relay_2", "pin:relay_3"}
    last = pid_plan.CALL_WEEKS - 1
    for pin, call in callers.items():
        before = call.weekly[:week_of_surge]
        assert all(n <= 1 for n in before), "before December: a call, at most, a week"
        assert 6 <= sum(before) <= 7, "one call a fortnight"
        per_week = 9 if pin == "pin:principal" else 7
        assert all(n == per_week for n in call.weekly[week_of_surge:last]), pin
        # The week holding the cut-off is partial: calls stop on 30 April.
        assert 0 < call.weekly[last] <= per_week, pin
    principal = sum(callers["pin:principal"].weekly)
    for pin in ("pin:relay_1", "pin:relay_2", "pin:relay_3"):
        # The margin is over the whole call period.
        assert principal - sum(callers[pin].weekly) >= 40, pin
    find_days = (
        date(2026, 1, 5), date(2026, 2, 2), date(2026, 2, 20), date(2026, 3, 9),
        date(2026, 3, 28), date(2026, 4, 14), date(2026, 4, 27),
    )  # fmt: skip
    finds = {f"incident:find_0{i}": d for i, d in enumerate(find_days, 1)}
    relay_cells = {
        f"cell:F2-{n}": who
        for n, who in (
            ("14", "relay_1"),
            ("09", "relay_2"),
            ("21", "relay_3"),
            ("17", "relay_4"),
            ("18", "relay_5"),
        )  # fmt: skip
    }
    cell_of: dict[str, str] = {}
    for link in demo.links("OCCURRED_AT"):
        if link.source in finds:
            cell_of[link.source] = link.target
    assert set(cell_of) == set(finds)
    calls_of: dict[str, list[Any]] = {}
    for lk in demo.links("COMMUNICATED_WITH", everything=True):
        calls_of.setdefault(lk.source, []).append(lk)
    for n, (find, day) in enumerate(finds.items(), 1):
        props = demo.ent[find].properties
        assert props["category"] == "find" and props["item"] in ("mobile phone", "SIM card")
        assert _as_date(props["occurred_at"]) == day
        assert date(2026, 1, 5) <= day <= date(2026, 4, 30)
        assert day > surge, "the surge precedes the finds"
        cell = cell_of[find]
        assert cell in relay_cells, "a find is in a relay's cell"
        # Everyone in the cell on the day is its occupant (so the principal, for his two finds);
        # anyone else with a role keeps "participant".
        roles = {
            lk.source: lk.properties["role"] for lk in demo.links("ROLE_IN") if lk.target == find
        }
        occupants = {who for who, role in roles.items() if role == "occupant"}
        assert occupants == _present_on(demo, cell, day), find
        assert relay_cells[cell] in occupants
        assert all(role in ("occupant", "participant") for role in roles.values())
        if find in ("incident:find_01", "incident:find_06"):
            assert {"principal", "relay_1"} <= occupants
        # The handset found there: used by the relay it was found with, its SIM paired to it.
        handset, sim = f"handset:find_0{n}", f"sim:find_0{n}"
        assert demo.etype(handset) == "Device" and demo.etype(sim) == "Endpoint"
        users = [lk.source for lk in demo.links("USES") if lk.target == handset]
        assert users == [relay_cells[cell]], f"{handset} is found with the relay of {cell}"
        paired = [lk for lk in demo.links("PAIRED_WITH") if lk.source == sim]
        assert [lk.target for lk in paired] == [handset]
        assert re.fullmatch(r"00101\d{10}", str(demo.ent[sim].properties["value_normalised"]))
        outside = calls_of[sim]
        assert 2 <= len(outside) <= 4
        for lk in outside:
            assert demo.ent[lk.target].properties["endpoint_kind"] == "msisdn"
            assert lk.target not in ("number:coordinator", "number:unidentified")
    # Pryce's handset: found with nobody; its SIM calls the unidentified number thirty times.
    assert [lk for lk in demo.links("USES") if lk.target == "handset:pryce"] == []
    assert [lk.target for lk in demo.links("PAIRED_WITH") if lk.source == "sim:pryce"] == [
        "handset:pryce"
    ]
    (pryce_calls,) = calls_of["sim:pryce"]
    assert (pryce_calls.target, pryce_calls.occurrences) == ("number:unidentified", 30)
    assert date(2026, 1, 1) <= _as_date(pryce_calls.first_seen) <= _as_date(pryce_calls.last_seen)
    assert _as_date(pryce_calls.last_seen) <= date(2026, 3, 31)
    # No seized SIM calls the coordinator's number at the seed or after chapter 4.
    sims = {e.key for e in demo.of_type("Endpoint") if e.properties.get("endpoint_kind") == "imsi"}
    assert len(sims) == 9 and len(demo.of_type("Device")) == 9
    for moment in ("seed", "chapter4"):
        assert not [
            lk
            for lk in demo.at(moment)
            if lk.link_type == "COMMUNICATED_WITH"
            and lk.source in sims
            and lk.target == "number:coordinator"
        ], moment
    assert not [
        lk
        for lk in demo.all_links
        if lk.link_type == "PRESENT_AT" and demo.etype(lk.source) == "Device"
    ]
    # The chapter 9 batch: a second handset and SIM, found with relay_5 on 27 April, the SIM
    # calling the coordinator eight times in April; nothing else loads at chapter 9.
    (batch_use,) = [
        lk for lk in demo.all_links if lk.link_type == "USES" and lk.target == "handset:batch2"
    ]
    assert batch_use.source == "relay_2", "found in find_07, F2-09, with relay_2"
    assert _as_date(batch_use.first_seen) == _as_date(batch_use.last_seen) == date(2026, 4, 27)
    (batch_call,) = [
        lk
        for lk in demo.all_links
        if lk.source == "sim:batch2" and lk.link_type == "COMMUNICATED_WITH"
    ]
    assert (batch_call.target, batch_call.occurrences) == ("number:coordinator", 8)
    assert (
        date(2026, 4, 1)
        <= _as_date(batch_call.first_seen)
        <= _as_date(batch_call.last_seen)
        <= date(2026, 4, 30)
    )
    assert [
        lk.target
        for lk in demo.all_links
        if lk.link_type == "PAIRED_WITH" and lk.source == "sim:batch2"
    ] == ["handset:batch2"]
    moments = demo.plan.moment_of
    batch = {
        lk.key for lk in demo.all_links if {"handset:batch2", "sim:batch2"} & {lk.source, lk.target}
    }
    assert {k for k, m in moments.items() if m == "chapter9"} == batch
    # report:p2 and report:p3 are dated on the finds they describe, both hotspot days.
    assert _as_date(demo.ent["report:p2"].properties["sent_at"]) == finds["incident:find_07"]
    assert _as_date(demo.ent["report:p3"].properties["sent_at"]) == finds["incident:find_06"]
    assert finds["incident:find_07"] in demo.hotspot_days
    assert finds["incident:find_06"] in demo.hotspot_days
    assert "cell:F2-09" in [demo.etype(a) and a for a in demo.areas_of("report:p2")]
    assert "cell:F2-14" in demo.areas_of("report:p3")
    texts = demo.plan.report_texts
    assert "sim card" in texts["report:p2"].lower()
    assert "handset" in texts["report:p3"].lower() or "mobile phone" in texts["report:p3"].lower()


def test_passes_items_to_is_inferred_and_nothing_else_is(demo: View, scale: View) -> None:
    passes = demo.links("PASSES_ITEMS_TO", everything=True)
    assert {(lk.source, lk.target) for lk in passes} == {
        ("principal", "relay_1"), ("principal", "relay_2"), ("principal", "relay_3"),
        ("relay_1", "relay_4"), ("relay_4", "relay_5"),
    }  # fmt: skip
    assert len(passes) == 5
    for lk in passes:
        assert lk.provenance == "inferred"
        assert lk.extracted_by == "synthetic:pid-extraction-run"
        assert lk.extraction_confidence is not None and 0 < lk.extraction_confidence < 1
        assert lk.properties["channel"] == "cell line"
    for view in (demo, scale):
        for lk in view.all_links:
            if lk.link_type != "PASSES_ITEMS_TO":
                assert lk.provenance == "asserted", lk.key
                assert lk.extracted_by is None and lk.extraction_confidence is None, lk.key
    assert not scale.links("PASSES_ITEMS_TO", everything=True)


# --- Identifiers and numbers (D4, D5) ---------------------------------------------------------


def test_identifiers_are_synthetic_by_construction(demo: View, scale: View) -> None:
    numbers: dict[str, set[str]] = {}
    for name, view in (("demo", demo), ("scale", scale)):
        nums = [str(p.properties["prison_number"]) for p in view.prisoners]
        assert all(re.fullmatch(r"Z\d{4}ZZ", n) for n in nums)
        assert len(nums) == len(set(nums))
        numbers[name] = set(nums)
        pins = {
            str(e.properties["value_normalised"])
            for e in view.of_type("Endpoint")
            if e.properties.get("endpoint_kind") == "handle"
        }
        assert pins == {f"PIN-{n}" for n in nums}
        for e in view.of_type("Endpoint"):
            kind = e.properties.get("endpoint_kind")
            value = str(e.properties["value_normalised"])
            if kind == "handle":
                assert e.properties["handle"] == value
            if kind == "account":
                # An account carries no identifier of its own, as the PaySim fixture's do not.
                assert set(e.properties) == {"value_raw", "value_normalised", "endpoint_kind"}, (
                    e.key
                )
                if value.startswith("PC-"):
                    assert value[3:] in numbers[name], value
                else:
                    assert re.fullmatch(r"SYN-7\d{4}", value), (
                        f"{value} is outside SYN-70000..79999"
                    )
            if kind == "imsi":
                assert re.fullmatch(r"00101\d{10}", value), value
                assert imsi(value) == value and e.properties["imsi"] == value
        # Everyone is a prisoner (a prison number, no NINO) or not (a NINO beginning QQ).
        for p in view.of_type("Person"):
            nino = p.properties.get("nino")
            if "prison_number" in p.properties:
                assert nino is None, p.key
            else:
                assert re.fullmatch(r"QQ\d{6}[A-D]", str(nino)), f"{p.key} has no NINO"
        # A prisoner's PIN account belongs to the right person.
        owner_pin = {
            lk.target: lk.source for lk in view.links("USES") if view.etype(lk.target) == "Endpoint"
        }
        by_number = {str(p.properties["prison_number"]): p.key for p in view.prisoners}
        pin_key = {
            str(e.properties["value_normalised"]): e.key
            for e in view.of_type("Endpoint")
            if e.properties.get("endpoint_kind") == "handle"
        }
        for pin, key in pin_key.items():
            assert owner_pin[key] == by_number[pin[4:]], pin
        for e in view.of_type("Device"):
            value = str(e.properties["imei"])
            assert re.fullmatch(r"\d{15}", value) and value.startswith("00"), value
            assert _luhn_valid(value), f"{value} fails Luhn"
            assert imei(value) == value[:14]
    assert not numbers["demo"] & numbers["scale"]
    assert all(1000 <= int(n[1:5]) <= 2999 for n in numbers["demo"])
    assert all(5000 <= int(n[1:5]) <= 7999 for n in numbers["scale"])
    payer = str(demo.ent["account:payer"].properties["value_normalised"])
    assert re.fullmatch(r"SYN-7\d{4}", payer)
    assert {"PC-" + str(demo.ent[k].properties["prison_number"]) for k in
            ("principal", "relay_1", "relay_2")} <= {
        str(e.properties["value_normalised"]) for e in demo.of_type("Endpoint")
    }  # fmt: skip


def test_every_phone_number_is_a_drama_number_in_the_pid_blocks(demo: View, scale: View) -> None:
    seen: set[str] = set()
    for view in (demo, scale):
        for e in view.of_type("Endpoint"):
            if e.properties.get("endpoint_kind") != "msisdn":
                continue
            normalised = msisdn(str(e.properties["value_raw"]))
            assert normalised == e.properties["value_normalised"], e.key
            assert _in_pid_block(normalised), f"{normalised} is outside the PID's blocks"
            if "e164" in e.properties:
                assert e.properties["e164"] == normalised
            seen.add(normalised)
    unidentified = str(demo.ent["number:unidentified"].properties["value_normalised"])
    assert {"+447700900640", unidentified} <= seen
    assert unidentified != "+447700900777"
    assert 7_700_900_600 <= int(unidentified[3:]) <= 7_700_900_899
    # The teaching row's malformed number: a letter O for a nought. Refused as written; corrected
    # it is one of the background numbers, as a mistyped real number would be, and called
    # numbers stay 1,500.
    assert pid_plan.PID_TEACHING_BAD_NUMBER == "07700 900 6O3"
    with pytest.raises(NormalisationError):
        msisdn(pid_plan.PID_TEACHING_BAD_NUMBER)
    corrected = msisdn(pid_plan.PID_TEACHING_BAD_NUMBER.replace("O", "0"))
    assert corrected == "+447700900603" and _in_pid_block(corrected)
    background = {
        e.key for e in demo.of_type("Endpoint") if e.properties["value_normalised"] == corrected
    }
    assert len(background) == 1 and not background & {"number:coordinator", "number:unidentified"}
    assert len({c.number for c in demo.plan.calls}) == pid_plan.CALLED_NUMBERS == 1_500
    for view in (demo, scale):
        for ent in view.plan.entities:
            assert all("900 6O3" not in str(v) for v in ent.properties.values()), ent.key
    for text in demo.plan.report_texts.values():
        assert "900 6O3" not in text
    # Who owns a number: the coordinator, and each background visitor one, the one most often
    # called by the PIN of the first prisoner the visitor visits (ties to the lower number); no
    # number has two owners; nobody else owns one.
    calls: dict[str, Counter[str]] = {}
    for call in demo.plan.calls:
        calls.setdefault(call.pin, Counter())[call.number] += sum(call.weekly)
    pin_of = {
        lk.source: lk.target
        for lk in demo.links("USES")
        if demo.etype(lk.target) == "Endpoint"
        and demo.ent[lk.target].properties["endpoint_kind"] == "handle"
    }
    owned: dict[str, list[str]] = {}
    for lk in demo.links("USES"):
        if (
            demo.etype(lk.target) == "Endpoint"
            and demo.ent[lk.target].properties["endpoint_kind"] == "msisdn"
        ):
            owned.setdefault(lk.source, []).append(lk.target)
    assert set(owned["coordinator"]) == {"number:coordinator"}
    visitors = {
        e.key for e in demo.of_type("Person") if e.key not in CAST_PEOPLE and "nino" in e.properties
    }
    assert set(owned) == visitors | {"coordinator"}, "no other cast outsider owns a number"
    assert all(len(v) == 1 for v in owned.values())
    flat = [v[0] for v in owned.values()]
    assert len(flat) == len(set(flat)), "no number has two owners"
    assert "number:unidentified" not in flat
    first_visit: dict[str, str] = {}
    for lk in demo.links("VISITED"):
        if lk.source in visitors:
            first_visit.setdefault(lk.source, lk.target)
    taken: set[str] = set()
    brindle = demo.component("est:brindle-heath", everything=True)
    for visitor in sorted(visitors):
        prisoner = first_visit[visitor]
        ranked = sorted(calls[pin_of[prisoner]].items(), key=lambda kv: (-kv[1], kv[0]))
        mine = owned[visitor][0]
        assert mine in dict(ranked), f"{visitor} owns a number its prisoner's PIN does not call"
        free = [n for n, _c in ranked if n not in taken]
        assert mine == free[0], f"{visitor} did not take the most called free number"
        taken.add(mine)
        assert (visitor in brindle) == (mine in brindle), "Brindle Heath's visitors, its numbers"
    mobiles = {n for n in seen if n.startswith("+447700")}
    assert all(7_700_900_600 <= int(n[3:]) <= 7_700_900_899 for n in mobiles)
    assert any(n.startswith(("+441164960", "+441174960")) for n in seen), "geographic numbers too"
    for text in demo.plan.report_texts.values():
        for number in _uk_numbers(text):
            assert _in_pid_block(number), f"a report writes {number}"


_NINO = re.compile(r"[A-Z]{2}\d{6}[A-D]")
_PRISON_NUMBER = re.compile(r"[A-Z]\d{4}[A-Z]{2}")
_ACCOUNT_LIKE = re.compile(r"\b(?:SYN-\d{5}|PC-[\w-]+|PIN-[\w-]+)")


def _collect_others(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[set[str], int]:
    """Every UK number and every account, PIN, NINO and prison-number-shaped value that any other
    fixture or seed produces, from calling its generators; and how many generators were called."""
    refused = (
        "write_", "reset", "clear", "repair", "restore", "load", "delete", "authorise",
        "permitted", "resolve", "read_", "main",
    )  # fmt: skip

    def no_network(*_a: object, **_k: object) -> None:
        raise OSError("the plan's tests open no connection")

    def no_process(*_a: object, **_k: object) -> None:
        raise OSError("the plan's tests start no process")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    monkeypatch.setattr(os, "system", no_process)
    monkeypatch.chdir(tmp_path)

    names = [
        f"demo_fixtures.{m.name}"
        for m in pkgutil.iter_modules(list(demo_fixtures.__path__))
        if not m.name.startswith("pid_")
    ]
    scripts = importlib.import_module("scripts")  # strict: an import failure fails the test
    names += [
        f"scripts.{m.name}"
        for m in pkgutil.iter_modules(list(scripts.__path__))
        if m.name.startswith("seed_")
    ]
    strings: list[str] = []

    def walk(value: object, depth: int = 0) -> None:
        if depth > 8 or value is None or isinstance(value, bytes | int | float | datetime | date):
            return
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, Mapping):
            for k, v in value.items():
                walk(k, depth + 1)
                walk(v, depth + 1)
        elif isinstance(value, list | tuple | set | frozenset):
            for v in value:
                walk(v, depth + 1)
        elif inspect.isgenerator(value):
            for v in itertools.islice(value, 200_000):
                walk(v, depth + 1)
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            for f in dataclasses.fields(value):
                walk(getattr(value, f.name), depth + 1)
        elif callable(dump := getattr(value, "model_dump", None)):
            walk(dump(), depth + 1)

    called = 0
    for name in names:
        module = importlib.import_module(name)  # strict, as above
        for fname, member in inspect.getmembers(module):
            wrapped = inspect.isfunction(member) or hasattr(member, "__wrapped__")
            if fname.startswith("_") or not wrapped:
                continue
            fn = inspect.unwrap(member)  # a functools-wrapped generator is called as itself
            if getattr(fn, "__module__", None) != module.__name__ or not inspect.isfunction(fn):
                continue
            if fname.startswith(refused) or inspect.iscoroutinefunction(fn):
                continue
            params = inspect.signature(fn).parameters.values()
            if any(
                p.default is inspect.Parameter.empty
                and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                for p in params
            ):
                continue
            state = random.getstate()
            try:
                random.seed(pid_plan.SEED)  # a generator that draws unseeded is made repeatable
                walk(fn())
                called += 1
            except (Exception, SystemExit):  # a generator that needs more than its defaults
                continue
            finally:
                random.setstate(state)  # the global generator is left as found
    for csv in Path(demo_fixtures.__file__).parent.rglob("*.csv"):
        strings.append(csv.read_text(errors="ignore"))
    found: set[str] = set()
    for text in strings:
        if any(ch.isdigit() for ch in text):
            found |= _uk_numbers(text)
            found |= set(_NINO.findall(text)) | set(_PRISON_NUMBER.findall(text))
            found |= set(_ACCOUNT_LIKE.findall(text))
    return found, called


def test_no_pid_number_is_produced_by_any_other_fixture_or_seed(
    demo: View, scale: View, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    others, called = _collect_others(monkeypatch, tmp_path)
    assert others, "discovery collected nothing"
    assert called >= 5, f"discovery called only {called} generators"
    # The discovery reached the Ledger fixture, the older prison fixture and the scenario seed
    # without naming them.
    sentinels = {
        "+447700900461", "+447700900100", "+447700900999", "+447700900500",
        "SYN-40001", "QQ100000A",
    }  # fmt: skip
    assert sentinels <= others, f"{called} generators called; missing {sorted(sentinels - others)}"
    if not any(_PRISON_NUMBER.fullmatch(x) for x in others):
        warnings.warn(
            "no generator produces a prison-number-shaped value, so the prison numbers' "
            "disjointness from other generators is untested",
            stacklevel=1,
        )
    mine: set[str] = set()
    for view in (demo, scale):
        for e in view.plan.entities:
            if e.entity_type == "Endpoint":
                mine.add(str(e.properties["value_normalised"]))
            if "nino" in e.properties:
                mine.add(str(e.properties["nino"]))
            if "prison_number" in e.properties:
                mine.add(str(e.properties["prison_number"]))
    for text in demo.plan.report_texts.values():
        mine |= _uk_numbers(text)
    assert len(mine) >= 1_500 + 1_000
    assert not mine & others, f"values another fixture also produces: {sorted(mine & others)[:5]}"


# --- Weights (D3, Amendment 7 decision 2) ----------------------------------------------------


def test_cell_share_occurrences_are_weeks_shared_rounded_up(demo: View, scale: View) -> None:
    for view in (demo, scale):
        shares = view.links("SHARED_CELL_WITH", everything=True)
        assert shares
        for lk in shares:
            assert lk.first_seen is not None and lk.last_seen is not None, lk.key
            days = (_as_date(lk.last_seen) - _as_date(lk.first_seen)).days + 1
            assert days >= 1
            assert lk.occurrences == math.ceil(days / 7), lk.key
            assert "cell" in lk.properties
    weeks = {
        (lk.target if lk.source == "principal" else lk.source): lk.occurrences
        for lk in demo.links("SHARED_CELL_WITH", everything=True)
        if "principal" in (lk.source, lk.target)
    }
    assert weeks == {
        "cellmate_1": 19, "cellmate_2": 12, "cellmate_3": 1, "relay_2": 21,
        "cellmate_4": 3, "relay_3": 8, "relay_1": 20,
    }  # fmt: skip
    # The dates the weeks come from are the cell history the spec gives.
    spans = {
        (lk.target if lk.source == "principal" else lk.source): (
            _as_date(lk.first_seen),
            _as_date(lk.last_seen),
        )
        for lk in demo.links("SHARED_CELL_WITH", everything=True)
        if "principal" in (lk.source, lk.target)
    }
    assert spans["relay_2"] == (date(2025, 5, 5), date(2025, 9, 28))
    assert spans["relay_1"] == (date(2025, 12, 15), date(2026, 4, 30))


def _circle(view: View, moment: str = "chapter4") -> list[Any]:
    visible = view.at(moment)
    used = {
        lk.target
        for lk in [lk for lk in visible if lk.link_type == "USES"]
        if lk.source == "principal" and view.etype(lk.target) == "Endpoint"
    }
    exchange: set[str] = set()
    for lk in visible:
        if lk.link_type in ("COMMUNICATED_WITH", "TRANSACTED"):
            if lk.source in used:
                exchange.add(lk.target)
            if lk.target in used:
                exchange.add(lk.source)
    centre = {"principal"} | used | exchange
    return [lk for lk in visible if lk.source in centre or lk.target in centre]


def _circle_verdict(
    view: View, rules: Any, *, now: datetime, zero_recency: bool, moment: str = "chapter4"
) -> dict[str, Any]:
    pair: Counter[tuple[str, str, str]] = Counter()
    degree: Counter[tuple[str, str]] = Counter()
    total: Counter[str] = Counter()
    # The store's corpus counts are not filtered by clearance; the batch is not loaded at chapter 4.
    for lk in view.at(moment, cleared=True):
        pair[(lk.link_type, lk.source, lk.target)] += lk.occurrences
        total[lk.link_type] += lk.occurrences
        degree[(lk.link_type, lk.source)] += lk.occurrences
        degree[(lk.link_type, lk.target)] += lk.occurrences  # a self-loop counts twice
    circle = _circle(view, moment)
    weights: dict[str, float] = {}
    for lk in circle:
        comp = WeightComponents(
            occurrences=lk.occurrences,
            corpus_pair_count=pair[(lk.link_type, lk.source, lk.target)],
            corpus_source_degree=degree[(lk.link_type, lk.source)],
            corpus_target_degree=degree[(lk.link_type, lk.target)],
            corpus_total_occurrences=total[lk.link_type],
            computed_at=now,
        )
        valid_to = None if lk.last_seen is None else _utc(lk.last_seen)
        if zero_recency and valid_to is not None:
            valid_to = datetime(1900, 1, 1, tzinfo=UTC)
        weights[lk.key] = compute_weight(
            comp, edge_type=lk.link_type, valid_to=valid_to, now=now, rules=rules,
            self_loop=lk.source == lk.target,
        )  # fmt: skip
    n = len(circle)

    def key_of(link_type: str, a: str, b: str) -> str:
        (match,) = [
            lk for lk in circle
            if lk.link_type == link_type and {lk.source, lk.target} == {a, b}
        ]  # fmt: skip
        return str(match.key)

    def heavy(k: str) -> int:  # from the heavy end; a tie takes the worse place
        return sum(1 for v in weights.values() if v >= weights[k])

    def light(k: str) -> int:  # from the light end; a tie takes the worse place
        return sum(1 for v in weights.values() if v <= weights[k])

    call = heavy(key_of("COMMUNICATED_WITH", "pin:principal", "number:coordinator"))
    transfers = [
        heavy(key_of("TRANSACTED", "account:payer", f"cash:{who}"))
        for who in ("principal", "relay_1", "relay_2")
    ]
    lightest = [
        light(key_of("DEPICTS", "picture:principal", "principal")),
        light(key_of("SHARED_CELL_WITH", "principal", "cellmate_3")),
    ]
    quarter, eighth = math.ceil(n / 4), math.ceil(n / 8)
    return {
        "n": n, "call": call, "transfers": transfers, "lightest": lightest,
        "green": call <= 3 and max(transfers) <= quarter and max(lightest) <= eighth,
    }  # fmt: skip


def test_the_principals_circle_weighs_as_amendment_7_says(demo: View) -> None:
    # ADVISORY: the binding test is stage 5's, against a store. This one has to count itself.
    rules = load_weight_rules()
    cut = datetime(2026, 4, 30, 23, 59, 59, tzinfo=UTC)
    assert _as_date(pid_plan.CUT_OFF) == cut.date()
    for moment in ("seed", "chapter4"):
        circle = _circle(demo, moment)
        assert 55 <= len(circle) <= 66, (
            f"{moment}: the circle holds about 62 links, not {len(circle)}"
        )
        for zero_recency in (False, True):
            verdict = _circle_verdict(
                demo, rules, now=cut, zero_recency=zero_recency, moment=moment
            )
            assert verdict["green"], f"{moment}, zero_recency={zero_recency}: {verdict}"

    # The check can fail: three planted wrong rules turn it red at both points (rule 15).
    def planted(link_type: str, heavy: int) -> Any:
        wrong = dataclasses.replace(rules.rules[link_type], heavy=heavy)
        return dataclasses.replace(rules, rules={**rules.rules, link_type: wrong})

    for link_type, heavy in (
        ("TRANSACTED", 60),
        ("SHARED_CELL_WITH", 1),
        ("COMMUNICATED_WITH", 4000),
    ):
        for moment in ("seed", "chapter4"):
            for zero_recency in (False, True):
                verdict = _circle_verdict(
                    demo, planted(link_type, heavy), now=cut, zero_recency=zero_recency,
                    moment=moment,
                )  # fmt: skip
                assert not verdict["green"], (
                    f"{moment}: {link_type} heavy {heavy} should turn it red: {verdict}"
                )


# --- Volumes and structure ----------------------------------------------------------------------


def _holding(view: View) -> Counter[str]:
    return Counter(_custody(view).values())


def test_demo_volumes(demo: View) -> None:
    ests = demo.of_type("Establishment")
    assert {e.properties["name"] for e in ests} == {
        pid_plan.ESTABLISHMENT_NAME, "Saltmarsh Grange Prison", "Brindle Heath Prison",
    }  # fmt: skip
    assert len(ests) == 3 and pid_plan.ESTABLISHMENT_NAME == "Fenwick Moor Prison"
    fenwick = demo.ent["est:fenwick-moor"].properties
    assert fenwick["establishment_ref"] == "pid:est:fenwick-moor"
    assert (fenwick["niu_area"], fenwick["soct_region"], fenwick["security_category"]) == (
        "PID NIU Area 2", "PID SOCT Region South", "B",
    )  # fmt: skip
    assert len(demo.prisoners) == pid_plan.DEMO_PRISONERS == 1_000
    held = _holding(demo)
    assert held == Counter(
        {"est:fenwick-moor": 650, "est:saltmarsh-grange": 230, "est:brindle-heath": 120}
    )
    assert 10_000 <= len(demo.at("chapter9")) <= 15_000
    assert 10_000 <= len(demo.visible) <= 15_000
    # The estate: wings, landings, 30 cells a landing, twelve yards, chained by PART_OF.
    refs = list(demo.site)
    assert sum(r.startswith("pid:est1:wing:") for r in refs) == 6
    assert sum(r.startswith("pid:est2:wing:") for r in refs) == 2
    assert sum(r.startswith("pid:est3:wing:") for r in refs) == 1
    assert sum(r.startswith("pid:est1:yard:") for r in refs) == 12
    landings = [r for r in refs if r.startswith("pid:est1:landing:")]
    assert len(landings) == 12
    parents: dict[str, set[str]] = {}
    for lk in demo.links("PART_OF"):
        parents.setdefault(lk.source, set()).add(lk.target)
    cells = [r for r in refs if r.startswith("pid:est1:cell:")]
    assert len(cells) == 360
    for c in cells:
        assert len(parents[demo.site[c]]) == 1, f"{c} is in one landing"
    per_landing = Counter(next(iter(parents[demo.site[c]])) for c in cells)
    assert set(per_landing) == {demo.site[r] for r in landings}
    assert set(per_landing.values()) == {30}
    for landing in per_landing:
        (wing,) = parents[landing]
        assert ":est1:wing:" in str(demo.ent[wing].properties["site_ref"])
        assert parents[wing] - {demo.site[ZONE_REF]} == {"est:fenwick-moor"}
    # The call file: exactly the rows, the numbers and the PIN accounts the brief states.
    calls = demo.plan.calls
    assert sum(sum(c.weekly) for c in calls) == pid_plan.CALL_ROWS == 1_000_000
    assert len({c.number for c in calls}) == pid_plan.CALLED_NUMBERS == 1_500
    pins = {c.pin for c in calls}
    assert len(pins) == pid_plan.PIN_ACCOUNTS == 1_000
    assert pins == {
        e.key for e in demo.of_type("Endpoint") if e.properties.get("endpoint_kind") == "handle"
    }
    links = {
        (lk.source, lk.target): lk
        for lk in demo.links("COMMUNICATED_WITH", everything=True)
        if lk.source in pins
    }
    assert len(links) == len(calls), "one COMMUNICATED_WITH link per PIN aggregate"
    for call in calls:
        lk = links[(call.pin, call.number)]
        assert lk.occurrences == sum(call.weekly)
        weeks = [i for i, n in enumerate(call.weekly) if n]
        monday = date(2025, 9, 1).toordinal()
        first_week, last_week = monday + 7 * weeks[0], monday + 7 * weeks[-1]
        assert first_week <= _as_date(lk.first_seen).toordinal() <= first_week + 6
        assert last_week <= _as_date(lk.last_seen).toordinal() <= last_week + 6
        assert _as_date(lk.last_seen) <= _as_date(pid_plan.CUT_OFF)
    visitors = [e for e in demo.of_type("Person") if "nino" in e.properties]
    assert 500 <= len(visitors) <= 700


def test_scale_volumes(scale: View) -> None:
    ests = scale.of_type("Establishment")
    assert {e.properties["name"] for e in ests} == {
        "Fenwick Moor Prison", "Saltmarsh Grange Prison", "Brindle Heath Prison",
        "Corrie Vale Prison", "Thistlemoor Prison", "Wexcombe Down Prison",
    }  # fmt: skip
    assert len(scale.plan.entities) < 50_000, "ADR-007's node cap, the premise of the J8 ruling"
    assert len(scale.prisoners) == pid_plan.SCALE_PRISONERS == 3_000
    assert len(scale.all_links) == pid_plan.SCALE_LINKS == 30_000
    assert scale.plan.calls == ()
    assert scale.plan.picture_subjects == ()
    assert not scale.plan.report_texts
    assert not scale.of_type("Document"), "no reports and no pictures"
    assert all(k.startswith("scale:") for k in scale.ent)
    assert not set(scale.ent) & CAST_STATIC
    types = {lk.link_type for lk in scale.all_links}
    banned = {"COMMUNICATED_WITH", "MENTIONED_IN", "OCCURRED_AT", "DEPICTS", "PASSES_ITEMS_TO"}
    allowed = SPEC_ALLOWED_BACKGROUND - banned
    assert types <= allowed | {"MEMBER_OF"}
    assert allowed <= types, f"link types the scale case never uses: {sorted(allowed - types)}"
    assert not any(lk.handling.classification != "OFFICIAL" for lk in scale.all_links)
    assert all(e.key.startswith("scale:ocg:") for e in scale.of_type("Organisation"))


def test_every_type_property_and_end_is_declared_in_the_core_and_niem(
    demo: View, scale: View, ontology: Any
) -> None:
    entity_defs = {t.name: t for t in ontology.entity_types}
    edge_defs = {t.name: t for t in ontology.edge_types}
    niem = load_pack("niem")
    core = load_default_ontology()
    known_entities = {t.name for t in core.entity_types} | {e["name"] for e in niem["entity_types"]}
    known_edges = {t.name for t in core.edge_types} | {
        e["name"] for e in niem.get("edge_types", [])
    }
    foreign = set()
    for pack in ("fibo", "stix"):
        raw = load_pack(pack)
        foreign |= {e["name"] for e in raw.get("entity_types", [])}
        foreign |= {e["name"] for e in raw.get("edge_types", [])}
    foreign -= known_entities | known_edges
    problems: list[str] = []
    for view in (demo, scale):
        for ent in view.plan.entities:
            if ent.entity_type in foreign or ent.entity_type not in known_entities:
                problems.append(f"{ent.key}: type {ent.entity_type} is not core or NIEM")
                continue
            try:
                validate_properties(entity_defs[ent.entity_type], dict(ent.properties))
            except Exception as exc:
                problems.append(f"{ent.key}: {exc}")
        for lk in view.all_links:
            if lk.link_type in foreign or lk.link_type not in known_edges:
                problems.append(f"{lk.key}: link type {lk.link_type} is not core or NIEM")
                continue
            edge = edge_defs[lk.link_type]
            try:
                validate_properties(edge, dict(lk.properties))
                validate_edge_endpoints(
                    edge, source_type=view.etype(lk.source), target_type=view.etype(lk.target)
                )
            except Exception as exc:
                problems.append(f"{lk.key}: {exc}")
    assert not problems, f"{len(problems)} problems, first: {problems[:5]}"
    used = {e.entity_type for e in demo.plan.entities}
    assert {"Establishment", "Incident", "Location", "Endpoint", "Device", "Document"} <= used


def _open_cells(view: View) -> dict[str, list[str]]:
    """Prisoner key -> the cells of its open `PRESENT_AT` links (an end date of None)."""
    out: dict[str, list[str]] = {}
    for lk in view.links("PRESENT_AT", everything=True):
        ref = str(view.ent[lk.target].properties.get("site_ref", ""))
        if view.etype(lk.source) == "Person" and ":cell:" in ref and lk.last_seen is None:
            out.setdefault(lk.source, []).append(lk.target)
    return out


def test_the_bulk_list_is_the_40_prisoners_on_f2(demo: View, scale: View) -> None:
    on_f2 = demo.present_at_cut_off(LANDING_F2_REF)
    assert len(on_f2) == pid_plan.BULK_LIST_SIZE == 40
    assert {"principal", *(f"relay_{i}" for i in range(1, 6))} <= on_f2
    assert not on_f2 & {"cellmate_1", "cellmate_2", "cellmate_3", "cellmate_4", "third_member"}
    assert all(demo.ent[k].properties.get("prison_number") for k in on_f2)
    # The interface is the function; there is no module constant, and none is worked out on access.
    assert not hasattr(pid_plan, "BULK_LIST") and not hasattr(pid_plan, "__getattr__")
    listed = pid_plan.bulk_list(demo.plan)
    assert set(listed) == on_f2 and len(listed) == len(set(listed)) == 40
    # Nobody but the cast sleeps in a cast cell (the background never touches J1, J5 or J7).
    cast_cells = {f"cell:{c}" for c in CAST_CELLS}
    for key in sorted(cast_cells):
        occupants = {
            lk.source for lk in demo.links("PRESENT_AT", everything=True) if lk.target == key
        }
        assert occupants and occupants <= demo.cast_keys(), (key, occupants - demo.cast_keys())
    # Custody and places, in both profiles: one open custody and one open cell for every prisoner;
    # a closed stay carries its end; at most two people in any cell on any day.
    for view in (demo, scale):
        assert set(_custody(view)) == {p.key for p in view.prisoners}
        cells = _open_cells(view)
        assert set(cells) == {p.key for p in view.prisoners}
        assert all(len(v) == 1 for v in cells.values()), "exactly one open cell each"
        stays: dict[str, list[tuple[date, date]]] = {}
        for lk in view.links("PRESENT_AT", everything=True):
            if view.etype(lk.source) == "Person":
                first = date(1900, 1, 1) if lk.first_seen is None else _as_date(lk.first_seen)
                last = date(2999, 1, 1) if lk.last_seen is None else _as_date(lk.last_seen)
                assert first <= last
                stays.setdefault(lk.target, []).append((first, last))
        for cell, spans in stays.items():
            for first, _last in spans:
                assert sum(a <= first <= b for a, b in spans) <= 2, f"{cell} on {first}"

    def landing_of(cell: str) -> str:
        parts = {lk.source: lk.target for lk in demo.links("PART_OF")}
        return str(demo.ent[parts[cell]].properties["site_ref"]).rsplit(":", 1)[1]

    def wing_of(cell: str) -> str:
        return landing_of(cell)[0]

    placed = _open_cells(demo)
    for who in ("larkhill_1", "larkhill_2", "calder_1", "calder_2", "calder_3", "calder_4"):
        assert landing_of(placed[who][0]) == "F1", who
    for who in ("calder_5", "calder_6", "calder_7"):
        assert wing_of(placed[who][0]) == "E", who
    for who in ("cellmate_1", "cellmate_2", "cellmate_3", "cellmate_4"):
        assert landing_of(placed[who][0]) == "F1", who
    for who in ("larkhill_1", "larkhill_2", "cellmate_1", "cellmate_2", "cellmate_3", "cellmate_4"):
        assert placed[who][0] not in cast_cells, who
    group = {f"calder_{i}" for i in range(1, 8)} | {"larkhill_1", "larkhill_2"}
    assert not group & on_f2, "none of the group members is on F2"
    (stay,) = [
        lk for lk in demo.links("PRESENT_AT") if lk.source == "principal" and lk.last_seen is None
    ]
    assert stay.target == "cell:F2-14"
    # Every incident is at exactly one place; assaults and disorders are at a landing, a yard or
    # the visits hall, never in a cast cell, and only throw-overs carry the four properties.
    for inc in demo.of_type("Incident"):
        at = [lk for lk in demo.all_links if lk.link_type == "OCCURRED_AT" and lk.source == inc.key]
        assert len(at) == 1, f"{inc.key} must occur at exactly one place"
        ref = str(demo.ent[at[0].target].properties["site_ref"])
        if inc.properties["category"] in ("assault", "disorder"):
            assert any(f":{kind}:" in ref for kind in ("landing", "yard", "hall")), inc.key
        if inc.properties["category"] != "throw_over":
            assert not at[0].properties, inc.key


def test_every_picture_subject_has_one_depicts(demo: View, scale: View) -> None:
    subjects = set(demo.plan.picture_subjects)
    assert len(subjects) == len(demo.plan.picture_subjects)
    expected = {e.key for e in demo.of_type("Person")}
    expected |= {e.key for e in demo.of_type("Establishment")}
    expected |= {e.key for e in demo.of_type("Device")}
    expected |= {e.key for e in demo.of_type("Organisation")}
    expected |= {
        key
        for ref, key in demo.site.items()
        if ref.startswith(("pid:est1:wing:", "pid:est1:yard:"))
    }
    # No picture for any entity first loaded after the seed: Brief 2 attaches pictures at the
    # seed, before such an entity exists (Pryce, created by R9; the second handset).
    late = {k for k in demo.ent if _entity_moment(demo, k) != "seed"}
    assert {"arrested_outside", "handset:batch2", "sim:batch2"} <= late
    expected -= late
    assert not subjects & late and not {f"picture:{k}" for k in late} & set(demo.ent)
    assert subjects == expected
    assert len(expected & {k for k in demo.ent if demo.etype(k) == "Location"}) == 18
    depicts = demo.links("DEPICTS", everything=True)
    by_subject = Counter(lk.target for lk in depicts)
    assert set(by_subject) == subjects and set(by_subject.values()) == {1}
    for lk in depicts:
        assert lk.source == f"picture:{lk.target}"
        assert demo.ent[lk.source].entity_type == "Document"
        assert demo.ent[lk.source].properties["media_kind"] == "image"
        assert lk.properties["shown"] is True
    assert {e.key for e in demo.of_type("Document") if e.properties["media_kind"] == "image"} == {
        f"picture:{k}" for k in subjects
    }
    assert scale.plan.picture_subjects == () and not scale.links("DEPICTS", everything=True)


def test_no_pid_name_appears_in_any_other_fixture(demo: View, scale: View) -> None:
    names: set[str] = set()
    for view in (demo, scale):
        for e in view.of_type("Person"):
            names.add(str(e.properties["family_name"]))
        for kind in ("Organisation", "Establishment"):
            names |= {
                str(e.properties["name"]) for e in view.of_type(kind) if "name" in e.properties
            }
    # The staff the report texts name come under the same rule, and so does the zone's name;
    # generic place names ("Wing F", "Yard 03") are exempt.
    names |= set(pid_names.STAFF_NAMES)
    names.add(str(demo.ent[demo.site[ZONE_REF]].properties["name"]))
    assert len(names) >= 150
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    root = Path(demo_fixtures.__file__).parent
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("pid_")
    ]
    assert len(files) >= 5
    for path in files:
        hit = pattern.search(path.read_text(errors="ignore"))
        assert hit is None, f"{path.name} already uses the PID name {hit and hit.group(0)!r}"


def test_every_link_end_exists_and_keys_are_unique(demo: View, scale: View) -> None:
    for view in (demo, scale):
        plan = view.plan
        assert len(view.ent) == len(plan.entities), "entity keys are unique"
        assert len({lk.key for lk in plan.links}) == len(plan.links), "link keys are unique"
        for lk in plan.links:
            assert lk.source in view.ent and lk.target in view.ent, lk.key
            assert lk.occurrences >= 1, lk.key
            if lk.first_seen is not None and lk.last_seen is not None:
                assert _as_dt(lk.first_seen) <= _as_dt(lk.last_seen), lk.key
        for call in plan.calls:
            assert call.pin in view.ent and call.number in view.ent
        assert set(plan.report_texts) <= set(view.ent)
        assert set(plan.picture_subjects) <= set(view.ent)
        # Moments: every key is a link of the plan; the loads nest; reports load in chapter 4.
        assert set(plan.moment_of) <= {lk.key for lk in plan.links}
        assert set(plan.moment_of.values()) <= {"seed", "chapter4", "chapter9"}
        loaded = [
            {lk.key for lk in pid_plan.links_at(plan, m, secret_cleared=True)}
            for m in ("seed", "chapter4", "chapter9")
        ]
        assert loaded[0] <= loaded[1] <= loaded[2] == {lk.key for lk in plan.links}
        # Both ways: a link touching no report and none of the batch is "seed"; a link touching a
        # report is "chapter4"; exactly the links of the second seized handset are "chapter9".
        batch_ends = {"handset:batch2", "sim:batch2"}
        for lk in plan.links:
            moment = plan.moment_of.get(lk.key, "seed")
            ends = {lk.source, lk.target}
            if ends & batch_ends:
                assert moment == "chapter9", lk.key
            elif ends & view.reports:
                assert moment == "chapter4", lk.key
            else:
                assert moment == "seed", lk.key
        # Association and family join two prisoners, prison number to prison number (R13).
        prisoners = {p.key for p in view.prisoners}
        for lk in plan.links:
            if lk.link_type in ("ASSOCIATE_OF", "FAMILY_OF"):
                assert lk.source in prisoners and lk.target in prisoners, lk.key
        assert not [lk for lk in plan.links if lk.link_type == "HOLDS"]
        assert not [e for e in plan.entities if e.key.startswith("extract:")]
    with pytest.raises(KeyError):
        demo.plan.entity("no-such-key")
    for key in ("principal", "number:coordinator", "pin:principal", "est:fenwick-moor"):
        assert {lk.key for lk in demo.plan.links_of(key)} == {
            lk.key for lk in demo.all_links if key in (lk.source, lk.target)
        }
    assert demo.plan.entity("principal") == demo.ent["principal"]


def test_every_throw_over_link_agrees_with_its_incident_and_yard(demo: View) -> None:
    links = [
        lk for lk in demo.all_links if lk.link_type == "OCCURRED_AT" and lk.source in demo.yard_of
    ]
    assert len(links) == 262
    for lk in links:
        props = lk.properties
        assert set(props) == {"lat", "lon", "yard", "item_type"}, lk.key
        assert isinstance(props["lat"], float) and isinstance(props["lon"], float)
        assert isinstance(props["yard"], str) and isinstance(props["item_type"], str)
        assert props["yard"] == demo.yard_code(lk.target), lk.key
        assert props["item_type"] == demo.ent[lk.source].properties["item"], lk.key
    assert Counter(lk.properties["item_type"] for lk in links) == Counter(EXPECTED_ITEMS)
    assert Counter(lk.properties["yard"] for lk in links) == Counter(EXPECTED_YARDS)
    # Every other incident places itself without the four (none is required), once.
    others = [
        lk
        for lk in demo.all_links
        if lk.link_type == "OCCURRED_AT" and lk.source not in demo.yard_of
    ]
    assert others and all(not lk.properties for lk in others)
    per_incident = Counter(lk.source for lk in demo.all_links if lk.link_type == "OCCURRED_AT")
    assert set(per_incident) == {e.key for e in demo.of_type("Incident")}
    assert set(per_incident.values()) == {1}


# --- The load contract (15.1) -------------------------------------------------------------------

#: The CSV each Brief 2 recipe names; a shape of that recipe in any other file is a new file, and
#: carries a Brief 2 addition.
BRIEF_2_FILES = {
    "R1": "pid_nomis_prisoners.csv", "R2": "pid_nomis_cell_shares.csv",
    "R3": "pid_nomis_visits.csv", "R4": "pid_nomis_incidents.csv", "R5": "pid_pin_calls.csv",
    "R7": "pid_prisoner_money.csv", "R8": "pid_codefendants.csv", "R9": "pid_intel_reports.csv",
    "R10": "pid_throwover_log.csv", "R11": "pid_establishment_plan.csv",
    "R12": "pid_soc_nominals.csv", "R13": "pid_family_and_associates.csv",
}  # fmt: skip
RECIPES = {*(f"R{i}" for i in range(1, 14)), "seed"}
#: The files Brief 2 names, with R6's two batches: any other file is new.
KNOWN_FILES = {
    *BRIEF_2_FILES.values(),
    "pid_seized_comms_batch1.csv",
    "pid_seized_comms_batch2.csv",
}


def _recipe_ok(recipe: str) -> bool:
    return recipe in RECIPES or re.fullmatch(r"new:pid-[a-z0-9-]+", recipe) is not None


def _label(view: View, key: str) -> str:
    """An entity's type as a shape names it, with a discriminator where one type is written by
    more than one recipe: `Person:prisoner` (a prison number) against the outsiders told by
    origin, `Person:visitor` (created by R3's visits) and `Person:named` (created by R9 as a
    report's subject), `Endpoint:<endpoint_kind>`, `Incident:throw_over` against
    `Incident:other`, and `Location:<kind>` (zone, wing, landing, cell, yard, hall, place)."""
    ent = view.ent[key]
    if ent.entity_type == "Endpoint":
        return f"Endpoint:{ent.properties['endpoint_kind']}"
    if ent.entity_type == "Incident":
        throw = ent.properties["category"] == "throw_over"
        return "Incident:throw_over" if throw else "Incident:other"
    if ent.entity_type == "Location":
        return f"Location:{str(ent.properties['site_ref']).split(':')[-2]}"
    if ent.entity_type == "Person":  # told as the files key them: a prison number, or a NINO
        if "prison_number" in ent.properties:
            return "Person:prisoner"
        return "Person:visitor" if key in view.visitor_keys else "Person:named"
    return str(ent.entity_type)


def _link_moment(view: View, link: Any) -> str:
    return str(view.plan.moment_of.get(link.key, "seed"))


def _entity_moment(view: View, key: str) -> str:
    if key in view.reports or _label(view, key) == "Person:named":
        return "chapter4"  # a report, and the outsider R9 creates as its subject
    return "chapter9" if key in ("handset:batch2", "sim:batch2") else "seed"


def _shape_matches(shape: Any, link: Any, view: View) -> bool:
    return (
        shape.link_type == link.link_type
        and shape.source_type == _label(view, link.source)
        and shape.target_type == _label(view, link.target)
        and set(shape.properties) == set(link.properties)
        and shape.moment == _link_moment(view, link)
        and shape.source_key == view.area_column.get(link.key, shape.source_key)
    )


def _unmatched(view: View, shapes: Iterable[Any]) -> list[tuple[str, int]]:
    """Every link that does not match exactly one shape, with how many it matches."""
    shapes = list(shapes)
    bad = []
    for link in view.all_links:
        n = sum(_shape_matches(sh, link, view) for sh in shapes)
        if n != 1:
            bad.append((link.key, n))
    return bad


def test_every_plan_link_has_a_load_shape(demo: View, scale: View) -> None:
    shapes = pid_plan.LOAD_SHAPES
    assert shapes and len(
        {
            (sh.link_type, sh.source_type, sh.target_type, sh.properties, sh.moment, sh.source_key)
            for sh in shapes
        }
    ) == len(shapes)
    for view in (demo, scale):
        assert _unmatched(view, shapes) == [], "a link with no shape, or with two"
        labels = {_label(view, e.key).split(":")[0] for e in view.plan.entities}
        written = {t.split(":")[0] for sh in shapes for t in (sh.source_type, sh.target_type)}
        written |= {sh.entity_type.split(":")[0] for sh in pid_plan.ENTITY_SHAPES}
        assert labels <= written, f"entity types no shape writes: {sorted(labels - written)}"
    for sh in shapes:
        assert (
            isinstance(sh.properties, frozenset)
            and sh.columns
            and len(set(sh.columns)) == len(sh.columns)
        )
        # A column for each property and a key column for each end, said in the shape itself.
        assert sh.source_key in sh.columns and sh.target_key in sh.columns, sh
        assert sh.source_key != sh.target_key and set(sh.properties) <= set(sh.columns), sh
        assert sh.moment in ("seed", "chapter4", "chapter9"), sh
        assert _recipe_ok(sh.recipe), sh
        assert sh.handling in ("recipe", "column"), sh
        assert re.fullmatch(r"pid_[a-z0-9_]+\.csv", sh.file) or sh.recipe == "seed", sh
        if sh.recipe in BRIEF_2_FILES:
            assert sh.file == BRIEF_2_FILES[sh.recipe] or sh.brief2_addition, (
                f"{sh.file} is a new file for {sh.recipe}, so it needs its Brief 2 addition"
            )
        if sh.recipe == "R6":
            assert sh.file in ("pid_seized_comms_batch1.csv", "pid_seized_comms_batch2.csv")
    # A prisoner's PIN account is written by R5, beside its calls.
    (pin_shape,) = [
        x for x in shapes if x.link_type == "USES" and x.target_type == "Endpoint:handle"
    ]
    assert (pin_shape.file, pin_shape.recipe) == ("pid_pin_calls.csv", "R5")
    # The two carve-outs of ADR-120, and only those, load without a recipe.
    assert {(sh.link_type) for sh in shapes if sh.recipe == "seed"} == {
        "PASSES_ITEMS_TO",
        "DEPICTS",
    }
    # Shown red: take away the IN_CONFLICT_WITH shape and the check reports its links.
    without = [sh for sh in shapes if sh.link_type != "IN_CONFLICT_WITH"]
    red = _unmatched(demo, without)
    assert red
    assert {k for k, n in red} == {
        lk.key for lk in demo.all_links if lk.link_type == "IN_CONFLICT_WITH"
    }
    assert all(n == 0 for _k, n in red)
    # Shown red: an association of a prisoner with an outsider has no shape (R13 is prison number
    # to prison number), and the same link between two prisoners has.
    plant = types.SimpleNamespace(
        key="planted",
        link_type="ASSOCIATE_OF",
        source="relay_5",
        target="outside_2",
        properties={},
    )
    assert not any(_shape_matches(sh, plant, demo) for sh in shapes)
    plant.target = "relay_4"
    assert sum(_shape_matches(sh, plant, demo) for sh in shapes) == 1
    # Every new file's shapes, and only they, carry a "new:" recipe, and each says what Brief 2
    # must add.
    every: list[Any] = [*shapes, *pid_plan.ENTITY_SHAPES]
    new_shapes = [sh for sh in every if sh.file not in KNOWN_FILES and sh.recipe != "seed"]
    assert {sh.file for sh in new_shapes} >= {
        "pid_conflicts.csv", "pid_number_owners.csv", "pid_nomis_cell_stays.csv",
    }  # fmt: skip
    for new in new_shapes:
        assert new.recipe.startswith("new:"), f"{new.file} borrows the label {new.recipe}"
        assert new.brief2_addition, f"{new.file} is new and needs its addition"
    for sh in every:
        assert not sh.recipe.startswith("new:") or sh.file not in KNOWN_FILES, sh


def test_the_brief_2_additions_are_listed() -> None:
    added = {
        (sh.link_type, sh.source_type, sh.target_type): sh.brief2_addition
        for sh in pid_plan.LOAD_SHAPES
        if sh.brief2_addition is not None
    }
    entity_added = {
        sh.entity_type + "/" + ",".join(sorted(sh.properties)): sh.brief2_addition
        for sh in pid_plan.ENTITY_SHAPES
        if sh.brief2_addition is not None
    }
    for text in [*added.values(), *entity_added.values()]:
        assert isinstance(text, str) and len(text.split()) >= 4
        assert text.rstrip().endswith("."), "one sentence each"
    expected = {
        ("IN_CONFLICT_WITH", "Person:prisoner", "Person:prisoner"): ("classification",),
        ("USES", "Person:visitor", "Endpoint:msisdn"): ("owner",),
        ("MENTIONED_IN", "Person:named", "Document"): ("outsider", "NINO"),
        ("USES", "Person:prisoner", "Device"): ("when",),
        ("SHARED_CELL_WITH", "Person:prisoner", "Person:prisoner"): ("last day",),
        ("MENTIONED_IN", "Incident:throw_over", "Document"): ("incident_refs",),
        ("MENTIONED_IN", "Location:wing", "Document"): ("area_ref_2", "area_ref_3"),
        ("PART_OF", "Location:wing", "Location:zone"): ("zone", "parent"),
        ("PART_OF", "Location:yard", "Location:zone"): ("zone", "parent"),
        ("HELD_AT", "Person:prisoner", "Establishment"): ("interval",),
        ("PRESENT_AT", "Person:prisoner", "Location:cell"): ("interval",),
    }
    for triple, words in expected.items():
        assert triple in added, f"Brief 2 must be told to add {triple}"
        for word in words:
            assert word in added[triple], (triple, word)
    joined = " ".join([*added.values(), *entity_added.values()])
    assert "originator" in joined and "NINO" in joined, "per-row units, and subject columns"
    # The entity files: visitors' dates of birth, the nicknames, a throw-over's name, and the
    # three kinds of place R11 does not yet write.
    for label, word in (
        ("Person:visitor", "date_of_birth"),
        ("Person:named", "NINO"),
        ("Person:prisoner", "aliases"),
        ("Incident:throw_over", "name"),
        ("Location:zone", "zone"),
        ("Location:hall", "visits hall"),
        ("Location:place", "outside place"),
    ):
        assert any(
            sh.entity_type == label and sh.brief2_addition and word in sh.brief2_addition
            for sh in pid_plan.ENTITY_SHAPES
        ), (label, word)


def _entity_matches(sh: Any, view: View, key: str) -> bool:
    return (
        sh.entity_type == _label(view, key)
        and set(view.ent[key].properties) <= set(sh.properties)
        and sh.moment == _entity_moment(view, key)
    )


def test_every_plan_entity_has_a_shape(demo: View, scale: View) -> None:
    shapes = pid_plan.ENTITY_SHAPES
    assert shapes
    for view in (demo, scale):
        for ent in view.plan.entities:
            n = sum(_entity_matches(sh, view, ent.key) for sh in shapes)
            assert n == 1, f"{ent.key} {sorted(ent.properties)} matches {n} entity shapes"
    for sh in shapes:
        assert isinstance(sh.properties, frozenset) and sh.columns
        assert len(set(sh.columns)) == len(sh.columns)
        assert sh.key in sh.columns and set(sh.properties) <= set(sh.columns), sh
        assert sh.moment in ("seed", "chapter4", "chapter9"), sh
        assert _recipe_ok(sh.recipe) and sh.handling in ("recipe", "column"), sh
        assert re.fullmatch(r"pid_[a-z0-9_]+\.csv", sh.file) or sh.recipe == "seed", sh
        if sh.recipe in BRIEF_2_FILES:
            assert sh.file == BRIEF_2_FILES[sh.recipe] or sh.brief2_addition, sh.file
    # Shown red: without the throw-over shape the throw-overs match none.
    without = [sh for sh in shapes if sh.entity_type != "Incident:throw_over"]
    unmatched = {
        e.key
        for e in demo.plan.entities
        if sum(_entity_matches(sh, demo, e.key) for sh in without) != 1
    }
    assert unmatched == {e.key for e in demo.throw_overs}


def _row_handlings(view: View) -> dict[str, set[Any]]:
    """File -> every distinct handling among the plan's rows that go through it."""
    by_file: dict[str, set[Any]] = {}
    for link in view.all_links:
        (sh,) = [x for x in pid_plan.LOAD_SHAPES if _shape_matches(x, link, view)]
        by_file.setdefault(sh.file, set()).add(link.handling)
    for ent in view.plan.entities:
        (esh,) = [x for x in pid_plan.ENTITY_SHAPES if _entity_matches(x, view, ent.key)]
        by_file.setdefault(esh.file, set()).add(ent.handling)
    return by_file


def test_a_file_with_rows_of_two_handlings_carries_them_by_column(demo: View, scale: View) -> None:
    mixed: set[str] = set()
    for view in (demo, scale):
        mixed |= {f for f, hs in _row_handlings(view).items() if len(hs) > 1}
    shapes: list[Any] = [*pid_plan.LOAD_SHAPES, *pid_plan.ENTITY_SHAPES]
    brief_2 = [sh for sh in shapes if sh.recipe != "seed"]  # the seed's own writers set handling
    mixed -= {sh.file for sh in shapes if sh.recipe == "seed"}
    # The list is the plan's, not a list written beforehand; the files the third review named
    # must be on it, and so must those the plan adds (cell shares, incidents, co-defendants,
    # the establishment plan, and in the scale case the nominals).
    assert {
        "pid_nomis_prisoners.csv", "pid_nomis_visits.csv", "pid_pin_calls.csv",
        "pid_prisoner_money.csv", "pid_intel_reports.csv", "pid_family_and_associates.csv",
        "pid_nomis_cell_shares.csv", "pid_nomis_incidents.csv", "pid_codefendants.csv",
        "pid_establishment_plan.csv",
    } <= mixed, sorted(mixed)  # fmt: skip
    for file in sorted(mixed):
        # One sentence for the file as a whole, on one of its shapes.
        assert any(
            sh.file == file
            and sh.brief2_addition
            and "classification" in sh.brief2_addition
            and "originator" in sh.brief2_addition
            for sh in brief_2
        ), f"{file} needs an addition sentence saying it carries its handling by column"
    for sh in brief_2:
        if sh.file in mixed:
            assert sh.handling == "column", f"{sh.file} holds two handlings"
        else:
            assert sh.handling == "recipe", f"{sh.file} holds one handling and says column"


def test_each_links_shape_file_agrees_with_its_moment(demo: View, scale: View) -> None:
    batch_2, reports = "pid_seized_comms_batch2.csv", "pid_intel_reports.csv"
    seen_moments: Counter[str] = Counter()
    for view in (demo, scale):
        for link in view.all_links:
            (sh,) = [x for x in pid_plan.LOAD_SHAPES if _shape_matches(x, link, view)]
            moment = _link_moment(view, link)
            seen_moments[moment] += 1
            if moment == "chapter9":
                assert sh.file == batch_2, link.key
            elif moment == "chapter4":
                assert sh.file == reports, link.key
            else:
                assert sh.file not in (batch_2, reports), f"a seed link loaded from {sh.file}"
        for ent in view.plan.entities:
            (esh,) = [x for x in pid_plan.ENTITY_SHAPES if _entity_matches(x, view, ent.key)]
            moment = _entity_moment(view, ent.key)
            if moment == "chapter9":
                assert esh.file == batch_2, ent.key
            elif moment == "chapter4":
                assert esh.file == reports, ent.key
            else:
                assert esh.file not in (batch_2, reports), f"{ent.key} loaded from {esh.file}"
    assert set(seen_moments) == {"seed", "chapter4", "chapter9"}
    # And the other way: everything in the second batch's file, and in the reports' file (but
    # for the report Document itself), is of that moment.
    for sh in pid_plan.LOAD_SHAPES:
        assert (sh.file == batch_2) == (sh.moment == "chapter9"), sh
        assert (sh.file == reports) == (sh.moment == "chapter4"), sh
    # The second handset gets no picture: Brief 2 attaches pictures at the seed, before it
    # exists.
    assert "picture:handset:batch2" not in demo.ent
    assert "handset:batch2" not in demo.plan.picture_subjects


def test_every_link_takes_the_regional_unit_when_either_end_has_it(demo: View, scale: View) -> None:
    regional = pid_plan.PlanHandling(
        originator="regional-intel-unit", owning_unit="regional-intel-unit"
    )
    local = pid_plan.PlanHandling()
    for view in (demo, scale):
        stale = []
        for link in view.all_links:
            if link.handling.classification == "SECRET":
                continue
            ends = (view.ent[link.source].handling, view.ent[link.target].handling)
            want = regional if any(h.owning_unit == "regional-intel-unit" for h in ends) else local
            if link.handling != want:
                stale.append(link.key)
        assert not stale, f"{len(stale)} links keep a handling their ends no longer give"


def test_every_account_endpoint_has_a_transfer(demo: View, scale: View) -> None:
    for view in (demo, scale):
        moved = {
            end
            for lk in view.all_links
            if lk.link_type == "TRANSACTED"
            for end in (lk.source, lk.target)
        }
        accounts = [
            e.key for e in view.of_type("Endpoint") if e.properties["endpoint_kind"] == "account"
        ]
        assert accounts
        assert not [k for k in accounts if k not in moved], (
            "an account with a USES and no TRANSACTED"
        )
