"""The Prison Intelligence Dataset's generated files, store writes and pictures, proved without a
store (ADR-120 D4 to D9 and Amendments 9, 10 and 11; stage 5 unit 5b).

`demo_fixtures.pid_files.write_files` serialises what `pid_plan.rows_for` yields, with the columns
the rows do not carry (entity properties under Brief 2's names, the call file's `duration_s`,
`direction` and `sequence`, the seized comms' `kind` and `duration_s`, `report_text` and
`reviewer_initials`), and plants the mess and the two teaching rows. Nothing here opens a store, a
socket or a file outside `tmp_path`; the real components stand in for the real consumers: the
engine's own `dedup_key` and `FieldBinding`, the `msisdn` and `geometry_ref` Knowledge Adapters, the
picture route's `validate_upload_name` and `image_dimensions`, and the composed ontology.

What each group of tests guards:

- **The round trip.** An engine-faithful reader, built from the shapes' columns and Brief 2's
  de-duplication keys, reads every file back. It groups rows by the real `dedup_key`, then by link
  type and ends, counts a distinct row as one occurrence and takes the first and last row's date as
  the interval. At each moment it must reconstruct exactly the plan's entities (type, identifier and
  properties) and links (type, ends, properties, occurrences, interval and, for the row's owner,
  handling). A writer that drops a call row, writes a number it cannot read back, or names a column
  other than the one the recipe binds, loads a different case from the one the demo's figures quote.
- **The mess** (Brief 2 section 3.4): 10,000 distinct calls in each of three international forms of
  an outside number, 40 exact duplicate rows and 40 repeats with a new sequence number, planted at
  recorded positions; every written number normalising, through the real `msisdn`, to the plan's.
- **The teaching rows** (Brief 2 section 5): row 17 of the reports file carries `07700 900 6O3`
  (refused by `msisdn`, with its cause) and row 101 a three-letter `reviewer_initials`.
- **Handling columns** on exactly the mixed files; **places** from coordinates, each resolving
  through the real transform, every throw-over within the jitter of its yard's point.
- **Pictures** (Amendment 9 decision 8): valid, 256 by 256, small, named acceptably, reproducible,
  all different, read from no file, and blind to the plan's hotspots.
- **The store writes** (`pid_writes`): ids, datasets, handling, provenance, the intervals
  `link_instants` gives, and what is left to the picture route; and the Amendment 7 circle's
  links and end nodes (`circle_links`, `circle_writes`), which the live access test loads alone
  into its three planted-rule stores.
- **The manifest and the script**: rows, bytes and SHA-256 per file, no timestamps, two runs
  byte-identical, and the script's refusal of a path inside the repository.

Limits, stated: the demo profile's file is written once per module (about 100,000 call
rows), and the round trip reads it with the engine's `dedup_key` (a few tens of seconds);
`link_instants` and the plan's `rows_for` are the plan's own and are proved in `test_pid_plan.py`,
so this file takes them as the reference and proves the files and writes against them.
Byte-identical means on one
interpreter and one `zlib` build, which the manifest records.
"""

from __future__ import annotations

import ast
import builtins
import csv
import dataclasses
import hashlib
import importlib
import io
import json
import os
import re
import struct
import sys
import types
import zlib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from scripts import write_pid_files
from services.api.entity_pictures import PICTURE_TYPES
from services.api.ingest_sources import UploadRefused, validate_upload_name
from services.ingest.engine import dedup_key

from demo_fixtures import pid_files, pid_pictures, pid_plan, pid_writes
from demo_fixtures.datasets import PID, PID_SCALE
from geo.image_dimensions import image_dimensions
from knowledge_adapters import REGISTRY
from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.imei import imei
from knowledge_adapters.imsi import imsi
from knowledge_adapters.msisdn import msisdn
from ontology.packs import load_deployment_ontology
from ontology.validation import validate_edge_endpoints, validate_properties
from schemas.domain import ProvenanceState
from schemas.ingest import FieldBinding

# --- What the specification states, written out here so a constant cannot drift with its data ----

MOMENTS = ("seed", "chapter4", "chapter9")
RANK = {moment: rank for rank, moment in enumerate(MOMENTS)}
HANDLING = (
    "classification", "handling_code", "action_code", "sanitisation_code", "originator",
    "owning_unit",
)  # fmt: skip
PSEUDO = frozenset({"graph port", "picture route"})
CALLS = "pid_pin_calls.csv"
REPORTS = "pid_intel_reports.csv"
REPORT_INCIDENTS = "pid_report_incidents.csv"
ESTATE = "pid_establishment_plan.csv"
THROW_OVERS = "pid_throwover_log.csv"
FAMILY = "pid_family_and_associates.csv"
BATCH_1 = "pid_seized_comms_batch1.csv"
BATCH_2 = "pid_seized_comms_batch2.csv"
#: The files a profile has no rows for, and so no file (Amendment 12 decision 5).
ABSENT: dict[str, set[str]] = {
    "demo": set(),
    "scale": {
        "pid_pin_calls.csv", "pid_intel_reports.csv", "pid_report_incidents.csv",
        "pid_seized_comms_batch1.csv", "pid_seized_comms_batch2.csv", "pid_number_owners.csv",
        "pid_throwover_log.csv",
    },
}  # fmt: skip
CALL_ROWS = pid_plan.CALL_ROWS  # about 100,000 (ADR-120 Amendment 17)
FORM_COUNT = 10_000  # distinct calls in each of the three international forms
EXACT_DUPLICATES = 40
SEQUENCE_DUPLICATES = 40
TEACHING_ROW = 17
INITIALS_ROW = 101
CORRECTED_NUMBER = "07700 900603"
LAST_CALL_INSTANT = "2026-04-30T23:59:59+00:00"
#: The throw-over jitter: the specification allows 50 millionths of a degree.
JITTER_DEGREES = 50e-6
CREATED = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
PICTURE_KINDS = ("person", "establishment", "wing", "yard", "handset", "group")
#: The columns each of Brief 2's recipes names that the files must carry (R1 to R13, transcribed
#: from `02_INGEST_STUDIO_JOBS_BRIEF.md` section 4). R1's `wing_ref` and `cell_ref` are not here:
#: R1's split addition moved them to the cell-stay file (Amendment 9 decision 1, Amendment 12
#: decision 4). `recovered` (R10) and `role` (R12) are kept, empty. The links' own columns are
#: `test_pid_plan.py`'s.
BRIEF_2_ENTITY_COLUMNS: dict[str, frozenset[str]] = {
    "pid_nomis_prisoners.csv": frozenset(
        "nomis_id family_name given_names date_of_birth establishment_ref custody_from "
        "custody_to".split()
    ),
    "pid_nomis_visits.csv": frozenset(
        "visit_ref visit_date visitor_nino visitor_family_name visitor_given_names channel "
        "nomis_id".split()
    ),
    "pid_nomis_incidents.csv": frozenset(
        "incident_ref category occurred_at area_ref item nomis_id role".split()
    ),
    CALLS: frozenset(
        "pin_account nomis_id called_number call_start duration_s direction sequence".split()
    ),
    BATCH_1: frozenset(
        "imei imsi other_number kind occurred_at duration_s found_with_nomis_id found_on".split()
    ),
    BATCH_2: frozenset(
        "imei imsi other_number kind occurred_at duration_s found_with_nomis_id found_on".split()
    ),
    "pid_prisoner_money.csv": frozenset(
        "transfer_id transferred_at payer_account payer_nino payer_family_name payer_given_names "
        "payee_nomis_id payee_account amount transaction_type".split()
    ),
    REPORTS: frozenset(
        "report_ref submitted_at area_ref category subject_1 subject_1_role subject_2 "
        "subject_2_role subject_3 subject_3_role subject_1_nino subject_2_nino subject_3_nino "
        "report_text reviewer_initials phone_mentioned area_ref_2 area_ref_3".split()
    ),
    THROW_OVERS: frozenset("incident_ref occurred_at yard_ref item_type recovered".split()),
    ESTATE: frozenset(
        "place_ref place_kind name parent_ref parent_kind lon lat adjoins_ref used_by_ref "
        "niu_area soct_region security_category".split()
    ),
    "pid_soc_nominals.csv": frozenset("nomis_id group_ref group_name role".split()),
    "pid_family_and_associates.csv": frozenset("nomis_id_a nomis_id_b relation kind".split()),
    "pid_codefendants.csv": frozenset("case_ref nomis_id_a nomis_id_b".split()),
    "pid_nomis_cell_shares.csv": frozenset("nomis_id_a nomis_id_b cell_ref week_start".split()),
    "pid_conflicts.csv": frozenset("nomis_id_a nomis_id_b reason first_seen".split()),
}  # fmt: skip

#: The two names the generated output must never carry: the older synthetic prison fixture's and the
#: film's. Built from code points so that this file does not itself contain either.
FORBIDDEN = tuple(
    bytes(codes).decode()
    for codes in ((104, 109, 112), (104, 111, 108, 108, 121, 119, 111, 111, 100))
)


def _expected_name(profile: str, file: str) -> str:
    if profile == "scale":
        return f"scale_{file}"
    return f"incoming/{file}" if file == BATCH_2 else file


def _all_files() -> list[str]:
    return sorted({sh.file for sh in pid_plan.LOAD_SHAPES} - PSEUDO)


@dataclasses.dataclass
class Written:
    plan: Any
    out: Path
    report: Any

    def path(self, file: str) -> Path:
        return self.out / _expected_name(self.plan.profile, file)

    def present(self) -> list[str]:
        return [f for f in _all_files() if self.path(f).exists()]

    def rows(self, file: str) -> Iterator[dict[str, str]]:
        return read_rows(self.path(file))


def read_rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def _header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


@pytest.fixture(scope="module")
def demo() -> Any:
    return pid_plan.build_plan("demo")


@pytest.fixture(scope="module")
def scale() -> Any:
    return pid_plan.build_plan("scale")


@pytest.fixture(scope="module")
def demo_out(demo: Any, tmp_path_factory: pytest.TempPathFactory) -> Written:
    out = tmp_path_factory.mktemp("pid_demo")
    return Written(demo, out, pid_files.write_files(demo, out))


@pytest.fixture(scope="module")
def demo_again(demo: Any, tmp_path_factory: pytest.TempPathFactory) -> Written:
    out = tmp_path_factory.mktemp("pid_demo_again")
    return Written(demo, out, pid_files.write_files(demo, out))


@pytest.fixture(scope="module")
def scale_out(scale: Any, tmp_path_factory: pytest.TempPathFactory) -> Written:
    out = tmp_path_factory.mktemp("pid_scale")
    return Written(scale, out, pid_files.write_files(scale, out))


# --- The engine-faithful reader ----------------------------------------------------------------


def _key(field: str, transform: str | None = None) -> FieldBinding:
    return FieldBinding(field=field, transform=transform)


#: Each file's de-duplication key, as Brief 2 gives it where it does (R1, R2's sorted pair, R3, R4,
#: R5, R7 and R10) and as the files' own columns make it where it is silent (R6, R8, R9, R11, R12,
#: R13, the cell stays, the conflicts, the number owners and the report incidents).
DEDUP: dict[str, list[FieldBinding]] = {
    "pid_nomis_prisoners.csv": [_key("nomis_id"), _key("establishment_ref"),
                                _key("custody_from", "datetime")],
    "pid_nomis_cell_stays.csv": [_key("nomis_id"), _key("cell_ref"), _key("start", "datetime")],
    "pid_nomis_cell_shares.csv": [_key("nomis_id_a"), _key("nomis_id_b"),
                                  _key("week_start", "datetime")],
    "pid_nomis_visits.csv": [_key("visit_ref")],
    "pid_nomis_incidents.csv": [_key("incident_ref"), _key("nomis_id"), _key("role")],
    CALLS: [_key("pin_account"), _key("called_number", "msisdn"), _key("call_start", "datetime"),
            _key("duration_s")],
    BATCH_1: [_key("imsi"), _key("other_number", "msisdn"), _key("occurred_at", "datetime")],
    BATCH_2: [_key("imsi"), _key("other_number", "msisdn"), _key("occurred_at", "datetime")],
    "pid_prisoner_money.csv": [_key("transfer_id")],
    "pid_codefendants.csv": [_key("case_ref"), _key("nomis_id_a"), _key("nomis_id_b")],
    "pid_conflicts.csv": [_key("nomis_id_a"), _key("nomis_id_b"), _key("first_seen", "datetime")],
    REPORTS: [_key("report_ref")],
    REPORT_INCIDENTS: [_key("incident_ref"), _key("report_ref")],
    THROW_OVERS: [_key("incident_ref")],
    ESTATE: [_key("place_ref")],
    "pid_soc_nominals.csv": [_key("nomis_id"), _key("group_ref")],
    "pid_family_and_associates.csv": [_key("nomis_id_a"), _key("nomis_id_b"), _key("kind")],
    "pid_number_owners.csv": [_key("owner_ref"), _key("number")],
}  # fmt: skip

#: The two date columns of a span link.
SPANS = {"HELD_AT": ("custody_from", "custody_to"), "PRESENT_AT": ("start", "end")}
PRISON_NUMBER = re.compile(r"[A-Z]\d{4}[A-Z]{2}")
NINO = re.compile(r"[A-Z]{2}\d{6}[A-D]")
PLACE_LABELS = {
    "establishment": "Establishment", "wing": "Location:wing", "landing": "Location:landing",
    "cell": "Location:cell", "yard": "Location:yard", "hall": "Location:hall",
    "zone": "Location:zone", "place": "Location:place",
}  # fmt: skip
#: The files whose rows are an entity's own (the estate's places, the reports): the row's handling
#: is that entity's. Every other file's row is a link's.
ENTITY_OWNED = frozenset({ESTATE, REPORTS})


