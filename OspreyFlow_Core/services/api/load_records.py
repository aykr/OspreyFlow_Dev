"""What a run keeps in the run ledger beside it (`06_DECISIONS.md` ADR-127 decision 6 and
Amendment 5): the `LoadRecord` of each load it made, so a revert needs nothing but the ledger.

**When.** A load's record is written when its graph transaction commits (`LedgerSink.committed`,
called by `load_with_rules` straight after the commit), before the events, the geometry points, the
post-commit rules, the resolution jobs and the change stream, so a failure in any of them still
leaves the record. The geometry refs a load inserts are recorded just before they are inserted
(`LedgerSink.geometries`). The run's ledger row is started before the load, so each record is
appended to a row that already exists.

**Whose.** A plain run made one load. A pipeline run made one per source branch, each under its own
`load_id` and with its own source, so each is independently revertible (`BranchRunReport`); the
pipeline's own id has no events or links, and extract and enrich stages write inferred elements that
no load record covers yet. A release of held rows is a load of its own, recorded with the id of the
load that held the rows.

**Never returned.** The records hold ids of elements some readers may not see. No route returns
them: `RecipeRunStore` selects no record column into `RecipeRun`, the one shape the routes read
(`test_run_ledger_read_side.py`), and the routes that answer a load's report answer a view without
its id lists (`report_view`)."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Protocol, overload

from services.ingest.load_ledger import load_record_from_report

from schemas.domain import HeldRow
from schemas.ingest import (
    BranchRunReportView,
    LoadRecord,
    LoadReport,
    LoadReportView,
    PipelineRunReport,
    PipelineRunReportView,
)


class _RunLedger(Protocol):
    async def add_record(
        self,
        run_id: str,
        record: LoadRecord,
        *,
        row_keys: Sequence[str] = (),
        row_key_fingerprint: str = "",
    ) -> None: ...

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]: ...

    def hold_row_keys(self, recipe_id: str, case: str) -> AbstractAsyncContextManager[None]: ...

    async def kept_row_keys(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]: ...

    async def add_geometries(self, run_id: str, load_id: str, refs: list[str]) -> None: ...

    async def add_rule_writes(
        self,
        run_id: str,
        load_id: str,
        *,
        node_ids: list[str],
        created_edge_ids: list[str],
        merged_edge_ids: list[str],
    ) -> None: ...

    async def mark_uncovered(self, run_id: str, load_id: str) -> None: ...


class LedgerSink:
    """A load's way of writing to its run's ledger row: `committed` appends the load's record,
    `geometries` adds the refs of the points it inserts. One sink serves every branch of a pipeline
    run, so each branch's record is appended as its own graph transaction commits."""

    def __init__(
        self,
        ledger: _RunLedger,
        run_id: str,
        *,
        created_by: str,
        investigation_id: str,
        started_at: datetime,
        released_from: str | None = None,
    ) -> None:
        self._ledger = ledger
        self._run_id = run_id
        self._created_by = created_by
        self._investigation_id = investigation_id
        self._started_at = started_at
        self._released_from = released_from

    async def committed(self, report: LoadReport, *, source: str) -> None:
        # The record and the keys of the rows this load wrote go in together, in one transaction of
        # the ledger, after the graph's commit (ADR-127 decision 5): never a key for a row that did
        # not load, and never a record without the keys of the rows it loaded.
        await self._ledger.add_record(
            self._run_id,
            load_record_from_report(
                report,
                source=source,
                created_by=self._created_by,
                started_at=self._started_at,
                now=datetime.now(UTC),
                investigation_id=self._investigation_id,
                released_from=self._released_from,
            ),
            row_keys=report.kept_row_keys,
            row_key_fingerprint=report.row_key_fingerprint or "",
        )

    async def kept(self, recipe_id: str, case: str, keys: Sequence[str]) -> set[str]:
        return await self._ledger.kept_row_keys(recipe_id, case, keys)

    async def fingerprints(self, recipe_id: str, case: str) -> dict[str, int]:
        return await self._ledger.fingerprints(recipe_id, case)

    def hold_row_keys(self, recipe_id: str, case: str) -> AbstractAsyncContextManager[None]:
        return self._ledger.hold_row_keys(recipe_id, case)

    async def geometries(self, load_id: str, refs: Sequence[str]) -> None:
        await self._ledger.add_geometries(self._run_id, load_id, list(refs))

    async def rule_writes(
        self,
        load_id: str,
        *,
        node_ids: Sequence[str],
        created_edge_ids: Sequence[str],
        merged_edge_ids: Sequence[str],
    ) -> None:
        """What an alert raised after the commit wrote, added to the load's record."""
        await self._ledger.add_rule_writes(
            self._run_id,
            load_id,
            node_ids=list(node_ids),
            created_edge_ids=list(created_edge_ids),
            merged_edge_ids=list(merged_edge_ids),
        )

    async def uncovered(self, load_id: str) -> None:
        """An extract or enrich stage fed by this load wrote elements no record covers."""
        await self._ledger.mark_uncovered(self._run_id, load_id)


def released_from_of(held: Sequence[HeldRow]) -> str:
    """The one load the rows of a release were held by. Rows of two loads are not one release
    (`release_held_rows` refuses them too); this refuses them rather than name one of the two."""
    originals = {h.load_id for h in held}
    if len(originals) != 1:
        raise ValueError("a release names the rows of one load, and these are of several")
    return next(iter(originals))


def _load_view(report: LoadReport) -> LoadReportView:
    fields = set(LoadReportView.model_fields)
    return LoadReportView.model_validate(report.model_dump(include=fields))


@overload
def report_view(report: LoadReport) -> LoadReportView: ...


@overload
def report_view(report: PipelineRunReport) -> PipelineRunReportView: ...


def report_view(
    report: LoadReport | PipelineRunReport,
) -> LoadReportView | PipelineRunReportView:
    """A report as a route answers it: its counts and words, and none of the id lists (rules 3 and
    7). A link an earlier load wrote, listed as merged into, would be told to the loader whether or
    not they may read it."""
    if isinstance(report, LoadReport):
        return _load_view(report)
    data = report.model_dump(include=set(PipelineRunReportView.model_fields) - {"branches"})
    return PipelineRunReportView(
        **data,
        branches=[
            BranchRunReportView(
                source_id=b.source_id,
                source_label=b.source_label,
                source_location=b.source_location,
                report=_load_view(b.report),
            )
            for b in report.branches
        ],
    )
