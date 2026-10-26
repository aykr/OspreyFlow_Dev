"""A branch made from what is lit reads only the parent's events inside its window (ADR-128
decision 2, B3; ADR-084 Amendment 2).

The brief's acceptance is that the branch's own timeline starts and ends inside the window. A lit
link can have events outside it, and a branch reads its parent's events on the links it holds, so
without a bound on that read the timeline would be wider than the window. The window is recorded on
the branch case (`Investigation.branch_window`, stored with it) and is applied wherever inherited
events are read, by the Conduit and in the adapter's own query, never in the Glass.

What a mistake here would do, and the case that catches it:

- the window recorded but not applied to a read: a route over the branch showing out-of-window
  events (`test_a_branchs_reads_hold_only_the_in_window_events`);
- a plain branch narrowed by accident (`test_a_plain_branch_still_inherits_every_event`);
- the window applied to the branch's own events (same case: the branch's own event outside it
  still counts);
- a branch of a windowed branch widening again, or the window not stored at all
  (`test_the_window_is_recorded_on_the_branch_and_a_branch_of_it_keeps_it`);
- a reader of inherited events that forgot the window
  (`test_every_reader_of_inherited_events_passes_the_branchs_window`);
- the access filter weakened by the new clause
  (`test_an_event_the_reader_may_not_see_stays_hidden_inside_the_window`).

Real in-memory DuckDB through the real adapter, `FakeWorkingSetStore` under the real service; no
port, no server.
"""

from __future__ import annotations

import ast
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_datasets,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.event_scope import link_event_filter
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.working_set.service import WorkingSetService

from adapters.analytics_duckdb.testing import duckdb_adapter
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventFilter, EventRecord
from schemas.domain import Handling, Interval, Principal, Subgraph

from .test_branch_tabs_routes import ALICE, _FakeInvestigations
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_branch_by_filter import _Datasets, _Recorder
from .working_set.test_visible_link import SCHEME, edge, node

PARENT = "inv-1"
START = datetime(2026, 1, 5, tzinfo=UTC)
END = datetime(2026, 4, 30, tzinfo=UTC)
WINDOW = Interval(valid_from=START, valid_to=END)