class Rejected(Exception):
    """A row the engine would reject: nothing of it is written."""


def _normalise(cell: str) -> str:
    try:
        return msisdn(cell)
    except NormalisationError as exc:
        raise Rejected(f"msisdn: {exc.reason}") from exc


def _canonical(adapter: Callable[[str], str], cell: str) -> str:
    try:
        return adapter(cell)
    except NormalisationError as exc:
        raise Rejected(f"{exc.adapter}: {exc.reason}") from exc


def _ident(label: str, cell: str) -> str:
    """A link end's identity as the recipe's Knowledge Adapter makes it: an outside number through
    `msisdn`, a handset through `imei` and a SIM through `imsi` (R6 binds both)."""
    if label == "Endpoint:msisdn":
        return _normalise(cell)
    if label == "Device":
        return _canonical(imei, cell)
    if label == "Endpoint:imsi":
        return _canonical(imsi, cell)
    return cell


def _endpoint(kind: str, ident: str, *, raw: str | None = None) -> dict[str, str]:
    return {
        "value_raw": ident if raw is None else raw,
        "value_normalised": ident,
        "endpoint_kind": kind,
        **({"e164": ident} if kind == "msisdn" else {kind: ident} if kind != "account" else {}),
    }


Entities = list[tuple[str, str, dict[str, str]]]


def _prisoners(row: dict[str, str]) -> Entities:
    props = {
        "prison_number": row["nomis_id"], "family_name": row["family_name"],
        "given_names": row["given_names"], "date_of_birth": row["date_of_birth"],
        "aliases": row["aliases"],
    }  # fmt: skip
    return [("Person:prisoner", row["nomis_id"], props)]


def _visits(row: dict[str, str]) -> Entities:
    nino = row["visitor_nino"]
    props = {
        "nino": nino, "family_name": row["visitor_family_name"],
        "given_names": row["visitor_given_names"],
        "date_of_birth": row["visitor_date_of_birth"], "aliases": row["visitor_aliases"],
    }  # fmt: skip
    return [("Person:visitor", nino, props)]


def _incidents(row: dict[str, str]) -> Entities:
    props = {
        "incident_ref": row["incident_ref"], "name": row["name"], "category": row["category"],
        "item": row["item"], "occurred_at": row["occurred_at"],
    }  # fmt: skip
    return [("Incident:other", row["incident_ref"], props)]


def _throw_overs(row: dict[str, str]) -> Entities:
    props = {
        "incident_ref": row["incident_ref"], "name": row["name"], "category": "throw_over",
        "item": row["item_type"], "occurred_at": row["occurred_at"],
    }  # fmt: skip
    return [("Incident:throw_over", row["incident_ref"], props)]


def _calls(row: dict[str, str]) -> Entities:
    pin, written = row["pin_account"], row["called_number"]
    number = _normalise(written)
    return [
        ("Endpoint:handle", pin, _endpoint("handle", pin)),
        ("Endpoint:msisdn", number, _endpoint("msisdn", number, raw=written)),
    ]


def _seized(row: dict[str, str]) -> Entities:
    handset, sim = _ident("Device", row["imei"]), _ident("Endpoint:imsi", row["imsi"])
    other, written = _normalise(row["other_number"]), row["other_number"]
    return [
        ("Device", handset, {"imei": handset}),
        ("Endpoint:imsi", sim, _endpoint("imsi", sim)),
        ("Endpoint:msisdn", other, _endpoint("msisdn", other, raw=written)),
    ]


def _owners(row: dict[str, str]) -> Entities:
    number = _normalise(row["number"])
    return [("Endpoint:msisdn", number, _endpoint("msisdn", number, raw=row["number"]))]


def _money(row: dict[str, str]) -> Entities:
    return [
        ("Endpoint:account", row[column], _endpoint("account", row[column]))
        for column in ("payer_account", "payee_account")
    ]


def _groups(row: dict[str, str]) -> Entities:
    props = {"org_ref": row["group_ref"], "name": row["group_name"]}
    return [("Organisation", row["group_ref"], props)]


def _reports(row: dict[str, str]) -> Entities:
    if row["phone_mentioned"]:
        _normalise(row["phone_mentioned"])
    out: Entities = [
        (
            "Document",
            row["report_ref"],
            {
                "title": row["title"], "sent_at": row["submitted_at"], "media_kind": "text",
                "document_kind": row["category"],
            },
        )
    ]
    for i in (1, 2, 3):
        assert not NINO.fullmatch(row[f"subject_{i}"]), "subject_N holds prison numbers only"
        nino = row[f"subject_{i}_nino"]
        if nino:
            assert NINO.fullmatch(nino), nino
            props = {
                "nino": nino, "family_name": row[f"subject_{i}_family_name"],
                "given_names": row[f"subject_{i}_given_names"],
                "date_of_birth": row[f"subject_{i}_date_of_birth"],
            }  # fmt: skip
            out.append(("Person:named", nino, props))
    return out


def _estate(row: dict[str, str]) -> Entities:
    label = PLACE_LABELS[row["place_kind"]]
    if label == "Establishment":
        props = {
            "establishment_ref": row["place_ref"], "name": row["name"],
            "niu_area": row["niu_area"], "soct_region": row["soct_region"],
            "security_category": row["security_category"],
        }  # fmt: skip
    else:
        props = {"site_ref": row["place_ref"], "name": row["name"]}
    return [(label, row["place_ref"], props)]


ENTITY_ROWS: dict[str, Callable[[dict[str, str]], Entities]] = {
    "pid_nomis_prisoners.csv": _prisoners,
    "pid_nomis_visits.csv": _visits,
    "pid_nomis_incidents.csv": _incidents,
    THROW_OVERS: _throw_overs,
    CALLS: _calls,
    BATCH_1: _seized,
    BATCH_2: _seized,
    "pid_number_owners.csv": _owners,
    "pid_prisoner_money.csv": _money,
    "pid_soc_nominals.csv": _groups,
    REPORTS: _reports,
    ESTATE: _estate,
}


def _form_of(written: str) -> str:
    if written.startswith("0044 "):
        return "zero_zero_44"
    if written.startswith("+44 "):
        return "plus_44"
    if re.fullmatch(r"44\d{10}", written):
        return "bare_44"
    return "national" if written.startswith("0") else "other"


@dataclasses.dataclass
class LinkRecord:
    file: str
    moment: str
    occurrences: int = 0
    instants: list[datetime] = dataclasses.field(default_factory=list)
    span: tuple[datetime, datetime | None] | None = None
    props: dict[str, str] = dataclasses.field(default_factory=dict)
    handlings: set[tuple[str, ...]] = dataclasses.field(default_factory=set)


@dataclasses.dataclass
class EntityRecord:
    file: str
    moment: str
    props: dict[str, str]
    handling: tuple[str, ...] | None


@dataclasses.dataclass
class FileStats:
    rows: int = 0
    distinct: int = 0
    duplicates: list[tuple[int, int]] = dataclasses.field(default_factory=list)
    rejected: list[tuple[int, str]] = dataclasses.field(default_factory=list)
    forms: Counter[str] = dataclasses.field(default_factory=Counter)


_ENTITY_MOMENT = {(sh.file, sh.entity_type): sh.moment for sh in pid_plan.ENTITY_SHAPES}
LinkKey = tuple[str, tuple[str, str], tuple[str, str]]


class Reader:
    """Reads the files as the Studio's engine would count them. It takes only the shapes' columns,
    each file's de-duplication key (through the real `dedup_key`) and the entity cells Brief 2
    names, and writes into dictionaries. A row that cannot be read is rejected whole."""

    def __init__(self) -> None:
        self.entities: dict[tuple[str, str], EntityRecord] = {}
        self.links: dict[LinkKey, LinkRecord] = {}
        self.kinds: dict[str, str] = {}
        self.stats: dict[str, FileStats] = {}
        self.conflicts: list[str] = []
        #: The first written form of each outside number in each file that names one.
        self.first_raw: dict[tuple[str, str], str] = {}
        self._pending_raw: list[tuple[str, str]] = []

    def preload_places(self, rows: Iterable[dict[str, str]]) -> None:
        for row in rows:
            self.kinds[row["place_ref"]] = PLACE_LABELS[row["place_kind"]]

    def _kind_ok(self, label: str, cell: str) -> bool:
        if label.startswith("Location:") or label == "Establishment":
            return self.kinds.get(cell) == label
        if label == "Person:prisoner":
            return PRISON_NUMBER.fullmatch(cell) is not None
        if label == "Person:named":
            return NINO.fullmatch(cell) is not None
        return True

    def _choose(self, shapes: list[Any], source: str, target: str) -> Any:
        if len(shapes) == 1:
            return shapes[0]
        for shape in shapes:
            if self._kind_ok(shape.source_type, source) and self._kind_ok(
                shape.target_type, target
            ):
                return shape
        raise Rejected(f"no shape for {source!r} and {target!r}")

    def read(
        self,
        file: str,
        rows: Iterable[dict[str, str]],
        *,
        repair: Callable[[str, int, dict[str, str]], dict[str, str]] | None = None,
    ) -> None:
        stats = self.stats.setdefault(file, FileStats())
        groups: dict[tuple[str, str, str], list[Any]] = {}
        for shape in pid_plan.LOAD_SHAPES:
            if shape.file == file:
                key = (shape.link_type, shape.source_key, shape.target_key)
                groups.setdefault(key, []).append(shape)
        seen: dict[str, int] = {}
        for number, row in enumerate(rows, start=1):
            stats.rows += 1
            if repair is not None:
                row = repair(file, number, row)
            digest = dedup_key(row, DEDUP[file])
            if digest is not None:
                if digest in seen:
                    stats.duplicates.append((number, seen[digest]))
                    continue
                seen[digest] = number
            self._pending_raw = []
            try:
                entities = ENTITY_ROWS[file](row) if file in ENTITY_ROWS else []
                links = self._links(groups, row)
            except Rejected as rejected:
                stats.rejected.append((number, str(rejected)))
                continue
            for e164, written in self._pending_raw:
                self.first_raw.setdefault((file, e164), written)
            for label, ident, props in entities:
                if label == "Endpoint:msisdn":
                    self.first_raw.setdefault((file, ident), props["value_raw"])
            stats.distinct += 1
            if file == CALLS:
                stats.forms[_form_of(row["called_number"])] += 1
            self._commit(file, row, entities, links)

    def _links(
        self, groups: dict[tuple[str, str, str], list[Any]], row: dict[str, str]
    ) -> list[tuple[Any, LinkKey]]:
        out = []
        for (link_type, source_key, target_key), shapes in groups.items():
            source, target = row.get(source_key, ""), row.get(target_key, "")
            if not source or not target:
                continue
            if "kind" in row and shapes[0].file == FAMILY and row["kind"] != link_type:
                continue  # R13 chooses its edge with a `when` on `kind`
            shape = self._choose(shapes, source, target)
            ends = []
            for label, cell in ((shape.source_type, source), (shape.target_type, target)):
                ends.append((label, _ident(label, cell)))
                if label == "Endpoint:msisdn":
                    self._pending_raw.append((ends[-1][1], cell))
            out.append((shape, (shape.link_type, ends[0], ends[1])))
        return out

    def _commit(
        self, file: str, row: dict[str, str], entities: Entities, links: list[tuple[Any, LinkKey]]
    ) -> None:
        cells = tuple(row.get(c, "") for c in HANDLING) if HANDLING[0] in row else None
        for label, ident, props in entities:
            props = {k: v for k, v in props.items() if v != ""}
            held = self.entities.get((label, ident))
            if held is None:
                self.entities[(label, ident)] = EntityRecord(
                    file, _ENTITY_MOMENT.get((file, label), "seed"), props, cells
                )
                continue
            same = {k: v for k, v in props.items() if k != "value_raw"} == {
                k: v for k, v in held.props.items() if k != "value_raw"
            }
            if not same:
                self.conflicts.append(f"{file}: {label} {ident} is written two ways")
        for shape, key in links:
            record = self.links.setdefault(key, LinkRecord(file, shape.moment))
            record.occurrences += 1
            span = SPANS.get(shape.link_type)
            columns = [c for c in shape.columns if c in pid_plan.DATE_COLUMNS]
            if span is not None:
                end = row[span[1]]
                record.span = (
                    datetime.fromisoformat(row[span[0]]),
                    datetime.fromisoformat(end) if end else None,
                )
            elif columns and row.get(columns[0], ""):
                record.instants.append(datetime.fromisoformat(row[columns[0]]))
            props = {
                name: row[pid_plan.property_column(shape, name)] for name in shape.properties
            }
            if not record.props:
                record.props = props
            elif record.props != props:
                self.conflicts.append(f"{file}: {key} carries two sets of properties")
            if cells is not None:
                record.handlings.add(cells)


def _read_all(
    written: Written,
    *,
    repair: Callable[[str, int, dict[str, str]], dict[str, str]] | None = None,
) -> Reader:
    reader = Reader()
    reader.preload_places(written.rows(ESTATE))
    for file in sorted(written.present(), key=lambda f: f != ESTATE):
        reader.read(file, written.rows(file), repair=repair)
    return reader


