"""The Prison Intelligence Dataset's plan (ADR-120 D3 to D9 and Amendments 4 and 7; the build
brief `01_DOMAIN_MODEL_AND_GENERATOR_BRIEF.md` section 5; rule 9: synthetic, in-repo, never real).

`build_plan` returns the whole synthetic case as *keys*, never ids: entities, links, the call
aggregates a later stage writes as rows, the report texts a later stage puts in the media store,
and the entities that get a picture. It is pure: standard library only, no file, no clock, no
environment, deterministic from the one seed (`random.Random(seed)`; sets are never iterated to
make a choice, and the background's draws are integers, so a run cannot move with the
interpreter's hash seed or a float's rounding). Stage 5 turns the plan into graph writes, CSV and
PNG files; `tests/scenarios/test_pid_plan.py` proves the plan itself, without a store, from the
plan's own entities and links.

Two profiles share one generator (ADR-120 D6):

- `demo` ("prison-intelligence"): three establishments, 1,000 prisoners, the cast of the script,
  350 intelligence reports, 262 throw-overs, a million PIN calls over 1,500 outside numbers,
  pictures, and about 13,000 links the analyst can see;
- `scale` ("prison-intelligence-scale"): six establishments, 3,000 prisoners, exactly 30,000
  links, and none of the above (no cast, no reports, no calls, no pictures, no throw-overs).

The cast is the one thing the seed never touches: `CAST` and the link table in `_add_cast` are
written out, because the demo's script quotes figures computed on them (J1's links, J5's two
degrees by five and six routes, J7's betweenness) and the background is generated around them so
that it adds no link a figure counts. Every link between the cast and the background is one of
four kinds, and the plan test enumerates exactly these:

- (a) one of the sixteen cast PIN accounts (every cast prisoner's except the principal's,
  relay_1's, relay_2's, relay_3's and the brother's) calls an outside number, because every PIN
  account calls at least one;
- (b) a seized SIM calls outside numbers;
- (c) larkhill_1/2, calder_1..7 and cellmate_1..4 have background cell-mates, in cells that are not
  cast cells; the principal and relay_1..5 share cells with nobody but as the table says;
- (d) the structural links (custody, group), the report links and the pictures.

Moments (`Plan.moment_of`): the demo loads in three steps. "seed" is everything the seed writes
before the analyst begins (Act 1); "chapter4" adds every intelligence report and every link that
touches one (Brief 2's R9 is live in chapter 4); "chapter9" adds the second seized handset. The
figures the script quotes are computed at the moment it quotes them: `links_at`.

The plan defines what the case holds (ADR-120, the owner's ruling of 23 October): `LOAD_SHAPES`
and `ENTITY_SHAPES` say, for every kind of link and entity, which CSV carries it and which recipe
writes it, and name what Brief 2 as written must be given where it cannot write the shape.

Names come from `pid_names.py` and are the PID's own: no surname used here appears in any other
file under `demo_fixtures/` (D5; the plan test searches every one). Phones use only the Ofcom drama
ranges ADR-103 accepts, in sub-ranges no other fixture or seed produces (D5). Prisoner numbers
are `Z####ZZ`, every person who is not a prisoner carries a National Insurance number beginning
`QQ`, bank accounts are `SYN-70000` to `SYN-79999`, private-cash accounts `PC-<prison number>`, PIN
accounts `PIN-<prison number>`, and every IMEI begins `00` and passes the Luhn check, every IMSI
begins `00101` (the test network) (D4).
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from functools import cached_property
from typing import Any, Literal

from .pid_names import FORENAMES, STAFF_NAMES, SURNAMES

Profile = Literal["demo", "scale"]
Moment = Literal["seed", "chapter4", "chapter9"]
_MOMENT_ORDER: dict[str, int] = {"seed": 0, "chapter4": 1, "chapter9": 2}

# --- The constants the script and the tests quote (spec 11) ------------------------------------

SEED = 120
ESTABLISHMENT_NAME = "Fenwick Moor Prison"

WINDOW_START = date(2026, 3, 1)  # a Sunday
WINDOW_END = date(2026, 4, 30)
CUT_OFF = date(2026, 4, 30)
TOTAL_THROW_OVERS = 262
#: Throw-overs per yard, keyed by the two-digit yard code; the four hotspots sit beside Wing F.
YARD_COUNTS: Mapping[str, int] = {
    "03": 36, "04": 35, "05": 35, "06": 30,
    "01": 16, "02": 16, "07": 16, "08": 16, "09": 16, "10": 16, "11": 15, "12": 15,
}  # fmt: skip
HOTSPOT_YARDS: frozenset[str] = frozenset({"03", "04", "05", "06"})
#: Per hour of the day: seven peak hours (173) and seventeen others (89).
HOUR_COUNTS: Mapping[int, int] = {
    **{h: 5 for h in (0, 1, 2, 3, 4, 5, 6, 18, 19, 20, 21, 22, 23)},
    7: 6, 8: 25, 9: 25, 10: 25, 11: 25, 12: 6, 13: 25, 14: 25, 15: 23, 16: 6, 17: 6,
}  # fmt: skip
#: Per `date.weekday()` (0 = Monday): Sunday 50, Saturday 40, Monday to Friday 34, 34, 34, 35, 35.
WEEKDAY_COUNTS: Mapping[int, int] = {0: 34, 1: 34, 2: 34, 3: 35, 4: 35, 5: 40, 6: 50}
ITEM_COUNTS: Mapping[str, int] = {
    "mobile phone": 70, "drugs": 90, "tobacco": 50, "SIM card": 30, "other": 22,
}  # fmt: skip

REPORTS_SELECTED = 229
REPORTS_USED = 68
F2_ILLICIT_REPORTS = 23
F2_ILLICIT_PRISONERS = 28
F2_ILLICIT_IN_GROUP = 13
F2_ILLICIT_NAMED_MORE_THAN_ONCE = 3
REPORTS_TOTAL = 350

#: The principal's links as the analyst sees them, after chapter 4 (49) and in Act 1, before any
#: report is loaded (45); a principal cleared to SECRET sees one more of each.
PRINCIPAL_LINK_COUNT = 49
PRINCIPAL_LINK_COUNT_SECRET = 50
PRINCIPAL_LINK_COUNT_ACT1 = 45
PRINCIPAL_LINK_COUNT_ACT1_SECRET = 46
PRINCIPAL_LINKS_BY_TYPE: Mapping[str, int] = {
    "DEPICTS": 1, "HELD_AT": 1, "MEMBER_OF": 1, "FAMILY_OF": 1, "CO_DEFENDANT_OF": 2, "USES": 2,
    "PRESENT_AT": 5, "MENTIONED_IN": 4, "VISITED": 12, "SHARED_CELL_WITH": 7,
    "PASSES_ITEMS_TO": 3, "ASSOCIATE_OF": 2, "ROLE_IN": 6, "IN_CONFLICT_WITH": 2,
}  # fmt: skip
PAIR_DEGREES = 2
PAIR_ROUTES = 6  # after chapter 4; five in Act 1, before the report that names relay_4
PAIR_ROUTES_ACT1 = 5
PRINCIPAL_BETWEENNESS = 0.87
PRINCIPAL_BETWEENNESS_ACT1 = 0.87
#: Brief 2's teaching row: a letter O for a nought. Corrected it is +447700900603, one of the
#: background numbers, as a mistyped real number would be; stage 5 places it in the PIN calls.
PID_TEACHING_BAD_NUMBER = "07700 900 6O3"
BULK_LIST_SIZE = 40
CALL_WEEKS = 35  # w/c Monday 1 September 2025 to the week holding the cut-off
CALL_ROWS = 1_000_000
CALLED_NUMBERS = 1_500
PIN_ACCOUNTS = 1_000
DEMO_PRISONERS = 1_000
SCALE_PRISONERS = 3_000
SCALE_LINKS = 30_000
#: (min latitude, max latitude, min longitude, max longitude): the Berkshire extract the local
#: basemap covers, so every point of the case draws on tier-1 map data.
BASEMAP_EXTENT = (51.33, 51.60, -1.59, -0.55)

LOCAL_UNIT = "fenwick-moor-security"
REGIONAL_UNIT = "regional-intel-unit"
CALL_START = date(2025, 9, 1)
EXTRACTION_RUN = "synthetic:pid-extraction-run"

# --- The plan's shape (spec 1) ---------------------------------------------------------------


@dataclass(frozen=True)
class PlanHandling:
    """Mirrors `schemas.domain.Handling`'s field names; the plan itself imports nothing."""

    classification: str = "OFFICIAL"
    handling_code: str = "P"
    action_code: str | None = None
    sanitisation_code: str | None = None
    originator: str = LOCAL_UNIT
    owning_unit: str = LOCAL_UNIT


@dataclass(frozen=True)
class PlanEntity:
    key: str
    entity_type: str
    properties: Mapping[str, object]
    handling: PlanHandling


@dataclass(frozen=True)
class PlanLink:
    key: str
    link_type: str
    source: str
    target: str
    occurrences: int
    first_seen: date | datetime | None
    last_seen: date | datetime | None
    properties: Mapping[str, object]
    provenance: Literal["asserted", "inferred"] = "asserted"
    extracted_by: str | None = None
    extraction_confidence: float | None = None
    handling: PlanHandling = PlanHandling()


@dataclass(frozen=True)
class CallAggregate:
    """One PIN account's calls to one outside number, by week: `CALL_WEEKS` entries, week 0 being
    the week commencing Monday 1 September 2025. Stage 5 writes the rows from these."""

    pin: str
    number: str
    weekly: tuple[int, ...]


@dataclass(frozen=True)
class Plan:
    profile: Profile
    seed: int
    entities: tuple[PlanEntity, ...]
    links: tuple[PlanLink, ...]
    calls: tuple[CallAggregate, ...]
    report_texts: Mapping[str, str]
    picture_subjects: tuple[str, ...]
    #: Every link key's moment (see the module docstring).
    moment_of: Mapping[str, Moment]

    @cached_property
    def _entity_index(self) -> dict[str, PlanEntity]:
        return {e.key: e for e in self.entities}

    @cached_property
    def _link_index(self) -> dict[str, tuple[PlanLink, ...]]:
        out: dict[str, list[PlanLink]] = {}
        for link in self.links:
            out.setdefault(link.source, []).append(link)
            if link.target != link.source:
                out.setdefault(link.target, []).append(link)
        return {k: tuple(v) for k, v in out.items()}

    def entity(self, key: str) -> PlanEntity:
        """The entity of this key; `KeyError` for a key the plan does not hold."""
        return self._entity_index[key]

    def links_of(self, key: str) -> tuple[PlanLink, ...]:
        """Every link touching the key, a `SECRET` one and every moment's included."""
        return self._link_index.get(key, ())


def links_at(plan: Plan, moment: Moment, *, secret_cleared: bool) -> tuple[PlanLink, ...]:
    """The links loaded by the end of a moment ("seed", then "chapter4", then "chapter9" each
    include the one before), less the one `SECRET` link unless the principal is cleared to it; the
    demo analyst is cleared only to `OFFICIAL`."""
    rank = _MOMENT_ORDER[moment]
    return tuple(
        lk
        for lk in plan.links
        if _MOMENT_ORDER[plan.moment_of.get(lk.key, "seed")] <= rank
        and (secret_cleared or lk.handling.classification != "SECRET")
    )


def j7_working_set(
    plan: Plan, moment: Moment = "chapter4"
) -> tuple[frozenset[str], tuple[PlanLink, ...]]:
    """J7's working set as the analyst sees it at a moment: the principal, every far end of his
    visible links, the coordinator's number and every far end of its visible links; its links are
    every visible link with both ends in the set, self-loops excluded (what the Conduit's
    `narrow_to_visible` and the expand step leave)."""
    visible = links_at(plan, moment, secret_cleared=False)
    keys = {"principal", "number:coordinator"}
    for link in visible:
        for here, there in ((link.source, link.target), (link.target, link.source)):
            if here in ("principal", "number:coordinator"):
                keys.add(there)
    links = tuple(
        lk for lk in visible if lk.source in keys and lk.target in keys and lk.source != lk.target
    )
    return frozenset(keys), links


#: The one pattern that selects the 229 reports (spec 6), shaped as `schemas.domain.PatternQuery`.
REPORT_PATTERN: dict[str, Any] = {
    "nodes": [
        {"var": "zone", "entity_type": "Location", "node_id": "zone:wing-f"},
        {"var": "area", "entity_type": "Location"},
        {"var": "report", "entity_type": "Document"},
        {"var": "incident", "entity_type": "Incident"},
        {"var": "yard", "entity_type": "Location"},
    ],
    "edges": [
        {"edge_type": "PART_OF", "from_var": "area", "to_var": "zone"},
        {"edge_type": "MENTIONED_IN", "from_var": "area", "to_var": "report"},
        {"edge_type": "MENTIONED_IN", "from_var": "incident", "to_var": "report"},
        {"edge_type": "OCCURRED_AT", "from_var": "incident", "to_var": "yard"},
        {"edge_type": "PART_OF", "from_var": "yard", "to_var": "zone"},
    ],
    "limit": 2_000,
}

# --- Places and the map (spec 7) --------------------------------------------------------------

_WING_F_POINT = (51.43000, -1.15000)
_M_PER_DEG_LAT = 111_320.0
_M_PER_DEG_LON = _M_PER_DEG_LAT * math.cos(math.radians(_WING_F_POINT[0]))


def _offset(north_m: float, east_m: float) -> tuple[float, float]:
    return (
        round(_WING_F_POINT[0] + north_m / _M_PER_DEG_LAT, 6),
        round(_WING_F_POINT[1] + east_m / _M_PER_DEG_LON, 6),
    )


