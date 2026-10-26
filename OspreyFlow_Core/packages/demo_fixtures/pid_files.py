"""The Prison Intelligence Dataset's generated files (ADR-120 D4 to D9 and Amendments 9 to 12;
Brief 2 sections 3.4, 4 and 5).

`write_files(plan, out_dir)` is the only function here that writes. It serialises what
`pid_plan.rows_for` yields, one CSV per file the plan's load shapes name, and adds the columns the
plan's rows do not carry. The files are written under `out_dir`, never anywhere else:

- `incoming/` holds the chapter 9 seized-comms batch (Brief 2 R6: loaded by the demo, not the seed);
  the scale profile's files are prefixed `scale_`; a file the plan has no rows for is not written;
- `pictures/` holds one PNG per picture subject (`pid_writes.picture_writes`);
- `manifest.json` holds rows, bytes and SHA-256 per file and the planted counts, as written, and
  their 1-based row positions. It carries no timestamp. Byte-identical means on one interpreter and
  one `zlib` runtime, which the manifest records.

Files are written with `csv.writer`, UTF-8, `\\n` line ends and one header row.

**Columns.** A file's header is `pid_plan.file_header(file)` (the columns its load shapes and entity
shapes name, in Brief 2's names, in first-seen order), then `EXTRAS[file]`, the few columns Brief 2
names for a value no shape holds, then the six handling columns where the contract
(`handling="column"`) says the file carries them, in every profile (Amendment 12 decision 3). A
column the plan holds no value for (R10's `recovered`, R12's `role`, R9's subject roles) is in the
header and left empty. An entity's property cells come from its shape's `names` table.

**Numbers.** An outside number's first row in each file that names it is written in the plan's own
form (`value_raw`), so whichever recipe runs first creates the endpoint as the plan holds it. The
seized and number-owner files write every row so; the call file mixes forms (below); the one
exception is the reports file's teaching row.

**References.** A report's `report_ref` is its IR reference as its text shows it (`IR 0263`), in
every file that names a report; the plan's key is never written. Rows stay in plan-key order.

**The call file's mess** (Brief 2 section 3.4), drawn from `Random(seed)` and so the same on every
run. Over the 1,000,000 distinct calls: exactly 10,000 each in `+44 7700 900123`,
`0044 7700 900123` and `447700900123` form (every outside number appears in all three, and its first
row is always the plan's own national form), the rest national; then 40 rows copying an earlier row
byte for byte and 40 repeating an earlier call with a new `sequence` above the maximum, each placed
after its original. `duration_s` is seeded between 20 and 1,800 and redrawn where two calls of one
link would share their start and duration, so no two distinct calls share Brief 2's key.

**A report's subjects** (ADR-120 Amendment 15): `subject_1` to `subject_3` hold prison numbers only.
An outside subject's National Insurance number is written in `subject_N_nino` for the same slot,
that row's `subject_N` left empty, and the names and date of birth sit in `subject_N_*` beside it.

**The reports file's two teaching rows** (Brief 2 section 5), in the same positions every run: row
17 (`PID_TEACHING_REPORT`) carries the number `07700 900 6O3` in `phone_mentioned` and names it
in its text, and every row carries two letters in `reviewer_initials`, row 101 three.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from . import pid_writes
from .pid_plan import (
    HANDLING_COLUMNS,
    LOAD_SHAPES,
    PID_TEACHING_BAD_NUMBER,
    PID_TEACHING_REPORT,
    Moment,
    Plan,
    PlanEntity,
    PlanRow,
    cell_text,
    entity_shape,
    file_header,
    rows_for,
)

CALLS = "pid_pin_calls.csv"
REPORTS = "pid_intel_reports.csv"
REPORT_INCIDENTS = "pid_report_incidents.csv"
BATCH_1 = "pid_seized_comms_batch1.csv"
BATCH_2 = "pid_seized_comms_batch2.csv"
OWNERS = "pid_number_owners.csv"
ESTATE = "pid_establishment_plan.csv"
MANIFEST = "manifest.json"
#: Distinct calls written in each of the three international forms; and the planted duplicates.
FORM_COUNT = 10_000
EXACT_DUPLICATES = 40
SEQUENCE_DUPLICATES = 40
TEACHING_INITIALS_ROW = 101
DURATION_RANGE = (20, 1_800)
_PSEUDO = frozenset({"graph port", "picture route"})
#: The column of each file that names an outside number, written in the plan's own form.
_NUMBER_COLUMNS = {BATCH_1: "other_number", BATCH_2: "other_number", OWNERS: "number"}
_IR = re.compile(r"IR \d+")



class SeedStage(NamedTuple):
    """One load of the seed: a source file, the recipe that reads it and the moment it loads at
    (`pid_plan.Moment`: "seed" before the analyst begins, "chapter4" and "chapter9" live)."""

    file: str
    recipe: str
    moment: Moment


#: The order the seed loads every source file, each with its recipe (ADR-127 Amendment 23): R11, R1,
#: R14, R2, R3, R4, R16, R12, R13, R8, R15, R5, R7, R6 batch 1, R10; then at the chapter-4 moment R9
#: and R17; then at chapter 9 R6 batch 2. Batch 1 and batch 2 are separate stages of one recipe. The
#: seed, and a test that loads a recipe's references, load in this order or a subsequence of it.
SEED_ORDER: tuple[SeedStage, ...] = (
    SeedStage("pid_establishment_plan.csv", "pid_establishment_plan_recipe.yaml", "seed"),
    SeedStage("pid_nomis_prisoners.csv", "pid_nomis_prisoners_recipe.yaml", "seed"),
    SeedStage("pid_nomis_cell_stays.csv", "pid_nomis_cell_stays_recipe.yaml", "seed"),
    SeedStage("pid_nomis_cell_shares.csv", "pid_nomis_cell_shares_recipe.yaml", "seed"),
    SeedStage("pid_nomis_visits.csv", "pid_nomis_visits_recipe.yaml", "seed"),
    SeedStage("pid_nomis_incidents.csv", "pid_nomis_incidents_recipe.yaml", "seed"),
    SeedStage("pid_number_owners.csv", "pid_number_owners_recipe.yaml", "seed"),
    SeedStage("pid_soc_nominals.csv", "pid_soc_nominals_recipe.yaml", "seed"),
    SeedStage("pid_family_and_associates.csv", "pid_family_and_associates_recipe.yaml", "seed"),
    SeedStage("pid_codefendants.csv", "pid_codefendants_recipe.yaml", "seed"),
    SeedStage("pid_conflicts.csv", "pid_conflicts_recipe.yaml", "seed"),
    SeedStage(CALLS, "pid_pin_calls_recipe.yaml", "seed"),
    SeedStage("pid_prisoner_money.csv", "pid_prisoner_money_recipe.yaml", "seed"),
    SeedStage(BATCH_1, "pid_seized_comms_recipe.yaml", "seed"),
    SeedStage("pid_throwover_log.csv", "pid_throwover_log_recipe.yaml", "seed"),
    SeedStage(REPORTS, "pid_intel_reports_recipe.yaml", "chapter4"),
    SeedStage(REPORT_INCIDENTS, "pid_report_incidents_recipe.yaml", "chapter4"),
    SeedStage(BATCH_2, "pid_seized_comms_recipe.yaml", "chapter9"),
)


def seed_stages(*moments: Moment) -> tuple[SeedStage, ...]:
    """The stages of `SEED_ORDER` at the given moments, in order: `seed_stages("seed")` is the
    seed's own part, before the analyst begins."""
    return tuple(stage for stage in SEED_ORDER if stage.moment in moments)


