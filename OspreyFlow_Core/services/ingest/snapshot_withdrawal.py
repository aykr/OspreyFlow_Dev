"""A full snapshot's withdrawal of its dropped rows' events (`06_DECISIONS.md` ADR-110 Amendment 8
point 3, as ADR-110 Amendment 15 narrows it).

A source refreshed as a *full snapshot* with *withdraw* reads the whole table each time; a row a
pipeline kept for the case that the snapshot no longer carries is *dropped*, and **only its own
events** (its timeline and analytics rows) are withdrawn (`AnalyticsPort.withdraw_events_by_id`),
named by the ids its key's record keeps, once the refresh's load has committed. **The graph is never
touched**: a dropped row's nodes and links stay, as *keep* leaves every element, until its load is
reverted (Amendment 15, the owner's ruling "Only the rows' events"). Whether a link or a node could
go depended on other cases' rows and loads, which the loader may not read, and the run's counts, the
live graph and the timeline told them so (rule 3's hidden degree). `plan_withdrawal` asks the ledger
one question, about this pipeline's own kept keys in this case, and nothing about any other row,
case or load:

- **the dropped keys**: the pipeline's kept keys for the case that no row of the snapshot carries
  (a held or rejected row still carries its key, so it is not dropped);
- **their events**, from each key's record: the events its row wrote, and no other row's on the same
  link;
- **what it says** (`Withdrawal.notes`), in words, never silently: the dropped keys kept before rows
  recorded the events they wrote, which are left in place, their events too, with no fallback to
  their links.

`WithdrawalLedger` is what `RecipeRunStore` answers (`services/api/recipe_runs.py`) and `LedgerSink`
passes through."""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from schemas.ingest import Recipe

from .engine import row_group_keys


class DroppedRow(Protocol):
    """A kept key a snapshot no longer carries, with its record (`recipe_runs.KeptRow`)."""

    @property
    def row_key(self) -> str: ...

    @property
    def load_id(self) -> str: ...

    @property
    def event_ids(self) -> tuple[str, ...] | None: ...


class WithdrawalLedger(Protocol):
    async def dropped_row_keys(
        self, recipe_id: str, case: str, *, present: Collection[str]
    ) -> Sequence[DroppedRow]: ...


@dataclass
class Withdrawal:
    """What a full snapshot withdraws (Amendment 15): the dropped keys whose record names their
    events (moved aside by the ledger with the load's record), those events, and the dropped keys
    left in place because their record names none. No node or link: the graph is never touched."""

    row_keys: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    rows_left_in_place: int = 0

    @property
    def notes(self) -> list[str]:
        if not self.rows_left_in_place:
            return []
        one = self.rows_left_in_place == 1
        return [
            f"{self.rows_left_in_place} dropped row{'' if one else 's'} "
            f"{'was' if one else 'were'} loaded before rows recorded the events they wrote, and "
            f"{'was' if one else 'were'} left in place, {'its' if one else 'their'} events too"
        ]


async def plan_withdrawal(
    recipe: Recipe,
    rows: Sequence[dict[str, str]],
    *,
    case: str,
    ledger: WithdrawalLedger,
) -> Withdrawal:
    """Which of the snapshot's dropped rows withdraw their events, and which events (the module
    docstring has the rule). `rows` are every row the snapshot read."""
    present = await asyncio.to_thread(
        lambda: {k for k in row_group_keys(recipe, rows) if k is not None}
    )
    dropped = await ledger.dropped_row_keys(recipe.id, case, present=present)
    recorded = [d for d in dropped if d.event_ids is not None]
    return Withdrawal(
        row_keys=[d.row_key for d in recorded],
        event_ids=list(dict.fromkeys(e for d in recorded for e in d.event_ids or ())),
        rows_left_in_place=len(dropped) - len(recorded),
    )