#: Metres north and east of Wing F: the hotspots within 150 m of it, the other eight beyond 300 m
#: from it and from every hotspot, all well inside `BASEMAP_EXTENT` and over 5 km from (51.5, -0.6).
_YARD_OFFSETS: dict[str, tuple[float, float]] = {
    "03": (100, 20), "04": (40, 110), "05": (-60, 90), "06": (-90, -50),
    "01": (520, 0), "02": (390, 390), "07": (0, 560), "08": (-400, 400),
    "09": (-560, 0), "10": (-420, -420), "11": (0, -600), "12": (430, -430),
}  # fmt: skip
#: Entity key -> (latitude, longitude) for Wing F, the zone, every yard of Fenwick Moor and the
#: arrest site; stage 5 writes the map geometries from it, and every throw-over sits within its
#: jitter of its yard's.
PLACE_POINTS: Mapping[str, tuple[float, float]] = {
    "wing:F": _WING_F_POINT,
    "zone:wing-f": _WING_F_POINT,
    **{f"yard:{code}": _offset(*off) for code, off in _YARD_OFFSETS.items()},
    #: Where Jamie Pryce was arrested: inside the basemap, several kilometres from Wing F.
    "place:arrest-site": (51.46, -1.05),
}
_JITTER_MICRO = 49  # millionths of a degree; the spec allows 50

#: Which wings use which yard of Fenwick Moor: Wing F the four hotspots, the others the rest.
_YARD_WINGS: dict[str, str] = {
    "03": "F", "04": "F", "05": "F", "06": "F",
    "01": "A", "02": "A", "07": "B", "08": "B", "09": "C", "10": "D", "11": "E", "12": "E",
}  # fmt: skip
_CAST_CELLS = ("F1-03", "F1-07", "F1-11", "F2-05", "F2-09", "F2-14", "F2-17", "F2-18", "F2-21")

# --- The cast (spec 3): written out, never drawn --------------------------------------------

#: key -> (given names, family name, aliases). Invented, and not one of them is in any other
#: fixture; the three that the brief names differently are noted in `PID_ACTUALS.md`.
CAST: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "principal": ("Callum", "Vance", ("Cally V",)),
    "brother": ("Ryan", "Vance", ()),
    "third_member": ("Darren", "Ashcombe", ()),
    "relay_1": ("Kieran", "Thackwray", ()),
    "relay_2": ("Dominic", "Fairlop", ()),
    "relay_3": ("Lewis", "Penhallow", ()),
    "relay_4": ("Rory", "Skellion", ()),
    "relay_5": ("Aaron", "Wetherill", ()),
    "cellmate_1": ("Gareth", "Holmcroft", ()),
    "cellmate_2": ("Stuart", "Peverell", ()),
    "cellmate_3": ("Neil", "Garrowby", ()),
    "cellmate_4": ("Callan", "Ruddock", ()),
    "larkhill_1": ("Jordan", "Selwood", ()),
    "larkhill_2": ("Elliot", "Marchbank", ()),
    "calder_1": ("Vince", "Ridsdale", ()),
    "calder_2": ("Kyle", "Tarbuck", ()),
    "calder_3": ("Dean", "Orrell", ()),
    "calder_4": ("Lee", "Stanwick", ()),
    "calder_5": ("Craig", "Mossop", ()),
    "calder_6": ("Wayne", "Haverlock", ()),
    "calder_7": ("Ross", "Dilnot", ()),
    "coordinator": ("Marcus", "Ellery", ("Mo",)),
    "payer": ("Shona", "Whitlow", ()),
    "arrested_outside": ("Jamie", "Pryce", ()),
    "mother": ("Brenda", "Vance", ()),
    "partner": ("Rhiannon", "Corbet", ()),
    "sister": ("Leah", "Vance", ()),
    "friend": ("Danny", "Kettlewell", ()),
    "outside_1": ("Ellis", "Garmston", ()),
    "outside_2": ("Maxine", "Tolliver", ()),
    "outside_3": ("Reggie", "Hobday", ()),
    "outside_4": ("Chantelle", "Marrable", ()),
    "outside_5": ("Spencer", "Dowell", ()),
    "outside_6": ("Yasmin", "Crowther", ()),
    "unconnected": ("Wesley", "Dorrance", ()),
}  # fmt: skip
_CAST_PRISONERS = (
    "principal", "brother", "third_member", "relay_1", "relay_2", "relay_3", "relay_4", "relay_5",
    "cellmate_1", "cellmate_2", "cellmate_3", "cellmate_4", "larkhill_1", "larkhill_2",
    "calder_1", "calder_2", "calder_3", "calder_4", "calder_5", "calder_6", "calder_7",
)  # fmt: skip
_LARKHILL = (
    "principal",
    "brother",
    "third_member",
    "relay_1",
    "relay_2",
    "larkhill_1",
    "larkhill_2",
)
_CALDER = tuple(f"calder_{i}" for i in range(1, 8))
_CAST_HELD_FROM: dict[str, date] = {
    "principal": date(2024, 6, 3), "brother": date(2023, 11, 14), "third_member": date(2024, 2, 20),
    "relay_1": date(2025, 6, 2), "relay_2": date(2025, 4, 14), "relay_3": date(2025, 7, 1),
    "relay_4": date(2025, 8, 18), "relay_5": date(2025, 9, 9), "cellmate_1": date(2024, 5, 20),
    "cellmate_2": date(2024, 9, 2), "cellmate_3": date(2024, 12, 9), "cellmate_4": date(2025, 8, 4),
    "larkhill_1": date(2023, 8, 1), "larkhill_2": date(2024, 1, 15), "calder_1": date(2024, 3, 11),
    "calder_2": date(2024, 7, 22), "calder_3": date(2024, 10, 7), "calder_4": date(2025, 2, 3),
    "calder_5": date(2025, 3, 17), "calder_6": date(2025, 5, 12), "calder_7": date(2025, 6, 23),
}  # fmt: skip
#: Where each cast prisoner other than the principal slept or sleeps: (cell, from, to or None for
#: open). The group members' and cell-mates' current cells are in `_GROUP_LANDING`: they are
#: drawn from the background's cells.
_CAST_PRESENT: dict[str, tuple[str, date, date | None]] = {
    "cellmate_1": ("F1-03", date(2024, 6, 3), date(2024, 10, 13)),
    "cellmate_2": ("F1-03", date(2024, 10, 14), date(2025, 1, 5)),
    "cellmate_3": ("F2-05", date(2025, 1, 6), date(2025, 1, 12)),
    "relay_2": ("F2-09", date(2025, 5, 5), None),
    "cellmate_4": ("F2-21", date(2025, 9, 29), date(2025, 10, 19)),
    "relay_3": ("F2-21", date(2025, 10, 20), None),
    "relay_1": ("F2-14", date(2025, 12, 15), None),
    "relay_4": ("F2-17", date(2025, 8, 18), None),
    "relay_5": ("F2-18", date(2025, 9, 9), None),
    "brother": ("F1-11", date(2025, 2, 3), None),
    "third_member": ("F1-07", date(2024, 2, 20), None),
}  # fmt: skip
#: The landing each of the thirteen cast prisoners with background cell-mates now sleeps on:
#: Wing F's first landing for the Larkhill members and Calder members one to four, Wing E for the
#: rest, the cell-mates on F1 too. None is on F2, so the bulk list stays the 40 prisoners there.
_GROUP_LANDING: dict[str, str] = {
    **dict.fromkeys(("larkhill_1", "larkhill_2"), "F1"),
    **dict.fromkeys(("calder_1", "calder_2", "calder_3", "calder_4"), "F1"),
    **dict.fromkeys(("calder_5", "calder_6", "calder_7"), "E1"),
    **dict.fromkeys(("cellmate_1", "cellmate_2", "cellmate_3", "cellmate_4"), "F1"),
}
#: The principal's cell history; each cell-mate's share of it is a SHARED_CELL_WITH link whose
#: occurrences are the weeks shared, rounded up (D3: one occurrence is one week shared).
_PRINCIPAL_CELLS: tuple[tuple[str, date, date], ...] = (
    ("F1-03", date(2024, 6, 3), date(2025, 1, 5)),
    ("F2-05", date(2025, 1, 6), date(2025, 5, 4)),
    ("F2-09", date(2025, 5, 5), date(2025, 9, 28)),
    ("F2-21", date(2025, 9, 29), date(2025, 12, 14)),
    ("F2-14", date(2025, 12, 15), CUT_OFF),
)
_CELL_SHARES: tuple[tuple[str, str, date, date], ...] = (
    ("cellmate_1", "F1-03", date(2024, 6, 3), date(2024, 10, 13)),
    ("cellmate_2", "F1-03", date(2024, 10, 14), date(2025, 1, 5)),
    ("cellmate_3", "F2-05", date(2025, 1, 6), date(2025, 1, 12)),
    ("relay_2", "F2-09", date(2025, 5, 5), date(2025, 9, 28)),
    ("cellmate_4", "F2-21", date(2025, 9, 29), date(2025, 10, 19)),
    ("relay_3", "F2-21", date(2025, 10, 20), date(2025, 12, 14)),
    ("relay_1", "F2-14", date(2025, 12, 15), CUT_OFF),
)
#: (visitor, visits, channel, first, last).
_PRINCIPAL_VISITS: tuple[tuple[str, int, date, date], ...] = (
    ("coordinator", 9, date(2025, 10, 6), date(2026, 4, 25)),
    ("payer", 6, date(2025, 11, 8), date(2026, 4, 11)),
    ("mother", 10, date(2025, 9, 6), date(2026, 4, 18)),
    ("partner", 8, date(2025, 10, 11), date(2026, 4, 22)),
    ("sister", 3, date(2025, 12, 20), date(2026, 2, 14)),
    ("friend", 1, date(2025, 11, 2), date(2025, 11, 2)),
)
#: (incident key, date, item, cell, the relay it was found with) for the seven finds.
_FINDS: tuple[tuple[str, date, str, str, str], ...] = (
    ("find_01", date(2026, 1, 5), "mobile phone", "F2-14", "relay_1"),
    ("find_02", date(2026, 2, 2), "SIM card", "F2-09", "relay_2"),
    ("find_03", date(2026, 2, 20), "mobile phone", "F2-21", "relay_3"),
    ("find_04", date(2026, 3, 9), "mobile phone", "F2-17", "relay_4"),
    ("find_05", date(2026, 3, 28), "SIM card", "F2-18", "relay_5"),
    ("find_06", date(2026, 4, 14), "mobile phone", "F2-14", "relay_1"),
    ("find_07", date(2026, 4, 27), "SIM card", "F2-09", "relay_2"),
)
_OTHER_INCIDENTS: tuple[tuple[str, str, date, tuple[str, ...], str], ...] = (
    ("assault_1", "assault", date(2025, 3, 10), ("calder_1",), "landing:F1"),
    ("assault_2", "assault", date(2025, 7, 22), ("calder_2",), "yard:07"),
    ("disorder_1", "disorder", date(2025, 5, 2), ("larkhill_1",), "hall:visits"),
    ("disorder_2", "disorder", date(2025, 11, 30), ("larkhill_2",), "landing:F1"),
)
#: The outside number nobody owns: in the PID block, in no other file of the repository.
_UNIDENTIFIED = ("07700 900718", "+447700900718")
_COORDINATOR = ("07700 900640", "+447700900640")


@dataclass(frozen=True)
class _CastReport:
    """One of the cast's four reports: the one table its mentions, its links and its text read."""

    key: str
    day: date | None  # None: drawn from the hotspot days
    area: str  # the cell or place it names, besides Wing F and landing F2
    persons: tuple[str, ...]
    text: str  # names are read from `CAST`; `{cally}`, `{mo}` and the number forms from the cast
    illicit: bool
    s2: bool = False


_FIND_DAY = {key: day for key, day, *_rest in _FINDS}
_CAST_REPORTS: tuple[_CastReport, ...] = (
    _CastReport(
        "report:p1",
        None,
        "cell:F2-14",
        ("principal", "relay_1", "relay_2"),
        "IR {ir:04d}. Officer {staff} reports that Prisoner {relay_1} and Prisoner {relay_2} were "
        "seen on F2 landing after lock-up passing items along the line between cells, on the "
        "instruction of the man known as {cally}. A handset was heard in use at night. The PIN "
        "calls from this group all go to one man, who calls himself {mo}, on {number_raw}.",
        True,
    ),  # fmt: skip
    _CastReport(
        "report:p2",
        _FIND_DAY["find_07"],
        "cell:F2-09",
        ("principal", "brother", "relay_4"),
        "IR {ir:04d}. Search of cell F2-09 after lock-up found a SIM card taped under the sink. "
        "Prisoner {relay_4} says it came from the line between cells. Prisoner {brother} was seen "
        "on F2 landing outside {cally}'s cell. The number saved on the card, {number_plain}, is "
        "the one the PIN calls go to.",
        True,
        s2=True,
    ),  # fmt: skip
    _CastReport(
        "report:p3",
        _FIND_DAY["find_06"],
        "cell:F2-14",
        ("principal", "relay_1", "calder_1"),
        "IR {ir:04d}. Cell F2-14: a mobile phone and drugs recovered. Prisoner {relay_1} blamed "
        "Prisoner {calder_1} of the Calder Street Group; the orders for the line between cells "
        "after lock-up were {cally}'s. A call from the PIN system to {number_intl} followed the "
        "next morning.",
        True,
    ),  # fmt: skip
    _CastReport(
        "report:pryce",
        date(2026, 4, 2),
        "place:arrest-site",
        ("principal", "arrested_outside"),
        "IR {ir:04d}. Officer {staff} reports that {arrested_outside} was arrested outside the "
        "establishment at the arrest site and a handset seized from him. It held a saved contact, "
        "{cally}, the bank account SYN-00988 with no holder named, and calls to the number "
        "{unidentified_raw}.",
        False,
    ),  # fmt: skip
)