#: The columns added after the shapes' own: Brief 2 names each, and no shape holds it.
EXTRAS: dict[str, tuple[str, ...]] = {
    CALLS: ("duration_s", "direction", "sequence"),
    BATCH_1: ("kind", "duration_s"),
    BATCH_2: ("kind", "duration_s"),
    "pid_prisoner_money.csv": ("payer_family_name", "payer_given_names"),
    "pid_family_and_associates.csv": ("kind",),
    REPORTS: ("reviewer_initials",),
}


@dataclass(frozen=True)
class FileRecord:
    name: str  # relative to the output folder, with `/` separators
    rows: int | None  # data rows of a CSV; `None` for a picture
    bytes: int
    sha256: str


@dataclass(frozen=True)
class WriteReport:
    profile: str
    seed: int
    files: tuple[FileRecord, ...]
    pictures: tuple[FileRecord, ...]
    #: The planted counts, as written, and 1-based data-row positions, per file.
    planted: dict[str, Any]
    #: The text of `manifest.json`.
    manifest: str


def output_name(profile: str, file: str) -> str:
    if profile == "scale":
        return f"scale_{file}"
    return f"incoming/{file}" if file == BATCH_2 else file


def header_for(file: str) -> list[str]:
    """The plan's shapes' columns, then `EXTRAS`, then the handling columns the contract gives."""
    shaped = list(file_header(file))
    handling = [c for c in shaped if c in HANDLING_COLUMNS]
    plain = [c for c in shaped if c not in HANDLING_COLUMNS]
    return [*plain, *(c for c in EXTRAS.get(file, ()) if c not in plain), *handling]