def _correct_the_teaching_cell(
    file: str, number: int, row: dict[str, str]
) -> dict[str, str]:
    """What the engineer does after the dry run: the source cell is fixed and the file run again."""
    if file == REPORTS and row["phone_mentioned"] == pid_plan.PID_TEACHING_BAD_NUMBER:
        return {**row, "phone_mentioned": CORRECTED_NUMBER}
    return row


@pytest.fixture(scope="module")
def demo_read(demo_out: Written) -> Reader:
    return _read_all(demo_out, repair=_correct_the_teaching_cell)


@pytest.fixture(scope="module")
def scale_read(scale_out: Written) -> Reader:
    return _read_all(scale_out)


# --- What the plan holds, as the reader reconstructs it -----------------------------------------


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list | tuple):
        return "|".join(_text(v) for v in value)
    return str(value)


_IDENTIFIERS = (
    "prison_number", "nino", "site_ref", "establishment_ref", "org_ref", "incident_ref", "imei",
    "value_normalised",
)  # fmt: skip


def _identifier(entity: Any) -> str:
    for name in _IDENTIFIERS:
        if name in entity.properties:
            return str(entity.properties[name])
    return str(entity.key)


_IR = re.compile(r"IR \d+")


def _ir(plan: Any, key: str) -> str:
    """A report's reference as its text shows it (`IR 0263`): the files' `report_ref`."""
    found = _IR.match(plan.report_texts[key])
    assert found is not None, key
    return found.group()


def _ident_of(plan: Any, entity: Any) -> str:
    return _ir(plan, entity.key) if entity.key in plan.report_texts else _identifier(entity)


def _label(entity: Any, visitors: frozenset[str]) -> str:
    kind = entity.entity_type
    if kind == "Endpoint":
        return f"Endpoint:{entity.properties['endpoint_kind']}"
    if kind == "Incident":
        return (
            "Incident:throw_over" if entity.properties["category"] == "throw_over"
            else "Incident:other"
        )  # fmt: skip
    if kind == "Location":
        return f"Location:{str(entity.properties['site_ref']).split(':')[-2]}"
    if kind == "Person":
        if "prison_number" in entity.properties:
            return "Person:prisoner"
        return "Person:visitor" if entity.key in visitors else "Person:named"
    return str(kind)


def _is_picture(entity: Any) -> bool:
    return entity.entity_type == "Document" and entity.properties.get("media_kind") == "image"


def _interval(plan: Any, link: Any) -> tuple[datetime, datetime | None] | None:
    """A link's interval as the files and the store writes hold it: a span from its first date's
    start to its last date's end (open when it has no last), anything else from its first to its
    last instant, `link_instants` being the one function that dates an occurrence."""
    if link.link_type in ("HELD_AT", "PRESENT_AT", "PASSES_ITEMS_TO"):
        if link.first_seen is None:
            return None
        last = None if link.last_seen is None else pid_plan.end_of(link.last_seen)
        return (pid_plan.start_of(link.first_seen), last)
    instants = pid_plan.link_instants(plan, link)
    return (min(instants), max(instants)) if instants else None


def _expected(
    plan: Any, moment: str, files: frozenset[str] | None
) -> tuple[dict[tuple[str, str], dict[str, str]], dict[LinkKey, dict[str, Any]]]:
    visitors = frozenset(lk.source for lk in plan.links if lk.link_type == "VISITED")
    label = {e.key: _label(e, visitors) for e in plan.entities}
    ident = {e.key: _ident_of(plan, e) for e in plan.entities}
    # What a Studio load stores is what `pid_writes` writes (adapters applied, ids derived), so the
    # expected entities are its nodes, matched to the plan's by derived id; their moment and kind
    # (and the reports' IR references) are the plan's.
    dataset = PID.id if plan.profile == "demo" else PID_SCALE.id
    stored = {n.id: n for n in _writes(plan, moment, dataset)[0]}
    for e in plan.entities:
        node = stored.get(pid_plan.node_id(e.key))
        if node is not None and label[e.key] in ("Device", "Endpoint:imsi"):
            ident[e.key] = _identifier(types.SimpleNamespace(key=e.key, properties=node.properties))
    entities = {
        (label[e.key], ident[e.key]): {
            k: _text(v) for k, v in stored[pid_plan.node_id(e.key)].properties.items()
        }
        for e in plan.entities
        if pid_plan.node_id(e.key) in stored
    }
    triples = {
        (sh.link_type, sh.source_type, sh.target_type)
        for sh in pid_plan.LOAD_SHAPES
        if sh.file not in PSEUDO and (files is None or sh.file in files)
    }
    carried = set(pid_plan.carrying_links(plan))
    links: dict[LinkKey, dict[str, Any]] = {}
    for link in pid_plan.links_at(plan, moment, secret_cleared=True):
        triple = (link.link_type, label[link.source], label[link.target])
        if triple not in triples:
            continue
        key = (link.link_type, (label[link.source], ident[link.source]),
               (label[link.target], ident[link.target]))  # fmt: skip
        assert key not in links, f"two plan links of one type and pair: {key}"
        links[key] = {
            "occurrences": link.occurrences,
            "interval": _interval(plan, link),
            "props": {k: _text(v) for k, v in link.properties.items()},
            "handling": tuple(getattr(link.handling, c) or "" for c in HANDLING),
            "carried": link.key in carried,
        }
    return entities, links


def _compare(
    read: Reader, plan: Any, moment: str, *, files: frozenset[str] | None = None
) -> list[str]:
    """Every difference between what the reader reconstructs from the files, as of a moment, and
    what the plan holds. `files` restricts the comparison to those files' links."""
    expected_entities, expected_links = _expected(plan, moment, files)
    mixed = pid_plan.mixed_files(plan)
    problems: list[str] = []
    if files is None:
        got_entities = {
            key: rec for key, rec in read.entities.items() if RANK[rec.moment] <= RANK[moment]
        }
        for key in sorted(got_entities.keys() - expected_entities.keys()):
            problems.append(f"entity read but not in the plan: {key}")
        for key in sorted(expected_entities.keys() - got_entities.keys()):
            problems.append(f"entity in the plan but not read: {key}")
        for key in sorted(got_entities.keys() & expected_entities.keys()):
            if got_entities[key].props != expected_entities[key]:
                got, want = got_entities[key].props, expected_entities[key]
                problems.append(f"entity {key}: {got} != {want}")
    got_links = {
        key: rec
        for key, rec in read.links.items()
        if RANK[rec.moment] <= RANK[moment] and (files is None or rec.file in files)
    }
    for key in sorted(got_links.keys() - expected_links.keys()):
        problems.append(f"link read but not in the plan: {key}")
    for key in sorted(expected_links.keys() - got_links.keys()):
        problems.append(f"link in the plan but not read: {key}")
    for key in sorted(got_links.keys() & expected_links.keys()):
        rec, want = got_links[key], expected_links[key]
        interval = rec.span if rec.span is not None else (
            (min(rec.instants), max(rec.instants)) if rec.instants else None
        )
        if rec.occurrences != want["occurrences"]:
            wanted = want["occurrences"]
            problems.append(f"link {key}: {rec.occurrences} occurrences, want {wanted}")
        if interval != want["interval"]:
            problems.append(f"link {key}: interval {interval}, wants {want['interval']}")
        if rec.props != want["props"]:
            problems.append(f"link {key}: properties {rec.props}, wants {want['props']}")
        if rec.file in mixed and rec.file not in ENTITY_OWNED and not want["carried"]:
            if rec.handlings != {want["handling"]}:
                problems.append(f"link {key}: handling {rec.handlings}, wants {want['handling']}")
    if files is None:
        for key, rec in got_links.items():
            for end in key[1:]:
                if end not in read.entities:
                    problems.append(f"link {key} ends at {end}, which no row writes")
        problems += _owner_handling_problems(read, plan, moment)
        problems += read.conflicts
    return problems


def _owner_handling_problems(read: Reader, plan: Any, moment: str) -> list[str]:
    """The estate's places and the reports are rows of an entity's own: the row's handling is that
    entity's, for every one that is read."""
    visitors = frozenset(lk.source for lk in plan.links if lk.link_type == "VISITED")
    out = []
    for e in plan.entities:
        label = _label(e, visitors)
        owned = label.startswith(("Location:", "Establishment")) or label == "Document"
        if not owned or _is_picture(e) or RANK[pid_plan.entity_moment(plan, e.key)] > RANK[moment]:
            continue
        got = read.entities.get((label, _ident_of(plan, e)))
        want = tuple(getattr(e.handling, c) or "" for c in HANDLING)
        if got is not None and got.handling is not None and got.handling != want:
            out.append(f"entity {e.key}: handling {got.handling}, wants {want}")
    return out


# --- The round trip ----------------------------------------------------------------------------


def test_reading_every_file_reconstructs_the_demo_plan_at_each_moment(
    demo: Any, demo_read: Reader
) -> None:
    for moment in MOMENTS:
        problems = _compare(demo_read, demo, moment)
        assert problems == [], f"{moment}: {len(problems)} problems, first: {problems[:5]}"
    assert all(not s.rejected for s in demo_read.stats.values()), {
        f: s.rejected for f, s in demo_read.stats.items() if s.rejected
    }
    # The reader read a file for every shape the demo has, the call file's 100,000 rows included.
    assert set(demo_read.stats) == set(_all_files())
    assert demo_read.stats[CALLS].distinct == CALL_ROWS


def test_reading_every_file_reconstructs_the_scale_plan(scale: Any, scale_read: Reader) -> None:
    problems = _compare(scale_read, scale, "seed")
    assert problems == [], f"{len(problems)} problems, first: {problems[:5]}"
    assert len(scale_read.links) == 30_000
    assert all(not s.rejected for s in scale_read.stats.values())


def test_the_round_trip_goes_red_for_one_call_row_dropped(
    demo: Any, demo_out: Written, demo_read: Reader
) -> None:
    """The control: the comparison, restricted to the call file, is clean for the real file. Then a
    reader is fed the same file with one distinct call row left out, and it sees both links the row
    counts once (the call link and the prisoner's `USES` of his PIN account that rides on it)."""
    only = frozenset({CALLS})
    assert _compare(demo_read, demo, "seed", files=only) == []
    dropped = pid_plan.CALL_ROWS // 8  # a row well inside the file, whatever its volume
    reader = Reader()
    rows = (r for n, r in enumerate(demo_out.rows(CALLS), start=1) if n != dropped)
    reader.read(CALLS, rows)
    problems = _compare(reader, demo, "seed", files=only)
    assert len(problems) >= 2 and all("occurrences" in p for p in problems), problems[:4]


def test_a_malformed_cell_rejects_its_row_whole_with_its_cause(
    demo: Any, demo_out: Written
) -> None:
    """The teaching row, read as the dry run reads it: the engine rejects the row, names the
    adapter's cause, and writes nothing of it (not the report, not its other mentions)."""
    reader = Reader()
    reader.preload_places(demo_out.rows(ESTATE))
    reader.read(REPORTS, demo_out.rows(REPORTS))
    ((number, cause),) = reader.stats[REPORTS].rejected
    assert number == TEACHING_ROW
    assert "msisdn" in cause and "letters" in cause
    teaching = _ir(demo, pid_plan.PID_TEACHING_REPORT)
    assert ("Document", teaching) not in reader.entities
    assert not any(key[2] == ("Document", teaching) for key in reader.links)
    # And repaired, the same file reads whole: the one link the plan holds is there.
    repaired = Reader()
    repaired.preload_places(demo_out.rows(ESTATE))
    repaired.read(REPORTS, demo_out.rows(REPORTS), repair=_correct_the_teaching_cell)
    assert not repaired.stats[REPORTS].rejected
    key = (
        "MENTIONED_IN",
        ("Endpoint:msisdn", pid_plan.PID_TEACHING_NUMBER),
        ("Document", teaching),
    )
    assert repaired.links[key].occurrences == 1


# --- The files: names, columns and what they hold ------------------------------------------------


def test_every_shape_has_a_file_and_the_chapter_9_batch_is_in_incoming(
    demo_out: Written, scale_out: Written
) -> None:
    out = demo_out.out
    csvs = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.csv"))
    assert csvs == sorted(_expected_name("demo", f) for f in _all_files())
    assert "incoming/pid_seized_comms_batch2.csv" in csvs
    assert not (out / BATCH_2).exists()
    # The scale profile's files carry the prefix, and a shape with no rows has no file: the list is
    # pinned (Amendment 12 decision 5), and is what the plan's rows say.
    scale_csvs = sorted(
        p.relative_to(scale_out.out).as_posix() for p in scale_out.out.rglob("*.csv")
    )
    with_rows = [
        f for f in _all_files() if next(iter(pid_plan.rows_for(scale_out.plan, f)), None)
    ]
    assert scale_csvs == sorted(_expected_name("scale", f) for f in with_rows)
    assert all(name.startswith("scale_") for name in scale_csvs)
    for written in (demo_out, scale_out):
        absent = set(_all_files()) - set(written.present())
        assert absent == ABSENT[written.plan.profile], absent
    assert not (scale_out.out / "pictures").exists()
    assert (demo_out.out / "pictures").is_dir()


