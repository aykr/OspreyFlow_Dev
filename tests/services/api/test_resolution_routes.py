"""`GET`/`PUT /v1/investigations/{investigation_id}/resolution/threshold`, `POST .../link`,
`POST .../split`, `GET .../explain/{cluster_id}` route wiring — `docs/03_CONDUIT_MIDDLEWARE.md`
§3.5. `WorkingSetService`'s own logic is proven in `tests/services/api/working_set/
test_resolution_threshold.py`/`test_manual_resolution.py`; this file only proves each route calls
it with the right arguments, publishes the delta where one exists, and audits — the same split
`test_search_route.py` and `test_app.py` already establish for this app.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_alerts_store,
    get_audit,
    get_config,
    get_graph,
    get_handling_scheme,
    get_hotlists_store,
    get_investigations,
    get_monitors_store,
    get_patterns_store,
    get_principal,
    get_principal_resolver,
    get_valkey,
    get_working_set,
)
from services.api.change_stream import ChangeStreamEntry
from services.api.investigations import Investigation, InvestigationNotFoundError
from services.api.working_set.models import (
    ClusterExplanation,
    ClusterNotFoundError,
    DeltaReproject,
    NodeNotInWorkingSetError,
    PairwiseExplanation,
    SameNodeAssertionError,
)

from schemas.domain import Principal

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")


class _FakeWorkingSet:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, Principal]] = []
        self.link_calls: list[tuple[str, str, str, Principal]] = []
        self.split_calls: list[tuple[str, str, str, Principal]] = []
        self.explain_calls: list[tuple[str, str, Principal]] = []
        self.threshold = 0.95
        self.link_error: Exception | None = None
        self.split_error: Exception | None = None
        self.explain_error: Exception | None = None
        self.explanation = ClusterExplanation(
            cluster_id="n1", member_node_ids=["n1", "n2"], pairs=[]
        )

    async def get_resolution_threshold(self, investigation_id: str) -> float:
        return self.threshold

    async def set_resolution_threshold(
        self, investigation_id: str, tau: float, principal: Principal
    ) -> DeltaReproject:
        self.calls.append((investigation_id, tau, principal))
        self.threshold = tau
        return DeltaReproject(seq=1, reason="test", merged=1, split=0, affected=2)

    async def manual_link(
        self, investigation_id: str, node_a: str, node_b: str, principal: Principal
    ) -> tuple[DeltaReproject, ChangeStreamEntry | None]:
        self.link_calls.append((investigation_id, node_a, node_b, principal))
        if self.link_error is not None:
            raise self.link_error
        # `entry=None` — this file only proves route wiring (see its own module docstring); a
        # non-`None` entry would exercise `_evaluate_watches_best_effort`'s own live-store path,
        # which `test_evaluation.py` already covers with real fakes at the right grain.
        return DeltaReproject(seq=2, reason="manual link", merged=1, split=0, affected=2), None

    async def manual_split(
        self, investigation_id: str, node_a: str, node_b: str, principal: Principal
    ) -> tuple[DeltaReproject, ChangeStreamEntry | None]:
        self.split_calls.append((investigation_id, node_a, node_b, principal))
        if self.split_error is not None:
            raise self.split_error
        return DeltaReproject(seq=3, reason="manual split", merged=0, split=1, affected=2), None

    async def explain_cluster(
        self, investigation_id: str, cluster_id: str, principal: Principal
    ) -> ClusterExplanation:
        self.explain_calls.append((investigation_id, cluster_id, principal))
        if self.explain_error is not None:
            raise self.explain_error
        return self.explanation


class _FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _FakeInvestigations:
    async def get_authorized(self, investigation_id: str, principal: Principal) -> Investigation:
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
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


@pytest.fixture
def client() -> TestClient:
    working_set = _FakeWorkingSet()
    audit = _FakeAudit()
    valkey = _FakeValkeyPublisher()

    app.dependency_overrides[get_principal] = lambda: PRINCIPAL
    app.dependency_overrides[get_working_set] = lambda: working_set
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = lambda: _FakeInvestigations()
    app.dependency_overrides[get_valkey] = lambda: valkey
    # `link_resolution_route`'s own Stage 6c evaluation wiring (`app.py`) — never reached by this
    # file's own fakes, since `_FakeWorkingSet.manual_link` always returns `entry=None`, so these
    # only need to satisfy FastAPI's dependency graph, not behave like the real stores.
    app.dependency_overrides[get_handling_scheme] = lambda: None
    app.dependency_overrides[get_principal_resolver] = lambda: None
    app.dependency_overrides[get_config] = lambda: None
    app.dependency_overrides[get_graph] = lambda: None
    app.dependency_overrides[get_hotlists_store] = lambda: None
    app.dependency_overrides[get_monitors_store] = lambda: None
    app.dependency_overrides[get_patterns_store] = lambda: None
    app.dependency_overrides[get_alerts_store] = lambda: None

    test_client = TestClient(app)
    test_client.working_set = working_set  # type: ignore[attr-defined]
    test_client.audit = audit  # type: ignore[attr-defined]
    test_client.valkey = valkey  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_get_threshold_returns_the_current_session_value(client: TestClient) -> None:
    response = client.get("/v1/investigations/inv-1/resolution/threshold")

    assert response.status_code == 200
    assert response.json() == {"threshold": 0.95}
    assert client.audit.records[-1]["action"] == "get_resolution_threshold"  # type: ignore[attr-defined]


def test_put_threshold_calls_the_service_and_returns_the_reproject_delta(
    client: TestClient,
) -> None:
    response = client.put("/v1/investigations/inv-1/resolution/threshold", json={"threshold": 0.80})

    assert response.status_code == 200
    body = response.json()
    assert body["op"] == "reproject"
    assert body["merged"] == 1
    assert body["split"] == 0
    assert body["affected"] == 2
    assert client.working_set.calls == [("inv-1", 0.80, PRINCIPAL)]  # type: ignore[attr-defined]


def test_put_threshold_publishes_the_delta(client: TestClient) -> None:
    client.put("/v1/investigations/inv-1/resolution/threshold", json={"threshold": 0.80})

    assert len(client.valkey.published) == 1  # type: ignore[attr-defined]
    channel, _message = client.valkey.published[0]  # type: ignore[attr-defined]
    assert "inv-1" in channel


def test_put_threshold_audits_with_the_new_value(client: TestClient) -> None:
    client.put("/v1/investigations/inv-1/resolution/threshold", json={"threshold": 0.80})

    record = client.audit.records[-1]  # type: ignore[attr-defined]
    assert record["action"] == "set_resolution_threshold"
    assert record["resolved_query"] == {"threshold": 0.80}


def test_put_threshold_rejects_a_value_outside_zero_to_one(client: TestClient) -> None:
    response = client.put("/v1/investigations/inv-1/resolution/threshold", json={"threshold": 1.5})
    assert response.status_code == 422


def test_threshold_routes_404_for_an_unknown_investigation(client: TestClient) -> None:
    response = client.get("/v1/investigations/no-such-inv/resolution/threshold")
    assert response.status_code == 404


def test_get_threshold_denies_a_principal_in_a_different_org_unit(client: TestClient) -> None:
    """`CLAUDE.md` rule 4: every read path gets its own access-control test, no exceptions for an
    internal endpoint — mirrors `test_app.py`'s
    `test_get_investigation_denies_a_principal_in_a_different_org_unit`."""
    other_unit_principal = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")
    app.dependency_overrides[get_principal] = lambda: other_unit_principal

    response = client.get("/v1/investigations/inv-1/resolution/threshold")

    assert response.status_code == 404
    assert response.json()["error"] == "investigation_not_found"


def test_put_threshold_denies_a_principal_in_a_different_org_unit(client: TestClient) -> None:
    other_unit_principal = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")
    app.dependency_overrides[get_principal] = lambda: other_unit_principal

    response = client.put("/v1/investigations/inv-1/resolution/threshold", json={"threshold": 0.80})

    assert response.status_code == 404
    assert client.working_set.calls == []  # type: ignore[attr-defined]


def test_post_link_calls_the_service_and_returns_the_reproject_delta(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/resolution/link", json={"node_a": "n1", "node_b": "n2"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["op"] == "reproject"
    assert body["merged"] == 1
    assert client.working_set.link_calls == [("inv-1", "n1", "n2", PRINCIPAL)]  # type: ignore[attr-defined]


def test_post_link_publishes_the_delta_and_audits(client: TestClient) -> None:
    client.post("/v1/investigations/inv-1/resolution/link", json={"node_a": "n1", "node_b": "n2"})

    assert len(client.valkey.published) == 1  # type: ignore[attr-defined]
    record = client.audit.records[-1]  # type: ignore[attr-defined]
    assert record["action"] == "manual_link"
    assert record["resolved_query"] == {"node_a": "n1", "node_b": "n2"}


def test_post_link_returns_404_when_a_node_is_not_in_the_working_set(
    client: TestClient,
) -> None:
    client.working_set.link_error = NodeNotInWorkingSetError("n1, n2")  # type: ignore[attr-defined]

    response = client.post(
        "/v1/investigations/inv-1/resolution/link", json={"node_a": "n1", "node_b": "n2"}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "node_not_in_working_set"


def test_post_link_denies_a_principal_in_a_different_org_unit(client: TestClient) -> None:
    other_unit_principal = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")
    app.dependency_overrides[get_principal] = lambda: other_unit_principal

    response = client.post(
        "/v1/investigations/inv-1/resolution/link", json={"node_a": "n1", "node_b": "n2"}
    )

    assert response.status_code == 404
    assert client.working_set.link_calls == []  # type: ignore[attr-defined]


def test_post_split_calls_the_service_and_returns_the_reproject_delta(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/resolution/split", json={"node_a": "n1", "node_b": "n2"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["split"] == 1
    assert client.working_set.split_calls == [("inv-1", "n1", "n2", PRINCIPAL)]  # type: ignore[attr-defined]


def test_post_split_returns_422_for_the_same_node_twice(client: TestClient) -> None:
    client.working_set.split_error = SameNodeAssertionError("n1")  # type: ignore[attr-defined]

    response = client.post(
        "/v1/investigations/inv-1/resolution/split", json={"node_a": "n1", "node_b": "n1"}
    )

    assert response.status_code == 422
    assert response.json()["error"] == "same_node_assertion"


def test_post_split_denies_a_principal_in_a_different_org_unit(client: TestClient) -> None:
    other_unit_principal = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")
    app.dependency_overrides[get_principal] = lambda: other_unit_principal

    response = client.post(
        "/v1/investigations/inv-1/resolution/split", json={"node_a": "n1", "node_b": "n2"}
    )

    assert response.status_code == 404
    assert client.working_set.split_calls == []  # type: ignore[attr-defined]


def test_get_explain_returns_the_cluster_explanation(client: TestClient) -> None:
    client.working_set.explanation = ClusterExplanation(  # type: ignore[attr-defined]
        cluster_id="n1",
        member_node_ids=["n1", "n2"],
        pairs=[
            PairwiseExplanation(
                node_a="n1",
                node_b="n2",
                edge_type="SAME_AS",
                score=0.97,
                model_version="splink-3.9.9-config-1",
                comparison_vector={"match_weight": 5.1},
                manually_asserted=False,
                meets_threshold=True,
            )
        ],
    )

    response = client.get("/v1/investigations/inv-1/resolution/explain/n1")

    assert response.status_code == 200
    body = response.json()
    assert body["cluster_id"] == "n1"
    assert body["pairs"][0]["score"] == 0.97
    assert client.working_set.explain_calls == [("inv-1", "n1", PRINCIPAL)]  # type: ignore[attr-defined]


def test_get_explain_audits_with_the_pair_count(client: TestClient) -> None:
    client.get("/v1/investigations/inv-1/resolution/explain/n1")

    record = client.audit.records[-1]  # type: ignore[attr-defined]
    assert record["action"] == "explain_resolution_cluster"
    assert record["resolved_query"] == {"cluster_id": "n1"}


def test_get_explain_returns_404_for_an_unknown_cluster(client: TestClient) -> None:
    client.working_set.explain_error = ClusterNotFoundError("no-such-cluster")  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/resolution/explain/no-such-cluster")

    assert response.status_code == 404
    assert response.json()["error"] == "cluster_not_found"


def test_get_explain_denies_a_principal_in_a_different_org_unit(client: TestClient) -> None:
    other_unit_principal = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-2")
    app.dependency_overrides[get_principal] = lambda: other_unit_principal

    response = client.get("/v1/investigations/inv-1/resolution/explain/n1")

    assert response.status_code == 404
    assert client.working_set.explain_calls == []  # type: ignore[attr-defined]