@dataclass(frozen=True)
class _Block:
    """A run of background reports: how many, what the text is, where they are about, when they
    are dated, and whether they are among the F2 illicit-item reports."""

    count: int
    kind: str  # line, illicit, plain, yard, free
    where: str  # f2, f1, wing_f, hotspot, other_wing, other_yard
    when: str  # window (a hotspot day), before (the zone before any throw-over data), anywhere
    illicit: bool = False


#: In key order: the 20 F2 reports that name people and describe an item, the 9 and 25 that name
#: people about something else, 11 hotspot-yard reports that name people, then the free text.
_BLOCKS: tuple[_Block, ...] = (
    _Block(8, "line", "f2", "window", True),
    _Block(12, "illicit", "f2", "window", True),
    _Block(9, "plain", "f2", "window"),
    _Block(25, "plain", "f1", "window"),
    _Block(120, "free", "wing_f", "window"),
    _Block(11, "yard", "hotspot", "window"),
    _Block(41, "free", "hotspot", "window"),
    _Block(31, "free", "wing_f", "before"),
    _Block(9, "free", "hotspot", "before"),
    _Block(40, "free", "other_wing", "anywhere"),
    _Block(40, "free", "other_yard", "anywhere"),
)


def _block_keys() -> list[tuple[str, _Block]]:
    """Every background report's key with its block, in key order."""
    out: list[tuple[str, _Block]] = []
    for block in _BLOCKS:
        for _ in range(block.count):
            out.append((f"report:{len(out) + 1:04d}", block))
    return out


#: The 23 F2 illicit-item reports, from the report tables' own flags.
F2_ILLICIT_REPORT_KEYS: frozenset[str] = frozenset(
    [k for k, blk in _block_keys() if blk.illicit] + [c.key for c in _CAST_REPORTS if c.illicit]
)

# --- Calls: the coordinator's four callers, week by week (spec 7) -----------------------------

_SURGE_WEEK = 13  # w/c Monday 1 December 2025
_LAST_WEEK = CALL_WEEKS - 1  # w/c 27 April 2026: calls stop on Thursday the 30th


def _coordinator_weekly(per_week: int, last_week: int) -> tuple[int, ...]:
    """One call a fortnight before the surge, then `per_week` a week; the week holding the
    cut-off carries only the days up to it."""
    weeks = [1 if w % 2 == 0 else 0 for w in range(_SURGE_WEEK)]
    weeks += [per_week] * (_LAST_WEEK - _SURGE_WEEK)
    weeks.append(last_week)
    return tuple(weeks)


_PRINCIPAL_CALLS = _coordinator_weekly(9, 5)
_RELAY_CALLS = _coordinator_weekly(7, 4)
#: Twelve calls each, from January 2026, to the number nobody owns.
_UNIDENTIFIED_WEEKS = (18, 20, 22, 24, 26, 27, 28, 29, 30, 31, 32, 33)
_UNIDENTIFIED_CALLS = tuple(1 if w in _UNIDENTIFIED_WEEKS else 0 for w in range(CALL_WEEKS))

# --- The builder ------------------------------------------------------------------------------

LOCAL = PlanHandling()
REGIONAL = PlanHandling(originator=REGIONAL_UNIT, owning_unit=REGIONAL_UNIT)
_SECRET = PlanHandling(classification="SECRET", originator=REGIONAL_UNIT, owning_unit=REGIONAL_UNIT)


class _Build:
    """Accumulates entities and links in the order they are made (which is never a set's)."""

    def __init__(self) -> None:
        self.ents: dict[str, PlanEntity] = {}
        self.links: list[PlanLink] = []

    def entity(
        self,
        key: str,
        entity_type: str,
        properties: Mapping[str, object],
        handling: PlanHandling = LOCAL,
    ) -> None:
        assert key not in self.ents, f"duplicate entity key {key}"
        self.ents[key] = PlanEntity(key, entity_type, dict(properties), handling)

    def finish(self) -> None:
        """Give every link the regional unit if either of its ends has it, now that the last
        entity's handling is set (Amendment 8, decision 11); the one SECRET link keeps its own."""
        out = []
        for lk in self.links:
            if lk.handling.classification != "SECRET":
                ends = (self.ents[lk.source].handling, self.ents[lk.target].handling)
                regional = any(h.owning_unit == REGIONAL_UNIT for h in ends)
                lk = replace(lk, handling=REGIONAL if regional else LOCAL)
            out.append(lk)
        self.links = out

    def set_handling(self, key: str, handling: PlanHandling) -> None:
        old = self.ents[key]
        self.ents[key] = PlanEntity(key, old.entity_type, old.properties, handling)

    def link(
        self,
        link_type: str,
        source: str,
        target: str,
        *,
        occ: int = 1,
        first: date | datetime | None = None,
        last: date | datetime | None = None,
        props: Mapping[str, object] | None = None,
        handling: PlanHandling | None = None,
        provenance: Literal["asserted", "inferred"] = "asserted",
        by: str | None = None,
        confidence: float | None = None,
    ) -> None:
        if handling is None:
            regional = REGIONAL_UNIT in (
                self.ents[source].handling.owning_unit,
                self.ents[target].handling.owning_unit,
            )
            handling = REGIONAL if regional else LOCAL
        self.links.append(
            PlanLink(
                key=f"l{len(self.links):06d}",
                link_type=link_type,
                source=source,
                target=target,
                occurrences=occ,
                first_seen=first,
                last_seen=last,
                properties=dict(props or {}),
                provenance=provenance,
                extracted_by=by,
                extraction_confidence=confidence,
                handling=handling,
            )
        )


def _day(rng: random.Random, lo: date, hi: date) -> date:
    return lo + timedelta(days=rng.randrange((hi - lo).days + 1))


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def _weeks(first: date, last: date) -> int:
    """D3's unit for a shared cell: one occurrence is one week shared, rounded up."""
    return math.ceil(((last - first).days + 1) / 7)


def _imei(rng: random.Random) -> str:
    """Fifteen digits, the test-device prefix `00`, and a Luhn check digit (D4)."""
    body = "00" + "".join(str(rng.randrange(10)) for _ in range(12))
    total = 0
    for i, ch in enumerate(reversed(body)):
        digit = int(ch)
        if i % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return body + str((10 - total % 10) % 10)


class _Names:
    """Hands out unused (forenames, family name) pairs from the PID's own lists."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._used: set[tuple[str, str]] = set()

    def next(self) -> tuple[str, str]:
        while True:
            pair = (self._rng.choice(FORENAMES), self._rng.choice(SURNAMES))
            if pair not in self._used:
                self._used.add(pair)
                return pair


@dataclass
class _Estate:
    """One establishment's places, by the codes a person would use for them."""

    index: int
    key: str
    kp: str  # key prefix
    sp: str  # site_ref prefix
    unit: PlanHandling
    wing_keys: dict[str, str]
    landing_keys: dict[str, str]
    cells: dict[str, list[str]]  # landing code -> cell keys, in order
    yard_keys: dict[str, str]


@dataclass
class _Prisoner:
    key: str
    est: _Estate
    pin: str
    component: int  # 0 for the main component, 1 for Brindle Heath's own
    held: date = CUT_OFF  # when the open custody began
    cell: str = ""


def _estate(
    b: _Build,
    *,
    index: int,
    key: str,
    kp: str,
    sp: str,
    name: str,
    ref: str,
    niu: str,
    soct: str,
    category: str,
    wings: str,
    yards: dict[str, str],
    unit: PlanHandling,
    cells_per_landing: int = 30,
) -> _Estate:
    """An establishment, its wings, two landings a wing, `cells_per_landing` cells a landing, its
    yards (each adjoining and used by a wing) and a visits hall, chained by `PART_OF`."""
    b.entity(
        key,
        "Establishment",
        {
            "name": name, "establishment_ref": ref, "niu_area": niu, "soct_region": soct,
            "security_category": category,
        },
        unit,
    )  # fmt: skip
    est = _Estate(index, key, kp, sp, unit, {}, {}, {}, {})
    for w in wings:
        wkey = f"{kp}wing:{w}"
        est.wing_keys[w] = wkey
        wprops: dict[str, object] = {"name": f"Wing {w}", "site_ref": f"{sp}wing:{w}"}
        if key == "est:fenwick-moor" and w == "F":
            wprops["geometry_ref"] = "pid:est1:geom:wing:F"
        b.entity(wkey, "Location", wprops, unit)
        b.link("PART_OF", wkey, key)
        for n in (1, 2):
            lcode = f"{w}{n}"
            lkey = f"{kp}landing:{lcode}"
            est.landing_keys[lcode] = lkey
            b.entity(
                lkey,
                "Location",
                {"name": f"Landing {lcode}", "site_ref": f"{sp}landing:{lcode}"},
                unit,
            )
            b.link("PART_OF", lkey, wkey)
            est.cells[lcode] = []
            for c in range(1, cells_per_landing + 1):
                ckey = f"{kp}cell:{lcode}-{c:02d}"
                est.cells[lcode].append(ckey)
                b.entity(
                    ckey,
                    "Location",
                    {"name": f"Cell {lcode}-{c:02d}", "site_ref": f"{sp}cell:{lcode}-{c:02d}"},
                    unit,
                )
                b.link("PART_OF", ckey, lkey)
    for code, wing in yards.items():
        ykey = f"{kp}yard:{code}"
        est.yard_keys[code] = ykey
        yprops: dict[str, object] = {"name": f"Yard {code}", "site_ref": f"{sp}yard:{code}"}
        if key == "est:fenwick-moor":
            yprops["geometry_ref"] = f"pid:est1:geom:yard:{code}"
        b.entity(ykey, "Location", yprops, unit)
        b.link("PART_OF", ykey, key)
        b.link("ADJOINS", ykey, est.wing_keys[wing])
        b.link("USED_BY", ykey, est.wing_keys[wing])
    hall = f"{kp}hall:visits"
    b.entity(hall, "Location", {"name": "Visits hall", "site_ref": f"{sp}hall:visits"}, unit)
    b.link("PART_OF", hall, key)
    return est


def _fenwick(b: _Build) -> _Estate:
    est = _estate(
        b, index=1, key="est:fenwick-moor", kp="", sp="pid:est1:", name=ESTABLISHMENT_NAME,
        ref="pid:est:fenwick-moor", niu="PID NIU Area 2", soct="PID SOCT Region South",
        category="B", wings="ABCDEF", yards=_YARD_WINGS, unit=LOCAL,
    )  # fmt: skip
    # The one zone the one pattern names: Wing F and the four yards it uses.
    b.entity(
        "zone:wing-f",
        "Location",
        {
            "name": "Wing F and its yards", "site_ref": "pid:est1:zone:wing-f",
            "geometry_ref": "pid:est1:geom:zone:wing-f",
        },
        LOCAL,
    )  # fmt: skip
    b.link("PART_OF", "wing:F", "zone:wing-f")
    for code in sorted(HOTSPOT_YARDS):
        b.link("PART_OF", f"yard:{code}", "zone:wing-f")
    return est


# --- Throw-overs (spec 7; Amendment 7) ----------------------------------------------------


def _multiset(counts: Mapping[Any, int]) -> list[Any]:
    return [k for k, n in counts.items() for _ in range(n)]


def _throw_overs(b: _Build, rng: random.Random) -> list[tuple[str, str, datetime]]:
    """262 incidents built as the exact multisets say: each dimension shuffled on its own with the
    one generator, then zipped; the date comes from a per-weekday cursor over the window. Returns
    (incident key, yard code, when), in time order."""
    yards = _multiset(YARD_COUNTS)
    hours = _multiset(HOUR_COUNTS)
    weekdays = _multiset(WEEKDAY_COUNTS)
    items = _multiset(ITEM_COUNTS)
    for column in (yards, hours, weekdays, items):
        rng.shuffle(column)
    window = [WINDOW_START + timedelta(days=i) for i in range((WINDOW_END - WINDOW_START).days + 1)]
    by_weekday: dict[int, list[date]] = {
        w: [d for d in window if d.weekday() == w] for w in range(7)
    }
    cursor = dict.fromkeys(range(7), 0)
    rows: list[tuple[datetime, str, str]] = []
    for yard, hour, weekday, item in zip(yards, hours, weekdays, items, strict=True):
        days = by_weekday[weekday]
        day = days[cursor[weekday] % len(days)]
        cursor[weekday] += 1
        rows.append((_at(day, hour, rng.randrange(60)), yard, item))
    rows.sort(key=lambda r: (r[0], r[1]))
    out: list[tuple[str, str, datetime]] = []
    for n, (when, yard, item) in enumerate(rows, 1):
        key = f"incident:to:{n:04d}"
        lat, lon = PLACE_POINTS[f"yard:{yard}"]
        b.entity(
            key,
            "Incident",
            {
                "name": f"Throw-over {n:04d}", "incident_ref": f"pid:est1:inc:to:{n:04d}",
                "category": "throw_over", "item": item, "occurred_at": when,
            },
        )  # fmt: skip
        b.link(
            "OCCURRED_AT", key, f"yard:{yard}", first=when, last=when,
            props={
                "lat": round(lat + rng.randint(-_JITTER_MICRO, _JITTER_MICRO) / 1_000_000, 6),
                "lon": round(lon + rng.randint(-_JITTER_MICRO, _JITTER_MICRO) / 1_000_000, 6),
                "yard": yard, "item_type": item,
            },
        )  # fmt: skip
        out.append((key, yard, when))
    return out