#: Brief 2's column for each property of an entity, transcribed (R1, R3, R9, R10, R11, R12): the
#: table the entity shapes' `names` must agree with. `None`: a value the file holds in no column of
#: its own (a literal, an endpoint's normalised forms, an outsider's names, which fill
#: `subject_1..3_*` by position). A property not listed keeps its own name.
ENTITY_COLUMN_NAMES: dict[tuple[str, str], dict[str, str | None]] = {
    ("pid_nomis_prisoners.csv", "Person:prisoner"): {"prison_number": "nomis_id"},
    ("pid_nomis_visits.csv", "Person:visitor"): {
        "nino": "visitor_nino", "family_name": "visitor_family_name",
        "given_names": "visitor_given_names", "date_of_birth": "visitor_date_of_birth",
        "aliases": "visitor_aliases",
    },
    (REPORTS, "Document"): {"sent_at": "submitted_at", "document_kind": "category",
                            "media_kind": None},
    (REPORTS, "Person:named"): {"family_name": None, "given_names": None, "aliases": None,
                                "date_of_birth": None, "nino": "subject_1_nino"},
    ("pid_soc_nominals.csv", "Organisation"): {"org_ref": "group_ref", "name": "group_name"},
    (THROW_OVERS, "Incident:throw_over"): {"category": None, "item": "item_type"},
}  # fmt: skip
for _label_name in ("Establishment", *(f"Location:{k}" for k in (
    "wing", "landing", "cell", "yard", "zone", "hall", "place"
))):
    ENTITY_COLUMN_NAMES[(ESTATE, _label_name)] = {
        "site_ref": "place_ref", "establishment_ref": "place_ref"
    }
for _endpoint_label in ("Endpoint:msisdn", "Endpoint:handle", "Endpoint:imsi", "Endpoint:account"):
    for _file in _all_files():
        ENTITY_COLUMN_NAMES[(_file, _endpoint_label)] = dict.fromkeys(
            ("value_raw", "value_normalised", "endpoint_kind", "e164", "handle", "imsi"), None
        )


def _contract_column_files() -> frozenset[str]:
    """The files the contract (the shapes' `handling`) says carry the six handling columns."""
    every: list[Any] = [*pid_plan.LOAD_SHAPES, *pid_plan.ENTITY_SHAPES]
    return frozenset(sh.file for sh in every if sh.handling == "column")


def _expected_header(file: str, column_files: frozenset[str]) -> list[str]:
    """A file's header from the shapes alone, exactly and in order: its links' columns, then its
    entities', each first seen once; then `EXTRAS`; then the handling columns the contract gives."""
    columns: list[str] = []
    every: list[Any] = [*pid_plan.LOAD_SHAPES, *pid_plan.ENTITY_SHAPES]
    for shape in every:
        if shape.file == file:
            columns += [c for c in shape.columns if c not in columns and c not in HANDLING]
    columns += [c for c in pid_files.EXTRAS.get(file, ()) if c not in columns]
    return [*columns, *(HANDLING if file in column_files else ())]


def test_each_files_header_is_the_column_list_derived_from_the_shapes(
    demo_out: Written, scale_out: Written
) -> None:
    contract = _contract_column_files()
    for written in (demo_out, scale_out):
        for file in written.present():
            header = _header(written.path(file))
            assert header == _expected_header(file, contract), (written.plan.profile, file)
            assert header == pid_files.header_for(file), file
            assert len(header) == len(set(header)), f"{file} repeats a column"
    # `EXTRAS` holds only true extras: a column no shape names.
    named = {c for sh in [*pid_plan.LOAD_SHAPES, *pid_plan.ENTITY_SHAPES] for c in sh.columns}
    for file, extras in pid_files.EXTRAS.items():
        assert not set(extras) & named, f"{file}: {sorted(set(extras) & named)} is in a shape"
    # Shown able to fail: a header that names the call number as the plan did before Brief 2's
    # name, and one that lost a shape's column.
    header = _header(demo_out.path(CALLS))
    wanted = _expected_header(CALLS, contract)
    assert header == wanted
    assert ["number" if c == "called_number" else c for c in header] != wanted
    assert [c for c in header if c != "duration_s"] != wanted


def test_the_entity_shapes_name_their_columns_as_brief_2_does() -> None:
    seen = set()
    for shape in pid_plan.ENTITY_SHAPES:
        if shape.recipe == "seed":
            continue
        table = ENTITY_COLUMN_NAMES.get((shape.file, shape.entity_type), {})
        seen.add((shape.file, shape.entity_type))
        for prop in sorted(shape.properties):
            want = table.get(prop, prop)
            assert shape.names.get(prop, prop) == want, (shape.file, shape.entity_type, prop)
            if want is not None:
                assert want in shape.columns, (shape.file, shape.entity_type, prop)
    assert seen >= {
        ("pid_nomis_visits.csv", "Person:visitor"), (REPORTS, "Document"),
        (ESTATE, "Location:yard"), ("pid_soc_nominals.csv", "Organisation"),
    }  # fmt: skip
    # Shown able to fail: a visitor's family name left under the plan's name.
    visitor = next(sh for sh in pid_plan.ENTITY_SHAPES if sh.entity_type == "Person:visitor")
    unrenamed = dataclasses.replace(visitor, names={})
    table = ENTITY_COLUMN_NAMES[(visitor.file, visitor.entity_type)]
    assert unrenamed.names.get("family_name", "family_name") != table["family_name"]


def test_the_headers_carry_the_names_brief_2_gives_and_the_kept_columns_are_empty(
    demo_out: Written,
) -> None:
    for file, names in BRIEF_2_ENTITY_COLUMNS.items():
        missing = names - set(_header(demo_out.path(file)))
        assert not missing, f"{file} lacks {sorted(missing)}"
    # R10's `recovered`, R12's `role` and R9's subject roles are kept and left empty: the plan
    # holds no value for them. (R1's `wing_ref` and `cell_ref` are not kept: R1's split addition
    # moved them to the cell-stay file.)
    for file, column in ((THROW_OVERS, "recovered"), ("pid_soc_nominals.csv", "role"),
                         (REPORTS, "subject_2_role")):  # fmt: skip
        values = {row[column] for row in demo_out.rows(file)}
        assert values == {""}, (file, column, values)
    assert "wing_ref" not in _header(demo_out.path("pid_nomis_prisoners.csv"))
    assert "cell_ref" not in _header(demo_out.path("pid_nomis_prisoners.csv"))
    # Shown able to fail: a header that names a value as the plan did before Brief 2's name.
    header = _header(demo_out.path(CALLS))
    renamed = [("number" if c == "called_number" else c) for c in header]
    assert BRIEF_2_ENTITY_COLUMNS[CALLS] - set(renamed) == {"called_number"}


def _handling_problems(
    written: Written, headers: Mapping[str, list[str]], column_files: frozenset[str]
) -> list[str]:
    """A file carries the six handling columns, last, exactly when the contract says it does, and
    every file this profile's rows make mixed is one the contract names."""
    out = [
        f"{file}: mixed in this profile but not a column file in the contract"
        for file in sorted(pid_plan.mixed_files(written.plan) - column_files)
    ]
    for file, header in headers.items():
        has = [c for c in HANDLING if c in header]
        if file in column_files and (has != list(HANDLING) or header[-6:] != list(HANDLING)):
            out.append(f"{file}: a column file lacks the handling columns, last: {has}")
        if file not in column_files and has:
            out.append(f"{file}: a file the contract gives none carries {has}")
    return out


def test_the_handling_columns_follow_the_contract_in_every_profile(
    demo_out: Written, scale_out: Written
) -> None:
    contract = _contract_column_files()
    soc = "pid_soc_nominals.csv"
    assert contract == pid_plan.mixed_files(pid_plan.build_plan("demo")) | pid_plan.mixed_files(
        scale_out.plan
    ), "the contract is the union of the profiles' mixed files"
    for written in (demo_out, scale_out):
        headers = {f: _header(written.path(f)) for f in written.present()}
        assert _handling_problems(written, headers, contract) == []
        assert pid_plan.mixed_files(written.plan) <= contract
    # One handling in the demo's rows, and the file still carries the columns: the contract says so.
    assert soc not in pid_plan.mixed_files(demo_out.plan)
    assert "classification" in _header(demo_out.path(soc))
    assert soc in pid_plan.mixed_files(scale_out.plan), "the scale profile makes it mixed"
    # Shown able to fail, on the real headers: the contract without a file the scale profile makes
    # mixed, a mixed file's header without a handling column, and one the contract gives none with.
    headers = {f: _header(scale_out.path(f)) for f in scale_out.present()}
    without = _handling_problems(scale_out, headers, contract - {soc})
    assert any(soc in p and "not a column file" in p for p in without), without
    one = sorted(contract & set(headers))[0]
    lost = {**headers, one: [c for c in headers[one] if c != "classification"]}
    assert len(_handling_problems(scale_out, lost, contract)) == 1
    single = "pid_throwover_log.csv"
    heads = {f: _header(demo_out.path(f)) for f in demo_out.present()}
    assert single not in contract
    extra = {**heads, single: [*heads[single], "classification"]}
    assert len(_handling_problems(demo_out, extra, contract)) == 1


def test_no_generated_text_carries_a_name_the_naming_rule_forbids(
    demo_out: Written, scale_out: Written
) -> None:
    for written in (demo_out, scale_out):
        for path in written.out.rglob("*"):
            assert not any(token in path.as_posix().lower() for token in FORBIDDEN), path
            if path.is_file() and path.suffix in (".csv", ".json"):
                data = path.read_bytes().lower()
                assert not any(token.encode() in data for token in FORBIDDEN), path.name


def _line_problems(file: str, data: bytes) -> list[str]:
    out = []
    if b"\r" in data:
        out.append(f"{file} has a carriage return")
    if b"report:" in data:
        out.append(f"{file} writes a report's plan key")
    if not data.endswith(b"\n"):
        out.append(f"{file} does not end in a line end")
    return out


def test_the_csv_files_use_unix_line_ends_and_never_write_a_plan_key_for_a_report(
    demo_out: Written, scale_out: Written
) -> None:
    for written in (demo_out, scale_out):
        for file in written.present():
            assert _line_problems(file, written.path(file).read_bytes()) == []
    # Shown able to fail, on the real reports file: a plan key in place of an IR reference, and a
    # Windows line end.
    data = demo_out.path(REPORTS).read_bytes()
    first = next(iter(demo_out.rows(REPORTS)))["report_ref"].encode()
    assert first.startswith(b"IR ")
    assert _line_problems(REPORTS, data.replace(first, b"report:0001", 1)) == [
        f"{REPORTS} writes a report's plan key"
    ]
    assert _line_problems(REPORTS, data.replace(b"\n", b"\r\n", 1)) == [
        f"{REPORTS} has a carriage return"
    ]


# --- The call file and its mess ----------------------------------------------------------------


@dataclasses.dataclass
class CallScan:
    rows: int
    mismatches: list[str]
    written_to_e164: dict[str, str]
    durations: tuple[int, int]
    directions: set[str]
    sequence_problems: list[str]
    kept: dict[int, list[str]]
    header: list[str]


def _scan_calls(written: Written, duplicates: Sequence[tuple[int, int]]) -> CallScan:
    """Walks the call file beside the plan's own rows, skipping the rows the engine's key calls
    duplicates, and keeps those rows and the ones they repeat."""
    wanted = {n for pair in duplicates for n in pair}
    skipped = {n for n, _ in duplicates}
    plan = written.plan
    raw_of = {
        e.properties["value_normalised"]: e.properties["value_raw"]
        for e in plan.entities
        if e.properties.get("endpoint_kind") == "msisdn"
    }
    expected = pid_plan.rows_for(plan, CALLS)
    cache: dict[str, str] = {}
    first_seen: set[str] = set()
    mismatches: list[str] = []
    sequence_problems: list[str] = []
    kept: dict[int, list[str]] = {}
    low, high, distinct = 10**9, 0, 0
    broke = False
    directions: set[str] = set()
    with written.path(CALLS).open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        col = {name: i for i, name in enumerate(header)}
        total = 0
        for number, cells in enumerate(reader, start=1):
            total += 1
            if number in wanted:
                kept[number] = cells
            if number in skipped:
                continue
            distinct += 1
            plan_row = next(expected)
            for name in ("nomis_id", "pin_account", "call_start", *HANDLING):
                if cells[col[name]] != plan_row.values[name]:
                    mismatches.append(f"row {number}: {name} {cells[col[name]]!r}")
            written_form = cells[col["called_number"]]
            if written_form not in cache:
                cache[written_form] = msisdn(written_form)
            planned = plan_row.values["called_number"]
            if cache[written_form] != planned:
                mismatches.append(f"row {number}: {written_form!r} is not {planned}")
            if planned not in first_seen:
                first_seen.add(planned)
                if written_form != raw_of[planned]:
                    mismatches.append(f"row {number}: a number's first row is not its raw form")
            if cells[col["call_start"]] > LAST_CALL_INSTANT:
                mismatches.append(f"row {number}: a call after the cut-off")
            duration = int(cells[col["duration_s"]])
            low, high = min(low, duration), max(high, duration)
            directions.add(cells[col["direction"]])
            if cells[col["sequence"]] != str(distinct):
                sequence_problems.append(f"row {number}: sequence {cells[col['sequence']]}")
            if len(mismatches) > 20 or len(sequence_problems) > 20:
                broke = True
                break
    if not broke:
        assert next(expected, None) is None, "the file has fewer distinct calls than the plan"
    return CallScan(total, mismatches, cache, (low, high), directions, sequence_problems, kept,
                    header)  # fmt: skip


