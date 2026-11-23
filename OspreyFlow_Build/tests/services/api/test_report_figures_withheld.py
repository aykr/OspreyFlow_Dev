"""Whether a case report's figures were lowered by what the reader may not see (SE8b, the owner's
ruling of 21 November 2026: every export writes its ledger row, the `withheld` flag as the route
computes it; the first fix's verifier finding: the flag must be the figures' own, not a stand-in).

The report's ledger row carries `withheld`. Its first version asked the case's working-set sentence
(`withheld_for`), a question about what the case's stored set holds, of a set no figure is counted
from: it said `False` for a reader whose alerts the queue had left out, and `True` for one whose
figures were whole. These tests run the real `reports.case_report_and_withheld` and the real alert
queue, against fakes that answer as the adapters do (a hidden id is absent from a batched read), and
plant both directions:

- figures lowered (an alert citing what the reader cannot read) -> the flag is true, and the total
  is lower: the flag follows the lowering, not a constant;
- figures whole but the case's working set holds material the reader may not view -> the flag is
  false (red against the first version);
- an alert left out only by a status filter is not withheld from the reader.

Held rows: the real `HeldRowStore.left_out_for` is Postgres (its live counterpart is
`test_reports.py::test_the_held_flag_follows_what_the_reader_may_not_read`, owed), so here it is
held to its query: the same clauses and the same parameters as `list_authorized`, which is what
keeps the flag and the figure from being asked differently.

**Folders this test walks** (for the line's scan map): none. It runs functions against fakes and reads no
file.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import reports
from services.api.held_rows import HeldRowStore
from tests.services.api.test_alert_evidence_withheld import (
    CASE,
    OVER_LINK,
    READER,
    V1,
    V2,
    _world,
)

from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

TODAY = date(2026, 11, 7)


class _EmptyGraph:
    """The reader's whole graph, empty: nothing for the KYC book to count."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def list_nodes(self, *args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(nodes=[], next_cursor=None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _Held:
    """Held rows by classification, as the store answers for a reader cleared to OFFICIAL: the
    figures count what it may list, and `left_out_for` is true when it listed fewer than there are."""

    def __init__(self, classifications: list[str]) -> None:
        self.rows = classifications
        self.asked: list[str] = []

    async def list_authorized(
        self, case: str, reader: Principal, *, status: str = "held"
    ) -> list[str]:
        return [c for c in self.rows if c == "OFFICIAL"] if status == "held" else []

    async def left_out_for(self, case: str, reader: Principal, *, status: str = "held") -> bool:
        self.asked.append(status)
        return status == "held" and any(c != "OFFICIAL" for c in self.rows)


async def _report(
    hidden: set[str], alerts: list[Any], *, held: _Held | None = None, show_held: bool = False
) -> tuple[Any, bool]:
    store, graph, analytics, _ = _world(hidden, alerts)
    return await reports.case_report_and_withheld(
        alerts=store, graph=_EmptyGraph(graph), analytics=analytics,  # type: ignore[arg-type]
        held=held or _Held([]),  # type: ignore[arg-type]
        compute=None, explore=None, ontology=None,  # type: ignore[arg-type]
        domains=["fibo"], investigation_id=CASE, reader=READER, today=TODAY, show_held=show_held,
    )  # fmt: skip


async def test_figures_lowered_by_what_the_reader_cannot_read_say_so() -> None:
    """An alert over a link the reader cannot read is in no figure; the flag says it. Red with the
    first version's predicate (the working set: here it knows nothing of the alert) and with the
    old constant `False`."""
    shown, flag = await _report({"e-secret"}, [V1, OVER_LINK, V2])
    whole, whole_flag = await _report(set(), [V1, OVER_LINK, V2])
    assert shown.alerts_total == whole.alerts_total - 1, "the figures were lowered"
    assert flag is True
    assert whole_flag is False, "nothing hidden: the flag is not a constant `True` either"


async def test_whole_figures_are_not_withheld_whatever_the_working_set_holds() -> None:
    """The figures are counted as the reader from the alerts' own evidence, never from the case's
    stored working set, so material in that set the reader may not view changes no figure and the
    flag stays false. The case report is built here with no working set at all: a route that asked
    one for the flag has nothing to ask."""
    figures, flag = await _report(set(), [V1, V2])
    assert figures.alerts_total == 2
    assert flag is False