# --- People -----------------------------------------------------------------------------------


class _Pool:
    """Prison numbers, National Insurance numbers, SYN accounts and IMSIs, each used once."""

    def __init__(self, rng: random.Random, profile: Profile) -> None:
        low, high = (1000, 3000) if profile == "demo" else (5000, 8000)
        count = DEMO_PRISONERS if profile == "demo" else SCALE_PRISONERS
        self.numbers = [f"Z{n}ZZ" for n in rng.sample(range(low, high), count)]
        self._rng = rng
        self._nino: set[str] = set()
        self._syn: set[int] = {70417}  # the payer's, written out in the cast
        self._imsi: set[str] = set()

    def prison_number(self) -> str:
        return self.numbers.pop()

    def nino(self) -> str:
        while True:
            value = f"QQ{self._rng.randrange(10**6):06d}{self._rng.choice('ABCD')}"
            if value not in self._nino:
                self._nino.add(value)
                return value

    def syn(self) -> str:
        while True:
            n = self._rng.randrange(70_000, 80_000)
            if n not in self._syn:
                self._syn.add(n)
                return f"SYN-{n:05d}"

    def imsi(self) -> str:
        """Fifteen digits on the test network (mobile country code 001, network code 01)."""
        while True:
            value = f"00101{self._rng.randrange(10**10):010d}"
            if value not in self._imsi:
                self._imsi.add(value)
                return value


def _person(
    b: _Build,
    key: str,
    given: str,
    family: str,
    *,
    number: str | None = None,
    nino: str | None = None,
    aliases: Sequence[str] = (),
    dob: date | None = None,
    handling: PlanHandling = LOCAL,
) -> None:
    props: dict[str, object] = {"family_name": family, "given_names": given}
    if aliases:
        props["aliases"] = list(aliases)
    if dob is not None:
        props["date_of_birth"] = dob
    if number is not None:
        props["prison_number"] = number
    if nino is not None:
        props["nino"] = nino
    b.entity(key, "Person", props, handling)


#: The identifier property an endpoint of each kind carries. An account carries none, as the
#: PaySim fixture's accounts carry none: `value_raw`, `value_normalised` and `endpoint_kind` only.
_IDENTIFIER = {"msisdn": "e164", "handle": "handle", "imsi": "imsi"}


def _endpoint(
    b: _Build, key: str, kind: str, raw: str, normalised: str, handling: PlanHandling = LOCAL
) -> None:
    props: dict[str, object] = {
        "value_raw": raw,
        "value_normalised": normalised,
        "endpoint_kind": kind,
    }
    if kind in _IDENTIFIER:
        props[_IDENTIFIER[kind]] = normalised
    b.entity(key, "Endpoint", props, handling)


def _pin(b: _Build, person: str, number: str, handling: PlanHandling, px: str = "") -> str:
    key = f"{px}pin:{person.removeprefix(px)}"
    _endpoint(b, key, "handle", f"PIN-{number}", f"PIN-{number}", handling)
    b.link("USES", person, key)
    return key


def _cash(b: _Build, person: str, number: str, handling: PlanHandling, px: str = "") -> str:
    key = f"{px}cash:{person.removeprefix(px)}"
    _endpoint(b, key, "account", f"PC-{number}", f"PC-{number}", handling)
    b.link("USES", person, key)
    return key


def _sim(b: _Build, pool: _Pool, key: str, handling: PlanHandling) -> None:
    value = pool.imsi()
    _endpoint(b, key, "imsi", value, value, handling)


def _call_link(
    b: _Build, calls: list[CallAggregate], pin: str, number: str, weekly: tuple[int, ...]
) -> None:
    """The link and the aggregate for one PIN account's calls to one number."""
    live = [w for w, n in enumerate(weekly) if n]
    first = CALL_START + timedelta(days=7 * live[0])
    last = min(CALL_START + timedelta(days=7 * live[-1] + 3), CUT_OFF)
    b.link("COMMUNICATED_WITH", pin, number, occ=sum(weekly), first=first, last=last)
    calls.append(CallAggregate(pin, number, weekly))


def _present(cell: str, day: date) -> list[str]:
    """Who the cast's own tables put in a cell on a day: the principal, then the others by key."""
    out = ["principal"] if any(c == cell and f <= day <= t for c, f, t in _PRINCIPAL_CELLS) else []
    for key, (c, first, last) in _CAST_PRESENT.items():
        if c == cell and first <= day and (last is None or day <= last):
            out.append(key)
    return out


# --- The cast's links (spec 3.1), transcribed ---------------------------------------------


def _add_cast(
    b: _Build, rng: random.Random, pool: _Pool, est: _Estate, calls: list[CallAggregate]
) -> dict[str, _Prisoner]:
    """The cast, entirely: people, groups, endpoints, handsets, incidents, and every link of the
    table. The reports (`report:p1..p3`, `report:pryce`) and what mentions them are the reports
    stage's; the group members' present cells are drawn with the background's."""
    prisoners: dict[str, _Prisoner] = {}
    outside = ("coordinator", "payer", "arrested_outside", *(f"outside_{i}" for i in range(1, 7)))
    for key, (given, family, aliases) in CAST.items():
        if key == "unconnected":
            continue
        is_prisoner = key in _CAST_PRISONERS
        _person(
            b, key, given, family,
            number=pool.prison_number() if is_prisoner else None,
            nino=None if is_prisoner else pool.nino(),
            aliases=aliases, dob=_day(rng, date(1960, 1, 1), date(2001, 12, 28)),
            handling=REGIONAL if key in outside else LOCAL,
        )  # fmt: skip
    for key, name in (
        ("ocg:larkhill-lane", "Larkhill Lane Group"),
        ("ocg:calder-street", "Calder Street Group"),
    ):
        b.entity(key, "Organisation", {"name": name, "org_ref": f"pid:{key}"})
    # Endpoints: a PIN for every cast prisoner, the cash and bank accounts, the two numbers.
    for key in _CAST_PRISONERS:
        number = str(b.ents[key].properties["prison_number"])
        prisoners[key] = _Prisoner(key, est, _pin(b, key, number, LOCAL), 0)
    for key in ("principal", "relay_1", "relay_2"):
        _cash(b, key, str(b.ents[key].properties["prison_number"]), LOCAL)
    _endpoint(b, "number:coordinator", "msisdn", *_COORDINATOR, REGIONAL)
    _endpoint(b, "number:unidentified", "msisdn", *_UNIDENTIFIED, REGIONAL)
    _endpoint(b, "account:payer", "account", "SYN-70417", "SYN-70417", REGIONAL)
    b.link("USES", "coordinator", "number:coordinator")
    b.link("USES", "payer", "account:payer")

    # Seized handsets (Brief 2 R6): each with its SIM; the find's relay is the one it was found
    # with, Pryce's was found with nobody, and a second batch is loaded in chapter 9.
    b.entity("handset:pryce", "Device", {"imei": _imei(rng)}, REGIONAL)
    _sim(b, pool, "sim:pryce", REGIONAL)
    b.link("PAIRED_WITH", "sim:pryce", "handset:pryce")
    b.link(
        "COMMUNICATED_WITH", "sim:pryce", "number:unidentified", occ=30,
        first=date(2026, 1, 12), last=date(2026, 3, 27),
    )  # fmt: skip
    for fkey, when, _item, _cell, relay in _FINDS:
        b.entity(f"handset:{fkey}", "Device", {"imei": _imei(rng)})
        _sim(b, pool, f"sim:{fkey}", LOCAL)
        b.link("PAIRED_WITH", f"sim:{fkey}", f"handset:{fkey}")
        b.link("USES", relay, f"handset:{fkey}", first=when, last=when)
    batch_day = _FIND_DAY["find_07"]
    b.entity("handset:batch2", "Device", {"imei": _imei(rng)})
    _sim(b, pool, "sim:batch2", LOCAL)
    b.link("PAIRED_WITH", "sim:batch2", "handset:batch2")
    b.link("USES", "relay_2", "handset:batch2", first=batch_day, last=batch_day)
    b.link(
        "COMMUNICATED_WITH", "sim:batch2", "number:coordinator", occ=8,
        first=date(2026, 4, 8), last=date(2026, 4, 26),
    )  # fmt: skip

    for key in _CAST_PRISONERS:
        b.link("HELD_AT", key, est.key, first=_CAST_HELD_FROM[key])
    for key in _LARKHILL:
        b.link("MEMBER_OF", key, "ocg:larkhill-lane")
    for key in _CALDER:
        b.link("MEMBER_OF", key, "ocg:calder-street")
    b.link("FAMILY_OF", "principal", "brother", props={"relation": "brother"})
    for other in ("brother", "third_member"):
        b.link("CO_DEFENDANT_OF", "principal", other, props={"case_ref": "pid:case:0417"})
    b.link("CO_DEFENDANT_OF", "brother", "third_member", props={"case_ref": "pid:case:0417"})

    for cell, first, last in _PRINCIPAL_CELLS:
        # His stay in F2-14 is open: the end date of the share is the cut-off, the stay has none.
        b.link(
            "PRESENT_AT",
            "principal",
            f"cell:{cell}",
            first=first,
            last=None if last == CUT_OFF else last,
        )
    for key, (cell, arrived, left) in _CAST_PRESENT.items():
        b.link("PRESENT_AT", key, f"cell:{cell}", first=arrived, last=left)
    for mate, cell, first, last in _CELL_SHARES:
        b.link(
            "SHARED_CELL_WITH", "principal", mate, occ=_weeks(first, last), first=first, last=last,
            props={"cell": cell},
        )  # fmt: skip

    for who, visits, first, last in _PRINCIPAL_VISITS:
        b.link(
            "VISITED", who, "principal", occ=visits, first=first, last=last,
            props={"channel": "in_person"},
        )  # fmt: skip
    for i in range(1, 7):  # the six outside associates visit him, twice each (Brief 2 R3)
        first = date(2026, 1, 8) + timedelta(days=14 * i)
        b.link(
            "VISITED", f"outside_{i}", "principal", occ=2, first=first,
            last=first + timedelta(days=21), props={"channel": "in_person"},
        )  # fmt: skip
    for src, dst, n, first, last, channel in (
        ("mother", "brother", 6, date(2025, 9, 20), date(2026, 4, 4), "in_person"),
        ("sister", "brother", 2, date(2026, 1, 10), date(2026, 3, 7), "in_person"),
        ("coordinator", "relay_3", 4, date(2026, 1, 17), date(2026, 4, 11), "video"),
    ):  # fmt: skip
        b.link("VISITED", src, dst, occ=n, first=first, last=last, props={"channel": channel})

    for who, last, conf in (
        ("relay_1", date(2026, 4, 28), 0.72), ("relay_2", date(2026, 4, 20), 0.68),
        ("relay_3", date(2026, 4, 2), 0.64),
    ):  # fmt: skip
        b.link(
            "PASSES_ITEMS_TO", "principal", who, first=date(2026, 1, 12), last=last,
            props={"channel": "cell line"}, provenance="inferred", by=EXTRACTION_RUN,
            confidence=conf,
        )  # fmt: skip
    for src, dst, last, conf in (
        ("relay_1", "relay_4", date(2026, 4, 21), 0.61),
        ("relay_4", "relay_5", date(2026, 4, 24), 0.57),
    ):  # fmt: skip
        b.link(
            "PASSES_ITEMS_TO", src, dst, first=date(2026, 2, 3), last=last,
            props={"channel": "cell line"}, provenance="inferred", by=EXTRACTION_RUN,
            confidence=conf,
        )  # fmt: skip
    for key in ("larkhill_1", "larkhill_2"):
        b.link("ASSOCIATE_OF", "principal", key)
    b.link("ASSOCIATE_OF", "relay_2", "relay_4")

    # Incidents: the seven finds in relay cells (everyone in the cell that day is its occupant),
    # then the assaults and disorders of 2025, each at a landing, a yard or the visits hall.
    for fkey, when, item, cell, _relay in _FINDS:
        ikey = f"incident:{fkey}"
        b.entity(
            ikey,
            "Incident",
            {
                "name": f"Find {fkey[-2:]}", "incident_ref": f"pid:est1:inc:find:{fkey[-2:]}",
                "category": "find", "item": item, "occurred_at": _at(when, 7, 30),
            },
        )  # fmt: skip
        b.link("OCCURRED_AT", ikey, f"cell:{cell}", first=when, last=when)
        for who in _present(cell, when):
            b.link("ROLE_IN", who, ikey, first=when, last=when, props={"role": "occupant"})
    for ikey, category, when, others, place in _OTHER_INCIDENTS:
        key = f"incident:{ikey}"
        b.entity(
            key,
            "Incident",
            {
                "name": f"{category.title()} {ikey[-1]}", "incident_ref": f"pid:est1:inc:{ikey}",
                "category": category, "occurred_at": _at(when, 14, 10),
            },
        )  # fmt: skip
        b.link("OCCURRED_AT", key, place, first=when, last=when)
        for who in ("principal", *others):
            b.link("ROLE_IN", who, key, first=when, last=when, props={"role": "participant"})

    for who, n, first, last, reason in (
        ("calder_1", 2, date(2025, 3, 10), date(2025, 11, 20), "wing dispute"),
        ("calder_2", 1, date(2025, 8, 14), date(2025, 8, 14), "debt"),
    ):  # fmt: skip
        b.link(
            "IN_CONFLICT_WITH", "principal", who, occ=n, first=first, last=last,
            props={"reason": reason},
        )  # fmt: skip
    b.link(
        "IN_CONFLICT_WITH", "principal", "calder_3", occ=1, first=date(2025, 6, 2),
        last=date(2025, 6, 2), props={"reason": "covert source"}, handling=_SECRET,
    )  # fmt: skip

    # Calls and money: the coordinator's four callers, the number nobody owns, the one payer.
    for who, weekly in (
        ("principal", _PRINCIPAL_CALLS), ("relay_1", _RELAY_CALLS), ("relay_2", _RELAY_CALLS),
        ("relay_3", _RELAY_CALLS),
    ):  # fmt: skip
        _call_link(b, calls, f"pin:{who}", "number:coordinator", weekly)
    for who in ("principal", "relay_2", "brother"):
        _call_link(b, calls, f"pin:{who}", "number:unidentified", _UNIDENTIFIED_CALLS)
    for who, n, amount, first, last in (
        ("principal", 9, 120.0, date(2025, 12, 5), date(2026, 4, 20)),
        ("relay_1", 8, 90.0, date(2025, 12, 12), date(2026, 4, 18)),
        ("relay_2", 8, 75.0, date(2026, 1, 9), date(2026, 4, 10)),
    ):  # fmt: skip
        b.link(
            "TRANSACTED", "account:payer", f"cash:{who}", occ=n, first=first, last=last,
            props={"amount": amount, "transaction_type": "TRANSFER"},
        )  # fmt: skip
    return prisoners