@pytest.fixture(scope="module")
def call_scan(demo_out: Written, demo_read: Reader) -> CallScan:
    return _scan_calls(demo_out, demo_read.stats[CALLS].duplicates)


@dataclasses.dataclass
class Mess:
    forms: Mapping[str, int]
    exact: list[int]
    sequence: list[int]


def _mess(read: Reader, scan: CallScan) -> Mess:
    exact, sequence = [], []
    col = {name: i for i, name in enumerate(scan.header)}
    for number, first in read.stats[CALLS].duplicates:
        if scan.kept[number] == scan.kept[first]:
            exact.append(number)
        else:
            differing = [n for n in col if scan.kept[number][col[n]] != scan.kept[first][col[n]]]
            if differing == ["sequence"]:
                sequence.append(number)
    return Mess(dict(read.stats[CALLS].forms), exact, sequence)


def _mess_problems(mess: Mess) -> list[str]:
    out = []
    for form in ("plus_44", "zero_zero_44", "bare_44"):
        if mess.forms.get(form) != FORM_COUNT:
            out.append(f"{mess.forms.get(form)} distinct calls in {form}, wants {FORM_COUNT}")
    if len(mess.exact) != EXACT_DUPLICATES:
        out.append(f"{len(mess.exact)} exact duplicates, wants {EXACT_DUPLICATES}")
    if len(mess.sequence) != SEQUENCE_DUPLICATES:
        out.append(f"{len(mess.sequence)} sequence duplicates, wants {SEQUENCE_DUPLICATES}")
    if mess.forms.get("other"):
        out.append(f"{mess.forms['other']} calls in no known form")
    return out


def test_the_call_file_has_exactly_the_planted_mess_at_the_recorded_positions(
    demo: Any, demo_out: Written, demo_read: Reader, call_scan: CallScan
) -> None:
    stats = demo_read.stats[CALLS]
    assert stats.rows == call_scan.rows == CALL_ROWS + EXACT_DUPLICATES + SEQUENCE_DUPLICATES
    assert stats.distinct == CALL_ROWS
    assert 90_000 <= CALL_ROWS <= 110_000, "ADR-120 Amendment 17: about 100,000 calls"
    assert CALL_ROWS == sum(
        lk.occurrences
        for lk in demo.links
        if lk.link_type == "COMMUNICATED_WITH" and lk.source.startswith("pin:")
    )
    mess = _mess(demo_read, call_scan)
    assert _mess_problems(mess) == []
    assert mess.forms["national"] == CALL_ROWS - 3 * FORM_COUNT
    assert len(stats.duplicates) == EXACT_DUPLICATES + SEQUENCE_DUPLICATES
    # The positions the writer records are the ones the engine's key finds, and no others.
    planted = demo_out.report.planted[CALLS]
    assert sorted(planted["exact_duplicate_rows"]) == sorted(mess.exact)
    assert sorted(planted["sequence_duplicate_rows"]) == sorted(mess.sequence)
    originals = dict(stats.duplicates)
    assert [originals[n] for n in planted["exact_duplicate_rows"]] == planted["exact_duplicate_of"]
    assert [originals[n] for n in planted["sequence_duplicate_rows"]] == planted[
        "sequence_duplicate_of"
    ]
    assert all(first < number for number, first in stats.duplicates)
    # A repeat with a new sequence number carries one above every real call's, and each its own.
    col = {name: i for i, name in enumerate(call_scan.header)}
    sequences = [int(call_scan.kept[n][col["sequence"]]) for n in mess.sequence]
    assert len(set(sequences)) == SEQUENCE_DUPLICATES and min(sequences) > CALL_ROWS
    # The counts the writer records are the ones it wrote, not constants: the engine's distinct
    # calls in each form, read back from the file.
    assert planted["distinct_calls"] == CALL_ROWS
    assert planted["form_counts"] == dict(mess.forms)
    assert planted["form_counts"]["national"] == CALL_ROWS - 3 * FORM_COUNT


def test_the_mess_counts_go_red_for_one_duplicate_fewer(
    demo_read: Reader, call_scan: CallScan
) -> None:
    mess = _mess(demo_read, call_scan)
    assert _mess_problems(mess) == []
    assert _mess_problems(dataclasses.replace(mess, exact=mess.exact[:-1])) == [
        f"{EXACT_DUPLICATES - 1} exact duplicates, wants {EXACT_DUPLICATES}"
    ]
    assert _mess_problems(dataclasses.replace(mess, sequence=mess.sequence[:-1])) == [
        f"{SEQUENCE_DUPLICATES - 1} sequence duplicates, wants {SEQUENCE_DUPLICATES}"
    ]
    fewer = {**mess.forms, "bare_44": FORM_COUNT - 1, "national": mess.forms["national"] + 1}
    assert len(_mess_problems(dataclasses.replace(mess, forms=fewer))) == 1


def _form_problems(written: Mapping[str, str]) -> list[str]:
    """Each of the call file's outside numbers is written in all four forms somewhere (the
    claim is the call file's alone)."""
    forms_of: dict[str, set[str]] = {}
    for form_written, number in written.items():
        forms_of.setdefault(number, set()).add(_form_of(form_written))
    every = {"national", "plus_44", "zero_zero_44", "bare_44"}
    return [
        f"{number} is missing {sorted(every - forms)}"
        for number, forms in sorted(forms_of.items())
        if forms != every
    ]


def test_every_distinct_written_number_normalises_to_the_plans_through_the_real_msisdn(
    call_scan: CallScan,
) -> None:
    assert call_scan.mismatches == [], call_scan.mismatches[:5]
    written = call_scan.written_to_e164
    # 1,500 outside numbers, each written all four ways somewhere in the call file: 6,000 forms.
    assert len(set(written.values())) == 1_500 and len(written) == 6_000
    assert _form_problems(written) == []
    # Shown able to fail: one number's `0044` form taken out of what the file wrote.
    victim = next(w for w in written if _form_of(w) == "zero_zero_44")
    fewer = {w: n for w, n in written.items() if w != victim}
    problems = _form_problems(fewer)
    assert len(problems) == 1 and written[victim] in problems[0] and "zero_zero_44" in problems[0]
    # Shown able to fail: a number the mess would corrupt is refused, not read as another.
    with pytest.raises(NormalisationError):
        msisdn("+44 7700 900 6O3")


def test_each_seized_files_imei_cell_is_the_plans_written_15_digit_value(
    demo: Any, demo_out: Written
) -> None:
    """The reader's `imei` adapter accepts 14 digits, so only this catches a writer that drops the
    check digit: every handset the plan holds is in its batch's file, as the plan wrote it."""
    for file, wanted in ((BATCH_1, "batch1"), (BATCH_2, "batch2")):
        cells = {row["imei"] for row in demo_out.rows(file)}
        planned = {
            str(e.properties["imei"])
            for e in demo.entities
            if e.entity_type == "Device"
            and (e.key == "handset:batch2") == (wanted == "batch2")
        }
        assert cells == planned, file
        assert cells and all(len(c) == 15 and c.isdigit() for c in cells), file
    # Shown able to fail: the 14-digit form the adapter would give is not the plan's value.
    sample = next(iter(demo_out.rows(BATCH_1)))["imei"]
    assert imei(sample) != sample and len(imei(sample)) == 14


def test_the_first_row_of_every_number_in_each_file_is_the_plans_own_form(
    demo: Any, demo_out: Written, demo_read: Reader
) -> None:
    """Whichever recipe runs first creates the endpoint as the plan holds it. The one exception is
    deliberate: the reports file's only row naming `+447700900603` is teaching row 17, whose
    corrected value is that number's own `value_raw`."""
    raw = {
        e.properties["value_normalised"]: e.properties["value_raw"]
        for e in demo.entities
        if e.properties.get("endpoint_kind") == "msisdn"
    }
    files = {file for file, _ in demo_read.first_raw}
    assert files == {CALLS, BATCH_1, BATCH_2, "pid_number_owners.csv", REPORTS}
    wrong = [
        (file, number, written)
        for (file, number), written in demo_read.first_raw.items()
        if file != REPORTS and written != raw[number]
    ]
    assert wrong == [], wrong[:5]
    reports = {n: w for (f, n), w in demo_read.first_raw.items() if f == REPORTS}
    assert reports == {pid_plan.PID_TEACHING_NUMBER: CORRECTED_NUMBER}
    assert raw[pid_plan.PID_TEACHING_NUMBER] == CORRECTED_NUMBER
    # Shown able to fail, on the real seized file: its numbers written in E.164 instead.
    planted = Reader()
    planted.read(
        BATCH_1,
        ({**row, "other_number": msisdn(row["other_number"])} for row in demo_out.rows(BATCH_1)),
    )
    assert [k for k, w in planted.first_raw.items() if w != raw[k[1]]]


def test_the_call_file_carries_a_seeded_duration_direction_and_running_sequence(
    call_scan: CallScan,
) -> None:
    assert call_scan.sequence_problems == [], call_scan.sequence_problems[:5]
    assert call_scan.durations[0] >= 20 and call_scan.durations[1] <= 1_800
    assert call_scan.durations[1] - call_scan.durations[0] > 1_000
    assert call_scan.directions == {"outbound"}


def test_no_two_distinct_calls_share_the_engines_key(demo_read: Reader) -> None:
    """The reader groups by the real `dedup_key`, so a collision between two distinct calls would
    have counted them once: the distinct count equals the plan's calls exactly (checked above), and
    the only rows it dropped are the 80 planted."""
    stats = demo_read.stats[CALLS]
    assert stats.rows - stats.distinct == len(stats.duplicates) == 80
    assert not stats.rejected


# --- The reports file and its teaching rows ----------------------------------------------------


def test_the_reports_file_is_one_row_per_report_with_two_teaching_rows(
    demo: Any, demo_out: Written
) -> None:
    rows = list(demo_out.rows(REPORTS))
    refs = [r["report_ref"] for r in rows]
    # `report_ref` is the IR reference its text shows, unique across the 350, and the rows stay in
    # plan-key order, so the teaching rows stay where they are.
    keys = sorted(demo.report_texts)
    assert refs == [_ir(demo, k) for k in keys]
    assert len(refs) == len(set(refs)) == 350
    assert all(re.fullmatch(r"IR \d{4}", ref) for ref in refs)
    assert keys[TEACHING_ROW - 1] == pid_plan.PID_TEACHING_REPORT
    assert refs[TEACHING_ROW - 1] == _ir(demo, pid_plan.PID_TEACHING_REPORT)
    assert keys[INITIALS_ROW - 1] == "report:0101"
    # Shown able to fail: two reports sharing a reference are counted as one by the check.
    assert len(set([*refs[:5], refs[0]])) == 5
    bad = [n for n, r in enumerate(rows, start=1) if r["phone_mentioned"]]
    assert bad == [TEACHING_ROW]
    assert rows[TEACHING_ROW - 1]["phone_mentioned"] == pid_plan.PID_TEACHING_BAD_NUMBER
    for n, (key, r) in enumerate(zip(keys, rows, strict=True), start=1):
        text = demo.report_texts[key]
        if n == TEACHING_ROW:
            assert r["report_text"] != text and r["report_text"].startswith(text)
            assert pid_plan.PID_TEACHING_BAD_NUMBER in r["report_text"]
        else:
            assert r["report_text"] == text
        assert len(r["report_text"]) < 1_000
        pattern = r"[A-Z]{3}" if n == INITIALS_ROW else r"[A-Z]{2}"
        assert re.fullmatch(pattern, r["reviewer_initials"]), (n, r["reviewer_initials"])
    assert len({r["reviewer_initials"] for r in rows}) >= 20, "seeded, not one constant"
    # Subjects: up to three, their role columns present and empty (the plan holds no role).
    header = _header(demo_out.path(REPORTS))
    assert {"subject_1_role", "subject_2_role", "subject_3_role"} <= set(header)
    assert all(not r[f"subject_{i}_role"] for r in rows for i in (1, 2, 3))
    # ADR-120 Amendment 15: `subject_N` holds prison numbers only; an outside subject's NINO is in
    # `subject_N_nino` and that row's `subject_N` is empty, so a slot is one or the other.
    for r in rows:
        for i in (1, 2, 3):
            assert not (r[f"subject_{i}"] and r[f"subject_{i}_nino"]), (r["report_ref"], i)
            assert not NINO.fullmatch(r[f"subject_{i}"]), (r["report_ref"], i)
            assert not r[f"subject_{i}_nino"] or NINO.fullmatch(r[f"subject_{i}_nino"])
        filled = [bool(r[f"subject_{i}"] or r[f"subject_{i}_nino"]) for i in (1, 2, 3)]
        assert filled == sorted(filled, reverse=True), "slots fill from the first"
    outside = [r for r in rows if any(r[f"subject_{i}_nino"] for i in (1, 2, 3))]
    assert len(outside) == 1, "one report names an outside subject"
    assert any(outside[0][f"subject_{i}_nino"] and outside[0][f"subject_{i}_family_name"]
               for i in (1, 2, 3))  # fmt: skip


