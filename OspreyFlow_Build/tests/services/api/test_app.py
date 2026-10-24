"""HTTP route wiring for the Conduit's FastAPI app —
`spec/03_CONDUIT_MIDDLEWARE.md` §3.1/§3.2. Exercises dependency injection,
status codes and the typed-error exception handlers against
`app.dependency_overrides`, never against a live ArcadeDB/Valkey/Postgres:
`WorkingSetService`, `AuditWriter` and `InvestigationStore`'s own
correctness is proven elsewhere (`test_service.py`, live-infra scenario
tests); what belongs here is only "does the right dependency's result end
up in the right response, with the right status code".
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
from services.api.audit import AuditWriteError
from services.api.history import HistoryStep
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.working_set.models import (
    DeltaAdd,
    ExpansionOutcome,
    LimitExceeded,
    LimitExceededError,
)

from schemas.domain import (
    AuditStub,
    Edge,
    ExpandRequest,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])


def _node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="doc-1", locator="p.1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


class _FakeWorkingSet:
    def __init__(self) -> None:
        self.expand_error: Exception | None = None

    async def seed(
        self,
        investigation_id: str,
        nodes: list[Node],
        edges: list[Edge],
        principal: Principal,
    ) -> ExpansionOutcome:
        return ExpansionOutcome(delta=DeltaAdd(seq=1, nodes=nodes, edges=edges))

    async def expand(
        self, investigation_id: str, req: ExpandRequest, principal: Principal
    ) -> ExpansionOutcome:
        if self.expand_error is not None:
            raise self.expand_error
        return ExpansionOutcome(delta=DeltaAdd(seq=2, nodes=[_node("hub")], edges=[]))

    async def current_membership(
        self, investigation_id: str
    ) -> tuple[list[Node], list[Edge]]:
        """Route-wiring tests below only assert on the seed/expand/branch/
        remove response itself, not on what a history step recorded — a
        fixed empty snapshot is enough; `working_set/test_service.py`
        exercises `current_membership`/`restore`'s real logic."""
        return [], []


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []
        self.raise_on_action: str | None = None

    async def record(self, **kwargs: object) -> None:
        if kwargs.get("action") == self.raise_on_action:
            raise AuditWriteError("simulated audit outage")
        self.records.append(kwargs)


class _FakeInvestigations:
    def __init__(self) -> None:
        self.created: Investigation | None = None

    async def create(
        self,
        principal: Principal,
        *,
        name: str,
        branched_from: str | None = None,
        domains: list[str] | None = None,
    ) -> Investigation:
        self.created = Investigation(
            id="inv-1",
            name=name,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=principal.id,
            owning_unit=principal.org_unit,
            branched_from=branched_from,
        )
        return self.created

    async def get(self, investigation_id: str) -> Investigation:
        if investigation_id != "inv-1":
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(
            id="inv-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="analyst-1",
            owning_unit="unit-1",
        )

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        # `need` (ADR-052) is accepted and ignored: this fake proves the unit check. The level
        # rules have their own tests in `test_investigation_levels.py`.
        investigation = await self.get(investigation_id)
        if investigation.owning_unit != principal.org_unit:
            raise InvestigationNotFoundError(investigation_id)
        return investigation


class _FakeHistory:
    def __init__(self) -> None:
        self.recorded: list[dict[str, object]] = []

    async def record_step(
        self,
        investigation_id: str,
        *,
        seq: int,
        label: str,
        created_by: str,
        nodes: list[Node],
        edges: list[Edge],
    ) -> HistoryStep:
        step = HistoryStep(
            id=f"step-{len(self.recorded) + 1}",
            investigation_id=investigation_id,
            seq=seq,
            label=label,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by=created_by,
            nodes=nodes,
            edges=edges,
        )
        self.recorded.append(
            {"investigation_id": investigation_id, "seq": seq, "label": label}
        )
        return step


class _FakeValkeyPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