# --- The background: prisoners, their cells, their visitors ---------------------------------


def _bg_prisoners(
    b: _Build,
    rng: random.Random,
    names: _Names,
    pool: _Pool,
    est: _Estate,
    count: int,
    *,
    px: str,
    component: int,
    reserved: frozenset[str] = frozenset(),
    quotas: Mapping[str, int] | None = None,
    first_key: str | None = None,
) -> tuple[list[_Prisoner], dict[str, list[tuple[str, date]]]]:
    """`count` background prisoners, each with a PIN account, one open custody, and a cell
    (never one of `reserved`); `quotas` fixes how many a landing holds, the rest share the others
    evenly. Returns the prisoners and each cell's occupants with the day they arrived."""
    quotas = dict(quotas or {})
    landings = list(est.cells)
    free = [lc for lc in landings if lc not in quotas]
    left = count - sum(quotas.values())
    per = {lc: left // len(free) for lc in free}
    for lc in free[: left % len(free)]:
        per[lc] += 1
    per.update(quotas)
    out: list[_Prisoner] = []
    occupants: dict[str, list[tuple[str, date]]] = {}
    for lc in landings:
        cells = [c for c in est.cells[lc] if c not in reserved]
        rng.shuffle(cells)
        for i in range(per[lc]):
            number = pool.prison_number()
            if first_key and not out:
                key = first_key
                given, family = CAST[first_key][0], CAST[first_key][1]
            else:
                key = f"{px}prisoner:{number}"
                given, family = names.next()
            _person(
                b, key, given, family, number=number,
                dob=_day(rng, date(1958, 1, 1), date(2005, 12, 28)), handling=est.unit,
            )  # fmt: skip
            pin = _pin(b, key, number, est.unit, px)
            arrived = _day(rng, date(2024, 9, 1), date(2026, 3, 31))
            held = arrived - timedelta(days=rng.randrange(200))
            cell = cells[i % len(cells)]
            b.link("HELD_AT", key, est.key, first=held)
            b.link("PRESENT_AT", key, cell, first=arrived)
            occupants.setdefault(cell, []).append((key, arrived))
            out.append(_Prisoner(key, est, pin, component, held, cell))
    return out, occupants


def _place_group(
    b: _Build,
    rng: random.Random,
    est: _Estate,
    occupants: dict[str, list[tuple[str, date]]],
) -> None:
    """The thirteen cast prisoners with background cell-mates sleep in a cell that already holds
    one background prisoner, on the landing `_GROUP_LANDING` names; so no cell holds three."""
    for who, landing in _GROUP_LANDING.items():
        single = [c for c in est.cells[landing] if len(occupants.get(c, ())) == 1]
        cell = rng.choice(single)
        arrived = _day(rng, max(_CAST_HELD_FROM[who], date(2025, 6, 1)), date(2026, 2, 28))
        b.link("PRESENT_AT", who, cell, first=arrived)
        occupants[cell].append((who, arrived))


def _cell_shares(b: _Build, occupants: Mapping[str, list[tuple[str, date]]]) -> None:
    """Co-occupants of a cell share it from the later arrival to the cut-off; one occurrence is
    one week shared, rounded up (D3). A chain, not every pair, so a crowded cell stays readable."""
    for cell, people in occupants.items():
        label = cell.rsplit("cell:", 1)[1]
        ordered = sorted(people, key=lambda p: (p[1], p[0]))
        for (a, a_from), (c, c_from) in zip(ordered, ordered[1:], strict=False):
            first = max(a_from, c_from)
            b.link(
                "SHARED_CELL_WITH", a, c, occ=_weeks(first, CUT_OFF), first=first, last=CUT_OFF,
                props={"cell": label},
            )  # fmt: skip


def _transfers(b: _Build, rng: random.Random, movers: Sequence[_Prisoner], other: _Estate) -> None:
    """An earlier, closed custody at the other establishment: a transfer's first `HELD_AT` ends
    before the open one begins."""
    for p in movers:
        last = p.held - timedelta(days=1)
        b.link(
            "HELD_AT",
            p.key,
            other.key,
            first=last - timedelta(days=rng.randrange(120, 500)),
            last=last,
        )


_REASONS = ("wing dispute", "debt", "canteen", "gang rivalry", "visit dispute", "bullying")
_RELATIONS = ("mother", "father", "sister", "brother", "partner", "cousin", "son", "daughter")
_ROLES = ("participant", "victim", "instigator", "witness")


@dataclass
class _Owners:
    """Who owns which outside number: each number the PIN of a prisoner calls, most called
    first (ties to the lower number), and the numbers already owned."""

    ranked: dict[str, list[str]]  # PIN account key -> number keys, most called first
    taken: set[str]


def _bg_social(
    b: _Build,
    rng: random.Random,
    names: _Names,
    pool: _Pool,
    people: Sequence[_Prisoner],
    *,
    px: str,
    tag: str,
    unit: PlanHandling,
    visitors: int,
    family: int,
    codef: int,
    conflict: int,
    assoc: int,
    incidents: int,
    places: Sequence[str],
    payers: int,
    cash: int,
    pairs: set[tuple[str, str, str]],
    owners: _Owners | None,
) -> None:
    """One establishment's visitors and their visits, and its prisoners' families, co-defendants,
    conflicts, associates and incidents, and its payers' transfers into private cash. Everything
    stays within `people`, and only the background types the spec allows. Family and association
    join two prisoners. A visitor owns one outside number, where there are calls to take it from."""
    keys = [p.key for p in people]
    pin_of = {p.key: p.pin for p in people}

    def pair(link_type: str) -> tuple[str, str] | None:
        for _ in range(50):
            x, y = rng.choice(keys), rng.choice(keys)
            low, high = sorted((x, y))
            if x != y and (link_type, low, high) not in pairs:
                pairs.add((link_type, low, high))
                return x, y
        return None

    def first_free(prisoner: str) -> str | None:
        assert owners is not None
        return next(
            (n for n in owners.ranked.get(pin_of[prisoner], ()) if n not in owners.taken), None
        )

    vkeys: list[str] = []
    for i in range(visitors):
        vkey = f"{px}visitor:{tag}{i:04d}"
        given, fam = names.next()
        _person(
            b, vkey, given, fam, nino=pool.nino(),
            dob=_day(rng, date(1950, 1, 1), date(2006, 12, 28)), handling=unit,
        )  # fmt: skip
        vkeys.append(vkey)
        targets = rng.sample(keys, rng.choice((1, 1, 1, 2, 2, 3)))
        number: str | None = None
        if owners is not None:
            while (number := first_free(targets[0])) is None:
                targets[0] = rng.choice(keys)
            targets = list(dict.fromkeys(targets))
        for target in targets:
            first = _day(rng, date(2025, 9, 1), date(2026, 2, 28))
            b.link(
                "VISITED", vkey, target, occ=rng.randint(1, 12), first=first,
                last=_day(rng, first, date(2026, 4, 25)),
                props={"channel": "video" if rng.randrange(5) == 0 else "in_person"},
            )  # fmt: skip
        if number is not None:
            assert owners is not None
            owners.taken.add(number)
            b.set_handling(number, unit)
            b.link("USES", vkey, number)
    for _ in range(family):
        got = pair("FAMILY_OF")
        if got:
            b.link("FAMILY_OF", *got, props={"relation": rng.choice(_RELATIONS)})
    for n in range(codef):
        got = pair("CO_DEFENDANT_OF")
        if got:
            b.link("CO_DEFENDANT_OF", *got, props={"case_ref": f"pid:case:{tag}{n:04d}"})
    for _ in range(conflict):
        got = pair("IN_CONFLICT_WITH")
        if got:
            first = _day(rng, date(2025, 1, 1), date(2026, 2, 1))
            b.link(
                "IN_CONFLICT_WITH", *got, occ=rng.randint(1, 3), first=first,
                last=_day(rng, first, date(2026, 4, 20)), props={"reason": rng.choice(_REASONS)},
            )  # fmt: skip
    for _ in range(assoc):
        got = pair("ASSOCIATE_OF")
        if got:
            b.link("ASSOCIATE_OF", *got)
    for i in range(incidents):
        ikey = f"{px}incident:bg:{tag}{i:03d}"
        when = _day(rng, date(2025, 6, 1), date(2026, 4, 20))
        category = rng.choice(("assault", "disorder", "other"))
        b.entity(
            ikey,
            "Incident",
            {
                "name": f"{category.title()} {tag}{i:03d}",
                "incident_ref": f"pid:{'scale:' if px else ''}inc:bg:{tag}{i:03d}",
                "category": category, "occurred_at": _at(when, rng.randrange(7, 22)),
            },
            unit,
        )  # fmt: skip
        if places:
            b.link("OCCURRED_AT", ikey, rng.choice(places), first=when, last=when)
        for who in rng.sample(keys, rng.choice((2, 2, 3))):
            b.link("ROLE_IN", who, ikey, first=when, last=when, props={"role": rng.choice(_ROLES)})
    accounts: list[str] = []
    for vkey in vkeys[:payers]:
        akey = f"{px}account:{vkey.removeprefix(px)}"
        value = pool.syn()
        _endpoint(b, akey, "account", value, value, unit)
        b.link("USES", vkey, akey)
        accounts.append(akey)
    by_key = {p.key: p for p in people}
    cash_keys: list[str] = []
    paid: set[str] = set()

    def transfer(payer: str, ckey: str) -> None:
        first = _day(rng, date(2025, 9, 1), date(2026, 2, 28))
        paid.add(payer)
        b.link(
            "TRANSACTED", payer, ckey, occ=rng.randint(1, 8), first=first,
            last=_day(rng, first, date(2026, 4, 25)),
            props={"amount": rng.randint(2_000, 40_000) / 100, "transaction_type": "TRANSFER"},
        )  # fmt: skip

    for target in rng.sample(keys, min(cash, len(keys))):
        number = str(b.ents[target].properties["prison_number"])
        cash_keys.append(_cash(b, target, number, by_key[target].est.unit, px))
        for payer in rng.sample(accounts, min(len(accounts), rng.choice((1, 1, 2)))):
            transfer(payer, cash_keys[-1])
    for payer in accounts:  # an account no transfer used is given one: no bare accounts
        if payer not in paid:
            transfer(payer, rng.choice(cash_keys))


# --- Reports (spec 5) ---------------------------------------------------------------------


@dataclass
class _Rep:
    key: str
    day: date
    areas: list[str]
    label: str
    kind: str  # the text's shape: line, illicit, plain, yard, free, or cast
    persons: list[str]
    landing: str = ""


def _who(b: _Build, key: str) -> str:
    return str(b.ents[key].properties["family_name"])


def _list_of(parts: Sequence[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


_ITEMS = (
    "a handset",
    "a SIM card",
    "a quantity of drugs",
    "tobacco",
    "spice-soaked paper",
    "a second handset",
)
_ILLICIT_LINE = (
    "Officer {s} reports that {names} were seen at the cell door after lock-up passing {item} "
    "along the line between cells. The matter is logged for the security meeting.",
    "Cell search on {landing}: {item} recovered. {names} named by a reliable source as involved "
    "in the line between cells that runs after lock-up. No adjudication yet.",
)
_ILLICIT_OTHER = (
    "Intelligence from the wing: {names} said to hold {item}, passed between cells at night. "
    "Officer {s} to monitor {landing}.",
    "Following a visit, {names} linked to {item} arriving by the yard and moved up {landing}. "
    "Officer {s} recommends a targeted search.",
    "{names} seen at the {landing} servery swapping {item} for canteen goods. Reported by "
    "Officer {s}; no search made.",
)
_PLAIN = (
    "Officer {s} recorded a verbal dispute on {landing} involving {names} over the television "
    "rota. Dealt with informally; no further action.",
    "{names} complained to Officer {s} about the canteen order on {landing}. Referred to the "
    "wing manager.",
    "Wing job allocation on {landing}: {names} moved to laundry duty. Officer {s} notes no "
    "concerns.",
)
_YARD = (
    "Exercise period, yard {yard}: Officer {s} moved {names} on from the fence line. No "
    "contact with the outside was seen.",
    "Yard {yard} patrol: {names} loitering near the boundary during association. Officer {s} "
    "logged it for information.",
)
_FREE = (
    "Routine check of {label} by Officer {s}: no concerns recorded, the area was clean and "
    "orderly.",
    "Officer {s} reports a quiet shift at {label}. Patrols made on the hour; nothing to add.",
    "Maintenance visit to {label}: a light was replaced and a door closer adjusted. Officer {s} "
    "present throughout.",
)
_TEMPLATES = {"line": _ILLICIT_LINE, "illicit": _ILLICIT_OTHER, "plain": _PLAIN, "yard": _YARD}


def _report_text(rng: random.Random, b: _Build, r: _Rep, number: int) -> str:
    s = rng.choice(STAFF_NAMES)
    head = f"IR {number:04d}. "
    if r.kind == "free":
        return head + rng.choice(_FREE).format(s=s, label=r.label)
    names = _list_of([f"Prisoner {_who(b, p)}" for p in r.persons])
    landing = f"{r.landing} landing" if r.landing else r.label
    return head + rng.choice(_TEMPLATES[r.kind]).format(
        s=s, names=names, item=rng.choice(_ITEMS), landing=landing, yard=r.label[-2:]
    )


def _cast_text(c: _CastReport, ir: int) -> str:
    """A cast report's text, every name read from `CAST` and the number from the cast's own."""
    raw = _COORDINATOR[0]
    return c.text.format(
        ir=ir,
        staff=STAFF_NAMES[0],
        cally=CAST["principal"][2][0],
        mo=CAST["coordinator"][2][0],
        number_raw=raw,
        number_plain=raw.replace(" ", ""),
        number_intl="+44 " + raw[1:],
        unidentified_raw=_UNIDENTIFIED[0],
        **{k: v[1] for k, v in CAST.items()},
    )


def _reports(
    b: _Build,
    rng: random.Random,
    throw: Sequence[tuple[str, str, datetime]],
    f2_bg: Sequence[str],
    fenwick_bg: Sequence[str],
) -> dict[str, str]:
    """The 350 reports: 229 meeting the rule (177 on Wing F, 52 in the hotspot yards), 40 in the
    zone before any throw-over data exists, 81 about other wings and yards or the arrest; 68 of
    the 229 name people. The keys follow a fixed order, so which report is which never moves with
    the seed; the choices below are by kind, never by position."""
    hot_days = sorted({when.date() for _k, yard, when in throw if yard in HOTSPOT_YARDS})
    hot_yards = sorted(HOTSPOT_YARDS)
    other_yards = sorted(set(YARD_COUNTS) - HOTSPOT_YARDS)
    specs: list[_Rep] = []
    for key, block in _block_keys():
        landing = ""
        if block.where in ("f2", "f1", "wing_f"):
            landing = {"f2": "F2", "f1": "F1"}.get(block.where) or rng.choice(("F1", "F2"))
            areas, label = ["wing:F", f"landing:{landing}"], f"{landing} landing"
        elif block.where == "hotspot":
            code = rng.choice(hot_yards)
            areas, label = [f"yard:{code}", "wing:F"], f"Yard {code}"
        elif block.where == "other_wing":
            wing = rng.choice("ABCDE")
            areas, label = [f"wing:{wing}"], f"Wing {wing}"
        else:
            code = rng.choice(other_yards)
            areas, label = [f"yard:{code}", f"wing:{_YARD_WINGS[code]}"], f"Yard {code}"
        day = {
            "window": lambda: rng.choice(hot_days),
            "before": lambda: _day(rng, date(2026, 1, 5), date(2026, 2, 27)),
            "anywhere": lambda: _day(rng, date(2026, 1, 5), date(2026, 4, 30)),
        }[block.when]()
        specs.append(_Rep(key, day, areas, label, block.kind, [], landing))
    background = list(specs)
    for c in _CAST_REPORTS:
        areas = [c.area] if c.area.startswith("place:") else ["wing:F", "landing:F2", c.area]
        label = "Arrest site" if c.area.startswith("place:") else "F2 landing"
        day = c.day or rng.choice(hot_days)
        specs.append(_Rep(c.key, day, areas, label, "cast", list(c.persons), "F2"))
    assert len(specs) == REPORTS_TOTAL

    # Who the other twenty illicit reports name: twenty-three mentions over twenty reports.
    bg12 = rng.sample(list(f2_bg), 12)
    mentions = [
        "brother", "relay_3", "relay_5", "larkhill_1", "larkhill_2",
        *(f"calder_{i}" for i in range(2, 8)), *bg12,
    ]  # fmt: skip
    rng.shuffle(mentions)
    illicit = [s for s in background if s.kind in ("line", "illicit")]
    for rep, who in zip(illicit, mentions[: len(illicit)], strict=True):
        rep.persons.append(who)
    for slot, who in zip(
        rng.sample(range(len(illicit)), len(mentions) - len(illicit)),
        mentions[len(illicit) :],
        strict=True,
    ):
        illicit[slot].persons.append(who)
    # The 45 others name background prisoners, none more than twice anywhere.
    used_by: Counter[str] = Counter(bg12)
    pool = [k for k in fenwick_bg if k not in used_by]
    for rep in (s for s in background if s.kind in ("plain", "yard")):
        for who in rng.sample(pool, rng.choice((1, 1, 2))):
            if used_by[who] < 2:
                rep.persons.append(who)
                used_by[who] += 1
        while not rep.persons:
            who = rng.choice(pool)
            if used_by[who] < 2:
                rep.persons.append(who)
                used_by[who] += 1

    # Handling: twelve consult-originator, twenty covert-development, disjoint.
    s2 = {s.key for s in rng.sample(background, 11)} | {c.key for c in _CAST_REPORTS if c.s2}
    open_ones = [s for s in background if s.key not in s2]
    a1 = {s.key for s in rng.sample([s for s in open_ones if s.persons], 5)}
    a1 |= {s.key for s in rng.sample([s for s in open_ones if not s.persons], 15)}

    # Numbers by date, then the entities, the places that mention them, the persons, the
    # throw-overs of the day.
    ordered = sorted(specs, key=lambda s: (s.day, s.key))
    numbers = {s.key: i for i, s in enumerate(ordered, 1)}
    cast_by_key = {c.key: c for c in _CAST_REPORTS}
    texts: dict[str, str] = {}
    incidents_by_day: dict[date, list[tuple[str, str]]] = {}
    for ikey, yard, when in throw:
        incidents_by_day.setdefault(when.date(), []).append((ikey, yard))
    users_of = {y: {f"yard:{y}", f"wing:{_YARD_WINGS[y]}"} for y in YARD_COUNTS}
    for rep in specs:
        cast = cast_by_key.get(rep.key)
        if cast is not None:
            handling = REGIONAL if cast.key == "report:pryce" else LOCAL
            if cast.s2:
                handling = PlanHandling(sanitisation_code="S2")
        else:
            handling = PlanHandling(
                originator=REGIONAL_UNIT if rep.key in a1 else LOCAL_UNIT,
                owning_unit=REGIONAL_UNIT if rep.key in a1 else LOCAL_UNIT,
                action_code="A1" if rep.key in a1 else None,
                sanitisation_code="S2" if rep.key in s2 else None,
            )
        b.entity(
            rep.key,
            "Document",
            {
                "title": f"IR {numbers[rep.key]:04d} — {rep.label}",
                "sent_at": _at(rep.day, 9), "media_kind": "text", "document_kind": "other",
            },
            handling,
        )  # fmt: skip
        texts[rep.key] = (
            _cast_text(cast, numbers[rep.key])
            if cast is not None
            else _report_text(rng, b, rep, numbers[rep.key])
        )
        for area in rep.areas:
            b.link("MENTIONED_IN", area, rep.key)
        for who in rep.persons:
            b.link("MENTIONED_IN", who, rep.key)
        for ikey, yard in incidents_by_day.get(rep.day, ()):
            if users_of[yard] & set(rep.areas):
                b.link("MENTIONED_IN", ikey, rep.key)
    return texts


# --- Numbers and calls (spec 7) -----------------------------------------------------------


def _outside_numbers() -> list[tuple[str, str]]:
    """The 1,500 numbers the PID may call, as (written form, E.164), lowest first: 07700 900600
    to 900899 and 0116 / 0117 496 0000 to 0599, all inside the drama blocks `msisdn` accepts
    (D5)."""
    out = [(f"07700 900{n}", f"+447700900{n}") for n in range(600, 900)]
    for area in ("0116", "0117"):
        out += [(f"{area} 496 {n:04d}", f"+44{area[1:]}496{n:04d}") for n in range(600)]
    return sorted(out, key=lambda n: n[1])


def _bg_calls(
    b: _Build,
    rng: random.Random,
    calls: list[CallAggregate],
    components: Sequence[tuple[Sequence[str], Sequence[str]]],
) -> dict[str, list[str]]:
    """The high-volume file's shape: every PIN account calls at least one number, every number is
    called, and the weeks add up to exactly `CALL_ROWS` with the cast's own calls. All integers.
    Returns each PIN account's numbers, most called first, ties to the lower number."""
    pairs: list[tuple[str, str]] = []
    for pins, numbers in components:
        seen: set[tuple[str, str]] = set()
        order = list(numbers)
        rng.shuffle(order)
        for i, number in enumerate(order):
            seen.add((pins[i % len(pins)], number))
        for pin in pins:
            for _ in range(rng.choice((0, 1, 1, 2))):
                seen.add((pin, rng.choice(order)))
        pairs += sorted(seen)
    target = CALL_ROWS - sum(sum(c.weekly) for c in calls)
    weights = [rng.randint(1, 40) ** 2 for _ in pairs]
    total_weight = sum(weights)
    totals = [max(25, target * w // total_weight) for w in weights]
    diff = target - sum(totals)
    i = 0
    while diff:
        step = 1 if diff > 0 else -1
        if step > 0 or totals[i % len(totals)] > 25:
            totals[i % len(totals)] += step
            diff -= step
        i += 1
    for (pin, number), total in zip(pairs, totals, strict=True):
        start = 0 if rng.randrange(5) < 3 else rng.randrange(1, 26)
        end = _LAST_WEEK if rng.randrange(5) < 4 else rng.randrange(start + 4, _LAST_WEEK)
        shares = [0] * CALL_WEEKS
        for w in range(start, end + 1):
            shares[w] = rng.randint(40, 160) * (4 if w == _LAST_WEEK else 7)  # a part week
        norm = sum(shares)
        weekly = [total * x // norm for x in shares]
        for _ in range(total - sum(weekly)):
            weekly[rng.randrange(start, end + 1)] += 1
        _call_link(b, calls, pin, number, tuple(weekly))
    called: dict[str, Counter[str]] = {}
    for c in calls:
        called.setdefault(c.pin, Counter())[c.number] += sum(c.weekly)
    return {
        pin: [n for n, _c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        for pin, counts in called.items()
    }


# --- Pictures (D9; the bytes are stage 5's) -----------------------------------------------


def _pictures(b: _Build) -> tuple[str, ...]:
    """Every person, every establishment, Fenwick Moor's six wings and twelve yards, every
    handset and both groups gets an image `Document` and one `DEPICTS`, except an entity first
    loaded after the seed: Brief 2 attaches pictures at the seed, before such an entity exists
    (Pryce, whom R9 creates as a report's subject, and the second handset)."""
    visitors = {lk.source for lk in b.links if lk.link_type == "VISITED"}
    late = {"handset:batch2", "sim:batch2"} | {
        e.key
        for e in b.ents.values()
        if e.entity_type == "Person" and "prison_number" not in e.properties
        and e.key not in visitors
    }  # fmt: skip
    subjects = sorted(
        e.key
        for e in b.ents.values()
        if e.key not in late
        and (
            e.entity_type in ("Person", "Establishment", "Device", "Organisation")
            or str(e.properties.get("site_ref", "")).startswith(
                ("pid:est1:wing:", "pid:est1:yard:")
            )
        )
    )
    for n, key in enumerate(subjects, 1):
        subject = b.ents[key]
        name = subject.properties.get("name") or subject.properties.get("family_name") or key
        pic = f"picture:{key}"
        b.entity(
            pic,
            "Document",
            {
                "title": f"Picture of {name}", "media_kind": "image",
                "object_ref": f"pid/pictures/{n:05d}.png",
            },
            subject.handling,
        )  # fmt: skip
        b.link("DEPICTS", pic, key, props={"shown": True})
    return tuple(subjects)


def _moments(b: _Build) -> dict[str, Moment]:
    """Every link's moment: those of the second seized handset are chapter 9, those touching a
    report are chapter 4, the rest are the seed's."""
    batch = {"handset:batch2", "sim:batch2"}
    reports = {
        e.key
        for e in b.ents.values()
        if e.entity_type == "Document" and e.properties.get("media_kind") == "text"
    }
    out: dict[str, Moment] = {}
    for lk in b.links:
        ends = {lk.source, lk.target}
        out[lk.key] = "chapter9" if ends & batch else "chapter4" if ends & reports else "seed"
    return out


# --- The two profiles -------------------------------------------------------------------------


def _demo(rng: random.Random, seed: int) -> Plan:
    b = _Build()
    calls: list[CallAggregate] = []
    fen = _fenwick(b)
    salt = _estate(
        b, index=2, key="est:saltmarsh-grange", kp="est2:", sp="pid:est2:",
        name="Saltmarsh Grange Prison", ref="pid:est:saltmarsh-grange", niu="PID NIU Area 3",
        soct="PID SOCT Region South", category="C", wings="AB", yards={}, unit=REGIONAL,
    )  # fmt: skip
    brin = _estate(
        b, index=3, key="est:brindle-heath", kp="est3:", sp="pid:est3:",
        name="Brindle Heath Prison", ref="pid:est:brindle-heath", niu="PID NIU Area 4",
        soct="PID SOCT Region North", category="C", wings="A", yards={}, unit=REGIONAL,
    )  # fmt: skip
    b.entity(
        "place:arrest-site",
        "Location",
        {"name": "Arrest site", "site_ref": "pid:out:place:arrest-01"},
        REGIONAL,
    )
    throw = _throw_overs(b, rng)
    pool, names = _Pool(rng, "demo"), _Names(rng)
    cast = _add_cast(b, rng, pool, fen, calls)
    reserved = frozenset(f"cell:{c}" for c in _CAST_CELLS)
    fen_people, fen_occ = _bg_prisoners(
        b, rng, names, pool, fen, 650 - len(cast), px="", component=0, reserved=reserved,
        quotas={"F2": 34, "F1": 42},
    )  # fmt: skip
    _place_group(b, rng, fen, fen_occ)
    salt_people, salt_occ = _bg_prisoners(b, rng, names, pool, salt, 230, px="", component=0)
    brin_people, brin_occ = _bg_prisoners(
        b, rng, names, pool, brin, 120, px="", component=1, first_key="unconnected"
    )  # fmt: skip
    for occupants in (fen_occ, salt_occ, brin_occ):
        _cell_shares(b, occupants)
    _transfers(b, rng, rng.sample(fen_people, 35), salt)
    _transfers(b, rng, rng.sample(salt_people, 25), fen)

    # Numbers, lowest first: the coordinator's and the unidentified one are the cast's; the rest
    # are the background's, with Brindle Heath's own set so no number is called from both
    # components. An owner's unit is given to its number when the owner is known.
    free = [n for n in _outside_numbers() if n[1] not in (_COORDINATOR[1], _UNIDENTIFIED[1])]
    keys = []
    for i, (raw, normalised) in enumerate(free, 1):
        keys.append(f"number:{i:04d}")
        _endpoint(b, keys[-1], "msisdn", raw, normalised)
    brindle_numbers = set(rng.sample(range(len(keys)), 180))
    brindle_keys = [k for i, k in enumerate(keys) if i in brindle_numbers]
    main_keys = [k for i, k in enumerate(keys) if i not in brindle_numbers]
    restricted = {"principal", "relay_1", "relay_2", "relay_3", "brother"}
    main_pins = [
        p.pin for p in [*cast.values(), *fen_people, *salt_people] if p.key not in restricted
    ]
    ranked = _bg_calls(
        b, rng, calls, [(main_pins, main_keys), ([p.pin for p in brin_people], brindle_keys)]
    )  # fmt: skip
    owners = _Owners(ranked, set())

    # The seized SIMs call two to four background numbers (R6); the coordinator's batch-two SIM
    # calls the coordinator alone.
    for fkey, when, *_rest in _FINDS:
        for number in rng.sample(main_keys, rng.randint(2, 4)):
            first = _day(rng, date(2025, 12, 1), when)
            b.link(
                "COMMUNICATED_WITH", f"sim:{fkey}", number, occ=rng.randint(1, 9), first=first,
                last=_day(rng, first, when),
            )  # fmt: skip

    pairs: set[tuple[str, str, str]] = set()
    for people, tag, unit, counts in (
        (fen_people, "a", LOCAL, (380, 70, 50, 60, 170, 28, 100, 110)),
        (salt_people, "s", REGIONAL, (140, 25, 18, 22, 60, 12, 40, 45)),
        (brin_people, "b", REGIONAL, (70, 15, 10, 12, 35, 6, 20, 22)),
    ):
        est = people[0].est
        visitors, family, codef, conflict, assoc, incidents, payers, cash = counts
        _bg_social(
            b, rng, names, pool, people, px="", tag=tag, unit=unit, visitors=visitors,
            family=family, codef=codef, conflict=conflict, assoc=assoc, incidents=incidents,
            places=[*est.landing_keys.values(), f"{est.kp}hall:visits"], payers=payers, cash=cash,
            pairs=pairs, owners=owners,
        )  # fmt: skip
    f2_bg = [p.key for p in fen_people if p.cell.startswith("cell:F2-")]
    texts = _reports(b, rng, throw, f2_bg, [p.key for p in fen_people])
    subjects = _pictures(b)
    b.finish()
    return Plan(
        profile="demo", seed=seed, entities=tuple(b.ents.values()), links=tuple(b.links),
        calls=tuple(calls), report_texts=texts, picture_subjects=subjects,
        moment_of=_moments(b),
    )  # fmt: skip


_SCALE_ESTABLISHMENTS = (
    ("fenwick-moor", ESTABLISHMENT_NAME, "B"),
    ("saltmarsh-grange", "Saltmarsh Grange Prison", "C"),
    ("brindle-heath", "Brindle Heath Prison", "C"),
    ("corrie-vale", "Corrie Vale Prison", "C"),
    ("thistlemoor", "Thistlemoor Prison", "B"),
    ("wexcombe-down", "Wexcombe Down Prison", "D"),
)


def _scale(rng: random.Random, seed: int) -> Plan:
    """3,000 prisoners and exactly 30,000 links across six establishments; no cast, no reports,
    no calls, no pictures, no throw-overs. Fenwick Moor's data is local and every other
    establishment's regional, with its visitors', incidents' and accounts'. The top-up is
    `ASSOCIATE_OF`, the cheapest link there is."""
    b = _Build()
    pool, names = _Pool(rng, "scale"), _Names(rng)
    estates = [
        _estate(
            b, index=i, key=f"scale:est:{slug}", kp=f"scale:e{i}:", sp=f"pid:scale:e{i}:",
            name=name, ref=f"pid:scale:est:{slug}", niu=f"PID NIU Area {i}",
            soct="PID SOCT Region South" if i % 2 else "PID SOCT Region North",
            category=category, wings="AB", yards={"01": "A", "02": "B"},
            unit=LOCAL if i == 1 else REGIONAL,
            cells_per_landing=64,  # 500 prisoners, never more than two to a cell
        )
        for i, (slug, name, category) in enumerate(_SCALE_ESTABLISHMENTS, 1)
    ]  # fmt: skip
    by_est: list[list[_Prisoner]] = []
    for est in estates:
        got, occupants = _bg_prisoners(b, rng, names, pool, est, 500, px="scale:", component=0)
        _cell_shares(b, occupants)
        by_est.append(got)
    people = [p for group in by_est for p in group]
    for i, est in enumerate(estates):
        _transfers(b, rng, rng.sample(by_est[i], 25), estates[(i + 1) % 6])
    pairs: set[tuple[str, str, str]] = set()
    for i, group in enumerate(by_est):
        _bg_social(
            b, rng, names, pool, group, px="scale:", tag=f"s{i}", unit=estates[i].unit,
            visitors=283, family=67, codef=83, conflict=83, assoc=0, incidents=33, places=(),
            payers=37, cash=75, pairs=pairs, owners=None,
        )  # fmt: skip
    groups: list[str] = []
    seen_names: set[str] = set()
    for i in range(12):
        while True:
            street = rng.choice(("Lane", "Street", "Row", "Quay", "Yard"))
            label = f"{rng.choice(SURNAMES)} {street} Group"
            if label not in seen_names:
                seen_names.add(label)
                break
        gkey = f"scale:ocg:{i:02d}"
        b.entity(gkey, "Organisation", {"name": label, "org_ref": f"pid:scale:ocg:{i:02d}"})
        groups.append(gkey)
    for p in rng.sample(people, 450):
        b.link("MEMBER_OF", p.key, rng.choice(groups))
    keys = [p.key for p in people]
    assert len(b.links) <= SCALE_LINKS, f"the scale plan already holds {len(b.links)} links"
    while len(b.links) < SCALE_LINKS:
        x, y = rng.sample(keys, 2)
        low, high = sorted((x, y))
        if ("ASSOCIATE_OF", low, high) not in pairs:
            pairs.add(("ASSOCIATE_OF", low, high))
            b.link("ASSOCIATE_OF", x, y)
    b.finish()
    return Plan(
        profile="scale", seed=seed, entities=tuple(b.ents.values()), links=tuple(b.links),
        calls=(), report_texts={}, picture_subjects=(), moment_of=dict.fromkeys(
            (lk.key for lk in b.links), "seed"
        ),
    )  # fmt: skip


def build_plan(profile: Profile = "demo", seed: int = SEED) -> Plan:
    """The plan for one profile, deterministic from `seed`."""
    rng = random.Random(seed)
    if profile == "demo":
        return _demo(rng, seed)
    if profile == "scale":
        return _scale(rng, seed)
    raise ValueError(f"unknown profile {profile!r}: expected 'demo' or 'scale'")


def bulk_list(plan: Plan) -> tuple[str, ...]:
    """The prisoners on landing F2 at the cut-off, in key order: the list the demo's bulk-add
    scene pastes. A person is on it when a `PRESENT_AT` of a cell of the landing is open at the
    cut-off (no end date, or one on the cut-off or later)."""
    cells = {
        lk.source for lk in plan.links if lk.link_type == "PART_OF" and lk.target == "landing:F2"
    }
    out: set[str] = set()
    for lk in plan.links:
        if lk.link_type != "PRESENT_AT" or lk.target not in cells:
            continue
        if plan.entity(lk.source).entity_type != "Person":
            continue
        last = lk.last_seen if lk.last_seen is None else _as_day(lk.last_seen)
        if last is None or last >= CUT_OFF:
            out.add(lk.source)
    return tuple(sorted(out))


def _as_day(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


# --- The load contract (ADR-120; the owner's ruling "Plan defines; Brief 2 adds") ------------


@dataclass(frozen=True)
class LoadShape:
    """One kind of link the plan holds and where it is loaded from. The ends are the entity type
    with a discriminator where one type is written by more than one recipe: `Person:prisoner` (a
    prison number), `Person:visitor` (an outsider R3's visits create) and `Person:named` (an
    outsider R9 creates as a report's subject); `Endpoint:<kind>`; `Incident:throw_over` against
    `Incident:other`; `Location:<kind>`. `source_key` and `target_key` name the file's column for
    each end (a report's area link names the area column it comes from); `columns` include both
    and a column for each property. `moment` is when the link loads; `handling` is "recipe" when
    every row of the file has one handling, "column" when the file carries its own
    classification, originator and owning unit columns."""

    link_type: str
    source_type: str
    target_type: str
    properties: frozenset[str]
    file: str
    recipe: str  # "R1" to "R13", "seed" for the two ADR-120 carve-outs, or "new:pid-<name>"
    moment: Moment
    source_key: str
    target_key: str
    columns: tuple[str, ...]
    handling: Literal["recipe", "column"]
    brief2_addition: str | None


@dataclass(frozen=True)
class EntityShape:
    """One kind of entity the plan holds, where it is loaded from and when, and which of its
    properties the file carries (an entity's properties must be a subset of exactly one shape's
    for its kind and moment). `key` is the file's column that identifies it."""

    entity_type: str
    properties: frozenset[str]
    file: str
    recipe: str
    moment: Moment
    key: str
    columns: tuple[str, ...]
    handling: Literal["recipe", "column"]
    brief2_addition: str | None


#: The files whose rows carry more than one handling (Fenwick Moor's and the other
#: establishments', a report with a covert-development code, the one SECRET link): the plan test
#: derives the list from the plan and fails if this one is wrong.
_COLUMN_FILES = frozenset(
    {
        "pid_nomis_prisoners.csv", "pid_nomis_cell_stays.csv", "pid_nomis_cell_shares.csv",
        "pid_nomis_visits.csv", "pid_nomis_incidents.csv", "pid_pin_calls.csv",
        "pid_seized_comms_batch1.csv", "pid_seized_comms_batch2.csv", "pid_prisoner_money.csv",
        "pid_codefendants.csv",
        "pid_intel_reports.csv", "pid_establishment_plan.csv", "pid_family_and_associates.csv",
        "pid_conflicts.csv", "pid_soc_nominals.csv", "pid_number_owners.csv",
    }
)  # fmt: skip
_COLUMNS_CLAUSE = "the file must carry classification, originator and owning unit columns"
_AREAS = (
    "R9 must gain area_ref_2 and area_ref_3 columns so a report names its wing, its landing and "
    "its cell, or its yard and the wing that uses it."
)
_ZONE_PARENT = (
    "R11 must gain the zone kind and a second parent column, so Wing F and the four hotspot yards "
    "sit in both their establishment and the zone."
)
_PRISONERS = "pid_nomis_prisoners.csv"
_STAYS = "pid_nomis_cell_stays.csv"
_VISITS = "pid_nomis_visits.csv"
_INCIDENTS = "pid_nomis_incidents.csv"
_PINS = "pid_pin_calls.csv"
_BATCH_1 = "pid_seized_comms_batch1.csv"
_BATCH_2 = "pid_seized_comms_batch2.csv"
_MONEY = "pid_prisoner_money.csv"
_REPORTS = "pid_intel_reports.csv"
_ESTATE = "pid_establishment_plan.csv"
_NO = frozenset[str]()
_P = "Person:prisoner"
_V = "Person:visitor"
_N = "Person:named"
_NEW_STAYS = "new:pid-cell-stays"
_NEW_CONFLICTS = "new:pid-conflicts"
_NEW_OWNERS = "new:pid-number-owners"
_DOC = "Document"
_SUBJECT = (
    "R9 must take a prison number or a NINO in its subject columns, and a per-row originator "
    "and owning unit."
)
_NAMED = (
    "R9's subject columns must create an outsider from a NINO and names, not only refer to one."
)
_FOUND_WITH = (
    "R6's found-with column may be empty (Pryce's handset) and needs a when gate so no empty "
    "row writes a link."
)


def _link(
    link_type: str, source: str, target: str, file: str, recipe: str, keys: tuple[str, str],
    *, props: frozenset[str] = _NO, extra: tuple[str, ...] = (), moment: Moment = "seed",
    addition: str | None = None,
) -> tuple[Any, ...]:  # fmt: skip
    return (link_type, source, target, props, file, recipe, moment, *keys, extra, addition)


_AT = ("first_seen",)
_SPAN = ("first_seen", "last_seen")
_PART = ("ref", "parent_ref")
_LINK_ROWS: tuple[tuple[Any, ...], ...] = (
    _link("HELD_AT", _P, "Establishment", _PRISONERS, "R1", ("prison_number", "establishment_ref"),
          extra=_SPAN, addition="R1 must be split so custody carries its own first and last seen "
          "interval, a closed transfer stay ending before the open one begins."),
    _link("USES", _P, "Endpoint:handle", _PINS, "R5", ("prison_number", "pin")),
    _link("PRESENT_AT", _P, "Location:cell", _STAYS, _NEW_STAYS, ("prison_number", "cell_ref"),
          extra=_SPAN, addition="R1 must be split so cell stays are their own rows, each with its "
          "own first and last seen interval, and writes no PART_OF cell to wing beyond what the "
          "plan has."),
    _link("SHARED_CELL_WITH", _P, _P, "pid_nomis_cell_shares.csv", "R2",
          ("prison_number_a", "prison_number_b"), props=frozenset({"cell"}),
          extra=("weeks", *_SPAN),
          addition="R2's link must carry the plan's last day, not the last week's Monday."),
    _link("VISITED", _V, _P, _VISITS, "R3", ("visitor_ref", "prison_number"),
          props=frozenset({"channel"}), extra=("visits", *_SPAN)),
    _link("ROLE_IN", _P, "Incident:other", _INCIDENTS, "R4", ("prison_number", "incident_ref"),
          props=frozenset({"role"}), extra=_AT),
    _link("IN_CONFLICT_WITH", _P, _P, "pid_conflicts.csv", _NEW_CONFLICTS,
          ("prison_number_a", "prison_number_b"), props=frozenset({"reason"}),
          extra=("episodes", *_SPAN),
          addition="Brief 2 must add a conflicts file with a per-row classification column for "
          "the one SECRET link, besides the originator and owning unit."),
    *(
        _link("OCCURRED_AT", "Incident:other", f"Location:{kind}", _INCIDENTS, "R4",
              ("incident_ref", "place_ref"), extra=_AT)
        for kind in ("cell", "hall", "landing", "yard")
    ),
    _link("COMMUNICATED_WITH", "Endpoint:handle", "Endpoint:msisdn", _PINS, "R5",
          ("pin", "number"), extra=("weekly_calls", *_SPAN)),
    _link("USES", _V, "Endpoint:msisdn", "pid_number_owners.csv", _NEW_OWNERS,
          ("owner_ref", "number"),
          addition="Brief 2 must add a number-owner file giving the coordinator and each visitor "
          "the one outside number they own."),
    _link("USES", _P, "Device", _BATCH_1, "R6", ("found_with", "handset_imei"), extra=("when",),
          addition=_FOUND_WITH),
    _link("PAIRED_WITH", "Endpoint:imsi", "Device", _BATCH_1, "R6", ("imsi", "handset_imei")),
    _link("COMMUNICATED_WITH", "Endpoint:imsi", "Endpoint:msisdn", _BATCH_1, "R6",
          ("imsi", "number"), extra=("calls", *_SPAN)),
    _link("USES", _P, "Device", _BATCH_2, "R6", ("found_with", "handset_imei"), extra=("when",),
          moment="chapter9", addition=_FOUND_WITH),
    _link("PAIRED_WITH", "Endpoint:imsi", "Device", _BATCH_2, "R6", ("imsi", "handset_imei"),
          moment="chapter9"),
    _link("COMMUNICATED_WITH", "Endpoint:imsi", "Endpoint:msisdn", _BATCH_2, "R6",
          ("imsi", "number"), extra=("calls", *_SPAN), moment="chapter9"),
    _link("TRANSACTED", "Endpoint:account", "Endpoint:account", _MONEY, "R7",
          ("payer_account", "cash_account"),
          props=frozenset({"amount", "transaction_type"}), extra=("transfers", "first_seen")),
    _link("USES", _P, "Endpoint:account", _MONEY, "R7", ("owner_ref", "account")),
    _link("USES", _V, "Endpoint:account", _MONEY, "R7", ("owner_ref", "account")),
    _link("CO_DEFENDANT_OF", _P, _P, "pid_codefendants.csv", "R8",
          ("prison_number_a", "prison_number_b"), props=frozenset({"case_ref"})),
    _link("MENTIONED_IN", _P, _DOC, _REPORTS, "R9", ("subject_ref", "report_ref"),
          extra=("originator", "owning_unit"), moment="chapter4", addition=_SUBJECT),
    _link("MENTIONED_IN", _N, _DOC, _REPORTS, "R9", ("subject_ref", "report_ref"),
          extra=("originator", "owning_unit"), moment="chapter4", addition=_NAMED),
    *(
        _link("MENTIONED_IN", f"Location:{kind}", _DOC, _REPORTS, "R9", (column, "report_ref"),
              moment="chapter4", addition=_AREAS)
        for kind, column in (
            ("wing", "area_ref"), ("wing", "area_ref_2"), ("landing", "area_ref_2"),
            ("cell", "area_ref_3"), ("yard", "area_ref"), ("place", "area_ref"),
        )
    ),
    _link("MENTIONED_IN", "Incident:throw_over", _DOC, _REPORTS, "R9",
          ("incident_refs", "report_ref"), moment="chapter4",
          addition="R9 must gain incident_refs, or a report-incident file, naming the throw-overs "
          "of the day."),
    _link("OCCURRED_AT", "Incident:throw_over", "Location:yard", "pid_throwover_log.csv", "R10",
          ("incident_ref", "yard_ref"), props=frozenset({"lat", "lon", "yard", "item_type"}),
          extra=("occurred_at",)),
    _link("PART_OF", "Location:cell", "Location:landing", _ESTATE, "R11", _PART),
    _link("PART_OF", "Location:landing", "Location:wing", _ESTATE, "R11", _PART),
    _link("PART_OF", "Location:wing", "Establishment", _ESTATE, "R11", _PART),
    _link("PART_OF", "Location:yard", "Establishment", _ESTATE, "R11", _PART),
    _link("PART_OF", "Location:hall", "Establishment", _ESTATE, "R11", _PART),
    _link("PART_OF", "Location:wing", "Location:zone", _ESTATE, "R11", ("ref", "parent_ref_2"),
          addition=_ZONE_PARENT),
    _link("PART_OF", "Location:yard", "Location:zone", _ESTATE, "R11", ("ref", "parent_ref_2"),
          addition=_ZONE_PARENT),
    _link("ADJOINS", "Location:yard", "Location:wing", _ESTATE, "R11", ("ref", "adjoins_ref")),
    _link("USED_BY", "Location:yard", "Location:wing", _ESTATE, "R11", ("ref", "used_by_ref")),
    _link("MEMBER_OF", _P, "Organisation", "pid_soc_nominals.csv", "R12",
          ("prison_number", "org_ref")),
    _link("FAMILY_OF", _P, _P, "pid_family_and_associates.csv", "R13",
          ("prison_number_a", "prison_number_b"), props=frozenset({"relation"})),
    _link("ASSOCIATE_OF", _P, _P, "pid_family_and_associates.csv", "R13",
          ("prison_number_a", "prison_number_b")),
    _link("PASSES_ITEMS_TO", _P, _P, "graph port", "seed", ("source", "target"),
          props=frozenset({"channel"}), extra=("confidence",)),
    *(
        _link("DEPICTS", _DOC, end, "picture route", "seed", ("picture", "subject"),
              props=frozenset({"shown"}))
        for end in (
            _P, _V, _N, "Organisation", "Establishment", "Device", "Location:wing",
            "Location:yard",
        )
    ),
)  # fmt: skip


def _entity(
    label: str, props: set[str], file: str, recipe: str, key: str,
    *, moment: Moment = "seed", addition: str | None = None,
) -> tuple[Any, ...]:  # fmt: skip
    return (label, frozenset(props), file, recipe, moment, key, addition)


_PERSON = {"family_name", "given_names", "date_of_birth", "aliases"}
_PLACE = {"name", "site_ref"}
_ENDPOINT = {"value_raw", "value_normalised", "endpoint_kind"}
_INCIDENT = {"name", "incident_ref", "category", "item", "occurred_at"}
_ENTITY_ROWS: tuple[tuple[Any, ...], ...] = (
    _entity(_P, {*_PERSON, "prison_number"}, _PRISONERS, "R1", "prison_number",
            addition="R1 must carry aliases, the principal's nickname among them, in a column."),
    _entity(_V, {*_PERSON, "nino"}, _VISITS, "R3", "nino",
            addition="R3 must carry each visitor's date_of_birth and aliases (the coordinator's "
            '"Mo") beside the NINO.'),
    _entity(_N, {*_PERSON, "nino"}, _REPORTS, "R9", "nino", moment="chapter4", addition=_NAMED),
    _entity("Establishment",
            {"name", "establishment_ref", "niu_area", "soct_region", "security_category"},
            _ESTATE, "R11", "establishment_ref"),
    _entity("Location:wing", {*_PLACE, "geometry_ref"}, _ESTATE, "R11", "site_ref"),
    _entity("Location:landing", _PLACE, _ESTATE, "R11", "site_ref"),
    _entity("Location:cell", _PLACE, _ESTATE, "R11", "site_ref"),
    _entity("Location:yard", {*_PLACE, "geometry_ref"}, _ESTATE, "R11", "site_ref"),
    _entity("Location:zone", {*_PLACE, "geometry_ref"}, _ESTATE, "R11", "site_ref",
            addition="R11 must gain the zone kind, a place made of other places."),
    _entity("Location:hall", _PLACE, _ESTATE, "R11", "site_ref",
            addition="R11 must gain the visits hall kind."),
    _entity("Location:place", _PLACE, _ESTATE, "R11", "site_ref",
            addition="R11 must gain the outside place kind, where a report is set away from any "
            "establishment."),
    _entity("Organisation", {"name", "org_ref"}, "pid_soc_nominals.csv", "R12", "org_ref"),
    _entity("Incident:other", _INCIDENT, _INCIDENTS, "R4", "incident_ref"),
    _entity("Incident:throw_over", _INCIDENT, "pid_throwover_log.csv", "R10", "incident_ref",
            addition="R10 must carry each throw-over's name in a column."),
    _entity("Device", {"imei"}, _BATCH_1, "R6", "imei"),
    _entity("Device", {"imei"}, _BATCH_2, "R6", "imei", moment="chapter9"),
    _entity("Endpoint:msisdn", {*_ENDPOINT, "e164"}, _PINS, "R5", "e164"),
    _entity("Endpoint:handle", {*_ENDPOINT, "handle"}, _PINS, "R5", "handle"),
    _entity("Endpoint:imsi", {*_ENDPOINT, "imsi"}, _BATCH_1, "R6", "imsi"),
    _entity("Endpoint:imsi", {*_ENDPOINT, "imsi"}, _BATCH_2, "R6", "imsi", moment="chapter9"),
    _entity("Endpoint:account", _ENDPOINT, _MONEY, "R7", "value_normalised"),
    _entity("Document", {"title", "sent_at", "media_kind", "document_kind"}, _REPORTS, "R9",
            "report_ref", moment="chapter4"),
    _entity("Document", {"title", "media_kind", "object_ref"}, "picture route", "seed",
            "picture"),
)  # fmt: skip


def _clause(rows: Sequence[tuple[Any, ...]], file_at: int, seen: set[str]) -> list[tuple[Any, ...]]:
    """Give the first shape of each file that holds rows of more than one handling the sentence
    that says so, folded into its own addition if it has one."""
    out = []
    for row in rows:
        file, addition = row[file_at], row[-1]
        if file in _COLUMN_FILES and file not in seen:
            seen.add(file)
            addition = (
                f"Brief 2 must make {file} carry classification, originator and owning unit "
                "columns, as the file holds rows of more than one handling."
                if addition is None
                else addition[:-1] + f", and {_COLUMNS_CLAUSE}."
            )
        out.append((*row[:-1], addition))
    return out


def _handling_of(file: str) -> Literal["recipe", "column"]:
    return "column" if file in _COLUMN_FILES else "recipe"


_SEEN_FILES: set[str] = set()
ENTITY_SHAPES: tuple[EntityShape, ...] = tuple(
    EntityShape(
        label,
        props,
        file,
        recipe,
        moment,
        key,
        (key, *sorted(p for p in props if p != key)),
        _handling_of(file),
        add,
    )  # fmt: skip
    for label, props, file, recipe, moment, key, add in _clause(_ENTITY_ROWS, 2, _SEEN_FILES)
)
LOAD_SHAPES: tuple[LoadShape, ...] = tuple(
    LoadShape(
        t,
        src,
        tgt,
        props,
        file,
        recipe,
        moment,
        skey,
        tkey,
        (skey, tkey, *sorted(props), *extra),
        _handling_of(file),
        add,
    )  # fmt: skip
    for t, src, tgt, props, file, recipe, moment, skey, tkey, extra, add in _clause(
        _LINK_ROWS, 4, _SEEN_FILES
    )
)