def test_the_teaching_number_is_refused_with_its_cause_and_the_corrected_one_accepted() -> None:
    with pytest.raises(NormalisationError) as refused:
        msisdn(pid_plan.PID_TEACHING_BAD_NUMBER)
    assert refused.value.adapter == "msisdn" and "letters" in refused.value.reason
    assert msisdn(CORRECTED_NUMBER) == pid_plan.PID_TEACHING_NUMBER
    # The bad number is the corrected one with a letter O for a nought, so the dry run's refusal is
    # the only difference between the two.
    assert pid_plan.PID_TEACHING_BAD_NUMBER.replace("O", "0").replace(" ", "") == (
        CORRECTED_NUMBER.replace(" ", "")
    )


def test_the_report_incident_file_is_one_row_per_report_and_throw_over(
    demo: Any, demo_out: Written
) -> None:
    rows = list(demo_out.rows(REPORT_INCIDENTS))
    pairs = [(r["report_ref"], r["incident_ref"]) for r in rows]
    assert len(pairs) == len(set(pairs)) == 589
    ent = {e.key: e for e in demo.entities}
    mentions = [
        lk for lk in demo.links
        if lk.link_type == "MENTIONED_IN" and lk.source.startswith("incident:to:")
    ]  # fmt: skip
    assert len(mentions) == len(rows)
    # The report is named by its IR reference, as in the reports file: the same references.
    want = {(_ir(demo, lk.target), _identifier(ent[lk.source])) for lk in mentions}
    assert set(pairs) == want
    assert {ref for ref, _ in pairs} <= {r["report_ref"] for r in demo_out.rows(REPORTS)}


def test_a_single_prisoner_in_a_report_text_takes_a_singular_verb(demo: Any) -> None:
    # A prisoner who is the only one named: not the last of "A and B" or "A, B and C".
    plural = re.compile(r"(?<![d,] )Prisoner [A-Z][a-z]+ were\b")
    assert [t for t in demo.report_texts.values() if plural.search(t)] == []
    singular = re.compile(r"Prisoner [A-Z][a-z]+ was seen\b")
    assert any(singular.search(t) for t in demo.report_texts.values())
    # Shown able to fail: the old sentence is found by the same check.
    assert plural.search("Officer Hall reports that Prisoner Selwood were seen at the door.")


# --- Places ------------------------------------------------------------------------------------


def _place_problems(
    estate: Iterable[dict[str, str]],
    throw_overs: Iterable[dict[str, str]],
    points: Mapping[str, Any],
) -> list[str]:
    """Each place with a point resolves through the real `geometry_ref` transform to the plan's
    point, no place without one has a coordinate, and every throw-over lies within the jitter of
    its yard's point."""
    out: list[str] = []
    yards: dict[str, tuple[float, float]] = {}
    pointed: dict[str, tuple[float, float]] = {}
    for row in estate:
        if not row["lat"] and not row["lon"]:
            continue
        raw = (row["lon"], row["lat"])
        ref = REGISTRY["geometry_ref"](raw, source_crs="EPSG:4326")
        lon = REGISTRY["coordinate_lon"](raw, source_crs="EPSG:4326")
        lat = REGISTRY["coordinate_lat"](raw, source_crs="EPSG:4326")
        if not str(ref).startswith("geo:") or abs(lon - float(row["lon"])) > 1e-9:
            out.append(f"{row['place_ref']}: does not resolve")
        if abs(lat - float(row["lat"])) > 1e-9:
            out.append(f"{row['place_ref']}: latitude moved by the transform")
        pointed[row["place_ref"]] = (float(row["lat"]), float(row["lon"]))
        if row["place_kind"] == "yard":
            yards[row["place_ref"]] = pointed[row["place_ref"]]
    if pointed != dict(points):
        out.append(f"places with a point: {sorted(set(pointed) ^ set(points))}")
    for row in throw_overs:
        centre = yards[row["yard_ref"]]
        lat, lon = float(row["lat"]), float(row["lon"])
        if abs(lat - centre[0]) > JITTER_DEGREES or abs(lon - centre[1]) > JITTER_DEGREES:
            out.append(f"{row['incident_ref']}: more than the jitter from its yard")
    return out


def test_every_place_resolves_through_the_geometry_transform_and_every_throw_over_is_by_its_yard(
    demo: Any, demo_out: Written
) -> None:
    points = {
        _identifier(demo.entity(key)): point for key, point in pid_plan.PLACE_POINTS.items()
    }
    assert "pid:out:place:arrest-01" in points, "the outside arrest site has a point"
    assert _place_problems(demo_out.rows(ESTATE), demo_out.rows(THROW_OVERS), points) == []
    assert sum(1 for _ in demo_out.rows(THROW_OVERS)) == 262
    # Shown able to fail: one throw-over moved a hundredth of a degree, and one yard's point lost.
    moved = [
        {**r, "lat": repr(float(r["lat"]) + 0.01)} if n == 7 else r
        for n, r in enumerate(demo_out.rows(THROW_OVERS))
    ]
    problems = _place_problems(demo_out.rows(ESTATE), moved, points)
    assert len(problems) == 1 and "more than the jitter" in problems[0]
    unpointed = [
        {**r, "lat": "", "lon": ""} if r["place_ref"] == "pid:est1:yard:03" else r
        for r in demo_out.rows(ESTATE)
    ]
    assert _place_problems(unpointed, [], points)


# --- Pictures ----------------------------------------------------------------------------------


def decode_png(data: bytes) -> tuple[int, int, int, int, bytes]:
    """A standard-library decode: signature, every chunk's length and CRC, IHDR first and IEND last,
    the IDAT inflated. Returns width, height, bit depth, colour type and the raw scanlines."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, tags, header = 8, b"", [], b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])
        assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF, f"bad CRC in {tag!r}"
        tags.append(tag)
        if tag == b"IHDR":
            header = body
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    assert tags[0] == b"IHDR" and tags[-1] == b"IEND" and b"IDAT" in tags
    fields = struct.unpack(">IIBBBBB", header)
    width, height, depth, colour, compression, filtering, interlace = fields
    assert (compression, filtering, interlace) == (0, 0, 0)
    raw = zlib.decompress(idat)
    assert len(raw) == height * (1 + width * 3)
    return width, height, depth, colour, raw


def _kind_of(plan: Any, key: str) -> str:
    visitors = frozenset(lk.source for lk in plan.links if lk.link_type == "VISITED")
    label = _label(plan.entity(key), visitors)
    return {
        "Person": "person", "Establishment": "establishment", "Location:wing": "wing",
        "Location:yard": "yard", "Device": "handset", "Organisation": "group",
    }[label.split(":")[0] if label.startswith("Person") else label]  # fmt: skip


@pytest.fixture(scope="module")
def pictures(demo: Any) -> list[tuple[str, str, bytes]]:
    return pid_writes.picture_writes(demo)


def test_every_picture_is_a_valid_256_by_256_rgb_png_under_50_kb(
    demo: Any, pictures: list[tuple[str, str, bytes]]
) -> None:
    assert len(pictures) == len(demo.picture_subjects) == 1_633
    for _, name, data in pictures:
        width, height, depth, colour, raw = decode_png(data)
        assert (width, height, depth, colour) == (256, 256, 8, 2), name
        assert image_dimensions(data) == (256, 256), name
        assert len(data) < 50_000, f"{name} is {len(data)} bytes"
    # Shown able to fail: a flipped byte in a chunk breaks its CRC; a short body is refused.
    data = bytearray(pictures[0][2])
    data[-20] ^= 0xFF
    with pytest.raises(AssertionError):
        decode_png(bytes(data))


def test_picture_names_are_the_key_with_colons_replaced_and_pass_the_routes_own_check(
    demo: Any, pictures: list[tuple[str, str, bytes]]
) -> None:
    extensions = frozenset(f".{ext}" for ext in PICTURE_TYPES)
    names = [name for _, name, _ in pictures]
    assert len(set(names)) == len(names)
    for subject, (node, name, _) in zip(demo.picture_subjects, pictures, strict=True):
        assert name == subject.replace(":", "_") + ".png"
        assert node == pid_plan.node_id(subject)
        assert validate_upload_name(name, extensions) == name
    # Shown able to fail: a name with a folder, and one that is not a picture.
    with pytest.raises(UploadRefused):
        validate_upload_name("pictures/a.png", extensions)
    with pytest.raises(UploadRefused):
        validate_upload_name("a.csv", extensions)


def test_every_picture_differs_from_every_other_byte_for_byte(
    pictures: list[tuple[str, str, bytes]],
) -> None:
    digests = [hashlib.sha256(data).hexdigest() for _, _, data in pictures]
    assert len(set(digests)) == len(digests)
    # The picture route keys a Document by its content, so two equal pictures would be one Document.
    assert len({node for node, _, _ in pictures}) == len(pictures)


def test_a_picture_is_the_drawer_of_its_kind_and_the_plans_seed_and_is_reproducible(
    demo: Any, pictures: list[tuple[str, str, bytes]]
) -> None:
    for subject, (_, _, data) in list(zip(demo.picture_subjects, pictures, strict=True))[::25]:
        kind = _kind_of(demo, subject)
        assert data == pid_pictures.draw_picture(subject, kind, demo.seed), subject
        assert data == pid_pictures.draw_picture(subject, kind, demo.seed), "not reproducible"
        assert data != pid_pictures.draw_picture(subject, kind, demo.seed + 1), "seed unused"
    kinds = {_kind_of(demo, s) for s in demo.picture_subjects}
    assert kinds == set(PICTURE_KINDS)
    one = demo.picture_subjects[0]
    drawn = {pid_pictures.draw_picture(one, kind, demo.seed) for kind in PICTURE_KINDS}
    assert len(drawn) == len(PICTURE_KINDS), "a kind draws the same as another"
    with pytest.raises(ValueError):
        pid_pictures.draw_picture(one, "castle", demo.seed)


def test_the_picture_module_is_standard_library_only_and_imports_nothing_from_the_plan() -> None:
    source = Path(pid_pictures.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import reaches the package, and the plan"
            roots.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    assert roots <= set(sys.stdlib_module_names) | {"__future__"}, roots
    assert not {"pid_plan", "HOTSPOT_YARDS", "YARD_COUNTS"} & names


def test_a_picture_is_drawn_without_reading_any_file(
    demo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The module is reloaded and every picture drawn with every way of reading a file refused: an
    asset read at import or at draw time (a font, a template, a stock image) would raise."""
    subjects = [(s, _kind_of(demo, s)) for s in demo.picture_subjects]

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a file was read")

    failure: BaseException | None = None
    drawn = 0
    with monkeypatch.context() as patched:
        patched.setattr(builtins, "open", refuse)
        patched.setattr(io, "open", refuse)
        patched.setattr(os, "open", refuse)
        patched.setattr(Path, "open", refuse)
        patched.setattr(Path, "read_bytes", refuse)
        patched.setattr(Path, "read_text", refuse)
        try:
            importlib.reload(pid_pictures)
            for subject, kind in subjects:
                pid_pictures.draw_picture(subject, kind, demo.seed)
                drawn += 1
        except BaseException as exc:  # noqa: BLE001 - reported below, outside the patches
            failure = exc
    assert failure is None, f"{type(failure).__name__}: {failure}"
    assert drawn == len(subjects) == 1_633


def _yard_pictures(plan: Any) -> dict[str, bytes]:
    """The twelve yards' pictures, drawn through `picture_writes` as the route gets them."""
    yards = tuple(s for s in plan.picture_subjects if _kind_of(plan, s) == "yard")
    only = dataclasses.replace(plan, picture_subjects=yards)
    return {name: data for _, name, data in pid_writes.picture_writes(only)}


