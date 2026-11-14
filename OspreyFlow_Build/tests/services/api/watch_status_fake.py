"""`HotlistStore.set_status` / `MonitorStore.set_status` as a test double must take them (ADR-044
Amendment 1; rule 15): the status, and a reason kept only with `stopped`, cleared with `active` as the
real statement's `CASE` does. A status or reason the real types do not allow is refused here, as the
schema refuses it when the row is read back."""

from __future__ import annotations

from typing import get_args

from schemas.domain import StoppedReason, WatchStatus


def kept(status: str, detail: str | None = None) -> tuple[str, str | None]:
    """What the real store keeps for `set_status(id, status, detail)`: `(status, reason)`."""
    if status not in get_args(WatchStatus):
        raise ValueError(f"not a watch status: {status!r}")
    if detail is not None and detail not in get_args(StoppedReason):
        raise ValueError(f"not a stopped reason: {detail!r}")
    return status, detail if status == "stopped" else None


class UnreachableCount:
    """The real stores' `unreachable_in_a_row` (ADR-044 Amendment 2) as a double must keep it (rule 15):
    `count_unreachable` adds one and answers the new count, as the real `UPDATE … RETURNING` does, and
    every `set_status` puts it back to 0, as the real statement does for any status."""

    def __init__(self) -> None:
        self.in_a_row: dict[str, int] = {}

    def count(self, watch_id: str) -> int:
        self.in_a_row[watch_id] = self.in_a_row.get(watch_id, 0) + 1
        return self.in_a_row[watch_id]

    def reset(self, watch_id: str) -> None:
        self.in_a_row[watch_id] = 0
