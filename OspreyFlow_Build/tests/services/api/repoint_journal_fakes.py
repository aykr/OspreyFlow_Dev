"""Stand-ins for the alerts' repoint journal (`AlertStore.repointing`, ADR-109 Amendments 10 and 11)
and the working set's purge, for route tests that do not run Postgres. Rule 15: each refuses what
the real one refuses. A pair recorded in a record already applied is refused
(`RepointRecordGone`), as `AlertStore._add_to_record` refuses it; a writer that leaves without
recording anything, or says `never_committed`, leaves no record, as the real writer closes its own.
What each write recorded is kept, so a test can say which links a route reported."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from services.api.alerts import RepointRecordGone

from ontology.handling import load_uk_le_scheme


class _Record:
    def __init__(self, journal: Journal, record_id: str) -> None:
        self._journal = journal
        self.id = record_id
        self.applied = False
        self.abandoned = False
        self.links: list[tuple[str, str, str]] = []
        self.nodes: list[tuple[str, str]] = []
        #: Each corrected node an alert may name, and its new revision (ADR-109 Amendment 12).
        self.referents: list[tuple[str, str]] = []
        #: Nothing is re-marked here: no alert is held.
        self.remarked_nodes: list[str] = []

    def _open(self) -> None:
        if self.applied:
            raise RepointRecordGone(self.id)

    async def record(self, old: str, new: str, *, old_type: str) -> None:
        self._open()
        self.links.append((old, new, old_type))

    async def cloned(self, old: str, new: str, old_type: str) -> None:
        await self.record(old, new, old_type=old_type)

    async def __call__(self, old: str, new: str, old_type: str) -> None:
        await self.cloned(old, new, old_type)

    async def superseded(self, old: str, new: str) -> None:
        self._open()
        self.referents.append((old, new))

    async def record_node(self, old: str, new: str) -> None:
        self._open()
        self.nodes.append((old, new))

    def never_committed(self) -> None:
        self.abandoned = True

    async def purged(self) -> None:
        return None


class Journal:
    """`AlertStore`'s journal and reads, holding no alert: every settle finds nothing to move."""

    def __init__(self) -> None:
        self.records: list[_Record] = []

    @asynccontextmanager
    async def repointing(self, graph: Any, *, held_open: bool = False) -> AsyncIterator[_Record]:
        record = _Record(self, f"record-{len(self.records) + 1}")
        try:
            yield record
        finally:
            record.applied = True
            if not record.abandoned and (record.links or record.nodes or record.referents):
                self.records.append(record)

    async def settle_pending(self, graph: Any, *, now: Any = None) -> None:
        return None

    async def cited_by_ids(self, alert_ids: Any) -> dict[str, Any]:
        """`AlertStore.cited_by_ids`: no alert is held, so none is found."""
        return {}

    @property
    def links(self) -> list[tuple[str, str, str]]:
        """Every link pair recorded by a write that reached its commit."""
        return [pair for record in self.records for pair in record.links]

    @property
    def referents(self) -> list[tuple[str, str]]:
        """Every corrected node recorded by a write that reached its commit."""
        return [pair for record in self.records for pair in record.referents]


class WorkingSets:
    """`WorkingSetService.remove_reverted` and its `publisher`: no case holds a copy here."""

    publisher = None

    async def remove_reverted(self, nodes: Any, links: Any) -> list[Any]:
        return []


class RaiserReads:
    """`AlertStore.handlings_by_id` and `scheme`, for a stand-in store of the queue's reads (ADR-109
    Amendment 12 point 10, `alerts.raiser_reads_admitting`). Answers only what the real query
    answers: an entry for each alert asked that the store holds (`held_alert_ids`), its recorded
    handlings or `None` where none were recorded, and nothing for an alert it does not hold. A test
    records a raiser's read in `recorded_handlings`."""

    scheme = load_uk_le_scheme()

    @property
    def recorded_handlings(self) -> dict[str, Any]:
        if "_recorded_handlings" not in self.__dict__:
            self.__dict__["_recorded_handlings"] = {}
        return self.__dict__["_recorded_handlings"]  # type: ignore[no-any-return]

    def held_alert_ids(self) -> set[str]:
        raise NotImplementedError

    async def handlings_by_id(self, alert_ids: Any) -> dict[str, Any]:
        held = self.held_alert_ids()
        return {i: self.recorded_handlings.get(i) for i in alert_ids if i in held}
