"""An incremental refresh's watermark (`06_DECISIONS.md` ADR-110 Amendment 6 point 1).

A source refreshed *incrementally* names a column whose values only grow. The highest value a
succeeded run read is kept with its load's record (`SourceWatermark`), per source, pipeline and
case; the next refresh reads only the rows past it. `read_past` decides which:

- **how values compare** is settled once, from the first read: as numbers if every value is one, as
  instants if every value is an ISO 8601 date or time (all with an offset, or all without), else as
  text. A later read compares in the kept kind; a value that cannot be is refused in words, by its
  row, never by its content (rule 7);
- **a row at or below** the kept value is not read, and is counted; a row with **no value** is read
  every time and counted: a refresh never runs a keyless pipeline (Amendment 6 point 2), so its key
  keeps it from loading twice;
- **the watermark reached** is the highest of the kept value and every value read: it never moves
  back;
- a **changed column** (the policy edited) starts afresh, and says so.

What the run says is in words (`WatermarkRead.notes`), never silent (rule 2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from schemas.ingest import SourceWatermark, WatermarkKind

_KIND_WORDS: dict[WatermarkKind, str] = {
    "number": "numbers",
    "time": "dates or times",
    "text": "text",
}


@dataclass(frozen=True)
class RefreshRead:
    """How a source's refresh reads it (ADR-110 Amendment 6 point 1), as the run is given it: from
    the source's policy (`SourceRefresh`), by the executor (`SourceWatch.read`)."""

    source_id: str
    mode: str = "snapshot"
    dropped_rows: str = "keep"
    watermark_column: str | None = None

    @property
    def withdraws(self) -> bool:
        return self.mode == "snapshot" and self.dropped_rows == "withdraw"

    @property
    def incremental(self) -> bool:
        return self.mode == "incremental" and bool(self.watermark_column)


class WatermarkRefused(ValueError):
    """An incremental read that cannot be judged against its watermark, in words."""


@dataclass
class WatermarkRead:
    """The rows past the watermark, with their row numbers in the file (for rejections and held
    rows), what was left and why, and the watermark the read reaches."""

    rows: list[dict[str, str]] = field(default_factory=list)
    row_numbers: list[int] = field(default_factory=list)
    below: int = 0
    without: int = 0
    reached: SourceWatermark | None = None
    column: str = ""
    changed_from: str | None = None

    @property
    def notes(self) -> list[str]:
        words: list[str] = []
        if self.changed_from is not None:
            words.append(
                f"the watermark column changed from {self.changed_from} to {self.column}, so every "
                "row was read"
            )
        if self.below:
            words.append(
                f"{self.below} row{'' if self.below == 1 else 's'} at or below the watermark "
                f"({self.column}) {'was' if self.below == 1 else 'were'} not read"
            )
        if self.without:
            words.append(
                f"{self.without} row{'' if self.without == 1 else 's'} had no value in the "
                f"watermark column ({self.column}) and {'was' if self.without == 1 else 'were'} "
                "read; their deduplication key keeps them from loading twice"
            )
        return words


def _number(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _instant(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _kind_of(values: Sequence[str]) -> WatermarkKind:
    if all(_number(v) is not None for v in values):
        return "number"
    instants = [_instant(v) for v in values]
    if all(i is not None for i in instants):
        aware = {i.tzinfo is not None for i in instants if i is not None}
        if len(aware) == 1:
            return "time"
    return "text"


def _key(value: str, kind: WatermarkKind) -> Any:
    """The value as it compares in `kind`, or `None` where it cannot."""
    if kind == "number":
        return _number(value)
    if kind == "time":
        instant = _instant(value)
        if instant is None:
            return None
        # Aware instants compare in UTC; naive ones as written (a kind is one or the other).
        return (instant.tzinfo is not None, instant.astimezone(UTC) if instant.tzinfo else instant)
    return value


def read_past(
    rows: Sequence[dict[str, str]],
    *,
    source_id: str,
    column: str,
    kept: SourceWatermark | None,
) -> WatermarkRead:
    """The rows of one read past `kept` (the module docstring has the rule). Raises
    `WatermarkRefused` where the file has no such column, or a value cannot be compared in the
    kept kind."""
    read = WatermarkRead(column=column)
    if kept is not None and kept.column != column:
        read.changed_from, kept = kept.column, None
    if not rows:
        read.reached = kept
        return read
    if column not in rows[0]:
        raise WatermarkRefused(
            f"the file has no column {column}, which the source's refresh reads its watermark from"
        )
    values = [(row.get(column) or "").strip() for row in rows]
    present = [v for v in values if v]
    kind: WatermarkKind = kept.kind if kept is not None else _kind_of(present)
    floor = _key(kept.value, kind) if kept is not None else None
    if kept is not None and floor is None:
        raise WatermarkRefused(
            f"the kept watermark of the column {column} cannot be read as {_KIND_WORDS[kind]}"
        )
    if kind == "time" and floor is not None:
        aware = floor[0]
    else:
        aware = None
    best_value, best_key = (kept.value, floor) if kept is not None else (None, None)
    for number, (row, value) in enumerate(zip(rows, values, strict=True)):
        if not value:
            read.without += 1
            read.rows.append(row)
            read.row_numbers.append(number)
            continue
        key = _key(value, kind)
        if key is None or (aware is not None and key[0] != aware):
            raise WatermarkRefused(
                f"row {number + 1} holds a value in the watermark column {column} unlike its "
                f"earlier values ({_KIND_WORDS[kind]}), so the refresh cannot tell whether it lies "
                "past the watermark"
            )
        if aware is None and kind == "time":
            aware = key[0]
        if floor is not None and key <= floor:
            read.below += 1
            continue
        read.rows.append(row)
        read.row_numbers.append(number)
        if best_key is None or key > best_key:
            best_value, best_key = value, key
    if best_value is not None:
        read.reached = SourceWatermark(
            source_id=source_id, column=column, kind=kind, value=best_value
        )
    return read
