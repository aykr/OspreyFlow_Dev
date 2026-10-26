"""Branching what is lit, on the route, over the real analytics adapter (ADR-128 decision 2, B3;
rules 2, 3 and 4).

`POST /v1/investigations/{id}/branch` takes an optional `window`. With one, the server derives the
slice itself: the links with at least one event in the window (inclusive at both ends), read by the
analytics adapter in its own access-filtered query for the branching principal, and the nodes they
touch, kept only where the request names them. Only those links and nodes arrive in the new case.

**What this file is.** The working set is `FakeWorkingSetStore` under the real `WorkingSetService`,
and the events are a real in-memory DuckDB through the real `AnalyticsDuckDBAdapter` (no port, no
server), so the access cases here run the adapter's own `WHERE` clause rather than a stand-in that
keeps what it is told. `tests/services/api/working_set/test_branch_lit.py` has the service's own
rules against a plain list of lit links; this file is the whole path, and is the one to run when
`first_seen` or the access predicate changes.

What a mistake here would do, and the case that catches it:

- a window the route ignored would branch every link among the named nodes
  (`test_the_branch_carries_exactly_the_lit_slice`);
- an event exactly on either end of the window not lighting its link would drop the first or last
  day the analyst brushed (the same case: `ab` has its event on the first instant, `cd` on the
  last);
- an event the principal may not see lighting a link for them would tell them it happened
  (`test_a_link_lit_only_by_an_event_the_reader_may_not_see_is_not_carried`, with its red half);
- a hidden node id answered unlike a made-up one would tell the asker it exists
  (`test_naming_a_hidden_node_answers_as_naming_a_made_up_one`);
- a window ahead of the choice of nodes, or one that runs backwards, being accepted
  (`test_a_window_needs_a_choice_of_nodes_and_must_run_forwards`).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
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
from services.api.working_set import service as service_module
from services.api.working_set.service import WorkingSetService

from adapters.analytics_duckdb.testing import duckdb_adapter
from ontology.handling import load_uk_le_scheme
from schemas.analytics import EventRecord
from schemas.domain import Handling, Principal, Subgraph

from .test_branch_tabs_routes import ALICE, _FakeInvestigations
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_branch_by_filter import _Datasets, _Recorder
from .working_set.test_visible_link import SCHEME, edge, node

CASE = "inv-1"
URL = f"/v1/investigations/{CASE}/branch"
CLEARED = ALICE.model_copy(update={"id": "alice-secret", "clearance": "SECRET"})

#: The window an analyst brushes: both ends are instants, and both are inside it.
START = datetime(2026, 1, 5, tzinfo=UTC)
END = datetime(2026, 4, 30, tzinfo=UTC)
WINDOW = {"valid_from": START.isoformat(), "valid_to": END.isoformat()}


def _event(edge_id: str, source: str, target: str, when: datetime, level: str = "OFFICIAL") -> Any:
    return EventRecord(
        event_id=f"ev-{edge_id}-{when.isoformat()}",
        edge_id=edge_id,
        edge_type="COMMUNICATED_WITH",
        source_id=source,
        target_id=target,
        occurred_at=when,
        investigation_scope=CASE,
        handling=Handling(
            classification=level, handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
    )


#: `ab` has one event before the window and one on its first instant; `cd` has one on its last
#: instant and one after; `bc`'s only event is in the window and is SECRET; `de` has one event
#: outside; `ex` has none (undated); `ah` is lit and its far end, `h`, is SECRET.
EVENTS = [
    _event("ab", "a", "b", datetime(2026, 1, 4, tzinfo=UTC)),
    _event("ab", "a", "b", START),
    _event("bc", "b", "c", datetime(2026, 3, 1, tzinfo=UTC), "SECRET"),
    _event("cd", "c", "d", END),
    _event("cd", "c", "d", datetime(2026, 5, 1, tzinfo=UTC)),
    _event("de", "d", "e", datetime(2026, 12, 1, tzinfo=UTC)),
    _event("ah", "a", "h", datetime(2026, 2, 1, tzinfo=UTC)),
]
EVERYONE = ["a", "b", "c", "d", "e", "x", "h"]


async def _held() -> FakeWorkingSetStore:
    store = FakeWorkingSetStore()
    await store.add_nodes(
        CASE,
        [node("a"), node("b"), node("c"), node("d"), node("e"), node("x"), node("h", "SECRET")],
    )
    await store.add_edges(
        CASE,
        [
            edge("ab", "a", "b"),
            edge("bc", "b", "c"),
            edge("cd", "c", "d"),
            edge("de", "d", "e"),
            edge("ex", "e", "x"),
            edge("ah", "a", "h"),
        ],
    )
    return store


class _Seen:
    """What the route asked the analytics port, kept so a case can say what it was asked."""

    def __init__(self, analytics: Any) -> None:
        self._analytics = analytics
        self.filters: list[Any] = []

    async def first_seen(self, req: Any, principal: Principal) -> Any:
        self.filters.append(req.filter)
        return await self._analytics.first_seen(req, principal)


@asynccontextmanager
async def _route(
    store: FakeWorkingSetStore, reader: Principal = ALICE
) -> AsyncIterator[tuple[TestClient, _Recorder, _FakeInvestigations, _Seen]]:
    recorder = _Recorder()
    investigations = _FakeInvestigations()
    datasets = _Datasets()
    async with duckdb_adapter(EVENTS, load_uk_le_scheme()) as analytics:
        seen = _Seen(analytics)
        graph = FakeGraphPort(Subgraph(nodes=[], edges=[]))
        app.dependency_overrides[get_datasets] = lambda: datasets
        app.dependency_overrides[get_principal] = lambda: reader
        app.dependency_overrides[get_working_set] = lambda: WorkingSetService(graph, store, SCHEME)
        app.dependency_overrides[get_audit] = lambda: recorder
        app.dependency_overrides[get_history] = lambda: recorder
        app.dependency_overrides[get_investigations] = lambda: investigations
        app.dependency_overrides[get_valkey] = lambda: recorder
        app.dependency_overrides[get_analytics] = lambda: seen
        try:
            yield TestClient(app), recorder, investigations, seen
        finally:
            app.dependency_overrides.clear()


def _published(recorder: _Recorder) -> tuple[set[str], set[str]]:
    (published,) = recorder.published
    delta = json.loads(published[1])
    return {n["id"] for n in delta["nodes"]}, {e["id"] for e in delta["edges"]}


async def test_the_branch_carries_exactly_the_lit_slice() -> None:
    async with _route(await _held()) as (client, recorder, investigations, seen):
        response = client.post(
            URL, json={"node_ids": EVERYONE, "window": WINDOW, "name": "5 Jan – 30 Apr 2026"}
        )

    assert response.status_code == 201
    assert response.json()["name"] == "5 Jan – 30 Apr 2026"
    # `ab` (an event on the first instant) and `cd` (one on the last) are lit; `bc` is not for this
    # reader; `de` has no event in the window; `ex` has none at all; `ah` reaches a node above them.
    assert _published(recorder) == ({"a", "b", "c", "d"}, {"ab", "cd"})
    (asked,) = seen.filters
    assert asked.investigation_scope == CASE
    assert asked.window is not None
    assert (asked.window.valid_from, asked.window.valid_to) == (START, END)
    assert [c.id for c in investigations.created] == [response.json()["id"]]


async def test_a_branch_with_no_window_is_unchanged_and_asks_analytics_nothing() -> None:
    async with _route(await _held()) as (client, recorder, _, seen):
        response = client.post(URL, json={"node_ids": ["a", "b", "c"]})

    assert response.status_code == 201
    assert seen.filters == []
    assert _published(recorder) == ({"a", "b", "c"}, {"ab", "bc"})


async def test_only_the_nodes_the_request_names_are_carried() -> None:
    async with _route(await _held()) as (client, recorder, _, _):
        response = client.post(URL, json={"node_ids": ["a", "b"], "window": WINDOW})

    assert response.status_code == 201
    assert _published(recorder) == ({"a", "b"}, {"ab"})


async def test_a_link_lit_only_by_an_event_the_reader_may_not_see_is_not_carried() -> None:
    """Violation caught (rule 3): `bc`'s only event in the window is SECRET. For an OFFICIAL reader
    the link is not lit; for a cleared one it is, and the red half is that the filter is real."""
    async with _route(await _held()) as (client, recorder, _, _):
        client.post(URL, json={"node_ids": EVERYONE, "window": WINDOW})
        official = _published(recorder)
    async with _route(await _held(), CLEARED) as (client, recorder, _, _):
        client.post(URL, json={"node_ids": EVERYONE, "window": WINDOW})
        cleared = _published(recorder)

    assert "bc" not in official[1]
    assert cleared == ({"a", "b", "c", "d", "h"}, {"ab", "bc", "cd", "ah"})


async def test_naming_a_hidden_node_answers_as_naming_a_made_up_one() -> None:
    """Violation caught (rule 3): `h` exists, is above the reader, and is joined to `a` by a lit
    link. Whether it is named beside others or alone, the response, the slice written, and the
    cases created are what naming `ghost` gives."""
    traces = []
    for extra in ("h", "ghost"):
        async with _route(await _held()) as (client, recorder, investigations, _):
            beside = client.post(URL, json={"node_ids": ["a", "b", extra], "window": WINDOW})
            traces.append(
                (
                    beside.status_code,
                    beside.json(),
                    [(c.id, c.name) for c in investigations.created],
                    recorder.published,
                    recorder.steps,
                )
            )
    assert traces[0] == traces[1]
    assert traces[0][0] == 201

    alone_traces = []
    for only in ("h", "ghost"):
        async with _route(await _held()) as (client, recorder, investigations, _):
            alone = client.post(URL, json={"node_ids": [only], "window": WINDOW})
            alone_traces.append(
                (alone.status_code, alone.json(), investigations.created, recorder.steps)
            )
    assert alone_traces[0] == alone_traces[1]
    assert alone_traces[0][0] == 422 and alone_traces[0][1] == {"error": "nothing_to_branch"}


async def test_a_window_with_no_event_in_it_leaves_nothing_and_no_case() -> None:
    quiet = {
        "valid_from": datetime(2030, 1, 1, tzinfo=UTC).isoformat(),
        "valid_to": datetime(2030, 2, 1, tzinfo=UTC).isoformat(),
    }
    async with _route(await _held()) as (client, recorder, investigations, _):
        response = client.post(URL, json={"node_ids": EVERYONE, "window": quiet})

    assert response.status_code == 422 and response.json() == {"error": "nothing_to_branch"}
    assert investigations.created == [] and recorder.published == []


async def test_a_window_needs_a_choice_of_nodes_and_must_run_forwards() -> None:
    backwards = {"valid_from": END.isoformat(), "valid_to": START.isoformat()}
    async with _route(await _held()) as (client, recorder, investigations, seen):
        without_nodes = client.post(URL, json={"window": WINDOW})
        reversed_window = client.post(URL, json={"node_ids": ["a"], "window": backwards})

    assert without_nodes.status_code == 422
    assert reversed_window.status_code == 422
    assert investigations.created == [] and recorder.published == [] and seen.filters == []


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "MAX_NODES", 3)


async def test_a_slice_past_the_cap_answers_limit_exceeded_and_creates_no_case(
    small_cap: None,
) -> None:
    async with _route(await _held()) as (client, recorder, investigations, _):
        response = client.post(URL, json={"node_ids": EVERYONE, "window": WINDOW})

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "limit_exceeded"
    assert (body["cap_kind"], body["cap"], body["would_be"]) == ("nodes", 3, 4)
    assert body["options"] == ["branch", "filter", "promote_to_batch"]
    assert investigations.created == [] and recorder.published == [] and recorder.steps == []


async def test_a_branch_of_what_is_lit_is_audited_with_its_window() -> None:
    async with _route(await _held()) as (client, _, _, _):
        audited: list[dict[str, Any]] = []

        class _Audit:
            async def record(self, **kwargs: Any) -> None:
                audited.append(kwargs)

        app.dependency_overrides[get_audit] = lambda: _Audit()
        client.post(URL, json={"node_ids": ["a", "b"], "window": WINDOW})

    (branch,) = [r for r in audited if r["action"] == "branch"]
    assert branch["resolved_query"]["window"] == {
        "valid_from": START.isoformat().replace("+00:00", "Z"),
        "valid_to": END.isoformat().replace("+00:00", "Z"),
    }
