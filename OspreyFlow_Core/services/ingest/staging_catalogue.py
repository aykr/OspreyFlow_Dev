"""The staging catalogue's engine (ADR-140 decision 11; `09_INGEST_STUDIO.md` §9; the redesign's
phase 7; `schemas/staging.py` has the step records).

A pipeline's source tables, and the reference lists it looks up, go in; the recipe's `staging:`
steps run over them in order; the last step's table is what Map reads. Every staged row carries its
**refs**: one per input row it came from, each naming the source (or list), the row's position in
it, the row's identity (its key, or its hash) and the load that read it. A Join's row carries both
sides', a Union's its own, a Dedupe's survivor every repeat's, a Lookup's the list row it took
values from. `map_input` turns the last table into the rows Map reads and, for each, the
`SourceRef`s the element it becomes records in `provenance.sources` (the orchestrator's settlement
of 8 November 2026, Q2 (a)).

**Closed** (rule 8): every value-changing part of a step is a Knowledge Adapter with a golden file
(a key's `normalise` from `knowledge_adapters.REGISTRY`, a Derive's operation from
`knowledge_adapters.derive`); nothing here evaluates text as code.

**Nothing lost silently** (rule 2): a row a step does not pass on is either counted in the step's
report (`StepReport`: unmatched, filtered out, repeats folded) or rejected with its cause
(`StagingRejection`: a key or a cell an adapter refused), never dropped without a word.

**Reference lists** (ADR-140 decision 4; Amendment 9 decision 3): a Lookup reads a list of the
pipeline's own dataset, or a screening list the dataset subscribes to, and nothing else. A list of
another dataset is refused in the same words as a list that does not exist, so the refusal says
nothing of another dataset's lists (rule 3's reasoning, applied to the save gate).

**Staged Parquet** (`03_CONDUIT_MIDDLEWARE.md` §5.1): each step's table is written as resolved rows
are, `<bucket>/loads/<load_id>/staged/<table>.parquet`, its cells as text and its refs as a JSON
column, so a re-run can re-map without re-reading the source; a reference list is written the same
way with its kind, name, version and key column in the file's metadata, so a screening list
round-trips through the catalogue as one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import pyarrow as pa
import pyarrow.parquet as pq

from knowledge_adapters import ARITY, REGISTRY
from knowledge_adapters.derive import derive
from knowledge_adapters.errors import NormalisationError
from knowledge_adapters.screening_lists import ListedParty
from schemas.dataset_model import ReferenceList
from schemas.domain import SourceRef
from schemas.staging import (
    AddedColumn,
    DedupeStep,
    DeriveStep,
    FilterCondition,
    FilterStep,
    JoinStep,
    LookupStep,
    StagingStep,
    UnionStep,
    step_inputs,
)

from . import staging as _staging
from .staging import ObjectStorageConfig

Cell = str | None
TableKind = Literal["source", "step", "reference", "screening"]

#: The one screening shape every list format maps to (ADR-140 Amendment 9 decision 3): primary
#: name, aliases, date of birth, nationality, identifiers, programme; with the publisher's own
#: reference (the key), the kind of listing and whether a person or an organisation. A many-valued
#: cell (aliases, identifiers) is its values joined by `|`, as `split` reads them back in Map.
SCREENING_COLUMNS: tuple[str, ...] = (
    "ref",
    "primary_name",
    "aliases",
    "date_of_birth",
    "nationality",
    "identifiers",
    "programme",
    "listing",
    "entity_type",
)
_MANY = "|"


class StagingError(Exception):
    """A staging run refused whole, before any row is passed on, with every reason in words."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True)
class StagedRef:
    """One input row a staged row came from."""

    #: The source table's name, or `reference_list:<name>@v<version>` for a list row.
    source: str
    #: The row's position in what the source gave (0 first), as the engine's locator reads it.
    row_index: int
    #: The SHA-256 of its declared key columns (else of all its cells); a list row's key value.
    row_key: str
    #: The load that read it; `None` for a list row, which a list's version identifies.
    load_id: str | None

    def to_source_ref(self) -> SourceRef:
        return SourceRef(
            document_id=self.source,
            locator=f"row {self.row_index}",
            excerpt_hash="",
            row_key=self.row_key,
            load_id=self.load_id,
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "row_index": self.row_index,
            "row_key": self.row_key,
            "load_id": self.load_id,
        }


