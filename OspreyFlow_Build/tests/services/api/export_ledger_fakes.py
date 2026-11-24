"""A stand-in for the export ledger that refuses what the real one refuses (SE8b, rule 15).

`ExportLedgerStore.record` refuses a row that names no `subject_kind` or `subject_id`
(`export.require_subject`, `ValueError`). A fake that just appended every entry would stay green
when a route dropped the subject: the route's own test would measure something more permissive than
the store. This one applies the same refusal, from the same function, so no route test written
against it can accept a row the real ledger would not take.

It keeps what it was given, in order, in `entries`.
"""

from __future__ import annotations

from services.api.export import ExportLedgerEntry, require_subject


class RefusingLedger:
    def __init__(self) -> None:
        self.entries: list[ExportLedgerEntry] = []

    async def record(self, entry: ExportLedgerEntry) -> None:
        require_subject(entry)
        self.entries.append(entry)
