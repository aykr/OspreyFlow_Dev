"""`POST .../links/{edge}/change` and `GET .../links/{edge}/history` route wiring — ADR-080. The
service's own rules are `test_link_changes.py`; this file proves each route calls it with the right
arguments, publishes the replace step, audits with the reason and the old and new values, and maps
each refusal to the status and body the Glass words its message from."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_investigations,
    get_link_changes,
    get_principal,
    get_valkey,
)
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.link_changes import (
    ChangeNotMadeError,
    InvalidChangeError,
    LinkChange,
    LinkChangeRequest,
    LinkChangeResult,
    LinkHistoryResponse,
    ResolutionLinkError,
)
from services.api.link_notes import LinkNotFoundError
from services.api.working_set.models import DeltaReplaceEdge

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
WHEN = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _edge(edge_id: str, type_: str) -> Edge:
    return Edge(
        id=edge_id,
        type=type_,
        source="a",
        target="b",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="a" * 64)],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="u", owning_unit="unit-1"
        ),
        audit=AuditStub(created_at=WHEN, created_by="analyst-1", revision=2),
    )


def _change() -> LinkChange:
    return LinkChange(
        id="c1",
        investigation_id="inv-1",
        edge_id="e2",
        previous_edge_id="e1",
        changed_by="analyst-1",
        changed_at=WHEN,
        reason="Told so",
        before={"type": "ASSOCIATE_OF"},
        after={"type": "FAMILY_OF"},
    )


class _FakeLinkChanges:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Principal, LinkChangeRequest]] = []
        self.history_calls: list[tuple[str, str, Principal]] = []
        self.error: Exception | None = None

    async def change(
        self, investigation_id: str, edge_id: str, principal: Principal, request: LinkChangeRequest
    ) -> LinkChangeResult:
        self.calls.append((investigation_id, edge_id, principal, request))
        if self.error is not None:
            raise self.error
        edge = _edge("e2", "FAMILY_OF")
        return LinkChangeResult(
            edge=edge,
            delta=DeltaReplaceEdge(seq=7, old_edge_id=edge_id, edge=edge),
            change=_change(),
        )

    async def history(
        self, investigation_id: str, edge_id: str, principal: Principal
    ) -> LinkHistoryResponse:
        self.history_calls.append((investigation_id, edge_id, principal))
        if self.error is not None:
            raise self.error
        return LinkHistoryResponse(changes=[_change()])


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _FakeInvestigations:
    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: object = None
    ) -> Investigation:
        if investigation_id != "inv-1":
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(
            id="inv-1", created_at=WHEN, created_by="analyst-1", owning_unit="unit-1"
        )


class _FakeValkey:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


@pytest.fixture
def client() -> TestClient:
    service, audit, valkey = _FakeLinkChanges(), _FakeAudit(), _FakeValkey()
    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_link_changes] = lambda: service
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: _FakeInvestigations()
    app.dependency_overrides[get_valkey] = lambda: valkey
    test_client = TestClient(app)
    test_client.service = service  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    test_client.valkey = valkey  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


URL = "/v1/investigations/inv-1/links/e1"


def test_a_change_calls_the_service_and_returns_the_new_link_and_the_replace_step(
    client: TestClient,
) -> None:
    response = client.post(f"{URL}/change", json={"type": "FAMILY_OF", "reason": "Told so"})
    assert response.status_code == 200
    body = response.json()
    assert body["edge"]["id"] == "e2"
    assert body["delta"]["op"] == "replace_edge"
    assert body["delta"]["old_edge_id"] == "e1"
    [(inv, edge_id, principal, request)] = client.service.calls  # type: ignore[attr-defined]
    assert (inv, edge_id, principal) == ("inv-1", "e1", PRINCIPAL)
    assert request.type == "FAMILY_OF"
    assert request.reason == "Told so"


def test_a_change_is_published_so_other_screens_see_it(client: TestClient) -> None:
    client.post(f"{URL}/change", json={"type": "FAMILY_OF", "reason": "Told so"})
    assert len(client.valkey.published) == 1  # type: ignore[attr-defined]


def test_a_change_is_audited_with_the_reason_and_the_old_and_new_values(
    client: TestClient,
) -> None:
    client.post(f"{URL}/change", json={"type": "FAMILY_OF", "reason": "Told so"})
    [record] = client.audit.records  # type: ignore[attr-defined]
    assert record["action"] == "link_change"
    assert record["justification"] == "Told so"
    assert record["investigation_id"] == "inv-1"
    assert record["principal"] == PRINCIPAL
    assert record["resolved_query"] == {
        "edge_id": "e1",
        "new_edge_id": "e2",
        "before": {"type": "ASSOCIATE_OF"},
        "after": {"type": "FAMILY_OF"},
    }


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LinkNotFoundError("e1"), 404, "link_not_found"),
        (InvalidChangeError("Say why."), 422, "invalid_link_change"),
        (ChangeNotMadeError("Nothing about the link would change."), 422, "nothing_changed"),
        (ResolutionLinkError("Same-as links are confirmed or not."), 422, "resolution_link"),
    ],
)
def test_each_refusal_has_its_own_status_and_nothing_is_published_or_audited(
    client: TestClient, error: Exception, status: int, code: str
) -> None:
    client.service.error = error  # type: ignore[attr-defined]
    response = client.post(f"{URL}/change", json={"type": "FAMILY_OF", "reason": "r"})
    assert response.status_code == status
    assert response.json()["error"] == code
    assert client.valkey.published == []  # type: ignore[attr-defined]
    assert client.audit.records == []  # type: ignore[attr-defined]


def test_a_change_without_a_reason_field_is_refused_before_the_service_runs(
    client: TestClient,
) -> None:
    response = client.post(f"{URL}/change", json={"type": "FAMILY_OF"})
    assert response.status_code == 422
    assert client.service.calls == []  # type: ignore[attr-defined]


def test_an_unknown_field_is_refused_so_a_marking_cannot_be_smuggled_in(
    client: TestClient,
) -> None:
    response = client.post(
        f"{URL}/change",
        json={"type": "FAMILY_OF", "reason": "r", "handling": {"classification": "PUBLIC"}},
    )
    assert response.status_code == 422
    assert client.service.calls == []  # type: ignore[attr-defined]


def test_the_history_is_read_through_the_service_with_the_principal(client: TestClient) -> None:
    response = client.get(f"{URL}/history")
    assert response.status_code == 200
    assert response.json()["changes"][0]["reason"] == "Told so"
    assert client.service.history_calls == [("inv-1", "e1", PRINCIPAL)]  # type: ignore[attr-defined]


def test_the_history_of_a_link_the_principal_cannot_see_is_a_plain_404(
    client: TestClient,
) -> None:
    client.service.error = LinkNotFoundError("e1")  # type: ignore[attr-defined]
    response = client.get(f"{URL}/history")
    assert response.status_code == 404
    assert response.json() == {"error": "link_not_found"}


def test_a_principal_in_another_org_unit_cannot_change_or_read_history(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_principal] = lambda: Principal(
        id="analyst-2", clearance="OFFICIAL", org_unit="unit-2"
    )
    # `_FakeInvestigations` above always authorises; use one that applies the unit rule.

    class _UnitChecked(_FakeInvestigations):
        async def get_authorized(
            self, investigation_id: str, principal: Principal, *, need: object = None
        ) -> Investigation:
            investigation = await super().get_authorized(investigation_id, principal, need=need)
            if investigation.owning_unit != principal.org_unit:
                raise InvestigationNotFoundError(investigation_id)
            return investigation

    app.dependency_overrides[get_investigations] = lambda: _UnitChecked()
    assert client.post(f"{URL}/change", json={"type": "X", "reason": "r"}).status_code == 404
    assert client.get(f"{URL}/history").status_code == 404
    assert client.service.calls == []  # type: ignore[attr-defined]
    assert client.service.history_calls == []  # type: ignore[attr-defined]