async def test_an_alert_left_out_by_a_status_filter_is_not_withheld() -> None:
    """The queue's own filters narrow what is asked for, not what the reader may see: a closed alert
    filtered out of an open-only listing is not 'withheld'. Only evidence the reader cannot read
    sets the flag."""
    from services.api import alert_queue

    store, graph, analytics, _ = _world(set(), [V1, V2])
    shown, left_out = await alert_queue.monitoring_queue_and_left_out(
        store, graph, analytics, CASE, READER, statuses=["closed"]  # type: ignore[arg-type]
    )  # fmt: skip
    assert shown == [] and left_out is False


async def test_the_queue_says_what_it_left_out_beside_the_list() -> None:
    from services.api import alert_queue

    store, graph, analytics, _ = _world({"e-secret"}, [V1, OVER_LINK, V2])
    shown, left_out = await alert_queue.monitoring_queue_and_left_out(
        store, graph, analytics, CASE, READER  # type: ignore[arg-type]
    )  # fmt: skip
    assert [q.alert.id for q in shown] == ["v1", "v2"] and left_out is True
    # and `monitoring_queue` is the same list, unchanged for every other caller
    again = await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER)  # type: ignore[arg-type]
    assert [q.alert.id for q in again] == ["v1", "v2"]


async def test_held_rows_the_reader_may_not_read_set_the_flag_only_where_the_figures_show_them() -> (
    None
):
    """An editor's held figures leave out a SECRET row for an OFFICIAL reader: flagged. A viewer
    (`show_held` false) is sent no held figure, so a held row lowers nothing for them."""
    held = _Held(["OFFICIAL", "SECRET"])
    figures, flag = await _report(set(), [V1], held=held, show_held=True)
    assert figures.held.held == 1, "the SECRET row is in no figure"
    assert flag is True
    assert held.asked == ["held", "released", "rejected"], "every status the figures count"

    viewer_held = _Held(["OFFICIAL", "SECRET"])
    figures, flag = await _report(set(), [V1], held=viewer_held, show_held=False)
    assert figures.held is None and flag is False
    assert viewer_held.asked == []

    figures, flag = await _report(set(), [V1], held=_Held(["OFFICIAL"]), show_held=True)
    assert figures.held.held == 1 and flag is False


# --- the held store's own query: the flag and the figure are asked the same way -------------------


class _Conn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.answer: dict[str, int] = {"every": 2, "readable": 1}

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        self.calls.append((sql, args))
        return []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, int]:
        self.calls.append((sql, args))
        return self.answer


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self.conn = conn

    @contextlib.asynccontextmanager
    async def acquire(self) -> AsyncIterator[_Conn]:
        yield self.conn


def _store(conn: _Conn) -> HeldRowStore:
    return HeldRowStore(_Pool(conn), load_uk_le_scheme())  # type: ignore[arg-type]


@pytest.mark.parametrize("datasets", [None, ["ds-1"]])
async def test_left_out_for_is_asked_with_the_clauses_and_parameters_of_the_listing(
    datasets: list[str] | None,
) -> None:
    """A flag asked with a looser or different predicate than the figure would say 'nothing left
    out' about rows the figure leaves out. Both queries are made with the same marking and reach
    clauses and the same bound values (red if either drifts)."""
    reader = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1", datasets=datasets)
    conn = _Conn()
    store = _store(conn)
    await store.list_authorized(CASE, reader, status="held")
    assert await store.left_out_for(CASE, reader, status="held") is True
    (listing_sql, listing_args), (flag_sql, flag_args) = conn.calls
    assert flag_args == listing_args
    clauses = listing_sql.split("status = $2", 1)[1].split(" ORDER BY")[0]
    assert clauses.strip().startswith("AND"), listing_sql
    assert f"FILTER (WHERE true{clauses})" in flag_sql
    assert "WHERE investigation_id = $1 AND status = $2" in flag_sql


async def test_left_out_for_is_false_when_the_reader_may_read_every_row() -> None:
    conn = _Conn()
    conn.answer = {"every": 3, "readable": 3}
    store = _store(conn)
    reader = Principal(id="r", clearance="OFFICIAL", org_unit="unit-1")
    assert await store.left_out_for(CASE, reader) is False