@pytest.fixture
def client() -> TestClient:
    working_set = _FakeWorkingSet()
    audit = _FakeAudit()
    investigations = _FakeInvestigations()
    history = _FakeHistory()
    valkey = _FakeValkeyPublisher()

    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_working_set] = lambda: working_set
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: investigations
    app.dependency_overrides[get_history] = lambda: history
    app.dependency_overrides[get_valkey] = lambda: valkey

    test_client = TestClient(app)
    test_client.working_set = working_set  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    test_client.investigations = investigations  # type: ignore[attr-defined]
    test_client.history = history  # type: ignore[attr-defined]
    test_client.valkey = valkey  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_create_investigation_returns_201_and_audits(client: TestClient) -> None:
    response = client.post("/v1/investigations")

    assert response.status_code == 201
    assert response.json()["id"] == "inv-1"
    assert client.audit.records[0]["action"] == "create_investigation"  # type: ignore[attr-defined]


def test_get_investigation_returns_404_for_an_unknown_id(client: TestClient) -> None:
    response = client.get("/v1/investigations/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"] == "investigation_not_found"


def test_get_investigation_denies_a_principal_in_a_different_org_unit(
    client: TestClient,
) -> None:
    """Divergence-review fix #1: `owning_unit` gates the investigation
    itself, not just node/edge content. A principal in a different unit
    gets the *same* 404 an unknown id would — existence-leak discipline
    extended to the investigation id, per `investigations.py`'s
    `InvestigationNotFoundError` docstring."""
    other_unit_principal = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2", roles=["analyst"])
    app.dependency_overrides[get_principal] = lambda: other_unit_principal

    response = client.get("/v1/investigations/inv-1")

    assert response.status_code == 404
    assert response.json()["error"] == "investigation_not_found"
    assert client.audit.records[-1]["action"] == "access_denied"  # type: ignore[attr-defined]


def test_seed_publishes_the_delta_and_audits(client: TestClient) -> None:
    body = {"nodes": [_node("n1").model_dump(mode="json")], "edges": []}

    response = client.post("/v1/investigations/inv-1/seed", json=body)

    assert response.status_code == 200
    assert response.json()["delta"]["nodes"][0]["id"] == "n1"
    assert client.valkey.published  # type: ignore[attr-defined]
    assert client.audit.records[-1]["action"] == "seed"  # type: ignore[attr-defined]


def test_expand_past_the_cap_returns_409_with_the_typed_body(client: TestClient) -> None:
    detail = LimitExceeded(cap_kind="nodes", cap=50_000, would_be=50_001)
    client.working_set.expand_error = LimitExceededError(detail)  # type: ignore[attr-defined]

    response = client.post(
        "/v1/investigations/inv-1/expand",
        json={"request": {"node_ids": ["a"], "depth": 1}},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "limit_exceeded"
    assert body["cap_kind"] == "nodes"
    assert set(body["options"]) == {"branch", "filter", "promote_to_batch"}


def test_expand_answers_with_no_count_of_what_was_withheld(client: TestClient) -> None:
    """ADR-124 decision 1: the response is the delta and the links-among note, and no figure for
    what the filter left out (`filtered_count` was removed, not held at 0)."""
    response = client.post(
        "/v1/investigations/inv-1/expand",
        json={"request": {"node_ids": ["a"], "depth": 1}},
    )

    assert response.status_code == 200
    assert set(response.json()) == {"delta", "links_among"}


def test_seed_answers_with_no_count_of_what_was_withheld(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/seed",
        json={"nodes": [], "edges": []},
    )

    assert response.status_code == 200
    assert set(response.json()) == {"delta", "links_among"}


def test_an_audit_write_failure_returns_503_and_discloses_nothing(client: TestClient) -> None:
    client.audit.raise_on_action = "seed"  # type: ignore[attr-defined]

    response = client.post(
        "/v1/investigations/inv-1/seed",
        json={"nodes": [_node("n1").model_dump(mode="json")], "edges": []},
    )

    assert response.status_code == 503
    assert response.json()["error"] == "audit_unavailable"
    assert "nodes" not in response.json()  # nothing about the seeded nodes reaches the caller