@dataclass(frozen=True)
class StagedTableRow:
    cells: dict[str, Cell]
    refs: tuple[StagedRef, ...]


@dataclass
class StagedTable:
    name: str
    columns: list[str]
    rows: list[StagedTableRow]
    kind: TableKind = "step"
    #: For a list: the list it is (kind, name, version, key column).
    reference: ReferenceList | None = None


@dataclass(frozen=True)
class StagingRejection:
    """A row a step refused: which step, the rows it came from, and why (never the value)."""

    step: str
    refs: tuple[StagedRef, ...]
    reason: str


@dataclass
class StepReport:
    step: str
    kind: str
    rows_in: int
    rows_out: int
    #: A Lookup's or a left Join's rows with no match (kept, with empty added cells), or an inner
    #: Join's (not passed on).
    unmatched: int = 0
    filtered_out: int = 0
    repeats_folded: int = 0
    rejected: int = 0


@dataclass
class StagingResult:
    output: StagedTable
    tables: dict[str, StagedTable]
    reports: list[StepReport]
    rejections: list[StagingRejection] = field(default_factory=list)


# --- Tables in ----------------------------------------------------------------


def _text(value: object) -> Cell:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _hash(parts: Sequence[Cell]) -> str:
    return hashlib.sha256(
        json.dumps(list(parts), ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def source_table(
    name: str,
    rows: Sequence[Mapping[str, object]],
    *,
    load_id: str,
    key: Sequence[str] | None = None,
) -> StagedTable:
    """A source's rows as a table: each row's ref names `name`, its position, its identity (the
    hash of its declared `key` columns, else of all its cells in column order) and `load_id`."""
    columns: list[str] = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    out: list[StagedTableRow] = []
    for index, row in enumerate(rows):
        cells = {c: _text(row.get(c)) for c in columns}
        identity = _hash([cells[c] for c in key] if key else [cells[c] for c in columns])
        out.append(StagedTableRow(cells, (StagedRef(name, index, identity, load_id),)))
    return StagedTable(name=name, columns=columns, rows=out, kind="source")


def reference_table(reference: ReferenceList, rows: Sequence[Mapping[str, object]]) -> StagedTable:
    """A reference list's rows as a table; each row's ref names the list at its version and its key
    value. A key column the rows lack, or a key two rows share, is refused: the key identifies a
    row (`ReferenceList.key_column`)."""
    columns: list[str] = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    if rows and reference.key_column not in columns:
        raise StagingError(
            [f"the list {reference.name!r} has no column {reference.key_column!r}, its key"]
        )
    source = f"reference_list:{reference.name}@v{reference.version}"
    seen: set[str] = set()
    out: list[StagedTableRow] = []
    for index, row in enumerate(rows):
        cells = {c: _text(row.get(c)) for c in columns}
        key = cells[reference.key_column]
        if key is None:
            raise StagingError([f"row {index} of the list {reference.name!r} has no key"])
        if key in seen:
            raise StagingError(
                [f"the list {reference.name!r} holds one key on two rows; its key must be unique"]
            )
        seen.add(key)
        out.append(StagedTableRow(cells, (StagedRef(source, index, key, None),)))
    return StagedTable(
        name=reference.name, columns=columns, rows=out, kind=reference.kind, reference=reference
    )


def screening_table(reference: ReferenceList, parties: Sequence[ListedParty]) -> StagedTable:
    """A parsed screening list (`knowledge_adapters.screening_lists`) in the one screening shape,
    as a reference list of kind `screening` keyed on the publisher's reference."""
    if reference.kind != "screening" or reference.key_column != "ref":
        raise StagingError(
            [f"the list {reference.name!r} is not a screening list keyed on its reference"]
        )
    rows: list[dict[str, object]] = []
    for party in parties:
        for alias in party.aliases:
            if _MANY in alias:
                raise StagingError(
                    [f"an alias of entry {party.ref} holds {_MANY!r}, which separates aliases"]
                )
        rows.append(
            {
                "ref": party.ref,
                "primary_name": party.name,
                "aliases": _MANY.join(party.aliases) or None,
                "date_of_birth": party.date_of_birth,
                "nationality": party.country,
                "identifiers": None,
                "programme": None,
                "listing": party.listing,
                "entity_type": party.entity_type,
            }
        )
    table = reference_table(reference, rows)
    table.columns = list(SCREENING_COLUMNS)
    return table


def screening_parties(table: StagedTable) -> tuple[ListedParty, ...]:
    """The screening entries a screening table holds, as the screening store reads them."""
    if table.kind != "screening":
        raise StagingError([f"the table {table.name!r} is not a screening list"])
    return tuple(
        ListedParty(
            ref=row.cells["ref"] or "",
            listing=row.cells["listing"],  # type: ignore[arg-type]
            entity_type=row.cells["entity_type"],  # type: ignore[arg-type]
            name=row.cells["primary_name"] or "",
            aliases=tuple((row.cells["aliases"] or "").split(_MANY))
            if row.cells["aliases"]
            else (),
            date_of_birth=row.cells["date_of_birth"],
            country=row.cells["nationality"],
        )
        for row in table.rows
    )


# --- The save gate's rules ----------------------------------------------------------


def _adapter_problem(step: str, name: str | None) -> str | None:
    if name is None:
        return None
    if name not in REGISTRY or name in ARITY or name == "split":
        return (
            f"step {step!r} normalises its key with {name!r}, which is not a Knowledge Adapter "
            "that reads one column into one value"
        )
    return None


def staging_rule_violations(
    steps: Sequence[StagingStep],
    *,
    sources: Collection[str],
    lists: Collection[ReferenceList],
    dataset_id: str,
    subscribed: Collection[str] = (),
) -> list[str]:
    """What the save gate refuses in a `staging:` list, in words (the redesign's phase 7: "a join
    must name a key; a step must be fed"). `sources`: the pipeline's source tables. `lists`: the
    lists the caller can see; a Lookup may name only the dataset's own (`dataset_id`) or a
    screening list in `subscribed`. A join's keys are required by the schema itself."""
    problems: list[str] = []
    known: list[str] = list(sources)
    readable = {
        ref.name
        for ref in lists
        if ref.dataset_id == dataset_id or (ref.kind == "screening" and ref.name in subscribed)
    }
    read_by_later: set[str] = set()
    for position, step in enumerate(steps):
        if step.id in known:
            problems.append(f"step {step.id!r} has the name of a source table or an earlier step")
        for table in step_inputs(step):
            if table == step.id:
                problems.append(f"step {step.id!r} reads itself")
            elif table not in known:
                later = any(s.id == table for s in steps[position + 1 :])
                problems.append(
                    f"step {step.id!r} reads {table!r}, which is "
                    + (
                        "a later step: a step reads only what comes before it"
                        if later
                        else "neither a source table of this pipeline nor an earlier step"
                    )
                )
            read_by_later.add(table)
        if isinstance(step, LookupStep):
            if step.list_ not in readable:
                problems.append(
                    f"step {step.id!r} looks up {step.list_!r}, which names no list this dataset "
                    "holds or subscribes to"
                )
            problem = _adapter_problem(step.id, step.normalise)
            if problem:
                problems.append(problem)
        if isinstance(step, JoinStep):
            problem = _adapter_problem(step.id, step.normalise)
            if problem:
                problems.append(problem)
        known.append(step.id)
    for step in steps[:-1]:
        if step.id not in read_by_later:
            problems.append(
                f"step {step.id!r} feeds nothing: every step but the last must feed a later one "
                "(the last is what Map reads)"
            )
    return problems


# --- The steps ----------------------------------------------------------------


def _key(value: Cell, normalise: str | None) -> str | None:
    """A key cell as it is compared: trimmed, or read through the declared adapter (which may
    refuse it, raising `NormalisationError`)."""
    if value is None:
        return None
    if normalise is None:
        return value.strip()
    return str(REGISTRY[normalise](value))


def _added_names(
    step_id: str, table: StagedTable, add: Sequence[AddedColumn], into: Sequence[str]
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    problems: list[str] = []
    for added in add:
        if added.column not in table.columns:
            problems.append(
                f"step {step_id!r} brings {added.column!r}, which {table.name!r} has not"
            )
        name = added.as_ or added.column
        if name in into or name in (p[1] for p in pairs):
            problems.append(f"step {step_id!r} adds {name!r}, a column its table already has")
        pairs.append((added.column, name))
    if problems:
        raise StagingError(problems)
    return pairs


def _lookup(
    step: LookupStep, table: StagedTable, reference: StagedTable
) -> tuple[StagedTable, StepReport, list[StagingRejection]]:
    assert reference.reference is not None
    if step.on not in table.columns:
        raise StagingError(
            [f"step {step.id!r} looks up on {step.on!r}, which {table.name!r} has not"]
        )
    pairs = _added_names(step.id, reference, step.add, table.columns)
    index: dict[str, StagedTableRow] = {}
    for row in reference.rows:
        try:
            key = _key(row.cells[reference.reference.key_column], step.normalise)
        except NormalisationError as exc:
            raise StagingError(
                [
                    f"step {step.id!r}: a key of the list {reference.name!r} cannot be read as "
                    f"{step.normalise} ({exc.reason})"
                ]
            ) from exc
        if key is not None:
            if key in index:
                raise StagingError(
                    [
                        f"step {step.id!r}: two keys of the list {reference.name!r} are one once "
                        f"read as {step.normalise}"
                    ]
                )
            index[key] = row
    report = StepReport(step.id, "lookup", rows_in=len(table.rows), rows_out=0)
    rejections: list[StagingRejection] = []
    out: list[StagedTableRow] = []
    for row in table.rows:
        try:
            key = _key(row.cells.get(step.on), step.normalise)
        except NormalisationError as exc:
            rejections.append(StagingRejection(step.id, row.refs, f"{step.on}: {exc.reason}"))
            continue
        match = index.get(key) if key is not None else None
        cells = dict(row.cells)
        for column, name in pairs:
            cells[name] = match.cells.get(column) if match else None
        if match is None:
            report.unmatched += 1
        out.append(StagedTableRow(cells, row.refs + (match.refs if match else ())))
    report.rows_out, report.rejected = len(out), len(rejections)
    return StagedTable(step.id, table.columns + [n for _, n in pairs], out), report, rejections


def _join(
    step: JoinStep, left: StagedTable, right: StagedTable
) -> tuple[StagedTable, StepReport, list[StagingRejection]]:
    problems = [
        f"step {step.id!r} joins on {key!r}, which {table.name!r} has not"
        for key, table in ((step.left_key, left), (step.right_key, right))
        if key not in table.columns
    ]
    if problems:
        raise StagingError(problems)
    pairs = _added_names(step.id, right, step.add, left.columns)
    index: dict[str, list[StagedTableRow]] = {}
    rejections: list[StagingRejection] = []
    for row in right.rows:
        try:
            key = _key(row.cells.get(step.right_key), step.normalise)
        except NormalisationError as exc:
            # A right row that cannot be read joins nothing, and is said, never silently missed.
            rejections.append(
                StagingRejection(step.id, row.refs, f"{step.right_key}: {exc.reason}")
            )
            continue
        if key is not None:
            index.setdefault(key, []).append(row)
    report = StepReport(step.id, "join", rows_in=len(left.rows), rows_out=0)
    out: list[StagedTableRow] = []
    for row in left.rows:
        try:
            key = _key(row.cells.get(step.left_key), step.normalise)
        except NormalisationError as exc:
            rejections.append(StagingRejection(step.id, row.refs, f"{step.left_key}: {exc.reason}"))
            continue
        matches = index.get(key, []) if key is not None else []
        if not matches:
            report.unmatched += 1
            if step.how == "left":
                cells = dict(row.cells) | {name: None for _, name in pairs}
                out.append(StagedTableRow(cells, row.refs))
            continue
        for match in matches:
            cells = dict(row.cells) | {name: match.cells.get(column) for column, name in pairs}
            out.append(StagedTableRow(cells, row.refs + match.refs))
    report.rows_out, report.rejected = len(out), len(rejections)
    return StagedTable(step.id, left.columns + [n for _, n in pairs], out), report, rejections


def _holds(condition: FilterCondition, cells: Mapping[str, Cell]) -> bool:
    value = cells.get(condition.field)
    text = value.strip() if value is not None else None
    if condition.is_ == "null":
        return text is None
    if condition.is_ == "not_null":
        return text is not None
    if condition.equals is not None:
        return text == condition.equals
    assert condition.in_ is not None
    return text in condition.in_


def _filter(
    step: FilterStep, table: StagedTable
) -> tuple[StagedTable, StepReport, list[StagingRejection]]:
    missing = [c.field for c in step.keep if c.field not in table.columns]
    if missing:
        raise StagingError(
            [f"step {step.id!r} filters on {m!r}, which {table.name!r} has not" for m in missing]
        )
    out = [row for row in table.rows if all(_holds(c, row.cells) for c in step.keep)]
    report = StepReport(
        step.id, "filter", len(table.rows), len(out), filtered_out=len(table.rows) - len(out)
    )
    return StagedTable(step.id, list(table.columns), out), report, []


def _derive(
    step: DeriveStep, table: StagedTable
) -> tuple[StagedTable, StepReport, list[StagingRejection]]:
    problems = [
        f"step {step.id!r} derives from {c!r}, which {table.name!r} has not"
        for c in step.columns
        if c not in table.columns
    ]
    if step.column in table.columns:
        problems.append(f"step {step.id!r} makes {step.column!r}, a column its table already has")
    if problems:
        raise StagingError(problems)
    out: list[StagedTableRow] = []
    rejections: list[StagingRejection] = []
    for row in table.rows:
        try:
            value = derive(step.operation, [row.cells.get(c) for c in step.columns], step.settings)
        except NormalisationError as exc:
            rejections.append(StagingRejection(step.id, row.refs, exc.reason))
            continue
        out.append(StagedTableRow(dict(row.cells) | {step.column: value}, row.refs))
    report = StepReport(step.id, "derive", len(table.rows), len(out), rejected=len(rejections))
    return StagedTable(step.id, table.columns + [step.column], out), report, rejections


def _union(
    step: UnionStep, tables: Sequence[StagedTable]
) -> tuple[StagedTable, StepReport, list[StagingRejection]]:
    first = tables[0]
    problems = [
        f"step {step.id!r} stacks {t.name!r} and {first.name!r}, whose columns differ"
        for t in tables[1:]
        if set(t.columns) != set(first.columns)
    ]
    if problems:
        raise StagingError(problems)
    out = [
        StagedTableRow({c: row.cells.get(c) for c in first.columns}, row.refs)
        for t in tables
        for row in t.rows
    ]
    report = StepReport(step.id, "union", sum(len(t.rows) for t in tables), len(out))
    return StagedTable(step.id, list(first.columns), out), report, []


def _dedupe(
    step: DedupeStep, table: StagedTable
) -> tuple[StagedTable, StepReport, list[StagingRejection]]:
    missing = [c for c in step.on if c not in table.columns]
    if missing:
        raise StagingError(
            [f"step {step.id!r} dedupes on {m!r}, which {table.name!r} has not" for m in missing]
        )
    groups: dict[tuple[Cell, ...], int] = {}
    out: list[StagedTableRow] = []
    for row in table.rows:
        key = tuple((row.cells.get(c) or "").strip() or None for c in step.on)
        at = groups.get(key)
        if at is None:
            groups[key] = len(out)
            out.append(row)
        else:
            survivor = out[at]
            out[at] = StagedTableRow(survivor.cells, survivor.refs + row.refs)
    report = StepReport(
        step.id, "dedupe", len(table.rows), len(out), repeats_folded=len(table.rows) - len(out)
    )
    return StagedTable(step.id, list(table.columns), out), report, []


def run_staging(
    steps: Sequence[StagingStep],
    *,
    sources: Mapping[str, StagedTable],
    lists: Mapping[str, StagedTable],
    dataset_id: str,
    subscribed: Collection[str] = (),
) -> StagingResult:
    """Run the steps in order over the source tables and the reference lists (each a
    `reference_table`), after the save gate's rules (refused whole if any is broken)."""
    if not steps:
        raise StagingError(["a staging list has at least one step"])
    references = [t.reference for t in lists.values() if t.reference is not None]
    problems = staging_rule_violations(
        steps, sources=list(sources), lists=references, dataset_id=dataset_id, subscribed=subscribed
    )
    if problems:
        raise StagingError(problems)
    tables: dict[str, StagedTable] = dict(sources)
    reports: list[StepReport] = []
    rejections: list[StagingRejection] = []
    for step in steps:
        if isinstance(step, LookupStep):
            done = _lookup(step, tables[step.input], lists[step.list_])
        elif isinstance(step, JoinStep):
            done = _join(step, tables[step.left], tables[step.right])
        elif isinstance(step, FilterStep):
            done = _filter(step, tables[step.input])
        elif isinstance(step, DeriveStep):
            done = _derive(step, tables[step.input])
        elif isinstance(step, UnionStep):
            done = _union(step, [tables[name] for name in step.inputs])
        else:
            done = _dedupe(step, tables[step.input])
        table, report, rejected = done
        tables[step.id] = table
        reports.append(report)
        rejections.extend(rejected)
    return StagingResult(tables[steps[-1].id], tables, reports, rejections)


# --- Into Map -------------------------------------------------------------------


def map_input(table: StagedTable) -> tuple[list[dict[str, str]], dict[int, tuple[SourceRef, ...]]]:
    """The rows Map reads (an empty cell as `""`, as a connector gives it) and, by each row's
    position, the `SourceRef`s its element records: `run_recipe`'s and `dry_run_recipe`'s
    `row_refs`."""
    rows = [{c: (row.cells.get(c) or "") for c in table.columns} for row in table.rows]
    refs = {i: tuple(r.to_source_ref() for r in row.refs) for i, row in enumerate(table.rows)}
    return rows, refs


# --- Staged Parquet -------------------------------------------------------------

_META = b"ospreyflow.staged_table"


def _to_arrow(table: StagedTable) -> pa.Table:
    data: dict[str, list[Any]] = {
        c: [row.cells.get(c) for row in table.rows] for c in table.columns
    }
    if "_refs" in data:
        raise StagingError(
            [f"the table {table.name!r} has a column named _refs, which staging keeps"]
        )
    data["_refs"] = [json.dumps([r.as_json() for r in row.refs]) for row in table.rows]
    schema = pa.schema([pa.field(name, pa.string()) for name in data])
    meta: dict[str, Any] = {"name": table.name, "kind": table.kind, "columns": table.columns}
    if table.reference is not None:
        meta["reference"] = table.reference.model_dump(mode="json")
    return pa.table(data, schema=schema.with_metadata({_META: json.dumps(meta).encode()}))


def stage_table(table: StagedTable, *, storage: ObjectStorageConfig, load_id: str) -> str:
    """Write one staged table to `<bucket>/loads/<load_id>/staged/<name>.parquet`; returns the
    path."""
    path = f"{storage.bucket}/loads/{load_id}/staged/{table.name}.parquet"
    fs = _staging.filesystem(storage)
    fs.create_dir(storage.bucket)
    with fs.open_output_stream(path) as sink:
        pq.write_table(_to_arrow(table), sink)
    return path


def read_staged_table(path: str, *, storage: ObjectStorageConfig) -> StagedTable:
    with _staging.filesystem(storage).open_input_file(path) as source:
        arrow = pq.read_table(source)
    meta = json.loads((arrow.schema.metadata or {})[_META])
    columns: list[str] = meta["columns"]
    data = arrow.to_pydict()
    rows = [
        StagedTableRow(
            {c: data[c][i] for c in columns},
            tuple(StagedRef(**r) for r in json.loads(data["_refs"][i])),
        )
        for i in range(arrow.num_rows)
    ]
    reference = ReferenceList.model_validate(meta["reference"]) if "reference" in meta else None
    return StagedTable(meta["name"], columns, rows, kind=meta["kind"], reference=reference)
