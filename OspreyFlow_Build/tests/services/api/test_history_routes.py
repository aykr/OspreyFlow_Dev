"""Route wiring for the named-step history endpoints —
`spec/03_CONDUIT_MIDDLEWARE.md` §3.1, pulled forward as the "named-step
history with restore" capability.

Same style as `test_app.py`: fakes behind `app.dependency_overrides`, never
a live Postgres/Valkey — `InvestigationHistoryStore`'s own SQL is exercised
elsewhere against a real Postgres (`tests/scenarios`), and
`WorkingSetService.restore`'s actual logic (the narrower-clearance
re-projection) is `working_set/test_service.py`'s job. What belongs here is
only "does the right dependency's result end up in the right response, with
the right status code" — including the standing rule that every
investigation-scoped route gets its own access-control test, not one
borrowed from a sibling route.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_history,
    get_investigations,
    get_principal,
    get_valkey,
    get_working_set,
)
from services.api.history import HistoryStep, HistoryStepNotFoundError, HistoryStepSummary
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.working_set.models import DeltaSnapshot

from schemas.domain import Edge, Node, Principal

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
OTHER_UNIT_PRINCIPAL = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])


class _FakeWorkingSet:
    def __init__(self) -> None:
        self.restore_calls: list[tuple[str, str, Principal]] = []

    async def restore(
        self,
        investigation_id: str,
        nodes: list[Node],
        edges: list[Edge],
        principal: Principal,
    ) -> DeltaSnapshot:
        self.restore_calls.append((investigation_id, "restore", principal))
        return DeltaSnapshot(seq=7, nodes=nodes, edges=edges)


class _FakeHistory:
    def __init__(self) -> None:
        self.steps: dict[str, HistoryStep] = {
            "step-1": HistoryStep(
                id="step-1",
                investigation_id="inv-1",
                seq=1,
                label="Seeded 1 node(s)",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                created_by="analyst-1",
                nodes=[],
                edges=[],
            )
        }

    async def list_steps(self, investigation_id: str) -> list[HistoryStepSummary]:
        return [
            HistoryStepSummary(
                id=step.id,
                label=step.label,
                created_at=step.created_at,
                node_count=len(step.nodes),
                edge_count=len(step.edges),
            )
            for step in self.steps.values()
            if step.investigation_id == investigation_id
        ]

    async def get_step(self, investigation_id: str, step_id: str) -> HistoryStep:
        step = self.steps.get(step_id)
        if step is None or step.investigation_id != investigation_id:
            raise HistoryStepNotFoundError(step_id)
        return step


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _FakeInvestigations:
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        # `need` (ADR-052) is accepted and ignored: this fake proves the unit check. The level
        # rules have their own tests in `test_investigation_levels.py`.
        if investigation_id != "inv-1":
            raise InvestigationNotFoundError(investigation_id)
        investigation = Investigation(
            id="inv-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="analyst-1",
            owning_unit="unit-1",
        )
        if investigation.owning_unit != principal.org_unit:
            raise InvestigationNotFoundError(investigation_id)
        return investigation


class _FakeValkeyPublisher:
    async def publish(self, channel: str, message: str) -> int:
        return 1


@pytest.fixture
def client() -> TestClient:
    working_set = _FakeWorkingSet()
    history = _FakeHistory()
    audit = _FakeAudit()

    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_working_set] = lambda: working_set
    app.dependency_overrides[get_history] = lambda: history
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: _FakeInvestigations()
    app.dependency_overrides[get_valkey] = lambda: _FakeValkeyPublisher()

    test_client = TestClient(app)
    test_client.working_set = working_set  # type: ignore[attr-defined]
    test_client.history = history  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_get_history_returns_step_metadata_only(client: TestClient) -> None:
    response = client.get("/v1/investigations/inv-1/history")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": "step-1",
            "label": "Seeded 1 node(s)",
            "created_at": "2026-01-01T00:00:00Z",
            "node_count": 0,
            "edge_count": 0,
        }
    ]
    assert "nodes" not in body[0]  # metadata only — never bodies


def test_get_history_denies_a_principal_in_a_different_org_unit(client: TestClient) -> None:
    app.dependency_overrides[get_principal] = lambda: OTHER_UNIT_PRINCIPAL

    response = client.get("/v1/investigations/inv-1/history")

    assert response.status_code == 404
    assert response.json()["error"] == "investigation_not_found"


def test_restore_returns_the_snapshot_and_publishes_it(client: TestClient) -> None:
    response = client.post("/v1/investigations/inv-1/history/step-1")

    assert response.status_code == 200
    assert response.json()["op"] == "snapshot"
    assert response.json()["seq"] == 7
    assert client.audit.records[-1]["action"] == "restore_history_step"  # type: ignore[attr-defined]


def test_restore_denies_a_principal_in_a_different_org_unit(client: TestClient) -> None:
    app.dependency_overrides[get_principal] = lambda: OTHER_UNIT_PRINCIPAL

    response = client.post("/v1/investigations/inv-1/history/step-1")

    assert response.status_code == 404
    assert response.json()["error"] == "investigation_not_found"
    assert client.working_set.restore_calls == []  # type: ignore[attr-defined]


def test_restore_of_an_unknown_step_returns_404(client: TestClient) -> None:
    response = client.post("/v1/investigations/inv-1/history/no-such-step")

    assert response.status_code == 404
    assert response.json()["error"] == "history_step_not_found"