def _event(
    scope: str,
    edge_id: str,
    when: datetime,
    level: str = "OFFICIAL",
    src: str = "a",
    dst: str = "b",
) -> Any:
    return EventRecord(
        event_id=f"ev-{scope}-{edge_id}-{when.isoformat()}-{level}",
        edge_id=edge_id,
        edge_type="COMMUNICATED_WITH",
        source_id=src,
        target_id=dst,
        occurred_at=when,
        investigation_scope=scope,
        handling=Handling(
            classification=level, handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
    )


#: `ab`, held by the branch, has events before, on the first instant, inside, on the last instant
#: and after the window; one more inside is SECRET. The branch's own event is outside the window.
EVENTS = [
    _event(PARENT, "ab", datetime(2026, 1, 4, tzinfo=UTC)),
    _event(PARENT, "ab", START),
    _event(PARENT, "ab", datetime(2026, 3, 1, tzinfo=UTC)),
    _event(PARENT, "ab", END),
    _event(PARENT, "ab", datetime(2026, 5, 1, tzinfo=UTC)),
    _event(PARENT, "ab", datetime(2026, 2, 1, tzinfo=UTC), "SECRET"),
    _event("win-case", "ab", datetime(2026, 12, 1, tzinfo=UTC)),
]


class _Cases(_FakeInvestigations):
    """The route tests' fake, with `get`, which the ancestor walk uses, and a record of the window
    each `create` was given."""

    @property
    def windows(self) -> list[Interval | None]:
        return [case.branch_window for case in self.created]

    async def get(self, investigation_id: str) -> Investigation:
        case = self.cases.get(investigation_id)
        if case is None:
            raise InvestigationNotFoundError(investigation_id)
        return case


async def _store(case: str) -> FakeWorkingSetStore:
    held = FakeWorkingSetStore()
    await held.add_nodes(case, [node("a"), node("b")])
    await held.add_edges(case, [edge("ab", "a", "b")])
    return held


@asynccontextmanager
async def _routes(
    reader: Principal = ALICE, window: Interval | None = WINDOW
) -> AsyncIterator[tuple[TestClient, _Cases]]:
    cases = _Cases()
    cases.add("win-case", "A windowed branch", owner=ALICE, branched_from=PARENT)
    cases.cases["win-case"].branch_window = window
    cases.add("plain-case", "A plain branch", owner=ALICE, branched_from=PARENT)
    held = FakeWorkingSetStore()
    for case in ("win-case", "plain-case", PARENT):
        await held.add_nodes(case, [node("a"), node("b")])
        await held.add_edges(case, [edge("ab", "a", "b")])
    recorder = _Recorder()
    async with duckdb_adapter(EVENTS, load_uk_le_scheme()) as analytics:
        graph = FakeGraphPort(Subgraph(nodes=[], edges=[]))
        app.dependency_overrides[get_datasets] = lambda: _Datasets()
        app.dependency_overrides[get_principal] = lambda: reader
        app.dependency_overrides[get_working_set] = lambda: WorkingSetService(graph, held, SCHEME)
        app.dependency_overrides[get_audit] = lambda: recorder
        app.dependency_overrides[get_history] = lambda: recorder
        app.dependency_overrides[get_investigations] = lambda: cases
        app.dependency_overrides[get_valkey] = lambda: recorder
        app.dependency_overrides[get_analytics] = lambda: analytics
        try:
            yield TestClient(app), cases
        finally:
            app.dependency_overrides.clear()


def _histogram(client: TestClient, case: str) -> dict[str, Any]:
    body = {"filter": {"investigation_scope": case}, "interval_seconds": 86_400}
    response = client.post("/v1/analytics/histogram", json=body)
    assert response.status_code == 200, response.text
    return dict(response.json())


def _first_seen(client: TestClient, case: str) -> dict[str, Any]:
    response = client.post(
        "/v1/analytics/first-seen", json={"filter": {"investigation_scope": case}}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_a_branchs_reads_hold_only_the_in_window_events() -> None:
    """The parent's events on `ab`: start, mid and end are in the window (SECRET one is hidden from
    this reader); the branch's own event in December is the branch's own and counts."""
    async with _routes() as (client, _):
        histogram = _histogram(client, "win-case")
        first = _first_seen(client, "win-case")

    assert histogram["total"] == 4
    assert first["edges"]["ab"].startswith("2026-01-05T00:00:00")
    days = {b["start"][:10] for b in histogram["buckets"] if b["count"]}
    assert days == {"2026-01-05", "2026-03-01", "2026-04-30", "2026-12-01"}


async def test_a_plain_branch_still_inherits_every_event() -> None:
    async with _routes() as (client, _):
        plain = _histogram(client, "plain-case")
        first = _first_seen(client, "plain-case")

    assert plain["total"] == 5  # five readable parent events on `ab`, the SECRET one is hidden
    assert first["edges"]["ab"].startswith("2026-01-04T00:00:00")


async def test_an_event_the_reader_may_not_see_stays_hidden_inside_the_window() -> None:
    """The red half: a cleared reader sees the SECRET event inside the window, an OFFICIAL one does
    not, so the window clause does not stand in for the access filter."""
    cleared = ALICE.model_copy(update={"id": "alice-secret", "clearance": "SECRET"})
    async with _routes(cleared) as (client, _):
        seen_by_cleared = _histogram(client, "win-case")["total"]
    async with _routes() as (client, _):
        seen_by_official = _histogram(client, "win-case")["total"]

    assert (seen_by_official, seen_by_cleared) == (4, 5)


async def test_the_window_is_recorded_on_the_branch_and_a_branch_of_it_keeps_it() -> None:
    inner = {
        "valid_from": datetime(2026, 2, 1, tzinfo=UTC).isoformat(),
        "valid_to": datetime(2026, 6, 1, tzinfo=UTC).isoformat(),
    }
    async with _routes() as (client, cases):
        # A branch made with a window records it, intersected with the parent's own window.
        windowed = client.post(
            "/v1/investigations/win-case/branch", json={"node_ids": ["a", "b"], "window": inner}
        )
        # A plain branch of a windowed case keeps the window, so it does not widen again.
        plain = client.post("/v1/investigations/win-case/branch", json={"node_ids": ["a", "b"]})
        # A plain branch of a plain case records none.
        none = client.post("/v1/investigations/plain-case/branch", json={"node_ids": ["a", "b"]})

    assert [r.status_code for r in (windowed, plain, none)] == [201, 201, 201]
    assert cases.windows == [
        Interval(valid_from=datetime(2026, 2, 1, tzinfo=UTC), valid_to=END),
        WINDOW,
        None,
    ]


async def test_the_windowed_branch_route_records_the_window_it_was_sent() -> None:
    body = {
        "node_ids": ["a", "b"],
        "window": {"valid_from": START.isoformat(), "valid_to": END.isoformat()},
    }
    async with _routes(window=None) as (client, cases):
        response = client.post(f"/v1/investigations/{PARENT}/branch", json=body)

    assert response.status_code == 201
    assert cases.windows == [WINDOW]


async def test_link_events_of_a_windowed_branch_carry_the_window() -> None:
    case = Investigation(
        id="win-case",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_by="alice",
        owning_unit="unit-1",
        branched_from=PARENT,
        branch_window=WINDOW,
    )
    cases = _Cases()
    cases.cases[PARENT] = Investigation(
        id=PARENT,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_by="alice",
        owning_unit="unit-1",
    )
    cases.cases["win-case"] = case

    filtered = await link_event_filter(
        cases, EventFilter(investigation_scope="win-case"), "ab", ALICE
    )

    assert filtered.inherited is not None
    assert filtered.inherited.window == WINDOW
    assert json.loads(filtered.model_dump_json())["inherited"]["scopes"] == [PARENT]


def test_every_reader_of_inherited_events_passes_the_branchs_window() -> None:
    """Rule 12: a reader that calls `with_inherited` and forgets the window silently widens a
    branch's events again. Every call in the Conduit names `window=`."""
    root = Path(__file__).resolve().parents[4] / "OspreyFlow_Core" / "services" / "api"
    missing: list[str] = []
    for path in sorted(root.glob("*.py")):
        for call in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "with_inherited"
                and "window" not in {k.arg for k in call.keywords}
            ):
                missing.append(f"{path.name}:{call.lineno}")
    assert missing == []