def test_the_yard_pictures_do_not_show_which_yards_are_hotspots(
    demo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All twelve yards drawn through `picture_writes`, then again after the picture module is
    reloaded with the plan's hotspots and counts patched to other values: every one identical. A
    drawer that used what it imports from the plan to draw would differ."""
    before = _yard_pictures(demo)
    assert len(before) == 12 and len(set(before.values())) == 12
    assert {n.removesuffix(".png") for n in before} == {f"yard_{c}" for c in pid_plan.YARD_COUNTS}
    try:
        with monkeypatch.context() as patched:
            patched.setattr(pid_plan, "HOTSPOT_YARDS", frozenset({"01", "02"}))
            patched.setattr(pid_plan, "YARD_COUNTS", dict.fromkeys(pid_plan.YARD_COUNTS, 1))
            importlib.reload(pid_pictures)
            after = _yard_pictures(demo)
    finally:
        importlib.reload(pid_pictures)
    assert after == before


def test_the_contact_sheet_tiles_its_pictures_in_a_valid_png(demo: Any) -> None:
    sample = [
        pid_pictures.draw_picture(f"sheet:{n}", PICTURE_KINDS[n % 6], demo.seed) for n in range(18)
    ]
    sheet = pid_pictures.contact_sheet(sample, columns=6, tile=128)
    width, height, depth, colour, raw = decode_png(sheet)
    assert (width, height, depth, colour) == (768, 384, 8, 2)
    assert image_dimensions(sheet) == (768, 384)
    for index, picture in enumerate(sample):
        assert _tile_of(raw, index) == _shrunk(picture), index
    # A short last row is left grey, not dropped.
    short = decode_png(pid_pictures.contact_sheet(sample[:7], columns=6, tile=128))
    assert (short[0], short[1]) == (768, 256)
    with pytest.raises(ValueError):
        pid_pictures.contact_sheet([])


def _shrunk(picture: bytes) -> list[bytes]:
    """A 256-pixel picture's rows as the sheet shrinks it: every 2nd pixel of every 2nd row."""
    raw = decode_png(picture)[4]
    stride = 1 + 256 * 3
    out = []
    for y in range(128):
        line = raw[y * 2 * stride + 1 : (y * 2 + 1) * stride]
        out.append(b"".join(line[x * 6 : x * 6 + 3] for x in range(128)))
    return out


def _tile_of(sheet_raw: bytes, index: int, columns: int = 6, tile: int = 128) -> list[bytes]:
    stride = 1 + columns * tile * 3
    left, top = (index % columns) * tile, (index // columns) * tile
    return [
        sheet_raw[(top + y) * stride + 1 + left * 3 : (top + y) * stride + 1 + (left + tile) * 3]
        for y in range(tile)
    ]


# --- The store writes --------------------------------------------------------------------------

_WRITES: dict[tuple[str, str, str], tuple[list[Any], list[Any]]] = {}


def _writes(plan: Any, moment: str, dataset: str = PID.id) -> tuple[list[Any], list[Any]]:
    key = (plan.profile, moment, dataset)
    if key not in _WRITES:
        _WRITES[key] = pid_writes.writes(plan, moment, dataset=dataset, created_at=CREATED)
    return _WRITES[key]


def test_the_entity_moments_are_the_ones_the_plan_loads_them_at(demo: Any, scale: Any) -> None:
    visitors = frozenset(lk.source for lk in demo.links if lk.link_type == "VISITED")
    reports = {e.key for e in demo.entities if e.entity_type == "Document" and not _is_picture(e)}
    assert len(reports) == 350
    for e in demo.entities:
        moment = pid_plan.entity_moment(demo, e.key)
        if e.key in reports or _label(e, visitors) == "Person:named":
            assert moment == "chapter4", e.key
        elif e.key in ("handset:batch2", "sim:batch2"):
            assert moment == "chapter9", e.key
        else:
            assert moment == "seed", e.key
    # A link is never loaded before its ends exist.
    for plan in (demo, scale):
        for lk in plan.links:
            at = plan.moment_of.get(lk.key, "seed")
            for end in (lk.source, lk.target):
                assert RANK[pid_plan.entity_moment(plan, end)] <= RANK[at], (lk.key, end)
    with pytest.raises(KeyError):
        pid_plan.entity_moment(demo, "no such entity")


@pytest.mark.parametrize("profile", ["demo", "scale"])
def test_the_writes_are_the_plan_at_each_moment_with_derived_ids(
    profile: str, demo: Any, scale: Any
) -> None:
    plan, seed = (demo, PID) if profile == "demo" else (scale, PID_SCALE)
    counts = []
    for moment in MOMENTS:
        nodes, edges = _writes(plan, moment, seed.id)
        want_nodes = {
            pid_plan.node_id(e.key)
            for e in plan.entities
            if RANK[pid_plan.entity_moment(plan, e.key)] <= RANK[moment] and not _is_picture(e)
        }
        want_edges = {
            pid_plan.link_id(lk)
            for lk in pid_plan.links_at(plan, moment, secret_cleared=True)
            if lk.link_type != "DEPICTS"
        }
        assert [n.id for n in nodes] and set(n.id for n in nodes) == want_nodes
        assert len(nodes) == len(want_nodes) and len(edges) == len(want_edges)
        assert {e.id for e in edges} == want_edges
        assert all(i.startswith("pid-") and len(i) == 28 for i in want_nodes | want_edges)
        counts.append((len(nodes), len(edges)))
    seed_nodes, seed_edges = _writes(plan, "seed", seed.id)
    assert not [n for n in seed_nodes if n.type == "Document"], "no report at the seed"
    assert not [e for e in seed_edges if e.type == "DEPICTS"]
    nodes, edges = _writes(plan, "chapter9", seed.id)
    if profile == "scale":
        assert counts[0] == counts[1] == counts[2], "the scale cohort loads at the seed"
        assert not [n for n in nodes if n.type == "Document"]
        return
    assert counts[0] < counts[1] < counts[2], counts
    assert len([n for n in nodes if n.type == "Document"]) == 350
    # What the picture route writes is left to it: no image Document, no DEPICTS link.
    assert not [n for n in nodes if n.properties.get("media_kind") == "image"]
    assert not [e for e in edges if e.type == "DEPICTS"]
    # ADR-120 Amendment 16: nothing written is above OFFICIAL, and the covert-source conflict is
    # not among the links.
    assert {w.handling.classification for w in (*nodes, *edges)} == {"OFFICIAL"}
    assert not [e for e in edges if e.properties.get("reason") == "covert source"]


def test_the_scale_writes_are_exactly_30000_links(scale: Any) -> None:
    nodes, edges = _writes(scale, "chapter9", PID_SCALE.id)
    assert len(edges) == 30_000 and not [n for n in nodes if n.type == "Document"]
    assert {d for w in (*nodes, *edges) for d in w.datasets} == {PID_SCALE.id}


@pytest.mark.parametrize("profile", ["demo", "scale"])
def test_each_write_carries_the_plans_handling_provenance_dataset_and_audit(
    profile: str, demo: Any, scale: Any
) -> None:
    """Both profiles: the scale round trip takes `pid_writes(scale)` as its expected side."""
    plan, seed = (demo, PID) if profile == "demo" else (scale, PID_SCALE)
    nodes, edges = _writes(plan, "chapter9", seed.id)
    assert nodes and edges
    by_node = {pid_plan.node_id(e.key): e for e in plan.entities}
    by_edge = {pid_plan.link_id(lk): lk for lk in plan.links}
    source = f"{seed.source}:{seed.id}"
    for node in nodes:
        e = by_node[node.id]
        assert node.type == e.entity_type and node.datasets == [seed.id]
        assert node.handling.model_dump() == {
            **dataclasses.asdict(e.handling), "review_date": None, "legal_basis": None,
        }  # fmt: skip
        assert node.created_by == "pid-generator" and node.created_at == CREATED
        assert node.provenance.state is ProvenanceState.ASSERTED
        assert node.provenance.extracted_by is None and node.provenance.first_seen == CREATED
        (ref,) = node.provenance.sources
        assert (ref.document_id, ref.locator) == (source, e.key)
        assert ref.excerpt_hash == hashlib.sha256(e.key.encode()).hexdigest()
        want = {k: _text(v) for k, v in e.properties.items()}
        if e.entity_type == "Device":  # stored as the `imei` adapter makes it (tested apart)
            want["imei"] = imei(want["imei"])
        assert {k: _text(v) for k, v in node.properties.items()} == want
        assert not any(isinstance(v, date | datetime) for v in node.properties.values())
    inferred = []
    for edge in edges:
        lk = by_edge[edge.id]
        assert (edge.type, edge.occurrences) == (lk.link_type, lk.occurrences)
        assert edge.datasets == [seed.id]
        assert edge.source == pid_plan.node_id(lk.source)
        assert edge.target == pid_plan.node_id(lk.target)
        assert edge.handling.classification == lk.handling.classification
        assert (edge.handling.originator, edge.handling.owning_unit) == (
            lk.handling.originator, lk.handling.owning_unit,
        )  # fmt: skip
        assert edge.handling.action_code == lk.handling.action_code
        assert edge.handling.sanitisation_code == lk.handling.sanitisation_code
        assert edge.created_by == "pid-generator" and edge.created_at == CREATED
        assert edge.properties == {k: v for k, v in lk.properties.items()}
        (ref,) = edge.provenance.sources
        assert (ref.document_id, ref.locator) == (source, lk.key)
        assert ref.excerpt_hash == hashlib.sha256(lk.key.encode()).hexdigest()
        if lk.provenance == "inferred":
            inferred.append(edge)
            assert edge.provenance.state is ProvenanceState.INFERRED
            assert edge.provenance.extracted_by == lk.extracted_by
            assert edge.provenance.extraction_confidence == lk.extraction_confidence
        else:
            assert edge.provenance.state is ProvenanceState.ASSERTED
            assert edge.provenance.extracted_by is None
            assert edge.provenance.extraction_confidence is None
    if profile == "demo":
        assert len(inferred) == 5 and {e.type for e in inferred} == {"PASSES_ITEMS_TO"}
    else:
        assert inferred == [], "the scale cohort holds no inferred link"


def test_a_write_names_only_a_registered_pid_dataset_and_its_own_source(
    demo: Any, scale: Any
) -> None:
    for plan, seed in ((demo, PID), (scale, PID_SCALE)):
        nodes, edges = _writes(plan, "seed", seed.id)
        assert {s.document_id for w in (*nodes, *edges) for s in w.provenance.sources} == {
            f"{seed.source}:{seed.id}"
        }
    with pytest.raises(ValueError, match="not-a-pid-dataset"):
        pid_writes.writes(demo, "seed", dataset="not-a-pid-dataset", created_at=CREATED)


def test_a_handset_and_a_sim_are_written_as_the_knowledge_adapters_make_them(demo: Any) -> None:
    """R6 binds `imei` and `imsi`, so a Studio load stores their output: the 14-digit handset, not
    the written 15-digit form the plan and the files hold."""
    nodes, _ = _writes(demo, "chapter9")
    by_id = {pid_plan.node_id(e.key): e for e in demo.entities}
    handsets = [n for n in nodes if n.type == "Device"]
    sims = [n for n in nodes if n.properties.get("endpoint_kind") == "imsi"]
    assert len(handsets) == 9 and len(sims) == 9
    for node in handsets:
        written = str(by_id[node.id].properties["imei"])
        assert len(written) == 15 and node.properties["imei"] == imei(written)
        assert len(node.properties["imei"]) == 14
    for node in sims:
        written = str(by_id[node.id].properties["imsi"])
        assert node.properties["imsi"] == imsi(written)
        assert node.properties["value_normalised"] == imsi(written)
        assert node.properties["value_raw"] == by_id[node.id].properties["value_raw"]
    # Shown able to fail: the plan's own value is not the adapter's.
    assert all(str(by_id[n.id].properties["imei"]) != n.properties["imei"] for n in handsets)


def test_a_plan_is_not_written_into_the_other_profiles_dataset(demo: Any, scale: Any) -> None:
    """The scale cohort's elements would otherwise share a case with the demo's, or the reverse."""
    with pytest.raises(ValueError, match="scale plan"):
        pid_writes.writes(scale, "seed", dataset=PID.id, created_at=CREATED)
    with pytest.raises(ValueError, match="demo plan"):
        pid_writes.writes(demo, "seed", dataset=PID_SCALE.id, created_at=CREATED)


def test_every_link_interval_is_the_one_link_instants_gives(demo: Any) -> None:
    _, edges = _writes(demo, "chapter9")
    by_edge = {pid_plan.link_id(lk): lk for lk in demo.links}
    for edge in edges:
        want = _interval(demo, by_edge[edge.id])
        got = None if edge.interval is None else (edge.interval.valid_from, edge.interval.valid_to)
        assert got == want, (edge.type, by_edge[edge.id].key)
    # The cases each branch of the rule decides, by name (Amendment 10): a PIN account's calls are
    # placed week by week and still span the link's first day to its last; a carried link is dated
    # on its own day, at noon; an undated carried link has no interval; a custody is open.
    def one(link_type: str, source: str, target: str) -> Any:
        (lk,) = [
            x for x in demo.links
            if (x.link_type, x.source, x.target) == (link_type, source, target)
        ]  # fmt: skip
        (edge,) = [e for e in edges if e.id == pid_plan.link_id(lk)]
        return edge.interval

    call = one("COMMUNICATED_WITH", "pin:principal", "number:coordinator")
    assert (call.valid_from, call.valid_to) == (
        datetime(2025, 9, 1, tzinfo=UTC), datetime(2026, 4, 30, 23, 59, 59, tzinfo=UTC)
    )
    find = one("USES", "relay_1", "handset:find_01")
    noon = datetime(2026, 1, 5, 12, tzinfo=UTC)
    assert (find.valid_from, find.valid_to) == (noon, noon)
    assert one("USES", "principal", "pin:principal") is None
    held = one("HELD_AT", "principal", "est:fenwick-moor")
    assert held.valid_from == datetime(2024, 6, 3, tzinfo=UTC) and held.valid_to is None
    passes = one("PASSES_ITEMS_TO", "principal", "relay_1")
    assert (passes.valid_from, passes.valid_to) == (
        datetime(2026, 1, 12, tzinfo=UTC), datetime(2026, 4, 28, 23, 59, 59, tzinfo=UTC)
    )


def test_the_written_nodes_and_links_are_declared_in_the_composed_ontology(demo: Any) -> None:
    ontology = load_deployment_ontology()
    entity_defs = {t.name: t for t in ontology.entity_types}
    edge_defs = {t.name: t for t in ontology.edge_types}
    nodes, edges = _writes(demo, "chapter9")
    types = {n.id: n.type for n in nodes}
    problems = []
    for node in nodes:
        try:
            validate_properties(entity_defs[node.type], dict(node.properties))
        except Exception as exc:
            problems.append(f"{node.id}: {exc}")
    for edge in edges:
        try:
            validate_properties(edge_defs[edge.type], dict(edge.properties))
            validate_edge_endpoints(
                edge_defs[edge.type], source_type=types[edge.source], target_type=types[edge.target]
            )
        except Exception as exc:
            problems.append(f"{edge.id}: {exc}")
    assert not problems, f"{len(problems)} problems, first: {problems[:5]}"


def test_picture_writes_pair_each_subjects_node_id_with_its_name_and_bytes(
    demo: Any, scale: Any, pictures: list[tuple[str, str, bytes]]
) -> None:
    assert [node for node, _, _ in pictures] == [pid_plan.node_id(s) for s in demo.picture_subjects]
    nodes, _ = _writes(demo, "chapter9")
    assert {node for node, _, _ in pictures} <= {n.id for n in nodes}
    assert pid_writes.picture_writes(scale) == []
    assert all(isinstance(d, bytes) and d.startswith(b"\x89PNG") for _, _, d in pictures)


# --- The circle (Amendment 7 decision 2), as the live access test writes it ---------------------

#: The links the amendment names, by (type, source key, target key): the call link, the payer's
#: three transfers, the one-week cell share and the principal's picture. The live access test reads
#: the same constants from `pid_writes`.
_CALL = pid_writes.CIRCLE_CALL
_TRANSFERS = pid_writes.CIRCLE_TRANSFERS
_ONE_WEEK_SHARE = pid_writes.CIRCLE_ONE_WEEK_SHARE
_PICTURE = pid_writes.CIRCLE_PICTURE
#: The amendment's own list of the circle's centre, written out here and not read from
#: `circle_links`: the principal, each endpoint he uses, and each endpoint those exchange with.
_CENTRE = frozenset(
    {
        "principal", "pin:principal", "cash:principal",
        "number:coordinator", "number:unidentified", "account:payer",
    }
)  # fmt: skip


def _ends(links: Iterable[Any]) -> set[tuple[str, str, str]]:
    return {(lk.link_type, lk.source, lk.target) for lk in links}


@pytest.mark.parametrize("moment", ["seed", "chapter4"])
def test_the_circle_is_the_principals_payment_and_call_circle_as_the_analyst_sees_it(
    moment: str, demo: Any
) -> None:
    centre, links = pid_writes.circle_links(demo, moment)
    # The amendment's own list: his own links, every link of each endpoint he uses (his PIN
    # account and his private-cash account), and every link of each endpoint those exchange calls
    # or money with (the coordinator's number, the unidentified number, the payer's account).
    assert centre == _CENTRE
    # About 58 links at the seed and about 62 after chapter 4 (Amendment 8 decision 9).
    assert len(links) == {"seed": 58, "chapter4": 62}[moment]
    ends = _ends(links)
    assert {_CALL, *_TRANSFERS, _ONE_WEEK_SHARE, _PICTURE} <= ends
    # The step that reaches a partner's own links: the payer's `USES` of his account touches
    # neither the principal nor an account he uses, only a partner of one.
    assert ("USES", "payer", "account:payer") in ends
    for relay in ("relay_1", "relay_2", "relay_3"):
        assert ("COMMUNICATED_WITH", f"pin:{relay}", "number:coordinator") in ends
    # The principal and calder_3 share no recorded conflict (ADR-120 Amendment 16), and nothing in
    # the circle is above OFFICIAL.
    assert ("IN_CONFLICT_WITH", "principal", "calder_3") not in ends
    assert not [lk for lk in links if lk.handling.classification != "OFFICIAL"]
    # Every link touches the centre, and every visible link that touches it is there.
    assert all(lk.source in _CENTRE or lk.target in _CENTRE for lk in links)
    visible = pid_plan.links_at(demo, moment, secret_cleared=False)
    assert _ends(links) == _ends(
        lk for lk in visible if lk.source in _CENTRE or lk.target in _CENTRE
    )
    assert len(links) == len({lk.key for lk in links})
    # No reports at the seed, whatever the circle holds.
    if moment == "seed":
        assert not [lk for lk in links if lk.link_type == "MENTIONED_IN"]


def test_the_circle_of_a_plan_with_no_principal_is_refused(scale: Any) -> None:
    with pytest.raises(KeyError):
        pid_writes.circle_links(scale, "seed")


@pytest.mark.parametrize("moment", ["seed", "chapter4"])
def test_the_circle_writes_are_the_circles_links_and_their_end_nodes_and_nothing_else(
    moment: str, demo: Any
) -> None:
    nodes, edges = pid_writes.circle_writes(demo, moment, dataset=PID.id, created_at=CREATED)
    _, links = pid_writes.circle_links(demo, moment)
    written_nodes, written_edges = _writes(demo, moment)
    # The picture route writes DEPICTS, so the circle's writes hold every other circle link.
    want = {pid_plan.link_id(lk): lk for lk in links if lk.link_type != "DEPICTS"}
    assert {e.id for e in edges} == set(want) and len(edges) == len(want)
    assert len(edges) == len(links) - 1, "only the principal's picture link is left out"
    # Each is the very write `writes` makes, so a store loaded from them weighs the same.
    by_id = {e.id: e for e in written_edges}
    assert all(e == by_id[e.id] for e in edges)
    ends = {pid_plan.node_id(k) for lk in want.values() for k in (lk.source, lk.target)}
    assert {n.id for n in nodes} == ends and len(nodes) == len(ends)
    by_node = {n.id: n for n in written_nodes}
    assert all(n == by_node[n.id] for n in nodes)
    assert not [n for n in nodes if n.properties.get("media_kind") == "image"]
    assert not [e for e in edges if e.handling.classification == "SECRET"]
    assert {d for w in (*nodes, *edges) for d in w.datasets} == {PID.id}
    with pytest.raises(ValueError):
        pid_writes.circle_writes(demo, moment, dataset="not-a-pid-dataset", created_at=CREATED)


# --- The report and the manifest ---------------------------------------------------------------


def _verify_manifest(written: Written) -> dict[str, Any]:
    manifest = json.loads((written.out / "manifest.json").read_text(encoding="utf-8"))
    on_disk = sorted(
        p.relative_to(written.out).as_posix()
        for p in written.out.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    )
    assert sorted([*manifest["files"], *manifest["pictures"]]) == on_disk
    for name, record in {**manifest["files"], **manifest["pictures"]}.items():
        data = (written.out / name).read_bytes()
        assert record["bytes"] == len(data), name
        assert record["sha256"] == hashlib.sha256(data).hexdigest(), name
        if name in manifest["files"]:
            with (written.out / name).open(newline="", encoding="utf-8") as handle:
                assert record["rows"] == sum(1 for _ in csv.reader(handle)) - 1, name
        else:
            assert "rows" not in record, name
    return manifest  # type: ignore[no-any-return]


def test_the_manifest_holds_rows_bytes_and_sha256_for_every_file_and_no_timestamp(
    demo_out: Written, scale_out: Written
) -> None:
    for written in (demo_out, scale_out):
        manifest = _verify_manifest(written)
        assert manifest["profile"] == written.plan.profile and manifest["seed"] == written.plan.seed
        assert manifest["reproducible_on"]["python"] == sys.version.split()[0]
        assert manifest["reproducible_on"]["zlib"] == zlib.ZLIB_RUNTIME_VERSION
        assert "1-based" in manifest["row_positions"] and "header" in manifest["row_positions"]
        assert "byte-identical" in manifest["reproducible_on"]["note"]
        text = json.dumps(manifest)
        assert not re.search(r"\d{4}-\d{2}-\d{2}", text), "a date in the manifest"
        assert not re.search(r'"(?:created|modified|written|time|timestamp)\w*"', text)
        report = written.report
        assert (written.out / "manifest.json").read_text(encoding="utf-8") == report.manifest
        assert {f.name: f.rows for f in report.files} == {
            n: r["rows"] for n, r in manifest["files"].items()
        }
        assert {f.name: f.sha256 for f in report.pictures} == {
            n: r["sha256"] for n, r in manifest["pictures"].items()
        }
        assert json.loads(json.dumps(report.planted)) == manifest["planted"]
    assert manifest["pictures"] == {}
    demo_manifest = json.loads((demo_out.out / "manifest.json").read_text(encoding="utf-8"))
    assert len(demo_manifest["pictures"]) == 1_633
    assert demo_manifest["files"][CALLS]["rows"] == CALL_ROWS + 80
    planted = demo_manifest["planted"]
    assert planted[REPORTS] == {
        "teaching_phone_row": TEACHING_ROW,
        "teaching_phone_report": _ir(demo_out.plan, pid_plan.PID_TEACHING_REPORT),
        "three_letter_initials_row": INITIALS_ROW,
    }
    assert len(planted[CALLS]["exact_duplicate_rows"]) == EXACT_DUPLICATES
    assert len(planted[CALLS]["sequence_duplicate_rows"]) == SEQUENCE_DUPLICATES


def test_two_runs_are_byte_identical(
    demo_out: Written, demo_again: Written, scale: Any, scale_out: Written, tmp_path: Path
) -> None:
    first, second = _verify_manifest(demo_out), _verify_manifest(demo_again)
    assert first == second
    assert demo_out.report == demo_again.report
    assert (demo_out.out / "manifest.json").read_bytes() == (
        demo_again.out / "manifest.json"
    ).read_bytes()
    again = pid_files.write_files(scale, tmp_path / "again")
    assert again == scale_out.report
    for path in sorted(scale_out.out.rglob("*")):
        if path.is_file():
            twin = tmp_path / "again" / path.relative_to(scale_out.out)
            assert path.read_bytes() == twin.read_bytes()


# --- The script --------------------------------------------------------------------------------


def _repository_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    raise AssertionError("not inside a git working tree")


def test_the_script_requires_out_and_refuses_a_path_inside_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as missing:
        write_pid_files.main([])
    assert missing.value.code == 2
    root = _repository_root()
    link = tmp_path / "into_the_repository"
    link.symlink_to(root, target_is_directory=True)
    for inside in (root / "pid_files_never_written", root, link / "pid_files_never_written"):
        capsys.readouterr()
        assert write_pid_files.main(["--out", str(inside), "--profile", "scale"]) == 2
        assert "inside the repository" in capsys.readouterr().err
    assert not (root / "pid_files_never_written").exists()
    # Shown able to fail: a path outside the working tree is accepted and written.
    outside = tmp_path / "scale_files"
    assert write_pid_files.main(["--out", str(outside), "--profile", "scale"]) == 0
    printed = capsys.readouterr().out
    assert (outside / "manifest.json").exists() and "scale_pid_nomis_prisoners.csv" in printed
    assert not (outside / "contact_sheet.png").exists(), "the scale profile has no pictures"


def test_the_script_writes_a_contact_sheet_of_the_specified_sample(
    demo: Any, tmp_path: Path
) -> None:
    sample = write_pid_files.picture_sample(demo)
    expected_start = ["principal", "brother", "coordinator"]
    assert sample[:3] == expected_start and len(sample) == 18 and len(set(sample)) == 18
    kinds = Counter(_kind_of(demo, k) for k in sample)
    assert kinds == {
        "person": 9, "establishment": 3, "yard": 2, "wing": 1, "handset": 1, "group": 2,
    }  # fmt: skip
    hotspots = {f"yard:{c}" for c in pid_plan.HOTSPOT_YARDS}
    assert len(hotspots & set(sample)) == 1, "one hotspot yard and one ordinary yard"
    # Its own folder, holding only the sample's pictures as `pictures/` would.
    only = dataclasses.replace(demo, picture_subjects=tuple(sample))
    written = pid_writes.picture_writes(only)
    folder = tmp_path / "pictures"
    folder.mkdir()
    for _, name, data in written:
        (folder / name).write_bytes(data)
    sheet = write_pid_files.write_contact_sheet(demo, tmp_path)
    assert sheet == tmp_path / "contact_sheet.png"
    width, height, depth, colour, raw = decode_png(sheet.read_bytes())
    assert (width, height, depth, colour) == (768, 384, 8, 2)
    # The tiles are the sample's pictures, in the sample's order.
    for index, (_, _, data) in enumerate(written):
        assert _tile_of(raw, index) == _shrunk(data), sample[index]
    assert _tile_of(raw, 0) != _tile_of(raw, 1)


# --- the estate file's order: a place is written before any row that names it --------------------

_PLACE_REFERENCES = ("parent_ref", "parent_ref_2", "adjoins_ref", "used_by_ref")


def _order_problems(rows: Sequence[Mapping[str, str]]) -> list[str]:
    """Each place a row names (its parent, its zone, the wing it adjoins, the wing that uses it) that
    is not yet a row written: a recipe that finds the place by reference (R11, ADR-127 decision 12)
    would make it bare, and its own row would then find that and never write its name and point."""
    written: set[str] = set()
    problems: list[str] = []
    for row in rows:
        for column in _PLACE_REFERENCES:
            named = row[column]
            if named and named not in written:
                problems.append(f"{row['place_ref']}: {column} names {named}, not yet written")
        written.add(row["place_ref"])
    return problems


def test_the_estate_file_writes_every_place_before_any_row_that_names_it(
    demo_out: Written,
) -> None:
    rows = list(demo_out.rows(ESTATE))
    assert len(rows) > 500
    assert _order_problems(rows) == []
    # Shown able to fail: the zone moved to the end, and a wing moved after its landings.
    zone = next(r for r in rows if r["place_kind"] == "zone")
    moved = [r for r in rows if r is not zone] + [zone]
    assert any("zone" in p or zone["place_ref"] in p for p in _order_problems(moved))
    wing = next(r for r in rows if r["place_kind"] == "wing" and r["parent_ref_2"] == "")
    late = [r for r in rows if r is not wing] + [wing]
    assert any(wing["place_ref"] in p for p in _order_problems(late))