def _unit(seed: int, *parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in (seed, *parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _place_kind(entity: PlanEntity) -> str:
    if entity.entity_type == "Establishment":
        return "establishment"
    return str(entity.properties["site_ref"]).split(":")[-2]


class _Context:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.links = {lk.key: lk for lk in plan.links}
        self.place_kind = {
            str(e.properties.get("site_ref", e.properties.get("establishment_ref"))): _place_kind(e)
            for e in plan.entities
            if e.entity_type in ("Location", "Establishment")
        }
        self.raw_of = {
            str(e.properties["value_normalised"]): str(e.properties["value_raw"])
            for e in plan.entities
            if e.properties.get("endpoint_kind") == "msisdn"
        }
        self.ir_of: dict[str, str] = {}
        for key, text in plan.report_texts.items():
            found = _IR.match(text)
            if found is None:
                raise ValueError(f"{key}'s text does not begin with its IR reference")
            self.ir_of[key] = found.group()
        if len(set(self.ir_of.values())) != len(self.ir_of):
            raise ValueError("two reports share an IR reference")

    def entity(self, key: str) -> PlanEntity:
        return self.plan.entity(key)


def _entity_cells(ctx: _Context, file: str, row: PlanRow) -> dict[str, str]:
    """The cells an entity shape's `names` give each property of the entities a row writes. A row
    of the reports or the estate is one entity's own (its first); the places it links to are other
    rows."""
    cells: dict[str, str] = {}
    for key in row.entities[:1] if file in (REPORTS, ESTATE) else row.entities:
        entity = ctx.entity(key)
        shape = entity_shape(ctx.plan, key)
        for prop, value in entity.properties.items():
            column = shape.names.get(prop, prop)
            if column is not None:
                cells[column] = cell_text(value)
    return cells


def _extras(file: str, ctx: _Context, row: PlanRow, number: int) -> dict[str, str]:
    """The cells the shapes' names do not give (`number` is the row's 1-based position)."""
    first = ctx.entity(row.entities[0]) if row.entities else None
    if file == "pid_prisoner_money.csv":
        for key in row.links[1:]:
            owner = ctx.entity(ctx.links[key].source)
            if owner.entity_type == "Person" and "prison_number" not in owner.properties:
                return {
                    "payer_family_name": str(owner.properties["family_name"]),
                    "payer_given_names": str(owner.properties["given_names"]),
                }
        return {}
    if file == "pid_family_and_associates.csv":
        return {"kind": ctx.links[row.links[0]].link_type}
    if file in (BATCH_1, BATCH_2):
        rng = _unit(ctx.plan.seed, file, number)
        if rng.randrange(2):
            return {"kind": "call", "duration_s": str(rng.randint(*DURATION_RANGE))}
        return {"kind": "text", "duration_s": ""}
    if file == ESTATE and first is not None:
        parent = row.values.get("parent_ref", "")
        return {
            "place_kind": _place_kind(first),
            "parent_kind": ctx.place_kind.get(parent, ""),
        }
    if file == REPORTS and first is not None:
        return _report_cells(ctx, row, first, number)
    return {}


def _report_cells(ctx: _Context, row: PlanRow, report: PlanEntity, number: int) -> dict[str, str]:
    plan = ctx.plan
    text = plan.report_texts[report.key]
    if report.key == PID_TEACHING_REPORT:
        text = f"{text} Number given: {PID_TEACHING_BAD_NUMBER}."
    digest = hashlib.sha256(f"{plan.seed}|initials|{report.key}".encode()).digest()
    width = 3 if number == TEACHING_INITIALS_ROW else 2
    cells = {
        "report_ref": ctx.ir_of[report.key],
        "report_text": text,
        "reviewer_initials": "".join(chr(65 + digest[i] % 26) for i in range(width)),
    }
    for key in row.entities[1:]:
        outsider = ctx.entity(key)
        if outsider.entity_type != "Person":
            continue
        extra = set(outsider.properties) - {"family_name", "given_names", "date_of_birth", "nino"}
        if extra:
            raise ValueError(f"{key} has properties the reports file has no column for: {extra}")
        slot = next(
            (
                i
                for i in (1, 2, 3)
                if row.values.get(f"subject_{i}_nino") == outsider.properties["nino"]
            ),
            None,
        )
        if slot is None:
            raise ValueError(f"{key} is written by a report row that does not name them")
        for name in ("family_name", "given_names", "date_of_birth"):
            cells[f"subject_{slot}_{name}"] = cell_text(outsider.properties[name])
    return cells


# --- The call file -------------------------------------------------------------------------------


@dataclass
class _CallPlan:
    """What is planted in the call file, decided before the first row is written."""

    total: int
    forms: dict[int, int]  # call index -> 0 (+44), 1 (0044), 2 (bare 44)
    exact: list[int]  # original call indexes, in the order they are copied
    sequence: list[int]
    after: dict[int, list[tuple[str, int]]]  # call index -> duplicates written straight after it


def _written(raw: str, form: int) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    return (f"+44 {raw[1:]}", f"0044 {raw[1:]}", f"44{digits[1:]}")[form]


def _form_name(written: str) -> str:
    if written.startswith("+44 "):
        return "plus_44"
    if written.startswith("0044 "):
        return "zero_zero_44"
    return "bare_44" if written.startswith("44") else "national"


def _plan_calls(plan: Plan) -> _CallPlan:
    positions: dict[str, list[int]] = defaultdict(list)
    total = 0
    for row in rows_for(plan, CALLS):
        positions[row.values["called_number"]].append(total)
        total += 1
    rng = random.Random(plan.seed * 7_919 + 1)
    forms: dict[int, int] = {}
    # Every number is written each of the three international ways at least once, never on its
    # first row, so a number's first row is always its own national form.
    for number in sorted(positions):
        for form, index in enumerate(rng.sample(positions[number][1:], 3)):
            forms[index] = form
    taken = set(forms) | {indexes[0] for indexes in positions.values()}
    rest = [i for i in range(total) if i not in taken]
    for form in range(3):
        need = FORM_COUNT - sum(1 for f in forms.values() if f == form)
        chosen = rng.sample(rest, need)
        chosen_set = set(chosen)
        rest = [i for i in rest if i not in chosen_set]
        forms.update(dict.fromkeys(chosen, form))
    originals = rng.sample(range(total - 1), EXACT_DUPLICATES + SEQUENCE_DUPLICATES)
    exact, sequence = originals[:EXACT_DUPLICATES], originals[EXACT_DUPLICATES:]
    after: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for kind, group in (("exact", exact), ("sequence", sequence)):
        for original in group:
            after[rng.randrange(original + 1, total)].append((kind, original))
    return _CallPlan(total, forms, exact, sequence, dict(after))


def _call_rows(
    ctx: _Context, header: list[str], planted: dict[str, Any]
) -> Iterator[list[str]]:
    plan = ctx.plan
    calls = _plan_calls(plan)
    column = {name: i for i, name in enumerate(header)}
    duration_rng = random.Random(plan.seed * 104_729 + 3)
    originals = set(calls.exact) | set(calls.sequence)
    kept: dict[int, list[str]] = {}
    position_of: dict[int, int] = {}
    seen: set[tuple[str, int]] = set()
    current = ""
    position = 0
    sequence_next = calls.total + 1
    written_forms: Counter[str] = Counter()
    exact_rows: list[int] = []
    exact_of: list[int] = []
    sequence_rows: list[int] = []
    sequence_of: list[int] = []
    for index, row in enumerate(rows_for(plan, CALLS)):
        if row.links[0] != current:
            current, seen = row.links[0], set()
        start = row.values["call_start"]
        duration = duration_rng.randint(*DURATION_RANGE)
        while (start, duration) in seen:
            duration = duration_rng.randint(*DURATION_RANGE)
        seen.add((start, duration))
        values = dict(row.values)
        raw = ctx.raw_of[values["called_number"]]
        form = calls.forms.get(index)
        values["called_number"] = raw if form is None else _written(raw, form)
        written_forms[_form_name(values["called_number"])] += 1
        values["duration_s"] = str(duration)
        values["direction"] = "outbound"
        values["sequence"] = str(index + 1)
        cells = [values.get(name, "") for name in header]
        position += 1
        if index in originals:
            kept[index] = cells
            position_of[index] = position
        yield cells
        for kind, original in calls.after.get(index, ()):
            copy = list(kept[original])
            position += 1
            if kind == "exact":
                exact_rows.append(position)
                exact_of.append(position_of[original])
            else:
                copy[column["sequence"]] = str(sequence_next)
                sequence_next += 1
                sequence_rows.append(position)
                sequence_of.append(position_of[original])
            yield copy
    planted[CALLS] = {
        "distinct_calls": calls.total,
        "form_counts": dict(sorted(written_forms.items())),
        "exact_duplicate_rows": exact_rows,
        "exact_duplicate_of": exact_of,
        "sequence_duplicate_rows": sequence_rows,
        "sequence_duplicate_of": sequence_of,
    }


# --- Writing -------------------------------------------------------------------------------------


def _digest(path: Path) -> tuple[int, str]:
    sha, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        while block := handle.read(1 << 20):
            sha.update(block)
            size += len(block)
    return size, sha.hexdigest()


def ordered_rows(plan: Plan, file: str) -> Iterator[PlanRow]:
    """The plan's rows of a file in the order the writer writes them, so a test that replays what a
    load does with them (which row first names an element) replays the file's own order."""
    plan_rows = rows_for(plan, file)
    if file == ESTATE:
        # A place a later row names as a parent (the zone: `parent_ref_2`) is written before every
        # row that names it, so a recipe that references it finds it with its name and point rather
        # than making it bare and leaving its own row to find that (ADR-127 decision 12, R11).
        planned = list(plan_rows)
        named = {r.values.get("parent_ref_2") for r in planned} - {None, ""}
        return iter(
            [r for r in planned if r.values.get("place_ref") in named]
            + [r for r in planned if r.values.get("place_ref") not in named]
        )
    return plan_rows


def _csv_rows(
    ctx: _Context, file: str, header: list[str], planted: dict[str, Any]
) -> Iterator[list[str]]:
    if file == CALLS:
        yield from _call_rows(ctx, header, planted)
        return
    refs: list[str] = []
    for number, row in enumerate(ordered_rows(ctx.plan, file), start=1):
        values = {**row.values, **_entity_cells(ctx, file, row), **_extras(file, ctx, row, number)}
        if file == REPORT_INCIDENTS:
            values["report_ref"] = ctx.ir_of[row.values["report_ref"]]
        if file == REPORTS:
            refs.append(values["report_ref"])
        column = _NUMBER_COLUMNS.get(file)
        if column is not None and values[column] in ctx.raw_of:
            values[column] = ctx.raw_of[values[column]]
        yield [values.get(name, "") for name in header]
    if file == REPORTS:
        teaching = ctx.ir_of[PID_TEACHING_REPORT]
        planted[REPORTS] = {
            "teaching_phone_row": refs.index(teaching) + 1,
            "teaching_phone_report": teaching,
            "three_letter_initials_row": TEACHING_INITIALS_ROW,
        }


def _write_csv(path: Path, header: list[str], rows: Iterator[list[str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        for cells in rows:
            writer.writerow(cells)
            count += 1
    return count


def _manifest(plan: Plan, files: list[FileRecord], pictures: list[FileRecord], planted: Any) -> str:
    body = {
        "profile": plan.profile,
        "seed": plan.seed,
        "reproducible_on": {
            "python": sys.version.split()[0],
            "zlib": zlib.ZLIB_RUNTIME_VERSION,
            "note": (
                "The files are byte-identical on the same interpreter and zlib runtime; the "
                "pictures' compressed bytes can differ under another zlib."
            ),
        },
        "row_positions": "1-based data rows of the file, the header row excluded",
        "files": {f.name: {"rows": f.rows, "bytes": f.bytes, "sha256": f.sha256} for f in files},
        "pictures": {p.name: {"bytes": p.bytes, "sha256": p.sha256} for p in pictures},
        "planted": planted,
    }
    return json.dumps(body, indent=2, sort_keys=True) + "\n"


def write_files(plan: Plan, out_dir: Path) -> WriteReport:
    """Writes the plan's CSV files, its pictures and `manifest.json` under `out_dir`, and reports
    what it wrote. Existing files of the same names are overwritten."""
    out_dir.mkdir(parents=True, exist_ok=True)
    names = sorted({sh.file for sh in LOAD_SHAPES} - _PSEUDO)
    ctx = _Context(plan)
    planted: dict[str, Any] = {}
    files: list[FileRecord] = []
    for file in names:
        if next(iter(rows_for(plan, file)), None) is None:
            continue
        header = header_for(file)
        name = output_name(plan.profile, file)
        path = out_dir / name
        count = _write_csv(path, header, _csv_rows(ctx, file, header, planted))
        size, sha = _digest(path)
        files.append(FileRecord(name, count, size, sha))
    pictures: list[FileRecord] = []
    for _, picture_name, data in pid_writes.picture_writes(plan):
        path = out_dir / "pictures" / picture_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        pictures.append(FileRecord(f"pictures/{picture_name}", None, len(data), sha))
    files.sort(key=lambda f: f.name)
    text = _manifest(plan, files, pictures, planted)
    (out_dir / MANIFEST).write_text(text, encoding="utf-8")
    return WriteReport(plan.profile, plan.seed, tuple(files), tuple(pictures), planted, text)


__all__ = [
    "FileRecord",
    "WriteReport",
    "header_for",
    "ordered_rows",
    "output_name",
    "write_files",
]
