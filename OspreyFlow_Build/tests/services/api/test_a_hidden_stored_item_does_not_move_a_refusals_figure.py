"""A refusal's `would_be` is the same with and without a stored item the reader may not read, at the
routes of two callers of the working set's cap (ADR-124 decision 2; rules 3 and 7).

`POST .../links/{edge_id}/events/documents` asks `ensure_room` before it writes the graph and then
`add_written` to put what it wrote on the canvas, each counting the reader's own view of the case.
The 409 `limit_exceeded` body carries `would_be`; counted over the stored set, it was higher for
a reader in a case that held a node above them, which is how a hidden node was measured.

Each case sends the route the same request against two cases that differ in one stored item the
reader may not read, and asserts the bodies are equal. The first is refused by `ensure_room`; the
second has `ensure_room` let everything through, so that the refusal is `add_written`'s own.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_email_extraction,
    get_investigations,
    get_principal,
    get_valkey,
)
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.working_set import service as service_module
from services.api.working_set.service import WorkingSetService

from schemas.domain import Principal

from .test_email_extraction import _at, _build

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
ROUTE = "/v1/investigations/inv-1/links/e1/events/documents"


class _Audit:
    async def record(self, **kwargs: object) -> None:
        return None


class _Publisher:
    async def publish(self, channel: str, message: str) -> int:
        return 1


class _Cases:
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        if investigation_id != "inv-1":
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(
            id="inv-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="analyst-1",
            owning_unit="unit-1",
        )


@pytest.fixture(autouse=True)
def _clean_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


async def _refusal(
    with_hidden_item: bool, monkeypatch: pytest.MonkeyPatch, *, room_check: bool
) -> dict[str, Any]:
    """The 409 body the route gives for five emails into a case with room for two more nodes of the
    reader's view. `_build`'s case holds a node above ANALYST; `with_hidden_item=False` removes it,
    and the link to it."""
    service, _graph, working, _, _ = await _build([_at(f"ev-{n}", n) for n in range(1, 6)])
    if not with_hidden_item:
        await working.remove_nodes("inv-1", ["c"])
        await working.remove_edges("inv-1", ["secret-end"])
    view_nodes = len(
        [
            n
            for n in (await working.source_fidelity_nodes("inv-1")).values()
            if n.handling.classification == "OFFICIAL"
        ]
    )
    monkeypatch.setattr(service_module, "MAX_NODES", view_nodes + 2)
    if not room_check:

        async def room_for_all(self: WorkingSetService, *args: object, **kwargs: object) -> None:
            return None

        monkeypatch.setattr(WorkingSetService, "ensure_room", room_for_all)
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_investigations] = lambda: _Cases()
    app.dependency_overrides[get_audit] = lambda: _Audit()
    app.dependency_overrides[get_valkey] = lambda: _Publisher()
    app.dependency_overrides[get_email_extraction] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(ROUTE, json={})
    assert response.status_code == 409, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.parametrize("room_check", [True, False], ids=["ensure_room", "add_written"])
async def test_a_refusals_would_be_is_the_same_with_and_without_a_hidden_stored_node(
    monkeypatch: pytest.MonkeyPatch, room_check: bool
) -> None:
    """Violation caught: a cap counted over the stored set. The body names the cap and what the
    request would have taken the reader's view to, which is the reader's view plus five."""
    with_hidden = await _refusal(True, monkeypatch, room_check=room_check)
    monkeypatch.undo()
    without = await _refusal(False, monkeypatch, room_check=room_check)

    assert with_hidden == without
    assert with_hidden["error"] == "limit_exceeded" and with_hidden["cap_kind"] == "nodes"
    assert with_hidden["would_be"] == with_hidden["cap"] + 3  # two of room, five asked: view + 5
